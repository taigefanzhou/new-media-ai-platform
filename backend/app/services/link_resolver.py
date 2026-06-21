from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote, urljoin, urlparse

import httpx


MEDIA_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".mp3", ".m4a", ".aac", ".wav"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".svg"}


@dataclass
class LinkResolverCredential:
    platform: str
    display_name: str
    api_base: str
    client_id: str = ""
    client_secret: str = ""
    access_token: str = ""
    notes: str = ""


@dataclass
class LinkResolution:
    original_url: str
    platform: str
    media_url: str | None = None
    canonical_url: str | None = None
    title: str | None = None
    author: str | None = None
    resolver_name: str = "direct"
    needs_manual_upload: bool = False
    message: str = ""


def detect_short_video_platform(source_url: str, selected_platform: str = "auto") -> str:
    selected = (selected_platform or "").strip()
    if selected and selected not in {"auto", "manual"}:
        return selected
    host = urlparse(source_url).netloc.lower()
    if "douyin.com" in host or "iesdouyin.com" in host:
        return "douyin"
    if "weixin.qq.com" in host or "channels.weixin.qq.com" in host or "finder.video.qq.com" in host:
        return "wechat_channels"
    if "xiaohongshu.com" in host or "xhslink.com" in host:
        return "xiaohongshu"
    if "kuaishou.com" in host or "kwai" in host:
        return "kuaishou"
    return "manual"


