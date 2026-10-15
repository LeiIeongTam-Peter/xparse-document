# Xparse Audit — 模組技術報告

> 版本：xparse-audit 0.7.1 | 更新日期：2026-05-30

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

### 類型

**Backend Library + HTTP API Service**

`xparse_audit` 是一個治理級審計系統，以雙重形式存在：

1. **Python SDK（Library）**：嵌入 `bustream` Gateway、IAM 等服務中，提供非阻塞的審計事件寫入介面（`AuditClient`）
2. **REST API Service（Backend）**：獨立的 FastAPI HTTP 服務，供 Console 前端查詢審計事件、統計、證據包等

### 協議

| 角色 | 協議 | 說明 |
|------|------|------|
| SDK 寫入路徑 | 本地函式呼叫 → 非同步 Queue | 生產者側，嵌入 Gateway/IAM |
| Sink 持久化 | 本地 JSONL / HTTP / gRPC / Elasticsearch / S3 | 多 Sink 可選，依部署環境配置 |
| REST API | HTTP/1.1 + JSON | 查詢端點，供 Console 使用 |
| Sidecar 關聯 | HTTP → Grafana Tempo HTTP API | 查詢 `xparse-otel-sidecar` 與 `xparse-gateway` spans |
| 可觀測性 | OpenTelemetry OTLP/gRPC → Tempo | Trace 事件上報 |
| 指標 | Prometheus `/metrics` | SDK 緩衝區與事件統計 |
| Evidence Package | HTTP streaming (ZIP) | 證據包下載 |

### 面向對象

- **Console App（前端）**：查詢事件、統計報表、使用量分析、證據包管理
- **bustream Gateway**：透過 SDK 寫入執行事件（request_started/finished）、效能指標、治理決策
- **xparse_iam**：透過 SDK 寫入身份驗證事件
- **合規/稽核人員**：透過 Evidence Package API 匯出法律證據
- **SRE / 維運**：Prometheus + Grafana 監控 SDK 健康度

### 部署方式

```
Docker Container (python:3.11-slim)
  Port: 8001
  Entry: uvicorn audit.api.main:app
  Volume: /var/audit/evidence (JSONL 事件檔案)
  Health: GET /health/live, GET /health/ready
```

SDK 以 Python package 形式安裝於 `bustream`、`xparse_iam` 等服務的容器中。

---

## 2. 資料夾結構總覽

```
3rd/xparse_audit/
├── src/audit/                         # 主要套件根目錄
│   ├── api/                           # FastAPI HTTP 服務層
│   │   ├── main.py                    # 生產 app 工廠（環境變數驅動）
│   │   ├── app.py                     # create_app()、CORS、router 註冊
│   │   ├── models.py                  # Pydantic request/response 模型
│   │   ├── auth.py                    # AuthContext、AuthProvider 插拔介面
│   │   ├── iam_auth.py                # IAM 認證整合（生產用）
│   │   └── routers/
│   │       ├── events.py              # POST/GET /events/* (5 端點)
│   │       ├── stats.py               # GET /stats/* (4 端點)
│   │       ├── evidence.py            # /evidence/packages/* (5 端點)
│   │       ├── usage.py               # GET /usage/* (3 端點)
│   │       ├── health.py              # GET /health/* (3 端點)
│   │       └── diagnostics.py         # GET /diagnostics/store (1 端點)
│   ├── sdk/                           # 公開 SDK（嵌入其他服務）
│   │   ├── client.py                  # AuditClient — 主要 API 入口
│   │   ├── config.py                  # AuditConfig dataclass
│   │   └── bounded_buffer.py          # BoundedBuffer — 非阻塞有界隊列
│   ├── buffer/
│   │   └── bounded_queue.py           # BoundedAuditBuffer — 非同步有界佇列
│   ├── writer/
│   │   └── async_writer.py            # AsyncSinkWriter — 背景寫入工作
│   ├── sink/                          # Sink 實作（多種後端）
│   │   ├── protocol.py                # AuditSink Protocol 定義
│   │   ├── jsonl_sink.py              # 非同步 JSONL 寫入（aiofiles）
│   │   ├── sync_jsonl_sink.py         # 同步 JSONL 寫入
│   │   ├── rotation.py                # 檔案輪換策略
│   │   ├── remote/
│   │   │   ├── config.py              # RetryConfig、CircuitBreakerConfig、RemoteSinkConfig
│   │   │   ├── http_sink.py           # HTTP 遠端 Sink（批次 + circuit breaker）
│   │   │   ├── elastic_sink.py        # Elasticsearch Sink
│   │   │   ├── grpc_sink.py           # gRPC Sink
│   │   │   ├── circuit_breaker.py     # CircuitBreaker（CLOSED/OPEN/HALF_OPEN）
│   │   │   ├── retry.py               # ExponentialBackoff + RetryExecutor
│   │   │   └── exceptions.py          # Sink 專用例外
│   │   └── s3/
│   │       ├── s3_sink.py             # S3 Sink（boto3，租戶分割）
│   │       └── s3_config.py           # S3SinkConfig
│   ├── core/                          # Clean Architecture 核心（零外部依賴）
│   │   ├── domain/                    # Domain 實體與值物件
│   │   │   ├── audit_event.py         # AuditEvent（封信 + payload）
│   │   │   ├── audit_envelope.py      # AuditEnvelope（不可變信封）
│   │   │   ├── actor.py               # Actor 值物件
│   │   │   ├── target.py              # Target 值物件
│   │   │   ├── compliance/            # Compliance Trail domain（hash chain）
│   │   │   ├── custody/               # Chain-of-Custody domain
│   │   │   ├── evidence/              # Evidence Bundle domain
│   │   │   ├── governance/            # PolicyDecision、Guardrail domain
│   │   │   ├── observability/         # Observability Payload domain
│   │   │   ├── retention/             # RetentionConfig、AuditRole domain
│   │   │   ├── storage/               # StorageTier、TierTransition domain
│   │   │   └── vault/                 # Vault AccessGrant domain
│   │   ├── ports/                     # Protocol 抽象介面
│   │   │   ├── audit_sink.py          # AuditSink protocol
│   │   │   ├── access_control.py      # AccessControl protocol
│   │   │   ├── trail_storage.py       # TrailStorage protocol（449 行）
│   │   │   ├── evidence_assembly.py   # EvidenceAssembly protocol
│   │   │   ├── content_vault.py       # ContentVault protocol（335 行）
│   │   │   ├── retention_policy.py    # RetentionPolicy protocol
│   │   │   ├── custody.py             # Custody protocol
│   │   │   └── archive_storage.py     # ArchiveStorage protocol（394 行）
│   │   └── use_cases/
│   │       ├── retention_service.py   # RetentionService（492 行）
│   │       └── custody_service.py     # CustodyService（451 行）
│   ├── storage/                       # 事件讀取（查詢端）
│   │   ├── jsonl_event_store.py       # JsonlEventStore — JSONL 事件載入查詢
│   │   ├── local_storage.py           # LocalStorage（717 行）
│   │   └── memory_storage.py          # MemoryStorage（測試用）
│   ├── access/                        # RBAC 存取控制
│   │   ├── query.py                   # AuditQueryService（角色過濾 + 紅線化）
│   │   └── rbac.py                    # RoleBasedAccessControl
│   ├── evidence/                      # 證據包管理
│   │   ├── assembler.py               # DefaultEvidenceAssembler（密碼學組裝）
│   │   ├── exporter.py                # EvidenceExporter（ZIP 匯出）
│   │   └── package_store.py           # SQLite/PostgreSQL/Memory PackageStore（870 行）
│   ├── custody/                       # Chain-of-Custody
│   │   ├── jsonl_repository.py        # JsonlCustodyRepository
│   │   └── trail_emitter.py           # TrailEmitter
│   ├── trail/
│   │   └── jsonl_storage.py           # JsonlTrailStorage（hash chain 段落存儲）
│   ├── vault/
│   │   ├── fernet_vault.py            # FernetVault（Fernet 對稱加密）
│   │   └── key_provider.py            # KeyProvider（金鑰管理）
│   ├── retention/
│   │   └── policy.py                  # DefaultRetentionPolicy
│   ├── metrics/
│   │   ├── prometheus_metrics.py      # AuditMetrics（Prometheus counters/gauges）
│   │   └── server.py                  # MetricsServer（/metrics 端點）
│   ├── tracing/
│   │   ├── tracer.py                  # AuditTracer（OpenTelemetry，506 行）
│   │   └── config.py                  # TracingConfig
│   └── correlation/
│       ├── engine.py                  # CorrelationEngine（Sidecar-Gateway span 關聯）
│       ├── tempo_client.py            # TempoClient（Tempo HTTP API 客戶端）
│       └── models.py                  # GatewaySpan、SidecarSpan 資料模型
├── tests/                             # 測試套件
│   ├── unit/                          # 單元測試（pure，無 mock）
│   ├── integration/                   # 整合測試（含 elastic、trail、sdk）
│   └── contract/                      # 契約測試（storage、tracing）
├── examples/                          # 使用範例
│   └── audit-sdk/                     # 01_quick_start.py、02_core_domain.py 等
├── docs/
│   ├── adr/                           # AUDIT-ADR-001 至 015（15 份）
│   ├── prd/                           # AUDIT-PRD-001 至 012（12 份）
│   ├── specs/                         # SPEC-001 至 006
│   ├── architecture/                  # 架構圖
│   └── guides/                        # 開發指南
├── deploy/
│   └── observability/                 # Observability stack（Docker Compose）
│       ├── docker-compose.yml         # Tempo + Prometheus + Grafana + ES + Kibana
│       ├── .env.example               # 所有 secrets 範本
│       ├── elasticsearch/             # ILM 政策、Index template、RBAC 角色
│       ├── grafana/                   # Dashboard JSON + Datasource provision
│       ├── kibana/                    # 合規儀表板 ndjson
│       ├── prometheus/                # prometheus.yml（scrape 設定）
│       └── tempo/                     # tempo.yaml（receiver + backend + retention）
├── Dockerfile                         # python:3.11-slim，port 8001
├── pyproject.toml                     # 版本 0.7.1，Python >=3.10
└── claude.md                          # 工程規範（PDCA、Clean Architecture）
```

