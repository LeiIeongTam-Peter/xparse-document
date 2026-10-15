# Xparse 成本（Cost）修復計畫與進度追蹤

> **狀態**：進行中｜**最後更新**：2026-10-02｜**Owner**：Peter（`@LeiIeongTam-Peter`）
> **兩份文件的分工**：
> - 本文件只管**進度與待辦的狀態**：每張 issue 到哪裡、PR 編號、main／rel／prod 欄位。接手前先讀 §0 和 §7。
> - **系統怎麼運作**寫在 [../cost.md](../cost.md)：架構、契約、gate、決策、待辦事項的技術判斷、#5640 的 merge 條件、接手守則與已知坑。
> - 同一件事只在一處寫細節，另一處放連結。
>
> **前一輪盤查**：2026-09-21 的原始報告封存在 [cost-issue-2026-09-21-audit.md](cost-issue-2026-09-21-audit.md)，9 張 issue（#5135–#5143）的根因分析都在那裡。
> **決策紀錄的正本**：GitHub #5437 的[決策表留言](https://github.com/futurenestit/xparse/issues/5437#issuecomment-5887615649)（D1–D15）。一句話摘要和之後的決定在 [../cost.md §4](../cost.md)。

---

## 0. 接手 agent 先看這裡

**目標一句話**：讓每一筆模型呼叫（含 LLM judge、guardrail）的錢，只記一次、只算一套、算到對的人（key 綁定的 user）頭上，並且 Budget、Dashboard、FinOps 三個畫面對同一段期間顯示同一個數字。

**進度（2026-09-29 晚 ～ 2026-09-30）**
- **已全部 merge 進 main（2026-09-29 晚，main 上 CI／Gateway CI／IAM CI（sqlite＋postgres）全綠）**：#5455（ingress 擋 internal）、#5456（IAM internal 預設拒絕 + node-agent binding）、#5463（#5434 part 1）、#5464（#5442）、#5465（#5435 縮小版）、#5457（#5437 文件 part 1）、#5462（ADR-489，Status 仍 Proposed）、Xparse-Audit#185 + pin bump #5466（#5436）。**都還沒上 rel／prod。**
- #5453（#5430）已於 2026-09-30 merge（`478235056`），#5430 已關。
- 2026-09-30 再 merge：#5472（#5437 part 2，`56b20f28c`）、#5473（#5434 part 2，`7be01da50`）、#5474（#5450，`6ccc5be8e`）；#5434、#5450 已關。**都還沒上 rel／prod。**
- 2026-09-30 再 merge：#5484（#5439，`eacbbead4`，main CI 全綠），#5439 已關。**還沒上 rel／prod；IAM、gateway、Console 要同批部署（#5453、#5484 都改了 IAM contract）。**
- 新開追蹤 issue：#5458–#5461、#5468、#5486–#5489（§5）。
- 2026-09-30 晚：#5140、#5143 改寫對齊 ADR-489；#5142 留下 SPEC-302 清單；開 #5490（routing 計價，S8、Peter）；清理類先不開 issue（§1.6）。
- 2026-10-01（下午起，Peter 指示依 SPEC-302 §10 往下做）：
  - **價格模型定案**（ADR-300 Am.Q／Am.R、SPEC-302 Rev.3–4）：每個 model 只有 input／output／cache read／cache write 四個價格。reasoning、cache_storage_rate、modifiers、line_items 收掉；length_tiers 先停寫，確認 0 筆再全收；#5490 凍結，確認 0 筆後撤回。盤點全文：`price-shape-inventory-2026-10-01.md`（本資料夾）。
  - **已 merge**：docs #5608、#5611、#5625、#5632、#5648；程式 #5624（口徑標籤統一 `query_time_schedule`，#5437 第 8 項，migration 0355）、#5636（reasoning／cache_storage_rate 移除、回溯改價稽核＋`ModelPriceRevision`，migration 0356）、#5647（IAM aggregate API／price-facts／loss-marker 讀取、Audit／Forecast binding、Budget 讀取與 fan-out 同一套判斷）。**都還沒上 rel／prod。**
  - **draft**：#5640 R2（拆列＋version 2 重建）——依 C-302-35 要等 R1 部署到所有環境才 merge；判定條件、指標與 SQL 見 [cost.md §6](../cost.md)。
  - **再 merge**（晚）：#5686（四個價格：modifiers／line_items 收掉、length_tiers／倍率／unit 停寫、不再寫純量段、Console reprice-from 預填、`inventory_pricing_schema`；migration 0358）、#5687（Forecast 改讀 aggregate、Am.J 停寫、series／end-users 退場；Pro tier `XPARSE_FORECAST_IAM_SECRET` 選填）、#5689（Phase 2 基礎：pre-release `cost_surfaces_from_iam`、MoneyAmount、「我的用量」頁預設關）、docs #5690。**都還沒上 rel／prod。**
  - **部署前必做**：清單在 [cost.md §5.1](../cost.md)（`inventory_pricing_schema --json`、forecast secret、IAM 先部署、0354 建索引、有回填列的 tenant 要重建）。
  - **Phase 2 Console 側已 merge**（2026-10-02 凌晨）：#5693 Dashboard 成本分頁＋依用途分項（closes #3046）、#5694 列表與詳情頁（SPEC-302 Rev.10：LLM Proxy 列表依 serving proxy）、#5695 Runtime per-user 改依 key 綁定（#5440）。全部在 `cost_surfaces_from_iam` 後面（dev／rel 讀 IAM、prod 讀 Audit）。Peter 定：#5441 統一金額格式在 prod 也上（Audit 異常值顯示「—」不崩潰）；詳情頁 Requests 格維持 Audit（營運指標）。
  - **還沒做**：Audit 那一側、#5143 對帳 job、Phase 2 發佈到 prod、C-302-60 效能、Phase 1c、Phase 3、length_tiers 全收（撤回 #5490）、C-302-72、剩下的 formatter、已知缺口。每一項的現況、卡在哪、下一步，見 [cost.md §5](../cost.md)。
  - **2026-10-02 查證時順手發現**：①「自助刪模型時硬刪價格段、不留紀錄」其實 #5636 已修；② `recompute_usage_rollup` 會拒絕帶首次建 Budget 回填事實（`backfill:`）的 tenant，部署前要先查；③ TC-302-40 人工回退演練的前半段沒有附在 #5595。細節見 cost.md §5.12、§5.13。
