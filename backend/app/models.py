"""数据库 ORM 模型。

v0.2 在 v0.1（Conversation / Message）基础上扩展为「跨设备统一 AI 角色核心」：

    users            用户（当前单用户，结构预留多用户）
    devices          设备（iPhone / Windows 桌宠），每设备独立令牌
    device_cursors   每设备每会话的同步游标
    characters       人格（林穗 / 祁鹿 / 沈昼 / 绘梨衣 / LUMI）
    conversations    会话（绑定用户 + 人格 + 来源设备）
    messages         消息（幂等 request_id、会话内单调 conv_seq、发送状态）
    memory_records   长期记忆（带来源与可信度，真实用户事实与角色虚构隔离）
    world_events     角色虚构人生时间线
    media_assets     图片 / 语音 / 表情包素材
    proactive_messages 服务器主动联系队列（客户端离线也能补拉）

时间一律 UTC 存储（`_utcnow()`），客户端负责本地时区展示。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.database import Base


class UTCDateTime(TypeDecorator):
    """强制以 UTC 存取的时间类型。

    SQLite 的 DATETIME 会丢掉 tzinfo，导致读回来变成 naive datetime，
    序列化后 `isoformat()` 少了 `+00:00`，客户端就无法判断时区。
    这里统一在写入时转成 UTC naive、读出时补回 `timezone.utc`，
    保证**所有时间字段对外一律是带时区的 UTC**。
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect: Dialect):  # noqa: ANN001
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect: Dialect):  # noqa: ANN001
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    display_name: Mapped[str] = mapped_column(String(64), default="Owner")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=_utcnow, onupdate=_utcnow
    )

    devices: Mapped[list["Device"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }


class Device(Base):
    """接入后端的物理设备。

    token_hash 只保存 SHA-256（服务端环境变量盐）后的值，**不存明文令牌**，
    令牌一旦返回给客户端即不可逆，只能通过重新配对重置。
    """

    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False, default="未命名设备")
    platform: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    app_version: Mapped[str] = mapped_column(String(32), nullable=False, default="0.0.0")
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    token_hint: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    scopes: Mapped[str] = mapped_column(String(255), nullable=False, default="chat,sync")
    revoked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)

    user: Mapped["User"] = relationship(back_populates="devices")

    @property
    def scope_list(self) -> list[str]:
        return [s.strip() for s in self.scopes.split(",") if s.strip()]

    def has_scope(self, scope: str) -> bool:
        return scope in self.scope_list

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "platform": self.platform,
            "app_version": self.app_version,
            "token_hint": self.token_hint,
            "scopes": self.scope_list,
            "revoked": bool(self.revoked),
            "last_seen_at": _iso(self.last_seen_at),
            "created_at": _iso(self.created_at),
        }


class DeviceCursor(Base):
    """设备在某个会话上读到的最后一条消息序号（增量同步锚点）。"""

    __tablename__ = "device_cursors"

    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True
    )
    conversation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=_utcnow, onupdate=_utcnow
    )


class Character(Base):
    """人格 / 角色定义。

    保留多套人格相互独立：LUMI、林穗、祁鹿、沈昼、绘梨衣。
    不同人格的虚构人生互不污染（world_events 按 character_id 归属）。
    """

    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    tagline: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    avatar_key: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    greeting: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    traits_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    interests_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    background: Mapped[str] = mapped_column(Text, nullable=False, default="")
    speaking_style: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="builtin")
    is_default: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=_utcnow, onupdate=_utcnow
    )

    def traits(self) -> list[str]:
        import json

        try:
            value = json.loads(self.traits_json or "[]")
        except (TypeError, ValueError):
            return []
        return value if isinstance(value, list) else []

    def interests(self) -> list[str]:
        import json

        try:
            value = json.loads(self.interests_json or "[]")
        except (TypeError, ValueError):
            return []
        return value if isinstance(value, list) else []

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "key": self.key,
            "name": self.name,
            "tagline": self.tagline,
            "avatar_key": self.avatar_key,
            "greeting": self.greeting,
            "summary": self.summary,
            "traits": self.traits(),
            "interests": self.interests(),
            "background": self.background,
            "speaking_style": self.speaking_style,
            "source": self.source,
            "is_default": bool(self.is_default),
            "is_active": bool(self.is_active),
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }

    def to_detail(self) -> dict:
        data = self.to_dict()
        data["system_prompt"] = self.system_prompt
        return data


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200), default="新的对话")
    user_id: Mapped[str | None] = mapped_column(String(64), index=True)
    character_id: Mapped[str | None] = mapped_column(String(64), index=True)
    origin_device_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=_utcnow, onupdate=_utcnow
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
        passive_deletes=True,
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
            "message_count": len(self.messages),
        }


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conv_seq", "conversation_id", "conv_seq"),
        Index("ux_messages_request_id", "request_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # user | assistant | system
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # pending | sent | ok | error
    status: Mapped[str] = mapped_column(String(16), default="ok")
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- v0.2 跨设备同步 ---
    # 客户端生成的幂等 ID：重复提交同一条消息时服务端不会写入第二条
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 会话内单调递增序号，作为增量同步游标
    conv_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 客户端本地产生时间（可能不准，仅用于离线排序与去重）
    client_ts: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    media_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # text | image | audio | sticker —— v0.3
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="text")
    tokens_prompt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_completion: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 软删除（tombstone）：删除也要能同步给另一端
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    # 用户收藏的重要消息（用于「收藏重要消息」能力）
    starred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=_utcnow, index=True
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    def to_dict(self) -> dict:
        """v0.1 兼容视图（保持既有字段集合不变）。"""
        data = {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "content": self.content,
            "status": self.status,
            "model": self.model,
            "error_code": self.error_code,
            "latency_ms": self.latency_ms,
            "created_at": _iso(self.created_at),
            # v0.3：媒体消息。历史接口也要能看到类型，否则图片/语音在
            # 另一台设备上会被渲染成一条普通文本。
            "kind": self.kind or "text",
            "media_id": self.media_id,
        }
        return {k: v for k, v in data.items() if v is not None}

    def to_sync_dict(self) -> dict:
        """跨设备同步视图：包含幂等 ID、游标、Token 消耗与 tombstone。"""
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "content": self.content,
            "status": self.status,
            "model": self.model,
            "error_code": self.error_code,
            "latency_ms": self.latency_ms,
            "request_id": self.request_id,
            "conv_seq": self.conv_seq,
            "client_ts": _iso(self.client_ts),
            "media_id": self.media_id,
            "kind": self.kind or "text",
            "tokens_prompt": self.tokens_prompt,
            "tokens_completion": self.tokens_completion,
            "starred": bool(self.starred),
            "deleted_at": _iso(self.deleted_at),
            "created_at": _iso(self.created_at),
        }


