from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_asset_nav_has_active_contract():
    base_html = read("webapp/templates/base.html")
    css = read("webapp/static/css/cathay.css")

    assert 'data-nav-key="assets"' in base_html
    assert "endpoint.startswith('api_hosts.')" in base_html
    assert ".nav a.active" in css
    assert "background: var(--g-light);" in css
    assert "box-shadow: inset 0 -3px 0 var(--g1);" in css
    assert ".nav a.nav-warn.active" in css


def test_saved_view_form_has_visible_asset_filters():
    hosts_html = read("webapp/templates/hosts.html")

    assert 'select name="host_type"' in hosts_html
    assert 'select name="environment"' in hosts_html
    assert 'select name="dc"' in hosts_html


def test_top_navigation_supports_personal_ordering():
    base_html = read("webapp/templates/base.html")
    js = read("webapp/static/js/ui_tools.js")
    css = read("webapp/static/css/cathay.css")

    assert 'data-nav-key="assets"' in base_html
    assert 'draggable="true"' in base_html
    assert "webitgpt-nav-order" in js
    assert "localStorage.setItem(navStorageKey" in js
    assert '.nav a[draggable="true"]' in css


def test_ipam_has_network_reconcile_report():
    ipam_html = read("webapp/templates/ipam.html")
    routes = read("webapp/routes/api_hosts.py")
    service = read("webapp/services/cmdb_service.py")

    assert "ipam_scan_report_submit" in routes
    assert "run_network_reconcile" in service
    assert '["nmap", "-sn", "-oX", "-", cidr]' in service
    assert "diff" in ipam_html or "report" in ipam_html.lower()


def test_ipam_schedule_is_configurable():
    installer = read("scripts/install_systemd.sh")
    script = read("scripts/weekly_ipam_reconcile.py")
    schedule_service = read("webapp/services/ipam_schedule_service.py")
    ipam_html = read("webapp/templates/ipam.html")
    routes = read("webapp/routes/api_hosts.py")

    assert "webitgpt-ipam-reconcile.timer" in installer
    assert "OnCalendar=*-*-* *:0/5:00" in installer
    assert "weekly_ipam_reconcile.py" in installer
    assert "should_run_now" in script
    assert "run_network_reconcile" in script
    assert '"weekday": "mon"' in schedule_service
    assert '"time": "07:30"' in schedule_service
    assert "ipam_reconcile_schedule" in schedule_service
    assert 'select name="weekday"' in ipam_html
    assert 'input name="time" type="time"' in ipam_html
    assert "ipam_schedule_submit" in routes
    assert "ipam_schedule_service.save_schedule" in routes


def test_dashboard_and_parity_pages_are_wired():
    base_html = read("webapp/templates/base.html")
    reports_route = read("webapp/routes/api_reports.py")
    superadmin_route = read("webapp/routes/api_superadmin.py")
    parity = read("webapp/templates/feature_parity.html")

    assert "dashboard_page" in reports_route
    assert "executive_page" in reports_route
    assert "api_reports.dashboard_page" in base_html
    assert "api_reports.executive_page" in base_html
    assert "feature_parity_page" in superadmin_route
    assert "v3.17" in superadmin_route or "v3.17" in parity


