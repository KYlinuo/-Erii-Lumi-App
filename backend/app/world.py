"""虚构人生：角色自己的世界状态与时间线。

总指令要求：
- 虚构日记、兴趣与爱好、阅读进度、虚构人物关系、个人目标、持续发展的事件时间线；
- 所有虚构事件都要有时间戳，并符合已经建立的设定；
- **角色的虚构人生必须与真实用户信息隔离**；
- 允许使用明确标记的演示数据，但**不得把模拟内容冒充真实 AI 经历**。

因此：所有写入 `world_events` 的记录 `simulated=1`，接口返回体也永远带上
`simulated` 字段；生成算法是**确定性的**（同一角色同一天得到同一批事件），
既不消耗任何模型额度，也可重复回放。
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Character, WorldEvent

logger = logging.getLogger("lumi.world")

KINDS = ("diary", "hobby", "reading", "relationship", "goal", "schedule")

# 需求 14：三种演绎模式。虚构事件可带 meta.mode 标记，切换模式时
# 不删除任何数据，只是检索时排除「明确属于另一模式」的经历。
_MODES = ("canon", "parallel", "pet")


# --------------------------------------------------------------- 模板

# {interest} / {name} / {topic} 等占位符会在生成时替换
_TEMPLATES: dict[str, tuple[str, ...]] = {
    "diary": (
        "今天{interest}的时候走神了。回来才发现时间已经过去很久。",
        "把一天里还算不错的瞬间收了起来，准备晚上再翻一遍。",
        "有点累，但没有特别糟的事。这样的一天也算过得去。",
        "窗外的光变了很多次，我一眼没漏。",
        "说了不太多的话，但听见的比平时多。",
        "给自己记了一行：今天没有把约定忘掉。",
    ),
    "hobby": (
        "又碰了一会儿{interest}，比上次顺手一点点。",
        "把{interest}收好，顺手列了下次想试的做法。",
        "发现自己做起{interest}来会忘记时间，这一点没变过。",
        "{interest}进展不多，但过程挺安静的。",
    ),
    "reading": (
        "今天的{book}又读了几页，进度到约 {progress}%。",
        "在{book}里看到一句不太明白的话，抄在了本子上。",
        "读{book}的时候分心去想别的事，回来只能重读一遍。",
        "{book}的故事走到一半了，有点舍不得读完。",
    ),
    "relationship": (
        "想起上次和你说到的话题，觉得可以再聊聊。",
        "有个小事记了很久，一直没找到合适的时机说。",
        "你说的那句话，我后来回想了几次。",
        "今天没有联系，但好像也不算疏远。",
    ),
    "goal": (
        "把这个星期想做完的事重新排了一遍顺序。",
        "给自己加了件小事当目标，完成起来不算难。",
        "有一项目标推后了，理由是今天的精力不太够。",
        "试着把大一点的目标拆成三步，先做第一步。",
    ),
}

# 每个角色的虚构书单（虚构设定，非真实推荐）
_BOOKS: dict[str, tuple[str, ...]] = {
    "lumi": ("《夜里的第二盏灯》", "《把话说完的人》", "《微光记事》"),
    "linsui": ("《阳台上的第三盆》", "《慢慢来的日子》", "《厨房笔记》"),
    "qilu": ("《跑过城西那条路》", "《两百个想去的地方》", "《风的行程表》"),
    "shenzhou": ("《在高层看灯》", "《短句集》", "《夜行记》"),
    "erii": ("《小本子的第一页》", "《安静的一天》", "《雨天的玩法》"),
}

_MOODS: tuple[str, ...] = ("平静", "有点困", "心情尚可", "专注", "微微走神", "松弛")


def _deterministic_choice(seed: str, options: Iterable[str]) -> str:
    """确定性伪随机：同一 seed 永远得到同一结果，便于回放与测试。"""
    values = list(options)
    if not values:
        return ""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    index = digest[0] % len(values)
    return values[index]


def _fill(template: str, character: Character, day: date) -> str:
    interests = character.interests() or ["自己喜欢的事"]
    books = _BOOKS.get(character.key) or ("《读到一半的书》",)
    seed = f"{character.key}|{template}|{day.isoformat()}"
    interest = _deterministic_choice(seed + "|interest", interests)
    if len(interest) < 3:
        # 太短的兴趣词放进句子里会读不通，补成短语
        interest = f"关于{interest}的事"
    book = _deterministic_choice(seed + "|book", books)
    progress = 10 + (hashlib.sha256((seed + "p").encode()).digest()[1] % 85)
    return template.format(interest=interest, book=book, progress=progress, name=character.name)


# --------------------------------------------------------------- 写入


def record_event(
    db: Session,
    *,
    character_id: str,
    kind: str,
    content: str,
    title: str = "",
    occurred_at: datetime | None = None,
    mood: str = "",
    meta: dict[str, Any] | None = None,
    simulated: bool = True,
    mode: str | None = None,
) -> WorldEvent:
    """写入一条虚构世界事件（`simulated` 默认 True，即它是虚构内容）。"""
    import json

    if kind not in KINDS:
        raise ValueError(f"unsupported world event kind: {kind}")

    payload = dict(meta or {})
    if mode in _MODES:
        payload["mode"] = mode
    row = WorldEvent(
        character_id=character_id,
        kind=kind,
        title=title,
        content=content,
        simulated=1 if simulated else 0,
        mood=mood,
        meta_json=json.dumps(payload, ensure_ascii=False),
        occurred_at=occurred_at or datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    return row


def _day_contents(db: Session, character_id: str, day: date) -> set[str]:
    """该角色在这一天已经生成过的文本（用于严格幂等）。"""
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    rows = db.execute(
        select(WorldEvent.content).where(
            WorldEvent.character_id == character_id,
            WorldEvent.occurred_at >= start,
            WorldEvent.occurred_at < end,
        )
    ).scalars()
    return set(rows)


def _recent_contents(
    db: Session, character_id: str, day: date, recent_days: int = 7
) -> set[str]:
    """最近 recent_days 天用过的文本，用于避免时间线看起来在复制粘贴。

    只回看有限窗口：角色积累很久之后仍能继续生成新内容。
    """
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    window_start = start - timedelta(days=recent_days)
    recent = db.execute(
        select(WorldEvent.content).where(
            WorldEvent.character_id == character_id,
            WorldEvent.occurred_at >= window_start,
            WorldEvent.occurred_at < start,
        )
    ).scalars()
    return set(recent)


def simulate_day(
    db: Session,
    character: Character,
    day: date | None = None,
    *,
    max_events: int = 3,
    mode: str | None = None,
) -> list[WorldEvent]:
    """为某个角色生成某一天的虚构生活。幂等：同一天重复调用不会写第二遍。"""
    day = day or datetime.now(timezone.utc).date()

    # 严格幂等：这一天已经生成过就不再写第二遍
    if _day_contents(db, character.id, day):
        return []

    already = _recent_contents(db, character.id, day)
    weights = ("diary", "hobby", "reading", "relationship", "goal")
    created: list[WorldEvent] = []

    # 剧情连贯：把最近一天的事件标题作为「此前剧情」关联进来，
    # 让时间线不是每天孤立的随机事件，而是有可追溯的上下文。
    previous_day_start = datetime.combine(day - timedelta(days=1), time.min, tzinfo=timezone.utc)
    previous_day = timeline(db, character.id, since=previous_day_start, limit=3)
    references = [
        {"kind": e.kind, "title": e.title, "content": e.content[:40]}
        for e in previous_day
        if e.occurred_at.date() < day
    ]

    for index in range(max_events):
        seed = f"{character.key}|{day.isoformat()}|{index}"

        # 优先挑一个近期没用过的句子；实在挑不出来时仍要保证「有内容」
        content = ""
        attempt = 0
        while attempt < 6:
            kind = _deterministic_choice(seed + f"|kind|{attempt}", weights)
            template = _deterministic_choice(seed + f"|tpl|{attempt}", _TEMPLATES[kind])
            candidate = _fill(template, character, day)
            if candidate not in already or attempt == 5:
                content = candidate
                break
            attempt += 1

        already.add(content)
        mood = _deterministic_choice(seed + "|mood", _MOODS)
        hour = 9 + (hashlib.sha256(seed.encode()).digest()[2] % 13)
        occurred = datetime.combine(day, time(hour=hour, minute=hashlib.sha256(
            (seed + "m").encode()).digest()[3] % 60), tzinfo=timezone.utc)
        created.append(
            record_event(
                db,
                character_id=character.id,
                kind=kind,
                title=_title_of(kind, character),
                content=content,
                occurred_at=occurred,
                mood=mood,
                meta={
                    "generated_by": "deterministic-simulator",
                    "day": day.isoformat(),
                    # 关联此前剧情：让 UI 与模型能看到这条事件的前文，
                    # 避免时间线看起来前后割裂。
                    "references": references,
                },
                mode=mode,
            )
        )
        already.add(content)
    db.flush()
    return created


def ensure_recent_days(db: Session, character: Character, days: int = 3) -> list[WorldEvent]:
    """补齐最近 N 天的虚构生活（首次接入或长时间未跑时用）。"""
    today = datetime.now(timezone.utc).date()
    result: list[WorldEvent] = []
    for offset in range(days, -1, -1):
        result.extend(simulate_day(db, character, today - timedelta(days=offset), max_events=1))
    return result


def _title_of(kind: str, character: Character) -> str:
    return {
        "diary": f"{character.name}的一天",
        "hobby": "记一点爱好",
        "reading": "读书进度",
        "relationship": "想起你",
        "goal": "小目标",
    }.get(kind, "虚构生活")


# --------------------------------------------------------------- 查询


def timeline(
    db: Session,
    character_id: str,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    kinds: Iterable[str] | None = None,
    limit: int = 50,
    mode: str | None = None,
) -> list[WorldEvent]:
    stmt = select(WorldEvent).where(WorldEvent.character_id == character_id)
    if since:
        stmt = stmt.where(WorldEvent.occurred_at >= since)
    if until:
        stmt = stmt.where(WorldEvent.occurred_at <= until)
    if kinds:
        stmt = stmt.where(WorldEvent.kind.in_(list(kinds)))
    if mode in _MODES:
        # 排除「明确标记了另一模式」的经历；未标记的旧事件仍可见，
        # 保证老库升级后不会突然丢掉已有虚构生活。
        # 同时兼容 json.dumps 的两种序列化格式（带空格 / 紧凑），
        # 否则 LIKE 匹配不到带空格的 '{"mode": "canon"}'。
        for other in _MODES:
            if other != mode:
                stmt = stmt.where(WorldEvent.meta_json.notlike(f'%"mode":"{other}"%'))
                stmt = stmt.where(WorldEvent.meta_json.notlike(f'%"mode": "{other}"%'))
    return list(
        db.execute(stmt.order_by(WorldEvent.occurred_at.desc(), WorldEvent.id.desc()).limit(limit)).scalars()
    )


def recent_context(db: Session, character_id: str, *, limit: int = 3, mode: str | None = None) -> str:
    """组装给模型的「最近虚构生活」文本块，始终带虚构声明。"""
    events = timeline(db, character_id, limit=limit, mode=mode)
    if not events:
        return ""
    lines = [f"- {e.title or '虚构生活'}：{e.content}" for e in events]
    return "\n".join(lines)


def count_events(db: Session, character_id: str) -> int:
    rows = db.execute(
        select(WorldEvent).where(WorldEvent.character_id == character_id)
    ).scalars()
    return len(list(rows))
