# xparse_scheduler 技術報告

> 生成日期：2026-05-29
> 版本來源：`xparse_scheduler/` 主分支

---

## 1. 是什麼應用

| 屬性 | 說明 |
|------|------|
| **類型** | Backend Microservice |
| **框架** | FastAPI + Uvicorn（Python 3.10+） |
| **協議** | HTTP/1.1 REST（非同步，async/await） |
| **面向對象** | 內部服務（IAM、Fleet、Console 呼叫） |
| **預設端口** | `8030`（`--port` 可覆蓋） |
| **URL 前綴** | `/scheduler` |
| **部署方式** | Docker 容器，透過 PyArmor 混淆後打包進主 Image；與 Gateway、IAM 同容器 |
| **健康檢查** | `GET /healthz`（無前綴） |

`xparse_scheduler` 是 Xparse 平台的**工作負載放置調度器（Workload Placement Scheduler）**，負責在 Fleet 節點群中決定應用程式應部署到哪個節點。它以三階段演算法執行容量檢查→配額驗證→節點選擇，並透過 Fleet API 下發部署命令，最終透過節點心跳中繼回報的方式確認部署完成。

---

## 2. 資料夾結構總覽

```
xparse_scheduler/
├── __init__.py                       # 空，套件標識
├── __main__.py                       # 服務進入點，uvicorn 啟動器
├── app.py                            # FastAPI 應用工廠（create_app / build_production_app）
├── audit.py                          # 審計事件發射（fail-soft）
│
├── api/                              # HTTP 路由層（輸入邊界）
│   ├── __init__.py
│   ├── schemas.py                    # Pydantic 請求／回應 Schema 定義
│   ├── placement_routes.py           # 放置生命週期端點（POST/DELETE/restart）
│   ├── capacity_routes.py            # 容量查詢端點（nodes / groups / tenants）
│   └── node_report_routes.py         # 節點心跳報告接收端點
│
├── application/                      # 應用層（Use Cases）
│   ├── __init__.py
│   ├── protocols.py                  # 依賴倒轉抽象邊界（IAMClient / FleetClient / Stores）
│   ├── dto.py                        # 資料轉移物件（跨層 DTO）
│   ├── request_placement.py          # RequestPlacement Use Case（三階段放置演算法）
│   ├── release_placement.py          # ReleasePlacement Use Case（放置釋放流程）
│   ├── update_node_report.py         # UpdateNodeReport Use Case（心跳更新 + PENDING→ACTIVE）
│   └── query_capacity.py             # QueryCapacity Use Case（容量/配額/用量查詢）
│
├── domain/                           # Domain 層（純業務邏輯，無 I/O）
│   ├── __init__.py
│   ├── value_objects.py              # PlacementStatus / NodeStatus 列舉與狀態機
│   ├── entities.py                   # NodeCapacity / ResourceUsage / PlacementRecord 實體
│   ├── exceptions.py                 # Domain 異常定義（QuotaExceeded、NoAvailableNode 等）
│   └── resource_vector.py            # ResourceVector 五維資源值物件
│
└── infrastructure/                   # 基礎設施層（I/O 實現）
    ├── __init__.py
    ├── memory.py                     # 記憶體內 Store 實現（Phase 1 + 測試用 Stub）
    ├── http_fleet.py                 # 生產用 Fleet HTTP 客戶端
    └── http_iam.py                   # 生產用 IAM HTTP 客戶端
```

**總計**：25 個檔案，4 層清潔架構。

---

## 3. 各模組功能說明

### 3.1 進入點與工廠

| 檔案 | 職責 | 關聯文件 |
|------|------|---------|
| `__main__.py` | Uvicorn 啟動器，接受 `--host`/`--port`/`--log-level` 命令列參數 | — |
| `app.py` | 應用工廠。`create_app()` 供測試注入依賴；`build_production_app()` 讀環境變數，掛載路由，設 `/healthz` | ADR-093 |
| `audit.py` | Fail-soft 審計事件發射，支援 `placement.requested/completed/released/restarted` 四類事件 | ADR-010、SPEC-086 §10 |

### 3.2 API 層

| 檔案 | 職責 | 關聯文件 |
|------|------|---------|
| `schemas.py` | 所有 Pydantic v2 Schema：`PlacementRequestSchema`、`PlacementResponseSchema`、`NodeReportSchema`、`ResourceVectorSchema`、`NodeCapacitySummarySchema` 等 | — |
| `placement_routes.py` | `POST /placements`、`DELETE /placements/{uuid}`、`POST /placements/{uuid}/restart` | ADR-140、ADR-143 |
| `capacity_routes.py` | `GET /capacity/nodes`、`GET /capacity/groups/{uuid}/usage`、`GET /capacity/tenants/{uuid}/usage` | PRD-113 |
| `node_report_routes.py` | `POST /nodes/{node_id}/report`（接收 Fleet 心跳中繼，更新容量與用量） | — |

