"""图片理解（视觉）适配层 —— 预留接口。

DeepSeek 当前不提供图像理解，因此默认走「未配置」降级：图片消息会被转成
「（用户发来一张图片）」的文本说明，而不是假装看懂了图片。

当用户在 .env 里配置了任意 OpenAI 兼容的视觉模型（LUMI_VISION_MODEL +
LUMI_VISION_BASE_URL）后，本模块会把图片以 data URL 形式随多模态消息发给
视觉模型，返回一段对图片内容的文字描述，再交给主模型结合上下文回应。

安全边界：
- 图片只在用户主动发送时，作为 base64 data URL 上传给视觉模型服务；
- 未配置时绝不伪造「看懂」的结果；
- 视觉描述失败时降级为文本说明，不阻断聊天主流程。
"""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger("erii.vision")

_MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MiB


def vision_configured() -> bool:
    """视觉模型是否可用：需同时配置 model + base_url + api_key。"""
    s = get_settings()
    return bool(s.vision_model and s.vision_base_url and s.api_key)


def describe_image(data: bytes, mime: str, prompt: str = "") -> str | None:
    """把图片交给视觉模型，返回一段文字描述。

    未配置或调用失败时返回 None，由调用方降级为文本说明。
    """
    if not vision_configured():
        return None

    s = get_settings()
    b64 = base64.b64encode(data).decode("ascii")
    data_url = f"data:{mime or 'image/jpeg'};base64,{b64}"

    user_text = prompt or "请简单描述这张图片里有什么，注意细节。"

    payload: dict[str, Any] = {
        "model": s.vision_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "max_tokens": 512,
    }

    base_url = s.vision_base_url.rstrip("/")
    url = f"{base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {s.api_key}"}

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json=payload, headers=headers)
        if resp.status_code >= 400:
            logger.warning("vision model HTTP %s: %s", resp.status_code, resp.text[:200])
            return None
        data_out = resp.json()
        content = data_out["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        text = (content or "").strip()
        return text or None
    except Exception as exc:  # pragma: no cover - 网络层异常不阻断主流程
        logger.warning("vision describe failed: %s", exc)
        return None
