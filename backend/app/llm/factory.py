"""按配置构造模型适配器。测试可通过 set_provider() 注入桩实现。"""

from __future__ import annotations

from app.config import get_settings
from app.llm.base import LLMProvider
from app.llm.openai_compat import OpenAICompatibleProvider

_provider: LLMProvider | None = None


def build_provider() -> LLMProvider:
    s = get_settings()
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


__all__ = ["build_provider", "get_provider", "set_provider"]
