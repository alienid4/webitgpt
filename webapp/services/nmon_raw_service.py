from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from webapp import config
from webapp.services.host_service import list_all_hosts
from webapp.services.mongo_service import get_collection


NMON_RAW_DIR = Path(config.DATA_DIR) / "nmon_raw"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_float(value: Any) -> Optional[float]:
    try:
        if value in {None, "", "-"}:
            return None
        return round(float(str(value).strip()), 2)
    except (TypeError, ValueError):
        return None


def _header_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _host_lookup() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for host in list_all_hosts():
        for key in [host.get("hostname"), host.get("asset_seq"), host.get("primary_ip")]:
            if key:
                result[str(key).lower()] = host
    return result


def _parse_nmon_timestamp(value: str) -> Optional[datetime]:
    value = value.strip()
    for fmt in ("%H:%M:%S,%d-%b-%Y", "%H:%M:%S,%d-%B-%Y"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def parse_nmon_raw(text: str, fallback_hostname: str = "") -> dict[str, Any]:
    host = fallback_hostname.strip()
    headers: dict[str, list[str]] = {}
    time_map: dict[str, datetime] = {}
    samples: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2:
            continue
        section = parts[0]
        marker = parts[1]
        if section == "AAA" and marker.lower() == "host" and len(parts) >= 3:
            host = parts[2]
            continue
        if section == "ZZZZ" and marker.startswith("T") and len(parts) >= 4:
            parsed = _parse_nmon_timestamp(f"{parts[2]},{parts[3]}")
            if parsed:
                time_map[marker] = parsed
            continue
        if marker.startswith("T"):
            header = headers.get(section, [])
            record = {header[index]: parts[index + 2] for index in range(min(len(header), max(len(parts) - 2, 0)))}
            sample = samples.setdefault(marker, {"tick": marker})
            if marker in time_map:
                sample["sampled_at"] = time_map[marker]
            if section == "CPU_ALL":
                busy = _to_float(record.get("busy") or record.get("cpu_total") or record.get("user"))
                idle = _to_float(record.get("idle"))
                if busy is None and idle is not None:
                    busy = round(max(0.0, 100.0 - idle), 2)
                sample["cpu_pct"] = busy
            elif section == "MEM":
                total = _to_float(record.get("memtotal") or record.get("memory_mb") or record.get("total"))
                free = _to_float(record.get("memfree") or record.get("free"))
                available = _to_float(record.get("memavailable") or record.get("available"))
                used = _to_float(record.get("memused") or record.get("used"))
                if total and available is not None:
                    sample["mem_pct"] = round(max(0.0, min(100.0, (total - available) * 100 / total)), 2)
                elif total and free is not None:
                    sample["mem_pct"] = round(max(0.0, min(100.0, (total - free) * 100 / total)), 2)
                elif total and used is not None:
                    sample["mem_pct"] = round(max(0.0, min(100.0, used * 100 / total)), 2)
            elif section in {"DISKBUSY", "DISKBSIZE"}:
                values = [_to_float(value) for value in record.values()]
                clean = [value for value in values if value is not None]
                if clean:
                    sample["disk_pct"] = max(clean)
            elif section == "NET":
                values = []
                for key, value in record.items():
                    if key.startswith("lo_") or key == "lo":
                        continue
                    parsed = _to_float(value)
                    if parsed is not None:
                        values.append(abs(parsed))
                if values:
                    sample["network_kbps"] = round(sum(values), 2)
            continue
        headers[section] = [_header_key(item) for item in parts[2:]]

    if not host:
        warnings.append("raw file 沒有 AAA,host，已使用上傳檔名推估主機。")
    normalized = []
    for tick, sample in sorted(samples.items()):
        if not any(sample.get(key) is not None for key in ["cpu_pct", "mem_pct", "disk_pct"]):
            continue
        normalized.append(sample)
    return {"hostname": host or fallback_hostname, "samples": normalized, "sample_count": len(normalized), "warnings": warnings}


def import_nmon_raw_file(filename: str, content: bytes, user: str = "system") -> dict[str, Any]:
    NMON_RAW_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename or "upload.nmon")
    digest = hashlib.sha256(content).hexdigest()
    existing = get_collection("nmon_raw_files").find_one({"sha256": digest}, {"_id": 0})
    if existing:
        return {"status": "duplicate", "raw_file_id": existing.get("raw_file_id"), "filename": existing.get("filename"), "inserted_samples": 0}

    text = content.decode("utf-8", errors="replace")
    parsed = parse_nmon_raw(text, Path(safe_name).stem)
    host_lookup = _host_lookup()
    host_meta = host_lookup.get(str(parsed["hostname"]).lower(), {})
    stamp = _now().strftime("%Y%m%d%H%M%S")
    raw_file_id = f"nmonraw-{stamp}-{digest[:8]}"
    target = NMON_RAW_DIR / f"{raw_file_id}_{safe_name}"
    target.write_bytes(content)

    raw_doc = {
        "raw_file_id": raw_file_id,
        "filename": safe_name,
        "path": str(target),
        "sha256": digest,
        "hostname": parsed["hostname"],
        "asset_seq": host_meta.get("asset_seq", ""),
        "sample_count": parsed["sample_count"],
        "warnings": parsed["warnings"],
        "uploaded_by": user,
        "uploaded_at": _now(),
        "status": "ok" if parsed["sample_count"] else "no_samples",
    }
    get_collection("nmon_raw_files").insert_one(raw_doc)

    docs = []
    for sample in parsed["samples"]:
        sampled_at = sample.get("sampled_at") or _now()
        docs.append(
            {
                "asset_seq": host_meta.get("asset_seq", ""),
                "hostname": parsed["hostname"],
                "sampled_at": sampled_at,
                "cpu_pct": sample.get("cpu_pct"),
                "mem_pct": sample.get("mem_pct"),
                "disk_pct": sample.get("disk_pct"),
                "network_kbps": sample.get("network_kbps"),
                "load_avg": "",
                "created_by": user,
                "source": "nmon_raw",
                "raw_file_id": raw_file_id,
                "raw_filename": safe_name,
                "error": "",
            }
        )
    if docs:
        get_collection("nmon_data").insert_many(docs)
    return {
        "status": raw_doc["status"],
        "raw_file_id": raw_file_id,
        "filename": safe_name,
        "hostname": parsed["hostname"],
        "sample_count": parsed["sample_count"],
        "inserted_samples": len(docs),
        "warnings": parsed["warnings"],
    }


def list_nmon_raw_files(limit: int = 10) -> list[dict[str, Any]]:
    return list(get_collection("nmon_raw_files").find({}, {"_id": 0}).sort("uploaded_at", -1).limit(limit))


def nmon_raw_pipeline_status() -> dict[str, Any]:
    latest = list_nmon_raw_files(5)
    raw_count = get_collection("nmon_raw_files").count_documents({})
    sample_count = get_collection("nmon_data").count_documents({"source": "nmon_raw"})
    last = latest[0] if latest else {}
    return {
        "raw_files": raw_count,
        "raw_samples": sample_count,
        "latest": last,
        "latest_files": latest,
        "raw_dir": str(NMON_RAW_DIR),
        "status": "ok" if raw_count else "no_raw_files",
        "message": "已可匯入 .nmon raw file 並轉成月報資料。" if raw_count else "尚未匯入 .nmon raw file；目前月報仍主要使用既有採樣資料。",
    }
