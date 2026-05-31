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
    service = read("webapp/services/saved_view_service.py")

    assert 'select name="host_type"' in hosts_html
    assert 'select name="environment"' in hosts_html
    assert 'select name="dc"' in hosts_html
    assert 'input name="name" placeholder="篩選名稱（可空白）"' in hosts_html
    assert 'input name="name" placeholder="篩選名稱" required' not in hosts_html
    assert "FILTER_LABELS" in service
    assert "clean_name = \" / \".join(parts)" in service


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
    base = read("webapp/templates/base.html")
    admin_topnav = read("webapp/templates/_partials/admin_topnav.html")
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
        "credentials_page",
        "credentials_linux_bootstrap_script",
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
    assert "admin-page-topnav" in superadmin
    assert "admin-sidebar-grouped" in superadmin
    assert "page-title-with-help" in superadmin
    assert '<details class="inline-help">' in superadmin
    assert 'aria-label="系統管理說明"' in superadmin
    assert '<details class="admin-nav-section">' in superadmin
    assert '<details class="admin-nav-section" open>' not in superadmin
    assert 'include "_partials/admin_topnav.html"' in base
    assert "admin-topnav-strip" in base
    assert "api_superadmin.system_health_page" in admin_topnav
    assert "api_superadmin.logs_page" in admin_topnav
    assert "admin-nav-heading {% if endpoint in" in admin_topnav
    assert '<summary class="admin-nav-heading">權限與憑證</summary>' in superadmin
    assert "credentials_page" in superadmin
    assert "API Token" in superadmin
    assert "important_services_page" in superadmin
    assert "backup_dr_page" in superadmin
    assert "重設密碼" in users
    assert "備援碼" in users
    assert "健康檢查" in health
    assert "備份 / DR" in backup
    assert "Patch / 回滾" in patches


def test_phase_readonly_guard_remains_enabled_and_blocks_writes():
    flags = read("webapp/services/feature_flags.py")
    decorators = read("webapp/decorators.py")
    admin_routes = read("webapp/routes/api_admin.py")
    operations_routes = read("webapp/routes/api_operations.py")

    assert '_flag("phase_readonly_mode"' in flags
    assert "雙寫評比期間封鎖受監控主機寫入動作" in flags
    assert "default=True" in decorators
    assert "Phase parallel review: monitored-host writes are locked" in decorators
    assert "monitored_write_blocked" in admin_routes
    assert "monitored_write_blocked" in operations_routes
    assert "@monitored_write_blocked\ndef nmon_deploy_api" in operations_routes


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
        "def import_system_relations_xlsx(",
        "def _system_radial_topology(",
        "def _layout_radial(",
        "def _core_radial_topology(",
        "def _core_impact_topology(",
    ]:
        assert name in dependency_service
    assert "system_relations_xlsx" in dependency_service
    assert "cmdb_import" in dependency_service
    assert "def cleanup_imported_system_relations(" in dependency_service
    import_script = read("scripts/import_system_relations.py")
    cleanup_script = read("scripts/cleanup_imported_system_relations.py")
    assert "import_system_relations_xlsx" in import_script
    assert "--dry-run" in import_script
    assert "cleanup_imported_system_relations" in cleanup_script
    assert "--yes" in cleanup_script
    assert "/api/dependencies/topology" in dependency_routes
    assert "/api/dependencies/reconcile/trigger" in dependency_routes
    assert "data-topology-canvas" in ui_tools
    assert "data-topology-panel" in dependencies_page
    assert 'value="core_radial"' in dependencies_page
    assert 'value="core_impact"' in dependencies_page
    assert "核心關聯圓圖" in dependencies_page
    assert "核心影響清單圖" in dependencies_page
    assert 'value="radial"' in dependencies_page
    assert "系統關聯圓圖" in dependencies_page
    assert "手動關聯管理" in dependencies_page
    assert "relation_save_page" in read("webapp/routes/api_dependencies.py")


