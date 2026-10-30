"""开发用替代实现：仅在显式配置 LUMI_PROVIDER=mock 时启用。

诚实边界（重要）：
- 它的 `model` 固定为 `mock-provider-v1`，并会被写进 `messages.model` 字段，
  因此任何一条回复都能被追查到「这是 Mock 生成的，不是真实模型输出」；
- `/health` 也会如实上报 `provider=mock`、`provider_configured=true`、
  并额外返回 `is_mock=true`；
- 一旦配置了真实 Key，工厂会优先构造真实适配器，Mock 不会偷偷顶替。

也就是说它只用于联调管线，不会被伪装成真实 AI 回复。
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Sequence

from app.llm.base import LLMMessage, LLMProvider, LLMResult

MODEL_NAME = "mock-provider-v1"

_OPENERS = (
    "嗯，我听清楚了：",
    "好，那我接着你说的",
    "这件事我想了一下，",
    "嗯……关于你说的，",
    "收到。关于",
)
_BODIES = (
    "我可以陪你把它理顺一点，你先说说最卡住的地方？",
    "我的感觉是事情没那么糟，但要一步步来。",
    "如果要我选，我会先做最简单那步，别一开始就给自己太大压力。",
    "我不太想敷衍你，所以先问清楚：你是想要建议，还是只想有人听你说？",
    "那就慢慢来吧，反正在我这里不用着急。",
    "我会把它记下来，免得下次又从头讲一遍。",
)

class MockProvider(LLMProvider):
    """确定性回答：同样的输入永远得到同样的输出，方便回放与测试。"""

    def __init__(self, replies: Sequence[str] | None = None, latency_ms: int = 8) -> None:
        self.name = "mock"
        self.model = MODEL_NAME
        self.replies = list(replies) if replies else []
        self.latency_ms = latency_ms
        self.calls: list[list[LLMMessage]] = []

    def is_configured(self) -> bool:
        """Mock 永远可用（不需要任何密钥）。"""
        return True

    def _reply_for(self, messages: list[LLMMessage]) -> str:
        if self.replies:
            # 脚本化回复：每次取一条，用完后保留最后一条
            if len(self.replies) > 1:
                return self.replies.pop(0)
            return self.replies[0]

        last = next((m for m in reversed(messages) if m.role == "user"), None)
        text = (last.content.strip() if last else "") or "（空）"
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        opener = _OPENERS[digest[0] % len(_OPENERS)]
        body = _BODIES[digest[1] % len(_BODIES)]
        return f"{opener}{text[:40]}。{body}"

    async def chat(self, messages: list[LLMMessage]) -> LLMResult:
        started = time.perf_counter()
        self.calls.append(list(messages))
        await asyncio.sleep(0)  # 让出事件循环，保持真实的 async 语义
        content = self._reply_for(messages)
        latency = max(int((time.perf_counter() - started) * 1000), self.latency_ms)

        prompt_chars = sum(len(m.content) for m in messages)
        return LLMResult(
            content=content,
            model=self.model,
            latency_ms=latency,
            # 粗略估算（非真实计费口径），仅用于让上层统计逻辑可被测试
            prompt_tokens=max(1, prompt_chars // 2),
            completion_tokens=max(1, len(content) // 2),
            total_tokens=max(1, (prompt_chars + len(content)) // 2),
        )

    @property
    def is_mock(self) -> bool:
        return True
