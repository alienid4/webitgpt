from __future__ import annotations

from flask import Blueprint, Response, jsonify, request, send_file

from webapp.decorators import current_user, require_feature, require_role
from webapp.services import audit_log_service
from webapp.services import deep_check_service


bp = Blueprint("api_deep_check", __name__)


@bp.get("/api/deep-check/meta")
@require_feature("deep_check")
def meta_api():
    return jsonify({"success": True, **deep_check_service.meta()})


@bp.post("/api/deep-check/run")
@require_feature("deep_check")
@require_role("admin")
def run_api():
    payload = request.get_json(force=True, silent=True) or {}
    result = deep_check_service.run(payload.get("hostname", ""), current_user()["username"])
    audit_log_service.append("deep_check.run", current_user()["username"], result)
    return jsonify(result), 200 if result.get("success") else (409 if result.get("job_id") else 400)


@bp.post("/api/deep-check/cancel/<job_id>")
@require_feature("deep_check")
@require_role("admin")
def cancel_api(job_id: str):
    result = deep_check_service.cancel(job_id, current_user()["username"])
    audit_log_service.append("deep_check.cancel", current_user()["username"], result)
    return jsonify(result), 200 if result.get("success") else 404


@bp.get("/api/deep-check/progress/<job_id>")
@require_feature("deep_check")
def progress_api(job_id: str):
    result = deep_check_service.progress(job_id)
    return jsonify(result), 200 if result.get("success") else 404


@bp.get("/api/deep-check/reports")
@require_feature("deep_check")
def reports_api():
    return jsonify(deep_check_service.reports(request.args.get("hostname", "")))


@bp.get("/api/deep-check/history")
@require_feature("deep_check")
def history_api():
    limit = min(max(int(request.args.get("limit", 20)), 1), 100)
    return jsonify(deep_check_service.history(request.args.get("hostname", ""), limit))


@bp.get("/api/deep-check/reports/<filename>/preview")
@require_feature("deep_check")
def preview_api(filename: str):
    result = deep_check_service.preview(filename)
    audit_log_service.append("deep_check.preview", current_user()["username"], {"filename": filename})
    if not result.get("success"):
        return jsonify(result), 404
    return Response(
        result.get("content", ""),
        content_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"inline; filename={filename}"},
    )


@bp.get("/api/deep-check/reports/<filename>/parsed")
@require_feature("deep_check")
def parsed_api(filename: str):
    return jsonify(deep_check_service.parsed(filename))


@bp.get("/api/deep-check/reports/<filename>/download")
@require_feature("deep_check")
def download_api(filename: str):
    path = deep_check_service.download_path(filename)
    audit_log_service.append("deep_check.download", current_user()["username"], {"filename": filename})
    return send_file(path, as_attachment=True, download_name=filename, mimetype="text/plain")
