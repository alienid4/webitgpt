from __future__ import annotations

from webapp.runners.base_runner import Runner


class As400Runner(Runner):
    def self_check(self) -> dict:
        raise NotImplementedError("AS400 runner is Phase 4 scope")

