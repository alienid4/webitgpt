# webitgpt Changelog

## v1.0.3.43 - 2026-05-29 09:35 +08:00 - host-draft-save-error-guard

- 主機新增與草稿補資料儲存若遇到非預期例外，不再顯示 Internal Server Error 白頁。
- 新增/編輯表單會保留使用者輸入並顯示「儲存失敗」原因，方便現場修正。
- server log 會記錄 `host_new_submit failed` 或 `host_edit_submit failed` traceback，方便後續排錯。

## v1.0.3.42 - 2026-05-28 00:25 +08:00 - ai-ready-pale-gold-contrast

- AI-ready / 可交給 AI 判讀的區塊改用淡金框，與真正 AI 判斷的深金框分離。
- 帳號盤點、AI 供應商、Token 成本、Dashboard、報表、資料品質、NMON、拓撲與 CMDB 匯入統一使用 `AI-ready` 淡金標示。
- L3 深度檢查與安裝後驗證的 AI 判斷卡保留深金框，代表實際 AI 判斷。

## v1.0.3.41 - 2026-05-28 00:15 +08:00 - static-asset-cache-busting

- CSS 與主要 JavaScript 靜態檔加入 `?v={{ asset_version }}`，避免瀏覽器快取舊樣式造成 UI patch 看起來沒變。
- `asset_version` 由目前 `VERSION` 與 `PATCH_ID` 組成，每次版號變更會自動刷新樣式與腳本。
- 帳號盤點、資產管理、效能月報、巡檢、備份、housekeeping 等頁面腳本同步加入版本參數。

## v1.0.3.40 - 2026-05-28 00:05 +08:00 - ai-judgement-visual-contrast

- 帳號盤點、AI 供應商與 Token 成本頁改用三段式判斷來源卡，不再只是一排 badge。
- AI 判讀使用金框與 AI 圓標，Script 使用灰框，資料/規則使用綠框，fallback 使用琥珀框。
- 帳號盤點新增來源流程：Shell / Script 採證 → CSV / Excel 匯入 → PAM / owner 規則 → L3 AI 判讀 → 規則接手。

## v1.0.3.39 - 2026-05-27 23:55 +08:00 - ai-key-budget-tier-routing

- AI 供應商設定加入 L1/L2/L3 KEY 階級，可分別設定模型、月預算與可支援檢查層級。
- Token 成本頁新增預算路由狀態，讓管理者看到目前費用、月預算、超額策略與 KEY 階級。
- 新增 KEY 路由預覽 API；超額時可降級、停用 AI 或 Script fallback，不影響既有 Script / Rule 判斷。

## v1.0.3.38 - 2026-05-27 23:45 +08:00 - global-judgement-source-visibility

- 維運總覽、統計報表、資料品質、CMDB 匯入、NMON、核心影響圖與帳號盤點加入判斷來源圖例。
- 統一顯示 CMDB、Script、Rule、API、NMON、AI-ready、AI + Script 與 fallback badge。
- API Key 尚未設定時，UI 明確表示仍由既有 Script / Rule / NMON / CMDB 判斷保底，不阻斷維運流程。

## v1.0.3.37 - 2026-05-27 23:20 +08:00 - ai-judgement-gold-frame-ui

- 安裝後驗證頁新增金框 AI 判斷卡，讓使用者一眼看出 AI 判讀與 Script/API Key 檢查不同。
- L3 深度檢查區塊套用金框 AI-ready 樣式，標示 Shell 採證 + AI 判讀與 Script 保底接手。
- 新增 AI、AI + Script、Script 接手 badge，可重用在後續報表、深度檢查與 API 分析結果。

## v1.0.3.36 - 2026-05-27 22:50 +08:00 - ai-judgement-source-ux

- 新增 AI 判斷來源視覺規格：Script、API Key、AI、AI + Script、Script 接手與證據不足。
- 定義核心原則：Shell 負責採證，AI 負責判讀；AI 不可用時，Script 保底接手。
- 架構簡報加入 AI 判斷來源與 fallback 設計，作為後續 L1/L2/L3 深度檢查與 Debug 模式的 UI/UX 基準。

## v1.0.3.35 - 2026-05-27 13:45 +08:00 - cmdb-import-fast-feedback

- CMDB 匯入結果不再把完整錯誤陣列直接渲染到頁面，避免大量錯誤列讓瀏覽器看起來卡住。
- 匯入結果新增耗時顯示，方便判斷匯入是否完成。
- 單次 UI 匯入上限保護為 2000 筆，超過時回報人可讀原因並要求拆批。

## v1.0.3.34 - 2026-05-27 11:45 +08:00 - cmdb-import-report-excel-drafts

- CMDB 匯入結果新增總筆數、成功、新增、更新、草稿與失敗摘要，讓大量匯入失敗可一眼看出主因。
- 資產匯入支援 `.xlsx`，並新增 Excel 匯出；CSV 範本、匯出與錯誤下載補 UTF-8 BOM，降低 Excel 開啟亂碼。
- 草稿區新增批次轉正式與批次補欄位，適合 nmap/IPAM 建立草稿後集中處理。
- API 補 `/api/hosts/xlsx/import`、`/api/hosts/xlsx/export`、`/api/hosts/xlsx/validate` 與 `.xlsx` 錯誤下載。

## v1.0.3.33 - 2026-05-27 10:45 +08:00 - cmdb-real-fields-scan-visibility

