from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any


class Runner(ABC):
    def __init__(self, host: dict[str, Any]) -> None:
        self.host = host

    @abstractmethod
    def self_check(self) -> dict[str, Any]:
        raise NotImplementedError

    def collect_debug_snapshot(self) -> dict[str, Any]:
        return {
            "asset_seq": self.host.get("asset_seq"),
            "hostname": self.host.get("hostname"),
            "host_type": self.host.get("host_type"),
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "sections": {
                "host": self.host,
                "runner": self.__class__.__name__,
            },
        }

    def collect_audit(self, scope: str = "all") -> dict[str, Any]:
        return {
            "asset_seq": self.host.get("asset_seq"),
            "hostname": self.host.get("hostname"),
            "host_type": self.host.get("host_type"),
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "scope": scope,
            "source": "not_collected",
            "accounts": [],
            "packages": [],
            "ports": [],
            "processes": [],
            "services": {},
            "files": {},
            "ip_rules": [],
            "settings": {},
        }

    def collect_identity(self) -> dict[str, Any]:
        return {
            "asset_seq": self.host.get("asset_seq"),
            "hostname": "",
            "os": "",
            "runner": self.__class__.__name__,
            "source": "not_collected",
            "trusted": False,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "error": "identity collection is not implemented for this runner",
        }

    def write_operation(self, name: str) -> dict[str, Any]:
        raise NotImplementedError("Monitored-host writes are disabled in parallel review mode")
