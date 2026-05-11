from __future__ import annotations

from flask import Blueprint, jsonify

from webapp.decorators import monitored_write_blocked, require_role

bp = Blueprint("api_admin", __name__)


@bp.post("/api/admin/monitored-write/<operation>")
@require_role("admin")
@monitored_write_blocked
def monitored_write(operation: str):
    raise NotImplementedError(f"{operation} is disabled during parallel review")

