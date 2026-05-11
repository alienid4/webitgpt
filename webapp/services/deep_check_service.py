from __future__ import annotations

import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from webapp import config
from webapp.services.host_service import list_hosts
from webapp.services.mongo_service import get_collection
from webapp.services.remedy_kb import match_remedies


REPORT_RE = re.compile(r"^ts_[\w\-.]+_\d{8}_\d{6}_(summary|detail)\.txt$")


FACE_SPECS = [
    (1, "效能", "uptime && top -bn1 | head -5 && free -m", "CPU idle > 30%，Swap < 50%"),
    (2, "頻寬", "ip -s link; ss -s; ping -c 3 ${PING_TGT:-127.0.0.1}", "NIC 無 error/drop，TCP 狀態正常"),
    (3, "AP listener", "ss -ltnp; systemctl --failed --no-pager || true", "必要 AP port 有 listener"),
    (4, "AP 健康檢查", "ss -ltnp; curl -fsS http://127.0.0.1:${AP_PORT:-8002}/health || true", "健康檢查 port 回應正常"),
    (5, "Session", "ss -tan | awk 'NR>1 {print $1}' | sort | uniq -c | sort -nr", "連線狀態無異常集中"),
    (6, "Storage", "df -h; df -i; df -h /tmp 2>/dev/null || true", "磁碟與 inode 未超過 85%"),
    (7, "時間與憑證", "timedatectl; chronyc tracking 2>/dev/null || ntpq -p 2>/dev/null || true", "時間同步正常，憑證未接近到期"),
    (8, "DB", "ps -ef | egrep 'tnslsnr|oracle|sqlservr|mysqld|mariadbd|db2sysc|postgres|mongod' | grep -v grep || true; ss -ltnp | egrep '1521|1433|3306|50000|5432|27017' || true", "DB process 與 port 狀態符合主機角色"),
    (9, "Infra", "dmesg -T | egrep -i 'oom|mce|machine check' | tail -20 || true; systemctl --failed --no-pager || true; cat /proc/sys/kernel/tainted 2>/dev/null || true", "無 OOM、MCE、failed unit 或 kernel tainted 異常"),
    (10, "運維軌跡", "last -n 10; find /etc /opt -xdev -mtime -1 -type f 2>/dev/null | head -30", "近期登入與異動可追溯"),
]


def meta() -> dict[str, Any]:
    return {
        "controller_hostname": _controller_hostname(),
        "role": "L3 on-demand deep check",
        "faces": [{"idx": idx, "name": name} for idx, name, _, _ in FACE_SPECS],
        "timeout_seconds": 300,
        "storage": "per-host data/hosts/<asset_seq>/deep_check",
    }


def run(hostname: str, user: str = "system") -> dict[str, Any]:
    hostname = (hostname or "").strip()
    if not hostname:
        return {"success": False, "error": "缺少 hostname"}
    host = _get_host_by_hostname(hostname)
    if not host:
        return {"success": False, "error": f"找不到主機: {hostname}"}
    if host.get("host_type") != "linux":
        return {"success": False, "error": f"目前深度檢查只支援 Linux 主機: {hostname}"}
    if host.get("status") in {"disabled", "retired"}:
        return {"success": False, "error": f"主機已停用: {hostname}"}

    running = get_collection("deep_check_jobs").find_one({"status": {"$in": ["starting", "running"]}}, {"_id": 0})
    if running:
        return {"success": False, "error": "已有深度檢查正在執行", "job_id": running["job_id"]}

    now = datetime.now(timezone.utc)
    job_ts = now.strftime("%Y%m%d_%H%M%S")
    job_id = f"dc_{job_ts}_{uuid.uuid4().hex[:6]}"
    job = {
        "job_id": job_id,
        "status": "starting",
        "hostname": hostname,
        "asset_seq": host["asset_seq"],
        "host_ip_map": {hostname: host.get("ip")},
        "target_hosts": [hostname],
        "job_ts": job_ts,
        "started_at": now,
        "finished_at": None,
        "phase": "建立 job",
        "progress": 0,
        "total": 1,
        "completed": 0,
        "created_by": user,
        "log": "",
        "report_files": {},
    }
    get_collection("deep_check_jobs").insert_one(job)
    try:
        _execute(job, host)
    except Exception as exc:
        get_collection("deep_check_jobs").update_one(
            {"job_id": job_id},
            {"$set": {"status": "error", "error": str(exc), "finished_at": datetime.now(timezone.utc), "phase": "執行失敗"}},
        )
    return {"success": True, "job_id": job_id, "message": f"深度檢查已完成: {hostname}", "hostname": hostname}


