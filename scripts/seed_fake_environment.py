from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from webapp import config
from webapp.services import host_service
from webapp.services.host_schema import normalize_host_doc
from webapp.services.mongo_service import get_collection


DEFAULT_BATCH = "codex_fake_50_20260513"
BASE_CIDR_PREFIX = "10.250"
FAKE_RUN_ID = f"topo-{DEFAULT_BATCH}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _network_docs(batch: str) -> list[dict[str, Any]]:
    now = _now()
    dcs = ["dunan", "neihu", "banciao"]
    envs = ["DEV", "TEST", "UAT", "PROD", "BACKUP"]
    return [
        {
            "name": f"測試網段 {idx + 1:02d}",
            "cidr": f"{BASE_CIDR_PREFIX}.{idx}.0/24",
            "dc": dcs[idx % len(dcs)],
            "environment": envs[idx % len(envs)],
            "purpose": f"假資料壓力測試 batch={batch}",
            "vlan": f"9{idx:03d}",
            "gateway": f"{BASE_CIDR_PREFIX}.{idx}.1",
            "dns": "192.168.1.221",
            "reserved_ips": [f"{BASE_CIDR_PREFIX}.{idx}.1-{BASE_CIDR_PREFIX}.{idx}.10"],
            "reserved_note": "測試資料保留 gateway 與前 10 個 IP",
            "created_at": now,
            "updated_at": now,
            "updated_by": "codex",
            "metadata": {"test_batch": batch, "fake": True},
        }
        for idx in range(10)
    ]


def _system_docs(batch: str) -> list[dict[str, Any]]:
    now = _now()
    categories = ["AP", "DB", "MQ", "Cache", "Gateway"]
    tiers = ["A", "B", "C", "B", "A"]
    docs = []
    for idx in range(10):
        docs.append(
            {
                "system_id": f"SYS-FAKE-{idx + 1:02d}",
                "display_name": f"測試系統 {idx + 1:02d}",
                "tier": tiers[idx % len(tiers)],
                "category": categories[idx % len(categories)],
                "description": f"Codex 產生的拓樸測試系統，batch={batch}",
                "owner": f"測試負責人 {idx + 1:02d}",
                "host_refs": [f"fake-sys{idx + 1:02d}-node{node:02d}" for node in range(1, 6)],
                "external": False,
                "metadata": {"test_batch": batch, "fake": True},
                "created_at": now,
                "updated_at": now,
                "updated_by": "codex",
            }
        )
    return docs