def test_legacy_module_wave1_pages_exist():
    base_html = read("webapp/templates/base.html")
    inspections = read("webapp/templates/inspections.html")
    inventory = read("webapp/templates/inventory.html")
    nmon = read("webapp/templates/nmon.html")
    dependencies = read("webapp/templates/dependencies.html")
    compliance = read("webapp/templates/security_audit.html")

    assert "api_operations.inspections_page" in base_html
    assert "api_reports.dependencies_page" in base_html
    assert "開門檢查" in base_html
    assert "開門檢查" in inspections
    assert "OPENING CHECK" in inspections
    assert "今日巡檢" not in base_html
    assert "run-inspection" in inspections or "/api/inspections/run" in inspections
    assert "深度檢查" in inspections
    assert "最近一週" in inspections
    assert "deep_diagnostic_page" in read("webapp/routes/api_operations.py")
    assert "run_deep_diagnostic" in read("webapp/services/legacy_parity_service.py")
    assert "diagnostic_results" in read("scripts/bootstrap.py")
    assert "/api/inventory/" in inventory
    assert "/api/nmon/status" in nmon or "nmon" in nmon.lower()
    assert "dependencies" in dependencies.lower() or "api/reports/dependencies" in dependencies
    assert "topology-edge" in dependencies
    assert "edge.x1" in dependencies
    assert "聯通清單" in dependencies
    assert "data-topology-zoom-in" in dependencies
    assert "data-topology-stage" in dependencies
    assert "topology-node-dc" in dependencies
    assert "data-topology-canvas" in read("webapp/static/js/ui_tools.js")
    assert "--topology-scale" in read("webapp/static/css/cathay.css")
    assert "rollback" in compliance.lower()


def test_admin_and_dev_console_wave1_routes_exist():
    routes = read("webapp/routes/api_superadmin.py")
    for name in [
        "settings_page",
        "logs_page",
        "jobs_page",
        "audit_logs_page",
        "remote_tools_page",
        "dev_console_page",
    ]:
        assert name in routes


def test_install_script_installs_nmap_for_ipam_scan():
    install = read("scripts/install.sh")

    assert "ensure_system_tool nmap nmap" in install
    assert "dnf install -y" in install
    assert "apt-get install -y" in install
    assert "please install ${package_name} manually for IPAM scan" in install


def test_inventory_history_and_cooldown_contracts_exist():
    inventory_service = read("webapp/services/inventory_service.py")
    legacy_service = read("webapp/services/legacy_parity_service.py")
    routes = read("webapp/routes/api_inventory.py")
    bootstrap = read("scripts/bootstrap.py")

    assert "DEFAULT_MIN_INTERVAL_MINUTES = 360" in inventory_service
    assert "def inventory_history(" in inventory_service
    assert "def _cooldown_result(" in inventory_service
    assert "%Y%m%d%H%M%S%f" in inventory_service
    assert "inventory_snapshots" in inventory_service
    assert "inventory_runs" in bootstrap
    assert "inventory_snapshots" in bootstrap
    assert "software_inventory_changes" in bootstrap
    assert "def _software_cooldown(" in legacy_service
    assert "%Y%m%d%H%M%S%f" in legacy_service
    assert '"/api/inventory/<kind>/history"' in routes
    assert "force=bool(payload.get(\"force\"))" in routes


def test_inventory_pages_show_history_and_force_collect():
    accounts_html = read("webapp/templates/accounts_inventory.html")
    software_html = read("webapp/templates/inventory.html")

    assert "history" in accounts_html.lower() or "inventory_history" in accounts_html
    assert "force" in accounts_html
    assert "360" in accounts_html
    assert "history" in software_html.lower() or "inventory_history" in software_html
    assert "force" in software_html
    assert "360" in software_html


def test_inventory_diff_report_contracts_exist():
    inventory_service = read("webapp/services/inventory_service.py")
    routes = read("webapp/routes/api_inventory.py")
    report_html = read("webapp/templates/inventory_diff_report.html")
    accounts_html = read("webapp/templates/accounts_inventory.html")
    software_html = read("webapp/templates/inventory.html")

    assert "def inventory_diff_report(" in inventory_service
    assert "def export_inventory_diff_csv(" in inventory_service
    assert "_changed_fields" in inventory_service
    assert '"/inventory/<kind>/diff-report"' in routes
    assert '"/inventory/<kind>/diff-report.csv"' in routes
    assert '"/api/inventory/<kind>/diff-report"' in routes
    assert "diff" in report_html.lower()
    assert "csv" in report_html.lower()
    assert "inventory_diff_report_page" in accounts_html
    assert "inventory_diff_report_page" in software_html


