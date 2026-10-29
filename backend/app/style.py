"""回复风格调节（需求 09）。

可设置：回复长度、提问频率、表情频率、动作描写、称呼。
- 所有调节仍受绘梨衣核心性格约束（在 compose_system_prompt 里叠加，不覆盖人格设定）；
- 参数带版本号，避免每次启动重置；未设置时回落默认值；
- 持久化在 `app_settings` 表（key-value），跨重启保留。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

# 参数版本：变更结构时 +1，读取时按版本迁移/回落，避免旧数据破坏。
STYLE_VERSION = 1

_LENGTHS = ("short", "medium", "long")
_FREQUENCIES = ("low", "medium", "high")


@dataclass
class StyleProfile:
    reply_length: str = "medium"       # short / medium / long
    question_frequency: str = "medium"  # low / medium / high
    emoji_frequency: str = "medium"    # low / medium / high
    action_description: bool = True    # 动作描写（*她低下头*）
    address: str = ""                  # 称呼（空 = 用默认称呼）

    def validate(self) -> "StyleProfile":
        if self.reply_length not in _LENGTHS:
            self.reply_length = "medium"
        if self.question_frequency not in _FREQUENCIES:
            self.question_frequency = "medium"
        if self.emoji_frequency not in _FREQUENCIES:
            self.emoji_frequency = "medium"
        self.address = (self.address or "").strip()[:20]
        return self

    def to_dict(self) -> dict:
        self.validate()
        return {"version": STYLE_VERSION, **asdict(self)}

    def to_prompt(self) -> str:
        """把风格约束转成一小段 system 提示，叠加在人格设定之后。"""
        self.validate()
        lines: list[str] = []

        length_hint = {
            "short": "回复尽量短，一两句就好，不要展开。",
            "medium": "回复长度适中，该说清楚时说清楚，不刻意凑字数。",
            "long": "可以多写一点，把感受和细节说完整。",
        }[self.reply_length]
        lines.append(f"- 回复长度：{length_hint}")

        question_hint = {
            "low": "尽量少提问，多顺着对方的话往下说，不要每句都反问。",
            "medium": "可以适当提问，但不要连续追问。",
            "high": "可以多问一点，多关心对方在想什么。",
        }[self.question_frequency]
        lines.append(f"- 提问：{question_hint}")

        emoji_hint = {
            "low": "几乎不用表情符号。",
            "medium": "偶尔用一两个表情符号。",
            "high": "可以多用表情符号表达情绪。",
        }[self.emoji_frequency]
        lines.append(f"- 表情：{emoji_hint}")

        if self.action_description:
            lines.append("- 动作：可以用星号写一点小动作（比如 *她低头看本子*），但别太多。")
        else:
            lines.append("- 动作：少写动作描写，多写对话本身。")

        if self.address:
            lines.append(f"- 称呼：称呼对方为「{self.address}」。")

        return "【你当前的表达方式（这是用户的可调偏好，不是你的性格本身）】\n" + "\n".join(lines)


def load_from_json(raw: str | None) -> StyleProfile:
    """从 app_settings 读回风格参数；坏数据/旧版本安全回落默认。"""
    if not raw:
        return StyleProfile()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return StyleProfile()
    if not isinstance(data, dict):
        return StyleProfile()
    return StyleProfile(
        reply_length=str(data.get("reply_length", "medium")),
        question_frequency=str(data.get("question_frequency", "medium")),
        emoji_frequency=str(data.get("emoji_frequency", "medium")),
        action_description=bool(data.get("action_description", True)),
        address=str(data.get("address", "")),
    ).validate()


_KEY = "style_profile"


def get_profile(db) -> StyleProfile:
    """读取当前风格参数（无则回落默认，不写库）。"""
    from app.models import AppSetting

    row = db.get(AppSetting, _KEY)
    return load_from_json(row.value if row else None)


def save_profile(db, profile: StyleProfile) -> StyleProfile:
    """保存风格参数（带版本号），跨重启保留。"""
    from app.models import AppSetting

    profile.validate()
    row = db.get(AppSetting, _KEY)
    if row is None:
        row = AppSetting(key=_KEY, value="")
        db.add(row)
    row.value = json.dumps(profile.to_dict(), ensure_ascii=False)
    db.flush()
    return profile
