from pathlib import Path

from webapp.services.inventory_service import account_risk_label, is_account_abnormal, normalize_account_risk


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_never_login_is_information_not_abnormal_risk():
    risk = normalize_account_risk("alien", {"risk": "從未登入", "can_login": True}, system_default=False)

    assert risk == "正常"


def test_high_privilege_is_review_item_not_abnormal():
    assert is_account_abnormal({"risk": "高權限", "privileged": True}) is False
    assert is_account_abnormal({"risk": "服務帳號可登入", "privileged": False}) is True


def test_service_login_risk_label_requires_review():
    assert account_risk_label("服務帳號可登入") == "服務帳號可登入，需複核"
    assert account_risk_label("高權限") == "高權限"


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


def test_asset_add_host_entry_is_clear_from_asset_page():
    hosts = read("webapp/templates/hosts.html")

    assert "新增 / 匯入主機" in hosts
    assert "host_new_page" in hosts
    assert "asset-intake-panel" not in hosts
    assert "要新增主機，先選你手上的資料型態" not in hosts
    assert "單筆新增主機" not in hosts
    assert "Excel / CSV 大量匯入" not in hosts
    assert "掃描網段建立草稿" not in hosts


def test_asset_secondary_actions_are_grouped_and_scan_rows_are_expandable():
    hosts = read("webapp/templates/hosts.html")
    host_new = read("webapp/templates/host_new.html")
    css = read("webapp/static/css/cathay.css")

    assert "asset-action-menu" in hosts
    assert "更多操作" in hosts
    assert "CMDB 資產池" in hosts
    assert "分類檢視" in hosts
    for text in ["全部資產池", "主機證據", "資料資產", "軟體 / AP", "人員窗口", "待分類"]:
        assert text in hosts
    for query in ["type='hardware'", "type='data'", "type='software'", "type='people'", "type='unknown'"]:
        assert query in hosts
    for label in ["資料維護", "匯出 / 匯入", "治理工具"]:
        assert label in hosts
    assert "scan-row-detail" in host_new
    assert "展開技術明細" in host_new
    assert "將勾選 IP 建立待補草稿" in host_new
    assert "進入草稿區處理" in host_new
    assert "下一步不是結束" in host_new
    assert "去草稿區批次補欄位" in host_new
    assert "立即補這台資料" in host_new
    assert "批次轉正式，才算完成主機新增" in host_new
    assert "新增待補草稿完成，共" in host_new
    assert "進入草稿區處理" in host_new
    assert "hide_draft_governance = true" in hosts
    assert 'request.args.get("status") == "draft" and not hide_draft_governance' in hosts
    assert "草稿轉正式完成" in hosts
    assert '<details class="asset-bulk-panel asset-optional-section">' in hosts
    assert "host.status == \"draft\" and not hide_draft_governance" in hosts
    assert "asset-bulk-panel[open]" in css
    assert "資產已儲存，已回到資產管理列表" in hosts
    host_edit = read("webapp/templates/host_edit.html")
    host_routes = read("webapp/routes/api_hosts.py")
    cmdb_service = read("webapp/services/cmdb_service.py")
    assert "儲存並回資產管理" in host_edit
    assert "儲存後繼續編輯" in host_edit
    assert "掃描帶入建議" in host_edit
    assert "先掃描，再矯正資產主檔" in host_edit
    assert "建議值只放進表單，仍需人工確認後儲存" in host_edit
    assert "掃描方式：nmap TCP 常見服務優先" in host_edit
    assert "prefillScanForm" in host_edit
    assert "asset-prefill-panel" in css
    assert "asset-optional-section" in host_edit
    assert "asset-optional-section[open]" in css
    assert "低頻操作，只有需要從 IPAM" in host_edit
    assert "停用、申請下線、下線封存等低頻治理動作" in host_edit
    assert "PAM 代號、業務窗口備註等非必要欄位" in host_edit
    assert "host_prefill_scan_submit" in host_routes
    assert "scan_host_prefill" in cmdb_service
    assert "after_save" in host_routes
    assert "asset_saved" in read("webapp/routes/api_hosts.py")
    assert 'errors=[f"儲存失敗：{exc}"]' in host_routes
    assert "current_app.logger.exception(\"host_edit_submit failed" in host_routes
    host_service = read("webapp/services/host_service.py")
    assert "_sync_host_dir_best_effort" in host_service
    assert "host_dir_status" in host_service
    assert "host_dir_error" in host_service
    assert "host directory sync skipped" in host_service
    assert "新增方式導覽" in host_new
    assert "判斷標籤與來源說明預設收合" in host_new
    assert '<details class="panel compact asset-helper-panel">' in host_new
    assert '<details class="judgement-source-legend asset-helper-panel"' in host_new
    assert '<details class="panel asset-create-step" id="single-create">' in host_new
    assert '<details class="panel asset-create-step" id="csv-import" {% if import_result %}open{% endif %}>' in host_new
    assert '<details class="panel asset-create-step" id="network-scan">' in host_new
    assert "展開第 3 步查看掃描結果" in host_new
    assert "step-expand-label" in host_new
    assert "驗證或人工確認主機識別、負責人與用途" in host_new
    assert "3 驗證 / 確認資料" in hosts
    assert "4 批次轉正式，完成新增" in hosts
    assert "{% if host.status == \"draft\" %}補資料{% else %}編輯{% endif %}" in hosts
    assert "draft-next-panel" in css
    assert "draft-workflow-panel" in css
    assert "asset-create-step[open]" in css
    assert "asset-helper-panel[open]" in css
    assert "asset-action-menu-panel" in css
    assert "scan-result-table" in css
    assert "openHashTarget" in read("webapp/static/js/host_new.js")


