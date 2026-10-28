"""Token 用量与预算接口测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

TOKEN = "test-token-usage"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LUMI_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv("LUMI_DB_PATH", str(tmp_path / "usage.db"))
    monkeypatch.setenv("LUMI_PROVIDER", "mock")
    monkeypatch.setenv("LUMI_MEMORY_AUTO_EXTRACT", "0")
    from app.config import reload_settings

    reload_settings()
    from app.database import init_db

    init_db(force=True)
    from app.main import create_app

    with TestClient(create_app()) as c:
        c.headers.update({"Authorization": f"Bearer {TOKEN}"})
        yield c


def test_usage_starts_empty(client):
    body = client.get("/api/v1/usage").json()
    assert body["today"]["total_tokens"] == 0
    assert body["today"]["replies"] == 0
    assert body["budget"]["daily_token_budget"] >= 0


def test_usage_counts_chat_tokens(client):
    r = client.post("/api/v1/chat", json={"message": "今天有点累"})
    assert r.status_code == 200
    body = client.get("/api/v1/usage").json()
    assert body["today"]["replies"] == 1
    assert body["today"]["total_tokens"] > 0
    # 成本必须是非负的估算值
    assert body["today"]["cost_usd"] >= 0


def test_usage_days_is_clamped(client):
    body = client.get("/api/v1/usage?days=999").json()
    assert body["last_days"]["days"] == 30


def test_usage_requires_auth(client):
    r = client.get("/api/v1/usage", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401
