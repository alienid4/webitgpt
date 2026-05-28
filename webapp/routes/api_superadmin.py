from __future__ import annotations

import json
from pathlib import Path

from flask import Blueprint, Response, flash, jsonify, redirect, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename

from webapp import config
from webapp.decorators import current_user, require_role
from webapp.services import audit_log_service
from webapp.services.api_token_service import issue_token
from webapp.services.asset_governance_status_service import list_statuses as list_governance_statuses
from webapp.services.asset_governance_status_service import save_status as save_governance_status
from webapp.services.asset_governance_status_service import set_status_enabled as set_governance_status_enabled
from webapp.services.auth_service import generate_backup_codes, list_users, reset_password, set_user_locked, upsert_user
from webapp.services.debug_bundle_service import ai_runtime_manifest, collect_debug_bundle, create_ai_debug_loop, get_ai_debug_loop_prompt, list_debug_bundles
from webapp.services.feature_flags import DEFAULT_FLAGS, is_enabled, set_enabled, snapshot
from webapp.services.important_service_service import delete_rule as delete_service_rule
from webapp.services.important_service_service import list_rules as list_service_rules
from webapp.services.important_service_service import save_rule as save_service_rule
from webapp.services.important_service_service import set_rule_enabled as set_service_rule_enabled
from webapp.services.llm_provider import choose_key_tier, get_settings, save_settings
from webapp.services.log_exception_service import delete_rule, list_rules, save_rule, set_rule_enabled
from webapp.services.mongo_service import get_collection
from webapp.services.system_service import (
    MODULE_CATEGORY_LABELS,
    MODULE_IMPACT,
    admin_console_overview,
    create_backup_manifest,
    dev_console_payload,
    dr_drill,
    health_dashboard,
    job_schedule,
    log_tail,
    operation_logs,
    operation_logs_csv,
    patch_inventory,
    remote_tool_plan,
    rollback_plan,
    save_dev_note,
    save_dev_upload,
    settings_overview,
)
from webapp.services.token_cost_service import record_usage, token_cost_report

bp = Blueprint("api_superadmin", __name__)


FEATURE_CATEGORY_LABELS = MODULE_CATEGORY_LABELS


def feature_flag_groups() -> list[dict[str, object]]:
    enabled_map = snapshot()
    catalog = {flag["key"]: flag for flag in DEFAULT_FLAGS}
    compliance_parent_enabled = bool(enabled_map.get("module_compliance_security", False))
    groups: dict[str, list[dict[str, object]]] = {}
    for key in sorted(enabled_map):
        flag = catalog.get(key, {"key": key, "name": key, "description": "", "category": "system"})
        category = str(flag.get("category", "system"))
        impact = MODULE_IMPACT.get(key, {})
        is_compliance_child = category == "compliance" and key != "module_compliance_security"
        effective_enabled = bool(enabled_map[key]) and (compliance_parent_enabled or not is_compliance_child)
        groups.setdefault(category, []).append(
            {
                "key": key,
                "name": flag.get("name", key),
                "description": flag.get("description", ""),
                "enabled": bool(enabled_map[key]),
                "effective_enabled": effective_enabled,
                "scope": impact.get("scope") or flag.get("description", ""),
                "off_effect": impact.get("off_effect") or "關閉後前台入口與相關 API 會停止開放。",
                "recommendation": impact.get("recommendation") or "未完成或暫停使用時可關閉。",
                "parent_note": "受合規與資安大模組控制。" if is_compliance_child else "",
            }
        )
    ordered = ["module", "dev", "auth", "cmdb", "inspect", "host", "platform", "compliance", "system", "api", "ai", "notify"]
    return [
        {
            "key": category,
            "label": FEATURE_CATEGORY_LABELS.get(category, category),
            "flags": groups[category],
            "enabled_count": sum(1 for item in groups[category] if item["enabled"]),
            "total": len(groups[category]),
        }
        for category in ordered
        if category in groups
    ]


