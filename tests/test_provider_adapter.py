"""OpenAI 兼容适配器：用 httpx MockTransport 模拟真实上游（不发真实网络请求）。"""

from __future__ import annotations

import json

import httpx
import pytest

from app.llm import errors as llm_errors
from app.llm.base import LLMMessage
from app.llm.openai_compat import OpenAICompatibleProvider


def _provider(handler, *, api_key="sk-test-1234567890", timeout=5.0) -> OpenAICompatibleProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, timeout=timeout)
    return OpenAICompatibleProvider(
        name="deepseek",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        api_key=api_key,
        timeout=timeout,
        client=client,
    )


def _ok(payload: dict) -> httpx.Response:
    return httpx.Response(200, json=payload)


def _default_payload() -> dict:
    return {
        "id": "chatcmpl-1",
        "model": "deepseek-chat",
        "choices": [{"message": {"role": "assistant", "content": "你好呀～"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


@pytest.mark.asyncio
async def test_successful_call_parses_reply():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return _ok(_default_payload())

    p = _provider(handler)
    result = await p.chat([LLMMessage(role="user", content="你好")])

    assert result.content == "你好呀～"
    assert result.model == "deepseek-chat"
    assert result.total_tokens == 15
    assert result.latency_ms >= 0
    assert captured["url"] == "https://api.deepseek.com/v1/chat/completions"
    assert captured["auth"] == "Bearer sk-test-1234567890"
    assert captured["body"]["model"] == "deepseek-chat"


@pytest.mark.asyncio
async def test_base_url_already_containing_v1():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.deepseek.com/v1/chat/completions"
        return _ok(_default_payload())

    p = _provider(handler)
    p.base_url = "https://api.deepseek.com/v1"
    await p.chat([LLMMessage(role="user", content="x")])


@pytest.mark.asyncio
async def test_missing_api_key_is_reported_not_guessed():
    p = _provider(lambda r: _ok(_default_payload()), api_key="")
    assert p.is_configured() is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_code,expected",
    [
        (401, llm_errors.ProviderAuthError),
        (403, llm_errors.ProviderAuthError),
        (429, llm_errors.ProviderRateLimitError),
        (500, llm_errors.ProviderUnavailableError),
        (503, llm_errors.ProviderUnavailableError),
        (400, llm_errors.ProviderBadResponse),
    ],
)
async def test_http_status_mapping(status_code, expected):
    p = _provider(lambda r: httpx.Response(status_code, text="boom"))
    with pytest.raises(expected):
        await p.chat([LLMMessage(role="user", content="x")])


@pytest.mark.asyncio
async def test_timeout_maps_to_timeout_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout", request=request)

    p = _provider(handler, timeout=0.01)
    with pytest.raises(llm_errors.ProviderTimeoutError) as exc:
        await p.chat([LLMMessage(role="user", content="x")])
    assert exc.value.http_status == 504


@pytest.mark.asyncio
async def test_connect_error_maps_to_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no network", request=request)

    p = _provider(handler)
    with pytest.raises(llm_errors.ProviderUnavailableError) as exc:
        await p.chat([LLMMessage(role="user", content="x")])
    assert exc.value.http_status == 503


@pytest.mark.asyncio
async def test_malformed_payload_is_bad_response():
    p = _provider(lambda r: httpx.Response(200, json={"unexpected": True}))
    with pytest.raises(llm_errors.ProviderBadResponse):
        await p.chat([LLMMessage(role="user", content="x")])


@pytest.mark.asyncio
async def test_empty_content_is_bad_response():
    payload = _default_payload()
    payload["choices"][0]["message"]["content"] = "   "
    p = _provider(lambda r: httpx.Response(200, json=payload))
    with pytest.raises(llm_errors.ProviderBadResponse):
        await p.chat([LLMMessage(role="user", content="x")])


@pytest.mark.asyncio
async def test_error_body_is_truncated():
    p = _provider(lambda r: httpx.Response(400, text="E" * 5000))
    with pytest.raises(llm_errors.ProviderBadResponse) as exc:
        await p.chat([LLMMessage(role="user", content="x")])
    assert len(exc.value.detail) < 400


@pytest.mark.asyncio
async def test_error_messages_do_not_leak_api_key():
    p = _provider(lambda r: httpx.Response(400, text="bad request"), api_key="sk-leakme-9999")
    with pytest.raises(llm_errors.ProviderBadResponse) as exc:
        await p.chat([LLMMessage(role="user", content="x")])
    assert "sk-leakme" not in str(exc.value.detail)
