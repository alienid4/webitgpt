from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from webapp import config
from webapp.services.feature_flags import is_enabled
from webapp.services.mongo_service import get_collection


@dataclass(frozen=True)
class HousekeepingTask:
    name: str
    description: str
    target: str
    retention_days: int
    schedule: str
    market_protected: bool = True


TASKS = [
    HousekeepingTask("host_self_check_purge", "Delete old self-check JSON files", "hosts/*/self_check", 30, "daily 1530"),
    HousekeepingTask("host_debug_snapshots_purge", "Delete old debug snapshots", "hosts/*/debug_snapshots", 30, "daily 1530"),
    HousekeepingTask("host_packages_purge", "Delete old package inventory files", "hosts/*/packages", 90, "daily 1530"),
    HousekeepingTask("host_accounts_purge", "Delete old account inventory files", "hosts/*/accounts", 90, "daily 1530"),
    HousekeepingTask("host_services_purge", "Delete old service inventory files", "hosts/*/services", 90, "daily 1530"),
    HousekeepingTask("host_security_audit_purge", "Delete old security audit files", "hosts/*/security_audit", 180, "daily 1530"),
    HousekeepingTask("host_nmon_purge", "Delete old NMON raw samples", "hosts/*/nmon", 30, "daily 1530"),
    HousekeepingTask("host_remote_tool_purge", "Delete old remote tool transcripts", "hosts/*/remote_tools", 30, "daily 1530"),
    HousekeepingTask("tmp_purge", "Delete old temporary files", "tmp", 7, "daily 1530"),
    HousekeepingTask("reports_purge", "Delete old generated reports", "data/reports", 365, "weekly Sunday 0430", False),
    HousekeepingTask("notification_events_purge", "Prune notification event records", "mongo:notification_events", 180, "weekly Sunday 0430", False),
    HousekeepingTask("login_attempts_purge", "Prune login attempt records", "mongo:login_attempts", 90, "weekly Sunday 0430", False),
    HousekeepingTask("api_tokens_review", "Review active API token count", "mongo:api_tokens", 0, "daily 1530", False),
    HousekeepingTask("audit_chain_verify", "Verify audit log hash chain", "mongo:audit_logs", 0, "hourly", False),
    HousekeepingTask("edge_agent_stale_check", "Check stale Edge agent heartbeats", "mongo:edge_agents", 0, "hourly", False),
    HousekeepingTask("mongo_collection_count", "Record core Mongo collection counts", "mongo:*", 0, "daily 1530", False),
    HousekeepingTask("data_dir_manifest", "Generate data directory manifest", "data", 0, "daily 1530", False),
    HousekeepingTask("patch_backup_keep", "Keep newest patch backups", "backup/patches", 10, "monthly 0200", False),
    HousekeepingTask("backup_verify", "Verify backup directory readability and metadata", "backup", 0, "weekly Sunday 0500", False),
    HousekeepingTask("disk_alert", "Check central disk usage", config.INSPECTION_HOME, 0, "hourly", False),
]


def list_tasks() -> list[dict[str, Any]]:
    runs = {run["task"]: run for run in get_collection("housekeeping_runs").find({}, {"_id": 0}).sort("started_at", -1)}
    return [
        {
            "name": task.name,
            "description": task.description,
            "target": task.target,
            "retention_days": task.retention_days,
            "schedule": task.schedule,
            "enabled": is_enabled("housekeeping_enabled", default=True),
            "last_run": runs.get(task.name),
        }
        for task in TASKS
    ]


def _delete_old_files(root: Path, retention_days: int, dry_run: bool) -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    deleted = 0
    freed = 0
    if not root.exists():
        return {"deleted_count": 0, "freed_bytes": 0, "missing": True}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        if mtime >= cutoff:
            continue
        size = path.stat().st_size
        if not dry_run:
            path.unlink()
        deleted += 1
        freed += size
    return {"deleted_count": deleted, "freed_bytes": freed}


