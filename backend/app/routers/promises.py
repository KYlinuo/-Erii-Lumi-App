"""约定 / 待续话题（需求 20）。

区分「随口一说」与「明确约定」，支持 完成 / 推迟 / 取消 / 归档。
有歧义的日期先标记 vague，由用户确认后再设 due_at。
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Promise
from app.ratelimit import rate_limit
from app.security import verify_token

router = APIRouter(
    prefix="/api/v1/promises",
    tags=["promises"],
    dependencies=[Depends(verify_token), rate_limit("default")],
)

_VALID_STATUS = ("pending", "done", "postponed", "cancelled", "archived")
_VALID_CERTAINTY = ("vague", "confirmed")


class PromiseCreate(BaseModel):
    content: str
    due_at: str | None = None
    certainty: str = "vague"
    note: str = ""


class PromiseUpdate(BaseModel):
    content: str | None = None
    due_at: str | None = None
    certainty: str | None = None
    status: str | None = None
    note: str | None = None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


@router.get("", response_model=list[dict])
def list_promises(
    status_filter: str | None = Query(default=None, alias="status"),
    certainty: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    stmt = select(Promise).order_by(Promise.updated_at.desc())
    if status_filter:
        stmt = stmt.where(Promise.status == status_filter)
    if certainty:
        stmt = stmt.where(Promise.certainty == certainty)
    rows = db.execute(stmt.limit(limit)).scalars().all()
    return [r.to_dict() for r in rows]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=dict)
def create_promise(payload: PromiseCreate, db: Session = Depends(get_db)):
    content = (payload.content or "").strip()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "empty_content", "message": "约定内容不能为空。", "hint": None},
        )
    certainty = payload.certainty if payload.certainty in _VALID_CERTAINTY else "vague"
    row = Promise(
        content=content,
        due_at=_parse_dt(payload.due_at),
        certainty=certainty,
        note=(payload.note or "").strip(),
        status="pending",
    )
    db.add(row)
    db.commit()
    return row.to_dict()


@router.patch("/{promise_id}", response_model=dict)
def update_promise(promise_id: str, payload: PromiseUpdate, db: Session = Depends(get_db)):
    row = db.get(Promise, promise_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "约定不存在。", "hint": None},
        )
    if payload.content is not None:
        content = payload.content.strip()
        if not content:
            raise HTTPException(status_code=422, detail={"code": "empty_content", "message": "内容不能为空。", "hint": None})
        row.content = content
    if payload.due_at is not None:
        row.due_at = _parse_dt(payload.due_at)
    if payload.certainty is not None and payload.certainty in _VALID_CERTAINTY:
        row.certainty = payload.certainty
    if payload.status is not None:
        if payload.status not in _VALID_STATUS:
            raise HTTPException(status_code=422, detail={"code": "bad_status", "message": "状态无效。", "hint": None})
        row.status = payload.status
    if payload.note is not None:
        row.note = payload.note.strip()
    db.commit()
    return row.to_dict()


@router.delete("/{promise_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_promise(promise_id: str, db: Session = Depends(get_db)):
    row = db.get(Promise, promise_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "约定不存在。", "hint": None},
        )
    db.delete(row)
    db.commit()
