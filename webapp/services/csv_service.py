from __future__ import annotations

import csv
import io
import json
from typing import Any

from webapp.services import host_service
from webapp.services.host_schema import ASSET_FIELDS, ValidationError


CSV_HEADERS = [
    *ASSET_FIELDS,
    "host_type",
    "dc",
    "ip_addresses",
    "network_segments",
    "connection",
    "ssh_user",
    "ssh_port",
    "tier",
    "ap_owner",
    "system_name",
    "os_group",
]

SAMPLE_ROW = {
    "division": "IT",
    "department": "Operations",
    "asset_seq": "HW-00009999",
    "status": "active",
    "group_name": "H4",
    "asset_name": "CSV sample host",
    "device_type": "VM",
    "quantity": "1",
    "owner": "IT",
    "environment": "DEV",
    "hostname": "csv-sample",
    "os": "Debian 13",
    "ip": "192.168.1.250",
    "ip_addresses": "192.168.1.250",
    "network_segments": "192.168.1.0/24",
    "custodian": "Alienlee",
    "user_unit": "IT",
    "company": "example-corp",
    "integrity": "1",
    "confidentiality": "2",
    "availability": "1",
    "host_type": "linux",
    "dc": "dunan",
    "connection": "ssh",
    "ssh_user": "sysinfra",
    "ssh_port": "22",
    "tier": "medium",
    "ap_owner": "Alienlee",
    "system_name": "CSV sample",
    "os_group": "debian",
}

CMDB_HEADER_ALIASES = {
    "總點單位-級別": "division",
    "總點單位-部門": "department",
    "資產序號": "asset_seq",
    "資產狀態": "status",
    "群組名稱": "group_name",
    "資料類別": "asset_usage",
    "APID": "apid",
    "資產名稱": "asset_name",
    "整體基礎架構": "device_type",
    "雲端服務類型": "device_model",
    "專案名稱": "system_name",
    "地區/可用區域": "dc",
    "擁有者": "owner",
    "保管者": "custodian",
    "主機名稱": "hostname",
    "IP": "ip",
    "使用單位": "user_unit",
    "附加說明": "note",
    "完整性(I)": "integrity",
    "機密性(C)": "confidentiality",
    "可用性(A)": "availability",
}

CMDB_EXTENSION_ALIASES = {
    "Cloud Service Pow": "cloud_service_power",
    "資料保留年限": "data_retention_period",
    "資料備份方式": "backup_method",
    "備份頻率": "backup_frequency",
    "個資群組名稱": "personal_data_group_name",
    "個人資料": "personal_data",
    "申請單編號": "request_no",
}

CMDB_STATUS_ALIASES = {
    "使用中": "active",
    "停用": "disabled",
    "已停用": "disabled",
    "退役": "retired",
    "已退役": "retired",
}

CMDB_DC_ALIASES = {
    "敦南": "dunan",
    "內湖": "neihu",
    "板橋": "banciao",
}


def _normalize_header(header: str) -> str:
    text = str(header or "").strip().replace("\ufeff", "")
    return CMDB_HEADER_ALIASES.get(text, text)


def _normalize_value(field: str, value: Any) -> Any:
    text = str(value or "").strip()
    if field == "status":
        return CMDB_STATUS_ALIASES.get(text, text)
    if field == "dc":
        return CMDB_DC_ALIASES.get(text, text)
    return text


def _normalize_row(row: dict[str, str]) -> dict[str, Any]:
    doc: dict[str, Any] = {}
    extensions: dict[str, Any] = {}
    for raw_key, raw_value in row.items():
        if not raw_key or raw_value is None:
            continue
        raw_header = str(raw_key).strip().replace("\ufeff", "")
        value = str(raw_value).strip()
        if value == "":
            continue
        if raw_header in CMDB_EXTENSION_ALIASES:
            extensions[CMDB_EXTENSION_ALIASES[raw_header]] = value
            continue
        field = _normalize_header(raw_header)
        doc[field] = _normalize_value(field, value)
    if extensions:
        doc["extensions"] = extensions
    return doc


