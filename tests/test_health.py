"""/api/v1/health 与 /api/v1/persona —— iOS 设置页连接状态检测依赖它们。"""

from __future__ import annotations

from app.llm.errors import ProviderNotConfigured
from app.llm.factory import set_provider
from tests.conftest import StubProvider


def test_health_ok(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["version"]
    assert body["auth_required"] is False


def test_health_reflects_provider_state(client):
    set_provider(StubProvider())
    body = client.get("/api/v1/health").json()
    assert body["provider_configured"] is True
    assert body["provider"] == "stub"

    set_provider(StubProvider(raise_exc=ProviderNotConfigured()))
    body = client.get("/api/v1/health").json()
    assert body["provider_configured"] is False


def test_health_never_leaks_api_key(monkeypatch, client):
    monkeypatch.setenv("LUMI_API_KEY", "sk-super-secret-value-123456")
    from app.config import reload_settings

    reload_settings()
    body = client.get("/api/v1/health").json()
    assert "super-secret" not in str(body)
    assert body["api_key_hint"].startswith("sk-s")


def test_persona_has_distinct_identity(client):
    body = client.get("/api/v1/persona").json()
    assert body["name"] == "绘梨衣"
    assert body["tagline"]
    assert body["avatar"]
    assert body["greeting"]


def test_root_endpoint(client):
    body = client.get("/").json()
    assert body["name"] == "绘梨衣"