---

## 3. 各模組功能說明

### API 層

| 模組 | 檔案 | 職責 | 關聯文件 |
|------|------|------|---------|
| App Factory | `api/main.py` | 生產 app 工廠，組裝所有依賴（EventStore、QueryService、PackageStore、CorrelationEngine） | ADR-007 |
| App Builder | `api/app.py` | `create_app()`，掛載 CORS、exception handlers、所有 router | — |
| API Models | `api/models.py` | Pydantic Request/Response 契約（382 行） | — |
| Auth | `api/auth.py` | `AuthContext`（role/user_id/tenant_id）、`AuthProvider` 插拔介面 | ADR-007 |
| IAM Auth | `api/iam_auth.py` | 生產環境 IAM 整合認證 | ADR-007 |
| Events Router | `api/routers/events.py` | 審計事件查詢（5 端點，RBAC 過濾 + 紅線化） | ADR-007 |
| Stats Router | `api/routers/stats.py` | 聚合統計、時間序列、Top Applications（4 端點） | — |
| Evidence Router | `api/routers/evidence.py` | 證據包 CRUD + ZIP 下載（5 端點） | ADR-012 |
| Usage Router | `api/routers/usage.py` | 每使用者 LLM 消耗統計（3 端點，Tempo 關聯） | ADR-141 |
| Health Router | `api/routers/health.py` | K8s liveness/readiness probe（3 端點） | — |
| Diagnostics Router | `api/routers/diagnostics.py` | EventStore 內部狀態（1 端點，防靜默失敗） | — |

### SDK 層

| 模組 | 檔案 | 職責 | 關聯文件 |
|------|------|------|---------|
| AuditClient | `sdk/client.py` | 主要公開 API（非阻塞寫入，868 行） | ADR-010 |
| AuditConfig | `sdk/config.py` | 配置 dataclass（queue size、degradation threshold、metrics、tracing） | ADR-008, ADR-010 |
| BoundedBuffer | `sdk/bounded_buffer.py` | 有界非阻塞隊列（HEALTHY/DEGRADED/SATURATED 狀態機） | ADR-010 |

### Buffer / Writer 層

| 模組 | 檔案 | 職責 | 關聯文件 |
|------|------|------|---------|
| BoundedAuditBuffer | `buffer/bounded_queue.py` | 非同步有界佇列，支援背壓 | ADR-010 |
| AsyncSinkWriter | `writer/async_writer.py` | 背景工作：從佇列取事件批次寫入 Sink | ADR-010 |

### Sink 層

| 模組 | 檔案 | 職責 | 關聯文件 |
|------|------|------|---------|
| AuditSink Protocol | `sink/protocol.py` | append-only、非阻塞、flush 保證持久化 | ADR-004 |
| JSONLSink（async） | `sink/jsonl_sink.py` | aiofiles 非同步 JSONL 寫入 | ADR-001 |
| JsonlSink（sync） | `sink/sync_jsonl_sink.py` | 同步 JSONL 寫入（Gateway 使用） | ADR-001 |
| SizeBasedRotation | `sink/rotation.py` | 檔案輪換策略（按大小） | — |
| HttpAuditSink | `sink/remote/http_sink.py` | HTTP 批次發送（gzip + retry + circuit breaker） | ADR-004 |
| ElasticAuditSink | `sink/remote/elastic_sink.py` | Elasticsearch 批次寫入（669 行） | SPEC-006 |
| GrpcAuditSink | `sink/remote/grpc_sink.py` | gRPC 串流（612 行） | ADR-004 |
| S3AuditSink | `sink/s3/s3_sink.py` | AWS S3 持久化（boto3，租戶分割鍵） | ADR-004 |
| CircuitBreaker | `sink/remote/circuit_breaker.py` | CLOSED/OPEN/HALF_OPEN 狀態機 | — |
| RetryExecutor | `sink/remote/retry.py` | 指數退避（max 3 次，jitter） | — |

### Domain 層（`core/domain/`）

| 模組 | 子資料夾 | 職責 | 關聯文件 |
|------|---------|------|---------|
| AuditEvent | 根層 | 不可變事件（信封 + 不透明 payload） | ADR-001, ADR-013 |
| AuditEnvelope | 根層 | 不可變信封（event_id/event_type/trace_id/payload_hash 等） | ADR-001~003 |
| Actor / Target | 根層 | 值物件（至少一個身份欄位） | ADR-003 |
| Governance | `governance/` | PolicyDecisionPayload、GuardrailPayload、ReasonCode、Decision、EnforcementMode | SPEC-002 |
| Observability | `observability/` | ObservabilityPayload（LatencyMetrics/TokenMetrics/CostMetrics/ModelMetrics） | SPEC-001 |
| Retention | `retention/` | RetentionConfig（30/90/14/365 天）、AuditRole enum、LegalHold | ADR-006, ADR-007 |
| Custody | `custody/` | CustodyChain（聚合根）、CustodyEvent、CustodyState、DeliveryMethod | ADR-014 |
| Evidence | `evidence/` | EvidenceBundle、EvidenceManifest、IntegrityProof、DisclosureScope | ADR-012 |
| Compliance | `compliance/` | TrailEntry、TrailSegment（hash chain）、SegmentAnchor、IntegrityResult | SPEC-005 |
| Storage | `storage/` | StorageTier、TierTransition（322 行） | — |
| Vault | `vault/` | AccessGrant（385 行） | ADR-011 |

