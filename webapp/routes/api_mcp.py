from __future__ import annotations

from flask import Blueprint, jsonify, request

from webapp.decorators import require_api_scope, require_feature
from webapp import config
from webapp.services.compliance_service import dashboard as compliance_dashboard
from webapp.services.feature_flags import is_enabled
from webapp.services.host_service import get_host, list_hosts
from webapp.services.mask_service import mask_dict

bp = Blueprint("api_mcp", __name__)


TOOLS = {
    "list_hosts": "List CMDB hosts",
    "get_host": "Get one CMDB host by asset sequence",
    "get_compliance_findings": "Get compliance dashboard findings",
    "get_dashboard_summary": "Get executive dashboard summary",
}


@bp.get("/mcp/manifest")
@require_feature("ai_mcp_server")
def manifest():
    return jsonify({"name": "webitgpt", "version": config.VERSION, "tools": [{"name": key, "description": value} for key, value in TOOLS.items()]})


@bp.post("/mcp/tools/<name>")
@require_feature("ai_mcp_server")
@require_api_scope("mcp:read")
def call_tool(name: str):
    payload = request.get_json(force=True, silent=True) or {}
    if name == "list_hosts":
        return jsonify(list_hosts(filters=payload.get("filters", {}), page=1, page_size=min(int(payload.get("limit", 50)), 100)))
    if name == "get_host":
        host = get_host(payload.get("asset_seq", "")) or {}
        return jsonify(mask_dict(host))
    if name == "get_compliance_findings":
        if not is_enabled("module_compliance_security", default=False):
            return jsonify({"error": "module disabled", "module": "module_compliance_security"}), 503
        return jsonify(compliance_dashboard())
    if name == "get_dashboard_summary":
        hosts = list_hosts(page=1, page_size=1)
        compliance = compliance_dashboard() if is_enabled("module_compliance_security", default=False) else {"open_findings": 0, "rules_total": 0}
        return jsonify({"hosts_total": hosts["total"], "open_findings": compliance["open_findings"], "rules_total": compliance["rules_total"]})
    return jsonify({"error": "unknown tool"}), 404
