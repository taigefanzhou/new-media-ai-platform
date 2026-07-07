from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote, urlencode

import httpx
from fastapi import HTTPException

from app.models.entities import WechatLoginConfig


WECHAT_QRCONNECT_URL = "https://open.weixin.qq.com/connect/qrconnect"
WECHAT_API_BASE = "https://api.weixin.qq.com"


@dataclass(frozen=True)
class WechatUserInfo:
    openid: str
    unionid: Optional[str] = None
    nickname: str = ""
    avatar_url: str = ""


def build_wechat_qr_url(config: WechatLoginConfig, state: str) -> str:
    params = {
        "appid": config.app_id,
        "redirect_uri": config.redirect_uri,
        "response_type": "code",
        "scope": "snsapi_login",
        "state": state,
    }
    return f"{WECHAT_QRCONNECT_URL}?{urlencode(params, quote_via=quote)}#wechat_redirect"


def create_wechat_state(secret: str, ttl_seconds: int = 600) -> str:
    issued_at = str(int(time.time()))
    nonce = secrets.token_urlsafe(16)
    payload = f"{issued_at}.{ttl_seconds}.{nonce}"
    signature = _sign_state_payload(payload, secret)
    token = f"{payload}.{signature}".encode("utf-8")
    return base64.urlsafe_b64encode(token).decode("ascii")


def verify_wechat_state(state: str, secret: str) -> str:
    try:
        decoded = base64.urlsafe_b64decode(state.encode("ascii")).decode("utf-8")
        issued_at_raw, ttl_raw, nonce, signature = decoded.split(".", 3)
        payload = f"{issued_at_raw}.{ttl_raw}.{nonce}"
        expected = _sign_state_payload(payload, secret)
        issued_at = int(issued_at_raw)
        ttl_seconds = int(ttl_raw)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="微信登录状态无效，请重新扫码。") from exc
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=400, detail="微信登录状态无效，请重新扫码。")
    if issued_at + ttl_seconds < int(time.time()):
        raise HTTPException(status_code=400, detail="微信登录状态已过期，请重新扫码。")
    return nonce


def masked_suffix(value: str | None, length: int = 6) -> str:
    if not value:
        return ""
    return value[-length:]


def random_temporary_password() -> str:
    return secrets.token_urlsafe(18)


class WechatOAuthClient:
    async def fetch_user_info(self, config: WechatLoginConfig, code: str) -> WechatUserInfo:
        fake_user = _fake_wechat_user()
        if fake_user is not None:
            return fake_user
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            token_response = await client.get(
                f"{WECHAT_API_BASE}/sns/oauth2/access_token",
                params={
                    "appid": config.app_id,
                    "secret": config.app_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                },
            )
            token_response.raise_for_status()
            token_payload = token_response.json()
            if token_payload.get("errcode"):
                raise HTTPException(status_code=400, detail=f"微信登录失败：{token_payload.get('errmsg') or '换取授权失败'}")
            access_token = str(token_payload.get("access_token") or "")
            openid = str(token_payload.get("openid") or "")
            if not access_token or not openid:
                raise HTTPException(status_code=400, detail="微信登录失败：未返回 openid。")

            user_response = await client.get(
                f"{WECHAT_API_BASE}/sns/userinfo",
                params={"access_token": access_token, "openid": openid, "lang": "zh_CN"},
            )
            user_response.raise_for_status()
            user_payload = user_response.json()
            if user_payload.get("errcode"):
                raise HTTPException(status_code=400, detail=f"微信登录失败：{user_payload.get('errmsg') or '获取用户信息失败'}")
            return WechatUserInfo(
                openid=openid,
                unionid=user_payload.get("unionid") or token_payload.get("unionid"),
                nickname=str(user_payload.get("nickname") or ""),
                avatar_url=str(user_payload.get("headimgurl") or ""),
            )


def _sign_state_payload(payload: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest


def _fake_wechat_user() -> WechatUserInfo | None:
    openid = os.getenv("WECHAT_LOGIN_FAKE_OPENID", "").strip()
    if not openid:
        return None
    return WechatUserInfo(
        openid=openid,
        unionid=os.getenv("WECHAT_LOGIN_FAKE_UNIONID", "").strip() or None,
        nickname=os.getenv("WECHAT_LOGIN_FAKE_NICKNAME", "").strip(),
        avatar_url=os.getenv("WECHAT_LOGIN_FAKE_AVATAR", "").strip(),
    )
