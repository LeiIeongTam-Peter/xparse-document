# Xparse 成本計算：系統怎麼運作（給接手的 agent）

> **對應版本**：`origin/main` `6e0f6bb4e`（2026-10-02 10:23 +0800，#5700 merge）。除非另外註明，本文所有 file:line 都在這個 commit 上查證過。**行號會漂移，引用前先重新 grep。**
>
> 檢查本機是否落後：
> ```bash
> cd /Users/peter/Desktop/X-parse/xparse && git fetch origin && git rev-list --count HEAD..origin/main
> ```
> 結果不是 0，就不要相信本機的樹，改用 worktree 或 `git show origin/main:<path>`。
>
> **兩份文件的分工**：
> - 本文件：系統怎麼運作，包括架構、契約、gate、決策，以及待辦事項的技術判斷。
> - [issues/cost-issue.md](issues/cost-issue.md)：每張 issue 的狀態、PR 編號，以及 main／rel／prod 欄位。
> - 同一件事只在一處寫細節，另一處放連結。
>
> **權威順序**：SPEC-302 → ADR-489 → 本文件。三者衝突時，以 SPEC／ADR 為準，並回頭修正本文件。
>
> **路徑寫法**：程式路徑都相對於 repo 根目錄 `/Users/peter/Desktop/X-parse/xparse`。`I/` 是 `apps/iam/xparse_iam/xparse_iam/` 的縮寫。

---

## 0. 三十秒速讀

- **一本帳**：每次 provider 呼叫，gateway 都記一筆用量事實到 IAM 的 `UsageLedgerEntry`。範圍包括主生成、判官、guardrail arm、失敗重試、moderation 次數、audio。事實裡只有 token 數，**不存金額**。
- **一個計價處**：只有 IAM 的 `I/authorization/usage_pricing.py` 會算錢，而且是在**查詢當下**算。每筆事實用涵蓋它 `occurred_at` 的那一段價格（`ModelPriceVersion`）計價。
- **讀取面**：Budget、admission、預算告警、`/v1/usage`、usage aggregate API（給 Console、Forecast）都讀 IAM。Audit 只剩**證據與對帳**兩個用途。
- **現況和目標的差距**：
  - prod 與客戶安裝的 Console 成本畫面，仍讀 Audit 的金額（被 pre-release entry `cost_surfaces_from_iam` 擋住）。
  - Audit 那一側（FOCUS、waste、事件表）還沒改。
  - **以上全部都還沒部署到 rel／prod**（§5.1）。

---

## 1. 全貌與資料流

```
請求 ─► gateway（apps/gateway/bustream）
        │  auth 邊界產生 ledger_request_id（gateway/auth_handler.py:167 bind_ledger_request_id；#5430）
        │  每次 provider 呼叫 = 一筆 phase=final 事實
        │  （token 軸；知道執行模型就另寫 cost 軸；audio 寫 audio_* 軸）
        │
        ├─► POST /iam/internal/budget/usage/append（I/api/ninja_api/_internal.py:958）
        │       └─► usage_ledger_entry（UsageLedgerEntry，append-only、不存金額）
        │             └─ 同一個 transaction 裡 fan-out（只限可扣款 producer、只限 phase=final）─►
        │                 budget_usage_daily_rollup（BudgetUsageDailyRollup，純加速快取，可整個重建）
        │
        │   計價：I/authorization/usage_pricing.py（全系統唯一一份 tokens × rate）
        │     ‧ 每筆事實用 occurred_at 落在的那一段 ModelPriceVersion 計價（半開區間）
        │     ‧ 某個 (model, UTC 日) 整天都被同一個 flat 段涵蓋時，才讀 rollup；其餘讀原始 ledger
        │
        │   讀取面（全部經過上面的計價模組）：
        │     Budget 頁／卡（plan 金額）· admission（query-batch）· budget preview · 預算告警 · /v1/usage
        │     usage aggregate API ─► Console（dev／rel 才讀，pre-release 擋住 prod）、Forecast
        │     price-facts、loss-markers ─► 給 Audit（端點已在 main，Audit 還沒接）
        │
        └─► Audit 事件（EXECUTION_COMPLETED 等）：帶 ledger_request_id／ledger_producer／ledger_discriminator，
              以及當作證據的價格快照（ADR-265）
              └─► 外部 Audit（3rd/xparse_audit）：保存證據、做 #5143 對帳（未做）
                  ※ Audit 目前仍自己算錢（latest／snapshot／FOCUS），prod Console 也仍讀它；Phase 2／3 才退場
```

一句話：**gateway 記量 → IAM 存量 → IAM 在查詢時計價 → 各畫面讀 IAM；Audit 只當證據和對帳。**

---

## 2. 各元件怎麼運作

### 2.1 記帳（gateway → IAM ledger）

**ledger key**（`apps/gateway/bustream/production/quota_counter.py:465` `final_idempotency_key`）
- final key 的格式是 `{ledger_request_id}:{axis}:final:{producer}[:{discriminator}]`。producer 若不在清單內，直接 `ValueError`。
- preflight key 的格式是 `{ledger_request_id}:token:preflight`（`:545`）。它只用來證明「記帳路徑是健康的」，**永遠不會摺進 rollup**（C-215-85）。
- `ledger_request_id` 由 gateway 在 auth 邊界產生，**不是**客戶端的 `X-Request-ID`。客戶端的 id 仍以 `request_id` 出現在事件上，但只用來關聯（C-215-127、SPEC-302 C-302-84）。
- discriminator 只用在同一個請求內可能出現多次的 producer：`generation_failed` 與 `moderation`。
  - 每次嘗試開始時產生一次（`gateway/usage_ledger_hook.py:94` `new_attempt_discriminator`），同一個值同時交給 writer 和 audit event。
  - 失敗的嘗試只經過一個「記帳＋發事件」的呼叫：`gateway/audit_helpers.py:455` `book_failed_attempt`（C-302-83a）。
- IAM 收到同一個 key 但內容不同時，回 409，並記 `usage_ledger_idempotency_conflict`（log 和 counter 各一份；`I/api/ninja_api/_internal.py:1084-1091`、`I/observability/metrics.py:151`）。
  - 比對哪些欄位見 `_ledger_resend_mismatch`（`_internal.py:938`），其中包含 `serving_proxy_application_code`。

**四個軸**（`I/db/models/budget_usage_ledger.py:89` `BudgetUsageAxis`）
- `token`：只要 `total_tokens > 0` 就寫。
- `cost`：只要知道執行模型就寫，**沒有任何門檻**（`gateway/usage_ledger_hook.py:533` `_maybe_schedule_ledger_final_write`；ADR-423 Amendment F、C-215-114）。
  - 這一列也只帶 token 數，錢由 IAM 在查詢時算。
  - 不知道執行模型時不寫 cost 列。這是唯一算不出價錢的情況（INV-213-4）。
- `audio_characters`、`audio_seconds`：每個 audio 請求一筆事實，`producer=audio`。數量放在 `units`，token 欄位全是 0。

**producer 清單**（兩端必須相同，由 `ledger-producer-parity-gate` 守）
- gateway 是權威：`quota_counter.py:344-378` `LEDGER_PRODUCERS`。
- IAM 是同源副本：`budget_usage_ledger.py:121` `BudgetUsageProducer`。
- IAM 收到不認得的 producer 會回 422。所以**新增 producer 時，IAM 要先認得，或兩端同一批改**。

| producer | 可扣款（進 rollup／Budget） | 說明 |
|---|---|---|
| `generation` | ✅ | 主生成 |
| `classifier_input`／`classifier_output` | ✅ | 內建 guardrail 判官（`llm_classifier`） |
| `tier_judge` | ✅ | `llm_judge_routing` 的分級判官 |
| `generation_failed` | ✅ | 失敗或重試的嘗試（D4），帶 discriminator |
| `audio` | ✅ | TTS 字元數、STT 秒數 |
| `guardrail_nemoguard`、`guardrail_jev`、`routing_jev` | ❌ | 會記錄，但不扣預算（D10、ADR-423 Amendment K）。**「不收費」絕不能用「不記錄」來實作** |
| `moderation` | ❌ | 0 token、`model_uuid=null`，只為了**數次數**（D10、C-302-80／81） |

**誰可扣款、怎麼判讀**
- 可扣款的集合是 **Budget 的政策**，不是用量本身的屬性：`CHARGEABLE_PRODUCERS`（`budget_usage_ledger.py:172`）。
  - 改這個集合等於改租戶要付的錢，必須單獨成一個變更（INV-418-36）。