### 3.3 Application 層

| 檔案 | 職責 | 關聯文件 |
|------|------|---------|
| `protocols.py` | `IAMClient`、`FleetClient`、`PlacementStore`、`UsageStore` 四個 Protocol 抽象，依賴倒轉邊界 | ADR-093 |
| `dto.py` | `PlacementRequest`、`PlacementResult`、`NodeAllocationDTO`、`NodeReport`、`NodeCapacitySummary`、`GroupUsageSummary`、`TenantUsageSummary` | — |
| `request_placement.py` | 三階段放置演算法：資源查詢→配額檢查→節點選擇（`MostRemainingStrategy`）→原子提交；支援 dry-run、passthrough mode、preferred_node_id | ADR-143、FR-5、PRD-113 INV-113-5 |
| `release_placement.py` | 放置釋放五步流程：取得記錄→轉 RELEASING→調派 destroy→刪除用量→轉 RELEASED | ADR-093 |
| `update_node_report.py` | 處理 Fleet 心跳：upsert 節點容量→upsert 用量記錄→將已報告的 PENDING 放置轉 ACTIVE；發射 `placement.completed` 審計事件 | — |
| `query_capacity.py` | 三個只讀查詢方法，聚合 UsageStore 資料計算 total/used/available | — |

### 3.4 Domain 層

| 檔案 | 職責 | 關聯文件 |
|------|------|---------|
| `value_objects.py` | `PlacementStatus`（PENDING/ACTIVE/RELEASING/RELEASED/DRY_RUN_OK）與 `NodeStatus`（ONLINE/OFFLINE/DRAINING）列舉，內含有效轉換映射 | SPEC-100 §5.4 |
| `entities.py` | `NodeCapacity`、`ResourceUsage`、`PlacementRecord` 三個 dataclass 實體；`PlacementRecord.transition_to()` 強制狀態機驗證 | ADR-093 |
| `exceptions.py` | `QuotaExceeded`、`NoAvailableNode`、`PlacementNotFound`、`ResourceProfileNotFound`、`GroupQuotaNotFound`、`InvalidPlacementTransition` | ADR-121 |
| `resource_vector.py` | `ResourceVector` 五維 frozen dataclass（cpu_millicores / memory_mb / disk_mb / gpu_slots / container_count）；支援 `fits()`、`min_ratio()`、算術運算 | — |

### 3.5 Infrastructure 層

| 檔案 | 職責 | 關聯文件 |
|------|------|---------|
| `memory.py` | `InMemoryPlacementStore`、`InMemoryUsageStore`（Phase 1 生產實現）；`StubIAMClient`、`StubFleetClient`（測試用） | — |
| `http_fleet.py` | `HttpFleetClient`：`deploy()` → `POST {fleet_url}/apps/{app_code}/deploy`；`destroy()` Phase 2 待實現 | — |
| `http_iam.py` | `HttpIAMClient`：查詢群組配額、節點分配、資源輪廓、部署計數；fail-fast 策略 | — |

---

## 4. 對外 API 端點完整列表

### 4.1 `POST /scheduler/placements`

| 項目 | 說明 |
|------|------|
| **方法** | `POST` |
| **路徑** | `/scheduler/placements` |
| **用途** | 請求新的工作負載放置，執行三階段容量→配額→節點選擇演算法，並向 Fleet 下發部署命令 |

**Request Headers**

```
Content-Type: application/json
Authorization: Bearer <api_key>   # 由上游 Gateway 驗證，Scheduler 透傳
```

**Request Body**

```json
{
  "application_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "tenant_uuid": "660e8400-e29b-41d4-a716-446655440001",
  "group_uuid": "770e8400-e29b-41d4-a716-446655440002",
  "deploy_config": {
    "app_code": "my-agent-app",
    "image": "registry.example.com/my-app:latest",
    "env": {"KEY": "VALUE"}
  },
  "dry_run": false,
  "preferred_node_id": "node-gpu-01"
}
```

**Response（201 Created）**

```json
{
  "placement_uuid": "880e8400-e29b-41d4-a716-446655440003",
  "node_id": "node-gpu-01",
  "status": "PENDING"
}
```

