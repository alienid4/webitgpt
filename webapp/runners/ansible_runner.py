from __future__ import annotations

import socket
import subprocess
from datetime import datetime, timezone
from typing import Any

from webapp.runners.base_runner import Runner
from webapp.services.collection_credential_service import account_for_tier


class AnsibleRunner(Runner):
    def collect_identity(self) -> dict[str, Any]:
        target = self.host.get("ip") or self.host.get("hostname")
        if not target:
            return self._identity_error("missing host address")
        script = (
            "printf 'HOSTNAME=%s\\n' \"$(hostname -s 2>/dev/null || hostname 2>/dev/null)\"; "
            "printf 'FQDN=%s\\n' \"$(hostname -f 2>/dev/null || hostname 2>/dev/null)\"; "
            "if [ -r /etc/os-release ]; then . /etc/os-release; printf 'OS=%s\\n' \"$PRETTY_NAME\"; "
            "else printf 'OS=%s\\n' \"$(uname -s 2>/dev/null)\"; fi; "
            "printf 'KERNEL=%s\\n' \"$(uname -r 2>/dev/null)\""
        )
        if self.host.get("connection") == "local":
            completed = subprocess.run(script, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        else:
            ssh_user = self.host.get("ssh_user") or account_for_tier("L1", "sysinfra")
            ssh_port = str(self.host.get("ssh_port") or 22)
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
                    ssh_port,
                    f"{ssh_user}@{target}",
                    script,
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
            )
        return self._parse_identity(completed, "ansible")

    def _identity_error(self, error: str) -> dict[str, Any]:
        return {
            "asset_seq": self.host.get("asset_seq"),
            "hostname": "",
            "os": "",
            "runner": "ansible",
            "source": "actual_runner",
            "trusted": False,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "error": error,
        }

    def _parse_identity(self, completed: subprocess.CompletedProcess, runner: str) -> dict[str, Any]:
        if completed.returncode != 0:
            return self._identity_error(completed.stderr.strip()[:200] or "identity probe failed")
        values = {}
        for line in completed.stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
        return {
            "asset_seq": self.host.get("asset_seq"),
            "hostname": values.get("HOSTNAME", ""),
            "fqdn": values.get("FQDN", ""),
            "os": values.get("OS", ""),
            "kernel": values.get("KERNEL", ""),
            "runner": runner,
            "source": "actual_runner",
            "trusted": bool(values.get("HOSTNAME") or values.get("OS")),
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

    def self_check(self) -> dict:
        host = self.host.get("ip") or self.host.get("hostname")
        status = "warn"
        details = {"message": "missing host address"}
        if host:
            try:
                socket.create_connection((host, int(self.host.get("ssh_port") or 22)), timeout=2).close()
                status = "ok"
                details = {"tcp_22": "reachable"}
            except OSError as exc:
                status = "fail"
                details = {"tcp_22": "unreachable", "error": str(exc)}
        return {
            "status": status,
            "runner": "ansible",
            "read_only": True,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "details": details,
        }

    def collect_audit(self, scope: str = "all") -> dict[str, Any]:
        target = self.host.get("ip") or self.host.get("hostname")
        if not target:
            return self._empty_audit(scope, "missing host address")
        if self.host.get("connection") == "local":
            result = self._run_linux_probe_local()
        else:
            result = self._run_linux_probe_ssh(str(target))
        result.update(
            {
                "asset_seq": self.host.get("asset_seq"),
                "hostname": self.host.get("hostname"),
                "host_type": self.host.get("host_type"),
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "scope": scope,
                "source": "actual_host_probe",
            }
        )
        return result

    def _empty_audit(self, scope: str, error: str) -> dict[str, Any]:
        return {
            "asset_seq": self.host.get("asset_seq"),
            "hostname": self.host.get("hostname"),
            "host_type": self.host.get("host_type"),
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "scope": scope,
            "source": "actual_host_probe",
            "error": error,
            "accounts": [],
            "packages": [],
            "ports": [],
            "processes": [],
            "services": {},
            "files": {},
            "ip_rules": [],
            "settings": {},
        }

    def _probe_script(self) -> str:
        return r"""python3 - <<'PY'
import json
import os
import re
import shlex
import subprocess
from datetime import datetime

def run(cmd):
    try:
        return subprocess.run(cmd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=8).stdout
    except Exception:
        return ""

def lines(text):
    return [item.strip() for item in text.splitlines() if item.strip()]

SYSTEM_DEFAULT_ACCOUNTS = {
    "adm", "bin", "chrony", "daemon", "dbus", "ftp", "games", "halt", "lp",
    "mail", "nobody", "operator", "polkitd", "saslauth", "setroubleshoot",
    "shutdown", "sshd", "sssd", "sync", "tss",
}

passwd_rows = lines(run("getent passwd"))
privileged = set()
for group_name in ["sudo", "wheel"]:
    group_line = run("getent group " + group_name).strip()
    if group_line:
        parts = group_line.split(":")
        if len(parts) >= 4:
            privileged.update([item for item in parts[3].split(",") if item])
accounts = []
for row in passwd_rows:
    parts = row.split(":", 6)
    if len(parts) < 7:
        continue
    name, _, uid, gid, gecos, home, shell = parts
    uid_num = int(uid) if uid.isdigit() else 0
    can_login = not shell.endswith(("nologin", "false", "sync", "shutdown", "halt"))
    account_type = "服務帳號" if uid_num < 1000 or not can_login else "人員帳號"
    if name in {"root"}:
        account_type = "特權帳號"
    quoted = shlex.quote(name)
    chage = run("chage -l " + quoted + " 2>/dev/null")
    password_changed = "-"
    password_expires = "-"
    password_age_days = None
    for line in chage.splitlines():
        if line.startswith("Last password change"):
            password_changed = line.split(":", 1)[1].strip() or "-"
        elif line.startswith("Password expires"):
            password_expires = line.split(":", 1)[1].strip() or "-"
    for fmt in ["%b %d, %Y", "%Y-%m-%d"]:
        try:
            if password_changed and password_changed.lower() not in {"never", "-"}:
                password_age_days = (datetime.now() - datetime.strptime(password_changed, fmt)).days
                break
        except Exception:
            pass
    last_login = "-"
    last_login_days = None
    lastlog = run("lastlog -u " + quoted + " 2>/dev/null | tail -n 1").strip().replace("*", "")
    if "Never logged in" in lastlog or "從未登入" in lastlog:
        last_login = "從未登入"
    elif lastlog:
        pieces = lastlog.split()
        last_login = " ".join(pieces[1:]) if len(pieces) > 1 else "-"
    system_default = name in SYSTEM_DEFAULT_ACCOUNTS or name.startswith("systemd-")
    risks = []
    if name == "root" or name in privileged:
        risks.append("高權限")
    if account_type == "服務帳號" and can_login:
        risks.append("服務帳號可登入")
    if password_age_days is not None and password_age_days > 90:
        risks.append("密碼超過90天")
    if last_login == "從未登入" and can_login and not system_default:
        risks.append("從未登入")
    accounts.append({
        "name": name,
        "uid": uid_num,
        "gid": int(gid) if gid.isdigit() else None,
        "gecos": gecos,
        "home": home,
        "shell": shell,
        "status": "present",
        "account_type": account_type,
        "can_login": can_login,
        "privileged": name == "root" or name in privileged,
        "password_changed": password_changed,
        "password_expires": password_expires,
        "password_age_days": password_age_days,
        "last_login": last_login,
        "last_login_days": last_login_days,
        "risk": "、".join(risks) if risks else "正常",
    })
packages = lines(run("if command -v rpm >/dev/null 2>&1; then rpm -qa; elif command -v dpkg-query >/dev/null 2>&1; then dpkg-query -W -f='${Package}\\n'; fi"))
ports = []
for item in lines(run("ss -ltnH 2>/dev/null | awk '{print $4}'")):
    match = re.search(r":(\\d+)$", item)
    if match:
        ports.append(int(match.group(1)))
processes = sorted(set(lines(run("ps -eo comm= 2>/dev/null"))))
services = {}
for service in lines(run("systemctl list-units --type=service --state=running --no-legend --no-pager 2>/dev/null | awk '{print $1}'")):
    services[service.replace(".service", "")] = "running"
files = {}
for path in ["/etc/ssh/sshd_config", "/etc/passwd"]:
    files[path] = "present" if os.path.exists(path) else "missing"
settings = {}
for key in ["PermitRootLogin", "PasswordAuthentication"]:
    value = lines(run("awk '/^[[:space:]]*" + key + "[[:space:]]+/ {print $2}' /etc/ssh/sshd_config 2>/dev/null | tail -1"))
    if value:
        settings[key] = value[-1]
firewall_text = run("firewall-cmd --list-all 2>/dev/null; iptables -S 2>/dev/null; nft list ruleset 2>/dev/null")
ip_rules = []
if "0.0.0.0/0" in firewall_text:
    ip_rules.append("0.0.0.0/0")
print(json.dumps({
    "accounts": sorted(accounts, key=lambda item: item["name"]),
    "packages": sorted(set(packages)),
    "ports": sorted(set(ports)),
    "processes": processes,
    "services": services,
    "files": files,
    "ip_rules": ip_rules,
    "settings": settings,
}, ensure_ascii=False))
PY"""

    def _parse_probe_result(self, completed: subprocess.CompletedProcess, target: str) -> dict[str, Any]:
        if completed.returncode != 0:
            return self._empty_audit("all", f"probe failed on {target}: {completed.stderr.strip()[:200]}")
        try:
            import json

            payload = json.loads(completed.stdout.strip().splitlines()[-1])
        except Exception as exc:
            return self._empty_audit("all", f"probe parse failed on {target}: {exc}")
        return {
            "accounts": payload.get("accounts", []),
            "packages": payload.get("packages", []),
            "ports": payload.get("ports", []),
            "processes": payload.get("processes", []),
            "services": payload.get("services", {}),
            "files": payload.get("files", {}),
            "ip_rules": payload.get("ip_rules", []),
            "settings": payload.get("settings", {}),
        }

    def _run_linux_probe_local(self) -> dict[str, Any]:
        completed = subprocess.run(
            self._probe_script(),
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
        )
        return self._parse_probe_result(completed, "local")

    def _run_linux_probe_ssh(self, target: str) -> dict[str, Any]:
        ssh_user = self.host.get("ssh_user") or account_for_tier("L1", "sysinfra")
        ssh_port = str(self.host.get("ssh_port") or 22)
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
                ssh_port,
                f"{ssh_user}@{target}",
                self._probe_script(),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
        )
        return self._parse_probe_result(completed, target)
