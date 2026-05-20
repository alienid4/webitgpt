#!/usr/bin/env bash
set -euo pipefail

APP_HOME="${INSPECTION_HOME:-/opt/webitgpt}"
export INSPECTION_HOME="$APP_HOME"
export MONGO_DB="${MONGO_DB:-webitgpt}"
export PYTHONPATH="$APP_HOME"
export FLASK_ENV=development

cd "$APP_HOME"
if [ ! -x "$APP_HOME/venv/bin/python" ]; then
  python3 -m venv "$APP_HOME/venv"
fi
"$APP_HOME/venv/bin/pip" install -r "$APP_HOME/requirements.txt"
"$APP_HOME/venv/bin/python" "$APP_HOME/scripts/bootstrap.py"
exec "$APP_HOME/venv/bin/python" -m flask --app webapp.app:app run --host 0.0.0.0 --port "${WEBITGPT_PORT:-8002}"
