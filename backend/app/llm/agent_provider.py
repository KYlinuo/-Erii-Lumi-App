"""Agent Relay Provider —— 由「本次会话的智能体」充当模型。

用途：在没有 `LUMI_API_KEY` 的情况下，仍然跑通**完整真实链路**
（人格提示词组装 → 记忆注入 → 虚构世界注入 → 历史上下文 → 落库 → Token 记账），
只是生成回复的那一步由外部智能体（本次算力）完成，而不是远端模型 API。

工作方式（文件中继，纯本地，不联网）：
    1. `chat()` 把完整的 messages 写到 `<relay>/outbox/<key>.json`；
    2. 等待 `<relay>/inbox/<key>.json` 出现（由外部智能体写入）；
    3. 读回 `content` 作为模型输出返回。

诚实边界：
- `model` 固定为 `lumi-agent-relay`，写进每条消息的 `model` 字段，随时可查；
- `/health` 的 `is_mock` 会把它算作"非远端真实模型"；
- 它**不是** DeepSeek / OpenAI 的替代品，`LUMI_API_KEY` 配好之后仍应切回
  `OpenAICompatibleProvider`。

两种模式：
- `wait_seconds=0`：只投递 outbox 就抛出 `RelayPending`（收集阶段用）；
- `wait_seconds>0`：投递后轮询等待 inbox（投递阶段用）。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

from app.llm.base import LLMMessage, LLMProvider, LLMResult
from app.llm.errors import ProviderTimeoutError

logger = logging.getLogger("lumi.llm.relay")

MODEL_NAME = "lumi-agent-relay"


class RelayPending(Exception):
    """收集阶段：outbox 已写好，等待外部智能体回复。"""

    def __init__(self, key: str, outbox_path: Path) -> None:
        self.key = key
        self.outbox_path = outbox_path
        super().__init__(f"relay pending: {key}")


class AgentRelayProvider(LLMProvider):
    def __init__(
        self,
        relay_dir: str | Path,
        *,
        wait_seconds: float = 0.0,
        poll_interval: float = 0.5,
    ) -> None:
        self.name = "agent-relay"
        self.model = MODEL_NAME
        self.relay_dir = Path(relay_dir)
        self.outbox = self.relay_dir / "outbox"
        self.inbox = self.relay_dir / "inbox"
        self.outbox.mkdir(parents=True, exist_ok=True)
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.wait_seconds = wait_seconds
        self.poll_interval = poll_interval
        self.calls: list[list[LLMMessage]] = []

    def is_configured(self) -> bool:
        """中继不需要任何密钥。"""
        return True

    @staticmethod
    def key_for(messages: list[LLMMessage]) -> str:
        """以「最后一条用户消息」作为中继键。

        刻意**不**把 system / 历史算进去：系统会注入当前时间与记忆，
        每次调用都略有不同；如果把它们算进 hash，同一个问题的回复就无法复用，
        外部智能体就得反复回答同一句话。
        """
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"),
            "",
        )
        payload = last_user or "\n".join(f"{m.role}:{m.content}" for m in messages)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def _write_outbox(self, key: str, messages: list[LLMMessage]) -> Path:
        path = self.outbox / f"{key}.json"
        body: dict[str, Any] = {
            "key": key,
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "created_at": time.time(),
        }
        path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def _read_inbox(self, key: str) -> dict[str, Any] | None:
        path = self.inbox / f"{key}.json"
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None
        if not isinstance(data.get("content"), str) or not data["content"].strip():
            return None
        return data

    async def chat(self, messages: list[LLMMessage]) -> LLMResult:
        started = time.perf_counter()
        self.calls.append(list(messages))

        key = self.key_for(messages)
        outbox_path = self._write_outbox(key, messages)
        logger.info("relay outbox written: %s", outbox_path.name)

        if self.wait_seconds <= 0:
            raise RelayPending(key, outbox_path)

        deadline = time.monotonic() + self.wait_seconds
        while time.monotonic() < deadline:
            data = self._read_inbox(key)
            if data is not None:
                latency = max(int((time.perf_counter() - started) * 1000), 1)
                content = data["content"].strip()
                usage = data.get("usage") or {}
                prompt_chars = sum(len(m.content) for m in messages)
                return LLMResult(
                    content=content,
                    model=data.get("model", self.model),
                    latency_ms=latency,
                    prompt_tokens=usage.get("prompt_tokens", max(1, prompt_chars // 2)),
                    completion_tokens=usage.get("completion_tokens", max(1, len(content) // 2)),
                    total_tokens=usage.get("total_tokens", max(1, (prompt_chars + len(content)) // 2)),
                )
            await asyncio.sleep(self.poll_interval)

        raise ProviderTimeoutError(detail=f"中继等待超时（{self.wait_seconds:.0f}s）：{key}")


def pending_requests(relay_dir: str | Path) -> list[dict[str, Any]]:
    """列出所有还没有收到回复的请求（按创建时间升序）。"""
    relay = Path(relay_dir)
    inbox = relay / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    outbox = relay / "outbox"
    if not outbox.is_dir():
        return []
    items = []
    for path in sorted(outbox.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if (inbox / path.name).is_file():
            continue
        items.append(data)
    return items


def write_reply(relay_dir: str | Path, key: str, content: str, model: str = MODEL_NAME) -> Path:
    """外部智能体写回回复。"""
    relay = Path(relay_dir)
    inbox = relay / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    path = inbox / f"{key}.json"
    chars = len(content)
    path.write_text(
        json.dumps(
            {
                "key": key,
                "model": model,
                "content": content,
                "usage": {
                    "prompt_tokens": None,
                    "completion_tokens": max(1, chars // 2),
                    "total_tokens": None,
                },
                "answered_at": time.time(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path
