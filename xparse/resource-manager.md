# xparse_resource_manager — 端點容量管理服務報告

> 版本：2026-05-29｜依據：SPEC-086、ADR-086、PRD-066

---

## 1. 是什麼應用

| 項目 | 說明 |
|------|------|
| **應用類型** | Backend Service（純後端，無前端界面） |
| **框架** | FastAPI（Python 3.11） + Uvicorn ASGI server |
| **協議** | HTTP/1.1 REST；JSON request/response |
| **面向對象** | Gateway（`bustream/`）及系統管理員（Admin API） |
| **部署方式** | 三段式 Docker image（builder → PyArmor obfuscator → runtime），埠號 `8020` |
| **啟動方式** | `python -m xparse_resource_manager`（`__main__.py` entrypoint） |
| **核心職責** | 管理共享推理端點的並發 slot，透過帶優先權的佇列對 Gateway 的 acquire/release 請求做准入控制（Endpoint Capacity Plane） |

這是 Xparse 四平面架構中的 **Endpoint Capacity Plane**：Gateway 每次發起推理前必須先向此服務 `acquire` 一個 lease，推理結束後 `release`，以防止單一端點被超量并發壓垮。

---

## 2. 資料夾結構總覽

```
xparse_resource_manager/
├── __init__.py                    # 套件聲明（"See ADR-086, PRD-066, SPEC-086"）
├── __main__.py                    # python -m 啟動入口，讀 env 啟動 uvicorn
├── app.py                         # Application factory：create_app() + build_production_app()
├── Dockerfile                     # 三段式 build（builder/obfuscator/runtime）
│
├── api/                           # HTTP 路由層（SPEC-086 §4、§5）
│   ├── __init__.py
│   ├── core.py                    # 核心 API：acquire / release / status 路由
│   ├── admin.py                   # 管理 API：endpoint CRUD 路由
│   └── schemas.py                 # Pydantic request/response schemas（SPEC §4、§5 wire format）
│
├── domain/                        # 純 domain 模型，無 I/O
│   ├── __init__.py
│   ├── lease.py                   # Lease 實體 + LeaseState 狀態機（QUEUED/ACTIVE/RELEASED/EXPIRED/RECLAIMED）
│   └── priority_queue.py          # min-heap 優先佇列（priority ASC, enqueue_ts ASC）
│
├── engine/                        # 容量引擎（slot 計帳 + asyncio 長輪詢）
│   ├── __init__.py
│   ├── capacity_engine.py         # EndpointCapacityEngine：acquire / release / reap；全服務的核心邏輯
│   └── ttl_reaper.py              # TtlReaper：asyncio 背景任務，定期回收過期 lease
│
├── audit/                         # Audit 事件發射（SPEC-086 §10）
│   ├── __init__.py
│   ├── sink.py                    # AuditSink protocol + NoopSink + RecordingSink（測試用）
│   ├── events.py                  # 純函數：建構 5 種 AuditEvent（acquired/released/reclaimed/timeout/full）
│   ├── composite.py               # CompositeSink：fan-out 給多個 sink，各自 fail-soft
│   └── xparse_bridge.py           # XparseAuditSink：適配至 xparse_audit SDK 的橋接器
│
├── client/                        # Gateway 側使用的 HTTP client（SPEC-086 §8）
│   ├── __init__.py
│   ├── resource_client.py         # ResourceManagerClient：acquire / release HTTP 呼叫 + 例外映射
│   ├── endpoint_resolver.py       # EndpointResolver：(provider, model) → endpoint_id 快取查詢
│   └── periodic_refresher.py      # PeriodicRefresher：定期更新 EndpointResolver 快取的背景任務
│
└── observability/                 # Prometheus metrics（ADR-063）
    ├── __init__.py
    └── metrics.py                 # PrometheusSink（事件驅動計數器/直方圖）+ EngineStateCollector（scrape 時讀 gauge）
```

---

## 3. 各模組功能說明