- CMDB 匯入支援真實中文欄位：總點單位、資產序號、APID、主機名稱、IP、備份頻率、資料保存、備份方式、CIA 與申請單編號。
- 網段掃描報告新增「掃描實際發現、CMDB 已納管、未納管待建檔、畫面列出筆數」，避免現場以為只掃到一台。
- TCP 掃描 port 範圍補齊 FTP、AD、LDAP、RDP、webitgpt 8002、app 5000 與 50000 系列服務。

## v1.0.3.32 - 2026-05-27 00:15 +08:00 - api-key-verify-visibility

- 安裝後驗證頁新增「API Key 驗證」與「Script 檢查」兩種模式卡，使用者可一眼辨識判斷來源。
- API Key 模式明列 `system:read` scope、`verification_source=api_key` 回應標記與 curl 範例。
- `/api/v1/post-install/verify` 回應新增 `verification_source`、`verification_label` 與 `required_scope`。

## v1.0.3.31 - 2026-05-26 23:45 +08:00 - api-key-post-install-verify

- 新增 `/api/v1/post-install/verify`，需使用 Bearer API Token 且具備 `system:read` scope。
- `post_install_verify.sh` 支援 `API_TOKEN=wgpt_xxx` 模式，可用 API Key 判斷版本、Mongo 與資料品質 API。
- 安裝後驗證頁補 API Key 模式指令，API Token 表單預設 scope 加入 `system:read`。

## v1.0.3.30 - 2026-05-26 23:30 +08:00 - reports-next-action-entry

- 統計報表新增「下一步要做什麼」操作區，直接引導到資料品質、帳號盤點、核心影響圖與交付匯出。
- 報表主按鈕改成「看下一步」，避免使用者停在數字摘要不知道要點哪裡。
- 補響應式樣式，手機與窄螢幕仍能清楚顯示操作卡。

## v1.0.3.29 - 2026-05-26 23:10 +08:00 - ops-ux-decision-workbench

- 維運總覽改成先看風險與資料品質分數，再進入帳號、拓撲與安裝驗證。
- 新增資料品質工作台頁面與安裝後驗證頁，讓 API/腳本結果有可讀 UI 入口。
- 統計報表改為決策摘要優先，降低亂碼頁面的第一眼壓力。

## v1.0.3.28 - 2026-05-26 23:00 +08:00 - post-install-report-ui

- 新增安裝後驗證 UI，列出 health、ready、帳號頁、AP 模板、核心影響圖與資料品質檢查。
- 頁面提供可直接執行的 post_install_verify.sh 指令。

## v1.0.3.27 - 2026-05-26 22:50 +08:00 - core-impact-decision-language

- 核心影響圖延續可信度摘要，將來源語意收斂成維運可判斷的 manual、auto、unknown。
- 右側面板定位為事故/維護決策面板。

## v1.0.3.26 - 2026-05-26 22:40 +08:00 - ap-account-risk-first-ux

- AP 帳號頁維持風險分類在清冊前方，讓使用者先看缺 owner、PAM、MFA 與待複核。
- 風險標籤與匯出語意保持一致。

## v1.0.3.25 - 2026-05-26 22:30 +08:00 - data-quality-workbench-ui

- 新增資料品質工作台頁面，顯示品質分數、CMDB 待修、AP 待複核與每項修正建議。
- 維運總覽新增資料品質入口。

## v1.0.3.24 - 2026-05-26 22:20 +08:00 - ops-dashboard-readable-copy

- 維運總覽與統計報表改用可讀中文主標、摘要與空狀態文案。
- 新增決策式版面，避免第一眼被明細表格淹沒。

## v1.0.3.23 - 2026-05-26 22:10 +08:00 - operations-quality-hardening

- 補齊維運安全門檻文件，安全修補、停用帳號與 rollback 仍需 phase_readonly_mode 與正式 approval。
- 整併 AP 帳號風險、資料品質、安裝驗證、UI 文案與拓撲可信度強化為可部署版本。

## v1.0.3.22 - 2026-05-26 22:00 +08:00 - topology-trust-source

- 核心影響圖新增 trust_summary 與 trust_note，標示 manual、auto、unknown 關係來源。
- 右側影響面板顯示可信度摘要，避免只看圖形卻不知道資料來源。

## v1.0.3.21 - 2026-05-26 21:50 +08:00 - ui-text-cleanup-map

- 新增 UI 文案整理基準，避免後續新功能繼續帶入亂碼或不清楚的操作語意。
- AP 帳號風險語意使用可讀中文標籤。

## v1.0.3.20 - 2026-05-26 21:40 +08:00 - post-install-verification

- 新增 post_install_verify.sh，安裝後可檢查 health、ready、accounts、AP template、核心拓撲與資料品質 API。
- 驗證腳本支援 EXPECTED_VERSION，方便離線移植後確認版本一致。

## v1.0.3.19 - 2026-05-26 21:30 +08:00 - operations-data-quality

- 新增 operations data quality API，彙整 CMDB、AP 帳號與拓撲通知 owner 缺口。
- 新增資料品質 CSV，讓維運可匯出待修項目。

## v1.0.3.18 - 2026-05-26 21:20 +08:00 - ap-account-risk-rules

- AP 帳號新增缺 owner、高權限未納 PAM、高權限未啟用 MFA、共用帳號與 180 天未登入風險。
- AP 帳號頁新增風險分類表與中文 risk label。

## v1.0.3.17 - 2026-05-26 18:20 +08:00 - ap-account-cmdb-runner-readonly-roadmap

- 整併 v1.0.3.12 到 v1.0.3.17 的安全可落地項目，保留 phase_readonly_mode，不直接開放受監控主機寫入。
- 安全稽核、修補、停用帳號維持 dry-run / rollback plan / blocked-by-phase-readonly 語意，作為後續正式驗收入口。
- RHEL 9.6 離線包可沿用 TARGET_OS_LABEL 產生 target package。

