from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_codex_working_rules_are_documented():
    agents = read("AGENTS.md")
    rules = read("docs/codex_working_rules.md")

    assert "版本只能使用 `1.X.X.X`" in agents
    assert "深度檢查目標是緊急時快速證明 OS 基礎狀態" in agents
    assert "CodeRabbit" in agents
    assert "長時間操作按鈕必須有狀態回報" in agents
    assert "Goal-Driven Execution" in rules
    assert "避免只說「好了」" in rules


def test_base_shell_keeps_navigation_theme_and_shortcuts():
    base_html = read("webapp/templates/base.html")
    js = read("webapp/static/js/ui_tools.js")
    css = read("webapp/static/css/cathay.css")

    assert 'data-nav-key="assets"' in base_html
    assert "endpoint.startswith('api_hosts.')" in base_html
    assert 'draggable="true"' in base_html
    assert "IT 巡檢系統" in base_html
    assert "themeToggle" in base_html
    assert "api_hosts.global_search_page" in base_html
    assert "webitgpt-theme" in js
    assert "webitgpt-nav-order" in js
    assert "event.altKey" in js
    assert ".nav a.active" in css
    assert ".nav a.nav-warn.active" in css


def test_hosts_saved_view_form_has_visible_asset_filters():
    hosts_html = read("webapp/templates/hosts.html")

    assert 'select name="host_type"' in hosts_html
    assert 'select name="environment"' in hosts_html
    assert 'select name="dc"' in hosts_html


def test_ipam_reconcile_and_schedule_contracts_exist():
    installer = read("scripts/install_systemd.sh")
    script = read("scripts/weekly_ipam_reconcile.py")
    schedule_service = read("webapp/services/ipam_schedule_service.py")
    ipam_html = read("webapp/templates/ipam.html")
    routes = read("webapp/routes/api_hosts.py")
    service = read("webapp/services/cmdb_service.py")

    assert "webitgpt-ipam-reconcile.timer" in installer
    assert "weekly_ipam_reconcile.py" in installer
    assert "should_run_now" in script
    assert "run_network_reconcile" in script
    assert '["nmap", "-sn", "-oX", "-", cidr]' in service
    assert '"weekday": "mon"' in schedule_service
    assert '"time": "07:30"' in schedule_service
    assert 'select name="weekday"' in ipam_html
    assert 'input name="time" type="time"' in ipam_html
    assert "ipam_scan_report_submit" in routes
    assert "ipam_scan_create_drafts_submit" in routes
    assert "create_asset_drafts_from_scan" in service
    assert "將未納管 IP 建立草稿" in ipam_html
    assert "ipam.network_scan.create_drafts" in routes
    assert "ipam_schedule_submit" in routes


def test_asset_new_workbench_has_csv_and_scan_entrypoints():
    host_new = read("webapp/templates/host_new.html")
    host_new_js = read("webapp/static/js/host_new.js")
    routes = read("webapp/routes/api_hosts.py")
    cmdb = read("webapp/services/cmdb_service.py")

    assert "新增主機工作台" in host_new
    assert "CSV 大量匯入" in host_new
    assert "網段掃描新增" in host_new
    assert "將勾選 IP 建立草稿" in host_new
    assert "選擇已建立網段" in host_new
    assert "data-submit-status" in host_new
    assert "data-preserve-results" in host_new
    assert "正在掃描網段" in host_new
    assert "下方會先保留上次掃描結果" in host_new
    assert "上次掃描結果" in host_new
    assert "狀態已依目前資產清冊重新校正" in host_new
    assert "混合掃描：ARP/Ping + TCP 常見服務" in host_new
    assert "開放服務" in host_new
    assert "發現方式" in host_new
    assert "data-fill-target" in host_new
    assert "initNetworkFill" in host_new_js
    assert "host_new_full_page" in routes
    assert "host_new_discovery_scan_page" in routes
    assert "host_new_discovery_create_drafts_page" in routes
    assert "latest_network_reconcile" in routes
    assert "run_asset_discovery_scan" in cmdb
    assert "_refresh_scan_report_with_current_cmdb" in cmdb
    assert "scan_mode" in cmdb
    assert '"scan_mode": mode' in cmdb
    skill = read("docs/scan_state_skill.md")
    assert "預設顯示最近一次" in skill
    assert "data-preserve-results" in skill
    assert '"nmap", "-Pn", "-R", "-p"' in cmdb
    assert '"hostname": item.get("hostname", "")' in cmdb
    assert '"os": item.get("os") or' in cmdb

def test_long_running_submit_feedback_contract_exists():
    js = read("webapp/static/js/ui_tools.js")
    admin_js = read("webapp/static/js/admin_tools.js")
    css = read("webapp/static/css/cathay.css")
    rules = read("docs/codex_working_rules.md")

    assert 'form[data-submit-status]' in js
    assert "dataset.submitting" in js
    assert "createElement(\"div\")" in js
    assert "[data-api-post]" in admin_js
    assert "findApiStatus" in admin_js
    assert "data-submit-message" in read("webapp/templates/accounts_inventory.html")
    assert "data-submit-message" in read("webapp/templates/dependencies.html")
    assert "data-submit-message" in read("webapp/templates/ipam.html")
    assert "data-submit-message" in read("webapp/templates/security_audit.html")
    assert "submit-status" in css
    assert "長時間操作" in rules
    assert "停用按鈕" in rules


