from __future__ import annotations

import csv
import io

from flask import Blueprint, Response, jsonify, redirect, render_template, request, url_for

from webapp.decorators import current_user, require_feature, require_role
from webapp.services import audit_log_service, host_service
from webapp.services.compliance_service import dashboard as compliance_dashboard
from webapp.services.feature_flags import is_enabled
from webapp.services.host_service import list_hosts
from webapp.services.inventory_service import account_report_summary
from webapp.services import dependency_service
from webapp.services import cmdb_relationship_service
from webapp.services.dependency_service import topology
from webapp.services.quality_service import operations_data_quality
from webapp.services.token_cost_service import token_cost_report

bp = Blueprint("api_reports", __name__)


def _include_external() -> bool:
    return request.args.get("include_external") in {"1", "true", "yes", "on"}


def _include_unmanaged() -> bool:
    return request.args.get("include_unmanaged") in {"1", "true", "yes", "on"}


def _focus_impact() -> bool:
    return request.args.get("focus_impact") in {"1", "true", "yes", "on"}


def _topology_from_request(default_view: str = "core_impact") -> dict:
    return topology(
        view=request.args.get("view", default_view),
        center=request.args.get("center", ""),
        depth=int(request.args.get("depth", 2)),
        limit=int(request.args.get("limit", 200)),
        include_external=_include_external(),
        include_unmanaged=_include_unmanaged(),
        failed_node=request.args.get("failed_node", ""),
        focus_impact=_focus_impact(),
    )


def _empty_account_summary() -> dict:
    return {
        "summary": {
            "total": 0,
            "abnormal": 0,
            "privileged": 0,
            "service_login": 0,
            "never_login": 0,
            "password_old": 0,
            "system_default_hidden": 0,
            "pam_managed": 0,
        },
        "count": 0,
        "last_collected": "-",
        "hide_system_defaults": True,
        "by_department": [],
        "by_host": [],
        "by_risk": [],
        "abnormal_items": [],
        "abnormal_count": 0,
    }


def _empty_quality_report(message: str) -> dict:
    return {
        "score": 0,
        "status": "degraded",
        "warnings": [message],
        "summary": {
            "hosts": 0,
            "accounts": 0,
            "ap_accounts": 0,
            "cmdb_issues": 0,
            "ap_review": 0,
            "ap_owner_missing": 0,
            "topology_notification_missing": 0,
            "relations": 0,
            "notifications": 0,
            "patches": 0,
        },
        "checks": [],
    }


def _summary() -> dict:
    warnings: list[str] = []
    try:
        hosts = list_hosts(page=1, page_size=10000)["items"]
    except Exception as exc:
        hosts = []
        warnings.append(f"CMDB 資產摘要暫時不可用：{exc.__class__.__name__}")
    formal_hosts = [host for host in hosts if str(host.get("status") or "") not in {"draft", "retired"}]
    draft_hosts = [host for host in hosts if str(host.get("status") or "") == "draft"]
    by_env: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_dc: dict[str, int] = {}
    for host in formal_hosts:
        by_env[host.get("environment", "")] = by_env.get(host.get("environment", ""), 0) + 1
        by_status[host.get("status", "")] = by_status.get(host.get("status", ""), 0) + 1
        by_type[host.get("host_type") or host.get("os_group") or "-"] = by_type.get(host.get("host_type") or host.get("os_group") or "-", 0) + 1
        by_dc[host.get("dc") or host.get("location") or "-"] = by_dc.get(host.get("dc") or host.get("location") or "-", 0) + 1
    try:
        compliance = compliance_dashboard() if is_enabled("module_compliance_security", default=False) else {"open_findings": 0, "rules_total": 0}
    except Exception as exc:
        compliance = {"open_findings": 0, "rules_total": 0}
        warnings.append(f"合規摘要暫時不可用：{exc.__class__.__name__}")
    try:
        accounts = account_report_summary()
    except Exception as exc:
        accounts = _empty_account_summary()
        warnings.append(f"帳號摘要暫時不可用：{exc.__class__.__name__}")
    try:
        quality = operations_data_quality()
    except Exception as exc:
        quality = _empty_quality_report(f"資料品質摘要暫時不可用：{exc.__class__.__name__}")
        warnings.append(f"資料品質摘要暫時不可用：{exc.__class__.__name__}")
    try:
        token_cost = token_cost_report()
    except Exception as exc:
        token_cost = {"summary": {"total_tokens": 0, "estimated_cost_usd": 0}}
        warnings.append(f"AI Token 摘要暫時不可用：{exc.__class__.__name__}")
    return {
        "hosts_total": len(formal_hosts),
        "hosts_all_total": len(hosts),
        "draft_total": len(draft_hosts),
        "by_env": by_env,
        "by_status": by_status,
        "by_type": by_type,
        "by_dc": by_dc,
        "compliance": compliance,
        "accounts": accounts,
        "quality": quality,
        "token_cost": token_cost,
        "warnings": warnings,
    }