**錯誤回應**

| HTTP 狀態碼 | 錯誤 | 說明 |
|------------|------|------|
| 400 | `ResourceProfileNotFound` | 找不到應用程式資源輪廓 |
| 400 | `GroupQuotaNotFound` | 群組無配額設定 |
| 400 | `QuotaExceeded` | 超過群組配額 |
| 400 | `NoAvailableNode` | 無可用節點（ADR-121） |

---

### 4.2 `DELETE /scheduler/placements/{placement_uuid}`

| 項目 | 說明 |
|------|------|
| **方法** | `DELETE` |
| **路徑** | `/scheduler/placements/{placement_uuid}` |
| **用途** | 釋放活動中的放置，向 Fleet 下發 destroy 命令，更新狀態為 RELEASED |

**Request Headers**

```
Authorization: Bearer <api_key>
```

**Response（200 OK）**

```json
{
  "placement_uuid": "880e8400-e29b-41d4-a716-446655440003",
  "node_id": "node-gpu-01",
  "status": "RELEASED"
}
```

**錯誤回應**

| HTTP 狀態碼 | 錯誤 | 說明 |
|------------|------|------|
| 404 | `PlacementNotFound` | 指定 UUID 不存在 |
| 409 | `InvalidPlacementTransition` | 放置狀態不允許釋放（如已 RELEASED） |

---

### 4.3 `POST /scheduler/placements/{placement_uuid}/restart`

| 項目 | 說明 |
|------|------|
| **方法** | `POST` |
| **路徑** | `/scheduler/placements/{placement_uuid}/restart` |
| **用途** | 重啟已 RELEASED 的放置，重新向 Fleet 下發 start_workload 命令（ADR-140）；fire-and-forget |

**Request Headers**

```
Content-Type: application/json
Authorization: Bearer <api_key>
```

**Request Body**（可選，傳入新的 deploy_config）

```json
{
  "deploy_config": {
    "app_code": "my-agent-app",
    "image": "registry.example.com/my-app:v2"
  }
}
```

**Response（200 OK）**

```json
{
  "placement_uuid": "880e8400-e29b-41d4-a716-446655440003",
  "node_id": "node-gpu-01",
  "status": "ACTIVE"
}
```

**錯誤回應**

| HTTP 狀態碼 | 錯誤 | 說明 |
|------------|------|------|
| 404 | `PlacementNotFound` | 指定 UUID 不存在 |
| 409 | `InvalidPlacementTransition` | 非 RELEASED 狀態不可重啟 |
| 502 | Fleet 通訊失敗 | Fleet API 呼叫異常 |

---

### 4.4 `GET /scheduler/capacity/nodes`

| 項目 | 說明 |
|------|------|
| **方法** | `GET` |
| **路徑** | `/scheduler/capacity/nodes` |
| **用途** | 列出所有節點的容量摘要（total / used / available 五維向量） |
| **Query Params** | `tenant_uuid`（可選，篩選有活動分配的節點） |

**Response（200 OK）**

```json
[
  {
    "node_id": "node-gpu-01",
    "status": "ONLINE",
    "total": {
      "cpu_millicores": 32000,
      "memory_mb": 131072,
      "disk_mb": 1048576,
      "gpu_slots": 4,
      "container_count": 2147483647
    },
    "used": {
      "cpu_millicores": 8000,
      "memory_mb": 32768,
      "disk_mb": 102400,
      "gpu_slots": 1,
      "container_count": 2
    },
    "available": {
      "cpu_millicores": 24000,
      "memory_mb": 98304,
      "disk_mb": 946176,
      "gpu_slots": 3,
      "container_count": 2147483645
    }
  }
]
```

---

### 4.5 `GET /scheduler/capacity/groups/{group_uuid}/usage`

| 項目 | 說明 |
|------|------|
| **方法** | `GET` |
| **路徑** | `/scheduler/capacity/groups/{group_uuid}/usage` |
| **用途** | 查詢群組的配額用量（配額 vs 實際用量） |

**Response（200 OK）**

```json
{
  "group_uuid": "770e8400-e29b-41d4-a716-446655440002",
  "quota": { "cpu_millicores": 16000, "memory_mb": 65536, "disk_mb": 512000, "gpu_slots": 2, "container_count": 10 },
  "used":  { "cpu_millicores": 4000,  "memory_mb": 16384, "disk_mb": 102400, "gpu_slots": 1, "container_count": 3 },
  "available": { "cpu_millicores": 12000, "memory_mb": 49152, "disk_mb": 409600, "gpu_slots": 1, "container_count": 7 }
}
```

