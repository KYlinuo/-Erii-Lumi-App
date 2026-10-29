"""回复风格调节（需求 09）测试。"""

from __future__ import annotations

from app import style as style_mod


def test_default_profile_is_medium():
    p = style_mod.StyleProfile()
    p.validate()
    assert p.reply_length == "medium"
    assert p.action_description is True
    assert p.address == ""


def test_invalid_values_fall_back():
    p = style_mod.StyleProfile(reply_length="huge", question_frequency="always")
    p.validate()
    assert p.reply_length == "medium"
    assert p.question_frequency == "medium"


def test_prompt_reflects_settings():
    p = style_mod.StyleProfile(reply_length="short", emoji_frequency="low", action_description=False, address="阿泽")
    prompt = p.to_prompt()
    assert "短" in prompt
    assert "几乎不用表情" in prompt
    assert "少写动作" in prompt
    assert "阿泽" in prompt


def test_load_from_json_bad_data_falls_back():
    assert style_mod.load_from_json(None).reply_length == "medium"
    assert style_mod.load_from_json("not json").reply_length == "medium"
    assert style_mod.load_from_json("[1,2,3]").reply_length == "medium"


def test_load_from_json_roundtrip():
    p = style_mod.StyleProfile(reply_length="long", address="主人")
    raw = __import__("json").dumps(p.to_dict(), ensure_ascii=False)
    loaded = style_mod.load_from_json(raw)
    assert loaded.reply_length == "long"
    assert loaded.address == "主人"


def test_save_and_get_profile(db_session):
    p = style_mod.StyleProfile(reply_length="short", address="你")
    style_mod.save_profile(db_session, p)
    db_session.commit()

    got = style_mod.get_profile(db_session)
    assert got.reply_length == "short"
    assert got.address == "你"


def test_style_endpoint(client):
    # 默认
    r = client.get("/api/v1/style")
    assert r.status_code == 200
    assert r.json()["reply_length"] == "medium"

    # 保存
    r2 = client.post("/api/v1/style", json={"reply_length": "long", "address": "主人"})
    assert r2.status_code == 200
    assert r2.json()["reply_length"] == "long"
    assert r2.json()["address"] == "主人"

    # 读回
    r3 = client.get("/api/v1/style")
    assert r3.json()["reply_length"] == "long"
    assert r3.json()["address"] == "主人"
