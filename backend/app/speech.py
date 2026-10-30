"""语音能力适配层：ASR（语音转写）与 TTS（合成）。

设计原则：

1. **默认不联网、不花钱**。没有配置真实服务时一律走 Mock，并且返回值带
   `mock=True`，客户端必须显式展示「未接入」，不能假装识别成功；
2. 真实服务只走 OpenAI 兼容协议（`/audio/transcriptions`、`/audio/speech`），
   换供应商只改 base_url 与 model，不动业务代码；
3. TTS 的 Mock 生成**真正可播放的 WAV**（极轻的低频包络），
   这样没有服务端语音能力时，客户端播放链路也能被完整测通。

注意：本项目**不做任何真人声音克隆**。TTS 只使用供应商提供的通用音色。
"""

from __future__ import annotations

import io
import math
import struct
import wave
from dataclasses import dataclass

import httpx

from app.config import get_settings
from app.llm.errors import (
    ProviderAuthError,
    ProviderBadResponse,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

MOCK_MODEL = "mock-speech-v1"


@dataclass(frozen=True)
class Transcript:
    text: str
    mock: bool
    language: str = "zh"
    duration_ms: int = 0


@dataclass(frozen=True)
class Speech:
    audio: bytes
    mime: str
    mock: bool
    model: str


def _endpoint(path: str) -> str:
    base = (get_settings().provider_base_url or "").rstrip("/")
    if base.endswith("/v1"):
        return f"{base}{path}"
    return f"{base}/v1{path}"


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_settings().api_key or ''}"}


def asr_configured() -> bool:
    settings = get_settings()
    return bool(settings.api_key) and bool(settings.asr_model)


def tts_configured() -> bool:
    settings = get_settings()
    return bool(settings.api_key) and bool(settings.tts_model)


# --------------------------------------------------------------------- Mock


def _wav_tone(seconds: float, sample_rate: int = 16000) -> bytes:
    frames = int(sample_rate * max(0.2, min(seconds, 20.0)))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        data = bytearray()
        for i in range(frames):
            envelope = math.sin(math.pi * i / max(1, frames))  # 淡入淡出
            value = int(90 * envelope * math.sin(2 * math.pi * 220 * i / sample_rate))
            data += struct.pack("<h", value)
        w.writeframes(bytes(data))
    return buf.getvalue()


def mock_transcribe(duration_ms: int = 0) -> Transcript:
    seconds = max(1, round(duration_ms / 1000)) if duration_ms else 1
    return Transcript(
        text=f"（语音消息 · {seconds} 秒；本机未接入 ASR，未做转写）",
        mock=True,
        duration_ms=duration_ms,
    )


def mock_synthesize(text: str) -> Speech:
    seconds = max(0.8, min(len(text) / 5.0, 15.0))  # 中文约 5 字/秒
    return Speech(audio=_wav_tone(seconds), mime="audio/wav", mock=True, model=MOCK_MODEL)


# ------------------------------------------------------------------- 真实实现


def transcribe(
    data: bytes,
    *,
    mime: str,
    filename: str = "audio.m4a",
    duration_ms: int = 0,
    timeout: float = 60.0,
) -> Transcript:
    if not asr_configured():
        return mock_transcribe(duration_ms)

    settings = get_settings()
    try:
        response = httpx.post(
            _endpoint("/audio/transcriptions"),
            headers=_headers(),
            files={"file": (filename, data, mime)},
            data={"model": settings.asr_model, "language": "zh"},
            timeout=timeout,
        )
    except httpx.TimeoutException as exc:
        raise ProviderTimeoutError() from exc
    except httpx.HTTPError as exc:
        raise ProviderUnavailableError() from exc

    if response.status_code in (401, 403):
        raise ProviderAuthError()
    if response.status_code >= 400:
        raise ProviderBadResponse()
    try:
        payload = response.json()
        text = (payload.get("text") or "").strip()
    except ValueError as exc:
        raise ProviderBadResponse() from exc
    if not text:
        raise ProviderBadResponse("语音识别返回了空结果，请再说一次。")
    return Transcript(text=text, mock=False, duration_ms=duration_ms)


def synthesize(text: str, *, voice: str | None = None, timeout: float = 60.0) -> Speech:
    if not tts_configured():
        return mock_synthesize(text)

    settings = get_settings()
    try:
        response = httpx.post(
            _endpoint("/audio/speech"),
            headers=_headers(),
            json={
                "model": settings.tts_model,
                "voice": voice or settings.tts_voice or "alloy",
                "input": text,
                "response_format": "mp3",
            },
            timeout=timeout,
        )
    except httpx.TimeoutException as exc:
        raise ProviderTimeoutError() from exc
    except httpx.HTTPError as exc:
        raise ProviderUnavailableError() from exc

    if response.status_code in (401, 403):
        raise ProviderAuthError()
    if response.status_code >= 400:
        raise ProviderBadResponse()
    if not response.content:
        raise ProviderBadResponse("语音合成返回了空内容。")
    return Speech(
        audio=response.content,
        mime=response.headers.get("content-type", "audio/mpeg"),
        mock=False,
        model=settings.tts_model,
    )
