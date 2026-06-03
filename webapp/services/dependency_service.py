from __future__ import annotations

import ipaddress
import hashlib
import math
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from bson import ObjectId

from webapp import config
from webapp.services.mongo_service import get_collection
from webapp.services.system_alias_service import canonical_host_system_name, host_matches_system


KNOWN_EXTERNAL = [
    {"name": "Google DNS", "cidr": "8.8.8.0/24", "category": "External"},
    {"name": "Cloudflare", "cidr": "1.1.1.0/24", "category": "External"},
    {"name": "Cloudflare", "cidr": "104.16.0.0/12", "category": "External"},
]

PORT_SERVICE_NAMES = {
    "20": "FTP-DATA",
    "21": "FTP",
    "22": "SSH",
    "23": "TELNET",
    "25": "SMTP",
    "53": "DNS",
    "80": "HTTP",
    "110": "POP3",
    "123": "NTP",
    "143": "IMAP",
    "389": "LDAP",
    "443": "HTTPS",
    "445": "SMB",
    "465": "SMTPS",
    "587": "SMTP",
    "636": "LDAPS",
    "993": "IMAPS",
    "995": "POP3S",
    "1433": "MSSQL",
    "1521": "ORACLE",
    "3306": "MYSQL",
    "3389": "RDP",
    "5432": "POSTGRES",
    "5900": "VNC",
    "6379": "REDIS",
    "8002": "WEBITGPT",
    "8080": "HTTP-ALT",
    "8443": "HTTPS-ALT",
    "9444": "EDGE",
    "27017": "MONGO",
}

COMMON_EXPOSURE_PORTS = ["22", "80", "443", "445", "3389", "5432", "3306", "1521", "27017", "6379", "8080", "8443"]
XLSX_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
CORE_SYSTEM_NAMES = ["好麥證券", "交易核心", "帳務核心", "通路核心", "資料核心", "巡檢系統"]
UNASSIGNED_CORE_NAME = "未歸屬核心"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _public(doc: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not doc:
        return None
    item = dict(doc)
    if "_id" in item:
        item["_id"] = str(item["_id"])
    return item


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value else ""


def _local_iso(value: datetime) -> str:
    try:
        return value.astimezone(ZoneInfo(config.TZ_NAME)).isoformat()
    except Exception:  # noqa: BLE001 - timezone name may be customized by deployment
        return value.isoformat()


def _system_id(name: str) -> str:
    key = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip()).strip("-").upper()
    if key:
        return f"SYS-{key}"
    digest = hashlib.sha1(name.strip().encode("utf-8")).hexdigest()[:8].upper()
    return f"SYS-{digest}"


def _system_id_from_code_or_name(code: str, name: str) -> str:
    raw = (code or "").strip() or (name or "").strip()
    key = re.sub(r"[^a-zA-Z0-9]+", "-", raw).strip("-").upper()
    if key:
        return f"SYS-{key}"
    return _system_id(name or "unknown")


def _confidence_value(label: str) -> float:
    text = (label or "").strip()
    if text in {"高", "high", "HIGH"}:
        return 0.9
    if text in {"低", "low", "LOW"}:
        return 0.3
    return 0.6


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    values: list[str] = []
    for item in root.findall("m:si", XLSX_NS):
        parts = []
        for text_node in item.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"):
            parts.append(text_node.text or "")
        values.append("".join(parts))
    return values


def _xlsx_sheet_paths(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    rel_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rels = {item.attrib["Id"]: item.attrib["Target"] for item in rel_root}
    wb_root = ET.fromstring(archive.read("xl/workbook.xml"))
    paths: list[tuple[str, str]] = []
    for sheet in wb_root.findall("m:sheets/m:sheet", XLSX_NS):
        rid = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "")
        target = rels.get(rid, "")
        if not target:
            continue
        path = target[1:] if target.startswith("/") else f"xl/{target}"
        paths.append((sheet.attrib.get("name", ""), path))
    return paths


def _xlsx_rows(path: str | Path) -> list[dict[str, str]]:
    """Read the system relation sheet without requiring openpyxl on Rocky Python 3.9."""
    with zipfile.ZipFile(path) as archive:
        shared_strings = _xlsx_shared_strings(archive)
        for _, sheet_path in _xlsx_sheet_paths(archive):
            root = ET.fromstring(archive.read(sheet_path))
            raw_rows: list[list[str]] = []
            for row in root.findall(".//m:sheetData/m:row", XLSX_NS):
                values = []
                for cell in row.findall("m:c", XLSX_NS):
                    value_node = cell.find("m:v", XLSX_NS)
                    if value_node is None:
                        values.append("")
                        continue
                    value = value_node.text or ""
                    if cell.attrib.get("t") == "s":
                        value = shared_strings[int(value)] if value.isdigit() and int(value) < len(shared_strings) else ""
                    values.append(value.strip())
                raw_rows.append(values)
            if not raw_rows:
                continue
            header = raw_rows[0]
            required = {"來源系統名稱", "目標系統名稱"}
            if not required.issubset(set(header)):
                continue
            rows = []
            for row in raw_rows[1:]:
                padded = row + [""] * max(0, len(header) - len(row))
                item = {header[idx]: padded[idx].strip() for idx in range(len(header))}
                if item.get("來源系統名稱") or item.get("目標系統名稱"):
                    rows.append(item)
            return rows
    return []


def _xlsx_matrix_rows(path: str | Path) -> list[dict[str, str]]:
    """Read a relation matrix: source system rows, target system columns, V means related."""
    with zipfile.ZipFile(path) as archive:
        shared_strings = _xlsx_shared_strings(archive)
        for _, sheet_path in _xlsx_sheet_paths(archive):
            root = ET.fromstring(archive.read(sheet_path))
            raw_rows: list[list[str]] = []
            for row in root.findall(".//m:sheetData/m:row", XLSX_NS):
                values: list[str] = []
                for cell in row.findall("m:c", XLSX_NS):
                    ref = cell.attrib.get("r", "")
                    letters = "".join(ch for ch in ref if ch.isalpha()) or "A"
                    idx = 0
                    for ch in letters:
                        idx = idx * 26 + ord(ch.upper()) - 64
                    idx -= 1
                    while len(values) <= idx:
                        values.append("")
                    value_node = cell.find("m:v", XLSX_NS)
                    value = value_node.text if value_node is not None else ""
                    if cell.attrib.get("t") == "s" and value and value.isdigit():
                        value = shared_strings[int(value)] if int(value) < len(shared_strings) else ""
                    values[idx] = (value or "").strip()
                raw_rows.append(values)
            if not raw_rows:
                continue
            header = raw_rows[0]
            if "系統別" not in header:
                continue
            source_name_idx = header.index("系統別")
            source_code_idx = header.index("APID") if "APID" in header else -1
            source_category_idx = header.index("系統類別") if "系統類別" in header else -1
            matrix_start = source_name_idx + 1
            rows: list[dict[str, str]] = []
            for row_idx, row in enumerate(raw_rows[1:], start=2):
                source_name = row[source_name_idx].strip() if len(row) > source_name_idx else ""
                if not source_name:
                    continue
                source_code = row[source_code_idx].strip() if source_code_idx >= 0 and len(row) > source_code_idx else ""
                source_category = row[source_category_idx].strip() if source_category_idx >= 0 and len(row) > source_category_idx else ""
                for col_idx, target_name in enumerate(header[matrix_start:], start=matrix_start):
                    marker = row[col_idx].strip() if len(row) > col_idx else ""
                    if not marker:
                        continue
                    target_name = (target_name or "").strip()
                    if not target_name or target_name == source_name:
                        continue
                    rows.append(
                        {
                            "來源系統代號": source_code,
                            "來源系統名稱": source_name,
                            "目標系統代號": "",
                            "目標系統名稱": target_name,
                            "介接方式": "矩陣關聯",
                            "方向": "來源到目標",
                            "信心水準": "中",
                            "覆核狀態": "待覆核",
                            "備註": "由第二層系統關聯矩陣匯入，可由關聯管理頁再編輯。",
                            "來源圖檔": "",
                            "來源系統類別": source_category,
                            "矩陣標記": marker,
                            "矩陣列": str(row_idx),
                            "矩陣欄": str(col_idx + 1),
                        }
                    )
            if rows:
                return rows
    return []


def import_system_relations_xlsx(path: str | Path, actor: str = "system", dry_run: bool = False) -> dict[str, Any]:
    rows = _xlsx_rows(path)
    layout = "pair_rows"
    if not rows:
        rows = _xlsx_matrix_rows(path)
        layout = "matrix"
    now = _now()
    systems: dict[str, dict[str, Any]] = {}
    relations: list[dict[str, Any]] = []
    for idx, row in enumerate(rows, start=2):
        source_name = row.get("來源系統名稱", "").strip()
        target_name = row.get("目標系統名稱", "").strip()
        if not source_name or not target_name:
            continue
        source_id = _system_id_from_code_or_name(row.get("來源系統代號", ""), source_name)
        target_id = _system_id_from_code_or_name(row.get("目標系統代號", ""), target_name)
        systems.setdefault(
            source_id,
            {
                "system_id": source_id,
                "display_name": source_name,
                "category": "AP",
                "tier": "C",
                "description": "由系統關聯清單匯入，需由 CMDB 管理者覆核。",
                "owner": "",
                "host_refs": [],
                "external": False,
                "metadata": {
                    "import_source": "system_relations_xlsx",
                    "import_layout": layout,
                    "source_code": row.get("來源系統代號", ""),
                    "system_category": row.get("來源系統類別", ""),
                    "review_status": row.get("覆核狀態", ""),
                },
            },
        )
        systems.setdefault(
            target_id,
            {
                "system_id": target_id,
                "display_name": target_name,
                "category": "AP",
                "tier": "C",
                "description": "由系統關聯清單匯入，需由 CMDB 管理者覆核。",
                "owner": "",
                "host_refs": [],
                "external": False,
                "metadata": {"import_source": "system_relations_xlsx", "import_layout": layout, "source_code": row.get("目標系統代號", ""), "review_status": row.get("覆核狀態", "")},
            },
        )
        relations.append(
            {
                "from_system": source_id,
                "to_system": target_id,
                "rel_type": row.get("介接方式") or "未標示",
                "source": "cmdb_import",
                "confidence": _confidence_value(row.get("信心水準", "")),
                "description": row.get("備註") or "由系統關聯清單匯入，需覆核方向與介接方式。",
                "evidence": {
                    "source_file": row.get("來源圖檔", ""),
                    "direction": row.get("方向", ""),
                    "review_status": row.get("覆核狀態", ""),
                    "row": idx,
                    "matrix_marker": row.get("矩陣標記", ""),
                    "matrix_row": row.get("矩陣列", ""),
                    "matrix_col": row.get("矩陣欄", ""),
                    "imported_at": now.isoformat(),
                },
                "metadata": {
                    "import_layout": layout,
                    "source_name": source_name,
                    "target_name": target_name,
                    "source_code": row.get("來源系統代號", ""),
                    "target_code": row.get("目標系統代號", ""),
                    "interface_type": row.get("介接方式", ""),
                },
            }
        )
    if dry_run:
        return {"status": "dry_run", "layout": layout, "systems": len(systems), "relations": len(relations), "rows": len(rows)}

    for item in systems.values():
        upsert_system(item, actor)
    imported = 0
    for item in relations:
        upsert_relation(item, actor)
        imported += 1
    get_collection("dependency_collect_runs").insert_one(
        {
            "run_id": f"cmdb-import-{now.strftime('%Y%m%d%H%M%S')}",
            "status": "success",
            "collector": "system_relations_xlsx",
            "started_at": now,
            "finished_at": _now(),
            "started_by": actor,
            "host_count": 0,
            "edge_count": imported,
            "snapshot_replaced": False,
            "errors": [],
            "summary": {"layout": layout, "systems": len(systems), "relations": imported, "rows": len(rows)},
        }
    )
    return {"status": "ok", "layout": layout, "systems": len(systems), "relations": imported, "rows": len(rows)}


def cleanup_imported_system_relations(actor: str = "system", dry_run: bool = False) -> dict[str, Any]:
    """Remove only the temporary Excel-imported relation layer."""
    relation_query = {"source": "cmdb_import"}
    system_query = {"metadata.import_source": "system_relations_xlsx", "host_refs": {"$size": 0}}
    relation_count = get_collection("dependency_relations").count_documents(relation_query)
    run_count = get_collection("dependency_collect_runs").count_documents({"collector": "system_relations_xlsx"})
    candidate_systems = list(get_collection("dependency_systems").find(system_query, {"system_id": 1}))
    system_ids = [item.get("system_id") for item in candidate_systems if item.get("system_id")]

    if dry_run:
        return {
            "status": "dry_run",
            "relations": relation_count,
            "collect_runs": run_count,
            "candidate_systems": len(system_ids),
        }

    get_collection("dependency_relations").delete_many(relation_query)
    still_referenced = {
        item.get("from_system")
        for item in get_collection("dependency_relations").find({"from_system": {"$in": system_ids}}, {"from_system": 1})
    }
    still_referenced.update(
        item.get("to_system")
        for item in get_collection("dependency_relations").find({"to_system": {"$in": system_ids}}, {"to_system": 1})
    )
    removable_systems = [system_id for system_id in system_ids if system_id not in still_referenced]
    system_deleted = 0
    if removable_systems:
        system_deleted = get_collection("dependency_systems").delete_many({"system_id": {"$in": removable_systems}, "host_refs": {"$size": 0}}).deleted_count
    run_deleted = get_collection("dependency_collect_runs").delete_many({"collector": "system_relations_xlsx"}).deleted_count
    return {
        "status": "ok",
        "relations_deleted": relation_count,
        "systems_deleted": int(system_deleted),
        "collect_runs_deleted": int(run_deleted),
        "updated_by": actor,
    }


