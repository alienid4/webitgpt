from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pymongo import ASCENDING, DESCENDING

from webapp.services.host_dir_service import archive_dir, init_dir, restore_dir, write_meta
from webapp.services.host_schema import assert_valid_host_doc, normalize_host_doc
from webapp.services.mongo_service import get_collection


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _public(doc: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not doc:
        return None
    out = {k: v for k, v in doc.items() if k != "ssh_key"}
    if "_id" in out:
        out["_id"] = str(out["_id"])
    return out


def list_hosts(
    query: str = "",
    filters: Optional[dict[str, Any]] = None,
    page: int = 1,
    page_size: int = 25,
    sort: str = "hostname",
    direction: str = "asc",
) -> dict[str, Any]:
    filters = filters or {}
    mongo_filter: dict[str, Any] = {}
    for key in ("status", "group_name", "environment", "host_type", "dc"):
        value = filters.get(key)
        if value:
            mongo_filter[key] = normalize_host_doc({key: value}).get(key, value)
    if query:
        mongo_filter["$or"] = [
            {"asset_seq": {"$regex": query, "$options": "i"}},
            {"hostname": {"$regex": query, "$options": "i"}},
            {"ip": {"$regex": query, "$options": "i"}},
            {"ip_addresses": {"$regex": query, "$options": "i"}},
            {"network_segments": {"$regex": query, "$options": "i"}},
            {"asset_name": {"$regex": query, "$options": "i"}},
            {"system_name": {"$regex": query, "$options": "i"}},
        ]
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    sort_dir = ASCENDING if direction == "asc" else DESCENDING
    col = get_collection("hosts")
    total = col.count_documents(mongo_filter)
    docs = (
        col.find(mongo_filter, {"ssh_key": 0})
        .sort(sort, sort_dir)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": [_public(doc) for doc in docs],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def status_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in get_collection("hosts").aggregate([{"$group": {"_id": "$status", "count": {"$sum": 1}}}]):
        counts[str(item.get("_id") or "unknown")] = int(item.get("count", 0))
    counts["total"] = sum(counts.values())
    return counts


def _identity_query(key: str) -> dict[str, Any]:
    return {"$or": [{"hostname": key}, {"asset_seq": key}]}


def get_host(key: str) -> Optional[dict[str, Any]]:
    return _public(get_collection("hosts").find_one(_identity_query(key), {"ssh_key": 0}))


def create_host(doc: dict[str, Any], user: str = "system") -> dict[str, Any]:
    normalized = normalize_host_doc(doc)
    warnings = assert_valid_host_doc(normalized)
    now = _now()
    normalized.update(
        {
            "created_at": now,
            "updated_at": now,
            "created_by": user,
            "updated_by": user,
            "import_source": normalized.get("import_source", "manual"),
        }
    )
    existing = get_collection("hosts").find_one({"hostname": normalized["hostname"]})
    if existing:
        raise ValidationError([f"hostname already exists: {normalized['hostname']}"])
    get_collection("hosts").insert_one(normalized)
    init_dir(normalized)
    result = get_host(normalized["hostname"]) or {}
    result["_warnings"] = warnings
    return result


def update_host(asset_seq: str, changes: dict[str, Any], user: str = "system") -> dict[str, Any]:
    existing = get_collection("hosts").find_one(_identity_query(asset_seq))
    if not existing:
        raise KeyError(f"host not found: {asset_seq}")
    original_asset_seq = existing.get("asset_seq", asset_seq)
    merged = normalize_host_doc({**existing, **changes, "asset_seq": changes.get("asset_seq", original_asset_seq)})
    warnings = assert_valid_host_doc(merged)
    conflict = get_collection("hosts").find_one({"hostname": merged["hostname"], "_id": {"$ne": existing["_id"]}})
    if conflict:
        raise ValidationError([f"hostname already exists: {merged['hostname']}"])
    merged["updated_at"] = _now()
    merged["updated_by"] = user
    get_collection("hosts").replace_one({"_id": existing["_id"]}, merged)
    if merged.get("status") == "retired":
        archive_dir(original_asset_seq, existing.get("hostname"))
    else:
        init_dir(merged)
        write_meta(merged)
    result = get_host(merged["hostname"]) or {}
    result["_warnings"] = warnings
    return result


def delete_host(asset_seq: str, user: str = "system", soft: bool = True) -> bool:
    if soft:
        update_host(asset_seq, {"status": "retired"}, user=user)
        return True
    result = get_collection("hosts").delete_one(_identity_query(asset_seq))
    return result.deleted_count == 1


def record_lifecycle_event(host: dict[str, Any], action: str, reason: str, user: str) -> None:
    get_collection("host_lifecycle_events").insert_one(
        {
            "asset_seq": host.get("asset_seq"),
            "hostname": host.get("hostname"),
            "action": action,
            "reason": reason,
            "status": host.get("status"),
            "created_at": _now(),
            "created_by": user,
        }
    )


def transition_lifecycle(asset_seq: str, action: str, reason: str, user: str = "system") -> dict[str, Any]:
    reason = str(reason or "").strip()
    if not reason:
        raise ValueError("請填寫處理原因，方便日後稽核追蹤。")
    target_map = {
        "request_retire": "pending_retire",
        "retire": "retired",
        "disable": "disabled",
        "restore": "active",
    }
    if action not in target_map:
        raise ValueError("不支援的資產生命週期動作。")
    existing = get_collection("hosts").find_one(_identity_query(asset_seq))
    if not existing:
        raise KeyError(f"host not found: {asset_seq}")
    record_lifecycle_event(existing, action, reason, user)
    return update_host(
        asset_seq,
        {
            "status": target_map[action],
            "lifecycle_action": action,
            "lifecycle_reason": reason,
            "lifecycle_updated_at": _now(),
            "lifecycle_updated_by": user,
        },
        user=user,
    )


def delete_draft_host(asset_seq: str, reason: str, user: str = "system") -> bool:
    reason = str(reason or "").strip()
    if not reason:
        raise ValueError("刪除草稿前請填寫原因。")
    existing = get_collection("hosts").find_one(_identity_query(asset_seq))
    if not existing:
        raise KeyError(f"host not found: {asset_seq}")
    if normalize_host_doc(existing).get("status") != "draft":
        raise ValueError("只有草稿資產可以直接刪除；正式資產請走下線或汰除流程。")
    record_lifecycle_event(existing, "delete_draft", reason, user)
    return get_collection("hosts").delete_one({"_id": existing["_id"]}).deleted_count == 1


def bulk_delete_draft_hosts(keys: list[str], reason: str, user: str = "system") -> dict[str, Any]:
    reason = str(reason or "").strip()
    if not reason:
        raise ValueError("批次刪除草稿前請填寫原因。")
    unique_keys = [key.strip() for key in dict.fromkeys(keys) if str(key).strip()]
    result = {"deleted": [], "skipped": [], "deleted_count": 0, "skipped_count": 0}
    for key in unique_keys:
        existing = get_collection("hosts").find_one(_identity_query(key))
        if not existing:
            result["skipped"].append({"asset_seq": key, "reason": "找不到資產"})
            continue
        normalized = normalize_host_doc(existing)
        if normalized.get("status") != "draft":
            result["skipped"].append(
                {
                    "asset_seq": existing.get("asset_seq") or key,
                    "hostname": existing.get("hostname"),
                    "status": normalized.get("status"),
                    "reason": "不是草稿；正式資產請走下線或汰除流程",
                }
            )
            continue
        record_lifecycle_event(existing, "bulk_delete_draft", reason, user)
        deleted = get_collection("hosts").delete_one({"_id": existing["_id"]}).deleted_count == 1
        if deleted:
            result["deleted"].append({"asset_seq": existing.get("asset_seq"), "hostname": existing.get("hostname")})
        else:
            result["skipped"].append({"asset_seq": existing.get("asset_seq") or key, "reason": "刪除失敗"})
    result["deleted_count"] = len(result["deleted"])
    result["skipped_count"] = len(result["skipped"])
    return result


def restore_host(asset_seq: str, user: str = "system") -> dict[str, Any]:
    existing = get_collection("hosts").find_one(_identity_query(asset_seq))
    if not existing:
        raise KeyError(f"host not found: {asset_seq}")
    normalized_existing = normalize_host_doc(existing)
    if normalized_existing.get("status") == "retired":
        try:
            restore_dir(asset_seq)
        except FileNotFoundError:
            pass
    return update_host(asset_seq, {"status": "active"}, user=user)


def upsert_host(doc: dict[str, Any], user: str = "system") -> dict[str, Any]:
    key = doc.get("hostname") or doc.get("asset_seq")
    if key and get_collection("hosts").find_one(_identity_query(key)):
        return update_host(key, doc, user=user)
    return create_host(doc, user=user)
