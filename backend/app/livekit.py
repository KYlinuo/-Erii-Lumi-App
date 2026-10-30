"""LiveKit 实时音视频通话支持。

架构：
    iPhone（LiveKit SDK）  ←→  LiveKit Server  ←→  LiveKit Agent（服务端语音助手）
                                                       │
                                          STT → DeepSeek → TTS → 音频回传

本模块负责**签发 LiveKit Access Token**（JWT / HS256，纯标准库实现，零额外依赖）
与**配置读取**。真正的双向通话需要：
    1. 一台 LiveKit Server（cloud.livekit.io 或自建 livekit-server）；
    2. STT / TTS 服务（DeepSeek 只做文本推理，不含语音合成/识别）。

未配置时，`call_status()` 会如实返回 `configured=false`，接口绝不假装已接通。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from app.config import get_settings


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _sign(header_payload: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), header_payload.encode("ascii"), hashlib.sha256).digest()
    return _b64url(digest)


def make_access_token(
    *,
    api_key: str,
    api_secret: str,
    identity: str,
    room: str,
    ttl_seconds: int = 3600,
    can_publish: bool = True,
    can_subscribe: bool = True,
    name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """签发一个 LiveKit Access Token（JWT，HS256）。

    identity 是该连接在房间里的唯一身份（我们用它区分「用户」与「AI 角色」）。
    """
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload: dict[str, Any] = {
        "iss": api_key,
        "sub": identity,
        "nbf": now,
        "exp": now + ttl_seconds,
        "video": {
            "room": room,
            "roomJoin": True,
            "canPublish": can_publish,
            "canSubscribe": can_subscribe,
            "canPublishData": True,
        },
    }
    if name:
        payload["name"] = name
    if metadata:
        payload["metadata"] = json.dumps(metadata, ensure_ascii=False)

    hp = _b64url(json.dumps(header, separators=(",", ":")).encode()) + "." + _b64url(
        json.dumps(payload, separators=(",", ":")).encode()
    )
    return hp + "." + _sign(hp, api_secret)


def livekit_configured() -> bool:
    s = get_settings()
    return bool(s.livekit_url and s.livekit_api_key and s.livekit_api_secret)


def call_status() -> dict:
    """语音/视频通话能力概览（如实报告，不做假）。"""
    s = get_settings()
    return {
        "configured": livekit_configured(),
        "livekit_url": s.livekit_url or None,
        "stt_configured": s.asr_model != "",
        "tts_configured": s.tts_model != "",
        "note": (
            "实时通话需要 LiveKit Server + STT/TTS 服务。"
            "未配置时通话按钮只展示说明，不产生任何费用。"
        ),
    }


def issue_call_token(
    *,
    identity: str,
    room: str,
    character_name: str = "绘梨衣",
    ttl_seconds: int = 3600,
) -> dict:
    """为一次通话签发用户侧 token（供 iOS LiveKit SDK 连接房间）。"""
    s = get_settings()
    if not livekit_configured():
        return {"configured": False, "reason": "livekit_not_configured"}
    token = make_access_token(
        api_key=s.livekit_api_key,
        api_secret=s.livekit_api_secret,
        identity=identity,
        room=room,
        ttl_seconds=ttl_seconds,
        can_publish=True,
        can_subscribe=True,
        name=f"user:{identity}",
        metadata={"role": "user", "character": character_name},
    )
    return {
        "configured": True,
        "url": s.livekit_url.rstrip("/"),
        "token": token,
        "room": room,
        "identity": identity,
        "ttl_seconds": ttl_seconds,
    }
