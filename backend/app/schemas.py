"""Pydantic 请求 / 响应模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------- 聊天


class HistoryItem(BaseModel):
    role: str = Field(pattern="^(user|assistant|system)$")
    content: str = Field(max_length=8000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = None
    # 客户端可选地携带上下文；缺省时后端从 SQLite 读取
    history: list[HistoryItem] | None = None
    # v0.2：幂等 ID（客户端生成 UUID）。同一 ID 重复提交不会重复产生回复
    request_id: str | None = Field(default=None, max_length=64)
    # v0.2：客户端本地时间戳（ISO8601），用于离线排序
    client_ts: datetime | None = None
    # v0.2：指定人格 key；缺省沿用会话已绑定的人格或默认人格
    character_key: str | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    user_message_id: str
    assistant_message_id: str
    reply: str
    model: str
    latency_ms: int
    character_id: str | None = None
    conv_seq: int | None = None
    # True 表示这是一次幂等重放，服务端没有再调用模型
    idempotent_replay: bool = False


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


class MessageSyncOut(BaseModel):
    """跨设备同步用：比 MessageOut 多出幂等 ID、游标与 tombstone。"""

    id: str
    conversation_id: str
    role: str
    content: str
    status: str = "ok"
    model: str | None = None
    error_code: str | None = None
    latency_ms: int | None = None
    request_id: str | None = None
    conv_seq: int | None = None
    client_ts: str | None = None
    media_id: str | None = None
    tokens_prompt: int | None = None
    tokens_completion: int | None = None
    deleted_at: str | None = None
    created_at: str | None = None


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0
    character_id: str | None = None
    user_id: str | None = None


# --------------------------------------------------------------- 错误与健康


class ErrorDetail(BaseModel):
    code: str
    message: str
    hint: str | None = None


class ErrorBody(BaseModel):
    error: ErrorDetail


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
    # v0.2
    schema_version: str = "unknown"
    is_mock: bool = False
    device_count: int = 0
    character_count: int = 0
    proactive_enabled: bool = False
    timezone: str = "UTC"


class PersonaResponse(BaseModel):
    name: str
    tagline: str
    avatar: str
    greeting: str


# --------------------------------------------------------------- 设备


class DeviceRegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    platform: str = "unknown"
    app_version: str = "0.0.0"
    scopes: list[str] | None = None
    user_id: str | None = None


class DeviceRegisterResponse(BaseModel):
    """注册成功返回明文令牌 —— **只出现这一次**，请立刻存入 Keychain。"""

    device_id: str
    user_id: str
    name: str
    platform: str
    token: str
    token_hint: str
    scopes: list[str]
    created_at: str


class DeviceOut(BaseModel):
    id: str
    user_id: str
    name: str
    platform: str
    app_version: str
    token_hint: str
    scopes: list[str]
    revoked: bool
    last_seen_at: str | None = None
    created_at: str


class DeviceRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class DeviceScopesRequest(BaseModel):
    scopes: list[str]


# --------------------------------------------------------------- 人格


class CharacterOut(BaseModel):
    id: str
    key: str
    name: str
    tagline: str
    avatar_key: str
    greeting: str
    summary: str
    traits: list[str] = []
    interests: list[str] = []
    background: str = ""
    speaking_style: str = ""
    source: str = "builtin"
    is_default: bool = False
    is_active: bool = True
    created_at: str | None = None
    updated_at: str | None = None


class CharacterDetail(CharacterOut):
    """含 system_prompt，仅内部 UI/调试使用。"""

    system_prompt: str = ""


# --------------------------------------------------------------- 长期记忆


class MemoryCreate(BaseModel):
    scope: str
    content: str = Field(min_length=1, max_length=1000)
    character_id: str | None = None
    # user_explicit | inferred | world_simulation | system_seed
    source_type: str = "user_explicit"
    source_ref: str = ""
    confidence: float | None = None
    salience: int = Field(default=5, ge=1, le=10)


class MemoryUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=1000)
    confidence: float | None = None
    salience: int | None = Field(default=None, ge=1, le=10)
    status: str | None = None


class MemoryOut(BaseModel):
    id: str
    user_id: str | None = None
    character_id: str | None = None
    scope: str
    subject: str
    content: str
    source_type: str
    source_message_id: str | None = None
    source_ref: str
    confidence: float
    salience: int
    status: str
    created_at: str | None = None
    updated_at: str | None = None


class MemoryScopeCount(BaseModel):
    scope: str
    count: int


# --------------------------------------------------------------- 虚构人生


class WorldEventOut(BaseModel):
    id: str
    character_id: str
    kind: str
    title: str
    content: str
    # 永远为 True：这是角色设定里的虚构内容，不是用户真实经历
    simulated: bool = True
    mood: str = ""
    meta: dict = {}
    occurred_at: str | None = None
    created_at: str | None = None


class DiaryResponse(BaseModel):
    character_key: str
    character_name: str
    # 明确提示客户端：以下内容全部为虚构生成
    notice: str = "以下为角色虚构生活中的内容，不是真实经历。"
    events: list[WorldEventOut]


# --------------------------------------------------------------- 同步


class SyncRequest(BaseModel):
    # {conversation_id: 已知的 conv_seq}
    since: dict[str, int] = Field(default_factory=dict)
    limit: int = Field(default=100, ge=1, le=500)


class ConversationDelta(BaseModel):
    conversation_id: str
    title: str
    character_id: str | None = None
    updated_at: str
    cursor: int
    has_more: bool = False
    messages: list[MessageSyncOut] = []


class SyncResponse(BaseModel):
    conversations: list[ConversationDelta]
    global_cursor: int
    server_time: str


class CursorUpdate(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=64)
    last_seq: int = Field(ge=0)


# --------------------------------------------------------------- 主动联系


class ProactiveOut(BaseModel):
    id: str
    character_id: str
    conversation_id: str | None = None
    content: str
    reason: str
    status: str
    scheduled_at: str | None = None
    sent_at: str | None = None
    created_at: str | None = None


class ProactiveToggle(BaseModel):
    enabled: bool


ErrorBody.model_rebuild()