def test_dashboard_parity_and_legacy_pages_are_wired():
    base_html = read("webapp/templates/base.html")
    reports_route = read("webapp/routes/api_reports.py")
    executive = read("webapp/templates/executive.html")
    css = read("webapp/static/css/cathay.css")
    superadmin_route = read("webapp/routes/api_superadmin.py")
    app = read("webapp/app.py")

    assert "dashboard_page" in reports_route
    assert "executive_page" in reports_route
    assert "_executive_charts" in reports_route
    assert "executive-chart-grid" in executive
    assert "executive-donut" in executive
    assert "roadmap-list" in executive
    assert "executive-chart-grid" in css
    assert "api_reports.dashboard_page" in base_html
    assert "api_reports.executive_page" in base_html
    assert "feature_parity_page" in superadmin_route
    assert "v3.17" in superadmin_route
    assert "api_dependencies" in app


def test_superadmin_full_system_surfaces_exist():
    routes = read("webapp/routes/api_superadmin.py")
    service = read("webapp/services/system_service.py")
    superadmin = read("webapp/templates/superadmin.html")
    users = read("webapp/templates/users.html")
    health = read("webapp/templates/system_health.html")
    backup = read("webapp/templates/backup_dr.html")
    patches = read("webapp/templates/patches.html")

    for name in [
        "users_page",
        "users_reset_password_api",
        "users_lock_api",
        "backup_manifest_api",
        "dr_drill_api",
        "rollback_plan_api",
        "system_health_api",
        "settings_api",
        "logs_api",
        "jobs_api",
        "audit_logs_api",
        "remote_tools_page",
        "dev_console_page",
    ]:
        assert name in routes
    for name in [
        "admin_console_overview",
        "health_dashboard",
        "create_backup_manifest",
        "dr_drill",
        "patch_inventory",
        "rollback_plan",
        "operation_logs_csv",
    ]:
        assert f"def {name}(" in service
    assert "Hash chain：" in superadmin
    assert "effective_enabled" in superadmin
    assert "重設密碼" in users
    assert "備用碼" in users
    assert "健康檢查" in health
    assert "備份 / DR" in backup
    assert "Patch / 回滾" in patches


def test_phase_readonly_guard_remains_enabled_and_blocks_writes():
    flags = read("webapp/services/feature_flags.py")
    decorators = read("webapp/decorators.py")
    admin_routes = read("webapp/routes/api_admin.py")

    assert '_flag("phase_readonly_mode"' in flags
    assert "雙寫評比期間封鎖受監控主機寫入動作" in flags
    assert "default=True" in decorators
    assert "Phase parallel review: monitored-host writes are locked" in decorators
    assert "monitored_write_blocked" in admin_routes


def test_inventory_history_diff_and_topology_contracts_exist():
    inventory_service = read("webapp/services/inventory_service.py")
    inventory_routes = read("webapp/routes/api_inventory.py")
    dependency_service = read("webapp/services/dependency_service.py")
    dependency_routes = read("webapp/routes/api_dependencies.py")
    dependencies_page = read("webapp/templates/dependencies.html")
    ui_tools = read("webapp/static/js/ui_tools.js")
    css = read("webapp/static/css/cathay.css")

    assert "DEFAULT_MIN_INTERVAL_MINUTES = 360" in inventory_service
    assert "def inventory_history(" in inventory_service
    assert "def inventory_diff_report(" in inventory_service
    assert '"/api/inventory/<kind>/history"' in inventory_routes
    assert '"/inventory/<kind>/diff-report"' in inventory_routes
    for name in [
        "def topology(",
        "def downstream_impact(",
        "def upstream_impact(",
        "def analyze_ghosts(",
        "def collect_topology(",
        "def reconcile_ss_nmap(",
    ]:
        assert name in dependency_service
    assert "/api/dependencies/topology" in dependency_routes
    assert "/api/dependencies/reconcile/trigger" in dependency_routes
    assert "data-topology-canvas" in ui_tools
    assert "data-topology-panel" in dependencies_page
    assert "topology-client-fullscreen" in css


