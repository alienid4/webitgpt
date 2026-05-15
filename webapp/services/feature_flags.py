from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from webapp.services.mongo_service import get_collection


def _flag(key: str, name: str, description: str, default: bool, category: str) -> dict[str, Any]:
    return {"key": key, "name": name, "description": description, "default": default, "category": category}


DEFAULT_FLAGS: list[dict[str, Any]] = [
    _flag("module_compliance_security", "合規與資安大模組", "帳號盤點、軟體盤點、TWGCB、安全稽核與合規 API 的總開關。", False, "module"),
    _flag("audit", "帳號盤點", "帳號盤點頁、清冊、歷史、差異報告與 API。", True, "compliance"),
    _flag("packages", "軟體盤點", "軟體與套件盤點、版本變更追蹤與匯出。", True, "compliance"),
    _flag("perf", "效能月報 / NMON", "效能資料、NMON 採樣與月報檢視。", True, "inspect"),
    _flag("twgcb", "TWGCB 合規", "TWGCB 類規則、設定、結果與報表。", True, "compliance"),
    _flag("summary", "異常總結", "開門檢查與異常摘要報告。", True, "inspect"),
    _flag("security_audit", "安全稽核", "資安缺口、修補規劃、備份與 rollback。", True, "compliance"),
    _flag("history", "歷史查詢", "巡檢、盤點與診斷歷史查詢。", True, "inspect"),
    _flag("dependencies", "系統拓撲", "系統相依、服務關聯、ss/nmap 對帳與互動拓撲。", True, "inspect"),
    _flag("cmdb_csv_import", "CSV 匯入匯出", "資產管理 CSV 匯入、匯出與範本。", True, "cmdb"),
    _flag("cmdb_saved_views", "常用篩選", "資產管理常用篩選與個人檢視。", True, "cmdb"),
    _flag("cmdb_manual_input", "手動建檔", "手動新增主機、快速草稿與多主機建立流程。", True, "cmdb"),
    _flag("cmdb_network_scan", "網段掃描 / IPAM", "IPAM、nmap 網段掃描、未納管清單與週期對帳。", True, "cmdb"),
    _flag("cmdb_extension_fields", "擴充欄位", "資產管理自訂欄位與欄位治理。", True, "cmdb"),
    _flag("cmdb_bulk_actions", "批次操作", "資產管理批次更新、管理者與備註維護。", True, "cmdb"),
    _flag("cmdb_undo_30s", "30 秒復原", "資產刪除短時間復原。", True, "cmdb"),
    _flag("host_self_check", "單機自檢", "資產列表單台主機自檢按鈕與 API。", True, "host"),
    _flag("host_self_check_global", "全域自檢", "多台主機批次自檢。", True, "host"),
    _flag("deep_check", "深度檢查", "Linux L3 深度診斷工作、歷史與 Remedy KB。", True, "host"),
    _flag("deep_check_blackbox", "黑箱深度檢查", "外部黑箱診斷整合預留功能。", False, "host"),
    _flag("host_debug_snapshot", "DEBUG 快照", "遮罩後的主機 DEBUG 快照按鈕與 API。", True, "host"),
    _flag("host_security_audit_button", "主機安全按鈕", "資產列表安全稽核操作按鈕。", True, "host"),
    _flag("host_type_linux", "Linux", "Linux runner 支援。", True, "platform"),
    _flag("host_type_windows", "Windows", "Windows / WinRM runner 支援。", True, "platform"),
    _flag("host_type_vmware", "VMware", "VMware / vCenter runner 支援。", False, "platform"),
    _flag("host_type_aix", "AIX", "AIX SSH raw runner 支援。", False, "platform"),
    _flag("host_type_as400", "AS400", "AS400 平台邊界，尚未支援。", False, "platform"),
    _flag("external_api_v1", "對外 API v1", "Bearer token 對外 API。", True, "api"),
    _flag("ai_chat_panel", "AI 對話面板", "右下角 AI 對話視窗。", False, "ai"),
    _flag("ai_mcp_server", "MCP Server", "MCP manifest 與 tools API。", True, "ai"),
    _flag("ai_openapi_auto_doc", "OpenAPI 自動文件", "自動產生 OpenAPI 文件。", True, "ai"),
    _flag("ai_report_summary", "AI 報告摘要", "AI 輔助產生報告摘要。", True, "ai"),
    _flag("ai_prompt_library", "提示詞庫", "AI 提示詞範本管理。", True, "ai"),
    _flag("market_hours_protection", "盤中保護", "盤中時段保護高風險變更。", True, "system"),
    _flag("housekeeping_enabled", "Housekeeping", "Housekeeping 任務清單與執行紀錄。", True, "system"),
    _flag("housekeeping_dry_run", "Housekeeping 試跑", "Housekeeping 預設只試跑不刪除。", False, "system"),
    _flag("backup_verify_enabled", "備份驗證", "備份可讀性與還原前檢查。", True, "system"),
    _flag("disk_alert_enabled", "磁碟告警", "磁碟容量告警任務。", True, "system"),
    _flag("audit_log_hash_chain", "操作紀錄 Hash Chain", "稽核紀錄 hash chain 驗證。", True, "system"),
    _flag("mfa_required", "MFA", "OTP/MFA 登入驗證要求。", False, "auth"),
    _flag("force_single_login", "單一登入", "限制同帳號單一有效 session。", True, "auth"),
    _flag("dev_auto_login_superadmin", "開發自動登入最高管理員", "開發驗證期間自動登入 superadmin。", True, "dev"),
    _flag("compliance_engine", "合規規則引擎", "合規規則評估引擎。", True, "compliance"),
    _flag("compliance_account", "帳號規則", "帳號類合規規則。", True, "compliance"),
    _flag("compliance_package", "套件規則", "套件類合規規則。", True, "compliance"),
    _flag("compliance_port", "連接埠規則", "連接埠類合規規則。", True, "compliance"),
    _flag("compliance_process", "程序規則", "程序類合規規則。", True, "compliance"),
    _flag("compliance_file", "檔案規則", "檔案與權限類合規規則。", True, "compliance"),
    _flag("compliance_ip", "IP 規則", "IP 與網段類合規規則。", True, "compliance"),
    _flag("security_audit_whitebox", "白箱安全稽核", "登入主機後執行的安全稽核。", True, "compliance"),
    _flag("security_audit_blackbox", "黑箱安全稽核", "外部觀點安全稽核。", True, "compliance"),
    _flag("security_audit_blackbox_hydra", "Hydra 黑箱檢查", "Hydra 登入風險檢查預留功能。", True, "compliance"),
    _flag("notify_email", "Email 通知", "Email 通知管道。", True, "notify"),
    _flag("notify_slack", "Slack 通知", "Slack 通知管道。", False, "notify"),
    _flag("notify_teams", "Teams 通知", "Teams 通知管道。", False, "notify"),
    _flag("notify_jira", "JIRA 整合", "JIRA 工單整合。", False, "notify"),
    _flag("phase_readonly_mode", "Phase 只讀模式", "雙寫評比期間封鎖受監控主機寫入動作。", True, "system"),
]


