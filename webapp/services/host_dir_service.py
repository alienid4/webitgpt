from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from typing import Any

from webapp import config


HOST_SUBDIRS = [
    "inspections",
    "nmon",
    "audit",
    "security_audit",
    "self_check",
    "deep_check",
    "debug_snapshots",
    "packages",
    "logs",
]

SENSITIVE_META_FIELDS = {"ssh_key", "password", "password_hash", "mfa_secret"}


def _host_dir(asset_seq: str) -> Path:
    return Path(config.HOSTS_DIR) / asset_seq


def _safe_meta(host: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in host.items() if k not in SENSITIVE_META_FIELDS and not k.startswith("_")}


def write_meta(host: dict[str, Any]) -> Path:
    asset_seq = host["asset_seq"]
    target = _host_dir(asset_seq)
    target.mkdir(parents=True, exist_ok=True)
    meta = {
        **_safe_meta(host),
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }
    meta_path = target / "meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return meta_path


def init_dir(host: dict[str, Any]) -> Path:
    asset_seq = host["asset_seq"]
    target = _host_dir(asset_seq)
    target.mkdir(parents=True, exist_ok=True)
    for subdir in HOST_SUBDIRS:
        (target / subdir).mkdir(exist_ok=True)
    write_meta(host)
    sync_symlink(host)
    return target


def sync_symlink(host: dict[str, Any]) -> None:
    hostname = (host.get("hostname") or "").strip()
    if not hostname:
        return
    link_root = Path(config.HOSTNAME_LINK_DIR)
    link_root.mkdir(parents=True, exist_ok=True)
    target = Path("..") / "hosts" / host["asset_seq"]
    link_path = link_root / hostname

    for existing in link_root.iterdir():
        try:
            if existing.name != hostname and existing.is_symlink() and os.readlink(existing) == str(target):
                existing.unlink()
        except OSError:
            continue

    if link_path.exists() or link_path.is_symlink():
        if link_path.is_dir() and not link_path.is_symlink():
            shutil.rmtree(link_path)
        else:
            link_path.unlink()

    try:
        os.symlink(str(target), link_path, target_is_directory=True)
    except OSError:
        # Windows without symlink privilege: create a tiny pointer file instead.
        link_path.mkdir(parents=True, exist_ok=True)
        (link_path / ".target").write_text(str(target), encoding="utf-8")


def archive_dir(asset_seq: str, hostname: Optional[str] = None) -> Path:
    source = _host_dir(asset_seq)
    stamp = datetime.now().strftime("%Y%m%d")
    target = Path(config.ARCHIVE_DIR) / f"{asset_seq}_retired_{stamp}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.exists():
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(source), str(target))
    if hostname:
        link_path = Path(config.HOSTNAME_LINK_DIR) / hostname
        if link_path.exists() or link_path.is_symlink():
            if link_path.is_dir() and not link_path.is_symlink():
                shutil.rmtree(link_path)
            else:
                link_path.unlink()
    return target


def restore_dir(asset_seq: str) -> Path:
    archive_root = Path(config.ARCHIVE_DIR)
    matches = sorted(archive_root.glob(f"{asset_seq}_retired_*"), reverse=True)
    if not matches:
        raise FileNotFoundError(f"No archive found for {asset_seq}")
    target = _host_dir(asset_seq)
    if target.exists():
        raise FileExistsError(f"Host directory already exists: {target}")
    shutil.move(str(matches[0]), str(target))
    return target
