# Container Platform 技術文件

> **適用範圍**：`xparse_container_platform/`、`xparse_node_mgr/`、Agent App 插件（`plugins/`）
> **相關 ADR**：ADR-102（容器平台架構）、ADR-103（安全硬性不變式）、ADR-110（Agent App 入口）、ADR-115（混合應用部署模型）、ADR-117（雙路徑群組綁定）、ADR-136（容器側反向代理）

---

## 一、服務端口清單（Service Ports）

### 1.1 核心服務


| 服務名稱                | 端口         | 協定   | 環境變數          | 用途說明                              |
| ------------------- | ---------- | ---- | ------------- | --------------------------------- |
| **xparse-node-mgr** | `8080`（預設） | HTTP | `XPARSE_PORT` | Node Manager REST API（沙箱、模型、服務管理） |
| **xparse-iam**      | `8000`     | HTTP | —             | IAM API（認證、授權、會話驗證）               |
| **xparse-fleet**    | `8090`     | HTTP | —             | Fleet API（節點心跳、工作負載調度）            |


### 1.2 Agent App 服務


| 服務名稱                              | 端口      | 協定   | 用途說明                                    |
| --------------------------------- | ------- | ---- | --------------------------------------- |
| **OpenClaw Gateway**（NemoClaw 內部） | `18789` | HTTP | NemoClaw App 應用閘道，透過 sidecar proxy 對外暴露 |
| **Open WebUI**（容器內部）              | `18789` | HTTP | Open WebUI SPA，透過 sidecar proxy 對外暴露    |
| **Sidecar Proxy**（所有 Agent App）   | `8080`  | HTTP | ADR-136 容器側 nginx 反向代理，負責路徑前綴移除與身分注入    |


### 1.3 模型推理服務


| 服務名稱          | 端口範圍              | 協定   | 環境變數                                              | 用途說明                                            |
| ------------- | ----------------- | ---- | ------------------------------------------------- | ----------------------------------------------- |
| **vLLM 推理實例** | `40001–40099`（動態） | HTTP | `XPARSE_VLLM_PORT_START` / `XPARSE_VLLM_PORT_END` | 每個 vLLM 模型實例的 OpenAI 相容推理端點，由 Node Manager 動態分配 |


### 1.4 Node Manager 監聽設定


| 設定項目 | 預設值       | 環境變數          | 說明                       |
| ---- | --------- | ------------- | ------------------------ |
| 監聽位址 | `0.0.0.0` | `XPARSE_BIND` | Node Manager 服務綁定位址      |
| 服務端口 | `8080`    | `XPARSE_PORT` | Node Manager REST API 端口 |


---

## 二、前端 API 清單（Frontend APIs）

> 以下端點均由 **xparse-node-mgr**（Container Platform）本身提供，前端或客戶端可直接呼叫。

### 2.1 健康檢查


| 方法    | 端點路徑         | 功能說明                            |
| ----- | ------------ | ------------------------------- |
| `GET` | `/livez`     | Kubernetes-style liveness probe |
| `GET` | `/v1/health` | 服務健康狀態查詢                        |


### 2.2 沙箱（容器）管理


| 方法       | 端點路徑                              | 功能說明                      |
| -------- | --------------------------------- | ------------------------- |
| `POST`   | `/v1/sandboxes`                   | 建立並啟動新沙箱容器（`201 Created`） |
| `GET`    | `/v1/sandboxes`                   | 列出所有沙箱（可按 `tenant_id` 過濾） |
| `GET`    | `/v1/sandboxes/{sandbox_id}`      | 查詢單一沙箱狀態與資訊               |
| `DELETE` | `/v1/sandboxes/{sandbox_id}`      | 銷毀沙箱容器（`204 No Content`）  |
| `POST`   | `/v1/sandboxes/{sandbox_id}/exec` | 在執行中的沙箱內執行命令              |


`**POST /v1/sandboxes` 請求欄位**：


