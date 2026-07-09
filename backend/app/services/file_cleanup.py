from __future__ import annotations

from pathlib import Path


def delete_local_file(path_value: str | None) -> None:
    if not path_value or path_value.startswith(("mock://", "http://", "https://")):
        return
    path = Path(path_value)
    if path.exists() and path.is_file():
        path.unlink()
    parent = path.parent
    try:
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
    except OSError:
        return
