from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from html import escape
import json
from typing import Optional
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

import httpx
from fastapi import Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select

from app.api.access import _assign_owner, _ensure_record_access, _owned_statement, _require_write_user
from app.api.material_support import _optional_form_id, _save_uploaded_material
from app.api.system_models import _active_volcengine_jimeng_credential
from app.core.auth import current_user
from app.core.db import get_session
from app.models.entities import DigitalHuman, Material, MaterialKind, PlatformCredential, User, VideoTask
from app.schemas.requests import DigitalHumanCreate, VolcenginePortraitAssetBind, VolcenginePortraitAuthSessionCreate


def _credential_note_value(credential: PlatformCredential | None, key: str) -> str | None:
    if credential is None:
        return None
    prefix = f"{key}="
    for line in (credential.notes or "").splitlines():
        clean = line.strip()
        if clean.startswith(prefix):
            return clean.removeprefix(prefix).strip() or None
    return None


def _append_query_param(url: str, key: str, value: str) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query[key] = value
    return urlunparse(parsed._replace(query=urlencode(query)))


def _volcengine_canonical_query(query: dict[str, str]) -> str:
    items = []
    for key in sorted(query):
        value = query[key]
        items.append(f"{quote(str(key), safe='-_.~')}={quote(str(value), safe='-_.~')}")
    return "&".join(items)