| 欄位              | 型別           | 預設值                   | 說明                                    |
| --------------- | ------------ | --------------------- | ------------------------------------- |
| `tenant_id`     | string（UUID） | 必填                    | 租戶識別碼                                 |
| `image`         | string       | 必填                    | Docker 映像名稱                           |
| `name`          | string       | `xps-{tenant_id[:8]}` | 容器名稱                                  |
| `memory_limit`  | string       | `512m`                | 記憶體上限                                 |
| `cpu_quota`     | int          | `100000`              | CPU 配額（微秒，100000 = 1 CPU）             |
| `pids_limit`    | int          | `256`                 | 進程數上限                                 |
| `network_mode`  | string       | `none`                | 網路模式（`none` / `host` / `container:X`） |
| `environment`   | object       | `{}`                  | 環境變數字典                                |
| `volumes`       | object       | `{}`                  | 掛載點字典                                 |
| `network_name`  | string       | —                     | 指定命名網路                                |
| `port_mappings` | object       | `{}`                  | 端口映射 `{container_port: host_port}`    |
| `command`       | list         | —                     | Entrypoint 覆蓋                         |
| `privileged`    | bool         | —                     | **禁止傳入 `true`**（ADR-103，422 拒絕）       |
| `cap_add`       | list         | —                     | **禁止傳入**（ADR-103，422 拒絕）              |


### 2.3 GPU / 資源查詢


| 方法    | 端點路徑                 | 功能說明            |
| ----- | -------------------- | --------------- |
| `GET` | `/v1/gpu`            | 查詢 GPU 可用性與指派狀態 |
| `GET` | `/v1/resources`      | 取得整體 GPU 資源使用情況 |
| `GET` | `/v1/resources/gpus` | 取得各 GPU 詳細狀態    |


### 2.4 模型管理


| 方法       | **端點路徑**                         | **功能說明**                            |
| -------- | -------------------------------- | ----------------------------------- |
| `GET`    | `/v1/catalog/models`             | **取得可用模型目錄**                        |
| `POST`   | `/v1/models/estimate`            | **估算部署指定模型所需資源**                    |
| `POST`   | `/v1/models/download`            | 非同步下載模型（`202 Accepted` + `task_id`） |
| `GET`    | `/v1/models/downloads`           | 列出所有下載任務及進度                         |
| `GET`    | `/v1/models/downloads/{task_id}` | 查詢特定下載任務進度                          |
| `DELETE` | `/v1/models/downloads/{task_id}` | 取消下載任務                              |
| `GET`    | `/v1/models/local`               | 列出節點上已部署的模型                         |
| `DELETE` | `/v1/models/local/{model_id}`    | 從節點卸載模型                             |


### 2.5 推理服務實例


| 方法       | 端點路徑                                      | 功能說明           |
| -------- | ----------------------------------------- | -------------- |
| `POST`   | `/v1/models/serve`                        | 部署 vLLM 推理服務實例 |
| `DELETE` | `/v1/models/serve/{instance_id}`          | 停止並移除推理服務實例    |
| `GET`    | `/v1/models/instances`                    | 列出所有執行中的推理實例   |
| `GET`    | `/v1/models/instances/{instance_id}`      | 查詢單一推理實例詳情     |
| `GET`    | `/v1/models/instances/{instance_id}/logs` | 取得推理實例日誌（串流）   |


---

## 三、後端 API 清單（Backend APIs）

### 3.1 Container Platform 對外呼叫（Outbound）

> 以下為 **xparse-node-mgr 主動呼叫** 其他後端服務的 API。


| 方法     | 端點路徑                  | 目標服務         | 功能說明                                                               |
| ------ | --------------------- | ------------ | ------------------------------------------------------------------ |
| `POST` | `/v1/fleet/heartbeat` | xparse-fleet | 定期上報節點狀態（沙箱清單、GPU 統計、部署進度），並拉取 `pending_commands` 命令佇列；回應包含待執行命令列表 |


