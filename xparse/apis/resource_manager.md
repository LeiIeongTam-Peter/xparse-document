# Resource Manager 技術文件

> **服務定位**：`xparse_resource_manager` 是 Xparse 平台的**共享端點容量守衛（Shared Endpoint Capacity Guard）**。
> 它以優先隊列與租賃（Lease）狀態機為核心，確保多租戶請求在有限並發容量下有序執行，防止 LLM Provider 端點過載。
>
> **呼叫關係**：Resource Manager 是純後端服務，**不開放給前端直接呼叫**。
> 唯一外部呼叫方為 Gateway（`bustream/`），透過 `ResourceManagerClient` 發起請求。
>
> **Source of Truth**：`xparse_resource_manager/` 程式碼 + 本文件

---

## 一、服務端口清單（Service Ports）

| 服務名稱 | 端口號碼 | 通訊協定 | 用途說明 |
|---------|---------|---------|---------|
| Resource Manager API | `8020` | HTTP | 核心 REST API，處理租賃申請（acquire）、釋放（release）、狀態查詢（status）以及端點 CRUD 管理 |
| Resource Manager Metrics | `8020` | HTTP | Prometheus metrics scrape，路徑 `/metrics`，與 API 共用同一端口 |
| Resource Manager Health | `8020` | HTTP | 健康檢查端點，路徑 `/healthz`，與 API 共用同一端口 |

> **環境變數覆寫**：
> - `RESOURCE_MANAGER_HOST`（預設 `0.0.0.0`）
> - `RESOURCE_MANAGER_PORT`（預設 `8020`）
> - `RESOURCE_MANAGER_LOG_LEVEL`（預設 `info`）

---

## 二、前端 API 清單（Frontend APIs）

> **Resource Manager 不對前端（Console App）開放任何 API。**
> Console App 透過 IAM API 間接了解端點資源狀態，但不直接與 Resource Manager 溝通。

*本節無條目。*

---

## 三、後端 API 清單（Backend APIs）

Resource Manager 提供兩類路由：**核心容量管理（Core）** 與 **端點行政管理（Admin）**，加上基礎設施端點。

### 3.1 核心容量 API（Core Capacity API）

路由前綴：`/resource/endpoints/{endpoint_id}/`

| HTTP 方法 | 端點路徑 | 功能說明 | 呼叫來源 |
|----------|---------|---------|---------|
| `POST` | `/resource/endpoints/{endpoint_id}/acquire` | 申請端點容量租賃。若有空閒 slot 立即授予；若 slot 滿則進入優先隊列長輪詢等待，直到逾時或有空缺。回傳 `lease_id`、`granted_at`（ISO-8601）、`ttl_sec`、`queue_wait_ms` | Gateway（`ResourceManagerClient.acquire()`） |
| `POST` | `/resource/endpoints/{endpoint_id}/release` | 釋放已持有的租賃。以 fire-and-forget 方式呼叫，Gateway 不等待回應。回傳 `released: bool`、`held_ms` | Gateway（`ResourceManagerClient.release()`） |
| `GET` | `/resource/endpoints/{endpoint_id}/status` | 查詢端點即時容量狀態。回傳 `max_concurrent`、`active_leases`、`available_slots`、`queue_depth` | Gateway（監控用途） |

**acquire 錯誤碼對應表**：

| HTTP 狀態碼 | `error` 欄位 | 觸發情境 |
|------------|------------|---------|
| `404` | `endpoint_not_found` | `endpoint_id` 未在引擎中註冊 |
| `408` | `queue_timeout` | 請求在隊列中等待超過 `queue_timeout_sec` |
| `503` | `queue_full` | 隊列深度已達 `max_queue_depth` 上限 |

**release 錯誤碼對應表**：

| HTTP 狀態碼 | `error` 欄位 | 觸發情境 |
|------------|------------|---------|
| `404` | `lease_not_found` | `lease_id` 不存在或已過期 |
| `409` | `lease_already_released` | 租賃已被釋放（重複 release） |

