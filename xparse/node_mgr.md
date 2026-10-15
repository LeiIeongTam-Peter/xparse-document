# xparse_node_mgr — 技術報告

> **生成日期**：2026-05-29
> **版本**：`APP_VERSION = "0.1.0"` (`core/config.py:15`)
> **對應程式碼路徑**：`xparse_node_mgr/`

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
| **類型** | Backend — Node Runtime Agent（`agentd`） |
| **框架** | FastAPI + uvicorn（Python 3.12） |
| **部署方式** | Docker container，掛載 host docker socket（`/var/run/docker.sock`） |
| **監聽協議** | HTTP（REST），預設 port `8080` |
| **面向對象** | Fleet 控制平面（遠端命令接收）、Node 本地操作員（直接 API 呼叫） |
| **職責** | GPU 節點的 Runtime 控制層：vLLM 部署、Sandbox 生命週期、Agent App 建立、模型下載、節點驗證、Plugin 同步 |

### 架構定位

`xparse_node_mgr` 是**節點端的輕量控制平面**，在整個 Xparse 系統中扮演以下角色：

- **向上（Fleet）**：週期性發送心跳，接收遠端命令（`pending_commands`），回報執行結果
- **向下（Docker）**：透過 Docker socket 管理所有本地容器（vLLM 推理容器、Sandbox、Agent App、Sidecar）
- **側向（IAM）**：查詢 Skill mount plan、取得 App credential
- **本地狀態**：透過 `state.json`（JSONL 事件日誌 + 單一 JSON 狀態檔）作為唯一狀態來源（ADR-093 不變量 #3）

---

## 2. 資料夾結構總覽

```
xparse_node_mgr/
├── __init__.py                      # 套件初始化
├── server.py                        # FastAPI app 入口點，註冊 routers，定義 lifespan
├── utils.py                         # 公用工具：auth()、sh()、now_iso()、resolve_endpoint()
├── requirements.txt                 # Python 依賴清單
├── Dockerfile                       # 容器映像定義
│
├── core/                            # 核心業務邏輯模組
│   ├── __init__.py
│   ├── config.py                    # 環境變數驅動的配置單例（所有 env var 在此定義）
│   ├── state.py                     # 原子性 JSON 狀態持久化 + 審計事件日誌
│   ├── heartbeat.py                 # Fleet 心跳迴圈 + 遠端命令執行分派器（最核心）
│   ├── instance_manager.py          # vLLM 容器生命週期（state machine）
│   ├── sandbox_runtime.py           # Sandbox 運行時單例（共享 Use Case 物件）
│   ├── download_manager.py          # 模型背景下載管理（子程序 + 狀態機）
│   ├── watchdog.py                  # vLLM 實例健康監控（自動重啟）
│   ├── resource_probe.py            # GPU / 磁碟 / RAM 探測（pynvml）
│   ├── model_estimator.py           # HuggingFace 模型 VRAM 估算
│   ├── iam_mounts.py                # IAM mount list → Docker volumes 轉換
│   ├── skill_mounts.py              # IAM Skill mount plan 取得 + 安全驗證
│   └── plugin_sync.py               # Plugin 模板自同步（image → host 協調）
│
├── handlers/                        # FastAPI route handlers（HTTP 層薄包裝）
│   ├── __init__.py
│   ├── health.py                    # GET /livez, GET /v1/health
│   ├── catalog.py                   # GET /v1/catalog/models（本地 manifest 讀取）
│   ├── gpu.py                       # GET /v1/gpu/info（nvidia-smi + Prometheus fallback）
│   ├── service.py                   # vLLM docker compose 服務生命週期（5 個端點）
│   ├── sandbox.py                   # Sandbox 生命週期（5 個端點，ADR-103 特權防護）
│   ├── model_manager.py             # 模型生命週期（資源探測、估算、下載、serving，14 個端點）
│   ├── nemoclaw.py                  # NemoClaw CLI 整合（RFC 1123 命名、閘門注入）
│   └── lifecycle.py                 # Lifecycle hook 執行器（ADR-140 D-3）
│
├── validation/                      # 節點驗證框架
│   ├── __init__.py
│   ├── protocol.py                  # 測試協議（TestResult / ValidationTest / ValidationReport）
│   ├── profiles.py                  # Profile → 測試清單映射（minimal / standard / performance / hardened / burn_in）
│   ├── runner.py                    # 測試執行器（循序 + 超時 + 進度回呼）
│   └── tests/                       # 各測試實作
│       ├── identity.py              # Token 驗證（POST /v1/fleet/heartbeat 探測）
│       ├── connectivity.py          # 服務連通性測試
│       ├── heartbeat.py             # 心跳端點回應測試
│       ├── resource.py              # 磁碟 / RAM / GPU 可用性
│       ├── latency.py               # 推理延遲測試
│       ├── gpu_benchmark.py         # GPU 吞吐量（TFLOPS）
│       ├── gpu_burnin.py            # GPU 持續壓力測試
│       ├── streaming_stability.py   # SSE Streaming 穩定性
│       ├── container_readiness.py   # 容器健康檢查
│       ├── energy_benchmark.py      # 能耗基準測試（含進度追蹤）
│       └── energy_profile.py        # 能耗 profile 量測
│
├── scripts/                         # Shell 工具腳本（容器內 PATH）
│   ├── build_plugin_manifest.py     # Plugin manifest 建立（build-time）
│   ├── compose_render.sh            # Docker Compose YAML 渲染（stdin JSON → compose YAML）
│   ├── compose_up.sh                # Docker compose up 包裝
│   ├── compose_down.sh              # Docker compose down 包裝
│   ├── gpu_probe.sh                 # GPU 探測（nvidia-smi）
│   ├── health_wait.sh               # 等待服務健康（輪詢 /health）
│   ├── inspect.sh                   # Docker compose 容器 ID 取得
│   └── port_alloc.sh                # Host port 分配（iproute2 ss）
│
└── tests/                           # 單元與整合測試
    ├── conftest.py                  # pytest 設定 + fixture
    ├── test_health.py
    ├── test_heartbeat.py            # 心跳 + 命令處理（最大，667 行）
    ├── test_sandbox_handler.py
    ├── test_contract.py
    ├── test_model_lifecycle.py      # 模型生命週期（628 行）
    ├── test_validation_runner.py
    ├── test_validation_profiles.py
    ├── test_gpu_benchmark.py
    ├── test_gpu_burnin.py
    ├── test_streaming_stability.py
    ├── test_energy_profile.py
    ├── test_container_readiness.py
    ├── test_deployment_progress.py
    └── test_download_manager_artifact_store.py
```

