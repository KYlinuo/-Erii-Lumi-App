"""阶段 D 验收：13 设定卡 / 14 演绎模式 / 15 便签 / 16 日程 / 17 熟悉度 /
18 表情词库 / 21 回忆时间线 / 22 长期话题档案。

关键断言对应原指令的硬约束：EPUB 未找到不编造出处、模式切换不删聊天且
虚构经历按模式隔离、未证实回忆不进时间线、长期话题只按相关性调取。
"""

from __future__ import annotations

from app import persona_card, personas, world


# ---------------------------------------------------------------- 13 设定卡


def test_persona_card_layers_and_missing_epub_is_honest(client, monkeypatch):
    monkeypatch.setattr(
        persona_card,
        "find_epub",
        lambda: {"found": False, "chapters": [], "note": "未找到本地 EPUB"},
    )
    card = client.get("/api/v1/persona-card").json()
    assert card["character"] == "绘梨衣"
    assert set(card["layers"]) == {"original", "deduction", "custom"}
    assert card["default_direction"] == "保留原著性格的平行日常"
    assert card["epub"]["found"] is False
    # 原著证据层必须标 missing，不能编造章节出处
    assert all(item["evidence"] in ("epub", "missing") for item in card["layers"]["original"])
    assert not card["epub"]["chapters"]
    assert card["boundaries"] and card["examples"]


# ---------------------------------------------------------------- 14 演绎模式


def test_persona_mode_default_switch_and_chat_preserved(client, stub, db_session):
    mode = client.get("/api/v1/persona-mode").json()
    assert mode["mode"] == "parallel"  # 默认平行日常

    chat = client.post("/api/v1/chat", json={"message": "你好", "request_id": "d-m1"})
    assert chat.status_code == 200
    cid = chat.json()["conversation_id"]

    switched = client.post(
        "/api/v1/persona-mode", json={"mode": "canon", "spoiler_scope": "known"}
    ).json()
    assert switched["mode"] == "canon"
    assert switched["version"] == mode["version"] + 1
    assert len(switched["history"]) >= 1

    # 切换模式不删除聊天
    history = client.get(f"/api/v1/conversations/{cid}/messages").json()
    assert len(history) >= 2
    # 模式约束确实进入系统提示词
    assert "演绎模式" in stub.calls[0][0].content


def test_world_events_are_isolated_by_mode(db_session):
    character = personas.resolve_character(db_session)
    world.record_event(
        db_session, character_id=character.id, kind="diary",
        content="原著模式专属经历", mode="canon",
    )
    world.record_event(
        db_session, character_id=character.id, kind="diary",
        content="平行日常专属经历", mode="parallel",
    )
    db_session.commit()
    parallel = world.recent_context(db_session, character.id, limit=10, mode="parallel")
    canon = world.recent_context(db_session, character.id, limit=10, mode="canon")
    assert "原著模式专属经历" not in parallel
    assert "平行日常专属经历" not in canon
    # 老数据（无 mode 标记）仍可见，升级不丢
    world.record_event(
        db_session, character_id=character.id, kind="diary", content="旧的无标记事件"
    )
    db_session.commit()
    assert "旧的无标记事件" in world.recent_context(db_session, character.id, limit=10, mode="pet")


# ---------------------------------------------------------------- 15 手写便签


def test_sticky_notes_crud_star_and_frequency(client):
    client.post("/api/v1/notes/settings", json={"frequency": "off"})
    settings = client.get("/api/v1/notes/settings").json()
    assert settings["enabled"] is False  # 可切回普通文字

    note = client.post(
        "/api/v1/notes",
        json={"content": "今天还不错的瞬间", "source_message_id": "m-src-1"},
    ).json()
    assert note["id"] and note["source_message_id"] == "m-src-1"

    starred = client.patch(f"/api/v1/notes/{note['id']}", json={"starred": True}).json()
    assert starred["starred"] is True
    assert any(n["id"] == note["id"] for n in client.get("/api/v1/notes?starred=true").json())

    assert client.delete(f"/api/v1/notes/{note['id']}").status_code == 204
    assert not client.get("/api/v1/notes").json()


# ---------------------------------------------------------------- 16 日程变更


def test_schedule_change_supersedes_same_day_without_conflict(client):
    first = client.post(
        "/api/v1/schedule", json={"day": "2026-11-01", "content": "去图书馆"}
    ).json()
    second = client.post(
        "/api/v1/schedule", json={"day": "2026-11-01", "content": "改去咖啡店"}
    ).json()
    assert second["supersedes"] == [first["id"]]

    state = client.get("/api/v1/schedule?day=2026-11-01").json()
    assert len(state["active"]) == 1
    assert state["active"][0]["content"] == "改去咖啡店"
    assert state["conflicts"] == {}, "同一天不能出现互相冲突的有效设定"
    # 旧记录保留（变更有记录），只是不再生效
    assert len(state["events"]) == 2


