# xparse_fleet 技術報告

> **最後更新：** 2026-05-29  
> **維護者：** Platform Team  
> **來源目錄：** `xparse_fleet/fleet/`

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

### 應用類型

| 屬性 | 值 |
|------|-----|
| **類型** | Backend Service |
| **框架** | FastAPI (Python 3.11+) |
| **協議** | HTTP/REST（對外 API）、HTTP（對 IAM / xparse-node-mgr 的上游呼叫） |
| **面向對象** | 內部服務（Gateway、IAM、Console 間接呼叫）；節點代理直接呼叫（xparse-node-mgr） |
| **部署方式** | Docker 容器，透過 `xparse_fleet/fleet/Dockerfile` 建構，預設監聽 port `8090` |

### 核心職責

`xparse_fleet` 是整個 Xparse 平台的**編排控制面（Orchestration Control Plane）**，扮演以下角色：

- **節點生命週期管理**：維護所有 GPU 節點從 `REGISTERED` 到 `ACTIVE` 的狀態機（ADR-114）
- **部署協調**：調度模型服務部署、Agent App 副本、Plugin Workload 到適當的節點
- **資源管理**：GPU VRAM 感知放置、Port 分配登錄、容量回報轉發
- **目錄協調**：與 IAM 同步模型定義（L1 YAML → L2 IAM DB）（ADR-158）
- **事件轉發**：將節點心跳中的部署進度事件轉發至 IAM（PRD-128 P4a）
- **節點上線（Onboarding）**：Bootstrap 會話管理、硬體指紋驗證、激活碼消耗（PRD-131）

### 最短主路徑

```
xparse-node-mgr → POST /v1/fleet/heartbeat → FleetStateManager → CommandQueue → HeartbeatAck
```

---

## 2. 資料夾結構總覽

```
xparse_fleet/fleet/
├── __init__.py                        # 版本宣告 (0.1.0)
├── app.py                             # FastAPI 主應用、lifespan 啟動流程、路由掛載
├── models.py                          # 所有 Pydantic 資料模型（HeartbeatRequest、NodeInfo 等）
├── config.py                          # 環境變數讀取與 FleetConfig dataclass
├── auth.py                            # IAM 優先認證（Bearer token 驗證 + SHA-256 快取）
├── fleet_state.py                     # 中央狀態管理器（唯一可信狀態來源，2262 行）
├── command_queue.py                   # 命令佇列（pending/dispatched/done/failed/expired）
├── scheduler.py                       # GPU VRAM 感知放置決策
├── scheduler_relay.py                 # 容量報告非同步轉發至 xparse-scheduler
├── model_catalog.py                   # 本地 YAML 模型目錄載入（L1 快取）
├── model_catalog_reconciler.py        # IAM 目錄協調客戶端（L2 同步）
├── runtime_event_forwarder.py         # 部署事件轉發（pulling→serving→failed）
├── reconciler.py                      # Plugin Workload 協調迴圈（Observe→Compare→Act→Verify）
├── reconciliation_models.py           # 協調相關的資料模型（PluginWorkloadSpec 等）
├── port_registry.py                   # Port 分配登錄表（pool / reserve / allocate / bind）
├── drift_detector.py                  # 服務漂移檢測（偵測節點意外狀態改變）
├── server_verifier.py                 # 節點驗證執行器（送出驗證命令並追蹤結果）
├── revalidation.py                    # 週期性重新驗證排程
├── admission.py                       # 節點認可引擎（APPROVED → ADMITTED 的前置條件檢查）
├── service_registry.py                # 聚合服務清單（跨節點可路由服務）
├── trend_analyzer.py                  # 心跳歷史趨勢分析（穩定性計算）
├── deploy_context.py                  # 部署上下文建構（inference_base_url 等）
├── node_proxy.py                      # HTTP 轉接層（代理呼叫 xparse-node-mgr REST API）
├── catalog_cli.py                     # 目錄 CLI 工具（手動觸發協調）
│
├── routes/                            # API 路由層（17 個模組）
│   ├── __init__.py
│   ├── heartbeat.py                   # POST /heartbeat — 節點心跳主入口（222 行）
│   ├── fleet.py                       # GET /status、/gpu、/model-profiles — 車隊狀態（229 行）
│   ├── nodes.py                       # 節點審核（approve/admit/reject/delete）（208 行）
│   ├── services.py                    # 服務代理（list/apply/delete/logs，轉接 node-mgr）（147 行）
│   ├── deploy.py                      # 模型部署調度（schedule/deploy/undeploy）（311 行）
│   ├── apps.py                        # Agent App 部署（replica 放置 + port 分配）（511 行）
│   ├── workloads.py                   # 沙盒工作負載端點（117 行）
│   ├── deployments.py                 # 部署意圖 CRUD 代理（IAM ↔ Fleet 雙向）（403 行）
│   ├── catalog.py                     # 目錄瀏覽代理（GET，轉接 IAM L2）（33 行）
│   ├── catalog_admin.py               # 目錄管理（觸發協調、更新 YAML）
│   ├── models.py                      # 模型 CRUD 端點（本地 L1 + IAM L2）（120 行）
│   ├── ports.py                       # Port 登錄 CRUD（pool/reserve/allocate/bind/reconcile）（601 行）
│   ├── validation.py                  # 驗證觸發端點（150 行）
│   ├── plugin_specs.py                # Plugin Spec CRUD（樂觀鎖）
│   ├── bootstrap.py                   # 公開 CA 憑證下載（44 行）
│   ├── onboarding.py                  # 節點上線（Bootstrap 會話管理）（729 行）
│   ├── node_ops.py                    # 節點操作（M4/M5 工作負載命令）（318 行）
│   └── benchmark.py                   # 基準測試端點
│
├── deploy_artifacts/                  # 部署工件生成
│   ├── __init__.py
│   ├── generator.py                   # 安裝腳本生成器（397 行）
│   └── session.py                     # Bootstrap 會話存儲（321 行）
│
├── lib/                               # 工具函式庫
│   ├── __init__.py
│   ├── fingerprint.py                 # 硬體指紋驗證（PRD-131）
│   └── gpu_classifier.py             # GPU 型號分類器（T0–T4 Tier）
│
├── config/                            # 靜態 YAML 配置
│   ├── models.yaml                    # 模型目錄定義（L1）
│   ├── models-gemma-3-4b-v1.0.0.yaml  # Gemma 3 4B 模型規格
│   └── gpu_classes.yaml               # GPU 等級分類表
│
├── tests/                             # 測試套件（40+ 測試檔案）
│   ├── conftest.py                    # 共用 fixtures（TestClient、mock state 等）
│   ├── test_fleet_state.py            # 狀態機單元測試
│   ├── test_heartbeat.py              # 心跳流程整合測試
│   ├── test_node_lifecycle_e2e.py     # 節點生命週期 E2E 測試
│   ├── test_reconciler.py             # 協調器行為測試
│   ├── test_port_registry.py          # Port 分配測試
│   └── test_*.py                      # 其他功能測試（共 40+ 個）
│
├── Dockerfile                         # 容器建構（Python 3.11 slim）
├── pyproject.toml                     # 套件定義與依賴
└── TESTING.md                         # 測試執行說明
```