**心跳回應結構（含 pending_commands）**：

```json
{
  "node_id": "gpu-node-01",
  "timestamp": "2026-05-31T10:00:00Z",
  "pending_commands": [
    {
      "action": "create_workload | destroy_workload | create_agent_app | nemoclaw_onboard",
      "workload_type": "nemoclaw_sandbox | service | ...",
      "...": "..."
    }
  ]
}
```

### 3.2 Container Platform 接收（Inbound from Backend，舊版）

> 以下端點定義於 xparse-node-mgr，由其他後端服務（Fleet 舊版命令通道）呼叫。


| 方法     | 端點路徑                          | 呼叫來源               | 功能說明          |
| ------ | ----------------------------- | ------------------ | ------------- |
| `POST` | `/v1/services/apply`          | Fleet（舊版命令分派）      | 宣告式部署服務（合成建立） |
| `GET`  | `/v1/services`                | Fleet / Console 後端 | 列出所有服務        |
| `GET`  | `/v1/services/{name}`         | Fleet / Console 後端 | 查詢服務詳情        |
| `GET`  | `/v1/services/{name}/profile` | Fleet / Console 後端 | 取得服務設定        |
| `GET`  | `/v1/services/{name}/logs`    | Console 後端         | 取得服務日誌        |
| `POST` | `/v1/services/delete`         | Fleet（舊版命令分派）      | 刪除服務          |


### 3.3 內部 Protocol 層（Clean Architecture Ports）

> 以下為 `xparse_container_platform/application/protocols/` 定義的介面，不對外暴露 HTTP，由 Use Case 層呼叫，底層由 `infrastructure/` 實現。

#### ContainerRuntime（實現：`DockerRuntime`）


| 方法簽名                                                                     | 說明                                   | 呼叫者                                     |
| ------------------------------------------------------------------------ | ------------------------------------ | --------------------------------------- |
| `create_container(config: ContainerConfig) -> ContainerInfo`             | 建立 Docker 容器（不啟動）                    | `CreateSandbox` use case                |
| `start_container(container_id: str) -> None`                             | 啟動容器                                 | `CreateSandbox`、`StartSandbox` use case |
| `stop_container(container_id: str, timeout: int) -> None`                | 停止容器                                 | `StopSandbox` use case                  |
| `remove_container(container_id: str, force: bool) -> None`               | 移除容器                                 | `DestroySandbox` use case               |
| `exec_in_container(container_id: str, command: list[str]) -> ExecResult` | 執行命令（回傳 exit_code / stdout / stderr） | `ExecInSandbox` use case                |
| `get_container_status(container_id: str) -> ContainerInfo`               | 查詢容器運行時狀態                            | `GetSandboxStatus` use case             |
| `get_container_stats(container_id: str) -> ContainerStats`               | 取得 CPU / Memory 統計                   | Watchdog                                |
| `list_container_stats(labels: dict) -> list[ContainerStats]`             | 按標籤過濾多容器統計                           | Fleet 心跳上報                              |


#### SandboxStore（實現：`StateBackedSandboxStore`）


| 方法簽名                                     | 說明                    | 呼叫者                       |
| ---------------------------------------- | --------------------- | ------------------------- |
| `save(sandbox: Sandbox) -> None`         | 持久化沙箱狀態至 `state.json` | 所有 Sandbox use cases      |
| `get(sandbox_id: str) -> Sandbox | None` | 從 `state.json` 讀取沙箱   | 所有 Sandbox use cases      |
| `list(tenant_id: str) -> list[Sandbox]`  | 列出租戶沙箱                | `ListSandboxes` use case  |
| `delete(sandbox_id: str) -> None`        | 刪除沙箱記錄                | `DestroySandbox` use case |


#### ExecutionSandbox（實現：`NsjailSandbox`）


