"""媒体资产（图片 / 语音 / 表情）的落盘与校验。

安全约束（全部有测试覆盖）：

1. **不信任客户端声明的 MIME**：一律用 magic bytes 嗅探真实类型，白名单之外直接拒绝；
2. **不使用客户端文件名**：磁盘文件名由服务端生成，杜绝路径穿越；
3. **单文件大小上限**：超限返回 413，避免磁盘被打满；
4. **下载需要鉴权**，并带 `X-Content-Type-Options: nosniff`，避免被当 HTML 执行。

存储布局：`<media_root>/<sha256 前两位>/<asset_id><ext>`——按内容哈希分桶，
同一文件重复上传不会占用额外空间（内容相同则复用同一份数据）。
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import MediaAsset, new_id

# 单文件上限：图片 8 MiB，音频 20 MiB
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_AUDIO_BYTES = 20 * 1024 * 1024

ALLOWED_KINDS = ("image", "audio", "sticker", "avatar")


@dataclass(frozen=True)
class Sniffed:
    kind: str
    mime: str
    ext: str


def _match(head: bytes) -> Sniffed | None:
    """按 magic bytes 判断真实类型。顺序敏感（RIFF 家族要先看子类型）。"""
    if head.startswith(b"\xff\xd8\xff"):
        return Sniffed("image", "image/jpeg", ".jpg")
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return Sniffed("image", "image/png", ".png")
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return Sniffed("image", "image/gif", ".gif")
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return Sniffed("image", "image/webp", ".webp")
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return Sniffed("audio", "audio/wav", ".wav")
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"heic", b"heix", b"hevc", b"mif1", b"msf1"):
            return Sniffed("image", "image/heic", ".heic")
        if brand in (b"M4A ", b"M4A\x20", b"mp42", b"isom"):
            return Sniffed("audio", "audio/mp4", ".m4a")
    if head.startswith(b"OggS"):
        return Sniffed("audio", "audio/ogg", ".ogg")
    if head.startswith(b"ID3") or (head[:2] == b"\xff\xfb") or (head[:2] == b"\xff\xf3"):
        return Sniffed("audio", "audio/mpeg", ".mp3")
    if head.startswith(b"#!AMR"):
        return Sniffed("audio", "audio/amr", ".amr")
    return None


def sniff(data: bytes) -> Sniffed | None:
    return _match(data[:32])


def media_root() -> Path:
    override = os.environ.get("LUMI_MEDIA_DIR")
    if override:
        root = Path(override)
    else:
        db_path = Path(get_settings().resolved_db_path)
        root = db_path.parent / "media"
    root.mkdir(parents=True, exist_ok=True)
    return root


def limit_for(kind: str) -> int:
    return MAX_AUDIO_BYTES if kind == "audio" else MAX_IMAGE_BYTES


class MediaRejected(ValueError):
    """上传内容被拒绝（类型不支持 / 超出大小）。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def validate(data: bytes, *, declared_kind: str | None = None) -> Sniffed:
    if not data:
        raise MediaRejected("empty_file", "上传内容为空。")
    info = sniff(data)
    if info is None:
        raise MediaRejected(
            "unsupported_type",
            "不支持的文件类型：只接受 JPEG / PNG / GIF / WebP / HEIC 图片与 WAV / M4A / MP3 / OGG / AMR 音频。",
        )
    if len(data) > limit_for(info.kind):
        raise MediaRejected(
            "file_too_large",
            f"文件超过上限（{'20' if info.kind == 'audio' else '8'} MiB）。",
        )
    if declared_kind and declared_kind not in ALLOWED_KINDS:
        raise MediaRejected("invalid_kind", f"未知的媒体类型 {declared_kind}。")
    return info


def path_for(asset: MediaAsset) -> Path:
    return media_root() / asset.storage_uri


def save(
    db: Session,
    data: bytes,
    *,
    user_id: str | None,
    character_id: str | None = None,
    declared_kind: str | None = None,
    width: int = 0,
    height: int = 0,
    duration_ms: int = 0,
) -> MediaAsset:
    """写入媒体。相同内容（sha256 一致）复用同一份磁盘文件。"""
    info = validate(data, declared_kind=declared_kind)
    digest = hashlib.sha256(data).hexdigest()

    cond = (MediaAsset.user_id == user_id) if user_id else MediaAsset.user_id.is_(None)
    existing: MediaAsset | None = db.execute(
        select(MediaAsset).where(MediaAsset.sha256 == digest, cond)
    ).scalars().first()

    if existing is not None and path_for(existing).exists():
        return existing

    asset = MediaAsset(
        id=new_id(),
        user_id=user_id,
        character_id=character_id,
        kind=declared_kind if declared_kind in ("sticker", "avatar") else info.kind,
        mime=info.mime,
        byte_size=len(data),
        sha256=digest,
        storage_uri="",
        width=width,
        height=height,
        duration_ms=duration_ms,
    )
    rel = f"{digest[:2]}/{asset.id}{info.ext}"
    target = media_root() / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(target)
    asset.storage_uri = rel
    db.add(asset)
    db.flush()
    return asset


def remove(db: Session, asset: MediaAsset) -> None:
    """删除记录；磁盘文件只在没有任何其它记录引用时才真正删除。"""
    rel = asset.storage_uri
    db.delete(asset)
    db.flush()
    if not rel:
        return
    still_used = db.execute(
        select(MediaAsset.id).where(MediaAsset.storage_uri == rel).limit(1)
    ).first()
    if still_used is None:
        try:
            (media_root() / rel).unlink(missing_ok=True)
        except OSError:  # 磁盘问题不应导致接口 500
            pass
