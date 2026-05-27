# webitgpt 前置套件離線包

## 為什麼需要這包

`webitgpt_offline_*.tar.gz` 只包含 App 與 Python wheels。  
如果新主機不能上網，而且缺少 OS 套件或 MongoDB，App 包無法單獨完成安裝。

前置套件包用來補齊：

- Python / venv
- `curl` / `tar` / `rsync`
- `nmap`
- `nmon`
- `podman`
- MongoDB container image

## 建立前置套件包

請在可上網、同版本 Rocky/RHEL 9 主機執行：

```bash
cd /path/to/webitgpt
bash scripts/prepare_offline_prereq_bundle.sh
```

輸出：

```text
dist/webitgpt_prereqs_<target-os>_<時間>.tar.gz
```

可調參數：

```bash
MONGO_IMAGE=docker.io/library/mongo:7.0 \
INCLUDE_NMON=1 \
INCLUDE_MONGO_IMAGE=1 \
bash scripts/prepare_offline_prereq_bundle.sh
```

## 在新主機安裝

```bash
tar -xzf webitgpt_prereqs_*.tar.gz
cd webitgpt_prereqs_*
sudo bash install_prereqs_offline.sh
```

安裝後預期：

```text
MongoDB: 127.0.0.1:27017
container: webitgpt-mongo
volume: webitgpt_mongo_data
```

## 驗證

```bash
command -v python3
command -v nmap
command -v nmon
command -v podman
podman ps
python3 - <<'PY'
import socket
s = socket.create_connection(("127.0.0.1", 27017), timeout=2)
s.close()
print("mongo tcp ok")
PY
```

## 注意

- 前置套件包可以包含 MongoDB image，但不包含 Mongo dump。
- 不要把家中測試資料帶到新主機。
- 如果公司已有正式 MongoDB，請不要啟動本機 `webitgpt-mongo`，App 安裝時改填正式 Mongo URI。
