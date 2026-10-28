"""Token 用量与成本估算。

数据来源就是 `messages` 表上的 `tokens_prompt` / `tokens_completion`，
不额外建表——一条消息花多少 token 本来就应该跟着消息走，
这样"这条回复为什么贵"随时能追回到具体某句话。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Message


def _day_start(day: datetime) -> datetime:
    return day.replace(hour=0, minute=0, second=0, microsecond=0)


def summarize(db: Session, *, now: datetime | None = None, days: int = 7) -> dict:
    settings = get_settings()
    now = now or datetime.now(timezone.utc)
    today = _day_start(now)
    since = today - timedelta(days=max(0, days - 1))

    def _sum(start: datetime) -> tuple[int, int, int]:
        row = db.execute(
            select(
                func.coalesce(func.sum(Message.tokens_prompt), 0),
                func.coalesce(func.sum(Message.tokens_completion), 0),
                func.count(Message.id),
            ).where(Message.created_at >= start, Message.role == "assistant")
        ).one()
        return int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)

    in_today, out_today, replies_today = _sum(today)
    in_week, out_week, replies_week = _sum(since)

    def cost(tin: int, tout: int) -> float:
        return round(
            tin / 1_000_000 * settings.price_input_per_mtok
            + tout / 1_000_000 * settings.price_output_per_mtok,
            6,
        )

    budget = max(0, settings.daily_token_budget)
    used = in_today + out_today
    return {
        "today": {
            "prompt_tokens": in_today,
            "completion_tokens": out_today,
            "total_tokens": used,
            "replies": replies_today,
            "cost_usd": cost(in_today, out_today),
        },
        "last_days": {
            "days": days,
            "prompt_tokens": in_week,
            "completion_tokens": out_week,
            "total_tokens": in_week + out_week,
            "replies": replies_week,
            "cost_usd": cost(in_week, out_week),
        },
        "budget": {
            "daily_token_budget": budget,
            "used": used,
            "remaining": max(0, budget - used) if budget else None,
            "exceeded": bool(budget) and used >= budget,
        },
        "pricing": {
            "input_per_mtok_usd": settings.price_input_per_mtok,
            "output_per_mtok_usd": settings.price_output_per_mtok,
            "note": "价格由配置给出，仅用于估算；实际以服务商账单为准。",
        },
        "provider": {
            "name": settings.provider,
            "model": settings.provider_model,
            "is_mock": settings.provider == "mock",
        },
    }
