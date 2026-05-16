from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from webapp.services.mongo_service import get_collection


DEFAULT_SCOPE = "opening_log"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _public(doc: dict[str, Any] | None) -> dict[str, Any]:
    if not doc:
        return {}
    item = {key: value for key, value in doc.items() if key != "_id"}
    return item


def _expires_at(days: int | None) -> datetime | None:
    if not days:
        return None
    return _now() + timedelta(days=max(1, int(days)))


def list_rules(include_disabled: bool = True) -> list[dict[str, Any]]:
    query: dict[str, Any] = {}
    if not include_disabled:
        query["enabled"] = True
    rules = [_public(row) for row in get_collection("log_exception_rules").find(query).sort("updated_at", -1)]
    now = _now()
    for rule in rules:
        expires_at = rule.get("expires_at")
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
            rule["expires_at"] = expires_at
        rule["expired"] = bool(expires_at and expires_at < now)
    return rules


def save_rule(data: dict[str, Any], user: str = "system") -> dict[str, Any]:
    rule_id = str(data.get("rule_id") or "").strip() or f"logex-{uuid4().hex[:8]}"
    match_type = str(data.get("match_type") or "contains").strip()
    if match_type not in {"contains", "regex"}:
        match_type = "contains"
    enabled = bool(data.get("enabled", True))
    expires_days = data.get("expires_days")
    try:
        expires_days_int = int(expires_days) if str(expires_days or "").strip() else None
    except ValueError:
        expires_days_int = None
    doc = {
        "rule_id": rule_id,
        "name": str(data.get("name") or "").strip()[:80] or rule_id,
        "pattern": str(data.get("pattern") or "").strip(),
        "match_type": match_type,
        "scope": str(data.get("scope") or DEFAULT_SCOPE).strip() or DEFAULT_SCOPE,
        "reason": str(data.get("reason") or "").strip()[:500],
        "owner": str(data.get("owner") or "").strip()[:80],
        "enabled": enabled,
        "expires_at": _expires_at(expires_days_int),
        "updated_at": _now(),
        "updated_by": user,
    }
    if not doc["pattern"]:
        raise ValueError("pattern is required")
    if match_type == "regex":
        re.compile(doc["pattern"])
    get_collection("log_exception_rules").update_one(
        {"rule_id": rule_id},
        {"$set": doc, "$setOnInsert": {"created_at": doc["updated_at"], "created_by": user}},
        upsert=True,
    )
    return doc


def set_rule_enabled(rule_id: str, enabled: bool, user: str = "system") -> bool:
    result = get_collection("log_exception_rules").update_one(
        {"rule_id": rule_id},
        {"$set": {"enabled": bool(enabled), "updated_at": _now(), "updated_by": user}},
    )
    return result.matched_count == 1


def delete_rule(rule_id: str) -> bool:
    return get_collection("log_exception_rules").delete_one({"rule_id": rule_id}).deleted_count == 1


def _rule_active(rule: dict[str, Any], scope: str, now: datetime) -> bool:
    if not rule.get("enabled", True):
        return False
    if rule.get("scope") not in {scope, "all", ""}:
        return False
    expires_at = rule.get("expires_at")
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return not bool(expires_at and expires_at < now)


def _matches(rule: dict[str, Any], line: str) -> bool:
    pattern = str(rule.get("pattern") or "")
    if not pattern:
        return False
    if rule.get("match_type") == "regex":
        try:
            return bool(re.search(pattern, line, flags=re.IGNORECASE))
        except re.error:
            return False
    return pattern.lower() in line.lower()


def assess_lines(lines: list[str], scope: str = DEFAULT_SCOPE) -> dict[str, Any]:
    now = _now()
    try:
        rules = [rule for rule in list_rules(include_disabled=False) if _rule_active(rule, scope, now)]
    except Exception:
        rules = []
    matched_lines = []
    unmatched_lines = []
    matched_rule_ids: set[str] = set()
    matched_rule_names: set[str] = set()
    for line in lines:
        matched = [rule for rule in rules if _matches(rule, line)]
        if matched:
            matched_lines.append(line)
            for rule in matched:
                matched_rule_ids.add(str(rule.get("rule_id")))
                matched_rule_names.add(str(rule.get("name") or rule.get("rule_id")))
        else:
            unmatched_lines.append(line)
    return {
        "matched_lines": matched_lines,
        "unmatched_lines": unmatched_lines,
        "matched_rule_ids": sorted(matched_rule_ids),
        "matched_rule_names": sorted(matched_rule_names),
        "all_matched": bool(lines) and not unmatched_lines and bool(matched_lines),
        "has_match": bool(matched_lines),
    }
