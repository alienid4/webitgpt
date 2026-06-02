from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from webapp import config
from webapp.services.collection_credential_service import account_for_tier
from webapp.services.host_service import list_hosts
from webapp.services.mongo_service import get_collection
from webapp.services.system_alias_service import canonical_host_system_name, host_matches_system

IBM_NMON_INTERVAL_SEC = 900
IBM_NMON_SNAPSHOT_COUNT = 96
IBM_NMON_DISK_BUSY_WARN_PCT = 80
IBM_NMON_OUTPUT_DIR = "/var/log/nmon"
IBM_NMON_COLLECT_SCRIPT = "/usr/local/sbin/webitgpt_nmon_collect.sh"
IBM_NMON_CRON_FILE = "/etc/cron.d/webitgpt-nmon"
IBM_NMON_RECORD_COMMAND = "nmon -x"
IBM_NMON_EQUIVALENT_COMMAND = f"nmon -ft -s {IBM_NMON_INTERVAL_SEC} -c {IBM_NMON_SNAPSHOT_COUNT}"


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
                f"{host.get('ssh_user') or account_for_tier('L1', 'sysinfra')}@{target}",
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


def _system_name(host: dict[str, Any]) -> str:
    return canonical_host_system_name(host)


def run_daily_inspection(limit: int = 20, user: str = "system", system_name: str = "", platform: str = "") -> dict[str, Any]:
    selected_system = (system_name or "").strip()
    selected_platform = (platform or "").strip()
    hosts = list_hosts(page=1, page_size=10000)["items"]
    if selected_platform:
        hosts = [host for host in hosts if host.get("host_type") == selected_platform]
    if selected_system:
        hosts = [host for host in hosts if host_matches_system(host, selected_system)]
    hosts = hosts[:limit]
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
    return {
        "status": "ok",
        "count": len(results),
        "system": selected_system,
        "platform": selected_platform,
        "message": f"開門檢查完成：{len(results)} 台。",
        "report_path": str(report_path),
        "results": results,
    }


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
    items = [_nmon_host_status(host) for host in hosts]
    enabled = [host for host in hosts if host.get("nmon_enabled")]
    installed = [item for item in items if item["install_status"] == "已安裝"]
    missing = [item for item in items if item["install_status"] == "缺少"]
    supported = [item for item in items if item["deploy_supported"]]
    return {
        "hosts_total": len(hosts),
        "enabled_count": len(enabled),
        "installed_count": len(installed),
        "missing_count": len(missing),
        "deploy_supported_count": len(supported),
        "ibm_profile": ibm_nmon_profile(),
        "items": items[:200],
        "read_only_mode": False,
    }


def ibm_nmon_profile() -> dict[str, Any]:
    return {
        "source": "IBM nmon command guidance",
        "record_command": IBM_NMON_RECORD_COMMAND,
        "equivalent_command": IBM_NMON_EQUIVALENT_COMMAND,
        "interval_sec": IBM_NMON_INTERVAL_SEC,
        "snapshot_count": IBM_NMON_SNAPSHOT_COUNT,
        "duration_hours": round(IBM_NMON_INTERVAL_SEC * IBM_NMON_SNAPSHOT_COUNT / 3600, 1),
        "output_dir": IBM_NMON_OUTPUT_DIR,
        "collector_script": IBM_NMON_COLLECT_SCRIPT,
        "cron_file": IBM_NMON_CRON_FILE,
        "cron_schedule": "05 00 * * *",
        "disk_busy_warn_pct": IBM_NMON_DISK_BUSY_WARN_PCT,
        "notes": [
            "以 IBM 文件的 recording mode 為主，產出 .nmon raw file 後再匯入月報。",
            "使用 IBM -x 容量規劃模式；等同 -ft -s 900 -c 96。",
            "每日一份 24 小時檔案，15 分鐘一筆，共 96 筆，適合容量與月報趨勢。",
            "不要用 kill 強制結束 nmon，以免檔案不完整。",
        ],
    }


def nmon_deploy_plan(limit: int = 20) -> dict[str, Any]:
    hosts = list_hosts(page=1, page_size=limit)["items"]
    plan = []
    for host in hosts:
        item = _nmon_host_status(host)
        if not item["deploy_supported"]:
            continue
        item["action"] = "install_nmon" if item["install_status"] == "缺少" else "verify_only"
        plan.append(item)
    return {
        "status": "planned",
        "mode": "dry-run",
        "read_only": False,
        "count": len(plan),
        "ibm_profile": ibm_nmon_profile(),
        "steps": [
            "check command -v nmon",
            "install nmon package when missing",
            f"create {IBM_NMON_OUTPUT_DIR}",
            f"install collector script: {IBM_NMON_COLLECT_SCRIPT}",
            f"schedule daily recording in {IBM_NMON_CRON_FILE}: {IBM_NMON_RECORD_COMMAND} ({IBM_NMON_EQUIVALENT_COMMAND})",
            "verify command -v nmon again",
        ],
        "items": plan,
    }