def test_account_metrics_link_to_detail_views():
    html = read("webapp/templates/accounts_inventory.html")
    js = read("webapp/static/js/account_inventory.js")
    css = read("webapp/static/css/cathay.css")
    service = read("webapp/services/inventory_service.py")

    assert "account-metric-link" in html
    assert "account-summary-shell" in html
    assert "服務帳號可登入，需複核" in html
    assert "risk_label" in html
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


def test_account_excel_inventory_tabs_and_upload_contracts_exist():
    html = read("webapp/templates/accounts_inventory.html")
    js = read("webapp/static/js/account_inventory.js")
    css = read("webapp/static/css/cathay.css")
    routes = read("webapp/routes/api_inventory.py")
    service = read("webapp/services/inventory_service.py")

    for label in ["帳號清冊", "Excel 清冊", "差異報告", "盤點批次"]:
        assert label in html
    assert "data-account-main-tab" in html
    assert "data-account-main-panel" in html
    assert "accounts_template_xlsx" in routes
    assert "accounts_excel_upload" in routes
    assert "accounts_excel_diff_csv" in routes
    assert "import_account_excel_inventory" in routes
    assert "account_excel_template_xlsx" in service
    assert "import_account_excel_inventory" in service
    assert "account_excel_diff_view" in service
    assert "account_excel_workbench" in service
    assert "Excel 有，主機沒有" in html
    assert "主機有，Excel 沒有" in html
    assert "activateAccountMainTab" in js
    assert ".account-main-tabs" in css
    assert ".account-upload-bar" in css


def test_ap_account_inventory_import_and_report_contracts_exist():
    html = read("webapp/templates/accounts_inventory.html")
    routes = read("webapp/routes/api_inventory.py")
    service = read("webapp/services/inventory_service.py")

    assert "AP 帳號" in html
    assert 'data-account-main-tab="ap"' in html
    assert 'data-account-main-panel="ap"' in html
    assert "accounts_ap_template_xlsx" in routes
    assert "accounts_ap_upload" in routes
    assert "accounts_ap_csv" in routes
    assert "accounts_ap_diff_csv" in routes
    assert "AP_ACCOUNT_HEADERS" in service
    assert 'AP_ACCOUNT_REQUIRED_FIELDS = ["app_id", "system_name", "account"]' in service
    assert "import_ap_account_inventory" in service
    assert "ap_account_report" in service
    assert "ap_account_diff_view" in service
    assert "owner、PAM、權限、最後登入等欄位可以空白" in html


def test_cmdb_csv_validation_and_self_check_guard_contracts_exist():
    csv_service = read("webapp/services/csv_service.py")
    host_routes = read("webapp/routes/api_hosts.py")
    self_check = read("webapp/routes/api_self_check.py")

    assert "def validate_csv(" in csv_service
    assert "def validation_errors_csv(" in csv_service
    assert "def validate_xlsx(" in csv_service
    assert "def validation_errors_xlsx(" in csv_service
    assert "def export_hosts_xlsx(" in csv_service
    assert 'return "\\ufeff" + output.getvalue()' in csv_service
    assert '"/api/hosts/csv/validate"' in host_routes
    assert '"/api/hosts/csv/validate.csv"' in host_routes
    assert '"/api/hosts/xlsx/import"' in host_routes
    assert '"/api/hosts/xlsx/export"' in host_routes
    assert '"/api/hosts/xlsx/validate"' in host_routes
    assert '"/api/hosts/xlsx/validate.xlsx"' in host_routes
    assert "duplicate asset_seq" in csv_service
    assert "payload.get(\"limit\", request.args.get(\"limit\", \"10\"))" in self_check
    assert "min(max(int(requested_limit), 1), 20)" in self_check
    assert "except TimeoutError" in self_check


def test_cmdb_import_report_excel_and_draft_bulk_contracts_exist():
    csv_service = read("webapp/services/csv_service.py")
    host_new = read("webapp/templates/host_new.html")
    hosts = read("webapp/templates/hosts.html")
    host_routes = read("webapp/routes/api_hosts.py")
    host_service = read("webapp/services/host_service.py")
    hosts_js = read("webapp/static/js/hosts.js")
    changelog = read("CHANGELOG.md")

    for text in ["CMDB 匯入結果摘要", "讀到筆數", "成功入庫", "人可讀原因", "匯入 CSV / Excel"]:
        assert text in host_new
    assert "錯誤明細只顯示前 10 筆" in host_new
    assert "{{ import_result.errors }}" not in host_new
    for text in ["批次轉正式", "批次補欄位", "bulkDraftPromoteForm", "bulkDraftPromoteAllForm", "bulkDraftUpdateForm", "匯出 Excel"]:
        assert text in hosts
    for text in ["草稿轉正式完成", "仍留草稿", "bulk_skip_reasons", "看正式資產", "看剩餘草稿"]:
        assert text in hosts
    assert 'name="scope" value="all_drafts"' in hosts
    for text in ["host_bulk_promote_drafts_submit", "host_bulk_update_drafts_submit", "xlsx_export", "xlsx_import"]:
        assert text in host_routes
    assert "_summarize_bulk_skip_reasons" in host_routes
    assert "list_draft_host_keys" in host_routes
    for text in ["bulk_promote_draft_hosts", "bulk_update_draft_hosts", "bulk_promote_draft", "bulk_update_draft", "list_draft_host_keys"]:
        assert text in host_service
    assert "data-draft-bulk-form" in hosts
    assert "data-draft-bulk-copy" in hosts_js
    assert "xlsx_rows_from_bytes" in csv_service
    assert "cmdb-import-report-excel-drafts" in changelog