- `producer` 欄位是 null 的舊事實：
  - 由 `fact_producer`（`:292`）從 key 的**結尾**判讀 producer（C-302-36）。
  - 不可只看前綴，也不可取最後一個 `:final:` 後面那段。
- `producer_is_chargeable`（`:184`）把 null 和 `""` 都當作可扣款。
  - 判斷一列時，一律寫成 `producer_is_chargeable(fact_producer(...))`。
  - 對應的 SQL 寫法是 `chargeable_fact_q`（`:345`）（C-302-15 Rev.6）。

**Audit backfill 留下的歷史列**
- 判別條件：key **完整符合** `audit-backfill:{event_id}:token`，而且 producer 是 null（`AUDIT_BACKFILL_KEY_PATTERN` `:216`、`is_audit_backfill_fact` `:240`）。
- 這些列算「ledger 之前的歷史」：計價、aggregate、price-facts、Budget 全都排除它們，重建 rollup 時也不摺進去（C-302-36a）。
- 列本身留在 ledger（append-only）。
- 寫出這些列的指令 `backfill_usage_ledger_from_audit_events` 已經刪除（C-302-100）。

**moderation 的次數**（C-302-81；Peter 的決定：「有送出就算」）
- 由 `gateway/usage_ledger_hook.py:253` `record_moderation_call_to_ledger` 寫入，一次 vendor 呼叫一筆。
- **算一次**：請求已經送往 vendor，不論結果是 2xx、非 2xx（含 429）、讀不懂的回應、連上之後逾時，或在途中被取消。
- **不算**：請求送出前就停下（資料邊界擋下、沒有 credential、根本沒連上），以及 memo 命中。
- 想查次數：aggregate 按 `producer` 分組，`producer=moderation` 那一組的 `facts` 就是次數。

**serving proxy**（C-302-82、ADR-453）
- ledger 欄位 `serving_proxy_application_code`（`budget_usage_ledger.py:481`）。
- gateway 從 AuthContext 原樣寫入。這個值由 IAM 在 validate 時綁定一次，**查詢時絕不重新推導**。
- 這個欄位上線之前寫入的事實是 null。aggregate 會回 `serving_proxy_since`，讓畫面知道從哪天起有歸屬。

**寫入失敗**（ADR-423 §2.2／§2.4）
- gateway 重試 3 次，仍失敗就寫 loss marker：`POST /iam/internal/budget/usage/loss-marker`（`_internal.py:1116`），寫進 `usage_loss_marker` 表。
- loss marker 不參與任何計算。
- gateway log 關鍵字：
  - `usage_write_loss`（`quota_counter.py:760`、`:821`）
  - `loss_marker_write_failed`（`:853`）
  - `usage_write_first_attempt_duplicate`（`:802`，第一次寫就撞到已存在的 key，C-215-130）

**Audit 事件上的 ledger 鍵**（C-302-83；這就是 #5143 要用的共同請求鍵）
- 每個對應到一筆 ledger 事實的事件，都帶三個欄位：`ledger_request_id`、`ledger_producer`、`ledger_discriminator`（`gateway/usage_ledger_hook.py:81` `ledger_fact_audit_fields`）。值和 ledger key 完全相同。
- 涵蓋的事件：
  - `EXECUTION_COMPLETED`：chat 串流／非串流、`/v1/responses`、embeddings、兩種 audio
  - `EXECUTION_FAILED`、`EXECUTION_RETRY_ATTEMPTED`、`PROVIDER_FALLBACK`、`TIER_JUDGE_INVOKED`
  - classifier 的 check 事件
- 沒有對應事實的事件，這三欄都是 null。
- 已知缺口見 §5.13。

### 2.2 Rollup（R1 已在 main；R2 是 draft #5640）

**基本結構**
- `budget_usage_daily_rollup`（`budget_usage_ledger.py:645`）只是快取：每一欄都是 ledger 的 `SUM`，可以整個重建。
- 一筆事實要 fan-out 到哪些 scope，由 `_internal.py:847` `_fanout_targets` 決定：

| scope | 期間 |
|---|---|
| `tenant` | 按月 |
| `group` | 按月，或依 Budget Plan 的 `plan_defined` 視窗 |
| `application` | 按月 |
| `application_interim` | `unbounded` |
| `api_key` | `unbounded` |

- fan-out 和寫入 ledger 在同一個 transaction 裡完成。

**R1**（migration `0354_spec302_r1_usage_rollup_producer_fact_count`，#5595，C-302-30..34）
- 新增兩個欄位：`producer`（`db_default=""`）、`fact_count`（`db_default=0`）。
- 唯一鍵：
  - **保留**舊的六欄唯一鍵 `uq_usage_rollup_composite_key`；
  - 另加七欄的 `uq_usage_rollup_key_producer`（`budget_usage_ledger.py:751-772`）。
- 寫入規則：
  - R1 一律寫 `producer=""`，同時累加 `fact_count`。
  - `""` 的意思是「重建前寫的、還沒按用途拆開」，**不等於任何一個 producer**。
- 和上一版的相容性：上一版程式用六欄 `get_or_create` 照常可以讀寫。六欄鍵還在，所以只會找到一列；它的 INSERT 不帶新欄位，由 DB default 補上。
- 新表 `usage_rollup_version`（`UsageRollupVersion`，`:796`）：
  - 只有 R2 的逐 tenant 重建會寫 `version=2`。
  - R1 每寫一列 `producer=""`，就在同一個 transaction 把該 tenant 的版本降回 1（`_internal.py:826` `_invalidate_rollup_split_marker`，C-302-39）。
  - R1 **從不建立** marker。
- 讀 rollup 的程式，必須把同一個六欄鍵下的多列加總（C-302-33）。

**重建**：`python manage.py recompute_usage_rollup --tenant <uuid>`（`I/management/commands/recompute_usage_rollup.py`，C-302-37）
- 每個 tenant 在一個 transaction 裡完成：
  1. 前置檢查；
  2. 刪掉該 tenant 的全部 rollup；
  3. 重新 fan-out；
  4. 逐 (kind, axis, producer) 比對 token 加總與 `fact_count`；
  5. 任何一項不相等就整筆回滾。
- 在 R1 上重建時，仍然寫 `producer=""`，也不寫 marker。
- **前置檢查會拒絕兩種情況**：
  - 有別的 tenant 的事實指向本 tenant 的 scope。
  - 本 tenant 持有已退場的「首次建 Budget 回填」事實，key 形如 `backfill:{scope_type}:{scope_uuid}:{period}:token`。部署前要先查有沒有（§5.1）。

**R2**（#5640，draft）
- 砍掉六欄鍵、fan-out 改寫真實 producer、重建時寫 `version=2`。
- **R2 只能退回 R1**：退到 R1 之前的版本時，六欄 `get_or_create` 會找到多列而失敗。merge 條件見 §6。

### 2.3 計價（IAM 唯一一份）

**模組分工**
- 入口是 `I/authorization/usage_pricing.py`，模組 docstring 就是規格摘要。
- 單價解析在 `I/authorization/pricing_rates.py`；價格段與 rollup 格子的規則在 `I/authorization/price_schedule.py`。這兩個模組**都不做 token 乘法**。
- 在 `usage_pricing.py` 以外寫出 tokens × rate，`iam-single-pricer-gate` 就會變紅。

**四個價格**（ADR-300 Amendment Q／R、SPEC-302 §2.6）：input、output、prompt cache read、prompt cache write。算式（C-302-6／7／8／9）：
- `fresh × input`
- `cache_read × cache_read`：沒寫 cache_read 價時退用 input 價，而且是已經乘過分級倍率的 input 價。
- `cache_write`：段裡有 `per_ttl` 時，用該段唯一一個 band 的 `flat`；**沒有任何 cache_write 設定時是 0**。
- `output × output`：**reasoning token 包含在 output 裡，以 output 價計**。價格模型裡沒有 reasoning 價。

**純量段**（沒有 `pricing` JSON，ADR-300 Amendment M 之前的舊資料）
- cache_read 與 cache_write 都用 input 價。這和 JSON 段的 0 **不一樣**，兩種行為都有 golden vector 釘住（C-302-6）。
- 新寫入不會再產生純量段（C-302-26）。

**實作細節**
- 單價在 `pricing_rates.py:308` `resolve_pricing`、`:360` `effective_rates`。
- `EXACT_CONTEXT`（`:43`）是 `Decimal`、prec 60、`ROUND_HALF_EVEN`，**全程不用 float**（C-302-5）。

**逐筆依 `occurred_at` 計價**（C-302-2／3）
- 用 active 且半開區間 `[effective_from, effective_to)` 涵蓋該筆事實的那一段（`PriceSchedule.covering`）。
- 舊做法是「整天都用 00:00 那一段的價」，已經移除。它正是當天中途換價時重算或漏算的原因（#5140）。

