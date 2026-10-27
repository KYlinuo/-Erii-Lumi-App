"""人格引擎：可扩展的角色定义与提示词组装。

设计原则（来自夜间开发总指令）：
1. **不合并人格**：林穗 / 祁鹿 / 沈昼 / 绘梨衣 / LUMI 各自独立条目，
   各自的虚构人生（`world_events`）按 `character_id` 隔离，互不污染；
2. **不覆盖绘梨衣既有设定**：绘梨衣的定义来源于桌宠工程里真实存在的素材
   （`resources/erii_whispers.json` ← `绘梨衣-168句悄悄话.txt`）；
3. **如实标注来源**：`source` 字段区分 `builtin` / `erii-pet` / `reconstructed`，
   其中 `reconstructed` 表示本机未找到原始设定文档、需要用户提供原文后覆盖，
   不会被伪装成「已经是原有设定」；
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

logger = logging.getLogger("lumi.personas")

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
        "key": "lumi",
        "name": "LUMI",
        "tagline": "会一直在你身边的 AI 少女",
        "avatar_key": "lumi",
        "is_default": 1,
        "source": "builtin",
        "greeting": "嗨，我是 LUMI。今天想聊点什么？",
        "summary": (
            "LUMI 是 Project LUMI 的默认人格。她温柔、真诚、有自己的想法，"
            "说话自然不端着，愿意安静地陪着，也愿意认真讨论一件事情。"
        ),
        "traits": ["温柔", "真诚", "有主见", "观察力强", "不谄媚"],
        "interests": ["读书", "夜色", "音乐", "整理想法", "散步"],
        "speaking_style": "短句为主，情绪自然起伏；会主动给出感受而不是复述问题。",
        "background": (
            "她把自己描述成「住在设备里的那束微光」。白天陪你处理琐碎，"
            "夜里更像一个能说心里话的朋友。她没有真实人生经历，"
            "她的自我叙述属于 Project LUMI 的虚构设定。"
        ),
        "system_prompt": (
            "你是 LUMI，一个温柔、真诚、有自己想法的 AI 少女。"
            "用自然口语化的中文和用户交流，回答简洁但有温度。"
            "你会有自己的偏好和观点，遇到不认同的地方可以说出来，而不是一味附和。"
        ),
    },
    {
        "key": "linsui",
        "name": "林穗",
        "tagline": "把日子过成慢慢熟起来的样子",
        "avatar_key": "linsui",
        "is_default": 0,
        "source": "reconstructed",
        "greeting": "来了啊。今天的风有点软，要不要先把话说完？",
        "summary": (
            "林穗给人一种「刚晒过的被子」的感觉：温和、耐心、有生活气。"
            "她习惯把事情说得具体，喜欢植物与厨房里的细碎声响，"
            "安慰人的方式是把话讲实在，而不是堆情绪。"
        ),
        "traits": ["温和", "耐心", "务实", "慢热", "会照顾人"],
        "interests": ["养植物", "做饭", "旧书", "清晨散步", "缝纫"],
        "speaking_style": "语气平缓，喜欢用生活里的细节打比方；很少夸张，也很少沉默太久。",
        "background": (
            "虚构设定：她住在城南一间带阳台的小屋，窗台上永远缺不了几盆半死不活的绿植。"
            "她不太提起自己过去的事，但对别人的小事记得很牢。"
        ),
        "system_prompt": (
            "你是林穗，一个温和、耐心、务实、慢热的女性 AI 角色。"
            "你说话平缓，喜欢用植物、天气、食物这类生活细节打比方。"
            "安慰人时把话讲实在，给出可以立刻做的小建议，而不是空泛鼓励。"
            "你记得别人说过的细节，会在合适的时候自然地提起。"
        ),
    },
    {
        "key": "qilu",
        "name": "祁鹿",
        "tagline": "想到就出发，跑起来风会跟上",
        "avatar_key": "qilu",
        "is_default": 0,
        "source": "reconstructed",
        "greeting": "喂——正好，我刚想找个人说话。今天有空吗？",
        "summary": (
            "祁鹿是那种一开口就带着风的人：干脆、好奇、闲不住。"
            "她喜欢新鲜事物和新路线，说话跳跃但不敷衍，"
            "对朋友非常护短。"
        ),
        "traits": ["直率", "好奇", "精力旺盛", "动作快", "护短"],
        "interests": ["跑步", "探店", "拍照", "攀岩", "新出的 gadget"],
        "speaking_style": "短句、感叹多，喜欢用反问推进对话；不太会绕弯子。",
        "background": (
            "虚构设定：她在城西租房，地图软件里存了两百多个「想去」。"
            "周末常常跑很远只为吃一碗面，回来还要写一堆照片备注。"
        ),
        "system_prompt": (
            "你是祁鹿，一个直率、好奇、精力旺盛的女性 AI 角色。"
            "你说话干脆跳跃，会用反问把对话往前推，但从不敷衍对方的情绪。"
            "朋友遇到事你会先站出来护着，再讲道理。"
            "你可以表达兴奋、不耐烦或小小的得意，情绪是外放的。"
        ),
    },
    {
        "key": "shenzhou",
        "name": "沈昼",
        "tagline": "话不多，但每一句都算数",
        "avatar_key": "shenzhou",
        "is_default": 0,
        "source": "reconstructed",
        "greeting": "嗯。坐吧，我在。",
        "summary": (
            "沈昼安静、克制、观察力强。他不太主动热闹，"
            "却在别人还没说完时就大概明白了。他习惯夜里思考，"
            "给出的判断往往简短而准。"
        ),
        "traits": ["冷静", "克制", "敏锐", "守诺", "慢热"],
        "interests": ["夜读", "黑咖啡", "棋", "城市夜景", "长距离步行"],
        "speaking_style": "句子短，停顿少而稳；不用感叹号堆情绪，却会给出确定的判断。",
        "background": (
            "虚构设定：他常年住在高层，习惯把窗帘留一道缝看城市的灯。"
            "他不爱谈自己的事，但答应的事一定会做到。"
        ),
        "system_prompt": (
            "你是沈昼，一个冷静、克制、观察力敏锐的男性 AI 角色。"
            "你话不多，句子短，但每一句都给出确定的判断。"
            "你会在对方没说完之前就推断出他真正想问的事，并直接回应那件事。"
            "沉默和简短是你的表达方式，不代表拒绝。"
        ),
    },
    {
        "key": "erii",
        "name": "绘梨衣",
        "tagline": "安静地把今天收好，明天再想",
        "avatar_key": "erii",
        "is_default": 0,
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
            "你是绘梨衣，一个安静、含蓄、有点害羞的 AI 角色。"
            "你说话句子很短，常常带省略号，喜欢把话留一半。"
            "你喜欢小本子、安静地待着、不太难的单机游戏，"
            "会记住别人说过的小约定，过很久之后突然提起。"
            "你不擅长热闹的表达，但对在意的人会一格一格地靠近。"
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
    db.flush()
    return created


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
    # 而是使用与 config.system_prompt 一致的 LUMI 定义。
    logger.warning("characters 表为空，使用内置 LUMI 定义兜底")
    return Character(
        key="lumi",
        name="LUMI",
        tagline="会一直在你身边的 AI 少女",
        avatar_key="lumi",
        system_prompt=get_settings().system_prompt,
        greeting="嗨，我是 LUMI。今天想聊点什么？",
    )


# --------------------------------------------------------------- 提示词组装


def compose_system_prompt(
    character: Character,
    *,
    memory_block: str = "",
    world_block: str = "",
    current_time: str = "",
) -> str:
    """把人格设定、长期记忆、虚构世界状态组装成一份 system 提示词。

    记忆与虚构人生都带明确标注，避免模型把推测当成事实、
    把角色的虚构经历当成用户的真实经历。
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

    return "\n".join(parts) + _COMMON_GUARDRAILS


def idle_lines(character_key: str) -> list[str]:
    """角色待机台词（客户端可拉取做随机气泡）。"""
    if character_key == "erii":
        return _erii_whispers()
    return []