def test_cmdb_workbook_import_contracts_exist():
    csv_service = read("webapp/services/csv_service.py")
    workbook_service = read("webapp/services/cmdb_workbook_service.py")
    host_routes = read("webapp/routes/api_hosts.py")
    host_new = read("webapp/templates/host_new.html")
    hosts = read("webapp/templates/hosts.html")
    template = read("webapp/templates/cmdb_workbook.html")

    assert "def xlsx_workbook_rows_from_bytes" in csv_service
    assert "def workbook_preview" in workbook_service
    assert "def import_hardware_drafts" in workbook_service
    assert "def import_asset_pool" in workbook_service
    assert "def import_governed_workbook" in workbook_service
    assert "def update_asset_pool_item" in workbook_service
    assert "def _latest_audit" in workbook_service
    assert "ASSET_TYPE_TABS" in workbook_service
    assert "EDITABLE_FIELDS" in workbook_service
    assert "ghost_candidate" in workbook_service
    assert "quarantine_missing_identity" in workbook_service
    assert "ASSET_COLLECTION = \"cmdb_asset_pool\"" in workbook_service
    for route in [
        "cmdb_workbook_page",
        "cmdb_workbook_preview_page",
        "cmdb_workbook_import_hardware_page",
        "cmdb_workbook_import_governed_page",
        "cmdb_workbook_import_pool_page",
        "cmdb_asset_pool_edit_page",
        "cmdb_asset_pool_edit_submit",
    ]:
        assert route in host_routes
    assert "CMDB Excel 匯入精靈" in host_new
    assert "CMDB Excel 匯入精靈" in hosts
    for text in ["CMDB Excel 匯入精靈", "整份治理匯入", "幽靈候選", "待分類", "CMDB 資產池"]:
        assert text in template
    assert "cmdb-workbook-primary-import" in template
    assert "只預檢，不寫入" in template
    assert "1. 預檢整份 Excel" not in template
    assert "2. 整份治理匯入" not in template
    for text in ["目前資產池沒有資料，不代表匯入資料消失", "主機清冊", "最近主機匯入", "最近 Excel 預檢", "最近資產池匯入"]:
        assert text in template
    for text in ["去資產清冊看已匯入主機", "回到上方執行整份治理匯入", "cmdb-empty-diagnosis"]:
        assert text in template
    edit_template = read("webapp/templates/cmdb_asset_edit.html")
    for text in ["編輯 CMDB 資產池", "原始 Excel 資料", "變更原因"]:
        assert text in edit_template


def test_cmdb_workbook_sheet_classification():
    from webapp.services.cmdb_workbook_service import classify_sheet

    assert classify_sheet(["資產序號", "設備機型", "主機名稱", "作業系統", "IP"]) == "hardware"
    assert classify_sheet(["資產序號", "資料類別", "主機名稱", "IP"]) == "data"
    assert classify_sheet(["資產序號", "人員姓名", "聯絡電話"]) == "people"
    assert classify_sheet(["資產序號", "AP ID", "委外維護", "處理個資"]) == "software"


def test_cmdb_relationship_dashboard_contracts_exist():
    hosts = read("webapp/templates/hosts.html")
    relationships = read("webapp/templates/cmdb_relationships.html")
    host_routes = read("webapp/routes/api_hosts.py")
    service = read("webapp/services/cmdb_relationship_service.py")
    css = read("webapp/static/css/cathay.css")

    assert "cmdb_relationships_page" in host_routes
    assert "cmdb_relationship_service.cmdb_relationship_overview" in host_routes
    assert "cmdb_relationship_entry" not in hosts
    assert "cmdb-relationship-entry" in hosts
    for text in ["CMDB 關聯總覽", "關聯覆蓋率", "核心系統關聯檢視", "待補清單", "系統關聯覆蓋明細"]:
        assert text in relationships
    for token in ["cmdb_relationship_overview", "DRAFT_STATUSES", "missing_owner", "service_port"]:
        assert token in service
    assert "selected_system.topology_center" in relationships
    assert "system.topology_center" in relationships
    assert "center=selected_system.key" not in relationships
    assert "center=system.key" not in relationships
    for token in [".cmdb-coverage-grid", ".cmdb-relation-map", ".cmdb-gap-item", ".cmdb-system-table"]:
        assert token in css


