from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urljoin

import httpx
from app.core.config import get_settings
from app.models.entities import PlatformCredential, TrendingSearch, TrendingVideo


class TrendingCollector:
    def __init__(self, credential: Optional[PlatformCredential] = None) -> None:
        self.settings = get_settings()
        self.credential = credential

    async def collect(self, search: TrendingSearch) -> list[TrendingVideo]:
        if self.credential and self.credential.api_base:
            return self._filter_and_sort(search, await self._collect_credential_http_json(search))
        if self.settings.trending_search_provider == "http-json" and self.settings.trending_search_api_base:
            return self._filter_and_sort(search, await self._collect_http_json(search))
        return self._filter_and_sort(search, self._collect_mock(search))

    async def _collect_credential_http_json(self, search: TrendingSearch) -> list[TrendingVideo]:
        headers = {"Accept": "application/json"}
        if self.credential:
            token = self.credential.access_token or self.credential.client_secret
            if token:
                headers["Authorization"] = f"Bearer {token}"
                headers["X-API-Key"] = token

        payload = {
            "platform": search.platform.value if hasattr(search.platform, "value") else str(search.platform),
            "keyword": search.keyword,
            "query": search.keyword,
            "category": search.category,
            "limit": search.limit,
            "count": search.limit,
            "cursor": 0,
            "sort_type": self._sort_type(search.sort_by),
            "publish_time": "0",
            "filter_duration": "0",
            "content_type": "0",
            "search_id": "",
            "backtrace": "",
            "sort_by": search.sort_by,
            "min_like_count": search.min_like_count,
            "min_comment_count": search.min_comment_count,
        }
        url = self._credential_endpoint()
        method = self._note_value(self.credential.notes if self.credential else "", "method").lower()
        timeout = self._credential_timeout()
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            if method == "get":
                response = await client.get(url, headers=headers, params=payload)
            else:
                response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        items = self._extract_items(data)
        return [self._video_from_item(search, item) for item in items]

    async def _collect_http_json(self, search: TrendingSearch) -> list[TrendingVideo]:
        headers = {}
        if self.settings.trending_search_api_key:
            headers["Authorization"] = f"Bearer {self.settings.trending_search_api_key}"

        payload = {
            "platform": search.platform.value if hasattr(search.platform, "value") else str(search.platform),
            "keyword": search.keyword,
            "query": search.keyword,
            "category": search.category,
            "limit": search.limit,
            "count": search.limit,
            "cursor": 0,
            "sort_type": self._sort_type(search.sort_by),
            "publish_time": "0",
            "filter_duration": "0",
            "content_type": "0",
            "search_id": "",
            "backtrace": "",
            "sort_by": search.sort_by,
            "min_like_count": search.min_like_count,
            "min_comment_count": search.min_comment_count,
        }
        url = self.settings.trending_search_api_base.rstrip("/") + "/trending/search"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        items = self._extract_items(data)
        return [self._video_from_item(search, item) for item in items]

    def _collect_mock(self, search: TrendingSearch) -> list[TrendingVideo]:
        platform_value = search.platform.value if hasattr(search.platform, "value") else str(search.platform)
        examples = [
            ("3秒讲清楚客户为什么不下单", "开头直接抛出反常识问题，再给出一个可执行判断标准。"),
            ("老板最关心的短视频获客闭环", "用痛点、流程、结果三段式拆解，适合企业服务账号复用。"),
            ("数字人不是替代员工，而是放大内容产能", "先化解误区，再展示团队如何用数字人稳定生产内容。"),
        ]
        videos = []
        for index, (title, summary) in enumerate(examples[: max(1, min(search.limit, len(examples)))], start=1):
            videos.append(
                TrendingVideo(
                    search_id=search.id,
                    platform=search.platform,
                    title=f"{search.keyword}｜{title}",
                    source_url=f"mock://{platform_value}/trending/{search.id}/{index}",
                    author="mock-trend-source",
                    play_count=100000 + index * 23000,
                    like_count=8000 + index * 1200,
                    comment_count=600 + index * 80,
                    share_count=900 + index * 120,
                    duration_seconds=30 + index * 5,
                    hook=title,
                    summary=summary,
                    tags=f"{search.keyword},爆款结构,选题参考",
                )
            )
        return videos

    def _extract_items(self, data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if not isinstance(data, dict):
            return []
        for key in (
            "items",
            "videos",
            "data",
            "results",
            "list",
            "aweme_list",
            "awemes",
            "feeds",
            "records",
        ):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = self._extract_items(value)
                if nested:
                    return nested
        return []

    def _video_from_item(self, search: TrendingSearch, item: dict[str, Any]) -> TrendingVideo:
        title = self._first_text(
            item,
            "title",
            "desc",
            "description",
            "caption",
            "content",
            "share_title",
            "share_info.share_title",
            "share_info.title",
        )
        source_url = self._first_text(
            item,
            "source_url",
            "url",
            "share_url",
            "share_info.share_url",
            "web_url",
            "aweme_share_url",
            "shareUrl",
        )
        return TrendingVideo(
            search_id=search.id,
            platform=search.platform,
            title=title or "Untitled video",
            source_url=source_url,
            author=self._optional_string(
                self._first_value(item, "author", "nickname", "creator", "user", "sec_uid", "unique_id")
            ),
            play_count=self._optional_int(
                self._first_value(
                    item,
                    "play_count",
                    "views",
                    "view_count",
                    "playCount",
                    "statistics.play_count",
                    "statistics.playCount",
                )
            ),
            like_count=self._optional_int(
                self._first_value(
                    item,
                    "like_count",
                    "likes",
                    "digg_count",
                    "diggCount",
                    "statistics.digg_count",
                    "statistics.diggCount",
                )
            ),
            comment_count=self._optional_int(
                self._first_value(
                    item,
                    "comment_count",
                    "comments",
                    "commentCount",
                    "statistics.comment_count",
                    "statistics.commentCount",
                )
            ),
            share_count=self._optional_int(
                self._first_value(
                    item,
                    "share_count",
                    "shares",
                    "shareCount",
                    "statistics.share_count",
                    "statistics.shareCount",
                )
            ),
            duration_seconds=self._optional_int(
                self._first_value(item, "duration_seconds", "duration", "video.duration")
            ),
            hook=str(self._first_value(item, "hook") or ""),
            summary=str(self._first_value(item, "summary", "analysis") or ""),
            tags=self._tags(item),
            compliance_notes="来自配置的数据源，仅作为选题和结构参考；发布前需确认授权与平台规则。",
        )

    def _optional_int(self, value: Any) -> Optional[int]:
        if value is None or value == "":
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    def _optional_string(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        return str(value)

    def _tags(self, item: dict[str, Any]) -> str:
        tags = item.get("tags") or item.get("hashtags") or ""
        if isinstance(tags, list):
            return ",".join(str(tag) for tag in tags)
        return str(tags)

    def _filter_and_sort(self, search: TrendingSearch, videos: list[TrendingVideo]) -> list[TrendingVideo]:
        filtered = [
            video
            for video in videos
            if (video.like_count or 0) >= search.min_like_count
            and (video.comment_count or 0) >= search.min_comment_count
            and video.source_url
        ]
        sort_key = (search.sort_by or "engagement").strip().lower()
        if sort_key == "likes":
            key = lambda video: video.like_count or 0
        elif sort_key == "comments":
            key = lambda video: video.comment_count or 0
        elif sort_key == "plays":
            key = lambda video: video.play_count or 0
        else:
            key = self._engagement_score
        filtered.sort(key=key, reverse=True)
        return filtered[: max(1, min(search.limit, 100))]

    def _engagement_score(self, video: TrendingVideo) -> int:
        return (
            (video.like_count or 0) * 45
            + (video.comment_count or 0) * 35
            + (video.share_count or 0) * 20
        )

    def _credential_endpoint(self) -> str:
        assert self.credential is not None
        api_base = (self.credential.api_base or "").strip()
        notes = self.credential.notes or ""
        path = self._note_value(notes, "path")
        if path:
            return urljoin(api_base.rstrip("/") + "/", path.lstrip("/"))
        if self._note_value(notes, "provider").lower() == "tikhub":
            return api_base.rstrip("/")
        if re.search(r"/(api|v\\d|trending|search)", api_base):
            return api_base.rstrip("/")
        return api_base.rstrip("/") + "/trending/search"

    def _credential_timeout(self) -> httpx.Timeout:
        raw_value = self._note_value(self.credential.notes if self.credential else "", "timeout")
        try:
            seconds = float(raw_value) if raw_value else 20.0
        except ValueError:
            seconds = 20.0
        seconds = max(5.0, min(seconds, 60.0))
        connect = min(8.0, seconds)
        return httpx.Timeout(connect=connect, read=seconds, write=connect, pool=connect)

    def _note_value(self, notes: str, key: str) -> str:
        prefix = f"{key}="
        for line in (notes or "").splitlines():
            line = line.strip()
            if line.startswith(prefix):
                return line.split("=", 1)[1].strip()
        return ""

    def _sort_type(self, sort_by: str) -> str:
        return {
            "engagement": "0",
            "likes": "0",
            "comments": "0",
            "plays": "0",
            "latest": "1",
        }.get((sort_by or "").strip().lower(), "0")

    def _first_text(self, item: dict[str, Any], *keys: str) -> str:
        value = self._first_value(item, *keys)
        if value is None:
            return ""
        return str(value).strip()

    def _first_value(self, item: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            value = self._value_by_path(item, key)
            if value not in (None, ""):
                if isinstance(value, dict):
                    nested = self._first_value(value, "nickname", "name", "title", "desc")
                    if nested:
                        return nested
                    continue
                return value
        return None

    def _value_by_path(self, item: dict[str, Any], key: str) -> Any:
        current: Any = item
        for part in key.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current
