#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -d "$SCRIPT_DIR/files" ]; then
  BUNDLE_DIR="$SCRIPT_DIR"
  SRC_DIR="$SCRIPT_DIR/files"
else
  BUNDLE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
  SRC_DIR="$BUNDLE_DIR"
fi

APP_HOME="${INSPECTION_HOME:-/opt/webitgpt}"
RUN_USER="${WEBITGPT_USER:-sysinfra}"
RUN_GROUP="${WEBITGPT_GROUP:-itagent}"
MONGO_URI_VALUE="${MONGO_URI:-mongodb://localhost:27017}"
MONGO_DB_VALUE="${MONGO_DB:-webitgpt}"
HOSTS_CSV="${WEBITGPT_INITIAL_HOSTS_CSV:-}"
SEED_DEMO="${WEBITGPT_SEED_DEMO_HOSTS:-0}"
CLEANUP_TEST="${WEBITGPT_CLEANUP_TEST_DATA:-0}"
BUILD_TIME="${WEBITGPT_BUILD_TIME:-$(date '+%Y-%m-%d %H:%M:%S %:z')}"
SERVICE_NAME="webitgpt.service"

usage() {
  cat <<'USAGE'
Usage:
  sudo bash install_offline.sh [options]

Options:
  --home PATH             Install path. Default: /opt/webitgpt
  --mongo-uri URI         Existing MongoDB URI. Default: mongodb://localhost:27017
  --mongo-db NAME         Database name. Default: webitgpt
  --hosts-csv PATH        Initial CMDB host CSV to import. Optional.
  --seed-demo             Seed home/lab demo hosts. Default: off for offline install.
  --cleanup-test-data     Remove known validation/test rows. Default: off.
  --user NAME             Runtime user. Default: sysinfra
  --group NAME            Runtime group. Default: itagent
  -h, --help              Show this help.

Examples:
  sudo bash install_offline.sh --mongo-uri mongodb://localhost:27017 --mongo-db webitgpt
  sudo bash install_offline.sh --hosts-csv /tmp/company_hosts.csv
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --home) APP_HOME="$2"; shift 2 ;;
    --mongo-uri) MONGO_URI_VALUE="$2"; shift 2 ;;
    --mongo-db) MONGO_DB_VALUE="$2"; shift 2 ;;
    --hosts-csv) HOSTS_CSV="$2"; shift 2 ;;
    --seed-demo) SEED_DEMO="1"; shift ;;
    --cleanup-test-data) CLEANUP_TEST="1"; shift ;;
    --user) RUN_USER="$2"; shift 2 ;;
    --group) RUN_GROUP="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

if [ "$(id -u)" -ne 0 ]; then
  echo "install_offline.sh must run as root. Use sudo." >&2
  exit 1
fi

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

