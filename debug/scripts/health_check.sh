#!/usr/bin/env bash
set -euo pipefail

APP_HOME="${INSPECTION_HOME:-/opt/webitgpt}"
PORT="${WEBITGPT_PORT:-8002}"
curl -fsS "http://127.0.0.1:${PORT}/health"
test -d "${APP_HOME}/webapp"
test -d "${APP_HOME}/logs"
