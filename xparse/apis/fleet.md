# Fleet API 參考文件

> 來源：`xparse_fleet/fleet/` — FastAPI 應用程式（`app.py`）+ 18 個路由模組。
> 認證參考：ADR-073（IAM 優先）、ADR-128（節點 bootstrap）、SPEC-093 §10（可路由端點）。

---

## 服務 Port 一覽

| 服務 | Container 名稱 | 內部 Port | 備註 |
|------|---------------|----------|------|
| xparse-fleet | `xparse-fleet` | **8090** | Fleet API 主服務（FastAPI/uvicorn）；可透過 `FLEET_PORT` 環境變數覆蓋 |
| xparse-iam | `xparse-iam` | **8010** | IAM 服務；Fleet 呼叫 `FLEET_IAM_VALIDATE_URL` 與 `FLEET_IAM_BASE_URL` |
| xparse-gateway | `xparse-gateway-blue/green` | **8000** | Gateway；定期輪詢 Fleet `/v1/fleet/model-profiles` + `/v1/fleet/routable-endpoints` |
| xparse-audit | `xparse-audit` | **8001** | Audit API（Fleet 不直接呼叫；由 IAM 轉送） |
| xparse-scheduler | `xparse-scheduler` | **8030** | Scheduler；Fleet 將節點容量中繼至 `POST /nodes/{id}/report` |
| xparse-console | `xparse-console` | **8080** | 前端 SPA（nginx）；瀏覽器透過反向代理 `/fleet/*` 存取 Fleet |
| xparse-app-nemoclaw | `xparse-app-nemoclaw` | **18789** | NemoClaw agent app；透過 `FLEET_APP_DEPLOYMENTS` 環境變數註冊 |
| xparse-proxy-nemoclaw-* | `xparse-proxy-nemoclaw-*` | — | NemoClaw 的 nginx sidecar（ADR-136）；代理至 port 18789 |
| xparse-guardrails | `xparse-guardrails` | **8400** | Guardrail sidecar；Fleet 不直接呼叫 |
| vLLM（節點管理） | 各節點獨立 container | **8000**（預設 container port） | `host_port` 依 port registry 動態分配（PRD-126） |
| xparse-node-mgr（agentd） | 各節點常駐程序 | 透過 `FLEET_AGENTS` JSON 設定 | Fleet 透過 heartbeat ack 下發命令；不維持持久連線 |

---

## 前端 APIs

所有呼叫源自 `frontend/console-app/src/services/fleetApi.ts`，透過 `fleetEndpoint()` 產生完整 URL。
瀏覽器透過反向代理存取：`${API_BASE}/fleet` → `http://xparse-fleet:8090`。

認證：所有請求均帶 `Authorization: Bearer <xp_live_* IAM key>`（健康檢查除外）。

### Fleet 狀態與 GPU

| 方法 | 路徑 | 對應元件 / Hook | 說明 |
|------|------|----------------|------|
| GET | `/v1/fleet/status` | `Dashboard`、`useFleetStatus` | 整體 fleet 概覽：節點總數、GPU 計數、服務計數；支援 `?group_uuid=` 篩選 |
| GET | `/v1/fleet/gpu` | `NodeAllocationsView`、`useFleet` | 各節點 GPU 詳情（記憶體、使用率、運行中服務） |
| GET | `/v1/fleet/nodes` | `useFleet`、`useFleetGroups` | 完整節點清單，含連線狀態與生命週期狀態；支援 `?group_uuid=` 篩選 |
| GET | `/v1/fleet/nodes/{node_id}` | 節點詳情頁 | 單一節點詳情（狀態、tier、服務、GPU） |

### 節點生命週期管理

| 方法 | 路徑 | 對應元件 / Hook | 說明 |
|------|------|----------------|------|
| POST | `/v1/fleet/nodes/{node_id}/approve` | `useFleetMutations` | 核准待審節點：`REGISTERED → APPROVED` |
| POST | `/v1/fleet/nodes/{node_id}/reject` | `useFleetMutations` | 拒絕節點：`ANY → REJECTED` |
| POST | `/v1/fleet/nodes/{node_id}/admit` | `useFleetMutations` | 管理員強制入場：`APPROVED → ADMITTED`（跳過驗證，tier=T1） |
| DELETE | `/v1/fleet/nodes/{node_id}` | `useFleetMutations` | 從 fleet 移除節點；靜態設定節點回傳 409 |
| POST | `/v1/fleet/nodes/{node_id}/validate` | `useFleetMutations` | 觸發硬體驗證；派送 `validate` 命令至節點 |
| GET | `/v1/fleet/nodes/{node_id}/validation` | 節點詳情頁 | 取得最新驗證狀態（state、tier、summary） |

