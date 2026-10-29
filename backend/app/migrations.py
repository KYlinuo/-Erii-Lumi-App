"""版本化数据库迁移。

设计约束（来自夜间开发总指令）：
1. **绝不允许通过删除数据库解决结构问题** —— 旧库必须原地升级；
2. 每个迁移步骤幂等，重复执行无副作用（进程重启、多实例并发都安全）；
3. 应用情况记录在 `schema_migrations` 表，可追溯；
4. 迁移只写 DDL + 安全的回填 UPDATE，不删用户数据。

执行顺序（见 `app.database.init_db`）：
    1. `Base.metadata.create_all()` —— 全新库直接建到最新结构；
    2. `run_migrations()` —— 老库补齐缺失的列与表，并登记版本。

因此同一个步骤在新库会被跳过（列已存在），在老库才真正执行。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

logger = logging.getLogger("lumi.migrations")

META_TABLE = "schema_migrations"

Step = Callable[[Connection], None]
_MIGRATIONS: list[tuple[str, str, Step]] = []


def migration(version: str, description: str) -> Callable[[Step], Step]:
    """注册一个迁移步骤。version 用于排序，必须单调递增。"""

    def _wrap(fn: Step) -> Step:
        _MIGRATIONS.append((version, description, fn))
        return fn

    return _wrap


# ------------------------------------------------------------------ 元信息辅助


def _table_exists(conn: Connection, table: str) -> bool:
    row = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"), {"t": table}
    ).first()
    return row is not None


def _columns(conn: Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    rows = conn.execute(text(f'PRAGMA table_info("{table}")')).all()
    return {r[1] for r in rows}


def _index_exists(conn: Connection, name: str) -> bool:
    row = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='index' AND name=:n"), {"n": name}
    ).first()
    return row is not None


def _add_column(conn: Connection, table: str, column: str, decl: str) -> None:
    """列不存在时才 ADD COLUMN，避免重复执行报错。"""
    if column in _columns(conn, table):
        return
    logger.debug("migrate: %s.%s %s", table, column, decl)
    conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {decl}'))


def _create_index(conn: Connection, name: str, ddl: str) -> None:
    if _index_exists(conn, name):
        return
    conn.execute(text(ddl))


def _ensure_meta(conn: Connection) -> None:
    if not _table_exists(conn, META_TABLE):
        conn.execute(
            text(
                f"CREATE TABLE {META_TABLE} ("
                "version VARCHAR(32) PRIMARY KEY, "
                "description VARCHAR(255), "
                "applied_at TIMESTAMP)"
            )
        )


# ------------------------------------------------------------------ 执行入口


def current_version(conn: Connection) -> str | None:
    """已应用的最后一个迁移版本号（可能为 None）。"""
    if not _table_exists(conn, META_TABLE):
        return None
    rows = conn.execute(text(f"SELECT version FROM {META_TABLE}")).all()
    if not rows:
        return None
    return sorted(r[0] for r in rows)[-1]


def applied_versions(conn: Connection) -> set[str]:
    _ensure_meta(conn)
    return {r[0] for r in conn.execute(text(f"SELECT version FROM {META_TABLE}")).all()}


def run_migrations(conn: Connection) -> list[str]:
    """按版本号顺序执行尚未应用的迁移，返回本次实际应用的版本列表。"""
    done = applied_versions(conn)
    applied: list[str] = []
    for version, description, fn in sorted(_MIGRATIONS, key=lambda item: item[0]):
        if version in done:
            continue
        logger.info("迁移 %s：%s", version, description)
        fn(conn)
        conn.execute(
            text(
                f"INSERT INTO {META_TABLE} (version, description, applied_at) "
                "VALUES (:v, :d, :t)"
            ),
            {"v": version, "d": description, "t": datetime.now(timezone.utc)},
        )
        applied.append(version)
    return applied


def migration_plan() -> list[dict[str, Any]]:
    """供 /health 与自检脚本展示的迁移清单。"""
    return [
        {"version": v, "description": d, "applied": False} for v, d, _ in sorted(_MIGRATIONS)
    ]


# ================================================================== 迁移步骤


@migration("2026102701", "identity: users / devices / device_cursors 与多设备字段")
def _migrate_identity(conn: Connection) -> None:
    conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS users ("
            "id VARCHAR(64) PRIMARY KEY, "
            "display_name VARCHAR(64) NOT NULL DEFAULT 'Owner', "
            "created_at TIMESTAMP NOT NULL, "
            "updated_at TIMESTAMP NOT NULL)"
        )
    )
    conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS devices ("
            "id VARCHAR(64) PRIMARY KEY, "
            "user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
            "name VARCHAR(64) NOT NULL, "
            "platform VARCHAR(16) NOT NULL DEFAULT 'unknown', "
            "app_version VARCHAR(32) NOT NULL DEFAULT '0.0.0', "
            "token_hash VARCHAR(128) NOT NULL, "
            "token_hint VARCHAR(16) NOT NULL DEFAULT '', "
            "scopes VARCHAR(255) NOT NULL DEFAULT 'chat,sync', "
            "revoked INTEGER NOT NULL DEFAULT 0, "
            "last_seen_at TIMESTAMP, "
            "created_at TIMESTAMP NOT NULL)"
        )
    )
    conn.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_devices_token_hash ON devices (token_hash)"
        )
    )
    conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS device_cursors ("
            "device_id VARCHAR(64) NOT NULL REFERENCES devices(id) ON DELETE CASCADE, "
            "conversation_id VARCHAR(64) NOT NULL, "
            "last_seq INTEGER NOT NULL DEFAULT 0, "
            "updated_at TIMESTAMP NOT NULL, "
            "PRIMARY KEY (device_id, conversation_id))"
        )
    )

    # conversations / messages 可能来自 v0.1 老库，逐列补齐
    if _table_exists(conn, "conversations"):
        _add_column(conn, "conversations", "user_id", "VARCHAR(64)")
        _add_column(conn, "conversations", "character_id", "VARCHAR(64)")
        _add_column(conn, "conversations", "origin_device_id", "VARCHAR(64)")
        _create_index(
            conn,
            "ix_conversations_user_id",
            "CREATE INDEX IF NOT EXISTS ix_conversations_user_id ON conversations (user_id)",
        )

    if _table_exists(conn, "messages"):
        _add_column(conn, "messages", "request_id", "VARCHAR(64)")
        _add_column(conn, "messages", "conv_seq", "INTEGER")
        _add_column(conn, "messages", "client_ts", "TIMESTAMP")
        _add_column(conn, "messages", "media_id", "VARCHAR(64)")
        _add_column(conn, "messages", "tokens_prompt", "INTEGER")
        _add_column(conn, "messages", "tokens_completion", "INTEGER")
        _add_column(conn, "messages", "deleted_at", "TIMESTAMP")
        # 幂等去重：request_id 全局唯一（NULL 不参与唯一约束）
        _create_index(
            conn,
            "ux_messages_request_id",
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_messages_request_id "
            "ON messages (request_id) WHERE request_id IS NOT NULL",
        )
        _create_index(
            conn,
            "ix_messages_conv_seq",
            "CREATE INDEX IF NOT EXISTS ix_messages_conv_seq "
            "ON messages (conversation_id, conv_seq)",
        )
        # 回填同步游标：老数据按会话内时间顺序编号（幂等，已编号的行跳过）
        conn.execute(
            text(
                "UPDATE messages SET conv_seq = ("
                "  SELECT rn FROM ("
                "    SELECT id, ROW_NUMBER() OVER ("
                "      PARTITION BY conversation_id ORDER BY created_at, id) AS rn "
                "    FROM messages) ranked "
                "  WHERE ranked.id = messages.id) "
                "WHERE conv_seq IS NULL"
            )
        )


@migration("2026102702", "persona: characters / memory_records / world_events / media_assets")
def _migrate_persona(conn: Connection) -> None:
    conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS characters ("
            "id VARCHAR(64) PRIMARY KEY, "
            "\"key\" VARCHAR(64) NOT NULL UNIQUE, "
            "name VARCHAR(64) NOT NULL, "
            "tagline VARCHAR(255) NOT NULL DEFAULT '', "
            "avatar_key VARCHAR(64) NOT NULL DEFAULT 'default', "
            "system_prompt TEXT NOT NULL DEFAULT '', "
            "greeting TEXT NOT NULL DEFAULT '', "
            "summary TEXT NOT NULL DEFAULT '', "
            "traits_json TEXT NOT NULL DEFAULT '[]', "
            "interests_json TEXT NOT NULL DEFAULT '[]', "
            "background TEXT NOT NULL DEFAULT '', "
            "speaking_style TEXT NOT NULL DEFAULT '', "
            "source VARCHAR(64) NOT NULL DEFAULT 'builtin', "
            "is_default INTEGER NOT NULL DEFAULT 0, "
            "is_active INTEGER NOT NULL DEFAULT 1, "
            "created_at TIMESTAMP NOT NULL, "
            "updated_at TIMESTAMP NOT NULL)"
        )
    )
    conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS memory_records ("
            "id VARCHAR(64) PRIMARY KEY, "
            "user_id VARCHAR(64) REFERENCES users(id) ON DELETE CASCADE, "
            "character_id VARCHAR(64), "
            "scope VARCHAR(32) NOT NULL, "
            "subject VARCHAR(32) NOT NULL DEFAULT 'user', "
            "content TEXT NOT NULL, "
            "source_type VARCHAR(32) NOT NULL DEFAULT 'unknown', "
            "source_message_id VARCHAR(64), "
            "source_ref VARCHAR(255) NOT NULL DEFAULT '', "
            "confidence FLOAT NOT NULL DEFAULT 0.5, "
            "salience INTEGER NOT NULL DEFAULT 5, "
            "status VARCHAR(16) NOT NULL DEFAULT 'active', "
            "created_at TIMESTAMP NOT NULL, "
            "updated_at TIMESTAMP NOT NULL, "
            "archived_at TIMESTAMP)"
        )
    )
    _create_index(
        conn,
        "ix_memory_scope",
        "CREATE INDEX IF NOT EXISTS ix_memory_scope "
        "ON memory_records (scope, status, character_id)",
    )
    conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS world_events ("
            "id VARCHAR(64) PRIMARY KEY, "
            "character_id VARCHAR(64) NOT NULL, "
            "kind VARCHAR(32) NOT NULL DEFAULT 'diary', "
            "title VARCHAR(255) NOT NULL DEFAULT '', "
            "content TEXT NOT NULL DEFAULT '', "
            "simulated INTEGER NOT NULL DEFAULT 1, "
            "mood VARCHAR(32) NOT NULL DEFAULT '', "
            "meta_json TEXT NOT NULL DEFAULT '{}', "
            "occurred_at TIMESTAMP NOT NULL, "
            "created_at TIMESTAMP NOT NULL)"
        )
    )
    _create_index(
        conn,
        "ix_world_events_timeline",
        "CREATE INDEX IF NOT EXISTS ix_world_events_timeline "
        "ON world_events (character_id, occurred_at DESC)",
    )
    conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS media_assets ("
            "id VARCHAR(64) PRIMARY KEY, "
            "user_id VARCHAR(64), "
            "character_id VARCHAR(64), "
            "kind VARCHAR(32) NOT NULL DEFAULT 'image', "
            "mime VARCHAR(64) NOT NULL DEFAULT 'application/octet-stream', "
            "byte_size INTEGER NOT NULL DEFAULT 0, "
            "sha256 VARCHAR(64) NOT NULL DEFAULT '', "
            "storage_uri VARCHAR(512) NOT NULL DEFAULT '', "
            "width INTEGER NOT NULL DEFAULT 0, "
            "height INTEGER NOT NULL DEFAULT 0, "
            "duration_ms INTEGER NOT NULL DEFAULT 0, "
            "created_at TIMESTAMP NOT NULL)"
        )
    )
    conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS proactive_messages ("
            "id VARCHAR(64) PRIMARY KEY, "
            "user_id VARCHAR(64), "
            "character_id VARCHAR(64) NOT NULL, "
            "conversation_id VARCHAR(64), "
            "content TEXT NOT NULL, "
            "reason VARCHAR(64) NOT NULL DEFAULT 'checkin', "
            "status VARCHAR(16) NOT NULL DEFAULT 'pending', "
            "scheduled_at TIMESTAMP NOT NULL, "
            "sent_at TIMESTAMP, "
            "created_at TIMESTAMP NOT NULL)"
        )
    )
    _create_index(
        conn,
        "ix_proactive_pending",
        "CREATE INDEX IF NOT EXISTS ix_proactive_pending "
        "ON proactive_messages (status, scheduled_at)",
    )


@migration("2026102801", "消息类型（text/image/audio）+ 媒体库索引")
def _m2026102801(conn: Connection) -> None:
    """v0.3：区分文本 / 图片 / 语音消息，并为媒体去重建立索引。

    只做增量 ADD COLUMN，不动既有数据；旧消息全部落到默认值 'text'。
    """
    if "kind" not in _columns(conn, "messages"):
        conn.execute(
            text("ALTER TABLE messages ADD COLUMN kind VARCHAR(16) NOT NULL DEFAULT 'text'")
        )
    _create_index(
        conn,
        "ix_messages_kind",
        "CREATE INDEX IF NOT EXISTS ix_messages_kind ON messages (kind)",
    )
    _create_index(
        conn,
        "ix_media_sha",
        "CREATE INDEX IF NOT EXISTS ix_media_sha ON media_assets (sha256)",
    )
    _create_index(
        conn,
        "ix_media_created",
        "CREATE INDEX IF NOT EXISTS ix_media_created ON media_assets (created_at)",
    )


@migration("2026102901", "记忆复述权重：recall_count / last_recalled_at")
def _m2026102901(conn: Connection) -> None:
    """v2.0：记录每条记忆被回忆的次数与时间，用于检索加权。

    只加列，不改既有数据；老记忆默认 recall_count=0（从没被回忆过）。
    """
    cols = _columns(conn, "memory_records")
    if "recall_count" not in cols:
        conn.execute(
            text("ALTER TABLE memory_records ADD COLUMN recall_count INTEGER NOT NULL DEFAULT 0")
        )
    if "last_recalled_at" not in cols:
        conn.execute(text("ALTER TABLE memory_records ADD COLUMN last_recalled_at TIMESTAMP"))
    _create_index(
        conn,
        "ix_memory_recall",
        "CREATE INDEX IF NOT EXISTS ix_memory_recall ON memory_records (status, recall_count)",
    )


@migration("2026102902", "记忆固定：pinned 字段")
def _m2026102902(conn: Connection) -> None:
    """v2.x：用户可固定重要记忆，固定的记忆检索时权重更高、不受时间衰减。"""
    cols = _columns(conn, "memory_records")
    if "pinned" not in cols:
        conn.execute(
            text("ALTER TABLE memory_records ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")
        )
    _create_index(
        conn,
        "ix_memory_pinned",
        "CREATE INDEX IF NOT EXISTS ix_memory_pinned ON memory_records (status, pinned)",
    )
