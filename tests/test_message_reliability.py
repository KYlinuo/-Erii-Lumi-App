"""消息可靠性：连发顺序 + 幂等重放（验收场景 1、3）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

TOKEN = "test-token-rel"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LUMI_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv("LUMI_DB_PATH", str(tmp_path / "rel.db"))
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


def test_consecutive_messages_keep_order_and_ids(client):
    """验收场景 1：连发三条消息，顺序正确、不丢消息、request_id 幂等。"""
    conv = None
    for i in range(3):
        body = {"message": f"第{i+1}条", "request_id": f"rid-seq-{i}"}
        if conv:
            body["conversation_id"] = conv
        r = client.post("/api/v1/chat", json=body).json()
        conv = r["conversation_id"]

    msgs = client.get(f"/api/v1/conversations/{conv}/messages").json()
    user_msgs = [m for m in msgs if m["role"] == "user"]
    # 三条用户消息按顺序，不丢
    assert [m["content"] for m in user_msgs] == ["第1条", "第2条", "第3条"]
    # 每条用户消息都有对应的一条助手回复
    assistant = [m for m in msgs if m["role"] == "assistant"]
    assert len(assistant) == 3


def test_idempotent_replay_returns_same_reply_no_duplicate(client):
    """验收场景 3：幂等重放只有最终结果，不产生第二条消息。"""
    body = {"message": "幂等测试", "request_id": "rid-idem-1"}
    first = client.post("/api/v1/chat", json=body).json()

    # 重放：同一 request_id，带 conversation_id
    replay = dict(body)
    replay["conversation_id"] = first["conversation_id"]
    second = client.post("/api/v1/chat", json=replay).json()

    assert first["reply"] == second["reply"]
    assert second["idempotent_replay"] is True
    assert second["assistant_message_id"] == first["assistant_message_id"]

    msgs = client.get(f"/api/v1/conversations/{first['conversation_id']}/messages").json()
    assistant = [m for m in msgs if m["role"] == "assistant"]
    # 只有一条助手消息（没有因为重放而重复）
    assert len(assistant) == 1
    assert assistant[0]["content"] == first["reply"]


def test_replay_after_retry_does_not_duplicate(client):
    """幂等重放 + 重试组合：同一 request_id 多次提交不产生重复回复。"""
    body = {"message": "重试幂等", "request_id": "rid-retry-idem"}
    r1 = client.post("/api/v1/chat", json=body).json()
    conv = r1["conversation_id"]

    def replay():
        return client.post("/api/v1/chat", json={
            "message": "重试幂等", "request_id": "rid-retry-idem",
            "conversation_id": conv,
        }).json()

    r2 = replay()
    r3 = replay()

    assert r1["reply"] == r2["reply"] == r3["reply"]
    msgs = client.get(f"/api/v1/conversations/{conv}/messages").json()
    assert len([m for m in msgs if m["role"] == "assistant"]) == 1
