# 在 221 產生完整離線安裝包

## 目的

`192.168.1.224` 如果不能上網，仍然可以一鍵安裝 webitgpt。做法是先在 `192.168.1.221` 產生完整離線包，再把包帶到 224 執行。

## 為什麼用 221 打包

221 是 Rocky/RHEL 9 系列環境，和目標 Linux 主機最接近。它可以正確下載：

- OS RPM 套件
- `nmap`
- `nmon`
- `podman`
- MongoDB container image
- Python wheels
- webitgpt 程式與安裝腳本

Windows PC 不適合直接產 RPM 依賴樹，所以完整包由 221 產生最合理。

## 221 上執行

```bash
cd /opt/webitgpt

sudo dnf install -y dnf-plugins-core podman python3-pip

MONGO_IMAGE=docker.io/library/mongo:7.0 \
INCLUDE_MONGO_IMAGE=1 \
INCLUDE_NMON=1 \
bash scripts/prepare_221_full_offline_bundle.sh
```

完成後會產出：

```text
/opt/webitgpt/dist/webitgpt_full_offline_<version>_<time>.tar.gz
```

## 放到 224 後執行

```bash
tar -xzf webitgpt_full_offline_*.tar.gz
cd webitgpt_full_offline_*
sudo bash INSTALL_ALL.sh
```

`INSTALL_ALL.sh` 會做兩段：

1. 安裝前置套件、載入 MongoDB image、啟動 MongoDB container。
2. 安裝 webitgpt App、建立 Python venv、建立 systemd service、執行 bootstrap。

## 安裝後檢查

```bash
curl http://localhost:8002/health
curl http://localhost:8002/ready
systemctl status webitgpt --no-pager
```

瀏覽器開：

```text
http://192.168.1.224:8002
```

## 正式包不可包含

- `data/`
- `logs/`
- `backup/`
- `venv/`
- `.git/`
- Mongo dump
- 家中測試資料
- 密碼、token、private key

## 注意

這是「新主機乾淨安裝」流程，不搬移 221 的資料庫內容。224 的正式資料應由 CMDB Excel/CSV 匯入，或安裝後由 UI 建立。
