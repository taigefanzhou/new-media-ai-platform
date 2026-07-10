from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class VideoQualityResult:
    score: float
    status: str
    summary: str
    duration_seconds: float
    width: int
    height: int


class GeneratedVideoQualityGuard:
    """Fast local quality gate used before a generated clip enters the final edit."""

    def inspect(
        self,
        video_path: str,
        *,
        expected_duration_seconds: int | None = None,
        expected_width: int | None = None,
        expected_height: int | None = None,
    ) -> VideoQualityResult:
        path = Path(video_path)
        if not path.exists() or not path.is_file() or path.stat().st_size < 1024:
            return VideoQualityResult(0, "failed", "输出文件不存在或内容为空。", 0, 0, 0)

        metadata = self._probe(path)
        duration = float(metadata.get("duration") or 0)
        width = int(metadata.get("width") or 0)
        height = int(metadata.get("height") or 0)
        if duration <= 0 or width <= 0 or height <= 0:
            return VideoQualityResult(0, "failed", "视频元数据无效，无法读取时长或画面尺寸。", duration, width, height)

        score = 100.0
        reasons: list[str] = []
        if expected_duration_seconds and abs(duration - expected_duration_seconds) > max(3, expected_duration_seconds * 0.45):
            score -= 32
            reasons.append("时长与分镜计划偏差过大")
        if expected_width and expected_height:
            expected_ratio = expected_width / expected_height
            actual_ratio = width / height
            if abs(expected_ratio - actual_ratio) > 0.08:
                score -= 25
                reasons.append("画幅与导出规格不一致")
        if self._looks_near_black(path, duration):
            score -= 70
            reasons.append("抽帧接近黑屏或无有效画面")

        score = max(0.0, round(score, 1))
        if score >= 82:
            return VideoQualityResult(score, "passed", "基础画面、时长和规格检查通过。", duration, width, height)
        if score >= 60:
            return VideoQualityResult(score, "review", "；".join(reasons) or "存在轻微质量风险，已保留候选。", duration, width, height)
        return VideoQualityResult(score, "retry", "；".join(reasons) or "自动质检未通过。", duration, width, height)

    def _probe(self, path: Path) -> dict[str, float | int]:
        command = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height:format=duration", "-of", "json", str(path),
        ]
        try:
            completed = subprocess.run(command, check=True, capture_output=True, text=True, timeout=20)
            payload = json.loads(completed.stdout)
            stream = (payload.get("streams") or [{}])[0]
            return {
                "duration": float((payload.get("format") or {}).get("duration") or 0),
                "width": int(stream.get("width") or 0),
                "height": int(stream.get("height") or 0),
            }
        except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
            try:
                from moviepy.editor import VideoFileClip

                clip = VideoFileClip(str(path), audio=False)
                try:
                    return {"duration": float(clip.duration or 0), "width": int(clip.w or 0), "height": int(clip.h or 0)}
                finally:
                    clip.close()
            except Exception:
                return {}

    def _looks_near_black(self, path: Path, duration: float) -> bool:
        try:
            from moviepy.editor import VideoFileClip

            clip = VideoFileClip(str(path), audio=False)
            try:
                sample_times = sorted({0.0, max(0.0, duration / 2), max(0.0, duration - 0.1)})
                brightness = [float(np.asarray(clip.get_frame(time)).mean()) for time in sample_times]
                return bool(brightness) and max(brightness) < 10
            finally:
                clip.close()
        except Exception:
            return False
