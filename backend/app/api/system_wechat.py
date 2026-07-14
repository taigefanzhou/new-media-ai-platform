from __future__ import annotations

from datetime import datetime
from time import sleep
from urllib.parse import urlencode

from fastapi import Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, select

from app.api.system_auth import _user_public, require_admin
from app.core.db import get_session
from app.core.security import create_token, hash_password
from app.models.entities import (
    AuthSession,
    User,
    WechatIdentity,
    WechatLoginConfig,
    WechatLoginRequest,
    WechatLoginStatus,
)
from app.schemas.requests import (
    WechatIdentityPublic,
    WechatLoginApproveRequest,
    WechatLoginConfigPublic,
    WechatLoginConfigUpdate,
    WechatLoginPublicConfig,
    WechatLoginRejectRequest,
    WechatLoginRequestPublic,
)
from app.services.wechat_login import (
    WechatOAuthClient,
    build_wechat_qr_url,
    create_wechat_state,
    masked_suffix,
    random_temporary_password,
    verify_wechat_state,
)


def _active_wechat_config(session: Session) -> WechatLoginConfig | None:
    return session.exec(
        select(WechatLoginConfig)
        .where(WechatLoginConfig.is_active == True)  # noqa: E712
        .order_by(WechatLoginConfig.updated_at.desc())
    ).first()


def _wechat_config_public(config: WechatLoginConfig | None) -> WechatLoginConfigPublic:
    if config is None:
        return WechatLoginConfigPublic()
    return WechatLoginConfigPublic(
        id=config.id,
        app_id=config.app_id,
        redirect_uri=config.redirect_uri,
        is_active=config.is_active,
        default_role=config.default_role,
        has_app_secret=bool(config.app_secret),
        updated_at=config.updated_at,
    )


def _wechat_request_public(item: WechatLoginRequest) -> WechatLoginRequestPublic:
    return WechatLoginRequestPublic(
        id=item.id or 0,
        openid_suffix=masked_suffix(item.openid),
        unionid_suffix=masked_suffix(item.unionid),
        nickname=item.nickname,
        avatar_url=item.avatar_url,
        status=item.status,
        requested_at=item.requested_at,
        reviewed_at=item.reviewed_at,
        reviewed_by_user_id=item.reviewed_by_user_id,
        target_user_id=item.target_user_id,
        reject_reason=item.reject_reason,
    )


def _wechat_identity_public(identity: WechatIdentity, session: Session) -> WechatIdentityPublic:
    user = session.get(User, identity.user_id)
    return WechatIdentityPublic(
        id=identity.id or 0,
        user_id=identity.user_id,
        username=user.username if user else "",
        openid_suffix=masked_suffix(identity.openid),
        unionid_suffix=masked_suffix(identity.unionid),
        nickname=identity.nickname,
        avatar_url=identity.avatar_url,
        is_active=identity.is_active,
        bound_at=identity.bound_at,
        last_login_at=identity.last_login_at,
    )


def _find_wechat_identity(session: Session, openid: str, unionid: str | None) -> WechatIdentity | None:
    identity = session.exec(select(WechatIdentity).where(WechatIdentity.openid == openid)).first()
    if identity is None and unionid:
        identity = session.exec(select(WechatIdentity).where(WechatIdentity.unionid == unionid)).first()
    return identity


def _find_wechat_request(session: Session, openid: str) -> WechatLoginRequest | None:
    return session.exec(
        select(WechatLoginRequest)
        .where(WechatLoginRequest.openid == openid)
        .order_by(WechatLoginRequest.requested_at.desc())
    ).first()


def _frontend_wechat_redirect(status: str, *, token: str = "", request_id: int | None = None) -> RedirectResponse:
    params: dict[str, str] = {"wechat_status": status}
    if token:
        params["wechat_token"] = token
    if request_id is not None:
        params["request_id"] = str(request_id)
    return RedirectResponse(url=f"/login.html?{urlencode(params)}")


