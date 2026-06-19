from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from app.core.db import get_session
from app.models.entities import (
    DigitalHuman,
    Material,
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


@router.post("/materials", response_model=Material)
def create_material(payload: MaterialCreate, session: Session = Depends(get_session)) -> Material:
    material = Material.model_validate(payload)
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
