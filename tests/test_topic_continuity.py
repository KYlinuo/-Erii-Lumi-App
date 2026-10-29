"""话题接续（需求 10）：未完成话题注入 system 提示。"""

from __future__ import annotations

from app import personas


def test_compose_injects_topic_block():
    from app.models import Character

    char = Character(key="erii", name="绘梨衣", system_prompt="你是绘梨衣")
    prompt = personas.compose_system_prompt(
        char,
        topic_block="【你们还没聊完的话题】\n- 下次聊考研\n",
    )
    assert "还没聊完的话题" in prompt
    assert "考研" in prompt


def test_compose_without_topic_block_ok():
    from app.models import Character

    char = Character(key="erii", name="绘梨衣", system_prompt="你是绘梨衣")
    prompt = personas.compose_system_prompt(char)
    assert "你是绘梨衣" in prompt
    assert "还没聊完的话题" not in prompt
