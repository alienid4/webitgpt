from __future__ import annotations

import json
import csv
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from webapp import config
from webapp.services import host_service
from webapp.services.host_dir_service import init_dir
from webapp.services.mongo_service import get_collection
from webapp.services.runner_dispatcher import get_runner


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hosts(limit: int = 100) -> list[dict[str, Any]]:
    return host_service.list_hosts(page=1, page_size=limit)["items"]


DEFAULT_MIN_INTERVAL_MINUTES = 360


def _item_key(item: dict[str, Any]) -> str:
    return str(item.get("name") or item.get("user") or item.get("id") or "")


def _latest_run(kind: str) -> Optional[dict[str, Any]]:
    return get_collection("inventory_runs").find_one({"kind": kind}, {"_id": 0}, sort=[("started_at", -1)])


def _latest_snapshot(kind: str) -> list[dict[str, Any]]:
    run = _latest_run(kind)
    if not run:
        return []
    return list(get_collection("inventory_snapshots").find({"kind": kind, "run_id": run["run_id"]}, {"_id": 0}).sort("hostname", 1))


def _previous_run(kind: str, current_run_id: str) -> Optional[dict[str, Any]]:
    return get_collection("inventory_runs").find_one({"kind": kind, "run_id": {"$ne": current_run_id}}, {"_id": 0}, sort=[("started_at", -1)])


def _run_by_id(kind: str, run_id: str) -> Optional[dict[str, Any]]:
    return get_collection("inventory_runs").find_one({"kind": kind, "run_id": run_id}, {"_id": 0})


def _snapshot_by_run(kind: str, run_id: str) -> list[dict[str, Any]]:
    return list(get_collection("inventory_snapshots").find({"kind": kind, "run_id": run_id}, {"_id": 0}).sort("hostname", 1))


def _item_digest(item: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "name",
        "user",
        "version",
        "status",
        "account_type",
        "uid",
        "gid",
        "home",
        "shell",
        "can_login",
        "privileged",
        "locked",
        "risk",
        "password_changed",
        "password_expires",
        "last_login",
        "source",
        "port",
    ]
    return {key: item.get(key) for key in keys if key in item}


def _changed_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    keys = sorted(set(before) | set(after))
    return [key for key in keys if before.get(key) != after.get(key)]


def _inventory_diff(kind: str, run_id: str) -> dict[str, Any]:
    current = _snapshot_by_run(kind, run_id)
    previous_run = _previous_run(kind, run_id)
    if not previous_run:
        return {"status": "no_previous", "added": 0, "removed": 0, "changed": 0, "items": []}
    previous = _snapshot_by_run(kind, previous_run["run_id"])
    previous_by_host = {row.get("asset_seq") or row.get("hostname"): row for row in previous}
    changes = []
    for row in current:
        host_key = row.get("asset_seq") or row.get("hostname")
        before = previous_by_host.get(host_key, {})
        before_items = {_item_key(item): item for item in before.get("items", []) if _item_key(item)}
        after_items = {_item_key(item): item for item in row.get("items", []) if _item_key(item)}
        added = sorted(set(after_items) - set(before_items))
        removed = sorted(set(before_items) - set(after_items))
        changed = []
        for key in sorted(set(before_items) & set(after_items)):
            if before_items[key] != after_items[key]:
                changed.append(key)
        if added or removed or changed:
            changes.append({"asset_seq": row.get("asset_seq"), "hostname": row.get("hostname"), "added": added, "removed": removed, "changed": changed})
    return {
        "status": "compared",
        "previous_run_id": previous_run["run_id"],
        "added": sum(len(item["added"]) for item in changes),
        "removed": sum(len(item["removed"]) for item in changes),
        "changed": sum(len(item["changed"]) for item in changes),
        "items": changes,
    }


