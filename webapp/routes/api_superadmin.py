from __future__ import annotations

import json
from pathlib import Path

from flask import Blueprint, Response, flash, jsonify, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from webapp import config
from webapp.decorators import current_user, require_role
from webapp.services import audit_log_service
from webapp.services.api_token_service import issue_token
from webapp.services.auth_service import generate_backup_codes, list_users, reset_password, set_user_locked, upsert_user
from webapp.services.feature_flags import DEFAULT_FLAGS, is_enabled, set_enabled, snapshot
from webapp.services.llm_provider import get_settings, save_settings
from webapp.services.mongo_service import get_collection
from webapp.services.system_service import (
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
    save_dev_upload,
    save_dev_note,
    settings_overview,
)

bp = Blueprint("api_superadmin", __name__)


FEATURE_CATEGORY_LABELS = {
    "module": "模組",
    "cmdb": "CMDB",
    "inspect": "巡檢",
    "host": "主機操作",
    "platform": "平台支援",
    "compliance": "合規資安",
    "api": "API",
    "ai": "AI",
    "system": "系統",
    "auth": "認證",
    "dev": "開發",
    "notify": "通知",
}


FEATURE_DISPLAY = {
    "module_compliance_security": ("合規資安模組", "啟用 TWGCB、盤點與修補規劃功能"),
    "audit": ("稽核紀錄", "啟用操作稽核紀錄"),
    "packages": ("套件盤點", "啟用套件與軟體盤點"),
    "perf": ("效能監控", "啟用效能資料與 NMON 檢視"),
    "twgcb": ("TWGCB 規則", "啟用 TWGCB 類規則"),
    "summary": ("摘要報表", "啟用主管摘要"),
    "security_audit": ("安全稽核", "啟用合規稽核頁面"),
    "history": ("歷史紀錄", "啟用盤點歷史"),
    "dependencies": ("系統拓撲", "啟用系統關聯圖"),
    "cmdb_csv_import": ("CSV 匯入", "啟用 CMDB CSV 匯入"),
    "cmdb_saved_views": ("儲存檢視", "啟用主機列表儲存檢視"),
    "cmdb_manual_input": ("手動建檔", "啟用手動新增主機"),
    "cmdb_network_scan": ("網段掃描", "啟用 IPAM 掃描規劃"),
    "cmdb_extension_fields": ("擴充欄位", "啟用 CMDB 擴充欄位"),
    "cmdb_bulk_actions": ("批次操作", "啟用批次操作"),
    "cmdb_undo_30s": ("30 秒復原", "啟用刪除復原視窗"),
    "host_self_check": ("單機自檢", "啟用單台主機自檢"),
    "host_self_check_global": ("全站自檢", "啟用限量全站自檢"),
    "host_debug_snapshot": ("DEBUG 快照", "啟用遮罩後的主機 DEBUG 快照"),
    "host_security_audit_button": ("主機安全稽核", "啟用主機頁安全稽核按鈕"),
    "host_type_linux": ("Linux", "啟用 Linux 主機類型"),
    "host_type_windows": ("Windows", "啟用 Windows 主機類型"),
    "host_type_vmware": ("VMware", "啟用 VMware 主機類型"),
    "host_type_aix": ("AIX", "啟用 AIX 主機類型"),
    "host_type_as400": ("AS400", "啟用 AS400 主機類型"),
    "external_api_v1": ("外部 API v1", "啟用 Bearer token API"),
    "ai_chat_panel": ("AI 聊天面板", "啟用 AI 互動面板"),
    "ai_mcp_server": ("MCP Server", "啟用 MCP manifest 與 tools"),
    "ai_openapi_auto_doc": ("OpenAPI 文件", "啟用自動 API 文件"),
    "ai_report_summary": ("AI 報表摘要", "啟用 AI 摘要介面"),
    "ai_prompt_library": ("Prompt Library", "啟用提示詞庫"),
    "market_hours_protection": ("交易時段保護", "交易時段封鎖高風險變更"),
    "housekeeping_enabled": ("Housekeeping", "啟用系統清理任務"),
    "housekeeping_dry_run": ("Dry-run 清理", "清理任務預設 dry-run"),
    "backup_verify_enabled": ("備份驗證", "啟用備份可讀性檢查"),
    "disk_alert_enabled": ("磁碟警示", "啟用磁碟使用率檢查"),
    "audit_log_hash_chain": ("稽核雜湊鏈", "啟用稽核鏈驗證"),
    "mfa_required": ("MFA", "啟用 MFA 要求"),
    "force_single_login": ("單一登入", "限制同帳號登入"),
    "dev_auto_login_superadmin": ("開發自動登入", "本機開發自動登入 superadmin"),
    "compliance_engine": ("合規引擎", "啟用合規規則引擎"),
    "compliance_account": ("帳號規則", "啟用帳號類規則"),
    "compliance_package": ("套件規則", "啟用套件類規則"),
    "compliance_port": ("連接埠規則", "啟用連接埠類規則"),
    "compliance_process": ("程序規則", "啟用程序類規則"),
    "compliance_file": ("檔案規則", "啟用檔案類規則"),
    "compliance_ip": ("IP 規則", "啟用 IP 類規則"),
    "security_audit_whitebox": ("白箱稽核", "啟用主機白箱稽核"),
    "security_audit_blackbox": ("黑箱稽核", "啟用外部黑箱稽核"),
    "security_audit_blackbox_hydra": ("Hydra 黑箱檢查", "啟用登入風險檢查規劃"),
    "notify_email": ("Email 通知", "啟用 Email 通知"),
    "notify_slack": ("Slack 通知", "啟用 Slack 通知"),
    "notify_teams": ("Teams 通知", "啟用 Teams 通知"),
    "notify_jira": ("JIRA 整合", "啟用 JIRA 整合"),
    "phase_readonly_mode": ("Phase Read-only Mode", "平行審查期間封鎖受監控主機寫入"),
}