## v1.0.3.16 - 2026-05-26 18:10 +08:00 - batch-self-check-runner-guard

- 批次自檢支援 JSON body limit，並將單次上限收斂到 20 台，避免誤觸大量連線。
- 批次 runner 增加 timeout/error 結果列，單台失敗不阻斷整批結果。

## v1.0.3.15 - 2026-05-26 18:00 +08:00 - cmdb-csv-validation-governance

- 新增 CMDB CSV 預檢 API，檢查必要欄位、重複 asset_seq、數字欄位與 host_type warning。
- 新增 CSV 預檢錯誤匯出，方便匯入前先修資料。

## v1.0.3.14 - 2026-05-26 17:50 +08:00 - core-impact-readability-tune

- 核心系統影響圖右側面板補強內距與清單間距，提升三欄式與影響清單掃讀性。
- 延續 v1.0.3.10 的焦點系統範圍修正，選 SYS 時維持只看該系統直接關係。

## v1.0.3.13 - 2026-05-26 17:40 +08:00 - ap-account-report-ui

- 帳號盤點新增 AP 帳號頁籤，依 AP 系統、帳號數、高權限、缺 owner、PAM 與待複核彙整。
- 提供 AP 帳號清冊、差異清單、CSV 匯出，讓主管可直接看應用程式帳號風險。

## v1.0.3.12 - 2026-05-26 17:30 +08:00 - ap-account-import

- 新增 AP 帳號 CSV / Excel 模板與匯入流程，必填 app_id、system_name、account。
- owner、PAM、權限、最後登入等欄位允許空白；缺 owner 或高權限未納 PAM 會列為 review 而不阻擋匯入。
- 新增 AP 帳號批次、明細與差異資料模型。

## v1.0.3.11 - 2026-05-26 16:55 +08:00 - rhel96-offline-target-package

- 完整離線包支援 `TARGET_OS_LABEL`，包名、README 與 prerequisite manifest 會標示目標 OS。
- RHEL 9.6 新機移植可產生清楚標記的 target package，避免與 Rocky/RHEL 9.7 包混淆。
- release note 明確記錄 build OS 與 target OS；若正式要求完全同版 RPM，請在 RHEL 9.6 build host 重建。

## v1.0.3.10 - 2026-05-26 08:25 +08:00 - core-impact-system-focus-scope

- 修正核心系統影響圖選取單一系統時仍把同核心全部系統畫出的問題。
- 選核心時維持核心總覽；選系統時只顯示焦點系統、直接關聯與主機 / IP。
- 右側影響面板新增「檢視口徑」，讓核心總覽與焦點系統口徑更清楚。

## v1.0.3.9 - 2026-05-26 08:15 +08:00 - core-impact-notification-export

- 核心系統影響圖新增三欄背景與更明確欄名，讓核心、關聯系統、主機 / IP 更容易掃讀。
- 右側影響面板新增待通知對象摘要，顯示系統 owner、主機數與聯絡狀態。
- 新增核心影響通知名單 CSV 匯出，避免「匯出通知名單」只回傳 JSON。

## v1.0.1.59 - 2026-05-13 12:15 +08:00 - topology-filter-hidden-data

- 拓撲預設不再把未納管內網與外網對帳明細輸出到 HTML，避免展開或搜尋時仍看到非 CMDB 主機。
- ss+nmap 對帳摘要改顯示「可見差異」與已收合筆數，讓管理者知道資料被收起而非消失。
- 全螢幕狀態下隱藏「全螢幕」按鈕，只保留「離開全螢幕」，避免狀態不明顯。

## v1.0.1.58 - 2026-05-13 11:50 +08:00 - topology-clean-reconcile

- ss+nmap 對帳頁預設只顯示摘要，逐筆 IP/Port 明細改收合在「展開對帳明細」。
- 避免未納管或外網位址直接出現在主畫面，被誤認為 CMDB 測試假資料仍存在。

## v1.0.1.57 - 2026-05-13 11:30 +08:00 - topology-clean-fullscreen

- 修正拓撲前端全螢幕，進入全螢幕時隱藏上方導覽、頁尾與提示窗，避免看起來仍停在一般頁面。
- 拓撲預設只顯示 CMDB 已納管主機，內網未納管節點改由「顯示內網未納管」開關手動打開。
- 保留 Ghost/未納管資料，不刪除採集證據，但主畫面預設維持乾淨，避免誤以為測試假資料還在。

## v1.0.1.56 - 2026-05-13 11:05 +08:00 - topology-human-status

- 改善拓撲採集狀態列，把批次編號與 ISO 時間改成人能閱讀的中文狀態。
- 主畫面改顯示「資料來源、最後採集、關聯線、最近執行」，技術 run id 收進可展開的「技術資訊」。
- ss+nmap 對帳狀態同步改成中文摘要，避免工程編號直接干擾閱讀。

## v1.0.1.55 - 2026-05-13 10:45 +08:00 - topology-fullscreen-toggle

- 修正拓撲「全螢幕」按鈕，改成點擊後直接把目前拓撲面板切成固定全螢幕，不再只靠跳轉全螢幕網址。
- 加入「離開全螢幕」按鈕、Esc/browser fullscreen change 後自動還原頁面捲動。
- 保留「全螢幕頁」備援連結，避免瀏覽器封鎖 Fullscreen API 時完全無路可用。

## v1.0.1.54 - 2026-05-13 10:20 +08:00 - topology-fullscreen-real