### Agent App 部署

| 方法 | 路徑 | 對應元件 / Hook | 說明 |
|------|------|----------------|------|
| POST | `/v1/fleet/apps/{app_code}/deploy` | `useDeployApp` | 部署 agent app 容器（支援多副本、round-robin 負載均衡） |
| GET | `/v1/fleet/apps/{app_code}/endpoint` | `BindDeploymentDialog` | 查詢 agent app 的健康上游 URL |
| GET | `/v1/fleet/apps/{app_code}/deployments/{deploy_code}/endpoint` | `ApplicationDetail` | 查詢特定部署的端點（ADR-129 Phase 1） |

### 節點上線（Bootstrap）

| 方法 | 路徑 | 對應元件 | 說明 |
|------|------|---------|------|
| POST | `/v1/fleet/deploy-node/bootstrap` | 節點上線精靈 | 建立 bootstrap session 並產生部署工件 |
| GET | `/v1/fleet/deploy-node/bootstrap/{id}/artifacts` | 節點上線精靈 | 下載 `docker-compose.yml`、`.env`、`deploy.sh` 工件包 |
| GET | `/v1/fleet/deploy-node/bootstrap/{id}/stream` | 節點上線精靈 | SSE 串流：`artifact_ready → completed` 進度事件 |
| DELETE | `/v1/fleet/deploy-node/bootstrap/{id}` | 節點上線精靈 | 取消 bootstrap session |

### 模型部署與 Scheduler（Console 端）

| 方法 | 路徑 | 對應元件 | 說明 |
|------|------|---------|------|
| GET | `/v1/fleet/models` | 模型目錄頁 | 列出 Fleet 記憶體中的模型目錄 |
| GET | `/v1/fleet/models/{model_code}` | 模型詳情頁 | 單一模型規格 |
| POST | `/v1/fleet/schedule` | 部署前預覽 | Dry-run 放置：回傳最佳候選節點，不建立命令 |
| POST | `/v1/fleet/deploy` | 部署對話框 | 排程模型並派送 `deploy` 命令至目標節點 |
| POST | `/v1/fleet/undeploy` | 服務管理 | 派送 `undeploy` 命令至運行中的服務 |
| GET | `/v1/fleet/commands` | 命令歷史頁 | 列出命令；支援 `?node_id=&status=` 篩選 |
| GET | `/v1/fleet/commands/{command_id}` | 命令詳情頁 | 單一命令狀態 |

### 部署意圖（PRD-128 P3b）

| 方法 | 路徑 | 對應元件 | 說明 |
|------|------|---------|------|
| POST | `/v1/fleet/deployments` | `DeploymentsTab` | 在 IAM 建立部署意圖；若節點已運行則立即派送部署命令 |
| GET | `/v1/fleet/deployments` | `DeploymentsTab` | 列出 group 範圍內的部署；`?include_stopped=true` 包含已停止項目 |
| GET | `/v1/fleet/deployments/by-alias/{alias}` | `DeploymentsTab` | 透過別名查詢部署 |
| GET | `/v1/fleet/deployments/{uuid}` | 部署詳情頁 | 單一部署（超出 scope 回傳 404） |
| PATCH | `/v1/fleet/deployments/{uuid}` | 部署編輯頁 | 更新意圖；狀態轉換時自動觸發 deploy/undeploy |
| DELETE | `/v1/fleet/deployments/{uuid}` | 部署清單 | 軟刪除：設定 `desired_state='stopped'` 並執行 undeploy |

### Port 登錄（PRD-126 / ADR-156）

| 方法 | 路徑 | 對應元件 | 說明 |
|------|------|---------|------|
| GET | `/v1/fleet/nodes/{node_id}/ports` | 節點 port 頁面 | 列出 port 池與已保留項目 |
| GET | `/v1/fleet/nodes/{node_id}/ports/free` | 節點 port 頁面 | 列出 `public_port_range` 內未分配的 port |
| PUT | `/v1/fleet/nodes/{node_id}/port-pool` | 節點設定 | 宣告或替換 `NodePortPool`；冪等操作 |
| POST | `/v1/fleet/nodes/{node_id}/ports/reserve` | 運維工具 | 手動預先佔用一個 port |
| DELETE | `/v1/fleet/nodes/{node_id}/ports/{port}` | 運維工具 | 釋放 port 保留 |