**錯誤回應**

| HTTP 狀態碼 | 說明 |
|------------|------|
| 404 | 群組無配額設定 |

---

### 4.6 `GET /scheduler/capacity/tenants/{tenant_uuid}/usage`

| 項目 | 說明 |
|------|------|
| **方法** | `GET` |
| **路徑** | `/scheduler/capacity/tenants/{tenant_uuid}/usage` |
| **用途** | 查詢租戶的總用量（跨所有節點的分配 vs 實際用量） |

**Response（200 OK）**

```json
{
  "tenant_uuid": "660e8400-e29b-41d4-a716-446655440001",
  "total":     { "cpu_millicores": 64000, "memory_mb": 262144, "disk_mb": 2097152, "gpu_slots": 8, "container_count": 50 },
  "used":      { "cpu_millicores": 12000, "memory_mb": 49152,  "disk_mb": 204800,  "gpu_slots": 2, "container_count": 5 },
  "available": { "cpu_millicores": 52000, "memory_mb": 212992, "disk_mb": 1892352, "gpu_slots": 6, "container_count": 45 }
}
```

**錯誤回應**

| HTTP 狀態碼 | 說明 |
|------------|------|
| 404 | 租戶無節點分配 |

---

### 4.7 `POST /scheduler/nodes/{node_id}/report`

| 項目 | 說明 |
|------|------|
| **方法** | `POST` |
| **路徑** | `/scheduler/nodes/{node_id}/report` |
| **用途** | 接收 Fleet 節點心跳中繼，更新節點容量與應用用量，將 PENDING 放置轉換為 ACTIVE |
| **發起方** | Fleet（透過 `xparse_node_mgr` 代理轉發） |

**Request Body**

```json
{
  "capacity": {
    "cpu_millicores": 32000,
    "memory_mb": 131072,
    "disk_mb": 1048576,
    "gpu_slots": 4,
    "gpu_model": "NVIDIA A100"
  },
  "usage": [
    {
      "application_uuid": "550e8400-e29b-41d4-a716-446655440000",
      "tenant_uuid": "660e8400-e29b-41d4-a716-446655440001",
      "group_uuid": "770e8400-e29b-41d4-a716-446655440002",
      "cpu_used": 4000,
      "memory_used": 16384,
      "disk_used": 51200,
      "gpu_used": 1,
      "container_count": 1
    }
  ],
  "last_heartbeat": "2026-05-29T10:30:00Z"
}
```

**Response（204 No Content）**

---

### 4.8 輔助端點

| 方法 | 路徑 | 說明 |
|------|------|------|
| `GET` | `/healthz` | 健康檢查，回傳 `{"status": "ok"}` |
| `GET` | `/scheduler/docs` | Swagger UI（FastAPI 自動生成） |
| `GET` | `/scheduler/openapi.json` | OpenAPI Schema |

---

## 5. 服務通訊全貌

### 5.1 ASCII 架構圖

```
                    ┌─────────────────────────────────────────────┐
                    │           xparse_scheduler (Port 8030)       │
                    │                                              │
  ┌──────────┐      │  ┌─────────┐   ┌──────────────┐            │
  │  Console │─────▶│  │   API   │──▶│  Application │            │
  │  (React) │ HTTP │  │ Routes  │   │  Use Cases   │            │
  └──────────┘      │  └─────────┘   └──────┬───────┘            │
                    │                        │                    │
  ┌──────────┐      │                 ┌──────▼───────┐            │
  │ Gateway  │─────▶│                 │    Domain    │            │
  │(bustream)│ HTTP │                 │(pure logic)  │            │
  └──────────┘      │                 └──────────────┘            │
                    │                        │                    │
                    │              ┌──────────▼──────────┐        │
                    │              │    Infrastructure    │        │
                    │              │  ┌────────────────┐  │        │
                    └──────────────│  │ InMemoryStores │  │────────┘
                                   │  └────────────────┘  │
                                   │  ┌──────────────┐     │
                                   │  │ HttpIAMClient│     │
                                   │  └──────┬───────┘     │
                                   │         │ HTTP GET     │
                                   │  ┌──────▼───────┐     │
                                   │  │HttpFleetClient│    │
                                   │  └──────┬───────┘     │
                                   └─────────│─────────────┘
                                             │
              ┌──────────────────────────────┴──────────────────────────┐
              │                              │                          │
              ▼  HTTP GET                    ▼  HTTP POST               ▼  HTTP POST
    ┌─────────────────┐            ┌──────────────────┐      ┌─────────────────────┐
    │   xparse_iam    │            │   xparse_fleet   │      │   xparse_fleet      │
    │  (Port 8010)    │            │   (Port 8800)    │      │  /nodes/{id}/report │
    │                 │            │  /apps/{code}/   │      │  ─────────────────▶ │
    │  /iam/internal/ │            │    deploy        │      │  (Fleet → Scheduler)│
    │  group-quotas/  │            └──────────────────┘      └─────────────────────┘
    │  node-alloc/    │
    │  resource-prof/ │
    │  deployment-cnt/│
    └─────────────────┘
```