### Infrastructure 層

| 模組 | 檔案 | 職責 | 關聯文件 |
|------|------|------|---------|
| JsonlEventStore | `storage/jsonl_event_store.py` | 從 JSONL 載入事件供 API 查詢（379 行） | SPEC-005 |
| AuditQueryService | `access/query.py` | RBAC 過濾 + 自動紅線化（角色決定可見欄位） | ADR-007 |
| RoleBasedAccessControl | `access/rbac.py` | 角色定義（SRE/SECURITY/COMPLIANCE/BILLING/APP_OWNER） | ADR-007 |
| DefaultEvidenceAssembler | `evidence/assembler.py` | 密碼學完整性組裝（SHA256 雜湊鏈，517 行） | ADR-012 |
| EvidenceExporter | `evidence/exporter.py` | 匯出為 ZIP（manifest.json + audit_events.jsonl） | ADR-012 |
| EvidencePackageStore | `evidence/package_store.py` | SQLite/PostgreSQL/Memory 後端（870 行） | ADR-012 |
| JsonlTrailStorage | `trail/jsonl_storage.py` | Compliance Trail 段落存儲（SHA256 hash chain，759 行） | SPEC-005 |
| FernetVault | `vault/fernet_vault.py` | Fernet 對稱加密存儲（454 行） | ADR-011 |
| DefaultRetentionPolicy | `retention/policy.py` | 保留期決策 + Legal Hold 覆蓋（198 行） | ADR-006 |
| AuditMetrics | `metrics/prometheus_metrics.py` | Prometheus 指標（470 行） | Phase 2A |
| AuditTracer | `tracing/tracer.py` | OpenTelemetry OTLP（506 行） | ADR-015 |
| CorrelationEngine | `correlation/engine.py` | Sidecar-Gateway span 關聯邏輯（383 行） | ADR-141 |
| TempoClient | `correlation/tempo_client.py` | Tempo HTTP API 查詢客戶端（459 行） | ADR-015 |

---

## 4. 對外 API 端點完整列表

### 基礎 URL

```
http://<host>:8001
```

### 認證方式

所有 API 端點需要認證：

| 認證方式 | 說明 |
|---------|------|
| `X-Audit-Role: <role>` | 開發用 header（bypass 真正認證） |
| `X-API-Key: <key>` | API Key 認證 |
| `Authorization: Bearer <token>` | Bearer Token（IAM 整合） |
| `X-User-ID: <id>` | 搭配 header 認證使用 |
| `X-Tenant-ID: <id>` | 租戶範圍（APP_OWNER/BILLING 角色必填） |

### 角色權限矩陣

| 角色 | 可見事件前綴 | 可見原始資料 | 租戶限制 |
|------|-----------|----------|--------|
| `COMPLIANCE` | `audit.*` | 是 | 無 |
| `SYSTEM` | `audit.*` | 是 | 無 |
| `SRE` | `audit.system.*`、`audit.observability.*` | 否 | 無 |
| `SECURITY` | `audit.identity.*`、`audit.policy.*`、`audit.access.*` | 否 | 無 |
| `APP_OWNER` | `audit.execution.*`、`audit.observability.*` | 否 | 必須提供 tenant_id |
| `BILLING` | `audit.observability.*` | 否 | 必須提供 tenant_id |

---

### 4.1 Events 端點（`/events`）

#### `POST /events/query`

| 項目 | 內容 |
|------|------|
| **用途** | 查詢審計事件，支援多條件過濾與分頁，自動依角色過濾與紅線化 |
| **認證** | AuthContext（role + user_id 必填） |
| **Status Code** | 200 OK |

**Request Headers：**
```
Content-Type: application/json
X-Audit-Role: compliance
X-User-ID: user-123
X-Tenant-ID: tenant-456  # APP_OWNER/BILLING 角色必填
```

**Request Body：**
```json
{
  "event_types": ["audit.execution.", "audit.governance."],
  "tenant_id": "tenant-456",
  "trace_id": "trace-abc-123",
  "start_time": "2026-05-29T00:00:00Z",
  "end_time": "2026-05-30T00:00:00Z",
  "limit": 100,
  "offset": 0,
  "application_codes": ["app-001"],
  "purpose": "audit trail logging"
}
```

**Response：**
```json
{
  "events": [
    {
      "event_id": "evt-abc123",
      "event_type": "audit.execution.request_started",
      "trace_id": "trace-abc-123",
      "occurred_at": "2026-05-29T10:30:00Z",
      "tenant_id": "tenant-456",
      "data": { "method": "POST", "model": "gpt-4" }
    }
  ],
  "pagination": {
    "offset": 0,
    "limit": 100,
    "total": 42,
    "has_more": false
  },
  "query_id": "qry-xyz789"
}
```

**程式碼**：`src/audit/api/routers/events.py:65-137`

---

#### `GET /events`

| 項目 | 內容 |
|------|------|
| **用途** | 列表查詢事件（`POST /events/query` 的 GET 便利版） |

**Query Parameters：**
```
event_type=audit.execution.request_started
tenant_id=tenant-456
trace_id=trace-abc-123
start_time=2026-05-29T00:00:00Z
end_time=2026-05-30T00:00:00Z
limit=100
offset=0
application_codes=app-001,app-002
purpose=list
```

**Response**：同 `POST /events/query`

**程式碼**：`src/audit/api/routers/events.py:140-211`

---

#### `GET /events/types`

| 項目 | 內容 |
|------|------|
| **用途** | 列出目前角色可存取的事件型別前綴 |

**Response：**
```json
{
  "role": "sre",
  "allowed_event_prefixes": ["audit.system.", "audit.observability."],
  "can_access_raw_data": false,
  "requires_tenant_scope": false
}
```

**程式碼**：`src/audit/api/routers/events.py:214-233`

---

#### `GET /events/trace/{trace_id}`

| 項目 | 內容 |
|------|------|
| **用途** | 取得特定 trace 的所有審計事件，並計算總 duration |
| **Path Parameter** | `trace_id` (string) |

**Response：**
```json
{
  "trace_id": "trace-abc-123",
  "events": [ { "event_id": "...", "event_type": "...", "occurred_at": "..." } ],
  "span_count": 5,
  "duration_ms": 342.5
}
```

**程式碼**：`src/audit/api/routers/events.py:236-282`

---

#### `GET /events/{event_id}`

| 項目 | 內容 |
|------|------|
| **用途** | 依 ID 取得單一審計事件 |
| **Path Parameter** | `event_id` (string) |

**Response**：`EventResponse`（同 events 陣列中的單筆）

**程式碼**：`src/audit/api/routers/events.py:285-321`

---

### 4.2 Stats 端點（`/stats`）

#### `GET /stats/summary`

| 項目 | 內容 |
|------|------|
| **用途** | 指定時間範圍的聚合統計（requests/tokens/errors/latency） |

**Query Parameters：**
```
time_range=24h        # 1h|6h|24h|7d|30d，預設 24h
start_time=<ISO 8601> # 選填，覆蓋 preset
end_time=<ISO 8601>   # 選填
tenant_id=<id>        # 選填
application_codes=<code1,code2>
```

