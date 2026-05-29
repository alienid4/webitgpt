#!/usr/bin/env bash
set -euo pipefail

PATCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${1:-$(pwd)}"
STAMP="$(date +%Y%m%d%H%M%S)"

if [ ! -d "$TARGET_DIR/packages" ]; then
  echo "Target must be the extracted webitgpt full offline directory containing packages/." >&2
  echo "Usage: bash install_patch_rhel96_installer.sh /path/to/webitgpt_full_offline_..." >&2
  exit 1
fi

prereq_archive="$(find "$TARGET_DIR/packages" -maxdepth 1 -type f -name 'webitgpt_prereqs_*.tar.gz' | head -n 1 || true)"
if [ -z "$prereq_archive" ]; then
  echo "Missing prerequisite archive under $TARGET_DIR/packages." >&2
  exit 1
fi

work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

tar -xzf "$prereq_archive" -C "$work_dir"
prereq_dir="$(find "$work_dir" -maxdepth 1 -type d -name 'webitgpt_prereqs_*' | head -n 1 || true)"
if [ -z "$prereq_dir" ]; then
  echo "Cannot locate extracted webitgpt_prereqs_* directory." >&2
  exit 1
fi

cp "$PATCH_DIR/scripts/install_prereqs_offline.sh" "$prereq_dir/install_prereqs_offline.sh"
chmod +x "$prereq_dir/install_prereqs_offline.sh"

cp "$prereq_archive" "$prereq_archive.bak.$STAMP"
tar -czf "$prereq_archive" -C "$work_dir" "$(basename "$prereq_dir")"

if [ -f "$TARGET_DIR/INSTALL_ALL.sh" ]; then
  cp "$TARGET_DIR/INSTALL_ALL.sh" "$TARGET_DIR/INSTALL_ALL.sh.bak.$STAMP"
  python3 - "$TARGET_DIR/INSTALL_ALL.sh" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
old = """prereq_archive="$(find "$SCRIPT_DIR/packages" -maxdepth 1 -type f -name 'webitgpt_prereqs_*.tar.gz' | head -n 1 || true)"
if [ -z "$prereq_archive" ]; then
  echo "Missing prerequisite archive in packages/." >&2
  exit 1
fi
tar -xzf "$prereq_archive" -C "$WORK_DIR"
prereq_dir="$(find "$WORK_DIR" -maxdepth 1 -type d -name 'webitgpt_prereqs_*' | head -n 1)"
normalize_shell_scripts "$prereq_dir"
bash "$prereq_dir/install_prereqs_offline.sh"
"""
new = """if [ "${SKIP_PREREQS:-0}" = "1" ]; then
  echo "SKIP_PREREQS=1; skipping prerequisite archive install."
else
  prereq_archive="$(find "$SCRIPT_DIR/packages" -maxdepth 1 -type f -name 'webitgpt_prereqs_*.tar.gz' | head -n 1 || true)"
  if [ -z "$prereq_archive" ]; then
    echo "Missing prerequisite archive in packages/." >&2
    exit 1
  fi
  tar -xzf "$prereq_archive" -C "$WORK_DIR"
  prereq_dir="$(find "$WORK_DIR" -maxdepth 1 -type d -name 'webitgpt_prereqs_*' | head -n 1)"
  normalize_shell_scripts "$prereq_dir"
  bash "$prereq_dir/install_prereqs_offline.sh"
fi
"""
if old in text and "SKIP_PREREQS=1; skipping prerequisite archive install." not in text:
    path.write_text(text.replace(old, new))
PY
  chmod +x "$TARGET_DIR/INSTALL_ALL.sh"
fi

cat <<EOF
RHEL 9.6 installer hotfix applied.

Backups:
  $prereq_archive.bak.$STAMP
  $TARGET_DIR/INSTALL_ALL.sh.bak.$STAMP

Recommended retry:
  USE_NATIVE_REPOS=1 sudo bash INSTALL_ALL.sh

If OS prerequisites are already installed:
  SKIP_RPMS=1 sudo bash INSTALL_ALL.sh

If OS prerequisites and MongoDB are already prepared:
  SKIP_PREREQS=1 sudo bash INSTALL_ALL.sh
EOF
