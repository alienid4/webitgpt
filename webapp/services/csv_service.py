from __future__ import annotations

import csv
import html
import io
import json
import time
import zipfile
import xml.etree.ElementTree as ET
from typing import Any

from webapp.services import host_service
from webapp.services.host_schema import ASSET_FIELDS, ValidationError


XLSX_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
MAX_UI_IMPORT_ROWS = 2000

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

CMDB_DC_ALIASES = {"敦南": "dunan", "內湖": "neihu", "板橋": "banciao"}


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
    inferred_host_type = host_service.infer_host_type_from_os(normalized.get("os") or "")
    if not inferred_host_type:
        inferred_host_type = host_service.infer_host_type_from_os(
            " ".join(str(normalized.get(key) or "") for key in ("device_type", "asset_usage", "system_name"))
        )
    if not normalized.get("host_type") or normalized.get("host_type") in {"end_device", "unknown"}:
        normalized["host_type"] = inferred_host_type or normalized.get("host_type") or "end_device"
        if inferred_host_type:
            normalized["host_type_source"] = "import_os_inference_rule"
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


def _error_category(field: str, message: str) -> str:
    text = f"{field} {message}".lower()
    if "duplicate" in text or "already exists" in text:
        return "重複資料"
    if "required" in text:
        return "必填缺漏"
    if "ip" in text:
        return "IP 格式錯誤"
    if "integer" in text or "0-3" in text:
        return "CIA/數字格式錯誤"
    if "host_type" in text:
        return "主機類型需確認"
    return "資料格式需確認"


def _human_message(field: str, message: str) -> str:
    category = _error_category(field, message)
    if category == "必填缺漏":
        return f"{field} 沒有資料，請補齊後再匯入。"
    if category == "IP 格式錯誤":
        return "IP 欄位不是合法 IPv4/IPv6，請檢查空白、中文符號或打錯。"
    if category == "CIA/數字格式錯誤":
        return f"{field} 必須是 0 到 3 的數字。"
    if category == "重複資料":
        return "資料和既有 CMDB 或同批資料重複，請確認要更新還是改名。"
    if category == "主機類型需確認":
        return "主機類型不在標準清單，請改成 linux/windows/aix/as400/vmware_host/network_device/end_device。"
    return str(message)


def _summarize_result(result: dict[str, Any]) -> dict[str, Any]:
    categories: dict[str, int] = {}
    fields: dict[str, int] = {}
    for item in result.get("errors", []):
        category = item.get("category") or _error_category(str(item.get("field", "")), str(item.get("error", "")))
        categories[category] = categories.get(category, 0) + 1
        field = str(item.get("field") or "整列")
        fields[field] = fields.get(field, 0) + 1
    result["summary"] = {
        "total_rows": result.get("total_rows", 0),
        "success": result.get("created", 0) + result.get("updated", 0),
        "created": result.get("created", 0),
        "updated": result.get("updated", 0),
        "draft": result.get("draft", 0),
        "failed": result.get("failed", 0),
        "categories": [{"category": key, "count": value} for key, value in sorted(categories.items(), key=lambda item: (-item[1], item[0]))],
        "fields": [{"field": key, "count": value} for key, value in sorted(fields.items(), key=lambda item: (-item[1], item[0]))],
    }
    return result


def _too_many_rows_result(row_count: int) -> dict[str, Any]:
    return _summarize_result(
        {
            "created": 0,
            "updated": 0,
            "failed": 1,
            "draft": 0,
            "total_rows": row_count,
            "elapsed_seconds": 0,
            "errors": [
                {
                    "line": "",
                    "field": "file",
                    "error": f"too many rows: {row_count}",
                    "category": "匯入筆數過大",
                    "human_message": f"單次匯入最多 {MAX_UI_IMPORT_ROWS} 筆，目前檔案有 {row_count} 筆。",
                    "suggestion": "請先拆成多個 CSV/Excel 檔分批匯入，避免瀏覽器長時間等待。",
                }
            ],
        }
    )


