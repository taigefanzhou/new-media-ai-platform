from __future__ import annotations

from pathlib import Path
import json
import subprocess
import wave
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

    async def render_task(
        self,
        task: VideoTask,
        script: Script,
        source_video_path: str | None,
        broll_paths: list[str] | None = None,
    ) -> str | None:
        if not self.enabled():
            return None
        source_path = self._local_path(source_video_path)
        if source_path is None:
            return None
        output_dir = get_storage_root() / "composition" / "remotion" / f"task-{task.id or uuid4().hex}"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "professional-video.mp4"
        source_duration = self._media_duration(source_path)
        duration_seconds = (
            source_duration
            if task.production_mode == "reference_clone" and source_duration > 0
            else float(script.duration_seconds or 0)
        )
        payload = {
            "task_id": task.id,
            "template": "he_yiyi_hotel" if task.production_mode == "reference_clone" else (self.settings.remotion_render_template or "business_talking"),
            "source_video_path": str(source_path),
            "output_path": str(output_path),
            "width": task.export_width,
            "height": task.export_height,
            "duration_seconds": duration_seconds,
            "fps": 25 if task.production_mode == "reference_clone" else 30,
            "title": self._script_title(script),
            "hook": script.hook,
            "voiceover": script.voiceover,
            "brand_name": "TECHARK",
            "scenes": self._storyboard_scenes(script),
            "broll_paths": [str(path) for path in (broll_paths or [])[:6]],
        }
        async with httpx.AsyncClient(timeout=1800, trust_env=False) as client:
            response = await client.post(
                self.settings.remotion_render_api_base.rstrip("/") + "/render",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        rendered = self._local_path(str(data.get("output_path") or output_path))
        if rendered is None:
            raise RuntimeError("Remotion 渲染完成但没有生成可用视频文件")
        if task.production_mode == "reference_clone":
            return self._mix_reference_audio(rendered, output_dir, duration_seconds or 71)
        return str(rendered)

    def _media_duration(self, path: Path) -> float:
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1", str(path),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return max(0.0, float(result.stdout.strip()))
        except (OSError, ValueError, subprocess.SubprocessError):
            return 0.0

    def _mix_reference_audio(self, video_path: Path, output_dir: Path, duration: float) -> str:
        """Add a quiet original music bed and short transition chimes; no third-party audio is copied."""
        import numpy as np

        sample_rate = 24000
        sample_count = max(1, int(max(3.0, duration) * sample_rate))
        timeline = np.arange(sample_count, dtype=np.float32) / sample_rate
        bed = (
            0.010 * np.sin(2 * np.pi * 146.83 * timeline)
            + 0.006 * np.sin(2 * np.pi * 220.00 * timeline)
            + 0.004 * np.sin(2 * np.pi * 293.66 * timeline)
        )
        for reference_second in (12, 22, 27, 53, 59, 68):
            start = int(min(duration - 0.1, duration * reference_second / 71) * sample_rate)
            count = min(int(0.22 * sample_rate), sample_count - start)
            if count <= 0:
                continue
            local = np.arange(count, dtype=np.float32) / sample_rate
            bed[start : start + count] += 0.035 * np.sin(2 * np.pi * 880 * local) * np.exp(-14 * local)
        bed_path = output_dir / "original-music-bed.wav"
        with wave.open(str(bed_path), "wb") as audio_file:
            audio_file.setnchannels(1)
            audio_file.setsampwidth(2)
            audio_file.setframerate(sample_rate)
            audio_file.writeframes((np.clip(bed, -0.12, 0.12) * 32767).astype("<i2").tobytes())

        mixed_path = output_dir / "he-yiyi-hotel-final.mp4"
        command = [
            "ffmpeg", "-y", "-i", str(video_path), "-i", str(bed_path),
            "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:weights='1 0.65':normalize=0[a]",
            "-map", "0:v:0", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", str(mixed_path),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=180)
        except (OSError, subprocess.SubprocessError):
            return str(video_path)
        return str(mixed_path)

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
