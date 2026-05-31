from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING

from webapp.services.mongo_service import get_collection


ALLOWED_PARAMS = {"q", "status", "group_name", "environment", "host_type", "dc", "page_size"}
FILTER_PARAMS = {"q", "status", "group_name", "environment", "host_type", "dc"}
FILTER_LABELS = {
    "q": "search",
    "status": "status",
    "group_name": "group",
    "environment": "environment",
    "host_type": "type",
    "dc": "dc",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean_params(params: dict[str, Any]) -> dict[str, str]:
    return {key: str(value) for key, value in params.items() if key in ALLOWED_PARAMS and value not in (None, "")}


def list_views(owner: str) -> list[dict[str, Any]]:
    docs = get_collection("saved_views").find({"owner": owner}, {"_id": 0}).sort("name", ASCENDING)
    return list(docs)


def save_view(owner: str, name: str, params: dict[str, Any]) -> dict[str, Any]:
    clean_name = name.strip()
    cleaned = _clean_params(params)
    if not any(cleaned.get(key) for key in FILTER_PARAMS):
        raise ValueError("至少要先輸入搜尋字或選擇篩選條件，才能儲存常用篩選")
    if not clean_name:
        parts = [
            f"{FILTER_LABELS.get(key, key)}={cleaned[key]}"
            for key in ("q", "status", "group_name", "environment", "host_type", "dc")
            if cleaned.get(key)
        ]
        clean_name = " / ".join(parts) or "saved-view"
    doc = {
        "owner": owner,
        "name": clean_name[:60],
        "params": cleaned,
        "updated_at": _now(),
    }
    get_collection("saved_views").update_one(
        {"owner": owner, "name": doc["name"]},
        {"$set": doc, "$setOnInsert": {"created_at": doc["updated_at"]}},
        upsert=True,
    )
    return doc


def delete_view(owner: str, name: str) -> bool:
    result = get_collection("saved_views").delete_one({"owner": owner, "name": name})
    return result.deleted_count == 1
