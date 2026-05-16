from __future__ import annotations

import os
import re
from pathlib import Path


APP_NAME = "webitgpt"
VERSION = "1.0.2.43"
PATCH_ID = "asset-verified-identity"
RELEASE_NOTE = "資產 Hostname 與 OS 改以實際採集為可信來源"
BUILD_TIME = os.environ.get("WEBITGPT_BUILD_TIME", "2026-05-16 23:05:00 +08:00")

if not re.match(r"^1\.\d+\.\d+\.\d+$", VERSION):
    raise RuntimeError("webitgpt version must stay in 1.X.X.X format")
if any(int(part) > 99 for part in VERSION.split(".")[1:]):
    raise RuntimeError("webitgpt version segments must stay within 0-99 after major version")

INSPECTION_HOME = os.environ.get("INSPECTION_HOME", "/opt/webitgpt")
WEB_PORT = int(os.environ.get("WEBITGPT_PORT", "8002"))
EDGE_PORT = int(os.environ.get("WEBITGPT_EDGE_PORT", "9444"))

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.environ.get("MONGO_DB") or os.environ.get("MONGO_DB_NAME", "webitgpt")

DATA_DIR = f"{INSPECTION_HOME}/data"
HOSTS_DIR = f"{DATA_DIR}/hosts"
HOSTNAME_LINK_DIR = f"{DATA_DIR}/hosts_by_hostname"
REPORTS_DIR = f"{DATA_DIR}/reports"
GLOBAL_DATA_DIR = f"{DATA_DIR}/_global"
ARCHIVE_DIR = f"{DATA_DIR}/_archive"
DOCS_DIR = f"{DATA_DIR}/docs"
LOGS_DIR = f"{INSPECTION_HOME}/logs"
TMP_DIR = f"{INSPECTION_HOME}/tmp"
BACKUP_DIR = f"{INSPECTION_HOME}/backup"

MARKET_HOURS_START = os.environ.get("MARKET_HOURS_START", "07:50")
MARKET_HOURS_END = os.environ.get("MARKET_HOURS_END", "15:00")
TZ_NAME = os.environ.get("TZ", "Asia/Taipei")

SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-prod")


def ensure_runtime_dirs() -> None:
    for path in [
        DATA_DIR,
        HOSTS_DIR,
        HOSTNAME_LINK_DIR,
        REPORTS_DIR,
        GLOBAL_DATA_DIR,
        ARCHIVE_DIR,
        DOCS_DIR,
        LOGS_DIR,
        TMP_DIR,
        BACKUP_DIR,
    ]:
        Path(path).mkdir(parents=True, exist_ok=True)

