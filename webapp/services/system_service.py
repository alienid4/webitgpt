from __future__ import annotations

import json
import csv
import io
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from webapp import config
from webapp.services.audit_log_service import verify_chain
from webapp.services.feature_flags import DEFAULT_FLAGS
from webapp.services.housekeeping_service import disk_status
from webapp.services.mongo_service import get_db


MODULE_CATEGORY_LABELS = {
    "module": "大模組",
    "cmdb": "資產管理",
    "inspect": "巡檢報告",
    "host": "主機操作",
    "platform": "平台支援",
    "compliance": "合規與資安",
    "system": "系統控制",
    "auth": "認證權限",
    "api": "對外 API",
    "ai": "AI 整合",
    "notify": "通知整合",
    "dev": "開發期設定",
}


MODULE_IMPACT = {
    "module_compliance_security": {
        "level": "大模組",
        "scope": "帳號盤點、軟體盤點、TWGCB 合規、安全稽核、合規 API",
        "off_effect": "上方選單會隱藏帳號盤點、軟體盤點、TWGCB 合規；相關 API 會回 503。",
        "recommendation": "合規資安還沒驗收完成時，優先關這個大模組。",
    },
    "ai_chat_panel": {
        "level": "入口",
        "scope": "右下角 AI 對話視窗",
        "off_effect": "所有頁面不會顯示右下角 AI 面板。",
        "recommendation": "未導入正式 LLM 前建議關閉。",
    },
    "phase_readonly_mode": {
        "level": "保護",
        "scope": "遠端修補、主機寫入、批次異動",
        "off_effect": "允許進入較高風險的寫入流程；仍需個別功能實作與權限控管。",
        "recommendation": "開發/評比期間保持啟用。",
    },
    "dev_auto_login_superadmin": {
        "level": "開發",
        "scope": "登入流程",
        "off_effect": "需要手動登入帳密，才能測一般帳號與權限。",
        "recommendation": "前期開發可開；驗證權限時再關。",
    },
    "cmdb_network_scan": {
        "level": "細項",
        "scope": "資產管理的 IPAM/nmap 網段掃描與對帳",
        "off_effect": "網段掃描、未納管清單、週期對帳入口停用。",
        "recommendation": "nmap 未安裝或掃描政策未核准前可關閉。",
    },
    "cmdb_csv_import": {
        "level": "細項",
        "scope": "資產管理 CSV 匯入/匯出",
        "off_effect": "資產批次匯入流程不可用。",
        "recommendation": "一般建議開啟，方便大量建檔。",
    },
    "cmdb_manual_input": {
        "level": "細項",
        "scope": "資產手動建檔與草稿",
        "off_effect": "使用者不能從 UI 手動新增資產。",
        "recommendation": "如果只允許正式 CMDB 匯入，可關閉。",
    },
    "host_debug_snapshot": {
        "level": "細項",
        "scope": "資產列表 DEBUG 快照按鈕與 API",
        "off_effect": "使用者不能產生遮罩後 debug 快照。",
        "recommendation": "資安疑慮或遮罩規則未確認時可關閉。",
    },
    "host_self_check": {
        "level": "細項",
        "scope": "單台主機自檢",
        "off_effect": "單機自檢按鈕停用。",
        "recommendation": "SSH/WinRM runner 穩定後建議開啟。",
    },
    "host_self_check_global": {
        "level": "細項",
        "scope": "全站批次自檢",
        "off_effect": "不能一次觸發多台主機自檢。",
        "recommendation": "避免網路負擔時可關閉。",
    },
    "market_hours_protection": {
        "level": "保護",
        "scope": "盤中 07:50-15:00 高風險變更",
        "off_effect": "盤中變更保護不生效。",
        "recommendation": "正式環境建議永遠開啟。",
    },
    "mfa_required": {
        "level": "認證",
        "scope": "登入 OTP/MFA",
        "off_effect": "登入不要求 OTP。",
        "recommendation": "你目前不想 OTP，維持關閉。",
    },
}