def test_cmdb_relationship_overview_summarizes_quality_and_relationships(monkeypatch):
    from webapp.services import cmdb_relationship_service

    hosts = [
        {
            "hostname": "app1",
            "asset_name": "巡檢系統主機",
            "ip": "10.0.0.1",
            "status": "active",
            "system_name": "巡檢系統",
            "owner": "ops",
            "open_ports": [{"port": "8002"}],
        },
        {
            "hostname": "app2",
            "asset_name": "巡檢系統資料庫",
            "ip": "10.0.0.2",
            "status": "draft",
            "system_name": "巡檢系統",
        },
        {
            "hostname": "misc1",
            "asset_name": "未分類主機",
            "status": "active",
            "custodian": "infra",
        },
    ]

    class FakeCursor(list):
        def limit(self, _limit):
            return self

    class FakeCollection:
        def __init__(self, rows):
            self.rows = rows

        def find(self, *_args, **_kwargs):
            return FakeCursor(self.rows)

    def fake_get_collection(name):
        rows = {
            "dependency_systems": [{"system_id": "SYS-INSPECTION", "display_name": "巡檢系統"}],
            "dependency_relations": [{"from_system": "SYS-INSPECTION", "to_system": "SYS-MONGO"}],
        }
        return FakeCollection(rows.get(name, []))

    monkeypatch.setattr(cmdb_relationship_service.host_service, "list_hosts", lambda **_kwargs: {"items": hosts})
    monkeypatch.setattr(cmdb_relationship_service, "get_collection", fake_get_collection)

    overview = cmdb_relationship_service.cmdb_relationship_overview("巡檢")

    assert overview["summary"]["total"] == 3
    assert overview["summary"]["formal_count"] == 2
    assert overview["summary"]["draft_count"] == 1
    assert overview["summary"]["dependency_relation_count"] == 1
    assert overview["coverage"]["system"]["pct"] == 67
    assert overview["coverage"]["owner"]["pct"] == 67
    assert overview["coverage"]["service_port"]["pct"] == 33
    assert overview["selected_system"]["display_name"] == "巡檢系統"
    assert overview["selected_system"]["topology_center"] == "SYS-INSPECTION"
    assert overview["systems"][0]["topology_center"] == "SYS-INSPECTION"
    assert overview["selected_system"]["host_count"] == 2
    assert overview["selected_system"]["missing_owner"] == 1


def test_cmdb_relationship_page_renders_with_overview(monkeypatch):
    from webapp.app import create_app
    from webapp.routes import api_hosts

    fake_overview = {
        "summary": {
            "total": 3,
            "formal_count": 2,
            "draft_count": 1,
            "dependency_relation_count": 1,
        },
        "coverage": {
            "system": {"label": "系統關聯率", "count": 2, "total": 3, "pct": 67},
            "owner": {"label": "owner 完整率", "count": 2, "total": 3, "pct": 67},
            "notification": {"label": "通知依據完整率", "count": 2, "total": 3, "pct": 67},
            "service_port": {"label": "服務 / Port 完整率", "count": 1, "total": 3, "pct": 33},
        },
        "gaps": [
            {"key": "missing_owner", "label": "缺 owner / 保管者", "count": 1, "action": "補 owner"},
        ],
        "systems": [
            {
                "key": "巡檢系統",
                "topology_center": "SYS-INSPECTION",
                "display_name": "巡檢系統",
                "is_classified": True,
                "host_count": 2,
                "formal_count": 1,
                "draft_count": 1,
                "owners": ["ops"],
                "missing_owner": 1,
                "missing_notification": 0,
                "missing_ports": 1,
            }
        ],
        "selected_system": {
            "key": "巡檢系統",
            "topology_center": "SYS-INSPECTION",
            "display_name": "巡檢系統",
            "host_count": 2,
            "formal_count": 1,
            "draft_count": 1,
            "missing_owner": 1,
            "missing_notification": 0,
            "missing_ports": 1,
            "owners": ["ops"],
            "ports": ["8002"],
            "hosts": [{"hostname": "app1", "ip": "10.0.0.1"}],
        },
    }

    monkeypatch.setattr(api_hosts.cmdb_relationship_service, "cmdb_relationship_overview", lambda _selected="": fake_overview)
    app = create_app()
    client = app.test_client()

    response = client.get("/hosts/cmdb-relationships")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "CMDB 關聯總覽" in body
    assert "關聯覆蓋率" in body
    assert "巡檢系統" in body


def test_operations_hardening_to_10323_contracts_exist():
    html = read("webapp/templates/accounts_inventory.html")
    service = read("webapp/services/inventory_service.py")
    reports = read("webapp/routes/api_reports.py")
    deps = read("webapp/services/dependency_service.py")
    deps_html = read("webapp/templates/dependencies.html")
    css = read("webapp/static/css/cathay.css")
    config = read("webapp/config.py")

    assert 'VERSION = "1.0.3.86"' in config
    assert "AP_ACCOUNT_RISK_LABELS" in service
    for text in ["缺 owner", "高權限未納 PAM", "高權限未啟用 MFA", "超過 180 天未登入"]:
        assert text in service
    assert "AP 風險分類" in html
    assert "operations_data_quality" in reports
    assert '"degraded" if warnings' in read("webapp/services/quality_service.py")
    assert '"/api/reports/data-quality"' in reports
    assert '"/api/reports/data-quality.csv"' in reports
    assert "trust_summary" in deps
    assert "trust_note" in deps
    assert "topology-trust-list" in deps_html
    assert ".topology-trust-list" in css
    assert "post_install_verify.sh" in read("docs/release_notes/v1.0.3.20.md")
    assert "phase_readonly_mode" in read("docs/operations_hardening_roadmap.md")


def test_ops_ux_to_10329_contracts_exist():
    dashboard = read("webapp/templates/dashboard.html")
    reports = read("webapp/templates/reports.html")
    routes = read("webapp/routes/api_reports.py")
    quality = read("webapp/templates/data_quality.html")
    post_install = read("webapp/templates/post_install_report.html")
    css = read("webapp/static/css/cathay.css")
    service = read("webapp/services/system_service.py")

    assert "維運總覽" in dashboard
    assert "資料品質分數" in dashboard
    assert "ops-decision-grid" in dashboard
    assert "資料品質工作台" in quality
    assert "quality-score-band" in quality
    assert "安裝後驗證" in post_install
    assert "post_install_verify.sh" in post_install
    assert "統計報表" in reports
    assert "資料品質缺口" in reports
    assert "data_quality_page" in routes
    assert "post_install_report_page" in routes
    assert ".ops-hero" in css
    assert ".quality-score-band" in css
    assert "1.0.3.29" in service
    assert "ops-ux-decision-workbench" in read("CHANGELOG.md")


