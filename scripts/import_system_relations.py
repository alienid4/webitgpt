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
from webapp.services.dependency_service import import_system_relations_xlsx


def main() -> int:
    parser = argparse.ArgumentParser(description="Import system relation workbook into CMDB dependency collections.")
    parser.add_argument("xlsx", help="Path to system relation xlsx.")
    parser.add_argument("--actor", default="script")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config.ensure_runtime_dirs()
    result = import_system_relations_xlsx(args.xlsx, actor=args.actor, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0 if result.get("status") in {"ok", "dry_run"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