# Clean Traditional Chinese labels for the SuperAdmin UI. Keep this map here so
# existing Mongo rows with older/mojibake names still render cleanly.
FEATURE_CATEGORY_LABELS.update({
    "module": "大模組",
    "cmdb": "資產管理",
    "inspect": "巡檢報告",
    "host": "主機操作",
    "platform": "平台支援",
    "compliance": "合規與資安",
    "api": "對外 API",
    "ai": "AI 整合",
    "system": "系統控制",
    "auth": "認證與權限",
    "dev": "開發後台",
    "notify": "通知整合",
})
FEATURE_DISPLAY.update({
    "module_compliance_security": ("合規與資安大模組", "控制帳號盤點、軟體盤點、TWGCB 合規、安全稽核"),
    "audit": ("帳號盤點", "帳號盤點頁、清冊、歷史與差異比較"),
    "packages": ("軟體盤點", "軟體盤點、套件搜尋、版本變更追蹤"),
    "perf": ("效能月報 / NMON", "NMON 採樣、效能圖表與報表"),
    "twgcb": ("TWGCB 合規", "TWGCB 規則、設定、Excel 與報表"),
    "summary": ("異常總結", "主管摘要與異常彙整"),
    "security_audit": ("安全稽核", "主機資安缺口、修補計畫、備份與回復"),
    "history": ("歷史查詢", "巡檢、盤點與診斷歷史"),
    "dependencies": ("系統聯通圖 / 拓撲", "系統相依與拓撲圖"),
    "cmdb_csv_import": ("CSV 匯入匯出", "資產管理 CSV 匯入、匯出"),
    "cmdb_saved_views": ("常用篩選", "資產管理常用篩選"),
    "cmdb_manual_input": ("手動建檔", "新增主機與快速建立草稿"),
    "cmdb_network_scan": ("網段掃描 / IPAM", "IPAM、nmap 對帳與未納管清單"),
    "cmdb_extension_fields": ("擴充欄位", "資產管理自訂欄位"),
    "cmdb_bulk_actions": ("批次操作", "資產管理批次更新"),
    "cmdb_undo_30s": ("30 秒復原", "資產刪除短時間復原"),
    "host_self_check": ("單機自檢", "資產列表單台主機自檢"),
    "host_self_check_global": ("全域自檢", "資產管理批次或全域自檢"),
    "host_debug_snapshot": ("DEBUG 快照", "資產列表 DEBUG 快照與遮罩"),
    "host_security_audit_button": ("安全按鈕", "資產列表安全稽核按鈕"),
    "host_type_linux": ("Linux", "Linux runner"),
    "host_type_windows": ("Windows", "Windows runner"),
    "host_type_vmware": ("VMware", "VMware / vCenter runner"),
    "host_type_aix": ("AIX", "AIX SSH raw runner"),
    "host_type_as400": ("AS400", "AS400 尚未支援，保留邊界"),
    "external_api_v1": ("對外 API v1", "Bearer Token API"),
    "ai_chat_panel": ("AI 對話面板", "右下角 AI 對話視窗"),
    "ai_mcp_server": ("MCP Server", "MCP manifest 與工具清單"),
    "ai_openapi_auto_doc": ("OpenAPI 自動文件", "自動 API 文件"),
    "ai_report_summary": ("AI 報告摘要", "AI 輔助報告摘要"),
    "ai_prompt_library": ("提示詞庫", "AI 提示詞範本管理"),
    "market_hours_protection": ("盤中保護", "07:50-15:00 高風險變更管控"),
    "housekeeping_enabled": ("Housekeeping", "系統清理排程"),
    "housekeeping_dry_run": ("Housekeeping 試跑", "清理作業只試跑不刪除"),
    "backup_verify_enabled": ("備份驗證", "備份檢查與還原驗證"),
    "disk_alert_enabled": ("磁碟告警", "磁碟容量告警"),
    "audit_log_hash_chain": ("操作紀錄 Hash Chain", "防竄改操作紀錄雜湊鏈"),
    "mfa_required": ("MFA", "OTP/MFA 登入驗證"),
    "force_single_login": ("單一登入", "同一帳號單一有效 session"),
    "dev_auto_login_superadmin": ("開發自動登入最高管理員", "開發期間自動登入 superadmin"),
    "compliance_engine": ("合規規則引擎", "合規規則比對"),
    "compliance_account": ("帳號規則", "帳號盤點合規規則"),
    "compliance_package": ("套件規則", "套件合規規則"),
    "compliance_port": ("連接埠規則", "連接埠合規規則"),
    "compliance_process": ("程序規則", "程序合規規則"),
    "compliance_file": ("檔案規則", "檔案與權限合規規則"),
    "compliance_ip": ("IP 規則", "IP 與網段合規規則"),
    "security_audit_whitebox": ("白箱稽核", "登入主機後執行的安全稽核"),
    "security_audit_blackbox": ("黑箱稽核", "外部觀點安全稽核"),
    "security_audit_blackbox_hydra": ("Hydra 安全檢查", "密碼攻擊安全檢查占位功能"),
    "notify_email": ("Email 通知", "Email 通知整合"),
    "notify_slack": ("Slack 通知", "Slack 通知整合"),
    "notify_teams": ("Teams 通知", "Teams 通知整合"),
    "notify_jira": ("JIRA 整合", "JIRA 工單整合"),
    "phase_readonly_mode": ("Phase 只讀模式", "雙寫評比期間禁止對受監控主機寫入"),
})

