"""服务器主动联系调度器。

约束（来自总指令）：
- 允许时段、每日次数上限、随机化、延续过去话题、按虚构日记分享故事；
- 用户忙碌 / 夜间免打扰时暂停，并且可以**即时关闭**；
- App 没打开时服务端也要把消息排好队，客户端下次同步时补拉。

诚实边界：**本模块不实现也不声称实现了 APNs 远程推送**。
免费 Apple ID 自签不支持可靠远程唤醒，这一点必须如实写进文档与 UI，
因此这里的机制是「服务端排 + 客户端拉」（pull-based）。
"""

from __future__ import annotations

import logging
import random
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import memory as memory_mod
from app import personas, world
from app.config import get_settings
from app.models import Conversation, Message, ProactiveMessage, WorldEvent

logger = logging.getLogger("lumi.proactive")

STATUS_PENDING = "pending"
STATUS_DELIVERED = "delivered"
STATUS_CANCELLED = "cancelled"


# --------------------------------------------------------------- 时段判断


def _parse_ranges(spec: str) -> list[tuple[time, time]]:
    """解析 "09:00-12:00,18:00-23:00" 形式的时间段。"""
    ranges: list[tuple[time, time]] = []
    for chunk in (spec or "").split(","):
        chunk = chunk.strip()
        if "-" not in chunk:
            continue
        left, right = chunk.split("-", 1)
        try:
            start = datetime.strptime(left.strip(), "%H:%M").time()
            end = datetime.strptime(right.strip(), "%H:%M").time()
        except ValueError:
            logger.warning("无法解析时间段：%s", chunk)
            continue
        ranges.append((start, end))
    return ranges


def _in_ranges(moment: datetime, ranges: list[tuple[time, time]]) -> bool:
    current = moment.time()
    for start, end in ranges:
        if start <= end:
            if start <= current <= end:
                return True
        else:  # 跨午夜，例如 23:30-07:30
            if current >= start or current <= end:
                return True
    return False


def local_now() -> datetime:
    settings = get_settings()
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(settings.timezone))
    except Exception:  # noqa: BLE001 - 缺少 tzdata 时退回 UTC
        return datetime.now(timezone.utc)


def _runtime_override() -> dict:
    """读取用户在设置页保存的主动联系参数（app_settings），无则回落 .env。"""
    import json

    try:
        from app.database import get_session_factory
        from app.models import AppSetting

        with get_session_factory()() as db:
            row = db.get(AppSetting, "proactive_settings")
            value = json.loads(row.value) if row is not None and row.value else {}
            return value if isinstance(value, dict) else {}
    except Exception:  # noqa: BLE001 - 设置读取失败不能拖垮调度
        return {}


def _user_idle_hours() -> float:
    """距用户最近一条消息多少小时；长期未回复时主动联系降频。"""
    from app.database import get_session_factory

    with get_session_factory()() as db:
        last = db.execute(
            select(func.max(Message.created_at)).join(Conversation).where(
                Message.role == "user", Message.deleted_at.is_(None), Conversation.is_ephemeral == 0
            )
        ).scalar()
    if last is None:
        return 0.0
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - last).total_seconds() / 3600


def allowed_now(moment: datetime | None = None) -> tuple[bool, str]:
    """返回 (是否允许主动联系, 原因)。运行时设置优先于 .env。"""
    settings = get_settings()
    moment = moment or local_now()
    override = _runtime_override()

    enabled = bool(override.get("enabled", settings.proactive_enabled))
    paused = bool(override.get("paused", False))
    windows = str(override.get("windows", settings.proactive_windows))
    cap = int(override.get("daily_cap", settings.proactive_daily_cap))
    interval = int(override.get("min_interval_minutes", settings.proactive_min_interval_minutes))

    if not enabled or paused:
        return False, "proactive_disabled"
    if _in_ranges(moment, _parse_ranges(settings.quiet_hours)):
        return False, "quiet_hours"
    if not _in_ranges(moment, _parse_ranges(windows)):
        return False, "outside_window"

    today_sent = daily_count(moment.date())
    if today_sent >= cap:
        return False, "daily_cap_reached"

    last = last_sent_at()
    if last is not None:
        gap = (moment - last).total_seconds() / 60
        # 需求 25：长期未回复时降低频率（间隔翻倍），避免越没人理越打扰。
        if _user_idle_hours() > 72:
            interval *= 2
        if gap < interval:
            return False, "too_soon"
    return True, "ok"


# --------------------------------------------------------------- 计数


def daily_count(day: date) -> int:
    from app.database import get_session_factory

    factory = get_session_factory()
    with factory() as db:
        start = datetime.combine(day, time.min)
        end = start + timedelta(days=1)
        return int(
            db.execute(
                select(func.count())
                .select_from(ProactiveMessage)
                .where(
                    ProactiveMessage.created_at >= start,
                    ProactiveMessage.created_at < end,
                    ProactiveMessage.status != STATUS_CANCELLED,
                )
            ).scalar_one()
        )


def last_sent_at() -> datetime | None:
    """上一次真正投递（delivered）的时间。"""
    from app.database import get_session_factory

    factory = get_session_factory()
    with factory() as db:
        row = db.execute(
            select(ProactiveMessage)
            .where(ProactiveMessage.status == STATUS_DELIVERED, ProactiveMessage.sent_at.is_not(None))
            .order_by(ProactiveMessage.sent_at.desc())
        ).scalar_one_or_none()
        return row.sent_at if row else None