| 模組 | 核心類別 / 函數 | 職責 | 關聯文件 |
|------|----------------|------|----------|
| `app.py` | `create_app()` / `build_production_app()` | 應用工廠：測試版（無 reaper）與生產版（含 reaper + audit + metrics）分離，遵循 Lifespan 管理 | SPEC-086 §12 |
| `__main__.py` | `main()` | uvicorn 啟動入口，讀取三個 env var | SPEC-086 §12.1 |
| `api/core.py` | `acquire` / `release` / `status` | 核心 API 路由，將 HTTP 錯誤碼映射至 SPEC 定義的 typed JSON error body | SPEC-086 §4 |
| `api/admin.py` | `put_endpoint` / `list_endpoints` / `delete_endpoint` | 端點 CRUD；path param 透過 `validate_endpoint_id` 校驗命名規則 | SPEC-086 §5 |
| `api/schemas.py` | `AcquireRequestBody` / `AcquireSuccessResponse` 等 | Pydantic wire-format schemas；單一檔案可完整審查契約 | SPEC-086 §4、§5 |
| `domain/lease.py` | `Lease` / `LeaseState` | Lease 實體 + 顯式狀態機，非法轉換拋 `LeaseTransitionError` | SPEC-086 §7 |
| `domain/priority_queue.py` | `PriorityQueue` / `QueueEntry` | min-heap，排序鍵 `(priority, enqueue_ts, sequence)`，純 domain 無 I/O | SPEC-086 §6、§11.3 |
| `engine/capacity_engine.py` | `EndpointCapacityEngine` | 全服務核心：slot 計帳 + asyncio 長輪詢 acquire + TTL reap + idempotent request_id | SPEC-086 §11.2 |
| `engine/ttl_reaper.py` | `TtlReaper` | asyncio 背景任務，週期呼叫 `reap_all_endpoints()`，建議間隔 `ttl_sec / 4`（最低 5s） | SPEC-086 §7.2 |
| `audit/sink.py` | `AuditSink` / `NoopSink` / `RecordingSink` | Protocol-based sink DI；測試用 `RecordingSink` 方便斷言事件序列 | SPEC-086 §10、ADR-010 |
| `audit/events.py` | `lease_acquired` 等純函數 | 建構 5 種 `AuditEvent`，與 engine 解耦 | SPEC-086 §10 |
| `audit/composite.py` | `CompositeSink` | fan-out 至多個 sink；任一 child 拋例外只記 warning，其餘繼續 | SPEC-086 §10、ADR-010 |
| `audit/xparse_bridge.py` | `XparseAuditSink` | 將 `AuditEvent` 映射至 xparse_audit SDK 的 `record()` 呼叫；完全 fail-soft | SPEC-086 §10.2、ADR-010 |
| `observability/metrics.py` | `PrometheusSink` / `EngineStateCollector` | 事件驅動計數器 + scrape 時讀取 gauge；metric namespace `xparse_resource_manager_*` | ADR-063 |
| `client/resource_client.py` | `ResourceManagerClient` | Gateway 側 HTTP client；acquire 拋類型化例外；release 為 fire-and-forget | SPEC-086 §8 |
| `client/endpoint_resolver.py` | `EndpointResolver` | `(provider, model) → endpoint_id` 快取；fetch 失敗保留舊快取 | SPEC-086 §8.2 |
| `client/periodic_refresher.py` | `PeriodicRefresher` | 定期呼叫 `resolver.refresh()`；例外 fail-soft，保持 loop 存活 | SPEC-086 §8 |

---

## 4. 對外 API 端點完整列表

### 4.1 Core API（SPEC-086 §4）

---

#### `POST /resource/endpoints/{endpoint_id}/acquire`

| 欄位 | 說明 |
|------|------|
| **用途** | 向指定端點申請一個容量 slot（lease）；slot 不足時進入優先佇列等待 |
| **Request Headers** | `Content-Type: application/json` |
| **Path Param** | `endpoint_id`：小寫英數字加連字號，2-64 字元 |

**Request Body：**
```json
{
  "app_id": "app-abc123",
  "tenant_id": "tenant-xyz",
  "request_id": "req-uuid-001",
  "priority": 3,
  "timeout_ms": 30000
}
```

**成功 Response（200）：**
```json
{
  "lease_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "endpoint_id": "openai-gpt-4o",
  "granted_at": "2026-05-29T10:00:00.123Z",
  "ttl_sec": 120,
  "queue_wait_ms": 450
}
```

