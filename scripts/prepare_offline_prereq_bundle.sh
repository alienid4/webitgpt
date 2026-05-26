#!/usr/bin/env bash
set -euo pipefail

# Build this on a Rocky/RHEL 9 host that CAN access OS repositories and image registries.
# The target host can then install these prerequisites without internet access.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +%Y%m%d%H%M%S)"
OUT_DIR="${OUT_DIR:-$ROOT/dist}"
BUNDLE_NAME="${BUNDLE_NAME:-webitgpt_prereqs_rocky9_${STAMP}}"
STAGE="$OUT_DIR/$BUNDLE_NAME"
RPM_DIR="$STAGE/rpms"
IMAGE_DIR="$STAGE/images"
MONGO_IMAGE="${MONGO_IMAGE:-docker.io/library/mongo:7.0}"
INCLUDE_MONGO_IMAGE="${INCLUDE_MONGO_IMAGE:-1}"
INCLUDE_NMON="${INCLUDE_NMON:-1}"
DNF_REPO_FLAGS="${DNF_REPO_FLAGS:---disablerepo=tailscale-stable --disablerepo=cloudflared-stable}"
PODMAN_BIN="${PODMAN_BIN:-podman}"
BUILD_OS_LABEL="$(cat /etc/redhat-release 2>/dev/null || uname -a)"
TARGET_OS_LABEL="${TARGET_OS_LABEL:-$BUILD_OS_LABEL}"

PACKAGES=(
  python3
  python3-pip
  python3-setuptools
  python3-pip-wheel
  python3-setuptools-wheel
  rsync
  tar
  gzip
  curl
  nmap
  openssh-clients
  policycoreutils
  podman
  crun
  conmon
  containers-common
  fuse-overlayfs
  slirp4netns
)

if [ "$INCLUDE_NMON" = "1" ]; then
  PACKAGES+=(nmon)
fi

if ! command -v dnf >/dev/null 2>&1; then
  echo "This script must run on a Rocky/RHEL compatible host with dnf." >&2
  exit 1
fi

mkdir -p "$RPM_DIR" "$IMAGE_DIR"

if ! dnf download --help >/dev/null 2>&1; then
  dnf -y $DNF_REPO_FLAGS install dnf-plugins-core
fi

echo "Downloading RPM prerequisites to $RPM_DIR"
dnf -y $DNF_REPO_FLAGS download --resolve --alldeps --destdir "$RPM_DIR" "${PACKAGES[@]}"

if [ "$INCLUDE_MONGO_IMAGE" = "1" ]; then
  if ! command -v "$PODMAN_BIN" >/dev/null 2>&1; then
    echo "podman is required on the build host to save MongoDB image." >&2
    echo "RPMs were downloaded, but MongoDB image was not saved." >&2
  else
    safe_image_name="$(echo "$MONGO_IMAGE" | tr '/:' '__')"
    image_tar="$IMAGE_DIR/${safe_image_name}.tar"
    echo "Pulling MongoDB image: $MONGO_IMAGE"
    "$PODMAN_BIN" pull "$MONGO_IMAGE"
    echo "Saving MongoDB image to $image_tar"
    "$PODMAN_BIN" save -o "$image_tar" "$MONGO_IMAGE"
  fi
fi

cp "$ROOT/scripts/install_prereqs_offline.sh" "$STAGE/install_prereqs_offline.sh"
chmod +x "$STAGE/install_prereqs_offline.sh"

cat >"$STAGE/manifest.txt" <<EOF
Bundle: $BUNDLE_NAME
Generated at: $(date -Is)
Build host: $(hostname -f 2>/dev/null || hostname)
Build OS: $BUILD_OS_LABEL
Target OS: $TARGET_OS_LABEL
Mongo image requested: $MONGO_IMAGE
Mongo image included: $INCLUDE_MONGO_IMAGE
NMON package requested: $INCLUDE_NMON

Packages:
$(printf ' - %s\n' "${PACKAGES[@]}")

Install on target:
  tar -xzf ${BUNDLE_NAME}.tar.gz
  cd ${BUNDLE_NAME}
  sudo bash install_prereqs_offline.sh
EOF

tar -czf "$OUT_DIR/${BUNDLE_NAME}.tar.gz" -C "$OUT_DIR" "$BUNDLE_NAME"
echo "$OUT_DIR/${BUNDLE_NAME}.tar.gz"
