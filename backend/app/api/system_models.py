from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse

from fastapi import Depends, HTTPException
from sqlmodel import Session, select

from app.api.system_auth import require_admin
from app.core.db import get_session
from app.models.entities import AIModelConfig, AIModelUsage, PlatformCredential, User
from app.schemas.requests import (
    AIModelConfigCreate,
    AIModelConfigPublic,
    AIModelConfigUpdate,
    PlatformCredentialCreate,
    PlatformCredentialPublic,
    PlatformCredentialUpdate,
)
from app.services.model_router import choose_model_config
from app.services.usage import record_model_usage
from app.services.video_analysis import ReferenceVideoAnalyzer


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


def list_model_configs(
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> list[AIModelConfigPublic]:
    configs = session.exec(select(AIModelConfig).order_by(AIModelConfig.created_at.desc())).all()
    return [_model_config_public(config) for config in configs]


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
    return [
        _platform_credential_public(item)
        for item in credentials
        if item.purpose != "link_resolver"
    ]


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
