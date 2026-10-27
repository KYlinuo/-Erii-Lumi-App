"""身份与设备：多设备接入、每设备独立令牌、会话权限。

安全约定：
- API 密钥（模型 Key）**只在服务端**，客户端永远拿不到；
- 设备令牌只在注册时明文返回一次，服务端只存
  `SHA256(token + LUMI_DEVICE_TOKEN_SECRET)`，泄露库也无法还原令牌；
- 令牌可通过吊销设备即时失效；
- 主令牌（LUMI_ACCESS_TOKEN）仍然有效，方便脚本 / Windows 桌宠直连。
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Device, User

logger = logging.getLogger("lumi.identity")

VALID_SCOPES = ("chat", "sync", "memory", "world", "admin")
DEFAULT_SCOPES = "chat,sync,memory,world"

# Windows 桌宠 / 脚本等非 iPhone 客户端
PLATFORMS = ("ios", "windows", "macos", "android", "cli", "unknown")


# --------------------------------------------------------------- 用户


def ensure_default_user(db: Session, display_name: str = "Owner") -> User:
    """保证至少有一个用户存在（当前单用户产品形态）。"""
    user = db.execute(select(User).order_by(User.created_at)).scalar_one_or_none()
    if user is None:
        user = User(display_name=display_name)
        db.add(user)
        db.flush()
        logger.info("创建默认用户 %s", user.id)
    return user


def get_or_create_user(db: Session, user_id: str | None = None) -> User:
    if user_id:
        found = db.get(User, user_id)
        if found:
            return found
    return ensure_default_user(db)


# --------------------------------------------------------------- 设备令牌


def _hash_token(token: str) -> str:
    secret = get_settings().device_token_secret
    return hashlib.sha256(f"{token}:{secret}".encode("utf-8")).hexdigest()


def generate_device_token() -> str:
    """32 字节随机串，URL 安全。"""
    return secrets.token_urlsafe(32)


def token_hint(token: str) -> str:
    return f"{token[:4]}...{token[-4:]}" if len(token) > 8 else "****"


def register_device(
    db: Session,
    *,
    name: str,
    platform: str = "unknown",
    app_version: str = "0.0.0",
    scopes: str | None = None,
    user_id: str | None = None,
) -> tuple[Device, str]:
    """注册设备并返回 `(device, 明文令牌)`。明文令牌只在此刻出现一次。"""
    if platform not in PLATFORMS:
        platform = "unknown"

    wanted = [s.strip() for s in (scopes or DEFAULT_SCOPES).split(",") if s.strip()]
    normalized = ",".join(sorted({s for s in wanted if s in VALID_SCOPES})) or "chat"

    user = get_or_create_user(db, user_id)
    token = generate_device_token()

    device = Device(
        user_id=user.id,
        name=name[:64] or "未命名设备",
        platform=platform,
        app_version=app_version[:32],
        token_hash=_hash_token(token),
        token_hint=token_hint(token),
        scopes=normalized,
        revoked=0,
        created_at=datetime.now(timezone.utc),
    )
    db.add(device)
    db.flush()
    logger.info("注册设备 %s (%s/%s) scopes=%s", device.id, name, platform, normalized)
    return device, token


def verify_device_token(db: Session, token: str | None) -> Device | None:
    """按令牌查找**有效**设备；任何异常都按「未授权」处理。"""
    if not token:
        return None
    try:
        digest = _hash_token(token)
    except Exception:  # noqa: BLE001
        return None

    device = db.execute(
        select(Device).where(Device.token_hash == digest, Device.revoked == 0)
    ).scalar_one_or_none()
    if device is not None:
        device.last_seen_at = datetime.now(timezone.utc)
        db.flush()
    return device


def list_devices(db: Session, include_revoked: bool = False) -> list[Device]:
    stmt = select(Device)
    if not include_revoked:
        stmt = stmt.where(Device.revoked == 0)
    return list(db.execute(stmt.order_by(Device.created_at)).scalars())


def revoke_device(db: Session, device_id: str) -> bool:
    device = db.get(Device, device_id)
    if device is None or device.revoked:
        return False
    device.revoked = 1
    db.flush()
    logger.info("吊销设备 %s", device_id)
    return True


def rename_device(db: Session, device_id: str, name: str) -> Device | None:
    device = db.get(Device, device_id)
    if device is None:
        return None
    device.name = (name or "").strip()[:64] or device.name
    db.flush()
    return device


def set_scopes(db: Session, device_id: str, scopes: list[str]) -> Device | None:
    device = db.get(Device, device_id)
    if device is None:
        return None
    normalized = ",".join(sorted({s for s in scopes if s in VALID_SCOPES}))
    if not normalized:
        return device
    device.scopes = normalized
    db.flush()
    return device


# --------------------------------------------------------------- 主令牌


def _tokens_match(provided: str, expected: str) -> bool:
    """常量时间比较，防时序攻击。"""
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def master_token_valid(provided: str | None) -> bool:
    settings = get_settings()
    expected = settings.access_token
    if not expected or not provided:
        return False
    return _tokens_match(provided, expected)
