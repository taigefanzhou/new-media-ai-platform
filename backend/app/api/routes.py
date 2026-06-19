from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session, func, select
from app.core.config import get_settings
from app.core.auth import current_user
from app.core.db import get_session
from app.core.security import create_token, hash_password
from app.models.entities import (
    AIModelConfig,
    AuthSession,
    CopyrightStatus,
    DigitalHuman,
    Material,
    MaterialKind,
    PlatformAccount,
    PlatformCredential,
    PublishRecord,
    Script,
    TaskStatus,
    Topic,
    TrendingSearch,
    TrendingVideo,
    TranscriptionTask,
    User,
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
    ScriptGenerateRequest,
    ScriptVideoTaskCreate,
    TopicCreate,
    TrendingSearchCreate,
    TrendingVideoCreate,
    TranscriptionTaskCreate,
    VideoTaskPublishPrepareRequest,
    VideoTaskCreate,
)
from app.services.ai_clients import ScriptGenerator
from app.services.asr import ASRClient
from app.services.pipeline import VideoPipeline
from app.services.trending import TrendingCollector


router = APIRouter()


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
    settings = get_settings()
    original_name = file.filename or "upload.bin"
    suffix = Path(original_name).suffix
    storage_dir = Path(settings.storage_dir) / "materials" / uuid4().hex
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
    task.status = TaskStatus.running
    session.add(task)
    session.commit()
    try:
        result = await ASRClient().transcribe(task, material)
        task.transcript = result.transcript
        task.summary = result.summary
        task.hook_analysis = result.hook_analysis
        task.status = TaskStatus.needs_review
    except Exception as exc:
        task.status = TaskStatus.failed
        task.error_message = str(exc)
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
    active_model = session.exec(
        select(AIModelConfig).where(AIModelConfig.purpose == "script", AIModelConfig.is_active == True)
    ).first()
    generated = await ScriptGenerator(active_model).generate(
        topic=topic,
        brand_voice="专业、可信、原创、适合公司数字人口播",
        duration_seconds=30,
        target_platform="douyin",
    )
    script = Script(
        topic_id=None,
        duration_seconds=30,
        hook=generated.hook,
        voiceover=generated.voiceover,
        storyboard=generated.storyboard,
        seedance_prompt=generated.seedance_prompt,
        title_options=generated.title_options,
        hashtags=generated.hashtags,
        compliance_notes=f"{generated.compliance_notes}\n基于转写任务 #{task.id} 生成，仅借鉴结构，不搬运原文。",
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


@router.post("/scripts/generate", response_model=Script)
async def generate_script(payload: ScriptGenerateRequest, session: Session = Depends(get_session)) -> Script:
    active_model = session.exec(
        select(AIModelConfig).where(AIModelConfig.purpose == "script", AIModelConfig.is_active == True)
    ).first()
    generated = await ScriptGenerator(active_model).generate(
        topic=payload.topic,
        brand_voice=payload.brand_voice,
        duration_seconds=payload.duration_seconds,
        target_platform=payload.target_platform,
        output_language=payload.output_language,
    )
    script = Script(
        topic_id=payload.topic_id,
        duration_seconds=payload.duration_seconds,
        hook=generated.hook,
        voiceover=generated.voiceover,
        storyboard=generated.storyboard,
        seedance_prompt=generated.seedance_prompt,
        title_options=generated.title_options,
        hashtags=generated.hashtags,
        compliance_notes=generated.compliance_notes,
    )
    session.add(script)
    session.commit()
    session.refresh(script)
    return script


@router.get("/scripts", response_model=list[Script])
def list_scripts(session: Session = Depends(get_session)) -> list[Script]:
    return list(session.exec(select(Script).order_by(Script.created_at.desc())).all())


@router.post("/scripts/{script_id}/video-task", response_model=VideoTask)
def create_video_task_from_script(
    script_id: int,
    payload: ScriptVideoTaskCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> VideoTask:
    if session.get(Script, script_id) is None:
        raise HTTPException(status_code=404, detail="Script not found")
    if payload.digital_human_id is not None and session.get(DigitalHuman, payload.digital_human_id) is None:
        raise HTTPException(status_code=404, detail="Digital human not found")
    task = VideoTask(script_id=script_id, digital_human_id=payload.digital_human_id, status=TaskStatus.queued)
    session.add(task)
    session.commit()
    session.refresh(task)
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


@router.get("/digital-humans", response_model=list[DigitalHuman])
def list_digital_humans(session: Session = Depends(get_session)) -> list[DigitalHuman]:
    return list(session.exec(select(DigitalHuman).order_by(DigitalHuman.created_at.desc())).all())


@router.post("/video-tasks", response_model=VideoTask)
def create_video_task(payload: VideoTaskCreate, session: Session = Depends(get_session)) -> VideoTask:
    if session.get(Script, payload.script_id) is None:
        raise HTTPException(status_code=404, detail="Script not found")
    if payload.digital_human_id is not None and session.get(DigitalHuman, payload.digital_human_id) is None:
        raise HTTPException(status_code=404, detail="Digital human not found")
    task = VideoTask(script_id=payload.script_id, digital_human_id=payload.digital_human_id, status=TaskStatus.queued)
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@router.post("/video-tasks/{task_id}/run", response_model=VideoTask)
async def run_video_task(task_id: int, session: Session = Depends(get_session)) -> VideoTask:
    task = session.get(VideoTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Video task not found")
    return await VideoPipeline(session).run(task)


@router.post("/video-tasks/{task_id}/approve", response_model=VideoTask)
def approve_video_task(task_id: int, session: Session = Depends(get_session)) -> VideoTask:
    task = session.get(VideoTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Video task not found")
    task.status = TaskStatus.approved
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@router.get("/video-tasks", response_model=list[VideoTask])
def list_video_tasks(session: Session = Depends(get_session)) -> list[VideoTask]:
    return list(session.exec(select(VideoTask).order_by(VideoTask.created_at.desc())).all())


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