**錯誤 Response：**
| HTTP 狀態碼 | `error` 欄位 | 觸發條件 |
|-------------|-------------|----------|
| `404` | `endpoint_not_found` | endpoint_id 未在 RM 註冊 |
| `408` | `queue_timeout` | 等待佇列超過 `timeout_ms` |
| `503` | `queue_full` | 佇列深度已達 `max_queue_depth` |

---

#### `POST /resource/endpoints/{endpoint_id}/release`

| 欄位 | 說明 |
|------|------|
| **用途** | 釋放已持有的 lease；觸發佇列下一位晉升 |
| **Request Headers** | `Content-Type: application/json` |

**Request Body：**
```json
{
  "lease_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479"
}
```

**成功 Response（200）：**
```json
{
  "released": true,
  "held_ms": 3520
}
```

**錯誤 Response：**
| HTTP 狀態碼 | `error` 欄位 | 觸發條件 |
|-------------|-------------|----------|
| `404` | `endpoint_not_found` | endpoint_id 未註冊 |
| `404` | `lease_not_found` | lease_id 不存在或已被 TTL 回收 |
| `409` | `lease_already_released` | 此 lease_id 已被釋放（幂等保護） |

---

#### `GET /resource/endpoints/{endpoint_id}/status`

| 欄位 | 說明 |
|------|------|
| **用途** | 查詢端點的即時 slot 使用量與佇列深度快照 |
| **Request Headers** | 無需 body |

**成功 Response（200）：**
```json
{
  "endpoint_id": "openai-gpt-4o",
  "max_concurrent": 10,
  "active_leases": 7,
  "available_slots": 3,
  "queue_depth": 2
}
```

**錯誤 Response：**
| HTTP 狀態碼 | `error` 欄位 | 觸發條件 |
|-------------|-------------|----------|
| `404` | `endpoint_not_found` | endpoint_id 未註冊 |

---

### 4.2 Admin API（SPEC-086 §5）

---

#### `PUT /resource/endpoints/{endpoint_id}`

| 欄位 | 說明 |
|------|------|
| **用途** | 新建或更新端點設定（upsert 語意） |

**Request Body：**
```json
{
  "max_concurrent": 10,
  "max_queue_depth": 50,
  "queue_timeout_sec": 30,
  "lease_ttl_sec": 120,
  "description": "OpenAI GPT-4o production endpoint"
}
```

**成功 Response（200）：**
```json
{
  "endpoint_id": "openai-gpt-4o",
  "max_concurrent": 10,
  "max_queue_depth": 50,
  "queue_timeout_sec": 30,
  "lease_ttl_sec": 120,
  "description": "OpenAI GPT-4o production endpoint"
}
```

**錯誤 Response：**
| HTTP 狀態碼 | `error` 欄位 | 觸發條件 |
|-------------|-------------|----------|
| `422` | `invalid_endpoint_id` | endpoint_id 不符合命名規則（非小寫英數字連字號，或長度超界） |

---

#### `GET /resource/endpoints`

| 欄位 | 說明 |
|------|------|
| **用途** | 列出全部已註冊端點的設定；Gateway `EndpointResolver` 用此 refresh 快取 |

**成功 Response（200）：**
```json
{
  "endpoints": [
    {
      "endpoint_id": "openai-gpt-4o",
      "max_concurrent": 10,
      "max_queue_depth": 50,
      "queue_timeout_sec": 30,
      "lease_ttl_sec": 120,
      "description": "OpenAI GPT-4o production endpoint"
    }
  ]
}
```

---

#### `DELETE /resource/endpoints/{endpoint_id}`

| 欄位 | 說明 |
|------|------|
| **用途** | 刪除端點設定；若仍有 active lease 則拒絕 |

**成功 Response（200）：**
```json
{ "deleted": true }
```

**錯誤 Response：**
| HTTP 狀態碼 | `error` 欄位 | 觸發條件 |
|-------------|-------------|----------|
| `404` | `endpoint_not_found` | endpoint_id 未註冊 |
| `409` | `endpoint_has_active_leases` | 仍有 active lease（含 `active_leases` 數量） |

---

### 4.3 Utility 端點

| 方法 | 路徑 | 用途 | Response |
|------|------|------|----------|
| `GET` | `/healthz` | Liveness / readiness probe（Docker HEALTHCHECK 使用） | `{"status": "ok"}` |
| `GET` | `/metrics` | Prometheus scrape endpoint；無 metrics_registry 時返回 404 | Prometheus text format |