---

## 3. 各模組功能說明

### 核心模組

| 模組 | 職責 | 關聯文件 |
|------|------|---------|
| `app.py` | FastAPI 主應用；`lifespan` 中啟動協調器、初始化 `FleetStateManager`；掛載所有路由；CORS 設定 | ADR-128、PRD-115 |
| `fleet_state.py` | **唯一可信狀態來源**；管理所有節點的生命週期狀態機；`asyncio.Lock` 保護所有寫入；提供 `update_from_heartbeat`、`approve_node`、`get_routable_endpoints` 等核心 API | ADR-114、SPEC-093 |
| `command_queue.py` | 命令佇列；`create / get_pending / report_result / expire_stale`；命令生命週期：`pending → dispatched → done / failed / expired` | ADR-102 |
| `auth.py` | IAM 優先 Bearer token 驗證；SHA-256 快取（TTL 300s）；支援 `dual` / `iam_only` / `legacy_only` 三種模式 | ADR-073、SPEC-076 |
| `scheduler.py` | GPU VRAM 感知放置；`find_best_node(model_code)`；CPU 優先沙盒放置 `find_node_for_workload()` | ADR-102 M4/M5 |
| `models.py` | 所有 Pydantic schema 定義；`HeartbeatRequest`、`NodeInfo`、`ServiceInfo`、`PortAllocation` 等 | — |
| `config.py` | `load_config()` 從環境變數建立 `FleetConfig`；統一配置入口 | — |

### 通訊與事件模組

| 模組 | 職責 | 關聯文件 |
|------|------|---------|
| `node_proxy.py` | 代理呼叫 `xparse-node-mgr` REST API；`deploy()`、`delete_service()`、`list_services()`；錯誤統一包裝為 `NodeProxyError` | — |
| `scheduler_relay.py` | 非同步轉發節點容量報告至外部 `xparse-scheduler`；失敗只記 warning，不阻止 ACK | PRD-102 |
| `runtime_event_forwarder.py` | 將心跳中的 `active_deployments` 相位事件轉換後 POST 至 IAM；去重（同相位百分比丟棄） | PRD-128 P4a |
| `model_catalog_reconciler.py` | IAM 目錄協調客戶端；`reconcile(specs)`、`list_models()`、`create_deployment()` 等 IAM Catalog API 封裝 | ADR-158 |

### 資源管理模組

| 模組 | 職責 | 關聯文件 |
|------|------|---------|
| `port_registry.py` | Port 分配登錄表；`allocate_port()`（真值表：auto-pick / override / legacy）；`bind_allocation()`（INV-156-3：一次精確）；`reconcile_node_ports()` | ADR-156、ADR-160、SPEC-126、PRD-126 |
| `model_catalog.py` | YAML 模型目錄載入（L1 快取）；`load_catalog(path)` | PRD-128 P3a |

### 節點管理模組

| 模組 | 職責 | 關聯文件 |
|------|------|---------|
| `server_verifier.py` | 送出驗證命令、追蹤驗證結果；觸發 `APPROVED → VALIDATING` 狀態轉移 | PRD-079、ADR-112 |
| `admission.py` | 節點認可前置條件檢查；`APPROVED → ADMITTED` 跳過驗證的快速通道 | — |
| `drift_detector.py` | 偵測節點意外狀態漂移；回報給 `fleet_state` | — |
| `revalidation.py` | 定期觸發已認可節點的重新驗證 | — |
| `trend_analyzer.py` | 心跳時間序列趨勢分析（視窗大小 48）；節點穩定性評分 | — |

### 協調模組

| 模組 | 職責 | 關聯文件 |
|------|------|---------|
| `reconciler.py` | Plugin Workload 協調迴圈（30s 間隔）；Observe → Compare → Decide → Act → Verify 5 步驟 | PRD-115、ADR-145 |
| `reconciliation_models.py` | 協調相關資料模型：`PluginWorkloadSpec`、`ReconciliationState`、`WorkloadCondition` | SPEC-108 |

### 工具模組

| 模組 | 職責 | 關聯文件 |
|------|------|---------|
| `deploy_context.py` | 建構部署上下文；組合 `inference_base_url` 等部署所需參數 | — |
| `deploy_artifacts/generator.py` | 生成節點安裝 shell 腳本工件 | ADR-128 |
| `deploy_artifacts/session.py` | Bootstrap 會話存儲（記憶體 + 可選持久化） | PRD-131 |
| `lib/fingerprint.py` | 硬體指紋驗證（CPU/GPU/MAC 雜湊） | PRD-131 |
| `lib/gpu_classifier.py` | GPU 型號 → Tier 分類（T0–T4） | — |
| `service_registry.py` | 聚合跨節點服務清單；提供可路由服務端點 | SPEC-093 §10 |
| `catalog_cli.py` | 目錄管理 CLI 工具（用於運維手動觸發協調） | — |

---

## 4. 對外 API 端點完整列表

**Base URL：** `/v1/fleet`  
**認證：** `Authorization: Bearer <token>`（IAM `xp_live_*` 優先；可配置 Legacy 靜態 token）

---

### A. 車隊狀態

| 方法 | 路徑 | 用途 | 認證 |
|------|------|------|------|
| `GET` | `/v1/fleet/status` | 車隊聚合狀態（節點、GPU、服務統計） | Bearer |
| `GET` | `/v1/fleet/gpu` | GPU 分配詳情 | Bearer |
| `GET` | `/v1/fleet/model-profiles` | Gateway 相容的模型設定檔列表 | Bearer |
| `GET` | `/v1/fleet/routable-endpoints` | 可路由服務端點（SPEC-093 §10） | Bearer |

**`GET /v1/fleet/status` Response：**
```json
{
  "nodes": [...],
  "total_gpus": 8,
  "active_gpus": 4,
  "idle_gpus": 4,
  "total_services": 3,
  "running_services": 2,
  "total_sandboxes": 1,
  "running_sandboxes": 1
}
```

---

### B. 心跳

| 方法 | 路徑 | 用途 | 認證 |
|------|------|------|------|
| `POST` | `/v1/fleet/heartbeat` | 接收節點心跳；回傳 pending commands | Bearer (IAM or Legacy) |

**Request Body：**
```json
{
  "node_id": "node-gpu-01",
  "timestamp": "2026-05-29T10:00:00Z",
  "services": [
    {
      "name": "llama3-8b",
      "model": "llama3",
      "status": "running",
      "endpoint": "http://node-gpu-01:8000",
      "host_port": 30001
    }
  ],
  "gpus": [
    {
      "index": 0,
      "name": "NVIDIA A100",
      "vram_total_gb": 80,
      "vram_used_gb": 40,
      "status": "active"
    }
  ],
  "command_results": [
    {"command_id": "cmd-uuid", "status": "done", "action": "deploy"}
  ],
  "workloads": [],
  "active_deployments": [
    {
      "command_id": "cmd-uuid",
      "model_code": "llama3-8b",
      "phase": "starting",
      "percent": 60
    }
  ],
  "capacity": {
    "cpu_millicores": 32000,
    "memory_mb": 65536,
    "disk_mb": 500000,
    "gpu_slots": 4
  },
  "usage": [],
  "host_ports_observed": {"30001": "llama3-8b"}
}
```

