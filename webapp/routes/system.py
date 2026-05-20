from __future__ import annotations

from flask import Blueprint, Response, jsonify

from webapp.config import APP_NAME, BUILD_TIME, PATCH_ID, RELEASE_NOTE, VERSION
from webapp.services import mongo_service

bp = Blueprint("system", __name__)


@bp.get("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "app": APP_NAME,
            "version": VERSION,
            "patch_id": PATCH_ID,
            "release_note": RELEASE_NOTE,
            "build_time": BUILD_TIME,
        }
    )


@bp.get("/ready")
def ready():
    try:
        mongo = mongo_service.ping()
        status = "ok"
    except Exception as exc:  # pragma: no cover - depends on local mongo
        mongo = {"mongo": "fail", "error": str(exc)}
        status = "degraded"
    return jsonify({"status": status, **mongo, "edges": []})


@bp.get("/metrics")
def metrics():
    try:
        db = mongo_service.get_db()
        hosts_total = db.hosts.count_documents({})
    except Exception:
        hosts_total = 0
    body = "\n".join(
        [
            "# HELP webitgpt_hosts_total Total CMDB hosts",
            "# TYPE webitgpt_hosts_total gauge",
            f"webitgpt_hosts_total {hosts_total}",
            "# HELP webitgpt_build_info Build information",
            "# TYPE webitgpt_build_info gauge",
            f'webitgpt_build_info{{version="{VERSION}",patch_id="{PATCH_ID}",build_time="{BUILD_TIME}"}} 1',
            "",
        ]
    )
    return Response(body, mimetype="text/plain; version=0.0.4")
