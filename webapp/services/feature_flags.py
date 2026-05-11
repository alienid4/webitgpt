from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from webapp.services.mongo_service import get_collection


def _flag(key: str, name: str, description: str, default: bool, category: str) -> dict[str, Any]:
    return {"key": key, "name": name, "description": description, "default": default, "category": category}


DEFAULT_FLAGS: list[dict[str, Any]] = [
    _flag("module_compliance_security", "合規與資安大模組", "控制帳號盤點、軟體盤點、TWGCB 合規、安全稽核與相關 API 是否開放", False, "module"),
    _flag("audit", "帳號盤點", "帳號盤點頁、盤點 API、歷史紀錄與差異比較", True, "compliance"),
    _flag("packages", "軟體盤點", "軟體盤點頁、套件搜尋、版本變更追蹤與匯出", True, "compliance"),
    _flag("perf", "效能月報 / NMON", "NMON 採樣、效能圖表與日週月報", True, "inspect"),
    _flag("twgcb", "TWGCB 合規", "TWGCB 規則、設定管理、Excel 與報表", True, "compliance"),
    _flag("summary", "異常總結", "主管摘要、異常彙整與報告摘要", True, "inspect"),
    _flag("security_audit", "安全稽核", "依主機檢視資安缺口、修補計畫、備份與回復", True, "compliance"),
    _flag("history", "歷史查詢", "巡檢、盤點與診斷歷史查詢", True, "inspect"),
    _flag("dependencies", "系統聯通圖 / 拓撲", "系統相依、服務關聯與互動拓撲圖", True, "inspect"),
    _flag("cmdb_csv_import", "CSV 匯入匯出", "資產管理 CSV 匯入、匯出與欄位檢核", True, "cmdb"),
    _flag("cmdb_saved_views", "常用篩選", "資產管理常用篩選儲存、套用、刪除", True, "cmdb"),
    _flag("cmdb_manual_input", "手動建檔", "資產管理新增主機、快速草稿與多主機建檔", True, "cmdb"),
    _flag("cmdb_network_scan", "網段掃描 / IPAM", "IPAM 網段管理、nmap 對帳與未納管清單", True, "cmdb"),
    _flag("cmdb_extension_fields", "擴充欄位", "資產管理自訂欄位與欄位定義", True, "cmdb"),
    _flag("cmdb_bulk_actions", "批次操作", "資產管理批次更新、套用管理者與備註", True, "cmdb"),
    _flag("cmdb_undo_30s", "30 秒復原", "資產刪除後短時間復原", True, "cmdb"),
    _flag("host_self_check", "單機自檢", "資產列表單台主機自檢按鈕與 API", True, "host"),
    _flag("host_self_check_global", "全域自檢", "資產管理批次或全域主機自檢", True, "host"),
    _flag("deep_check", "深度檢查", "Linux 主機 L3 深度檢查、Job、報告與 Remedy KB", True, "host"),
    _flag("deep_check_blackbox", "深度檢查黑箱", "深度檢查黑箱擴充，Phase 6 後啟用", False, "host"),
    _flag("host_debug_snapshot", "DEBUG 快照", "資產列表 DEBUG 快照按鈕與遮罩 API", True, "host"),
    _flag("host_security_audit_button", "安全按鈕", "資產列表安全稽核按鈕與主機資安入口", True, "host"),
    _flag("host_type_linux", "Linux", "Linux runner", True, "platform"),
    _flag("host_type_windows", "Windows", "Windows runner", True, "platform"),
    _flag("host_type_vmware", "VMware", "VMware/vCenter runner", False, "platform"),
    _flag("host_type_aix", "AIX", "AIX SSH runner", False, "platform"),
    _flag("host_type_as400", "AS400", "AS400 尚未支援，保留邊界", False, "platform"),
    _flag("external_api_v1", "對外 API v1", "Bearer Token API 與外部系統串接", True, "api"),
    _flag("ai_chat_panel", "AI 對話面板", "右下角 AI 對話視窗", False, "ai"),
    _flag("ai_mcp_server", "MCP Server", "MCP manifest 與工具清單", True, "ai"),
    _flag("ai_openapi_auto_doc", "OpenAPI 自動文件", "提供 AI 或外部系統讀取的 OpenAPI 文件", True, "ai"),
    _flag("ai_report_summary", "AI 報告摘要", "AI 輔助產生報告摘要", True, "ai"),
    _flag("ai_prompt_library", "提示詞庫", "AI 提示詞範本管理", True, "ai"),
    _flag("market_hours_protection", "盤中保護", "07:50-15:00 高風險變更管控", True, "system"),
    _flag("housekeeping_enabled", "Housekeeping", "系統清理排程", True, "system"),
    _flag("housekeeping_dry_run", "Housekeeping 試跑", "清理作業預設只試跑不刪除", False, "system"),
    _flag("backup_verify_enabled", "備份驗證", "備份檢查與還原驗證", True, "system"),
    _flag("disk_alert_enabled", "磁碟告警", "磁碟容量告警", True, "system"),
    _flag("audit_log_hash_chain", "操作紀錄 Hash Chain", "防竄改操作紀錄雜湊鏈", True, "system"),
    _flag("mfa_required", "MFA", "OTP/MFA 登入驗證；開發期間預設停用", False, "auth"),
    _flag("force_single_login", "單一登入", "同一帳號只允許一個有效登入", True, "auth"),
    _flag("dev_auto_login_superadmin", "開發自動登入最高管理員", "開發期間預設以最高管理員登入", True, "dev"),
    _flag("compliance_engine", "合規規則引擎", "合規規則比對與 finding 產生", True, "compliance"),
    _flag("compliance_account", "帳號規則", "帳號盤點合規規則", True, "compliance"),
    _flag("compliance_package", "套件規則", "軟體盤點與套件合規規則", True, "compliance"),
    _flag("compliance_port", "連接埠規則", "連接埠與網路服務合規規則", True, "compliance"),
    _flag("compliance_process", "程序規則", "程序與服務程序合規規則", True, "compliance"),
    _flag("compliance_file", "檔案規則", "重要檔案、權限與內容合規規則", True, "compliance"),
    _flag("compliance_ip", "IP 規則", "IP、網段與納管狀態合規規則", True, "compliance"),
    _flag("security_audit_whitebox", "白箱稽核", "登入主機後執行的安全稽核", True, "compliance"),
    _flag("security_audit_blackbox", "黑箱稽核", "從網路外部觀點執行的安全稽核", True, "compliance"),
    _flag("security_audit_blackbox_hydra", "Hydra 安全檢查", "密碼攻擊安全檢查占位功能", True, "compliance"),
    _flag("notify_email", "Email 通知", "Email 通知整合", True, "notify"),
    _flag("notify_slack", "Slack 通知", "Slack 通知整合", False, "notify"),
    _flag("notify_teams", "Teams 通知", "Teams 通知整合", False, "notify"),
    _flag("notify_jira", "JIRA 整合", "JIRA 工單整合", False, "notify"),
    _flag("phase_readonly_mode", "Phase 只讀模式", "雙寫評比期間禁止對受監控主機做寫入變更", True, "system"),
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
