# Xparse — 後端服務結構說明

每個服務的職責、技術棧、目錄結構與關鍵設計決策。

> **API 完整清單**：各服務的所有 endpoint、path、說明請見 [`docs/api.md`](./api.md)。本文件聚焦架構與設計，不重複列 API 表格。

---

## 服務總表

| 服務 | 職責 | 框架 | Port | Python 檔數 |
|------|------|------|------|------------|
| `bustream/` | Gateway & 串流引擎 | FastAPI | 8000 | ~147 |
| `xparse_iam/` | IAM & Governance | Django Ninja | 8010 | ~335 |
| `3rd/xparse_audit/` | Audit SDK & API | FastAPI | 8030 | ~152 |
| `xparse_fleet/` | Fleet API & Node 管理 | FastAPI | 8090 | ~89 |
| `xparse_node_mgr/` | Node Runtime Agent (agentd) | gRPC daemon | — | ~58 |
| `xparse_container_platform/` | Container 生命週期（Library） | DDD pure lib | — | ~50 |
| `xparse_resource_manager/` | Endpoint 容量守衛 | FastAPI | 8020 | ~24 |
| `xparse_routing/` | 路由策略（Library） | Pure lib | — | ~18 |
| `xparse_scheduler/` | GPU Placement 排程 | FastAPI | — | ~25 |
| `xparse_warden/` | 系統健康監控 | CLI / Checker | — | ~11 |

---

## 1. `bustream/` — Gateway & 串流引擎

**職責**：系統的 runtime 核心。接收所有 AI 推論請求，執行治理檢查，驅動 inference worker，以 SSE 串流回傳結果。所有流量都必須經過這一層。

**技術棧**：FastAPI + asyncio

**目錄結構**：

```
bustream/
├── gateway/               # FastAPI app 入口
│   ├── app.py             # 建立 FastAPI 實例，掛載所有 middleware
│   ├── __main__.py        # 啟動點（uvicorn）
│   ├── routes/            # API endpoint handlers（/v1/chat, /v1/models…）
│   ├── auth_handler.py    # 向 IAM 驗證 API key
│   ├── admission_handler.py   # Rate limit + Circuit breaker
│   ├── guardrail_handler.py   # Content policy 過濾
│   ├── cache_handler.py       # Semantic cache 查詢
│   └── endpoint_queue_handler.py  # 向 ResourceManager 申請 lease
│
├── streaming/             # SSE 串流引擎
│   ├── manager_v3.py      # 主 orchestrator（控制狀態機）
│   ├── workers/           # Provider worker（OpenAI / Azure / vLLM / NemoClaw）
│   ├── parsers/           # Response parser（把 provider 格式轉標準格式）
│   └── fusion_engine.py   # Multi-worker 結果合併
│
├── production/            # 生產保護層
│   ├── auth.py            # API key 解析
│   ├── rate_limiter.py    # Token bucket / sliding window
│   ├── circuit_breaker.py # Provider 熔斷器
│   ├── admission/         # Admission control logic
│   └── quota_counter.py   # Token 用量計數
│
├── policy/                # Policy Kernel（純函數）
│   ├── kernel.py          # 決策函數：給定 context → 回傳 decision（不打任何 I/O）
│   └── request_params.py  # Policy 相關的 request 參數模型
│
├── audit/                 # Audit 發射點
│   ├── emit.py            # 非同步發送 audit event
│   ├── schema.py          # Audit event schema
│   └── xparse_bridge.py   # 連接 xparse_audit SDK
│
├── agent/                 # Agent 編排
│   ├── service.py         # Agent 服務入口
│   ├── orchestrator.py    # Multi-step agent workflow
│   ├── agents/            # Executor / Planner 實作
│   └── enforcement/       # Context gating
│
├── semantic_cache/        # 語意快取層
│   ├── manager.py         # 快取查詢 / 寫入策略
│   └── stores/            # Redis / in-memory 實作
│
├── registry/              # Plan 解析
│   └── ...                # PlanResolver：決定哪個 worker + provider 組合
│
├── models/                # Request/Response schema
│   ├── multimodal.py      # 多模態 input（圖片、語音）
│   ├── tts.py             # TTS request/response
│   └── embedding_models.py
│
└── observability/         # Metrics & tracing
    └── ...                # Prometheus counter / OpenTelemetry span
```

**SSE 狀態機**（串流核心設計）：

