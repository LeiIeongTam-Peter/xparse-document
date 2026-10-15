# Xparse Scheduler 技術文件

> **服務定位**：Scheduler 是資源配額排程服務，負責在 Tenant/Group 配額約束下，將 Application 佈署請求分配到最佳可用節點，並維護 Placement 生命週期狀態機。

---

## 一、服務端口清單（Service Ports）

| 服務名稱 | 端口號碼 | 通訊協定 | 用途說明 |
|----------|---------|---------|---------|
| `xparse-scheduler` | **8030** | HTTP | Scheduler API 主服務（Placement / Capacity / Node Report） |
| `xparse-iam` | **8010** | HTTP | IAM 內部 API（Scheduler 查詢配額、資源設定檔、節點分配） |
| `xparse-fleet` | **8090** | HTTP | Fleet API（Scheduler 派送 deploy / destroy / start_workload 指令） |
| `xparse-gateway` | **8000** | HTTP | API Gateway（入口，轉發請求至 IAM；不直接與 Scheduler 通訊） |

> **環境變數參考**：
> - `FLEET_API_URL`：預設 `http://xparse-fleet:8090/v1/fleet`
> - `SCHEDULER_API_URL`：預設 `http://xparse-scheduler:8030`（由 IAM 使用）

---

## 二、前端 API 清單（Frontend APIs）

前端 Console App 透過 IAM 代理或直接呼叫 Scheduler 取得容量資訊。

| HTTP 方法 | 端點路徑 | 目標服務 | 功能說明 |
|-----------|---------|---------|---------|
| `GET` | `/scheduler/capacity/nodes` | xparse-scheduler | 取得所有節點容量摘要，可選傳 `?tenant_uuid=<uuid>` 篩選 |
| `GET` | `/scheduler/capacity/nodes?tenant_uuid={uuid}` | xparse-scheduler | 取得特定 Tenant 可用節點容量清單 |
| `GET` | `/scheduler/capacity/groups/{group_uuid}/usage` | xparse-scheduler | 取得指定 Group 的資源配額使用摘要（quota / used / available） |
| `GET` | `/scheduler/capacity/tenants/{tenant_uuid}/usage` | xparse-scheduler | 取得指定 Tenant 跨節點資源使用摘要（total / used / available） |

> 以上端點供 Console 的「資源容量」儀表板使用，回應包含 5 維資源向量（CPU、Memory、Disk、GPU、Container Count）。

---

## 三、後端 API 清單（Backend APIs）

### 3.1 Scheduler 對外公開 API

#### Placement 端點（`/scheduler`）

| HTTP 方法 | 端點路徑 | 功能說明 | 呼叫來源 |
|-----------|---------|---------|---------|
| `POST` | `/scheduler/placements` | 請求新 Placement（含三重檢查：Group 配額 → 節點選擇 → Atomic Commit）| IAM（Application 部署流程） |
| `DELETE` | `/scheduler/placements/{placement_uuid}` | 釋放 Placement（ACTIVE → RELEASING → RELEASED，並觸發 Fleet destroy）| IAM（Application 停止流程） |
| `POST` | `/scheduler/placements/{placement_uuid}/restart` | 重啟已釋放的 Placement（僅 RELEASED 狀態可重啟，透過 Fleet `start_workload`）| IAM（Application 重啟流程） |

**POST /scheduler/placements 請求欄位：**

| 欄位 | 型別 | 說明 |
|------|------|------|
| `application_uuid` | string (UUID) | 要部署的 Application UUID |
| `tenant_uuid` | string (UUID) | 所屬 Tenant UUID |
| `group_uuid` | string (UUID) | 所屬 Group UUID（用於配額檢查） |
| `deploy_config` | object \| null | 傳遞給 Fleet 的部署設定（含 `app_code`、image、env 等） |
| `dry_run` | boolean | `true` 時僅驗證，不實際建立 Placement |
| `preferred_node_id` | string \| null | 指定優先節點（ADR-143），若節點不可用則 fail-fast |

**HTTP 狀態碼：**

