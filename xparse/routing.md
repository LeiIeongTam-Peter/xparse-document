# xparse_routing 模組技術報告

> **生成日期**：2026-05-29  
> **模組路徑**：`xparse/xparse_routing/`  
> **整合點**：`bustream/gateway/routing_adapter.py`、`bustream/gateway/routes/chat_helpers.py`

---

## 1. 是什麼應用

| 項目 | 說明 |
|------|------|
| **類型** | Python Library（不對外開放 HTTP port） |
| **協議** | 純函式庫呼叫（In-process function call）；持久層透過 SQLAlchemy（SQLite / PostgreSQL） |
| **面向對象** | Gateway 服務（bustream）—— 為每個聊天請求決定使用哪些 LLM 模型、以何種模式執行 |
| **部署方式** | 與 bustream Gateway 共用同一 Python 程序（non-standalone），以 `import xparse_routing` 的形式被 Gateway 消費；DB 預設位於 `/var/lib/xparse/routing.db`（SQLite），可透過環境變數切換至 PostgreSQL |
| **角色定位** | 「決策核心」——純函式策略計算 + 持久化設定讀取 + 決策日誌寫入；不做 HTTP 呼叫，不做串流，不做 Auth |

---

## 2. 資料夾結構總覽

```
xparse_routing/
├── __init__.py                          # 公開 API 入口，Lazy Import Resolver
│
├── domain/                              # 純業務型別層（禁止 I/O）
│   ├── __init__.py                      # 層說明文件
│   ├── errors.py                        # 型別化例外：RoutingError / RoutingResolutionError / RoutingSystemError
│   ├── protocols.py                     # 凍結 Dataclass：RequestContext / ModelInfo / ModelAssignment / ExecutionPlan / StrategyConfig；RoutingStrategy Protocol
│   └── repositories.py                  # Repository Protocol 介面：ConfigRepositoryProtocol / DecisionLogRepositoryProtocol
│
├── application/                         # 用例編排層（Flow Control + 策略決策）
│   ├── __init__.py                      # 層說明文件
│   ├── registry.py                      # StrategyRegistry：Thread-safe 策略名稱 → 實例查找
│   ├── resolver.py                      # Resolver：主入口；Load Config → Select Strategy → Log Decision
│   └── strategies/
│       ├── __init__.py                  # 匯出 DirectStrategy / TwinStrategy
│       ├── direct.py                    # "none"：永遠使用 models[0]，mode=direct
│       ├── twin.py                      # "smart_routing"：複雜度計算 → direct 或 twin
│       ├── cost_first.py                # "cost_first"：最低估算費用選模，附 viability guard
│       ├── energy_first.py              # "energy_first"：最低焦耳/token 選模，附 circuit breaker
│       └── health_aware.py              # "health_aware"：健康分數優先 twin 路由
│
└── infrastructure/                      # 持久層（SQLAlchemy ORM）
    ├── __init__.py                      # 層說明文件
    ├── database.py                      # init_db()：建立 Engine，自動建表，支援 SQLite / PostgreSQL
    ├── models.py                        # ORM Model：routing_strategy_config / routing_decision_log
    └── repository.py                    # ConfigRepository（含 60s TTL cache）/ DecisionLogRepository
```

---

## 3. 各模組功能說明

