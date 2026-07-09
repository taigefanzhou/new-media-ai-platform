from __future__ import annotations

from datetime import datetime
import json
import mimetypes
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from fastapi import Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select
from app.api.access import (
    _assign_owner,
    _ensure_record_access,
    _owned_count,
    _owned_statement,
    _require_write_user,
)
from app.api.reference_learning import (
    _link_resolver_credentials,
    _probe_reference_media_url,
    _url_preview,
)
from app.api.system_auth import require_admin
from app.api.system_models import (
    _configured_model_status,
    _smart_model_config,
    _video_generation_fallback_ready,
)
from app.core.config import get_settings
from app.core.auth import current_user
from app.core.db import get_session
from app.core.storage import get_storage_root
from app.models.entities import (
    AIModelConfig,
    DigitalHuman,
    Material,
    PlatformCredential,
    PublishRecord,
    ReferenceVideoAnalysis,
    Script,
    Topic,
    TrendingVideo,
    TranscriptionTask,
    User,
    VideoTask,
)
from app.schemas.requests import (
    LinkResolverTestRequest,
    ScriptBatchGenerateRequest,
    ScriptGenerateRequest,
    ScriptUpdate,
    ScriptVideoTaskCreate,
    TopicCreate,
)
from app.services.ai_clients import MediaGenerationClient, ScriptGenerator
from app.services.link_resolver import (
    ShortVideoLinkResolver,
    detect_short_video_platform,
)
from app.services.usage import estimate_text_tokens, record_generated_model_usage, record_model_usage

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


def list_scripts(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[Script]:
    statement = _owned_statement(select(Script).order_by(Script.created_at.desc()), Script, user)
    return list(session.exec(statement).all())


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
