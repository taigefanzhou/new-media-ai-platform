from __future__ import annotations

import math
from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session

from app.api.access import _assign_owner
from app.models.entities import Script, TaskStatus, User, VideoTask
from app.services.export_profiles import resolve_export_profile
from app.services.pipeline import VideoPipeline


PRODUCTION_MODES = {
    "dynamic_explainer",
    "digital_human",
    "material_mix",
    "reference_clone",
    "seedance_scene",
    "talking_head_template",
}

VOICE_PRESETS = {
    "longanhuan": "元气自然女声",
    "longanwen_v3": "优雅知性女声",
    "longanli_v3": "利落从容女声",
    "longxing_v3": "温婉邻家女声",
    "longwan_v3": "细腻柔声女声",
    "longanyang": "阳光男声",
}


def normalize_voice_id(voice_id: Optional[str]) -> Optional[str]:
    value = (voice_id or "").strip()
    if not value:
        return None
    if value not in VOICE_PRESETS:
        raise HTTPException(status_code=400, detail="未知音色，请选择系统提供的音色。")
    return value


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
    voice_id: Optional[str] = None,
    status: TaskStatus = TaskStatus.queued,
    audit_notes: str = "",
    owner: User | None = None,
) -> VideoTask:
    if production_mode not in PRODUCTION_MODES:
        raise HTTPException(status_code=400, detail="Unknown production mode")
    segment_count = _estimated_video_segment_count(script.duration_seconds)
    platform_name = target_platform or script.target_platform or "douyin"
    # ponytail: reference_clone currently means the approved He Yiyi 9:16 hotel talking template.
    if production_mode == "reference_clone":
        platform_name = "wechat_channels"
        profile = resolve_export_profile("wechat_channels_portrait", platform_name)
    else:
        profile = resolve_export_profile(export_profile, platform_name)
    selected_voice = normalize_voice_id(voice_id)
    task_notes = audit_notes
    if selected_voice:
        task_notes = f"{task_notes}\nvoice_id={selected_voice}".strip()
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
        audit_notes=task_notes,
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


def _ensure_video_task_can_run(task: VideoTask) -> None:
    if task.status == TaskStatus.running:
        raise HTTPException(status_code=409, detail="Video task is already generating")
    if task.output_path or task.status in (TaskStatus.needs_review, TaskStatus.approved):
        raise HTTPException(status_code=400, detail="Video task already has generated output")
    if task.status not in (TaskStatus.draft, TaskStatus.queued, TaskStatus.failed):
        raise HTTPException(status_code=400, detail="Video task is not ready to generate")
