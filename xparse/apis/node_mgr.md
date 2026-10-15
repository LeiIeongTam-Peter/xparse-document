# xparse_node_mgr — 技術 API 文件

> **服務定位**：Node Runtime Agent（`agentd`），負責節點端的模型部署、容器工作負載管理、GPU 資源監控，以及與 Fleet 控制平面的心跳通訊。
>
> **架構依據**：ADR-102（Runtime Layering）、ADR-103（Sandbox Security）、ADR-110（Console-centric Ingress）、ADR-115（Hybrid App/Deployment）、ADR-136（Sidecar Proxy）

---

## 一、服務端口清單（Service Ports）

| 服務名稱 | 端口號碼 | 通訊協定 | 用途說明 |
|----------|----------|----------|----------|
| xparse_node_mgr（主服務） | `8080`（可覆寫） | HTTP | FastAPI REST API 主入口；由環境變數 `XPARSE_PORT` 控制，繫結位址由 `XPARSE_BIND`（預設 `0.0.0.0`）控制 |
| Health Probe | `8080` | HTTP | Docker `HEALTHCHECK` 使用，端點為 `/livez`，無需認證 |
| vLLM 動態模型服務（起始） | `40001`（可覆寫） | HTTP | vLLM 容器動態端口分配起點；由 `XPARSE_VLLM_PORT_START` 控制 |
| vLLM 動態模型服務（終止） | `40099`（可覆寫） | HTTP | vLLM 容器動態端口分配終點；由 `XPARSE_VLLM_PORT_END` 控制 |
| NemoClaw Gateway | `18789`（慣例） | HTTP | NemoClaw Sandbox 的 OpenClaw gateway proxy 端口；用於 sidecar nginx reverse proxy 接入 |

---

## 二、前端 API 清單（Frontend APIs）

> 以下端點為 Console App 前端可能透過後端代理（Gateway → IAM → node_mgr）或 Fleet 轉發呼叫的 API。直接呼叫需附帶 `Authorization: Bearer {XPARSE_TOKEN}` Header，僅 `/livez` 例外。

| HTTP 方法 | 端點路徑 | 目標服務 | 功能說明 |
|-----------|----------|----------|----------|
| `GET` | `/livez` | xparse_node_mgr | Liveness probe；無需認證，回傳 `{status, version, time, fleet_configured}` |
| `GET` | `/v1/health` | xparse_node_mgr | 認證版健康檢查，回傳 `{status, version, time, endpoint_mode}` |
| `GET` | `/v1/catalog/models` | xparse_node_mgr | 列出本節點 catalog 中所有可用模型清單（含 name、version、engine、image、profiles） |
| `GET` | `/v1/gpu` | xparse_node_mgr | 探測 GPU 資訊（透過 nvidia-smi），回傳 `{gpus, source, error}` |
| `GET` | `/v1/resources` | xparse_node_mgr | 完整資源報告（GPU、磁碟、記憶體） |
| `GET` | `/v1/resources/gpus` | xparse_node_mgr | 所有 NVIDIA GPU 詳細資訊 |
| `GET` | `/v1/services` | xparse_node_mgr | 列出所有已部署的 vLLM 服務及即時狀態 |
| `GET` | `/v1/services/{name}` | xparse_node_mgr | 取得指定服務詳細資訊 |
| `GET` | `/v1/services/{name}/profile` | xparse_node_mgr | 取得 Gateway 相容的 model_profile（含 profile_yaml、gateway_synced、instructions） |
| `GET` | `/v1/services/{name}/logs` | xparse_node_mgr | 取得容器 log（支援 `tail` 查詢參數） |
| `GET` | `/v1/sandboxes` | xparse_node_mgr | 列出所有 sandbox（可用 `tenant_id` 過濾） |
| `GET` | `/v1/sandboxes/{sandbox_id}` | xparse_node_mgr | 取得單一 sandbox 狀態 |
| `GET` | `/v1/models/downloads` | xparse_node_mgr | 列出所有模型下載任務 |
| `GET` | `/v1/models/downloads/{task_id}` | xparse_node_mgr | 取得特定下載任務狀態 |
| `GET` | `/v1/models/local` | xparse_node_mgr | 列出本地快取的模型 |
| `GET` | `/v1/models/instances` | xparse_node_mgr | 列出所有正在運行的 vLLM 模型實例 |
| `GET` | `/v1/models/instances/{instance_id}` | xparse_node_mgr | 取得特定模型實例詳細資訊 |
| `GET` | `/v1/models/instances/{instance_id}/logs` | xparse_node_mgr | 串流或拉取模型實例 log（支援 `tail`、`follow` 查詢參數） |

