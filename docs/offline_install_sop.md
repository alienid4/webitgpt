# webitgpt 新主機離線移植與一鍵安裝 SOP

適用情境：新主機不能上網、不能現場下載套件、不要帶入家中測試資料，只用離線包完成 webitgpt 安裝。

## 1. 三台角色

| 角色 | 範例 | 用途 |
|---|---|---|
| Windows PC | 家用或公司 PC | 整理程式碼、文件、版本、GitHub Release |
| 製包主機 | 192.168.1.221 secansible | 可上網的 Rocky/RHEL 9 相容主機，用來產完整離線包 |
| 目標主機 | 192.168.1.224 secclient2 | 不上網，只解壓縮並執行安裝 |

重點：Windows PC 不負責下載 Rocky/RHEL RPM 依賴樹，也不負責打 MongoDB image。完整離線包要在 221 這類可上網 Linux 主機產生。

## 2. 目前已驗證版本

| 項目 | 值 |
|---|---|
| 版本 | v1.0.2.99 |
| Release | https://github.com/alienid4/webitgpt/releases/tag/v1.0.2.99 |
| 離線包 | webitgpt_full_offline_1.0.2.99-offline-install-noninteractive_20260523002435.tar.gz |
| SHA256 | 8b75a87c4ee52ac8ae7e9f0dea7d76fbbc0c1ff6ef3d72f8c563d55e1521781e |

注意：v1.0.2.98 不建議作為正式離線移植包，因為自動化安裝可能卡在密碼互動輸入。v1.0.2.99 已加入非互動安裝模式。

## 3. 離線包不能包含

正式離線包不得包含：

- `data/`
- `logs/`
- `backup/`
- `venv/`
- `.git/`
- Mongo dump
- 密碼、token、private key
- 家中測試主機資料
- 公司正式 CMDB 原始檔，除非另案核准

新主機安裝後，主機資料應由正式 CMDB Excel/CSV 匯入，或由 IPAM/nmap 掃描建立草稿後人工確認。

## 4. 在 221 產生完整離線包

在 221 執行：

```bash
cd /opt/webitgpt

MONGO_IMAGE=docker.io/library/mongo:7.0 \
INCLUDE_MONGO_IMAGE=1 \
INCLUDE_NMON=1 \
bash scripts/prepare_221_full_offline_bundle.sh
```

完成後檢查：

```bash
ls -lh /opt/webitgpt/dist/webitgpt_full_offline_*.tar.gz
sha256sum /opt/webitgpt/dist/webitgpt_full_offline_*.tar.gz
```

離線包應包含：

- webitgpt 程式
- `INSTALL_ALL.sh`
- Python wheels
- Rocky/RHEL 9 RPM
- MongoDB container image
- nmap / nmon / podman 相關套件
- systemd unit
- 安裝與驗證文件

## 5. 上傳或複製到目標主機

範例：從 221 複製到 224。

```bash
scp /opt/webitgpt/dist/webitgpt_full_offline_1.0.2.99-offline-install-noninteractive_20260523002435.tar.gz root@192.168.1.224:/root/
scp /opt/webitgpt/dist/webitgpt_full_offline_1.0.2.99-offline-install-noninteractive_20260523002435.tar.gz.sha256 root@192.168.1.224:/root/
```

如果 Windows 不能直接 SSH 到 224，可先放到 221，再由 221 傳到 224。

## 6. 在目標主機一鍵安裝

在 224 執行，預設使用 `auto` 模式：

```bash
cd /root
sha256sum -c webitgpt_full_offline_1.0.2.99-offline-install-noninteractive_20260523002435.tar.gz.sha256

tar -xzf webitgpt_full_offline_1.0.2.99-offline-install-noninteractive_20260523002435.tar.gz
cd webitgpt_full_offline_1.0.2.99-offline-install-noninteractive_20260523002435

WEBITGPT_INSTALL_MODE=auto bash INSTALL_ALL.sh
```