def test_cmdb_quality_actionable_platform_fix_contracts_exist():
    quality_service = read("webapp/services/quality_service.py")
    data_quality = read("webapp/templates/data_quality.html")
    hosts = read("webapp/templates/hosts.html")
    host_service = read("webapp/services/host_service.py")
    cmdb_service = read("webapp/services/cmdb_service.py")
    reports = read("webapp/routes/api_reports.py")

    assert "infer_host_type_from_os" in host_service
    assert "platform_suggestion_for_host" in host_service
    assert "platform_mismatch" in cmdb_service
    assert "平台分類疑似不正確" in cmdb_service
    assert "OS 版本為" in cmdb_service
    assert "OS 是版本與發行版資訊" in cmdb_service
    assert "cmdb_detail_rows" in quality_service
    assert "CMDB 需檢視明細" in data_quality
    assert "平台分類需修正" in data_quality
    assert "OS 版本推論平台分類" in data_quality
    assert "status_label" in data_quality
    assert "cmdb_breakdown" in reports
    assert "bulk_apply_platform_suggestions" in host_service
    assert "data_quality_apply_platform_suggestions" in reports
    assert "套用平台分類建議" in data_quality
    assert "bulk_apply_default_connections" in host_service
    assert "data_quality_apply_default_connections" in reports
    assert "套用預設連線" in data_quality
    assert "套用勾選：平台分類" in data_quality
    assert "全部同類型：平台分類" in data_quality
    assert "套用勾選：連線方式" in data_quality
    assert "全部同類型：連線方式" in data_quality
    assert "同類型：草稿流程" in data_quality
    assert "data-quality-checkbox" in data_quality
    assert "data-quality-select-all" in data_quality
    assert "data-quality-bulk-form" in data_quality
    assert "asset_key" in data_quality
    assert 'name="scope" value="selected"' in data_quality
    assert "cmdb_missing_connection" in quality_service
    assert "cmdb_workflow_pending" in quality_service
    assert "can_bulk_platform" in quality_service
    assert "can_bulk_connection" in quality_service
    assert "keys=selected_keys" in reports
    assert "host_type_source" in host_service
    assert '"rhle"' in host_service
    assert '"redhat"' in host_service
    assert '"ubantu"' in host_service
    assert "url_for('api_reports.data_quality_page')" in hosts
    assert "平台：{{ host_type_labels.get(host.host_type" in hosts
    assert "全部平台分類" in hosts


def test_reports_next_action_to_10330_contracts_exist():
    reports = read("webapp/templates/reports.html")
    css = read("webapp/static/css/cathay.css")
    service = read("webapp/services/system_service.py")
    changelog = read("CHANGELOG.md")

    assert "reports-next-action-entry" in changelog
    assert "下一步要做什麼" in reports
    assert "report-next-actions" in reports
    assert "前往資料品質工作台" in reports
    assert "前往帳號盤點" in reports
    assert "前往核心影響圖" in reports
    assert "安裝驗證" in reports
    assert ".report-action-card" in css
    assert "1.0.3.30" in service
    assert "reports-next-action-entry" in changelog
    assert "reports-next-action-entry" in read("docs/release_notes/v1.0.3.30.md")


def test_api_key_post_install_to_10331_contracts_exist():
    config = read("webapp/config.py")
    api_v1 = read("webapp/routes/api_v1.py")
    script = read("scripts/post_install_verify.sh")
    post_install = read("webapp/templates/post_install_report.html")
    tokens = read("webapp/templates/tokens.html")
    service = read("webapp/services/system_service.py")
    changelog = read("CHANGELOG.md")

    assert "api-key-post-install-verify" in changelog
    assert '"/api/v1/post-install/verify"' in api_v1
    assert '@require_api_scope("system:read")' in api_v1
    assert "API_TOKEN" in script
    assert "api_key_verify" in script
    assert "system:read" in post_install
    assert "system:read" in tokens
    assert "1.0.3.31" in service
    assert "api-key-post-install-verify" in changelog
    assert "api-key-post-install-verify" in read("docs/release_notes/v1.0.3.31.md")