---

## 三、後端 API 清單（Backend APIs）

### 3.1 對外公開端點（xparse_node_mgr 自身暴露）

| HTTP 方法 | 端點路徑 | 所屬服務 | 功能說明 | 呼叫來源 |
|-----------|----------|----------|----------|----------|
| `POST` | `/v1/services/apply` | xparse_node_mgr | 部署 vLLM 模型服務（docker-compose）；Body: `{name, model, tp, profile, image?, weights?}` | Fleet 指令分派 / 本機回呼 |
| `POST` | `/v1/services/delete` | xparse_node_mgr | 停止並移除 vLLM 服務；Body: `{name, purge?}` | Fleet 指令分派 / 本機回呼 |
| `POST` | `/v1/sandboxes` | xparse_node_mgr | 建立新 sandbox 容器；Body: `{tenant_id, image, name?, memory_limit, cpu_quota, pids_limit, environment, volumes, port_mappings, ...}` | Fleet 指令分派 |
| `DELETE` | `/v1/sandboxes/{sandbox_id}` | xparse_node_mgr | 銷毀 sandbox 容器；回傳 204 No Content | Fleet 指令分派 |
| `POST` | `/v1/sandboxes/{sandbox_id}/exec` | xparse_node_mgr | 在 sandbox 內執行指令；Body: `{command, sandboxed?, language?}`；回傳 `{exit_code, stdout, stderr}` | 後端服務 / Agent App |
| `POST` | `/v1/models/estimate` | xparse_node_mgr | 估算 HuggingFace 模型所需 VRAM；Body: `{repo_id, dtype?, max_model_len?, hf_token?}` | 排程任務 / 後端服務 |
| `POST` | `/v1/models/download` | xparse_node_mgr | 啟動背景模型下載任務；Body: `{repo_id, hf_token?}`；回傳 202 Accepted + `{task_id}` | Fleet 指令分派 / 後端服務 |
| `DELETE` | `/v1/models/downloads/{task_id}` | xparse_node_mgr | 取消模型下載任務 | 後端服務 |
| `DELETE` | `/v1/models/local/{model_id:path}` | xparse_node_mgr | 刪除本地快取模型 | 後端服務 |
| `POST` | `/v1/models/serve` | xparse_node_mgr | 啟動本地模型的 vLLM 容器實例；Body: `{repo_id, gpu_indices, dtype?, max_model_len?, extra_args?}`；回傳 `{instance_id, container_id, port, endpoint}` | Fleet 指令分派 |
| `DELETE` | `/v1/models/serve/{instance_id}` | xparse_node_mgr | 停止 vLLM 實例 | Fleet 指令分派 |

### 3.2 對外呼叫端點（xparse_node_mgr 作為 HTTP Client）

| HTTP 方法 | 端點路徑 | 目標服務 | 功能說明 | 呼叫時機 |
|-----------|----------|----------|----------|----------|
| `POST` | `/v1/fleet/heartbeat` | xparse_fleet | 定期回報節點狀態（GPU、服務、工作負載、容量）；接收 `pending_commands`；由 `FLEET_API_URL` 環境變數配置 | 每 30 秒（`FLEET_HEARTBEAT_INTERVAL`） |
| `POST` | `/v1/fleet/nodes/{node_id}/ports/allocations/{id}/bind` | xparse_fleet | 將端口分配綁定至容器 | 容器建立後（best-effort） |
| `DELETE` | `/v1/fleet/nodes/{node_id}/ports/allocations/{id}` | xparse_fleet | 釋放端口分配 | 容器銷毀時 |
| `GET` | `/iam/applications/{application_uuid}/skills/mount-plan` | xparse_iam | 取得 Agent App 的技能掛載計畫（ADR-122）；由 `IAM_API_URL` + `IAM_API_KEY` 配置 | create_workload / create_agent_app 指令執行時 |
| `GET` | `/health` | 外部 vLLM 端點 | 探測外部 vLLM 服務健康狀態（5 秒 timeout）；端點清單由 `VLLM_ENDPOINTS` 配置 | 每次心跳周期 |
| `GET` | `/metrics` | NVIDIA Exporter | 從 Prometheus metrics 端點（nvidia-gpu-exporter 或 dcgm-exporter）解析 GPU 資訊；由 `NVIDIA_EXPORTER_URL` 配置 | nvidia-smi 不可用時 fallback |
| `POST` | `http://127.0.0.1:{PORT}/v1/services/apply` | 本機自身 | 心跳指令分派器透過 HTTP 呼叫本機 API 部署 vLLM 服務 | 收到 Fleet `deploy` 指令時 |
| `POST` | `http://127.0.0.1:{PORT}/v1/services/delete` | 本機自身 | 心跳指令分派器透過 HTTP 呼叫本機 API 移除 vLLM 服務 | 收到 Fleet `undeploy` 指令時 |