def test_collection_credentials_page_contract_exists():
    routes = read("webapp/routes/api_superadmin.py")
    template = read("webapp/templates/credentials.html")
    search_registry = read("webapp/routes/api_hosts.py")
    css = read("webapp/static/css/cathay.css")

    assert '"/superadmin/credentials"' in routes
    assert '"/superadmin/credentials/linux-bootstrap.sh"' in routes
    assert "COLLECTION CREDENTIALS" in template
    assert "L1" in template
    assert "tier-{{ item.tier|lower }}" in template
    assert "L2" in template
    assert "credential-tier-card" in template
    assert "L3" in template
    assert "source-badge" in template
    assert "credentials_page" in search_registry
    assert ".credential-tier-grid" in css
    assert "details.admin-nav-section[open] > .admin-nav-heading" in css
    assert ".admin-page-topnav .admin-nav-heading.active" in css
    assert ".admin-page-topnav .admin-sidebar" in css
    assert ".admin-page-topnav .admin-sidebar-title" in css
    assert "flex: 0 0 auto" in css
    assert "min-height: 30px" in css
    assert "position: absolute" in css
    assert ".page-title-with-help" in css
    assert ".inline-help summary" in css
    assert "itwebL1" in template
    assert "itwebL2" in template
    assert "itwebL3" in template
    assert "1qaz@WSX" in template
    assert "下載 Linux 偵測/建立腳本" in template
    assert "linux_bootstrap_script" in read("webapp/services/collection_credential_service.py")


def test_ai_token_cost_visibility_contract_exists():
    reports_route = read("webapp/routes/api_reports.py")
    superadmin_route = read("webapp/routes/api_superadmin.py")
    token_service = read("webapp/services/token_cost_service.py")
    token_page = read("webapp/templates/token_costs.html")
    executive = read("webapp/templates/executive.html")
    superadmin = read("webapp/templates/superadmin.html")
    css = read("webapp/static/css/cathay.css")
    dependencies_page = read("webapp/templates/dependencies.html")
    ui_tools = read("webapp/static/js/ui_tools.js")
    dependency_service = read("webapp/services/dependency_service.py")

    assert "token_cost_report" in reports_route
    assert "token_cost = token_cost_report()" in reports_route
    assert '"token_cost": token_cost' in reports_route
    assert '"/superadmin/token-costs"' in superadmin_route
    assert '"/api/superadmin/token-costs"' in superadmin_route
    assert '"/api/superadmin/token-usage"' in superadmin_route
    assert "ai_token_usage" in token_service
    assert "estimate_cost_usd" in token_service
    assert "Token 成本" in token_page
    assert "每日 Token 與費用" in token_page
    assert "最花 Token 的動作" in token_page
    assert "價格估算表" in token_page
    assert "預算路由" in token_page
    assert "KEY 階級與預算上限" in token_page
    assert "budget_policy" in token_service
    assert "get_settings(masked=True)" in token_service
    assert "choose_key_tier" in superadmin_route
    assert '"/api/superadmin/ai/key-routing-preview"' in superadmin_route
    assert "L1 低成本" in read("webapp/services/llm_provider.py")
    assert "L2 一般分析" in read("webapp/services/llm_provider.py")
    assert "L3 深度判讀" in read("webapp/services/llm_provider.py")
    assert "budget_policy_enabled" in read("webapp/templates/ai_settings.html")
    assert "超額策略" in read("webapp/templates/ai_settings.html")
    assert "Script fallback" in read("webapp/templates/ai_settings.html")
    assert "judgement-source-card ai-ready" in read("webapp/templates/ai_settings.html")
    assert "judgement-source-card ai-ready" in token_page
    assert "本月 AI Token" in executive
    assert "Token 成本" in superadmin
    assert "topology-node-radial-center" in css
    assert "topology-node-focus-muted" in css
    assert "topology-edge-focus-muted" in css
    assert "topology-edge-focus-" in dependencies_page
    assert 'list="topology-system-options"' in dependencies_page
    assert 'data-select-filter="topology-center-core"' in dependencies_page
    assert 'data-select-filter="topology-center-system"' in dependencies_page
    assert "選擇資產名稱 / 系統名稱" in dependencies_page
    assert "搜尋資產名稱 / 系統名稱" in dependencies_page
    assert "topology-searchable-select" in dependencies_page
    assert "data-select-filter-count" in dependencies_page
    assert "initSearchableSelectFilters" in ui_tools
    assert "originalOptions" in ui_tools
    assert ".topology-searchable-select" in css
    assert "def _host_business_system_name" in dependency_service
    assert "never promote hostname to system" in dependency_service
    assert "sync_source\": \"host_inventory\"" in dependency_service
    assert "metadata.asset_name" in dependency_service
    assert "metadata.system_name" in dependency_service
    assert 'querySelector(\'[name="center"]\')' in ui_tools
    assert "topology-impact-node-box" in dependencies_page
    assert "topology-impact-panel" in dependencies_page
    assert "topology-contact-list" in dependencies_page
    assert "dependencies_notifications_csv" in dependencies_page
    assert "核心系統影響圖" in dependencies_page
    assert "topology-tabs" in dependencies_page
    assert "1. 核心影響" in dependencies_page
    assert "2. 系統關聯圓圖" in dependencies_page
    assert "3. 連線偵測 / 對帳" in dependencies_page
    reports_route = read("webapp/routes/api_reports.py")
    assert 'def _topology_from_request(default_view: str = "core_impact")' in reports_route
    assert '"/api/dependencies/notifications.csv"' in reports_route
    assert "webitgpt_core_impact_notifications.csv" in reports_route
    assert "impact_panel" in dependency_service
    assert "核心影響圖" in dependency_service
    assert "notification_contacts" in dependency_service
    assert "layer_lanes" in dependency_service
    assert "def _resolve_topology_node_id" in dependency_service
    assert 'value.startswith("core:")' in dependency_service
    assert 'data.get("view") != "core_impact"' in dependency_service
    assert "document.createElement(\"option\")" in ui_tools
    assert ".topology-impact-panel" in css
    assert ".topology-layer-lane" in css
    assert ".topology-contact-list" in css
    assert "centerCanvas" in ui_tools
    assert "stage.scrollWidth - canvas.clientWidth" in ui_tools
    assert "min-height: calc(100vh - 150px)" in css
    assert "height: calc(100vh - 260px)" in css
    assert "flex-wrap: nowrap" in css
    assert "host_relation_graph" in dependency_service
    assert "edge_relations" in dependency_service
    assert 'layout_mode": "system_trunks"' not in dependency_service
    assert "latest_network_scan_report" in dependency_service
    assert "network_reports" in dependency_service
    assert "掃描未納管" in dependency_service
    assert "topology-node-unmanaged" in dependencies_page
    assert ".topology-node-unmanaged" in css
    assert "網段掃描發現" in dependencies_page
    assert "網段掃描明細" in dependencies_page
    assert "Port 對帳明細" in dependencies_page
    assert "window.location.href = fallback" in ui_tools
    assert "panel.requestFullscreen" in ui_tools
    assert "topology-client-fullscreen" in css


