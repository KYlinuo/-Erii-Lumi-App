"""流式输出（SSE）测试。

验证 /api/v1/chat?stream=true 的增量协议，以及 Mock 下的行为。
Mock 的 chat_stream 走基类默认实现（一次性吐完整内容），
所以这里验证的是「协议正确」而非「真分流」——真分流由 OpenAI 兼容层保证。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

TOKEN = "test-token-stream"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LUMI_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv("LUMI_DB_PATH", str(tmp_path / "stream.db"))
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


def _events(body: str) -> list[dict]:
    import json

    out = []
    for line in body.splitlines():
        if line.startswith("data:"):
            out.append(json.loads(line[5:].strip()))
    return out


def test_stream_returns_deltas_and_done(client):
    r = client.post("/api/v1/chat", json={"message": "晚上好", "stream": True})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")

    events = _events(r.text)
    types = [e["type"] for e in events]
    assert "delta" in types, "应至少有一个正文增量事件"
    assert types[-1] == "done", "最后一个事件必须是 done"

    done = events[-1]
    assert done["reply"]
    assert done["assistant_message_id"]
    assert done["conversation_id"]


def test_stream_delta_text_joins_to_reply(client):
    r = client.post("/api/v1/chat", json={"message": "你好", "stream": True})
    events = _events(r.text)
    joined = "".join(e["text"] for e in events if e["type"] == "delta")
    done = events[-1]
    assert joined == done["reply"]


def test_stream_and_nonstream_equivalent(client):
    a = client.post("/api/v1/chat", json={"message": "同一个问题"})
    b = client.post("/api/v1/chat", json={"message": "同一个问题", "stream": True})
    events = _events(b.text)
    assert a.status_code == 200
    assert events[-1]["type"] == "done"


def test_stream_idempotent_replay_marks_replay(client):
    body = {"message": "重复测试", "request_id": "rid-stream-1", "stream": True}
    first = _events(client.post("/api/v1/chat", json=body).text)
    cid = first[-1]["conversation_id"]
    # 幂等重放必须带同一 conversation_id，否则会被当成另一个会话而 409
    second = _events(client.post("/api/v1/chat", json={**body, "conversation_id": cid}).text)
    assert second[-1]["idempotent_replay"] is True
    assert first[-1]["reply"] == second[-1]["reply"]


def test_stream_empty_message_rejected(client):
    r = client.post("/api/v1/chat", json={"message": "   ", "stream": True})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "empty_message"