| 狀態碼 | 情境 |
|-------|-----|
| 201 | Placement 建立成功 |
| 400 | 資源設定檔不存在 / Group 配額不存在 / 配額超限 / 無可用節點 |
| 404 | Placement UUID 不存在（DELETE） |
| 409 | 狀態機轉換非法（例如對 ACTIVE Placement 執行 restart） |
| 502 | Fleet 指令失敗（restart 時） |

#### Capacity 端點（`/scheduler/capacity`）

| HTTP 方法 | 端點路徑 | 功能說明 | 呼叫來源 |
|-----------|---------|---------|---------|
| `GET` | `/scheduler/capacity/nodes` | 列出所有節點容量（可選 `?tenant_uuid` 篩選）| 前端 Console |
| `GET` | `/scheduler/capacity/groups/{group_uuid}/usage` | 取得 Group 層級使用摘要 | 前端 Console |
| `GET` | `/scheduler/capacity/tenants/{tenant_uuid}/usage` | 取得 Tenant 層級使用摘要 | 前端 Console |

#### 節點回報端點（`/scheduler/nodes`）

| HTTP 方法 | 端點路徑 | 功能說明 | 呼叫來源 |
|-----------|---------|---------|---------|
| `POST` | `/scheduler/nodes/{node_id}/report` | 接收 Fleet 轉發的節點心跳（更新節點容量 + per-app 使用量 + PENDING → ACTIVE 轉換）| Fleet（心跳轉發） |

#### 系統端點

| HTTP 方法 | 端點路徑 | 功能說明 | 呼叫來源 |
|-----------|---------|---------|---------|
| `GET` | `/healthz` | 健康檢查（回傳 `{"status": "ok"}`）| 容器健康探針 / 維運監控 |
| `GET` | `/scheduler/docs` | Swagger UI（互動式 API 文件）| 開發者 |
| `GET` | `/scheduler/openapi.json` | OpenAPI 規格（JSON 格式）| 開發工具 |

---

### 3.2 Scheduler 呼叫的外部 API

#### Scheduler → IAM（`HttpIAMClient`）

| HTTP 方法 | 端點路徑 | 所屬服務 | 功能說明 |
|-----------|---------|---------|---------|
| `GET` | `/iam/internal/group-quotas/{group_uuid}` | xparse-iam | 取得 Group 資源配額（ResourceVector） |
| `GET` | `/iam/internal/node-allocations?tenant={uuid}` | xparse-iam | 取得 Tenant 的節點分配清單（含每節點可分配上限） |
| `GET` | `/iam/internal/resource-profiles/{application_uuid}` | xparse-iam | 取得 Application 資源需求設定檔 |
| `GET` | `/iam/internal/deployment-count/{application_uuid}` | xparse-iam | 取得 Application 目前活躍部署數（PRD-113 INV-113-5 容量限制） |

#### Scheduler → Fleet（`HttpFleetClient`）

| HTTP 方法 | 端點路徑 | 所屬服務 | 功能說明 |
|-----------|---------|---------|---------|
| `POST` | `/v1/fleet/apps/{app_code}/deploy` | xparse-fleet | 派送 deploy 指令（fire-and-forget，無 deploy_config 時略過） |
| `POST` | `/v1/fleet/commands` | xparse-fleet | 派送 `start_workload` 指令（用於 restart 流程，ADR-140） |

> Fleet destroy 端點目前為 Phase 1 stub，尚未實作（`HttpFleetClient.destroy` 僅 log）。

---

## 四、工作流程（Workflows）

### 4.1 Application Placement（部署請求流程）

**發起方**：IAM（處理 Console 的 Application 部署操作）