def _xlsx_col_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha()).upper()
    value = 0
    for ch in letters:
        value = value * 26 + (ord(ch) - 64)
    return max(0, value - 1)


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    values: list[str] = []
    for item in root.findall("m:si", XLSX_NS):
        values.append("".join(node.text or "" for node in item.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")))
    return values


def _xlsx_sheet_paths(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    rel_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rels = {item.attrib["Id"]: item.attrib["Target"] for item in rel_root}
    wb_root = ET.fromstring(archive.read("xl/workbook.xml"))
    paths: list[tuple[str, str]] = []
    for sheet in wb_root.findall("m:sheets/m:sheet", XLSX_NS):
        rid = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "")
        target = rels.get(rid, "")
        if target:
            paths.append((sheet.attrib.get("name", ""), target[1:] if target.startswith("/") else f"xl/{target}"))
    return paths


def xlsx_workbook_rows_from_bytes(payload: bytes) -> list[dict[str, Any]]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        shared_strings = _xlsx_shared_strings(archive)
        sheets: list[dict[str, Any]] = []
        for workbook_sheet_name, sheet_path in _xlsx_sheet_paths(archive):
            root = ET.fromstring(archive.read(sheet_path))
            sheet_name = workbook_sheet_name or sheet_path.rsplit("/", 1)[-1].removesuffix(".xml")
            raw_rows: list[list[str]] = []
            for row in root.findall(".//m:sheetData/m:row", XLSX_NS):
                values: dict[int, str] = {}
                max_index = -1
                for cell in row.findall("m:c", XLSX_NS):
                    idx = _xlsx_col_index(cell.attrib.get("r", ""))
                    max_index = max(max_index, idx)
                    if cell.attrib.get("t") == "inlineStr":
                        value = "".join(node.text or "" for node in cell.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"))
                    else:
                        value_node = cell.find("m:v", XLSX_NS)
                        value = value_node.text if value_node is not None else ""
                        if cell.attrib.get("t") == "s" and str(value).isdigit():
                            value = shared_strings[int(value)] if int(value) < len(shared_strings) else ""
                    values[idx] = str(value or "").strip()
                if max_index >= 0:
                    raw_rows.append([values.get(idx, "") for idx in range(max_index + 1)])
            if not raw_rows:
                continue
            headers = [cell.strip() for cell in raw_rows[0]]
            rows = []
            for row_no, row in enumerate(raw_rows[1:], start=2):
                padded = row + [""] * max(0, len(headers) - len(row))
                item = {headers[idx]: padded[idx].strip() for idx in range(len(headers)) if headers[idx]}
                if any(item.values()):
                    item["_row_no"] = str(row_no)
                    rows.append(item)
            sheets.append({"name": sheet_name, "headers": headers, "rows": rows})
        return sheets


def xlsx_rows_from_bytes(payload: bytes) -> list[dict[str, str]]:
    sheets = xlsx_workbook_rows_from_bytes(payload)
    return sheets[0]["rows"] if sheets else []


def _simple_xlsx_bytes(headers: list[str], rows: list[list[Any]], sheet_name: str = "hosts_export") -> bytes:
    def cell_ref(col_idx: int, row_idx: int) -> str:
        col = ""
        n = col_idx + 1
        while n:
            n, rem = divmod(n - 1, 26)
            col = chr(65 + rem) + col
        return f"{col}{row_idx}"

    sheet_rows = []
    for row_idx, row in enumerate([headers] + rows, start=1):
        cells = []
        for col_idx, value in enumerate(row):
            text = html.escape("" if value is None else str(value))
            cells.append(f'<c r="{cell_ref(col_idx, row_idx)}" t="inlineStr"><is><t>{text}</t></is></c>')
        sheet_rows.append(f'<row r="{row_idx}">{"".join(cells)}</row>')
    sheet = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
    workbook = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="{html.escape(sheet_name)}" sheetId="1" r:id="rId1"/></sheets></workbook>'
    rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    wb_rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'
    content_types = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return output.getvalue()


def csv_template() -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_HEADERS, extrasaction="ignore")
    writer.writeheader()
    writer.writerow(SAMPLE_ROW)
    return "\ufeff" + output.getvalue()


def export_hosts_csv(hosts: list[dict[str, Any]]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_HEADERS, extrasaction="ignore")
    writer.writeheader()
    for host in hosts:
        writer.writerow({key: host.get(key, "") for key in CSV_HEADERS})
    return "\ufeff" + output.getvalue()


def export_hosts_xlsx(hosts: list[dict[str, Any]]) -> bytes:
    return _simple_xlsx_bytes(CSV_HEADERS, [[host.get(key, "") for key in CSV_HEADERS] for host in hosts], "hosts_export")


def import_rows(rows: list[dict[str, str]], user: str) -> dict[str, Any]:
    started = time.monotonic()
    if len(rows) > MAX_UI_IMPORT_ROWS:
        return _too_many_rows_result(len(rows))
    result = {"created": 0, "updated": 0, "failed": 0, "draft": 0, "total_rows": len(rows), "errors": []}
    for index, row in enumerate(rows, start=2):
        line = int(row.get("_row_no") or index)
        try:
            doc = _coerce(row)
            existed = host_service.get_host(doc.get("asset_seq", "")) is not None
            host = host_service.upsert_host(doc, user=user)
            result["updated" if existed else "created"] += 1
            if host.get("status") == "draft":
                result["draft"] += 1
        except (ValidationError, ValueError, KeyError) as exc:
            message = str(exc)
            if isinstance(exc, ValidationError) and exc.errors:
                message = exc.errors[0]
            field = next((candidate for candidate in ("asset_seq", "hostname", "ip", "host_type", "integrity", "confidentiality", "availability") if candidate in message), "整列")
            result["failed"] += 1
            result["errors"].append(
                {
                    "line": line,
                    "field": field,
                    "error": message,
                    "category": _error_category(field, message),
                    "human_message": _human_message(field, message),
                    "suggestion": "請修正此列後重新匯入；若是重複資料，請確認 asset_seq/hostname 是否應更新既有資料。",
                }
            )
    result["elapsed_seconds"] = round(time.monotonic() - started, 2)
    return _summarize_result(result)


def import_csv(text: str, user: str) -> dict[str, Any]:
    return import_rows(list(csv.DictReader(io.StringIO(text))), user=user)


def import_xlsx(payload: bytes, user: str) -> dict[str, Any]:
    try:
        return import_rows(xlsx_rows_from_bytes(payload), user=user)
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        return _summarize_result(
            {
                "created": 0,
                "updated": 0,
                "failed": 1,
                "draft": 0,
                "total_rows": 0,
                "errors": [
                    {
                        "line": 1,
                        "field": "file",
                        "error": str(exc),
                        "category": "Excel 檔案格式錯誤",
                        "human_message": "這不是可讀取的 .xlsx 檔，請另存為 Excel 活頁簿後再匯入。",
                        "suggestion": "請使用下載範本或將來源檔另存成 .xlsx。",
                    }
                ],
            }
        )


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
                errors.append({"line": index, "field": "asset_seq", "error": "duplicate asset_seq", "category": "重複資料", "human_message": "同一份檔案內 asset_seq 重複，請保留一筆或改成正確資產序號。"})
            seen_asset_seq.add(asset_seq)
        for field in ("hostname", "ip"):
            if not doc.get(field):
                errors.append({"line": index, "field": field, "error": "required", "category": "必填缺漏", "human_message": _human_message(field, "required")})
        for field in ("quantity", "ssh_port", "integrity", "confidentiality", "availability"):
            if doc.get(field):
                try:
                    int(doc[field])
                except ValueError:
                    errors.append({"line": index, "field": field, "error": "must be an integer", "category": "CIA/數字格式錯誤", "human_message": _human_message(field, "must be an integer")})
    for field in missing_headers:
        errors.insert(0, {"line": 1, "field": field, "error": "missing header", "category": "欄位缺漏", "human_message": f"檔案缺少 {field} 欄位，請確認欄位名稱或使用 Excel 範本。"})
    report = {"status": "ok" if not errors else "needs_review", "row_count": len(rows), "error_count": len(errors), "warning_count": len(warnings), "errors": errors, "warnings": warnings}
    return _summarize_result({**report, "created": 0, "updated": 0, "failed": len(errors), "draft": 0, "total_rows": len(rows)})


def validate_xlsx(payload: bytes) -> dict[str, Any]:
    try:
        rows = xlsx_rows_from_bytes(payload)
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        report = {
            "status": "needs_review",
            "row_count": 0,
            "error_count": 1,
            "warning_count": 0,
            "errors": [
                {
                    "line": 1,
                    "field": "file",
                    "error": str(exc),
                    "category": "Excel 檔案格式錯誤",
                    "human_message": "這不是可讀取的 .xlsx 檔，請另存為 Excel 活頁簿後再匯入。",
                    "suggestion": "請使用下載範本或將來源檔另存成 .xlsx。",
                }
            ],
            "warnings": [],
        }
        return _summarize_result({**report, "created": 0, "updated": 0, "failed": 1, "draft": 0, "total_rows": 0})
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys() if rows else CSV_HEADERS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return validate_csv(output.getvalue())


def validation_errors_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    fields = ["severity", "line", "field", "category", "message", "human_message", "suggestion"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for item in report.get("errors", []):
        writer.writerow({"severity": "error", "line": item.get("line", ""), "field": item.get("field", ""), "category": item.get("category", ""), "message": item.get("error", ""), "human_message": item.get("human_message", ""), "suggestion": item.get("suggestion", "")})
    for item in report.get("warnings", []):
        writer.writerow({"severity": "warning", "line": item.get("line", ""), "field": item.get("field", ""), "category": "提醒", "message": item.get("warning", ""), "human_message": item.get("warning", ""), "suggestion": ""})
    return "\ufeff" + output.getvalue()


def validation_errors_xlsx(report: dict[str, Any]) -> bytes:
    rows = []
    for item in report.get("errors", []):
        rows.append(["error", item.get("line", ""), item.get("field", ""), item.get("category", ""), item.get("error", ""), item.get("human_message", ""), item.get("suggestion", "")])
    for item in report.get("warnings", []):
        rows.append(["warning", item.get("line", ""), item.get("field", ""), "提醒", item.get("warning", ""), item.get("warning", ""), ""])
    return _simple_xlsx_bytes(["severity", "line", "field", "category", "message", "human_message", "suggestion"], rows, "cmdb_import_errors")


def import_json(text: str, user: str) -> dict[str, Any]:
    payload = json.loads(text)
    rows = payload if isinstance(payload, list) else [payload]
    result = {"created": 0, "updated": 0, "failed": 0, "draft": 0, "total_rows": len(rows), "errors": []}
    for index, doc in enumerate(rows, start=1):
        try:
            existed = host_service.get_host(doc.get("asset_seq", "")) is not None
            host = host_service.upsert_host(doc, user=user)
            result["updated" if existed else "created"] += 1
            if host.get("status") == "draft":
                result["draft"] += 1
        except (ValidationError, ValueError, KeyError) as exc:
            result["failed"] += 1
            result["errors"].append({"item": index, "field": "整列", "error": str(exc), "category": _error_category("", str(exc)), "human_message": _human_message("", str(exc))})
    return _summarize_result(result)
