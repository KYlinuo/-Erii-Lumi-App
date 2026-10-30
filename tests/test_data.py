"""消息收藏 + 数据导出 + 视觉预留 测试。"""

from __future__ import annotations

from app import vision


def test_vision_not_configured_by_default(monkeypatch):
    monkeypatch.setenv("LUMI_VISION_MODEL", "")
    monkeypatch.setenv("LUMI_VISION_BASE_URL", "")
    from app.config import reload_settings

    reload_settings()
    assert vision.vision_configured() is False
    assert vision.describe_image(b"fake", "image/jpeg") is None


def test_vision_configured_requires_all_three(monkeypatch):
    monkeypatch.setenv("LUMI_VISION_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("LUMI_VISION_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("LUMI_API_KEY", "sk-test")
    from app.config import reload_settings

    reload_settings()
    assert vision.vision_configured() is True


def test_star_and_unstar_message(client, stub):
    body = client.post("/api/v1/chat", json={"message": "收藏我"}).json()
    conv_id = body["conversation_id"]
    msgs = client.get(f"/api/v1/conversations/{conv_id}/messages").json()
    mid = next(m for m in msgs if m["role"] == "assistant")["id"]

    starred = client.post(f"/api/v1/conversations/{conv_id}/messages/{mid}/star?starred=true").json()
    assert starred.get("starred") is True or starred.get("starred") is None
    listed = client.get(f"/api/v1/conversations/{conv_id}/messages/starred").json()
    assert any(m["id"] == mid for m in listed)

    client.post(f"/api/v1/conversations/{conv_id}/messages/{mid}/star?starred=false")
    listed2 = client.get(f"/api/v1/conversations/{conv_id}/messages/starred").json()
    assert not any(m["id"] == mid for m in listed2)


def test_export_returns_shape(client):
    r = client.get("/api/v1/export")
    assert r.status_code == 200
    body = r.json()
    assert "conversations" in body
    assert "memories" in body
    assert "exported_at" in body


def test_wipe_requires_confirm(client):
    r = client.post("/api/v1/data/wipe", json={"confirm": "no"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "confirm_required"
