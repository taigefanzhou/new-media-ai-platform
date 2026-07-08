from __future__ import annotations

from fastapi import HTTPException
from sqlmodel import Session, func, select

from app.models.entities import User, UserRole


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


def _owned_count(session: Session, model: object, user: User) -> int:
    statement = _owned_statement(select(func.count()).select_from(model), model, user)
    return session.exec(statement).one()
