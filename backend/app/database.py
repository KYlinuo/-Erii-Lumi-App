"""SQLAlchemy 引擎 / 会话管理（SQLite）。"""

from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _build_engine(db_url: str) -> Engine:
    kwargs: dict = {"future": True}
    if ":memory:" in db_url or "mode=memory" in db_url:
        # 内存库必须复用同一连接，否则每个 Session 看到的是不同的空库
        kwargs.update(poolclass=StaticPool, connect_args={"check_same_thread": False})
    elif db_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}

    engine = create_engine(db_url, **kwargs)

    if db_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _record):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

    return engine


def init_engine(db_url: str | None = None, force: bool = False) -> Engine:
    """初始化全局引擎。测试可传入 sqlite:///:memory: 强制重建。"""
    global _engine, _session_factory
    if _engine is not None and not force and db_url is None:
        return _engine

    if db_url is None:
        path = get_settings().resolved_db_path
        db_url = f"sqlite:///{path.as_posix()}"

    _engine = _build_engine(db_url)
    _session_factory = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        init_engine()
    assert _engine is not None
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    if _session_factory is None:
        init_engine()
    assert _session_factory is not None
    return _session_factory


def create_all() -> None:
    import app.models  # noqa: F401  保证模型已注册

    Base.metadata.create_all(bind=get_engine())


def get_db():
    """FastAPI 依赖：每请求一个会话。"""
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()