@bp.get("/superadmin")
@require_role("superadmin")
def superadmin_page():
    logs = list(get_collection("audit_logs").find({}, {"_id": 0}).sort("seq", -1).limit(50))
    audit_status = audit_log_service.verify_chain()
    return render_template("superadmin.html", feature_groups=feature_flag_groups(), logs=logs, audit_status=audit_status, console=admin_console_overview())


@bp.get("/superadmin/feature-parity")
@require_role("superadmin")
def feature_parity_page():
    legacy_modules = [
        {"module": "Dashboard", "legacy": "v3.17 KPI and host overview", "gpt": "Dashboard and executive summary", "status": "implemented", "gap": "Live KPI calibration remains environment-specific"},
        {"module": "Inspection", "legacy": "Linux/Windows/AIX/AS400 collectors", "gpt": "Read-only inspection API and demo host results", "status": "implemented", "gap": "Real AIX/AS400 endpoints still need site connection"},
        {"module": "Account inventory", "legacy": "CSV account inventory", "gpt": "Inventory API, history, cooldown and diff report", "status": "implemented", "gap": "Live write remediation stays blocked by phase_readonly_mode"},
        {"module": "CMDB / IPAM", "legacy": "Asset, network and IP records", "gpt": "Host CRUD, import/export, IPAM and nmap reconcile plan", "status": "implemented", "gap": "Production scan cadence needs owner confirmation"},
        {"module": "System admin", "legacy": "Settings, backup, patch and logs", "gpt": "SuperAdmin users, health, Backup/DR and rollback plan", "status": "implemented", "gap": "Real DR restore remains supervised"},
    ]
    spec_items = [
        "v3.17 module parity is tracked by visible routes, APIs and functional validation checks.",
        "Monitored-host write actions remain blocked while phase_readonly_mode is true.",
        "Patch rollback and DR operations are dry-run plans until the review phase closes.",
        "API, MCP and OpenAPI surfaces are token-gated where required.",
    ]
    return render_template("feature_parity.html", legacy_modules=legacy_modules, spec_items=spec_items)


@bp.post("/superadmin/features")
@require_role("superadmin")
def feature_update_page():
    key = request.form.get("key", "")
    enabled = request.form.get("enabled") == "on"
    if set_enabled(key, enabled, current_user()["username"]):
        audit_log_service.append("feature_flag.update", current_user()["username"], {"key": key, "enabled": enabled})
        flash(f"{key} 已{'啟用' if enabled else '停用'}")
    else:
        flash(f"找不到功能開關：{key}")
    return redirect(url_for("api_superadmin.superadmin_page"))


@bp.post("/superadmin/dev-console/features")
@require_role("superadmin")
def dev_console_feature_update_page():
    key = request.form.get("key", "")
    enabled = request.form.get("enabled") == "on"
    if set_enabled(key, enabled, current_user()["username"]):
        audit_log_service.append("feature_flag.update", current_user()["username"], {"key": key, "enabled": enabled, "source": "dev_console"})
        flash(f"{key} 已{'啟用' if enabled else '停用'}")
    else:
        flash(f"找不到功能開關：{key}")
    return redirect(url_for("api_superadmin.dev_console_page") + "#module-manager")


@bp.post("/api/superadmin/features/<key>")
@require_role("superadmin")
def feature_update_api(key: str):
    payload = request.get_json(force=True, silent=True) or {}
    if not set_enabled(key, bool(payload.get("enabled")), current_user()["username"]):
        return jsonify({"error": "feature not found"}), 404
    audit_log_service.append("feature_flag.update", current_user()["username"], {"key": key, "enabled": bool(payload.get("enabled"))})
    return jsonify({"key": key, "enabled": bool(payload.get("enabled"))})


@bp.get("/api/superadmin/audit/verify")
@require_role("superadmin")
def verify_audit():
    return jsonify(audit_log_service.verify_chain())


@bp.post("/api/superadmin/token")
@require_role("superadmin")
def token():
    payload = request.get_json(force=True, silent=True) or {}
    return jsonify(issue_token(payload.get("name", "api-token"), payload.get("scopes", ["hosts:read"]), "superadmin"))


