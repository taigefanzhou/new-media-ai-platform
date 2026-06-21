from __future__ import annotations

import json
import math
import mimetypes
import platform
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from uuid import uuid4
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session, func, select
from app.core.config import get_settings
from app.core.auth import current_user
from app.core.db import engine, get_session
from app.core.security import create_token, hash_password
from app.core.storage import STORAGE_ROOT_KEY, get_storage_root, save_storage_root
from app.models.entities import (
    AIModelConfig,
    AIModelUsage,
    AuthSession,
    CopyrightStatus,
    DigitalHuman,
    Material,
    MaterialKind,
    PlatformAccount,
    PlatformCredential,
    PublishRecord,
    ReferenceVideoAnalysis,
    Script,
    SystemSetting,
    TaskStatus,
    Topic,
    TrendingSearch,
    TrendingVideo,
    TranscriptionTask,
    User,
    UserRole,
    VideoSegment,
    VideoTask,
)
from app.schemas.requests import (
    AIModelConfigCreate,
    AIModelConfigPublic,
    AIModelConfigUpdate,
    DigitalHumanCreate,
    LoginRequest,
    MaterialCreate,
    PlatformAccountCreate,
    PlatformAccountUpdate,
    PlatformCredentialCreate,
    PlatformCredentialPublic,
    PlatformCredentialUpdate,
    PublishPrepareRequest,
    ReferenceMaterialLinkCreate,
    ReferenceVideoAnalysisCreate,
    RemoteUploadSettingsUpdate,
    PublishRecordUpdate,
    ScriptBatchGenerateRequest,
    ScriptGenerateRequest,
    ScriptUpdate,
    ScriptVideoTaskCreate,
    StorageSettingsUpdate,
    TopicCreate,
    TrendingSearchCreate,
    TrendingVideoCreate,
    TranscriptionTaskCreate,
    UserCreate,
    UserPasswordReset,
    UserPublic,
    UserUpdate,
    VideoTaskBatchCreateRequest,
    VideoTaskBatchRunRequest,
    VideoTaskPublishPrepareRequest,
    VideoTaskCreate,
)
from app.services.ai_clients import ScriptGenerator
from app.services.asr import ASRClient
from app.services.export_profiles import export_profile_options, resolve_export_profile
from app.services.pipeline import VideoPipeline
from app.services.trending import TrendingCollector
from app.services.usage import estimate_text_tokens, record_generated_model_usage, record_model_usage
from app.services.video_analysis import ReferenceVideoAnalyzer


router = APIRouter()

REMOTE_UPLOAD_ENABLED_KEY = "remote_upload_enabled"
REMOTE_UPLOAD_URL_KEY = "remote_upload_url"
REMOTE_UPLOAD_PUBLIC_BASE_URL_KEY = "remote_upload_public_base_url"
REMOTE_UPLOAD_FIELD_NAME_KEY = "remote_upload_field_name"
REMOTE_UPLOAD_TOKEN_KEY = "remote_upload_token"

PRODUCTION_MODES = {"dynamic_explainer", "digital_human", "seedance_scene", "talking_head_template"}
MODEL_PURPOSE_ORDER = [
    "script",
    "knowledge",
    "compliance",
    "video_understanding",
    "video",
    "asr",
    "tts",
    "voice_clone",
    "digital_human",
]
MODEL_PURPOSE_LABELS = {
    "script": "脚本生成",
    "tts": "语音合成",
    "voice_clone": "声音复刻",
    "video": "视频生成",
    "digital_human": "数字人驱动",
    "asr": "语音识别",
    "video_understanding": "视频理解/深度拆解",
    "compliance": "合规检查",
    "knowledge": "知识库/文档/长文本",
}
MODEL_LOCAL_PROVIDERS = {"local", "mock", "stub"}
MODEL_HTTP_LOCAL_PROVIDERS = {
    "comfyui",
    "cosyvoice",
    "cosyvoice-clone",
    "f5-tts",
    "fish-speech",
    "http-json",
    "openvoice",
    "sadtalker",
    "vllm",
    "whisperx",
}


def _usage_provider_is_real_api(provider: str) -> bool:
    normalized = (provider or "").strip().lower()
    if not normalized:
        return False
    if normalized in MODEL_LOCAL_PROVIDERS or normalized in MODEL_HTTP_LOCAL_PROVIDERS:
        return False
    if "mock" in normalized or "local" in normalized:
        return False
    return True


def _api_base_looks_valid(api_base: str | None) -> bool:
    if not api_base:
        return False
    parsed = urlparse(api_base)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _model_requires_api_base(purpose: str, provider: str) -> bool:
    if provider in MODEL_LOCAL_PROVIDERS:
        return False
    return purpose in set(MODEL_PURPOSE_ORDER)


def _model_requires_api_key(purpose: str, provider: str) -> bool:
    if provider in MODEL_LOCAL_PROVIDERS or provider in MODEL_HTTP_LOCAL_PROVIDERS:
        return False
    if purpose == "video" and provider == "comfyui":
        return False
    return True


def _diagnose_model_config(
    config: AIModelConfig | None,
    purpose: str | None = None,
    require_active: bool = True,
) -> dict[str, object]:
    resolved_purpose = purpose or (config.purpose if config else "")
    if not config:
        return {
            "purpose": resolved_purpose,
            "purpose_label": MODEL_PURPOSE_LABELS.get(resolved_purpose, resolved_purpose),
            "model_config_id": None,
            "name": "未启用模型",
            "provider": "-",
            "model_name": "-",
            "is_active": False,
            "has_api_base": False,
            "has_api_key": False,
            "configured": False,
            "real_api": False,
            "missing": ["active_model"],
            "level": "blocked",
            "summary": "还没有启用的模型配置。",
            "next_action": "到 AI 模型接入里新增或启用一个模型配置。",
        }

    provider = config.provider
    api_base = (config.api_base or "").strip()
    has_api_base = bool(api_base)
    has_valid_api_base = _api_base_looks_valid(api_base)
    has_api_key = bool(config.api_key)
    missing: list[str] = []
    if require_active and not config.is_active:
        missing.append("active")
    if _model_requires_api_base(config.purpose, provider):
        if not has_api_base:
            missing.append("api_base")
        elif not has_valid_api_base:
            missing.append("valid_api_base")
    if _model_requires_api_key(config.purpose, provider) and not has_api_key:
        missing.append("api_key")

    configured = not missing
    real_api = configured and provider not in MODEL_LOCAL_PROVIDERS
    if provider in MODEL_LOCAL_PROVIDERS:
        level = "mock" if configured else "blocked"
        summary = "当前使用本地/测试模式，不会调用真实外部接口。" if configured else "本地/测试模型未启用。"
        next_action = "如果要真实生成，请切换为火山、千问或已部署的 HTTP 服务。"
    elif configured:
        level = "ready"
        summary = "接口地址和密钥要求已满足，业务运行时可以调用这个模型。"
        next_action = "可以在对应业务页面发起真实任务，系统会记录调用用量。"
    else:
        level = "blocked"
        missing_labels = {
            "active": "启用状态",
            "api_base": "接口地址",
            "valid_api_base": "有效接口地址",
            "api_key": "API Key",
        }
        missing_text = "、".join(missing_labels.get(item, item) for item in missing)
        summary = f"配置不完整，缺少：{missing_text}。"
        next_action = f"补齐{missing_text}后再测试或运行任务。"

    return {
        "purpose": config.purpose,
        "purpose_label": MODEL_PURPOSE_LABELS.get(config.purpose, config.purpose),
        "model_config_id": config.id,
        "name": config.name,
        "provider": provider,
        "model_name": config.model_name,
        "is_active": config.is_active,
        "has_api_base": has_api_base,
        "has_api_key": has_api_key,
        "configured": configured,
        "real_api": real_api,
        "missing": missing,
        "level": level,
        "summary": summary,
        "next_action": next_action,
    }


def _active_model_config(session: Session, purpose: str) -> AIModelConfig | None:
    return session.exec(
        select(AIModelConfig).where(AIModelConfig.purpose == purpose, AIModelConfig.is_active == True)
    ).first()


def _model_config_public(config: AIModelConfig) -> AIModelConfigPublic:
    return AIModelConfigPublic(
        id=config.id or 0,
        name=config.name,
        provider=config.provider,
        purpose=config.purpose,
        api_base=config.api_base,
        model_name=config.model_name,
        is_active=config.is_active,
        notes=config.notes,
        created_at=config.created_at,
        has_api_key=bool(config.api_key),
    )


def _configured_model_status(
    session: Session,
    purpose: str,
    fallback_provider: str,
    fallback_model: str = "",
    fallback_configured: bool = False,
) -> dict[str, object]:
    config = _active_model_config(session, purpose)
    if config:
        diagnostic = _diagnose_model_config(config, require_active=False)
        return {
            "provider": config.provider,
            "configured": diagnostic["configured"],
            "model": config.model_name,
            "real_api": diagnostic["real_api"],
            "missing": diagnostic["missing"],
        }
    return {
        "provider": fallback_provider,
        "configured": fallback_configured,
        "model": fallback_model,
        "real_api": fallback_configured and fallback_provider not in MODEL_LOCAL_PROVIDERS,
        "missing": [] if fallback_configured else ["model_config"],
    }


async def _run_video_task_background(task_id: int) -> None:
    with Session(engine) as session:
        task = session.get(VideoTask, task_id)
        if task is not None:
            await VideoPipeline(session).run(task)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/auth/login")
def login(payload: LoginRequest, session: Session = Depends(get_session)) -> dict[str, object]:
    user = session.exec(select(User).where(User.username == payload.username)).first()
    if user is None or user.password_hash != hash_password(payload.password) or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_token()
    auth_session = AuthSession(user_id=user.id, token=token)
    session.add(auth_session)
    session.commit()
    return {
        "token": token,
        "user": {"id": user.id, "username": user.username, "role": user.role},
    }


@router.get("/auth/me")
def me(user: User = Depends(current_user)) -> dict[str, object]:
    return {"id": user.id, "username": user.username, "role": user.role}


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin account required")
    return user