| 模組 | 檔案 | 職責 | 關聯文件 |
|------|------|------|----------|
| **Public API** | `__init__.py` | Lazy import + 公開型別匯出，避免 SQLAlchemy 在 import 時初始化 | SPEC-080 §6 |
| **RoutingError** | `domain/errors.py` | 型別化例外體系：Base / 4xx(ResolutionError) / 5xx(SystemError) | SPEC-080 §7 |
| **RequestContext** | `domain/protocols.py` | 凍結請求快照（token 估算、message 數、tool 定義、stream flag） | SPEC-080 §3 |
| **ModelInfo** | `domain/protocols.py` | 凍結模型描述（model_id, provider, tier, capabilities dict） | SPEC-080 §4, PRD-139 |
| **ExecutionPlan** | `domain/protocols.py` | 路由決策輸出（mode: direct/twin, assignments list） | SPEC-080 §4 |
| **StrategyConfig** | `domain/protocols.py` | 每 Application 的策略設定（strategy_name, role_assignments, parameters） | SPEC-080 §8 |
| **RoutingStrategy** | `domain/protocols.py` | Protocol 介面（runtime_checkable），所有策略必須實作 `name` + `resolve()` | SPEC-080 §5 |
| **ConfigRepository Protocol** | `domain/repositories.py` | 抽象化設定存取（get/save/invalidate/delete） | SPEC-080 §8 |
| **DecisionLog Protocol** | `domain/repositories.py` | 抽象化決策日誌寫入（write/update_actuals/list_by_application） | PRD-065, INV-121b-2 |
| **StrategyRegistry** | `application/registry.py` | Thread-safe 策略名稱 → 實例 map，Register/Lookup/List | — |
| **Resolver** | `application/resolver.py` | 主編排器：Load Config → Get Strategy → Call resolve() → Log Decision | SPEC-080 §6, PRD-065 Phase C-1 |
| **DirectStrategy** | `application/strategies/direct.py` | "none"：忽略設定，取 models[0]，回傳 mode=direct | SPEC-080 §5.1, Rules D-1~D-4 |
| **TwinStrategy** | `application/strategies/twin.py` | "smart_routing"：計算複雜度分數（0.0-1.0），閾值判斷 direct vs twin | SPEC-080 §5.2-5.3 |
| **CostFirstStrategy** | `application/strategies/cost_first.py` | "cost_first"：估算費用 = input_token_price × tokens + output_token_price × output；附 cheap_risk viability guard | PRD-139 §2 §3.3, ADR-166 |
| **EnergyFirstStrategy** | `application/strategies/energy_first.py` | "energy_first"：選最低 joules_per_output_token 模型；附 circuit breaker 過濾與 min_tier 地板 | PRD-139 §3.x, ADR-166 |
| **HealthAwareTwinStrategy** | `application/strategies/health_aware.py` | "health_aware"：延伸 TwinStrategy，依 health_score 過濾不健康模型 | SPEC-080 §5.4 |
| **database.py** | `infrastructure/database.py` | `init_db(url)`：建立 Engine + 自動建表；支援 SQLite file auto-mkdir | SPEC-082 §3 |
| **ORM Models** | `infrastructure/models.py` | `routing_strategy_config`（upsert 設定）、`routing_decision_log`（追加式日誌） | SPEC-080 §8 |
| **ConfigRepository** | `infrastructure/repository.py` | 實作 ConfigRepositoryProtocol + 60s in-memory TTL cache；upsert 寫入 | — |
| **DecisionLogRepository** | `infrastructure/repository.py` | 實作 DecisionLogRepositoryProtocol；追加 + update_actuals（token 實際用量補填） | INV-121b-2 |

---

## 4. 對外 API 端點完整列表

> `xparse_routing` **不是 HTTP 服務**，沒有 REST endpoint。  
> 其公開 API 為 Python 函式呼叫界面，由 Gateway 在進程內直接呼叫。

### 4.1 Public Python API（`xparse_routing` 公開介面）

| 呼叫方式 | 簽名 | 用途 | 回傳值 |
|----------|------|------|--------|
| `Resolver.__init__` | `(config_repo, decision_repo=None, registry=None, degraded_allowed=False)` | 建構主解析器，注入 Repository 依賴 | `Resolver` 實例 |
| `Resolver.resolve` | `(application_id: str, context: RequestContext, models: list[ModelInfo]) -> ExecutionPlan` | **核心決策入口**：讀取策略設定 → 計算執行計劃 → 非同步寫日誌 | `ExecutionPlan` |
| `Resolver.record_actuals` | `(request_id: str, actual_prompt_tokens: int \| None, actual_completion_tokens: int \| None) -> None` | 串流結束後補填實際 token 用量至決策日誌 | `None` |
| `get_routing_metrics` | `() -> dict` | 回傳即時計數器快照（writes / failures / resolutions） | `dict` |

### 4.2 Admin REST Endpoint（由 bustream Gateway 代理）