MODULE_CATEGORY_LABELS = {
    "module": "大模組",
    "cmdb": "資產管理",
    "inspect": "巡檢報告",
    "host": "主機操作",
    "platform": "平台支援",
    "compliance": "合規與資安",
    "system": "系統控制",
    "auth": "認證與權限",
    "api": "對外 API",
    "ai": "AI 整合",
    "notify": "通知整合",
    "dev": "開發後台",
}


MODULE_IMPACT = {
    "module_compliance_security": {
        "level": "大模組",
        "scope": "帳號盤點、軟體盤點、TWGCB 合規、安全稽核、合規規則 API",
        "off_effect": "關閉後上方選單會隱藏帳號盤點、軟體盤點、TWGCB 合規與安全稽核；相關 API 回傳 503。",
        "recommendation": "合規與資安功能未驗收前可整個關閉；要開放給主管看時再啟用。",
    },
    "audit": {"level": "頁面", "scope": "帳號盤點頁、帳號清冊、主機角度、帳號角度、差異報告", "off_effect": "關閉後帳號盤點不應開放使用；仍受合規與資安大模組總開關控制。", "recommendation": "帳號盤點流程驗收完成後再開放。"},
    "packages": {"level": "頁面", "scope": "軟體盤點頁、套件搜尋、版本變更追蹤、CSV/JSON 匯出", "off_effect": "關閉後軟體盤點功能不開放；仍受合規與資安大模組總開關控制。", "recommendation": "套件採集與差異報告完成後再開放。"},
    "twgcb": {"level": "頁面", "scope": "TWGCB 合規頁、規則庫、設定管理、Excel 與報表", "off_effect": "關閉後 TWGCB 合規功能不開放；仍受合規與資安大模組總開關控制。", "recommendation": "完整規則庫與報表驗收後再開放。"},
    "security_audit": {"level": "頁面", "scope": "安全稽核頁、主機缺口、修補計畫、備份與 rollback", "off_effect": "關閉後安全稽核入口不開放；仍受合規與資安大模組總開關控制。", "recommendation": "修補前備份與 rollback 流程完成後再開放。"},
    "ai_chat_panel": {"level": "入口", "scope": "右下角 AI 對話面板", "off_effect": "關閉後所有頁面右下角不顯示 AI 視窗。", "recommendation": "LLM 串接未驗收前維持關閉。"},
    "ai_mcp_server": {"level": "細項", "scope": "MCP Server manifest 與 tools API", "off_effect": "關閉後 AI/MCP client 不能讀取工具清單。", "recommendation": "MCP 權限模型完成後再開放。"},
    "ai_openapi_auto_doc": {"level": "細項", "scope": "OpenAPI 自動文件", "off_effect": "關閉後不提供 AI 或外部系統讀取 OpenAPI 文件。", "recommendation": "API 文件穩定後再開放。"},
    "ai_prompt_library": {"level": "細項", "scope": "提示詞庫", "off_effect": "關閉後不提供提示詞範本管理。", "recommendation": "提示詞權限與遮罩策略完成後再開放。"},
    "ai_report_summary": {"level": "細項", "scope": "AI 報告摘要", "off_effect": "關閉後報表不產生 AI 摘要。", "recommendation": "主管報表語氣與資料遮罩驗收後再開放。"},
    "cmdb_network_scan": {"level": "細項", "scope": "資產管理的網段掃描 / IPAM / nmap 對帳", "off_effect": "關閉後不能執行網段掃描、IPAM 對帳與未納管清單。", "recommendation": "nmap 安裝與掃描排程確認後再開放。"},
    "cmdb_csv_import": {"level": "細項", "scope": "資產管理 CSV 匯入匯出", "off_effect": "關閉後不能大量匯入或匯出資產清冊。", "recommendation": "欄位檢核規則穩定後再開放。"},
    "cmdb_saved_views": {"level": "細項", "scope": "資產管理常用篩選", "off_effect": "關閉後不能儲存、套用或刪除常用篩選。", "recommendation": "常用篩選驗收後再開放。"},
    "cmdb_manual_input": {"level": "細項", "scope": "資產管理手動建檔與快速建立草稿", "off_effect": "關閉後不能從 UI 新增資產或建立草稿。", "recommendation": "若只允許 CMDB 匯入，可關閉此功能。"},
    "cmdb_extension_fields": {"level": "細項", "scope": "資產管理擴充欄位", "off_effect": "關閉後不能管理自訂欄位。", "recommendation": "欄位治理流程確定後再開放。"},
    "cmdb_bulk_actions": {"level": "細項", "scope": "資產管理批次操作", "off_effect": "關閉後不能批次更新管理者、備註或其他資產欄位。", "recommendation": "權限與 audit log 完成後再開放。"},
    "cmdb_undo_30s": {"level": "細項", "scope": "資產刪除 30 秒復原", "off_effect": "關閉後刪除資產不提供短時間復原。", "recommendation": "正式變更流程完成前可保留啟用。"},
    "host_debug_snapshot": {"level": "細項", "scope": "資產列表 DEBUG 快照按鈕與遮罩 API", "off_effect": "關閉後不能產生主機 DEBUG 快照。", "recommendation": "遮罩規則與稽核紀錄確認後再開放。"},
    "host_security_audit_button": {"level": "細項", "scope": "資產列表安全按鈕與安全稽核入口", "off_effect": "關閉後資產列表不顯示安全稽核操作按鈕。", "recommendation": "安全稽核功能未完成前可關閉。"},
    "host_self_check": {"level": "細項", "scope": "資產列表單機自檢按鈕與 API", "off_effect": "關閉後不能從資產列表對單台主機自檢。", "recommendation": "SSH/WinRM runner 驗收後再開放。"},
    "host_self_check_global": {"level": "細項", "scope": "資產管理批次或全域自檢", "off_effect": "關閉後不能對多台主機一次執行自檢。", "recommendation": "避免對網路造成負擔，排程與限流完成後再開放。"},
    "market_hours_protection": {"level": "安全", "scope": "盤中 07:50-15:00 高風險變更管控", "off_effect": "關閉後盤中不再阻擋高風險變更。", "recommendation": "正式環境建議保持啟用。"},
    "mfa_required": {"level": "認證", "scope": "登入 OTP/MFA", "off_effect": "關閉後登入不需要 OTP。", "recommendation": "開發期間可關閉；正式環境再啟用。"},
    "dev_auto_login_superadmin": {"level": "開發", "scope": "登入流程", "off_effect": "關閉後不再自動登入最高管理員，需要輸入帳密。", "recommendation": "開發期間可啟用；正式評估時再關閉。"},
    "phase_readonly_mode": {"level": "安全", "scope": "受監控主機寫入保護", "off_effect": "關閉後可能允許修補、停用帳號等寫入操作。", "recommendation": "雙寫評比期間建議保持啟用。"},
}


