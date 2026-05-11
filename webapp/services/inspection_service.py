from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from webapp import config
from webapp.services.host_service import list_hosts
from webapp.services.mongo_service import get_collection


def _empty_metrics(error: str = "") -> dict[str, Any]:
    return {
        "status": "unknown" if error else "ok",
        "cpu_pct": None,
        "mem_pct": None,
        "disk_pct": None,
        "metric_source": "actual_host_probe",
        "metric_error": error,
    }


def _probe_script() -> str:
    return r"""python3 - <<'PY'
import json
import subprocess

def run(cmd):
    try:
        return subprocess.run(cmd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=8).stdout.strip()
    except Exception:
        return ""

def as_float(value):
    try:
        return round(float(value), 1)
    except Exception:
        return None

cpu_idle = as_float(run("LC_ALL=C top -bn1 | awk -F',' '/Cpu\\(s\\)|%Cpu/ {for(i=1;i<=NF;i++) if($i ~ /id/) {gsub(/[^0-9.]/,\"\",$i); print $i; exit}}'"))
cpu_pct = None if cpu_idle is None else max(0, round(100 - cpu_idle, 1))
mem_pct = as_float(run("awk '/MemTotal/ {total=$2} /MemAvailable/ {avail=$2} END {if(total>0) printf \"%.1f\", (total-avail)*100/total}' /proc/meminfo"))
disk_pct = as_float(run("df -P / | awk 'NR==2 {gsub(/%/,\"\",$5); print $5}'"))
print(json.dumps({"cpu_pct": cpu_pct, "mem_pct": mem_pct, "disk_pct": disk_pct}, ensure_ascii=False))
PY"""


def _parse_metrics(completed: subprocess.CompletedProcess, target: str) -> dict[str, Any]:
    if completed.returncode != 0:
        return _empty_metrics(f"metric probe failed on {target}: {completed.stderr.strip()[:160]}")
    try:
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
    except Exception as exc:
        return _empty_metrics(f"metric probe parse failed on {target}: {exc}")
    status = "ok"
    if payload.get("cpu_pct") is None or payload.get("mem_pct") is None or payload.get("disk_pct") is None:
        status = "unknown"
    elif payload["cpu_pct"] >= 90 or payload["mem_pct"] >= 90 or payload["disk_pct"] >= 90:
        status = "warn"
    return {
        "status": status,
        "cpu_pct": payload.get("cpu_pct"),
        "mem_pct": payload.get("mem_pct"),
        "disk_pct": payload.get("disk_pct"),
        "metric_source": "actual_host_probe",
        "metric_error": "",
    }


def _collect_metrics(host: dict[str, Any]) -> dict[str, Any]:
    target = host.get("ip") or host.get("hostname")
    if not target:
        return _empty_metrics("missing host address")
    if host.get("connection") == "local":
        completed = subprocess.run(
            _probe_script(),
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
        )
        return _parse_metrics(completed, "local")
    if host.get("connection") == "ssh" or host.get("host_type") in {"linux", "aix"}:
        completed = subprocess.run(
            [
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
                _probe_script(),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
        )
        return _parse_metrics(completed, str(target))
    return _empty_metrics("platform metric probe not implemented")


def _inspection_for(host: dict[str, Any]) -> dict[str, Any]:
    metrics = _collect_metrics(host)
    return {
        "asset_seq": host.get("asset_seq"),
        "hostname": host.get("hostname"),
        "host_type": host.get("host_type"),
        "dc": host.get("dc"),
        "environment": host.get("environment"),
        "status": metrics["status"],
        "cpu_pct": metrics["cpu_pct"],
        "mem_pct": metrics["mem_pct"],
        "disk_pct": metrics["disk_pct"],
        "metric_source": metrics["metric_source"],
        "metric_error": metrics["metric_error"],
        "checked_at": datetime.now(timezone.utc),
    }


def run_daily_inspection(limit: int = 20, user: str = "system") -> dict[str, Any]:
    hosts = list_hosts(page=1, page_size=limit)["items"]
    results = [_inspection_for(host) for host in hosts]
    now = datetime.now(timezone.utc)
    if results:
        col = get_collection("inspection_results")
        for item in results:
            col.update_one(
                {"asset_seq": item["asset_seq"]},
                {"$set": {**item, "run_at": now, "created_by": user}},
                upsert=True,
            )
    report_path = Path(config.DATA_DIR) / "reports" / f"inspection_{now.strftime('%Y%m%d_%H%M%S')}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps({"run_at": now.isoformat(), "results": results}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return {"status": "ok", "count": len(results), "report_path": str(report_path), "results": results}


def today_report() -> dict[str, Any]:
    rows = list(get_collection("inspection_results").find({}, {"_id": 0}).sort("run_at", -1).limit(100))
    if not rows:
        hosts = list_hosts(page=1, page_size=100)["items"]
        rows = [
            {
                "asset_seq": host.get("asset_seq"),
                "hostname": host.get("hostname"),
                "host_type": host.get("host_type"),
                "dc": host.get("dc"),
                "environment": host.get("environment"),
                "status": "尚未巡檢",
                "cpu_pct": None,
                "mem_pct": None,
                "disk_pct": None,
                "metric_source": "not_collected",
                "checked_at": None,
            }
            for host in hosts
        ]
    by_status: dict[str, int] = {}
    for row in rows:
        by_status[row.get("status", "unknown")] = by_status.get(row.get("status", "unknown"), 0) + 1
    return {"count": len(rows), "by_status": by_status, "items": rows}


def nmon_status() -> dict[str, Any]:
    hosts = list_hosts(page=1, page_size=10000)["items"]
    enabled = [host for host in hosts if host.get("nmon_enabled")]
    return {"hosts_total": len(hosts), "enabled_count": len(enabled), "items": enabled[:50], "read_only_mode": True}


def nmon_deploy_plan(limit: int = 20) -> dict[str, Any]:
    hosts = list_hosts(page=1, page_size=limit)["items"]
    plan = []
    for host in hosts:
        if host.get("host_type") not in {"linux", "aix"}:
            continue
        plan.append(
            {
                "asset_seq": host.get("asset_seq"),
                "hostname": host.get("hostname"),
                "host_type": host.get("host_type"),
                "interval_min": host.get("nmon_interval_min", 5),
                "action": "blocked_by_phase_readonly_mode",
            }
        )
    return {
        "status": "planned",
        "mode": "dry-run",
        "read_only": True,
        "count": len(plan),
        "steps": ["verify host connection", "upload nmon package", "install scheduler", "start collector"],
        "items": plan,
    }