# ---------------------------------------------------------------- 17 熟悉程度


def test_intimacy_hidden_slow_pause_and_reset(client):
    initial = client.get("/api/v1/intimacy").json()
    assert initial["level"] is None and initial["hidden"] is True  # 数值可隐藏

    client.post("/api/v1/intimacy/experience", json={"reason": "一起看了雨"})
    assert client.get("/api/v1/intimacy?reveal=true").json()["level"] == 1
    assert client.get("/api/v1/intimacy").json()["stage"] == "初识"  # 变化缓慢

    client.post("/api/v1/intimacy/pause", json={"paused": True})
    client.post("/api/v1/intimacy/experience", json={})
    assert client.get("/api/v1/intimacy?reveal=true").json()["level"] == 1

    client.post("/api/v1/intimacy/pause", json={"paused": False})
    client.post("/api/v1/intimacy/reset")
    assert client.get("/api/v1/intimacy?reveal=true").json()["level"] == 0


# ---------------------------------------------------------------- 18 表情动作


def test_expression_pack_placeholder_and_user_import(client):
    pack = client.get("/api/v1/expressions").json()
    assert pack["placeholder_notice"]
    assert all(i["placeholder"] is True for i in pack["builtin"]["action"])
    assert pack["frequency"] == "medium"

    client.post("/api/v1/expressions/frequency", json={"frequency": "low"})
    imported = client.post(
        "/api/v1/expressions/import",
        json={"text": "（自定义贴纸）", "source": "我画的", "license": "CC0"},
    ).json()
    assert imported["imported"] is True
    after = client.get("/api/v1/expressions").json()
    assert after["frequency"] == "low"
    assert any(i["source"] == "我画的" for i in after["user_imported"])


# ---------------------------------------------------------------- 21 回忆时间线


def test_timeline_only_verified_and_sync_from_sources(client, stub):
    stub.reply = "嗯。"
    chat = client.post("/api/v1/chat", json={"message": "你好", "request_id": "d-t1"})
    cid = chat.json()["conversation_id"]
    amid = chat.json()["assistant_message_id"]
    client.post(f"/api/v1/conversations/{cid}/messages/{amid}/star")

    # 未证实候选不得进入默认时间线
    client.post("/api/v1/timeline", json={"title": "候选", "content": "可能是这样", "verified": False})
    default_view = client.get("/api/v1/timeline").json()
    assert all(e["verified"] is True for e in default_view)
    assert not any(e["title"] == "候选" for e in default_view)

    synced = client.post("/api/v1/timeline/sync").json()
    assert synced["created"]["first_chat"] >= 1
    kinds = {e["kind"] for e in client.get("/api/v1/timeline").json()}
    assert "first_chat" in kinds and "starred" in kinds

    # 未证实候选可由用户确认后进入
    candidates = client.get("/api/v1/timeline?include_unverified=true").json()
    candidate = next(e for e in candidates if not e["verified"])
    client.post(f"/api/v1/timeline/{candidate['id']}/verify")
    assert any(e["id"] == candidate["id"] for e in client.get("/api/v1/timeline").json())


# ---------------------------------------------------------------- 22 长期话题档案


def test_topic_archive_relevance_and_active_switch(client):
    topic = client.post(
        "/api/v1/topics",
        json={
            "title": "考研", "keywords": ["考研", "数学"], "goal": "上岸",
            "latest_progress": "高数一轮", "next_step": "线代",
        },
    ).json()
    client.post("/api/v1/topics", json={"title": "CDIO", "keywords": ["CDIO", "项目"]})

    relevant = client.get("/api/v1/topics/relevant?query=考研数学复习").json()
    assert relevant and relevant[0]["title"] == "考研"
    assert len(relevant) <= 2  # 不发送全部历史

    client.post("/api/v1/topics/active", json={"topic_id": topic["id"]})
    fallback = client.get("/api/v1/topics/relevant?query=完全无关的话题").json()
    assert fallback and fallback[0]["id"] == topic["id"]  # 手动切换优先

    client.patch(f"/api/v1/topics/{topic['id']}", json={"latest_progress": "高数二轮"})
    updated = client.get("/api/v1/topics").json()
    assert any(t["id"] == topic["id"] and t["latest_progress"] == "高数二轮" for t in updated)
