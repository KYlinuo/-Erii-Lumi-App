"""业务层：会话与消息持久化 + 模型调用编排 + 跨设备同步。

编排顺序（重要）：
    1. 幂等检查：同一 `request_id` 重复提交 → 直接返回上次结果，不产生第二条消息；
    2. 解析人格：会话未绑定人格时按 `character_key` 或默认人格绑定；
    3. 落库用户消息（`conv_seq` 自增）→ **立即 commit**，保证上游失败也不丢；
    4. 抽取并写入长期记忆（用户层共享 / 关系层隔离）；
    5. 组装上下文：人格 system + 虚构世界 + 记忆 + 历史 + 本次提问；
    6. 调用模型（带退避重试），记录延迟与 Token；
    7. 落库助手消息并更新会话。

绝不伪造回复：未配置 Key 时必须抛 `ProviderNotConfigured`，由路由转成 503。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import activities as activities_mod
from app import companion as companion_mod
from app import context_sense
from app import expression_pack
from app import memory as memory_mod
from app import personas
from app import segments as segments_mod
from app import style as style_mod
from app import usage as usage_mod
from app import world as world_mod
from app.config import get_settings
from app.errors import RequestIdConflict
from app.identity import get_or_create_user
from app.llm import LLMMessage, LLMResult, ProviderError
from app.llm.errors import ProviderBadResponse, ProviderBudgetExceeded, ProviderNotConfigured
from app.llm.factory import get_provider
from app.llm.retry import generate_with_retry
from app.models import Conversation, Message

logger = logging.getLogger("lumi.services")

# 取回给模型的上下文条数（不含本次提问）
# 默认滑动窗口；实际取值由 LUMI_CONTEXT_RECENT_MESSAGES 覆盖
MAX_CONTEXT_MESSAGES = 40
TITLE_MAX_LEN = 24
DEFAULT_SYNC_PAGE = 100


def now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- 会话


def get_or_create_conversation(
    db: Session,
    conversation_id: str | None = None,
    *,
    user_id: str | None = None,
    character_key: str | None = None,
    device_id: str | None = None,
    ephemeral: bool = False,
) -> Conversation:
    if conversation_id:
        conv = db.get(Conversation, conversation_id)
        if conv is not None:
            # 已有会话：按需补全归属，不覆盖已有的人格选择
            if conv.character_id is None and character_key:
                character = personas.get_character(db, key=character_key)
                if character is not None:
                    conv.character_id = character.id
            if conv.user_id is None and user_id:
                conv.user_id = user_id
            return conv
        conv = Conversation(id=conversation_id, title="新的对话")
    else:
        conv = Conversation(title="新的对话")

    character = personas.resolve_character(db, character_key)
    if character.id is not None:
        conv.character_id = character.id
    conv.user_id = user_id
    conv.origin_device_id = device_id
    # 需求 23：临时会话标记只在新会话建立时写入，已有会话不改写，
    # 避免把一段正常聊天意外变成「不进记忆」的数据。
    if ephemeral:
        conv.is_ephemeral = 1
    db.add(conv)
    db.flush()
    return conv


def list_conversations(
    db: Session, limit: int = 50, *, user_id: str | None = None,
    character_key: str | None = None,
) -> list[dict]:
    # One indexed SQL query. Never materialize conversation.messages to count them.
    message_count = (
        select(func.count(Message.id))
        .where(Message.conversation_id == Conversation.id, Message.deleted_at.is_(None))
        .correlate(Conversation).scalar_subquery()
    )
    stmt = select(Conversation, message_count).where(Conversation.is_ephemeral == 0)
    if user_id:
        stmt = stmt.where(Conversation.user_id == user_id)
    if character_key:
        character = personas.get_character(db, key=character_key)
        if character is None:
            return []
        stmt = stmt.where(Conversation.character_id == character.id)
    rows = db.execute(stmt.order_by(Conversation.updated_at.desc()).limit(limit)).all()
    return [
        {
            "id": conv.id, "title": conv.title,
            "created_at": conv.created_at.isoformat(),
            "updated_at": conv.updated_at.isoformat(),
            "message_count": count, "character_id": conv.character_id,
            "user_id": conv.user_id, "is_ephemeral": False,
        }
        for conv, count in rows
    ]


def get_messages(db: Session, conversation_id: str, limit: int = 500) -> list[dict]:
    rows = db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.deleted_at.is_(None))
        .order_by(Message.created_at.asc(), Message.id.asc())
        .limit(limit)
    ).scalars().all()
    return [m.to_dict() for m in rows]


def search_messages(
    db: Session,
    conversation_id: str,
    query: str,
    limit: int = 50,
) -> list[dict]:
    """在指定会话内按关键词搜索消息（大小写不敏感的 LIKE）。"""
    query = query.strip()
    if not query:
        return []
    rows = db.execute(
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.deleted_at.is_(None),
            Message.role.in_(("user", "assistant")),
            Message.content.icontains(query, autoescape=True),
        )
        .order_by(Message.created_at.asc(), Message.id.asc())
        .limit(limit)
    ).scalars().all()
    return [m.to_dict() for m in rows]


def delete_conversation(db: Session, conversation_id: str) -> bool:
    conv = db.get(Conversation, conversation_id)
    if conv is None:
        return False
    db.delete(conv)
    return True


# ---------------------------------------------------------------- 消息


def next_conv_seq(db: Session, conversation_id: str) -> int:
    """会话内单调递增序号。增量同步以此为游标。"""
    current = db.execute(
        select(func.max(Message.conv_seq)).where(Message.conversation_id == conversation_id)
    ).scalar()
    return int(current or 0) + 1


def append_message(
    db: Session,
    conversation_id: str,
    role: str,
    content: str,
    *,
    status: str = "ok",
    model: str | None = None,
    error_code: str | None = None,
    latency_ms: int | None = None,
    request_id: str | None = None,
    client_ts: datetime | None = None,
    media_id: str | None = None,
    kind: str = "text",
    tokens_prompt: int | None = None,
    tokens_completion: int | None = None,
) -> Message:
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        status=status,
        model=model,
        error_code=error_code,
        latency_ms=latency_ms,
        request_id=request_id,
        conv_seq=next_conv_seq(db, conversation_id),
        client_ts=client_ts,
        media_id=media_id,
        kind=kind,
        tokens_prompt=tokens_prompt,
        tokens_completion=tokens_completion,
        created_at=now(),
    )
    db.add(msg)
    db.flush()
    return msg


def find_message_by_request_id(db: Session, request_id: str) -> Message | None:
    return db.execute(
        select(Message).where(Message.request_id == request_id)
    ).scalar_one_or_none()


def reply_request_id(request_id: str) -> str:
    """一条请求对应的回复消息使用的 request_id。

    用户消息用 `rid`，它的回复用 `rid#reply`——两者都落在全局唯一索引内，
    同时让「哪条回复属于哪条提问」变成确定性查找，而不是推断。
    """
    return f"{request_id}#reply"


def _find_previous_reply(db: Session, conversation_id: str, request_id: str) -> dict | None:
    """幂等重放：返回同一 request_id 上次产生的完整结果。

    回复与请求通过 `request_id` **精确关联**：用户消息存 `request_id`，
    它的回复存 `request_id + "#reply"`。因此不需要靠序号或时间戳去猜
    「哪条回复属于哪条提问」——那种推断在多轮、重试、乱序落库时一定会出错
    （真实缺陷，已由 `test_idempotent_replay_does_not_swallow_later_turns` 覆盖）。
    """
    user_msg = find_message_by_request_id(db, request_id)
    if user_msg is None or user_msg.conversation_id != conversation_id:
        return None

    assistant = find_message_by_request_id(db, reply_request_id(request_id))
    if assistant is None:
        return None
    conv = db.get(Conversation, conversation_id)
    return {
        "conversation_id": conversation_id,
        "user_message_id": user_msg.id,
        "assistant_message_id": assistant.id,
        "reply": assistant.content,
        "model": assistant.model or "",
        "latency_ms": assistant.latency_ms or 0,
        "character_id": conv.character_id if conv else None,
        "is_mock": (assistant.model or "").startswith("mock-"),
        "idempotent_replay": True,
        "conv_seq": assistant.conv_seq,
        # 需求 08：幂等重放必须返回与首次完全一致的分条（稳定 ID / 顺序）
        "segments": assistant.segment_list(),
        "rhythm": (assistant.segment_list() or [{}])[0].get("rhythm", "natural"),
        "urgent": any(bool(s.get("urgent")) for s in assistant.segment_list()),
    }


def _maybe_update_title(db: Session, conv: Conversation, user_text: str) -> None:
    existing = db.execute(
        select(func.count()).select_from(Message).where(Message.conversation_id == conv.id)
    ).scalar_one()
    if existing > 1:
        return
    text = " ".join(user_text.split())
    conv.title = (text[:TITLE_MAX_LEN] + "…") if len(text) > TITLE_MAX_LEN else (text or "新的对话")
    conv.updated_at = now()


# ---------------------------------------------------------------- 上下文


def _wrap_user_message(user_text: str, quoted_text: str | None) -> str:
    """把「被引用的消息」与「用户现在说的话」分隔开，避免模型把引用当新陈述。

    引用只是背景，不是用户本轮的新内容；长期记忆抽取走的是原始 user_text，
    因此引用内容不会被当成用户事实记录。
    """
    quoted = (quoted_text or "").strip()
    if not quoted:
        return user_text
    return (
        "（用户引用了下面这条消息作为背景，它不是用户现在说的新内容）\n"
        f"<引用>\n{quoted}\n</引用>\n\n"
        f"<用户现在说>\n{user_text}\n</用户现在说>"
    )


def _build_context(
    db: Session,
    *,
    conversation_id: str,
    user_text: str,
    character,
    exclude_message_id: str | None = None,
    quoted_text: str | None = None,
) -> list[LLMMessage]:
    settings = get_settings()
    stmt = select(Message).where(
        Message.conversation_id == conversation_id, Message.status == "ok", Message.deleted_at.is_(None)
    )
    if exclude_message_id:
        stmt = stmt.where(Message.id != exclude_message_id)
    history = db.execute(
        stmt.order_by(Message.created_at.desc(), Message.id.desc()).limit(
            max(4, settings.context_recent_messages or MAX_CONTEXT_MESSAGES)
        )
    ).scalars().all()
    history = list(reversed(history))

    # 记忆与虚构世界都限定在「当前人格」的可见范围内
    # 按「与当前这句话的相关性 + 记忆强度」挑最相关的几条，而不是简单取最新
    memories = memory_mod.query_memories(
        db,
        character_id=character.id,
        limit=settings.memory_injection_limit,
        query=user_text,
    )
    # 被用到的记忆记一次"回忆"，下次权重更高（复习效应）
    memory_mod.touch_recall(db, memories)
    # 需求 14：虚构经历按当前演绎模式隔离；真实用户事实（上面的 memories）
    # 跨模式共享，不随模式切换而丢失。
    mode_state = companion_mod.get_mode(db)
    world_block = (
        world_mod.recent_context(db, character.id, limit=3, mode=mode_state["mode"])
        if character.id
        else ""
    )

    # 需求 10：未完成话题 / 待续话题——隔天聊天时自然接续，
    # 不重复问候、不把已经聊完的事当新话题。
    pending_topics = memory_mod.query_memories(
        db,
        character_id=character.id,
        scopes=["pending_topic"],
        limit=3,
    )
    topic_block = ""
    if pending_topics:
        items = "\n".join(f"- {m.content}" for m in pending_topics)
        topic_block = (
            "【你们还没聊完的话题】\n"
            + items
            + "\n（如果和当前对话相关，可以自然接续；对方说换个话题就放下。）"
        )

    profile = style_mod.get_profile(db)
    # 需求 12：语境判断（分享/倾诉/玩笑/认真提问/求建议）只是猜测，
    # to_prompt 会显式标注「未经用户确认」，避免把情绪推断当事实。
    sense = context_sense.classify(user_text)
    system_text = personas.compose_system_prompt(
        character,
        memory_block=memory_mod.prompt_block(memories),
        world_block=world_block,
        current_time=_local_time_text(),
        style_block=profile.to_prompt(),
        topic_block=topic_block,
        context_block=context_sense.to_prompt(sense, style_length=profile.reply_length),
        mode_block=companion_mod.mode_prompt(mode_state),
        intimacy_block=companion_mod.intimacy_prompt(db),
        topic_archive_block=companion_mod.topic_prompt(db, user_text),
        expression_block=expression_pack.to_prompt(db, user_text),
        reading_block=activities_mod.reading_prompt(db),
        activity_block=activities_mod.activity_prompt(db),
    )

    return [
        LLMMessage(role="system", content=system_text),
        *[LLMMessage(role=m.role, content=m.content) for m in history],
        LLMMessage(role="user", content=_wrap_user_message(user_text, quoted_text)),
    ]


def _local_time_text() -> str:
    settings = get_settings()
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(settings.timezone)
    except Exception:  # noqa: BLE001 - 时区数据缺失时退回 UTC
        tz = timezone.utc
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M（星期" + "一二三四五六日"[datetime.now(tz).weekday()] + "）")


# ---------------------------------------------------------------- 发送


async def send_message(
    db: Session,
    conversation_id: str | None,
    user_text: str,
    *,
    character_key: str | None = None,
    device_id: str | None = None,
    request_id: str | None = None,
    client_ts: datetime | None = None,
    user_id: str | None = None,
    media_id: str | None = None,
    kind: str = "text",
    segment_enabled: bool = True,
    segment_rhythm: str = "natural",
    ephemeral: bool = False,
    quoted_text: str | None = None,
) -> dict:
    """落库用户消息 → 调真实模型 → 落库助手消息。

    失败时抛出 ProviderError，由路由层映射为对应 HTTP 状态码。
    """
    settings = get_settings()
    user = get_or_create_user(db, user_id)
    conv = get_or_create_conversation(
        db,
        conversation_id,
        user_id=user.id,
        character_key=character_key,
        device_id=device_id,
        ephemeral=ephemeral,
    )

    # ---- 1. 幂等：同一 request_id 不重复产生回复 ----
    #
    # 三种情况：
    #   a) 上次已成功产生回复   → 直接重放，不再调用模型；
    #   b) 上次用户消息已落库但上游失败了 → 复用同一条用户消息继续重试，
    #      绝不能再插入一条（否则 UNIQUE(request_id) 会直接把请求打成 500）；
    #   c) request_id 属于另一个会话 → 明确报 409，由客户端修正逻辑。
    reused_user_message = None
    if request_id:
        replay = _find_previous_reply(db, conv.id, request_id)
        if replay is not None:
            logger.info("幂等重放 request_id=%s", request_id)
            return replay

        previous = find_message_by_request_id(db, request_id)
        if previous is not None and previous.conversation_id != conv.id:
            raise RequestIdConflict()
        if previous is not None:
            logger.info("重试 request_id=%s：复用已落库的用户消息", request_id)
            reused_user_message = previous

    character = personas.get_character(db, id=conv.character_id) or personas.resolve_character(
        db, character_key
    )

    # ---- 2. 用户消息先落库并提交，保证上游失败也不丢 ----
    if reused_user_message is not None:
        _maybe_update_title(db, conv, user_text)
        reused_user_message.content = user_text
        reused_user_message.status = "ok"
        reused_user_message.error_code = None
        reused_user_message.client_ts = client_ts
        user_msg = reused_user_message
        db.commit()
    else:
        _maybe_update_title(db, conv, user_text)
        user_msg = append_message(
            db,
            conv.id,
            "user",
            user_text,
            request_id=request_id,
            client_ts=client_ts,
            media_id=media_id,
            kind=kind,
        )
        db.commit()

    # ---- 3. 吸收长期记忆（不在此处生成角色的虚构人生）----
    # 需求 23：临时聊天不进入长期记忆（同时约束后台抽取/检索索引/日记主动）。
    if settings.memory_auto_extract and not conv.is_ephemeral:
        try:
            saved = memory_mod.ingest_user_message(
                db,
                user_id=user.id,
                character_id=character.id,
                message_id=user_msg.id,
                user_text=user_text,
            )
            if saved:
                db.commit()
        except Exception:  # noqa: BLE001 - 记忆失败绝不能影响聊天主链路
            logger.exception("memory ingestion failed, rolled back")
            db.rollback()

    # ---- 4. 单日预算拦截（验收场景 12）：超限停止新增费用 ----
    # 放在「无 Key 拒绝」之前：预算超限是费用控制，与 provider 是否配置无关。
    if usage_mod.check_budget_exceeded(db):
        raise ProviderBudgetExceeded()

    # ---- 4.5 明确拒绝「无 Key 还编造回复」----
    provider = get_provider()
    if not provider.is_configured():
        raise ProviderNotConfigured()

    # ---- 5. 组装上下文并调用模型 ----
    context = _build_context(
        db,
        conversation_id=conv.id,
        user_text=user_text,
        character=character,
        exclude_message_id=user_msg.id,
        quoted_text=quoted_text,
    )
    try:
        result: LLMResult = await generate_with_retry(
            provider, context, max_retries=settings.provider_max_retries
        )
    except ProviderError:
        # 用户消息已经 commit，这里把失败原因记到那条消息上，供客户端显示「失败可重试」
        user_msg.status = "error"
        try:
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        raise

    assistant_msg = append_message(
        db,
        conv.id,
        "assistant",
        result.content,
        model=result.model,
        latency_ms=result.latency_ms,
        tokens_prompt=result.prompt_tokens,
        tokens_completion=result.completion_tokens,
        # 精确绑定：这条回复属于哪一个 request_id（幂等重放靠它定位）
        request_id=reply_request_id(request_id) if request_id else None,
    )
    # 需求 08/12：语义分条 + 语境。turn_id 取幂等 request_id（无则消息 ID），
    # 保证重连、同步、重启后分条 ID 与顺序完全一致；紧急求助零延迟。
    sense = context_sense.classify(user_text)
    seg_list: list[dict] = []
    rhythm = segment_rhythm
    if segment_enabled:
        turn_id = request_id or assistant_msg.id
        seg_list = segments_mod.split_reply(
            result.content,
            turn_id=turn_id,
            rhythm=segment_rhythm,
            urgent=sense.urgent,
        )
        if seg_list:
            rhythm = seg_list[0]["rhythm"]
        assistant_msg.segments_json = segments_mod.serialize(seg_list)
    conv.updated_at = now()
    # 需求 15/17：短回复按频率转手写便签；一次完整对话记一次共同经历。
    # 临时聊天（23）两者都不做——不进入任何未允许的存储范围。
    if not conv.is_ephemeral:
        companion_mod.maybe_note_from_reply(db, result.content, assistant_msg.id, conv.id)
        companion_mod.record_experience(db, "一次完整对话")
    db.commit()

    return {
        "conversation_id": conv.id,
        "user_message_id": user_msg.id,
        "assistant_message_id": assistant_msg.id,
        "reply": result.content,
        "model": result.model,
        "latency_ms": result.latency_ms,
        "character_id": conv.character_id,
        "conv_seq": assistant_msg.conv_seq,
        "is_mock": (result.model or "").startswith("mock-"),
        "idempotent_replay": False,
        "segments": seg_list,
        "rhythm": rhythm,
        "urgent": sense.urgent,
    }


async def send_message_stream(
    db: Session,
    conversation_id: str | None,
    user_text: str,
    *,
    character_key: str | None = None,
    device_id: str | None = None,
    request_id: str | None = None,
    client_ts: datetime | None = None,
    user_id: str | None = None,
    media_id: str | None = None,
    kind: str = "text",
    segment_enabled: bool = True,
    segment_rhythm: str = "natural",
    ephemeral: bool = False,
    quoted_text: str | None = None,
):
    """send_message 的流式版本：逐个产出正文片段，最终 yield 元数据字典。

    产出协议（由路由层转成 SSE）：
      yield {"type": "delta", "text": "..."}   —— 正文增量
      yield {"type": "done", ...}             —— 与 ChatResponse 字段一致的收尾
    中途抛 ProviderError 时，路由层负责把错误写入用户消息并返回。
    """
    settings = get_settings()
    user = get_or_create_user(db, user_id)
    conv = get_or_create_conversation(
        db,
        conversation_id,
        user_id=user.id,
        character_key=character_key,
        device_id=device_id,
        ephemeral=ephemeral,
    )

    # 幂等重放：直接一次性吐完整内容
    if request_id:
        replay = _find_previous_reply(db, conv.id, request_id)
        if replay is not None:
            yield {"type": "delta", "text": replay["reply"]}
            yield {"type": "done", **replay}
            return

        previous = find_message_by_request_id(db, request_id)
        if previous is not None and previous.conversation_id != conv.id:
            raise RequestIdConflict()
        reused_user_message = previous
    else:
        reused_user_message = None

    character = personas.get_character(db, id=conv.character_id) or personas.resolve_character(
        db, character_key
    )

    if reused_user_message is not None:
        _maybe_update_title(db, conv, user_text)
        reused_user_message.content = user_text
        reused_user_message.status = "ok"
        reused_user_message.error_code = None
        reused_user_message.client_ts = client_ts
        user_msg = reused_user_message
        db.commit()
    else:
        _maybe_update_title(db, conv, user_text)
        user_msg = append_message(
            db,
            conv.id,
            "user",
            user_text,
            request_id=request_id,
            client_ts=client_ts,
            media_id=media_id,
            kind=kind,
        )
        db.commit()

    # 需求 23：临时聊天不进入长期记忆（同时约束后台抽取/检索索引/日记主动）。
    if settings.memory_auto_extract and not conv.is_ephemeral:
        try:
            saved = memory_mod.ingest_user_message(
                db,
                user_id=user.id,
                character_id=character.id,
                message_id=user_msg.id,
                user_text=user_text,
            )
            if saved:
                db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("memory ingestion failed, rolled back")
            db.rollback()

    # 单日预算拦截（与 send_message 保持一致）
    if usage_mod.check_budget_exceeded(db):
        raise ProviderBudgetExceeded()

    provider = get_provider()
    if not provider.is_configured():
        raise ProviderNotConfigured()

    context = _build_context(
        db,
        conversation_id=conv.id,
        user_text=user_text,
        character=character,
        exclude_message_id=user_msg.id,
        quoted_text=quoted_text,
    )

    chunks: list[str] = []
    started = time.perf_counter()
    try:
        async for piece in provider.chat_stream(context):
            chunks.append(piece)
            yield {"type": "delta", "text": piece}
    except ProviderError:
        user_msg.status = "error"
        try:
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        raise

    content = "".join(chunks).strip()
    if not content:
        raise ProviderBadResponse(detail="流式上游返回了空内容。")

    latency_ms = int((time.perf_counter() - started) * 1000)
    assistant_msg = append_message(
        db,
        conv.id,
        "assistant",
        content,
        model=provider.model,
        latency_ms=latency_ms,
        request_id=reply_request_id(request_id) if request_id else None,
    )
    # 与非流式路径保持一致的分条与语境元数据
    sense = context_sense.classify(user_text)
    seg_list: list[dict] = []
    rhythm = segment_rhythm
    if segment_enabled:
        turn_id = request_id or assistant_msg.id
        seg_list = segments_mod.split_reply(
            content, turn_id=turn_id, rhythm=segment_rhythm, urgent=sense.urgent
        )
        if seg_list:
            rhythm = seg_list[0]["rhythm"]
        assistant_msg.segments_json = segments_mod.serialize(seg_list)
    conv.updated_at = now()
    if not conv.is_ephemeral:
        companion_mod.maybe_note_from_reply(db, content, assistant_msg.id, conv.id)
        companion_mod.record_experience(db, "一次完整对话")
    db.commit()

    yield {
        "type": "done",
        "conversation_id": conv.id,
        "user_message_id": user_msg.id,
        "assistant_message_id": assistant_msg.id,
        "reply": content,
        "model": provider.model,
        "latency_ms": latency_ms,
        "character_id": conv.character_id,
        "conv_seq": assistant_msg.conv_seq,
        "is_mock": (provider.model or "").startswith("mock-"),
        "idempotent_replay": False,
        "segments": seg_list,
        "rhythm": rhythm,
        "urgent": sense.urgent,
    }


# ---------------------------------------------------------------- 增量同步


def sync_messages(
    db: Session,
    conversation_id: str,
    *,
    after: int = 0,
    limit: int = DEFAULT_SYNC_PAGE,
    include_tombstones: bool = True,
) -> tuple[list[dict], int, str]:
    """拉取某会话 `conv_seq > after` 的消息。返回 (消息, 最新游标, 会话更新时间)。"""
    conv = db.get(Conversation, conversation_id)
    # 需求 23：临时聊天不进入多端同步（不是只在界面隐藏）。
    if conv is not None and conv.is_ephemeral:
        return [], 0, conv.updated_at.isoformat() if conv.updated_at else now().isoformat()

    stmt = select(Message).where(
        Message.conversation_id == conversation_id, Message.conv_seq > after
    )
    if not include_tombstones:
        stmt = stmt.where(Message.deleted_at.is_(None))
    rows = db.execute(
        stmt.order_by(Message.conv_seq.asc()).limit(min(limit, DEFAULT_SYNC_PAGE * 5))
    ).scalars().all()

    return (
        [m.to_sync_dict() for m in rows],
        int(rows[-1].conv_seq or after) if rows else after,
        conv.updated_at.isoformat() if conv else now().isoformat(),
    )


def sync_all(
    db: Session,
    *,
    since_map: dict[str, int] | None = None,
    limit: int = DEFAULT_SYNC_PAGE,
    user_id: str | None = None,
) -> dict:
    """一次拉取所有会话的增量，适合 App 冷启动。

    since_map: {conversation_id: last_conv_seq}；未出现的会话视为从头拉取。
    """
    since_map = since_map or {}
    stmt = select(Conversation).where(Conversation.is_ephemeral == 0)
    if user_id:
        stmt = stmt.where(Conversation.user_id == user_id)
    conversations = [
        c
        for c in db.execute(stmt.order_by(Conversation.updated_at.desc())).scalars()
        if not c.is_ephemeral  # 需求 23：临时会话不参与冷启动全量同步
    ]

    payload = []
    for conv in conversations:
        messages, cursor, updated = sync_messages(
            db, conv.id, after=int(since_map.get(conv.id, 0)), limit=limit
        )
        payload.append(
            {
                "conversation_id": conv.id,
                "title": conv.title,
                "character_id": conv.character_id,
                "updated_at": updated,
                "cursor": cursor,
                "messages": messages,
                "has_more": cursor > int(since_map.get(conv.id, 0)) and len(messages) >= limit,
            }
        )
    latest = db.execute(select(func.max(Message.conv_seq))).scalar()
    return {
        "conversations": payload,
        "global_cursor": int(latest or 0),
        "server_time": now().isoformat(),
    }