---

## 3. 各模組功能說明

### 3.1 核心模組（`core/`）

| 模組 | 主要職責 | 關鍵 ADR/PRD |
|------|---------|-------------|
| `config.py` | 所有環境變數在 import 時讀取，提供全局常數；`ensure_runtime_dirs()` 初始化目錄與 state.json | — |
| `state.py` | 以 `filelock` + temp-rename 實作原子性 state.json 讀寫；`log_event()` 追加 JSONL 審計日誌；`StateBackedSandboxStore` 實作 SandboxStore protocol | ADR-093 #1 #3 |
| `heartbeat.py` | Fleet 心跳迴圈（每 `FLEET_HEARTBEAT_INTERVAL` 秒）；`_COMMAND_HANDLERS` 分派表執行遠端命令；payload 包含 services/workloads/active_deployments/host_ports_observed | PRD-062, ADR-102 M4 |
| `instance_manager.py` | vLLM 容器生命週期狀態機（starting→running→stopping→stopped/error）；`serve_model()` 分配 port、啟動容器、生成異步健康輪詢任務 | ADR-146, PRD-116 |
| `sandbox_runtime.py` | 全域 Singleton：DockerRuntime + StateBackedSandboxStore + 6 個 Use Case；心跳命令路徑與 HTTP 路徑共享同一實例（ADR-093 #5） | ADR-102 M3/M4 |
| `download_manager.py` | 模型下載狀態機（pending→downloading→completed/failed/cancelled）；`_artifact_store_worker()` 透過 MaterializeArtifactUseCase 子程序下載 | PRD-116, PRD-129 P2.6 |
| `watchdog.py` | 背景輪詢 vLLM 實例健康；非暫態錯誤（CUDA OOM、driver 缺失）標記為永久失敗；暫態失敗指數退避重啟（最多 `WATCHDOG_MAX_RESTARTS` 次） | WD-01~WD-04 |
| `resource_probe.py` | `get_gpus()` 透過 pynvml 探測 NVIDIA GPU；`get_resource_report()` 聚合 GPU/磁碟/RAM | RES-01~RES-04 |
| `model_estimator.py` | 從 HuggingFace config 衍生參數量；計算模型 bytes + KV cache（20% overhead）+ 最少 GPU 數量 | EST-01~EST-04 |
| `iam_mounts.py` | IAM mount list（含 source/target/mode/kind）→ Docker volume dict；多目標同源以 `"source@target"` 合成鍵避免衝突 | Issue #221 Phase 1b |
| `skill_mounts.py` | 向 IAM 取得 Skill mount plan；拒絕 Layer 2 root 以外的 host_path（INV-122-19）；所有 volume 唯讀（INV-101-24）；fail-open | ADR-122 D10, SPEC-101 Phase 7 |
| `plugin_sync.py` | 啟動時將 image 內 `/app/plugins/` 同步到 host plugin dir；版本 + 雜湊快速路徑；失敗降級不阻斷啟動 | PRD-137, ADR-165 |

### 3.2 Handler 模組（`handlers/`）

| 模組 | 主要職責 | 端點數 | 關鍵 ADR/PRD |
|------|---------|--------|-------------|
| `health.py` | `/livez`（匿名）+ `/v1/health`（需 Bearer）兩用健康檢查 | 2 | Docker HEALTHCHECK 相容 |
| `catalog.py` | 讀取本地 catalog manifest YAML，回傳模型清單 | 1 | PRD-128 legacy path |
| `gpu.py` | nvidia-smi 腳本探測 GPU；fallback 解析 Prometheus metrics（nvidia-gpu-exporter / dcgm-exporter） | 1 | RES-01~04 |
| `service.py` | vLLM docker compose 服務 apply/list/get/profile/logs/delete；支援 legacy manifest 與 catalog-driven 兩種模式；自動生成 PlanResolver 相容的 model profile YAML | 6 | PRD-128, ADR-157 |
| `sandbox.py` | Sandbox create/list/get/exec/destroy；Pydantic schema 層拒絕 `privileged=true` 和 `cap_add`（ADR-103） | 5 | ADR-102 M3, ADR-103 |
| `model_manager.py` | 資源探測、VRAM 估算、模型下載（202）、本地模型管理、vLLM serving、實例查詢與日誌 | 14 | PRD-116, ADR-146 |
| `nemoclaw.py` | NemoClaw CLI 整合；RFC 1123 命名；`_OPENCLAW_GATEWAY_GUARD_JS` monkey-patch（RCA-005）；per-group sidecar | ADR-123, SPEC-102 | INV-102-1~6 |
| `lifecycle.py` | Lifecycle hook 執行（pod/container/host 三種 context）；序列執行；critical hook 失敗立即停止；非 critical 記錄繼續；背景 fork；60s 超時 | — | ADR-140 D-3 |

### 3.3 驗證框架（`validation/`）

| 模組 | 主要職責 |
|------|---------|
| `protocol.py` | `TestResult`（passed/category/message/details/duration_ms）、`ValidationTest` Protocol、`ValidationReport.compute_verdict()`（common → REJECTED，specialized → QUARANTINED） |
| `profiles.py` | Profile 名稱 → 測試清單映射：`minimal`（T1）、`standard`（T2）、`performance`（T3）、`hardened`（T4）、`burn_in`（長時間壓測） |
| `runner.py` | 循序執行所有測試；每項測試有個別超時；`on_progress` 回呼；所有例外均被捕獲不上拋 |

---

## 4. 對外 API 端點完整列表

所有 `/v1/*` 端點需要 `Authorization: Bearer <XPARSE_TOKEN>` header。`/livez` 為匿名端點。

### 4.1 Health（`handlers/health.py`）

