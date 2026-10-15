# Xparse Backend API 完整清單

所有服務的 HTTP endpoint、說明與用途。以呼叫方視角組織：誰打這個 API、做什麼事。

---

## 服務入口總表

| 服務 | Port | 主要呼叫方 |
|------|------|-----------|
| Gateway (`bustream`) | 8000 | 外部 Client / SDK / Console |
| IAM (`xparse_iam`) | 8010 | Gateway、Console、內部服務 |
| ResourceManager (`xparse_resource_manager`) | 8020 | Gateway |
| Audit (`xparse_audit`) | 8030 | Gateway（SDK emit）/ Console |
| Fleet (`xparse_fleet`) | 8090 | Console、agentd、Gateway |
| Scheduler (`xparse_scheduler`) | — | Fleet、IAM |

---

## 1. Gateway — `bustream/` (port 8000)

對外的 OpenAI-compatible API。所有 AI 推論請求的入口。

### AI 推論

| Method | Path | 說明 |
|--------|------|------|
| `POST` | `/v1/chat/completions` | 主推論端點，支援 streaming SSE（OpenAI-compatible）。驗身份 → Policy → Admission → 打 Provider → 回傳 SSE 串流 |
| `POST` | `/v1/embeddings` | 向量嵌入，回傳 float array |
| `POST` | `/v1/audio/speech` | TTS 語音合成，回傳音訊檔 |
| `GET`  | `/v1/models` | 列出目前可用的模型（從 Fleet model-profiles 拉取） |

### Admin / Routing（內部管理）

| Method | Path | 說明 |
|--------|------|------|
| `POST`   | `/admin/keys` | 建立 Legacy admin API key |
| `GET`    | `/admin/keys` | 列出所有 Legacy admin keys |
| `DELETE` | `/admin/keys/{key}` | 刪除指定 key |
| `POST`   | `/admin/registry/reload` | 重新載入 routing config（熱更新，不重啟） |
| `GET`    | `/routing/config/{app_uuid}` | 查詢指定 Application 的 routing 設定 |
| `PUT`    | `/routing/config/{app_uuid}` | 更新指定 Application 的 routing 設定 |

### 系統

| Method | Path | 說明 |
|--------|------|------|
| `GET` | `/health` | 健康檢查 |
| `GET` | `/metrics` | Prometheus metrics（request count、latency、token usage） |

---

## 2. IAM — `xparse_iam/` (port 8010)

治理資料平面。管理所有身份、授權、策略、Provider 憑證。

### 身份驗證（Auth）

| Method | Path | 說明 |
|--------|------|------|
| `POST` | `/iam/auth/validate` | 驗證 API key，回傳 auth context（舊版，Gateway 呼叫） |
| `GET`  | `/iam/auth/verify-session` | 驗證 session cookie（nginx auth_request 使用） |
| `POST` | `/iam/auth/logout` | 清除 session cookie |
| `GET`  | `/iam/auth/resolve-deployment` | 解析 backward-compat 部署 URL |
| `POST` | `/iam/api-keys` | 建立 Application-level API key |
| `POST` | `/iam/api-keys/{uuid}/revoke` | 撤銷 API key |
| `POST` | `/iam/api-keys/{uuid}/rotate` | Rotate API key（雙 key overlap，不中斷服務） |
| `POST` | `/iam/derive` | 衍生 encrypted_provider key（BYOK 短效 token） |
| `GET`  | `/iam/console/capabilities` | 取得 Console 頁面的功能權限矩陣（Console 前端用） |
| `GET`  | `/iam/console/edition` | 取得安裝版本資訊（pro / enterprise / basic） |

### Tenant 管理

