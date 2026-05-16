from __future__ import annotations

import argparse
import csv
import io
import json
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any, Optional


def request(
    opener: urllib.request.OpenerDirector,
    method: str,
    url: str,
    *,
    data: Optional[dict[str, Any]] = None,
    form: Optional[dict[str, str]] = None,
    headers: Optional[dict[str, str]] = None,
    timeout: int = 10,
) -> tuple[int, str, Any]:
    headers = {**(headers or {})}
    body: Optional[bytes] = None
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif form is not None:
        body = urllib.parse.urlencode(form, doseq=True).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with opener.open(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            return resp.status, text, parse_json(text)
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        return exc.code, text, parse_json(text)
    except urllib.error.URLError as exc:
        return 0, str(exc), None


def parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def check(report: list[dict[str, Any]], name: str, ok: bool, detail: Any = None) -> None:
    report.append({"name": name, "ok": bool(ok), "detail": detail})


def build_host(asset_seq: str) -> dict[str, Any]:
    return {
        "division": "IT",
        "department": "Operations",
        "asset_seq": asset_seq,
        "status": "active",
        "group_name": "H4",
        "asset_name": "Functional validation host",
        "device_type": "VM",
        "quantity": 1,
        "owner": "IT",
        "environment": "DEV",
        "hostname": f"func-{asset_seq.lower()}",
        "os": "Debian 13",
        "ip": "192.168.1.221",
        "custodian": "functional-validation",
        "user_unit": "IT",
        "company": "example-corp",
        "integrity": 1,
        "confidentiality": 2,
        "availability": 1,
        "host_type": "linux",
        "dc": "dunan",
        "connection": "local",
        "ssh_user": "sysinfra",
        "ssh_port": 22,
        "tier": "medium",
        "system_name": "webitgpt validation",
        "ap_owner": "functional-validation",
    }


def build_csv(asset_seq: str) -> str:
    host = build_host(asset_seq)
    output = io.StringIO()
    headers = [
        "division",
        "department",
        "asset_seq",
        "status",
        "group_name",
        "asset_name",
        "device_type",
        "quantity",
        "owner",
        "environment",
        "hostname",
        "os",
        "ip",
        "custodian",
        "user_unit",
        "company",
        "integrity",
        "confidentiality",
        "availability",
        "host_type",
        "dc",
        "connection",
        "ssh_user",
        "ssh_port",
        "tier",
        "ap_owner",
        "system_name",
        "os_group",
    ]
    writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    writer.writerow(host)
    return output.getvalue()


def cleanup_validation_records(asset_seqs: list[str], view_name: str) -> None:
    try:
        from pymongo import MongoClient  # type: ignore
    except Exception:
        return

    try:
        client = MongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=1000)
        db = client["webitgpt"]
        client.admin.command("ping")
    except Exception:
        return

    collections = [
        "hosts",
        "inspection_results",
        "nmon_data",
        "compliance_findings",
        "inventory_snapshots",
        "inventory_runs",
        "account_inventory",
        "software_inventory",
        "services_inventory",
        "ssh_keys_inventory",
    ]
    for collection_name in collections:
        db[collection_name].delete_many({"asset_seq": {"$in": asset_seqs}})
    db.users.delete_many({"username": "validation-viewer"})
    db.saved_views.delete_many({"name": view_name})
    db.saved_views.delete_many({"name": {"$regex": "^validation-"}})

    host_root = Path("/opt/webitgpt/data/hosts")
    for asset_seq in asset_seqs:
        path = host_root / asset_seq
        if path.exists():
            import shutil

            shutil.rmtree(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run webitgpt v1.0 functional validation.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8002")
    parser.add_argument("--username", default="superadmin")
    parser.add_argument("--password", default="1qaz@WSX")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    report: list[dict[str, Any]] = []

    status, _, health = request(opener, "GET", f"{base}/health")
    check(report, "health", status == 200 and health and health.get("status") == "ok", health)

    status, _, ready = request(opener, "GET", f"{base}/ready")
    check(report, "ready_mongo", status == 200 and ready and ready.get("mongo") == "ok", ready)

    status, text, _ = request(opener, "GET", f"{base}/metrics")
    check(report, "metrics_hosts_total", status == 200 and "webitgpt_hosts_total" in text, text[:200])

    status, _, _ = request(opener, "POST", f"{base}/login", form={"username": args.username, "password": args.password})
    check(report, "login_superadmin", status in {200, 302}, {"status": status})

    status, mfa_page, _ = request(opener, "GET", f"{base}/account/mfa")
    check(report, "otp_disabled_page_loads", status == 200 and "OTP / MFA 驗證目前已停用" in mfa_page and "otpauth://" not in mfa_page, {"status": status})

    status, superadmin_page, _ = request(opener, "GET", f"{base}/superadmin")
    check(report, "superadmin_features_audit_page", status == 200 and "Hash chain：正常" in superadmin_page and "cmdb_saved_views" in superadmin_page, {"status": status})

    page_checks = [
        ("/superadmin/users", "users_page_loads", "使用者與權限"),
        ("/superadmin/system-health", "system_health_page_loads", "健康檢查"),
        ("/superadmin/log-exceptions", "log_exceptions_page_loads", "系統日誌白名單"),
        ("/superadmin/asset-governance-statuses", "asset_governance_statuses_page_loads", "等待 PAM 納管"),
        ("/superadmin/backup-dr", "backup_dr_page_loads", "備份 / DR"),
        ("/superadmin/patches", "patches_page_loads", "Patch / 回滾"),
        ("/superadmin/ai", "ai_provider_page_loads", "AI 供應商"),
        ("/security_audit", "security_audit_page_loads", "安全稽核"),
        ("/housekeeping", "housekeeping_page_loads", "Housekeeping"),
        ("/notifications", "notifications_page_loads", "通知"),
        ("/reports", "reports_page_loads", "統計報表"),
        ("/dependencies", "dependencies_page_loads", "系統拓撲"),
        ("/platforms", "platforms_page_loads", "平台支援"),
        ("/vmware", "vmware_page_loads", "VMware"),
        ("/nmon", "nmon_page_loads", "NMON"),
        ("/inspections", "inspections_page_loads", "開門檢查"),
        ("/accounts", "accounts_inventory_page", "帳號盤點"),
        ("/software", "software_inventory_page", "軟體盤點"),
        ("/services", "services_management_page", "服務管理"),
        ("/ssh-keys", "ssh_key_management_page", "SSH Key"),
        ("/changes", "change_management_page", "變更管理"),
    ]
    for path, name, marker in page_checks:
        status, page_text, _ = request(opener, "GET", f"{base}{path}")
        check(report, name, status == 200 and marker in page_text, {"status": status})

    status, _, feature_update = request(opener, "POST", f"{base}/api/superadmin/features/cmdb_saved_views", data={"enabled": True})
    check(report, "feature_flag_update_api", status == 200 and feature_update and feature_update.get("enabled") is True, feature_update)

    status, _, vmware_flag = request(opener, "POST", f"{base}/api/superadmin/features/host_type_vmware", data={"enabled": True})
    check(report, "vmware_feature_flag_enable", status == 200 and vmware_flag and vmware_flag.get("enabled") is True, vmware_flag)

    status, _, ai_settings = request(
        opener,
        "POST",
        f"{base}/api/ai/settings",
        data={"provider": "ollama", "base_url": "http://127.0.0.1:11434", "model": "phase1-review", "api_key": "functional-secret", "enabled": False},
    )
    check(report, "ai_provider_settings_api", status == 200 and ai_settings and ai_settings.get("api_key") == "***MASKED***", ai_settings)

    status, _, user_created = request(
        opener,
        "POST",
        f"{base}/api/superadmin/users",
        data={"username": "validation-viewer", "role": "viewer", "email": "validation@example.local", "display_name": "Validation Viewer", "password": "change-me-too"},
    )
    check(report, "user_create_api", status == 200 and user_created and user_created.get("username") == "validation-viewer", user_created)

    status, _, lock_result = request(opener, "POST", f"{base}/api/superadmin/users/validation-viewer/lock", data={"locked": True})
    check(report, "user_lock_api", status == 200 and lock_result and lock_result.get("locked") is True, lock_result)

    status, _, unlock_result = request(opener, "POST", f"{base}/api/superadmin/users/validation-viewer/lock", data={"locked": False})
    check(report, "user_unlock_api", status == 200 and unlock_result and unlock_result.get("locked") is False, unlock_result)

    status, _, reset_result = request(opener, "POST", f"{base}/api/superadmin/users/validation-viewer/reset-password")
    check(report, "user_reset_password_api", status == 200 and reset_result and reset_result.get("temporary_password", "").startswith("Reset-"), {"status": status})

    status, _, token_result = request(opener, "POST", f"{base}/api/superadmin/token", data={"name": "functional-validation", "scopes": ["hosts:read"]})
    token = (token_result or {}).get("token", "")
    check(report, "api_token_issue", status == 200 and token.startswith("wgpt_"), {"status": status})

    status, _, mcp_token_result = request(opener, "POST", f"{base}/api/superadmin/token", data={"name": "functional-validation-mcp", "scopes": ["mcp:read"]})
    mcp_token = (mcp_token_result or {}).get("token", "")
    check(report, "mcp_token_issue", status == 200 and mcp_token.startswith("wgpt_"), {"status": status})

    status, token_page, _ = request(opener, "GET", f"{base}/superadmin/tokens")
    check(report, "token_page_loads", status == 200 and "API Token" in token_page, {"status": status})

    status, token_form_page, _ = request(opener, "POST", f"{base}/superadmin/tokens", form={"name": "functional-validation-ui", "scopes": "hosts:read"})
    check(report, "token_page_issue", status == 200 and "wgpt_" in token_form_page, {"status": status})

    status, _, unauthorized = request(opener, "GET", f"{base}/api/v1/hosts")
    check(report, "api_v1_requires_token", status == 401, unauthorized)

    auth_headers = {"Authorization": f"Bearer {token}"}
    status, _, hosts_before = request(opener, "GET", f"{base}/api/v1/hosts", headers=auth_headers)
    before_total = int((hosts_before or {}).get("total", 0))
    check(report, "api_v1_hosts_before", status == 200 and before_total >= 3, {"total": before_total})

    status, home_page, _ = request(opener, "GET", f"{base}/hosts")
    check(report, "ui_version_visible", status == 200 and "webitgpt v1.0.2.45" in home_page and "sortable-data-tables" in home_page and "IT 巡檢系統" in home_page, {"status": status})
    check(report, "ui_asset_nav_active", status == 200 and 'class="nav-warn active"' in home_page and "▣ 資產管理" in home_page, {"status": status})
    status, quality_page, _ = request(opener, "GET", f"{base}/hosts/quality")
    check(report, "asset_quality_page_loads", status == 200 and "資產異常清單" in quality_page and "納管資產" in quality_page, {"status": status})
    status, search_page, _ = request(opener, "GET", f"{base}/search?q={urllib.parse.quote('資產治理狀態')}")
    check(report, "global_search_asset_governance_route", status == 200 and "資產治理狀態" in search_page and "等待 PAM 納管" in search_page, {"status": status})
    status, search_page, _ = request(opener, "GET", f"{base}/search?q={urllib.parse.quote('開發後台')}")
    check(report, "global_search_dev_console_route", status == 200 and "開發後台" in search_page and "模組管理" in search_page, {"status": status})
    status, search_page, _ = request(opener, "GET", f"{base}/search?q={urllib.parse.quote('IPAM')}")
    check(report, "global_search_ipam_route", status == 200 and "網段" in search_page and "帳號盤點工作台" not in search_page, {"status": status})
    status, search_page, _ = request(opener, "GET", f"{base}/search?q={urllib.parse.quote('A.')}")
    check(report, "global_search_a_shortcut_route", status == 200 and "儀表板" in search_page, {"status": status})
    status, search_page, _ = request(opener, "GET", f"{base}/search?q={urllib.parse.quote('B.')}")
    check(report, "global_search_b_shortcut_route", status == 200 and "資產管理" in search_page, {"status": status})
    status, search_page, _ = request(opener, "GET", f"{base}/search?q={urllib.parse.quote('SA.A')}")
    check(report, "global_search_sa_a_shortcut_route", status == 200 and "系統管理" in search_page and "功能開關" in search_page, {"status": status})
    status, search_page, _ = request(opener, "GET", f"{base}/search?q={urllib.parse.quote('SA.H')}")
    check(report, "global_search_sa_h_shortcut_route", status == 200 and "工作排程" in search_page, {"status": status})
    status, search_page, _ = request(opener, "GET", f"{base}/search?q={urllib.parse.quote('日')}")
    check(report, "global_search_single_char_log_route", status == 200 and "搜尋結果" in search_page and "日誌檢視" in search_page and "系統日誌白名單" in search_page, {"status": status})

    view_name = f"validation-{random.randint(1000, 9999)}"
    status, _, saved_view = request(
        opener,
        "POST",
        f"{base}/api/hosts/saved-views",
        data={"name": view_name, "params": {"environment": "DEV", "host_type": "linux", "page_size": "10"}},
    )
    check(report, "saved_view_create", status == 201 and saved_view and saved_view.get("name") == view_name, saved_view)

    status, hosts_page, _ = request(opener, "GET", f"{base}/hosts?environment=DEV&host_type=linux&page_size=10")
    check(report, "hosts_page_filters_saved_views", status == 200 and view_name in hosts_page and "常用篩選" in hosts_page and "全部作業系統/平台" in hosts_page, {"status": status})

    asset_seq = f"HW-{random.randint(99000000, 99999999)}"
    status, _, created = request(opener, "POST", f"{base}/api/hosts", data=build_host(asset_seq))
    check(report, "host_create", status == 201 and created and created.get("asset_seq") == asset_seq, created)

    status, _, updated = request(opener, "PUT", f"{base}/api/hosts/{asset_seq}", data={"note": "functional validation updated"})
    check(report, "host_update", status == 200 and updated and updated.get("note") == "functional validation updated", updated)

    status, _, deleted = request(opener, "DELETE", f"{base}/api/hosts/{asset_seq}")
    check(report, "host_soft_delete", status == 200 and deleted and deleted.get("status") == "deleted", deleted)

    status, _, restored = request(opener, "POST", f"{base}/api/hosts/{asset_seq}/restore")
    check(report, "host_restore", status == 200 and restored and restored.get("status") == "active", restored)

    draft_a = build_host(f"HW-{random.randint(97000000, 97999999)}")
    draft_b = build_host(f"HW-{random.randint(97000000, 97999999)}")
    draft_a.update({"status": "draft", "hostname": f"func-draft-{draft_a['asset_seq'].lower()}", "asset_name": "Functional validation draft"})
    draft_b.update({"status": "draft", "hostname": f"func-draft-{draft_b['asset_seq'].lower()}", "asset_name": "Functional validation draft"})
    status_a, _, created_a = request(opener, "POST", f"{base}/api/hosts", data=draft_a)
    status_b, _, created_b = request(opener, "POST", f"{base}/api/hosts", data=draft_b)
    check(report, "bulk_draft_seed", status_a == 201 and status_b == 201, {"a": created_a, "b": created_b})
    status, bulk_page, _ = request(
        opener,
        "POST",
        f"{base}/hosts/bulk-delete-drafts",
        form={"asset_seq": [draft_a["hostname"], draft_b["hostname"]], "reason": "functional validation bulk delete", "return_status": "draft"},
    )
    post_status = status
    status, _, draft_a_after = request(opener, "GET", f"{base}/api/hosts?q={urllib.parse.quote(draft_a['hostname'])}")
    status_b_after, _, draft_b_after = request(opener, "GET", f"{base}/api/hosts?q={urllib.parse.quote(draft_b['hostname'])}")
    check(
        report,
        "bulk_draft_delete",
        post_status == 200
        and "批次刪除草稿" in bulk_page
        and "刪除 2 筆" in bulk_page
        and draft_a_after
        and draft_a_after.get("total") == 0
        and draft_b_after
        and draft_b_after.get("total") == 0,
        {"post_status": post_status, "a": draft_a_after, "b": draft_b_after},
    )

    manual_asset_seq = f"HW-{random.randint(96000000, 96999999)}"
    manual_form = {
        "division": "IT",
        "department": "Operations",
        "status": "active",
        "group_name": "H4",
        "asset_name": "Manual validation host",
        "device_type": "VM",
        "quantity": "1",
        "owner": "IT",
        "environment": "DEV",
        "custodian": "functional-validation",
        "user_unit": "IT",
        "company": "example-corp",
        "integrity": "1",
        "confidentiality": "2",
        "availability": "1",
        "dc": "dunan",
        "rows": f"{manual_asset_seq},manual-{manual_asset_seq.lower()},192.168.1.221,linux,Debian 13,local",
    }
    status, manual_page, _ = request(opener, "POST", f"{base}/hosts/import/manual", form=manual_form)
    check(report, "manual_multi_import", status == 200, {"status": status})

    status, _, self_check = request(opener, "POST", f"{base}/api/host/HW-00000221/self_check")
    check(report, "self_check_seed_host", status == 200 and self_check and self_check.get("status") in {"ok", "warn", "fail"}, self_check)

    status, _, global_self_check = request(opener, "POST", f"{base}/api/self_check/global?limit=2")
    check(report, "global_self_check_limited", status == 200 and global_self_check and global_self_check.get("count") == 2, global_self_check)

    status, _, compliance_eval = request(opener, "POST", f"{base}/api/compliance/evaluate/HW-00000221")
    check(report, "compliance_evaluate_host", status == 200 and compliance_eval and "score" in compliance_eval, compliance_eval)

    status, _, compliance_dashboard = request(opener, "GET", f"{base}/api/compliance/dashboard")
    check(report, "compliance_dashboard_api", status == 200 and compliance_dashboard and compliance_dashboard.get("rules_total", 0) >= 3, compliance_dashboard)

    status, compliance_csv, _ = request(opener, "GET", f"{base}/api/compliance/findings.csv")
    check(report, "compliance_findings_csv", status == 200 and "rule_id" in compliance_csv, compliance_csv[:200])

    status, _, housekeeping_run = request(opener, "POST", f"{base}/api/housekeeping/run/disk_alert", data={"dry_run": True})
    check(report, "housekeeping_run_disk_alert", status == 200 and housekeeping_run and housekeeping_run.get("task") == "disk_alert", housekeeping_run)

    status, _, backup_manifest = request(opener, "POST", f"{base}/api/superadmin/backup/manifest")
    expected_version = (health or {}).get("version")
    check(report, "backup_manifest_api", status == 200 and backup_manifest and backup_manifest.get("version") == expected_version, backup_manifest)

    status, _, dr_result = request(opener, "POST", f"{base}/api/superadmin/dr-drill")
    check(report, "dr_drill_api", status == 200 and dr_result and dr_result.get("status") == "ok", dr_result)

    status, _, rollback = request(opener, "POST", f"{base}/api/superadmin/patches/rollback-plan", data={"target": "latest"})
    check(report, "patch_rollback_plan_api", status == 200 and rollback and rollback.get("mode") == "dry-run", rollback)

    status, _, notification_test = request(opener, "POST", f"{base}/api/notifications/test/email")
    check(report, "notification_test_email", status == 200 and notification_test and notification_test.get("channel") == "email", notification_test)

    status, _, report_summary = request(opener, "GET", f"{base}/api/reports/summary")
    check(report, "reports_summary_api", status == 200 and report_summary and report_summary.get("hosts_total", 0) >= 3, report_summary)

    status, _, vcenter = request(
        opener,
        "POST",
        f"{base}/api/vmware/credentials",
        data={"name": "functional-vcenter", "url": "https://192.168.1.10/sdk", "username": "administrator@vsphere.local", "password": "vmware-secret"},
    )
    check(report, "vmware_credentials_masked", status == 200 and vcenter and vcenter.get("password") == "***MASKED***", vcenter)

    status, _, vmware_inventory = request(opener, "GET", f"{base}/api/vmware/inventory")
    check(report, "vmware_inventory_api", status == 200 and vmware_inventory and "credentials" in vmware_inventory, vmware_inventory)

    status, _, platform_status = request(opener, "GET", f"{base}/api/platforms/status")
    check(report, "platforms_status_api", status == 200 and platform_status and platform_status.get("aix_ready") is True, platform_status)

    status, _, inspection_run = request(opener, "POST", f"{base}/api/inspections/run", data={"limit": 3})
    check(report, "inspection_run_limited", status == 200 and inspection_run and inspection_run.get("count") == 3, inspection_run)

    status, _, inspection_today = request(opener, "GET", f"{base}/api/inspections/today")
    check(report, "inspection_today_api", status == 200 and inspection_today and inspection_today.get("count", 0) >= 3, inspection_today)

    status, _, nmon_status = request(opener, "GET", f"{base}/api/nmon/status")
    check(report, "nmon_status_api", status == 200 and nmon_status and "enabled_count" in nmon_status, nmon_status)

    for kind in ["accounts", "software", "services", "ssh_keys"]:
        status, _, inventory = request(opener, "POST", f"{base}/api/inventory/{kind}/collect", data={"limit": 2})
        check(report, f"inventory_collect_{kind}", status == 200 and inventory and inventory.get("status") in {"ok", "cached"}, inventory)

    status, _, ssh_plan = request(opener, "POST", f"{base}/api/ssh-keys/plan", data={"asset_seq": "HW-00000221"})
    check(report, "ssh_key_plan_api", status == 200 and ssh_plan and ssh_plan.get("mode") == "dry-run", ssh_plan)

    status, _, change_ticket = request(opener, "POST", f"{base}/api/changes", data={"title": "functional change", "target": "/opt/webitgpt", "risk": "low"})
    check(report, "change_ticket_api", status == 200 and change_ticket and change_ticket.get("ticket_id", "").startswith("CHG-"), change_ticket)

    status, _, mcp_manifest = request(opener, "GET", f"{base}/mcp/manifest")
    check(report, "mcp_manifest", status == 200 and mcp_manifest and len(mcp_manifest.get("tools", [])) >= 4, mcp_manifest)

    status, _, mcp_hosts = request(opener, "POST", f"{base}/mcp/tools/list_hosts", headers={"Authorization": f"Bearer {mcp_token}"}, data={"limit": 2})
    check(report, "mcp_tool_list_hosts", status == 200 and mcp_hosts and len(mcp_hosts.get("items", [])) <= 2, {"status": status, "total": (mcp_hosts or {}).get("total")})

    status, _, openapi = request(opener, "GET", f"{base}/api/v1/openapi.json")
    check(report, "openapi_auto_doc", status == 200 and openapi and openapi.get("openapi") == "3.0.0", openapi)

    status, text, debug = request(opener, "POST", f"{base}/api/host/HW-00000221/debug_snapshot")
    check(report, "debug_snapshot_masked", status == 200 and "***IP_MASKED***" in text and debug, text[:300])

    status, _, blocked = request(opener, "POST", f"{base}/api/admin/monitored-write/nmon_deploy")
    check(report, "phase_readonly_blocks_monitored_write", status == 403, blocked)

    status, _, audit = request(opener, "GET", f"{base}/api/superadmin/audit/verify")
    check(report, "audit_chain_verify", status == 200 and audit and audit.get("ok") is True, audit)

    status, _, hosts_after = request(opener, "GET", f"{base}/api/v1/hosts", headers=auth_headers)
    after_total = int((hosts_after or {}).get("total", 0))
    check(report, "api_v1_hosts_after", status == 200 and after_total >= before_total + 1, {"before": before_total, "after": after_total})

    csv_asset_seq = f"HW-{random.randint(98000000, 98999999)}"
    csv_body = build_csv(csv_asset_seq).encode("utf-8")
    req = urllib.request.Request(f"{base}/api/hosts/csv/import", data=csv_body, headers={"Content-Type": "text/csv"}, method="POST")
    try:
        with opener.open(req, timeout=10) as resp:
            csv_import_result = parse_json(resp.read().decode("utf-8", errors="replace"))
            csv_import_status = resp.status
    except urllib.error.HTTPError as exc:
        csv_import_status = exc.code
        csv_import_result = parse_json(exc.read().decode("utf-8", errors="replace"))
    except urllib.error.URLError as exc:
        csv_import_status = 0
        csv_import_result = {"error": str(exc)}
    check(report, "csv_import", csv_import_status == 200 and csv_import_result and csv_import_result.get("created") == 1, csv_import_result)

    json_asset_seq = f"HW-{random.randint(97000000, 97999999)}"
    status, _, json_import_result = request(opener, "POST", f"{base}/api/hosts/json/import", data=build_host(json_asset_seq))
    check(report, "json_import", status == 200 and json_import_result and json_import_result.get("created") == 1, json_import_result)

    status, csv_export_text, _ = request(opener, "GET", f"{base}/api/hosts/csv/export")
    check(report, "csv_export", status == 200 and "asset_seq" in csv_export_text and csv_asset_seq in csv_export_text, csv_export_text[:300])

    host_root = Path("/opt/webitgpt/data/hosts")
    if host_root.exists():
        meta_files = list(host_root.glob("*/meta.json"))
        check(report, "per_host_meta_files", len(meta_files) >= after_total, {"meta_files": len(meta_files), "hosts_total": after_total})
        check(report, "self_check_file_written", any((host_root / "HW-00000221" / "self_check").glob("*.json")), "HW-00000221/self_check")
        check(report, "debug_snapshot_file_written", any((host_root / "HW-00000221" / "debug_snapshots").glob("*.json")), "HW-00000221/debug_snapshots")

    cleanup_validation_records([asset_seq, manual_asset_seq, csv_asset_seq, json_asset_seq], view_name)

    summary = {
        "base_url": base,
        "generated_at_epoch": int(time.time()),
        "passed": sum(1 for item in report if item["ok"]),
        "failed": sum(1 for item in report if not item["ok"]),
        "checks": report,
    }
    output = json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    print(output)
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
