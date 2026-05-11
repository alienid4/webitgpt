from __future__ import annotations

from flask import Blueprint, jsonify, request

from webapp.decorators import current_user, require_feature, require_role
from webapp import config
from webapp.services import audit_log_service
from webapp.services.llm_provider import get_provider, get_settings, save_settings

bp = Blueprint("api_ai", __name__)


@bp.post("/api/ai/chat")
@require_feature("ai_chat_panel")
def chat():
    payload = request.get_json(force=True, silent=True) or {}
    return jsonify(get_provider().chat(payload.get("message", ""), payload.get("context", {})))


@bp.get("/api/ai/mcp/manifest")
@require_feature("ai_mcp_server")
def mcp_manifest():
    return jsonify({"name": "webitgpt", "version": config.VERSION, "tools": []})


@bp.get("/api/ai/settings")
@require_role("superadmin")
def ai_settings_api():
    return jsonify(get_settings(masked=True))


@bp.post("/api/ai/settings")
@require_role("superadmin")
def ai_settings_update_api():
    payload = request.get_json(force=True, silent=True) or {}
    settings = save_settings(payload, current_user()["username"])
    audit_log_service.append("ai.settings.update", current_user()["username"], {"provider": settings.get("provider"), "enabled": settings.get("enabled")})
    return jsonify(settings)
