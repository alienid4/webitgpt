from __future__ import annotations

import ipaddress

from flask import Blueprint, Response, abort, jsonify, redirect, render_template, request, url_for

from webapp.decorators import current_user, market_hours_protected, require_feature, require_role
from webapp.services import audit_log_service, cmdb_service, host_service, ipam_schedule_service
from webapp.services.csv_service import csv_template as build_csv_template
from webapp.services.csv_service import export_hosts_csv, import_csv, import_json, validate_csv, validation_errors_csv
from webapp.services.host_schema import ASSET_FIELDS, REQUIRED_FIELDS, ValidationError
from webapp.services.saved_view_service import delete_view, list_views, save_view

bp = Blueprint("api_hosts", __name__)


MANUAL_MULTI_FIELDS = ["asset_seq", "hostname", "ip", "host_type", "os", "connection"]

GLOBAL_SEARCH_TARGETS = [
    {"endpoint": "api_reports.dashboard_page", "keywords": ["A", "A.", "儀表板", "dashboard", "首頁"], "role": "viewer"},
    {"endpoint": "api_hosts.hosts_page", "keywords": ["B", "B.", "資產管理", "主機管理", "CMDB", "資產清冊", "主機清冊", "資產列表"], "role": "viewer"},
    {"endpoint": "api_hosts.asset_quality_page", "title": "資產異常清單", "group": "資產管理", "keywords": ["資產異常", "資產品質", "可信資產", "資料品質", "CMDB 異常", "IP 衝突", "未納管"], "role": "viewer"},
    {"endpoint": "api_inventory.accounts_page", "keywords": ["C", "C.", "帳號盤點", "帳號清冊", "高權限帳號", "PAM", "pam納管", "pam 納管"], "role": "viewer"},
    {"endpoint": "api_inventory.software_page", "keywords": ["D", "D.", "軟體盤點", "套件搜尋", "版本變更", "套件", "package", "software"], "role": "viewer"},
    {"endpoint": "api_operations.inspections_page", "title": "開門檢查", "group": "巡檢", "keywords": ["E", "E.", "開門檢查", "今日巡檢", "巡檢", "L1", "L3", "深度檢查", "deep check"], "role": "viewer"},
    {"endpoint": "api_reports.dependencies_page", "keywords": ["F", "F.", "系統拓撲", "拓撲", "關聯圖", "依賴圖", "系統依賴", "ss nmap", "nmap", "ghost"], "role": "viewer"},
    {"endpoint": "api_operations.nmon_page", "keywords": ["G", "G.", "效能月報", "效能", "nmon", "CPU", "記憶體", "磁碟趨勢"], "role": "viewer"},
    {"endpoint": "api_compliance.security_audit_page", "keywords": ["H", "H.", "TWGCB", "合規", "安全稽核", "資安", "修補", "rollback", "弱掃"], "role": "viewer"},
    {"endpoint": "api_reports.executive_page", "keywords": ["I", "I.", "主管儀表板", "主管", "高階主管", "executive"], "role": "viewer"},
    {"endpoint": "api_hosts.host_new_page", "keywords": ["新增主機", "新增資產", "CSV 匯入", "CSV匯入", "大量匯入", "掃描新增", "建立草稿", "新增"], "role": "admin"},
    {"endpoint": "api_hosts.ipam_page", "keywords": ["IPAM", "網段管理", "網段掃描", "IP 分配", "IP 保留", "未納管 IP", "未納管"], "role": "viewer"},
    {"endpoint": "api_hosts.extension_fields_page", "keywords": ["擴充欄位", "自訂欄位", "欄位管理", "新增欄位"], "role": "superadmin"},
    {"endpoint": "api_inventory.services_page", "keywords": ["服務管理", "服務盤點", "服務啟停", "service", "systemctl"], "role": "viewer"},
    {"endpoint": "api_inventory.ssh_keys_page", "keywords": ["SSH Key", "ssh key", "金鑰", "遠端金鑰"], "role": "viewer"},
    {"endpoint": "api_inventory.changes_page", "keywords": ["變更管理", "ticket", "rollback plan", "變更單"], "role": "viewer"},
    {"endpoint": "api_platforms.platforms_page", "keywords": ["平台支援", "Linux", "Windows", "AIX", "AS400", "VMware"], "role": "viewer"},
    {"endpoint": "api_platforms.vmware_page", "keywords": ["VMware", "vCenter", "虛擬化"], "role": "viewer"},
    {"endpoint": "api_superadmin.superadmin_page", "keywords": ["SA.A", "SA-A", "系統A", "系統管理", "後台", "后台", "superadmin", "超級管理員", "功能開關", "模組管理"], "role": "superadmin"},
    {"endpoint": "api_superadmin.users_page", "keywords": ["SA.B", "SA-B", "系統B", "使用者", "權限", "使用者與權限", "帳號權限", "角色"], "role": "superadmin"},
    {"endpoint": "api_superadmin.tokens_page", "keywords": ["SA.C", "SA-C", "系統C", "API Token", "token", "MCP token", "對外 API"], "role": "superadmin"},
    {"endpoint": "api_superadmin.ai_page", "keywords": ["SA.D", "SA-D", "系統D", "AI 供應商", "AI設定", "LLM", "Ollama", "OpenAI"], "role": "superadmin"},
    {"endpoint": "api_superadmin.system_health_page", "keywords": ["SA.E", "SA-E", "系統E", "健康檢查", "health", "ready", "metrics", "系統健康"], "role": "superadmin"},
    {"endpoint": "api_superadmin.settings_page", "keywords": ["SA.F", "SA-F", "系統F", "設定管理", "系統設定", "settings", "Mongo 設定"], "role": "superadmin"},
    {"endpoint": "api_superadmin.logs_page", "title": "日誌檢視", "group": "系統管理", "keywords": ["SA.G", "SA-G", "系統G", "日", "誌", "日誌檢視", "log", "error log", "access log", "日誌"], "role": "superadmin"},
    {"endpoint": "api_superadmin.jobs_page", "keywords": ["SA.H", "SA-H", "系統H", "工作排程", "排程", "scheduler", "timer", "systemd timer", "每週掃描"], "role": "superadmin"},
    {"endpoint": "api_superadmin.feature_parity_page", "keywords": ["功能驗證", "功能旗標", "feature flag", "feature flags", "開關"], "role": "superadmin"},
    {"endpoint": "api_superadmin.log_exceptions_page", "title": "系統日誌白名單 / 例外管理", "group": "系統管理", "keywords": ["系統日誌白名單", "日誌白名單", "例外管理", "log exception", "系統日誌例外"], "role": "superadmin"},
    {"endpoint": "api_superadmin.important_services_page", "keywords": ["重要服務設定", "重要服務", "sshd", "cron", "rsyslog", "AP service", "服務白名單"], "role": "superadmin"},
    {"endpoint": "api_superadmin.asset_governance_statuses_page", "keywords": ["資產治理狀態", "治理狀態", "等待防火牆", "防火牆開通", "等待弱掃", "弱掃完成", "等待 PAM", "PAM 納管", "asset governance"], "role": "superadmin"},
    {"endpoint": "api_superadmin.audit_logs_page", "title": "操作紀錄", "group": "系統管理", "keywords": ["操作紀錄", "稽核紀錄", "audit log", "hash chain", "操作日誌"], "role": "superadmin"},
    {"endpoint": "api_superadmin.backup_dr_page", "keywords": ["備份", "DR", "backup", "restore", "災難復原"], "role": "superadmin"},
    {"endpoint": "api_superadmin.patches_page", "keywords": ["Patch", "patch", "回滾", "版本", "release", "rollback"], "role": "superadmin"},
    {"endpoint": "api_superadmin.remote_tools_page", "keywords": ["遠端工具", "遠端", "remote tool", "Linux 初始化", "服務啟停"], "role": "superadmin"},
    {"endpoint": "api_superadmin.validation_page", "keywords": ["驗證報告", "功能驗證報告", "validation", "測試報告"], "role": "superadmin"},
    {"endpoint": "api_superadmin.dev_console_page", "keywords": ["開發後台", "開發后台", "developer", "dev console", "開發者文件", "文件", "檔案管理", "備忘錄", "提交紀錄", "模組管理"], "role": "superadmin"},
]

