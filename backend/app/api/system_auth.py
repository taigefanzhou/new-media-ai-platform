from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlmodel import Session, select

from app.core.auth import current_user
from app.core.db import get_session
from app.core.security import create_token, hash_password, password_hash_needs_upgrade, verify_password
from app.models.entities import AuthSession, User, UserRole
from app.schemas.requests import ChangePasswordRequest, LoginRequest, UserPublic


def _bearer_token(authorization: Optional[str]) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")
    return authorization.removeprefix("Bearer ").strip()


def _user_public(user: User) -> UserPublic:
    return UserPublic(
        id=user.id or 0,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


def health() -> dict[str, str]:
    return {"status": "ok"}


def login(payload: LoginRequest, session: Session = Depends(get_session)) -> dict[str, object]:
    user = session.exec(select(User).where(User.username == payload.username)).first()
    if user is None or not verify_password(payload.password, user.password_hash) or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if password_hash_needs_upgrade(user.password_hash):
        user.password_hash = hash_password(payload.password)
        session.add(user)
    token = create_token()
    auth_session = AuthSession(user_id=user.id, token=token)
    session.add(auth_session)
    session.commit()
    return {"token": token, "user": _user_public(user)}


def me(user: User = Depends(current_user)) -> UserPublic:
    return _user_public(user)


def logout(
    authorization: Optional[str] = Header(default=None),
    session: Session = Depends(get_session),
) -> dict[str, bool]:
    token = _bearer_token(authorization)
    auth_session = session.exec(select(AuthSession).where(AuthSession.token == token)).first()
    if auth_session is not None:
        session.delete(auth_session)
        session.commit()
    return {"ok": True}


def change_password(
    payload: ChangePasswordRequest,
    authorization: Optional[str] = Header(default=None),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict[str, bool]:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    session.add(user)
    current_token = _bearer_token(authorization)
    other_sessions = session.exec(
        select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.token != current_token)
    ).all()
    for auth_session in other_sessions:
        session.delete(auth_session)
    session.commit()
    return {"ok": True}


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin account required")
    return user