**rollup 只能用在整天單一 flat 段的格子**（`price_schedule.py:107` `rollup_segment`，C-302-4）

某個 (model, UTC 日) 要**同時**滿足以下三點才讀 rollup：
1. 恰好一段 active 段和這一天重疊，而且這一段涵蓋整天。
2. 這一段是 flat（`_segment_is_flat` `:38`）：沒有 `length_tiers`，cache_write band 最多一個。
3. 這一段有寫 input 和 output 價。

不符合的格子讀該格的原始 ledger，逐筆計價。兩條路徑對同一批事實的結果必須逐位相同，有測試守（C-302-20）。

> ⚠️ 文件漂移（待修，見 §5.12）：SPEC C-302-4 原文的條件 ③ 還寫著「沒有 `modifiers`」。但 Rev.4 之後計價已經不讀 modifiers（C-302-10），程式也不看。以程式和 C-302-10 為準。

**未定價**（C-302-12..16，D3）
- 可扣款事實在三種情況下算「未定價」：沒有涵蓋它的段、段裡缺 input 或 output 價、`model_uuid` 是 null。
- 未定價事實計入 `unpriced: {calls, tokens}`：**不貢獻金額，但也不能被跳過**。
- 不可扣款的 producer 既不計錢，也不算未定價。aggregate 對它們回 `billed_by_xparse: false`。
- **一組事實全部未定價時**（Peter，2026-09-30）：
  - Budget 的金額欄（`cost_used`、interim `cost_used_usd`、`query`／`query-batch` 的 `total`）**回 0**，旁邊附上 `unpriced`。原因是 Budget 欄位的 `null` 已經代表「讀不到」。
  - **只有 aggregate API 回 `null`**（C-302-13）。
- 明確設成 $0 的價格段計為 `"0"`，不算未定價。

**`pricing_error`**（C-302-10／11）
- 只在「既存的價格資料無法解析成四個價格」時觸發：`PricingError`（`pricing_rates.py:46`），會帶出 model 與 price_version 的 uuid。
- 各端點的反應：
  - 內部 `query`、`query-batch` 回 503 `pricing_error: …`。
  - gateway 把任何非 2xx 都當成 `budget_usage_unavailable`，交給 #5484 的 per-tenant 處置。
  - aggregate 回 degraded 200：`freshness.reason="pricing_error"`，數字全部是 null。
- **絕不轉成 0，也不轉成「未定價」。**
- 部署前要先盤點：`inventory_pricing_schema --json` 的 `active.pricing_error`（§5.1）。

**捨入**（C-302-17／18）
- 只在輸出時捨入一次：`quantize_usd`（`usage_pricing.py:87`），取 6 位小數、`ROUND_HALF_EVEN`。
- admission、preview、告警、Budget 對同一個 scope、同一段期間，必須得到同一個數。
- aggregate 的 `cost_usd` 是由精確總和捨入；四個 meter 則各自捨入。所以四個 meter 加起來可能和 `cost_usd` 差幾個 micro-USD，**以 `cost_usd` 為準**（C-302-52）。

**golden vectors**（C-302-19..21）
- IAM 發佈 `apps/iam/xparse_iam/contracts/pricing-formula.v1.json`，用 `pricing-formula.publisher.v1.json` 釘住 sha256。
- gateway 持有逐位元相同的副本 `apps/gateway/bustream/contracts/pricing-formula.consumer.v1.json`。gateway 的 `production/pricing.py:93` `resolve_pricing` 必須通過副本中「單價解析」那一部分。
- gateway 的 `resolve_pricing` 只解出**單價**，給 routing 的成本目標和 audit 的價格快照使用。**gateway 不計帳。**
- 改了 IAM 的 vectors，要在同一個 PR 更新 consumer 副本和 publisher 的 sha，否則 `pricing-formula-parity-gate` 會紅。

**已退場或停寫的價格形狀**（C-302-24；寫入規則在 `I/api/ninja_api/_price_write_rules.py:263` `pricing_write_error`）

| 形狀 | 寫入 | 計價 |
|---|---|---|
| `components.reasoning` | 新段帶任何值都回 400；修改既有段時只能原樣送回 | 不讀 |
| `components.cache_storage_rate` | 新寫入回 400 `pricing_cache_storage_rate_retired`；原樣送回放行 | 不讀；cache_write 依 per_ttl 或 0 計 |
| `modifiers`／`modifier_compat` | 新寫入回 400；原樣送回放行 | 不讀（事實上的 `active_modifiers` 也不讀） |
| `line_items` | 收掉。migration `0358_spec302_strip_pricing_line_items` 清除既有值，逐列比對清除前後的 `resolve_pricing` 結果相同才寫入 | 不讀 |
| `length_tiers` | **停寫**：新寫入回 400；修改時只能原樣送回，**拿掉也回 400**（要停用分級，就從某個日期另開新段） | **暫時照讀**；全收的條件見 §5.9 |
| `per_ttl[].mult`、`cache_read.mult`（倍率寫法） | 新寫入回 400，只收 flat 絕對值 | 舊形狀照舊：只有 mult 的 band 算 0，並記 warning |
| `unit`、`currency` | 只放行原樣送回 | — |

其他寫入規則：
- cache 欄位留空時：該 provider 有預設快取費率（ADR-300 Amendment H）就帶入預設，沒有就是 0（C-302-26）。
- 判斷「原樣送回」時，兩邊都要先經同一個正規化再比（C-302-25）。
- Console 的 `reprice-from` 用「日期 X 所在的那一段」預填（C-302-27）。

### 2.4 價格寫入與回溯改價

**誰能寫價格**
- 價格的權威是 IAM 的 `ModelPriceVersion`。
- Console 裡只有 Model Pool 能寫價格，由 `console-price-authoring-boundary-gate.sh` 守。

**改過去的價格會改寫歷史**
- 依 D2，所有金額都用**查詢當下的價目表**計價，所以改了過去的價格，歷史花費也會跟著變。沒有鎖帳期。

**回溯改價會留下兩筆紀錄**

觸發範圍：任何改到過去時間的價格寫入，包括新增段、修改段、`reprice-from`、刪除段，以及 lifecycle 刪除模型時一併刪掉的段（`application/use_cases/model/lifecycle.py:360`，#5636 起適用）。

1. 稽核事件 `iam.model_price.retroactive_change`（`I/api/iam_crud_audit/_emit_price_revision.py:50`，C-302-110），送到外部 Audit。
2. 在同一個 transaction 裡寫 `ModelPriceRevision`（C-302-111）：
   - model：`I/db/models/model_price_revision.py:26`，migration `0356`
   - 寫入函式：`I/db/django_database/_model_pricing.py:717` `write_schedule_with_revision`
   - 一次寫入若改到幾段不相連的時間，就寫幾列，共用同一個 `write_uuid`。

**預算告警怎麼使用這些紀錄**
- 下一輪告警掃描時，若同時符合以下兩點，告警 payload 會帶 `cause="price_revision"`（`I/authorization/budget_alert_price_revision.py:109`）：
  - 受影響區間和 plan 期間重疊；
  - 該 scope 在重疊期間內真的用過那個模型。
- 掃描下限 = 上一次成功掃描的 `started_at` − `SWEEP_LOWER_BOUND_OVERLAP`。後者是 60 秒，即 `PRICE_WRITE_COMMIT_DEADLINE`（30 秒）的兩倍。

**另一個會發同一事件的地方**：`I/management/commands/backfill_cache_pricing_defaults.py` 改到過去時間時。

### 2.5 讀取面

