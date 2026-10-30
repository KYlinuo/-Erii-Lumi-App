"""阶段 C：08 自然分条回复 / 12 语境回应 / 23 临时聊天的服务端验收测试。

覆盖用户验收场景 1（连发不吞）、3（幂等重放只有最终结果）、6（临时聊天
不进长期记忆），以及需求 08 的稳定 ID / 节奏 / 停止生成与需求 12 的
「不把情绪推断冒充已知事实」。
"""

from __future__ import annotations

from sqlalchemy import select

from app import context_sense, segments
from app.models import Conversation, MemoryRecord, Message


# ---------------------------------------------------------------- 12 语境回应


def test_classify_all_kinds():
    assert context_sense.classify("今天看到一只很胖的猫，给你看").kind == "share"
    assert context_sense.classify("今天真的好累，压力好大，想哭").kind == "vent"
    assert context_sense.classify("哈哈笑死我了233").kind == "joke"
    assert context_sense.classify("为什么天空是蓝色的？原理是什么").kind == "serious"
    assert context_sense.classify("我该怎么办，要不要换工作，给个建议").kind == "advice"


def test_urgent_is_detected_and_flagged():
    sense = context_sense.classify("救命，有人要伤害我")
    assert sense.urgent is True
    assert sense.confidence == "guess"


def test_context_prompt_never_claims_emotion_as_fact():
    prompt = context_sense.to_prompt(context_sense.classify("我很难过，压力好大"))
    assert "猜测" in prompt
    assert "未经用户确认" in prompt
    assert "不是已知事实" in prompt
    assert "不要把上面的猜测说成事实" in prompt
    assert "我知道你" in prompt  # 明确禁止的说法示例


# ---------------------------------------------------------------- 08 自然分条


def test_split_reply_stable_ids_and_turn():
    a = segments.split_reply("第一句。\n第二句！\n第三句？", turn_id="rid-1")
    b = segments.split_reply("第一句。\n第二句！\n第三句？", turn_id="rid-1")
    assert [s["id"] for s in a] == ["rid-1#s0", "rid-1#s1", "rid-1#s2"]
    assert a == b, "稳定 ID 与顺序必须完全确定性（重连/重启后一致）"
    assert all(s["turn_id"] == "rid-1" and s["total"] == 3 for s in a)
    assert all(s["status"] == "pending" for s in a)


def test_natural_rhythm_delays_immediate_does_not():
    nat = segments.split_reply("第一条。\n第二条。", turn_id="t", rhythm="natural")
    assert nat[0]["delay_ms"] == 0
    assert nat[1]["delay_ms"] > 0
    imm = segments.split_reply("第一条。\n第二条。", turn_id="t", rhythm="immediate")
    assert all(s["delay_ms"] == 0 and s["rhythm"] == "immediate" for s in imm)


def test_urgent_and_error_force_immediate():
    for kwargs in ({"urgent": True}, {"is_error": True}):
        result = segments.split_reply(
            "别怕。\n我在。", turn_id="t", rhythm="natural", **kwargs
        )
        assert all(s["rhythm"] == "immediate" and s["delay_ms"] == 0 for s in result)


def test_skip_and_stop_controls():
    base = segments.split_reply("一。\n二。\n三。", turn_id="t")
    shown = segments.apply_control(base, "shown")
    assert shown[0]["status"] == "shown" and shown[1]["status"] == "pending"
    skipped = segments.apply_control(base, "skip")
    assert all(s["status"] == "shown" and s["delay_ms"] == 0 for s in skipped)
    stopped = segments.apply_control(base, "stop")
    assert all(s["status"] in ("shown", "stopped") for s in stopped)
    assert base[0]["status"] == "pending", "控制不能原地污染原列表"


def test_serialize_roundtrip_and_bad_data():
    original = segments.split_reply("你好。", turn_id="t")
    assert segments.deserialize(segments.serialize(original)) == original
    assert segments.deserialize("not-json") == []
    assert segments.deserialize("") == []


# ---------------------------------------------------------------- 端到端


def test_chat_segments_idempotent_replay_and_sync(client, stub, db_session):
    stub.reply = "第一句。\n第二句！\n第三句？"
    payload = {"message": "你好", "request_id": "rid-c1"}
    first = client.post("/api/v1/chat", json=payload)
    assert first.status_code == 200, first.text
    data = first.json()
    assert len(data["segments"]) == 3
    assert [s["id"] for s in data["segments"]] == ["rid-c1#s0", "rid-c1#s1", "rid-c1#s2"]

    # 验收场景 3：幂等重放只有最终结果，没有逐字片段；分条完全一致
    replay = client.post(
        "/api/v1/chat", json={**payload, "conversation_id": data["conversation_id"]}
    )
    assert replay.status_code == 200
    again = replay.json()
    assert again["idempotent_replay"] is True
    assert again["segments"] == data["segments"]
    assert len(stub.calls) == 1, "重放不得再调用模型"

    # 跨设备同步视图必须带 segments，顺序与稳定 ID 一致
    sync = client.get(f"/api/v1/sync/conversation/{data['conversation_id']}")
    assert sync.status_code == 200
    assistant_rows = [m for m in sync.json() if m["role"] == "assistant"]
    assert assistant_rows and assistant_rows[-1]["segments"] == data["segments"]

    # 数据库持久化（重启后可读）
    rows = db_session.execute(
        select(Message).where(Message.conversation_id == data["conversation_id"])
    ).scalars().all()
    assert rows[-1].segment_list() == data["segments"]


def test_chat_context_block_injected_into_system_prompt(client, stub):
    stub.reply = "嗯……"
    client.post(
        "/api/v1/chat",
        json={"message": "今天好累，压力好大，想哭", "request_id": "rid-c2"},
    )
    system = stub.calls[0][0].content
    assert "语境判断" in system
    assert "猜测" in system
    assert "不是已知事实" in system


def test_urgent_chat_has_no_decorative_delay(client, stub):
    stub.reply = "别怕。\n我在。"
    resp = client.post(
        "/api/v1/chat",
        json={
            "message": "救命，有人要伤害我",
            "request_id": "rid-c3",
            "segment_rhythm": "natural",
        },
    )
    data = resp.json()
    assert data["urgent"] is True
    assert all(s["delay_ms"] == 0 and s["rhythm"] == "immediate" for s in data["segments"])


def test_ephemeral_chat_does_not_write_long_term_memory(client, stub, db_session):
    """验收场景 6：临时聊天不进入长期记忆（对照组证明抽取本身是生效的）。"""
    stub.reply = "好。"
    temp = client.post(
        "/api/v1/chat",
        json={"message": "我叫小明，在腾讯工作", "request_id": "rid-c4", "ephemeral": True},
    )
    assert temp.status_code == 200
    conv = db_session.get(Conversation, temp.json()["conversation_id"])
    assert conv is not None and conv.is_ephemeral == 1

    normal = client.post(
        "/api/v1/chat",
        json={"message": "我叫小红，在阿里工作", "request_id": "rid-c5"},
    )
    assert normal.status_code == 200

    contents = [m.content for m in db_session.execute(select(MemoryRecord)).scalars().all()]
    assert not any("小明" in c for c in contents), "临时聊天内容不得进入长期记忆"
    assert any("小红" in c for c in contents), "对照组应正常写入名字记忆"