@bp.get("/superadmin/tokens")
@require_role("superadmin")
def tokens_page():
    docs = list(get_collection("api_tokens").find({}, {"_id": 0, "token_hash": 0}).sort("created_at", -1).limit(50))
    return render_template("tokens.html", tokens=docs, issued=None)


@bp.post("/superadmin/tokens")
@require_role("superadmin")
def tokens_issue_page():
    scopes = [scope.strip() for scope in request.form.get("scopes", "hosts:read").split(",") if scope.strip()]
    issued = issue_token(request.form.get("name", "api-token"), scopes, "superadmin")
    audit_log_service.append("api_token.issue", "superadmin", {"name": request.form.get("name", "api-token"), "scopes": scopes})
    docs = list(get_collection("api_tokens").find({}, {"_id": 0, "token_hash": 0}).sort("created_at", -1).limit(50))
    return render_template("tokens.html", tokens=docs, issued=issued)


@bp.get("/superadmin/ai")
@require_role("superadmin")
def ai_page():
    return render_template("ai_settings.html", settings=get_settings(masked=True))


@bp.get("/superadmin/credentials")
@require_role("superadmin")
def credentials_page():
    tiers = [
        {
            "tier": "L1",
            "name": "探測帳號",
            "purpose": "確認連通、主機名稱、OS 線索與常見服務，不讀敏感資料。",
            "permission": "低權限，不允許 sudo 或寫入。",
            "examples": "ping、port、hostname、banner、基本 health check",
        },
        {
            "tier": "L2",
            "name": "盤點帳號",
            "purpose": "讀取資產盤點需要的 OS、套件、服務、帳號與效能資訊。",
            "permission": "read-only sudo 或受限指令白名單。",
            "examples": "os-release、systemctl、套件清單、帳號清單、NMON/效能資料",
        },
        {
            "tier": "L3",
            "name": "深度檢查帳號",
            "purpose": "事件排查時讀取 log、程序、網路與核心狀態，用於深度診斷。",
            "permission": "高權限，需 PAM、審核、時間限制與稽核紀錄。",
            "examples": "journal、kernel、process、socket、AP 服務狀態",
        },
    ]
    return render_template("credentials.html", tiers=tiers)


@bp.post("/superadmin/ai")
@require_role("superadmin")
def ai_update_page():
    key_tiers = []
    for tier in ["L1", "L2", "L3"]:
        key_tiers.append(
            {
                "tier": tier,
                "label": request.form.get(f"{tier}_label", ""),
                "model": request.form.get(f"{tier}_model", ""),
                "api_key": request.form.get(f"{tier}_api_key", ""),
                "monthly_limit_usd": request.form.get(f"{tier}_monthly_limit_usd", "0"),
                "max_check_level": request.form.get(f"{tier}_max_check_level", tier),
                "enabled": request.form.get(f"{tier}_enabled") == "on",
            }
        )
    settings = save_settings(
        {
            "provider": request.form.get("provider", "disabled"),
            "base_url": request.form.get("base_url", ""),
            "model": request.form.get("model", ""),
            "api_key": request.form.get("api_key", ""),
            "enabled": request.form.get("enabled") == "on",
            "budget_policy_enabled": request.form.get("budget_policy_enabled") == "on",
            "monthly_budget_usd": request.form.get("monthly_budget_usd", "0"),
            "fallback_strategy": request.form.get("fallback_strategy", "script_fallback"),
            "key_tiers": key_tiers,
        },
        current_user()["username"],
    )
    audit_log_service.append(
        "ai.settings.update",
        current_user()["username"],
        {
            "provider": settings.get("provider"),
            "enabled": settings.get("enabled"),
            "budget_policy_enabled": settings.get("budget_policy_enabled"),
            "key_tiers": [tier.get("tier") for tier in settings.get("key_tiers", []) if tier.get("enabled")],
        },
    )
    flash("AI provider settings saved")
    return redirect(url_for("api_superadmin.ai_page"))


