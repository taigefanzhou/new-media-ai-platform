from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

db_file = tempfile.NamedTemporaryFile(prefix="new-media-api-regression-", suffix=".db", delete=False)
db_file.close()
storage_dir = tempfile.mkdtemp(prefix="new-media-api-regression-storage-")
os.environ["DATABASE_URL"] = f"sqlite:///{db_file.name}"
os.environ["STORAGE_DIR"] = storage_dir
os.environ["AUTH_SESSION_TTL_HOURS"] = "12"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def login(client: TestClient, username: str, password: str) -> tuple[str, dict[str, str]]:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    token = response.json()["token"]
    return token, {"Authorization": f"Bearer {token}"}


def main() -> None:
    with TestClient(app) as client:
        admin_token, admin_headers = login(client, "admin", "admin123456")
        query_token_me = client.get(f"/api/auth/me?access_token={admin_token}")
        assert query_token_me.status_code == 200, query_token_me.text

        operator = client.post(
            "/api/settings/users",
            headers=admin_headers,
            json={"username": "operator_a", "password": "operator-a-pass", "role": "operator", "is_active": True},
        )
        assert operator.status_code == 200, operator.text
        _, operator_headers = login(client, "operator_a", "operator-a-pass")

        material = client.post(
            "/api/materials",
            headers=admin_headers,
            json={"name": "管理员素材", "kind": "image", "copyright_status": "owned", "tags": "regression"},
        )
        assert material.status_code == 200, material.text
        material_id = material.json()["id"]

        operator_materials = client.get("/api/materials", headers=operator_headers)
        assert operator_materials.status_code == 200, operator_materials.text
        assert all(item["id"] != material_id for item in operator_materials.json())
        blocked_delete = client.delete(f"/api/materials/{material_id}", headers=operator_headers)
        assert blocked_delete.status_code == 403, blocked_delete.text

        topic = client.post(
            "/api/topics",
            headers=admin_headers,
            json={"title": "回归测试选题", "industry": "酒店", "audience": "店长"},
        )
        assert topic.status_code == 200, topic.text

        script = client.post(
            "/api/scripts/generate",
            headers=admin_headers,
            json={
                "topic_id": topic.json()["id"],
                "topic": "重庆苏适酒店 10 秒介绍",
                "brand_voice": "专业、清爽、短视频口播",
                "duration_seconds": 30,
                "target_platform": "douyin",
            },
        )
        assert script.status_code == 200, script.text
        script_id = script.json()["id"]

        task = client.post(
            "/api/video-tasks",
            headers=admin_headers,
            json={"script_id": script_id, "production_mode": "seedance_scene", "subtitle_enabled": True},
        )
        assert task.status_code == 200, task.text
        assert task.json()["script_id"] == script_id
        assert task.json()["quality_status"] == "pending"
        assert task.json()["quality_score"] == 0

        incomplete_resume = client.post(f"/api/video-tasks/{task.json()['id']}/resume", headers=admin_headers)
        assert incomplete_resume.status_code == 409, incomplete_resume.text

        task_list = client.get("/api/video-tasks", headers=admin_headers)
        assert task_list.status_code == 200, task_list.text
        assert any(item["id"] == task.json()["id"] for item in task_list.json())

        operator_tasks = client.get("/api/video-tasks", headers=operator_headers)
        assert operator_tasks.status_code == 200, operator_tasks.text
        assert all(item["id"] != task.json()["id"] for item in operator_tasks.json())

    print("api regression smoke ok")


if __name__ == "__main__":
    main()