| 方法 | 路徑 | 用途 |
|------|------|------|
| `GET` | `/admin/routing/strategies` | 列出所有已註冊策略名稱 |
| `GET` | `/admin/routing/metrics` | 回傳 `get_routing_metrics()` 快照 |
| `GET` | `/admin/routing/config/{application_id}` | 讀取 Application 的策略設定 |
| `PUT` | `/admin/routing/config/{application_id}` | 寫入 / 更新 Application 的策略設定 |
| `DELETE` | `/admin/routing/config/{application_id}` | 刪除 Application 的策略設定 |
| `GET` | `/admin/routing/decisions/{application_id}` | 查詢最近 N 筆決策日誌（預設 100） |

> **來源**：`bustream/gateway/routes/admin.py`；所有端點需要 Admin 權限。

---

## 5. 服務通訊全貌

### 5.1 ASCII 架構圖

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        bustream Gateway Process                         │
│                                                                         │
│  HTTP ←→ Client                                                         │
│     │                                                                   │
│     ▼                                                                   │
│  chat_helpers.py                                                        │
│  _route_via_routing_module()   ────[in-process call]──────────────────┐ │
│     │                                                                  │ │
│     │  routing_adapter.py                                              │ │
│     │  ┌──────────────────────────────────────────────────────────┐   │ │
│     │  │ models_from_auth_context(auth_context, health_tracker)   │   │ │
│     │  │   └─ ModelInfo[] (含 health_score, cost, joules 欄位)     │   │ │
│     │  │ build_request_context(request_id, messages, ...)         │   │ │
│     │  │   └─ RequestContext (token estimate, complexity signals) │   │ │
│     │  │ execution_plan_to_routing_mode(plan)                     │   │ │
│     │  │   └─ "fast_only" | "fast_then_large"                    │   │ │
│     │  └──────────────────────────────────────────────────────────┘   │ │
│     │                                                                  │ │
│     └──────────────[in-process]──────────────────────────────────────►│ │
│                                                                        │ │
│  ┌─────────────────── xparse_routing (Library) ───────────────────────┘ │
│  │                                                                       │
│  │  Resolver.resolve(application_id, context, models)                    │
│  │     │                                                                 │
│  │     ├─[1] ConfigRepository.get(application_id)                       │
│  │     │      ├─ Cache hit (TTL 60s): 直接回傳 StrategyConfig            │
│  │     │      └─ Cache miss: SQLAlchemy SELECT ──────────────────────┐  │
│  │     │                                                             │  │
│  │     ├─[2] StrategyRegistry.get(strategy_name)                    │  │
│  │     │      └─ DirectStrategy / TwinStrategy / CostFirst / ...    │  │
│  │     │                                                             │  │
│  │     ├─[3] strategy.resolve(context, models, config)              │  │
│  │     │      └─ ExecutionPlan (pure function, no I/O)              │  │
│  │     │                                                             │  │
│  │     └─[4] _write_decision_log() ──[fire-and-forget]─────────────►│  │
│  │                    DecisionLogRepository.write() ─────────────►  │  │
│  │                                                SQLAlchemy INSERT  │  │
│  │                                                         │         │  │
│  └─────────────────────────────────────────────────────────┼─────────┘  │
│                                                            │            │
│                                          ┌─────────────────▼──────────┐ │
│                                          │   SQLite / PostgreSQL DB    │ │
│                                          │  routing_strategy_config   │ │
│                                          │  routing_decision_log      │ │
│                                          └────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘

  [外部] IAM (xparse_iam) ──[HTTP]──► Gateway auth_context.models
         含 ModelInfo 欄位：model_uuid / provider / tier / cost / joules
