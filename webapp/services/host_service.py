from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from pymongo import ASCENDING, DESCENDING

from webapp.services.host_dir_service import archive_dir, init_dir, restore_dir, write_meta
from webapp.services.host_schema import DRAFT_LIKE_STATUSES, ValidationError, assert_valid_host_doc, normalize_host_doc
from webapp.services.mongo_service import get_collection

LOGGER = logging.getLogger(__name__)
INACTIVE_LIST_STATUSES = {"disabled", "retired", "pending_retire"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _public(doc: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not doc:
        return None
    out = {k: v for k, v in doc.items() if k != "ssh_key"}
    if "_id" in out:
        out["_id"] = str(out["_id"])
    return out


def _mark_host_dir_warning(asset_seq: str, exc: Exception) -> None:
    get_collection("hosts").update_one(
        {"asset_seq": asset_seq},
        {
            "$set": {
                "host_dir_status": "warning",
                "host_dir_error": str(exc),
                "host_dir_checked_at": _now(),
            }
        },
    )


def _sync_host_dir_best_effort(host: dict[str, Any], *, meta_only: bool = False) -> None:
    try:
        if meta_only:
            write_meta(host)
        else:
            init_dir(host)
    except OSError as exc:
        LOGGER.warning("host directory sync skipped for %s: %s", host.get("asset_seq"), exc)
        if host.get("asset_seq"):
            _mark_host_dir_warning(str(host["asset_seq"]), exc)


def list_hosts(
    query: str = "",
    filters: Optional[dict[str, Any]] = None,
    page: int = 1,
    page_size: int = 25,
    sort: str = "hostname",
    direction: str = "asc",
) -> dict[str, Any]:
    mongo_filter = build_host_filter(query, filters)
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


def build_host_filter(query: str = "", filters: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    filters = filters or {}
    mongo_filter: dict[str, Any] = {}
    for key in ("status", "group_name", "environment", "host_type", "dc"):
        value = filters.get(key)
        if value:
            mongo_filter[key] = normalize_host_doc({key: value}).get(key, value)
    if not mongo_filter.get("status") and not filters.get("include_inactive"):
        mongo_filter["status"] = {"$nin": sorted(INACTIVE_LIST_STATUSES)}
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
    return mongo_filter


def list_matching_host_keys(
    query: str = "",
    filters: Optional[dict[str, Any]] = None,
    page: int = 1,
    page_size: int = 25,
    current_page_only: bool = True,
) -> list[str]:
    mongo_filter = build_host_filter(query, filters)
    mongo_filter["status"] = {"$nin": ["draft", "retired"]}
    docs = get_collection("hosts").find(mongo_filter, {"hostname": 1, "asset_seq": 1}).sort("hostname", ASCENDING)
    if current_page_only:
        docs = docs.skip((max(page, 1) - 1) * min(max(page_size, 1), 100)).limit(min(max(page_size, 1), 100))
    return [str(doc.get("hostname") or doc.get("asset_seq")) for doc in docs if doc.get("hostname") or doc.get("asset_seq")]


def status_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in get_collection("hosts").aggregate([{"$group": {"_id": "$status", "count": {"$sum": 1}}}]):
        counts[str(item.get("_id") or "unknown")] = int(item.get("count", 0))
    counts["total"] = sum(counts.values())
    return counts


def list_draft_host_keys() -> list[str]:
    docs = get_collection("hosts").find({"status": "draft"}, {"hostname": 1, "asset_seq": 1}).sort("hostname", ASCENDING)
    return [str(doc.get("hostname") or doc.get("asset_seq")) for doc in docs if doc.get("hostname") or doc.get("asset_seq")]


def _identity_query(key: str) -> dict[str, Any]:
    return {"$or": [{"hostname": key}, {"asset_seq": key}]}


def get_host(key: str) -> Optional[dict[str, Any]]:
    return _public(get_collection("hosts").find_one(_identity_query(key), {"ssh_key": 0}))


def create_host(doc: dict[str, Any], user: str = "system") -> dict[str, Any]:
    normalized = normalize_host_doc(doc)
    warnings = assert_valid_host_doc(normalized, partial=normalized.get("status") in DRAFT_LIKE_STATUSES)
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
    _sync_host_dir_best_effort(normalized)
    result = get_host(normalized["hostname"]) or {}
    result["_warnings"] = warnings
    return result


def update_host(asset_seq: str, changes: dict[str, Any], user: str = "system") -> dict[str, Any]:
    existing = get_collection("hosts").find_one(_identity_query(asset_seq))
    if not existing:
        raise KeyError(f"host not found: {asset_seq}")
    original_asset_seq = existing.get("asset_seq", asset_seq)
    merged = normalize_host_doc({**existing, **changes, "asset_seq": changes.get("asset_seq", original_asset_seq)})
    warnings = assert_valid_host_doc(merged, partial=merged.get("status") in DRAFT_LIKE_STATUSES)
    conflict = get_collection("hosts").find_one({"hostname": merged["hostname"], "_id": {"$ne": existing["_id"]}})
    if conflict:
        raise ValidationError([f"hostname already exists: {merged['hostname']}"])
    merged["updated_at"] = _now()
    merged["updated_by"] = user
    get_collection("hosts").replace_one({"_id": existing["_id"]}, merged)
    if merged.get("status") == "retired":
        archive_dir(original_asset_seq, existing.get("hostname"))
    else:
        _sync_host_dir_best_effort(merged)
        _sync_host_dir_best_effort(merged, meta_only=True)
    result = get_host(merged["hostname"]) or {}
    result["_warnings"] = warnings
    return result


def apply_verified_identity(asset_seq: str, identity: dict[str, Any], user: str = "system") -> dict[str, Any]:
    existing = get_collection("hosts").find_one(_identity_query(asset_seq))
    if not existing:
        raise KeyError(f"host not found: {asset_seq}")
    now = _now()
    observed_hostname = str(identity.get("hostname") or "").strip()
    observed_os = str(identity.get("os") or "").strip()
    trusted = bool(identity.get("trusted"))
    changes: dict[str, Any] = {
        "hostname_observed": observed_hostname,
        "os_observed": observed_os,
        "identity_source": identity.get("source") or "actual_runner",
        "identity_runner": identity.get("runner") or "",
        "identity_verified_at": now,
        "identity_verified_by": user,
        "identity_confidence": "verified" if trusted else "failed",
        "identity_error": identity.get("error", ""),
    }
    warnings: list[str] = []
    if trusted and observed_os:
        changes["os"] = observed_os
        changes["os_source"] = "actual_runner"
    if trusted and observed_hostname:
        conflict = get_collection("hosts").find_one({"hostname": observed_hostname, "_id": {"$ne": existing["_id"]}})
        if conflict:
            warnings.append(f"observed hostname conflicts with existing host: {observed_hostname}")
        else:
            changes["hostname"] = observed_hostname
            changes["hostname_source"] = "actual_runner"
    updated = update_host(existing.get("hostname") or existing.get("asset_seq"), changes, user=user)
    updated["_identity_warnings"] = warnings
    return updated


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


def bulk_promote_draft_hosts(keys: list[str], reason: str, user: str = "system") -> dict[str, Any]:
    reason = str(reason or "").strip() or "bulk promote draft to active"
    unique_keys = [key.strip() for key in dict.fromkeys(keys) if str(key).strip()]
    result = {"promoted": [], "skipped": [], "promoted_count": 0, "skipped_count": 0}
    for key in unique_keys:
        existing = get_collection("hosts").find_one(_identity_query(key))
        if not existing:
            result["skipped"].append({"asset_seq": key, "reason": "host not found"})
            continue
        normalized = normalize_host_doc(existing)
        if normalized.get("status") != "draft":
            result["skipped"].append(
                {
                    "asset_seq": existing.get("asset_seq") or key,
                    "hostname": existing.get("hostname"),
                    "status": normalized.get("status"),
                    "reason": "not a draft host",
                }
            )
            continue
        record_lifecycle_event(existing, "bulk_promote_draft", reason, user)
        try:
            updated = update_host(existing.get("hostname") or existing.get("asset_seq"), {"status": "active"}, user=user)
        except Exception as exc:
            result["skipped"].append(
                {
                    "asset_seq": existing.get("asset_seq") or key,
                    "hostname": existing.get("hostname"),
                    "status": normalized.get("status"),
                    "reason": str(exc),
                }
            )
            continue
        result["promoted"].append({"asset_seq": updated.get("asset_seq"), "hostname": updated.get("hostname")})
    result["promoted_count"] = len(result["promoted"])
    result["skipped_count"] = len(result["skipped"])
    return result


def bulk_update_draft_hosts(keys: list[str], changes: dict[str, Any], reason: str, user: str = "system") -> dict[str, Any]:
    allowed = {"environment", "dc", "host_type", "owner", "custodian", "user_unit", "system_name", "note"}
    clean_changes = {key: value for key, value in changes.items() if key in allowed and str(value or "").strip()}
    if not clean_changes:
        raise ValueError("no draft fields selected for update")
    reason = str(reason or "").strip() or "bulk update draft fields"
    unique_keys = [key.strip() for key in dict.fromkeys(keys) if str(key).strip()]
    result = {"updated": [], "skipped": [], "updated_count": 0, "skipped_count": 0}
    for key in unique_keys:
        existing = get_collection("hosts").find_one(_identity_query(key))
        if not existing:
            result["skipped"].append({"asset_seq": key, "reason": "host not found"})
            continue
        normalized = normalize_host_doc(existing)
        if normalized.get("status") != "draft":
            result["skipped"].append(
                {
                    "asset_seq": existing.get("asset_seq") or key,
                    "hostname": existing.get("hostname"),
                    "status": normalized.get("status"),
                    "reason": "not a draft host",
                }
            )
            continue
        record_lifecycle_event(existing, "bulk_update_draft", reason, user)
        updated = update_host(existing.get("hostname") or existing.get("asset_seq"), clean_changes, user=user)
        result["updated"].append({"asset_seq": updated.get("asset_seq"), "hostname": updated.get("hostname")})
    result["updated_count"] = len(result["updated"])
    result["skipped_count"] = len(result["skipped"])
    return result


def bulk_update_host_statuses(keys: list[str], status: str, reason: str, user: str = "system") -> dict[str, Any]:
    normalized_status = normalize_host_doc({"status": status}).get("status")
    if normalized_status not in {
        "draft",
        "pending_ip",
        "pending_data",
        "pending_deploy",
        "active",
        "disabled",
        "retired",
        "pending_retire",
    }:
        raise ValueError("invalid asset status")
    reason = str(reason or "").strip() or "bulk update asset status"
    unique_keys = [key.strip() for key in dict.fromkeys(keys) if str(key).strip()]
    result = {"updated": [], "skipped": [], "updated_count": 0, "skipped_count": 0, "target_status": normalized_status}
    for key in unique_keys:
        existing = get_collection("hosts").find_one(_identity_query(key))
        if not existing:
            result["skipped"].append({"asset_seq": key, "reason": "host not found"})
            continue
        current_status = normalize_host_doc(existing).get("status")
        if current_status == normalized_status:
            result["skipped"].append(
                {
                    "asset_seq": existing.get("asset_seq") or key,
                    "hostname": existing.get("hostname"),
                    "status": current_status,
                    "reason": "already in target status",
                }
            )
            continue
        record_lifecycle_event(existing, "bulk_update_status", reason, user)
        try:
            updated = update_host(existing.get("hostname") or existing.get("asset_seq"), {"status": normalized_status}, user=user)
        except Exception as exc:
            result["skipped"].append(
                {
                    "asset_seq": existing.get("asset_seq") or key,
                    "hostname": existing.get("hostname"),
                    "status": current_status,
                    "reason": str(exc),
                }
            )
            continue
        result["updated"].append({"asset_seq": updated.get("asset_seq"), "hostname": updated.get("hostname")})
    result["updated_count"] = len(result["updated"])
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