| Method | Path | 說明 |
|--------|------|------|
| `POST`  | `/iam/tenants` | 建立新 Tenant |
| `GET`   | `/iam/tenants` | 列出所有 Tenant |
| `GET`   | `/iam/tenants/{uuid}` | 取得 Tenant 詳細資訊 |
| `PUT`   | `/iam/tenants/{uuid}` | 更新 Tenant（目前只支援 name） |
| `PATCH` | `/iam/tenants/{uuid}/status` | 變更 Tenant 狀態（suspend / reactivate） |
| `GET`   | `/iam/tenants/{uuid}/settings` | 取得 Tenant 設定（含 feature flags） |
| `PATCH` | `/iam/tenants/{uuid}/settings/feature-flags` | 更新 Tenant feature flags（tri-state） |
| `POST`  | `/iam/tenants/{uuid}/keys` | 建立 Tenant-level API key |
| `GET`   | `/iam/tenants/{uuid}/keys` | 列出 Tenant 的所有 API keys |
| `POST`  | `/iam/tenants/{uuid}/keys/{key_uuid}/revoke` | 撤銷 Tenant API key |
| `POST`  | `/iam/tenants/{uuid}/keys/{key_uuid}/rotate` | Rotate Tenant API key |

### Group 管理

| Method | Path | 說明 |
|--------|------|------|
| `POST`   | `/iam/groups` | 建立 Group |
| `GET`    | `/iam/groups` | 列出 Groups（依 data scope 過濾） |
| `GET`    | `/iam/groups/{uuid}` | 取得 Group 詳細資訊 |
| `PUT`    | `/iam/groups/{uuid}` | 更新 Group（name / description） |
| `DELETE` | `/iam/groups/{uuid}` | 停用 Group |
| `GET`    | `/iam/groups/{uuid}/members` | 列出 Group 成員（OIDC users） |
| `GET`    | `/iam/groups/{uuid}/candidate-users` | 列出可加入此 Group 的 OIDC users |
| `POST`   | `/iam/groups/{uuid}/members` | 將 OIDC user 加入 Group |
| `DELETE` | `/iam/groups/{uuid}/members/{mapping_uuid}` | 從 Group 移除成員 |
| `PATCH`  | `/iam/groups/{uuid}/members/{mapping_uuid}` | 更新成員狀態或角色 |
| `GET`    | `/iam/me/invitations` | 列出目前使用者的待接受 Group 邀請 |

### Application 管理

| Method | Path | 說明 |
|--------|------|------|
| `GET`    | `/iam/app-types` | 列出可用的 Application 類型（ADR-115 type registry） |
| `POST`   | `/iam/groups/{uuid}/applications` | 用 type-based 流程建立 Application（ADR-115） |
| `POST`   | `/iam/applications` | 建立 Application（legacy，直接綁定 models） |
| `GET`    | `/iam/applications` | 列出 Applications（依 data scope 過濾） |
| `GET`    | `/iam/applications/{uuid}` | 取得 Application 詳細資訊 |
| `PUT`    | `/iam/applications/{uuid}` | 更新 Application |
| `DELETE` | `/iam/applications/{uuid}` | 軟刪除 Application（設為 SUSPENDED） |
| `GET`    | `/iam/applications/{uuid}/policy-summary` | 取得所有綁定的 Policy 摘要（含 enforcement 狀態） |
| `GET`    | `/iam/applications/{uuid}/api-keys` | 列出 Application 的所有 API keys |
| `GET`    | `/iam/applications/{uuid}/effective-config` | 取得解析後的 routing + policy 設定（Gateway 用） |

### Provider 管理（BYOK）

| Method | Path | 說明 |
|--------|------|------|
| `GET`    | `/iam/provider-definitions` | 列出所有 Provider 定義（OpenAI、Azure 等） |
| `GET`    | `/iam/provider-definitions/{code}` | 取得單一 Provider 定義 |
| `POST`   | `/iam/provider-definitions` | 新增 Provider 定義 |
| `PUT`    | `/iam/provider-definitions/{code}` | 更新 Provider 定義 |
| `DELETE` | `/iam/provider-definitions/{code}` | 刪除 Provider 定義 |
| `POST`   | `/iam/provider-credentials` | 登錄 Provider Credential（企業自帶 API key，BYOK） |
| `GET`    | `/iam/provider-credentials` | 列出 Provider Credentials（不含加密欄位） |
| `GET`    | `/iam/provider-credentials/{uuid}` | 取得 Credential metadata |
| `PUT`    | `/iam/provider-credentials/{uuid}/rotate` | Rotate Credential（原子替換加密 key） |
| `PUT`    | `/iam/provider-credentials/{uuid}/revoke` | 撤銷 Credential |
| `DELETE` | `/iam/provider-credentials/{uuid}` | 刪除 Credential |
| `POST`   | `/iam/provider-credentials/{uuid}/test` | 探測 Provider 驗證 Credential 是否有效（不需模型 context） |