---

## 5. 服務通訊全貌

### 5.1 ASCII 架構圖

```
                         ┌──────────────────────────────────────┐
                         │         xparse_resource_manager       │
                         │              :8020 HTTP                │
                         │                                        │
                         │  ┌──────────┐   ┌──────────────────┐  │
                         │  │ Core API │   │   Admin API      │  │
                         │  │ acquire  │   │ PUT/GET/DELETE   │  │
                         │  │ release  │   │  /resource/      │  │
                         │  │  status  │   │  endpoints       │  │
                         │  └────┬─────┘   └─────────┬────────┘  │
                         │       │                   │            │
                         │  ┌────▼───────────────────▼────────┐  │
                         │  │     EndpointCapacityEngine       │  │
                         │  │  (slot accounting + async queue) │  │
                         │  └──────────────┬───────────────────┘  │
                         │                 │ emit()                │
                         │  ┌──────────────▼───────────────────┐  │
                         │  │         CompositeSink            │  │
                         │  │  ┌─────────────┐ ┌────────────┐  │  │
                         │  │  │PrometheusSink│ │XparseAudit│  │  │
                         │  │  │  /metrics    │ │   Sink     │  │  │
                         │  │  └─────────────┘ └──────┬─────┘  │  │
                         │  └──────────────────────────┼────────┘  │
                         │                             │            │
                         │  ┌──────────────────────────▼────────┐  │
                         │  │       TtlReaper (background)      │  │
                         │  │  every 5s → reap_all_endpoints()  │  │
                         │  └───────────────────────────────────┘  │
                         └──────────────────────────────────────────┘
                                  ▲                        │
            HTTP POST acquire     │                        │ HTTP SDK record()
            HTTP POST release     │                        ▼
   ┌─────────────────────────┐    │           ┌───────────────────────┐
   │      bustream/          │────┘           │   3rd/xparse_audit/   │
   │      Gateway            │                │   Audit Pipeline      │
   │                         │                │   (fail-soft)         │
   │  ResourceManagerClient  │                └───────────────────────┘
   │  EndpointResolver       │
   │  PeriodicRefresher      │
   └─────────────────────────┘
                ▲
   HTTP GET /resource/endpoints (every 60s cache refresh)
                │
   ┌────────────┴────────────┐
   │       Prometheus        │
   │  GET /metrics (scrape)  │
   └─────────────────────────┘
```

---

### 5.2 通訊連結總表

| 對象 | 類型 | 協議 | 方向 | 發起點檔案 | 失敗行為 |
|------|------|------|------|-----------|----------|
| Gateway（bustream） | Backend | HTTP/1.1 REST | Gateway → RM | `client/resource_client.py` | `acquire`：fail-fast（拋 typed exception）；`release`：fire-and-forget（log warning，swallow） |
| Gateway EndpointResolver | Backend | HTTP/1.1 REST GET | Gateway → RM | `client/endpoint_resolver.py` | 網路錯誤保留舊快取，log warning，不中斷 Gateway |
| xparse_audit SDK | Backend | In-process SDK call | RM → Audit | `audit/xparse_bridge.py` | 完全 fail-soft：任何例外被 `except Exception` 吞掉，不影響主路徑 |
| Prometheus | Backend | HTTP/1.1 GET `/metrics` | Prometheus → RM | `app.py:_wire_routes_and_handlers()` | RM 無 registry 時返回 404，Prometheus 側當成 down |
| Docker HEALTHCHECK | Infrastructure | HTTP/1.1 GET `/healthz` | Docker → RM | `Dockerfile` | curl 失敗 → container unhealthy |

---

### 5.3 每條連線詳細說明

---

#### 連線 A：Gateway → RM `acquire`

**用途**：Gateway 在每次推理請求前向 RM 申請容量 slot。

**確切 URL 建構**（`client/resource_client.py:105`）：
```
POST {RESOURCE_MANAGER_BASE_URL}/resource/endpoints/{endpoint_id}/acquire
```
其中 `RESOURCE_MANAGER_BASE_URL` 由 Gateway 構造 `httpx.AsyncClient` 時注入（env var 由 Gateway 管理，非 RM 本體）。

