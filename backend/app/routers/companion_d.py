"""阶段 D 路由（需求 13–18 / 21–22）：设定卡、演绎模式、熟悉度、手写便签、
专属表情动作、共同回忆时间线、长期话题档案、日程变更。

全部接口都需要设备令牌与限流；状态写入都持久化，重启后不丢失。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import companion as companion_mod
from app import expression_pack
from app import persona_card
from app.database import get_db
from app.ratelimit import rate_limit
from app.security import verify_token

router = APIRouter(
    prefix="/api/v1",
    tags=["companion-d"],
    dependencies=[Depends(verify_token), rate_limit("default")],
)


def _bad(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": "bad_request", "message": message, "hint": None},
    )


# ---------------------------------------------------------------- 13 设定卡


@router.get("/persona-card")
def get_persona_card():
    """绘梨衣设定卡：三层来源分离 + EPUB 来源状态（未找到如实标注）。"""
    return persona_card.build_card()


# ---------------------------------------------------------------- 14 演绎模式


@router.get("/persona-mode")
def get_persona_mode(db: Session = Depends(get_db)):
    return companion_mod.get_mode(db)


@router.post("/persona-mode")
def set_persona_mode(payload: dict, db: Session = Depends(get_db)):
    mode = str(payload.get("mode") or "")
    if mode not in ("canon", "parallel", "pet"):
        raise _bad("mode 必须是 canon / parallel / pet。")
    scope = payload.get("spoiler_scope")
    return companion_mod.set_mode(db, mode, str(scope) if scope else None)


# ---------------------------------------------------------------- 17 熟悉程度


@router.get("/intimacy")
def get_intimacy(reveal: bool = Query(default=False), db: Session = Depends(get_db)):
    return companion_mod.get_intimacy(db, reveal=reveal)


@router.post("/intimacy/experience")
def record_experience(payload: dict, db: Session = Depends(get_db)):
    return companion_mod.record_experience(db, str(payload.get("reason") or ""))


@router.post("/intimacy/pause")
def pause_intimacy(payload: dict, db: Session = Depends(get_db)):
    return companion_mod.set_intimacy_paused(db, bool(payload.get("paused", True)))


@router.post("/intimacy/reset")
def reset_intimacy(db: Session = Depends(get_db)):
    return companion_mod.reset_intimacy(db)


# ---------------------------------------------------------------- 15 手写便签


@router.get("/notes/settings")
def get_note_settings(db: Session = Depends(get_db)):
    return companion_mod.note_settings(db)


@router.post("/notes/settings")
def set_note_settings(payload: dict, db: Session = Depends(get_db)):
    freq = str(payload.get("frequency") or "")
    if freq not in ("off", "low", "medium", "high"):
        raise _bad("frequency 必须是 off / low / medium / high。")
    return companion_mod.set_note_settings(db, freq)


@router.get("/notes")
def list_notes(starred: bool = Query(default=False), db: Session = Depends(get_db)):
    return companion_mod.list_notes(db, starred_only=starred)


@router.post("/notes", status_code=status.HTTP_201_CREATED)
def create_note(payload: dict, db: Session = Depends(get_db)):
    content = str(payload.get("content") or "").strip()
    if not content:
        raise _bad("便签内容不能为空。")
    return companion_mod.add_note(
        db,
        content,
        source_message_id=payload.get("source_message_id"),
        source_conversation_id=payload.get("source_conversation_id"),
    )


@router.patch("/notes/{note_id}")
def star_note(note_id: str, payload: dict, db: Session = Depends(get_db)):
    result = companion_mod.star_note(db, note_id, bool(payload.get("starred", True)))
    if result is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "便签不存在。", "hint": None}
        )
    return result


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(note_id: str, db: Session = Depends(get_db)):
    if not companion_mod.delete_note(db, note_id):
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "便签不存在。", "hint": None}
        )


# ---------------------------------------------------------------- 18 专属表情动作


@router.get("/expressions")
def get_expressions(db: Session = Depends(get_db)):
    return expression_pack.all_packs(db)


@router.post("/expressions/frequency")
def set_expression_frequency(payload: dict, db: Session = Depends(get_db)):
    value = str(payload.get("frequency") or "")
    if value not in ("low", "medium", "high"):
        raise _bad("frequency 必须是 low / medium / high。")
    return {"frequency": expression_pack.set_frequency(db, value)}


@router.post("/expressions/import", status_code=status.HTTP_201_CREATED)
def import_expression(payload: dict, db: Session = Depends(get_db)):
    result = expression_pack.import_pack(db, payload)
    if not result.get("imported"):
        raise _bad("导入失败：text 不能为空。")
    return result


# ---------------------------------------------------------------- 21 共同回忆时间线


@router.get("/timeline")
def list_timeline(
    include_unverified: bool = Query(default=False), db: Session = Depends(get_db)
):
    return companion_mod.list_timeline(db, include_unverified=include_unverified)


@router.post("/timeline/sync")
def sync_timeline(db: Session = Depends(get_db)):
    """从首聊 / 约定 / 收藏 / 照片生成已证实回忆；虚构事件只作未证实候选。"""
    from app import personas

    character = personas.resolve_character(db)
    return companion_mod.sync_from_sources(db, character_id=character.id)


@router.post("/timeline", status_code=status.HTTP_201_CREATED)
def create_timeline(payload: dict, db: Session = Depends(get_db)):
    content = str(payload.get("content") or "").strip()
    if not content:
        raise _bad("回忆内容不能为空。")
    return companion_mod.add_timeline(
        db,
        kind=str(payload.get("kind") or "manual"),
        title=str(payload.get("title") or "一条回忆"),
        content=content,
        source_message_id=payload.get("source_message_id"),
        source_ref=str(payload.get("source_ref") or ""),
        verified=bool(payload.get("verified", False)),
    )


@router.post("/timeline/{event_id}/verify")
def verify_timeline(event_id: str, db: Session = Depends(get_db)):
    result = companion_mod.verify_timeline(db, event_id)
    if result is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "回忆不存在。", "hint": None}
        )
    return result


@router.patch("/timeline/{event_id}")
def update_timeline(event_id: str, payload: dict, db: Session = Depends(get_db)):
    result = companion_mod.update_timeline(db, event_id, payload)
    if result is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "回忆不存在。", "hint": None}
        )
    return result


@router.delete("/timeline/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_timeline(event_id: str, db: Session = Depends(get_db)):
    if not companion_mod.delete_timeline(db, event_id):
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "回忆不存在。", "hint": None}
        )


# ---------------------------------------------------------------- 22 长期话题档案


@router.get("/topics")
def list_topics(db: Session = Depends(get_db)):
    return companion_mod.list_topics(db)


@router.get("/topics/relevant")
def relevant_topics(query: str = Query(default=""), db: Session = Depends(get_db)):
    return companion_mod.relevant_topics(db, query)


@router.post("/topics", status_code=status.HTTP_201_CREATED)
def create_topic(payload: dict, db: Session = Depends(get_db)):
    title = str(payload.get("title") or "").strip()
    if not title:
        raise _bad("话题标题不能为空。")
    return companion_mod.create_topic(db, {**payload, "title": title})


@router.post("/topics/active")
def set_active_topic(payload: dict, db: Session = Depends(get_db)):
    topic_id = payload.get("topic_id")
    return companion_mod.set_active_topic(db, str(topic_id) if topic_id else None)


@router.patch("/topics/{topic_id}")
def update_topic(topic_id: str, payload: dict, db: Session = Depends(get_db)):
    result = companion_mod.update_topic(db, topic_id, payload)
    if result is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "话题不存在。", "hint": None}
        )
    return result


@router.delete("/topics/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_topic(topic_id: str, db: Session = Depends(get_db)):
    if not companion_mod.delete_topic(db, topic_id):
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "话题不存在。", "hint": None}
        )


# ---------------------------------------------------------------- 16 日程变更


@router.get("/schedule")
def list_schedule(day: str | None = Query(default=None), db: Session = Depends(get_db)):
    from app import companion, personas

    character = personas.resolve_character(db)
    return companion.list_schedule(db, character.id, day=day)


@router.post("/schedule", status_code=status.HTTP_201_CREATED)
def record_schedule(payload: dict, db: Session = Depends(get_db)):
    from app import companion, personas

    content = str(payload.get("content") or "").strip()
    day = str(payload.get("day") or "").strip()
    if not content or not day:
        raise _bad("day 与 content 都不能为空（day 用 YYYY-MM-DD）。")
    character = personas.resolve_character(db)
    return companion.record_schedule_change(db, character.id, day, content)