**Response：**
```json
{
  "total_events": 10215,
  "total_requests": 8432,
  "successful_requests": 8100,
  "failed_requests": 200,
  "blocked_requests": 132,
  "error_rate": 3.94,
  "total_tokens": 2540000,
  "estimated_cost": 12.5,
  "avg_latency_ms": 145.3,
  "p95_latency_ms": 380.0,
  "avg_ttft_ms": 42.1,
  "avg_tps": 18.4,
  "time_range_start": "2026-05-29T10:00:00Z",
  "time_range_end": "2026-05-30T10:00:00Z"
}
```

**程式碼**：`src/audit/api/routers/stats.py:421-507`

---

#### `GET /stats/time-series`

| 項目 | 內容 |
|------|------|
| **用途** | 取得指定 metric 的時間序列（圖表用） |

**Query Parameters：**
```
metric=requests   # requests|tokens|errors|latency|ttft|tps，預設 requests
time_range=24h
start_time=<ISO 8601>
end_time=<ISO 8601>
tenant_id=<id>
application_codes=<codes>
```

**Response：**
```json
{
  "metric": "requests",
  "points": [
    { "timestamp": "2026-05-29T10:00:00Z", "value": 124.0, "count": 124 },
    { "timestamp": "2026-05-29T10:15:00Z", "value": 98.0, "count": 98 }
  ],
  "granularity": "15m",
  "time_range_start": "2026-05-29T10:00:00Z",
  "time_range_end": "2026-05-30T10:00:00Z"
}
```

顆粒度對照：`1h→5m`、`6h→15m`、`24h→1h`、`7d→6h`、`30d→1d`

**程式碼**：`src/audit/api/routers/stats.py:510-596`

---

#### `GET /stats/distribution`

| 項目 | 內容 |
|------|------|
| **用途** | 事件型別分佈（用於 Pie Chart） |

**Response：**
```json
{
  "distribution": [
    { "event_type": "audit.execution.request_started", "count": 4200, "percentage": 41.1 },
    { "event_type": "audit.observability.performance", "count": 3800, "percentage": 37.2 }
  ],
  "total_events": 10215,
  "time_range_start": "...",
  "time_range_end": "..."
}
```

**程式碼**：`src/audit/api/routers/stats.py:599-667`

---

#### `GET /stats/top-applications`

| 項目 | 內容 |
|------|------|
| **用途** | 依 requests 排序的頂級應用程式 |

**Query Parameters**：`limit=10`（1-100）、`time_range`、`tenant_id` 等

**Response：**
```json
{
  "applications": [
    {
      "application_id": "app-001",
      "application_name": "ChatBot Pro",
      "request_count": 3200,
      "error_count": 45,
      "token_count": 980000,
      "estimated_cost": 4.9
    }
  ],
  "time_range_start": "...",
  "time_range_end": "..."
}
```

**程式碼**：`src/audit/api/routers/stats.py:670-743`

---

### 4.3 Evidence 端點（`/evidence`）

#### `POST /evidence/packages`

| 項目 | 內容 |
|------|------|
| **用途** | 建立證據套件（非同步，立即回 202，背景生成） |
| **認證** | 需要 COMPLIANCE 或 SYSTEM 角色 |
| **Status Code** | 202 Accepted |

**Request Body：**
```json
{
  "start_time": "2026-05-01T00:00:00Z",
  "end_time": "2026-05-31T23:59:59Z",
  "reason": "Quarterly compliance audit Q2 2026",
  "tenant_id": "tenant-456",
  "event_types": ["audit.governance.", "audit.identity."],
  "include_raw_data": false
}
```

**Response（202）：**
```json
{
  "package_id": "pkg-a1b2c3d4e5f6",
  "status": "pending",
  "created_at": "2026-05-30T10:00:00Z",
  "created_by": "user-123",
  "reason": "Quarterly compliance audit Q2 2026",
  "time_range_start": "2026-05-01T00:00:00Z",
  "time_range_end": "2026-05-31T23:59:59Z",
  "tenant_id": "tenant-456",
  "events_count": null,
  "size_bytes": null,
  "expires_at": "2026-06-06T10:00:00Z",
  "download_url": null,
  "error_message": null,
  "bundle_hash": null,
  "manifest_hash": null
}
```

**程式碼**：`src/audit/api/routers/evidence.py:202-279`

---

#### `GET /evidence/packages`

| 項目 | 內容 |
|------|------|
| **用途** | 列表查詢證據套件（含分頁） |

**Query Parameters**：`limit=50`（1-100）、`offset=0`、`status=ready`

**Response：**
```json
{
  "packages": [ { "/* EvidencePackageResponse */" : "..." } ],
  "pagination": { "offset": 0, "limit": 50, "total": 5, "has_more": false }
}
```

---

#### `GET /evidence/packages/{package_id}`

| 項目 | 內容 |
|------|------|
| **用途** | 取得單一證據套件中繼資料（status：pending/generating/ready/failed） |

---

#### `GET /evidence/packages/{package_id}/download`

| 項目 | 內容 |
|------|------|
| **用途** | 下載證據套件（ZIP 格式串流） |
| **Response Content-Type** | `application/zip` |
| **Response Headers** | `Content-Disposition: attachment; filename=evidence-{id}.zip`；`Content-Length: {size}` |

ZIP 內容：
```
evidence-{id}/
  manifest.json           # 事件清單 + 雜湊清單
  audit_events.jsonl      # 所有審計事件（一行一筆）
  content_refs.json       # 敏感內容參照（不含明文）
  integrity.json          # SHA256 完整性證明
```

---

#### `DELETE /evidence/packages/{package_id}`

| 項目 | 內容 |
|------|------|
| **用途** | 刪除指定證據套件 |
| **Status Code** | 204 No Content |

---

### 4.4 Usage 端點（`/usage`）

#### `GET /usage/per-user`

| 項目 | 內容 |
|------|------|
| **用途** | 依使用者彙總 LLM 消耗（透過 Sidecar-Gateway Span 關聯） |

**Query Parameters：**
```
time_range=24h
tenant_id=<id>
app_code=<code>
deploy_code=<code>
application_codes=<codes>
```

**Response：**
```json
{
  "users": [
    {
      "user_id": "user-001",
      "tenant_id": "tenant-456",
      "total_requests": 120,
      "total_input_tokens": 45000,
      "total_output_tokens": 32000,
      "total_tokens": 77000,
      "estimated_cost": 0.38,
      "avg_latency_ms": 155.2,
      "top_model": "gpt-4",
      "model_distribution": { "gpt-4": 85, "gpt-3.5-turbo": 35 },
      "last_active": "2026-05-30T09:45:00Z",
      "correlation_rate": 0.92
    }
  ],
  "time_range_start": "...",
  "time_range_end": "...",
  "total_correlated": 115,
  "total_unmatched": 5
}
```

**程式碼**：`src/audit/api/routers/usage.py:70-171`

---

#### `GET /usage/per-user/time-series`

| 項目 | 內容 |
|------|------|
| **用途** | 特定使用者的 token 消耗時間序列 |

**Query Parameters**：`user_id=<required>`、`metric=tokens`（tokens/requests/cost）、`time_range`

**Response**：同 `/stats/time-series`

---

#### `GET /usage/correlation-health`

| 項目 | 內容 |
|------|------|
| **用途** | Sidecar-Gateway span 關聯健康度診斷 |

**Response：**
```json
{
  "total_sidecar_spans": 1200,
  "total_gateway_spans": 1100,
  "matched_count": 1050,
  "unmatched_count": 150,
  "correlation_rate": 0.875,
  "avg_confidence": 0.94,
  "tempo_available": true,
  "time_range_start": "...",
  "time_range_end": "..."
}
```

---

### 4.5 Health 端點（`/health`）

#### `GET /health`

