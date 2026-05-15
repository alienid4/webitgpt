# webitgpt Codex / CodeRabbit 工作準則

本 repo 採用 Codex 負責實作、測試、部署與修補，CodeRabbit 負責 PR 風險審查。目標是把每次修改做成可追蹤、可驗證、可回滾的小步驟，避免因猜測、過度設計或無關修改讓巡檢系統變得不可信。

## 核心原則

1. 先釐清再動手
   - 不確定需求時，先明講假設。
   - 若使用者提供畫面截圖、錯誤訊息或現場語境，以現場需求優先，不自行套用通用做法。
   - 高風險功能要先定義判斷條件，例如深度檢查什麼情況才判 `WARN`。

2. 最小可驗證修改
   - 只改本次需求必要的檔案。
   - 不順手重構、格式化或刪除無關程式碼。
   - 不為未要求的彈性加入大抽象。
   - 如果一個小修可以解決，不做大改版。

3. 每行修改都要能追到需求
   - UI 改動要對應到使用者看得到的畫面或操作。
   - 後端邏輯要對應到 API、資料流或實際巡檢結果。
   - 測試要覆蓋使用者明確抱怨過的 bug，避免回歸。

4. 成功條件要可驗證
   - 每次完成後至少跑 `python -m pytest -q`。
   - 影響部署行為時，需跑 `scripts/functional_validation.py`。
   - 影響 UI 時，需用瀏覽器、HTTP 或 API 驗證畫面實際存在。
   - 影響 221 時，需確認 `/health` 回報正確版本與 `patch_id`。

## webitgpt 專案硬規則

- 版本只能使用 `1.X.X.X`，不得升到 `2.0` 或 `2.X`。
- 每次功能或行為變更都要同步更新：
  - `webapp/config.py` 的 `VERSION`
  - `PATCH_ID`
  - `RELEASE_NOTE`
  - `BUILD_TIME`
  - `scripts/make_patch.sh`
  - `scripts/functional_validation.py`
- 回報時要說清楚「哪個功能的哪個項目」被修復，例如「開門檢查的 L3 深度檢查」。
- 不能用假資料取代真實資料，除非使用者明確要求測試資料；測完要能清除。
- UI 統計卡片需可點入細項，除非明確沒有明細來源。
- 使用者未要求登入驗證時，開發期預設免 OTP，權限邏輯仍需保留。
- 221 部署目標為 `/opt/webitgpt`，web port 為 `8002`，Mongo DB 為 `webitgpt`。
- 不要動 legacy 5000 服務、`inspection` DB 或 Claude 版 `webitcl`。

## 深度檢查特別規則

- 深度檢查目標是緊急時快速證明 OS 基礎狀態，不是把所有 service 都追到底。
- 不應因 `setroubleshootd` 這類無關 failed service 判定 AP 或 OS 有問題。
- 優先檢查會直接影響 AP 的項目：
  - AP listener / port
  - CPU / memory / disk
  - network / packet loss / retransmit
  - firewall 排除證據
  - OOM / machine check / kernel tainted
  - 可登入帳號是否被鎖定
- 若提供處置建議，要能讓 L1 或主管看懂：
  - 問題是什麼
  - 影響是什麼
  - 立即排除怎麼做
  - 正式修復怎麼做
  - 怎麼驗證恢復

## CodeRabbit 協作

- PR 描述需包含：
  - 變更內容
  - 驗證方式
  - 已知風險
  - 需要人工確認的地方
- CodeRabbit 的 blocking / high-risk 意見不能直接忽略。
- 若不採納，需回覆：
  - 不採納原因
  - 替代保障
  - 後續追蹤方式

更多細節見 `docs/codex_working_rules.md`。
