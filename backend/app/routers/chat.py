"""POST /api/v1/chat —— 唯一的「产生回复」入口，必须调用真实模型。

v0.2 新增：
- `request_id` 幂等：断线重发同一条消息不会产生第二条回复；
- `character_key`：指定人格，缺省沿用会话已绑定的人格；
- 请求身份（设备令牌）会写入会话的 `origin_device_id`，便于溯源。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.llm import ProviderError
from app.ratelimit import rate_limit
from app.schemas import ChatRequest, ChatResponse
from app.security import Caller, verify_token
from app.services import send_message

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
) -> ChatResponse | JSONResponse:
    text = payload.message.strip()
    if not text:
        return JSONResponse(
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