---

## 四、工作流程（Workflows）

### 4.1 vLLM 模型服務部署（Fleet deploy 指令）

```
發起方：xparse_fleet（透過心跳 pending_commands）
接收方：xparse_node_mgr
```

**步驟流程：**

1. Fleet 心跳回應中夾帶 `{"type": "deploy", "name": "...", "model": "...", "profile": "..."}` 指令
2. `heartbeat.py` 指令分派器收到後，呼叫本機 `POST /v1/services/apply`
3. `handlers/service.py` 驗證輸入（name、model、profile 必填）
4. 從 catalog 載入 manifest（`handlers/catalog.py`）
5. 透過 `handlers/gpu.py` 檢查 GPU 可用性並分配
6. 呼叫 `port_alloc.sh` 分配主機端口（40001–40099 範圍）
7. 呼叫 `compose_render.sh` 渲染 `docker-compose.yaml`
8. 呼叫 `compose_up.sh` 啟動容器
9. 呼叫 `health_wait.sh` 等待服務健康就緒
10. 產生 Gateway 相容的 `model_profile.yaml`
11. 可選：同步至 Gateway 的 `model_profiles.d/`
12. 持久化至 `state.json`（`services` 段落）
13. 回傳服務 metadata + profile 至 Fleet 下一次心跳

**回應路徑：** `node_mgr` → 下一次心跳 `POST /v1/fleet/heartbeat` → `xparse_fleet`

---

### 4.2 Agent App 工作負載部署（Fleet create_workload 指令）

```
發起方：xparse_fleet（透過心跳 pending_commands）
接收方：xparse_node_mgr
```

**步驟流程：**

1. Fleet 心跳回應夾帶 `{"type": "create_workload", "workload_type": "...", "image": "...", "workload_id": "..."}` 指令
2. `heartbeat.py` 指令分派器接收並驗證 `workload_type`、`image`、`workload_id`
3. 冪等性檢查：若 `workload_id` 已在 `state.json` 中，直接回傳現有狀態
4. 呼叫 `GET /iam/applications/{uuid}/skills/mount-plan` 取得技能掛載計畫（IAM API）
5. 若需要 private registry，執行 `docker login`（密碼透過 stdin 傳遞，非 argv）
6. 執行 `docker run` 建立 App 容器（含 network、port mappings）
7. 可選：建立 sidecar nginx reverse proxy 容器（ADR-136）
8. 執行 `lifecycle.py` post-create hooks
9. 持久化至 `state.json`（`sandboxes` 段落）含 `endpoint`
10. Best-effort 呼叫 Fleet `POST /v1/fleet/nodes/{node_id}/ports/allocations/{id}/bind` 綁定端口
11. 於下一次心跳回報 workload 狀態

**回應路徑：** `node_mgr` → IAM（取得掛載計畫）→ 心跳回報 → `xparse_fleet`

---

### 4.3 NemoClaw Sandbox 部署（Fleet nemoclaw_onboard 指令）

```
發起方：xparse_fleet（透過心跳 pending_commands）
接收方：xparse_node_mgr → NemoClaw CLI → Docker
```

**步驟流程：**

1. Fleet 心跳回應夾帶 `{"type": "nemoclaw_onboard", "workload_type": "nemoclaw_sandbox", ...}` 指令
2. `handlers/nemoclaw.py` 設定環境變數：`NEMOCLAW_SANDBOX_NAME`、`NEMOCLAW_PROVIDER`、`MODEL`、`ENDPOINT_URL`、`API_KEY`
3. 執行子程序 `nemoclaw onboard --non-interactive`（最長等待 900 秒，含 image build）
4. 可選：注入 `os.networkInterfaces()` guard（修復特定 OpenClaw crash）
5. 可選：建立 sidecar nginx reverse proxy（ADR-136）監聽 port `18789`
6. 執行 post-create lifecycle hooks
7. 持久化至 `state.json`，記錄 `gateway_port`、`sandbox_id`、`endpoint`、`status`
8. 於下一次心跳回報部署結果

**回應路徑：** `node_mgr` → NemoClaw CLI（subprocess）→ Docker → 心跳回報 → `xparse_fleet`

---

### 4.4 Fleet 心跳迴圈（主動上報 + 指令接收）

