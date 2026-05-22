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
from webapp.services.debug_bundle_service import ai_runtime_manifest, list_ai_debug_loops, list_debug_bundles
from webapp.services.feature_flags import DEFAULT_FLAGS
from webapp.services.housekeeping_service import disk_status
from webapp.services.mongo_service import get_db
from webapp.services.nmon_raw_service import nmon_raw_pipeline_status


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


RECENT_PATCH_RELEASES = [
    {
        "version": "1.0.2.97",
        "date": "2026-05-22 08:35 +08:00",
        "patch_id": "full-system-validation-artifacts",
        "changes": [
            "修復 SuperAdmin、使用者、健康檢查、Backup/DR 與 Patch 回滾頁面模板，恢復可渲染 UI。",
            "健康檢查 API 補上 host artifact 統計，功能驗證可透過遠端 API 確認 meta/self-check/debug snapshot 寫入。",
            "Backup manifest 對目錄權限問題回傳可稽核 warning，不讓 DR dry-run 直接 500。",
            "保留 Phase 只讀模式，受監控主機寫入動作仍由 phase_readonly_mode 封鎖。",
        ],
    },
    {
        "version": "1.0.2.96",
        "date": "2026-05-19 22:55 +08:00",
        "patch_id": "offline-onekey-install",
        "changes": [
            "新增離線一鍵安裝流程，支援既有 MongoDB、正式主機 CSV 匯入與不帶測試資料安裝。",
            "補齊離線 bundle 準備腳本與安裝文件，讓封閉環境可先準備 RPM / Python wheel 後部署。",
            "保留 Phase 只讀模式，平行評比期間不開放受監控主機寫入動作。",
        ],
    },
    {
        "version": "1.0.2.92",
        "date": "2026-05-19 07:25 +08:00",
        "patch_id": "full-system-package-metadata-sync",
        "changes": [
            "同步 overnight build 的版本、patch id、make_patch 預設套件名稱與功能驗證版本規則。",
            "保留 Phase 只讀模式，不開放受監控主機寫入動作。",
        ],
    },
    {
        "version": "1.0.2.91",
        "date": "2026-05-19 06:34 +08:00",
        "patch_id": "topology-overlay-unmanaged-scan",
        "changes": [
            "連線偵測圖自動疊加網段掃描未納管 IP 節點。",
            "讓系統拓撲能同時呈現 CMDB 內節點與掃描發現的待治理節點。",
        ],
    },
    {
        "version": "1.0.2.71",
        "date": "2026-05-18 07:55 +08:00",
        "patch_id": "opening-filesystem-mount-label",
        "changes": [
            "開門檢查檔案系統小卡改顯示最高使用率掛載點，例如 / 77% 或 /var 91%。",
            "保留臨時 75% WARN 門檻供畫面觀察；看完後再改回正式門檻。",
        ],
    },
    {
        "version": "1.0.2.70",
        "date": "2026-05-18 07:45 +08:00",
        "patch_id": "opening-disk-threshold-preview-75",
        "changes": [
            "臨時預覽版：開門檢查 Filesystem WARN 門檻由 85% 暫調為 75%，用來觀察 77% 會如何呈現。",
            "FAIL 門檻仍維持 95%。看完後可改回正式 85% 門檻。",
        ],
    },
    {
        "version": "1.0.2.69",
        "date": "2026-05-18 07:30 +08:00",
        "patch_id": "opening-disk-full-threshold",
        "changes": [
            "修正開門檢查檔案系統只看 rc=0 導致 DISK FULL 沒有轉成警示的問題。",
            "Filesystem 使用率 85% 以上標示 WARN，95% 以上標示 FAIL；77% 仍屬正常容量觀察值。",
            "舊的開門檢查紀錄在畫面 normalize 時也會重新依百分比判定，避免歷史資料仍顯示全綠。",
        ],
    },
    {
        "version": "1.0.2.68",
        "date": "2026-05-18 07:15 +08:00",
        "patch_id": "housekeeping-code-cache-scope",
        "changes": [
            "收斂 code_cache_purge 範圍，只清目前程式碼、scripts、tests、ansible、edge 與根目錄 .pytest_cache。",
            "避免正式清理掃到 venv、data、logs、backup 等不應歸類為程式碼快取的目錄。",
        ],
    },
    {
        "version": "1.0.2.67",
        "date": "2026-05-18 07:05 +08:00",
        "patch_id": "housekeeping-data-retention",
        "changes": [
            "Housekeeping 擴充到 Mongo 歷史資料、NMON raw file、主機資料、log/debug bundle 與正式程式碼快取。",
            "Mongo 清理採 collection 對應時間欄位與 retention days，不碰 hosts、users、feature_flags、api_tokens 內容與 audit_logs。",
            "NMON raw 檔保留 180 天，nmon_data 與 raw metadata 保留 400 天，讓效能月報與差異追蹤不斷層。",
        ],
    },
    {
        "version": "1.0.2.66",
        "date": "2026-05-18 06:45 +08:00",
        "patch_id": "housekeeping-postinstall-runner-fix",
        "changes": [
            "修正 scripts/run_housekeeping.py 直接執行時找不到 webapp package 的匯入路徑問題。",
            "部署後 post-install housekeeping 可正常執行，會清 /tmp 舊 patch 並保留最新 20 份回滾備份。",
        ],
    },
    {
        "version": "1.0.2.65",
        "date": "2026-05-18 06:35 +08:00",
        "patch_id": "housekeeping-retention-mechanism",
        "changes": [
            "Housekeeping 補上正式 patch 回滾備份保留機制，固定保留最新 20 份 preinstall 備份目錄。",
            "新增部署暫存清理，清除 /tmp 舊 webitgpt patch 解壓與 tarball 暫存。",
            "install.sh 部署後自動執行 post-install housekeeping，避免磁碟再次累積到 98%。",
        ],
    },
    {
        "version": "1.0.2.64",
        "date": "2026-05-17 23:55 +08:00",
        "patch_id": "dev-console-complete-release-notes",
        "changes": [
            "開發後台提交紀錄改為合併近期 patch release notes、CHANGELOG 與 git log，避免部署目錄不是完整 git repo 時紀錄不完整。",
            "補齊 v1.0.2.55 之後的主要修補紀錄，讓版本、時間、patch id 與變更摘要可追溯。",
        ],
    },
    {
        "version": "1.0.2.63",
        "date": "2026-05-17 23:45 +08:00",
        "patch_id": "nmon-ibm-profile",
        "changes": [
            "效能月報與 NMON 派送改以 IBM nmon -x 容量規劃採樣口徑為主。",
            "畫面、API、Ansible playbook 與文件明確顯示 nmon -x 等同 nmon -ft -s 900 -c 96。",
        ],
    },
    {
        "version": "1.0.2.62",
        "date": "2026-05-17 23:25 +08:00",
        "patch_id": "nmon-ansible-install-coverage",
        "changes": [
            "效能月報新增 NMON 安裝覆蓋率檢查。",
            "缺少 NMON 的 Linux 主機可由 Ansible playbook 派送安裝。",
        ],
    },
    {
        "version": "1.0.2.61",
        "date": "2026-05-17 22:55 +08:00",
        "patch_id": "dev-console-current-docs",
        "changes": [
            "開發後台文件改為產生目前系統狀態文件。",
            "補齊資產、帳號、開門檢查、NMON、AI debug loop、部署與模組旗標文件入口。",
        ],
    },
    {
        "version": "1.0.2.60",
        "date": "2026-05-17 22:45 +08:00",
        "patch_id": "nmon-monthly-report-completion",
        "changes": [
            "效能月報補齊月份、系統、環境、機房與搜尋篩選。",
            "新增 P95、採樣覆蓋率、主機熱區圖、CSV/JSON 與架構部數據摘要。",
        ],
    },
    {
        "version": "1.0.2.59",
        "date": "2026-05-17 22:25 +08:00",
        "patch_id": "ai-runtime-builder-manifest",
        "changes": [
            "開發後台新增 AI Runtime Manifest。",
            "把最小 AI debug loop 的流程、限制、輸入輸出與人工核准點寫成機器可讀 manifest。",
        ],
    },
    {
        "version": "1.0.2.58",
        "date": "2026-05-17 21:58 +08:00",
        "patch_id": "minimal-ai-debug-loop",
        "changes": [
            "建立最小 AI debug loop：公司 VM 產生去識別化 debug bundle，再交由 GPT Enterprise 分析。",
            "新增 prompt 產生與下載，並保留 dry-run、verbose debug 與 regression test 工作規則。",
        ],
    },
    {
        "version": "1.0.2.57",
        "date": "2026-05-17 21:32 +08:00",
        "patch_id": "nmon-raw-pipeline-debug",
        "changes": [
            "補強 NMON raw file pipeline 狀態，讓 debug bundle 能收集 NMON pipeline 摘要。",
            "開發後台可看到 raw file、raw sample 與 pipeline 狀態。",
        ],
    },
    {
        "version": "1.0.2.56",
        "date": "2026-05-17 21:19 +08:00",
        "patch_id": "gpt-enterprise-debug-bundle",
        "changes": [
            "新增去識別化 Debug Bundle，收集版本、設定摘要、錯誤 log、OS、Python、套件與服務狀態。",
            "敏感資訊遮蔽後才提供給 GPT Enterprise 分析。",
        ],
    },
    {
        "version": "1.0.2.55",
        "date": "2026-05-17 20:55 +08:00",
        "patch_id": "performance-monthly-architecture-report",
        "changes": [
            "效能月報改為系統架構部可閱讀的數字摘要版。",
            "報表口氣改為只呈現數字、趨勢與選項，讓主管自行決策。",
        ],
    },
    {
        "version": "1.0.2.54",
        "date": "2026-05-17 19:31 +08:00",
        "patch_id": "full-system-ui-repair",
        "changes": [
            "修復多個功能頁 UI 一致性、中文化、統計卡可點擊與表格操作問題。",
            "補強資產管理、帳號盤點、開門檢查與開發後台的主要操作入口。",
        ],
    },
]


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
            {"title": "資產治理狀態", "desc": "管理可信資產、未納管發現、等待防火牆、等待弱掃、等待 PAM 等治理狀態。", "endpoint": "api_superadmin.asset_governance_statuses_page", "status": "可設定"},
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
    host_root = Path(config.HOSTS_DIR)
    host_artifacts = {
        "root": str(host_root),
        "exists": host_root.exists(),
        "meta_files": 0,
        "self_check_files": 0,
        "debug_snapshot_files": 0,
    }
    if host_root.exists():
        host_artifacts.update(
            {
                "meta_files": len(list(host_root.glob("*/meta.json"))),
                "self_check_files": len(list(host_root.glob("*/self_check/*.json"))),
                "debug_snapshot_files": len(list(host_root.glob("*/debug_snapshots/*.json"))),
            }
        )
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
        "host_artifacts": host_artifacts,
    }


