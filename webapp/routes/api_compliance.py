from __future__ import annotations

from flask import Blueprint, Response, jsonify, redirect, render_template, request, url_for

from webapp.decorators import current_user, require_feature, require_module, require_role
from webapp.services import audit_log_service
from webapp.services.compliance_service import (
    create_remediation_plan,
    dashboard,
    evaluate_host,
    export_findings_csv,
    export_twgcb_excel_html,
    host_audit_overview,
    list_remediation_plans,
    list_rules,
    rollback_remediation_plan,
    upsert_rule,
)

bp = Blueprint("api_compliance", __name__)


@bp.get("/security_audit")
@require_module("module_compliance_security")
@require_feature("compliance_engine")
def security_audit_page():
    return render_template(
        "security_audit.html",
        dashboard=dashboard(),
        host_overview=host_audit_overview(),
        plans=list_remediation_plans(),
        rules=list_rules(),
    )


@bp.post("/security_audit/evaluate/<asset_seq>")
@require_module("module_compliance_security")
@require_feature("compliance_engine")
@require_role("admin")
def evaluate_host_page(asset_seq: str):
    try:
        result = evaluate_host(asset_seq, current_user()["username"])
    except KeyError:
        return (
            render_template(
                "security_audit.html",
                dashboard=dashboard(),
                host_overview=host_audit_overview(),
                plans=list_remediation_plans(),
                rules=list_rules(),
                error=f"找不到主機：{asset_seq}",
            ),
            404,
        )
    audit_log_service.append("compliance.evaluate_host", current_user()["username"], {"asset_seq": asset_seq, "finding_count": result["finding_count"]})
    return redirect(url_for("api_compliance.security_audit_page"))


@bp.post("/api/compliance/evaluate/<asset_seq>")
@require_module("module_compliance_security")
@require_feature("compliance_engine")
@require_role("admin")
def evaluate_host_api(asset_seq: str):
    try:
        result = evaluate_host(asset_seq, current_user()["username"])
    except KeyError:
        return jsonify({"error": "host not found", "asset_seq": asset_seq}), 404
    audit_log_service.append("compliance.evaluate_host", current_user()["username"], {"asset_seq": asset_seq, "finding_count": result["finding_count"]})
    return jsonify(result)


@bp.get("/api/compliance/dashboard")
@require_module("module_compliance_security")
@require_feature("compliance_engine")
def dashboard_api():
    return jsonify(dashboard())


@bp.get("/api/compliance/rules")
@require_module("module_compliance_security")
@require_feature("compliance_engine")
def rules_api():
    return jsonify({"items": list_rules()})


@bp.post("/api/compliance/rules")
@require_module("module_compliance_security")
@require_feature("compliance_engine")
@require_role("superadmin")
def rule_upsert_api():
    rule = upsert_rule(request.get_json(force=True, silent=True) or {}, current_user()["username"])
    audit_log_service.append("compliance.rule.upsert", current_user()["username"], {"rule_id": rule["rule_id"]})
    return jsonify(rule)


@bp.post("/security_audit/rules")
@require_module("module_compliance_security")
@require_feature("compliance_engine")
@require_role("superadmin")
def rule_upsert_page():
    rule = upsert_rule(
        {
            "rule_id": request.form.get("rule_id", ""),
            "type": request.form.get("type", "setting"),
            "action": request.form.get("action", "blacklist"),
            "category": request.form.get("category", "white_box"),
            "target": request.form.get("target", ""),
            "severity": request.form.get("severity", "medium"),
            "compliance_ref": request.form.get("compliance_ref", ""),
            "active": request.form.get("active") == "on",
        },
        current_user()["username"],
    )
    audit_log_service.append("compliance.rule.upsert", current_user()["username"], {"rule_id": rule["rule_id"]})
    return redirect(url_for("api_compliance.security_audit_page"))


@bp.post("/security_audit/remediate/<asset_seq>/all")
@require_module("module_compliance_security")
@require_feature("compliance_engine")
@require_role("admin")
def remediate_all_page(asset_seq: str):
    try:
        plan = create_remediation_plan(asset_seq, user=current_user()["username"])
    except (KeyError, ValueError) as exc:
        return (
            render_template(
                "security_audit.html",
                dashboard=dashboard(),
                host_overview=host_audit_overview(),
                plans=list_remediation_plans(),
                rules=list_rules(),
                error=str(exc),
            ),
            400,
        )
    audit_log_service.append("compliance.remediation.plan", current_user()["username"], {"plan_id": plan["plan_id"], "asset_seq": asset_seq, "mode": "all"})
    return redirect(url_for("api_compliance.security_audit_page"))


