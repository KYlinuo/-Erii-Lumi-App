"""POST /api/v1/chat —— 唯一的「产生回复」入口，必须调用真实模型。"""

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
from app.security import verify_token
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
        )

    try:
        data = await send_message(db, payload.conversation_id, text)
    except ProviderError as exc:
        http_status, problem = exc.to_problem()
        logger.warning("provider error code=%s status=%s", problem["code"], http_status)
        return JSONResponse(
            status_code=http_status,
            content={"error": problem},
            headers={"X-LUMI-Error-Code": problem["code"]},
        )

    return ChatResponse(**data)
