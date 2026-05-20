#!/usr/bin/env bash
set -euo pipefail

APP_HOME="${INSPECTION_HOME:-/opt/webitgpt}"
bash "${APP_HOME}/debug/scripts/health_check.sh"
"${APP_HOME}/venv/bin/python" -m pytest tests/test_ui_contracts.py -q
