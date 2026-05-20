#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp.services.debug_bundle_service import mask_debug_text


def main() -> int:
    parser = argparse.ArgumentParser(description="Mask sensitive data for GPT Enterprise debug analysis.")
    parser.add_argument("input", nargs="?", help="Input file. Reads stdin when omitted.")
    parser.add_argument("-o", "--output", help="Output file. Writes stdout when omitted.")
    args = parser.parse_args()

    if args.input:
        text = Path(args.input).read_text(encoding="utf-8", errors="replace")
    else:
        text = sys.stdin.read()
    masked = mask_debug_text(text)
    if args.output:
        Path(args.output).write_text(masked, encoding="utf-8")
    else:
        sys.stdout.write(masked)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