**Response：**
```json
{
  "ack": true,
  "approved": true,
  "node_state": "ACTIVE",
  "pending_commands": [
    {"command_id": "cmd-uuid-2", "action": "deploy", "params": {}}
  ]
}
```

---

### C. 節點管理

| 方法 | 路徑 | 用途 | 狀態轉移 |
|------|------|------|---------|
| `GET` | `/v1/fleet/nodes` | 列出所有節點 | — |
| `GET` | `/v1/fleet/nodes/{node_id}` | 單一節點詳情 | — |
| `POST` | `/v1/fleet/nodes/{node_id}/approve` | 審核通過節點 | `REGISTERED → APPROVED` |
| `POST` | `/v1/fleet/nodes/{node_id}/admit` | 跳過驗證直接認可（管理員） | `APPROVED → ADMITTED` |
| `POST` | `/v1/fleet/nodes/{node_id}/reject` | 拒絕節點 | `ANY → REJECTED` |
| `DELETE` | `/v1/fleet/nodes/{node_id}` | 移除節點（僅動態節點） | 刪除 |

**允許的狀態轉移（ADR-114 / SPEC-093 §4）：**
```
REGISTERED  → APPROVED, REJECTED
APPROVED    → VALIDATING, ADMITTED, REJECTED
VALIDATING  → ADMITTED, QUARANTINED, REJECTED
ADMITTED    → DEPLOYING, VALIDATING, REJECTED
DEPLOYING   → ACTIVE, ADMITTED, DEGRADED, REJECTED
ACTIVE      → DEGRADED, ADMITTED, REJECTED
DEGRADED    → ACTIVE, ADMITTED, REJECTED
QUARANTINED → VALIDATING, REJECTED
REJECTED    → (終端態)
```

---

### D. 模型部署

| 方法 | 路徑 | 用途 | 備註 |
|------|------|------|------|
| `GET` | `/v1/fleet/models` | 列出模型目錄（L1 + L2） | — |
| `GET` | `/v1/fleet/models/{model_code}` | 單一模型規格 | — |
| `POST` | `/v1/fleet/schedule` | 乾跑放置決策（不建立命令） | `{"model_code": "llama3-8b"}` |
| `POST` | `/v1/fleet/deploy` | 調度 + 建立 deploy 命令 | `{"model_code": "llama3-8b"}` |
| `POST` | `/v1/fleet/undeploy` | 建立 undeploy 命令 | `{"node_id": "n1", "service_name": "llama3-8b"}` |
| `GET` | `/v1/fleet/commands` | 列出命令（可選 `node_id`, `status` 篩選） | — |
| `GET` | `/v1/fleet/commands/{command_id}` | 單一命令狀態 | — |

---

### E. Agent App 部署

| 方法 | 路徑 | 用途 | 備註 |
|------|------|------|------|
| `POST` | `/v1/fleet/apps/{app_code}/deploy` | 部署應用副本（自動 port 分配） | ADR-160 |
| `GET` | `/v1/fleet/apps/{app_code}/endpoint` | 取得應用上游 URL | ADR-110 Phase 3c |
| `GET` | `/v1/fleet/apps/{app_code}/deployments/{deploy_code}/endpoint` | 每部署端點（副本清單） | ADR-129 Phase 1 |

**`POST /v1/fleet/apps/{app_code}/deploy` Request Body：**
```json
{
  "image": "registry.example.com/open-webui:1.0.0",
  "replicas": 2,
  "placement": "spread",
  "tenant_id": "tenant-uuid",
  "preferred_port": 8080,
  "env": {
    "OPENAI_API_KEY": "...",
    "OPENAI_API_BASE": "http://gateway/v1"
  },
  "workload_type": "agent_app",
  "proxy_enabled": true,
  "proxy_image": "nginx:alpine",
  "proxy_port": 80,
  "app_url_slug": "my-app",
  "deploy_code": "deploy-v1",
  "preferred_node_id": "node-gpu-01",
  "registry_auth": {"username": "user", "password": "pass"}
}
```

**Response：**
```json
{
  "ok": true,
  "placed": [
    {"node_id": "node-gpu-01", "command_id": "cmd-uuid", "allocated_port": 30080}
  ],
  "failed_count": 0
}
```

---

### F. 部署意圖（PRD-128 / ADR-158）

| 方法 | 路徑 | 用途 | 轉發目標 |
|------|------|------|---------|
| `POST` | `/v1/fleet/deployments` | 建立意圖 + 分配命令 | `IAM POST /iam/catalog/deployments` |
| `GET` | `/v1/fleet/deployments` | 列出意圖（群組範圍） | `IAM GET /iam/catalog/deployments` |
| `GET` | `/v1/fleet/deployments/by-alias/{alias}` | 別名查詢 | `IAM GET by-alias` |
| `GET` | `/v1/fleet/deployments/{uuid}` | 意圖詳情 | `IAM GET /{uuid}` |
| `PATCH` | `/v1/fleet/deployments/{uuid}` | 更新意圖（含命令分配） | `IAM PATCH + Command` |
| `DELETE` | `/v1/fleet/deployments/{uuid}` | 軟停止 + undeploy 命令 | `IAM DELETE + Command` |

---

### G. Port 登錄（SPEC-126 / ADR-156 / ADR-160）

| 方法 | 路徑 | 用途 | 階段 |
|------|------|------|------|
| `GET` | `/v1/fleet/nodes/{node_id}/ports` | 列出 port pool + 保留清單 | Phase 1 |
| `GET` | `/v1/fleet/nodes/{node_id}/ports/free` | 空閒 port 列表 | Phase 1 |
| `PUT` | `/v1/fleet/nodes/{node_id}/port-pool` | 聲明/替換 port pool | Phase 1 |
| `POST` | `/v1/fleet/nodes/{node_id}/ports/reserve` | 靜態保留 port | Phase 1 |
| `DELETE` | `/v1/fleet/nodes/{node_id}/ports/{port}` | 移除保留 | Phase 1 |
| `POST` | `/v1/fleet/nodes/{node_id}/ports/allocate` | 動態分配（ADR-160） | Phase 2a |
| `POST` | `/v1/fleet/nodes/{node_id}/ports/allocations/{id}/bind` | 轉移 REQUESTED→BOUND | Phase 2a |
| `DELETE` | `/v1/fleet/nodes/{node_id}/ports/allocations/{id}` | 釋放分配 | Phase 2a |
| `POST` | `/v1/fleet/nodes/{node_id}/ports/reconcile` | 差分與策略應用（M5） | ADR-156 §3.3 |

---