| 讀取面 | 入口 | 重點 |
|---|---|---|
| Budget（plan、單一 scope、batch） | `I/authorization/budget_usage_query.py`：`query_cost_usage_detail` `:238`、`batch_query_cost_usage_detail` `:479`、`batch_query_usage` `:521`。內部端點：`/iam/internal/budget/usage/query`（`_internal.py:1155`）、`query-batch`（`:1231`） | 只算可扣款事實，排除 backfill 歷史（C-302-15）；回應多了 additive 的 `unpriced`。Budget Plan 的讀取在 2026-10-02 由 ADR-433 Phase 5a（#4979，Silvia）改讀新形狀的表，屬 Silvia 的範圍 |
| admission | gateway `quota_counter.py:861` `reserve_from_ledger`（token）、`:936` `check_cost_from_ledger`（cost），都打 `query-batch` | 只讀已提交的用量，不預估本次請求（C-215-12）。讀不到時回 `usage_unavailable`，再由 #5484 的旗標 `budget_usage_unavailable_blocks` 決定放行（預設，D8）或擋下 |
| budget preview、預算告警 | `budget_preview.py`、`budget_alerts.py` | 告警的 Audit 備援已經拿掉（C-302-101）：ledger 讀不到就發 degraded 告警。但告警目前送不到任何人（§5.13） |
| `/v1/usage` | gateway `routes/usage.py`，經 `query-batch` | 由 `usage-endpoint-readonly-barrier-gate` 保證唯讀 |
| **usage aggregate API** | `I/api/ninja_api/_usage_aggregate.py`。Console 用 `GET /iam/usage/aggregate`（`:157`）；內部有 `GET /iam/internal/audit/usage/aggregate`（`:195`）、`GET /iam/internal/forecast/usage/aggregate`（`:201`）。三條路由共用同一個 handler | 細節見下方 |
| price-facts | `POST /iam/internal/audit/usage/price-facts`（`:241`） | 輸入 `{tenant_uuid, facts:[{ledger_request_id, producer, discriminator?}]}`，一次最多 2000 筆。找不到回 `found=false`、metrics 為 null，絕不回 0；跨 tenant 的鍵一律當作找不到（C-302-64／65）。**Audit 還沒接** |
| loss-markers 讀取 | `GET /iam/internal/audit/budget/usage/loss-markers`（`:288`） | 給 #5143 對帳，用來列出已知遺失（C-302-85）。**還沒有人用** |
| Forecast | `apps/forecast/src/xparse_forecast/adapters/iam_aggregate.py:34`（打 `/iam/internal/forecast/usage/aggregate`） | 細節見下方 |

**Forecast 細節**
- #5687 起改讀 aggregate；原本的 `series`、`end-users` 兩條內部路由已移除（C-302-102）。
- 憑證：header `X-Forecast-Secret`，env `XPARSE_FORECAST_IAM_SECRET`（`config.py:41`）。
- **沒設 secret 時，IAM 只接受 loopback**。這時 forecast 那一輪會是 partial 而不是 failed，`/forecast/health` 照樣回 ok；要看 `last_cycle.status` 才看得出問題。
- Forecast 本身是 pre-release 功能 `budget_forecast`（stage DEV，Silvia 負責）。

**aggregate API 細節**（SPEC-302 §4）

呼叫者綁定（`I/api/gateway_internal_auth.py:62-63`、`:76-82`、`:113-116`，C-302-41）：
- 每條內部路由只綁一個呼叫者：
  - Audit：`X-Audit-Secret`／`XPARSE_AUDIT_IAM_SECRET`
  - Forecast：`X-Forecast-Secret`／`XPARSE_FORECAST_IAM_SECRET`
- 兩者都**不得**使用 `NETWORK_TRUST`。由 IAM 測試 `test_internal_route_caller_bindings.py`（TC-302-32）守。

權限（`I/api/usage_aggregate_access.py`，C-302-61／62）：
- 依 Console `dashboard` 的 `data_scope` 決定：
  - system_admin：任一 tenant
  - tenant_admin、tenant_auditor：整個 tenant
  - group 角色：只限自己的 group；帶別的 group 回 403，不是回空結果
- 每次查詢恰好一個 tenant（C-302-42）。
- `mine=true`：
  - 只回綁在呼叫者 `(issuer, subject)` 名下的 key。
  - `group_by` 只能用 model、producer、api_key、application。
  - 回應帶 `bound_keys`；`0` 表示沒有任何 key 綁在你名下（Rev.9）。

參數上限（`I/authorization/usage_aggregate_request.py:39-48`）：
- `group_by`：公開路由最多 3 個，內部最多 4 個。
- `limit`：公開路由最多 1000，內部最多 10000。
- `offset` 只有內部路由能用。
- `billing`：預設 `chargeable`，可改 `all`。

查詢路徑（`I/authorization/usage_aggregate_plan.py:90` `plan_source`，C-302-58／59／38）：
- 視窗 ≤31 天，或 `bucket=hour` 且 ≤7 天：讀原始 ledger。
- 更長的視窗只接受「rollup 形狀」的查詢，上限 400 天。rollup 形狀是指同時滿足：
  - 整數個 UTC 日；
  - bucket 是 `none` 或 `day`；
  - `billing=chargeable`；
  - scope 維度最多一個；
  - 沒有 `serving_proxy`。
- **目前沒有任何 tenant 的版本是 2**（R2 還沒上），所以超過 31 天的 rollup 形狀查詢一律回 **409 `rollup_rebuild_pending`**。
- 不是 rollup 形狀、又超過上限：回 400 `aggregate_window_too_large`，絕不截斷後回傳部分結果。

回應內容：
- `basis="query_time_schedule"`。
- `metrics` 欄位：
  - `calls`：只算 generation 和 generation_failed，等於 provider 呼叫次數。
  - `facts`：所有 phase=final 事實，含不可扣款的；token 軸與 audio 軸每列記 1，cost 軸不另計。
  - 四類 token、四個 meter 的金額、`cost_saved_usd`（可以是負數）、`unpriced`。
- `coverage.ledger_since` 與 `partial`：見 C-302-56。
- 讀不到 ledger 時 `freshness.degraded=true`，數字全部是 null（C-302-55）。
- 維度怎麼取：
  - `provider`、`credential`：取模型**目前**的綁定。
  - `bound_user`：取 key 的 ADR-286 綁定；沒綁人的 key 歸入 `unattributed`（D6／D11／D14）。

**Console 各畫面：`cost_surfaces_from_iam` 開關前後各讀哪裡**

開關怎麼決定：
- entry 定義在 `I/core/pre_release_features.py:180`：`stage=REL`，owner Peter，2026-12-21 到期，governing doc 是 ADR-489。
- 依 host `.env` 的 `XPARSE_ENVIRONMENT` 判斷；**沒設或拼錯都當作 prod**。
- 結果：dev／rel 是 released（開），prod 與沒設標籤的客戶安裝是 withheld（關）。
- Console 一律透過 `usePreReleaseFeature("cost_surfaces_from_iam")` 讀取。共用 hook 是 `src/hooks/use-cost-surface-source.ts:25` `useCostSurfaceSource`。

| 畫面 | released（dev／rel） | withheld（prod、客戶安裝） |
|---|---|---|
| Dashboard 成本分頁：Current Spend、Token、Cache Savings、Requests、Cost/Token Trend、依用途分項卡，以及 stat／gauge／progress-tabs 外掛（`(dashboard)/_tabs/cost-usage/*`、`_components/cost-source/dashboard-cost-source.ts:161` `useDashboardAggregate`） | 讀 aggregate，`group_by` 對應各維度；`by_end_user` 改成 `bound_user` | 讀 Audit `/dashboard/usage-cost`、`/stats/summary`；算法不變，只統一了金額格式 |
| Dashboard Budget 卡（`budget-cost-card.tsx`） | 上限與 plan 金額讀 IAM；**走勢仍讀 Audit**（`useDashboardUsageCost`，`:68`），並標示為不同口徑 | 同左 |
| Applications 列表（`applications/page.tsx:413`） | aggregate `group_by=application`，用 `order_by` 排名 | Audit `/stats/top-applications` |
| LLM Proxy 列表（`llm-proxy/page.tsx:275`）與詳情（`components/features/llm-proxy/proxy-detail-view.tsx`） | aggregate 依 `serving_proxy` 分組或篩選（走原始 ledger）；`serving_proxy_since` 之前顯示「無法歸屬」，不顯示 0（Rev.10） | Audit |
| Application／Group 詳情的 Cost 格、API Keys 分頁（`components/features/api-key/api-key-usage.tsx`） | aggregate 篩選；但 **Requests 格、`error_rate`、`blocked` 仍讀 Audit**（屬營運指標，Peter 的決定） | Audit |
| Credentials（`credentials/page.tsx:169`）、Models legacy（`deployments-view.tsx:89`） | aggregate `group_by=credential`／`model` | Audit `/stats/top-*` |
| Runtime per-user（`runtime/_components/per-user-ledger*.ts(x)`） | aggregate `group_by=bound_user`；token 和 cost 用同一種身分（修 #5440） | Audit `/usage/per-user`（舊的身分分裂問題還在） |
| 「我的用量」（`my-usage/page.tsx`；nav 在 `src/config/nav.ts:75`） | 會顯示，但還要租戶旗標 `my_usage_enabled`（`I/authorization/feature_flags.py:823`，預設 HIDDEN，由 operator 逐一開啟）；查詢用 `mine=true` | **整頁隱藏**，路由也擋（`I/api/console_capabilities.py:1254` `PRE_RELEASE_PAGE_REQUIREMENTS`） |
| Audit 事件表的成本欄、Waste、FinOps／FOCUS | **仍讀 Audit**（Audit 那一側還沒做，§5.3） | Audit |