ASSET_FIELD_LABELS = {
    "division": "組織-處別",
    "department": "組織-部門",
    "asset_seq": "資產編號",
    "status": "資產狀態",
    "group_name": "主機群組",
    "apid": "APID",
    "asset_name": "資產名稱",
    "device_type": "設備類型",
    "device_model": "設備型號",
    "asset_usage": "資產用途",
    "location": "放置位置",
    "rack_no": "機櫃編號",
    "quantity": "數量",
    "owner": "資產擁有單位",
    "environment": "環境",
    "hostname": "主機名稱",
    "os": "作業系統",
    "bigip": "BIG IP / VIP",
    "hardware_seq": "硬體序號",
    "ip": "主要 IP",
    "custodian": "保管人",
    "sys_admin": "系統管理者",
    "user": "使用者",
    "user_unit": "使用單位",
    "note": "備註",
    "company": "公司別",
    "integrity": "完整性 I",
    "confidentiality": "機密性 C",
    "availability": "可用性 A",
    "ip_addresses": "所有 IP",
    "network_segments": "網段",
    "host_type": "主機類型",
    "dc": "機房",
    "connection": "連線方式",
    "ssh_user": "SSH / WinRM 使用者",
    "ssh_port": "SSH 連接埠",
    "tier": "重要等級",
    "ap_owner": "AP 負責人",
    "system_name": "系統名稱",
    "os_group": "OS 分類",
}

ASSET_STATUS_LABELS = {
    "active": "使用中",
    "draft": "草稿",
    "pending_ip": "待分配 IP",
    "pending_data": "待補資料",
    "pending_deploy": "待部署",
    "disabled": "停用",
    "retired": "已汰除",
    "pending_retire": "待汰除",
}

HOST_FORM_ERROR_MESSAGES = {
    "server hosts require connection": ("connection", "連線方式未設定：Linux / Windows / AIX / AS400 等伺服器主機，請選擇 SSH、WinRM、SSH Raw、本機等連線方式。"),
    "server hosts require os": ("os", "作業系統未填：伺服器主機請填寫實際 OS，例如 Rocky Linux 9.7、Debian 13、Windows Server 2019。"),
    "hostname is required and must be unique": ("hostname", "主機名稱未填或重複：主機名稱是唯一索引，請填寫不重複的 hostname。"),
    "ip must be a valid IPv4/IPv6 address": ("ip", "主要 IP 格式不正確：請填 IPv4 或 IPv6，例如 192.168.1.110。"),
    "vmware hosts require connection=vcenter_api": ("connection", "VMware 資產的連線方式需選 vCenter API，或先保持草稿狀態。"),
}

HOST_FORM_WARNING_MESSAGES = {
    "asset_seq should look like HW-XXXXXXXX": ("asset_seq", "資產編號格式提醒：正式資產建議使用 HW-XXXXXXXX。掃描草稿若還沒有正式資產編號，可先保持草稿或待補資料。"),
}

HOST_TYPE_LABELS = {
    "linux": "Linux",
    "windows": "Windows",
    "aix": "AIX",
    "as400": "AS400",
    "vmware_host": "VMware 主機",
    "vmware_vm": "VMware VM",
    "vmware_vcenter": "vCenter",
    "network_device": "網路設備",
    "end_device": "端點設備",
}

DC_LABELS = {"dunan": "敦南", "neihu": "內湖", "banciao": "板橋"}


def _role_allowed(required: str) -> bool:
    role_order = {"viewer": 0, "admin": 1, "super": 2, "superadmin": 3}
    user_role = current_user().get("role", "viewer")
    return role_order.get(user_role, 0) >= role_order.get(required, 0)