def admin_console_overview() -> dict[str, Any]:
    db = get_db()
    health = health_dashboard()
    latest_logs = operation_logs(8)
    settings_count = db_count("settings")
    timer_text = job_schedule().get("timers", "")
    return {
        "health": health,
        "metrics": {
            "hosts": db_count("hosts"),
            "users": db_count("users"),
            "feature_flags": db_count("feature_flags"),
            "settings": settings_count,
            "audit_logs": db_count("audit_logs"),
            "inventory_runs": db_count("inventory_runs"),
            "ipam_reports": db_count("network_scan_reports"),
            "patch_backups": len(patch_inventory().get("patches", [])),
        },
        "modules": [
            {"title": "功能開關", "desc": "依大模組啟用或關閉尚未開發完成的功能。", "endpoint": "api_superadmin.superadmin_page", "status": "可操作"},
            {"title": "使用者與權限", "desc": "建立帳號、鎖定、重設密碼與角色管理。", "endpoint": "api_superadmin.users_page", "status": "可操作"},
            {"title": "API Token", "desc": "核發對外 API 與 MCP 用 token。", "endpoint": "api_superadmin.tokens_page", "status": "可操作"},
            {"title": "設定管理", "desc": "檢視 Mongo 設定與系統執行參數。", "endpoint": "api_superadmin.settings_page", "status": f"{settings_count} 筆設定"},
            {"title": "日誌檢視", "desc": "檢視 error、access、IPAM 排程日誌。", "endpoint": "api_superadmin.logs_page", "status": "可匯出"},
            {"title": "系統日誌例外", "desc": "管理開門檢查系統日誌白名單，避免已確認無害訊息每天亮橘燈。", "endpoint": "api_superadmin.log_exceptions_page", "status": "可管理"},
            {"title": "重要服務設定", "desc": "設定開門檢查必須啟動的 sshd、cron、AP service 等服務。", "endpoint": "api_superadmin.important_services_page", "status": "可管理"},
            {"title": "工作排程", "desc": "檢視 systemd timer、Housekeeping 與 IPAM 對帳排程。", "endpoint": "api_superadmin.jobs_page", "status": "可檢視"},
            {"title": "操作紀錄", "desc": "稽核操作紀錄與 hash chain 狀態。", "endpoint": "api_superadmin.audit_logs_page", "status": "可匯出"},
            {"title": "備份 / DR", "desc": "產生備份 manifest 與 DR dry-run。", "endpoint": "api_superadmin.backup_dr_page", "status": "dry-run"},
            {"title": "Patch / 回滾", "desc": "檢視 patch 備份與產生回滾計畫。", "endpoint": "api_superadmin.patches_page", "status": config.VERSION},
            {"title": "開發後台", "desc": "文件、檔案管理、備忘錄、提交紀錄與模組管理。", "endpoint": "api_superadmin.dev_console_page", "status": "開發期"},
        ],
        "latest_logs": latest_logs,
        "timer_lines": [line for line in timer_text.splitlines()[:8] if line.strip()],
    }


