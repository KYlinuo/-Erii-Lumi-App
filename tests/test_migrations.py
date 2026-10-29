"""数据库迁移：旧库必须**原地升级**，绝不删库，且可重复执行。"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from app import migrations
from app.database import get_session_factory, init_engine


def _make_v01_db(path: Path) -> None:
    """手工造一个 v0.1 结构 + 真实数据的数据库（模拟用户手里已有的库）。"""
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE conversations (
            id VARCHAR(64) PRIMARY KEY,
            title VARCHAR(200),
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        );
        CREATE TABLE messages (
            id VARCHAR(64) PRIMARY KEY,
            conversation_id VARCHAR(64) NOT NULL,
            role VARCHAR(16) NOT NULL,
            content TEXT NOT NULL,
            status VARCHAR(16),
            model VARCHAR(64),
            error_code VARCHAR(64),
            latency_ms INTEGER,
            created_at TIMESTAMP
        );
        """
    )
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO conversations VALUES ('c1','老对话',?,?)", (now, now)
    )
    for idx, (role, content) in enumerate(
        [("user", "第一条老消息"), ("assistant", "老回复"), ("user", "第二条老消息")]
    ):
        conn.execute(
            "INSERT INTO messages VALUES (?, 'c1', ?, ?, 'ok', 'old-model', NULL, 10, ?)",
            (f"m{idx}", role, content, f"2026-10-2{idx % 9}T00:00:00+00:00"),
        )
    conn.commit()
    conn.close()


def test_legacy_v01_database_upgrades_in_place(tmp_path):
    db_file = tmp_path / "legacy.db"
    _make_v01_db(db_file)

    engine = init_engine(f"sqlite:///{db_file.as_posix()}", force=True)
    applied = None
    from app import database

    with engine.begin() as conn:
        applied = migrations.run_migrations(conn)
    assert applied, "首次运行必须实际应用迁移"

    with engine.begin() as conn:
        tables = {r[0] for r in conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'"))}
        for expected in ("users", "devices", "characters", "memory_records",
                        "world_events", "media_assets", "proactive_messages",
                        "device_cursors", "schema_migrations"):
            assert expected in tables, f"缺少新表 {expected}"

        conv_cols = {r[1] for r in conn.execute(text("PRAGMA table_info(conversations)"))}
        assert {"user_id", "character_id", "origin_device_id"} <= conv_cols

        msg_cols = {r[1] for r in conn.execute(text("PRAGMA table_info(messages)"))}
        assert {"request_id", "conv_seq", "client_ts", "deleted_at"} <= msg_cols

        # ---- 老数据必须原封不动 ----
        rows = list(conn.execute(
            text("SELECT id, role, content FROM messages ORDER BY created_at")))
        assert [r[2] for r in rows] == ["第一条老消息", "老回复", "第二条老消息"]

    database.init_db(force=True)


def test_legacy_rows_get_backfilled_sync_cursor(tmp_path):
    db_file = tmp_path / "legacy2.db"
    _make_v01_db(db_file)

    engine = init_engine(f"sqlite:///{db_file.as_posix()}", force=True)
    with engine.begin() as conn:
        migrations.run_migrations(conn)
        seqs = [r[0] for r in conn.execute(
            text("SELECT conv_seq FROM messages ORDER BY created_at, id"))]
        assert seqs == [1, 2, 3], "老消息必须按时间回填单调递增游标"


def test_migrations_are_idempotent(tmp_path):
    db_file = tmp_path / "legacy3.db"
    _make_v01_db(db_file)
    engine = init_engine(f"sqlite:///{db_file.as_posix()}", force=True)

    with engine.begin() as conn:
        first = migrations.run_migrations(conn)
    with engine.begin() as conn:
        second = migrations.run_migrations(conn)
        third = migrations.run_migrations(conn)

    assert first and second == [] and third == []
    with engine.begin() as conn:
        versions = sorted(r[0] for r in conn.execute(
            text("SELECT version FROM schema_migrations")))
    assert versions == ["2026102701", "2026102702", "2026102801", "2026102901", "2026102902", "2026102903", "2026102904"]


def test_orm_can_read_migrated_schema(tmp_path):
    """迁移后 ORM 必须能正常读写所有新字段（防止 DDL 与模型漂移）。"""
    db_file = tmp_path / "legacy4.db"
    _make_v01_db(db_file)
    engine = init_engine(f"sqlite:///{db_file.as_posix()}", force=True)
    with engine.begin() as conn:
        migrations.run_migrations(conn)

    factory = get_session_factory()
    with factory() as db:
        from app import personas
        from app.identity import ensure_default_user
        from app.models import Message

        user = ensure_default_user(db)
        assert user.id

        personas.seed_characters(db)
        db.commit()
        character = personas.resolve_character(db, "erii")
        assert character.name == "绘梨衣"

        msg = db.execute(
            text("SELECT id FROM messages WHERE content='第一条老消息'")
        ).scalar_one()
        row = db.get(Message, msg)
        assert row is not None
        row.request_id = "req-legacy"
        row.conv_seq = 99
        db.commit()

        reloaded = db.get(Message, msg)
        assert reloaded.request_id == "req-legacy"
        assert reloaded.conv_seq == 99