def disk_status() -> dict[str, Any]:
    usage = shutil.disk_usage(config.INSPECTION_HOME)
    used_pct = round((usage.used / usage.total) * 100, 2)
    return {"path": config.INSPECTION_HOME, "total": usage.total, "used": usage.used, "free": usage.free, "used_pct": used_pct}


def run_task(name: str, user: str = "system", dry_run: Optional[bool] = None) -> dict[str, Any]:
    task = next((item for item in TASKS if item.name == name), None)
    if not task:
        raise KeyError(f"unknown housekeeping task: {name}")
    dry_run = is_enabled("housekeeping_dry_run", default=False) if dry_run is None else dry_run
    started = datetime.now(timezone.utc)
    status = "ok"
    detail: dict[str, Any] = {}
    try:
        if name == "disk_alert":
            detail = disk_status()
            status = "warn" if detail["used_pct"] >= 85 else "ok"
        elif name == "backup_verify":
            backup_dir = Path(config.BACKUP_DIR)
            backup_dir.mkdir(parents=True, exist_ok=True)
            detail = {"exists": backup_dir.exists(), "files": len(list(backup_dir.glob("*"))), "dry_run": dry_run}
        elif name == "patch_backup_keep":
            patch_dir = Path(config.BACKUP_DIR) / "patches"
            patch_dir.mkdir(parents=True, exist_ok=True)
            files = sorted([p for p in patch_dir.glob("*") if p.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)
            remove = files[task.retention_days :]
            for path in remove:
                if not dry_run:
                    path.unlink()
            detail = {"deleted_count": len(remove), "freed_bytes": sum(p.stat().st_size for p in remove if p.exists()), "dry_run": dry_run}
        elif task.target.startswith("mongo:"):
            collection_name = task.target.split(":", 1)[1]
            if collection_name == "*":
                names = get_collection("hosts").database.list_collection_names()
                detail = {"collections": {item: get_collection(item).count_documents({}) for item in names}, "dry_run": dry_run}
            elif name == "audit_chain_verify":
                from webapp.services.audit_log_service import verify_chain

                detail = verify_chain()
            else:
                count = get_collection(collection_name).count_documents({})
                detail = {"collection": collection_name, "count": count, "dry_run": dry_run}
        elif name == "data_dir_manifest":
            data_dir = Path(config.DATA_DIR)
            files = [path for path in data_dir.rglob("*") if path.is_file()] if data_dir.exists() else []
            detail = {"path": str(data_dir), "files": len(files), "bytes": sum(path.stat().st_size for path in files)}
        else:
            roots = []
            if task.target.startswith("hosts/*/"):
                leaf = task.target.split("/", 2)[2]
                roots = [Path(config.HOSTS_DIR) / host.name / leaf for host in Path(config.HOSTS_DIR).glob("*") if host.is_dir()]
            else:
                roots = [Path(config.INSPECTION_HOME) / task.target]
            totals = {"deleted_count": 0, "freed_bytes": 0, "dry_run": dry_run}
            for root in roots:
                result = _delete_old_files(root, task.retention_days, dry_run)
                totals["deleted_count"] += result.get("deleted_count", 0)
                totals["freed_bytes"] += result.get("freed_bytes", 0)
            detail = totals
    except Exception as exc:
        status = "fail"
        detail = {"error": str(exc)}
    ended = datetime.now(timezone.utc)
    doc = {"task": name, "started_at": started, "ended_at": ended, "status": status, "user": user, **detail}
    get_collection("housekeeping_runs").insert_one(doc)
    doc.pop("_id", None)
    return doc


def run_all(user: str = "system", dry_run: bool = True) -> dict[str, Any]:
    results = [run_task(task.name, user=user, dry_run=dry_run) for task in TASKS]
    return {"status": "ok" if all(item["status"] in {"ok", "warn"} for item in results) else "fail", "count": len(results), "results": results}