def _translate_host_form_messages(messages: list[str], warning: bool = False) -> tuple[list[str], list[str]]:
    translated: list[str] = []
    fields: list[str] = []
    mapping = HOST_FORM_WARNING_MESSAGES if warning else HOST_FORM_ERROR_MESSAGES
    for message in messages or []:
        field = ""
        text = message
        if message in mapping:
            field, text = mapping[message]
        elif message.endswith(" is required"):
            field = message.removesuffix(" is required")
            text = f"{ASSET_FIELD_LABELS.get(field, field)}未填：請補齊這個必填欄位。"
        elif message.startswith("ip_addresses contains invalid IP:"):
            field = "ip_addresses"
            text = f"所有 IP 內有格式不正確的 IP：{message.split(':', 1)[1].strip()}。"
        elif message.startswith("network_segments contains invalid CIDR:"):
            field = "network_segments"
            text = f"網段格式不正確：{message.split(':', 1)[1].strip()}。"
        elif " must be an integer 0-3" in message or " must be 0-3" in message:
            field = message.split(" ", 1)[0]
            text = f"{ASSET_FIELD_LABELS.get(field, field)}請填 0 到 3 的數字。"
        if field:
            fields.append(field)
        translated.append(text)
    return translated, sorted(set(fields))


def _normalize_search_text(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _keyword_matches(query: str, keyword: str) -> bool:
    key = _normalize_search_text(keyword)
    if not key:
        return False
    if query == key:
        return True
    if len(key) <= 3 or len(query) <= 3:
        return False
    return key in query or query in key


def _keyword_related(query: str, keyword: str) -> bool:
    key = _normalize_search_text(keyword)
    if not key:
        return False
    if query == key:
        return True
    if len(query) == 1:
        return query in key
    if len(key) <= 3 or len(query) <= 3:
        return False
    return key in query or query in key


def _is_direct_search_code(value: str) -> bool:
    text = _normalize_search_text(value).replace("-", ".")
    if len(text) == 1 and text.isascii() and text.isalnum():
        return True
    if "." in text:
        left, _, right = text.partition(".")
        return bool(left and right) and left.isascii() and right.isascii()
    return False


def _search_target_title(target: dict, fallback_keyword: str) -> str:
    if target.get("title"):
        return target["title"]
    for keyword in target["keywords"]:
        normalized = _normalize_search_text(keyword)
        if normalized and not _is_direct_search_code(normalized) and len(normalized) > 1:
            return keyword
    return fallback_keyword


@bp.get("/search")
@require_role("viewer")
def global_search_page():
    query = request.args.get("q", "").strip()
    normalized = _normalize_search_text(query)
    if not normalized:
        return redirect(url_for("api_hosts.hosts_page"))

    exact_matches = []
    related_results = []
    seen_endpoints = set()
    for target in GLOBAL_SEARCH_TARGETS:
        if not _role_allowed(target["role"]):
            continue
        for keyword in target["keywords"]:
            exact = _keyword_matches(normalized, keyword)
            related = exact or _keyword_related(normalized, keyword)
            if exact:
                exact_matches.append(target)
            if related and target["endpoint"] not in seen_endpoints:
                seen_endpoints.add(target["endpoint"])
                related_results.append({
                    "title": _search_target_title(target, keyword),
                    "group": target.get("group", "功能"),
                    "role": target["role"],
                    "matched_keyword": keyword,
                    "url": url_for(target["endpoint"]),
                })
            if related:
                break

    if len(exact_matches) == 1 and _is_direct_search_code(normalized):
        return redirect(url_for(exact_matches[0]["endpoint"]))
    if len(related_results) == 1 and len(normalized) > 1:
        return redirect(related_results[0]["url"])
    if related_results:
        return render_template("search_results.html", query=query, results=related_results)

    return redirect(url_for("api_hosts.hosts_page", q=query))

EDIT_FIELDS = [
    "division", "department", "asset_seq", "status", "group_name", "apid",
    "asset_name", "device_type", "device_model", "asset_usage", "location", "rack_no",
    "quantity", "owner", "environment", "hostname", "os", "bigip", "hardware_seq", "ip",
    "ip_addresses", "network_segments", "custodian", "sys_admin", "user", "user_unit",
    "note", "company", "integrity", "confidentiality", "availability", "host_type", "dc",
    "connection", "ssh_user", "ssh_port", "tier", "ap_owner", "system_name", "os_group",
]


def _asset_page_summary(items: list[dict]) -> dict:
    missing_required = 0
    complete_assets = 0
    for item in items:
        missing = [field for field in REQUIRED_FIELDS if item.get(field) in (None, "")]
        missing_required += len(missing)
        if not missing:
            complete_assets += 1
    return {
        "complete_assets": complete_assets,
        "missing_required": missing_required,
        "environments": len({item.get("environment") for item in items if item.get("environment")}),
        "types": len({item.get("host_type") for item in items if item.get("host_type")}),
    }


def _host_form_data() -> dict:
    data = dict(request.form)
    for field in ("ip_addresses", "network_segments"):
        if field in data:
            data[field] = data[field].replace("\r", "\n")
    extensions = {}
    for key, value in list(data.items()):
        if key.startswith("ext__"):
            extensions[key[5:]] = value
            data.pop(key, None)
    if extensions:
        data["extensions"] = extensions
    return data


def _host_new_context(**extra: dict) -> dict:
    last_scan_report = cmdb_service.latest_network_reconcile("") or None
    context = {
        "errors": None,
        "import_result": None,
        "scan_report": last_scan_report,
        "scan_created": None,
        "scan_skipped": None,
        "ipam_networks": cmdb_service.list_networks(),
        "host_type_labels": HOST_TYPE_LABELS,
        "dc_labels": DC_LABELS,
        "status_labels": ASSET_STATUS_LABELS,
    }
    context.update(extra)
    return context


@bp.get("/")
def index():
    return redirect(url_for("api_hosts.hosts_page"))


@bp.get("/hosts")
@require_feature("cmdb_manual_input")
def hosts_page():
    params = {
        "query": request.args.get("q", ""),
        "filters": {
            "status": request.args.get("status", ""),
            "group_name": request.args.get("group_name", ""),
            "environment": request.args.get("environment", ""),
            "host_type": request.args.get("host_type", ""),
            "dc": request.args.get("dc", ""),
        },
        "page": int(request.args.get("page", "1")),
        "page_size": int(request.args.get("page_size", "25")),
    }
    try:
        data = host_service.list_hosts(**params)
    except Exception as exc:
        data = {"items": [], "total": 0, "page": 1, "page_size": 25, "error": str(exc)}
    user = current_user()
    saved_views = [] if user["username"] == "anonymous" else list_views(user["username"])
    return render_template(
        "hosts.html",
        data=data,
        q=params["query"],
        saved_views=saved_views,
        asset_fields=ASSET_FIELDS,
        asset_field_labels=ASSET_FIELD_LABELS,
        required_fields=REQUIRED_FIELDS,
        status_labels=ASSET_STATUS_LABELS,
        host_type_labels=HOST_TYPE_LABELS,
        dc_labels=DC_LABELS,
        asset_summary=_asset_page_summary(data.get("items", [])),
        status_counts=host_service.status_counts(),
        refresh_result=None,
    )


@bp.post("/hosts/refresh-identity")
@require_feature("cmdb_manual_input")
@require_role("admin")
def hosts_refresh_identity_submit():
    scope = request.form.get("scope", "page")
    filters = {
        "status": request.form.get("status", ""),
        "group_name": request.form.get("group_name", ""),
        "environment": request.form.get("environment", ""),
        "host_type": request.form.get("host_type", ""),
        "dc": request.form.get("dc", ""),
    }
    page = int(request.form.get("page", "1") or 1)
    page_size = int(request.form.get("page_size", "25") or 25)
    current_page_only = scope != "all"
    keys = host_service.list_matching_host_keys(
        query=request.form.get("q", ""),
        filters=filters,
        page=page,
        page_size=page_size,
        current_page_only=current_page_only,
    )
    result = cmdb_service.refresh_asset_identities(keys, user=current_user()["username"])
    audit_log_service.append("host.identity.refresh", current_user()["username"], {"scope": scope, **{k: result[k] for k in ["total", "updated_count", "failed_count", "skipped_count"]}})
    params = {
        "q": request.form.get("q", ""),
        "status": request.form.get("status", ""),
        "group_name": request.form.get("group_name", ""),
        "environment": request.form.get("environment", ""),
        "host_type": request.form.get("host_type", ""),
        "dc": request.form.get("dc", ""),
        "page": str(page),
        "page_size": str(page_size),
        "refresh_updated": str(result["updated_count"]),
        "refresh_failed": str(result["failed_count"]),
        "refresh_skipped": str(result["skipped_count"]),
        "refresh_scope": scope,
    }
    return redirect(url_for("api_hosts.hosts_page", **params))


@bp.get("/hosts/quality")
@require_feature("cmdb_manual_input")
def asset_quality_page():
    report = cmdb_service.asset_quality_report()
    return render_template(
        "asset_quality.html",
        report=report,
        status_labels=ASSET_STATUS_LABELS,
        host_type_labels=HOST_TYPE_LABELS,
    )


@bp.get("/hosts/new")
@require_feature("cmdb_manual_input")
def host_new_page():
    return render_template("host_new.html", **_host_new_context())


@bp.get("/hosts/new/full")
@require_feature("cmdb_manual_input")
def host_new_full_page():
    return render_template(
        "host_edit.html",
        host={},
        edit_fields=EDIT_FIELDS,
        field_labels=ASSET_FIELD_LABELS,
        required_fields=REQUIRED_FIELDS,
        ipam_networks=cmdb_service.list_networks(),
        extension_definitions=cmdb_service.list_extension_definitions(),
        mode="new",
    )


@bp.post("/hosts/new")
@require_feature("cmdb_manual_input")
@require_role("admin")
@market_hours_protected
def host_new_submit():
    try:
        host = host_service.create_host(_host_form_data(), user=current_user()["username"])
        audit_log_service.append("host.create", current_user()["username"], {"hostname": host["hostname"], "asset_seq": host["asset_seq"]})
        return redirect(url_for("api_hosts.host_edit_page", asset_seq=host["hostname"]))
    except ValidationError as exc:
        errors, error_fields = _translate_host_form_messages(exc.errors)
        warnings, warning_fields = _translate_host_form_messages(exc.warnings, warning=True)
        return render_template(
            "host_edit.html",
            host=_host_form_data(),
            edit_fields=EDIT_FIELDS,
            field_labels=ASSET_FIELD_LABELS,
            required_fields=REQUIRED_FIELDS,
            ipam_networks=cmdb_service.list_networks(),
            extension_definitions=cmdb_service.list_extension_definitions(),
            mode="new",
            errors=errors,
            warnings=warnings,
            error_fields=error_fields,
            warning_fields=warning_fields,
        ), 400


@bp.post("/hosts/import/csv")
@require_feature("cmdb_csv_import")
@require_role("admin")
@market_hours_protected
def host_import_csv_page():
    text = request.form.get("csv_text", "")
    if not text and request.files.get("csv_file"):
        text = request.files["csv_file"].read().decode("utf-8-sig", errors="replace")
    result = import_csv(text, user=current_user()["username"])
    audit_log_service.append("host.csv_import", current_user()["username"], result)
    return render_template("host_new.html", **_host_new_context(import_result=result)), 200 if result["failed"] == 0 else 400


@bp.post("/hosts/import/json")
@require_feature("cmdb_csv_import")
@require_role("admin")
@market_hours_protected
def host_import_json_page():
    text = request.form.get("json_text", "")
    if not text and request.files.get("json_file"):
        text = request.files["json_file"].read().decode("utf-8-sig", errors="replace")
    result = import_json(text, user=current_user()["username"])
    audit_log_service.append("host.json_import", current_user()["username"], result)
    return render_template("host_import.html", import_result=result, active_tab="json"), 200 if result["failed"] == 0 else 400


@bp.post("/hosts/import/manual")
@require_feature("cmdb_manual_input")
@require_role("admin")
@market_hours_protected
def host_import_manual_page():
    defaults = {
        "division": request.form.get("division", ""),
        "department": request.form.get("department", ""),
        "status": request.form.get("status", ""),
        "group_name": request.form.get("group_name", ""),
        "asset_name": request.form.get("asset_name", ""),
        "device_type": request.form.get("device_type", ""),
        "quantity": request.form.get("quantity", "1"),
        "owner": request.form.get("owner", ""),
        "environment": request.form.get("environment", ""),
        "custodian": request.form.get("custodian", ""),
        "user_unit": request.form.get("user_unit", ""),
        "company": request.form.get("company", ""),
        "integrity": request.form.get("integrity", ""),
        "confidentiality": request.form.get("confidentiality", ""),
        "availability": request.form.get("availability", ""),
        "dc": request.form.get("dc", ""),
    }
    result = {"created": 0, "updated": 0, "failed": 0, "errors": []}
    for line_no, raw_line in enumerate(request.form.get("rows", "").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        values = [part.strip() for part in line.split(",")]
        if len(values) != len(MANUAL_MULTI_FIELDS):
            result["failed"] += 1
            result["errors"].append(f"第 {line_no} 行：需要 {len(MANUAL_MULTI_FIELDS)} 個逗號分隔欄位")
            continue
        doc = {**defaults, **dict(zip(MANUAL_MULTI_FIELDS, values))}
        try:
            existed = host_service.get_host(doc["hostname"]) is not None
            host_service.upsert_host(doc, user=current_user()["username"])
            result["updated" if existed else "created"] += 1
        except Exception as exc:
            result["failed"] += 1
            result["errors"].append(f"第 {line_no} 行：{exc}")
    audit_log_service.append("host.manual_multi_import", current_user()["username"], result)
    return render_template("host_import.html", import_result=result, active_tab="manual_multi"), 200 if result["failed"] == 0 else 400


@bp.post("/api/hosts/network-scan")
@require_feature("cmdb_network_scan")
@require_role("admin")
@market_hours_protected
def network_scan_stub():
    payload = request.get_json(force=True, silent=True) or {}
    result = cmdb_service.run_asset_discovery_scan(
        payload.get("cidr", ""),
        user=current_user()["username"],
        environment=payload.get("environment", ""),
        dc=payload.get("dc", ""),
        scan_mode=payload.get("scan_mode", "combined"),
    )
    audit_log_service.append("host.network_scan.preview", current_user()["username"], {"cidr": result.get("cidr"), "count": result.get("discovered_count")})
    return jsonify(result)


@bp.post("/hosts/network-scan")
@require_feature("cmdb_network_scan")
@require_role("admin")
@market_hours_protected
def network_scan_page():
    result = cmdb_service.run_asset_discovery_scan(
        request.form.get("cidr", ""),
        user=current_user()["username"],
        environment=request.form.get("environment", ""),
        dc=request.form.get("dc", ""),
        scan_mode=request.form.get("scan_mode", "combined"),
    )
    audit_log_service.append("host.network_scan.preview", current_user()["username"], {"cidr": result.get("cidr"), "count": result.get("discovered_count")})
    return render_template("host_new.html", **_host_new_context(scan_report=result))


@bp.post("/hosts/new/discovery-scan")
@require_feature("cmdb_network_scan")
@require_role("admin")
def host_new_discovery_scan_page():
    cidr = request.form.get("cidr", "")
    try:
        report = cmdb_service.run_asset_discovery_scan(
            cidr,
            user=current_user()["username"],
            environment=request.form.get("environment", ""),
            dc=request.form.get("dc", ""),
            scan_mode=request.form.get("scan_mode", "combined"),
        )
        audit_log_service.append(
            "host.discovery_scan",
            current_user()["username"],
            {"cidr": report.get("cidr"), "discovered": report.get("discovered_count"), "unmanaged": report.get("mismatch_count")},
        )
        return render_template("host_new.html", **_host_new_context(scan_report=report))
    except Exception as exc:
        last_report = cmdb_service.latest_network_reconcile(cidr) or cmdb_service.latest_network_reconcile("")
        return render_template("host_new.html", **_host_new_context(scan_report=last_report, errors=[str(exc)])), 400


@bp.post("/hosts/new/discovery-create-drafts")
@require_feature("cmdb_network_scan")
@require_role("admin")
@market_hours_protected
def host_new_discovery_create_drafts_page():
    ips = request.form.getlist("ip")
    try:
        result = cmdb_service.create_asset_drafts_from_scan(request.form.get("cidr", ""), user=current_user()["username"], ips=ips)
        audit_log_service.append(
            "host.discovery_scan.create_drafts",
            current_user()["username"],
            {"cidr": result.get("cidr"), "created": result.get("created_count"), "skipped": result.get("skipped_count")},
        )
        report = cmdb_service.latest_network_reconcile(result.get("cidr", "")) or {}
        return render_template(
            "host_new.html",
            **_host_new_context(scan_report=report, scan_created=result.get("created", []), scan_skipped=result.get("skipped", [])),
        )
    except Exception as exc:
        return render_template("host_new.html", **_host_new_context(errors=[str(exc)])), 400


def _network_scan_preview(cidr: str, environment: str, dc: str, host_type: str) -> dict:
    try:
        network = ipaddress.ip_network(cidr, strict=False)
    except ValueError as exc:
        return {"status": "error", "mode": "dry-run", "cidr": cidr, "error": str(exc), "discovered": []}
    candidates = []
    for index, ip in enumerate(network.hosts()):
        if index >= 32:
            break
        ip_text = str(ip)
        suffix = ip_text.replace(".", "-").replace(":", "-")
        candidates.append(
            {
                "asset_seq": f"DISC-{suffix}",
                "hostname": f"scan-{suffix}",
                "ip": ip_text,
                "ip_addresses": [ip_text],
                "network_segments": [str(network)],
                "host_type": host_type,
                "environment": environment,
                "dc": dc,
                "action": "preview_only",
            }
        )
    return {"status": "ok", "mode": "dry-run", "cidr": str(network), "read_only": True, "discovered": candidates}


@bp.post("/hosts/saved-views")
@require_feature("cmdb_saved_views")
def host_save_view_page():
    user = current_user()
    if user["username"] == "anonymous":
        abort(401)
    params = {
        "q": request.form.get("q", ""),
        "status": request.form.get("status", ""),
        "group_name": request.form.get("group_name", ""),
        "environment": request.form.get("environment", ""),
        "host_type": request.form.get("host_type", ""),
        "dc": request.form.get("dc", ""),
        "page_size": request.form.get("page_size", ""),
    }
    try:
        view = save_view(user["username"], request.form.get("name", ""), params)
    except ValueError as exc:
        return redirect(url_for("api_hosts.hosts_page", save_view_error=str(exc), **params))
    audit_log_service.append("host.saved_view.save", user["username"], {"name": view["name"]})
    return redirect(url_for("api_hosts.hosts_page", **view["params"]))


@bp.post("/hosts/saved-views/delete")
@require_feature("cmdb_saved_views")
def host_delete_view_page():
    user = current_user()
    if user["username"] == "anonymous":
        abort(401)
    name = request.form.get("name", "")
    deleted = delete_view(user["username"], name)
    audit_log_service.append("host.saved_view.delete", user["username"], {"name": name, "deleted": deleted})
    return redirect(url_for("api_hosts.hosts_page"))


@bp.get("/hosts/<asset_seq>")
@require_feature("cmdb_manual_input")
@require_role("admin")
def host_edit_page(asset_seq: str):
    host = host_service.get_host(asset_seq)
    if not host:
        return render_template("host_edit.html", error="找不到資產", host=None), 404
    return render_template(
        "host_edit.html",
        host=host,
        edit_fields=EDIT_FIELDS,
        field_labels=ASSET_FIELD_LABELS,
        required_fields=REQUIRED_FIELDS,
        ipam_networks=cmdb_service.list_networks(),
        extension_definitions=cmdb_service.list_extension_definitions(),
        mode="edit",
    )


@bp.post("/hosts/<asset_seq>")
@require_feature("cmdb_manual_input")
@require_role("admin")
@market_hours_protected
def host_edit_submit(asset_seq: str):
    try:
        host = host_service.update_host(asset_seq, _host_form_data(), user=current_user()["username"])
        audit_log_service.append("host.update", current_user()["username"], {"hostname": host["hostname"], "asset_seq": host["asset_seq"]})
        return redirect(url_for("api_hosts.host_edit_page", asset_seq=host["hostname"]))
    except ValidationError as exc:
        errors, error_fields = _translate_host_form_messages(exc.errors)
        warnings, warning_fields = _translate_host_form_messages(exc.warnings, warning=True)
        form_host = {**_host_form_data(), "asset_seq": request.form.get("asset_seq", asset_seq)}
        return render_template(
            "host_edit.html",
            host=form_host,
            edit_fields=EDIT_FIELDS,
            field_labels=ASSET_FIELD_LABELS,
            required_fields=REQUIRED_FIELDS,
            ipam_networks=cmdb_service.list_networks(),
            extension_definitions=cmdb_service.list_extension_definitions(),
            mode="edit",
            errors=errors,
            warnings=warnings,
            error_fields=error_fields,
            warning_fields=warning_fields,
        ), 400


@bp.post("/hosts/<asset_seq>/verify-identity")
@require_feature("cmdb_manual_input")
@require_role("admin")
def host_verify_identity_submit(asset_seq: str):
    try:
        result = cmdb_service.verify_host_identity(asset_seq, user=current_user()["username"])
        host = result["host"]
        audit_log_service.append(
            "host.identity.verify",
            current_user()["username"],
            {
                "asset_seq": host.get("asset_seq"),
                "hostname": host.get("hostname"),
                "os": host.get("os"),
                "trusted": result["identity"].get("trusted"),
            },
        )
        return redirect(url_for("api_hosts.host_edit_page", asset_seq=host["hostname"]))
    except Exception as exc:
        host = host_service.get_host(asset_seq) or {"asset_seq": asset_seq}
        return render_template(
            "host_edit.html",
            host=host,
            edit_fields=EDIT_FIELDS,
            field_labels=ASSET_FIELD_LABELS,
            required_fields=REQUIRED_FIELDS,
            ipam_networks=cmdb_service.list_networks(),
            extension_definitions=cmdb_service.list_extension_definitions(),
            mode="edit",
            errors=[f"主機名稱/OS 驗證失敗：{exc}"],
        ), 400


@bp.post("/hosts/drafts")
@require_feature("cmdb_manual_input")
@require_role("admin")
def host_draft_submit():
    try:
        host = cmdb_service.create_asset_draft(dict(request.form), user=current_user()["username"])
        audit_log_service.append("host.draft.create", current_user()["username"], {"hostname": host["hostname"], "asset_name": host["asset_name"]})
        return redirect(url_for("api_hosts.host_edit_page", asset_seq=host["hostname"]))
    except Exception as exc:
        return redirect(url_for("api_hosts.hosts_page", draft_error=str(exc)))


@bp.post("/hosts/<asset_seq>/allocate-ip")
@require_feature("cmdb_manual_input")
@require_role("admin")
@market_hours_protected
def host_allocate_ip(asset_seq: str):
    try:
        host = cmdb_service.assign_ip_to_host(asset_seq, request.form.get("cidr", ""), user=current_user()["username"])
        audit_log_service.append("host.ip.allocate", current_user()["username"], {"hostname": host.get("hostname"), "asset_seq": host.get("asset_seq")})
        return redirect(url_for("api_hosts.host_edit_page", asset_seq=host["hostname"]))
    except Exception as exc:
        host = host_service.get_host(asset_seq) or {"asset_seq": asset_seq}
        return render_template(
            "host_edit.html",
            host=host,
            edit_fields=EDIT_FIELDS,
            field_labels=ASSET_FIELD_LABELS,
            required_fields=REQUIRED_FIELDS,
            ipam_networks=cmdb_service.list_networks(),
            extension_definitions=cmdb_service.list_extension_definitions(),
            mode="edit",
            errors=[str(exc)],
        ), 400


@bp.post("/hosts/<asset_seq>/lifecycle")
@require_feature("cmdb_manual_input")
@require_role("admin")
@market_hours_protected
def host_lifecycle_submit(asset_seq: str):
    action = request.form.get("action", "")
    reason = request.form.get("reason", "")
    try:
        if action == "delete_draft":
            host_service.delete_draft_host(asset_seq, reason, user=current_user()["username"])
            audit_log_service.append("host.draft.delete", current_user()["username"], {"asset_seq": asset_seq})
            return redirect(url_for("api_hosts.hosts_page", lifecycle_message="draft_deleted"))
        host = host_service.transition_lifecycle(asset_seq, action, reason, user=current_user()["username"])
        audit_log_service.append(
            "host.lifecycle",
            current_user()["username"],
            {"hostname": host.get("hostname"), "asset_seq": host.get("asset_seq"), "action": action},
        )
        return redirect(url_for("api_hosts.host_edit_page", asset_seq=host["hostname"]))
    except Exception as exc:
        host = host_service.get_host(asset_seq) or {"asset_seq": asset_seq}
        return render_template(
            "host_edit.html",
            host=host,
            edit_fields=EDIT_FIELDS,
            field_labels=ASSET_FIELD_LABELS,
            required_fields=REQUIRED_FIELDS,
            ipam_networks=cmdb_service.list_networks(),
            extension_definitions=cmdb_service.list_extension_definitions(),
            mode="edit",
            errors=[str(exc)],
        ), 400


@bp.post("/hosts/<asset_seq>/delete-draft")
@require_feature("cmdb_manual_input")
@require_role("admin")
def host_delete_draft_submit(asset_seq: str):
    reason = request.form.get("reason", "")
    try:
        host_service.delete_draft_host(asset_seq, reason, user=current_user()["username"])
        audit_log_service.append("host.draft.delete", current_user()["username"], {"asset_seq": asset_seq})
        return redirect(url_for("api_hosts.hosts_page", lifecycle_message="draft_deleted"))
    except Exception as exc:
        host = host_service.get_host(asset_seq) or {"asset_seq": asset_seq}
        return render_template(
            "host_edit.html",
            host=host,
            edit_fields=EDIT_FIELDS,
            field_labels=ASSET_FIELD_LABELS,
            required_fields=REQUIRED_FIELDS,
            ipam_networks=cmdb_service.list_networks(),
            extension_definitions=cmdb_service.list_extension_definitions(),
            mode="edit",
            errors=[str(exc)],
        ), 400


@bp.post("/hosts/bulk-delete-drafts")
@require_feature("cmdb_manual_input")
@require_role("admin")
def host_bulk_delete_drafts_submit():
    try:
        result = host_service.bulk_delete_draft_hosts(
            request.form.getlist("asset_seq"),
            request.form.get("reason", ""),
            user=current_user()["username"],
        )
        audit_log_service.append("host.draft.bulk_delete", current_user()["username"], result)
        return redirect(
            url_for(
                "api_hosts.hosts_page",
                status=request.form.get("return_status", ""),
                bulk_deleted=result["deleted_count"],
                bulk_skipped=result["skipped_count"],
            )
        )
    except Exception as exc:
        return redirect(url_for("api_hosts.hosts_page", status=request.form.get("return_status", ""), bulk_error=str(exc)))


@bp.get("/cmdb/ipam")
@require_feature("cmdb_manual_input")
def ipam_page():
    selected_cidr = request.args.get("cidr", "")
    return render_template(
        "ipam.html",
        networks=cmdb_service.list_networks(),
        reservations=cmdb_service.list_reservations(),
        scan_report=cmdb_service.latest_network_reconcile(selected_cidr),
        ipam_schedule=ipam_schedule_service.get_schedule(),
        weekday_labels=ipam_schedule_service.WEEKDAY_LABELS,
        selected_cidr=selected_cidr,
        status_labels=ASSET_STATUS_LABELS,
        host_type_labels=HOST_TYPE_LABELS,
        dc_labels=DC_LABELS,
    )


@bp.post("/cmdb/ipam/schedule")
@require_feature("cmdb_network_scan")
@require_role("admin")
def ipam_schedule_submit():
    schedule = ipam_schedule_service.save_schedule(dict(request.form), user=current_user()["username"])
    audit_log_service.append(
        "ipam.schedule.update",
        current_user()["username"],
        {"enabled": schedule.get("enabled"), "weekday": schedule.get("weekday"), "time": schedule.get("time")},
    )
    return redirect(url_for("api_hosts.ipam_page"))


@bp.get("/cmdb/ipam/network")
@require_feature("cmdb_manual_input")
def ipam_network_detail_page():
    detail = cmdb_service.network_ip_detail(request.args.get("cidr", ""))
    return render_template(
        "ipam_network_detail.html",
        detail=detail,
        status_labels=ASSET_STATUS_LABELS,
        host_type_labels=HOST_TYPE_LABELS,
        dc_labels=DC_LABELS,
    )


@bp.post("/cmdb/ipam/scan-report")
@require_feature("cmdb_network_scan")
@require_role("admin")
def ipam_scan_report_submit():
    report = cmdb_service.run_network_reconcile(request.form.get("cidr", ""), user=current_user()["username"])
    audit_log_service.append("ipam.network_scan.reconcile", current_user()["username"], {"cidr": report.get("cidr"), "mismatch_count": report.get("mismatch_count")})
    return redirect(url_for("api_hosts.ipam_page", cidr=report.get("cidr", "")))


@bp.post("/cmdb/ipam/scan-report/create-drafts")
@require_feature("cmdb_network_scan")
@require_role("admin")
def ipam_scan_create_drafts_submit():
    ips = request.form.getlist("ip")
    result = cmdb_service.create_asset_drafts_from_scan(request.form.get("cidr", ""), user=current_user()["username"], ips=ips)
    audit_log_service.append(
        "ipam.network_scan.create_drafts",
        current_user()["username"],
        {"cidr": result.get("cidr"), "created": result.get("created_count"), "skipped": result.get("skipped_count")},
    )
    return redirect(
        url_for(
            "api_hosts.ipam_page",
            cidr=result.get("cidr", ""),
            scan_draft_created=result.get("created_count", 0),
            scan_draft_skipped=result.get("skipped_count", 0),
        )
    )


@bp.get("/api/cmdb/ipam/scan-report")
@require_feature("cmdb_network_scan")
def ipam_scan_report_api():
    cidr = request.args.get("cidr", "")
    report = cmdb_service.latest_network_reconcile(cidr) if cidr else None
    return jsonify(report or {"error": "尚無網段掃描對帳報告"})


@bp.get("/cmdb/ipam/scan-report.csv")
@require_feature("cmdb_network_scan")
def ipam_scan_report_csv():
    import csv
    import io

    report = cmdb_service.latest_network_reconcile(request.args.get("cidr", ""))
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["severity", "type_label", "ip", "hostname", "asset_name", "os", "host_type", "status", "suggestion"])
    writer.writeheader()
    for row in (report or {}).get("rows", []):
        writer.writerow({key: row.get(key, "") for key in writer.fieldnames})
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=ipam_scan_report.csv"})


@bp.post("/cmdb/ipam/networks")
@require_feature("cmdb_manual_input")
@require_role("admin")
def ipam_network_submit():
    network = cmdb_service.create_network(dict(request.form), user=current_user()["username"])
    audit_log_service.append("ipam.network.save", current_user()["username"], {"cidr": network.get("cidr")})
    return redirect(url_for("api_hosts.ipam_page"))


@bp.post("/cmdb/ipam/reservations")
@require_feature("cmdb_manual_input")
@require_role("admin")
def ipam_reserve_submit():
    reservation = cmdb_service.reserve_ip(dict(request.form), user=current_user()["username"])
    audit_log_service.append("ipam.reserve", current_user()["username"], {"ip": reservation.get("ip"), "cidr": reservation.get("cidr")})
    return redirect(url_for("api_hosts.ipam_page"))


@bp.get("/cmdb/extensions")
@require_feature("cmdb_extension_fields")
def extension_fields_page():
    return render_template("extension_fields.html", definitions=cmdb_service.list_extension_definitions())


@bp.post("/cmdb/extensions")
@require_feature("cmdb_extension_fields")
@require_role("admin")
def extension_field_submit():
    definition = cmdb_service.save_extension_definition(dict(request.form), user=current_user()["username"])
    audit_log_service.append("cmdb.extension.save", current_user()["username"], {"key": definition.get("key")})
    return redirect(url_for("api_hosts.extension_fields_page"))


@bp.get("/api/hosts")
@require_feature("cmdb_manual_input")
def api_list_hosts():
    try:
        data = host_service.list_hosts(
            query=request.args.get("q", ""),
            page=int(request.args.get("page", "1")),
            page_size=int(request.args.get("page_size", "25")),
        )
    except Exception as exc:
        data = {"items": [], "total": 0, "page": 1, "page_size": 25, "error": str(exc)}
    return jsonify(data)


@bp.get("/api/hosts/saved-views")
@require_feature("cmdb_saved_views")
def api_list_saved_views():
    user = current_user()
    if user["username"] == "anonymous":
        return jsonify({"error": "login required"}), 401
    return jsonify({"items": list_views(user["username"])})


@bp.post("/api/hosts/saved-views")
@require_feature("cmdb_saved_views")
def api_save_saved_view():
    user = current_user()
    if user["username"] == "anonymous":
        return jsonify({"error": "login required"}), 401
    payload = request.get_json(force=True, silent=True) or {}
    try:
        view = save_view(user["username"], payload.get("name", ""), payload.get("params", {}))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    audit_log_service.append("host.saved_view.save", user["username"], {"name": view["name"]})
    return jsonify(view), 201


@bp.post("/api/hosts")
@require_feature("cmdb_manual_input")
@require_role("admin")
@market_hours_protected
def api_create_host():
    try:
        host = host_service.create_host(request.get_json(force=True), user=current_user()["username"])
        audit_log_service.append("host.create", current_user()["username"], {"hostname": host["hostname"], "asset_seq": host["asset_seq"]})
        return jsonify(host), 201
    except ValidationError as exc:
        return jsonify({"errors": exc.errors, "warnings": exc.warnings}), 400


@bp.put("/api/hosts/<asset_seq>")
@require_feature("cmdb_manual_input")
@require_role("admin")
@market_hours_protected
def api_update_host(asset_seq: str):
    try:
        host = host_service.update_host(asset_seq, request.get_json(force=True), user=current_user()["username"])
        audit_log_service.append("host.update", current_user()["username"], {"hostname": host["hostname"], "asset_seq": host["asset_seq"]})
        return jsonify(host)
    except ValidationError as exc:
        return jsonify({"errors": exc.errors, "warnings": exc.warnings}), 400


@bp.delete("/api/hosts/<asset_seq>")
@require_feature("cmdb_undo_30s")
@require_role("admin")
@market_hours_protected
def api_delete_host(asset_seq: str):
    host_service.delete_host(asset_seq, user=current_user()["username"], soft=True)
    audit_log_service.append("host.soft_delete", current_user()["username"], {"asset_seq": asset_seq})
    return jsonify({"status": "deleted", "asset_seq": asset_seq, "undo_seconds": 30})


@bp.post("/api/hosts/<asset_seq>/restore")
@require_feature("cmdb_undo_30s")
@require_role("admin")
@market_hours_protected
def api_restore_host(asset_seq: str):
    host = host_service.restore_host(asset_seq, user=current_user()["username"])
    audit_log_service.append("host.restore", current_user()["username"], {"asset_seq": asset_seq})
    return jsonify(host)


@bp.get("/api/hosts/csv/template")
@require_feature("cmdb_csv_import")
def csv_template():
    return Response(build_csv_template(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=hosts_template.csv"})


@bp.get("/api/hosts/csv/export")
@require_feature("cmdb_csv_import")
def csv_export():
    data = host_service.list_hosts(page=1, page_size=10000)
    return Response(export_hosts_csv(data["items"]), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=hosts_export.csv"})


@bp.post("/api/hosts/csv/import")
@require_feature("cmdb_csv_import")
@require_role("admin")
@market_hours_protected
def csv_import():
    text = request.get_data(as_text=True)
    result = import_csv(text, user=current_user()["username"])
    audit_log_service.append("host.csv_import", current_user()["username"], result)
    return jsonify(result), 200 if result["failed"] == 0 else 400


@bp.post("/api/hosts/csv/validate")
@require_feature("cmdb_csv_import")
def csv_validate():
    text = request.get_data(as_text=True)
    report = validate_csv(text)
    audit_log_service.append("host.csv_validate", current_user()["username"], {"status": report["status"], "row_count": report["row_count"], "error_count": report["error_count"]})
    return jsonify(report), 200 if report["error_count"] == 0 else 400


@bp.post("/api/hosts/csv/validate.csv")
@require_feature("cmdb_csv_import")
def csv_validate_errors():
    text = request.get_data(as_text=True)
    report = validate_csv(text)
    return Response(validation_errors_csv(report), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=host_csv_validation_errors.csv"})


@bp.post("/api/hosts/json/import")
@require_feature("cmdb_csv_import")
@require_role("admin")
@market_hours_protected
def json_import():
    text = request.get_data(as_text=True)
    result = import_json(text, user=current_user()["username"])
    audit_log_service.append("host.json_import", current_user()["username"], result)
    return jsonify(result), 200 if result["failed"] == 0 else 400
