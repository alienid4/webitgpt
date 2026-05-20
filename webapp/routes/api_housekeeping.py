from __future__ import annotations

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from webapp.decorators import current_user, require_feature, require_role
from webapp.services import audit_log_service
from webapp.services.housekeeping_service import disk_status, list_tasks, run_all, run_task

bp = Blueprint("api_housekeeping", __name__)


@bp.get("/housekeeping")
@require_feature("housekeeping_enabled")
@require_role("superadmin")
def housekeeping_page():
    return render_template("housekeeping.html", tasks=list_tasks(), disk=disk_status())


@bp.post("/housekeeping/run/<task>")
@require_feature("housekeeping_enabled")
@require_role("superadmin")
def run_task_page(task: str):
    result = run_task(task, current_user()["username"], dry_run=request.form.get("dry_run") == "on")
    audit_log_service.append("housekeeping.run", current_user()["username"], {"task": task, "status": result["status"]})
    return redirect(url_for("api_housekeeping.housekeeping_page"))


@bp.post("/api/housekeeping/run/<task>")
@require_feature("housekeeping_enabled")
@require_role("superadmin")
def run_task_api(task: str):
    result = run_task(task, current_user()["username"], dry_run=bool((request.get_json(force=True, silent=True) or {}).get("dry_run", True)))
    audit_log_service.append("housekeeping.run", current_user()["username"], {"task": task, "status": result["status"]})
    return jsonify(result)


@bp.post("/api/housekeeping/run-all")
@require_feature("housekeeping_enabled")
@require_role("superadmin")
def run_all_api():
    result = run_all(current_user()["username"], dry_run=bool((request.get_json(force=True, silent=True) or {}).get("dry_run", True)))
    audit_log_service.append("housekeeping.run_all", current_user()["username"], {"status": result["status"], "count": result["count"]})
    return jsonify(result)


@bp.get("/api/housekeeping/tasks")
@require_feature("housekeeping_enabled")
@require_role("superadmin")
def tasks_api():
    return jsonify({"disk": disk_status(), "items": list_tasks()})