```

### 5.2 通訊連結總表

| 對象 | 類型 | 協議 | 方向 | 發起點檔案 | 失敗行為 |
|------|------|------|------|------------|----------|
| `chat_helpers.py` → `Resolver.resolve()` | Backend（in-process） | Python function call | Gateway → xparse_routing | `bustream/gateway/routes/chat_helpers.py:71` | RoutingResolutionError → HTTP 400；RoutingSystemError → HTTP 500 |
| `Resolver` → `ConfigRepository.get()` | Backend（in-process） | SQLAlchemy ORM | Resolver → SQLite/PG | `xparse_routing/application/resolver.py:130` | RoutingSystemError 上拋（strict mode）；fallback DirectStrategy（degraded mode） |
| `Resolver` → `DecisionLogRepository.write()` | Backend（in-process） | SQLAlchemy ORM | Resolver → SQLite/PG | `xparse_routing/application/resolver.py:218` | Fire-and-forget：失敗記 metrics，不影響 resolve 回傳值 |
| `Resolver.record_actuals()` → `DecisionLogRepository.update_actuals()` | Backend（in-process） | SQLAlchemy ORM | Gateway → SQLite/PG | `xparse_routing/application/resolver.py:193` | Fire-and-forget：失敗靜默（No-op if repo is None） |
| IAM → Gateway `auth_context.models` | Backend（HTTP） | REST / JSON | IAM → Gateway（驗證階段） | `bustream/gateway/routing_adapter.py:110` | IAM 驗證失敗 → Gateway 回 401；models 為空 → HTTP 400 |
| Admin endpoints → `ConfigRepository.save/delete` | Backend（in-process） | Python function call（透過 FastAPI handler） | Gateway Admin routes → xparse_routing | `bustream/gateway/routes/admin.py` | 寫入失敗 → HTTP 500 |

### 5.3 連線詳細說明

#### 連線 A：Gateway → Resolver.resolve()（主要決策呼叫）

```
發起點：bustream/gateway/routes/chat_helpers.py:71
函式：plan = resolver.resolve(str(application_id), request_ctx, models)

輸入（RequestContext）：
{
  "request_id": "req-uuid-xxxx",
  "prompt_token_estimate": 342,         # 4 chars/token 估算
  "message_count": 5,
  "has_system_prompt": true,
  "has_tool_definitions": false,
  "stream": true,
  "metadata": { "code_blocks": 2 }
}

輸入（ModelInfo[]，來自 IAM auth_context.models）：
[
  {
    "model_id": "model-uuid-A",
    "provider": "openai",
    "model_name": "gpt-4o-mini",
    "tier": "lightweight",
    "capabilities": {
      "health_score": 0.95,
      "circuit_breaker_open": false,
      "avg_latency_ms": 320,
      "cost_per_input_token": 0.00000015,
      "cost_per_output_token": 0.0000006,
      "joules_per_output_token": 0.0004
    }
  },
  {
    "model_id": "model-uuid-B",
    "provider": "azure",
    "model_name": "gpt-4o",
    "tier": "premium",
    "capabilities": {
      "health_score": 0.88,
      "circuit_breaker_open": false,
      "avg_latency_ms": 780,
      "cost_per_input_token": 0.0000025,
      "cost_per_output_token": 0.00001,
      "joules_per_output_token": 0.0018
    }
  }
]

輸出（ExecutionPlan，twin 模式範例）：
{
  "mode": "twin",
  "assignments": [
    { "role": "fast",  "model_id": "model-uuid-A", "model_name": "gpt-4o-mini", "provider": "openai" },
    { "role": "large", "model_id": "model-uuid-B", "model_name": "gpt-4o",      "provider": "azure" }
  ],
  "metadata": {
    "strategy_name": "smart_routing",
    "complexity_score": 0.74,
    "complexity_threshold": 0.7,
    "reasoning": "complex request: complexity 0.74 >= threshold 0.70",
    "confidence": 0.9
  }
}

失敗行為：
  RoutingResolutionError → HTTP 400（設定缺失、未知策略、驗證失敗）
  RoutingSystemError     → HTTP 500（DB 連線失敗、runtime 錯誤）
  degraded_allowed=True  → fallback DirectStrategy（回傳 mode=direct models[0]）
```

#### 連線 B：Resolver → ConfigRepository（設定讀取）

```
發起點：xparse_routing/application/resolver.py:130
DB Table：routing_strategy_config

SELECT 範例：
  SELECT * FROM routing_strategy_config WHERE application_id = 'app-uuid-xxx'

回傳（StrategyConfig）：
{
  "strategy_name": "smart_routing",
  "role_assignments": { "fast": "model-uuid-A", "large": "model-uuid-B" },
  "parameters": { "complexity_threshold": 0.75 }
}

Cache：in-memory dict，TTL 預設 60s（由 _RoutingConfigRepo(..., cache_ttl_seconds=60) 設定）
Timeout：無顯式 timeout，由 SQLAlchemy engine 層級 connection pool 控制
失敗行為：例外上拋 → Resolver 包裝成 RoutingSystemError
```

#### 連線 C：Resolver → DecisionLogRepository.write()（決策日誌）

```
發起點：xparse_routing/application/resolver.py:218
DB Table：routing_decision_log
模式：Fire-and-forget（失敗不影響 resolve 回傳）

