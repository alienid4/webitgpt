#!/usr/bin/env bash
set -euo pipefail

APP_HOME="${INSPECTION_HOME:-/opt/webitgpt}"
bash "${APP_HOME}/scripts/collect_debug_bundle.sh"
