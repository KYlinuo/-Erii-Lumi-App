"""启动自检与初始数据。

只在进程启动（FastAPI lifespan）与测试夹具里调用：
    1. 保证默认用户存在；
    2. 播种内置人格（已存在的 key 不覆盖，保护绘梨衣等既有设定）；
    3. 为每个已激活人格补齐最近几天的虚构生活（幂等，同一天不会写第二遍）。

这些都是**确定性**生成，不调用任何模型、不消耗任何额度。
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import personas, world
from app.identity import ensure_default_user
from app.memory import (
    SOURCE_WORLD,
    SUBJECT_CHARACTER,
    record as record_memory,
)
from app.models import Character, MemoryRecord

logger = logging.getLogger("erii.bootstrap")

# 每个角色播种的虚构生活背景（标 world_simulation，绝不当作用户真实信息）
# v2.x：只保留绘梨衣一个角色。
_FICTIONAL_SEEDS: dict[str, list[str]] = {
    "erii": [
        "她随身带一个小本子，想到什么就写下来。",
        "一天结束时会把「今天还不错的瞬间」悄悄收起来。",
    ],
}


def bootstrap(db: Session, *, days: int = 3) -> dict:
    """幂等初始化。返回本次做了什么的统计信息。"""
    stats: dict[str, int] = {}

    ensure_default_user(db)
    stats["user_ready"] = 1

    created = personas.seed_characters(db)
    db.flush()
    stats["characters_created"] = created

    characters: list[Character] = personas.list_characters(db)

    # 虚构生活背景（按 character_id 隔离，且永远标记为 world_simulation）
    seeded_memories = 0
    for character in characters:
        for line in _FICTIONAL_SEEDS.get(character.key, []):
            # 显式查重统计：`record()` 对已存在内容只更新，不能靠时间差判断新建
            existed = db.execute(
                select(MemoryRecord).where(
                    MemoryRecord.scope == "fictional_life",
                    MemoryRecord.subject == SUBJECT_CHARACTER,
                    MemoryRecord.character_id == character.id,
                    MemoryRecord.content == line,
                )
            ).scalar_one_or_none()
            record_memory(
                db,
                scope="fictional_life",
                content=line,
                user_id=None,  # 不是用户的信息
                character_id=character.id,
                subject=SUBJECT_CHARACTER,
                source_type=SOURCE_WORLD,
                source_ref=f"character:{character.key}",
                confidence=1.0,
                salience=6,
            )
            if existed is None:
                seeded_memories += 1
    db.flush()
    stats["fictional_memories"] = seeded_memories

    # 虚构世界时间线
    events = 0
    for character in characters:
        events += len(world.ensure_recent_days(db, character, days=days))
    db.flush()
    stats["world_events"] = events

    db.commit()
    logger.info("bootstrap done: %s", stats)
    return stats