**Response（200 healthy / 207 degraded / 503 unhealthy）：**
```json
{
  "status": "healthy",
  "version": "0.7.1",
  "timestamp": "2026-05-30T10:00:00Z",
  "components": {
    "query_service": "healthy",
    "metrics": "healthy",
    "tracing": "not_available"
  }
}
```

#### `GET /health/live`

Kubernetes liveness probe，回傳 `{"status": "alive"}`。

#### `GET /health/ready`

Kubernetes readiness probe，503 表示未就緒。

---

### 4.6 Diagnostics 端點

#### `GET /diagnostics/store`

| 項目 | 內容 |
|------|------|
| **認證** | 需要 COMPLIANCE、SRE 或 SYSTEM 角色 |
| **用途** | EventStore 內部狀態（防止靜默失敗） |

**Response：**
```json
{
  "store_type": "JsonlEventStore",
  "evidence_dir": "/var/audit/evidence",
  "reload_count": 42,
  "last_reload_at": "2026-05-30T09:55:00Z",
  "last_reload_error": null,
  "files_scanned": 7,
  "events_loaded": 10215,
  "file_positions": { "/var/audit/evidence/audit-2026-05-30.jsonl": 10485760 },
  "per_file_event_counts": { "/var/audit/evidence/audit-2026-05-30.jsonl": 10215 },
  "per_file_errors": {}
}
```

**程式碼**：`src/audit/api/routers/diagnostics.py:38-83`

---

## 5. 服務通訊全貌

### ASCII 架構圖

```
                          ┌────────────────────────────┐
                          │  Console App (React)       │
                          │  port: 3000                │
                          └──────────┬─────────────────┘
                                     │ HTTP/JSON
                                     │ GET /events, /stats, /usage, /evidence
                                     ▼
┌────────────────────────────────────────────────────────────┐
│  xparse-audit API Service (port: 8001)                    │
│                                                           │
│  routers: events | stats | evidence | usage | health      │
│               │                          │                │
│  AuditQueryService              CorrelationEngine         │
│  + RoleBasedAccessControl       (correlation/)            │
│               │                          │ HTTP           │
│  JsonlEventStore                         ▼                │
│  /var/audit/evidence/*.jsonl    Grafana Tempo             │
│                                 http://xparse-tempo:3200  │
│  EvidencePackageStore                                     │
│  SQLite / PostgreSQL / Memory                             │
└────────────────────────────────────────────────────────────┘

━━━━━━━━━━━━ 寫入路徑（SDK，嵌入 bustream / xparse_iam） ━━━━━━━━━━━━

 bustream (Gateway)               xparse_iam (IAM)
  AuditClient                      AuditClient
  sdk/client.py                    sdk/client.py
       │ put() 非阻塞                    │ put() 非阻塞
       ▼                                ▼
  BoundedBuffer                    BoundedBuffer
  HEALTHY / DEGRADED / SATURATED
       │ batch                          │ batch
       ▼                                ▼
  AsyncSinkWriter                  AsyncSinkWriter
       │                                │
       ▼                                ▼
  JsonlSink ──────── append ──────── JsonlSink
                        │
                        ▼
           /var/audit/evidence/audit-YYYY-MM-DD.jsonl
           (共享 Volume，Audit API 讀取)

━━━━━━━━━━━━━━━━ 可觀測性通訊 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  AuditTracer (tracing/tracer.py)
  OTLP/gRPC ──────────────────────► Grafana Tempo :4317

  AuditMetrics (metrics/prometheus_metrics.py)
  /metrics :9090 ◄──────────────── Prometheus scrape

━━━━━━━━━━━━━━━━ 選配 Remote Sink ━━━━━━━━━━━━━━━━━━━━━━━━━━

  HttpAuditSink    ── HTTPS POST ──────────────► 自訂 collector
  ElasticAuditSink ── HTTP Bulk ───────────────► Elasticsearch :9200
  GrpcAuditSink    ── gRPC ────────────────────► gRPC collector
  S3AuditSink      ── HTTPS (boto3) ───────────► AWS S3
```

---

### 通訊連結總表

| 編號 | 通訊對象 | 類型 | 協議 | 方向 | 發起點檔案 | 失敗行為 |
|------|---------|------|------|------|----------|---------|
| C1 | Console App → Audit API | Frontend→Backend | HTTP/JSON | 入站 | `api/routers/*.py` | API 回 4xx/5xx |
| C2 | Audit API → JsonlEventStore | Internal | 本地檔案讀取 | 單向 | `storage/jsonl_event_store.py` | 空結果，fail-open（PRD-041） |
| C3 | Audit API → EvidencePackageStore | Internal | SQLite / PostgreSQL | 雙向 | `evidence/package_store.py` | 降回 memory，LOG warning |
| C4 | Audit API → Tempo | Backend→Backend | HTTP GET | 出站 | `correlation/tempo_client.py` | 空 list，fail-open，`tempo_available=false` |
| C5 | AuditClient → JsonlSink | Internal（SDK） | 本地檔案寫入 | 單向 | `sink/sync_jsonl_sink.py` | 隊列滿→丟棄 + `audit.system.saturated` |
| C6 | AuditClient → HttpSink | Backend→Remote | HTTPS POST | 出站 | `sink/remote/http_sink.py` | 指數退避 3 次，circuit breaker，fail-open |
| C7 | AuditClient → ElasticSink | Backend→Remote | HTTP Bulk | 出站 | `sink/remote/elastic_sink.py` | 指數退避，fail-open |
| C8 | AuditClient → GrpcSink | Backend→Remote | gRPC | 出站 | `sink/remote/grpc_sink.py` | circuit breaker，fail-open |
| C9 | AuditClient → S3Sink | Backend→Remote | HTTPS（boto3） | 出站 | `sink/s3/s3_sink.py` | 指數退避，fail-open |
| C10 | AuditTracer → Tempo | Backend→Observability | OTLP/gRPC | 出站 | `tracing/tracer.py` | 靜默失敗，不影響主流程 |
| C11 | Prometheus → AuditMetrics | Observability→SDK | HTTP scrape | 入站 | `metrics/server.py` | 無影響（只影響監控） |

---

### 每條連線詳細說明

#### C1：Console App → Audit API

| 欄位 | 內容 |
|------|------|
| **Endpoint URL** | `http://${AUDIT_API_HOST}:${AUDIT_API_PORT:-8001}` |
| **Request Headers** | `Content-Type: application/json`、`X-Audit-Role: <role>`、`X-User-ID: <id>` |
| **Request / Response** | 依端點，見 §4 各端點說明 |
| **Timeout** | 無明確設定（前端 fetch 預設） |
| **失敗行為** | API 回 4xx/5xx，Console 顯示錯誤，不重試 |

---

#### C2：Audit API → JsonlEventStore（本地 JSONL 讀取）

| 欄位 | 內容 |
|------|------|
| **路徑** | `${AUDIT_EVIDENCE_DIR:-/var/audit/evidence}/*.jsonl` |
| **機制** | 啟動時掃描目錄，定期 reload，動態重載 |
| **格式** | 每行一個 JSON 事件（AuditEvent 序列化） |
| **失敗行為** | 空結果回傳，LOG error，不拋例外（fail-open per PRD-041） |
| **程式碼** | `src/audit/storage/jsonl_event_store.py` |

---

#### C3：Audit API → EvidencePackageStore

| 欄位 | 內容 |
|------|------|
| **PostgreSQL DSN** | `postgresql://${AUDIT_DB_USER}:${AUDIT_DB_PASSWORD}@${AUDIT_DB_HOST}:${AUDIT_DB_PORT:-5432}/${AUDIT_DB_NAME:-xparse_audit}` |
| **SQLite 路徑** | `${AUDIT_PACKAGE_STORE_PATH:-/tmp/audit/evidence_packages.db}` |
| **用途** | EvidencePackage 中繼資料 CRUD |
| **失敗行為** | PostgreSQL 失敗 → 降回 SQLite；SQLite 失敗 → LOG warning，PackageStore=None（禁用功能） |
| **程式碼** | `src/audit/evidence/package_store.py` |

