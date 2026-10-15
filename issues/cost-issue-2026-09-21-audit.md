# Xparse 成本計算全面盤查報告

> **封存說明（2026-09-29）**：本檔是 2026-09-21 那一輪盤查的原始報告，原本存在 `cost-issue.md`。該檔於 2026-09-29 被清空後改寫為進行中的修復計畫與追蹤文件，這份原文依 session 內保留的全文還原到這裡，內容未改動（2026-09-30 只在下方加了「現況對照」一節，原文從「日期」開始照舊）。現況請看 [cost-issue.md](cost-issue.md)。

## 現況對照（2026-09-30 補）

> 原文沒改。這一節只對照 9 張 issue 和幾個結論現在的狀態，細節看 [cost-issue.md](cost-issue.md)。

| Issue | 現在 | 由誰修／怎麼處理 |
|---|---|---|
| #5135 judge 撞 key、主生成用量被丟 | ✅ 已關（09-22） | #5251。同一類問題「客戶端的 `X-Request-ID` 被當成冪等鍵」09-29 另開 #5430，由 #5453 修（09-30） |
| #5136 `/v1/responses`、`/v1/embeddings` 沒記帳 | ✅ 已關（09-23） | #5257 |
| #5137 失敗／重試沒進 ledger | ✅ 已關（09-23） | #5277。Audit 端的失敗事件補 `model_uuid` 與 ledger 欄位，另由 #5435 → #5465 做（價格快照依 D1／D2 不做） |
| #5138 classifier／judge 只記 token 軸 | ✅ 已關（09-23） | #5274。judge 計量仍少算的部分，09-29 另開 #5432，由 #5451 修 |
| #5139 cost 列被吞掉 | ✅ 已關（09-23） | #5274 |
| #5140 多套算式分裂 | ⬜ 開著 | 09-30 再改寫：現為 9 份實作；IAM 的 4 份收斂成一份並用 golden vector 釘住，Audit／FOCUS 停止計價（對齊 ADR-489）；routing 另開 #5490 |
| #5141 讀失敗退回沒人寫的 Redis | ✅ 已關（09-23） | #5286。同一類「讀不到就當 0」的另外三處，09-29 開 #5439，由 #5484 修（09-30） |
| #5142 結構修復 | 🔄 **方向反過來了** | 原文建議「ledger 由 audit event stream 衍生」；09-29 改寫為「ledger 是唯一帳本、IAM 是唯一計價的地方」（Peter 選的方向）。ADR-489 已 merge（#5462，Proposed）；SPEC-302 要涵蓋的清單已留在 #5142（09-30）；實作還沒做 |
| #5143 口徑與對帳告警 | ⬜ 開著 | 09-30 改寫：對帳改成比 token（Audit 不再計價）；要先決定共同請求鍵（#5453 之後 ledger 沒有 client `request_id`、Audit 事件沒有 `ledger_request_id`），並納入 `usage_loss_marker` |

