#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

ENV_FILE="${1:-}"
if [ -n "$ENV_FILE" ]; then
  if [ ! -f "$ENV_FILE" ]; then
    echo "Config file not found: $ENV_FILE" >&2
    exit 1
  fi
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

export WEBITGPT_SEED_DEMO_HOSTS="${WEBITGPT_SEED_DEMO_HOSTS:-0}"
export WEBITGPT_CLEANUP_TEST_DATA="${WEBITGPT_CLEANUP_TEST_DATA:-0}"

if [ -d "$ROOT/wheelhouse" ] || [ -d "$SCRIPT_DIR/wheelhouse" ]; then
  exec bash "$SCRIPT_DIR/install_offline.sh"
fi

exec bash "$SCRIPT_DIR/install.sh"
