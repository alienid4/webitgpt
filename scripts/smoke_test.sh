#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8002}"
curl -fsS "$BASE_URL/health"
curl -fsS "$BASE_URL/ready"
curl -fsS "$BASE_URL/metrics"