def _create_auth_session_for_user(session: Session, user: User) -> str:
    token = create_token()
    for attempt in range(2):
        session.add(AuthSession(user_id=user.id or 0, token=token))
        try:
            session.commit()
            return token
        except OperationalError as exc:
            session.rollback()
            if "database is locked" not in str(exc).lower() or attempt:
                raise
            sleep(0.25)
    raise RuntimeError("Unable to create an authentication session")


def wechat_login_public_config(session: Session = Depends(get_session)) -> WechatLoginPublicConfig:
    config = _active_wechat_config(session)
    enabled = bool(config and config.app_id and config.app_secret and config.redirect_uri)
    return WechatLoginPublicConfig(enabled=enabled, app_id=config.app_id if enabled and config else "")


def start_wechat_login(session: Session = Depends(get_session)) -> RedirectResponse:
    config = _active_wechat_config(session)
    if config is None or not config.app_id or not config.app_secret or not config.redirect_uri:
        raise HTTPException(status_code=400, detail="微信扫码登录未配置。")
    state = create_wechat_state(config.app_secret)
    return RedirectResponse(url=build_wechat_qr_url(config, state))


async def wechat_login_callback(
    code: str,
    state: str,
    session: Session = Depends(get_session),
) -> RedirectResponse:
    config = _active_wechat_config(session)
    if config is None or not config.app_secret:
        return _frontend_wechat_redirect("error")
    state_nonce = verify_wechat_state(state, config.app_secret)
    info = await WechatOAuthClient().fetch_user_info(config, code)
    identity = _find_wechat_identity(session, info.openid, info.unionid)
    if identity is not None:
        user = session.get(User, identity.user_id)
        if identity.is_active and user is not None and user.is_active:
            identity.nickname = info.nickname or identity.nickname
            identity.avatar_url = info.avatar_url or identity.avatar_url
            identity.last_login_at = datetime.utcnow()
            session.add(identity)
            token = _create_auth_session_for_user(session, user)
            return _frontend_wechat_redirect("success", token=token)
        return _frontend_wechat_redirect("disabled")

    existing_request = _find_wechat_request(session, info.openid)
    if existing_request is not None and existing_request.status == WechatLoginStatus.rejected:
        return _frontend_wechat_redirect("rejected", request_id=existing_request.id)
    if existing_request is None or existing_request.status != WechatLoginStatus.pending:
        existing_request = WechatLoginRequest(openid=info.openid)
    existing_request.unionid = info.unionid
    existing_request.nickname = info.nickname
    existing_request.avatar_url = info.avatar_url
    existing_request.status = WechatLoginStatus.pending
    existing_request.state_nonce = state_nonce
    session.add(existing_request)
    session.commit()
    session.refresh(existing_request)
    return _frontend_wechat_redirect("pending", request_id=existing_request.id)