def create_backup_manifest(user: str = "system") -> dict[str, Any]:
    backup_dir = Path(config.BACKUP_DIR)
    now = datetime.now(timezone.utc)
    manifest = {
        "status": "ok",
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
        "path": str(backup_dir / f"backup_manifest_{now.strftime('%Y%m%d_%H%M%S')}.json"),
    }
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        target = Path(manifest["path"])
        target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    except OSError as exc:
        manifest["status"] = "warn"
        manifest["error"] = str(exc)
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
    ensure_current_dev_docs(docs_dir)
    notes_path = docs_dir / "dev_notes.md"
    if not notes_path.exists():
        notes_path.write_text("# 開發備忘錄\n\n- 這裡記錄人工補充的開發決策與待辦。\n", encoding="utf-8")
    try:
        git_result = subprocess.run(["git", "log", "--oneline", "-n", "20"], cwd=config.INSPECTION_HOME, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8)
        commits = git_result.stdout.strip() or git_result.stderr.strip()
    except Exception as exc:
        commits = str(exc)
    current_line = f"目前部署版本：v{config.VERSION} / {config.PATCH_ID} / {config.BUILD_TIME} / {config.RELEASE_NOTE}"
    if commits:
        commits = f"{current_line}\n\nGit log:\n{commits}"
    else:
        commits = f"{current_line}\n\nGit log：部署目錄沒有可讀取的 git log，請以 release note 與 patch 備份為準。"
    files = []
    for path in sorted(docs_dir.glob("*"))[:100]:
        files.append({"name": path.name, "size": path.stat().st_size, "mtime": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc), "kind": "文件" if path.suffix.lower() in {".md", ".txt"} else "檔案"})
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
        "debug_bundles": list_debug_bundles(),
        "ai_debug_loops": list_ai_debug_loops(),
        "ai_runtime_manifest": ai_runtime_manifest(),
        "nmon_raw_pipeline": nmon_raw_pipeline_status(),
    }


