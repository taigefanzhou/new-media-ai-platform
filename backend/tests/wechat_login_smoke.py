from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

db_file = tempfile.NamedTemporaryFile(prefix="new-media-wechat-", suffix=".db", delete=False)
db_file.close()
storage_dir = tempfile.mkdtemp(prefix="new-media-wechat-storage-")
os.environ["DATABASE_URL"] = f"sqlite:///{db_file.name}"
os.environ["STORAGE_DIR"] = storage_dir
os.environ["AUTH_SESSION_TTL_HOURS"] = "12"
os.environ["WECHAT_LOGIN_FAKE_OPENID"] = "openid-smoke-001"
os.environ["WECHAT_LOGIN_FAKE_UNIONID"] = "unionid-smoke-001"
os.environ["WECHAT_LOGIN_FAKE_NICKNAME"] = "扫码测试用户"
os.environ["WECHAT_LOGIN_FAKE_AVATAR"] = "https://example.com/avatar.png"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def login_admin(client: TestClient) -> dict[str, str]:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123456"})
    assert login.status_code == 200, login.text
    token = login.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def main() -> None:
    with TestClient(app) as client:
        public_config = client.get("/api/auth/wechat/config")
        assert public_config.status_code == 200, public_config.text
        assert public_config.json()["enabled"] is False

        blocked_start = client.get("/api/auth/wechat/start", follow_redirects=False)
        assert blocked_start.status_code == 400, blocked_start.text

        admin_headers = login_admin(client)
        saved_config = client.post(
            "/api/settings/wechat-login/config",
            headers=admin_headers,
            json={
                "app_id": "wx-smoke-app",
                "app_secret": "wx-smoke-secret",
                "redirect_uri": "https://media.tech-ark.com/api/auth/wechat/callback",
                "is_active": True,
                "default_role": "operator",
            },
        )
        assert saved_config.status_code == 200, saved_config.text
        assert saved_config.json()["has_app_secret"] is True
        assert "app_secret" not in saved_config.json()

        default_redirect_config = client.post(
            "/api/settings/wechat-login/config",
            headers=admin_headers,
            json={
                "app_id": "wx-smoke-app",
                "app_secret": "",
                "redirect_uri": "",
                "is_active": True,
                "default_role": "operator",
            },
        )
        assert default_redirect_config.status_code == 200, default_redirect_config.text
        assert default_redirect_config.json()["redirect_uri"] == "https://media.tech-ark.com/api/auth/wechat/callback"

        enabled_config = client.get("/api/auth/wechat/config")
        assert enabled_config.status_code == 200, enabled_config.text
        assert enabled_config.json()["enabled"] is True

        start = client.get("/api/auth/wechat/start", follow_redirects=False)
        assert start.status_code == 307, start.text
        location = start.headers["location"]
        assert location.startswith("https://open.weixin.qq.com/connect/qrconnect")
        state = parse_qs(urlparse(location).query)["state"][0]

        callback = client.get(
            f"/api/auth/wechat/callback?code=fake-code&state={state}",
            follow_redirects=False,
        )
        assert callback.status_code == 307, callback.text
        assert "wechat_status=pending" in callback.headers["location"]

        requests = client.get("/api/settings/wechat-login/requests", headers=admin_headers)
        assert requests.status_code == 200, requests.text
        pending = requests.json()
        assert len(pending) == 1
        assert pending[0]["status"] == "pending"
        assert pending[0]["nickname"] == "扫码测试用户"
        request_id = pending[0]["id"]

        approved = client.post(
            f"/api/settings/wechat-login/requests/{request_id}/approve",
            headers=admin_headers,
            json={"mode": "create_user", "username": "wechat_operator", "role": "operator"},
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"

        second_start = client.get("/api/auth/wechat/start", follow_redirects=False)
        assert second_start.status_code == 307, second_start.text
        second_state = parse_qs(urlparse(second_start.headers["location"]).query)["state"][0]
        second_callback = client.get(
            f"/api/auth/wechat/callback?code=fake-code-2&state={second_state}",
            follow_redirects=False,
        )
        assert second_callback.status_code == 307, second_callback.text
        redirect = second_callback.headers["location"]
        assert "wechat_token=" in redirect
        token = parse_qs(urlparse(redirect).query)["wechat_token"][0]
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200, me.text
        assert me.json()["username"] == "wechat_operator"

        second_user = client.post(
            "/api/settings/users",
            headers=admin_headers,
            json={"username": "other_operator", "password": "other-password", "role": "operator", "is_active": True},
        )
        assert second_user.status_code == 200, second_user.text
        second_login = client.post("/api/auth/login", json={"username": "other_operator", "password": "other-password"})
        assert second_login.status_code == 200, second_login.text
        second_headers = {"Authorization": f"Bearer {second_login.json()['token']}"}

        own_material = client.post(
            "/api/materials",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "微信用户素材", "kind": "image", "copyright_status": "owned", "tags": "owner-test"},
        )
        assert own_material.status_code == 200, own_material.text
        material_id = own_material.json()["id"]

        hidden_materials = client.get("/api/materials", headers=second_headers)
        assert hidden_materials.status_code == 200, hidden_materials.text
        assert all(item["id"] != material_id for item in hidden_materials.json())

        blocked_delete = client.delete(f"/api/materials/{material_id}", headers=second_headers)
        assert blocked_delete.status_code == 403, blocked_delete.text

        print("wechat login smoke ok")


if __name__ == "__main__":
    main()