INSERT 欄位範例：
  id                = uuid4()
  application_id    = "app-uuid-xxx"
  request_id        = "req-uuid-xxxx"
  strategy_name     = "smart_routing"
  input_summary     = '{"prompt_tokens": 342, "message_count": 5, ...}'  # JSON
  execution_plan    = '{"mode": "twin", "assignments": [...]}'             # JSON
  reasoning         = "complex request: complexity 0.74 >= threshold 0.70"
  selection_reason  = "complexity_twin"  # 預定義代碼（INV-121b-2）
  duration_ms       = 3
  winner_model_id   = null              # 由後續 record_actuals 補填
  created_at        = "2026-05-29T10:00:00.000Z"

失敗行為：例外被 try/except 吃掉，metrics.decision_log_failures_total++
```

#### 連線 D：Gateway → record_actuals()（串流後補填）

```
發起點：bustream/gateway（串流完成後）
函式：resolver.record_actuals(request_id, actual_prompt_tokens, actual_completion_tokens)

UPDATE：
  UPDATE routing_decision_log
  SET actual_prompt_tokens = 358, actual_completion_tokens = 125
  WHERE request_id = 'req-uuid-xxxx'

失敗行為：No-op（decision_repo is None 時直接跳過）；例外靜默記錄
```

---

## 6. 請求主流程

```
Client HTTP Request (POST /v1/chat/completions)
         │
         ▼
┌─────────────────────────────┐
│ bustream/gateway/app.py     │  Gateway startup 已初始化：
│ (FastAPI lifespan)          │  routing_resolver = Resolver(config_repo, decision_repo)
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ bustream/gateway/routes/chat_helpers.py                             │
│ _route_via_routing_module()                                         │
│                                                                     │
│  Step 1: models_from_auth_context(auth_context, health_tracker)    │
│           └─ routing_adapter.py:110                                 │
│           └─ IAM 驗證時注入的 auth_context.models 轉成 ModelInfo[]   │
│                                                                     │
│  Step 2: build_request_context(request_id, messages, ...)          │
│           └─ routing_adapter.py:87                                  │
│           └─ 4 chars/token 估算、code block 計數、role 偵測         │
│                                                                     │
│  Step 3: resolver.resolve(application_id, request_ctx, models)     │
│           └─ chat_helpers.py:71                                     │
│                                                                     │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ xparse_routing/application/resolver.py                              │
│ Resolver.resolve()                                                  │
│                                                                     │
│  [A] config_repo.get(application_id)                               │
│       └─ Cache hit → StrategyConfig (skip DB)                       │
│       └─ Cache miss → SELECT routing_strategy_config WHERE app_id  │
│       └─ No row found → RoutingResolutionError("no config")         │
│                                                                     │
│  [B] registry.get(strategy_name)                                    │
│       └─ Returns strategy instance (e.g. TwinStrategy)             │
│       └─ Unknown name → RoutingResolutionError("unknown strategy")  │
│                                                                     │
│  [C] strategy.resolve(context, models, config)                      │
│       └─ Pure function, NO I/O                                      │
│       └─ Returns ExecutionPlan (mode + assignments)                 │
│                                                                     │
│  [D] _write_decision_log() [fire-and-forget]                       │
│       └─ INSERT routing_decision_log                                │
│       └─ Failure → metrics++, NOT propagated                       │
│                                                                     │
│  → return ExecutionPlan                                             │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ routing_adapter.py                                                  │
│ execution_plan_to_routing_mode(plan)                                │
│   "direct" → "fast_only"                                            │
│   "twin"   → "fast_then_large"                                      │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ bustream/gateway/streaming/StreamingManager                         │
│ routing_mode = "fast_only" | "fast_then_large"                      │
│ → 依此決定啟動 1 個或 2 個 LLM Worker                                │
└─────────────────────────────────────────────────────────────────────┘
                           │
         ─ 串流結束後 ─────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ resolver.record_actuals(request_id, actual_prompt, actual_complete) │
