from __future__ import annotations

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from webapp.decorators import current_user, require_feature, require_role
from webapp.services import audit_log_service
from webapp.services import dependency_service


bp = Blueprint("api_dependencies", __name__)


def _include_external() -> bool:
    return request.args.get("include_external") in {"1", "true", "yes", "on"}


def _include_unmanaged() -> bool:
    return request.args.get("include_unmanaged") in {"1", "true", "yes", "on"}


def _focus_impact() -> bool:
    return request.args.get("focus_impact") in {"1", "true", "yes", "on"}


@bp.get("/dependencies/fullscreen")
@require_feature("dependencies")
def dependencies_fullscreen_page():
    collect_runs = dependency_service.collect_runs(limit=5)
    systems = dependency_service.list_systems()
    relations = dependency_service.list_relations()
    data = dependency_service.topology(
        view=request.args.get("view", "core_radial"),
        center=request.args.get("center", ""),
        depth=int(request.args.get("depth", 2)),
        limit=int(request.args.get("limit", 200)),
        include_external=_include_external(),
        include_unmanaged=_include_unmanaged(),
        failed_node=request.args.get("failed_node", ""),
        focus_impact=_focus_impact(),
    )
    return render_template(
        "dependencies.html",
        topology=data,
        fullscreen=True,
        reconcile_report=dependency_service.filtered_reconcile_report(include_external=_include_external(), include_unmanaged=_include_unmanaged()),
        network_scan_report=dependency_service.latest_network_scan_report(),
        collect_runs=collect_runs,
        systems=systems,
        relation_items=relations,
    )


@bp.post("/dependencies/relations")
@require_feature("dependencies")
@require_role("admin")
def relation_save_page():
    form = request.form
    remote_port = (form.get("remote_port") or "").strip()
    service_name = (form.get("service_name") or "").strip()
    evidence = {}
    if remote_port:
        evidence["remote_ports"] = [remote_port]
        evidence["last_remote_port"] = remote_port
    if service_name:
        evidence["service_name"] = service_name
        evidence["process_name"] = service_name
    doc = dependency_service.upsert_relation(
        {
            "from_system": form.get("from_system", "").strip(),
            "to_system": form.get("to_system", "").strip(),
            "rel_type": form.get("rel_type") or "depends_on",
            "source": "manual",
            "confidence": form.get("confidence") or 1.0,
            "description": form.get("description") or "",
            "evidence": evidence,
            "metadata": {"manual_note": form.get("manual_note") or ""},
        },
        current_user()["username"],
    )
    audit_log_service.append("dependencies.relation.page_save", current_user()["username"], {"from": doc.get("from_system"), "to": doc.get("to_system")})
    return redirect(request.referrer or url_for("api_reports.dependencies_page", view="core_radial", center=doc.get("from_system", "")))


@bp.post("/dependencies/relations/<relation_id>/delete")
@require_feature("dependencies")
@require_role("admin")
def relation_delete_page(relation_id: str):
    ok = dependency_service.delete_relation(relation_id)
    audit_log_service.append("dependencies.relation.page_delete", current_user()["username"], {"relation_id": relation_id, "ok": ok})
    return redirect(request.referrer or url_for("api_reports.dependencies_page", view="core_radial"))


@bp.get("/dependencies/ghosts")
@require_feature("dependencies")
def dependencies_ghosts_page():
    return render_template("dependencies_ghosts.html", ghosts=dependency_service.analyze_ghosts(include_external=_include_external()))


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
            view=request.args.get("view", "core_radial"),
            center=request.args.get("center", ""),
            depth=int(request.args.get("depth", 2)),
            limit=int(request.args.get("limit", 200)),
            include_external=_include_external(),
            include_unmanaged=_include_unmanaged(),
            failed_node=request.args.get("failed_node", ""),
            focus_impact=_focus_impact(),
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
    run = dependency_service.collect_topology(current_user()["username"])
    audit_log_service.append("dependencies.collect.trigger", current_user()["username"], {"run_id": run.get("run_id"), "status": run.get("status")})
    return jsonify(run)


@bp.post("/dependencies/collect/trigger")
@require_feature("dependencies")
@require_role("admin")
def collect_trigger_page():
    run = dependency_service.collect_topology(current_user()["username"])
    audit_log_service.append("dependencies.collect.trigger", current_user()["username"], {"run_id": run.get("run_id"), "status": run.get("status")})
    return redirect(url_for("api_reports.dependencies_page", view=request.form.get("view", "host"), collect_run=run.get("run_id"), collect_status=run.get("status")))


@bp.post("/api/dependencies/reconcile/trigger")
@require_feature("dependencies")
@require_role("admin")
def reconcile_trigger_api():
    report = dependency_service.reconcile_ss_nmap(current_user()["username"])
    audit_log_service.append("dependencies.reconcile.trigger", current_user()["username"], {"run_id": report.get("run_id"), "row_count": report.get("row_count"), "network_count": report.get("summary", {}).get("network_count", 0)})
    return jsonify(report)


@bp.post("/dependencies/reconcile/trigger")
@require_feature("dependencies")
@require_role("admin")
def reconcile_trigger_page():
    report = dependency_service.reconcile_ss_nmap(current_user()["username"])
    audit_log_service.append("dependencies.reconcile.trigger", current_user()["username"], {"run_id": report.get("run_id"), "row_count": report.get("row_count"), "network_count": report.get("summary", {}).get("network_count", 0)})
    return redirect(url_for("api_reports.dependencies_page", view=request.form.get("view", "host"), show_ports=1, reconcile_run=report.get("run_id"), reconcile_rows=report.get("row_count")))


@bp.get("/api/dependencies/reconcile/latest")
@require_feature("dependencies")
def reconcile_latest_api():
    return jsonify(dependency_service.latest_reconcile_report() or {"status": "empty"})


@bp.get("/api/dependencies/collect/status/<run_id>")
@require_feature("dependencies")
def collect_status_api(run_id: str):
    items = [item for item in dependency_service.collect_runs(limit=100) if item.get("run_id") == run_id]
    return (jsonify(items[0]), 200) if items else (jsonify({"run_id": run_id, "status": "not_found"}), 404)


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
    return jsonify({"items": dependency_service.collect_runs()})


@bp.get("/api/dependencies/ghosts")
@require_feature("dependencies")
def ghosts_api():
    return jsonify(dependency_service.analyze_ghosts(include_external=_include_external()))


@bp.post("/api/dependencies/ghosts/<ip>/adopt")
@require_feature("dependencies")
@require_role("admin")
def ghost_adopt_api(ip: str):
    payload = request.get_json(silent=True) or {}
    result = dependency_service.adopt_ghost(ip, payload.get("action", "ignore"), payload, current_user()["username"])
    audit_log_service.append("dependencies.ghost.adopt", current_user()["username"], {"ip": ip, "action": payload.get("action")})
    return jsonify(result)


@bp.post("/dependencies/ghosts/<ip>/ignore")
@require_feature("dependencies")
@require_role("admin")
def ghost_ignore_page(ip: str):
    result = dependency_service.adopt_ghost(ip, "ignore", {"reason": request.form.get("reason") or "由 Ghost 清單忽略"}, current_user()["username"])
    audit_log_service.append("dependencies.ghost.ignore", current_user()["username"], {"ip": ip, "status": result.get("status")})
    include_external = 1 if request.form.get("include_external") in {"1", "true", "yes", "on"} else 0
    return redirect(url_for("api_dependencies.dependencies_ghosts_page", include_external=include_external))
