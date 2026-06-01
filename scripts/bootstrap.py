from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from pymongo.errors import OperationFailure
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp import config
from webapp.services.asset_governance_status_service import ensure_default_statuses
from webapp.services.compliance_service import ensure_default_rules
from webapp.services.csv_service import import_csv
from webapp.services.feature_flags import ensure_feature_flags
from webapp.services.host_dir_service import init_dir
from webapp.services.host_service import bulk_apply_platform_suggestions
from webapp.services.mongo_service import get_db


HOST_INDEXES = [
    ("asset_seq", [("asset_seq", 1)], {}),
    ("hostname", [("hostname", 1)], {"unique": True}),
    ("ip", [("ip", 1)], {}),
    ("ip_addresses", [("ip_addresses", 1)], {}),
    ("network_segments", [("network_segments", 1)], {}),
    ("dc_group_name", [("dc", 1), ("group_name", 1)], {}),
    ("environment_status", [("environment", 1), ("status", 1)], {}),
    ("connection_host_type", [("connection", 1), ("host_type", 1)], {}),
    ("compliance_score", [("compliance_score", -1)], {}),
    ("last_self_check_at", [("last_self_check_at", -1)], {}),
]

COLLECTIONS = [
    "hosts",
    "audit_logs",
    "users",
    "feature_flags",
    "saved_views",
    "sessions",
    "settings",
    "compliance_rules",
    "extension_definitions",
    "ipam_networks",
    "ip_reservations",
    "housekeeping_runs",
    "vmware_credentials",
    "api_tokens",
    "edge_agents",
    "compliance_findings",
    "compliance_remediation_plans",
    "notification_channels",
    "notification_events",
    "inspection_results",
    "diagnostic_results",
    "deep_check_jobs",
    "deep_check_reports",
    "accounts_inventory",
    "software_inventory",
    "inventory_runs",
    "inventory_snapshots",
    "software_inventory_changes",
    "services_inventory",
    "ssh_keys_inventory",
    "change_tickets",
    "login_attempts",
    "nmon_data",
    "dependency_systems",
    "dependency_relations",
    "dependency_collect_runs",
    "dependency_reconcile_reports",
    "dependency_ghost_ignored",
    "asset_governance_statuses",
]

BASE_HOST = {
    "division": "資訊管理處",
    "department": "系統運維組",
    "status": "active",
    "group_name": "H4",
    "device_type": "VM",
    "quantity": 1,
    "owner": "資訊管理處",
    "environment": "DEV",
    "custodian": "Alienlee",
    "user_unit": "資訊管理處",
    "company": "example-corp",
    "connection": "ssh",
    "ssh_user": "sysinfra",
    "ssh_port": 22,
    "ssh_key_records": {},
    "nmon_interval_min": 5,
    "tier": "medium",
    "ap_owner": "Alienlee",
    "host_type": "linux",
    "dc": "dunan",
    "edge_id": "edge_dunan",
    "last_self_check_status": "unknown",
    "compliance_score": 0,
    "extensions": {},
    "import_source": "actual_env",
}

ACTUAL_HOSTS = [
    {
        **BASE_HOST,
        "asset_seq": "HW-00000221",
        "asset_name": "巡檢系統主機",
        "device_model": "VMware VM",
        "asset_usage": "Inspection Server",
        "location": "dunan-lab",
        "rack_no": "VM",
        "hostname": "secansible",
        "os": "Debian 13",
        "ip": "192.168.1.221",
        "ip_addresses": ["192.168.1.221"],
        "network_segments": ["192.168.1.0/24"],
        "sys_admin": "sysinfra",
        "user": "lab-admin",
        "note": "實際部署主機，來源為目前 221 環境資料。",
        "connection": "local",
        "nmon_enabled": False,
        "system_name": "webitgpt inspection",
        "os_group": "debian",
        "integrity": 1,
        "confidentiality": 2,
        "availability": 1,
    },
    {
        **BASE_HOST,
        "asset_seq": "HW-00000222",
        "asset_name": "受監控主機-Rocky",
        "hostname": "secclient1",
        "os": "Rocky Linux 9.7",
        "ip": "192.168.1.222",
        "ip_addresses": ["192.168.1.222"],
        "network_segments": ["192.168.1.0/24"],
        "nmon_enabled": True,
        "os_group": "rocky",
        "integrity": 3,
        "confidentiality": 3,
        "availability": 3,
    },
    {
        **BASE_HOST,
        "asset_seq": "HW-00000223",
        "asset_name": "受監控主機-Debian",
        "hostname": "sec9c2",
        "os": "Debian 13",
        "ip": "192.168.1.223",
        "ip_addresses": ["192.168.1.223"],
        "network_segments": ["192.168.1.0/24"],
        "nmon_enabled": False,
        "os_group": "debian",
        "integrity": 3,
        "confidentiality": 3,
        "availability": 3,
    },
]


