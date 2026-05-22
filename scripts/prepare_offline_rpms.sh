#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${OUT_DIR:-$ROOT/dist/offline_rpms}"
mkdir -p "$OUT_DIR"

PACKAGES=(
  python3
  python3-pip
  python3-setuptools
  python3-wheel
  rsync
  tar
  gzip
  curl
  nmap
  openssh-clients
  policycoreutils
)

if ! command -v dnf >/dev/null 2>&1; then
  echo "This helper must run on a Rocky/RHEL compatible host with dnf." >&2
  exit 1
fi

echo "Downloading RPMs to $OUT_DIR"
if dnf download --help >/dev/null 2>&1; then
  dnf download --resolve --alldeps --destdir "$OUT_DIR" "${PACKAGES[@]}"
else
  echo "dnf download plugin is unavailable; trying dnf install --downloadonly." >&2
  dnf install -y --downloadonly --downloaddir="$OUT_DIR" "${PACKAGES[@]}"
fi

cat >"$OUT_DIR/manifest.txt" <<EOF
Generated at: $(date -Is)
OS: $(cat /etc/redhat-release 2>/dev/null || uname -a)
Packages:
$(printf ' - %s\n' "${PACKAGES[@]}")
EOF

echo "RPM download completed: $OUT_DIR"