def ensure_current_dev_docs(docs_dir: Path) -> None:
    docs_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    docs: dict[str, str] = {
        "00_CURRENT_STATUS.md": f"""# itweb-gpt 目前狀態

版本：v{config.VERSION}
Patch：{config.PATCH_ID}
更新時間：{generated_at}
部署：{config.INSPECTION_HOME}
Web Port：{config.WEB_PORT}
Mongo DB：{config.MONGO_DB_NAME}

## 本版重點

- 資產管理系統：資產清冊、草稿、IPAM、網段掃描、資產治理狀態、真實 OS/hostname 更新流程。
- 帳號盤點：帳號清冊、主機角度、帳號角度、PAM 納管註記、差異報告與歷史批次。
- 開門檢查 / 深度檢查：L1 快速檢查、L3 深度檢查、9 面向、人類可讀摘要、Remedy 與原始證據分離。
- 效能月報：NMON raw file pipeline、月份/系統/環境/機房篩選、P95、採樣覆蓋率、主機熱區圖、CSV/JSON。
- 開發後台：Debug Bundle、AI debug loop、Runtime Manifest、模組管理、提交紀錄、檔案管理。

## 驗證入口

- 健康檢查：/health
- 效能月報：/nmon?period=month
- 開發後台：/superadmin/dev-console
- AI Runtime Manifest：/superadmin/dev-console/ai-runtime-manifest
""",
        "01_ASSET_MANAGEMENT.md": """# 資產管理系統

## 目的

建立可信任 CMDB，不只是一張主機表。主機名稱是唯一索引，資產編號保留為資產流水與對外識別。

## 目前功能

- 一台一行的密集清冊。
- 顯示資產名稱、hostname、IP、OS、設備類型、機櫃、環境、機房、備註。
- 編輯頁可維護完整資產主檔。
- IPAM 網段管理與網段掃描。
- 掃描結果可建立草稿，避免直接正式納管錯誤設備。
- 多筆刪除模式與下線/草稿狀態流程。
- 資產治理狀態：等待防火牆開通、等待弱掃完成、等待 PAM 納管、例外保留。

## 重要規則

- hostname / OS 應以實際採集結果為主。
- 人工匯入大量資料後，需透過掃描、SSH/WinRM/ssh_raw 或後續盤點校正可信度。
- Windows 若未配置 WinRM 憑證，只能由 nmap/TCP 服務推估，不能當作可信 OS。
- AIX 走 SSH Raw runner，AS400 目前保留後續協定支援。
""",
        "02_ACCOUNT_INVENTORY.md": """# 帳號盤點

## 目的

解決主管與稽核最常問的問題：哪台主機有哪些帳號、誰負責、是否高權限、是否納入 PAM、是否異常。

## 目前功能

- 帳號清冊、主機角度、帳號角度、合規、變更、處置、清冊。
- 可依主機、部門、風險、搜尋條件篩選。
- 統計格可點擊後在下方顯示細項，不把畫面捲到最底。
- 系統預設帳號可隱藏；root 永遠列管。
- PAM 納管、管理者/保管人、用途說明可維護。
- 差異報告可比對新增、移除、變更。

## 判斷口徑

- 從未登入不直接算問題。
- 服務帳號可登入顯示為「服務帳號可登入，需複核」。
- 高權限帳號不是一定錯，但需要負責人與用途說明。
""",
        "03_OPENING_AND_DEEP_CHECK.md": """# 開門檢查與深度檢查

## 開門檢查

用於每天快速確認系統是否能營運。可用系統角度執行，不一定每台主機都做。

## 深度檢查

用於單台主機 L3 診斷。Linux、RHEL、Debian、CentOS、AIX 方向都要支援；Windows 與 AS400 依 runner 分階段補齊。

## 顯示原則

- 小卡只顯示人類看得懂的重點，不直接塞 raw output。
- PASS 也要有證據，例如 CPU、MEM、SWAP、Filesystem、IO 或帳號鎖定數。
- WARN 要說明：問題點、證據、影響、可執行指令。
- raw data 放在原始證據、下載明細或 API。

## 例外管理

系統日誌可設定白名單 / 例外管理，避免已知非 AP 事件每天造成誤報。
""",
        "04_NMON_PERFORMANCE_MONTHLY.md": """# 效能月報

## 定義

效能月報是給主管與維運共同使用的容量與趨勢報表。資料來源包含 NMON raw file pipeline 與系統既有 nmon_data 採樣。

## 目前功能

- 日報 / 週報 / 月報。
- 月份、系統、環境、機房、搜尋篩選。
- NMON raw file 匯入與 pipeline 狀態。
- NMON 安裝覆蓋率檢查；缺少時可從效能月報用 Ansible 派送安裝。
- IBM nmon 採樣口徑：使用 `nmon -x`，等同 `nmon -ft -s 900 -c 96`。
- 平均 CPU / 記憶體 / 磁碟。
- CPU / 記憶體 / 磁碟尖峰。
- 主機排名：平均 / P95 / Max。
- 採樣覆蓋率。
- 主機熱區圖。
- 風險追蹤清單與可選處理方式。
- CSV / JSON 匯出。

## 注意

目前沒有資料時不做假資料；報表會顯示待採樣或無資料。

## NMON 派送

- Linux 主機：使用 Ansible playbook `ansible/playbooks/install_nmon.yml` 安裝。
- 派送後會建立 `/usr/local/sbin/webitgpt_nmon_collect.sh`。
- 派送後會建立 `/etc/cron.d/webitgpt-nmon`，每日 00:05 產生 24 小時 `.nmon` raw file。
- raw file 存放於 `/var/log/nmon`，再由本系統 raw pipeline 匯入月報。
- 採樣依 IBM nmon recording mode：`nmon -x`；等同 15 分鐘一筆、96 筆、含 top process 的 spreadsheet raw 檔。
- AIX：保留 ssh_raw runner 後續接入。
- Windows / AS400：不使用 nmon，需走各平台自己的採樣方式。
""",
        "05_AI_DEBUG_LOOP.md": """# AI Debug Loop

## 目的

公司 VM 產生去識別化 Debug Bundle，GPT Enterprise 只負責分析，不直接連 VM。

## 流程

1. 在開發後台輸入問題標題與描述。
2. 系統產生 Debug Bundle。
3. 系統產生 GPT Enterprise prompt。
4. 人工下載 prompt 與 bundle。
5. 貼到 GPT Enterprise 分析。
6. Codex 依分析修 code。
7. 補 regression test。
8. 重新部署到 VM 驗證。

## 安全規則

- IP、hostname、username、password、token、private key 會遮蔽。
- 真實 DEV log 只用 GPT Enterprise。
- 個人 GPT Pro 不接觸公司 VM log。
- GPT 不直接連線 VM。
- 部署、刪除、憑證調整與破壞性動作需人工確認。
""",
        "06_DEPLOY_AND_VERIFY.md": f"""# 部署與驗證

## 部署目標

- 路徑：{config.INSPECTION_HOME}
- Web：port {config.WEB_PORT}
- Edge：port {config.EDGE_PORT}
- DB：{config.MONGO_DB_NAME}

## 基本驗證

```bash
curl -fsS http://127.0.0.1:{config.WEB_PORT}/health
cd {config.INSPECTION_HOME}
./venv/bin/python -m pytest tests/test_ui_contracts.py tests/test_nmon_raw_service.py tests/test_app.py -q
```

## Patch 原則

- 版號只能使用 1.X.X.X。
- 第二、三、四段不得超過 99。
- 每次 patch 要更新 VERSION、PATCH_ID、RELEASE_NOTE、BUILD_TIME。
""",
        "07_MODULE_FLAGS.md": """# 模組管理與功能開關

## 目的

讓未完成的大功能可以整體關閉，避免使用者看到半成品。

## 使用方式

- 到開發後台 → 模組管理。
- 大模組可控制一群子功能，例如合規與資安。
- 子功能會顯示控制範圍、關閉影響、建議狀態。

## 原則

- 未完成、未測完、不想開放給一般使用者時先關閉。
- 沒權限的角色不應看到對應入口或操作按鈕。
- Debug、資安、自檢等高風險功能應限制 admin / superadmin。
""",
    }
    for name, content in docs.items():
        target = docs_dir / name
        target.write_text(content, encoding="utf-8")


def release_notes(limit: int = 12) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen_versions: set[str] = set()
    for item in RECENT_PATCH_RELEASES:
        if item["version"] in seen_versions:
            continue
        entries.append({**item})
        seen_versions.add(item["version"])
        if len(entries) >= limit:
            return entries

    candidates = [
        Path(config.INSPECTION_HOME) / "CHANGELOG.md",
        Path(__file__).resolve().parents[2] / "CHANGELOG.md",
    ]
    changelog = next((path for path in candidates if path.exists()), None)
    if not changelog:
        return entries[:limit]

    def clean_release_text(value: str) -> bool:
        return "\ufffd" not in value and "??" not in value

    current: dict[str, Any] | None = None
    heading = re.compile(r"^## v(?P<version>\S+) - (?P<date>.+?) - (?P<patch_id>\S+)")
    for line in changelog.read_text(encoding="utf-8", errors="replace").splitlines():
        matched = heading.match(line)
        if matched:
            if current and current.get("changes"):
                if current.get("version") not in seen_versions:
                    entries.append(current)
                    seen_versions.add(current.get("version", ""))
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
    if current and current.get("changes") and current.get("version") not in seen_versions and len(entries) < limit:
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

