from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from html import escape
import json
import math
import mimetypes
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse
from uuid import uuid4
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlmodel import Session, func, select
from app.core.config import get_settings
from app.core.auth import current_user
from app.core.db import engine, get_session
from app.core.security import create_token, hash_password, password_hash_needs_upgrade, verify_password
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
    WechatIdentity,
    WechatLoginConfig,
    WechatLoginRequest,
    WechatLoginStatus,
)
from app.schemas.requests import (
    AIModelConfigCreate,
    AIModelConfigPublic,
    AIModelConfigUpdate,
    ChangePasswordRequest,
    DigitalHumanCreate,
    LinkResolverTestRequest,
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
    VideoSegmentMaterialUpdate,
    TranscriptionTaskCreate,
    UserCreate,
    UserPasswordReset,
    UserPublic,
    UserUpdate,
    VideoTaskBatchCreateRequest,
    VideoTaskBatchRunRequest,
    VideoTaskPublishPrepareRequest,
    VideoTaskCreate,
    VolcenginePortraitAuthSessionCreate,
    WechatIdentityPublic,
    WechatLoginApproveRequest,
    WechatLoginConfigPublic,
    WechatLoginConfigUpdate,
    WechatLoginPublicConfig,
    WechatLoginRejectRequest,
    WechatLoginRequestPublic,
)
from app.services.ai_clients import MediaGenerationClient, ScriptGenerator
from app.services.asr import ASRClient
from app.services.export_profiles import resolve_export_profile
from app.services.link_resolver import (
    LinkResolverCredential,
    LinkResolution,
    ShortVideoLinkResolver,
    detect_short_video_platform,
)
from app.services.model_router import choose_model_config, is_model_config_ready
from app.services.pipeline import VideoPipeline
from app.services.trending import TrendingCollector
from app.services.usage import estimate_text_tokens, record_generated_model_usage, record_model_usage
from app.services.video_analysis import ReferenceVideoAnalyzer
from app.services.wechat_login import (
    WechatOAuthClient,
    build_wechat_qr_url,
    create_wechat_state,
    masked_suffix,
    random_temporary_password,
    verify_wechat_state,
)


router = APIRouter()

REMOTE_UPLOAD_ENABLED_KEY = "remote_upload_enabled"
REMOTE_UPLOAD_URL_KEY = "remote_upload_url"
REMOTE_UPLOAD_PUBLIC_BASE_URL_KEY = "remote_upload_public_base_url"
REMOTE_UPLOAD_FIELD_NAME_KEY = "remote_upload_field_name"
REMOTE_UPLOAD_TOKEN_KEY = "remote_upload_token"

PRODUCTION_MODES = {"dynamic_explainer", "digital_human", "material_mix", "seedance_scene", "talking_head_template"}
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
    if purpose == "digital_human" and _is_volcengine_jimeng_provider(provider):
        return False
    return True


def _is_volcengine_jimeng_provider(provider: str) -> bool:
    normalized = (provider or "").strip().lower()
    return normalized in {"volcengine-jimeng-digital-human", "jimeng-digital-human"} or (
        "jimeng" in normalized and "digital" in normalized
    )


def _active_volcengine_jimeng_credential(session: Session) -> PlatformCredential | None:
    return session.exec(
        select(PlatformCredential).where(
            PlatformCredential.platform == "volcengine",
            PlatformCredential.purpose == "digital_human",
            PlatformCredential.is_active == True,  # noqa: E712
        )
    ).first()


def _volcengine_jimeng_credential_ready(session: Session) -> bool:
    credential = _active_volcengine_jimeng_credential(session)
    return bool(
        credential
        and (credential.client_id or "").strip()
        and (credential.client_secret or "").strip()
    )


def _credential_note_value(credential: PlatformCredential | None, key: str) -> str | None:
    if credential is None:
        return None
    prefix = f"{key}="
    for line in (credential.notes or "").splitlines():
        clean = line.strip()
        if clean.startswith(prefix):
            return clean.removeprefix(prefix).strip() or None
    return None


def _append_query_param(url: str, key: str, value: str) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query[key] = value
    return urlunparse(parsed._replace(query=urlencode(query)))


def _volcengine_canonical_query(query: dict[str, str]) -> str:
    items = []
    for key in sorted(query):
        value = query[key]
        items.append(f"{quote(str(key), safe='-_.~')}={quote(str(value), safe='-_.~')}")
    return "&".join(items)


