from __future__ import annotations

import ipaddress
import shutil
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from webapp.services import host_service
from webapp.services.mongo_service import get_collection


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _public(doc: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not doc:
        return None
    out = {k: v for k, v in doc.items() if k != "_id"}
    if "_id" in doc:
        out["id"] = str(doc["_id"])
    return out


def _used_ips() -> set[str]:
    used: set[str] = set()
    try:
        for host in get_collection("hosts").find({"status": {"$ne": "retired"}}, {"ip": 1, "ip_addresses": 1}):
            if host.get("ip"):
                used.add(str(host["ip"]))
            for ip in host.get("ip_addresses") or []:
                used.add(str(ip))
        for reservation in get_collection("ip_reservations").find({"status": {"$in": ["reserved", "assigned"]}}, {"ip": 1}):
            if reservation.get("ip"):
                used.add(str(reservation["ip"]))
    except Exception:
        return used
    return used


def _reserved_ips_for_network(item: dict[str, Any]) -> set[str]:
    reserved: set[str] = set()
    if item.get("gateway"):
        reserved.add(str(item["gateway"]))
    network = ipaddress.ip_network(item["cidr"], strict=False)
    values = item.get("reserved_ips") or []
    if isinstance(values, str):
        values = values.replace("\r", "\n").replace(",", "\n").splitlines()
    for raw in values:
        token = str(raw).strip()
        if not token:
            continue
        if "-" in token:
            start_text, end_text = [part.strip() for part in token.split("-", 1)]
            start = ipaddress.ip_address(start_text)
            end = ipaddress.ip_address(end_text)
            current = int(start)
            while current <= int(end):
                ip_text = str(ipaddress.ip_address(current))
                if ipaddress.ip_address(ip_text) in network:
                    reserved.add(ip_text)
                current += 1
            continue
        ip = ipaddress.ip_address(token)
        if ip in network:
            reserved.add(str(ip))
    return reserved


def list_networks() -> list[dict[str, Any]]:
    used = _used_ips()
    rows = []
    try:
        for item in get_collection("ipam_networks").find({}).sort([("dc", 1), ("environment", 1), ("cidr", 1)]):
            network = ipaddress.ip_network(item["cidr"], strict=False)
            usable = [str(ip) for ip in network.hosts()]
            reserved = _reserved_ips_for_network(item)
            used_count = sum(1 for ip in usable if ip in used)
            reserved_count = sum(1 for ip in usable if ip in reserved and ip not in used)
            row = _public(item) or {}
            row.update(
                {
                    "total_usable": len(usable),
                    "used_count": used_count,
                    "reserved_count": reserved_count,
                    "available_count": max(len(usable) - used_count - reserved_count, 0),
                }
            )
            rows.append(row)
    except Exception:
        return []
    return rows


def network_ip_detail(cidr: str) -> dict[str, Any]:
    network = ipaddress.ip_network(cidr, strict=False)
    network_doc = get_collection("ipam_networks").find_one({"cidr": str(network)}) or {"name": str(network), "cidr": str(network)}
    reserved = _reserved_ips_for_network(network_doc)

    hosts_by_ip: dict[str, list[dict[str, Any]]] = {}
    for host in get_collection("hosts").find({"status": {"$ne": "retired"}}, {"ssh_key": 0}):
        host_ips = []
        if host.get("ip"):
            host_ips.append(str(host["ip"]))
        host_ips.extend(str(ip) for ip in host.get("ip_addresses") or [])
        for ip_text in sorted(set(host_ips)):
            try:
                if ipaddress.ip_address(ip_text) in network:
                    hosts_by_ip.setdefault(ip_text, []).append(_public(host) or {})
            except ValueError:
                continue

    reservations_by_ip: dict[str, dict[str, Any]] = {}
    for reservation in get_collection("ip_reservations").find({"cidr": str(network), "status": {"$in": ["reserved", "assigned"]}}):
        if reservation.get("ip"):
            reservations_by_ip[str(reservation["ip"])] = _public(reservation) or {}

    rows = []
    used_count = 0
    reserved_count = 0
    for ip in network.hosts():
        ip_text = str(ip)
        host_rows = hosts_by_ip.get(ip_text, [])
        reservation = reservations_by_ip.get(ip_text)
        is_reserved = ip_text in reserved or reservation is not None
        if host_rows:
            used_count += 1
            state = "asset"
            enrolled_label = "已納入資產"
        elif is_reserved:
            reserved_count += 1
            state = "reserved"
            enrolled_label = "未納入資產（僅保留）"
        else:
            state = "available"
            enrolled_label = "未納入資產"
        rows.append(
            {
                "ip": ip_text,
                "state": state,
                "state_label": {"asset": "已使用", "reserved": "已保留", "available": "可用"}[state],
                "enrolled_label": enrolled_label,
                "hosts": host_rows,
                "reservation": reservation,
                "reserved_by_rule": ip_text in reserved,
            }
        )

    network_row = _public(network_doc) or {"cidr": str(network)}
    total_usable = network.num_addresses - (2 if network.version == 4 and network.prefixlen < 31 else 0)
    network_row.update(
        {
            "cidr": str(network),
            "total_usable": total_usable,
            "used_count": used_count,
            "reserved_count": reserved_count,
            "available_count": max(total_usable - used_count - reserved_count, 0),
        }
    )
    return {"network": network_row, "rows": rows}


def create_network(data: dict[str, Any], user: str) -> dict[str, Any]:
    cidr = str(data.get("cidr", "")).strip()
    network = ipaddress.ip_network(cidr, strict=False)
    doc = {
        "name": str(data.get("name") or cidr).strip(),
        "cidr": str(network),
        "dc": str(data.get("dc", "")).strip(),
        "environment": str(data.get("environment", "")).strip(),
        "purpose": str(data.get("purpose", "")).strip(),
        "vlan": str(data.get("vlan", "")).strip(),
        "gateway": str(data.get("gateway", "")).strip(),
        "dns": str(data.get("dns", "")).strip(),
        "reserved_ips": [part.strip() for part in str(data.get("reserved_ips", "")).replace("\r", "\n").replace(",", "\n").splitlines() if part.strip()],
        "reserved_note": str(data.get("reserved_note", "")).strip(),
        "created_at": _now(),
        "updated_at": _now(),
        "updated_by": user,
    }
    existing = get_collection("ipam_networks").find_one({"cidr": doc["cidr"]})
    if existing:
        get_collection("ipam_networks").update_one({"_id": existing["_id"]}, {"$set": {**doc, "created_at": existing.get("created_at", doc["created_at"])}})
        return _public(get_collection("ipam_networks").find_one({"_id": existing["_id"]})) or {}
    get_collection("ipam_networks").insert_one(doc)
    return _public(get_collection("ipam_networks").find_one({"cidr": doc["cidr"]})) or {}


def find_next_ip(cidr: str) -> str:
    network = ipaddress.ip_network(cidr, strict=False)
    used = _used_ips()
    network_doc = get_collection("ipam_networks").find_one({"cidr": str(network)}) or {"cidr": str(network)}
    reserved = _reserved_ips_for_network(network_doc)
    for ip in network.hosts():
        ip_text = str(ip)
        if ip_text not in used and ip_text not in reserved:
            return ip_text
    raise ValueError(f"網段已無可用 IP：{cidr}")


def reserve_ip(data: dict[str, Any], user: str) -> dict[str, Any]:
    cidr = str(data.get("cidr", "")).strip()
    if not cidr:
        network = get_collection("ipam_networks").find_one({"_id": data.get("network_id")})
        cidr = network["cidr"] if network else ""
    ip_text = str(data.get("ip") or find_next_ip(cidr)).strip()
    ip = ipaddress.ip_address(ip_text)
    network = ipaddress.ip_network(cidr, strict=False)
    if ip not in network:
        raise ValueError(f"IP {ip_text} 不在網段 {cidr}")
    if ip_text in _used_ips():
        raise ValueError(f"IP 已被使用或預留：{ip_text}")
    doc = {
        "ip": ip_text,
        "cidr": str(network),
        "hostname": str(data.get("hostname", "")).strip(),
        "asset_name": str(data.get("asset_name", "")).strip(),
        "ticket": str(data.get("ticket", "")).strip(),
        "status": "reserved",
        "expires_at": _now() + timedelta(days=int(data.get("days") or 14)),
        "created_at": _now(),
        "updated_at": _now(),
        "updated_by": user,
    }
    get_collection("ip_reservations").insert_one(doc)
    return _public(doc) or {}


def list_reservations() -> list[dict[str, Any]]:
    try:
        return [_public(item) or {} for item in get_collection("ip_reservations").find({}).sort("created_at", -1).limit(100)]
    except Exception:
        return []


def _host_ips_in_network(cidr: str) -> dict[str, list[dict[str, Any]]]:
    network = ipaddress.ip_network(cidr, strict=False)
    hosts_by_ip: dict[str, list[dict[str, Any]]] = {}
    for host in get_collection("hosts").find({"status": {"$ne": "retired"}}, {"ssh_key": 0}):
        values = []
        if host.get("ip"):
            values.append(str(host["ip"]))
        values.extend(str(ip) for ip in host.get("ip_addresses") or [])
        for ip_text in sorted(set(values)):
            try:
                if ipaddress.ip_address(ip_text) in network:
                    hosts_by_ip.setdefault(ip_text, []).append(_public(host) or {})
            except ValueError:
                continue
    return hosts_by_ip


def _run_nmap_ping_scan(cidr: str) -> dict[str, Any]:
    if not shutil.which("nmap"):
        return {"mode": "nmap_missing", "ips": [], "error": "nmap 未安裝，無法執行網段掃描。"}
    try:
        completed = subprocess.run(
            ["nmap", "-sn", "-oX", "-", cidr],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return {"mode": "nmap_timeout", "ips": [], "error": "nmap 掃描逾時。"}
    if completed.returncode not in (0, 1):
        return {"mode": "nmap_error", "ips": [], "error": completed.stderr.strip() or "nmap 掃描失敗。"}
    ips = []
    try:
        root = ET.fromstring(completed.stdout)
        for host in root.findall("host"):
            status = host.find("status")
            if status is not None and status.attrib.get("state") != "up":
                continue
            for address in host.findall("address"):
                if address.attrib.get("addrtype") == "ipv4":
                    ips.append(address.attrib.get("addr", ""))
    except ET.ParseError as exc:
        return {"mode": "nmap_parse_error", "ips": [], "error": f"nmap XML 解析失敗：{exc}"}
    return {"mode": "nmap", "ips": sorted({ip for ip in ips if ip}), "error": ""}


def _infer_host_type_from_os(os_text: str) -> str:
    value = str(os_text or "").lower()
    if "windows" in value:
        return "windows"
    if "aix" in value:
        return "aix"
    if "as/400" in value or "as400" in value or "ibm i" in value:
        return "as400"
    if "vmware" in value or "esxi" in value:
        return "vmware_host"
    if value:
        return "linux"
    return "end_device"


def _parse_nmap_hosts(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    rows = []
    for host in root.findall("host"):
        status = host.find("status")
        if status is not None and status.attrib.get("state") != "up":
            continue
        ip_text = ""
        for address in host.findall("address"):
            if address.attrib.get("addrtype") == "ipv4":
                ip_text = str(address.attrib.get("addr", "")).strip()
                break
        if not ip_text:
            continue
        hostname = ""
        hostnames = host.find("hostnames")
        if hostnames is not None:
            first = hostnames.find("hostname")
            if first is not None:
                hostname = str(first.attrib.get("name", "")).strip()
        os_text = ""
        os_node = host.find("os")
        if os_node is not None:
            osmatch = os_node.find("osmatch")
            if osmatch is not None:
                os_text = str(osmatch.attrib.get("name", "")).strip()
        rows.append({"ip": ip_text, "hostname": hostname, "os": os_text, "host_type": _infer_host_type_from_os(os_text)})
    return rows


def run_asset_discovery_scan(cidr: str, user: str = "system", environment: str = "", dc: str = "") -> dict[str, Any]:
    network = ipaddress.ip_network(cidr, strict=False)
    hosts_by_ip = _host_ips_in_network(str(network))
    if not shutil.which("nmap"):
        report = {
            "cidr": str(network),
            "mode": "nmap_missing",
            "error": "nmap 未安裝，無法執行網段掃描。",
            "discovered_count": 0,
            "cmdb_count": len(hosts_by_ip),
            "mismatch_count": 0,
            "rows": [],
            "started_at": _now(),
            "updated_by": user,
            "source": "asset_new_workbench",
            "default_environment": environment,
            "default_dc": dc,
        }
        get_collection("network_scan_reports").insert_one(report)
        return _public(report) or report

    commands = [
        ["nmap", "-O", "--osscan-guess", "-oX", "-", str(network)],
        ["nmap", "-sn", "-R", "-oX", "-", str(network)],
    ]
    parsed_hosts: list[dict[str, Any]] = []
    mode = "nmap_os"
    last_error = ""
    for index, command in enumerate(commands):
        try:
            completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            last_error = "nmap 掃描逾時。"
            continue
        if completed.returncode not in (0, 1):
            last_error = completed.stderr.strip() or "nmap 掃描失敗。"
            continue
        try:
            parsed_hosts = _parse_nmap_hosts(completed.stdout)
            mode = "nmap_os" if index == 0 else "nmap_ping"
            break
        except ET.ParseError as exc:
            last_error = f"nmap XML 解析失敗：{exc}"

    rows = []
    for item in sorted(parsed_hosts, key=lambda row: ipaddress.ip_address(row["ip"])):
        ip_text = item["ip"]
        enrolled_hosts = hosts_by_ip.get(ip_text, [])
        if enrolled_hosts:
            for host in enrolled_hosts:
                rows.append(
                    {
                        "severity": "info",
                        "type": "already_in_cmdb",
                        "type_label": "已納管",
                        "ip": ip_text,
                        "hostname": host.get("hostname") or item.get("hostname", ""),
                        "asset_name": host.get("asset_name", ""),
                        "os": host.get("os") or item.get("os", ""),
                        "host_type": host.get("host_type") or item.get("host_type", ""),
                        "status": host.get("status", ""),
                        "suggestion": "此 IP 已在資產管理系統，不需要重複建立。",
                    }
                )
            continue
        rows.append(
            {
                "severity": "high",
                "type": "scan_not_in_cmdb",
                "type_label": "掃描到但未納管",
                "ip": ip_text,
                "hostname": item.get("hostname", ""),
                "asset_name": "",
                "os": item.get("os") or "未偵測",
                "host_type": item.get("host_type") or "end_device",
                "status": "待建立草稿",
                "suggestion": "請勾選需要納管的主機，建立草稿後再補齊資產欄位。",
            }
        )

    report = {
        "cidr": str(network),
        "mode": mode,
        "error": last_error if not parsed_hosts else "",
        "discovered_count": len(parsed_hosts),
        "cmdb_count": len(hosts_by_ip),
        "mismatch_count": len([row for row in rows if row.get("type") == "scan_not_in_cmdb"]),
        "rows": rows,
        "started_at": _now(),
        "updated_by": user,
        "source": "asset_new_workbench",
        "default_environment": environment,
        "default_dc": dc,
    }
    get_collection("network_scan_reports").insert_one(report)
    return _public(report) or report


def run_network_reconcile(cidr: str, user: str = "system") -> dict[str, Any]:
    network = ipaddress.ip_network(cidr, strict=False)
    scan = _run_nmap_ping_scan(str(network))
    discovered = set(scan["ips"])
    hosts_by_ip = _host_ips_in_network(str(network))
    cmdb_ips = set(hosts_by_ip.keys())
    reservations = {
        str(item["ip"]): _public(item) or {}
        for item in get_collection("ip_reservations").find({"cidr": str(network), "status": {"$in": ["reserved", "assigned"]}})
        if item.get("ip")
    }

    rows = []
    for ip_text in sorted(discovered - cmdb_ips, key=lambda value: ipaddress.ip_address(value)):
        rows.append(
            {
                "severity": "high",
                "type": "scan_not_in_cmdb",
                "type_label": "掃描有回應但未納入資產",
                "ip": ip_text,
                "hostname": "",
                "asset_name": "",
                "os": "",
                "host_type": "",
                "status": "需要補申請",
                "suggestion": "請建立資產草稿或補資產申請。",
            }
        )
    for ip_text in sorted(cmdb_ips - discovered, key=lambda value: ipaddress.ip_address(value)):
        for host in hosts_by_ip[ip_text]:
            rows.append(
                {
                    "severity": "medium",
                    "type": "cmdb_not_seen",
                    "type_label": "資產有登錄但掃描未回應",
                    "ip": ip_text,
                    "hostname": host.get("hostname", ""),
                    "asset_name": host.get("asset_name", ""),
                    "os": host.get("os", ""),
                    "host_type": host.get("host_type", ""),
                    "status": host.get("status", ""),
                    "suggestion": "確認主機是否關機、防火牆阻擋 ICMP/ARP，或資產已退役未更新。",
                }
            )
    for ip_text, hosts in sorted(hosts_by_ip.items(), key=lambda item: ipaddress.ip_address(item[0])):
        if len(hosts) <= 1:
            continue
        rows.append(
            {
                "severity": "high",
                "type": "duplicate_ip",
                "type_label": "多筆資產使用同一 IP",
                "ip": ip_text,
                "hostname": "、".join(host.get("hostname", "") for host in hosts),
                "asset_name": "、".join(host.get("asset_name", "") for host in hosts),
                "os": "",
                "host_type": "",
                "status": "需要修正",
                "suggestion": "請確認 IP 是否重複登錄或多網卡資料未拆清楚。",
            }
        )
    for ip_text, reservation in sorted(reservations.items(), key=lambda item: ipaddress.ip_address(item[0])):
        if ip_text in discovered and ip_text not in cmdb_ips:
            rows.append(
                {
                    "severity": "medium",
                    "type": "reserved_but_alive",
                    "type_label": "IP 已保留且掃描有回應但未建資產",
                    "ip": ip_text,
                    "hostname": reservation.get("hostname", ""),
                    "asset_name": reservation.get("asset_name", ""),
                    "os": "",
                    "host_type": "",
                    "status": "需要補申請",
                    "suggestion": "請確認是否已部署但尚未建立資產主檔。",
                }
            )

    report = {
        "cidr": str(network),
        "mode": scan["mode"],
        "error": scan["error"],
        "discovered_count": len(discovered),
        "cmdb_count": len(cmdb_ips),
        "mismatch_count": len(rows),
        "rows": rows,
        "started_at": _now(),
        "updated_by": user,
        "schedule": "建議每週執行一次，產出掃描與資產管理不一致名單。",
    }
    get_collection("network_scan_reports").insert_one(report)
    return _public(report) or report


def latest_network_reconcile(cidr: str = "") -> Optional[dict[str, Any]]:
    query = {"cidr": str(ipaddress.ip_network(cidr, strict=False))} if cidr else {}
    return _public(get_collection("network_scan_reports").find_one(query, sort=[("started_at", -1)]))


def _unique_scan_hostname(ip_text: str) -> str:
    base = f"scan-{ip_text.replace('.', '-').replace(':', '-')}"
    hostname = base
    index = 2
    while host_service.get_host(hostname):
        hostname = f"{base}-{index}"
        index += 1
    return hostname


def create_asset_drafts_from_scan(cidr: str, user: str, ips: Optional[list[str]] = None) -> dict[str, Any]:
    network = ipaddress.ip_network(cidr, strict=False)
    report = latest_network_reconcile(str(network))
    if not report:
        raise ValueError("尚未有此網段掃描報告，請先執行 IPAM 網段對帳。")

    requested = {str(ip).strip() for ip in (ips or []) if str(ip).strip()}
    candidates = {}
    for row in report.get("rows") or []:
        if row.get("type") != "scan_not_in_cmdb":
            continue
        ip_text = str(row.get("ip") or "").strip()
        if not ip_text:
            continue
        if requested and ip_text not in requested:
            continue
        candidates[ip_text] = row

    network_doc = get_collection("ipam_networks").find_one({"cidr": str(network)}) or {}
    created = []
    skipped = []
    used = _used_ips()
    now = _now()
    for ip_text in sorted(candidates, key=lambda value: ipaddress.ip_address(value)):
        if ip_text in used:
            skipped.append({"ip": ip_text, "reason": "IP 已存在於資產或保留清單"})
            continue
        source_row = candidates[ip_text]
        source_hostname = str(source_row.get("hostname") or "").strip()
        hostname = source_hostname if source_hostname and not host_service.get_host(source_hostname) else _unique_scan_hostname(ip_text)
        os_text = str(source_row.get("os") or "").strip()
        host_type = str(source_row.get("host_type") or "").strip() or _infer_host_type_from_os(os_text)
        doc = {
            "division": "待補",
            "department": "待補",
            "asset_seq": f"DISC-{now.strftime('%Y%m%d%H%M%S')}-{ip_text.replace('.', '-')}",
            "status": "draft",
            "group_name": "H4",
            "asset_name": f"掃描發現 {ip_text}",
            "device_type": "待分類",
            "quantity": 1,
            "owner": "待補",
            "environment": report.get("default_environment") or network_doc.get("environment") or "DEV",
            "hostname": hostname,
            "os": os_text,
            "ip": ip_text,
            "ip_addresses": [ip_text],
            "network_segments": [str(network)],
            "custodian": "待補",
            "company": "待補",
            "host_type": host_type,
            "dc": report.get("default_dc") or network_doc.get("dc") or "dunan",
            "integrity": 1,
            "confidentiality": 1,
            "availability": 1,
            "note": f"由 IPAM/nmap 掃描發現後建立草稿。來源網段：{network}",
            "import_source": "ipam_scan",
        }
        try:
            host = host_service.create_host(doc, user=user)
            created.append({"ip": ip_text, "hostname": host.get("hostname"), "asset_seq": host.get("asset_seq")})
            used.add(ip_text)
        except Exception as exc:
            skipped.append({"ip": ip_text, "reason": str(exc)})

    return {"cidr": str(network), "created": created, "skipped": skipped, "created_count": len(created), "skipped_count": len(skipped)}


def assign_ip_to_host(host_key: str, cidr: str, user: str) -> dict[str, Any]:
    ip_text = find_next_ip(cidr)
    host = host_service.get_host(host_key)
    if not host:
        raise KeyError(f"找不到資產：{host_key}")
    ip_addresses = list(host.get("ip_addresses") or [])
    if ip_text not in ip_addresses:
        ip_addresses.append(ip_text)
    network_segments = list(host.get("network_segments") or [])
    normalized_cidr = str(ipaddress.ip_network(cidr, strict=False))
    if normalized_cidr not in network_segments:
        network_segments.append(normalized_cidr)
    updated = host_service.update_host(
        host_key,
        {"ip": host.get("ip") or ip_text, "ip_addresses": ip_addresses, "network_segments": network_segments, "status": "pending_data" if host.get("status") == "draft" else host.get("status")},
        user=user,
    )
    get_collection("ip_reservations").insert_one(
        {
            "ip": ip_text,
            "cidr": normalized_cidr,
            "hostname": updated.get("hostname"),
            "asset_name": updated.get("asset_name"),
            "status": "assigned",
            "created_at": _now(),
            "updated_at": _now(),
            "updated_by": user,
        }
    )
    return updated


def create_asset_draft(data: dict[str, Any], user: str) -> dict[str, Any]:
    now = _now()
    asset_name = str(data.get("asset_name", "")).strip()
    if not asset_name:
        raise ValueError("資產名稱必填")
    suffix = now.strftime("%Y%m%d%H%M%S")
    draft_key = f"DRAFT-{suffix}"
    doc = {
        "division": str(data.get("division") or "待補").strip(),
        "department": str(data.get("department") or "待補").strip(),
        "asset_seq": str(data.get("asset_seq") or draft_key).strip(),
        "hostname": str(data.get("hostname") or draft_key.lower()).strip(),
        "asset_name": asset_name,
        "status": "draft",
        "group_name": str(data.get("group_name") or "H4").strip(),
        "device_type": str(data.get("device_type") or "待補").strip(),
        "quantity": int(data.get("quantity") or 1),
        "owner": str(data.get("owner") or "待補").strip(),
        "environment": str(data.get("environment") or "DEV").strip(),
        "custodian": str(data.get("custodian") or "待補").strip(),
        "company": str(data.get("company") or "待補").strip(),
        "host_type": str(data.get("host_type") or "linux").strip(),
        "dc": str(data.get("dc") or "dunan").strip(),
        "integrity": int(data.get("integrity") or 1),
        "confidentiality": int(data.get("confidentiality") or 1),
        "availability": int(data.get("availability") or 1),
        "note": str(data.get("note") or "草稿資產：尚未完成主機名稱、IP 或資產欄位確認。").strip(),
        "import_source": "draft",
    }
    return host_service.create_host(doc, user=user)


def list_extension_definitions() -> list[dict[str, Any]]:
    try:
        return [_public(item) or {} for item in get_collection("extension_definitions").find({}).sort([("order", 1), ("key", 1)])]
    except Exception:
        return []


def save_extension_definition(data: dict[str, Any], user: str) -> dict[str, Any]:
    key = str(data.get("key", "")).strip()
    if not key:
        raise ValueError("欄位代碼必填")
    doc = {
        "key": key,
        "label": str(data.get("label") or key).strip(),
        "field_type": str(data.get("field_type") or "text").strip(),
        "required": bool(data.get("required")),
        "show_in_list": bool(data.get("show_in_list")),
        "searchable": bool(data.get("searchable")),
        "applies_to": str(data.get("applies_to") or "all").strip(),
        "order": int(data.get("order") or 100),
        "updated_at": _now(),
        "updated_by": user,
    }
    get_collection("extension_definitions").update_one({"key": key}, {"$set": doc, "$setOnInsert": {"created_at": _now()}}, upsert=True)
    return _public(get_collection("extension_definitions").find_one({"key": key})) or {}
