from __future__ import annotations

import html
import re
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, quote, urljoin, urlparse

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
    diagnostic_errors: tuple[str, ...] = field(default_factory=tuple)


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
    if "bilibili.com" in host or host == "b23.tv":
        return "bilibili"
    if "youtube.com" in host or host == "youtu.be":
        return "youtube"
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
        diagnostics: list[str] = []
        direct = self._direct_media_resolution(source_url, platform)
        if direct.media_url:
            return direct

        metadata = await self._resolve_from_public_page(source_url, platform)
        if metadata.media_url:
            return metadata
        diagnostics.extend(metadata.diagnostic_errors)

        configured_credentials = list(credentials)
        for credential in configured_credentials:
            resolved = await self._resolve_with_credential(source_url, platform, credential)
            if not resolved:
                continue
            if resolved.media_url:
                return resolved
            diagnostics.extend(resolved.diagnostic_errors)

        if configured_credentials and diagnostics:
            message = "链接解析服务不可用或没有返回视频地址：" + "；".join(diagnostics[:3])
        elif configured_credentials:
            message = "已调用链接解析服务，但没有返回可下载视频地址。"
        else:
            message = "这个分享链接没有解析出可下载视频，需要配置链接解析服务或上传源文件。"
        return LinkResolution(
            original_url=source_url,
            platform=platform,
            canonical_url=source_url,
            resolver_name="link-only",
            needs_manual_upload=True,
            message=message,
            diagnostic_errors=tuple(diagnostics),
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
        except Exception as exc:
            return LinkResolution(
                original_url=source_url,
                platform=platform,
                resolver_name="public-page",
                diagnostic_errors=(f"公开页读取失败：{self._short_error(exc)}",),
            )

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
        provider = self._note_value(credential.notes, "provider").lower()
        if provider in {"yuanbao", "yuanbao-wechat", "yuanbao_wechat"}:
            return await self._resolve_with_yuanbao(source_url, platform, credential)

        endpoints = self._credential_endpoints(credential)
        if not endpoints:
            return None
        method = self._note_value(credential.notes, "method").lower()
        methods = [method] if method in {"get", "post"} else ["post", "get"]
        headers = self._credential_headers(credential)
        resolver_name = credential.display_name or "external-resolver"
        payload = {
            "url": source_url,
            "source_url": source_url,
            "share_url": source_url,
            "platform": platform,
        }
        if credential.client_id:
            payload["client_id"] = credential.client_id

        timeout = self._credential_timeout(credential)
        diagnostics: list[str] = []
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
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
                            diagnostics.append(f"{resolver_name} {item_method.upper()} {target_endpoint} 返回 {response.status_code}")
                            continue
                        response.raise_for_status()
                        data = response.json()
                    except Exception as exc:
                        diagnostics.append(
                            f"{resolver_name} {item_method.upper()} {target_endpoint} 失败：{self._short_error(exc)}"
                        )
                        continue
                    media_url = self._extract_media_url(data)
                    if not media_url:
                        diagnostics.append(f"{resolver_name} {item_method.upper()} {target_endpoint} 未返回视频地址")
                        continue
                    return LinkResolution(
                        original_url=source_url,
                        platform=platform,
                        media_url=media_url,
                        canonical_url=self._extract_text(data, ("canonical_url", "source_url", "share_url")) or source_url,
                        title=self._extract_text(data, ("title", "desc", "description", "caption")),
                        author=self._extract_text(data, ("author", "nickname", "user_name")),
                        resolver_name=resolver_name,
                    )
        return LinkResolution(
            original_url=source_url,
            platform=platform,
            canonical_url=source_url,
            resolver_name=resolver_name,
            needs_manual_upload=True,
            message="链接解析服务没有返回可下载视频地址。",
            diagnostic_errors=tuple(dict.fromkeys(diagnostics)),
        )

    async def _resolve_with_yuanbao(
        self,
        source_url: str,
        platform: str,
        credential: LinkResolverCredential,
    ) -> LinkResolution:
        resolver_name = credential.display_name or "系统内置解析"
        cookie = credential.access_token or credential.client_secret
        if not cookie:
            return LinkResolution(
                original_url=source_url,
                platform=platform,
                canonical_url=source_url,
                resolver_name=resolver_name,
                needs_manual_upload=True,
                message="系统内置解析尚未配置登录凭据。",
                diagnostic_errors=(f"{resolver_name} 缺少元宝登录 Cookie",),
            )

        timeout = self._credential_timeout(credential)
        browser_headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Content-Type": "application/json",
            "Origin": "https://yuanbao.tencent.com",
            "Referer": "https://yuanbao.tencent.com/chat/naQivTmsDa/cf4d0079-ed1b-4c55-a3f3-2ca1379727d1",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
            ),
            "X-Requested-With": "XMLHttpRequest",
            "X-Agentid": "naQivTmsDa/cf4d0079-ed1b-4c55-a3f3-2ca1379727d1",
            "X-Device-Id": "1921b001708100d7fa31002b9646bd0cc15a3e2e1f",
            "X-Source": "web",
            "X-Web-Third-Source": "main",
            "X-Webdriver": "0",
            "X-Webversion": "2.69.0",
            "X-Platform": "mac",
            "Cookie": cookie,
        }
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                parsed_response = await client.post(
                    "https://yuanbao.tencent.com/api/weixin/get_parse_result",
                    headers=browser_headers,
                    json={"type": "video_channel_url", "url": source_url, "scene": 1},
                )
                parsed_response.raise_for_status()
                parsed_payload = parsed_response.json()
                parsed_data = parsed_payload.get("data") if isinstance(parsed_payload, dict) else None
                if not isinstance(parsed_data, dict):
                    raise RuntimeError(self._provider_message(parsed_payload) or "元宝没有返回视频解析数据")

                playable_url = str(parsed_data.get("playable_url") or "")
                export_id, general_token = self._yuanbao_feed_credentials(playable_url)
                if not export_id or not general_token:
                    raise RuntimeError("元宝解析结果缺少视频访问凭据")

                rid = f"{int(time.time()):x}-{secrets.token_hex(4)}"
                feed_response = await client.post(
                    "https://channels.weixin.qq.com/finder-preview/api/feed/get_feed_info",
                    params={
                        "_rid": rid,
                        "_pageUrl": "https://channels.weixin.qq.com/finder-preview/pages/feed",
                    },
                    headers={
                        "Accept": "application/json, text/plain, */*",
                        "Content-Type": "application/json",
                        "Origin": "https://channels.weixin.qq.com",
                        "Referer": playable_url,
                        "User-Agent": browser_headers["User-Agent"],
                    },
                    json={"baseReq": {"generalToken": general_token}, "exportId": export_id},
                )
                feed_response.raise_for_status()
                feed_payload = feed_response.json()
        except Exception as exc:
            return LinkResolution(
                original_url=source_url,
                platform=platform,
                canonical_url=source_url,
                resolver_name=resolver_name,
                needs_manual_upload=True,
                message="系统内置视频号解析失败，请更新登录凭据后重试。",
                diagnostic_errors=(f"{resolver_name} 失败：{self._short_error(exc)}",),
            )

        err_code = str(feed_payload.get("errCode", "0")) if isinstance(feed_payload, dict) else "0"
        media_url = self._extract_media_url(feed_payload)
        if err_code not in {"0", ""} or not media_url:
            message = self._provider_message(feed_payload) or "视频号没有返回可下载视频地址"
            return LinkResolution(
                original_url=source_url,
                platform=platform,
                canonical_url=source_url,
                resolver_name=resolver_name,
                needs_manual_upload=True,
                message=message,
                diagnostic_errors=(f"{resolver_name}：{message}",),
            )

        return LinkResolution(
            original_url=source_url,
            platform=platform,
            media_url=media_url,
            canonical_url=source_url,
            title=(
                self._extract_text(feed_payload, ("description", "title", "desc", "caption"))
                or self._extract_text(parsed_data, ("desc", "description", "title"))
            ),
            author=(
                self._extract_text(feed_payload, ("nickname", "author", "user_name"))
                or self._extract_text(parsed_data, ("author", "nickname"))
            ),
            resolver_name=resolver_name,
        )

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
        parsed = urlparse(base)
        if parsed.path and parsed.path != "/":
            return [base]
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
                if isinstance(value, (str, int, float)):
                    text = str(value).strip()
                    if text:
                        return text[:160]
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

    def _provider_message(self, payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        return str(payload.get("msg") or payload.get("message") or payload.get("errMsg") or "").strip()

    def _yuanbao_feed_credentials(self, playable_url: str) -> tuple[str, str]:
        query = parse_qs(urlparse(playable_url).query)
        export_id = (query.get("eid") or [""])[0]
        general_token = (query.get("token") or [""])[0]
        return export_id, general_token

    def _credential_timeout(self, credential: LinkResolverCredential) -> httpx.Timeout:
        raw_value = self._note_value(credential.notes, "timeout")
        try:
            seconds = float(raw_value) if raw_value else min(self.timeout_seconds, 8.0)
        except ValueError:
            seconds = min(self.timeout_seconds, 8.0)
        seconds = max(3.0, min(seconds, 25.0))
        connect_seconds = min(5.0, seconds)
        return httpx.Timeout(connect=connect_seconds, read=seconds, write=connect_seconds, pool=connect_seconds)

    def _short_error(self, exc: Exception) -> str:
        text = str(exc).strip() or exc.__class__.__name__
        text = re.sub(r"\s+", " ", text)
        return text[:180]
