#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8002}"
EXPECTED_VERSION="${EXPECTED_VERSION:-}"
TIMEOUT="${TIMEOUT:-8}"

check() {
  local name="$1"
  local url="$2"
  local body
  if ! body="$(curl -fsS --max-time "$TIMEOUT" "$url")"; then
    echo "FAIL $name $url"
    return 1
  fi
  echo "OK $name"
  printf '%s\n' "$body" | head -c 500
  printf '\n'
}

health="$(curl -fsS --max-time "$TIMEOUT" "$BASE_URL/health")"
echo "OK health"
printf '%s\n' "$health"

if [ -n "$EXPECTED_VERSION" ]; then
  printf '%s' "$health" | grep -q "\"version\":\"$EXPECTED_VERSION\"" || {
    echo "FAIL version expected=$EXPECTED_VERSION"
    exit 1
  }
fi

check ready "$BASE_URL/ready"
check accounts "$BASE_URL/accounts"
check ap_template "$BASE_URL/accounts/ap-template.xlsx"
check dependencies "$BASE_URL/dependencies?view=core_impact"
check data_quality "$BASE_URL/api/reports/data-quality"

if command -v systemctl >/dev/null 2>&1; then
  systemctl is-active --quiet webitgpt.service && echo "OK systemd webitgpt.service" || echo "WARN systemd webitgpt.service not active"
fi

echo "post-install verification completed"