### 5.2 通訊連結總表

| 對象 | 類型 | 協議 | 方向 | 發起點檔案 | 失敗行為 |
|------|------|------|------|-----------|---------|
| `xparse_iam` | Backend | HTTP/1.1 REST | Scheduler → IAM | `infrastructure/http_iam.py` | Fail-fast（raise `httpx.HTTPStatusError`） |
| `xparse_fleet` | Backend | HTTP/1.1 REST | Scheduler → Fleet | `infrastructure/http_fleet.py` | Fire-and-forget，記錄錯誤但不拋出 |
| `xparse_fleet` (節點心跳) | Backend | HTTP/1.1 REST | Fleet → Scheduler | `api/node_report_routes.py` | 204，即使處理異常也不阻斷 |
| Console / Gateway | Backend | HTTP/1.1 REST | 呼叫方 → Scheduler | `api/placement_routes.py` 等 | 4xx/5xx 標準 HTTP 錯誤 |

### 5.3 每條連線詳細說明

---

#### 5.3.1 Scheduler → IAM：取得群組配額

- **Endpoint URL**：`{IAM_API_URL}/iam/internal/group-quotas/{group_uuid}`
  - 環境變數：`IAM_API_URL`（未在 scheduler 內部顯式宣告，由上層傳入 `HttpIAMClient(iam_url=...)`）
- **方法**：`GET`
- **Request Headers**：（無 Authorization，內部信任網路）
- **Response 範例**：
  ```json
  {
    "cpu_millicores": 16000,
    "memory_mb": 65536,
    "disk_mb": 512000,
    "gpu_slots": 2,
    "container_count": 10
  }
  ```
- **Timeout**：`10.0` 秒（`http_iam.py` hardcode）
- **失敗行為**：`404` → 回傳 `None`；其他錯誤 → raise `httpx.HTTPStatusError`（fail-fast）
- **程式碼位置**：`infrastructure/http_iam.py::HttpIAMClient.get_group_quota()`

---

#### 5.3.2 Scheduler → IAM：取得節點分配

- **Endpoint URL**：`{IAM_API_URL}/iam/internal/node-allocations?tenant={tenant_uuid}`
- **方法**：`GET`
- **Response 範例**：
  ```json
  [
    {
      "node_id": "node-gpu-01",
      "resources": {
        "cpu_millicores": 32000, "memory_mb": 131072,
        "disk_mb": 1048576, "gpu_slots": 4, "container_count": 20
      },
      "status": "ACTIVE"
    }
  ]
  ```
- **Timeout**：`10.0` 秒
- **失敗行為**：Fail-fast（`raise`）
- **程式碼位置**：`infrastructure/http_iam.py::HttpIAMClient.get_node_allocations()`

---

#### 5.3.3 Scheduler → IAM：取得應用資源輪廓

- **Endpoint URL**：`{IAM_API_URL}/iam/internal/resource-profiles/{application_uuid}`
- **方法**：`GET`
- **Response 範例**：
  ```json
  {
    "cpu_millicores": 4000,
    "memory_mb": 16384,
    "disk_mb": 51200,
    "gpu_slots": 1,
    "container_count": 1
  }
  ```
- **Timeout**：`10.0` 秒
- **失敗行為**：`404` → 回傳 `None`（Use Case 中轉為 `ResourceProfileNotFound` 400）；其他 → raise
- **程式碼位置**：`infrastructure/http_iam.py::HttpIAMClient.get_resource_profile()`

---

#### 5.3.4 Scheduler → IAM：取得部署計數

- **Endpoint URL**：`{IAM_API_URL}/iam/internal/deployment-count/{application_uuid}`
- **方法**：`GET`
- **Response 範例**：`{ "count": 2 }`
- **Timeout**：`10.0` 秒
- **失敗行為**：Fail-fast（`raise`）
- **程式碼位置**：`infrastructure/http_iam.py::HttpIAMClient.get_deployment_count()`

