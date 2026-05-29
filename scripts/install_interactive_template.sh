#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEBITGPT_INSTALL_MODE="${WEBITGPT_INSTALL_MODE:-auto}"

case "$WEBITGPT_INSTALL_MODE" in
  auto)
    WEBITGPT_NONINTERACTIVE="${WEBITGPT_NONINTERACTIVE:-1}"
    WEBITGPT_SUPERADMIN_PASSWORD="${WEBITGPT_SUPERADMIN_PASSWORD:-1qaz@WSX}"
    ;;
  user)
    WEBITGPT_NONINTERACTIVE="${WEBITGPT_NONINTERACTIVE:-0}"
    ;;
  *)
    echo "Invalid WEBITGPT_INSTALL_MODE: $WEBITGPT_INSTALL_MODE. Use auto or user." >&2
    exit 2
    ;;
esac

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root: sudo bash INSTALL.sh"
  exit 1
fi

if [ ! -f "$SCRIPT_DIR/install_offline.sh" ]; then
  echo "Missing install_offline.sh. Please unpack the complete webitgpt offline bundle."
  exit 1
fi

ask_default() {
  local prompt="$1"
  local default="$2"
  local value
  read -r -p "$prompt [$default]: " value
  if [ -z "$value" ]; then
    value="$default"
  fi
  printf '%s' "$value"
}

ask_yes_no() {
  local prompt="$1"
  local default="$2"
  local value
  read -r -p "$prompt [$default]: " value
  value="${value:-$default}"
  case "$value" in
    y|Y|yes|YES|Yes) return 0 ;;
    *) return 1 ;;
  esac
}

ask_password() {
  local first second
  if [ -n "${WEBITGPT_SUPERADMIN_PASSWORD:-}" ]; then
    printf '%s' "$WEBITGPT_SUPERADMIN_PASSWORD"
    return 0
  fi
  if [ ! -t 0 ]; then
    echo "Non-interactive install requires WEBITGPT_SUPERADMIN_PASSWORD." >&2
    exit 2
  fi
  while true; do
    read -r -s -p "Enter initial superadmin password: " first
    echo
    read -r -s -p "Confirm initial superadmin password: " second
    echo
    if [ -z "$first" ]; then
      echo "Password cannot be empty."
      continue
    fi
    if [ "$first" != "$second" ]; then
      echo "Passwords do not match. Try again."
      continue
    fi
    printf '%s' "$first"
    return 0
  done
}

echo "============================================================"
echo " webitgpt offline one-key installer"
echo "============================================================"
echo "This installer is for a clean target host. It does not import lab/test data."
echo "Install mode: $WEBITGPT_INSTALL_MODE"
echo

if [ "${WEBITGPT_NONINTERACTIVE:-0}" = "1" ]; then
  APP_HOME="${INSPECTION_HOME:-/opt/webitgpt}"
  RUN_USER="${WEBITGPT_USER:-sysinfra}"
  RUN_GROUP="${WEBITGPT_GROUP:-itagent}"
  MONGO_URI_VALUE="${MONGO_URI:-mongodb://localhost:27017}"
  MONGO_DB_VALUE="${MONGO_DB:-webitgpt}"
  HOSTS_CSV="${WEBITGPT_INITIAL_HOSTS_CSV:-}"
  if [ -n "$HOSTS_CSV" ] && [ ! -f "$HOSTS_CSV" ]; then
    echo "CSV file not found: $HOSTS_CSV" >&2
    exit 1
  fi
else
  APP_HOME="$(ask_default 'Install path' '/opt/webitgpt')"
  RUN_USER="$(ask_default 'Runtime Linux user' 'sysinfra')"
  RUN_GROUP="$(ask_default 'Runtime Linux group' 'itagent')"
  MONGO_URI_VALUE="$(ask_default 'MongoDB URI' 'mongodb://localhost:27017')"
  MONGO_DB_VALUE="$(ask_default 'MongoDB database' 'webitgpt')"

  HOSTS_CSV=""
  if ask_yes_no "Import initial CMDB host CSV now" "n"; then
    HOSTS_CSV="$(ask_default 'CSV path on this host' '/tmp/company_hosts.csv')"
    if [ ! -f "$HOSTS_CSV" ]; then
      echo "CSV file not found: $HOSTS_CSV"
      exit 1
    fi
  fi
fi

SUPERADMIN_PASSWORD="$(ask_password)"

echo
echo "Install summary:"
echo "  APP_HOME: $APP_HOME"
echo "  Runtime:  $RUN_USER:$RUN_GROUP"
echo "  Mongo:    $MONGO_URI_VALUE / $MONGO_DB_VALUE"
if [ -n "$HOSTS_CSV" ]; then
  echo "  CSV:      $HOSTS_CSV"
else
  echo "  CSV:      none. Import CMDB later from the UI or API."
fi
echo "  Demo:     disabled"
echo "  Cleanup:  disabled"
echo

if [ "${WEBITGPT_NONINTERACTIVE:-0}" != "1" ] && ! ask_yes_no "Start install" "y"; then
  echo "Install cancelled."
  exit 0
fi

export INSPECTION_HOME="$APP_HOME"
export WEBITGPT_USER="$RUN_USER"
export WEBITGPT_GROUP="$RUN_GROUP"
export MONGO_URI="$MONGO_URI_VALUE"
export MONGO_DB="$MONGO_DB_VALUE"
export WEBITGPT_SUPERADMIN_PASSWORD="$SUPERADMIN_PASSWORD"
export WEBITGPT_SEED_DEMO_HOSTS=0
export WEBITGPT_CLEANUP_TEST_DATA=0
if [ -n "$HOSTS_CSV" ]; then
  export WEBITGPT_INITIAL_HOSTS_CSV="$HOSTS_CSV"
fi

INSTALL_ARGS=(
  --home "$APP_HOME"
  --mongo-uri "$MONGO_URI_VALUE"
  --mongo-db "$MONGO_DB_VALUE"
  --user "$RUN_USER"
  --group "$RUN_GROUP"
)
if [ -n "$HOSTS_CSV" ]; then
  INSTALL_ARGS+=(--hosts-csv "$HOSTS_CSV")
fi

bash "$SCRIPT_DIR/install_offline.sh" "${INSTALL_ARGS[@]}"

echo
echo "Install completed."
echo "Verify with:"
echo "  curl http://localhost:8002/health"
echo "  systemctl status webitgpt --no-pager"
echo "  http://<target-host-ip>:8002"
