from __future__ import annotations

from pathlib import Path

from fastapi import Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.core.auth import current_user
from app.core.db import get_session
from app.api.modules._legacy import legacy_module_router
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


MIGRATED_ROUTES = {
    ("/materials", "GET"),
    ("/materials", "POST"),
    ("/materials/{material_id}/preview", "GET"),
    ("/materials/{material_id}", "DELETE"),
}

router = legacy_module_router("reference_learning", exclude_routes=MIGRATED_ROUTES)


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
