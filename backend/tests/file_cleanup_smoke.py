"""Smoke checks for local generated-file cleanup."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from app.services.file_cleanup import delete_local_file


def main() -> None:
    with TemporaryDirectory() as tmp:
        nested = Path(tmp) / "output" / "video.mp4"
        nested.parent.mkdir()
        nested.write_text("x", encoding="utf-8")

        delete_local_file(str(nested))

        assert not nested.exists()
        assert not nested.parent.exists()

    for remote in ("mock://video", "http://example.com/a.mp4", "https://example.com/a.mp4", None):
        delete_local_file(remote)

    print("file cleanup smoke ok")


if __name__ == "__main__":
    main()
