"""长期记忆：抽取、来源、可信度、真实用户事实与角色虚构人生的严格隔离。"""

from __future__ import annotations

from app import memory as mem


def test_extracts_user_name_and_preference():
    candidates = mem.extract_candidates("我叫小明，我很喜欢爬山")
    contents = [c.content for c in candidates]
    assert any("小明" in c for c in contents)
    assert any("爬山" in c for c in contents)
    assert all(c.source_type == mem.SOURCE_INFERRED for c in candidates)
    assert all(c.confidence < 0.9 for c in candidates)  # 推断 ≠ 确定事实


def test_extraction_is_deterministic():
    a = [c.content for c in mem.extract_candidates("我叫小明，我很喜欢爬山")]
    b = [c.content for c in mem.extract_candidates("我叫小明，我很喜欢爬山")]
    assert a == b


def test_extraction_can_be_disabled(monkeypatch):
    monkeypatch.setenv("LUMI_MEMORY_AUTO_EXTRACT", "0")
    from app.config import reload_settings

    reload_settings()
    assert mem.extract_candidates("我叫小明") == []


def test_ingest_stores_user_facts_as_shared(db_session):
    """用户真实信息抽成用户层记忆（character_id=None），不绑定角色。"""
    from app import personas

    erii = personas.get_character(db_session, key="erii")
    saved = mem.ingest_user_message(
        db_session, user_id=None, character_id=erii.id,
        message_id="m1", user_text="我叫小明",
    )
    db_session.commit()
    assert saved, "应至少抽出一条记忆"

    visible = {m.content for m in mem.query_memories(db_session, character_id=erii.id)}
    assert any("小明" in c for c in visible)
    assert all(m.character_id is None for m in saved), "用户层记忆不绑定人格"


def test_fictional_life_never_leaks_into_user_facts(db_session):
    """角色的虚构人生（subject=character）不能出现在用户事实检索里。"""
    from app import personas

    erii = personas.get_character(db_session, key="erii")
    mem.record(
        db_session, scope="fictional_life", content="她随身带着小本子",
        character_id=erii.id, subject=mem.SUBJECT_CHARACTER,
        source_type=mem.SOURCE_WORLD,
    )
    db_session.commit()

    row = next(m for m in mem.query_memories(db_session, character_id=erii.id)
               if m.content == "她随身带着小本子")
    assert row.subject == mem.SUBJECT_CHARACTER
    assert row.source_type == mem.SOURCE_WORLD

    user_facts = mem.query_memories(db_session, character_id=erii.id, scopes=["user_fact"])
    assert all("她随身带着小本子" != m.content for m in user_facts)


def test_memory_is_idempotent_not_duplicated(db_session):
    first = mem.record(db_session, scope="user_fact", content="用户住在杭州")
    db_session.commit()
    second = mem.record(db_session, scope="user_fact", content="用户住在杭州")
    db_session.commit()
    assert first.id == second.id
    assert mem.count_by_scope(db_session).get("user_fact", 0) == 1


def test_explicit_memory_has_high_confidence(db_session):
    row = mem.record(db_session, scope="user_fact", content="用户是老师",
                     source_type=mem.SOURCE_USER_EXPLICIT)
    db_session.commit()
    assert row.confidence >= 0.9
    assert row.source_type == mem.SOURCE_USER_EXPLICIT


def test_prompt_block_marks_inferred_items(db_session):
    row = mem.record(db_session, scope="user_fact", content="用户叫小明",
                     source_type=mem.SOURCE_INFERRED)
    block = mem.prompt_block([row])
    assert "推测" in block
    assert "小明" in block


def test_prompt_block_marks_explicit_items(db_session):
    row = mem.record(db_session, scope="user_preference", content="用户不喜欢香菜",
                     source_type=mem.SOURCE_USER_EXPLICIT, confidence=0.95)
    block = mem.prompt_block([row])
    assert "用户说过" in block


def test_archive_and_delete(db_session):
    row = mem.record(db_session, scope="user_fact", content="临时记忆")
    db_session.commit()
    assert mem.archive_memory(db_session, row.id)
    db_session.commit()
    assert db_session.get(mem.MemoryRecord, row.id).status == mem.STATUS_ARCHIVED

    assert mem.delete_memory(db_session, row.id)
    db_session.commit()
    assert db_session.get(mem.MemoryRecord, row.id) is None


def test_export_includes_source_and_confidence(db_session):
    mem.record(db_session, scope="user_fact", content="用户叫小明")
    db_session.commit()
    rows = mem.export_memories(db_session)
    assert rows
    assert "confidence" in rows[0] and "source_type" in rows[0]


def test_invalid_scope_rejected(db_session):
    import pytest

    with pytest.raises(ValueError):
        mem.record(db_session, scope="not_a_scope", content="x")


def test_memory_api_roundtrip(client):
    r = client.post("/api/v1/memory", json={"scope": "user_fact", "content": "用户养了一只猫"})
    assert r.status_code == 201
    memory_id = r.json()["id"]
    assert r.json()["confidence"] >= 0.9

    listed = client.get("/api/v1/memory").json()
    assert any(m["id"] == memory_id for m in listed)

    assert client.patch(f"/api/v1/memory/{memory_id}", json={"content": "用户养了两只猫"}).json()["content"] == "用户养了两只猫"
    assert client.delete(f"/api/v1/memory/{memory_id}").status_code == 204
    assert client.get(f"/api/v1/memory/{memory_id}", ).status_code == 405  # 未定义 GET，确认已删除的另有路径


def test_memory_api_rejects_bad_scope(client):
    assert client.post("/api/v1/memory", json={"scope": "nope", "content": "x"}).status_code == 422


def test_memory_summary_and_export_endpoint(client):
    client.post("/api/v1/memory", json={"scope": "user_preference", "content": "用户喜欢深夜聊天"})
    summary = client.get("/api/v1/memory/summary").json()
    assert summary["by_scope"].get("user_preference", 0) >= 1

    exported = client.get("/api/v1/memory/export").json()
    assert any("深夜聊天" in r["content"] for r in exported["records"])