def _nmon_check_command() -> str:
    return "command -v nmon >/dev/null 2>&1 && nmon -V 2>&1 | head -1 || true"


def _nmon_host_status(host: dict[str, Any]) -> dict[str, Any]:
    host_type = str(host.get("host_type") or "").lower()
    connection = str(host.get("connection") or "").lower()
    target = host.get("primary_ip") or host.get("ip") or host.get("hostname")
    supported = host_type == "linux" and connection in {"ssh", "local", "ansible", ""}
    base = {
        "asset_seq": host.get("asset_seq"),
        "hostname": host.get("hostname"),
        "primary_ip": target,
        "host_type": host_type or "-",
        "connection": connection or "-",
        "interval_min": IBM_NMON_INTERVAL_SEC // 60,
        "snapshot_count": IBM_NMON_SNAPSHOT_COUNT,
        "record_command": IBM_NMON_RECORD_COMMAND,
        "nmon_enabled": bool(host.get("nmon_enabled")),
        "deploy_supported": supported,
        "install_status": "不支援",
        "version": "",
        "message": "目前只支援 Linux SSH/本機 Ansible 派送；AIX/Windows/AS400 需後續 runner。",
    }
    if not supported:
        return base
    if not target:
        return {**base, "install_status": "失敗", "message": "缺少 IP 或 hostname，無法檢查。"}
    if connection == "local":
        completed = subprocess.run(_nmon_check_command(), shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
    else:
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
                f"{host.get('ssh_user') or account_for_tier('L1', 'sysinfra')}@{target}",
                _nmon_check_command(),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
        )
    version = (completed.stdout or "").strip().splitlines()
    if completed.returncode != 0:
        return {**base, "install_status": "失敗", "message": (completed.stderr or "檢查失敗").strip()[:180]}
    if version:
        return {**base, "install_status": "已安裝", "version": version[0][:120], "message": "主機已可執行 nmon。"}
    return {**base, "install_status": "缺少", "message": "主機可連線，但找不到 nmon 指令。"}


def _ansible_inventory_for(hosts: list[dict[str, Any]], target: Path) -> list[dict[str, Any]]:
    lines = ["[nmon_targets]"]
    selected = []
    for host in hosts:
        status = _nmon_host_status(host)
        if not status["deploy_supported"] or status["install_status"] != "缺少":
            continue
        hostname = str(host.get("hostname") or host.get("asset_seq") or status["primary_ip"]).replace(" ", "_")
        address = status["primary_ip"]
        if not address:
            continue
        if str(host.get("connection") or "").lower() == "local":
            lines.append(f"{hostname} ansible_connection=local")
        else:
            user = host.get("ssh_user") or account_for_tier("L1", "sysinfra")
            port = host.get("ssh_port") or 22
            lines.append(f"{hostname} ansible_host={address} ansible_user={user} ansible_port={port}")
        selected.append({**status, "inventory_name": hostname})
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return selected


def deploy_nmon_with_ansible(limit: int = 100, user: str = "system") -> dict[str, Any]:
    hosts = list_hosts(page=1, page_size=limit)["items"]
    run_id = datetime.now(timezone.utc).astimezone().strftime("nmon-deploy-%Y%m%d%H%M%S")
    run_dir = Path(config.TMP_DIR) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    inventory = run_dir / "inventory.ini"
    selected = _ansible_inventory_for(hosts, inventory)
    playbook = Path(config.INSPECTION_HOME) / "ansible" / "playbooks" / "install_nmon.yml"
    result: dict[str, Any] = {
        "status": "skipped" if not selected else "running",
        "run_id": run_id,
        "requested_by": user,
        "count": len(selected),
        "inventory": str(inventory),
        "playbook": str(playbook),
        "ibm_profile": ibm_nmon_profile(),
        "items": selected,
        "stdout": "",
        "stderr": "",
        "rc": 0,
        "verified": [],
    }
    if not selected:
        result["message"] = "沒有缺少 nmon 且可由 Ansible 派送的 Linux 主機。"
        get_collection("nmon_deploy_runs").insert_one({**result, "created_at": datetime.now(timezone.utc)})
        return result
    if not playbook.exists():
        result.update({"status": "failed", "rc": 2, "stderr": f"playbook not found: {playbook}"})
        get_collection("nmon_deploy_runs").insert_one({**result, "created_at": datetime.now(timezone.utc)})
        return result
    completed = subprocess.run(
        ["ansible-playbook", "-i", str(inventory), str(playbook)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=900,
    )
    verified = [_nmon_host_status(host) for host in hosts if any(item["asset_seq"] == host.get("asset_seq") for item in selected)]
    result.update(
        {
            "status": "ok" if completed.returncode == 0 else "failed",
            "rc": completed.returncode,
            "stdout": completed.stdout[-12000:],
            "stderr": completed.stderr[-8000:],
            "verified": verified,
        }
    )
    get_collection("nmon_deploy_runs").insert_one({**result, "created_at": datetime.now(timezone.utc)})
    return result