---

#### 5.3.5 Scheduler → Fleet：部署應用（deploy）

- **Endpoint URL**：`{FLEET_API_URL}/apps/{app_code}/deploy`
  - 環境變數：`FLEET_API_URL`（預設 `http://localhost:8800/v1/fleet`）
- **方法**：`POST`
- **Request Headers**：
  ```
  Content-Type: application/json
  Authorization: Bearer {FLEET_API_TOKEN}   # 若有設定
  ```
- **Request Body 範例**：
  ```json
  {
    "node_id": "node-gpu-01",
    "application_uuid": "550e8400-e29b-41d4-a716-446655440000",
    "resources": {
      "cpu_millicores": 4000, "memory_mb": 16384,
      "disk_mb": 51200, "gpu_slots": 1, "container_count": 1
    },
    "image": "registry.example.com/my-app:latest",
    "env": { "KEY": "VALUE" }
  }
  ```
- **Timeout**：`10.0` 秒
- **失敗行為**：**Fire-and-forget** — 記錄 warning/error，不拋出例外；放置狀態保持 `PENDING`，等待節點心跳確認（`UpdateNodeReport` 中轉 ACTIVE）
- **程式碼位置**：`infrastructure/http_fleet.py::HttpFleetClient.deploy()`

---

#### 5.3.6 Scheduler → Fleet：銷毀應用（destroy）

- **狀態**：Phase 2 尚未實現，目前僅記錄 log
- **預期 Endpoint**：`{FLEET_API_URL}/apps/{app_code}/destroy`（待補充）
- **程式碼位置**：`infrastructure/http_fleet.py::HttpFleetClient.destroy()`

---

#### 5.3.7 Fleet → Scheduler：節點心跳報告

- **Endpoint URL**：`{SCHEDULER_URL}/scheduler/nodes/{node_id}/report`
- **方法**：`POST`
- **發起方**：Fleet / `xparse_node_mgr` agentd（週期性心跳）
- **Request Body 範例**：
  ```json
  {
    "capacity": {
      "cpu_millicores": 32000, "memory_mb": 131072,
      "disk_mb": 1048576, "gpu_slots": 4, "gpu_model": "NVIDIA A100"
    },
    "usage": [
      {
        "application_uuid": "550e8400-...",
        "tenant_uuid": "660e8400-...",
        "group_uuid": "770e8400-...",
        "cpu_used": 4000, "memory_used": 16384, "disk_used": 51200,
        "gpu_used": 1, "container_count": 1
      }
    ],
    "last_heartbeat": "2026-05-29T10:30:00Z"
  }
  ```
- **Response**：`204 No Content`
- **副作用**：PENDING → ACTIVE 狀態轉換，發射 `placement.completed` 審計事件
- **程式碼位置**：`api/node_report_routes.py`、`application/update_node_report.py`

---

## 6. 請求主流程

### 6.1 放置請求流程（POST /scheduler/placements）

```
Client
  │
  │  POST /scheduler/placements
  ▼
placement_routes.py::create_placement()
  │  解析 PlacementRequestSchema
  │  呼叫 request_placement.execute()
  ▼
application/request_placement.py::RequestPlacement.execute()
  │
  ├─── [Phase 1] 資源查詢
  │      ├── IAMClient.get_resource_profile(application_uuid)
  │      │     └── http_iam.py → GET /iam/internal/resource-profiles/{uuid}
  │      │
  │      ├── IAMClient.get_group_quota(group_uuid)
  │      │     └── http_iam.py → GET /iam/internal/group-quotas/{uuid}
  │      │
  │      ├── IAMClient.get_node_allocations(tenant_uuid)
  │      │     └── http_iam.py → GET /iam/internal/node-allocations?tenant={uuid}
  │      │
  │      └── IAMClient.get_deployment_count(application_uuid)
  │            └── http_iam.py → GET /iam/internal/deployment-count/{uuid}
  │
  ├─── [Phase 2] 配額與容量驗證
  │      ├── 群組配額檢查（UsageStore.sum_by_group() + quota.fits()）
  │      ├── 部署計數限制（PRD-113 INV-113-5）
  │      └── dry_run → 回傳 DRY_RUN_OK，不繼續
  │
  ├─── [Phase 3] 節點選擇
  │      ├── 若有 preferred_node_id → 直接驗證並使用（ADR-143）
  │      └── 否則 → MostRemainingStrategy（選 min_ratio 最大的節點）
  │
  └─── [Phase 4] 原子提交
         ├── PlacementStore.save(record, status=PENDING)
         ├── FleetClient.deploy(node_id, app_uuid, resources, deploy_config)
         │     └── http_fleet.py → POST /apps/{app_code}/deploy（fire-and-forget）
         └── 發射 placement.requested 審計事件（fail-soft）
  │
  ▼
placement_routes.py
  │  回傳 PlacementResponseSchema (201)
  ▼
Client  ←  201 { placement_uuid, node_id, status: "PENDING" }
```

