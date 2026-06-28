from __future__ import annotations

from pathlib import Path
import json
from typing import Any
from uuid import uuid4

import httpx

from app.core.config import get_settings
from app.core.storage import get_storage_root
from app.models.entities import Script, VideoTask


class ProfessionalRenderClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def enabled(self) -> bool:
        provider = (self.settings.composition_provider or "").lower()
        return provider == "remotion" and bool(self.settings.remotion_render_api_base)

    async def render_task(self, task: VideoTask, script: Script, source_video_path: str | None) -> str | None:
        if not self.enabled():
            return None
        source_path = self._local_path(source_video_path)
        if source_path is None:
            return None
        output_dir = get_storage_root() / "composition" / "remotion" / f"task-{task.id or uuid4().hex}"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "professional-video.mp4"
        payload = {
            "task_id": task.id,
            "template": self.settings.remotion_render_template or "business_talking",
            "source_video_path": str(source_path),
            "output_path": str(output_path),
            "width": task.export_width,
            "height": task.export_height,
            "duration_seconds": script.duration_seconds,
            "title": self._script_title(script),
            "hook": script.hook,
            "voiceover": script.voiceover,
            "brand_name": "TECHARK",
            "scenes": self._storyboard_scenes(script),
        }
        async with httpx.AsyncClient(timeout=900, trust_env=False) as client:
            response = await client.post(
                self.settings.remotion_render_api_base.rstrip("/") + "/render",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        rendered = self._local_path(str(data.get("output_path") or output_path))
        if rendered is None:
            raise RuntimeError("Remotion 渲染完成但没有生成可用视频文件")
        return str(rendered)

    def _local_path(self, value: str | None) -> Path | None:
        if not value or value.startswith(("mock://", "http://", "https://")):
            return None
        path = Path(value)
        candidates = [path]
        if not path.is_absolute():
            candidates.extend([Path.cwd() / path, Path("/app") / path])
        workspace_backend = "/Users/Admin/Documents/Codex/2026-06-19/r/outputs/new-media-ai-platform/backend"
        if value.startswith(workspace_backend):
            candidates.append(Path(value.replace(workspace_backend, "/app")))
            candidates.append(Path(value.replace(workspace_backend, "/opt/new-media-ai-platform/backend")))
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    def _script_title(self, script: Script) -> str:
        for line in (script.title_options or "").splitlines():
            title = line.strip().lstrip("0123456789.、 ")
            if title:
                return title[:64]
        return (script.hook or "专业讲解视频")[:64]

    def _storyboard_scenes(self, script: Script) -> list[dict[str, Any]]:
        raw = script.storyboard_plan
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [item for item in parsed if isinstance(item, dict)][:24]
            except json.JSONDecodeError:
                pass
        scenes = []
        for index, line in enumerate((script.storyboard or "").splitlines()):
            text = line.strip()
            if not text:
                continue
            scenes.append(
                {
                    "title": f"镜头 {index + 1}",
                    "screen_text": text[:18],
                    "visual": text,
                    "shot_type": "storyboard",
                }
            )
        return scenes[:24]
