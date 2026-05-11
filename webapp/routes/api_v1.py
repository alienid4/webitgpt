from __future__ import annotations

from flask import Blueprint, jsonify, request

from webapp import config
from webapp.decorators import require_api_scope, require_feature
from webapp.services.host_service import list_hosts
from webapp.services.mask_service import mask_dict

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


@bp.get("/api/v1/openapi.json")
@require_feature("ai_openapi_auto_doc")
def openapi_json():
    return jsonify(
        {
            "openapi": "3.0.0",
            "info": {"title": "webitgpt API", "version": config.VERSION},
            "paths": {
                "/api/v1/hosts": {"get": {"summary": "List CMDB hosts", "tags": ["hosts"]}},
                "/api/compliance/dashboard": {"get": {"summary": "Compliance dashboard", "tags": ["compliance"]}},
                "/api/reports/summary": {"get": {"summary": "Executive summary", "tags": ["reports"]}},
                "/mcp/tools/{name}": {"post": {"summary": "Call MCP tool", "tags": ["ai"]}},
            },
            "x-ai-hints": {"common_filters": ["dc", "group_name", "environment", "host_type", "status"]},
        }
    )