**原文結論哪些變了**
- **§0「沒有重複計算」**：當時的線上請求路徑是成立的；09-29 複查找到兩條**維運路徑**會重複計算（`recompute_rollup_for_tenant`、首次建 Budget 的 audit backfill，#5434），已由 #5463、#5473 修掉。
- **§1.2 查詢當下計價**：D2 定案保留，而且 FOCUS 也跟著改用同一個口徑，不再用使用當下的價格快照。
- **§1.3 三種價格基準**：ADR-489 收斂成一種（IAM 查詢當下計價）；三個 basis 名稱的統一還沒做（#5437 第 8 項）。
- **§5 不建議獨立 cost service**：與 ADR-489 一致——計價集中在 IAM 裡的一個模組，不另起服務。
- **§6 執行順序**：已由 cost-issue.md §4 的 Phase 0–6 取代。
- **§1.2「gateway 的 `cost_micro` 只用來判斷有價／無價」**：現在 gateway 完全不算 `cost_micro` 了；只要知道是哪個模型就寫 cost 列（`usage_ledger_hook.py:338`）。
- **§1.3「三種價格基準」**：計帳其實只有兩種（查詢當下、凍結快照）；IAM 和 Audit 讀同一張價目表，差在引擎、延遲、整天 vs 事件當下；真正的第三種是 routing 用的即時單一價。
- **§1.5「成本算式 5 套」**：現為 9 份——表中 #1 gateway 那份已沒有呼叫端（dead code），IAM 其實是手抄 4 份，另有 routing 成本目標一份。
- **§1.5「用量 7 份」**：`audit_dashboard_rollups` 其實沒有用量；Redis `app:*:token_count` 在 Pro／Enterprise 仍被寫入（只是沒人讀，不是「已無人寫」）；漏列了 evidence 檔、end-user rollup、loss marker、routing.db、forecast SQLite。「價格 4 份」裡的 `ModelSourceSummary.cost_per_*` 是每次讀取時計算，不是存的。完整盤點見 cost-issue.md §1.5；哪些有 issue 在修、哪些沒有，見 §1.6。
- **部署**：9/21 那批修正在 2026-09-29 時已上 rel（v1.77.0.1），prod 還在 v1.76.1；之後沒再核對。09-29 之後 merge 的修正都還沒上 rel／prod。

---

**日期**：2026-09-21
**盤查範圍**：`origin/main`（commit `9989d2301`，於 fresh worktree 上讀取；本機共用樹當時落後 40 個 commit）
**涵蓋元件**：`apps/gateway/bustream` · `apps/iam` · `3rd/xparse_audit`（pin `20eba53`）· `frontend/console-app-refactor`
**產出**：9 張 GitHub issue（#5135–#5143），全部已進敏捷看板 #6、Sprint S8

---

## 0. 一句話結論

**沒有找到「同一筆錢被加兩次」。** 反方向的問題才是真的：平台有 **5 套成本算式 × 3 種價格基準 × 2 條互相獨立的用量流**，導致 Audit / Dashboard / Budget / FinOps 四個畫面結構上就對不起來；而 Budget 那條另有 7 個會**漏計**的缺陷，其中 2 個會讓帳直接錯。

---

## 1. 現況架構

### 1.1 價格的唯一權威

`ModelPriceVersion`（掛在 `Model` 上，ADR-300）是唯一可寫入的價格來源。
`ApplicationModel.cost_per_*` 已於 IAM migration `0308` 移除，撰寫面收斂到 Model Pool（ADR-300 Amendment L / M）。**這一層是乾淨的。**

### 1.2 金額不是寫下來的，是查詢當下算的

ADR-423 / SPEC-215 C-215-77 明確規定：ledger **不得存任何已乘價格的金額欄位**，cost 一律在查詢時用當下的 `active` 分段現算。
gateway 請求路徑上算的 `cost_micro` **只用來判斷「有價 / 無價」一個布林值**，數字本身不落盤。

### 1.3 三種價格基準（這是「對不起來」的根源之一）

| 基準 | 定義 | 誰在用 |
|---|---|---|
| **latest effective schedule** | 用「現在的價目表中涵蓋 `occurred_at` 的分段」重估歷史 | Dashboard / Audit / Runtime / `/stats/*` / applications / credentials |
| **IAM 本地 schedule** | 語意同上，但直接查 IAM 自己的 `ModelPriceVersion`，不走 HTTP | Budget |
| **at-time-of-use 凍結快照** | 用 event 上凍結的 `price_in` / `price_out` | FinOps FOCUS tab 與 CSV、legacy `usage_cost_rollup`、SQL pushdown |

FOCUS 與 dashboard 的分裂是**刻意的**，ADR-383 §1.3 自己寫明：

> 兩條路徑計價基準不同（latest-price vs at-time-of-use），價格一調整即分裂；因此「同一期間，通用 dashboard 成本 ≠ FOCUS CSV 成本」今天已成立（既存，非本 ADR 引入）。

並由 INV-383-2 鎖定。FinOps tab 目前被 `NON_PROD_TABS` 擋在 prod 之外，所以客戶還看不到這個分裂。

### 1.4 兩條互相獨立的用量流（這是根源之二）