### Policy 管理

| Method | Path | 說明 |
|--------|------|------|
| `POST`   | `/iam/rate-limit-policies` | 建立 Rate Limit Policy |
| `GET`    | `/iam/rate-limit-policies` | 列出所有 Rate Limit Policies |
| `GET`    | `/iam/rate-limit-policies/{uuid}` | 取得 Rate Limit Policy 詳情 |
| `PUT`    | `/iam/rate-limit-policies/{uuid}` | 更新 Rate Limit Policy |
| `DELETE` | `/iam/rate-limit-policies/{uuid}` | 刪除 Rate Limit Policy |
| `PUT`    | `/iam/applications/{uuid}/rate-limit-policy` | 將 Rate Limit Policy 綁定到 Application |
| `POST`   | `/iam/guardrail-policies` | 建立 Guardrail Policy（content filter 規則） |
| `GET`    | `/iam/guardrail-policies` | 列出所有 Guardrail Policies |
| `GET`    | `/iam/guardrail-policies/{uuid}` | 取得 Guardrail Policy 詳情 |
| `PUT`    | `/iam/guardrail-policies/{uuid}` | 更新 Guardrail Policy |
| `DELETE` | `/iam/guardrail-policies/{uuid}` | 刪除 Guardrail Policy |
| `PUT`    | `/iam/applications/{uuid}/guardrail-policy` | 將 Guardrail Policy 綁定到 Application |
| `POST`   | `/iam/policy-bundles` | 建立 Policy Bundle（進階授權引擎） |
| `GET`    | `/iam/policy-bundles` | 列出 Policy Bundles |
| `GET`    | `/iam/policy-bundles/{uuid}` | 取得 Policy Bundle 詳情 |
| `PATCH`  | `/iam/policy-bundles/{uuid}/status` | 更新 Bundle 狀態 |
| `POST`   | `/iam/policy-bindings` | 建立 Policy Binding（將 Bundle 綁定到 Application） |
| `GET`    | `/iam/policy-bindings` | 列出 Policy Bindings |
| `PATCH`  | `/iam/policy-bindings/{uuid}/status` | 更新 Binding 狀態 |

### Catalog & Deployment

| Method | Path | 說明 |
|--------|------|------|
| `POST`   | `/iam/catalog/reconcile` | 將 Fleet model specs 同步到 IAM L2 catalog |
| `GET`    | `/iam/catalog/reconcile/status` | 取得最近一次 reconcile 結果 |
| `GET`    | `/iam/catalog/models` | 列出所有 Model 定義 |
| `GET`    | `/iam/catalog/models/{name}` | 取得 Model 定義 + 版本清單 |
| `GET`    | `/iam/catalog/models/{name}/versions/{version}` | 取得特定 Model 版本詳情 |
| `POST`   | `/iam/catalog/deployments` | 建立 Deployment intent（模型部署意圖） |
| `GET`    | `/iam/catalog/deployments` | 列出所有 Deployments |
| `GET`    | `/iam/catalog/deployments/by-alias/{alias}` | 用 alias 查詢 Deployment |
| `GET`    | `/iam/catalog/deployments/{uuid}` | 取得 Deployment 詳情 |
| `PATCH`  | `/iam/catalog/deployments/{uuid}` | 更新 desired_version / quota / desired_state |
| `DELETE` | `/iam/catalog/deployments/{uuid}` | 軟刪除 Deployment |
| `POST`   | `/iam/applications/{uuid}/bind-deployment` | 將 Application 綁定到 Deployment |
| `GET`    | `/iam/applications/{uuid}/bound-deployments` | 列出 Application 已綁定的 Deployments |
| `POST`   | `/iam/applications/{uuid}/deployments` | 經由 Scheduler 建立 Deployment |
| `GET`    | `/iam/applications/{uuid}/deploy-preflight` | 部署前容量預檢 |
| `GET`    | `/iam/applications/{uuid}/deployments` | 列出 Application 的 Deployments |
| `GET`    | `/iam/deployments/{uuid}` | 取得 Deployment 詳情 |
| `PATCH`  | `/iam/deployments/{uuid}` | 更新 Deployment 狀態 / scope |
| `POST`   | `/iam/deployments/{uuid}/keys` | 建立 Deployment key（Agent login 用） |
| `GET`    | `/iam/deployments/{uuid}/keys` | 列出 Deployment keys |
| `DELETE` | `/iam/deployments/{uuid}/keys/{key_uuid}` | 撤銷 Deployment key |
| `POST`   | `/iam/deployments/{uuid}/assign-key` | 將 API key 指派給 Deployment |
| `POST`   | `/iam/deployments/{uuid}/unassign-key` | 解除 API key 與 Deployment 的關聯 |

