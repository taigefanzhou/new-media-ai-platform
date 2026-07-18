from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.video_quality import GeneratedVideoQualityGuard


def _make_clip(path: Path, color: str, duration_seconds: int = 2, with_audio: bool = True) -> None:
    import numpy as np
    from moviepy.editor import AudioClip, ColorClip

    def tone(t):
        values = np.asarray(t)
        wave = 0.04 * np.sin(2 * np.pi * 220 * values)
        return [float(wave), float(wave)] if np.isscalar(t) else np.column_stack([wave, wave])

    audio = AudioClip(tone, duration=duration_seconds, fps=44100)
    clip = ColorClip(
        size=(320, 568),
        color={"blue": (30, 80, 220), "black": (0, 0, 0)}[color],
        duration=duration_seconds,
    )
    if with_audio:
        clip = clip.set_audio(audio)
    try:
        clip.write_videofile(str(path), fps=24, codec="libx264", audio_codec="aac", logger=None)
    finally:
        clip.close()
        audio.close()


def main() -> None:
    guard = GeneratedVideoQualityGuard()
    with tempfile.TemporaryDirectory(prefix="video-quality-") as directory:
        root = Path(directory)
        normal = root / "normal.mp4"
        black = root / "black.mp4"
        silent = root / "silent.mp4"
        _make_clip(normal, "blue")
        _make_clip(black, "black")
        _make_clip(silent, "blue", with_audio=False)

        passed = guard.inspect(str(normal), expected_duration_seconds=2, expected_width=320, expected_height=568)
        assert passed.status == "passed", passed
        assert passed.score >= 82, passed

        rejected = guard.inspect(str(black), expected_duration_seconds=2, expected_width=320, expected_height=568)
        assert rejected.status == "retry", rejected
        assert rejected.score < 60, rejected

        silent_plate = guard.inspect(
            str(silent),
            expected_duration_seconds=2,
            expected_width=320,
            expected_height=568,
            require_audio=False,
        )
        assert silent_plate.status == "passed", silent_plate

    print("video quality smoke ok")


if __name__ == "__main__":
    main()
