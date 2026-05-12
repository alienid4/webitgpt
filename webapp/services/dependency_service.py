from __future__ import annotations

import ipaddress
import hashlib
import re
import subprocess
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId

from webapp.services.host_service import list_hosts
from webapp.services.mongo_service import get_collection


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


def _system_id(name: str) -> str:
    key = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip()).strip("-").upper()
    if key:
        return f"SYS-{key}"
    digest = hashlib.sha1(name.strip().encode("utf-8")).hexdigest()[:8].upper()
    return f"SYS-{digest}"


def _hosts() -> list[dict[str, Any]]:
    return list_hosts(page=1, page_size=10000)["items"]


def sync_systems_from_hosts(actor: str = "system") -> int:
    now = _now()
    col = get_collection("dependency_systems")
    count = 0
    by_system: dict[str, dict[str, Any]] = {}
    for host in _hosts():
        name = host.get("system_name") or host.get("asset_name") or host.get("hostname")
        sid = _system_id(name)
        item = by_system.setdefault(
            sid,
            {
                "system_id": sid,
                "display_name": name,
                "tier": str(host.get("tier") or "C").upper()[:1] if host.get("tier") in {"A", "B", "C"} else "C",
                "category": "AP",
                "description": "由資產管理系統同步建立",
                "owner": host.get("ap_owner") or host.get("custodian") or "",
                "host_refs": [],
                "external": False,
                "metadata": {},
                "updated_at": now,
                "updated_by": actor,
            },
        )
        if host.get("hostname") and host["hostname"] not in item["host_refs"]:
            item["host_refs"].append(host["hostname"])
    for item in by_system.values():
        result = col.update_one(
            {"system_id": item["system_id"]},
            {"$set": item, "$setOnInsert": {"created_at": now, "created_by": actor}},
            upsert=True,
        )
        count += int(bool(result.upserted_id or result.modified_count))
        if item["system_id"] != "SYS-UNKNOWN":
            col.delete_many({"system_id": "SYS-UNKNOWN", "display_name": item["display_name"]})
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