---

### 3.2 端點行政 API（Admin Endpoint API）

路由前綴：`/resource/endpoints/`

| HTTP 方法 | 端點路徑 | 功能說明 | 呼叫來源 |
|----------|---------|---------|---------|
| `PUT` | `/resource/endpoints/{endpoint_id}` | 註冊或更新端點設定。若端點不存在則新建，已存在則更新容量參數。Request body：`max_concurrent`、`max_queue_depth`、`queue_timeout_sec`、`lease_ttl_sec`、`description` | 部署腳本 / IAM 服務初始化 |
| `GET` | `/resource/endpoints` | 列出所有已註冊的端點及其設定。回傳 `endpoints: list[EndpointResource]`。Gateway 的 `EndpointResolver` 每 60 秒定期呼叫此端點更新本地快取 | Gateway（`EndpointResolver.refresh()`）/ 運維工具 |
| `DELETE` | `/resource/endpoints/{endpoint_id}` | 刪除端點及其所有進行中的租賃。回傳 `deleted: bool` | 運維工具 / 部署腳本 |

**EndpointResource 欄位說明**：

| 欄位 | 型別 | 說明 |
|-----|-----|-----|
| `endpoint_id` | `string` | 端點唯一識別碼，格式：`^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$` |
| `max_concurrent` | `int` | 最大並發租賃數（active slots 上限） |
| `max_queue_depth` | `int` | 隊列最大容納請求數 |
| `queue_timeout_sec` | `int` | 請求在隊列中等待的最長秒數 |
| `lease_ttl_sec` | `int` | 租賃存活時間（TTL Reaper 每 5 秒掃描過期租賃） |
| `description` | `string` | 端點描述（自由文字） |

---

### 3.3 基礎設施端點（Infrastructure）

| HTTP 方法 | 端點路徑 | 功能說明 | 呼叫來源 |
|----------|---------|---------|---------|
| `GET` | `/healthz` | 健康檢查。回傳 `{"status": "ok"}`，HTTP 200 | Docker HEALTHCHECK / Load Balancer |
| `GET` | `/metrics` | Prometheus metrics scrape（text format）。包含計數器、直方圖、gauge 指標 | Prometheus scraper |

**主要 Prometheus 指標**（命名空間：`xparse_resource_manager_*`）：

| 指標名稱 | 類型 | 說明 |
|---------|-----|-----|
| `xparse_resource_manager_leases_acquired_total` | Counter | 成功獲取租賃總次數（依 `endpoint_id` 分類） |
| `xparse_resource_manager_leases_released_total` | Counter | 成功釋放租賃總次數 |
| `xparse_resource_manager_leases_reclaimed_total` | Counter | TTL 過期被強制回收的租賃次數 |
| `xparse_resource_manager_queue_timeout_total` | Counter | 隊列等待逾時次數 |
| `xparse_resource_manager_queue_full_total` | Counter | 隊列已滿拒絕請求次數 |
| `xparse_resource_manager_queue_wait_ms` | Histogram | 租賃在隊列中的等待時間分佈（毫秒） |
| `xparse_resource_manager_active_leases` | Gauge | 各端點當前 active lease 數量 |
| `xparse_resource_manager_available_slots` | Gauge | 各端點當前可用 slot 數量 |
| `xparse_resource_manager_queue_depth` | Gauge | 各端點當前隊列深度 |

---

## 四、工作流程（Workflows）

### 4.1 請求容量獲取流程（Acquire Lease）

**發起方**：Gateway（每個進入 StreamingManager 的 LLM 請求）

**場景 A：有空閒 Slot（即時授予）**

