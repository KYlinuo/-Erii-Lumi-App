"""主动联系：时段、配额、免打扰、即时关闭、离线排队。

诚实边界：这里测的是「服务端排队 + 客户端拉取」，
**不是** APNs 远程推送（免费自签条件下不声称支持）。
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from app import personas, proactive


def test_disabled_by_default(db_session, monkeypatch):
    allowed, why = proactive.allowed_now()
    assert allowed is False
    assert why == "proactive_disabled"


def test_quiet_hours_block_sending(monkeypatch):
    monkeypatch.setenv("LUMI_PROACTIVE_ENABLED", "1")
    from app.config import reload_settings

    reload_settings()
    night = datetime(2026, 10, 28, 1, 0)  # 凌晨一点
    allowed, why = proactive.allowed_now(night)
    assert allowed is False and why == "quiet_hours"


def test_outside_window_blocked(monkeypatch):
    monkeypatch.setenv("LUMI_PROACTIVE_ENABLED", "1")
    from app.config import reload_settings

    reload_settings()
    afternoon = datetime(2026, 10, 28, 15, 0)  # 15:00 不在允许时段
    allowed, why = proactive.allowed_now(afternoon)
    assert allowed is False and why == "outside_window"


def test_within_window_allowed(monkeypatch, db_session):
    monkeypatch.setenv("LUMI_PROACTIVE_ENABLED", "1")
    from app.config import reload_settings

    reload_settings()
    evening = datetime(2026, 10, 28, 19, 30)
    allowed, why = proactive.allowed_now(evening)
    assert allowed is True and why == "ok"


def test_daily_cap_is_enforced(monkeypatch, db_session):
    monkeypatch.setenv("LUMI_PROACTIVE_ENABLED", "1")
    monkeypatch.setenv("LUMI_PROACTIVE_DAILY_CAP", "2")
    from app.config import reload_settings

    reload_settings()

    character = personas.get_character(db_session, key="erii")
    moment = datetime(2026, 10, 28, 19, 0)
    for _ in range(2):
        db_session.add(
            _pending_message(character.id, "第一条", scheduled_at=moment)
        )
    db_session.commit()

    # 直接把配额打满：造 2 条「今天」的记录
    from app.models import ProactiveMessage

    rows = db_session.query(ProactiveMessage).all()
    assert len(rows) == 2
    allowed, why = proactive.allowed_now(moment)
    assert allowed is False and why == "daily_cap_reached"


def _pending_message(character_id: str, content: str, scheduled_at: datetime):
    from app.models import ProactiveMessage

    return ProactiveMessage(
        character_id=character_id,
        content=content,
        reason="checkin",
        status="pending",
        scheduled_at=scheduled_at,
        created_at=datetime.combine(
            scheduled_at.date(), time.min, tzinfo=timezone.utc
        ),
    )


def test_plan_enqueues_when_allowed(monkeypatch, db_session):
    monkeypatch.setenv("LUMI_PROACTIVE_ENABLED", "1")
    from app.config import reload_settings

    reload_settings()
    # 把「上次投递时间」与「今日计数」都放在干净状态，且当前处于允许时段
    character = personas.get_character(db_session, key="erii")
    row = proactive.plan_next(db_session, character_key="erii")
    # 结果取决于运行时刻，因此只断言「要么排上要么给出明确原因」
    if row is None:
        allowed, why = proactive.allowed_now()
        assert why in ("quiet_hours", "outside_window", "daily_cap_reached", "too_soon")
    else:
        assert row["character_id"] == character.id
        assert row["content"]


def test_pending_queue_survives_app_offline(db_session):
    """App 没打开时，服务端也要把消息排好队，等客户端来取。"""
    character = personas.get_character(db_session, key="erii")
    proactive.enqueue(
        db_session, character=character, user_id=None,
        content="离线期间排的一条", reason="greeting",
        scheduled_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    db_session.commit()

    rows = proactive.pending(db_session)
    assert any(r.content == "离线期间排的一条" for r in rows)


def test_deliver_marks_as_sent(db_session):
    from app.models import ProactiveMessage

    character = personas.get_character(db_session, key="erii")
    row = proactive.enqueue(db_session, character=character, user_id=None,
                            content="待投递", reason="checkin")
    db_session.commit()

    assert proactive.deliver(db_session, [row.id]) == 1
    db_session.commit()
    reloaded = db_session.get(ProactiveMessage, row.id)
    assert reloaded.status == "delivered"
    assert reloaded.sent_at is not None


def test_cancel_all_clears_pending(db_session):
    character = personas.get_character(db_session, key="erii")
    for text in ("a", "b", "c"):
        proactive.enqueue(db_session, character=character, user_id=None,
                          content=text, reason="checkin")
    db_session.commit()
    assert proactive.cancel_all(db_session) == 3
    assert proactive.pending(db_session) == []


def test_proactive_status_endpoint_does_not_claim_apns(client):
    body = client.get("/api/v1/proactive/status").json()
    assert body["apns_remote_push"] is False
    assert "APNs" in body["note"]


def test_pending_endpoint_and_delivered(client, db_session):
    from app import personas

    character = personas.get_character(db_session, key="erii")
    proactive.enqueue(db_session, character=character, user_id=None,
                      content="待拉取的问候", reason="greeting")
    db_session.commit()

    rows = client.get("/api/v1/proactive").json()
    assert any(r["content"] == "待拉取的问候" for r in rows)

    ids = [r["id"] for r in rows if r["content"] == "待拉取的问候"]
    assert client.post("/api/v1/proactive/delivered", json={"ids": ids}).json()["delivered"] == 1


def test_cancel_endpoint(client, db_session):
    from app import personas

    character = personas.get_character(db_session, key="erii")
    proactive.enqueue(db_session, character=character, user_id=None,
                      content="会被取消", reason="checkin")
    db_session.commit()
    body = client.post("/api/v1/proactive/cancel").json()
    assert body["cancelled"] >= 1
    assert client.get("/api/v1/proactive").json() == []
