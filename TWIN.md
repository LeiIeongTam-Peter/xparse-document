# Twin（`smart_routing`）——它是什麼、怎麼運作

> **本文範圍**：Twin 策略的決策邏輯與執行邏輯全鏈路。
> **證據基礎**：`origin/main` 讀碼（2026-08-27）。**本文未跑 runtime probe**——所有行為描述都是對程式碼的閱讀結論，標示為「⚠️ 待驗證」的段落尚未有實測證據（§8.1 紀律：讀碼 ≠ verified）。
> **相關文件**：`docs/路由v2.md`（ADR-406 complexity routing 全程紀錄，Twin 在該案中「行為一天都沒變」）· ADR-088 Rev.3（strategy parameters）· SPEC-080（Twin 規則 T-1..T-9）· ADR-397 P2（role_assignments 死枝清除）· TD-004（QualityGate / SignalHub）

---

## 1. 一句話

**Twin 是「同一題讓兩顆模型一起跑」的路由策略**：快的那顆先把字串流給使用者看，強的那顆算完後發一個 `reverse` 事件把前面整段預覽換掉。它的策略值是 `smart_routing`，而且是 Application 的**預設**路由策略（`application.py:186` `default=RoutingStrategy.SMART_ROUTING`）。

名字裡的 "twin" 指的就是這對雙生的 fast / large 模型。

## 2. 定位——五個策略中的哪一個

`CANONICAL_WRITABLE = {none, smart_routing, complexity_routing, llm_judge_routing, agent}`（`.github/scripts/routing-strategy-value-gate.py:54`）

| 值                          | 實作                    | 幾顆模型執行 | 決策依據                                |
| --------------------------- | ----------------------- | ------------ | --------------------------------------- |
| `none`                      | `direct.py`             | 1            | 不選，直送                              |
| **`smart_routing`（Twin）** | **`twin.py`**           | **1 或 2**   | **請求複雜度 + `Model.tier`**           |
| `complexity_routing`        | `complexity_routing.py` | 1            | 請求難度 tier → pool 排序位置           |
| `llm_judge_routing`         | `llm_judge_routing.py`  | 1            | 同上，難度由 LLM 判                     |
| `agent`                     | —                       | —            | marketplace app-kind 標記，非 chat 路由 |

**Twin 是唯一會同時執行兩顆模型的策略**，也是唯一把 `Model.tier`（operator 在 Register 時宣告的 lightweight/standard/heavy）當決策輸入的策略——ADR-406 之後，`Model.tier` 的 runtime 消費者就只剩這裡。

> **命名陷阱**：`complexity_routing` / `llm_judge_routing` 文件裡滿篇的 "tier" 是 **request 難度** tier（`SIMPLE / MEDIUM / COMPLEX / REASONING`），跟 Twin 讀的 **model 能力** tier（`lightweight / standard / heavy`）是兩個不同的東西。

---

## 3. 決策層 logic（`xparse_routing/application/strategies/twin.py`）

策略是**純函數**：`resolve(context, models, config) -> ExecutionPlan`，無 I/O、同輸入必同輸出。它做兩個彼此獨立的決定。

### 3.1 決定一：這題複雜嗎（`_compute_complexity_score`）

五個訊號的加權和，clamp 到 `[0.0, 1.0]`：

| 訊號               | 計算                                     | 預設權重      |
| ------------------ | ---------------------------------------- | ------------- |
| prompt 長度        | `min(prompt_token_estimate / 2000, 1.0)` | `token` 0.3   |
| 對話輪數           | `min(message_count / 10, 1.0)`           | `message` 0.2 |
| 有無 tool 定義     | `1.0 / 0.0`                              | `tool` 0.2    |
| 有無 system prompt | `1.0 / 0.0`                              | `system` 0.1  |
| code block 數      | `min(code_blocks / 3, 1.0)`              | `code` 0.2    |

`score >= complexity_threshold`（預設 **0.7**）→ 判定為複雜。

兩個 knob 都可 per-app 覆寫（`parameters_schema`，ADR-088 Rev.3）：