def test_dev_console_contracts_exist():
    css = read("webapp/static/css/cathay.css")
    validation = read("webapp/templates/validation.html")
    dev_console = read("webapp/templates/dev_console.html")
    dev_tabs = read("webapp/templates/_partials/dev_tabs.html")
    ui_tools = read("webapp/static/js/ui_tools.js")
    service = read("webapp/services/system_service.py")
    routes = read("webapp/routes/api_superadmin.py")
    debug_service = read("webapp/services/debug_bundle_service.py")

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
    assert "RECENT_PATCH_RELEASES" in service
    assert "1.0.2.71" in service
    assert "nmon-ibm-profile" in service
    assert "目前部署版本" in service
    assert "save_dev_upload" in service
    assert "dev_console_upload_page" in routes
    assert "dev_console_feature_update_page" in routes
    assert "dev_console_debug_bundle_page" in routes
    assert "dev_console_debug_bundle_download" in routes
    assert "dev_console_ai_debug_loop_page" in routes
    assert "dev_console_ai_debug_loop_prompt_download" in routes
    assert "dev_console_ai_runtime_manifest" in routes
    assert "dev_console_doc_download" in routes
    assert "ensure_current_dev_docs" in service
    for doc_name in ["00_CURRENT_STATUS.md", "01_ASSET_MANAGEMENT.md", "04_NMON_PERFORMANCE_MONTHLY.md", "05_AI_DEBUG_LOOP.md"]:
        assert doc_name in service
    assert "Debug Bundle" in dev_console
    assert "AI debug loop" in dev_console
    assert "GPT Enterprise" in dev_console
    assert "Runtime Manifest" in dev_console
    assert "查看" in dev_console
    assert "ai_runtime_manifest" in service
    assert "debug-bundle" in dev_tabs
    for marker in ["<IP_MASKED>", "<HOST_MASKED>", "<USER_MASKED>", "<SECRET_MASKED>", "collect_debug_bundle", "create_ai_debug_loop", "ai_runtime_manifest", "AI_RUNTIME_ID"]:
        assert marker in debug_service


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
    assert "global_search_service.search_data" in host_routes
    assert "global_search_service.recent_data" in host_routes
    assert "is_empty_search=True" in host_routes
    assert "_keyword_related" in host_routes
    assert "_is_direct_search_code" in host_routes
    search_template = read("webapp/templates/search_results.html")
    search_service = read("webapp/services/global_search_service.py")
    css = read("webapp/static/css/cathay.css")
    for text in ["搜尋入口", "不必先填完整條件", "正式資產", "草稿 / 未納管", "CMDB 資產池", "功能入口"]:
        assert text in search_template
    for text in ["HOST_SEARCH_FIELDS", "ASSET_POOL_SEARCH_FIELDS", "recent_data", "cmdb_asset_pool"]:
        assert text in search_service
    for text in [".search-result-summary", ".search-result-row", ".search-result-badge"]:
        assert text in css
    assert "asset_quality_page" in host_routes
    assert "status_counts" in host_routes
    assert "status_counts" in read("webapp/services/host_service.py")
    hosts_template = read("webapp/templates/hosts.html")
    host_service = read("webapp/services/host_service.py")
    hosts_js = read("webapp/static/js/hosts.js")
    host_edit = read("webapp/templates/host_edit.html")
    for text in ["批次草稿處理", "全選本頁草稿", "刪除勾選草稿", "bulkDraftDeleteForm"]:
        assert text in hosts_template
    for text in ["asset-table-compact", "資產名稱 *", "Hostname", "asset-row-menu"]:
        assert text in hosts_template
    assert "資產名稱 / 系統名稱 / 主機名稱 / IP / 網段" in hosts_template
    for text in ["asset-col-expand", "data-asset-detail-toggle", "asset-detail-panel"]:
        assert text in hosts_template
    for text in ["設備類型", "機櫃", "備註", "asset-note-cell"]:
        assert text in hosts_template
    for text in ["asset-source-pill", "驗證名稱/OS", "host_verify_identity_submit"]:
        assert text in hosts_template or text in host_routes
    for text in ["重整本頁資產", "重整全部納管資產", "hosts_refresh_identity_submit", "refresh_asset_identities"]:
        assert text in hosts_template or text in host_routes or text in host_service or text in read("webapp/services/cmdb_service.py")
    for text in ["主機名稱 / OS 可信度", "Hostname 來源", "OS 來源", "verifyIdentityForm"]:
        assert text in host_edit
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


