from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_asset_actions_are_consistent_and_superadmin_only_for_sensitive_buttons():
    hosts = read("webapp/templates/hosts.html")
    debug_route = read("webapp/routes/api_debug.py")
    compliance_route = read("webapp/routes/api_compliance.py")

    assert "asset-row-actions" in hosts
    assert 'class="btn-sm btn-secondary"' in hosts
    assert 'current_user.role == "superadmin"' in hosts
    assert "data-debug" in hosts
    assert "evaluate_host_page" in hosts
    assert '@require_role("superadmin")' in debug_route
    assert compliance_route.count('@require_role("superadmin")') >= 2


def test_account_metrics_link_to_detail_views():
    html = read("webapp/templates/accounts_inventory.html")
    js = read("webapp/static/js/account_inventory.js")
    css = read("webapp/static/css/cathay.css")
    service = read("webapp/services/inventory_service.py")

    assert "account-metric-link" in html
    assert "account-summary-shell" in html
    assert 'data-account-tab-jump="host"' in html
    assert 'data-account-tab-jump="departments"' in html
    assert 'href="#list" data-account-tab-jump="list"' in html
    assert "scrollIntoView" not in js
    assert "account-summary-shell" in css
    assert "position: sticky" in css
    for metric in ["abnormal", "privileged", "never_login", "service_login", "pam_managed", "system_default"]:
        assert f"metric='{metric}'" in html
    assert "activateAccountTab" in js
    assert "window.location.hash" in js
    assert 'metric == "pam_managed"' in service
    assert 'metric == "system_default"' in service


def test_inventory_metrics_link_to_details_and_diff_filters():
    inventory = read("webapp/templates/inventory.html")
    diff = read("webapp/templates/inventory_diff_report.html")
    routes = read("webapp/routes/api_inventory.py")
    service = read("webapp/services/inventory_service.py")

    assert "inventory-metric-link" in inventory
    assert 'id="software-packages"' in inventory
    assert 'id="software-history"' in inventory
    assert 'id="software-changes"' in inventory
    assert "change_type='新增'" in inventory
    assert "change_type='移除'" in inventory
    assert "change_type='變更'" in inventory
    assert 'id="diff-details"' in diff
    assert "report.filter.change_type" in diff
    assert 'request.args.get("change_type", "")' in routes
    assert "def inventory_diff_report(kind: str, run_id: str = \"\", change_type: str = \"\")" in service
    assert "filtered_rows" in service


def test_deep_check_items_are_collapsible_and_have_problem_recommendation():
    html = read("webapp/templates/inspections.html")
    css = read("webapp/static/css/cathay.css")
    service = read("webapp/services/deep_check_service.py")

    assert '<details class="l3-item l3-{{ item.level }}" data-l3-verdict="{{ item.verdict }}">' in html
    assert "l3-item-summary" in html
    assert "問題點" in html
    assert "建議處置" in html
    assert ".l3-item-summary" in css
    assert "def _problem_summary(" in service
    assert "def _recommendation(" in service


def test_opening_check_is_system_scoped_and_deep_check_supports_aix():
    html = read("webapp/templates/inspections.html")
    routes = read("webapp/routes/api_operations.py")
    legacy = read("webapp/services/legacy_parity_service.py")
    deep = read("webapp/services/deep_check_service.py")

    assert "開門檢查系統" in html
    assert 'name="system"' in html
    assert "巡檢目前範圍" in html
    assert "全部系統" in html
    assert "搜尋系統" in html
    assert "data-opening-system-search" in html
    assert "data-opening-system-select" in html
    assert "diagnostics.all_systems_value" in html
    assert "diagnostics.all_systems_count" in html
    assert "diagnostics.selected_system_label" in html
    assert "system=diagnostics.selected_system if diagnostics.selected_system else diagnostics.all_systems_value" in html
    assert 'host.host_type in ["linux", "aix"]' in html
    assert "data-l3-filter" in html
    assert "data-l3-verdict" in html
    assert "data-score-ring" in html
    assert "data-score=\"{{ host.summary.score if host.summary else 0 }}\"" in html
    assert "conic-gradient" in read("webapp/static/css/cathay.css")
    assert "refreshScoreRings" in read("webapp/static/js/admin_tools.js")
    assert "api_superadmin.log_exceptions_page" in html
    assert "aspect-helper-link" in html
    assert ".aspect-helper-link" in read("webapp/static/css/cathay.css")
    assert "[data-l3-filter]" in read("webapp/static/js/admin_tools.js")
    assert "[data-opening-system-search]" in read("webapp/static/js/admin_tools.js")
    assert 'option.value === "__all__"' in read("webapp/static/js/admin_tools.js")
    assert "daily_diagnostics(platform, system_name)" in routes
    assert "OPENING_DEFAULT_SYSTEM" in legacy
    assert "OPENING_ALL_SYSTEMS_VALUE" in legacy
    assert "if requested == OPENING_ALL_SYSTEMS_VALUE:" in legacy
    assert '"all_systems_count": sum(item["count"] for item in options)' in legacy
    assert "selected_system" in legacy
    assert "AIX_COMMANDS" in deep
    assert 'host.get("host_type") not in {"linux", "aix"}' in deep


def test_metric_cards_are_clickable_across_pages():
    for path in (ROOT / "webapp/templates").glob("*.html"):
        html = read(path)
        assert '<div class="metric"' not in html, str(path)
        assert '<div class="metric-card"' not in html, str(path)
        if 'class="metric' in html:
            assert '<a class="metric' in html, str(path)
            assert 'href="' in html, str(path)
    hosts = read("webapp/templates/hosts.html")
    security = read("webapp/templates/security_audit.html")
    deps = read("webapp/templates/dependencies.html")
    assert 'id="asset-details"' in hosts
    assert 'id="security-hosts"' in security
    assert 'id="security-rules"' in security
    assert 'id="reconcile-details"' in deps
    assert "統計格 UI Skill" in read("docs/ui_metric_card_skill.md")
