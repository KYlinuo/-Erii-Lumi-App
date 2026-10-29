"""LiveKit Access Token 签发测试（纯本地，不连真实 LiveKit Server）。"""

from __future__ import annotations

import base64
import json
import time

from app import livekit as livekit_mod


def _decode_token(token: str) -> dict:
    header_b64, payload_b64, _sig = token.split(".")
    pad = lambda s: s + "=" * (-len(s) % 4)  # noqa: E731
    payload = json.loads(base64.urlsafe_b64decode(pad(payload_b64)))
    return payload


def test_token_has_expected_claims():
    token = livekit_mod.make_access_token(
        api_key="test-key",
        api_secret="test-secret",
        identity="ios-user-1",
        room="lumi-room",
    )
    payload = _decode_token(token)
    assert payload["iss"] == "test-key"
    assert payload["sub"] == "ios-user-1"
    assert payload["video"]["room"] == "lumi-room"
    assert payload["video"]["roomJoin"] is True
    assert payload["video"]["canPublish"] is True
    assert payload["exp"] > int(time.time())


def test_token_signature_validates_with_secret():
    token = livekit_mod.make_access_token(
        api_key="k", api_secret="s", identity="u", room="r"
    )
    header_b64, payload_b64, sig = token.split(".")
    import hashlib
    import hmac

    expected = hmac.new(
        b"s", f"{header_b64}.{payload_b64}".encode("ascii"), hashlib.sha256
    ).digest()
    pad = lambda s: s + "=" * (-len(s) % 4)  # noqa: E731
    assert base64.urlsafe_b64decode(pad(sig)) == expected


def test_call_status_reports_unconfigured(monkeypatch):
    monkeypatch.setenv("LUMI_LIVEKIT_URL", "")
    monkeypatch.setenv("LUMI_LIVEKIT_API_KEY", "")
    monkeypatch.setenv("LUMI_LIVEKIT_API_SECRET", "")
    from app.config import reload_settings

    reload_settings()
    status = livekit_mod.call_status()
    assert status["configured"] is False


def test_call_status_reports_configured(monkeypatch):
    monkeypatch.setenv("LUMI_LIVEKIT_URL", "wss://example.livekit.cloud")
    monkeypatch.setenv("LUMI_LIVEKIT_API_KEY", "apikey123")
    monkeypatch.setenv("LUMI_LIVEKIT_API_SECRET", "secret123")
    from app.config import reload_settings

    reload_settings()
    status = livekit_mod.call_status()
    assert status["configured"] is True
    assert status["livekit_url"] == "wss://example.livekit.cloud"


def test_issue_token_returns_connection_fields(monkeypatch):
    monkeypatch.setenv("LUMI_LIVEKIT_URL", "wss://example.livekit.cloud")
    monkeypatch.setenv("LUMI_LIVEKIT_API_KEY", "apikey123")
    monkeypatch.setenv("LUMI_LIVEKIT_API_SECRET", "secret123")
    from app.config import reload_settings

    reload_settings()
    result = livekit_mod.issue_call_token(identity="u1", room="r1")
    assert result["configured"] is True
    assert result["url"] == "wss://example.livekit.cloud"
    assert result["token"]
    assert result["room"] == "r1"


def test_issue_token_unconfigured(monkeypatch):
    monkeypatch.setenv("LUMI_LIVEKIT_URL", "")
    monkeypatch.setenv("LUMI_LIVEKIT_API_KEY", "")
    monkeypatch.setenv("LUMI_LIVEKIT_API_SECRET", "")
    from app.config import reload_settings

    reload_settings()
    result = livekit_mod.issue_call_token(identity="u1", room="r1")
    assert result["configured"] is False
    assert result["reason"] == "livekit_not_configured"
