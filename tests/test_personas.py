"""人格系统：内置人格完整、不互相覆盖、绘梨衣设定不被改写、虚构人生隔离。"""

from __future__ import annotations

from app import personas
from app.models import Character

EXPECTED_KEYS = {"lumi", "linsui", "qilu", "shenzhou", "erii"}


def test_all_builtin_personas_exist(db_session):
    personas.seed_characters(db_session)
    db_session.commit()
    keys = {c.key for c in personas.list_characters(db_session)}
    assert EXPECTED_KEYS <= keys


def test_exactly_one_default_persona(db_session):
    defaults = [c for c in personas.list_characters(db_session) if c.is_default]
    assert len(defaults) == 1
    assert defaults[0].key == "lumi"


def test_seeding_does_not_overwrite_existing_settings(db_session):
    """既有设定（例如绘梨衣来自桌宠的描述）绝不能被内置模板覆盖。"""
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


def test_personas_are_not_merged(db_session):
    """三套人格 + 绘梨衣各自独立，不能出现合并后的统一人设。"""
    rows = {c.key: c for c in personas.list_characters(db_session)}
    names = {key: row.name for key, row in rows.items()}
    assert len(set(names.values())) == len(names), "人格名字不应重复/合并"

    styles = {key: row.speaking_style for key, row in rows.items()}
    assert len(set(styles.values())) == len(styles), "说话方式不应复用同一段"

    assert rows["linsui"].system_prompt != rows["qilu"].system_prompt
    assert "绘梨衣" in rows["erii"].name


def test_unknown_key_falls_back_to_default(db_session):
    character = personas.resolve_character(db_session, "does-not-exist")
    assert character.key == "lumi"


def test_system_prompt_contains_persona_and_guardrails(db_session):
    character = personas.resolve_character(db_session, "shenzhou")
    prompt = personas.compose_system_prompt(character)
    assert "沈昼" in prompt
    assert "虚构" in prompt  # 必须声明自己是虚构角色


def test_system_prompt_injects_memory_and_world_with_labels(db_session):
    character = personas.resolve_character(db_session, "lumi")
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


def test_fictional_life_is_isolated_per_persona(db_session):
    """不同人格的虚构人生互不相见。"""
    lumi = personas.get_character(db_session, key="lumi")
    erii = personas.get_character(db_session, key="erii")

    from app import world

    world.record_event(db_session, character_id=lumi.id, kind="diary", content="LUMI 的私事")
    world.record_event(db_session, character_id=erii.id, kind="diary", content="绘梨衣的私事")
    db_session.commit()

    lumi_events = {e.content for e in world.timeline(db_session, lumi.id, limit=50)}
    erii_events = {e.content for e in world.timeline(db_session, erii.id, limit=50)}
    assert "LUMI 的私事" in lumi_events
    assert "LUMI 的私事" not in erii_events
    assert "绘梨衣的私事" in erii_events


def test_idle_lines_for_erii_are_marked_fictional(db_session):
    lines = personas.idle_lines("erii")
    assert len(lines) >= 100, "绘梨衣的待机台词来自桌宠已有素材"
    assert lines[0]
    assert personas.idle_lines("lumi") == []


def test_character_to_dict_exposes_traits(db_session):
    data = personas.get_character(db_session, key="qilu").to_dict()
    assert data["name"] == "祁鹿"
    assert isinstance(data["traits"], list) and data["traits"]
    assert isinstance(data["interests"], list) and data["interests"]


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
