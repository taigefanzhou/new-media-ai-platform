from __future__ import annotations

from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlmodel import Session

from app.api.access import _assign_owner
from app.api.system_storage import _publish_material_to_remote
from app.core.storage import get_storage_root
from app.models.entities import CopyrightStatus, Material, MaterialKind, User


def _optional_form_id(value: Optional[str | int], field_label: str) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field_label}必须是有效素材 ID。") from exc


async def _save_uploaded_material(
    file: UploadFile,
    kind: MaterialKind,
    name: Optional[str],
    session: Session,
    copyright_status: CopyrightStatus = CopyrightStatus.owned,
    tags: str = "",
    owner: User | None = None,
) -> Material:
    original_name = file.filename or "upload.bin"
    suffix = Path(original_name).suffix
    storage_dir = get_storage_root(session) / "materials" / uuid4().hex
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_path = storage_dir / f"source{suffix}"
    with file_path.open("wb") as output:
        while chunk := await file.read(1024 * 1024):
            output.write(chunk)

    material = Material(
        name=name or original_name,
        kind=kind,
        copyright_status=copyright_status,
        file_path=str(file_path),
        tags=tags,
    )
    if owner is not None:
        _assign_owner(material, owner)
    session.add(material)
    session.commit()
    session.refresh(material)
    try:
        await _publish_material_to_remote(material, session)
        session.refresh(material)
    except Exception:
        pass
    return material