│   → UPDATE routing_decision_log SET actual_* WHERE request_id       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 7. 關鍵類別索引

| 類別名稱 | 檔案路徑 | 職責摘要 |
|----------|----------|----------|
| `Resolver` | `application/resolver.py:87` | 主編排器：Config 讀取 → 策略選取 → ExecutionPlan 輸出 → 日誌寫入 |
| `StrategyRegistry` | `application/registry.py:16` | Thread-safe 策略名稱 → 實例映射；支援執行期動態 register |
| `DirectStrategy` | `application/strategies/direct.py:17` | 名稱 "none"；永遠 mode=direct，使用 models[0]；忽略所有 config |
| `TwinStrategy` | `application/strategies/twin.py:82` | 名稱 "smart_routing"；複雜度分數 → 閾值判斷 direct vs twin |
| `CostFirstStrategy` | `application/strategies/cost_first.py:112` | 名稱 "cost_first"；費用最小化；附 cheap_risk viability guard |
| `EnergyFirstStrategy` | `application/strategies/energy_first.py:63` | 名稱 "energy_first"；最低 joules/output_token；circuit breaker + min_tier 過濾 |
| `HealthAwareTwinStrategy` | `application/strategies/health_aware.py:97` | 名稱 "health_aware"；健康分數加權的 TwinStrategy 擴充版 |
| `ConfigRepository` | `infrastructure/repository.py:21` | StrategyConfig 讀寫；含 in-memory TTL 60s cache；upsert 語意 |
| `DecisionLogRepository` | `infrastructure/repository.py:112` | 決策日誌追加寫入；record_actuals 補填 token 實際值 |
| `RequestContext` | `domain/protocols.py:16` | 凍結請求快照（frozen dataclass）；策略計算的唯一輸入 |
| `ModelInfo` | `domain/protocols.py:33` | 凍結模型描述；含 capabilities dict（health / cost / energy） |
| `ExecutionPlan` | `domain/protocols.py:62` | 凍結路由決策輸出；mode + assignments + metadata |
| `StrategyConfig` | `domain/protocols.py:80` | 凍結 per-application 策略設定；由 DB 載入 |
| `RoutingResolutionError` | `domain/errors.py:22` | 預期失敗（4xx）：設定缺失、未知策略、資料驗證失敗 |
| `RoutingSystemError` | `domain/errors.py:34` | 意外失敗（5xx）：DB 連線、runtime 錯誤 |
| `_Metrics` | `application/resolver.py:55` | 計數器快照：writes / log_failures / resolution_failures / system_failures |

---

## 8. 重要環境變數

| 變數名稱 | 預設值 | 說明 |
|----------|--------|------|
| `XPARSE_ROUTING_DB_URL` | `sqlite:////var/lib/xparse/routing.db` | SQLAlchemy DB URL；支援 SQLite（預設）或 PostgreSQL（`postgresql+psycopg2://...`） |
| `XPARSE_ROUTING_RESOLVER_ENABLED` | `"true"` | Gateway 啟動時是否初始化 Routing Module；設 "false" 可完全停用 |

### 8.1 Per-Application 策略參數（透過 `StrategyConfig.parameters` 傳入，非環境變數）

| 參數鍵名 | 策略 | 預設值 | 說明 |
|----------|------|--------|------|
| `complexity_threshold` | smart_routing / health_aware | `0.7` | 複雜度分數超過此閾值使用 twin 模式（0.0-1.0） |
| `output_length_category` | cost_first | `"short"` | 估算輸出長度：`"short"`=200 tokens、`"medium"`=600、`"long"`=1500 |
| `cheap_risk_threshold` | cost_first | `0.3` | 低於此分數可選最便宜模型；高於則 viability guard 排除 lightweight |
| `min_tier` | energy_first | `None` | 能源最優策略的 tier 地板（`"lightweight"` / `"standard"` / `"premium"`） |
| `min_health_threshold` | health_aware | `0.3` | 健康分數低於此值的模型被過濾（0.0-1.0） |

### 8.2 ConfigRepository 建構參數

| 參數 | 預設值 | 說明 |
|------|--------|------|
| `cache_ttl_seconds` | `60.0` | StrategyConfig in-memory cache 存活秒數（Gateway 啟動時設定） |

---

## 9. 關聯文件索引

