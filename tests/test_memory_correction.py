"""记忆纠错（需求 19）：记错了 / 已经变化 / 仅本次有效。"""

from __future__ import annotations

from app import memory as mem
from app.identity import get_or_create_user
from sqlalchemy import select
from app.models import MemoryRecord


def _seed(db):
    get_or_create_user(db, user_id="u-corr")
    return mem.record(
        db, scope="user_fact", content="用户住在城西",
        subject="user", source_type="inferred", source_ref="message:m1",
    )


def test_correct_wrong_archives(db_session):
    row = _seed(db_session)
    db_session.commit()

    corrected = mem.correct_memory(db_session, row.id, "wrong", note="记错了")
    db_session.commit()

    assert corrected.status == "archived"
    assert "corrected:wrong" in corrected.source_ref


def test_correct_changed_supersedes(db_session):
    row = _seed(db_session)
    db_session.commit()

    corrected = mem.correct_memory(db_session, row.id, "changed", note="搬去浦东了")
    db_session.commit()

    assert corrected.status == "superseded"
    assert "corrected:changed" in corrected.source_ref


def test_correct_ephemeral_excluded_from_retrieval(db_session):
    row = _seed(db_session)
    db_session.commit()

    mem.correct_memory(db_session, row.id, "ephemeral")
    db_session.commit()

    # ephemeral 不进入 active 检索
    active = mem.query_memories(db_session, character_id=None, limit=100)
    assert all(m.id != row.id for m in active)


def test_correct_unpins(db_session):
    row = _seed(db_session)
    mem.set_pinned(db_session, row.id, True)
    db_session.commit()

    corrected = mem.correct_memory(db_session, row.id, "wrong")
    db_session.commit()

    assert corrected.pinned == 0, "被纠正后不再固定"


def test_correct_invalid_type_raises(db_session):
    row = _seed(db_session)
    db_session.commit()
    import pytest
    with pytest.raises(ValueError):
        mem.correct_memory(db_session, row.id, "bogus")


def test_correct_endpoint(client, db_session):
    row = _seed(db_session)
    db_session.commit()
    mem_id = row.id

    r = client.post(f"/api/v1/memory/{mem_id}/correct", json={"correction": "changed", "note": "变了"})
    assert r.status_code == 200
    assert r.json()["status"] == "superseded"
