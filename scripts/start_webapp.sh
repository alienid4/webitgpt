#!/usr/bin/env bash
set -euo pipefail

export INSPECTION_HOME="${INSPECTION_HOME:-/opt/webitgpt}"
cd "$INSPECTION_HOME"
exec gunicorn -w 4 -b 0.0.0.0:8002 webapp.app:app

