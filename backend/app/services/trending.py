from __future__ import annotations

from typing import Any, Optional
import httpx
from app.core.config import get_settings
from app.models.entities import PlatformCredential, TrendingSearch, TrendingVideo


class TrendingCollector:
    def __init__(self, credential: Optional[PlatformCredential] = None) -> None:
        self.settings = get_settings()
        self.credential = credential

    async def collect(self, search: TrendingSearch) -> list[TrendingVideo]:
        if self.credential and self.credential.api_base:
            return await self._collect_credential_http_json(search)
        if self.settings.trending_search_provider == "http-json" and self.settings.trending_search_api_base:
            return await self._collect_http_json(search)
        return self._collect_mock(search)

    async def _collect_credential_http_json(self, search: TrendingSearch) -> list[TrendingVideo]:
        headers = {}
        if self.credential:
            token = self.credential.access_token or self.credential.client_secret
            if token:
                headers["Authorization"] = f"Bearer {token}"

        payload = {
            "platform": search.platform,
            "keyword": search.keyword,
            "category": search.category,
            "limit": 20,
        }
        url = (self.credential.api_base or "").rstrip("/") + "/trending/search"
        async with httpx.AsyncClient(timeout=60) as client:
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
            "platform": search.platform,
            "keyword": search.keyword,
            "category": search.category,
            "limit": 20,
        }
        url = self.settings.trending_search_api_base.rstrip("/") + "/trending/search"
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        items = self._extract_items(data)
        return [self._video_from_item(search, item) for item in items]

    def _collect_mock(self, search: TrendingSearch) -> list[TrendingVideo]:
        examples = [
            ("3秒讲清楚客户为什么不下单", "开头直接抛出反常识问题，再给出一个可执行判断标准。"),
            ("老板最关心的短视频获客闭环", "用痛点、流程、结果三段式拆解，适合企业服务账号复用。"),
            ("数字人不是替代员工，而是放大内容产能", "先化解误区，再展示团队如何用数字人稳定生产内容。"),
        ]
        videos = []
        for index, (title, summary) in enumerate(examples, start=1):
            videos.append(
                TrendingVideo(
                    search_id=search.id,
                    platform=search.platform,
                    title=f"{search.keyword}｜{title}",
                    source_url=f"mock://{search.platform}/trending/{search.id}/{index}",
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
        for key in ("items", "videos", "data", "results", "list"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = self._extract_items(value)
                if nested:
                    return nested
        return []

    def _video_from_item(self, search: TrendingSearch, item: dict[str, Any]) -> TrendingVideo:
        return TrendingVideo(
            search_id=search.id,
            platform=search.platform,
            title=str(item.get("title") or item.get("desc") or item.get("caption") or "Untitled video"),
            source_url=str(item.get("source_url") or item.get("url") or item.get("share_url") or ""),
            author=self._optional_string(item.get("author") or item.get("nickname") or item.get("creator")),
            play_count=self._optional_int(item.get("play_count") or item.get("views") or item.get("view_count")),
            like_count=self._optional_int(item.get("like_count") or item.get("likes") or item.get("digg_count")),
            comment_count=self._optional_int(item.get("comment_count") or item.get("comments")),
            share_count=self._optional_int(item.get("share_count") or item.get("shares")),
            duration_seconds=self._optional_int(item.get("duration_seconds") or item.get("duration")),
            hook=str(item.get("hook") or ""),
            summary=str(item.get("summary") or item.get("analysis") or ""),
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