def test_topology_spec_foundation_contracts_exist():
    service = read("webapp/services/dependency_service.py")
    routes = read("webapp/routes/api_dependencies.py")
    app = read("webapp/app.py")
    bootstrap = read("scripts/bootstrap.py")
    page = read("webapp/templates/dependencies.html")
    ghosts = read("webapp/templates/dependencies_ghosts.html")

    for name in [
        "def topology(",
        "def _system_topology(",
        "def _host_topology(",
        "def _ip_topology(",
        "def downstream_impact(",
        "def upstream_impact(",
        "def analyze_ghosts(",
        "def adopt_ghost(",
        "def collect_topology(",
        "def latest_collect_run(",
        "def collect_runs(",
        "ss -tunp",
    ]:
        assert name in service
    assert "hashlib.sha1" in service
    for endpoint in [
        "/api/dependencies/systems",
        "/api/dependencies/relations",
        "/api/dependencies/topology",
        "/api/dependencies/impact",
        "/api/dependencies/ghosts",
        "/api/dependencies/collect/trigger",
        "/dependencies/collect/trigger",
    ]:
        assert endpoint in routes
    assert "api_dependencies" in app
    assert "def _port_summary(" in service
    assert "def _edge_payload(" in service
    assert "dependency_systems" in bootstrap
    assert "dependency_relations" in bootstrap
    assert "dependency_collect_runs" in bootstrap
    assert "dependency_ghost_ignored" in bootstrap
    assert "系統視角" in page and "主機視角" in page and "IP 視角" in page
    assert "edge.detail_label" in page and "edge.port_summary" in page
    assert "edge.caption" not in page
    assert "Port 明細請看下方清單" in page
    assert "執行 ss -tunp 採集" in page
    assert "採集狀態" in page
    assert "Ghost 清單" in ghosts


def test_superadmin_console_is_complete_and_chinese():
    routes = read("webapp/routes/api_superadmin.py")
    service = read("webapp/services/system_service.py")
    superadmin = read("webapp/templates/superadmin.html")
    settings = read("webapp/templates/system_settings.html")
    logs = read("webapp/templates/system_logs.html")
    jobs = read("webapp/templates/system_jobs.html")
    audit = read("webapp/templates/operation_logs.html")

    assert "def admin_console_overview(" in service
    assert "def operation_logs_csv(" in service
    assert "settings_api" in routes
    assert "logs_api" in routes
    assert "logs_download" in routes
    assert "jobs_api" in routes
    assert "audit_logs_api" in routes
    assert "audit_logs_csv" in routes
    assert "系統管理後台" in superadmin
    assert "管理模組" in superadmin
    assert "功能開關" in superadmin
    assert "使用者與權限" in superadmin
    assert "操作紀錄" in superadmin
    assert "設定管理" in settings
    assert "日誌檢視" in logs
    assert "工作排程" in jobs
    assert "匯出 CSV" in audit


def test_legacy_5000_style_density_contract():
    css = read("webapp/static/css/cathay.css")
    base_html = read("webapp/templates/base.html")

    assert "Legacy v3.17-style density" in css
    assert "--content-max: none;" in css
    assert ".nav a.active" in css
    assert "background: transparent;" in css
    assert "box-shadow: inset 0 -3px 0 var(--g1);" in css
    assert "v{{ app_version }} <span>|</span> {{ build_time }}" in base_html
    assert "{{ patch_id }} / {{ release_note }}" in base_html