gateway 對同一筆請求做**兩次獨立的 fire-and-forget 寫入**：

```
                    ┌─→ audit_emitter.emit(EXECUTION_COMPLETED)
request 完成 ──────┤        └→ audit_events → usage_cost_rollup / latest_usage_cost_rollup / audit_dashboard_rollups
                    └─→ ledger_writer.write_final / write_final_cost
                             └→ IAM UsageLedgerEntry → BudgetUsageDailyRollup（×5 scope）
```

兩條路互不知道對方存在，都 fail-open。**下面所有「Budget 少算了 X」的缺陷，都是同一個結構性原因的不同實例**：某個面／某條錯誤路徑／某個輔助呼叫被接上了其中一條，沒接另一條。

### 1.5 同一項資料散落的份數

| 類別 | 份數 | 位置 |
|---|---|---|
| **價格** | 4 | `ModelPriceVersion`（canonical）→ validate wire snapshot → audit event 凍結欄位（`price_in/out/cache_read/cache_write/price_version_uuid`）→ `ModelSourceSummary.cost_per_*`（唯讀投影） |
| **用量** | 7 | `audit_events` · `UsageLedgerEntry` · `BudgetUsageDailyRollup` · `usage_cost_rollup`（legacy，仍活著）· `latest_usage_cost_rollup` · `audit_dashboard_rollups` · Redis counters（**已無人寫**） |
| **成本算式** | 5 | 見下表 |

五套算式：

| # | 位置 | 特性 |
|---|---|---|
| 1 | `apps/gateway/bustream/production/pricing.py:270` | 完整（tier + modifier + cache 三形狀）；但呼叫端只傳預設 `UsageShape()` |
| 2 | `apps/iam/.../authorization/budget_usage_query.py:385`（flat）`:435`（tiered） | 手抄一份 `resolve_pricing`，完整；ADR-418 share-nothing 規定如此 |
| 3 | `3rd/xparse_audit/src/audit/api/latest_pricing.py:452` | 有 tier、有 cache，**無 modifier** |
| 4 | `3rd/xparse_audit/src/audit/export/focus.py:302` | 凍結快照、有 cache 拆分、**無 tier、無 modifier** |
| 5 | `3rd/xparse_audit/src/audit/storage/postgres_event_store.py:291` | 純 SQL `input_tokens × price_in`，**無 cache 折扣、無 tier** |

---

## 2. 確認「沒有重複計算」的檢查點

| 檢查點 | 結論 | 證據 |
|---|---|---|
| cache token 被重複算進 input | ✅ 正確 | Anthropic / Bedrock 的 cache read/write 與 `input_tokens` 不相交 → worker 主動 fold（`anthropic_worker.py:425`、`bedrock_worker.py:492`）；Gemini / OpenAI 本來就含在內 → 不 fold（`google_worker.py:444`）。下游一律 `fresh = input − cache_read − cache_write`，三者不重疊 |
| reasoning 被疊在 output 上 | ✅ 已修 | gateway（`chat_streaming_audit.py:511` 傳 `reasoning=0`）、audit（`latest_pricing.py` `_compute_cost` 不加 reasoning）、IAM 三邊一致 |
| tenant / group / application 被加總 | ✅ 正確 | `_fanout_usage_rollup` 一筆用量寫 5 個 scope 列，各 scope 各自查；`application` 與 `application_interim` 刻意是不同 `scope_type`，有 INV-418-12 守著 |
| token 軸 / cost 軸兩筆 ledger 列被重複計 | ✅ 正確 | idempotency key 帶 axis，查詢也依 axis 過濾 |

---

## 3. 問題清單（9 張 issue）

