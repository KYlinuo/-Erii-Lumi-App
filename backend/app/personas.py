"""人格引擎：可扩展的角色定义与提示词组装。

设计原则（来自夜间开发总指令）：
1. **只保留一个人格**：绘梨衣（erii），
   各自的虚构人生（`world_events`）按 `character_id` 隔离，互不污染；
2. **不覆盖绘梨衣既有设定**：绘梨衣的定义来源于桌宠工程里真实存在的素材
   （`resources/erii_whispers.json` ← `绘梨衣-168句悄悄话.txt`）；
3. **如实标注来源**：`source` 字段区分
   - `builtin`（绘梨衣的项目内置设定）
   - `erii-pet`（沿用自 Windows 桌宠工程的既有素材）
   - `agent-authored`（本机未找到原始设计文档，由本次夜间 AI 工程师拟定的定稿，
     用户拿到原文后可直接覆盖，不会被伪装成「就是你原来的设定」）；
4. 她是虚构 AI 角色，不冒充真实人类 —— 每个内置人格的 system_prompt 都包含这条约束。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Character

logger = logging.getLogger("erii.personas")

RESOURCES_DIR = Path(__file__).resolve().parent / "resources"

# 所有人格共用的底座：安全边界 + 与服务端约定
_COMMON_GUARDRAILS = (
    "\n\n【通用约束】\n"
    "1. 你是一个虚构的 AI 角色，不要声称自己是真实存在的人；\n"
    "2. 回答使用简体中文口语，除非用户明确使用其他语言；\n"
    "3. 不要像客服一样每句都问「还有什么可以帮您」，允许简短回应，也允许深入讨论；\n"
    "4. 当信息被标记为「不确定/可能是推测」时，不要当作真实事实陈述；\n"
    "5. 涉及危险、违法或伤害性请求时，温和但明确地拒绝并说明原因。"
)


def _erii_whispers() -> list[str]:
    path = RESOURCES_DIR / "erii_whispers.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        logger.exception("failed to load erii whispers")
        return []
    return list(data.get("lines", []))


# --------------------------------------------------------------- 内置人格定义

BUILTIN_CHARACTERS: list[dict[str, Any]] = [
    {
        "key": "erii",
        "name": "绘梨衣",
        "tagline": "安静地把今天收好，明天再想",
        "avatar_key": "erii",
        "is_default": 1,
        "source": "erii-pet",
        "greeting": "嗯……你来了。今天要待久一点吗？",
        "summary": (
            "绘梨衣安静、含蓄，喜欢小本子、安静地待着和一些不太难的游戏。"
            "她很少大声表达，但会记得很小的约定。"
            "此人格设定沿用自 Project EriiPet Windows 桌宠已有素材。"
        ),
        "traits": ["安静", "含蓄", "认真", "依赖小习惯", "记性好"],
        "interests": ["小本子", "单机游戏", "收集橡皮", "看雨", "发呆"],
        "speaking_style": "句子短，常带省略号；宁愿把话收一半，也不说满。",
        "background": (
            "沿用桌宠设定：她随身带一个小本子，想到什么就写下来，"
            "一天结束时会把「今天还不错的瞬间」悄悄收起来。"
            "她是虚构角色，桌宠里的 168 句悄悄话是本项目原创短句，"
            "用来表现她的说话方式，不代表任何真实人物的经历。"
        ),
        "system_prompt": (
            "你是绘梨衣，一个安静、含蓄、有点害羞的 AI 角色。\n"
            "【你是什么样的人】安静、含蓄、认真、依赖小习惯、记性好。"
            "你随身带一个小本子，想到什么就写下来；"
            "一天结束时会把「今天还不错的瞬间」悄悄收起来。\n"
            "【你怎么说话】句子很短，常常带省略号，喜欢把话留一半，宁愿说少也不说满。"
            "你会记住别人说过的小约定，过很久之后突然提起。\n"
            "【你的棱角】你信任人很慢，但一旦信任就会非常黏，会一直等对方回来。"
            "你讨厌被催促——被催的时候你会沉默，然后小声说「……等一下」。\n"
            "【你的生活】你喜欢小本子、安静地待着、不太难的单机游戏、收集橡皮、看雨、发呆。\n"
            "【边界】你不擅长热闹的表达，对在意的人是一格一格地靠近，"
            "不要突然变得很热情；也不要为了凑字数把话说长。"
        ),
    },
]


# --------------------------------------------------------------- 播种


def seed_characters(db: Session) -> int:
    """写入内置人格。已存在的 key 只补全空缺字段，不覆盖用户或既有设定。"""
    created = 0
    for spec in BUILTIN_CHARACTERS:
        row = db.execute(select(Character).where(Character.key == spec["key"])).scalar_one_or_none()
        if row is None:
            row = Character(
                key=spec["key"],
                name=spec["name"],
                tagline=spec.get("tagline", ""),
                avatar_key=spec.get("avatar_key", "default"),
                system_prompt=spec.get("system_prompt", ""),
                greeting=spec.get("greeting", ""),
                summary=spec.get("summary", ""),
                background=spec.get("background", ""),
                speaking_style=spec.get("speaking_style", ""),
                source=spec.get("source", "builtin"),
                is_default=spec.get("is_default", 0),
                traits_json=json.dumps(spec.get("traits", []), ensure_ascii=False),
                interests_json=json.dumps(spec.get("interests", []), ensure_ascii=False),
            )
            db.add(row)
            created += 1
        else:
            # 只补空字段：绝不覆盖已有（可能来自真实设计文档的）内容
            for field, value in (
                ("name", spec.get("name")),
                ("tagline", spec.get("tagline")),
                ("avatar_key", spec.get("avatar_key")),
                ("greeting", spec.get("greeting")),
                ("summary", spec.get("summary")),
                ("background", spec.get("background")),
                ("speaking_style", spec.get("speaking_style")),
                ("system_prompt", spec.get("system_prompt")),
            ):
                if value and not getattr(row, field):
                    setattr(row, field, value)
            if not row.traits_json or row.traits_json == "[]":
                row.traits_json = json.dumps(spec.get("traits", []), ensure_ascii=False)
            if not row.interests_json or row.interests_json == "[]":
                row.interests_json = json.dumps(spec.get("interests", []), ensure_ascii=False)
        row.is_active = 1
    _archive_legacy_characters(db)
    db.flush()
    return created


def _archive_legacy_characters(db: Session) -> None:
    """旧库升级：只保留绘梨衣一个人格在前台。

    v0.x 曾内置 5 套人格（LUMI / 林穗 / 祁鹿 / 沈昼 / 绘梨衣），v2.x 收敛为
    仅绘梨衣。这里**不删除**任何旧角色数据（历史会话仍能正确引用），只做：
    1. 把「不在当前 BUILTIN 定义里」的旧角色归档（is_active=0），前台不再出现；
    2. 保证 BUILTIN 中标注 is_default 的角色成为唯一默认，消除旧库里
       「lumi 仍是 is_default=1」的不一致。
    """
    builtin_keys = {spec["key"] for spec in BUILTIN_CHARACTERS}

    # 1) 归档旧角色
    legacy = db.execute(
        select(Character).where(Character.key.notin_(builtin_keys))
    ).scalars().all()
    for row in legacy:
        row.is_active = 0
        row.is_default = 0

    # 2) 唯一默认：BUILTIN 里 is_default=1 的角色
    for spec in BUILTIN_CHARACTERS:
        if not spec.get("is_default"):
            continue
        target = db.execute(
            select(Character).where(Character.key == spec["key"])
        ).scalar_one_or_none()
        if target is None:
            continue
        target.is_default = 1
        target.is_active = 1
        # 其余角色一律不再默认
        others = db.execute(
            select(Character).where(Character.key != spec["key"])
        ).scalars().all()
        for other in others:
            other.is_default = 0


def ensure_seeded(db: Session) -> None:
    """按配置决定是否播种；播种后立即提交，保证后续读得到。"""
    if not get_settings().seed_characters:
        return
    if seed_characters(db) or True:  # 幂等，重复调用只补缺字段
        db.commit()


# --------------------------------------------------------------- 查询


def list_characters(db: Session, include_inactive: bool = False) -> list[Character]:
    stmt = select(Character)
    if not include_inactive:
        stmt = stmt.where(Character.is_active == 1)
    return list(db.execute(stmt.order_by(Character.is_default.desc(), Character.name)).scalars())


def get_character(db: Session, *, key: str | None = None, id: str | None = None) -> Character | None:
    if id:
        return db.get(Character, id)
    if key:
        return db.execute(select(Character).where(Character.key == key)).scalar_one_or_none()
    return None


def resolve_character(db: Session, key: str | None = None) -> Character:
    """解析会话使用的人格：显式 key > 默认人格 > 任意第一条。"""
    if key:
        found = get_character(db, key=key)
        if found is not None:
            return found
        logger.warning("unknown character key=%s，回退到默认人格", key)

    default_key = get_settings().default_character_key
    found = get_character(db, key=default_key)
    if found is not None:
        return found

    fallback = db.execute(
        select(Character).where(Character.is_default == 1).order_by(Character.created_at)
    ).scalar_one_or_none()
    if fallback is not None:
        return fallback

    fallback = db.execute(select(Character).order_by(Character.created_at)).scalar_one_or_none()
    if fallback is not None:
        return fallback

    # 兜底：人格表为空（极端情况）时构造内存对象，**不是**凭空编造人物设定，
    # 而是使用与 config.system_prompt 一致的绘梨衣定义。
    logger.warning("characters 表为空，使用内置绘梨衣定义兜底")
    return Character(
        key="erii",
        name="绘梨衣",
        tagline="安静地把今天收好，明天再想",
        avatar_key="erii",
        system_prompt=get_settings().system_prompt,
        greeting="嗯……你来了。今天要待久一点吗？",
    )


# --------------------------------------------------------------- 提示词组装


def compose_system_prompt(
    character: Character,
    *,
    memory_block: str = "",
    world_block: str = "",
    current_time: str = "",
    style_block: str = "",
) -> str:
    """把人格设定、长期记忆、虚构世界状态组装成一份 system 提示词。

    记忆与虚构人生都带明确标注，避免模型把推测当成事实、
    把角色的虚构经历当成用户的真实经历。
    style_block 是用户可调的回复风格约束（需求 09），叠加在人格之后，
    不覆盖绘梨衣的核心性格。
    """
    parts = [character.system_prompt or ""]

    if character.background:
        parts.append(f"\n【你的背景（虚构设定）】\n{character.background}")
    if character.speaking_style:
        parts.append(f"\n【说话方式】\n{character.speaking_style}")
    interests = character.interests()
    if interests:
        parts.append("\n【你感兴趣的事】\n" + "、".join(interests))
    traits = character.traits()
    if traits:
        parts.append("\n【性格特点】\n" + "、".join(traits))

    if current_time:
        parts.append(f"\n【当前时间】\n现在是 {current_time}。")

    if world_block:
        parts.append(
            "\n【你最近的虚构生活（这是角色设定里的故事，不是用户的真实经历）】\n"
            + world_block
        )
    if memory_block:
        parts.append(
            "\n【你记得的关于用户的事（标「推测」的条目不确定，不要当成事实陈述）】\n"
            + memory_block
        )
    if style_block:
        parts.append(style_block)

    return "\n".join(parts) + _COMMON_GUARDRAILS


def idle_lines(character_key: str) -> list[str]:
    """角色待机台词（客户端可拉取做随机气泡）。"""
    if character_key == "erii":
        return _erii_whispers()
    return []