**完整 Request：**
```
POST /resource/endpoints/openai-gpt-4o/acquire HTTP/1.1
Content-Type: application/json

{
  "app_id": "app-abc123",
  "tenant_id": "tenant-xyz",
  "request_id": "req-uuid-001",
  "priority": 3,
  "timeout_ms": 30000
}
```

**完整 Response（200）：**
```json
{
  "lease_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "endpoint_id": "openai-gpt-4o",
  "granted_at": "2026-05-29T10:00:00.123Z",
  "ttl_sec": 120,
  "queue_wait_ms": 450
}
```

**Timeout 設定**：由 `AcquireRequestBody.timeout_ms`（Gateway 端設定）控制，RM 端以 `asyncio.wait_for` 實作（`engine/capacity_engine.py:223`）。連線層 timeout 由 Gateway 的 `httpx.AsyncClient` 設定（RM 不控制）。

**失敗行為（`client/resource_client.py:109`）**：
- `httpx.ConnectError` / `ConnectTimeout` / `ReadTimeout` / `ReadError` → 拋 `ResourceManagerUnavailableError`，Gateway fail-open（跳過 Layer 2 直接執行推理）
- HTTP 408 → `EndpointQueueTimeoutError`
- HTTP 503 → `EndpointQueueFullError`
- HTTP 404 → `EndpointNotFoundError`
- 其他 4xx/5xx → `ResourceManagerUnavailableError`

---

#### 連線 B：Gateway → RM `release`

**確切 URL**（`client/resource_client.py:160`）：
```
POST {base_url}/resource/endpoints/{endpoint_id}/release HTTP/1.1
Content-Type: application/json

{"lease_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479"}
```

**Response（200）：**
```json
{"released": true, "held_ms": 3520}
```

**Timeout 設定**：由 Gateway 的 `httpx.AsyncClient` 控制。

**失敗行為（`client/resource_client.py:164-180`）**：完全 fire-and-forget。任何 `httpx.HTTPError` 或 4xx/5xx 均只 log warning，不拋例外。Gateway 的 `finally` block 不會因此 block。

---

#### 連線 C：Gateway EndpointResolver → RM `GET /resource/endpoints`

**確切 URL**（`client/endpoint_resolver.py:46`）：
```
GET {base_url}/resource/endpoints HTTP/1.1
```

**Response（200）：**
```json
{
  "endpoints": [
    {"endpoint_id": "openai-gpt-4o", "max_concurrent": 10, ...}
  ]
}
```

**Timeout 設定**：由 Gateway 的 `httpx.AsyncClient` 控制。

**觸發方式**：由 `client/periodic_refresher.py` 的背景 asyncio task 每 `interval_sec`（生產預設 60s）呼叫一次 `resolver.refresh()`。

**失敗行為（`client/endpoint_resolver.py:48-68`）**：任何 `httpx.HTTPError`、non-200 狀態碼、malformed body 均 log warning + 保留舊快取，不中斷 Gateway。初始快取為空，未知的 `(provider, model)` 直接返回 `None`（fail-open）。

---

#### 連線 D：RM → xparse_audit SDK

**呼叫位置**（`audit/xparse_bridge.py:41`）：
```python
self._client.record(
    event_type="resource.lease.acquired",
    trace_id="req-uuid-001",
    actor={"tenant_id": "tenant-xyz", "app_id": "app-abc123"},
    target={"resource_type": "endpoint", "resource_id": "openai-gpt-4o"},
    payload={"lease_id": "...", "queue_wait_ms": 450, "ttl_sec": 120}
)
```

**控制開關**：env var `XPARSE_AUDIT_ENABLED`（預設 `false`）。為 `false` 時使用 `NoopSink`，不呼叫 SDK。

**失敗行為**：`XparseAuditSink.emit()` 以 `except Exception` 捕捉全部例外並靜默返回（ADR-010 fail-soft；`audit/xparse_bridge.py:56`）。`CompositeSink` 額外加一層防護（`audit/composite.py:32`）。

**5 種 Audit Event（`audit/events.py`）：**
| event_type | 觸發時機 |
|-----------|---------|
| `resource.lease.acquired` | acquire 成功（slot 立即授予或從佇列晉升） |
| `resource.lease.released` | 正常 release |
| `resource.lease.reclaimed` | TTL reaper 強制回收 |
| `resource.queue.timeout` | acquire 等待超時 |
| `resource.queue.full` | 佇列深度達 max_queue_depth，拒絕入列 |

