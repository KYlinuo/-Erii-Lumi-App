"""POST /api/v1/chat —— 唯一的「产生回复」入口，必须调用真实模型。

v0.2 新增：
- `request_id` 幂等：断线重发同一条消息不会产生第二条回复；
- `character_key`：指定人格，缺省沿用会话已绑定的人格；
- 请求身份（设备令牌）会写入会话的 `origin_device_id`，便于溯源。
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app import media as media_mod
from app import speech
from app.config import Settings, get_settings
from app.database import get_db
from app.models import MediaAsset
from app.llm import ProviderError
from app.ratelimit import rate_limit
from app.schemas import ChatRequest, ChatResponse
from app.security import Caller, verify_token
from app.services import send_message, send_message_stream

logger = logging.getLogger("lumi.chat")
router = APIRouter(prefix="/api/v1")


@router.post(
    "/chat",
    response_model=ChatResponse,
    tags=["chat"],
    dependencies=[Depends(verify_token), rate_limit("chat")],
)
async def chat(
    payload: ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    caller: Caller = Depends(verify_token),
) -> ChatResponse | JSONResponse | StreamingResponse:
    text, media_id, kind, problem = await _resolve_text_and_media(db, payload)
    if problem is not None:
        return problem

    if not caller.allows("chat"):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error": {
                    "code": "forbidden",
                    "message": "当前设备没有聊天权限。",
                    "hint": "请重新注册设备并申请 chat scope。",
                }
            },
            headers={"X-LUMI-Error-Code": "forbidden"},
        )

    if payload.stream:
        return _stream_response(
            db, payload, text, media_id=media_id, kind=kind, caller=caller
        )

    try:
        data = await send_message(
            db,
            payload.conversation_id,
            text,
            character_key=payload.character_key,
            device_id=caller.device_id,
            request_id=payload.request_id,
            client_ts=payload.client_ts,
            user_id=caller.user_id,
            media_id=media_id,
            kind=kind,
        )
    except ProviderError as exc:
        http_status, problem = exc.to_problem()
        logger.warning("provider error code=%s status=%s", problem["code"], http_status)
        return JSONResponse(
            status_code=http_status,
            content={"error": problem},
            headers={"X-LUMI-Error-Code": problem["code"]},
        )

    return ChatResponse(**data)


async def _resolve_text_and_media(
    db: Session, payload: ChatRequest
) -> tuple[str, str | None, str, JSONResponse | None]:
    """把「媒体转正文 + 空文本校验」收敛成一个辅助，供流式与非流式共用。"""
    text = payload.message.strip()
    kind = payload.kind
    media_id = payload.media_id
    if media_id:
        asset = db.get(MediaAsset, media_id)
        if asset is None:
            return "", None, kind, JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={
                    "error": {
                        "code": "media_not_found",
                        "message": "找不到这条媒体，请重新上传。",
                        "hint": None,
                    }
                },
                headers={"X-LUMI-Error-Code": "media_not_found"},
            )
        if not text:
            if kind == "audio":
                transcript = speech.transcribe(
                    media_mod.path_for(asset).read_bytes(),
                    mime=asset.mime,
                    duration_ms=asset.duration_ms,
                )
                text = transcript.text
            elif kind == "image":
                text = "（用户发来一张图片）"
            else:
                text = "（媒体消息）"

    if not text:
        return "", media_id, kind, JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": "empty_message",
                    "message": "消息内容不能为空。",
                    "hint": None,
                }
            },
            headers={"X-LUMI-Error-Code": "empty_message"},
        )
    return text, media_id, kind, None


def _stream_response(
    db: Session, payload: ChatRequest, text: str, *, media_id: str | None, kind: str, caller: Caller
) -> StreamingResponse:
    async def gen():
        try:
            async for event in send_message_stream(
                db,
                payload.conversation_id,
                text,
                character_key=payload.character_key,
                device_id=caller.device_id,
                request_id=payload.request_id,
                client_ts=payload.client_ts,
                user_id=caller.user_id,
                media_id=media_id,
                kind=kind,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except ProviderError as exc:
            http_status, problem = exc.to_problem()
            logger.warning("stream provider error code=%s status=%s", problem["code"], http_status)
            yield f"data: {json.dumps({'type': 'error', **problem}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
