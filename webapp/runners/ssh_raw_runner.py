from __future__ import annotations

from webapp.runners.base_runner import Runner


class SshRawRunner(Runner):
    def self_check(self) -> dict:
        raise NotImplementedError("AIX ssh_raw runner is Phase 3 scope")