def test_dev_console_contracts_exist():
    css = read("webapp/static/css/cathay.css")
    validation = read("webapp/templates/validation.html")
    dev_console = read("webapp/templates/dev_console.html")
    dev_tabs = read("webapp/templates/_partials/dev_tabs.html")
    ui_tools = read("webapp/static/js/ui_tools.js")
    service = read("webapp/services/system_service.py")
    routes = read("webapp/routes/api_superadmin.py")

    assert ".dev-workbench" in css
    assert ".dev-toolbar" in css
    assert ".dev-grid" in css
    assert "dev-workbench" in validation
    assert "dev-compact-summary" in validation
    assert "<details class=\"dev-detail\">" in validation
    assert "dev-admin-v317" in dev_console
    assert "data-dev-panel=\"developer-docs\"" in dev_tabs
    assert "data-tab-storage=\"webitgpt-dev-section-tabs\"" in dev_tabs
    assert "enableSortableTabs" in ui_tools
    assert "enableDevPanelTabs" in ui_tools
    assert "def release_notes" in service
    assert "save_dev_upload" in service
    assert "dev_console_upload_page" in routes
    assert "dev_console_feature_update_page" in routes


def test_asset_governance_status_admin_contracts_exist():
    service = read("webapp/services/asset_governance_status_service.py")
    routes = read("webapp/routes/api_superadmin.py")
    host_routes = read("webapp/routes/api_hosts.py")
    template = read("webapp/templates/asset_governance_statuses.html")
    superadmin = read("webapp/templates/superadmin.html")
    system_service = read("webapp/services/system_service.py")
    bootstrap = read("scripts/bootstrap.py")

    for text in ["等待防火牆開通", "等待弱掃完成", "等待 PAM 納管", "例外保留"]:
        assert text in service
    for text in [
        "visible_in_report",
        "blocks_activation",
        "requires_reason",
        "requires_expiry",
        "auto_assignable",
    ]:
        assert text in service
        assert text in template
    assert "asset_governance_statuses" in bootstrap
    assert "ensure_default_statuses" in bootstrap
    assert "asset_governance_statuses_page" in routes
    assert "asset_governance_statuses_api" in routes
    assert "global_search_page" in host_routes
    assert "等待防火牆" in host_routes
    assert "等待弱掃" in host_routes
    assert "PAM 納管" in host_routes
    for text in ['"A."', '"B."', '"C."', '"D."', '"E."', '"F."', '"G."', '"H."', '"I."']:
        assert text in host_routes
    for text in ['"SA.A"', '"SA.B"', '"SA.C"', '"SA.D"', '"SA.E"', '"SA.F"', '"SA.G"', '"SA.H"']:
        assert text in host_routes
    assert '"日"' in host_routes
    assert '"誌"' in host_routes
    assert "search_results.html" in host_routes
    assert "_keyword_related" in host_routes
    assert "_is_direct_search_code" in host_routes
    assert "asset_quality_page" in host_routes
    assert "status_counts" in host_routes
    assert "status_counts" in read("webapp/services/host_service.py")
    hosts_template = read("webapp/templates/hosts.html")
    host_service = read("webapp/services/host_service.py")
    hosts_js = read("webapp/static/js/hosts.js")
    for text in ["批次草稿處理", "全選本頁草稿", "刪除勾選草稿", "bulkDraftDeleteForm"]:
        assert text in hosts_template
    for text in ["asset-table-compact", "資產名稱 *", "Hostname", "asset-row-menu"]:
        assert text in hosts_template
    for text in ["asset-col-expand", "data-asset-detail-toggle", "asset-detail-panel"]:
        assert text in hosts_template
    for text in ["設備類型", "機櫃", "備註", "asset-note-cell"]:
        assert text in hosts_template
    assert '<span>草稿</span>' in hosts_template
    assert "host_bulk_delete_drafts_submit" in host_routes
    assert "bulk_delete_draft_hosts" in host_service
    assert "不是草稿；正式資產請走下線或汰除流程" in host_service
    assert "data-select-drafts" in hosts_js
    assert '@require_role("admin")\ndef host_edit_page' in host_routes
    assert "host_lifecycle_submit" in host_routes
    assert "host_delete_draft_submit" in host_routes
    host_service = read("webapp/services/host_service.py")
    assert "transition_lifecycle" in host_service
    assert "delete_draft_host" in host_service
    host_edit = read("webapp/templates/host_edit.html")
    for text in ["資產生命週期", "刪除草稿", "申請下線", "下線封存", "處理原因"]:
        assert text in host_edit
    for text in ["請先修正以下欄位", "field-has-error", "這個欄位需要修正"]:
        assert text in host_edit
    for text in ["HOST_FORM_ERROR_MESSAGES", "連線方式未設定", "_translate_host_form_messages", "error_fields"]:
        assert text in host_routes
    assert 'current_user.role in ["admin", "super", "superadmin"]' in read("webapp/templates/hosts.html")
    assert 'current_user.role in ["admin", "super", "superadmin"]' in read("webapp/templates/asset_quality.html")
    assert "asset_quality_report" in Path("webapp/services/cmdb_service.py").read_text(encoding="utf-8")
    assert "資產異常清單" in Path("webapp/templates/asset_quality.html").read_text(encoding="utf-8")
    for text in ["開發後台", "IPAM", "系統拓撲", "操作紀錄", "重要服務設定", "新增主機"]:
        assert text in host_routes
    assert "資產治理狀態" in superadmin
    assert "資產治理狀態" in system_service