### OIDC / SSO

| Method | Path | 說明 |
|--------|------|------|
| `GET`    | `/iam/oidc/config` | 取得 OIDC 設定（public，Console 登入頁用） |
| `POST`   | `/iam/oidc/exchange` | 用 OIDC ID token 換取 session key |
| `POST`   | `/iam/oidc/user-mappings` | 建立 OIDC user mapping（對應到 Tenant / Group） |
| `GET`    | `/iam/oidc/user-mappings` | 列出所有 OIDC user mappings |
| `GET`    | `/iam/oidc/user-mappings/{uuid}` | 取得 mapping 詳情 |
| `PUT`    | `/iam/oidc/user-mappings/{uuid}` | 更新 mapping（email / group） |
| `DELETE` | `/iam/oidc/user-mappings/{uuid}` | 停用 mapping |
| `POST`   | `/iam/oidc/user-mappings/{uuid}/reactivate` | 重新啟用 mapping |
| `POST`   | `/iam/oidc/user-mappings/{uuid}/emergency-unlock` | 緊急解鎖（覆蓋自動停用保護） |
| `POST`   | `/iam/oidc/tenant-group-bindings` | 建立 Tenant ↔ Keycloak group 綁定 |
| `GET`    | `/iam/oidc/tenant-group-bindings` | 列出所有 bindings |
| `GET`    | `/iam/oidc/tenant-group-bindings/{uuid}` | 取得 binding 詳情 |
| `DELETE` | `/iam/oidc/tenant-group-bindings/{uuid}` | 軟刪除 binding |

### Skills & Plugins

| Method | Path | 說明 |
|--------|------|------|
| `POST`   | `/iam/groups/{uuid}/skills/install` | 安裝 Skill 到 Group |
| `DELETE` | `/iam/groups/{uuid}/skills/{inst_uuid}` | 解除安裝 Skill |
| `GET`    | `/iam/groups/{uuid}/skills` | 列出 Group 的 Skill installations |
| `GET`    | `/iam/applications/{uuid}/skills` | 列出 Application 已部署的 Skills |
| `GET`    | `/iam/applications/{uuid}/skills/drift` | 偵測 Skill selection drift |
| `PATCH`  | `/iam/applications/{uuid}/skills/selections` | 更新 Skill 選擇 |
| `POST`   | `/iam/applications/{uuid}/skills/reconcile` | 重新部署 Skills |
| `GET`    | `/iam/applications/{uuid}/skills/mount-plan` | 取得容器 mount plan |
| `GET`    | `/iam/plugins` | 列出 Plugin catalog |
| `POST`   | `/iam/plugins` | 建立 Plugin 定義 |
| `GET`    | `/iam/plugins/{slug}` | 取得 Plugin 定義 |
| `GET`    | `/iam/plugins/{slug}/versions` | 列出 Plugin 版本 |
| `POST`   | `/iam/plugins/{slug}/versions` | 發布 Plugin 版本 |
| `POST`   | `/iam/plugins/{slug}/install` | 安裝 Plugin 到 Group |
| `GET`    | `/iam/plugins/installations` | 列出所有 Plugin installations |
| `DELETE` | `/iam/plugins/installations/{uuid}` | 解除安裝 Plugin |