def _hosts() -> list[dict[str, Any]]:
    return [
        _public(doc) or {}
        for doc in get_collection("hosts").find({}, {"ssh_key": 0}).sort("hostname", 1)
    ]


def _host_business_system_name(host: dict[str, Any]) -> str:
    """Return the human business system name; never promote hostname to system."""
    asset_name = str(host.get("asset_name") or "").strip()
    asset_seq = str(host.get("asset_seq") or "").strip().upper()
    hostname = str(host.get("hostname") or "").strip().lower()
    if asset_seq.startswith("DISC-") or hostname.startswith("scan-") or asset_name.startswith("掃描發現"):
        return ""
    return canonical_host_system_name(host, default="")


def _host_node_key(host: dict[str, Any]) -> str:
    return str(host.get("asset_seq") or host.get("hostname") or host.get("ip") or "").strip()


def _system_host_match_names(system: dict[str, Any]) -> list[str]:
    metadata = system.get("metadata") or {}
    names: list[str] = []
    for value in (
        system.get("display_name"),
        metadata.get("asset_name"),
        metadata.get("system_name"),
    ):
        text = str(value or "").strip()
        if text and text not in names:
            names.append(text)
    return names


def _host_matches_dependency_system(host: dict[str, Any], system: dict[str, Any]) -> bool:
    return any(host_matches_system(host, name) for name in _system_host_match_names(system))


def sync_systems_from_hosts(actor: str = "system") -> int:
    now = _now()
    col = get_collection("dependency_systems")
    count = 0
    by_system: dict[str, dict[str, Any]] = {}
    for host in _hosts():
        system_name = str(host.get("system_name") or "").strip()
        asset_name = str(host.get("asset_name") or "").strip()
        identity_name = _host_business_system_name(host)
        if not identity_name:
            continue
        display_name = identity_name
        sid = _system_id(identity_name)
        item = by_system.setdefault(
            sid,
            {
                "system_id": sid,
                "display_name": display_name,
                "tier": str(host.get("tier") or "C").upper()[:1] if host.get("tier") in {"A", "B", "C"} else "C",
                "category": "AP",
                "description": "由資產管理系統同步建立",
                "owner": host.get("ap_owner") or host.get("custodian") or "",
                "host_refs": [],
                "external": False,
                "metadata": {"asset_name": asset_name, "system_name": system_name, "sync_source": "host_inventory"},
                "updated_at": now,
                "updated_by": actor,
            },
        )
        if asset_name and not item["metadata"].get("asset_name"):
            item["metadata"]["asset_name"] = asset_name
        if system_name and not item["metadata"].get("system_name"):
            item["metadata"]["system_name"] = system_name
        if host.get("hostname") and host["hostname"] not in item["host_refs"]:
            item["host_refs"].append(host["hostname"])
    for item in by_system.values():
        existing = col.find_one({"system_id": item["system_id"]}, {"metadata": 1, "core_name": 1}) or {}
        existing_metadata = existing.get("metadata") or {}
        for core_field in ("core_name", "core"):
            if existing_metadata.get(core_field) and not item["metadata"].get(core_field):
                item["metadata"][core_field] = existing_metadata.get(core_field)
        if existing.get("core_name"):
            item["core_name"] = existing.get("core_name")
        result = col.update_one(
            {"system_id": item["system_id"]},
            {"$set": item, "$setOnInsert": {"created_at": now, "created_by": actor}},
            upsert=True,
        )
        count += int(bool(result.upserted_id or result.modified_count))
        if item["system_id"] != "SYS-UNKNOWN":
            col.delete_many({"system_id": "SYS-UNKNOWN", "display_name": item["display_name"]})
    col.delete_many(
        {
            "description": "由資產管理系統同步建立",
            "metadata.asset_name": "",
            "metadata.system_name": "",
            "host_refs.0": {"$exists": True},
        }
    )
    col.delete_many(
        {
            "$or": [
                {"display_name": {"$regex": r"^掃描發現"}},
                {"system_id": {"$regex": r"^SYS-[0-9]+-[0-9]+-[0-9]+-[0-9]+$"}},
                {"host_refs": {"$elemMatch": {"$regex": r"^scan-"}}},
            ],
        }
    )
    return count