@bp.get("/api/superadmin/ai/key-routing-preview")
@require_role("superadmin")
def ai_key_routing_preview_api():
    decision = choose_key_tier(
        check_level=request.args.get("level", "L1"),
        month_cost_usd=float(request.args.get("month_cost_usd") or 0),
        estimated_cost_usd=float(request.args.get("estimated_cost_usd") or 0),
    )
    return jsonify(decision)


@bp.get("/superadmin/token-costs")
@require_role("superadmin")
def token_costs_page():
    return render_template("token_costs.html", report=token_cost_report(request.args.get("month") or None))


@bp.get("/api/superadmin/token-costs")
@require_role("superadmin")
def token_costs_api():
    return jsonify(token_cost_report(request.args.get("month") or None))


@bp.post("/api/superadmin/token-usage")
@require_role("superadmin")
def token_usage_create_api():
    payload = request.get_json(force=True, silent=True) or {}
    doc = record_usage(
        action=payload.get("action", "manual_test"),
        model=payload.get("model", "default"),
        provider=payload.get("provider", "OpenAI"),
        input_tokens=int(payload.get("input_tokens") or 0),
        output_tokens=int(payload.get("output_tokens") or 0),
        actor=current_user()["username"],
        metadata={"source": "manual_api"},
    )
    audit_log_service.append("ai_token_usage.create", current_user()["username"], {"action": doc.get("action"), "total_tokens": doc.get("total_tokens")})
    if hasattr(doc.get("occurred_at"), "isoformat"):
        doc["occurred_at"] = doc["occurred_at"].isoformat()
    return jsonify(doc)


@bp.get("/superadmin/validation")
@require_role("superadmin")
def validation_page():
    path = Path(config.DATA_DIR) / "functional_validation_latest.json"
    report = None
    error = ""
    if path.exists():
        report = json.loads(path.read_text(encoding="utf-8"))
    else:
        error = "functional_validation_latest.json not found"
    return render_template("validation.html", report=report, error=error, dev_auto_login=is_enabled("dev_auto_login_superadmin", default=True))


@bp.post("/superadmin/dev-settings")
@require_role("superadmin")
def dev_settings_update_page():
    enabled = request.form.get("dev_auto_login_superadmin") == "on"
    set_enabled("dev_auto_login_superadmin", enabled, current_user()["username"])
    audit_log_service.append("dev_settings.update", current_user()["username"], {"dev_auto_login_superadmin": enabled})
    flash(f"Development auto-login {'enabled' if enabled else 'disabled'}")
    return redirect(url_for("api_superadmin.validation_page"))


@bp.get("/superadmin/users")
@require_role("superadmin")
def users_page():
    return render_template("users.html", users=list_users(), reset_result=None, backup_codes=None)


@bp.post("/superadmin/users")
@require_role("superadmin")
def users_upsert_page():
    user_doc = upsert_user(
        request.form.get("username", ""),
        request.form.get("role", "viewer"),
        request.form.get("email", ""),
        request.form.get("display_name", ""),
        request.form.get("password", ""),
        current_user()["username"],
    )
    audit_log_service.append("user.upsert", current_user()["username"], {"username": user_doc["username"], "role": user_doc["role"]})
    return redirect(url_for("api_superadmin.users_page"))


@bp.post("/superadmin/users/<username>/lock")
@require_role("superadmin")
def users_lock_page(username: str):
    locked = request.form.get("locked") == "on"
    set_user_locked(username, locked, current_user()["username"])
    audit_log_service.append("user.lock", current_user()["username"], {"username": username, "locked": locked})
    return redirect(url_for("api_superadmin.users_page"))


@bp.post("/superadmin/users/<username>/reset-password")
@require_role("superadmin")
def users_reset_password_page(username: str):
    result = reset_password(username, current_user()["username"])
    audit_log_service.append("user.password_reset", current_user()["username"], {"username": username})
    return render_template("users.html", users=list_users(), reset_result=result, backup_codes=None)


@bp.post("/superadmin/users/<username>/backup-codes")
@require_role("superadmin")
def users_backup_codes_page(username: str):
    result = generate_backup_codes(username)
    audit_log_service.append("user.backup_codes", current_user()["username"], {"username": username, "count": len(result["backup_codes"])})
    return render_template("users.html", users=list_users(), reset_result=None, backup_codes=result)


