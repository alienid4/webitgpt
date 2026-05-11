from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from webapp import config
from webapp.services import cmdb_service, ipam_schedule_service


def main() -> int:
    config.ensure_runtime_dirs()
    force = "--force" in sys.argv
    if not force:
        should_run, reason = ipam_schedule_service.should_run_now()
        if not should_run:
            print(json.dumps({"status": "skip", "reason": reason, "schedule": ipam_schedule_service.get_schedule()}, default=str, ensure_ascii=False))
            return 0
    reports = []
    for network in cmdb_service.list_networks():
        cidr = network.get("cidr")
        if not cidr:
            continue
        reports.append(cmdb_service.run_network_reconcile(cidr, user="system-weekly-ipam"))
    result = {"status": "ok", "count": len(reports), "reports": reports, "schedule": ipam_schedule_service.get_schedule()}
    ipam_schedule_service.mark_run(result)
    print(json.dumps(result, default=str, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
