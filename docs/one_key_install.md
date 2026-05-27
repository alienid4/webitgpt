# webitgpt 一鍵離線安裝說明

## 目標

把 webitgpt 從目前測試環境移植到新主機，例如 `192.168.1.224`。新主機可能不能上網，因此安裝要分成兩種包：

1. **前置套件包**：OS RPM、MongoDB container image、nmap、nmon、podman。
2. **App 離線包**：webitgpt 程式、Python wheels、INSTALL.sh、systemd、範例設定。

正式移植時不帶入家中測試資料，不帶 Mongo dump，不帶 demo hosts。

## 包裝規則

正式安裝包不得包含：

- `data/`
- `logs/`
- `backup/`
- `venv/`
- `.git/`
- Mongo dump
- demo/test hosts
- 密碼、token、private key

## 1. 先準備前置套件包

如果新主機已經有 Python、nmap、nmon、podman、MongoDB，可以略過本章。

如果新主機不能上網，而且 MongoDB 也沒有，請在一台可上網且同版本的 Rocky/RHEL 9 主機執行：

```bash
cd /path/to/webitgpt
bash scripts/prepare_offline_prereq_bundle.sh
```

會產生：

```text
dist/webitgpt_prereqs_<target-os>_<時間>.tar.gz
```

這包包含：

- Python / venv 相關 RPM
- `curl` / `tar` / `rsync`
- `nmap`
- `nmon`
- `podman`
- MongoDB container image
- `install_prereqs_offline.sh`

在新主機先執行：

```bash
tar -xzf webitgpt_prereqs_*.tar.gz
cd webitgpt_prereqs_*
sudo bash install_prereqs_offline.sh
```

完成後應該會有：

```text
MongoDB: 127.0.0.1:27017
container: webitgpt-mongo
volume: webitgpt_mongo_data
```

## 2. 在 Windows PC 建立 App 離線包

```powershell
cd F:\ClaudeHome\webitgpt
powershell -ExecutionPolicy Bypass -File .\scripts\prepare_offline_bundle.ps1
```

會產生：

```text
F:\ClaudeHome\webitgpt\dist\webitgpt_offline_<version>_<time>.tar.gz
```

App 離線包包含：

- `files/`：webitgpt 程式
- `wheelhouse/`：Python 3.9 Linux wheels
- `INSTALL.sh`：互動式一鍵安裝入口
- `install_offline.sh`：實際安裝腳本
- `install.env.example`：範例設定
- `rpms/README.txt`：提醒 OS RPM 不在 App 包內

## 3. 驗證 App 離線包

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify_offline_bundle.ps1 -Archive .\dist\<bundle>.tar.gz
```

驗證重點：

- 找得到 `INSTALL.sh`
- 找得到 `install_offline.sh`
- 找得到 `wheelhouse/`
- 找得到 `requirements.txt`
- 不含 `data/`、`logs/`、`backup/`、`venv/`、`.git/`

## 4. 安裝 webitgpt App

在新主機執行：

```bash
tar -xzf webitgpt_offline_*.tar.gz
cd webitgpt_offline_*
sudo bash INSTALL.sh
```

`INSTALL.sh` 會詢問：

- 安裝路徑，預設 `/opt/webitgpt`
- Runtime user/group，預設 `sysinfra:itagent`
- MongoDB URI，預設 `mongodb://localhost:27017`
- MongoDB DB name，預設 `webitgpt`
- 是否匯入 CMDB CSV
- `superadmin` 初始密碼

## 5. MongoDB 原則

如果新主機已有 MongoDB：

```text
MongoDB URI: mongodb://localhost:27017
MongoDB DB: webitgpt
```

如果新主機沒有 MongoDB，先執行前置套件包，不要直接跑 App 包。

禁止把家中測試 Mongo dump 當成新主機初始資料。正式環境資料來源只允許：

- CMDB Excel/CSV 匯入
- 少量人工建檔
- 後續掃描建立草稿

## 6. CMDB 匯入

最小 CSV 欄位：

```csv
asset_name,hostname,primary_ip,os,environment,datacenter,owner,admin,notes
```

新主機第一次建置時可以用 `INSTALL.sh` 指定 CSV，也可以先安裝空系統，再從 UI 匯入。

## 7. 安裝後驗證

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

- webapp 可開啟
- MongoDB ready
- superadmin 可登入
- 沒有家中測試資料
- CMDB CSV 匯入結果正確

## 8. 不可做

- 不要把 221 的 MongoDB dump 匯到新正式主機。
- 不要把測試 hosts 當正式資料。
- 不要把密碼寫進 GitHub。
- 不要把 App 包誤認為完整 OS 離線安裝包。
