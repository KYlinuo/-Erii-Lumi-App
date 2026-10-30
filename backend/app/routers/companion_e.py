"""阶段 E 路由（需求 23–30）+ 阶段 G 桌宠协议契约（35）。

备份恢复用 POST /backup/preview + /backup/apply 两步：先预览冲突与完整性，
再由用户选择 skip/overwrite 应用，重复恢复不会产生重复记录。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import activities as A
from app.database import get_db
from app.ratelimit import rate_limit
from app.security import verify_token

router = APIRouter(
    prefix="/api/v1",
    tags=["companion-e"],
    dependencies=[Depends(verify_token), rate_limit("default")],
)


def _bad(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": "bad_request", "message": message, "hint": None},
    )


# ---------------------------------------------------------------- 23 临时聊天


@router.get("/ephemeral")
def list_ephemeral(db: Session = Depends(get_db)):
    return A.list_ephemeral(db)


@router.get("/ephemeral/policy")
def get_ephemeral_policy(db: Session = Depends(get_db)):
    return A.ephemeral_policy(db)


@router.post("/ephemeral/policy")
def set_ephemeral_policy(payload: dict, db: Session = Depends(get_db)):
    return A.set_ephemeral_policy(db, str(payload.get("on_exit") or ""))


@router.post("/ephemeral/exit")
def exit_ephemeral(db: Session = Depends(get_db)):
    return A.apply_exit_policy(db)


@router.delete("/ephemeral/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ephemeral(conversation_id: str, db: Session = Depends(get_db)):
    if not A.delete_ephemeral(db, conversation_id):
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "临时会话不存在。", "hint": None}
        )


# ---------------------------------------------------------------- 24 备份 / 恢复


@router.get("/backup/export")
def export_backup(db: Session = Depends(get_db)):
    """明文导出（含 SHA-256 完整性校验）；加密请用 POST /backup/export。"""
    return A.build_backup(db)


@router.post("/backup/export")
def export_backup_encrypted(payload: dict, db: Session = Depends(get_db)):
    key = payload.get("encrypt_key")
    try:
        return A.build_backup(db, encrypt_key=str(key) if key else None)
    except ValueError as exc:
        raise _bad(str(exc))


@router.post("/backup/preview")
def preview_backup(payload: dict, db: Session = Depends(get_db)):
    backup = payload.get("backup")
    if not isinstance(backup, dict):
        raise _bad("缺少 backup 载荷。")
    try:
        return A.preview_backup(db, backup, payload.get("encrypt_key"))
    except A.BackupError as exc:
        raise _bad(str(exc))


@router.post("/backup/apply")
def apply_backup(payload: dict, db: Session = Depends(get_db)):
    backup = payload.get("backup")
    if not isinstance(backup, dict):
        raise _bad("缺少 backup 载荷。")
    try:
        return A.apply_backup(
            db,
            backup,
            strategy=str(payload.get("strategy") or "skip"),
            encrypt_key=payload.get("encrypt_key"),
        )
    except A.BackupError as exc:
        raise _bad(str(exc))


# ---------------------------------------------------------------- 25 主动联系


@router.get("/proactive/settings")
def get_proactive_settings(db: Session = Depends(get_db)):
    return A.proactive_settings(db)


@router.post("/proactive/settings")
def set_proactive_settings(payload: dict, db: Session = Depends(get_db)):
    return A.set_proactive_settings(db, payload)


@router.get("/proactive/capability")
def proactive_capability():
    return A.proactive_capability()


@router.post("/proactive/expire")
def expire_proactive(hours: int = Query(default=24, ge=1, le=168), db: Session = Depends(get_db)):
    return {"expired": A.expire_stale_proactive(db, hours=hours)}


# ---------------------------------------------------------------- 26 学习陪伴


@router.post("/study/start", status_code=status.HTTP_201_CREATED)
def study_start(payload: dict, db: Session = Depends(get_db)):
    return A.study_start(db, str(payload.get("subject") or "自习"))


@router.get("/study/{session_id}")
def study_get(session_id: str, db: Session = Depends(get_db)):
    result = A.study_get(db, session_id)
    if result is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "计时不存在。", "hint": None}
        )
    return result


@router.post("/study/{session_id}/pause")
def study_pause(session_id: str, db: Session = Depends(get_db)):
    return A.study_pause(db, session_id)


@router.post("/study/{session_id}/resume")
def study_resume(session_id: str, db: Session = Depends(get_db)):
    return A.study_resume(db, session_id)


@router.post("/study/{session_id}/end")
def study_end(session_id: str, payload: dict, db: Session = Depends(get_db)):
    result = A.study_end(db, session_id, str(payload.get("note") or ""))
    if result is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "计时不存在。", "hint": None}
        )
    return result


# ---------------------------------------------------------------- 27 一起读书


@router.get("/reading")
def reading_list(db: Session = Depends(get_db)):
    return A.reading_list(db)


@router.post("/reading", status_code=status.HTTP_201_CREATED)
def reading_upsert(payload: dict, db: Session = Depends(get_db)):
    try:
        return A.reading_upsert(db, payload)
    except ValueError as exc:
        raise _bad(str(exc))


@router.post("/reading/delete")
def reading_delete(payload: dict, db: Session = Depends(get_db)):
    book = str(payload.get("book") or "")
    if not A.reading_delete(db, book):
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "书籍不存在。", "hint": None}
        )
    return {"deleted": True, "book": book}


# ---------------------------------------------------------------- 28 共同小活动


@router.get("/activities")
def activity_list(db: Session = Depends(get_db)):
    return A.activity_list(db)


@router.post("/activities/start", status_code=status.HTTP_201_CREATED)
def activity_start(payload: dict, db: Session = Depends(get_db)):
    try:
        return A.activity_start(db, str(payload.get("kind") or ""))
    except ValueError as exc:
        raise _bad(str(exc))


@router.get("/activities/{session_id}")
def activity_get(session_id: str, db: Session = Depends(get_db)):
    result = A.activity_get(db, session_id)
    if result is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "活动不存在。", "hint": None}
        )
    return result


@router.post("/activities/{session_id}/step")
def activity_step(session_id: str, payload: dict, db: Session = Depends(get_db)):
    result = A.activity_step(db, session_id, str(payload.get("answer") or ""))
    if result is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "活动不存在。", "hint": None}
        )
    return result


@router.post("/activities/{session_id}/finish")
def activity_finish(session_id: str, payload: dict, db: Session = Depends(get_db)):
    result = A.activity_finish(db, session_id, str(payload.get("status") or "done"))
    if result is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "活动不存在。", "hint": None}
        )
    return result


# ---------------------------------------------------------------- 29 日记与留言


@router.get("/diary/day")
def diary_day(day: str = Query(default=""), db: Session = Depends(get_db)):
    return A.diary_day(db, day)


@router.post("/diary/regenerate")
def regenerate_diary(payload: dict, db: Session = Depends(get_db)):
    day = str(payload.get("day") or "")
    if not day:
        raise _bad("day 不能为空（YYYY-MM-DD）。")
    return A.regenerate_diary(db, day)


@router.get("/diary-notes")
def diary_notes(day: str | None = Query(default=None), db: Session = Depends(get_db)):
    return A.diary_notes(db, day)


@router.post("/diary-notes", status_code=status.HTTP_201_CREATED)
def add_diary_note(payload: dict, db: Session = Depends(get_db)):
    try:
        return A.add_diary_note(db, payload)
    except ValueError as exc:
        raise _bad(str(exc))


@router.patch("/diary-notes/{note_id}")
def update_diary_note(note_id: str, payload: dict, db: Session = Depends(get_db)):
    content = str(payload.get("content") or "").strip()
    if not content:
        raise _bad("留言内容不能为空。")
    result = A.update_diary_note(db, note_id, content)
    if result is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "留言不存在。", "hint": None}
        )
    return result


@router.delete("/diary-notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_diary_note(note_id: str, db: Session = Depends(get_db)):
    if not A.delete_diary_note(db, note_id):
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "留言不存在。", "hint": None}
        )


# ---------------------------------------------------------------- 30 小组件


@router.get("/widget/summary")
def widget_summary(privacy: bool = Query(default=False), db: Session = Depends(get_db)):
    return A.widget_summary(db, privacy=privacy)


# ---------------------------------------------------------------- 35 桌宠协议契约


@router.get("/bridge/contract")
def bridge_contract():
    return A.bridge_contract()