def _volcengine_signing_key(secret_key: str, short_date: str, region: str, service: str) -> bytes:
    date_key = hmac.new(secret_key.encode("utf-8"), short_date.encode("utf-8"), hashlib.sha256).digest()
    region_key = hmac.new(date_key, region.encode("utf-8"), hashlib.sha256).digest()
    service_key = hmac.new(region_key, service.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(service_key, b"request", hashlib.sha256).digest()


def _volcengine_signed_headers(
    api_base: str,
    query: dict[str, str],
    body: str,
    access_key: str,
    secret_key: str,
    *,
    region: str,
    service: str,
) -> dict[str, str]:
    parsed = urlparse(api_base)
    host = parsed.netloc
    path = parsed.path or "/"
    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc)
    x_date = now.strftime("%Y%m%dT%H%M%SZ")
    short_date = now.strftime("%Y%m%d")
    canonical_query = _volcengine_canonical_query(query)
    content_type = "application/json"
    signed_headers = "content-type;host;x-content-sha256;x-date"
    canonical_headers = (
        f"content-type:{content_type}\n"
        f"host:{host}\n"
        f"x-content-sha256:{body_hash}\n"
        f"x-date:{x_date}\n"
    )
    canonical_request = "\n".join(["POST", path, canonical_query, canonical_headers, signed_headers, body_hash])
    credential_scope = f"{short_date}/{region}/{service}/request"
    string_to_sign = "\n".join(
        [
            "HMAC-SHA256",
            x_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    signing_key = _volcengine_signing_key(secret_key, short_date, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "Authorization": (
            f"HMAC-SHA256 Credential={access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),
        "Content-Type": content_type,
        "Host": host,
        "X-Content-Sha256": body_hash,
        "X-Date": x_date,
    }


async def _volcengine_portrait_request(
    session: Session,
    action: str,
    payload: dict[str, object],
) -> dict[str, object]:
    credential = _active_volcengine_jimeng_credential(session)
    access_key = (getattr(credential, "client_id", "") or "").strip()
    secret_key = (getattr(credential, "client_secret", "") or "").strip()
    if not access_key or not secret_key:
        raise HTTPException(status_code=400, detail="请先在系统设置中启用火山数字人 AK/SK 凭证。")
    api_base = (
        _credential_note_value(credential, "portrait_api_base")
        or _credential_note_value(credential, "asset_api_base")
        or "https://ark.cn-beijing.volcengineapi.com"
    ).rstrip("/")
    region = _credential_note_value(credential, "portrait_region") or "cn-beijing"
    service = _credential_note_value(credential, "portrait_service") or "ark"
    version = _credential_note_value(credential, "portrait_version") or "2024-01-01"
    query = {"Action": action, "Version": version}
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    headers = _volcengine_signed_headers(
        api_base,
        query,
        body,
        access_key,
        secret_key,
        region=region,
        service=service,
    )
    async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
        response = await client.post(f"{api_base}?{urlencode(query)}", headers=headers, content=body)
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"火山接口返回非 JSON：HTTP {response.status_code}") from exc
    if response.status_code >= 400:
        request_id = response.headers.get("X-Tt-Logid") or response.headers.get("X-Tt-LogId") or ""
        raise HTTPException(status_code=400, detail=f"火山接口 HTTP {response.status_code}：{data} {request_id}".strip())
    metadata = data.get("ResponseMetadata") if isinstance(data, dict) else None
    error = metadata.get("Error") if isinstance(metadata, dict) else None
    if isinstance(error, dict) and error:
        request_id = metadata.get("RequestId") or metadata.get("RequestID") or ""
        message = error.get("Message") or error.get("Code") or data
        raise HTTPException(status_code=400, detail=f"火山接口 {action} 失败：{message} RequestId={request_id}".strip())
    return data


def _volcengine_result_payload(data: dict[str, object]) -> dict[str, object]:
    result = data.get("Result") or data.get("result") or data.get("Data") or data.get("data")
    if isinstance(result, dict):
        return result
    return data


def _nested_value(payload: object, keys: set[str]) -> str | None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in keys and value not in (None, ""):
                return str(value)
        for value in payload.values():
            nested = _nested_value(value, keys)
            if nested:
                return nested
    if isinstance(payload, list):
        for item in payload:
            nested = _nested_value(item, keys)
            if nested:
                return nested
    return None


def _human_portrait_auth_state(human: DigitalHuman) -> dict[str, object]:
    return {
        "digital_human_id": human.id,
        "status": human.volcengine_auth_status or "not_started",
        "auth_url": human.volcengine_auth_url,
        "byted_token": human.volcengine_byted_token,
        "result_code": human.volcengine_auth_result_code,
        "asset_group_id": human.volcengine_asset_group_id,
        "asset_group_uri": human.volcengine_asset_group_uri,
        "asset_uri": human.volcengine_asset_uri,
        "asset_status": human.volcengine_asset_status,
    }


async def _sync_volcengine_portrait_auth_result(session: Session, human: DigitalHuman) -> dict[str, object]:
    token = (human.volcengine_byted_token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="这个数字人还没有 BytedToken，请先创建 H5 认证链接。")
    data = await _volcengine_portrait_request(session, "GetVisualValidateResult", {"BytedToken": token})
    result = _volcengine_result_payload(data)
    result_code = _nested_value(result, {"ResultCode", "resultCode", "Code", "code"})
    group_id = _nested_value(result, {"GroupId", "groupId", "AssetGroupId", "assetGroupId", "asset_group_id"})
    group_uri = _nested_value(result, {"GroupUri", "groupUri", "AssetGroupUri", "assetGroupUri", "asset_group_uri"})
    human.volcengine_auth_result_code = result_code or human.volcengine_auth_result_code
    human.volcengine_asset_group_id = group_id or human.volcengine_asset_group_id
    human.volcengine_asset_group_uri = group_uri or human.volcengine_asset_group_uri
    if group_id or group_uri or result_code == "10000":
        human.volcengine_auth_status = "active"
    elif result_code:
        human.volcengine_auth_status = "failed"
    human.volcengine_auth_payload = json.dumps(result, ensure_ascii=False)[:4000]
    session.add(human)
    session.commit()
    session.refresh(human)
    return _human_portrait_auth_state(human)


def create_digital_human(
    payload: DigitalHumanCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> DigitalHuman:
    _require_write_user(user)
    if payload.portrait_material_id is not None:
        portrait_material = session.get(Material, payload.portrait_material_id)
        _ensure_record_access(portrait_material, user, "Portrait material")
    if payload.source_video_material_id is not None:
        source_material = session.get(Material, payload.source_video_material_id)
        _ensure_record_access(source_material, user, "Source video material")
        if source_material.kind not in (MaterialKind.avatar_source, MaterialKind.video):
            raise HTTPException(status_code=400, detail="Source video material must be a video source")
    human = DigitalHuman.model_validate(payload)
    _assign_owner(human, user)
    session.add(human)
    session.commit()
    session.refresh(human)
    return human


async def create_digital_human_with_assets(
    name: str = Form(...),
    role: Optional[str] = Form(default=None),
    style: str = Form(default="realistic"),
    authorization_scope: str = Form(default="internal_marketing"),
    default_voice: Optional[str] = Form(default=None),
    portrait_material_id: Optional[str] = Form(default=None),
    source_video_material_id: Optional[str] = Form(default=None),
    portrait_file: Optional[UploadFile] = File(default=None),
    source_video_file: Optional[UploadFile] = File(default=None),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> DigitalHuman:
    _require_write_user(user)
    portrait_id = _optional_form_id(portrait_material_id, "头像素材 ID")
    source_video_id = _optional_form_id(source_video_material_id, "口播源视频素材 ID")
    if portrait_id is not None:
        portrait = session.get(Material, portrait_id)
        _ensure_record_access(portrait, user, "Portrait material")
    if source_video_id is not None:
        source_video = session.get(Material, source_video_id)
        _ensure_record_access(source_video, user, "Source video material")

    if portrait_file is not None and portrait_file.filename:
        portrait = await _save_uploaded_material(
            file=portrait_file,
            kind=MaterialKind.portrait,
            name=f"{name}头像",
            tags="digital-human,portrait",
            session=session,
            owner=user,
        )
        portrait_id = portrait.id

    if source_video_file is not None and source_video_file.filename:
        source_video = await _save_uploaded_material(
            file=source_video_file,
            kind=MaterialKind.avatar_source,
            name=f"{name}口播源视频",
            tags="digital-human,voice-source",
            session=session,
            owner=user,
        )
        source_video_id = source_video.id

    payload = DigitalHumanCreate(
        name=name,
        role=role,
        style=style,
        portrait_material_id=portrait_id,
        source_video_material_id=source_video_id,
        default_voice=default_voice,
        authorization_scope=authorization_scope,
    )
    return create_digital_human(payload, session, user)


def list_digital_humans(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[DigitalHuman]:
    statement = _owned_statement(select(DigitalHuman).order_by(DigitalHuman.created_at.desc()), DigitalHuman, user)
    return list(session.exec(statement).all())


async def create_volcengine_portrait_auth_session(
    human_id: int,
    payload: VolcenginePortraitAuthSessionCreate,
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict[str, object]:
    human = session.get(DigitalHuman, human_id)
    _ensure_record_access(human, user, "Digital human", write=True)
    callback_url = (payload.callback_url or str(request.url_for("volcengine_portrait_auth_callback"))).strip()
    callback_url = _append_query_param(callback_url, "human_id", str(human_id))
    request_payload = {
        "CallbackURL": callback_url,
        "ProjectName": "default",
    }
    if payload.subject_name:
        request_payload["SubjectName"] = payload.subject_name.strip()
    if payload.remark:
        request_payload["Remark"] = payload.remark
    data = await _volcengine_portrait_request(session, "CreateVisualValidateSession", request_payload)
    result = _volcengine_result_payload(data)
    auth_url = _nested_value(
        result,
        {
            "H5Link",
            "h5Link",
            "h5_link",
            "H5Url",
            "H5URL",
            "h5Url",
            "h5_url",
            "AuthURL",
            "AuthUrl",
            "authUrl",
            "Url",
            "url",
            "ValidateUrl",
        },
    )
    byted_token = _nested_value(result, {"BytedToken", "bytedToken", "byted_token", "Token", "token"})
    if not auth_url or not byted_token:
        raise HTTPException(status_code=400, detail=f"火山未返回 H5 认证链接或 BytedToken：{result}")
    human.volcengine_auth_status = "pending"
    human.volcengine_auth_url = auth_url
    human.volcengine_byted_token = byted_token
    human.volcengine_auth_result_code = None
    human.volcengine_auth_payload = json.dumps(result, ensure_ascii=False)[:4000]
    session.add(human)
    session.commit()
    session.refresh(human)
    return _human_portrait_auth_state(human)


def bind_volcengine_portrait_asset(
    human_id: int,
    payload: VolcenginePortraitAssetBind,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> DigitalHuman:
    human = session.get(DigitalHuman, human_id)
    _ensure_record_access(human, user, "Digital human", write=True)
    group_id = (payload.asset_group_id or "").strip() or None
    group_uri = (payload.asset_group_uri or "").strip() or None
    asset_uri = (payload.asset_uri or "").strip() or None
    if not group_id and not group_uri:
        raise HTTPException(status_code=400, detail="请填写方舟控制台中的 Asset Group ID 或 Asset Group URI。")
    human.volcengine_asset_group_id = group_id
    human.volcengine_asset_group_uri = group_uri
    human.volcengine_asset_uri = asset_uri
    human.volcengine_auth_status = "active"
    human.volcengine_auth_result_code = "manual_console"
    human.volcengine_auth_payload = "控制台人工授权后手动绑定"
    session.add(human)
    session.commit()
    session.refresh(human)
    return human


async def sync_volcengine_portrait_auth_session(
    human_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict[str, object]:
    human = session.get(DigitalHuman, human_id)
    _ensure_record_access(human, user, "Digital human", write=True)
    return await _sync_volcengine_portrait_auth_result(session, human)


def get_volcengine_portrait_auth_status(
    human_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict[str, object]:
    human = session.get(DigitalHuman, human_id)
    _ensure_record_access(human, user, "Digital human")
    return _human_portrait_auth_state(human)


async def volcengine_portrait_auth_callback(
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    params = dict(request.query_params)
    human_id = int(str(params.get("human_id") or "0") or 0)
    human = session.get(DigitalHuman, human_id) if human_id else None
    result_code = str(params.get("resultCode") or params.get("ResultCode") or "")
    detail = "未找到对应数字人，请回到系统详情页手动同步。"
    status = "failed"
    if human is not None:
        token = str(params.get("BytedToken") or params.get("bytedToken") or params.get("byted_token") or "")
        if token and human.volcengine_byted_token and token != human.volcengine_byted_token:
            detail = "回调 Token 与数字人记录不一致，请回到系统详情页重新创建认证链接。"
        else:
            human.volcengine_auth_result_code = result_code or human.volcengine_auth_result_code
            human.volcengine_auth_payload = json.dumps(params, ensure_ascii=False)[:4000]
            human.volcengine_auth_status = "callback_received" if result_code == "10000" else "failed"
            session.add(human)
            session.commit()
            session.refresh(human)
            if result_code == "10000":
                try:
                    state = await _sync_volcengine_portrait_auth_result(session, human)
                    status = str(state.get("status") or "active")
                    detail = "认证已完成，系统已同步真人 Asset Group。"
                except HTTPException as exc:
                    status = "callback_received"
                    detail = f"认证已完成，但自动同步 Asset Group 失败：{exc.detail}"
            else:
                detail = f"真人认证未通过或已取消，resultCode={result_code or '-'}。"
    html = f"""
    <!doctype html>
    <html lang="zh-CN">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>火山真人认证结果</title>
        <style>
          body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f8fafc; color: #111827; }}
          main {{ max-width: 620px; margin: 12vh auto; padding: 28px; background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }}
          h1 {{ margin: 0 0 12px; font-size: 24px; }}
          p {{ line-height: 1.7; color: #4b5563; }}
          a {{ color: #2563eb; font-weight: 700; }}
        </style>
      </head>
      <body>
        <main>
          <h1>火山真人认证结果</h1>
          <p>状态：{escape(status)}</p>
          <p>{escape(detail)}</p>
          <p><a href="/">返回系统</a></p>
        </main>
      </body>
    </html>
    """
    return HTMLResponse(html)


def delete_digital_human(
    human_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict[str, object]:
    human = session.get(DigitalHuman, human_id)
    _ensure_record_access(human, user, "Digital human", write=True)
    tasks = session.exec(select(VideoTask).where(VideoTask.digital_human_id == human_id)).all()
    for task in tasks:
        task.digital_human_id = None
        session.add(task)
    session.delete(human)
    session.commit()
    return {"deleted": True, "id": human_id}
