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
from app.api.modules import module_routers  # noqa: E402
from app.main import app  # noqa: E402


def route_tag(path: str) -> str:
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == f"/api{path}":
            return str(route.tags[0])
    raise AssertionError(f"missing route: {path}")


def route_count(path: str, method: str | None = None) -> int:
    expected_method = method.upper() if method else None
    return sum(
        1
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path == f"/api{path}"
        and (expected_method is None or expected_method in route.methods)
    )


def main() -> None:
    routes_source = Path("app/api/routes.py").read_text()
    assert "@router." not in routes_source
    assert "router = APIRouter" not in routes_source
    for helper_name in (
        "PRODUCTION_MODES =",
        "def _estimated_video_segment_count",
        "def _build_video_task",
        "def _prepare_material_mix_segments",
        "def _ensure_video_task_can_run",
        "def login(",
        "def logout(",
        "def change_password(",
        "def require_admin(",
        "def wechat_login_public_config(",
        "def start_wechat_login(",
        "async def wechat_login_callback(",
        "def get_wechat_login_config(",
        "def save_wechat_login_config(",
        "def list_wechat_login_requests(",
        "def approve_wechat_login_request(",
        "def reject_wechat_login_request(",
        "def list_wechat_identities(",
        "def disable_wechat_identity(",
        "def list_users(",
        "def create_user(",
        "def update_user(",
        "def reset_user_password(",
        "def list_model_configs(",
        "def model_diagnostics(",
        "def model_usage_summary(",
        "def create_model_config(",
        "def update_model_config(",
        "def activate_model_config(",
        "async def test_model_config(",
        "def list_platform_credentials(",
        "def create_platform_credential(",
        "def update_platform_credential(",
        "def activate_platform_credential(",
        "def video_storage_summary(",
        "def update_video_storage(",
        "def remote_upload_settings(",
        "def update_remote_upload_settings(",
        "async def upload_material_to_remote(",
    ):
        assert helper_name not in routes_source
    for module_path in ("app/api/modules/script_creation.py", "app/api/modules/video_library.py", "app/api/modules/system.py"):
        module_source = Path(module_path).read_text()
        assert "from app.api.routes import *" not in module_source

    assert len(API_MODULES) >= 5
    assert len(module_routers) == len(API_MODULES)
    for module_router in module_routers:
        assert any(isinstance(route, APIRoute) for route in module_router.routes)
    seen: dict[tuple[str, str], int] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/"):
            continue
        for method in route.methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            key = (method, route.path)
            seen[key] = seen.get(key, 0) + 1
    duplicates = {key: count for key, count in seen.items() if count > 1}
    assert not duplicates

    assert route_tag("/materials") == "参考视频学习"
    assert route_tag("/scripts/generate") == "脚本方向创作"
    assert route_tag("/digital-humans") == "素材库与数字人"
    assert route_tag("/video-tasks") == "视频库与生成任务"
    assert route_tag("/publish-records") == "账号绑定与自动发布"
    assert route_tag("/product-modules") == "系统与认证"
    assert route_count("/product-modules") == 1
    assert route_count("/video-production-skills") == 1
    assert route_count("/video-export-profiles") == 1
    assert route_count("/materials", "GET") == 1
    assert route_count("/materials", "POST") == 1
    assert route_count("/materials/{material_id}/preview", "GET") == 1
    assert route_count("/materials/{material_id}", "DELETE") == 1

    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123456"})
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['token']}"}
        manifest = client.get("/api/product-modules", headers=headers)
        assert manifest.status_code == 200, manifest.text
        body = manifest.json()
        assert len(body["modules"]) >= 5
        assert len(body["api_modules"]) >= 5
        skills = client.get("/api/video-production-skills", headers=headers)
        assert skills.status_code == 200, skills.text
        assert skills.json()["mode"] == "built_in"
        profiles = client.get("/api/video-export-profiles", headers=headers)
        assert profiles.status_code == 200, profiles.text
        assert len(profiles.json()) >= 1
        created = client.post(
            "/api/materials",
            headers=headers,
            json={"name": "模块路由素材", "kind": "image", "copyright_status": "owned"},
        )
        assert created.status_code == 200, created.text
        material_id = created.json()["id"]
        materials = client.get("/api/materials", headers=headers)
        assert materials.status_code == 200, materials.text
        assert any(item["id"] == material_id for item in materials.json())
        deleted = client.delete(f"/api/materials/{material_id}", headers=headers)
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["deleted"] is True

    print("module router smoke ok")


if __name__ == "__main__":
    main()