### Plugin 工作負載規格（PRD-115 / ADR-145）

| 方法 | 路徑 | 對應元件 | 說明 |
|------|------|---------|------|
| POST | `/v1/fleet/plugin-specs` | Plugin 規格編輯器 | 建立工作負載規格；自動產生 `workload_key`；重複回傳 409 |
| GET | `/v1/fleet/plugin-specs` | Plugin 規格清單 | 列出所有規格；支援 `?tenant_uuid=` 篩選 |
| GET | `/v1/fleet/plugin-specs/{spec_id}` | Plugin 規格詳情 | 單一規格，含 instances 與協調狀態 |
| PATCH | `/v1/fleet/plugin-specs/{spec_id}` | Plugin 規格編輯器 | 樂觀鎖更新（`expected_generation`） |
| DELETE | `/v1/fleet/plugin-specs/{spec_id}` | Plugin 規格清單 | 軟刪除；instance 清理透過 reconciler 非同步執行 |

### 模型目錄瀏覽（PRD-128 P3a — IAM L2 代理）

| 方法 | 路徑 | 對應元件 | 說明 |
|------|------|---------|------|
| GET | `/v1/fleet/catalog/models` | 目錄瀏覽頁 | 從 IAM L2 列出 `ModelDefinitions`；`?include_removed=true` 包含已移除項目 |
| GET | `/v1/fleet/catalog/models/{name}` | 目錄詳情頁 | 模型 + 版本清單 |
| GET | `/v1/fleet/catalog/models/{name}/versions/{version}` | 目錄詳情頁 | 單一版本詳情 |

### Benchmark

| 方法 | 路徑 | 對應元件 | 說明 |
|------|------|---------|------|
| POST | `/v1/fleet/nodes/{node_id}/benchmark` | 節點管理 | 觸發能耗 benchmark；派送 `energy_benchmark` 命令 |
| GET | `/v1/fleet/nodes/{node_id}/benchmark` | 節點管理 | 取得最新 benchmark 進度與結果 |

### Services（舊版代理）

| 方法 | 路徑 | 對應元件 | 說明 |
|------|------|---------|------|
| GET | `/v1/services` | 服務清單頁 | 跨所有節點的 vLLM 服務聚合清單 |
| GET | `/v1/services/{name}` | 服務詳情頁 | 代理至 xparse-node-mgr 的服務詳情 |
| GET | `/v1/services/{name}/logs` | 服務日誌頁 | 代理日誌串流至 xparse-node-mgr（`?tail=N`） |
| POST | `/v1/services/apply` | 服務部署 | 代理部署請求至 xparse-node-mgr |
| POST | `/v1/services/delete` | 服務刪除 | 代理服務刪除；Fleet 依服務名稱解析目標節點 |

---

## 後端 APIs

供其他後端服務（IAM、Gateway、Scheduler、agentd/xparse-node-mgr）呼叫的端點。

### Heartbeat（agentd → Fleet）

| 方法 | 路徑 | 呼叫方 | 說明 |
|------|------|--------|------|
| POST | `/v1/fleet/heartbeat` | xparse-node-mgr（agentd） | 節點狀態回報：GPU、服務、工作負載、命令執行結果、port 觀測快照。回應中的 `pending_commands[]` 為待執行命令。認證：IAM `xp_live_*` token（預設停用 legacy bearer token）。 |

### Gateway 路由（Gateway → Fleet）

| 方法 | 路徑 | 呼叫方 | 說明 |
|------|------|--------|------|
| GET | `/v1/fleet/model-profiles` | xparse-gateway | 將 Fleet 中就緒的服務轉換為 Gateway 相容的 model profile |
| GET | `/v1/fleet/routable-endpoints` | xparse-gateway | 回傳符合三重 AND 條件的可路由服務端點（SPEC-093 §10）：node_state ∈ {active, deploying, degraded}、tier ≥ T1、service.status == ready |

### Scheduler 整合（Scheduler ↔ Fleet）