def health_dashboard() -> dict[str, Any]:
    db = get_db()
    return {
        "app": config.APP_NAME,
        "version": config.VERSION,
        "patch_id": config.PATCH_ID,
        "release_note": config.RELEASE_NOTE,
        "build_time": config.BUILD_TIME,
        "generated_at": datetime.now(timezone.utc),
        "disk": disk_status(),
        "audit": verify_chain(),
        "collections": {name: db[name].count_documents({}) for name in ["hosts", "audit_logs", "users", "compliance_rules", "compliance_findings"]},
    }


def create_backup_manifest(user: str = "system") -> dict[str, Any]:
    backup_dir = Path(config.BACKUP_DIR)
    backup_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    manifest = {
        "app": config.APP_NAME,
        "version": config.VERSION,
        "patch_id": config.PATCH_ID,
        "release_note": config.RELEASE_NOTE,
        "build_time": config.BUILD_TIME,
        "created_at": now.isoformat(),
        "created_by": user,
        "data_dir": config.DATA_DIR,
        "disk": disk_status(),
        "audit": verify_chain(),
    }
    target = backup_dir / f"backup_manifest_{now.strftime('%Y%m%d_%H%M%S')}.json"
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    manifest["path"] = str(target)
    return manifest


def dr_drill(user: str = "system") -> dict[str, Any]:
    manifest = create_backup_manifest(user)
    return {"status": "ok", "mode": "dry-run", "checked": ["backup_dir", "audit_chain", "disk"], "manifest": manifest}


def patch_inventory() -> dict[str, Any]:
    backup_dir = Path(config.BACKUP_DIR) / "patches"
    backup_dir.mkdir(parents=True, exist_ok=True)
    patches = [
        {"name": path.name, "size": path.stat().st_size, "mtime": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)}
        for path in backup_dir.glob("*")
        if path.is_file()
    ]
    return {
        "patches": sorted(patches, key=lambda item: item["mtime"], reverse=True),
        "current_version": config.VERSION,
        "patch_id": config.PATCH_ID,
        "release_note": config.RELEASE_NOTE,
        "build_time": config.BUILD_TIME,
    }


def rollback_plan(target: str, user: str = "system") -> dict[str, Any]:
    return {
        "status": "planned",
        "mode": "dry-run",
        "target": target,
        "requested_by": user,
        "steps": ["stop webitgpt", "restore selected patch backup", "run bootstrap", "restart services", "run smoke test"],
    }


def settings_overview() -> dict[str, Any]:
    db = get_db()
    settings = list(db.settings.find({}, {"_id": 0}).sort("key", 1))
    return {
        "runtime": {
            "inspection_home": config.INSPECTION_HOME,
            "mongo_db": config.MONGO_DB_NAME,
            "web_port": config.WEB_PORT,
            "edge_port": config.EDGE_PORT,
            "timezone": config.TZ_NAME,
        },
        "settings": settings,
    }


