from __future__ import annotations

import shutil
from pathlib import Path

from pymongo import MongoClient


ASSET_COLLECTIONS = [
    "hosts",
    "inspection_results",
    "nmon_data",
    "compliance_findings",
    "inventory_snapshots",
    "inventory_runs",
    "account_inventory",
    "software_inventory",
    "services_inventory",
    "ssh_keys_inventory",
]


def main() -> None:
    db = MongoClient("mongodb://localhost:27017")["webitgpt"]
    query = {
        "$or": [
            {"hostname": {"$regex": "^(func|manual)-hw-"}},
            {"asset_seq": {"$regex": "^HW-9(6|7|8|9)"}},
        ]
    }
    assets = [
        host["asset_seq"]
        for host in db.hosts.find(query, {"asset_seq": 1})
        if host.get("asset_seq")
    ]
    print(f"assets_to_cleanup={assets}")
    for collection_name in ASSET_COLLECTIONS:
        result = db[collection_name].delete_many({"asset_seq": {"$in": assets}})
        print(f"{collection_name}={result.deleted_count}")
    print(f"users={db.users.delete_many({'username': 'validation-viewer'}).deleted_count}")
    print(f"saved_views={db.saved_views.delete_many({'name': {'$regex': '^validation-'}}).deleted_count}")

    host_root = Path("/opt/webitgpt/data/hosts")
    for asset_seq in assets:
        path = host_root / asset_seq
        if path.exists():
            shutil.rmtree(path)
            print(f"removed_dir={path}")


if __name__ == "__main__":
    main()
