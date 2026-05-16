# 開門檢查摘要 Skill

## 目的

開門檢查是給主管、值班人員與非專業 IT 人員快速判斷狀況的畫面。畫面優先順序是：

圖 > 表 > 人話摘要 > 原始證據

卡片上不可直接顯示 raw command output，例如 `uptime`、`top`、`df`、`ps`、`ss`、`rpm` 原文。raw data 只能放在 `raw_detail`、下載明細、API 或「查看原始證據」區。

## 卡片摘要規則

- 每個開門檢查面向都必須回傳低技術摘要。
- 摘要要回答三件事：
  1. 現在看起來是否正常。
  2. 哪個重點數字或狀態值得看。
  3. 需要怎麼處置，或目前不需處置。
- 文字要讓不懂 IT 的主管也能理解。
- 不用專有名詞堆疊。必要術語要搭配短句說明。
- PASS 也要說明「看過什麼所以 pass」，不能只寫正常。
- WARN/FAIL 要說問題、證據摘要、處置方向。緊急處置要條列。
- 資源類 PASS 小卡要更短，只放指標數字，不放建議文字。例如 `CPU:12%`、`MEMORY:36%`、`SWAP:2%`、`Filesystem:15%`、`IO:2%`。

## 例子

不好的顯示：

```text
secansible
23:04:55 up 7:02, 0 users, load average: 0.09, 0.10, 0.04
```

好的顯示：

```text
連線狀態：主機可連線。
開機狀態：已開機 7 小時 2 分鐘。
使用者：目前無登入使用者。
```

## 目前套用範圍

開門檢查 9 個面向都必須套用：

- 連線狀態
- CPU / 記憶體 / 磁碟
- 檔案系統
- 程序
- 服務
- 帳號
- 安全設定
- 套件
- 系統日誌

## 防呆測試

`tests/test_opening_connectivity_detail.py::test_all_opening_aspects_use_human_summary_not_raw_output`

這個測試用來防止 raw output 再次直接出現在開門檢查卡片摘要。
