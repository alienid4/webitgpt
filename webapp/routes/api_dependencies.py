from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from webapp.decorators import current_user, require_feature, require_role
from webapp.services import audit_log_service
from webapp.services import dependency_service


bp = Blueprint("api_dependencies", __name__)


@bp.get("/dependencies/fullscreen")
@require_feature("dependencies")
def dependencies_fullscreen_page():
    data = dependency_service.topology(
        view=request.args.get("view", "system"),
        center=request.args.get("center", ""),
        depth=int(request.args.get("depth", 2)),
        limit=int(request.args.get("limit", 200)),
    )
    return render_template("dependencies.html", topology=data, fullscreen=True)


@bp.get("/dependencies/ghosts")
@require_feature("dependencies")
def dependencies_ghosts_page():
    return render_template("dependencies_ghosts.html", ghosts=dependency_service.analyze_ghosts())


@bp.get("/api/dependencies/systems")
@require_feature("dependencies")
def systems_api():
    return jsonify({"items": dependency_service.list_systems(request.args)})


@bp.post("/api/dependencies/systems")
@require_feature("dependencies")
@require_role("admin")
def system_create_api():
    doc = dependency_service.upsert_system(request.get_json(silent=True) or {}, current_user()["username"])
    audit_log_service.append("dependencies.system.upsert", current_user()["username"], {"system_id": doc.get("system_id")})
    return jsonify(doc)


@bp.get("/api/dependencies/systems/<system_id>")
@require_feature("dependencies")
def system_get_api(system_id: str):
    systems = {item["system_id"]: item for item in dependency_service.list_systems()}
    item = systems.get(system_id)
    return (jsonify(item), 200) if item else (jsonify({"error": "not found"}), 404)


@bp.put("/api/dependencies/systems/<system_id>")
@require_feature("dependencies")
@require_role("admin")
def system_update_api(system_id: str):
    payload = request.get_json(silent=True) or {}
    payload["system_id"] = system_id
    doc = dependency_service.upsert_system(payload, current_user()["username"])
    audit_log_service.append("dependencies.system.update", current_user()["username"], {"system_id": system_id})
    return jsonify(doc)


@bp.delete("/api/dependencies/systems/<system_id>")
@require_feature("dependencies")
@require_role("admin")
def system_delete_api(system_id: str):
    ok = dependency_service.delete_system(system_id)
    audit_log_service.append("dependencies.system.delete", current_user()["username"], {"system_id": system_id, "ok": ok})
    return jsonify({"ok": ok})


@bp.get("/api/dependencies/relations")
@require_feature("dependencies")
def relations_api():
    return jsonify({"items": dependency_service.list_relations(request.args)})


@bp.post("/api/dependencies/relations")
@require_feature("dependencies")
@require_role("admin")
def relation_create_api():
    doc = dependency_service.upsert_relation(request.get_json(silent=True) or {}, current_user()["username"])
    audit_log_service.append("dependencies.relation.upsert", current_user()["username"], {"from": doc.get("from_system"), "to": doc.get("to_system")})
    return jsonify(doc)


@bp.put("/api/dependencies/relations/<relation_id>")
@require_feature("dependencies")
@require_role("admin")
def relation_update_api(relation_id: str):
    payload = request.get_json(silent=True) or {}
    doc = dependency_service.upsert_relation(payload, current_user()["username"])
    audit_log_service.append("dependencies.relation.update", current_user()["username"], {"relation_id": relation_id})
    return jsonify(doc)


@bp.delete("/api/dependencies/relations/<relation_id>")
@require_feature("dependencies")
@require_role("admin")
def relation_delete_api(relation_id: str):
    ok = dependency_service.delete_relation(relation_id)
    audit_log_service.append("dependencies.relation.delete", current_user()["username"], {"relation_id": relation_id, "ok": ok})
    return jsonify({"ok": ok})


@bp.get("/api/dependencies/topology")
@require_feature("dependencies")
def topology_api():
    return jsonify(
        dependency_service.topology(
            view=request.args.get("view", "system"),
            center=request.args.get("center", ""),
            depth=int(request.args.get("depth", 2)),
            limit=int(request.args.get("limit", 200)),
        )
    )


@bp.get("/api/dependencies/impact")
@require_feature("dependencies")
def impact_api():
    system_id = request.args.get("system_id", "")
    direction = request.args.get("direction", "down")
    max_depth = int(request.args.get("max_depth", 3))
    result = dependency_service.upstream_impact(system_id, max_depth) if direction == "up" else dependency_service.downstream_impact(system_id, max_depth)
    return jsonify(result)


@bp.get("/api/dependencies/upstream")
@require_feature("dependencies")
def upstream_api():
    return jsonify(dependency_service.upstream_impact(request.args.get("system_id", ""), int(request.args.get("max_depth", 3))))


@bp.post("/api/dependencies/collect/trigger")
@require_feature("dependencies")
@require_role("admin")
def collect_trigger_api():
    return jsonify({"status": "queued", "message": "拓撲採集器骨架已建立；ss -tunp read-only runner 將在下一步接入。"})


@bp.get("/api/dependencies/collect/status/<run_id>")
@require_feature("dependencies")
def collect_status_api(run_id: str):
    return jsonify({"run_id": run_id, "status": "not_found"})


@bp.get("/api/dependencies/collect/schedule")
@require_feature("dependencies")
def collect_schedule_api():
    return jsonify({"interval_min": 60, "business_hours_only": True, "limit_hosts": 20, "enabled": False})


@bp.post("/api/dependencies/collect/schedule")
@require_feature("dependencies")
@require_role("superadmin")
def collect_schedule_update_api():
    return jsonify({"status": "saved", "schedule": request.get_json(silent=True) or {}})


@bp.get("/api/dependencies/collect/runs")
@require_feature("dependencies")
def collect_runs_api():
    return jsonify({"items": []})


@bp.get("/api/dependencies/ghosts")
@require_feature("dependencies")
def ghosts_api():
    return jsonify(dependency_service.analyze_ghosts())


@bp.post("/api/dependencies/ghosts/<ip>/adopt")
@require_feature("dependencies")
@require_role("admin")
def ghost_adopt_api(ip: str):
    payload = request.get_json(silent=True) or {}
    result = dependency_service.adopt_ghost(ip, payload.get("action", "ignore"), payload, current_user()["username"])
    audit_log_service.append("dependencies.ghost.adopt", current_user()["username"], {"ip": ip, "action": payload.get("action")})
    return jsonify(result)
