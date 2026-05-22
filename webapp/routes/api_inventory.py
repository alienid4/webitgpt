from __future__ import annotations

from flask import Blueprint, Response, jsonify, redirect, render_template, request, url_for

from webapp.decorators import current_user, require_feature, require_module, require_role
from webapp.services import audit_log_service
from webapp.services.inventory_service import (
    account_inventory_view,
    account_excel_template_xlsx,
    collect_inventory,
    create_change_ticket,
    export_account_excel_diff_csv,
    export_inventory_diff_csv,
    export_accounts_csv,
    import_account_excel_inventory,
    inventory_diff_report,
    latest_inventory,
    list_change_tickets,
    save_account_usage_note,
    ssh_key_plan,
)
from webapp.services.legacy_parity_service import collect_software_inventory, software_csv, software_json

bp = Blueprint("api_inventory", __name__)


@bp.get("/accounts")
@require_module("module_compliance_security")
@require_feature("compliance_account")
def accounts_page():
    return render_template("accounts_inventory.html", title="帳號盤點", kind="accounts", account_view=account_inventory_view(dict(request.args)))


@bp.get("/accounts.csv")
@require_module("module_compliance_security")
@require_feature("compliance_account")
def accounts_csv():
    return Response(
        export_accounts_csv(dict(request.args)),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=accounts_inventory.csv"},
    )