---

#### 連線 E：Prometheus → RM `GET /metrics`

**確切 URL**：`GET http://<rm-host>:8020/metrics`

**Response**：Prometheus text exposition format（MIME `text/plain; version=0.0.4`）

**Metrics 清單（`observability/metrics.py`）：**
| Metric 名稱 | 類型 | 說明 |
|-------------|------|------|
| `xparse_resource_manager_reclaim_total` | Counter | TTL 強制回收次數，label: `endpoint_id` |
| `xparse_resource_manager_queue_timeout_total` | Counter | acquire 超時次數，label: `endpoint_id` |
| `xparse_resource_manager_queue_full_total` | Counter | 佇列滿而拒絕次數，label: `endpoint_id` |
| `xparse_resource_manager_acquire_wait_seconds` | Histogram | 等待佇列時間（bucket 含 SPEC §6 P99 < 500ms 門檻），label: `endpoint_id`, `priority_band` |
| `xparse_resource_manager_lease_held_seconds` | Histogram | lease 持有時間（release 時觀測），label: `endpoint_id` |
| `xparse_resource_manager_endpoint_active_leases` | Gauge | 當前 active lease 數量（scrape 時讀引擎） |
| `xparse_resource_manager_endpoint_queue_depth` | Gauge | 當前佇列深度 |
| `xparse_resource_manager_endpoint_available_slots` | Gauge | 當前可用 slot 數 |
| `xparse_resource_manager_endpoint_max_concurrent` | Gauge | 設定的最大並發數 |

**priority_band 對應（`observability/metrics.py:36`）：**
| priority 值 | band |
|-------------|------|
| ≤ 0 | `critical` |
| 1–3 | `production` |
| 4–7 | `staging` |
| 8–10 | `standard` |
| > 10 | `dev` |

---

## 6. 請求主流程

```
Gateway 收到推理請求
        │
        ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  EndpointResolver.resolve(provider, model)                                 │
│  client/endpoint_resolver.py:71                                            │
│  → 查 _known_ids 快取，返回 endpoint_id 或 None                            │
└───────────────────────┬────────────────────────────────────────────────────┘
                        │
            ┌───────────▼──────────┐
            │  endpoint_id = None? │
            └───────────┬──────────┘
             是(fail-open)│                    否
                        ▼                      ▼
              跳過 Layer 2，           ┌──────────────────────────────────────┐
              直接推理                 │  ResourceManagerClient.acquire()     │
                                      │  client/resource_client.py:87        │
                                      │  POST /resource/endpoints/{id}/acquire│
                                      └───────────────────┬──────────────────┘
                                                          │
                                              ┌───────────▼───────────┐
                                              │ RM: EndpointCapacity  │
                                              │ Engine.acquire()      │
                                              │ engine/capacity_      │
                                              │ engine.py:152         │
                                              └───────────┬───────────┘
                                                          │
                                          ┌───────────────▼────────────────┐
                                          │  有空 slot?                    │
                                          └───────────────┬────────────────┘
                                           有             │              無
                                           ▼              │              ▼
                                  立即 ACTIVE             │    佇列是否已滿?
                                  lease.activate()        │        │
                                  engine.py:328           │   已滿  │  未滿
                                                          │    ▼   │    ▼
                                                          │  HTTP  │  進入
                                                          │  503   │  PriorityQueue
                                                          │        │  asyncio.wait_for
                                                          │        │  engine.py:223
                                                          │        │
                                                          │        │ 等待 release 促進
                                                          │        │ 或 timeout_ms 超時
                                                          │        ▼
                                                          │   超時 → HTTP 408
                                                          │   晉升 → ACTIVE lease
                                                          │
                                                          ▼
                                          ┌───────────────────────────────────┐
                                          │ Gateway 收到 LeaseGrant            │
                                          │ lease_id + ttl_sec                 │
                                          │ client/resource_client.py:116      │
                                          └───────────────┬───────────────────┘
                                                          │
                                                          ▼
                                              執行推理（呼叫 Provider）
                                                          │
                                                          ▼
                                          ┌───────────────────────────────────┐
                                          │ ResourceManagerClient.release()    │
                                          │ client/resource_client.py:157      │
                                          │ POST /resource/endpoints/{id}/     │
                                          │       release (fire-and-forget)    │
                                          └───────────────┬───────────────────┘
                                                          │
                                                          ▼
                                          RM: engine.release() 觸發
                                          _promote_next_waiter()
                                          engine.py:256
                                                          │
                                                          ▼
                                          TTL Reaper（背景，每 5s）：
                                          reap_all_endpoints()
                                          engine/ttl_reaper.py:49
                                          回收已超過 lease_ttl_sec 的 ACTIVE lease
```

