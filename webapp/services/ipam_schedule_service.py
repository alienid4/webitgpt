from __future__ import annotations

from datetime import datetime, time
from typing import Any, Optional
from zoneinfo import ZoneInfo

from webapp.config import TZ_NAME
from webapp.services.mongo_service import get_collection


DEFAULT_SCHEDULE = {
    "enabled": True,
    "weekday": "mon",
    "time": "07:30",
    "timezone": TZ_NAME,
}

WEEKDAY_LABELS = {
    "mon": "週一",
    "tue": "週二",
    "wed": "週三",
    "thu": "週四",
    "fri": "週五",
    "sat": "週六",
    "sun": "週日",
}

WEEKDAY_INDEX = {key: index for index, key in enumerate(WEEKDAY_LABELS)}


def _settings_collection():
    return get_collection("settings")


def _now() -> datetime:
    return datetime.now(ZoneInfo(TZ_NAME))


def _normalize_weekday(value: str) -> str:
    value = (value or DEFAULT_SCHEDULE["weekday"]).strip().lower()
    if value not in WEEKDAY_INDEX:
        return DEFAULT_SCHEDULE["weekday"]
    return value


def _normalize_time(value: str) -> str:
    value = (value or DEFAULT_SCHEDULE["time"]).strip()
    try:
        parsed = time.fromisoformat(value)
    except ValueError:
        return DEFAULT_SCHEDULE["time"]
    return f"{parsed.hour:02d}:{parsed.minute:02d}"


def get_schedule() -> dict[str, Any]:
    doc = _settings_collection().find_one({"key": "ipam_reconcile_schedule"}, {"_id": 0}) or {}
    value = dict(DEFAULT_SCHEDULE)
    value.update(doc.get("value") or {})
    value["enabled"] = bool(value.get("enabled"))
    value["weekday"] = _normalize_weekday(str(value.get("weekday", "")))
    value["time"] = _normalize_time(str(value.get("time", "")))
    value["timezone"] = value.get("timezone") or TZ_NAME
    value["weekday_label"] = WEEKDAY_LABELS[value["weekday"]]
    value["display"] = f"{value['weekday_label']} {value['time']} {value['timezone']}"
    value["next_run"] = next_run_text(value)
    return value


def save_schedule(data: dict[str, Any], user: str = "system") -> dict[str, Any]:
    value = {
        "enabled": str(data.get("enabled", "")).lower() in ("1", "true", "yes", "on"),
        "weekday": _normalize_weekday(str(data.get("weekday", ""))),
        "time": _normalize_time(str(data.get("time", ""))),
        "timezone": TZ_NAME,
        "updated_at": _now(),
        "updated_by": user,
    }
    _settings_collection().update_one(
        {"key": "ipam_reconcile_schedule"},
        {"$set": {"key": "ipam_reconcile_schedule", "value": value}},
        upsert=True,
    )
    return get_schedule()


def mark_run(result: dict[str, Any]) -> None:
    schedule = get_schedule()
    today_key = _now().strftime("%Y-%m-%d")
    value = dict(schedule)
    value.update(
        {
            "last_run_date": today_key,
            "last_run_at": _now(),
            "last_result": {
                "count": result.get("count", 0),
                "status": result.get("status", ""),
            },
        }
    )
    _settings_collection().update_one(
        {"key": "ipam_reconcile_schedule"},
        {"$set": {"key": "ipam_reconcile_schedule", "value": value}},
        upsert=True,
    )


def should_run_now(now: Optional[datetime] = None) -> tuple[bool, str]:
    schedule = get_schedule()
    if not schedule.get("enabled"):
        return False, "IPAM 對帳排程已停用"
    now = now or _now()
    if now.weekday() != WEEKDAY_INDEX[schedule["weekday"]]:
        return False, f"今天不是設定日：{schedule['weekday_label']}"
    scheduled_time = time.fromisoformat(schedule["time"])
    current_minutes = now.hour * 60 + now.minute
    scheduled_minutes = scheduled_time.hour * 60 + scheduled_time.minute
    if current_minutes < scheduled_minutes:
        return False, f"尚未到設定時間：{schedule['time']}"
    today_key = now.strftime("%Y-%m-%d")
    if schedule.get("last_run_date") == today_key:
        return False, f"今天已執行：{schedule.get('last_run_at', '')}"
    return True, f"到達設定時間：{schedule['display']}"


def next_run_text(schedule: Optional[dict[str, Any]] = None) -> str:
    schedule = schedule or get_schedule()
    if not schedule.get("enabled", True):
        return "已停用"
    now = _now()
    target_index = WEEKDAY_INDEX[schedule["weekday"]]
    target_time = time.fromisoformat(schedule["time"])
    days = (target_index - now.weekday()) % 7
    candidate = now.replace(hour=target_time.hour, minute=target_time.minute, second=0, microsecond=0)
    if days == 0 and candidate <= now:
        days = 7
    candidate = candidate.replace(day=now.day) if days == 0 else candidate
    if days:
        from datetime import timedelta

        candidate = candidate + timedelta(days=days)
    return candidate.strftime("%Y-%m-%d %H:%M %z")
