from __future__ import annotations

from webapp.runners.base_runner import Runner


class VcenterRunner(Runner):
    def self_check(self) -> dict:
        raise NotImplementedError("VMware runner is Phase 2 scope")

