from __future__ import annotations

import csv
import io
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from webapp import config
from webapp.services.host_service import get_host
from webapp.services.host_service import list_hosts
from webapp.services.deep_check_service import latest_report
from webapp.services.inventory_service import DEFAULT_MIN_INTERVAL_MINUTES, inventory_history
from webapp.services.mongo_service import get_collection


PLATFORM_TABS = [
    {"key": "linux", "label": "Linux"},
    {"key": "windows", "label": "Windows"},
    {"key": "aix", "label": "AIX"},
    {"key": "as400", "label": "AS400"},
]

OPENING_DEFAULT_SYSTEM = "巡檢系統主機"
OPENING_ALL_SYSTEMS_VALUE = "__all__"

DIAGNOSTIC_ASPECTS = [
    ("connectivity", "連線狀態"),
    ("resource", "CPU / 記憶體 / 磁碟"),
    ("filesystem", "檔案系統"),
    ("process", "程序"),
    ("service", "服務"),
    ("account", "帳號"),
    ("security", "安全設定"),
    ("package", "套件"),
    ("log", "系統日誌"),
]


def _with_diagnostic_summary(row: dict[str, Any]) -> dict[str, Any]:
    checks = row.get("checks", [])
    ok = sum(1 for item in checks if item.get("status") == "ok")
    warn = sum(1 for item in checks if item.get("status") == "warn")
    pending = sum(1 for item in checks if item.get("status") == "pending")
    fail = sum(1 for item in checks if item.get("status") in {"fail", "error"})
    total = max(len(checks), 1)
    score = max(0, round(((ok + pending * 0.35) / total) * 100) - warn * 6 - fail * 15)
    if fail:
        overall = "fail"
        overall_label = "異常"
    elif warn:
        overall = "warn"
        overall_label = "警示"
    elif pending:
        overall = "pending"
        overall_label = "待檢"
    else:
        overall = "ok"
        overall_label = "正常"
    row["summary"] = {"ok": ok, "warn": warn, "pending": pending, "fail": fail, "total": total, "score": score}
    row["overall"] = overall
    row["overall_label"] = overall_label
    return row

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hosts() -> list[dict[str, Any]]:
    return list_hosts(page=1, page_size=10000)["items"]


def _system_name(host: dict[str, Any]) -> str:
    return str(host.get("asset_name") or host.get("system_name") or host.get("group_name") or "未分類系統").strip()