def test_data_tables_are_sortable_by_default():
    base_html = read("webapp/templates/base.html")
    sorter = read("webapp/static/js/table_sort.js")
    css = read("webapp/static/css/cathay.css")
    hosts_template = read("webapp/templates/hosts.html")
    skill = read("docs/table_sorting_skill.md")

    assert "js/table_sort.js" in base_html
    assert "table.data-table" in sorter
    assert "sortable-header" in sorter
    assert "asset-detail-row" in sorter
    assert "data-sortable" in sorter
    assert "data-no-sort" in sorter
    assert ".data-table th.sortable-header" in css
    assert 'asset-col-select" data-sortable="false"' in hosts_template
    assert 'asset-col-actions" data-sortable="false"' in hosts_template
    assert 'asset-col-expand" data-sortable="false"' in hosts_template
    assert "所有清冊型、報表型、盤點型表格" in skill
    assert "`table.data-table`" in skill


def test_nmon_monthly_report_has_real_report_surfaces():
    template = read("webapp/templates/nmon.html")
    routes = read("webapp/routes/api_operations.py")
    service = read("webapp/services/legacy_parity_service.py")
    css = read("webapp/static/css/cathay.css")

    for text in [
        "效能月報主管摘要",
        "效能月報技術明細",
        "主管只看四個數字",
        "風險追蹤清單",
        "EOS / 作業系統生命週期",
        "剩餘",
        "公司核准的 EOS 規則",
        "report.os_lifecycle.catalog_source",
        "技術檢視摘要",
        "主機效能排名",
        "採樣明細",
        "趨勢時間軸",
        "主機熱區圖",
        "覆蓋率",
        "CSV",
        "CPU 尖峰",
        "記憶體尖峰",
        "磁碟尖峰",
        "CPU / RAM / Disk 趨勢圖",
        "NMON 分析常看的三條線",
        "Disk 平均",
    ]:
        assert text in template
    assert "nmon_report_csv_page" in routes
    assert "nmon_monthly_plan_api" in routes
    assert "nmon_deploy_api" in routes
    assert 'view in {"executive", "technical"}' in routes
    assert "/api/nmon/deploy" in template
    assert "安裝缺少 NMON" in template
    assert "IBM NMON 採樣口徑" in template
    assert "IBM_NMON_EQUIVALENT_COMMAND" in read("webapp/services/inspection_service.py")
    assert "equivalent_command" in template
    assert "webitgpt_nmon_collect.sh" in read("ansible/playbooks/install_nmon.yml")
    assert "/etc/cron.d/webitgpt-nmon" in read("ansible/playbooks/install_nmon.yml")
    assert '"${nmon_bin}" -x -m "${out_dir}"' in read("ansible/playbooks/install_nmon.yml")
    assert "def nmon_report_csv" in service
    assert "def nmon_monthly_plan" in service
    assert "def deploy_nmon_with_ansible" in read("webapp/services/inspection_service.py")
    assert "install_nmon.yml" in read("webapp/services/inspection_service.py")
    assert "cpu_pct" in service
    assert "timeline" in service
    assert "trend_chart" in service
    assert "_build_nmon_trend_chart" in service
    assert "_local_network_kbps" in service
    assert "_read_network_bytes" in service
    assert '"network_kbps": network_kbps' in service
    assert "x_axis_label" in service
    assert "y_axis_label" in service
    assert "y_ticks" in service
    assert "heatmap" in service
    assert "_p95" in service
    assert "_build_nmon_heatmap" in service
    assert "_matches_nmon_filters" in service
    assert "_build_nmon_architecture_summary" in service
    assert "_build_nmon_risk_rows" in service
    assert "_build_os_lifecycle_report" in service
    assert "source_url" in service
    assert "_eos_action" in service
    assert ".nmon-director-grid" in css
    assert ".nmon-exec-grid" in css
    assert ".nmon-exec-card" in css
    assert ".nmon-timeline" in css
    assert ".nmon-line-chart" in css
    assert ".nmon-line-cpu" in css
    assert ".nmon-line-mem" in css
    assert ".nmon-line-disk" in css
    assert ".nmon-line-network" in css
    assert ".nmon-y-axis-label" in css
    assert ".nmon-x-axis-label" in css
    assert ".nmon-heatmap" in css