def _apply_cmdb_defaults(doc: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(doc)
    normalized.setdefault("division", normalized.get("owner") or "未填")
    normalized.setdefault("department", normalized.get("user_unit") or normalized.get("owner") or "未填")
    normalized.setdefault("status", "active")
    normalized.setdefault("group_name", "H4")
    normalized.setdefault("asset_name", normalized.get("hostname") or normalized.get("asset_seq") or normalized.get("ip") or "未命名資產")
    normalized.setdefault("device_type", normalized.get("asset_usage") or "CMDB")
    normalized.setdefault("quantity", 1)
    normalized.setdefault("owner", normalized.get("custodian") or "未填")
    normalized.setdefault("environment", "PROD")
    normalized.setdefault("hostname", normalized.get("ip") or normalized.get("asset_seq") or "")
    normalized.setdefault("custodian", normalized.get("owner") or "未填")
    normalized.setdefault("company", normalized.get("division") or "未填")
    normalized.setdefault("host_type", "end_device")
    normalized.setdefault("dc", "dunan")
    normalized.setdefault("integrity", 0)
    normalized.setdefault("confidentiality", 0)
    normalized.setdefault("availability", 0)
    return normalized


def _coerce(row: dict[str, str]) -> dict[str, Any]:
    out = _apply_cmdb_defaults(_normalize_row(row))
    for key in ("quantity", "ssh_port", "integrity", "confidentiality", "availability"):
        if out.get(key) not in (None, ""):
            out[key] = int(out[key])
    return out


def csv_template() -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_HEADERS, extrasaction="ignore")
    writer.writeheader()
    writer.writerow(SAMPLE_ROW)
    return output.getvalue()


def export_hosts_csv(hosts: list[dict[str, Any]]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_HEADERS, extrasaction="ignore")
    writer.writeheader()
    for host in hosts:
        writer.writerow({key: host.get(key, "") for key in CSV_HEADERS})
    return output.getvalue()


def import_csv(text: str, user: str) -> dict[str, Any]:
    reader = csv.DictReader(io.StringIO(text))
    result = {"created": 0, "updated": 0, "failed": 0, "errors": []}
    for index, row in enumerate(reader, start=2):
        try:
            doc = _coerce(row)
            existed = host_service.get_host(doc.get("asset_seq", "")) is not None
            host_service.upsert_host(doc, user=user)
            result["updated" if existed else "created"] += 1
        except (ValidationError, ValueError, KeyError) as exc:
            result["failed"] += 1
            result["errors"].append({"line": index, "error": str(exc)})
    return result


def validate_csv(text: str) -> dict[str, Any]:
    reader = csv.DictReader(io.StringIO(text))
    headers = [_normalize_header(field) for field in (reader.fieldnames or [])]
    missing_headers = [field for field in ("hostname", "ip") if field not in headers]
    rows = []
    errors = []
    warnings = []
    seen_asset_seq: set[str] = set()
    for index, row in enumerate(reader, start=2):
        doc = _apply_cmdb_defaults(_normalize_row(row))
        if not any(doc.values()):
            continue
        rows.append(doc)
        asset_seq = doc.get("asset_seq", "")
        if asset_seq:
            if asset_seq in seen_asset_seq:
                errors.append({"line": index, "field": "asset_seq", "error": "duplicate asset_seq"})
            seen_asset_seq.add(asset_seq)
        for field in ("hostname", "ip"):
            if not doc.get(field):
                errors.append({"line": index, "field": field, "error": "required"})
        if doc.get("host_type") and doc["host_type"] not in {"linux", "windows", "aix", "as400", "vmware_host", "vmware_vm", "vmware_vcenter", "network_device", "end_device"}:
            warnings.append({"line": index, "field": "host_type", "warning": "unknown host_type; import may normalize or reject it"})
        for field in ("quantity", "ssh_port", "integrity", "confidentiality", "availability"):
            if doc.get(field):
                try:
                    int(doc[field])
                except ValueError:
                    errors.append({"line": index, "field": field, "error": "must be an integer"})
    for field in missing_headers:
        errors.insert(0, {"line": 1, "field": field, "error": "missing header"})
    return {"status": "ok" if not errors else "needs_review", "row_count": len(rows), "error_count": len(errors), "warning_count": len(warnings), "errors": errors, "warnings": warnings}


def validation_errors_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    fields = ["severity", "line", "field", "message"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for item in report.get("errors", []):
        writer.writerow({"severity": "error", "line": item.get("line", ""), "field": item.get("field", ""), "message": item.get("error", "")})
    for item in report.get("warnings", []):
        writer.writerow({"severity": "warning", "line": item.get("line", ""), "field": item.get("field", ""), "message": item.get("warning", "")})
    return output.getvalue()


def import_json(text: str, user: str) -> dict[str, Any]:
    payload = json.loads(text)
    rows = payload if isinstance(payload, list) else [payload]
    result = {"created": 0, "updated": 0, "failed": 0, "errors": []}
    for index, doc in enumerate(rows, start=1):
        try:
            existed = host_service.get_host(doc.get("asset_seq", "")) is not None
            host_service.upsert_host(doc, user=user)
            result["updated" if existed else "created"] += 1
        except (ValidationError, ValueError, KeyError) as exc:
            result["failed"] += 1
            result["errors"].append({"item": index, "error": str(exc)})
    return result
