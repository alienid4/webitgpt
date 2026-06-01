from __future__ import annotations

from typing import Any

from webapp.services.cmdb_service import asset_quality_report
from webapp.services.inventory_service import ap_account_report
from webapp.services import dependency_service


STATUS_LABELS = {
    "ok": "正常",
    "needs_review": "需檢視",
    "degraded": "資料源異常",
}

ISSUE_LABELS = {
    "platform_mismatch": "平台分類疑似錯誤",
    "missing_required": "必填欄位缺漏",
    "workflow_pending": "流程尚未結案",
    "missing_ip": "缺少 IP",
    "missing_os": "缺少 OS",
    "missing_connection": "缺少連線方式",
    "duplicate_ip": "IP 重複",
    "scan_not_in_cmdb": "掃描到但 CMDB 無",
    "cmdb_not_seen": "CMDB 有但掃描未見",
    "reserved_but_alive": "保留 IP 卻有回應",
}

PLATFORM_LABELS = {
    "linux": "Linux",
    "windows": "Windows",
    "aix": "AIX",
    "as400": "AS400",
    "vmware_host": "VMware 主機",
    "vmware_vm": "VMware VM",
    "vmware_vcenter": "vCenter",
    "network_device": "網路設備",
    "end_device": "端點設備",
}


def _status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status or "未知")


def _issue_label(issue_type: str) -> str:
    return ISSUE_LABELS.get(issue_type, issue_type or "未分類")


def _platform_label(value: str) -> str:
    return PLATFORM_LABELS.get(str(value or ""), str(value or "-"))


def _cmdb_detail_rows(cmdb: dict[str, Any], limit: int = 200) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for issue in cmdb.get("issues", [])[:limit]:
        issue_type = str(issue.get("type") or "")
        key = str(issue.get("hostname") or issue.get("asset_seq") or issue.get("ip") or "")
        rows.append(
            {
                "domain": "CMDB",
                "type": issue_type,
                "type_label": _issue_label(issue_type),
                "severity": issue.get("severity") or "medium",
                "asset_name": issue.get("asset_name") or "-",
                "hostname": issue.get("hostname") or "-",
                "ip": issue.get("ip") or "-",
                "status": issue.get("status") or "-",
                "detail": issue.get("detail") or issue.get("title") or "-",
                "action": issue.get("action") or "請進入資產編輯頁補齊資料。",
                "edit_key": key,
                "suggested_host_type": issue.get("suggested_host_type") or "",
                "current_host_type": issue.get("current_host_type") or "",
                "suggested_host_type_label": _platform_label(issue.get("suggested_host_type") or ""),
                "current_host_type_label": _platform_label(issue.get("current_host_type") or ""),
            }
        )
    return rows


def _cmdb_breakdown(cmdb: dict[str, Any]) -> list[dict[str, Any]]:
    counts = cmdb.get("counts") or {}
    return [
        {"type": key, "label": _issue_label(key), "count": int(value or 0)}
        for key, value in sorted(counts.items(), key=lambda item: (-int(item[1] or 0), _issue_label(str(item[0]))))
    ]


def operations_data_quality() -> dict[str, Any]:
    warnings = []
    try:
        cmdb = asset_quality_report()
    except Exception as exc:
        warnings.append(f"CMDB quality unavailable: {type(exc).__name__}")
        cmdb = {"issues_total": 0, "counts": {}, "issues": []}
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
    cmdb_counts = cmdb.get("counts") or {}
    platform_mismatch = int(cmdb_counts.get("platform_mismatch", 0) or 0)
    missing_connection = int(cmdb_counts.get("missing_connection", 0) or 0)
    workflow_pending = int(cmdb_counts.get("workflow_pending", 0) or 0)
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
            "status_label": "CMDB 需檢視" if cmdb_issues else "CMDB 正常",
            "count": cmdb_issues,
            "action": "先處理平台分類、必填欄位與草稿流程；點下方明細可直接進入資產編輯。",
            "href": "#cmdb-quality-details",
        },
        {
            "domain": "平台分類",
            "status": "needs_review" if platform_mismatch else "ok",
            "status_label": "平台分類需修正" if platform_mismatch else "平台分類正常",
            "count": platform_mismatch,
            "action": "OS 版本顯示 Red Hat、CentOS、Ubuntu、Debian 等時，平台分類應歸到 Linux；若仍是端點或錯誤分類，會影響主管儀表板與巡檢範圍。",
            "href": "#cmdb-quality-details",
        },
        {
            "domain": "AP 帳號",
            "status": "needs_review" if ap_review else "ok",
            "status_label": "AP 帳號需複核" if ap_review else "AP 帳號正常",
            "count": ap_review,
            "action": "檢查 owner、PAM、MFA 與權限欄位，避免帳號盤點無法交付主管。",
            "href": "",
        },
        {
            "domain": "AP owner",
            "status": "needs_review" if owner_missing else "ok",
            "status_label": "AP owner 需補齊" if owner_missing else "AP owner 正常",
            "count": owner_missing,
            "action": "補齊 owner 後，通知與責任歸屬才會清楚。",
            "href": "",
        },
        {
            "domain": "拓撲通知",
            "status": "needs_review" if topology_owner_missing else "ok",
            "status_label": "拓撲通知需補齊" if topology_owner_missing else "拓撲通知正常",
            "count": topology_owner_missing,
            "action": "補齊系統 owner 與通知對象，核心影響圖才可直接支援事件通知。",
            "href": "",
        },
    ]
    score = max(0, 100 - cmdb_issues * 2 - ap_review * 3 - topology_owner_missing * 5)
    status = "degraded" if warnings else ("ok" if score >= 90 else "needs_review")
    return {
        "score": score,
        "status": status,
        "status_label": _status_label(status),
        "warnings": warnings,
        "checks": checks,
        "cmdb_breakdown": _cmdb_breakdown(cmdb),
        "cmdb_detail_rows": _cmdb_detail_rows(cmdb),
        "summary": {
            "cmdb_issues": cmdb_issues,
            "cmdb_platform_mismatch": platform_mismatch,
            "cmdb_missing_connection": missing_connection,
            "cmdb_workflow_pending": workflow_pending,
            "ap_accounts": ap_summary.get("total", 0),
            "ap_review": ap_review,
            "ap_owner_missing": owner_missing,
            "topology_notification_missing": topology_owner_missing,
        },
    }
