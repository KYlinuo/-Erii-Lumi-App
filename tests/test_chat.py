"""POST /api/v1/chat —— 必须调用真实模型适配器，任何失败都要有明确错误码。"""

from __future__ import annotations

from app.llm import errors as llm_errors
from app.llm.factory import set_provider
from tests.conftest import StubProvider


def test_chat_returns_model_reply(client, stub):
    r = client.post("/api/v1/chat", json={"message": "你好，LUMI"})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "这是来自桩模型的回复。"
    assert body["conversation_id"]
    assert body["user_message_id"]
    assert body["assistant_message_id"]
    assert body["model"] == "stub-model-v1"


def test_chat_sends_system_prompt_and_history(client, stub):
    client.post("/api/v1/chat", json={"message": "第一条"})
    client.post("/api/v1/chat", json={"message": "第二条", "conversation_id": _last_conv(client)})

    last_call = stub.calls[-1]
    assert last_call[0].role == "system"
    assert "LUMI" in last_call[0].content
    assert [m.role for m in last_call[1:]] == ["user", "assistant", "user"]


def _last_conv(client) -> str:
    return client.get("/api/v1/conversations").json()[0]["id"]


def test_chat_persists_both_sides(client, stub):
    body = client.post("/api/v1/chat", json={"message": "记下来了吗"}).json()
    msgs = client.get(f"/api/v1/conversations/{body['conversation_id']}/messages").json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["content"] == "记下来了吗"
    assert msgs[1]["content"] == "这是来自桩模型的回复。"
    assert msgs[1]["status"] == "ok"


def test_chat_rejects_empty_message(client, stub):
    r = client.post("/api/v1/chat", json={"message": "   "})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "empty_message"


def test_chat_rejects_oversized_message(client, stub):
    r = client.post("/api/v1/chat", json={"message": "x" * 9000})
    assert r.status_code == 422


def test_chat_when_api_key_missing(client):
    """未配置 Key 时必须显式报错，绝不能返回伪造回复。"""
    set_provider(StubProvider(raise_exc=llm_errors.ProviderNotConfigured()))
    r = client.post("/api/v1/chat", json={"message": "你好"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "provider_not_configured"
    assert "reply" not in r.json()


FAILURE_CASES = [
    (llm_errors.ProviderTimeoutError(), 504, "upstream_timeout"),
    (llm_errors.ProviderUnavailableError(), 503, "upstream_unavailable"),
    (llm_errors.ProviderAuthError(), 502, "upstream_unauthorized"),
    (llm_errors.ProviderRateLimitError(), 429, "upstream_rate_limited"),
    (llm_errors.ProviderBadResponse(), 502, "upstream_bad_response"),
]


def test_chat_maps_every_upstream_failure(client):
    for exc, expected_status, expected_code in FAILURE_CASES:
        set_provider(StubProvider(raise_exc=exc))
        r = client.post("/api/v1/chat", json={"message": "会失败吗"})
        assert r.status_code == expected_status, (
            f"{type(exc).__name__} 期望 {expected_status}，实际 {r.status_code}"
        )
        assert r.json()["error"]["code"] == expected_code
        assert r.headers.get("x-lumi-error-code") == expected_code


def test_user_message_survives_upstream_failure(client):
    """上游失败时用户消息依然落库，重启 App 不会丢历史。"""
    set_provider(StubProvider(raise_exc=llm_errors.ProviderTimeoutError()))
    r = client.post("/api/v1/chat", json={"message": "超时前说的话"})
    assert r.status_code == 504
    convs = client.get("/api/v1/conversations").json()
    assert convs, "失败请求也应创建会话并保存用户消息"
    msgs = client.get(f"/api/v1/conversations/{convs[0]['id']}/messages").json()
    assert [m["role"] for m in msgs] == ["user"]