- 2026-10-01：SPEC-302 已 merge（#5568 `eafd38bcc`、#5574 C-302-36a `4e6462bb7`、#5588 Rev.2 `6b6abd902`）；#3949、#4006、#4007 已關，#4045 拿掉 backfill 步驟。Phase 1a 三個程式 PR **已 merge**（2026-10-01，**都還沒上 rel／prod**）：[#5594](https://github.com/futurenestit/xparse/pull/5594) IAM 單一計價模組（#5140，`41a3aac2a`）、[#5595](https://github.com/futurenestit/xparse/pull/5595) IAM R1 expand＋backfill 退場（migration 0354，`edb234abe`）、[#5596](https://github.com/futurenestit/xparse/pull/5596) gateway 記錄端＋producer parity gate（`f2c3fc3df`）。
- 2026-09-30 深夜：SPEC-302 草稿開 PR [#5568](https://github.com/futurenestit/xparse/pull/5568)（docs only，未 merge）。撰寫時 Peter 定了四件事（記在 ADR-489 Rev.2）：路由成本目標改用分級價（#5490）、`backfill_usage_ledger_from_audit_events` 退場、modifier 保留但標明不生效、reasoning 一律用 output 價（寫入時不同就 400）。
- D8 的「告警」目前只會產生 Prometheus 的 `ALERTS`，沒有 Alertmanager，不會通知任何人（#5271）；IAM 的 `/metrics` 也沒人抓（#5489）。

**現在做到哪（2026-09-30）**
- 本輪共 **22 個**追蹤項目（§5，含 09-30 加的 #5468、#5490）：**9 個已修好並進 main**（都還沒上 rel／prod）；3 個進行中——#5429 剩 A／D 等 senior，#5437 剩第 8 項（已記入 #5142 的 SPEC-302 清單），#5142 的 ADR 已 merge、SPEC-302 還沒寫；10 個未開始。
- 9/21 那批修正（#5135–#5139、#5141）在 2026-09-29 時已上 rel（v1.77.0.1），prod 還在 v1.76.1（之後沒再核對）。
- **安全問題 #5429**：程式面的修正（#5455 nginx 擋 internal、#5456 IAM internal 預設拒絕）已進 main，**但還沒部署，部署前這個洞都還開著**。部署時程、要不要先查 Cloudflare／nginx 存取紀錄、有命中就換 key（object storage 金鑰優先），已在 #5429 留言請 senior 決定；WAF 先不加（Peter，2026-09-30）。
- 15 個產品決策已定案（§2）；ADR-489（#5142）已 merge、Status 仍 Proposed，SPEC-302 與 Core-ADR-13 還沒寫。

**下一步（依序）**
1. #5429：等 senior 決定部署時程、查存取紀錄、換 key。**不要自己打環境。**
2. Phase 1a 剩下：口徑標籤改名 `query_time_schedule`（C-302-90，#5437 第 8 項）、reasoning 寫入規則（C-302-9）、回溯改價稽核（C-302-110／111）。部署（要 Peter 授權）：IAM 與 gateway 同批、IAM 先；migration 0354 建索引挑低流量；rel 有 `audit-backfill:` 列的 tenant 部署後跑 `recompute_usage_rollup --tenant`。之後 Phase 1b（R2、aggregate API、Forecast、路由分級價 #5490）。建 Core-ADR-13。
3. 實作依 SPEC-302 §10：1a（R1：計價模組＋golden vectors＝#5140、rollup expand、ledger／事件欄位、口徑標籤、backfill 退場、告警 Audit 備援移除）→ 1b（R2：重建、aggregate API、Forecast、路由分級價＝#5490）→ 1c → 2（Console／Audit 切換，#3046、#5433、#5440、#2574）→ 3。
4. 可平行的小修：#5487、#5489、#5468（P2）；#5486、#5488（P3）；#5458–#5461。
5. 部署：已 merge 的修正上 rel／prod 需要 Peter 授權；部署前先跑 `/deploy-gap`。

**不可違反的規則**（細節見 [cost.md §7](../cost.md)）
- 行為改動先改文件再寫碼（CLAUDE.md §17.1）；計量相關的修正要用**真元件**測（CLAUDE.md §8.1），不要用 fake writer。
- 沒有 Peter 授權，不要對 rel／prod 送任何請求；不要讀任何 secret 的值。
- 有其他 session 在平行修這批 issue（#5431、#5432 就是）。**開工前先查 issue 有沒有 PR**（§7.1 第 3 步）。

**更新這份文件**：每個 PR merge、每次部署後，更新 §5 那一列；方法見 §7.6。

---

## 1. 問題是什麼

### 1.1 一句話

正常的請求不會被重複計費。真正的問題有三個：**錢會漏算、兩本帳對不起來、計價沒有統一**（使用者看得到的錢出自 3 個引擎、程式裡共 9 份算式，見 §1.5）。另外還有一個會外洩憑證的安全漏洞。

### 1.2 修復前（2026-09-29）的資料流

> 這是**修復前**的狀態，留著當作問題紀錄。現況的資料流見 [cost.md §1](../cost.md)。

```
                          ┌─ audit event（EXECUTION_COMPLETED 等，帶凍結價格快照）
                          │     └→ Audit：3 套計價（latest / snapshot SQL / FOCUS）→ Dashboard、FinOps、Runtime
  請求 ─ gateway ─────────┤
  （含 judge／guardrail）  │
                          └─ IAM usage ledger（每次 provider 呼叫一列，帶 producer 與是否計費）
                                └→ IAM：4 份手抄計價 → Budget、admission、/v1/usage、forecast
  Console：自己再算 run-rate、百分比，有 13 種金額格式
```

同一筆用量，gateway **分兩次、各自獨立寫入**（audit 和 ledger），兩邊各自算錢。只要某條路徑只接上其中一邊，兩個畫面就對不起來。

（2026-09-30 更正：Audit 的三套裡，snapshot SQL 算出的金額不會顯示，只影響 `/stats/top-*` 的排名順序；另有 routing 的成本目標用即時單一價估算，是決策用、不是帳；gateway `pricing.py` 的估價函式已是 dead code。完整盤點見 §1.5。）

### 1.3 五個根因

| # | 根因 | 例子 |
|---|---|---|
| 1 | **兩條獨立的用量流**，各自送出不等結果、出錯就放行 | judge 的錢只進 Budget、不進 Dashboard（#3046）；失敗／重試只有一邊記得完整（#5435） |
| 2 | **每個畫面各算各的**：9 份計價實作（使用者看得到的出自 3 個引擎）、2 種計帳基準，加上 routing 的即時價（§1.5） | 同一筆事件，Audit 的三套算式分別算出 $0.862、$0.608、$0.458（#5140） |
| 3 | **契約沒列舉清楚，還互相矛盾** | Jev 要不要寫 ledger、改價要不要回溯、沒價格算 0 還是另計，不同文件寫法相反（#5437） |
| 4 | **CI gate 只檢查模組層級**，測試常用 fake | parity gate 只看「模組裡有沒有記帳呼叫」，所以 failover 漏記帳照樣綠燈（#5431）；per-end-user rollup 的測試自己塞 payload，真實流量下那張表永遠是空的（#5433） |
| 5 | **修正和新功能本身又帶進新的漏洞** | Amendment J 新增了 end-user rollup，gateway 卻沒送 end_user；ADR-488 讓 judge 呼叫變多，少算的量也跟著放大 |

### 1.4 安全問題（#5429，最高優先）

IAM 的 `/iam/internal/*` 端點宣告 `auth=None`，前提是「只有同一個 Docker 網路打得到」。但正式環境的 nginx 把 `/apis/iam/` 整段轉給 IAM，沒有擋掉 internal（Audit 有擋）。受影響的端點：

- 用量／預算端點：外部可以寫入（包括負數）或讀取任何 tenant 的用量。
- `resolve-provider-credential`：回傳**解密後的 provider API key**，包括平台自己的 system 範圍 key。
- `resolve-object-store-credential`：回傳 object storage 的 access key 和 secret key。

可能的暴露期間：provider 憑證端點從 2026-05-16 起、object store 端點從 2026-06-22 起，目前的 `/apis/iam/` 轉發設定從 2026-06-15 起。**以上都只根據程式碼與設定判斷，沒有對任何環境實測。**

**2026-09-29 更正（本機跑真 IAM 路由確認，未對環境實測）**：`resolve-provider-credential` 因參數宣告錯誤，任何請求都在 handler 前回 422——**provider key 沒有從這條外洩**（node-agent 取 provider token 的功能也因此從沒生效過）；`resolve-object-store-credential` **真的可達**，object storage 金鑰在暴露期間可被取走——查 log 與換 key 以它為優先。回傳解密 provider key 的 gateway-validate 等 4 條原本就有 gateway binding。budget usage 寫入端點任何人可寫，查 log 時一併看。

### 1.5 計價有沒有統一、有沒有重複讀寫（2026-09-30 對 main `eacbbead4`、Audit pin `1c9758e` 查證）

> Peter 做成本計算優化只看這兩件事。以下每一列都讀過程式碼；路徑前綴：`gw/`＝`apps/gateway/bustream/`、`iam/`＝`apps/iam/xparse_iam/xparse_iam/`、`au/`＝`3rd/xparse_audit/src/audit/`。

**一、計價沒有統一。** 使用者看得到的錢出自 3 個引擎；程式裡共 9 份「token × 單價」的實作。

| # | 實作 | 價格基準 | 使用者在哪裡看到 | 狀態 |
|---|---|---|---|---|
| 1–4 | IAM `iam/authorization/budget_usage_query.py`：單一 scope `:385`／`:435`、批次 `:652`／`:740`、series `:975`、end-user series `:1140`（共用 resolver `:133`） | 查詢當下讀 `ModelPriceVersion`；flat 路徑整天用 00:00 UTC 的價，tiered 路徑用 `occurred_at` | Budget 頁、admission、`/v1/usage`、interim 額度、預算告警、forecast | 使用中；end-user 那份永遠是空的（#5433） |
| 5 | Audit `au/api/latest_pricing.py:504` | 同一張價目表經 HTTP 取、快取 600 秒，用事件當下的價 | Dashboard 成本卡、Runtime、`/stats/*` 的金額、Dashboard Budget 卡的已花費、告警的 Audit 備援 | 使用中 |
| 6 | Audit `au/export/focus.py:302` | 事件上凍結的價（gateway `audit_helpers.py:375` 寫入，固定 tier 0） | FinOps／FOCUS 分頁與 CSV | 使用中 |
| 7 | Audit SQL `au/storage/postgres_event_store.py:315`、`au/access/query.py:252`、legacy `au/storage/rollup_store.py:122-164` | 凍結價 × 全部 input（不拆 cache、沒有 tier） | 金額在讀取時被 #5 蓋掉；但 `/stats/top-*` 的**排名順序**仍用它 | 算了卻不顯示 |
| 8 | routing 成本目標 `apps/gateway/xparse_routing/application/strategies/_objective_pick.py:246-280` | validate 回傳的即時單一價，沒有 tier；未定價當 0（D28） | 路由選模型、audit 的 `effective_cost` | 使用中（決策用，不是帳） |
| 9 | gateway `gw/production/pricing.py:270`（`estimate_cost_*`） | — | 無 | dead code |

一定會算出不同金額的情況：
- **長度分級模型的長 prompt**：IAM ＝ Audit（有套分級）≠ FOCUS（固定 tier 0）≠ routing（基本價）。
- **未定價模型**：IAM 當 $0，而且**完全不回傳未定價筆數**（違反 SPEC-215 C-215-30；ADR-489 INV-489-4 要求改）；Audit 當 $0 但有計數；FOCUS 顯示空白並加旗標；routing 當免費，反而偏好選它。
- **回溯改價**：Budget 立刻變，Dashboard 約 10 分鐘內（600 秒快取＋重建），FOCUS 永遠不變。
- **classifier／tier judge 的用量**：只有 IAM 計價，Budget 會比 Dashboard 多（#3046）。
- **價格段邊界不在 00:00 UTC**（只有 API 寫得出來，Console 一律寫午夜）：IAM flat 路徑整天用同一段價；當天若在 flat 與分級價之間切換，IAM 會重複計算（flat→分級）或漏算（分級→flat）（#5140 已記錄）。
- **有 `cache_storage_rate` 的模型的 cache-write token**：IAM 用 input 價（`budget_usage_query.py:203`），Audit 算 $0（`latest_pricing.py:628`）。
- **modifier**：沒有任何路徑會帶 `active_modifiers`，寫了 modifier 價格也不會生效。
- **捨入**：admission half-even（`quota_counter.py:964`）、preview half-up（`budget_preview.py:84`）、告警用 float（`budget_alerts.py:337`）。

**二、有重複讀寫。** 同一個請求的 token 由 gateway 分兩次、各自獨立寫出（Audit 與 IAM ledger），之後又被彙總進多個儲存：

| 儲存 | 內容 | 寫入 | 讀取 → 畫面 | 狀態 |
|---|---|---|---|---|
| Evidence JSONL（＋S3／Blob） | token＋凍結價，每請求 | `gw/audit/xparse_bridge.py:711-733`（佇列滿就丟） | Audit projector | 使用中（Audit 的原始資料） |
| `audit_events`（Audit PG） | 同上，每事件 | Audit projector | FOCUS、`/stats/summary` 的 token、IAM backfill 指令 | 使用中 |
| `usage_cost_rollup`（Audit，legacy） | token＋凍結價 × 全部 input，每小時 | `au/storage/rollup_store.py:91`，每 60 秒 | `/stats/top-*`、`/stats/keys-usage` 的 token 排名；金額讀取時被蓋掉 | token 使用中，金額沒用 |
| `latest_usage_cost_rollup`（Audit） | token＋依事件時間計價的金額，5m／1h／1d | 每 600 秒**整張重建**（`au/usage_cost/rollup_projector.py:137-231`；超過 100 萬事件就報錯） | Dashboard 成本／token 卡、Budget 卡的已花費、Runtime、所有 `/stats/*` 的金額、IAM 告警備援 | 使用中 |
| `usage_ledger_entry`（IAM） | 4 類 token，不存金額；token 列與 cost 列帶同樣的 token | `gw/production/quota_counter.py:687-801` → `iam/api/ninja_api/_internal.py:926-1057`；手動 backfill 指令 | tiered 計價、series、重算 | 使用中 |
| `budget_usage_daily_rollup`（IAM） | token，每天 × 5 scope × 軸 × 模型（只有可計費） | 同一個 transaction 內 fan-out（`_internal.py:734-874`）；重算指令 | Budget 頁、admission、`/v1/usage`、interim 額度、告警、forecast | 使用中 |
| `budget_usage_end_user_daily_rollup`（IAM，Am.J） | token，每天 × end_user | 只有 ledger 列帶 `end_user` 才寫；gateway 從不送，只有 Audit backfill 會寫 | forecast | 真實流量永遠是空的（#5433；D13 決定移除） |
| `usage_loss_marker`（IAM） | 寫入失敗三次後的最後紀錄 | `quota_counter.py:803-833` | 沒有人讀 | 只寫不讀 |
| `interim_api_key_quota.token_used／cost_used_usd` | 舊欄位 | 沒有人寫 | 只有 CRUD audit 快照（永遠 0） | dead |
| Redis `app:{uuid}:token_count` | 每個 app 的累計 token | `quota_counter.py:168-195`（Pro／Enterprise 有設 Redis）；`reconcile_token_quota` 從 Audit 覆寫 | 沒有人讀 | 只寫不讀 |
| Redis `budget:*`／`cost_budget:*` | 舊的預算計數 | 沒有人寫 | 舊的直連模式，實際設定下走不到 | dead |
| forecast SQLite `forecast_result` | IAM 每日 series 的副本＋預測 | forecast daemon | Budget 頁的預測、Dashboard Budget 卡 | 使用中（incubating） |
| routing.db `routing_decision_log` | 每請求 prompt／completion token | routing resolver | 啟動時的 EWMA；成本選擇不用它 | 路由專用 |

兩本帳對不起來的原因：
1. Audit 會掉事件（emitter 關閉或佇列滿）；ledger 重試 3 次後寫 loss marker，但沒人讀。
2. 範圍不同：ledger 還記 classifier、tier judge、失敗重試與 evaluator；Audit 的 token 彙總只算 execution 事件。
3. #5453 之後兩邊沒有共同的請求鍵：ledger 用 gateway 產生的 `ledger_request_id`、沒有 `request_id` 欄；Audit 事件沒有 `ledger_request_id`；`end_user` 只在 Audit。
4. 新鮮度：ledger 即時，Audit 每 60 秒／600 秒才更新。
5. Audit 內部三種 token 數用的事件集合不同（全部／只算 completed／Dashboard 預設只算成功），FOCUS 又算所有 token > 0 的事件。

同一個畫面混用兩個來源：
- Dashboard Budget 卡：上限讀 IAM、已花費讀 Audit（只算成功）、預測線讀 forecast（IAM）（#5438）。
- API Keys 分頁：interim 額度欄讀 IAM，旁邊的用量讀 Audit `/stats/keys-usage`。
- Group 詳情：「Cost」讀 Audit、「Budget Used」讀 IAM。
- 預算告警：讀 ledger，讀失敗時改用 Audit `/stats/summary` 的金額（ADR-489 要拿掉）。

還會從 Audit 寫回的路徑（都是手動指令）：
- `backfill_usage_ledger_from_audit_events`：把 Audit 的用量寫進 ledger 與 rollup；只寫 token 軸，缺 producer 就當可計費；防重複只靠 `--end` 截止時間。
- `reconcile_token_quota`：從 Audit 覆寫 Redis 的 `app:*:token_count`，而那個 key 沒人讀。

**可以直接清掉的**（沒人讀或走不到）：gateway `pricing.py` 的估價函式、Audit legacy rollup 的金額欄、Redis `app:*:token_count` 與 `reconcile_token_quota`、Redis 預算直連模式、`interim_api_key_quota` 兩個舊欄位（依 CLAUDE.md §8.3 分兩次 release）、end-user rollup 表（D13）。`usage_loss_marker` 則相反：應該有人讀（對帳時列出遺失的量），不是刪掉。

**程式裡過時的註解**：`gw/gateway/usage_ledger_hook.py:223-225`（說 ledger 的 cost 用 audit 快照）、`budget_usage_query.py:1246-1249`（說 backfill 沒有 end_user）、`deployments/compose/tiers/docker-compose.pro.yml:51-57`（說 Redis 在計預算）、`iam/api/ninja_api/_budgets.py:214-222` 的 docstring 與 OpenAPI 還在描述 #5473 已刪的 backfill。

**由哪張 issue 收**：見 §1.6。

### 1.6 現有 issue 有沒有涵蓋「統一計價」與「重複讀寫」（2026-09-30）

**結論（2026-09-30 晚更新）：23 項中 17 項已有 issue 涵蓋，6 項沒有。** 同日已完成：
- 改寫 #5140、#5143 的 Desired／Acceptance，對齊 ADR-489；
- 在 #5142 留下 SPEC-302 必須涵蓋的清單（[留言](https://github.com/futurenestit/xparse/issues/5142#issuecomment-5905335221)）；
- 開 #5490（routing 計價）。

沒有 issue 的 6 項是清理類（#9、#18、#19、#20、#23），Peter 決定先不開 issue；#22 要先有 ADR。

✅ 已涵蓋｜⚠️ 只涵蓋一半或 issue 內容過時｜❌ 沒有 issue

| # | 項目 | 類別 | 由誰涵蓋 | 狀況 |
|---|---|---|---|---|
| 1 | IAM 的 4 份手抄收斂成一份，用 golden vector 釘住 | 計價 | #5140（2026-09-30 改寫）、ADR-489 §2.1-2、INV-489-2 | ✅ |
| 2 | Audit 最新價、FOCUS 凍結價停止計價，畫面改讀 IAM | 計價＋重複讀 | ADR-489 §2.1-1／2／8／9，Phase 2–3 | ✅ |
| 3 | Audit SQL 與 legacy rollup 的金額 | 計價＋重複寫 | ADR-489 Phase 3；`/stats/top-*` 的排名來源記在 #5142 的 SPEC-302 清單 | ✅ |
| 4 | 未定價不再當 $0、回傳未定價筆數 | 計價 | ADR-489 §2.1-6、INV-489-4 | ✅ |
| 5 | routing 成本目標（沒有 tier、未定價當免費） | 計價 | #5490（決定要不要套用 IAM 的分級價；D28、D29 不重開） | ✅ |
| 6 | IAM flat 路徑整天用 00:00 的價（日界線重複或漏算） | 計價 | #5140 Desired 4、驗收 | ✅ |
| 7 | 捨入規則不一（admission half-even、preview half-up、告警 float） | 計價 | #5140 Desired 4、驗收 | ✅ |
| 8 | modifier 從來不生效；`cache_storage_rate` 模型的 cache-write、reasoning 計法 | 計價 | #5140 Desired 4 | ✅ |
| 9 | gateway `pricing.py` 的估價函式（dead code） | 清理 | — | ❌ Peter 決定先不開清理 issue（2026-09-30） |
| 10 | gateway 對同一請求寫兩份（Audit＋ledger） | 重複寫 | ADR-489：刻意保留，Audit 只當證據，由 #5143 對帳 | ✅ 設計上保留 |
| 11 | 兩本帳對帳（需要共同請求鍵） | 重複寫 | #5143（2026-09-30 改寫：比 token、先決定共同鍵） | ✅ |
| 12 | `usage_loss_marker` 沒人讀 | 重複寫 | #5143 Desired 2 | ✅ |
| 13 | Audit 三張 rollup 的成本部分 | 重複讀寫 | ADR-489 Phase 3 | ✅ |
| 14 | end-user rollup 表 | 重複寫 | ADR-489 §2.1-5（D13）、#5433 | ✅ |
| 15 | Dashboard Budget 卡混用兩個來源 | 重複讀 | ADR-489 §2.1-1、#5438（Silvia） | ✅ |
| 16 | 預算告警的 Audit 備援 | 重複讀 | ADR-489 §2.1-7 | ✅ |
| 17 | API Keys 分頁的用量、Group 詳情的 Cost、Applications／LLM Proxy 列表的 cost | 重複讀 | #5142 的 SPEC-302 清單 | ✅ |
| 18 | Redis `app:*:token_count` 與 `reconcile_token_quota` | 重複寫 | — | ❌ 先不開 issue |
| 19 | Redis 預算直連模式（走不到） | 清理 | — | ❌ 先不開 issue |
| 20 | `interim_api_key_quota.token_used／cost_used_usd` 舊欄位 | 清理 | — | ❌ 先不開 issue（刪除要依 CLAUDE.md §8.3 分兩次 release） |
| 21 | `backfill_usage_ledger_from_audit_events` 從 Audit 寫回 ledger | 重複寫 | #5142 的 SPEC-302 清單（退場或限制） | ✅ |
| 22 | ledger 每筆可計費事實寫 token、cost 兩列（token 相同），rollup 最多 10 次更新 | 重複寫（同一處） | — | ❌ 優化候選，要先有 ADR 決定 |
| 23 | 4 處過時的程式註解（§1.5） | 清理 | — | ❌ 先不開 issue |

處理結果（2026-09-30 晚，Peter 同意）：
1. #5140 改寫完成：標題改成「9 份實作」，並補上日界線、捨入、未定價、modifier、cache／reasoning 的驗收。
2. #5143 改寫完成：改成比 token，先決定共同請求鍵，並納入 loss marker；口徑表放在 Core-PRD-13。
3. SPEC-302 必須涵蓋的清單已留在 #5142。
4. 開 #5490（routing 計價）；清理類 issue 先不開。

---

## 2. 已定案的決策

D1–D15（2026-09-29）、之後 Peter 的決定（四個價格、各價格形狀的去留、R2／Phase 2 怎麼扣住、moderation 計數、「我的用量」預設關等），以及不採用的方向，都整理在 [cost.md §4](../cost.md)（每項一句話＋出處）。正本仍是 [#5437 的決策表留言](https://github.com/futurenestit/xparse/issues/5437#issuecomment-5887615649)。

**還沒定的事**見 §6。

---

## 3. 修完 issue 就好了嗎？不夠

**理由**
1. **修好不等於客戶用得到**：9/21 那批修正已經關閉一週，prod 還沒有；現在 prod 的 Budget 仍然偏低。完成要算到 prod 部署並驗證。
2. **沒改文件就動手修，會修出另一套互相矛盾的版本**：#5437 的文件修正和 #5142 的 ADR 決定了其他 issue 的「正確答案」。
3. **issue 清空了，問題還會再長出來**：9/21 修了 6 張，8 天後又找到 14 張，其中好幾張是修正或新功能本身帶進來的。根因在結構（§1.3 的第 1、2、4 點），要靠 #5142（一本帳、一套算式）、#5143（自動對帳告警）和更嚴格的 gate 才能停止。
4. **安全問題要處理到確認沒被利用**：光修程式不夠，要查存取紀錄，有命中就換 key。
5. **清單不是全部**：這次沒有驗證的有三項：`RetryableWorker` 在第一個 token 之後的重試（推論沒記帳）、admission 每個請求都掃一次原始 ledger 的效能、跟 provider 真實帳單對帳（#3261）。

**整體完成的定義（Definition of Done）**
- [ ] #5429：從外網打 `/apis/iam/internal/*`，在 rel 和 prod 都回 404；兩個憑證端點在 IAM 端也要求呼叫者驗證；存取紀錄已檢查，有命中的 key 已經換掉。
- [ ] §5 的所有追蹤項目都已部署到 prod 並驗證，不是只 merge。
- [ ] #5437 的每一組矛盾只剩一個有效說法，另一個標上 `Superseded by`；#5142 的 ADR 已 merge（含 ADR-093 表與 Core 對比表）。
- [ ] 同一個 scope、同一段期間，Budget、Dashboard、FOCUS 的金額相等（只差宣告過的口徑）。
- [ ] 計價只剩 IAM 一套實作，由 golden vector 釘住；沒有任何畫面用 Audit 或 gateway 的價格快照算金額（#5140、ADR-489 INV-489-1／2）。
- [ ] §1.6 列為「沒有 issue」的重複寫入與 dead code，都已刪除或明確決定保留。
- [ ] 每個 user 的花費可以從 key 綁定查出來，包含 judge 費用，並能按用途拆開（生成／guardrail 判官／路由判官／失敗重試）。
- [ ] #5143 的對帳告警已上線：故意關掉一條記帳路徑時會變紅，而且在 prod 連續 7 天沒有誤報。
- [ ] 新增推論面或 evaluator 時，只要寫一次 ledger，所有成本畫面就會出現（由 gate 或測試保證）。

---

## 4. 修復計畫（依序進行；同一階段內可平行）

### Phase 0 — 止血
| 項目 | 做法 | 需要授權 |
|---|---|---|
| #5429 A | 在 Cloudflare 加 WAF 規則，擋 `/apis/iam/internal/*`。不用部署，立刻生效。**2026-09-30：WAF 先不加（Peter）** | **是**（要有 Cloudflare 權限的人） |
| #5429 B | 5 份 ingress 設定都加 `location /apis/iam/internal/ { return 404; }`（比照 Audit）。repo 追蹤的服務都走 `http://xparse-iam:8010`，不受影響；但要先確認沒有遠端 node 手動把 `IAM_API_URL` 設成公開網址。**✅ #5455 已 merge，未部署** | 部署到 rel／prod：**是** |
| #5429 C | IAM 端 `/iam/internal/` 改成預設拒絕：每條路由明列允許的呼叫方。gateway 呼叫的沿用 `gateway_internal_auth.py` 的 binding；兩個憑證端點的呼叫方是 node-agent，用 node-agent 專用 binding（D12）；forecast、scheduler 各自一把。**✅ #5456 已 merge，未部署**（scheduler／forecast 8 條暫列網路信任，#5461） | 否（一般 PR） |
| #5429 D | 查 Cloudflare 和 nginx 的存取紀錄；憑證端點有外部命中就換 key。如果紀錄涵蓋不到 2026-05-16 起的整段期間，建議預防性換掉平台自己的 system 範圍 key。**已在 #5429 留言請 senior 決定** | **是** |
| #5430 | ✅ 已修（#5453）：冪等鍵改用 gateway 自己產生的 id；IAM 收到重複的 key 時比對內容，不一致回 409 | 否 |
| #5431 | ✅ 已修（#5449） | — |

**退出條件**：從外網打 internal 回 404；同一個 `X-Request-ID` 送兩次，兩筆都有記帳。

### Phase 1 — 把決策寫進文件（CLAUDE.md §17.1 設計閉環）
- #5437：依 D1–D11 修改以下文件：
  - Jev 的「不寫 ledger」改成「記錄但不扣款」：ADR-472 INV-472-7、ADR-476 INV-476-9、SPEC-223 `:571-574`、SPEC-294 `:206`、`:279`。
  - Core-PRD-13 原則 1 與 ADR-265 **INV-265-3**（原本誤寫成 INV-265-2；INV-265-2 是「無價目 → None」，D3 要保留）改成「回溯改價，歷史跟著變」（D2）；INV-265-5 的價格快照降為證據用途；ADR-383 INV-383-2 要一併處理 FOCUS；PRD-213 A7／INV-213-6 同步。
  - SPEC-215 C-215-114 的「沒價格算 0」改成跟 C-215-30 一致（D3）。
  - ADR-423 INV-418-17 的「一個 request 只有一筆」、SPEC-215 C-215-110 的封閉 producer 清單，改成現況（9 個 producer）。
  - ADR-423 `:505-507` 和 PRD-237 `:684` 的「audit 與 ledger 的 token 逐位相同」，改成只比對 `generation`。
  - ADR-488 和 SPEC-223 `:925` 對「多判官記幾列」寫法不同，統一成「每個判官模型一列」。
- #5142：寫 ADR（Rev.2 的方向加上 D1、D2、D4、D5、D6、D11）：
  - ledger 是唯一的計量紀錄，IAM 是唯一計價的地方（查詢時計價）。
  - Dashboard 和 FOCUS 改讀 IAM 的彙總。
  - 每個 user 的花費用 key 綁定反查；rollup 加上 producer 維度。
  - 決定 Amendment J 那張空的 end-user rollup 表要不要移除。
  - Audit 只當證據。
- Core 整合層：Core-PRD-13 補上 producer 與計費規則、口徑總表，並附 §17.4 的 Core 對比表。

**退出條件**：#5437 的每組矛盾都已處理，#5142 的 ADR 已 merge。

**現況（2026-09-30）**：#5437 文件已修兩輪（#5457、#5472），9 組矛盾剩第 8 組（三個 cost basis 名稱）；ADR-489 已 merge（#5462，Proposed）；Core-PRD-13 已列出 9 個 producer 與計費規則；Core-ADR-13 還沒建。

### Phase 2 — 計量正確（gateway／IAM；大多可以跟 Phase 1 平行）
| Issue | 重點 |
|---|---|
| #5432 | ✅ 已修（#5451）：completion 分開計價、output 階段的模型 uuid、失敗路徑也記帳、外部判官不再撞 key |
| #5450 | ✅ 已修（#5474）：不依賴模型的預算／額度檢查移到路由 judge 和 input guardrail 之前（D9） |
| #5434 | ✅ 已修（#5463、#5473）：`recompute_rollup_for_tenant` 刪整個 tenant 的 rollup，並走計費判斷；首次建 Budget 時的 audit backfill 已刪 |
| #5435 | ✅ 已修（#5465，縮小版）：失敗／重試事件補上 `model_uuid` 和 ledger 欄位；價格快照依 D1／D2 不做 |
| #5436 | ✅ 已修（Xparse-Audit#185 + #5466）：只掃啟用規則的近期事件；被截斷時的使用者告警另案 |
| #5439 | ✅ 已修（#5484）：讀取失敗回 degraded，不回 0；per-tenant 旗標 `budget_usage_unavailable_blocks`（D8）。後續 #5486–#5489 |
| #5442 | ✅ 已修（#5464）：Limit window 的結束日改成不含當天 |
| #5433 | 每個 user 的花費用 `api_key` rollup 加 key 綁定反查（D6）。要不要把 end_user 補寫進 ledger、要不要移除 Amendment J 的表，跟 #5142 的 ADR 一起決定 |

**退出條件**：每張 issue 的驗收測試都對真 IAM 跑過，而且全綠。

### Phase 3 — 一本帳、一套算式（#5142 的實作）
- IAM 提供成本彙總 API：可以依 tenant、group、application、api_key、user（key 綁定）、model、producer、日期分組；口徑固定為查詢時計價（D2）。
- Dashboard 成本卡和 FinOps／FOCUS 改讀這個 API。Audit 的三套計價退役，或只留給對帳用。gateway 的凍結價格快照不再是任何畫面的計價來源。
- #5140：只剩 IAM 一套，用 golden vector 釘住（`pricing-formula.v1.json`，加上各 owner `contracts/` 裡的 sha256）。
- #3046 等 Dashboard 顯示 judge 費用後關閉。

**退出條件**：同一個 scope、同一段期間，Budget、Dashboard、FOCUS 的金額相等。

### Phase 4 — 前端
| Issue | 重點 |
|---|---|
| #5438 | Budget 卡改讀跟 Budget 頁同一個 IAM 數字；tenant 總額用整個 tenant（D5）；上限用 allocated + granted；警戒線讀 plan 設定；拿掉瀏覽器自己算的預測 |
| #5441 | 只留一個 `formatMoney`，做一個顯示「未定價」的元件（D3）；「By Provider」改名，或真的按 provider 彙總；排名以外的列逐列查詢，不要顯示 $0.00 |
| #5440 | Runtime per-user 的 token 和 cost 用同一種身分（D6 的 key 綁定） |
| #2574 | 使用者可以看自己名下 key 的花費（D7） |
| 新增 | 成本按用途分項（生成／guardrail 判官／路由判官／失敗重試）（D1、D4）；Jev 的 UI 文字（D10）；「未歸屬」一列（D6、D11）；ADR-488 設定畫面顯示「每個請求要跑幾次判官」 |

### Phase 5 — 防回歸
- #5143：對帳告警，比對 ledger 的 `generation` 列和 Audit 的 completion 事件，輔助呼叫另外報；口徑總表放進 Core-PRD-13。
- gate 從「模組裡有記帳呼叫」加強成「每個 provider 呼叫都會寫到 ledger」，用行為測試或更細的 AST 檢查。
- （之後再做）跟 provider 真實帳單對帳（#3261），可以參考 LiteLLM 的 `/spend/capture_rate`。

### Phase 6 — 上線與驗收
- 部署前先跑 `/deploy-gap` 看 migration 風險；部署順序照各 PR 的說明，通常是 gateway → IAM → Console。#5453、#5484 改了 IAM contract，IAM、gateway、Console 要同一批上。
- D8 的告警要等 #5271（Alertmanager）才會通知人；IAM 的計數器要等 #5489 才看得到。
- rel 驗證：
  - chat（串流／非串流）、`/v1/responses`、`/v1/embeddings`、agent mode 各打一次，確認 ledger 的 producer 和金額正確。
  - failover、judge、guardrail 各觸發一次。
  - 確認 Budget 和 Dashboard 的金額相等。
- prod 部署後重做同一組驗證，並觀察對帳告警 7 天。

---

## 5. 進度追蹤表

**分工（Peter，2026-09-30）**：Peter 只做成本計算的優化——**計價有沒有統一**、**同一筆用量／金額有沒有在不同地方重複讀寫**（#5142、#5140、#5143、#5490、#5433、#5440、#5441、#3046、#2574 這一條線）。**Budget 功能本身**的 issue 交給 `silvia-futurenest`：#5438、#5468、#5486、#5487、#5488。安全（#5429、#5459–#5461）與 #5458、#5489 不在這兩條線上，維持原本的指派。

**狀態說明**：⬜ 未開始｜🔄 有 PR 進行中或部分完成｜⏸ 凍結｜✅ 已完成｜— 不適用
**main／rel／prod 欄**：✅ 該環境已包含這個修正｜⬜ 還沒有

| Issue | 內容 | 優先 | 階段 | 依賴 | 狀態 | PR | main | rel | prod |
|---|---|---|---|---|---|---|---|---|---|
| [#5429](https://github.com/futurenestit/xparse/issues/5429) | IAM internal 端點不用驗證、外網可達（含解密憑證） | P0 | 0 | — | 🔄 B：[#5455](https://github.com/futurenestit/xparse/pull/5455)（`b25e8b8e4`）、C：[#5456](https://github.com/futurenestit/xparse/pull/5456)（`cf07387f5`）已 merge；A／D（WAF、查 log、換 key）待 Peter | — | ✅ | ⬜ | ⬜ |
| [#5430](https://github.com/futurenestit/xparse/issues/5430) | `X-Request-ID` 被當成冪等鍵，重複的 id 會讓用量被丟掉 | P0 | 0 | — | ✅ | [#5453](https://github.com/futurenestit/xparse/pull/5453)（`478235056`） | ✅ | ⬜ | ⬜ |
| [#5431](https://github.com/futurenestit/xparse/issues/5431) | 非串流 failover 成功那次沒記帳，也跳過 output rail | P0 | 0 | — | ✅ | [#5449](https://github.com/futurenestit/xparse/pull/5449)（`f20167b01`） | ✅ | ⬜ | ⬜ |
| [#5437](https://github.com/futurenestit/xparse/issues/5437) | 契約互相矛盾 → 依 D1–D15 改文件 | P2 | 1 | — | 🔄 9 項矛盾中 8 項已解；剩第 8 項（三個 cost basis 名稱統一），已記入 #5142 的 SPEC-302 清單；issue 兼決策表，保持開著 | [#5457](https://github.com/futurenestit/xparse/pull/5457)（`fe26aa387`）、[#5472](https://github.com/futurenestit/xparse/pull/5472)（`56b20f28c`） | ✅ | — | — |
| [#5142](https://github.com/futurenestit/xparse/issues/5142) | ADR：ledger 是唯一帳本（Rev.2） | P1 | 1→3 | #5437 | 🔄 ADR-489 Rev.2（Status 仍 Proposed）＋SPEC-302 Rev.10 已 merge；Phase 1a／1b／2（Console）已 merge，Audit 側、Phase 1c／3 未做（[cost.md §5](../cost.md)） | [#5462](https://github.com/futurenestit/xparse/pull/5462)（`586a84eeb`）、[#5568](https://github.com/futurenestit/xparse/pull/5568)（`eafd38bcc`）、[#5574](https://github.com/futurenestit/xparse/pull/5574)、[#5588](https://github.com/futurenestit/xparse/pull/5588) | ✅ | ⬜ | ⬜ |
| [#5432](https://github.com/futurenestit/xparse/issues/5432) | judge／classifier 計量少算 | P1 | 2 | — | ✅ | [#5451](https://github.com/futurenestit/xparse/pull/5451)（`d10b54b14`） | ✅ | ⬜ | ⬜ |
| [#5450](https://github.com/futurenestit/xparse/issues/5450) | 預算檢查移到 judge 之前 | P1 | 2 | — | ✅ | [#5474](https://github.com/futurenestit/xparse/pull/5474)（`6ccc5be8e`） | ✅ | ⬜ | ⬜ |
| [#5434](https://github.com/futurenestit/xparse/issues/5434) | 兩條維運路徑重複計算 rollup | P1 | 2 | — | ✅ | [#5463](https://github.com/futurenestit/xparse/pull/5463)（`d8f83b93f`）、[#5473](https://github.com/futurenestit/xparse/pull/5473)（`7be01da50`） | ✅ | ⬜ | ⬜ |
| [#5435](https://github.com/futurenestit/xparse/issues/5435) | Audit 算不出失敗／重試的費用（縮小為對帳證據欄位） | P1 | 2 | — | ✅（已關；價格快照依 D1／D2 不做，FOCUS 改由 #5142 Phase 3） | [#5465](https://github.com/futurenestit/xparse/pull/5465)（`8c7337ca9`） | ✅ | ⬜ | ⬜ |
| [#5436](https://github.com/futurenestit/xparse/issues/5436) | 預算告警只掃最舊的 100 萬筆事件 | P1 | 2 | — | ✅（截斷的使用者告警另案） | [Xparse-Audit#185](https://github.com/futurenestit/Xparse-Audit/pull/185)（`1c9758e`）＋ pin bump [#5466](https://github.com/futurenestit/xparse/pull/5466)（`77121e57b`） | ✅ | ⬜ | ⬜ |
| [#5433](https://github.com/futurenestit/xparse/issues/5433) | 每個 user 的花費（D6／D11） | P1 | 2→3 | #5142 | 🔄 依 key 綁定的每人花費（aggregate `bound_user`）已 merge，在 pre-release 後；Am.J 表停寫、Phase 1c 刪表；**要不要關待 Peter** | [#5647](https://github.com/futurenestit/xparse/pull/5647)（`271e80357`）、[#5687](https://github.com/futurenestit/xparse/pull/5687)（`a9642a70a`） | ✅ | ⬜ | ⬜ |
| [#5439](https://github.com/futurenestit/xparse/issues/5439) | interim quota 讀取失敗回 0；per-tenant 失敗模式（D8） | P2 | 2 | #5450 ✅ | ✅（旗標 `budget_usage_unavailable_blocks`；後續 #5486–#5489） | [#5484](https://github.com/futurenestit/xparse/pull/5484)（`eacbbead4`） | ✅ | ⬜ | ⬜ |
| [#5442](https://github.com/futurenestit/xparse/issues/5442) | Limit window 多算一天 | P3 | 2 | — | ✅ | [#5464](https://github.com/futurenestit/xparse/pull/5464)（`5db917219`） | ✅ | ⬜ | ⬜ |
| [#5140](https://github.com/futurenestit/xparse/issues/5140) | 9 份算式：IAM 收斂成一份＋golden vector，其餘退場（09-30 改寫對齊 ADR-489） | P3 | 3 | #5142 | 🔄 IAM 部分已 merge（Audit／FOCUS 退場在 Phase 2–3） | [#5594](https://github.com/futurenestit/xparse/pull/5594)（`41a3aac2a`） | ✅ | ⬜ | ⬜ |
| [#3046](https://github.com/futurenestit/xparse/issues/3046) | judge 費用出現在成本畫面（透過 ledger，D1） | — | 3 | #5142 | ✅（pre-release 後；prod 發佈待 C-302-60／#5143） | [#5693](https://github.com/futurenestit/xparse/pull/5693)（`3bcd8c94b`） | ✅ | ⬜ | ⬜ |
| [#5438](https://github.com/futurenestit/xparse/issues/5438) | Dashboard 的 Budget 卡與 Budget 頁數字不同 | P2 | 4 | 部分依賴 #5142 | ✅ 已關（silvia-futurenest；卡上走勢仍讀 Audit，見 cost.md §5.11） | [#5553](https://github.com/futurenestit/xparse/pull/5553)（`fa307455e`） | ✅ | ⬜ | ⬜ |
| [#5441](https://github.com/futurenestit/xparse/issues/5441) | 13 個金額格式函式、「未定價」的顯示 | P3 | 4 | — | 🔄 `MoneyAmount`／`audit-amount` 已上（prod 也上，Peter）；Audit 事件表、waste、FinOps、Budget 卡未換；保持開著 | [#5689](https://github.com/futurenestit/xparse/pull/5689)（`88050adb4`）、[#5693](https://github.com/futurenestit/xparse/pull/5693)、[#5694](https://github.com/futurenestit/xparse/pull/5694) | ✅ | ⬜ | ⬜ |
| [#5440](https://github.com/futurenestit/xparse/issues/5440) | Runtime per-user 的 token 與 cost 用了不同的身分 | P2 | 4 | #5433 | 🔄 dev／rel 改依 key 綁定（pre-release 後）；prod 仍走 Audit 舊路徑；**要不要關待 Peter** | [#5695](https://github.com/futurenestit/xparse/pull/5695)（`b5513f3aa`） | ✅ | ⬜ | ⬜ |
| [#2574](https://github.com/futurenestit/xparse/issues/2574) | 使用者看自己的花費（D7） | — | 4 | #5433 | 🔄「我的用量」頁已 merge（pre-release 後＋租戶旗標 `my_usage_enabled` 預設關）；**要不要關待 Peter** | [#5689](https://github.com/futurenestit/xparse/pull/5689)（`88050adb4`） | ✅ | ⬜ | ⬜ |
| [#5468](https://github.com/futurenestit/xparse/issues/5468) | 排程好的 Limit window 到開始時間不會自動生效（sweep 只處理過期） | P2 | 2 | — | ⬜ | — | ⬜ | ⬜ | ⬜ |
| [#5143](https://github.com/futurenestit/xparse/issues/5143) | token 層級對帳（先定共同請求鍵、納入 loss marker）＋口徑表（09-30 改寫） | P3 | 5 | #5142 | 🔄 共同請求鍵已落地：Audit 事件帶 `ledger_request_id`／`ledger_producer`／`ledger_discriminator`；對帳 job 與 loss-marker 查詢還沒做 | [#5596](https://github.com/futurenestit/xparse/pull/5596)（`f2c3fc3df`） | 🔄 | ⬜ | ⬜ |
| [#5490](https://github.com/futurenestit/xparse/issues/5490) | routing 成本目標用沒有分級的單一價 → 決定要不要用 IAM 的計價 | P3 | 3 | #5140 | ⏸ 凍結（C-302-22 Rev.4）：確認各環境 active `length_tiers` 為 0 筆後撤回並關閉（cost.md §5.9） | — | — | — | — |

**已經修好、但還沒上 prod 的舊修正**

| 修正 | PR | main | rel（v1.77.0.1） | prod（v1.76.1） |
|---|---|---|---|---|
| #5135 judge 撞 key，把主生成的用量丟掉 | #5251 | ✅ | ✅ | ⬜ |
| #5136 `/v1/responses`、`/v1/embeddings` 沒記帳 | #5257 | ✅ | ✅ | ⬜ |
| #5137 失敗／重試沒進 ledger | #5277 | ✅ | ✅ | ⬜ |
| #5138、#5139 judge 兩軸都記帳、cost 列不再被吞掉 | #5274 | ✅ | ✅ | ⬜ |
| #5141 ledger 讀取失敗時不再退回 Redis 的 0 | #5286 | ✅ | ✅ | ⬜ |
| ADR-423 Amendment J（per-end-user rollup） | #5291、#5292 | ✅ | ✅ | ⬜ |
| ADR-423 Amendment K（每次 provider 呼叫都記錄、加上是否計費） | #5296 | ✅ | ✅ | ⬜ |

**#5143 對帳的已知缺口（2026-09-30，#5472 記錄）**：#5453 之後 ledger 列不再帶 client `request_id`，Audit 事件也沒有 `ledger_request_id`，INV-418-20 的逐筆比對目前沒有共同鍵；#5143 實作前要先決定鍵（例如讓 Audit 事件帶 gateway 產生的 ledger request id）。

**本輪修 #5429 時新開的後續 issue（2026-09-29，敏捷看板 #6、S8、指派 Peter）**

| Issue | 內容 | 優先 |
|---|---|---|
| [#5458](https://github.com/futurenestit/xparse/issues/5458) | 限流與 creator denylist 在 admit() 裡、判官之後才擋（D15 另開） | P2 |
| [#5459](https://github.com/futurenestit/xparse/issues/5459) | 憑證端點只認一把共用 node-agent secret → 改 Fleet per-node 身分（D12 長期） | P2 |
| [#5460](https://github.com/futurenestit/xparse/issues/5460) | `resolve-provider-credential` 參數宣告錯誤（永遠 422）＋ node-agent `verify=False` | P2 |
| [#5461](https://github.com/futurenestit/xparse/issues/5461) | scheduler／forecast 的 8 條 internal 路由仍是網路信任 | P3 |

**#5439 修完後新開的後續 issue（2026-09-30，敏捷看板 #6、S8、未指派）**

| Issue | 內容 | 優先 |
|---|---|---|
| [#5486](https://github.com/futurenestit/xparse/issues/5486) | IAM 查不到額度設定時，`GET /v1/usage` 顯示「沒設上限」（應為 `unavailable`） | P3 |
| [#5487](https://github.com/futurenestit/xparse/issues/5487) | 沒設過額度的 API key 用量回 0、沒讀 ledger；第一次從 Unlimited 加值會把上限設得比實際用量低，key 立刻被擋 | P2 |
| [#5488](https://github.com/futurenestit/xparse/issues/5488) | 503 `budget_usage_unavailable` 不寫 audit 事件（429 的預算拒絕都會寫） | P3 |
| [#5489](https://github.com/futurenestit/xparse/issues/5489) | 沒有任何設定去抓 IAM 的 `/metrics`，IAM 的計數器全都看不到（含 #5453、#5484 新加的） | P2 |

**相關的舊 issue（不在主線上，但要一起考慮）**

| Issue | 關係 |
|---|---|
| #3220、#2731、#4752 | Audit rollup 全量重算的效能問題；Phase 3 讓 Dashboard 改讀 IAM 之後，可能就不需要了 |
| #4006、#4007 | 手動指令 `backfill_usage_ledger_from_audit_events` 讀不到 `XPARSE_AUDIT_URL`／對帳時間窗不對齊。原本「修 #4006 之前要先做 #5434，否則會重複計算」的顧慮已解除（#5473 刪了首次建 Budget 的 backfill）；但這個指令本身跟 ADR-489 §2.1-14 方向相反，要不要退場已記入 #5142 的 SPEC-302 清單，**修 #4006 之前先等那個決定** |
| #3949、#4045、#4584、#3886 | 部署與 backfill 的追蹤單 |
| #4518 | 刪除價格段可能留下空窗，那段期間就變成未定價（要配合 D3 的顯示方式） |
| #4519 | `resolve_model_effective_pricing` 的 docstring 寫錯 |
| #3548 | FOCUS 1.4 匯出違反兩條 MUST |
| #3261 | 跟 provider 真實帳單對帳（Phase 5 之後再做） |
| #4367 | 跨 tenant 的 proxy membership 讓用量出現在錯的 tenant（程式缺陷追在 #4399） |
| #3898 | `XPARSE_BUDGET_COUNT_TOOLS` 要不要落地 |

---

## 6. 還需要 Peter 決定或授權的事

設計決策都已定案，剩下的是授權和排程（2026-09-30 更新）：

| # | 事項 | 現況／建議 |
|---|---|---|
| 1 | #5429 止血 | nginx 與 IAM 的修正已 merge（#5455、#5456），**還沒部署**；WAF 先不加（Peter，2026-09-30）；部署時程已在 #5429 留言請 senior 決定 |
| 2 | 查 Cloudflare 和 nginx 的存取紀錄 | 請 senior 決定要不要在部署前查；憑證端點有外部命中就換 key，object storage 金鑰優先 |
| 3 | 紀錄涵蓋不到整段暴露期間時，要不要預防性換 key | 建議平台自己的 system 範圍 key 預防性換掉；租戶的 key 只在紀錄有命中時才通知租戶換 |
| 4 | 已 merge 的修正什麼時候上 rel／prod | 跟下一個正常版本一起上；IAM、gateway、Console 同批；部署前先跑 `/deploy-gap` |
| 5 | 後續 issue 的排程 | #5458–#5461、#5468、#5486–#5490 都在 S8；#5433 等 #5142 Phase 3；清理類先不開 issue（§1.6） |

---

## 7. 給接手 agent 的工作守則

### 7.1 開工步驟
1. 確認本機是不是最新：
   ```bash
   cd /Users/peter/Desktop/X-parse/xparse && git fetch origin && git rev-list --count HEAD..origin/main
   ```
   結果不是 0，就不要相信本機的程式碼；改用 worktree，或用 `git show origin/main:<path>` 讀。
2. 要讀的東西：[cost.md](../cost.md)（系統怎麼運作、決策、待辦的技術判斷）、#5437 的決策表、要做的那張 issue 的內文和留言。issue 裡的 file:line 是當時的 commit 查的，main 一直在變，引用前都要重新 grep。
3. **確認沒有人正在做**（有其他 session 在平行修）：
   ```bash
   gh issue view <N> --json state,assignees,closedByPullRequestsReferences
   gh pr list --state all --search "<N> in:title,body"
   ```
4. 行為改動要先改文件（ADR／SPEC）再寫碼；PR 要附 ADR-093 表，新 ADR／PRD 要附 Core 對比表（CLAUDE.md §1.1、§17.4）。
5. 先寫整合測試，並用真元件驗證觸發條件（CLAUDE.md §8.1）。

### 7.2 系統事實、驗證方法、已知陷阱、禁止事項

都搬到 [cost.md](../cost.md)：系統事實（ledger key、producer、計價、讀取面）見 §2，CI gate 見 §3，守則與已知坑見 §7。

### 7.6 怎麼更新這份文件
- PR merge 之後：該列的「狀態」改成 ✅，填上 PR 和 merge commit，「main」欄改成 ✅。
- 部署之後：確認 rel、prod 是否包含那個 merge commit，再改對應的欄位：
  ```bash
  git fetch origin --tags
  git merge-base --is-ancestor <merge-sha> origin/rel && echo "rel 有"
  git merge-base --is-ancestor <merge-sha> <prod 的 release tag> && echo "prod 有"
  ```
  prod 實際跑的是 release tag（2026-09-29 是 v1.76.1），`origin/prod` 分支可能比較舊，以 tag 為準。
- 一次刷新所有追蹤項目的 GitHub 狀態：
  ```bash
  for n in 5429 5430 5431 5437 5142 5432 5450 5434 5435 5436 5433 5439 5442 5140 3046 5438 5441 5440 2574 5143 5468 5490 5458 5459 5460 5461 5486 5487 5488 5489; do
    gh issue view $n --json number,state,closedByPullRequestsReferences \
      -q '"#\(.number) \(.state) \([.closedByPullRequestsReferences[].number])"'
  done
  ```
- 最後更新頂部的「最後更新」日期，並在 §8.3 的變更紀錄加一行。

---

## 8. 附錄

### 8.1 關鍵 file:line 索引

舊索引（2026-09-29 `2a5392a7d`／09-30 `eacbbead4`）已過時，改看 [cost.md §2](../cost.md)（對 `6e0f6bb4e` 查證）。修復前的程式位置要用 `git show eacbbead4:<path>` 查。

### 8.2 LiteLLM 可以借鏡的地方（快照 `39d14bd`，2026-09-28）

- **值得學**：
  - 內部子呼叫繼承呼叫者的身分、標上 `internal_call_origin`，而且不算進請求數（`litellm/litellm_core_utils/internal_call_metadata.py`、`proxy/db/db_spend_update_writer.py:2766`）。
  - 回應的 header 會帶 judge 的成本（`x-litellm-classifier-cost`）。
  - 端到端一致性測試：一份固定的測試價表，加上 475 個手算的案例（`tests/integration/cost_calculation/`）。
  - 跟 OpenAI 帳單對帳（`proxy/spend_tracking/spend_capture_rate.py`）。
- **不要學**：
  - 用可變的 `spend +=` 累加欄位、錯誤直接吞掉、queue 滿了就丟、預設 fail-open。
  - 價表是全域、可以隨時改，而且沒有生效日。
  - provider 回報的成本會蓋過租戶自己設的價格。
  - admin 可以改 key 的 owner，所以它的 per-user 其實是「請求當下」的 owner。
- **它自己的教訓**：LLM-as-a-judge guardrail 沒有帶呼叫者的身分，費用整筆遺失。judge 的 client 應該在建立時就強制帶身分。
- Xparse 已經 vendor 了一份它的價表快照，拿來補 cache 的預設價：`apps/iam/xparse_iam/xparse_iam/reference_data/model_defaults_snapshot.json`（v1.99.0，只取 9 家）。

### 8.3 變更紀錄
| 日期 | 變更 |
|---|---|
| 2026-09-21 | 第一輪盤查，開了 #5135–#5143（見封存報告） |
| 2026-09-29 | 第二輪複查：開了 #5429–#5442 和 #5450；改寫 #5140、#5142、#5143；D1–D11 定案；#5431（#5449）和 #5432（#5451）已修好；本文件改為修復計畫與進度追蹤 |
| 2026-09-29 | D12–D15 定案（#5437 決策表同步）；#5429 C 改為「internal 預設拒絕 + node-agent 專用 binding」；更正 ADR-265 引用（INV-265-3，不是 INV-265-2）；#5430 有 PR #5453 |
| 2026-09-29 晚 | 開 PR #5455／#5456／#5457／#5462／#5463／#5464／#5465、Xparse-Audit#185；開 issue #5458–#5461；更正 #5429 暴露評估（provider 憑證端點永遠 422，object storage 金鑰端點真的可達） |
| 2026-09-30 | merge #5453（#5430）、#5472、#5473、#5474；關 #5430、#5434、#5435、#5450；開 #5468（limit window 不會自動生效）；#5429 留言請 senior 決定部署時程／查存取紀錄／換 key；#5437 剩第 8 項 basis 名稱；#5439 開工 |
| 2026-09-30（晚） | merge #5484（#5439，`eacbbead4`），#5439 已關；開 #5486–#5489（S8、未指派）；§0、§4、§6 改成現況；封存的 09-21 報告加上現況對照 |
| 2026-09-30（晚） | 依 Peter 的分工，Budget 功能的 issue（#5438、#5468、#5486–#5488）改指派 `silvia-futurenest`；新增 §1.5「計價有沒有統一、有沒有重複讀寫」（對 main `eacbbead4` 查證），更正 §1.1–1.3 與 §8.1 的計價數字 |
| 2026-09-30（晚） | 新增 §1.6：逐項對照現有 issue 是否涵蓋「統一計價」與「重複讀寫」——23 項中 8 項已涵蓋、5 項只涵蓋一半、10 項沒有 issue；#5140、#5143 的 Desired 與 ADR-489 不一致 |
| 2026-09-30（晚） | 依 Peter 同意：改寫 #5140、#5143 對齊 ADR-489；#5142 留 SPEC-302 清單；開 #5490（routing 計價）；清理類 issue 先不開。§1.6 更新為 17 項已涵蓋、6 項沒有 |
| 2026-09-30（晚） | 全文對齊現況：§0 計數改為 22 項；#4006 的警告改寫（#5473 已解除重複計算風險，但要等 SPEC-302 決定 backfill 指令去留）；§7 的冪等鍵格式、Audit pin、刷新清單；§8.1 索引 13 列改成 `eacbbead4` 的行號（標 †） |
| 2026-09-30（深夜） | 寫 SPEC-302 開 PR #5568（docs only）：Peter 定路由用分級價、backfill 指令退場、modifier 保留標明不生效、reasoning 用 output 價；對抗式審查 16 項已修；ADR-489 Rev.2、ADR-430 Am.C、ADR-300 Am.P、SPEC-215 Am.T、SPEC-276 Rev.17 |
| 2026-10-01 | SPEC-302 #5574、#5588 merge；關 #3949／#4006／#4007、改 #4045；Phase 1a 開 PR #5594（計價模組）、#5595（R1 expand、backfill 退場）、#5596（gateway 記錄端，draft）。Peter 定：全未定價時 Budget 回 0＋unpriced、moderation 有送出就算、NemoGuard 快取命中的幽靈事實順手修 |
| 2026-10-01 | merge #5594（計價模組）、#5595（R1 expand、backfill 退場，合併時與 #5594 解衝突、重產 OpenAPI）、#5596（gateway 記錄端＋`ledger-producer-parity-gate`）；三者都還沒部署 |
| 2026-10-01（下午） | 價格模型四個價格（Am.Q／R）；merge #5608／#5611／#5624／#5625／#5632／#5636／#5647／#5648；R2 開 draft #5640；Phase 2 以 pre-release 扣住、#2574 做「我的用量」頁（Peter） |
| 2026-10-01（晚） | merge #5686／#5687／#5689／#5690；「我的用量」預設關（Peter）；Forecast secret 選填（Peter）；Phase 2 畫面切換開工 |
| 2026-10-02 | merge #5693（Dashboard＋依用途，closes #3046）、#5694（列表／詳情，SPEC-302 Rev.10）、#5695（Runtime per-user，#5440）；#5441 格式在 prod 也上、Requests 格維持 Audit（Peter） |
| 2026-10-02（上午） | 新增 [../cost.md](../cost.md)（系統怎麼運作，對 main `6e0f6bb4e` 查證）。本文件改成只管進度：§2 決策表、§7.2–7.5、§8.1 索引改為連到 cost.md；§1.2 標為修復前；§5 更新 #5142／#5433／#5438（#5553 已關）／#5441／#5440／#2574／#5490（凍結）的狀態 |
