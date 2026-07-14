from fastapi import APIRouter

from app.api.drama import (
    bootstrap_cloud_hotel,
    build_drama_video_task,
    create_drama_character,
    create_drama_project,
    create_drama_scene,
    create_drama_shot,
    get_drama_project,
    list_drama_projects,
    update_drama_shot,
)


router = APIRouter(tags=["短剧工作台"])

router.get("/drama-projects")(list_drama_projects)
router.post("/drama-projects")(create_drama_project)
router.get("/drama-projects/{project_id}")(get_drama_project)
router.post("/drama-projects/{project_id}/bootstrap-cloud-hotel")(bootstrap_cloud_hotel)
router.post("/drama-projects/{project_id}/characters")(create_drama_character)
router.post("/drama-projects/{project_id}/scenes")(create_drama_scene)
router.post("/drama-projects/{project_id}/shots")(create_drama_shot)
router.patch("/drama-shots/{shot_id}")(update_drama_shot)
router.post("/drama-projects/{project_id}/build-video-task")(build_drama_video_task)