```
FAST_STREAMING   先用快速小模型輸出 preview token（低延遲體感）
      ↓
LARGE_BUFFERING  同時讓大模型在後台緩衝（高品質結果）
      ↓
REVERSE_EMIT     大模型完成後發一次 reverse 事件取代 preview（僅能發一次）
      ↓
DONE
```

**主要 API**：

```
POST /v1/chat/completions    主推論，支援 streaming SSE
POST /v1/embeddings          向量嵌入
POST /v1/audio/speech        TTS 語音合成
GET  /v1/models              列出可用模型
GET  /health                 健康檢查
GET  /metrics                Prometheus metrics
```

---

## 2. `xparse_iam/` — IAM & Governance 服務

**職責**：管理「誰是誰、誰可以用什麼、用多少、怎麼用」。所有資源的 CRUD、認證、授權、OIDC SSO 都在這裡。Gateway 每個請求都必須先向 IAM 驗證身份。

**技術棧**：Django + Django Ninja（REST API），PostgreSQL

**核心資源模型**：

```
Tenant                    # 最頂層組織（一家公司）
  └── Group               # 部門或專案群組
        └── Application   # 一個 AI 應用實體
              ├── APIKey            # 客戶端用來打 Gateway 的 key
              ├── PolicyBundle      # 策略集合（rate limit + guardrail…）
              ├── ProviderCredential # 企業自帶的 Provider key（BYOK）
              ├── Deployment        # 綁定到哪個模型 / 節點
              └── RateLimitPolicy   # 每分鐘 / 每日 token 上限
```

**目錄結構**：

```
xparse_iam/xparse_iam/
├── api/
│   ├── ninja_api/         # 所有 REST endpoints（~30 個檔案，共約 188 endpoints）
│   │   ├── _app_auth.py       # POST /iam/internal/gateway-validate（Gateway 呼叫）
│   │   ├── _applications.py   # Application CRUD
│   │   ├── _groups.py         # Group / Member 管理
│   │   ├── _tenants.py        # Tenant CRUD + API Key 管理
│   │   ├── _credentials.py    # Provider Credential（BYOK）
│   │   ├── _policies.py       # Rate Limit / Guardrail Policy
│   │   ├── _deployments.py    # Deployment Catalog
│   │   ├── _catalog.py        # Model catalog
│   │   ├── _oidc.py           # OIDC / SSO exchange
│   │   ├── _fleet_runtime.py  # Node allocation / quota
│   │   └── ...
│   ├── authentication.py  # JWT / API key 驗證邏輯
│   └── console_capabilities.py  # Console 前端頁面權限矩陣
│
├── application/
│   └── use_cases/         # 業務邏輯（CreateTenant、RotateAPIKey、BindDeployment…）
│
├── core/
│   ├── auth_engine.py     # 核心認證引擎
│   ├── oidc/              # OIDC provider 整合
│   └── crypto/            # API key 加密 / 雜湊
│
├── domain/
│   └── value_objects/     # Enum（KeyType、PolicyStatus、DeploymentState…）
│
├── db/
│   ├── models/            # Django ORM models
│   └── migrations/        # DB migrations（0001–0111+）
│
└── manage.py              # Django 管理入口
```

**關鍵設計**：
- 所有對外 API 由 Django Ninja 定義，自動產生 OpenAPI schema
- Gateway 只能透過 `/iam/internal/gateway-validate` 查身份，不可直讀 DB
- API Key rotate 採用雙 key overlap period，rolling rotation 不中斷服務

---

## 3. `3rd/xparse_audit/` — Audit SDK & API

**職責**：接收所有服務發送的 audit event，提供 evidence-grade 的查詢介面。獨立子模組，可單獨部署，也可被 bustream 用 SDK 模式直接寫入。

**技術棧**：FastAPI，JSONL sink（可選 S3 / Elasticsearch）

**目錄結構**：

