# xparse_routing — 路由模組 API 文件

> **文件狀態**：正式
> **最後更新**：2026-05-31
> **相關 ADR**：ADR-085、ADR-088、ADR-093
> **相關 SPEC**：SPEC-080

---

## 模組定位

`xparse_routing` 為**程式庫模組**，不對外公開獨立 HTTP 端口。路由決策由 Gateway 在同一進程內透過函式呼叫觸發。

所有路由邏輯均在 Gateway 進程中同步執行，無需跨進程網路呼叫。

---

## 路由設定 API（由 Gateway Admin 路由代理）

以下端點由 **Gateway** 的 admin 路由層提供，底層讀寫 `xparse_routing` 的 `ConfigRepository`。

| 方法 | 路徑 | 說明 |
|------|------|------|
| `GET` | `/routing/config/{app_uuid}` | 取得指定 Application 的 `StrategyConfig`（`strategy_name` + 參數）。若尚無設定記錄則回傳 404。 |
| `PUT` | `/routing/config/{app_uuid}` | 合併 `output_length_category` 參數至現有 `StrategyConfig`。若無記錄則建立 `strategy_name=none` 的預設記錄。**不修改** `strategy_name`（由 IAM 管理）。 |

> **注意**：`strategy_name` 的擁有權在 IAM，config API 僅管理策略參數（`output_length_category`、`complexity_threshold` 等）。

---

## 前端 API 清單

`xparse_routing` 不對前端公開任何 API 端點。前端若需查詢或修改路由設定，需透過上述 Gateway admin 路由層的端點進行。

---

## 後端 API 清單

`xparse_routing` 不公開獨立後端 API，以程式庫形式直接被 Gateway 呼叫。

主要程式庫進入點：

| 函式 | 說明 |
|------|------|
| `Resolver.resolve(application_id, request_ctx, models)` | 同步解析路由決策，回傳 `ExecutionPlan`（所有 `POST /v1/chat/completions` 請求的主要路由路徑） |
| `Resolver.record_actuals(request_id, actual_prompt_tokens, actual_completion_tokens)` | Streaming 完成後修補實際 token 數至決策日誌（fire-and-forget，卸載至 thread pool） |
| `ConfigRepository.get(application_id)` | 取得應用程式的 `StrategyConfig`（含 TTL in-memory cache，預設 60 秒） |
| `ConfigRepository.save(application_id, config)` | 寫入或更新 `StrategyConfig` |
| `get_routing_metrics()` | 回傳模組層級 `_Metrics` singleton（含各計數器） |

---

## 路由策略

| 策略名稱 | 類別 | 說明 |
|----------|------|------|
| `none` | `DirectStrategy` | 無條件 pass-through，使用 `models[0]`。若 models 為空則拋出 `ValueError`。 |
| `smart_routing` | `TwinStrategy` | 基於複雜度分數（0–1）決定 `direct` 或 `twin` 模式。分數 ≥ `complexity_threshold`（預設 0.7）且 models ≥ 2 時使用 twin；否則 direct。分數來源：token 估計、message 數量、tool 定義、system prompt、程式碼區塊。 |
| `health_aware` | `HealthAwareTwinStrategy` | 延伸 `TwinStrategy`，加入健康感知。從 `ModelInfo.capabilities` 讀取 `health_score` 與 `circuit_breaker_open`；若僅剩一個健康 model 則降級為 direct。 |
| `cost_first` | `CostFirstStrategy` | 選擇估算成本最低的 model（`cost_per_input_token × prompt_tokens + cost_per_output_token × output_tokens`）。`output_tokens` 由 `output_length_category` 驅動（short=200、medium=600、long=1500）。若 `cheap_risk_score ≥ cheap_risk_threshold`（預設 0.3），改選最便宜的非 lightweight 計費 model（viability guard）。無計費資料的 model 排除在外，最終以 list 順序為 fallback。 |
| `energy_first` | `EnergyFirstStrategy` | 選擇 `joules_per_output_token` 最低的 model（靜態硬體 benchmark 數值）。排除 `circuit_breaker_open=True` 的 model（若全部 open 則 fail-open）。可選 `min_tier` 下限排除 lightweight model。 |

### 策略設定欄位

| 策略 | 可設定欄位 |
|------|-----------|
| `none` | 無 |
| `smart_routing` | `complexity_threshold`、`role_assignments.fast`、`role_assignments.large` |
| `health_aware` | `complexity_threshold`、`min_health_threshold`、`role_assignments.fast`、`role_assignments.large` |
| `cost_first` | `output_length_category`、`cheap_risk_threshold` |
| `energy_first` | `min_tier` |

---

## 工作流程

以下為 `xparse_routing` 在每次 `POST /v1/chat/completions` 請求中的決策流程。步驟 1–2 與 9–10 為 Gateway 自身邏輯，僅作銜接說明；步驟 3–8 與 11 為 `xparse_routing` 負責的範圍。

