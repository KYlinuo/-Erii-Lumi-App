"""Pydantic 请求 / 响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = None
    # 客户端可选地携带上下文；缺省时后端从 SQLite 读取
    history: list["HistoryItem"] | None = None


class HistoryItem(BaseModel):
    role: str = Field(pattern="^(user|assistant|system)$")
    content: str = Field(max_length=8000)


class ChatResponse(BaseModel):
    conversation_id: str
    user_message_id: str
    assistant_message_id: str
    reply: str
    model: str
    latency_ms: int


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    role: str
    content: str
    status: str = "ok"
    model: str | None = None
    error_code: str | None = None
    latency_ms: int | None = None
    created_at: str


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0


class ErrorBody(BaseModel):
    error: "ErrorDetail"


class ErrorDetail(BaseModel):
    code: str
    message: str
    hint: str | None = None


ErrorBody.model_rebuild()


class HealthResponse(BaseModel):
    status: str
    version: str
    env: str
    database: str
    provider: str
    provider_model: str
    provider_configured: bool
    api_key_hint: str
    auth_required: bool


class PersonaResponse(BaseModel):
    name: str
    tagline: str
    avatar: str
    greeting: str


ChatRequest.model_rebuild()
