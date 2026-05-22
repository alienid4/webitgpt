#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp import config
from webapp.services.housekeeping_service import run_all, run_post_install_housekeeping, run_task


def main() -> int:
    parser = argparse.ArgumentParser(description="Run webitgpt housekeeping tasks.")
    parser.add_argument("--mode", choices=["daily", "post-install", "task"], default="daily")
    parser.add_argument("--task", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config.ensure_runtime_dirs()
    if args.mode == "post-install":
        result = run_post_install_housekeeping()
    elif args.mode == "task":
        if not args.task:
            raise SystemExit("--task is required when --mode task")
        result = run_task(args.task, user="script", dry_run=args.dry_run)
    else:
        result = run_all(user="script", dry_run=args.dry_run)

    Path(config.LOGS_DIR).mkdir(parents=True, exist_ok=True)
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0 if result.get("status") in {"ok", "warn"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
