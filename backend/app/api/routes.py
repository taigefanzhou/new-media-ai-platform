from __future__ import annotations

from datetime import datetime
import json
import mimetypes
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from fastapi import BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select
from app.api.access import (
    _assign_owner,
    _ensure_record_access,
    _is_admin,
    _owned_count,
    _owned_statement,
    _require_write_user,
)
from app.api.publishing_support import (
    _active_platform_credential,
    _caption_from_script,
    _clear_default_account,
    _effective_video_output_path,
    _ensure_publish_ready,
    _hashtags_from_script,
    _parse_optional_datetime,
    _publish_title_from_script,
    _resolve_publish_account,
    _set_publish_status,
)
from app.api.reference_learning import (
    _link_resolver_credentials,
    _probe_reference_media_url,
    _url_preview,
)
from app.api.system_auth import (
    _bearer_token,
    _user_public,
    require_admin,
)
from app.api.system_models import (
    MODEL_LOCAL_PROVIDERS,
    MODEL_PURPOSE_LABELS,
    _active_model_config,
    _configured_model_status,
    _diagnose_model_config,
    _is_volcengine_jimeng_provider,
    _smart_model_config,
    _video_generation_fallback_ready,
    _volcengine_jimeng_credential_ready,
)
from app.api.video_tasks_support import (
    PRODUCTION_MODES,
    _build_video_task,
    _ensure_video_task_can_run,
    _prepare_material_mix_segments,
)
from app.core.config import get_settings
from app.core.auth import current_user
from app.core.db import engine, get_session
from app.core.storage import get_storage_root
from app.models.entities import (
    AIModelConfig,
    CopyrightStatus,
    DigitalHuman,
    Material,
    MaterialKind,
    PlatformAccount,
    PlatformCredential,
    PublishRecord,
    ReferenceVideoAnalysis,
    Script,
    TaskStatus,
    Topic,
    TrendingSearch,
    TrendingVideo,
    TranscriptionTask,
    User,
    VideoSegment,
    VideoTask,
)
from app.schemas.requests import (
    LinkResolverTestRequest,
    ScriptBatchGenerateRequest,
    ScriptGenerateRequest,
    ScriptUpdate,
    ScriptVideoTaskCreate,
    TopicCreate,
    VideoSegmentMaterialUpdate,
    UserPublic,
    VideoTaskBatchCreateRequest,
    VideoTaskBatchRunRequest,
    VideoTaskPublishPrepareRequest,
    VideoTaskCreate,
)
from app.services.ai_clients import MediaGenerationClient, ScriptGenerator
from app.services.link_resolver import (
    ShortVideoLinkResolver,
    detect_short_video_platform,
)
from app.services.model_router import is_model_config_ready
from app.services.usage import estimate_text_tokens, record_generated_model_usage, record_model_usage

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


def list_video_tasks(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[VideoTask]:
    statement = _owned_statement(select(VideoTask).order_by(VideoTask.created_at.desc()), VideoTask, user)
    return list(session.exec(statement).all())


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
