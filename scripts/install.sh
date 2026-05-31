#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -d "$SCRIPT_DIR/files" ]; then
  SRC_DIR="$SCRIPT_DIR/files"
else
  SRC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

APP_HOME="${INSPECTION_HOME:-/opt/webitgpt}"
RUN_USER="${WEBITGPT_USER:-sysinfra}"
RUN_GROUP="${WEBITGPT_GROUP:-itagent}"
BACKUP_ROOT="${APP_HOME}/backup/patches"
STAMP="$(date +%Y%m%d_%H%M%S)"
WEBITGPT_BUILD_TIME="${WEBITGPT_BUILD_TIME:-$(date '+%Y-%m-%d %H:%M:%S %:z')}"
BACKUP_DIR="${BACKUP_ROOT}/preinstall_${STAMP}"
SERVICE_NAME="webitgpt.service"
WEBITGPT_PIP_MODE="${WEBITGPT_PIP_MODE:-offline}"

ensure_system_tool() {
  local command_name="$1"
  local package_name="$2"
  if command -v "$command_name" >/dev/null 2>&1; then
    return 0
  fi
  echo "System tool '${command_name}' not found; trying to install package '${package_name}'." >&2
  if [ "$(id -u)" -eq 0 ]; then
    if command -v dnf >/dev/null 2>&1; then
      dnf install -y "$package_name"
    elif command -v apt-get >/dev/null 2>&1; then
      apt-get update && apt-get install -y "$package_name"
    else
      echo "No supported package manager found; please install ${package_name} manually." >&2
    fi
  elif command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
    if command -v dnf >/dev/null 2>&1; then
      sudo dnf install -y "$package_name"
    elif command -v apt-get >/dev/null 2>&1; then
      sudo apt-get update && sudo apt-get install -y "$package_name"
    else
      echo "No supported package manager found; please install ${package_name} manually." >&2
    fi
  else
    echo "No sudo permission; please install ${package_name} manually for IPAM scan." >&2
  fi
}

rollback() {
  echo "Install failed; attempting rollback from ${BACKUP_DIR}" >&2
  if [ -d "$BACKUP_DIR/files" ]; then
    find "$APP_HOME" -mindepth 1 -maxdepth 1 \
      ! -name 'venv' ! -name 'data' ! -name 'logs' ! -name 'tmp' ! -name 'backup' \
      -exec rm -rf {} + || true
    cp -a "$BACKUP_DIR/files"/. "$APP_HOME"/ || true
    if command -v systemctl >/dev/null 2>&1; then
      systemctl restart "$SERVICE_NAME" >/dev/null 2>&1 || true
    fi
  fi
}
trap rollback ERR

mkdir -p "$APP_HOME" "$BACKUP_ROOT"
if [ -d "$APP_HOME/webapp" ]; then
  mkdir -p "$BACKUP_DIR/files"
  (
    cd "$APP_HOME"
    tar \
      --exclude './venv' \
      --exclude './data' \
      --exclude './logs' \
      --exclude './tmp' \
      --exclude './backup' \
      -cf - .
  ) | (
    cd "$BACKUP_DIR/files"
    tar -xf -
  )
fi

mkdir -p "$APP_HOME/data" "$APP_HOME/logs" "$APP_HOME/tmp" "$APP_HOME/backup"
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete \
    --exclude 'venv/' \
    --exclude 'data/' \
    --exclude 'logs/' \
    --exclude 'tmp/' \
    --exclude 'backup/' \
    --exclude '__pycache__/' \
    "$SRC_DIR/" "$APP_HOME/"
else
  find "$APP_HOME" -mindepth 1 -maxdepth 1 \
    ! -name 'venv' ! -name 'data' ! -name 'logs' ! -name 'tmp' ! -name 'backup' \
    -exec rm -rf {} +
  (
    cd "$SRC_DIR"
    tar \
      --exclude './venv' \
      --exclude './data' \
      --exclude './logs' \
      --exclude './tmp' \
      --exclude './backup' \
      --exclude './dist' \
      --exclude './__pycache__' \
      --exclude '*/__pycache__' \
      -cf - .
  ) | (
    cd "$APP_HOME"
    tar -xf -
  )
