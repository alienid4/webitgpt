from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from webapp.services.debug_bundle_service import create_ai_debug_loop


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a sanitized AI debug loop for GPT Enterprise.")
    parser.add_argument("--title", required=True, help="Short issue title.")
    parser.add_argument("--detail", default="", help="Issue detail, steps, expected result, actual result.")
    parser.add_argument("--created-by", default="ai_debug_loop.py")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    result = create_ai_debug_loop(args.title, args.detail, created_by=args.created_by, verbose=args.verbose)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