@bp.get("/api/superadmin/users")
@require_role("superadmin")
def users_api():
    return jsonify({"items": list_users()})


@bp.post("/api/superadmin/users")
@require_role("superadmin")
def users_upsert_api():
    payload = request.get_json(force=True, silent=True) or {}
    user_doc = upsert_user(
        payload.get("username", ""),
        payload.get("role", "viewer"),
        payload.get("email", ""),
        payload.get("display_name", ""),
        payload.get("password", ""),
        current_user()["username"],
    )
    audit_log_service.append("user.upsert", current_user()["username"], {"username": user_doc["username"], "role": user_doc["role"]})
    return jsonify(user_doc)


@bp.post("/api/superadmin/users/<username>/reset-password")
@require_role("superadmin")
def users_reset_password_api(username: str):
    result = reset_password(username, current_user()["username"])
    audit_log_service.append("user.password_reset", current_user()["username"], {"username": username})
    return jsonify(result)


@bp.post("/api/superadmin/users/<username>/lock")
@require_role("superadmin")
def users_lock_api(username: str):
    payload = request.get_json(force=True, silent=True) or {}
    locked = bool(payload.get("locked"))
    if not set_user_locked(username, locked, current_user()["username"]):
        return jsonify({"error": "user not found"}), 404
    audit_log_service.append("user.lock", current_user()["username"], {"username": username, "locked": locked})
    return jsonify({"username": username, "locked": locked})


@bp.get("/superadmin/system-health")
@require_role("superadmin")
def system_health_page():
    return render_template("system_health.html", health=health_dashboard())


@bp.get("/api/superadmin/system-health")
@require_role("superadmin")
def system_health_api():
    return jsonify(health_dashboard())


@bp.get("/superadmin/backup-dr")
@require_role("superadmin")
def backup_dr_page():
    return render_template("backup_dr.html", backup=None, drill=None)


@bp.post("/api/superadmin/backup/manifest")
@require_role("superadmin")
def backup_manifest_api():
    result = create_backup_manifest(current_user()["username"])
    audit_log_service.append("backup.manifest", current_user()["username"], {"path": result["path"]})
    return jsonify(result)


@bp.post("/api/superadmin/dr-drill")
@require_role("superadmin")
def dr_drill_api():
    result = dr_drill(current_user()["username"])
    audit_log_service.append("dr.drill", current_user()["username"], {"status": result["status"], "mode": result["mode"]})
    return jsonify(result)


@bp.get("/superadmin/patches")
@require_role("superadmin")
def patches_page():
    return render_template("patches.html", inventory=patch_inventory(), rollback=None)


@bp.get("/api/superadmin/patches")
@require_role("superadmin")
def patches_api():
    return jsonify(patch_inventory())


@bp.post("/api/superadmin/patches/rollback-plan")
@require_role("superadmin")
def rollback_plan_api():
    payload = request.get_json(force=True, silent=True) or {}
    result = rollback_plan(payload.get("target", "latest"), current_user()["username"])
    audit_log_service.append("patch.rollback_plan", current_user()["username"], {"target": result["target"]})
    return jsonify(result)


@bp.get("/superadmin/settings")
@require_role("superadmin")
def settings_page():
    return render_template("system_settings.html", overview=settings_overview())


@bp.get("/api/superadmin/settings")
@require_role("superadmin")
def settings_api():
    return jsonify(settings_overview())


@bp.get("/superadmin/logs")
@require_role("superadmin")
def logs_page():
    return render_template("system_logs.html", log=log_tail(request.args.get("name", "error")))


@bp.get("/api/superadmin/logs")
@require_role("superadmin")
def logs_api():
    return jsonify(log_tail(request.args.get("name", "error"), int(request.args.get("lines", 200))))


