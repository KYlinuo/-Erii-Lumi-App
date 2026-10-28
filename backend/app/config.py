"""Project LUMI - 集中式配置（全部来自环境变量，.env 不入库）。"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目录
BACKEND_ROOT = Path(__file__).resolve().parents[1]

# 依次尝试加载 backend/.env 与项目根 .env，已存在同名变量不会被覆盖
for _candidate in (BACKEND_ROOT / ".env", BACKEND_ROOT.parent / ".env"):
    if _candidate.is_file():
        load_dotenv(_candidate, override=False)


class Settings(BaseSettings):
    """所有配置项。None / empty 表示未配置，由调用方决定降级或报错。"""

    model_config = SettingsConfigDict(env_prefix="LUMI_", extra="ignore")

    # 运行环境
    env: str = "dev"

    # 服务器
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"

    # 数据库
    db_path: str = "data/lumi.db"

    # 单用户访问认证
    access_token: str | None = None

    # 限流
    rate_limit_per_minute: int = 30
    chat_rate_limit_per_minute: int = 10

    # 模型提供方（OpenAI 兼容）
    provider: str = "deepseek"
    provider_base_url: str = "https://api.deepseek.com"
    provider_model: str = "deepseek-chat"
    api_key: str | None = None
    provider_timeout_seconds: float = 60.0
    system_prompt: str = (
        "你是 LUMI，一个温柔、真诚、有自己想法的 AI 少女。"
        "用自然口语化的中文和用户交流，回答简洁但有温度。"
    )

    # ---- v0.3：语音 ----
    # 留空表示不接入，走 Mock（明确标注未接入，不假装识别成功）
    asr_model: str = ""
    tts_model: str = ""
    tts_voice: str = "alloy"

    # CORS
    cors_origins: str = ""

    # ---- v0.2：身份与设备 ----
    # 设备令牌做 SHA-256 存储时的服务端盐；未配置时回退为空字符串（仅适合单机自用）
    device_token_secret: str = "lumi-device-salt"

    # ---- v0.2：人格 ----
    default_character_key: str = "erii"
    # 启动时是否写入内置人格（林穗/祁鹿/沈昼/绘梨衣/LUMI）
    seed_characters: bool = True

    # ---- v0.2：长期记忆 ----
    # 每次请求注入模型的最大记忆条数
    memory_injection_limit: int = 8
    # 是否允许模型自动抽取记忆（关闭则只能由用户显式写入）
    memory_auto_extract: bool = True
    memory_confidence_inferred: float = 0.55
    memory_confidence_explicit: float = 0.95

    # ---- v0.2：虚构人生与主动联系 ----
    # 虚构人生/主动联系默认关闭，避免产生非用户触发的内容
    proactive_enabled: bool = False
    proactive_daily_cap: int = 3
    # 允许发起主动联系的时段（本地时区，24h）
    proactive_windows: str = "09:00-12:00,18:00-23:00"
    # 夜间免打扰（此时段绝不主动联系）
    quiet_hours: str = "23:30-07:30"
    # 主动联系每日同一次最少间隔（分钟）
    proactive_min_interval_minutes: int = 120

    # 服务器本地时区（用于时段判断，内部仍按 UTC 存储）
    timezone: str = "Asia/Shanghai"

    # 上游模型调用的最大重试次数（不含首次）
    provider_max_retries: int = 2

    @property
    def is_production(self) -> bool:
        return self.env.lower() in ("prod", "production")

    @property
    def auth_required(self) -> bool:
        """生产环境强制认证；开发环境未配置 token 时允许裸奔（仅本地）。"""
        return self.is_production or bool(self.access_token)

    @property
    def resolved_db_path(self) -> Path:
        p = Path(self.db_path)
        if not p.is_absolute():
            p = BACKEND_ROOT / p
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    """测试用：丢弃缓存重新读取环境变量。"""
    get_settings.cache_clear()
    return get_settings()


def mask_secret(value: str | None) -> str:
    """日志/接口展示时对密钥做脱敏。"""
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def env_flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in ("1", "true", "yes", "on")