| 方法 | 路徑 | Auth | 用途 | Response 範例 |
|------|------|------|------|--------------|
| `GET` | `/livez` | 無 | Docker HEALTHCHECK 存活探測 | `{"status":"alive","version":"0.1.0","time":"...","fleet_configured":true}` |
| `GET` | `/v1/health` | Bearer | 操作員健康查詢，含 endpoint_mode | `{"status":"ok","version":"0.1.0","time":"...","endpoint_mode":"host_port"}` |

### 4.2 Catalog（`handlers/catalog.py`）

| 方法 | 路徑 | Auth | 用途 | Response 範例 |
|------|------|------|------|--------------|
| `GET` | `/v1/catalog/models` | Bearer | 列出本地 catalog 目錄下所有模型 manifest | `{"models": [...]}` |

### 4.3 GPU（`handlers/gpu.py`）

| 方法 | 路徑 | Auth | 用途 | Response 範例 |
|------|------|------|------|--------------|
| `GET` | `/v1/gpu/info` | Bearer | 探測所有 NVIDIA GPU 資訊 | `{"gpus":[{"index":0,"name":"A100","memory_total_mib":40960,...}]}` |

### 4.4 Services — vLLM（`handlers/service.py`）

| 方法 | 路徑 | Auth | 用途 |
|------|------|------|------|
| `POST` | `/v1/services/apply` | Bearer | 部署 vLLM docker compose 服務（legacy manifest 或 catalog-driven） |
| `GET` | `/v1/services` | Bearer | 列出所有已部署服務（含即時容器狀態） |
| `GET` | `/v1/services/{name}` | Bearer | 取得特定服務詳情 |
| `GET` | `/v1/services/{name}/profile` | Bearer | 取得 PlanResolver 相容的 model profile YAML |
| `GET` | `/v1/services/{name}/logs` | Bearer | 取得容器日誌（`?tail=200`） |
| `POST` | `/v1/services/delete` | Bearer | 停止並刪除服務 |

**`POST /v1/services/apply` Request Body：**

```json
{
  "name": "qwen2-7b",
  "model": "Qwen/Qwen2-7B-Instruct",
  "tp": 1,
  "image": "vllm/vllm-openai:v0.6.1",
  "weights": {"type": "hf_hub", "repo": "Qwen/Qwen2-7B-Instruct"},
  "extra_args": ["--max-model-len=8192"],
  "env": {"HF_HOME": "/cache"}
}
```

**`POST /v1/services/apply` Response（成功）：**

```json
{
  "service": {
    "name": "qwen2-7b",
    "model": "Qwen/Qwen2-7B-Instruct",
    "status": "ready",
    "endpoint": "http://ai-server:40001",
    "host_port": 40001,
    "container_port": 8000,
    "image": "vllm/vllm-openai:v0.6.1",
    "gpu_indices": [0],
    "created_at": "2026-05-29T10:00:00Z"
  },
  "model_profile": {
    "profile_name": "demo_qwen2-7b",
    "profile_yaml": "profiles:\n  demo_qwen2-7b:\n ...",
    "gateway_synced": true
  }
}
```

### 4.5 Sandboxes（`handlers/sandbox.py`）

| 方法 | 路徑 | Auth | Status Code | 用途 |
|------|------|------|-------------|------|
| `POST` | `/v1/sandboxes` | Bearer | 201 | 建立並啟動 sandbox 容器 |
| `GET` | `/v1/sandboxes` | Bearer | 200 | 列出所有 sandbox（`?tenant_id=xxx` 過濾） |
| `GET` | `/v1/sandboxes/{sandbox_id}` | Bearer | 200 | 取得單一 sandbox 即時狀態 |
| `DELETE` | `/v1/sandboxes/{sandbox_id}` | Bearer | 204 | 停止並移除 sandbox 容器 |
| `POST` | `/v1/sandboxes/{sandbox_id}/exec` | Bearer | 200 | 在 sandbox 內執行命令 |

**`POST /v1/sandboxes` Request Body：**

```json
{
  "tenant_id": "tenant-uuid",
  "image": "python:3.11-slim",
  "name": "code-runner-1",
  "memory_limit": "512m",
  "cpu_quota": 100000,
  "pids_limit": 256,
  "network_mode": "none",
  "environment": {"PYTHONPATH": "/app"},
  "volumes": {"/host/path": {"bind": "/app", "mode": "ro"}}
}
```

> **注意**：`privileged: true` 或 `cap_add: [...]` 會被 schema 層立即以 422 拒絕（ADR-103）。

**`POST /v1/sandboxes/{id}/exec` Request Body：**

```json
{
  "command": ["python", "-c", "print('hello')"],
  "sandboxed": true,
  "language": "python"
}
```

**Exec Response：**

```json
{
  "exit_code": 0,
  "stdout": "hello\n",
  "stderr": ""
}
```

### 4.6 Model Manager（`handlers/model_manager.py`）

| 方法 | 路徑 | Auth | 用途 |
|------|------|------|------|
| `GET` | `/v1/resources` | Bearer | 完整資源報告（GPU + 磁碟 + RAM） |
| `GET` | `/v1/resources/gpus` | Bearer | GPU 詳細資訊陣列（503 when unavailable） |
| `POST` | `/v1/models/estimate` | Bearer | VRAM 需求估算（從 HuggingFace config） |
| `POST` | `/v1/models/download` | Bearer / 202 | 啟動背景下載任務，回傳 `task_id` |
| `GET` | `/v1/models/downloads` | Bearer | 列出所有下載任務 |
| `GET` | `/v1/models/downloads/{task_id}` | Bearer | 查詢下載狀態 |
| `DELETE` | `/v1/models/downloads/{task_id}` | Bearer | 取消下載並清理暫存 |
| `GET` | `/v1/models/local` | Bearer | 列出本地已下載模型 |
| `DELETE` | `/v1/models/local/{model_id}` | Bearer | 刪除本地模型 |
| `POST` | `/v1/models/serve` | Bearer | 啟動 vLLM 容器 serving 本地模型 |
| `DELETE` | `/v1/models/serve/{instance_id}` | Bearer | 停止 vLLM 實例 |
| `GET` | `/v1/models/instances` | Bearer | 列出所有 serving 實例 |
| `GET` | `/v1/models/instances/{instance_id}` | Bearer | 取得實例詳情 |
| `GET` | `/v1/models/instances/{instance_id}/logs` | Bearer | 容器日誌（`?tail=200&follow=false`） |

