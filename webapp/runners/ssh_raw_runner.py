from __future__ import annotations

import subprocess
from datetime import datetime, timezone

from webapp.runners.base_runner import Runner


class SshRawRunner(Runner):
    def collect_identity(self) -> dict:
        target = self.host.get("ip") or self.host.get("hostname")
        if not target:
            return self._identity_error("missing host address")
        ssh_user = self.host.get("ssh_user") or "sysinfra"
        ssh_port = str(self.host.get("ssh_port") or 22)
        command = "printf 'HOSTNAME=%s\\n' \"$(uname -n)\"; printf 'OS=%s\\n' \"AIX $(oslevel -s 2>/dev/null)\"; printf 'MODEL=%s\\n' \"$(uname -M 2>/dev/null)\""
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
                command,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
        )
        if completed.returncode != 0:
            return self._identity_error(completed.stderr.strip()[:200] or "AIX identity probe failed")
        values = {}
        for line in completed.stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
        return {
            "asset_seq": self.host.get("asset_seq"),
            "hostname": values.get("HOSTNAME", ""),
            "os": values.get("OS", "").strip(),
            "model": values.get("MODEL", ""),
            "runner": "ssh_raw",
            "source": "actual_runner",
            "trusted": bool(values.get("HOSTNAME") or values.get("OS")),
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

    def _identity_error(self, error: str) -> dict:
        return {
            "asset_seq": self.host.get("asset_seq"),
            "hostname": "",
            "os": "",
            "runner": "ssh_raw",
            "source": "actual_runner",
            "trusted": False,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "error": error,
        }

    def self_check(self) -> dict:
        raise NotImplementedError("AIX ssh_raw runner is Phase 3 scope")
