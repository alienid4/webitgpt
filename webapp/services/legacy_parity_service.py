from __future__ import annotations

import csv
import io
import json
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from webapp import config
from webapp.services.host_service import get_host
from webapp.services.host_service import list_hosts
from webapp.services.deep_check_service import latest_report
from webapp.services.important_service_service import enabled_service_names
from webapp.services.inventory_service import DEFAULT_MIN_INTERVAL_MINUTES, inventory_history
from webapp.services.log_exception_service import assess_lines
from webapp.services.mongo_service import get_collection
from webapp.services.nmon_raw_service import nmon_raw_pipeline_status


PLATFORM_TABS = [
    {"key": "linux", "label": "Linux"},
    {"key": "windows", "label": "Windows"},
    {"key": "aix", "label": "AIX"},
    {"key": "as400", "label": "AS400"},
]

OPENING_DEFAULT_SYSTEM = "巡檢系統主機"
OPENING_ALL_SYSTEMS_VALUE = "__all__"
FILESYSTEM_WARN_PCT = 75
FILESYSTEM_FAIL_PCT = 95
EOS_WARN_DAYS = 365
EOS_WATCH_DAYS = 730

OS_EOS_CATALOG = [
    {
        "key": "rhel_9",
        "label": "Red Hat Enterprise Linux 9",
        "patterns": ["red hat enterprise linux 9", "rhel 9"],
        "eos": "2032-05-31",
        "source": "Red Hat lifecycle reference",
        "source_url": "https://access.redhat.com/support/policy/updates/errata",
    },
    {
        "key": "rocky_9",
        "label": "Rocky Linux 9",
        "patterns": ["rocky linux 9", "rocky 9"],
        "eos": "2032-05-31",
        "source": "Rocky Linux release lifecycle reference",
        "source_url": "https://docs.rockylinux.org/release_notes/",
    },
    {
        "key": "debian_13",
        "label": "Debian 13",
        "patterns": ["debian 13", "trixie"],
        "eos": "2030-06-30",
        "source": "Debian release lifecycle reference",
        "source_url": "https://www.debian.org/releases/trixie/",
    },
    {
        "key": "debian_12",
        "label": "Debian 12",
        "patterns": ["debian 12", "bookworm"],
        "eos": "2028-06-30",
        "source": "Debian release lifecycle reference",
        "source_url": "https://wiki.debian.org/LTS",
    },
    {
        "key": "windows_server_2019",
        "label": "Windows Server 2019",
        "patterns": ["windows server 2019"],
        "eos": "2029-01-09",
        "source": "Microsoft lifecycle reference",
        "source_url": "https://learn.microsoft.com/en-us/lifecycle/products/windows-server-2019",
    },
    {
        "key": "windows_server_2022",
        "label": "Windows Server 2022",
        "patterns": ["windows server 2022"],
        "eos": "2031-10-14",
        "source": "Microsoft lifecycle reference",
        "source_url": "https://learn.microsoft.com/en-us/lifecycle/products/windows-server-2022",
    },
    {
        "key": "centos_7",
        "label": "CentOS 7",
        "patterns": ["centos 7"],
        "eos": "2024-06-30",
        "source": "CentOS lifecycle reference",
        "source_url": "https://www.centos.org/centos-linux-eol/",
    },
]

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


