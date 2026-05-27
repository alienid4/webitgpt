# RHEL 9.6 Field Commands

This document is the copy source for field operators. Any command that Codex
asks the operator to run on a server should be added here first, then copied
from GitHub.

For one-pass issue reporting and masking rules, use:

- `docs/field_issue_intake_and_masking.md`

## Current Install Path

Use this after applying the `v1.0.3.32_rhel96-installer-hotfix-patch` to the
extracted full offline package.

```bash
cd /tmp/webitgpt_full_offline_1.0.3.32-api-key-verify-visibility_rhel-9-6_20260527081023
sudo dnf install -y podman containers-common container-selinux crun conmon fuse-overlayfs slirp4netns
SKIP_RPMS=1 sudo bash INSTALL_ALL.sh
```

## Post Install Checks

```bash
podman ps -a
ss -ltnp | grep -E '27017|8002' || true
curl -sS http://127.0.0.1:8002/health || true
curl -sS http://127.0.0.1:8002/ready || true
```

## One Shot Diagnostic Collection

Run this when installation does not complete cleanly. It writes a single log
file that can be sent back for analysis.

```bash
cat > /tmp/webitgpt_rhel_check.sh <<'EOF'
#!/usr/bin/env bash
set -x
cat /etc/redhat-release
dnf repolist
dnf list podman containers-common container-selinux crun conmon fuse-overlayfs slirp4netns nmap nmon
command -v podman || true
podman --version || true
podman ps -a || true
ss -ltnp | grep -E '27017|8002' || true
systemctl status webitgpt --no-pager || true
systemctl status webitgpt-mongo --no-pager || true
journalctl -u webitgpt -n 80 --no-pager || true
journalctl -u webitgpt-mongo -n 80 --no-pager || true
curl -sS http://127.0.0.1:8002/health || true
curl -sS http://127.0.0.1:8002/ready || true
EOF
bash /tmp/webitgpt_rhel_check.sh > /tmp/webitgpt_rhel_check.log 2>&1
cat /tmp/webitgpt_rhel_check.log
```

## Hotfix Patch Apply Commands

Use this only if the full offline package has already been extracted and the
RHEL 9.6 installer hotfix patch has been downloaded.

```bash
cd /tmp/webitgpt_full_offline_1.0.3.32-api-key-verify-visibility_rhel-9-6_20260527081023
tar -xzf /tmp/v1.0.3.32_rhel96-installer-hotfix-patch_20260527085058.tar.gz -C /tmp
bash /tmp/webitgpt_v1.0.3.32-rhel96-installer-hotfix-patch/install_patch_rhel96_installer.sh "$(pwd)"
```

## Alternative Modes

Use native RHEL or Satellite repositories for prerequisites:

```bash
USE_NATIVE_REPOS=1 sudo bash INSTALL_ALL.sh
```

Skip local RPM installation when prerequisites are already installed:

```bash
SKIP_RPMS=1 sudo bash INSTALL_ALL.sh
```

Skip the entire prerequisite step when OS packages and MongoDB are already
prepared:

```bash
SKIP_PREREQS=1 sudo bash INSTALL_ALL.sh
```

## GitHub Release Links

- Release page: <https://github.com/alienid4/webitgpt/releases/tag/v1.0.3.32>
- Hotfix patch: <https://github.com/alienid4/webitgpt/releases/download/v1.0.3.32/v1.0.3.32_rhel96-installer-hotfix-patch_20260527085058.tar.gz>
- Hotfix SHA256: <https://github.com/alienid4/webitgpt/releases/download/v1.0.3.32/v1.0.3.32_rhel96-installer-hotfix-patch_20260527085058.tar.gz.sha256>
