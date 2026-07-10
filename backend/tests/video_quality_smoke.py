from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.video_quality import GeneratedVideoQualityGuard


def _make_clip(path: Path, color: str, duration_seconds: int = 2) -> None:
    from moviepy.editor import ColorClip

    colors = {"blue": (30, 80, 220), "black": (0, 0, 0)}
    clip = ColorClip(size=(320, 568), color=colors[color], duration=duration_seconds)
    try:
        clip.write_videofile(str(path), fps=24, codec="libx264", audio=False, logger=None)
    finally:
        clip.close()


def main() -> None:
    guard = GeneratedVideoQualityGuard()
    with tempfile.TemporaryDirectory(prefix="video-quality-") as directory:
        root = Path(directory)
        normal = root / "normal.mp4"
        black = root / "black.mp4"
        _make_clip(normal, "blue")
        _make_clip(black, "black")

        passed = guard.inspect(str(normal), expected_duration_seconds=2, expected_width=320, expected_height=568)
        assert passed.status == "passed", passed
        rejected = guard.inspect(str(black), expected_duration_seconds=2, expected_width=320, expected_height=568)
        assert rejected.status == "retry", rejected

    print("video quality smoke ok")


if __name__ == "__main__":
    main()