def test_api_key_verify_visibility_to_10332_contracts_exist():
    config = read("webapp/config.py")
    api_v1 = read("webapp/routes/api_v1.py")
    post_install = read("webapp/templates/post_install_report.html")
    css = read("webapp/static/css/cathay.css")
    service = read("webapp/services/system_service.py")
    changelog = read("CHANGELOG.md")
    reports = read("webapp/routes/api_reports.py")
    data_quality = read("webapp/templates/data_quality.html")

    assert 'VERSION = "1.0.3.86"' in config
    assert "opening-check-readiness-workflow" in config
    assert "data_quality_retire_selected_assets" in reports
    assert "data-quality-bulk-form=\"retire\"" in data_quality
    assert "can_bulk_retire" in read("webapp/services/quality_service.py")


    assert "verification_source" in api_v1
    assert "verification_label" in api_v1
    assert "required_scope" in api_v1
    assert "API Key 驗證" in post_install
    assert "Script 檢查" in post_install
    assert "verification_source=api_key" in post_install
    assert "/api/v1/post-install/verify" in post_install
    assert "verify-mode-grid" in post_install
    assert ".verify-mode-card" in css
    assert ".verify-badge.api" in css
    assert ".verify-badge.script" in css
    assert "1.0.3.42" in service
    assert "ai-judgement-gold-frame-ui" in changelog
    assert "host-draft-save-error-guard" in changelog
    assert "host-data-dir-permission-guard" in changelog
    assert "ai-judgement-gold-frame-ui" in read("docs/release_notes/v1.0.3.37.md")
    assert "Shell 負責採證" in read("docs/20260527/v1.0.3.36_ai-judgement-source-ux-design.md")
    assert "AI 判斷來源與 Fallback 設計" in read("docs/20260527/v1.0.3.36_webitgpt-system-architecture-slides.html")
    assert "verify-mode-card ai-judgement" in post_install
    assert "AI 判斷金框" in read("webapp/templates/inspections.html")
    assert ".verify-badge.ai" in css
    assert ".l3-panel.l3-ai-ready" in css


def test_cmdb_import_infers_linux_platform_from_os_text():
    from webapp.services import cmdb_workbook_service, csv_service

    bootstrap = read("scripts/bootstrap.py")

    assert cmdb_workbook_service._infer_host_type({"os": "CentOS 4.6 1810"}) == "linux"
    assert cmdb_workbook_service._infer_host_type({"os": "RHLE 8.10"}) == "linux"
    assert cmdb_workbook_service._infer_host_type({"os": "Ubuntu 22.04"}) == "linux"
    assert "repair_imported_platform_classification" in bootstrap
    assert "bulk_apply_platform_suggestions" in bootstrap
    assert "repair_imported_connection_defaults" in bootstrap
    assert "bulk_apply_default_connections" in bootstrap

    csv_doc = csv_service._apply_cmdb_defaults({"os": "CentOS 7.6 1810", "host_type": "end_device"})
    assert csv_doc["host_type"] == "linux"
    assert csv_doc["host_type_source"] == "import_os_inference_rule"
    assert csv_doc["connection"] == "ssh"
    assert csv_doc["connection_source"] == "platform_default_rule"


def test_platform_default_connection_rules():
    from webapp.services import cmdb_workbook_service, csv_service, host_service

    assert host_service.default_connection_for_host_type("linux") == "ssh"
    assert host_service.default_connection_for_host_type("windows") == "winrm"
    assert host_service.default_connection_for_host_type("aix") == "ssh_raw"
    assert host_service.default_connection_for_host_type("as400") == "ssh_raw"
    assert host_service.infer_host_type_from_os("IBM i 7.4") == "as400"
    assert host_service.infer_host_type_from_os("IBMi V7R4") == "as400"

    aix_doc = cmdb_workbook_service._host_doc_from_hardware(
        {
            "asset_seq": "HW-00000001",
            "asset_name": "unit-test",
            "hostname": "unit-test",
            "ip": "127.0.0.1",
            "os": "AIX 7.3",
        },
        user="pytest",
    )
    assert aix_doc["host_type"] == "aix"
    assert aix_doc["connection"] == "ssh_raw"

    as400_doc = cmdb_workbook_service._host_doc_from_hardware(
        {
            "asset_seq": "HW-00000002",
            "asset_name": "unit-test-as400",
            "hostname": "unit-test-as400",
            "ip": "127.0.0.2",
            "os": "IBM i 7.4",
        },
        user="pytest",
    )
    assert as400_doc["host_type"] == "as400"
    assert as400_doc["connection"] == "ssh_raw"

    win_doc = csv_service._apply_cmdb_defaults({"os": "Windows Server 2019", "host_type": ""})
    assert win_doc["host_type"] == "windows"
    assert win_doc["connection"] == "winrm"


def test_patch_installer_defaults_to_offline_pip():
    install_script = read("scripts/install.sh")
    changelog = read("CHANGELOG.md")
    release_note = read("docs/release_notes/v1.0.3.58.md")

    assert 'WEBITGPT_PIP_MODE="${WEBITGPT_PIP_MODE:-offline}"' in install_script
    assert "pip install --upgrade pip" in install_script
    assert 'if [ "$WEBITGPT_PIP_MODE" = "online" ]' in install_script
    assert "--no-index" in install_script
    assert "WEBITGPT_PIP_MODE=skip" in release_note
    assert "offline-pip-patch-install" in changelog


def test_global_judgement_source_visibility_contracts_exist():
    css = read("webapp/static/css/cathay.css")
    config = read("webapp/config.py")
    changelog = read("CHANGELOG.md")
    dashboard = read("webapp/templates/dashboard.html")
    accounts = read("webapp/templates/accounts_inventory.html")
    nmon = read("webapp/templates/nmon.html")
    dependencies = read("webapp/templates/dependencies.html")

    assert "opening-check-readiness-workflow" in config
    assert "static-asset-cache-busting" in changelog
    assert "ai-judgement-visual-contrast" in changelog
    assert "global-judgement-source-visibility" in changelog
    assert "v1.0.3.38" in changelog
    assert "judgement-source-legend" not in dashboard
    assert "judgement-source-panel" not in accounts
    assert "judgement-source-path" not in accounts
    assert "judgement-source-legend" not in nmon
    assert "judgement-source-legend" not in dependencies
    assert "judgement-source-legend" in read("webapp/templates/reports.html")
    assert "judgement-source-legend" in read("webapp/templates/data_quality.html")
    assert "judgement-source-legend asset-helper-panel" in read("webapp/templates/host_new.html")
    for token in [
        ".judgement-source-legend",
        ".source-badge.ai",
        ".source-badge.hybrid",
        ".source-badge.nmon",
        ".source-badge.cmdb",
        ".source-badge.fallback",
        ".source-badge.insufficient",
    ]:
        assert token in css
    assert "AI ???? Script ??" not in dashboard

