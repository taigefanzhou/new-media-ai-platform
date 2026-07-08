from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import *  # noqa: F403


router = APIRouter(tags=["脚本方向创作"])


router.post("/topics", response_model=Topic)(create_topic)
router.get("/topics", response_model=list[Topic])(list_topics)
router.post("/scripts/generate", response_model=Script)(generate_script)
router.post("/scripts/batch-generate", response_model=list[Script])(batch_generate_scripts)
router.get("/scripts", response_model=list[Script])(list_scripts)
router.patch("/scripts/{script_id}", response_model=Script)(update_script)
router.post("/scripts/{script_id}/video-task", response_model=VideoTask)(create_video_task_from_script)
router.post("/scripts/{script_id}/auto-video-task", response_model=VideoTask)(approve_script_and_run_video_task)
router.post("/scripts/{script_id}/voice-preview")(generate_script_voice_preview)