def get_wechat_login_config(
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> WechatLoginConfigPublic:
    return _wechat_config_public(_active_wechat_config(session))


def save_wechat_login_config(
    payload: WechatLoginConfigUpdate,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> WechatLoginConfigPublic:
    config = _active_wechat_config(session) or session.exec(select(WechatLoginConfig).order_by(WechatLoginConfig.updated_at.desc())).first()
    app_id = payload.app_id.strip()
    app_secret = (payload.app_secret or "").strip()
    redirect_uri = payload.redirect_uri.strip() or "https://media.tech-ark.com/api/auth/wechat/callback"
    if not app_id:
        raise HTTPException(status_code=400, detail="请填写微信开放平台 AppID。")
    if config is None and not app_secret:
        raise HTTPException(status_code=400, detail="首次配置微信登录必须填写 AppSecret。")
    if payload.is_active:
        for item in session.exec(select(WechatLoginConfig)).all():
            item.is_active = False
            session.add(item)
    if config is None:
        config = WechatLoginConfig(
            app_id=app_id,
            app_secret=app_secret,
            redirect_uri=redirect_uri,
            is_active=payload.is_active,
            default_role=payload.default_role,
        )
    else:
        config.app_id = app_id
        if app_secret:
            config.app_secret = app_secret
        config.redirect_uri = redirect_uri
        config.is_active = payload.is_active
        config.default_role = payload.default_role
        config.updated_at = datetime.utcnow()
    session.add(config)
    session.commit()
    session.refresh(config)
    return _wechat_config_public(config)


def list_wechat_login_requests(
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> list[WechatLoginRequestPublic]:
    rows = session.exec(select(WechatLoginRequest).order_by(WechatLoginRequest.requested_at.desc())).all()
    status_rank = {
        WechatLoginStatus.pending: 0,
        WechatLoginStatus.approved: 1,
        WechatLoginStatus.rejected: 2,
    }
    rows = sorted(rows, key=lambda item: (status_rank.get(item.status, 9), -item.requested_at.timestamp()))
    return [_wechat_request_public(item) for item in rows]


def approve_wechat_login_request(
    request_id: int,
    payload: WechatLoginApproveRequest,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> WechatLoginRequestPublic:
    item = session.get(WechatLoginRequest, request_id)
    if item is None:
        raise HTTPException(status_code=404, detail="微信登录申请不存在。")
    if item.status != WechatLoginStatus.pending:
        raise HTTPException(status_code=400, detail="只能批准待处理的微信登录申请。")
    if payload.mode == "bind_existing":
        if payload.user_id is None:
            raise HTTPException(status_code=400, detail="请选择要绑定的系统用户。")
        target_user = session.get(User, payload.user_id)
        if target_user is None:
            raise HTTPException(status_code=404, detail="系统用户不存在。")
    else:
        username = (payload.username or "").strip()
        if not username:
            raise HTTPException(status_code=400, detail="新建用户需要填写用户名。")
        existing_user = session.exec(select(User).where(User.username == username)).first()
        if existing_user is not None:
            raise HTTPException(status_code=400, detail="用户名已存在。")
        target_user = User(
            username=username,
            password_hash=hash_password(random_temporary_password()),
            role=payload.role,
            is_active=True,
        )
        session.add(target_user)
        session.commit()
        session.refresh(target_user)

    existing_identity = _find_wechat_identity(session, item.openid, item.unionid)
    if existing_identity is None:
        existing_identity = WechatIdentity(openid=item.openid, user_id=target_user.id or 0)
    existing_identity.user_id = target_user.id or 0
    existing_identity.unionid = item.unionid
    existing_identity.nickname = item.nickname
    existing_identity.avatar_url = item.avatar_url
    existing_identity.is_active = True
    session.add(existing_identity)

    item.status = WechatLoginStatus.approved
    item.reviewed_at = datetime.utcnow()
    item.reviewed_by_user_id = admin.id
    item.target_user_id = target_user.id
    session.add(item)
    session.commit()
    session.refresh(item)
    return _wechat_request_public(item)


def reject_wechat_login_request(
    request_id: int,
    payload: WechatLoginRejectRequest,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> WechatLoginRequestPublic:
    item = session.get(WechatLoginRequest, request_id)
    if item is None:
        raise HTTPException(status_code=404, detail="微信登录申请不存在。")
    item.status = WechatLoginStatus.rejected
    item.reject_reason = payload.reason.strip()
    item.reviewed_at = datetime.utcnow()
    item.reviewed_by_user_id = admin.id
    session.add(item)
    session.commit()
    session.refresh(item)
    return _wechat_request_public(item)


def list_wechat_identities(
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> list[WechatIdentityPublic]:
    rows = session.exec(select(WechatIdentity).order_by(WechatIdentity.bound_at.desc())).all()
    return [_wechat_identity_public(item, session) for item in rows]


def disable_wechat_identity(
    identity_id: int,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> WechatIdentityPublic:
    identity = session.get(WechatIdentity, identity_id)
    if identity is None:
        raise HTTPException(status_code=404, detail="微信绑定不存在。")
    identity.is_active = False
    session.add(identity)
    session.commit()
    session.refresh(identity)
    return _wechat_identity_public(identity, session)
