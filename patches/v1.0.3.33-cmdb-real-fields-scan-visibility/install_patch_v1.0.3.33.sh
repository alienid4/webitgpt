#!/usr/bin/env bash
set -euo pipefail

PATCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_HOME="${1:-/opt/webitgpt}"
STAMP="$(date +%Y%m%d%H%M%S)"

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root: sudo bash install_patch_v1.0.3.33.sh /opt/webitgpt" >&2
  exit 1
fi

if [ ! -d "$APP_HOME/webapp" ]; then
  echo "APP_HOME does not look like webitgpt: $APP_HOME" >&2
  exit 1
fi

BACKUP_DIR="$APP_HOME/backup/patches/pre_v1.0.3.33_cmdb_real_fields_scan_$STAMP"
mkdir -p "$BACKUP_DIR"

backup_if_exists() {
  local path="$1"
  if [ -e "$APP_HOME/$path" ]; then
    mkdir -p "$BACKUP_DIR/$(dirname "$path")"
    cp -a "$APP_HOME/$path" "$BACKUP_DIR/$path"
  fi
}

for path in \
  CHANGELOG.md \
  docs/release_notes/v1.0.3.33.md \
  tests/test_asset_account_ui.py \
  tests/test_cmdb_real_fields_and_scan_summary.py \
  webapp/config.py \
  webapp/services/cmdb_service.py \
  webapp/services/csv_service.py \
  webapp/services/system_service.py \
  webapp/templates/host_new.html \
  webapp/templates/ipam.html
do
  backup_if_exists "$path"
done

cp -a "$PATCH_DIR/files/." "$APP_HOME/"

if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files webitgpt.service >/dev/null 2>&1; then
  systemctl restart webitgpt
fi

echo "webitgpt v1.0.3.33 patch applied."
echo "Backup: $BACKUP_DIR"
echo "Verify:"
echo "  curl -fsS http://127.0.0.1:8002/health"
echo "  cd $APP_HOME && ./venv/bin/python -m pytest -q tests/test_cmdb_real_fields_and_scan_summary.py tests/test_asset_account_ui.py"