---

#### C4：Audit API → Grafana Tempo（Sidecar 關聯查詢）

| 欄位 | 內容 |
|------|------|
| **Endpoint URL** | `${TEMPO_QUERY_URL:-http://xparse-tempo:3200}` |
| **健康檢查** | `GET {TEMPO_QUERY_URL}/ready` |
| **搜尋 API** | `GET {TEMPO_QUERY_URL}/api/search?service.name=xparse-otel-sidecar&...` |
| **Trace API** | `GET {TEMPO_QUERY_URL}/api/traces/{trace_id}` |
| **Request Headers** | 無認證（或 `Authorization: Bearer ${TEMPO_AUTH_TOKEN}`） |
| **Timeout** | 10.0 秒（`TempoClient.__init__` 預設） |
| **失敗行為** | 回傳空 list（fail-open），`tempo_available=false`，LOG warning；`health()` 才 raise `TempoUnavailableError` |
| **程式碼** | `src/audit/correlation/tempo_client.py:39-80` |

---

#### C5：AuditClient → JsonlSink（SDK 本地寫入，主路徑）

| 欄位 | 內容 |
|------|------|
| **機制** | 非同步有界隊列 → background worker → append to JSONL file |
| **格式** | `{"event_id": ..., "event_type": ..., ...}\n`（每行一筆） |
| **Timeout** | `put()` 非阻塞，立即回傳 True/False |
| **失敗行為（隊列滿）** | 丟棄事件 + 自動發出 `audit.system.saturated` 退化事件（ADR-010），強制事件不丟棄 |
| **失敗行為（寫入錯誤）** | 指數退避重試，最終 LOG error，不拋到主流程 |
| **程式碼** | `src/audit/sink/sync_jsonl_sink.py`、`src/audit/writer/async_writer.py` |

---

#### C6：HttpAuditSink → 遠端 HTTP Collector

| 欄位 | 內容 |
|------|------|
| **Endpoint URL** | `${AUDIT_HTTP_SINK_ENDPOINT}` |
| **Method** | POST |
| **Request Headers** | `Content-Type: application/json`、`Content-Encoding: gzip`（啟用時）、`X-API-Key: ${AUDIT_HTTP_SINK_API_KEY}` |
| **Request Body** | `{"events": [{...}, ...], "batch_id": "...", "sent_at": "..."}` |
| **Timeout** | `RemoteSinkConfig.timeout_ms`（預設 5000ms） |
| **Retry** | 最多 3 次，指數退避（初始 100ms，最大 10000ms，jitter enabled） |
| **Circuit Breaker** | 5 次失敗開路，2 次成功閉路，30000ms timeout |
| **失敗行為** | circuit open 時立即丟棄，LOG warning，不拋到主流程（fail-open） |
| **程式碼** | `src/audit/sink/remote/http_sink.py:46-453` |

---

#### C10：AuditTracer → Grafana Tempo（OTel OTLP）

| 欄位 | 內容 |
|------|------|
| **Endpoint URL** | `${AUDIT_OTLP_ENDPOINT:-http://xparse-tempo:4317}` |
| **協議** | OTLP/gRPC（預設）或 OTLP/HTTP |
| **Exporter 類型** | `OTLP_GRPC` / `JAEGER` / `NONE`（TracingConfig） |
| **Service Name** | `${AUDIT_TRACING_SERVICE_NAME:-xparse-audit}` |
| **失敗行為** | 靜默失敗，不影響主流程（可觀測性降級） |
| **程式碼** | `src/audit/tracing/tracer.py:1-506` |

---

## 6. 請求主流程

### SDK 寫入路徑（Gateway 呼叫 AuditClient）

```
Gateway 主請求路徑
        │
        │ (非阻塞，不等待)
        ▼
  AuditClient.record(event_type, trace_id, actor, ...)
  sdk/client.py:147
  │
  ├─ 1. 建立 AuditEnvelope（event_id=UUID, occurred_at=now,
  │      payload_hash=SHA256(payload)）
  │      core/domain/audit_envelope.py
  │
  ├─ 2. 建立 AuditEvent（envelope + payload）
  │      core/domain/audit_event.py
  │
  └─ 3. BoundedBuffer.put(event)  ← 非阻塞
         sdk/bounded_buffer.py
         ├─ 隊列 < 80%（HEALTHY）   → 入列 True
         ├─ 隊列 80-100%（DEGRADED）→ 入列 True（+自審計事件）
         └─ 隊列 100%（SATURATED） → 丟棄 + audit.system.saturated

  主請求繼續執行（無等待）

  [背景工作：AsyncSinkWriter — writer/async_writer.py]
  │
  ├─ loop: get_batch(100 events) from BoundedAuditBuffer
  │        buffer/bounded_queue.py
  │
  └─ write_batch(events) → AuditSink.write(event) × N
     └─ JsonlSink（或其他 Sink）
        sink/sync_jsonl_sink.py
        │
        ├─ 序列化事件為 JSONL 行
        ├─ append() → /var/audit/evidence/audit-YYYY-MM-DD.jsonl
        └─ 達到 rotate_size_mb → 滾動新檔
           sink/rotation.py
```

### API 查詢路徑（Console → Audit API）

```
Console App
    │
    │ GET /events/query  [+ X-Audit-Role: compliance]
    ▼
FastAPI Router：events.py:65
    │
    ├─ 1. 認證解析：api/auth.py
    │      parse_role(X-Audit-Role) → AuthContext(role, user_id, ...)
    │
    ├─ 2. 請求驗證：EventQueryRequest（Pydantic）
    │      api/models.py
    │
    ├─ 3. AuditQueryService.query_events(request, auth_context)
    │      access/query.py
    │      ├─ RoleBasedAccessControl.check_access(role, event_type)
    │      │   access/rbac.py → 過濾不可見事件類型
    │      ├─ EventStore.query(filters)
    │      │   storage/jsonl_event_store.py → 掃描 JSONL 回傳匹配事件
    │      └─ _redact_event(event, role) → 依角色遮蔽欄位
    │
    └─ 4. 建立 EventQueryResponse（含分頁）
           api/models.py
    │
    │ 200 OK + JSON
    ▼
Console App（顯示審計列表）
```

### 證據包生成路徑

```
Console App
    │
    │ POST /evidence/packages
    ▼
evidence.py:202
    │
    ├─ 1. 認證：需要 COMPLIANCE 或 SYSTEM 角色
    ├─ 2. 建立 EvidencePackageRecord（status=pending）
    │      evidence/package_store.py
    ├─ 3. 啟動背景 asyncio Task
    └─ 4. 立即回傳 202 Accepted

  [背景 Task]
    │
    ├─ EventStore.query(time_range, filters) → events
    │   storage/jsonl_event_store.py
    │
    ├─ DefaultEvidenceAssembler.assemble(events, scope)
    │   evidence/assembler.py
    │   ├─ 計算 SHA256 雜湊清單
    │   ├─ 建立 EvidenceManifest
    │   └─ 回傳 EvidenceBundle（不可變）
    │
    ├─ EvidenceExporter.export_to_zip(bundle) → ZIP bytes
    │   evidence/exporter.py
    │   └─ manifest.json + audit_events.jsonl + integrity.json
    │
    └─ PackageStore.update(status=ready, size_bytes=...)
       evidence/package_store.py
```

---

## 7. 關鍵類別索引

