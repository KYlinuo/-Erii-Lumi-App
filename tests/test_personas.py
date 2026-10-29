"""人格系统：只保留绘梨衣，设定不被覆盖，虚构人生正确标注。"""

from __future__ import annotations

from app import personas
from app.models import Character

EXPECTED_KEYS = {"erii"}


def test_only_erii_persona_exists(db_session):
    personas.seed_characters(db_session)
    db_session.commit()
    keys = {c.key for c in personas.list_characters(db_session)}
    assert keys == EXPECTED_KEYS


def test_exactly_one_default_persona(db_session):
    defaults = [c for c in personas.list_characters(db_session) if c.is_default]
    assert len(defaults) == 1
    assert defaults[0].key == "erii"


def test_seeding_does_not_overwrite_existing_settings(db_session):
    """绘梨衣既有设定（来自桌宠素材）绝不能被内置模板覆盖。"""
    erii = personas.get_character(db_session, key="erii")
    erii.background = "【用户自定义】保留原始设定"
    erii.system_prompt = "【用户自定义】保留原始提示词"
    db_session.commit()

    personas.seed_characters(db_session)
    db_session.commit()

    reloaded = personas.get_character(db_session, key="erii")
    assert reloaded.background == "【用户自定义】保留原始设定"
    assert reloaded.system_prompt == "【用户自定义】保留原始提示词"


def test_seeding_is_idempotent(db_session):
    personas.seed_characters(db_session)
    db_session.commit()
    before = personas.list_characters(db_session)
    n_before = len(before)

    created = personas.seed_characters(db_session)
    db_session.commit()
    assert created == 0
    assert len(personas.list_characters(db_session)) == n_before


def test_unknown_key_falls_back_to_default(db_session):
    from app.config import get_settings

    character = personas.resolve_character(db_session, "does-not-exist")
    assert character.key == get_settings().default_character_key


def test_system_prompt_contains_persona_and_guardrails(db_session):
    character = personas.resolve_character(db_session, "erii")
    prompt = personas.compose_system_prompt(character)
    assert "绘梨衣" in prompt
    assert "虚构" in prompt  # 必须声明自己是虚构角色


def test_system_prompt_injects_memory_and_world_with_labels(db_session):
    character = personas.resolve_character(db_session, "erii")
    prompt = personas.compose_system_prompt(
        character,
        memory_block="- [事实] 用户叫小明 （推测，不确定）",
        world_block="- 今天读了点书",
        current_time="2026-10-28 09:00（星期二）",
    )
    assert "用户叫小明" in prompt
    assert "不是用户的真实经历" in prompt  # 虚构世界声明
    assert "不要当成事实陈述" in prompt  # 推测声明
    assert "2026-10-28" in prompt


def test_idle_lines_for_erii_are_marked_fictional(db_session):
    lines = personas.idle_lines("erii")
    assert len(lines) >= 100, "绘梨衣的待机台词来自桌宠已有素材"
    assert lines[0]


def test_character_to_dict_exposes_traits(db_session):
    data = personas.get_character(db_session, key="erii").to_dict()
    assert data["name"] == "绘梨衣"
    assert isinstance(data["traits"], list) and data["traits"]
    assert isinstance(data["interests"], list) and data["interests"]


def test_erii_has_edges_not_customer_service(db_session):
    """绘梨衣要有棱角：明确写出边界，避免变成千人一面的客服。"""
    row = personas.get_character(db_session, key="erii")
    prompt = row.system_prompt
    assert "【你的棱角】" in prompt or "【边界】" in prompt
    assert len(prompt) > 120


def test_character_model_roundtrip(db_session):
    row = Character(
        key="custom", name="自定义角色", tagline="t", system_prompt="p",
        traits_json='["A"]', interests_json='["B"]',
    )
    db_session.add(row)
    db_session.commit()
    reloaded = personas.get_character(db_session, key="custom")
    assert reloaded.traits() == ["A"]
    assert reloaded.interests() == ["B"]
