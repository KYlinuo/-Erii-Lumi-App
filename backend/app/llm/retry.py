"""带退避重试的模型调用。

只对**可重试**的错误重试：超时、连接失败、5xx、上游限流。
不重试：未配置 Key（重试也没用）、Key 无效（重试只会更快被拒）、坏响应（通常也会再次坏）。

退避策略：0.4s → 0.8s → 1.6s… 并叠加少量抖动，避免多设备同时重发造成尖峰。
"""

from __future__ import annotations

import asyncio
import logging
import random

from app.llm.base import LLMMessage, LLMProvider, LLMResult
from app.llm.errors import (
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

logger = logging.getLogger("lumi.llm.retry")

# 可重试的错误
RETRYABLE: tuple[type[Exception], ...] = (
    ProviderTimeoutError,
    ProviderUnavailableError,
    ProviderRateLimitError,
)

BASE_DELAY = 0.4


def is_retryable(error: Exception) -> bool:
    return isinstance(error, RETRYABLE)


async def generate_with_retry(
    provider: LLMProvider,
    messages: list[LLMMessage],
    *,
    max_retries: int = 2,
    sleep=asyncio.sleep,
) -> LLMResult:
    """最多执行 1 + max_retries 次；全部失败后抛出**最后一次**的错误。"""
    attempt = 0
    last_error: Exception | None = None

    while attempt <= max_retries:
        try:
            return await provider.chat(messages)
        except ProviderError as exc:
            last_error = exc
            if not is_retryable(exc) or attempt == max_retries:
                raise
            delay = BASE_DELAY * (2**attempt) + random.uniform(0, 0.15)  # noqa: S311
            logger.warning(
                "上游调用失败(%s)，%.2fs 后重试（%d/%d）",
                exc.code,
                delay,
                attempt + 1,
                max_retries,
            )
            await sleep(delay)
            attempt += 1

    assert last_error is not None
    raise last_error
