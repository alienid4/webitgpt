# webitgpt 新主機離線一鍵安裝

## 目的

這份文件用於把 webitgpt 從開發/測試主機移植到新的公司主機，例如從 `192.168.1.221` 轉到 `192.168.1.224`。目標主機可設定為不能上網，因此所有 Python 套件必須先放進離線包。

正式離線包不帶入目前測試資料。

## 原則

- 不帶 `data/`
- 不帶 `logs/`
- 不帶 `backup/`
- 不帶 `venv/`
- 不帶 `.git/`
- 不帶 Mongo dump
- 不帶 demo/test hosts
- 不帶密碼、token、private key

正式主機的資產資料來源應來自：

- CMDB Excel/CSV 匯入
- 少量手動新增
- IPAM / 網段掃描建立草稿後再補欄位

## 1. 在 Windows PC 產離線包

```powershell
cd F:\ClaudeHome\webitgpt
powershell -ExecutionPolicy Bypass -File .\scripts\prepare_offline_bundle.ps1
```

輸出位置：

```text
F:\ClaudeHome\webitgpt\dist\webitgpt_offline_<version>_<time>.tar.gz
```

離線包內應包含：

- `files/`：webitgpt 程式與部署檔
- `wheelhouse/`：Python 3.9 Linux wheels
- `INSTALL.sh`：互動式一鍵安裝
- `install_offline.sh`：實際安裝腳本
- `install.env.example`：非互動設定範本
- `rpms/README.txt`：OS RPM 準備說明

## 2. 檢查離線包內容

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify_offline_bundle.ps1 -Archive .\dist\<bundle>.tar.gz
```

確認結果必須通過：

- 找得到 `INSTALL.sh`
- 找得到 `install_offline.sh`
- 找得到 `wheelhouse/`
- 找得到 `requirements.txt`
- 沒有 `data/`、`logs/`、`backup/`、`venv/`、`.git/`

## 3. OS RPM 準備

Python wheels 已在 `wheelhouse/`，但 OS 套件如 Python、curl、rsync、nmap 仍可能需要 RPM。

若 `1.224` 不能上網，請在相同 Rocky/RHEL 版本、有 repo 的主機先下載：

```bash
cd /path/to/webitgpt
OUT_DIR=/tmp/webitgpt_rpms bash scripts/prepare_offline_rpms.sh
```

再把 `/tmp/webitgpt_rpms/*.rpm` 放進離線包的 `rpms/` 目錄。

## 4. 將包移到新主機

在 `192.168.1.224`：

```bash
tar -xzf webitgpt_offline_*.tar.gz
cd webitgpt_offline_*
sudo bash INSTALL.sh
```

`INSTALL.sh` 會詢問：

- 安裝路徑，預設 `/opt/webitgpt`
- Runtime user/group，預設 `sysinfra:itagent`
- MongoDB URI
- MongoDB DB name
- 是否匯入 CMDB CSV
- 初始 `superadmin` 密碼

## 5. MongoDB

如果新主機已經有 MongoDB：

```text
MongoDB URI: mongodb://localhost:27017
MongoDB DB: webitgpt
```

安裝程式只初始化 webitgpt 需要的 collections/indexes，不應覆蓋其他 DB。

## 6. CMDB 匯入

初次安裝可以不匯入 CMDB。安裝完成後再從 UI 匯入也可以。

最小 CSV 欄位：

```csv
asset_name,hostname,primary_ip,os,environment,datacenter,owner,admin,notes
```

## 7. 安裝後驗證

```bash
curl http://localhost:8002/health
curl http://localhost:8002/ready
systemctl status webitgpt --no-pager
journalctl -u webitgpt -n 80 --no-pager
```

瀏覽器：

```text
http://192.168.1.224:8002
```

確認：

- webapp 可以開
- superadmin 可以登入
- MongoDB ready
- 沒有 221 測試主機資料
- 可以匯入 CMDB CSV 或手動新增資產

## 8. 不能做的事

- 不要把 221 的 MongoDB dump 當成新主機初始資料。
- 不要把家中測試資料帶到正式主機。
- 不要在正式包內保存 superadmin 密碼。
- 不要要求目標主機上網下載 Python 套件。
