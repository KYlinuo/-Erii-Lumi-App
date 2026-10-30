"""自然分条回复（需求 08）：把一轮回复拆成数条，带稳定 ID / 轮次 / 状态 / 节奏。

设计要点（对应用户验收要求）：
1. **稳定 ID**：`f"{turn_id}#s{index}"`。turn_id 取幂等 request_id（客户端生成）
   或已落库的消息 ID，两者在重连、同步、重启后都不变；不使用时间戳或随机数，
   因此 segments 的 ID 与顺序在任何一次重新拉取中都完全一致。
2. **轮次关系**：每条 segment 带 turn_id + index + total，一轮回复的所有分条
   归属同一个 turn；同步时随主消息一起下发（messages.segments_json）。
3. **状态**：pending → shown / skipped / stopped，支持「跳过等待」与「停止生成」，
   状态可由客户端上报并持久化，重启后继续。
4. **节奏**：immediate（立即全部呈现）/ natural（按字数给一个小延迟）。
   **重要错误与紧急求助强制 immediate，延迟为 0**，不做装饰性等待。
5. 一条 assistant 消息仍是同步与幂等的最小单位，分条只是它的渲染元数据，
   因此不会破坏既有 conv_seq / 幂等重放 / 跨设备去重（需求 35 交叉约束）。
"""

from __future__ import annotations

import json
import re

MAX_SEGMENTS = 5
MAX_CHARS = 72
MAX_NATURAL_DELAY_MS = 1400

# 句末标点（含中文省略号与分号），用于长句再切分
_SENT_SPLIT = re.compile(r"(?<=[。！？!?；;…])\s*")
_LINE_SPLIT = re.compile(r"\n+")

_VALID_STATUS = ("pending", "shown", "skipped", "stopped")
_VALID_RHYTHM = ("immediate", "natural")


def _chunks(text: str) -> list[str]:
    """先把显式换行当作作者意图的分条，再把过长的段落按句末标点合并。"""
    blocks: list[str] = []
    for raw_line in _LINE_SPLIT.split(text or ""):
        line = raw_line.strip()
        if not line:
            continue
        if len(line) <= MAX_CHARS:
            blocks.append(line)
            continue
        # 长段落：切句后累积合并，避免把一句完整的话从中间截断
        buf = ""
        for sent in _SENT_SPLIT.split(line):
            piece = sent.strip()
            if not piece:
                continue
            if buf and len(buf) + len(piece) > MAX_CHARS:
                blocks.append(buf)
                buf = piece
            else:
                buf = f"{buf}{piece}"
        if buf:
            blocks.append(buf)
    return blocks


def _merge_tail(blocks: list[str], max_segments: int) -> list[str]:
    """超过上限时把尾部合并进最后一条，保证不丢内容、不膨胀条数。"""
    if len(blocks) <= max_segments:
        return blocks
    head = blocks[: max_segments - 1]
    tail = "".join(blocks[max_segments - 1 :])
    return head + [tail]


def split_reply(
    content: str,
    *,
    turn_id: str,
    rhythm: str = "natural",
    urgent: bool = False,
    is_error: bool = False,
    max_segments: int = MAX_SEGMENTS,
) -> list[dict]:
    """把模型回复拆成分条列表。

    urgent / is_error 时强制 immediate + 零延迟（需求 08：重要错误与紧急求助
    不做装饰性延迟）。rhythm 非法值回落 natural。
    """
    eff_rhythm = rhythm if rhythm in _VALID_RHYTHM else "natural"
    force_immediate = bool(urgent or is_error)
    if force_immediate:
        eff_rhythm = "immediate"

    text = (content or "").strip()
    if not text:
        return []

    blocks = _merge_tail(_chunks(text), max(1, min(max_segments, MAX_SEGMENTS)))
    total = len(blocks)
    out: list[dict] = []
    for i, block in enumerate(blocks):
        delay = 0
        if eff_rhythm == "natural" and i > 0:
            delay = min(MAX_NATURAL_DELAY_MS, 220 + len(block) * 20)
        out.append(
            {
                "id": f"{turn_id}#s{i}",
                "turn_id": turn_id,
                "index": i,
                "total": total,
                "text": block,
                "status": "pending",
                "rhythm": eff_rhythm,
                "delay_ms": delay,
                "urgent": bool(urgent),
            }
        )
    return out


def serialize(segments: list[dict]) -> str:
    """写入 messages.segments_json。空列表写空串，节省空间。"""
    if not segments:
        return ""
    return json.dumps(segments, ensure_ascii=False, separators=(",", ":"))


def deserialize(raw: str | None) -> list[dict]:
    """从数据库读回分条；坏数据安全回落空列表（绝不抛异常打断聊天）。"""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict) and "text" in item]


def apply_control(segments: list[dict], action: str, index: int | None = None) -> list[dict]:
    """应用「跳过等待 / 停止生成 / 已展示」控制，返回新的列表（不原地修改）。

    - shown：把 index（缺省为第一个 pending）标记为 shown；
    - skip：跳过剩余等待，全部 pending → shown（不删除内容）；
    - stop：把剩余 pending 标记为 stopped（停止生成，内容保留可查看）。
    """
    result = [dict(s) for s in segments]
    if action == "shown":
        target = index
        if target is None:
            target = next((s["index"] for s in result if s.get("status") == "pending"), None)
        for s in result:
            if target is not None and s.get("index") == target and s.get("status") == "pending":
                s["status"] = "shown"
        return result
    if action == "skip":
        for s in result:
            if s.get("status") == "pending":
                s["status"] = "shown"
                s["delay_ms"] = 0
        return result
    if action == "stop":
        for s in result:
            if s.get("status") == "pending":
                s["status"] = "stopped"
                s["delay_ms"] = 0
        return result
    return result