def progress(job_id: str) -> dict[str, Any]:
    job = get_collection("deep_check_jobs").find_one({"job_id": job_id}, {"_id": 0})
    if not job:
        return {"success": False, "error": "job not found"}
    return {
        "success": True,
        "job_id": job_id,
        "job_status": job.get("status"),
        "phase": job.get("phase"),
        "total": job.get("total", 1),
        "completed": job.get("completed", 0),
        "hosts": [{"hostname": job.get("hostname"), "ip": (job.get("host_ip_map") or {}).get(job.get("hostname")), "status": job.get("status")}],
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "is_finished": job.get("status") in {"done", "error", "timeout", "canceled"},
        "log": (job.get("log") or "")[-5000:],
        "report_files": job.get("report_files", {}),
        "progress": job.get("progress", 0),
        "error": job.get("error"),
    }


def cancel(job_id: str, user: str = "system") -> dict[str, Any]:
    result = get_collection("deep_check_jobs").update_one(
        {"job_id": job_id, "status": {"$in": ["starting", "running"]}},
        {"$set": {"status": "canceled", "finished_at": datetime.now(timezone.utc), "phase": "使用者取消", "canceled_by": user}},
    )
    return {"success": bool(result.modified_count), "job_id": job_id}


def history(hostname: str, limit: int = 20) -> dict[str, Any]:
    rows = list(get_collection("deep_check_jobs").find({"hostname": hostname}, {"_id": 0}).sort("started_at", -1).limit(limit))
    return {"success": True, "hostname": hostname, "items": rows}


def reports(hostname: str) -> dict[str, Any]:
    rows = list(get_collection("deep_check_reports").find({"hostname": hostname}, {"_id": 0}).sort("timestamp", -1))
    return {"success": True, "hostname": hostname, "items": rows}


def preview(filename: str) -> dict[str, Any]:
    path = _report_path(filename)
    return {"success": True, "filename": filename, "content": path.read_text(encoding="utf-8", errors="replace")}


def parsed(filename: str) -> dict[str, Any]:
    report = get_collection("deep_check_reports").find_one({"filename": filename}, {"_id": 0})
    if not report:
        return {"success": False, "error": "report not found"}
    return {"success": True, "filename": filename, "data": report.get("parsed", {})}


def download_path(filename: str) -> Path:
    return _report_path(filename)


def _execute(job: dict[str, Any], host: dict[str, Any]) -> None:
    job_id = job["job_id"]
    get_collection("deep_check_jobs").update_one({"job_id": job_id}, {"$set": {"status": "running", "phase": "執行 9 面向檢查", "progress": 10}})
    items = []
    detail_lines = []
    for idx, name, cmd, baseline in FACE_SPECS:
        rc, out, err = _run_command(host, cmd)
        text = out or err or "無輸出"
        verdict = _verdict(idx, rc, text)
        item = {
            "idx": idx,
            "name": name,
            "level": verdict.lower(),
            "verdict": verdict,
            "range": f"{name} 深度檢查",
            "cmd": cmd,
            "baseline": baseline,
            "actual": text[:1000],
            "impact": _impact(verdict, name, text),
            "action": "PASS 無需處置" if verdict in {"PASS", "N/A"} else "請依 Remedy KB 進行人工確認",
        }
        item["remedies"] = match_remedies(item)
        items.append(item)
        detail_lines.append(_format_item(item, text))
        get_collection("deep_check_jobs").update_one({"job_id": job_id}, {"$set": {"phase": f"{name} 完成", "progress": min(95, idx * 10)}})

    parsed_data = _parsed_data(host, job["job_ts"], items)
    summary_text = _summary_text(parsed_data)
    detail_text = "\n\n".join(detail_lines)
    summary_file, detail_file = _write_reports(host, job["job_ts"], summary_text, detail_text)
    report_doc = {
        "hostname": host["hostname"],
        "asset_seq": host["asset_seq"],
        "timestamp": datetime.now(timezone.utc),
        "filename": summary_file.name,
        "summary_filename": summary_file.name,
        "detail_filename": detail_file.name,
        "path": str(summary_file),
        "detail_path": str(detail_file),
        "parsed": parsed_data,
    }
    get_collection("deep_check_reports").update_one({"filename": summary_file.name}, {"$set": report_doc}, upsert=True)
    get_collection("deep_check_jobs").update_one(
        {"job_id": job_id},
        {
            "$set": {
                "status": "done",
                "phase": "完成",
                "progress": 100,
                "completed": 1,
                "finished_at": datetime.now(timezone.utc),
                "returncode": 0,
                "report_files": {"summary": summary_file.name, "detail": detail_file.name},
                "log": detail_text[-5000:],
            }
        },
    )