| 方法簽名                                                          | 說明                              | 呼叫者                                        |
| ------------------------------------------------------------- | ------------------------------- | ------------------------------------------ |
| `wrap(command: list[str], language: str | None) -> list[str]` | 用 nsjail 包裝命令（per-execution 隔離） | `ExecInSandbox` use case（`sandboxed=True`） |


---

## 四、工作流程（Workflows）

### 4.1 沙箱容器建立流程

**發起方**：前端 Console 或 Fleet 命令分派
**關聯服務**：xparse-node-mgr → xparse_container_platform → Docker Engine

```
前端 / Fleet
    │
    ▼  POST /v1/sandboxes
xparse-node-mgr（handler 層）
    ├─ 驗證 CreateSandboxBody
    │  └─ ADR-103：拒絕 privileged=true、cap_add 非空（422）
    │
    ▼
CreateSandbox Use Case（xparse_container_platform）
    ├─ 建立 Sandbox 領域實體（sandbox_id, 狀態: CREATING）
    ├─ SandboxStore.save() → state.json
    ├─ ContainerRuntime.create_container(ContainerConfig)
    │     └─ Docker Engine：建立容器（CapDrop=ALL, no-new-privileges）
    ├─ ContainerRuntime.start_container(container_id)
    │     └─ Docker Engine：啟動容器
    ├─ 狀態轉換：CREATING → RUNNING
    ├─ ContainerRuntime.get_container_status()（取得最新 port_mappings）
    └─ SandboxStore.save()（持久化最終狀態）
    │
    ▼
回傳 SandboxDTO（201 Created）

失敗路徑：任何例外 → 狀態 ERROR → 500 ContainerRuntimeError
```


| 步驟         | 關聯服務                                                        |
| ---------- | ----------------------------------------------------------- |
| HTTP 接收與驗證 | xparse-node-mgr                                             |
| 領域邏輯與狀態管理  | xparse_container_platform（Use Case + Domain）                |
| 狀態持久化      | xparse_container_platform（SandboxStore → state.json）        |
| 容器操作       | xparse_container_platform（ContainerRuntime → Docker Engine） |


---

### 4.2 沙箱命令執行流程

**發起方**：前端 Console（程式碼執行功能）
**關聯服務**：xparse-node-mgr → xparse_container_platform → Docker Engine

```
前端 Console
    │
    ▼  POST /v1/sandboxes/{sandbox_id}/exec
xparse-node-mgr（handler 層）
    ├─ 驗證 ExecBody（command 非空）
    │
    ▼
ExecInSandbox Use Case（xparse_container_platform）
    ├─ SandboxStore.get(sandbox_id)
    │     └─ 不存在 → SandboxNotFoundError（404）
    ├─ sandbox.require_running()
    │     └─ 非 RUNNING → SandboxNotRunningError（409）
    ├─ 命令處理
    │  ├─ sandboxed=True → NsjailSandbox.wrap(command)（nsjail per-execution 隔離）
    │  └─ sandboxed=False → 直接執行
    └─ ContainerRuntime.exec_in_container(container_id, command)
          └─ Docker Engine：執行命令，回傳 exit_code / stdout / stderr
    │
    ▼
回傳 ExecResultDTO（200 OK）
```


| 步驟         | 關聯服務                                                        |
| ---------- | ----------------------------------------------------------- |
| HTTP 接收    | xparse-node-mgr                                             |
| 狀態驗證       | xparse_container_platform（Domain Entity）                    |
| 命令隔離包裝（可選） | xparse_container_platform（NsjailSandbox）                    |
| 命令執行       | xparse_container_platform（ContainerRuntime → Docker Engine） |


---

### 4.3 Agent App 部署流程

**發起方**：IAM（使用者建立 Application）
**關聯服務**：xparse-iam → xparse-fleet → xparse-node-mgr → xparse_container_platform → Docker Engine

