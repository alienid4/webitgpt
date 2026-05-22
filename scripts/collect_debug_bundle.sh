#!/usr/bin/env bash
set -euo pipefail

APP_HOME="${INSPECTION_HOME:-/opt/webitgpt}"
PYTHON_BIN="${APP_HOME}/venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="${PYTHON_BIN_OVERRIDE:-python3}"
fi

cd "$APP_HOME"
"$PYTHON_BIN" - <<'PY'
from webapp.services.debug_bundle_service import collect_debug_bundle

result = collect_debug_bundle(created_by="collect_debug_bundle.sh", verbose=False)
print(result["path"])
PY
