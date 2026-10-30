"""人格（角色）接口。

v2.x：只保留一个人格——绘梨衣。她的设定来自 Windows 桌宠工程已有素材
（source='erii-pet'），不会被覆盖。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import personas
from app.database import get_db
from app.ratelimit import rate_limit
from app.schemas import CharacterDetail, CharacterOut
from app.security import verify_token

router = APIRouter(
    prefix="/api/v1/characters",
    tags=["characters"],
    dependencies=[Depends(verify_token), rate_limit("default")],
)


@router.get("", response_model=list[CharacterOut])
def list_all(db: Session = Depends(get_db)):
    """前台只返回绘梨衣一个人格；旧的多角色数据只在后端做兼容归档。"""
    erii = personas.get_character(db, key="erii")
    if erii is None:
        personas.seed_characters(db)
        db.commit()
        erii = personas.get_character(db, key="erii")
    return [erii.to_dict()] if erii else []


@router.get("/{key}", response_model=CharacterDetail)
def detail(key: str, db: Session = Depends(get_db)):
    character = personas.get_character(db, key=key)
    if character is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": f"未找到人格 {key}。", "hint": None},
        )
    return character.to_detail()


@router.get("/{key}/idle-lines")
def idle_lines(
    key: str,
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """角色待机台词。绘梨衣的台词来自桌宠已有素材（本项目原创短句）。

    返回体显式标注 `fictional=True`：这些是角色设定里的句子，不是任何人的真实经历。
    """
    character = personas.get_character(db, key=key)
    if character is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": f"未找到人格 {key}。", "hint": None},
        )
    lines = personas.idle_lines(key)
    return {
        "character_key": key,
        "character_name": character.name,
        "fictional": True,
        "notice": "待机台词来自角色设定与桌宠已有素材，属虚构内容。",
        "count": len(lines),
        "lines": lines[:limit],
    }
