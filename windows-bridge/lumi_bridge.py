#!/usr/bin/env python3
"""Project LUMI — Windows 桥接客户端（绘梨衣桌宠 / 脚本共用同一 AI 角色核心）。

目的：让 Windows 侧与 iPhone 共用
    - 同一个角色 ID（character_id）
    - 同一个会话（conversation_id）
    - 同一份消息数据库
    - 同一份长期记忆
    - 同一条虚构人生时间线

实现说明（如实记录）：
- 现有 Windows 桌宠（EriiPet）是 **Electron 发布包**，本仓库没有它的源码，
  因此**无法**在桌宠进程内直接替换它的对话模块；
- 本文件提供的是「同一后端、同一角色、同一会话」的**集成接口 + 命令行客户端**，
  桌宠或任何 Windows 脚本只要调用它，就能读写与 iPhone 完全一致的数据；
- 只使用 Python 标准库（urllib），无需安装依赖。

用法：
    python windows-bridge/lumi_bridge.py status
    python windows-bridge/lumi_bridge.py register --name "EriiPet Windows"
    python windows-bridge/lumi_bridge.py send "你今天过得怎么样"
    python windows-bridge/lumi_bridge.py sync
    python windows-bridge/lumi_bridge.py diary --character erii
    python windows-bridge/lumi_bridge.py memory --character erii

环境变量：
    LUMI_BASE_URL       后端地址，默认 http://127.0.0.1:8000
    LUMI_TOKEN          访问令牌（设备令牌或主令牌）
    LUMI_DEVICE_FILE    设备配置存放位置，默认同目录 .lumi_device.json
    LUMI_CHARACTER      默认人格 key，默认 erii
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_DEVICE_FILE = HERE / ".lumi_device.json"
DEFAULT_CHARACTER = "erii"
TIMEOUT = 30


class BridgeError(RuntimeError):
    pass


# ------------------------------------------------------------------ 配置


def base_url() -> str:
    return (os.environ.get("LUMI_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")


def device_file() -> Path:
    return Path(os.environ.get("LUMI_DEVICE_FILE") or DEFAULT_DEVICE_FILE)


def load_device() -> dict[str, Any]:
    path = device_file()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def save_device(data: dict[str, Any]) -> None:
    path = device_file()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)  # 令牌文件仅当前用户可读
    except OSError:
        pass


def token() -> str:
    env_token = os.environ.get("LUMI_TOKEN")
    if env_token:
        return env_token
    stored = load_device().get("token")
    if not stored:
        raise BridgeError(
            "尚未注册设备：请先执行 `register`，或设置环境变量 LUMI_TOKEN。"
        )
    return str(stored)


# ------------------------------------------------------------------ HTTP


def request(
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    auth: bool = True,
    query: dict[str, Any] | None = None,
) -> Any:
    url = base_url() + path
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})

    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json"}
    if data:
        headers["Content-Type"] = "application/json"
    if auth:
        headers["X-LUMI-TOKEN"] = token()

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
            detail = payload.get("error", {})
            raise BridgeError(
                f"HTTP {exc.code} {detail.get('code', '')}: {detail.get('message', raw[:200])}"
            ) from exc
        except ValueError:
            raise BridgeError(f"HTTP {exc.code}: {raw[:200]}") from exc
    except urllib.error.URLError as exc:
        raise BridgeError(f"无法连接到后端 {base_url()}：{exc.reason}") from exc


# ------------------------------------------------------------------ 命令


def cmd_status(_args: argparse.Namespace) -> int:
    health = request("GET", "/api/v1/health", auth=False)
    print(f"后端: {base_url()}")
    print(f"  版本        : {health.get('version')}")
    print(f"  数据库      : {health.get('database')}  (schema {health.get('schema_version')})")
    print(f"  模型        : {health.get('provider')}/{health.get('provider_model')}")
    print(f"  已配置 Key  : {health.get('provider_configured')}")
    print(f"  使用 Mock   : {health.get('is_mock')}")
    print(f"  人格数量    : {health.get('character_count')}")

    device = load_device()
    if device:
        print(f"  本设备      : {device.get('name')} ({device.get('platform')}) id={device.get('device_id')}")
    else:
        print("  本设备      : 未注册（执行 register 注册）")
    return 0


def cmd_register(args: argparse.Namespace) -> int:
    payload = {
        "name": args.name,
        "platform": args.platform,
        "app_version": args.app_version,
    }
    result = request("POST", "/api/v1/devices", body=payload, auth=bool(os.environ.get("LUMI_TOKEN")))
    device = {
        "device_id": result["device_id"],
        "user_id": result["user_id"],
        "name": result["name"],
        "platform": result["platform"],
        "token": result["token"],
        "token_hint": result["token_hint"],
        "scopes": result["scopes"],
    }
    save_device(device)
    print(f"已注册设备 {device['name']}（{device['platform']}）")
    print(f"  设备 ID    : {device['device_id']}")
    print(f"  令牌指纹   : {device['token_hint']}（明文令牌已写入 {device_file()}，请妥善保管）")
    print(f"  权限       : {', '.join(device['scopes'])}")
    return 0


def cmd_send(args: argparse.Namespace) -> int:
    device = load_device()
    conversation_id = args.conversation or device.get("conversation_id")
    result = request(
        "POST",
        "/api/v1/chat",
        body={
            "message": args.text,
            "conversation_id": conversation_id,
            "character_key": args.character,
        },
    )
    device["conversation_id"] = result["conversation_id"]
    device["character_key"] = args.character
    if device.get("token") or os.environ.get("LUMI_TOKEN"):
        save_device(device)

    print(f"[{args.character}] 你：{args.text}")
    print(f"[{args.character}] {result['model']}：{result['reply']}")
    print(f"  conversation_id = {result['conversation_id']}  conv_seq = {result.get('conv_seq')}")
    if result.get("idempotent_replay"):
        print("  （幂等重放：服务端未重复调用模型）")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    device = load_device()
    since: dict[str, int] = {}
    if device.get("conversation_id"):
        since[device["conversation_id"]] = int(device.get("last_seq", 0))

    result = request("POST", "/api/v1/sync", body={"since": since, "limit": args.limit})
    printed = 0
    for block in result["conversations"]:
        new_messages = [m for m in block["messages"] if (m.get("conv_seq") or 0) > since.get(block["conversation_id"], 0)]
        if not new_messages:
            continue
        print(f"— 会话 {block['conversation_id']}（{block['title']}）")
        for m in new_messages:
            mark = "×" if m.get("deleted_at") else " "
            print(f" {mark} [{m['role']}] {m['content']}")
            printed += 1
        if device.get("conversation_id") == block["conversation_id"]:
            device["last_seq"] = block["cursor"]
    if printed == 0:
        print("没有新消息。")
    if device.get("token") or os.environ.get("LUMI_TOKEN"):
        save_device(device)
    return 0


def cmd_diary(args: argparse.Namespace) -> int:
    result = request("GET", f"/api/v1/world/{args.character}/diary", query={"limit": args.limit})
    print(f"【{result['character_name']} 的虚构日记】{result['notice']}")
    for event in result["events"]:
        print(f"  · [{event['kind']}] {event['content']}")
    return 0


def cmd_memory(args: argparse.Namespace) -> int:
    result = request("GET", "/api/v1/memory", query={"character_key": args.character, "limit": args.limit})
    print(f"共 {len(result)} 条记忆（人格 {args.character} 可见范围）")
    for item in result:
        tag = "推测" if item["source_type"] in ("inferred", "world_simulation") else "用户说过"
        print(f"  · [{item['scope']}/{item['subject']}] {item['content']}（{tag}，{int(item['confidence']*100)}%）")
    return 0


def cmd_characters(_args: argparse.Namespace) -> int:
    result = request("GET", "/api/v1/characters")
    for item in result:
        flag = ""
        if item.get("source") == "erii-pet":
            flag = "  （来自桌宠设定）"
        elif item.get("source") == "agent-authored":
            flag = "  （AI 拟定，可用原始文档覆盖）"
        elif item.get("source") == "reconstructed":
            flag = "  ⚠ 设定待补充"
        print(f"  {item['key']:10s} {item['name']}{flag}")
    return 0


# ------------------------------------------------------------------ 入口


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lumi_bridge",
        description="Project LUMI Windows 桥接客户端（与 iPhone 共享同一 AI 角色核心）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="查看后端与本机注册状态").set_defaults(func=cmd_status)

    p = sub.add_parser("register", help="把这台 Windows 注册为设备（令牌只返回一次）")
    p.add_argument("--name", default="EriiPet Windows")
    p.add_argument("--platform", default="windows", choices=["windows", "macos", "cli", "ios"])
    p.add_argument("--app-version", default="0.2.0")
    p.set_defaults(func=cmd_register)

    p = sub.add_parser("send", help="发送一条消息并等待真实模型回复")
    p.add_argument("text")
    p.add_argument("--conversation", default=None)
    p.add_argument("--character", default=os.environ.get("LUMI_CHARACTER", DEFAULT_CHARACTER))
    p.set_defaults(func=cmd_send)

    p = sub.add_parser("sync", help="增量拉取服务端新消息（含 iPhone 端产生的）")
    p.add_argument("--limit", type=int, default=100)
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("diary", help="查看角色虚构日记")
    p.add_argument("--character", default=os.environ.get("LUMI_CHARACTER", DEFAULT_CHARACTER))
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_diary)

    p = sub.add_parser("memory", help="查看长期记忆")
    p.add_argument("--character", default=os.environ.get("LUMI_CHARACTER", DEFAULT_CHARACTER))
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_memory)

    sub.add_parser("characters", help="列出可用人格").set_defaults(func=cmd_characters)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except BridgeError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
