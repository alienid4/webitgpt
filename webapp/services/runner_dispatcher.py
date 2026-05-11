from __future__ import annotations

from typing import Any

from webapp.runners.ansible_runner import AnsibleRunner
from webapp.runners.as400_runner import As400Runner
from webapp.runners.base_runner import Runner
from webapp.runners.ssh_raw_runner import SshRawRunner
from webapp.runners.vcenter_runner import VcenterRunner
from webapp.runners.winrm_runner import WinrmRunner


def get_runner(host: dict[str, Any]) -> Runner:
    connection = host.get("connection") or ""
    host_type = host.get("host_type") or ""
    if connection in {"ssh", "local"} or host_type == "linux":
        return AnsibleRunner(host)
    if connection == "winrm" or host_type == "windows":
        return WinrmRunner(host)
    if connection == "ssh_raw" or host_type == "aix":
        return SshRawRunner(host)
    if connection == "vcenter_api" or host_type.startswith("vmware"):
        return VcenterRunner(host)
    if connection == "as400_api" or host_type == "as400":
        return As400Runner(host)
    return AnsibleRunner(host)