def _host_docs(batch: str) -> list[dict[str, Any]]:
    host_kinds = [
        ("linux", "Rocky Linux 9.7", "ssh", "rocky"),
        ("linux", "Debian 13", "ssh", "debian"),
        ("windows", "Windows Server 2022", "winrm", "win"),
        ("aix", "AIX 7.3", "ssh_raw", "aix"),
        ("as400", "IBM i 7.5", "as400_api", "as400"),
        ("vmware_vm", "VMware VM", "vcenter_api", "other"),
    ]
    dcs = ["dunan", "neihu", "banciao"]
    envs = ["DEV", "TEST", "UAT", "PROD", "BACKUP"]
    docs = []
    for idx in range(50):
        system_idx = idx // 5
        node_idx = idx % 5
        network_idx = idx % 10
        host_type, os_name, connection, os_group = host_kinds[idx % len(host_kinds)]
        ip = f"{BASE_CIDR_PREFIX}.{network_idx}.{11 + (idx // 10) * 10 + node_idx}"
        hostname = f"fake-sys{system_idx + 1:02d}-node{node_idx + 1:02d}"
        doc = {
            "division": "測試事業群",
            "department": f"測試部門 {system_idx + 1:02d}",
            "asset_seq": f"HW-FAKE-{idx + 1:05d}",
            "status": "draft",
            "group_name": f"H{(idx % 9) + 1}",
            "apid": f"FAKE-AP-{system_idx + 1:02d}",
            "asset_name": f"測試資產 {idx + 1:02d}",
            "device_type": "虛擬主機" if host_type != "network_device" else "網路設備",
            "device_model": os_name,
            "asset_usage": f"測試系統 {system_idx + 1:02d} 節點",
            "location": f"測試機房 {dcs[network_idx % len(dcs)]}",
            "rack_no": f"T{network_idx + 1:02d}",
            "quantity": 1,
            "owner": f"系統窗口 {system_idx + 1:02d}",
            "environment": envs[network_idx % len(envs)],
            "hostname": hostname,
            "os": os_name,
            "bigip": "",
            "hardware_seq": f"FAKE-SN-{idx + 1:05d}",
            "ip": ip,
            "ip_addresses": [ip],
            "network_segments": [f"{BASE_CIDR_PREFIX}.{network_idx}.0/24"],
            "custodian": f"保管人 {idx + 1:02d}",
            "sys_admin": "sysinfra",
            "user": f"使用者 {idx + 1:02d}",
            "user_unit": f"測試部門 {system_idx + 1:02d}",
            "note": f"Codex 假資料，可用 scripts/seed_fake_environment.py delete --batch {batch} 清除",
            "company": "example-corp",
            "integrity": (idx % 3) + 1,
            "confidentiality": ((idx + 1) % 3) + 1,
            "availability": ((idx + 2) % 3) + 1,
            "host_type": host_type,
            "dc": dcs[network_idx % len(dcs)],
            "connection": connection,
            "ssh_user": "sysinfra",
            "ssh_port": 22,
            "nmon_enabled": False,
            "tier": ["critical", "high", "medium", "low"][idx % 4],
            "ap_owner": f"AP 負責人 {system_idx + 1:02d}",
            "system_name": f"測試系統 {system_idx + 1:02d}",
            "os_group": os_group,
            "import_source": "codex_fake_seed",
            "extensions": {"test_batch": batch, "fake": True},
        }
        docs.append(normalize_host_doc(doc))
    return docs


def seed(batch: str) -> dict[str, Any]:
    delete(batch)
    now = _now()
    for network in _network_docs(batch):
        created_at = network.pop("created_at")
        get_collection("ipam_networks").update_one(
            {"cidr": network["cidr"]},
            {"$set": network, "$setOnInsert": {"created_at": created_at}},
            upsert=True,
        )
    for system in _system_docs(batch):
        created_at = system.pop("created_at")
        get_collection("dependency_systems").update_one(
            {"system_id": system["system_id"]},
            {"$set": system, "$setOnInsert": {"created_at": created_at}},
            upsert=True,
        )
    hosts = _host_docs(batch)
    for host in hosts:
        host_service.upsert_host(host, user="codex")

    relations = []
    for idx, host in enumerate(hosts):
        target = hosts[(idx + 1) % len(hosts)]
        local_port = str(41000 + idx)
        remote_port = ["22", "80", "443", "1521", "3306", "5432", "8002", "9444"][idx % 8]
        relations.append(
            {
                "from_system": host["hostname"],
                "to_system": target["hostname"],
                "rel_type": "connects_to",
                "source": "auto",
                "confidence": 0.8,
                "description": f"假資料 ss -tunp 關聯 batch={batch}",
                "evidence": {
                    "run_id": FAKE_RUN_ID,
                    "caller_hostname": host["hostname"],
                    "caller_ip": host["ip"],
                    "last_local_ip": host["ip"],
                    "last_local_port": local_port,
                    "last_remote_ip": target["ip"],
                    "last_remote_port": remote_port,
                    "local_ports": [local_port],
                    "remote_ports": [remote_port],
                    "process_name": ["sshd", "nginx", "java", "python", "db2sysc"][idx % 5],
                    "seen_count": (idx % 7) + 1,
                    "last_seen_at": now,
                },
                "metadata": {"test_batch": batch, "fake": True},
                "created_at": now,
                "updated_at": now,
                "updated_by": "codex",
            }
        )
    get_collection("dependency_relations").delete_many({"metadata.test_batch": batch})
    if relations:
        get_collection("dependency_relations").insert_many(relations)
    get_collection("dependency_collect_runs").update_one(
        {"run_id": FAKE_RUN_ID},
        {
            "$set": {
                "run_id": FAKE_RUN_ID,
                "status": "success",
                "collector": "fake ss -tunp",
                "started_at": now,
                "finished_at": now,
                "started_by": "codex",
                "host_count": len(hosts),
                "edge_count": len(relations),
                "errors": [],
                "snapshot_replaced": False,
                "metadata": {"test_batch": batch, "fake": True},
            }
        },
        upsert=True,
    )
    return {"batch": batch, "hosts": len(hosts), "networks": 10, "systems": 10, "relations": len(relations), "run_id": FAKE_RUN_ID}


