from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.api.routes import *  # noqa: F403
from app.core.auth import current_user
from app.core.db import get_session
from app.models.entities import (
    DigitalHuman,
    Material,
    ReferenceVideoAnalysis,
    Topic,
    TranscriptionTask,
    User,
    UserRole,
)
from app.schemas.requests import MaterialCreate


router = APIRouter(tags=["参考视频学习"])


def _is_admin(user: User) -> bool:
    return user.role == UserRole.admin


def _require_write_user(user: User) -> None:
    if user.role == UserRole.reviewer:
        raise HTTPException(status_code=403, detail="Reviewer accounts cannot create or modify business data")


def _assign_owner(record: object, user: User) -> None:
    if hasattr(record, "owner_user_id") and getattr(record, "owner_user_id", None) is None:
        setattr(record, "owner_user_id", user.id)


def _owned_statement(statement, model: object, user: User):
    if _is_admin(user):
        return statement
    owner_field = getattr(model, "owner_user_id", None)
    if owner_field is None:
        return statement
    return statement.where(owner_field == user.id)


def _ensure_record_access(record: object | None, user: User, label: str, *, write: bool = False):
    if record is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    if write:
        _require_write_user(user)
    if _is_admin(user):
        return record
    owner_id = getattr(record, "owner_user_id", None)
    if owner_id != user.id:
        raise HTTPException(status_code=403, detail=f"No permission to access this {label}")
    return record


def _delete_local_file(path_value: str | None) -> None:
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


@router.get("/materials", response_model=list[Material])
def list_materials(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[Material]:
    statement = _owned_statement(select(Material).order_by(Material.created_at.desc()), Material, user)
    return list(session.exec(statement).all())


@router.post("/materials", response_model=Material)
def create_material(
    payload: MaterialCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> Material:
    _require_write_user(user)
    material = Material.model_validate(payload)
    _assign_owner(material, user)
    session.add(material)
    session.commit()
    session.refresh(material)
    return material


@router.get("/materials/{material_id}/preview")
def preview_material(
    material_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> FileResponse:
    material = session.get(Material, material_id)
    _ensure_record_access(material, user, "Material")
    if not material.file_path:
        raise HTTPException(status_code=404, detail="Material preview not found")
    path = Path(material.file_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Material file not found")
    return FileResponse(path)


@router.delete("/materials/{material_id}")
def delete_material(
    material_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict[str, object]:
    material = session.get(Material, material_id)
    _ensure_record_access(material, user, "Material", write=True)

    humans = session.exec(
        select(DigitalHuman).where(
            (DigitalHuman.portrait_material_id == material_id)
            | (DigitalHuman.source_video_material_id == material_id)
        )
    ).all()
    for human in humans:
        if human.portrait_material_id == material_id:
            human.portrait_material_id = None
        if human.source_video_material_id == material_id:
            human.source_video_material_id = None
        session.add(human)

    topics = session.exec(select(Topic).where(Topic.reference_material_id == material_id)).all()
    for topic in topics:
        topic.reference_material_id = None
        session.add(topic)

    transcriptions = session.exec(select(TranscriptionTask).where(TranscriptionTask.material_id == material_id)).all()
    for task in transcriptions:
        session.delete(task)
    analyses = session.exec(select(ReferenceVideoAnalysis).where(ReferenceVideoAnalysis.material_id == material_id)).all()
    for analysis in analyses:
        _delete_local_file(analysis.contact_sheet_path)
        _delete_local_file(analysis.dense_contact_sheet_path)
        session.delete(analysis)

    _delete_local_file(material.file_path)
    session.delete(material)
    session.commit()
    return {"deleted": True, "id": material_id}


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
