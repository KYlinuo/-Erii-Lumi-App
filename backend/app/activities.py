"""阶段 E 核心逻辑（需求 23–30）+ 阶段 G 的桌宠协议契约（35）。

包含：临时会话管理、完整备份/恢复（含完整性校验与可选加密）、主动联系
运行时设置、学习计时、一起读书、共同小活动、日记留言、小组件数据接口，
以及 iPhone—桌宠接续的协议契约定义。

诚实边界：
- 备份「加密选项」依赖 cryptography(Fernet)；当前环境未安装时导出明文并
  明确标注 encrypted=false，不伪称已加密；
- 小组件扩展签名与共享容器属于用户签名方案外部条件，标注 blocked；
- APNs 远程推送在免费自签下不可用，只实现服务端排队 + 客户端补拉。
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select

from app import companion as C
from app import personas, world
from app.config import get_settings
from app.database import schema_version
from app.models import (
    Character,
    User,
    ActivitySession,
    AppSetting,
    Conversation,
    DiaryNote,
    MediaAsset,
    MemoryRecord,
    Message,
    ProactiveMessage,
    Promise,
    ReadingProgress,
    StickyNote,
    StudySession,
    TimelineEvent,
    TopicArchive,
    UTCDateTime,
    WorldEvent,
)

try:  # 可选加密依赖：未安装时如实降级为明文 + 完整性校验
    from cryptography.fernet import Fernet

    _FERNET = True
except ImportError:  # pragma: no cover - 取决于部署环境
    _FERNET = False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _get(db, key: str, default):
    row = db.get(AppSetting, key)
    if row is None:
        return default
    try:
        value = json.loads(row.value)
    except (json.JSONDecodeError, TypeError):
        return default
    return value if isinstance(value, type(default)) else default


def _set(db, key: str, value, commit: bool = True) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value="")
        db.add(row)
    row.value = json.dumps(value, ensure_ascii=False)
    db.flush()
    if commit:
        db.commit()


# ================================================================ 23 临时聊天


EPHEMERAL_POLICY_KEY = "ephemeral_policy"


def ephemeral_policy(db) -> dict:
    data = _get(db, EPHEMERAL_POLICY_KEY, {})
    return {
        "on_exit": data.get("on_exit") if data.get("on_exit") in ("keep", "delete") else "delete",
        "notice": "临时聊天不进入长期记忆/日记/主动联系依据/多端同步；退出后按设置保留或删除。",
    }


def set_ephemeral_policy(db, on_exit: str) -> dict:
    if on_exit not in ("keep", "delete"):
        on_exit = "delete"
    _set(db, EPHEMERAL_POLICY_KEY, {"on_exit": on_exit})
    return ephemeral_policy(db)


def list_ephemeral(db) -> list[dict]:
    rows = db.execute(
        select(Conversation)
        .where(Conversation.is_ephemeral == 1)
        .order_by(Conversation.updated_at.desc())
    ).scalars().all()
    return [r.to_dict() for r in rows]


def delete_ephemeral(db, conversation_id: str) -> bool:
    conv = db.get(Conversation, conversation_id)
    if conv is None or not conv.is_ephemeral:
        return False
    db.delete(conv)  # messages 级联删除
    db.commit()
    return True


def apply_exit_policy(db) -> dict:
    """客户端退出临时聊天时调用：按设置清空临时会话（真正删除，不只是隐藏）。"""
    policy = ephemeral_policy(db)
    if policy["on_exit"] != "delete":
        return {"deleted": 0, "on_exit": "keep"}
    rows = db.execute(
        select(Conversation).where(Conversation.is_ephemeral == 1)
    ).scalars().all()
    for conv in rows:
        db.delete(conv)
    db.commit()
    return {"deleted": len(rows), "on_exit": "delete"}


# ================================================================ 24 备份 / 恢复

BACKUP_VERSION = 2
# 不备份 users / devices / characters：设备令牌与内置人格由目标端自己管理，
# 避免把私钥哈希和种子设定跨设备覆盖（明确写进 notice）。
_BACKUP_TABLES = (
    ("conversations", Conversation),
    ("messages", Message),
    ("memory_records", MemoryRecord),
    ("world_events", WorldEvent),
    ("media_assets", MediaAsset),
    ("proactive_messages", ProactiveMessage),
    ("app_settings", AppSetting),
    ("promises", Promise),
    ("timeline_events", TimelineEvent),
    ("topic_archives", TopicArchive),
    ("sticky_notes", StickyNote),
    ("activity_sessions", ActivitySession),
    ("study_sessions", StudySession),
    ("reading_progress", ReadingProgress),
    ("diary_notes", DiaryNote),
)


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _dump_table(db, model) -> list[dict]:
    out: list[dict] = []
    for row in db.execute(select(model)).scalars().all():
        item: dict = {}
        for column in model.__table__.columns:
            value = getattr(row, column.name)
            if isinstance(value, datetime):
                value = value.isoformat()
            item[column.name] = value
        out.append(item)
    return out


def _fernet(key: str):
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def build_backup(db, encrypt_key: str | None = None) -> dict:
    """全量导出聊天/记忆/约定/主题/便签/活动/设置 + 版本号 + SHA-256 校验。"""
    data = {name: _dump_table(db, model) for name, model in _BACKUP_TABLES}
    # Portable identity references; never export credentials or device tokens.
    data["_identities"] = {"characters": {r.id: r.key for r in db.execute(select(Character)).scalars()}}
    ephemeral = {r["id"] for r in data["conversations"] if r.get("is_ephemeral")}
    temp_messages = {r["id"] for r in data["messages"] if r["conversation_id"] in ephemeral}
    temp_media = {r["media_id"] for r in data["messages"] if r["id"] in temp_messages and r.get("media_id")}
    data["conversations"] = [r for r in data["conversations"] if r["id"] not in ephemeral]
    data["messages"] = [r for r in data["messages"] if r["id"] not in temp_messages]
    for table in ("memory_records", "sticky_notes", "timeline_events"):
        data[table] = [r for r in data[table] if r.get("source_message_id") not in temp_messages and r.get("source_conversation_id") not in ephemeral]
    shared_media = {r.get("media_id") for r in data["messages"]}
    data["media_assets"] = [r for r in data["media_assets"] if r["id"] not in temp_media or r["id"] in shared_media]
    raw = _canonical(data)
    payload = {
        "version": BACKUP_VERSION,
        "schema": schema_version(),
        "exported_at": _now().isoformat(),
        "encrypted": False,
        "checksum": hashlib.sha256(raw).hexdigest(),
        "data": data,
        "tables": [name for name, _ in _BACKUP_TABLES],
        "notice": (
            "不含临时会话与媒体二进制（只含媒体元数据），不含用户凭据、设备与角色配置；"
            "密钥与 .env 不在备份内。"
        ),
        "encryption": {
            "offered": True,
            "method": "fernet-sha256" if _FERNET else "unavailable",
            "note": (
                "传入 encrypt_key 时使用 Fernet 加密载荷" if _FERNET
                else "当前环境未安装 cryptography，导出为明文；请依赖 TLS/本地加密，不伪称已加密。"
            ),
        },
    }
    if encrypt_key:
        if not _FERNET:
            raise ValueError("ENCRYPTION_UNAVAILABLE")
        ciphertext = _fernet(encrypt_key).encrypt(raw).decode("ascii")
        payload = {
            **payload,
            "encrypted": True,
            "ciphertext": ciphertext,
            "checksum": hashlib.sha256(ciphertext.encode("ascii")).hexdigest(),
            "data": None,
            "notice": payload["notice"] + " 本包载荷已用 Fernet 加密，恢复需同一 encrypt_key。",
        }
    return payload


class BackupError(ValueError):
    pass


def _decode_backup(payload: dict, encrypt_key: str | None) -> tuple[dict, dict]:
    """校验版本/完整性并解出 data；返回 (data, meta)。"""
    if not isinstance(payload, dict) or type(payload.get("version")) is not int or not 1 <= payload["version"] <= BACKUP_VERSION:
        raise BackupError("备份版本不兼容或格式无效。")
    meta = {
        "version": payload.get("version"),
        "encrypted": bool(payload.get("encrypted")),
        "exported_at": payload.get("exported_at"),
    }
    if payload.get("encrypted"):
        if not _FERNET or not encrypt_key:
            raise BackupError("该备份已加密：需要 encrypt_key 且服务端安装 cryptography。")
        ciphertext = str(payload.get("ciphertext") or "")
        if not ciphertext.isascii() or not isinstance(encrypt_key, str):
            raise BackupError("加密载荷格式无效。")
        if hashlib.sha256(ciphertext.encode("ascii")).hexdigest() != payload.get("checksum"):
            raise BackupError("完整性校验失败：密文被篡改。")
        try:
            raw = _fernet(encrypt_key).decrypt(ciphertext.encode("ascii"))
            data = json.loads(raw.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise BackupError("解密失败：encrypt_key 不正确或数据损坏。") from exc
    else:
        data = payload.get("data")
        if not isinstance(data, dict):
            raise BackupError("备份缺少 data 载荷。")
        if hashlib.sha256(_canonical(data)).hexdigest() != payload.get("checksum"):
            raise BackupError("完整性校验失败：数据被篡改。")
    if not isinstance(data, dict):
        raise BackupError("data 必须是对象。")
    for name, model in _BACKUP_TABLES:
        rows = data.get(name, [])
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            raise BackupError(f"{name} 必须是记录列表。")
        pk = "key" if model is AppSetting else "id"
        seen = set()
        for row in rows:
            key = row.get(pk)
            if not isinstance(key, str) or not key or key in seen:
                raise BackupError(f"{name} 包含缺失或重复的主键。")
            seen.add(key)
            for column in model.__table__.columns:
                if column.name not in row:
                    continue
                value = row[column.name]
                if value is None and not column.nullable:
                    raise BackupError(f"{name}.{column.name} 不允许空值。")
                if isinstance(column.type, UTCDateTime) and value is not None:
                    if not isinstance(value, str):
                        raise BackupError(f"{name}.{column.name} 日期格式无效。")
                    try:
                        datetime.fromisoformat(value.replace("Z", "+00:00"))
                    except ValueError as exc:
                        raise BackupError(f"{name}.{column.name} 日期格式无效。") from exc
    return data, meta


def _map_backup_identities(db, data: dict) -> dict:
    """Single-owner app: attach imported records to local owner and character keys."""
    import copy
    data = copy.deepcopy(data)
    owner = db.execute(select(User).order_by(User.created_at).limit(1)).scalar_one_or_none()
    chars = {c.key: c.id for c in db.execute(select(Character)).scalars()}
    char_ids = set(chars.values())
    identities = data.get("_identities", {})
    if not isinstance(identities, dict) or not isinstance(identities.get("characters", {}), dict):
        raise BackupError("身份映射格式无效。")
    source_chars = identities.get("characters", {})
    for name, _model in _BACKUP_TABLES:
        for row in data.get(name, []):
            if row.get("user_id"):
                if owner is None:
                    raise BackupError("请先初始化目标数据库的用户。")
                row["user_id"] = owner.id
            cid = row.get("character_id")
            if cid:
                key = source_chars.get(cid)
                if key is not None:
                    if not isinstance(key, str) or key not in chars:
                        raise BackupError("目标端缺少备份关联的人格。")
                    row["character_id"] = chars[key]
                elif cid not in char_ids:
                    raise BackupError("旧备份缺少人格映射，请从原服务重新导出。")
            if "origin_device_id" in row:
                row["origin_device_id"] = None
    conv_ids = set(db.execute(select(Conversation.id)).scalars()) | {r["id"] for r in data.get("conversations", [])}
    if any(r.get("conversation_id") not in conv_ids for r in data.get("messages", [])):
        raise BackupError("消息引用了不存在的会话。")
    return data


def preview_backup(db, payload: dict, encrypt_key: str | None = None) -> dict:
    """恢复预览：列出每个表将新增/已存在/冲突的记录，不写任何数据。"""
    meta: dict = {}
    try:
        data, meta = _decode_backup(payload, encrypt_key)
        data = _map_backup_identities(db, data)
    except BackupError as exc:
        return {"valid": False, "error": str(exc), "meta": meta}

    summary: dict[str, dict] = {}
    conflicts: list[dict] = []
    for name, model in _BACKUP_TABLES:
        rows = data.get(name) or []
        cols = {c.name: c for c in model.__table__.columns}
        pk = "key" if name == "app_settings" else "id"
        new = existing = 0
        for raw in rows:
            key = raw.get(pk)
            if not key:
                continue
            row = db.get(model, key)
            if row is None:
                new += 1
                continue
            existing += 1
            # 内容冲突：同名主键但至少一个非空字段不同
            for field, value in raw.items():
                if field == pk or field not in cols:
                    continue
                current = getattr(row, field, None)
                if isinstance(current, datetime):
                    current = current.isoformat()
                if str(current) != str(value):
                    conflicts.append({"table": name, pk: key, "field": field})
                    break
        summary[name] = {"total": len(rows), "new": new, "existing": existing}
    return {
        "valid": True,
        "meta": meta,
        "checksum_ok": True,
        "tables": summary,
        "conflicts": conflicts[:50],
        "strategy_hint": "skip=保留本机、只补缺失；overwrite=用备份覆盖同 id 记录",
    }


def _coerce_value(column, value):
    if isinstance(column.type, UTCDateTime) and isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return value


def _restore_table(db, model, rows: list[dict], strategy: str) -> dict:
    cols = {c.name: c for c in model.__table__.columns}
    pk = "key" if model is AppSetting else "id"
    created = updated = skipped = 0
    for raw in rows:
        key = raw.get(pk)
        if not key:
            continue
        existing = db.get(model, key)
        if existing is not None and strategy == "skip":
            skipped += 1
            continue
        fields: dict = {}
        for field, value in raw.items():
            if field not in cols:
                continue
            coerced = _coerce_value(cols[field], value)
            fields[field] = coerced
        if existing is not None:
            for field, value in fields.items():
                if field != pk:
                    setattr(existing, field, value)
            updated += 1
        else:
            db.add(model(**fields))
            created += 1
    db.flush()
    return {"created": created, "updated": updated, "skipped": skipped}


def apply_backup(db, payload: dict, *, strategy: str = "skip", encrypt_key: str | None = None) -> dict:
    """幂等恢复：以主键去重，重复恢复不产生重复记录；单事务，失败整体回滚。"""
    data, meta = _decode_backup(payload, encrypt_key)
    data = _map_backup_identities(db, data)
    if strategy not in ("skip", "overwrite"):
        raise BackupError("strategy 必须是 skip 或 overwrite。")
    results: dict[str, dict] = {}
    try:
        for name, model in _BACKUP_TABLES:
            results[name] = _restore_table(db, model, data.get(name) or [], strategy)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise BackupError("恢复失败，已整体回滚；请检查字段类型、关联记录和唯一性冲突。") from exc
    return {"applied": True, "meta": meta, "strategy": strategy, "tables": results}


# ================================================================ 25 主动联系设置

PROACTIVE_KEY = "proactive_settings"


def proactive_settings(db) -> dict:
    settings = get_settings()
    data = _get(db, PROACTIVE_KEY, {})
    return {
        "enabled": bool(data.get("enabled", settings.proactive_enabled)),
        "paused": bool(data.get("paused", False)),
        "windows": str(data.get("windows", settings.proactive_windows)),
        "daily_cap": int(data.get("daily_cap", settings.proactive_daily_cap)),
        "min_interval_minutes": int(data.get("min_interval_minutes", settings.proactive_min_interval_minutes)),
        "source": "app_settings" if data else "env",
        "notice": "服务器排队 + App 打开补拉已实现；本地通知/APNs 在免费自签下不可用。",
    }


def set_proactive_settings(db, payload: dict) -> dict:
    current = proactive_settings(db)
    merged = {
        "enabled": bool(payload.get("enabled", current["enabled"])),
        "paused": bool(payload.get("paused", current["paused"])),
        "windows": str(payload.get("windows", current["windows"])),
        "daily_cap": max(1, min(20, int(payload.get("daily_cap", current["daily_cap"])))),
        "min_interval_minutes": max(10, int(payload.get("min_interval_minutes", current["min_interval_minutes"]))),
    }
    _set(db, PROACTIVE_KEY, merged)
    return proactive_settings(db)


def proactive_capability() -> dict:
    """分别标明四种投递能力的真实状态（不承诺后台常驻送达）。"""
    return {
        "server_queue": {"status": "implemented", "note": "服务端排队 pending，客户端下次同步补拉"},
        "app_pull": {"status": "implemented", "note": "App 冷启动/前台拉取 /proactive/pending"},
        "local_notification": {"status": "not_implemented", "note": "免费自签无法保证后台定时唤醒"},
        "apns": {"status": "blocked", "note": "需要付费开发者账号 + APNs 证书/密钥；当前签名方案不具备"},
        "note": "不承诺依靠后台常驻保证送达；多端重复由服务端 pending 去重与 deliver 幂等处理。",
    }


def expire_stale_proactive(db, hours: int = 24) -> int:
    """过期关心：超过 N 小时未投递的 pending 主动消息作废，避免迟到的打扰。"""
    cutoff = _now() - timedelta(hours=hours)
    rows = db.execute(
        select(ProactiveMessage).where(
            ProactiveMessage.status == "pending", ProactiveMessage.scheduled_at < cutoff
        )
    ).scalars().all()
    for row in rows:
        row.status = "cancelled"
    if rows:
        db.commit()
    return len(rows)


# ================================================================ 26 学习陪伴


def study_start(db, subject: str = "自习") -> dict:
    running = db.execute(
        select(StudySession).where(StudySession.status.in_(("running", "paused"))).limit(1)
    ).scalar_one_or_none()
    if running is not None:
        return _study_view(running)
    row = StudySession(subject=subject or "自习", status="running")
    db.add(row)
    db.commit()
    return _study_view(row)


def _study_view(row: StudySession) -> dict:
    data = row.to_dict()
    end = row.ended_at or _now()
    elapsed_ms = int((end - row.started_at).total_seconds() * 1000) - row.paused_ms
    if row.status == "paused" and row.paused_at is not None:
        elapsed_ms -= int((_now() - row.paused_at).total_seconds() * 1000)
    data["elapsed_ms"] = max(0, elapsed_ms)
    data["resumable"] = row.status in ("running", "paused")
    return data


def study_get(db, session_id: str) -> dict | None:
    row = db.get(StudySession, session_id)
    return _study_view(row) if row else None


def study_pause(db, session_id: str) -> dict | None:
    row = db.get(StudySession, session_id)
    if row is None or row.status != "running":
        return study_get(db, session_id)
    row.status = "paused"
    row.paused_at = _now()
    db.commit()
    return _study_view(row)


def study_resume(db, session_id: str) -> dict | None:
    row = db.get(StudySession, session_id)
    if row is None or row.status != "paused":
        return study_get(db, session_id)
    if row.paused_at is not None:
        row.paused_ms += int((_now() - row.paused_at).total_seconds() * 1000)
    row.paused_at = None
    row.status = "running"
    db.commit()
    return _study_view(row)


def study_end(db, session_id: str, note: str = "") -> dict | None:
    row = db.get(StudySession, session_id)
    if row is None:
        return None
    if row.status == "paused" and row.paused_at is not None:
        row.paused_ms += int((_now() - row.paused_at).total_seconds() * 1000)
        row.paused_at = None
    row.status = "done"
    row.ended_at = _now()
    row.note = note
    db.commit()
    return _study_view(row)


# ================================================================ 27 一起读书


def reading_list(db) -> list[dict]:
    rows = db.execute(select(ReadingProgress).order_by(ReadingProgress.updated_at.desc())).scalars().all()
    return [r.to_dict() for r in rows]


def reading_upsert(db, payload: dict) -> dict:
    book = str(payload.get("book") or "").strip()
    if not book:
        raise ValueError("书名不能为空")
    row = db.execute(
        select(ReadingProgress).where(ReadingProgress.book == book)
    ).scalar_one_or_none()
    if row is None:
        row = ReadingProgress(book=book)
        db.add(row)
    for field in ("chapter", "progress", "spoiler_limit", "notes"):
        if field in payload:
            setattr(row, field, str(payload[field]))
    db.commit()
    return row.to_dict()


def reading_delete(db, book: str) -> bool:
    row = db.execute(
        select(ReadingProgress).where(ReadingProgress.book == book)
    ).scalar_one_or_none()
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def reading_prompt(db) -> str:
    """剧透控制：只按已读范围讨论，原著资料与生成解读分开。"""
    rows = reading_list(db)[:1]
    if not rows:
        return ""
    r = rows[0]
    limit = r["spoiler_limit"] or r["progress"] or "未标注"
    return (
        "【一起读书（剧透控制）】\n"
        f"- 正在读《{r['book']}》，已到 {r['chapter'] or '未标注'}（{r['progress']}）；"
        f"只讨论 {limit} 之前的内容，不许越过。\n"
        "- 原著内容与你的解读分开说；不知道的直接说不确定，引用要能说出章节来源。"
    )


# ================================================================ 28 共同小活动

_ACTIVITY_KINDS = ("guess_word", "story_chain", "daily_question", "weekend_plan")
_ACTIVITY_SEEDS: dict[str, dict] = {
    "guess_word": {
        "word": "雨", "hints": ["……会从天上落下来", "……打在窗户上", "……她喜欢看"],
        "state": {"hints_shown": 0, "guessed": False},
    },
    "story_chain": {
        "state": {"lines": ["从前有一只总在窗边看雨的猫。"], "turn": 0},
    },
    "daily_question": {
        "state": {"question": "今天有没有一个还算不错的瞬间？", "answer": "", "answered": False},
    },
    "weekend_plan": {
        "state": {"items": [], "done": False},
    },
}


def activity_start(db, kind: str) -> dict:
    if kind not in _ACTIVITY_KINDS:
        raise ValueError("不支持的活动类型")
    active = db.execute(
        select(ActivitySession).where(
            ActivitySession.kind == kind, ActivitySession.status == "active"
        )
    ).scalar_one_or_none()
    if active is not None:
        return active.to_dict()
    import copy

    seed = copy.deepcopy(_ACTIVITY_SEEDS[kind])
    row = ActivitySession(kind=kind, state_json=json.dumps(seed["state"], ensure_ascii=False))
    db.add(row)
    db.commit()
    return row.to_dict()


def activity_get(db, session_id: str) -> dict | None:
    row = db.get(ActivitySession, session_id)
    return row.to_dict() if row else None


def activity_list(db) -> list[dict]:
    rows = db.execute(
        select(ActivitySession).order_by(ActivitySession.updated_at.desc()).limit(50)
    ).scalars().all()
    return [r.to_dict() for r in rows]


def activity_step(db, session_id: str, answer: str = "") -> dict | None:
    row = db.get(ActivitySession, session_id)
    if row is None:
        return None
    state = row.state()
    kind = row.kind
    text = (answer or "").strip()
    if kind == "guess_word":
        seed = _ACTIVITY_SEEDS[kind]
        hints = seed["hints"]
        if text == seed["word"]:
            state["guessed"] = True
            state["hints_shown"] = min(state.get("hints_shown", 0) + 1, len(hints))
        else:
            state["hints_shown"] = min(state.get("hints_shown", 0) + 1, len(hints))
        state["hint"] = hints[state["hints_shown"] - 1] if state["hints_shown"] else ""
    elif kind == "story_chain":
        if text:
            state.setdefault("lines", []).append(text[:120])
            state["turn"] = len(state["lines"])
    elif kind == "daily_question":
        state["answer"] = text[:200]
        state["answered"] = bool(text)
    elif kind == "weekend_plan":
        if text:
            state.setdefault("items", []).append(text[:80])
    row.state_json = json.dumps(state, ensure_ascii=False)
    db.commit()
    return row.to_dict()


def activity_finish(db, session_id: str, status: str = "done") -> dict | None:
    row = db.get(ActivitySession, session_id)
    if row is None:
        return None
    row.status = status if status in ("active", "paused", "done") else "done"
    db.commit()
    return row.to_dict()


def activity_prompt(db) -> str:
    """只在有 active 活动时注入；退出/结束后立即失效，不长期改变普通聊天模式。"""
    row = db.execute(
        select(ActivitySession).where(ActivitySession.status == "active").limit(1)
    ).scalar_one_or_none()
    if row is None:
        return ""
    state = row.state()
    hint = {
        "guess_word": f"猜词活动进行中（已给 {state.get('hints_shown', 0)} 个提示）",
        "story_chain": f"接故事进行中（已接 {state.get('turn', 0)} 句）",
        "daily_question": "每日小问题进行中",
        "weekend_plan": f"周末计划进行中（{len(state.get('items', []))} 项）",
    }.get(row.kind, "小活动进行中")
    return (
        "【正在进行的共同小活动（仅本轮有效，用户退出即结束）】\n"
        f"- {hint}；顺着活动状态接话，不要把这个模式带到普通聊天里。"
    )


# ================================================================ 29 日记与留言


def diary_notes(db, day: str | None = None) -> list[dict]:
    stmt = select(DiaryNote)
    if day:
        stmt = stmt.where(DiaryNote.day == day)
    rows = db.execute(stmt.order_by(DiaryNote.created_at.desc()).limit(200)).scalars().all()
    return [r.to_dict() for r in rows]


def add_diary_note(db, payload: dict) -> dict:
    content = str(payload.get("content") or "").strip()
    if not content:
        raise ValueError("留言不能为空")
    row = DiaryNote(
        day=str(payload.get("day") or _now().date().isoformat()),
        content=content[:1000],
        source_message_id=payload.get("source_message_id"),
    )
    db.add(row)
    db.commit()
    return row.to_dict()


def update_diary_note(db, note_id: str, content: str) -> dict | None:
    row = db.get(DiaryNote, note_id)
    if row is None:
        return None
    row.content = content[:1000]
    db.commit()
    return row.to_dict()


def delete_diary_note(db, note_id: str) -> bool:
    row = db.get(DiaryNote, note_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def diary_day(db, day: str) -> dict:
    """某天的日记视图：角色虚构日常 + 当天相关聊天 + 用户留言（分别管理）。"""
    try:
        target = date.fromisoformat(day)
    except ValueError:
        target = _now().date()
    start = datetime.combine(target, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    character = personas.resolve_character(db)
    events = [
        e.to_dict()
        for e in world.timeline(db, character.id, since=start, until=end, limit=50)
    ]
    messages = db.execute(
        select(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Message.created_at >= start,
            Message.created_at < end,
            Conversation.is_ephemeral == 0,
        )
        .order_by(Message.created_at.asc())
        .limit(100)
    ).scalars().all()
    return {
        "day": target.isoformat(),
        "simulated_events": events,
        "user_messages": [m.to_dict() for m in messages],
        "user_notes": diary_notes(db, target.isoformat()),
        "notice": "角色虚构日记 / 真实用户聊天 / 用户留言分别管理，不互相冒充。",
    }


def regenerate_diary(db, day: str) -> dict:
    """重新生成某天虚构日记：先删当天事件再生成（幂等，返回新条数）。"""
    try:
        target = date.fromisoformat(day)
    except ValueError:
        target = _now().date()
    start = datetime.combine(target, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    character = personas.resolve_character(db)
    rows = db.execute(
        select(WorldEvent).where(
            WorldEvent.character_id == character.id,
            WorldEvent.occurred_at >= start,
            WorldEvent.occurred_at < end,
        )
    ).scalars().all()
    for row in rows:
        db.delete(row)
    db.commit()
    created = world.simulate_day(
        db, character, target, max_events=2, mode=C.get_mode(db)["mode"]
    )
    db.commit()
    return {"day": target.isoformat(), "regenerated": len(created), "deleted": len(rows)}


# ================================================================ 30 小组件


def widget_summary(db, *, privacy: bool = False) -> dict:
    notes = C.list_notes(db, limit=3)
    promises = db.execute(
        select(Promise).where(Promise.status == "pending").order_by(Promise.updated_at.desc()).limit(3)
    ).scalars().all()
    latest_note = db.execute(
        select(DiaryNote).order_by(DiaryNote.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    capability = {
        "extension_signing": "blocked",
        "shared_container": "blocked",
        "system_refresh": "limited",
        "note": "小组件扩展需要 App Group/共享容器与扩展签名；当前自签方案不具备，不保证持续实时刷新。",
    }
    if privacy:
        return {
            "privacy": True,
            "counts": {"notes": len(notes), "promises": len(promises), "diary_notes": 1 if latest_note else 0},
            "capability": capability,
        }
    return {
        "privacy": False,
        "notes": notes,
        "promises": [p.to_dict() for p in promises],
        "latest_diary_note": latest_note.to_dict() if latest_note else None,
        "capability": capability,
    }


# ================================================================ 35 桌宠协议契约


BRIDGE_CONTRACT = {
    "version": 1,
    "identity": "同一后端 / 同一 user_id / 同一 character key（erii）；每台设备独立 token",
    "idempotency": {
        "user_message": "request_id 全局唯一索引（ux_messages_request_id）",
        "reply": "request_id#reply 精确绑定，不靠序号推断",
        "segments": "request_id#s{index} 稳定分条 ID（需求 08）",
        "notification": "同 content 的 pending 主动消息不重复入队；deliver 幂等",
    },
    "pagination": "POST /api/v1/sync 带 since_map{conv_seq} + has_more；DELETE 用 deleted_at tombstone 传播",
    "conflict_rule": "同 id 以服务端 conv_seq/updated_at 为准；客户端不得本地改写服务端 id",
    "ephemeral": "is_ephemeral=1 的会话不进入多端同步（需求 23）",
    "desktop_status": "桌宠端为 Electron 发布包、无源码，桌宠端验收明确列为待完成",
    "migration": "旧库原地升级（schema_migrations 版本链），不删库；设备令牌由各端自行配对",
    "acceptance_scenario_8": "两端同时在线：同一 request_id 只产生一条回复，deliver 幂等不重复投递",
}


def bridge_contract() -> dict:
    return BRIDGE_CONTRACT
