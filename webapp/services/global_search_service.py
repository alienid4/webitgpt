from __future__ import annotations

import re
from typing import Any

from webapp.services.mongo_service import get_collection


DRAFT_STATUSES = {"draft", "pending_ip", "pending_data", "pending_deploy", "pending_retire"}

HOST_SEARCH_FIELDS = [
    "asset_seq",
    "hostname",
    "ip",
    "ip_addresses",
    "network_segments",
    "asset_name",
    "system_name",
    "apid",
    "owner",
    "custodian",
    "sys_admin",
    "user",
    "user_unit",
    "department",
    "group_name",
    "note",
]

ASSET_POOL_SEARCH_FIELDS = [
    "object_type",
    "asset_seq",
    "asset_name",
    "apid",
    "owner",
    "custodian",
    "host_link.hostname",
    "host_link.ip",
    "data.asset_seq",
    "data.asset_name",
    "data.hostname",
    "data.ip",
    "data.apid",
    "data.owner",
    "data.custodian",
    "data.user",
    "data.user_unit",
    "data.department",
    "data.software_name",
    "data.app_name",
    "data.account",
    "data.name",
]

ASSET_POOL_TYPE_LABELS = {
    "hardware": "主機證據",
    "data": "資料資產",
    "software": "軟體 / AP",
    "people": "人員窗口",
    "unknown": "待分類",
}


def _regex_filter(fields: list[str], query: str) -> dict[str, Any]:
    escaped = re.escape(query.strip())
    return {"$or": [{field: {"$regex": escaped, "$options": "i"}} for field in fields]}


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item not in (None, ""))
    return str(value)


def _host_title(host: dict[str, Any]) -> str:
    return _clean(host.get("asset_name")) or _clean(host.get("hostname")) or _clean(host.get("asset_seq")) or "未命名資產"


def _host_subtitle(host: dict[str, Any]) -> str:
    parts = [_clean(host.get("hostname")), _clean(host.get("ip")), _clean(host.get("os"))]
    return " / ".join(part for part in parts if part)


def _host_owner(host: dict[str, Any]) -> str:
    for key in ("owner", "custodian", "sys_admin", "user", "user_unit"):
        value = _clean(host.get(key))
        if value:
            return value
    return ""


def _host_item(host: dict[str, Any], bucket: str) -> dict[str, Any]:
    key = _clean(host.get("hostname")) or _clean(host.get("asset_seq"))
    return {
        "type": bucket,
        "title": _host_title(host),
        "subtitle": _host_subtitle(host),
        "meta": _host_owner(host),
        "badge": _clean(host.get("status")) or ("draft" if bucket == "draft_hosts" else "active"),
        "endpoint": "api_hosts.host_edit_page",
        "params": {"asset_seq": key},
    }


def _asset_pool_title(item: dict[str, Any]) -> str:
    data = item.get("data") or {}
    return (
        _clean(item.get("asset_name"))
        or _clean(data.get("asset_name"))
        or _clean(data.get("software_name"))
        or _clean(data.get("app_name"))
        or _clean(data.get("name"))
        or _clean(item.get("asset_seq"))
        or "未命名資產池資料"
    )


def _asset_pool_subtitle(item: dict[str, Any]) -> str:
    data = item.get("data") or {}
    parts = [
        ASSET_POOL_TYPE_LABELS.get(_clean(item.get("object_type")), _clean(item.get("object_type"))),
        _clean(item.get("apid")) or _clean(data.get("apid")),
        _clean(data.get("hostname")) or _clean((item.get("host_link") or {}).get("hostname")),
        _clean(data.get("ip")) or _clean((item.get("host_link") or {}).get("ip")),
    ]
    return " / ".join(part for part in parts if part)


def _asset_pool_item(item: dict[str, Any]) -> dict[str, Any]:
    object_type = _clean(item.get("object_type")) or "unknown"
    asset_seq = _clean(item.get("asset_seq"))
    data = item.get("data") or {}
    return {
        "type": "asset_pool",
        "title": _asset_pool_title(item),
        "subtitle": _asset_pool_subtitle(item),
        "meta": _clean(item.get("owner")) or _clean(item.get("custodian")) or _clean(data.get("owner")) or _clean(data.get("custodian")),
        "badge": ASSET_POOL_TYPE_LABELS.get(object_type, object_type),
        "endpoint": "api_hosts.cmdb_asset_pool_edit_page",
        "params": {"object_type": object_type, "asset_seq": asset_seq},
    }


def _find_hosts(query: str, limit: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    projection = {field: 1 for field in HOST_SEARCH_FIELDS}
    projection.update({"status": 1, "os": 1, "host_type": 1})
    docs = list(
        get_collection("hosts")
        .find(_regex_filter(HOST_SEARCH_FIELDS, query), projection)
        .sort("updated_at", -1)
        .limit(limit * 4)
    )
    formal: list[dict[str, Any]] = []
    drafts: list[dict[str, Any]] = []
    for host in docs:
        if _clean(host.get("status")) in DRAFT_STATUSES:
            drafts.append(_host_item(host, "draft_hosts"))
        else:
            formal.append(_host_item(host, "formal_hosts"))
    return formal[:limit], drafts[:limit]


def _find_asset_pool(query: str, limit: int) -> list[dict[str, Any]]:
    docs = (
        get_collection("cmdb_asset_pool")
        .find(
            _regex_filter(ASSET_POOL_SEARCH_FIELDS, query),
            {
                "object_type": 1,
                "asset_seq": 1,
                "asset_name": 1,
                "apid": 1,
                "owner": 1,
                "custodian": 1,
                "host_link": 1,
                "data": 1,
                "updated_at": 1,
            },
        )
        .sort("updated_at", -1)
        .limit(limit)
    )
    return [_asset_pool_item(doc) for doc in docs]


def search_data(query: str, limit: int = 8) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return {"formal_hosts": [], "draft_hosts": [], "asset_pool": [], "total": 0}
    formal, drafts = _find_hosts(query, limit)
    asset_pool = _find_asset_pool(query, limit)
    total = len(formal) + len(drafts) + len(asset_pool)
    return {
        "formal_hosts": formal,
        "draft_hosts": drafts,
        "asset_pool": asset_pool,
        "total": total,
    }