def test_ai_judgement_visual_contrast_cards_exist():
    accounts = read("webapp/templates/accounts_inventory.html")
    ai_settings = read("webapp/templates/ai_settings.html")
    token_costs = read("webapp/templates/token_costs.html")
    css = read("webapp/static/css/cathay.css")
    changelog = read("CHANGELOG.md")

    assert "ai-judgement-visual-contrast" in changelog
    assert "judgement-source-panel" not in accounts
    assert "judgement-source-path" not in accounts
    assert "Shell / Script ??" not in accounts
    assert "L3 ??? AI ????" not in accounts
    assert "judgement-source-panel" in ai_settings
    assert "judgement-source-card ai-ready" in ai_settings
    assert "judgement-source-panel" in token_costs
    assert "AI KEY" in token_costs
    for token in [
        ".judgement-source-panel",
        ".judgement-source-card.ai",
        ".judgement-source-card.ai-ready",
        ".judgement-source-card.script",
        ".judgement-source-card.data",
        ".judgement-source-card.fallback",
        ".judgement-source-path",
        ".compact-note",
        ".source-badge.ai-ready",
    ]:
        assert token in css
    assert "ai-ready-pale-gold-contrast" in changelog

def test_ai_ready_uses_pale_gold_not_deep_ai_style():
    css = read("webapp/static/css/cathay.css")
    post_install = read("webapp/templates/post_install_report.html")
    inspections = read("webapp/templates/inspections.html")

    assert ".source-badge.ai-ready" in css
    assert ".judgement-source-card.ai-ready" in css
    assert "judgement-source-card ai-ready" not in read("webapp/templates/accounts_inventory.html")
    assert "verify-mode-card ai-judgement" in post_install
    assert "l3-panel l3-ai-ready" in inspections


def test_static_assets_use_version_cache_busting():
    base = read("webapp/templates/base.html")
    app = read("webapp/app.py")
    accounts = read("webapp/templates/accounts_inventory.html")

    assert "asset_version" in app
    assert "css/cathay.css', v=asset_version" in base
    assert "js/ui_tools.js', v=asset_version" in base
    assert "js/table_sort.js', v=asset_version" in base
    assert "js/account_inventory.js', v=asset_version" in accounts
    assert "static-asset-cache-busting" in read("CHANGELOG.md")


def test_rhel96_offline_prereq_installer_guards_core_packages():
    install_prereqs = read("scripts/install_prereqs_offline.sh")
    prereq_builder = read("scripts/prepare_offline_prereq_bundle.sh")
    full_builder = read("scripts/prepare_221_full_offline_bundle.sh")
    one_key = read("docs/one_key_install.md")
    prereq_doc = read("docs/offline_prereq_bundle.md")

    assert 'RPM_INSTALL_MODE="${RPM_INSTALL_MODE:-missing}"' in install_prereqs
    assert "PROTECTED_RPM_RE" in install_prereqs
    assert "systemd|systemd-libs" in install_prereqs
    assert "SKIP protected package from offline bundle" in install_prereqs
    assert "SKIP already installed package" in install_prereqs
    assert "--disablerepo=*" in install_prereqs
    assert "webitgpt_prereqs_${TARGET_OS_SLUG}_${STAMP}" in prereq_builder
    assert "TARGET_OS_SLUG" in prereq_builder
    assert "webitgpt_prereqs_*.tar.gz" in full_builder
    assert "webitgpt_prereqs_<target-os>_<時間>.tar.gz" in one_key
    assert "webitgpt_prereqs_<target-os>_<時間>.tar.gz" in prereq_doc


def test_account_checkboxes_use_inline_left_layout():
    html = read("webapp/templates/accounts_inventory.html")
    css = read("webapp/static/css/cathay.css")

    assert "checkbox-line account-system-toggle" in html
    assert html.count('class="toggle-label checkbox-line"') >= 2
    assert ".checkbox-line" in css
    assert 'input[type="checkbox"]' in css
    assert "inline-size: 16px" in css
    assert ".account-filter-compact label.checkbox-line" in css
    assert ".account-drawer-panel label.checkbox-line" in css
    assert "flex-direction: row" in css


def test_account_risk_badge_stays_on_one_line():
    css = read("webapp/static/css/cathay.css")

    assert ".account-ledger-table .col-risk { width: 180px; min-width: 180px; white-space: nowrap; }" in css
    assert ".account-ledger-table .col-risk .badge-warn" in css
    assert "word-break: keep-all" in css
    assert "width: max-content" in css