def _is_empty_log_output(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return True
    if cleaned == "無輸出":
        return True
    lowered = cleaned.lower()
    return "no entries" in lowered or "-- no entries --" in lowered


def _first_log_lines(text: str, limit: int = 5) -> list[str]:
    lines = []
    for line in (text or "").splitlines():
        cleaned = line.strip()
        if cleaned and not cleaned.startswith("--"):
            lines.append(cleaned[:220])
        if len(lines) >= limit:
            break
    return lines


def _passwd_account_warning_names(text: str) -> list[str]:
    names: list[str] = []
    for line in (text or "").splitlines():
        match = re.search(r"passwd\[\d+\]:\s+can't view or modify password information for\s+(\S+)", line)
        if match and match.group(1) not in names:
            names.append(match.group(1))
    return names


def _log_exception_assessment(detail: str) -> dict[str, Any]:
    lines = _first_log_lines(detail, limit=50)
    return assess_lines(lines, scope="opening_log")


def _log_check_status(rc: int, detail: str) -> str:
    if rc != 0:
        return "warn"
    if _is_empty_log_output(detail):
        return "ok"
    assessment = _log_exception_assessment(detail)
    return "ok" if assessment.get("all_matched") else "warn"


def _log_check_detail(status: str, detail: str) -> str:
    evidence = _first_log_lines(detail)
    passwd_names = _passwd_account_warning_names(detail)
    exception_assessment = _log_exception_assessment(detail) if not _is_empty_log_output(detail) else {}
    if exception_assessment.get("all_matched"):
        rule_names = "、".join(exception_assessment.get("matched_rule_names") or [])
        return f"警示:已列例外\n規則:{rule_names or '未命名'}"
    if status == "ok":
        return "警示:無"
    if passwd_names:
        system_accounts = [name for name in passwd_names if name.startswith(("systemd-", "messagebus", "sshd", "dbus", "nobody"))]
        human_or_app_accounts = [name for name in passwd_names if name not in system_accounts]
        return "\n".join(
            [
                "警示:passwd 訊息",
                f"系統帳號:{', '.join(system_accounts) if system_accounts else '無'}",
                f"需確認:{', '.join(human_or_app_accounts) if human_or_app_accounts else '無'}",
            ]
        )
    if not evidence:
        evidence = ["journalctl 查詢失敗或沒有可讀內容，需確認 journald 權限與服務狀態。"]
    return "\n".join(
        [
            "警示:有日誌訊息",
            f"筆數:{len(evidence)}",
            f"第一筆:{evidence[0][:60]}",
        ]
    )


def _uptime_human_summary(text: str) -> str:
    match = re.search(r"\bup\s+(\d+)\s+days?\b", text, re.IGNORECASE)
    if match:
        return f"已開機 {match.group(1)} 天"
    match = re.search(r"\bup\s+(\d+):(\d+)", text, re.IGNORECASE)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        if hours:
            return f"已開機 {hours} 小時 {minutes} 分鐘"
        return f"已開機 {minutes} 分鐘"
    return "已取得開機狀態"


def _users_human_summary(text: str) -> str:
    matches = re.findall(r"\b(\d+)\s+users?\b", text, re.IGNORECASE)
    if not matches:
        return "目前登入人數未回報"
    count = int(matches[-1])
    return "目前無登入使用者" if count == 0 else f"目前在線人數 {count} 人"


def _connectivity_detail(status: str, raw: str) -> str:
    if status != "ok":
        return "\n".join(
            [
                "連線:異常",
                "確認:網路/SSH key",
            ]
        )
    return "\n".join(
        [
            "連線:可連線",
            f"開機:{_uptime_human_summary(raw).replace('已開機 ', '')}",
            f"登入:{_users_human_summary(raw).replace('目前在線人數 ', '').replace('目前無登入使用者', '0人')}",
        ]
    )


def _max_percent(text: str):
    values = [int(value) for value in re.findall(r"\b(\d{1,3})%", text or "") if int(value) <= 100]
    return max(values) if values else None


def _max_filesystem_usage(text: str) -> tuple[str, int | None]:
    best_mount = "Filesystem"
    best_percent = None
    for line in (text or "").splitlines():
        cleaned = line.strip()
        if not cleaned or cleaned.lower().startswith("filesystem"):
            continue
        match = re.search(r"\b(\d{1,3})%(?=\s|$)", cleaned)
        if not match:
            continue
        percent = int(match.group(1))
        if percent > 100:
            continue
        parts = cleaned.split()
        mount = parts[-1] if parts else "Filesystem"
        if best_percent is None or percent > best_percent:
            best_mount = mount
            best_percent = percent
    return best_mount, best_percent


def _filesystem_check_status(rc: int, raw: str) -> str:
    if rc != 0:
        return "warn"
    percent = _max_percent(raw)
    if percent is None:
        return "ok"
    if percent >= FILESYSTEM_FAIL_PCT:
        return "fail"
    if percent >= FILESYSTEM_WARN_PCT:
        return "warn"
    return "ok"


def _resource_check_status(rc: int, raw: str) -> str:
    if rc != 0:
        return "warn"
    percent = _max_percent(raw)
    if percent is None:
        return "ok"
    if percent >= FILESYSTEM_FAIL_PCT:
        return "fail"
    if percent >= FILESYSTEM_WARN_PCT:
        return "warn"
    return "ok"


def _cpu_usage_percent(text: str):
    line = next((item for item in (text or "").splitlines() if "Cpu" in item or "%Cpu" in item), "")
    idle = re.search(r"([0-9.]+)\s*id\b", line)
    if idle:
        return round(max(0, 100 - float(idle.group(1))))
    usage = re.search(r"CPU[:\s]+([0-9.]+)%", text or "", re.IGNORECASE)
    return round(float(usage.group(1))) if usage else None


def _iowait_percent(text: str):
    match = re.search(r"([0-9.]+)\s*wa\b", text or "")
    return round(float(match.group(1))) if match else None


def _free_percent(text: str, label: str):
    for line in (text or "").splitlines():
        if not line.strip().lower().startswith(label.lower() + ":"):
            continue
        parts = line.replace(":", " ").split()
        numbers = [float(part) for part in parts if re.fullmatch(r"\d+(?:\.\d+)?", part)]
        if len(numbers) >= 2 and numbers[0] > 0:
            return round((numbers[1] / numbers[0]) * 100)
    return None


def _short_percent(label: str, value) -> str:
    return f"{label}:{value if value is not None else '-'}%"


def _visual_rows(detail: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in (detail or "").splitlines():
        if ":" not in line:
            continue
        label, value = line.split(":", 1)
        label = label.strip()
        value = value.strip()
        if not label:
            continue
        percent_match = re.search(r"(-?\d{1,3})%", value)
        rows.append(
            {
                "label": label,
                "value": value or "-",
                "percent": max(0, min(100, int(percent_match.group(1)))) if percent_match else None,
            }
        )
    return rows


def _package_count(text: str) -> int:
    match = re.search(r"\bpackages=(\d+)\b", text or "")
    if match:
        return int(match.group(1))
    return len([line for line in (text or "").splitlines() if line.strip()])


def _package_changes(text: str) -> int:
    match = re.search(r"\bchanged_7d=(\d+)\b", text or "")
    return int(match.group(1)) if match else 0


def _top_process(text: str, column: str) -> str:
    best_name = ""
    best_value = -1.0
    for line in (text or "").splitlines():
        parts = line.split()
        if len(parts) < 4 or not parts[0].isdigit():
            continue
        try:
            cpu = float(parts[-2])
            mem = float(parts[-1])
        except ValueError:
            continue
        value = cpu if column == "cpu" else mem
        if value > best_value:
            best_name = parts[1]
            best_value = value
    if not best_name:
        return "無資料"
    return f"{best_name} {round(best_value)}%"


def _listen_ports(text: str, limit: int = 6) -> list[str]:
    ports: list[str] = []
    for match in re.finditer(r":(\d{2,5})\b", text or ""):
        port = match.group(1)
        if port not in ports:
            ports.append(port)
        if len(ports) >= limit:
            break
    return ports


def _failed_service_names(text: str) -> list[str]:
    names: list[str] = []
    for line in (text or "").splitlines():
        cleaned = line.strip()
        if not cleaned or "failed" not in cleaned.lower():
            continue
        match = re.match(r"([A-Za-z0-9_.@:-]+\.service)\b", cleaned)
        if match and match.group(1) not in names:
            names.append(match.group(1))
    return names


def _service_check_command(deep: bool = False) -> str:
    names = enabled_service_names("linux")
    status_checks = ""
    if names:
        quoted = " ".join("'" + name.replace("'", "'\\''") + "'" for name in names)
        status_checks = (
            "; echo __IMPORTANT_SERVICES__; "
            f"for svc in {quoted}; do "
            "printf '%s=' \"$svc\"; systemctl is-active \"$svc\" 2>/dev/null || true; "
            "done"
        )
    base = "systemctl --failed --no-pager || true"
    if deep:
        base += "; systemctl list-units --type=service --state=running --no-pager | head -20"
    return base + status_checks


def _important_service_statuses(text: str) -> dict[str, str]:
    statuses: dict[str, str] = {}
    marker_seen = False
    for line in (text or "").splitlines():
        cleaned = line.strip()
        if cleaned == "__IMPORTANT_SERVICES__":
            marker_seen = True
            continue
        if not marker_seen or "=" not in cleaned:
            continue
        name, value = cleaned.split("=", 1)
        name = name.strip()
        value = value.strip().lower()
        if name:
            statuses[name] = value or "unknown"
    return statuses


def _service_check_status(raw: str) -> str:
    failed = _failed_service_names(raw)
    inactive = [name for name, state in _important_service_statuses(raw).items() if state != "active"]
    return "warn" if failed or inactive else "ok"


def _service_detail(raw: str) -> str:
    failed = _failed_service_names(raw)
    statuses = _important_service_statuses(raw)
    inactive = [name for name, state in statuses.items() if state != "active"]
    lines = [f"失敗服務:{', '.join(failed[:5]) if failed else '無'}"]
    if statuses:
        lines.append(f"重要服務未啟動:{', '.join(inactive[:5]) if inactive else '無'}")
    else:
        lines.append("重要服務:未設定")
    return "\n".join(lines)


def _account_count(text: str) -> str:
    match = re.search(r"\busers=(\d+)\b", text or "")
    if match:
        return match.group(1)
    lines = [line for line in (text or "").splitlines() if ":" in line]
    if lines:
        return f"已取得帳號清冊，抽樣 {len(lines)} 筆"
    return "已取得帳號狀態"


def _locked_accounts(text: str) -> list[str]:
    names = re.findall(r"\blocked=([A-Za-z0-9_.@-]+)\b", text or "")
    return [name for name in names if not name.startswith(("systemd-", "messagebus", "sshd", "dbus", "nobody"))][:5]


def _firewall_ports(text: str) -> list[str]:
    marker = re.search(r"FIREWALL_PORTS=([^\n]*)", text or "")
    if marker:
        return re.findall(r"\b(\d{1,5})(?:/tcp|/udp)?\b", marker.group(1))
    return _listen_ports(text, limit=8)


def _java_cert_status(text: str) -> str:
    if "JAVA_CERT=not_installed" in (text or ""):
        return "未安裝"
    match = re.search(r"JAVA_CERT_DAYS=(-?\d+)", text or "")
    if not match:
        return "未安裝"
    days = int(match.group(1))
    if days < 0:
        return "已到期"
    return f"{days}天"


def _account_check_command() -> str:
    return (
        "printf 'users='; getent passwd | wc -l; "
        "if sudo -n true 2>/dev/null; then "
        "awk -F: '($7 !~ /(nologin|false)$/){print $1}' /etc/passwd | while read u; do "
        "s=$(sudo -n passwd -S \"$u\" 2>/dev/null | awk '{print $2}'); "
        "if [ \"$s\" = \"L\" ] || [ \"$s\" = \"LK\" ]; then echo locked=$u; fi; "
        "done; "
        "else echo locked_check=需要sudo; fi"
    )


def _human_diagnostic_detail(key: str, status: str, raw: str) -> str:
    if key == "connectivity":
        return _connectivity_detail(status, raw)
    if key == "resource":
        return "\n".join(
            [
                _short_percent("CPU", _cpu_usage_percent(raw)),
                _short_percent("MEMORY", _free_percent(raw, "Mem")),
                _short_percent("SWAP", _free_percent(raw, "Swap")),
            ]
        )
    if key == "filesystem":
        mount, percent = _max_filesystem_usage(raw)
        lines = [_short_percent(mount, percent), _short_percent("IO", _iowait_percent(raw))]
        if status in {"warn", "fail"} and percent is not None:
            lines.append(f"狀態:{'磁碟已接近滿載' if status == 'fail' else '磁碟需觀察'}")
        return "\n".join(lines)
    if status != "ok":
        return "\n".join(
            [
                "檢查狀態：此項目回應異常，可能需要 IT 人員確認。",
                "建議處置：先看原始證據中的錯誤訊息，修正後重新執行開門檢查。",
            ]
        )
    if key == "process":
        return "\n".join(
            [
                f"CPU最高:{_top_process(raw, 'cpu')}",
                f"MEM最高:{_top_process(raw, 'mem')}",
            ]
        )
    if key == "service":
        return _service_detail(raw)
    if key == "account":
        locked = _locked_accounts(raw)
        return "\n".join(
            [
                f"帳號總數:{_account_count(raw)}",
                f"鎖定帳號:{', '.join(locked) if locked else '無'}",
            ]
        )
    if key == "security":
        ports = _firewall_ports(raw)
        return "\n".join(
            [
                f"防火牆Port:{', '.join(ports[:8]) if ports else '無法取得'}",
                f"Java憑證:{_java_cert_status(raw)}",
            ]
        )
    if key == "package":
        count = _package_count(raw)
        return "\n".join([f"套件總數:{count}", f"近7日異動:{_package_changes(raw)}"])
    return raw or "無輸出"


def _build_diagnostic_check(key: str, label: str, rc: int, out: str, err: str) -> dict[str, Any]:
    raw = out or err or ""
    if key == "log":
        status = _log_check_status(rc, raw)
        detail = _log_check_detail(status, raw)
    elif key == "service":
        status = _service_check_status(raw) if rc == 0 else "warn"
        detail = _human_diagnostic_detail(key, status, raw)
    elif key == "filesystem":
        status = _filesystem_check_status(rc, raw)
        detail = _human_diagnostic_detail(key, status, raw)
    elif key == "resource":
        status = _resource_check_status(rc, raw)
        detail = _human_diagnostic_detail(key, status, raw)
    else:
        status = "ok" if rc == 0 else "warn"
        detail = _human_diagnostic_detail(key, status, raw)
    return {"key": key, "label": label, "status": status, "detail": detail[:1800], "raw_detail": raw[:1800], "visual_rows": _visual_rows(detail)}


def _normalize_diagnostic_row(row: dict[str, Any]) -> dict[str, Any]:
    checks = []
    changed = False
    for check in row.get("checks", []):
        if check.get("key") == "log":
            raw = check.get("raw_detail") or check.get("detail") or ""
            status = _log_check_status(0, raw)
            detail = _log_check_detail(status, raw)
            normalized = {**check, "status": status, "detail": detail[:1800], "raw_detail": raw[:1800], "visual_rows": _visual_rows(detail)}
            checks.append(normalized)
            changed = True
        elif check.get("key") in {key for key, _label in DIAGNOSTIC_ASPECTS}:
            raw = check.get("raw_detail") or check.get("detail") or ""
            if check.get("key") == "filesystem":
                status = _filesystem_check_status(0, raw)
            elif check.get("key") == "resource":
                status = _resource_check_status(0, raw)
            else:
                status = check.get("status") or "ok"
            detail = _human_diagnostic_detail(check.get("key"), status, raw)
            normalized = {**check, "status": status, "detail": detail[:1800], "raw_detail": raw[:1800], "visual_rows": _visual_rows(detail)}
            checks.append(normalized)
            changed = True
        else:
            checks.append(check)
    if changed:
        row["checks"] = checks
    return _with_diagnostic_summary(row)


def _local_linux_diagnostics(host: dict[str, Any]) -> dict[str, Any]:
    checks = []
    commands = {
        "connectivity": "hostname && uptime",
        "resource": "top -bn1 | head -5; df -h /",
        "filesystem": "top -bn1 | awk -F',' '/Cpu\\(s\\)|%Cpu/ {print $0; exit}'; df -hT | head -10",
        "process": "ps -eo pid,comm,%cpu,%mem --sort=-%cpu | head -10",
        "service": _service_check_command(),
        "account": _account_check_command(),
        "security": "printf 'FIREWALL_PORTS='; firewall-cmd --list-ports 2>/dev/null || true; command -v keytool >/dev/null 2>&1 || { echo JAVA_CERT=not_installed; exit 0; }; find /etc /opt -name '*.jks' -o -name '*.p12' 2>/dev/null | head -1 | grep -q . || echo JAVA_CERT=not_installed",
        "package": "printf 'packages='; (rpm -qa 2>/dev/null || dpkg-query -W -f='${Package}\\n' 2>/dev/null) | wc -l; echo changed_7d=0",
        "log": "journalctl -p warning --since '-24 hours' -n 10 --no-pager || true",
    }
    for key, label in DIAGNOSTIC_ASPECTS:
        try:
            rc, out, err = _shell(commands[key])
            check = _build_diagnostic_check(key, label, rc, out, err)
        except Exception as exc:
            check = {"key": key, "label": label, "status": "warn", "detail": str(exc), "raw_detail": str(exc)}
        checks.append(check)
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
        "filesystem": "top -bn1 | awk -F',' '/Cpu\\(s\\)|%Cpu/ {print $0; exit}'; df -hT; findmnt -rno TARGET,SOURCE,FSTYPE,OPTIONS | head -20",
        "process": "ps -eo pid,comm,%cpu,%mem --sort=-%cpu | head -15",
        "service": _service_check_command(deep=True),
        "account": _account_check_command(),
        "security": "printf 'FIREWALL_PORTS='; firewall-cmd --list-ports 2>/dev/null || true; command -v keytool >/dev/null 2>&1 || { echo JAVA_CERT=not_installed; exit 0; }; find /etc /opt -name '*.jks' -o -name '*.p12' 2>/dev/null | head -1 | grep -q . || echo JAVA_CERT=not_installed",
        "package": "printf 'packages='; (rpm -qa 2>/dev/null || dpkg-query -W -f='${Package}\\n' 2>/dev/null) | wc -l; echo changed_7d=0",
        "log": "journalctl -p warning --since '-24 hours' -n 20 --no-pager 2>/dev/null || tail -50 /var/log/syslog 2>/dev/null || tail -50 /var/log/messages 2>/dev/null",
    }
    for key, label in DIAGNOSTIC_ASPECTS:
        try:
            rc, out, err = _remote_linux_command(host, commands[key])
            check = _build_diagnostic_check(key, label, rc, out, err)
        except Exception as exc:
            check = {"key": key, "label": label, "status": "warn", "detail": str(exc), "raw_detail": str(exc)}
        checks.append(check)
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


def _with_host_display_fields(row: dict[str, Any], host: dict[str, Any]) -> dict[str, Any]:
    row["asset_name"] = host.get("asset_name") or row.get("asset_name") or host.get("system_name") or host.get("hostname")
    row["hostname"] = host.get("hostname") or row.get("hostname")
    row["ip"] = host.get("ip") or row.get("ip")
    row["os"] = host.get("os") or row.get("os") or host.get("host_type") or row.get("host_type")
    row["host_type"] = host.get("host_type") or row.get("host_type")
    row["system_name"] = host.get("system_name") or row.get("system_name")
    return row


def daily_diagnostics(platform: str = "linux", system_name: str = "") -> dict[str, Any]:
    platform = platform or "linux"
    all_hosts = _hosts()
    platform_hosts = [host for host in all_hosts if host.get("host_type") == platform]
    options = _system_options(platform_hosts)
    selected_system = _selected_system(system_name, options)
    hosts = [
        host
        for host in platform_hosts
        if not selected_system or _system_name(host) == selected_system
    ]
    if platform == "linux":
        rows = []
        for host in hosts:
            latest = get_collection("diagnostic_results").find_one({"asset_seq": host.get("asset_seq")}, {"_id": 0}, sort=[("checked_at", -1)])
            if latest:
                latest = _normalize_diagnostic_row(latest)
                latest = _with_host_display_fields(latest, host)
                latest["recent"] = diagnostic_history(host.get("asset_seq"), days=7, limit=6)
                latest["latest_deep_check"] = latest_report(host.get("hostname"))
                rows.append(latest)
            elif host.get("connection") == "local":
                row = _local_linux_diagnostics(host)
                row = _with_host_display_fields(row, host)
                row["recent"] = diagnostic_history(host.get("asset_seq"), days=7, limit=6)
                row["latest_deep_check"] = latest_report(host.get("hostname"))
                rows.append(row)
            else:
                row = _ssh_placeholder_diagnostics(host)
                row = _with_host_display_fields(row, host)
                row["recent"] = diagnostic_history(host.get("asset_seq"), days=7, limit=6)
                row["latest_deep_check"] = latest_report(host.get("hostname"))
                rows.append(row)
    else:
        rows = []
        for host in hosts:
            row = _ssh_placeholder_diagnostics(host)
            row = _with_host_display_fields(row, host)
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
    rows = [_normalize_diagnostic_row(row) for row in rows]
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
        cpu = _local_cpu_pct()
        network_kbps = _local_network_kbps()
        doc = {
            "asset_seq": host.get("asset_seq"),
            "hostname": host.get("hostname"),
            "sampled_at": now,
            "cpu_pct": cpu,
            "mem_pct": mem,
            "disk_pct": disk,
            "network_kbps": network_kbps,
            "load_avg": Path("/proc/loadavg").read_text(encoding="utf-8").split()[0] if Path("/proc/loadavg").exists() else "",
            "created_by": user,
            "error": err if rc != 0 else "",
        }
        get_collection("nmon_data").insert_one({**doc})
        docs.append(doc)
    return {"status": "ok", "count": len(docs), "items": docs}


def _read_network_bytes() -> int | None:
    try:
        total = 0
        for line in Path("/proc/net/dev").read_text(encoding="utf-8").splitlines()[2:]:
            if ":" not in line:
                continue
            name, payload = line.split(":", 1)
            if name.strip() == "lo":
                continue
            fields = payload.split()
            if len(fields) >= 16:
                total += int(fields[0]) + int(fields[8])
        return total
    except Exception:
        return None


def _local_network_kbps() -> float | None:
    first = _read_network_bytes()
    if first is None:
        return None
    time.sleep(0.2)
    second = _read_network_bytes()
    if second is None or second < first:
        return None
    return round((second - first) / 1024 / 0.2, 2)


def _read_cpu_ticks() -> tuple[int, int] | None:
    try:
        fields = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0].split()[1:]
        values = [int(value) for value in fields]
    except Exception:
        return None
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return idle, sum(values)


