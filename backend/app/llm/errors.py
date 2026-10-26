"""上游模型异常 → HTTP 错误码映射。

设计目标：客户端（iOS）要能对每一种失败给出**不同且准确**的提示，
因此这里不做笼统的 "内部错误"，而是细分到具体语义。
"""

from __future__ import annotations

from typing import ClassVar


class ProviderError(Exception):
    """所有上游模型错误的基类。"""

    code: ClassVar[str] = "upstream_error"
    http_status: ClassVar[int] = 502
    message: ClassVar[str] = "模型服务暂时不可用。"

    def __init__(self, message: str | None = None, detail: str | None = None) -> None:
        self.text = message or self.message
        self.detail = detail
        super().__init__(self.text)

    def to_problem(self) -> tuple[int, dict]:
        return self.http_status, {
            "code": self.code,
            "message": self.text,
            "hint": self.detail,
        }


class ProviderNotConfigured(ProviderError):
    """未配置 API Key —— 明确告诉使用者去配置，而不是返回假回复。"""

    code = "provider_not_configured"
    http_status = 503
    message = "后端尚未配置模型 API Key，无法生成回复。"

    def __init__(self, detail: str | None = "请在 .env 中设置 LUMI_API_KEY 后重启后端。") -> None:
        super().__init__(self.message, detail)


class ProviderAuthError(ProviderError):
    code = "upstream_unauthorized"
    http_status = 502
    message = "模型服务拒绝了请求（API Key 无效或已禁用）。"

    def __init__(self, detail: str | None = "请检查后端环境变量 LUMI_API_KEY 是否正确。") -> None:
        super().__init__(self.message, detail)


class ProviderRateLimitError(ProviderError):
    code = "upstream_rate_limited"
    http_status = 429
    message = "模型服务限流，请稍后再试。"

    def __init__(self, detail: str | None = "上游返回 429，稍等十几秒再发送。") -> None:
        super().__init__(self.message, detail)


class ProviderTimeoutError(ProviderError):
    code = "upstream_timeout"
    http_status = 504
    message = "模型响应超时，请重试。"

    def __init__(self, detail: str | None = "上游未在超时时间内返回完整结果。") -> None:
        super().__init__(self.message, detail)


class ProviderUnavailableError(ProviderError):
    """连接失败 / DNS 失败 / 5xx —— 对应客户端「断网或服务器不可达」。"""

    code = "upstream_unavailable"
    http_status = 503
    message = "无法连接到模型服务，请检查网络。"

    def __init__(self, detail: str | None = "网络不可达或上游服务故障。") -> None:
        super().__init__(self.message, detail)


class ProviderBadResponse(ProviderError):
    code = "upstream_bad_response"
    http_status = 502
    message = "模型返回了无法解析的内容。"

    def __init__(self, detail: str | None = "上游响应结构与 OpenAI 兼容格式不一致。") -> None:
        super().__init__(self.message, detail)
