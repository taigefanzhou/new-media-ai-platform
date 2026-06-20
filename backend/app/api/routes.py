from __future__ import annotations

import json
import math
import platform
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4
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


router = APIRouter()

PRODUCTION_MODES = {"dynamic_explainer", "digital_human", "seedance_scene", "talking_head_template"}


def _active_model_config(session: Session, purpose: str) -> AIModelConfig | None:
    return session.exec(
        select(AIModelConfig).where(AIModelConfig.purpose == purpose, AIModelConfig.is_active == True)
    ).first()


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
    }
    recent_tasks = session.exec(select(VideoTask).order_by(VideoTask.created_at.desc()).limit(5)).all()
    recent_scripts = session.exec(select(Script).order_by(Script.created_at.desc()).limit(5)).all()
    return {"counts": counts, "recent_tasks": recent_tasks, "recent_scripts": recent_scripts}


@router.get("/settings/models", response_model=list[AIModelConfig])
def list_model_configs(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[AIModelConfig]:
    return list(session.exec(select(AIModelConfig).order_by(AIModelConfig.created_at.desc())).all())


@router.get("/settings/model-usage")
def model_usage_summary(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict[str, object]:
    rows = session.exec(select(AIModelUsage).order_by(AIModelUsage.created_at.desc())).all()
    summary: dict[tuple[str, str, str], dict[str, object]] = {}
    totals = {
        "call_count": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    for row in rows:
        key = (row.purpose, row.provider, row.model_name)
        item = summary.setdefault(
            key,
            {
                "purpose": row.purpose,
                "provider": row.provider,
                "model_name": row.model_name,
                "call_count": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "success_count": 0,
                "failed_count": 0,
                "last_used_at": row.created_at,
            },
        )
        item["call_count"] = int(item["call_count"]) + 1
        item["prompt_tokens"] = int(item["prompt_tokens"]) + row.prompt_tokens
        item["completion_tokens"] = int(item["completion_tokens"]) + row.completion_tokens
        item["total_tokens"] = int(item["total_tokens"]) + row.total_tokens
        item["success_count" if row.status == "success" else "failed_count"] = (
            int(item["success_count" if row.status == "success" else "failed_count"]) + 1
        )
        if row.created_at > item["last_used_at"]:
            item["last_used_at"] = row.created_at
        totals["call_count"] += 1
        totals["prompt_tokens"] += row.prompt_tokens
        totals["completion_tokens"] += row.completion_tokens
        totals["total_tokens"] += row.total_tokens
    return {
        "totals": totals,
        "items": sorted(summary.values(), key=lambda item: item["last_used_at"], reverse=True),
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
    for task in tasks:
        if not task.output_path:
            continue
        output_path = task.output_path
        is_local_path = not output_path.startswith(("http://", "https://", "mock://"))
        path = Path(output_path) if is_local_path else None
        exists = bool(path and path.exists() and path.is_file())
        size_bytes = path.stat().st_size if path and exists else 0
        total_size += size_bytes
        existing_count += 1 if exists else 0
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
            "missing_count": len(videos) - existing_count,
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


@router.post("/settings/models", response_model=AIModelConfig)
def create_model_config(
    payload: AIModelConfigCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> AIModelConfig:
    if payload.is_active:
        _deactivate_models(session, payload.purpose)
    config = AIModelConfig.model_validate(payload)
    session.add(config)
    session.commit()
    session.refresh(config)
    return config


@router.patch("/settings/models/{model_id}", response_model=AIModelConfig)
def update_model_config(
    model_id: int,
    payload: AIModelConfigUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> AIModelConfig:
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
    return config


@router.post("/settings/models/{model_id}/activate", response_model=AIModelConfig)
def activate_model_config(
    model_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> AIModelConfig:
    config = session.get(AIModelConfig, model_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Model config not found")
    _deactivate_models(session, config.purpose)
    config.is_active = True
    session.add(config)
    session.commit()
    session.refresh(config)
    return config


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
def integrations_status() -> dict[str, dict[str, object]]:
    settings = get_settings()
    return {
        "script_model": {
            "provider": settings.llm_provider,
            "configured": bool(settings.llm_api_base and settings.llm_api_key) or settings.llm_provider == "stub",
            "model": settings.llm_model,
        },
        "tts": {
            "provider": settings.tts_provider,
            "configured": bool(settings.tts_api_base) or settings.tts_provider == "mock",
            "voice": settings.tts_voice,
        },
        "digital_human": {
            "provider": settings.digital_human_provider,
            "configured": bool(settings.digital_human_api_base) or settings.digital_human_provider == "mock",
        },
        "voice_clone": {
            "provider": settings.voice_clone_provider,
            "configured": bool(settings.voice_clone_api_base and settings.voice_clone_api_key),
        },
        "video_generation": {
            "provider": settings.video_generation_provider,
            "configured": (
                settings.video_generation_provider == "mock"
                or bool(settings.seedance_api_base)
                or bool(settings.comfyui_api_base)
            ),
            "model": settings.seedance_model,
        },
        "composition": {
            "provider": settings.composition_provider,
            "configured": settings.composition_provider in ("mock", "ffmpeg"),
        },
        "trending_search": {
            "provider": settings.trending_search_provider,
            "configured": settings.trending_search_provider == "mock" or bool(settings.trending_search_api_base),
        },
        "asr": {
            "provider": settings.asr_provider,
            "configured": settings.asr_provider == "mock" or bool(settings.asr_api_base),
            "model": settings.asr_model,
        },
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
    return material


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
            raise HTTPException(status_code=400, detail="数字人口播需要选择数字人，并上传口播源视频。")
        return
    human = session.get(DigitalHuman, digital_human_id)
    if human is None:
        raise HTTPException(status_code=404, detail="Digital human not found")
    if production_mode in {"digital_human", "talking_head_template"} and human.source_video_material_id is None:
        raise HTTPException(status_code=400, detail="数字人口播需要先上传该数字人的口播源视频。")
    if production_mode in {"digital_human", "talking_head_template"} and not _digital_human_service_ready(session):
        raise HTTPException(status_code=400, detail="数字人口播需要先在系统设置里配置真实数字人驱动接口。")


def _digital_human_service_ready(session: Session) -> bool:
    model_config = _active_model_config(session, "digital_human")
    settings = get_settings()
    api_base = model_config.api_base if model_config and model_config.api_base else settings.digital_human_api_base
    provider = model_config.provider if model_config else settings.digital_human_provider
    return bool(api_base) and provider != "mock"


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
