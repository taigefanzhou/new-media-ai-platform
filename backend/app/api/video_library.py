from __future__ import annotations

from datetime import datetime
from pathlib import Path
import subprocess
from typing import Optional

from fastapi import BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.api.access import _assign_owner, _ensure_record_access, _owned_statement, _require_write_user
from app.api.publishing_support import (
    _caption_from_script,
    _effective_video_output_path,
    _ensure_publish_ready,
    _hashtags_from_script,
    _parse_optional_datetime,
    _publish_title_from_script,
    _resolve_publish_account,
)
from app.api.system_models import (
    MODEL_LOCAL_PROVIDERS,
    _is_volcengine_jimeng_provider,
    _smart_model_config,
    _volcengine_jimeng_credential_ready,
)
from app.api.video_tasks_support import (
    PRODUCTION_MODES,
    _build_video_task,
    _ensure_video_task_can_run,
    _prepare_material_mix_segments,
)
from app.core.auth import current_user
from app.core.config import get_settings
from app.core.db import engine, get_session
from app.core.storage import get_storage_root
from app.models.entities import (
    CopyrightStatus,
    DigitalHuman,
    Material,
    MaterialKind,
    PublishRecord,
    Script,
    TaskStatus,
    User,
    VideoSegment,
    VideoTask,
)
from app.schemas.requests import (
    ScriptVideoTaskCreate,
    VideoSegmentMaterialUpdate,
    VideoTaskBatchCreateRequest,
    VideoTaskBatchRunRequest,
    VideoTaskCreate,
    VideoTaskPublishPrepareRequest,
)
from app.services.model_router import is_model_config_ready
from app.services.pipeline import VideoPipeline


async def _run_video_task_background(task_id: int) -> None:
    with Session(engine) as session:
        task = session.get(VideoTask, task_id)
        if task is None:
            return
        try:
            await VideoPipeline(session).run(task)
        except Exception as exc:
            task.status = TaskStatus.failed
            task.error_message = str(exc)
            task.audit_notes = (
                f"{task.audit_notes}\n后台生成启动失败：{exc}".strip()
                if task.audit_notes
                else f"后台生成启动失败：{exc}"
            )
            task.updated_at = datetime.utcnow()
            session.add(task)
            session.commit()


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


def preview_video_task_poster(
    task_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> FileResponse:
    task = session.get(VideoTask, task_id)
    _ensure_record_access(task, user, "Video task")
    output_path = _effective_video_output_path(task) if task else None
    if not output_path or output_path.startswith(("http://", "https://", "mock://")):
        raise HTTPException(status_code=404, detail="Video poster not found")
    video_path = Path(output_path)
    if not video_path.exists() or not video_path.is_file():
        raise HTTPException(status_code=404, detail="Video file not found")

    poster_path = get_storage_root(session) / "posters" / f"task-{task_id}.jpg"
    if not poster_path.exists() or poster_path.stat().st_mtime < video_path.stat().st_mtime:
        poster_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            get_settings().ffmpeg_binary,
            "-y",
            "-ss",
            "0",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(poster_path),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True)
        except Exception as exc:
            raise HTTPException(status_code=404, detail=f"Video poster unavailable: {exc}") from exc
    return FileResponse(poster_path, media_type="image/jpeg")


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