### Model 管理

| Method | Path | 說明 |
|--------|------|------|
| `POST`  | `/iam/groups/{uuid}/models` | 在 Group 中建立 Model |
| `GET`   | `/iam/groups/{uuid}/models` | 列出 Group 的所有 Models |
| `GET`   | `/iam/models/{uuid}` | 取得 Model 詳情 |
| `PATCH` | `/iam/models/{uuid}` | 更新 Model 欄位 |
| `POST`  | `/iam/models/{uuid}/override` | 寫入 manual override 欄位（escape hatch） |
| `DELETE`| `/iam/models/{uuid}/override/{field}` | 移除 manual override 欄位 |

### Quota & Node Allocation

| Method | Path | 說明 |
|--------|------|------|
| `POST`   | `/iam/admin/node-allocations` | 建立 Node Allocation（指定 GPU 給 Tenant） |
| `GET`    | `/iam/admin/node-allocations` | 列出所有 Node Allocations |
| `PUT`    | `/iam/admin/node-allocations/{uuid}` | 更新 Node Allocation |
| `DELETE` | `/iam/admin/node-allocations/{uuid}` | 刪除 Node Allocation |
| `POST`   | `/iam/tenants/{uuid}/group-quotas` | 建立 Group Quota（限制 Group 的 GPU 用量） |

### Node Activation（節點接入用）

| Method | Path | 說明 |
|--------|------|------|
| `POST` | `/iam/node-activations` | 發行 Activation code（agentd 首次接入用） |
| `POST` | `/iam/node-activations/validate` | 驗證 Activation code（read-only，不消耗） |
| `POST` | `/iam/node-activations/consume` | 消耗 Activation code（原子操作，一次性） |

### Bootstrap & 工具

| Method | Path | 說明 |
|--------|------|------|
| `POST` | `/iam/bootstrap` | 一次性管理員初始化（第一次安裝用） |
| `GET`  | `/iam/model-options` | 取得模型 / Provider 參考資料（Console 下拉選單用） |
| `POST` | `/iam/models/test-connection` | 測試模型連線 |
| `GET`  | `/iam/user/my-deployments` | 列出目前使用者的 Deployments |

### Internal（服務間內部呼叫，不對外）

| Method | Path | 呼叫方 | 說明 |
|--------|------|--------|------|
| `POST` | `/iam/internal/gateway-validate` | Gateway | 驗證 API key 並回傳完整 tenant / policy context |
| `POST` | `/iam/internal/resolve-provider-credential` | agentd | 解析加密的 Provider Credential |
| `GET`  | `/iam/internal/resource-profiles/{app_uuid}` | Gateway | 取得 Application resource profile |
| `GET`  | `/iam/internal/node-allocations` | Scheduler | 列出 Node Allocations（服務間呼叫） |
| `GET`  | `/iam/internal/group-quotas/{uuid}` | Scheduler | 取得 Group quota |
| `GET`  | `/iam/internal/deployment-count/{app_uuid}` | 內部 | 取得 Application active deployment 數量 |

---

## 3. ResourceManager — `xparse_resource_manager/` (port 8020)

Endpoint 容量守衛。Gateway 打 Provider 前必須先取得 lease。

### 核心（Gateway 呼叫）

| Method | Path | 說明 |
|--------|------|------|
| `POST` | `/resource/endpoints/{endpoint_id}/acquire` | 申請 lease（排隊，超過 max_concurrent 則 block 等待） |
| `POST` | `/resource/endpoints/{endpoint_id}/release` | 釋放 lease（讓下一個等待者通過） |
| `GET`  | `/resource/endpoints/{endpoint_id}/status` | 查詢 endpoint 目前狀態（queue depth、active leases） |

