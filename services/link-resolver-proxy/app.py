from __future__ import annotations

import os
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel


class ResolveRequest(BaseModel):
    url: Optional[str] = None
    source_url: Optional[str] = None
    share_url: Optional[str] = None
    platform: Optional[str] = None


app = FastAPI(title="Short Video Link Resolver Proxy")


def _settings() -> dict[str, str]:
    return {
        "upstream_url": os.getenv("UPSTREAM_RESOLVER_URL", "").strip(),
        "access_token": os.getenv("RESOLVER_ACCESS_TOKEN", "").strip(),
        "upstream_token": os.getenv("UPSTREAM_ACCESS_TOKEN", "").strip(),
    }


def _check_access(authorization: Optional[str], x_api_key: Optional[str]) -> None:
    token = _settings()["access_token"]
    if not token:
        return
    bearer = f"Bearer {token}"
    if authorization == bearer or x_api_key == token:
        return
    raise HTTPException(status_code=401, detail="resolver token invalid")


def _source_url(payload: ResolveRequest) -> str:
    source_url = (payload.url or payload.source_url or payload.share_url or "").strip()
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="missing valid video share url")
    return source_url


@app.get("/health")
def health() -> dict[str, object]:
    settings = _settings()
    return {
        "ok": True,
        "upstream_configured": bool(settings["upstream_url"]),
        "protected": bool(settings["access_token"]),
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
