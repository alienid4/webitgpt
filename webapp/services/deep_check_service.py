from __future__ import annotations

import os
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
    {
        "idx": 1,
        "name": "效能",
        "cmd": "uptime; top -bn1 | head -5; free -m; vmstat 1 3",
        "baseline": "CPU idle 大於 30%，Swap 使用率低於 50%，load 不高於 CPU 核心數 2 倍。",
        "warn_patterns": ["load average"],
    },
    {
        "idx": 2,
        "name": "網路",
        "cmd": "ip -s link; ss -s; ping -c 3 ${PING_TGT:-127.0.0.1}; sysctl net.netfilter.nf_conntrack_count net.netfilter.nf_conntrack_max 2>/dev/null || true",
        "baseline": "網卡無大量 error/drop，TCP 狀態正常，ping 無明顯 loss。",
        "warn_patterns": ["retrans", "drop", "errors", "loss"],
    },
    {
        "idx": 3,
        "name": "AP Listener",
        "cmd": "ss -ltnp 2>/dev/null | head -80; ps -eo pid,comm,%cpu,%mem --sort=-%cpu | head -12; systemctl --failed --no-pager || true",
        "baseline": "AP listener 存在，程序資源合理，systemd 無 failed unit。",
        "warn_patterns": ["failed"],
    },
    {
        "idx": 4,
        "name": "AP 連線",
        "cmd": "ss -ltnp 2>/dev/null | egrep ':(${AP_PORT:-8002})\\b' || true; curl -fsS --max-time 5 http://127.0.0.1:${AP_PORT:-8002}/health || true",
        "baseline": "指定 AP port 可連線，health endpoint 回應正常。",
        "warn_patterns": ["failed", "refused", "timeout", "not found"],
    },
    {
        "idx": 5,
        "name": "Session",
        "cmd": "ss -tan | awk 'NR>1 {print $1}' | sort | uniq -c | sort -nr; ss -tan state established | awk 'NR>1 {print $5}' | cut -d: -f1 | sort | uniq -c | sort -nr | head",
        "baseline": "TCP session 分布合理，沒有大量 CLOSE_WAIT / SYN_RECV。",
        "warn_patterns": ["CLOSE-WAIT", "SYN-RECV"],
    },
    {
        "idx": 6,
        "name": "Storage",
        "cmd": "df -h; df -i; df -h /tmp 2>/dev/null || true; journalctl --disk-usage 2>/dev/null || true",
        "baseline": "磁碟與 inode 使用率低於 85%，/tmp 空間足夠。",
        "warn_patterns": [],
    },
    {
        "idx": 7,
        "name": "時間與憑證",
        "cmd": "date; timedatectl 2>/dev/null || true; chronyc tracking 2>/dev/null || ntpq -p 2>/dev/null || true; find /etc/pki /opt -name '*.crt' -o -name '*.pem' 2>/dev/null | head -20",
        "baseline": "時間同步正常，憑證未在 30 天內到期。",
        "warn_patterns": ["not synchronized", "unsynchronized"],
    },
    {
        "idx": 8,
        "name": "資料庫",
        "cmd": "ps -ef | egrep 'tnslsnr|oracle|sqlservr|mysqld|mariadbd|db2sysc|postgres|mongod' | grep -v grep || true; ss -ltnp 2>/dev/null | egrep '1521|1433|3306|50000|5432|27017' || true",
        "baseline": "DB process 與常見 port 狀態符合主機用途。",
        "warn_patterns": [],
    },
    {
        "idx": 9,
        "name": "Infra",
        "cmd": "dmesg -T 2>/dev/null | egrep -i 'oom|mce|machine check' | tail -20 || true; systemctl --failed --no-pager || true; cat /proc/sys/kernel/tainted 2>/dev/null || true",
        "baseline": "無 OOM / MCE / failed unit，kernel tainted 為 0。",
        "warn_patterns": ["oom", "machine check", "failed"],
    },
    {
        "idx": 10,
        "name": "運維軌跡",
        "cmd": "last -n 10; find /etc /opt -xdev -mtime -1 -type f 2>/dev/null | head -30; journalctl --since '24 hours ago' 2>/dev/null | egrep -i 'started|stopped|restart|failed' | tail -40 || true",
        "baseline": "近期登入、設定異動與服務啟停都有可追溯紀錄。",
        "warn_patterns": ["failed"],
    },
]