### ADR（架構決策記錄）

| 文件 | 狀態 | 關聯模組 | 說明 |
|------|------|----------|------|
| ADR-088 | Active | `resolver.py`, `routing_adapter.py` | Routing 模組主架構決策：AuthContext.models 作為 PRIMARY model source（Phase C-1） |
| ADR-166 | Active | `cost_first.py`, `energy_first.py` | cost_first / energy_first 策略引入決策；pricing + energy metadata 規範 |

### PRD（產品需求文件）

| 文件 | 關聯模組 | 說明 |
|------|----------|------|
| PRD-065 Phase C-1 | `resolver.py`, `chat_helpers.py` | Routing Resolver 整合到 Gateway 的 Phase C-1 工作項目；決策日誌、shadow mode |
| PRD-139 §2, §3 | `cost_first.py`, `energy_first.py` | cost_first（§2：費用最小化）、energy_first（§3：能源最小化）策略需求定義 |

### SPEC（行為規格）

| 文件 | 關聯模組 | 說明 |
|------|----------|------|
| SPEC-080 §3-4 | `domain/protocols.py` | RequestContext / ModelInfo / ExecutionPlan / StrategyConfig 型別契約 |
| SPEC-080 §5.1 | `direct.py` | DirectStrategy 規則 D-1~D-4（mode=direct, assignments=[1 entry]） |
| SPEC-080 §5.2-5.3 | `twin.py` | TwinStrategy 複雜度計算公式（5 個 factor 權重） |
| SPEC-080 §6 | `resolver.py` | Resolver 編排流程與 degraded mode 行為規範 |
| SPEC-080 §7 | `domain/errors.py` | 錯誤型別映射（4xx / 5xx） |
| SPEC-080 §8 | `infrastructure/models.py`, `repository.py` | DB schema 契約（routing_strategy_config / routing_decision_log） |
| SPEC-080 §9 | `routing_adapter.py` | Gateway Integration Contract（RequestContext 建構規則） |
| SPEC-080 §11 | `routing_adapter.py:42` | Mode Mapping：`direct`→`fast_only`，`twin`→`fast_then_large` |
| SPEC-082 §3 | `infrastructure/database.py` | DB 初始化規格（auto mkdir for SQLite, create_all） |
| INV-121b-2 | `infrastructure/models.py:43`, `resolver.py` | `selection_reason` 欄位只允許預定義代碼（不允許自由文字） |

---

## 10. 規模統計

| 模組 | 檔案 | 程式碼行數 |
|------|------|-----------|
| **Public API** | `__init__.py` | 44 |
| **Domain** | `domain/errors.py` | 43 |
| **Domain** | `domain/protocols.py` | 109 |
| **Domain** | `domain/repositories.py` | 64 |
| **Application** | `application/registry.py` | 42 |
| **Application** | `application/resolver.py` | 273 |
| **Strategies** | `strategies/direct.py` | 57 |
| **Strategies** | `strategies/twin.py` | 183 |
| **Strategies** | `strategies/cost_first.py` | 204 |
| **Strategies** | `strategies/energy_first.py` | 161 |
| **Strategies** | `strategies/health_aware.py` | 232 |
| **Infrastructure** | `infrastructure/database.py` | 45 |
| **Infrastructure** | `infrastructure/models.py` | 56 |
| **Infrastructure** | `infrastructure/repository.py` | 206 |
| **Layer `__init__`** | 4 個 `__init__.py` | ~26（合計） |
| **合計（模組本身）** | 18 個 .py 檔 | **1,745 行** |
| **整合橋接** | `bustream/gateway/routing_adapter.py` | 165 |
| **整合橋接** | `bustream/gateway/routes/chat_helpers.py`（路由相關部分） | ~95 |
| **測試** | 18 個測試檔案（unit / contract / integration） | 約 2,500+ 行（估算） |

### 10.1 各層佔比

| 層 | 行數 | 佔比 |
|----|------|------|
| Domain（純型別） | 216 | 12% |
| Application / Strategies | 895 | 51% |
| Infrastructure | 307 | 18% |
| 其他（入口、layer docs） | 70 | 4% |
| 整合橋接（bustream 側） | 260 | 15% |
| **合計** | **1,748** | **100%** |