@bp.get("/accounts/template.xlsx")
@require_module("module_compliance_security")
@require_feature("compliance_account")
def accounts_template_xlsx():
    return Response(
        account_excel_template_xlsx(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=account_inventory_template.xlsx"},
    )


@bp.post("/accounts/excel-upload")
@require_module("module_compliance_security")
@require_feature("compliance_account")
@require_role("admin")
def accounts_excel_upload():
    uploaded = request.files.get("file")
    if not uploaded:
        return redirect(url_for("api_inventory.accounts_page", tab="excel", upload_error="missing_file"))
    result = import_account_excel_inventory(uploaded.read(), uploaded.filename or "account_inventory.xlsx", current_user()["username"])
    audit_log_service.append("account_excel.upload", current_user()["username"], {"run_id": result.get("run_id"), "status": result.get("status"), "rows": result.get("row_count", 0)})
    return redirect(url_for("api_inventory.accounts_page", tab="excel", upload_run=result.get("run_id", "")) + "#excel")


@bp.get("/accounts/excel-diff.csv")
@require_module("module_compliance_security")
@require_feature("compliance_account")
def accounts_excel_diff_csv():
    return Response(
        export_account_excel_diff_csv(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=account_excel_vs_host_diff.csv"},
    )


@bp.post("/accounts/usage-note")
@require_module("module_compliance_security")
@require_feature("compliance_account")
@require_role("admin")
def accounts_usage_note_update():
    payload = dict(request.form)
    save_account_usage_note(
        payload.get("hostname", ""),
        payload.get("asset_seq", ""),
        payload.get("name", ""),
        payload.get("usage_note", ""),
        current_user()["username"],
        payload.get("owner", ""),
        payload.get("pam_managed") == "1",
        payload.get("apply_all") == "1",
        payload.get("platform_scope", ""),
    )
    audit_log_service.append("account_usage_note.update", current_user()["username"], {"name": payload.get("name", "")})
    return redirect(request.referrer or url_for("api_inventory.accounts_page"))


@bp.get("/software")
@require_module("module_compliance_security")
@require_feature("compliance_package")
def software_page():
    return render_template("inventory.html", title="軟體盤點", kind="software", inventory=software_json(dict(request.args)))


@bp.post("/software/collect")
@require_module("module_compliance_security")
@require_feature("compliance_package")
@require_role("admin")
def software_collect_page():
    result = collect_software_inventory(current_user()["username"], force=request.form.get("force") == "1")
    audit_log_service.append("software.collect", current_user()["username"], {"count": result["count"]})
    return redirect(url_for("api_inventory.software_page"))


@bp.get("/software.csv")
@require_module("module_compliance_security")
@require_feature("compliance_package")
def software_csv_page():
    return Response(
        software_csv(dict(request.args)),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=software_inventory.csv"},
    )


@bp.get("/software.json")
@require_module("module_compliance_security")
@require_feature("compliance_package")
def software_json_page():
    return jsonify(software_json(dict(request.args)))


@bp.get("/services")
def services_page():
    return render_template("inventory.html", title="服務管理", kind="services", inventory=latest_inventory("services"))


@bp.get("/ssh-keys")
def ssh_keys_page():
    return render_template("ssh_keys.html", plan=ssh_key_plan())


@bp.get("/changes")
def changes_page():
    return render_template("changes.html", tickets=list_change_tickets(), created=None)


@bp.post("/changes")
@require_role("admin")
def changes_create_page():
    doc = create_change_ticket(dict(request.form), current_user()["username"])
    audit_log_service.append("change_ticket.upsert", current_user()["username"], {"ticket_id": doc["ticket_id"]})
    return render_template("changes.html", tickets=list_change_tickets(), created=doc)


@bp.post("/api/inventory/<kind>/collect")
@require_role("admin")
def inventory_collect_api(kind: str):
    if kind not in {"accounts", "software", "services", "ssh_keys"}:
        return jsonify({"error": "unknown inventory kind"}), 404
    if kind == "software":
        payload = request.get_json(force=True, silent=True) or {}
        result = collect_software_inventory(current_user()["username"], force=bool(payload.get("force")), min_interval_minutes=int(payload.get("min_interval_minutes", 360)))
    else:
        payload = request.get_json(force=True, silent=True) or {}
        result = collect_inventory(
            kind,
            limit=int(payload.get("limit", 50)),
            user=current_user()["username"],
            force=bool(payload.get("force")),
            min_interval_minutes=int(payload.get("min_interval_minutes", 360)),
        )
    audit_log_service.append("inventory.collect", current_user()["username"], {"kind": kind, "count": result["count"]})
    return jsonify(result)


@bp.get("/api/inventory/<kind>")
def inventory_latest_api(kind: str):
    if kind not in {"accounts", "software", "services", "ssh_keys"}:
        return jsonify({"error": "unknown inventory kind"}), 404
    if kind == "software":
        return jsonify(software_json(dict(request.args)))
    return jsonify(latest_inventory(kind))


@bp.get("/api/inventory/<kind>/history")
def inventory_history_api(kind: str):
    if kind not in {"accounts", "software", "services", "ssh_keys"}:
        return jsonify({"error": "unknown inventory kind"}), 404
    from webapp.services.inventory_service import inventory_history

    return jsonify(inventory_history(kind))


@bp.get("/inventory/<kind>/diff-report")
def inventory_diff_report_page(kind: str):
    if kind not in {"accounts", "software", "services", "ssh_keys"}:
        return "unknown inventory kind", 404
    report = inventory_diff_report(kind, request.args.get("run_id", ""), request.args.get("change_type", ""))
    return render_template("inventory_diff_report.html", title="盤點差異報告", report=report)


@bp.get("/inventory/<kind>/diff-report.csv")
def inventory_diff_report_csv(kind: str):
    if kind not in {"accounts", "software", "services", "ssh_keys"}:
        return "unknown inventory kind", 404
    return Response(
        export_inventory_diff_csv(kind, request.args.get("run_id", ""), request.args.get("change_type", "")),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={kind}_inventory_diff_report.csv"},
    )


@bp.get("/api/inventory/<kind>/diff-report")
def inventory_diff_report_api(kind: str):
    if kind not in {"accounts", "software", "services", "ssh_keys"}:
        return jsonify({"error": "unknown inventory kind"}), 404
    return jsonify(inventory_diff_report(kind, request.args.get("run_id", ""), request.args.get("change_type", "")))


@bp.post("/api/ssh-keys/plan")
@require_role("admin")
def ssh_key_plan_api():
    payload = request.get_json(force=True, silent=True) or {}
    result = ssh_key_plan(payload.get("asset_seq"))
    audit_log_service.append("ssh_key.plan", current_user()["username"], {"count": result["count"]})
    return jsonify(result)


@bp.get("/api/changes")
def changes_api():
    return jsonify({"items": list_change_tickets()})


@bp.post("/api/changes")
@require_role("admin")
def changes_create_api():
    doc = create_change_ticket(request.get_json(force=True, silent=True) or {}, current_user()["username"])
    audit_log_service.append("change_ticket.upsert", current_user()["username"], {"ticket_id": doc["ticket_id"]})
    return jsonify(doc)