### H. 工作負載（ADR-102 M4/M5）

| 方法 | 路徑 | 用途 | 節點選擇 |
|------|------|------|---------|
| `POST` | `/v1/fleet/workloads/deploy` | 自動調度沙盒工作負載 | CPU 優先自動選節點 |
| `POST` | `/v1/fleet/nodes/{node_id}/deploy` | 在指定節點放置工作負載 | 指定節點 |
| `POST` | `/v1/fleet/nodes/{node_id}/destroy` | 銷毀工作負載 | 指定節點 |
| `POST` | `/v1/fleet/nodes/{node_id}/stop` | 停止工作負載 | 指定節點 |
| `POST` | `/v1/fleet/nodes/{node_id}/start` | 啟動工作負載 | 指定節點 |

---

### I. 驗證（PRD-079 / ADR-112）

| 方法 | 路徑 | 用途 | 狀態轉移 |
|------|------|------|---------|
| `POST` | `/v1/fleet/nodes/{node_id}/validate` | 觸發節點驗證 | `APPROVED/ADMITTED → VALIDATING` |
| `GET` | `/v1/fleet/nodes/{node_id}/validation` | 驗證狀態報告 | — |

---

### J. Plugin Spec（ADR-145 / SPEC-108）

| 方法 | 路徑 | 用途 | 鎖定機制 |
|------|------|------|---------|
| `POST` | `/v1/fleet/plugin-specs` | 建立規格 | 樂觀鎖 via `generation` |
| `GET` | `/v1/fleet/plugin-specs` | 列出規格 | — |
| `GET` | `/v1/fleet/plugin-specs/{spec_id}` | 規格詳情 | — |
| `PATCH` | `/v1/fleet/plugin-specs/{spec_id}` | 更新規格（`expected_generation` 校驗） | 樂觀鎖 |
| `DELETE` | `/v1/fleet/plugin-specs/{spec_id}` | 軟刪除（協調器處理撕除） | — |

---

### K. 目錄瀏覽（PRD-128 P3a）

| 方法 | 路徑 | 用途 | 來源 |
|------|------|------|------|
| `GET` | `/v1/fleet/catalog/models` | 列出模型定義 | IAM L2 |
| `GET` | `/v1/fleet/catalog/models/{name}` | 模型詳情 + 版本列表 | IAM L2 |
| `GET` | `/v1/fleet/catalog/models/{name}/versions/{version}` | 版本詳情 | IAM L2 |

---

### L. 節點上線（ADR-128 / PRD-131 / SPEC-153 §8）

| 方法 | 路徑 | 用途 | 認證 |
|------|------|------|------|
| `POST` | `/v1/fleet/deploy-node/bootstrap` | 建立 Bootstrap 會話（生成工件） | Bearer |
| `POST` | `/v1/fleet/deploy-node/bootstrap/{id}/claim` | 節點聲稱會話（指紋驗證） | 無認證（bootstrap_id + activation_code） |
| `GET` | `/v1/fleet/deploy-node/bootstrap/{id}/install.sh` | 一次性安裝腳本下載 | Secret token |
| `GET` | `/v1/fleet/deploy-node/bootstrap/{id}/artifacts` | 手動工件下載 | Bearer |
| `GET` | `/v1/fleet/deploy-node/bootstrap/{id}/stream` | SSE 進度追蹤 | Bearer |
| `DELETE` | `/v1/fleet/deploy-node/bootstrap/{id}` | 取消會話 | Bearer |

---

### M. 服務代理

| 方法 | 路徑 | 用途 | 轉發目標 |
|------|------|------|---------|
| `GET` | `/v1/fleet/services` | 聚合服務清單（跨所有節點） | 各節點 node-mgr |
| `GET` | `/v1/fleet/services/{name}` | 服務詳情 | 對應節點 node-mgr |
| `GET` | `/v1/fleet/services/{name}/logs` | 服務日誌（`tail` 參數） | 對應節點 node-mgr |
| `POST` | `/v1/fleet/services/apply` | 部署服務（代理至節點） | 對應節點 node-mgr |
| `POST` | `/v1/fleet/services/delete` | 刪除服務（代理至節點） | 對應節點 node-mgr |

---

### N. 雜項

| 方法 | 路徑 | 用途 | 認證 |
|------|------|------|------|
| `GET` | `/v1/fleet/bootstrap/registry-ca` | 公開 CA 憑證（PEM 格式） | 無認證（Docker trust 用途） |

---

## 5. 服務通訊全貌

### ASCII 架構圖

```
╔══════════════════════════════════════════════════════════════════════════╗
║                        xparse_fleet (port 8090)                         ║
╚══════════════════════════════════════════════════════════════════════════╝
          ▲ REST/HTTP                            ▲ REST/HTTP
          │ Bearer                               │ Bearer
          │ (入站)                               │ (入站)
  ┌───────┴────────┐                    ┌────────┴────────┐
  │  xparse-node   │                    │  Console App /  │
  │  -mgr (agentd) │                    │  Gateway /      │
  │  POST /heart-  │                    │  CLI (xpctl)    │
  │  beat          │                    └─────────────────┘
  └────────────────┘
          │
    ╔═════╧══════════════════════════════════════════════════════╗
    ║  xparse_fleet 內部處理流程                                  ║
    ║                                                             ║
    ║  auth.py ─────────────────────────────────────────────────►║
    ║  (快取驗證)          POST /iam/auth/validate (出站)         ║
    ║                                ▼                            ║
    ║  fleet_state.py ──────────────────────────────────────────►║
    ║  (狀態機)            狀態轉移 + asyncio.Lock 保護            ║
    ║                                ▼                            ║
    ║  command_queue.py ─────────────────────────────────────────║
    ║  (命令佇列)          pending_commands → HeartbeatAck        ║
    ╚═════════════════════════════════════════════════════════════╝
          │
          │ 對外呼叫（HTTP 出站）
          ▼
  ┌───────────────────────────────────────────────────────────────┐
  │                xparse_iam (Django / port 3000)                │
  │                                                               │
  │  POST /iam/auth/validate              (auth.py)               │
  │  POST /iam/catalog/reconcile          (model_catalog_reconciler)│
  │  GET  /iam/catalog/models             (model_catalog_reconciler)│
  │  POST /iam/catalog/deployments        (deployments.py)        │
  │  PATCH/DELETE /iam/catalog/deployments/{uuid}                 │
  │  POST /iam/fleet-runtime/deployments/{uuid}/events            │
  │       (runtime_event_forwarder)                               │
  │  POST /iam/node-activations/validate  (onboarding.py)         │
  │  POST /iam/node-activations/consume   (onboarding.py)         │
  └───────────────────────────────────────────────────────────────┘
          │
          │ 對外呼叫（HTTP 出站，選配）
          ▼
  ┌──────────────────────────────────┐
  │  xparse-scheduler (port 8000)   │
  │                                 │
  │  POST /nodes/{node_id}/report   │
  │       (scheduler_relay.py)      │
  └──────────────────────────────────┘
          │
          │ 對外呼叫（HTTP 出站，靜態節點）
          ▼
  ┌──────────────────────────────────────────────────┐
  │  xparse-node-mgr (各 GPU 節點，URL 由 env var)  │
  │                                                  │
  │  POST /v1/services/apply   (node_proxy.py)       │
  │  POST /v1/services/delete  (node_proxy.py)       │
  │  GET  /v1/services         (node_proxy.py)       │
  │  GET  /v1/services/{name}  (node_proxy.py)       │
  │  GET  /v1/services/{name}/logs  (node_proxy.py)  │
  │  GET  /v1/catalog/models   (node_proxy.py)       │
  └──────────────────────────────────────────────────┘
```

