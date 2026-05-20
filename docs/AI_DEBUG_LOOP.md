# itweb-gpt 最小 AI Debug Loop

## 目的

公司 VM 發生問題時，不讓 GPT 直接連 VM。系統只產出去識別化資料與 GPT Enterprise prompt，再由工程師在公司 repo 修 code、補測試、重新部署。

## 流程

1. 在開發後台建立 AI debug loop。
2. 系統產生去識別化 Debug Bundle。
3. 系統產生 GPT Enterprise prompt。
4. 將 prompt 與 bundle 內容提供給 GPT Enterprise 分析。
5. Codex 依分析修 code。
6. 將 bug 補成 pytest 或 `scripts/functional_validation.py` 檢查。
7. 部署到 221 後重新驗證。

## CLI

```bash
cd /opt/webitgpt
./venv/bin/python scripts/ai_debug_loop.py \
  --title "效能月報 raw file 匯入失敗" \
  --detail "操作步驟、預期結果、實際結果"
```

輸出位置：

- `debug/reports/debug_bundle_YYYYMMDD_HHMMSS.zip`
- `debug/ai_loop/ai-debug-loop-YYYYMMDD_HHMMSS.md`
- `debug/ai_loop/ai-debug-loop-YYYYMMDD_HHMMSS.json`

## 安全邊界

- 真實 DEV log 只給 GPT Enterprise。
- 不貼個人 GPT Pro。
- 不提供未遮蔽 IP、hostname、username、password、token、key。
- GPT 只分析，不能直接操作 VM。