**`POST /v1/models/estimate` Request / Response：**

```json
// Request
{"repo_id": "meta-llama/Llama-3-8B", "dtype": "fp16", "hf_token": "hf_xxx"}

// Response
{
  "repo_id": "meta-llama/Llama-3-8B",
  "num_parameters": 8000000000,
  "dtype": "fp16",
  "model_bytes": 16000000000,
  "kv_cache_bytes": 3200000000,
  "total_bytes": 19200000000,
  "min_gpus_required": 1,
  "recommended_tp": 1
}
```

**`POST /v1/models/download` Response（202）：**

```json
{"task_id": "task-uuid", "status": "pending", "repo_id": "meta-llama/Llama-3-8B"}
```

---

## 5. 服務通訊全貌

### 5.1 ASCII 架構圖

```
                    ┌─────────────────────────────────────────────────────┐
                    │              xparse_node_mgr (agentd)               │
                    │                                                     │
  ┌────────────┐   │  ┌─────────────┐    ┌──────────────────────────┐   │
  │  Fleet API  │◄──┼──│  heartbeat  │    │  FastAPI HTTP Server     │   │
  │  :8090     │   │  │  loop       │    │  (uvicorn :8080)          │   │
  └────────────┘   │  │  (async)    │    │                          │   │
       │           │  └─────┬───────┘    │  /livez                  │   │
       │           │        │            │  /v1/health              │   │
       │           │        │ pending_   │  /v1/catalog/models      │   │  ◄── Fleet / Operator
       │           │        │ commands   │  /v1/gpu/info            │   │
       │           │        ▼            │  /v1/services/*          │   │
       │           │  ┌─────────────┐   │  /v1/sandboxes/*         │   │
       │           │  │  Command    │   │  /v1/models/*            │   │
       │           │  │  Handlers   │   │  /v1/resources/*         │   │
       │           │  │  dispatch   │   └──────────────────────────┘   │
       │           │  └─────┬───────┘                                   │
       │           │        │                                           │
  ┌────────────┐   │  ┌─────▼───────────────────────────────────────┐  │
  │  IAM API    │◄──┼──│           Docker Socket                     │  │
  │  (IAM svc)  │   │  │  /var/run/docker.sock                       │  │
  └────────────┘   │  │                                             │  │
                    │  │  ┌────────────┐  ┌──────────┐  ┌────────┐  │  │
  ┌────────────┐   │  │  │ vLLM       │  │ Sandbox  │  │ Agent  │  │  │
  │  HF Hub    │◄──┼──│  │ Container  │  │ Container│  │  App   │  │  │
  │ (internet)  │   │  │  │ :40001-   │  │          │  │ + Sidecar│ │  │
  └────────────┘   │  │  │  40099    │  │          │  │        │  │  │
                    │  │  └────────────┘  └──────────┘  └────────┘  │  │
  ┌────────────┐   │  └─────────────────────────────────────────────┘  │
  │ NVIDIA GPU │   │                                                     │
  │ Exporter  │◄──┼──  /metrics (Prometheus, optional fallback)         │
  │ (optional) │   │                                                     │
  └────────────┘   └─────────────────────────────────────────────────────┘

  Gateway      ◄──────── /v1/chat/completions  (vLLM container, direct)
  (bustream)
```

**連線方向圖例：**
- `►` 主動發起（outbound request）
- `◄` 接收請求（inbound）
- `◄──►` 雙向

### 5.2 通訊連結總表

| 對象 | 類型 | 協議 | 方向 | 發起點 | 失敗行為 |
|------|------|------|------|--------|---------|
| Fleet API | Backend | HTTP/JSON | 外送（主動心跳） | `core/heartbeat.py` | fail-open，記錄 warning，下個週期重試 |
| Fleet API（port bind） | Backend | HTTP/JSON | 外送 | `core/heartbeat.py:403` | best-effort，失敗僅 log，不阻斷容器創建 |
| Fleet API（port release） | Backend | HTTP/JSON | 外送 | `core/heartbeat.py:450` | best-effort，失敗僅 log |
| IAM API（skill mounts） | Backend | HTTP/JSON | 外送 | `core/skill_mounts.py:88` | fail-open，回傳空 dict（INV-101-23） |
| Docker Socket | Backend | Unix Socket | 本地 | `xparse_container_platform` | fail-fast，ContainerRuntimeError → HTTP 500 |
| HuggingFace Hub | External | HTTPS | 外送 | `core/download_manager.py` | 失敗標記 task 為 failed state |
| NVIDIA GPU Exporter | Backend | HTTP/Prometheus | 外送（fallback） | `handlers/gpu.py` | fail-open，若無法取得則回 503 |
| vLLM 容器（健康檢查） | Backend | HTTP | 本地 | `core/instance_manager.py` | timeout → state: error；WATCHDOG_HEALTH_TIMEOUT 秒後放棄 |
| 本地 FastAPI（命令自呼叫） | Backend | HTTP | 本地回送 | `core/heartbeat.py:364` | fail-fast，HTTP 非 200 → 回報 failed 命令結果 |
| Gateway（model profile） | Backend | 檔案系統 | 本地寫入 | `handlers/service.py:384` | fail-open，profile 寫入失敗只記錄 event，不影響部署 |

### 5.3 各連線詳細說明

---

#### 連線 1：Fleet 心跳（最核心）

- **發起點**：`core/heartbeat.py`（`heartbeat_loop()` async task）
- **URL**：`{FLEET_API_URL}/v1/fleet/heartbeat`
  - env var：`FLEET_API_URL`（例：`http://fleet-svc:8090/v1/fleet/heartbeat`）
- **觸發頻率**：每 `FLEET_HEARTBEAT_INTERVAL` 秒（預設 30s）
- **Timeout**：60 秒（httpx client 層）
- **TLS 控制**：`FLEET_INSECURE_TLS=true` 時跳過憑證驗證

**Request：**

