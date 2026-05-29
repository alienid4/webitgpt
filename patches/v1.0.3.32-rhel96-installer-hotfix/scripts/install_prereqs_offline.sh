#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RPM_DIR="${RPM_DIR:-$SCRIPT_DIR/rpms}"
IMAGE_DIR="${IMAGE_DIR:-$SCRIPT_DIR/images}"
MONGO_CONTAINER="${MONGO_CONTAINER:-webitgpt-mongo}"
MONGO_PORT="${MONGO_PORT:-27017}"
MONGO_VOLUME="${MONGO_VOLUME:-webitgpt_mongo_data}"
SKIP_RPMS="${SKIP_RPMS:-0}"
SKIP_MONGO="${SKIP_MONGO:-0}"
USE_NATIVE_REPOS="${USE_NATIVE_REPOS:-0}"
RPM_INSTALL_MODE="${RPM_INSTALL_MODE:-missing}"
DNF_LOCAL_FLAGS="${DNF_LOCAL_FLAGS:---disablerepo=* --setopt=install_weak_deps=False --skip-broken}"
PROTECTED_RPM_RE="${PROTECTED_RPM_RE:-^(systemd|systemd-libs|systemd-pam|systemd-rpm-macros|kernel|kernel-core|kernel-modules|glibc|glibc-common|glibc-minimal-langpack|filesystem|setup|basesystem|.*-release|.*-repos|.*-gpg-keys)$}"
NATIVE_PACKAGE_LIST="${NATIVE_PACKAGE_LIST:-python3 python3-pip python3-setuptools python3-pip-wheel python3-setuptools-wheel rsync tar gzip curl nmap openssh-clients policycoreutils podman crun conmon containers-common fuse-overlayfs slirp4netns nmon}"

if [ "$(id -u)" -ne 0 ]; then
  echo "install_prereqs_offline.sh must run as root. Use sudo." >&2
  exit 1
fi

install_rpms() {
  if [ "$SKIP_RPMS" = "1" ]; then
    echo "SKIP_RPMS=1; skipping local RPM prerequisite install."
    return
  fi

  if [ "$USE_NATIVE_REPOS" = "1" ]; then
    echo "USE_NATIVE_REPOS=1; installing prerequisites from target host repositories."
    if command -v dnf >/dev/null 2>&1; then
      dnf install -y $NATIVE_PACKAGE_LIST
    elif command -v yum >/dev/null 2>&1; then
      yum install -y $NATIVE_PACKAGE_LIST
    else
      echo "No dnf/yum found for native repo install." >&2
      return 1
    fi
    return
  fi

  if [ ! -d "$RPM_DIR" ] || ! find "$RPM_DIR" -name '*.rpm' -print -quit | grep -q .; then
    echo "No RPM files found in $RPM_DIR; skipping OS package install."
    return
  fi

  echo "Installing local RPM prerequisites from $RPM_DIR"
  mapfile -t rpm_files < <(find "$RPM_DIR" -maxdepth 1 -type f -name '*.rpm' | sort)
  install_files=()

  for rpm_file in "${rpm_files[@]}"; do
    pkg_name="$(rpm -qp --qf '%{NAME}' "$rpm_file" 2>/dev/null || true)"
    if [ -z "$pkg_name" ]; then
      echo "WARN cannot read RPM name: $rpm_file"
      continue
    fi
    pkg_release="$(rpm -qp --qf '%{RELEASE}' "$rpm_file" 2>/dev/null || true)"
    if [[ "$pkg_name" =~ $PROTECTED_RPM_RE ]]; then
      echo "SKIP protected package from offline bundle: $pkg_name"
      continue
    fi
    if grep -qi 'Red Hat Enterprise Linux.* 9\.6' /etc/redhat-release 2>/dev/null && [[ "$pkg_release" == *el9_7* ]]; then
      echo "SKIP RHEL 9.6 incompatible RPM from offline bundle: $pkg_name-$pkg_release"
      continue
    fi
    if [ "$RPM_INSTALL_MODE" = "missing" ] && rpm -q "$pkg_name" >/dev/null 2>&1; then
      echo "SKIP already installed package: $pkg_name"
      continue
    fi
    install_files+=("$rpm_file")
  done

  if [ "${#install_files[@]}" -eq 0 ]; then
    echo "No missing RPM prerequisites to install."
    return
  fi

  echo "Installing ${#install_files[@]} missing RPM prerequisites."
  if command -v dnf >/dev/null 2>&1; then
    dnf install -y $DNF_LOCAL_FLAGS "${install_files[@]}"
  elif command -v yum >/dev/null 2>&1; then
    yum localinstall -y "${install_files[@]}"
  else
    rpm -Uvh --replacepkgs "${install_files[@]}"
  fi
}