- 修正拓撲全螢幕模式，讓全螢幕面板覆蓋整個視窗寬高。
- 全螢幕拓撲畫布改為吃滿可用高度，不再像一般頁面卡片只是變高。
- 壓縮全螢幕下方關聯清單高度，保留主要空間給拓撲圖。

## v1.0.1.53 - 2026-05-13 10:05 +08:00 - topology-action-feedback

- 拓撲「立即 ss 採集」按鈕改為回頁面顯示 run id、狀態與最近錯誤，避免看起來像沒反應。
- `ss+nmap 對帳` 按鈕回頁面顯示對帳 run id 與結果筆數。
- 新增卡住採集自動清理，超過 15 分鐘仍為 running 的 run 會標記 failed 並留下錯誤訊息。
- 採集流程加上最後防線，非預期例外不再留下永久 running 狀態。

## v1.0.1.52 - 2026-05-13 09:40 +08:00 - topology-third-hop-fake-data

- 系統拓撲新增 `第四層：IP 三跳`，可呈現二跳後再延伸到第三個 IP hop 的關係。
- 三跳若命中已納管主機，會補上「三跳回接系統」關聯，讓跨系統回接不會只停在 IP。
- 50 台假資料新增 10 組三跳鏈：來源系統主機 → 中介 IP → 中介 IP → 另一套系統主機。

## v1.0.1.51 - 2026-05-13 09:15 +08:00 - topology-layered-system-ip

- 系統視角加入三層拓撲模式：第一層顯示系統對系統，第二層展開 IP 一跳，第三層再追 IP 二跳。
- 第二層資料由 CMDB 主機 IP 與 ss evidence 產生；第三層會從一跳 IP 再追一層關聯。
- 拓撲圖新增層級導引線，讓系統、IP 一跳、IP 二跳不再混在同一層。
- 深度選單改成明確文字：第一層、第二層、第三層。

## v1.0.1.50 - 2026-05-13 08:45 +08:00 - topology-system-trunks

- 主機視角改為「一個系統一條樹幹」，每套系統以縱向主幹呈現，主機掛載在該系統旁邊。
- 跨系統連線仍以 ss 採集關聯畫線，Port 顯示與 Ghost 標示沿用既有控制。
- 主機視角說明改成中文描述系統分組邏輯，讓使用者知道目前不是單純 hostname 平鋪。

## v1.0.1.49 - 2026-05-13 08:20 +08:00 - topology-tree-layout

- 拓撲圖改為階層樹狀布局，來源節點在左側，相關節點依層級往右展開，較接近大型系統關聯圖的閱讀方式。
- 畫布寬高改由後端布局計算，節點多時自動加高，不再硬塞固定 1100x520。
- Port 標籤改用線段偏移座標，降低與節點、線段文字互相蓋住的機率。
- 拓撲頁文字重整為中文，並支援點選節點直接帶入故障模擬。

## v1.0.1.48 - 2026-05-13 07:45 +08:00 - ghost-ignore-ui

- 修復 Ghost 清單在顯示外網後只能切回「忽略外網」、不能忽略單一外網 IP 的 UI 缺口。
- 新增 `/dependencies/ghosts/<ip>/ignore` 頁面操作，會寫入 `dependency_ghost_ignored` 並保留 audit log。
- 重整 Ghost 清單中文欄位，補上每筆 Ghost 的「忽略」按鈕。

## v1.0.1.47 - 2026-05-13 07:28 +08:00 - fake-data-topology-seed

- 新增 `scripts/seed_fake_environment.py`，可建立/刪除/查詢同一批 50 台假資產、10 個測試網段、10 套測試系統與 50 條拓撲關聯。
- 假資料使用 `codex_fake_50_20260513` batch 標記，後續可精準清除，不影響正式 221/222/223 主機。
- 修正拓撲系統視角合併多條 evidence 時呼叫錯誤函式，避免大量假資料時系統視角 500。

## v1.0.1.46 - 2026-05-13 02:05 +08:00 - topology-ss-nmap-reconcile

- 拓撲新增 `ss+nmap` 聯通驗證：以最新 `ss -tunp` 採集結果對照 nmap port scan。
- 新增差異分類：雙方一致、ss 有但 nmap 掃不到、nmap 有但 ss 沒看到、外網未掃描。
- 新增 Mongo 報告集合 `dependency_reconcile_reports`，保留每次驗證結果供後續比較與稽核。

## v1.0.1.45 - 2026-05-13 01:18 +08:00 - topology-impact-detail-panel

- 拓撲故障模擬新增右側詳情面板，顯示故障節點、IP/OS、系統、一跳/二跳影響與關聯 Port。
- 新增「只看一/二跳影響」聚焦模式，讓大拓撲只保留故障節點附近的上下游關係。
- 聚焦模式會重新排版節點，降低大圖線條與文字重疊。

## v1.0.1.44 - 2026-05-13 01:02 +08:00 - topology-failure-simulation

- 系統拓撲新增「故障模擬」欄位，可輸入主機、系統或 IP 節點，假裝該節點故障。
- 拓撲節點可直接點選套用故障模擬；紅色為故障節點、橘色為下游受影響、灰色為上游/關聯來源。
- 模擬只影響畫面與 API 回傳標示，不會真的關機、斷線或修改受監控主機。

## v1.0.1.43 - 2026-05-13 00:44 +08:00 - topology-fullscreen-toolbar-compact

- 壓縮全螢幕拓撲工具列欄位寬度，避免控制項垂直堆疊吃掉圖面空間。
- 下方聯通清單固定為較小高度，中間拓撲圖保留更多可視區域。

## v1.0.1.42 - 2026-05-13 00:36 +08:00 - topology-fullscreen-layout-fix