---

### 通訊連結總表

| 對象 | 類型 | 協議 | 方向 | 發起點檔案 | 失敗行為 |
|------|------|------|------|-----------|---------|
| xparse-node-mgr（agentd） | Backend | HTTP/REST | 入站 | `routes/heartbeat.py` | 401/503 回應 |
| Console App / Gateway / CLI | Backend/Frontend | HTTP/REST | 入站 | `routes/*.py` | 4xx/5xx 回應 |
| xparse_iam（token 驗證） | Backend | HTTP/REST | 出站 | `auth.py` | 503（IAM 不可達）；401（無效 token） |
| xparse_iam（目錄協調） | Backend | HTTP/REST | 出站 | `model_catalog_reconciler.py` | `CatalogReconcileError`（502 回傳調用者） |
| xparse_iam（部署意圖） | Backend | HTTP/REST | 出站 | `routes/deployments.py` | 錯誤透傳至調用者 |
| xparse_iam（事件轉發） | Backend | HTTP/REST | 出站 | `runtime_event_forwarder.py` | Warning 記錄，**不阻止** HeartbeatAck（fail-open） |
| xparse_iam（激活碼） | Backend | HTTP/REST | 出站 | `routes/onboarding.py` | 409/410/403 → 422 回傳調用者 |
| xparse-scheduler（容量報告） | Backend | HTTP/REST | 出站 | `scheduler_relay.py` | Warning 記錄，**不阻止** HeartbeatAck（fail-open） |
| xparse-node-mgr（服務代理） | Backend | HTTP/REST | 出站 | `node_proxy.py` | `NodeProxyError` → 502（fail-fast） |

---

### 各連線詳細說明

---

#### 連線 1：IAM Token 驗證

- **用途：** Bearer token 認證（所有 API 入口）
- **Endpoint URL：** `{FLEET_IAM_VALIDATE_URL}`（env var）
- **程式碼：** `fleet/auth.py:99–103`
- **Request：**
  ```http
  POST {FLEET_IAM_VALIDATE_URL}
  Authorization: Bearer {bearer_token}
  Content-Type: application/json

  {"api_key": "{bearer_token}"}
  ```
- **Response：**
  ```json
  {
    "valid": true,
    "application_code": "app-001",
    "tenant_code": "tenant-001",
    "key_type": "live",
    "key_deprecated": false,
    "key_expires_at": null
  }
  ```
- **Timeout：** httpx 預設 30s
- **快取：** SHA-256(token) → 300s TTL（`FLEET_AUTH_CACHE_TTL`）；過期 key 強制縮短 TTL（SPEC-076）
- **失敗行為：** `httpx.ConnectError` → HTTP 503；`valid: false` → HTTP 401

---

#### 連線 2：IAM 目錄協調（啟動時 + 手動觸發）

- **用途：** 將本地 YAML 模型規格（L1）同步至 IAM DB（L2）
- **Endpoint URL：** `{FLEET_IAM_BASE_URL}/iam/catalog/reconcile`
- **程式碼：** `fleet/model_catalog_reconciler.py:99–129`；觸發點 `fleet/app.py:129–130`
- **Request：**
  ```http
  POST {FLEET_IAM_BASE_URL}/iam/catalog/reconcile
  Authorization: Bearer {FLEET_IAM_ADMIN_KEY}
  Content-Type: application/json

  {
    "specs": [
      {
        "model_code": "llama3-8b",
        "engine": "vllm",
        "image": "registry/vllm:v0.4",
        "tp": 1,
        "min_vram_per_gpu_gb": 20,
        "extra_args": ["--max-model-len", "4096"]
      }
    ]
  }
  ```
- **Response：**
  ```json
  {"ok": true, "errors": []}
  ```
- **Timeout：** httpx 預設 30s
- **失敗行為：** 422（規格驗證失敗）→ `CatalogReconcileError`（回傳 502 給調用者）；IAM 不可達 → 502

---

#### 連線 3：IAM 部署事件轉發

- **用途：** 將心跳中的部署進度相位轉換後通知 IAM（PRD-128 P4a）
- **Endpoint URL：** `{FLEET_IAM_BASE_URL}/iam/fleet-runtime/deployments/{deployment_uuid}/events`
- **程式碼：** `fleet/runtime_event_forwarder.py:135–340`；觸發點 `fleet/app.py:137–141`

**相位對應表：**

| agentd 相位 | 轉發至 IAM 相位 |
|------------|--------------|
| `pulling` | `image_pulling` |
| `starting` | `booting` |
| `health_check` | `healthchecking` |
| `deploy done` | `serving` |
| `deploy failed` | `failed` |
| `undeploy done` | `stopped` |

- **Request：**
  ```http
  POST {FLEET_IAM_BASE_URL}/iam/fleet-runtime/deployments/{uuid}/events
  Authorization: Bearer {FLEET_IAM_ADMIN_KEY}
  Content-Type: application/json

  {
    "events": [
      {
        "timestamp": "2026-05-29T10:00:05Z",
        "phase": "booting",
        "ok": true,
        "percent": 40
      }
    ]
  }
  ```
- **去重邏輯：** 相位邊界檢查；同一相位內的百分比更新被丟棄（只發相位切換事件）
- **Timeout：** httpx 預設 30s
- **失敗行為：** Warning 記錄，**從不阻止** HeartbeatAck（fail-open）

---

#### 連線 4：IAM 激活碼驗證與消耗（節點上線）

- **用途：** 節點 Bootstrap 時驗證並消耗一次性激活碼（PRD-131 BOOTSTRAP-02~04）
- **程式碼：** `fleet/routes/onboarding.py:195–271`

**驗證 Endpoint：**
```http
POST {FLEET_IAM_BASE_URL}/iam/node-activations/validate
Authorization: Bearer {FLEET_IAM_ADMIN_KEY}
Content-Type: application/json

{"tenant_uuid": "...", "code": "ACTV-XXXX-YYYY"}
```
**Response：** `{"valid": true, "sku": "gpu-node-std", "constraints": {...}}`

**消耗 Endpoint（原子操作）：**
```http
POST {FLEET_IAM_BASE_URL}/iam/node-activations/consume
Authorization: Bearer {FLEET_IAM_ADMIN_KEY}
Content-Type: application/json

{
  "tenant_uuid": "...",
  "code": "ACTV-XXXX-YYYY",
  "node_id": "node-gpu-01",
  "fingerprint": {"cpu": "...", "mac": "...", "gpu": "..."}
}
```
**Response：** `{"consumed_at": "2026-05-29T10:00:00Z", "sku": "gpu-node-std"}`

