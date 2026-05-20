# webitgpt 移植到 192.168.1.224 測試 Runbook

## 目的

把目前在 `192.168.1.221` 測試的 webitgpt，以乾淨離線安裝方式移植到 `192.168.1.224`。

限制：

- `192.168.1.224` 視為不能上網。
- 不帶 `192.168.1.221` 的測試資料。
- 不帶 Mongo dump。
- 不帶 `data/`、`logs/`、`backup/`、`venv/`、`.git/`。
- 主機清單之後由 CMDB Excel/CSV 匯入或手動建立。

## 目前已產生的離線包

```text
F:\ClaudeHome\webitgpt\dist\webitgpt_offline_1.0.2.96-offline-onekey-install_20260520220527.tar.gz
```

大小約 24 MB，已包含 Python 3.9 Linux wheels。

已驗證：

```powershell
cd F:\ClaudeHome\webitgpt
powershell -ExecutionPolicy Bypass -File .\scripts\verify_offline_bundle.ps1 -Archive .\dist\webitgpt_offline_1.0.2.96-offline-onekey-install_20260520220527.tar.gz
```

結果應為：

```text
Offline bundle verification OK
```

## 1. 從 Windows PC 傳到 1.224

```powershell
scp "F:\ClaudeHome\webitgpt\dist\webitgpt_offline_1.0.2.96-offline-onekey-install_20260520220527.tar.gz" sysinfra@192.168.1.224:/tmp/
```

如果 `sysinfra` 尚未開 key 或權限不足，請先在 `1.224` 建立可登入帳號或部署 SSH key。

## 2. 在 1.224 解壓縮

```bash
cd /tmp
tar -xzf webitgpt_offline_1.0.2.96-offline-onekey-install_20260520220527.tar.gz
cd webitgpt_offline_1.0.2.96-offline-onekey-install_20260520220527
```

## 3. 安裝前檢查

```bash
hostname
python3 --version
command -v tar
command -v curl
command -v rsync || true
command -v mongod || true
command -v podman || true
```

最低需求：

- `python3`
- `tar`
- `curl`
- MongoDB 可連線，或已有 MongoDB container/service

如果沒有 Python/curl/tar，且主機不能上網，必須先準備 OS RPM 放入離線包的 `rpms/`。

## 4. 執行互動式安裝

```bash
sudo bash INSTALL.sh
```

建議輸入：

```text
Install path: /opt/webitgpt
Runtime Linux user: sysinfra
Runtime Linux group: itagent
MongoDB URI: mongodb://localhost:27017
MongoDB database: webitgpt
Import initial CMDB host CSV now: n
```

接著輸入初始 `superadmin` 密碼。

正式移植測試預設不匯入 CMDB，先確保系統乾淨可用。之後再匯入公司 CMDB Excel/CSV。

## 5. 安裝後驗證

```bash
curl http://localhost:8002/health
curl http://localhost:8002/ready
systemctl status webitgpt --no-pager
journalctl -u webitgpt -n 80 --no-pager
```

瀏覽器開：

```text
http://192.168.1.224:8002
```

確認：

- webapp 可以開。
- superadmin 可以登入。
- 沒有 `192.168.1.221` 測試資料。
- 資產管理是空的或只有匯入資料。
- 可以從 UI 匯入 CMDB CSV 或手動新增主機。

## 6. 若安裝失敗，收集資訊

```bash
systemctl status webitgpt --no-pager
journalctl -u webitgpt -n 120 --no-pager
curl -v http://localhost:8002/health
ls -lah /opt/webitgpt
ls -lah /opt/webitgpt/logs
tail -n 120 /opt/webitgpt/logs/error.log 2>/dev/null || true
tail -n 120 /opt/webitgpt/logs/install_audit.log 2>/dev/null || true
```

把輸出交給公司內部 GPT 或貼回來分析。

## 7. 注意

目前 Windows 端測試結果：

- `192.168.1.224:22` 有通。
- `192.168.1.224:8002` 尚未有 webitgpt 服務。
- `sysinfra` SSH key 尚未可登入，錯誤為 `Permission denied`。

因此在正式安裝前，請先處理 `sysinfra` SSH 登入或改用你可登入的帳號。