- 修正全螢幕拓撲在視窗高度不足時，圖面與「聯通清單」互相重疊的版面問題。
- 全螢幕改為三段式固定工作區：標題列、拓撲圖、聯通清單，讓中間圖面自行捲動。

## v1.0.1.41 - 2026-05-13 00:28 +08:00 - topology-fullscreen-mode-fix

- 修復系統拓撲「全螢幕」入口只有普通頁面效果的問題，改為覆蓋式全螢幕工作區。
- 全螢幕模式保留目前視角、中心節點、深度、外網未知節點與 Port 顯示設定，切換條件後不會跳回普通頁。
- 導覽列在全螢幕拓撲頁仍標示「系統拓撲」為目前位置，避免使用者迷路。

## v1.0.1.40 - 2026-05-13 00:12 +08:00 - topology-port-label-offset

- 拓撲 Port 標籤改為顯示在節點上方，避免長連線穿過中間節點時文字被蓋住。
- 圖上只放短標籤，例如 `SSH 22`；完整 `SSH 22 -> 39950` 仍保留在 tooltip 與下方聯通清單。

## v1.0.1.39 - 2026-05-13 00:05 +08:00 - topology-port-label-overlap-fix

- 拓撲短線上的 Port 標籤改顯示服務簡稱，例如 `SSH`，避免完整 `SSH 22 -> 39950` 被節點蓋住。
- 完整 Port 仍保留在 tooltip 與下方聯通清單。

## v1.0.1.38 - 2026-05-12 23:52 +08:00 - topology-port-label-toggle

- 拓撲新增「圖上顯示 Port」開關，預設保持乾淨，打開後在線條中央顯示 Port。
- 常見 Port 會轉成服務名稱，例如 `22` 顯示 `SSH`、`443` 顯示 `HTTPS`、`27017` 顯示 `MONGO`。
- 下方聯通清單仍保留完整 Port、程序、次數與最後看到時間。

## v1.0.1.37 - 2026-05-12 23:38 +08:00 - topology-auto-apply-view

- 拓撲視角、深度與外網未知節點開關改為切換後自動套用。
- 避免下拉選單已顯示 IP 視角，但圖面仍停留在上一個視角造成誤判。

## v1.0.1.36 - 2026-05-12 23:21 +08:00 - topology-distinct-views

- 拓撲三視角拆成不同資料粒度：系統視角彙總主機連線到系統，主機視角顯示 hostname，IP 視角改為純 IP/Port。
- 系統視角會把 ss 採集到的主機連線回推到業務系統節點，避免只看到孤立節點。
- 拓撲頁新增視角說明，IP 節點與外網未知節點使用不同樣式，避免三個視角看起來一樣。

## v1.0.1.35 - 2026-05-12 23:02 +08:00 - topology-ignore-external-ghosts

- 拓撲與 Ghost 清單預設忽略外網未知節點，只標示內網未納管對端。
- 新增「顯示外網未知節點」切換與 `include_external=1` API 參數，必要時仍可查外網連線。
- Ghost 清單新增「範圍」欄位，區分內網與外網。

## v1.0.1.34 - 2026-05-12 22:46 +08:00 - topology-preserve-last-success

- 拓撲採集遇到部分主機失敗時不覆蓋上一個成功快照，避免半套資料洗掉原本可用拓撲。
- 採集結果新增 `snapshot_replaced`，方便判斷本次是否真的更新畫面資料來源。

## v1.0.1.33 - 2026-05-12 22:38 +08:00 - topology-local-collector-fix

- 修正 221 本機拓撲採集改走本機 `ss -tunp`，不再 SSH 自己造成 permission denied。

## v1.0.1.32 - 2026-05-12 22:28 +08:00 - topology-ss-snapshot-source

- 拓撲線條改為只讀最後一次成功 `ss -tunp` 採集快照，未採集前不再用 CMDB 歸屬產生假連線。
- 新增拓撲採集按鈕與採集狀態，採集失敗時保留上一版成功快照。
- `dependency_collect_runs` 記錄採集版本，`dependency_relations` 的 auto 關聯改帶 run_id、Port、process 與 last_seen evidence。

## v1.0.1.31 - 2026-05-12 22:12 +08:00 - topology-edge-labels-off

- 拓撲圖關閉線上 Port/關係文字，避免多條線靠近時文字仍然黏在一起。
- Port、程序、次數、最後看到時間集中放在下方「聯通清單」，圖上只保留方向與關係線。

## v1.0.1.30 - 2026-05-12 22:02 +08:00 - topology-port-detail-no-overlap

- 拓撲圖不再把每條線的 Port 文字常駐畫在線上，避免大量連線時文字疊在一起。
- Port、程序、次數、最後看到時間改放在滑鼠提示與下方「聯通清單」明細表。

## v1.0.1.29 - 2026-05-12 21:38 +08:00 - topology-clean-legacy-unknown

- 清理前一版拓撲同步留下的 `SYS-UNKNOWN` 重複系統節點。
- 系統同步時若同名中文系統已有新版 hash system_id，會移除舊版 unknown 節點。

## v1.0.1.28 - 2026-05-12 21:32 +08:00 - topology-chinese-system-id

- 修正中文系統名稱在拓撲同步時被轉成 `SYS-UNKNOWN` 的問題。
- 中文或非英數系統名稱改用穩定 SHA1 短碼產生 system_id，避免不同中文系統互相覆蓋。

## v1.0.1.27 - 2026-05-12 21:20 +08:00 - topology-spec-foundation

