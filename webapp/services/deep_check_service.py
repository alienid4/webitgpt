from __future__ import annotations

import os
import re
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from webapp import config
from webapp.services.host_service import list_hosts
from webapp.services.mongo_service import get_collection
from webapp.services.remedy_kb import match_remedies


REPORT_RE = re.compile(r"^ts_[\w\-.]+_\d{8}_\d{6}_(summary|detail)\.txt$")


def _local_tz():
    try:
        return ZoneInfo(config.TZ_NAME)
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=8))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _local_now() -> datetime:
    return _utc_now().astimezone(_local_tz())


NETWORK_CHECKPOINTS = [
    ("NET-01", "網卡 errors", "實體網卡 errors 應為 0 或不再增加。"),
    ("NET-02", "網卡 dropped", "實體網卡 dropped 應為 0 或不再增加。"),
    ("NET-03", "TCP retransmit", "TCP retransmit 應無明顯增加。"),
    ("NET-04", "Ping loss", "ping packet loss 應為 0%。"),
    ("NET-05", "conntrack 用量", "nf_conntrack_count 不應接近 nf_conntrack_max。"),
    ("NET-06", "TIME_WAIT / port range", "TIME_WAIT 不應造成 ephemeral port 耗盡。"),
    ("NET-07", "SYN backlog / listen drops", "SYN backlog 與 listen drops 不應出現堆積或丟棄。"),
]


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
        "cmd": "ss -ltnp 2>/dev/null | head -80; ps -eo pid,comm,%cpu,%mem --sort=-%cpu | head -12",
        "baseline": "AP listener 存在，程序資源合理，systemd 無 failed unit。",
        "warn_patterns": [],
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
        "cmd": "dmesg -T 2>/dev/null | egrep -i 'oom|mce|machine check' | tail -20 || true; cat /proc/sys/kernel/tainted 2>/dev/null || true; systemctl is-active firewalld 2>/dev/null || true; firewall-cmd --state 2>/dev/null || true; nft list ruleset 2>/dev/null | head -40 || iptables -S 2>/dev/null | head -40 || true",
        "baseline": "無 OOM / MCE / failed unit，kernel tainted 為 0。",
        "warn_patterns": ["oom", "machine check"],
    },
    {
        "idx": 10,
        "name": "運維軌跡",
        "cmd": "for u in $(awk -F: '($7 !~ /(nologin|false)$/ && $3 >= 0){print $1}' /etc/passwd); do s=$(passwd -S \"$u\" 2>/dev/null | awk '{print $2}'); if [ \"$s\" = \"L\" ] || [ \"$s\" = \"LK\" ]; then echo \"ACCOUNT_LOCKED $u\"; fi; done; last -n 10",
        "baseline": "近期登入、設定異動與服務啟停都有可追溯紀錄。",
        "warn_patterns": ["ACCOUNT_LOCKED"],
    },
]


AIX_COMMANDS = {
    1: "uptime; vmstat 1 3; svmon -G 2>/dev/null | head -20 || true",
    2: "netstat -in; netstat -s | egrep -i 'error|drop|retransmit|collision' | head -40 || true",
    3: "netstat -an | egrep 'LISTEN|\\.22|\\.9444|\\.8002' | head -80; ps -eo pid,comm,pcpu,pmem | sort -k3 -nr | head -12",
    4: "netstat -an | egrep '\\.${AP_PORT:-8002} .*LISTEN' || true",
    5: "netstat -an | awk 'NR>2 {print $6}' | sort | uniq -c | sort -nr | head -20",
    6: "df -g; df -i 2>/dev/null || true",
    7: "date; lssrc -ls xntpd 2>/dev/null || ntpq -p 2>/dev/null || true",
    8: "ps -ef | egrep 'oracle|db2sysc|mysqld|postgres|mongod' | grep -v grep || true; netstat -an | egrep '1521|50000|3306|5432|27017' || true",
    9: "errpt | head -30; lssrc -a | egrep -i 'inoperative|failed' || true",
    10: "last | head -20; errpt | head -20",
}


def _face_specs_for(host: dict[str, Any]) -> list[dict[str, Any]]:
    if host.get("host_type") != "aix":
        return FACE_SPECS
    specs = []
    for spec in FACE_SPECS:
        cloned = dict(spec)
        cloned["cmd"] = AIX_COMMANDS.get(int(spec["idx"]), str(spec["cmd"]))
        cloned["baseline"] = f"AIX：{spec['baseline']}"
        specs.append(cloned)
    return specs


def meta() -> dict[str, Any]:
    return {
        "controller_hostname": _controller_hostname(),
        "role": "L3 on-demand deep check",
        "faces": [{"idx": item["idx"], "name": item["name"], "baseline": item["baseline"]} for item in FACE_SPECS],
        "supported_platforms": ["linux", "aix"],
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
    if host.get("host_type") not in {"linux", "aix"}:
        return {"success": False, "error": f"目前 L3 深度檢查支援 Linux/RHEL/Debian/CentOS 與 AIX 主機：{hostname}"}
    if host.get("status") in {"disabled", "retired"}:
        return {"success": False, "error": f"主機狀態不允許檢查：{hostname}"}

    running = get_collection("deep_check_jobs").find_one({"status": {"$in": ["starting", "running"]}}, {"_id": 0})
    if running:
        return {"success": False, "error": "已有深度檢查正在執行", "job_id": running["job_id"]}

    now = _utc_now()
    job_ts = _local_now().strftime("%Y%m%d_%H%M%S")
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
            {"$set": {"status": "error", "error": str(exc), "finished_at": _utc_now(), "phase": "執行失敗"}},
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
        {"$set": {"status": "canceled", "finished_at": _utc_now(), "phase": "已取消", "canceled_by": user}},
    )
    return {"success": bool(result.modified_count), "job_id": job_id}


def history(hostname: str, limit: int = 20) -> dict[str, Any]:
    query = {"hostname": hostname} if hostname else {}
    rows = list(get_collection("deep_check_jobs").find(query, {"_id": 0}).sort("started_at", -1).limit(limit))
    return {"success": True, "hostname": hostname, "items": rows}


def reports(hostname: str) -> dict[str, Any]:
    query = {"hostname": hostname} if hostname else {}
    rows = list(get_collection("deep_check_reports").find(query, {"_id": 0}).sort("timestamp", -1).limit(100))
    rows = [_normalize_report_doc(row) for row in rows]
    return {"success": True, "hostname": hostname, "items": rows}


def latest_report(hostname: str) -> Optional[dict[str, Any]]:
    report = get_collection("deep_check_reports").find_one({"hostname": hostname}, {"_id": 0}, sort=[("timestamp", -1)])
    return _normalize_report_doc(report) if report else None


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
    report = _normalize_report_doc(report)
    return {"success": True, "filename": filename, "data": report.get("parsed", {})}


def download_path(filename: str) -> Path:
    return _report_path(filename)