```
Console ──POST /iam/...──► IAM
                            │
                            ├──GET /iam/internal/resource-profiles/{app_uuid}──► IAM DB
                            │   (取得 Application 資源需求設定檔)
                            │
                            ├──GET /iam/internal/deployment-count/{app_uuid}──► IAM DB
                            │   (INV-113-5: 檢查部署數量上限)
                            │
                            ├──POST /scheduler/placements──────────────────────► Scheduler
                            │   body: { application_uuid, tenant_uuid,
                            │           group_uuid, deploy_config, dry_run,
                            │           preferred_node_id }
                            │
                            │   Scheduler 內部三重檢查流程：
                            │   ┌──────────────────────────────────────────────┐
                            │   │ Phase 1（Pre-condition, side-effect free）    │
                            │   │  1. GET resource_profile from IAM            │
                            │   │  2. GET deployment_count from IAM            │
                            │   │  3. GET group_quota from IAM                 │
                            │   │  4. 計算 Group 剩餘容量                       │
                            │   │  5. GET node_allocations from IAM            │
                            │   │  6. MostRemainingStrategy 選最佳節點          │
                            │   │     （或 preferred_node_id 驗證，ADR-143）    │
                            │   ├──────────────────────────────────────────────┤
                            │   │ Phase 2（Atomic Commit）                      │
                            │   │  7. 儲存 PlacementRecord (PENDING)           │
                            │   ├──────────────────────────────────────────────┤
                            │   │ Phase 3（Fleet Dispatch）                     │
                            │   │  8. POST /v1/fleet/apps/{app_code}/deploy    │
                            │   │  9. emit audit: placement.requested          │
                            │   └──────────────────────────────────────────────┘
                            │
                            │   回應：{ placement_uuid, node_id, status: "pending" }
                            │
                            ◄──────────────────────────────────────────────────
Console ◄──response────── IAM
```

**dry_run 模式**：Phase 1 完成後直接回傳 `{ status: "dry_run_ok" }`，不執行 Phase 2/3。

**passthrough 模式**（`SCHEDULER_MODE=passthrough`）：跳過三重檢查，直接觸發 Fleet deploy（用於 StubIAMClient 場景）。

---

### 4.2 Application Release（停止/釋放流程）

**發起方**：IAM（處理 Console 的停止 Application 操作）

```
Console ──DELETE /iam/...──► IAM
                              │
                              ├──DELETE /scheduler/placements/{placement_uuid}──► Scheduler
                              │
                              │   Scheduler 內部釋放流程：
                              │   ┌────────────────────────────────────────────┐
                              │   │ Phase 1（Validate）                        │
                              │   │  1. 查找 PlacementRecord                   │
                              │   │  2. 狀態機驗證（需為 ACTIVE 或 PENDING）   │
                              │   │  3. 轉換為 RELEASING 並儲存                │
                              │   ├────────────────────────────────────────────┤
                              │   │ Phase 2（Fleet Dispatch）                  │
                              │   │  4. Fleet.destroy(node_id, app_uuid)       │
                              │   │     （Phase 1 stub，僅 log）               │
                              │   ├────────────────────────────────────────────┤
                              │   │ Phase 3（Cleanup）                         │
                              │   │  5. 刪除 UsageRecord                       │
                              │   │  6. 轉換為 RELEASED 並儲存                 │
                              │   │  7. emit audit: placement.released         │
                              │   └────────────────────────────────────────────┘
                              │
                              │   回應：{ placement_uuid, node_id, status: "released" }
                              │
Console ◄──response────── IAM
```

---

### 4.3 Application Restart（重啟流程）

**發起方**：IAM（處理 Console 的重啟操作，ADR-140）

```
Console ──POST /iam/...──► IAM
                            │
                            ├──POST /scheduler/placements/{placement_uuid}/restart──► Scheduler
                            │
                            │   Scheduler 內部重啟流程：
                            │   ┌────────────────────────────────────────────────┐
                            │   │ 1. 查找 PlacementRecord                        │
                            │   │ 2. 驗證狀態為 RELEASED（否則 409）             │
                            │   │ 3. POST /v1/fleet/commands                    │
                            │   │    body: { node_id, action: "start_workload", │
                            │   │            params: { placement_uuid } }       │
                            │   │ 4. 轉換 PlacementRecord 為 ACTIVE 並儲存      │
                            │   │ 5. emit audit: placement.restarted            │
                            │   └────────────────────────────────────────────────┘
                            │
                            │   回應：{ placement_uuid, node_id, status: "active" }
                            │
Console ◄──response────── IAM
```

> 重啟為 fire-and-forget（Fleet 非同步執行容器啟動）；Scheduler 不直接管理容器生命週期。

---

### 4.4 Node Heartbeat Report（節點心跳流程）

**發起方**：Fleet（定時轉發各節點的心跳資料）

