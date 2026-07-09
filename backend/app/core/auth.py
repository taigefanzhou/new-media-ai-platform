from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, Header, HTTPException, Query
from sqlmodel import Session, select
from app.core.config import get_settings
from app.core.db import get_session
from app.models.entities import AuthSession, User


def user_from_token(token: str, session: Session) -> User:
    auth_session = session.exec(select(AuthSession).where(AuthSession.token == token)).first()
    if auth_session is None:
        raise HTTPException(status_code=401, detail="Invalid authorization token")
    ttl_hours = get_settings().auth_session_ttl_hours
    if ttl_hours > 0 and auth_session.created_at < datetime.utcnow() - timedelta(hours=ttl_hours):
        session.delete(auth_session)
        session.commit()
        raise HTTPException(status_code=401, detail="Authorization token expired")
    user = session.get(User, auth_session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Inactive user")
    return user


def current_user(
    authorization: Optional[str] = Header(default=None),
    access_token: Optional[str] = Query(default=None),
    session: Session = Depends(get_session),
) -> User:
    token = access_token
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing authorization token")
    return user_from_token(token, session)
