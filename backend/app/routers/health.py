"""/health 与 /persona —— 供 iOS 设置页检测服务器连接状态。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import __version__
from app.config import Settings, get_settings, mask_secret
from app.database import get_db, schema_version
from app.llm.factory import get_provider, is_mock_provider
from app.models import Character, Device
from app.schemas import HealthResponse, PersonaResponse
from app.security import verify_token

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

    try:
        device_count = int(db.execute(select(func.count()).select_from(Device)).scalar_one())
        character_count = int(db.execute(select(func.count()).select_from(Character)).scalar_one())
    except Exception:  # noqa: BLE001 - 极端情况下不要让 /health 挂掉
        logger.exception("health aggregation failed")
        device_count = 0
        character_count = 0

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
        # v0.2
        "schema_version": schema_version(),
        "is_mock": is_mock_provider(provider),
        "device_count": device_count,
        "character_count": character_count,
        "proactive_enabled": settings.proactive_enabled,
        "timezone": settings.timezone,
    }


@router.get("/persona", response_model=PersonaResponse, tags=["system"])
def persona() -> PersonaResponse:
    """默认人格的简要形象信息（v0.1 客户端兼容字段）。"""
    return PERSONA


@router.get("/time", tags=["system"])
def server_time() -> dict:
    return {"server_time": datetime.now(timezone.utc).isoformat()}


@router.get("/usage", tags=["usage"], dependencies=[Depends(verify_token)])
def usage(days: int = 7, db: Session = Depends(get_db)):
    """Token 用量与成本估算（数据来自 messages 表的 token 记账）。"""
    from app import usage as usage_mod

    return usage_mod.summarize(db, days=max(1, min(days, 30)))


@router.get("/metrics", tags=["metrics"], dependencies=[Depends(verify_token)])
def metrics(db: Session = Depends(get_db)):
    """运行时性能指标：记忆检索耗时、模型回复延迟（来自 messages 表）。

    用于上下文优化的基准测试——记忆检索变慢说明注入过多，
    模型延迟升高说明窗口太长。
    """
    from app import metrics as metrics_mod
    from app.models import Message

    # 模型延迟：从 assistant 消息的 latency_ms 聚合
    lat_rows = db.execute(
        select(
            func.coalesce(func.avg(Message.latency_ms), 0),
            func.coalesce(func.max(Message.latency_ms), 0),
            func.count(Message.id),
        ).where(Message.role == "assistant", Message.latency_ms.isnot(None))
    ).one()
    avg_lat = round(float(lat_rows[0] or 0), 1)
    max_lat = int(lat_rows[1] or 0)
    reply_count = int(lat_rows[2] or 0)

    return {
        "memory_retrieval": metrics_mod.memory_retrieval.snapshot(),
        "model_reply_latency": {
            "count": reply_count,
            "avg_ms": avg_lat,
            "max_ms": max_lat,
        },
        "note": "样本只在进程生命周期内有效，重启清零；延迟来自 messages 表持久记录。",
    }
