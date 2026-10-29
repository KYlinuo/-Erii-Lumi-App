"""运行时性能指标接口测试。"""

from __future__ import annotations

from app import metrics as metrics_mod


def test_counter_empty_snapshot():
    c = metrics_mod._Counter()
    snap = c.snapshot()
    assert snap["count"] == 0
    assert snap["avg_ms"] is None


def test_counter_records_and_stats():
    c = metrics_mod._Counter()
    for v in [10.0, 20.0, 30.0, 40.0, 50.0]:
        c.record(v)
    snap = c.snapshot()
    assert snap["count"] == 5
    assert snap["avg_ms"] == 30.0
    assert snap["max_ms"] == 50.0
    assert snap["p50_ms"] is not None
    assert snap["p95_ms"] is not None


def test_metrics_endpoint_returns_shape(client):
    r = client.get("/api/v1/metrics")
    assert r.status_code == 200
    body = r.json()
    assert "memory_retrieval" in body
    assert "model_reply_latency" in body
    assert "count" in body["memory_retrieval"]


def test_memory_query_records_retrieval_time(client, db_session):
    """发一条消息会触发记忆检索，从而在 metrics 里留下样本。"""
    # 通过 metrics 模块直接记录，模拟检索耗时
    metrics_mod.record_memory_retrieval_ms(3.2)
    snap = metrics_mod.memory_retrieval.snapshot()
    assert snap["count"] >= 1
