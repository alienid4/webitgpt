# Codex 工作紀律

這份文件把外部 coding-agent 通用原則轉成 webitgpt 專案可執行規則。它不是口號，而是每次修改前後的檢查清單。

## 1. Think Before Coding

動手前先回答：

- 這次真正要解決哪個畫面、API、流程或現場痛點？
- 我是否需要讀現有程式碼或資料結構？
- 有沒有可能誤判使用者意思？
- 有沒有較小、較安全的做法？

若答案不明確，先說出假設；但能從程式碼、畫面或 API 查到的，不要把問題丟回給使用者。

## 2. Simplicity First

實作時遵守：

- 不做使用者沒要求的功能。
- 不建立只用一次的抽象層。
- 不把簡單 UI 修補變成大型框架改造。
- 先讓單一路徑可用，再擴充批次、排程或自動化。

## 3. Surgical Changes

每次修改要能回答：

- 這一行為什麼需要改？
- 它對應使用者哪句需求？
- 會不會影響無關模組？
- 是否動到使用者或其他 AI 的未提交修改？

若看到無關問題，先記錄或回報，不順手改。

## 4. Goal-Driven Execution

每個任務都要轉成成功條件，例如：

- 「搜尋功能」不是只加 input，而是能輸入關鍵字、縮小結果、仍能清除或套用。
- 「深度檢查」不是只顯示 PASS/WARN，而是要有判斷標準、證據、建議處置與驗證方式。
- 「部署完成」不是只重啟服務，而是 `/health` 正確、版本正確、pytest 正確、必要時 functional validation 正確。
- 「長時間操作」不是只有按鈕，而是送出後要有狀態回報、停用按鈕、防止重複提交，讓使用者知道系統正在處理。

## 5. webitgpt 驗證矩陣

| 變更類型 | 必跑驗證 |
| --- | --- |
| Python service / route | `python -m compileall webapp scripts tests`、`python -m pytest -q` |
| UI template / JS / CSS | pytest，加瀏覽器或 HTTP 檢查實際字串/互動 |
| 掃描 / 盤點 / 巡檢 / 修補按鈕 | 確認有送出狀態、busy 文字、停用按鈕與可理解的等待說明 |
| 版本或部署腳本 | `/health`、`scripts/functional_validation.py`、patch tarball |
| 深度檢查判斷 | 單元測試覆蓋 PASS/WARN 條件與證據文字 |
| 資產 / 帳號 / IPAM | 確認不產生假資料、不重複建檔、不誤刪真資料 |

## 6. 回報格式

完成後回報要短但具體：

- 功能：哪個模組
- 項目：哪個子功能或畫面區塊
- 修復：改了什麼
- 驗證：跑了什麼
- 版本：`VERSION / PATCH_ID`
- Patch：tarball 路徑
- Commit：hash

避免只說「好了」。

## 7. 禁止事項

- 不用「可能好了」取代驗證。
- 不把假資料留在正式畫面。
- 不因 unrelated failed service 讓深度檢查誤判 OS 異常。
- 不長期建議關閉防火牆；只能作為緊急短時間排除，正式作法是開必要 port。
- 不改動 legacy 5000、`inspection` DB、Claude 版路徑或無關服務。
