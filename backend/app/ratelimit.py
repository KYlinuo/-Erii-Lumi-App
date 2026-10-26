"""内存滑动窗口限流（单进程部署足够；多实例请换 Redis）。"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque

from fastapi import Depends, HTTPException, Request, status

from app.config import get_settings

logger = logging.getLogger("lumi.ratelimit")

DEFAULT_LIMIT = 30
DEFAULT_WINDOW = 60.0


class SlidingWindowLimiter:
    """线程安全的滑动窗口计数器。"""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window: float = DEFAULT_WINDOW) -> tuple[bool, int, float]:
        """返回 (是否放行, 当前窗口内已用次数, 建议重试等待秒数)。"""
        if limit <= 0:
            return True, 0, 0.0
        now = time.monotonic()
        with self._lock:
            bucket = self._hits.setdefault(key, deque())
            cutoff = now - window
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(0.0, window - (now - bucket[0]))
                return False, len(bucket), retry_after
            bucket.append(now)
            return True, len(bucket) + 1, 0.0

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)


_limiter = SlidingWindowLimiter()


def get_limiter() -> SlidingWindowLimiter:
    return _limiter


def client_key(request: Request) -> str:
    """优先使用反向代理传递的真实 IP。"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(scope: str = "default"):
    """按 scope 取对应配额的限流依赖。"""

    def _dependency(request: Request) -> None:
        settings = get_settings()
        if scope == "chat":
            limit = settings.chat_rate_limit_per_minute
        else:
            limit = settings.rate_limit_per_minute

        allowed, used, retry_after = _limiter.check(f"{scope}:{client_key(request)}", limit)
        if not allowed:
            logger.warning("rate limit exceeded scope=%s used=%s", scope, used)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "rate_limited",
                    "message": f"请求过于频繁（{scope} 每分钟上限 {limit} 次）。",
                    "hint": f"请 {max(1, int(retry_after))} 秒后重试。",
                },
                headers={"Retry-After": str(max(1, int(retry_after)))},
            )

    return Depends(_dependency)


__all__ = ["SlidingWindowLimiter", "get_limiter", "rate_limit", "client_key"]
