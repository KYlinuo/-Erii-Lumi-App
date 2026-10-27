"""模型网关：Mock Provider、重试策略、Token 记录、人格/记忆注入。"""

from __future__ import annotations

import asyncio

import pytest

from app import personas
from app.config import reload_settings
from app.llm import errors as llm_errors
from app.llm.base import LLMMessage, LLMResult
from app.llm.factory import (
    build_provider,
    get_provider,
    is_mock_provider,
    set_provider,
)
from app.llm.mock import MODEL_NAME, MockProvider
from app.llm.retry import generate_with_retry, is_retryable


def _messages() -> list[LLMMessage]:
    return [
        LLMMessage(role="system", content="你是 LUMI。"),
        LLMMessage(role="user", content="你好"),
    ]


# --------------------------------------------------------------- Mock Provider


def test_mock_provider_is_configured_without_any_key():
    provider = MockProvider()
    assert provider.is_configured() is True
    assert provider.model == MODEL_NAME


@pytest.mark.asyncio
async def test_mock_provider_returns_deterministic_reply():
    provider = MockProvider()
    first = await provider.chat(_messages())
    second = await provider.chat(_messages())
    assert first.content == second.content
    assert first.model == MODEL_NAME
    assert first.prompt_tokens and first.completion_tokens


@pytest.mark.asyncio
async def test_mock_provider_can_be_scripted():
    provider = MockProvider(replies=["甲", "乙"])
    assert (await provider.chat(_messages())).content == "甲"
    assert (await provider.chat(_messages())).content == "乙"


def test_factory_builds_mock_when_configured(monkeypatch):
    monkeypatch.setenv("LUMI_PROVIDER", "mock")
    reload_settings()
    set_provider(None)
    provider = build_provider()
    assert isinstance(provider, MockProvider)
    assert is_mock_provider(provider) is True


def test_factory_does_not_silently_substitute_mock_without_key(monkeypatch):
    """没配 Key 时**不能**偷偷用 Mock 顶替真实模型。"""
    monkeypatch.setenv("LUMI_PROVIDER", "deepseek")
    monkeypatch.delenv("LUMI_API_KEY", raising=False)
    reload_settings()
    provider = build_provider()
    assert not isinstance(provider, MockProvider)
    assert provider.is_configured() is False


def test_health_reports_mock_usage(monkeypatch):
    monkeypatch.setenv("LUMI_PROVIDER", "mock")
    reload_settings()
    set_provider(None)
    provider = get_provider()
    assert is_mock_provider(provider)
    set_provider(None)


# --------------------------------------------------------------- 重试


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_failure():
    calls = {"n": 0}

    async def _chat(messages):  # noqa: ANN001
        calls["n"] += 1
        if calls["n"] < 3:
            raise llm_errors.ProviderTimeoutError()
        return LLMResult(content="ok", model="stub", latency_ms=1)

    class Flaky(MockProvider):
        async def chat(self, messages):  # noqa: ANN001
            return await _chat(messages)

    slept: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    result = await generate_with_retry(Flaky(), _messages(), max_retries=2, sleep=_fake_sleep)
    assert result.content == "ok"
    assert calls["n"] == 3
    assert len(slept) == 2
    assert slept[1] > slept[0], "退避时间应递增"


@pytest.mark.asyncio
async def test_retry_gives_up_and_raises_last_error():
    class AlwaysFail(MockProvider):
        async def chat(self, messages):  # noqa: ANN001
            raise llm_errors.ProviderUnavailableError()

    async def _no_sleep(_seconds: float) -> None:
        return None

    with pytest.raises(llm_errors.ProviderUnavailableError):
        await generate_with_retry(AlwaysFail(), _messages(), max_retries=2, sleep=_no_sleep)


@pytest.mark.asyncio
async def test_non_retryable_errors_are_not_retried():
    calls = {"n": 0}

    class BadKey(MockProvider):
        async def chat(self, messages):  # noqa: ANN001
            calls["n"] += 1
            raise llm_errors.ProviderAuthError()

    async def _no_sleep(_seconds: float) -> None:
        return None

    with pytest.raises(llm_errors.ProviderAuthError):
        await generate_with_retry(BadKey(), _messages(), max_retries=3, sleep=_no_sleep)
    assert calls["n"] == 1, "Key 无效不应重试"


