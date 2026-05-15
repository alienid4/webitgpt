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
    assert "巡檢目前系統" in html
    assert "system=diagnostics.selected_system" in html
    assert 'host.host_type in ["linux", "aix"]' in html
    assert "data-l3-filter" in html
    assert "data-l3-verdict" in html
    assert "[data-l3-filter]" in read("webapp/static/js/admin_tools.js")
    assert "daily_diagnostics(platform, system_name)" in routes
    assert "OPENING_DEFAULT_SYSTEM" in legacy
    assert "selected_system" in legacy
    assert "AIX_COMMANDS" in deep
    assert 'host.get("host_type") not in {"linux", "aix"}' in deep
