"""OpenAI 兼容 Chat Completions 适配器。

DeepSeek、Moonshot、通义、OpenAI、以及任何兼容 /chat/completions 的网关
（含本地 vLLM / Ollama 的 OpenAI 兼容端口）都可直接使用本实现。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncIterator

import httpx

from app.llm.base import LLMMessage, LLMProvider, LLMResult
from app.llm.errors import (
    ProviderAuthError,
    ProviderBadResponse,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

logger = logging.getLogger("lumi.llm")

# 模型服务返回的错误也一并脱敏，避免把 key 回显给客户端
_MAX_ERROR_LEN = 300


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        model: str,
        api_key: str | None,
        timeout: float = 60.0,
        temperature: float = 0.8,
        max_tokens: int = 1024,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = client

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    @property
    def endpoint(self) -> str:
        base = self.base_url
        # 允许 base_url 已经包含 /v1
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    async def chat(self, messages: list[LLMMessage]) -> LLMResult:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        own_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout)
        started = time.perf_counter()
        try:
            resp = await client.post(self.endpoint, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                detail=f"超过 {self.timeout:.0f}s 未收到响应（{self.name}）。"
            ) from exc
        except httpx.ConnectError as exc:
            raise ProviderUnavailableError(
                detail=f"无法建立到 {self.endpoint} 的连接，可能是断网或被防火墙拦截。"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(detail=f"网络请求失败：{type(exc).__name__}") from exc
        finally:
            if own_client:
                await client.aclose()
            self._last_latency_ms = int((time.perf_counter() - started) * 1000)

        if resp.status_code in (401, 403):
            raise ProviderAuthError()
        if resp.status_code == 429:
            raise ProviderRateLimitError()
        if resp.status_code >= 500:
            raise ProviderUnavailableError(
                detail=f"上游返回 HTTP {resp.status_code}。"
            )
        if resp.status_code >= 400:
            raise ProviderBadResponse(detail=self._safe_body(resp))

        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
        except Exception as exc:
            raise ProviderBadResponse(detail=self._safe_body(resp)) from exc

        if not isinstance(content, str) or not content.strip():
            raise ProviderBadResponse(detail="上游返回了空内容。")

        usage = data.get("usage") or {}
        return LLMResult(
            content=content.strip(),
            model=data.get("model", self.model),
            latency_ms=self._last_latency_ms,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )

    async def chat_stream(self, messages: list[LLMMessage]) -> AsyncIterator[str]:
        """流式返回内容增量（只产出正文片段，不含元数据）。

        与 chat() 共用同一套请求头与端点，`stream: true`。
        错误处理策略与 chat() 一致，但流式中途出错时抛出的异常由
        路由层决定是否截断响应。
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        own_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout)
        started = time.perf_counter()
        try:
            async with client.stream(
                "POST", self.endpoint, json=payload, headers=headers
            ) as resp:
                if resp.status_code in (401, 403):
                    raise ProviderAuthError()
                if resp.status_code == 429:
                    raise ProviderRateLimitError()
                if resp.status_code >= 500:
                    raise ProviderUnavailableError(
                        detail=f"上游返回 HTTP {resp.status_code}。"
                    )
                if resp.status_code >= 400:
                    raise ProviderBadResponse(detail=self._safe_body(resp))

                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    piece = delta.get("content")
                    if piece:
                        yield piece
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                detail=f"超过 {self.timeout:.0f}s 未收到响应（{self.name}）。"
            ) from exc
        except httpx.ConnectError as exc:
            raise ProviderUnavailableError(
                detail=f"无法建立到 {self.endpoint} 的连接，可能是断网或被防火墙拦截。"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(detail=f"网络请求失败：{type(exc).__name__}") from exc
        finally:
            if own_client:
                await client.aclose()
            self._last_latency_ms = int((time.perf_counter() - started) * 1000)

    @staticmethod
    def _safe_body(resp: httpx.Response) -> str:
        try:
            text = resp.text[:_MAX_ERROR_LEN]
        except Exception:  # pragma: no cover
            text = "<unreadable>"
        return f"HTTP {resp.status_code}: {text}"
