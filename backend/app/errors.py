"""业务层异常（非模型上游错误）。

与 `app.llm.errors.ProviderError` 区分：这里是 LUMI 自己的业务语义，
同样会走统一错误信封 `{"error": {"code","message","hint"}}`。
"""

from __future__ import annotations

from typing import ClassVar


class LUMIError(Exception):
    code: ClassVar[str] = "internal_error"
    http_status: ClassVar[int] = 400
    message: ClassVar[str] = "请求无法处理。"
    hint: ClassVar[str | None] = None

    def __init__(self, message: str | None = None, hint: str | None = None) -> None:
        self.text = message or self.message
        self.detail = hint or self.hint
        super().__init__(self.text)

    def to_problem(self) -> tuple[int, dict]:
        return self.http_status, {"code": self.code, "message": self.text, "hint": self.detail}


class RequestIdConflict(LUMIError):
    """同一个 request_id 被用在了另一个会话上 —— 客户端逻辑有误。"""

    code = "request_id_conflict"
    http_status = 409
    message = "该幂等 ID 已经用于另一个会话。"
    hint = "request_id 必须全局唯一且与会话绑定；请为新的会话生成新的 request_id。"


class ConversationNotFound(LUMIError):
    code = "not_found"
    http_status = 404
    message = "会话不存在。"
    hint = "会话可能已在其他设备上被删除。"
