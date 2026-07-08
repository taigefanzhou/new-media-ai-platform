from __future__ import annotations

from fastapi import APIRouter

from app.api.reference_learning import (
    approve_reference_video_analysis,
    create_material,
    create_reference_material_from_link,
    create_reference_video_analysis,
    create_topic_from_transcription,
    create_transcription_task,
    delete_material,
    generate_script_from_reference_video_analysis,
    generate_script_from_transcription,
    list_reference_video_analyses,
    list_materials,
    list_transcription_tasks,
    preview_material,
    reference_video_analysis_contact_sheet,
    reference_video_analysis_dense_contact_sheet,
    reject_reference_video_analysis,
    resolve_download_reference_material,
    run_reference_video_analysis,
    run_transcription_task,
    upload_material,
    upload_material_to_remote,
)
from app.models.entities import Material, ReferenceVideoAnalysis, Script, Topic, TranscriptionTask


router = APIRouter(tags=["参考视频学习"])


router.get("/materials", response_model=list[Material])(list_materials)
router.post("/materials", response_model=Material)(create_material)
router.get("/materials/{material_id}/preview")(preview_material)
router.delete("/materials/{material_id}")(delete_material)


router.post("/materials/{material_id}/remote-upload", response_model=Material)(upload_material_to_remote)
router.post("/reference-materials/from-link", response_model=Material)(create_reference_material_from_link)
router.post("/reference-materials/{material_id}/resolve-download", response_model=Material)(resolve_download_reference_material)
router.post("/materials/upload", response_model=Material)(upload_material)
router.post("/transcriptions", response_model=TranscriptionTask)(create_transcription_task)
router.post("/transcriptions/{task_id}/run", response_model=TranscriptionTask)(run_transcription_task)
router.get("/transcriptions", response_model=list[TranscriptionTask])(list_transcription_tasks)
router.post("/transcriptions/{task_id}/create-topic", response_model=Topic)(create_topic_from_transcription)
router.post("/transcriptions/{task_id}/generate-script", response_model=Script)(generate_script_from_transcription)
router.post("/video-analyses", response_model=ReferenceVideoAnalysis)(create_reference_video_analysis)
router.post("/video-analyses/{analysis_id}/run", response_model=ReferenceVideoAnalysis)(run_reference_video_analysis)
router.get("/video-analyses", response_model=list[ReferenceVideoAnalysis])(list_reference_video_analyses)
router.post("/video-analyses/{analysis_id}/approve", response_model=ReferenceVideoAnalysis)(approve_reference_video_analysis)
router.post("/video-analyses/{analysis_id}/reject", response_model=ReferenceVideoAnalysis)(reject_reference_video_analysis)
router.get("/video-analyses/{analysis_id}/contact-sheet")(reference_video_analysis_contact_sheet)
router.get("/video-analyses/{analysis_id}/dense-contact-sheet")(reference_video_analysis_dense_contact_sheet)
router.post("/video-analyses/{analysis_id}/generate-script", response_model=Script)(generate_script_from_reference_video_analysis)