def list_systems(filters: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    sync_systems_from_hosts()
    filters = filters or {}
    query: dict[str, Any] = {}
    if filters.get("tier"):
        query["tier"] = filters["tier"]
    if filters.get("category"):
        query["category"] = filters["category"]
    return [_public(item) or {} for item in get_collection("dependency_systems").find(query).sort("system_id", 1)]


def core_name_options(systems: Optional[list[dict[str, Any]]] = None) -> list[str]:
    systems = systems if systems is not None else list_systems()
    names = list(CORE_SYSTEM_NAMES)
    for system in systems:
        name = _core_name_for_system(system)
        if name and name not in names:
            names.append(name)
    if UNASSIGNED_CORE_NAME not in names:
        names.append(UNASSIGNED_CORE_NAME)
    return names


def core_assignment_rows(filters: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    filters = filters or {}
    systems = list_systems()
    query = str(filters.get("q") or "").strip().lower()
    core_filter = str(filters.get("core") or "").strip()
    grouped: dict[str, dict[str, Any]] = {}
    for system in systems:
        metadata = system.get("metadata") or {}
        core_name = _core_name_for_system(system)
        if core_filter and core_name != core_filter:
            continue
        searchable = " ".join(
            str(value or "")
            for value in [
                system.get("display_name"),
                system.get("system_id"),
                system.get("owner"),
                metadata.get("asset_name"),
                metadata.get("system_name"),
                " ".join(str(ref) for ref in system.get("host_refs") or []),
            ]
        ).lower()
        if query and query not in searchable:
            continue
        explicit = bool(metadata.get("core_name") or metadata.get("core") or system.get("core_name"))
        display_name = system.get("display_name") or system.get("system_id") or ""
        key = display_name.strip().lower() or str(system.get("system_id") or "")
        host_count = len(system.get("host_refs") or [])
        row = grouped.setdefault(
            key,
            {
                "system_id": system.get("system_id", ""),
                "system_ids": [],
                "display_name": display_name,
                "owner": "",
                "host_count": 0,
                "category": system.get("category") or "",
                "core_name": core_name,
                "explicit": False,
                "source_label": "系統推定",
                "duplicate_count": 0,
            },
        )
        sid = str(system.get("system_id") or "").strip()
        if sid and sid not in row["system_ids"]:
            row["system_ids"].append(sid)
        row["duplicate_count"] = len(row["system_ids"])
        row["host_count"] += host_count
        if system.get("owner") and not row["owner"]:
            row["owner"] = system.get("owner")
        if explicit:
            row["explicit"] = True
            row["source_label"] = "人工設定"
            row["core_name"] = core_name
        elif row["core_name"] == UNASSIGNED_CORE_NAME and core_name != UNASSIGNED_CORE_NAME:
            row["core_name"] = core_name
        if host_count > 0 and row["system_id"] != sid:
            row["system_id"] = sid
    options = core_name_options(systems)
    rows = list(grouped.values())
    return {
        "rows": sorted(rows, key=lambda row: (row["core_name"], row["display_name"])),
        "core_options": options,
        "summary": {
            "total": len(rows),
            "filtered": len(rows),
            "explicit": sum(1 for row in rows if row["explicit"]),
            "unassigned": sum(1 for row in rows if row["core_name"] == UNASSIGNED_CORE_NAME),
        },
        "filters": {"q": filters.get("q") or "", "core": core_filter},
    }


def update_core_assignments(assignments: dict[str, str], actor: str = "system") -> dict[str, int]:
    now = _now()
    col = get_collection("dependency_systems")
    updated = 0
    skipped = 0
    for system_id, core_name in assignments.items():
        sid = str(system_id or "").strip()
        core = str(core_name or "").strip()
        if not sid:
            skipped += 1
            continue
        if not core:
            result = col.update_one(
                {"system_id": sid},
                {"$unset": {"metadata.core_name": "", "metadata.core": "", "core_name": ""}, "$set": {"updated_at": now, "updated_by": actor}},
            )
        else:
            result = col.update_one(
                {"system_id": sid},
                {"$set": {"metadata.core_name": core, "updated_at": now, "updated_by": actor}},
            )
        updated += int(bool(result.modified_count))
        if not result.matched_count:
            skipped += 1
    return {"updated": updated, "skipped": skipped, "total": len(assignments)}


def upsert_system(data: dict[str, Any], actor: str = "system") -> dict[str, Any]:
    now = _now()
    system_id = data.get("system_id") or _system_id(data.get("display_name") or "")
    existing = get_collection("dependency_systems").find_one({"system_id": system_id}, {"metadata": 1}) or {}
    metadata = {**(existing.get("metadata") or {}), **(data.get("metadata") or {})}
    doc = {
        "system_id": system_id,
        "display_name": data.get("display_name") or system_id,
        "tier": data.get("tier") or "C",
        "category": data.get("category") or "AP",
        "description": data.get("description") or "",
        "owner": data.get("owner") or "",
        "host_refs": data.get("host_refs") or [],
        "external": bool(data.get("external")),
        "metadata": metadata,
        "updated_at": now,
        "updated_by": actor,
    }
    get_collection("dependency_systems").update_one(
        {"system_id": system_id},
        {"$set": doc, "$setOnInsert": {"created_at": now, "created_by": actor}},
        upsert=True,
    )
    return _public(get_collection("dependency_systems").find_one({"system_id": system_id})) or {}


def delete_system(system_id: str) -> bool:
    deleted = get_collection("dependency_systems").delete_one({"system_id": system_id}).deleted_count
    get_collection("dependency_relations").delete_many({"$or": [{"from_system": system_id}, {"to_system": system_id}]})
    return bool(deleted)


def list_relations(filters: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    filters = filters or {}
    query: dict[str, Any] = {}
    if filters.get("source"):
        query["source"] = filters["source"]
    if filters.get("system_id"):
        query["$or"] = [{"from_system": filters["system_id"]}, {"to_system": filters["system_id"]}]
    if filters.get("run_id"):
        query["evidence.run_id"] = filters["run_id"]
    items = [_public(item) or {} for item in get_collection("dependency_relations").find(query).sort("updated_at", -1)]
    q = str(filters.get("q") or filters.get("relation_q") or "").strip().lower()
    if not q:
        return _decorate_relation_labels(items)
    return _decorate_relation_labels([item for item in items if _relation_matches_query(item, q)])


def _decorate_relation_labels(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        return items
    system_ids = {str(item.get("from_system") or "") for item in items} | {str(item.get("to_system") or "") for item in items}
    system_ids.discard("")
    systems = {
        item.get("system_id"): item
        for item in get_collection("dependency_systems").find({"system_id": {"$in": sorted(system_ids)}})
    }
    for item in items:
        from_doc = systems.get(item.get("from_system")) or {}
        to_doc = systems.get(item.get("to_system")) or {}
        item["from_label"] = from_doc.get("display_name") or item.get("from_system") or "-"
        item["to_label"] = to_doc.get("display_name") or item.get("to_system") or "-"
    return items


def _relation_matches_query(item: dict[str, Any], q: str) -> bool:
    values: list[str] = []
    values.extend([str(item.get("from_system") or ""), str(item.get("to_system") or ""), str(item.get("rel_type") or ""), str(item.get("source") or ""), str(item.get("description") or "")])
    evidence = item.get("evidence") or {}
    metadata = item.get("metadata") or {}
    for source in (evidence, metadata):
        for value in source.values():
            if isinstance(value, list):
                values.extend(str(part) for part in value)
            else:
                values.append(str(value or ""))
    system_ids = [str(item.get("from_system") or ""), str(item.get("to_system") or "")]
    for system in get_collection("dependency_systems").find({"system_id": {"$in": system_ids}}):
        values.extend([str(system.get("display_name") or ""), str(system.get("owner") or ""), str(system.get("description") or "")])
        values.extend(str(part) for part in (system.get("host_refs") or []))
        values.extend(str(part or "") for part in (system.get("metadata") or {}).values())
    return q in " ".join(values).lower()


def upsert_relation(data: dict[str, Any], actor: str = "system") -> dict[str, Any]:
    now = _now()
    doc = {
        "from_system": data["from_system"],
        "to_system": data["to_system"],
        "rel_type": data.get("rel_type") or "depends_on",
        "source": data.get("source") or "manual",
        "confidence": float(data.get("confidence", 1.0)),
        "description": data.get("description") or "",
        "evidence": data.get("evidence") or {},
        "metadata": data.get("metadata") or {},
        "updated_at": now,
        "updated_by": actor,
    }
    get_collection("dependency_relations").update_one(
        {"from_system": doc["from_system"], "to_system": doc["to_system"]},
        {"$set": doc, "$setOnInsert": {"created_at": now, "created_by": actor}},
        upsert=True,
    )
    return _public(get_collection("dependency_relations").find_one({"from_system": doc["from_system"], "to_system": doc["to_system"]})) or {}


def update_relation_by_id(relation_id: str, data: dict[str, Any], actor: str = "system") -> dict[str, Any]:
    now = _now()
    existing = get_collection("dependency_relations").find_one({"_id": ObjectId(relation_id)})
    if not existing:
        raise KeyError("relation not found")
    evidence = dict(existing.get("evidence") or {})
    remote_port = str(data.get("remote_port") or "").strip()
    service_name = str(data.get("service_name") or "").strip()
    if remote_port:
        evidence["remote_ports"] = [remote_port]
        evidence["last_remote_port"] = remote_port
    else:
        evidence.pop("remote_ports", None)
        evidence.pop("last_remote_port", None)
    if service_name:
        evidence["service_name"] = service_name
        evidence["process_name"] = service_name
    else:
        evidence.pop("service_name", None)
        evidence.pop("process_name", None)
    doc = {
        "from_system": data.get("from_system") or existing.get("from_system"),
        "to_system": data.get("to_system") or existing.get("to_system"),
        "rel_type": data.get("rel_type") or existing.get("rel_type") or "depends_on",
        "source": data.get("source") or existing.get("source") or "manual",
        "confidence": float(data.get("confidence") or existing.get("confidence") or 1.0),
        "description": data.get("description") or "",
        "evidence": evidence,
        "metadata": {**(existing.get("metadata") or {}), "edited_from_ui": True},
        "updated_at": now,
        "updated_by": actor,
    }
    get_collection("dependency_relations").update_one({"_id": ObjectId(relation_id)}, {"$set": doc})
    return _public(get_collection("dependency_relations").find_one({"_id": ObjectId(relation_id)})) or {}


def delete_relation(relation_id: str) -> bool:
    return bool(get_collection("dependency_relations").delete_one({"_id": ObjectId(relation_id)}).deleted_count)


def latest_collect_run() -> Optional[dict[str, Any]]:
    mark_stale_collect_runs()
    return _public(get_collection("dependency_collect_runs").find_one({"status": "success"}, sort=[("finished_at", -1)]))


def mark_stale_collect_runs(max_age_min: int = 15) -> int:
    cutoff = _now() - timedelta(minutes=max_age_min)
    result = get_collection("dependency_collect_runs").update_many(
        {"status": "running", "started_at": {"$lt": cutoff}},
        {
            "$set": {
                "status": "failed",
                "finished_at": _now(),
                "edge_count": 0,
                "snapshot_replaced": False,
                "errors": [{"host": "*", "error": f"採集超過 {max_age_min} 分鐘未完成，已自動標記失敗。"}],
            }
        },
    )
    return int(result.modified_count)


def collect_topology(actor: str = "system", limit_hosts: int = 20) -> dict[str, Any]:
    mark_stale_collect_runs()
    previous_success = latest_collect_run()
    run_id = f"topo-{_now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
    started_at = _now()
    hosts = _hosts()[:limit_hosts]
    run_doc = {
        "run_id": run_id,
        "status": "running",
        "collector": "ss -tunp",
        "started_at": started_at,
        "started_by": actor,
        "host_count": len(hosts),
        "edge_count": 0,
        "errors": [],
    }
    get_collection("dependency_collect_runs").insert_one(run_doc)
    try:
        aggregate: dict[tuple[str, str], dict[str, Any]] = {}
        errors = []
        for host in hosts:
            hostname = host.get("hostname") or host.get("asset_seq") or host.get("ip")
            try:
                output = _run_ss_tunp(host)
                for edge in _parse_ss_tunp(host, output, run_id):
                    key = (edge["from_system"], edge["to_system"])
                    item = aggregate.setdefault(key, edge)
                    if item is not edge:
                        _merge_edge_evidence(item["evidence"], edge["evidence"])
            except Exception as exc:  # noqa: BLE001 - keep collection resilient per host
                errors.append({"host": hostname, "error": str(exc)[:300]})
        now = _now()
        should_replace_snapshot = not errors
        if errors and aggregate and not previous_success:
            should_replace_snapshot = True
        if should_replace_snapshot:
            get_collection("dependency_relations").delete_many({"source": "auto"})
            for edge in aggregate.values():
                edge["updated_at"] = now
                edge["updated_by"] = actor
                get_collection("dependency_relations").update_one(
                    {"from_system": edge["from_system"], "to_system": edge["to_system"]},
                    {"$set": edge, "$setOnInsert": {"created_at": now, "created_by": actor}},
                    upsert=True,
                )
            status = "success" if not errors else "partial"
        else:
            status = "partial" if aggregate else "failed"
        update = {"status": status, "finished_at": now, "edge_count": len(aggregate), "errors": errors, "snapshot_replaced": should_replace_snapshot}
        get_collection("dependency_collect_runs").update_one({"run_id": run_id}, {"$set": update})
        run_doc.update(update)
        return _public(run_doc) or run_doc
    except Exception as exc:  # noqa: BLE001 - never leave a run stuck in running
        update = {
            "status": "failed",
            "finished_at": _now(),
            "edge_count": 0,
            "errors": [{"host": "*", "error": str(exc)[:300]}],
            "snapshot_replaced": False,
        }
        get_collection("dependency_collect_runs").update_one({"run_id": run_id}, {"$set": update})
        run_doc.update(update)
        return _public(run_doc) or run_doc


def collect_runs(limit: int = 20) -> list[dict[str, Any]]:
    mark_stale_collect_runs()
    return [_public(item) or {} for item in get_collection("dependency_collect_runs").find({}).sort("started_at", -1).limit(limit)]


def latest_reconcile_report() -> Optional[dict[str, Any]]:
    return _public(get_collection("dependency_reconcile_reports").find_one({}, sort=[("started_at", -1)]))


def latest_network_scan_report() -> Optional[dict[str, Any]]:
    try:
        from webapp.services import cmdb_service

        return cmdb_service.latest_network_reconcile("")
    except Exception:  # noqa: BLE001 - topology page should still render if IPAM is unavailable
        return _public(get_collection("network_scan_reports").find_one({}, sort=[("started_at", -1)]))


def filtered_reconcile_report(include_external: bool = False, include_unmanaged: bool = False) -> Optional[dict[str, Any]]:
    report = latest_reconcile_report()
    if not report:
        return None
    known_ips = _known_host_ip_map()
    visible_rows = []
    hidden_unmanaged = 0
    hidden_external = 0
    for row in report.get("rows") or []:
        remote_ip = str(row.get("remote_ip") or "")
        is_known = remote_ip in known_ips
        is_internal = _is_internal_ip(remote_ip)
        if not is_known and is_internal and not include_unmanaged:
            hidden_unmanaged += 1
            continue
        if not is_known and not is_internal and not include_external:
            hidden_external += 1
            continue
        visible_rows.append(row)
    report = dict(report)
    report["rows"] = visible_rows
    report["visible_row_count"] = len(visible_rows)
    report["hidden_unmanaged_count"] = hidden_unmanaged
    report["hidden_external_count"] = hidden_external
    return report


def reconcile_ss_nmap(actor: str = "system", limit_hosts: int = 20) -> dict[str, Any]:
    started_at = _now()
    run_id = f"dep-reconcile-{started_at.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
    latest = latest_collect_run()
    relations = list_relations({"run_id": latest["run_id"]}) if latest else []
    hosts = _hosts()[:limit_hosts]
    known_ips = {str(ip) for host in hosts for ip in (host.get("ip_addresses") or ([host.get("ip")] if host.get("ip") else [])) if ip}

    ss_pairs: dict[tuple[str, str], dict[str, Any]] = {}
    scan_targets: dict[str, set[str]] = {ip: set(COMMON_EXPOSURE_PORTS) for ip in known_ips if _is_internal_ip(ip)}
    skipped_targets: set[str] = set()
    for rel in relations:
        evidence = rel.get("evidence") or {}
        remote_ip = str(evidence.get("last_remote_ip") or "").strip()
        remote_port = str(evidence.get("last_remote_port") or "").strip()
        if not remote_ip or not remote_port or remote_port == "*":
            continue
        ss_pairs[(remote_ip, remote_port)] = {
            "source": rel.get("from_system"),
            "target": rel.get("to_system"),
            "remote_ip": remote_ip,
            "port": remote_port,
            "process": evidence.get("process_name") or "",
            "last_seen": evidence.get("last_seen_at") or evidence.get("last_seen") or "",
        }
        if _is_internal_ip(remote_ip):
            scan_targets.setdefault(remote_ip, set(COMMON_EXPOSURE_PORTS)).add(remote_port)
        else:
            skipped_targets.add(remote_ip)

    nmap_pairs: dict[tuple[str, str], dict[str, Any]] = {}
    scan_errors = []
    if not shutil.which("nmap"):
        scan_errors.append({"target": "*", "error": "nmap 未安裝，無法執行 ss+nmap 聯通驗證。"})
    else:
        for ip, ports in sorted(scan_targets.items()):
            result = _run_nmap_port_scan(ip, sorted(ports, key=lambda value: int(value) if value.isdigit() else 99999))
            if result.get("error"):
                scan_errors.append({"target": ip, "error": result["error"]})
            for port in result.get("open_ports") or []:
                nmap_pairs[(ip, str(port))] = {"remote_ip": ip, "port": str(port), "service": _port_service_name(port) or ""}

    network_reports = []
    try:
        from webapp.services import cmdb_service

        for network in cmdb_service.list_networks()[:10]:
            cidr = network.get("cidr")
            if not cidr:
                continue
            network_reports.append(
                cmdb_service.run_asset_discovery_scan(
                    cidr,
                    user=actor,
                    environment=network.get("environment", ""),
                    dc=network.get("dc", ""),
                    scan_mode="combined",
                )
            )
    except Exception as exc:  # noqa: BLE001 - keep ss+nmap result even if IPAM scan fails
        scan_errors.append({"target": "IPAM", "error": f"網段掃描對帳失敗：{exc}"})

    rows = []
    for key in sorted(set(ss_pairs) | set(nmap_pairs), key=lambda item: (item[0], int(item[1]) if item[1].isdigit() else 99999)):
        ss_item = ss_pairs.get(key)
        nmap_item = nmap_pairs.get(key)
        if ss_item and nmap_item:
            status = "matched"
            status_label = "雙方一致"
            suggestion = "ss 看到實際連線，nmap 也能掃到該 Port。"
        elif ss_item and key[0] in skipped_targets:
            status = "external_skipped"
            status_label = "外網未掃描"
            suggestion = "外網目標預設不做 nmap 掃描，避免對外部位址造成不必要流量；可先確認是否要納入外部服務白名單。"
        elif ss_item:
            status = "ss_only"
            status_label = "ss 有、nmap 掃不到"
            suggestion = "可能只允許特定來源、防火牆限制，或 nmap 掃描來源無權連線。"
        else:
            status = "nmap_only"
            status_label = "nmap 有、ss 沒看到"
            suggestion = "外部可見服務目前沒有被 ss 快照捕捉到連線，請確認是否為必要暴露面。"
        base = ss_item or nmap_item or {}
        rows.append(
            {
                "status": status,
                "status_label": status_label,
                "source": base.get("source") or "",
                "target": base.get("target") or "",
                "remote_ip": base.get("remote_ip") or key[0],
                "port": base.get("port") or key[1],
                "service": _port_service_name(base.get("port") or key[1]) or nmap_item.get("service", "") if nmap_item else _port_service_name(base.get("port") or key[1]),
                "process": base.get("process") or "",
                "last_seen": base.get("last_seen") or "",
                "suggestion": suggestion,
            }
        )

    summary = {
        "matched": sum(1 for row in rows if row["status"] == "matched"),
        "ss_only": sum(1 for row in rows if row["status"] == "ss_only"),
        "nmap_only": sum(1 for row in rows if row["status"] == "nmap_only"),
        "external_skipped": sum(1 for row in rows if row["status"] == "external_skipped"),
        "network_discovered": sum(int(report.get("discovered_count") or 0) for report in network_reports),
        "network_cmdb": sum(int(report.get("cmdb_count") or 0) for report in network_reports),
        "network_mismatch": sum(int(report.get("mismatch_count") or 0) for report in network_reports),
        "network_count": len(network_reports),
    }
    report = {
        "run_id": run_id,
        "started_at": started_at,
        "started_at_local": _local_iso(started_at),
        "finished_at": _now(),
        "started_by": actor,
        "collector": "ss+nmap",
        "ss_run_id": latest.get("run_id") if latest else "",
        "target_count": len(scan_targets),
        "row_count": len(rows),
        "summary": summary,
        "rows": rows,
        "network_reports": network_reports,
        "errors": scan_errors,
    }
    report["finished_at_local"] = _local_iso(report["finished_at"])
    get_collection("dependency_reconcile_reports").insert_one(report)
    return _public(report) or report


def _run_nmap_port_scan(ip: str, ports: list[str]) -> dict[str, Any]:
    if not ports:
        return {"open_ports": [], "error": ""}
    try:
        completed = subprocess.run(
            ["nmap", "-Pn", "-sT", "-p", ",".join(ports[:80]), "-oX", "-", ip],
            check=False,
            capture_output=True,
            text=True,
            timeout=90,
        )
    except subprocess.TimeoutExpired:
        return {"open_ports": [], "error": "nmap port scan 逾時。"}
    if completed.returncode not in (0, 1):
        return {"open_ports": [], "error": completed.stderr.strip() or "nmap port scan 失敗。"}
    open_ports = []
    try:
        root = ET.fromstring(completed.stdout)
        for port in root.findall(".//port"):
            state = port.find("state")
            if state is not None and state.attrib.get("state") == "open":
                open_ports.append(port.attrib.get("portid", ""))
    except ET.ParseError as exc:
        return {"open_ports": [], "error": f"nmap XML 解析失敗：{exc}"}
    return {"open_ports": sorted({port for port in open_ports if port}, key=lambda value: int(value) if value.isdigit() else 99999), "error": ""}


def _run_ss_tunp(host: dict[str, Any]) -> str:
    hostname = host.get("hostname") or host.get("ip")
    local_probe_hosts = {
        item.strip()
        for item in os.environ.get("WEBITGPT_LOCAL_PROBE_HOSTS", "127.0.0.1,localhost").split(",")
        if item.strip()
    }
    if host.get("ip") in local_probe_hosts or hostname in local_probe_hosts:
        cmd = ["bash", "-lc", "ss -tunp || netstat -tunp"]
    else:
        ssh_user = host.get("ssh_user") or "sysinfra"
        ssh_port = str(host.get("ssh_port") or 22)
        target = host.get("ip") or hostname
        cmd = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=8",
            "-o",
            "StrictHostKeyChecking=no",
            "-p",
            ssh_port,
            f"{ssh_user}@{target}",
            "ss -tunp || netstat -tunp",
        ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or f"{hostname} ss failed").strip())
    return result.stdout


def _parse_ss_tunp(host: dict[str, Any], output: str, run_id: str) -> list[dict[str, Any]]:
    host_ips = _known_host_ip_map()
    caller = host.get("hostname") or host.get("asset_seq") or host.get("ip")
    caller_ip = host.get("ip") or ""
    now = _now()
    edges: list[dict[str, Any]] = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 6 or parts[0].lower() in {"netid", "proto"}:
            continue
        local = _parse_endpoint(parts[4])
        remote = _parse_endpoint(parts[5])
        if not local or not remote:
            continue
        remote_ip, remote_port = remote
        local_ip, local_port = local
        if _skip_remote(remote_ip, remote_port):
            continue
        target = host_ips.get(remote_ip, f"UNKNOWN-{remote_ip}")
        process_name = _parse_process(line)
        edges.append(
            {
                "from_system": caller,
                "to_system": target,
                "rel_type": "tcp/udp",
                "source": "auto",
                "confidence": 0.8,
                "description": "ss -tunp 採集",
                "evidence": {
                    "run_id": run_id,
                    "collector": "ss -tunp",
                    "caller_hostname": caller,
                    "caller_ip": caller_ip,
                    "last_local_ip": local_ip,
                    "last_local_port": local_port,
                    "last_remote_ip": remote_ip,
                    "last_remote_port": remote_port,
                    "remote_ports": [remote_port],
                    "local_ports": [local_port],
                    "process_name": process_name,
                    "processes": [process_name] if process_name else [],
                    "seen_count": 1,
                    "last_seen_at": now,
                },
                "metadata": {},
            }
        )
    return edges


def _parse_endpoint(value: str) -> Optional[tuple[str, str]]:
    value = value.strip()
    if value in {"*:*", "0.0.0.0:*", "[::]:*"}:
        return None
    if value.startswith("[") and "]:" in value:
        ip, port = value[1:].rsplit("]:", 1)
        return ip, port
    if ":" not in value:
        return None
    ip, port = value.rsplit(":", 1)
    return ip.strip("[]"), port


def _skip_remote(ip: str, port: str) -> bool:
    if not ip or port == "*":
        return True
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return addr.is_loopback or addr.is_unspecified


def _parse_process(line: str) -> str:
    match = re.search(r'users:\(\("([^"]+)"', line)
    return match.group(1) if match else ""


def _merge_edge_evidence(target: dict[str, Any], source: dict[str, Any]) -> None:
    target["seen_count"] = int(target.get("seen_count") or 0) + int(source.get("seen_count") or 1)
    for key in ("remote_ports", "local_ports", "processes"):
        values = list(target.get(key) or [])
        for item in source.get(key) or []:
            if item and item not in values:
                values.append(item)
        target[key] = values
    for key in ("last_local_ip", "last_local_port", "last_remote_ip", "last_remote_port", "process_name", "last_seen_at"):
        target[key] = source.get(key) or target.get(key)


def _node(system: dict[str, Any]) -> dict[str, Any]:
    tier = system.get("tier") or "C"
    return {
        "id": system["system_id"],
        "label": system.get("display_name") or system["system_id"],
        "kind": system.get("category") if system.get("category") in {"內網未納管", "外網未知"} else "系統",
        "tier": tier,
        "category": system.get("category") or "AP",
        "owner": system.get("owner") or "",
        "external": bool(system.get("external")),
    }


def _layout(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, int]:
    if not nodes:
        return {"width": 1100, "height": 520}

    by_id = {str(node["id"]): node for node in nodes}
    outgoing: dict[str, set[str]] = {str(node["id"]): set() for node in nodes}
    incoming: dict[str, set[str]] = {str(node["id"]): set() for node in nodes}
    neighbors: dict[str, set[str]] = {str(node["id"]): set() for node in nodes}
    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source in by_id and target in by_id:
            outgoing[source].add(target)
            incoming[target].add(source)
            neighbors[source].add(target)
            neighbors[target].add(source)

    remaining = set(by_id)
    components: list[list[str]] = []
    while remaining:
        starts = sorted(
            remaining,
            key=lambda item: (len(outgoing.get(item, set())) - len(incoming.get(item, set())), len(neighbors.get(item, set())), item),
            reverse=True,
        )
        start = starts[0]
        queue = [start]
        seen = {start}
        for current in queue:
            for nxt in sorted(neighbors.get(current, set())):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        components.append(queue)
        remaining -= seen

    canvas_width = 1100
    y_offset = 70
    for component in components:
        root = sorted(
            component,
            key=lambda item: (len(outgoing.get(item, set())) - len(incoming.get(item, set())), len(neighbors.get(item, set())), item),
            reverse=True,
        )[0]
        levels: dict[int, list[str]] = {0: [root]}
        visited = {root}
        queue = [(root, 0)]
        for current, level in queue:
            next_nodes = sorted(
                [item for item in neighbors.get(current, set()) if item not in visited],
                key=lambda item: (len(neighbors.get(item, set())), item),
                reverse=True,
            )
            for nxt in next_nodes:
                visited.add(nxt)
                levels.setdefault(level + 1, []).append(nxt)
                queue.append((nxt, level + 1))
        if len(visited) < len(component):
            levels.setdefault(1, []).extend(sorted(set(component) - visited))

        max_level = max(levels)
        max_rows = max(len(items) for items in levels.values())
        component_height = max(300, max_rows * 86)
        for level, items in levels.items():
            x = 120 + level * 230
            canvas_width = max(canvas_width, x + 170)
            if level == 0:
                positions = [y_offset + component_height / 2]
            else:
                gap = component_height / (len(items) + 1)
                positions = [y_offset + gap * (index + 1) for index in range(len(items))]
            for node_id, y in zip(items, positions):
                by_id[node_id]["x"] = round(x, 1)
                by_id[node_id]["y"] = round(y, 1)
        y_offset += component_height + 80

    by_id = {node["id"]: node for node in nodes}
    for edge in edges:
        source = by_id.get(edge.get("source"))
        target = by_id.get(edge.get("target"))
        if source and target:
            x1, y1, x2, y2 = source["x"], source["y"], target["x"], target["y"]
            dx = x2 - x1
            dy = y2 - y1
            length = max((dx * dx + dy * dy) ** 0.5, 1)
            label_offset = 18 if abs(dy) < 36 else 26
            label_x = (x1 + x2) / 2 - (dy / length) * label_offset
            label_y = (y1 + y2) / 2 + (dx / length) * label_offset
            edge.update({"x1": x1, "y1": y1, "x2": x2, "y2": y2, "label_x": round(label_x, 1), "label_y": round(label_y, 1)})
    return {"width": int(max(canvas_width, 1100)), "height": int(max(y_offset, 520))}


def _layout_radial(nodes: list[dict[str, Any]], edges: list[dict[str, Any]], center_id: str = "") -> dict[str, Any]:
    if not nodes:
        return {"width": 1100, "height": 620, "layout_mode": "system_radial"}
    width = 1280
    height = 720
    cx = width / 2
    cy = height / 2
    by_id = {str(node["id"]): node for node in nodes}
    degree: dict[str, int] = {str(node["id"]): 0 for node in nodes}
    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source in degree:
            degree[source] += 1
        if target in degree:
            degree[target] += 1
    if not center_id or center_id not in by_id:
        center_id = sorted(degree, key=lambda item: (degree[item], item), reverse=True)[0]
    center = by_id[center_id]
    center.update({"x": cx, "y": cy, "radial_role": "center"})
    direct_ids: set[str] = set()
    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source == center_id and target in by_id:
            direct_ids.add(target)
        if target == center_id and source in by_id:
            direct_ids.add(source)
    direct = sorted([by_id[item] for item in direct_ids], key=lambda node: str(node.get("label") or node.get("id")))
    ring_radius = 250
    if direct:
        for index, node in enumerate(direct):
            angle = -3.14159 / 2 + (2 * 3.14159 * index / len(direct))
            node.update({"x": round(cx + ring_radius * math.cos(angle), 1), "y": round(cy + ring_radius * math.sin(angle), 1), "radial_role": "direct"})
    other = [node for node in nodes if node["id"] != center_id and str(node["id"]) not in direct_ids]
    outer_radius = 330
    for index, node in enumerate(other):
        angle = -3.14159 / 2 + (2 * 3.14159 * index / max(1, len(other)))
        node.update({"x": round(cx + outer_radius * math.cos(angle), 1), "y": round(cy + outer_radius * math.sin(angle), 1), "radial_role": "other"})
    for edge in edges:
        source = by_id.get(edge.get("source"))
        target = by_id.get(edge.get("target"))
        if source and target:
            x1, y1, x2, y2 = source["x"], source["y"], target["x"], target["y"]
            edge.update({"x1": x1, "y1": y1, "x2": x2, "y2": y2, "label_x": round((x1 + x2) / 2, 1), "label_y": round((y1 + y2) / 2 - 18, 1)})
    return {"width": width, "height": height, "layout_mode": "system_radial", "radial_center": center_id, "direct_relations": len(direct_ids)}


def _layout_host_system_trunks(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    if not nodes:
        return {"width": 1100, "height": 520, "groups": []}

    system_groups: dict[str, list[dict[str, Any]]] = {}
    unknown_nodes: list[dict[str, Any]] = []
    for node in nodes:
        if node.get("kind") == "主機":
            system_name = str(node.get("system") or "未分類系統")
            system_groups.setdefault(system_name, []).append(node)
        else:
            unknown_nodes.append(node)

    groups: list[dict[str, Any]] = []
    y_offset = 80
    host_x = 280
    trunk_x = 120
    canvas_width = 1100
    for system_name, group_nodes in sorted(system_groups.items()):
        group_nodes.sort(key=lambda item: str(item.get("label") or item.get("id")))
        height = max(220, len(group_nodes) * 78)
        y1 = y_offset
        y2 = y_offset + height
        groups.append({"label": system_name, "x": trunk_x, "y1": y1, "y2": y2, "label_y": y1 + 22})
        gap = height / (len(group_nodes) + 1)
        for index, node in enumerate(group_nodes):
            node["x"] = host_x
            node["y"] = round(y1 + gap * (index + 1), 1)
            node["trunk_x"] = trunk_x
            node["trunk_y"] = node["y"]
        y_offset = y2 + 90

    unknown_x = 560
    for index, node in enumerate(sorted(unknown_nodes, key=lambda item: str(item.get("label") or item.get("id")))):
        node["x"] = unknown_x + (index // 14) * 220
        node["y"] = 90 + (index % 14) * 78
        canvas_width = max(canvas_width, node["x"] + 170)

    by_id = {node["id"]: node for node in nodes}
    for edge in edges:
        source = by_id.get(edge.get("source"))
        target = by_id.get(edge.get("target"))
        if source and target:
            x1, y1, x2, y2 = source["x"], source["y"], target["x"], target["y"]
            dx = x2 - x1
            dy = y2 - y1
            length = max((dx * dx + dy * dy) ** 0.5, 1)
            label_offset = 24
            edge.update(
                {
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "label_x": round((x1 + x2) / 2 - (dy / length) * label_offset, 1),
                    "label_y": round((y1 + y2) / 2 + (dx / length) * label_offset, 1),
                }
            )
    return {"width": int(max(canvas_width, 1100)), "height": int(max(y_offset, 520)), "groups": groups}


def _layout_layered_system_ip(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    if not nodes:
        return {"width": 1100, "height": 520, "layer_guides": []}
    layers = {
        1: [node for node in nodes if int(node.get("layer") or 1) == 1],
        2: [node for node in nodes if int(node.get("layer") or 1) == 2],
        3: [node for node in nodes if int(node.get("layer") or 1) == 3],
        4: [node for node in nodes if int(node.get("layer") or 1) >= 4],
    }
    labels = {1: "第一層：系統拓撲", 2: "第二層：IP 一跳", 3: "第三層：IP 二跳", 4: "第四層：IP 三跳 / 回接系統"}
    x_map = {1: 130, 2: 420, 3: 710, 4: 1000}
    max_rows = max(len(items) for items in layers.values()) if layers else 1
    height = max(520, max_rows * 86 + 140)
    guides = []
    for layer, items in layers.items():
        items.sort(key=lambda item: (str(item.get("system") or ""), str(item.get("label") or item.get("id"))))
        x = x_map[layer]
        guides.append({"label": labels[layer], "x": x, "y": 36})
        if not items:
            continue
        gap = (height - 110) / (len(items) + 1)
        for index, node in enumerate(items):
            node["x"] = x
            node["y"] = round(80 + gap * (index + 1), 1)

    by_id = {node["id"]: node for node in nodes}
    for edge in edges:
        source = by_id.get(edge.get("source"))
        target = by_id.get(edge.get("target"))
        if source and target:
            x1, y1, x2, y2 = source["x"], source["y"], target["x"], target["y"]
            dx = x2 - x1
            dy = y2 - y1
            length = max((dx * dx + dy * dy) ** 0.5, 1)
            label_offset = 24
            edge.update(
                {
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "label_x": round((x1 + x2) / 2 - (dy / length) * label_offset, 1),
                    "label_y": round((y1 + y2) / 2 + (dx / length) * label_offset, 1),
                }
            )
    return {"width": 1250, "height": int(height), "layer_guides": guides}


def _port_summary(evidence: dict[str, Any]) -> str:
    local_port = evidence.get("last_local_port") or evidence.get("local_port")
    remote_port = evidence.get("last_remote_port") or evidence.get("remote_port")
    ports = evidence.get("remote_ports") or evidence.get("ports") or []
    if local_port and remote_port:
        return f"{local_port} -> {remote_port}"
    if remote_port:
        return str(remote_port)
    if local_port:
        return str(local_port)
    if isinstance(ports, list) and ports:
        visible = [str(port) for port in ports[:3]]
        suffix = f" +{len(ports) - 3}" if len(ports) > 3 else ""
        return ", ".join(visible) + suffix
    return ""


def _port_service_name(*ports: Any) -> str:
    for port in ports:
        if not port:
            continue
        name = PORT_SERVICE_NAMES.get(str(port))
        if name:
            return name
    return ""


def _port_label(evidence: dict[str, Any]) -> str:
    summary = _port_summary(evidence)
    if not summary:
        return ""
    service = _port_service_name(evidence.get("last_remote_port"), evidence.get("last_local_port"))
    return f"{service} {summary}" if service else summary


def _edge_payload(rel: dict[str, Any], source_label: str, target_label: str) -> dict[str, Any]:
    evidence = rel.get("evidence") or {}
    port_summary = _port_summary(evidence)
    port_label = _port_label(evidence)
    process_name = evidence.get("process_name") or evidence.get("program") or ""
    seen_count = evidence.get("seen_count") or ""
    last_seen = evidence.get("last_seen_at") or evidence.get("last_seen") or ""
    rel_label = rel.get("rel_type") or rel.get("description") or rel.get("source") or ""
    detail_parts = [source_label, "->", target_label]
    if port_summary:
        detail_parts.append(f"port {port_summary}")
    if process_name:
        detail_parts.append(f"process {process_name}")
    if seen_count:
        detail_parts.append(f"seen {seen_count}")
    if last_seen:
        detail_parts.append(f"last {last_seen}")
    return {
        "source": rel.get("from_system"),
        "target": rel.get("to_system"),
        "source_label": source_label,
        "target_label": target_label,
        "label": rel_label,
        "caption": port_summary or rel_label,
        "detail_label": " / ".join(str(item) for item in detail_parts if item),
        "port_summary": port_summary,
        "port_label": port_label,
        "port_label_short": _short_port_label(port_label),
        "process_name": process_name,
        "seen_count": seen_count,
        "last_seen": last_seen,
        "trust": rel.get("source") or "manual",
        "evidence": evidence,
    }


def _merge_topology_relation(target: dict[str, Any], source: dict[str, Any]) -> None:
    target_evidence = target.setdefault("evidence", {})
    source_evidence = source.get("evidence") or {}
    ports = set(str(port) for port in (target_evidence.get("remote_ports") or []) if port)
    for key in ("last_remote_port", "remote_port", "last_local_port", "local_port"):
        if source_evidence.get(key):
            ports.add(str(source_evidence.get(key)))
    if ports:
        target_evidence["remote_ports"] = sorted(ports, key=lambda item: (len(item), item))
    for key in ("last_local_ip", "last_local_port", "last_remote_ip", "last_remote_port", "process_name", "last_seen_at"):
        target_evidence[key] = source_evidence.get(key) or target_evidence.get(key)
    target_evidence["seen_count"] = int(target_evidence.get("seen_count") or 0) + int(source_evidence.get("seen_count") or 1)
    if source.get("description") and not target.get("description"):
        target["description"] = source.get("description")


def _layer_edge(source: str, target: str, label: str, source_label: str, target_label: str, evidence: Optional[dict[str, Any]] = None, trust: str = "manual") -> dict[str, Any]:
    return _edge_payload(
        {
            "from_system": source,
            "to_system": target,
            "rel_type": label,
            "source": trust,
            "evidence": evidence or {},
        },
        source_label,
        target_label,
    )


def _short_port_label(port_label: str) -> str:
    if " -> " in port_label:
        return port_label.split(" -> ", 1)[0]
    return port_label


def _topology_meta(view: str) -> dict[str, Any]:
    latest = latest_collect_run()
    if not latest:
        return {
            "view": view,
            "collect_status": "never",
            "message": "尚未執行 ss -tunp 採集，拓撲只顯示節點，不顯示連線。",
        }
    collector = latest.get("collector")
    if collector == "system_relations_xlsx":
        message = "目前顯示 CMDB 系統關聯匯入資料，可再用 ss/nmap 驗證實際連線。"
    else:
        message = "目前顯示最後一次成功 ss -tunp 採集快照。"
    return {
        "view": view,
        "collect_status": latest.get("status"),
        "run_id": latest.get("run_id"),
        "collector": collector,
        "last_collect_at": _iso(latest.get("finished_at") or latest.get("started_at")),
        "edge_count": latest.get("edge_count", 0),
        "message": message,
    }


def topology(view: str = "system", center: str = "", depth: int = 2, limit: int = 200, include_external: bool = False, include_unmanaged: bool = False, failed_node: str = "", focus_impact: bool = False) -> dict[str, Any]:
    view = view if view in {"core_radial", "core_impact", "radial", "system", "host", "ip"} else "core_radial"
    if view == "host":
        data = _host_topology(limit, include_external=include_external, include_unmanaged=include_unmanaged)
    elif view == "ip":
        data = _ip_topology(limit, include_external=include_external, include_unmanaged=include_unmanaged)
    elif view == "core_radial":
        data = _core_radial_topology(center=center, depth=depth, limit=limit, include_external=include_external, include_unmanaged=include_unmanaged)
    elif view == "core_impact":
        data = _core_impact_topology(center=center, depth=depth, limit=limit, include_external=include_external, include_unmanaged=include_unmanaged)
    elif view == "radial":
        data = _system_radial_topology(center=center, limit=limit, include_external=include_external, include_unmanaged=include_unmanaged)
    else:
        data = _system_topology(center=center, depth=depth, limit=limit, include_external=include_external, include_unmanaged=include_unmanaged)
    _apply_failure_simulation(data, failed_node, max_depth=max(depth, 1))
    if focus_impact:
        _filter_to_failure_scope(data)
    data.setdefault("meta", {})["focus_impact"] = bool(focus_impact)
    return data


def _resolve_topology_node_id(nodes: list[dict[str, Any]], raw_value: str) -> str:
    value = (raw_value or "").strip()
    if not value:
        return ""
    node_ids = {str(node.get("id")) for node in nodes}
    if value in node_ids:
        return value
    if value.startswith("core:"):
        core_label = value.split(":", 1)[1].strip().lower()
        for node in nodes:
            if str(node.get("id", "")).startswith("core:") and str(node.get("label") or "").strip().lower() == core_label:
                return str(node.get("id"))
    lowered = value.lower()
    for node in nodes:
        candidates = [
            node.get("label"),
            node.get("id"),
            node.get("system_id"),
            node.get("hostname"),
            node.get("ip"),
        ]
        for candidate in candidates:
            if candidate and str(candidate).strip().lower() == lowered:
                return str(node.get("id"))
    for node in nodes:
        label = str(node.get("label") or "").lower()
        node_id = str(node.get("id") or "").lower()
        if lowered and (lowered in label or lowered in node_id):
            return str(node.get("id"))
    return value


def _apply_failure_simulation(data: dict[str, Any], failed_node: str = "", max_depth: int = 2) -> None:
    failed_node = (failed_node or "").strip()
    nodes = data.get("nodes") or []
    edges = data.get("edges") or []
    failed_node = _resolve_topology_node_id(nodes, failed_node)
    node_ids = {str(node.get("id")) for node in nodes}
    if not failed_node or failed_node not in node_ids:
        data.setdefault("meta", {})["simulation"] = {"enabled": False, "failed_node": failed_node}
        return

    downstream: set[str] = set()
    upstream: set[str] = set()
    downstream_layers: list[list[str]] = []
    upstream_layers: list[list[str]] = []
    current = {failed_node}
    for _ in range(max(max_depth, 1)):
        next_layer = {
            str(edge.get("target"))
            for edge in edges
            if str(edge.get("source")) in current and str(edge.get("target")) not in downstream and str(edge.get("target")) != failed_node
        }
        if not next_layer:
            break
        downstream.update(next_layer)
        downstream_layers.append(sorted(next_layer))
        current = next_layer
    current = {failed_node}
    for _ in range(max(max_depth, 1)):
        next_layer = {
            str(edge.get("source"))
            for edge in edges
            if str(edge.get("target")) in current and str(edge.get("source")) not in upstream and str(edge.get("source")) != failed_node
        }
        if not next_layer:
            break
        upstream.update(next_layer)
        upstream_layers.append(sorted(next_layer))
        current = next_layer

    for node in nodes:
        node_id = str(node.get("id"))
        if node_id == failed_node:
            node["simulation_status"] = "failed"
        elif node_id in downstream:
            node["simulation_status"] = "affected"
        elif node_id in upstream:
            node["simulation_status"] = "related"
        else:
            node["simulation_status"] = "normal"

    for edge in edges:
        source = str(edge.get("source"))
        target = str(edge.get("target"))
        if source == failed_node or source in downstream:
            edge["simulation_status"] = "affected"
        elif target == failed_node or source in upstream or target in upstream:
            edge["simulation_status"] = "related"
        else:
            edge["simulation_status"] = "normal"

    node_detail = next((node for node in nodes if str(node.get("id")) == failed_node), {})
    data.setdefault("meta", {})["simulation"] = {
        "enabled": True,
        "failed_node": failed_node,
        "node": node_detail,
        "affected_nodes": sorted(downstream),
        "related_nodes": sorted(upstream),
        "downstream_layers": downstream_layers,
        "upstream_layers": upstream_layers,
        "affected_count": len(downstream),
        "related_count": len(upstream),
        "direct_affected": downstream_layers[0] if downstream_layers else [],
        "second_hop_affected": downstream_layers[1] if len(downstream_layers) > 1 else [],
        "direct_related": upstream_layers[0] if upstream_layers else [],
        "second_hop_related": upstream_layers[1] if len(upstream_layers) > 1 else [],
        "edges": [
            {
                "source": edge.get("source_label") or edge.get("source"),
                "target": edge.get("target_label") or edge.get("target"),
                "port": edge.get("port_summary") or "-",
                "process": edge.get("process_name") or "-",
                "status": edge.get("simulation_status"),
            }
            for edge in edges
            if edge.get("simulation_status") in {"affected", "related"}
        ][:30],
    }


def _filter_to_failure_scope(data: dict[str, Any]) -> None:
    simulation = data.get("meta", {}).get("simulation") or {}
    if not simulation.get("enabled"):
        return
    keep = {simulation.get("failed_node")}
    keep.update(simulation.get("direct_affected") or [])
    keep.update(simulation.get("second_hop_affected") or [])
    keep.update(simulation.get("direct_related") or [])
    keep.update(simulation.get("second_hop_related") or [])
    keep = {str(item) for item in keep if item}
    data["nodes"] = [node for node in data.get("nodes", []) if str(node.get("id")) in keep]
    data["edges"] = [
        edge
        for edge in data.get("edges", [])
        if str(edge.get("source")) in keep and str(edge.get("target")) in keep and edge.get("simulation_status") in {"affected", "related"}
    ]
    if data.get("view") != "core_impact":
        data.setdefault("meta", {}).update(_layout(data["nodes"], data["edges"]))
    data.setdefault("meta", {})["focus_node_count"] = len(data["nodes"])
    data.setdefault("meta", {})["focus_edge_count"] = len(data["edges"])


def _system_topology(center: str = "", depth: int = 2, limit: int = 200, include_external: bool = False, include_unmanaged: bool = False) -> dict[str, Any]:
    systems = list_systems()
    system_map = {item["system_id"]: item for item in systems}
    host_to_system = _host_system_index()
    latest_auto = _public(get_collection("dependency_collect_runs").find_one({"status": "success", "collector": "ss -tunp"}, sort=[("finished_at", -1)]))
    latest_auto_run_id = latest_auto.get("run_id") if latest_auto else ""
    all_relations = list_relations()
    raw_relations: list[dict[str, Any]] = []
    relation_map: dict[tuple[str, str], dict[str, Any]] = {}
    for rel in all_relations:
        if rel.get("source") == "auto" and (rel.get("evidence") or {}).get("run_id") != latest_auto_run_id:
            continue
        raw_relations.append(rel)
        source_key = rel.get("from_system")
        target_key = rel.get("to_system")
        if source_key in system_map and target_key in system_map:
            source_system = str(source_key)
            target_system = str(target_key)
            key = (source_system, target_system)
            relation_map.setdefault(key, dict(rel))
            continue
        source_host = source_key
        source_system = host_to_system.get(source_host or "")
        if not source_system:
            continue
        evidence = rel.get("evidence") or {}
        target_host = target_key
        remote_ip = evidence.get("last_remote_ip") or str(target_host).replace("UNKNOWN-", "")
        target_system = host_to_system.get(target_host or "")
        if not target_system and str(target_host).startswith("UNKNOWN-"):
            if not include_unmanaged and _is_internal_ip(remote_ip):
                continue
            if not include_external and not _is_internal_ip(remote_ip):
                continue
            target_system = str(target_host)
            if target_system not in system_map:
                system_map[target_system] = {
                    "system_id": target_system,
                    "display_name": remote_ip or target_system,
                    "tier": "C",
                    "category": _unknown_node_kind(remote_ip),
                    "owner": "",
                    "external": not _is_internal_ip(remote_ip),
                }
                systems.append(system_map[target_system])
        if not target_system:
            continue
        key = (source_system, target_system)
        if key not in relation_map:
            doc = dict(rel)
            doc["from_system"] = source_system
            doc["to_system"] = target_system
            relation_map[key] = doc
        else:
            _merge_edge_evidence(relation_map[key].setdefault("evidence", {}), evidence)
    relations = list(relation_map.values())
    if center:
        keep = _reachable(center, relations, depth)
        systems = [item for item in systems if item["system_id"] in keep]
        relations = [item for item in relations if item.get("from_system") in keep and item.get("to_system") in keep]
    nodes = [_node(item) for item in systems[:limit]]
    node_ids = {node["id"] for node in nodes}
    edges = [
        _edge_payload(
            rel,
            system_map.get(rel.get("from_system"), {}).get("display_name", rel.get("from_system")),
            system_map.get(rel.get("to_system"), {}).get("display_name", rel.get("to_system")),
        )
        for rel in relations
        if rel.get("from_system") in node_ids and rel.get("to_system") in node_ids
    ]
    if depth >= 2:
        return _layered_system_ip_topology(systems[:limit], edges, raw_relations, system_map, center, depth, include_external, include_unmanaged)
    dimensions = _layout(nodes, edges)
    meta = _topology_meta("system")
    meta.update(dimensions)
    meta.update({"systems": len(nodes), "relations": len(edges), "center": center, "depth": depth, "include_external": include_external, "include_unmanaged": include_unmanaged, "layer_mode": "system_only"})
    return {"view": "system", "nodes": nodes, "edges": edges, "meta": meta}


def _match_system_id(query: str, systems: list[dict[str, Any]]) -> str:
    text = (query or "").strip().lower()
    if not text:
        return ""
    for item in systems:
        if str(item.get("system_id", "")).lower() == text:
            return str(item.get("system_id"))
    for item in systems:
        if text in str(item.get("display_name", "")).lower() or text in str(item.get("system_id", "")).lower():
            return str(item.get("system_id"))
    return ""


def _system_radial_topology(center: str = "", limit: int = 160, include_external: bool = False, include_unmanaged: bool = False) -> dict[str, Any]:
    systems = list_systems()
    system_map = {item["system_id"]: item for item in systems}
    relations = [
        rel
        for rel in list_relations()
        if rel.get("from_system") in system_map and rel.get("to_system") in system_map and (include_external or not system_map.get(rel.get("to_system"), {}).get("external"))
    ]
    if not include_unmanaged:
        systems = [item for item in systems if not str(item.get("system_id", "")).startswith("UNKNOWN-")]
    degree: dict[str, int] = {}
    for rel in relations:
        degree[str(rel.get("from_system"))] = degree.get(str(rel.get("from_system")), 0) + 1
        degree[str(rel.get("to_system"))] = degree.get(str(rel.get("to_system")), 0) + 1
    center_id = _match_system_id(center, systems)
    if not center_id and degree:
        center_id = sorted(degree, key=lambda item: (degree[item], item), reverse=True)[0]
    direct_ids = {center_id} if center_id else set()
    for rel in relations:
        if rel.get("from_system") == center_id:
            direct_ids.add(str(rel.get("to_system")))
        if rel.get("to_system") == center_id:
            direct_ids.add(str(rel.get("from_system")))
    if center_id and direct_ids:
        selected_systems = [item for item in systems if item["system_id"] in direct_ids]
        selected_relations = [rel for rel in relations if rel.get("from_system") in direct_ids and rel.get("to_system") in direct_ids]
    else:
        ranked = {item["system_id"] for item in sorted(systems, key=lambda item: degree.get(item["system_id"], 0), reverse=True)[:limit]}
        selected_systems = [item for item in systems if item["system_id"] in ranked]
        selected_relations = [rel for rel in relations if rel.get("from_system") in ranked and rel.get("to_system") in ranked]
    nodes = [_node(item) for item in selected_systems[:limit]]
    node_ids = {node["id"] for node in nodes}
    edges = [
        _edge_payload(rel, system_map.get(rel.get("from_system"), {}).get("display_name", rel.get("from_system")), system_map.get(rel.get("to_system"), {}).get("display_name", rel.get("to_system")))
        for rel in selected_relations
        if rel.get("from_system") in node_ids and rel.get("to_system") in node_ids
    ]
    dimensions = _layout_radial(nodes, edges, center_id=center_id)
    meta = _topology_meta("radial")
    meta.update(dimensions)
    meta.update(
        {
            "systems": len(nodes),
            "relations": len(edges),
            "center": center_id,
            "center_label": system_map.get(center_id, {}).get("display_name", center_id),
            "include_external": include_external,
            "include_unmanaged": include_unmanaged,
        }
    )
    return {"view": "radial", "nodes": nodes, "edges": edges, "meta": meta}


def _core_id(name: str) -> str:
    return "core:" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]


def _core_name_for_system(system: dict[str, Any]) -> str:
    metadata = system.get("metadata") or {}
    explicit = metadata.get("core_name") or metadata.get("core") or system.get("core_name")
    if explicit:
        return str(explicit)
    display = str(system.get("display_name") or system.get("system_id") or "")
    for name in CORE_SYSTEM_NAMES:
        if name in display:
            return name
    if any(token in display for token in ("巡檢", "受監控")):
        return "巡檢系統"
    return UNASSIGNED_CORE_NAME


def _core_node(name: str) -> dict[str, Any]:
    return {"id": _core_id(name), "label": name, "kind": "核心", "tier": "A", "category": "core", "owner": "", "external": False}


def _position_edge_labels(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
    by_id = {node["id"]: node for node in nodes}
    for edge in edges:
        source = by_id.get(edge.get("source"))
        target = by_id.get(edge.get("target"))
        if not source or not target:
            continue
        if "x" not in source or "y" not in source or "x" not in target or "y" not in target:
            continue
        x1, y1, x2, y2 = source["x"], source["y"], target["x"], target["y"]
        dx = x2 - x1
        dy = y2 - y1
        length = max((dx * dx + dy * dy) ** 0.5, 1)
        label_offset = 20
        edge.update(
            {
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "label_x": round((x1 + x2) / 2 - (dy / length) * label_offset, 1),
                "label_y": round((y1 + y2) / 2 + (dx / length) * label_offset, 1),
            }
        )


def _ensure_node_positions(nodes: list[dict[str, Any]], width: int, height: int) -> None:
    """Keep old or sparse topology data from breaking SVG rendering."""
    missing_nodes = [node for node in nodes if "x" not in node or "y" not in node]
    if not missing_nodes:
        return
    start_x = max(120, width - 180)
    gap = max(64, (height - 120) / (len(missing_nodes) + 1))
    for index, node in enumerate(missing_nodes):
        node["x"] = start_x
        node["y"] = round(70 + gap * (index + 1), 1)
        node.setdefault("radial_role", "other")


def _core_radial_topology(center: str = "", depth: int = 2, limit: int = 200, include_external: bool = False, include_unmanaged: bool = False) -> dict[str, Any]:
    systems = [item for item in list_systems() if include_unmanaged or not str(item.get("system_id", "")).startswith("UNKNOWN-")]
    system_map = {item["system_id"]: item for item in systems}
    relations = [
        rel
        for rel in list_relations()
        if rel.get("from_system") in system_map and rel.get("to_system") in system_map and (include_external or not system_map.get(rel.get("to_system"), {}).get("external"))
    ]
    core_names = list(CORE_SYSTEM_NAMES)
    core_by_system = {item["system_id"]: _core_name_for_system(item) for item in systems}
    for name in sorted(set(core_by_system.values())):
        if name not in core_names:
            core_names.append(name)
    center_system_id = _match_system_id(center, systems)
    selected_core = core_by_system.get(center_system_id, "")
    if not selected_core and str(center).startswith("core:"):
        selected_core = next((name for name in core_names if _core_id(name) == center), "")
    if not selected_core and center:
        center_text = str(center).strip().lower()
        selected_core = next((name for name in core_names if center_text in str(name).lower() or str(name).lower() in center_text), "")

    width = 1280
    height = 760
    cx = width / 2
    cy = height / 2
    core_radius = 205
    nodes = [_core_node(name) for name in core_names[:8]]
    core_ids = {node["label"]: node["id"] for node in nodes}
    for index, node in enumerate(nodes):
        angle = -math.pi / 2 + 2 * math.pi * index / max(1, len(nodes))
        node.update({"x": round(cx + core_radius * math.cos(angle), 1), "y": round(cy + core_radius * math.sin(angle), 1), "radial_role": "direct"})

    selected_systems = systems[: max(0, limit - len(nodes))]
    for index, system in enumerate(selected_systems):
        core_name = core_by_system.get(system["system_id"], CORE_SYSTEM_NAMES[0])
        core_index = max(0, core_names.index(core_name) if core_name in core_names else 0)
        base_angle = -math.pi / 2 + 2 * math.pi * core_index / max(1, len(nodes))
        sibling_index = sum(1 for prev in selected_systems[:index] if core_by_system.get(prev["system_id"]) == core_name)
        angle = base_angle + (sibling_index - 1.5) * 0.13
        radius = 335 + (sibling_index % 3) * 42
        node = _node(system)
        node.update({"x": round(cx + radius * math.cos(angle), 1), "y": round(cy + radius * math.sin(angle), 1), "radial_role": "other", "core_name": core_name})
        nodes.append(node)

    node_ids = {node["id"] for node in nodes}
    edges: list[dict[str, Any]] = []
    for system in selected_systems:
        core_name = core_by_system.get(system["system_id"], CORE_SYSTEM_NAMES[0])
        core_id = core_ids.get(core_name)
        if core_id:
            edges.append(_layer_edge(core_id, system["system_id"], "核心關聯", core_name, system.get("display_name") or system["system_id"], trust="manual"))
    for rel in relations:
        if rel.get("from_system") in node_ids and rel.get("to_system") in node_ids:
            edges.append(
                _edge_payload(
                    rel,
                    system_map.get(rel.get("from_system"), {}).get("display_name", rel.get("from_system")),
                    system_map.get(rel.get("to_system"), {}).get("display_name", rel.get("to_system")),
                )
            )
    active_ids: set[str] = set()
    if center_system_id:
        active_ids.add(center_system_id)
        active_ids.add(_core_id(core_by_system.get(center_system_id, CORE_SYSTEM_NAMES[0])))
        for rel in relations:
            if rel.get("from_system") == center_system_id:
                active_ids.add(str(rel.get("to_system")))
                active_ids.add(_core_id(core_by_system.get(str(rel.get("to_system")), CORE_SYSTEM_NAMES[0])))
            if rel.get("to_system") == center_system_id:
                active_ids.add(str(rel.get("from_system")))
                active_ids.add(_core_id(core_by_system.get(str(rel.get("from_system")), CORE_SYSTEM_NAMES[0])))
    elif selected_core:
        active_ids.add(_core_id(selected_core))
        active_ids.update(item["system_id"] for item in selected_systems if core_by_system.get(item["system_id"]) == selected_core)
    if active_ids:
        for node in nodes:
            node["focus_state"] = "active" if node["id"] in active_ids else "muted"
        for edge in edges:
            edge["focus_state"] = "active" if edge.get("source") in active_ids and edge.get("target") in active_ids else "muted"
    else:
        for node in nodes:
            node["focus_state"] = "normal"
        for edge in edges:
            edge["focus_state"] = "normal"
    _ensure_node_positions(nodes, width, height)
    _position_edge_labels(nodes, edges)
    meta = _topology_meta("core_radial")
    meta.update({"width": width, "height": height, "layout_mode": "core_radial", "systems": len(selected_systems), "relations": len(edges), "center": center, "include_external": include_external, "include_unmanaged": include_unmanaged, "message": "CMDB 畫正式核心關聯；ss+nmap 用於補漏與驗證，覆核後才進正式圖。"})
    return {"view": "core_radial", "nodes": nodes, "edges": edges, "meta": meta}


def _core_impact_topology(center: str = "", depth: int = 2, limit: int = 200, include_external: bool = False, include_unmanaged: bool = False) -> dict[str, Any]:
    systems = [item for item in list_systems() if include_unmanaged or not str(item.get("system_id", "")).startswith("UNKNOWN-")]
    system_map = {item["system_id"]: item for item in systems}
    core_by_system = {item["system_id"]: _core_name_for_system(item) for item in systems}
    center_system_id = _match_system_id(center, systems)
    selected_core = core_by_system.get(center_system_id) if center_system_id else ""
    if not selected_core and str(center).startswith("core:"):
        selected_core = next((name for name in list(CORE_SYSTEM_NAMES) + [UNASSIGNED_CORE_NAME] if _core_id(name) == center), "")
    if not selected_core:
        selected_core = "巡檢系統" if any(_core_name_for_system(item) == "巡檢系統" for item in systems) else UNASSIGNED_CORE_NAME
    core_names = list(CORE_SYSTEM_NAMES)
    for name in sorted(set(core_by_system.values())):
        if name not in core_names:
            core_names.append(name)
    core_nodes = [_core_node(name) for name in core_names]
    related_systems = [item for item in systems if core_by_system.get(item["system_id"]) == selected_core]
    scope = "core"
    if center_system_id:
        relations_all = list_relations({"system_id": center_system_id})
        linked_ids = {center_system_id}
        for rel in relations_all:
            if rel.get("from_system"):
                linked_ids.add(str(rel.get("from_system")))
            if rel.get("to_system"):
                linked_ids.add(str(rel.get("to_system")))
        related_systems = [item for item in systems if item["system_id"] in linked_ids]
        scope = "system_focus"
    related_systems = related_systems[: max(1, min(limit, 12))]
    selected_ids = {item["system_id"] for item in related_systems}

    hosts = _hosts()
    host_nodes = []
    for system in related_systems:
        seen_host_keys: set[str] = set()
        for host_ref in system.get("host_refs") or []:
            host = next((item for item in hosts if item.get("hostname") == host_ref or item.get("asset_seq") == host_ref), None)
            if not host:
                continue
            host_key = _host_node_key(host)
            if not host_key or host_key in seen_host_keys:
                continue
            seen_host_keys.add(host_key)
            node_id = "host:" + host_key
            host_nodes.append(
                {
                    "id": node_id,
                    "label": host.get("ip") or host.get("hostname") or host.get("asset_seq"),
                    "kind": "主機",
                    "system_id": system["system_id"],
                    "hostname": host.get("hostname") or "",
                    "ip": host.get("ip") or "",
                    "category": "host",
                    "tier": system.get("tier") or "C",
                }
            )
        for host in hosts:
            if not _host_matches_dependency_system(host, system):
                continue
            host_key = _host_node_key(host)
            if not host_key or host_key in seen_host_keys:
                continue
            seen_host_keys.add(host_key)
            node_id = "host:" + host_key
            host_nodes.append(
                {
                    "id": node_id,
                    "label": host.get("ip") or host.get("hostname") or host.get("asset_seq"),
                    "kind": "主機",
                    "system_id": system["system_id"],
                    "hostname": host.get("hostname") or "",
                    "ip": host.get("ip") or "",
                    "category": "host",
                    "tier": system.get("tier") or "C",
                }
            )
    host_nodes = host_nodes[:18]

    nodes: list[dict[str, Any]] = []
    nodes.extend(core_nodes)
    nodes.extend([_node(item) for item in related_systems])
    nodes.extend(host_nodes)
    for node in nodes:
        if str(node.get("id", "")).startswith("core:"):
            node["role_label"] = "核心"
        elif str(node.get("id", "")).startswith("host:"):
            node["role_label"] = "主機 / IP"
        else:
            node["role_label"] = "關聯系統"
        node["shape"] = "card"
    related_host_ids = {node["id"] for node in host_nodes}
    selected_core_id = _core_id(selected_core)
    active_ids = {selected_core_id} | selected_ids | related_host_ids
    for node in nodes:
        node["focus_state"] = "active" if node["id"] in active_ids else "muted"

    height = max(720, max(len(core_nodes), len(related_systems), len(host_nodes), 1) * 92 + 130)
    lanes = [
        {"key": "core", "label": "第一欄：核心歸屬", "x": 30, "y": 64, "width": 280, "height": int(height - 96)},
        {"key": "system", "label": "第二欄：關聯系統", "x": 410, "y": 64, "width": 290, "height": int(height - 96)},
        {"key": "host", "label": "第三欄：主機 / IP", "x": 810, "y": 64, "width": 310, "height": int(height - 96)},
    ]
    guides = [
        {"label": lane["label"], "x": lane["x"] + lane["width"] / 2, "y": 36}
        for lane in lanes
    ]
    columns = [("core", 170, core_nodes), ("system", 555, [node for node in nodes if node["id"] in selected_ids]), ("host", 965, host_nodes)]
    by_id = {node["id"]: node for node in nodes}
    for _, x, items in columns:
        gap = (height - 120) / (len(items) + 1) if items else 1
        for index, node in enumerate(items):
            target = by_id.get(node["id"])
            if target:
                target.update({"x": x, "y": round(70 + gap * (index + 1), 1), "radial_role": "direct" if x == 170 else "other"})

    relations = [
        rel
        for rel in list_relations()
        if rel.get("from_system") in system_map and rel.get("to_system") in system_map and rel.get("from_system") in selected_ids and rel.get("to_system") in selected_ids and (include_external or not system_map.get(rel.get("to_system"), {}).get("external"))
    ]
    trust_summary: dict[str, int] = {"manual": 0, "auto": 0, "unknown": 0}
    edges: list[dict[str, Any]] = []
    for system in related_systems:
        edges.append(_layer_edge(selected_core_id, system["system_id"], "核心關聯", selected_core, system.get("display_name") or system["system_id"], trust="manual"))
    host_by_node = {node["id"]: node for node in host_nodes}
    for host_node in host_nodes:
        system = system_map.get(host_node.get("system_id"))
        if system:
            edges.append(_layer_edge(system["system_id"], host_node["id"], "主機/IP", system.get("display_name") or system["system_id"], host_node["label"], trust="manual"))
    for rel in relations:
        edges.append(_edge_payload(rel, system_map.get(rel.get("from_system"), {}).get("display_name", rel.get("from_system")), system_map.get(rel.get("to_system"), {}).get("display_name", rel.get("to_system"))))
    for edge in edges:
        trust = str(edge.get("trust") or edge.get("source") or "unknown").lower()
        trust_summary[trust if trust in trust_summary else "unknown"] += 1
        edge["focus_state"] = "active" if edge.get("source") in active_ids and edge.get("target") in active_ids else "muted"
    _ensure_node_positions(nodes, 1220, int(height))
    _position_edge_labels(nodes, edges)
    focus_system = system_map.get(center_system_id or "")
    focus_label = (focus_system or {}).get("display_name") or selected_core
    affected_items = []
    for system in related_systems:
        if system.get("system_id") == center_system_id:
            continue
        affected_items.append(
            {
                "name": system.get("display_name") or system.get("system_id"),
                "note": system.get("description") or "需依 CMDB 關聯與主機狀態確認影響。",
            }
        )
    if not affected_items and related_systems:
        affected_items = [
            {
                "name": related_systems[0].get("display_name") or related_systems[0].get("system_id"),
                "note": "目前焦點系統底下的主機與通知口徑。",
            }
        ]
    host_count_by_system: dict[str, int] = {}
    for host_node in host_nodes:
        system_id = str(host_node.get("system_id") or "")
        host_count_by_system[system_id] = host_count_by_system.get(system_id, 0) + 1
    notification_contacts = []
    for system in related_systems:
        owner = (system.get("owner") or "").strip()
        notification_contacts.append(
            {
                "core": selected_core,
                "system_id": system.get("system_id"),
                "system_name": system.get("display_name") or system.get("system_id"),
                "owner": owner or "未指定",
                "host_count": host_count_by_system.get(str(system.get("system_id")), 0),
                "reason": "核心系統維護 / 故障影響通知",
                "status": "需要補聯絡人" if not owner else "可通知",
            }
        )
    meta = _topology_meta("core_impact")
    meta.update({"width": 1120, "height": int(height), "layout_mode": "core_impact", "systems": len(related_systems), "relations": len(edges), "center": center_system_id or selected_core, "center_label": selected_core, "include_external": include_external, "include_unmanaged": include_unmanaged, "layer_guides": guides, "message": "處理角度：先看核心，再看關聯系統，最後展開主機 / IP 與通知對象。"})
    meta.update(
        {
            "width": 1220,
            "message": "核心影響圖：選核心時顯示整個核心，選系統時只顯示焦點系統、直接關聯與主機 / IP。",
            "scope": scope,
            "layer_lanes": lanes,
            "impact_panel": {
                "focus_label": focus_label,
                "core_label": selected_core,
                "scope_label": "焦點系統" if scope == "system_focus" else "核心總覽",
                "system_count": len(related_systems),
                "host_count": len(host_nodes),
                "relation_count": len(edges),
                "loop_count": sum(1 for rel in relations if rel.get("from_system") == rel.get("to_system")),
                "notification_count": len({(item.get("owner") or "").strip() for item in related_systems if (item.get("owner") or "").strip()}),
                "affected_items": affected_items[:6],
                "notification_contacts": notification_contacts,
                "trust_summary": trust_summary,
                "trust_note": "manual=人工/CMDB，auto=自動採集，unknown=來源不足；通知或變更前請優先確認 unknown。",
            },
        }
    )
    return {"view": "core_impact", "nodes": nodes, "edges": edges, "meta": meta}


def _layered_system_ip_topology(
    systems: list[dict[str, Any]],
    system_edges: list[dict[str, Any]],
    raw_relations: list[dict[str, Any]],
    system_map: dict[str, dict[str, Any]],
    center: str,
    depth: int,
    include_external: bool,
    include_unmanaged: bool,
) -> dict[str, Any]:
    hosts = _hosts()
    host_to_system = _host_system_index()
    host_by_name = {host.get("hostname"): host for host in hosts if host.get("hostname")}
    known_ips = _known_host_ip_map()
    selected_systems = {item["system_id"] for item in systems}
    nodes_by_id: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def add_node(node: dict[str, Any]) -> None:
        nodes_by_id.setdefault(str(node["id"]), node)

    def ip_node_id(ip: str) -> str:
        return f"ip:{ip}"

    for system in systems:
        add_node(
            {
                "id": system["system_id"],
                "label": system.get("display_name") or system["system_id"],
                "kind": system.get("category") if system.get("category") in {"內網未納管", "外網未知"} else "系統",
                "tier": system.get("tier") or "C",
                "category": system.get("category") or "AP",
                "external": bool(system.get("external")),
                "layer": 1,
            }
        )

    for edge in system_edges:
        if edge.get("source") in nodes_by_id and edge.get("target") in nodes_by_id:
            layer_edge = dict(edge)
            layer_edge["label"] = "系統關聯"
            edges.append(layer_edge)

    first_hop_ip_ids: set[str] = set()
    known_system_ip_ids: set[str] = set()
    for host in hosts:
        hostname = host.get("hostname")
        system_id = host_to_system.get(hostname or "")
        if not hostname or system_id not in selected_systems:
            continue
        system_label = system_map.get(system_id, {}).get("display_name") or system_id
        for ip in host.get("ip_addresses") or ([host.get("ip")] if host.get("ip") else []):
            if not ip:
                continue
            node_id = ip_node_id(str(ip))
            known_system_ip_ids.add(node_id)
            first_hop_ip_ids.add(node_id)
            add_node({"id": node_id, "label": str(ip), "kind": "IP", "hostname": hostname, "os": host.get("os"), "system": system_label, "layer": 2})
            edges.append(_layer_edge(system_id, node_id, "系統內 IP", system_label, str(ip), trust="manual"))

    def add_ip(ip: str, layer: int, source_host: str = "") -> str:
        node_id = ip_node_id(str(ip))
        if node_id not in nodes_by_id:
            add_node(
                {
                    "id": node_id,
                    "label": str(ip),
                    "kind": "IP" if known_ips.get(str(ip)) else _unknown_ip_kind(str(ip)),
                    "hostname": known_ips.get(str(ip)) or source_host,
                    "system": "",
                    "layer": layer,
                }
            )
        else:
            nodes_by_id[node_id]["layer"] = min(int(nodes_by_id[node_id].get("layer") or layer), layer)
        return node_id

    for rel in raw_relations:
        evidence = rel.get("evidence") or {}
        source_host = rel.get("from_system")
        source_system = host_to_system.get(source_host or "")
        target_host = rel.get("to_system")
        target_system = host_to_system.get(target_host or "")
        source_doc = host_by_name.get(source_host or "", {})
        source_ip = evidence.get("caller_ip") or evidence.get("last_local_ip") or source_doc.get("ip")
        target_ip = evidence.get("last_remote_ip") or str(target_host).replace("UNKNOWN-", "")
        if not source_ip or not target_ip:
            continue
        if source_system not in selected_systems:
            continue
        if not include_unmanaged and not target_system and _is_internal_ip(str(target_ip)):
            continue
        if not include_external and not _is_internal_ip(str(target_ip)) and not target_system:
            continue
        source_node = add_ip(str(source_ip), 2, str(source_host or ""))
        target_node = add_ip(str(target_ip), 2, str(target_host or ""))
        first_hop_ip_ids.update({source_node, target_node})
        edges.append(_layer_edge(source_node, target_node, "IP 一跳", str(source_ip), str(target_ip), evidence=evidence, trust=rel.get("source") or "auto"))

    second_hop_ip_ids: set[str] = set()
    if depth >= 3:
        seed_ips = {node_id.replace("ip:", "") for node_id in first_hop_ip_ids}
        for rel in raw_relations:
            evidence = rel.get("evidence") or {}
            source_host = rel.get("from_system")
            source_doc = host_by_name.get(source_host or "", {})
            source_ip = str(evidence.get("caller_ip") or evidence.get("last_local_ip") or source_doc.get("ip") or "")
            target_ip = str(evidence.get("last_remote_ip") or str(rel.get("to_system")).replace("UNKNOWN-", "") or "")
            if not source_ip or not target_ip:
                continue
            if source_ip not in seed_ips and target_ip not in seed_ips:
                continue
            if not include_unmanaged and target_ip not in known_ips and _is_internal_ip(target_ip):
                continue
            if not include_external and not _is_internal_ip(target_ip) and target_ip not in known_ips:
                continue
            source_layer = 2 if source_ip in seed_ips else 3
            target_layer = 2 if target_ip in seed_ips else 3
            source_node = add_ip(source_ip, source_layer, str(source_host or ""))
            target_node = add_ip(target_ip, target_layer, str(rel.get("to_system") or ""))
            if target_node not in known_system_ip_ids or source_node not in known_system_ip_ids:
                edges.append(_layer_edge(source_node, target_node, "IP 二跳", source_ip, target_ip, evidence=evidence, trust=rel.get("source") or "auto"))
                if source_layer == 3:
                    second_hop_ip_ids.add(source_node)
                if target_layer == 3:
                    second_hop_ip_ids.add(target_node)

    if depth >= 4:
        seed_ips = {node_id.replace("ip:", "") for node_id in second_hop_ip_ids}
        for rel in raw_relations:
            evidence = rel.get("evidence") or {}
            source_host = rel.get("from_system")
            source_doc = host_by_name.get(source_host or "", {})
            source_ip = str(evidence.get("caller_ip") or evidence.get("last_local_ip") or source_doc.get("ip") or "")
            target_ip = str(evidence.get("last_remote_ip") or str(rel.get("to_system")).replace("UNKNOWN-", "") or "")
            if not source_ip or not target_ip:
                continue
            if source_ip not in seed_ips and target_ip not in seed_ips:
                continue
            if not include_unmanaged and target_ip not in known_ips and _is_internal_ip(target_ip):
                continue
            if not include_external and not _is_internal_ip(target_ip) and target_ip not in known_ips:
                continue
            source_layer = 3 if source_ip in seed_ips else 4
            target_layer = 3 if target_ip in seed_ips else 4
            source_node = add_ip(source_ip, source_layer, str(source_host or ""))
            target_node = add_ip(target_ip, target_layer, str(rel.get("to_system") or ""))
            edges.append(_layer_edge(source_node, target_node, "IP 三跳", source_ip, target_ip, evidence=evidence, trust=rel.get("source") or "auto"))

            source_system = host_to_system.get(source_host or "")
            target_host = rel.get("to_system")
            target_system = host_to_system.get(target_host or "")
            if source_layer == 4 and source_system in selected_systems:
                system_label = system_map.get(source_system, {}).get("display_name") or source_system
                edges.append(_layer_edge(source_node, source_system, "三跳回接系統", source_ip, system_label, evidence=evidence, trust="auto"))
            if target_layer == 4 and target_system in selected_systems:
                system_label = system_map.get(target_system, {}).get("display_name") or target_system
                edges.append(_layer_edge(target_node, target_system, "三跳回接系統", target_ip, system_label, evidence=evidence, trust="auto"))

    nodes = list(nodes_by_id.values())
    dimensions = _layout_layered_system_ip(nodes, edges)
    meta = _topology_meta("system")
    meta.update(dimensions)
    meta.update(
        {
            "systems": len([node for node in nodes if node.get("layer") == 1]),
            "ips": len([node for node in nodes if node.get("kind") in {"IP", "內網未納管IP", "外網 IP"}]),
            "relations": len(edges),
            "center": center,
            "depth": depth,
            "include_external": include_external,
            "include_unmanaged": include_unmanaged,
            "layer_mode": "system_ip_layers",
            "max_hop": 3 if depth >= 4 else 2 if depth >= 3 else 1 if depth >= 2 else 0,
        }
    )
    return {"view": "system", "nodes": nodes, "edges": edges, "meta": meta}


def _host_topology(limit: int = 200, include_external: bool = False, include_unmanaged: bool = False) -> dict[str, Any]:
    hosts = _hosts()[:limit]
    host_map = {host.get("hostname"): host for host in hosts if host.get("hostname")}
    ip_map = _known_host_ip_map()
    nodes = [{"id": host.get("hostname"), "label": host.get("hostname"), "kind": "主機", "ip": host.get("ip"), "os": host.get("os"), "system": host.get("system_name") or ""} for host in hosts if host.get("hostname")]
    node_ids = {node["id"] for node in nodes}
    edge_relations: dict[tuple[str, str], dict[str, Any]] = {}
    latest = latest_collect_run()
    relations = list_relations({"run_id": latest["run_id"]}) if latest else []
    for rel in relations:
        source = rel.get("from_system")
        target = rel.get("to_system")
        evidence = rel.get("evidence") or {}
        remote_ip = evidence.get("last_remote_ip") or str(target).replace("UNKNOWN-", "")
        if str(target).startswith("UNKNOWN-") and not include_unmanaged and _is_internal_ip(remote_ip):
            continue
        if str(target).startswith("UNKNOWN-") and not include_external and not _is_internal_ip(remote_ip):
            continue
        if target not in node_ids:
            label = ip_map.get(remote_ip) or remote_ip or target
            kind = _unknown_node_kind(remote_ip) if str(target).startswith("UNKNOWN-") else "主機"
            nodes.append({"id": target, "label": label, "kind": kind, "ip": remote_ip, "os": ""})
            node_ids.add(target)
        key = (str(source), str(target))
        if key not in edge_relations:
            edge_relations[key] = dict(rel)
            edge_relations[key]["evidence"] = dict(evidence)
        else:
            _merge_topology_relation(edge_relations[key], rel)
    edges = []
    for rel in edge_relations.values():
        source = rel.get("from_system")
        target = rel.get("to_system")
        evidence = rel.get("evidence") or {}
        source_label = host_map.get(source, {}).get("hostname") or source
        target_label = host_map.get(target, {}).get("hostname") or evidence.get("last_remote_ip") or target
        edges.append(_edge_payload(rel, source_label, target_label))
    if include_unmanaged or include_external:
        known_node_ips = {str(node.get("ip") or node.get("label") or "") for node in nodes}
        scan_report = latest_network_scan_report() or {}
        for row in scan_report.get("rows") or []:
            if row.get("type") != "scan_not_in_cmdb":
                continue
            ip_text = str(row.get("ip") or "").strip()
            if not ip_text or ip_text in known_node_ips:
                continue
            is_internal = _is_internal_ip(ip_text)
            if is_internal and not include_unmanaged:
                continue
            if not is_internal and not include_external:
                continue
            node_id = f"SCAN-{ip_text}"
            if node_id in node_ids:
                continue
            nodes.append(
                {
                    "id": node_id,
                    "label": ip_text,
                    "kind": "內網未納管" if is_internal else "外網未知",
                    "ip": ip_text,
                    "os": row.get("os") or row.get("host_type") or "",
                    "system": "掃描未納管",
                    "scan_status": row.get("type_label") or "掃描到但未納管",
                    "open_ports": row.get("open_ports") or [],
                }
            )
            node_ids.add(node_id)
            known_node_ips.add(ip_text)
    dimensions = _layout(nodes, edges)
    meta = _topology_meta("host")
    meta.update(dimensions)
    meta.update({"hosts": len(hosts), "relations": len(edges), "include_external": include_external, "include_unmanaged": include_unmanaged, "layout_mode": "host_relation_graph"})
    return {"view": "host", "nodes": nodes, "edges": edges, "meta": meta}


def _ip_topology(limit: int = 200, include_external: bool = False, include_unmanaged: bool = False) -> dict[str, Any]:
    hosts = _hosts()[:limit]
    nodes = []
    edges = []
    latest = latest_collect_run()
    relations = list_relations({"run_id": latest["run_id"]}) if latest else []
    ip_to_host = _known_host_ip_map()
    for host in hosts:
        for ip in host.get("ip_addresses") or ([host.get("ip")] if host.get("ip") else []):
            nodes.append({"id": ip, "label": ip, "kind": "IP", "hostname": host.get("hostname"), "os": host.get("os")})
    node_ids = {node["id"] for node in nodes}
    for rel in relations:
        evidence = rel.get("evidence") or {}
        source = evidence.get("caller_ip") or rel.get("from_system")
        target = evidence.get("last_remote_ip") or rel.get("to_system")
        if target and target not in node_ids and not include_unmanaged and _is_internal_ip(str(target)):
            continue
        if target and target not in node_ids and not include_external and not _is_internal_ip(str(target)):
            continue
        if source not in node_ids:
            nodes.append({"id": source, "label": source, "kind": "IP", "hostname": ip_to_host.get(source)})
            node_ids.add(source)
        if target not in node_ids:
            nodes.append({"id": target, "label": target, "kind": _unknown_ip_kind(str(target)), "hostname": ip_to_host.get(target)})
            node_ids.add(target)
        ip_rel = dict(rel)
        ip_rel["from_system"] = source
        ip_rel["to_system"] = target
        edges.append(_edge_payload(ip_rel, source, target))
    dimensions = _layout(nodes, edges)
    meta = _topology_meta("ip")
    meta.update(dimensions)
    meta.update({"hosts": len(hosts), "ips": len([n for n in nodes if n.get("kind") == "IP"]), "relations": len(edges), "include_external": include_external, "include_unmanaged": include_unmanaged})
    return {"view": "ip", "nodes": nodes, "edges": edges, "meta": meta}


def _reachable(center: str, relations: list[dict[str, Any]], depth: int) -> set[str]:
    visited = {center}
    current = {center}
    for _ in range(max(depth, 1)):
        nxt = set()
        for rel in relations:
            if rel.get("from_system") in current:
                nxt.add(rel.get("to_system"))
            if rel.get("to_system") in current:
                nxt.add(rel.get("from_system"))
        nxt = {item for item in nxt if item and item not in visited}
        if not nxt:
            break
        visited.update(nxt)
        current = nxt
    return visited


def downstream_impact(system_id: str, max_depth: int = 3) -> dict[str, Any]:
    relations = list_relations()
    layers = []
    visited = {system_id}
    current = {system_id}
    for _ in range(max_depth):
        next_layer = {rel["to_system"] for rel in relations if rel.get("from_system") in current and rel.get("to_system") not in visited}
        if not next_layer:
            break
        layers.append(sorted(next_layer))
        visited.update(next_layer)
        current = next_layer
    return {"system_id": system_id, "direction": "downstream", "layers": layers, "total": len(visited) - 1}


def upstream_impact(system_id: str, max_depth: int = 3) -> dict[str, Any]:
    relations = list_relations()
    layers = []
    visited = {system_id}
    current = {system_id}
    for _ in range(max_depth):
        next_layer = {rel["from_system"] for rel in relations if rel.get("to_system") in current and rel.get("from_system") not in visited}
        if not next_layer:
            break
        layers.append(sorted(next_layer))
        visited.update(next_layer)
        current = next_layer
    return {"system_id": system_id, "direction": "upstream", "layers": layers, "total": len(visited) - 1}


def _known_host_ips() -> set[str]:
    ips = set()
    for host in _hosts():
        for ip in host.get("ip_addresses") or ([host.get("ip")] if host.get("ip") else []):
            ips.add(ip)
    return ips


def _known_host_ip_map() -> dict[str, str]:
    items = {}
    for host in _hosts():
        hostname = host.get("hostname")
        for ip in host.get("ip_addresses") or ([host.get("ip")] if host.get("ip") else []):
            if ip and hostname:
                items[ip] = hostname
    return items


def _host_system_index() -> dict[str, str]:
    items = {}
    for host in _hosts():
        hostname = host.get("hostname")
        if not hostname:
            continue
        name = _host_business_system_name(host)
        if not name:
            continue
        items[hostname] = _system_id(name)
    return items


def _is_internal_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr.is_private or addr.is_loopback or addr.is_link_local


def _unknown_node_kind(ip: str) -> str:
    return "內網未納管" if _is_internal_ip(ip) else "外網未知"


def _unknown_ip_kind(ip: str) -> str:
    return "內網未納管 IP" if _is_internal_ip(ip) else "外網 IP"


def _classify_external(ip: str) -> Optional[dict[str, str]]:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    for item in KNOWN_EXTERNAL:
        if addr in ipaddress.ip_network(item["cidr"]):
            return item
    for system in get_collection("dependency_systems").find({"external": True}):
        cidr = (system.get("metadata") or {}).get("cidr")
        if cidr and addr in ipaddress.ip_network(cidr, strict=False):
            return {"name": system.get("display_name") or system.get("system_id"), "cidr": cidr, "category": system.get("category", "External")}
    return None


def analyze_ghosts(include_external: bool = False) -> dict[str, Any]:
    known_ips = _known_host_ips()
    ghosts: dict[str, dict[str, Any]] = {}
    ignored = {item["ip"] for item in get_collection("dependency_ghost_ignored").find({}, {"ip": 1}) if item.get("ip")}
    for rel in get_collection("dependency_relations").find({"source": "auto"}):
        evidence = rel.get("evidence") or {}
        ip = evidence.get("last_remote_ip")
        if not ip or ip in known_ips or ip in ignored or _classify_external(ip):
            continue
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            continue
        is_internal = _is_internal_ip(ip)
        if not include_external and not is_internal:
            continue
        item = ghosts.setdefault(ip, {"ip": ip, "seen_count": 0, "callers": [], "remote_ports": set(), "severity": "medium", "scope": "內網" if is_internal else "外網"})
        item["seen_count"] += int(evidence.get("seen_count") or 1)
        item["severity"] = "high" if is_internal else "medium"
        if evidence.get("last_remote_port"):
            item["remote_ports"].add(evidence["last_remote_port"])
        item["callers"].append({"hostname": evidence.get("caller_hostname") or "", "process": evidence.get("process_name") or "", "port": evidence.get("last_remote_port") or "", "count": evidence.get("seen_count") or 1})
    rows = []
    for item in ghosts.values():
        item["remote_ports"] = sorted(item["remote_ports"])
        rows.append(item)
    return {"items": sorted(rows, key=lambda x: (x["severity"], -x["seen_count"])), "summary": {"total": len(rows), "high": sum(1 for item in rows if item["severity"] == "high"), "medium": sum(1 for item in rows if item["severity"] == "medium"), "include_external": include_external}}


def adopt_ghost(ip: str, action: str, payload: dict[str, Any], actor: str = "system") -> dict[str, Any]:
    if action == "add_external":
        return upsert_system({"display_name": payload.get("display_name") or ip, "system_id": payload.get("system_id") or _system_id(payload.get("display_name") or ip), "category": "External", "external": True, "metadata": {"cidr": payload.get("cidr") or f"{ip}/32"}}, actor)
    if action == "ignore":
        get_collection("dependency_ghost_ignored").update_one({"ip": ip}, {"$set": {"ip": ip, "reason": payload.get("reason") or "", "updated_at": _now(), "updated_by": actor}}, upsert=True)
        return {"ip": ip, "action": "ignore", "status": "ok"}
    return {"ip": ip, "action": action, "status": "pending_host_create", "message": "請到資產管理建立主機資料後再重新分析 Ghost。"}
