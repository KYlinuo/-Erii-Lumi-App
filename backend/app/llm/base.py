"""模型适配器抽象接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class LLMMessage:
    role: str  # system | user | assistant
    content: str


@dataclass
class LLMResult:
    content: str
    model: str
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class LLMProvider(ABC):
    """任何 OpenAI 兼容服务只要实现本接口即可接入 LUMI。"""

    name: str = "base"
    model: str = "unknown"

    @abstractmethod
    async def chat(self, messages: list[LLMMessage]) -> LLMResult: ...

    async def chat_stream(self, messages: list[LLMMessage]) -> AsyncIterator[str]:
        """默认实现：不支持流式的 provider 退化为一次性返回完整内容。

        子类（如 OpenAICompatibleProvider）可覆盖为真正的 SSE 增量。
        """
        result = await self.chat(messages)
        yield result.content

    @abstractmethod
    def is_configured(self) -> bool: ...