### Admin（管理）

| Method | Path | 說明 |
|--------|------|------|
| `PUT`    | `/resource/endpoints/{endpoint_id}` | 新增或更新 endpoint config（max_concurrent、priority） |
| `GET`    | `/resource/endpoints` | 列出所有 endpoint configs |
| `DELETE` | `/resource/endpoints/{endpoint_id}` | 移除 endpoint config |

---

## 4. Audit — `3rd/xparse_audit/` (port 8030)

Audit event 查詢、Evidence 生成、統計分析。Gateway 透過 SDK 直接寫入，Console 透過 HTTP 查詢。

### Events（事件查詢）

| Method | Path | 說明 |
|--------|------|------|
| `POST` | `/events/query` | 以 JSON body 條件查詢 audit events（access control 保護） |
| `GET`  | `/events` | 以 query params 條件列出 events |
| `GET`  | `/events/types` | 列出呼叫方有權限看到的所有 event types |
| `GET`  | `/events/trace/{trace_id}` | 取得某個 trace 的所有相關 events（跨服務追蹤） |
| `GET`  | `/events/{event_id}` | 取得單筆 event 詳情 |

### Evidence（證據包）

| Method | Path | 說明 |
|--------|------|------|
| `POST`   | `/evidence/packages` | 建立 Evidence Package（打包特定時間範圍的 events） |
| `GET`    | `/evidence/packages` | 列出所有 Evidence Packages |
| `GET`    | `/evidence/packages/{id}` | 取得 Evidence Package metadata |
| `GET`    | `/evidence/packages/{id}/download` | 下載 Evidence Package（ZIP 格式，含 chain of custody） |
| `DELETE` | `/evidence/packages/{id}` | 刪除 Evidence Package |

### Stats（統計）

| Method | Path | 說明 |
|--------|------|------|
| `GET` | `/stats/summary` | Dashboard 摘要統計（總請求數、總 tokens、錯誤率） |
| `GET` | `/stats/time-series` | 時間序列資料（用於折線圖） |
| `GET` | `/stats/distribution` | Event type 分布（用於圓餅圖） |
| `GET` | `/stats/top-applications` | 依請求數排名的 Top Applications |

### Usage（用量分析）

| Method | Path | 說明 |
|--------|------|------|
| `GET` | `/usage/per-user` | 每個 user 的 LLM token 用量（透過 sidecar-gateway span correlation） |
| `GET` | `/usage/per-user/time-series` | 特定 user 的 token 用量時間序列 |
| `GET` | `/usage/correlation-health` | 診斷 sidecar-gateway correlation 狀態 |

### Diagnostics & Health

| Method | Path | 說明 |
|--------|------|------|
| `GET` | `/diagnostics/store` | 取得目前 event store 狀態（queue depth、storage path） |
| `GET` | `/health` | 健康檢查 |
| `GET` | `/health/live` | Kubernetes liveness probe |
| `GET` | `/health/ready` | Kubernetes readiness probe |

---

## 5. Fleet — `xparse_fleet/` (port 8090)

GPU 節點管理、模型部署、Agent App 服務的 control plane。

### Fleet 狀態（Console 首頁用）

| Method | Path | 說明 |
|--------|------|------|
| `GET` | `/v1/fleet/status` | Fleet 整體概覽（節點數、GPU 使用率、service 狀態） |
| `GET` | `/v1/fleet/gpu` | GPU 用量詳情（各節點的 VRAM、溫度、功耗） |
| `GET` | `/v1/fleet/nodes` | 列出所有節點及連線狀態 |
| `GET` | `/v1/fleet/nodes/{node_id}` | 取得單一節點詳情 |
| `GET` | `/v1/fleet/model-profiles` | 轉換 Fleet services 為 Gateway 可用的 model profiles（Gateway 每 30 秒 poll） |
| `GET` | `/v1/fleet/routable-endpoints` | 列出 Gateway 可路由的所有 inference endpoints（SPEC-093 §10） |

### 節點心跳

