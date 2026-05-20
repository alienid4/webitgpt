from __future__ import annotations

import ipaddress
import re
from typing import Any, Optional


REQUIRED_FIELDS = {
    "division",
    "department",
    "hostname",
    "status",
    "group_name",
    "asset_name",
    "device_type",
    "quantity",
    "owner",
    "environment",
    "custodian",
    "company",
    "host_type",
    "dc",
    "integrity",
    "confidentiality",
    "availability",
}

ASSET_FIELDS = [
    "division",
    "department",
    "asset_seq",
    "status",
    "group_name",
    "apid",
    "asset_name",
    "device_type",
    "device_model",
    "asset_usage",
    "location",
    "rack_no",
    "quantity",
    "owner",
    "environment",
    "hostname",
    "os",
    "bigip",
    "hardware_seq",
    "ip",
    "custodian",
    "sys_admin",
    "user",
    "user_unit",
    "note",
    "company",
    "integrity",
    "confidentiality",
    "availability",
]

INSPECTION_FIELDS = [
    "connection",
    "ssh_user",
    "ssh_port",
    "ssh_key",
    "ssh_key_records",
    "nmon_enabled",
    "nmon_interval_min",
    "nmon_deployed_at",
    "nmon_removed_at",
    "tier",
    "ap_owner",
    "system_name",
    "os_group",
]

SYSTEM_FIELDS = [
    "host_type",
    "dc",
    "edge_id",
    "last_self_check_at",
    "last_self_check_status",
    "last_inspection_at",
    "compliance_score",
    "created_at",
    "updated_at",
    "created_by",
    "updated_by",
    "imported_at",
    "import_source",
    "extensions",
]

ENUMS = {
    "status": {"draft", "pending_ip", "pending_data", "pending_deploy", "active", "disabled", "retired", "pending_retire"},
    "group_name": {f"H{i}" for i in range(1, 10)},
    "environment": {"OA", "PROD", "UAT", "BACKUP", "TEST", "DEV"},
    "host_type": {
        "linux",
        "windows",
        "aix",
        "as400",
        "vmware_host",
        "vmware_vm",
        "vmware_vcenter",
        "network_device",
        "end_device",
    },
    "dc": {"dunan", "neihu", "banciao"},
    "connection": {"ssh", "ssh_raw", "winrm", "vcenter_api", "as400_api", "local", ""},
    "last_self_check_status": {"ok", "warn", "fail", "unknown", ""},
    "tier": {"critical", "high", "medium", "low", ""},
    "os_group": {"rocky", "debian", "win", "aix", "as400", "other", ""},
}

ALIASES = {
    "status": {
        "enabled": "active",
        "in_use": "active",
        "online": "active",
        "deleted": "retired",
        "delete": "retired",
    },
    "environment": {
        "prod": "PROD",
        "production": "PROD",
        "backup": "BACKUP",
        "test": "TEST",
    },
    "dc": {
        "banqiao": "banciao",
        "dun-nan": "dunan",
        "nei-hu": "neihu",
    },
}

SERVER_TYPES = {"linux", "windows", "aix", "as400"}
VMWARE_TYPES = {"vmware_host", "vmware_vm", "vmware_vcenter"}
ASSET_SEQ_RE = re.compile(r"^HW-[A-Za-z0-9-]{4,32}$")


class ValidationError(ValueError):
    def __init__(self, errors: list[str], warnings: Optional[list[str]] = None) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors
        self.warnings = warnings or []


def _canonical(field: str, value: Any) -> Any:
    if value in (None, ""):
        return value
    if field not in ENUMS:
        return value
    text = str(value).strip()
    if text in ENUMS[field]:
        return text
    mapped = ALIASES.get(field, {}).get(text.lower())
    return mapped or text


def derive_edge_id(dc: Optional[str]) -> str:
    return {"dunan": "edge_dunan", "neihu": "edge_neihu", "banciao": "edge_banciao"}.get(dc or "", "")