### 路由決策流程概覽

```
步驟 1   IAM 驗證 → AuthContext 組裝（Gateway）
步驟 2   Policy 評估（Gateway，pure function，無 I/O）
步驟 3   RequestContext 建構                      ← xparse_routing 邊界開始
步驟 4   ModelInfo 清單建構（注入 health data）
步驟 5   StrategyConfig 載入（含 TTL cache）
步驟 6   策略查找（StrategyRegistry）
步驟 7   Strategy.resolve() — 純函數決策（無 I/O）
步驟 8   決策日誌寫入（fire-and-forget）          ← xparse_routing 主路徑結束
步驟 9   ExecutionPlan → routing_mode 映射（Gateway）
步驟 10  StreamingManager 執行（Gateway）
步驟 11  Token 實際值修補（async，xparse_routing）
```

### 各步驟說明

| 步驟 | 執行者 | 動作 |
|------|--------|------|
| 3 | `routing_adapter.build_request_context()` | 從 messages list 提取 `prompt_token_estimate`（4-char 啟發式）、`message_count`、`has_system_prompt`、`has_tool_definitions`、`code_blocks` 數量，產生不可變的 `RequestContext`。 |
| 4 | `routing_adapter.models_from_auth_context()` | 將 `AuthContext.models`（依 `sort_order` 排序）轉換為 `list[ModelInfo]`，並注入每個 model 的 `health_score`、`circuit_breaker_open`、`avg_latency_ms`（來自 `ModelHealthTracker` 快照）及成本與能耗欄位。 |
| 5 | `ConfigRepository.get(application_id)` | 查 TTL cache（60 秒），miss 時 SELECT `routing_strategy_config` 資料列。若無記錄，`Resolver` 使用 `StrategyConfig(strategy_name='none')` 預設值（直通模式）。 |
| 6 | `StrategyRegistry.get(strategy_name)` | Thread-safe dict 查找策略名稱。未知策略且 strict mode（預設）時拋出 `RoutingResolutionError`；`degraded_allowed=True` 時 fallback 至 `DirectStrategy`。 |
| 7 | 所選 `RoutingStrategy.resolve(context, models, config)` | **純函數，無 I/O**。計算並回傳 `ExecutionPlan`，包含 `mode`（`direct` 或 `twin`）與 `assignments` 清單（含 `role`、`model_id`、`model_name`、`provider`）。 |
| 8 | `Resolver._write_decision_log()` | 寫入 `routing_decision_log` 資料列（見「決策日誌」章節）。失敗時遞增 `routing_decision_log_failures_total` 計數器並記錄 WARN，**不影響請求路徑**。 |
| 9 | `routing_adapter.execution_plan_to_routing_mode(plan)` | 映射 `plan.mode` → legacy `routing_mode` 字串：`direct` → `fast_only`，`twin` → `fast_then_large`。未知 mode 預設為 `fast_then_large`。 |
| 11 | `Resolver.record_actuals()` via thread pool | Streaming 完成後，Gateway 將此呼叫卸載至 thread executor。`DecisionLogRepository.update_actuals()` 修補現有日誌列的 `actual_prompt_tokens` 與 `actual_completion_tokens`。Fire-and-forget，失敗被 swallow。 |

### Fallback 路徑

當 worker 回傳可重試錯誤（`provider_timeout`、`provider_unavailable`、`provider_error`、`provider_stream_error`、`circuit_breaker_open`）時，Gateway fallback handler 會**再次呼叫** `Resolver.resolve()`，但從 models 清單中排除失敗的 model，觸發新一輪路由決策。

### Twin 策略複雜度評分（`smart_routing` / `health_aware`）

```
score = (prompt_token_estimate / 2000) × 0.3
      + (message_count / 10)           × 0.2
      + has_tool_definitions            × 0.2
      + has_system_prompt               × 0.1
      + (code_blocks / 3)               × 0.2

score ≥ complexity_threshold（預設 0.7）且 models ≥ 2 → mode=twin（fast + large 雙軌）
score <  complexity_threshold 或 models < 2           → mode=direct（快速模型）
```

---

## 服務關聯圖

| 外部服務 | 關係方向 | 性質 | 說明 |
|----------|----------|------|------|
| `routing.db`（SQLite / PostgreSQL） | 讀寫 | 同步 SQLAlchemy | 讀取 `routing_strategy_config`；寫入 / 修補 `routing_decision_log`。 |
| IAM（透過 Gateway 注入的 `AuthContext`） | 讀（間接） | in-process 物件傳遞 | `xparse_routing` 不直接呼叫 IAM；`AuthContext`（含 `routing_strategy`、`models` 清單）已由 Gateway 取得並以函式參數形式傳入。 |
| `ModelHealthTracker`（Gateway in-process 元件） | 讀（間接） | in-process 函式呼叫 | `routing_adapter` 在建構 `ModelInfo` 時呼叫 `health_tracker.get_health(model_uuid)`；策略本身只讀 `ModelInfo.capabilities` dict，不直接接觸 `HealthTracker`。 |
| 進程內 `_Metrics` singleton | 寫 | 直接記憶體操作 | 計數器遞增，可透過 `get_routing_metrics()` 讀取。 |