@bp.get("/superadmin/logs/download")
@require_role("superadmin")
def logs_download():
    log = log_tail(request.args.get("name", "error"), int(request.args.get("lines", 1000)))
    return Response(log["content"], mimetype="text/plain", headers={"Content-Disposition": f"attachment; filename=webitgpt_{log['name']}.log"})


@bp.get("/superadmin/log-exceptions")
@require_role("superadmin")
def log_exceptions_page():
    return render_template("log_exceptions.html", rules=list_rules(), saved=None, error="")


@bp.post("/superadmin/log-exceptions")
@require_role("superadmin")
def log_exceptions_save_page():
    try:
        rule = save_rule(
            {
                "rule_id": request.form.get("rule_id", ""),
                "name": request.form.get("name", ""),
                "pattern": request.form.get("pattern", ""),
                "match_type": request.form.get("match_type", "contains"),
                "scope": request.form.get("scope", "opening_log"),
                "reason": request.form.get("reason", ""),
                "owner": request.form.get("owner", ""),
                "enabled": request.form.get("enabled") == "on",
                "expires_days": request.form.get("expires_days", ""),
            },
            current_user()["username"],
        )
        audit_log_service.append("log_exception.save", current_user()["username"], {"rule_id": rule["rule_id"], "pattern": rule["pattern"]})
        return render_template("log_exceptions.html", rules=list_rules(), saved=rule, error="")
    except Exception as exc:
        return render_template("log_exceptions.html", rules=list_rules(), saved=None, error=str(exc)), 400


@bp.post("/superadmin/log-exceptions/<rule_id>/toggle")
@require_role("superadmin")
def log_exceptions_toggle_page(rule_id: str):
    enabled = request.form.get("enabled") == "on"
    set_rule_enabled(rule_id, enabled, current_user()["username"])
    audit_log_service.append("log_exception.toggle", current_user()["username"], {"rule_id": rule_id, "enabled": enabled})
    return redirect(url_for("api_superadmin.log_exceptions_page"))


@bp.post("/superadmin/log-exceptions/<rule_id>/delete")
@require_role("superadmin")
def log_exceptions_delete_page(rule_id: str):
    deleted = delete_rule(rule_id)
    audit_log_service.append("log_exception.delete", current_user()["username"], {"rule_id": rule_id, "deleted": deleted})
    return redirect(url_for("api_superadmin.log_exceptions_page"))


@bp.get("/api/superadmin/log-exceptions")
@require_role("superadmin")
def log_exceptions_api():
    return jsonify({"items": list_rules()})


@bp.get("/superadmin/important-services")
@require_role("superadmin")
def important_services_page():
    return render_template("important_services.html", rules=list_service_rules(), saved=None, error="")


@bp.post("/superadmin/important-services")
@require_role("superadmin")
def important_services_save_page():
    try:
        rule = save_service_rule(
            {
                "rule_id": request.form.get("rule_id", ""),
                "name": request.form.get("name", ""),
                "service_name": request.form.get("service_name", ""),
                "platform": request.form.get("platform", "linux"),
                "owner": request.form.get("owner", ""),
                "note": request.form.get("note", ""),
                "enabled": request.form.get("enabled") == "on",
            },
            current_user()["username"],
        )
        audit_log_service.append("important_service.save", current_user()["username"], {"rule_id": rule["rule_id"], "service_name": rule["service_name"]})
        return render_template("important_services.html", rules=list_service_rules(), saved=rule, error="")
    except Exception as exc:
        return render_template("important_services.html", rules=list_service_rules(), saved=None, error=str(exc)), 400


@bp.post("/superadmin/important-services/<rule_id>/toggle")
@require_role("superadmin")
def important_services_toggle_page(rule_id: str):
    enabled = request.form.get("enabled") == "on"
    set_service_rule_enabled(rule_id, enabled, current_user()["username"])
    audit_log_service.append("important_service.toggle", current_user()["username"], {"rule_id": rule_id, "enabled": enabled})
    return redirect(url_for("api_superadmin.important_services_page"))