def _local_cpu_pct() -> float | None:
    first = _read_cpu_ticks()
    if not first:
        return None
    time.sleep(0.2)
    second = _read_cpu_ticks()
    if not second:
        return None
    idle_delta = second[0] - first[0]
    total_delta = second[1] - first[1]
    if total_delta <= 0:
        return None
    return round(max(0.0, min(100.0, (1 - idle_delta / total_delta) * 100)), 1)


def _avg(values: list[Any]) -> float:
    clean = [float(value) for value in values if value is not None and value != ""]
    return round(sum(clean) / len(clean), 1) if clean else 0.0


def _max(values: list[Any]) -> float:
    clean = [float(value) for value in values if value is not None and value != ""]
    return round(max(clean), 1) if clean else 0.0


def _p95(values: list[Any]) -> float:
    clean = sorted(float(value) for value in values if value is not None and value != "")
    if not clean:
        return 0.0
    index = max(0, min(len(clean) - 1, int(round((len(clean) - 1) * 0.95))))
    return round(clean[index], 1)


def _sample_status(row: dict[str, Any]) -> str:
    if row.get("error"):
        return "異常"
    if float(row.get("cpu_pct") or 0) >= 85 or float(row.get("mem_pct") or 0) >= 85 or float(row.get("disk_pct") or 0) >= 90:
        return "警示"
    return "正常"


