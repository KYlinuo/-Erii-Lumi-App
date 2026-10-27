"""按配置构造模型适配器。测试可通过 set_provider() 注入桩实现。

工厂规则：
    1. 注入优先（测试与运行时切换）；
    2. `LUMI_PROVIDER=mock` → MockProvider（明确知道自己用的是 Mock）；
    3. 配置了 `LUMI_API_KEY` → 真实 OpenAI 兼容适配器（DeepSeek / OpenAI / Gemini 兼容网关…）；
    4. 没配 Key → **仍然返回 OpenAI 兼容适配器**，由它在 `is_configured()`
       返回 False，调用方据此返回 `503 provider_not_configured`。

第 4 点是刻意设计：**绝不在用户不知情的情况下悄悄用 Mock 顶替真实模型**。
Mock 只在显式配置 `LUMI_PROVIDER=mock` 时启用。
"""

from __future__ import annotations

from app.config import get_settings
from app.llm.base import LLMProvider
from app.llm.mock import MockProvider
from app.llm.openai_compat import OpenAICompatibleProvider

_provider: LLMProvider | None = None


def build_provider() -> LLMProvider:
    s = get_settings()
    if s.provider.lower() == "mock":
        return MockProvider()

    return OpenAICompatibleProvider(
        name=s.provider,
        base_url=s.provider_base_url,
        model=s.provider_model,
        api_key=s.api_key,
        timeout=s.provider_timeout_seconds,
    )


def get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = build_provider()
    return _provider


def set_provider(provider: LLMProvider | None) -> None:
    """注入/清除适配器（测试与运行时切换用）。"""
    global _provider
    _provider = provider


def is_mock_provider(provider: LLMProvider | None = None) -> bool:
    return isinstance(provider or get_provider(), MockProvider)


__all__ = ["build_provider", "get_provider", "set_provider", "is_mock_provider"]