def upsert_system(data: dict[str, Any], actor: str = "system") -> dict[str, Any]:
    now = _now()
    system_id = data.get("system_id") or _system_id(data.get("display_name") or "")
    doc = {
        "system_id": system_id,
        "display_name": data.get("display_name") or system_id,
        "tier": data.get("tier") or "C",
        "category": data.get("category") or "AP",
        "description": data.get("description") or "",
        "owner": data.get("owner") or "",
        "host_refs": data.get("host_refs") or [],
        "external": bool(data.get("external")),
        "metadata": data.get("metadata") or {},
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
    return [_public(item) or {} for item in get_collection("dependency_relations").find(query).sort("updated_at", -1)]


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


def delete_relation(relation_id: str) -> bool:
    return bool(get_collection("dependency_relations").delete_one({"_id": ObjectId(relation_id)}).deleted_count)


def latest_collect_run() -> Optional[dict[str, Any]]:
    return _public(get_collection("dependency_collect_runs").find_one({"status": "success"}, sort=[("finished_at", -1)]))


def collect_topology(actor: str = "system", limit_hosts: int = 20) -> dict[str, Any]:
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


def collect_runs(limit: int = 20) -> list[dict[str, Any]]:
    return [_public(item) or {} for item in get_collection("dependency_collect_runs").find({}).sort("started_at", -1).limit(limit)]


def _run_ss_tunp(host: dict[str, Any]) -> str:
    hostname = host.get("hostname") or host.get("ip")
    if host.get("ip") in {"127.0.0.1", "localhost", "192.168.1.221"} or hostname in {"localhost", "secansible"}:
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


def _layout(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
    count = max(len(nodes), 1)
    columns = min(5, count)
    for index, node in enumerate(nodes):
        node["x"] = 110 + (index % columns) * 220
        node["y"] = 90 + (index // columns) * 140
    by_id = {node["id"]: node for node in nodes}
    for edge in edges:
        source = by_id.get(edge.get("source"))
        target = by_id.get(edge.get("target"))
        if source and target:
            edge.update({"x1": source["x"], "y1": source["y"], "x2": target["x"], "y2": target["y"]})


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
    return {
        "view": view,
        "collect_status": latest.get("status"),
        "run_id": latest.get("run_id"),
        "collector": latest.get("collector"),
        "last_collect_at": _iso(latest.get("finished_at") or latest.get("started_at")),
        "edge_count": latest.get("edge_count", 0),
        "message": "目前顯示最後一次成功 ss -tunp 採集快照。",
    }


def topology(view: str = "system", center: str = "", depth: int = 2, limit: int = 200, include_external: bool = False, failed_node: str = "", focus_impact: bool = False) -> dict[str, Any]:
    view = view if view in {"system", "host", "ip"} else "system"
    if view == "host":
        data = _host_topology(limit, include_external=include_external)
    elif view == "ip":
        data = _ip_topology(limit, include_external=include_external)
    else:
        data = _system_topology(center=center, depth=depth, limit=limit, include_external=include_external)
    _apply_failure_simulation(data, failed_node, max_depth=max(depth, 1))
    if focus_impact:
        _filter_to_failure_scope(data)
    data.setdefault("meta", {})["focus_impact"] = bool(focus_impact)
    return data


def _apply_failure_simulation(data: dict[str, Any], failed_node: str = "", max_depth: int = 2) -> None:
    failed_node = (failed_node or "").strip()
    nodes = data.get("nodes") or []
    edges = data.get("edges") or []
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
    _layout(data["nodes"], data["edges"])
    data.setdefault("meta", {})["focus_node_count"] = len(data["nodes"])
    data.setdefault("meta", {})["focus_edge_count"] = len(data["edges"])


def _system_topology(center: str = "", depth: int = 2, limit: int = 200, include_external: bool = False) -> dict[str, Any]:
    systems = list_systems()
    system_map = {item["system_id"]: item for item in systems}
    host_to_system = _host_system_index()
    latest = latest_collect_run()
    raw_relations = list_relations({"run_id": latest["run_id"]}) if latest else []
    relation_map: dict[tuple[str, str], dict[str, Any]] = {}
    for rel in raw_relations:
        source_host = rel.get("from_system")
        source_system = host_to_system.get(source_host or "")
        if not source_system:
            continue
        evidence = rel.get("evidence") or {}
        target_host = rel.get("to_system")
        remote_ip = evidence.get("last_remote_ip") or str(target_host).replace("UNKNOWN-", "")
        target_system = host_to_system.get(target_host or "")
        if not target_system and str(target_host).startswith("UNKNOWN-"):
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
            _merge_evidence(relation_map[key].setdefault("evidence", {}), evidence)
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
    _layout(nodes, edges)
    meta = _topology_meta("system")
    meta.update({"systems": len(nodes), "relations": len(edges), "center": center, "depth": depth, "include_external": include_external})
    return {"view": "system", "nodes": nodes, "edges": edges, "meta": meta}


def _host_topology(limit: int = 200, include_external: bool = False) -> dict[str, Any]:
    hosts = _hosts()[:limit]
    host_map = {host.get("hostname"): host for host in hosts if host.get("hostname")}
    ip_map = _known_host_ip_map()
    nodes = [{"id": host.get("hostname"), "label": host.get("hostname"), "kind": "主機", "ip": host.get("ip"), "os": host.get("os"), "system": host.get("system_name") or ""} for host in hosts if host.get("hostname")]
    node_ids = {node["id"] for node in nodes}
    edges = []
    latest = latest_collect_run()
    relations = list_relations({"run_id": latest["run_id"]}) if latest else []
    for rel in relations:
        source = rel.get("from_system")
        target = rel.get("to_system")
        evidence = rel.get("evidence") or {}
        remote_ip = evidence.get("last_remote_ip") or str(target).replace("UNKNOWN-", "")
        if str(target).startswith("UNKNOWN-") and not include_external and not _is_internal_ip(remote_ip):
            continue
        if target not in node_ids:
            label = ip_map.get(remote_ip) or remote_ip or target
            kind = _unknown_node_kind(remote_ip) if str(target).startswith("UNKNOWN-") else "主機"
            nodes.append({"id": target, "label": label, "kind": kind, "ip": remote_ip, "os": ""})
            node_ids.add(target)
        source_label = host_map.get(source, {}).get("hostname") or source
        target_label = host_map.get(target, {}).get("hostname") or evidence.get("last_remote_ip") or target
        edges.append(_edge_payload(rel, source_label, target_label))
    _layout(nodes, edges)
    meta = _topology_meta("host")
    meta.update({"hosts": len(hosts), "relations": len(edges), "include_external": include_external})
    return {"view": "host", "nodes": nodes, "edges": edges, "meta": meta}


def _ip_topology(limit: int = 200, include_external: bool = False) -> dict[str, Any]:
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
    _layout(nodes, edges)
    meta = _topology_meta("ip")
    meta.update({"hosts": len(hosts), "ips": len([n for n in nodes if n.get("kind") == "IP"]), "relations": len(edges), "include_external": include_external})
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
        name = host.get("system_name") or host.get("asset_name") or hostname
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