fi

cd "$APP_HOME"
ensure_system_tool nmap nmap
if [ ! -x "$APP_HOME/venv/bin/python" ]; then
  python3 -m venv "$APP_HOME/venv"
fi

install_python_requirements() {
  local pip_args=()
  if [ "$WEBITGPT_PIP_MODE" = "skip" ]; then
    echo "Skipping Python dependency install because WEBITGPT_PIP_MODE=skip."
    return 0
  fi
  if [ "$WEBITGPT_PIP_MODE" = "offline" ]; then
    if [ -d "$SRC_DIR/wheelhouse" ]; then
      pip_args=(--no-index --find-links "$SRC_DIR/wheelhouse")
      echo "Installing Python dependencies from local wheelhouse."
    else
      pip_args=(--no-index)
      echo "Installing Python dependencies in offline mode; existing venv must satisfy requirements."
    fi
  elif [ "$WEBITGPT_PIP_MODE" = "online" ]; then
    "$APP_HOME/venv/bin/python" -m pip install --upgrade pip
  else
    echo "Unsupported WEBITGPT_PIP_MODE=${WEBITGPT_PIP_MODE}; use offline, online, or skip." >&2
    return 1
  fi
  "$APP_HOME/venv/bin/pip" install "${pip_args[@]}" -r "$APP_HOME/requirements.txt"
}

install_python_requirements
INSPECTION_HOME="$APP_HOME" MONGO_URI="${MONGO_URI:-mongodb://localhost:27017}" MONGO_DB="${MONGO_DB:-webitgpt}" WEBITGPT_SUPERADMIN_PASSWORD="${WEBITGPT_SUPERADMIN_PASSWORD:-}" WEBITGPT_BUILD_TIME="$WEBITGPT_BUILD_TIME" "$APP_HOME/venv/bin/python" "$APP_HOME/scripts/bootstrap.py"
"$APP_HOME/venv/bin/python" "$APP_HOME/scripts/run_housekeeping.py" --mode post-install >>"$APP_HOME/logs/housekeeping_install.log" 2>&1 || true

if [ "$(id -u)" -eq 0 ]; then
  chown -R "${RUN_USER}:${RUN_GROUP}" "$APP_HOME" || true
  chmod -R 750 "$APP_HOME" || true
  INSPECTION_HOME="$APP_HOME" WEBITGPT_USER="$RUN_USER" WEBITGPT_GROUP="$RUN_GROUP" MONGO_URI="${MONGO_URI:-mongodb://localhost:27017}" MONGO_DB="${MONGO_DB:-webitgpt}" WEBITGPT_BUILD_TIME="$WEBITGPT_BUILD_TIME" "$APP_HOME/scripts/install_systemd.sh"
elif command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
  sudo chown -R "${RUN_USER}:${RUN_GROUP}" "$APP_HOME" || true
  sudo chmod -R 750 "$APP_HOME" || true
  sudo INSPECTION_HOME="$APP_HOME" WEBITGPT_USER="$RUN_USER" WEBITGPT_GROUP="$RUN_GROUP" MONGO_URI="${MONGO_URI:-mongodb://localhost:27017}" MONGO_DB="${MONGO_DB:-webitgpt}" WEBITGPT_BUILD_TIME="$WEBITGPT_BUILD_TIME" "$APP_HOME/scripts/install_systemd.sh"
else
  echo "Not root: skipped systemd install/restart. Run scripts/install_systemd.sh with sudo." >&2
fi

for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:8002/health" >/dev/null 2>&1; then
    trap - ERR
    echo "{\"event\":\"install.ok\",\"app\":\"webitgpt\",\"home\":\"${APP_HOME}\",\"ts\":\"$(date -Is)\"}" >>"$APP_HOME/logs/install_audit.log"
    echo "Installed webitgpt to ${APP_HOME}"
    exit 0
  fi
  sleep 1
done

echo "Health check failed after install" >&2
exit 1
