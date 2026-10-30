"""跨设备增量同步。

权威数据在服务端：Windows 桌宠与 iPhone 都通过这里读写同一份
会话 / 消息 / 记忆 / 虚构人生时间线。

同步模型：
- 每个消息在会话内有单调递增的 `conv_seq`；
- 客户端保存每个会话读到过的 `conv_seq`，下次带 `since` 只拉增量；
- 消息带 `request_id`，重复提交（断线重发）不会产生第二条；
- 删除是软删除（tombstone），删除动作也能同步到另一端。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DeviceCursor, Message
from app.ratelimit import rate_limit
from app.schemas import CursorUpdate, MessageSyncOut, SyncRequest, SyncResponse
from app.security import Caller, verify_token

router = APIRouter(
    prefix="/api/v1/sync",
    tags=["sync"],
    dependencies=[Depends(verify_token), rate_limit("default")],
)


@router.post("", response_model=SyncResponse)
def sync_all(payload: SyncRequest, db: Session = Depends(get_db)):
    """一次拉全部会话的增量。App 冷启动 / 下拉刷新都用它。"""
    from app.services import sync_all as _sync_all

    data = _sync_all(db, since_map=payload.since, limit=payload.limit)
    return data


@router.get("/conversation/{conversation_id}", response_model=list[MessageSyncOut])
def sync_conversation(
    conversation_id: str,
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    from app.services import sync_messages

    messages, _cursor, _updated = sync_messages(db, conversation_id, after=after, limit=limit)
    return messages


class CursorResponse(BaseModel):
    device_id: str | None
    conversation_id: str
    last_seq: int


@router.put("/cursor", response_model=CursorResponse)
def update_cursor(payload: CursorUpdate, caller: Caller = Depends(verify_token), db: Session = Depends(get_db)):
    """记录本设备读到哪一条了（用于未读提示与恢复续传）。"""
    if not caller.device_id:
        return CursorResponse(
            device_id=None, conversation_id=payload.conversation_id, last_seq=payload.last_seq
        )
    row = db.get(DeviceCursor, (caller.device_id, payload.conversation_id))
    if row is None:
        row = DeviceCursor(
            device_id=caller.device_id,
            conversation_id=payload.conversation_id,
            last_seq=payload.last_seq,
        )
        db.add(row)
    else:
        row.last_seq = max(row.last_seq, payload.last_seq)
    db.commit()
    return CursorResponse(
        device_id=caller.device_id,
        conversation_id=payload.conversation_id,
        last_seq=row.last_seq,
    )


@router.get("/cursor/{conversation_id}", response_model=CursorResponse)
def read_cursor(conversation_id: str, caller: Caller = Depends(verify_token), db: Session = Depends(get_db)):
    row = (
        db.get(DeviceCursor, (caller.device_id, conversation_id)) if caller.device_id else None
    )
    return CursorResponse(
        device_id=caller.device_id,
        conversation_id=conversation_id,
        last_seq=row.last_seq if row else 0,
    )


@router.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def soft_delete(message_id: str, db: Session = Depends(get_db)):
    """软删除：保留 tombstone 让另一端也能同步删除动作。"""
    from datetime import datetime, timezone

    msg = db.get(Message, message_id)
    if msg is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "消息不存在。", "hint": None},
        )
    if msg.deleted_at is None:
        from app.services import next_conv_seq
        msg.conv_seq = next_conv_seq(db, msg.conversation_id)
        msg.deleted_at = datetime.now(timezone.utc)
        db.commit()
