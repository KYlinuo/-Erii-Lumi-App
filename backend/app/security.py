"""单用户访问认证。

客户端（iOS Keychain 中保存的 token）通过以下任一方式携带：
    X-LUMI-TOKEN: <token>
    Authorization: Bearer <token>

服务端只比较环境变量 LUMI_ACCESS_TOKEN，使用 hmac.compare_digest 防时序攻击。
"""

from __future__ import annotations

import hmac
import logging

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

logger = logging.getLogger("lumi.security")

# 无需认证即可访问（只读、不含任何私密数据）
PUBLIC_PATHS: frozenset[str] = frozenset(
    {
        "/",
        "/api/v1/health",
        "/api/v1/persona",
    }
)

bearer_scheme = HTTPBearer(auto_error=False)


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


def _tokens_match(provided: str, expected: str) -> bool:
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def verify_token(
    request: Request,
    x_lumi_token: str | None = Header(default=None, alias="X-LUMI-TOKEN"),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    """FastAPI 依赖：校验访问令牌。公开路径直接放行。"""
    settings = get_settings()

    if request.url.path in PUBLIC_PATHS:
        return "public"

    if not settings.auth_required:
        # dev 且未配置 token：放行，但每次启动仅记录一次
        logger.debug("auth disabled (dev mode, LUMI_ACCESS_TOKEN unset)")
        return "anonymous"

    provided = x_lumi_token or (credentials.credentials if credentials else None)
    expected = settings.access_token or ""

    if not provided or not expected or not _tokens_match(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "unauthorized",
                "message": "访问令牌缺失或不正确。",
                "hint": "在请求头中携带 X-LUMI-TOKEN，值需与服务端 LUMI_ACCESS_TOKEN 一致。",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    return "user"
