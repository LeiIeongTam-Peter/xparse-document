# bustream — 技術架構報告

> 生成日期：2026-05-30
> 版本依據：`bustream/` 現行 main 分支程式碼

---

## 目錄

1. [是什麼應用](#1-是什麼應用)
2. [資料夾結構總覽](#2-資料夾結構總覽)
3. [各模組功能說明](#3-各模組功能說明)
4. [對外 API 端點完整列表](#4-對外-api-端點完整列表)
5. [服務通訊全貌](#5-服務通訊全貌)
6. [請求主流程](#6-請求主流程)
7. [關鍵類別索引](#7-關鍵類別索引)
8. [重要環境變數](#8-重要環境變數)
9. [關聯文件索引](#9-關聯文件索引)
10. [規模統計](#10-規模統計)

---

## 1. 是什麼應用

| 屬性 | 說明 |
|------|------|
| **類型** | Backend Service（Python FastAPI ASGI） |
| **協議** | HTTP/1.1（REST + SSE）、OpenTelemetry OTLP（出向 Trace） |
| **對外 API 相容性** | OpenAI API v1 相容（Chat Completions、Embeddings、TTS、Transcriptions、Models） |
| **面向對象** | 所有 LLM API 消費端（Console App、外部 SDK Client、Agent App sidecar） |
| **部署方式** | Docker 容器（`python -m bustream.gateway`，預設 port 8000）；可獨立部署，也可與 `xparse_iam` 同容器（`GATEWAY_IAM_MODE=direct`）或分容器（`GATEWAY_IAM_MODE=http`） |
| **角色定位** | **Runtime Orchestrator** — 整個 Xparse 平台的推論請求入口，負責認證、政策決策、准入控制、多後端 LLM streaming 協調、稽核事件發射 |

**一句話記憶錨點**：`bustream/` = 所有 LLM 請求的 Gateway，從 API Key 認證到 SSE token 輸出，全部在這裡完成。

---

## 2. 資料夾結構總覽

```
bustream/
├── __init__.py
│
├── gateway/                          # FastAPI 應用入口（主 routing 層）
│   ├── __main__.py                   # 進入點：python -m bustream.gateway
│   ├── app.py                        # FastAPI app 初始化 + lifespan + 全域元件
│   ├── deps.py                       # GatewayDeps singleton（依賴容器）
│   ├── protocols.py                  # AuthContextProtocol 等 Protocol 定義
│   ├── auth_handler.py               # 認證分發（IAM / legacy auth）
│   ├── iam_http_client.py            # HTTP 模式 IAM 客戶端
│   ├── iam_validate_cache.py         # IAM 驗證 TTL 快取（issue #302）
│   ├── admission_handler.py          # ADR-027 准入控制包裝
│   ├── pre_execution.py              # Policy + cache salt + param 驗證
│   ├── worker_setup.py               # RoutingPlan → Worker 工廠
│   ├── non_streaming_handler.py      # 非串流請求處理
│   ├── fallback_handler.py           # 後端降級 fallback
│   ├── cache_handler.py              # Semantic cache lookup / store
│   ├── endpoint_queue_handler.py     # SPEC-086 Layer 2 端點佇列
│   ├── guardrail_enforcer.py         # SPEC-106 / ADR-139 guardrail 引擎
│   ├── guardrail_handler.py          # guardrail input/output check 包裝
│   ├── guardrail_config.py           # guardrail 政策設定（純函數）
│   ├── guardrail_metrics.py          # guardrail Prometheus 計數器
│   ├── gateway_queue_metrics.py      # SPEC-086 佇列降級計數器
│   ├── fleet_poller.py               # Fleet API 背景輪詢（model profile）
│   ├── routing_adapter.py            # xparse_routing 模組整合橋
│   ├── audit_helpers.py              # Audit context builder 工具函數
│   ├── sse_formatter.py              # SSE 事件格式化
│   ├── responses_chain_validator.py  # PRD-157 Responses API 驗證
│   ├── responses_delete_handler.py   # PRD-157 刪除處理
│   ├── responses_iam_client.py       # PRD-157 IAM 客戶端橋
│   ├── responses_tools_filter.py     # PRD-157 工具過濾
│   └── routes/
│       ├── chat.py                   # POST /v1/chat/completions（主端點）
│       ├── chat_agent.py             # Agent 模式串流分支
│       ├── chat_helpers.py           # routing 模組呼叫 + audit context 建構
│       ├── chat_quality_gate.py      # QualityGate 設定橋
│       ├── chat_streaming_audit.py   # 串流 audit 事件發射
│       ├── embeddings.py             # POST /v1/embeddings（SPEC-039）
│       ├── models.py                 # GET /v1/models（ADR-138）
│       ├── tts.py                    # POST /v1/audio/speech（SPEC-037）
│       ├── transcriptions.py         # POST /v1/audio/transcriptions（SPEC-038）
│       ├── responses.py              # PRD-157 / ADR-192 Responses API
│       └── admin.py                  # 管理端點
│
├── streaming/                        # 核心串流協調引擎
│   ├── manager_v3.py                 # StreamingManagerV3（主協調器）
│   ├── manager_v3_events.py          # EventMixin（SSE 事件發射）
│   ├── manager_v3_workers.py         # WorkerMixin（worker 生命週期）
│   ├── manager.py                    # Legacy manager（向下相容）
│   ├── agent_manager.py              # Agent 模式串流協調
│   ├── agent_streaming.py            # Agent 串流事件處理
│   ├── fusion_engine.py              # Fast/Large/Safety 輸出融合
│   ├── state_machine.py              # StreamState 枚舉
│   ├── sse_event.py                  # SSE 事件 schema
│   ├── non_streaming_collector.py    # 串流轉非串流收集器
│   ├── parsers/                      # SSE 解析器
│   └── workers/
│       ├── base_worker.py            # BaseWorker 抽象類
│       ├── factory.py                # WorkerFactory.create_worker()
│       ├── openai_worker.py          # OpenAI API worker
│       ├── openai_responses_worker.py# PRD-157 Responses API worker
│       ├── azure_openai_worker.py    # Azure OpenAI Service（ADR-057）
│       ├── azure_responses_worker.py # Azure OpenAI Responses worker
│       ├── azure_ai_inference_worker.py # Azure AI Foundry worker
│       ├── vllm_worker.py            # vLLM 自建後端 worker
│       ├── mock_worker.py            # 測試用 mock
│       ├── passthrough_worker.py     # 透傳 worker
│       ├── safety_worker.py          # 安全補丁（PII redaction）
│       ├── embedding_worker.py       # Embedding 生成 worker
│       ├── tts_worker.py             # TTS 生成 worker
│       ├── transcription_worker.py   # 語音轉文字 worker
│       ├── response_formatter.py     # 回應格式化
│       ├── errors.py                 # WorkerError 異常類
│       └── _named_sse_parser.py      # Named SSE chunk 解析
│
├── production/                       # 生產強化元件
│   ├── auth.py                       # AuthManager（legacy auth）
│   ├── rate_limiter.py               # RateLimiter（token bucket）
│   ├── circuit_breaker.py            # CircuitBreaker（CLOSED/OPEN/HALF_OPEN）
│   ├── health_tracker.py             # ModelHealthTracker（EWMA 健康度）
│   ├── retry.py                      # RetryableWorker（自動重試包裝）
│   ├── key_resolver.py               # KeyResolver（BYOK M0/M1/M2 分發）
│   ├── quota_counter.py              # PRD-149 Token quota（Redis shadow）
│   ├── admission/
│   │   ├── controller.py             # AdmissionController（ADR-027 單一准入點）
│   │   └── token_bucket.py           # Token bucket 實作
│   └── queue/
│       ├── interfaces.py             # RequestQueue 抽象介面
│       ├── memory_queue.py           # MemoryQueue 實作
│       ├── factory.py                # create_queue() 工廠
│       └── request_envelope.py       # 佇列信封
│
├── audit/                            # PRD-041 稽核 SDK
│   ├── emit.py                       # AuditEmitter（主介面）
│   ├── schema.py                     # AuditRecord + AuditEventType
│   ├── otel.py                       # OpenTelemetry tracer 初始化
│   ├── config.py                     # 稽核設定
│   └── xparse_bridge.py              # xparse_evidence 橋接
│
├── policy/                           # PRD-033 Policy Kernel
│   ├── kernel.py                     # 純函數 evaluate()
│   ├── models.py                     # PolicyDecision / ApplicationInput / KeyInput
│   ├── errors.py                     # PolicyErrorCode 枚舉
│   ├── request_params.py             # 請求參數政策
│   └── passthrough_policy.py         # 透傳政策（測試用）
│
├── registry/                         # Decision Plane（模型 profile 決策）
│   ├── plan_resolver.py              # PlanResolver（profiles → ExecutionPlan）
│   └── schema.py                     # Profile schema
│
├── agent/                            # Phase 2-A Agent 框架
│   ├── service.py                    # TaskService（任務生命週期）
│   ├── orchestrator.py               # AgentOrchestrator（狀態機）
│   ├── contract.py                   # Agent 契約定義
│   ├── context.py                    # 任務上下文
│   ├── context_gate.py               # 上下文門控
│   ├── enforcer.py                   # 契約強制執行
│   ├── events.py                     # Agent 事件
│   ├── exceptions.py                 # Agent 異常
│   ├── agents/
│   │   ├── planner.py                # PlannerAgent 參考實作
│   │   └── executor.py               # ExecutorAgent 參考實作
│   ├── lite/
│   │   ├── planner_lite.py           # 輕量 planner
│   │   └── executor_lite.py          # 輕量 executor
│   ├── api/
│   │   ├── tasks.py                  # /v2/tasks 端點
│   │   └── schemas.py                # 任務 API schema
│   └── storage/
│       ├── interface.py              # ContextStore 抽象介面
│       ├── sqlite_store.py           # SQLiteContextStore 實作
│       └── _serializers.py           # 序列化工具
│
├── models/                           # OpenAI 相容 schema
│   ├── response_models.py            # ChatCompletionResponse 等
│   ├── embedding_models.py           # EmbeddingRequest
│   ├── multimodal.py                 # PRD-035 多模態 content（Vision API）
│   ├── tts.py                        # TTSRequest
│   ├── transcriptions.py             # TranscriptionRequest
│   └── openai_errors.py              # OpenAI 相容錯誤格式
│
├── observability/                    # 可觀察性
│   ├── logger.py                     # ObservabilityLogger（結構化 JSON log）
│   └── metrics.py                    # MetricsCollector（Prometheus）
│
├── cache_salt/                       # PRD-034 vLLM prefix cache safety
│   ├── generator.py                  # CacheSaltGenerator（HMAC-SHA256）
│   ├── context.py                    # Cache salt 上下文
│   ├── policy.py                     # Cache salt 政策
│   └── tool_detection.py             # Tool-call guard 偵測
│
├── semantic_cache/                   # PRD-048 語意快取
│   ├── manager.py                    # SemanticCacheManager
│   ├── models.py                     # CacheConfig / CacheLookupResult
│   ├── protocols.py                  # 快取協議
│   ├── embedding_adapter.py          # EmbeddingWorkerAdapter
│   └── stores/
│       └── numpy_store.py            # NumpyVectorStore（in-memory）
│
├── quality/                          # TD-004 QualityGate（能源優化）
│   ├── gate.py                       # QualityGate
│   ├── evaluators.py                 # RuleBasedEvaluator
│   ├── protocols.py                  # 評估器協議
│   └── response_validator.py         # 回應品質驗證
│
├── signals/                          # TD-004 Phase 3 使用者驅動取消
│   ├── hub.py                        # SignalHub（session 登記 + handler）
│   ├── models.py                     # Signal 模型
│   └── router.py                     # /v1/signals 端點
│
├── backend/                          # 後端計畫物件
│   ├── plan.py                       # RoutingPlan / ExecutionStep / BackendConfig
│   └── provider.py                   # StaticPlanProvider
│
├── context/
│   └── request_params_context.py     # 請求參數上下文
│
└── utils/
    └── __init__.py                   # 工具函數
```

---

## 3. 各模組功能說明

| 模組 | 主要職責 | 關鍵類別 / 函數 | 關聯文件 |
|------|---------|----------------|---------|
| `gateway/app.py` | FastAPI 應用初始化、lifespan 管理、全域元件裝配 | `app: FastAPI`, `lifespan()` | — |
| `gateway/routes/chat.py` | Chat completions 主端點（串流 + 非串流） | `chat_completions()` | ADR-027, PRD-033, PRD-034, PRD-041, PRD-048, PRD-065 |
| `gateway/routes/embeddings.py` | Embedding 端點 | `embeddings()` | SPEC-039, ADR-089 |
| `gateway/routes/tts.py` | TTS 端點 | `tts()` | SPEC-037 |
| `gateway/routes/transcriptions.py` | 語音轉文字端點 | `transcriptions()` | SPEC-038 |
| `gateway/routes/models.py` | 模型列表端點 | `list_models()` | ADR-138 |
| `gateway/routes/responses.py` | OpenAI Responses API | — | PRD-157, ADR-192 |
| `gateway/auth_handler.py` | 認證分發（IAM / legacy） | `authenticate_request()` | ADR-018, ADR-074 |
| `gateway/iam_http_client.py` | HTTP 模式 IAM 客戶端 | `IAMHttpClient.validate()` | — |
| `gateway/pre_execution.py` | Policy 驗證 + cache salt 決策 + 參數驗證 | `enforce_request_policy()`, `determine_cache_salt()` | PRD-033, PRD-034 |
| `gateway/worker_setup.py` | RoutingPlan → Worker 工廠呼叫 | `create_workers()`, `build_routing_plan()` | ADR-094 |
| `gateway/guardrail_enforcer.py` | NeMo Guardrails sidecar 整合 | `GuardrailEnforcer.check_input()`, `.check_output()` | SPEC-106, ADR-139 |
| `gateway/fleet_poller.py` | Fleet API 背景輪詢，同步 model profiles | `FleetPoller` | — |
| `gateway/deps.py` | 依賴容器（Singleton） | `GatewayDeps` | — |
| `streaming/manager_v3.py` | 多後端 LLM 串流協調 | `StreamingManagerV3` | ADR-056, PRD-064 |
| `streaming/workers/factory.py` | Worker 工廠（依 provider 分發） | `WorkerFactory.create_worker()` | — |
| `streaming/workers/openai_worker.py` | OpenAI API 串流 worker | `OpenAIWorker` | — |
| `streaming/workers/azure_openai_worker.py` | Azure OpenAI 串流 worker | `AzureOpenAIWorker` | ADR-057 |
| `streaming/workers/vllm_worker.py` | vLLM 自建後端 worker | `VLLMWorker` | — |
| `streaming/workers/safety_worker.py` | PII redaction 安全補丁 | `SafetyWorker` | — |
| `production/admission/controller.py` | 單一准入決策點（限流 + 佇列） | `AdmissionController` | ADR-027 |
| `production/key_resolver.py` | BYOK M0/M1/M2 金鑰解析 | `KeyResolver` | ADR-018, ADR-074 |
| `production/circuit_breaker.py` | Worker 熔斷保護 | `CircuitBreaker` | — |
| `production/quota_counter.py` | Redis shadow token quota | `TokenQuotaCounter` | PRD-149 |
| `policy/kernel.py` | 純函數執行合法性決策 | `evaluate()` | PRD-033, ADR-081 |
| `registry/plan_resolver.py` | Profile → ExecutionPlan 決策 | `PlanResolver` | PRD-065, ADR-085, ADR-088 |
| `audit/emit.py` | OTel 稽核事件發射 | `AuditEmitter` | PRD-041 |
| `audit/schema.py` | 稽核記錄 schema | `AuditRecord`, `AuditEventType` | PRD-003 |
| `cache_salt/generator.py` | HMAC-SHA256 cache salt 生成 | `CacheSaltGenerator` | PRD-034 |
| `semantic_cache/manager.py` | 語意相似度快取 | `SemanticCacheManager` | PRD-048 |
| `quality/gate.py` | Fast output 品質評估（能源優化） | `QualityGate` | TD-004 |
| `signals/hub.py` | 使用者取消信號處理 | `SignalHub` | TD-004 Phase 3 |
| `agent/service.py` | Agent 任務生命週期 | `TaskService` | — |
| `observability/logger.py` | 結構化 JSON logging | `ObservabilityLogger` | — |
| `observability/metrics.py` | Prometheus 指標 | `MetricsCollector` | — |

---

## 4. 對外 API 端點完整列表

### 4.1 健康 / 狀態端點

| 方法 | 路徑 | 用途 | 實作檔案 |
|------|------|------|---------|
| `GET` | `/` | 快速健康檢查 + 功能列表 | `gateway/app.py:712` |
| `GET` | `/health` | 詳細健康檢查（circuit breaker 狀態、profiles） | `gateway/app.py:785` |
| `GET` | `/v1/health` | `/health` 別名（v1 路徑） | `gateway/app.py:791` |
| `GET` | `/metrics` | Prometheus metrics（text/plain） | `gateway/app.py:797` |

**`GET /health` Response 範例：**
```json
{
  "status": "healthy",
  "observability": { "logging_enabled": true, "metrics_enabled": true },
  "production": {
    "auth_enabled": false,
    "rate_limit_enabled": true,
    "circuit_breaker_enabled": true,
    "retry_enabled": true
  },
  "circuit_breakers": { "fast_worker": "CLOSED" },
  "routing": { "mode": "registry", "profiles": ["default", "turbo"] },
  "embeddings": { "models": ["text-embedding-ada-002"] }
}
```

---

### 4.2 Chat Completions

| 方法 | 路徑 | 用途 | 實作檔案 |
|------|------|------|---------|
| `POST` | `/v1/chat/completions` | OpenAI 相容 Chat Completions（串流 + 非串流） | `gateway/routes/chat.py:57` |

**Request Headers：**

| Header | 必填 | 說明 |
|--------|------|------|
| `Authorization` | 是（IAM 啟用時） | `Bearer <api_key>` |
| `X-Request-ID` | 否 | 自定義請求 ID（若未提供則自動生成 UUID） |
| `X-Tenant` | 否 | Tenant 代碼（legacy auth fallback 用） |
| `X-BuStream-Debug` | 否 | 開啟 debug 模式 |
| `X-Conversation-Id` | 否 | 用於 per-conversation cache salt（PRD-034） |
| `X-Cache-Salt` | 否 | 客戶端自訂 cache salt 覆蓋 |
| `X-Agent-Task-Id` | 否 | Agent 任務 ID（ADR-055，per-task cache sharing） |
| `traceparent` | 否 | W3C Trace Context（trace_id 提取） |

**Request Body 範例（串流）：**
```json
{
  "model": "gpt-4o",
  "messages": [
    { "role": "system", "content": "You are a helpful assistant." },
    { "role": "user", "content": "Hello!" }
  ],
  "stream": true,
  "temperature": 0.7,
  "max_tokens": 2048,
  "tools": [],
  "tool_choice": "auto"
}
```

**多模態 Request Body 範例（Vision API，PRD-035）：**
```json
{
  "model": "gpt-4o",
  "messages": [{
    "role": "user",
    "content": [
      { "type": "text", "text": "What's in this image?" },
      { "type": "image_url", "image_url": { "url": "https://example.com/image.jpg" } }
    ]
  }],
  "stream": true
}
```

**Response（串流 SSE）：**
```
data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1700000000,"model":"gpt-4o","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}],"xparse":null}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":0,"model":"gpt-4o","choices":[{"index":0,"delta":{},"finish_reason":null}],"xparse":{"routing_mode":"twin","complexity_score":0.3,"quality_gate_triggered":false,"request_id":"uuid","trace_id":"hex","providers":{"fast":"openai","large":"openai"}}}

data: [DONE]
```

**Response Headers（串流）：**
```
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no
X-BuStream-Provider: registry
X-BuStream-Routing-Source: routing_module
X-BuStream-Tenant: tenant_code
X-BuStream-Observability: enabled
X-Request-Id: <uuid>
X-Trace-Id: <hex>
```

**非串流 Response：**
```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1700000000,
  "model": "gpt-4o",
  "choices": [{
    "index": 0,
    "message": { "role": "assistant", "content": "Hello! How can I help?" },
    "finish_reason": "stop"
  }],
  "usage": { "prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30 }
}
```

**錯誤回應（OpenAI 相容）：**
```json
{ "error": { "message": "Unauthorized", "type": "authentication_error", "code": 401 } }
```

| HTTP 狀態碼 | 情境 |
|------------|------|
| 400 | Pydantic 驗證錯誤（ISSUE-002，OpenAI 相容格式） |
| 401 | API Key 無效 |
| 403 | Policy 拒絕（boundary / data egress） |
| 408 | endpoint queue timeout（Layer 2） |
| 422 | model_resolution_error（ADR-094） |
| 429 | 限流 / 准入拒絕 |
| 503 | circuit breaker open / guardrail sidecar 不可達 |

---

### 4.3 Embeddings

| 方法 | 路徑 | 用途 | 實作檔案 |
|------|------|------|---------|
| `POST` | `/v1/embeddings` | OpenAI 相容 Embedding 生成 | `gateway/routes/embeddings.py` |

**Request Body：**
```json
{ "model": "text-embedding-ada-002", "input": "Hello world" }
```

**Response：**
```json
{
  "object": "list",
  "data": [{ "object": "embedding", "embedding": [0.1, -0.2], "index": 0 }],
  "model": "text-embedding-ada-002",
  "usage": { "prompt_tokens": 2, "total_tokens": 2 }
}
```

---

### 4.4 TTS（Text-to-Speech）

| 方法 | 路徑 | 用途 | 實作檔案 |
|------|------|------|---------|
| `POST` | `/v1/audio/speech` | OpenAI 相容 TTS | `gateway/routes/tts.py` |

**Request Body：**
```json
{ "model": "tts-1", "input": "Hello world", "voice": "alloy" }
```

**Response：** `audio/mpeg` binary stream

---

### 4.5 Transcriptions（Speech-to-Text）

| 方法 | 路徑 | 用途 | 實作檔案 |
|------|------|------|---------|
| `POST` | `/v1/audio/transcriptions` | OpenAI 相容 Whisper 轉錄 | `gateway/routes/transcriptions.py` |

**Request：** `multipart/form-data`（`file`, `model`, `language` 等）

**Response：**
```json
{ "text": "Hello world." }
```

---

### 4.6 Models

| 方法 | 路徑 | 用途 | 實作檔案 |
|------|------|------|---------|
| `GET` | `/v1/models` | 列出可用模型 | `gateway/routes/models.py` |

**Response（OpenAI 相容）：**
```json
{
  "object": "list",
  "data": [
    { "id": "gpt-4o", "object": "model", "created": 1700000000, "owned_by": "openai" }
  ]
}
```

---

### 4.7 Responses API（PRD-157 / ADR-192）

| 方法 | 路徑 | 用途 |
|------|------|------|
| `POST` | `/v1/responses` | OpenAI Responses API surface |
| `GET` | `/v1/responses/{id}` | 取得 response 物件 |
| `DELETE` | `/v1/responses/{id}` | 刪除 response 物件 |

---

### 4.8 Signals（TD-004 Phase 3）

| 方法 | 路徑 | 用途 | 實作檔案 |
|------|------|------|---------|
| `POST` | `/v1/signals` | 使用者取消信號（取消 large model） | `signals/router.py` |

**Request Body：**
```json
{ "request_id": "uuid", "signal": "cancel_large", "reason": "user_request" }
```

---

### 4.9 Agent Tasks（Phase 2-B）

| 方法 | 路徑 | 用途 | 實作檔案 |
|------|------|------|---------|
| `POST` | `/v2/tasks` | 建立 Agent 任務 | `agent/api/tasks.py` |
| `GET` | `/v2/tasks/{task_id}` | 取得任務狀態 | `agent/api/tasks.py` |
| `POST` | `/v2/tasks/{task_id}/resume` | 恢復任務執行 | `agent/api/tasks.py` |
| `POST` | `/v2/tasks/{task_id}/cancel` | 取消任務 | `agent/api/tasks.py` |

---

## 5. 服務通訊全貌

### 5.1 ASCII 架構圖

```
                   ┌─────────────────────────────────────────────────────────┐
                   │                   bustream (Gateway)                     │
                   │                      Port 8000                            │
                   │                                                           │
 Client ──HTTP──►  │  ┌──────────┐   ┌──────────┐   ┌──────────────────────┐ │
 (OpenAI SDK /     │  │  auth    │──►│  policy  │──►│  admission           │ │
  Console App /    │  │  handler │   │  kernel  │   │  controller          │ │
  Agent Sidecar)   │  └──────────┘   └──────────┘   └──────────────────────┘ │
                   │       │                               │                  │
                   │       ▼                               ▼                  │
                   │  ┌──────────┐   ┌────────────────────────────────────┐  │
                   │  │  plan    │   │        StreamingManagerV3           │  │
                   │  │ resolver │   │  Fast Worker  Large Worker          │  │
                   │  └──────────┘   │  Safety Worker                      │  │
                   │                 └────────────────────────────────────┘  │
                   └─────────────────────────────────────────────────────────┘
                          │                  │              │
                          │ HTTP POST        │ HTTPS/SSE    │ HTTPS/SSE
                          ▼                  ▼              ▼
               ┌──────────────┐   ┌──────────────┐  ┌──────────────┐
               │  xparse_iam  │   │  OpenAI API  │  │  Azure OAI   │
               │  Port 8010   │   │  (Cloud)     │  │  (Cloud)     │
               └──────────────┘   └──────────────┘  └──────────────┘
                                          │
                          ┌───────────────┼──────────────┐
                          │               │               │
                          ▼               ▼               ▼
               ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
               │  vLLM Server │  │  xparse_     │  │  Fleet API   │
               │  (On-prem)   │  │  resource_   │  │  (xparse_    │
               │  HTTP/SSE    │  │  manager     │  │  fleet)      │
               └──────────────┘  │  Port 8020   │  │  HTTP GET    │
                                 └──────────────┘  └──────────────┘
                          │               │
                          ▼               ▼
               ┌──────────────┐  ┌──────────────┐
               │  NeMo Guards │  │  Tempo/OTLP  │
               │  (Sidecar)   │  │  Collector   │
               │  Port 8400   │  │  OTLP/gRPC   │
               │  HTTP POST   │  │              │
               └──────────────┘  └──────────────┘

               ┌──────────────┐
               │  Redis       │
               │  TCP 6379    │
               │  (quota)     │
               └──────────────┘
```

---

### 5.2 通訊連結總表

| 對象 | 類型 | 協議 | 方向 | 發起點 | 失敗行為 |
|------|------|------|------|--------|---------|
| **xparse_iam** | Backend | HTTP | 出向（每次請求） | `gateway/iam_http_client.py` | Fail-fast（HTTP error → 401/500） |
| **OpenAI API** | LLM Provider | HTTPS/SSE | 出向（推論時） | `streaming/workers/openai_worker.py` | CircuitBreaker → RetryableWorker → 503 |
| **Azure OpenAI** | LLM Provider | HTTPS/SSE | 出向（推論時） | `streaming/workers/azure_openai_worker.py` | CircuitBreaker → RetryableWorker → 503 |
| **vLLM Server** | LLM Provider | HTTP/SSE | 出向（推論時） | `streaming/workers/vllm_worker.py` | CircuitBreaker → RetryableWorker → 503 |
| **xparse_resource_manager** | Backend | HTTP（長輪詢） | 出向（可選） | `gateway/endpoint_queue_handler.py` | Fail-open（直接執行，降級日誌） |
| **Fleet API** | Backend | HTTP GET | 出向（背景輪詢） | `gateway/fleet_poller.py` | 忽略錯誤，保留上次 profiles |
| **NeMo Guardrails Sidecar** | Backend | HTTP POST | 出向（可選） | `gateway/guardrail_enforcer.py` | **Fail-closed**（→ HTTP 503，INV-139-4） |
| **Tempo OTLP Collector** | 觀察性 | OTLP/gRPC | 出向（非同步） | `audit/otel.py` | Fail-open（不影響請求） |
| **Redis** | 狀態存儲 | TCP | 出向（可選） | `production/quota_counter.py` | Fail-open（quota 失敗不阻擋） |
| **xparse_routing DB** | 本地 DB | SQLite | 本地讀寫 | `gateway/app.py:497` | Fail-fast（startup abort） |

---

### 5.3 連線詳細說明

#### 連線 1：Gateway → IAM（認證驗證）

- **Endpoint URL：** `POST {GATEWAY_IAM_URL}/iam/internal/gateway-validate`
  - Env var：`GATEWAY_IAM_URL`（預設：`http://localhost:8010`）
- **模式控制：** `GATEWAY_IAM_MODE`
  - `http`：使用 `IAMHttpClient`（`gateway/iam_http_client.py:257`）
  - `direct`：使用 in-process Django ORM `IAMClient`
- **Request：**
  ```http
  POST /iam/internal/gateway-validate HTTP/1.1
  Content-Type: application/json
  X-Gateway-Secret: <XPARSE_GATEWAY_IAM_SECRET>

  { "api_key": "xai-xxxxxxxxxxxxxxxx" }
  ```
- **Response（成功）：**
  ```json
  {
    "valid": true,
    "tenant_uuid": "uuid",
    "tenant_code": "acme",
    "application_uuid": "uuid",
    "application_code": "my-app",
    "api_key_uuid": "uuid",
    "routing_strategy": "twin",
    "key_type": "M1",
    "execution_boundary": "CLOUD",
    "data_egress": "ALLOWED",
    "rate_limit_policy": {
      "req_per_sec": 10.0,
      "burst": 20,
      "max_concurrency": 5,
      "max_queue_depth": 100,
      "queue_timeout_sec": 30
    },
    "guardrail_policy": {
      "enabled": true,
      "content_filter_level": "medium",
      "pii_redaction_enabled": true,
      "blocked_keywords": "violence,hate",
      "max_input_tokens": 4096,
      "mode": "enforce"
    },
    "models": [{
      "model_uuid": "uuid",
      "provider": "openai",
      "model_name": "gpt-4o",
      "tier": "large",
      "resolved_api_key": "sk-...",
      "timeout": 30.0,
      "max_tokens": 4096
    }]
  }
  ```
- **Timeout：** `GATEWAY_IAM_TIMEOUT`（預設：10 秒）
- **快取：** `IAMValidateCache`（Positive TTL：30s；Negative TTL：60s）
- **失敗行為：** `httpx.HTTPError` → Fail-fast → HTTP 401/500
- **程式碼：** `gateway/iam_http_client.py:257`

---

#### 連線 2：Gateway → LLM Providers（OpenAI / Azure / vLLM）

**OpenAI Worker：**

- **Endpoint URL：** `{endpoint}/v1/chat/completions`（endpoint 來自 model profile；OpenAI 預設 `https://api.openai.com`）
- **Request：**
  ```http
  POST /v1/chat/completions HTTP/1.1
  Authorization: Bearer sk-xxxxxxxx
  Content-Type: application/json

  {
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": true,
    "temperature": 0.7,
    "max_tokens": 2048,
    "tools": [],
    "tool_choice": "auto"
  }
  ```
- **Response（SSE chunk）：**
  ```
  data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"delta":{"content":"Hello"},"index":0}]}
  ```
- **Timeout：** model profile `timeout`（預設 30s）
- **程式碼：** `streaming/workers/openai_worker.py`

**Azure OpenAI Worker（ADR-057）：**

- **Endpoint URL：** `{endpoint}/openai/deployments/{deployment_id}/chat/completions?api-version={api_version}`
- **Request Headers：** `api-key: <azure_key>`
- **程式碼：** `streaming/workers/azure_openai_worker.py`

**vLLM Worker：**

- **Endpoint URL：** `{endpoint}/v1/chat/completions`（vLLM 完全 OpenAI API 相容）
- **額外欄位：** `extra_body: {"cache_salt": "hex32chars"}` — PRD-034 prefix cache safety
- **程式碼：** `streaming/workers/vllm_worker.py`

---

#### 連線 3：Gateway → ResourceManager（端點佇列，SPEC-086 Layer 2）

- **Endpoint URL：** `{RESOURCE_MANAGER_URL}/...`
  - Env var：`RESOURCE_MANAGER_URL`（預設：`http://localhost:8020`）
- **功能：** 跨應用優先佇列（acquire endpoint lease / release）
- **Timeout：** Connect `RESOURCE_MANAGER_CONNECT_TIMEOUT_SEC`（預設 2s）；Read timeout = `RESOURCE_MANAGER_ACQUIRE_TIMEOUT_MS/1000 + 5s`
- **失敗行為：** Fail-open（`XPARSE_ENDPOINT_QUEUE_ENABLED=false` 預設不啟用；啟用後若不可達則降級直接執行，發射 `RESOURCE_QUEUE_DEGRADED` audit event）
- **程式碼：** `gateway/endpoint_queue_handler.py`, `gateway/app.py:618`

---

#### 連線 4：Gateway → NeMo Guardrails Sidecar（SPEC-106）

- **Endpoint URL：** `{XPARSE_GUARDRAIL_SIDECAR_URL}/v1/guardrails/check_input`（或 `check_output`）
  - Env var：`XPARSE_GUARDRAIL_SIDECAR_URL`（預設：`http://xparse-guardrails:8400`）
- **Request（input check）：**
  ```http
  POST /v1/guardrails/check_input HTTP/1.1
  Content-Type: application/json

  {
    "messages": [{"role": "user", "content": "..."}],
    "config_id": "policy_uuid",
    "policy": { "max_input_tokens": 4096, "blocked_keywords": "..." }
  }
  ```
- **Response：**
  ```json
  {
    "action": "pass",
    "violation_type": null,
    "modified_content": null,
    "rail_latency_ms": 12.5,
    "config_id": "policy_uuid"
  }
  ```
- **Timeout：** `XPARSE_GUARDRAIL_TIMEOUT_SEC`（預設 5.0s）
- **失敗行為：** **Fail-closed（INV-139-4）** — sidecar 不可達 → HTTP 503，絕不 silent pass
- **模式：** `XPARSE_GUARDRAIL_MODE`：`enforce`（阻擋）或 `shadow`（觀察）
- **程式碼：** `gateway/guardrail_enforcer.py:57`

---

#### 連線 5：Gateway → Fleet API（背景輪詢）

- **Endpoint URL：** `{FLEET_API_URL}/v1/fleet/model-profiles`
  - Env var：`FLEET_API_URL`（未設定則不啟動）
- **Request：**
  ```http
  GET /v1/fleet/model-profiles HTTP/1.1
  Authorization: Bearer <FLEET_API_TOKEN>
  ```
- **輪詢間隔：** `FLEET_POLL_INTERVAL_SECONDS`（預設 30s）
- **Timeout：** 10s（hardcoded）
- **失敗行為：** 保留上次 profiles，不中斷 gateway
- **程式碼：** `gateway/fleet_poller.py:41`

---

#### 連線 6：Gateway → Tempo / OTLP（稽核事件）

- **Endpoint：** `{OTEL_EXPORTER_OTLP_ENDPOINT}`（gRPC 或 HTTP OTLP）
- **協議：** OpenTelemetry Protocol（OTLP）
- **資料：** OTel Span（每個 `AuditRecord` 轉換為一個 Span）
- **非同步：** 非阻塞 background queue，不影響請求延遲
- **失敗行為：** Fail-open（PRD-041 規範）
- **程式碼：** `audit/otel.py`, `audit/emit.py:501`

**稽核事件類型（`AuditEventType`）：**

| 事件 | 說明 |
|------|------|
| `request_received` | 請求抵達 gateway |
| `admission_decided` | 准入決策完成 |
| `request_queued` / `request_dequeued` | 進出佇列 |
| `execution_started` / `execution_completed` / `execution_failed` | 執行生命週期 |
| `tool_call_detected` | 偵測到 tool call |
| `quality_gate_decided` | QualityGate 決策 |
| `safety_patch_applied` | PII redaction 補丁 |
| `guardrail_input_check` / `guardrail_output_check` / `guardrail_blocked` | Guardrail 事件 |
| `credential_resolved` / `credential_resolution_failed` | 憑證解析 |
| `cache_hit` | 語意快取命中 |
| `resource.queue.degraded` | ResourceManager 降級 |

---

#### 連線 7：Gateway → Redis（Token Quota）

- **Env var：** Redis 連線設定（`TokenQuotaCounter.create_from_env()`）
- **用途：** PRD-149 Token quota shadow 計數（不阻擋請求）
- **失敗行為：** Fail-open（quota 計數失敗不阻擋推論）
- **程式碼：** `production/quota_counter.py`

---

## 6. 請求主流程

```
Client
  │
  │  POST /v1/chat/completions
  │  Authorization: Bearer <api_key>
  ▼
┌────────────────────────────────────────────────────────────────────┐
│  gateway/routes/chat.py:chat_completions()                         │
│                                                                    │
│  ① 產生 request_id (UUID) + completion_id (chatcmpl-xxx)          │
│     chat.py:89-93                                                  │
│                                                                    │
│  ② [認證] authenticate_request()                                   │
│     auth_handler.py → iam_http_client.py:validate()               │
│     → POST /iam/internal/gateway-validate                          │
│     ↓ HttpAuthContext (frozen dataclass)                          │
│                                                                    │
│  ③ [Guardrail Input Check] (可選，XPARSE_GUARDRAIL_ENABLED)        │
│     guardrail_handler.py → guardrail_enforcer.py                  │
│     → POST {sidecar}/v1/guardrails/check_input                    │
│     ↓ GuardrailVerdict.action == "pass" 繼續                      │
│                                                                    │
│  ④ [Semantic Cache Lookup] (可選，XPARSE_SEMANTIC_CACHE_ENABLED)   │
│     cache_handler.py → semantic_cache/manager.py                  │
│     ↓ Cache HIT → 直接返回，跳過推論                              │
│                                                                    │
│  ⑤ [Policy] enforce_request_policy()                              │
│     pre_execution.py → policy/kernel.py:evaluate()                │
│     ↓ PolicyDecision = ALLOW 繼續                                 │
│                                                                    │
│  ⑥ [Routing] _route_via_routing_module()                           │
│     routes/chat_helpers.py                                         │
│     → xparse_routing.Resolver → routing.db                        │
│     ↓ ExecutionPlan (assignments: fast + large models)             │
│                                                                    │
│  ⑦ [Admission Control] run_admission()                             │
│     admission_handler.py → production/admission/controller.py     │
│     ↓ EXECUTE_NOW（或 QUEUED 等待）                                │
│                                                                    │
│  ⑧ [Endpoint Queue] acquire_endpoint_lease() (可選)               │
│     endpoint_queue_handler.py                                      │
│     → POST {resource_manager}/acquire                              │
│                                                                    │
│  ⑨ [Cache Salt] determine_cache_salt()                             │
│     pre_execution.py → cache_salt/generator.py                    │
│     ↓ cache_salt (32-char hex, HMAC-SHA256)                       │
│                                                                    │
│  ⑩ [Worker Setup] build_routing_plan() + create_workers()          │
│     worker_setup.py → streaming/workers/factory.py                │
│     ↓ fast_worker + large_worker + safety_worker                  │
│                                                                    │
│  ⑪ [Quality Gate Setup] _setup_quality_gate() (可選)              │
│     routes/chat_quality_gate.py                                    │
│                                                                    │
│  ⑫ [SignalHub Register] signal_hub.register() (twin mode)          │
│     signals/hub.py                                                 │
│                                                                    │
│  ⑬ [Emit EXECUTION_STARTED] audit/emit.py → Tempo OTLP            │
│                                                                    │
│  ⑭ [StreamingManagerV3] manager.run()                              │
│     streaming/manager_v3.py                                        │
│     ├── fast_worker.stream()                                      │
│     │   → {provider}/v1/chat/completions (SSE)                   │
│     │   ↓ tokens 即時 yield 給 Client                             │
│     ├── large_worker.stream()                                     │
│     │   → {provider}/v1/chat/completions (SSE)                   │
│     │   ↓ 完成後發射 reverse event（取代 fast output）             │
│     └── safety_worker（PII regex patch）                          │
│                                                                    │
│  ⑮ [Guardrail Output Check] (可選)                                │
│     guardrail_enforcer.check_output()                              │
│                                                                    │
│  ⑯ [Quality Gate Callback] (可選)                                  │
│     fast output 評分 → 若足夠好則取消 large_worker                 │
│     savings: ~60% energy                                          │
│                                                                    │
│  ⑰ [Xparse Meta Chunk] 注入 routing metadata SSE chunk             │
│     { "xparse": { "routing_mode": "twin", "complexity_score": ... }}│
│                                                                    │
│  ⑱ data: [DONE]                                                    │
│                                                                    │
│  Finally（regardless of success/failure）：                         │
│  ├── release_concurrency() (admission Layer 1 slot 釋放)          │
│  ├── release_endpoint_lease() (Layer 2 slot 釋放)                 │
│  ├── signal_hub.unregister()                                       │
│  └── emit EXECUTION_COMPLETED / EXECUTION_FAILED audit event      │
└────────────────────────────────────────────────────────────────────┘
  │
  ▼
Client 收到 SSE token stream
```

---

## 7. 關鍵類別索引

| 類別名稱 | 檔案路徑 | 職責 |
|---------|---------|------|
| `StreamingManagerV3` | `streaming/manager_v3.py:18` | 多後端 LLM 串流協調，Fast/Large/Safety worker 並行 |
| `GatewayDeps` | `gateway/deps.py` | Singleton 依賴容器，存放所有全域元件 |
| `IAMHttpClient` | `gateway/iam_http_client.py:193` | HTTP 模式 IAM 認證客戶端 |
| `HttpAuthContext` | `gateway/iam_http_client.py:132` | 不可變認證上下文（frozen dataclass） |
| `AdmissionController` | `production/admission/controller.py` | 單一准入決策點（ADR-027）：限流 + 佇列 |
| `KeyResolver` | `production/key_resolver.py` | BYOK M0/M1/M2 金鑰解析（HMAC/KMS/plaintext） |
| `PlanResolver` | `registry/plan_resolver.py` | Profile → ExecutionPlan 決策引擎 |
| `WorkerFactory` | `streaming/workers/factory.py` | provider → BaseWorker 工廠 |
| `OpenAIWorker` | `streaming/workers/openai_worker.py` | OpenAI / compatible endpoint 串流 worker |
| `AzureOpenAIWorker` | `streaming/workers/azure_openai_worker.py` | Azure OpenAI Service 串流 worker（ADR-057） |
| `VLLMWorker` | `streaming/workers/vllm_worker.py` | vLLM self-hosted 串流 worker |
| `SafetyWorker` | `streaming/workers/safety_worker.py` | PII regex redaction 安全補丁 |
| `CircuitBreaker` | `production/circuit_breaker.py` | 熔斷器（CLOSED/OPEN/HALF_OPEN） |
| `ModelHealthTracker` | `production/health_tracker.py` | EWMA 健康度追蹤，驅動 circuit breaker |
| `RetryableWorker` | `production/retry.py` | 自動重試包裝（裝飾 BaseWorker） |
| `QualityGate` | `quality/gate.py` | Fast output 品質評分，決定是否取消 large worker |
| `SemanticCacheManager` | `semantic_cache/manager.py` | 語意相似度快取（NumpyVectorStore + TTL） |
| `CacheSaltGenerator` | `cache_salt/generator.py` | HMAC-SHA256 cache salt 生成（PRD-034） |
| `GuardrailEnforcer` | `gateway/guardrail_enforcer.py:57` | NeMo sidecar 整合，input/output 內容安全 |
| `AuditEmitter` | `audit/emit.py` | OTel-native 稽核事件發射（非同步 queue） |
| `AuditRecord` | `audit/schema.py:90` | 完整稽核記錄 schema（Pydantic model） |
| `ObservabilityLogger` | `observability/logger.py` | 結構化 JSON logging（TTFT、延遲、決策） |
| `MetricsCollector` | `observability/metrics.py` | Prometheus 指標收集 |
| `FleetPoller` | `gateway/fleet_poller.py:24` | 背景輪詢 Fleet API model profiles |
| `SignalHub` | `signals/hub.py` | 使用者取消信號 session registry |
| `TaskService` | `agent/service.py` | Agent 任務生命週期管理 |
| `FusionEngine` | `streaming/fusion_engine.py` | Fast/Large/Safety 輸出融合邏輯 |
| `TokenQuotaCounter` | `production/quota_counter.py` | Redis shadow token quota（PRD-149） |
| `IAMValidateCache` | `gateway/iam_validate_cache.py` | IAM 驗證 TTL 快取（issue #302） |

---

## 8. 重要環境變數

### 8.1 Gateway 核心設定

| 變數名稱 | 預設值 | 說明 |
|---------|-------|------|
| `GATEWAY_PORT` | `8000` | Gateway 監聽埠 |
| `XPARSE_VERSION` | `dev` | 版本字串 |
| `GATEWAY_IAM_MODE` | `direct` | IAM 通訊模式（`direct`=Django ORM，`http`=HTTP） |
| `GATEWAY_IAM_URL` | `http://localhost:8010` | HTTP 模式 IAM 服務 URL |
| `XPARSE_GATEWAY_IAM_SECRET` | `""` | IAM 內部通訊共享 secret（X-Gateway-Secret header） |
| `GATEWAY_IAM_TIMEOUT` | `10` | IAM HTTP timeout（秒） |

### 8.2 IAM 快取設定

| 變數名稱 | 預設值 | 說明 |
|---------|-------|------|
| `IAM_VALIDATE_CACHE_ENABLED` | `true` | 是否啟用 IAM 驗證快取 |
| `IAM_VALIDATE_CACHE_POSITIVE_TTL_SEC` | `30` | 有效 key 快取秒數 |
| `IAM_VALIDATE_CACHE_NEGATIVE_TTL_SEC` | `60` | 無效 key 快取秒數 |
| `IAM_VALIDATE_CACHE_MAX_ENTRIES` | `10000` | 快取最大筆數 |

### 8.3 可觀察性

| 變數名稱 | 預設值 | 說明 |
|---------|-------|------|
| `BUSTREAM_OBSERVABILITY_ENABLED` | `true` | 是否啟用結構化日誌 |
| `BUSTREAM_METRICS_ENABLED` | `true` | 是否啟用 Prometheus metrics |
| `AUDIT_ENABLED` | `false` | 是否啟用 OTel 稽核事件 |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | OTLP collector URL（Tempo） |
| `OTEL_EXPORTER_OTLP_HEADERS` | — | OTLP 認證 headers |
| `AUDIT_SAMPLE_RATE` | `1.0` | 稽核事件取樣比率（0-1） |

### 8.4 生產強化

| 變數名稱 | 預設值 | 說明 |
|---------|-------|------|
| `BUSTREAM_AUTH_ENABLED` | `false` | Legacy auth 開關 |
| `BUSTREAM_RATE_LIMIT_ENABLED` | `true` | Legacy rate limiter 開關 |
| `BUSTREAM_DEFAULT_RATE_LIMIT` | `60` | Legacy 預設每分鐘請求數 |
| `BUSTREAM_CIRCUIT_BREAKER_ENABLED` | `true` | 熔斷器開關 |
| `BUSTREAM_RETRY_ENABLED` | `true` | 自動重試開關 |
| `XPARSE_HEALTH_TRACKER_ALPHA` | `0.1` | EWMA 健康度 alpha 參數 |

### 8.5 准入控制（ADR-027）

| 變數名稱 | 預設值 | 說明 |
|---------|-------|------|
| `XPARSE_QUEUE_BASED_ADMISSION` | `true` | true=佇列模式；false=拒絕模式 |
| `XPARSE_GLOBAL_MAX_CONCURRENCY` | `0` | 全域最大並發（0=不限） |
| `XPARSE_SERVER_SIDE_QUEUE_WAIT` | `false` | Server 端是否等待佇列完成 |

### 8.6 Routing

| 變數名稱 | 預設值 | 說明 |
|---------|-------|------|
| `XPARSE_ROUTING_RESOLVER_ENABLED` | `true` | 是否啟用 routing 模組 |
| `XPARSE_ROUTING_DB_URL` | `sqlite:////var/lib/xparse/routing.db` | Routing 決策 DB URL |

### 8.7 Cache Salt（PRD-034）

| 變數名稱 | 預設值 | 說明 |
|---------|-------|------|
| `XPARSE_CACHE_SALT_ENABLED` | `true` | 是否啟用 cache salt |
| `XPARSE_CACHE_SALT_SECRET` | — | HMAC-SHA256 secret（必須設定，否則 cache salt 停用） |

### 8.8 QualityGate（TD-004）

| 變數名稱 | 預設值 | 說明 |
|---------|-------|------|
| `XPARSE_QUALITY_GATE_ENABLED` | `true` | 是否啟用 quality gate |
| `XPARSE_QUALITY_THRESHOLD` | `0.7` | Fast output 品質閾值（0-1） |

### 8.9 Guardrail（SPEC-106）

| 變數名稱 | 預設值 | 說明 |
|---------|-------|------|
| `XPARSE_GUARDRAIL_ENABLED` | `false` | 是否啟用 guardrail |
| `XPARSE_GUARDRAIL_SIDECAR_URL` | `http://xparse-guardrails:8400` | NeMo sidecar URL |
| `XPARSE_GUARDRAIL_TIMEOUT_SEC` | `5.0` | Sidecar HTTP timeout |
| `XPARSE_GUARDRAIL_MODE` | `enforce` | `enforce`（阻擋）或 `shadow`（觀察） |

### 8.10 Semantic Cache（PRD-048）

| 變數名稱 | 預設值 | 說明 |
|---------|-------|------|
| `XPARSE_SEMANTIC_CACHE_ENABLED` | `false` | 是否啟用語意快取 |
| `XPARSE_SEMANTIC_CACHE_THRESHOLD` | `0.9` | 相似度閾值 |
| `XPARSE_SEMANTIC_CACHE_TTL_SECONDS` | `3600` | 快取 TTL（秒） |

### 8.11 ResourceManager（SPEC-086）

| 變數名稱 | 預設值 | 說明 |
|---------|-------|------|
| `XPARSE_ENDPOINT_QUEUE_ENABLED` | `false` | 是否啟用 Layer 2 端點佇列 |
| `RESOURCE_MANAGER_URL` | `http://localhost:8020` | ResourceManager 服務 URL |
| `RESOURCE_MANAGER_CONNECT_TIMEOUT_SEC` | `2` | 連線 timeout（秒） |
| `RESOURCE_MANAGER_ACQUIRE_TIMEOUT_MS` | `30000` | Acquire 等待 timeout（毫秒） |
| `RESOURCE_MANAGER_REFRESH_INTERVAL_SEC` | `60` | EndpointResolver 刷新間隔 |

### 8.12 Fleet & Agent

| 變數名稱 | 預設值 | 說明 |
|---------|-------|------|
| `FLEET_API_URL` | — | Fleet API URL（未設定則不啟動 FleetPoller） |
| `FLEET_API_TOKEN` | `demo-token` | Fleet API 認證 token |
| `FLEET_POLL_INTERVAL_SECONDS` | `30` | 輪詢間隔（秒） |
| `XPARSE_AGENT_DATA_PATH` | `/tmp/agent` | Agent SQLite context store 路徑 |

---

## 9. 關聯文件索引

### ADR（架構決策記錄）

| ADR | 標題 | 影響模組 |
|-----|------|---------|
| ADR-018 | Identity & Auth | `production/key_resolver.py`, `gateway/auth_handler.py` |
| ADR-027 | Admission Control | `production/admission/controller.py` |
| ADR-031 | Messages Array Preservation | `streaming/workers/factory.py` |
| ADR-035 | Multi-Modal Content | `models/multimodal.py` |
| ADR-055 | Agent Task Header | `gateway/routes/chat.py` |
| ADR-056 | Reasoning Models（透傳 reasoning_content） | `streaming/manager_v3.py` |
| ADR-057 | Azure OpenAI + Audit Context | `streaming/workers/azure_openai_worker.py` |
| ADR-074 | Key Resolver（BYOK） | `production/key_resolver.py` |
| ADR-081 | Policy Authorization（Rev.2） | `policy/kernel.py` |
| ADR-085 | Routing Strategy | `registry/plan_resolver.py` |
| ADR-088 | Routing Module Primary Path | `gateway/routing_adapter.py` |
| ADR-089 | Embedding Profile Config | `gateway/iam_http_client.py` |
| ADR-092 | Credential Resolution | `production/key_resolver.py` |
| ADR-093 | Execution Safety Invariants（5 條） | 全模組（non-negotiable） |
| ADR-094 | Model Identity Binding | `gateway/worker_setup.py` |
| ADR-102 | Node Runtime Layering | `gateway/fleet_poller.py` |
| ADR-105 | Semaphore Hold Duration（ADR-105） | `gateway/routes/chat.py:664` |
| ADR-110 | Agent App Ingress | `agent/service.py` |
| ADR-127 | Deployment UUID（Phase 3） | `audit/schema.py` |
| ADR-138 | /v1/models Data | `gateway/routes/models.py` |
| ADR-139 | Guardrail（SPEC-106） | `gateway/guardrail_enforcer.py` |
| ADR-192 | Responses API（PRD-157） | `gateway/routes/responses.py` |

### PRD（產品需求文件）

| PRD | 標題 | 影響模組 |
|-----|------|---------|
| PRD-003 | Audit Record Schema | `audit/schema.py` |
| PRD-033 | Policy Kernel | `policy/kernel.py` |
| PRD-034 | Cache Salt（vLLM prefix cache safety） | `cache_salt/generator.py` |
| PRD-035 | Multi-Modal Content（Vision API） | `models/multimodal.py` |
| PRD-041 | Audit SDK Integration（OTel v2） | `audit/emit.py` |
| PRD-048 | Semantic Cache | `semantic_cache/manager.py` |
| PRD-064 | Execution Detail Events | `audit/schema.py` |
| PRD-065 | Routing Strategy（Phase C-1） | `gateway/routing_adapter.py` |
| PRD-149 | Token Quota（Redis shadow） | `production/quota_counter.py` |
| PRD-154 | Response Formatter | `streaming/workers/response_formatter.py` |
| PRD-157 | Responses API | `gateway/routes/responses.py` |

### SPEC（行為規格）

| SPEC | 標題 | 影響模組 |
|------|------|---------|
| SPEC-031 | Stable Completion ID | `streaming/manager_v3.py` |
| SPEC-037 | TTS API | `gateway/routes/tts.py` |
| SPEC-038 | Transcriptions API | `gateway/routes/transcriptions.py` |
| SPEC-039 | Embeddings API | `gateway/routes/embeddings.py` |
| SPEC-064 | Audit Detail Events | `audit/schema.py` |
| SPEC-086 | ResourceManager Layer 2 端點佇列 | `gateway/endpoint_queue_handler.py` |
| SPEC-106 | Guardrail（NeMo sidecar） | `gateway/guardrail_enforcer.py` |

### TD（技術債 / 優化）

| TD | 標題 | 影響模組 |
|----|------|---------|
| TD-004 | Energy-aware Twin Streaming（QualityGate + SignalHub） | `quality/gate.py`, `signals/hub.py` |

---

## 10. 規模統計

### 主要檔案行數（Top 30）

| 檔案 | 行數 |
|------|------|
| `audit/xparse_bridge.py` | 878 |
| `gateway/app.py` | 818 |
| `gateway/routes/responses.py` | 802 |
| `gateway/routes/chat.py` | 743 |
| `agent/orchestrator.py` | 674 |
| `gateway/non_streaming_handler.py` | 665 |
| `agent/storage/sqlite_store.py` | 635 |
| `streaming/manager_v3_events.py` | 605 |
| `production/key_resolver.py` | 560 |
| `agent/service.py` | 547 |
| `observability/metrics.py` | 513 |
| `production/admission/controller.py` | 511 |
| `registry/plan_resolver.py` | 506 |
| `streaming/workers/embedding_worker.py` | 501 |
| `audit/emit.py` | 501 |
| `streaming/workers/azure_openai_worker.py` | 499 |
| `streaming/workers/vllm_worker.py` | 498 |
| `gateway/worker_setup.py` | 496 |
| `streaming/workers/factory.py` | 471 |
| `gateway/iam_http_client.py` | 477 |
| `streaming/non_streaming_collector.py` | 461 |
| `semantic_cache/manager.py` | 461 |
| `audit/otel.py` | 460 |
| `gateway/pre_execution.py` | 434 |
| `streaming/workers/openai_worker.py` | 413 |
| `agent/api/tasks.py` | 408 |
| `agent/context.py` | 402 |
| `agent/events.py` | 401 |
| `streaming/agent_streaming.py` | 393 |
| 其他（~110+ 檔案） | ~15,000 |
| **全模組合計** | **~34,760** |

### 各子系統行數估計

| 子系統 | 估計行數 | 佔比 |
|-------|---------|------|
| `gateway/`（含 routes/） | ~8,500 | 24% |
| `streaming/`（含 workers/） | ~7,000 | 20% |
| `agent/`（含子目錄） | ~5,500 | 16% |
| `audit/` | ~2,300 | 7% |
| `production/`（含子目錄） | ~2,500 | 7% |
| `observability/` | ~600 | 2% |
| `registry/` | ~600 | 2% |
| `semantic_cache/` | ~600 | 2% |
| `policy/` | ~450 | 1% |
| `cache_salt/` | ~400 | 1% |
| `quality/` | ~400 | 1% |
| `models/` | ~500 | 1% |
| 其他（signals, backend, context, utils） | ~5,910 | 17% |
| **合計** | **~34,760** | **100%** |

### 檔案數

| 類型 | 數量 |
|------|------|
| Python 檔案（`.py`） | ~142 |
| 子目錄 | 27 |
| 對外 API 端點 | 13 個（含健康端點） |
| LLM Provider 種類 | 7（openai, azure_openai, azure_ai_inference, vllm, mock, passthrough, openai_responses） |
| 稽核事件類型 | 21 種（`AuditEventType`） |
