"""会话与历史消息 —— 支持 App 冷启动后恢复聊天记录。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.ratelimit import rate_limit
from app.schemas import ConversationOut, MessageOut
from app.security import Caller, verify_token
from app.services import (
    delete_conversation,
    get_messages,
    get_or_create_conversation,
    list_conversations,
    search_messages,
)

logger = logging.getLogger("lumi.conversations")
router = APIRouter(
    prefix="/api/v1/conversations",
    tags=["conversations"],
    dependencies=[Depends(verify_token), rate_limit("default")],
)


class CreateConversationResponse(BaseModel):
    id: str
    title: str
    character_id: str | None = None


@router.get("", response_model=list[ConversationOut])
def list_all(
    db: Session = Depends(get_db),
    caller: Caller = Depends(verify_token),
    character_key: str | None = None,
) -> list[dict]:
    return list_conversations(db)


@router.post("", response_model=CreateConversationResponse, status_code=status.HTTP_201_CREATED)
def create(
    conversation_id: str | None = None,
    character_key: str | None = None,
    db: Session = Depends(get_db),
    caller: Caller = Depends(verify_token),
) -> dict:
    conv = get_or_create_conversation(
        db,
        conversation_id,
        user_id=caller.user_id,
        character_key=character_key,
        device_id=caller.device_id,
    )
    db.commit()
    return {"id": conv.id, "title": conv.title, "character_id": conv.character_id}


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
def history(
    conversation_id: str,
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> list[dict]:
    return get_messages(db, conversation_id, limit=limit)


@router.get("/{conversation_id}/search", response_model=list[MessageOut])
def search(
    conversation_id: str,
    query: str = Query(min_length=1, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[dict]:
    """在当前会话内按关键词搜索历史消息。"""
    return search_messages(db, conversation_id, query.strip(), limit=limit)


@router.get("/{conversation_id}/messages/starred", response_model=list[MessageOut])
def starred_messages(
    conversation_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict]:
    """收藏的消息列表（按收藏时间倒序，这里退化为按创建时间倒序）。"""
    from app.models import Message

    rows = db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.starred.is_(True))
        .order_by(Message.created_at.desc())
        .limit(limit)
    ).scalars().all()
    return [m.to_dict() for m in rows]


@router.post("/{conversation_id}/messages/{message_id}/star", response_model=MessageOut)
def star_message(
    conversation_id: str,
    message_id: str,
    starred: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> dict:
    """收藏 / 取消收藏一条消息。"""
    from app.models import Message

    row = db.get(Message, message_id)
    if row is None or row.conversation_id != conversation_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "消息不存在。", "hint": None},
        )
    row.starred = starred
    db.commit()
    return row.to_dict()


@router.patch("/{conversation_id}/character", response_model=CreateConversationResponse)
def switch_character(
    conversation_id: str,
    character_key: str,
    db: Session = Depends(get_db),
    caller: Caller = Depends(verify_token),
) -> dict:
    """切换会话所属人格（不合并人格，只是换一个角色继续聊）。"""
    from app import personas

    character = personas.get_character(db, key=character_key)
    if character is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": f"未找到人格 {character_key}。", "hint": None},
        )
    conv = get_or_create_conversation(
        db, conversation_id, user_id=caller.user_id, character_key=character_key
    )
    conv.character_id = character.id
    db.commit()
    return {"id": conv.id, "title": conv.title, "character_id": conv.character_id}


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove(conversation_id: str, db: Session = Depends(get_db)) -> None:
    if not delete_conversation(db, conversation_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "会话不存在。", "hint": None},
        )
    db.commit()
