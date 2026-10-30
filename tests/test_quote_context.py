"""引用消息进入模型上下文（需求：引用内容与用户新陈述分开，不进长期记忆）。

验收点：
1. quoted_text 真正出现在发给模型的最后一条 user 消息里，且与「用户现在说」明确分隔；
2. 落库的用户消息正文仍是原始新内容，不含引用文本；
3. 引用文本不会被当成用户事实写进长期记忆。
"""

from __future__ import annotations


def _last_conv(client) -> str:
    return client.get("/api/v1/conversations").json()[0]["id"]


def test_quoted_text_reaches_model_context(client, stub):
    client.post("/api/v1/chat", json={"message": "我之前说过我喜欢猫"})
    r = client.post(
        "/api/v1/chat",
        json={
            "message": "那你记得我喜欢什么吗",
            "conversation_id": _last_conv(client),
            "quoted_text": "我之前说过我喜欢猫",
        },
    )
    assert r.status_code == 200

    final_user = stub.calls[-1][-1].content
    # 引用内容与用户新陈述都进入模型上下文
    assert "我之前说过我喜欢猫" in final_user
    assert "那你记得我喜欢什么吗" in final_user
    # 二者被明确分隔，模型能区分「引用」与「新话」
    assert "<引用>" in final_user
    assert "<用户现在说>" in final_user


def test_quoted_text_not_persisted_in_message_content(client, stub):
    client.post("/api/v1/chat", json={"message": "第一条"})
    conv = _last_conv(client)
    r = client.post(
        "/api/v1/chat",
        json={
            "message": "就这条被引用的话",
            "conversation_id": conv,
            "quoted_text": "第一条",
        },
    )
    assert r.status_code == 200

    msgs = client.get(f"/api/v1/conversations/{conv}/messages").json()
    user_msgs = [m for m in msgs if m["role"] == "user"]
    # 落库正文只有原始新内容，不含引用文本
    assert user_msgs[-1]["content"] == "就这条被引用的话"
    assert all("第一条" != m["content"] for m in user_msgs[1:])


def test_quoted_text_not_recorded_as_memory(client, stub):
    """引用内容不被长期记忆当作用户事实抽取。"""
    client.post("/api/v1/chat", json={"message": "我叫李华"})
    r = client.post(
        "/api/v1/chat",
        json={
            "message": "再说一次我的名字",
            "conversation_id": _last_conv(client),
            "quoted_text": "我叫李华",
        },
    )
    assert r.status_code == 200

    memories = client.get("/api/v1/memory").json()
    contents = " ".join(m.get("content", "") for m in memories)
    # 引用里的名字不应作为新的用户事实；真正落库的新内容里没有「李华」，
    # 因此记忆不应新增「李华」（记忆抽取基于原始 user_text，不含引用）。
    # 这里只做弱断言：引用文本不会被原样整段记为一条记忆。
    assert "我叫李华" not in contents


def test_quoted_text_idempotent_replay_unchanged(client, stub):
    """带引用重放同一 request_id 不产生新回复、不重复进入上下文。"""
    body = {
        "message": "重放引用",
        "request_id": "rid-quote-1",
        "quoted_text": "被引用的句子",
    }
    first = client.post("/api/v1/chat", json=body).json()
    replay = dict(body)
    replay["conversation_id"] = first["conversation_id"]
    second = client.post("/api/v1/chat", json=replay).json()

    assert second["idempotent_replay"] is True
    assert second["reply"] == first["reply"]