```
發起方：xparse_node_mgr（每 30 秒排程）
接收方：xparse_fleet
```

**步驟流程：**

```
每 30 秒（FLEET_HEARTBEAT_INTERVAL）：
├─ 探測 GPU（nvidia-smi，失敗時 fallback NVIDIA_EXPORTER_URL/metrics）
├─ docker inspect 豐富化各服務狀態
├─ 探測外部 vLLM 端點（GET /health，5s timeout）
├─ 每 150 秒探測 NemoClaw sandbox 健康狀態
├─ 蒐集 pending 指令執行結果緩衝
├─ 快照主機端口綁定（docker ps）
├─ 從 state.json 建構 workloads payload
│
├─ POST /v1/fleet/heartbeat（含 gpus、services、workloads、capacity、host_ports_observed）
│
└─ 接收回應中的 pending_commands，逐一分派至指令處理器：
   ├─ deploy / undeploy        → vLLM 服務部署/移除
   ├─ create_workload          → Agent App / sandbox 建立
   ├─ destroy_workload         → 容器銷毀 + 端口釋放
   ├─ create_agent_app         → 特化 App 建立流程
   ├─ nemoclaw_onboard         → NemoClaw sandbox 部署
   ├─ validate                 → 節點驗收測試
   └─ energy_benchmark         → GPU 功耗測試
```

**回應路徑：** Fleet 在下一次 POST heartbeat 的 response body 中夾帶指令；結果在再下一次心跳回報。

---

### 4.5 Sandbox 指令執行（exec）

```
發起方：後端服務 / Agent App
接收方：xparse_node_mgr → Docker exec
```

**步驟流程：**

1. 呼叫 `POST /v1/sandboxes/{sandbox_id}/exec`，Body: `{command: [...], sandboxed?, language?}`
2. 驗證 `sandbox_id` 存在於 `state.json`
3. 若 `sandboxed=true`：以 nsjail 包裝執行（隔離沙箱）
4. 建立 `docker exec` 子程序，捕捉 stdout / stderr
5. 等待執行完成，回傳 `{exit_code, stdout, stderr}`

**回應路徑：** 同步回應（無非同步回呼）

---

### 4.6 本地模型 HuggingFace 下載與服務啟動

```
發起方：後端服務 / Fleet 指令
接收方：xparse_node_mgr → HuggingFace Hub → Docker（vLLM）
```

**步驟流程：**

1. `POST /v1/models/estimate`：預先估算 VRAM 需求（向 HuggingFace 取得模型 config）
2. `POST /v1/models/download`：啟動背景下載任務（202 Accepted + `task_id`）
   - `core/download_manager.py` 管理下載佇列
   - 可透過 `GET /v1/models/downloads/{task_id}` 輪詢進度
3. 下載完成後，`GET /v1/models/local` 確認模型存在
4. `POST /v1/models/serve`：啟動 vLLM Docker 容器服務本地模型
   - 指定 `gpu_indices`、`dtype`、`max_model_len`
   - 回傳 `{instance_id, container_id, port, endpoint}`
5. `core/watchdog.py` 持續監控模型實例健康狀態

**回應路徑：** 各步驟同步回應；下載進度非同步輪詢

---

## 附錄：狀態持久化

| 儲存項目 | 路徑 | 說明 |
|----------|------|------|
| Runtime 狀態 | `{XPARSE_BASE_DIR}/xparse_node_mgr/runtime/state.json` | 所有工作負載生命週期的 single source of truth；包含 `services`、`sandboxes`、`downloads`、`instances`、`gpu_assignments` |
| 事件稽核日誌 | `{XPARSE_BASE_DIR}/xparse_node_mgr/runtime/events.log` | 可稽核的事件記錄，由 `core/state.py` 的 `log_event()` 寫入 |

## 附錄：認證機制

| 機制 | 說明 |
|------|------|
| Bearer Token | 所有端點（除 `/livez`）需附帶 `Authorization: Bearer {XPARSE_TOKEN}`；Token 由 `XPARSE_TOKEN` 環境變數配置，預設值為 `demo-token` |
| ADR-103 沙箱安全 | Sandbox 容器禁止 `privileged=true` 及 `cap_add`，由 Pydantic schema 層強制執行 |
| 憑證不落磁碟 | NemoClaw CLI 憑證與 Docker registry 密碼僅透過環境變數或 stdin 傳遞，不寫入任何檔案（INV-102-1） |
| IAM 路徑驗證 | 技能掛載路徑驗證確保不超出 Layer 2 根目錄範圍（INV-122-19） |
