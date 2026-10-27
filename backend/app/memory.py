"""长期记忆：抽取、存储、检索与隔离。

六类记忆（`scope`）：
    user_fact          用户事实（姓名、职业、所在地…）
    user_preference    用户喜好
    shared_experience  用户与该人格共同经历过的聊天
    important_event    重要事件（面试、搬家、纪念日…）
    pending_topic      待续话题
    fictional_life     角色自身的虚构人生

隔离规则（严格，测试覆盖）：
    subject='user'           → 真实用户信息，character_id 为 NULL，**所有人格共享**
    subject='relationship'   → 用户与某个具体人格之间的关系，按 character_id 隔离
    subject='character'      → 角色自己的虚构人生，按 character_id 隔离

因此：**角色的虚构人生不会污染用户的真实信息，不同人格之间也不会互相串戏。**

来源与可信度：
    source_type='user_explicit'    用户明确说出（confidence 0.95）
    source_type='inferred'         由文本模式推断（confidence 0.55）
    source_type='world_simulation' 虚构世界生成（不涉及用户事实）

抽取器默认是**确定性规则**，不需要调用模型、不消耗任何 API 额度；
可在 `LUMI_MEMORY_AUTO_EXTRACT=0` 下关闭，或未来接入模型抽取器替换。
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import MemoryRecord

logger = logging.getLogger("lumi.memory")

# --------------------------------------------------------------- 常量

SCOPES = (
    "user_fact",
    "user_preference",
    "shared_experience",
    "important_event",
    "pending_topic",
    "fictional_life",
)

SUBJECT_USER = "user"
SUBJECT_RELATIONSHIP = "relationship"
SUBJECT_CHARACTER = "character"

SOURCE_USER_EXPLICIT = "user_explicit"
SOURCE_INFERRED = "inferred"
SOURCE_WORLD = "world_simulation"
SOURCE_SYSTEM = "system_seed"

STATUS_ACTIVE = "active"
STATUS_ARCHIVED = "archived"

# 只有真实用户相关的记忆可以跨人格共享
_USER_LEVEL_SCOPES = frozenset({"user_fact", "user_preference"})


@dataclass(frozen=True)
class Candidate:
    """抽取候选记忆。"""

    scope: str
    content: str
    source_type: str
    confidence: float
    salience: int = 5


# --------------------------------------------------------------- 规则抽取

_PATTERNS: tuple[tuple[str, str, str, int], ...] = (
    # (scope, 正则, 模板占位, salience)
    (
        "user_fact",
        r"(?:我叫|我是|我的名字是)([^，。！？,.!?\s]{1,12})",
        "用户的名字是 {0}",
        9,
    ),
    (
        "user_fact",
        r"我是(?:一个)?([^，。！？,.\s]{0,6}(?:工程师|老师|医生|设计师|程序员|产品经理|司机|护士|律师|会计|厨师|服务员|老板|公务员|自由职业者|自由职业))",
        "用户的职业是 {0}",
        9,
    ),
    (
        "user_fact",
        r"我在([^，。！？,.\s]{1,20}(?:公司|学校|大学|研究院|医院|银行|政府|团队|厂))",
        "用户所在单位/学校：{0}",
        7,
    ),
    (
        "user_fact",
        r"我住在([^，。！？,.\s]{1,18}?)(?:市|区|附近|这边)?(?:[，。！？,.\s]|$)",
        "用户住在 {0} 一带",
        6,
    ),
    (
        "user_fact",
        r"我今年(\d{1,3})岁",
        "用户的年龄是 {0} 岁",
        6,
    ),
    (
        "user_preference",
        r"我(?:很|超|最|特别|挺|比较)?喜欢(?!问|去想)([^，。！？,.\s]{1,20})",
        "用户喜欢 {0}",
        7,
    ),
    (
        "user_preference",
        r"我(?:很|超|最|特别|挺|比较)?(?:讨厌|不喜欢|受不了|反感)([^，。！？,.\s]{1,20})",
        "用户不喜欢 {0}",
        7,
    ),
    (
        "user_preference",
        r"比起([^，。！？,.]{1,12})(?:我)?更(?:喜欢|想要|倾向)([^，。！？,.]{1,12})",
        "比起 {0}，用户更喜欢 {1}",
        6,
    ),
    (
        "important_event",
        r"(?:明天|后天|下周|下个月|下周[一二三四五六日天])(?:我)?(?:要|得|得去|会去|准备)([^，。！？,.]{1,24})",
        "用户计划：{0}",
        7,
    ),
    (
        "important_event",
        r"我刚(?:刚)?([^，。！？,.]{1,20})",
        "用户刚刚：{0}",
        5,
    ),
    (
        "pending_topic",
        r"(?:下次|改天|回头|以后|晚点)(?:再|我们)?(?:聊|说|谈|继续)?([^，。！？,.]{0,16})",
        "待续话题：{0}",
        5,
    ),
)

_COMPILED = tuple((scope, re.compile(pattern), template, sal) for scope, pattern, template, sal in _PATTERNS)


def _normalize_text(text: str) -> str:
    """去掉多余空白与首尾标点，保证同一句话得到同一个 hash。"""
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    return cleaned.strip("。！？!?… ")


def content_fingerprint(scope: str, subject: str, content: str) -> str:
    payload = f"{scope}|{subject}|{_normalize_text(content)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def extract_candidates(user_text: str) -> list[Candidate]:
    """从一句用户消息里确定性抽取候选记忆。不调用任何模型。"""
    settings = get_settings()
    if not settings.memory_auto_extract:
        return []

    text = _normalize_text(user_text)
    if len(text) < 4:
        return []

    results: list[Candidate] = []
    seen: set[str] = set()
    for scope, pattern, template, salience in _COMPILED:
        for match in pattern.finditer(text):
            groups = [g.strip() for g in match.groups() if g and g.strip()]
            if not groups:
                continue
            try:
                content = template.format(*groups)
            except (IndexError, KeyError):  # 模板与分组不匹配，跳过该条
                continue
            content = _normalize_text(content)
            if len(content) < 3 or len(content) > 200:
                continue
            if "再说" in content or "问你" in content:
                continue
            fingerprint = content_fingerprint(scope, SUBJECT_USER, content)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            results.append(
                Candidate(
                    scope=scope,
                    content=content,
                    source_type=SOURCE_INFERRED,
                    confidence=settings.memory_confidence_inferred,
                    salience=salience,
                )
            )
    return results


# --------------------------------------------------------------- 写入


def record(
    db: Session,
    *,
    scope: str,
    content: str,
    user_id: str | None = None,
    character_id: str | None = None,
    subject: str | None = None,
    source_type: str = SOURCE_USER_EXPLICIT,
    source_message_id: str | None = None,
    source_ref: str = "",
    confidence: float | None = None,
    salience: int = 5,
) -> MemoryRecord:
    """写入一条记忆；内容相同时更新而非重复插入（幂等）。"""
    if scope not in SCOPES:
        raise ValueError(f"unsupported memory scope: {scope}")

    if subject is None:
        subject = _default_subject(scope)

    if confidence is None:
        confidence = (
            get_settings().memory_confidence_explicit
            if source_type == SOURCE_USER_EXPLICIT
            else get_settings().memory_confidence_inferred
        )

    content = _normalize_text(content)
    existing = _find_same(db, scope, subject, content, character_id)
    if existing is not None:
        existing.content = content
        existing.confidence = max(existing.confidence, confidence)
        existing.salience = max(existing.salience, salience)
        existing.source_type = source_type
        existing.source_message_id = source_message_id or existing.source_message_id
        existing.source_ref = source_ref or existing.source_ref
        existing.status = STATUS_ACTIVE
        existing.archived_at = None
        existing.updated_at = datetime.now(timezone.utc)
        db.flush()
        return existing

    row = MemoryRecord(
        user_id=user_id,
        character_id=character_id,
        scope=scope,
        subject=subject,
        content=content,
        source_type=source_type,
        source_message_id=source_message_id,
        source_ref=source_ref,
        confidence=confidence,
        salience=salience,
        status=STATUS_ACTIVE,
    )
    db.add(row)
    db.flush()
    return row


def _default_subject(scope: str) -> str:
    if scope == "fictional_life":
        return SUBJECT_CHARACTER
    if scope in _USER_LEVEL_SCOPES:
        return SUBJECT_USER
    return SUBJECT_RELATIONSHIP


def _find_same(
    db: Session, scope: str, subject: str, content: str, character_id: str | None
) -> MemoryRecord | None:
    stmt = select(MemoryRecord).where(
        MemoryRecord.scope == scope,
        MemoryRecord.subject == subject,
        MemoryRecord.content == content,
    )
    if character_id:
        stmt = stmt.where(MemoryRecord.character_id == character_id)
    return db.execute(stmt.order_by(MemoryRecord.created_at)).scalar_one_or_none()


def ingest_user_message(
    db: Session,
    *,
    user_id: str | None,
    character_id: str,
    message_id: str,
    user_text: str,
) -> list[MemoryRecord]:
    """在一次对话里自动吸收用户的真实信息。角色的虚构人生**不会**走这里。"""
    saved: list[MemoryRecord] = []
    for candidate in extract_candidates(user_text):
        if candidate.scope in _USER_LEVEL_SCOPES:
            row = record(
                db,
                scope=candidate.scope,
                content=candidate.content,
                user_id=user_id,
                character_id=None,  # 用户层记忆跨人格共享
                subject=SUBJECT_USER,
                source_type=SOURCE_INFERRED,
                source_message_id=message_id,
                source_ref=f"message:{message_id}",
                confidence=candidate.confidence,
                salience=candidate.salience,
            )
        else:
            row = record(
                db,
                scope=candidate.scope,
                content=candidate.content,
                user_id=user_id,
                character_id=character_id,
                subject=SUBJECT_RELATIONSHIP,
                source_type=SOURCE_INFERRED,
                source_message_id=message_id,
                source_ref=f"message:{message_id}",
                confidence=candidate.confidence,
                salience=candidate.salience,
            )
        saved.append(row)
    return saved


# --------------------------------------------------------------- 检索


def query_memories(
    db: Session,
    *,
    character_id: str | None = None,
    scopes: Iterable[str] | None = None,
    include_shared: bool = True,
    limit: int | None = None,
    status: str = STATUS_ACTIVE,
) -> list[MemoryRecord]:
    """按「当前人格」可见范围检索：用户层记忆 + 该人格自己的关系/虚构记忆。"""
    conditions = []
    if include_shared:
        conditions.append(
            (MemoryRecord.subject == SUBJECT_USER) & (MemoryRecord.character_id.is_(None))
        )
    if character_id:
        conditions.append(
            (MemoryRecord.character_id == character_id)
            & (MemoryRecord.subject.in_([SUBJECT_RELATIONSHIP, SUBJECT_CHARACTER]))
        )
    if not conditions:
        conditions.append(MemoryRecord.character_id.is_(None))

    stmt = select(MemoryRecord).where(or_(*conditions))
    if status:
        stmt = stmt.where(MemoryRecord.status == status)
    if scopes:
        stmt = stmt.where(MemoryRecord.scope.in_(list(scopes)))

    # 高显著性 + 高可信度优先
    stmt = stmt.order_by(
        MemoryRecord.salience.desc(), MemoryRecord.confidence.desc(), MemoryRecord.updated_at.desc()
    )
    if limit:
        stmt = stmt.limit(limit)
    return list(db.execute(stmt).scalars())


def prompt_block(records: list[MemoryRecord]) -> str:
    """把记忆渲染成给模型看的文本块；推测条目显式标注「推测」。"""
    if not records:
        return ""
    lines: list[str] = []
    for item in records:
        if item.source_type == SOURCE_WORLD:
            # 虚构世界内容：必须让模型知道这是「她的设定」而不是用户的事实
            tag = "（角色设定，非用户事实）"
        elif item.source_type == SOURCE_INFERRED:
            tag = "（推测，不确定）"
        else:
            tag = "（用户说过）"
        lines.append(f"- [{_scope_label(item.scope)}] {item.content} {tag}")
    return "\n".join(lines)


def _scope_label(scope: str) -> str:
    return {
        "user_fact": "事实",
        "user_preference": "喜好",
        "shared_experience": "共同经历",
        "important_event": "重要事件",
        "pending_topic": "待续话题",
        "fictional_life": "她的虚构生活",
    }.get(scope, scope)


def delete_memory(db: Session, memory_id: str) -> bool:
    row = db.get(MemoryRecord, memory_id)
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True


def archive_memory(db: Session, memory_id: str) -> bool:
    row = db.get(MemoryRecord, memory_id)
    if row is None:
        return False
    row.status = STATUS_ARCHIVED
    row.archived_at = datetime.now(timezone.utc)
    db.flush()
    return True


def export_memories(db: Session, *, character_id: str | None = None) -> list[dict]:
    rows = query_memories(db, character_id=character_id, limit=None, status=None)
    return [r.to_dict() for r in rows]


def count_by_scope(db: Session, character_id: str | None = None) -> dict[str, int]:
    rows = query_memories(db, character_id=character_id, limit=None)
    result: dict[str, int] = {}
    for row in rows:
        result[row.scope] = result.get(row.scope, 0) + 1
    return result


def total_count(db: Session) -> int:
    return int(db.execute(select(func.count()).select_from(MemoryRecord)).scalar_one())