def _run_command(host: dict[str, Any], cmd: str) -> tuple[int, str, str]:
    if host.get("connection") == "local":
        completed = subprocess.run(cmd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        return completed.returncode, completed.stdout.strip(), completed.stderr.strip()
    target = host.get("ip") or host.get("hostname")
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
    completed = subprocess.run(ssh_cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=38)
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def _verdict(idx: int, rc: int, text: str) -> str:
    lowered = text.lower()
    if rc != 0:
        return "WARN"
    if idx == 6 and re.search(r"\s(9[0-9]|100)%", text):
        return "WARN"
    if idx == 9 and any(token in lowered for token in ("oom", "failed", "machine check")):
        return "WARN"
    return "PASS"


def _impact(verdict: str, name: str, text: str) -> str:
    if verdict == "PASS":
        return "目前未看到明顯客戶影響。"
    sample = " ".join(text.split())[:160]
    return f"{name} 出現警示，可能造成服務延遲、timeout 或維運風險。摘要: {sample}"


def _format_item(item: dict[str, Any], raw: str) -> str:
    return "\n".join(
        [
            f"[{item['idx']}/9] {item['name']} {item['verdict']}",
            f"  檢查項目   : {item['range']}",
            f"  檢查指令   : {item['cmd']}",
            f"  通過基準   : {item['baseline']}",
            f"  實際結果   : {item['actual']}",
            f"  判斷說明   : {item['impact']}",
            f"  客戶影響   : {item['impact']}",
            f"  Remedy     : {item['action']}",
            "",
            raw,
        ]
    )


def _parsed_data(host: dict[str, Any], job_ts: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    stats = {
        "pass": sum(1 for item in items if item["verdict"] == "PASS"),
        "warn": sum(1 for item in items if item["verdict"] == "WARN"),
        "fail": sum(1 for item in items if item["verdict"] == "FAIL"),
        "na": sum(1 for item in items if item["verdict"] == "N/A"),
    }
    status_level = "fail" if stats["fail"] else "warn" if stats["warn"] else "pass"
    status = "客戶影響" if status_level == "fail" else "警示" if status_level == "warn" else "正常"
    return {
        "hostname": host["hostname"],
        "asset_seq": host["asset_seq"],
        "timestamp": job_ts,
        "os": host.get("os") or host.get("os_version") or host.get("host_type"),
        "ap_port": "-",
        "ping_target": "127.0.0.1",
        "status": status,
        "status_level": status_level,
        "stats": stats,
        "customer_impact": "；".join(item["impact"] for item in items if item["verdict"] in {"WARN", "FAIL"})[:800] or "目前未看到明顯客戶影響。",
        "items": items,
    }


def _summary_text(data: dict[str, Any]) -> str:
    lines = [
        f"深度檢查摘要 - {data['hostname']}",
        f"時間: {data['timestamp']}",
        f"狀態: {data['status']}",
        f"PASS={data['stats']['pass']} WARN={data['stats']['warn']} FAIL={data['stats']['fail']} N/A={data['stats']['na']}",
        f"客戶影響: {data['customer_impact']}",
        "",
    ]
    for item in data["items"]:
        lines.append(f"{item['idx']}. {item['name']} {item['verdict']} - {item['impact']}")
    return "\n".join(lines)


def _write_reports(host: dict[str, Any], job_ts: str, summary: str, detail: str) -> tuple[Path, Path]:
    host_dir = Path(config.HOSTS_DIR) / host["asset_seq"] / "deep_check"
    host_dir.mkdir(parents=True, exist_ok=True)
    hostname = re.sub(r"[^\w\-.]", "_", host["hostname"])
    short_ts = job_ts
    summary_name = f"ts_{hostname}_{short_ts}_summary.txt"
    detail_name = f"ts_{hostname}_{short_ts}_detail.txt"
    summary_path = host_dir / summary_name
    detail_path = host_dir / detail_name
    summary_path.write_text(summary, encoding="utf-8")
    detail_path.write_text(detail, encoding="utf-8")
    return summary_path, detail_path


def _report_path(filename: str) -> Path:
    if not REPORT_RE.match(filename):
        raise FileNotFoundError("invalid report filename")
    report = get_collection("deep_check_reports").find_one({"$or": [{"summary_filename": filename}, {"detail_filename": filename}]}, {"_id": 0})
    if not report:
        raise FileNotFoundError(filename)
    path = Path(report["path"] if report.get("summary_filename") == filename else report["detail_path"])
    if not path.exists():
        raise FileNotFoundError(filename)
    return path


def _controller_hostname() -> str:
    try:
        completed = subprocess.run("hostname", shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3)
        return completed.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _get_host_by_hostname(hostname: str) -> Optional[dict[str, Any]]:
    for host in list_hosts(page=1, page_size=10000)["items"]:
        if host.get("hostname") == hostname:
            return host
    return None
