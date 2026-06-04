# webitgpt patch 發布自動化

目的：把小修發布流程縮短成一個固定指令，避免每次手動打包、手動檢查 TAR 結構、手動丟 221、手動建立 GitHub Release。

## 適用情境

### 快速小修

適合：

- 文字、標籤、按鈕名稱
- UI 預設收合 / 展開
- 表格欄位顯示
- 小範圍 CSS
- 不寫入資料的 read-only UI

建議流程：

1. 本機 focused test。
2. 建立 3.89 相容 patch TAR。
3. 部署 221。
4. 檢查 `/health` 與關鍵頁面。
5. 上 GitHub Release。

### 完整驗證

適合：

- 匯入 / 匯出 / CMDB 對帳
- 批次改狀態、草稿轉正式、刪除、下線
- inspection runner、SSH、WinRM、AIX、AS400
- NMON、報表、拓撲計算
- install script、offline package、權限、Token、PAM

完整驗證仍要跑 full pytest、敏感資訊掃描與較完整的 221 驗證。

## 指令範例

以下範例會：

- 執行 focused test
- 產生標準 patch TAR
- 複製到 221
- 在 221 安裝並檢查 `/health`、`/hosts`
- 建立或更新 GitHub Release

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\release_patch.ps1 `
  -Version v1.0.4.12 `
  -Slug small-ui-fix `
  -PayloadFiles @(
    "webapp/config.py",
    "webapp/templates/hosts.html",
    "webapp/static/css/cathay.css",
    "CHANGELOG.md",
    "docs/release_notes/v1.0.4.12.md"
  ) `
  -ReleaseNotes "docs/release_notes/v1.0.4.12.md" `
  -TestCommand "pytest -q tests/test_asset_account_ui.py"
```

## 只打包，不上 221 / Release

用於本機先看 TAR 結構：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\release_patch.ps1 `
  -Version v1.0.4.12 `
  -Slug small-ui-fix `
  -PayloadFiles @("webapp/config.py") `
  -SkipDeploy221 `
  -SkipRelease
```

## 套件格式

腳本固定產生下列格式，與 v1.0.3.89 相容：

```text
webitgpt_v1.0.X.Y-patch-<slug>_<yyyymmddHHmm>/
  copy_commands.md
  install.sh
  PACKAGE_MANIFEST.txt
  payload/
  RELEASE_NOTE.md
  ROLLBACK.sh
```

現場安裝仍固定：

```bash
tar -xzf webitgpt_v1.0.X.Y-patch-<slug>_<yyyymmddHHmm>.tar.gz
cd webitgpt_v1.0.X.Y-patch-<slug>_<yyyymmddHHmm>
sudo bash install.sh /opt/webitgpt
```

## 注意事項

- `install.sh` 是 Release TAR 內固定入口，不要改名。
- 公司 Linux 內網可能不能上網，patch 不應在安裝時下載套件。
- 不要把 data、logs、backup、venv、Mongo dump、密碼、Token 或敏感資料放進 payload。
- 需要公司測試時，不要跳過 221 驗證。
- 大修不要只用 focused test。