```json
{
  "complexity_threshold": 0.7,
  "complexity_weights": {
    "token": 0.3,
    "message": 0.2,
    "tool": 0.2,
    "system": 0.1,
    "code": 0.2
  }
}
```

權重經 `sanitize_weights()` 過濾後與預設 merge——覆寫是**部分覆寫**，沒給的鍵保留預設值。

### 3.2 決定二：誰當 fast、誰當 large（`_assign_roles_from_config`）

```
lightweight 堆 = [m for m in models if m.tier == "lightweight"]  按 hard_constraint_rate 升冪
others 堆      = [m for m in models if m.tier != "lightweight"]  按 hard_constraint_rate 升冪

fast  = lightweight[0]  若該堆為空 → 全 pool 按品質排序取第一顆
large = others[0]       若該堆為空 → 全 pool 按品質排序取最後一顆
```

`hard_constraint_rate` 是歷史硬約束違反率（ADR-275 cost feedback 迴路，由 `routing_metrics_tracker` 的 EWMA 供給），**越低越好**，所以同一堆內是「品質歷史最好的先上」。

若 fast 與 large 撞成同一顆且 pool > 1，會強制換掉 large 取另一顆。

> **注意**：`Model.tier` 在這裡只被當成**布林**用——`== "lightweight"` 或不是。`standard` 與 `heavy` 在 Twin 眼中**完全等價**。三值詞彙實際只有兩個可區分狀態。

### 3.3 兩個決定合成 ExecutionPlan

| 條件                           | `plan.mode` | assignments                        |
| ------------------------------ | ----------- | ---------------------------------- |
| `len(models) == 1`（規則 T-7） | `direct`    | `[primary]` — 強制直送，不管多複雜 |
| 不複雜（規則 T-4）             | `direct`    | `[primary=fast]` — 只跑便宜那顆    |
| 複雜（規則 T-5）               | `twin`      | `[fast, large]`                    |

metadata 一律帶 `strategy_name` / `reasoning` / `confidence` / `complexity_score`；`confidence` 是與門檻的距離（`min(0.95, 0.5 + |score - threshold|)`）。

`models` 為空則 `raise ValueError`——fail-fast，不靜默降級。

---

## 4. 執行層 logic（gateway + streaming）

### 4.1 mode 翻譯

`routing_adapter.py:99` 把策略層的 plan mode 翻成 streaming manager 的 routing_mode：

```
plan.mode "direct" → routing_mode "fast_only"        （1 worker）
plan.mode "twin"   → routing_mode "fast_then_large"  （2 workers）
未知 mode          → "fast_then_large"（安全預設）
```

### 4.2 兩個 worker 真的平行

`manager_v3_events.py:920-928`，`fast_then_large` 分支同時 `asyncio.create_task` 兩個 consumer：

```python
tasks.append(asyncio.create_task(self._consume_fast()))
self._large_task = asyncio.create_task(self._consume_large())   # TD-004: 留參考以便取消
tasks.append(self._large_task)
```

兩顆模型**同時**收到同一份 messages，各自向自己的 provider 發請求。`self._large_task` 被單獨留著，是為了 §4.4 的取消路徑。

### 4.3 SSE 狀態機（CLAUDE.md §7 不變量的由來）

```
FAST_STREAMING    fast 的 delta 立刻串給使用者 —— 使用者「馬上看到字」
      ↓ fast 完成
LARGE_BUFFERING   large 還在跑，它的 token 先進 buffer 不外送
      ↓ large 完成（經 guardrail output 檢查）
REVERSE_EMIT      發一個 reverse 事件，內容是 large 的完整輸出
      ↓
FINALIZE / DONE
```

不變量（`state_machine.py` + `manager_v3_events.py`）：

- `id` 是 request-level 穩定，`seq` 單調遞增
- **reverse 至多發一次**，發完不再有 delta
- SSE 線上的 reverse 內容帶 `\n\n--- REVERSE ---\n\n` 標記（`sse_formatter.py:161`）；Anthropic 相容層在 `anthropic_translation.py:441` 剝掉這個標記並吸收覆寫語意（ADR-239 §2.1 D2）
- guardrail 在 REVERSE 之前介入：`block` → 改發 `guardrail_output_blocked` + `finish_reason=content_filter`；`modify` → 用去識別化後的文字取代 buffer 再 reverse