| 類別名稱 | 檔案 | 職責 |
|---------|------|------|
| `AuditClient` | `sdk/client.py` | SDK 主入口，非阻塞事件寫入 |
| `AuditConfig` | `sdk/config.py` | SDK 配置 dataclass |
| `BoundedBuffer` | `sdk/bounded_buffer.py` | SDK 有界非阻塞隊列（HEALTHY/DEGRADED/SATURATED） |
| `BoundedAuditBuffer` | `buffer/bounded_queue.py` | 非同步有界佇列（背景寫入層） |
| `AsyncSinkWriter` | `writer/async_writer.py` | 背景批次寫入工作 |
| `AuditEvent` | `core/domain/audit_event.py` | 完整審計事件（信封 + 不透明 payload） |
| `AuditEnvelope` | `core/domain/audit_envelope.py` | 不可變事件信封（治理欄位） |
| `Actor` | `core/domain/actor.py` | 誰做的（tenant_id/user_id/app_id，至少一個） |
| `Target` | `core/domain/target.py` | 做了什麼（endpoint/resource_type/resource_id） |
| `ObservabilityPayload` | `core/domain/observability/` | Phase 2A：延遲/Token/Cost/Model 指標 |
| `PolicyDecisionPayload` | `core/domain/governance/` | Phase 2B：策略決定（allow/deny/conditional） |
| `GuardrailPayload` | `core/domain/governance/` | Phase 2B：護欄觸發（safety/compliance/operational） |
| `RetentionConfig` | `core/domain/retention/` | 保留期設定（30/90/14/365 天） |
| `AuditRole` | `core/domain/retention/` | RBAC 角色 enum（SRE/SECURITY/COMPLIANCE/BILLING/APP_OWNER） |
| `LegalHold` | `core/domain/retention/` | 法律保留（覆蓋 retention expiration） |
| `CustodyChain` | `core/domain/custody/` | 證據移交鏈聚合根（ADR-014） |
| `EvidenceBundle` | `core/domain/evidence/` | 不可變證據物件（含完整性證明） |
| `TrailSegment` | `core/domain/compliance/` | Compliance Trail 段落（hash chain） |
| `JsonlEventStore` | `storage/jsonl_event_store.py` | JSONL 事件載入與查詢（API 查詢端） |
| `AuditQueryService` | `access/query.py` | RBAC 整合查詢（角色過濾 + 紅線化） |
| `RoleBasedAccessControl` | `access/rbac.py` | 角色與事件前綴對應表 |
| `DefaultEvidenceAssembler` | `evidence/assembler.py` | 密碼學完整性組裝（SHA256，517 行） |
| `EvidenceExporter` | `evidence/exporter.py` | 組裝 ZIP 匯出（357 行） |
| `EvidencePackageStore` | `evidence/package_store.py` | SQLite/PostgreSQL/Memory 後端（870 行） |
| `FernetVault` | `vault/fernet_vault.py` | Fernet 對稱加密（454 行） |
| `JsonlTrailStorage` | `trail/jsonl_storage.py` | Compliance Trail hash chain 存儲（759 行） |
| `DefaultRetentionPolicy` | `retention/policy.py` | 保留期決策（ADR-006） |
| `AuditMetrics` | `metrics/prometheus_metrics.py` | Prometheus 指標（470 行） |
| `AuditTracer` | `tracing/tracer.py` | OpenTelemetry OTLP（506 行） |
| `CorrelationEngine` | `correlation/engine.py` | Sidecar-Gateway span 關聯（383 行） |
| `TempoClient` | `correlation/tempo_client.py` | Tempo HTTP API 客戶端（459 行） |
| `CircuitBreaker` | `sink/remote/circuit_breaker.py` | CLOSED/OPEN/HALF_OPEN 狀態機（190 行） |
| `HttpAuditSink` | `sink/remote/http_sink.py` | HTTP 批次遠端 Sink（453 行） |
| `ElasticAuditSink` | `sink/remote/elastic_sink.py` | Elasticsearch Sink（669 行） |
| `S3AuditSink` | `sink/s3/s3_sink.py` | AWS S3 Sink（boto3，312 行） |
| `AuthContext` | `api/auth.py` | 請求認證上下文（role/user_id/tenant_id） |
| `RetentionService` | `core/use_cases/retention_service.py` | 保留期業務邏輯（492 行） |
| `CustodyService` | `core/use_cases/custody_service.py` | Chain-of-Custody 業務邏輯（451 行） |

---

## 8. 重要環境變數

### Audit API Service

| 變數名稱 | 預設值 | 說明 |
|---------|--------|------|
| `AUDIT_API_HOST` | `0.0.0.0` | FastAPI 監聽 IP |
| `AUDIT_API_PORT` | `8001` | FastAPI 監聽 Port |
| `AUDIT_LOG_LEVEL` | `INFO` | 日誌等級（`DEBUG`/`INFO`/`WARNING`） |
| `AUDIT_EVIDENCE_DIR` | `/var/audit/evidence` | JSONL 事件檔案目錄（共享卷，必填） |
| `CORS_ORIGINS` | `""` | 逗號分隔的 CORS 允許來源（空=不設） |
| `DEBUG` | `""` | 開發模式（`true`/`1`/`yes`） |

### Evidence Package Store

| 變數名稱 | 預設值 | 說明 |
|---------|--------|------|
| `AUDIT_PACKAGE_STORE_ENGINE` | `sqlite` | 後端引擎：`sqlite` / `postgres` / `memory` |
| `AUDIT_PACKAGE_STORE_PATH` | `/tmp/audit/evidence_packages.db` | SQLite DB 路徑 |
| `AUDIT_PACKAGE_STORE_DSN` | `""` | PostgreSQL 完整 DSN（覆蓋以下個別變數） |
| `AUDIT_DB_HOST` | `""` | PostgreSQL 主機（不設則降回 SQLite） |
| `AUDIT_DB_USER` | `xparse` | PostgreSQL 使用者 |
| `AUDIT_DB_PASSWORD` | `""` | PostgreSQL 密碼 |
| `AUDIT_DB_PORT` | `5432` | PostgreSQL 埠 |
| `AUDIT_DB_NAME` | `xparse_audit` | PostgreSQL 資料庫名稱 |

### Sidecar 關聯

| 變數名稱 | 預設值 | 說明 |
|---------|--------|------|
| `TEMPO_QUERY_URL` | `""` | Tempo HTTP API base URL（空=停用關聯功能） |

### SDK / 可觀測性

| 變數名稱 | 預設值 | 說明 |
|---------|--------|------|
| `AUDIT_OTLP_ENDPOINT` | `http://xparse-tempo:4317` | OTel OTLP 上報端點 |
| `AUDIT_TRACING_SERVICE_NAME` | `xparse-audit` | OTel service.name |

### Observability Stack（`deploy/observability/.env`）

| 變數名稱 | 預設值 | 說明 |
|---------|--------|------|
| `ELASTIC_PASSWORD` | （必須更換） | Elasticsearch superuser 密碼 |
| `KIBANA_SYSTEM_PASSWORD` | （必須更換） | Kibana system 使用者密碼 |
| `AUDIT_SINK_PASSWORD` | （必須更換） | Audit Sink 服務帳戶密碼 |
| `KIBANA_ENCRYPTION_KEY` | （必須更換） | Kibana 存儲物件加密金鑰（32 bytes base64） |
| `GF_SECURITY_ADMIN_PASSWORD` | （必須更換） | Grafana 管理員密碼 |
| `GF_SECURITY_SECRET_KEY` | （必須更換） | Grafana cookie 簽名金鑰（32+ chars） |
| `TEMPO_AUTH_TOKEN` | `""` | Tempo Bearer 認證 Token（選配） |
| `TLS_ENABLED` | `true` | 是否啟用 TLS |
| `ELASTICSEARCH_PORT` | `9200` | ES API Port |
| `KIBANA_PORT` | `5601` | Kibana Web UI Port |
| `GRAFANA_PORT` | `3000` | Grafana Web UI Port（容器外映射為 13000） |
| `TEMPO_API_PORT` | `3200` | Tempo API Port |
| `TEMPO_OTLP_GRPC_PORT` | `4317` | Tempo OTLP gRPC Port |
| `TEMPO_OTLP_HTTP_PORT` | `4318` | Tempo OTLP HTTP Port |
| `PROMETHEUS_PORT` | `9090` | Prometheus Port（容器外映射為 9091） |