class ShortVideoLinkResolver:
    def __init__(self, timeout_seconds: float = 18.0) -> None:
        self.timeout_seconds = timeout_seconds

    async def resolve(
        self,
        source_url: str,
        platform: str,
        credentials: Iterable[LinkResolverCredential] = (),
    ) -> LinkResolution:
        direct = self._direct_media_resolution(source_url, platform)
        if direct.media_url:
            return direct

        metadata = await self._resolve_from_public_page(source_url, platform)
        if metadata.media_url:
            return metadata

        for credential in credentials:
            resolved = await self._resolve_with_credential(source_url, platform, credential)
            if resolved and resolved.media_url:
                return resolved

        return LinkResolution(
            original_url=source_url,
            platform=platform,
            canonical_url=source_url,
            resolver_name="link-only",
            needs_manual_upload=True,
            message="这个分享链接没有解析出可下载视频，需要配置链接解析服务或上传源文件。",
        )

    def _direct_media_resolution(self, source_url: str, platform: str) -> LinkResolution:
        parsed = urlparse(source_url)
        suffix = Path(parsed.path).suffix.lower()
        is_finder_download = "finder.video.qq.com" in parsed.netloc and "stodownload" in parsed.path
        media_url = source_url if suffix in MEDIA_EXTENSIONS or is_finder_download else None
        return LinkResolution(
            original_url=source_url,
            platform=platform,
            media_url=media_url,
            canonical_url=source_url,
            resolver_name="direct-download" if media_url else "direct",
        )

    async def _resolve_from_public_page(self, source_url: str, platform: str) -> LinkResolution:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            ),
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.5",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True, headers=headers) as client:
                response = await client.get(source_url)
                response.raise_for_status()
        except Exception:
            return LinkResolution(original_url=source_url, platform=platform, resolver_name="public-page")

        content_type = response.headers.get("content-type", "")
        canonical_url = str(response.url)
        if "json" in content_type:
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            media_url = self._extract_media_url(payload)
            return LinkResolution(
                original_url=source_url,
                platform=platform,
                media_url=media_url,
                canonical_url=canonical_url,
                title=self._extract_text(payload, ("title", "desc", "description", "caption")),
                author=self._extract_text(payload, ("author", "nickname", "user_name")),
                resolver_name="public-json",
                needs_manual_upload=not bool(media_url),
            )

        body = response.text[:2_000_000]
        media_url = self._extract_media_url_from_html(body)
        title = self._extract_title_from_html(body)
        return LinkResolution(
            original_url=source_url,
            platform=platform,
            media_url=media_url,
            canonical_url=canonical_url,
            title=title,
            resolver_name="public-page",
            needs_manual_upload=not bool(media_url),
        )

    async def _resolve_with_credential(
        self,
        source_url: str,
        platform: str,
        credential: LinkResolverCredential,
    ) -> LinkResolution | None:
        endpoints = self._credential_endpoints(credential)
        method = self._note_value(credential.notes, "method").lower()
        methods = [method] if method in {"get", "post"} else ["post", "get"]
        headers = self._credential_headers(credential)
        payload = {
            "url": source_url,
            "source_url": source_url,
            "share_url": source_url,
            "platform": platform,
        }
        if credential.client_id:
            payload["client_id"] = credential.client_id

        async with httpx.AsyncClient(timeout=max(self.timeout_seconds, 25), follow_redirects=True) as client:
            for endpoint in endpoints:
                target_endpoint = endpoint.replace("{url}", quote(source_url, safe=""))
                for item_method in methods:
                    try:
                        if item_method == "post":
                            response = await client.post(target_endpoint, headers=headers, json=payload)
                        else:
                            params = {} if "{url}" in endpoint else payload
                            response = await client.get(target_endpoint, headers=headers, params=params)
                        if response.status_code in {404, 405}:
                            continue
                        response.raise_for_status()
                        data = response.json()
                    except Exception:
                        continue
                    media_url = self._extract_media_url(data)
                    if not media_url:
                        continue
                    return LinkResolution(
                        original_url=source_url,
                        platform=platform,
                        media_url=media_url,
                        canonical_url=self._extract_text(data, ("canonical_url", "source_url", "share_url")) or source_url,
                        title=self._extract_text(data, ("title", "desc", "description", "caption")),
                        author=self._extract_text(data, ("author", "nickname", "user_name")),
                        resolver_name=credential.display_name or "external-resolver",
                    )
        return None

    def _credential_endpoints(self, credential: LinkResolverCredential) -> list[str]:
        api_base = credential.api_base.strip()
        if not api_base:
            return []
        path = self._note_value(credential.notes, "path")
        if path:
            return [urljoin(api_base.rstrip("/") + "/", path.lstrip("/"))]
        if "{" in api_base and "url" in api_base:
            return [api_base]
        base = api_base.rstrip("/")
        return list(dict.fromkeys([
            base,
            f"{base}/api/resolve",
            f"{base}/api/hybrid/video_data",
            f"{base}/api/download",
        ]))

    def _credential_headers(self, credential: LinkResolverCredential) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if credential.access_token:
            headers["Authorization"] = f"Bearer {credential.access_token}"
        if credential.client_secret:
            headers["X-API-Key"] = credential.client_secret
        if credential.client_id:
            headers["X-Client-Id"] = credential.client_id
        return headers

    def _extract_media_url_from_html(self, body: str) -> str | None:
        unescaped = html.unescape(body).replace("\\/", "/")
        meta_match = re.search(
            r'<meta[^>]+(?:property|name)=["\'](?:og:video|og:video:url|twitter:player:stream)["\'][^>]+content=["\']([^"\']+)["\']',
            unescaped,
            flags=re.I,
        )
        if meta_match:
            value = html.unescape(meta_match.group(1))
            if self._looks_like_media_url(value):
                return value
        candidates = re.findall(r"https?://[^\"'<>\\\s]+", unescaped)
        return self._best_media_url(candidates)

    def _extract_title_from_html(self, body: str) -> str | None:
        unescaped = html.unescape(body)
        for pattern in (
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
            r"<title[^>]*>(.*?)</title>",
        ):
            match = re.search(pattern, unescaped, flags=re.I | re.S)
            if match:
                title = re.sub(r"\s+", " ", match.group(1)).strip()
                if title:
                    return title[:120]
        return None

    def _extract_media_url(self, data: Any) -> str | None:
        candidates = list(self._collect_urls(data))
        return self._best_media_url(candidates)

    def _collect_urls(self, value: Any) -> Iterable[str]:
        if isinstance(value, str):
            text = html.unescape(value).replace("\\/", "/")
            if text.startswith(("http://", "https://")):
                yield text
            for match in re.findall(r"https?://[^\"'<>\\\s]+", text):
                yield match
            return
        if isinstance(value, list):
            for item in value:
                yield from self._collect_urls(item)
            return
        if isinstance(value, dict):
            preferred_keys = (
                "download_url",
                "video_url",
                "media_url",
                "play_url",
                "nwm_video_url",
                "no_watermark_url",
                "url_list",
                "urls",
            )
            for key in preferred_keys:
                if key in value:
                    yield from self._collect_urls(value[key])
            for key, item in value.items():
                if key not in preferred_keys:
                    yield from self._collect_urls(item)

    def _best_media_url(self, candidates: Iterable[str]) -> str | None:
        scored = []
        for raw_url in candidates:
            url = raw_url.strip().rstrip("),.;")
            if not url.startswith(("http://", "https://")):
                continue
            if not self._looks_like_media_url(url):
                continue
            scored.append((self._media_score(url), url))
        if not scored:
            return None
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][1]

    def _looks_like_media_url(self, url: str) -> bool:
        parsed = urlparse(url)
        if not parsed.netloc:
            return False
        suffix = Path(parsed.path).suffix.lower()
        lowered = url.lower()
        if suffix in IMAGE_EXTENSIONS:
            return False
        if any(blocked in lowered for blocked in ("avatar", "cover", "poster", "thumbnail")):
            return False
        if suffix in MEDIA_EXTENSIONS:
            return True
        return any(marker in lowered for marker in ("/video/", "play", "download", "media", "mp4", "stodownload"))

    def _media_score(self, url: str) -> int:
        lowered = url.lower()
        suffix = Path(urlparse(url).path).suffix.lower()
        score = 0
        if suffix in MEDIA_EXTENSIONS:
            score += 50
        for marker in ("no_watermark", "nwm", "download", "play", "video", "mp4"):
            if marker in lowered:
                score += 8
        if "watermark" in lowered and "no_watermark" not in lowered:
            score -= 10
        return score

    def _extract_text(self, data: Any, keys: tuple[str, ...]) -> str | None:
        if isinstance(data, dict):
            for key in keys:
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()[:160]
            for value in data.values():
                found = self._extract_text(value, keys)
                if found:
                    return found
        if isinstance(data, list):
            for item in data:
                found = self._extract_text(item, keys)
                if found:
                    return found
        return None

    def _note_value(self, notes: str, key: str) -> str:
        prefix = f"{key}="
        for line in (notes or "").splitlines():
            line = line.strip()
            if line.startswith(prefix):
                return line.split("=", 1)[1].strip()
        return ""
