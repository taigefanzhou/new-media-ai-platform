from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    approve_video_task,
    batch_create_video_tasks,
    batch_run_video_tasks,
    create_video_task,
    delete_video_task,
    delete_video_task_output,
    list_video_task_segments,
    list_video_tasks,
    prepare_publish_record_from_video_task,
    preview_video_task_output,
    run_video_task,
    update_video_segment_material,
)
from app.models.entities import PublishRecord, VideoSegment, VideoTask


router = APIRouter(tags=["视频库与生成任务"])


router.post("/video-tasks", response_model=VideoTask)(create_video_task)
router.post("/video-tasks/batch-create", response_model=list[VideoTask])(batch_create_video_tasks)
router.post("/video-tasks/batch-run", response_model=list[VideoTask])(batch_run_video_tasks)
router.post("/video-tasks/{task_id}/run", response_model=VideoTask)(run_video_task)
router.post("/video-tasks/{task_id}/approve", response_model=VideoTask)(approve_video_task)
router.get("/video-tasks", response_model=list[VideoTask])(list_video_tasks)
router.get("/video-tasks/{task_id}/segments", response_model=list[VideoSegment])(list_video_task_segments)
router.patch("/video-tasks/{task_id}/segments/{segment_id}/material", response_model=VideoSegment)(update_video_segment_material)
router.get("/video-tasks/{task_id}/output")(preview_video_task_output)
router.delete("/video-tasks/{task_id}/output")(delete_video_task_output)
router.delete("/video-tasks/{task_id}")(delete_video_task)
router.post("/video-tasks/{task_id}/publish-record", response_model=PublishRecord)(prepare_publish_record_from_video_task)