| 方向 | 方法 | 路徑 | 說明 |
|------|------|------|------|
| Scheduler → Fleet | POST | `/v1/fleet/workloads/deploy` | 將工作負載放置到最佳可用節點；由 Scheduler 選定節點並產生 `workload_id` |
| Fleet → Scheduler | POST | `{FLEET_SCHEDULER_URL}/nodes/{node_id}/report` | 將 heartbeat 取得的節點容量與用量中繼至 Scheduler（盡力送出，不阻塞 heartbeat） |

### 目錄協調（Fleet ↔ IAM）

| 方法 | 路徑 | 呼叫方 | 說明 |
|------|------|--------|------|
| POST | `/v1/fleet/catalog/validate` | IAM / Console | Dry-run 驗證目錄規格；回傳正規化後的規格，不持久化 |
| POST | `/v1/fleet/catalog/reconcile` | IAM / Console | 將 Fleet 記憶體目錄同步至 IAM L2；回傳協調摘要 |
| GET | `/v1/fleet/catalog/reconcile/status` | Console | 中繼 IAM 最近一次協調快照（completed_at、計數、錯誤） |
| GET | `/v1/catalog/models` | Console（舊版） | 代理模型目錄至預設 xparse-node-mgr |

### 節點上線（deploy.sh / 節點 → Fleet — 無需認證）

| 方法 | 路徑 | 呼叫方 | 認證 | 說明 |
|------|------|--------|------|------|
| GET | `/v1/fleet/bootstrap/registry-ca` | 節點 bootstrap 腳本 | **無需認證** | 回傳 Registry CA PEM（公鑰，可安全公開存取） |
| POST | `/v1/fleet/deploy-node/bootstrap/{id}/claim` | `deploy.sh` | activation_code 憑證 | 提交硬體指紋；原子性消耗 activation_code（BOOTSTRAP-03） |
| GET | `/v1/fleet/deploy-node/bootstrap/{id}/install.sh` | `deploy.sh` | `?token={bootstrap_secret}` | 一次性下載安裝腳本（首次 GET 後即失效） |

### Port 動態分配（agentd → Fleet）

| 方法 | 路徑 | 呼叫方 | 說明 |
|------|------|--------|------|
| POST | `/v1/fleet/nodes/{node_id}/ports/allocate` | agentd | 從 `public_port_range` 自動選取可用 port；回傳 REQUESTED 狀態的分配記錄（預設 5 分鐘 TTL） |
| POST | `/v1/fleet/nodes/{node_id}/ports/allocations/{id}/bind` | agentd | REQUESTED → BOUND；綁定 `container_id`（相同 container_id 重複呼叫為冪等） |
| DELETE | `/v1/fleet/nodes/{node_id}/ports/allocations/{id}` | agentd | 釋放分配：BOUND → RELEASED |
| POST | `/v1/fleet/nodes/{node_id}/ports/reconcile` | agentd / Heartbeat | 比對 `docker ps` 快照與 port 登錄；依來源套用清理策略（SPEC-126 §3.4） |

### 工作負載節點操作（Scheduler → Fleet → 節點）

| 方法 | 路徑 | 呼叫方 | 說明 |
|------|------|--------|------|
| POST | `/v1/fleet/nodes/{node_id}/deploy` | Scheduler / Console | 派送 `create_workload` 命令至指定節點的沙箱 |
| POST | `/v1/fleet/nodes/{node_id}/destroy` | Scheduler / Console | 派送 `destroy_workload` 命令 |
| POST | `/v1/fleet/nodes/{node_id}/stop` | Scheduler / Console | 暫停工作負載；保留 volume（ADR-140） |
| POST | `/v1/fleet/nodes/{node_id}/start` | Scheduler / Console | 啟動先前暫停的工作負載 |

### 執行期事件轉送（Fleet → IAM，非同步射後不理）

| 方向 | 端點 | 說明 |
|------|------|------|
| Fleet → IAM | `{FLEET_IAM_BASE_URL}/iam/fleet/runtime/...` | 將 deploy/undeploy 終態結果及進行中的部署階段（pulling/starting/health_check）轉送至 IAM `fleet_runtime_*` 資料表（PRD-128 P4a）。未設定 IAM 時為 no-op；絕不阻塞 heartbeat ack。 |

---

## 工作流程

### 1. 節點 Heartbeat 週期

