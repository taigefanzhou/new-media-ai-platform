from __future__ import annotations

import os
import html
import re
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


class ResolveRequest(BaseModel):
    url: Optional[str] = None
    source_url: Optional[str] = None
    share_url: Optional[str] = None
    platform: Optional[str] = None


app = FastAPI(title="Short Video Link Resolver Proxy")


UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/uploads")).resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


def _settings() -> dict[str, str]:
    return {
        "provider": os.getenv("RESOLVER_PROVIDER", "generic").strip().lower(),
        "upstream_url": os.getenv("UPSTREAM_RESOLVER_URL", "").strip(),
        "access_token": os.getenv("RESOLVER_ACCESS_TOKEN", "").strip(),
        "upstream_token": os.getenv("UPSTREAM_ACCESS_TOKEN", "").strip(),
        "justone_base": os.getenv("JUSTONE_API_BASE", "http://47.117.133.51:30015").strip().rstrip("/"),
        "justone_token": (
            os.getenv("JUSTONE_API_TOKEN", "").strip()
            or os.getenv("UPSTREAM_ACCESS_TOKEN", "").strip()
        ),
        "upload_access_token": (
            os.getenv("UPLOAD_ACCESS_TOKEN", "").strip()
            or os.getenv("RESOLVER_ACCESS_TOKEN", "").strip()
        ),
        "upload_public_base_url": os.getenv("UPLOAD_PUBLIC_BASE_URL", "").strip().rstrip("/"),
    }


def _check_access(authorization: Optional[str], x_api_key: Optional[str]) -> None:
    token = _settings()["access_token"]
    if not token:
        return
    bearer = f"Bearer {token}"
    if authorization == bearer or x_api_key == token:
        return
    raise HTTPException(status_code=401, detail="resolver token invalid")


def _check_upload_access(authorization: Optional[str], x_api_key: Optional[str]) -> None:
    token = _settings()["upload_access_token"]
    if not token:
        return
    bearer = f"Bearer {token}"
    if authorization == bearer or x_api_key == token:
        return
    raise HTTPException(status_code=401, detail="upload token invalid")


def _safe_upload_name(filename: str) -> str:
    suffix = Path(filename or "upload.bin").suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,12}", suffix or ""):
        suffix = ".bin"
    return f"{uuid4().hex}{suffix}"


def _public_upload_url(request: Request, filename: str) -> str:
    public_base = _settings()["upload_public_base_url"]
    if public_base:
        return f"{public_base}/{filename}"
    return str(request.url_for("uploads", path=filename))


def _source_url(payload: ResolveRequest) -> str:
    source_url = (payload.url or payload.source_url or payload.share_url or "").strip()
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="missing valid video share url")
    return source_url


def _text_by_key(data: Any, keys: tuple[str, ...]) -> str:
    wanted = {key.lower() for key in keys}
    if isinstance(data, dict):
        for key, value in data.items():
            if key.lower() in wanted and isinstance(value, (str, int)):
                text = str(value).strip()
                if text:
                    return text
        for value in data.values():
            found = _text_by_key(value, keys)
            if found:
                return found
    if isinstance(data, list):
        for item in data:
            found = _text_by_key(item, keys)
            if found:
                return found
    return ""