### 6.2 節點心跳確認放置流程（PENDING → ACTIVE）

```
Fleet / Node Agent
  │
  │  POST /scheduler/nodes/{node_id}/report
  ▼
node_report_routes.py::receive_node_report()
  │
  ▼
application/update_node_report.py::UpdateNodeReport.execute()
  │
  ├── UsageStore.upsert_node_capacity(capacity)
  ├── for each usage_entry:
  │     └── UsageStore.upsert_usage(usage)
  └── for each PENDING placement on this node:
        └── PlacementRecord.transition_to(ACTIVE)
              └── 發射 placement.completed 審計事件（fail-soft）
  │
  ▼
204 No Content
```

### 6.3 放置釋放流程（DELETE /scheduler/placements/{uuid}）

```
Client
  │
  ▼
placement_routes.py::release_placement()
  │
  ▼
application/release_placement.py::ReleasePlacement.execute()
  │
  ├── 1. PlacementStore.get(placement_uuid)   # 驗證存在
  ├── 2. transition_to(RELEASING)
  ├── 3. FleetClient.destroy(node_id, app_uuid)   # fire-and-forget（Phase 2 待實現）
  ├── 4. UsageStore.delete_usage(node_id, app_uuid)
  └── 5. transition_to(RELEASED)
        └── 發射 placement.released 審計事件（fail-soft）
  │
  ▼
200 { placement_uuid, node_id, status: "RELEASED" }
```

---

## 7. 關鍵類別索引

| 類別名稱 | 檔案 | 職責 |
|---------|------|------|
| `RequestPlacement` | `application/request_placement.py` | 三階段放置演算法主體，含 MostRemainingStrategy 節點選擇 |
| `ReleasePlacement` | `application/release_placement.py` | 放置釋放五步流程，含狀態機轉換 |
| `UpdateNodeReport` | `application/update_node_report.py` | 節點心跳處理，PENDING→ACTIVE 轉換 |
| `QueryCapacity` | `application/query_capacity.py` | 只讀容量/配額/用量聚合查詢 |
| `PlacementRecord` | `domain/entities.py` | 放置記錄實體，內建 `transition_to()` 狀態機 |
| `ResourceVector` | `domain/resource_vector.py` | 五維資源值物件，支援 `fits()`、`min_ratio()`、算術運算 |
| `NodeCapacity` | `domain/entities.py` | 節點硬體容量實體，含心跳時間與狀態 |
| `ResourceUsage` | `domain/entities.py` | 單應用/單節點資源使用量記錄 |
| `PlacementStatus` | `domain/value_objects.py` | 放置狀態列舉，定義有效轉換映射 |
| `NodeStatus` | `domain/value_objects.py` | 節點狀態列舉（ONLINE / OFFLINE / DRAINING） |
| `HttpIAMClient` | `infrastructure/http_iam.py` | 生產用 IAM HTTP 客戶端，四個查詢方法 |
| `HttpFleetClient` | `infrastructure/http_fleet.py` | 生產用 Fleet HTTP 客戶端，deploy（fire-and-forget） |
| `InMemoryPlacementStore` | `infrastructure/memory.py` | Phase 1 記憶體內放置記錄存儲 |
| `InMemoryUsageStore` | `infrastructure/memory.py` | Phase 1 記憶體內用量存儲，含聚合運算 |
| `StubIAMClient` | `infrastructure/memory.py` | 測試用 IAM Stub，預加載測試資料 |
| `StubFleetClient` | `infrastructure/memory.py` | 測試用 Fleet Stub，記錄呼叫與模擬失敗 |
| `IAMClient` | `application/protocols.py` | IAM 依賴倒轉 Protocol 抽象 |
| `FleetClient` | `application/protocols.py` | Fleet 依賴倒轉 Protocol 抽象 |
| `PlacementStore` | `application/protocols.py` | 放置存儲依賴倒轉 Protocol 抽象 |
| `UsageStore` | `application/protocols.py` | 用量存儲依賴倒轉 Protocol 抽象 |

