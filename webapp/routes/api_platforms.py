from __future__ import annotations

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from webapp.decorators import current_user, require_feature, require_role
from webapp.services import audit_log_service
from webapp.services.platform_service import list_vcenters, platform_status, save_vcenter, vmware_inventory

bp = Blueprint("api_platforms", __name__)


@bp.get("/vmware")
@require_feature("host_type_vmware")
def vmware_page():
    return render_template("vmware.html", inventory=vmware_inventory())


@bp.post("/vmware/credentials")
@require_feature("host_type_vmware")
@require_role("superadmin")
def save_vcenter_page():
    doc = save_vcenter(request.form.get("name", ""), request.form.get("url", ""), request.form.get("username", ""), request.form.get("password", ""), current_user()["username"])
    audit_log_service.append("vmware.credentials.save", current_user()["username"], {"name": doc["name"], "url": doc["url"]})
    return redirect(url_for("api_platforms.vmware_page"))


@bp.get("/api/vmware/inventory")
@require_feature("host_type_vmware")
def vmware_inventory_api():
    return jsonify(vmware_inventory())


@bp.post("/api/vmware/credentials")
@require_feature("host_type_vmware")
@require_role("superadmin")
def save_vcenter_api():
    payload = request.get_json(force=True, silent=True) or {}
    doc = save_vcenter(payload.get("name", ""), payload.get("url", ""), payload.get("username", ""), payload.get("password", ""), current_user()["username"])
    audit_log_service.append("vmware.credentials.save", current_user()["username"], {"name": doc["name"], "url": doc["url"]})
    return jsonify(doc)


@bp.get("/platforms")
def platforms_page():
    return render_template("platforms.html", status=platform_status(), vcenters=list_vcenters())


@bp.get("/api/platforms/status")
def platforms_status_api():
    return jsonify(platform_status())
