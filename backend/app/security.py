"""访问认证：主令牌 + 设备令牌。

客户端（iOS Keychain / Windows 桌宠）通过以下任一方式携带凭据：
    X-LUMI-TOKEN: <token>
    Authorization: Bearer <token>

两种令牌都认：
- **主令牌** `LUMI_ACCESS_TOKEN`：单用户环境的管理令牌；
- **设备令牌**：由 `POST /api/v1/devices` 注册时下发，按设备隔离、可单独吊销。

认证结果统一封装为 `Caller`，路由可以从里面拿到 user_id / device_id / scopes，
供数据隔离与权限判断使用。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.identity import _tokens_match, master_token_valid, verify_device_token

logger = logging.getLogger("lumi.security")

# 无需认证即可访问（只读、不含任何私密数据）
PUBLIC_PATHS: frozenset[str] = frozenset(
    {
        "/",
        "/api/v1/health",
        "/api/v1/persona",
        "/api/v1/time",
    }
)

# 注册设备本身不需要凭据，但其返回结果是一次性明文令牌，生产环境建议关闭
DEVICE_REGISTER_PATH = "/api/v1/devices"

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Caller:
    """一次请求的身份上下文。"""

    kind: str  # public | anonymous | master | device
    user_id: str | None = None
    device_id: str | None = None
    scopes: frozenset[str] = frozenset()

    @property
    def is_device(self) -> bool:
        return self.kind == "device"

    def allows(self, scope: str) -> bool:
        """权限判断：主令牌与 Anonymous(dev) 视为全权限，设备按 scopes。"""
        if self.kind in ("master", "anonymous", "public"):
            return True
        return scope in self.scopes

    def describe(self) -> str:
        if self.kind == "device":
            return f"device:{self.device_id}"
        return self.kind


class AuthState:
    """记录当前认证模式，供 /health 与日志展示。"""

    def __init__(self, required: bool) -> None:
        self.required = required

    def describe(self) -> str:
        return "required" if self.required else "disabled(dev)"


def build_auth_state() -> AuthState:
    settings = get_settings()
    if settings.is_production and not settings.access_token:
        raise RuntimeError(
            "LUMI_ENV=prod 但未提供 LUMI_ACCESS_TOKEN，拒绝启动。"
            "请执行 python scripts/gen_token.py 生成并写入 .env"
        )
    return AuthState(required=settings.auth_required)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "unauthorized",
            "message": "访问令牌缺失或不正确。",
            "hint": (
                "在请求头中携带 X-LUMI-TOKEN；"
                "可以是服务端 LUMI_ACCESS_TOKEN，也可以是设备注册时下发的令牌。"
            ),
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


def verify_token(
    request: Request,
    x_lumi_token: str | None = Header(default=None, alias="X-LUMI-TOKEN"),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Caller:
    """FastAPI 依赖：解析本次请求的身份。公开路径直接放行。"""
    settings = get_settings()

    if request.url.path in PUBLIC_PATHS:
        return Caller(kind="public")

    provided = x_lumi_token or (credentials.credentials if credentials else None)

    # 1) 主令牌
    if provided and master_token_valid(provided):
        return Caller(kind="master", scopes=frozenset({"chat", "sync", "memory", "world", "admin"}))

    # 2) 设备令牌
    if provided:
        device = verify_device_token(db, provided)
        if device is not None:
            return Caller(
                kind="device",
                user_id=device.user_id,
                device_id=device.id,
                scopes=frozenset(device.scope_list),
            )

    # 3) 开发环境裸奔
    if not settings.auth_required:
        logger.debug("auth disabled (dev mode, LUMI_ACCESS_TOKEN unset)")
        return Caller(kind="anonymous")

    raise _unauthorized()


def require_scope(scope: str):
    """细粒度权限依赖：设备令牌必须含对应 scope。"""

    def _dep(caller: Caller = Depends(verify_token)) -> Caller:
        if not caller.allows(scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "forbidden",
                    "message": f"当前设备没有 {scope} 权限。",
                    "hint": "在设置里重新注册设备，或请服务端为该设备开启对应 scope。",
                },
            )
        return caller

    return _dep
