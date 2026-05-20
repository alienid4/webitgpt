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
    keep_count: int = 0


TASKS = [
    HousekeepingTask("host_self_check_purge", "主機自檢檔保留 90 天。", "hosts/*/self_check", 90, "daily 1530"),
    HousekeepingTask("host_debug_snapshots_purge", "DEBUG 快照含大量原始輸出，只保留 30 天。", "hosts/*/debug_snapshots", 30, "daily 1530"),
    HousekeepingTask("host_deep_check_purge", "L3 深度檢查報告保留 365 天。", "hosts/*/deep_check", 365, "daily 1530"),
    HousekeepingTask("host_packages_purge", "軟體盤點主機檔保留 365 天。", "hosts/*/packages", 365, "daily 1530"),
    HousekeepingTask("host_accounts_purge", "帳號盤點主機檔保留 365 天，支援前後次盤點比較。", "hosts/*/accounts", 365, "daily 1530"),
    HousekeepingTask("host_services_purge", "服務盤點主機檔保留 365 天。", "hosts/*/services", 365, "daily 1530"),
    HousekeepingTask("host_security_audit_purge", "資安稽核主機檔保留 365 天。", "hosts/*/security_audit", 365, "daily 1530"),
    HousekeepingTask("host_nmon_purge", "每台主機的 NMON raw 檔保留 180 天；彙整後樣本另存 Mongo。", "hosts/*/nmon", 180, "daily 1530"),
    HousekeepingTask("host_remote_tool_purge", "遠端工具 transcript 保留 30 天。", "hosts/*/remote_tools", 30, "daily 1530"),
    HousekeepingTask("tmp_purge", "清理 /opt/webitgpt/tmp 暫存檔，保留 7 天。", "tmp", 7, "daily 1530"),
    HousekeepingTask("deploy_tmp_purge", "清理 /tmp 內 webitgpt patch 解壓目錄與 tarball。", "/tmp", 1, "after install / daily 1530", False),
    HousekeepingTask("code_cache_purge", "清理正式程式碼目錄內的 __pycache__、.pytest_cache 等可重建快取。", "code-cache", 0, "after install / daily 1530", False),
    HousekeepingTask("reports_purge", "產出報表保留 365 天。", "data/reports", 365, "weekly Sunday 0430", False),
    HousekeepingTask("logs_purge", "應用程式 log 檔保留 90 天。", "logs", 90, "daily 1530", False),
    HousekeepingTask("debug_bundle_purge", "AI debug bundle 與去識別化報告保留 30 天。", "debug", 30, "daily 1530", False),
    HousekeepingTask("nmon_raw_files_purge", "中央 NMON raw file pipeline 檔案保留 180 天。", "data/nmon_raw", 180, "daily 1530", False),
    HousekeepingTask("mongo_nmon_data_purge", "Mongo nmon_data 採樣保留 400 天，足夠做月報與年內趨勢。", "mongo:nmon_data", 400, "weekly Sunday 0430", False),
    HousekeepingTask("mongo_nmon_raw_files_purge", "Mongo nmon_raw_files metadata 保留 400 天。", "mongo:nmon_raw_files", 400, "weekly Sunday 0430", False),
    HousekeepingTask("mongo_inventory_runs_purge", "盤點 run 歷史保留 400 天。", "mongo:inventory_runs", 400, "weekly Sunday 0430", False),
    HousekeepingTask("mongo_inventory_snapshots_purge", "盤點 snapshot 保留 400 天，支援差異報告。", "mongo:inventory_snapshots", 400, "weekly Sunday 0430", False),
    HousekeepingTask("mongo_deep_check_jobs_purge", "L3 job 狀態保留 180 天。", "mongo:deep_check_jobs", 180, "weekly Sunday 0430", False),
    HousekeepingTask("mongo_deep_check_reports_purge", "L3 Mongo 報告保留 365 天。", "mongo:deep_check_reports", 365, "weekly Sunday 0430", False),
    HousekeepingTask("notification_events_purge", "通知事件保留 180 天。", "mongo:notification_events", 180, "weekly Sunday 0430", False),
    HousekeepingTask("login_attempts_purge", "登入嘗試紀錄保留 90 天。", "mongo:login_attempts", 90, "weekly Sunday 0430", False),
    HousekeepingTask("network_scan_reports_purge", "IPAM / nmap 掃描報告保留 180 天。", "mongo:network_scan_reports", 180, "weekly Sunday 0430", False),
    HousekeepingTask("dependency_collect_runs_purge", "拓樸採集 run 保留 180 天。", "mongo:dependency_collect_runs", 180, "weekly Sunday 0430", False),
    HousekeepingTask("api_tokens_review", "只檢查 API token 數量，不自動刪除正式 token。", "mongo:api_tokens", 0, "daily 1530", False),
    HousekeepingTask("audit_chain_verify", "只驗證 audit hash chain，不刪 audit log。", "mongo:audit_logs", 0, "hourly", False),
    HousekeepingTask("edge_agent_stale_check", "檢查 Edge agent heartbeat 是否過舊。", "mongo:edge_agents", 0, "hourly", False),
    HousekeepingTask("mongo_collection_count", "記錄核心 Mongo collection 筆數，不刪正式主檔。", "mongo:*", 0, "daily 1530", False),
    HousekeepingTask("data_dir_manifest", "產生 data 目錄 manifest。", "data", 0, "daily 1530", False),
    HousekeepingTask("patch_backup_keep", "正式程式碼部署前備份固定保留最新 20 份，可供 rollback。", "backup/patches", 0, "after install / daily 1530", False, 20),
    HousekeepingTask("backup_manifest_purge", "備份 manifest 保留 365 天。", "backup", 365, "weekly Sunday 0500", False),
    HousekeepingTask("backup_verify", "檢查備份目錄可讀與基本 metadata。", "backup", 0, "weekly Sunday 0500", False),
    HousekeepingTask("disk_alert", "檢查中央磁碟用量。", config.INSPECTION_HOME, 0, "hourly", False),
]


