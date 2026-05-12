from __future__ import annotations

import csv
import io

from flask import Blueprint, Response, jsonify, render_template, request

from webapp.decorators import require_feature
from webapp.services.compliance_service import dashboard as compliance_dashboard
from webapp.services.feature_flags import is_enabled
from webapp.services.host_service import list_hosts
from webapp.services.inventory_service import account_report_summary
from webapp.services.dependency_service import topology

bp = Blueprint("api_reports", __name__)


def _include_external() -> bool:
    return request.args.get("include_external") in {"1", "true", "yes", "on"}


def _summary() -> dict:
    hosts = list_hosts(page=1, page_size=10000)["items"]
    by_env: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for host in hosts:
        by_env[host.get("environment", "")] = by_env.get(host.get("environment", ""), 0) + 1
        by_status[host.get("status", "")] = by_status.get(host.get("status", ""), 0) + 1
    compliance = compliance_dashboard() if is_enabled("module_compliance_security", default=False) else {"open_findings": 0, "rules_total": 0}
    return {
        "hosts_total": len(hosts),
        "by_env": by_env,
        "by_status": by_status,
        "compliance": compliance,
        "accounts": account_report_summary(),
    }


@bp.get("/reports")
@require_feature("summary")
def reports_page():
    return render_template("reports.html", summary=_summary())


@bp.get("/dashboard")
@require_feature("summary")
def dashboard_page():
    return render_template("dashboard.html", summary=_summary())


@bp.get("/executive")
@require_feature("summary")
def executive_page():
    summary = _summary()
    risk_items = summary["accounts"].get("abnormal_items", [])[:5]
    return render_template("executive.html", summary=summary, risk_items=risk_items)


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
    writer.writerow(["summary", "open_findings", summary["compliance"].get("open_findings", 0)])
    writer.writerow(["summary", "rules_total", summary["compliance"].get("rules_total", 0)])
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


@bp.get("/dependencies")
@require_feature("dependencies")
def dependencies_page():
    data = topology(
        view=request.args.get("view", "host"),
        center=request.args.get("center", ""),
        depth=int(request.args.get("depth", 2)),
        limit=int(request.args.get("limit", 200)),
        include_external=_include_external(),
        failed_node=request.args.get("failed_node", ""),
    )
    return render_template("dependencies.html", topology=data)


@bp.get("/api/dependencies")
@require_feature("dependencies")
def dependencies_api():
    return jsonify(topology(view=request.args.get("view", "host"), center=request.args.get("center", ""), depth=int(request.args.get("depth", 2)), limit=int(request.args.get("limit", 200)), include_external=_include_external(), failed_node=request.args.get("failed_node", "")))