def test_dev_console_uses_legacy_workbench_layout():
    css = read("webapp/static/css/cathay.css")
    validation = read("webapp/templates/validation.html")
    dev_console = read("webapp/templates/dev_console.html")
    dev_tabs = read("webapp/templates/_partials/dev_tabs.html")

    assert ".dev-workbench" in css
    assert ".dev-toolbar" in css
    assert ".dev-grid" in css
    assert "dev-workbench" in validation
    assert "dev-toolbar" in validation
    assert "dev-grid" in validation
    assert "驗證報告" in dev_tabs
    assert "開發者文件" in dev_tabs
    assert "檔案管理" in dev_tabs
    assert "備忘錄" in dev_tabs
    assert "dev-admin-v317" in dev_console
    assert "dev-admin-tabs" not in dev_console
    assert "GitHub 推送" not in dev_console
    assert "GitHub 推送" not in dev_tabs
    assert "提交紀錄" in dev_console


def test_dev_validation_summary_is_compact():
    css = read("webapp/static/css/cathay.css")
    validation = read("webapp/templates/validation.html")

    assert "dev-compact-summary" in validation
    assert "<details class=\"dev-detail\">" in validation
    assert "dev-summary" not in validation
    assert ".dev-compact-summary" in css
    assert ".dev-detail summary" in css


def test_dev_console_has_v317_superadmin_tabs():
    css = read("webapp/static/css/cathay.css")
    service = read("webapp/services/system_service.py")
    dev_console = read("webapp/templates/dev_console.html")
    validation = read("webapp/templates/validation.html")
    dev_tabs = read("webapp/templates/_partials/dev_tabs.html")
    ui_tools = read("webapp/static/js/ui_tools.js")
    base_html = read("webapp/templates/base.html")

    for label in ["開發者文件", "檔案管理", "備忘錄", "提交紀錄", "模組管理"]:
        assert label in dev_tabs
    assert "github-push" not in dev_tabs
    assert "github_push" not in dev_console
    assert "GitHub 推送" not in service
    assert "dev-admin-v317" in dev_console
    assert "dev-admin-tabs" not in dev_console
    assert "data-dev-panel=\"developer-docs\"" in dev_tabs
    assert "data-dev-panel-target=\"developer-docs\"" in dev_console
    assert "draggable=\"true\"" in dev_tabs
    assert "_partials/dev_tabs.html" in validation
    assert "data-tab-storage=\"webitgpt-dev-section-tabs\"" in dev_tabs
    assert "data-dev-tab-key=\"validation\"" in dev_tabs
    assert "data-dev-tab-key=\"developer-docs\"" in dev_tabs
    assert "data-dev-tab-key=\"module-manager\"" in dev_tabs
    assert "console.files" in dev_console
    assert "console.modules" in dev_console
    assert "console.release_notes" in dev_console
    assert "修復內容" in dev_console
    assert "技術提交明細" in dev_console
    assert "release.changes" in dev_console
    assert "\"changes\": []" in service
    assert "current[\"changes\"].append" in service
    assert "root_files" in service
    assert "def release_notes" in service
    assert "CHANGELOG.md" in service
    assert "save_dev_upload" in service
    assert "dev_console_upload_page" in read("webapp/routes/api_superadmin.py")
    assert "dev_console_feature_update_page" in read("webapp/routes/api_superadmin.py")
    assert "enctype=\"multipart/form-data\"" in dev_console
    assert "上傳檔案" in dev_console
    assert "重新整理" in dev_console
    assert "dev_console.upload" in read("webapp/routes/api_superadmin.py")
    assert "modules" in service
    assert "MODULE_IMPACT" in service
    assert "控制範圍" in dev_console
    assert "關閉後影響" in dev_console
    assert "recommendation" in service
    assert "effective_enabled" in service
    assert "module_compliance_security" in service
    assert ".dev-admin-panel" in css
    assert ".dev-admin-panel.active" in css
    assert ".dev-upload-bar" in css
    assert ".dev-release-items" in css
    assert "enableSortableTabs" in ui_tools
    assert "enableDevPanelTabs" in ui_tools
    assert "localStorage.setItem(storageKey" in ui_tools
    assert "localStorage.setItem(activeKey" in ui_tools
    assert "dev_console_endpoints" in base_html
    assert "endpoint not in dev_console_endpoints" in base_html