def _collect_urls(value: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(value, str):
        text = html.unescape(value).replace("\\/", "/")
        if text.startswith(("http://", "https://")):
            urls.append(text)
        urls.extend(re.findall(r"https?://[^\"'<>\\\s]+", text))
    elif isinstance(value, list):
        for item in value:
            urls.extend(_collect_urls(item))
    elif isinstance(value, dict):
        preferred = (
            "download_url",
            "video_url",
            "media_url",
            "play_url",
            "url",
            "videoUrl",
            "playUrl",
            "downloadUrl",
            "h264VideoInfo",
        )
        for key in preferred:
            if key in value:
                urls.extend(_collect_urls(value[key]))
        for key, item in value.items():
            if key not in preferred:
                urls.extend(_collect_urls(item))
    return urls


def _looks_like_video_url(url: str) -> bool:
    lowered = url.lower()
    parsed = urlparse(url)
    if not parsed.netloc:
        return False
    if any(marker in lowered for marker in ("avatar", "cover", "poster", "thumbnail", ".jpg", ".jpeg", ".png", ".webp")):
        return False
    return any(marker in lowered for marker in ("mp4", "m3u8", "/video/", "play", "download", "media", "stodownload"))


def _best_video_url(data: Any) -> str:
    scored: list[tuple[int, str]] = []
    for raw_url in _collect_urls(data):
        url = raw_url.strip().rstrip("),.;")
        if not url.startswith(("http://", "https://")) or not _looks_like_video_url(url):
            continue
        score = 0
        lowered = url.lower()
        for marker in ("download", "mp4", "video", "play", "media", "m3u8"):
            if marker in lowered:
                score += 10
        scored.append((score, url))
    if not scored:
        return ""
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def _ok_or_message(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    code = str(payload.get("code", "")).strip()
    message = str(payload.get("message", "")).strip()
    if code and code not in {"0", "200", "success", "SUCCESS"}:
        return message or f"provider returned code {code}"
    return ""


async def _resolve_with_justone(source_url: str, settings: dict[str, str]) -> dict[str, Any]:
    token = settings["justone_token"]
    if not token:
        raise HTTPException(status_code=503, detail="JUSTONE_API_TOKEN or UPSTREAM_ACCESS_TOKEN not configured")

    base = settings["justone_base"] or "http://47.117.133.51:30015"
    headers = {
        "Accept": "application/json",
        "User-Agent": "new-media-ai-platform-link-resolver/1.0",
    }
    async with httpx.AsyncClient(timeout=45, follow_redirects=True, headers=headers) as client:
        basic_response = await client.get(
            f"{base}/api/weixin-channels/get-video-basic-info/v1",
            params={"token": token, "feedInfo": source_url},
        )
        basic_response.raise_for_status()
        basic_payload = basic_response.json()
        basic_error = _ok_or_message(basic_payload)
        if basic_error:
            raise HTTPException(status_code=502, detail=f"Just One basic info failed: {basic_error}")

        basic_data = basic_payload.get("data") if isinstance(basic_payload, dict) else basic_payload
        object_id = _text_by_key(basic_data, ("objectId", "object_id", "feedId", "feed_id", "id"))
        object_nonce_id = _text_by_key(basic_data, ("objectNonceId", "object_nonce_id", "nonceId", "nonce_id"))
        if not object_id:
            raise HTTPException(status_code=502, detail="Just One did not return objectId")

        download_params = {"token": token, "objectId": object_id}
        if object_nonce_id:
            download_params["objectNonceId"] = object_nonce_id
        download_response = await client.get(
            f"{base}/api/weixin-channels/get-video-download-url/v1",
            params=download_params,
        )
        download_response.raise_for_status()
        download_payload = download_response.json()
        download_error = _ok_or_message(download_payload)
        if download_error:
            raise HTTPException(status_code=502, detail=f"Just One download url failed: {download_error}")

    download_data = download_payload.get("data") if isinstance(download_payload, dict) else download_payload
    media_url = _best_video_url(download_data) or _best_video_url(download_payload)
    title = _text_by_key(basic_data, ("title", "desc", "description", "caption", "content"))
    author = _text_by_key(basic_data, ("nickname", "author", "user_name", "v2Name", "finderUsername"))
    normalized = {
        "media_url": media_url,
        "video_url": media_url,
        "download_url": media_url,
        "title": title,
        "author": author,
        "source_url": source_url,
        "objectId": object_id,
        "objectNonceId": object_nonce_id,
        "provider": "justone-wechat-channels",
        "basic_info": basic_payload,
        "download_info": download_payload,
    }
    return {
        "code": str(download_payload.get("code", "0")) if isinstance(download_payload, dict) else "0",
        "message": str(download_payload.get("message", "")) if isinstance(download_payload, dict) else "",
        "data": normalized,
        "media_url": media_url,
        "video_url": media_url,
        "download_url": media_url,
        "title": title,
        "author": author,
        "_resolver_proxy": {
            "provider": "justone-wechat-channels",
            "api_base": base,
        },
    }


@app.get("/health")
def health() -> dict[str, object]:
    settings = _settings()
    return {
        "ok": True,
        "provider": settings["provider"],
        "upstream_configured": bool(settings["upstream_url"]),
        "justone_configured": bool(settings["justone_token"]),
        "protected": bool(settings["access_token"]),
        "upload_enabled": True,
        "upload_protected": bool(settings["upload_access_token"]),
        "upload_public_base_url": settings["upload_public_base_url"],
    }


@app.post("/api/upload")
async def upload_material(
    request: Request,
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None),
) -> dict[str, object]:
    _check_upload_access(authorization, x_api_key)
    filename = _safe_upload_name(file.filename or "upload.bin")
    output_path = UPLOAD_DIR / filename
    with output_path.open("wb") as output:
        while chunk := await file.read(1024 * 1024):
            output.write(chunk)
    public_url = _public_upload_url(request, filename)
    return {
        "ok": True,
        "url": public_url,
        "source_url": public_url,
        "file_url": public_url,
        "filename": filename,
        "size_bytes": output_path.stat().st_size,
    }


@app.post("/api/fetch_video_profile")
async def fetch_video_profile(
    payload: ResolveRequest,
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    _check_access(authorization, x_api_key)
    source_url = _source_url(payload)
    settings = _settings()
    upstream_url = settings["upstream_url"]
    provider = settings["provider"]
    if provider in {"justone", "justone-wechat", "justone_wechat", "justone-wechat-channels"} or "justoneapi.com" in upstream_url or "47.117.133.51:30015" in upstream_url:
        return await _resolve_with_justone(source_url, settings)

    if not upstream_url:
        raise HTTPException(status_code=503, detail="UPSTREAM_RESOLVER_URL not configured")

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "new-media-ai-platform-link-resolver/1.0",
    }
    if settings["upstream_token"]:
        headers["Authorization"] = f"Bearer {settings['upstream_token']}"

    upstream_payload = payload.model_dump(exclude_none=True)
    upstream_payload["url"] = source_url
    try:
        async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
            response = await client.post(upstream_url, headers=headers, json=upstream_payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:400]
        raise HTTPException(status_code=502, detail=f"upstream resolver failed: {body}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"upstream resolver unavailable: {exc}") from exc

    if isinstance(data, dict):
        data.setdefault("_resolver_proxy", {"upstream": upstream_url})
        return data
    return {"data": data, "_resolver_proxy": {"upstream": upstream_url}}
