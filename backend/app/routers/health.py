"""/health 与 /persona —— 供 iOS 设置页检测服务器连接状态。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.config import Settings, get_settings, mask_secret
from app.database import get_db
from app.llm.factory import get_provider
from app.schemas import HealthResponse, PersonaResponse

logger = logging.getLogger("lumi.health")
router = APIRouter(prefix="/api/v1")

PERSONA = PersonaResponse(
    name="LUMI",
    tagline="会一直在你身边的 AI 少女",
    avatar="lumi_avatar",
    greeting="嗨，我是 LUMI。今天想聊点什么？",
)


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:  # pragma: no cover - 正常路径不会触发
        logger.exception("database health check failed")
        db_status = f"error: {type(exc).__name__}"

    provider = get_provider()
    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "version": __version__,
        "env": settings.env,
        "database": db_status,
        "provider": provider.name,
        "provider_model": provider.model,
        "provider_configured": provider.is_configured(),
        "api_key_hint": mask_secret(settings.api_key),
        "auth_required": settings.auth_required,
    }


@router.get("/persona", response_model=PersonaResponse, tags=["system"])
def persona() -> PersonaResponse:
    """AI 少女的名称与形象信息。"""
    return PERSONA


@router.get("/time", tags=["system"])
def server_time() -> dict:
    return {"server_time": datetime.now(timezone.utc).isoformat()}