金額格式：
- IAM 的金額用 `components/features/cost/money-amount.tsx:79` `MoneyAmount` 顯示，底層是 `lib/format-money.ts:146` `formatMoney`。
- Audit 的金額用 `audit-amount.tsx` 顯示；遇到異常值顯示「—」，不會讓畫面崩潰。
- 依 Peter 的決定，這套統一格式**在 prod 也上**。

### 2.6 口徑標籤

- 所有由 IAM 計價的金額，對外標籤一律是 `query_time_schedule`（C-302-90），由 `cost-basis-label-gate.py` 守。
- 已經改名的地方：IAM `cost_basis`（migration `0355`）、gateway 預算 429 的 `basis`、forecast 的 `ledger_meter`、Console 的型別。
- **Audit FOCUS 的兩個標籤**（`estimated_at_time_of_use_list_price`、`x_CostBasis="estimated_list_price"`）要等 FOCUS 改向 IAM 取數時才改。FOCUS 現在還在用凍結價，提前改名會讓標籤和實際算法不符。
- `derived_sum_of_children`（Budget Plan）描述的是加總方式，不是價格口徑，保留不動（C-302-92）。
- ledger 之前的期間不接進 IAM 的序列，畫面上標示「用量自 <日期> 起記錄」。要看那段歷史，只能到標了 `legacy_audit_basis` 的舊檢視（C-302-94／95）。

---

## 3. 守住正確性的 CI gate

這些 gate 都在 `.github/workflows/ci.yml` 的 static-gates job 裡，每個都有 `--self-test`。本地可以直接跑 `python3 .github/scripts/<gate>`。

| gate | 擋什麼 | 契約 |
|---|---|---|
| `iam-single-pricer-gate.py` | 用 AST 掃 `apps/iam`：在 `usage_pricing.py` 以外只要出現「token 數 × 單價」就紅。起因是 `budget_usage_query.py` 從前有四份手抄的算式，彼此已經漂移 | C-302-1／23，TC-302-30 |
| `pricing-formula-parity-gate.py` | gateway 的 consumer 副本要和 IAM 的 golden vectors 逐位元相同；publisher 記錄的 sha 要等於 artifact 的 digest | C-302-21，TC-302-31 |
| `ledger-producer-parity-gate.py` | gateway 的 `LEDGER_PRODUCERS` 要等於 IAM 的 `BudgetUsageProducer`（用 AST 讀，不 import）。gateway 多出來的 producer 會被 IAM 回 422，那筆用量就整筆遺失 | C-302-80 |
| `cost-basis-label-gate.py` | `apps/`、`frontend/` 不得出現已退場的標籤（migration 豁免）；每個 producer 檔仍要有 `query_time_schedule` 字面值；已知的 emit 點不得出現第三種標籤 | C-302-90，TC-302-34 |
| `usage-ledger-surface-parity-gate.py` | 會 emit `EXECUTION_COMPLETED` 的 gateway 模組，必須同時呼叫記帳。起因是 #5136：responses、embeddings 漏帳好幾個月 | ADR-423 Am.E，C-215-112 |
| `provider-call-usage-parity-gate.py` | 拿到 provider client 的模組，必須記錄那次呼叫的用量。起因是 NemoGuard／Jev 的 arm 曾經真的花了 token 卻沒有記 | ADR-423 Am.K，C-215-124 |
| `usage-endpoint-readonly-barrier-gate.py` | `/v1/usage` 不得呼叫 reserve、admit 或 provider，也不得讀 `budget_layers` | SPEC-296 |
| `console-price-authoring-boundary-gate.sh` | 會寫價格的 hook，只能出現在 Model Pool 相關的路由 | ADR-300 Am.L |
| `pre-release-feature-registry-gate.py` | 不得再手寫環境判斷；pre-release entry 的 call site 不得增加 | ADR-473 |
| `test_internal_route_caller_bindings.py`（IAM 測試，不是 static gate） | 新增的 internal 路由必須宣告呼叫者；Audit／Forecast 不得用 `NETWORK_TRUST` | C-302-41，TC-302-32 |

**還缺的 gate**：TC-302-33（Console typecheck：成本元件讀 Audit 的金額就失敗）與 TC-302-35（grep gate：擋 `latest_cost_total`、`cost_total` 等欄位名）。兩者都要隨 C-302-72 一起做，見 §5.10。

---

## 4. 決策來源

### 4.1 D1–D15（Peter，2026-09-29）

