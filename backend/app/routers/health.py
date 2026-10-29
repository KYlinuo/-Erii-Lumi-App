"""/health 与 /persona —— 供 iOS 设置页检测服务器连接状态。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
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
    name="绘梨衣",
    tagline="安静地把今天收好，明天再想",
    avatar="erii_avatar",
    greeting="嗯……你来了。今天要待久一点吗？",
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


# ------------------------------------------------------------------ 模型切换
#
# 「模型可修改」：运行时切换模型名（LUMI_PROVIDER_MODEL 的进程内覆盖），
# 不用重启后端、不用改 .env。默认 deepseek-flash（V4.1-Flash-1017）。

_KNOWN_MODELS = (
    {"id": "deepseek-flash", "label": "DeepSeek V4.1-Flash-1017（默认，快 + 便宜）"},
    {"id": "deepseek-v4-pro", "label": "DeepSeek V4-Pro-0813（旗舰，当前路由到 Flash）"},
)


@router.get("/model", tags=["model"], dependencies=[Depends(verify_token)])
def model_info():
    from app.llm.factory import current_model

    return {
        "current": current_model(),
        "default": get_settings().provider_model,
        "configured": get_provider().is_configured(),
        "is_mock": is_mock_provider(),
        "available": _KNOWN_MODELS,
    }


@router.post("/model", tags=["model"], dependencies=[Depends(verify_token)])
def model_switch(payload: dict):
    from app.llm.factory import set_model

    model = (payload.get("model") or "").strip()
    if not model:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "invalid_model", "message": "模型名不能为空。", "hint": None}},
        )
    set_model(model)
    return {"current": model, "default": get_settings().provider_model, "configured": get_provider().is_configured()}


@router.post("/model/reset", tags=["model"], dependencies=[Depends(verify_token)])
def model_reset():
    from app.llm.factory import reset_model

    return {"current": reset_model(), "default": get_settings().provider_model}


@router.get("/export", tags=["data"], dependencies=[Depends(verify_token)])
def export_all(db: Session = Depends(get_db)):
    """全量导出聊天记录 + 长期记忆（JSON），用于备份 / 迁移。

    不包含媒体二进制，只导出元数据与文本；媒体文件仍在 media 目录。
    """
    from app.models import Conversation, Message, MemoryRecord

    conversations = db.execute(
        select(Conversation).order_by(Conversation.created_at.asc())
    ).scalars().all()
    convs = []
    for c in conversations:
        msgs = db.execute(
            select(Message)
            .where(Message.conversation_id == c.id, Message.deleted_at.is_(None))
            .order_by(Message.created_at.asc())
        ).scalars().all()
        convs.append(
            {
                "id": c.id,
                "title": c.title,
                "character_id": c.character_id,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "messages": [m.to_sync_dict() for m in msgs],
            }
        )

    memories = db.execute(
        select(MemoryRecord).order_by(MemoryRecord.updated_at.desc())
    ).scalars().all()
    mems = [m.to_dict() for m in memories]

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "version": __version__,
        "schema": schema_version(),
        "conversations": convs,
        "memories": mems,
    }


@router.post("/data/wipe", tags=["data"], dependencies=[Depends(verify_token)])
def wipe_data(payload: dict, db: Session = Depends(get_db)):
    """清除全部数据并重建（危险操作，需显式确认参数 confirm=绘梨衣）。

    删除所有会话、消息、记忆；用户/设备/角色保留。供「清除数据与重建」使用。
    """
    from app.models import Conversation, Message, MemoryRecord

    if (payload.get("confirm") or "") != "绘梨衣":
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "confirm_required",
                    "message": "清除全部数据不可恢复，需携带 confirm='绘梨衣' 二次确认。",
                    "hint": None,
                }
            },
        )
    db.execute(text("DELETE FROM messages"))
    db.execute(text("DELETE FROM conversations"))
    db.execute(text("DELETE FROM memory_records"))
    db.commit()
    return {"wiped": True, "note": "会话、消息、记忆已清空；用户/设备/角色保留。"}


@router.get("/style", tags=["style"], dependencies=[Depends(verify_token)])
def style_get(db: Session = Depends(get_db)):
    """读取当前回复风格参数（需求 09）。"""
    from app import style as style_mod

    return style_mod.get_profile(db).to_dict()


@router.post("/style", tags=["style"], dependencies=[Depends(verify_token)])
def style_set(payload: dict, db: Session = Depends(get_db)):
    """保存回复风格参数（长度/提问/表情/动作/称呼），带版本号持久化。"""
    from app import style as style_mod

    profile = style_mod.load_from_json(
        None
    )  # 起点默认；用 payload 覆盖，避免未知字段污染
    for field in ("reply_length", "question_frequency", "emoji_frequency", "address"):
        if field in payload:
            setattr(profile, field, str(payload[field]))
    if "action_description" in payload:
        profile.action_description = bool(payload["action_description"])

    profile.validate()
    style_mod.save_profile(db, profile)
    db.commit()
    return profile.to_dict()


@router.post("/feedback", tags=["feedback"], dependencies=[Depends(verify_token)])
def feedback(payload: dict, db: Session = Depends(get_db)):
    """用户对某条回复的反馈（需求 11）：记错了 / 太长 / 不像绘梨衣。

    - ``too_long`` 会自动把回复长度调到「简短」；
    - 所有反馈都记录到 app_settings 的 feedback_log（最近 50 条），
      供后续风格/记忆微调，不把普通纠正写成人物长期事实。
    """
    from app import style as style_mod
    from app.models import AppSetting

    feedback_type = (payload.get("type") or "").strip()
    message_id = (payload.get("message_id") or "").strip()
    note = (payload.get("note") or "").strip()[:200]

    valid = ("wrong", "too_long", "not_erii")
    if feedback_type not in valid:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "bad_feedback", "message": "type 必须是 wrong/too_long/not_erii。", "hint": None}},
        )

    # 动作：太长 → 自动把回复长度调短（可被用户再改回）
    if feedback_type == "too_long":
        profile = style_mod.get_profile(db)
        profile.reply_length = "short"
        style_mod.save_profile(db, profile)

    # 记录反馈轨迹
    import json as _json

    row = db.get(AppSetting, "feedback_log")
    log = []
    if row is not None:
        try:
            log = _json.loads(row.value)
        except _json.JSONDecodeError:
            log = []
    log.append({
        "type": feedback_type,
        "message_id": message_id,
        "note": note,
        "at": datetime.now(timezone.utc).isoformat(),
    })
    if row is None:
        row = AppSetting(key="feedback_log", value="")
        db.add(row)
    row.value = _json.dumps(log[-50:], ensure_ascii=False)
    db.commit()

    return {"recorded": True, "type": feedback_type, "count": len(log[-50:])}