def _bar_items(rows, total: int = 0, limit: int = 8) -> list[dict]:
    if isinstance(rows, dict):
        items = [{"name": name or "-", "count": count} for name, count in rows.items()]
    else:
        items = [{"name": row.get("name") or "-", "count": int(row.get("count") or 0)} for row in rows]
    items = sorted(items, key=lambda row: (-row["count"], row["name"]))[:limit]
    denominator = max(total or sum(row["count"] for row in items), 1)
    return [{**row, "pct": round((row["count"] / denominator) * 100, 1), "width": max(2, round((row["count"] / denominator) * 100, 1))} for row in items]


def _executive_charts(summary: dict) -> dict:
    account_summary = summary["accounts"]["summary"]
    risk_total = max(account_summary.get("total", 0), 1)
    risk_rows = [
        {"name": "異常帳號", "count": account_summary.get("abnormal", 0)},
        {"name": "高權限帳號", "count": account_summary.get("privileged", 0)},
        {"name": "長期未登入", "count": account_summary.get("never_login", 0)},
        {"name": "服務帳號可登入", "count": account_summary.get("service_login", 0)},
        {"name": "PAM 納管", "count": account_summary.get("pam_managed", 0)},
    ]
    compliance_open = int(summary["compliance"].get("open_findings", 0) or 0)
    rules_total = int(summary["compliance"].get("rules_total", 0) or 0)
    return {
        "asset_status": _bar_items(summary["by_status"], summary["hosts_total"]),
        "asset_type": _bar_items(summary["by_type"], summary["hosts_total"]),
        "asset_env": _bar_items(summary["by_env"], summary["hosts_total"]),
        "asset_dc": _bar_items(summary["by_dc"], summary["hosts_total"]),
        "account_risk": _bar_items(risk_rows, risk_total),
        "account_by_host": _bar_items(summary["accounts"].get("by_host", []), account_summary.get("total", 0), limit=5),
        "compliance": {
            "open_findings": compliance_open,
            "rules_total": rules_total,
            "ok_pct": 100 if not rules_total and not compliance_open else max(0, round(100 - min(100, compliance_open * 10), 1)),
        },
    }


@bp.get("/reports")
@require_feature("summary")
def reports_page():
    return render_template("reports.html", summary=_summary())


@bp.get("/dashboard")
@require_feature("summary")
def dashboard_page():
    return render_template("dashboard.html", summary=_summary())


@bp.get("/reports/data-quality")
@require_feature("summary")
def data_quality_page():
    return render_template("data_quality.html", report=operations_data_quality(), apply_result=None)


@bp.post("/reports/data-quality/apply-platform-suggestions")
@require_feature("summary")
@require_role("admin")
def data_quality_apply_platform_suggestions():
    selected_keys = [item for item in request.form.getlist("asset_key") if str(item or "").strip()]
    if request.form.get("scope") == "selected" and not selected_keys:
        return render_template(
            "data_quality.html",
            report=operations_data_quality(),
            apply_result={"action_label": "平台分類", "updated_count": 0, "skipped_count": 0, "error": "請先勾選要套用的平台分類項目。"},
        )
    result = host_service.bulk_apply_platform_suggestions(
        user=current_user()["username"],
        keys=selected_keys if request.form.get("scope") == "selected" else None,
    )
    result["action_label"] = "平台分類"
    audit_log_service.append(
        "cmdb.platform_suggestion.apply",
        current_user()["username"],
        {
            "updated_count": result["updated_count"],
            "skipped_count": result["skipped_count"],
        },
    )
    return render_template("data_quality.html", report=operations_data_quality(), apply_result=result)


@bp.post("/reports/data-quality/apply-default-connections")
@require_feature("summary")
@require_role("admin")
def data_quality_apply_default_connections():
    selected_keys = [item for item in request.form.getlist("asset_key") if str(item or "").strip()]
    if request.form.get("scope") == "selected" and not selected_keys:
        return render_template(
            "data_quality.html",
            report=operations_data_quality(),
            apply_result={"action_label": "預設連線方式", "updated_count": 0, "skipped_count": 0, "error": "請先勾選要套用預設連線方式的項目。"},
        )
    result = host_service.bulk_apply_default_connections(
        user=current_user()["username"],
        keys=selected_keys if request.form.get("scope") == "selected" else None,
    )
    result["action_label"] = "預設連線方式"
    audit_log_service.append(
        "cmdb.default_connection.apply",
        current_user()["username"],
        {
            "updated_count": result["updated_count"],
            "skipped_count": result["skipped_count"],
        },
    )
    return render_template("data_quality.html", report=operations_data_quality(), apply_result=result)


@bp.get("/reports/post-install")
@require_feature("summary")
def post_install_report_page():
    checks = [
        {"name": "Health", "target": "/health", "purpose": "確認服務版本與狀態。"},
        {"name": "Ready", "target": "/ready", "purpose": "確認 MongoDB 與核心依賴可用。"},
        {"name": "帳號盤點", "target": "/accounts", "purpose": "確認 OS / AP 帳號工作台可載入。"},
        {"name": "AP 模板", "target": "/accounts/ap-template.xlsx", "purpose": "確認 AP 帳號匯入模板可下載。"},
        {"name": "核心影響圖", "target": "/dependencies?view=core_impact", "purpose": "確認拓撲決策圖可載入。"},
        {"name": "資料品質", "target": "/api/reports/data-quality", "purpose": "確認維運資料品質 API 可回應。"},
    ]
    return render_template("post_install_report.html", checks=checks)