```
src/audit/
├── api/                       # REST API server
│   ├── main.py                # FastAPI 啟動點
│   ├── routers/               # endpoints（events、evidence、stats、usage、health）
│   └── app.py                 # 建立 FastAPI 實例
│
├── sdk/
│   ├── client.py              # SDK client（bustream 用這個發 audit event）
│   ├── config.py              # SDK 設定（endpoint URL、buffer size…）
│   └── bounded_buffer.py      # 非同步發送用的有界 queue
│
├── core/domain/
│   ├── audit_event.py         # 核心 event schema
│   ├── audit_envelope.py      # 帶簽名的 envelope（tamper-evident）
│   ├── custody/               # Chain of custody（不可竄改的事件鏈）
│   ├── evidence/              # Evidence assembly（證據包裝）
│   ├── compliance/            # Compliance 標記
│   └── retention/             # Retention policy
│
├── storage/
│   ├── jsonl_event_store.py   # 主要儲存：JSONL 檔案
│   └── memory_storage.py      # 測試用 in-memory store
│
├── sink/
│   ├── jsonl_sink.py          # 本地 JSONL 寫入
│   ├── s3/                    # S3 sink（Enterprise 版）
│   └── remote/                # HTTP / gRPC / Elasticsearch sink
│
├── custody/
│   ├── trail_emitter.py       # 發送 custody trail
│   └── jsonl_repository.py    # 持久化 custody trail
│
├── vault/                     # 加密 vault（事件加密儲存）
└── correlation/               # Tempo trace correlation
```

**兩種使用模式**：

```
模式 A（SDK 模式）：bustream 直接 import sdk/client.py，非同步寫本地 JSONL
模式 B（API 模式）：bustream 發 HTTP 到 audit service，audit service 統一儲存
```

---

## 4. `xparse_fleet/` — Fleet API

**職責**：管理 GPU 節點的生命週期、模型部署（Deployment）、model catalog、Agent App 服務（NemoClaw / OpenWebUI）。是 Agent Platform 的 control plane。

**技術棧**：FastAPI，port 8090

**目錄結構**：

```
xparse_fleet/fleet/
├── app.py                     # FastAPI 入口
├── routes/                    # API endpoint handlers
│   ├── fleet.py               # Fleet 狀態查詢
│   ├── nodes.py               # 節點管理（register / deregister / drain）
│   ├── heartbeat.py           # 接收 agentd 心跳
│   ├── deployments.py         # Deployment CRUD
│   ├── catalog.py             # Model catalog
│   ├── services.py            # Agent App services（apply / delete / status）
│   ├── onboarding.py          # 新節點 onboarding 流程
│   ├── validation.py          # 節點驗收（GPU / driver / Docker）
│   └── workloads.py           # Workload scheduling
│
├── reconciler.py              # Fleet 狀態調和引擎（desired vs actual）
├── drift_detector.py          # 偵測 config drift
├── fleet_state.py             # Fleet 全域狀態（in-memory + DB 同步）
├── model_catalog.py           # Model catalog 管理
├── service_registry.py        # 服務登錄（健在 / 下線的 endpoint）
├── scheduler.py               # 與 xparse_scheduler 整合
│
└── lib/
    ├── fingerprint.py         # 節點硬體指紋（GPU 型號 / VRAM / CUDA）
    └── gpu_classifier.py      # GPU 分級（T4 / A100 / H100…）
```

**關鍵 API**：

```
GET  /v1/fleet/model-profiles        # Gateway 每 30 秒 poll，取得可路由 endpoints
POST /v1/fleet/heartbeat             # agentd 每 30 秒打一次，更新節點狀態
POST /v1/fleet/nodes/register        # 新節點加入
GET  /v1/fleet/status                # Console 首頁用，整體 fleet 健康度
POST /v1/services/apply              # 部署或更新 Agent App
```

---

## 5. `xparse_node_mgr/` — Node Runtime Agent（agentd）

**職責**：跑在每台 GPU 機器上的 Python daemon。負責：向 Fleet API 回報心跳、管理本機容器生命週期、執行模型下載、跑 validation benchmark。

**技術棧**：gRPC server（對 Fleet API 的本機 agent）

**目錄結構**：

```
xparse_node_mgr/
├── server.py                  # gRPC server 入口
├── core/
│   ├── heartbeat.py           # 定時向 Fleet API 發心跳
│   ├── instance_manager.py    # 管理本機 container instance
│   ├── download_manager.py    # Model 檔案下載（支援斷點續傳）
│   ├── watchdog.py            # 監控 container 健康，自動重啟
│   ├── resource_probe.py      # GPU / CPU / RAM 用量探測
│   └── sandbox_runtime.py     # nsjail sandbox 管理
│
├── handlers/                  # 各類請求 handler
│   ├── lifecycle.py           # 容器 start / stop / restart
│   ├── model_manager.py       # 模型安裝 / 卸載
│   ├── gpu.py                 # GPU 狀態回報
│   └── nemoclaw.py            # NemoClaw 專用 handler
│
└── validation/                # 節點驗收測試套件
    ├── runner.py              # 測試 orchestrator
    ├── profiles.py            # 驗收 profile（basic / gpu / full）
    └── tests/                 # 各測試模組
        ├── gpu_benchmark.py       # FP16 throughput benchmark
        ├── gpu_burnin.py          # 長時間壓力測試
        ├── streaming_stability.py # SSE 串流穩定性測試
        └── container_readiness.py # 容器啟動就緒測試
```

