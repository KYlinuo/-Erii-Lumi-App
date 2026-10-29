"""预算拦截（验收场景 12）测试。"""

from __future__ import annotations

from app import usage as usage_mod


def test_budget_zero_means_unlimited(db_session):
    from app.config import get_settings
    s = get_settings()
    assert s.daily_token_budget == 200_000  # 默认值
    # 单独验证 check 函数：手动塞一条超额的 assistant 消息
    from app.models import Conversation, Message
    from app.identity import get_or_create_user

    u = get_or_create_user(db_session, user_id="u-budget")
    conv = Conversation(title="t", user_id=u.id)
    db_session.add(conv)
    db_session.flush()
    db_session.add(Message(
        conversation_id=conv.id, role="assistant", content="x",
        tokens_prompt=150_000, tokens_completion=100_000, status="ok", kind="text",
    ))
    db_session.commit()

    # 150k + 100k = 250k >= 200k → 超限
    assert usage_mod.check_budget_exceeded(db_session) is True


def test_budget_not_exceeded_when_under(db_session):
    from app.identity import get_or_create_user
    from app.models import Conversation, Message

    u = get_or_create_user(db_session, user_id="u-budget2")
    conv = Conversation(title="t", user_id=u.id)
    db_session.add(conv)
    db_session.flush()
    db_session.add(Message(
        conversation_id=conv.id, role="assistant", content="x",
        tokens_prompt=100, tokens_completion=100, status="ok", kind="text",
    ))
    db_session.commit()
    assert usage_mod.check_budget_exceeded(db_session) is False


def test_budget_exceeded_rejects_chat(client, db_session, monkeypatch):
    """超限时 chat 返回 429 budget_exceeded，不再调用模型。"""
    from app.identity import get_or_create_user
    from app.models import Conversation, Message

    u = get_or_create_user(db_session, user_id="u-budget3")
    conv = Conversation(title="t", user_id=u.id)
    db_session.add(conv)
    db_session.flush()
    db_session.add(Message(
        conversation_id=conv.id, role="assistant", content="x",
        tokens_prompt=150_000, tokens_completion=100_000, status="ok", kind="text",
    ))
    db_session.commit()

    r = client.post("/api/v1/chat", json={"message": "hi"})
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "budget_exceeded"
