from __future__ import annotations

from typing import Any

from webapp.services.cmdb_service import asset_quality_report
from webapp.services.inventory_service import ap_account_report
from webapp.services import dependency_service


def operations_data_quality() -> dict[str, Any]:
    warnings = []
    try:
        cmdb = asset_quality_report()
    except Exception as exc:
        warnings.append(f"CMDB quality unavailable: {type(exc).__name__}")
        cmdb = {"issues_total": 0}
    try:
        ap = ap_account_report()
    except Exception as exc:
        warnings.append(f"AP account quality unavailable: {type(exc).__name__}")
        ap = {"summary": {"total": 0, "review": 0, "no_owner": 0}}
    try:
        topology = dependency_service.topology(view="core_impact")
    except Exception as exc:
        warnings.append(f"Topology quality unavailable: {type(exc).__name__}")
        topology = {"meta": {"impact_panel": {"notification_contacts": []}}}
    impact_panel = (topology.get("meta") or {}).get("impact_panel") or {}
    ap_summary = ap.get("summary", {})
    cmdb_issues = int(cmdb.get("issues_total", 0) or 0)
    ap_review = int(ap_summary.get("review", 0) or 0)
    owner_missing = int(ap_summary.get("no_owner", 0) or 0)
    topology_owner_missing = sum(
        1
        for item in impact_panel.get("notification_contacts", [])
        if str(item.get("status") or "").lower() not in {"ready", "可通知"} and "owner" in str(item.get("status") or "").lower()
    )
    checks = [
        {
            "domain": "CMDB",
            "status": "needs_review" if cmdb_issues else "ok",
            "count": cmdb_issues,
            "action": "先修匯入欄位、重複 IP、缺 owner 與缺連線方式。",
        },
        {
            "domain": "AP 帳號",
            "status": "needs_review" if ap_review else "ok",
            "count": ap_review,
            "action": "優先補 owner、PAM、MFA 與長期未登入帳號處置語意。",
        },
        {
            "domain": "AP owner",
            "status": "needs_review" if owner_missing else "ok",
            "count": owner_missing,
            "action": "缺 owner 會直接影響通知與稽核責任歸屬。",
        },
        {
            "domain": "拓撲通知",
            "status": "needs_review" if topology_owner_missing else "ok",
            "count": topology_owner_missing,
            "action": "補齊系統 owner，讓核心影響圖的通知名單可直接使用。",
        },
    ]
    score = max(0, 100 - cmdb_issues * 2 - ap_review * 3 - topology_owner_missing * 5)
    return {
        "score": score,
        "status": "degraded" if warnings else ("ok" if score >= 90 else "needs_review"),
        "warnings": warnings,
        "checks": checks,
        "summary": {
            "cmdb_issues": cmdb_issues,
            "ap_accounts": ap_summary.get("total", 0),
            "ap_review": ap_review,
            "ap_owner_missing": owner_missing,
            "topology_notification_missing": topology_owner_missing,
        },
    }