## 7. 安裝模式

安裝分成兩個模式：

| 模式 | 指令 | 用途 |
|---|---|---|
| `auto` | `WEBITGPT_INSTALL_MODE=auto bash INSTALL_ALL.sh` | 全自動安裝。等同 `WEBITGPT_NONINTERACTIVE=1`，初始密碼預設 `1qaz@WSX`。 |
| `user` | `WEBITGPT_INSTALL_MODE=user bash INSTALL_ALL.sh` | 互動式安裝。現場輸入路徑、Mongo、CSV 與 superadmin 密碼。 |

`auto` 模式是目前測試與工讀生操作的預設方式。

若正式環境要改密碼，可用：

```bash
WEBITGPT_INSTALL_MODE=auto \
WEBITGPT_SUPERADMIN_PASSWORD='正式密碼' \
bash INSTALL_ALL.sh
```

密碼注意事項：

- `auto` 預設密碼為 `1qaz@WSX`。
- 正式環境安裝後必須立即修改密碼。
- 不要把正式密碼寫進 GitHub、Skill 或截圖。

## 8. 安裝後驗證

在目標主機執行：

```bash
curl http://localhost:8002/health
curl http://localhost:8002/ready
systemctl status webitgpt --no-pager
systemctl status webitgpt-mongo --no-pager
systemctl status webitgpt-edge --no-pager
journalctl -u webitgpt -n 80 --no-pager
```

驗證標準：

- `/health` 回傳 OK，且版本正確。
- `/ready` 回傳 OK。
- `webitgpt` 服務為 active。
- `webitgpt-mongo` 服務為 active。
- `webitgpt-edge` 服務為 active。
- 新環境不應出現家中測試主機資料。

## 9. 可否重複執行

`INSTALL_ALL.sh` 應設計為可重複執行。

重複執行允許：

- 補裝缺少的 RPM。
- 重新載入 MongoDB image。
- 修復 `/opt/webitgpt` 程式檔案。
- 重建 systemd unit。
- 重新啟動服務。

重複執行預設不得：

- 刪除 MongoDB 資料。
- 刪除已匯入的 CMDB。
- 清空正式資料。
- 覆蓋正式密碼。

如果要清空資料或重建 DB，必須另外做明確確認，不能藏在一般安裝流程。

## 10. 新主機資料怎麼進來

正式環境不帶測試資料，資料來源依序建議：

1. CMDB Excel/CSV 匯入。
2. 少量主機人工建立。
3. IPAM/nmap 掃描產生草稿。
4. 管理者確認草稿後正式納管。

匯入最少欄位：

- 資產名稱
- hostname
- IP
- OS
- 環境
- 機房

## 11. 發生問題時要收集什麼

若安裝失敗，先收集以下資訊，不要只拍錯誤最後一行。

```bash
hostnamectl
df -h
free -h
ip addr
systemctl status webitgpt --no-pager
systemctl status webitgpt-mongo --no-pager
systemctl status webitgpt-edge --no-pager
journalctl -u webitgpt -n 120 --no-pager
journalctl -u webitgpt-mongo -n 120 --no-pager
ls -lh /opt/webitgpt
ls -lh /opt/webitgpt/logs
```

給公司內部 GPT 分析時，可保留公司內部資訊。若要給外部或個人 AI，必須先遮蔽 IP、hostname、username、token、password、key。

## 12. 工讀生版最短流程

```bash
cd /root
sha256sum -c webitgpt_full_offline_*.tar.gz.sha256
tar -xzf webitgpt_full_offline_*.tar.gz
cd webitgpt_full_offline_*

WEBITGPT_INSTALL_MODE=auto bash INSTALL_ALL.sh

curl http://localhost:8002/health
curl http://localhost:8002/ready
systemctl status webitgpt --no-pager
```

如果 `sha256sum` 失敗，不要安裝，代表檔案可能不完整或被換過。
