"""设备与身份：注册、令牌校验、作用域、吊销。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import identity
from tests.conftest import TEST_TOKEN


def _auth_app(monkeypatch):
    """开启认证后的真实应用（主令牌 = TEST_TOKEN）。"""
    monkeypatch.setenv("LUMI_ACCESS_TOKEN", TEST_TOKEN)
    from app.config import reload_settings

    reload_settings()
    from app.bootstrap import bootstrap
    from app.database import create_all, get_session_factory, init_engine
    from app.main import create_app

    init_engine("sqlite:///:memory:", force=True)
    create_all()
    with get_session_factory()() as db:
        bootstrap(db)
    return create_app()


def test_register_device_returns_plaintext_token_once(client):
    r = client.post(
        "/api/v1/devices",
        json={"name": "iPhone 17 Pro", "platform": "ios", "app_version": "0.2.0"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["token"] and len(body["token"]) > 20
    assert body["platform"] == "ios"
    assert "chat" in body["scopes"]
    assert body["token_hint"].endswith(body["token"][-4:])


def test_device_token_is_stored_only_as_hash(client, db_session):
    body = client.post(
        "/api/v1/devices", json={"name": "Windows 桌宠", "platform": "windows"}
    ).json()
    device = db_session.get(identity.Device, body["device_id"])
    assert device.token_hash != body["token"]
    assert body["token"] not in device.token_hash
    assert len(device.token_hash) == 64  # SHA-256 hex


def test_device_token_authenticates_requests(monkeypatch):
    app = _auth_app(monkeypatch)
    with TestClient(app) as c:
        # 无凭据 → 401
        assert c.get("/api/v1/devices/me").status_code == 401

        # 主令牌 → 通过
        assert c.get("/api/v1/devices/me", headers={"X-LUMI-TOKEN": TEST_TOKEN}).status_code == 200

        # 注册后拿设备令牌 → 通过，且能识别设备身份
        token = c.post(
            "/api/v1/devices",
            json={"name": "iPhone", "platform": "ios"},
            headers={"X-LUMI-TOKEN": TEST_TOKEN},
        ).json()["token"]
        me = c.get("/api/v1/devices/me", headers={"X-LUMI-TOKEN": token})
        assert me.status_code == 200
        assert me.json()["kind"] == "device"
        assert me.json()["device_id"]


def test_revoked_device_token_stops_working(monkeypatch):
    app = _auth_app(monkeypatch)
    with TestClient(app) as c:
        device_id, token = None, None
        created = c.post(
            "/api/v1/devices",
            json={"name": "iPhone", "platform": "ios"},
            headers={"X-LUMI-TOKEN": TEST_TOKEN},
        ).json()
        device_id, token = created["device_id"], created["token"]
        assert c.get("/api/v1/devices/me", headers={"X-LUMI-TOKEN": token}).status_code == 200

        assert c.delete(f"/api/v1/devices/{device_id}",
                        headers={"X-LUMI-TOKEN": TEST_TOKEN}).status_code == 204
        assert c.get("/api/v1/devices/me", headers={"X-LUMI-TOKEN": token}).status_code == 401


def test_wrong_token_rejected(monkeypatch):
    app = _auth_app(monkeypatch)
    with TestClient(app) as c:
        assert c.get("/api/v1/devices/me", headers={"X-LUMI-TOKEN": "wrong-token"}).status_code == 401
        body = c.get("/api/v1/devices/me", headers={"X-LUMI-TOKEN": "wrong-token"}).json()
        assert body["error"]["code"] == "unauthorized"


def test_scopes_can_be_narrowed(db_session):
    _device, token = identity.register_device(
        db_session, name="受限设备", platform="cli", scopes="chat"
    )
    db_session.commit()
    found = identity.verify_device_token(db_session, token)
    assert found is not None
    assert found.scope_list == ["chat"]
    assert not found.has_scope("admin")


def test_rename_device(client):
    created = client.post("/api/v1/devices", json={"name": "A", "platform": "ios"}).json()
    r = client.patch(f"/api/v1/devices/{created['device_id']}", json={"name": "B"})
    assert r.status_code == 200 and r.json()["name"] == "B"


def test_unknown_device_returns_404(client):
    assert client.patch("/api/v1/devices/nope", json={"name": "x"}).status_code == 404
    assert client.delete("/api/v1/devices/nope").status_code == 404