def delete(batch: str) -> dict[str, Any]:
    host_query = {"$or": [{"extensions.test_batch": batch}, {"import_source": "codex_fake_seed"}]}
    fake_hosts = list(get_collection("hosts").find(host_query, {"asset_seq": 1, "hostname": 1}))
    asset_seqs = [item.get("asset_seq") for item in fake_hosts if item.get("asset_seq")]
    hostnames = [item.get("hostname") for item in fake_hosts if item.get("hostname")]
    deleted_hosts = get_collection("hosts").delete_many(host_query).deleted_count
    for asset_seq in asset_seqs:
        if asset_seq:
            _remove_path(Path(config.HOSTS_DIR) / asset_seq)
    for hostname in hostnames:
        if hostname:
            _remove_path(Path(config.HOSTNAME_LINK_DIR) / hostname)
    deleted = {
        "hosts": deleted_hosts,
        "networks": get_collection("ipam_networks").delete_many({"metadata.test_batch": batch}).deleted_count,
        "systems": get_collection("dependency_systems").delete_many({"metadata.test_batch": batch}).deleted_count,
        "relations": get_collection("dependency_relations").delete_many({"metadata.test_batch": batch}).deleted_count,
        "collect_runs": get_collection("dependency_collect_runs").delete_many({"metadata.test_batch": batch}).deleted_count,
        "reconcile_reports": get_collection("dependency_reconcile_reports").delete_many({"started_by": "codex-fake"}).deleted_count,
    }
    for collection in ("inspection_results", "diagnostic_results", "deep_check_jobs", "deep_check_reports", "accounts_inventory", "software_inventory"):
        if asset_seqs:
            deleted[collection] = get_collection(collection).delete_many({"asset_seq": {"$in": asset_seqs}}).deleted_count
    return {"batch": batch, "deleted": deleted}


def status(batch: str) -> dict[str, Any]:
    return {
        "batch": batch,
        "hosts": get_collection("hosts").count_documents({"extensions.test_batch": batch}),
        "networks": get_collection("ipam_networks").count_documents({"metadata.test_batch": batch}),
        "systems": get_collection("dependency_systems").count_documents({"metadata.test_batch": batch}),
        "relations": get_collection("dependency_relations").count_documents({"metadata.test_batch": batch}),
        "collect_runs": get_collection("dependency_collect_runs").count_documents({"metadata.test_batch": batch}),
    }


def _remove_path(path: Path) -> None:
    if path.exists() or path.is_symlink():
        if path.is_dir() and not path.is_symlink():
            for child in path.iterdir():
                _remove_path(child)
            path.rmdir()
        else:
            path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed or delete reversible fake CMDB/topology data.")
    parser.add_argument("action", choices=["seed", "delete", "status"])
    parser.add_argument("--batch", default=DEFAULT_BATCH)
    args = parser.parse_args()
    if args.action == "seed":
        result = seed(args.batch)
    elif args.action == "delete":
        result = delete(args.batch)
    else:
        result = status(args.batch)
    print(result)


if __name__ == "__main__":
    main()
