from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable

from webapp.services import host_service
from webapp.services.csv_service import MAX_UI_IMPORT_ROWS, xlsx_workbook_rows_from_bytes
from webapp.services.host_schema import normalize_host_doc
from webapp.services.mongo_service import get_collection


ASSET_COLLECTION = "cmdb_asset_pool"

COMMON_ALIASES = {
    "盤點單位-處別": "division",
    "盤點單位-部門": "department",
    "總點單位-識別": "division",
    "總點單位-級別": "division",
    "總點單位-部門": "department",
    "資產序號": "asset_seq",
    "資產狀態": "status",
    "群組名稱": "group_name",
    "AP ID": "apid",
    "APID": "apid",
    "資產名稱": "asset_name",
    "整體基礎架構": "infrastructure",
    "資產用途": "asset_usage",
    "擁有者": "owner",
    "保管者": "custodian",
    "使用單位": "user_unit",
    "附加說明": "note",
    "完整性(I)": "integrity",
    "機密性(C)": "confidentiality",
    "可用性(A)": "availability",
    "申請單編號": "request_no",
}

HARDWARE_ALIASES = {
    **COMMON_ALIASES,
    "設備機型": "device_model",
    "資產實體位置": "location",
    "機櫃編號": "rack_no",
    "數量": "quantity",
    "環境別": "environment",
    "主機名稱": "hostname",
    "作業系統": "os",
    "BIG IP/VI": "bigip",
    "硬體編號": "hardware_seq",
    "IP": "ip",
    "使用者": "user",
    "所屬公司": "company",
}

DATA_ALIASES = {
    **COMMON_ALIASES,
    "資料類別": "data_category",
    "資料保留年限": "data_retention_period",
    "資料備份方式": "backup_method",
    "主機名稱": "hostname",
    "IP": "ip",
    "備份頻率": "backup_frequency",
    "個資群組名稱": "personal_data_group_name",
    "個人資料": "personal_data",
}

SOFTWARE_ALIASES = {
    **COMMON_ALIASES,
    "處理個資": "personal_data",
    "委外維護": "outsourced_maintenance",
    "所屬公司": "company",
}

PEOPLE_ALIASES = {
    **COMMON_ALIASES,
    "人員姓名": "person_name",
    "隸屬單位-處別": "affiliation_division",
    "隸屬單位-部門": "affiliation_department",
    "聯絡電話": "phone",
    "職務概述": "job_summary",
    "代理人1": "proxy_name",
    "代理人聯絡電話": "proxy_phone",
}

TYPE_LABELS = {
    "hardware": "硬體 / 主機設備",
    "data": "資料資產",
    "software": "軟體資產",
    "people": "人員 / 聯絡窗口",
    "unknown": "未辨識",
}

TYPE_ALIASES = {
    "hardware": HARDWARE_ALIASES,
    "data": DATA_ALIASES,
    "software": SOFTWARE_ALIASES,
    "people": PEOPLE_ALIASES,
}

STATUS_ALIASES = {
    "使用中": "active",
    "已停用": "disabled",
    "停用": "disabled",
    "汰除": "retired",
    "已汰除": "retired",
}

_HOST_LOOKUP_DISABLED = False

