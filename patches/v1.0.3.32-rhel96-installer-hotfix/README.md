# v1.0.3.32 RHEL 9.6 Installer Hotfix Patch

This patch updates an already extracted `v1.0.3.32` full offline package.

It fixes the RHEL 9.6 prerequisite installer so it:

- skips `rocky-release`, `rocky-repos`, and `rocky-gpg-keys`;
- skips protected/base packages such as `systemd`, kernel, `glibc`, release,
  repos, and GPG key packages;
- skips `el9_7` RPMs when the target is RHEL 9.6;
- supports native RHEL/Satellite repository install with `USE_NATIVE_REPOS=1`;
- supports skipping local RPM install with `SKIP_RPMS=1`;
- supports skipping the entire prerequisites step with `SKIP_PREREQS=1`.

## Apply

From the extracted full offline directory:

```bash
tar -xzf webitgpt_v1.0.3.32-rhel96-installer-hotfix-patch_*.tar.gz -C /tmp
bash /tmp/webitgpt_v1.0.3.32-rhel96-installer-hotfix-patch/install_patch_rhel96_installer.sh "$(pwd)"
```

## Recommended Retry On RHEL 9.6 With Satellite Repos

```bash
USE_NATIVE_REPOS=1 sudo bash INSTALL_ALL.sh
```

## If OS Prerequisites Are Already Installed

```bash
SKIP_RPMS=1 sudo bash INSTALL_ALL.sh
```

## If OS Prerequisites And MongoDB Are Already Prepared

```bash
SKIP_PREREQS=1 sudo bash INSTALL_ALL.sh
```