- **失敗行為：** 409（已消耗）/ 410（已過期）/ 403（指紋不符）→ 回傳 422 至調用者（fail-fast）

---

#### 連線 5：容量報告轉發至 xparse-scheduler

- **用途：** 將節點 CPU/記憶體/GPU 容量轉發至排程器（非關鍵路徑）
- **Endpoint URL：** `{FLEET_SCHEDULER_URL}/nodes/{node_id}/report`
- **程式碼：** `fleet/scheduler_relay.py:51–104`；觸發點 `fleet/routes/heartbeat.py:208–214`
- **Request：**
  ```http
  POST {FLEET_SCHEDULER_URL}/nodes/{node_id}/report
  Content-Type: application/json

  {
    "capacity": {
      "cpu_millicores": 32000,
      "memory_mb": 65536,
      "disk_mb": 500000,
      "gpu_slots": 4
    },
    "usage": [
      {
        "application_uuid": "app-uuid",
        "cpu_used": 2000,
        "memory_used": 4096
      }
    ],
    "last_heartbeat": "2026-05-29T10:00:00Z"
  }
  ```
- **Timeout：** httpx 預設 30s
- **失敗行為：** **所有錯誤被吞掉（fail-open）**，僅記錄 warning；不阻止 HeartbeatAck

---

#### 連線 6：xparse-node-mgr 服務代理

- **用途：** Fleet 代理管理員指令至各節點（部署服務、查詢狀態）
- **Endpoint URL：** `{node.url}{path}`（節點 URL 來自 `FLEET_AGENTS` env var）
- **程式碼：** `fleet/node_proxy.py:44–115`

**常用端點：**
```http
POST {node.url}/v1/services/apply
POST {node.url}/v1/services/delete
GET  {node.url}/v1/services
GET  {node.url}/v1/services/{name}
GET  {node.url}/v1/services/{name}/logs
```

- **Request Header：** `Authorization: Bearer {node.token}`
- **Timeout：** 30 秒
- **失敗行為：** `NodeProxyError` → HTTP 502 回傳調用者（fail-fast）

---

## 6. 請求主流程

### 心跳處理主流程

```
xparse-node-mgr
    │
    │ POST /v1/fleet/heartbeat
    │ Authorization: Bearer {node_token}
    ▼
routes/heartbeat.py : receive_heartbeat()
    │
    ├─ ① 認證 (auth.py : authenticate)
    │       ├─ IAM token → POST {FLEET_IAM_VALIDATE_URL}（快取 300s）
    │       └─ Legacy token → 靜態比較
    │
    ├─ ② 狀態更新 (fleet_state.py : update_from_heartbeat)
    │       ├─ node_id 解析（支援 agent_id 別名）
    │       ├─ 節點生命週期驗證 ALLOWED_TRANSITIONS 檢查
    │       ├─ GPU / 服務 UPSERT（asyncio.Lock 保護）
    │       ├─ 隔離冷卻檢查（FLEET_QUARANTINE_COOLDOWN_HOURS）
    │       └─ 心跳 TTL 標記（FLEET_HEARTBEAT_TTL=120s）
    │
    ├─ ③ Port 協調（選配，ADR-156 M5）
    │       └─ fleet_state.py : reconcile_node_ports(observed_dict)
    │               └─ 差分事件 + 策略應用
    │
    ├─ ④ 命令結果處理（每個 command_result）
    │       ├─ command_queue.py : report_result(command_id, status)
    │       ├─ fleet_state.py : process_validation_result（若 action=validate）
    │       └─ runtime_event_forwarder.py : forward_command_result
    │               └─ POST {IAM}/fleet-runtime/deployments/{uuid}/events
    │
    ├─ ⑤ 進行中部署事件轉發（active_deployments[]）
    │       └─ runtime_event_forwarder.py : forward_active_deployments
    │               ├─ 相位邊界去重（同相位百分比丟棄）
    │               └─ POST {IAM}/fleet-runtime/deployments/{uuid}/events
    │
    ├─ ⑥ 容量中繼（選配）
    │       └─ scheduler_relay.py : relay_capacity（異步，fail-open）
    │               └─ POST {FLEET_SCHEDULER_URL}/nodes/{node_id}/report
    │
    └─ ⑦ 回應 HeartbeatAck
            ├─ pending_commands（command_queue.get_pending(node_id)）
            ├─ node_state（當前狀態機狀態）
            └─ approved: true/false
```

---

### Agent App 部署主流程

```
Console App / xpctl CLI
    │
    │ POST /v1/fleet/apps/{app_code}/deploy
    ▼
routes/apps.py : deploy_agent_app()
    │
    ├─ ① 驗證首選節點（若指定 preferred_node_id，ADR-143）
    │       └─ fleet_state.get_node(preferred_node_id) → 確認在線
    │
    ├─ ② 副本放置迴圈（i = 0 to replicas-1）
    │   ├─ 選擇節點
    │   │   ├─ 若 preferred_node_id → 直接使用
    │   │   └─ 否則 scheduler.py : find_node_for_workload()（CPU 優先）
    │   │
    │   ├─ Port 分配（ADR-160）
    │   │   └─ fleet_state.allocate_port(
    │   │         allocated_to="{app_code}/{deploy_code}",
    │   │         purpose=AGENT_APP,
    │   │         ttl=300
    │   │      )
    │   │       ├─ auto-pick（從 pool 選空閒 port）
    │   │       ├─ preferred_port（若指定）
    │   │       └─ legacy escape（force_legacy=True 時）
    │   │
    │   └─ 建立部署命令（command_queue.create）
    │         ├─ action: "nemoclaw_onboard"（若 workload_type=nemoclaw）
    │         └─ action: "create_workload"（一般 Agent App）
    │               ├─ allocated_host_port（M4 新增）
    │               ├─ allocation_id（agentd 用於 POST /bind）
    │               ├─ proxy params（ADR-136 sidecar）
    │               ├─ lifecycle_hooks（ADR-140 D-3）
    │               ├─ volumes（ADR-140 D-8）
    │               └─ mounts（Issue #221 Phase 1b）
    │
    └─ ③ 回應
            ├─ ok: true（至少一個副本放置成功）
            ├─ placed: [{node_id, command_id, allocated_port}]
            └─ failed_count: N
```

---

### 節點上線（Bootstrap）主流程

