"""轻量运行时指标计数器。

不引入 Prometheus 之类的外部依赖，只在进程内维护一个环形缓冲，
记录「记忆检索耗时」与「模型调用延迟」的最近样本，供 /metrics 接口
返回平均值 / 分位数 / 采样数。

用途：为上下文优化提供基准——记忆检索变慢说明注入过多，
模型延迟升高说明窗口太长。样本只在进程生命周期内有效，重启清零。
"""

from __future__ import annotations

import threading
import time
from collections import deque

_MAX_SAMPLES = 512


class _Counter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._samples: deque[float] = deque(maxlen=_MAX_SAMPLES)

    def record(self, value_ms: float) -> None:
        with self._lock:
            self._samples.append(value_ms)

    def snapshot(self) -> dict:
        with self._lock:
            samples = list(self._samples)
        if not samples:
            return {"count": 0, "avg_ms": None, "p50_ms": None, "p95_ms": None, "max_ms": None}
        ordered = sorted(samples)
        n = len(ordered)

        def _pct(p: float) -> float:
            idx = min(n - 1, int(p * n))
            return round(ordered[idx], 1)

        return {
            "count": n,
            "avg_ms": round(sum(samples) / n, 1),
            "p50_ms": _pct(0.50),
            "p95_ms": _pct(0.95),
            "max_ms": round(ordered[-1], 1),
        }


# 记忆检索耗时（从 query_memories 入口到返回）
memory_retrieval = _Counter()
# 模型调用延迟（provider.chat 全链路）
model_latency = _Counter()


def record_memory_retrieval_ms(ms: float) -> None:
    memory_retrieval.record(ms)


def record_model_latency_ms(ms: float) -> None:
    model_latency.record(ms)