def _system_options(hosts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for host in hosts:
        name = _system_name(host)
        counts[name] = counts.get(name, 0) + 1
    return [{"name": name, "count": count} for name, count in sorted(counts.items())]


def _selected_system(system_name: str, options: list[dict[str, Any]]) -> str:
    names = {item["name"] for item in options}
    requested = (system_name or "").strip()
    if requested == OPENING_ALL_SYSTEMS_VALUE:
        return ""
    if requested and requested in names:
        return requested
    if OPENING_DEFAULT_SYSTEM in names:
        return OPENING_DEFAULT_SYSTEM
    return sorted(names)[0] if names else ""


def _shell(cmd: str, timeout: int = 12) -> tuple[int, str, str]:
    completed = subprocess.run(cmd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def _local_linux_diagnostics(host: dict[str, Any]) -> dict[str, Any]:
    checks = []
    commands = {
        "connectivity": "hostname && uptime",
        "resource": "top -bn1 | head -5; df -h /",
        "filesystem": "df -hT | head -10",
        "process": "ps -eo pid,comm,%cpu,%mem --sort=-%cpu | head -10",
        "service": "systemctl --failed --no-pager || true",
        "account": "getent passwd | head -10",
        "security": "ss -ltn | head -10",
        "package": "command -v rpm >/dev/null && rpm -qa | head -10 || dpkg-query -W | head -10",
        "log": "journalctl -p warning -n 10 --no-pager || true",
    }
    for key, label in DIAGNOSTIC_ASPECTS:
        try:
            rc, out, err = _shell(commands[key])
            status = "ok" if rc == 0 else "warn"
            detail = out or err or "無輸出"
        except Exception as exc:
            status = "warn"
            detail = str(exc)
        checks.append({"key": key, "label": label, "status": status, "detail": detail[:1200]})
    return _with_diagnostic_summary({
        "asset_seq": host.get("asset_seq"),
        "hostname": host.get("hostname"),
        "host_type": host.get("host_type"),
        "platform": "linux",
        "checked_at": _now(),
        "checks": checks,
    })


def _remote_linux_command(host: dict[str, Any], cmd: str, timeout: int = 18) -> tuple[int, str, str]:
    target = host.get("ip") or host.get("hostname")
    if not target:
        return 2, "", "missing host address"
    if host.get("connection") == "local":
        return _shell(cmd, timeout=timeout)
    ssh_cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "ConnectTimeout=5",
        "-p",
        str(host.get("ssh_port") or 22),
        f"{host.get('ssh_user') or 'sysinfra'}@{target}",
        cmd,
    ]
    completed = subprocess.run(ssh_cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout + 8)
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def _linux_deep_diagnostics(host: dict[str, Any]) -> dict[str, Any]:
    checks = []
    commands = {
        "connectivity": "hostname; uptime; who | wc -l",
        "resource": "printf 'CPU '; top -bn1 | awk -F',' '/Cpu\\(s\\)|%Cpu/ {print $0; exit}'; free -m; df -P /",
        "filesystem": "df -hT; findmnt -rno TARGET,SOURCE,FSTYPE,OPTIONS | head -20",
        "process": "ps -eo pid,ppid,user,comm,%cpu,%mem --sort=-%cpu | head -15",
        "service": "systemctl --failed --no-pager || true; systemctl list-units --type=service --state=running --no-pager | head -20",
        "account": "printf 'users='; getent passwd | wc -l; printf 'sudo/wheel='; getent group sudo wheel 2>/dev/null || true; lastlog | head -15",
        "security": "ss -ltnp 2>/dev/null | head -20; grep -E '^(PermitRootLogin|PasswordAuthentication)' /etc/ssh/sshd_config 2>/dev/null || true",
        "package": "command -v rpm >/dev/null && rpm -qa --last | head -15 || dpkg-query -W -f='${Package} ${Version}\\n' | head -15",
        "log": "journalctl -p warning -n 20 --no-pager 2>/dev/null || tail -50 /var/log/syslog 2>/dev/null || tail -50 /var/log/messages 2>/dev/null",
    }
    for key, label in DIAGNOSTIC_ASPECTS:
        try:
            rc, out, err = _remote_linux_command(host, commands[key])
            status = "ok" if rc == 0 else "warn"
            detail = out or err or "無輸出"
        except Exception as exc:
            status = "warn"
            detail = str(exc)
        checks.append({"key": key, "label": label, "status": status, "detail": detail[:1800]})
    result = _with_diagnostic_summary({
        "asset_seq": host.get("asset_seq"),
        "hostname": host.get("hostname"),
        "ip": host.get("ip"),
        "host_type": host.get("host_type"),
        "platform": "linux",
        "checked_at": _now(),
        "checks": checks,
    })
    get_collection("diagnostic_results").insert_one({**result, "created_at": _now()})
    return result


def _ssh_placeholder_diagnostics(host: dict[str, Any]) -> dict[str, Any]:
    checks = []
    for key, label in DIAGNOSTIC_ASPECTS:
        status = "pending"
        detail = "等待遠端採集。此主機已納入資產，但目前沒有本次深度診斷資料。"
        if host.get("host_type") in {"windows", "aix"}:
            detail = "平台入口已建立，後續由 WinRM / SSH raw runner 接入實際診斷。"
        if host.get("host_type") == "as400":
            detail = "AS400 目前只保留盤點入口，實際採集需等待協定確認。"
        checks.append({"key": key, "label": label, "status": status, "detail": detail})
    return _with_diagnostic_summary({
        "asset_seq": host.get("asset_seq"),
        "hostname": host.get("hostname"),
        "host_type": host.get("host_type"),
        "platform": host.get("host_type"),
        "checked_at": None,
        "checks": checks,
    })


def daily_diagnostics(platform: str = "linux", system_name: str = "") -> dict[str, Any]:
    platform = platform or "linux"
    all_hosts = _hosts()
    options = _system_options(all_hosts)
    selected_system = _selected_system(system_name, options)
    hosts = [
        host
        for host in all_hosts
        if host.get("host_type") == platform and (not selected_system or _system_name(host) == selected_system)
    ]
    if platform == "linux":
        rows = []
        for host in hosts:
            latest = get_collection("diagnostic_results").find_one({"asset_seq": host.get("asset_seq")}, {"_id": 0}, sort=[("checked_at", -1)])
            if latest:
                latest["recent"] = diagnostic_history(host.get("asset_seq"), days=7, limit=6)
                latest["latest_deep_check"] = latest_report(host.get("hostname"))
                rows.append(latest)
            elif host.get("connection") == "local":
                row = _local_linux_diagnostics(host)
                row["recent"] = diagnostic_history(host.get("asset_seq"), days=7, limit=6)
                row["latest_deep_check"] = latest_report(host.get("hostname"))
                rows.append(row)
            else:
                row = _ssh_placeholder_diagnostics(host)
                row["recent"] = diagnostic_history(host.get("asset_seq"), days=7, limit=6)
                row["latest_deep_check"] = latest_report(host.get("hostname"))
                rows.append(row)
    else:
        rows = []
        for host in hosts:
            row = _ssh_placeholder_diagnostics(host)
            row["latest_deep_check"] = latest_report(host.get("hostname"))
            rows.append(row)
    summary = {
        "hosts": len(rows),
        "ok": sum(1 for row in rows for check in row["checks"] if check["status"] == "ok"),
        "warn": sum(1 for row in rows for check in row["checks"] if check["status"] == "warn"),
        "pending": sum(1 for row in rows for check in row["checks"] if check["status"] == "pending"),
    }
    return {
        "platform": platform,
        "tabs": PLATFORM_TABS,
        "aspects": DIAGNOSTIC_ASPECTS,
        "summary": summary,
        "items": rows,
        "system_options": options,
        "selected_system": selected_system,
        "all_systems_value": OPENING_ALL_SYSTEMS_VALUE,
        "all_systems_count": sum(item["count"] for item in options),
        "selected_system_label": selected_system or "全部系統",
    }


def diagnostic_history(asset_seq: str, days: int = 7, limit: int = 10) -> list[dict[str, Any]]:
    since = _now() - timedelta(days=days)
    rows = list(
        get_collection("diagnostic_results")
        .find({"asset_seq": asset_seq, "checked_at": {"$gte": since}}, {"_id": 0})
        .sort("checked_at", -1)
        .limit(limit)
    )
    for row in rows:
        checks = row.get("checks", [])
        row["summary"] = {
            "ok": sum(1 for item in checks if item.get("status") == "ok"),
            "warn": sum(1 for item in checks if item.get("status") == "warn"),
            "pending": sum(1 for item in checks if item.get("status") == "pending"),
        }
    return rows


def run_deep_diagnostic(asset_seq: str, user: str = "system") -> dict[str, Any]:
    host = get_host(asset_seq)
    if not host:
        raise KeyError(f"host not found: {asset_seq}")
    if host.get("host_type") != "linux":
        result = _ssh_placeholder_diagnostics(host)
        result["created_by"] = user
        get_collection("diagnostic_results").insert_one({**result, "created_at": _now()})
        return result
    result = _linux_deep_diagnostics(host)
    result["created_by"] = user
    get_collection("diagnostic_results").update_one(
        {"asset_seq": result["asset_seq"], "checked_at": result["checked_at"]},
        {"$set": {"created_by": user}},
    )
    return result


def _software_cooldown(user: str, force: bool, min_interval_minutes: int) -> dict[str, Any] | None:
    if force:
        return None
    latest = get_collection("inventory_runs").find_one({"kind": "software"}, {"_id": 0}, sort=[("started_at", -1)])
    if not latest:
        return None
    finished = latest.get("finished_at") or latest.get("started_at")
    if not finished:
        return None
    if finished.tzinfo is None:
        finished = finished.replace(tzinfo=timezone.utc)
    next_allowed = finished + timedelta(minutes=min_interval_minutes)
    if _now() >= next_allowed:
        return None
    rows = list(get_collection("inventory_snapshots").find({"kind": "software", "run_id": latest["run_id"]}, {"_id": 0}).sort("hostname", 1))
    return {
        "status": "cached",
        "kind": "software",
        "count": len(rows),
        "items": rows,
        "run": latest,
        "next_allowed_at": next_allowed,
        "message": f"最近已完成軟體盤點，{min_interval_minutes} 分鐘內不重複連線採集，已沿用最近一次盤點結果；需要立即重跑請使用 force=true。",
    }


def collect_software_inventory(user: str = "system", force: bool = False, min_interval_minutes: int = DEFAULT_MIN_INTERVAL_MINUTES) -> dict[str, Any]:
    cached = _software_cooldown(user, force, min_interval_minutes)
    if cached:
        return cached
    now = _now()
    run_id = f"software-{now.strftime('%Y%m%d%H%M%S%f')}"
    get_collection("inventory_runs").insert_one(
        {
            "run_id": run_id,
            "kind": "software",
            "status": "running",
            "started_at": now,
            "created_by": user,
            "min_interval_minutes": min_interval_minutes,
            "force": force,
        }
    )
    rows = []
    for host in _hosts():
        items = []
        if host.get("connection") == "local":
            rc, out, err = _shell("command -v rpm >/dev/null && rpm -qa --qf '%{NAME}|%{VERSION}-%{RELEASE}|rpm\\n' | head -200 || dpkg-query -W -f='${Package}|${Version}|deb\\n' | head -200", timeout=20)
            for line in out.splitlines():
                parts = line.split("|")
                if len(parts) >= 3:
                    items.append({"name": parts[0], "version": parts[1], "source": parts[2], "status": "installed"})
            if rc != 0 and err:
                items.append({"name": "collect_error", "version": err[:200], "source": "local", "status": "warn"})
        rows.append(
            {
                "asset_seq": host.get("asset_seq"),
                "hostname": host.get("hostname"),
                "host_type": host.get("host_type"),
                "environment": host.get("environment"),
                "items": items,
                "collected_at": now,
                "created_by": user,
                "run_id": run_id,
            }
        )
    col = get_collection("software_inventory")
    for row in rows:
        previous = col.find_one({"asset_seq": row["asset_seq"]}, {"_id": 0})
        col.update_one({"asset_seq": row["asset_seq"]}, {"$set": row, "$setOnInsert": {"created_at": now}}, upsert=True)
        get_collection("inventory_snapshots").insert_one({**row, "kind": "software"})
        if previous:
            _save_software_change(row, previous, now, user)
    changes_count = get_collection("software_inventory_changes").count_documents({"created_at": {"$gte": now}})
    get_collection("inventory_runs").update_one(
        {"run_id": run_id},
        {"$set": {"status": "ok", "finished_at": _now(), "count": len(rows), "diff": {"changed": changes_count, "added": 0, "removed": 0, "status": "compared"}}},
    )
    run_doc = get_collection("inventory_runs").find_one({"run_id": run_id}, {"_id": 0})
    return {"status": "ok", "kind": "software", "count": len(rows), "items": rows, "run": run_doc}


def _save_software_change(current: dict[str, Any], previous: dict[str, Any], now: datetime, user: str) -> None:
    before = {item.get("name"): item for item in previous.get("items", []) if item.get("name")}
    after = {item.get("name"): item for item in current.get("items", []) if item.get("name")}
    changes = []
    for name in sorted(set(after) - set(before)):
        changes.append({"type": "新增", "name": name, "before": "", "after": after[name].get("version", "")})
    for name in sorted(set(before) - set(after)):
        changes.append({"type": "移除", "name": name, "before": before[name].get("version", ""), "after": ""})
    for name in sorted(set(before) & set(after)):
        if before[name].get("version") != after[name].get("version"):
            changes.append({"type": "版本變更", "name": name, "before": before[name].get("version", ""), "after": after[name].get("version", "")})
    if changes:
        get_collection("software_inventory_changes").insert_one(
            {
                "asset_seq": current.get("asset_seq"),
                "hostname": current.get("hostname"),
                "changes": changes,
                "created_at": now,
                "created_by": user,
            }
        )


def software_inventory_view(filters: Any = None) -> dict[str, Any]:
    filters = filters or {}
    q = (filters.get("q") or "").strip()
    terms = [term for term in q.lower().split() if term]
    host = filters.get("host") or ""
    rows = list(get_collection("software_inventory").find({}, {"_id": 0}).sort("collected_at", -1).limit(500))
    host_lookup = _software_host_lookup()
    packages = []
    for row in rows:
        if host and host not in {row.get("hostname"), row.get("asset_seq")}:
            continue
        host_meta = host_lookup.get(row.get("hostname")) or host_lookup.get(row.get("asset_seq")) or {}
        for item in row.get("items", []):
            record = {
                **item,
                "hostname": row.get("hostname"),
                "asset_seq": row.get("asset_seq"),
                "ip": row.get("ip") or row.get("primary_ip") or host_meta.get("ip") or "",
                "ip_addresses": row.get("ip_addresses") or host_meta.get("ip_addresses") or [],
                "host_type": row.get("host_type"),
                "collected_at": row.get("collected_at"),
            }
            if terms and not _software_record_matches(record, terms):
                continue
            packages.append(record)
    changes = []
    for change in get_collection("software_inventory_changes").find({}, {"_id": 0}).sort("created_at", -1).limit(100):
        if host and host not in {change.get("hostname"), change.get("asset_seq")}:
            continue
        if terms and not _software_change_matches(change, terms):
            continue
        changes.append(change)
    return {
        "summary": {
            "hosts": len({item.get("hostname") for item in packages if item.get("hostname")}),
            "hosts_total": len({row.get("hostname") for row in rows if row.get("hostname")}),
            "packages": len(packages),
            "changes": sum(len(row.get("changes", [])) for row in changes),
        },
        "hosts": sorted({row.get("hostname") for row in rows if row.get("hostname")}),
        "items": packages[:1000],
        "changes": changes,
        "filters": {"q": q, "host": host, "terms": terms},
        "history": inventory_history("software", limit=10),
    }


def _software_host_lookup() -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for host in _hosts():
        keys = [host.get("hostname"), host.get("asset_seq")]
        for key in keys:
            if key:
                lookup[key] = host
    return lookup


def _software_record_matches(record: dict[str, Any], terms: list[str]) -> bool:
    haystack = " ".join(
        str(record.get(field, ""))
        for field in ["hostname", "asset_seq", "ip", "host_type", "name", "version", "source", "status"]
    ).lower()
    if record.get("ip_addresses"):
        haystack = f"{haystack} {' '.join(str(ip) for ip in record.get('ip_addresses', []))}".lower()
    return all(term in haystack for term in terms)


def _software_change_matches(change: dict[str, Any], terms: list[str]) -> bool:
    parts = [str(change.get("hostname", "")), str(change.get("asset_seq", ""))]
    for item in change.get("changes", []):
        parts.extend([str(item.get("type", "")), str(item.get("name", "")), str(item.get("before", "")), str(item.get("after", ""))])
    haystack = " ".join(parts).lower()
    return all(term in haystack for term in terms)


def software_csv(filters: Any = None) -> str:
    view = software_inventory_view(filters)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["hostname", "asset_seq", "ip", "host_type", "name", "version", "source", "status", "collected_at"], extrasaction="ignore")
    writer.writeheader()
    for item in view["items"]:
        writer.writerow(item)
    return output.getvalue()