```
管理員（Console / xpctl）
    │
    │ POST /v1/fleet/deploy-node/bootstrap
    ▼
routes/onboarding.py : create_bootstrap_session()
    │
    ├─ BOOTSTRAP-01：若 XPARSE_REQUIRE_ACTIVATION_CODE=true
    │    └─ POST {IAM}/iam/node-activations/validate（驗證碼有效性）
    │
    ├─ deploy_artifacts/generator.py : generate_install_script()
    │    └─ 生成一次性安裝 shell 腳本
    │
    └─ 回傳 bootstrap_session_id（含 SSE stream URL）

節點安裝腳本執行
    │
    │ GET /v1/fleet/deploy-node/bootstrap/{id}/install.sh
    │     （一次性 secret token）
    ▼
routes/onboarding.py : download_install_script()

節點完成安裝後
    │
    │ POST /v1/fleet/deploy-node/bootstrap/{id}/claim
    │ Body: {activation_code, fingerprint: {cpu, mac, gpu}}
    ▼
routes/onboarding.py : claim_session()
    │
    ├─ BOOTSTRAP-03：lib/fingerprint.py 驗證指紋
    │
    ├─ BOOTSTRAP-04：POST {IAM}/iam/node-activations/consume（原子）
    │    └─ 409/410/403 → 422 回傳
    │
    └─ 回傳 {sku, consumed_at}
```

---

## 7. 關鍵類別索引

| 類別名稱 | 檔案 | 職責 |
|---------|------|------|
| `FleetStateManager` | `fleet_state.py` | 中央狀態管理器；節點生命週期、服務狀態、port 分配的唯一可信來源；`asyncio.Lock` 保護全部寫入 |
| `CommandQueue` | `command_queue.py` | 命令佇列；CRUD + 狀態轉移（pending/dispatched/done/failed/expired）；到期清理 |
| `NodeAuthenticator` | `auth.py` | Bearer token 驗證；SHA-256 快取；IAM HTTP 呼叫封裝 |
| `WorkloadReconciler` | `reconciler.py` | Plugin Workload 協調迴圈；Observe→Compare→Decide→Act→Verify 5 步驟；30s 背景迴圈 |
| `CatalogReconcileClient` | `model_catalog_reconciler.py` | IAM 目錄協調客戶端；`reconcile()`、`list_models()`、`create_deployment()` 等 IAM Catalog API |
| `RuntimeEventForwarder` | `runtime_event_forwarder.py` | 部署事件相位轉換與轉發；去重邏輯；fail-open |
| `ModelCatalog` | `model_catalog.py` | YAML 模型目錄 L1 快取載入；`get_model(model_code)` |
| `NodeProxy` | `node_proxy.py` | xparse-node-mgr REST API 代理；統一包裝 `NodeProxyError` |
| `SchedulerRelay` | `scheduler_relay.py` | 容量報告非同步轉發；fail-open |
| `BootstrapSession` | `deploy_artifacts/session.py` | Bootstrap 會話存儲（記憶體）；TTL 管理；一次性 token 防重放 |
| `InstallScriptGenerator` | `deploy_artifacts/generator.py` | 節點安裝 shell 腳本生成器 |
| `PortAllocation` | `port_registry.py` | Port 分配資料類別；REQUESTED→BOUND→RELEASED 狀態機（INV-156-3：bind 一次精確） |
| `NodePortPool` | `port_registry.py` | 節點 port pool 資料類別；保留清單管理 |
| `TrendAnalyzer` | `trend_analyzer.py` | 心跳歷史趨勢分析；滑動視窗穩定性評分 |
| `ServerVerifier` | `server_verifier.py` | 節點驗證執行；送出 validate 命令、追蹤結果 |
| `DriftDetector` | `drift_detector.py` | 偵測節點服務狀態意外漂移 |
| `FingerprintVerifier` | `lib/fingerprint.py` | 硬體指紋驗證（CPU/GPU/MAC 雜湊） |
| `GpuClassifier` | `lib/gpu_classifier.py` | GPU 型號 → Tier（T0–T4）分類 |

---

## 8. 重要環境變數