```
agentd（xparse-node-mgr）
  → POST /v1/fleet/heartbeat  （每 ~30 秒）
      payload：{ node_id, services[], gpus[], workloads[], command_results[], capacity, usage, host_ports_observed }

Fleet（FleetStateManager）
  1. 透過 IAM /iam/auth/validate 驗證 token（xp_live_* 前綴或 iam_only 模式）
  2. 更新節點狀態、GPU/服務快照、工作負載清單
  3. 處理 command_results[] → 更新 CommandQueue，觸發驗證准入流程
  4. 比對 host_ports_observed 協調 port 登錄（若有提供）
  5. 透過 RuntimeEventForwarder 轉送 deploy 終態至 IAM（非同步，射後不理）
  6. 轉送 active_deployments 階段至 IAM（非同步）
  7. 中繼容量與用量至 Scheduler POST /nodes/{node_id}/report（盡力送出）
  8. 回傳 HeartbeatAckResponse：{ ack, approved, node_state, pending_commands[] }

agentd 接收 pending_commands[] 並執行對應動作
```

### 2. 節點上線（Bootstrap）

```
Console（操作者）
  → POST /v1/fleet/deploy-node/bootstrap  （fleet_api_url、node_id、group_uuid、port_range……）
      Fleet：建立 BootstrapSession，產生 docker-compose.yml + .env + deploy.sh + install.sh

Console
  → GET /v1/fleet/deploy-node/bootstrap/{id}/stream  （SSE）
      Fleet：推送進度事件：artifact_ready → （等待 claim）→ completed

操作者將 install.sh 下載至目標機器並執行：
  deploy.sh
    → GET /v1/fleet/deploy-node/bootstrap/{id}/install.sh?token={secret}   （一次性下載）
    → POST /v1/fleet/deploy-node/bootstrap/{id}/claim  { hardware_fingerprint }
        Fleet：驗證硬體指紋限制條件，消耗 activation_code，標記 session 已認領

agentd 在節點啟動 → POST /v1/fleet/heartbeat → 節點進入 REGISTERED 狀態

Console
  → POST /v1/fleet/nodes/{node_id}/approve   （REGISTERED → APPROVED）
  → POST /v1/fleet/nodes/{node_id}/validate  （APPROVED → VALIDATING；派送 validate 命令）
      Fleet → heartbeat ack → agentd 執行驗證 → 下次 heartbeat 回報結果
      Fleet：process_validation_result → ADMITTED（通過時，依 profile 指派 tier）
```

### 3. 模型部署（Console 發起）

```
Console
  → POST /v1/fleet/schedule  （dry-run：預覽放置結果，無任何副作用）
  → POST /v1/fleet/deploy    { model_code, node_id（可選） }

Fleet（scheduler）
  1. 執行放置：依 GPU 可用性與模型親和性選出最佳節點
  2. 將 deploy 命令加入目標節點的 CommandQueue
  3. 回傳 { command_id, node_id }

下一次目標節點的 agentd heartbeat：
  ← HeartbeatAck.pending_commands[] 包含 deploy 命令

agentd 執行 docker pull + 啟動 vLLM 容器 → 下次 heartbeat 回報結果：
  POST /v1/fleet/heartbeat { command_results: [{ command_id, status: "done", result: { ... } }] }

Fleet：
  - 更新 CommandQueue 狀態
  - 服務出現在下次 heartbeat 的 services[] → ServiceRegistry 同步
  - RuntimeEventForwarder 將階段更新轉送至 IAM

Gateway（定期輪詢）
  → GET /v1/fleet/routable-endpoints
  ← Fleet 回傳符合條件的就緒服務（節點狀態 ACTIVE/DEPLOYING/DEGRADED，tier ≥ T1）
```

### 4. 目錄協調（Fleet → IAM L2）

```
Fleet 啟動時（app.py lifespan）：
  asyncio.create_task(run_startup_reconcile(catalog_client, model_catalog))

CatalogReconcileClient
  → POST {FLEET_IAM_BASE_URL}/iam/admin/catalog/models  （對應 config/models.yaml 中每個模型）
      認證：FLEET_IAM_ADMIN_KEY

Console（手動觸發）
  → POST /v1/fleet/catalog/reconcile
      Fleet：CatalogReconcileClient.reconcile() → IAM L2 upsert
      回傳：{ upserted, skipped, errors }

Console（狀態查詢）
  → GET /v1/fleet/catalog/reconcile/status
      Fleet：中繼 IAM 最近一次協調快照
```