try_local_rpms() {
  if [ -d "$BUNDLE_DIR/rpms" ] && find "$BUNDLE_DIR/rpms" -name '*.rpm' -print -quit | grep -q .; then
    if command -v dnf >/dev/null 2>&1; then
      dnf install -y "$BUNDLE_DIR"/rpms/*.rpm || true
    elif command -v yum >/dev/null 2>&1; then
      yum localinstall -y "$BUNDLE_DIR"/rpms/*.rpm || true
    fi
  fi
}

try_local_rpms
need_cmd python3
need_cmd tar
need_cmd curl

if ! id "$RUN_USER" >/dev/null 2>&1; then
  useradd --system --create-home --shell /bin/bash "$RUN_USER"
fi
if ! getent group "$RUN_GROUP" >/dev/null 2>&1; then
  groupadd --system "$RUN_GROUP"
fi
usermod -a -G "$RUN_GROUP" "$RUN_USER" >/dev/null 2>&1 || true

mkdir -p "$APP_HOME" "$APP_HOME/data" "$APP_HOME/logs" "$APP_HOME/tmp" "$APP_HOME/backup"

BACKUP_DIR="$APP_HOME/backup/offline_preinstall_$(date +%Y%m%d_%H%M%S)"
if [ -d "$APP_HOME/webapp" ]; then
  mkdir -p "$BACKUP_DIR/files"
  tar \
    --exclude './venv' \
    --exclude './data' \
    --exclude './logs' \
    --exclude './tmp' \
    --exclude './backup' \
    -C "$APP_HOME" -cf - . | tar -C "$BACKUP_DIR/files" -xf -
fi

if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete \
    --exclude 'venv/' \
    --exclude 'data/' \
    --exclude 'logs/' \
    --exclude 'tmp/' \
    --exclude 'backup/' \
    --exclude 'dist/' \
    --exclude '__pycache__/' \
    "$SRC_DIR/" "$APP_HOME/"
else
  find "$APP_HOME" -mindepth 1 -maxdepth 1 \
    ! -name 'venv' ! -name 'data' ! -name 'logs' ! -name 'tmp' ! -name 'backup' \
    -exec rm -rf {} +
  tar \
    --exclude './venv' \
    --exclude './data' \
    --exclude './logs' \
    --exclude './tmp' \
    --exclude './backup' \
    --exclude './dist' \
    --exclude './__pycache__' \
    --exclude '*/__pycache__' \
    -C "$SRC_DIR" -cf - . | tar -C "$APP_HOME" -xf -
fi

cd "$APP_HOME"
if [ ! -x "$APP_HOME/venv/bin/python" ]; then
  python3 -m venv "$APP_HOME/venv"
fi

WHEELHOUSE="$BUNDLE_DIR/wheelhouse"
if [ ! -d "$WHEELHOUSE" ]; then
  echo "Missing wheelhouse: $WHEELHOUSE" >&2
  echo "Build the offline bundle first, then install again." >&2
  exit 1
fi

"$APP_HOME/venv/bin/python" -m pip install --no-index --find-links "$WHEELHOUSE" --upgrade pip
"$APP_HOME/venv/bin/pip" install --no-index --find-links "$WHEELHOUSE" -r "$APP_HOME/requirements.txt"

export INSPECTION_HOME="$APP_HOME"
export MONGO_URI="$MONGO_URI_VALUE"
export MONGO_DB="$MONGO_DB_VALUE"
export WEBITGPT_BUILD_TIME="$BUILD_TIME"
export WEBITGPT_SEED_DEMO_HOSTS="$SEED_DEMO"
export WEBITGPT_CLEANUP_TEST_DATA="$CLEANUP_TEST"
if [ -n "$HOSTS_CSV" ]; then
  export WEBITGPT_INITIAL_HOSTS_CSV="$HOSTS_CSV"
fi

"$APP_HOME/venv/bin/python" "$APP_HOME/scripts/bootstrap.py"
"$APP_HOME/venv/bin/python" "$APP_HOME/scripts/run_housekeeping.py" --mode post-install >>"$APP_HOME/logs/housekeeping_install.log" 2>&1 || true

chown -R "${RUN_USER}:${RUN_GROUP}" "$APP_HOME" || true
chmod -R 750 "$APP_HOME" || true

INSPECTION_HOME="$APP_HOME" WEBITGPT_USER="$RUN_USER" WEBITGPT_GROUP="$RUN_GROUP" MONGO_URI="$MONGO_URI_VALUE" MONGO_DB="$MONGO_DB_VALUE" WEBITGPT_BUILD_TIME="$BUILD_TIME" "$APP_HOME/scripts/install_systemd.sh"

for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:8002/health" >/dev/null 2>&1; then
    echo "{\"event\":\"offline_install.ok\",\"home\":\"${APP_HOME}\",\"db\":\"${MONGO_DB_VALUE}\",\"seed_demo\":\"${SEED_DEMO}\",\"ts\":\"$(date -Is)\"}" >>"$APP_HOME/logs/install_audit.log"
    echo "Offline install completed: $APP_HOME"
    exit 0
  fi
  sleep 1
done

echo "Health check failed after offline install." >&2
systemctl --no-pager --full status "$SERVICE_NAME" || true
exit 1
