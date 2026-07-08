from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlmodel import Session, select

from app.api.system_auth import _user_public, require_admin
from app.core.db import get_session
from app.core.security import hash_password
from app.models.entities import User, UserRole
from app.schemas.requests import UserCreate, UserPasswordReset, UserPublic, UserUpdate


def list_users(
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> list[UserPublic]:
    users = session.exec(select(User).order_by(User.created_at.desc())).all()
    return [_user_public(item) for item in users]


def create_user(
    payload: UserCreate,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> UserPublic:
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    existing = session.exec(select(User).where(User.username == username)).first()
    if existing is not None:
        raise HTTPException(status_code=400, detail="Username already exists")
    user = User(
        username=username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=payload.is_active,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return _user_public(user)


def update_user(
    user_id: int,
    payload: UserUpdate,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> UserPublic:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    update_data = payload.model_dump(exclude_unset=True)
    if user.id == admin.id and (
        update_data.get("is_active") is False or update_data.get("role") not in (None, UserRole.admin)
    ):
        raise HTTPException(status_code=400, detail="Cannot disable or demote the current admin account")
    for key, value in update_data.items():
        setattr(user, key, value)
    session.add(user)
    session.commit()
    session.refresh(user)
    return _user_public(user)


def reset_user_password(
    user_id: int,
    payload: UserPasswordReset,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> UserPublic:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.password_hash = hash_password(payload.password)
    session.add(user)
    session.commit()
    session.refresh(user)
    return _user_public(user)
