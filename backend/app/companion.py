"""阶段 D 核心逻辑（需求 13–18 / 21–22）：设定、演绎模式、便签、熟悉度、
回忆时间线、长期话题档案、连续虚构日常的日程变更。

设计约束：
- 设置类状态用 app_settings（key-value，带版本与变更历史）；
- 有来源回溯的数据用专用表（timeline_events / topic_archives / sticky_notes）；
- 真实用户事实跨模式共享，角色虚构经历按模式隔离（world.meta.mode）；
- 自动生成的回忆一律 verified=0，未证实不进默认时间线；
- 长期话题只按相关性调取 1–2 条，绝不每轮发送全部历史。
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select

from app.models import (
    AppSetting,
    Conversation,
    MediaAsset,
    Message,
    Promise,
    StickyNote,
    TimelineEvent,
    TopicArchive,
    WorldEvent,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _get(db, key: str, default):
    row = db.get(AppSetting, key)
    if row is None:
        return default
    try:
        value = json.loads(row.value)
    except (json.JSONDecodeError, TypeError):
        return default
    return value if isinstance(value, type(default)) else default


def _set(db, key: str, value, commit: bool = True) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value="")
        db.add(row)
    row.value = json.dumps(value, ensure_ascii=False)
    db.flush()
    if commit:
        db.commit()


# ---------------------------------------------------------------- 14 演绎模式

_MODES = {
    "canon": {"label": "贴近原著", "spoiler_default": "known"},
    "parallel": {"label": "原著性格的平行日常", "spoiler_default": "none"},
    "pet": {"label": "沿用桌宠个人设定", "spoiler_default": "none"},
}
_SPOILER_SCOPES = ("none", "known", "partial", "full")
MODE_KEY = "persona_mode"
MODE_STATE_VERSION = 1


def get_mode(db) -> dict:
    data = _get(db, MODE_KEY, {})
    mode = data.get("mode") if data.get("mode") in _MODES else "parallel"
    scope = data.get("spoiler_scope") if data.get("spoiler_scope") in _SPOILER_SCOPES else "none"
    return {
        "mode": mode,
        "label": _MODES[mode]["label"],
        "spoiler_scope": scope,
        "available": [{"id": k, "label": v["label"]} for k, v in _MODES.items()],
        "spoiler_scopes": list(_SPOILER_SCOPES),
        "version": data.get("version", MODE_STATE_VERSION),
        "changed_at": data.get("changed_at"),
        "history": data.get("history", [])[-10:],
        "shared_facts_rule": (
            "真实用户事实（名字/偏好/共同经历）跨模式共享；角色虚构经历按模式隔离，"
            "切换模式不删除聊天、不混入另一模式的角色经历。"
        ),
    }


def set_mode(db, mode: str, spoiler_scope: str | None = None) -> dict:
    if mode not in _MODES:
        mode = "parallel"
    if spoiler_scope not in _SPOILER_SCOPES:
        spoiler_scope = _MODES[mode]["spoiler_default"]
    previous = get_mode(db)
    history = list(previous["history"])
    history.append(
        {
            "from": previous["mode"],
            "to": mode,
            "at": _now().isoformat(),
            "version": previous["version"] + 1,
        }
    )
    _set(
        db,
        MODE_KEY,
        {
            "mode": mode,
            "spoiler_scope": spoiler_scope,
            "version": previous["version"] + 1,
            "changed_at": _now().isoformat(),
            "history": history[-20:],
        },
    )
    return get_mode(db)


def mode_prompt(state: dict) -> str:
    scope_hint = {
        "none": "不主动提原著任何具体剧情，不剧透；",
        "known": "只谈用户明确表示已经读过的范围，不越过；",
        "partial": "只做模糊提及，不给关键情节细节；",
        "full": "可以讨论全部原著内容（用户主动选择）。",
    }[state["spoiler_scope"]]
    return (
        "【演绎模式（同一时间只激活一种）】\n"
        f"- 当前：{state['label']}（{state['mode']}）；剧透范围：{state['spoiler_scope']}——{scope_hint}\n"
        f"- {state['shared_facts_rule']}\n"
        "- 不要提及其他模式下才发生的角色经历，也不要因为切换模式就删掉或改写聊天记录。"
    )


# ---------------------------------------------------------------- 17 熟悉程度

INTIMACY_KEY = "intimacy_state"
_STAGES = (
    (0, "初识", "保持一点距离，用普通的称呼，不要突然变黏。"),
    (20, "有点熟", "可以偶尔提起上次聊过的小事，但仍别太热情。"),
    (45, "会等对方回来", "可以自然地说「你回来了」，记住对方的小习惯。"),
    (70, "有共同笑话", "可以用只有你们懂的简短说法，但别解释给外人听。"),
    (90, "很黏", "会主动等、会小声撒娇，但仍然是那个安静的绘梨衣。"),
)


def _stage(level: int) -> tuple[str, str]:
    name, hint = _STAGES[0][1], _STAGES[0][2]
    for threshold, sname, shint in _STAGES:
        if level >= threshold:
            name, hint = sname, shint
    return name, hint


def get_intimacy(db, reveal: bool = False) -> dict:
    data = _get(db, INTIMACY_KEY, {})
    level = int(data.get("level", 0))
    paused = bool(data.get("paused", False))
    name, hint = _stage(level)
    out = {
        "stage": name,
        "paused": paused,
        "hint": hint,
        "history": data.get("history", [])[-10:],
        "version": data.get("version", 1),
        "hidden": not reveal,
    }
    out["level"] = level if reveal else None
    return out


def record_experience(db, reason: str = "") -> dict:
    """一次有效共同经历只 +1，变化缓慢；暂停时不变化；可解释（history）。"""
    data = _get(db, INTIMACY_KEY, {})
    if bool(data.get("paused", False)):
        return get_intimacy(db)
    level = min(100, int(data.get("level", 0)) + 1)
    history = list(data.get("history", []))
    history.append({"delta": 1, "reason": reason or "有效共同经历", "at": _now().isoformat(), "level": level})
    _set(
        db,
        INTIMACY_KEY,
        {
            "level": level,
            "paused": False,
            "version": int(data.get("version", 1)) + 1,
            "history": history[-30:],
        },
    )
    return get_intimacy(db)


def set_intimacy_paused(db, paused: bool) -> dict:
    data = _get(db, INTIMACY_KEY, {})
    data["paused"] = bool(paused)
    data["version"] = int(data.get("version", 1)) + 1
    _set(db, INTIMACY_KEY, data)
    return get_intimacy(db)


def reset_intimacy(db) -> dict:
    _set(db, INTIMACY_KEY, {"level": 0, "paused": False, "version": 1, "history": []})
    return get_intimacy(db)


def intimacy_prompt(db) -> str:
    state = get_intimacy(db)
    return (
        "【熟悉程度（随共同经历缓慢变化，可暂停/重置，数值默认隐藏）】\n"
        f"- 当前阶段：{state['stage']}；{state['hint']}\n"
        "- 不要突然改变称呼或互动习惯，也不要把阶段数值说给用户听。"
    )


# ---------------------------------------------------------------- 15 手写便签

NOTE_FREQ_KEY = "note_frequency"
_NOTE_FREQS = ("off", "low", "medium", "high")
_NOTE_PROB = {"off": 0, "low": 4, "medium": 2, "high": 1}  # 1/N 概率


def note_settings(db) -> dict:
    data = _get(db, NOTE_FREQ_KEY, {})
    freq = data.get("frequency") if data.get("frequency") in _NOTE_FREQS else "medium"
    return {
        "enabled": freq != "off",
        "frequency": freq,
        "available": list(_NOTE_FREQS),
        "notice": "手写便签可切回普通文字（frequency=off）；手写效果需保证可读性与无障碍。",
    }


def set_note_settings(db, frequency: str) -> dict:
    if frequency not in _NOTE_FREQS:
        frequency = "medium"
    _set(db, NOTE_FREQ_KEY, {"frequency": frequency, "version": 1})
    return note_settings(db)


def add_note(db, content: str, *, source_message_id=None, source_conversation_id=None) -> dict:
    row = StickyNote(
        content=(content or "").strip()[:500],
        source_message_id=source_message_id,
        source_conversation_id=source_conversation_id,
    )
    db.add(row)
    db.commit()
    return row.to_dict()


def list_notes(db, starred_only: bool = False, limit: int = 100) -> list[dict]:
    stmt = select(StickyNote)
    if starred_only:
        stmt = stmt.where(StickyNote.starred == 1)
    rows = db.execute(stmt.order_by(StickyNote.created_at.desc()).limit(limit)).scalars().all()
    return [r.to_dict() for r in rows]


def star_note(db, note_id: str, starred: bool) -> dict | None:
    row = db.get(StickyNote, note_id)
    if row is None:
        return None
    row.starred = 1 if starred else 0
    db.commit()
    return row.to_dict()


def delete_note(db, note_id: str) -> bool:
    row = db.get(StickyNote, note_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def maybe_note_from_reply(db, content: str, message_id: str, conversation_id: str) -> dict | None:
    """按频率把短句/心情/约定自动转成手写便签。确定性 hash，可重放、可测试。"""
    settings = note_settings(db)
    divisor = _NOTE_PROB[settings["frequency"]]
    if divisor == 0 or not content or len(content.strip()) > 40:
        return None
    digest = hashlib.sha256(f"{message_id}|note".encode()).digest()[0]
    if digest % divisor != 0:
        return None
    return add_note(
        db,
        content.strip(),
        source_message_id=message_id,
        source_conversation_id=conversation_id,
    )


# ---------------------------------------------------------------- 21 共同回忆时间线

_TIMELINE_KINDS = ("first_chat", "promise", "starred", "photo", "milestone", "manual")


def add_timeline(
    db,
    *,
    kind: str,
    title: str,
    content: str,
    source_message_id: str | None = None,
    source_ref: str = "",
    verified: bool = False,
    occurred_at: datetime | None = None,
    character_id: str | None = None,
) -> dict:
    if kind not in _TIMELINE_KINDS:
        kind = "manual"
    row = TimelineEvent(
        character_id=character_id,
        kind=kind,
        title=title[:255],
        content=content,
        source_message_id=source_message_id,
        source_ref=source_ref,
        verified=1 if verified else 0,
        occurred_at=occurred_at or _now(),
    )
    db.add(row)
    db.commit()
    return row.to_dict()


def list_timeline(db, include_unverified: bool = False, limit: int = 200) -> list[dict]:
    stmt = select(TimelineEvent).where(TimelineEvent.deleted_at.is_(None))
    if not include_unverified:
        # 硬约束：未经证实的事件不进入默认时间线
        stmt = stmt.where(TimelineEvent.verified == 1)
    rows = db.execute(stmt.order_by(TimelineEvent.occurred_at.desc()).limit(limit)).scalars().all()
    return [r.to_dict() for r in rows]


def verify_timeline(db, event_id: str) -> dict | None:
    row = db.get(TimelineEvent, event_id)
    if row is None:
        return None
    row.verified = 1
    db.commit()
    return row.to_dict()


def update_timeline(db, event_id: str, payload: dict) -> dict | None:
    row = db.get(TimelineEvent, event_id)
    if row is None:
        return None
    if "title" in payload:
        row.title = str(payload["title"])[:255]
    if "content" in payload:
        row.content = str(payload["content"])
    db.commit()
    return row.to_dict()


def delete_timeline(db, event_id: str) -> bool:
    row = db.get(TimelineEvent, event_id)
    if row is None:
        return False
    row.deleted_at = _now()
    db.commit()
    return True


def sync_from_sources(db, character_id: str | None = None) -> dict:
    """从明确的用户操作生成 verified 回忆；虚构世界事件只作未证实候选。

    幂等：用 source_ref 去重，重复执行不产生第二条。
    """
    existing = {
        r[0]
        for r in db.execute(select(TimelineEvent.source_ref)).all()
        if r[0]
    }
    created = {"first_chat": 0, "promise": 0, "starred": 0, "photo": 0, "candidate": 0}

    first = db.execute(
        select(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Message.role == "user", Conversation.is_ephemeral == 0, Message.deleted_at.is_(None))
        .order_by(Message.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()
    if first is not None:
        ref = f"message:{first.id}"
        if ref not in existing:
            add_timeline(
                db, kind="first_chat", title="第一次聊天",
                content=(first.content or "")[:120], source_message_id=first.id,
                source_ref=ref, verified=True, occurred_at=first.created_at,
                character_id=character_id,
            )
            existing.add(ref)
            created["first_chat"] += 1

    for promise in db.execute(
        select(Promise).where(Promise.certainty == "confirmed").limit(200)
    ).scalars().all():
        ref = f"promise:{promise.id}"
        if ref in existing:
            continue
        add_timeline(
            db, kind="promise", title="一个约定",
            content=promise.content, source_ref=ref, verified=True,
            occurred_at=promise.created_at, character_id=character_id,
        )
        existing.add(ref)
        created["promise"] += 1

    for msg in db.execute(
        select(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Message.starred.is_(True), Conversation.is_ephemeral == 0, Message.deleted_at.is_(None))
        .limit(200)
    ).scalars().all():
        ref = f"message:{msg.id}"
        if ref in existing:
            continue
        add_timeline(
            db, kind="starred", title="收藏的一条消息",
            content=(msg.content or "")[:120], source_message_id=msg.id,
            source_ref=ref, verified=True, occurred_at=msg.created_at,
            character_id=character_id,
        )
        existing.add(ref)
        created["starred"] += 1

    for asset in db.execute(
        select(MediaAsset).where(MediaAsset.kind == "image").limit(200)
    ).scalars().all():
        ref = f"media:{asset.id}"
        if ref in existing:
            continue
        add_timeline(
            db, kind="photo", title="一张照片", content="用户上传的照片",
            source_ref=ref, verified=True, occurred_at=asset.created_at,
            character_id=character_id,
        )
        existing.add(ref)
        created["photo"] += 1

    # 虚构世界事件 = 未证实候选，verified=0，需要用户确认才进时间线
    for event in db.execute(select(WorldEvent).limit(200)).scalars().all():
        ref = f"world:{event.id}"
        if ref in existing:
            continue
        add_timeline(
            db, kind="milestone", title=event.title or "虚构日常",
            content=event.content, source_ref=ref, verified=False,
            occurred_at=event.occurred_at, character_id=event.character_id,
        )
        existing.add(ref)
        created["candidate"] += 1

    return {"created": created, "note": "虚构事件仅作未证实候选（verified=0），不进入默认时间线。"}


# ---------------------------------------------------------------- 22 长期话题档案

TOPIC_ACTIVE_KEY = "active_topic_id"


def list_topics(db, status: str | None = None) -> list[dict]:
    stmt = select(TopicArchive)
    if status:
        stmt = stmt.where(TopicArchive.status == status)
    rows = db.execute(stmt.order_by(TopicArchive.updated_at.desc())).scalars().all()
    return [r.to_dict() for r in rows]


def create_topic(db, payload: dict) -> dict:
    row = TopicArchive(
        title=str(payload.get("title") or "未命名话题")[:200],
        goal=str(payload.get("goal") or ""),
        latest_progress=str(payload.get("latest_progress") or ""),
        key_conclusions=str(payload.get("key_conclusions") or ""),
        next_step=str(payload.get("next_step") or ""),
        keywords=",".join(str(k).strip() for k in (payload.get("keywords") or []) if str(k).strip())[:512],
        status=str(payload.get("status") or "active"),
    )
    db.add(row)
    db.commit()
    return row.to_dict()


def update_topic(db, topic_id: str, payload: dict) -> dict | None:
    row = db.get(TopicArchive, topic_id)
    if row is None:
        return None
    for field in ("title", "goal", "latest_progress", "key_conclusions", "next_step", "status"):
        if field in payload:
            setattr(row, field, str(payload[field]))
    if "keywords" in payload:
        row.keywords = ",".join(str(k).strip() for k in payload["keywords"] if str(k).strip())[:512]
    db.commit()
    return row.to_dict()


def delete_topic(db, topic_id: str) -> bool:
    row = db.get(TopicArchive, topic_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def set_active_topic(db, topic_id: str | None) -> dict:
    _set(db, TOPIC_ACTIVE_KEY, {"id": topic_id, "at": _now().isoformat()})
    return {"active_topic_id": topic_id}


def _active_id(db) -> str | None:
    data = _get(db, TOPIC_ACTIVE_KEY, {})
    return data.get("id")


def relevant_topics(db, query: str, limit: int = 2) -> list[dict]:
    """按关键词相关性挑 1–2 个档案；手动激活的优先。不发送全部历史。"""
    rows = list(db.execute(select(TopicArchive).where(TopicArchive.status != "archived")).scalars().all())
    active = _active_id(db)
    q = query or ""

    def score(row: TopicArchive) -> int:
        keys = [k for k in (row.keywords or "").split(",") if k]
        hits = sum(1 for k in keys if k and k in q)
        if row.title and row.title in q:
            hits += 2
        if row.id == active:
            hits += 3
        return hits

    ranked = sorted(rows, key=lambda r: -score(r))
    ranked = [r for r in ranked if score(r) > 0][:limit]
    if not ranked and active:
        ranked = [r for r in rows if r.id == active][:1]
    return [r.to_dict() for r in ranked]


def topic_prompt(db, query: str) -> str:
    topics = relevant_topics(db, query, limit=2)
    if not topics:
        return ""
    lines = []
    for t in topics:
        lines.append(
            f"- {t['title']}：目标={t['goal']}；进度={t['latest_progress']}；"
            f"结论={t['key_conclusions']}；下一步={t['next_step']}"
        )
    return (
        "【长期话题档案（只调取与当前最相关的，不发送全部历史）】\n"
        + "\n".join(lines)
        + "\n- 相关时才自然提起；用户手动切换话题时以上下文为准，不要硬塞。"
    )


# ---------------------------------------------------------------- 16 日程变更


def record_schedule_change(db, character_id: str, day: str, content: str, mode: str | None = None) -> dict:
    """记录一次日程变更；同一天只保留一条「有效」设定，旧的标记 superseded。"""
    from app import world

    try:
        target = date.fromisoformat(day)
    except ValueError:
        target = _now().date()
    start = datetime.combine(target, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)

    existing = [
        e
        for e in world.timeline(db, character_id, kinds=["schedule"], since=start, until=end, limit=100, mode=mode)
        if not e.meta().get("superseded")
    ]
    superseded_ids = [e.id for e in existing]
    for e in existing:
        meta = e.meta()
        meta["superseded"] = True
        meta["superseded_at"] = _now().isoformat()
        e.meta_json = json.dumps(meta, ensure_ascii=False)
    db.flush()

    event = world.record_event(
        db,
        character_id=character_id,
        kind="schedule",
        title="日程变更",
        content=content,
        occurred_at=start + timedelta(hours=12),
        meta={
            "type": "schedule_change",
            "day": target.isoformat(),
            "supersedes": superseded_ids,
        },
        mode=mode,
    )
    db.commit()
    return {
        "id": event.id,
        "day": target.isoformat(),
        "content": content,
        "supersedes": superseded_ids,
        "notice": "同一天只保留一条有效日程；旧设定保留记录但标记 superseded，不再作为冲突设定生效。",
    }


def list_schedule(db, character_id: str, day: str | None = None, mode: str | None = None) -> dict:
    from app import world

    events = world.timeline(db, character_id, kinds=["schedule"], limit=100, mode=mode)
    if day:
        events = [e for e in events if e.occurred_at and e.occurred_at.date().isoformat() == day]
    active = [e for e in events if not e.meta().get("superseded")]
    by_day: dict[str, list[str]] = {}
    for e in active:
        key = e.occurred_at.date().isoformat() if e.occurred_at else "unknown"
        by_day.setdefault(key, []).append(e.id)
    conflicts = {d: ids for d, ids in by_day.items() if len(ids) > 1}
    return {
        "events": [e.to_dict() for e in events],
        "active": [e.to_dict() for e in active],
        "conflicts": conflicts,
    }