---

## 8. 重要環境變數

| 變數名稱 | 預設值 | 說明 | 使用位置 |
|---------|--------|------|---------|
| `FLEET_API_URL` | `http://localhost:8800/v1/fleet` | Fleet API 基礎 URL | `app.py`、`api/placement_routes.py` |
| `FLEET_API_TOKEN` | `""` | Fleet API 鑑權 Token | `app.py`、`api/placement_routes.py` |
| `SCHEDULER_MODE` | `""` | 設為 `passthrough` 可跳過三階段檢查（測試/緊急模式） | `application/request_placement.py` |
| `IAM_API_URL` | 無預設（必須傳入） | IAM API 基礎 URL，由 `build_production_app()` 傳入 `HttpIAMClient` | `app.py`（透過建構子） |
| `LOG_LEVEL` | `info` | Uvicorn Log 等級 | `__main__.py` |

> **注意**：`IAM_API_URL` 在 `xparse_scheduler` 內部的 `app.py` 中以 `os.getenv("IAM_API_URL", "http://localhost:8010")` 讀取（依 Docker Compose 設定，生產環境為 `http://127.0.0.1:8010`）。

**Docker 容器層級環境變數**（由 Dockerfile 注入）

| 變數名稱 | 值 | 說明 |
|---------|----|------|
| `GATEWAY_PORT` | `8000` | Gateway 服務端口 |
| `IAM_PORT` | `8010` | IAM 服務端口 |
| `PYTHONPATH` | `/app:/app/3rd/xparse_audit/src` | Python 模組搜尋路徑 |
| `LOG_LEVEL` | `INFO` | 預設 Log 等級 |

---

## 9. 關聯文件索引

### ADR（架構決策記錄）

| ADR 編號 | 標題（推測） | 影響範圍 |
|---------|------------|---------|
| ADR-010 | 審計設計 | `audit.py` — 事件類型定義 |
| ADR-093 | Execution Safety Invariants（5 不變量） | 全模組 — 原子提交、預條件驗證、後條件驗證 |
| ADR-110 | Console-Centric Ingress 代理 | 呼叫鏈入口（Console → Scheduler） |
| ADR-121 | 無可用節點的錯誤回應格式 | `domain/exceptions.py::NoAvailableNode` |
| ADR-140 | 放置重啟端點（restart）設計 | `api/placement_routes.py::restart_placement()` |
| ADR-143 | 偏好節點選擇（preferred_node_id） | `application/request_placement.py` |
| ADR-161 | 部署版本分級 | `deploy_config` 透傳邏輯 |

### PRD（產品需求文件）

| PRD 編號 | 標題（推測） | 影響範圍 |
|---------|------------|---------|
| PRD-041 | OpenTelemetry 審計整合 | `audit.py` fail-soft 實現 |
| PRD-113 | 調度器資源管理（含 INV-113-5 部署計數限制） | `application/request_placement.py` |

### SPEC（規格文件）

| SPEC 編號 | 章節 | 影響範圍 |
|----------|------|---------|
| SPEC-086 | §10 — Fail-soft 審計 | `audit.py` — 不阻斷主流程 |
| SPEC-100 | §5.4 — 無可用節點回應 | `domain/exceptions.py::NoAvailableNode` |

### Functional Requirements

| 需求編號 | 說明 | 影響範圍 |
|---------|------|---------|
| FR-5 | Dry-run 模式支援 | `PlacementRequestSchema.dry_run`、`request_placement.py` |

---

## 10. 規模統計

| 模組 | 主要檔案 | 估計行數 |
|------|---------|---------|
| 進入點與工廠 | `__main__.py`、`app.py`、`audit.py` | ~120 行 |
| API 層 | `schemas.py`、3 個 routes 檔案 | ~300 行 |
| Application 層 | `protocols.py`、`dto.py`、4 個 use case 檔案 | ~400 行 |
| Domain 層 | `value_objects.py`、`entities.py`、`exceptions.py`、`resource_vector.py` | ~250 行 |
| Infrastructure 層 | `memory.py`、`http_fleet.py`、`http_iam.py` | ~350 行 |
| **合計** | **25 個檔案** | **~1,420 行** |

> **架構密度分析**：Domain 層程式碼密度最高（純業務邏輯，無 I/O），Infrastructure 層最薄（抽象後的 I/O 實現）。目前 Phase 1 使用記憶體內儲存，Phase 2 計劃遷移至持久化資料庫（`InMemoryPlacementStore`、`InMemoryUsageStore` 將被替換）。
