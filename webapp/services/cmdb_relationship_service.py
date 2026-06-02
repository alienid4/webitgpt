from __future__ import annotations

from typing import Any

from webapp.services import host_service
from webapp.services.mongo_service import get_collection
from webapp.services.system_alias_service import canonical_host_system_name, normalize_system_text, system_match_key


DRAFT_STATUSES = {"draft", "pending_ip", "pending_data", "pending_deploy", "pending_retire"}
RETIRED_STATUSES = {"retired"}


def _filled(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _has_any(host: dict[str, Any], fields: list[str]) -> bool:
    return any(_filled(host.get(field)) for field in fields)


def _pct(count: int, total: int) -> int:
    if total <= 0:
        return 0
    return round(count * 100 / total)


def _safe_docs(collection_name: str, projection: dict[str, int] | None = None, limit: int = 5000) -> list[dict[str, Any]]:
    try:
        cursor = get_collection(collection_name).find({}, projection or {"_id": 0}).limit(limit)
        return [dict(item) for item in cursor]
    except Exception:
        return []


def _host_identity(host: dict[str, Any]) -> str:
    return str(host.get("hostname") or host.get("asset_seq") or host.get("ip") or "").strip()


def _host_identity_values(host: dict[str, Any]) -> set[str]:
    return {
        str(host.get(field) or "").strip()
        for field in ("hostname", "asset_seq", "ip", "asset_name")
        if str(host.get(field) or "").strip()
    }


def _host_system_key(host: dict[str, Any]) -> str:
    for field in ("system_name", "group_name", "apid"):
        value = normalize_system_text(host.get(field))
        if value:
            return system_match_key(value)
    return ""


def _display_system_name(host: dict[str, Any]) -> str:
    return canonical_host_system_name(host, default=str(host.get("hostname") or "").strip() or "未分類")


def _host_ports(host: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for field in ("open_ports", "ports", "service_ports", "important_ports"):
        raw = host.get(field)
        if isinstance(raw, list):
            values.extend(str(item.get("port") if isinstance(item, dict) else item) for item in raw)
        elif _filled(raw):
            values.extend(part.strip() for part in str(raw).replace(",", "\n").splitlines() if part.strip())
    if _filled(host.get("ssh_port")):
        values.append(str(host["ssh_port"]))
    return sorted({value for value in values if value})


def _owner_values(host: dict[str, Any]) -> list[str]:
    fields = ["owner", "custodian", "ap_owner", "sys_admin", "user_unit", "department"]
    return sorted({str(host.get(field)).strip() for field in fields if _filled(host.get(field))})


def _status_summary(hosts: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for host in hosts:
        status = str(host.get("status") or "unknown")
        summary[status] = summary.get(status, 0) + 1
    return summary


def _system_rows(hosts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for host in hosts:
        system_key = _host_system_key(host)
        display_name = _display_system_name(host)
        bucket_key = system_key or f"unclassified:{display_name}"
        item = grouped.setdefault(
            bucket_key,
            {
                "key": bucket_key,
                "display_name": display_name,
                "is_classified": bool(system_key),
                "host_count": 0,
                "formal_count": 0,
                "draft_count": 0,
                "missing_owner": 0,
                "missing_notification": 0,
                "missing_ports": 0,
                "owners": set(),
                "hosts": [],
            },
        )
        item["host_count"] += 1
        status = str(host.get("status") or "")
        if status in DRAFT_STATUSES:
            item["draft_count"] += 1
        elif status not in RETIRED_STATUSES:
            item["formal_count"] += 1
        if not _has_any(host, ["owner", "custodian", "ap_owner", "sys_admin"]):
            item["missing_owner"] += 1
        if not _has_any(host, ["owner", "custodian", "ap_owner", "sys_admin", "user_unit", "department"]):
            item["missing_notification"] += 1
        if not _host_ports(host):
            item["missing_ports"] += 1
        item["owners"].update(_owner_values(host))
        item["hosts"].append(host)

    rows = []
    for item in grouped.values():
        rows.append(
            {
                **{key: value for key, value in item.items() if key not in {"owners", "hosts"}},
                "owners": sorted(item["owners"])[:5],
                "hosts": item["hosts"][:12],
            }
        )
    return sorted(rows, key=lambda row: (not row["is_classified"], -row["host_count"], row["display_name"]))


def _topology_center_for_row(row: dict[str, Any], dependency_systems: list[dict[str, Any]]) -> str:
    key = str(row.get("key") or "").strip()
    display_name = str(row.get("display_name") or "").strip()
    host_refs = {value for host in row.get("hosts", []) for value in _host_identity_values(host)}
    if not key and not display_name and not host_refs:
        return ""

    for system in dependency_systems:
        system_id = str(system.get("system_id") or "").strip()
        if system_id and system_id == key:
            return system_id

    for system in dependency_systems:
        system_id = str(system.get("system_id") or "").strip()
        system_name = str(system.get("display_name") or "").strip()
        if system_id and display_name and system_name == display_name:
            return system_id

    for system in dependency_systems:
        system_id = str(system.get("system_id") or "").strip()
        refs = {str(ref or "").strip() for ref in system.get("host_refs") or [] if str(ref or "").strip()}
        if system_id and refs and refs.intersection(host_refs):
            return system_id

    return display_name or key


def _selected_system(rows: list[dict[str, Any]], dependency_systems: list[dict[str, Any]], selected: str = "") -> dict[str, Any]:
    selected_text = (selected or "").strip().lower()
    current = None
    if selected_text:
        for row in rows:
            if selected_text in str(row["key"]).lower() or selected_text in str(row["display_name"]).lower():
                current = row
                break
    if current is None:
        current = next((row for row in rows if row.get("is_classified")), None) or (rows[0] if rows else {})
    hosts = current.get("hosts", []) if current else []
    ports = sorted({port for host in hosts for port in _host_ports(host)})
    owners = sorted({owner for host in hosts for owner in _owner_values(host)})
    return {
        "key": current.get("key", ""),
        "topology_center": _topology_center_for_row(current, dependency_systems) if current else "",
        "display_name": current.get("display_name", "未選擇"),
        "host_count": current.get("host_count", 0),
        "formal_count": current.get("formal_count", 0),
        "draft_count": current.get("draft_count", 0),
        "missing_owner": current.get("missing_owner", 0),
        "missing_notification": current.get("missing_notification", 0),
        "missing_ports": current.get("missing_ports", 0),
        "owners": owners[:8],
        "ports": ports[:10],
        "hosts": hosts[:8],
    }


def cmdb_relationship_overview(selected_system: str = "") -> dict[str, Any]:
    """Build an executive CMDB quality and relationship coverage summary."""
    hosts = host_service.list_hosts(page=1, page_size=10000)["items"]
    hosts = [host for host in hosts if str(host.get("status") or "") not in RETIRED_STATUSES]
    total = len(hosts)
    formal_count = sum(1 for host in hosts if str(host.get("status") or "") not in DRAFT_STATUSES)
    draft_count = sum(1 for host in hosts if str(host.get("status") or "") in DRAFT_STATUSES)
    owner_count = sum(1 for host in hosts if _has_any(host, ["owner", "custodian", "ap_owner", "sys_admin"]))
    system_count = sum(1 for host in hosts if _host_system_key(host))
    notification_count = sum(1 for host in hosts if _has_any(host, ["owner", "custodian", "ap_owner", "sys_admin", "user_unit", "department"]))
    port_count = sum(1 for host in hosts if _host_ports(host))
    ip_count = sum(1 for host in hosts if _has_any(host, ["ip", "ip_addresses"]))

    system_rows = _system_rows(hosts)
    dependency_systems = _safe_docs("dependency_systems", {"_id": 0, "system_id": 1, "display_name": 1, "owner": 1, "host_refs": 1})
    dependency_relations = _safe_docs("dependency_relations", {"_id": 0, "from_system": 1, "to_system": 1, "source": 1})
    for row in system_rows:
        row["topology_center"] = _topology_center_for_row(row, dependency_systems)

    gaps = [
        {
            "key": "missing_owner",
            "label": "缺 owner / 保管者",
            "count": max(total - owner_count, 0),
            "action": "補 owner、保管者或 AP owner，異常時才能追責任窗口。",
        },
        {
            "key": "missing_system",
            "label": "缺系統關聯",
            "count": max(total - system_count, 0),
            "action": "補 system_name、group_name 或 APID，才能納入核心影響圖。",
        },
        {
            "key": "missing_notification",
            "label": "缺通知依據",
            "count": max(total - notification_count, 0),
            "action": "補使用單位、owner 或通知群組，讓匯出名單可用。",
        },
        {
            "key": "missing_port",
            "label": "缺服務 / Port",
            "count": max(total - port_count, 0),
            "action": "補服務或 Port，讓關聯圖能判斷實際影響路徑。",
        },
    ]

    return {
        "summary": {
            "total": total,
            "formal_count": formal_count,
            "draft_count": draft_count,
            "ip_count": ip_count,
            "dependency_system_count": len(dependency_systems),
            "dependency_relation_count": len(dependency_relations),
            "status_counts": _status_summary(hosts),
        },
        "coverage": {
            "system": {"label": "系統關聯率", "count": system_count, "total": total, "pct": _pct(system_count, total)},
            "owner": {"label": "owner 完整率", "count": owner_count, "total": total, "pct": _pct(owner_count, total)},
            "notification": {"label": "通知依據完整率", "count": notification_count, "total": total, "pct": _pct(notification_count, total)},
            "service_port": {"label": "服務 / Port 完整率", "count": port_count, "total": total, "pct": _pct(port_count, total)},
        },
        "gaps": gaps,
        "systems": system_rows[:12],
        "selected_system": _selected_system(system_rows, dependency_systems, selected_system),
    }
