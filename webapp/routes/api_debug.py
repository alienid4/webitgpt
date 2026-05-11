from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, jsonify

from webapp import config
from webapp.decorators import current_user, require_feature, require_role
from webapp.services import audit_log_service, host_service
from webapp.services.mask_service import mask_dict
from webapp.services.runner_dispatcher import get_runner

bp = Blueprint("api_debug", __name__)


@bp.post("/api/host/<asset_seq>/debug_snapshot")
@require_feature("host_debug_snapshot")
@require_role("admin")
def debug_snapshot(asset_seq: str):
    host = host_service.get_host(asset_seq)
    if not host:
        return jsonify({"error": "host not found"}), 404
    raw = get_runner(host).collect_debug_snapshot()
    masked = mask_dict(raw)
    now = datetime.now(timezone.utc)
    target = Path(config.HOSTS_DIR) / asset_seq / "debug_snapshots" / f"{now.strftime('%Y%m%d_%H%M%S')}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(masked, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    audit_log_service.append("host.debug_snapshot", current_user()["username"], {"asset_seq": asset_seq, "path": str(target)})
    return jsonify(masked)
