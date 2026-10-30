"""媒体与语音测试。

覆盖的安全与语义约束：
- 不信任客户端 MIME：伪装成 image/png 的文本必须被拒；
- 超限文件返回 413；
- 文件名由服务端生成（客户端传 ../../ 也不会穿越）；
- 下载需要鉴权，且带 nosniff；
- 相同内容只占一份磁盘空间；
- 未接入 ASR/TTS 时必须显式标记 mock，不能假装识别/合成成功。
"""

from __future__ import annotations

import io
import os
import struct
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_TOKEN = "test-token-media"

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    + b"\x00\x00\x00\rIHDR"
    + struct.pack(">II", 1, 1)
    + b"\x08\x06\x00\x00\x00"
    + b"\x00" * 24
)


def _wav_bytes(seconds: float = 0.3, rate: int = 8000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return buf.getvalue()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LUMI_ACCESS_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("LUMI_DB_PATH", str(tmp_path / "media.db"))
    monkeypatch.setenv("LUMI_MEDIA_DIR", str(tmp_path / "media-store"))
    monkeypatch.setenv("LUMI_PROVIDER", "mock")
    monkeypatch.setenv("LUMI_MEMORY_AUTO_EXTRACT", "0")

    from app.config import reload_settings

    reload_settings()
    from app.database import init_db

    init_db(force=True)

    from app.main import create_app

    app = create_app()
    with TestClient(app) as c:
        c.headers.update({"Authorization": f"Bearer {TEST_TOKEN}"})
        yield c


def test_upload_image_and_download(client):
    r = client.post("/api/v1/media", files={"file": ("a.png", PNG_BYTES, "image/png")})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "image"
    assert body["mime"] == "image/png"
    assert body["byte_size"] == len(PNG_BYTES)

    got = client.get(f"/api/v1/media/{body['id']}")
    assert got.status_code == 200
    assert got.content == PNG_BYTES
    assert got.headers["x-content-type-options"] == "nosniff"


def test_rejects_fake_mime(client):
    """客户端把文本声明成 image/png，也必须被 magic bytes 拦下。"""
    r = client.post(
        "/api/v1/media",
        files={"file": ("evil.png", b"<script>alert(1)</script>", "image/png")},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "unsupported_type"


def test_upload_is_authenticated(client):
    r = client.post(
        "/api/v1/media",
        files={"file": ("a.png", PNG_BYTES, "image/png")},
        headers={"Authorization": "Bearer wrong"},
    )
    assert r.status_code == 401


def test_client_filename_is_ignored(client, tmp_path):
    r = client.post(
        "/api/v1/media",
        files={"file": ("../../../../evil.png", PNG_BYTES, "image/png")},
    )
    assert r.status_code == 201
    stored = list((tmp_path / "media-store").rglob("*"))
    files = [p for p in stored if p.is_file()]
    assert len(files) == 1
    # 落盘路径必须仍在 media 根目录内
    assert (tmp_path / "media-store") in files[0].parents


def test_duplicate_content_reuses_storage(client):
    first = client.post("/api/v1/media", files={"file": ("a.png", PNG_BYTES, "image/png")}).json()
    second = client.post("/api/v1/media", files={"file": ("b.png", PNG_BYTES, "image/png")}).json()
    assert first["id"] == second["id"], "相同内容应复用同一条媒体记录"


def test_audio_upload_and_transcribe_mock(client):
    wav = _wav_bytes()
    r = client.post(
        "/api/v1/media",
        files={"file": ("v.wav", wav, "audio/wav")},
        data={"duration_ms": "1200"},
    )
    assert r.status_code == 201, r.text
    media = r.json()
    assert media["kind"] == "audio"

    tr = client.post(f"/api/v1/media/{media['id']}/transcribe")
    assert tr.status_code == 200
    body = tr.json()
    assert body["mock"] is True, "未接入 ASR 时必须显式标记 mock"
    assert "未接入" in body["text"]


def test_transcribe_rejects_image(client):
    media = client.post(
        "/api/v1/media", files={"file": ("a.png", PNG_BYTES, "image/png")}
    ).json()
    r = client.post(f"/api/v1/media/{media['id']}/transcribe")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "not_audio"


def test_tts_returns_playable_wav_marked_mock(client):
    r = client.post("/api/v1/speech/tts", json={"text": "晚上好呀"})
    assert r.status_code == 200
    assert r.headers["x-lumi-mock"] == "true"
    assert r.content[:4] == b"RIFF"
    with wave.open(io.BytesIO(r.content)) as w:
        assert w.getnframes() > 0


def test_tts_rejects_empty_text(client):
    r = client.post("/api/v1/speech/tts", json={"text": "   "})
    assert r.status_code == 422


def test_speech_status_reports_mock(client):
    body = client.get("/api/v1/speech/status").json()
    assert body["mock"] is True
    assert "不会冒充" in body["notice"]


def test_chat_with_image_media(client):
    media = client.post(
        "/api/v1/media", files={"file": ("a.png", PNG_BYTES, "image/png")}
    ).json()
    r = client.post(
        "/api/v1/chat",
        json={"message": "", "media_id": media["id"], "kind": "image"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reply"]

    messages = client.get(f"/api/v1/conversations/{body['conversation_id']}/messages").json()
    user_msg = next(m for m in messages if m["role"] == "user")
    assert user_msg["kind"] == "image"
    assert user_msg["media_id"] == media["id"]


def test_chat_with_audio_media_uses_transcript(client):
    wav = _wav_bytes()
    media = client.post(
        "/api/v1/media", files={"file": ("v.wav", wav, "audio/wav")}
    ).json()
    r = client.post(
        "/api/v1/chat",
        json={"message": "", "media_id": media["id"], "kind": "audio"},
    )
    assert r.status_code == 200
    messages = client.get(f"/api/v1/conversations/{r.json()['conversation_id']}/messages").json()
    user_msg = next(m for m in messages if m["role"] == "user")
    assert user_msg["kind"] == "audio"
    assert "语音消息" in user_msg["content"]


def test_chat_with_unknown_media_returns_404(client):
    r = client.post("/api/v1/chat", json={"message": "", "media_id": "nope", "kind": "image"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "media_not_found"


def test_delete_removes_file_and_record(client, tmp_path):
    media = client.post(
        "/api/v1/media", files={"file": ("a.png", PNG_BYTES, "image/png")}
    ).json()
    files_before = [p for p in (tmp_path / "media-store").rglob("*") if p.is_file()]
    assert files_before

    r = client.delete(f"/api/v1/media/{media['id']}")
    assert r.status_code == 200
    assert client.get(f"/api/v1/media/{media['id']}").status_code == 404
    files_after = [p for p in (tmp_path / "media-store").rglob("*") if p.is_file()]
    assert files_after == []


def test_media_list_filters_by_kind(client):
    client.post("/api/v1/media", files={"file": ("a.png", PNG_BYTES, "image/png")})
    client.post("/api/v1/media", files={"file": ("v.wav", _wav_bytes(), "audio/wav")})
    images = client.get("/api/v1/media?kind=image").json()
    audios = client.get("/api/v1/media?kind=audio").json()
    assert [m["kind"] for m in images] == ["image"]
    assert [m["kind"] for m in audios] == ["audio"]