```
使用者（Console）建立 Application（app_type_code: nemoclaw / open-webui）
    │
    ▼
xparse-iam
    ├─ 建立 Application 治理記錄（app_type_code → 能力模板，ADR-115）
    └─ 非同步通知 Fleet 觸發部署
    │
    ▼
xparse-fleet（Scheduler）
    ├─ 依資源需求選擇目標節點
    ├─ 生成 DeploymentContext
    └─ 將 create_agent_app 命令寫入命令佇列
    │
    ▼（等待節點下一次心跳）
xparse-node-mgr（heartbeat 拉取）
    │  POST /v1/fleet/heartbeat → 回收 pending_commands
    └─ 分派至 _handle_create_agent_app()
    │
    ▼
CreateSandbox Use Case（xparse_container_platform）
    ├─ 建立 App 容器
    │  ├─ image: 來自 deploy.yaml
    │  ├─ name: xparse-app-{app_code}
    │  ├─ network_name: agent-network（ADR-133 隔離）
    │  ├─ environment: 注入 IAM 設定值
    │  └─ 安全：CapDrop=ALL, no privileged
    ├─ 等待容器健康（health-check loop）
    ├─ 啟動 Sidecar Proxy 容器（ADR-136）
    │  ├─ image: nginx:1.31.0-alpine
    │  ├─ name: xparse-app-{app_code}-sidecar
    │  ├─ port: 8080（對外暴露）
    │  └─ proxy_pass → app container:18789
    └─ 執行 post_create 生命週期鉤子（symlink、gateway 啟動、health-check）
    │
    ▼
xparse-fleet 回報部署完成（下次心跳 pending_command_results）
```


| 步驟                  | 關聯服務                                             |
| ------------------- | ------------------------------------------------ |
| 建立 Application 治理記錄 | xparse-iam                                       |
| 工作負載調度與節點選擇         | xparse-fleet                                     |
| 命令傳遞（heartbeat 通道）  | xparse-node-mgr ↔ xparse-fleet                   |
| 容器建立與生命週期管理         | xparse_container_platform → Docker Engine        |
| Sidecar 代理建立        | xparse_container_platform → Docker Engine（nginx） |
| 部署結果回報              | xparse-node-mgr → xparse-fleet                   |


---

### 4.4 使用者存取 Agent App 請求流程

**發起方**：使用者瀏覽器
**關聯服務**：nginx ingress → xparse-iam → Sidecar（nginx）→ Agent App 容器

```
使用者瀏覽器
    │  點擊 Console 應用啟動器 → /app/{app_code}/
    │
    ▼
nginx ingress（port 443）
    ├─ auth_request /_auth_verify
    │     └─ GET /iam/auth/verify-session  →  xparse-iam
    │           ├─ 驗證 Django session cookie
    │           ├─ 確認應用存取權限（ADR-117 群組綁定）
    │           ├─ 失敗（401）→ 導向 Console 登入頁
    │           └─ 成功（200）→ 回傳身分標頭
    │
    ├─ 注入身分標頭（ADR-110 D-5 Channel 1）
    │  ├─ X-Xparse-User-Id
    │  ├─ X-Xparse-Tenant-Id
    │  └─ X-Xparse-App-Code
    │
    ├─ 設定 xparse_identity cookie（Channel 2，WebSocket 用）
    │     └─ 簽署 JWT：{sub, tid, app, rol, iat, exp}
    │
    ├─ 場景 A — Phase 1（Convention 路由）
    │     └─ proxy_pass http://xparse-app-{app_code}-sidecar:8080
    │
    └─ 場景 B — Phase 2（Fleet 動態路由）
          ├─ GET /fleet/apps/{app_code}/endpoint  →  xparse-fleet
          └─ proxy_pass $upstream（動態上游）
    │
    ▼
Sidecar Proxy（nginx，port 8080）
    ├─ 移除路徑前綴：/app/{app_code}/ → /
    ├─ sub_filter 路徑改寫（SvelteKit 靜態資源、Socket.IO 命名空間）
    └─ proxy_pass http://app-container:18789/
    │
    ▼
Agent App 容器（port 18789）
    ├─ 讀取 X-Xparse-User-Id 等標頭（HTTP 請求）
    └─ 讀取 xparse_identity cookie（WebSocket 連線）

回應路徑（反向）：App 容器 → Sidecar → nginx ingress → 瀏覽器
```


