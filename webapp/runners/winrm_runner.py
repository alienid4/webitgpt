from __future__ import annotations

from datetime import datetime, timezone

from webapp.runners.base_runner import Runner


class WinrmRunner(Runner):
    def collect_identity(self) -> dict:
        target = self.host.get("ip") or self.host.get("hostname")
        username = self.host.get("winrm_user") or self.host.get("ssh_user")
        password = self.host.get("winrm_password")
        if not target or not username or not password:
            return {
                "asset_seq": self.host.get("asset_seq"),
                "hostname": "",
                "os": "",
                "runner": "winrm",
                "source": "actual_runner",
                "trusted": False,
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "error": "WinRM identity check requires host, username and password/credential binding",
            }
        try:
            import winrm

            session = winrm.Session(str(target), auth=(str(username), str(password)))
            result = session.run_ps(
                "Write-Output ('HOSTNAME=' + $env:COMPUTERNAME); "
                "$os = Get-CimInstance Win32_OperatingSystem; "
                "Write-Output ('OS=' + $os.Caption + ' ' + $os.Version)"
            )
            if result.status_code != 0:
                raise RuntimeError(result.std_err.decode(errors="ignore")[:200])
            values = {}
            for line in result.std_out.decode(errors="ignore").splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    values[key.strip()] = value.strip()
            return {
                "asset_seq": self.host.get("asset_seq"),
                "hostname": values.get("HOSTNAME", ""),
                "os": values.get("OS", ""),
                "runner": "winrm",
                "source": "actual_runner",
                "trusted": bool(values.get("HOSTNAME") or values.get("OS")),
                "collected_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            return {
                "asset_seq": self.host.get("asset_seq"),
                "hostname": "",
                "os": "",
                "runner": "winrm",
                "source": "actual_runner",
                "trusted": False,
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "error": str(exc),
            }

    def self_check(self) -> dict:
        return {
            "status": "warn",
            "runner": "winrm",
            "read_only": True,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "details": {"message": "Phase 1 WinRM command wiring placeholder"},
        }