def inventory_diff_report(kind: str, run_id: str = "", change_type: str = "") -> dict[str, Any]:
    current_run = _run_by_id(kind, run_id) if run_id else _latest_run(kind)
    if not current_run:
        return {"kind": kind, "status": "empty", "run": None, "previous_run": None, "summary": {"added": 0, "removed": 0, "changed": 0}, "rows": [], "filter": {"change_type": change_type}}
    previous_run = _previous_run(kind, current_run["run_id"])
    if not previous_run:
        return {
            "kind": kind,
            "status": "no_previous",
            "run": current_run,
            "previous_run": None,
            "summary": {"added": 0, "removed": 0, "changed": 0},
            "rows": [],
            "filter": {"change_type": change_type},
        }

    current = _snapshot_by_run(kind, current_run["run_id"])
    previous = _snapshot_by_run(kind, previous_run["run_id"])
    previous_by_host = {row.get("asset_seq") or row.get("hostname"): row for row in previous}
    rows = []
    summary = {"added": 0, "removed": 0, "changed": 0}
    for row in current:
        host_key = row.get("asset_seq") or row.get("hostname")
        before = previous_by_host.get(host_key, {})
        before_items = {_item_key(item): item for item in before.get("items", []) if _item_key(item)}
        after_items = {_item_key(item): item for item in row.get("items", []) if _item_key(item)}
        for item_name in sorted(set(after_items) - set(before_items)):
            summary["added"] += 1
            rows.append(
                {
                    "asset_seq": row.get("asset_seq"),
                    "hostname": row.get("hostname"),
                    "host_type": row.get("host_type"),
                    "change_type": "新增",
                    "item_name": item_name,
                    "changed_fields": "",
                    "before": "",
                    "after": json.dumps(_item_digest(after_items[item_name]), ensure_ascii=False, default=str),
                }
            )
        for item_name in sorted(set(before_items) - set(after_items)):
            summary["removed"] += 1
            rows.append(
                {
                    "asset_seq": row.get("asset_seq"),
                    "hostname": row.get("hostname"),
                    "host_type": row.get("host_type"),
                    "change_type": "移除",
                    "item_name": item_name,
                    "changed_fields": "",
                    "before": json.dumps(_item_digest(before_items[item_name]), ensure_ascii=False, default=str),
                    "after": "",
                }
            )
        for item_name in sorted(set(before_items) & set(after_items)):
            before_digest = _item_digest(before_items[item_name])
            after_digest = _item_digest(after_items[item_name])
            fields = _changed_fields(before_digest, after_digest)
            if fields:
                summary["changed"] += 1
                rows.append(
                    {
                        "asset_seq": row.get("asset_seq"),
                        "hostname": row.get("hostname"),
                        "host_type": row.get("host_type"),
                        "change_type": "變更",
                        "item_name": item_name,
                        "changed_fields": ", ".join(fields),
                        "before": json.dumps(before_digest, ensure_ascii=False, default=str),
                        "after": json.dumps(after_digest, ensure_ascii=False, default=str),
                    }
                )
    filtered_rows = rows
    if change_type:
        filtered_rows = [row for row in rows if row.get("change_type") == change_type]
    return {
        "kind": kind,
        "status": "compared",
        "run": current_run,
        "previous_run": previous_run,
        "summary": summary,
        "rows": filtered_rows,
        "all_rows_count": len(rows),
        "filter": {"change_type": change_type},
    }