def log_tail(name: str = "error", lines: int = 200) -> dict[str, Any]:
    safe = {"error": "error.log", "access": "access.log", "ipam": "ipam_reconcile.log"}.get(name, "error.log")
    path = Path(config.LOGS_DIR) / safe
    if not path.exists():
        return {"name": name, "path": str(path), "content": "", "error": "log file not found"}
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
    return {"name": name, "path": str(path), "content": "\n".join(content), "error": ""}


def job_schedule() -> dict[str, Any]:
    try:
        completed = subprocess.run(["systemctl", "list-timers", "--no-pager", "--all"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8)
        timers = completed.stdout
    except Exception as exc:
        timers = str(exc)
    return {"timers": timers, "housekeeping": db_count("housekeeping_runs"), "ipam_reports": db_count("network_scan_reports")}


def db_count(collection: str) -> int:
    try:
        return int(get_db()[collection].count_documents({}))
    except Exception:
        return 0


def operation_logs(limit: int = 200) -> list[dict[str, Any]]:
    return list(get_db().audit_logs.find({}, {"_id": 0}).sort("seq", -1).limit(limit))


def operation_logs_csv(limit: int = 1000) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["seq", "created_at", "ts", "actor", "user", "action", "detail"], extrasaction="ignore")
    writer.writeheader()
    for row in operation_logs(limit):
        row = dict(row)
        row["detail"] = json.dumps(row.get("detail", row.get("details", {})), ensure_ascii=False, default=str)
        writer.writerow(row)
    return output.getvalue()


def remote_tool_plan(action: str, target: str = "", service: str = "") -> dict[str, Any]:
    action_labels = {
        "linux_init": "Linux initialization",
        "service_start": "Start service",
        "service_stop": "Stop service",
        "service_restart": "Restart service",
        "remote_command": "Remote command",
    }
    steps = {
        "linux_init": ["prepare SSH key", "create or verify sysinfra account", "verify sudo policy", "install required packages", "record audit evidence"],
        "service_start": [f"systemctl start {service}", "verify active status", "record service event"],
        "service_stop": [f"systemctl stop {service}", "verify inactive status", "record service event"],
        "service_restart": [f"systemctl restart {service}", "verify active status", "record service event"],
        "remote_command": ["validate change ticket", "preview command", "execute only after approval", "store stdout/stderr"],
    }.get(action, ["select a supported action"])
    return {
        "status": "planned",
        "mode": "dry-run",
        "action": action,
        "action_label": action_labels.get(action, action),
        "target": target,
        "service": service,
        "steps": steps,
        "message": "Remote tools are dry-run plans while monitored-host write actions are locked.",
    }