| Method | Path | 說明 |
|--------|------|------|
| `POST` | `/v1/fleet/heartbeat` | agentd 每 30 秒發一次，回報節點狀態 + workload 清單。回應帶 CommandQueue 待執行指令 |

### 節點生命週期管理

| Method | Path | 說明 |
|--------|------|------|
| `POST`   | `/v1/fleet/nodes/{node_id}/approve` | 核准節點：REGISTERED → APPROVED |
| `POST`   | `/v1/fleet/nodes/{node_id}/reject` | 拒絕節點：ANY → REJECTED（強制） |
| `POST`   | `/v1/fleet/nodes/{node_id}/admit` | Admin 直接 admit：APPROVED → ADMITTED（跳過 validation） |
| `DELETE` | `/v1/fleet/nodes/{node_id}` | 從 Fleet 完全移除節點 |

### 節點指令（Workload 層級）

| Method | Path | 說明 |
|--------|------|------|
| `POST` | `/v1/fleet/nodes/{node_id}/deploy` | 在指定節點部署 sandbox workload（enqueue create_workload 指令） |
| `POST` | `/v1/fleet/nodes/{node_id}/destroy` | 摧毀指定節點上的 workload（idempotent） |
| `POST` | `/v1/fleet/nodes/{node_id}/stop` | 停止 workload（容器停止但不移除，保留 volumes） |
| `POST` | `/v1/fleet/nodes/{node_id}/start` | 重啟已停止的 workload |

### 節點驗收（Validation）

| Method | Path | 說明 |
|--------|------|------|
| `POST` | `/v1/fleet/nodes/{node_id}/validate` | 觸發節點驗收測試：APPROVED/ADMITTED → VALIDATING |
| `GET`  | `/v1/fleet/nodes/{node_id}/validate` | 取得節點最新驗收狀態與報告 |

### 節點 Benchmark

| Method | Path | 說明 |
|--------|------|------|
| `POST` | `/v1/fleet/nodes/{node_id}/benchmark` | 觸發 energy benchmark（dispatch energy_benchmark 指令到節點） |
| `GET`  | `/v1/fleet/nodes/{node_id}/benchmark` | 取得最新 benchmark 狀態（進行中 + 最近結果） |

### Deployment（模型部署）

| Method | Path | 說明 |
|--------|------|------|
| `POST`   | `/v1/fleet/deployments` | 建立 Deployment intent 並（若有 running 節點）立即 dispatch deploy 指令 |
| `GET`    | `/v1/fleet/deployments` | 列出所有 Deployments |
| `GET`    | `/v1/fleet/deployments/by-alias/{alias}` | 用 alias 查詢 Deployment |
| `GET`    | `/v1/fleet/deployments/{uuid}` | 取得 Deployment 詳情 |
| `PATCH`  | `/v1/fleet/deployments/{uuid}` | 更新 desired_version / quota / placement / desired_state |
| `DELETE` | `/v1/fleet/deployments/{uuid}` | 軟刪除：設 desired_state='stopped' 並嘗試 undeploy |

### Agent App Services

| Method | Path | 說明 |
|--------|------|------|
| `POST` | `/v1/services/apply` | 部署或更新 Agent App（NemoClaw / OpenWebUI）到指定節點 |
| `POST` | `/v1/services/delete` | 移除指定 Agent App |
| `GET`  | `/v1/services` | 列出所有節點的 services（聚合結果） |
| `GET`  | `/v1/services/{name}` | 取得 service 詳情 |
| `GET`  | `/v1/services/{name}/logs` | 取得 service logs |

### App Endpoint（Gateway 路由用）

| Method | Path | 說明 |
|--------|------|------|
| `GET`  | `/v1/fleet/apps/{app_code}/endpoint` | 查詢 Agent App 的 upstream URL（backward compat，取第一個健康 instance） |
| `GET`  | `/v1/fleet/apps/{app_code}/deployments/{deploy_code}/endpoint` | 查詢特定 deploy_code 的 endpoint（ADR-129 Phase 1） |
| `POST` | `/v1/fleet/apps/{app_code}/deploy` | 部署 Agent App（dispatch 到節點） |

