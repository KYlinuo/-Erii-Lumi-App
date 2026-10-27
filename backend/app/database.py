"""SQLAlchemy 引擎 / 会话管理（SQLite，保留迁移到 PostgreSQL 的能力）。"""

from __future__ import annotations

import logging
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings

logger = logging.getLogger("lumi.database")


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


def _run_migrations(engine: Engine) -> list[str]:
    """先建全量表（新库），再执行增量迁移（老库），返回本次应用的迁移版本。"""
    from app import migrations  # 局部导入：避免模型 ↔ 迁移循环依赖
    import app.models  # noqa: F401  保证模型已注册到 Base.metadata

    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        return migrations.run_migrations(conn)


def create_all() -> None:
    """幂等：新库建表 + 老库迁移。绝不删库。"""
    engine = get_engine()
    applied = _run_migrations(engine)
    if applied:
        logger.info("已应用数据库迁移：%s", ", ".join(applied))
    else:
        logger.info("数据库结构已是最新，无需迁移")


def schema_version() -> str:
    """当前 schema 版本号，用于 /health 展示。"""
    with get_engine().begin() as conn:
        from app import migrations

        version = migrations.current_version(conn)
    return version or "unknown"


def init_db(db_url: str | None = None, force: bool = False) -> Engine:
    """完整初始化（引擎 + 迁移）。lifespan 与测试共用。"""
    engine = init_engine(db_url=db_url, force=force)
    _run_migrations(engine)
    return engine


def get_db():
    """FastAPI 依赖：每请求一个会话。"""
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Session:
    """脚本/后台任务使用的短生命周期会话，自动 commit/rollback。"""
    factory = get_session_factory()
    db = factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def ping_database() -> bool:
    """/health 用的轻量探活。"""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        logger.exception("database ping failed")
        return False
