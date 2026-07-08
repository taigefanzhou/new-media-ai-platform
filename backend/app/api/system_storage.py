from __future__ import annotations

from datetime import datetime
from pathlib import Path

import httpx
from fastapi import Depends, HTTPException
from sqlmodel import Session, select

from app.api.access import _ensure_record_access
from app.api.publishing_support import _effective_video_output_path
from app.api.system_auth import require_admin
from app.api.system_models import _api_base_looks_valid
from app.core.auth import current_user
from app.core.config import get_settings
from app.core.db import get_session
from app.core.storage import STORAGE_ROOT_KEY, get_storage_root, save_storage_root
from app.models.entities import Material, Script, SystemSetting, User, VideoTask
from app.schemas.requests import RemoteUploadSettingsUpdate, StorageSettingsUpdate


REMOTE_UPLOAD_ENABLED_KEY = "remote_upload_enabled"
REMOTE_UPLOAD_URL_KEY = "remote_upload_url"
REMOTE_UPLOAD_PUBLIC_BASE_URL_KEY = "remote_upload_public_base_url"
REMOTE_UPLOAD_FIELD_NAME_KEY = "remote_upload_field_name"
REMOTE_UPLOAD_TOKEN_KEY = "remote_upload_token"


def video_storage_summary(
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> dict[str, object]:
    storage_root = get_storage_root(session)
    storage_setting = session.get(SystemSetting, STORAGE_ROOT_KEY)
    default_root = Path(get_settings().storage_dir).expanduser().resolve()
    shared_root = default_root.parent
    suggested_roots = [
        {
            "label": "系统默认空间",
            "description": "适合日常生成、审核和发布前准备，所有文件按类型自动归档。",
            "path": str(default_root),
        },
        {
            "label": "成片工作区",
            "description": "适合集中保存已生成的视频任务和发布前成片。",
            "path": str(shared_root / "ai-video-output"),
        },
        {
            "label": "素材工作区",
            "description": "适合集中保存采集素材、数字人口播源和中间视频。",
            "path": str(shared_root / "ai-video-assets"),
        },
    ]
    if not any(item["path"] == str(storage_root) for item in suggested_roots):
        suggested_roots.insert(
            0,
            {
                "label": "当前自定义空间",
                "description": "沿用当前已经保存的系统位置。",
                "path": str(storage_root),
            },
        )
    for item in suggested_roots:
        item["active"] = item["path"] == str(storage_root)
    active_profile = next((item for item in suggested_roots if item["active"]), suggested_roots[0])
    storage_groups = [
        {"label": "成片库", "description": "最终审核和发布使用的视频。"},
        {"label": "分段视频库", "description": "AI 生成的分镜片段和中间视频。"},
        {"label": "数字人口播库", "description": "数字人口播视频和驱动结果。"},
        {"label": "音频库", "description": "配音、声音复刻和口播音频。"},
        {"label": "素材库", "description": "上传、采集和补传到服务器的素材。"},
    ]
    tasks = session.exec(select(VideoTask).order_by(VideoTask.created_at.desc())).all()
    videos = []
    total_size = 0
    existing_count = 0
    missing_count = 0
    external_count = 0
    placeholder_count = 0
    for task in tasks:
        effective_output_path = _effective_video_output_path(task)
        if not effective_output_path:
            continue
        output_path = effective_output_path
        is_mock_path = output_path.startswith("mock://")
        is_external_path = output_path.startswith(("http://", "https://"))
        is_local_path = not is_external_path and not is_mock_path
        path = Path(output_path) if is_local_path else None
        exists = bool(path and path.exists() and path.is_file())
        size_bytes = path.stat().st_size if path and exists else 0
        total_size += size_bytes
        if is_local_path:
            existing_count += 1 if exists else 0
            missing_count += 0 if exists else 1
            storage_kind = "local"
        elif is_external_path:
            external_count += 1
            storage_kind = "external"
        else:
            placeholder_count += 1
            storage_kind = "placeholder"
        script = session.get(Script, task.script_id)
        videos.append(
            {
                "task_id": task.id,
                "script_id": task.script_id,
                "script_title": script.hook if script else f"脚本 #{task.script_id}",
                "status": task.status,
                "target_platform": task.target_platform,
                "export_profile": task.export_profile,
                "export_width": task.export_width,
                "export_height": task.export_height,
                "output_path": str(path.resolve()) if path else output_path,
                "raw_output_path": task.output_path,
                "captioned_output_path": task.captioned_output_path,
                "subtitle_status": task.subtitle_status,
                "subtitle_style": task.subtitle_style,
                "exists": exists,
                "storage_kind": storage_kind,
                "storage_label": (
                    "云端素材库"
                    if storage_kind == "external"
                    else "占位结果"
                    if storage_kind == "placeholder"
                    else "本地成片库"
                ),
                "size_bytes": size_bytes,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
            }
        )
    return {
        "storage_root": str(storage_root),
        "storage_profile_label": active_profile["label"],
        "final_video_dir": str(storage_root / "final"),
        "segment_video_dir": str(storage_root / "seedance"),
        "digital_human_dir": str(storage_root / "digital-human"),
        "voice_dir": str(storage_root / "voice"),
        "configured_by": "后台设置" if storage_setting and storage_setting.value else "STORAGE_DIR",
        "final_video_pattern": str(storage_root / "final" / "{自动生成ID}" / "final-video.mp4"),
        "suggested_roots": suggested_roots,
        "storage_groups": storage_groups,
        "totals": {
            "video_count": len(videos),
            "existing_count": existing_count,
            "missing_count": missing_count,
            "external_count": external_count,
            "placeholder_count": placeholder_count,
            "size_bytes": total_size,
        },
        "videos": videos,
    }


def update_video_storage(
    payload: StorageSettingsUpdate,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> dict[str, object]:
    try:
        save_storage_root(session, payload.storage_root)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"无法使用这个目录：{exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return video_storage_summary(session=session, admin=admin)


def remote_upload_settings(
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> dict[str, object]:
    settings = _remote_upload_settings(session)
    return {
        "enabled": settings["enabled"],
        "upload_url": settings["upload_url"],
        "public_base_url": settings["public_base_url"],
        "file_field_name": settings["file_field_name"],
        "has_upload_token": bool(settings["upload_token"]),
        "ready": bool(settings["enabled"] and settings["upload_url"]),
    }


def update_remote_upload_settings(
    payload: RemoteUploadSettingsUpdate,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> dict[str, object]:
    upload_url = (payload.upload_url or "").strip()
    public_base_url = (payload.public_base_url or "").strip()
    field_name = (payload.file_field_name or "file").strip() or "file"
    if payload.enabled and not upload_url:
        raise HTTPException(status_code=400, detail="启用素材服务器上传前，请先填写上传接口地址。")
    if upload_url and not _api_base_looks_valid(upload_url):
        raise HTTPException(status_code=400, detail="上传接口地址必须是 http 或 https 地址。")
    if public_base_url and not _api_base_looks_valid(public_base_url):
        raise HTTPException(status_code=400, detail="访问域名必须是 http 或 https 地址。")

    _save_system_setting(session, REMOTE_UPLOAD_ENABLED_KEY, "1" if payload.enabled else "0")
    _save_system_setting(session, REMOTE_UPLOAD_URL_KEY, upload_url)
    _save_system_setting(session, REMOTE_UPLOAD_PUBLIC_BASE_URL_KEY, public_base_url)
    _save_system_setting(session, REMOTE_UPLOAD_FIELD_NAME_KEY, field_name)
    if payload.clear_upload_token:
        _save_system_setting(session, REMOTE_UPLOAD_TOKEN_KEY, "")
    elif payload.upload_token:
        _save_system_setting(session, REMOTE_UPLOAD_TOKEN_KEY, payload.upload_token.strip())
    return remote_upload_settings(session=session, admin=admin)


async def upload_material_to_remote(
    material_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> Material:
    material = session.get(Material, material_id)
    _ensure_record_access(material, user, "Material", write=True)
    await _publish_material_to_remote(material, session, require_config=True)
    session.refresh(material)
    return material


def _save_system_setting(session: Session, key: str, value: str) -> SystemSetting:
    setting = session.get(SystemSetting, key)
    if setting is None:
        setting = SystemSetting(key=key)
    setting.value = value
    setting.updated_at = datetime.utcnow()
    session.add(setting)
    session.commit()
    session.refresh(setting)
    return setting


def _system_setting_value(session: Session, key: str) -> str:
    setting = session.get(SystemSetting, key)
    return setting.value.strip() if setting and setting.value else ""


def _remote_upload_settings(session: Session) -> dict[str, object]:
    return {
        "enabled": _system_setting_value(session, REMOTE_UPLOAD_ENABLED_KEY) == "1",
        "upload_url": _system_setting_value(session, REMOTE_UPLOAD_URL_KEY),
        "public_base_url": _system_setting_value(session, REMOTE_UPLOAD_PUBLIC_BASE_URL_KEY),
        "file_field_name": _system_setting_value(session, REMOTE_UPLOAD_FIELD_NAME_KEY) or "file",
        "upload_token": _system_setting_value(session, REMOTE_UPLOAD_TOKEN_KEY),
    }


async def _publish_material_to_remote(
    material: Material,
    session: Session,
    require_config: bool = False,
) -> None:
    if material.source_url and material.source_url.startswith(("http://", "https://")):
        return
    settings = _remote_upload_settings(session)
    if not settings["enabled"] or not settings["upload_url"]:
        if require_config:
            raise HTTPException(status_code=400, detail="请先在视频存储位置里配置素材服务器上传接口。")
        return
    if not material.file_path or not Path(material.file_path).exists():
        if require_config:
            raise HTTPException(status_code=400, detail="素材本地文件不存在，无法上传到服务器。")
        return

    upload_url = str(settings["upload_url"])
    field_name = str(settings["file_field_name"] or "file")
    token = str(settings["upload_token"] or "")
    path = Path(material.file_path)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with open(path, "rb") as file_obj:
        files = {field_name: (path.name, file_obj, "application/octet-stream")}
        data = {
            "material_id": str(material.id or ""),
            "name": material.name,
            "kind": material.kind.value if hasattr(material.kind, "value") else str(material.kind),
        }
        async with httpx.AsyncClient(timeout=600) as client:
            try:
                response = await client.post(upload_url, headers=headers, files=files, data=data)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                message = str(exc) or exc.__class__.__name__
                raise HTTPException(status_code=502, detail=f"素材服务器上传失败：{message}") from exc
            try:
                result = response.json()
            except ValueError:
                result = response.text
    source_url = _extract_remote_upload_url(result)
    if not source_url and settings["public_base_url"]:
        source_url = _join_public_base_url(str(settings["public_base_url"]), path.name)
    if not source_url:
        raise HTTPException(status_code=400, detail="素材服务器未返回 url/source_url/file_url 字段。")
    material.source_url = source_url
    session.add(material)
    session.commit()


def _extract_remote_upload_url(result: object) -> str:
    if isinstance(result, str):
        return result if result.startswith(("http://", "https://")) else ""
    if not isinstance(result, dict):
        return ""
    for key in ("source_url", "url", "file_url", "public_url", "download_url"):
        value = result.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    data = result.get("data")
    if isinstance(data, dict):
        return _extract_remote_upload_url(data)
    return ""


def _join_public_base_url(base_url: str, filename: str) -> str:
    return f"{base_url.rstrip('/')}/{filename.lstrip('/')}"