def _execute(job: dict[str, Any], host: dict[str, Any]) -> None:
    job_id = job["job_id"]
    get_collection("deep_check_jobs").update_one({"job_id": job_id}, {"$set": {"status": "running", "phase": "執行 9 面向檢查", "progress": 5}})
    items = []
    detail_lines = []
    for spec in _face_specs_for(host):
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
        "timestamp": _utc_now(),
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
                "finished_at": _utc_now(),
                "returncode": 0,
                "report_files": {"summary": summary_file.name, "detail": detail_file.name},
                "log": detail_text[-5000:],
            }
        },
    )


def _run_command(host: dict[str, Any], cmd: str) -> tuple[int, str, str]:
    env_cmd = f"AP_PORT={os.environ.get('AP_PORT', str(config.WEB_PORT))}; PING_TGT={os.environ.get('PING_TGT', '127.0.0.1')}; {cmd}"
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
    if int(spec["idx"]) == 1:
        return _performance_verdict(rc, text)
    if int(spec["idx"]) == 2:
        return _network_verdict(rc, text)
    if int(spec["idx"]) == 3:
        return _ap_listener_verdict(rc, text)
    if int(spec["idx"]) == 4:
        return _ap_endpoint_verdict(rc, text)
    if int(spec["idx"]) == 5:
        return _session_verdict(rc, text)
    if int(spec["idx"]) == 6:
        return _storage_verdict(rc, text)
    if int(spec["idx"]) == 7:
        return _time_cert_verdict(rc, text)
    if int(spec["idx"]) == 9:
        return _infra_verdict(rc, text)
    if int(spec["idx"]) == 10:
        return _account_lock_verdict(rc, text)
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


def _performance_verdict(rc: int, text: str) -> str:
    if rc != 0:
        return "WARN"
    if _performance_issue_lines(text):
        return "WARN"
    return "PASS"


def _ap_listener_verdict(rc: int, text: str) -> str:
    if rc != 0:
        return "WARN"
    if "listen" not in text.lower():
        return "WARN"
    return "PASS"


def _ap_endpoint_verdict(rc: int, text: str) -> str:
    lowered = text.lower()
    if rc != 0:
        return "WARN"
    if any(token in lowered for token in ("connection refused", "failed", "timeout", "timed out", "not found", "could not connect")):
        return "WARN"
    if "listen" in lowered or '"status":"ok"' in lowered or '"status": "ok"' in lowered or "status ok" in lowered:
        return "PASS"
    return "WARN"


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


def _storage_verdict(rc: int, text: str) -> str:
    if rc != 0:
        return "WARN"
    if _storage_issue_lines(text):
        return "WARN"
    return "PASS"


def _time_cert_verdict(rc: int, text: str) -> str:
    lowered = text.lower()
    if rc != 0:
        return "WARN"
    if any(token in lowered for token in ("not synchronized", "unsynchronized", "no server suitable", "clock unsynchronized")):
        return "WARN"
    return "PASS"


def _time_cert_pass_points(text: str) -> list[str]:
    points: list[str] = []
    for line in text.splitlines():
        cleaned = line.strip()
        lowered = cleaned.lower()
        if not cleaned:
            continue
        if "system clock synchronized:" in lowered or "ntp synchronized:" in lowered:
            points.append(cleaned)
        elif "ntp service:" in lowered or "systemd-timesyncd.service active:" in lowered:
            points.append(cleaned)
        elif "leap status" in lowered:
            points.append(cleaned)
        elif "reference id" in lowered or "stratum" in lowered:
            points.append(cleaned)
        elif re.search(r"\b\d{4}-\d{2}-\d{2}\b", cleaned) or re.search(r"\b[A-Z]{3}\b.*\b\d{2}:\d{2}:\d{2}\b", cleaned):
            points.append(cleaned)
        if len(points) >= 6:
            break

    cert_count = len(re.findall(r"\.(?:crt|pem)\b", text, re.IGNORECASE))
    if cert_count:
        points.append(f"憑證檔清單可讀：本次列出 {cert_count} 筆 .crt/.pem 檔案；目前只證明檔案可讀，尚未判斷到期日。")
    if not points:
        points.append("未看到 unsynchronized、not synchronized、no server suitable 或 clock unsynchronized 等時間同步警示字樣。")
    return points


def _time_cert_pass_summary(text: str) -> str:
    return "；".join(_time_cert_pass_points(text)[:4])


def _infra_verdict(rc: int, text: str) -> str:
    lowered = text.lower()
    if rc != 0:
        return "WARN"
    if any(token in lowered for token in ("oom", "machine check")):
        return "WARN"
    tainted = _kernel_tainted_value(text)
    if tainted and tainted != "0":
        return "WARN"
    return "PASS"


def _account_lock_verdict(rc: int, text: str) -> str:
    if rc != 0:
        return "WARN"
    if re.search(r"^ACCOUNT_LOCKED\s+\S+", text, re.MULTILINE):
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

    if any(item["status"] == "WARN" for item in _network_checkpoint_statuses(text)):
        return "WARN"
    return "PASS"


def _link_error_or_drop_seen(text: str) -> bool:
    return bool(_network_counter_issue_lines(text))


def _iface_name(line: str) -> str:
    match = re.match(r"^\d+:\s+([^:@]+)", line.strip())
    return match.group(1) if match else ""


def _is_loopback_iface(line: str) -> bool:
    return _iface_name(line) == "lo"


