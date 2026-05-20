from __future__ import annotations

from flask import Blueprint, jsonify, request

bp = Blueprint("api_edge", __name__)


@bp.post("/api/edge/push")
def edge_push():
    payload = request.get_json(force=True, silent=True) or {}
    return jsonify({"status": "accepted", "type": payload.get("type")})


@bp.get("/api/edge/pending_cmds")
def pending_cmds():
    return jsonify({"commands": []})

