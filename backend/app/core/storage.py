from __future__ import annotations

from datetime import datetime
from pathlib import Path
from sqlmodel import Session

from app.core.config import get_settings
from app.models.entities import SystemSetting


STORAGE_ROOT_KEY = "video_storage_root"
STORAGE_SUBDIRS = ("materials", "final", "seedance", "digital-human", "voice", "composition")


def normalize_storage_root(value: str | Path) -> Path:
    raw_value = str(value).strip()
    if not raw_value:
        raise ValueError("Storage path cannot be empty")
    return Path(raw_value).expanduser().resolve()


def get_storage_root(session: Session | None = None) -> Path:
    if session is not None:
        setting = session.get(SystemSetting, STORAGE_ROOT_KEY)
        if setting and setting.value.strip():
            return normalize_storage_root(setting.value)
    return normalize_storage_root(get_settings().storage_dir)


def ensure_storage_root(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for subdir in STORAGE_SUBDIRS:
        (path / subdir).mkdir(parents=True, exist_ok=True)
    probe = path / ".write-test"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink(missing_ok=True)


def save_storage_root(session: Session, storage_root: str) -> Path:
    path = normalize_storage_root(storage_root)
    ensure_storage_root(path)
    setting = session.get(SystemSetting, STORAGE_ROOT_KEY)
    if setting is None:
        setting = SystemSetting(key=STORAGE_ROOT_KEY)
    setting.value = str(path)
    setting.updated_at = datetime.utcnow()
    session.add(setting)
    session.commit()
    session.refresh(setting)
    return path
