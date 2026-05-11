from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from webapp.services.host_service import list_hosts
from webapp.services.mask_service import mask_dict
from webapp.services.mongo_service import get_collection


def save_vcenter(name: str, url: str, username: str, password: str, user: str) -> dict[str, Any]:
    doc = {
        "name": name.strip(),
        "url": url.strip(),
        "username": username.strip(),
        "password": password,
        "enabled": True,
        "updated_at": datetime.now(timezone.utc),
        "updated_by": user,
    }
    get_collection("vmware_credentials").update_one({"name": doc["name"]}, {"$set": doc}, upsert=True)
    return mask_dict(doc)


def list_vcenters() -> list[dict[str, Any]]:
    return [mask_dict(doc) for doc in get_collection("vmware_credentials").find({}, {"_id": 0})]


def vmware_inventory() -> dict[str, Any]:
    hosts = list_hosts(filters={"host_type": "vmware_host"}, page=1, page_size=1000)["items"]
    vms = list_hosts(filters={"host_type": "vmware_vm"}, page=1, page_size=1000)["items"]
    vcenters = list_hosts(filters={"host_type": "vmware_vcenter"}, page=1, page_size=1000)["items"]
    return {"vcenters": vcenters, "hosts": hosts, "vms": vms, "credentials": list_vcenters()}


def platform_status() -> dict[str, Any]:
    all_hosts = list_hosts(page=1, page_size=10000)["items"]
    counts: dict[str, int] = {}
    for host in all_hosts:
        counts[host.get("host_type", "unknown")] = counts.get(host.get("host_type", "unknown"), 0) + 1
    return {
        "counts": counts,
        "aix_ready": True,
        "as400_ready": True,
        "vmware_ready": bool(list_vcenters()),
        "read_only_mode": True,
    }
