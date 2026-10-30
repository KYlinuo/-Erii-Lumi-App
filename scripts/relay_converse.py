#!/usr/bin/env python3
"""用「Agent Relay」跑一次真实多轮对话（不需要任何模型 API Key）。

两段式：
    collect  —— 走完整真实链路（人格解析 / 记忆抽取 / 上下文组装 / 用户消息落库），
                在调用模型那一步把完整 prompt 投递到 outbox 并停下；
                由外部智能体（本次会话的算力）阅读 outbox 并写入 inbox；
    apply    —— 再用**同一个 request_id** 跑一遍（命中幂等，不会重复产生用户消息），
                这次从 inbox 取回复、落库助手消息、记录游标与 Token。

用法：
    python scripts/relay_converse.py collect --scenario scripts/relay_scenario.json
    python scripts/relay_converse.py pending
    python scripts/relay_converse.py apply  --scenario scripts/relay_scenario.json
    python scripts/relay_converse.py show
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

RELAY_DIR = Path(__file__).resolve().parents[1] / "backend" / ".agent_relay"
DEFAULT_SCENARIO = Path(__file__).resolve().parent / "relay_scenario.json"


def _boot(db_path: str):
    import os

    os.environ["LUMI_DB_PATH"] = db_path
    os.environ["LUMI_PROVIDER"] = "agent-relay"
    os.environ["LUMI_MEMORY_AUTO_EXTRACT"] = "1"

    from app.config import reload_settings

    reload_settings()

    from app.bootstrap import bootstrap
    from app.database import create_all, get_session_factory, init_engine

    init_engine(force=True)
    create_all()
    with get_session_factory()() as db:
        bootstrap(db)
    return get_session_factory()


def _provider(wait_seconds: float):
    from app.llm.agent_provider import AgentRelayProvider
    from app.llm import factory

    provider = AgentRelayProvider(RELAY_DIR, wait_seconds=wait_seconds)
    factory.set_provider(provider)
    return provider


def _request_id(conv_index: int, turn_index: int) -> str:
    return f"relay-c{conv_index}-t{turn_index}"


def cmd_collect(args) -> int:
    from app.llm.agent_provider import RelayPending
    from app.services import send_message

    scenario = json.loads(Path(args.scenario).read_text(encoding="utf-8"))
    factory_fn = _boot(args.db)

    _provider(wait_seconds=0)
    collected = []
    conv_map: dict[str, str | None] = {}
    for conv_index, conv in enumerate(scenario["conversations"]):
        character_key = conv["character_key"]
        conversation_id = None
        for turn_index, text in enumerate(conv["turns"]):
            rid = _request_id(conv_index, turn_index)
            with factory_fn() as db:
                try:
                    asyncio.run(
                        send_message(
                            db,
                            conversation_id,
                            text,
                            character_key=character_key,
                            request_id=rid,
                        )
                    )
                except RelayPending:
                    pass
                conversation_id = _conversation_of(db, rid)
            collected.append(
                {"conversation_index": conv_index, "turn_index": turn_index,
                 "character_key": character_key, "request_id": rid}
            )
        conv_map[str(conv_index)] = conversation_id

    RELAY_DIR.mkdir(parents=True, exist_ok=True)
    (RELAY_DIR / "state.json").write_text(
        json.dumps({"conversations": conv_map, "collected": collected}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"已投递 {len(collected)} 条请求到 outbox：{RELAY_DIR / 'outbox'}")
    print(f"会话映射已保存：{RELAY_DIR / 'state.json'}")
    return 0


def _conversation_of(db, request_id: str) -> str | None:
    from sqlalchemy import select

    from app.models import Message

    row = db.execute(
        select(Message.conversation_id).where(Message.request_id == request_id)
    ).first()
    return row[0] if row else None


def cmd_pending(_args) -> int:
    from app.llm.agent_provider import pending_requests

    items = pending_requests(RELAY_DIR)
    print(f"待回复：{len(items)} 条")
    for item in items:
        last = item["messages"][-1]
        system = item["messages"][0]
        print("-" * 60)
        print(f"key = {item['key']}")
        print(f"用户说：{last['content']}")
        print(f"[system 前 120 字] {system['content'][:120]}…")
    return 0


def cmd_apply(args) -> int:
    from app.llm.agent_provider import AgentRelayProvider
    from app.services import send_message

    scenario = json.loads(Path(args.scenario).read_text(encoding="utf-8"))
    factory_fn = _boot(args.db)
    _provider(wait_seconds=args.wait)

    # 必须沿用 collect 阶段创建的会话，否则同一 request_id 会被判为「跨会话冲突」
    state = json.loads((RELAY_DIR / "state.json").read_text(encoding="utf-8"))
    conv_map = state["conversations"]

    applied = []
    for conv_index, conv in enumerate(scenario["conversations"]):
        character_key = conv["character_key"]
        conversation_id = conv_map.get(str(conv_index))
        for turn_index, text in enumerate(conv["turns"]):
            rid = _request_id(conv_index, turn_index)
            with factory_fn() as db:
                result = asyncio.run(
                    send_message(
                        db,
                        conversation_id,
                        text,
                        character_key=character_key,
                        request_id=rid,
                    )
                )
            conversation_id = result["conversation_id"]
            applied.append(
                {
                    "character_key": character_key,
                    "request_id": rid,
                    "user": text,
                    "reply": result["reply"],
                    "model": result["model"],
                    "conv_seq": result.get("conv_seq"),
                    "idempotent_replay": result.get("idempotent_replay"),
                }
            )
    out = BACKEND_ROOT / Path(args.db).parent / "relay_transcript.json"
    out.write_text(json.dumps(applied, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已落库 {len(applied)} 条助手回复，逐字稿：{out}")
    for row in applied:
        print("-" * 60)
        print(f"[{row['character_key']}] 你：{row['user']}")
        print(f"[{row['character_key']}] {row['model']}：{row['reply']}")
    return 0


def cmd_show(args) -> int:
    from sqlalchemy import select

    factory_fn = _boot(args.db)
    from app.models import Conversation, Message

    with factory_fn() as db:
        convs = db.execute(select(Conversation).order_by(Conversation.created_at)).scalars()
        for conv in convs:
            from app.personas import get_character

            character = get_character(db, id=conv.character_id) if conv.character_id else None
            print("=" * 64)
            print(f"会话 {conv.id[:8]} · 人格 {character.name if character else '(无)'}")
            msgs = db.execute(
                select(Message)
                .where(Message.conversation_id == conv.id)
                .order_by(Message.conv_seq)
            ).scalars()
            for m in msgs:
                who = "你" if m.role == "user" else (character.name if character else "她")
                tail = f"  [seq={m.conv_seq} model={m.model}]" if m.role == "assistant" else ""
                print(f"  {who}：{m.content}{tail}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Agent Relay 多轮对话（无需 API Key）")
    p.add_argument("--db", default="data/relay_demo.db")
    p.add_argument("--scenario", default=str(DEFAULT_SCENARIO))
    p.add_argument("--wait", type=float, default=180.0)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("collect").set_defaults(func=cmd_collect)
    sub.add_parser("pending").set_defaults(func=cmd_pending)
    sub.add_parser("apply").set_defaults(func=cmd_apply)
    sub.add_parser("show").set_defaults(func=cmd_show)
    return p


if __name__ == "__main__":
    raise SystemExit(build_parser().parse_args().func(build_parser().parse_args()))