def _pct_width(value: Any) -> float:
    try:
        return round(max(0.0, min(100.0, float(value))), 1)
    except (TypeError, ValueError):
        return 0.0


def _host_lookup() -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for host in _hosts():
        for key in [host.get("hostname"), host.get("asset_seq"), host.get("primary_ip")]:
            if key:
                lookup[str(key)] = host
                lookup[str(key).lower()] = host
    return lookup


def _host_meta_for_nmon(row: dict[str, Any], lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    for key in [row.get("hostname"), row.get("asset_seq"), row.get("primary_ip")]:
        if key and (str(key) in lookup or str(key).lower() in lookup):
            return lookup.get(str(key)) or lookup.get(str(key).lower()) or {}
    return {}


def _month_range(month: str) -> tuple[datetime, datetime] | None:
    if not month:
        return None
    try:
        start = datetime.strptime(month, "%Y-%m").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    year = start.year + (1 if start.month == 12 else 0)
    next_month = 1 if start.month == 12 else start.month + 1
    end = start.replace(year=year, month=next_month)
    return start, end


def _nmon_period_range(period: str, filters: dict[str, Any]) -> tuple[datetime, datetime, str]:
    now = _now()
    if period == "month":
        month_range = _month_range(str(filters.get("month") or ""))
        if month_range:
            return month_range[0], month_range[1], month_range[0].strftime("%Y-%m")
    since = now - {"day": timedelta(days=1), "week": timedelta(days=7), "month": timedelta(days=31)}[period]
    return since, now, since.strftime("%Y-%m")


def _nmon_filter_options(hosts: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "systems": sorted({_system_name(host) for host in hosts if _system_name(host)}),
        "environments": sorted({str(host.get("environment") or "") for host in hosts if host.get("environment")}),
        "dcs": sorted({str(host.get("dc") or "") for host in hosts if host.get("dc")}),
    }


def _matches_nmon_filters(row: dict[str, Any], host_meta: dict[str, Any], filters: dict[str, Any]) -> bool:
    system_name = _system_name(host_meta) if host_meta else str(row.get("system_name") or "")
    environment = str(host_meta.get("environment") or row.get("environment") or "")
    dc = str(host_meta.get("dc") or row.get("dc") or "")
    q = str(filters.get("q") or "").strip().lower()
    if filters.get("system") and filters["system"] != system_name:
        return False
    if filters.get("environment") and filters["environment"] != environment:
        return False
    if filters.get("dc") and filters["dc"] != dc:
        return False
    if q:
        haystack = " ".join(
            str(value or "")
            for value in [
                row.get("hostname"),
                row.get("asset_seq"),
                row.get("primary_ip"),
                host_meta.get("hostname"),
                host_meta.get("asset_name"),
                host_meta.get("primary_ip"),
                system_name,
                environment,
                dc,
            ]
        ).lower()
        if q not in haystack:
            return False
    return True


def _host_os_text(host: dict[str, Any]) -> str:
    for key in ["os", "os_version", "operating_system", "platform_version", "host_type"]:
        value = host.get(key)
        if value not in {None, ""}:
            return str(value).strip()
    return "-"


def _parse_iso_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _match_os_eos(os_text: str) -> dict[str, Any]:
    normalized = (os_text or "").lower()
    if not normalized or normalized == "-":
        return {
            "os_label": "-",
            "eos_date": None,
            "days_left": None,
            "months_left": None,
            "status": "unknown",
            "status_label": "未判斷",
            "source": "CMDB 未填 OS 版本",
            "source_url": "",
            "action": "補上實際 OS 版本後再判斷 EOS。",
        }
    for item in OS_EOS_CATALOG:
        if any(pattern in normalized for pattern in item["patterns"]):
            eos_date = _parse_iso_date(item["eos"])
            today = _now().replace(hour=0, minute=0, second=0, microsecond=0)
            days_left = (eos_date - today).days
            if days_left < 0:
                status, label = "expired", "已過 EOS"
            elif days_left <= EOS_WARN_DAYS:
                status, label = "warning", "一年內 EOS"
            elif days_left <= EOS_WATCH_DAYS:
                status, label = "watch", "兩年內 EOS"
            else:
                status, label = "ok", "仍在支援"
            return {
                "os_label": item["label"],
                "eos_date": eos_date.strftime("%Y-%m-%d"),
                "days_left": days_left,
                "months_left": round(days_left / 30.4, 1),
                "status": status,
                "status_label": label,
                "source": item["source"],
                "source_url": item.get("source_url", ""),
                "action": _eos_action(status),
            }
    return {
        "os_label": os_text,
        "eos_date": None,
        "days_left": None,
        "months_left": None,
        "status": "unknown",
        "status_label": "需補 EOS",
        "source": "未命中內建 EOS 參考表，請由系統管理補規則",
        "source_url": "",
        "action": "在系統管理補公司核准的 EOS 日期，或修正 CMDB OS 名稱。",
    }


def _eos_action(status: str) -> str:
    if status == "expired":
        return "已過支援期限，列入優先升級或隔離評估。"
    if status == "warning":
        return "一年內到期，排入升級時程與預算確認。"
    if status == "watch":
        return "兩年內到期，列入年度汰換或升級規劃。"
    return "仍在支援，維持例行盤點。"


def _build_os_lifecycle_report(hosts: list[dict[str, Any]], filters: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for host in hosts:
        if not _matches_nmon_filters({}, host, filters):
            continue
        eos = _match_os_eos(_host_os_text(host))
        rows.append(
            {
                "hostname": host.get("hostname") or host.get("asset_seq") or "-",
                "asset_seq": host.get("asset_seq") or "",
                "system_name": _system_name(host),
                "environment": host.get("environment") or "-",
                "dc": host.get("dc") or "-",
                "os": _host_os_text(host),
                **eos,
            }
        )
    priority = {"expired": 0, "warning": 1, "watch": 2, "unknown": 3, "ok": 4}
    rows = sorted(rows, key=lambda row: (priority.get(row["status"], 9), row["days_left"] if row["days_left"] is not None else 999999, row["hostname"]))
    summary = {
        "total": len(rows),
        "expired": sum(1 for row in rows if row["status"] == "expired"),
        "within_12_months": sum(1 for row in rows if row["status"] == "warning"),
        "within_24_months": sum(1 for row in rows if row["status"] == "watch"),
        "unknown": sum(1 for row in rows if row["status"] == "unknown"),
        "ok": sum(1 for row in rows if row["status"] == "ok"),
    }
    nearest = next((row for row in rows if row["eos_date"]), None)
    summary["risk_total"] = summary["expired"] + summary["within_12_months"]
    summary["nearest_label"] = f"{nearest['hostname']} / {nearest['eos_date']}" if nearest else "-"
    display_rows = [row for row in rows if row["status"] in {"expired", "warning", "watch", "unknown"}][:10]
    if not display_rows:
        display_rows = rows[:10]
    return {
        "summary": summary,
        "rows": rows[:100],
        "top_risks": display_rows,
        "catalog_source": "內建 EOS 參考表；正式環境建議由系統管理維護公司核准日期。",
    }


def _pressure_score(row: dict[str, Any]) -> float:
    return _max([row.get("cpu_pct"), row.get("mem_pct"), row.get("disk_pct")])


def _coverage_pct(sample_count: int, period: str) -> float:
    expected = {"day": 24, "week": 7 * 24, "month": 31 * 24}.get(period, 24)
    return round(min(100.0, sample_count * 100 / expected), 1) if expected else 0.0


def _build_nmon_heatmap(series: list[dict[str, Any]], period: str) -> list[dict[str, Any]]:
    result = []
    max_hosts = 12
    for item in series[:max_hosts]:
        buckets: dict[str, list[dict[str, Any]]] = {}
        for row in item.get("items_all", []):
            sampled_at = row.get("sampled_at")
            if not sampled_at:
                continue
            label = sampled_at.strftime("%H") if period == "day" else sampled_at.strftime("%m/%d")
            buckets.setdefault(label, []).append(row)
        cells = []
        for label, rows in sorted(buckets.items()):
            pressure = _max([_pressure_score(row) for row in rows])
            state = "error" if pressure >= 90 else "warn" if pressure >= 75 else "ok"
            cells.append({"label": label, "pressure": pressure, "state": state})
        result.append({"host": item.get("host"), "score": item.get("health_score"), "cells": cells[-31:]})
    return result


def _build_nmon_trend_chart(timeline: list[dict[str, Any]]) -> dict[str, Any]:
    width = 720
    height = 220
    padding_x = 36
    padding_y = 24
    plot_w = width - padding_x * 2
    plot_h = height - padding_y * 2
    if not timeline:
        return {
            "width": width,
            "height": height,
            "cpu_path": "",
            "mem_path": "",
            "disk_path": "",
            "points": [],
            "labels": [],
            "y_ticks": [],
            "x_axis_label": "時間",
            "y_axis_label": "使用率 (%)",
        }

    count = max(len(timeline) - 1, 1)

    def point(index: int, value: Any) -> tuple[float, float]:
        pct = max(0.0, min(100.0, float(value or 0)))
        x = padding_x + (plot_w * index / count)
        y = padding_y + plot_h - (plot_h * pct / 100.0)
        return round(x, 1), round(y, 1)

    def path(field: str) -> str:
        return " ".join(f"{x},{y}" for x, y in (point(i, item.get(field)) for i, item in enumerate(timeline)))

    points = []
    for index, item in enumerate(timeline):
        x, _ = point(index, 0)
        points.append(
            {
                "label": item.get("label"),
                "x": x,
                "cpu": item.get("avg_cpu", 0),
                "mem": item.get("avg_mem", 0),
                "disk": item.get("avg_disk", 0),
                "samples": item.get("samples", 0),
            }
        )

    return {
        "width": width,
        "height": height,
        "cpu_path": path("avg_cpu"),
        "mem_path": path("avg_mem"),
        "disk_path": path("avg_disk"),
        "points": points,
        "labels": points[-8:],
        "y_ticks": [
            {"label": "100%", "x": 6, "y": padding_y + 6},
            {"label": "50%", "x": 14, "y": padding_y + plot_h / 2 + 6},
            {"label": "0%", "x": 22, "y": padding_y + plot_h + 4},
        ],
        "x_axis_label": "時間",
        "y_axis_label": "使用率 (%)",
    }


def _nmon_chart_value(row: dict[str, Any], field: str) -> Any:
    if field == "network_kbps":
        values = [
            row.get("network_kbps"),
            row.get("net_kbps"),
            row.get("net_total_kbps"),
        ]
        if any(value not in {None, ""} for value in values):
            return next(value for value in values if value not in {None, ""})
        read_kbps = row.get("net_read_kbps")
        write_kbps = row.get("net_write_kbps")
        if read_kbps not in {None, ""} or write_kbps not in {None, ""}:
            return float(read_kbps or 0) + float(write_kbps or 0)
        return None
    return row.get(field)


def _build_nmon_metric_chart(items: list[dict[str, Any]], field: str, value_label: str) -> dict[str, Any]:
    width = 640
    height = 220
    padding_x = 32
    padding_y = 24
    plot_w = width - padding_x * 2
    plot_h = height - padding_y * 2
    values = []
    for row in items:
        value = _nmon_chart_value(row, field)
        if value in {None, ""}:
            continue
        try:
            values.append((row.get("sampled_at"), round(float(value), 2)))
        except (TypeError, ValueError):
            continue
    values = values[-96:]
    axis_unit = "KB/s" if field == "network_kbps" else "%"
    if not values:
        return {
            "width": width,
            "height": height,
            "path": "",
            "points": [],
            "max": None,
            "min": None,
            "avg": None,
            "last": None,
            "value_label": value_label,
            "axis_unit": axis_unit,
            "x_axis_label": "時間",
            "y_axis_label": f"{value_label} ({axis_unit})",
            "y_ticks": [],
        }

    max_value = max(100.0 if field != "network_kbps" else 1.0, max(value for _, value in values))
    count = max(len(values) - 1, 1)

    points = []
    path_parts = []
    for index, (sampled_at, value) in enumerate(values):
        x = padding_x + (plot_w * index / count)
        y = padding_y + plot_h - (plot_h * max(0.0, value) / max_value)
        label = sampled_at.strftime("%H:%M") if hasattr(sampled_at, "strftime") else "-"
        point = {"x": round(x, 1), "y": round(y, 1), "value": value, "label": label}
        points.append(point)
        path_parts.append(f"{point['x']},{point['y']}")

    return {
        "width": width,
        "height": height,
        "path": " ".join(path_parts),
        "points": points,
        "max": round(max(value for _, value in values), 1),
        "min": round(min(value for _, value in values), 1),
        "avg": round(sum(value for _, value in values) / len(values), 1),
        "last": points[-1],
        "value_label": value_label,
        "axis_unit": axis_unit,
        "x_axis_label": "時間",
        "y_axis_label": f"{value_label} ({axis_unit})",
        "y_ticks": [
            {"label": f"{round(max_value, 1)}{axis_unit}", "x": 4, "y": padding_y + 6},
            {"label": f"{round(max_value / 2, 1)}{axis_unit}", "x": 4, "y": padding_y + plot_h / 2 + 6},
            {"label": f"0{axis_unit}", "x": 16, "y": padding_y + plot_h + 4},
        ],
    }


def _build_nmon_host_charts(series: list[dict[str, Any]], period: str) -> list[dict[str, Any]]:
    suffix = {"day": "日內時序", "week": "週內時序", "month": "月內時序"}.get(period, "時序")
    result = []
    for item in series[:12]:
        samples = item.get("items_all", [])
        host = item.get("host") or "-"
        result.append(
            {
                "host": host,
                "system_name": item.get("system_name") or "-",
                "charts": [
                    {"title": f"{host} · CPU 使用率 · {suffix}", "unit": "%", "data": _build_nmon_metric_chart(samples, "cpu_pct", "CPU")},
                    {"title": f"{host} · 記憶體使用率 · {suffix}", "unit": "%", "data": _build_nmon_metric_chart(samples, "mem_pct", "RAM")},
                    {"title": f"{host} · 磁碟最忙 (%busy) · {suffix}", "unit": "%", "data": _build_nmon_metric_chart(samples, "disk_pct", "Disk")},
                    {"title": f"{host} · 網路吞吐 · {suffix}", "unit": "KB/s", "data": _build_nmon_metric_chart(samples, "network_kbps", "Network")},
                ],
            }
        )
    return result


def _series_growth(items: list[dict[str, Any]], field: str) -> float:
    values = [float(item.get(field) or 0) for item in items if item.get(field) is not None]
    if len(values) < 2:
        return 0.0
    return round(values[-1] - values[0], 1)


def _days_to_threshold(items: list[dict[str, Any]], field: str, threshold: float = 90.0) -> Any:
    dated_values = [(item.get("sampled_at"), float(item.get(field) or 0)) for item in items if item.get("sampled_at") and item.get(field) is not None]
    if len(dated_values) < 2:
        return None
    first_time, first_value = dated_values[0]
    last_time, last_value = dated_values[-1]
    days = max((last_time - first_time).total_seconds() / 86400, 1.0)
    daily_growth = (last_value - first_value) / days
    if daily_growth <= 0 or last_value >= threshold:
        return 0 if last_value >= threshold else None
    return max(1, int((threshold - last_value) / daily_growth))


def _build_nmon_architecture_summary(series: list[dict[str, Any]], summary: dict[str, Any], count: int) -> dict[str, Any]:
    if count == 0:
        return {
            "state": "待採樣",
            "observation": "目前沒有採樣資料，尚無法判讀容量與趨勢。",
            "reason": "請先執行採樣，或確認 nmon 排程是否已部署。",
            "impact": "沒有資料時，報表只能顯示納管狀態，不能作為容量判斷依據。",
            "options": "可選擇立即採樣、部署排程，或匯入既有 nmon 歷史資料。",
            "operation": "尚無效能樣本。",
            "capacity": "尚無容量樣本。",
            "cost": "尚無回收判斷。",
            "followup": "完成採樣後再產生月報。",
            "decision_count": 0,
            "immediate_count": 0,
            "followup_count": 0,
            "reclaim_count": 0,
            "risk_label": "無資料",
        }

    capacity_candidates = [item for item in series if item.get("peak_disk", 0) >= 80 or item.get("disk_growth", 0) >= 5]
    immediate_candidates = [item for item in series if item.get("peak_cpu", 0) >= 95 or item.get("peak_mem", 0) >= 95 or item.get("peak_disk", 0) >= 95]
    reclaim_candidates = [
        item
        for item in series
        if item.get("samples", 0) >= 3 and item.get("avg_cpu", 0) < 10 and item.get("avg_mem", 0) < 35 and item.get("avg_disk", 0) < 40
    ]
    top_capacity = max(series, key=lambda item: (item.get("peak_disk", 0), item.get("disk_growth", 0)), default={})
    top_host = top_capacity.get("host", "-")
    top_disk = top_capacity.get("peak_disk", 0)
    growth = top_capacity.get("disk_growth", 0)
    days = top_capacity.get("days_to_disk_90")
    if capacity_candidates:
        observation = f"{top_host} 磁碟最高 {top_disk}%，本期變化 {growth:+.1f}%。"
        if days is not None:
            observation += " 已達 90% 門檻。" if days == 0 else f" 依目前趨勢約 {days} 天接近 90%。"
        risk_label = "待確認"
    elif summary.get("warn_samples", 0):
        observation = f"本期共有 {summary.get('warn_samples', 0)} 筆警示樣本，需查看主機排名確認來源。"
        risk_label = "觀察"
    else:
        observation = "本期 CPU、記憶體與磁碟未達主要警示門檻。"
        risk_label = "正常"

    return {
        "state": risk_label,
        "observation": observation,
        "reason": "依採樣資料計算 CPU、記憶體、磁碟尖峰與本期變化。",
        "impact": "若容量持續上升，可能影響報表產生、log 寫入或批次作業。",
        "options": "可選擇清理舊檔、調整保留天數、擴充磁碟或列入下期觀察。",
        "operation": "未看到 CPU、記憶體或 I/O 長時間壅塞。" if not immediate_candidates else "有主機曾達高水位，請看風險追蹤清單。",
        "capacity": "磁碟是本期主要容量觀察項。" if capacity_candidates else "未看到接近容量門檻的主機。",
        "cost": "目前沒有明顯過度配置主機。" if not reclaim_candidates else f"{len(reclaim_candidates)} 台主機可列入資源回收觀察。",
        "followup": "下期追蹤容量變化與尖峰時段。" if capacity_candidates or summary.get("warn_samples", 0) else "維持例行採樣。",
        "decision_count": len(capacity_candidates),
        "immediate_count": len(immediate_candidates),
        "followup_count": len(capacity_candidates) + (1 if summary.get("warn_samples", 0) and not capacity_candidates else 0),
        "reclaim_count": len(reclaim_candidates),
        "risk_label": risk_label,
    }


def _build_nmon_risk_rows(series: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in series:
        host = item.get("host", "-")
        if item.get("peak_disk", 0) >= 80 or item.get("disk_growth", 0) >= 5:
            days = item.get("days_to_disk_90")
            evidence = f"磁碟最高 {item.get('peak_disk', 0)}%，本期變化 {item.get('disk_growth', 0):+.1f}%"
            if days is not None:
                evidence += "，已達 90% 門檻" if days == 0 else f"，約 {days} 天接近 90%"
            rows.append(
                {
                    "priority": "P1" if item.get("peak_disk", 0) >= 90 else "P2",
                    "item": "磁碟容量",
                    "host": host,
                    "evidence": evidence,
                    "horizon": "本期確認" if item.get("peak_disk", 0) >= 90 else "下期觀察",
                    "status": "待確認",
                    "option": "清理舊檔、調整保留天數、擴充磁碟或列入下期觀察。",
                }
            )
        if item.get("peak_cpu", 0) >= 85:
            rows.append(
                {
                    "priority": "P2",
                    "item": "CPU 尖峰",
                    "host": host,
                    "evidence": f"CPU 尖峰 {item.get('peak_cpu', 0)}%",
                    "horizon": "下期觀察",
                    "status": "觀察",
                    "option": "比對尖峰時間、批次排程與 AP 負載。",
                }
            )
        if item.get("peak_mem", 0) >= 85:
            rows.append(
                {
                    "priority": "P2",
                    "item": "記憶體尖峰",
                    "host": host,
                    "evidence": f"記憶體尖峰 {item.get('peak_mem', 0)}%",
                    "horizon": "下期觀察",
                    "status": "觀察",
                    "option": "比對程式版本、批次時間與長駐程序。",
                }
            )
    return sorted(rows, key=lambda item: (item["priority"], item["host"], item["item"]))[:10]


def nmon_report(period: str = "day", filters: Any = None) -> dict[str, Any]:
    period = period if period in {"day", "week", "month"} else "day"
    filters = filters or {}
    since, until, month_label = _nmon_period_range(period, filters)
    host_lookup = _host_lookup()
    all_hosts = _hosts()
    filter_options = _nmon_filter_options(all_hosts)
    rows = list(get_collection("nmon_data").find({"sampled_at": {"$gte": since, "$lt": until}}, {"_id": 0}).sort("sampled_at", 1).limit(20000))
    filtered_rows = []
    for row in rows:
        host_meta = _host_meta_for_nmon(row, host_lookup)
        if not _matches_nmon_filters(row, host_meta, filters):
            continue
        row["system_name"] = _system_name(host_meta) if host_meta else row.get("system_name", "-")
        row["environment"] = host_meta.get("environment") or row.get("environment") or "-"
        row["dc"] = host_meta.get("dc") or row.get("dc") or "-"
        row["primary_ip"] = host_meta.get("primary_ip") or row.get("primary_ip") or ""
        filtered_rows.append(row)
    rows = filtered_rows
    by_host: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        row["status"] = _sample_status(row)
        by_host.setdefault(row.get("hostname") or row.get("asset_seq") or "-", []).append(row)
    series = []
    for host, items in by_host.items():
        host_meta = host_lookup.get(host) or host_lookup.get(str(host).lower()) or _host_meta_for_nmon(items[-1], host_lookup)
        disk_growth = _series_growth(items, "disk_pct")
        peak_cpu = _max([item.get("cpu_pct") for item in items])
        peak_mem = _max([item.get("mem_pct") for item in items])
        peak_disk = _max([item.get("disk_pct") for item in items])
        health_score = round(max(0.0, 100.0 - max(peak_cpu, peak_mem, peak_disk)), 1)
        series.append(
            {
                "host": host,
                "asset_seq": host_meta.get("asset_seq", items[-1].get("asset_seq") if items else ""),
                "system_name": host_meta.get("system_name") or host_meta.get("asset_name") or "-",
                "environment": host_meta.get("environment") or "-",
                "dc": host_meta.get("dc") or "-",
                "samples": len(items),
                "coverage_pct": _coverage_pct(len(items), period),
                "health_score": health_score,
                "avg_cpu": _avg([item.get("cpu_pct") for item in items]),
                "avg_mem": _avg([item.get("mem_pct") for item in items]),
                "avg_disk": _avg([item.get("disk_pct") for item in items]),
                "p95_cpu": _p95([item.get("cpu_pct") for item in items]),
                "p95_mem": _p95([item.get("mem_pct") for item in items]),
                "p95_disk": _p95([item.get("disk_pct") for item in items]),
                "peak_cpu": peak_cpu,
                "peak_mem": peak_mem,
                "peak_disk": peak_disk,
                "disk_growth": disk_growth,
                "days_to_disk_90": _days_to_threshold(items, "disk_pct", 90),
                "warn_count": sum(1 for item in items if item["status"] != "正常"),
                "items_all": items,
                "items": items[-24:],
            }
        )
    series = sorted(series, key=lambda item: (-item["warn_count"], -item["peak_cpu"], -item["peak_mem"], item["host"]))
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        sampled_at = row.get("sampled_at")
        if not sampled_at:
            continue
        key = sampled_at.strftime("%H:00") if period == "day" else sampled_at.strftime("%m/%d")
        buckets.setdefault(key, []).append(row)
    timeline = [
        {
            "label": key,
            "avg_cpu": _avg([row.get("cpu_pct") for row in items]),
            "avg_mem": _avg([row.get("mem_pct") for row in items]),
            "avg_disk": _avg([row.get("disk_pct") for row in items]),
            "samples": len(items),
        }
        for key, items in sorted(buckets.items())
    ]
    trend_chart = _build_nmon_trend_chart(timeline)
    summary = {
        "hosts": len(by_host),
        "managed_hosts": len(filter_options["systems"]) and len(all_hosts) or 0,
        "avg_cpu": _avg([row.get("cpu_pct") for row in rows]),
        "avg_mem": _avg([row.get("mem_pct") for row in rows]),
        "avg_disk": _avg([row.get("disk_pct") for row in rows]),
        "peak_cpu": _max([row.get("cpu_pct") for row in rows]),
        "peak_mem": _max([row.get("mem_pct") for row in rows]),
        "peak_disk": _max([row.get("disk_pct") for row in rows]),
        "warn_samples": sum(1 for row in rows if row["status"] != "正常"),
        "avg_coverage": _avg([item.get("coverage_pct") for item in series]),
        "tracked_hosts": sum(1 for item in series if item.get("warn_count") or item.get("peak_disk", 0) >= 80 or item.get("peak_cpu", 0) >= 85 or item.get("peak_mem", 0) >= 85),
    }
    architecture = _build_nmon_architecture_summary(series, summary, len(rows))
    risk_rows = _build_nmon_risk_rows(series)
    top_pressure = series[:5]
    heatmap = _build_nmon_heatmap(series, period)
    host_charts = _build_nmon_host_charts(series, period)
    os_lifecycle = _build_os_lifecycle_report(all_hosts, filters)
    return {
        "period": period,
        "period_label": {"day": "日報", "week": "週報", "month": "月報"}[period],
        "month": month_label,
        "filters": filters,
        "filter_options": filter_options,
        "since": since,
        "until": until,
        "count": len(rows),
        "summary": summary,
        "architecture": architecture,
        "risk_rows": risk_rows,
        "top_pressure": top_pressure,
        "heatmap": heatmap,
        "series": series,
        "timeline": timeline,
        "trend_chart": trend_chart,
        "host_charts": host_charts,
        "os_lifecycle": os_lifecycle,
        "rows": rows[-300:],
        "raw_pipeline": nmon_raw_pipeline_status(),
        "generated_at": _now(),
    }


def nmon_report_csv(period: str = "day", filters: Any = None) -> str:
    report = nmon_report(period, filters)
    output = io.StringIO()
    fields = ["sampled_at", "asset_seq", "hostname", "system_name", "environment", "dc", "status", "cpu_pct", "mem_pct", "disk_pct", "load_avg", "source", "error"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in report["rows"]:
        writer.writerow(row)
    return output.getvalue()


def nmon_monthly_plan() -> dict[str, Any]:
    return {
        "status": "planned",
        "frequency": "每 5 分鐘採樣、每日彙總、每月產生月報",
        "retention": "raw 30 天、日彙總 400 天",
        "charts": ["CPU 趨勢", "記憶體趨勢", "磁碟使用率", "尖峰排名", "警示樣本"],
        "next_steps": ["建立排程採樣服務", "新增 nmon_daily_rollups collection", "補 Windows/AIX 採樣 runner"],
    }


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
