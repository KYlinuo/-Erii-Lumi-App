"""单用户访问认证。"""

from __future__ import annotations

import pytest

from app.config import reload_settings
from app.security import build_auth_state
from tests.conftest import TEST_TOKEN


def test_public_endpoints_open_without_token(authed_client):
    for path in ("/", "/api/v1/health", "/api/v1/persona"):
        r = authed_client.get(path)
        assert r.status_code == 200, path


def test_protected_endpoint_rejects_missing_token(authed_client):
    r = authed_client.post("/api/v1/chat", json={"message": "hi"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"
    assert r.headers["x-lumi-error-code"] == "unauthorized"


def test_protected_endpoint_rejects_wrong_token(authed_client):
    r = authed_client.post(
        "/api/v1/chat", json={"message": "hi"}, headers={"X-LUMI-TOKEN": "wrong-token"}
    )
    assert r.status_code == 401


def test_valid_token_is_accepted(authed_client, stub, auth_headers):
    r = authed_client.post("/api/v1/chat", json={"message": "hi"}, headers=auth_headers)
    assert r.status_code == 200


def test_bearer_scheme_also_accepted(authed_client, stub):
    r = authed_client.post(
        "/api/v1/chat",
        json={"message": "hi"},
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )
    assert r.status_code == 200


def test_conversation_endpoints_require_token(authed_client):
    assert authed_client.get("/api/v1/conversations").status_code == 401
    assert authed_client.get("/api/v1/conversations", headers={"X-LUMI-TOKEN": TEST_TOKEN}).status_code == 200


def test_token_comparison_is_constant_time():
    from app.security import _tokens_match

    assert _tokens_match(TEST_TOKEN, TEST_TOKEN) is True
    assert _tokens_match(TEST_TOKEN, TEST_TOKEN[:-1] + "x") is False


def test_dev_mode_without_token_allows_access(client, stub):
    r = client.post("/api/v1/chat", json={"message": "dev"})
    assert r.status_code == 200


def test_production_requires_token_or_refuses_to_boot(monkeypatch):
    monkeypatch.setenv("LUMI_ENV", "prod")
    monkeypatch.delenv("LUMI_ACCESS_TOKEN", raising=False)
    reload_settings()
    with pytest.raises(RuntimeError, match="LUMI_ACCESS_TOKEN"):
        build_auth_state()

    monkeypatch.setenv("LUMI_ACCESS_TOKEN", TEST_TOKEN)
    reload_settings()
    assert build_auth_state().required is True


def test_auth_state_reported_by_health(authed_client):
    assert authed_client.get("/api/v1/health").json()["auth_required"] is True