def _env_enabled(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def ensure_collections() -> None:
    db = get_db()
    existing = set(db.list_collection_names())
    for name in COLLECTIONS:
        if name not in existing:
            db.create_collection(name)


def ensure_indexes() -> None:
    hosts = get_db().hosts
    for index_name in ("asset_seq", "hostname"):
        try:
            hosts.drop_index(index_name)
        except OperationFailure:
            pass
    for name, keys, options in HOST_INDEXES:
        hosts.create_index(keys, name=name, **options)
    get_db().audit_logs.create_index([("seq", 1)], name="seq", unique=True)
    get_db().users.create_index([("username", 1)], name="username", unique=True)
    get_db().feature_flags.create_index([("key", 1)], name="key", unique=True)
    get_db().settings.create_index([("key", 1)], name="key", unique=True)
    get_db().saved_views.create_index([("owner", 1), ("name", 1)], name="owner_name", unique=True)
    get_db().compliance_rules.create_index([("rule_id", 1)], name="rule_id", unique=True)
    get_db().compliance_findings.create_index([("asset_seq", 1), ("rule_id", 1), ("fixed_at", 1)], name="asset_rule_fixed")
    get_db().compliance_remediation_plans.create_index([("plan_id", 1)], name="plan_id", unique=True)
    get_db().compliance_remediation_plans.create_index([("asset_seq", 1), ("created_at", -1)], name="asset_created")
    get_db().housekeeping_runs.create_index([("task", 1), ("started_at", -1)], name="task_started")
    get_db().inspection_results.create_index([("asset_seq", 1), ("run_at", -1)], name="asset_run")
    get_db().diagnostic_results.create_index([("asset_seq", 1), ("checked_at", -1)], name="asset_checked")
    get_db().deep_check_jobs.create_index([("job_id", 1)], name="job_id", unique=True)
    get_db().deep_check_jobs.create_index([("hostname", 1), ("started_at", -1)], name="hostname_started")
    get_db().deep_check_reports.create_index([("hostname", 1), ("timestamp", -1)], name="hostname_timestamp")
    get_db().deep_check_reports.create_index([("filename", 1)], name="filename", unique=True)
    get_db().inventory_runs.create_index([("kind", 1), ("started_at", -1)], name="kind_started")
    get_db().inventory_runs.create_index([("run_id", 1)], name="run_id", unique=True)
    get_db().inventory_snapshots.create_index([("kind", 1), ("run_id", 1), ("asset_seq", 1)], name="kind_run_asset")
    get_db().software_inventory_changes.create_index([("asset_seq", 1), ("created_at", -1)], name="asset_created")
    get_db().ipam_networks.create_index([("cidr", 1)], name="cidr", unique=True)
    get_db().network_scan_reports.create_index([("cidr", 1), ("started_at", -1)], name="cidr_started")
    get_db().ip_reservations.create_index([("ip", 1), ("status", 1)], name="ip_status")
    get_db().extension_definitions.create_index([("key", 1)], name="key", unique=True)
    get_db().dependency_systems.create_index([("system_id", 1)], name="system_id", unique=True)
    get_db().dependency_systems.create_index([("tier", 1), ("category", 1)], name="tier_category")
    get_db().dependency_systems.create_index([("external", 1)], name="external")
    get_db().dependency_systems.create_index([("host_refs", 1)], name="host_refs")
    get_db().dependency_relations.create_index([("from_system", 1), ("to_system", 1)], name="from_to", unique=True)
    get_db().dependency_relations.create_index([("source", 1)], name="source")
    get_db().dependency_relations.create_index([("evidence.last_seen_at", -1)], name="evidence_last_seen")
    get_db().dependency_collect_runs.create_index([("run_id", 1)], name="run_id", unique=True)
    get_db().dependency_collect_runs.create_index([("started_at", -1)], name="started_at")
    get_db().dependency_reconcile_reports.create_index([("run_id", 1)], name="run_id", unique=True)
    get_db().dependency_reconcile_reports.create_index([("started_at", -1)], name="started_at")
    get_db().dependency_reconcile_reports.create_index([("ss_run_id", 1)], name="ss_run_id")
    get_db().dependency_ghost_ignored.create_index([("ip", 1)], name="ip", unique=True)


def seed_hosts() -> int:
    if not _env_enabled("WEBITGPT_SEED_DEMO_HOSTS", True):
        return 0
    hosts = get_db().hosts
    now = datetime.now(timezone.utc)
    inserted = 0
    for host in ACTUAL_HOSTS:
        doc = {
            **host,
            "created_at": now,
            "updated_at": now,
            "created_by": "bootstrap",
            "updated_by": "bootstrap",
            "imported_at": now,
        }
        result = hosts.update_one({"hostname": host["hostname"]}, {"$setOnInsert": doc}, upsert=True)
        if result.upserted_id:
            inserted += 1
    for host in ACTUAL_HOSTS:
        hosts.update_one(
            {"hostname": host["hostname"]},
            {
                "$set": {
                    "asset_name": host["asset_name"],
                    "division": host.get("division"),
                    "department": host.get("department"),
                    "status": host.get("status"),
                    "group_name": host.get("group_name"),
                    "device_type": host.get("device_type"),
                    "quantity": host.get("quantity"),
                    "owner": host.get("owner"),
                    "environment": host.get("environment"),
                    "hostname": host["hostname"],
                    "host_type": host.get("host_type"),
                    "dc": host.get("dc"),
                    "ip": host["ip"],
                    "ip_addresses": host.get("ip_addresses", [host["ip"]]),
                    "network_segments": host.get("network_segments", []),
                    "custodian": host.get("custodian"),
                    "user_unit": host.get("user_unit"),
                    "company": host.get("company"),
                    "connection": host.get("connection"),
                    "ssh_user": host.get("ssh_user"),
                    "ssh_port": host.get("ssh_port"),
                    "os": host.get("os"),
                    "os_group": host.get("os_group"),
                    "integrity": host.get("integrity"),
                    "confidentiality": host.get("confidentiality"),
                    "availability": host.get("availability"),
                    "import_source": "actual_env",
                    "note": host.get("note", ""),
                    "updated_at": now,
                    "updated_by": "bootstrap",
                }
            },
        )
    return inserted


def seed_cmdb_support() -> dict[str, int]:
    if not _env_enabled("WEBITGPT_SEED_DEMO_HOSTS", True):
        return {"ipam_networks_inserted": 0, "extension_definitions_inserted": 0}
    db = get_db()
    now = datetime.now(timezone.utc)
    network_result = db.ipam_networks.update_one(
        {"cidr": "192.168.1.0/24"},
        {
            "$setOnInsert": {
                "name": "Lab 192.168.1.0/24",
                "cidr": "192.168.1.0/24",
                "dc": "dunan",
                "environment": "DEV",
                "purpose": "Phase 1 demo hosts",
                "vlan": "",
                "gateway": "192.168.1.1",
                "dns": "",
                "reserved_note": ".1-.20 保留給 gateway、網管設備或固定用途；目前 221/222/223 為實際巡檢測試主機。",
                "created_at": now,
            },
            "$set": {"reserved_ips": ["192.168.1.1-192.168.1.20"], "updated_at": now, "updated_by": "bootstrap"},
        },
        upsert=True,
    )
    extension_defaults = [
        {
            "key": "pam_system_id",
            "label": "PAM 系統代號",
            "field_type": "text",
            "required": False,
            "show_in_list": False,
            "searchable": True,
            "applies_to": "all",
            "order": 10,
        },
        {
            "key": "business_owner_note",
            "label": "業務窗口備註",
            "field_type": "text",
            "required": False,
            "show_in_list": False,
            "searchable": True,
            "applies_to": "all",
            "order": 20,
        },
    ]
    inserted_extensions = 0
    for item in extension_defaults:
        result = db.extension_definitions.update_one(
            {"key": item["key"]},
            {"$setOnInsert": {**item, "created_at": now}, "$set": {"updated_at": now, "updated_by": "bootstrap"}},
            upsert=True,
        )
        if result.upserted_id:
            inserted_extensions += 1
    return {"ipam_networks_inserted": int(bool(network_result.upserted_id)), "extension_definitions_inserted": inserted_extensions}


def cleanup_non_actual_data() -> dict[str, int]:
    if not _env_enabled("WEBITGPT_CLEANUP_TEST_DATA", True):
        return {
            "skipped": 1,
            "fake_hosts_removed": 0,
            "fake_related_rows_removed": 0,
            "stale_inventory_removed": 0,
            "stale_inspections_removed": 0,
            "stale_findings_removed": 0,
            "stale_remediation_plans_removed": 0,
        }
    db = get_db()
    hosts = db.hosts
    fake_query = {
        "$or": [
            {"hostname": {"$regex": r"^(func|manual|csv)-hw-", "$options": "i"}},
            {"asset_name": {"$regex": r"(功能驗證測試主機|Functional validation host|Manual validation host|手動批次主機|CSV sample host)", "$options": "i"}},
            {"asset_name": {"$regex": r"^audit host$", "$options": "i"}},
            {"hostname": {"$regex": r"^audit-host$", "$options": "i"}},
            {"asset_seq": {"$regex": r"^HW-9[6-9][0-9]{6}$"}},
            {"asset_seq": "HW-00009999"},
            {"asset_seq": "HW-AUDIT0484"},
        ]
    }
    fake_asset_seqs = [item["asset_seq"] for item in hosts.find(fake_query, {"asset_seq": 1}) if item.get("asset_seq")]
    deleted_hosts = hosts.delete_many({"asset_seq": {"$in": fake_asset_seqs}}).deleted_count if fake_asset_seqs else 0
    removed_related = 0
    related_collections = ["inspection_results", "nmon_data"]
    for name in related_collections:
        if fake_asset_seqs:
            removed_related += db[name].delete_many({"asset_seq": {"$in": fake_asset_seqs}}).deleted_count
    stale_inventory = 0
    stale_inspections = db.inspection_results.delete_many({}).deleted_count
    stale_findings = db.compliance_findings.delete_many({}).deleted_count
    stale_plans = db.compliance_remediation_plans.delete_many({}).deleted_count
    for asset_seq in fake_asset_seqs:
        shutil.rmtree(Path(config.HOSTS_DIR) / asset_seq, ignore_errors=True)
    return {
        "fake_hosts_removed": int(deleted_hosts),
        "fake_related_rows_removed": int(removed_related),
        "stale_inventory_removed": int(stale_inventory),
        "stale_inspections_removed": int(stale_inspections),
        "stale_findings_removed": int(stale_findings),
        "stale_remediation_plans_removed": int(stale_plans),
    }


def ensure_host_directories() -> int:
    count = 0
    for host in get_db().hosts.find({}):
        init_dir(host)
        count += 1
    return count


def import_initial_hosts() -> dict[str, object]:
    csv_path = os.environ.get("WEBITGPT_INITIAL_HOSTS_CSV", "").strip()
    if not csv_path:
        return {"skipped": 1, "created": 0, "updated": 0, "failed": 0}
    path = Path(csv_path)
    if not path.exists():
        return {"skipped": 0, "created": 0, "updated": 0, "failed": 1, "error": f"initial hosts CSV not found: {path}"}
    result = import_csv(path.read_text(encoding="utf-8-sig"), user="bootstrap_csv")
    return {"skipped": 0, **result}


def seed_superadmin() -> bool:
    now = datetime.now(timezone.utc)
    users = get_db().users
    initial_password = os.environ.get("WEBITGPT_SUPERADMIN_PASSWORD") or "change-me-before-login"
    result = users.update_one(
        {"username": "superadmin"},
        {
            "$setOnInsert": {
                "username": "superadmin",
                "display_name": "Super Admin",
                "role": "superadmin",
                "password_hash": generate_password_hash(initial_password),
                "must_change": True,
                "mfa_enabled": False,
                "mfa_secret": None,
                "locked": False,
                "failed_login_count": 0,
                "created_at": now,
                "updated_at": now,
                "created_by": "bootstrap",
            }
        },
        upsert=True,
    )
    return bool(result.upserted_id)


def disable_otp_verification() -> int:
    db = get_db()
    db.feature_flags.update_one(
        {"key": "mfa_required"},
        {
            "$set": {
                "enabled": False,
                "default": False,
                "updated_at": datetime.now(timezone.utc),
                "updated_by": "bootstrap",
            }
        },
    )
    result = db.users.update_many(
        {},
        {
            "$set": {"mfa_enabled": False, "updated_at": datetime.now(timezone.utc)},
            "$unset": {"mfa_secret": "", "mfa_pending_secret": ""},
        },
    )
    return int(result.modified_count)


def write_runtime_files() -> None:
    config.ensure_runtime_dirs()
    version_path = Path(config.DATA_DIR) / "version.json"
    settings_path = Path(config.DATA_DIR) / "settings.json"
    seed_path = Path(config.DATA_DIR) / "bootstrap_seed.json"
    version_path.write_text(
        json.dumps(
            {
                "version": config.VERSION,
                "patch_id": config.PATCH_ID,
                "release_note": config.RELEASE_NOTE,
                "build_time": config.BUILD_TIME,
                "app": config.APP_NAME,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    if not settings_path.exists():
        settings_path.write_text(
            json.dumps(
                {
                    "timezone": config.TZ_NAME,
                    "market_hours": {"start": config.MARKET_HOURS_START, "end": config.MARKET_HOURS_END},
                    "phase_readonly_mode": True,
                    "web_port": config.WEB_PORT,
                    "edge_port": config.EDGE_PORT,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    if _env_enabled("WEBITGPT_SEED_DEMO_HOSTS", True):
        seed_path.write_text(json.dumps(ACTUAL_HOSTS, ensure_ascii=False, indent=2), encoding="utf-8")
    elif not seed_path.exists():
        seed_path.write_text("[]\n", encoding="utf-8")


def repair_imported_platform_classification() -> dict:
    return bulk_apply_platform_suggestions(user="bootstrap_platform_repair", limit=5000)


def main() -> None:
    ensure_collections()
    ensure_indexes()
    host_count = seed_hosts()
    cmdb_support = seed_cmdb_support()
    cleanup_stats = cleanup_non_actual_data()
    imported_hosts = import_initial_hosts()
    host_dirs = ensure_host_directories()
    flag_count = ensure_feature_flags()
    otp_disabled_users = disable_otp_verification()
    rule_count = ensure_default_rules()
    ensure_default_statuses()
    platform_repair = repair_imported_platform_classification()
    user_created = seed_superadmin()
    write_runtime_files()
    print(
        json.dumps(
            {
                "status": "ok",
                "db": config.MONGO_DB_NAME,
                "hosts_seeded": host_count,
                "cmdb_support": cmdb_support,
                "cleanup": cleanup_stats,
                "initial_hosts_import": imported_hosts,
                "host_dirs_synced": host_dirs,
                "feature_flags_inserted": flag_count,
                "otp_disabled_users": otp_disabled_users,
                "compliance_rules_inserted": rule_count,
                "asset_governance_statuses_seeded": True,
                "platform_repair": platform_repair,
                "superadmin_created": user_created,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
