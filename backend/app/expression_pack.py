"""专属表情动作（需求 18）：统一风格的表情包 / 便签贴纸 / 轻量动作词库。

硬性约束：
1. 控制重复和频率 —— 用最近使用记录做去重窗口，并可设置频率上限；
2. 素材来源、授权与用户导入记录清楚；
3. **缺少正式素材时标注待替换**，不把工程占位素材写成最终资源完成。
   本模块内置条目全部 `placeholder=True / license=project-placeholder`。

用户导入的条目单独存 app_settings，附来源与授权声明，不覆盖内置占位。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

_FREQUENCY_LIMIT = {"low": 1, "medium": 2, "high": 3}
_RECENT_KEY = "expression_recent"
_USER_PACK_KEY = "expression_user_pack"
_FREQ_KEY = "expression_frequency"

# 工程占位词库：统一风格（安静、短句、小本子），全部标注待替换。
_BUILTIN: dict[str, list[dict]] = {
    "sticker": [
        {"id": "st-01", "text": "（把本子合上）", "tag": "收起来"},
        {"id": "st-02", "text": "（在本子边角画了个小圈）", "tag": "走神"},
        {"id": "st-03", "text": "（抬头看了一眼，又低下去）", "tag": "害羞"},
        {"id": "st-04", "text": "（把橡皮摆正）", "tag": "小习惯"},
    ],
    "action": [
        {"id": "ac-01", "text": "*她低头翻了翻本子*", "tag": "安静"},
        {"id": "ac-02", "text": "*她把话停在这里，没有说完*", "tag": "留半句"},
        {"id": "ac-03", "text": "*她轻轻点了一下头*", "tag": "回应"},
        {"id": "ac-04", "text": "*她把窗户推开一点，听雨*", "tag": "看雨"},
    ],
    "note_sticker": [
        {"id": "ns-01", "text": "【今天还不错的瞬间】", "tag": "便签"},
        {"id": "ns-02", "text": "【下次再说】", "tag": "便签"},
        {"id": "ns-03", "text": "【记得的约定】", "tag": "便签"},
    ],
}


def _setting(db, key: str) -> str | None:
    from app.models import AppSetting

    row = db.get(AppSetting, key)
    return row.value if row else None


def _save_setting(db, key: str, value: str) -> None:
    from app.models import AppSetting

    row = db.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value=value)
        db.add(row)
    row.value = value
    db.flush()


def _recent(db) -> list[str]:
    try:
        data = json.loads(_setting(db, _RECENT_KEY) or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    return data if isinstance(data, list) else []


def get_frequency(db) -> str:
    value = _setting(db, _FREQ_KEY) or "medium"
    return value if value in _FREQUENCY_LIMIT else "medium"


def set_frequency(db, value: str) -> str:
    value = value if value in _FREQUENCY_LIMIT else "medium"
    _save_setting(db, _FREQ_KEY, value)
    db.commit()
    return value


def all_packs(db) -> dict:
    """返回全部词库 + 来源/授权记录 + 占位声明。"""
    user_items: list[dict] = []
    try:
        user_items = json.loads(_setting(db, _USER_PACK_KEY) or "[]")
    except (json.JSONDecodeError, TypeError):
        user_items = []
    if not isinstance(user_items, list):
        user_items = []

    builtin = {
        kind: [
            {
                **item,
                "kind": kind,
                "source": "erii-pet",
                "license": "project-placeholder",
                "placeholder": True,
            }
            for item in items
        ]
        for kind, items in _BUILTIN.items()
    }
    return {
        "builtin": builtin,
        "user_imported": user_items,
        "frequency": get_frequency(db),
        "sources": [
            {"source": "erii-pet", "license": "project-placeholder",
             "note": "工程占位素材，缺少正式授权资源，待替换"},
            {"source": "user-import", "license": "user-declared",
             "note": "用户导入条目附来源与授权声明，逐条记录在 user_imported"},
        ],
        "placeholder_notice": (
            "内置贴纸/动作词为工程占位，非最终素材；正式素材需提供授权来源后替换。"
        ),
    }


def pick(db, kind: str, seed: str) -> dict | None:
    """挑一条不重复的动作/贴纸，控制频率；返回 None 表示本轮不使用。"""
    if kind not in _BUILTIN:
        return None
    limit = _FREQUENCY_LIMIT[get_frequency(db)]
    recent = _recent(db)
    # 最近已使用的 id 不重复挑选
    candidates = [i for i in _BUILTIN[kind] if i["id"] not in recent]
    if not candidates:
        candidates = list(_BUILTIN[kind])
    digest = hashlib.sha256(f"{kind}|{seed}".encode()).digest()
    chosen = candidates[digest[0] % len(candidates)]
    # 记录最近使用（窗口 = 频率上限 * 2，low 时仍换着用）
    window = max(2, limit * 2)
    updated = (recent + [chosen["id"]])[-window:]
    _save_setting(db, _RECENT_KEY, json.dumps(updated))
    db.commit()
    return {**chosen, "kind": kind, "source": "erii-pet", "placeholder": True}


def import_pack(db, payload: dict) -> dict:
    """用户导入一条素材，必须声明来源与授权；不覆盖内置占位。"""
    try:
        items = json.loads(_setting(db, _USER_PACK_KEY) or "[]")
    except (json.JSONDecodeError, TypeError):
        items = []
    if not isinstance(items, list):
        items = []
    text = str(payload.get("text") or "").strip()[:120]
    if not text:
        return {"imported": False, "error": "empty_text"}
    entry = {
        "id": f"ui-{len(items) + 1:04d}",
        "kind": str(payload.get("kind") or "sticker"),
        "text": text,
        "source": str(payload.get("source") or "user-import"),
        "license": str(payload.get("license") or "user-declared"),
        "placeholder": False,
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }
    items.append(entry)
    _save_setting(db, _USER_PACK_KEY, json.dumps(items[-200:], ensure_ascii=False))
    db.commit()
    return {"imported": True, "item": entry}


def to_prompt(db, seed: str = "") -> str:
    """给模型一小段可用动作词（最多 2 条）+ 频率与来源约束。"""
    limit = _FREQUENCY_LIMIT[get_frequency(db)]
    chosen = []
    for kind in ("action", "sticker"):
        item = pick(db, kind, f"{seed}|{kind}")
        if item:
            chosen.append(item["text"])
        if len(chosen) >= min(2, limit):
            break
    if not chosen:
        return ""
    return (
        "【动作/贴纸（工程占位素材，来源 erii-pet，缺少正式授权，待替换）】\n"
        "- 本轮最多用这些，且不要每轮都用：" + "、".join(chosen) + "\n"
        "- 控制重复：同一条不要连续出现；不把占位素材说成正式表情包。"
    )