def meta() -> dict[str, Any]:
    return {
        "controller_hostname": _controller_hostname(),
        "role": "L3 on-demand deep check",
        "faces": [{"idx": item["idx"], "name": item["name"], "baseline": item["baseline"]} for item in FACE_SPECS],
        "timeout_seconds": 300,
        "storage": "per-host data/hosts/<asset_seq>/deep_check",
        "job_store": "mongo deep_check_jobs",
    }


def run(hostname: str, user: str = "system") -> dict[str, Any]:
    hostname = (hostname or "").strip()
    if not hostname:
        return {"success": False, "error": "缺少 hostname"}
    host = _get_host_by_hostname(hostname)
    if not host:
        return {"success": False, "error": f"找不到主機：{hostname}"}
    if host.get("host_type") != "linux":
        return {"success": False, "error": f"目前 L3 深度檢查只支援 Linux 主機：{hostname}"}
    if host.get("status") in {"disabled", "retired"}:
        return {"success": False, "error": f"主機狀態不允許檢查：{hostname}"}

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
        "phase": "建立工作",
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
        return {"success": False, "error": str(exc), "job_id": job_id, "hostname": hostname}
    return {"success": True, "job_id": job_id, "message": f"L3 深度檢查已完成：{hostname}", "hostname": hostname}


def progress(job_id: str) -> dict[str, Any]:
    job = get_collection("deep_check_jobs").find_one({"job_id": job_id}, {"_id": 0})
    if not job:
        return {"success": False, "error": "job not found"}
    hostname = job.get("hostname")
    return {
        "success": True,
        "job_id": job_id,
        "job_status": job.get("status"),
        "phase": job.get("phase"),
        "total": job.get("total", 1),
        "completed": job.get("completed", 0),
        "hosts": [{"hostname": hostname, "ip": (job.get("host_ip_map") or {}).get(hostname), "status": job.get("status")}],
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
        {"$set": {"status": "canceled", "finished_at": datetime.now(timezone.utc), "phase": "已取消", "canceled_by": user}},
    )
    return {"success": bool(result.modified_count), "job_id": job_id}


def history(hostname: str, limit: int = 20) -> dict[str, Any]:
    query = {"hostname": hostname} if hostname else {}
    rows = list(get_collection("deep_check_jobs").find(query, {"_id": 0}).sort("started_at", -1).limit(limit))
    return {"success": True, "hostname": hostname, "items": rows}


def reports(hostname: str) -> dict[str, Any]:
    query = {"hostname": hostname} if hostname else {}
    rows = list(get_collection("deep_check_reports").find(query, {"_id": 0}).sort("timestamp", -1).limit(100))
    return {"success": True, "hostname": hostname, "items": rows}


def latest_report(hostname: str) -> Optional[dict[str, Any]]:
    return get_collection("deep_check_reports").find_one({"hostname": hostname}, {"_id": 0}, sort=[("timestamp", -1)])


def preview(filename: str) -> dict[str, Any]:
    path = _report_path(filename)
    return {"success": True, "filename": filename, "content": path.read_text(encoding="utf-8", errors="replace")}


def parsed(filename: str) -> dict[str, Any]:
    report = get_collection("deep_check_reports").find_one(
        {"$or": [{"filename": filename}, {"summary_filename": filename}, {"detail_filename": filename}]},
        {"_id": 0},
    )
    if not report:
        return {"success": False, "error": "report not found"}
    return {"success": True, "filename": filename, "data": report.get("parsed", {})}


