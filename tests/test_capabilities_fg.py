"""阶段 F/G 验收：31/32/33 外部阻塞如实标注、34 立绘点击反馈与静态模式、
36 费用明细与隐私诊断设置。"""

from __future__ import annotations


def test_capability_statuses_are_honest(client):
    caps = client.get("/api/v1/capabilities").json()
    assert caps["image_understanding"]["status"] in ("configured", "blocked")
    assert caps["voice_message"]["status"] == "blocked"
    assert caps["live_call"]["status"] == "blocked"
    assert caps["avatar"]["status"] == "partial"
    assert caps["desktop_bridge"]["status"] == "partial"
    assert caps["privacy_and_cost"]["status"] == "implemented"
    assert caps["apns"]["status"] == "blocked"
    assert caps["liquid_glass"]["status"] == "blocked"
    # 阻塞项必须写明缺什么，不许空着
    for key in ("voice_message", "live_call", "apns", "liquid_glass"):
        assert caps[key]["blocked_by"], f"{key} 必须写明阻塞条件"


def test_image_pipeline_distinguishes_four_states(client):
    too_large = client.get(
        "/api/v1/capabilities/image?size=9000000&mime=image/jpeg"
    ).json()
    assert too_large["state"] == "upload_too_large"

    bad_type = client.get(
        "/api/v1/capabilities/image?size=100&mime=application/pdf"
    ).json()
    assert bad_type["state"] == "unsupported_type"

    # DeepSeek 无视觉：默认必须标 model_unsupported，且保留用户正文
    unsupported = client.get(
        "/api/v1/capabilities/image?size=100&mime=image/jpeg&has_caption=true"
    ).json()
    assert unsupported["state"] == "model_unsupported"
    assert unsupported["caption_preserved"] is True
    assert unsupported["upload"] == "ok"


def test_usage_detail_separates_actual_and_estimate(client, stub):
    stub.reply = "嗯。"
    client.post("/api/v1/chat", json={"message": "你好", "request_id": "f-u1"})
    detail = client.get("/api/v1/usage/detail").json()
    assert set(detail["channels"]) == {"chat", "vision", "speech", "livekit"}
    assert detail["channels"]["chat"]["status"] == "active"
    for channel in ("vision", "speech", "livekit"):
        assert detail["channels"][channel]["today_cost_usd"] == 0.0
    assert detail["budget_controls"]["concurrent_safe"] is True
    assert detail["budget_controls"]["retry_safe"] is True
    assert "估算" in detail["estimate_vs_bill"]


def test_avatar_interaction_parts_and_reduce_motion(client):
    head = client.get("/api/v1/avatar/interaction?part=head").json()
    book = client.get("/api/v1/avatar/interaction?part=book").json()
    assert head["line"] != book["line"]
    assert head["mode"] == "animated"

    static = client.get(
        "/api/v1/avatar/interaction?part=face&reduce_motion=true"
    ).json()
    assert static["mode"] == "static" and static["motion"] == "none"
    assert static["placeholder"] is True  # 占位素材如实标注


def test_privacy_and_speech_settings_persist(client):
    privacy = client.get("/api/v1/settings/privacy").json()
    assert privacy["blur_snapshot"] is True
    assert privacy["show_diagnostics"] is False
    assert privacy["hide_model_meta"] is True

    updated = client.post(
        "/api/v1/settings/privacy", json={"show_diagnostics": True, "blur_snapshot": False}
    ).json()
    assert updated["show_diagnostics"] is True and updated["blur_snapshot"] is False
    assert client.get("/api/v1/settings/privacy").json() == updated

    speech = client.post(
        "/api/v1/settings/speech", json={"rate": 1.4, "auto_play": True, "headphone_output": True}
    ).json()
    assert speech["rate"] == 1.4 and speech["auto_play"] is True
    assert speech["service_status"] == "not_connected"  # 不伪装已接入
    clamped = client.post("/api/v1/settings/speech", json={"rate": 99}).json()
    assert clamped["rate"] == 2.0
