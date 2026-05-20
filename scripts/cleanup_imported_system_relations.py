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
from webapp.services.dependency_service import cleanup_imported_system_relations


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove temporary Excel-imported CMDB system relations.")
    parser.add_argument("--actor", default="script")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true", help="Required for real cleanup.")
    args = parser.parse_args()

    config.ensure_runtime_dirs()
    if not args.dry_run and not args.yes:
        raise SystemExit("Refusing cleanup without --yes. Run with --dry-run first.")
    result = cleanup_imported_system_relations(actor=args.actor, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0 if result.get("status") in {"ok", "dry_run"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
