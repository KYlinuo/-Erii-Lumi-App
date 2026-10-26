"""会话与历史消息 —— 支持 App 冷启动后恢复聊天记录。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.ratelimit import rate_limit
from app.schemas import ConversationOut, MessageOut
from app.security import verify_token
from app.services import (
    delete_conversation,
    get_messages,
    get_or_create_conversation,
    list_conversations,
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


@router.get("", response_model=list[ConversationOut])
def list_all(db: Session = Depends(get_db)) -> list[dict]:
    return list_conversations(db)


@router.post("", response_model=CreateConversationResponse, status_code=status.HTTP_201_CREATED)
def create(conversation_id: str | None = None, db: Session = Depends(get_db)) -> dict:
    conv = get_or_create_conversation(db, conversation_id)
    db.commit()
    return {"id": conv.id, "title": conv.title}


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
def history(
    conversation_id: str,
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> list[dict]:
    return get_messages(db, conversation_id, limit=limit)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove(conversation_id: str, db: Session = Depends(get_db)) -> None:
    if not delete_conversation(db, conversation_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "会话不存在。", "hint": None},
        )
    db.commit()
