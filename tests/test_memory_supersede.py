"""事实变化纠正测试：同槽位的新事实归档旧事实，避免互相矛盾。"""

from __future__ import annotations

import pytest

from app import memory as memory_mod
from app.identity import get_or_create_user
from app.models import MemoryRecord
from sqlalchemy import select


def _user(db):
    return get_or_create_user(db, user_id="u-test-1")


def test_same_slot_new_value_supersedes(db_session):
    _user(db_session)
    memory_mod.record(
        db_session,
        scope="user_fact",
        content="用户的名字是 阿泽",
        subject="user",
        source_type="inferred",
        source_ref="message:m1 slot:name",
        slot="name",
    )
    memory_mod.record(
        db_session,
        scope="user_fact",
        content="用户的名字是 阿哲",
        subject="user",
        source_type="inferred",
        source_ref="message:m2 slot:name",
        slot="name",
    )
    db_session.commit()

    rows = db_session.execute(
        select(MemoryRecord).where(MemoryRecord.scope == "user_fact")
    ).scalars().all()
    active = [r for r in rows if r.status == "active"]
    archived = [r for r in rows if r.status == "archived"]
    assert len(active) == 1
    assert active[0].content == "用户的名字是 阿哲"
    assert len(archived) == 1
    assert archived[0].content == "用户的名字是 阿泽"


def test_preferences_coexist_no_supersede(db_session):
    _user(db_session)
    memory_mod.record(
        db_session,
        scope="user_preference",
        content="用户喜欢 猫",
        subject="user",
        source_type="inferred",
        source_ref="message:m1",
    )
    memory_mod.record(
        db_session,
        scope="user_preference",
        content="用户喜欢 狗",
        subject="user",
        source_type="inferred",
        source_ref="message:m2",
    )
    db_session.commit()
    rows = db_session.execute(
        select(MemoryRecord).where(MemoryRecord.scope == "user_preference")
    ).scalars().all()
    assert len([r for r in rows if r.status == "active"]) == 2


def test_ingest_residence_change_archives_old(db_session):
    """端到端：两条住址信息走 ingest，旧的被归档。"""
    user = _user(db_session)
    char_id = "seed-character"
    memory_mod.ingest_user_message(
        db_session, user_id=user.id, character_id=char_id,
        message_id="m1", user_text="我住在城西"
    )
    memory_mod.ingest_user_message(
        db_session, user_id=user.id, character_id=char_id,
        message_id="m2", user_text="我住在浦东"
    )
    db_session.commit()
    rows = db_session.execute(
        select(MemoryRecord).where(MemoryRecord.scope == "user_fact")
    ).scalars().all()
    active = [r for r in rows if r.status == "active" and "住" in r.content]
    archived = [r for r in rows if r.status == "archived" and "住" in r.content]
    # 新地址 active，旧地址归档
    assert any("浦东" in r.content for r in active)
    assert any("城西" in r.content for r in archived)


def test_list_memories_supports_query(client, db_session):
    _user(db_session)
    memory_mod.record(
        db_session, scope="user_fact", content="用户不吃香菜", subject="user",
        source_type="user_explicit", source_ref=""
    )
    memory_mod.record(
        db_session, scope="user_fact", content="用户住在城西", subject="user",
        source_type="user_explicit", source_ref=""
    )
    db_session.commit()

    r = client.get("/api/v1/memory?query=香菜")
    assert r.status_code == 200
    data = r.json()
    assert any("香菜" in m["content"] for m in data)