```
POST {FLEET_API_URL}/v1/fleet/heartbeat
Authorization: Bearer {FLEET_NODE_KEY}
Content-Type: application/json

{
  "node_id": "node-uuid",
  "timestamp": "2026-05-29T10:00:00Z",
  "gpus": [{"index": 0, "name": "A100", "memory_total_mib": 40960, ...}],
  "services": [{"name": "qwen2-7b", "status": "running", "endpoint": "..."}],
  "group_affinity": ["group-a", "group-b"],
  "capabilities": {"nemoclaw": true, "sandbox": true},
  "command_results": [{"command_id": "cmd-uuid", "status": "done", "result": {...}}],
  "workloads": [{"workload_id": "sandbox-uuid", "workload_type": "agent_app", "status": "running", ...}],
  "capacity": {"disk_free_bytes": 100000000000, "ram_available_bytes": 50000000000},
  "active_deployments": [{"command_id": "cmd-uuid", "model_code": "llama3", "phase": "pulling", "percent": 10}],
  "host_ports_observed": {40001: "vllm-qwen2-7b"}
}
```

**Response（200）：**

```json
{
  "pending_commands": [
    {
      "command_id": "cmd-uuid",
      "action": "create_workload",
      "params": {
        "workload_type": "agent_app",
        "workload_id": "app-uuid",
        "image": "registry.io/app:latest",
        ...
      }
    }
  ]
}
```

- **失敗行為**：`except Exception` → `logger.warning()`；下個 sleep 週期繼續重試（fail-open）

---

#### 連線 2：Fleet Port Allocation Bind

- **發起點**：`core/heartbeat.py:_fleet_bind_port_allocation()` 行 ~403
- **URL**：`{FLEET_API_URL}/v1/fleet/nodes/{node_id}/ports/allocations/{allocation_id}/bind`
- **方法**：`POST`
- **Timeout**：10 秒

**Request：**

```
POST {FLEET_API_URL}/v1/fleet/nodes/{node_id}/ports/allocations/{allocation_id}/bind
Authorization: Bearer {FLEET_NODE_KEY}
Content-Type: application/json

{"container_id": "abc123def456", "node_id": "node-uuid"}
```

- **失敗行為**：best-effort，False on any failure；失敗僅 log，不回滾容器

---

#### 連線 3：IAM Skill Mount Plan

- **發起點**：`core/skill_mounts.py:fetch_skill_volumes()` 行 ~88
- **URL**：`{IAM_API_URL}/iam/applications/{application_uuid}/skills/mount-plan`
  - env var：`IAM_API_URL`（例：`http://iam-svc:8000`）
- **方法**：`GET`
- **Auth**：`Authorization: Bearer {IAM_API_KEY}`

**Response：**

```json
{
  "volumes": [
    {
      "host_path": "/data/xparse/app-deployed-skills/skill-uuid/files",
      "container_path": "/app/skills",
      "read_only": true
    }
  ]
}
```

- **失敗行為**：fail-open，任何 Exception 回傳空 dict（INV-101-23）
- **安全驗證**：`host_path` 必須在 `SKILL_LAYER2_ROOT` 下，否則拒絕（INV-122-19）

---

#### 連線 4：Docker Socket

- **發起點**：`xparse_container_platform.DockerRuntime`（透過 `sandbox_runtime.py` singleton）
- **Socket**：`/var/run/docker.sock`（Docker SDK，sync `docker.from_env()` + async `aiodocker`）
- **操作類型**：
  - `container.run()` — 建立並啟動容器
  - `container.stop()` / `container.remove()` — 銷毀容器
  - `container.exec_run()` — 在容器內執行命令
  - `containers.list()` — 列出 running 容器（heartbeat 用）
  - `docker inspect` — 容器狀態探測（`handlers/service.py:109`，timeout 5s）
  - `docker ps` — port binding 列舉（`heartbeat.py:_build_host_ports_observed()`）
- **失敗行為**：`ContainerRuntimeError` → HTTP 500；Docker 不可用時 fail-fast

---

#### 連線 5：HuggingFace Hub（模型下載）

- **發起點**：`core/download_manager.py:_artifact_store_worker()`
- **協議**：HTTPS（透過 `huggingface_hub.snapshot_download()`）
- **Auth**：`HF_TOKEN` env var 或 IAM ProviderCredential（fallback chain）
- **Timeout**：無限（子程序可被 cancel）

**失敗行為**：download task state → `failed`，`error_message` 記錄原因

---

#### 連線 6：NVIDIA GPU Exporter（Prometheus，可選 fallback）

- **發起點**：`handlers/gpu.py:_probe_exporter_fallback()`
- **URL**：`{NVIDIA_EXPORTER_URL}/metrics`
  - env var：`NVIDIA_EXPORTER_URL`（例：`http://nvidia-exporter:9835`）
- **方法**：`GET`
- **格式**：Prometheus text format

**支援的 metric 名稱：**

| Exporter 類型 | Metric |
|--------------|--------|
| nvidia-gpu-exporter | `nvidia_gpu_memory_total_bytes`, `nvidia_gpu_memory_used_bytes`, `nvidia_gpu_power_usage_milliwatts`, `nvidia_gpu_temperature_celsius`, `nvidia_gpu_utilization_percent` |
| dcgm-exporter（legacy） | `DCGM_FI_DEV_FB_TOTAL`, `DCGM_FI_DEV_FB_USED`, `DCGM_FI_DEV_POWER_USAGE`, `DCGM_FI_DEV_GPU_TEMP`, `DCGM_FI_DEV_GPU_UTIL` |

- **失敗行為**：fail-open，若 `NVIDIA_EXPORTER_URL` 未設定則跳過；解析失敗回 503

---

#### 連線 7：本地 FastAPI 自呼叫（命令自代理）

- **發起點**：`core/heartbeat.py:_handle_deploy()` 行 369、`_handle_undeploy()` 行 391
- **URL**：`http://127.0.0.1:{PORT}/v1/services/apply` 或 `/v1/services/delete`
- **目的**：Fleet 遠端命令透過本地 API 執行（同一進程，保持程式碼複用）
- **Auth**：`Authorization: Bearer {TOKEN}`
- **Timeout**：apply 600s，delete 240s

---

## 6. 請求主流程

### 6.1 Fleet 遠端命令執行流程（最重要）