| 變數名稱 | 預設值 | 說明 |
|---------|--------|------|
| `FLEET_PORT` | `8090` | Fleet 服務監聽 port |
| `FLEET_AGENTS` | — | 靜態節點 JSON 陣列：`[{"node_id":"n1","url":"http://...","token":"..."}]` |
| `FLEET_APP_DEPLOYMENTS` | — | 靜態 Agent App 部署設定 JSON 陣列（Phase 3c） |
| `FLEET_AUTH_MODE` | `iam_only` | 認證模式：`legacy_only` / `dual` / `iam_only` |
| `FLEET_ALLOW_LEGACY_AUTH` | `false` | 是否允許舊版靜態 token |
| `FLEET_API_TOKEN` | `demo-token` | 靜態 API token（Legacy 模式） |
| `FLEET_NODE_KEY` | `demo-token` | 靜態節點 token（Legacy 模式） |
| `FLEET_IAM_VALIDATE_URL` | — | IAM token 驗證端點（Bearer token 認證用） |
| `FLEET_AUTH_CACHE_TTL` | `300` | Token 驗證快取 TTL（秒）；過期 key 強制縮短 |
| `FLEET_IAM_BASE_URL` | `https://localhost:3000/iam` | IAM 服務基礎 URL（目錄協調、事件轉發） |
| `FLEET_IAM_ADMIN_KEY` | — | Fleet → IAM 服務帳戶認證 token（`xp_admin_*`） |
| `FLEET_HEARTBEAT_TTL` | `120` | 心跳 TTL（超過則節點標記 offline，秒） |
| `FLEET_SCHEDULER_URL` | — | xparse-scheduler 服務 URL（選配，不設則跳過容量中繼） |
| `FLEET_DATA_DIR` | `/tmp/fleet` | 狀態持久化資料目錄 |
| `FLEET_REGISTRY_CA_PATH` | `/app/certs/ca.crt` | Docker registry CA 憑證路徑（上線用途） |
| `FLEET_RECONCILER_ENABLED` | `true` | 是否啟動 Plugin Workload 協調器背景迴圈 |
| `FLEET_RECONCILER_INTERVAL` | `30` | 協調器迴圈間隔（秒） |
| `FLEET_QUARANTINE_COOLDOWN_HOURS` | `6` | 節點 QUARANTINE 後冷卻時間（小時） |
| `FLEET_QUARANTINE_MAX_RETRIES` | `3` | QUARANTINE 最大重試次數 |
| `FLEET_TREND_WINDOW_SIZE` | `48` | 心跳趨勢分析滑動視窗大小 |
| `FLEET_REVALIDATION_INTERVAL_HOURS` | `24` | 週期性重新驗證間隔（小時） |
| `FLEET_GATEWAY_URL` | `https://gateway:8000` | Gateway URL（部署上下文 inference_base_url 建構） |
| `FLEET_CONSOLE_ORIGIN` | — | Console App Origin（CORS 設定） |
| `FLEET_AGENT_NETWORK_CIDR` | `172.20.0.0/16` | Docker 網路 CIDR（Agent App 網路設定） |
| `FLEET_LOG_LEVEL` | `INFO` | 日誌等級：`DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `XPARSE_REQUIRE_ACTIVATION_CODE` | `false` | 節點上線是否強制激活碼（BOOTSTRAP-01 前置條件） |
| `HF_TOKEN` | — | HuggingFace 存取 token（部署時注入容器 env，不存 YAML） |

---

## 9. 關聯文件索引

### ADR（架構決策記錄）

| ADR | 主題 | 影響模組 |
|-----|------|---------|
| ADR-073 | IAM 優先認證（Bearer token 驗證流程） | `auth.py`、全部 routes |
| ADR-093 | 執行安全不變量（5 個 cross-system invariants） | 全部狀態變更路徑 |
| ADR-102 M4/M5 | 工作負載排程（CPU 優先、GPU 備援放置） | `scheduler.py`、`routes/workloads.py`、`routes/node_ops.py` |
| ADR-110 | Agent App 部署（Phase 3c 上游端點） | `routes/apps.py` |
| ADR-112 | 節點驗證觸發協議 | `routes/validation.py`、`server_verifier.py` |
| ADR-114 | 節點生命週期狀態機（REGISTERED→ACTIVE 7 種狀態） | `fleet_state.py`、`routes/nodes.py` |
| ADR-128 | 多模式節點部署（Bootstrap 上線流程） | `routes/onboarding.py`、`deploy_artifacts/` |
| ADR-129 | 每部署端點（per-deployment endpoint） | `routes/apps.py`、`fleet_state.py` |
| ADR-133 | Docker 網路命名規則 | `routes/apps.py` |
| ADR-136 | Sidecar 反向代理（Agent App 側車 nginx） | `routes/apps.py` |
| ADR-140 | 生命週期掛鉤 + 卷掛載（D-3、D-8） | `routes/apps.py` |
| ADR-143 | 首選節點覆蓋（preferred_node_id） | `routes/apps.py`、`scheduler.py` |
| ADR-145 | Plugin Workload 協調器（Observe→Act→Verify） | `reconciler.py`、`reconciliation_models.py`、`routes/plugin_specs.py` |
| ADR-156 | Port 登錄 M5 協調（差分 + 策略應用） | `port_registry.py`、`routes/ports.py` |
| ADR-157 | 權重規格 + HuggingFace token（§D7） | `models.py`、`routes/deploy.py` |
| ADR-158 | 部署意圖 + 目錄 L2（IAM Catalog 協調） | `model_catalog_reconciler.py`、`routes/deployments.py`、`routes/catalog.py` |
| ADR-160 | 動態 Port 分配（M4 準備，真值表） | `port_registry.py`、`routes/apps.py`、`routes/ports.py` |
| ADR-162 | 激活碼商業模式（節點上線授權） | `routes/onboarding.py` |
| ADR-188 | Registry Auth 注入（`registry_auth` 欄位） | `routes/apps.py` |

### PRD（產品需求文件）

| PRD | 主題 | 影響模組 |
|-----|------|---------|
| PRD-057 | 群組親緣性過濾（group_affinity） | `fleet_state.py`、`routes/nodes.py` |
| PRD-079 | 驗證進度摘要（ValidationSummary） | `routes/validation.py`、`server_verifier.py`、`models.py` |
| PRD-080 | 活躍部署追蹤（active_deployments） | `routes/heartbeat.py`、`runtime_event_forwarder.py`、`models.py` |
| PRD-098 | 多模式節點部署 | `routes/onboarding.py` |
| PRD-102 | 排程器整合（容量報告） | `scheduler_relay.py` |
| PRD-110 | Agent App 部署（應用端點模型） | `routes/apps.py` |
| PRD-115 | Plugin Workload 協調 | `reconciler.py`、`routes/plugin_specs.py` |
| PRD-126 | Port 登錄（pool / reserve / allocate） | `port_registry.py`、`routes/ports.py` |
| PRD-128 P3a | 模型目錄瀏覽（IAM L2 Catalog） | `model_catalog_reconciler.py`、`routes/catalog.py` |
| PRD-128 P3b | 部署意圖 CRUD（Fleet 代理 IAM） | `routes/deployments.py` |
| PRD-128 P4a | 部署事件轉發（相位轉換至 IAM） | `runtime_event_forwarder.py` |
| PRD-131 | 硬體激活碼（節點上線授權） | `routes/onboarding.py`、`lib/fingerprint.py`、`deploy_artifacts/` |

### SPEC（行為規格）

| SPEC | 主題 | 影響模組 |
|------|------|---------|
| SPEC-076 | 過期 API Key 寬限期（快取 TTL 縮短） | `auth.py` |
| SPEC-093 | 節點生命週期（7 種狀態 + 轉移規則 + 可路由端點） | `fleet_state.py`、`routes/nodes.py` |
| SPEC-108 | Plugin Spec CRUD（樂觀鎖 via generation） | `routes/plugin_specs.py`、`reconciliation_models.py` |
| SPEC-126 | Port 登錄 & 分配（INV-156-3：bind 一次精確） | `port_registry.py`、`routes/ports.py` |
| SPEC-153 §8 | 激活碼協議（BOOTSTRAP-01~04 四步驟） | `routes/onboarding.py` |

---

## 10. 規模統計

### 核心模組行數（前 30 大）

| 模組 | 行數 |
|------|------|
| `fleet_state.py` | 2,262 |
| `routes/onboarding.py` | 729 |
| `port_registry.py` | 679 |
| `routes/ports.py` | 601 |
| `reconciler.py` | 565 |
| `routes/apps.py` | 511 |
| `catalog_cli.py` | 454 |
| `routes/deployments.py` | 403 |
| `deploy_artifacts/generator.py` | 397 |
| `model_catalog.py` | 369 |
| `models.py` | 358 |
| `model_catalog_reconciler.py` | 356 |
| `runtime_event_forwarder.py` | 340 |
| `deploy_artifacts/session.py` | 321 |
| `routes/node_ops.py` | 318 |
| `reconciliation_models.py` | 312 |
| `routes/deploy.py` | 311 |
| `server_verifier.py` | 299 |
| `scheduler.py` | 292 |
| `trend_analyzer.py` | 260 |
| `config.py` | 235 |
| `routes/fleet.py` | 229 |
| `routes/heartbeat.py` | 222 |
| `routes/nodes.py` | 208 |
| `app.py` | 206 |
| `command_queue.py` | 175 |
| `routes/validation.py` | 150 |
| `routes/services.py` | 147 |
| `auth.py` | 140 |
| `service_registry.py` | 128 |

### 整體統計

| 項目 | 數量 |
|------|------|
| Python 原始檔（含測試） | 89 個 |
| 總程式碼行數（含測試） | 22,846 行 |
| API 路由模組 | 17 個 |
| 測試檔案 | 40+ 個 |
| 對外 API 端點群組（A~N） | 14 組 |
| 對外 HTTP 呼叫連線 | 6 條 |
| 關聯 ADR 數量 | 19 個 |
| 關聯 PRD 數量 | 12 個 |
| 關聯 SPEC 數量 | 5 個 |
| 重要環境變數 | 27 個 |
| 關鍵類別 | 18 個 |

---

*報告由 Claude Code 自動生成，基於 `xparse_fleet/fleet/` 原始碼（截至 2026-05-29）。*