---

## 7. 關鍵類別索引

| 類別名稱 | 檔案 | 職責 |
|---------|------|------|
| `EndpointCapacityEngine` | `engine/capacity_engine.py:132` | 全服務核心：slot 計帳、優先佇列、asyncio 長輪詢、idempotent acquire、TTL reap |
| `TtlReaper` | `engine/ttl_reaper.py:19` | asyncio 背景任務，定期呼叫 engine reap_all_endpoints() |
| `Lease` | `domain/lease.py:33` | capacity lease 實體，5 狀態機（QUEUED/ACTIVE/RELEASED/EXPIRED/RECLAIMED） |
| `PriorityQueue` | `domain/priority_queue.py:30` | min-heap，排序鍵 (priority, enqueue_ts, sequence) |
| `_EndpointState` | `engine/capacity_engine.py:116` | 單一端點的執行時狀態（active_leases、queue、pending、idempotency index、tombstones） |
| `_PendingWaiter` | `engine/capacity_engine.py:107` | 一個等待佇列晉升的 acquire() 呼叫（含 asyncio.Event） |
| `AuditSink` | `audit/sink.py:26` | Protocol interface，供 engine DI |
| `CompositeSink` | `audit/composite.py:23` | fan-out 多個 sink，各自 fail-soft |
| `XparseAuditSink` | `audit/xparse_bridge.py:35` | 將 AuditEvent 橋接到 xparse_audit SDK |
| `PrometheusSink` | `observability/metrics.py:53` | 事件驅動更新 Prometheus counter/histogram |
| `EngineStateCollector` | `observability/metrics.py:118` | 自訂 Prometheus collector，scrape 時讀取 gauge |
| `ResourceManagerClient` | `client/resource_client.py:80` | Gateway 側 HTTP client，acquire/release + 例外映射 |
| `EndpointResolver` | `client/endpoint_resolver.py:32` | (provider, model) → endpoint_id 快取查詢 |
| `PeriodicRefresher` | `client/periodic_refresher.py:39` | 定期 refresh EndpointResolver 快取的背景任務 |
| `EndpointConfig` | `engine/capacity_engine.py:63` | 端點靜態設定（frozen dataclass） |
| `LeaseGrant` | `client/resource_client.py:67` | acquire 成功後 Gateway 收到的 value object |

---

## 8. 重要環境變數

| 變數名稱 | 預設值 | 說明 | 位置 |
|---------|--------|------|------|
| `RESOURCE_MANAGER_HOST` | `0.0.0.0` | uvicorn 綁定 host | `__main__.py:23` / `Dockerfile:70` |
| `RESOURCE_MANAGER_PORT` | `8020` | uvicorn 監聽埠號 | `__main__.py:24` / `Dockerfile:70` |
| `RESOURCE_MANAGER_LOG_LEVEL` | `info` | uvicorn log level（debug/info/warning/error） | `__main__.py:25` / `Dockerfile:70` |
| `XPARSE_AUDIT_ENABLED` | `false` | 是否啟用 xparse_audit SDK 橋接；`true/1/yes` 才啟用 | `app.py:151` |
| `PYTHONPATH` | `/app` | Python module search path（container 內） | `Dockerfile:68` |
| `PYTHONUNBUFFERED` | `1` | 關閉 Python stdout/stderr 緩衝，確保 log 即時輸出 | `Dockerfile:69` |

> **注意**：RM 本身不管理 Gateway 的 `RESOURCE_MANAGER_BASE_URL`（Gateway 側 env var），此 URL 由 bustream/Gateway 的 httpx.AsyncClient 設定。

---

## 9. 關聯文件索引