def _user_public(user: User) -> UserPublic:
    return UserPublic(
        id=user.id or 0,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.get("/settings/users", response_model=list[UserPublic])
def list_users(
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> list[UserPublic]:
    users = session.exec(select(User).order_by(User.created_at.desc())).all()
    return [_user_public(item) for item in users]


@router.post("/settings/users", response_model=UserPublic)
def create_user(
    payload: UserCreate,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> UserPublic:
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    existing = session.exec(select(User).where(User.username == username)).first()
    if existing is not None:
        raise HTTPException(status_code=400, detail="Username already exists")
    user = User(
        username=username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=payload.is_active,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return _user_public(user)


@router.patch("/settings/users/{user_id}", response_model=UserPublic)
def update_user(
    user_id: int,
    payload: UserUpdate,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> UserPublic:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    update_data = payload.model_dump(exclude_unset=True)
    if user.id == admin.id and (
        update_data.get("is_active") is False or update_data.get("role") not in (None, UserRole.admin)
    ):
        raise HTTPException(status_code=400, detail="Cannot disable or demote the current admin account")
    for key, value in update_data.items():
        setattr(user, key, value)
    session.add(user)
    session.commit()
    session.refresh(user)
    return _user_public(user)


@router.post("/settings/users/{user_id}/reset-password", response_model=UserPublic)
def reset_user_password(
    user_id: int,
    payload: UserPasswordReset,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> UserPublic:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.password_hash = hash_password(payload.password)
    session.add(user)
    session.commit()
    session.refresh(user)
    return _user_public(user)


@router.get("/dashboard")
def dashboard(session: Session = Depends(get_session)) -> dict[str, object]:
    counts = {
        "materials": session.exec(select(func.count()).select_from(Material)).one(),
        "topics": session.exec(select(func.count()).select_from(Topic)).one(),
        "scripts": session.exec(select(func.count()).select_from(Script)).one(),
        "digital_humans": session.exec(select(func.count()).select_from(DigitalHuman)).one(),
        "video_tasks": session.exec(select(func.count()).select_from(VideoTask)).one(),
        "publish_records": session.exec(select(func.count()).select_from(PublishRecord)).one(),
        "trending_videos": session.exec(select(func.count()).select_from(TrendingVideo)).one(),
        "transcriptions": session.exec(select(func.count()).select_from(TranscriptionTask)).one(),
        "video_analyses": session.exec(select(func.count()).select_from(ReferenceVideoAnalysis)).one(),
    }
    recent_tasks = session.exec(select(VideoTask).order_by(VideoTask.created_at.desc()).limit(5)).all()
    recent_scripts = session.exec(select(Script).order_by(Script.created_at.desc()).limit(5)).all()
    return {"counts": counts, "recent_tasks": recent_tasks, "recent_scripts": recent_scripts}


@router.get("/settings/models", response_model=list[AIModelConfigPublic])
def list_model_configs(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[AIModelConfigPublic]:
    configs = session.exec(select(AIModelConfig).order_by(AIModelConfig.created_at.desc())).all()
    return [_model_config_public(config) for config in configs]


@router.get("/settings/model-diagnostics")
def model_diagnostics(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict[str, object]:
    items = []
    for purpose in MODEL_PURPOSE_ORDER:
        config = _active_model_config(session, purpose)
        items.append(_diagnose_model_config(config, purpose))
    return {
        "items": items,
        "ready_count": sum(1 for item in items if item["level"] == "ready"),
        "mock_count": sum(1 for item in items if item["level"] == "mock"),
        "blocked_count": sum(1 for item in items if item["level"] == "blocked"),
    }


@router.get("/settings/model-usage")
def model_usage_summary(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict[str, object]:
    rows = session.exec(select(AIModelUsage).order_by(AIModelUsage.created_at.desc())).all()
    summary: dict[tuple[str, str, str], dict[str, object]] = {}
    all_time_totals = {
        "call_count": 0,
        "success_count": 0,
        "failed_count": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    active_configs = {purpose: _active_model_config(session, purpose) for purpose in MODEL_PURPOSE_ORDER}
    active_diagnostics = {
        item["purpose"]: item for item in (_diagnose_model_config(active_configs.get(purpose), purpose) for purpose in MODEL_PURPOSE_ORDER)
    }
    for row in rows:
        key = (row.purpose, row.provider, row.model_name)
        diagnostic = active_diagnostics.get(row.purpose) or {}
        active_config = active_configs.get(row.purpose)
        is_current_config = bool(
            active_config
            and active_config.provider == row.provider
            and active_config.model_name == row.model_name
        )
        item = summary.setdefault(
            key,
            {
                "purpose": row.purpose,
                "purpose_label": MODEL_PURPOSE_LABELS.get(row.purpose, row.purpose),
                "provider": row.provider,
                "model_name": row.model_name,
                "active_level": diagnostic.get("level", "unknown"),
                "real_api": _usage_provider_is_real_api(row.provider),
                "current_config": is_current_config,
                "call_count": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "success_count": 0,
                "failed_count": 0,
                "last_status": row.status,
                "last_used_at": row.created_at,
            },
        )
        item["real_api"] = _usage_provider_is_real_api(row.provider)
        item["current_config"] = bool(item["current_config"]) or is_current_config
        item["call_count"] = int(item["call_count"]) + 1
        item["prompt_tokens"] = int(item["prompt_tokens"]) + row.prompt_tokens
        item["completion_tokens"] = int(item["completion_tokens"]) + row.completion_tokens
        item["total_tokens"] = int(item["total_tokens"]) + row.total_tokens
        item["success_count" if row.status == "success" else "failed_count"] = (
            int(item["success_count" if row.status == "success" else "failed_count"]) + 1
        )
        if row.created_at > item["last_used_at"]:
            item["last_used_at"] = row.created_at
            item["last_status"] = row.status
        all_time_totals["call_count"] += 1
        all_time_totals["success_count" if row.status == "success" else "failed_count"] += 1
        all_time_totals["prompt_tokens"] += row.prompt_tokens
        all_time_totals["completion_tokens"] += row.completion_tokens
        all_time_totals["total_tokens"] += row.total_tokens
    current_items: list[dict[str, object]] = []
    historical_items: list[dict[str, object]] = []
    totals = {
        "call_count": 0,
        "success_count": 0,
        "failed_count": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "current_config_count": 0,
        "historical_count": 0,
        "real_api_count": 0,
        "mock_count": 0,
        "current_model_count": 0,
        "historical_real_api_count": 0,
        "historical_mock_count": 0,
    }
    active_keys: set[tuple[str, str, str]] = set()
    for purpose in MODEL_PURPOSE_ORDER:
        config = active_configs.get(purpose)
        diagnostic = active_diagnostics.get(purpose) or {}
        key = (purpose, config.provider, config.model_name) if config else None
        if key:
            active_keys.add(key)
        item = dict(summary.get(key, {})) if key else {}
        current_item = {
            "purpose": purpose,
            "purpose_label": MODEL_PURPOSE_LABELS.get(purpose, purpose),
            "provider": config.provider if config else "-",
            "model_name": config.model_name if config else "-",
            "active_level": diagnostic.get("level", "blocked"),
            "real_api": bool(diagnostic.get("real_api")),
            "current_config": bool(config),
            "call_count": int(item.get("call_count") or 0),
            "prompt_tokens": int(item.get("prompt_tokens") or 0),
            "completion_tokens": int(item.get("completion_tokens") or 0),
            "total_tokens": int(item.get("total_tokens") or 0),
            "success_count": int(item.get("success_count") or 0),
            "failed_count": int(item.get("failed_count") or 0),
            "last_status": item.get("last_status") or "",
            "last_used_at": item.get("last_used_at"),
        }
        current_items.append(current_item)
        totals["current_model_count"] += 1
        totals["call_count"] += int(current_item["call_count"])
        totals["success_count"] += int(current_item["success_count"])
        totals["failed_count"] += int(current_item["failed_count"])
        totals["prompt_tokens"] += int(current_item["prompt_tokens"])
        totals["completion_tokens"] += int(current_item["completion_tokens"])
        totals["total_tokens"] += int(current_item["total_tokens"])
        totals["current_config_count"] += int(current_item["call_count"])
        if current_item["real_api"]:
            totals["real_api_count"] += int(current_item["call_count"])
        else:
            totals["mock_count"] += int(current_item["call_count"])

    for key, item in summary.items():
        if key in active_keys:
            continue
        item["current_config"] = False
        historical_items.append(item)
        totals["historical_count"] += int(item["call_count"])
        if item["real_api"]:
            totals["historical_real_api_count"] += int(item["call_count"])
        else:
            totals["historical_mock_count"] += int(item["call_count"])
    return {
        "totals": totals,
        "all_time_totals": all_time_totals,
        "items": current_items,
        "historical_items": sorted(historical_items, key=lambda item: item["last_used_at"], reverse=True),
        "recent": rows[:20],
    }


@router.get("/settings/video-storage")
def video_storage_summary(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict[str, object]:
    storage_root = get_storage_root(session)
    storage_setting = session.get(SystemSetting, STORAGE_ROOT_KEY)
    home_dir = Path.home()
    suggested_roots = [
        {"label": "当前保存位置", "path": str(storage_root)},
        {"label": "桌面：AI 视频成片", "path": str(home_dir / "Desktop" / "AI视频成片")},
        {"label": "文档：AI 视频素材", "path": str(home_dir / "Documents" / "AI视频素材")},
        {"label": "影片：AI 视频输出", "path": str(home_dir / "Movies" / "AI视频输出")},
    ]
    tasks = session.exec(select(VideoTask).order_by(VideoTask.created_at.desc())).all()
    videos = []
    total_size = 0
    existing_count = 0
    missing_count = 0
    external_count = 0
    placeholder_count = 0
    for task in tasks:
        if not task.output_path:
            continue
        output_path = task.output_path
        is_mock_path = output_path.startswith("mock://")
        is_external_path = output_path.startswith(("http://", "https://"))
        is_local_path = not is_external_path and not is_mock_path
        path = Path(output_path) if is_local_path else None
        exists = bool(path and path.exists() and path.is_file())
        size_bytes = path.stat().st_size if path and exists else 0
        total_size += size_bytes
        if is_local_path:
            existing_count += 1 if exists else 0
            missing_count += 0 if exists else 1
            storage_kind = "local"
        elif is_external_path:
            external_count += 1
            storage_kind = "external"
        else:
            placeholder_count += 1
            storage_kind = "placeholder"
        script = session.get(Script, task.script_id)
        videos.append(
            {
                "task_id": task.id,
                "script_id": task.script_id,
                "script_title": script.hook if script else f"脚本 #{task.script_id}",
                "status": task.status,
                "target_platform": task.target_platform,
                "export_profile": task.export_profile,
                "export_width": task.export_width,
                "export_height": task.export_height,
                "output_path": str(path.resolve()) if path else output_path,
                "exists": exists,
                "storage_kind": storage_kind,
                "size_bytes": size_bytes,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
            }
        )
    return {
        "storage_root": str(storage_root),
        "final_video_dir": str(storage_root / "final"),
        "segment_video_dir": str(storage_root / "seedance"),
        "digital_human_dir": str(storage_root / "digital-human"),
        "voice_dir": str(storage_root / "voice"),
        "configured_by": "后台设置" if storage_setting and storage_setting.value else "STORAGE_DIR",
        "final_video_pattern": str(storage_root / "final" / "{自动生成ID}" / "final-video.mp4"),
        "suggested_roots": suggested_roots,
        "totals": {
            "video_count": len(videos),
            "existing_count": existing_count,
            "missing_count": missing_count,
            "external_count": external_count,
            "placeholder_count": placeholder_count,
            "size_bytes": total_size,
        },
        "videos": videos,
    }


@router.patch("/settings/video-storage")
def update_video_storage(
    payload: StorageSettingsUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict[str, object]:
    try:
        save_storage_root(session, payload.storage_root)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"无法使用这个目录：{exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return video_storage_summary(session=session, user=user)


@router.get("/settings/remote-upload")
def remote_upload_settings(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict[str, object]:
    settings = _remote_upload_settings(session)
    return {
        "enabled": settings["enabled"],
        "upload_url": settings["upload_url"],
        "public_base_url": settings["public_base_url"],
        "file_field_name": settings["file_field_name"],
        "has_upload_token": bool(settings["upload_token"]),
        "ready": bool(settings["enabled"] and settings["upload_url"]),
    }


@router.patch("/settings/remote-upload")
def update_remote_upload_settings(
    payload: RemoteUploadSettingsUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict[str, object]:
    upload_url = (payload.upload_url or "").strip()
    public_base_url = (payload.public_base_url or "").strip()
    field_name = (payload.file_field_name or "file").strip() or "file"
    if payload.enabled and not upload_url:
        raise HTTPException(status_code=400, detail="启用素材服务器上传前，请先填写上传接口地址。")
    if upload_url and not _api_base_looks_valid(upload_url):
        raise HTTPException(status_code=400, detail="上传接口地址必须是 http 或 https 地址。")
    if public_base_url and not _api_base_looks_valid(public_base_url):
        raise HTTPException(status_code=400, detail="访问域名必须是 http 或 https 地址。")

    _save_system_setting(session, REMOTE_UPLOAD_ENABLED_KEY, "1" if payload.enabled else "0")
    _save_system_setting(session, REMOTE_UPLOAD_URL_KEY, upload_url)
    _save_system_setting(session, REMOTE_UPLOAD_PUBLIC_BASE_URL_KEY, public_base_url)
    _save_system_setting(session, REMOTE_UPLOAD_FIELD_NAME_KEY, field_name)
    if payload.clear_upload_token:
        _save_system_setting(session, REMOTE_UPLOAD_TOKEN_KEY, "")
    elif payload.upload_token:
        _save_system_setting(session, REMOTE_UPLOAD_TOKEN_KEY, payload.upload_token.strip())
    return remote_upload_settings(session=session, user=user)


@router.post("/materials/{material_id}/remote-upload", response_model=Material)
async def upload_material_to_remote(
    material_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> Material:
    material = session.get(Material, material_id)
    if material is None:
        raise HTTPException(status_code=404, detail="Material not found")
    await _publish_material_to_remote(material, session, require_config=True)
    session.refresh(material)
    return material


@router.post("/settings/video-storage/choose-folder")
def choose_video_storage_folder(user: User = Depends(current_user)) -> dict[str, str]:
    if platform.system() != "Darwin":
        raise HTTPException(status_code=400, detail="当前环境不支持系统文件夹选择，请手动输入本机目录。")
    script = 'POSIX path of (choose folder with prompt "请选择 AI 视频文件保存位置")'
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=400, detail="选择文件夹超时，请重试或手动输入目录。") from exc
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=400, detail="没有选择文件夹。") from exc
    selected_path = result.stdout.strip()
    if not selected_path:
        raise HTTPException(status_code=400, detail="没有选择文件夹。")
    return {"storage_root": str(Path(selected_path).expanduser().resolve())}


@router.post("/settings/models", response_model=AIModelConfigPublic)
def create_model_config(
    payload: AIModelConfigCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> AIModelConfigPublic:
    if payload.is_active:
        _deactivate_models(session, payload.purpose)
    config = AIModelConfig.model_validate(payload)
    session.add(config)
    session.commit()
    session.refresh(config)
    return _model_config_public(config)


@router.patch("/settings/models/{model_id}", response_model=AIModelConfigPublic)
def update_model_config(
    model_id: int,
    payload: AIModelConfigUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> AIModelConfigPublic:
    config = session.get(AIModelConfig, model_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Model config not found")
    update_data = payload.model_dump(exclude_unset=True)
    if update_data.get("is_active") is True:
        _deactivate_models(session, update_data.get("purpose", config.purpose))
    for key, value in update_data.items():
        setattr(config, key, value)
    session.add(config)
    session.commit()
    session.refresh(config)
    return _model_config_public(config)


@router.post("/settings/models/{model_id}/activate", response_model=AIModelConfigPublic)
def activate_model_config(
    model_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> AIModelConfigPublic:
    config = session.get(AIModelConfig, model_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Model config not found")
    _deactivate_models(session, config.purpose)
    config.is_active = True
    session.add(config)
    session.commit()
    session.refresh(config)
    return _model_config_public(config)


@router.post("/settings/models/{model_id}/test")
async def test_model_config(
    model_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict[str, object]:
    config = session.get(AIModelConfig, model_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Model config not found")
    try:
        diagnostic = _diagnose_model_config(config, require_active=False)
        if not diagnostic["configured"]:
            raise ValueError(str(diagnostic["summary"]))
        if config.purpose == "video_understanding":
            result = await ReferenceVideoAnalyzer(config).test_connection()
            result["test_level"] = "live_api"
        elif config.provider in MODEL_LOCAL_PROVIDERS:
            result = {
                "ok": True,
                "provider": config.provider,
                "model_name": config.model_name,
                "quality_score": 60,
                "test_level": "local",
                "summary": "本地或测试模式可用，但不会调用真实外部 API。",
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }
        else:
            result = {
                "ok": True,
                "provider": config.provider,
                "model_name": config.model_name,
                "quality_score": 75,
                "test_level": "configuration",
                "summary": (
                    f"{MODEL_PURPOSE_LABELS.get(config.purpose, config.purpose)}配置体检通过："
                    "接口地址和密钥要求已满足，真实调用会在对应业务运行时执行。"
                ),
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }
        usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
        record_model_usage(
            session=session,
            purpose=config.purpose,
            model_config=config,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            total_tokens=int(usage.get("total_tokens") or 0),
        )
        session.commit()
        return result
    except Exception as exc:
        record_model_usage(
            session=session,
            purpose=config.purpose,
            model_config=config,
            status="failed",
        )
        session.commit()
        raise HTTPException(status_code=400, detail=f"模型测试失败：{exc}") from exc


def _deactivate_models(session: Session, purpose: str) -> None:
    configs = session.exec(select(AIModelConfig).where(AIModelConfig.purpose == purpose)).all()
    for item in configs:
        item.is_active = False
        session.add(item)


@router.get("/settings/platform-credentials", response_model=list[PlatformCredentialPublic])
def list_platform_credentials(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[PlatformCredentialPublic]:
    credentials = session.exec(
        select(PlatformCredential).order_by(
            PlatformCredential.is_active.desc(),
            PlatformCredential.created_at.desc(),
        )
    ).all()
    return [_platform_credential_public(item) for item in credentials]


@router.post("/settings/platform-credentials", response_model=PlatformCredentialPublic)
def create_platform_credential(
    payload: PlatformCredentialCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> PlatformCredentialPublic:
    if payload.is_active:
        _deactivate_platform_credentials(session, payload.platform, payload.purpose)
    credential = PlatformCredential.model_validate(payload)
    credential.updated_at = datetime.utcnow()
    session.add(credential)
    session.commit()
    session.refresh(credential)
    return _platform_credential_public(credential)


@router.patch("/settings/platform-credentials/{credential_id}", response_model=PlatformCredentialPublic)
def update_platform_credential(
    credential_id: int,
    payload: PlatformCredentialUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> PlatformCredentialPublic:
    credential = session.get(PlatformCredential, credential_id)
    if credential is None:
        raise HTTPException(status_code=404, detail="Platform credential not found")
    update_data = payload.model_dump(exclude_unset=True)
    next_platform = update_data.get("platform", credential.platform)
    next_purpose = update_data.get("purpose", credential.purpose)
    if update_data.get("is_active") is True:
        _deactivate_platform_credentials(session, next_platform, next_purpose)
    for key, value in update_data.items():
        setattr(credential, key, value)
    credential.updated_at = datetime.utcnow()
    session.add(credential)
    session.commit()
    session.refresh(credential)
    return _platform_credential_public(credential)


@router.post("/settings/platform-credentials/{credential_id}/activate", response_model=PlatformCredentialPublic)
def activate_platform_credential(
    credential_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> PlatformCredentialPublic:
    credential = session.get(PlatformCredential, credential_id)
    if credential is None:
        raise HTTPException(status_code=404, detail="Platform credential not found")
    _deactivate_platform_credentials(session, credential.platform, credential.purpose)
    credential.is_active = True
    credential.status = "active"
    credential.updated_at = datetime.utcnow()
    session.add(credential)
    session.commit()
    session.refresh(credential)
    return _platform_credential_public(credential)


def _deactivate_platform_credentials(session: Session, platform: str, purpose: str) -> None:
    credentials = session.exec(
        select(PlatformCredential).where(
            PlatformCredential.platform == platform,
            PlatformCredential.purpose == purpose,
        )
    ).all()
    for item in credentials:
        item.is_active = False
        session.add(item)


def _platform_credential_public(credential: PlatformCredential) -> PlatformCredentialPublic:
    return PlatformCredentialPublic(
        id=credential.id or 0,
        platform=credential.platform,
        purpose=credential.purpose,
        display_name=credential.display_name,
        api_base=credential.api_base,
        client_id=credential.client_id,
        webhook_url=credential.webhook_url,
        status=credential.status,
        is_active=credential.is_active,
        notes=credential.notes,
        has_client_secret=bool(credential.client_secret),
        has_access_token=bool(credential.access_token),
        has_refresh_token=bool(credential.refresh_token),
    )


@router.get("/integrations/status")
def integrations_status(session: Session = Depends(get_session)) -> dict[str, dict[str, object]]:
    settings = get_settings()
    return {
        "script_model": _configured_model_status(
            session,
            "script",
            settings.llm_provider,
            settings.llm_model,
            bool(settings.llm_api_base and settings.llm_api_key) or settings.llm_provider == "stub",
        ),
        "tts": _configured_model_status(
            session,
            "tts",
            settings.tts_provider,
            settings.tts_voice,
            bool(settings.tts_api_base) or settings.tts_provider == "mock",
        ),
        "digital_human": _configured_model_status(
            session,
            "digital_human",
            settings.digital_human_provider,
            settings.digital_human_provider,
            bool(settings.digital_human_api_base) or settings.digital_human_provider == "mock",
        ),
        "voice_clone": _configured_model_status(
            session,
            "voice_clone",
            settings.voice_clone_provider,
            settings.voice_clone_provider,
            bool(settings.voice_clone_api_base and settings.voice_clone_api_key),
        ),
        "video_generation": _configured_model_status(
            session,
            "video",
            settings.video_generation_provider,
            settings.seedance_model,
            settings.video_generation_provider == "mock" or bool(settings.seedance_api_base) or bool(settings.comfyui_api_base),
        ),
        "video_understanding": _configured_model_status(
            session,
            "video_understanding",
            "local",
            "local-video-analyzer",
            False,
        ),
        "composition": {
            "provider": settings.composition_provider,
            "configured": settings.composition_provider in ("mock", "ffmpeg"),
        },
        "trending_search": {
            "provider": settings.trending_search_provider,
            "configured": settings.trending_search_provider == "mock" or bool(settings.trending_search_api_base),
        },
        "asr": _configured_model_status(
            session,
            "asr",
            settings.asr_provider,
            settings.asr_model,
            settings.asr_provider == "mock" or bool(settings.asr_api_base),
        ),
    }


@router.get("/video-export-profiles")
def list_video_export_profiles() -> list[dict[str, object]]:
    return export_profile_options()


@router.post("/materials", response_model=Material)
def create_material(payload: MaterialCreate, session: Session = Depends(get_session)) -> Material:
    material = Material.model_validate(payload)
    session.add(material)
    session.commit()
    session.refresh(material)
    return material


REFERENCE_MEDIA_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".m4v",
    ".webm",
    ".mkv",
    ".avi",
    ".mp3",
    ".m4a",
    ".aac",
    ".wav",
}


def _reference_title_from_url(source_url: str) -> str:
    parsed = urlparse(source_url)
    filename = Path(parsed.path).name
    stem = Path(filename).stem if filename else ""
    if stem and stem.lower() not in {"stodownload", "download", "video"}:
        return stem[:80]
    return parsed.netloc or "参考视频链接"


def _reference_tags(platform: str, tags: str) -> str:
    values = ["参考素材", platform.strip()]
    values.extend(item.strip() for item in tags.split(",") if item.strip())
    deduped = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return ",".join(deduped)


def _media_suffix_from_response(source_url: str, content_type: str, content_disposition: str) -> str:
    disposition_parts = content_disposition.split(";") if content_disposition else []
    for part in disposition_parts:
        if "filename=" not in part:
            continue
        filename = part.split("=", 1)[1].strip().strip('"')
        suffix = Path(filename).suffix.lower()
        if suffix in REFERENCE_MEDIA_EXTENSIONS:
            return suffix

    parsed_url = urlparse(source_url)
    url_suffix = Path(parsed_url.path).suffix.lower()
    if url_suffix in REFERENCE_MEDIA_EXTENSIONS:
        return url_suffix
    if "finder.video.qq.com" in parsed_url.netloc and "stodownload" in parsed_url.path:
        return ".mp4"

    normalized_type = content_type.split(";", 1)[0].strip().lower()
    if normalized_type == "video/mp4":
        return ".mp4"
    if normalized_type == "video/quicktime":
        return ".mov"
    if normalized_type == "audio/mpeg":
        return ".mp3"
    if normalized_type == "audio/mp4":
        return ".m4a"
    guessed = mimetypes.guess_extension(normalized_type) or ""
    if guessed in REFERENCE_MEDIA_EXTENSIONS:
        return guessed
    if normalized_type.startswith("video/"):
        return ".mp4"
    if normalized_type.startswith("audio/"):
        return ".m4a"
    return ""


def _response_looks_like_reference_media(source_url: str, content_type: str, content_disposition: str) -> bool:
    normalized_type = content_type.split(";", 1)[0].strip().lower()
    if normalized_type.startswith(("video/", "audio/")):
        return True
    if _media_suffix_from_response(source_url, content_type, content_disposition):
        return True
    return False


async def _download_reference_media(source_url: str, storage_dir: Path) -> Path | None:
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="请输入有效的视频链接。")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        ),
        "Accept": "video/mp4,video/*;q=0.9,audio/*;q=0.8,*/*;q=0.5",
    }
    max_bytes = 800 * 1024 * 1024
    async with httpx.AsyncClient(timeout=600, follow_redirects=True, headers=headers) as client:
        async with client.stream("GET", source_url) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            content_disposition = response.headers.get("content-disposition", "")
            if not _response_looks_like_reference_media(source_url, content_type, content_disposition):
                return None
            suffix = _media_suffix_from_response(source_url, content_type, content_disposition) or ".mp4"
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > max_bytes:
                raise HTTPException(status_code=400, detail="参考视频文件超过 800MB，请先下载后上传。")

            storage_dir.mkdir(parents=True, exist_ok=True)
            file_path = storage_dir / f"source{suffix}"
            total = 0
            with open(file_path, "wb") as output:
                async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        output.close()
                        _delete_local_file(str(file_path))
                        raise HTTPException(status_code=400, detail="参考视频文件超过 800MB，请先下载后上传。")
                    output.write(chunk)
            if total == 0:
                _delete_local_file(str(file_path))
                return None
            return file_path


@router.post("/reference-materials/from-link", response_model=Material)
async def create_reference_material_from_link(
    payload: ReferenceMaterialLinkCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> Material:
    source_url = payload.source_url.strip()
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="请输入 http 或 https 开头的视频链接。")

    storage_dir = get_storage_root(session) / "materials" / uuid4().hex
    file_path: Path | None = None
    if payload.download:
        try:
            file_path = await _download_reference_media(source_url, storage_dir)
        except HTTPException:
            raise
        except Exception:
            file_path = None

    material = Material(
        name=(payload.title or "").strip() or _reference_title_from_url(source_url),
        kind=MaterialKind.reference,
        copyright_status=CopyrightStatus.reference_only,
        file_path=str(file_path) if file_path else None,
        source_url=source_url,
        tags=_reference_tags(payload.platform, payload.tags),
    )
    session.add(material)
    session.commit()
    session.refresh(material)
    return material


@router.post("/materials/upload", response_model=Material)
async def upload_material(
    file: UploadFile = File(...),
    name: Optional[str] = Form(default=None),
    kind: MaterialKind = Form(default=MaterialKind.image),
    copyright_status: CopyrightStatus = Form(default=CopyrightStatus.owned),
    tags: str = Form(default=""),
    session: Session = Depends(get_session),
) -> Material:
    return await _save_uploaded_material(
        file=file,
        kind=kind,
        name=name,
        copyright_status=copyright_status,
        tags=tags,
        session=session,
    )


async def _save_uploaded_material(
    file: UploadFile,
    kind: MaterialKind,
    name: Optional[str],
    session: Session,
    copyright_status: CopyrightStatus = CopyrightStatus.owned,
    tags: str = "",
) -> Material:
    original_name = file.filename or "upload.bin"
    suffix = Path(original_name).suffix
    storage_dir = get_storage_root(session) / "materials" / uuid4().hex
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_path = storage_dir / f"source{suffix}"
    file_path.write_bytes(await file.read())

    material = Material(
        name=name or original_name,
        kind=kind,
        copyright_status=copyright_status,
        file_path=str(file_path),
        tags=tags,
    )
    session.add(material)
    session.commit()
    session.refresh(material)
    try:
        await _publish_material_to_remote(material, session)
        session.refresh(material)
    except Exception:
        pass
    return material


def _save_system_setting(session: Session, key: str, value: str) -> SystemSetting:
    setting = session.get(SystemSetting, key)
    if setting is None:
        setting = SystemSetting(key=key)
    setting.value = value
    setting.updated_at = datetime.utcnow()
    session.add(setting)
    session.commit()
    session.refresh(setting)
    return setting


def _system_setting_value(session: Session, key: str) -> str:
    setting = session.get(SystemSetting, key)
    return setting.value.strip() if setting and setting.value else ""


def _remote_upload_settings(session: Session) -> dict[str, object]:
    return {
        "enabled": _system_setting_value(session, REMOTE_UPLOAD_ENABLED_KEY) == "1",
        "upload_url": _system_setting_value(session, REMOTE_UPLOAD_URL_KEY),
        "public_base_url": _system_setting_value(session, REMOTE_UPLOAD_PUBLIC_BASE_URL_KEY),
        "file_field_name": _system_setting_value(session, REMOTE_UPLOAD_FIELD_NAME_KEY) or "file",
        "upload_token": _system_setting_value(session, REMOTE_UPLOAD_TOKEN_KEY),
    }


async def _publish_material_to_remote(
    material: Material,
    session: Session,
    require_config: bool = False,
) -> None:
    if material.source_url and material.source_url.startswith(("http://", "https://")):
        return
    settings = _remote_upload_settings(session)
    if not settings["enabled"] or not settings["upload_url"]:
        if require_config:
            raise HTTPException(status_code=400, detail="请先在视频存储位置里配置素材服务器上传接口。")
        return
    if not material.file_path or not Path(material.file_path).exists():
        if require_config:
            raise HTTPException(status_code=400, detail="素材本地文件不存在，无法上传到服务器。")
        return

    upload_url = str(settings["upload_url"])
    field_name = str(settings["file_field_name"] or "file")
    token = str(settings["upload_token"] or "")
    path = Path(material.file_path)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with open(path, "rb") as file_obj:
        files = {field_name: (path.name, file_obj, "application/octet-stream")}
        data = {
            "material_id": str(material.id or ""),
            "name": material.name,
            "kind": material.kind.value if hasattr(material.kind, "value") else str(material.kind),
        }
        async with httpx.AsyncClient(timeout=600) as client:
            response = await client.post(upload_url, headers=headers, files=files, data=data)
            response.raise_for_status()
            try:
                result = response.json()
            except ValueError:
                result = response.text
    source_url = _extract_remote_upload_url(result)
    if not source_url and settings["public_base_url"]:
        source_url = _join_public_base_url(str(settings["public_base_url"]), path.name)
    if not source_url:
        raise HTTPException(status_code=400, detail="素材服务器未返回 url/source_url/file_url 字段。")
    material.source_url = source_url
    session.add(material)
    session.commit()


def _extract_remote_upload_url(result: object) -> str:
    if isinstance(result, str):
        return result if result.startswith(("http://", "https://")) else ""
    if not isinstance(result, dict):
        return ""
    for key in ("source_url", "url", "file_url", "public_url", "download_url"):
        value = result.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    data = result.get("data")
    if isinstance(data, dict):
        return _extract_remote_upload_url(data)
    return ""


def _join_public_base_url(base_url: str, filename: str) -> str:
    return f"{base_url.rstrip('/')}/{filename.lstrip('/')}"


@router.get("/materials", response_model=list[Material])
def list_materials(session: Session = Depends(get_session)) -> list[Material]:
    return list(session.exec(select(Material).order_by(Material.created_at.desc())).all())


@router.get("/materials/{material_id}/preview")
def preview_material(material_id: int, session: Session = Depends(get_session)) -> FileResponse:
    material = session.get(Material, material_id)
    if material is None or not material.file_path:
        raise HTTPException(status_code=404, detail="Material preview not found")
    path = Path(material.file_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Material file not found")
    return FileResponse(path)


@router.delete("/materials/{material_id}")
def delete_material(material_id: int, session: Session = Depends(get_session)) -> dict[str, object]:
    material = session.get(Material, material_id)
    if material is None:
        raise HTTPException(status_code=404, detail="Material not found")

    humans = session.exec(
        select(DigitalHuman).where(
            (DigitalHuman.portrait_material_id == material_id)
            | (DigitalHuman.source_video_material_id == material_id)
        )
    ).all()
    for human in humans:
        if human.portrait_material_id == material_id:
            human.portrait_material_id = None
        if human.source_video_material_id == material_id:
            human.source_video_material_id = None
        session.add(human)

    topics = session.exec(select(Topic).where(Topic.reference_material_id == material_id)).all()
    for topic in topics:
        topic.reference_material_id = None
        session.add(topic)

    transcriptions = session.exec(select(TranscriptionTask).where(TranscriptionTask.material_id == material_id)).all()
    for task in transcriptions:
        session.delete(task)
    analyses = session.exec(select(ReferenceVideoAnalysis).where(ReferenceVideoAnalysis.material_id == material_id)).all()
    for analysis in analyses:
        _delete_local_file(analysis.contact_sheet_path)
        _delete_local_file(analysis.dense_contact_sheet_path)
        session.delete(analysis)

    _delete_local_file(material.file_path)
    session.delete(material)
    session.commit()
    return {"deleted": True, "id": material_id}


@router.post("/transcriptions", response_model=TranscriptionTask)
def create_transcription_task(
    payload: TranscriptionTaskCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> TranscriptionTask:
    if session.get(Material, payload.material_id) is None:
        raise HTTPException(status_code=404, detail="Material not found")
    task = TranscriptionTask(
        material_id=payload.material_id,
        language=payload.language,
        provider=get_settings().asr_provider,
        status=TaskStatus.queued,
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@router.post("/transcriptions/{task_id}/run", response_model=TranscriptionTask)
async def run_transcription_task(
    task_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> TranscriptionTask:
    task = session.get(TranscriptionTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Transcription task not found")
    material = session.get(Material, task.material_id)
    if material is None:
        raise HTTPException(status_code=404, detail="Material not found")
    active_model = _active_model_config(session, "asr")
    settings = get_settings()
    task.provider = active_model.provider if active_model else settings.asr_provider
    task.status = TaskStatus.running
    session.add(task)
    session.commit()
    try:
        result = await ASRClient(active_model).transcribe(task, material)
        task.transcript = result.transcript
        task.summary = result.summary
        task.hook_analysis = result.hook_analysis
        task.status = TaskStatus.needs_review
        record_model_usage(
            session=session,
            purpose="asr",
            model_config=active_model,
            provider=settings.asr_provider,
            model_name=settings.asr_model,
            completion_tokens=estimate_text_tokens(result.transcript, result.summary, result.hook_analysis),
        )
    except Exception as exc:
        task.status = TaskStatus.failed
        task.error_message = str(exc)
        record_model_usage(
            session=session,
            purpose="asr",
            model_config=active_model,
            provider=settings.asr_provider,
            model_name=settings.asr_model,
            status="failed",
        )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@router.get("/transcriptions", response_model=list[TranscriptionTask])
def list_transcription_tasks(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[TranscriptionTask]:
    return list(session.exec(select(TranscriptionTask).order_by(TranscriptionTask.created_at.desc())).all())


@router.post("/transcriptions/{task_id}/create-topic", response_model=Topic)
def create_topic_from_transcription(
    task_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> Topic:
    task = session.get(TranscriptionTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Transcription task not found")
    if not task.transcript:
        raise HTTPException(status_code=400, detail="Transcription has no transcript")
    material = session.get(Material, task.material_id)
    title_seed = task.hook_analysis or task.summary or task.transcript[:80]
    topic = Topic(
        title=_topic_title_from_text(title_seed),
        industry="待补充",
        audience="目标客户",
        reference_material_id=task.material_id,
        notes=(
            f"来源素材：{material.name if material else task.material_id}\n"
            f"摘要：{task.summary}\n"
            f"钩子分析：{task.hook_analysis}"
        ),
    )
    session.add(topic)
    session.commit()
    session.refresh(topic)
    return topic


@router.post("/transcriptions/{task_id}/generate-script", response_model=Script)
async def generate_script_from_transcription(
    task_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> Script:
    task = session.get(TranscriptionTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Transcription task not found")
    if not task.transcript:
        raise HTTPException(status_code=400, detail="Transcription has no transcript")
    topic = (
        "基于参考视频结构，生成原创公司短视频脚本。"
        f"参考摘要：{task.summary}。"
        f"开头钩子分析：{task.hook_analysis}。"
        "要求只借鉴结构和选题，不复制原文。"
    )
    active_model = _active_model_config(session, "script")
    generated = await ScriptGenerator(active_model).generate(
        topic=topic,
        brand_voice="专业、可信、原创、适合公司数字人口播",
        duration_seconds=30,
        target_platform="douyin",
    )
    script = Script(
        topic_id=None,
        target_platform="douyin",
        duration_seconds=30,
        hook=generated.hook,
        voiceover=generated.voiceover,
        storyboard=generated.storyboard,
        storyboard_plan=json.dumps(getattr(generated, "storyboard_plan", []) or [], ensure_ascii=False),
        seedance_prompt=generated.seedance_prompt,
        title_options=generated.title_options,
        hashtags=generated.hashtags,
        compliance_notes=f"{generated.compliance_notes}\n基于转写任务 #{task.id} 生成，仅借鉴结构，不搬运原文。",
    )
    session.add(script)
    settings = get_settings()
    record_generated_model_usage(
        session,
        "script",
        generated,
        active_model,
        provider=settings.llm_provider,
        model_name=settings.llm_model,
    )
    session.commit()
    session.refresh(script)
    return script


def _latest_transcript_for_material(session: Session, material_id: int) -> str:
    task = session.exec(
        select(TranscriptionTask)
        .where(TranscriptionTask.material_id == material_id, TranscriptionTask.transcript != "")
        .order_by(TranscriptionTask.updated_at.desc())
    ).first()
    return task.transcript if task else ""


@router.post("/video-analyses", response_model=ReferenceVideoAnalysis)
def create_reference_video_analysis(
    payload: ReferenceVideoAnalysisCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> ReferenceVideoAnalysis:
    material = session.get(Material, payload.material_id)
    if material is None:
        raise HTTPException(status_code=404, detail="Material not found")
    if material.kind not in (MaterialKind.avatar_source, MaterialKind.video, MaterialKind.reference):
        raise HTTPException(status_code=400, detail="深度视频拆解需要选择视频或参考素材。")
    task = ReferenceVideoAnalysis(
        material_id=payload.material_id,
        provider=payload.provider,
        language=payload.language,
        status=TaskStatus.queued,
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@router.post("/video-analyses/{analysis_id}/run", response_model=ReferenceVideoAnalysis)
async def run_reference_video_analysis(
    analysis_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> ReferenceVideoAnalysis:
    task = session.get(ReferenceVideoAnalysis, analysis_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Reference video analysis not found")
    material = session.get(Material, task.material_id)
    if material is None:
        raise HTTPException(status_code=404, detail="Material not found")

    active_model = _active_model_config(session, "video_understanding")
    task.provider = active_model.provider if active_model else task.provider or "local"
    task.status = TaskStatus.running
    task.error_message = None
    task.updated_at = datetime.utcnow()
    session.add(task)
    session.commit()
    session.refresh(task)

    try:
        transcript = _latest_transcript_for_material(session, task.material_id)
        result = await ReferenceVideoAnalyzer(active_model).analyze(task, material, transcript=transcript)
        task.duration_seconds = result.duration_seconds
        task.width = result.width
        task.height = result.height
        task.fps = result.fps
        task.has_audio = result.has_audio
        task.scene_count = result.scene_count
        task.avg_shot_seconds = result.avg_shot_seconds
        task.visual_change_frequency = result.visual_change_frequency
        task.contact_sheet_path = result.contact_sheet_path
        task.dense_contact_sheet_path = result.dense_contact_sheet_path
        task.timeline_json = result.timeline_json
        task.transcript = transcript
        task.script_analysis = result.script_analysis
        task.shooting_analysis = result.shooting_analysis
        task.editing_analysis = result.editing_analysis
        task.reusable_template = result.reusable_template
        task.reuse_notes = result.reuse_notes
        task.quality_score = result.quality_score
        task.quality_summary = result.quality_summary
        task.model_enhanced = result.model_enhanced
        task.status = TaskStatus.needs_review
        estimated_completion_tokens = estimate_text_tokens(
            task.script_analysis,
            task.shooting_analysis,
            task.editing_analysis,
            task.reusable_template,
            task.reuse_notes,
        )
        completion_tokens = result.completion_tokens or max(0, result.total_tokens - result.prompt_tokens)
        record_model_usage(
            session=session,
            purpose="video_understanding",
            model_config=active_model,
            provider=task.provider,
            model_name=active_model.model_name if active_model else "local-video-analyzer",
            prompt_tokens=result.prompt_tokens,
            completion_tokens=completion_tokens or estimated_completion_tokens,
        )
    except Exception as exc:
        task.status = TaskStatus.failed
        task.error_message = str(exc)
        record_model_usage(
            session=session,
            purpose="video_understanding",
            model_config=active_model,
            provider=task.provider,
            model_name=active_model.model_name if active_model else "local-video-analyzer",
            status="failed",
        )
    task.updated_at = datetime.utcnow()
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@router.get("/video-analyses", response_model=list[ReferenceVideoAnalysis])
def list_reference_video_analyses(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[ReferenceVideoAnalysis]:
    return list(session.exec(select(ReferenceVideoAnalysis).order_by(ReferenceVideoAnalysis.created_at.desc())).all())


@router.post("/video-analyses/{analysis_id}/approve", response_model=ReferenceVideoAnalysis)
def approve_reference_video_analysis(
    analysis_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> ReferenceVideoAnalysis:
    task = session.get(ReferenceVideoAnalysis, analysis_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Reference video analysis not found")
    if task.status == TaskStatus.failed:
        raise HTTPException(status_code=400, detail="失败的拆解结果不能采纳，请重新拆解。")
    task.status = TaskStatus.approved
    task.updated_at = datetime.utcnow()
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@router.post("/video-analyses/{analysis_id}/reject", response_model=ReferenceVideoAnalysis)
def reject_reference_video_analysis(
    analysis_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> ReferenceVideoAnalysis:
    task = session.get(ReferenceVideoAnalysis, analysis_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Reference video analysis not found")
    task.status = TaskStatus.rejected
    task.updated_at = datetime.utcnow()
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@router.get("/video-analyses/{analysis_id}/contact-sheet")
def reference_video_analysis_contact_sheet(
    analysis_id: int,
    session: Session = Depends(get_session),
) -> FileResponse:
    task = session.get(ReferenceVideoAnalysis, analysis_id)
    if task is None or not task.contact_sheet_path:
        raise HTTPException(status_code=404, detail="Contact sheet not found")
    path = Path(task.contact_sheet_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Contact sheet file not found")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/video-analyses/{analysis_id}/dense-contact-sheet")
def reference_video_analysis_dense_contact_sheet(
    analysis_id: int,
    session: Session = Depends(get_session),
) -> FileResponse:
    task = session.get(ReferenceVideoAnalysis, analysis_id)
    if task is None or not task.dense_contact_sheet_path:
        raise HTTPException(status_code=404, detail="Dense contact sheet not found")
    path = Path(task.dense_contact_sheet_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Dense contact sheet file not found")
    return FileResponse(path, media_type="image/jpeg")


@router.post("/video-analyses/{analysis_id}/generate-script", response_model=Script)
async def generate_script_from_reference_video_analysis(
    analysis_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> Script:
    task = session.get(ReferenceVideoAnalysis, analysis_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Reference video analysis not found")
    if task.status != TaskStatus.approved:
        raise HTTPException(status_code=400, detail="请先在拆解详情里采纳这个参考模板。")
    material = session.get(Material, task.material_id)
    topic = (
        "基于参考视频的结构生成原创公司短视频脚本，不能复刻原画面、原文和人物。"
        f"参考素材：{material.name if material else task.material_id}。"
        f"脚本结构分析：{task.script_analysis}\n"
        f"拍摄方式分析：{task.shooting_analysis}\n"
        f"剪辑方式分析：{task.editing_analysis}\n"
        f"可复用模板：{task.reusable_template}\n"
        "请改写成适合酒店智能化、酒店运营或公司负责人数字人口播的原创脚本。"
    )
    active_model = _active_model_config(session, "script")
    generated = await ScriptGenerator(active_model).generate(
        topic=topic,
        brand_voice="专业、可信、适合公司负责人口播；学习参考视频的结构和节奏，但不搬运原文和画面。",
        duration_seconds=max(30, min(180, int(task.duration_seconds or 60))),
        target_platform="wechat_channels" if task.height >= task.width else "douyin",
        output_language="zh-CN",
    )
    payload = ScriptGenerateRequest(
        topic=topic,
        brand_voice="专业、可信、适合公司负责人口播；学习参考视频的结构和节奏，但不搬运原文和画面。",
        duration_seconds=max(30, min(180, int(task.duration_seconds or 60))),
        target_platform="wechat_channels" if task.height >= task.width else "douyin",
        output_language="zh-CN",
    )
    script = _create_script_record(session, payload, generated, active_model)
    script.compliance_notes = (
        f"{script.compliance_notes}\n基于深度视频拆解 #{task.id} 生成，仅学习结构、节奏、拍摄和剪辑方法。"
    )
    session.add(script)
    session.commit()
    session.refresh(script)
    return script


def _topic_title_from_text(text: str) -> str:
    cleaned = " ".join(text.replace("\n", " ").split())
    if not cleaned:
        return "参考视频改写选题"
    return cleaned[:48]


@router.post("/topics", response_model=Topic)
def create_topic(payload: TopicCreate, session: Session = Depends(get_session)) -> Topic:
    topic = Topic.model_validate(payload)
    session.add(topic)
    session.commit()
    session.refresh(topic)
    return topic


@router.get("/topics", response_model=list[Topic])
def list_topics(session: Session = Depends(get_session)) -> list[Topic]:
    return list(session.exec(select(Topic).order_by(Topic.created_at.desc())).all())


def _create_script_record(
    session: Session,
    payload: ScriptGenerateRequest,
    generated,
    model_config: Optional[AIModelConfig] = None,
) -> Script:
    storyboard_plan = json.dumps(getattr(generated, "storyboard_plan", []) or [], ensure_ascii=False)
    script = Script(
        topic_id=payload.topic_id,
        target_platform=payload.target_platform,
        duration_seconds=payload.duration_seconds,
        hook=generated.hook,
        voiceover=generated.voiceover,
        storyboard=generated.storyboard,
        storyboard_plan=storyboard_plan,
        seedance_prompt=generated.seedance_prompt,
        title_options=generated.title_options,
        hashtags=generated.hashtags,
        compliance_notes=generated.compliance_notes,
    )
    session.add(script)
    settings = get_settings()
    record_generated_model_usage(
        session,
        "script",
        generated,
        model_config,
        provider=settings.llm_provider,
        model_name=settings.llm_model,
    )
    session.commit()
    session.refresh(script)
    return script


@router.post("/scripts/generate", response_model=Script)
async def generate_script(payload: ScriptGenerateRequest, session: Session = Depends(get_session)) -> Script:
    active_model = _active_model_config(session, "script")
    generated = await ScriptGenerator(active_model).generate(
        topic=payload.topic,
        brand_voice=payload.brand_voice,
        duration_seconds=payload.duration_seconds,
        target_platform=payload.target_platform,
        output_language=payload.output_language,
    )
    return _create_script_record(session, payload, generated, active_model)


@router.post("/scripts/batch-generate", response_model=list[Script])
async def batch_generate_scripts(payload: ScriptBatchGenerateRequest, session: Session = Depends(get_session)) -> list[Script]:
    active_model = _active_model_config(session, "script")
    generator = ScriptGenerator(active_model)
    topics = [item.strip() for item in payload.topics if item.strip()] or [
        f"{payload.topic}\n批量生成第 {index + 1} 条：请换一个标题角度、开头钩子和分镜结构，避免与其他脚本重复。"
        for index in range(payload.count)
    ]
    scripts: list[Script] = []
    for index, topic in enumerate(topics[: payload.count]):
        generated = await generator.generate(
            topic=topic,
            brand_voice=payload.brand_voice,
            duration_seconds=payload.duration_seconds,
            target_platform=payload.target_platform,
            output_language=payload.output_language,
        )
        item_payload = ScriptGenerateRequest(
            topic_id=payload.topic_id,
            topic=topic,
            brand_voice=payload.brand_voice,
            duration_seconds=payload.duration_seconds,
            target_platform=payload.target_platform,
            output_language=payload.output_language,
        )
        script = _create_script_record(session, item_payload, generated, active_model)
        scripts.append(script)
    return scripts


@router.get("/scripts", response_model=list[Script])
def list_scripts(session: Session = Depends(get_session)) -> list[Script]:
    return list(session.exec(select(Script).order_by(Script.created_at.desc())).all())


@router.patch("/scripts/{script_id}", response_model=Script)
def update_script(script_id: int, payload: ScriptUpdate, session: Session = Depends(get_session)) -> Script:
    script = session.get(Script, script_id)
    if script is None:
        raise HTTPException(status_code=404, detail="Script not found")
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if value is not None:
            setattr(script, key, value)
    session.add(script)
    session.commit()
    session.refresh(script)
    return script


def _estimated_video_segment_count(duration_seconds: int) -> int:
    clip_duration = 10 if duration_seconds >= 60 else 5
    return max(1, min(36, math.ceil(max(duration_seconds, clip_duration) / clip_duration)))


def _build_video_task(
    script: Script,
    digital_human_id: Optional[int],
    production_mode: str = "talking_head_template",
    target_platform: Optional[str] = None,
    export_profile: Optional[str] = None,
    status: TaskStatus = TaskStatus.queued,
    audit_notes: str = "",
) -> VideoTask:
    if production_mode not in PRODUCTION_MODES:
        raise HTTPException(status_code=400, detail="Unknown production mode")
    segment_count = _estimated_video_segment_count(script.duration_seconds)
    platform_name = target_platform or script.target_platform or "douyin"
    profile = resolve_export_profile(export_profile, platform_name)
    return VideoTask(
        script_id=script.id or 0,
        digital_human_id=digital_human_id,
        status=status,
        target_platform=platform_name,
        export_profile=profile.key,
        export_width=profile.width,
        export_height=profile.height,
        generation_mode="long" if script.duration_seconds >= 120 else "short",
        production_mode=production_mode,
        segment_count=segment_count,
        completed_segments=0,
        audit_notes=audit_notes,
    )


def _validate_video_task_inputs(
    session: Session,
    production_mode: str,
    digital_human_id: Optional[int],
) -> None:
    if production_mode not in PRODUCTION_MODES:
        raise HTTPException(status_code=400, detail="Unknown production mode")
    if digital_human_id is None:
        if production_mode in {"digital_human", "talking_head_template"}:
            raise HTTPException(status_code=400, detail="数字人口播需要选择数字人，并上传头像或口播源视频。")
        return
    human = session.get(DigitalHuman, digital_human_id)
    if human is None:
        raise HTTPException(status_code=404, detail="Digital human not found")
    if (
        production_mode in {"digital_human", "talking_head_template"}
        and human.portrait_material_id is None
        and human.source_video_material_id is None
    ):
        raise HTTPException(status_code=400, detail="数字人口播需要先上传该数字人的头像或口播源视频。")
    if production_mode in {"digital_human", "talking_head_template"} and not _digital_human_service_ready(session):
        raise HTTPException(status_code=400, detail="数字人口播需要先在系统设置里配置真实数字人驱动接口。")


def _digital_human_service_ready(session: Session) -> bool:
    model_config = _active_model_config(session, "digital_human")
    settings = get_settings()
    if model_config:
        return bool(_diagnose_model_config(model_config)["configured"])
    api_base = model_config.api_base if model_config and model_config.api_base else settings.digital_human_api_base
    provider = model_config.provider if model_config else settings.digital_human_provider
    if provider in MODEL_LOCAL_PROVIDERS:
        return False
    if provider in {"sadtalker", "http-json"}:
        return bool(api_base)
    return bool(api_base and settings.digital_human_api_key)


def _ensure_video_task_can_run(task: VideoTask) -> None:
    if task.status == TaskStatus.running:
        raise HTTPException(status_code=409, detail="Video task is already generating")
    if task.output_path or task.status in (TaskStatus.needs_review, TaskStatus.approved):
        raise HTTPException(status_code=400, detail="Video task already has generated output")
    if task.status not in (TaskStatus.draft, TaskStatus.queued, TaskStatus.failed):
        raise HTTPException(status_code=400, detail="Video task is not ready to generate")


@router.post("/scripts/{script_id}/video-task", response_model=VideoTask)
def create_video_task_from_script(
    script_id: int,
    payload: ScriptVideoTaskCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> VideoTask:
    script = session.get(Script, script_id)
    if script is None:
        raise HTTPException(status_code=404, detail="Script not found")
    _validate_video_task_inputs(session, payload.production_mode, payload.digital_human_id)
    task = _build_video_task(
        script,
        payload.digital_human_id,
        production_mode=payload.production_mode,
        target_platform=payload.target_platform,
        export_profile=payload.export_profile,
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@router.post("/scripts/{script_id}/auto-video-task", response_model=VideoTask)
async def approve_script_and_run_video_task(
    script_id: int,
    payload: ScriptVideoTaskCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> VideoTask:
    script = session.get(Script, script_id)
    if script is None:
        raise HTTPException(status_code=404, detail="Script not found")
    _validate_video_task_inputs(session, payload.production_mode, payload.digital_human_id)
    task = _build_video_task(
        script,
        payload.digital_human_id,
        production_mode=payload.production_mode,
        target_platform=payload.target_platform,
        export_profile=payload.export_profile,
        status=TaskStatus.running,
        audit_notes=f"脚本已审核通过，系统已按「{payload.production_mode}」创建视频任务并进入生成队列。",
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    background_tasks.add_task(_run_video_task_background, task.id)
    return task


@router.post("/digital-humans", response_model=DigitalHuman)
def create_digital_human(payload: DigitalHumanCreate, session: Session = Depends(get_session)) -> DigitalHuman:
    if payload.portrait_material_id is not None and session.get(Material, payload.portrait_material_id) is None:
        raise HTTPException(status_code=404, detail="Portrait material not found")
    if payload.source_video_material_id is not None:
        source_material = session.get(Material, payload.source_video_material_id)
        if source_material is None:
            raise HTTPException(status_code=404, detail="Source video material not found")
        if source_material.kind not in (MaterialKind.avatar_source, MaterialKind.video):
            raise HTTPException(status_code=400, detail="Source video material must be a video source")
    human = DigitalHuman.model_validate(payload)
    session.add(human)
    session.commit()
    session.refresh(human)
    return human


@router.post("/digital-humans/create-with-assets", response_model=DigitalHuman)
async def create_digital_human_with_assets(
    name: str = Form(...),
    role: Optional[str] = Form(default=None),
    style: str = Form(default="realistic"),
    authorization_scope: str = Form(default="internal_marketing"),
    default_voice: Optional[str] = Form(default=None),
    portrait_material_id: Optional[int] = Form(default=None),
    source_video_material_id: Optional[int] = Form(default=None),
    portrait_file: Optional[UploadFile] = File(default=None),
    source_video_file: Optional[UploadFile] = File(default=None),
    session: Session = Depends(get_session),
) -> DigitalHuman:
    portrait_id = portrait_material_id
    source_video_id = source_video_material_id

    if portrait_file is not None and portrait_file.filename:
        portrait = await _save_uploaded_material(
            file=portrait_file,
            kind=MaterialKind.portrait,
            name=f"{name}头像",
            tags="digital-human,portrait",
            session=session,
        )
        portrait_id = portrait.id

    if source_video_file is not None and source_video_file.filename:
        source_video = await _save_uploaded_material(
            file=source_video_file,
            kind=MaterialKind.avatar_source,
            name=f"{name}口播源视频",
            tags="digital-human,voice-source",
            session=session,
        )
        source_video_id = source_video.id

    payload = DigitalHumanCreate(
        name=name,
        role=role,
        style=style,
        portrait_material_id=portrait_id,
        source_video_material_id=source_video_id,
        default_voice=default_voice,
        authorization_scope=authorization_scope,
    )
    return create_digital_human(payload, session)


@router.get("/digital-humans", response_model=list[DigitalHuman])
def list_digital_humans(session: Session = Depends(get_session)) -> list[DigitalHuman]:
    return list(session.exec(select(DigitalHuman).order_by(DigitalHuman.created_at.desc())).all())


@router.delete("/digital-humans/{human_id}")
def delete_digital_human(human_id: int, session: Session = Depends(get_session)) -> dict[str, object]:
    human = session.get(DigitalHuman, human_id)
    if human is None:
        raise HTTPException(status_code=404, detail="Digital human not found")
    tasks = session.exec(select(VideoTask).where(VideoTask.digital_human_id == human_id)).all()
    for task in tasks:
        task.digital_human_id = None
        session.add(task)
    session.delete(human)
    session.commit()
    return {"deleted": True, "id": human_id}


@router.post("/video-tasks", response_model=VideoTask)
def create_video_task(payload: VideoTaskCreate, session: Session = Depends(get_session)) -> VideoTask:
    script = session.get(Script, payload.script_id)
    if script is None:
        raise HTTPException(status_code=404, detail="Script not found")
    _validate_video_task_inputs(session, payload.production_mode, payload.digital_human_id)
    task = _build_video_task(
        script,
        payload.digital_human_id,
        production_mode=payload.production_mode,
        target_platform=payload.target_platform,
        export_profile=payload.export_profile,
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@router.post("/video-tasks/batch-create", response_model=list[VideoTask])
def batch_create_video_tasks(payload: VideoTaskBatchCreateRequest, session: Session = Depends(get_session)) -> list[VideoTask]:
    _validate_video_task_inputs(session, payload.production_mode, payload.digital_human_id)
    tasks: list[VideoTask] = []
    for script_id in payload.script_ids:
        script = session.get(Script, script_id)
        if script is None:
            raise HTTPException(status_code=404, detail=f"Script {script_id} not found")
        task = _build_video_task(
            script,
            payload.digital_human_id,
            production_mode=payload.production_mode,
            target_platform=payload.target_platform,
            export_profile=payload.export_profile,
        )
        session.add(task)
        tasks.append(task)
    session.commit()
    for task in tasks:
        session.refresh(task)
    return tasks


@router.post("/video-tasks/batch-run", response_model=list[VideoTask])
async def batch_run_video_tasks(payload: VideoTaskBatchRunRequest, session: Session = Depends(get_session)) -> list[VideoTask]:
    pipeline = VideoPipeline(session)
    results: list[VideoTask] = []
    for task_id in payload.task_ids:
        task = session.get(VideoTask, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"Video task {task_id} not found")
        _ensure_video_task_can_run(task)
        results.append(await pipeline.run(task))
    return results


@router.post("/video-tasks/{task_id}/run", response_model=VideoTask)
async def run_video_task(task_id: int, session: Session = Depends(get_session)) -> VideoTask:
    task = session.get(VideoTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Video task not found")
    _ensure_video_task_can_run(task)
    return await VideoPipeline(session).run(task)


@router.post("/video-tasks/{task_id}/approve", response_model=VideoTask)
def approve_video_task(task_id: int, session: Session = Depends(get_session)) -> VideoTask:
    task = session.get(VideoTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Video task not found")
    if task.status != TaskStatus.needs_review or not task.output_path:
        raise HTTPException(status_code=400, detail="Only generated videos waiting for review can be approved")
    task.status = TaskStatus.approved
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@router.get("/video-tasks", response_model=list[VideoTask])
def list_video_tasks(session: Session = Depends(get_session)) -> list[VideoTask]:
    return list(session.exec(select(VideoTask).order_by(VideoTask.created_at.desc())).all())


@router.get("/video-tasks/{task_id}/segments", response_model=list[VideoSegment])
def list_video_task_segments(task_id: int, session: Session = Depends(get_session)) -> list[VideoSegment]:
    if session.get(VideoTask, task_id) is None:
        raise HTTPException(status_code=404, detail="Video task not found")
    return list(
        session.exec(
            select(VideoSegment)
            .where(VideoSegment.video_task_id == task_id)
            .order_by(VideoSegment.segment_index.asc())
        ).all()
    )


@router.get("/video-tasks/{task_id}/output")
def preview_video_task_output(task_id: int, session: Session = Depends(get_session)) -> FileResponse:
    task = session.get(VideoTask, task_id)
    if task is None or not task.output_path:
        raise HTTPException(status_code=404, detail="Video output not found")
    path = Path(task.output_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Video file not found")
    return FileResponse(path, media_type="video/mp4")


@router.delete("/video-tasks/{task_id}/output")
def delete_video_task_output(task_id: int, session: Session = Depends(get_session)) -> dict[str, object]:
    task = session.get(VideoTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Video task not found")
    if task.status == TaskStatus.running:
        raise HTTPException(status_code=409, detail="Cannot delete output while video is generating")
    if not task.output_path:
        raise HTTPException(status_code=400, detail="Video task has no generated output")
    _delete_local_file(task.output_path)
    segments = session.exec(select(VideoSegment).where(VideoSegment.video_task_id == task_id)).all()
    for segment in segments:
        _delete_local_file(segment.output_path)
        segment.output_path = None
        segment.status = TaskStatus.queued
        segment.error_message = None
        segment.updated_at = datetime.utcnow()
        session.add(segment)
    task.output_path = None
    task.status = TaskStatus.queued
    task.completed_segments = 0
    task.updated_at = datetime.utcnow()
    session.add(task)
    session.commit()
    return {"deleted": True, "id": task_id, "target": "output"}


@router.delete("/video-tasks/{task_id}")
def delete_video_task(task_id: int, session: Session = Depends(get_session)) -> dict[str, object]:
    task = session.get(VideoTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Video task not found")
    if task.status == TaskStatus.running:
        raise HTTPException(status_code=409, detail="Cannot delete a video task while it is generating")
    records = session.exec(select(PublishRecord).where(PublishRecord.video_task_id == task_id)).all()
    for record in records:
        session.delete(record)
    segments = session.exec(select(VideoSegment).where(VideoSegment.video_task_id == task_id)).all()
    for segment in segments:
        _delete_local_file(segment.output_path)
        session.delete(segment)
    _delete_local_file(task.output_path)
    session.delete(task)
    session.commit()
    return {"deleted": True, "id": task_id}


@router.post("/video-tasks/{task_id}/publish-record", response_model=PublishRecord)
def prepare_publish_record_from_video_task(
    task_id: int,
    payload: VideoTaskPublishPrepareRequest,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> PublishRecord:
    task = session.get(VideoTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Video task not found")
    if task.status != TaskStatus.approved:
        raise HTTPException(status_code=400, detail="Video task must be approved before publishing")
    if not task.output_path:
        raise HTTPException(status_code=400, detail="Video task has no generated output")
    script = session.get(Script, task.script_id)
    account = _resolve_publish_account(session, payload.platform_account_id, payload.platform)
    title = payload.title or _publish_title_from_script(script)
    record = PublishRecord(
        video_task_id=task.id,
        platform=account.platform if account else payload.platform,
        platform_account_id=account.id if account else payload.platform_account_id,
        account_name=account.account_name if account else payload.account_name,
        title=title,
        hashtags=payload.hashtags or _hashtags_from_script(script),
        caption=payload.caption or _caption_from_script(script),
        scheduled_at=_parse_optional_datetime(payload.scheduled_at),
        publish_status="prepared",
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _publish_title_from_script(script: Optional[Script]) -> str:
    if script is None:
        return "待发布视频"
    first_line = script.title_options.splitlines()[0] if script.title_options else ""
    return first_line.replace("1.", "").strip() or script.hook[:40] or "待发布视频"


def _hashtags_from_script(script: Optional[Script]) -> str:
    return script.hashtags if script else ""


def _caption_from_script(script: Optional[Script]) -> str:
    if script is None:
        return ""
    return f"{script.hook}\n\n{script.hashtags}".strip()


def _parse_optional_datetime(value: Optional[str]):
    if not value:
        return None
    return datetime.fromisoformat(value)


def _resolve_publish_account(
    session: Session,
    account_id: Optional[int],
    platform: Optional[str],
) -> Optional[PlatformAccount]:
    if account_id is not None:
        account = session.get(PlatformAccount, account_id)
        if account is None:
            raise HTTPException(status_code=404, detail="Platform account not found")
        return account
    if platform is None:
        return None
    return session.exec(
        select(PlatformAccount).where(
            PlatformAccount.platform == platform,
            PlatformAccount.is_default == True,
        )
    ).first()


def _clear_default_account(session: Session, platform: str) -> None:
    accounts = session.exec(select(PlatformAccount).where(PlatformAccount.platform == platform)).all()
    for account in accounts:
        account.is_default = False
        session.add(account)


@router.post("/trending/searches", response_model=TrendingSearch)
def create_trending_search(
    payload: TrendingSearchCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> TrendingSearch:
    search = TrendingSearch.model_validate(payload)
    session.add(search)
    session.commit()
    session.refresh(search)
    return search


@router.post("/trending/searches/{search_id}/run", response_model=TrendingSearch)
async def run_trending_search(
    search_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> TrendingSearch:
    search = session.get(TrendingSearch, search_id)
    if search is None:
        raise HTTPException(status_code=404, detail="Trending search not found")
    search.status = TaskStatus.running
    session.add(search)
    session.commit()

    credential = _active_platform_credential(session, search.platform, "trending")
    videos = await TrendingCollector(credential).collect(search)
    for video in videos:
        session.add(video)
    search.status = TaskStatus.needs_review
    search.result_count = len(videos)
    session.add(search)
    session.commit()
    session.refresh(search)
    return search


@router.get("/trending/searches", response_model=list[TrendingSearch])
def list_trending_searches(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[TrendingSearch]:
    return list(session.exec(select(TrendingSearch).order_by(TrendingSearch.created_at.desc())).all())


@router.get("/trending/videos", response_model=list[TrendingVideo])
def list_trending_videos(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[TrendingVideo]:
    return list(session.exec(select(TrendingVideo).order_by(TrendingVideo.created_at.desc())).all())


@router.post("/trending/videos", response_model=TrendingVideo)
def create_trending_video(
    payload: TrendingVideoCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> TrendingVideo:
    video = TrendingVideo.model_validate(payload)
    session.add(video)
    session.commit()
    session.refresh(video)
    return video


@router.post("/publish-records", response_model=PublishRecord)
def prepare_publish_record(
    payload: PublishPrepareRequest,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> PublishRecord:
    if session.get(VideoTask, payload.video_task_id) is None:
        raise HTTPException(status_code=404, detail="Video task not found")
    account = _resolve_publish_account(session, payload.platform_account_id, payload.platform)
    record = PublishRecord(
        video_task_id=payload.video_task_id,
        platform=account.platform if account else payload.platform,
        platform_account_id=account.id if account else payload.platform_account_id,
        account_name=account.account_name if account else payload.account_name,
        title=payload.title,
        hashtags=payload.hashtags,
        caption=payload.caption,
        scheduled_at=_parse_optional_datetime(payload.scheduled_at),
        publish_status="prepared",
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


@router.get("/publish-records", response_model=list[PublishRecord])
def list_publish_records(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[PublishRecord]:
    return list(session.exec(select(PublishRecord).order_by(PublishRecord.created_at.desc())).all())


@router.patch("/publish-records/{record_id}", response_model=PublishRecord)
def update_publish_record(
    record_id: int,
    payload: PublishRecordUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> PublishRecord:
    record = session.get(PublishRecord, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Publish record not found")
    update_data = payload.model_dump(exclude_unset=True)
    if "platform_account_id" in update_data:
        account_id = update_data.pop("platform_account_id")
        if account_id is None:
            record.platform_account_id = None
            if "account_name" not in update_data:
                record.account_name = None
        else:
            account = _resolve_publish_account(session, account_id, update_data.get("platform"))
            if account is not None:
                record.platform = account.platform
                record.platform_account_id = account.id
                record.account_name = account.account_name
    for key in ("scheduled_at", "published_at"):
        if key in update_data:
            update_data[key] = _parse_optional_datetime(update_data[key])
    for key, value in update_data.items():
        setattr(record, key, value)
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


@router.post("/publish-records/{record_id}/mark-published", response_model=PublishRecord)
def mark_publish_record_published(
    record_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> PublishRecord:
    return _set_publish_status(session, record_id, "published", datetime.utcnow())


@router.post("/publish-records/{record_id}/fail", response_model=PublishRecord)
def mark_publish_record_failed(
    record_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> PublishRecord:
    return _set_publish_status(session, record_id, "failed")


@router.post("/publish-records/{record_id}/cancel", response_model=PublishRecord)
def cancel_publish_record(
    record_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> PublishRecord:
    return _set_publish_status(session, record_id, "canceled")


def _set_publish_status(
    session: Session,
    record_id: int,
    status: str,
    published_at: Optional[datetime] = None,
) -> PublishRecord:
    record = session.get(PublishRecord, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Publish record not found")
    record.publish_status = status
    if published_at is not None:
        record.published_at = published_at
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _active_platform_credential(
    session: Session,
    platform: str,
    purpose: str,
) -> Optional[PlatformCredential]:
    return session.exec(
        select(PlatformCredential).where(
            PlatformCredential.platform == platform,
            PlatformCredential.purpose == purpose,
            PlatformCredential.is_active == True,
        )
    ).first()


@router.post("/platform-accounts", response_model=PlatformAccount)
def create_platform_account(
    payload: PlatformAccountCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> PlatformAccount:
    if payload.is_default:
        _clear_default_account(session, payload.platform)
    account = PlatformAccount.model_validate(payload)
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


@router.get("/platform-accounts", response_model=list[PlatformAccount])
def list_platform_accounts(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[PlatformAccount]:
    return list(
        session.exec(
            select(PlatformAccount).order_by(
                PlatformAccount.is_default.desc(),
                PlatformAccount.created_at.desc(),
            )
        ).all()
    )


@router.patch("/platform-accounts/{account_id}", response_model=PlatformAccount)
def update_platform_account(
    account_id: int,
    payload: PlatformAccountUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> PlatformAccount:
    account = session.get(PlatformAccount, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Platform account not found")
    update_data = payload.model_dump(exclude_unset=True)
    next_platform = update_data.get("platform", account.platform)
    if update_data.get("is_default") is True:
        _clear_default_account(session, next_platform)
    for key, value in update_data.items():
        setattr(account, key, value)
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


@router.post("/platform-accounts/{account_id}/set-default", response_model=PlatformAccount)
def set_default_platform_account(
    account_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> PlatformAccount:
    account = session.get(PlatformAccount, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Platform account not found")
    _clear_default_account(session, account.platform)
    account.is_default = True
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


def _delete_local_file(path_value: Optional[str]) -> None:
    if not path_value or path_value.startswith("mock://") or path_value.startswith("http"):
        return
    path = Path(path_value)
    if path.exists() and path.is_file():
        path.unlink()
    parent = path.parent
    try:
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
    except OSError:
        return