# --------------------------------------------------------------- 内容生成


def _pick_latest_topic(db: Session, character_id: str) -> str | None:
    rows = memory_mod.query_memories(
        db, character_id=character_id, scopes=["pending_topic"], limit=3
    )
    return rows[0].content if rows else None


def _pick_world_event(db: Session, character_id: str) -> WorldEvent | None:
    events = world.timeline(db, character_id, limit=5)
    if not events:
        return None
    return random.choice(events)  # noqa: S311 - 主动联系需要随机性，非安全用途


def compose_message(db: Session, character, user_id: str | None) -> tuple[str, str] | None:
    """生成一条主动联系内容。返回 (content, reason)；无法生成时返回 None。"""
    topic = _pick_latest_topic(db, character.id)
    event = _pick_world_event(db, character.id)

    choices: list[tuple[str, str]] = []
    if topic:
        choices.append(
            (f"上次说的「{topic.replace('待续话题：', '')}」我一直记着。要不要接着聊？", "followup")
        )
    if event is not None:
        choices.append((f"今天有一件小事想说给你听：{event.content}", "diary"))
    choices.append(("这会儿没事，就是想看看你在不在。", "checkin"))
    choices.append((f"{character.greeting or '嗨，'} 今天过得怎么样？", "greeting"))

    content, reason = random.choice(choices)  # noqa: S311
    return content, reason


def enqueue(
    db: Session,
    *,
    character,
    user_id: str | None,
    content: str,
    reason: str,
    conversation_id: str | None = None,
    scheduled_at: datetime | None = None,
) -> ProactiveMessage:
    # 需求 25：重复通知去重 —— 同样内容的 pending 还在队列里就不再入队。
    duplicate = db.execute(
        select(ProactiveMessage).where(
            ProactiveMessage.status == STATUS_PENDING,
            ProactiveMessage.content == content,
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        return duplicate

    row = ProactiveMessage(
        user_id=user_id,
        character_id=character.id,
        conversation_id=conversation_id,
        content=content,
        reason=reason,
        status=STATUS_PENDING,
        scheduled_at=scheduled_at or datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    return row


def _expire_stale(db: Session, hours: int = 24) -> int:
    """过期关心：超期未投递的 pending 作废，避免迟到的打扰。"""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = db.execute(
        select(ProactiveMessage).where(
            ProactiveMessage.status == STATUS_PENDING,
            ProactiveMessage.scheduled_at < cutoff,
        )
    ).scalars().all()
    for row in rows:
        row.status = STATUS_CANCELLED
    if rows:
        db.flush()
    return len(rows)


def plan_next(db: Session, user_id: str | None = None, character_key: str | None = None) -> dict | None:
    """判断是否该发一条主动联系；合适则入队并返回该条目。"""
    settings = get_settings()
    _expire_stale(db)
    allowed, why = allowed_now()
    if not allowed:
        logger.debug("主动联系未触发：%s", why)
        return None

    character = personas.resolve_character(db, character_key)
    composed = compose_message(db, character, user_id)
    if composed is None:
        return None
    content, reason = composed

    latest_conv = db.execute(
        select(Conversation)
        .where(Conversation.character_id == character.id, Conversation.is_ephemeral == 0)
        .order_by(Conversation.updated_at.desc())
    ).scalar_one_or_none()

    row = enqueue(
        db,
        character=character,
        user_id=user_id,
        content=content,
        reason=reason,
        conversation_id=latest_conv.id if latest_conv else None,
    )
    db.commit()
    logger.info("主动联系入队：character=%s reason=%s", character.key, reason)
    _ = settings
    return row.to_dict()


def pending(db: Session, *, limit: int = 20, character_id: str | None = None) -> list[ProactiveMessage]:
    stmt = select(ProactiveMessage).where(ProactiveMessage.status == STATUS_PENDING)
    if character_id:
        stmt = stmt.where(ProactiveMessage.character_id == character_id)
    return list(db.execute(stmt.order_by(ProactiveMessage.scheduled_at).limit(limit)).scalars())


def deliver(db: Session, ids: list[str]) -> int:
    """客户端拉取成功后标记为已投递。返回实际标记数量。"""
    count = 0
    for pid in ids:
        row = db.get(ProactiveMessage, pid)
        if row is None or row.status != STATUS_PENDING:
            continue
        row.status = STATUS_DELIVERED
        row.sent_at = datetime.now(timezone.utc)
        count += 1
    db.flush()
    if count:
        db.commit()
    return count


def cancel_all(db: Session) -> int:
    """「即时关闭主动消息」：撤销所有尚未投递的条目。"""
    rows = pending(db, limit=500)
    for row in rows:
        row.status = STATUS_CANCELLED
    db.flush()
    if rows:
        db.commit()
    return len(rows)


def has_user_activity_recently(db: Session, minutes: int = 15) -> bool:
    """用户刚用过 → 视作「可能还在忙/自己会聊」，不再重复打扰。"""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    row = db.execute(
        select(Message).join(Conversation).where(
            Message.role == "user", Message.created_at >= cutoff,
            Message.deleted_at.is_(None), Conversation.is_ephemeral == 0
        ).limit(1)
    ).scalar_one_or_none()
    return row is not None
