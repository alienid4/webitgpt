#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${OUT_DIR:-$ROOT/dist}"
PATCH_NAME="${PATCH_NAME:-patch_webitgpt_v1.0.2.24-asset-governance-status-admin}"
WORK="$OUT_DIR/$PATCH_NAME"

rm -rf "$WORK"
mkdir -p "$WORK/files"
cp "$ROOT/README.md" "$WORK/README.md"
cp "$ROOT/scripts/install.sh" "$WORK/install.sh"
if command -v rsync >/dev/null 2>&1; then
  rsync -a \
    --exclude 'dist/' \
    --exclude 'venv/' \
    --exclude '__pycache__/' \
    --exclude '.pytest_cache/' \
    --exclude 'data/' \
    --exclude 'logs/' \
    --exclude 'tmp/' \
    --exclude 'backup/' \
    "$ROOT/" "$WORK/files/"
else
  tar \
    --exclude './dist' \
    --exclude './venv' \
    --exclude './__pycache__' \
    --exclude './.pytest_cache' \
    --exclude './data' \
    --exclude './logs' \
    --exclude './tmp' \
    --exclude './backup' \
    -C "$ROOT" -cf - . | tar -C "$WORK/files" -xf -
fi
tar -czf "$OUT_DIR/$PATCH_NAME.tar.gz" -C "$OUT_DIR" "$PATCH_NAME"
echo "$OUT_DIR/$PATCH_NAME.tar.gz"