def software_json(filters: Any = None) -> dict[str, Any]:
    return software_inventory_view(filters)


def collect_nmon_sample(user: str = "system") -> dict[str, Any]:
    now = _now()
    docs = []
    for host in _hosts():
        if host.get("connection") != "local":
            continue
        rc, out, err = _shell("awk '/MemTotal/ {t=$2} /MemAvailable/ {a=$2} END {printf \"%.1f\", (t-a)*100/t}' /proc/meminfo; echo; df -P / | awk 'NR==2 {gsub(/%/,\"\",$5); print $5}'", timeout=8)
        lines = out.splitlines()
        mem = float(lines[0]) if lines and lines[0] else None
        disk = float(lines[1]) if len(lines) > 1 and lines[1] else None
        doc = {
            "asset_seq": host.get("asset_seq"),
            "hostname": host.get("hostname"),
            "sampled_at": now,
            "cpu_pct": None,
            "mem_pct": mem,
            "disk_pct": disk,
            "load_avg": Path("/proc/loadavg").read_text(encoding="utf-8").split()[0] if Path("/proc/loadavg").exists() else "",
            "created_by": user,
            "error": err if rc != 0 else "",
        }
        get_collection("nmon_data").insert_one({**doc})
        docs.append(doc)
    return {"status": "ok", "count": len(docs), "items": docs}