def test_global_pam_governance_is_not_hidden_by_host_note(monkeypatch):
    from webapp.services import inventory_service

    def fake_latest_inventory(kind, limit=200):
        return {
            "items": [
                {
                    "asset_seq": "HW-1",
                    "hostname": "app1",
                    "host_type": "linux",
                    "department": "IT",
                    "items": [{"name": "root", "can_login": True, "privileged": True, "risk": "高權限"}],
                }
            ]
        }

    def fake_hosts(limit=100):
        return [{"asset_seq": "HW-1", "hostname": "app1", "host_type": "linux", "department": "IT"}]

    monkeypatch.setattr(inventory_service, "latest_inventory", fake_latest_inventory)
    monkeypatch.setattr(inventory_service, "_hosts", fake_hosts)
    monkeypatch.setattr(
        inventory_service,
        "_load_account_governance",
        lambda: {
            "*:linux:root": {"scope": "platform_account", "owner": "PAM Team", "pam_managed": True, "usage_note": "PAM 納管"},
            "app1:root": {"scope": "host_account", "owner": "", "pam_managed": False, "usage_note": ""},
        },
    )
    monkeypatch.setattr(inventory_service, "inventory_history", lambda kind, limit=10: {"latest": None, "diff": None, "runs": []})

    view = inventory_service.account_inventory_view({"include_system_defaults": "1"})

    assert view["items"][0]["pam_managed"] is True
    assert view["items"][0]["account_owner"] == "PAM Team"
    assert view["items"][0]["usage_note"] == "PAM 納管"


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
    assert "l3-ai-ready" in html
    assert "AI + Script" in html
    assert "Script 接手" in html
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
    assert "開始巡檢目前範圍" in html
    assert '"platform":"{{ diagnostics.platform }}"' in html
    assert "全部系統" in html
    assert "搜尋資產名稱 / 系統名稱" in html
    assert "data-opening-system-search" in html
    assert "data-opening-system-select" in html
    assert "diagnostics.all_systems_value" in html
    assert "diagnostics.all_systems_count" in html
    assert "diagnostics.selected_system_label" in html
    assert "diagnostics.readiness_summary" in html
    assert "diagnostics.system_groups" in html
    assert "系統巡檢分組" in html
    assert "已巡檢主機" in html
    assert "可巡檢未執行" in html
    assert '"limit":500' in html
    assert "host.readiness.label" in html
    assert "host.readiness.next_action" in html
    assert "system=diagnostics.all_systems_value" in html
    assert 'host.host_type in ["linux", "aix"]' in html
    assert "data-l3-filter" in html
    assert "data-l3-verdict" in html
    assert "data-score-ring" in html
    assert "data-score=\"{{ host.summary.score if host.summary else 0 }}\"" in html
    assert "{{ host.asset_name or host.system_name or host.hostname }}" in html
    assert "{{ host.hostname or \"-\" }} / {{ host.ip or \"-\" }} / {{ host.os or host.host_type }}" in html
    assert "{{ host.asset_seq }} / {{ host.ip or \"-\" }} / {{ host.host_type }}" not in html
    assert "conic-gradient" in read("webapp/static/css/cathay.css")
    assert "refreshScoreRings" in read("webapp/static/js/admin_tools.js")
    assert "api_superadmin.log_exceptions_page" in html
    assert "aspect-helper-link" in html
    assert ".aspect-helper-link" in read("webapp/static/css/cathay.css")
    assert "[data-l3-filter]" in read("webapp/static/js/admin_tools.js")
    assert "[data-opening-system-search]" in read("webapp/static/js/admin_tools.js")
    assert "webitgpt.opening.lastSystem" in read("webapp/static/js/admin_tools.js")
    assert "applyLastOpeningSystem" in read("webapp/static/js/admin_tools.js")
    assert "form.requestSubmit()" in read("webapp/static/js/admin_tools.js")
    assert 'option.value === "__all__"' in read("webapp/static/js/admin_tools.js")
    assert "daily_diagnostics(platform, system_name)" in routes
    assert "platform=str(payload.get(\"platform\") or \"\")" in routes
    assert "), 500)" in routes
    assert "OPENING_DEFAULT_SYSTEM" in legacy
    assert "OPENING_ALL_SYSTEMS_VALUE" in legacy
    assert "platform_hosts = [host for host in all_hosts if host.get(\"host_type\") == platform]" in legacy
    assert "_with_host_display_fields" in legacy
    assert "_inspection_result_to_diagnostic_row" in legacy
    assert "_system_readiness_groups" in legacy
    assert "inspection_results" in legacy
    assert "account_for_tier('L1', 'sysinfra')" in legacy
    assert "if requested == OPENING_ALL_SYSTEMS_VALUE:" in legacy
    assert '"all_systems_count": sum(item["count"] for item in options)' in legacy
    assert '"readiness_summary": readiness_summary' in legacy
    assert "selected_system" in legacy
    assert "AIX_COMMANDS" in deep
    assert 'host.get("host_type") not in {"linux", "aix"}' in deep


def test_opening_check_defaults_to_all_systems_after_import():
    from webapp.services.legacy_parity_service import OPENING_ALL_SYSTEMS_VALUE, _selected_system

    options = [{"name": "A system", "count": 1}, {"name": "Z system", "count": 2}]

    assert _selected_system("", options) == ""
    assert _selected_system(OPENING_ALL_SYSTEMS_VALUE, options) == ""
    assert _selected_system("Z system", options) == "Z system"
    assert _selected_system("missing", options) == ""


def test_asset_management_defaults_to_100_rows_per_page():
    routes = read("webapp/routes/api_hosts.py")
    html = read("webapp/templates/hosts.html")

    assert 'request.args.get("page_size", "100")' in routes
    assert 'request.form.get("page_size", "100")' in routes
    assert 'data = {"items": [], "total": 0, "page": 1, "page_size": 100' in routes
    assert "data.get('page_size', 100)" in html


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
