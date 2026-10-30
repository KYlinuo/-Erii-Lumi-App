"""请求限流（滑动窗口）。"""

from __future__ import annotations

from app.config import get_settings, reload_settings
from app.ratelimit import SlidingWindowLimiter, get_limiter
from tests.conftest import StubProvider


def _reconfigure(monkeypatch, chat_limit: int, global_limit: int):
    monkeypatch.setenv("LUMI_CHAT_RATE_LIMIT_PER_MINUTE", str(chat_limit))
    monkeypatch.setenv("LUMI_RATE_LIMIT_PER_MINUTE", str(global_limit))
    reload_settings()
    get_limiter().reset()


def test_chat_limit_enforced(monkeypatch, client, stub):
    _reconfigure(monkeypatch, chat_limit=3, global_limit=1000)
    codes = [client.post("/api/v1/chat", json={"message": f"m{i}"}).status_code for i in range(5)]
    assert codes == [200, 200, 200, 429, 429]


def test_rate_limited_response_shape(monkeypatch, client, stub):
    _reconfigure(monkeypatch, chat_limit=1, global_limit=1000)
    client.post("/api/v1/chat", json={"message": "first"})
    r = client.post("/api/v1/chat", json={"message": "second"})
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1


def test_global_limit_applies_to_history(monkeypatch, client):
    _reconfigure(monkeypatch, chat_limit=1000, global_limit=2)
    codes = [client.get("/api/v1/conversations").status_code for _ in range(4)]
    assert codes == [200, 200, 429, 429]


def test_limits_are_independent_per_scope(monkeypatch, client, stub):
    _reconfigure(monkeypatch, chat_limit=1, global_limit=1)
    assert client.post("/api/v1/chat", json={"message": "x"}).status_code == 200
    # chat 配额耗尽，但 default 作用域仍有余量
    assert client.get("/api/v1/conversations").status_code == 200
    assert client.post("/api/v1/chat", json={"message": "y"}).status_code == 429


def test_limiter_window_expires(monkeypatch, client, stub):
    limiter = get_limiter()
    limiter.reset()
    _reconfigure(monkeypatch, chat_limit=2, global_limit=1000)
    first = client.post("/api/v1/chat", json={"message": "1"})
    assert first.status_code == 200
    limiter.reset("chat:testclient")  # 模拟窗口滚动
    assert client.post("/api/v1/chat", json={"message": "2"}).status_code == 200


def test_sliding_window_unit():
    limiter = SlidingWindowLimiter()
    assert limiter.check("k", 2)[0] is True
    assert limiter.check("k", 2)[0] is True
    allowed, used, retry = limiter.check("k", 2)
    assert allowed is False
    assert used == 2
    assert retry > 0


def test_zero_limit_disables_throttling():
    limiter = SlidingWindowLimiter()
    assert all(limiter.check("z", 0)[0] for _ in range(100))


def test_settings_defaults_present():
    settings = get_settings()
    assert settings.rate_limit_per_minute >= 1
    assert settings.chat_rate_limit_per_minute >= 1
