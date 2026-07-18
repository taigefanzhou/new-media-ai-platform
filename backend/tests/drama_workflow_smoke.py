from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

db_file = tempfile.NamedTemporaryFile(prefix="new-media-drama-", suffix=".db", delete=False)
db_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{db_file.name}"
os.environ["STORAGE_DIR"] = tempfile.mkdtemp(prefix="new-media-drama-storage-")

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.services.ai_clients import MediaGenerationClient  # noqa: E402


def main() -> None:
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123456"})
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['token']}"}
        material = client.post(
            "/api/materials",
            headers=headers,
            json={"name": "云端酒店角色首帧", "kind": "image", "copyright_status": "owned"},
        )
        assert material.status_code == 200, material.text
        project = client.post("/api/drama-projects", headers=headers, json={"title": "未来云端酒店"})
        assert project.status_code == 200, project.text
        project_id = project.json()["id"]
        seeded = client.post(f"/api/drama-projects/{project_id}/bootstrap-cloud-hotel", headers=headers)
        assert seeded.status_code == 200, seeded.text
        assert len(seeded.json()["shots"]) == 8
        shot_id = seeded.json()["shots"][0]["id"]
        updated = client.patch(f"/api/drama-shots/{shot_id}", headers=headers, json={"reference_material_id": material.json()["id"]})
        assert updated.status_code == 200, updated.text
        built = client.post(f"/api/drama-projects/{project_id}/build-video-task", headers=headers)
        assert built.status_code == 200, built.text
        plan = json.loads(built.json()["script"]["storyboard_plan"])
        assert plan[0]["reference_material_id"] == material.json()["id"]
        generated_plan = MediaGenerationClient().segment_plan("", "", 60, plan)
        assert generated_plan[0]["reference_material_id"] == material.json()["id"]
        assert built.json()["video_task"]["production_mode"] == "seedance_scene"

        action_plan = MediaGenerationClient().segment_plan(
            "",
            "0-5秒：黄丽迎面行走讲解。5-10秒：警报亮起，黄丽停步回头。",
            10,
            [
                {
                    "start_second": 0,
                    "end_second": 10,
                    "shot_type": "medium tracking shot",
                    "asset_or_background": "固定的云端安防通道和同一组三辊闸机",
                    "person_action": "行走讲解，随后回头",
                    "ai_prompt": "walk, speak, trigger alarm and look back in one shot",
                }
            ],
        )
        assert [item["duration_seconds"] for item in action_plan] == [5, 5]
        assert "黄丽迎面行走讲解" in str(action_plan[0]["prompt"])
        assert "黄丽停步回头" not in str(action_plan[0]["prompt"])
        assert "黄丽停步回头" in str(action_plan[1]["prompt"])
    print("drama workflow smoke ok")


if __name__ == "__main__":
    main()
