from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from webapp.services.mongo_service import get_collection


DEFAULT_STATUSES = [
    {"code": "trusted", "name": "可信資產", "category": "正常", "risk": "低", "color": "green", "sort_order": 10, "visible_in_report": True, "blocks_activation": False, "requires_reason": False, "requires_expiry": False, "auto_assignable": True, "description": "人工資料與實測資料一致，可列入正式資產清冊。"},
    {"code": "pending_verify", "name": "待驗證", "category": "待處理", "risk": "中", "color": "orange", "sort_order": 20, "visible_in_report": True, "blocks_activation": True, "requires_reason": False, "requires_expiry": False, "auto_assignable": True, "description": "剛匯入或剛建立草稿，尚未完成掃描與欄位比對。"},
    {"code": "missing_data", "name": "待補資料", "category": "待處理", "risk": "中", "color": "orange", "sort_order": 30, "visible_in_report": True, "blocks_activation": True, "requires_reason": False, "requires_expiry": False, "auto_assignable": True, "description": "必要欄位缺漏，例如保管人、部門、用途或申請單號。"},
    {"code": "data_mismatch", "name": "資料不一致", "category": "異常", "risk": "中", "color": "orange", "sort_order": 40, "visible_in_report": True, "blocks_activation": True, "requires_reason": False, "requires_expiry": False, "auto_assignable": True, "description": "人工匯入資料與系統實測資料不同，需要確認採用哪一邊。"},
    {"code": "unmanaged_found", "name": "未納管發現", "category": "異常", "risk": "高", "color": "red", "sort_order": 50, "visible_in_report": True, "blocks_activation": True, "requires_reason": False, "requires_expiry": False, "auto_assignable": True, "description": "掃描或採集看到設備存在，但 CMDB 沒有正式資產紀錄。"},
    {"code": "suspected_offline", "name": "疑似下線", "category": "異常", "risk": "中", "color": "orange", "sort_order": 60, "visible_in_report": True, "blocks_activation": False, "requires_reason": False, "requires_expiry": False, "auto_assignable": True, "description": "CMDB 有資料，但連續多次掃描或連線都找不到主機。"},
    {"code": "pending_retire", "name": "待退役", "category": "待處理", "risk": "中", "color": "orange", "sort_order": 70, "visible_in_report": True, "blocks_activation": False, "requires_reason": True, "requires_expiry": False, "auto_assignable": False, "description": "已確認準備下線，但退役流程或 IP 釋放尚未完成。"},
    {"code": "retired", "name": "已退役", "category": "結案", "risk": "低", "color": "gray", "sort_order": 80, "visible_in_report": False, "blocks_activation": False, "requires_reason": True, "requires_expiry": False, "auto_assignable": False, "description": "資產已完成下線與結案，保留歷史紀錄。"},
    {"code": "ip_conflict", "name": "IP 衝突", "category": "異常", "risk": "高", "color": "red", "sort_order": 90, "visible_in_report": True, "blocks_activation": True, "requires_reason": False, "requires_expiry": False, "auto_assignable": True, "description": "同一 IP 對應到多筆資產或掃描結果與 CMDB 不一致。"},
    {"code": "hostname_conflict", "name": "Hostname 衝突", "category": "異常", "risk": "高", "color": "red", "sort_order": 100, "visible_in_report": True, "blocks_activation": True, "requires_reason": False, "requires_expiry": False, "auto_assignable": True, "description": "同一 hostname 出現多筆資產，或 hostname 與實測結果不一致。"},
    {"code": "os_mismatch", "name": "OS 不一致", "category": "異常", "risk": "中", "color": "orange", "sort_order": 110, "visible_in_report": True, "blocks_activation": True, "requires_reason": False, "requires_expiry": False, "auto_assignable": True, "description": "資產表 OS 與主機實際偵測版本不同。"},
    {"code": "owner_missing", "name": "保管人缺漏", "category": "待處理", "risk": "中", "color": "orange", "sort_order": 120, "visible_in_report": True, "blocks_activation": True, "requires_reason": False, "requires_expiry": False, "auto_assignable": True, "description": "主機沒有保管人或負責窗口，主管報表需要列出追蹤。"},
    {"code": "scan_failed", "name": "掃描失敗", "category": "待處理", "risk": "中", "color": "orange", "sort_order": 130, "visible_in_report": True, "blocks_activation": False, "requires_reason": False, "requires_expiry": False, "auto_assignable": True, "description": "網段掃描或主機採集失敗，需要確認防火牆、連線權限或主機狀態。"},
    {"code": "waiting_firewall", "name": "等待防火牆開通", "category": "待處理", "risk": "中", "color": "orange", "sort_order": 140, "visible_in_report": True, "blocks_activation": True, "requires_reason": True, "requires_expiry": True, "auto_assignable": False, "description": "主機已申請或已建置，但必要連線尚未開通，暫時不能完成驗證或納管。"},
    {"code": "waiting_vuln_scan", "name": "等待弱掃完成", "category": "待處理", "risk": "中", "color": "orange", "sort_order": 150, "visible_in_report": True, "blocks_activation": True, "requires_reason": True, "requires_expiry": True, "auto_assignable": False, "description": "主機需完成弱點掃描或資安確認後才能正式納管或上線。"},
    {"code": "waiting_pam", "name": "等待 PAM 納管", "category": "待處理", "risk": "高", "color": "red", "sort_order": 160, "visible_in_report": True, "blocks_activation": True, "requires_reason": True, "requires_expiry": True, "auto_assignable": False, "description": "高權限或服務帳號尚未納入 PAM，需完成後才能結案。"},
    {"code": "exception_hold", "name": "例外保留", "category": "例外", "risk": "低", "color": "blue", "sort_order": 900, "visible_in_report": True, "blocks_activation": False, "requires_reason": True, "requires_expiry": True, "auto_assignable": False, "description": "已知特殊情境，允許暫時保留，但必須填原因與到期日。"},
    {"code": "not_managed", "name": "暫不納管", "category": "例外", "risk": "低", "color": "gray", "sort_order": 910, "visible_in_report": True, "blocks_activation": False, "requires_reason": True, "requires_expiry": True, "auto_assignable": False, "description": "確認不是本系統目前納管範圍，但保留發現紀錄供追蹤。"},
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _public(doc: dict[str, Any] | None) -> dict[str, Any]:
    if not doc:
        return {}
    return {key: value for key, value in doc.items() if key != "_id"}


def ensure_default_statuses() -> None:
    col = get_collection("asset_governance_statuses")
    now = _now()
    for item in DEFAULT_STATUSES:
        col.update_one(
            {"code": item["code"]},
            {"$setOnInsert": {**item, "enabled": True, "created_at": now, "created_by": "system"}, "$set": {"seeded_at": now}},
            upsert=True,
        )


def list_statuses(include_disabled: bool = True) -> list[dict[str, Any]]:
    ensure_default_statuses()
    query: dict[str, Any] = {}
    if not include_disabled:
        query["enabled"] = True
    return [_public(row) for row in get_collection("asset_governance_statuses").find(query).sort([("sort_order", 1), ("name", 1)])]


def save_status(data: dict[str, Any], user: str = "system") -> dict[str, Any]:
    code = str(data.get("code") or "").strip().lower().replace(" ", "_")
    if not code:
        raise ValueError("code is required")
    name = str(data.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    try:
        sort_order = int(data.get("sort_order") or 500)
    except ValueError:
        sort_order = 500
    doc = {
        "code": code[:80],
        "name": name[:80],
        "category": str(data.get("category") or "待處理").strip()[:40],
        "risk": str(data.get("risk") or "中").strip()[:20],
        "color": str(data.get("color") or "orange").strip()[:20],
        "sort_order": sort_order,
        "visible_in_report": bool(data.get("visible_in_report", True)),
        "blocks_activation": bool(data.get("blocks_activation", False)),
        "requires_reason": bool(data.get("requires_reason", False)),
        "requires_expiry": bool(data.get("requires_expiry", False)),
        "auto_assignable": bool(data.get("auto_assignable", False)),
        "enabled": bool(data.get("enabled", True)),
        "description": str(data.get("description") or "").strip()[:600],
        "updated_at": _now(),
        "updated_by": user,
    }
    get_collection("asset_governance_statuses").update_one(
        {"code": doc["code"]},
        {"$set": doc, "$setOnInsert": {"created_at": doc["updated_at"], "created_by": user}},
        upsert=True,
    )
    return doc


def set_status_enabled(code: str, enabled: bool, user: str = "system") -> bool:
    result = get_collection("asset_governance_statuses").update_one(
        {"code": code},
        {"$set": {"enabled": bool(enabled), "updated_at": _now(), "updated_by": user}},
    )
    return result.matched_count == 1