```
NodeAgent ──heartbeat──► Fleet
                          │
                          ├──POST /scheduler/nodes/{node_id}/report──► Scheduler
                          │   body: {
                          │     capacity: { cpu_millicores, memory_mb,
                          │                disk_mb, gpu_slots, gpu_model },
                          │     usage: [ { application_uuid, tenant_uuid,
                          │               group_uuid, cpu_used, memory_used,
                          │               disk_used, gpu_used,
                          │               container_count } ],
                          │     last_heartbeat: <datetime>
                          │   }
                          │
                          │   Scheduler 內部處理流程：
                          │   ┌──────────────────────────────────────────────────┐
                          │   │ Step 1: Upsert NodeCapacity（冪等）              │
                          │   │         status 設為 ONLINE                       │
                          │   │ Step 2: Upsert per-app ResourceUsage（冪等）     │
                          │   │ Step 3: 激活 PENDING Placement                   │
                          │   │         若 PlacementRecord.node_id 與回報節點    │
                          │   │         一致 → PENDING → ACTIVE                  │
                          │   │         → emit audit: placement.completed       │
                          │   └──────────────────────────────────────────────────┘
                          │
                          │   回應：204 No Content
```

---

### 4.5 Capacity Query（容量查詢流程）

**發起方**：前端 Console（資源監控頁面）

```
Console ──GET /scheduler/capacity/nodes──► Scheduler
                                            │
                                            ├─（若有 tenant_uuid 篩選）
                                            │  GET /iam/internal/node-allocations?tenant=...──► IAM
                                            │  取得 Tenant 的節點分配清單
                                            │
                                            ├── 讀取 UsageStore（in-memory）
                                            │   每個節點：total、sum_by_node (used)、total - used (available)
                                            │
                                            ◄── [NodeCapacitySummarySchema]
                                                { node_id, status, gpu_model,
                                                  total, used, available,
                                                  last_heartbeat }

Console ──GET /scheduler/capacity/groups/{group_uuid}/usage──► Scheduler
                                                                 │
                                                                 ├──GET /iam/internal/group-quotas/{uuid}──► IAM
                                                                 ├── sum_by_group(group_uuid) ← UsageStore
                                                                 ◄── { group_uuid, quota, used, available }

Console ──GET /scheduler/capacity/tenants/{tenant_uuid}/usage──► Scheduler
                                                                   │
                                                                   ├──GET /iam/internal/node-allocations?tenant=...──► IAM
                                                                   │  （彙總所有 active allocation 為 total）
                                                                   ├── sum_by_tenant(tenant_uuid) ← UsageStore
                                                                   ◄── { tenant_uuid, total, used, available }
```

---

## 附錄：Placement 狀態機

```
            [POST /placements]
                    │
                    ▼
              ┌─────────┐
              │ PENDING │ ──── Fleet heartbeat confirms deploy
              └─────────┘              │
                    │                  ▼
                    │           ┌────────────┐
    deploy failed   │           │   ACTIVE   │
    (rollback)      │           └────────────┘
                    │                  │
                    │      [DELETE /placements/{uuid}]
                    │                  │
                    ▼                  ▼
              ┌──────────────────────────┐
              │        RELEASING         │
              └──────────────────────────┘
                             │
              Fleet destroy confirmed
                             │
                             ▼
              ┌────────────────────────────┐
              │          RELEASED          │ ──[POST .../restart]──► ACTIVE
              └────────────────────────────┘

dry_run 路徑：
[POST /placements?dry_run=true] ──► DRY_RUN_OK（不建立 PlacementRecord）
```

---

## 附錄：資源向量（ResourceVector）說明

| 維度 | 欄位名稱 | 單位 | 說明 |
|------|---------|------|------|
| CPU | `cpu_millicores` | millicores | 1000 = 1 核心 |
| Memory | `memory_mb` | MB | 記憶體用量 |
| Disk | `disk_mb` | MB | 磁碟用量 |
| GPU | `gpu_slots` | 個 | GPU 插槽數量 |
| Container | `container_count` | 個 | 容器數量（-1 = 無限制） |

> **MostRemainingStrategy**：節點選擇時，計算每個候選節點的 `min(tenant_remaining, node_remaining)` 資源向量，選取 `min_ratio` 最大者（即各維度剩餘比例最小值最大的節點），以避免資源碎片化。
