from __future__ import annotations

from pathlib import Path
from typing import Optional
from uuid import uuid4
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session, func, select
from app.core.config import get_settings
from app.core.db import get_session
from app.models.entities import (
    CopyrightStatus,
    DigitalHuman,
    Material,
    MaterialKind,
    PublishRecord,
    Script,
    TaskStatus,
    Topic,
    VideoTask,
)
from app.schemas.requests import (
    DigitalHumanCreate,
    MaterialCreate,
    PublishPrepareRequest,
    ScriptGenerateRequest,
    TopicCreate,
    VideoTaskCreate,
)
from app.services.ai_clients import ScriptGenerator
from app.services.pipeline import VideoPipeline


router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/dashboard")
def dashboard(session: Session = Depends(get_session)) -> dict[str, object]:
    counts = {
        "materials": session.exec(select(func.count()).select_from(Material)).one(),
        "topics": session.exec(select(func.count()).select_from(Topic)).one(),
        "scripts": session.exec(select(func.count()).select_from(Script)).one(),
        "digital_humans": session.exec(select(func.count()).select_from(DigitalHuman)).one(),
        "video_tasks": session.exec(select(func.count()).select_from(VideoTask)).one(),
        "publish_records": session.exec(select(func.count()).select_from(PublishRecord)).one(),
    }
    recent_tasks = session.exec(select(VideoTask).order_by(VideoTask.created_at.desc()).limit(5)).all()
    recent_scripts = session.exec(select(Script).order_by(Script.created_at.desc()).limit(5)).all()
    return {"counts": counts, "recent_tasks": recent_tasks, "recent_scripts": recent_scripts}


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
    generated = await ScriptGenerator().generate(
        topic=payload.topic,
        brand_voice=payload.brand_voice,
        duration_seconds=payload.duration_seconds,
        target_platform=payload.target_platform,
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


@router.post("/digital-humans", response_model=DigitalHuman)
def create_digital_human(payload: DigitalHumanCreate, session: Session = Depends(get_session)) -> DigitalHuman:
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


@router.post("/publish-records", response_model=PublishRecord)
def prepare_publish_record(payload: PublishPrepareRequest, session: Session = Depends(get_session)) -> PublishRecord:
    if session.get(VideoTask, payload.video_task_id) is None:
        raise HTTPException(status_code=404, detail="Video task not found")
    record = PublishRecord.model_validate(payload)
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


@router.get("/publish-records", response_model=list[PublishRecord])
def list_publish_records(session: Session = Depends(get_session)) -> list[PublishRecord]:
    return list(session.exec(select(PublishRecord).order_by(PublishRecord.created_at.desc())).all())
