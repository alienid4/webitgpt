#!/usr/bin/env bash
set -euo pipefail

# Build a single offline package on 192.168.1.221 (or another online
# Rocky/RHEL 9 host). The target host only needs:
#
#   tar -xzf webitgpt_full_offline_*.tar.gz
#   cd webitgpt_full_offline_*
#   sudo bash INSTALL_ALL.sh
#
# The package includes:
# - OS RPM prerequisites
# - MongoDB container image
# - webitgpt source code without runtime/test data
# - Python wheels
# - one-key installer

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${OUT_DIR:-$ROOT/dist}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
STAMP="$(date +%Y%m%d%H%M%S)"
VERSION_TEXT="$("$PYTHON_BIN" - <<'PY'
from webapp import config
print(f"{config.VERSION}-{config.PATCH_ID}")
PY
)"

FULL_NAME="${FULL_NAME:-webitgpt_full_offline_${VERSION_TEXT}_${STAMP}}"
STAGE="$OUT_DIR/$FULL_NAME"
PACKAGE_DIR="$STAGE/packages"

mkdir -p "$OUT_DIR"
rm -rf "$STAGE"
mkdir -p "$PACKAGE_DIR"

if ! command -v dnf >/dev/null 2>&1; then
  echo "This full offline builder must run on a Rocky/RHEL 9 compatible host with dnf." >&2
  exit 1
fi

echo "Building prerequisite bundle on this host..."
PREREQ_ARCHIVE="$(
  OUT_DIR="$OUT_DIR" \
  MONGO_IMAGE="${MONGO_IMAGE:-docker.io/library/mongo:7.0}" \
  INCLUDE_MONGO_IMAGE="${INCLUDE_MONGO_IMAGE:-1}" \
  INCLUDE_NMON="${INCLUDE_NMON:-1}" \
  bash "$ROOT/scripts/prepare_offline_prereq_bundle.sh" | tail -n 1
)"

echo "Building app bundle on this host..."
APP_ARCHIVE="$(
  OUT_DIR="$OUT_DIR" \
  PYTHON_BIN="$PYTHON_BIN" \
  bash "$ROOT/scripts/prepare_offline_app_bundle.sh" | tail -n 1
)"

mv "$PREREQ_ARCHIVE" "$PACKAGE_DIR/"
mv "$APP_ARCHIVE" "$PACKAGE_DIR/"

# The sub-builders leave their staging directories next to the archives.
# Remove them before creating the final tarball so small lab disks do not fill
# up while building the combined offline package.
PREREQ_STAGE="${PREREQ_ARCHIVE%.tar.gz}"
APP_STAGE="${APP_ARCHIVE%.tar.gz}"
rm -rf "$PREREQ_STAGE" "$APP_STAGE"

cat >"$STAGE/INSTALL_ALL.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="${TMPDIR:-/tmp}/webitgpt_full_offline_install_$(date +%Y%m%d%H%M%S)"

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root: sudo bash INSTALL_ALL.sh" >&2
  exit 1
fi

mkdir -p "$WORK_DIR"
trap 'rm -rf "$WORK_DIR"' EXIT

echo "============================================================"
echo " webitgpt full offline installer"
echo "============================================================"
echo "Step 1/2: install OS prerequisites, nmap/nmon/podman, and MongoDB container."

prereq_archive="$(find "$SCRIPT_DIR/packages" -maxdepth 1 -type f -name 'webitgpt_prereqs_rocky9_*.tar.gz' | head -n 1 || true)"
if [ -z "$prereq_archive" ]; then
  echo "Missing prerequisite archive in packages/." >&2
  exit 1
fi
tar -xzf "$prereq_archive" -C "$WORK_DIR"
prereq_dir="$(find "$WORK_DIR" -maxdepth 1 -type d -name 'webitgpt_prereqs_rocky9_*' | head -n 1)"
bash "$prereq_dir/install_prereqs_offline.sh"

echo
echo "Step 2/2: install webitgpt app."
app_archive="$(find "$SCRIPT_DIR/packages" -maxdepth 1 -type f -name 'webitgpt_offline_*.tar.gz' | head -n 1 || true)"
if [ -z "$app_archive" ]; then
  echo "Missing webitgpt app archive in packages/." >&2
  exit 1
fi
tar -xzf "$app_archive" -C "$WORK_DIR"
app_dir="$(find "$WORK_DIR" -maxdepth 1 -type d -name 'webitgpt_offline_*' | head -n 1)"
bash "$app_dir/INSTALL.sh"

echo
echo "Full offline install completed."
echo "Verify:"
echo "  curl http://localhost:8002/health"
echo "  curl http://localhost:8002/ready"
echo "  systemctl status webitgpt --no-pager"
EOF
chmod +x "$STAGE/INSTALL_ALL.sh"

cat >"$STAGE/README_INSTALL.txt" <<EOF
webitgpt full offline package
Generated at: $(date -Is)
Build host: $(hostname -f 2>/dev/null || hostname)
Version: $VERSION_TEXT

Use on target host:

  tar -xzf ${FULL_NAME}.tar.gz
  cd ${FULL_NAME}
  sudo bash INSTALL_ALL.sh

Target host does not need internet access.

This package must not include:
 - data/
 - logs/
 - backup/
 - venv/
 - .git/
 - Mongo dump
 - home/lab test data
 - secrets, tokens, or private keys

Included package files:
 - $(basename "$PREREQ_ARCHIVE")
 - $(basename "$APP_ARCHIVE")
EOF

ARCHIVE="$OUT_DIR/${FULL_NAME}.tar.gz"
tar -czf "$ARCHIVE" -C "$OUT_DIR" "$FULL_NAME"

echo "Full offline package created:"
echo "$ARCHIVE"