def ensure_feature_flags() -> int:
    col = get_collection("feature_flags")
    now = datetime.now(timezone.utc)
    inserted = 0
    for flag in DEFAULT_FLAGS:
        insert_doc = {"key": flag["key"], "enabled": flag["default"], "created_at": now}
        result = col.update_one(
            {"key": flag["key"]},
            {
                "$setOnInsert": insert_doc,
                "$set": {
                    "name": flag["name"],
                    "description": flag["description"],
                    "category": flag["category"],
                    "default": flag["default"],
                    "updated_at": now,
                },
            },
            upsert=True,
        )
        if result.upserted_id:
            inserted += 1
    return inserted


def is_enabled(key: str, default: bool = False) -> bool:
    try:
        flag = get_collection("feature_flags").find_one({"key": key}, {"enabled": 1})
        if not flag:
            return default
        return bool(flag.get("enabled"))
    except Exception:
        return default


def snapshot() -> dict[str, bool]:
    try:
        return {doc["key"]: bool(doc.get("enabled")) for doc in get_collection("feature_flags").find({}, {"key": 1, "enabled": 1})}
    except Exception:
        return {flag["key"]: bool(flag["default"]) for flag in DEFAULT_FLAGS}


def set_enabled(key: str, enabled: bool, user: str = "system") -> bool:
    now = datetime.now(timezone.utc)
    result = get_collection("feature_flags").update_one({"key": key}, {"$set": {"enabled": bool(enabled), "updated_at": now, "updated_by": user}})
    return result.matched_count == 1
