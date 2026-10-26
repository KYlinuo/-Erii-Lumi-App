"""pytest 公共夹具。

关键约束：
1. 每个测试使用独立的 SQLite（内存或 tmp_path 文件），互不污染；
2. 测试中**注入桩模型适配器**，绝不调用真实 DeepSeek API（不花钱、不依赖网络）；
3. 认证与限流通过环境变量开启，验证真实的中间件行为。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app import database  # noqa: E402
from app.config import get_settings, reload_settings  # noqa: E402
from app.database import create_all, init_engine  # noqa: E402
from app.llm.base import LLMMessage, LLMProvider, LLMResult  # noqa: E402
from app.llm import factory as llm_factory  # noqa: E402
from app.llm import errors as llm_errors  # noqa: E402

TEST_TOKEN = "test-access-token-0123456789abcdef"


class StubProvider(LLMProvider):
    """可控的桩适配器：记录请求、可抛出任意上游错误。"""

    def __init__(self, reply: str = "这是来自桩模型的回复。", raise_exc: Exception | None = None):
        self.name = "stub"
        self.model = "stub-model-v1"
        self.reply = reply
        self.raise_exc = raise_exc
        self.calls: list[list[LLMMessage]] = []

    def is_configured(self) -> bool:
        return self.raise_exc is None or not isinstance(self.raise_exc, llm_errors.ProviderNotConfigured)

    async def chat(self, messages: list[LLMMessage]) -> LLMResult:
        self.calls.append(messages)
        if self.raise_exc is not None:
            raise self.raise_exc
        return LLMResult(content=self.reply, model=self.model, latency_ms=12)


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    """为所有测试准备干净的环境变量与内存数据库。"""
    monkeypatch.setenv("LUMI_ENV", "dev")
    monkeypatch.delenv("LUMI_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("LUMI_API_KEY", raising=False)
    monkeypatch.setenv("LUMI_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("LUMI_RATE_LIMIT_PER_MINUTE", "1000")
    monkeypatch.setenv("LUMI_CHAT_RATE_LIMIT_PER_MINUTE", "1000")
    monkeypatch.setenv("LUMI_CORS_ORIGINS", "")
    monkeypatch.setenv("LUMI_PROVIDER", "stub")
    monkeypatch.setenv("LUMI_PROVIDER_MODEL", "stub-model-v1")
    monkeypatch.setenv("LUMI_PROVIDER_BASE_URL", "http://stub.invalid")
    monkeypatch.delenv("LUMI_SYSTEM_PROMPT", raising=False)

    reload_settings()
    settings = get_settings()
    init_engine(f"sqlite:///{Path(settings.resolved_db_path).as_posix()}", force=True)
    create_all()
    llm_factory.set_provider(None)

    yield

    llm_factory.set_provider(None)
    from app.ratelimit import get_limiter

    get_limiter().reset()


@pytest.fixture
def db_session():
    """直接操作 ORM 的会话。"""
    factory = database.get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def stub(monkeypatch) -> StubProvider:
    provider = StubProvider()
    llm_factory.set_provider(provider)
    return provider


@pytest.fixture
def client():
    """已触发生命周期的 TestClient。"""
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def authed_client(monkeypatch):
    """开启单用户认证后的客户端。

    注意：httpx 会把 per-request headers 与 client 默认 headers **合并**，
    因此这里刻意不设置默认头，由测试显式传入 auth_headers，才能真实模拟「没带 token」。
    """
    from fastapi.testclient import TestClient

    from app.main import create_app

    monkeypatch.setenv("LUMI_ACCESS_TOKEN", TEST_TOKEN)
    reload_settings()
    init_engine("sqlite:///:memory:", force=True)
    create_all()

    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-LUMI-TOKEN": TEST_TOKEN}