ENV_ALIASES = {
    "正式": "PROD",
    "生產": "PROD",
    "測試": "TEST",
    "開發": "DEV",
    "備援": "BACKUP",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _to_int(value: Any, default: int = 0) -> int:
    text = _clean(value)
    if not text:
        return default
    try:
        return int(float(text))
    except ValueError:
        return default


def _public(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if not doc:
        return None
    out = {k: v for k, v in doc.items() if k != "_id"}
    if "_id" in doc:
        out["_id"] = str(doc["_id"])
    return out


def classify_sheet(headers: Iterable[str]) -> str:
    names = {_clean(header) for header in headers if _clean(header)}
    if "資料類別" in names and {"主機名稱", "IP"} & names:
        return "data"
    if ({"作業系統", "設備機型", "硬體編號"} & names) and {"主機名稱", "IP"} <= names:
        return "hardware"
    if "人員姓名" in names:
        return "people"
    if "委外維護" in names or ("處理個資" in names and "AP ID" in names):
        return "software"
    return "unknown"


def normalize_sheet_row(row: dict[str, str], sheet_type: str) -> dict[str, Any]:
    aliases = TYPE_ALIASES.get(sheet_type, COMMON_ALIASES)
    normalized: dict[str, Any] = {}
    extensions: dict[str, Any] = {}
    for raw_key, raw_value in row.items():
        if raw_key == "_row_no":
            continue
        value = _clean(raw_value)
        if not value:
            continue
        key = aliases.get(_clean(raw_key))
        if key:
            normalized[key] = value
        else:
            extensions[_clean(raw_key)] = value
    if extensions:
        normalized["extensions"] = extensions
    if "status" in normalized:
        normalized["status"] = STATUS_ALIASES.get(_clean(normalized["status"]), _clean(normalized["status"]))
    if "environment" in normalized:
        normalized["environment"] = ENV_ALIASES.get(_clean(normalized["environment"]), _clean(normalized["environment"]))
    for key in ("quantity", "integrity", "confidentiality", "availability"):
        if key in normalized:
            normalized[key] = _to_int(normalized[key], 1 if key == "quantity" else 0)
    return normalized


def _infer_host_type(row: dict[str, Any]) -> str:
    text = " ".join([_clean(row.get("os")), _clean(row.get("device_model")), _clean(row.get("asset_usage"))]).lower()
    if "windows" in text or "win" in text:
        return "windows"
    if "linux" in text or "red hat" in text or "rocky" in text or "debian" in text:
        return "linux"
    if "aix" in text:
        return "aix"
    if "as400" in text or "iseries" in text:
        return "as400"
    if "vmware" in text or "vcenter" in text:
        return "vmware_host"
    if "switch" in text or "router" in text or "firewall" in text or "storage" in text or "nas" in text:
        return "network_device"
    return "end_device"


def _infer_dc(row: dict[str, Any]) -> str:
    text = _clean(row.get("location")) + " " + _clean(row.get("rack_no"))
    if "內湖" in text:
        return "neihu"
    if "板橋" in text:
        return "banciao"
    return "dunan"


def _host_doc_from_hardware(row: dict[str, Any], user: str) -> dict[str, Any]:
    host_type = _infer_host_type(row)
    connection = ""
    if host_type in {"linux", "aix"}:
        connection = "ssh"
    elif host_type == "windows":
        connection = "winrm"
    elif host_type.startswith("vmware"):
        connection = "vcenter_api"
    doc = {
        "division": row.get("division") or row.get("owner") or "待補",
        "department": row.get("department") or row.get("user_unit") or row.get("owner") or "待補",
        "asset_seq": row.get("asset_seq") or f"DISC-{row.get('ip') or row.get('hostname')}",
        "status": "draft",
        "group_name": row.get("group_name") or "H4",
        "apid": row.get("apid") or "",
        "asset_name": row.get("asset_name") or row.get("hostname") or row.get("ip") or "待補",
        "device_type": row.get("device_type") or row.get("asset_name") or host_type,
        "device_model": row.get("device_model") or "",
        "asset_usage": row.get("asset_usage") or "",
        "location": row.get("location") or "",
        "rack_no": row.get("rack_no") or "",
        "quantity": row.get("quantity") or 1,
        "owner": row.get("owner") or row.get("custodian") or "待補",
        "environment": row.get("environment") or "PROD",
        "hostname": row.get("hostname") or f"scan-{row.get('ip') or row.get('asset_seq')}",
        "os": "" if _clean(row.get("os")).upper() in {"N/A", "NA", "無"} else row.get("os", ""),
        "bigip": row.get("bigip") or "",
        "hardware_seq": row.get("hardware_seq") or "",
        "ip": row.get("ip") or "",
        "custodian": row.get("custodian") or row.get("owner") or "待補",
        "user": row.get("user") or "",
        "user_unit": row.get("user_unit") or "",
        "note": row.get("note") or "",
        "company": row.get("company") or row.get("division") or "待補",
        "integrity": row.get("integrity", 0),
        "confidentiality": row.get("confidentiality", 0),
        "availability": row.get("availability", 0),
        "host_type": host_type,
        "dc": _infer_dc(row),
        "connection": connection,
        "ssh_port": 22,
        "import_source": "cmdb_workbook_hardware",
        "updated_by": user,
        "extensions": {
            **(row.get("extensions") or {}),
            "cmdb_request_no": row.get("request_no") or "",
            "cmdb_infrastructure": row.get("infrastructure") or "",
        },
    }
    return normalize_host_doc(doc)


def _find_host_link(row: dict[str, Any]) -> dict[str, Any]:
    global _HOST_LOOKUP_DISABLED
    candidates = [_clean(row.get("hostname")), _clean(row.get("ip"))]
    for value in candidates:
        if not value:
            continue
        if _HOST_LOOKUP_DISABLED:
            break
        try:
            host = host_service.get_host(value)
        except Exception:
            _HOST_LOOKUP_DISABLED = True
            host = None
        if host:
            return {
                "asset_seq": host.get("asset_seq"),
                "hostname": host.get("hostname"),
                "ip": host.get("ip"),
                "status": "linked",
            }
    if _clean(row.get("ip")) or _clean(row.get("hostname")):
        return {"status": "unmatched", "hostname": _clean(row.get("hostname")), "ip": _clean(row.get("ip"))}
    return {"status": "not_applicable"}


def workbook_preview(payload: bytes) -> dict[str, Any]:
    sheets = xlsx_workbook_rows_from_bytes(payload)
    result = {
        "status": "ok",
        "total_sheets": len(sheets),
        "total_rows": sum(len(sheet["rows"]) for sheet in sheets),
        "sheets": [],
        "totals": Counter(),
    }
    for sheet in sheets:
        sheet_type = classify_sheet(sheet.get("headers", []))
        rows = sheet.get("rows") or []
        row_count = len(rows)
        normalized = [normalize_sheet_row(row, sheet_type) for row in rows]
        keys = [_clean(row.get("asset_seq")) for row in normalized if _clean(row.get("asset_seq"))]
        duplicates = sum(count - 1 for count in Counter(keys).values() if count > 1)
        missing_host_identity = 0
        if sheet_type == "hardware":
            missing_host_identity = sum(1 for row in normalized if not _clean(row.get("hostname")) and not _clean(row.get("ip")))
        linkable = 0
        unmatched = 0
        if sheet_type == "data":
            for row in normalized:
                link = _find_host_link(row)
                linkable += 1 if link["status"] == "linked" else 0
                unmatched += 1 if link["status"] == "unmatched" else 0
        action = {
            "hardware": "可建立主機草稿，正式納管前再補欄位與採集帳號。",
            "data": "可進資料資產池，並用 IP / 主機名稱嘗試關聯主機。",
            "software": "可進軟體資產池，後續用 AP ID / 系統名稱關聯。",
            "people": "可進人員窗口池，後續連到 owner / 保管者 / 代理人。",
        }.get(sheet_type, "先進預檢，不建議匯入正式資料。")
        status = "ready" if sheet_type != "unknown" and row_count <= MAX_UI_IMPORT_ROWS else "needs_review"
        result["sheets"].append(
            {
                "name": sheet["name"],
                "type": sheet_type,
                "type_label": TYPE_LABELS.get(sheet_type, sheet_type),
                "row_count": row_count,
                "header_count": len([h for h in sheet.get("headers", []) if h]),
                "duplicate_asset_seq": duplicates,
                "missing_host_identity": missing_host_identity,
                "linked_hosts": linkable,
                "unmatched_hosts": unmatched,
                "status": status,
                "recommended_action": action,
                "sample": normalized[:3],
            }
        )
        result["totals"][sheet_type] += row_count
    result["totals"] = dict(result["totals"])
    if not sheets:
        result["status"] = "needs_review"
    return result


def import_hardware_drafts(payload: bytes, user: str) -> dict[str, Any]:
    preview = workbook_preview(payload)
    result = {"created": 0, "updated": 0, "failed": 0, "draft": 0, "errors": [], "sheets": preview["sheets"]}
    for sheet in xlsx_workbook_rows_from_bytes(payload):
        if classify_sheet(sheet.get("headers", [])) != "hardware":
            continue
        for row in sheet.get("rows") or []:
            line = int(row.get("_row_no") or 0)
            try:
                normalized = normalize_sheet_row(row, "hardware")
                doc = _host_doc_from_hardware(normalized, user)
                existed = host_service.get_host(doc.get("asset_seq", "")) is not None
                host = host_service.upsert_host(doc, user=user)
                result["updated" if existed else "created"] += 1
                if host.get("status") == "draft":
                    result["draft"] += 1
            except Exception as exc:
                result["failed"] += 1
                result["errors"].append({"sheet": sheet["name"], "line": line, "error": str(exc)})
    result["total_rows"] = result["created"] + result["updated"] + result["failed"]
    return result


def import_asset_pool(payload: bytes, user: str, kinds: set[str] | None = None) -> dict[str, Any]:
    allowed = kinds or {"data", "software", "people"}
    col = get_collection(ASSET_COLLECTION)
    result = {"created": 0, "updated": 0, "failed": 0, "linked": 0, "unmatched": 0, "errors": []}
    for sheet in xlsx_workbook_rows_from_bytes(payload):
        sheet_type = classify_sheet(sheet.get("headers", []))
        if sheet_type not in allowed:
            continue
        for row in sheet.get("rows") or []:
            line = int(row.get("_row_no") or 0)
            try:
                normalized = normalize_sheet_row(row, sheet_type)
                asset_seq = _clean(normalized.get("asset_seq")) or f"{sheet_type}-{sheet['name']}-{line}"
                link = _find_host_link(normalized) if sheet_type == "data" else {"status": "not_applicable"}
                if link["status"] == "linked":
                    result["linked"] += 1
                if link["status"] == "unmatched":
                    result["unmatched"] += 1
                doc = {
                    "object_type": sheet_type,
                    "sheet_name": sheet["name"],
                    "asset_seq": asset_seq,
                    "asset_name": normalized.get("asset_name") or normalized.get("person_name") or asset_seq,
                    "apid": normalized.get("apid") or "",
                    "status": normalized.get("status") or "active",
                    "owner": normalized.get("owner") or "",
                    "custodian": normalized.get("custodian") or "",
                    "host_link": link,
                    "data": normalized,
                    "raw": {k: v for k, v in row.items() if k != "_row_no"},
                    "updated_at": _now(),
                    "updated_by": user,
                    "import_source": "cmdb_workbook_asset_pool",
                }
                existing = col.find_one({"object_type": sheet_type, "asset_seq": asset_seq})
                if existing:
                    col.update_one({"_id": existing["_id"]}, {"$set": doc})
                    result["updated"] += 1
                else:
                    doc["created_at"] = _now()
                    doc["created_by"] = user
                    col.insert_one(doc)
                    result["created"] += 1
            except Exception as exc:
                result["failed"] += 1
                result["errors"].append({"sheet": sheet["name"], "line": line, "error": str(exc)})
    result["total_rows"] = result["created"] + result["updated"] + result["failed"]
    return result


def asset_pool_overview(limit: int = 200) -> dict[str, Any]:
    try:
        col = get_collection(ASSET_COLLECTION)
        counts = {str(item.get("_id")): int(item.get("count", 0)) for item in col.aggregate([{"$group": {"_id": "$object_type", "count": {"$sum": 1}}}])}
        items = [_public(doc) for doc in col.find({}, {"_id": 1, "object_type": 1, "asset_seq": 1, "asset_name": 1, "apid": 1, "owner": 1, "custodian": 1, "host_link": 1, "updated_at": 1}).sort("updated_at", -1).limit(limit)]
    except Exception as exc:
        return {"counts": {}, "total": 0, "items": [], "error": str(exc)}
    return {"counts": counts, "total": sum(counts.values()), "items": items}