### 5. Agent App 部署（ADR-110 + ADR-136）

```
Console
  → POST /v1/fleet/apps/{app_code}/deploy  { node_ids[], replicas }
      Fleet：查詢 FLEET_APP_DEPLOYMENTS 設定中的 app_code
             對每個目標節點派送 create_workload 命令

各節點的 agentd：
  - 透過 heartbeat ack 的 pending_commands[] 接收命令
  - 拉取映像檔、啟動容器、啟動 sidecar proxy（ADR-136 nginx）
  - 下次 heartbeat 的 workloads[] 回報工作負載狀態

Fleet：
  - 更新 FleetStateManager 中的 WorkloadInfo
  - RuntimeEventForwarder → IAM fleet_runtime_* 資料表

Console
  → GET /v1/fleet/apps/{app_code}/endpoint
      Fleet：從 FLEET_APP_DEPLOYMENTS 設定回傳第一個健康的 instance 端點
             （依 app 設定採 round-robin 或 sticky LB）
```

### 6. Port 分配生命週期（agentd，PRD-126 / ADR-160）

```
agentd（啟動容器前）
  → POST /v1/fleet/nodes/{node_id}/ports/allocate  { allocated_to, purpose, preferred_port? }
      Fleet：在 public_port_range 內選取下一個可用 port（碰撞檢查 reserved + 活躍分配）
      回傳：{ allocation_id, port, state: "REQUESTED", expires_at }

agentd（docker run 成功、取得 container_id 後）
  → POST /v1/fleet/nodes/{node_id}/ports/allocations/{id}/bind  { container_id }
      Fleet：REQUESTED → BOUND，綁定 container_id（相同 container_id 為冪等）

TTL 回收器（FleetState 內部，在 heartbeat 處理中執行）：
  - 超過 expires_at 且仍為 REQUESTED 的分配 → EXPIRED

agentd（容器銷毀時）
  → DELETE /v1/fleet/nodes/{node_id}/ports/allocations/{id}
      Fleet：BOUND → RELEASED

heartbeat（每個週期，若 host_ports_observed 存在）
  → Fleet：reconcile_node_ports(node_id, {host_port: container_id})
      Fleet 依來源套用策略（SPEC-126 §3.4）：
        - manual_run / observed_at_reconcile + 未觀測到 → MARK_RELEASED
        - compose / legacy → NO_OP
```

### 7. 節點驗證流程（PRD-079 / ADR-112）

```
Console
  → POST /v1/fleet/nodes/{node_id}/validate?profile=standard
      Fleet：狀態轉換 APPROVED/ADMITTED/QUARANTINED → VALIDATING
             將 validate 命令加入 CommandQueue

agentd（透過 heartbeat ack 的 pending_commands[]）：
  - 執行硬體驗證測試（GPU、記憶體、網路等）
  - 在 heartbeat 的 validation_summary 回報進度
  - 在 command_results[{ command_id, result: { profile: {...} } }] 回報最終結果

Fleet（下次 heartbeat 時）：
  1. process_validation_result(node_id, command_result)
  2. 通過：VALIDATING → ADMITTED，依 profile 指派 tier
  3. 失敗：VALIDATING → QUARANTINED

Console
  → GET /v1/fleet/nodes/{node_id}/validation
      回傳：{ node_state, tier, summary }
```

### 8. 部署意圖生命週期（PRD-128 P3b — Console + IAM）

```
Console
  → POST /v1/fleet/deployments  { model_code, node_id, desired_state: "running", ... }
      Fleet → IAM：POST {FLEET_IAM_BASE_URL}/iam/admin/fleet/deployments  （建立意圖）
      Fleet：若節點已運行 → 立即派送 deploy 命令
      回傳：{ deployment_uuid, ... }

Console
  → GET /v1/fleet/deployments  （輪詢狀態）
      Fleet → IAM：取得 group 範圍內的部署清單

agentd 執行部署 → 透過 heartbeat command_results[] 回報
  Fleet → IAM RuntimeEventForwarder：更新部署執行期狀態

Console
  → DELETE /v1/fleet/deployments/{uuid}
      Fleet：設定 desired_state = 'stopped' + 派送 undeploy 命令
```