def download_path(filename: str) -> Path:
    return _report_path(filename)


def _execute(job: dict[str, Any], host: dict[str, Any]) -> None:
    job_id = job["job_id"]
    get_collection("deep_check_jobs").update_one({"job_id": job_id}, {"$set": {"status": "running", "phase": "執行 9 面向檢查", "progress": 5}})
    items = []
    detail_lines = []
    for spec in FACE_SPECS:
        idx = int(spec["idx"])
        rc, out, err = _run_command(host, str(spec["cmd"]))
        raw = out or err or "無輸出"
        verdict = _verdict(spec, rc, raw)
        item = {
            "idx": idx,
            "name": spec["name"],
            "level": verdict.lower(),
            "verdict": verdict,
            "range": f"{spec['name']} 深度診斷",
            "cmd": spec["cmd"],
            "returncode": rc,
            "baseline": spec["baseline"],
            "actual": raw[:1200],
            "evidence": _evidence_summary(spec, rc, raw, verdict),
            "problem": _problem_summary(spec, rc, raw, verdict),
            "threshold": _threshold_summary(spec, raw),
            "recommendation": _recommendation(spec, verdict, raw),
            "action": "持續觀察" if verdict in {"PASS", "N/A"} else "依 Remedy KB 確認風險、備份與修復步驟",
        }
        item["impact"] = _impact(verdict, spec["name"], item["evidence"])
        item["remedies"] = match_remedies(item)
        items.append(item)
        detail_lines.append(_format_item(item, raw))
        progress_pct = min(95, 5 + idx * 9)
        get_collection("deep_check_jobs").update_one({"job_id": job_id}, {"$set": {"phase": f"{spec['name']} 完成", "progress": progress_pct, "log": "\n\n".join(detail_lines)[-5000:]}})

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
    env_cmd = f"AP_PORT={os.environ.get('AP_PORT', str(config.WEB_PORT))} {cmd}"
    if host.get("connection") == "local":
        completed = subprocess.run(env_cmd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=35)
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
        env_cmd,
    ]
    completed = subprocess.run(ssh_cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def _verdict(spec: dict[str, Any], rc: int, text: str) -> str:
    lowered = text.lower()
    if int(spec["idx"]) == 2:
        return _network_verdict(rc, text)
    if int(spec["idx"]) == 3:
        return _ap_listener_verdict(rc, text)
    if int(spec["idx"]) == 5:
        return _session_verdict(rc, text)
    if int(spec["idx"]) == 9:
        return _infra_verdict(rc, text)
    if rc != 0 and int(spec["idx"]) not in {4, 8, 10}:
        return "WARN"
    if int(spec["idx"]) == 6 and re.search(r"\s(8[5-9]|9[0-9]|100)%", text):
        return "WARN"
    if int(spec["idx"]) == 9 and any(token in lowered for token in ("oom", "machine check")):
        return "WARN"
    for token in spec.get("warn_patterns", []):
        if token.lower() in lowered and int(spec["idx"]) in {2, 3, 4, 5, 7, 9, 10}:
            return "WARN"
    return "PASS"


def _ap_listener_verdict(rc: int, text: str) -> str:
    if rc != 0:
        return "WARN"
    if _systemd_failed_issue_lines(text):
        return "WARN"
    if "listen" not in text.lower():
        return "WARN"
    return "PASS"


def _session_verdict(rc: int, text: str) -> str:
    if rc != 0:
        return "WARN"
    counts = _tcp_state_counts(text)
    if counts.get("SYN-RECV", 0) > 0:
        return "WARN"
    if counts.get("CLOSE-WAIT", 0) >= 10:
        return "WARN"
    if counts.get("ESTAB", 0) >= 500:
        return "WARN"
    return "PASS"


def _infra_verdict(rc: int, text: str) -> str:
    lowered = text.lower()
    if rc != 0:
        return "WARN"
    if any(token in lowered for token in ("oom", "machine check")):
        return "WARN"
    if _systemd_failed_issue_lines(text):
        return "WARN"
    tainted = _kernel_tainted_value(text)
    if tainted and tainted != "0":
        return "WARN"
    return "PASS"


def _network_verdict(rc: int, text: str) -> str:
    lowered = text.lower()
    if rc != 0:
        return "WARN"
    if any(
        token in lowered
        for token in [
            "no route to host",
            "network is unreachable",
            "connection timed out",
            "temporary failure in name resolution",
        ]
    ):
        return "WARN"

    loss_match = re.search(r"(\d+(?:\.\d+)?)%\s+packet loss", lowered)
    if loss_match and float(loss_match.group(1)) > 0:
        return "WARN"

    if _link_error_or_drop_seen(text):
        return "WARN"
    if _tcp_retransmit_seen(text):
        return "WARN"
    return "PASS"


def _link_error_or_drop_seen(text: str) -> bool:
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        headers = line.lower().split()
        if not headers or headers[0].rstrip(":") not in {"rx", "tx"}:
            continue
        if not any(header in headers for header in ["errors", "dropped", "drop", "carrier", "collsns", "overruns"]):
            continue
        if idx + 1 >= len(lines):
            continue
        values = [int(value) for value in re.findall(r"\b\d+\b", lines[idx + 1])]
        if not values:
            continue
        value_headers = [header.rstrip(":") for header in headers[1:]]
        for pos, normalized in enumerate(value_headers):
            if normalized in {"errors", "dropped", "drop", "carrier", "collsns", "overruns"} and pos < len(values) and values[pos] > 0:
                return True
    return False


def _tcp_retransmit_seen(text: str) -> bool:
    lowered = text.lower()
    patterns = [
        r"\b(\d+)\s+segments?\s+retransm",
        r"\bretrans(?:mitted|mits|mission)?\D+(\d+)",
        r"\b(\d+)\s+listen(?:ing)?\s+drops?",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, lowered):
            if int(match.group(1)) > 0:
                return True
    return False


def _tcp_state_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in text.splitlines():
        match = re.match(r"\s*(\d+)\s+([A-Z-]+)\s*$", line)
        if match:
            counts[match.group(2).upper()] = int(match.group(1))
    return counts


def _systemd_failed_issue_lines(text: str) -> list[str]:
    issues: list[str] = []
    for line in text.splitlines():
        cleaned = line.strip()
        lowered = cleaned.lower()
        if not cleaned or cleaned.startswith("UNIT ") or "0 loaded units listed" in lowered:
            continue
        if re.search(r"\bloaded\s+failed\s+failed\b", lowered) or re.search(r"\bfailed\b", lowered):
            issues.append(cleaned[:240])
    return issues


def _kernel_tainted_value(text: str) -> str:
    for line in reversed(text.splitlines()):
        cleaned = line.strip()
        if re.fullmatch(r"\d+", cleaned):
            return cleaned
    return ""


def _impact(verdict: str, name: str, text: str) -> str:
    if verdict == "PASS":
        return "未發現明顯影響，維持例行觀察。"
    sample = " ".join(text.split())[:180]
    return f"{name} 發現警示訊號，可能影響服務穩定、連線品質或維運可追溯性。摘要：{sample}"


def _problem_summary(spec: dict[str, Any], rc: int, text: str, verdict: str) -> str:
    idx = int(spec["idx"])
    if verdict == "PASS":
        if idx == 3:
            return "AP listener 有偵測到 LISTEN，且未發現 systemd failed unit。"
        if idx == 5:
            counts = _tcp_state_counts(text)
            return (
                f"TCP 狀態在門檻內：SYN-RECV={counts.get('SYN-RECV', 0)}、"
                f"CLOSE-WAIT={counts.get('CLOSE-WAIT', 0)}、ESTAB={counts.get('ESTAB', 0)}。"
            )
        if idx == 9:
            return "未發現 OOM/MCE、failed unit 或 kernel tainted 異常。"
        return "未超過警示門檻。"
    if rc != 0:
        return f"命令回傳碼 rc={rc}，代表採集或檢查命令執行異常。"
    if idx == 2:
        issues = _network_counter_issue_lines(text)
        loss_match = re.search(r"(\d+(?:\.\d+)?)%\s+packet loss", text.lower())
        if issues:
            return "網路介面 counter 有非 0 異常值：" + "；".join(line for line in issues if line.startswith("異常 counter"))
        if loss_match and float(loss_match.group(1)) > 0:
            return f"Ping packet loss={loss_match.group(1)}%，高於 0% 門檻。"
    if idx == 3:
        issues = _systemd_failed_issue_lines(text)
        if issues:
            return "AP 主機存在 failed unit：" + "；".join(issues[:3])
        return "未找到 LISTEN 服務或 AP listener 輸出異常。"
    if idx == 5:
        counts = _tcp_state_counts(text)
        if counts.get("SYN-RECV", 0) > 0:
            return f"SYN-RECV={counts.get('SYN-RECV')}，門檻為 0。"
        if counts.get("CLOSE-WAIT", 0) >= 10:
            return f"CLOSE-WAIT={counts.get('CLOSE-WAIT')}，門檻為小於 10。"
        if counts.get("ESTAB", 0) >= 500:
            return f"ESTAB={counts.get('ESTAB')}，門檻為小於 500。"
    if idx == 9:
        issues = _systemd_failed_issue_lines(text)
        if issues:
            return "Infra failed unit：" + "；".join(issues[:3])
        tainted = _kernel_tainted_value(text)
        if tainted and tainted != "0":
            return f"kernel tainted={tainted}，門檻為 0。"
    return "命中警示條件，請查看證據摘要確認異常數值。"


def _threshold_summary(spec: dict[str, Any], text: str) -> str:
    idx = int(spec["idx"])
    if idx == 3:
        return "需有 LISTEN 服務；systemd failed unit 必須為 0。"
    if idx == 5:
        return "SYN-RECV 必須為 0；CLOSE-WAIT 小於 10；ESTAB 小於 500。"
    if idx == 9:
        return "無 OOM / MCE / failed unit；kernel tainted 必須為 0。"
    return str(spec.get("baseline") or "")


def _recommendation(spec: dict[str, Any], verdict: str, text: str) -> str:
    if verdict == "PASS":
        return "維持例行觀察；不需立即處置。"
    idx = int(spec["idx"])
    if idx == 2:
        return "先確認異常網卡的 switch port、VM NIC、線路或虛擬化層狀態；修復前保留 ip -s link 與 ethtool 證據。"
    if idx == 3:
        return "確認 failed unit 是否與 AP 服務相關；先執行 systemctl status <unit> 與 journalctl -u <unit>，確認影響後再重啟。"
    if idx == 5:
        return "確認連線來源與應用 socket 釋放狀況；CLOSE_WAIT 偏高時先查應用 thread/連線池，不要直接重啟。"
    if idx == 9:
        return "針對 failed unit 執行 systemctl status 與 journalctl；若是 setroubleshootd，可確認 SELinux denial log 處理服務是否需要啟動或停用。"
    return "依 Remedy KB 先查證、備份與建立 rollback，再安排修復。"


def _evidence_summary(spec: dict[str, Any], rc: int, text: str, verdict: str) -> str:
    idx = int(spec["idx"])
    lines = [f"回傳碼 rc={rc}；判定={verdict}。"]
    if idx == 1:
        lines.extend(_matching_lines(text, [r"load average", r"^mem:", r"^swap:", r"%?cpu"], limit=4))
    elif idx == 2:
        lines.extend(_network_evidence(text))
    elif idx == 3:
        failed = _systemd_failed_issue_lines(text)
        if failed:
            lines.extend(failed[:5])
        else:
            lines.extend(_matching_lines(text, [r"listening|listen", r"0 loaded units listed|unit"], limit=5))
    elif idx == 4:
        lines.extend(_matching_lines(text, [r"status|ok|health|refused|failed|timeout|not found"], limit=5))
    elif idx == 5:
        lines.extend(_matching_lines(text, [r"estab|listen|close-wait|syn-recv|time-wait"], limit=6))
    elif idx == 6:
        lines.extend(_matching_lines(text, [r"filesystem|/dev/|tmpfs|journal"], limit=6))
    elif idx == 7:
        lines.extend(_matching_lines(text, [r"ntp|system clock|synchronized|rtc|\.crt|\.pem"], limit=6))
    elif idx == 8:
        lines.extend(_matching_lines(text, [r"oracle|sql|mysql|mariadb|postgres|mongod|1521|1433|3306|5432|27017"], limit=6))
    elif idx == 9:
        failed = _systemd_failed_issue_lines(text)
        if failed:
            lines.extend(failed[:5])
        else:
            lines.extend(_matching_lines(text, [r"oom|machine check|tainted|0 loaded units listed"], limit=6))
    elif idx == 10:
        lines.extend(_matching_lines(text, [r"logged|reboot|started|stopped|restart|failed"], limit=6))
    if len(lines) == 1:
        lines.extend(_first_nonempty_lines(text, limit=4))
    return "\n".join(lines[:8])


def _matching_lines(text: str, patterns: list[str], limit: int = 5) -> list[str]:
    compiled = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    found: list[str] = []
    for line in text.splitlines():
        cleaned = line.strip()
        if cleaned and any(pattern.search(cleaned) for pattern in compiled):
            found.append(cleaned[:220])
        if len(found) >= limit:
            break
    return found


def _first_nonempty_lines(text: str, limit: int = 4) -> list[str]:
    lines = []
    for line in text.splitlines():
        cleaned = line.strip()
        if cleaned:
            lines.append(cleaned[:220])
        if len(lines) >= limit:
            break
    return lines


def _network_evidence(text: str) -> list[str]:
    evidence = _matching_lines(text, [r"packet loss", r"retrans", r"listen.*drop", r"no route|unreachable|timed out"], limit=4)
    issue_lines = _network_counter_issue_lines(text)
    if issue_lines:
        return (evidence + issue_lines)[:8]

    lines = text.splitlines()
    for idx, line in enumerate(lines):
        cleaned = line.strip()
        lowered = cleaned.lower()
        if re.match(r"^\d+:\s+\S+:", cleaned):
            evidence.append(cleaned[:220])
        elif lowered.startswith(("rx:", "tx:")) or re.search(r"\b(errors|dropped|carrier|collsns|overruns)\b", lowered):
            evidence.append(cleaned[:220])
            if idx + 1 < len(lines):
                value_line = lines[idx + 1].strip()
                if value_line:
                    evidence.append(value_line[:220])
        if len(evidence) >= 7:
            break
    return evidence


def _network_counter_issue_lines(text: str) -> list[str]:
    lines = text.splitlines()
    current_iface = ""
    issues: list[str] = []
    for idx, line in enumerate(lines):
        cleaned = line.strip()
        iface_match = re.match(r"^\d+:\s+([^:]+):", cleaned)
        if iface_match:
            current_iface = cleaned
            continue

        headers = cleaned.lower().split()
        if not headers or headers[0].rstrip(":") not in {"rx", "tx"}:
            continue
        watched = {"errors", "dropped", "drop", "carrier", "collsns", "overruns"}
        if not any(header.rstrip(":") in watched for header in headers):
            continue
        if idx + 1 >= len(lines):
            continue

        value_line = lines[idx + 1].strip()
        values = [int(value) for value in re.findall(r"\b\d+\b", value_line)]
        triggered = []
        value_headers = [header.rstrip(":") for header in headers[1:]]
        for pos, normalized in enumerate(value_headers):
            if normalized in watched and pos < len(values) and values[pos] > 0:
                triggered.append(f"{normalized}={values[pos]}")
        if triggered:
            if current_iface:
                issues.append(current_iface[:220])
            issues.append(cleaned[:220])
            issues.append(value_line[:220])
            issues.append("異常 counter: " + ", ".join(triggered))
    return issues


def _format_item(item: dict[str, Any], raw: str) -> str:
    return "\n".join(
        [
            f"[{item['idx']}/9] {item['name']} {item['verdict']}",
            f"  檢查範圍   : {item['range']}",
            f"  檢查指令   : {item['cmd']}",
            f"  回傳碼     : {item['returncode']}",
            f"  判斷基準   : {item['baseline']}",
            f"  問題點     : {item.get('problem', '-')}",
            f"  警示門檻   : {item.get('threshold', item['baseline'])}",
            f"  證據摘要   : {item['evidence']}",
            f"  實際結果   : {item['actual']}",
            f"  影響說明   : {item['impact']}",
            f"  建議處置   : {item.get('recommendation') or item['action']}",
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
    status = "異常" if status_level == "fail" else "警示" if status_level == "warn" else "正常"
    impacts = [item["impact"] for item in items if item["verdict"] in {"WARN", "FAIL"}]
    return {
        "hostname": host["hostname"],
        "asset_seq": host["asset_seq"],
        "timestamp": job_ts,
        "os": host.get("os") or host.get("os_version") or host.get("host_type"),
        "ap_port": os.environ.get("AP_PORT", str(config.WEB_PORT)),
        "ping_target": os.environ.get("PING_TGT", "127.0.0.1"),
        "status": status,
        "status_level": status_level,
        "stats": stats,
        "customer_impact": "；".join(impacts)[:1000] if impacts else "未發現明顯服務影響。",
        "items": items,
    }


def _summary_text(data: dict[str, Any]) -> str:
    lines = [
        f"深度檢查摘要 - {data['hostname']}",
        f"時間: {data['timestamp']}",
        f"狀態: {data['status']}",
        f"PASS={data['stats']['pass']} WARN={data['stats']['warn']} FAIL={data['stats']['fail']} N/A={data['stats']['na']}",
        f"影響摘要: {data['customer_impact']}",
        "",
    ]
    for item in data["items"]:
        lines.append(f"{item['idx']}. {item['name']} {item['verdict']} - {item['impact']}")
    return "\n".join(lines)


def _write_reports(host: dict[str, Any], job_ts: str, summary: str, detail: str) -> tuple[Path, Path]:
    host_dir = Path(config.HOSTS_DIR) / host["asset_seq"] / "deep_check"
    host_dir.mkdir(parents=True, exist_ok=True)
    hostname = re.sub(r"[^\w\-.]", "_", host["hostname"])
    summary_name = f"ts_{hostname}_{job_ts}_summary.txt"
    detail_name = f"ts_{hostname}_{job_ts}_detail.txt"
    summary_path = host_dir / summary_name
    detail_path = host_dir / detail_name
    summary_path.write_text(summary, encoding="utf-8")
    detail_path.write_text(detail, encoding="utf-8")
    return summary_path, detail_path


def _report_path(filename: str) -> Path:
    if not REPORT_RE.match(filename):
        raise FileNotFoundError("invalid report filename")
    report = get_collection("deep_check_reports").find_one(
        {"$or": [{"summary_filename": filename}, {"detail_filename": filename}, {"filename": filename}]},
        {"_id": 0},
    )
    if not report:
        raise FileNotFoundError(filename)
    path = Path(report["path"] if report.get("summary_filename") == filename or report.get("filename") == filename else report["detail_path"])
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