---

## 9. 關聯文件索引

### ADR（架構決策記錄）

| ADR | 標題 | 核心不變量 | 影響模組 |
|-----|------|----------|---------|
| ADR-001 | Audit Architecture & Event Model | Append-only，事件不可修改 | Domain, Sink |
| ADR-002 | Audit Schema Versioning Policy | schema_version 必填，向後相容 | Envelope, Config |
| ADR-003 | Trace ID Establishment & Correlation | 無 trace_id = 無效事件 | Correlation, Envelope |
| ADR-004 | Audit Sink & Replay Strategy | Replay 不依賴 Sink 順序 | Sink protocols |
| ADR-005 | Audit Event Type Registry | 未註冊事件不可存在 | EventType domain |
| ADR-006 | Retention Policy | 分層保留期（14/30/90/365 天） | Retention domain |
| ADR-007 | RBAC Access Control | 角色決定可見事件類型 | Access layer |
| ADR-008 | Mandatory Events Coverage | 強制事件不可被設定關閉 | SDK Config, Buffer |
| ADR-009 | Audit Time, Ordering & Causality | Timestamp ≠ Causality | Domain |
| ADR-010 | Audit Write Path & Backpressure | **Audit 絕不阻塞主流程** | SDK, Buffer, Writer |
| ADR-011 | Confidential Vault & Evidence Chain | Audit index 不含敏感明文 | Vault, Content refs |
| ADR-012 | Evidence Export & Disclosure | 匯出證據必有完整性清單 | Evidence domain |
| ADR-013 | Payload Deferral Decision | Payload schemas 在 SPECs，非 ADRs | AuditEvent domain |
| ADR-014 | Chain-of-Custody State Model | Custody 是顯性狀態 | Custody domain |
| ADR-015 | OpenTelemetry & Tempo as Evidence Runtime | 每個審計事件 = OTel span；Tempo = 事實之源 | Tracing, Correlation |

### PRD（產品需求文件）

| PRD | 標題 | Phase | Tier | 狀態 |
|-----|------|-------|------|------|
| PRD-001 | System Integrity | 1 | 0 | 完成 |
| PRD-002 | Trace Lifecycle | 1 | 0 | 完成 |
| PRD-003 | Observability Events | 2A | 1 | 完成 |
| PRD-004 | Governance Events | 2B | 2 | 完成 |
| PRD-005 | Retention & Access | 2C | 2 | 進行中 |
| PRD-006 | Compliance Trail | 3 | 3 | 待定 |
| PRD-007 | Sensitive Data Handling | 3 | 3 | 待定 |
| PRD-008 | Evidence Export | 4 | 4 | 待定 |
| PRD-009 | Chain of Custody | 4 | 4 | 待定 |
| PRD-010 | SDK Integration Testing | — | — | — |
| PRD-011 | API Integration | — | — | — |
| PRD-012 | Observability Backend | — | — | — |

### SPEC（技術規格）

| SPEC | 標題 | 影響模組 |
|------|------|---------|
| SPEC-001 | Observability Event Payload Semantics | `core/domain/observability/` |
| SPEC-002 | Governance Event Payload Semantics | `core/domain/governance/` |
| SPEC-003 | Content Vault Specification（簡版） | `vault/` |
| SPEC-004 | Content Vault Specification（詳版） | `vault/` |
| SPEC-005 | JSONL Storage Invariants | `sink/`、`trail/`、`storage/` |
| SPEC-006 | Elasticsearch Projection Specification | `sink/remote/elastic_sink.py` |

---

## 10. 規模統計

| 模組 | 主要檔案（LOC） | 估計行數 |
|------|--------------|---------|
| **API 層**（`api/`） | main.py (180)、app.py (187)、models.py (382)、routers/events.py (322)、routers/stats.py (743)、routers/evidence.py (473)、routers/usage.py (337)、routers/health.py (155)、routers/diagnostics.py (~80)、auth.py (~100) | **~2,959** |
| **SDK 層**（`sdk/`） | client.py (868)、config.py (91)、bounded_buffer.py (301) | **~1,260** |
| **Buffer / Writer**（`buffer/`、`writer/`） | bounded_queue.py (~120)、async_writer.py (243) | **~363** |
| **Sink 層**（`sink/`） | jsonl_sink.py (189)、sync_jsonl_sink.py (210)、rotation.py (204)、http_sink.py (453)、elastic_sink.py (669)、grpc_sink.py (612)、circuit_breaker.py (190)、retry.py (207)、s3_sink.py (312)、config.py (~90) | **~3,136** |
| **Domain 層**（`core/domain/`） | audit_event.py (58)、audit_envelope.py (~80)、custody_chain.py (461)、trail_segment.py (352)、tier_transition.py (322)、access_grant.py (385)、governance (~200)、observability (~150)、retention (~120)、evidence (~150) | **~2,278** |
| **Ports 層**（`core/ports/`） | trail_storage.py (449)、archive_storage.py (394)、content_vault.py (335)、custody.py (~100)、audit_sink.py (~75)、others (~200) | **~1,553** |
| **Use Cases**（`core/use_cases/`） | retention_service.py (492)、custody_service.py (451) | **~943** |
| **Infrastructure — Storage**（`storage/`） | jsonl_event_store.py (379)、local_storage.py (717)、memory_storage.py (351) | **~1,447** |
| **Infrastructure — Access**（`access/`） | query.py (~250)、rbac.py (~100) | **~350** |
| **Infrastructure — Evidence**（`evidence/`） | assembler.py (517)、exporter.py (357)、package_store.py (870) | **~1,744** |
| **Infrastructure — Trail / Vault / Custody** | jsonl_storage.py (759)、fernet_vault.py (454)、key_provider.py (275)、jsonl_repository.py (260)、trail_emitter.py (230) | **~1,978** |
| **Infrastructure — Retention**（`retention/`） | policy.py (198) | **~198** |
| **Metrics / Tracing**（`metrics/`、`tracing/`） | prometheus_metrics.py (470)、server.py (218)、tracer.py (506)、config.py (~60) | **~1,254** |
| **Correlation**（`correlation/`） | engine.py (383)、tempo_client.py (459)、models.py (~80) | **~922** |
| **其他**（`__init__.py`、小型輔助檔案） | — | **~993** |
| **合計（`src/audit/`）** | 152 個 `.py` 檔案 | **28,380** |

---

### 各層級佔比

| 層級 | 行數 | 佔比 |
|------|------|------|
| Domain + Ports + Use Cases | ~4,774 | 16.8% |
| Infrastructure（Storage 等） | ~5,717 | 20.1% |
| Sink 層 | ~3,136 | 11.0% |
| API 層 | ~2,959 | 10.4% |
| Metrics + Tracing + Correlation | ~2,176 | 7.7% |
| SDK + Buffer + Writer | ~1,623 | 5.7% |
| 其他（init、小型輔助） | ~7,995 | 28.2% |

---

*報告產生日期：2026-05-30 | 基於 xparse-audit 0.7.1 原始碼分析*