@bp.get("/executive")
@require_feature("summary")
def executive_page():
    summary = _summary()
    risk_items = summary["accounts"].get("abnormal_items", [])[:5]
    return render_template("executive.html", summary=summary, risk_items=risk_items, charts=_executive_charts(summary))


@bp.get("/api/reports/summary")
@require_feature("summary")
def reports_summary_api():
    return jsonify(_summary())


@bp.get("/api/reports/summary.csv")
@require_feature("summary")
def reports_summary_csv():
    summary = _summary()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["section", "name", "value"])
    writer.writerow(["summary", "hosts_total", summary["hosts_total"]])
    writer.writerow(["summary", "hosts_all_total", summary.get("hosts_all_total", summary["hosts_total"])])
    writer.writerow(["summary", "draft_total", summary.get("draft_total", 0)])
    writer.writerow(["summary", "open_findings", summary["compliance"].get("open_findings", 0)])
    writer.writerow(["summary", "rules_total", summary["compliance"].get("rules_total", 0)])
    writer.writerow(["ai_token", "month_total_tokens", summary["token_cost"]["summary"].get("total_tokens", 0)])
    writer.writerow(["ai_token", "month_estimated_cost_usd", summary["token_cost"]["summary"].get("estimated_cost_usd", 0)])
    account_summary = summary["accounts"]["summary"]
    writer.writerow(["accounts", "total", account_summary.get("total", 0)])
    writer.writerow(["accounts", "abnormal", account_summary.get("abnormal", 0)])
    writer.writerow(["accounts", "privileged", account_summary.get("privileged", 0)])
    writer.writerow(["accounts", "service_login", account_summary.get("service_login", 0)])
    writer.writerow(["accounts", "never_login", account_summary.get("never_login", 0)])
    writer.writerow(["accounts", "password_old", account_summary.get("password_old", 0)])
    writer.writerow(["accounts", "system_default_hidden", account_summary.get("system_default_hidden", 0)])
    for key, value in summary["by_env"].items():
        writer.writerow(["environment", key, value])
    for key, value in summary["by_status"].items():
        writer.writerow(["status", key, value])
    for item in summary["accounts"]["by_department"]:
        writer.writerow(["accounts_by_department", item["name"], item["count"]])
    for item in summary["accounts"]["by_host"]:
        writer.writerow(["accounts_by_host", item["name"], item["count"]])
    for item in summary["accounts"]["by_risk"]:
        writer.writerow(["accounts_by_risk", item["name"], item["count"]])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=webitgpt_summary.csv"})


@bp.get("/api/reports/data-quality")
@require_feature("summary")
def data_quality_api():
    return jsonify(operations_data_quality())


@bp.get("/api/reports/data-quality.csv")
@require_feature("summary")
def data_quality_csv():
    report = operations_data_quality()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["domain", "status", "status_label", "count", "action"])
    for item in report["checks"]:
        writer.writerow([item["domain"], item["status"], item.get("status_label", item["status"]), item["count"], item["action"]])
    writer.writerow([])
    writer.writerow(["cmdb_issue_type", "label", "count"])
    for item in report.get("cmdb_breakdown", []):
        writer.writerow([item["type"], item["label"], item["count"]])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=webitgpt_data_quality.csv"})


@bp.get("/dependencies")
@require_feature("dependencies")
def dependencies_page():
    collect_runs = dependency_service.collect_runs(limit=5)
    systems = dependency_service.list_systems()
    relations = dependency_service.list_relations({"q": request.args.get("relation_q", "")})
    data = _topology_from_request()
    cmdb_overview = cmdb_relationship_service.cmdb_relationship_overview(request.args.get("center", ""))
    return render_template(
        "dependencies.html",
        topology=data,
        cmdb_overview=cmdb_overview,
        reconcile_report=dependency_service.filtered_reconcile_report(include_external=_include_external(), include_unmanaged=_include_unmanaged()),
        network_scan_report=dependency_service.latest_network_scan_report(),
        collect_runs=collect_runs,
        systems=systems,
        relation_items=relations,
    )


@bp.get("/api/dependencies")
@require_feature("dependencies")
def dependencies_api():
    return jsonify(_topology_from_request())


@bp.get("/api/dependencies/notifications.csv")
@require_feature("dependencies")
def dependencies_notifications_csv():
    data = _topology_from_request("core_impact")
    contacts = ((data.get("meta") or {}).get("impact_panel") or {}).get("notification_contacts") or []
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["core", "system_id", "system_name", "owner", "host_count", "status", "reason"])
    for item in contacts:
        writer.writerow(
            [
                item.get("core") or "",
                item.get("system_id") or "",
                item.get("system_name") or "",
                item.get("owner") or "",
                item.get("host_count") or 0,
                item.get("status") or "",
                item.get("reason") or "",
            ]
        )
    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=webitgpt_core_impact_notifications.csv"},
    )
