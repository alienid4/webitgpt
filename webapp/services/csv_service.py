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


def _coerce(row: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {key: value.strip() for key, value in row.items() if key and value is not None}
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
    headers = reader.fieldnames or []
    missing_headers = [field for field in ("asset_seq", "hostname", "ip", "host_type") if field not in headers]
    rows = []
    errors = []
    warnings = []
    seen_asset_seq: set[str] = set()
    for index, row in enumerate(reader, start=2):
        doc = {key: str(value or "").strip() for key, value in row.items() if key}
        if not any(doc.values()):
            continue
        rows.append(doc)
        asset_seq = doc.get("asset_seq", "")
        if asset_seq:
            if asset_seq in seen_asset_seq:
                errors.append({"line": index, "field": "asset_seq", "error": "duplicate asset_seq"})
            seen_asset_seq.add(asset_seq)
        for field in ("asset_seq", "hostname", "ip", "host_type"):
            if not doc.get(field):
                errors.append({"line": index, "field": field, "error": "required"})
        if doc.get("host_type") and doc["host_type"] not in {"linux", "windows", "aix", "as400", "vmware", "network", "other"}:
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