| 步驟      | 關聯服務                                        |
| ------- | ------------------------------------------- |
| 會話驗證    | nginx ingress → xparse-iam                  |
| 身分注入    | nginx ingress（標頭 + cookie）                  |
| 靜態路由    | nginx ingress → Sidecar（Phase 1）            |
| 動態路由查詢  | nginx ingress → xparse-fleet（Phase 2）       |
| 路徑改寫與代理 | Sidecar（nginx，xparse_container_platform 管理） |
| 業務邏輯    | Agent App 容器（xparse_container_platform 管理）  |


---

### 4.5 遠端工作負載調度流程（心跳命令通道）

**發起方**：xparse-node-mgr 排程任務（定期觸發）
**關聯服務**：xparse-node-mgr ↔ xparse-fleet → xparse_container_platform

```
xparse-node-mgr（每 FLEET_HEARTBEAT_INTERVAL 秒，預設 30s）
    │
    ├─ 蒐集本地狀態快照
    │  ├─ 沙箱清單（state.json）
    │  ├─ 運行中服務
    │  ├─ GPU 資源統計
    │  └─ 部署進度
    │
    ▼  POST /v1/fleet/heartbeat  →  xparse-fleet
    ├─ 攜帶 FLEET_NODE_KEY 簽名
    └─ 回傳 pending_commands 列表
    │
    ▼
xparse-node-mgr 命令分派（_COMMAND_HANDLERS 路由表）
    ├─ action="create_workload"      → CreateSandbox Use Case
    ├─ action="destroy_workload"     → DestroySandbox Use Case
    ├─ action="create_agent_app"     → _handle_create_agent_app()（見 §4.3）
    └─ action="nemoclaw_onboard"     → 執行 `nemoclaw onboard` CLI
    │
    ▼
執行結果（下一次心跳回傳）
    ├─ 成功：status="success", result={...}
    └─ 失敗：status="failed", error_message="..."
```


| 步驟        | 關聯服務                                      |
| --------- | ----------------------------------------- |
| 狀態快照蒐集    | xparse-node-mgr                           |
| 心跳上報與命令拉取 | xparse-node-mgr → xparse-fleet            |
| 命令路由分派    | xparse-node-mgr（_COMMAND_HANDLERS）        |
| 容器操作執行    | xparse_container_platform → Docker Engine |
| 執行結果回報    | xparse-node-mgr → xparse-fleet（下次心跳）      |


---

### 4.6 推理服務健康監控流程

**發起方**：xparse-node-mgr 內建 Watchdog（背景任務）
**關聯服務**：xparse-node-mgr → xparse_container_platform → vLLM 實例

```
xparse-node-mgr Watchdog（每 XPARSE_WATCHDOG_INTERVAL 秒，預設 10s）
    │
    ├─ 掃描所有 RUNNING 狀態的 vLLM 實例
    │
    ├─  GET http://localhost:{port}/health  →  vLLM 實例
    │   ├─ 成功（200）→ 重置失敗計數器
    │   └─ 失敗（timeout / non-200）→ 失敗計數器 ++
    │
    ├─ 失敗計數 > XPARSE_WATCHDOG_HEALTH_FAILURES（預設 3）
    │  ├─ 重啟次數 < XPARSE_WATCHDOG_MAX_RESTARTS（預設 5）
    │  │     └─ ContainerRuntime.stop_container() → start_container()
    │  └─ 重啟次數 >= 上限 → 標記 "unhealthy"，停止自動重啟
    │
    └─ 定期向 Fleet 心跳回報實例健康狀態
```


