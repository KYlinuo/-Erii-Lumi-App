"""服务器主动联系（pull 模式）。

**不声称实现了 APNs 远程推送**：免费 Apple ID 自签条件下 iOS 无法被可靠远程唤醒。
本实现的语义是「服务端排好队 → 客户端下次联网时补拉」，
因此 App 未打开时消息也不会丢，但要等 App 自己来取。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import proactive
from app.database import get_db
from app.ratelimit import rate_limit
from app.schemas import ProactiveOut
from app.security import verify_token

logger = logging.getLogger("lumi.proactive_router")
router = APIRouter(
    prefix="/api/v1/proactive",
    tags=["proactive"],
    dependencies=[Depends(verify_token), rate_limit("default")],
)


class DeliverRequest(BaseModel):
    ids: list[str] = Field(default_factory=list)


@router.get("", response_model=list[ProactiveOut])
def pending(
    limit: int = Query(default=20, ge=1, le=100),
    character_key: str | None = None,
    db: Session = Depends(get_db),
):
    """拉取待投递的主动消息。客户端拿到后应调用 /delivered 确认。"""
    from app import personas

    character_id = None
    if character_key:
        character = personas.get_character(db, key=character_key)
        character_id = character.id if character else None
    rows = proactive.pending(db, limit=limit, character_id=character_id)
    return [r.to_dict() for r in rows]


@router.post("/delivered", status_code=status.HTTP_200_OK)
def delivered(payload: DeliverRequest, db: Session = Depends(get_db)):
    count = proactive.deliver(db, payload.ids)
    return {"delivered": count}


@router.post("/plan")
def plan(character_key: str | None = None, db: Session = Depends(get_db)):
    """按当前时段/配额判断是否需要排一条主动消息；不合适就不排。"""
    row = proactive.plan_next(db, character_key=character_key)
    if row is None:
        allowed, why = proactive.allowed_now()
        return {"planned": False, "reason": why, "allowed": allowed}
    return {"planned": True, "reason": "ok", "message": row}


@router.post("/cancel", status_code=status.HTTP_200_OK)
def cancel(db: Session = Depends(get_db)):
    """即时关闭：撤销所有尚未投递的主动消息。"""
    count = proactive.cancel_all(db)
    return {"cancelled": count}


@router.get("/status")
def status_view():
    """当前调度策略与是否允许发送。"""
    from app.config import get_settings

    settings = get_settings()
    allowed, why = proactive.allowed_now()
    return {
        "enabled": settings.proactive_enabled,
        "allowed_now": allowed,
        "reason": why,
        "daily_cap": settings.proactive_daily_cap,
        "windows": settings.proactive_windows,
        "quiet_hours": settings.quiet_hours,
        "min_interval_minutes": settings.proactive_min_interval_minutes,
        "timezone": settings.timezone,
        "apns_remote_push": False,
        "note": "采用「服务端排队 + 客户端拉取」模式，未实现也不声称实现了 APNs 远程推送。",
    }