### ADR（Architecture Decision Records）

| ADR | 說明 | 關係 |
|-----|------|------|
| **ADR-086** | ResourceManager 服務架構決策 | 核心設計決策 |
| **ADR-010** | Audit fail-soft 原則 | `XparseAuditSink` 與 `CompositeSink` 的 fail-soft 依據 |
| **ADR-063** | Prometheus metric namespace 規範（`xparse_resource_manager_*`） | `observability/metrics.py` 命名依據 |

### PRD（Product Requirement Documents）

| PRD | 說明 | 關係 |
|-----|------|------|
| **PRD-066** | Endpoint Capacity Management 功能需求 | 全服務需求源頭 |

### SPEC（Specification Documents）

| SPEC | 章節 | 說明 |
|------|------|------|
| **SPEC-086 §3.1** | endpoint_id 命名規則 | `api/schemas.py:ENDPOINT_ID_REGEX` |
| **SPEC-086 §4** | Core API 契約（acquire/release/status 的 HTTP contract） | `api/core.py`、`api/schemas.py` |
| **SPEC-086 §5** | Admin API 契約（endpoint CRUD） | `api/admin.py`、`api/schemas.py` |
| **SPEC-086 §6** | 優先佇列語意（success criteria：P99 queue wait < 500ms） | `domain/priority_queue.py`、`observability/metrics.py` |
| **SPEC-086 §7** | Lease 生命週期狀態機 | `domain/lease.py` |
| **SPEC-086 §7.2** | TTL reaper 建議間隔 | `engine/ttl_reaper.py` |
| **SPEC-086 §8** | Gateway-side client 契約（fail-open 行為） | `client/resource_client.py`、`client/endpoint_resolver.py` |
| **SPEC-086 §8.2** | endpoint_id naming convention for resolver | `client/endpoint_resolver.py:77` |
| **SPEC-086 §8.4** | Gateway fail-open 條件（RM unreachable 時） | `client/resource_client.py:56` |
| **SPEC-086 §9.2** | Priority band 定義（5 bands） | `observability/metrics.py:36` |
| **SPEC-086 §10** | Audit event domain / naming convention | `audit/events.py`、`audit/sink.py` |
| **SPEC-086 §10.1** | `resource.<sub_domain>.<action>` event 命名 | `audit/events.py` |
| **SPEC-086 §10.2** | AuditEvent → xparse_audit SDK 欄位映射規則 | `audit/xparse_bridge.py` |
| **SPEC-086 §11.2** | EndpointCapacityEngine 契約 | `engine/capacity_engine.py` |
| **SPEC-086 §11.3** | PriorityQueue 語意 | `domain/priority_queue.py` |
| **SPEC-086 §12.1** | 啟動 env var 規格 | `__main__.py` |

---

## 10. 規模統計

| 模組 / 檔案 | 程式碼行數（含空行與注釋） |
|------------|--------------------------|
| `engine/capacity_engine.py` | 418 行 |
| `app.py` | 162 行 |
| `observability/metrics.py` | 163 行 |
| `client/resource_client.py` | 180 行 |
| `domain/lease.py` | 133 行 |
| `api/core.py` | 131 行 |
| `api/schemas.py` | 111 行 |
| `api/admin.py` | 96 行 |
| `client/endpoint_resolver.py` | 80 行 |
| `client/periodic_refresher.py` | 79 行 |
| `audit/events.py` | 69 行 |
| `audit/xparse_bridge.py` | 67 行 |
| `domain/priority_queue.py` | 62 行 |
| `engine/ttl_reaper.py` | 53 行 |
| `audit/sink.py` | 50 行 |
| `audit/composite.py` | 40 行 |
| `__main__.py` | 30 行 |
| **合計** | **約 1,924 行**（不含 `__init__.py` 空檔與 `Dockerfile`） |

**模組分佈：**

| 子模組 | 行數 | 佔比 |
|--------|------|------|
| `engine/` | 471 行 | 24% |
| `client/` | 339 行 | 18% |
| `observability/` | 163 行 | 8% |
| `api/` | 338 行 | 18% |
| `audit/` | 226 行 | 12% |
| `domain/` | 195 行 | 10% |
| 根目錄（`app.py`、`__main__.py`） | 192 行 | 10% |