- 依 `topology.md` 補上拓撲模組骨架：system / host / ip 三視角、Systems CRUD、Relations CRUD、Topology API、Impact API、Ghost API。
- 新增 Mongo collections 與 indexes：`dependency_systems`、`dependency_relations`、`dependency_collect_runs`、`dependency_ghost_ignored`。
- `/dependencies` 改由拓撲服務供資料，支援視角切換、中心節點、深度、Ghost 清單與全螢幕入口。
- 目前採集器仍為安全骨架，`ss -tunp` read-only runner 尚未接入。

## v1.0.1.26 - 2026-05-12 09:55 +08:00 - topology-zoom-controls

- 拓撲互動圖新增縮小、放大、重設與目前倍率顯示。
- 拓撲畫布預設 80% 顯示，並支援滑鼠拖曳移動畫布與 Ctrl+滾輪縮放。
- 修正拓撲頁中文模板，避免頁面標題與聯通清單再次出現亂碼。

## v1.0.1.25 - 2026-05-12 08:39 +08:00 - topology-relationship-lines

- 修正系統拓撲互動圖只顯示節點、沒有關聯線的問題。
- 拓撲後端會依 CMDB 的機房、系統名稱與主機資料產生節點座標與線條座標。
- 拓撲頁面文字改回正常中文，並新增機房、系統、主機圖例與聯通清單中文欄位。

## v1.0.1.24 - 2026-05-12 07:35 +08:00 - opening-dashboard-overflow-fix

- 修正開門檢查儀表板在兩張主機卡並排時，9 面向燈號格子超出卡片邊界的問題。
- 將燈號區改為自適應 2 欄/1 欄，並限制卡片、內容與文字不可外溢。

## v1.0.1.23 - 2026-05-11 23:42 +08:00 - deep-check-spec-foundation

- 依 deep_check.md 規格導入深度檢查 Job 架構，新增 Mongo `deep_check_jobs` 與 `deep_check_reports`。
- 新增 `/api/deep-check/*` API、per-host 報告檔、parsed JSON 與 Remedy KB 基礎資料。
- 開門檢查頁新增新版 L3 深度檢查入口，與既有儀表板視圖並存。

## v1.0.1.22 - 2026-05-11 23:31 +08:00 - opening-check-gauge-dashboard

- 將開門檢查的深度檢查結果由橫向表格改為主機儀表板卡片。
- 新增健康分數、整體狀態、9 面向燈號與可展開明細，避免原始輸出直接撐破表格。

## v1.0.1.21 - 2026-05-11 23:22 +08:00 - module-manager-clean-release-notes

- 修正開發後台提交紀錄顯示，過濾舊版亂碼 release note。
- 保留模組管理清楚中文說明，讓功能開關可直接對應實際頁面與按鈕。

## v1.0.1.20 - 2026-05-11 22:57 +08:00 - module-manager-labels

- 修正模組管理的名稱、分類、控制範圍、關閉後影響與建議文字，改成對齊實際畫面功能。
- 清理模組管理來源資料中的英文描述與亂碼，讓管理者能判斷每個開關會影響哪個功能。

## v1.0.1.19 - 2026-05-11 22:15 +08:00 - opening-check-clean-label

- 清理畫面可見的版本說明文字，只保留「開門檢查」命名。
- 避免頁尾與版本提示仍出現舊功能名稱，降低操作判斷混淆。

## v1.0.1.18 - 2026-05-11 22:50 +08:00 - opening-check-label

- 將上方選單與頁面標題由「今日巡檢 / 今日報告」改為「開門檢查」。
- 同步調整按鈕與空資料提示文字，符合值班開門檢查情境。

## v1.0.1.17 - 2026-05-11 22:40 +08:00 - daily-deep-diagnostics

- 今日報告加入每台主機的深度檢查按鈕，對 Linux local/SSH 主機執行 9 面向檢查。
- 深度檢查結果寫入 `diagnostic_results`，頁面顯示最近一週紀錄，避免每次查看都重跑。
- 9 面向包含連線、CPU/記憶體/磁碟、檔案系統、程序、服務、帳號、安全設定、套件、系統日誌。

## v1.0.1.16 - 2026-05-11 22:25 +08:00 - module-manager-impact

- 模組管理加入控制範圍、關閉後影響與建議欄位，讓管理者知道每個開關會關掉什麼。
- 大模組優先排序，合規資安子功能會標示受大模組控制。
- 開發後台模組管理可直接啟用/停用功能開關，操作寫入 audit log。

## v1.0.1.15 - 2026-05-11 22:15 +08:00 - dev-console-release-notes-fix

- 修正提交紀錄頁 500 錯誤：修復摘要欄位改名，避免 Jinja 把 `items` 誤判成 dict 方法。
- 補強部署後頁面驗證，確認 `/superadmin/dev-console` 可正常打開。

## v1.0.1.14 - 2026-05-11 22:05 +08:00 - dev-console-release-notes

- 提交紀錄頁加入版本修復摘要，直接顯示版號、時間、patch id 與修復內容。
- 保留原本 git log 作為技術提交明細，方便追查 hash。

## v1.0.1.13 - 2026-05-11 21:55 +08:00 - dev-console-remove-github

- 開發後台移除 GitHub 推送分頁與內容區。
- 開發後台說明文字同步改為文件、檔案管理、備忘錄、提交紀錄與模組管理。

## v1.0.1.12 - 2026-05-11 21:45 +08:00 - dev-console-file-upload

- 開發後台檔案管理加入上傳檔案與重新整理操作。
- 上傳檔案存放到 `/opt/webitgpt/data/docs`，避免直接覆蓋系統程式目錄。
- 上傳動作寫入 audit log，並限制單檔 20MB。