### Workload 排程

| Method | Path | 說明 |
|--------|------|------|
| `POST` | `/v1/fleet/workloads/deploy` | 自動選節點並部署 workload（CPU-first，GPU-fallback） |

### Model Catalog（節點 proxy）

| Method | Path | 說明 |
|--------|------|------|
| `GET`  | `/v1/catalog/models` | 代理轉發到 default xparse-node-mgr 的 model catalog |
| `POST` | `/v1/fleet/catalog/validate` | Dry-run 驗證 catalog spec（不寫入） |
| `POST` | `/v1/fleet/catalog/reconcile` | 將 Fleet in-memory catalog 同步到 IAM L2（PRD-128） |
| `GET`  | `/v1/fleet/catalog/reconcile/status` | 取得最近一次 reconcile 狀態 |

### Node Onboarding（新節點接入流程）

| Method | Path | 說明 |
|--------|------|------|
| `POST`   | `/v1/fleet/deploy-node` | 建立 bootstrap session，產生部署 artifacts（install script、config） |
| `POST`   | `/v1/fleet/deploy-node/{id}/claim` | 節點提交硬體 fingerprint 並 claim bootstrap session（PRD-131） |
| `GET`    | `/v1/fleet/deploy-node/{id}/script` | 一次性下載 deploy script（URL 過期後不可再用） |
| `GET`    | `/v1/fleet/deploy-node/{id}/artifacts` | 取得 bootstrap session 所有 artifacts（Manual Download 模式） |
| `GET`    | `/v1/fleet/deploy-node/bootstrap/{id}/stream` | SSE 串流追蹤 bootstrap 進度（Console 進度條用） |
| `DELETE` | `/v1/fleet/deploy-node/{id}` | 取消 bootstrap session |

---

## 6. Scheduler — `xparse_scheduler/`

GPU resource placement 排程。決定 workload 要放在哪台節點。

### Placement（資源申請）

| Method | Path | 說明 |
|--------|------|------|
| `POST`   | `/scheduler/placements` | 申請 placement（「我要一個有 A100 的節點」），回傳 node_id + workload_id |
| `DELETE` | `/scheduler/placements/{uuid}` | 釋放 placement（workload 完成後呼叫） |
| `POST`   | `/scheduler/placements/{uuid}/restart` | 重新啟動一個 released / stopped placement |

### Capacity（容量查詢）

| Method | Path | 說明 |
|--------|------|------|
| `GET` | `/scheduler/capacity/nodes` | 列出所有節點的容量摘要（可依 tenant 過濾） |
| `GET` | `/scheduler/capacity/groups/{uuid}/usage` | 取得 Group 層級的用量摘要 |
| `GET` | `/scheduler/capacity/tenants/{uuid}/usage` | 取得 Tenant 層級的用量摘要（allocation vs actual） |

### Node Report（Fleet relay）

| Method | Path | 說明 |
|--------|------|------|
| `POST` | `/scheduler/nodes/{node_id}/report` | Fleet 轉發 agentd 心跳，更新節點容量與用量資料 |

---

## 跨服務呼叫圖（一次 `/v1/chat/completions` 的全路徑）

```
Client
  │
  └─ POST /v1/chat/completions  →  Gateway (8000)
                                       │
                                       ├─ POST /iam/internal/gateway-validate  →  IAM (8010)
                                       │    ← tenant_uuid, policy, credential context
                                       │
                                       ├─ POST /resource/endpoints/{id}/acquire  →  ResourceMgr (8020)
                                       │    ← lease_id
                                       │
                                       ├─ HTTP POST  →  AI Provider (OpenAI / Azure / vLLM)
                                       │    ← SSE stream
                                       │
                                       ├─ POST /resource/endpoints/{id}/release  →  ResourceMgr (8020)
                                       │
                                       └─ audit SDK emit (async, in-process)  →  Audit JSONL
```

Gateway 另每 30 秒向 Fleet 拉一次：

```
GET /v1/fleet/model-profiles  →  Fleet (8090)
```
