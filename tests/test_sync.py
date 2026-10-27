"""跨设备同步：iPhone 与 Windows 桌宠共享同一个会话、同一份消息、同一份记忆。

这里的「两台设备」用两个不同的设备令牌模拟，走的是真实的 HTTP 路径，
不做任何捷径（不共享内存对象）。
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.config import reload_settings
from app.database import create_all, get_session_factory, init_engine
from app.main import create_app
from tests.conftest import TEST_TOKEN

MASTER = {"X-LUMI-TOKEN": TEST_TOKEN}


def _two_device_app(monkeypatch):
    """构造一个开启认证的应用，并注册 iPhone 与 Windows 两台设备。"""
    monkeypatch.setenv("LUMI_ACCESS_TOKEN", TEST_TOKEN)
    # 用 Mock Provider 打通链路（不消耗任何真实额度，且 model 名可追查）
    monkeypatch.setenv("LUMI_PROVIDER", "mock")
    reload_settings()

    from app.bootstrap import bootstrap

    init_engine("sqlite:///:memory:", force=True)
    create_all()
    with get_session_factory()() as db:
        bootstrap(db)

    app = create_app()
    client = TestClient(app)
    client.__enter__()

    iphone = client.post(
        "/api/v1/devices",
        json={"name": "iPhone 17 Pro", "platform": "ios", "app_version": "0.2.0"},
        headers=MASTER,
    ).json()
    windows = client.post(
        "/api/v1/devices",
        json={"name": "EriiPet Windows", "platform": "windows", "app_version": "2.2.4"},
        headers=MASTER,
    ).json()

    return client, iphone, windows


def test_two_devices_share_one_conversation(monkeypatch):
    client, iphone, windows = _two_device_app(monkeypatch)
    iph_headers = {"X-LUMI-TOKEN": iphone["token"]}
    win_headers = {"X-LUMI-TOKEN": windows["token"]}

    # iPhone 发起对话
    conv = client.post(
        "/api/v1/conversations", params={"character_key": "lumi"}, headers=iph_headers
    ).json()["id"]

    body = client.post(
        "/api/v1/chat",
        json={"message": "在 iPhone 上说的第一句", "conversation_id": conv},
        headers=iph_headers,
    ).json()
    assert body["conversation_id"] == conv

    # Windows 同步，必须能看到 iPhone 说的话
    sync = client.post("/api/v1/sync", json={"since": {}}, headers=win_headers).json()
    target = next(c for c in sync["conversations"] if c["conversation_id"] == conv)
    texts = [m["content"] for m in target["messages"]]
    assert "在 iPhone 上说的第一句" in texts
    assert any(m["role"] == "assistant" for m in target["messages"])

    client.__exit__(None, None, None)


def test_incremental_sync_returns_only_new_messages(monkeypatch):
    client, iphone, windows = _two_device_app(monkeypatch)
    iph_headers = {"X-LUMI-TOKEN": iphone["token"]}
    win_headers = {"X-LUMI-TOKEN": windows["token"]}

    conv = client.post("/api/v1/conversations", headers=iph_headers).json()["id"]
    client.post(
        "/api/v1/chat", json={"message": "第一批", "conversation_id": conv}, headers=iph_headers
    )

    first = client.post("/api/v1/sync", json={"since": {}}, headers=win_headers).json()
    conv_block = next(c for c in first["conversations"] if c["conversation_id"] == conv)
    cursor = conv_block["cursor"]
    seen_ids = {m["id"] for m in conv_block["messages"]}

    # 再次同步：已读到的部分不应重复返回
    second = client.post(
        "/api/v1/sync", json={"since": {conv: cursor}}, headers=win_headers
    ).json()
    conv_block2 = next(c for c in second["conversations"] if c["conversation_id"] == conv)
    assert conv_block2["messages"] == []

    # iPhone 再发一条：Windows 只能拿到新增的那条
    client.post(
        "/api/v1/chat", json={"message": "第二批", "conversation_id": conv}, headers=iph_headers
    )
    third = client.post(
        "/api/v1/sync", json={"since": {conv: cursor}}, headers=win_headers
    ).json()
    block3 = next(c for c in third["conversations"] if c["conversation_id"] == conv)
    new_ids = {m["id"] for m in block3["messages"]}
    assert new_ids and not (new_ids & seen_ids)
    assert all(m["conv_seq"] > cursor for m in block3["messages"])

    client.__exit__(None, None, None)


def test_conv_seq_is_monotonic_within_conversation(monkeypatch):
    client, iphone, _windows = _two_device_app(monkeypatch)
    headers = {"X-LUMI-TOKEN": iphone["token"]}
    conv = client.post("/api/v1/conversations", headers=headers).json()["id"]
    for i in range(3):
        client.post(
            "/api/v1/chat", json={"message": f"第{i}句", "conversation_id": conv}, headers=headers
        )
    sync = client.post("/api/v1/sync", json={"since": {}}, headers=headers).json()
    block = next(c for c in sync["conversations"] if c["conversation_id"] == conv)
    seqs = [m["conv_seq"] for m in block["messages"]]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)


def test_idempotent_send_does_not_duplicate(monkeypatch):
    """断线重发同一个 request_id → 只产生一条用户消息。"""
    client, iphone, _windows = _two_device_app(monkeypatch)
    headers = {"X-LUMI-TOKEN": iphone["token"]}
    conv = client.post("/api/v1/conversations", headers=headers).json()["id"]

    payload = {
        "message": "网络很差时重发了这条",
        "conversation_id": conv,
        "request_id": "retry-0001",
    }
    first = client.post("/api/v1/chat", json=payload, headers=headers).json()
    second = client.post("/api/v1/chat", json=payload, headers=headers).json()

    assert first["reply"] == second["reply"]
    assert first["user_message_id"] == second["user_message_id"]
    assert second["idempotent_replay"] is True
    assert first["idempotent_replay"] is False

    sync = client.post("/api/v1/sync", json={"since": {}}, headers=headers).json()
    block = next(c for c in sync["conversations"] if c["conversation_id"] == conv)
    user_msgs = [m for m in block["messages"] if m["role"] == "user"]
    assert len(user_msgs) == 1, "重复提交不应产生第二条用户消息"

    client.__exit__(None, None, None)


def test_different_request_ids_still_produce_separate_messages(monkeypatch):
    client, iphone, _ = _two_device_app(monkeypatch)
    headers = {"X-LUMI-TOKEN": iphone["token"]}
    conv = client.post("/api/v1/conversations", headers=headers).json()["id"]
    for rid in ("a1", "a2"):
        client.post(
            "/api/v1/chat",
            json={"message": "同一句话", "conversation_id": conv, "request_id": rid},
            headers=headers,
        )
    sync = client.post("/api/v1/sync", json={"since": {}}, headers=headers).json()
    block = next(c for c in sync["conversations"] if c["conversation_id"] == conv)
    assert len([m for m in block["messages"] if m["role"] == "user"]) == 2


def test_device_cursor_can_be_saved_and_read(monkeypatch):
    client, iphone, _ = _two_device_app(monkeypatch)
    headers = {"X-LUMI-TOKEN": iphone["token"]}
    conv = client.post("/api/v1/conversations", headers=headers).json()["id"]

    r = client.put(
        "/api/v1/sync/cursor", json={"conversation_id": conv, "last_seq": 7}, headers=headers
    )
    assert r.json()["last_seq"] == 7

    got = client.get(f"/api/v1/sync/cursor/{conv}", headers=headers).json()
    assert got["last_seq"] == 7
    assert got["device_id"] == iphone["device_id"]

    client.__exit__(None, None, None)


def test_soft_delete_is_synced_as_tombstone(monkeypatch):
    client, iphone, windows = _two_device_app(monkeypatch)
    iph_headers = {"X-LUMI-TOKEN": iphone["token"]}
    win_headers = {"X-LUMI-TOKEN": windows["token"]}

    conv = client.post("/api/v1/conversations", headers=iph_headers).json()["id"]
    client.post("/api/v1/chat", json={"message": "要删掉的", "conversation_id": conv},
                headers=iph_headers).json()

    sync = client.post("/api/v1/sync", json={"since": {}}, headers=win_headers).json()
    block = next(c for c in sync["conversations"] if c["conversation_id"] == conv)
    msg_id = block["messages"][0]["id"]

    assert client.delete(f"/api/v1/sync/messages/{msg_id}", headers=iph_headers).status_code == 204

    again = client.post("/api/v1/sync", json={"since": {}}, headers=win_headers).json()
    block2 = next(c for c in again["conversations"] if c["conversation_id"] == conv)
    deleted = [m for m in block2["messages"] if m["id"] == msg_id]
    assert deleted and deleted[0]["deleted_at"], "删除动作必须作为 tombstone 同步给另一端"

    client.__exit__(None, None, None)


def test_messages_carry_sync_metadata(monkeypatch):
    client, iphone, _ = _two_device_app(monkeypatch)
    headers = {"X-LUMI-TOKEN": iphone["token"]}
    conv = client.post("/api/v1/conversations", headers=headers).json()["id"]
    client.post(
        "/api/v1/chat",
        json={"message": "带元数据", "conversation_id": conv, "request_id": "meta-1"},
        headers=headers,
    )
    sync = client.post("/api/v1/sync", json={"since": {}}, headers=headers).json()
    block = next(c for c in sync["conversations"] if c["conversation_id"] == conv)
    msg = next(m for m in block["messages"] if m["role"] == "user")
    assert msg["request_id"] == "meta-1"
    assert msg["conv_seq"] is not None
    assert msg["created_at"].endswith("+00:00"), "时间必须是 UTC"


def test_character_is_shared_between_devices(monkeypatch):
    """同一人格：一端切换人格，另一端看到的会话归属一致。"""
    client, iphone, windows = _two_device_app(monkeypatch)
    iph_headers = {"X-LUMI-TOKEN": iphone["token"]}
    win_headers = {"X-LUMI-TOKEN": windows["token"]}

    conv = client.post(
        "/api/v1/conversations", params={"character_key": "qilu"}, headers=iph_headers
    ).json()
    conv_id, character_id = conv["id"], conv["character_id"]
    assert character_id

    sync = client.post("/api/v1/sync", json={"since": {}}, headers=win_headers).json()
    block = next(c for c in sync["conversations"] if c["conversation_id"] == conv_id)
    assert block["character_id"] == character_id

    client.__exit__(None, None, None)
