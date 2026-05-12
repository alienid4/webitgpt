from __future__ import annotations

import ipaddress
import hashlib
import re
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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _public(doc: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not doc:
        return None
    item = dict(doc)
    if "_id" in item:
        item["_id"] = str(item["_id"])
    return item


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


def _node(system: dict[str, Any]) -> dict[str, Any]:
    tier = system.get("tier") or "C"
    return {
        "id": system["system_id"],
        "label": system.get("display_name") or system["system_id"],
        "kind": "系統",
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


def topology(view: str = "system", center: str = "", depth: int = 2, limit: int = 200) -> dict[str, Any]:
    view = view if view in {"system", "host", "ip"} else "system"
    if view == "host":
        return _host_topology(limit)
    if view == "ip":
        return _ip_topology(limit)
    return _system_topology(center=center, depth=depth, limit=limit)


def _system_topology(center: str = "", depth: int = 2, limit: int = 200) -> dict[str, Any]:
    systems = list_systems()
    system_map = {item["system_id"]: item for item in systems}
    relations = list_relations()
    if center:
        keep = _reachable(center, relations, depth)
        systems = [item for item in systems if item["system_id"] in keep]
        relations = [item for item in relations if item.get("from_system") in keep and item.get("to_system") in keep]
    nodes = [_node(item) for item in systems[:limit]]
    node_ids = {node["id"] for node in nodes}
    edges = [
        {
            "source": rel.get("from_system"),
            "target": rel.get("to_system"),
            "source_label": system_map.get(rel.get("from_system"), {}).get("display_name", rel.get("from_system")),
            "target_label": system_map.get(rel.get("to_system"), {}).get("display_name", rel.get("to_system")),
            "label": rel.get("rel_type") or rel.get("description") or rel.get("source") or "",
            "trust": rel.get("source") or "manual",
            "evidence": rel.get("evidence") or {},
        }
        for rel in relations
        if rel.get("from_system") in node_ids and rel.get("to_system") in node_ids
    ]
    _layout(nodes, edges)
    return {"view": "system", "nodes": nodes, "edges": edges, "meta": {"systems": len(nodes), "relations": len(edges), "center": center, "depth": depth}}


def _host_topology(limit: int = 200) -> dict[str, Any]:
    hosts = _hosts()[:limit]
    nodes = [{"id": host.get("hostname"), "label": host.get("hostname"), "kind": "主機", "ip": host.get("ip"), "os": host.get("os"), "system": host.get("system_name") or ""} for host in hosts if host.get("hostname")]
    system_nodes = []
    edges = []
    known_systems = set()
    for host in hosts:
        system_name = host.get("system_name")
        if not system_name or not host.get("hostname"):
            continue
        sid = _system_id(system_name)
        if sid not in known_systems:
            known_systems.add(sid)
            system_nodes.append({"id": sid, "label": system_name, "kind": "系統"})
        edges.append({"source": sid, "target": host["hostname"], "source_label": system_name, "target_label": host["hostname"], "label": host.get("asset_usage") or "host_ref", "trust": "manual"})
    nodes = system_nodes + nodes
    _layout(nodes, edges)
    return {"view": "host", "nodes": nodes, "edges": edges, "meta": {"hosts": len(hosts), "relations": len(edges)}}


def _ip_topology(limit: int = 200) -> dict[str, Any]:
    hosts = _hosts()[:limit]
    nodes = []
    edges = []
    for host in hosts:
        hostname = host.get("hostname")
        if hostname:
            nodes.append({"id": hostname, "label": hostname, "kind": "主機", "os": host.get("os")})
        for ip in host.get("ip_addresses") or ([host.get("ip")] if host.get("ip") else []):
            nodes.append({"id": ip, "label": ip, "kind": "IP"})
            edges.append({"source": hostname, "target": ip, "source_label": hostname, "target_label": ip, "label": "has_ip", "trust": "manual"})
    _layout(nodes, edges)
    return {"view": "ip", "nodes": nodes, "edges": edges, "meta": {"hosts": len(hosts), "ips": len([n for n in nodes if n.get("kind") == "IP"])}}


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


def analyze_ghosts() -> dict[str, Any]:
    known_ips = _known_host_ips()
    ghosts: dict[str, dict[str, Any]] = {}
    ignored = {item["ip"] for item in get_collection("dependency_ghost_ignored").find({}, {"ip": 1}) if item.get("ip")}
    for rel in get_collection("dependency_relations").find({"source": "auto"}):
        evidence = rel.get("evidence") or {}
        ip = evidence.get("last_remote_ip")
        if not ip or ip in known_ips or ip in ignored or _classify_external(ip):
            continue
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            continue
        item = ghosts.setdefault(ip, {"ip": ip, "seen_count": 0, "callers": [], "remote_ports": set(), "severity": "medium"})
        item["seen_count"] += int(evidence.get("seen_count") or 1)
        item["severity"] = "high" if addr.is_private else "medium"
        if evidence.get("last_remote_port"):
            item["remote_ports"].add(evidence["last_remote_port"])
        item["callers"].append({"hostname": evidence.get("caller_hostname") or "", "process": evidence.get("process_name") or "", "port": evidence.get("last_remote_port") or "", "count": evidence.get("seen_count") or 1})
    rows = []
    for item in ghosts.values():
        item["remote_ports"] = sorted(item["remote_ports"])
        rows.append(item)
    return {"items": sorted(rows, key=lambda x: (x["severity"], -x["seen_count"])), "summary": {"total": len(rows), "high": sum(1 for item in rows if item["severity"] == "high"), "medium": sum(1 for item in rows if item["severity"] == "medium")}}


def adopt_ghost(ip: str, action: str, payload: dict[str, Any], actor: str = "system") -> dict[str, Any]:
    if action == "add_external":
        return upsert_system({"display_name": payload.get("display_name") or ip, "system_id": payload.get("system_id") or _system_id(payload.get("display_name") or ip), "category": "External", "external": True, "metadata": {"cidr": payload.get("cidr") or f"{ip}/32"}}, actor)
    if action == "ignore":
        get_collection("dependency_ghost_ignored").update_one({"ip": ip}, {"$set": {"ip": ip, "reason": payload.get("reason") or "", "updated_at": _now(), "updated_by": actor}}, upsert=True)
        return {"ip": ip, "action": "ignore", "status": "ok"}
    return {"ip": ip, "action": action, "status": "pending_host_create", "message": "請到資產管理建立主機資料後再重新分析 Ghost。"}