```
Fleet API                heartbeat_loop()              Command Handler
    │                    (heartbeat.py:2163)            (heartbeat.py)
    │                          │
    │◄────── POST /v1/fleet/heartbeat ─────────────────│
    │                          │
    │────── 200 + pending_commands ────────────────────►│
    │                          │
    │              for cmd in pending_commands:          │
    │                          │──► _execute_command(cmd)
    │                          │         │
    │                          │         ├── action="create_workload"
    │                          │         │       │
    │                          │         │   _handle_create_workload()
    │                          │         │   (heartbeat.py:985)
    │                          │         │       │
    │                          │         │   workload_type dispatch:
    │                          │         │   ├── "sandbox"        → create via sandbox_runtime
    │                          │         │   ├── "agent_app"      → _handle_create_agent_app()
    │                          │         │   ├── "nemoclaw_sandbox"→ _handle_nemoclaw_onboard()
    │                          │         │   └── "sandbox_executor"→ _handle_create_sandbox_executor()
    │                          │         │       │
    │                          │         │   Docker Socket ──► container.run()
    │                          │         │       │
    │                          │         │   state.json ──► save_state()
    │                          │         │       │
    │                          │         │   _pending_command_results.append({status: "done"})
    │                          │         │
    │                          │         └── action="deploy"
    │                          │                 │
    │                          │             _handle_deploy()
    │                          │             (heartbeat.py:329)
    │                          │                 │
    │                          │             POST http://127.0.0.1:8080/v1/services/apply
    │                          │             (本地 FastAPI，600s timeout)
    │                          │                 │
    │                          │             handlers/service.py
    │                          │             compose_render.sh → docker compose up
    │                          │                 │
    │                          │             _pending_command_results.append(result)
    │                          │
    │◄────── POST /v1/fleet/heartbeat (next cycle) ─────│
    │        (含 command_results)
```

### 6.2 vLLM 服務部署主流程（`POST /v1/services/apply`）

```
HTTP Client
    │
    │── POST /v1/services/apply
    │      ├── auth() ─── 驗證 Bearer token (utils.py)
    │      │
    │      ├── [Pre-condition] (ADR-093 #2)
    │      │      ├── load_state() → 確認 service 不重複 (service.py:266)
    │      │      ├── catalog_mode ? _build_catalog_spec() : load_manifest()
    │      │      └── 權重路徑驗證（local_path 模式）
    │      │
    │      ├── assign_gpus() → state 中排除已占用 GPU (handlers/gpu.py)
    │      │
    │      ├── port_alloc.sh → iproute2 ss 取得空閒 host port
    │      │
    │      ├── compose_render.sh (stdin JSON → YAML)
    │      │      └── 寫入 services/{name}/docker-compose.yaml
    │      │
    │      ├── compose_up.sh → docker compose up -d (timeout: 240s)
    │      │
    │      ├── health_wait.sh → 輪詢 {endpoint}/health (timeout: 600s)
    │      │
    │      ├── inspect.sh → 取得 container_id
    │      │
    │      ├── generate_model_profile() → 生成 PlanResolver YAML (service.py:31)
    │      │      └── 若 GATEWAY_PROFILES_DIR 設定 → 寫入 drop-in profile
    │      │
    │      ├── [Post-condition] (ADR-093 #3)
    │      │      └── save_state() + log_event()
    │      │
    │      └── 200 JSON Response
```

### 6.3 Sandbox 建立主流程（`POST /v1/sandboxes`）

```
HTTP Client
    │
    │── POST /v1/sandboxes
    │      ├── CreateSandboxBody.model_validate()
    │      │      ├── _reject_privileged() → privileged=true 422 (ADR-103)
    │      │      └── _reject_cap_add()   → cap_add=[] 422 (ADR-103)
    │      │
    │      ├── auth()
    │      │
    │      ├── CreateSandboxRequest 建構
    │      │
    │      ├── sandbox_runtime.get_create_sandbox().execute(request)
    │      │      │
    │      │      ├── xparse_container_platform.CreateSandboxUseCase
    │      │      │      ├── DockerRuntime.create_container()
    │      │      │      │      └── Docker Socket → container.run()
    │      │      │      └── StateBackedSandboxStore.save()
    │      │      │             └── state.json 原子寫入 (state.py:68)
    │      │      │
    │      │      └── SandboxDTO
    │      │
    │      └── 201 JSON Response
```

---

## 7. 關鍵類別索引

| 類別 / 函數 | 檔案 | 職責 |
|------------|------|------|
| `FastAPI app` | `server.py:46` | 主應用實例，含 lifespan |
| `lifespan()` | `core/heartbeat.py:2187` | 啟動時觸發 plugin sync、heartbeat loop、watchdog |
| `heartbeat_loop()` | `core/heartbeat.py` | async 心跳迴圈，發送 payload + 執行 pending_commands |
| `_COMMAND_HANDLERS` | `core/heartbeat.py` | 命令類型 → handler 分派表 |
| `_handle_create_workload()` | `core/heartbeat.py:985` | workload_type 分派（sandbox / agent_app / nemoclaw 等） |
| `_handle_create_agent_app()` | `core/heartbeat.py:512` | Agent App 容器 + sidecar 建立（含 IAM mounts、Skill mounts、port allocation） |
| `_handle_nemoclaw_onboard()` | `core/heartbeat.py:1376` | NemoClaw sandbox 建立（CLI + gateway guard + lifecycle hooks） |
| `StateBackedSandboxStore` | `core/state.py:120` | SandboxStore protocol 實作，後端為 state.json |
| `load_state()` / `save_state()` | `core/state.py:49/68` | 原子性 JSON 讀寫（temp-rename pattern） |
| `log_event()` | `core/state.py:93` | JSONL 審計事件追加 |
| `ensure_runtime_dirs()` | `core/config.py:110` | 初始化目錄與 state.json 預設結構 |
| `serve_model()` | `core/instance_manager.py:203` | 啟動 vLLM 容器 + 非同步健康輪詢 |
| `Watchdog.run()` | `core/watchdog.py` | 每 WATCHDOG_INTERVAL 秒掃描所有實例健康 |
| `get_resource_report()` | `core/resource_probe.py` | 聚合 GPU + disk + RAM 快照 |
| `estimate_vram()` | `core/model_estimator.py` | VRAM 估算 = model_bytes + kv_cache_bytes（20%） |
| `fetch_skill_volumes()` | `core/skill_mounts.py` | IAM skill mount plan 取得 + 安全驗證 |
| `sync_plugin_templates()` | `core/plugin_sync.py` | image → host plugin 同步（hash-based diff） |
| `generate_model_profile()` | `handlers/service.py:31` | 生成 PlanResolver 相容的 model profile YAML |
| `CreateSandboxBody` | `handlers/sandbox.py:50` | ADR-103 防護 schema（含 field_validator 拒絕特權） |
| `ValidationReport.compute_verdict()` | `validation/protocol.py` | common failure → REJECTED；specialized → QUARANTINED |
| `_build_catalog_spec()` | `handlers/service.py:177` | Fleet catalog 驅動部署的 manifest 合成 |