load_mongo_image() {
  if [ "$SKIP_MONGO" = "1" ]; then
    echo "SKIP_MONGO=1; skipping MongoDB image load."
    return 0
  fi

  if ! command -v podman >/dev/null 2>&1; then
    echo "podman is not installed; cannot load MongoDB container image." >&2
    return 1
  fi

  image_tar="$(find "$IMAGE_DIR" -maxdepth 1 -type f -name '*mongo*.tar' | head -n 1 || true)"
  if [ -z "$image_tar" ]; then
    echo "No MongoDB image tar found in $IMAGE_DIR; assuming MongoDB is already provided."
    return 0
  fi

  echo "Loading MongoDB image: $image_tar"
  podman load -i "$image_tar"
}

ensure_mongo_container() {
  if [ "$SKIP_MONGO" = "1" ]; then
    echo "SKIP_MONGO=1; skipping MongoDB container setup."
    return 0
  fi

  if ! command -v podman >/dev/null 2>&1; then
    echo "podman is unavailable; skip MongoDB container setup."
    return 0
  fi

  if podman ps --format '{{.Names}}' | grep -qx "$MONGO_CONTAINER"; then
    echo "MongoDB container already running: $MONGO_CONTAINER"
    ensure_mongo_systemd_unit
    return 0
  fi

  if podman ps -a --format '{{.Names}}' | grep -qx "$MONGO_CONTAINER"; then
    echo "Starting existing MongoDB container: $MONGO_CONTAINER"
    podman start "$MONGO_CONTAINER"
  else
    image="$(podman images --format '{{.Repository}}:{{.Tag}}' | grep -E '(^|/)mongo:' | head -n 1 || true)"
    if [ -z "$image" ]; then
      echo "No MongoDB image is loaded; cannot create MongoDB container." >&2
      return 1
    fi
    echo "Creating MongoDB container $MONGO_CONTAINER from $image"
    podman volume exists "$MONGO_VOLUME" >/dev/null 2>&1 || podman volume create "$MONGO_VOLUME" >/dev/null
    podman run -d \
      --name "$MONGO_CONTAINER" \
      -p "127.0.0.1:${MONGO_PORT}:27017" \
      -v "${MONGO_VOLUME}:/data/db:Z" \
      "$image" --bind_ip_all
  fi

  ensure_mongo_systemd_unit
}

ensure_mongo_systemd_unit() {
  if command -v systemctl >/dev/null 2>&1; then
    unit="/etc/systemd/system/${MONGO_CONTAINER}.service"
    podman generate systemd --new --name "$MONGO_CONTAINER" >"$unit" 2>/dev/null || true
    systemctl daemon-reload || true
    systemctl enable --now "${MONGO_CONTAINER}.service" || true
  fi
}

wait_mongo() {
  echo "Checking MongoDB port 127.0.0.1:${MONGO_PORT}"
  for _ in $(seq 1 30); do
    if command -v python3 >/dev/null 2>&1 && python3 - <<PY >/dev/null 2>&1
import socket
s = socket.create_connection(("127.0.0.1", int("${MONGO_PORT}")), timeout=1)
s.close()
PY
    then
      echo "MongoDB TCP port is reachable."
      return 0
    fi
    sleep 1
  done
  echo "MongoDB TCP port is not reachable after 30 seconds." >&2
  return 1
}

install_rpms
load_mongo_image || true
ensure_mongo_container || true
wait_mongo || true

echo "Prerequisite offline install completed."
echo "Next step: run the webitgpt app offline bundle INSTALL.sh."
