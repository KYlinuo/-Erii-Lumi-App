"""虚构人生时间线。

所有返回内容 `simulated=True`：**这是角色设定里的虚构事件，不是用户真实经历**，
接口与 UI 都必须显式标注，禁止冒充真实记忆。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import personas, world as world_mod
from app.database import get_db
from app.ratelimit import rate_limit
from app.schemas import DiaryResponse, WorldEventOut
from app.security import verify_token

router = APIRouter(
    prefix="/api/v1/world",
    tags=["world"],
    dependencies=[Depends(verify_token), rate_limit("default")],
)


def _character_or_404(db: Session, character_key: str):
    character = personas.get_character(db, key=character_key)
    if character is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": f"未找到人格 {character_key}。", "hint": None},
        )
    return character


@router.get("/{character_key}/timeline", response_model=list[WorldEventOut])
def timeline(
    character_key: str,
    days: int = Query(default=7, ge=1, le=365),
    kind: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    character = _character_or_404(db, character_key)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    events = world_mod.timeline(
        db, character.id, since=since, kinds=[kind] if kind else None, limit=limit
    )
    return [e.to_dict() for e in events]


@router.get("/{character_key}/diary", response_model=DiaryResponse)
def diary(
    character_key: str,
    limit: int = Query(default=30, ge=1, le=200),
    db: Session = Depends(get_db),
):
    character = _character_or_404(db, character_key)
    events = world_mod.timeline(db, character.id, limit=limit)
    return DiaryResponse(
        character_key=character.key,
        character_name=character.name,
        notice="以下为角色虚构生活中的内容，不是真实经历，也不代表 AI 的真实记忆。",
        events=[WorldEventOut(**e.to_dict()) for e in events],
    )


@router.post("/{character_key}/simulate", response_model=list[WorldEventOut])
def simulate(
    character_key: str,
    max_events: int = Query(default=3, ge=1, le=10),
    date: str | None = Query(default=None, description="YYYY-MM-DD，缺省为今天（UTC）"),
    db: Session = Depends(get_db),
):
    """为角色生成某一天的虚构生活。确定性 + 幂等，同一天不会重复写入。"""
    character = _character_or_404(db, character_key)

    target = None
    if date:
        try:
            target = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "invalid_date",
                    "message": "日期格式应为 YYYY-MM-DD。",
                    "hint": str(exc),
                },
            ) from exc

    events = world_mod.simulate_day(db, character, target, max_events=max_events)
    db.commit()
    return [e.to_dict() for e in events]


@router.get("/{character_key}/state")
def state(character_key: str, db: Session = Depends(get_db)):
    """虚构世界概览：事件数、按类型分布、最近进展。"""
    character = _character_or_404(db, character_key)
    events = world_mod.timeline(db, character.id, limit=200)
    by_kind: dict[str, int] = {}
    for event in events:
        by_kind[event.kind] = by_kind.get(event.kind, 0) + 1
    return {
        "character_key": character.key,
        "character_name": character.name,
        "simulated": True,
        "event_count": len(events),
        "by_kind": by_kind,
        "latest": events[0].to_dict() if events else None,
    }