@bp.post("/superadmin/important-services/<rule_id>/delete")
@require_role("superadmin")
def important_services_delete_page(rule_id: str):
    deleted = delete_service_rule(rule_id)
    audit_log_service.append("important_service.delete", current_user()["username"], {"rule_id": rule_id, "deleted": deleted})
    return redirect(url_for("api_superadmin.important_services_page"))


@bp.get("/api/superadmin/important-services")
@require_role("superadmin")
def important_services_api():
    return jsonify({"items": list_service_rules()})


@bp.get("/superadmin/asset-governance-statuses")
@require_role("superadmin")
def asset_governance_statuses_page():
    return render_template("asset_governance_statuses.html", statuses=list_governance_statuses(), saved=None, error="")


@bp.post("/superadmin/asset-governance-statuses")
@require_role("superadmin")
def asset_governance_statuses_save_page():
    try:
        status = save_governance_status(
            {
                "code": request.form.get("code", ""),
                "name": request.form.get("name", ""),
                "category": request.form.get("category", "待處理"),
                "risk": request.form.get("risk", "中"),
                "color": request.form.get("color", "orange"),
                "sort_order": request.form.get("sort_order", "500"),
                "visible_in_report": request.form.get("visible_in_report") == "on",
                "blocks_activation": request.form.get("blocks_activation") == "on",
                "requires_reason": request.form.get("requires_reason") == "on",
                "requires_expiry": request.form.get("requires_expiry") == "on",
                "auto_assignable": request.form.get("auto_assignable") == "on",
                "enabled": request.form.get("enabled") == "on",
                "description": request.form.get("description", ""),
            },
            current_user()["username"],
        )
        audit_log_service.append("asset_governance_status.save", current_user()["username"], {"code": status["code"], "name": status["name"]})
        return render_template("asset_governance_statuses.html", statuses=list_governance_statuses(), saved=status, error="")
    except Exception as exc:
        return render_template("asset_governance_statuses.html", statuses=list_governance_statuses(), saved=None, error=str(exc)), 400


@bp.post("/superadmin/asset-governance-statuses/<code>/toggle")
@require_role("superadmin")
def asset_governance_statuses_toggle_page(code: str):
    enabled = request.form.get("enabled") == "on"
    set_governance_status_enabled(code, enabled, current_user()["username"])
    audit_log_service.append("asset_governance_status.toggle", current_user()["username"], {"code": code, "enabled": enabled})
    return redirect(url_for("api_superadmin.asset_governance_statuses_page"))


@bp.get("/api/superadmin/asset-governance-statuses")
@require_role("superadmin")
def asset_governance_statuses_api():
    return jsonify({"items": list_governance_statuses()})


@bp.get("/superadmin/jobs")
@require_role("superadmin")
def jobs_page():
    return render_template("system_jobs.html", jobs=job_schedule())


@bp.get("/api/superadmin/jobs")
@require_role("superadmin")
def jobs_api():
    return jsonify(job_schedule())


@bp.get("/superadmin/audit-logs")
@require_role("superadmin")
def audit_logs_page():
    return render_template("operation_logs.html", logs=operation_logs())


@bp.get("/api/superadmin/audit-logs")
@require_role("superadmin")
def audit_logs_api():
    return jsonify({"items": operation_logs(int(request.args.get("limit", 200)))})