reverse 延遲（fast 完成 → reverse 發出的間隔）會被記進 obs log 與 metrics，是 Twin 的核心體感指標。

### 4.4 兩條「提前收掉 large」的路徑

Twin 最貴的部分是那顆 large。有兩個機制可以在它跑完前把它砍掉：

**(a) QualityGate（TD-004 Phase 2，`chat_quality_gate.py` + `bustream/quality/gate.py`）**

fast 一完成就評估它的輸出品質，夠好就取消 large：

- 預設**開啟**：`XPARSE_QUALITY_GATE_ENABLED=true`、`XPARSE_QUALITY_THRESHOLD=0.7`（`app.py:580-587`）
- evaluator 是 `RuleBasedEvaluator`——純規則計分（長度比例、結構完整性、是否 truncated、是否展示推理過程、任務複雜度…），0-100 正規化到 0-1
- `should_skip_large = score >= threshold and confidence >= 0.6`
- **fail-safe**：任何錯誤都預設「不跳過」，也就是照常跑 large
- 觸發時 `get_energy_saving_stats()` 記 `estimated_energy_saving_percent: 60`

**(b) SignalHub（TD-004 Phase 3，`chat.py:1535-1552`）**

使用者主動送 cancel signal 時，callback 呼叫 `manager.request_cancel_large(reason)`。只有 twin 系列的 routing_mode 會註冊這個 session。

兩條路徑都只砍 large——fast 的輸出已經送出去了，就是最終答案。

---

## 5. 計費與 audit

### 5.1 決策側

`resolver.py:280-297` 對**每一個**策略都算 `winner_tier`（第一個 assignment 的 `Model.tier`）寫進：

- `routing_decision_log.selected_model_tier`（`xparse_routing` 自己的 DB）
- `plan.metadata["selected_model_tier"]` → 由 `chat_helpers.py:131` 帶進 audit 的 `ROUTING_DECISION_RECORDED`

`plan_mode`（`"direct" | "twin"`）也在同一個 audit 事件裡（`audit/schema.py:517`）——**這是判斷某次請求有沒有真的走 twin 的欄位**。

QualityGate 決策另有 `QUALITY_GATE_DECIDED` 事件（`audit/schema.py:69`）與 `quality_gate_triggered` 旗標。

### 5.2 Token 計數 ⚠️ 待驗證

`manager_v3_events.py:1157-1172` 的 `_finalize_output_tokens()`：

```python
provider_completion = self._large_provider_completion_tokens or self._fast_provider_completion_tokens
counted = self.fast_token_count + self.large_token_count + self._tool_call_output_token_count
```

precedence 是 `provider 回報 > 串流實數 > 估算`（ADR-283 INV-283-2）。這裡有一個**不對稱**值得注意：

- provider **有**回 usage（常態）→ output tokens 取 **large 那一顆的** completion_tokens，fast 那顆生成的 token **不計入**
- provider **沒**回 usage → counted 是 **fast + large 相加**

也就是說同一次 twin 請求，記到的 output token 數會因為 provider 有沒有吐 usage chunk 而落在兩種語意上。**這是讀碼觀察，尚未以實測核對**——要下結論前應該對真實 twin 請求查 audit 落盤數字。無論哪一種，**provider 端都已經對兩顆各自計費了**，這是 Twin 的固有成本結構。

---

## 6. 不變量摘要

| #   | 不變量                                           | 位置                  |
| --- | ------------------------------------------------ | --------------------- |
| T-4 | 簡單請求 → direct，用 fast 當 primary            | `twin.py` `resolve()` |
| T-5 | 複雜請求 → twin，fast + large 平行               | 同上                  |
| T-7 | pool 只有一顆 → 強制 direct，不看複雜度          | 同上                  |
| —   | 策略層純函數、無 I/O、同輸入同輸出               | `resolve()` docstring |
| —   | `models` 為空 → `raise ValueError`，不靜默降級   | 同上                  |
| §7  | reverse 至多一次；reverse 後無 delta；`seq` 單調 | `state_machine.py`    |
| —   | QualityGate 出錯 → 預設不跳過 large（fail-safe） | `quality/gate.py`     |