---

## 8. 重要環境變數

| 變數名稱 | 預設值 | 用途 |
|---------|--------|------|
| `XPARSE_TOKEN` | `"demo-token"` | Bearer token（API 鑑權 + 本地自呼叫） |
| `XPARSE_BIND` | `"0.0.0.0"` | HTTP 監聽位址 |
| `XPARSE_PORT` | `"8080"` | HTTP 監聽 port |
| `XPARSE_BASE_DIR` | repo 根目錄 | catalog / services / runtime 目錄的 base path |
| `XPARSE_SCRIPTS_DIR` | `/app/xparse_node_mgr/scripts` | Shell 腳本目錄（compose render 等） |
| `FLEET_API_URL` | 無（選填） | Fleet API 位址；未設定時不發心跳，開機 warning |
| `FLEET_NODE_ID` | `"local"` | 節點 UUID（fallback：`FLEET_AGENT_ID`） |
| `FLEET_NODE_KEY` | = `XPARSE_TOKEN` | Fleet 心跳認證 token |
| `FLEET_HEARTBEAT_INTERVAL` | `"30"` | 心跳間隔（秒） |
| `FLEET_INSECURE_TLS` | `"false"` | `"true"` 時跳過 Fleet API TLS 驗證 |
| `FLEET_GROUP_AFFINITY` | `""` | 逗號分隔的 group 名稱，心跳 payload 帶入 |
| `FLEET_NODE_EXTERNAL_IP` | `""` | 節點外部 IP（跨節點 endpoint 構建，ADR-136） |
| `IAM_API_URL` | 無（選填） | IAM API 位址（skill mount plan 查詢） |
| `IAM_API_KEY` | `""` | IAM API 認證 token |
| `XPARSE_VLLM_IMAGE` | `"vllm/vllm-openai:latest"` | 預設 vLLM Docker image |
| `XPARSE_VLLM_PORT_START` | `"40001"` | vLLM port 範圍起始 |
| `XPARSE_VLLM_PORT_END` | `"40099"` | vLLM port 範圍終止 |
| `XPARSE_VLLM_HEALTH_TIMEOUT` | `"600"` | vLLM 健康等待超時（秒） |
| `XPARSE_VLLM_GPU_UTIL` | `"0.9"` | vLLM GPU memory utilization |
| `XPARSE_WATCHDOG_INTERVAL` | `"10"` | Watchdog 輪詢間隔（秒） |
| `XPARSE_WATCHDOG_MAX_RESTARTS` | `"5"` | Watchdog 最大重啟次數 |
| `XPARSE_WATCHDOG_HEALTH_FAILURES` | `"3"` | 連續失敗幾次才觸發重啟 |
| `XPARSE_MODEL_CACHE_PATH` | `/var/lib/xparse/models` | 模型下載快取路徑 |
| `XPARSE_GATEWAY_PROFILES_DIR` | 無（選填） | Gateway model profile drop-in 目錄 |
| `XPARSE_ENDPOINT_MODE` | `"host_port"` | endpoint 解析模式（`host_port` / `k8s_service` / `template`） |
| `XPARSE_PUBLIC_HOST` | `"ai-server"` | host_port 模式的公開 hostname |
| `AGENT_APP_NETWORK` | `""` | Agent App 容器的 Docker network 名稱 |
| `NEMOCLAW_CLI_PATH` | `"nemoclaw"` | NemoClaw CLI 執行檔路徑 |
| `OPENSHELL_CLI_PATH` | `"openshell"` | OpenShell CLI 執行檔路徑 |
| `NVIDIA_EXPORTER_URL` | 無（選填） | NVIDIA Prometheus exporter（GPU probe fallback） |
| `VLLM_ENDPOINTS` | `""` | 外部 vLLM endpoint（格式：`name=url,name2=url2`） |
| `XPARSE_PLUGINS_DIR` | `/opt/xparse/plugins` | Plugin 目錄（lifecycle hooks deploy.yaml 位置） |
| `SKILL_LAYER2_ROOT` | `/data/xparse/app-deployed-skills` | Skill mount path 安全驗證 root（INV-122-19） |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `"xparse-tempo:4317"` | OTel gRPC exporter（sidecar container 傳入） |

---

## 9. 關聯文件索引

### 9.1 ADR（架構決策記錄）

| ADR 編號 | 關聯模組 | 主要內容 |
|---------|---------|---------|
| **ADR-093** | 全域 | 5 個 Execution Safety Invariants（原子狀態、預條件驗證、後置驗證、fail-fast、identity binding） |
| **ADR-102 M3** | `core/state.py`, `handlers/sandbox.py` | Sandbox store 以 state.json 為後端；sandbox lifecycle HTTP 路徑 |
| **ADR-102 M4** | `core/heartbeat.py`, `core/sandbox_runtime.py` | 共享 runtime singleton；命令分派表；心跳 workloads payload |
| **ADR-103** | `handlers/sandbox.py:50` | Sandbox 特權防護：schema 層拒絕 `privileged` + `cap_add` |
| **ADR-112** | `validation/profiles.py` | Validation profile → test list 映射 |
| **ADR-122 D10** | `core/skill_mounts.py` | IAM skill mount plan 取得 + Layer 2 root 路徑驗證 |
| **ADR-123** | `handlers/nemoclaw.py` | NemoClaw CLI 整合契約（RFC 1123 命名、env 傳憑證） |
| **ADR-136** | `core/heartbeat.py:708~801` | Agent App reverse proxy sidecar（nginx）；per-group 網路隔離 |
| **ADR-140 D-3** | `handlers/lifecycle.py` | Lifecycle hooks（post_create / pre_destroy）執行規則 |
| **ADR-146** | `core/instance_manager.py` | vLLM instance state machine |
| **ADR-157** | `handlers/service.py:177` | Catalog-driven deploy（image + weights 由 Fleet 提供）|
| **ADR-160 M4** | `core/heartbeat.py:403,450` | Port allocation registry bind / release |
| **ADR-165** | `core/plugin_sync.py` | Plugin template self-sync（image manifest → host，hash-based） |