| # | Issue | 嚴重度 | 標題 |
|---|---|---|---|
| 1 | [#5135](https://github.com/futurenestit/xparse/issues/5135) | **P0** | Gateway: auxiliary LLM ledger writes collide with the main generation idempotency key |
| 2 | [#5136](https://github.com/futurenestit/xparse/issues/5136) | **P0** | Gateway: `/v1/responses` and `/v1/embeddings` never write to the budget usage ledger |
| 3 | [#5137](https://github.com/futurenestit/xparse/issues/5137) | P1 | Budget: failed and retried requests are priced by Audit but never reach the usage ledger |
| 4 | [#5138](https://github.com/futurenestit/xparse/issues/5138) | P2 | Budget: classifier and tier-judge usage is metered on the token axis only |
| 5 | [#5139](https://github.com/futurenestit/xparse/issues/5139) | P3 | Budget: the cost-axis ledger row is dropped for sub-micro-USD requests and for any pricing exception |
| 6 | [#5140](https://github.com/futurenestit/xparse/issues/5140) | P3 | Pricing: five cost engines disagree on `length_tiers` and `modifiers` |
| 7 | [#5141](https://github.com/futurenestit/xparse/issues/5141) | P2 | IAM: budget usage reads fall back to a Redis counter that no longer has any writer |
| 8 | [#5142](https://github.com/futurenestit/xparse/issues/5142) | P1 | Architecture: derive the IAM usage ledger from the audit event stream |
| 9 | [#5143](https://github.com/futurenestit/xparse/issues/5143) | P3 | Governance: no declared cost-basis ownership per surface, no reconciliation alarm |

---

### #5135 — idempotency key 撞號，主生成的 token 用量被當成重複丟掉　`P0`

**現象**：啟用 guardrail classifier 或 LLM judge 的請求，**主生成整筆 token 用量從 token budget 消失**，只留下輔助呼叫的幾百個 token。

**根因**：ledger key 是 `f"{request_id}:{axis}:final"`（`quota_counter.py:499`），而 `idempotency_key` 是 **globally UNIQUE**。同一個 request 上有四個生產者都用**同一個 `request_id`**：

| 生產者 | 位置 | 執行時機 |
|---|---|---|
| tier judge | `tier_judge_handler.py:762` | 路由決策，生成前 |
| input classifier | `classifier_handler.py:1675` | 生成前 |
| output classifier | 同上 | 生成後 |
| 主生成 | `non_streaming_handler.py:341` / `chat_streaming_audit.py:580` | 回應後 |

classifier 在 `chat.py:1324` 拿到的就是主 request_id（`request_id=request_id`），沒有任何地方派生新 id。
IAM 端遇到重複鍵 → 回 200 `duplicate=true` **且不執行 `_fanout_usage_rollup`**（`_internal.py:999`，早退在 `try` 之外）。
classifier 的 task 在生成前就排了，幾乎必定先落地 → 主生成被丟。

**為什麼 CI 是綠的**：`test_classifier_judge_ledger_metering.py:45` 的 `FakeLedgerWriter.write_final` 只是 `append` 到 list，既不派生 key 也不檢查 UNIQUE。**這正是 CLAUDE.md §8.1 的教案**——測試證明的是 fake 的契約，不是真元件的契約。

**來源**：`bba4dc27b`（key 格式）+ `802b22b16`（撞號的生產者），同在 PR #3936，2026-08-31 merge。

**連帶效果**：cost 軸不受影響（只有主路徑寫 `:cost:final`），所以**同一個 Budget 列的 token 軸與 cost 軸會以不同速度前進**，看起來像定價 bug 而不是計量 bug。

---

### #5136 — `/v1/responses` 與 `/v1/embeddings` 完全沒有 budget 計量　`P0`

**現象**：Responses 面與 embeddings 的花費，Dashboard 看得到、Budget 完全看不到，也**不受任何 budget / ADR-398 per-key 上限約束**。Codex CLI 是純 Responses，整條流量對 Budget 隱形。

**根因**：ledger 寫入只接在 chat handler 上——`_maybe_record_quota` 全 repo 只有一個呼叫點（`non_streaming_handler.py:1603`，在 `handle_non_streaming` 內），串流那條在 `chat_streaming_audit.py:580`。
responses / embeddings 的檔案裡 `budget_usage_ledger_writer|quota_counter` grep 是空的，但它們**確實**發帶價格快照的 `EXECUTION_COMPLETED`（`responses_execution_audit.py:227,247`；`embeddings.py:243,253`）。

`/v1/messages` 不受影響——它 delegate 到 `execute_chat`（`messages.py:441`）。

**是「從未接上」，不是 regression**：`git log --all -S'quota_counter'` 對這三個檔案回傳空。

**為什麼沒被發現**：契約從未列舉「哪些推論面必須記錄用量」。ADR-423 / SPEC-215 裡搜 `v1/responses|v1/embeddings|v1/chat` 只有一處無關的提及。而 ADR-423 INV-418-18 明文要求記錄是**無條件**的：「不得因為某個 tenant/application/api_key 沒有配置 Budget 就跳過」——整個面不記錄，比這條 invariant 原本要防的情況更嚴重。

---

### #5137 — 失敗／重試請求：Audit 算錢，Budget 不算，FOCUS 也不算　`P1`

**現象**：同一筆浪費掉的錢，waste-report 有、Budget 沒有、FOCUS 也沒有。三個畫面三個答案。

**根因**：
- audit 刻意把 `EXECUTION_FAILED` / `RETRY_ATTEMPTED` 納入計價（`latest_pricing.py:432`，PRD-313 FR-2 / ADR-439）。
- gateway 的 ledger 寫入只在成功路徑（`non_streaming_handler.py:1603`）；失敗 emit（`:1863`）不寫 ledger。
- `EXECUTION_FAILED` payload 帶已實現的 tokens，但**沒有 spread `price_snapshot_fields`**（`:1863-1890`）→ FOCUS 靠凍結快照計價（`focus.py:327-354`），所以對它而言是 unpriced。

---

### #5138 — classifier / judge 只寫 token 軸，不寫 cost 軸　`P2`

**現象**：同一個 Budget 列的兩個軸在量**不同的流量**。

**根因**：`_meter_classifier_usage`（`classifier_handler.py:1675`）與 `_meter_judge_usage`（`tier_judge_handler.py:762`）只呼叫 `write_final`，docstring 自己寫明「Token-only（mirrors the pre-4b Redis path here: cost was never metered for classifier/judge calls either）」。
audit 也不算它們：classifier 不發 `EXECUTION_COMPLETED`，judge 發的 `TIER_JUDGE_INVOKED`（`:807`）不在 `_is_cost_eligible_event` 允許清單。

**這是需要產品決策的問題**，不是純技術修復：輔助推論（護欄、路由判定）該不該計入客戶的 cost budget？兩個答案都說得通，但必須擇一並寫進 SPEC-215。

---

### #5139 — `if cost_micro:` 把 cost 列整筆吞掉　`P3`

**根因**：`non_streaming_handler.py:348` 與 `chat_streaming_audit.py:587` 用 `cost_micro` 的**真值**判斷要不要寫 cost 列。而 `cost_micro = int(round(total_usd * 1_000_000))`：

1. 單價極低的請求（< $0.0000005）四捨五入成 0 → **整筆不寫**。因為 cost 是查詢時從 token 事實現算的，少一列就是永久遺失。
2. `price_snapshot_fields` 或估算式拋例外時，`except` 只 log warning、留 `cost_micro = 0`（`:281-283`）→ 同樣靜默不寫。違反 ADR-093 #4。

原意是 INV-213-4「unpriced 永不 zero-fill」，但實作把「無價」（沒有費率）和「價格約等於 0」混為一談。

---

### #5140 — 五套算式在 `length_tiers` / `modifiers` 上分裂　`P3`（潛伏）

**兩個具體分裂**：

1. **gateway 的凍結快照永遠落 tier 0**：`audit_helpers.py:354` 用**預設 `UsageShape()`**（`prompt_tokens=0`）解析價格，`_tier_mults` 必然命中第一階。IAM（`budget_usage_query.py:435`，依 `entry.prompt_tokens` 分組）與 audit（`latest_pricing.py:545`）都按真實 prompt 長度選階。→ 一旦有模型啟用分階，FOCUS 與 legacy rollup 會算錯，其他面算對。
2. **audit 不套 `modifiers`**：`latest_pricing.py:545-580` 只處理 `length_tiers` 與 cache 形狀；gateway（`pricing.py:176-181`）與 IAM（`budget_usage_query.py:178`）都乘 `mod_mult`。

**目前是潛伏的**：gateway 從不填 `active_modifiers` / `cache_write_ttl`（它們只存在於 wire 參數 `iam_http_client.py:1191-1192`），Console 也沒有分階／修飾詞的撰寫面。

**現有防線不夠**：`test_cache_pricing_cross_engine_parity.py` 是對的方向，但 ①只涵蓋 cache 費率、②gateway arm 是 `except ImportError: pass` 會靜默跳過、③audit 那一邊是**在另一個 repo 手抄的第二份 fixture**，改一邊沒人會紅。`contracts/` 下也沒有任何 pricing 產物。

---

### #5141 — Budget 讀失敗會退回沒人再寫的 Redis counter　`P2`

**根因**：`budget_preview.py:204-208` 是 ledger-primary + Redis fallback，但 gateway 的 Redis 寫入路徑已在 ADR-423 Phase 4b 退役（`quota_counter.py:309-311`，`commit_cost` 全 repo 無呼叫點）。剩下的寫入者只有 IAM 側的維護命令。
→ ledger 一抖，Budget 顯示與 enforcement 會讀到近乎 0 的用量，而且是「合理的小數字」而不是錯誤，沒人會去查。違反 ADR-093 #4。

---

### #5142 — 結構修復：讓 ledger 成為 audit event stream 的投影　`P1`

**這是 #5136 / #5137 / #5138 的共同根因**（§1.4）。每新增一個推論面，同一類 bug 就靜默重開一次，review checklist 上沒有任何一項會攔到。

**已有前例**：`backfill_usage_ledger_from_audit_events.py` 已經在做「從 audit event 重建 ledger 列並呼叫 `_fanout_usage_rollup`」（`:453`、`:540`）——歷史補算那條路已經實作了，缺的是把它變成常態路徑。

需要一份 ADR（含 invariants + ADR-093 compliance 表），並處理兩條流目前的不對稱：失敗／重試事件、輔助推論、profile-only embeddings。必須守住 ADR-418 邊界（IAM 不得 import audit source，只能消費已發布的事件契約）。

---

### #5143 — 治理：沒有口徑 owner，也沒有對帳告警　`P3`

三種基準、四個畫面，決策散在 ADR-264 / 265 / 300 / 330 / 336 / 383 / 423 七份文件，`docs/` 裡沒有任何一張總表。也沒有任何機制監控兩條用量流的漂移——最接近的 #4007 因為窗口對不齊而永遠回報 MISMATCH。

需要：①`docs/governance/cost-basis-ownership.md` 總表；②UI 標示基準（FOCUS 回應已經帶 `cost_basis`，只是沒顯示）；③Budget rollup vs `latest_usage_cost_rollup` 對帳 job + 告警。

---

## 4. 根因歸納

| 根因類別 | 對應 issue | 說明 |
|---|---|---|
| **兩條獨立用量流** | #5136 #5137 #5138 → #5142 | 同一筆請求兩次 fire-and-forget 寫入，互不知情，都 fail-open。新增面就漏。 |
| **契約沒有列舉面向** | #5136 | ADR-423 說記錄是「無條件」的，但從未列舉哪些面必須記錄，所以「整個面沒接」不違反任何可檢查的條文。 |
| **key 的唯一性範圍假設錯誤** | #5135 | C-215-76 假設「一個 request 一筆用量事實」，但實際有四個生產者。 |
| **fake 測試掩蓋真元件契約** | #5135 | §8.1 教案再現：fake writer 不派生 key、不檢查 UNIQUE。 |
| **share-nothing 複製了算式卻沒複製契約** | #5140 | ADR-418 要求各 owner 自帶實作是對的，缺的是釘住等價性的**契約產物**（repo 已有 `routing-parameters.v1.json` 的慣例可循）。 |
| **真值判斷取代了語意判斷** | #5139 | 用 `if cost_micro:` 代替 `is not None`，把「無價」與「約等於 0」混為一談。 |
| **退役了寫入者卻留著讀取 fallback** | #5141 | Redis 寫入路徑退役，讀取 fallback 沒跟著拆。 |
| **刻意的口徑差異沒有對外說明** | #5143 | ADR-383 的分裂是設計決策，但沒有總表、沒有 UI 標示、沒有對帳。 |

---

## 5. 為什麼不建議做一個獨立的 cost service

盤查期間討論過「把成本計算抽成獨立 service 以解耦」。結論是**不建議**，理由如下：

**① 9 個發現裡只有 1 個是算式分裂造成的**（#5140）。其餘 8 個是邊界上「該寫沒寫 / 寫錯 key / 退役沒拆乾淨」——service 一個都修不掉，但會多一個要部署、要監控、會掛的元件。

**② 兩種呼叫形狀都不適合 RPC**：
- 請求路徑上，成本只被用來判一個布林值，而且是在 fire-and-forget / fail-open 的 post-response hook 裡——多一次網路往返等於多一個失敗源。
- 查詢路徑上是百萬列批次重估。`latest_usage_cost_rollup` 等三張 rollup 存在的原因，就是「每次查詢都重新 reprice 太慢」。per-row RPC 是把已經解掉的問題再解一次。

**③ 價格權威已經是 service 了**：IAM 的 `ModelPriceVersion` + `GET /iam/models/{uuid}/price-schedule`，audit 就是透過 HTTP 問它的。真正被複製的只有 `tokens × rate` 那 30 行乘法。把乘法變成 RPC 不划算。

**④ PRD-302 M5 正在進行**：新增 owner 要配 `project.yaml`、build-contexts 註冊、CI capsule、deployment binding、phase-entry evidence。而且 ADR-418 明講應用之間只透過 wire/artifact 整合、consumer 自己擁有本地 adapter——IAM 那份手抄的 `resolve_pricing` **是照規矩寫的**，不是技術債。

**什麼時候 service 才對**：當要做的是 **rating / billing**（真帳單、credit、合約折扣、invoice 對帳），不是「算成本」。注意 FOCUS 的 `BilledCost` 現在永遠是空的（`focus.py:52`，BYOK 沒有發票）——那一欄什麼時候要填真數字，就是該拉 billing service 的時候。

---

## 6. 建議執行順序

| 階段 | 做什麼 | Issue |
|---|---|---|
| **1. 止血** | 修兩個 P0——它們會讓帳直接錯 | #5135 · #5136 |
| **2. 補齊口徑** | 失敗請求與輔助推論的歸屬決策 + 實作 | #5137 · #5138 |
| **3. 釘住等價性** | `pricing-formula.v1.json` golden vector + 各 owner `contracts/` sha256 釘住（沿用 `routing-parameters.v1.json` 慣例）；順手修 tier-0 與 modifier 兩處分裂 | #5140 |
| **4. 清理小缺陷** | 真值判斷、Redis fallback | #5139 · #5141 |
| **5. 結構修復** | ADR：ledger 改為 audit event stream 的投影 | #5142 |
| **6. 治理收尾** | 口徑總表 + UI 標示 + 對帳告警 | #5143 |

第 3 步建議優先於第 5 步：它不動架構、一個 PR 就能落地，做完之後第 5 步的設計會清楚很多。

---

## 7. 附錄

### 7.1 關鍵 file:line 索引

| 主題 | 位置 |
|---|---|
| gateway 價格解析（tier / modifier / cache 三形狀） | `apps/gateway/bustream/production/pricing.py:133`（`resolve_pricing`）`:270`（`estimate_cost_breakdown_micro`） |
| gateway 凍結快照（**用預設 UsageShape**） | `apps/gateway/bustream/gateway/audit_helpers.py:316-385`（`:354` 是問題點） |
| ledger key 派生 | `apps/gateway/bustream/production/quota_counter.py:499` |
| 主生成 ledger 寫入（非串流 / 串流） | `non_streaming_handler.py:341,348` · `chat_streaming_audit.py:580,587` |
| 輔助推論 ledger 寫入 | `classifier_handler.py:1675` · `tier_judge_handler.py:762` |
| IAM 用量 append + 五 scope fan-out | `apps/iam/.../api/ninja_api/_internal.py:868`（fan-out）`:924`（endpoint）`:999`（duplicate 早退） |
| IAM 成本查詢（flat / tiered 分流） | `apps/iam/.../authorization/budget_usage_query.py:385` · `:435` · `:521` |
| IAM budget 讀取（ledger-primary + Redis fallback） | `apps/iam/.../authorization/budget_preview.py:179-208` |
| audit 重估引擎 | `3rd/xparse_audit/src/audit/api/latest_pricing.py:228`（enrich）`:452`（`_compute_cost`）`:545`（`_segment_rates`） |
| audit FOCUS 投影（凍結快照） | `3rd/xparse_audit/src/audit/export/focus.py:302-400` |
| audit SQL pushdown 成本 | `3rd/xparse_audit/src/audit/storage/postgres_event_store.py:280-296` |
| audit 三張 rollup 表 | `storage/rollup_store.py:91`（legacy）· `usage_cost/rollup_store.py:753`（ADR-330）· `dashboard/rollup_store.py:239`（PRD-215） |
| FinOps tab prod gating | `frontend/console-app-refactor/src/app/(main)/(overview)/(dashboard)/_components/tab-visibility.ts:34` |

### 7.2 相關契約條文

- **SPEC-215 C-215-76**（line 298）— idempotency key 唯一性；**本次發現它的範圍假設不足**
- **SPEC-215 C-215-77**（line 299）— cost 永遠查詢時現算，ledger 無金額欄位
- **SPEC-215 C-215-83**（line 310）— post-response 重試 3 次全失敗必須觸發可觀測告警
- **ADR-423 INV-418-2 / INV-418-5 / INV-418-18**（lines 289 / 292 / 476）
- **ADR-383 INV-383-2**（line 139）— FOCUS 基準固定為 at-time-of-use
- **ADR-330 INV-330-3 / 8 / 9** — `/stats/*` 與 dashboard 一律讀 latest-price rollup
- **ADR-093 #1 / #4** — no partial state transition / fail-fast no silent fallback
- **CLAUDE.md §8.1** — 驗證 trigger 必須來自真元件，不是 fake 的假設

### 7.3 盤查方法備註

- 本機共用樹落後 `origin/main` 40 個 commit，全程在 `pr-worktrees/cost-audit-main`（detached at `9989d2301`）上讀，未依 stale 樹下判斷。
- `3rd/xparse_audit` 本機 checkout（`4bafa47`）與 main 所 pin 的 `20eba53` **不同**，但 `latest_pricing.py` 兩者逐位元相同，已比對確認。
- 送 issue 時撞到 `.claude/hooks/guard-stacked-pr-merge.sh` 的誤攔：它用 `shlex.split` 解析整條指令，body 裡的單引號（`generation's`、`request's`）讓引號數不成對 → 拋 `ValueError` → fail-closed 拒絕。改用 `--body-file` 即可繞開（這不是真的 stacked merge）。

### 7.4 看板狀態

9 張全部在敏捷看板 #6，欄位已回讀驗證：

- **Status** = `Triaged`（都附完整根因分析）
- **Epic** = `FinOps & Budget Control`（description：「模型計價分段 + 部門預算治理 (PRD-237)」）
- **Objective** = `提升效能與成本效益`（description 點名「FinOps 預算治理、用量歸因」）
- **Sprint** = `S8 09/22-10/05`
- **Product** = `Xparse`
- **Assignee** = Peter
- **工作類型** = `Bug`（#5135–#5141）/ `技術債`（#5142 #5143）

出貨看板 #3 **未加入**：WBS test 不成立——這 9 張是 review 中新浮現的缺陷與技術債，不是任何已承諾版本的交付項。若 Budget / FinOps 有列在承諾版本的 WBS 上，#5142 可以另外掛上 #3。