---

## 決策日誌（`routing_decision_log`）

每次路由決策（步驟 8）都會寫入一筆日誌記錄，供可觀測性與審計使用。符合 ADR-093 §Layer 2 可觀測性要求（Invariant 4：fail-fast, no silent fallback；Invariant 5：`request_id` 由 Gateway 在邊界注入後保持不可變）。

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | UUID | 主鍵 |
| `application_id` | string | 應用程式識別碼 |
| `request_id` | string | 請求識別碼（`correlation_id`，由 Gateway 在邊界注入並保持不可變，ADR-093 Invariant 5） |
| `strategy_name` | string | 實際使用的策略名稱 |
| `input_summary` | JSON | `prompt_token_estimate`、`message_count`、`has_system_prompt`、`has_tool_definitions`、`code_blocks`、`stream`、`cheap_risk_score`、`cheap_risk_threshold` |
| `execution_plan` | JSON | `mode`、`assignments[{role, model_id, model_name, provider}]` |
| `reasoning` | string | 決策說明（最多 512 字元） |
| `selection_reason` | string | 預定義代碼（見下表） |
| `duration_ms` | int | 路由決策耗時（毫秒） |
| `winner_model_id` | string | 最終選定的 model UUID |
| `actual_prompt_tokens` | int | Streaming 完成後修補的實際 prompt token 數 |
| `actual_completion_tokens` | int | Streaming 完成後修補的實際 completion token 數 |
| `created_at` | timestamp | 記錄建立時間 |

**索引**：`(application_id, created_at)`、`(request_id)`、`(winner_model_id)`

**儲存**：預設 SQLite（`/var/lib/xparse/routing.db`）或 PostgreSQL，由 `XPARSE_ROUTING_DB_URL` 控制。

### `selection_reason` 代碼

| 代碼 | 觸發策略 | 說明 |
|------|----------|------|
| `cost_minimum` | `cost_first` | 選出成本最低的計費 model |
| `single_model` | `cost_first`、`energy_first` | 只有一個可用 model |
| `list_order_fallback` | `cost_first` | 無計費資料，以 list 順序為 fallback |
| `no_priced_models_fallback` | `cost_first` | 所有 model 均無計費資料 |
| `viability_guard` | `cost_first` | `cheap_risk_score ≥ cheap_risk_threshold`，改選最便宜非 lightweight model |
| `energy_minimum` | `energy_first` | 選出 `joules_per_output_token` 最低的 model |
| `no_energy_data_fallback` | `energy_first` | 所有 model 均無能耗資料，以 list 順序為 fallback |
| `min_tier_fallback` | `energy_first` | 所有符合 `min_tier` 的 model 均無能耗資料 |

---

## 環境變數

| 變數名稱 | 預設值 | 說明 |
|----------|--------|------|
| `XPARSE_ROUTING_DB_URL` | `sqlite:////var/lib/xparse/routing.db` | xparse_routing 的 SQLAlchemy DB URL，用於路由設定與決策日誌的持久化。 |
| `XPARSE_ROUTING_RESOLVER_ENABLED` | `true` | 路由模組主開關。設為 `false` 時 Gateway 無法服務 chat 請求（路由為必要元件）。 |
| `GATEWAY_IAM_MODE` | `direct` | Gateway 與 IAM 的通訊模式：`http` = 無狀態 HTTP 呼叫；`direct` = 進程內 Django ORM。影響 `AuthContext`（含 model 清單）的取得方式。 |
| `GATEWAY_IAM_URL` | `http://localhost:8010` | `GATEWAY_IAM_MODE=http` 時 IAM 服務的 Base URL。 |
| `XPARSE_HEALTH_TRACKER_ALPHA` | `0.1` | `ModelHealthTracker` EWMA 平滑係數。健康分數注入 `ModelInfo.capabilities` 供 `health_aware` 策略使用。 |

---

## 相關文件

| 類型 | 文件 | 說明 |
|------|------|------|
| ADR | ADR-085 | 路由策略架構決策 |
| ADR | ADR-088 | ExecutionPlan 合約 |
| ADR | ADR-093 | Execution Safety Invariants（`correlation_id` / `request_id` 不可變性） |
| SPEC | SPEC-080 | 路由行為契約與驗收條件 |
| Core-ADR | Core-ADR-01 | Gateway & Streaming 整合導航層 |
