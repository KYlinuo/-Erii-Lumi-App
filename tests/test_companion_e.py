"""阶段 E 验收：23 临时聊天 / 24 备份恢复（验收场景 7）/ 25 主动联系 /
26 学习计时 / 27 一起读书 / 28 共同小活动 / 29 日记留言 / 30 小组件 /
35 桌宠协议契约（验收场景 8）。

关键断言：临时会话不进多端同步、重复恢复不产生重复记录、完整性校验能
发现篡改、APNs 状态如实标 blocked、小活动不改变普通聊天模式。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import personas, proactive
from app.models import (
    ActivitySession,
    AppSetting,
    Conversation,
    DiaryNote,
    MemoryRecord,
    Message,
    ProactiveMessage,
    Promise,
    ReadingProgress,
    StickyNote,
    StudySession,
    TimelineEvent,
    TopicArchive,
    WorldEvent,
)


def _wipe_backup_tables(db_session):
    """模拟恢复到临时目录的空库：只清「备份覆盖的数据表」，保留设备/人格。"""
    for model in (
        Message, MemoryRecord, WorldEvent, ProactiveMessage, Promise,
        TimelineEvent, TopicArchive, StickyNote, ActivitySession, StudySession,
        ReadingProgress, DiaryNote, AppSetting, Conversation,
    ):
        db_session.query(model).delete()
    db_session.commit()


# ---------------------------------------------------------------- 23 临时聊天


def test_ephemeral_excluded_from_sync_and_exit_policy(client, stub, db_session):
    stub.reply = "好。"
    temp = client.post(
        "/api/v1/chat", json={"message": "临时的话", "request_id": "e-e1", "ephemeral": True}
    ).json()
    cid = temp["conversation_id"]
    assert any(c["id"] == cid for c in client.get("/api/v1/ephemeral").json())

    # 单会话与全量同步都不含临时会话（不是只隐藏界面）
    assert client.get(f"/api/v1/sync/conversation/{cid}").json() == []
    everything = client.post("/api/v1/sync", json={"since": {}}).json()
    assert all(c["conversation_id"] != cid for c in everything["conversations"])

    # 退出策略默认 delete：真正删除，不只是隐藏
    result = client.post("/api/v1/ephemeral/exit").json()
    assert result["deleted"] >= 1
    assert db_session.get(Conversation, cid) is None


# ---------------------------------------------------------------- 24 备份恢复


def test_backup_export_preview_apply_is_deduped(client, stub, db_session):
    """验收场景 7：导出—恢复演练，重复恢复不产生重复记录。"""
    stub.reply = "嗯。"
    client.post("/api/v1/chat", json={"message": "我叫小明", "request_id": "e-b1"})
    client.post("/api/v1/notes", json={"content": "便签A"})
    client.post("/api/v1/topics", json={"title": "考研", "keywords": ["考研"]})

    backup = client.get("/api/v1/backup/export").json()
    assert backup["version"] == 2
    assert backup["checksum"]
    assert backup["encrypted"] is False  # 无密钥时如实标明文
    assert len(backup["data"]["conversations"]) >= 1
    assert len(backup["data"]["sticky_notes"]) >= 1
    assert backup["encryption"]["offered"] is True

    _wipe_backup_tables(db_session)
    assert db_session.query(Conversation).count() == 0

    preview = client.post("/api/v1/backup/preview", json={"backup": backup}).json()
    assert preview["valid"] is True and preview["checksum_ok"] is True
    assert preview["tables"]["conversations"]["new"] >= 1

    first = client.post("/api/v1/backup/apply", json={"backup": backup, "strategy": "skip"}).json()
    second = client.post("/api/v1/backup/apply", json={"backup": backup, "strategy": "skip"}).json()
    assert first["tables"]["conversations"]["created"] >= 1
    assert second["tables"]["conversations"]["created"] == 0
    assert second["tables"]["conversations"]["skipped"] >= 1
    # 记录数与备份一致（没有重复）
    assert db_session.query(Conversation).count() == len(backup["data"]["conversations"])
    assert db_session.query(StickyNote).count() == len(backup["data"]["sticky_notes"])


def test_backup_detects_tampering(client, stub):
    stub.reply = "嗯。"
    client.post("/api/v1/chat", json={"message": "你好", "request_id": "e-b2"})
    backup = client.get("/api/v1/backup/export").json()
    backup["data"]["conversations"][0]["title"] = "被篡改的标题"
    preview = client.post("/api/v1/backup/preview", json={"backup": backup}).json()
    assert preview["valid"] is False
    assert "完整性" in preview["error"]


def test_backup_encryption_state_is_honest(client):
    backup = client.get("/api/v1/backup/export").json()
    method = backup["encryption"]["method"]
    assert method in ("fernet-sha256", "unavailable")
    if method == "unavailable":
        assert backup["encrypted"] is False
        assert "未安装" in backup["encryption"]["note"]


# ---------------------------------------------------------------- 25 主动联系


def test_proactive_settings_and_capability_status(client):
    current = client.get("/api/v1/proactive/settings").json()
    assert "daily_cap" in current and "windows" in current
    updated = client.post(
        "/api/v1/proactive/settings",
        json={"daily_cap": 5, "paused": True, "enabled": False},
    ).json()
    assert updated["daily_cap"] == 5 and updated["paused"] is True
    assert updated["source"] == "app_settings"

    capability = client.get("/api/v1/proactive/capability").json()
    assert capability["server_queue"]["status"] == "implemented"
    assert capability["app_pull"]["status"] == "implemented"
    assert capability["apns"]["status"] == "blocked"
    assert capability["local_notification"]["status"] == "not_implemented"


def test_proactive_expire_and_dedup(client, db_session):
    stale = ProactiveMessage(
        character_id="x", content="过期关心", status="pending",
        scheduled_at=datetime.now(timezone.utc) - timedelta(hours=48),
    )
    db_session.add(stale)
    db_session.commit()
    assert client.post("/api/v1/proactive/expire?hours=24").json()["expired"] >= 1

    character = personas.resolve_character(db_session)
    first = proactive.enqueue(db_session, character=character, user_id=None, content="同一句", reason="checkin")
    second = proactive.enqueue(db_session, character=character, user_id=None, content="同一句", reason="checkin")
    assert first.id == second.id, "同内容 pending 不重复入队"


# ---------------------------------------------------------------- 26 学习陪伴


def test_study_timer_restart_recovery_and_end(client, db_session):
    session = client.post("/api/v1/study/start", json={"subject": "高数"}).json()
    sid = session["id"]
    # 模拟进程重启：started_at 是持久化的，重启后仍按它算已用时长
    row = db_session.get(StudySession, sid)
    row.started_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db_session.commit()
    view = client.get(f"/api/v1/study/{sid}").json()
    assert view["elapsed_ms"] >= 9 * 60 * 1000
    assert view["resumable"] is True

    client.post(f"/api/v1/study/{sid}/pause")
    client.post(f"/api/v1/study/{sid}/resume")
    ended = client.post(f"/api/v1/study/{sid}/end", json={"note": "看了两节"}).json()
    assert ended["status"] == "done" and ended["note"] == "看了两节"
    assert ended["resumable"] is False


# ---------------------------------------------------------------- 27 一起读书


def test_reading_progress_injects_spoiler_guard(client, stub):
    client.post(
        "/api/v1/reading",
        json={"book": "龙族", "chapter": "第三章", "progress": "30%", "spoiler_limit": "第三章"},
    )
    stub.reply = "嗯。"
    client.post("/api/v1/chat", json={"message": "后来怎么样了", "request_id": "e-r1"})
    system = stub.calls[0][0].content
    assert "剧透控制" in system and "第三章" in system


# ---------------------------------------------------------------- 28 共同小活动


def test_activity_scoped_prompt_and_finish(client, stub):
    session = client.post("/api/v1/activities/start", json={"kind": "guess_word"}).json()
    sid = session["id"]
    step = client.post(f"/api/v1/activities/{sid}/step", json={"answer": "云"}).json()
    assert step["state"]["hints_shown"] == 1

    stub.reply = "嗯。"
    client.post("/api/v1/chat", json={"message": "继续", "request_id": "e-a1"})
    assert "正在进行的共同小活动" in stub.calls[0][0].content

    client.post(f"/api/v1/activities/{sid}/finish", json={"status": "done"})
    stub.calls.clear()
    client.post("/api/v1/chat", json={"message": "普通聊天", "request_id": "e-a2"})
    assert "正在进行的共同小活动" not in stub.calls[0][0].content, "活动不得长期改变普通聊天"


# ---------------------------------------------------------------- 29 日记与留言


def test_diary_day_separates_simulated_user_and_notes(client, stub):
    stub.reply = "嗯。"
    today = datetime.now(timezone.utc).date().isoformat()
    client.post("/api/v1/chat", json={"message": "今天下雨", "request_id": "e-d1"})
    note = client.post(
        "/api/v1/diary-notes", json={"day": today, "content": "我的留言"}
    ).json()

    day = client.get(f"/api/v1/diary/day?day={today}").json()
    assert day["user_notes"] and day["user_messages"]
    assert day["notice"]  # 分别管理声明
    assert "simulated_events" in day

    regen = client.post("/api/v1/diary/regenerate", json={"day": today}).json()
    assert regen["regenerated"] >= 1

    client.delete(f"/api/v1/diary-notes/{note['id']}")
    assert not client.get(f"/api/v1/diary-notes?day={today}").json()


# ---------------------------------------------------------------- 30 小组件


def test_widget_privacy_and_capability_blocked(client):
    public = client.get("/api/v1/widget/summary").json()
    assert public["capability"]["extension_signing"] == "blocked"
    assert public["capability"]["shared_container"] == "blocked"
    private = client.get("/api/v1/widget/summary?privacy=true").json()
    assert private["privacy"] is True
    assert "notes" not in private and "counts" in private


# ---------------------------------------------------------------- 35 桌宠契约（验收场景 8）


def test_bridge_contract_and_cross_device_idempotency(client, stub):
    contract = client.get("/api/v1/bridge/contract").json()
    assert "request_id#reply" in contract["idempotency"]["reply"]
    assert contract["desktop_status"]  # 桌宠端待完成如实标注

    stub.reply = "同一句"
    payload = {"message": "两端同时在线", "request_id": "e-bridge-1"}
    first = client.post("/api/v1/chat", json=payload)
    cid = first.json()["conversation_id"]
    second = client.post("/api/v1/chat", json={**payload, "conversation_id": cid})
    assert second.json()["assistant_message_id"] == first.json()["assistant_message_id"]
    assert len(stub.calls) == 1, "两端同一 request_id 只产生一条回复"
