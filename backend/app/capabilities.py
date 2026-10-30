"""阶段 F/G 可独立部分：能力状态清单 / 费用明细 / 轻量动态立绘交互 / 隐私设置。

诚实边界（用户原指令硬性要求）：
- 31 图片理解、32 语音消息、33 实时通话依赖外部模型与服务，当前为「可配置
  适配器预留 + 明确阻塞」，绝不把占位接口说成已打通；
- 34 立绘交互只做点击反馈与低功耗/静态模式的数据层，正式分层立绘素材缺失；
- 36 费用页区分「实际可获取的用量」（messages token 记账）与「估价」，
  未接入渠道显示 0 并标注「无实际账单」，不虚构费用。
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import usage as usage_mod
from app.config import get_settings
from app.models import AppSetting


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get(db, key: str, default):
    row = db.get(AppSetting, key)
    if row is None:
        return default
    import json

    try:
        value = json.loads(row.value)
    except (json.JSONDecodeError, TypeError):
        return default
    return value if isinstance(value, type(default)) else default


def _set(db, key: str, value) -> None:
    import json

    row = db.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value="")
        db.add(row)
    row.value = json.dumps(value, ensure_ascii=False)
    db.flush()
    db.commit()


# ---------------------------------------------------------------- 能力清单


def all_capabilities() -> dict:
    """31/32/33/34/35/36 与 APNs 的真实状态；外部阻塞写明缺什么。"""
    s = get_settings()
    return {
        "image_understanding": {
            "id": 31,
            "status": "configured" if (s.vision_model and s.vision_base_url and s.api_key) else "blocked",
            "implemented": "OpenAI 兼容视觉适配器预留（vision.py）",
            "blocked_by": [] if (s.vision_model and s.vision_base_url and s.api_key) else [
                "DeepSeek 无视觉能力，需另配 LUMI_VISION_MODEL + LUMI_VISION_BASE_URL"
            ],
            "note": "未配置时图片降级为「（用户发来一张图片）」，不假装看懂。",
        },
        "voice_message": {
            "id": 32,
            "status": "blocked",
            "implemented": "录音/上传/播放链路 + Mock WAV（明确 mock=True）",
            "blocked_by": ["真实 ASR 服务", "真实 TTS 服务与授权音色"],
            "note": "未接入服务时界面必须显示「未接入」，不把占位音频当绘梨衣语音。",
        },
        "live_call": {
            "id": 33,
            "status": "blocked",
            "implemented": "LiveKit Access Token 签发（JWT/HS256）+ iOS 房间连接",
            "blocked_by": ["LiveKit Server", "STT", "TTS"],
            "note": "取得 token / 进入房间不等于通话完成；视频入口提供的是角色动画，不是实时视频。",
        },
        "avatar": {
            "id": 34,
            "status": "partial",
            "implemented": "呼吸/眨眼/浮动占位动画 + 点击部位反馈 + 低功耗静态模式",
            "blocked_by": ["正式分层立绘素材"],
            "note": "占位动画不是最终资源；尊重系统「减少动态效果」。",
        },
        "desktop_bridge": {
            "id": 35,
            "status": "partial",
            "implemented": "协议契约 / App 端幂等 / 契约测试（/bridge/contract）",
            "blocked_by": ["桌宠端源码（当前为 Electron 发布包，无源码）"],
            "note": "桌宠端验收明确列为待完成。",
        },
        "privacy_and_cost": {
            "id": 36,
            "status": "implemented",
            "implemented": "预算拦截（并发/重试安全）+ 用量与估价页 + Face ID 锁 + 缩略图遮挡 + 诊断可关闭",
            "blocked_by": [],
            "note": "实际账单以服务商为准；本页只显示可获取用量与可配置估价。",
        },
        "apns": {
            "status": "blocked",
            "blocked_by": ["付费开发者账号 + APNs 证书/密钥"],
            "note": "免费自签不支持可靠远程唤醒；只做服务端排队 + App 打开补拉。",
        },
        "liquid_glass": {
            "id": 2,
            "status": "blocked",
            "blocked_by": ["iOS 26 SDK（当前 CI Xcode 16.4 / iOS 18.5）"],
            "note": "用 .ultraThinMaterial 等系统材质回退，不宣称原生 Liquid Glass 完成。",
        },
    }


# ---------------------------------------------------------------- 31 图片状态分类


def image_pipeline_state(data: bytes, mime: str, *, has_caption: bool = False) -> dict:
    """明确区分：上传成功 / 解析失败 / 模型不支持 / 识别不确定。

    chat.py 当前路径：未配置视觉模型 → 明确返回 model_unsupported，正文优先
    于任何自动生成描述（保留用户提供的正文与指代）。
    """
    s = get_settings()
    configured = bool(s.vision_model and s.vision_base_url and s.api_key)
    too_large = len(data) > 8 * 1024 * 1024
    supported_mime = (mime or "").lower() in (
        "image/jpeg", "image/png", "image/webp", "image/gif", "image/heic", "image/heif"
    )
    if too_large:
        state, error = "upload_too_large", "upload_too_large"
    elif not supported_mime:
        state, error = "unsupported_type", "unsupported_type"
    elif not configured:
        state, error = "model_unsupported", "model_unsupported"
    else:
        state, error = "ready_for_model", "none"
    return {
        "upload": "ok" if not too_large and supported_mime else "rejected",
        "model_supported": configured,
        "parse": "pending" if state == "ready_for_model" else "skipped",
        "state": state,
        "error": error,
        "caption_preserved": has_caption,
        "orientation_and_metadata": (
            "保留原始字节；EXIF 方向/元数据剥离需 Pillow，当前环境未安装，"
            "不伪称已处理（前端上传前请自行规范化方向）。"
        ),
        "notice": {
            "upload_too_large": "图片超过 8 MiB，需前端压缩后重试。",
            "unsupported_type": "不支持的图片格式。",
            "model_unsupported": "当前未配置视觉模型，无法解析画面；已保留用户正文与指代。",
            "ready_for_model": "已就绪，交给视觉模型；识别不确定时会明确说明。",
        }[state],
    }


# ---------------------------------------------------------------- 36 费用明细


def usage_detail(db: Session, days: int = 7) -> dict:
    """实际可获取用量 + 可配置估价 + 渠道拆分 + 预算覆盖说明。"""
    base = usage_mod.summarize(db, days=days)
    s = get_settings()
    channels = {
        "chat": {
            "status": "active",
            "source": "messages.tokens_prompt / tokens_completion 实际记账",
            "today_tokens": base["today"]["total_tokens"],
            "today_cost_usd": base["today"]["cost_usd"],
        },
        "vision": {
            "status": "not_connected" if not (s.vision_model and s.vision_base_url) else "connected",
            "source": "无实际账单（未接入渠道不虚构费用）",
            "today_tokens": 0,
            "today_cost_usd": 0.0,
        },
        "speech": {
            "status": "not_connected",
            "source": "ASR/TTS 未接入，无实际账单",
            "today_tokens": 0,
            "today_cost_usd": 0.0,
        },
        "livekit": {
            "status": "not_connected",
            "source": "LiveKit Server 未接入，无实际账单",
            "today_tokens": 0,
            "today_cost_usd": 0.0,
        },
    }
    return {
        **base,
        "channels": channels,
        "budget_controls": {
            "enforced_before_send": True,
            "concurrent_safe": True,
            "retry_safe": True,
            "covers_channels": ["chat"],
            "note": (
                "预算在每次发送/流式前实时求和（只算 assistant 真实模型消耗），"
                "因此并发与重试都会重新校验，不存在窗口内漏算；视觉/语音/通话"
                "渠道尚未接入，接入后需把其用量计入同一预算校验。"
            ),
        },
        "estimate_vs_bill": "本页为估算，实际以服务商账单为准；未接入渠道显示 0 并标注无账单。",
    }


# ---------------------------------------------------------------- 34 轻量动态立绘


_AVATAR_PARTS = ("head", "face", "hand", "book", "shoulder")
_PART_FEEDBACK = {
    "head": ("……别摸头。", "hair_bounce"),
    "face": ("……看我干什么。", "blush"),
    "hand": ("手有点凉。", "hand_wave"),
    "book": ("这一页还没写完。", "page_flip"),
    "shoulder": ("嗯……我在。", "lean"),
}


def avatar_interaction(part: str, *, reduce_motion: bool = False) -> dict:
    """点击不同部位给不同反馈；尊重「减少动态效果」→ 静态模式。"""
    key = part if part in _AVATAR_PARTS else "shoulder"
    line, motion = _PART_FEEDBACK[key]
    if reduce_motion:
        motion = "none"
    digest = hashlib.sha256(f"{key}|{_now()[:10]}".encode()).digest()[0]
    variants = ("", "（小声）", "……")
    return {
        "part": key,
        "line": line + variants[digest % len(variants)],
        "motion": motion,
        "mode": "static" if reduce_motion else "animated",
        "low_power_hint": "静态模式下不做呼吸/眨眼动画，只保留点击文字反馈。",
        "placeholder": True,
        "notice": "立绘为占位素材，正式分层素材待替换；交互不遮挡主要聊天操作。",
    }


# ---------------------------------------------------------------- 36 隐私与诊断设置

PRIVACY_KEY = "privacy_settings"


def privacy_settings(db) -> dict:
    data = _get(db, PRIVACY_KEY, {})
    return {
        "blur_snapshot": bool(data.get("blur_snapshot", True)),
        "show_diagnostics": bool(data.get("show_diagnostics", False)),
        "hide_model_meta": bool(data.get("hide_model_meta", True)),
        "note": "缩略图遮挡在 App 进入后台时生效；诊断信息默认关闭，模型名/Token 不常驻气泡。",
    }


def set_privacy_settings(db, payload: dict) -> dict:
    current = privacy_settings(db)
    merged = {
        "blur_snapshot": bool(payload.get("blur_snapshot", current["blur_snapshot"])),
        "show_diagnostics": bool(payload.get("show_diagnostics", current["show_diagnostics"])),
        "hide_model_meta": bool(payload.get("hide_model_meta", current["hide_model_meta"])),
    }
    _set(db, PRIVACY_KEY, merged)
    return privacy_settings(db)


# ---------------------------------------------------------------- 32 语音设置（持久化）

SPEECH_KEY = "speech_settings"


def speech_settings(db) -> dict:
    data = _get(db, SPEECH_KEY, {})
    return {
        "rate": float(data.get("rate", 1.0)),
        "auto_play": bool(data.get("auto_play", False)),
        "headphone_output": bool(data.get("headphone_output", False)),
        "service_status": "not_connected",
        "notice": "ASR/TTS 未配置：设置会保存，但不能伪装成已接入真实语音服务。",
    }


def set_speech_settings(db, payload: dict) -> dict:
    current = speech_settings(db)
    try:
        rate = max(0.5, min(2.0, float(payload.get("rate", current["rate"]))))
    except (TypeError, ValueError):
        rate = current["rate"]
    _set(
        db,
        SPEECH_KEY,
        {
            "rate": rate,
            "auto_play": bool(payload.get("auto_play", current["auto_play"])),
            "headphone_output": bool(payload.get("headphone_output", current["headphone_output"])),
        },
    )
    return speech_settings(db)