@bp.get("/superadmin/audit-logs.csv")
@require_role("superadmin")
def audit_logs_csv():
    return Response(operation_logs_csv(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=webitgpt_audit_logs.csv"})


@bp.get("/superadmin/remote-tools")
@require_role("superadmin")
def remote_tools_page():
    return render_template("remote_tools.html", plan=None)


@bp.post("/superadmin/remote-tools")
@require_role("superadmin")
def remote_tools_plan_page():
    plan = remote_tool_plan(request.form.get("action", ""), request.form.get("target", ""), request.form.get("service", ""))
    audit_log_service.append("remote_tools.plan", current_user()["username"], {"action": plan["action"], "target": plan["target"]})
    return render_template("remote_tools.html", plan=plan)


@bp.get("/superadmin/dev-console")
@require_role("superadmin")
def dev_console_page():
    return render_template("dev_console.html", console=dev_console_payload(), saved=None)


@bp.post("/superadmin/dev-console/notes")
@require_role("superadmin")
def dev_console_notes_page():
    saved = save_dev_note(request.form.get("notes", ""), current_user()["username"])
    audit_log_service.append("dev_console.notes", current_user()["username"], {"path": saved["path"]})
    return render_template("dev_console.html", console=dev_console_payload(), saved=saved)


@bp.post("/superadmin/dev-console/upload")
@require_role("superadmin")
def dev_console_upload_page():
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        flash("請先選擇要上傳的檔案。")
        return redirect(url_for("api_superadmin.dev_console_page") + "#file-manager")
    if request.content_length and request.content_length > 20 * 1024 * 1024:
        flash("檔案超過 20MB，請拆小後再上傳。")
        return redirect(url_for("api_superadmin.dev_console_page") + "#file-manager")
    filename = secure_filename(uploaded.filename)
    saved = save_dev_upload(filename, uploaded.read(), current_user()["username"])
    audit_log_service.append("dev_console.upload", current_user()["username"], {"path": saved["path"], "size": saved["size"]})
    return render_template("dev_console.html", console=dev_console_payload(), saved=saved)


@bp.get("/superadmin/dev-console/docs/<path:filename>")
@require_role("superadmin")
def dev_console_doc_download(filename: str):
    safe_name = secure_filename(filename)
    docs_dir = Path(config.DOCS_DIR)
    target = docs_dir / safe_name
    if safe_name and target.exists() and target.parent == docs_dir:
        return send_file(target, as_attachment=False, download_name=safe_name)
    flash("找不到指定的開發文件。")
    return redirect(url_for("api_superadmin.dev_console_page") + "#developer-docs")


@bp.post("/superadmin/dev-console/debug-bundle")
@require_role("superadmin")
def dev_console_debug_bundle_page():
    result = collect_debug_bundle(current_user()["username"], verbose=bool(request.form.get("verbose")))
    audit_log_service.append("dev_console.debug_bundle", current_user()["username"], {"bundle": result["bundle"], "size": result["size"]})
    flash(f"已產生 Debug Bundle：{result['bundle']}。")
    return redirect(url_for("api_superadmin.dev_console_page") + "#debug-bundle")


@bp.post("/superadmin/dev-console/ai-debug-loop")
@require_role("superadmin")
def dev_console_ai_debug_loop_page():
    result = create_ai_debug_loop(
        request.form.get("issue_title", ""),
        request.form.get("issue_detail", ""),
        current_user()["username"],
        verbose=bool(request.form.get("verbose")),
    )
    audit_log_service.append("dev_console.ai_debug_loop", current_user()["username"], {"loop_id": result["loop_id"], "bundle": result["bundle"]})
    flash(f"已建立 AI debug loop：{result['loop_id']}。")
    return redirect(url_for("api_superadmin.dev_console_page") + "#debug-bundle")


@bp.get("/superadmin/dev-console/ai-debug-loop/<loop_id>/prompt")
@require_role("superadmin")
def dev_console_ai_debug_loop_prompt_download(loop_id: str):
    item = get_ai_debug_loop_prompt(loop_id)
    if item:
        return send_file(item["path"], as_attachment=True, download_name=item["name"])
    flash("找不到指定的 AI debug loop prompt。")
    return redirect(url_for("api_superadmin.dev_console_page") + "#debug-bundle")


@bp.get("/superadmin/dev-console/ai-runtime-manifest")
@require_role("superadmin")
def dev_console_ai_runtime_manifest():
    return jsonify(ai_runtime_manifest())


@bp.get("/superadmin/dev-console/debug-bundle/<path:filename>")
@require_role("superadmin")
def dev_console_debug_bundle_download(filename: str):
    safe_name = secure_filename(filename)
    for item in list_debug_bundles(50):
        if item["name"] == safe_name:
            return send_file(item["path"], as_attachment=True, download_name=safe_name)
    flash("找不到指定的 Debug Bundle。")
    return redirect(url_for("api_superadmin.dev_console_page") + "#debug-bundle")