---

## 6. `xparse_container_platform/` — Container 生命週期 Library

**職責**：提供 Docker 容器與 nsjail sandbox 的統一操作介面。採用 Clean Architecture（DDD），核心 domain 與具體實作解耦，方便日後替換為 K8s。

**技術棧**：純 Python library（不是 server，被 `xparse_node_mgr/` 和 `xparse_fleet/` import）

**目錄結構**：

```
xparse_container_platform/
├── domain/                    # DDD 核心（不依賴任何外部框架）
│   ├── entities/
│   │   └── sandbox.py         # Sandbox entity（狀態機：CREATING→RUNNING→STOPPED）
│   └── value_objects/
│       ├── container_config.py    # 容器設定（image、env、ports、volumes…）
│       ├── container_info.py      # 容器運行時資訊（id、status、ip…）
│       └── network_config.py      # 網路設定
│
├── application/
│   ├── use_cases/             # 11 個 use case
│   │   ├── create_sandbox.py
│   │   ├── start_sandbox.py
│   │   ├── stop_sandbox.py
│   │   ├── destroy_sandbox.py
│   │   ├── exec_in_sandbox.py     # 在容器內執行指令
│   │   └── get_sandbox_status.py
│   └── protocols/             # Port 抽象介面（Liskov-safe）
│
├── infrastructure/            # 具體實作（可替換）
│   ├── runtime/
│   │   └── docker_runtime.py  # Docker SDK 實作
│   └── sandbox/
│       └── nsjail_sandbox.py  # nsjail（Linux namespace sandbox）實作
│
└── interface/
    └── container.py           # 外部唯一入口（Facade）
```

**設計哲學**：外部呼叫者只看 `interface/container.py`，不知道底層是 Docker 還是 nsjail。切換實作只需換 infrastructure 層。

---

## 7. `xparse_resource_manager/` — Endpoint 容量守衛

**職責**：每個 inference endpoint（Provider URL）有並發上限。這個服務用 priority queue + lease 機制，讓 Gateway 在打 Provider 前必須排隊取票，避免 Provider 被超量打爆。

**技術棧**：FastAPI，port 8020

**運作邏輯**：

```
Gateway                               ResourceManager
  │                                         │
  ├── POST /acquire ──────────────────────→ │  排隊，超過 max_concurrent 則 block
  │   ← { lease_id, expires_at } ─────────  │
  │                                         │
  ├── 打 Provider（帶 lease_id）             │
  │                                         │
  └── POST /release ──────────────────────→ │  釋放，讓下一個等待者通過
                                            │
                                   TTL reaper 定期清超時未釋放的 lease
```

**目錄結構**：

```
xparse_resource_manager/
├── __main__.py / app.py       # FastAPI 入口
├── api/
│   ├── core.py                # /acquire、/release、/status endpoints
│   └── admin.py               # Admin endpoints（新增 / 更新 endpoint config）
│
├── engine/
│   ├── capacity_engine.py     # 核心 lease 管理（priority queue + waitlist）
│   └── ttl_reaper.py          # 定期清理超時 lease（asyncio background task）
│
├── domain/
│   ├── lease.py               # Lease value object（id、tenant、expires_at…）
│   └── priority_queue.py      # Priority queue 實作（高優先級 tenant 先拿到 slot）
│
└── client/
    ├── resource_client.py     # Client SDK（bustream import 這個來呼叫 ResourceManager）
    └── periodic_refresher.py  # 定期重整 endpoint 清單
```

---

## 8. `xparse_routing/` — 路由策略 Library

**職責**：決定一個 AI 請求應該打哪個 Provider / endpoint。採用策略模式，5 種路由算法可插拔。

**技術棧**：純 Python library（被 bustream/gateway/ 的 PlanResolver import）

