from __future__ import annotations

from flask import Blueprint, jsonify, request

from webapp import config
from webapp.decorators import require_api_scope, require_feature
from webapp.services import mongo_service
from webapp.services.host_service import list_hosts
from webapp.services.mask_service import mask_dict
from webapp.services.quality_service import operations_data_quality

bp = Blueprint("api_v1", __name__)


@bp.get("/api/v1/hosts")
@require_feature("external_api_v1")
@require_api_scope("hosts:read")
def hosts_v1():
    try:
        data = list_hosts(
            query=request.args.get("q", ""),
            page=int(request.args.get("page", "1")),
            page_size=int(request.args.get("page_size", "100")),
        )
    except Exception as exc:
        data = {"items": [], "total": 0, "page": 1, "page_size": 100, "error": str(exc)}
    data["items"] = [mask_dict(item) for item in data["items"]]
    return jsonify(data)


@bp.get("/api/v1/post-install/verify")
@require_feature("external_api_v1")
@require_api_scope("system:read")
def post_install_verify_v1():
    expected_version = request.args.get("expected_version", "").strip()
    checks: list[dict] = [
        {
            "name": "api_key",
            "ok": True,
            "status": "ok",
            "detail": "Bearer token accepted with system:read scope.",
        }
    ]

    version_ok = not expected_version or expected_version == config.VERSION
    checks.append(
        {
            "name": "version",
            "ok": version_ok,
            "status": "ok" if version_ok else "fail",
            "expected": expected_version or config.VERSION,
            "actual": config.VERSION,
        }
    )

    try:
        mongo = mongo_service.ping()
        mongo_ok = mongo.get("mongo") == "ok"
        checks.append({"name": "mongo", "ok": mongo_ok, "status": "ok" if mongo_ok else "fail", "detail": mongo})
    except Exception as exc:
        checks.append({"name": "mongo", "ok": False, "status": "fail", "detail": exc.__class__.__name__})

    try:
        quality = operations_data_quality()
        checks.append(
            {
                "name": "data_quality_api",
                "ok": True,
                "status": quality.get("status", "unknown"),
                "score": quality.get("score", 0),
                "warnings": quality.get("warnings", []),
            }
        )
    except Exception as exc:
        checks.append({"name": "data_quality_api", "ok": False, "status": "fail", "detail": exc.__class__.__name__})

    required_ok = all(item["ok"] for item in checks if item["name"] in {"api_key", "version", "mongo", "data_quality_api"})
    return jsonify(
        {
            "ok": required_ok,
            "status": "ok" if required_ok else "degraded",
            "app": config.APP_NAME,
            "version": config.VERSION,
            "patch_id": config.PATCH_ID,
            "build_time": config.BUILD_TIME,
            "checks": checks,
        }
    )


@bp.get("/api/v1/openapi.json")
@require_feature("ai_openapi_auto_doc")
def openapi_json():
    return jsonify(
        {
            "openapi": "3.0.0",
            "info": {"title": "webitgpt API", "version": config.VERSION},
            "paths": {
                "/api/v1/hosts": {"get": {"summary": "List CMDB hosts", "tags": ["hosts"]}},
                "/api/v1/post-install/verify": {"get": {"summary": "API key gated post-install verification", "tags": ["system"]}},
                "/api/compliance/dashboard": {"get": {"summary": "Compliance dashboard", "tags": ["compliance"]}},
                "/api/reports/summary": {"get": {"summary": "Executive summary", "tags": ["reports"]}},
                "/mcp/tools/{name}": {"post": {"summary": "Call MCP tool", "tags": ["ai"]}},
            },
            "x-ai-hints": {"common_filters": ["dc", "group_name", "environment", "host_type", "status"]},
        }
    )