def _tcp_retransmit_seen(text: str) -> bool:
    lowered = text.lower()
    patterns = [
        r"\b(\d+)\s+segments?\s+retransm",
        r"\bretrans(?:mitted|mits|mission)?\D+(\d+)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, lowered):
            if int(match.group(1)) > 0:
                return True
    return False


def _listen_drop_seen(text: str) -> bool:
    lowered = text.lower()
    patterns = [
        r"\b(\d+)\s+listen(?:ing)?\s+drops?",
        r"\blisten(?:ing)?\s+drops?\D+(\d+)",
        r"\bsyn(?:-|_)?recv\D+(\d+)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, lowered):
            if int(match.group(1)) > 0:
                return True
    return False


def _ping_loss_pct(text: str) -> Optional[float]:
    match = re.search(r"(\d+(?:\.\d+)?)%\s+packet loss", text.lower())
    if match:
        return float(match.group(1))
    return None


def _network_reachability_error_seen(text: str) -> bool:
    lowered = text.lower()
    return any(
        token in lowered
        for token in [
            "no route to host",
            "network is unreachable",
            "connection timed out",
            "temporary failure in name resolution",
        ]
    )


def _conntrack_usage(text: str) -> Optional[tuple[int, int, float]]:
    count_match = re.search(r"nf_conntrack_count\s*[=:]\s*(\d+)", text)
    max_match = re.search(r"nf_conntrack_max\s*[=:]\s*(\d+)", text)
    if not count_match or not max_match:
        return None
    count = int(count_match.group(1))
    maximum = int(max_match.group(1))
    if maximum <= 0:
        return None
    return count, maximum, count / maximum * 100


def _time_wait_count(text: str) -> int:
    counts = _tcp_state_counts(text)
    if counts.get("TIME-WAIT", 0):
        return counts["TIME-WAIT"]
    match = re.search(r"\btimewait\s+(\d+)", text, re.IGNORECASE)
    return int(match.group(1)) if match else 0


def _tcp_state_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in text.splitlines():
        match = re.match(r"\s*(\d+)\s+([A-Z-]+)\s*$", line)
        if match:
            counts[match.group(2).upper()] = int(match.group(1))
    return counts


def _locked_account_names(text: str) -> list[str]:
    names = []
    for line in text.splitlines():
        match = re.match(r"ACCOUNT_LOCKED\s+(\S+)", line.strip())
        if match and match.group(1) not in names:
            names.append(match.group(1))
    return names


def _locked_account_display(text: str, limit: int = 6) -> str:
    names = _locked_account_names(text)
    if not names:
        return "未列出帳號"
    shown = names[:limit]
    suffix = f" 等 {len(names)} 個帳號" if len(names) > limit else ""
    return "、".join(shown) + suffix


def _locked_account_command_examples(text: str, command: str, limit: int = 3) -> str:
    names = _locked_account_names(text)[:limit]
    if not names:
        return f"{command} <account>"
    return "；".join(f"{command} {name}" for name in names)


def _locked_account_fix_commands(text: str, limit: int = 6) -> str:
    names = _locked_account_names(text)[:limit]
    if not names:
        return "\n".join(
            [
                "sudo awk -F: '($7 !~ /(nologin|false)$/ && $3 >= 0){print $1}' /etc/passwd | while read u; do passwd -S \"$u\" 2>/dev/null; done",
                "若上一行仍沒有帳號名稱，代表帳號狀態採集失敗，請先重跑 L3，不要直接解鎖未知帳號。",
            ]
        )
    commands: list[str] = []
    for name in names:
        commands.extend(
            [
                f"# {name}",
                f"id {name}",
                f"passwd -S {name}",
                f"sudo passwd -u {name}",
                f"passwd -S {name}",
                f"sudo usermod -U {name}",
                f"passwd -S {name}",
            ]
        )
    return "\n".join(commands)


def _locked_account_lines(text: str) -> list[str]:
    return [f"{name} 被鎖定" for name in _locked_account_names(text)]


def _performance_issue_lines(text: str) -> list[str]:
    issues: list[str] = []
    load_match = re.search(r"load average:\s*([0-9.]+),\s*([0-9.]+),\s*([0-9.]+)", text, re.IGNORECASE)
    cpu_match = re.search(r"%?Cpu\(s\):.*?([0-9.]+)\s*id", text, re.IGNORECASE)
    if cpu_match and float(cpu_match.group(1)) < 30:
        issues.append(f"CPU idle={cpu_match.group(1)}%，低於 30%，代表 CPU 可能忙碌。")
    if load_match and float(load_match.group(1)) >= 8:
        issues.append(f"load average 1 分鐘={load_match.group(1)}，需確認是否超過主機核心數 2 倍。")
    swap = _free_swap_usage_pct(text)
    if swap is not None and swap >= 50:
        issues.append(f"Swap 使用率={swap:.1f}%，高於 50%，可能代表記憶體壓力。")
    return issues


def _free_swap_usage_pct(text: str) -> Optional[float]:
    for line in text.splitlines():
        cleaned = line.strip()
        if not cleaned.lower().startswith("swap:"):
            continue
        values = [float(value) for value in re.findall(r"\b\d+(?:\.\d+)?\b", cleaned)]
        if len(values) >= 3 and values[0] > 0:
            return values[1] / values[0] * 100
    return None


def _storage_issue_lines(text: str) -> list[str]:
    issues: list[str] = []
    for line in text.splitlines():
        cleaned = line.strip()
        if not cleaned or cleaned.lower().startswith("filesystem"):
            continue
        match = re.search(r"\s(8[5-9]|9[0-9]|100)%\s+(\S+)$", cleaned)
        if match:
            issues.append(f"{match.group(2)} 使用率 {match.group(1)}%，高於 85%。")
    return issues[:8]


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
        if idx == 1:
            return "效能檢查目的：確認 CPU、記憶體與 Swap 是否足以支撐 AP。結果未發現 CPU idle 過低、load 明顯過高或 Swap 過量使用。"
        if idx == 2:
            return "網路檢查目的：確認這台主機本身的對外網路品質是否會影響 AP 連線。7 個檢查點均未命中 WARN；若輸出只有 lo，那是本機迴圈介面，不代表對外網路異常。"
        if idx == 3:
            return "AP Listener 檢查目的：確認 AP 或管理服務有在主機上監聽。結果有看到 LISTEN，代表主機端服務入口存在。"
        if idx == 4:
            return "AP 連線檢查目的：確認本機可以連到指定 AP port 或 health endpoint。結果有監聽或 health 回應，代表本機端 AP 入口可用。"
        if idx == 5:
            counts = _tcp_state_counts(text)
            return (
                f"Session 檢查目的：確認 TCP 連線沒有塞車或卡死。結果在門檻內：SYN-RECV={counts.get('SYN-RECV', 0)}、"
                f"CLOSE-WAIT={counts.get('CLOSE-WAIT', 0)}、ESTAB={counts.get('ESTAB', 0)}。"
            )
        if idx == 6:
            return "Storage 檢查目的：確認磁碟與 inode 空間不會讓 AP 寫檔、暫存或 log 失敗。結果未發現 85% 以上使用率。"
        if idx == 7:
            return "時間與憑證檢查目的：確認主機時間沒有明顯不同步，避免排程、憑證或稽核時間錯亂。PASS 證據：" + _time_cert_pass_summary(text)
        if idx == 8:
            return "資料庫檢查目的：確認主機上是否存在常見 DB 程序或 port，供影響判斷使用；沒有命中不代表異常。"
        if idx == 9:
            return "Infra 檢查目的：快速排除 OS 層重大不穩定因素。結果未發現 OOM、machine check 或 kernel tainted 異常；防火牆狀態只作為連線排除證據。"
        if idx == 10:
            return "運維軌跡檢查目的：確認可登入帳號沒有被非預期鎖定。結果未發現可登入帳號被鎖定。"
        return "未超過警示門檻。"
    if rc != 0:
        return f"命令回傳碼 rc={rc}，代表採集或檢查命令執行異常。"
    if idx == 1:
        issues = _performance_issue_lines(text)
        if issues:
            return "效能檢查目的：確認 CPU、記憶體與 Swap 是否影響 AP。發現：" + "；".join(issues)
        return "效能檢查回報 WARN，但未抓到 CPU idle、load 或 Swap 的明確異常數值。"
    if idx == 2:
        warn_lines = _network_warn_checkpoint_lines(text)
        if warn_lines:
            return "網路檢查目的：確認主機本身網路品質是否影響 AP。命中檢查點：" + "；".join(warn_lines)
        return "網路檢查回報 WARN，但未找到實體網卡 error/drop、ping loss 或 TCP 重傳證據；請先確認採集命令是否完整。"
    if idx == 3:
        return "AP Listener 檢查目的：確認 AP 或管理服務是否有監聽。結果未看到 LISTEN，可能是服務未啟動、port 綁定錯誤或採集權限不足。"
    if idx == 4:
        return "AP 連線檢查目的：確認本機指定 port 或 health endpoint 是否可用。結果未取得明確 LISTEN 或 health ok，可能是 AP 未啟動、port 設錯或本機防火牆阻擋。"
    if idx == 5:
        counts = _tcp_state_counts(text)
        if counts.get("SYN-RECV", 0) > 0:
            return f"Session 檢查目的：確認連線沒有卡在半開狀態。發現 SYN-RECV={counts.get('SYN-RECV')}，門檻為 0。"
        if counts.get("CLOSE-WAIT", 0) >= 10:
            return f"Session 檢查目的：確認連線沒有被 AP 程式卡住。發現 CLOSE-WAIT={counts.get('CLOSE-WAIT')}，門檻為小於 10。"
        if counts.get("ESTAB", 0) >= 500:
            return f"Session 檢查目的：確認連線量沒有異常暴增。發現 ESTAB={counts.get('ESTAB')}，門檻為小於 500。"
        return "Session 檢查回報 WARN，但未解析到 SYN-RECV、CLOSE-WAIT 或 ESTAB 的明確異常。"
    if idx == 6:
        issues = _storage_issue_lines(text)
        if issues:
            return "Storage 檢查目的：確認磁碟與 inode 空間是否會影響 AP 寫檔、暫存或 log。發現：" + "；".join(issues)
        return "Storage 檢查回報 WARN，但未解析到 85% 以上的 filesystem 或 inode 使用率。"
    if idx == 7:
        return "時間與憑證檢查目的：確認時間同步是否正常。發現時間未同步或同步來源異常，可能造成排程、憑證驗證或稽核時間不一致。"
    if idx == 8:
        return "資料庫檢查回報 WARN；請確認這台主機是否應該存在 DB 程序或 DB port。若不是 DB 主機，通常只需備註主機用途。"
    if idx == 9:
        issues = _systemd_failed_issue_lines(text)
        tainted = _kernel_tainted_value(text)
        if "oom" in text.lower() or "machine check" in text.lower():
            return "Infra 檢查目的：快速排除 OS 層重大不穩定因素。發現 OOM 或硬體 machine check 訊號，代表主機曾出現記憶體或硬體層風險。"
        if tainted and tainted != "0":
            return f"Infra 檢查目的：快速排除 OS 層重大不穩定因素。發現 kernel tainted={tainted}，門檻為 0，代表核心載入狀態需由系統管理者確認。"
        if issues:
            return "Infra 檢查發現 failed unit，但此項只把它當輔助線索，不直接代表 AP 故障：" + "；".join(issues[:3])
        return "Infra 檢查回報 WARN，但未抓到 OOM、machine check 或 kernel tainted 的明確證據。"
    if idx == 10:
        locked = _locked_account_lines(text)
        if locked:
            return "運維軌跡檢查目的：確認 AP 或批次可能使用的可登入帳號沒有被鎖定。發現：" + _locked_account_display(text)
        return "帳號狀態檢查異常，需確認 passwd -S 或 OS 帳號資料是否可讀取。"
    return "命中警示條件，請查看證據摘要確認異常數值。"


def _threshold_summary(spec: dict[str, Any], text: str) -> str:
    idx = int(spec["idx"])
    if idx == 1:
        return "用途：判斷主機效能是否會拖慢 AP。門檻：CPU idle 不低於 30%，Swap 使用率低於 50%，load 不應明顯超過主機核心數。"
    if idx == 2:
        checkpoint_text = "；".join(f"{sn} {name}" for sn, name, _ in NETWORK_CHECKPOINTS)
        return "用途：判斷主機本身對外網路品質是否影響 AP。網路共 7 個檢查點：" + checkpoint_text + "。忽略 lo 本機迴圈介面。"
    if idx == 3:
        return "AP listener 必須存在；不再以全部 systemd failed unit 作為 AP 異常依據。"
    if idx == 4:
        return "用途：確認 AP port 或 health endpoint 是否可用。門檻：有 LISTEN 或 health 回應 ok。"
    if idx == 5:
        return "用途：判斷 TCP 連線是否卡住。門檻：SYN-RECV 必須為 0，CLOSE-WAIT 小於 10，ESTAB 小於 500。"
    if idx == 6:
        return "用途：確認磁碟、inode、/tmp 或 journal 不會讓 AP 寫檔失敗。門檻：主要 filesystem 與 inode 使用率低於 85%。"
    if idx == 7:
        return "用途：確認主機時間可信。門檻：時間同步不可顯示 unsynchronized、not synchronized、no server suitable 或 clock unsynchronized；若有憑證檔，只列出可讀清單，憑證到期日需另做 openssl 到期檢查。"
    if idx == 8:
        return "用途：辨識這台主機是否有 DB 程序或常見 DB port，供影響判斷使用；不是 DB 主機時不視為異常。"
    if idx == 9:
        return "無 OOM / machine check；kernel tainted 為 0；防火牆狀態只作為連線排除證據。"
    if idx == 10:
        return "可登入帳號不應被非預期鎖定，尤其 AP 或批次使用帳號。"
    return str(spec.get("baseline") or "")


def _recommendation(spec: dict[str, Any], verdict: str, text: str) -> str:
    urgent_idx = int(spec["idx"])
    if verdict != "PASS" and urgent_idx == 10:
        accounts = _locked_account_display(text)
        commands = _locked_account_fix_commands(text)
        if _locked_account_names(text):
            return "\n".join(
                [
                    f"狀況：發現可登入帳號被鎖定：{accounts}，可能影響 AP 登入、批次或服務連線。",
                    "1. 先確認帳號用途與目前狀態。",
                    "2. 若確認需要立即恢復，只解鎖確認要用的帳號。",
                    "3. 解鎖後重跑 passwd -S，確認不再是 L/LK。",
                    "4. 若是資安刻意鎖定，不要解鎖，改通知 AP 負責人改用正確帳號。",
                    "可直接執行指令：",
                    commands,
                ]
            )
        return "\n".join(
            [
                "狀況：帳號鎖定檢查失敗，這次沒有抓到實際帳號名稱。",
                "1. 不能使用 <account> 這種占位文字解鎖，避免誤解鎖未知帳號。",
                "2. 先執行下列採集確認指令，取得真實帳號名稱。",
                "3. 有真實帳號名稱後，再依帳號用途決定是否解鎖。",
                "採集確認指令：",
                commands,
            ]
        )
    if verdict == "PASS":
        idx = int(spec["idx"])
        if idx == 7:
            return "\n".join(
                [
                    "PASS 證明：",
                    *[f"{pos}. {line}" for pos, line in enumerate(_time_cert_pass_points(text), start=1)],
                    "建議處置：目前沒有看到需要立即處理的時間同步異常；維持例行觀察即可。若要證明憑證未過期，需執行 openssl x509 -enddate 的到期日檢查。",
                ]
            )
        return "目前沒有看到需要立即處理的異常，維持例行觀察即可。"
    idx = int(spec["idx"])
    if idx == 1:
        return "\n".join(
            [
                "狀況：效能數據超過門檻，可能造成 AP 反應變慢。",
                "1. 先確認是否為短暫尖峰。",
                "2. 找出 CPU 或記憶體用量最高的程序。",
                "3. 若 Swap 高於 50%，確認 AP 是否記憶體不足或有異常批次。",
                "4. 處理後重跑深度檢查。",
                "可直接執行指令：",
                "uptime",
                "top -bn1 | head -20",
                "free -m",
                "vmstat 1 3",
            ]
        )
    if idx == 2:
        issues = _network_counter_issue_lines(text)
        loss = _ping_loss_pct(text)
        if issues:
            return "\n".join(
                [
                    "狀況：網路檢查命中 SN：" + "、".join(line.split(" ", 1)[0] for line in _network_warn_checkpoint_lines(text)) + "，可能影響 AP 連線品質。",
                    "1. 先確認是哪張網卡與哪個 counter 在增加。",
                    "2. 若 dropped/errors/carrier 持續增加，交由 VM/網路管理者檢查虛擬網卡、交換器埠、線路或速率/雙工設定。",
                    "3. 如果同時命中 conntrack 或 TIME_WAIT，也要一併確認是否有大量短連線或連線池異常。",
                    "4. 修正後重跑深度檢查，確認 counter 與連線壓力不再增加。",
                    "可直接執行指令：",
                    _network_fix_commands(text),
                    _network_pressure_fix_commands(text),
                ]
            )
        if loss is not None and loss > 0:
            return "\n".join(
                [
                    f"狀況：NET-04 Ping loss 偵測到 {loss:g}%，代表封包有遺失。",
                    "1. 先確認目標 IP 是否正確。",
                    "2. 檢查路由、交換器、防火牆與主機負載。",
                    "3. 處理後重跑深度檢查，確認 loss 回到 0%。",
                    "可直接執行指令：",
                    "ping -c 5 ${PING_TGT:-127.0.0.1}",
                    "tracepath ${PING_TGT:-127.0.0.1} 2>/dev/null || traceroute ${PING_TGT:-127.0.0.1}",
                ]
            )
        if _tcp_retransmit_seen(text):
            return "\n".join(
                [
                    "狀況：NET-03 TCP retransmit 偵測到重傳，可能是連線重送、佇列滿或服務過載。",
                    "1. 先確認是否為單一 AP 服務過載。",
                    "2. 檢查網路延遲、防火牆或連線佇列。",
                    "3. 處理後重跑深度檢查，確認重傳或 drop 不再增加。",
                    "可直接執行指令：",
                    "ss -s",
                    "netstat -s | egrep -i 'retrans|listen|drop'",
                ]
            )
        if _listen_drop_seen(text):
            return "\n".join(
                [
                    "狀況：NET-07 SYN backlog / listen drops 命中，可能有連線排隊或被丟棄。",
                    "1. 先確認 AP listener 是否過載。",
                    "2. 檢查 TCP backlog、服務連線佇列與防火牆。",
                    "3. 處理後重跑深度檢查，確認 listen drops 不再增加。",
                    "可直接執行指令：",
                    "ss -s",
                    "netstat -s | egrep -i 'listen|drop|syn'",
                ]
            )
        conntrack = _conntrack_usage(text)
        if conntrack is not None and conntrack[2] >= 80:
            return "\n".join(
                [
                    f"狀況：NET-05 conntrack 用量已達 {conntrack[2]:.1f}% ({conntrack[0]}/{conntrack[1]})，新連線可能被丟棄。",
                    "1. 先確認是否有大量短連線或異常來源。",
                    "2. 若 AP 連線受影響，先找出連線最多的來源 IP，再決定是否阻擋或調整 AP 連線池。",
                    "3. 若確認是正常尖峰，請由系統管理者評估提高 nf_conntrack_max，並記錄變更。",
                    "4. 處理後重跑深度檢查，確認 conntrack 使用率低於 80%。",
                    "可直接執行指令：",
                    "sysctl net.netfilter.nf_conntrack_count net.netfilter.nf_conntrack_max",
                    "sudo conntrack -S 2>/dev/null || true",
                    "ss -tan | awk 'NR>1 {print $5}' | cut -d: -f1 | sort | uniq -c | sort -nr | head -20",
                ]
            )
        time_wait = _time_wait_count(text)
        if time_wait >= 1000:
            return "\n".join(
                [
                    f"狀況：NET-06 TIME_WAIT / port range 偵測到 TIME_WAIT={time_wait}，可能代表短連線過多或連線釋放壓力。",
                    "1. 先確認是否為批次、AP 或代理服務大量建立短連線。",
                    "2. 找出連線最多的本機程序與遠端 IP。",
                    "3. 若 AP 連線受影響，優先調整 AP 連線池或 keepalive，不要直接改 kernel 參數。",
                    "4. 處理後重跑深度檢查，確認 TIME_WAIT 回到合理範圍。",
                    "可直接執行指令：",
                    "ss -tan state time-wait | wc -l",
                    "ss -tanp | awk 'NR>1 {print $5}' | cut -d: -f1 | sort | uniq -c | sort -nr | head -20",
                    "cat /proc/sys/net/ipv4/ip_local_port_range",
                ]
            )
        return "\n".join(
            [
                "狀況：目前沒有明確網路異常證據。",
                "1. 網路共 7 個檢查點，請先看 NET-01 到 NET-07 的 SN 結果。",
                "2. 若畫面只看到 lo，代表本機迴圈介面，不需通知網路單位。",
                "3. 重新執行深度檢查或補抓實體網卡資料。",
                "可直接執行指令：",
                "ip -s link",
                "ss -s",
            ]
        )
    if idx == 3:
        return "\n".join(
            [
                "狀況：未確認到 AP listener，可能是 AP 未啟動、port 綁定錯誤或被防火牆擋住。",
                "1. 確認 AP 程序是否存在。",
                "2. 確認 AP port 是否有監聽。",
                "3. 若 AP 有啟動但外部連不到，短時間排除防火牆；測完立即恢復。",
                "4. 若停防火牆後恢復，改用正式規則只開必要 port。",
                "可直接執行指令：",
                "ps -ef | grep <AP關鍵字>",
                "ss -ltnp | grep <port>",
                "sudo systemctl stop firewalld",
                "sudo systemctl start firewalld",
                "sudo firewall-cmd --permanent --add-port=<port>/tcp && sudo firewall-cmd --reload",
            ]
        )
    if idx == 4:
        return "\n".join(
            [
                "狀況：本機 AP port 或 health endpoint 沒有正常回應。",
                "1. 確認 AP_PORT 是否正確。",
                "2. 確認本機是否監聽該 port。",
                "3. 確認 health endpoint 是否回應。",
                "4. 若本機可通但外部不通，再檢查防火牆或 ACL。",
                "可直接執行指令：",
                "echo ${AP_PORT:-8002}",
                "ss -ltnp | grep ${AP_PORT:-8002}",
                "curl -v http://127.0.0.1:${AP_PORT:-8002}/health",
            ]
        )
    if idx == 5:
        return "請交由應用系統負責人與系統管理者共同確認：1. 找出大量異常連線的來源程式與對象；2. 若是程式未正常關閉連線，安排應用修正或重啟服務；3. 若是外部連線不穩，請網路單位確認路徑與防火牆。"
    if idx == 6:
        return "建議處置：先確認是哪個掛載點或 inode 高於門檻。可執行 df -h、df -i、du -xh <path> | sort -h | tail。若是 log 或暫存檔，先備份再清理；若是 AP 資料目錄，先擴容或搬移，不要直接刪除未知檔案。"
    if idx == 7:
        return "建議處置：先確認時間服務狀態。Linux 可執行 timedatectl、chronyc tracking 或 ntpq -p；若未同步，修復 NTP/Chrony 設定並重啟時間服務。時間修正後，重新檢查憑證、排程與稽核時間是否一致。"
    if idx == 8:
        return "建議處置：若這台是 DB 主機，確認 DB process 與 port 是否符合預期；若不是 DB 主機，將結果作為用途備註即可。不要因未看到 DB process 直接判斷 OS 異常。"
    if idx == 9:
        return "緊急判斷：這裡只處理能直接證明 OS 不穩的 OOM、硬體 machine check、kernel tainted 或防火牆阻擋證據。若懷疑防火牆阻擋 AP，短時間排除可執行 sudo systemctl stop firewalld，測完立即 sudo systemctl start firewalld；正式修復請只開必要 port，不要長期關閉防火牆。"
    return "請先確認影響範圍與備份，再安排修復；不建議未確認原因就直接變更系統。"


def _evidence_summary(spec: dict[str, Any], rc: int, text: str, verdict: str) -> str:
    idx = int(spec["idx"])
    lines = [f"回傳碼 rc={rc}；判定={verdict}。"]
    if idx == 1:
        lines.extend(_matching_lines(text, [r"load average", r"^mem:", r"^swap:", r"%?cpu"], limit=4))
    elif idx == 2:
        lines.extend(_network_evidence(text))
    elif idx == 3:
        lines.extend(_matching_lines(text, [r"listening|listen|:\d+"], limit=5))
    elif idx == 4:
        lines.extend(_matching_lines(text, [r"status|ok|health|refused|failed|timeout|not found"], limit=5))
    elif idx == 5:
        lines.extend(_matching_lines(text, [r"estab|listen|close-wait|syn-recv|time-wait"], limit=6))
    elif idx == 6:
        lines.extend(_matching_lines(text, [r"filesystem|/dev/|tmpfs|journal"], limit=6))
    elif idx == 7:
        lines.extend(_time_cert_pass_points(text))
    elif idx == 8:
        lines.extend(_matching_lines(text, [r"oracle|sql|mysql|mariadb|postgres|mongod|1521|1433|3306|5432|27017"], limit=6))
    elif idx == 9:
        lines.extend(_matching_lines(text, [r"oom|machine check|tainted|firewalld|running|not running|table|chain|^-A"], limit=6))
    elif idx == 10:
        locked = _locked_account_lines(text)
        if locked:
            lines.extend(locked[:6])
        else:
            lines.extend(_matching_lines(text, [r"ACCOUNT_LOCKED|logged|reboot"], limit=6))
    if len(lines) == 1:
        lines.extend(_first_nonempty_lines(text, limit=4))
    if idx == 2:
        return "\n".join(lines[:18])
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
    evidence = _network_checkpoint_lines(text)
    evidence.extend(_matching_lines(text, [r"packet loss", r"retrans", r"listen.*drop", r"no route|unreachable|timed out"], limit=4))
    issue_lines = _network_counter_issue_lines(text)
    if issue_lines:
        return (evidence + issue_lines)[:17]

    lines = text.splitlines()
    current_iface = ""
    saw_non_loopback = False
    raw_lines: list[str] = []
    for idx, line in enumerate(lines):
        cleaned = line.strip()
        lowered = cleaned.lower()
        if re.match(r"^\d+:\s+\S+:", cleaned):
            current_iface = cleaned
            if _is_loopback_iface(cleaned):
                continue
            saw_non_loopback = True
            raw_lines.append(cleaned[:220])
        elif (not current_iface or not _is_loopback_iface(current_iface)) and (lowered.startswith(("rx:", "tx:")) or re.search(r"\b(errors|dropped|carrier|collsns|overruns)\b", lowered)):
            raw_lines.append(cleaned[:220])
            if idx + 1 < len(lines):
                value_line = lines[idx + 1].strip()
                if value_line and re.search(r"\d", value_line):
                    raw_lines.append(value_line[:220])
        if len(raw_lines) >= 8:
            break
    evidence.extend(raw_lines[:8])
    if not saw_non_loopback and "lo:" in text:
        evidence.append("只看到 lo 本機迴圈介面，不代表對外網路異常；需補抓實體網卡資料才可判斷外部連線品質。")
    if not evidence:
        return ["未發現實體網卡 error/drop、TCP 重傳或 ping loss；若只有 lo，代表本機迴圈介面，不代表對外網路異常。"]
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
        if current_iface and _is_loopback_iface(current_iface):
            continue

        headers = cleaned.lower().split()
        if not headers or headers[0].rstrip(":") not in {"rx", "tx"}:
            continue
        # `dropped` is cumulative since boot. A one-shot non-zero value is often
        # historical noise on VMs, so it should not be a current WARN unless a
        # future trend check proves it is still increasing.
        watched = {"errors", "carrier", "collsns", "overruns"}
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


def _network_counter_trigger_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for line in _network_counter_issue_lines(text):
        if not line.startswith("異常 counter:"):
            continue
        tokens.update(re.findall(r"([A-Za-z_-]+)=", line))
    return {token.lower() for token in tokens}


def _network_checkpoint_statuses(text: str) -> list[dict[str, str]]:
    tokens = _network_counter_trigger_tokens(text)
    loss = _ping_loss_pct(text)
    conntrack = _conntrack_usage(text)
    time_wait = _time_wait_count(text)
    reachability_error = _network_reachability_error_seen(text)

    statuses = [
        {
            "sn": "NET-01",
            "name": "網卡 errors",
            "status": "WARN" if "errors" in tokens else "PASS",
            "evidence": "errors counter > 0" if "errors" in tokens else "未看到實體網卡 errors 增加",
        },
        {
            "sn": "NET-02",
            "name": "網卡 dropped",
            "status": "WARN" if tokens.intersection({"carrier", "collsns", "overruns"}) else "PASS",
            "evidence": "carrier/collsns/overruns counter > 0" if tokens.intersection({"carrier", "collsns", "overruns"}) else "dropped 為開機後累積值，未看到持續增加證據",
        },
        {
            "sn": "NET-03",
            "name": "TCP retransmit",
            "status": "WARN" if _tcp_retransmit_seen(text) else "PASS",
            "evidence": "偵測到 TCP retransmit" if _tcp_retransmit_seen(text) else "未看到 TCP retransmit 警示",
        },
        {
            "sn": "NET-04",
            "name": "Ping loss",
            "status": "WARN" if (loss is not None and loss > 0) or reachability_error else "PASS",
            "evidence": f"packet loss={loss:g}%" if loss is not None else ("連線或 DNS 可達性失敗" if reachability_error else "未看到 ping loss 資料"),
        },
        {
            "sn": "NET-05",
            "name": "conntrack 用量",
            "status": "WARN" if conntrack is not None and conntrack[2] >= 80 else "PASS",
            "evidence": f"nf_conntrack_count={conntrack[0]} / max={conntrack[1]} ({conntrack[2]:.1f}%)" if conntrack else "未取得 conntrack 資料",
        },
        {
            "sn": "NET-06",
            "name": "TIME_WAIT / port range",
            "status": "WARN" if time_wait >= 1000 else "PASS",
            "evidence": f"TIME_WAIT={time_wait}" if time_wait else "未看到 TIME_WAIT 過量",
        },
        {
            "sn": "NET-07",
            "name": "SYN backlog / listen drops",
            "status": "WARN" if _listen_drop_seen(text) else "PASS",
            "evidence": "偵測到 SYN backlog 或 listen drops" if _listen_drop_seen(text) else "未看到 SYN backlog 或 listen drops",
        },
    ]
    return statuses


def _network_checkpoint_lines(text: str) -> list[str]:
    return [f"{item['sn']} {item['name']}：{item['status']} - {item['evidence']}" for item in _network_checkpoint_statuses(text)]


def _network_warn_checkpoint_lines(text: str) -> list[str]:
    return [line for line in _network_checkpoint_lines(text) if "：WARN -" in line]


def _network_issue_interfaces(text: str) -> list[str]:
    interfaces: list[str] = []
    issue_lines = _network_counter_issue_lines(text)
    for line in issue_lines:
        iface = _iface_name(line)
        if iface and iface not in interfaces:
            interfaces.append(iface)
    return interfaces


def _network_fix_commands(text: str) -> str:
    interfaces = _network_issue_interfaces(text)
    if not interfaces:
        return "\n".join(
            [
                "ip -s link",
                "ss -s",
                "ping -c 5 ${PING_TGT:-127.0.0.1}",
                "若只看到 lo，代表本機迴圈介面，不要當成對外網路異常。",
            ]
        )
    commands: list[str] = []
    for iface in interfaces[:3]:
        commands.extend(
            [
                f"# {iface}",
                f"ip -s link show dev {iface}",
                f"ethtool -S {iface} 2>/dev/null | egrep -i 'error|drop|crc|timeout|collision|carrier' || true",
                f"ethtool {iface} 2>/dev/null | egrep -i 'Speed|Duplex|Link detected' || true",
                "ss -s",
                "ping -c 5 ${PING_TGT:-127.0.0.1}",
            ]
        )
    return "\n".join(commands)


def _network_pressure_fix_commands(text: str) -> str:
    commands: list[str] = []
    conntrack = _conntrack_usage(text)
    if conntrack is not None and conntrack[2] >= 80:
        commands.extend(
            [
                "# NET-05 conntrack 用量",
                "sysctl net.netfilter.nf_conntrack_count net.netfilter.nf_conntrack_max",
                "sudo conntrack -S 2>/dev/null || true",
                "ss -tan | awk 'NR>1 {print $5}' | cut -d: -f1 | sort | uniq -c | sort -nr | head -20",
            ]
        )
    if _time_wait_count(text) >= 1000:
        commands.extend(
            [
                "# NET-06 TIME_WAIT / port range",
                "ss -tan state time-wait | wc -l",
                "ss -tanp | awk 'NR>1 {print $5}' | cut -d: -f1 | sort | uniq -c | sort -nr | head -20",
                "cat /proc/sys/net/ipv4/ip_local_port_range",
            ]
        )
    return "\n".join(commands)


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
    impact_lines = _customer_impact_lines(items)
    return {
        "hostname": host["hostname"],
        "asset_seq": host["asset_seq"],
        "timestamp": job_ts,
        "display_timestamp": _display_timestamp(job_ts),
        "os": host.get("os") or host.get("os_version") or host.get("host_type"),
        "ap_port": os.environ.get("AP_PORT", str(config.WEB_PORT)),
        "ping_target": os.environ.get("PING_TGT", "127.0.0.1"),
        "status": status,
        "status_level": status_level,
        "stats": stats,
        "customer_impact": "；".join(impacts)[:1000] if impacts else "未發現明顯服務影響。",
        "customer_impact_lines": impact_lines,
        "items": items,
    }


def _customer_impact_lines(items: list[dict[str, Any]]) -> list[str]:
    lines = []
    for item in items:
        if item.get("verdict") not in {"WARN", "FAIL"}:
            continue
        text = _compact_impact_line(item)
        if not text:
            continue
        lines.append(text)
    return lines or ["未發現明顯服務影響。"]


def _compact_impact_line(item: dict[str, Any]) -> str:
    idx = int(item.get("idx") or 0)
    name = str(item.get("name") or f"面向 {idx}")
    text = "\n".join(
        str(item.get(key) or "")
        for key in ("evidence", "actual", "problem", "impact")
    )
    lowered = text.lower()
    prefix = f"{idx}. {name}："
    if idx == 1:
        parts = []
        uptime = _uptime_summary(text)
        if uptime:
            parts.append(f"開機時間 {uptime}")
        users = _online_user_summary(text)
        if users:
            parts.append(f"在線人數 {users}")
        load = _load_summary(text)
        if load:
            parts.append(f"Load {load}")
        return prefix + ("、".join(parts) if parts else "效能數值超過門檻，請看明細。")
    if idx == 2:
        issues = _network_evidence_checkpoint_lines(text) or _network_warn_checkpoint_lines(text)
        if issues:
            compact = []
            for issue in issues[:3]:
                matched = re.search(r"(NET-\d+)\s+([^：:]+)[：:]\s*(.+)", issue)
                if matched:
                    sn = matched.group(1)
                    title = matched.group(2).strip()
                    detail = matched.group(3).strip()
                    value = _short_network_issue_value(title, detail)
                    compact.append(f"{sn} {value}")
                else:
                    compact.append(issue.split(" - ", 1)[0][:60])
            return prefix + "、".join(compact)
        counters = re.findall(r"\b(errors|dropped|drop|carrier|collsns|overruns|retransmit)\b[^0-9]*(\d+)", lowered)
        if counters:
            return prefix + "、".join(f"{key}={value}" for key, value in counters[:4])
        return prefix + "網路品質有警示，請看明細確認網卡或交換器。"
    if idx == 3:
        ports = sorted(set(re.findall(r":(\d{2,5})\b", text)))[:5]
        return prefix + (f"Listener/程序需確認，涉及 port {', '.join(ports)}。" if ports else "Listener 或程序狀態需確認。")
    if idx == 4:
        port = re.search(r"port\s+(\d{2,5})", text, re.IGNORECASE)
        if "refused" in lowered or "could not connect" in lowered or "failed to connect" in lowered:
            return prefix + f"本機 health port {port.group(1) if port else 'AP'} 連線被拒絕。"
        if "timeout" in lowered:
            return prefix + "health endpoint 逾時。"
        return prefix + "AP health endpoint 未通過。"
    if idx == 5:
        counts = _tcp_state_counts(text)
        parts = [f"{key}={value}" for key, value in counts.items() if value]
        return prefix + ("、".join(parts[:4]) if parts else "TCP session 分布異常。")
    if idx == 6:
        issues = _storage_issue_lines(text)
        return prefix + ("、".join(issues[:3]) if issues else "磁碟或 inode 使用率超過門檻。")
    if idx == 7:
        if "unsynchronized" in lowered or "not synchronized" in lowered:
            return prefix + "時間同步異常。"
        return prefix + "時間或憑證需確認。"
    if idx == 8:
        db_hits = sorted(set(re.findall(r"\b(oracle|sqlservr|mysqld|mariadbd|db2sysc|postgres|mongod|1521|1433|3306|50000|5432|27017)\b", lowered)))[:5]
        return prefix + (f"DB process/port 需確認：{', '.join(db_hits)}。" if db_hits else "DB process 或 DB port 需確認。")
    if idx == 9:
        failed = _systemd_failed_issue_lines(text)
        if failed:
            services = [line.split()[0] for line in failed[:3] if line.split()]
            return prefix + f"服務啟動失敗：{', '.join(services)}。"
        tainted = _kernel_tainted_value(text)
        if tainted and tainted != "0":
            return prefix + f"kernel tainted={tainted}。"
        if "oom" in lowered:
            return prefix + "發現 OOM 記錄。"
        return prefix + "OS infra 訊息需確認。"
    if idx == 10:
        accounts = _locked_account_names(text)
        return prefix + (f"可登入帳號被鎖定：{', '.join(accounts[:6])}。" if accounts else "登入軌跡或帳號狀態需確認。")
    fallback = str(item.get("problem") or item.get("impact") or "").strip()
    fallback = fallback.split("摘要：", 1)[0].strip()
    return prefix + (fallback[:90] if fallback else "需確認。")


def _uptime_summary(text: str) -> str:
    match = re.search(r"\bup\s+(\d+)\s+days?\b", text, re.IGNORECASE)
    if match:
        return f"{match.group(1)}D"
    match = re.search(r"\bup\s+(\d+):(\d+)\b", text, re.IGNORECASE)
    if match:
        return f"{match.group(1)}H{match.group(2)}M"
    return ""


def _online_user_summary(text: str) -> str:
    matches = re.findall(r"\b(\d+)\s+users?\b", text, re.IGNORECASE)
    return matches[-1] if matches else ""


def _load_summary(text: str) -> str:
    match = re.search(r"load average:\s*([0-9.]+,\s*[0-9.]+,\s*[0-9.]+)", text, re.IGNORECASE)
    return match.group(1) if match else ""


def _network_evidence_checkpoint_lines(text: str) -> list[str]:
    lines = []
    for line in text.splitlines():
        cleaned = line.strip()
        if re.match(r"^NET-\d+", cleaned) and re.search(r"\bWARN\b", cleaned, re.IGNORECASE):
            lines.append(cleaned)
    return lines


def _short_network_issue_value(title: str, detail: str) -> str:
    lowered = f"{title} {detail}".lower()
    assigned = re.search(r"\b(errors|dropped|drop|carrier|collsns|overruns|retransmit)\s*=\s*(\d+)", lowered)
    if assigned:
        return f"{assigned.group(1)}={assigned.group(2)}"
    if "syn" in lowered or "listen" in lowered:
        return "listen drops"
    if "counter > 0" in lowered:
        if "dropped" in lowered or "drop" in lowered:
            return "dropped/drop"
        if "error" in lowered:
            return "errors"
    numeric = re.search(r"\b(errors|dropped|drop|carrier|collsns|overruns|retransmit)\b[^0-9]*(\d+)", lowered)
    if numeric:
        return f"{numeric.group(1)}={numeric.group(2)}"
    if "dropped" in lowered or "drop" in lowered:
        return "dropped/drop"
    if "retransmit" in lowered or "retrans" in lowered:
        return "TCP retransmit"
    if "ping" in lowered or "loss" in lowered:
        return "ping loss"
    if "conntrack" in lowered:
        return "conntrack"
    return title


def _summary_text(data: dict[str, Any]) -> str:
    lines = [
        f"深度檢查摘要 - {data['hostname']}",
        f"時間: {data.get('display_timestamp') or data['timestamp']}",
        f"狀態: {data['status']}",
        f"PASS={data['stats']['pass']} WARN={data['stats']['warn']} FAIL={data['stats']['fail']} N/A={data['stats']['na']}",
        f"影響摘要: {data['customer_impact']}",
        "",
    ]
    for item in data["items"]:
        lines.append(f"{item['idx']}. {item['name']} {item['verdict']} - {item['impact']}")
    return "\n".join(lines)


def _display_timestamp(value: Any) -> str:
    if not value:
        return "-"
    if isinstance(value, datetime):
        base = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        local = base.astimezone(_local_tz()).replace(second=0, microsecond=0)
        return local.strftime("%Y%m%d %H:%M")
    text = str(value)
    match = re.search(r"(\d{8})[_\s-]?(\d{2})(\d{2})(\d{2})?", text)
    if match:
        return f"{match.group(1)} {match.group(2)}:{match.group(3)}"
    iso_match = re.search(r"(\d{4})-(\d{2})-(\d{2})[T\s](\d{2}):(\d{2})", text)
    if iso_match:
        return f"{iso_match.group(1)}{iso_match.group(2)}{iso_match.group(3)} {iso_match.group(4)}:{iso_match.group(5)}"
    return text


def _normalize_report_doc(report: dict[str, Any]) -> dict[str, Any]:
    parsed = report.get("parsed")
    if isinstance(parsed, dict):
        parsed["display_timestamp"] = _display_timestamp(report.get("timestamp") or parsed.get("timestamp"))
        parsed["customer_impact_lines"] = _customer_impact_lines(parsed.get("items") or [])
    return report


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