```
Client
  │ HTTP 請求
  ▼
Gateway (bustream/)
  │ ResourceManagerClient.acquire(endpoint_id, app_id, tenant_id, request_id, priority, timeout_ms)
  │ POST /resource/endpoints/{endpoint_id}/acquire
  ▼
Resource Manager API (api/core.py)
  │ 查找 EndpointCapacityEngine 對應 endpoint_id
  ▼
EndpointCapacityEngine (engine/capacity_engine.py)
  │ active_leases < max_concurrent ?
  │ → YES: 建立 Lease（QUEUED → ACTIVE），queue_wait_ms = 0
  ▼
Resource Manager API
  │ 回傳 AcquireSuccessResponse { lease_id, granted_at, ttl_sec, queue_wait_ms: 0 }
  ▼
Gateway
  │ 持有 lease_id，繼續 LLM Provider 請求
```

**場景 B：Slot 滿，進入隊列等待**

```
Client
  │ HTTP 請求
  ▼
Gateway
  │ POST /resource/endpoints/{endpoint_id}/acquire
  ▼
Resource Manager API
  ▼
EndpointCapacityEngine
  │ active_leases >= max_concurrent
  │ queue_depth < max_queue_depth ?
  │ → YES: 建立 Lease（QUEUED），加入優先隊列（priority, enqueue_ts）
  │        asyncio.Future 掛起，等待 slot 釋放
  │        等待期間：TTL Reaper 背景掃描 → 若有 TTL 過期租賃，強制回收 → 喚醒隊列
  │
  │ 有 slot 釋放（release 或 TTL 過期）
  │ → QUEUED → ACTIVE，resolve Future
  │ 計算 queue_wait_ms
  ▼
Resource Manager API
  │ 回傳 AcquireSuccessResponse { lease_id, granted_at, ttl_sec, queue_wait_ms: N }
  ▼
Gateway
  │ 持有 lease_id，繼續 LLM Provider 請求
```

**場景 C：隊列已滿（拒絕）**

```
Gateway
  │ POST /resource/endpoints/{endpoint_id}/acquire
  ▼
EndpointCapacityEngine
  │ queue_depth >= max_queue_depth
  │ → 拋出 503 queue_full
  ▼
Gateway
  │ ResourceManagerClient 捕獲 EndpointQueueFullError
  │ fail-open（SPEC §8.4）：記錄 audit 事件，繼續請求（不阻擋）
```

---

### 4.2 租賃釋放流程（Release Lease）

**發起方**：Gateway（LLM Provider 請求完成後）

```
Gateway (StreamingManager)
  │ LLM 請求完成（成功 / 失敗 / 超時）
  │ ResourceManagerClient.release(endpoint_id, lease_id)  ← fire-and-forget
  │ POST /resource/endpoints/{endpoint_id}/release
  ▼
Resource Manager API (api/core.py)
  ▼
EndpointCapacityEngine
  │ Lease 狀態 ACTIVE → RELEASED
  │ active_leases -= 1
  │ 有隊列中等待的 Lease？
  │ → YES: 取出最高優先級請求（min priority, min enqueue_ts）
  │         QUEUED → ACTIVE，resolve Future，queue_wait_ms 計算
  ▼
Resource Manager API
  │ 回傳 ReleaseSuccessResponse { released: true, held_ms: N }
  ▼
Audit Sink（CompositeSink）
  ├── PrometheusSink：更新 leases_released_total、active_leases gauge
  └── XparseAuditSink（若 XPARSE_AUDIT_ENABLED=true）：寫入 audit 事件
```

---

### 4.3 TTL 過期回收流程（TTL Reaper）

**發起方**：Resource Manager 內部背景任務（每 5 秒執行一次）

```
TTLReaper (engine/ttl_reaper.py)
  │ asyncio 背景 Task，間隔 DEFAULT_REAPER_INTERVAL_SEC = 5.0 秒
  ▼
EndpointCapacityEngine.reap_all_endpoints()
  │ 遍歷所有已註冊端點
  │ 對每個端點：掃描 active_leases
  │   current_time > lease.granted_at + lease_ttl_sec ?
  │   → YES: Lease 狀態 ACTIVE → EXPIRED（RECLAIMED）
  │           active_leases -= 1
  │           嘗試喚醒隊列中等待的請求
  ▼
Audit Sink
  ├── PrometheusSink：更新 leases_reclaimed_total、active_leases gauge
  └── XparseAuditSink：寫入 lease_reclaimed audit 事件（含 held_ms、reason: ttl_expired）
```

