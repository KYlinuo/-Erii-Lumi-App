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
# 运行时模型覆盖：通过 POST /api/v1/model 切换，无需重启。
# 为空时回落到配置里的 provider_model（默认 deepseek-flash）。
_model_override: str | None = None


def build_provider() -> LLMProvider:
    s = get_settings()
    if s.provider.lower() == "mock":
        return MockProvider()

    return OpenAICompatibleProvider(
        name=s.provider,
        base_url=s.provider_base_url,
        model=current_model(),
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


def current_model() -> str:
    """当前生效的模型名：运行时覆盖优先，否则回落配置。"""
    return _model_override or get_settings().provider_model


def set_model(model: str | None) -> str:
    """切换模型名（运行时覆盖）。返回切换后的模型名。"""
    global _model_override, _provider
    _model_override = (model or "").strip() or None
    _provider = None  # 强制下次调用时按新模型重建
    return current_model()


def reset_model() -> str:
    """清除运行时覆盖，回到配置文件里的默认模型。"""
    return set_model(None)


def is_mock_provider(provider: LLMProvider | None = None) -> bool:
    return isinstance(provider or get_provider(), MockProvider)


__all__ = [
    "build_provider",
    "get_provider",
    "set_provider",
    "current_model",
    "set_model",
    "reset_model",
    "is_mock_provider",
]