def _volcengine_signing_key(secret_key: str, short_date: str, region: str, service: str) -> bytes:
    date_key = hmac.new(secret_key.encode("utf-8"), short_date.encode("utf-8"), hashlib.sha256).digest()
    region_key = hmac.new(date_key, region.encode("utf-8"), hashlib.sha256).digest()
    service_key = hmac.new(region_key, service.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(service_key, b"request", hashlib.sha256).digest()


def _volcengine_signed_headers(
    api_base: str,
    query: dict[str, str],
    body: str,
    access_key: str,
    secret_key: str,
    *,
    region: str,
    service: str,
) -> dict[str, str]:
    parsed = urlparse(api_base)
    host = parsed.netloc
    path = parsed.path or "/"
    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc)
    x_date = now.strftime("%Y%m%dT%H%M%SZ")
    short_date = now.strftime("%Y%m%d")
    canonical_query = _volcengine_canonical_query(query)
    content_type = "application/json"
    signed_headers = "content-type;host;x-content-sha256;x-date"
    canonical_headers = (
        f"content-type:{content_type}\n"
        f"host:{host}\n"
        f"x-content-sha256:{body_hash}\n"
        f"x-date:{x_date}\n"
    )
    canonical_request = "\n".join(["POST", path, canonical_query, canonical_headers, signed_headers, body_hash])
    credential_scope = f"{short_date}/{region}/{service}/request"
    string_to_sign = "\n".join(
        [
            "HMAC-SHA256",
            x_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    signing_key = _volcengine_signing_key(secret_key, short_date, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "Authorization": (
            f"HMAC-SHA256 Credential={access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),
        "Content-Type": content_type,
        "Host": host,
        "X-Content-Sha256": body_hash,
        "X-Date": x_date,
    }


async def _volcengine_portrait_request(
    session: Session,
    action: str,
    payload: dict[str, object],
) -> dict[str, object]:
    credential = _active_volcengine_jimeng_credential(session)
    access_key = (getattr(credential, "client_id", "") or "").strip()
    secret_key = (getattr(credential, "client_secret", "") or "").strip()
    if not access_key or not secret_key:
        raise HTTPException(status_code=400, detail="请先在系统设置中启用火山数字人 AK/SK 凭证。")
    api_base = (
        _credential_note_value(credential, "portrait_api_base")
        or _credential_note_value(credential, "asset_api_base")
        or "https://ark.cn-beijing.volcengineapi.com"
    ).rstrip("/")
    region = _credential_note_value(credential, "portrait_region") or "cn-beijing"
    service = _credential_note_value(credential, "portrait_service") or "ark"
    version = _credential_note_value(credential, "portrait_version") or "2024-01-01"
    query = {"Action": action, "Version": version}
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    headers = _volcengine_signed_headers(
        api_base,
        query,
        body,
        access_key,
        secret_key,
        region=region,
        service=service,
    )
    async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
        response = await client.post(f"{api_base}?{urlencode(query)}", headers=headers, content=body)
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"火山接口返回非 JSON：HTTP {response.status_code}") from exc
    if response.status_code >= 400:
        request_id = response.headers.get("X-Tt-Logid") or response.headers.get("X-Tt-LogId") or ""
        raise HTTPException(status_code=400, detail=f"火山接口 HTTP {response.status_code}：{data} {request_id}".strip())
    metadata = data.get("ResponseMetadata") if isinstance(data, dict) else None
    error = metadata.get("Error") if isinstance(metadata, dict) else None
    if isinstance(error, dict) and error:
        request_id = metadata.get("RequestId") or metadata.get("RequestID") or ""
        message = error.get("Message") or error.get("Code") or data
        raise HTTPException(status_code=400, detail=f"火山接口 {action} 失败：{message} RequestId={request_id}".strip())
    return data


def _volcengine_result_payload(data: dict[str, object]) -> dict[str, object]:
    result = data.get("Result") or data.get("result") or data.get("Data") or data.get("data")
    if isinstance(result, dict):
        return result
    return data


def _nested_value(payload: object, keys: set[str]) -> str | None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in keys and value not in (None, ""):
                return str(value)
        for value in payload.values():
            nested = _nested_value(value, keys)
            if nested:
                return nested
    if isinstance(payload, list):
        for item in payload:
            nested = _nested_value(item, keys)
            if nested:
                return nested
    return None


def _human_portrait_auth_state(human: DigitalHuman) -> dict[str, object]:
    return {
        "digital_human_id": human.id,
        "status": human.volcengine_auth_status or "not_started",
        "auth_url": human.volcengine_auth_url,
        "byted_token": human.volcengine_byted_token,
        "result_code": human.volcengine_auth_result_code,
        "asset_group_id": human.volcengine_asset_group_id,
        "asset_group_uri": human.volcengine_asset_group_uri,
        "asset_uri": human.volcengine_asset_uri,
        "asset_status": human.volcengine_asset_status,
    }


async def _sync_volcengine_portrait_auth_result(session: Session, human: DigitalHuman) -> dict[str, object]:
    token = (human.volcengine_byted_token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="这个数字人还没有 BytedToken，请先创建 H5 认证链接。")
    data = await _volcengine_portrait_request(session, "GetVisualValidateResult", {"BytedToken": token})
    result = _volcengine_result_payload(data)
    result_code = _nested_value(result, {"ResultCode", "resultCode", "Code", "code"})
    group_id = _nested_value(result, {"GroupId", "groupId", "AssetGroupId", "assetGroupId", "asset_group_id"})
    group_uri = _nested_value(result, {"GroupUri", "groupUri", "AssetGroupUri", "assetGroupUri", "asset_group_uri"})
    human.volcengine_auth_result_code = result_code or human.volcengine_auth_result_code
    human.volcengine_asset_group_id = group_id or human.volcengine_asset_group_id
    human.volcengine_asset_group_uri = group_uri or human.volcengine_asset_group_uri
    if group_id or group_uri or result_code == "10000":
        human.volcengine_auth_status = "active"
    elif result_code:
        human.volcengine_auth_status = "failed"
    human.volcengine_auth_payload = json.dumps(result, ensure_ascii=False)[:4000]
    session.add(human)
    session.commit()
    session.refresh(human)
    return _human_portrait_auth_state(human)


def _diagnose_model_config(
    config: AIModelConfig | None,
    purpose: str | None = None,
    require_active: bool = True,
    session: Session | None = None,
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
    if (
        config.purpose == "digital_human"
        and _is_volcengine_jimeng_provider(provider)
        and session is not None
        and not _volcengine_jimeng_credential_ready(session)
    ):
        missing.append("volcengine_ak_sk")

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
            "volcengine_ak_sk": "火山 AccessKeyID/SecretAccessKey",
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


def _smart_model_config(session: Session, purpose: str, scenario: str = "") -> AIModelConfig | None:
    return choose_model_config(session, purpose, scenario)


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
        diagnostic = _diagnose_model_config(config, require_active=False, session=session)
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


def _video_generation_fallback_ready(settings) -> bool:
    provider = (settings.video_generation_provider or "").lower()
    if provider == "mock":
        return True
    if "seedance" in provider:
        return bool(settings.seedance_api_base and settings.seedance_api_key)
    if provider == "comfyui":
        return bool(settings.comfyui_api_base)
    return False


async def _run_video_task_background(task_id: int) -> None:
    with Session(engine) as session:
        task = session.get(VideoTask, task_id)
        if task is not None:
            await VideoPipeline(session).run(task)


def _queue_video_task(session: Session, task: VideoTask, note: str | None = None) -> VideoTask:
    task.status = TaskStatus.queued
    task.error_message = None
    task.subtitle_status = "pending" if task.subtitle_enabled else "disabled"
    task.subtitle_srt_path = None
    task.subtitle_ass_path = None
    task.captioned_output_path = None
    task.updated_at = datetime.utcnow()
    if note:
        task.audit_notes = f"{task.audit_notes}\n{note}".strip() if task.audit_notes else note
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def _effective_video_output_path(task: VideoTask) -> Optional[str]:
    if task.captioned_output_path:
        path = Path(task.captioned_output_path)
        if path.exists() and path.is_file():
            return task.captioned_output_path
    return task.output_path


def _bearer_token(authorization: Optional[str]) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")
    return authorization.removeprefix("Bearer ").strip()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/auth/login")
def login(payload: LoginRequest, session: Session = Depends(get_session)) -> dict[str, object]:
    user = session.exec(select(User).where(User.username == payload.username)).first()
    if user is None or not verify_password(payload.password, user.password_hash) or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if password_hash_needs_upgrade(user.password_hash):
        user.password_hash = hash_password(payload.password)
        session.add(user)
    token = create_token()
    auth_session = AuthSession(user_id=user.id, token=token)
    session.add(auth_session)
    session.commit()
    return {"token": token, "user": _user_public(user)}


@router.get("/auth/me")
def me(user: User = Depends(current_user)) -> UserPublic:
    return _user_public(user)


@router.post("/auth/logout")
def logout(
    authorization: Optional[str] = Header(default=None),
    session: Session = Depends(get_session),
) -> dict[str, bool]:
    token = _bearer_token(authorization)
    auth_session = session.exec(select(AuthSession).where(AuthSession.token == token)).first()
    if auth_session is not None:
        session.delete(auth_session)
        session.commit()
    return {"ok": True}


@router.post("/auth/change-password")
def change_password(
    payload: ChangePasswordRequest,
    authorization: Optional[str] = Header(default=None),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict[str, bool]:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    session.add(user)
    current_token = _bearer_token(authorization)
    other_sessions = session.exec(
        select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.token != current_token)
    ).all()
    for auth_session in other_sessions:
        session.delete(auth_session)
    session.commit()
    return {"ok": True}


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin account required")
    return user


def _active_wechat_config(session: Session) -> WechatLoginConfig | None:
    return session.exec(
        select(WechatLoginConfig)
        .where(WechatLoginConfig.is_active == True)  # noqa: E712
        .order_by(WechatLoginConfig.updated_at.desc())
    ).first()


def _wechat_config_public(config: WechatLoginConfig | None) -> WechatLoginConfigPublic:
    if config is None:
        return WechatLoginConfigPublic()
    return WechatLoginConfigPublic(
        id=config.id,
        app_id=config.app_id,
        redirect_uri=config.redirect_uri,
        is_active=config.is_active,
        default_role=config.default_role,
        has_app_secret=bool(config.app_secret),
        updated_at=config.updated_at,
    )


def _wechat_request_public(item: WechatLoginRequest) -> WechatLoginRequestPublic:
    return WechatLoginRequestPublic(
        id=item.id or 0,
        openid_suffix=masked_suffix(item.openid),
        unionid_suffix=masked_suffix(item.unionid),
        nickname=item.nickname,
        avatar_url=item.avatar_url,
        status=item.status,
        requested_at=item.requested_at,
        reviewed_at=item.reviewed_at,
        reviewed_by_user_id=item.reviewed_by_user_id,
        target_user_id=item.target_user_id,
        reject_reason=item.reject_reason,
    )


def _wechat_identity_public(identity: WechatIdentity, session: Session) -> WechatIdentityPublic:
    user = session.get(User, identity.user_id)
    return WechatIdentityPublic(
        id=identity.id or 0,
        user_id=identity.user_id,
        username=user.username if user else "",
        openid_suffix=masked_suffix(identity.openid),
        unionid_suffix=masked_suffix(identity.unionid),
        nickname=identity.nickname,
        avatar_url=identity.avatar_url,
        is_active=identity.is_active,
        bound_at=identity.bound_at,
        last_login_at=identity.last_login_at,
    )


def _find_wechat_identity(session: Session, openid: str, unionid: str | None) -> WechatIdentity | None:
    identity = session.exec(select(WechatIdentity).where(WechatIdentity.openid == openid)).first()
    if identity is None and unionid:
        identity = session.exec(select(WechatIdentity).where(WechatIdentity.unionid == unionid)).first()
    return identity


def _find_wechat_request(session: Session, openid: str) -> WechatLoginRequest | None:
    return session.exec(
        select(WechatLoginRequest)
        .where(WechatLoginRequest.openid == openid)
        .order_by(WechatLoginRequest.requested_at.desc())
    ).first()


def _frontend_wechat_redirect(status: str, *, token: str = "", request_id: int | None = None) -> RedirectResponse:
    params: dict[str, str] = {"wechat_status": status}
    if token:
        params["wechat_token"] = token
    if request_id is not None:
        params["request_id"] = str(request_id)
    return RedirectResponse(url=f"/login.html?{urlencode(params)}")


def _create_auth_session_for_user(session: Session, user: User) -> str:
    token = create_token()
    session.add(AuthSession(user_id=user.id or 0, token=token))
    session.commit()
    return token


@router.get("/auth/wechat/config", response_model=WechatLoginPublicConfig)
def wechat_login_public_config(session: Session = Depends(get_session)) -> WechatLoginPublicConfig:
    config = _active_wechat_config(session)
    enabled = bool(config and config.app_id and config.app_secret and config.redirect_uri)
    return WechatLoginPublicConfig(enabled=enabled, app_id=config.app_id if enabled and config else "")


@router.get("/auth/wechat/start")
def start_wechat_login(session: Session = Depends(get_session)) -> RedirectResponse:
    config = _active_wechat_config(session)
    if config is None or not config.app_id or not config.app_secret or not config.redirect_uri:
        raise HTTPException(status_code=400, detail="微信扫码登录未配置。")
    state = create_wechat_state(config.app_secret)
    return RedirectResponse(url=build_wechat_qr_url(config, state))


@router.get("/auth/wechat/callback")
async def wechat_login_callback(
    code: str,
    state: str,
    session: Session = Depends(get_session),
) -> RedirectResponse:
    config = _active_wechat_config(session)
    if config is None or not config.app_secret:
        return _frontend_wechat_redirect("error")
    state_nonce = verify_wechat_state(state, config.app_secret)
    info = await WechatOAuthClient().fetch_user_info(config, code)
    identity = _find_wechat_identity(session, info.openid, info.unionid)
    if identity is not None:
        user = session.get(User, identity.user_id)
        if identity.is_active and user is not None and user.is_active:
            identity.nickname = info.nickname or identity.nickname
            identity.avatar_url = info.avatar_url or identity.avatar_url
            identity.last_login_at = datetime.utcnow()
            session.add(identity)
            token = _create_auth_session_for_user(session, user)
            return _frontend_wechat_redirect("success", token=token)
        return _frontend_wechat_redirect("disabled")

    existing_request = _find_wechat_request(session, info.openid)
    if existing_request is not None and existing_request.status == WechatLoginStatus.rejected:
        return _frontend_wechat_redirect("rejected", request_id=existing_request.id)
    if existing_request is None or existing_request.status != WechatLoginStatus.pending:
        existing_request = WechatLoginRequest(openid=info.openid)
    existing_request.unionid = info.unionid
    existing_request.nickname = info.nickname
    existing_request.avatar_url = info.avatar_url
    existing_request.status = WechatLoginStatus.pending
    existing_request.state_nonce = state_nonce
    session.add(existing_request)
    session.commit()
    session.refresh(existing_request)
    return _frontend_wechat_redirect("pending", request_id=existing_request.id)


@router.get("/settings/wechat-login/config", response_model=WechatLoginConfigPublic)
def get_wechat_login_config(
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> WechatLoginConfigPublic:
    return _wechat_config_public(_active_wechat_config(session))


@router.post("/settings/wechat-login/config", response_model=WechatLoginConfigPublic)
def save_wechat_login_config(
    payload: WechatLoginConfigUpdate,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> WechatLoginConfigPublic:
    config = _active_wechat_config(session) or session.exec(select(WechatLoginConfig).order_by(WechatLoginConfig.updated_at.desc())).first()
    app_id = payload.app_id.strip()
    app_secret = (payload.app_secret or "").strip()
    redirect_uri = payload.redirect_uri.strip() or "https://media.tech-ark.com/api/auth/wechat/callback"
    if not app_id:
        raise HTTPException(status_code=400, detail="请填写微信开放平台 AppID。")
    if config is None and not app_secret:
        raise HTTPException(status_code=400, detail="首次配置微信登录必须填写 AppSecret。")
    if payload.is_active:
        for item in session.exec(select(WechatLoginConfig)).all():
            item.is_active = False
            session.add(item)
    if config is None:
        config = WechatLoginConfig(
            app_id=app_id,
            app_secret=app_secret,
            redirect_uri=redirect_uri,
            is_active=payload.is_active,
            default_role=payload.default_role,
        )
    else:
        config.app_id = app_id
        if app_secret:
            config.app_secret = app_secret
        config.redirect_uri = redirect_uri
        config.is_active = payload.is_active
        config.default_role = payload.default_role
        config.updated_at = datetime.utcnow()
    session.add(config)
    session.commit()
    session.refresh(config)
    return _wechat_config_public(config)


@router.get("/settings/wechat-login/requests", response_model=list[WechatLoginRequestPublic])
def list_wechat_login_requests(
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> list[WechatLoginRequestPublic]:
    rows = session.exec(select(WechatLoginRequest).order_by(WechatLoginRequest.requested_at.desc())).all()
    status_rank = {
        WechatLoginStatus.pending: 0,
        WechatLoginStatus.approved: 1,
        WechatLoginStatus.rejected: 2,
    }
    rows = sorted(rows, key=lambda item: (status_rank.get(item.status, 9), -item.requested_at.timestamp()))
    return [_wechat_request_public(item) for item in rows]


@router.post("/settings/wechat-login/requests/{request_id}/approve", response_model=WechatLoginRequestPublic)
def approve_wechat_login_request(
    request_id: int,
    payload: WechatLoginApproveRequest,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> WechatLoginRequestPublic:
    item = session.get(WechatLoginRequest, request_id)
    if item is None:
        raise HTTPException(status_code=404, detail="微信登录申请不存在。")
    if item.status != WechatLoginStatus.pending:
        raise HTTPException(status_code=400, detail="只能批准待处理的微信登录申请。")
    if payload.mode == "bind_existing":
        if payload.user_id is None:
            raise HTTPException(status_code=400, detail="请选择要绑定的系统用户。")
        target_user = session.get(User, payload.user_id)
        if target_user is None:
            raise HTTPException(status_code=404, detail="系统用户不存在。")
    else:
        username = (payload.username or "").strip()
        if not username:
            raise HTTPException(status_code=400, detail="新建用户需要填写用户名。")
        existing_user = session.exec(select(User).where(User.username == username)).first()
        if existing_user is not None:
            raise HTTPException(status_code=400, detail="用户名已存在。")
        target_user = User(
            username=username,
            password_hash=hash_password(random_temporary_password()),
            role=payload.role,
            is_active=True,
        )
        session.add(target_user)
        session.commit()
        session.refresh(target_user)

    existing_identity = _find_wechat_identity(session, item.openid, item.unionid)
    if existing_identity is None:
        existing_identity = WechatIdentity(openid=item.openid, user_id=target_user.id or 0)
    existing_identity.user_id = target_user.id or 0
    existing_identity.unionid = item.unionid
    existing_identity.nickname = item.nickname
    existing_identity.avatar_url = item.avatar_url
    existing_identity.is_active = True
    session.add(existing_identity)

    item.status = WechatLoginStatus.approved
    item.reviewed_at = datetime.utcnow()
    item.reviewed_by_user_id = admin.id
    item.target_user_id = target_user.id
    session.add(item)
    session.commit()
    session.refresh(item)
    return _wechat_request_public(item)


@router.post("/settings/wechat-login/requests/{request_id}/reject", response_model=WechatLoginRequestPublic)
def reject_wechat_login_request(
    request_id: int,
    payload: WechatLoginRejectRequest,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> WechatLoginRequestPublic:
    item = session.get(WechatLoginRequest, request_id)
    if item is None:
        raise HTTPException(status_code=404, detail="微信登录申请不存在。")
    item.status = WechatLoginStatus.rejected
    item.reject_reason = payload.reason.strip()
    item.reviewed_at = datetime.utcnow()
    item.reviewed_by_user_id = admin.id
    session.add(item)
    session.commit()
    session.refresh(item)
    return _wechat_request_public(item)


@router.get("/settings/wechat-login/identities", response_model=list[WechatIdentityPublic])
def list_wechat_identities(
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> list[WechatIdentityPublic]:
    rows = session.exec(select(WechatIdentity).order_by(WechatIdentity.bound_at.desc())).all()
    return [_wechat_identity_public(item, session) for item in rows]


@router.post("/settings/wechat-login/identities/{identity_id}/disable", response_model=WechatIdentityPublic)
def disable_wechat_identity(
    identity_id: int,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> WechatIdentityPublic:
    identity = session.get(WechatIdentity, identity_id)
    if identity is None:
        raise HTTPException(status_code=404, detail="微信绑定不存在。")
    identity.is_active = False
    session.add(identity)
    session.commit()
    session.refresh(identity)
    return _wechat_identity_public(identity, session)

def _is_admin(user: User) -> bool:
    return user.role == UserRole.admin


def _require_write_user(user: User) -> None:
    if user.role == UserRole.reviewer:
        raise HTTPException(status_code=403, detail="Reviewer accounts cannot create or modify business data")


def _assign_owner(record: object, user: User) -> None:
    if hasattr(record, "owner_user_id") and getattr(record, "owner_user_id", None) is None:
        setattr(record, "owner_user_id", user.id)


def _owned_statement(statement, model: object, user: User):
    if _is_admin(user):
        return statement
    owner_field = getattr(model, "owner_user_id", None)
    if owner_field is None:
        return statement
    return statement.where(owner_field == user.id)


def _ensure_record_access(record: object | None, user: User, label: str, *, write: bool = False):
    if record is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    if write:
        _require_write_user(user)
    if _is_admin(user):
        return record
    owner_id = getattr(record, "owner_user_id", None)
    if owner_id != user.id:
        raise HTTPException(status_code=403, detail=f"No permission to access this {label}")
    return record


def _owned_count(session: Session, model: object, user: User) -> int:
    statement = _owned_statement(select(func.count()).select_from(model), model, user)
    return session.exec(statement).one()


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
def dashboard(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict[str, object]:
    counts = {
        "materials": _owned_count(session, Material, user),
        "topics": _owned_count(session, Topic, user),
        "scripts": _owned_count(session, Script, user),
        "digital_humans": _owned_count(session, DigitalHuman, user),
        "video_tasks": _owned_count(session, VideoTask, user),
        "publish_records": _owned_count(session, PublishRecord, user),
        "trending_videos": _owned_count(session, TrendingVideo, user),
        "transcriptions": _owned_count(session, TranscriptionTask, user),
        "video_analyses": _owned_count(session, ReferenceVideoAnalysis, user),
    }
    recent_tasks = session.exec(
        _owned_statement(select(VideoTask).order_by(VideoTask.created_at.desc()).limit(5), VideoTask, user)
    ).all()
    recent_scripts = session.exec(
        _owned_statement(select(Script).order_by(Script.created_at.desc()).limit(5), Script, user)
    ).all()
    return {"counts": counts, "recent_tasks": recent_tasks, "recent_scripts": recent_scripts}


@router.get("/settings/models", response_model=list[AIModelConfigPublic])
def list_model_configs(
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> list[AIModelConfigPublic]:
    configs = session.exec(select(AIModelConfig).order_by(AIModelConfig.created_at.desc())).all()
    return [_model_config_public(config) for config in configs]


@router.get("/settings/model-diagnostics")
def model_diagnostics(
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> dict[str, object]:
    items = []
    for purpose in MODEL_PURPOSE_ORDER:
        config = _active_model_config(session, purpose)
        items.append(_diagnose_model_config(config, purpose, session=session))
    return {
        "items": items,
        "ready_count": sum(1 for item in items if item["level"] == "ready"),
        "mock_count": sum(1 for item in items if item["level"] == "mock"),
        "blocked_count": sum(1 for item in items if item["level"] == "blocked"),
    }


@router.get("/settings/model-usage")
def model_usage_summary(
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
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
        item["purpose"]: item
        for item in (
            _diagnose_model_config(active_configs.get(purpose), purpose, session=session)
            for purpose in MODEL_PURPOSE_ORDER
        )
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
    admin: User = Depends(require_admin),
) -> dict[str, object]:
    storage_root = get_storage_root(session)
    storage_setting = session.get(SystemSetting, STORAGE_ROOT_KEY)
    default_root = Path(get_settings().storage_dir).expanduser().resolve()
    shared_root = default_root.parent
    suggested_roots = [
        {
            "label": "系统默认空间",
            "description": "适合日常生成、审核和发布前准备，所有文件按类型自动归档。",
            "path": str(default_root),
        },
        {
            "label": "成片工作区",
            "description": "适合集中保存已生成的视频任务和发布前成片。",
            "path": str(shared_root / "ai-video-output"),
        },
        {
            "label": "素材工作区",
            "description": "适合集中保存采集素材、数字人口播源和中间视频。",
            "path": str(shared_root / "ai-video-assets"),
        },
    ]
    if not any(item["path"] == str(storage_root) for item in suggested_roots):
        suggested_roots.insert(
            0,
            {
                "label": "当前自定义空间",
                "description": "沿用当前已经保存的系统位置。",
                "path": str(storage_root),
            },
        )
    for item in suggested_roots:
        item["active"] = item["path"] == str(storage_root)
    active_profile = next((item for item in suggested_roots if item["active"]), suggested_roots[0])
    storage_groups = [
        {"label": "成片库", "description": "最终审核和发布使用的视频。"},
        {"label": "分段视频库", "description": "AI 生成的分镜片段和中间视频。"},
        {"label": "数字人口播库", "description": "数字人口播视频和驱动结果。"},
        {"label": "音频库", "description": "配音、声音复刻和口播音频。"},
        {"label": "素材库", "description": "上传、采集和补传到服务器的素材。"},
    ]
    tasks = session.exec(select(VideoTask).order_by(VideoTask.created_at.desc())).all()
    videos = []
    total_size = 0
    existing_count = 0
    missing_count = 0
    external_count = 0
    placeholder_count = 0
    for task in tasks:
        effective_output_path = _effective_video_output_path(task)
        if not effective_output_path:
            continue
        output_path = effective_output_path
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
                "raw_output_path": task.output_path,
                "captioned_output_path": task.captioned_output_path,
                "subtitle_status": task.subtitle_status,
                "subtitle_style": task.subtitle_style,
                "exists": exists,
                "storage_kind": storage_kind,
                "storage_label": (
                    "云端素材库"
                    if storage_kind == "external"
                    else "占位结果"
                    if storage_kind == "placeholder"
                    else "本地成片库"
                ),
                "size_bytes": size_bytes,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
            }
        )
    return {
        "storage_root": str(storage_root),
        "storage_profile_label": active_profile["label"],
        "final_video_dir": str(storage_root / "final"),
        "segment_video_dir": str(storage_root / "seedance"),
        "digital_human_dir": str(storage_root / "digital-human"),
        "voice_dir": str(storage_root / "voice"),
        "configured_by": "后台设置" if storage_setting and storage_setting.value else "STORAGE_DIR",
        "final_video_pattern": str(storage_root / "final" / "{自动生成ID}" / "final-video.mp4"),
        "suggested_roots": suggested_roots,
        "storage_groups": storage_groups,
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
    admin: User = Depends(require_admin),
) -> dict[str, object]:
    try:
        save_storage_root(session, payload.storage_root)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"无法使用这个目录：{exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return video_storage_summary(session=session, admin=admin)


@router.get("/settings/remote-upload")
def remote_upload_settings(
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
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
    admin: User = Depends(require_admin),
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
    return remote_upload_settings(session=session, admin=admin)


@router.post("/materials/{material_id}/remote-upload", response_model=Material)
async def upload_material_to_remote(
    material_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> Material:
    material = session.get(Material, material_id)
    _ensure_record_access(material, user, "Material", write=True)
    await _publish_material_to_remote(material, session, require_config=True)
    session.refresh(material)
    return material


@router.post("/settings/models", response_model=AIModelConfigPublic)
def create_model_config(
    payload: AIModelConfigCreate,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
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
    admin: User = Depends(require_admin),
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
    admin: User = Depends(require_admin),
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
    admin: User = Depends(require_admin),
) -> dict[str, object]:
    config = session.get(AIModelConfig, model_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Model config not found")
    try:
        diagnostic = _diagnose_model_config(config, require_active=False, session=session)
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
    admin: User = Depends(require_admin),
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
    admin: User = Depends(require_admin),
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
    admin: User = Depends(require_admin),
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
    admin: User = Depends(require_admin),
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


def _url_preview(value: str | None, max_length: int = 110) -> str:
    if not value:
        return ""
    if len(value) <= max_length:
        return value
    return f"{value[:max_length]}..."


async def _probe_reference_media_url(source_url: str) -> dict[str, object]:
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {"ok": False, "content_type": "", "message": "不是有效的视频地址。"}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        ),
        "Accept": "video/mp4,video/*;q=0.9,audio/*;q=0.8,*/*;q=0.5",
        "Range": "bytes=0-1023",
    }
    try:
        async with httpx.AsyncClient(timeout=25, follow_redirects=True, headers=headers) as client:
            async with client.stream("GET", source_url) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                content_disposition = response.headers.get("content-disposition", "")
                looks_like_media = _response_looks_like_reference_media(
                    str(response.url),
                    content_type,
                    content_disposition,
                )
                return {
                    "ok": bool(looks_like_media),
                    "content_type": content_type,
                    "final_url_preview": _url_preview(str(response.url)),
                    "message": "已确认可访问视频文件。" if looks_like_media else "解析地址可访问，但不像视频或音频文件。",
                }
    except Exception as exc:
        return {"ok": False, "content_type": "", "message": f"视频地址访问失败：{exc}"}


@router.post("/settings/link-resolver/test")
async def test_link_resolver(
    payload: LinkResolverTestRequest,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> dict[str, object]:
    source_url = payload.source_url.strip()
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="请输入 http 或 https 开头的视频链接。")
    platform_name = detect_short_video_platform(source_url, payload.platform)
    credentials = _link_resolver_credentials(session, platform_name)
    resolution = await ShortVideoLinkResolver().resolve(source_url, platform_name, credentials)
    probe = await _probe_reference_media_url(resolution.media_url) if resolution.media_url else {
        "ok": False,
        "content_type": "",
        "message": "没有解析出视频文件地址。",
    }
    has_configured_resolver = bool(credentials)
    can_download = bool(resolution.media_url and probe.get("ok"))
    message = str(probe.get("message") or "")
    if not resolution.media_url and not has_configured_resolver:
        message = "当前没有启用的链接解析服务，普通分享页只能保存为参考链接。"
    elif not resolution.media_url:
        message = resolution.message or "已调用链接解析服务，但没有返回视频地址。"
    return {
        "source_url": source_url,
        "platform": platform_name,
        "resolver": resolution.resolver_name,
        "configured_resolver_count": len(credentials),
        "can_resolve": bool(resolution.media_url),
        "can_download": can_download,
        "media_url_preview": _url_preview(resolution.media_url),
        "canonical_url_preview": _url_preview(resolution.canonical_url),
        "title": resolution.title or "",
        "content_type": probe.get("content_type") or "",
        "message": message,
        "diagnostics": list(resolution.diagnostic_errors),
    }


@router.get("/integrations/status")
def integrations_status(session: Session = Depends(get_session)) -> dict[str, dict[str, object]]:
    settings = get_settings()
    trending_credentials = [
        credential
        for credential in session.exec(
            select(PlatformCredential).where(
                PlatformCredential.purpose == "trending",
                PlatformCredential.is_active == True,  # noqa: E712
            )
        ).all()
        if (credential.api_base or "").strip()
    ]
    trending_env_real_api = settings.trending_search_provider != "mock" and bool(settings.trending_search_api_base)
    trending_provider = (
        trending_credentials[0].display_name
        if trending_credentials
        else settings.trending_search_provider
    )
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
            _video_generation_fallback_ready(settings),
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
            "configured": settings.composition_provider in ("mock", "ffmpeg")
            or (settings.composition_provider == "remotion" and bool(settings.remotion_render_api_base)),
            "real_api": settings.composition_provider in {"ffmpeg", "remotion"}
            and (settings.composition_provider != "remotion" or bool(settings.remotion_render_api_base)),
            "missing": []
            if settings.composition_provider in ("mock", "ffmpeg")
            or (settings.composition_provider == "remotion" and bool(settings.remotion_render_api_base))
            else ["remotion_render_api_base" if settings.composition_provider == "remotion" else "composition_provider"],
        },
        "trending_search": {
            "provider": trending_provider,
            "configured": settings.trending_search_provider == "mock"
            or bool(settings.trending_search_api_base)
            or bool(trending_credentials),
            "real_api": trending_env_real_api or bool(trending_credentials),
            "credential_count": len(trending_credentials),
            "missing": []
            if trending_env_real_api or trending_credentials or settings.trending_search_provider == "mock"
            else ["trending_search_api_base 或平台采集配置"],
        },
        "asr": _configured_model_status(
            session,
            "asr",
            settings.asr_provider,
            settings.asr_model,
            settings.asr_provider == "mock" or bool(settings.asr_api_base),
        ),
    }


@router.post("/materials", response_model=Material)
def create_material(
    payload: MaterialCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> Material:
    _require_write_user(user)
    material = Material.model_validate(payload)
    _assign_owner(material, user)
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


def _reference_tags(platform: str, tags: str, *extra_tags: str) -> str:
    values = ["参考素材", platform.strip()]
    values.extend(item.strip() for item in tags.split(",") if item.strip())
    values.extend(item.strip() for item in extra_tags if item and item.strip())
    deduped = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return ",".join(deduped)


def _merge_reference_tags(existing_tags: str, platform: str, resolver_name: str, parse_status: str) -> str:
    retained = [
        item.strip()
        for item in existing_tags.split(",")
        if item.strip()
        and not item.strip().startswith("解析:")
        and item.strip() not in {"已下载视频", "需上传源文件", "仅保存链接"}
    ]
    return _reference_tags(platform, ",".join(retained), f"解析:{resolver_name}", parse_status)


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


def _link_resolver_credentials(session: Session, platform: str) -> list[LinkResolverCredential]:
    credentials = session.exec(
        select(PlatformCredential).where(
            PlatformCredential.purpose == "link_resolver",
            PlatformCredential.is_active == True,  # noqa: E712
        )
    ).all()
    allowed_platforms = {platform, "manual"}
    result = []
    for credential in credentials:
        credential_platform = (
            credential.platform.value if hasattr(credential.platform, "value") else str(credential.platform)
        )
        if credential_platform not in allowed_platforms:
            continue
        if not credential.api_base:
            continue
        result.append(
            LinkResolverCredential(
                platform=credential_platform,
                display_name=credential.display_name,
                api_base=credential.api_base,
                client_id=credential.client_id or "",
                client_secret=credential.client_secret or "",
                access_token=credential.access_token or "",
                notes=credential.notes or "",
            )
        )
    return result


async def _resolve_and_download_reference_media(
    source_url: str,
    platform_name: str,
    storage_dir: Path,
    session: Session,
) -> tuple[Path | None, LinkResolution | None]:
    file_path: Path | None = None
    resolution: LinkResolution | None = None
    try:
        file_path = await _download_reference_media(source_url, storage_dir)
    except HTTPException:
        raise
    except Exception:
        file_path = None
    if file_path:
        return file_path, resolution

    try:
        resolver = ShortVideoLinkResolver()
        resolution = await resolver.resolve(
            source_url,
            platform_name,
            _link_resolver_credentials(session, platform_name),
        )
        if resolution.media_url and resolution.media_url != source_url:
            file_path = await _download_reference_media(resolution.media_url, storage_dir)
    except HTTPException:
        raise
    except Exception:
        file_path = None
    return file_path, resolution


@router.post("/reference-materials/from-link", response_model=Material)
async def create_reference_material_from_link(
    payload: ReferenceMaterialLinkCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> Material:
    _require_write_user(user)
    source_url = payload.source_url.strip()
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="请输入 http 或 https 开头的视频链接。")

    platform_name = detect_short_video_platform(source_url, payload.platform)
    storage_dir = get_storage_root(session) / "materials" / uuid4().hex
    file_path: Path | None = None
    resolution: LinkResolution | None = None
    if payload.download:
        file_path, resolution = await _resolve_and_download_reference_media(
            source_url,
            platform_name,
            storage_dir,
            session,
        )

    resolver_name = resolution.resolver_name if resolution else ("direct-download" if file_path else "link-only")
    title = (payload.title or "").strip() or (resolution.title if resolution else "") or _reference_title_from_url(source_url)
    parse_status = "已下载视频" if file_path else ("需上传源文件" if payload.download else "仅保存链接")
    material = Material(
        name=title,
        kind=MaterialKind.reference,
        copyright_status=CopyrightStatus.reference_only,
        file_path=str(file_path) if file_path else None,
        source_url=source_url,
        tags=_reference_tags(platform_name, payload.tags, f"解析:{resolver_name}", parse_status),
    )
    _assign_owner(material, user)
    session.add(material)
    session.commit()
    session.refresh(material)
    return material


@router.post("/reference-materials/{material_id}/resolve-download", response_model=Material)
async def resolve_download_reference_material(
    material_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> Material:
    material = session.get(Material, material_id)
    _ensure_record_access(material, user, "Material", write=True)
    if material.kind != MaterialKind.reference or not material.source_url:
        raise HTTPException(status_code=400, detail="只有通过链接保存的参考素材可以解析下载。")
    if material.file_path and Path(material.file_path).exists():
        return material

    source_url = material.source_url.strip()
    platform_name = detect_short_video_platform(source_url, "auto")
    storage_dir = get_storage_root(session) / "materials" / uuid4().hex
    file_path, resolution = await _resolve_and_download_reference_media(
        source_url,
        platform_name,
        storage_dir,
        session,
    )
    resolver_name = resolution.resolver_name if resolution else ("direct-download" if file_path else "link-only")
    parse_status = "已下载视频" if file_path else "需上传源文件"
    if file_path:
        material.file_path = str(file_path)
    if resolution and resolution.title and material.name == _reference_title_from_url(source_url):
        material.name = resolution.title[:120]
    material.tags = _merge_reference_tags(material.tags, platform_name, resolver_name, parse_status)
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
    user: User = Depends(current_user),
) -> Material:
    _require_write_user(user)
    return await _save_uploaded_material(
        file=file,
        kind=kind,
        name=name,
        copyright_status=copyright_status,
        tags=tags,
        session=session,
        owner=user,
    )


async def _save_uploaded_material(
    file: UploadFile,
    kind: MaterialKind,
    name: Optional[str],
    session: Session,
    copyright_status: CopyrightStatus = CopyrightStatus.owned,
    tags: str = "",
    owner: User | None = None,
) -> Material:
    original_name = file.filename or "upload.bin"
    suffix = Path(original_name).suffix
    storage_dir = get_storage_root(session) / "materials" / uuid4().hex
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_path = storage_dir / f"source{suffix}"
    with file_path.open("wb") as output:
        while chunk := await file.read(1024 * 1024):
            output.write(chunk)

    material = Material(
        name=name or original_name,
        kind=kind,
        copyright_status=copyright_status,
        file_path=str(file_path),
        tags=tags,
    )
    if owner is not None:
        _assign_owner(material, owner)
    session.add(material)
    session.commit()
    session.refresh(material)
    try:
        await _publish_material_to_remote(material, session)
        session.refresh(material)
    except Exception:
        pass
    return material


def _optional_form_id(value: Optional[str | int], field_label: str) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field_label}必须是有效素材 ID。") from exc


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
            try:
                response = await client.post(upload_url, headers=headers, files=files, data=data)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                message = str(exc) or exc.__class__.__name__
                raise HTTPException(status_code=502, detail=f"素材服务器上传失败：{message}") from exc
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
def list_materials(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[Material]:
    statement = _owned_statement(select(Material).order_by(Material.created_at.desc()), Material, user)
    return list(session.exec(statement).all())


@router.get("/materials/{material_id}/preview")
def preview_material(
    material_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> FileResponse:
    material = session.get(Material, material_id)
    _ensure_record_access(material, user, "Material")
    if not material.file_path:
        raise HTTPException(status_code=404, detail="Material preview not found")
    path = Path(material.file_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Material file not found")
    return FileResponse(path)


@router.delete("/materials/{material_id}")
def delete_material(
    material_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict[str, object]:
    material = session.get(Material, material_id)
    _ensure_record_access(material, user, "Material", write=True)

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
    _require_write_user(user)
    material = session.get(Material, payload.material_id)
    _ensure_record_access(material, user, "Material")
    task = TranscriptionTask(
        material_id=payload.material_id,
        language=payload.language,
        provider=get_settings().asr_provider,
        status=TaskStatus.queued,
    )
    _assign_owner(task, user)
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
    _ensure_record_access(task, user, "Transcription task", write=True)
    material = session.get(Material, task.material_id)
    _ensure_record_access(material, user, "Material")
    active_model = _smart_model_config(session, "asr", "transcription")
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
            provider=active_model.provider if active_model else settings.asr_provider,
            model_name=active_model.model_name if active_model else settings.asr_model,
            completion_tokens=estimate_text_tokens(result.transcript, result.summary, result.hook_analysis),
        )
    except Exception as exc:
        task.status = TaskStatus.failed
        task.error_message = str(exc)
        record_model_usage(
            session=session,
            purpose="asr",
            model_config=active_model,
            provider=active_model.provider if active_model else settings.asr_provider,
            model_name=active_model.model_name if active_model else settings.asr_model,
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
    statement = _owned_statement(
        select(TranscriptionTask).order_by(TranscriptionTask.created_at.desc()),
        TranscriptionTask,
        user,
    )
    return list(session.exec(statement).all())


@router.post("/transcriptions/{task_id}/create-topic", response_model=Topic)
def create_topic_from_transcription(
    task_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> Topic:
    task = session.get(TranscriptionTask, task_id)
    _ensure_record_access(task, user, "Transcription task", write=True)
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
    _assign_owner(topic, user)
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
    _ensure_record_access(task, user, "Transcription task", write=True)
    if not task.transcript:
        raise HTTPException(status_code=400, detail="Transcription has no transcript")
    topic = (
        "基于参考视频结构，生成原创公司短视频脚本。"
        f"参考摘要：{task.summary}。"
        f"开头钩子分析：{task.hook_analysis}。"
        "要求只借鉴结构和选题，不复制原文。"
    )
    active_model = _smart_model_config(session, "script", "script_generation")
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
    _assign_owner(script, user)
    session.add(script)
    record_generated_model_usage(
        session,
        "script",
        generated,
        active_model,
        provider=active_model.provider if active_model else get_settings().llm_provider,
        model_name=active_model.model_name if active_model else get_settings().llm_model,
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
    _require_write_user(user)
    material = session.get(Material, payload.material_id)
    _ensure_record_access(material, user, "Material")
    if material.kind not in (MaterialKind.avatar_source, MaterialKind.video, MaterialKind.reference):
        raise HTTPException(status_code=400, detail="深度视频拆解需要选择视频或参考素材。")
    task = ReferenceVideoAnalysis(
        material_id=payload.material_id,
        provider=payload.provider,
        language=payload.language,
        status=TaskStatus.queued,
    )
    _assign_owner(task, user)
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
    _ensure_record_access(task, user, "Reference video analysis")
    material = session.get(Material, task.material_id)
    _ensure_record_access(material, user, "Material")

    active_model = _smart_model_config(session, "video_understanding", "reference_analysis")
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
    statement = _owned_statement(
        select(ReferenceVideoAnalysis).order_by(ReferenceVideoAnalysis.created_at.desc()),
        ReferenceVideoAnalysis,
        user,
    )
    return list(session.exec(statement).all())


@router.post("/video-analyses/{analysis_id}/approve", response_model=ReferenceVideoAnalysis)
def approve_reference_video_analysis(
    analysis_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> ReferenceVideoAnalysis:
    task = session.get(ReferenceVideoAnalysis, analysis_id)
    _ensure_record_access(task, user, "Reference video analysis")
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
    _ensure_record_access(task, user, "Reference video analysis", write=True)
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
    user: User = Depends(current_user),
) -> FileResponse:
    task = session.get(ReferenceVideoAnalysis, analysis_id)
    _ensure_record_access(task, user, "Reference video analysis")
    if not task.contact_sheet_path:
        raise HTTPException(status_code=404, detail="Contact sheet not found")
    path = Path(task.contact_sheet_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Contact sheet file not found")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/video-analyses/{analysis_id}/dense-contact-sheet")
def reference_video_analysis_dense_contact_sheet(
    analysis_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> FileResponse:
    task = session.get(ReferenceVideoAnalysis, analysis_id)
    _ensure_record_access(task, user, "Reference video analysis")
    if not task.dense_contact_sheet_path:
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
    _ensure_record_access(task, user, "Reference video analysis", write=True)
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
    active_model = _smart_model_config(session, "script", "script_generation")
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
    script = _create_script_record(session, payload, generated, active_model, owner=user)
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
def create_topic(
    payload: TopicCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> Topic:
    _require_write_user(user)
    if payload.reference_material_id is not None:
        material = session.get(Material, payload.reference_material_id)
        _ensure_record_access(material, user, "Material")
    topic = Topic.model_validate(payload)
    _assign_owner(topic, user)
    session.add(topic)
    session.commit()
    session.refresh(topic)
    return topic


@router.get("/topics", response_model=list[Topic])
def list_topics(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[Topic]:
    statement = _owned_statement(select(Topic).order_by(Topic.created_at.desc()), Topic, user)
    return list(session.exec(statement).all())


def _create_script_record(
    session: Session,
    payload: ScriptGenerateRequest,
    generated,
    model_config: Optional[AIModelConfig] = None,
    owner: User | None = None,
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
    if owner is not None:
        _assign_owner(script, owner)
    session.add(script)
    record_generated_model_usage(
        session,
        "script",
        generated,
        model_config,
        provider=model_config.provider if model_config else get_settings().llm_provider,
        model_name=model_config.model_name if model_config else get_settings().llm_model,
    )
    session.commit()
    session.refresh(script)
    return script


@router.post("/scripts/generate", response_model=Script)
async def generate_script(
    payload: ScriptGenerateRequest,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> Script:
    _require_write_user(user)
    if payload.topic_id is not None:
        topic_record = session.get(Topic, payload.topic_id)
        _ensure_record_access(topic_record, user, "Topic")
    active_model = _smart_model_config(session, "script", "script_generation")
    generated = await ScriptGenerator(active_model).generate(
        topic=payload.topic,
        brand_voice=payload.brand_voice,
        duration_seconds=payload.duration_seconds,
        target_platform=payload.target_platform,
        output_language=payload.output_language,
    )
    return _create_script_record(session, payload, generated, active_model, owner=user)


@router.post("/scripts/batch-generate", response_model=list[Script])
async def batch_generate_scripts(
    payload: ScriptBatchGenerateRequest,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[Script]:
    _require_write_user(user)
    if payload.topic_id is not None:
        topic_record = session.get(Topic, payload.topic_id)
        _ensure_record_access(topic_record, user, "Topic")
    active_model = _smart_model_config(
        session,
        "script",
        "long_script" if payload.duration_seconds >= 120 else "script_generation",
    )
    generator = ScriptGenerator(active_model)
    topics = [item.strip() for item in payload.topics if item.strip()] or [payload.topic.strip() for _ in range(payload.count)]
    scripts: list[Script] = []
    for index, topic in enumerate(topics[: payload.count]):
        variation_instruction = (
            f"候选方案 {index + 1}/{payload.count}：请只在标题角度、开头钩子、案例侧重点和分镜节奏上做差异化。"
            "这是内部策划要求，不得出现在最终脚本、口播稿、分镜或屏幕文字里。"
        )
        generated = await generator.generate(
            topic=topic,
            brand_voice=payload.brand_voice,
            duration_seconds=payload.duration_seconds,
            target_platform=payload.target_platform,
            output_language=payload.output_language,
            variation_instruction=variation_instruction,
        )
        item_payload = ScriptGenerateRequest(
            topic_id=payload.topic_id,
            topic=topic,
            brand_voice=payload.brand_voice,
            duration_seconds=payload.duration_seconds,
            target_platform=payload.target_platform,
            output_language=payload.output_language,
        )
        script = _create_script_record(session, item_payload, generated, active_model, owner=user)
        scripts.append(script)
    return scripts


@router.get("/scripts", response_model=list[Script])
def list_scripts(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[Script]:
    statement = _owned_statement(select(Script).order_by(Script.created_at.desc()), Script, user)
    return list(session.exec(statement).all())


@router.patch("/scripts/{script_id}", response_model=Script)
def update_script(
    script_id: int,
    payload: ScriptUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> Script:
    script = session.get(Script, script_id)
    _ensure_record_access(script, user, "Script", write=True)
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
    subtitle_enabled: bool = True,
    subtitle_style: str = "auto",
    status: TaskStatus = TaskStatus.queued,
    audit_notes: str = "",
    owner: User | None = None,
) -> VideoTask:
    if production_mode not in PRODUCTION_MODES:
        raise HTTPException(status_code=400, detail="Unknown production mode")
    segment_count = _estimated_video_segment_count(script.duration_seconds)
    platform_name = target_platform or script.target_platform or "douyin"
    profile = resolve_export_profile(export_profile, platform_name)
    task = VideoTask(
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
        subtitle_enabled=subtitle_enabled,
        subtitle_style=subtitle_style or "auto",
        subtitle_status="pending" if subtitle_enabled else "disabled",
        audit_notes=audit_notes,
    )
    if owner is not None:
        _assign_owner(task, owner)
    return task


def _prepare_material_mix_segments(session: Session, task: VideoTask, script: Script) -> VideoTask:
    if task.production_mode != "material_mix":
        return task
    pipeline = VideoPipeline(session)
    segment_specs = pipeline.media.segment_plan(
        script.seedance_prompt,
        script.storyboard,
        script.duration_seconds,
        script.storyboard_plan,
    )
    segments = pipeline._reset_segments(task, segment_specs)
    task.segment_count = len(segments)
    task.completed_segments = 0
    note = "素材库混剪方案已按分镜生成，可在任务详情里人工修改每段素材；未绑定素材的段落会由 Seedance 补镜头。"
    task.audit_notes = f"{task.audit_notes}\n{note}".strip() if task.audit_notes else note
    task.updated_at = datetime.utcnow()
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def _validate_video_task_inputs(
    session: Session,
    production_mode: str,
    digital_human_id: Optional[int],
    user: User | None = None,
) -> None:
    if production_mode not in PRODUCTION_MODES:
        raise HTTPException(status_code=400, detail="Unknown production mode")
    if digital_human_id is None:
        if production_mode in {"digital_human", "talking_head_template"}:
            raise HTTPException(status_code=400, detail="数字人口播需要选择数字人，并上传头像或口播源视频。")
        return
    human = session.get(DigitalHuman, digital_human_id)
    if user is not None:
        _ensure_record_access(human, user, "Digital human")
    elif human is None:
        raise HTTPException(status_code=404, detail="Digital human not found")
    if (
        production_mode in {"digital_human", "talking_head_template"}
        and human.portrait_material_id is None
        and human.source_video_material_id is None
    ):
        raise HTTPException(status_code=400, detail="数字人口播需要先上传该数字人的头像或口播源视频。")
    if (
        production_mode in {"digital_human", "talking_head_template"}
        and _digital_human_model_needs_source_video(session)
        and human.source_video_material_id is None
    ):
        raise HTTPException(status_code=400, detail="当前 VideoRetalk 数字人模型需要先上传该数字人的口播源视频。")
    if production_mode in {"digital_human", "talking_head_template"} and not _digital_human_service_ready(session):
        raise HTTPException(status_code=400, detail="数字人口播需要先在系统设置里配置真实数字人驱动接口。")


def _digital_human_model_needs_source_video(session: Session) -> bool:
    model_config = _smart_model_config(session, "digital_human", "talking_head_template")
    settings = get_settings()
    provider = model_config.provider if model_config else settings.digital_human_provider
    model_name = model_config.model_name if model_config else settings.digital_human_provider
    value = f"{provider} {model_name}".lower()
    return "videoretalk" in value or "jimeng" in value


def _digital_human_service_ready(session: Session) -> bool:
    model_config = _smart_model_config(session, "digital_human", "talking_head_template")
    settings = get_settings()
    if model_config:
        if _is_volcengine_jimeng_provider(model_config.provider):
            return is_model_config_ready(model_config) and _volcengine_jimeng_credential_ready(session)
        return is_model_config_ready(model_config)
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
    _require_write_user(user)
    script = session.get(Script, script_id)
    _ensure_record_access(script, user, "Script")
    _validate_video_task_inputs(session, payload.production_mode, payload.digital_human_id, user=user)
    task = _build_video_task(
        script,
        payload.digital_human_id,
        production_mode=payload.production_mode,
        target_platform=payload.target_platform,
        export_profile=payload.export_profile,
        subtitle_enabled=payload.subtitle_enabled,
        subtitle_style=payload.subtitle_style,
        owner=user,
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    task = _prepare_material_mix_segments(session, task, script)
    return task


@router.post("/scripts/{script_id}/auto-video-task", response_model=VideoTask)
async def approve_script_and_run_video_task(
    script_id: int,
    payload: ScriptVideoTaskCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> VideoTask:
    _require_write_user(user)
    script = session.get(Script, script_id)
    _ensure_record_access(script, user, "Script")
    _validate_video_task_inputs(session, payload.production_mode, payload.digital_human_id, user=user)
    task = _build_video_task(
        script,
        payload.digital_human_id,
        production_mode=payload.production_mode,
        target_platform=payload.target_platform,
        export_profile=payload.export_profile,
        subtitle_enabled=payload.subtitle_enabled,
        subtitle_style=payload.subtitle_style,
        status=TaskStatus.queued,
        audit_notes=f"脚本已审核通过，系统已按「{payload.production_mode}」创建视频任务并进入生成队列。",
        owner=user,
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    background_tasks.add_task(_run_video_task_background, task.id)
    return task


@router.post("/scripts/{script_id}/voice-preview")
async def generate_script_voice_preview(
    script_id: int,
    payload: ScriptVideoTaskCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> FileResponse:
    script = session.get(Script, script_id)
    _ensure_record_access(script, user, "Script")
    human = session.get(DigitalHuman, payload.digital_human_id) if payload.digital_human_id else None
    if human is not None:
        _ensure_record_access(human, user, "Digital human")
    voice = human.default_voice if human and human.default_voice else None
    tts_model = _smart_model_config(session, "tts", "voice_preview")
    media = MediaGenerationClient(tts_model_config=tts_model, storage_dir=get_storage_root(session))
    try:
        audio_path = await media.synthesize_voice(script.voiceover, voice)
        record_model_usage(
            session,
            "tts",
            tts_model,
            provider=(tts_model.provider if tts_model else get_settings().tts_provider),
            model_name=(tts_model.model_name if tts_model else get_settings().tts_voice),
            prompt_tokens=estimate_text_tokens(script.voiceover),
        )
        session.commit()
    except Exception as exc:
        record_model_usage(
            session,
            "tts",
            tts_model,
            provider=(tts_model.provider if tts_model else get_settings().tts_provider),
            model_name=(tts_model.model_name if tts_model else get_settings().tts_voice),
            prompt_tokens=estimate_text_tokens(script.voiceover),
            status="failed",
        )
        session.commit()
        raise HTTPException(status_code=400, detail=f"口播试听生成失败：{exc}") from exc
    media_type = mimetypes.guess_type(audio_path)[0] or "audio/wav"
    return FileResponse(audio_path, media_type=media_type, filename=f"script-{script_id}-voice-preview.wav")


@router.post("/digital-humans", response_model=DigitalHuman)
def create_digital_human(
    payload: DigitalHumanCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> DigitalHuman:
    _require_write_user(user)
    if payload.portrait_material_id is not None:
        portrait_material = session.get(Material, payload.portrait_material_id)
        _ensure_record_access(portrait_material, user, "Portrait material")
    if payload.source_video_material_id is not None:
        source_material = session.get(Material, payload.source_video_material_id)
        _ensure_record_access(source_material, user, "Source video material")
        if source_material.kind not in (MaterialKind.avatar_source, MaterialKind.video):
            raise HTTPException(status_code=400, detail="Source video material must be a video source")
    human = DigitalHuman.model_validate(payload)
    _assign_owner(human, user)
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
    portrait_material_id: Optional[str] = Form(default=None),
    source_video_material_id: Optional[str] = Form(default=None),
    portrait_file: Optional[UploadFile] = File(default=None),
    source_video_file: Optional[UploadFile] = File(default=None),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> DigitalHuman:
    _require_write_user(user)
    portrait_id = _optional_form_id(portrait_material_id, "头像素材 ID")
    source_video_id = _optional_form_id(source_video_material_id, "口播源视频素材 ID")
    if portrait_id is not None:
        portrait = session.get(Material, portrait_id)
        _ensure_record_access(portrait, user, "Portrait material")
    if source_video_id is not None:
        source_video = session.get(Material, source_video_id)
        _ensure_record_access(source_video, user, "Source video material")

    if portrait_file is not None and portrait_file.filename:
        portrait = await _save_uploaded_material(
            file=portrait_file,
            kind=MaterialKind.portrait,
            name=f"{name}头像",
            tags="digital-human,portrait",
            session=session,
            owner=user,
        )
        portrait_id = portrait.id

    if source_video_file is not None and source_video_file.filename:
        source_video = await _save_uploaded_material(
            file=source_video_file,
            kind=MaterialKind.avatar_source,
            name=f"{name}口播源视频",
            tags="digital-human,voice-source",
            session=session,
            owner=user,
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
    return create_digital_human(payload, session, user)


@router.get("/digital-humans", response_model=list[DigitalHuman])
def list_digital_humans(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[DigitalHuman]:
    statement = _owned_statement(select(DigitalHuman).order_by(DigitalHuman.created_at.desc()), DigitalHuman, user)
    return list(session.exec(statement).all())


@router.post("/digital-humans/{human_id}/volcengine-auth/session")
async def create_volcengine_portrait_auth_session(
    human_id: int,
    payload: VolcenginePortraitAuthSessionCreate,
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict[str, object]:
    human = session.get(DigitalHuman, human_id)
    _ensure_record_access(human, user, "Digital human", write=True)
    callback_url = (payload.callback_url or str(request.url_for("volcengine_portrait_auth_callback"))).strip()
    callback_url = _append_query_param(callback_url, "human_id", str(human_id))
    request_payload = {
        "CallbackURL": callback_url,
        "ProjectName": "default",
    }
    if payload.subject_name:
        request_payload["SubjectName"] = payload.subject_name.strip()
    if payload.remark:
        request_payload["Remark"] = payload.remark
    data = await _volcengine_portrait_request(session, "CreateVisualValidateSession", request_payload)
    result = _volcengine_result_payload(data)
    auth_url = _nested_value(
        result,
        {
            "H5Link",
            "h5Link",
            "h5_link",
            "H5Url",
            "H5URL",
            "h5Url",
            "h5_url",
            "AuthURL",
            "AuthUrl",
            "authUrl",
            "Url",
            "url",
            "ValidateUrl",
        },
    )
    byted_token = _nested_value(result, {"BytedToken", "bytedToken", "byted_token", "Token", "token"})
    if not auth_url or not byted_token:
        raise HTTPException(status_code=400, detail=f"火山未返回 H5 认证链接或 BytedToken：{result}")
    human.volcengine_auth_status = "pending"
    human.volcengine_auth_url = auth_url
    human.volcengine_byted_token = byted_token
    human.volcengine_auth_result_code = None
    human.volcengine_auth_payload = json.dumps(result, ensure_ascii=False)[:4000]
    session.add(human)
    session.commit()
    session.refresh(human)
    return _human_portrait_auth_state(human)


@router.post("/digital-humans/{human_id}/volcengine-auth/sync")
async def sync_volcengine_portrait_auth_session(
    human_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict[str, object]:
    human = session.get(DigitalHuman, human_id)
    _ensure_record_access(human, user, "Digital human", write=True)
    return await _sync_volcengine_portrait_auth_result(session, human)


@router.get("/digital-humans/{human_id}/volcengine-auth/status")
def get_volcengine_portrait_auth_status(
    human_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict[str, object]:
    human = session.get(DigitalHuman, human_id)
    _ensure_record_access(human, user, "Digital human")
    return _human_portrait_auth_state(human)


@router.get("/volcengine/portrait-auth/callback", name="volcengine_portrait_auth_callback")
async def volcengine_portrait_auth_callback(
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    params = dict(request.query_params)
    human_id = int(str(params.get("human_id") or "0") or 0)
    human = session.get(DigitalHuman, human_id) if human_id else None
    result_code = str(params.get("resultCode") or params.get("ResultCode") or "")
    detail = "未找到对应数字人，请回到系统详情页手动同步。"
    status = "failed"
    if human is not None:
        token = str(params.get("BytedToken") or params.get("bytedToken") or params.get("byted_token") or "")
        if token and human.volcengine_byted_token and token != human.volcengine_byted_token:
            detail = "回调 Token 与数字人记录不一致，请回到系统详情页重新创建认证链接。"
        else:
            human.volcengine_auth_result_code = result_code or human.volcengine_auth_result_code
            human.volcengine_auth_payload = json.dumps(params, ensure_ascii=False)[:4000]
            human.volcengine_auth_status = "callback_received" if result_code == "10000" else "failed"
            session.add(human)
            session.commit()
            session.refresh(human)
            if result_code == "10000":
                try:
                    state = await _sync_volcengine_portrait_auth_result(session, human)
                    status = str(state.get("status") or "active")
                    detail = "认证已完成，系统已同步真人 Asset Group。"
                except HTTPException as exc:
                    status = "callback_received"
                    detail = f"认证已完成，但自动同步 Asset Group 失败：{exc.detail}"
            else:
                detail = f"真人认证未通过或已取消，resultCode={result_code or '-'}。"
    html = f"""
    <!doctype html>
    <html lang="zh-CN">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>火山真人认证结果</title>
        <style>
          body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f8fafc; color: #111827; }}
          main {{ max-width: 620px; margin: 12vh auto; padding: 28px; background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }}
          h1 {{ margin: 0 0 12px; font-size: 24px; }}
          p {{ line-height: 1.7; color: #4b5563; }}
          a {{ color: #2563eb; font-weight: 700; }}
        </style>
      </head>
      <body>
        <main>
          <h1>火山真人认证结果</h1>
          <p>状态：{escape(status)}</p>
          <p>{escape(detail)}</p>
          <p><a href="/">返回系统</a></p>
        </main>
      </body>
    </html>
    """
    return HTMLResponse(html)


@router.delete("/digital-humans/{human_id}")
def delete_digital_human(
    human_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict[str, object]:
    human = session.get(DigitalHuman, human_id)
    _ensure_record_access(human, user, "Digital human", write=True)
    tasks = session.exec(select(VideoTask).where(VideoTask.digital_human_id == human_id)).all()
    for task in tasks:
        task.digital_human_id = None
        session.add(task)
    session.delete(human)
    session.commit()
    return {"deleted": True, "id": human_id}


@router.post("/video-tasks", response_model=VideoTask)
def create_video_task(
    payload: VideoTaskCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> VideoTask:
    _require_write_user(user)
    script = session.get(Script, payload.script_id)
    _ensure_record_access(script, user, "Script")
    _validate_video_task_inputs(session, payload.production_mode, payload.digital_human_id, user=user)
    task = _build_video_task(
        script,
        payload.digital_human_id,
        production_mode=payload.production_mode,
        target_platform=payload.target_platform,
        export_profile=payload.export_profile,
        subtitle_enabled=payload.subtitle_enabled,
        subtitle_style=payload.subtitle_style,
        owner=user,
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@router.post("/video-tasks/batch-create", response_model=list[VideoTask])
def batch_create_video_tasks(
    payload: VideoTaskBatchCreateRequest,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[VideoTask]:
    _require_write_user(user)
    _validate_video_task_inputs(session, payload.production_mode, payload.digital_human_id, user=user)
    tasks: list[VideoTask] = []
    for script_id in payload.script_ids:
        script = session.get(Script, script_id)
        _ensure_record_access(script, user, f"Script {script_id}")
        task = _build_video_task(
            script,
            payload.digital_human_id,
            production_mode=payload.production_mode,
            target_platform=payload.target_platform,
            export_profile=payload.export_profile,
            subtitle_enabled=payload.subtitle_enabled,
            subtitle_style=payload.subtitle_style,
            owner=user,
        )
        session.add(task)
        tasks.append(task)
    session.commit()
    for task in tasks:
        session.refresh(task)
        script = session.get(Script, task.script_id)
        if script is not None:
            _prepare_material_mix_segments(session, task, script)
    return tasks


@router.post("/video-tasks/batch-run", response_model=list[VideoTask])
async def batch_run_video_tasks(
    payload: VideoTaskBatchRunRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[VideoTask]:
    results: list[VideoTask] = []
    for task_id in payload.task_ids:
        task = session.get(VideoTask, task_id)
        _ensure_record_access(task, user, f"Video task {task_id}", write=True)
        _ensure_video_task_can_run(task)
        queued_task = _queue_video_task(session, task, "任务已进入后台生成队列。")
        background_tasks.add_task(_run_video_task_background, queued_task.id)
        results.append(queued_task)
    return results


@router.post("/video-tasks/{task_id}/run", response_model=VideoTask)
async def run_video_task(
    task_id: int,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> VideoTask:
    task = session.get(VideoTask, task_id)
    _ensure_record_access(task, user, "Video task", write=True)
    _ensure_video_task_can_run(task)
    queued_task = _queue_video_task(session, task, "任务已进入后台生成队列。")
    background_tasks.add_task(_run_video_task_background, queued_task.id)
    return queued_task


@router.post("/video-tasks/{task_id}/approve", response_model=VideoTask)
def approve_video_task(
    task_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> VideoTask:
    task = session.get(VideoTask, task_id)
    _ensure_record_access(task, user, "Video task")
    if task.status != TaskStatus.needs_review or not task.output_path:
        raise HTTPException(status_code=400, detail="Only generated videos waiting for review can be approved")
    task.status = TaskStatus.approved
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@router.get("/video-tasks", response_model=list[VideoTask])
def list_video_tasks(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[VideoTask]:
    statement = _owned_statement(select(VideoTask).order_by(VideoTask.created_at.desc()), VideoTask, user)
    return list(session.exec(statement).all())


@router.get("/video-tasks/{task_id}/segments", response_model=list[VideoSegment])
def list_video_task_segments(
    task_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[VideoSegment]:
    task = session.get(VideoTask, task_id)
    _ensure_record_access(task, user, "Video task")
    return list(
        session.exec(
            select(VideoSegment)
            .where(VideoSegment.video_task_id == task_id)
            .order_by(VideoSegment.segment_index.asc())
        ).all()
    )


@router.patch("/video-tasks/{task_id}/segments/{segment_id}/material", response_model=VideoSegment)
def update_video_segment_material(
    task_id: int,
    segment_id: int,
    payload: VideoSegmentMaterialUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> VideoSegment:
    task = session.get(VideoTask, task_id)
    _ensure_record_access(task, user, "Video task", write=True)
    if task.status == TaskStatus.running:
        raise HTTPException(status_code=409, detail="生成中的任务不能修改素材方案。")
    segment = session.get(VideoSegment, segment_id)
    if segment is None or segment.video_task_id != task_id:
        raise HTTPException(status_code=404, detail="Video segment not found")
    if payload.material_id is not None:
        material = session.get(Material, payload.material_id)
        _ensure_record_access(material, user, "Material")
        allowed_kinds = {MaterialKind.video, MaterialKind.image, MaterialKind.product, MaterialKind.portrait}
        if task.production_mode == "seedance_scene":
            allowed_kinds.update({MaterialKind.reference, MaterialKind.avatar_source})
        if material.kind not in allowed_kinds:
            raise HTTPException(status_code=400, detail="请选择素材库里的图片、产品图、视频或参考素材。")
        if material.copyright_status == CopyrightStatus.blocked:
            raise HTTPException(status_code=400, detail="这个素材未获得成片使用授权。")
        if task.production_mode == "material_mix" and material.copyright_status == CopyrightStatus.reference_only:
            raise HTTPException(status_code=400, detail="参考素材不能直接混剪进成片，请改用 Seedance 参考生成。")
        segment.material_id = material.id
        if material.copyright_status == CopyrightStatus.reference_only:
            segment.material_match_notes = f"人工指定参考素材 #{material.id}：{material.name}，仅作为 Seedance 参考输入。"
        else:
            segment.material_match_notes = f"人工指定素材 #{material.id}：{material.name}"
    else:
        segment.material_id = None
        segment.material_match_notes = "人工取消素材，生成时将由 Seedance 补镜头。"
    segment.output_path = None
    segment.error_message = None
    segment.status = TaskStatus.queued
    segment.updated_at = datetime.utcnow()
    task.output_path = None
    task.subtitle_srt_path = None
    task.subtitle_ass_path = None
    task.captioned_output_path = None
    task.subtitle_status = "pending" if task.subtitle_enabled else "disabled"
    task.completed_segments = 0
    if task.status in {TaskStatus.needs_review, TaskStatus.approved, TaskStatus.failed}:
        task.status = TaskStatus.queued
    task.updated_at = datetime.utcnow()
    session.add(segment)
    session.add(task)
    session.commit()
    session.refresh(segment)
    return segment


@router.get("/video-tasks/{task_id}/output")
def preview_video_task_output(
    task_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> FileResponse:
    task = session.get(VideoTask, task_id)
    _ensure_record_access(task, user, "Video task")
    output_path = _effective_video_output_path(task) if task else None
    if not output_path:
        raise HTTPException(status_code=404, detail="Video output not found")
    path = Path(output_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Video file not found")
    return FileResponse(path, media_type="video/mp4")


@router.delete("/video-tasks/{task_id}/output")
def delete_video_task_output(
    task_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict[str, object]:
    task = session.get(VideoTask, task_id)
    _ensure_record_access(task, user, "Video task", write=True)
    if task.status == TaskStatus.running:
        raise HTTPException(status_code=409, detail="Cannot delete output while video is generating")
    if not _effective_video_output_path(task):
        raise HTTPException(status_code=400, detail="Video task has no generated output")
    _delete_local_file(task.output_path)
    _delete_local_file(task.captioned_output_path)
    _delete_local_file(task.subtitle_srt_path)
    _delete_local_file(task.subtitle_ass_path)
    segments = session.exec(select(VideoSegment).where(VideoSegment.video_task_id == task_id)).all()
    for segment in segments:
        _delete_local_file(segment.output_path)
        segment.output_path = None
        segment.status = TaskStatus.queued
        segment.error_message = None
        segment.updated_at = datetime.utcnow()
        session.add(segment)
    task.output_path = None
    task.subtitle_srt_path = None
    task.subtitle_ass_path = None
    task.captioned_output_path = None
    task.subtitle_status = "pending" if task.subtitle_enabled else "disabled"
    task.status = TaskStatus.queued
    task.completed_segments = 0
    task.updated_at = datetime.utcnow()
    session.add(task)
    session.commit()
    return {"deleted": True, "id": task_id, "target": "output"}


@router.delete("/video-tasks/{task_id}")
def delete_video_task(
    task_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict[str, object]:
    task = session.get(VideoTask, task_id)
    _ensure_record_access(task, user, "Video task", write=True)
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
    _delete_local_file(task.captioned_output_path)
    _delete_local_file(task.subtitle_srt_path)
    _delete_local_file(task.subtitle_ass_path)
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
    _ensure_record_access(task, user, "Video task")
    if task.status != TaskStatus.approved:
        raise HTTPException(status_code=400, detail="Video task must be approved before publishing")
    if not _effective_video_output_path(task):
        raise HTTPException(status_code=400, detail="Video task has no generated output")
    script = session.get(Script, task.script_id)
    account = _resolve_publish_account(session, payload.platform_account_id, payload.platform, user=user)
    title = payload.title or _publish_title_from_script(script)
    _ensure_publish_ready(session, task, script, title, account)
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
    _assign_owner(record, user)
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


def _publish_validation_blockers(
    session: Session,
    task: VideoTask,
    script: Optional[Script],
    title: str | None,
    account: Optional[PlatformAccount] = None,
) -> list[str]:
    blockers: list[str] = []
    if task.status != TaskStatus.approved:
        blockers.append("视频任务必须先审核通过")
    output_path_value = _effective_video_output_path(task)
    if not output_path_value:
        blockers.append("视频任务还没有成片文件")
    elif output_path_value.startswith("mock://"):
        blockers.append("当前成片仍是占位结果，不能发布")
    elif not output_path_value.startswith("http"):
        output_path = Path(output_path_value)
        if not output_path.exists() or not output_path.is_file():
            blockers.append("本地成片文件不存在")
    if not (title or "").strip():
        blockers.append("发布标题不能为空")
    if account is not None and account.status != "active":
        blockers.append("发布账号不是启用状态")

    if script is not None:
        notes = (script.compliance_notes or "").lower()
        blocked_markers = ("不可发布", "禁止发布", "侵权", "未授权", "blocked", "do not publish")
        if any(marker in notes for marker in blocked_markers):
            blockers.append("脚本合规备注包含不可发布风险")

    if task.digital_human_id:
        human = session.get(DigitalHuman, task.digital_human_id)
        for material_id, label in (
            (human.portrait_material_id if human else None, "数字人头像"),
            (human.source_video_material_id if human else None, "数字人口播源视频"),
        ):
            if material_id is None:
                continue
            material = session.get(Material, material_id)
            if material is None:
                blockers.append(f"{label}素材不存在")
            elif material.copyright_status in {CopyrightStatus.blocked, CopyrightStatus.reference_only}:
                blockers.append(f"{label}素材未获得发布授权")
    return blockers


def _ensure_publish_ready(
    session: Session,
    task: VideoTask,
    script: Optional[Script],
    title: str | None,
    account: Optional[PlatformAccount] = None,
) -> None:
    blockers = _publish_validation_blockers(session, task, script, title, account)
    if blockers:
        raise HTTPException(status_code=400, detail="发布前校验未通过：" + "；".join(blockers))


def _parse_optional_datetime(value: Optional[str]):
    if not value:
        return None
    return datetime.fromisoformat(value)


def _resolve_publish_account(
    session: Session,
    account_id: Optional[int],
    platform: Optional[str],
    user: User | None = None,
) -> Optional[PlatformAccount]:
    if account_id is not None:
        account = session.get(PlatformAccount, account_id)
        if user is not None:
            _ensure_record_access(account, user, "Platform account")
        elif account is None:
            raise HTTPException(status_code=404, detail="Platform account not found")
        return account
    if platform is None:
        return None
    statement = select(PlatformAccount).where(
            PlatformAccount.platform == platform,
            PlatformAccount.is_default == True,
    )
    if user is not None:
        statement = _owned_statement(statement, PlatformAccount, user)
    return session.exec(statement).first()


def _clear_default_account(session: Session, platform: str, user: User | None = None) -> None:
    statement = select(PlatformAccount).where(PlatformAccount.platform == platform)
    if user is not None:
        statement = _owned_statement(statement, PlatformAccount, user)
    accounts = session.exec(statement).all()
    for account in accounts:
        account.is_default = False
        session.add(account)


@router.post("/trending/searches", response_model=TrendingSearch)
def create_trending_search(
    payload: TrendingSearchCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> TrendingSearch:
    _require_write_user(user)
    search = TrendingSearch.model_validate(payload)
    _assign_owner(search, user)
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
    _ensure_record_access(search, user, "Trending search", write=True)
    search.status = TaskStatus.running
    session.add(search)
    session.commit()

    credential = _active_platform_credential(session, search.platform, "trending")
    try:
        videos = await TrendingCollector(credential).collect(search)
    except Exception as exc:
        search.status = TaskStatus.failed
        search.notes = f"采集失败：{str(exc)[:400]}"
        session.add(search)
        session.commit()
        session.refresh(search)
        return search
    existing_videos = session.exec(select(TrendingVideo).where(TrendingVideo.search_id == search.id)).all()
    for existing_video in existing_videos:
        session.delete(existing_video)
    for video in videos:
        _assign_owner(video, user)
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
    statement = _owned_statement(select(TrendingSearch).order_by(TrendingSearch.created_at.desc()), TrendingSearch, user)
    return list(session.exec(statement).all())


@router.get("/trending/videos", response_model=list[TrendingVideo])
def list_trending_videos(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[TrendingVideo]:
    statement = _owned_statement(select(TrendingVideo).order_by(TrendingVideo.created_at.desc()), TrendingVideo, user)
    return list(session.exec(statement).all())


@router.post("/trending/videos", response_model=TrendingVideo)
def create_trending_video(
    payload: TrendingVideoCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> TrendingVideo:
    _require_write_user(user)
    video = TrendingVideo.model_validate(payload)
    _assign_owner(video, user)
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
    task = session.get(VideoTask, payload.video_task_id)
    _ensure_record_access(task, user, "Video task")
    script = session.get(Script, task.script_id)
    account = _resolve_publish_account(session, payload.platform_account_id, payload.platform, user=user)
    _ensure_publish_ready(session, task, script, payload.title, account)
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
    _assign_owner(record, user)
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


@router.get("/publish-records", response_model=list[PublishRecord])
def list_publish_records(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[PublishRecord]:
    statement = _owned_statement(select(PublishRecord).order_by(PublishRecord.created_at.desc()), PublishRecord, user)
    return list(session.exec(statement).all())


@router.patch("/publish-records/{record_id}", response_model=PublishRecord)
def update_publish_record(
    record_id: int,
    payload: PublishRecordUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> PublishRecord:
    record = session.get(PublishRecord, record_id)
    _ensure_record_access(record, user, "Publish record", write=True)
    update_data = payload.model_dump(exclude_unset=True)
    if "platform_account_id" in update_data:
        account_id = update_data.pop("platform_account_id")
        if account_id is None:
            record.platform_account_id = None
            if "account_name" not in update_data:
                record.account_name = None
        else:
            account = _resolve_publish_account(session, account_id, update_data.get("platform"), user=user)
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
    record = session.get(PublishRecord, record_id)
    _ensure_record_access(record, user, "Publish record")
    task = session.get(VideoTask, record.video_task_id)
    _ensure_record_access(task, user, "Video task")
    script = session.get(Script, task.script_id)
    account = session.get(PlatformAccount, record.platform_account_id) if record.platform_account_id else None
    _ensure_publish_ready(session, task, script, record.title, account)
    return _set_publish_status(session, record_id, "published", datetime.utcnow(), user=user)


@router.post("/publish-records/{record_id}/fail", response_model=PublishRecord)
def mark_publish_record_failed(
    record_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> PublishRecord:
    return _set_publish_status(session, record_id, "failed", user=user)


@router.post("/publish-records/{record_id}/cancel", response_model=PublishRecord)
def cancel_publish_record(
    record_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> PublishRecord:
    return _set_publish_status(session, record_id, "canceled", user=user)


def _set_publish_status(
    session: Session,
    record_id: int,
    status: str,
    published_at: Optional[datetime] = None,
    user: User | None = None,
) -> PublishRecord:
    record = session.get(PublishRecord, record_id)
    if user is not None:
        _ensure_record_access(record, user, "Publish record", write=True)
    elif record is None:
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
    _require_write_user(user)
    if payload.is_default:
        _clear_default_account(session, payload.platform, user=user)
    account = PlatformAccount.model_validate(payload)
    _assign_owner(account, user)
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


@router.get("/platform-accounts", response_model=list[PlatformAccount])
def list_platform_accounts(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[PlatformAccount]:
    statement = _owned_statement(
        select(PlatformAccount).order_by(
            PlatformAccount.is_default.desc(),
            PlatformAccount.created_at.desc(),
        ),
        PlatformAccount,
        user,
    )
    return list(session.exec(statement).all())


@router.patch("/platform-accounts/{account_id}", response_model=PlatformAccount)
def update_platform_account(
    account_id: int,
    payload: PlatformAccountUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> PlatformAccount:
    account = session.get(PlatformAccount, account_id)
    _ensure_record_access(account, user, "Platform account", write=True)
    update_data = payload.model_dump(exclude_unset=True)
    next_platform = update_data.get("platform", account.platform)
    if update_data.get("is_default") is True:
        _clear_default_account(session, next_platform, user=user)
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
    _ensure_record_access(account, user, "Platform account", write=True)
    _clear_default_account(session, account.platform, user=user)
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
