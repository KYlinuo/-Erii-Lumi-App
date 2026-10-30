"""旧库升级：角色归档迁移测试。

验证 v2.x 收敛为「仅绘梨衣」时，旧库中残留的多人格被正确归档
（不删除数据），且绘梨衣成为唯一默认。

conftest 的 bootstrap 已播种 erii，这里只模拟「旧库额外残留 4 个旧角色 +
lumi 仍是默认」的不一致状态。
"""

from __future__ import annotations

import json

from app import personas
from app.models import Character
from sqlalchemy import select


def _legacy_seed(db):
    """模拟 v0.x 旧库残留：额外 4 套旧人格，lumi 是默认，erii 非默认。"""
    legacy = [("lumi", "LUMI"), ("linsui", "林穗"), ("qilu", "祁鹿"), ("shenzhou", "沈昼")]
    for key, name in legacy:
        db.add(Character(
            key=key, name=name, is_default=(1 if key == "lumi" else 0), is_active=1,
            system_prompt="", greeting="", summary="", background="",
            speaking_style="", source="legacy",
            traits_json=json.dumps([]), interests_json=json.dumps([]),
        ))
    # 模拟旧库：erii 非默认
    erii = db.execute(select(Character).where(Character.key == "erii")).scalar_one()
    erii.is_default = 0
    db.commit()


def test_legacy_characters_archived_and_erii_default(db_session):
    _legacy_seed(db_session)
    personas.seed_characters(db_session)
    db_session.commit()

    by_key = {r.key: r for r in db_session.execute(select(Character)).scalars()}

    # 旧角色归档但不删除
    for key in ("lumi", "linsui", "qilu", "shenzhou"):
        assert by_key[key].is_active == 0, f"{key} 应归档"
        assert by_key[key].is_default == 0

    # 绘梨衣是唯一默认 + 活跃
    assert by_key["erii"].is_default == 1
    assert by_key["erii"].is_active == 1

    # 前台只返回绘梨衣
    assert [c.key for c in personas.list_characters(db_session)] == ["erii"]


def test_archive_is_idempotent(db_session):
    _legacy_seed(db_session)
    personas.seed_characters(db_session)
    db_session.commit()
    personas.seed_characters(db_session)
    db_session.commit()
    assert [c.key for c in personas.list_characters(db_session)] == ["erii"]


def test_legacy_conversation_data_untouched(db_session):
    """归档不删除角色，历史会话的 character_id 引用仍然有效。"""
    _legacy_seed(db_session)
    from app.models import Conversation, Message
    lumi = db_session.execute(select(Character).where(Character.key == "lumi")).scalar_one()
    conv = Conversation(title="老会话", character_id=lumi.id)
    db_session.add(conv)
    db_session.flush()
    db_session.add(Message(conversation_id=conv.id, role="user", content="老消息", kind="text"))
    db_session.commit()

    personas.seed_characters(db_session)
    db_session.commit()

    msg = db_session.execute(select(Message)).scalar_one()
    assert msg.content == "老消息"
    lumi_after = db_session.get(Character, lumi.id)
    assert lumi_after is not None and lumi_after.is_active == 0