def dev_console_payload() -> dict[str, Any]:
    docs_dir = Path(config.DOCS_DIR)
    docs_dir.mkdir(parents=True, exist_ok=True)
    notes_path = docs_dir / "dev_notes.md"
    if not notes_path.exists():
        notes_path.write_text("# Development notes\n\n- Track implementation notes and deployment decisions here.\n", encoding="utf-8")
    try:
        commits = subprocess.run(["git", "log", "--oneline", "-n", "20"], cwd=config.INSPECTION_HOME, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8).stdout
    except Exception as exc:
        commits = str(exc)
    files = []
    for path in sorted(docs_dir.glob("*"))[:100]:
        files.append({"name": path.name, "size": path.stat().st_size, "mtime": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)})
    root_files = []
    root_dir = Path(config.INSPECTION_HOME)
    for path in sorted(root_dir.glob("*"))[:80]:
        if path.name in {"venv", "__pycache__"}:
            continue
        root_files.append(
            {
                "name": path.name,
                "kind": "目錄" if path.is_dir() else "檔案",
                "size": 0 if path.is_dir() else path.stat().st_size,
                "mtime": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc),
            }
        )
    modules = []
    defaults = {flag["key"]: flag for flag in DEFAULT_FLAGS}
    compliance_parent = get_db().feature_flags.find_one({"key": "module_compliance_security"}, {"enabled": 1}) or {}
    compliance_enabled = bool(compliance_parent.get("enabled"))
    for doc in get_db().feature_flags.find({}, {"_id": 0}).sort("category", 1).sort("key", 1):
        key = doc.get("key", "")
        default = defaults.get(key, {})
        category = doc.get("category") or default.get("category", "system")
        impact = MODULE_IMPACT.get(key, {})
        is_compliance_child = category == "compliance" and key != "module_compliance_security"
        effective_enabled = bool(doc.get("enabled")) and (compliance_enabled or not is_compliance_child)
        modules.append(
            {
                "key": key,
                "name": doc.get("name") or default.get("name") or key,
                "category": category,
                "category_label": MODULE_CATEGORY_LABELS.get(str(category), str(category)),
                "enabled": bool(doc.get("enabled")),
                "effective_enabled": effective_enabled,
                "level": impact.get("level", "細項"),
                "scope": impact.get("scope") or doc.get("description") or default.get("description", "控制此功能是否開放。"),
                "off_effect": impact.get("off_effect") or "關閉後，此功能入口、按鈕或相關 API 會依實作停用；若屬子功能，可能仍受大模組開關限制。",
                "recommendation": impact.get("recommendation") or "不確定時先維持預設；未完成或不想開放給使用者時可關閉。",
                "parent_note": "受合規資安大模組控制" if is_compliance_child else "",
                "updated_at": doc.get("updated_at"),
            }
        )
    modules.sort(key=lambda item: (0 if item["level"] == "大模組" else 1, item["category_label"], item["key"]))
    return {
        "docs_dir": str(docs_dir),
        "files": files,
        "root_dir": str(root_dir),
        "root_files": root_files,
        "notes": notes_path.read_text(encoding="utf-8", errors="replace"),
        "commits": commits,
        "release_notes": release_notes(),
        "modules": modules,
    }


def release_notes(limit: int = 12) -> list[dict[str, Any]]:
    candidates = [
        Path(config.INSPECTION_HOME) / "CHANGELOG.md",
        Path(__file__).resolve().parents[2] / "CHANGELOG.md",
    ]
    changelog = next((path for path in candidates if path.exists()), None)
    if not changelog:
        return []

    def clean_release_text(value: str) -> bool:
        return "\ufffd" not in value and "??" not in value

    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    heading = re.compile(r"^## v(?P<version>\S+) - (?P<date>.+?) - (?P<patch_id>\S+)")
    for line in changelog.read_text(encoding="utf-8", errors="replace").splitlines():
        matched = heading.match(line)
        if matched:
            if current and current.get("changes"):
                entries.append(current)
            if len(entries) >= limit:
                break
            if not clean_release_text(line):
                current = None
                continue
            current = {
                "version": matched.group("version"),
                "date": matched.group("date"),
                "patch_id": matched.group("patch_id"),
                "changes": [],
            }
            continue
        if current and line.startswith("- ") and clean_release_text(line):
            current["changes"].append(line[2:])
    if current and current.get("changes") and len(entries) < limit:
        entries.append(current)
    return entries[:limit]

def save_dev_note(text: str, user: str = "system") -> dict[str, Any]:
    docs_dir = Path(config.DOCS_DIR)
    docs_dir.mkdir(parents=True, exist_ok=True)
    notes_path = docs_dir / "dev_notes.md"
    notes_path.write_text(text, encoding="utf-8")
    return {"status": "ok", "path": str(notes_path), "updated_by": user, "updated_at": datetime.now(timezone.utc)}


def save_dev_upload(filename: str, content: bytes, user: str = "system") -> dict[str, Any]:
    docs_dir = Path(config.DOCS_DIR)
    docs_dir.mkdir(parents=True, exist_ok=True)
    target = docs_dir / filename
    if not filename or filename in {".", ".."}:
        raise ValueError("檔名不可為空")
    if target.exists():
        stem = target.stem
        suffix = target.suffix
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = docs_dir / f"{stem}_{timestamp}{suffix}"
    target.write_bytes(content)
    return {
        "status": "ok",
        "path": str(target),
        "name": target.name,
        "size": target.stat().st_size,
        "updated_by": user,
        "updated_at": datetime.now(timezone.utc),
    }

