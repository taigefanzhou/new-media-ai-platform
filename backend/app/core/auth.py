from __future__ import annotations

from typing import Optional
from fastapi import Depends, Header, HTTPException
from sqlmodel import Session, select
from app.core.db import get_session
from app.models.entities import AuthSession, User


def current_user(
    authorization: Optional[str] = Header(default=None),
    session: Session = Depends(get_session),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")
    token = authorization.removeprefix("Bearer ").strip()
    auth_session = session.exec(select(AuthSession).where(AuthSession.token == token)).first()
    if auth_session is None:
        raise HTTPException(status_code=401, detail="Invalid authorization token")
    user = session.get(User, auth_session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Inactive user")
    return user
