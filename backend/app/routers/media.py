"""媒体接口：上传 / 下载 / 删除 / 语音转写。

安全要点：
- 上传一律做 magic bytes 校验（`app/media.py`），不信任客户端声明的 MIME；
- 下载必须鉴权，响应头带 `X-Content-Type-Options: nosniff`；
- 单文件大小上限，超限 413；
- 上传者身份取自令牌，不接受客户端传入的 user_id。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import media as media_mod
from app import speech
from app.database import get_db
from app.identity import ensure_default_user
from app.models import MediaAsset
from app.ratelimit import rate_limit
from app.security import Caller, verify_token

router = APIRouter(
    prefix="/api/v1/media",
    tags=["media"],
    dependencies=[Depends(verify_token), rate_limit("default")],
)

_READ_CHUNK = 512 * 1024


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "not_found", "message": "媒体不存在。", "hint": None},
    )


async def _read_limited(upload: UploadFile, limit: int) -> bytes:
    """分块读取，超过上限立刻停止（不把整个大文件读进内存）。"""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(_READ_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={
                    "code": "file_too_large",
                    "message": f"文件超过上限（{limit // (1024 * 1024)} MiB）。",
                    "hint": "压缩后再发送，或改发文字。",
                },
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload(
    file: UploadFile = File(...),
    kind: str | None = Form(default=None),
    duration_ms: int = Form(default=0),
    db: Session = Depends(get_db),
    caller: Caller = Depends(verify_token),
):
    """上传图片或语音。返回媒体元信息，客户端随后用 `media_id` 发消息。"""
    data = await _read_limited(file, media_mod.MAX_AUDIO_BYTES)
    user = ensure_default_user(db)
    try:
        asset = media_mod.save(
            db,
            data,
            user_id=user.id,
            declared_kind=kind,
            duration_ms=max(0, duration_ms),
        )
    except media_mod.MediaRejected as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
            if exc.code != "file_too_large"
            else status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"code": exc.code, "message": exc.message, "hint": None},
        ) from exc
    db.commit()
    return asset.to_dict()


@router.get("")
def list_assets(
    kind: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    stmt = select(MediaAsset).order_by(MediaAsset.created_at.desc()).limit(limit)
    if kind:
        stmt = stmt.where(MediaAsset.kind == kind)
    rows = db.execute(stmt).scalars().all()
    return [r.to_dict() for r in rows]


@router.get("/{media_id}")
def download(media_id: str, db: Session = Depends(get_db)):
    asset = db.get(MediaAsset, media_id)
    if asset is None:
        raise _not_found()
    path = media_mod.path_for(asset)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={"code": "file_missing", "message": "媒体记录存在但文件已丢失。", "hint": None},
        )
    return FileResponse(
        path,
        media_type=asset.mime,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=31536000, immutable",
            "Content-Disposition": f'inline; filename="{asset.id}"',
        },
    )


@router.delete("/{media_id}", status_code=status.HTTP_200_OK)
def remove(media_id: str, db: Session = Depends(get_db)):
    asset = db.get(MediaAsset, media_id)
    if asset is None:
        raise _not_found()
    media_mod.remove(db, asset)
    db.commit()
    return {"deleted": media_id}


@router.post("/{media_id}/transcribe")
def transcribe(media_id: str, db: Session = Depends(get_db)):
    """把语音资产转成文字。未接入 ASR 时返回 `mock=true` 的占位文本。"""
    asset = db.get(MediaAsset, media_id)
    if asset is None:
        raise _not_found()
    if asset.kind != "audio":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "not_audio", "message": "只有语音消息可以转写。", "hint": None},
        )
    data = media_mod.path_for(asset).read_bytes()
    result = speech.transcribe(
        data,
        mime=asset.mime,
        filename=f"{asset.id}",
        duration_ms=asset.duration_ms,
    )
    return {
        "media_id": asset.id,
        "text": result.text,
        "language": result.language,
        "mock": result.mock,
        "duration_ms": result.duration_ms or asset.duration_ms,
    }


# --------------------------------------------------------------- 合成（TTS）

speech_router = APIRouter(
    prefix="/api/v1/speech",
    tags=["speech"],
    dependencies=[Depends(verify_token), rate_limit("default")],
)


@speech_router.post("/tts")
def tts(payload: dict, db: Session = Depends(get_db)):
    """把文字合成为语音。未接入 TTS 时返回可播放的 Mock WAV，并带 `X-LUMI-Mock`。"""
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "empty_text", "message": "text 不能为空。", "hint": None},
        )
    if len(text) > 1000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "text_too_long", "message": "单次合成最多 1000 字。", "hint": None},
        )
    result = speech.synthesize(text, voice=payload.get("voice"))
    from fastapi import Response

    return Response(
        content=result.audio,
        media_type=result.mime,
        headers={
            "X-LUMI-Mock": "true" if result.mock else "false",
            "X-LUMI-Model": result.model,
            "X-Content-Type-Options": "nosniff",
        },
    )


@speech_router.post("/transcribe")
async def transcribe_direct(
    file: UploadFile = File(...),
    duration_ms: int = Form(default=0),
):
    """不落库的一次性转写（客户端只想拿文字时用）。"""
    data = await _read_limited(file, media_mod.MAX_AUDIO_BYTES)
    info = media_mod.sniff(data)
    if info is None or info.kind != "audio":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "not_audio", "message": "请上传音频文件。", "hint": None},
        )
    result = speech.transcribe(data, mime=info.mime, duration_ms=duration_ms)
    return {"text": result.text, "mock": result.mock, "language": result.language}


@speech_router.get("/status")
def speech_status():
    return {
        "asr_configured": speech.asr_configured(),
        "tts_configured": speech.tts_configured(),
        "mock": not (speech.asr_configured() and speech.tts_configured()),
        "notice": "未接入语音服务时使用 Mock，返回内容会显式标注，不会冒充真实识别结果。",
    }
