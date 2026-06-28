from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

db_file = tempfile.NamedTemporaryFile(prefix="new-media-release-", suffix=".db", delete=False)
db_file.close()
storage_dir = tempfile.mkdtemp(prefix="new-media-storage-")
os.environ["DATABASE_URL"] = f"sqlite:///{db_file.name}"
os.environ["STORAGE_DIR"] = storage_dir
os.environ["AUTH_SESSION_TTL_HOURS"] = "12"

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session  # noqa: E402

from app.core.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.entities import Script, TaskStatus, VideoTask  # noqa: E402


def main() -> None:
    with TestClient(app) as client:
        unauthenticated = client.get("/api/dashboard")
        assert unauthenticated.status_code == 401, unauthenticated.text

        login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123456"})
        assert login.status_code == 200, login.text
        token = login.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        dashboard = client.get("/api/dashboard", headers=headers)
        assert dashboard.status_code == 200, dashboard.text

        me = client.get("/api/auth/me", headers=headers)
        assert me.status_code == 200, me.text
        assert me.json()["username"] == "admin"
        assert me.json()["is_active"] is True

        wrong_password = client.post(
            "/api/auth/change-password",
            headers=headers,
            json={"current_password": "wrong-password", "new_password": "new-admin-password"},
        )
        assert wrong_password.status_code == 400, wrong_password.text

        changed_password = client.post(
            "/api/auth/change-password",
            headers=headers,
            json={"current_password": "admin123456", "new_password": "new-admin-password"},
        )
        assert changed_password.status_code == 200, changed_password.text

        old_login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123456"})
        assert old_login.status_code == 401, old_login.text

        with Session(engine) as session:
            script = Script(
                hook="发布验收脚本",
                voiceover="这是一条发布验收脚本。",
                storyboard="镜头一",
                seedance_prompt="business video",
                title_options="1. 发布验收标题",
                hashtags="#验收",
                compliance_notes="可发布",
            )
            session.add(script)
            session.commit()
            session.refresh(script)

            task = VideoTask(
                script_id=script.id or 0,
                status=TaskStatus.approved,
                output_path="mock://final/final-video.mp4",
            )
            session.add(task)
            session.commit()
            session.refresh(task)
            task_id = task.id

        blocked = client.post(f"/api/video-tasks/{task_id}/publish-record", headers=headers, json={"platform": "douyin"})
        assert blocked.status_code == 400, blocked.text
        assert "占位结果" in blocked.text

        real_file = Path(storage_dir) / "release-ready.mp4"
        real_file.write_bytes(b"release-smoke-video-placeholder")
        with Session(engine) as session:
            task = session.get(VideoTask, task_id)
            assert task is not None
            task.output_path = str(real_file)
            session.add(task)
            session.commit()

        ready = client.post(f"/api/video-tasks/{task_id}/publish-record", headers=headers, json={"platform": "douyin"})
        assert ready.status_code == 200, ready.text

        record_id = ready.json()["id"]
        published = client.post(f"/api/publish-records/{record_id}/mark-published", headers=headers)
        assert published.status_code == 200, published.text
        assert published.json()["publish_status"] == "published"

        logout = client.post("/api/auth/logout", headers=headers)
        assert logout.status_code == 200, logout.text
        after_logout = client.get("/api/dashboard", headers=headers)
        assert after_logout.status_code == 401, after_logout.text

    print("release smoke ok")


if __name__ == "__main__":
    main()
