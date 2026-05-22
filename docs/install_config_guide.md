# webitgpt 離線安裝設定指引

## 必要設定

| 變數 | 預設值 | 說明 |
| --- | --- | --- |
| `INSPECTION_HOME` | `/opt/webitgpt` | 安裝目錄 |
| `WEBITGPT_USER` | `sysinfra` | 執行 webapp 的 Linux user |
| `WEBITGPT_GROUP` | `itagent` | 安裝目錄群組 |
| `MONGO_URI` | `mongodb://localhost:27017` | MongoDB 連線 |
| `MONGO_DB` | `webitgpt` | webitgpt 使用的 DB 名稱 |
| `WEBITGPT_SEED_DEMO_HOSTS` | `0` | 正式安裝必須保持 0 |
| `WEBITGPT_CLEANUP_TEST_DATA` | `0` | 正式安裝預設保持 0 |

## 選用設定

| 變數 | 範例 | 說明 |
| --- | --- | --- |
| `WEBITGPT_INITIAL_HOSTS_CSV` | `/tmp/company_hosts.csv` | 初次 CMDB/主機清單匯入 |
| `WEBITGPT_SUPERADMIN_PASSWORD` | 不建議寫入檔案 | 初始 superadmin 密碼，建議由 `INSTALL.sh` 互動輸入 |
| `WEBITGPT_BUILD_TIME` | `2026-05-20 09:00:00 +08:00` | 顯示於頁面與版本資訊 |

## install.env 範例

```bash
INSPECTION_HOME=/opt/webitgpt
WEBITGPT_USER=sysinfra
WEBITGPT_GROUP=itagent

MONGO_URI=mongodb://localhost:27017
MONGO_DB=webitgpt

WEBITGPT_SEED_DEMO_HOSTS=0
WEBITGPT_CLEANUP_TEST_DATA=0

# 若要安裝時匯入 CMDB CSV，取消註解並放上新主機路徑。
# WEBITGPT_INITIAL_HOSTS_CSV=/tmp/company_hosts.csv
```

使用方式：

```bash
cp install.env.example install.env
vi install.env
sudo bash install_onekey.sh ./install.env
```

若需要互動輸入 admin 密碼，建議直接執行：

```bash
sudo bash INSTALL.sh
```

## CMDB CSV 最小欄位

```csv
asset_name,hostname,primary_ip,os,environment,datacenter,owner,admin,notes
```

欄位說明：

- `asset_name`：資產名稱，例如 `受監控主機-Rocky`
- `hostname`：主機名稱，例如 `secclient1`
- `primary_ip`：主要 IP，例如 `192.168.1.222`
- `os`：實際 OS，例如 `Rocky Linux 9.7`
- `environment`：環境，例如 `DEV`、`SIT`、`PROD`
- `datacenter`：機房
- `owner`：保管人
- `admin`：系統管理者
- `notes`：備註

## 新主機確認清單

- OS 版本與套件相容。
- Python 3.9 可用。
- MongoDB 可連線。
- 8002 port 可被使用者瀏覽器連線。
- `sysinfra` / `itagent` 或指定 user/group 可建立。
- 若完全不能上網，RPM 與 Python wheels 已放入離線包。

## 驗證指令

```bash
curl http://localhost:8002/health
curl http://localhost:8002/ready
systemctl status webitgpt --no-pager
journalctl -u webitgpt -n 80 --no-pager
```

驗證重點：

- webapp 是否啟動。
- MongoDB 是否 ready。
- 是否沒有測試主機資料。
- CMDB CSV 是否可匯入。