## v1.0.1.11 - 2026-05-11 15:05 +08:00 - dev-console-unified-tabs

- 開發後台改成單一分頁列，直接放入驗證報告、開發者文件、檔案管理、備忘錄、GitHub 推送、提交紀錄、模組管理、日誌、排程。
- 移除文件備忘錄進入後才看到第二層功能列的操作繞路。
- 單一分頁列仍可拖拉排序，並支援同頁切換開發者文件、檔案管理、備忘錄等內容。

## v1.0.1.10 - 2026-05-11 14:05 +08:00 - dev-console-tabs-order

- 開發後台四個主分頁補上共用導覽，進入文件備忘錄、日誌、排程後可直接切回驗證報告。
- 超級管理員六個功能分頁改成真正同頁 tab，只顯示目前選取內容。
- 後台主分頁與功能分頁支援拖拉排序，順序儲存在瀏覽器 localStorage。

## v1.0.1.9 - 2026-05-11 ???? - dev-console-v317-tabs

- ???????????????????????????????GitHub ?????????????
- ?????? `/opt/webitgpt` ?????/???????????? docs ?????
- ?????? feature flags ????key???????????
- ???????? `:5000` ????????????

## v1.0.1.8 - 2026-05-11 ???? - dev-validation-compact

- ????????????? metric ??????????
- ?????????? key/value ??????????
- ???? JSON ?????????????????

## v1.0.1.7 - 2026-05-11 ???? - dev-console-legacy-workbench

- ???? `/superadmin/validation` ????????????????????????????????
- ???? `/superadmin/dev-console` ?????????????GitHub ?????????????????????
- ???????? compact CSS??????????????????? `:5000`?

## v1.0.1.6 - 2026-05-11 ???? - legacy-5000-ui-density

- ????????? `:5000` ??????????????? header??????active tab ?????????
- ?????????panel????????????????????? padding ?????
- Header ??????????? `?? | ??`?patch id ?????? tooltip ? footer?

## v1.0.1.5 - 2026-05-11 ???? - superadmin-console-complete

- ??????????????????????????????????????????IPAM ??? Patch ?????
- ????????????????????????????API Token?????????????????/DR?Patch/????????
- ??????????????????????/DR?Patch/??????????? UI?
- ??????????????? JSON API????????????/CSV ???

## v1.0.1.4 - 2026-05-11 ???? - inventory-diff-report

- ??????????????????????????????????????
- ?? `/inventory/<kind>/diff-report`?CSV ??? JSON API??????????????
- ??????????????????????????????????

## v1.0.1.3 - 2026-05-11 ???? - inventory-history-cooldown

- ?????????????????????? `inventory_runs` ? `inventory_snapshots`??????????
- ???????????????????????????????????????
- ????????? 360 ???????????????????????????????????????????
- bootstrap ????????????????????????

## v1.0.1.2 - 2026-05-11 部署時間 - ipam-nmap-system-package

- 221 已安裝 nmap 7.92，IPAM 網段掃描可正常執行。
- install.sh 新增 nmap 系統套件檢查與安裝，避免重新部署後環境缺套件。
- 驗證 192.168.1.0/24 掃描模式為 nmap，並產出資產不一致清單。

## v1.0.1.1 - 2026-05-11 部署時間 - legacy-module-parity-wave1

- 今日報告補 Linux / Windows / AIX / AS400 分頁與 9 面向深度診斷矩陣。
- 軟體盤點補套件搜尋、主機篩選、版本變更追蹤、CSV / JSON 匯出與採集入口。
- 效能月報補 nmon 採樣入口、日 / 週 / 月報表與趨勢圖。
- TWGCB 補規則庫、設定管理、CSV / Excel 報表與主機角度修補計畫。
- 系統聯通圖補 CMDB 拓撲圖與 JSON API。
- 系統管理補設定管理、日誌檢視、工作排程、操作紀錄、遠端工具。
- 開發後台補文件、檔案、備忘錄、GitHub 推送計畫與提交紀錄。

## v1.0.0.20 - 2026-05-10 部署時間 - ipam-schedule-settings

- IPAM 每週網段對帳排程改為可設定，預設仍為每週一 07:30。
- IPAM 頁面新增「每週自動對帳排程」區塊，可調整啟用狀態、星期與時間。
- systemd timer 改成每 5 分鐘喚醒檢查一次，由程式依 Mongo 設定判斷是否真正掃描所有網段。

## v1.0.0.19 - 2026-05-10 部署時間 - legacy-parity-spec

- 補上真正的 `/dashboard` 與 `/executive` 頁面，頂部「儀表板 / 主管儀表板」不再共用報告頁。
- 新增 `/superadmin/feature-parity` 功能對照規格書，整理舊版 v3.17 與 GPT v1.0 的已做、部分完成與缺口。
- 先補齊可快速落地的入口與規格追蹤頁，後續缺口可依表逐項補功能。

## v1.0.0.18 - 2026-05-10 部署時間 - weekly-ipam-reconcile-timer

- 新增 `weekly_ipam_reconcile.py`，可批次對所有 IPAM 網段產生 nmap 對帳報告。
- systemd 新增 `webitgpt-ipam-reconcile.timer`，預設每週一 07:30 執行。
- 報告輸出至 MongoDB `network_scan_reports`，執行 log 寫入 `logs/ipam_reconcile.log`。

## v1.0.0.17 - 2026-05-10 部署時間 - ipam-nmap-reconcile

- IPAM 新增網段掃描對帳週報，可用 nmap `-sn` 掃描網段並與資產管理資料比對。
- 報告列出掃描有回應但未納入資產、資產有登錄但掃描未回應、重複 IP、保留 IP 已啟用但未建資產。
- 報告可匯出 CSV，供管理者補申請或修正 CMDB。

