#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8002}"
EXPECTED_VERSION="${EXPECTED_VERSION:-}"
TIMEOUT="${TIMEOUT:-8}"
API_TOKEN="${API_TOKEN:-}"
API_VERIFY_PATH="${API_VERIFY_PATH:-/api/v1/post-install/verify}"

check() {
  local name="$1"
  local url="$2"
  local body_file
  body_file="$(mktemp)"
  if ! curl -fsS --max-time "$TIMEOUT" -o "$body_file" "$url"; then
    echo "FAIL $name $url"
    rm -f "$body_file"
    return 1
  fi
  echo "OK $name"
  LC_ALL=C tr -cd '\11\12\15\40-\176' < "$body_file" | head -c 500 || true
  printf '\n'
  rm -f "$body_file"
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

if [ -n "$API_TOKEN" ]; then
  api_url="$BASE_URL$API_VERIFY_PATH"
  if [ -n "$EXPECTED_VERSION" ]; then
    api_url="$api_url?expected_version=$EXPECTED_VERSION"
  fi
  api_body_file="$(mktemp)"
  if ! curl -fsS --max-time "$TIMEOUT" -H "Authorization: Bearer $API_TOKEN" -o "$api_body_file" "$api_url"; then
    echo "FAIL api_key_verify $API_VERIFY_PATH"
    rm -f "$api_body_file"
    exit 1
  fi
  if ! grep -q '"ok":true' "$api_body_file"; then
    echo "FAIL api_key_verify returned not ok"
    cat "$api_body_file"
    rm -f "$api_body_file"
    exit 1
  fi
  echo "OK api_key_verify"
  cat "$api_body_file"
  printf '\n'
  rm -f "$api_body_file"
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