MONGO_RETENTION_FIELDS = {
    "nmon_data": ["sampled_at", "created_at"],
    "nmon_raw_files": ["uploaded_at", "created_at"],
    "inventory_runs": ["started_at", "created_at"],
    "inventory_snapshots": ["created_at", "snapshot_at", "started_at"],
    "deep_check_jobs": ["started_at", "created_at"],
    "deep_check_reports": ["timestamp", "created_at"],
    "notification_events": ["created_at", "sent_at"],
    "login_attempts": ["created_at", "attempted_at"],
    "network_scan_reports": ["started_at", "created_at"],
    "dependency_collect_runs": ["started_at", "created_at"],
}


def _human_bytes(value: int) -> str:
    amount = float(value or 0)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if amount < 1024 or unit == "TB":
            return f"{amount:.1f}{unit}" if unit != "B" else f"{int(amount)}B"
        amount /= 1024
    return f"{amount:.1f}TB"


def list_tasks() -> list[dict[str, Any]]:
    runs = {run["task"]: run for run in get_collection("housekeeping_runs").find({}, {"_id": 0}).sort("started_at", -1)}
    return [
        {
            "name": task.name,
            "description": task.description,
            "target": task.target,
            "retention_days": task.retention_days,
            "keep_count": task.keep_count,
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


def _delete_old_collection_docs(collection_name: str, retention_days: int, dry_run: bool) -> dict[str, Any]:
    fields = MONGO_RETENTION_FIELDS.get(collection_name, ["created_at"])
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    collection = get_collection(collection_name)
    before = collection.count_documents({})
    query = {"$or": [{field: {"$lt": cutoff}} for field in fields]}
    matched = collection.count_documents(query)
    deleted = 0
    if matched and not dry_run:
        deleted = collection.delete_many(query).deleted_count
    return {
        "collection": collection_name,
        "retention_days": retention_days,
        "cutoff": cutoff.isoformat(),
        "date_fields": fields,
        "before_count": before,
        "matched_count": matched,
        "deleted_count": deleted if not dry_run else matched,
        "dry_run": dry_run,
    }


def disk_status() -> dict[str, Any]:
    usage = shutil.disk_usage(config.INSPECTION_HOME)
    used_pct = round((usage.used / usage.total) * 100, 2)
    return {
        "path": config.INSPECTION_HOME,
        "total": usage.total,
        "used": usage.used,
        "free": usage.free,
        "used_pct": used_pct,
        "total_h": _human_bytes(usage.total),
        "used_h": _human_bytes(usage.used),
        "free_h": _human_bytes(usage.free),
    }


def _safe_remove_path(path: Path, dry_run: bool) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    size = 0
    if path.is_dir():
        for item in path.rglob("*"):
            if item.is_file():
                try:
                    size += item.stat().st_size
                except OSError:
                    pass
        if not dry_run:
            shutil.rmtree(path)
    else:
        size = path.stat().st_size
        if not dry_run:
            path.unlink()
    return 1, size


def _keep_newest_directories(root: Path, pattern: str, keep_count: int, dry_run: bool) -> dict[str, Any]:
    root = root.resolve()
    items = sorted(
        [path for path in root.glob(pattern) if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    remove = items[keep_count:]
    deleted = 0
    freed = 0
    removed_names = []
    for path in remove:
        resolved = path.resolve()
        if root not in resolved.parents:
            continue
        count, size = _safe_remove_path(resolved, dry_run)
        deleted += count
        freed += size
        removed_names.append(path.name)
    return {
        "deleted_count": deleted,
        "freed_bytes": freed,
        "freed_h": _human_bytes(freed),
        "kept_count": min(len(items), keep_count),
        "total_count": len(items),
        "removed_names": removed_names[:30],
        "dry_run": dry_run,
    }


def _purge_deploy_tmp(dry_run: bool) -> dict[str, Any]:
    root = Path("/tmp").resolve()
    patterns = ["patch_webitgpt*", "webitgpt_patch*"]
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(root.glob(pattern))
    deleted = 0
    freed = 0
    removed_names = []
    for path in sorted(set(candidates), key=lambda item: item.name):
        resolved = path.resolve()
        if resolved.parent != root:
            continue
        count, size = _safe_remove_path(resolved, dry_run)
        deleted += count
        freed += size
        removed_names.append(path.name)
    return {
        "deleted_count": deleted,
        "freed_bytes": freed,
        "freed_h": _human_bytes(freed),
        "removed_names": removed_names[:50],
        "dry_run": dry_run,
    }


def _purge_code_cache(dry_run: bool) -> dict[str, Any]:
    root = Path(config.INSPECTION_HOME).resolve()
    allowed_roots = [root / "webapp", root / "scripts", root / "tests", root / "ansible", root / "edge"]
    patterns = ["__pycache__", ".pytest_cache", "*.pyc", "*.pyo"]
    candidates: list[Path] = []
    for base in allowed_roots:
        if not base.exists():
            continue
        for pattern in patterns:
            candidates.extend(base.rglob(pattern))
    pytest_cache = root / ".pytest_cache"
    if pytest_cache.exists():
        candidates.append(pytest_cache)
    deleted = 0
    freed = 0
    removed_names = []
    for path in sorted(set(candidates), key=lambda item: str(item)):
        resolved = path.resolve()
        if root not in resolved.parents:
            continue
        count, size = _safe_remove_path(resolved, dry_run)
        deleted += count
        freed += size
        removed_names.append(str(resolved.relative_to(root)))
    return {
        "deleted_count": deleted,
        "freed_bytes": freed,
        "freed_h": _human_bytes(freed),
        "removed_names": removed_names[:50],
        "dry_run": dry_run,
    }


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
            detail = _keep_newest_directories(patch_dir, "preinstall_*", task.keep_count or 20, dry_run)
        elif name == "deploy_tmp_purge":
            detail = _purge_deploy_tmp(dry_run)
        elif name == "code_cache_purge":
            detail = _purge_code_cache(dry_run)
        elif task.target.startswith("mongo:"):
            collection_name = task.target.split(":", 1)[1]
            if collection_name == "*":
                names = get_collection("hosts").database.list_collection_names()
                detail = {"collections": {item: get_collection(item).count_documents({}) for item in names}, "dry_run": dry_run}
            elif name == "audit_chain_verify":
                from webapp.services.audit_log_service import verify_chain

                detail = verify_chain()
            elif task.retention_days > 0:
                detail = _delete_old_collection_docs(collection_name, task.retention_days, dry_run)
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


def run_post_install_housekeeping(user: str = "install") -> dict[str, Any]:
    tasks = ["deploy_tmp_purge", "patch_backup_keep", "code_cache_purge", "disk_alert"]
    results = [run_task(task, user=user, dry_run=False) for task in tasks]
    status = "ok" if all(item["status"] in {"ok", "warn"} for item in results) else "fail"
    return {"status": status, "count": len(results), "results": results}


def install_cron_file() -> dict[str, Any]:
    script = Path(config.INSPECTION_HOME) / "scripts" / "run_housekeeping.py"
    cron = Path("/etc/cron.d/webitgpt-housekeeping")
    line = f"30 15 * * * sysinfra INSPECTION_HOME={config.INSPECTION_HOME} {config.INSPECTION_HOME}/venv/bin/python {script} --mode daily >> {config.LOGS_DIR}/housekeeping_cron.log 2>&1\n"
    if os.geteuid() != 0:
        return {"status": "skipped", "reason": "requires root", "path": str(cron)}
    cron.write_text("# webitgpt housekeeping\n" + line, encoding="utf-8")
    return {"status": "ok", "path": str(cron), "line": line.strip()}