def nmon_report(period: str = "day") -> dict[str, Any]:
    period = period if period in {"day", "week", "month"} else "day"
    since = _now() - {"day": timedelta(days=1), "week": timedelta(days=7), "month": timedelta(days=31)}[period]
    rows = list(get_collection("nmon_data").find({"sampled_at": {"$gte": since}}, {"_id": 0}).sort("sampled_at", 1).limit(2000))
    by_host: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_host.setdefault(row.get("hostname") or row.get("asset_seq") or "-", []).append(row)
    series = []
    for host, items in by_host.items():
        avg_mem = round(sum(float(item.get("mem_pct") or 0) for item in items) / max(len(items), 1), 1)
        avg_disk = round(sum(float(item.get("disk_pct") or 0) for item in items) / max(len(items), 1), 1)
        series.append({"host": host, "samples": len(items), "avg_mem": avg_mem, "avg_disk": avg_disk, "items": items[-24:]})
    return {"period": period, "count": len(rows), "series": series, "generated_at": _now()}


def topology_view() -> dict[str, Any]:
    hosts = _hosts()
    nodes = []
    edges = []
    dcs = sorted({host.get("dc") or "unknown" for host in hosts})
    for dc in dcs:
        nodes.append({"id": f"dc:{dc}", "label": dc, "kind": "機房"})
    for host in hosts:
        hid = host.get("hostname") or host.get("asset_seq")
        nodes.append({"id": hid, "label": hid, "kind": host.get("host_type") or "host", "status": host.get("status")})
        edges.append({"source": f"dc:{host.get('dc') or 'unknown'}", "target": hid, "label": host.get("environment") or ""})
        if host.get("system_name"):
            sid = f"sys:{host.get('system_name')}"
            if not any(node["id"] == sid for node in nodes):
                nodes.append({"id": sid, "label": host.get("system_name"), "kind": "系統"})
            edges.append({"source": sid, "target": hid, "label": host.get("asset_usage") or ""})

    def assign_positions(group: list[dict[str, Any]], y: int) -> None:
        if not group:
            return
        count = max(len(group), 1)
        if count == 1:
            group[0]["x"] = 550
            group[0]["y"] = y
            return
        step = 900 / max(count - 1, 1)
        for index, node in enumerate(group):
            node["x"] = int(100 + index * step)
            node["y"] = y

    dc_nodes = [node for node in nodes if node["id"].startswith("dc:")]
    system_nodes = [node for node in nodes if node["id"].startswith("sys:")]
    host_nodes = [node for node in nodes if node not in dc_nodes and node not in system_nodes]
    assign_positions(dc_nodes, 80)
    assign_positions(system_nodes, 235)
    assign_positions(host_nodes, 400)

    node_map = {node["id"]: node for node in nodes}
    enriched_edges = []
    for edge in edges:
        source = node_map.get(edge["source"])
        target = node_map.get(edge["target"])
        if not source or not target:
            continue
        enriched_edges.append(
            {
                **edge,
                "source_label": source.get("label") or edge["source"],
                "target_label": target.get("label") or edge["target"],
                "x1": source.get("x"),
                "y1": source.get("y"),
                "x2": target.get("x"),
                "y2": target.get("y"),
            }
        )

    return {"nodes": nodes, "edges": enriched_edges, "hosts": hosts}

