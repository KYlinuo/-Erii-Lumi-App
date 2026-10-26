"""业务层：会话与消息的持久化 + 模型调用编排。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.llm import LLMMessage, LLMResult, ProviderError
from app.llm.errors import ProviderNotConfigured
from app.llm.factory import get_provider
from app.models import Conversation, Message

logger = logging.getLogger("lumi.services")

# 取回给模型的上下文条数（不含本次提问）
MAX_CONTEXT_MESSAGES = 40
TITLE_MAX_LEN = 24


def now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- 会话


def get_or_create_conversation(db: Session, conversation_id: str | None) -> Conversation:
    if conversation_id:
        conv = db.get(Conversation, conversation_id)
        if conv is None:
            conv = Conversation(id=conversation_id)
            db.add(conv)
            db.flush()
        return conv
    conv = Conversation(title="新的对话")
    db.add(conv)
    db.flush()
    return conv


def list_conversations(db: Session, limit: int = 50) -> list[dict]:
    rows = db.execute(
        select(Conversation).order_by(Conversation.updated_at.desc()).limit(limit)
    ).scalars().all()
    result = []
    for conv in rows:
        count = db.execute(
            select(func.count()).select_from(Message).where(Message.conversation_id == conv.id)
        ).scalar_one()
        data = conv.to_dict()
        data["message_count"] = count
        result.append(data)
    return result


def get_messages(db: Session, conversation_id: str, limit: int = 500) -> list[dict]:
    rows = db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
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
) -> Message:
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        status=status,
        model=model,
        error_code=error_code,
        latency_ms=latency_ms,
        created_at=now(),
    )
    db.add(msg)
    db.flush()
    return msg


def _build_context(
    db: Session, conversation_id: str, user_text: str, exclude_message_id: str | None = None
) -> list[LLMMessage]:
    """组装 [system] + 历史 + 本次提问。

    exclude_message_id 用于排除刚刚落库的这条用户消息，避免它被拼接两次。
    """
    settings = get_settings()
    stmt = select(Message).where(
        Message.conversation_id == conversation_id, Message.status == "ok"
    )
    if exclude_message_id:
        stmt = stmt.where(Message.id != exclude_message_id)
    history = db.execute(
        stmt.order_by(Message.created_at.desc(), Message.id.desc()).limit(MAX_CONTEXT_MESSAGES)
    ).scalars().all()
    history = list(reversed(history))
    return [
        LLMMessage(role="system", content=settings.system_prompt),
        *[LLMMessage(role=m.role, content=m.content) for m in history],
        LLMMessage(role="user", content=user_text),
    ]


def _maybe_update_title(db: Session, conv: Conversation, user_text: str) -> None:
    existing = db.execute(
        select(func.count()).select_from(Message).where(Message.conversation_id == conv.id)
    ).scalar_one()
    if existing > 1:
        return
    text = " ".join(user_text.split())
    conv.title = (text[:TITLE_MAX_LEN] + "…") if len(text) > TITLE_MAX_LEN else (text or "新的对话")
    conv.updated_at = now()


async def send_message(db: Session, conversation_id: str | None, user_text: str) -> dict:
    """落库用户消息 → 调真实模型 → 落库助手消息。失败时抛出 ProviderError。

    用户消息在任何情况下都会先 commit，保证 App 重启后历史不丢。
    """
    conv = get_or_create_conversation(db, conversation_id)

    _maybe_update_title(db, conv, user_text)
    user_msg = append_message(db, conv.id, "user", user_text)
    db.commit()

    provider = get_provider()
    if not provider.is_configured():
        # 绝不返回假回复：明确报错，让客户端提示去配置后端
        raise ProviderNotConfigured()

    context = _build_context(db, conv.id, user_text, exclude_message_id=user_msg.id)
    result: LLMResult = await provider.chat(context)

    assistant_msg = append_message(
        db,
        conv.id,
        "assistant",
        result.content,
        model=result.model,
        latency_ms=result.latency_ms,
    )
    conv.updated_at = now()
    db.commit()

    return {
        "conversation_id": conv.id,
        "user_message_id": user_msg.id,
        "assistant_message_id": assistant_msg.id,
        "reply": result.content,
        "model": result.model,
        "latency_ms": result.latency_ms,
    }