def normalize_host_doc(doc: dict[str, Any]) -> dict[str, Any]:
    normalized = {**doc}
    for field in ENUMS:
        if field in normalized:
            normalized[field] = _canonical(field, normalized[field])
    normalized.setdefault("quantity", 1)
    normalized.setdefault("connection", "")
    normalized.setdefault("ssh_port", 22)
    normalized.setdefault("ssh_key_records", {})
    normalized.setdefault("nmon_enabled", False)
    normalized.setdefault("nmon_interval_min", 5)
    normalized.setdefault("extensions", {})
    normalized.setdefault("last_self_check_status", "unknown")
    normalized.setdefault("compliance_score", 0)
    normalized["hostname"] = str(normalized.get("hostname", "")).strip()
    normalized["asset_seq"] = str(normalized.get("asset_seq") or f"HOST-{normalized['hostname']}").strip()
    normalized["ip_addresses"] = _listify(normalized.get("ip_addresses"))
    normalized["network_segments"] = _listify(normalized.get("network_segments"))
    if normalized.get("ip") and normalized["ip"] not in normalized["ip_addresses"]:
        normalized["ip_addresses"].insert(0, str(normalized["ip"]).strip())
    if not normalized.get("ip") and normalized["ip_addresses"]:
        normalized["ip"] = normalized["ip_addresses"][0]
    normalized["edge_id"] = normalized.get("edge_id") or derive_edge_id(normalized.get("dc"))
    return normalized


def _listify(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).replace("\r", "\n").replace(";", "\n").replace(",", "\n")
    return [part.strip() for part in text.splitlines() if part.strip()]


def validate_host_doc(doc: dict[str, Any], partial: bool = False) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not partial:
        for field in REQUIRED_FIELDS:
            if doc.get(field) in (None, ""):
                errors.append(f"{field} is required")

    for field, allowed in ENUMS.items():
        if field in doc and doc.get(field) not in (None, "") and doc.get(field) not in allowed:
            warnings.append(f"{field} is outside known values: {doc.get(field)}")

    asset_seq = doc.get("asset_seq")
    if asset_seq and not ASSET_SEQ_RE.match(str(asset_seq)):
        warnings.append("asset_seq should look like HW-XXXXXXXX")

    if not doc.get("hostname"):
        errors.append("hostname is required and must be unique")

    ip = doc.get("ip")
    if ip:
        try:
            ipaddress.ip_address(str(ip))
        except ValueError:
            errors.append("ip must be a valid IPv4/IPv6 address")

    for address in doc.get("ip_addresses") or []:
        try:
            ipaddress.ip_address(str(address))
        except ValueError:
            errors.append(f"ip_addresses contains invalid IP: {address}")

    for segment in doc.get("network_segments") or []:
        try:
            ipaddress.ip_network(str(segment), strict=False)
        except ValueError:
            errors.append(f"network_segments contains invalid CIDR: {segment}")

    for cia_field in ("integrity", "confidentiality", "availability"):
        if cia_field in doc and doc.get(cia_field) not in (None, ""):
            try:
                value = int(doc[cia_field])
            except (TypeError, ValueError):
                errors.append(f"{cia_field} must be an integer 0-3")
                continue
            if value not in {0, 1, 2, 3}:
                errors.append(f"{cia_field} must be 0-3")

    host_type = doc.get("host_type")
    is_draft = doc.get("status") == "draft"
    if host_type in SERVER_TYPES and not is_draft:
        if not doc.get("connection"):
            errors.append("server hosts require connection")
        if not doc.get("os"):
            errors.append("server hosts require os")
    if host_type in VMWARE_TYPES and doc.get("connection") not in {None, "", "vcenter_api"}:
        errors.append("vmware hosts require connection=vcenter_api")

    return errors, warnings


def assert_valid_host_doc(doc: dict[str, Any], partial: bool = False) -> list[str]:
    errors, warnings = validate_host_doc(doc, partial=partial)
    if errors:
        raise ValidationError(errors, warnings)
    return warnings