### 9.2 PRD（產品需求文檔）

| PRD 編號 | 關聯模組 | 主要內容 |
|---------|---------|---------|
| **PRD-062** | `core/heartbeat.py` | Fleet heartbeat + remote command execution |
| **PRD-079** | `validation/` | Node validation framework（profile / test / verdict） |
| **PRD-080** | `core/heartbeat.py:_active_deployments` | Active deployment progress tracking |
| **PRD-116** | `core/instance_manager.py`, `handlers/model_manager.py` | Model Lifecycle Manager |
| **PRD-126** | `core/heartbeat.py:_build_host_ports_observed` | Port registry reconciliation |
| **PRD-128** | `handlers/service.py:177` | Catalog-driven deploy（extended schema） |
| **PRD-129 P2.6** | `core/download_manager.py` | Artifact store worker（MaterializeArtifactUseCase） |
| **PRD-137** | `core/plugin_sync.py` | Plugin template bundling + startup sync |

### 9.3 SPEC 與 Invariants

| 文件 | 關聯模組 | 說明 |
|------|---------|------|
| **SPEC-101 Phase 7** | `core/skill_mounts.py` | Skill mount plan 安全規則（INV-101-23, INV-101-24） |
| **SPEC-102** | `handlers/nemoclaw.py` | NemoClaw 整合行為契約 |
| **SPEC-144** | `core/resource_probe.py`, `core/model_estimator.py` | GPU probe + VRAM 估算契約（RES-01~04, EST-01~04） |
| **INV-102-1** | `handlers/nemoclaw.py` | NemoClaw 憑證只透過 env 傳遞，不寫磁碟 |
| **INV-102-3** | `handlers/nemoclaw.py` | RFC 1123 命名規則 |
| **INV-102-4** | `handlers/nemoclaw.py` | Capability gate（CLI 存在才執行） |
| **INV-102-6** | `handlers/nemoclaw.py` | 銷毀操作需冪等 |
| **INV-188** | `core/heartbeat.py:485` | Registry auth：密碼透過 stdin，fail-fast on failure |
| **RCA-005** | `handlers/nemoclaw.py:_OPENCLAW_GATEWAY_GUARD_JS` | NemoClaw gateway guard monkey-patch |

---

## 10. 規模統計

### 10.1 各模組程式碼行數

| 模組 | 檔案 | 行數 |
|------|------|------|
| **core/heartbeat.py** | 心跳 + 命令執行 | 2,258 |
| **validation/tests/energy_benchmark.py** | 能耗基準測試 | 896 |
| **handlers/nemoclaw.py** | NemoClaw 整合 | 690 |
| **handlers/service.py** | vLLM 服務生命週期 | 566 |
| **core/download_manager.py** | 模型下載管理 | 499 |
| **core/plugin_sync.py** | Plugin 同步 | 448 |
| **core/instance_manager.py** | vLLM 實例管理 | 448 |
| **handlers/model_manager.py** | 模型管理 HTTP | 370 |
| **core/watchdog.py** | 健康監控 | 351 |
| **handlers/sandbox.py** | Sandbox HTTP | 225 |
| **core/state.py** | 狀態持久化 | 218 |
| **core/resource_probe.py** | 資源探測 | 210 |
| **core/model_estimator.py** | VRAM 估算 | 207 |
| **handlers/gpu.py** | GPU 探測 HTTP | 194 |
| **handlers/lifecycle.py** | Lifecycle hooks | 264 |
| **core/sandbox_runtime.py** | Sandbox singleton | 164 |
| **core/config.py** | 配置 | 141 |
| **server.py** | 入口點 | 59 |
| **handlers/health.py** | 健康檢查 | 63 |
| **全部測試（tests/）** | — | ~3,000 |
| **validation/（不含 tests/）** | — | ~450 |

| 分類 | 估計行數 |
|------|---------|
| **核心業務邏輯（core/）** | ~5,200 |
| **HTTP handlers（handlers/）** | ~2,500 |
| **驗證框架（validation/）** | ~1,800 |
| **測試（tests/）** | ~3,000 |
| **腳本（scripts/）** | ~400 |
| **Total（不含測試）** | **~9,900** |
| **Total（含測試）** | **~13,100** |

### 10.2 Python 套件依賴

| 套件 | 版本 | 用途 |
|------|------|------|
| `fastapi` | 0.115.8 | HTTP framework |
| `uvicorn[standard]` | 0.34.0 | ASGI server |
| `pyyaml` | 6.0.2 | compose_render.sh + config YAML 解析 |
| `httpx` | ≥0.25 | 非同步 HTTP client（Fleet 心跳、IAM 查詢） |
| `aiodocker` | ≥0.21 | 非同步 Docker SDK（sandbox use cases） |
| `pynvml` | ≥12.0.0 | GPU 探測（energy benchmark 可選） |
| `huggingface_hub` | ≥0.23 | 模型下載（`snapshot_download`） |
| `psutil` | ≥5.9 | RAM / disk 資源探測 |
| `docker` | ≥7.0.0,<8.0.0 | 同步 Docker SDK（container inspect + logs） |

### 10.3 系統依賴（Docker image）

| 依賴 | 版本 | 用途 |
|------|------|------|
| Docker CLI | 27.5.1 | vLLM 容器管理 |
| Docker Compose plugin | v2.35.1 | compose up/down/logs |
| `iproute2`（ss） | OS 預設 | port_alloc.sh 可用 port 掃描 |
| `curl` | OS 預設 | health_wait.sh 健康等待 |
| Python | 3.12-slim | 執行環境 |
