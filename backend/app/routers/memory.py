"""长期记忆接口。

隔离规则在 `app/memory.py` 里实现并由测试覆盖：
- `subject='user'` 的真实用户信息跨人格共享（character_id 为 NULL）；
- `subject='relationship' / 'character'` 按 character_id 严格隔离，
  因此 A 人格的虚构人生不会出现在 B 人格的记忆里，也不会污染用户事实。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import memory as memory_mod
from app.database import get_db
from app.models import MemoryRecord
from app.ratelimit import rate_limit
from app.schemas import MemoryCreate, MemoryOut, MemoryUpdate
from app.security import verify_token

router = APIRouter(
    prefix="/api/v1/memory",
    tags=["memory"],
    dependencies=[Depends(verify_token), rate_limit("default")],
)


def _resolve_character(db: Session, character_key: str | None) -> str | None:
    from app import personas

    if not character_key:
        return None
    character = personas.get_character(db, key=character_key)
    if character is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": f"未找到人格 {character_key}。", "hint": None},
        )
    return character.id


@router.get("", response_model=list[MemoryOut])
def list_all(
    character_key: Annotated[str | None, Query()] = None,
    scope: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    include_shared: bool = True,
    query: Annotated[str | None, Query()] = None,
    db: Session = Depends(get_db),
):
    character_id = _resolve_character(db, character_key)
    rows = memory_mod.query_memories(
        db,
        character_id=character_id,
        scopes=[scope] if scope else None,
        limit=limit,
        include_shared=include_shared,
        query=query,
    )
    return [r.to_dict() for r in rows]


@router.get("/summary")
def summary(character_key: str | None = None, db: Session = Depends(get_db)):
    character_id = _resolve_character(db, character_key)
    counts = memory_mod.count_by_scope(db, character_id)
    return {
        "character_key": character_key,
        "character_id": character_id,
        "by_scope": counts,
        "total": sum(counts.values()),
    }


@router.get("/export")
def export(character_key: str | None = None, db: Session = Depends(get_db)):
    """导出全部记忆（含来源与可信度），供用户自行备份。"""
    character_id = _resolve_character(db, character_key)
    return {
        "version": 1,
        "character_key": character_key,
        "count": memory_mod.total_count(db),
        "records": memory_mod.export_memories(db, character_id=character_id),
    }


@router.post("", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
def create(payload: MemoryCreate, db: Session = Depends(get_db)):
    """用户显式写入一条记忆（source_type 可指定；默认 user_explicit）。"""
    if payload.scope not in memory_mod.SCOPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_scope",
                "message": f"scope 必须是：{', '.join(memory_mod.SCOPES)}",
                "hint": None,
            },
        )
    try:
        row = memory_mod.record(
            db,
            scope=payload.scope,
            content=payload.content,
            character_id=payload.character_id,
            source_type=payload.source_type,
            source_ref=payload.source_ref,
            confidence=payload.confidence,
            salience=payload.salience,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_scope", "message": str(exc), "hint": None},
        ) from exc
    db.commit()
    return row.to_dict()


@router.patch("/{memory_id}", response_model=MemoryOut)
def update(memory_id: str, payload: MemoryUpdate, db: Session = Depends(get_db)):
    row = db.get(MemoryRecord, memory_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "记忆不存在。", "hint": None},
        )
    if payload.content is not None:
        row.content = payload.content
    if payload.confidence is not None:
        row.confidence = payload.confidence
    if payload.salience is not None:
        row.salience = payload.salience
    if payload.status is not None:
        row.status = payload.status
    db.commit()
    return row.to_dict()


@router.post("/{memory_id}/archive", response_model=MemoryOut)
def archive(memory_id: str, db: Session = Depends(get_db)):
    if not memory_mod.archive_memory(db, memory_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "记忆不存在。", "hint": None},
        )
    db.commit()
    return db.get(MemoryRecord, memory_id).to_dict()


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(memory_id: str, db: Session = Depends(get_db)):
    if not memory_mod.delete_memory(db, memory_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "记忆不存在。", "hint": None},
        )
    db.commit()