@bp.post("/security_audit/remediate/<asset_seq>/<rule_id>")
@require_module("module_compliance_security")
@require_feature("compliance_engine")
@require_role("admin")
def remediate_one_page(asset_seq: str, rule_id: str):
    try:
        plan = create_remediation_plan(asset_seq, rule_id=rule_id, user=current_user()["username"])
    except (KeyError, ValueError) as exc:
        return (
            render_template(
                "security_audit.html",
                dashboard=dashboard(),
                host_overview=host_audit_overview(),
                plans=list_remediation_plans(),
                rules=list_rules(),
                error=str(exc),
            ),
            400,
        )
    audit_log_service.append("compliance.remediation.plan", current_user()["username"], {"plan_id": plan["plan_id"], "asset_seq": asset_seq, "rule_id": rule_id})
    return redirect(url_for("api_compliance.security_audit_page"))


@bp.post("/security_audit/rollback/<plan_id>")
@require_module("module_compliance_security")
@require_feature("compliance_engine")
@require_role("admin")
def rollback_page(plan_id: str):
    try:
        plan = rollback_remediation_plan(plan_id, current_user()["username"])
    except KeyError as exc:
        return (
            render_template(
                "security_audit.html",
                dashboard=dashboard(),
                host_overview=host_audit_overview(),
                plans=list_remediation_plans(),
                rules=list_rules(),
                error=str(exc),
            ),
            404,
        )
    audit_log_service.append("compliance.remediation.rollback", current_user()["username"], {"plan_id": plan_id, "status": plan["rollback_request"]["status"]})
    return redirect(url_for("api_compliance.security_audit_page"))


@bp.post("/api/compliance/remediate/<asset_seq>/all")
@require_module("module_compliance_security")
@require_feature("compliance_engine")
@require_role("admin")
def remediate_all_api(asset_seq: str):
    try:
        plan = create_remediation_plan(asset_seq, user=current_user()["username"])
    except KeyError:
        return jsonify({"error": "host not found", "asset_seq": asset_seq}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc), "asset_seq": asset_seq}), 400
    audit_log_service.append("compliance.remediation.plan", current_user()["username"], {"plan_id": plan["plan_id"], "asset_seq": asset_seq, "mode": "all"})
    return jsonify(plan)


@bp.post("/api/compliance/remediate/<asset_seq>/<rule_id>")
@require_module("module_compliance_security")
@require_feature("compliance_engine")
@require_role("admin")
def remediate_api(asset_seq: str, rule_id: str):
    try:
        plan = create_remediation_plan(asset_seq, rule_id=rule_id, user=current_user()["username"])
    except KeyError:
        return jsonify({"error": "host not found", "asset_seq": asset_seq}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc), "asset_seq": asset_seq, "rule_id": rule_id}), 400
    audit_log_service.append("compliance.remediation.plan", current_user()["username"], {"plan_id": plan["plan_id"], "asset_seq": asset_seq, "rule_id": rule_id})
    return jsonify(plan)


@bp.post("/api/compliance/rollback/<plan_id>")
@require_module("module_compliance_security")
@require_feature("compliance_engine")
@require_role("admin")
def rollback_api(plan_id: str):
    try:
        plan = rollback_remediation_plan(plan_id, current_user()["username"])
    except KeyError:
        return jsonify({"error": "plan not found", "plan_id": plan_id}), 404
    audit_log_service.append("compliance.remediation.rollback", current_user()["username"], {"plan_id": plan_id, "status": plan["rollback_request"]["status"]})
    return jsonify(plan)


@bp.get("/api/compliance/findings.csv")
@require_module("module_compliance_security")
@require_feature("compliance_engine")
def findings_csv():
    return Response(export_findings_csv(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=compliance_findings.csv"})


@bp.get("/twgcb.xlsx")
@require_module("module_compliance_security")
@require_feature("compliance_engine")
def twgcb_excel():
    return Response(
        export_twgcb_excel_html(),
        mimetype="application/vnd.ms-excel",
        headers={"Content-Disposition": "attachment; filename=twgcb_report.xls"},
    )