---

## 7. 涉及檔案（依層列）

**決策層**

- `xparse_routing/application/strategies/twin.py` — 策略本體（計分 + 角色指派 + plan 產生）
- `xparse_routing/application/strategies/_weights.py` — `sanitize_weights()`
- `xparse_routing/application/resolver.py` — 呼叫策略、算 `winner_tier`、寫 decision log
- `xparse_routing/domain/protocols.py` — `RequestContext` / `ModelInfo` / `ExecutionPlan`（`RequestContext` 刻意不帶 prompt 原文——隱私不變量）

**Gateway 銜接**

- `bustream/gateway/routing_adapter.py` — plan mode → routing_mode；把 `tier` 與 capabilities 塞進候選
- `bustream/gateway/worker_setup.py` — 依 role 建 worker（retry 的 `initial_delay` fast 0.5s / large 1.0s）
- `bustream/gateway/routes/chat.py` — SignalHub 註冊、QualityGate 掛載、audit context
- `bustream/gateway/routes/chat_quality_gate.py` — QualityGate callback 組裝
- `bustream/gateway/routes/chat_helpers.py` — 把 plan metadata 攤進 audit

**執行層**

- `bustream/streaming/manager_v3.py` / `manager_v3_events.py` / `manager_v3_workers.py` — worker 啟動、狀態機、reverse、token 收斂
- `bustream/streaming/state_machine.py` — `StreamState` 列舉
- `bustream/streaming/non_streaming_collector.py` — 非串流路徑的 `_execute_fast_then_large`（`asyncio.gather` 兩顆，回 large 的結果）
- `bustream/gateway/sse_formatter.py` / `anthropic_translation.py` — reverse 標記的產生與剝除
- `bustream/quality/gate.py` / `evaluators.py` — QualityGate 與規則式評分器

**IAM / 設定**

- `xparse_iam/xparse_iam/db/models/application.py:91,186` — `SMART_ROUTING` 列舉值與 `default`
- `xparse_iam/xparse_iam/domain/model_tier.py` — tier 閉集詞彙（Twin 是它退場後唯一的 runtime 消費者）

---

## 8. 已知限制與待辦

1. **`standard` 與 `heavy` 對 Twin 無差別** — 角色指派只問 `== "lightweight"`。三值 tier 詞彙、migration 0264、六條 write path 驗證、`model-tier-value-gate.py` lockstep 這整套治理，目前守的是一個單一布林判斷。要嘛給 `heavy` 一個真實消費點，要嘛承認它是 Console 的展示標籤。
2. **複雜度計分只看結構、不看語意** — 五個訊號全是形狀特徵（長度、輪數、有沒有 tool）。一句短而極難的問題（`"證明黎曼猜想"`）score 極低 → 判 direct → 送 fast 那顆。這與 ADR-406 `complexity_routing` 讀 prompt 文字做關鍵字/推理標記計分是不同量尺。**中文流量在 Twin 下的表現未實測**（`complexity_routing` 的 CJK 失效問題由 PRD-293 修，Twin 的 `prompt_token_estimate` 是否有同樣的 CJK 低估，未查）。
3. **Token 計數不對稱** — 見 §5.2，⚠️ 待實測核對。
4. **QualityGate 的規則式評分未見校準紀錄** — threshold 0.7 與各項加減分常數的來源、以及「省 60% 能源」這個寫死的數字，都沒有在碼裡指向任何實測。預設是開的，所以這條路徑在 prod 每天都在跑。
5. **`role_assignments` 沒有設定面** — ADR-397 P2 已刪掉策略內的分支（gateway 永遠傳空）。`StrategyConfig.role_assignments` 本身保留是給 resolver 的 ADR-321 protected_ids 用，與角色指派無關。