def test_retryable_classification():
    assert is_retryable(llm_errors.ProviderTimeoutError())
    assert is_retryable(llm_errors.ProviderUnavailableError())
    assert is_retryable(llm_errors.ProviderRateLimitError())
    assert not is_retryable(llm_errors.ProviderAuthError())
    assert not is_retryable(llm_errors.ProviderBadResponse())
    assert not is_retryable(llm_errors.ProviderNotConfigured())


# --------------------------------------------------------------- 注入与记账


def test_context_includes_system_persona_and_history(client, stub):
    client.post("/api/v1/chat", json={"message": "第一条"})
    conv = client.get("/api/v1/conversations").json()[0]["id"]
    client.post("/api/v1/chat", json={"message": "第二条", "conversation_id": conv})

    last = stub.calls[-1]
    assert last[0].role == "system"
    assert "LUMI" in last[0].content
    assert [m.role for m in last[1:]] == ["user", "assistant", "user"]


def test_character_persona_is_injected(client, stub):
    r = client.post(
        "/api/v1/chat", json={"message": "你是谁", "character_key": "shenzhou"}
    )
    assert r.status_code == 200
    conv = r.json()["conversation_id"]
    assert conv


def test_memory_is_injected_into_context(client, db_session, monkeypatch):
    """写入一条记忆后，下一次请求的系统提示词里必须能看到它。"""
    from app import memory as mem
    from app import personas as p
    from app.llm.factory import set_provider as _set

    class Recording(MockProvider):
        def __init__(self):
            super().__init__()
            self.seen: list[list[LLMMessage]] = []

        async def chat(self, messages):  # noqa: ANN001
            self.seen.append(list(messages))
            return LLMResult(content="收到", model=MODEL_NAME, latency_ms=1)

    mem.record(db_session, scope="user_fact", content="用户叫小明",
               source_type=mem.SOURCE_USER_EXPLICIT)
    db_session.commit()

    recorder = Recording()
    _set(recorder)
    try:
        client.post("/api/v1/chat", json={"message": "还记得我吗"})
    finally:
        _set(None)

    assert recorder.seen, "模型应被调用"
    system_text = recorder.seen[-1][0].content
    assert "小明" in system_text


def test_token_usage_is_persisted(client, db_session, monkeypatch):
    from app.llm.base import LLMResult
    from app.llm.factory import set_provider as _set

    class Counting(MockProvider):
        async def chat(self, messages):  # noqa: ANN001
            return LLMResult(
                content="带用量的回复", model=MODEL_NAME, latency_ms=5,
                prompt_tokens=120, completion_tokens=30, total_tokens=150,
            )

    _set(Counting())
    try:
        body = client.post("/api/v1/chat", json={"message": "数一下 token"}).json()
    finally:
        _set(None)

    from app.models import Message

    msg = db_session.get(Message, body["assistant_message_id"])
    assert msg.tokens_prompt == 120
    assert msg.tokens_completion == 30
    assert msg.model == MODEL_NAME


def test_conversation_keeps_its_character(client, db_session, stub):
    from app import personas as p

    body = client.post(
        "/api/v1/chat", json={"message": "用祁鹿聊", "character_key": "qilu"}
    ).json()
    conv_id = body["conversation_id"]
    qilu = p.get_character(db_session, key="qilu")

    # 不指定 character_key 继续聊，应沿用同一人格
    client.post("/api/v1/chat", json={"message": "继续", "conversation_id": conv_id})
    listed = client.get("/api/v1/conversations").json()
    conv = next(c for c in listed if c["id"] == conv_id)
    assert conv["character_id"] == qilu.id


def test_switching_character_does_not_merge_personas(client, db_session):
    from app import personas as p

    conv = client.post(
        "/api/v1/conversations", params={"character_key": "linsui"}
    ).json()
    conv_id = conv["id"]
    linsui_id = conv["character_id"]

    switched = client.patch(
        f"/api/v1/conversations/{conv_id}/character?character_key=qilu"
    ).json()
    qilu = p.get_character(db_session, key="qilu")

    assert switched["character_id"] == qilu.id
    assert switched["character_id"] != linsui_id
    assert len({c.key for c in p.list_characters(db_session)}) >= 5
