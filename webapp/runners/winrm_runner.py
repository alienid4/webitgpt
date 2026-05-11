from __future__ import annotations

from datetime import datetime, timezone

from webapp.runners.base_runner import Runner


class WinrmRunner(Runner):
    def self_check(self) -> dict:
        return {
            "status": "warn",
            "runner": "winrm",
            "read_only": True,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "details": {"message": "Phase 1 WinRM command wiring placeholder"},
        }

