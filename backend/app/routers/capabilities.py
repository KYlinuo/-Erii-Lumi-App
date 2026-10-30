"""阶段 F/G 路由：能力状态、费用明细、立绘交互、隐私与语音设置。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import capabilities as cap
from app.database import get_db
from app.ratelimit import rate_limit
from app.security import verify_token

router = APIRouter(
    prefix="/api/v1",
    tags=["capabilities"],
    dependencies=[Depends(verify_token), rate_limit("default")],
)


@router.get("/capabilities")
def get_capabilities():
    """31/32/33/34/35/36 与 APNs / 液态玻璃的真实状态（不伪装占位为完成）。"""
    return cap.all_capabilities()


@router.get("/capabilities/image")
def image_state(
    size: int = Query(default=1024, ge=0),
    mime: str = Query(default="image/jpeg"),
    has_caption: bool = Query(default=False),
):
    """需求 31：明确区分上传成功 / 解析失败 / 模型不支持 / 识别不确定。"""
    return cap.image_pipeline_state(b"x" * min(size, 9 * 1024 * 1024), mime, has_caption=has_caption)


@router.get("/usage/detail")
def usage_detail(days: int = Query(default=7, ge=1, le=30), db: Session = Depends(get_db)):
    """需求 36：实际用量 + 可配置估价 + 渠道拆分 + 预算覆盖说明。"""
    return cap.usage_detail(db, days=days)


@router.get("/avatar/interaction")
def avatar_interaction(
    part: str = Query(default="head"),
    reduce_motion: bool = Query(default=False),
):
    """需求 34：点击不同部位不同反馈，支持低功耗/静态模式。"""
    return cap.avatar_interaction(part, reduce_motion=reduce_motion)


@router.get("/settings/privacy")
def get_privacy_settings(db: Session = Depends(get_db)):
    return cap.privacy_settings(db)


@router.post("/settings/privacy")
def set_privacy_settings(payload: dict, db: Session = Depends(get_db)):
    return cap.set_privacy_settings(db, payload)


@router.get("/settings/speech")
def get_speech_settings(db: Session = Depends(get_db)):
    return cap.speech_settings(db)


@router.post("/settings/speech")
def set_speech_settings(payload: dict, db: Session = Depends(get_db)):
    return cap.set_speech_settings(db, payload)
