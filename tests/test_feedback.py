"""回复反馈（需求 11）测试：记错了 / 太长 / 不像绘梨衣。"""

from __future__ import annotations


def test_feedback_too_long_sets_short_style(client):
    # 先确认默认 medium
    assert client.get("/api/v1/style").json()["reply_length"] == "medium"

    r = client.post("/api/v1/feedback", json={"type": "too_long", "message_id": "m1"})
    assert r.status_code == 200
    assert r.json()["recorded"] is True

    # too_long 自动把回复长度调短
    assert client.get("/api/v1/style").json()["reply_length"] == "short"


def test_feedback_wrong_recorded(client):
    r = client.post("/api/v1/feedback", json={"type": "wrong", "message_id": "m2", "note": "她说错了我的名字"})
    assert r.status_code == 200
    assert r.json()["type"] == "wrong"


def test_feedback_not_erii_recorded(client):
    r = client.post("/api/v1/feedback", json={"type": "not_erii", "message_id": "m3"})
    assert r.status_code == 200


def test_feedback_invalid_type_rejected(client):
    r = client.post("/api/v1/feedback", json={"type": "bogus"})
    assert r.status_code == 422