class MemoryRecord(Base):
    """长期记忆条目。

    关键约束：
    - `source_type` 标明这条记忆从哪来（用户明说 / 模型推断 / 虚构世界），
      **推断内容不允许冒充用户真实经历**；
    - `confidence` 为可信度，前端展示时可据此区分「确定事实」与「猜测」；
    - `scope` 区分六大类：user_fact / user_preference / shared_experience /
      important_event / pending_topic / fictional_life；
    - `subject` 区分归属：`user`（真实用户事实）与 `character`（角色虚构人生），
      两者在检索时严格隔离，不同 character_id 之间也互不污染。
    """

    __tablename__ = "memory_records"
    __table_args__ = (Index("ix_memory_scope", "scope", "status", "character_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    character_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    subject: Mapped[str] = mapped_column(String(32), nullable=False, default="user")
    content: Mapped[str] = mapped_column(Text, nullable=False)

    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    source_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_ref: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    salience: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    # 用户手动固定（收藏）的重要记忆：检索时权重更高，不受时间衰减
    pinned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 被成功回忆的次数与最近一次回忆时间：用于"复述加权"
    recall_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_recalled_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=_utcnow, onupdate=_utcnow
    )
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "character_id": self.character_id,
            "scope": self.scope,
            "subject": self.subject,
            "content": self.content,
            "source_type": self.source_type,
            "source_message_id": self.source_message_id,
            "source_ref": self.source_ref,
            "confidence": self.confidence,
            "salience": self.salience,
            "status": self.status,
            "pinned": bool(self.pinned),
            "recall_count": self.recall_count,
            "last_recalled_at": _iso(self.last_recalled_at),
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }


class WorldEvent(Base):
    """角色虚构人生时间线。

    `simulated=1` 表示该事件由虚构世界生成，**不是用户真实经历**，
    接口与 UI 必须显式标注，禁止冒充真实记忆。
    """

    __tablename__ = "world_events"
    __table_args__ = (Index("ix_world_events_timeline", "character_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    character_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # diary | hobby | reading | relationship | goal
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="diary")
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    simulated: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    mood: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    meta_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)

    def meta(self) -> dict:
        import json

        try:
            value = json.loads(self.meta_json or "{}")
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "character_id": self.character_id,
            "kind": self.kind,
            "title": self.title,
            "content": self.content,
            "simulated": bool(self.simulated),
            "mood": self.mood,
            "meta": self.meta(),
            "occurred_at": _iso(self.occurred_at),
            "created_at": _iso(self.created_at),
        }


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    character_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # image | audio | sticker | avatar
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="image")
    mime: Mapped[str] = mapped_column(String(64), nullable=False, default="application/octet-stream")
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    storage_uri: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "character_id": self.character_id,
            "kind": self.kind,
            "mime": self.mime,
            "byte_size": self.byte_size,
            "sha256": self.sha256,
            "storage_uri": self.storage_uri,
            "width": self.width,
            "height": self.height,
            "duration_ms": self.duration_ms,
            "created_at": _iso(self.created_at),
        }


class ProactiveMessage(Base):
    """服务器主动联系队列。

    即使 App 没打开，服务端也会把主动消息排好队；客户端下次同步（App 冷启动
    或后台拉取）时按 `status=pending` 补拉。**不声称已实现 APNs 远程推送**：
    免费自签条件下 iOS 无法可靠地远程唤醒 App。
    """

    __tablename__ = "proactive_messages"
    __table_args__ = (Index("ix_proactive_pending", "status", "scheduled_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # checkin | followup | diary | greeting
    reason: Mapped[str] = mapped_column(String(64), nullable=False, default="checkin")
    # pending | delivered | cancelled
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    scheduled_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "character_id": self.character_id,
            "conversation_id": self.conversation_id,
            "content": self.content,
            "reason": self.reason,
            "status": self.status,
            "scheduled_at": _iso(self.scheduled_at),
            "sent_at": _iso(self.sent_at),
            "created_at": _iso(self.created_at),
        }


class AppSetting(Base):
    """应用级 key-value 设置（如回复风格调节）。"""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow, onupdate=_utcnow)
