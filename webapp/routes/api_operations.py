from __future__ import annotations

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from webapp.decorators import current_user, require_feature, require_role
from webapp.services import audit_log_service
from webapp.services.inspection_service import nmon_deploy_plan, nmon_status, run_daily_inspection, today_report
from webapp.services.legacy_parity_service import collect_nmon_sample, daily_diagnostics, diagnostic_history, nmon_report, run_deep_diagnostic

bp = Blueprint("api_operations", __name__)


@bp.get("/inspections")
@require_feature("history")
def inspections_page():
    platform = request.args.get("platform", "linux")
    system_name = request.args.get("system", "")
    return render_template("inspections.html", report=today_report(), diagnostics=daily_diagnostics(platform, system_name))


@bp.post("/api/inspections/run")
@require_feature("history")
@require_role("admin")
def run_inspection_api():
    payload = request.get_json(force=True, silent=True) or {}
    limit = min(max(int(payload.get("limit", 10)), 1), 100)
    result = run_daily_inspection(limit=limit, user=current_user()["username"], system_name=str(payload.get("system") or ""))
    audit_log_service.append("inspection.run", current_user()["username"], {"count": result["count"]})
    return jsonify(result)


@bp.get("/api/inspections/today")
@require_feature("history")
def today_report_api():
    return jsonify(today_report())


@bp.get("/api/inspections/diagnostics")
@require_feature("history")
def diagnostics_api():
    return jsonify(daily_diagnostics(request.args.get("platform", "linux"), request.args.get("system", "")))


@bp.post("/api/inspections/deep/<asset_seq>")
@require_feature("history")
@require_role("admin")
def deep_diagnostic_api(asset_seq: str):
    result = run_deep_diagnostic(asset_seq, current_user()["username"])
    audit_log_service.append("inspection.deep_diagnostic", current_user()["username"], {"asset_seq": asset_seq})
    return jsonify(result)


@bp.post("/inspections/deep/<asset_seq>")
@require_feature("history")
@require_role("admin")
def deep_diagnostic_page(asset_seq: str):
    result = run_deep_diagnostic(asset_seq, current_user()["username"])
    audit_log_service.append("inspection.deep_diagnostic", current_user()["username"], {"asset_seq": asset_seq})
    return redirect(url_for("api_operations.inspections_page", platform=result.get("platform", "linux")) + f"#host-{asset_seq}")


@bp.get("/api/inspections/deep/<asset_seq>/history")
@require_feature("history")
def deep_diagnostic_history_api(asset_seq: str):
    return jsonify({"asset_seq": asset_seq, "items": diagnostic_history(asset_seq)})


@bp.get("/nmon")
@require_feature("perf")
def nmon_page():
    period = request.args.get("period", "day")
    return render_template("nmon.html", status=nmon_status(), report=nmon_report(period))


@bp.get("/api/nmon/status")
@require_feature("perf")
def nmon_status_api():
    return jsonify(nmon_status())


@bp.post("/api/nmon/deploy-plan")
@require_feature("perf")
@require_role("admin")
def nmon_deploy_plan_api():
    limit = min(max(int((request.get_json(force=True, silent=True) or {}).get("limit", 20)), 1), 100)
    result = nmon_deploy_plan(limit=limit)
    audit_log_service.append("nmon.deploy_plan", current_user()["username"], {"count": result["count"], "mode": result["mode"]})
    return jsonify(result)


@bp.post("/nmon/sample")
@require_feature("perf")
@require_role("admin")
def nmon_sample_page():
    result = collect_nmon_sample(current_user()["username"])
    audit_log_service.append("nmon.sample", current_user()["username"], {"count": result["count"]})
    return redirect(url_for("api_operations.nmon_page"))


@bp.post("/api/nmon/sample")
@require_feature("perf")
@require_role("admin")
def nmon_sample_api():
    result = collect_nmon_sample(current_user()["username"])
    audit_log_service.append("nmon.sample", current_user()["username"], {"count": result["count"]})
    return jsonify(result)


@bp.get("/api/nmon/report")
@require_feature("perf")
def nmon_report_api():
    return jsonify(nmon_report(request.args.get("period", "day")))