**5 種路由策略**：

| 策略 | 邏輯 |
|------|------|
| `direct` | 直接指定，無選擇邏輯 |
| `cost_first` | 優先選成本最低的 endpoint |
| `energy_first` | 優先選能耗最低的 endpoint（綠色 AI） |
| `health_aware` | 優先選健康度最高的 endpoint，避開錯誤率高的 |
| `twin` | 同時打兩個 endpoint，取先回來的結果（低延遲） |

**目錄結構**：

```
xparse_routing/
├── application/
│   ├── resolver.py            # 路由決策入口：輸入 request context → 輸出 endpoint
│   ├── registry.py            # 已知 endpoint 的 registry
│   └── strategies/            # 5 種策略實作
│
├── domain/
│   ├── protocols.py           # Strategy Protocol（Liskov-safe interface）
│   └── errors.py              # 路由失敗的明確 exception
│
└── infrastructure/
    ├── database.py            # Endpoint config 讀取（from IAM DB or config file）
    └── repository.py          # Repository 抽象
```

---

## 9. `xparse_scheduler/` — GPU Placement 排程器

**職責**：接收 GPU 資源 placement 請求（「我要一個有 A100 的節點跑這個模型」），查詢 Fleet 目前的節點容量，決定放在哪台機器。橋接 Fleet API 與 ResourceManager。

**技術棧**：FastAPI

**目錄結構**：

```
xparse_scheduler/
├── app.py / __main__.py       # FastAPI 入口
├── api/
│   ├── placement_routes.py    # POST /placement/request、DELETE /placement/{id}
│   └── capacity_routes.py     # GET /capacity/summary
│
├── application/
│   ├── request_placement.py   # 核心邏輯：根據資源需求選節點
│   ├── release_placement.py   # 釋放已佔用的 placement
│   └── query_capacity.py      # 查詢整體可用容量
│
├── domain/
│   ├── entities.py            # PlacementRequest entity
│   └── resource_vector.py     # 資源需求 vector（GPU type、VRAM、CPU…）
│
└── infrastructure/
    ├── http_fleet.py          # 呼叫 Fleet API 取節點清單
    └── http_iam.py            # 呼叫 IAM API 取 quota 限制
```

---

## 10. `xparse_warden/` — 系統健康監控

**職責**：定期跑一組 health check，偵測系統異常（audit 斷掉、容器不健康、docker-compose config drift），並匯出 Prometheus metrics 給 Grafana dashboard。

**技術棧**：Python CLI daemon

**目錄結構**：

```
xparse_warden/src/warden/
├── main.py                    # 入口，啟動 check loop
├── runner.py                  # Check orchestrator（逐一執行 checks，收集結果）
├── models.py                  # CheckResult value object
├── history.py                 # 保存最近 N 次 check 結果，計算趨勢
├── prom_exporter.py           # 匯出 /metrics（Prometheus gauge）
│
└── checks/                    # Health check 插件
    ├── base.py                # Check base class（所有 check 必須繼承）
    ├── audit_diagnostics.py   # 檢查 Audit service 是否正常接收 events
    ├── container_health.py    # 檢查各 container 是否 running + healthy
    └── compose_drift.py       # 偵測 docker-compose 定義與實際狀態是否 drift
```

---

## 服務間依賴關係

```
bustream (Gateway)
  ├── → xparse_iam         每個請求驗身份（HTTP）
  ├── → xparse_resource_manager  每個請求申請 lease（HTTP）
  ├── → xparse_fleet       每 30 秒拉 model-profiles（HTTP）
  ├── import xparse_routing    路由決策（library，in-process）
  └── import 3rd/xparse_audit  寫 audit event（SDK，in-process）

xparse_fleet (Fleet API)
  ├── → xparse_iam         取 quota / policy（HTTP）
  ├── → xparse_scheduler   placement 請求（HTTP）
  ├── ← xparse_node_mgr    heartbeat（HTTP，agentd 主動打 Fleet）
  └── import xparse_container_platform  (library，in-process)

xparse_node_mgr (agentd)
  ├── → xparse_fleet       heartbeat + 接收指令（HTTP）
  └── import xparse_container_platform  (library，in-process)

xparse_scheduler
  ├── → xparse_fleet       查節點容量（HTTP）
  └── → xparse_iam         查 quota（HTTP）

xparse_warden
  └── → 所有服務           健康探針（HTTP /health）
```
