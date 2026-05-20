from __future__ import annotations

from datetime import datetime, time
from typing import Optional
from zoneinfo import ZoneInfo

from webapp import config
from webapp.services.feature_flags import is_enabled


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(int(hour), int(minute))


def is_market_hours(now: Optional[datetime] = None) -> bool:
    if not is_enabled("market_hours_protection", default=True):
        return False
    tz = ZoneInfo(config.TZ_NAME)
    current = now.astimezone(tz) if now else datetime.now(tz)
    if current.weekday() >= 5:
        return False
    start = _parse_hhmm(config.MARKET_HOURS_START)
    end = _parse_hhmm(config.MARKET_HOURS_END)
    return start <= current.time() <= end


def can_mutate(role: str) -> bool:
    if role in {"super", "superadmin"}:
        return True
    if role == "admin":
        return not is_market_hours()
    return False
