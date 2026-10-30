"""记忆强度打分测试。

目标是「像人一样有轻重地回忆」：时间衰减只是其中一项，
重要性与相关性可以压过时间，被反复回忆的记忆会变强。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import memory as memory_mod
from app.models import MemoryRecord


def _record(**kwargs) -> MemoryRecord:
    base = dict(
        id=kwargs.pop("id", "m1"),
        scope=kwargs.pop("scope", "user_fact"),
        subject=kwargs.pop("subject", "user"),
        content=kwargs.pop("content", "用户叫阿泽"),
        source_type=kwargs.pop("source_type", "user_explicit"),
        confidence=kwargs.pop("confidence", 0.95),
        salience=kwargs.pop("salience", 6),
        status="active",
        created_at=kwargs.pop("created_at", datetime.now(timezone.utc)),
        updated_at=kwargs.pop("updated_at", datetime.now(timezone.utc)),
    )
    rec = MemoryRecord(**base)
    rec.recall_count = kwargs.pop("recall_count", 0)
    rec.last_recalled_at = kwargs.pop("last_recalled_at", None)
    return rec


def test_recency_decays_score():
    now = datetime.now(timezone.utc)
    fresh = _record(id="new", created_at=now, updated_at=now)
    old = _record(id="old", created_at=now - timedelta(days=120), updated_at=now - timedelta(days=120))
    assert memory_mod.score_memory(fresh, "", now) > memory_mod.score_memory(old, "", now)


def test_salience_can_outweigh_time():
    now = datetime.now(timezone.utc)
    old_important = _record(
        id="old-important",
        salience=10,
        confidence=1.0,
        created_at=now - timedelta(days=200),
        updated_at=now - timedelta(days=200),
    )
    new_trivial = _record(id="new-trivial", salience=1, confidence=0.4, created_at=now, updated_at=now)
    assert memory_mod.score_memory(old_important, "", now) > memory_mod.score_memory(new_trivial, "", now)


def test_relevance_boosts_score():
    now = datetime.now(timezone.utc)
    related = _record(id="rel", content="用户不吃香菜")
    unrelated = _record(id="unrel", content="用户住在城西")
    assert memory_mod.score_memory(related, "香菜", now) > memory_mod.score_memory(unrelated, "香菜", now)


def test_recall_count_boosts_score():
    now = datetime.now(timezone.utc)
    rehearsed = _record(id="r", recall_count=5)
    naive = _record(id="n", recall_count=0)
    assert memory_mod.score_memory(rehearsed, "", now) > memory_mod.score_memory(naive, "", now)


def test_rank_memories_orders_by_score():
    now = datetime.now(timezone.utc)
    items = [
        _record(id="a", content="用户喜欢爬山", salience=5),
        _record(id="b", content="用户不吃香菜", salience=9),
    ]
    ranked = memory_mod.rank_memories(items, "香菜", now)
    assert ranked[0].id == "b"


def test_touch_recall_updates_counter(db_session):
    rec = _record(id="touch-1")
    db_session.add(rec)
    db_session.flush()
    memory_mod.touch_recall(db_session, [rec])
    assert rec.recall_count == 1
    assert rec.last_recalled_at is not None
    memory_mod.touch_recall(db_session, [rec])
    assert rec.recall_count == 2