def feature_flag_groups() -> list[dict[str, object]]:
    enabled_map = snapshot()
    catalog = {flag["key"]: flag for flag in DEFAULT_FLAGS}
    groups: dict[str, list[dict[str, object]]] = {}
    for key in sorted(enabled_map):
        flag = catalog.get(key, {"key": key, "name": key, "description": "", "category": "system"})
        display = FEATURE_DISPLAY.get(key)
        category = str(flag.get("category", "system"))
        groups.setdefault(category, []).append(
            {
                "key": key,
                "name": display[0] if display else flag.get("name", key),
                "description": display[1] if display else flag.get("description", ""),
                "enabled": bool(enabled_map[key]),
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
        {"module": "System admin", "legacy": "Settings, backup, patch and logs", "gpt": "SuperAdmin users, health, Backup/DR and rollback plan", "status": "implemented", "gap": "Real DR restore remains a supervised manual operation"},
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
        flash(f"{key} {'enabled' if enabled else 'disabled'}")
    else:
        flash(f"Feature flag not found: {key}")
    return redirect(url_for("api_superadmin.superadmin_page"))


@bp.post("/superadmin/dev-console/features")
@require_role("superadmin")
def dev_console_feature_update_page():
    key = request.form.get("key", "")
    enabled = request.form.get("enabled") == "on"
    if set_enabled(key, enabled, current_user()["username"]):
        audit_log_service.append("feature_flag.update", current_user()["username"], {"key": key, "enabled": enabled, "source": "dev_console"})
        flash(f"{key} {'已啟用' if enabled else '已停用'}")
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


@bp.post("/superadmin/ai")
@require_role("superadmin")
def ai_update_page():
    settings = save_settings(
        {
            "provider": request.form.get("provider", "disabled"),
            "base_url": request.form.get("base_url", ""),
            "model": request.form.get("model", ""),
            "api_key": request.form.get("api_key", ""),
            "enabled": request.form.get("enabled") == "on",
        },
        current_user()["username"],
    )
    audit_log_service.append("ai.settings.update", current_user()["username"], {"provider": settings.get("provider"), "enabled": settings.get("enabled")})
    flash("AI provider settings saved")
    return redirect(url_for("api_superadmin.ai_page"))


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
        flash("請先選擇要上傳的檔案")
        return redirect(url_for("api_superadmin.dev_console_page") + "#file-manager")
    if request.content_length and request.content_length > 20 * 1024 * 1024:
        flash("檔案超過 20MB，請拆小後再上傳")
        return redirect(url_for("api_superadmin.dev_console_page") + "#file-manager")
    filename = secure_filename(uploaded.filename)
    saved = save_dev_upload(filename, uploaded.read(), current_user()["username"])
    audit_log_service.append("dev_console.upload", current_user()["username"], {"path": saved["path"], "size": saved["size"]})
    return render_template("dev_console.html", console=dev_console_payload(), saved=saved)