def export_inventory_diff_csv(kind: str, run_id: str = "", change_type: str = "") -> str:
    report = inventory_diff_report(kind, run_id, change_type)
    output = io.StringIO()
    fields = ["change_type", "asset_seq", "hostname", "host_type", "item_name", "changed_fields", "before", "after"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in report["rows"]:
        writer.writerow(row)
    return output.getvalue()


def inventory_history(kind: str, limit: int = 20) -> dict[str, Any]:
    runs = list(get_collection("inventory_runs").find({"kind": kind}, {"_id": 0}).sort("started_at", -1).limit(limit))
    latest = runs[0] if runs else None
    return {"kind": kind, "latest": latest, "runs": runs, "diff": _inventory_diff(kind, latest["run_id"]) if latest else None}


def _cooldown_result(kind: str, latest_run: dict[str, Any], min_interval_minutes: int) -> Optional[dict[str, Any]]:
    finished = latest_run.get("finished_at") or latest_run.get("started_at")
    if not finished:
        return None
    if finished.tzinfo is None:
        finished = finished.replace(tzinfo=timezone.utc)
    next_allowed = finished + timedelta(minutes=min_interval_minutes)
    if _now() >= next_allowed:
        return None
    rows = _latest_snapshot(kind)
    return {
        "status": "cached",
        "kind": kind,
        "count": len(rows),
        "read_only": True,
        "items": rows,
        "run": latest_run,
        "next_allowed_at": next_allowed,
        "message": f"最近已完成盤點，{min_interval_minutes} 分鐘內不重複連線採集，已沿用最近一次盤點結果；需要立即重跑請使用 force=true。",
    }


SYSTEM_DEFAULT_ACCOUNTS = {
    "adm",
    "bin",
    "chrony",
    "daemon",
    "dbus",
    "ftp",
    "games",
    "halt",
    "lp",
    "mail",
    "nobody",
    "operator",
    "polkitd",
    "saslauth",
    "setroubleshoot",
    "shutdown",
    "sshd",
    "sssd",
    "sync",
    "tss",
}

SYSTEM_ACCOUNT_USAGE_NOTES = {
    "adm": "系統預設帳號：歷史系統管理群組使用，不需互動登入",
    "bin": "系統預設帳號：系統二進位檔案擁有者，不需互動登入",
    "chrony": "系統預設帳號：時間同步服務 chrony 使用，不需互動登入",
    "daemon": "系統預設帳號：背景服務執行使用，不需互動登入",
    "dbus": "系統預設帳號：系統訊息匯流排服務使用，不需互動登入",
    "ftp": "系統預設帳號：FTP 服務隔離使用，不需互動登入",
    "games": "系統預設帳號：歷史遊戲檔案擁有者，不需互動登入",
    "halt": "系統預設帳號：系統關機指令使用，不需互動登入",
    "lp": "系統預設帳號：列印服務使用，不需互動登入",
    "mail": "系統預設帳號：郵件服務與郵件檔案使用，不需互動登入",
    "nobody": "系統預設帳號：低權限降級與隔離用途，不需互動登入",
    "operator": "系統預設帳號：歷史系統操作用途，不需互動登入",
    "polkitd": "系統預設帳號：PolicyKit 權限服務使用，不需互動登入",
    "saslauth": "系統預設帳號：SASL 認證服務使用，不需互動登入",
    "setroubleshoot": "系統預設帳號：SELinux 疑難排解服務使用，不需互動登入",
    "shutdown": "系統預設帳號：系統關機指令使用，不需互動登入",
    "sshd": "系統預設帳號：SSH 服務權限隔離使用，不需互動登入",
    "sssd": "系統預設帳號：SSSD 身分驗證服務使用，不需互動登入",
    "sync": "系統預設帳號：系統同步指令使用，不需互動登入",
    "tss": "系統預設帳號：TPM/TSS 安全晶片服務使用，不需互動登入",
}


def is_system_default_account(name: str) -> bool:
    if not name or name == "root":
        return False
    return name in SYSTEM_DEFAULT_ACCOUNTS or name.startswith("systemd-")


def normalize_account_risk(name: str, item: dict[str, Any], system_default: bool) -> str:
    risk = item.get("risk") or "正常"
    if system_default and not item.get("can_login", False):
        return "正常"
    if risk == "從未登入" and not item.get("can_login", False):
        return "正常"
    return risk


def _account_note_key(hostname: str, asset_seq: str, name: str) -> str:
    return f"{hostname or asset_seq}:{name}"


def _account_global_key(name: str, platform_scope: str = "all") -> str:
    return f"*:{platform_scope}:{name}"


def _account_platform_scope(host_type: str) -> str:
    return (host_type or "unknown").lower()


def _account_platform_bulk_supported(platform_scope: str) -> bool:
    return platform_scope in {"linux", "windows", "aix"}


def _load_account_governance() -> dict[str, dict[str, Any]]:
    rows = get_collection("account_usage_notes").find({}, {"_id": 0})
    return {row["key"]: row for row in rows if row.get("key")}


def save_account_usage_note(
    hostname: str,
    asset_seq: str,
    name: str,
    usage_note: str,
    user: str,
    owner: str = "",
    pam_managed: bool = False,
    apply_all: bool = False,
    platform_scope: str = "",
) -> dict[str, Any]:
    now = _now()
    platform_scope = _account_platform_scope(platform_scope or "unknown")
    apply_all = apply_all and _account_platform_bulk_supported(platform_scope)
    key = _account_global_key(name, platform_scope) if apply_all else _account_note_key(hostname, asset_seq, name)
    doc = {
        "key": key,
        "hostname": "" if apply_all else hostname,
        "asset_seq": "" if apply_all else asset_seq,
        "name": name,
        "scope": "platform_account" if apply_all else "host_account",
        "platform_scope": platform_scope if apply_all else "",
        "usage_note": usage_note.strip(),
        "owner": owner.strip(),
        "pam_managed": bool(pam_managed),
        "updated_by": user,
        "updated_at": now,
    }
    get_collection("account_usage_notes").update_one({"key": doc["key"]}, {"$set": doc}, upsert=True)
    return doc


def account_usage_note(name: str, item: dict[str, Any], system_default: bool, risk: str) -> str:
    if name == "root":
        return "最高權限系統管理帳號，必須保留盤點並定期確認保管人"
    if system_default:
        if name.startswith("systemd-"):
            return "系統預設帳號：systemd 服務隔離使用，不需互動登入"
        return SYSTEM_ACCOUNT_USAGE_NOTES.get(name, "系統預設帳號：作業系統或服務使用，不需互動登入")
    if "服務帳號可登入" in risk:
        return "服務帳號具登入能力，需確認用途、保管人與是否仍需要互動登入"
    if item.get("account_type") == "服務帳號":
        return "服務或應用程式使用帳號，需確認負責單位與保管人"
    return "人員或應用帳號，需確認部門、HR 歸屬與使用狀態"


def collect_inventory(kind: str, limit: int = 100, user: str = "system", force: bool = False, min_interval_minutes: int = DEFAULT_MIN_INTERVAL_MINUTES) -> dict[str, Any]:
    latest_run = _latest_run(kind)
    if latest_run and not force:
        cached = _cooldown_result(kind, latest_run, min_interval_minutes)
        if cached:
            return cached
    rows = []
    now = _now()
    run_id = f"{kind}-{now.strftime('%Y%m%d%H%M%S%f')}"
    run_doc = {
        "run_id": run_id,
        "kind": kind,
        "status": "running",
        "started_at": now,
        "created_by": user,
        "min_interval_minutes": min_interval_minutes,
        "force": force,
    }
    get_collection("inventory_runs").insert_one({**run_doc})
    for host in _hosts(limit):
        audit = get_runner(host).collect_audit(kind)
        if kind == "accounts":
            items = []
            for item in audit.get("accounts", []):
                if isinstance(item, dict):
                    account = {**item}
                else:
                    account = {"name": item, "status": "present"}
                account.setdefault("status", "present")
                account.setdefault("account_type", "未分類")
                account.setdefault("password_changed", "-")
                account.setdefault("password_expires", "-")
                account.setdefault("last_login", "-")
                account.setdefault("risk", "正常")
                items.append(account)
        elif kind == "software":
            items = [{"name": item, "status": "installed"} for item in audit.get("packages", [])]
        elif kind == "services":
            items = [{"name": name, "status": status} for name, status in audit.get("services", {}).items()]
        elif kind == "ssh_keys":
            items = [{"user": host.get("ssh_user", ""), "port": host.get("ssh_port", 22), "status": "registered" if host.get("ssh_user") else "missing"}]
        else:
            raise KeyError(f"unknown inventory kind: {kind}")
        row = {
            "asset_seq": host.get("asset_seq"),
            "hostname": host.get("hostname"),
            "host_type": host.get("host_type"),
            "environment": host.get("environment"),
            "department": host.get("department") or host.get("user_unit") or "-",
            "items": items,
            "collected_at": now,
            "created_by": user,
            "run_id": run_id,
        }
        rows.append(row)
        host_dir = Path(init_dir(host)) / kind
        host_dir.mkdir(parents=True, exist_ok=True)
        (host_dir / f"{now.strftime('%Y%m%d_%H%M%S')}.json").write_text(json.dumps(row, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if rows:
        col = get_collection(f"{kind}_inventory")
        for row in rows:
            col.update_one(
                {"asset_seq": row["asset_seq"]},
                {"$set": row},
                upsert=True,
            )
            get_collection("inventory_snapshots").insert_one({**row, "kind": kind})
    diff = _inventory_diff(kind, run_id)
    get_collection("inventory_runs").update_one(
        {"run_id": run_id},
        {
            "$set": {
                "status": "ok",
                "finished_at": _now(),
                "count": len(rows),
                "diff": {"added": diff["added"], "removed": diff["removed"], "changed": diff["changed"], "status": diff["status"]},
            }
        },
    )
    run_doc = get_collection("inventory_runs").find_one({"run_id": run_id}, {"_id": 0}) or run_doc
    return {"status": "ok", "kind": kind, "count": len(rows), "read_only": True, "items": rows, "run": run_doc, "diff": diff}


def latest_inventory(kind: str, limit: int = 50) -> dict[str, Any]:
    rows = list(get_collection(f"{kind}_inventory").find({}, {"_id": 0}).sort("collected_at", -1).limit(limit))
    return {"kind": kind, "count": len(rows), "items": rows}


def account_inventory_view(filters: Optional[dict[str, str]] = None) -> dict[str, Any]:
    filters = filters or {}
    rows = latest_inventory("accounts", limit=200)["items"]
    accounts = []
    governance = _load_account_governance()
    for row in rows:
        for item in row.get("items", []):
            name = item.get("name") or item.get("user") or ""
            gecos = item.get("gecos") or ""
            system_default = is_system_default_account(name)
            platform_scope = _account_platform_scope(row.get("host_type", ""))
            risk = normalize_account_risk(name, item, system_default)
            can_login = item.get("can_login", False)
            last_login = item.get("last_login") or "-"
            if system_default and not can_login:
                last_login = "不適用"
            usage_note = account_usage_note(name, item, system_default, risk)
            global_governance = governance.get(_account_global_key(name, platform_scope), {})
            host_governance = governance.get(_account_note_key(row.get("hostname", ""), row.get("asset_seq", ""), name), {})
            merged_governance = {**global_governance, **host_governance}
            usage_note = merged_governance.get("usage_note") or usage_note
            account = {
                "asset_seq": row.get("asset_seq", ""),
                "hostname": row.get("hostname", ""),
                "host_type": row.get("host_type", ""),
                "platform_scope": platform_scope,
                "platform_bulk_supported": _account_platform_bulk_supported(platform_scope),
                "department": row.get("department") or "-",
                "name": name,
                "uid": item.get("uid"),
                "gid": item.get("gid"),
                "home": item.get("home") or "-",
                "shell": item.get("shell") or "-",
                "can_login": can_login,
                "privileged": bool(item.get("privileged")) or name == "root" or "高權限" in risk,
                "locked": bool(item.get("locked", False)),
                "note": item.get("account_type") or "-",
                "usage_note": usage_note,
                "account_owner": merged_governance.get("owner") or "-",
                "pam_managed": bool(merged_governance.get("pam_managed", False)),
                "governance_scope": merged_governance.get("scope") or "default",
                "hr_name": gecos.split(",", 1)[0] if gecos else "-",
                "password_changed": item.get("password_changed") or "-",
                "password_age_days": item.get("password_age_days"),
                "password_expires": item.get("password_expires") or "-",
                "last_login": last_login,
                "risk": risk,
                "is_system_default": system_default,
                "collected_at": row.get("collected_at"),
            }
            accounts.append(account)
    all_accounts = list(accounts)
    hide_system_defaults = filters.get("include_system_defaults") != "1"
    if hide_system_defaults:
        accounts = [item for item in accounts if not item["is_system_default"]]
    managed_hosts = _hosts(10000)
    department_hosts = account_department_host_summary(managed_hosts)
    inventoried_host_keys = {row.get("hostname") or row.get("asset_seq") for row in rows if row.get("hostname") or row.get("asset_seq")}
    summary = {
        "total": len(accounts),
        "all_total": len(all_accounts),
        "managed_hosts": len(managed_hosts),
        "inventoried_hosts": len(inventoried_host_keys),
        "departments": len(department_hosts),
        "system_default_hidden": sum(1 for item in all_accounts if item["is_system_default"]) if hide_system_defaults else 0,
        "abnormal": sum(1 for item in accounts if item["risk"] != "正常"),
        "privileged": sum(1 for item in accounts if "高權限" in item["risk"]),
        "never_login": sum(1 for item in accounts if "從未登入" in item["risk"] or item["last_login"] == "從未登入"),
        "password_old": sum(1 for item in accounts if "密碼超過90天" in item["risk"]),
        "service_login": sum(1 for item in accounts if "服務帳號可登入" in item["risk"]),
        "pam_managed": sum(1 for item in accounts if item.get("pam_managed")),
    }
    options = {
        "hosts": sorted({host.get("hostname") or host.get("asset_seq") for host in managed_hosts if host.get("hostname") or host.get("asset_seq")}),
        "departments": sorted({host.get("department") or host.get("user_unit") for host in managed_hosts if host.get("department") or host.get("user_unit")}),
        "risks": ["異常", "高權限", "服務帳號可登入", "密碼超過90天", "從未登入", "正常"],
    }
    q = (filters.get("q") or "").strip().lower()
    host = filters.get("host") or ""
    department = filters.get("department") or ""
    risk = filters.get("risk") or ""
    metric = filters.get("metric") or ""
    if host:
        accounts = [item for item in accounts if item["hostname"] == host or item["asset_seq"] == host]
    if department:
        accounts = [item for item in accounts if item["department"] == department]
    if risk:
        if risk == "異常":
            accounts = [item for item in accounts if item["risk"] != "正常"]
        else:
            accounts = [item for item in accounts if risk in item["risk"]]
    if metric == "pam_managed":
        accounts = [item for item in accounts if item.get("pam_managed")]
    elif metric == "system_default":
        accounts = [item for item in accounts if item.get("is_system_default")]
    elif metric == "service_login":
        accounts = [item for item in accounts if "服務帳號可登入" in item["risk"]]
    elif metric == "never_login":
        accounts = [item for item in accounts if "從未登入" in item["risk"] or item["last_login"] == "從未登入"]
    elif metric == "privileged":
        accounts = [item for item in accounts if "高權限" in item["risk"]]
    elif metric == "abnormal":
        accounts = [item for item in accounts if item["risk"] != "正常"]
    if q:
        accounts = [
            item
            for item in accounts
            if q in item["name"].lower()
            or q in item["hostname"].lower()
            or q in item["asset_seq"].lower()
            or q in item["note"].lower()
            or q in item["hr_name"].lower()
        ]
    last_collected = "-"
    collected_values = [item.get("collected_at") for item in all_accounts if item.get("collected_at")]
    if collected_values:
        last_collected = max(collected_values)
    return {
        "count": len(accounts),
        "items": accounts,
        "options": options,
        "filters": filters,
        "hide_system_defaults": hide_system_defaults,
        "last_collected": last_collected,
        "summary": summary,
        "by_host": account_host_summary(accounts, managed_hosts, rows),
        "by_account": account_name_summary(accounts),
        "compliance": account_compliance_summary(accounts),
        "action_plan": account_action_plan(accounts),
        "changes": account_change_summary(rows),
        "department_hosts": department_hosts,
        "history": inventory_history("accounts", limit=10),
    }


def export_accounts_csv(filters: Optional[dict[str, str]] = None) -> str:
    view = account_inventory_view(filters)
    output = io.StringIO()
    fields = ["hostname", "name", "uid", "gid", "home", "shell", "can_login", "privileged", "locked", "note", "usage_note", "account_owner", "pam_managed", "department", "hr_name", "password_changed", "password_expires", "last_login", "risk"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for item in view["items"]:
        writer.writerow(item)
    return output.getvalue()


def account_host_summary(items: list[dict[str, Any]], managed_hosts: list[dict[str, Any]], inventory_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    inventory_by_host = {
        row.get("hostname") or row.get("asset_seq") or "-": row
        for row in inventory_rows
    }
    for host in managed_hosts:
        key = host.get("hostname") or host.get("asset_seq") or "-"
        inv = inventory_by_host.get(key)
        collected_at = inv.get("collected_at") if inv else None
        status = "已盤點" if inv and inv.get("items") else "無帳號資料"
        if not inv:
            status = "尚未盤點"
        rows[key] = {
            "host": key,
            "asset_seq": host.get("asset_seq", ""),
            "total": 0,
            "abnormal": 0,
            "no_owner": 0,
            "never_login": 0,
            "privileged": 0,
            "status": status,
            "last_collected": collected_at or "-",
        }
    for item in items:
        key = item["hostname"] or item["asset_seq"] or "-"
        row = rows.setdefault(
            key,
            {"host": key, "asset_seq": item.get("asset_seq", ""), "total": 0, "abnormal": 0, "no_owner": 0, "never_login": 0, "privileged": 0, "status": "已盤點", "last_collected": item.get("collected_at") or "-"},
        )
        row["total"] += 1
        row["abnormal"] += 1 if item["risk"] != "正常" else 0
        row["no_owner"] += 1 if item["hr_name"] in {"", "-"} and not item["is_system_default"] else 0
        row["never_login"] += 1 if item["last_login"] == "從未登入" and item["can_login"] else 0
        row["privileged"] += 1 if item["privileged"] else 0
        if row["status"] == "無帳號資料":
            row["status"] = "已盤點"
    return sorted(rows.values(), key=lambda row: (-row["abnormal"], row["host"]))


def account_department_host_summary(managed_hosts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for host in managed_hosts:
        department = host.get("department") or host.get("user_unit") or "-"
        row = rows.setdefault(department, {"department": department, "count": 0, "hosts": []})
        row["count"] += 1
        row["hosts"].append(host.get("hostname") or host.get("asset_seq") or "-")
    result = []
    for row in rows.values():
        result.append({**row, "hosts_text": "、".join(sorted(row["hosts"]))})
    return sorted(result, key=lambda item: (-item["count"], item["department"]))


def account_name_summary(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for item in items:
        row = rows.setdefault(
            item["name"],
            {"name": item["name"], "hosts": [], "count": 0, "risks": set(), "privileged": False, "service_login": False, "usage_note": item["usage_note"]},
        )
        row["hosts"].append(item["hostname"] or item["asset_seq"])
        row["count"] += 1
        row["risks"].add(item["risk"])
        row["privileged"] = row["privileged"] or item["privileged"]
        row["service_login"] = row["service_login"] or ("服務帳號可登入" in item["risk"])
    result = []
    for row in rows.values():
        result.append({**row, "risks": "、".join(sorted(row["risks"])), "hosts_text": "、".join(sorted(row["hosts"]))})
    return sorted(result, key=lambda row: (-row["count"], row["name"]))


def account_compliance_summary(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blacklist = {"guest", "test", "test01", "test02", "temp", "tmp"}
    whitelist = {"sysinfra"}
    names = {item["name"] for item in items}
    checks = [
        {"name": "黑名單帳號不可存在", "status": "異常" if names & blacklist else "正常", "count": len(names & blacklist), "detail": "、".join(sorted(names & blacklist)) or "-"},
        {"name": "白名單帳號必須存在", "status": "異常" if whitelist - names else "正常", "count": len(whitelist - names), "detail": "缺少：" + "、".join(sorted(whitelist - names)) if whitelist - names else "-"},
        {"name": "服務帳號不可互動登入", "status": "異常" if any("服務帳號可登入" in item["risk"] for item in items) else "正常", "count": sum(1 for item in items if "服務帳號可登入" in item["risk"]), "detail": "-"},
        {"name": "高權限帳號需列管", "status": "注意" if any(item["privileged"] for item in items) else "正常", "count": sum(1 for item in items if item["privileged"]), "detail": "-"},
        {"name": "人員帳號需有負責人", "status": "異常" if any(item["hr_name"] in {"", "-"} and not item["is_system_default"] for item in items) else "正常", "count": sum(1 for item in items if item["hr_name"] in {"", "-"} and not item["is_system_default"]), "detail": "-"},
    ]
    return checks


def account_action_plan(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plans = []
    for item in items:
        if item["risk"] == "正常":
            continue
        action = "人工確認"
        if "服務帳號可登入" in item["risk"]:
            action = "規劃改為不可互動登入"
        elif item["last_login"] == "從未登入":
            action = "確認負責人後停用或保留例外"
        elif item["privileged"]:
            action = "確認高權限授權與保管人"
        plans.append(
            {
                "hostname": item["hostname"] or item["asset_seq"],
                "name": item["name"],
                "risk": item["risk"],
                "action": action,
                "mode": "dry-run",
                "backup": "/etc/passwd /etc/shadow /etc/group /etc/sudoers",
                "rollback": "還原備份檔並重新載入帳號資料",
            }
        )
    return plans[:20]


def account_change_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    changes = []
    for row in rows:
        asset_seq = row.get("asset_seq") or ""
        hostname = row.get("hostname") or asset_seq
        account_dir = Path(config.HOSTS_DIR) / asset_seq / "accounts"
        files = sorted(account_dir.glob("*.json"), key=lambda path: path.name, reverse=True)
        if len(files) < 2:
            changes.append({"host": hostname, "added": [], "removed": [], "changed": [], "status": "尚無上次盤點"})
            continue
        try:
            current = json.loads(files[0].read_text(encoding="utf-8"))
            previous = json.loads(files[1].read_text(encoding="utf-8"))
        except Exception:
            changes.append({"host": hostname, "added": [], "removed": [], "changed": [], "status": "差異讀取失敗"})
            continue
        current_items = {item.get("name"): item for item in current.get("items", []) if item.get("name")}
        previous_items = {item.get("name"): item for item in previous.get("items", []) if item.get("name")}
        added = sorted(set(current_items) - set(previous_items))
        removed = sorted(set(previous_items) - set(current_items))
        changed = []
        for name in sorted(set(current_items) & set(previous_items)):
            before = previous_items[name]
            after = current_items[name]
            watched = ["uid", "gid", "shell", "home", "risk", "can_login", "privileged"]
            if any(before.get(field) != after.get(field) for field in watched):
                changed.append(name)
        changes.append(
            {
                "host": hostname,
                "added": added,
                "removed": removed,
                "changed": changed,
                "status": "有差異" if added or removed or changed else "無差異",
            }
        )
    return changes


def _count_by(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for item in items:
        value = item.get(key) or "-"
        counts[value] = counts.get(value, 0) + 1
    return [{"name": name, "count": count} for name, count in sorted(counts.items(), key=lambda row: (-row[1], row[0]))]


def account_report_summary(filters: Optional[dict[str, str]] = None) -> dict[str, Any]:
    view = account_inventory_view(filters or {})
    items = view["items"]
    abnormal_items = [item for item in items if item["risk"] != "正常"]
    return {
        "summary": view["summary"],
        "count": view["count"],
        "last_collected": view["last_collected"],
        "hide_system_defaults": view["hide_system_defaults"],
        "by_department": _count_by(items, "department"),
        "by_host": _count_by(items, "hostname"),
        "by_risk": _count_by(items, "risk"),
        "abnormal_items": abnormal_items[:20],
        "abnormal_count": len(abnormal_items),
    }


def ssh_key_plan(asset_seq: Optional[str] = None) -> dict[str, Any]:
    hosts = [host_service.get_host(asset_seq)] if asset_seq else _hosts(100)
    hosts = [host for host in hosts if host]
    items = []
    for host in hosts:
        items.append(
            {
                "asset_seq": host.get("asset_seq"),
                "hostname": host.get("hostname"),
                "ssh_user": host.get("ssh_user", ""),
                "ssh_port": host.get("ssh_port", 22),
                "action": "blocked_by_phase_readonly_mode",
            }
        )
    return {"status": "planned", "mode": "dry-run", "read_only": True, "count": len(items), "items": items}


def create_change_ticket(payload: dict[str, Any], user: str = "system") -> dict[str, Any]:
    now = _now()
    doc = {
        "ticket_id": payload.get("ticket_id") or f"CHG-{now.strftime('%Y%m%d%H%M%S')}",
        "title": payload.get("title", "webitgpt change"),
        "target": payload.get("target", ""),
        "risk": payload.get("risk", "low"),
        "status": payload.get("status", "draft"),
        "rollback_plan": payload.get("rollback_plan", "dry-run rollback plan required before execution"),
        "created_by": user,
        "created_at": now,
        "updated_at": now,
    }
    get_collection("change_tickets").update_one({"ticket_id": doc["ticket_id"]}, {"$set": doc}, upsert=True)
    doc.pop("_id", None)
    return doc


def list_change_tickets(limit: int = 50) -> list[dict[str, Any]]:
    return list(get_collection("change_tickets").find({}, {"_id": 0}).sort("created_at", -1).limit(limit))
