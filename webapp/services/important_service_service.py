from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from webapp.services.mongo_service import get_collection


DEFAULT_EXAMPLES = [
    {"name": "SSH 連線服務", "service_name": "sshd", "platform": "linux", "enabled": False, "owner": "Linux 管理者", "note": "RHEL / Rocky 常用 SSH service 名稱"},
    {"name": "SSH 連線服務 Debian", "service_name": "ssh", "platform": "linux", "enabled": False, "owner": "Linux 管理者", "note": "Debian / Ubuntu 常用 SSH service 名稱"},
    {"name": "排程服務", "service_name": "cron", "platform": "linux", "enabled": False, "owner": "Linux 管理者", "note": "Debian / Ubuntu 排程服務"},
    {"name": "排程服務 RHEL", "service_name": "crond", "platform": "linux", "enabled": False, "owner": "Linux 管理者", "note": "RHEL / Rocky 排程服務"},
    {"name": "系統日誌服務", "service_name": "rsyslog", "platform": "linux", "enabled": False, "owner": "Linux 管理者", "note": "如公司要求本機 rsyslog 才啟用"},
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _public(doc: dict[str, Any] | None) -> dict[str, Any]:
    if not doc:
        return {}
    return {key: value for key, value in doc.items() if key != "_id"}


def ensure_default_rules() -> None:
    col = get_collection("important_service_rules")
    if col.count_documents({}) > 0:
        return
    now = _now()
    for item in DEFAULT_EXAMPLES:
        rule_id = f"svc-{uuid4().hex[:8]}"
        col.insert_one({**item, "rule_id": rule_id, "created_at": now, "updated_at": now, "created_by": "system", "updated_by": "system"})


def list_rules(include_disabled: bool = True, platform: str = "") -> list[dict[str, Any]]:
    ensure_default_rules()
    query: dict[str, Any] = {}
    if not include_disabled:
        query["enabled"] = True
    if platform:
        query["platform"] = platform
    return [_public(row) for row in get_collection("important_service_rules").find(query).sort("updated_at", -1)]


def enabled_service_names(platform: str = "linux") -> list[str]:
    names: list[str] = []
    for rule in list_rules(include_disabled=False, platform=platform):
        name = str(rule.get("service_name") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def save_rule(data: dict[str, Any], user: str = "system") -> dict[str, Any]:
    rule_id = str(data.get("rule_id") or "").strip() or f"svc-{uuid4().hex[:8]}"
    service_name = str(data.get("service_name") or "").strip()
    if not service_name:
        raise ValueError("service_name is required")
    doc = {
        "rule_id": rule_id,
        "name": str(data.get("name") or "").strip()[:80] or service_name,
        "service_name": service_name[:120],
        "platform": str(data.get("platform") or "linux").strip() or "linux",
        "owner": str(data.get("owner") or "").strip()[:80],
        "note": str(data.get("note") or "").strip()[:500],
        "enabled": bool(data.get("enabled", True)),
        "updated_at": _now(),
        "updated_by": user,
    }
    get_collection("important_service_rules").update_one(
        {"rule_id": rule_id},
        {"$set": doc, "$setOnInsert": {"created_at": doc["updated_at"], "created_by": user}},
        upsert=True,
    )
    return doc


def set_rule_enabled(rule_id: str, enabled: bool, user: str = "system") -> bool:
    result = get_collection("important_service_rules").update_one(
        {"rule_id": rule_id},
        {"$set": {"enabled": bool(enabled), "updated_at": _now(), "updated_by": user}},
    )
    return result.matched_count == 1


def delete_rule(rule_id: str) -> bool:
    return get_collection("important_service_rules").delete_one({"rule_id": rule_id}).deleted_count == 1
