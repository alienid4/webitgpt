from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, jsonify, request

from webapp import config
from webapp.decorators import current_user, require_feature, require_role
from webapp.services import audit_log_service, host_service
from webapp.services.mongo_service import get_collection
from webapp.services.runner_dispatcher import get_runner

bp = Blueprint("api_self_check", __name__)


@bp.post("/api/host/<asset_seq>/self_check")
@require_feature("host_self_check")
@require_role("admin")
def self_check(asset_seq: str):
    host = host_service.get_host(asset_seq)
    if not host:
        return jsonify({"error": "host not found"}), 404
    try:
        result = get_runner(host).self_check()
    except NotImplementedError as exc:
        result = {"status": "warn", "error": str(exc)}
    now = datetime.now(timezone.utc)
    target = Path(config.HOSTS_DIR) / asset_seq / "self_check" / f"{now.strftime('%Y%m%d_%H%M%S')}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    result["artifact_path"] = str(target)
    get_collection("hosts").update_one(
        {"asset_seq": asset_seq},
        {"$set": {"last_self_check_at": now, "last_self_check_status": result.get("status", "unknown")}},
    )
    audit_log_service.append("host.self_check", current_user()["username"], {"asset_seq": asset_seq, "status": result.get("status")})
    return jsonify(result)


@bp.post("/api/self_check/global")
@require_feature("host_self_check_global")
@require_role("admin")
def global_self_check():
    payload = request.get_json(force=True, silent=True) or {}
    requested_limit = payload.get("limit", request.args.get("limit", "10"))
    limit = min(max(int(requested_limit), 1), 20)
    hosts = host_service.list_hosts(page=1, page_size=limit)["items"]
    results = []
    for host in hosts:
        try:
            result = get_runner(host).self_check()
        except NotImplementedError as exc:
            result = {"status": "warn", "error": str(exc)}
        except TimeoutError as exc:
            result = {"status": "timeout", "error": str(exc)}
        except Exception as exc:
            result = {"status": "error", "error": str(exc)}
        now = datetime.now(timezone.utc)
        target = Path(config.HOSTS_DIR) / host["asset_seq"] / "self_check" / f"{now.strftime('%Y%m%d_%H%M%S')}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        result["artifact_path"] = str(target)
        get_collection("hosts").update_one(
            {"asset_seq": host["asset_seq"]},
            {"$set": {"last_self_check_at": now, "last_self_check_status": result.get("status", "unknown")}},
        )
        results.append({"asset_seq": host["asset_seq"], "hostname": host.get("hostname", ""), "status": result.get("status", "unknown"), "artifact_path": result.get("artifact_path", "")})
    audit_log_service.append("host.self_check.global", current_user()["username"], {"count": len(results), "limit": limit})
    return jsonify({"status": "ok", "count": len(results), "limit": limit, "read_only": True, "results": results})
