from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

db_file = tempfile.NamedTemporaryFile(prefix="new-media-modules-", suffix=".db", delete=False)
db_file.close()
storage_dir = tempfile.mkdtemp(prefix="new-media-modules-storage-")
os.environ["DATABASE_URL"] = f"sqlite:///{db_file.name}"
os.environ["STORAGE_DIR"] = storage_dir
os.environ["AUTH_SESSION_TTL_HOURS"] = "12"

from fastapi.routing import APIRoute  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.module_registry import API_MODULES  # noqa: E402
from app.main import app  # noqa: E402


def route_tag(path: str) -> str:
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == f"/api{path}":
            return str(route.tags[0])
    raise AssertionError(f"missing route: {path}")


def main() -> None:
    assert len(API_MODULES) >= 5
    assert route_tag("/materials") == "参考视频学习"
    assert route_tag("/scripts/generate") == "脚本方向创作"
    assert route_tag("/digital-humans") == "素材库与数字人"
    assert route_tag("/video-tasks") == "视频库与生成任务"
    assert route_tag("/publish-records") == "账号绑定与自动发布"

    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123456"})
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['token']}"}
        manifest = client.get("/api/product-modules", headers=headers)
        assert manifest.status_code == 200, manifest.text
        body = manifest.json()
        assert len(body["modules"]) >= 5
        assert len(body["api_modules"]) >= 5

    print("module router smoke ok")


if __name__ == "__main__":
    main()