| 步驟      | 關聯服務                                                        |
| ------- | ----------------------------------------------------------- |
| 週期性健康探測 | xparse-node-mgr（Watchdog） → vLLM 容器                         |
| 容器重啟操作  | xparse_container_platform（ContainerRuntime → Docker Engine） |
| 健康狀態上報  | xparse-node-mgr → xparse-fleet（心跳通道）                        |


---

## 附錄 A：沙箱狀態機

> 定義於 `xparse_container_platform/domain/entities/sandbox.py`

```
                  ContainerRuntime 失敗
         ┌─────────────────────────────────────┐
         │                                     ▼
     CREATING ─── 啟動成功 ──► RUNNING ─── stop() ──► STOPPED
         │                        │                       │
         │                        │ start()               │
         │                        └───────────────────────┘
         │                        │
         │                   destroy()
         │                        │
         │                        ▼
         └──── 啟動失敗 ──► ERROR ──► DESTROYED
                                        ▲
                                        │
                              STOPPED ──┘ (destroy())
```

不變式：

- 一旦進入 `DESTROYED`，無法再轉移
- 只有 `RUNNING` 狀態允許 exec
- 非法轉移擲出 `InvalidStateTransitionError`
- 每次轉移更新 `updated_at` 時間戳

---

## 附錄 B：安全硬性不變式（ADR-103）


| 限制項目                      | 強制值                     | 執行位置                           |
| ------------------------- | ----------------------- | ------------------------------ |
| `Privileged`              | 永遠 `False`              | `docker_runtime.py` 第 49 行     |
| `CapDrop`                 | `["ALL"]`               | `docker_runtime.py` HostConfig |
| `SecurityOpt`             | `["no-new-privileges"]` | `docker_runtime.py` HostConfig |
| `cap_add`（API 請求）         | 拒絕（`422`）               | `handlers/sandbox.py` 驗證器      |
| `privileged=True`（API 請求） | 拒絕（`422`）               | `handlers/sandbox.py` 驗證器      |


---

## 附錄 C：環境變數速查


| 環境變數                              | 預設值                       | 說明                 |
| --------------------------------- | ------------------------- | ------------------ |
| `XPARSE_BIND`                     | `0.0.0.0`                 | Node Manager 監聽位址  |
| `XPARSE_PORT`                     | `8080`                    | Node Manager 服務端口  |
| `XPARSE_TOKEN`                    | `demo-token`              | 認證 token           |
| `XPARSE_VLLM_IMAGE`               | `vllm/vllm-openai:latest` | vLLM 容器映像          |
| `XPARSE_VLLM_PORT_START`          | `40001`                   | vLLM 端口範圍起始        |
| `XPARSE_VLLM_PORT_END`            | `40099`                   | vLLM 端口範圍結束        |
| `XPARSE_VLLM_GPU_UTIL`            | `0.9`                     | GPU 利用率上限          |
| `XPARSE_WATCHDOG_INTERVAL`        | `10`                      | 健康檢查間隔（秒）          |
| `XPARSE_WATCHDOG_MAX_RESTARTS`    | `5`                       | 最大自動重啟次數           |
| `XPARSE_WATCHDOG_HEALTH_FAILURES` | `3`                       | 觸發重啟的連續失敗閾值        |
| `FLEET_API_URL`                   | —（必填）                     | Fleet API 服務 URL   |
| `FLEET_NODE_KEY`                  | `XPARSE_TOKEN`            | 節點認證金鑰             |
| `FLEET_NODE_ID`                   | `local`                   | 節點識別 ID            |
| `FLEET_HEARTBEAT_INTERVAL`        | `30`                      | 心跳上報間隔（秒）          |
| `FLEET_NODE_EXTERNAL_IP`          | —                         | 節點外部 IP（跨節點路由用）    |
| `IAM_API_URL`                     | —（必填）                     | IAM 服務 URL         |
| `NEMOCLAW_CLI_PATH`               | `nemoclaw`                | NemoClaw CLI 執行路徑  |
| `OPENSHELL_CLI_PATH`              | `openshell`               | OpenShell CLI 執行路徑 |