def test_nmon_raw_pipeline_contracts_are_exposed():
    template = read("webapp/templates/nmon.html")
    routes = read("webapp/routes/api_operations.py")
    service = read("webapp/services/legacy_parity_service.py")
    raw_service = read("webapp/services/nmon_raw_service.py")
    debug_service = read("webapp/services/debug_bundle_service.py")
    dev_console = read("webapp/templates/dev_console.html")
    assert 'section == "NET"' in raw_service
    assert '"network_kbps": sample.get("network_kbps")' in raw_service

    for text in [
        "效能月報",
        "NMON raw file pipeline",
        "匯入 raw file",
        "Pipeline JSON",
        "主管摘要",
        "技術明細",
        "採樣明細",
    ]:
        assert text in template
    assert "nmon_raw_upload_page" in routes
    assert "nmon_raw_pipeline_api" in routes
    assert "raw_pipeline" in service
    assert "def parse_nmon_raw" in raw_service
    assert "def import_nmon_raw_file" in raw_service
    assert "def nmon_raw_pipeline_status" in raw_service
    assert "nmon_raw_pipeline.json" in debug_service
    assert "NMON raw 檔" in dev_console


def test_housekeeping_retention_mechanism_exists():
    service = read("webapp/services/housekeeping_service.py")
    template = read("webapp/templates/housekeeping.html")
    install = read("scripts/install.sh")
    runner = read("scripts/run_housekeeping.py")

    assert "deploy_tmp_purge" in service
    assert "patch_backup_keep" in service
    assert "code_cache_purge" in service
    assert 'root / "webapp"' in service
    assert 'root / "scripts"' in service
    assert "mongo_nmon_data_purge" in service
    assert "nmon_raw_files_purge" in service
    assert "host_accounts_purge" in service
    assert "MONGO_RETENTION_FIELDS" in service
    assert "_delete_old_collection_docs" in service
    assert "_keep_newest_directories" in service
    assert "preinstall_*" in service
    assert "run_post_install_housekeeping" in service
    assert "固定保留最新 20 份" in template
    assert "正式清理" in template
    assert "Mongo、NMON raw、主機資料、正式程式碼快取" in template
    assert "不碰主機主檔" in template
    assert "run_housekeeping.py\" --mode post-install" in install
    assert "sys.path.insert" in runner
    assert "--mode" in runner