## v1.0.0.16 - 2026-05-10 部署時間 - personal-nav-order

- 上方導覽列支援個人拖曳排序，每個 TAB 可直接拖曳調整位置。
- 排序保存在瀏覽器 localStorage，不影響其他使用者或其他電腦。

## v1.0.0.15 - 2026-05-10 部署時間 - saved-view-visible-filters

- 資產管理「常用篩選」儲存表單新增作業系統/平台、環境、機房下拉選單。
- 儲存常用篩選時會直接保存這三個條件，之後點選常用篩選可直接套用。

## v1.0.0.14 - 2026-05-10 部署時間 - ipam-network-detail

- IPAM 網段清單新增「查看 IP 明細」，可進入單一網段檢視每個 IP 的納管狀態。
- IP 明細會顯示已納入資產、僅保留、可用，並帶出主機名稱、資產名稱、作業系統、平台類型與資產狀態。
- 平台欄位支援 Linux、Windows、AIX、AS400、VMware 主機、VMware VM、vCenter、網路設備與端點設備。

## v1.0.0.13 - 2026-05-10 部署時間 - ui-contract-gates

- 新增 UI 合約測試，固定檢查資產管理導覽列 active 狀態與高亮樣式。
- 部署功能驗證新增 `/hosts` 導覽 active 檢查，避免同類問題只能靠人工逐頁抓。

## v1.0.0.12 - 2026-05-10 部署時間 - nav-active-state

- 導覽列目前所在頁面改為明顯高亮，資產管理頁會清楚標示「資產管理」為目前 TAB。
- active TAB 加上淡綠底、邊框與底線，管理類 TAB 保留橘色/紅色識別。

## v1.0.0.11 - 2026-05-10 部署時間 - saved-view-filter-fix

- 修正常用篩選只保存每頁筆數、沒有實際篩選條件的問題。
- 儲存常用篩選時，必須包含搜尋字、狀態、環境、類型、機房或群組任一條件。
- 既有「巡檢系統主機」常用篩選會修成 `q=巡檢系統主機`。

## v1.0.0.10 - 2026-05-10 部署時間 - asset-detail-copy-polish

- 資產列表展開列改為「展開資產明細：主機名」。
- 移除列表說明、展開文字與頁面版本說明中的冗長欄位描述。

## v1.0.0.8 - 2026-05-10 部署時間 - ipam-reserved-range-guard

- IPAM 新增保留 IP / 範圍欄位，支援單一 IP 與 `起始-結束` 範圍。
- 下一個可用 IP 分配會避開 gateway、保留範圍、CMDB 已用 IP 與預留紀錄。
- 預設 lab 網段保留 `192.168.1.1-192.168.1.20`，避免誤配網管或固定用途 IP。

## v1.0.0.7 - 2026-05-10 部署時間 - cmdb-ipam-draft-extensions

- 新增 IPAM 網段管理與網段使用率統計。
- 新增 IP 預留與從資產編輯頁分配下一個可用 IP。
- 新增資產草稿狀態，支援先用資產名稱/系統名稱建檔再補欄位。
- 新增 CMDB 擴充欄位管理，核心 29 欄外的欄位寫入 `extensions`。

## v1.0.0.6 - 2026-05-10 20:45 +08:00 - build-time-from-deploy-host

- 修正版本顯示時間與 Windows/221 實際時間不一致的問題。
- `install.sh` 會用部署主機的 `date` 產生 `WEBITGPT_BUILD_TIME`。
- systemd unit 會保存同一個 `WEBITGPT_BUILD_TIME`，避免重啟後回到寫死時間。

## v1.0.0.5 - 2026-05-10 22:18 +08:00 - asset-edit-index-polish

- 資產編輯頁補齊中文欄位名稱，包含主機類型、機房與連線欄位。
- bootstrap 會把 3 台實機資產正規化回 hostname unique、狀態/機房/平台代碼一致。
- 保留 v1.0.0.4 的多 IP、多網段與資產編輯功能。

## v1.0.0.4 - 2026-05-10 22:08 +08:00 - asset-edit-hostname-ip

- 資產管理補上可用的新增/編輯表單，所有欄位改為中文標籤。
- 主機名稱改為資產唯一索引，資產編號保留為資產流水與相容識別。
- 補多 IP、多網段欄位與查詢，保留主要 IP 供 runner 相容。
- bootstrap 會調整 MongoDB index：hostname unique、asset_seq non-unique。

## v1.0.0.3 - 2026-05-10 21:28 +08:00 - v1-version-policy

- 明確固定版本規則為 `1.X.X.X`，禁止升到 `v2` 或其他主版號。
- 新增啟動檢查，若 `VERSION` 不符合 `1.X.X.X` 會直接阻擋啟動。
- 新增 `VERSION_POLICY.md` 作為後續修補與部署的版號規範。

## v1.0.0.2 - 2026-05-10 21:18 +08:00 - asset-version-tracking

- 將頁首、頁尾、`/health`、`/metrics`、`data/version.json` 補上版本號、修補代號與修補說明。
- 主機管理更名為資產管理系統，加入資產工作台與每台主機 29 欄資產主檔展開明細。
- 明確建立後續追版規則：每次修補都必須升版號、更新時間、修補代號與 changelog。

## v1.0.0.1 - 2026-05-10 - phase1-ui-and-account-inventory

- 建立 Phase 1 基礎功能、帳號盤點工作台、資產清單、自檢、Debug、合規 stub、部署腳本與 221 部署流程。
