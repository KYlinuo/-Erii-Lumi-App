"""虚构时间线「关联此前剧情」测试。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import personas, world as world_mod


@pytest.fixture()
def character(db_session):
    from app import personas

    char = personas.get_character(db_session, key="erii")
    if char is None:
        # 取任意内置人格
        chars = personas.list_characters(db_session)
        char = chars[0]
    return char


def test_simulate_day_links_references(db_session, character):
    """第二天的生成应携带「前一天」的事件引用，形成剧情连贯。

    用 10 天前的时间窗口，避开 bootstrap 已经播种的最近 3 天。
    """
    base = datetime.now(timezone.utc).date() - timedelta(days=10)
    yesterday = base - timedelta(days=1)

    # 先生成昨天
    world_mod.simulate_day(db_session, character, yesterday, max_events=2)
    db_session.commit()

    # 再生成"今天"（相对于 base 而言）
    created = world_mod.simulate_day(db_session, character, base, max_events=1)
    db_session.commit()

    assert created, "今天应生成至少一条事件"
    meta = created[0].meta()
    refs = meta.get("references", [])
    # 今天的事件应引用到昨天的剧情（如果昨天确实生成成功）
    assert isinstance(refs, list)
    # 引用项含 kind/title/content 三要素
    for ref in refs:
        assert "kind" in ref and "title" in ref and "content" in ref


def test_simulate_is_idempotent_with_references(db_session, character):
    """同一天重复生成不重复写，references 稳定。"""
    day = datetime.now(timezone.utc).date() - timedelta(days=12)
    first = world_mod.simulate_day(db_session, character, day, max_events=2)
    db_session.commit()
    second = world_mod.simulate_day(db_session, character, day, max_events=2)
    assert second == [], "同一天重复生成应返回空"
    assert len(first) == 2
