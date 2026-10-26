"""会话与历史消息 —— 验证 App 冷启动后能恢复历史。"""

from __future__ import annotations

from app.database import get_session_factory
from app.models import Conversation, Message
from tests.conftest import StubProvider


def _seed(client, stub: StubProvider, texts: list[str]) -> str:
    conv_id = None
    for t in texts:
        payload = {"message": t}
        if conv_id:
            payload["conversation_id"] = conv_id
        conv_id = client.post("/api/v1/chat", json=payload).json()["conversation_id"]
    return conv_id


def test_history_is_restored_in_order(client, stub):
    texts = ["第一句", "第二句", "第三句"]
    conv_id = _seed(client, stub, texts)

    # 模拟 App 退出重启：新会话对象读取，确认顺序与内容一致
    r = client.get(f"/api/v1/conversations/{conv_id}/messages")
    assert r.status_code == 200
    msgs = r.json()
    assert len(msgs) == 6
    assert [m["content"] for m in msgs if m["role"] == "user"] == texts
    timestamps = [m["created_at"] for m in msgs]
    assert timestamps == sorted(timestamps)


def test_history_survives_new_engine_session(tmp_path, client, stub):
    """跨数据库会话（近似 App 重启）仍能读到消息。"""
    conv_id = _seed(client, stub, ["持久化测试"])

    factory = get_session_factory()
    with factory() as s:
        count = s.query(Message).filter(Message.conversation_id == conv_id).count()
    assert count == 2


def test_conversation_list_includes_counts(client, stub):
    _seed(client, stub, ["a"])
    _seed(client, stub, ["b", "c"])
    convs = client.get("/api/v1/conversations").json()
    assert len(convs) == 2
    assert sorted(c["message_count"] for c in convs) == [2, 4]


def test_title_derived_from_first_message(client, stub):
    conv_id = _seed(client, stub, ["今天天气不错，我们聊聊旅行"])
    convs = client.get("/api/v1/conversations").json()
    title = next(c["title"] for c in convs if c["id"] == conv_id)
    assert title.startswith("今天天气不错")


def test_long_title_truncated(client, stub):
    conv_id = _seed(client, stub, ["一" * 80])
    convs = client.get("/api/v1/conversations").json()
    title = next(c["title"] for c in convs if c["id"] == conv_id)
    assert len(title) <= 25
    assert title.endswith("…")


def test_delete_conversation_cascades_messages(client, stub):
    conv_id = _seed(client, stub, ["删除我"])
    assert client.delete(f"/api/v1/conversations/{conv_id}").status_code == 204
    assert client.get(f"/api/v1/conversations/{conv_id}/messages").json() == []
    assert client.delete(f"/api/v1/conversations/{conv_id}").status_code == 404


def test_unknown_conversation_returns_empty_history(client):
    assert client.get("/api/v1/conversations/does-not-exist/messages").json() == []


def test_orphan_messages_are_removed_with_conversation(db_session):
    from datetime import datetime, timezone

    conv = Conversation(id="c1", title="t", created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc))
    db_session.add(conv)
    db_session.flush()
    db_session.add(Message(id="m1", conversation_id="c1", role="user", content="x",
                           created_at=datetime.now(timezone.utc)))
    db_session.commit()
    db_session.delete(conv)
    db_session.commit()
    assert db_session.get(Message, "m1") is None