正本是 [#5437 的決策表留言](https://github.com/futurenestit/xparse/issues/5437#issuecomment-5887615649)。下表每項一句話。

| # | 決定 |
|---|---|
| D1 | Audit 不替 judge 事件計價；Dashboard 改讀 ledger，自然就包含 judge 的花費，並按用途分項 |
| D2 | 所有畫面都依**查詢當下的價目表**計價，改過去的價格會改寫歷史；回溯改價必須留稽核 |
| D3 | 沒設價格不擋請求，畫面顯示「未定價」加筆數；只有明確設為 $0 的才顯示 $0 |
| D4 | 失敗和重試的嘗試都算錢，所有畫面一致，並分項顯示 |
| D5 | tenant 的總花費就是整個 tenant；受管 group 的加總只是 plan 的分配視圖 |
| D6 | 「user」指 API key 產生時綁定的那個人（ADR-286 的 `(end_user_issuer, end_user_subject)`）；沒綁人的 key 算「未歸屬」 |
| D7 | 使用者可以看自己的花費，只限綁在自己身上的 key（#2574） |
| D8 | ledger 讀不到時，預設放行並告警；另外提供 per-tenant 的「讀不到就擋」選項 |
| D9 | 預算檢查移到 judge 之前（#5450） |
| D10 | 內建判官和 tier judge 用判官模型自己的價格計；moderation 免費、只記次數；Jev／NemoGuard 記錄但不扣預算（UI 寫「由 TypeSafe 直接計費」，不寫「免費」） |
| D11 | 部署型 agent app 自動產生的 key 算「未歸屬」，花費在 application 層級看 |
| D12 | 兩個憑證端點改用 node-agent 專用的 secret，和 gateway binding 分開 |
| D13 | 移除 Amendment J 的 per-end-user rollup 表，每人花費改由 key 綁定反查；分兩次 release 砍掉 |
| D14 | 只有 `end_user` 文字標籤的 key 算「未歸屬」，未歸屬那一列仍顯示標籤；Audit 的 By End User 和 FOCUS 改成依綁定歸屬 |
| D15 | #5450 只把三項預算檢查移到判官前面；rate limit 和 denylist 另開 issue（#5458） |

### 4.2 Peter 之後的決定（2026-09-30 ～ 10-02）

| 主題 | 決定 | 出處 |
|---|---|---|
| 價格模型 | 每個模型只有四個價格：input、output、cache read、cache write | ADR-300 Am.Q／R；SPEC-302 Rev.4 §2.6 |
| reasoning | 先定「一律用 output 價」，後來改成**整個收掉**（寫入回 400、計價不讀） | C-302-9（Rev.1 → Rev.3） |
| modifiers | 先定「保留、標明不生效」，後來改成**寫入和讀取都收掉** | C-302-10（Rev.1 → Rev.4） |
| `cache_storage_rate`、`line_items`、倍率輸入、`unit` | 收掉，或只放行原樣送回（見 §2.3 的表） | C-302-24 |
| `length_tiers` | 先停寫；**拿掉也不允許**；確認 active 為 0 筆後才全部收掉 | C-302-24 |
| cache 欄位留空 | 有預設就用預設，沒有就是 0；不再寫純量段 | C-302-26 |
| 路由成本目標（#5490） | 原本定為改用分級價，**現已凍結**；確認 length_tiers 為 0 筆後，撤回 C-302-22 和 ADR-430 Am.C，並關掉 #5490 | C-302-22；ADR-430 Am.C（Frozen） |
| Audit backfill 指令 | 退場；已寫入的列當作 ledger 之前的歷史（不刪除、不計入） | C-302-100、C-302-36a |
| 全部未定價 | Budget 回 0，附 `unpriced`；只有 aggregate 回 null | C-302-16 |
| moderation | 只要請求有送出，就算一次 | C-302-81 |
| NemoGuard 快取命中產生的幽靈事實 | 在 gateway PR 裡順手修掉 | #5596 |
| R2 | 先不 merge，等 R1 成為各環境的已部署版本 | C-302-35；SPEC-302 §10 |
| Phase 2 | Console 程式碼可以先 merge，用 pre-release entry 擋住 prod | SPEC-302 Rev.3／Rev.9、C-302-60 |
| #2574 | 新增「我的用量」頁；預設關閉，由租戶逐一開啟 | C-302-62；flag `my_usage_enabled` |
| Forecast secret | 在 Pro tier 是選填變數，operator 之後再補 | #5687；`deployments/compose/tiers/docker-compose.pro.yml` |
| #5441 金額格式 | prod 也上（Audit 的異常值顯示「—」） | #5693 |
| 詳情頁的 Requests 格 | 維持讀 Audit（屬營運指標） | #5694；C-302-70 |
| 分工 | Peter 負責計價統一與去重；Budget 功能本身交給 silvia-futurenest；安全相關（#5429、#5458–#5461）和 #5489 不在這條線上 | [cost-issue.md §5](issues/cost-issue.md) |

### 4.3 不採用的方向

- 不做獨立的 cost 微服務。價格權威本來就在 IAM，而請求路徑只需要知道「有沒有價格」。
- 不把 ledger 改成從 Audit 衍生。Amendment K 之後 ledger 比 Audit 完整，而 Audit 依設計是 fail-open。
- 不在 ledger 裡存金額（C-215-77）。

---

## 5. 還沒做完、待檢查

每張 issue 的狀態欄位見 [cost-issue.md §5](issues/cost-issue.md)。這裡只寫技術判斷，每一項都包含：現況、卡在哪、下一步、相關的 PR 或 issue。

### 5.1 所有東西都還沒部署

**現況**（2026-10-02 查）：
- `origin/rel` = `6ccc5be8e`（09-30），`origin/prod` = `1dbffaccb`。
- 最新的 tag 是 `v1.77.0.1`／`v1.76.2`。
- 以上**都不含 R1**（`edb234abe`），也就是說，SPEC-302 的實作一個都還沒部署。

**卡在哪**：部署需要 Peter 授權，本線不做部署。

**部署前提**（依序）：
1. 每個環境都先跑唯讀的 `python manage.py inventory_pricing_schema --json`（`I/management/commands/inventory_pricing_schema.py`），看三項：
   - `active.pricing_error` 必須是 0（`active_pricing_error_rows` 會列出 uuid）。如果不是 0，#5686 部署後，該模型的 Budget 讀取會回 503，admission 也會把它當成讀不到。
   - `active.length_tiers` 與 `active_length_tiers_rows`：這是 §5.9 的前提。
   - `active_round_trip_candidate_rows`：Console 編輯不了的列，需要 operator 看過。
   - 更完整的唯讀檢查見 `docs/issues/price-shape-inventory-2026-10-01.md` 第五節（repo 外）。
2. 在 rel／prod 的 `envs/secrets.env` 設定 `XPARSE_FORECAST_IAM_SECRET`。沒設的話 forecast 只會 partial，不會報錯。
3. **IAM 先於 gateway 部署**；IAM、gateway、Console 要同一批（#5453、#5484、#5647 都改了 IAM contract）。
4. migration `0354` 會建索引，要挑低流量時段跑。
5. 有 `audit-backfill:` 列的 tenant（rel 確定有兩個，prod 未知），部署後各跑一次 `recompute_usage_rollup --tenant`。
   - 跑完之後，這些 tenant 的 Budget token 用量會少掉回填的那一段。
   - 跑之前先確認該 tenant 沒有首次建 Budget 留下的 `backfill:` 事實，否則重建會被拒絕（§2.2）。
6. 部署前先跑 `/deploy-gap`；部署後照 cost-issue.md §7.6 更新欄位。

### 5.2 R2 #5640

- **現況**：draft。migration 編號目前是 `0357`，**已經和 main 撞號**：main 上已有 `0357_adr490_tool_governance_policy_kind` 與 `0358_spec302_strip_pricing_line_items`。
- **卡在哪**：R1 還沒部署到任何環境。
- **下一步**：判定條件見 §6。

### 5.3 Audit 那一側（Phase 2 的 Audit 部分，外部 repo `3rd/xparse_audit`）

**現況**：IAM 的端點已經在 main 上（aggregate、price-facts、loss-markers，#5647），但 Audit 一條都還沒接。要做的事：
- FOCUS 改為呼叫內部 aggregate（`bucket=day`、`group_by=model,api_key,producer`，分頁取）。
- waste 和事件表的成本欄，改用事件上的 ledger 鍵去呼叫 price-facts。
- FOCUS 的標籤改名（§2.6）。
- Audit 開始送 `X-Audit-Secret`；rel／prod 也要設 `XPARSE_AUDIT_IAM_SECRET`。

**卡在哪**：
- 還沒開工。這需要兩個 repo 各一個 PR，再 bump pin（見 memory `reference_audit_submodule_two_repo_pr`）。
- FOCUS 匯出一個月的資料要約 63 秒（§5.6）。

**下一步**：等 Peter 決定是否進入 Phase 2b，之後照 SPEC-302 §5 表格的最後幾列做。

### 5.4 #5143 對帳 job

- **現況**：
  - 共同請求鍵已經落地（#5596，見 §2.1）。
  - loss-marker 的讀取端點已經落地（#5647）。
  - **對帳 job 本身還沒寫。**
- **卡在哪**：還沒開工。有兩類資料對帳時 join 不到：§5.13 的輔助 arm 提前阻擋、孤兒 cost 列。這兩類要在報表裡列為已知差異。
- **下一步**：依 ADR-489 §5.3 和 #5143 實作。它也是 §5.5 的前提之一：prod 要連續 7 天綠燈。

### 5.5 Phase 2 發佈到 prod（刪除 `cost_surfaces_from_iam`）

**前提**：
- C-302-60 效能驗收通過（§5.6）。
- #5143 在 prod 連續 7 天綠燈。

**刪除時要一起動的地方**：
- `I/core/pre_release_features.py:180` 的 entry。
- `I/api/console_capabilities.py:1254` 那一列。
- Console 的所有 call site：`grep -rn cost_surfaces_from_iam frontend/console-app-refactor/src`。
- Audit 金額的讀取路徑與型別（C-302-72，§5.10）。

同一個 PR 要附上 TC-302-41 的效能數字。

### 5.6 C-302-60 效能

- **現況**：還沒達標。在 SQLite、20 萬筆資料上實測：
  - Dashboard 30 天 p95 約 5.6 秒，目標是 <1 秒。
  - FOCUS 一個月約 63 秒，目標是 <30 秒。
  - 正式驗收的資料規模是 1,000 萬筆。
- **卡在哪**：要等 R2 的 rollup 路徑（版本 2），再加上 SQL 端預先彙總。目前 aggregate 只要視窗 ≤31 天，就一律讀原始 ledger。
- **下一步**：R2 上線並重建之後，在 Postgres 上用驗收規模重測。

### 5.7 Phase 1c：刪掉 Amendment J 的表

- **現況**：`budget_usage_end_user_daily_rollup`（`BudgetUsageEndUserDailyRollup`，`budget_usage_ledger.py:914`）已經沒有任何讀寫（#5687）。依 ADR-463，表和 model 要再保留一個 release。
- **前提**：1b（#5647、#5687）已經是各環境的已部署版本。
- **下一步**：寫 contract migration 刪表（`DeleteModel`），並跑 `migration-backward-compat-gate`。

### 5.8 Phase 3

- **要做的事**：
  - Audit 停止成本投影（C-302-103）：`enrich_events_with_latest_cost`、`latest_usage_cost_rollup`、legacy `usage_cost_rollup` 的金額欄，以及 `/dashboard/usage-cost`、`/stats/*` 的金額欄位，全部退場。
  - gateway 照舊把價格快照寫進事件，當作證據。
  - 舊檢視（C-302-95）一起退場。
- **前提**：Phase 2 已經在 prod 穩定跑過一個 release。

### 5.9 `length_tiers` 全收，以及撤回 #5490

- **前提**：rel、prod 和所有客戶自架環境跑 `inventory_pricing_schema --json`，`active.length_tiers` 都是 0。
- **下一步**：在同一個變更裡完成：
  - 收掉計價模組和 gateway `resolve_pricing` 的分級邏輯。
  - 收掉 golden vectors 裡的分級案例，並重新釘住 consumer 副本與 sha。
  - 撤回 C-302-22 與 ADR-430 Amendment C，並關閉 #5490。
  - 修正 `apps/gateway/bustream/gateway/routing_adapter.py:593` 的錯誤註解。

### 5.10 C-302-72：Console 型別拿掉 Audit 的金額欄位

- **現況**：還沒做。prod 目前走 withheld 路徑，仍在讀 Audit 的金額；現在拿掉，prod 會壞。
- **下一步**：和 §5.5 刪除 entry 放在同一個 PR，並一起加上 TC-302-33（typecheck）與 TC-302-35（grep gate）。舊檢視模組要列進允許清單。

### 5.11 剩下的金額格式（#5441）

- **現況**：IAM 的畫面和 Audit 的主要畫面已經改用 `MoneyAmount`／`audit-amount`。以下仍各自格式化：
  - Budget 卡：屬 Silvia 的範圍（她的 #5553 已經關掉 #5438），卡上的走勢還讀 Audit。
  - Audit 事件表、waste、FinOps。
- **下一步**：Audit 那一側（§5.3）改完時，順手換成同一個 formatter。Budget 卡的部分交給 Silvia。

### 5.12 文件與治理

- ADR-489 的 Status 仍是 Proposed；Core-ADR-13（FinOps）還沒建立。
- SPEC C-302-4 的條件 ③（modifiers）要改成和 C-302-10 Rev.4 一致。
- ADR-489 §2 第 10 點寫「浪費金額 = aggregate 的 `producer=generation_failed`」，和 ADR-445 的類別對不上：五類是 `failed`、`cancelled`、`retried_transient`、`retried_deterministic` 加上 `hidden_in_success`，其中 `cancelled` 與 `hidden_in_success` 的錢記在 `generation`，不在 `generation_failed`。以 SPEC-302 C-302-64 為準（分類留 Audit，金額由 Audit 用 ledger 鍵呼叫 price-facts），ADR-489 這句要改。已記在 #5518。
- 等 Peter 決定要不要關的 issue：#5433、#5440、#2574。它們的程式已經在 pre-release 下 merge，問題是現在就關，還是等發佈到 prod 再關。#5441 保持開著。
- TC-302-40 人工回退演練的前半段（用 R1 之前的版本，對已套用 R1 migration 的真 Postgres 跑 append 與 Budget 讀取）**沒有附在 #5595**，要在部署 R1 之前補做。

### 5.13 已知缺口（還沒修，部分沒有 issue）

| 缺口 | 影響 | 出處或位置 | 狀態 |
|---|---|---|---|
| 提前阻擋（C-223-65）時，NemoGuard／Jev 等輔助 arm 的 check 事件沒有 ledger 鍵 | #5143 對帳時 join 不到這幾筆 | C-302-83（SPEC 已宣告） | 沒有 issue |
| 孤兒 cost 列：token 那筆寫入遺失，cost 那筆寫成功 | 有計價，但 `facts`、`calls`、token 全是 0 | SPEC-302 §4.3 Rev.8 | 交給 #5143 列出 |
| guardrail 判官跑到一半，請求被取消 | 已經回答的內建判官，它花的 token 不計費（背景補完的那條路徑會計） | #5596 實作時發現 | **沒有 issue**（之前問過 Peter 要不要開，還沒有回覆） |
| `/iam/internal/forecast/targets` 仍是 `NETWORK_TRUST` | Forecast 的其他讀取仍靠網路信任 | `gateway_internal_auth.py:131` | #5461（屬安全線，不在本線） |
| 告警送不到任何人 | D8 的 degraded 告警、價格回溯的 cause，都只停在 Prometheus 的 `ALERTS`；IAM 的 `/metrics` 也沒人抓 | — | #5271、#5489 |
| FAE TC-RT-006 的腳本假設資料走 Audit 路徑 | 在 dev／rel 上，會和新的 Runtime per-user 畫面不一致 | `fae/tests/monitor-runtime/per-user-usage.spec.ts` | 需要補一個 ledger 路徑的版本 |
| agentd 的 `env_file` 是 `envs/secrets.env` | forecast secret 放進去之後，agentd 容器也拿得到（違反 SPEC-269 item 8 的精神） | Pro tier compose | runbook 已記錄，另案處理 |
| gateway `resolve_pricing` 遇到型別錯誤的價格值 | 可能拋出 `TypeError`／`KeyError`，而 `price_snapshot_fields` 沒有接住（模組 docstring 自己寫的） | `apps/gateway/bustream/production/pricing.py` 模組 docstring | 待檢查（IAM 端有 `pricing_error` 擋；先用 inventory 確認有沒有這種列） |
| Dashboard 成本分頁同一頁兩種計價 | dev（以及下次部署後的 rel）上，Current Spend 讀 IAM，同一頁的 Wasted Spend 讀 Audit 自己算的金額（例如 Audit 不替 judge 計價，D1），數字不能直接相比。Wasted Spend 已在 09-30 對所有環境開放（#5467）；prod 目前兩者都讀 Audit，暫時一致 | §5.3 的 waste 改走 price-facts 之前都存在 | 記在 #5518；它也擋住 Phase 3（§5.8） |
| ~~自助刪模型時硬刪價格段，不留紀錄~~ | — | `lifecycle.py:360` | **已修**：#5636 起會寫 `ModelPriceRevision` 和稽核事件（之前的筆記有誤） |

---

## 6. #5640（R2）merge 的判定條件

### 6.1 為什麼要等 R1 上 prod

- R2 的 migration 會砍掉六欄唯一鍵，fan-out 改寫真實的 producer，同一個六欄鍵下就會出現多列。
- R1 的程式能處理這種狀態：它寫 `producer=""`，讀取時加總。
- R1 **之前**的程式不能：它用六欄 `get_or_create`，會找到多列而失敗。結果是 rollup 寫入壞掉，每次 append 都失敗，用量只能落到 loss marker。
- 所以，一個同時帶 R1 和 R2 的 release **不能回退到 R1 之前**。
- 必須先讓 R1 單獨成為各環境的已部署版本，而且觀察期內沒有回退，回退的底線才會變成 R1（C-302-35、ADR-463）。

### 6.2 R1 上線後要看的指標

告警目前沒有人收（#5271、#5489），所以以下**全部要主動去查**。

| 來源 | 看什麼 | 正常的樣子 |
|---|---|---|
| gateway log | `usage_write_loss`、`loss_marker_write_failed`、`usage_write_first_attempt_duplicate` | 次數和部署前持平，理想是 0 |
| IAM log | `usage_ledger_idempotency_conflict`（同一個 key、不同內容的 409） | 0，或和部署前持平 |
| DB | `usage_loss_marker` 新增的筆數 | 0，或和部署前持平 |
| DB | 每小時的 ledger 筆數 | 曲線形狀和部署前相同，沒有掉到 0 的時段 |
| DB | 部署後新寫的 rollup 列 | `producer=''`，而且 `fact_count` 有累加（大於 0） |
| DB | `usage_rollup_version` | **0 筆**（R1 從不建立 marker） |
| 指令 | `recompute_usage_rollup --tenant <小 tenant>` | 能跑完，post-verify 通過。**這是寫入操作**，在 prod 跑要授權；可以先在 prod 的 DB 快照上跑 |
| Budget API | 同一個 scope、同一段已結束的期間，部署前後各讀一次 | 數字相同（前提：期間內沒有人改過價格） |
| 指令 | `inventory_pricing_schema --json` 的 `active.pricing_error`，以及 IAM log 裡的 `pricing_error` | 0 |

### 6.3 可以直接跑的唯讀 SQL

以下是 Postgres 語法，`:deploy_ts` 換成部署時間。

```sql
-- 0) R1 migration 已套用
SELECT name, applied FROM django_migrations
WHERE app = 'xparse_iam' AND name >= '0354' ORDER BY name;

-- 1) 每小時 ledger 筆數（final，按軸），部署前後各看 3 天
SELECT date_trunc('hour', recorded_at) AS hour, axis, count(*) AS facts
FROM usage_ledger_entry
WHERE phase = 'final'
  AND recorded_at >= :deploy_ts - interval '3 days'
GROUP BY 1, 2 ORDER BY 1, 2;

-- 2) 部署後寫的 rollup 列：應該只有 producer=''，而且 fact_count > 0
SELECT producer,
       count(*)                                AS rows,
       count(*) FILTER (WHERE fact_count = 0)  AS rows_with_zero_count,
       sum(fact_count)                         AS facts
FROM budget_usage_daily_rollup
WHERE occurred_date > (:deploy_ts)::date      -- 完整落在部署之後的日子
GROUP BY producer;

-- 3) 抽查一致性：tenant scope 的 token 軸 fact_count = ledger 中可扣款的 final token 事實數
--    （:day 取部署後的某個完整 UTC 日；部署後的 gateway 一定會帶 producer）
WITH r AS (
  SELECT scope_uuid AS tenant_uuid, sum(fact_count) AS rollup_facts
  FROM budget_usage_daily_rollup
  WHERE scope_type = 'tenant' AND axis = 'token' AND occurred_date = :day
  GROUP BY 1
), l AS (
  SELECT tenant_uuid, count(*) AS ledger_facts
  FROM usage_ledger_entry
  WHERE phase = 'final' AND axis = 'token'
    AND (occurred_at AT TIME ZONE 'UTC')::date = :day
    AND producer IN ('generation','classifier_input','classifier_output',
                     'tier_judge','generation_failed','audio')
  GROUP BY 1
)
SELECT coalesce(r.tenant_uuid, l.tenant_uuid) AS tenant_uuid, rollup_facts, ledger_facts
FROM r FULL JOIN l ON r.tenant_uuid = l.tenant_uuid
WHERE rollup_facts IS DISTINCT FROM ledger_facts;   -- 應該是 0 列

-- 4) marker 表：R1 期間應該是 0 筆
SELECT count(*) FROM usage_rollup_version;

-- 5) loss marker：部署前後每天的筆數
SELECT date_trunc('day', attempted_at) AS day, axis, count(*)
FROM usage_loss_marker
WHERE attempted_at >= :deploy_ts - interval '7 days'
GROUP BY 1, 2 ORDER BY 1, 2;
```

查詢 3 的注意事項：
- `audio` 的事實寫在 `audio_*` 軸，不會出現在 `axis='token'`。它出現在 IN 清單裡不影響結果。
- 若有 producer 為 null 的列（理論上只會來自 Amendment K 之前的 gateway），要改用 `fact_producer` 的規則判讀。

### 6.4 判定條件（四項全部成立才 merge）

1. prod（以 release tag 為準）、rel 與已知的客戶安裝，**都已經包含 R1**。檢查方法：`git merge-base --is-ancestor edb234abe <tag>`。
2. 部署之後觀察了 **3–7 天**。
3. §6.2 的指標全部正常。
4. 觀察期間**沒有回退到 R1 之前的版本**。

### 6.5 merge 前後要做的事

1. rebase 到最新的 main，並且**重新編 migration 號**：目前是 `0357`，但 main 上已有 0357 和 0358，所以要改成最新號之後的編號，`dependencies` 也要跟著改。
2. 補做 TC-302-40：用 R1 的程式，對已套用 R2 migration 的真 Postgres 跑一次。
3. merge 並部署之後，逐 tenant 跑 `recompute_usage_rollup --tenant <uuid>`。
   - aggregate 只有在版本 2 的 tenant 上才會用 rollup。
   - 還沒重建的 tenant，超過 31 天的查詢仍會回 409。
4. 重建一定要等舊版實例全部下線後才跑（C-302-39）。

---

## 7. 接手守則與已知坑

### 7.1 守則

- **不部署，也不對 rel／prod 送任何請求**；不讀、也不印出任何 secret 的值。部署與 prod 上的寫入操作，都要 Peter 授權。
- **先改文件再寫碼**（CLAUDE.md §17.1）：
  - 行為改動要先改 SPEC-302／ADR。
  - PR 要附 ADR-093 表與 Core 對比表。成本屬於領域 #13 FinOps，Core-ADR-13 還沒建。
- **用真元件測**（§8.1）：真的 `BudgetUsageLedgerWriter`、真的 IAM append 端點、真的 `ModelPriceVersion`。#5135 就是教訓：fake writer 讓 CI 綠燈，prod 卻在丟帳。
- 開工前先確認沒有其他人在做：`gh pr list --state all --search "<N> in:title,body"`。
- PR 的 base 一律是 `main`，用 squash merge。有依賴關係的 PR 照順序 merge，每 merge 一個就更新 cost-issue.md 與 memory。
- 不碰以下範圍：
  - Silvia 負責的 Budget 功能 issue（#5438、#5468、#5486–#5488）。
  - 安全線（#5429、#5458–#5461）。
  - #5489。
- 不要把 #5429 的利用方式（完整的請求範例）寫進任何文件或 issue。
- 建 issue 一律走 `/doc-issue`，並同步敏捷看板 #6（Status、工作類型、Priority、Epic、Objective、Sprint），之後讀回確認。
- 只有 application 的 API key 能打推論：tenant_admin key 做推論會被擋（`apps/gateway/bustream/gateway/auth_handler.py` 的 key 類型檢查），console_session key 是唯讀的。本地做 e2e 時要用 application key。

### 7.2 已知的坑

**git 與 commit**
- **用 worktree，不要用 `git stash`**：
  - 所有 worktree 共用同一個 stash 堆疊，曾經有 agent 把別人的 stash pop 到自己的分支上。
  - lint-staged 也會用到 stash，所以 commit 一律加 `--no-verify`，並在 commit 前自己跑 lint、typecheck 和相關的 gate。
  - 見 memory `reference_git_stash_shared_across_worktrees`。
- **不要讓 agent 跑 CI 的 git-auth 或 submodule-init 步驟**：曾經因此改壞 `~/.gitconfig` 和共用的 `.git/config`。
- **`Acceptance-Impact:` 這一行只能寫 `none` 或 TC 清單**：後面**不能接任何說明文字**，否則 CI 紅。改了 PR 描述不會重跑 CI，要 close 再 reopen。見 memory `reference_acceptance_impact_line_exact`。
- `.claude/hooks/guard-stacked-pr-merge.sh` 會用 shlex 解析整條指令，內文有單引號就會被誤攔。issue 和 PR 的內文一律用 `--body-file` 傳。

**IAM 改了 API**
- 要重新產生 OpenAPI，而且**必須用自己 worktree 的 venv**：`<wt>/apps/iam/.venv`，並設 `PYTHONPATH=<wt>/apps/iam`。用別的 worktree 的 venv，會因為 editable install 產出那一棵樹的 schema。
- 產生後要重新釘住 **6 處** consumer digest：console、gateway、fleet、node-agent、scheduler、forecast（清單見 CLAUDE.md §17.2 #7）。

**merge 衝突的固定解法**
- OpenAPI digest：取 HEAD 那一邊，在 merge 後的樹上重新產生 OpenAPI，再把 6 個 consumer 檔裡的舊 sha 換成新的。
- acceptance 產生檔：先 `git checkout --theirs`，再跑 `scripts/testing/build_feature_acceptance_workbook.py --write`，結果要**單獨**作為最後一個 commit（workbook 會記錄產生時的 revision）。
- CLAUDE.md、wiki log：保留兩邊，或取聯集。

**migration**
- **撞號**：main 每天都有新的 migration，merge 前一定要確認最新編號：`ls apps/iam/xparse_iam/xparse_iam/migrations | tail`。
- 本機跑 `makemigrations --check` 會被 secret guard 擋下，要加 `DJANGO_DEBUG=True`。
- 縮欄位或收緊約束，必須走 expand／contract（CLAUDE.md §8.3、`migration-backward-compat-gate`）。

**測試與環境**
- gateway 的 `tests/test_exit_receipts.py` 會留下孤兒 process，跑完要檢查並清掉。
- zsh 的坑：
  - `--include=*.py` 沒有匹配時會直接報錯，要加引號。
  - zsh 不做 word split，需要時改用 `xargs`。
  - `"$SHA:path"` 要加引號。
- **讀 Audit 的程式碼，要讀 main pin 住的那個版本**：先 `git ls-tree HEAD 3rd/xparse_audit` 取得 sha，再 `git -C 3rd/xparse_audit archive <sha>` 解到 scratch 目錄。本機的 checkout 常常和 pin 不一樣。
- **dev 的 IAM 改了程式要重啟容器才會生效**，驗證一律打真的 API。
- dev 的 IAM DB 是 SQLite，量到的效能數字不能當成 Postgres 的數字。

---

## 8. 變更紀錄

| 日期 | 對應 main | 變更 |
|---|---|---|
| 2026-10-02 | `03c95cb8f` | §5.12 加 ADR-489 §2.10 與 ADR-445 的浪費金額衝突；§5.13 加「Dashboard 成本分頁同一頁兩種計價」。同步更新 #5514、#5517、#5518 的 issue 內文（三張原本都停在舊狀態） |
| 2026-10-02 | `6e0f6bb4e` | 初版：依 SPEC-302 Rev.10、ADR-489 Rev.2 和程式現況整理。更正「自助刪模型不留紀錄」（#5636 已修）。新增三項：「重建會拒絕帶 `backfill:` 事實的 tenant」、「TC-302-40 前半段沒附」、「C-302-4 文件漂移」 |
