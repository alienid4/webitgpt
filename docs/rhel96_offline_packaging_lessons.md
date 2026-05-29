# RHEL 9.6 Offline Packaging Lessons

## Do Not Ship Distro Identity RPMs From The Build Host

When a prerequisite bundle is built on Rocky Linux, `dnf download --resolve`
can pull Rocky identity packages such as:

- `rocky-release`
- `rocky-repos`
- `rocky-gpg-keys`

These packages must never be installed on a RHEL target. They conflict with
`redhat-release` and files such as `/etc/redhat-release`, `/usr/lib/os-release`,
and systemd preset files.

## Do Not Force A Newer Minor Release Onto RHEL 9.6

If the build host is Rocky/RHEL 9.7, the RPM bundle may contain `el9_7`
packages. A RHEL 9.6 target should not be forced to install those packages,
especially for low-level dependencies such as:

- `glibc`
- `podman`
- `containers-common`
- `container-selinux`
- `passt`
- `selinux-policy`

Use the target host's native RHEL 9.6 repositories when available, or build the
RPM bundle on a host that exactly matches the target OS and enabled repositories.

## Installer Guardrails

The RHEL installer must:

- Skip protected packages such as `systemd`, kernel, `glibc`, release packages,
  repos packages, and GPG key packages.
- Default to installing only missing packages.
- Offer `USE_NATIVE_REPOS=1` for RHEL hosts that have Satellite/RHEL repos.
- Offer `SKIP_RPMS=1` when prerequisites have already been installed by the OS
  team.
- Offer `SKIP_PREREQS=1` when the target only needs the webitgpt application
  installation step.

## Recommended RHEL 9.6 Recovery Commands

If the target has RHEL/Satellite repositories:

```bash
USE_NATIVE_REPOS=1 sudo bash INSTALL_ALL.sh
```

If OS prerequisites are already installed:

```bash
SKIP_RPMS=1 sudo bash INSTALL_ALL.sh
```

If MongoDB and OS prerequisites are already prepared:

```bash
SKIP_PREREQS=1 sudo bash INSTALL_ALL.sh
```
