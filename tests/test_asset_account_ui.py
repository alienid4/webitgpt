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
    service = read("webapp/services/inventory_service.py")

    assert "account-metric-link" in html
    assert 'data-account-tab-jump="host"' in html
    assert 'data-account-tab-jump="departments"' in html
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