---

### 4.4 端點清單定期更新流程（Endpoint Cache Refresh）

**發起方**：Gateway 內部背景任務（`PeriodicRefresher`，每 60 秒執行一次）

```
PeriodicRefresher (client/periodic_refresher.py)
  │ asyncio 背景 Task，間隔 60 秒
  ▼
EndpointResolver.refresh()
  │ GET /resource/endpoints
  ▼
Resource Manager API (api/admin.py)
  │ 回傳 EndpointListResponse { endpoints: [...] }
  ▼
EndpointResolver
  │ 更新本地快取 _known_ids: set[str]
  │ 失敗時：保留既有快取（never raises），靜默記錄 warning
  ▼
Gateway（後續請求）
  │ EndpointResolver.resolve(provider, model)
  │ 查找 f"{provider.lower()}-{model.lower()}" 是否在 _known_ids 中
  │ → 找到：回傳 endpoint_id，Gateway 繼續 acquire
  │ → 找不到：回傳 None，Gateway 跳過容量管控（fail-open）
```

---

### 4.5 端點註冊流程（Endpoint Registration）

**發起方**：部署腳本 / IAM 服務初始化 / 運維人員

```
部署腳本 / Admin 工具
  │ PUT /resource/endpoints/{endpoint_id}
  │ Body: { max_concurrent, max_queue_depth, queue_timeout_sec, lease_ttl_sec, description }
  ▼
Resource Manager API (api/admin.py)
  │ 驗證 endpoint_id 格式（正則：^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$）
  │ 驗證 EndpointUpsertRequest（Pydantic schema）
  ▼
EndpointCapacityEngine
  │ 端點不存在：建立新的 EndpointConfig + PriorityQueue + active_leases dict
  │ 端點已存在：更新 EndpointConfig（保留進行中的租賃）
  ▼
Resource Manager API
  │ 回傳 EndpointResource（完整設定）
  ▼
Gateway（下次 PeriodicRefresher 觸發時）
  │ 自動感知到新端點（GET /resource/endpoints 回傳更新後的清單）
```

---

## 附錄：Request / Response Schema 速查

### AcquireRequest（POST /acquire body）

```json
{
  "app_id": "string",
  "tenant_id": "string",
  "request_id": "string",
  "priority": 0,
  "timeout_ms": 30000
}
```

> `priority`：數值越小優先級越高（min-heap）；`timeout_ms`：隊列等待逾時，預設由 `queue_timeout_sec` 決定。

### AcquireSuccessResponse

```json
{
  "lease_id": "uuid-string",
  "granted_at": "2026-05-31T12:00:00.000Z",
  "ttl_sec": 120,
  "queue_wait_ms": 0
}
```

### ReleaseRequest（POST /release body）

```json
{
  "lease_id": "uuid-string"
}
```

### StatusResponse（GET /status）

```json
{
  "endpoint_id": "openai-gpt4o",
  "max_concurrent": 10,
  "active_leases": 3,
  "available_slots": 7,
  "queue_depth": 0
}
```

### EndpointUpsertRequest（PUT /endpoints/{id} body）

```json
{
  "max_concurrent": 10,
  "max_queue_depth": 50,
  "queue_timeout_sec": 30,
  "lease_ttl_sec": 120,
  "description": "OpenAI GPT-4o shared endpoint"
}
```

### Lease 狀態機

```
QUEUED ──────────────────────────────────── → EXPIRED（queue_timeout_sec 內無 slot）
  │
  │ slot 釋放 / TTL 回收觸發
  ▼
ACTIVE ──────────────────────────────────── → RECLAIMED（TTL Reaper 強制回收）
  │
  │ Gateway 呼叫 release
  ▼
RELEASED
```
