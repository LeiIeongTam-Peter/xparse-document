# Xparse IAM 服務技術文件

> **服務定位**：IAM（Identity and Access Management）是 Xparse 平台的治理資料平面，負責租戶、群組、應用程式、API 金鑰、供應商認證、策略、部署等核心實體的生命週期管理。Gateway 所有請求均需透過 `POST /iam/internal/gateway-validate` 進行認證解析。

---

## 一、服務端口清單

| 服務名稱 | 端口號碼 | 通訊協定 | 用途說明 |
|---------|---------|---------|---------|
| IAM 主服務（生產） | `8010` | HTTP | IAM API 主入口，Uvicorn ASGI 伺服器 |
| IAM 測試實例（SQLite） | `8011` | HTTP | CI/整合測試環境，SQLite 後端 |
| IAM 測試實例（PostgreSQL） | `8012` | HTTP | CI/整合測試環境，PostgreSQL 後端 |
| PostgreSQL 測試資料庫 | `5433` | TCP | 測試專用 PostgreSQL 實例 |
| Prometheus 指標 | `8010/metrics` | HTTP | 可觀測性指標端點 |

### 相關上游服務端口

| 服務名稱 | 端口號碼 | 環境變數 | 說明 |
|---------|---------|---------|------|
| Scheduler | `8030` | `SCHEDULER_API_URL` | 部署排程與自動配置 |
| Fleet | `8090` | `FLEET_API_URL` | 群組邊車建立、節點管理 |
| Audit | `8020` | `XPARSE_AUDIT_URL` | 審計事件與令牌配額 |
| Gateway（NemoClaw） | — | — | 同一 Docker 網路，內部回環 |

---

## 二、前端 API 清單

> 以下端點由 Console App（`frontend/console-app/`）透過 Bearer Token 呼叫，路徑前綴均為 `/iam/`。

### 2.1 認證與會話

| 方法 | 端點路徑 | 功能說明 |
|------|---------|---------|
| `POST` | `/iam/auth/logout` | 登出目前會話 |
| `GET` | `/iam/auth/verify-session` | 驗證 Console 會話有效性 |
| `GET` | `/iam/auth/resolve-deployment` | 解析部署 URL（自動配置） |
| `GET` | `/iam/oidc/config` | 取得 OIDC 設定（公開，無需認證） |
| `POST` | `/iam/oidc/exchange` | 交換 OIDC ID token 為 IAM 會話金鑰 |

### 2.2 租戶管理

| 方法 | 端點路徑 | 功能說明 |
|------|---------|---------|
| `POST` | `/iam/tenants` | 建立新租戶 |
| `GET` | `/iam/tenants` | 列出所有租戶 |
| `GET` | `/iam/tenants/{tenant_uuid}` | 取得租戶詳情 |
| `PUT` | `/iam/tenants/{tenant_uuid}` | 更新租戶資訊 |
| `PATCH` | `/iam/tenants/{tenant_uuid}/status` | 啟用或停用租戶 |
| `GET` | `/iam/tenants/{tenant_uuid}/settings` | 取得租戶功能設定 |
| `PATCH` | `/iam/tenants/{tenant_uuid}/settings/feature-flags` | 更新功能開關（Feature Flags） |
| `POST` | `/iam/tenants/{tenant_uuid}/keys` | 建立租戶 API 金鑰 |
| `GET` | `/iam/tenants/{tenant_uuid}/keys` | 列出租戶所有金鑰 |
| `POST` | `/iam/tenants/{tenant_uuid}/keys/{tenant_key_uuid}/rotate` | 輪換租戶金鑰 |
| `POST` | `/iam/tenants/{tenant_uuid}/keys/{tenant_key_uuid}/revoke` | 撤銷租戶金鑰 |

### 2.3 群組管理

| 方法 | 端點路徑 | 功能說明 |
|------|---------|---------|
| `POST` | `/iam/groups` | 建立群組 |
| `GET` | `/iam/groups` | 列出群組 |
| `GET` | `/iam/groups/{group_uuid}` | 取得群組詳情 |
| `PUT` | `/iam/groups/{group_uuid}` | 更新群組資訊 |
| `DELETE` | `/iam/groups/{group_uuid}` | 刪除群組 |
| `GET` | `/iam/groups/{group_uuid}/members` | 列出群組成員 |
| `POST` | `/iam/groups/{group_uuid}/members` | 邀請成員加入群組 |
| `PATCH` | `/iam/groups/{group_uuid}/members/{mapping_uuid}` | 更新成員角色 |
| `DELETE` | `/iam/groups/{group_uuid}/members/{mapping_uuid}` | 移除群組成員 |
| `GET` | `/iam/groups/{group_uuid}/candidate-users` | 列出可邀請的候選使用者 |
| `GET` | `/iam/me/invitations` | 取得個人待處理邀請 |
| `GET` | `/iam/groups/{group_uuid}/keys` | 列出群組 API 金鑰 |
| `POST` | `/iam/groups/{group_uuid}/keys` | 建立群組 API 金鑰 |
| `DELETE` | `/iam/groups/{group_uuid}/keys/{group_key_uuid}` | 刪除群組金鑰 |
| `POST` | `/iam/groups/{group_uuid}/api-keys/{group_key_uuid}/rotate` | 輪換群組金鑰 |
| `PUT` | `/iam/groups/{group_uuid}/embedding-profile-config` | 設定群組嵌入設定檔 |
| `PUT` | `/iam/groups/{group_uuid}/default-policies` | 設定群組預設策略 |
| `GET` | `/iam/groups/{group_uuid}/oidc-mappings` | 列出群組 OIDC 對應 |
| `POST` | `/iam/groups/{group_uuid}/oidc-mappings` | 建立群組 OIDC 對應 |
| `DELETE` | `/iam/groups/{group_uuid}/oidc-mappings/{mapping_uuid}` | 刪除 OIDC 對應 |

### 2.4 應用程式管理

| 方法 | 端點路徑 | 功能說明 |
|------|---------|---------|
| `GET` | `/iam/app-types` | 列出支援的應用程式型別 |
| `POST` | `/iam/applications` | 建立應用程式 |
| `GET` | `/iam/applications` | 列出應用程式 |
| `GET` | `/iam/applications/{application_uuid}` | 取得應用程式詳情 |
| `PUT` | `/iam/applications/{application_uuid}` | 更新應用程式 |
| `DELETE` | `/iam/applications/{application_uuid}` | 刪除應用程式 |
| `POST` | `/iam/applications/{application_uuid}/reactivate` | 重新啟用應用程式 |
| `POST` | `/iam/applications/{application_uuid}/terminate` | 終止應用程式 |
| `GET` | `/iam/applications/{application_uuid}/api-keys` | 列出應用程式 API 金鑰 |
| `GET` | `/iam/applications/{application_uuid}/policy-summary` | 取得應用程式策略摘要 |
| `GET` | `/iam/applications/{application_uuid}/deploy-preflight` | 部署前置檢查 |
| `POST` | `/iam/applications/{group_uuid}/applications` | 在指定群組建立應用程式 |

### 2.5 模型管理

| 方法 | 端點路徑 | 功能說明 |
|------|---------|---------|
| `POST` | `/iam/groups/{group_uuid}/models` | 在群組建立模型 |
| `GET` | `/iam/groups/{group_uuid}/models` | 列出群組模型 |
| `POST` | `/iam/models` | 建立模型 |
| `GET` | `/iam/models/{model_uuid}` | 取得模型詳情 |
| `PATCH` | `/iam/models/{model_uuid}` | 更新模型 |
| `DELETE` | `/iam/models/{model_uuid}` | 刪除模型 |
| `POST` | `/iam/models/test-connection` | 測試模型連線 |
| `POST` | `/iam/applications/{app_uuid}/models` | 綁定應用程式與模型 |
| `PATCH` | `/iam/applications/{app_uuid}/models/reorder` | 重新排序應用程式模型優先順序 |
| `PATCH` | `/iam/applications/{app_uuid}/models/{model_uuid}` | 更新應用程式-模型綁定 |
| `DELETE` | `/iam/applications/{app_uuid}/models/{model_uuid}` | 移除應用程式-模型綁定 |
| `GET` | `/iam/model-options` | 取得模型選項參考資料 |

### 2.6 供應商認證

| 方法 | 端點路徑 | 功能說明 |
|------|---------|---------|
| `GET` | `/iam/provider-definitions` | 列出供應商定義 |
| `POST` | `/iam/provider-definitions` | 建立供應商定義 |
| `GET` | `/iam/provider-definitions/{provider_code}` | 取得特定供應商定義 |
| `PUT` | `/iam/provider-definitions/{provider_code}` | 更新供應商定義 |
| `DELETE` | `/iam/provider-definitions/{provider_code}` | 刪除供應商定義 |
| `GET` | `/iam/provider-credentials` | 列出供應商認證 |
| `POST` | `/iam/provider-credentials` | 建立供應商認證 |
| `GET` | `/iam/provider-credentials/{credential_uuid}` | 取得認證詳情 |
| `DELETE` | `/iam/provider-credentials/{credential_uuid}` | 刪除認證 |
| `PUT` | `/iam/provider-credentials/{credential_uuid}/rotate` | 輪換認證金鑰 |
| `PUT` | `/iam/provider-credentials/{credential_uuid}/revoke` | 撤銷認證 |
| `POST` | `/iam/provider-credentials/{credential_uuid}/test` | 測試認證有效性 |
| `GET` | `/iam/applications/{application_uuid}/effective-config` | 取得應用程式有效設定（含繼承） |

### 2.7 策略管理

| 方法 | 端點路徑 | 功能說明 |
|------|---------|---------|
| `GET` | `/iam/rate-limit-policies` | 列出限流策略 |
| `POST` | `/iam/rate-limit-policies` | 建立限流策略 |
| `GET` | `/iam/rate-limit-policies/{policy_uuid}` | 取得限流策略 |
| `PUT` | `/iam/rate-limit-policies/{policy_uuid}` | 更新限流策略 |
| `DELETE` | `/iam/rate-limit-policies/{policy_uuid}` | 刪除限流策略 |
| `GET` | `/iam/guardrail-policies` | 列出護欄策略 |
| `POST` | `/iam/guardrail-policies` | 建立護欄策略 |
| `GET` | `/iam/guardrail-policies/{policy_uuid}` | 取得護欄策略 |
| `PUT` | `/iam/guardrail-policies/{policy_uuid}` | 更新護欄策略 |
| `DELETE` | `/iam/guardrail-policies/{policy_uuid}` | 刪除護欄策略 |
| `PUT` | `/iam/applications/{application_uuid}/rate-limit-policy` | 指派限流策略至應用程式 |
| `PUT` | `/iam/applications/{application_uuid}/guardrail-policy` | 指派護欄策略至應用程式 |
| `GET` | `/iam/policy-bundles` | 列出策略包 |
| `POST` | `/iam/policy-bundles` | 建立策略包 |
| `GET` | `/iam/policy-bundles/{bundle_uuid}` | 取得策略包 |
| `PATCH` | `/iam/policy-bundles/{bundle_uuid}/status` | 更新策略包狀態 |
| `GET` | `/iam/policy-bindings` | 列出策略綁定 |
| `POST` | `/iam/policy-bindings` | 建立策略綁定 |
| `GET` | `/iam/policy-bindings/{binding_uuid}` | 取得策略綁定 |
| `PATCH` | `/iam/policy-bindings/{binding_uuid}/status` | 更新綁定狀態 |

### 2.8 嵌入設定檔

| 方法 | 端點路徑 | 功能說明 |
|------|---------|---------|
| `POST` | `/iam/embedding-profile-configs` | 建立嵌入設定檔 |
| `GET` | `/iam/embedding-profile-configs` | 列出嵌入設定檔 |
| `GET` | `/iam/embedding-profile-configs/by-name/{name}` | 按名稱取得設定檔 |
| `GET` | `/iam/embedding-profile-configs/{profile_config_uuid}` | 取得設定檔詳情 |
| `PUT` | `/iam/embedding-profile-configs/{profile_config_uuid}` | 更新設定檔 |
| `DELETE` | `/iam/embedding-profile-configs/{profile_config_uuid}` | 刪除設定檔 |
| `PUT` | `/iam/applications/{application_uuid}/embedding-profile-config` | 指派設定檔至應用程式 |

### 2.9 部署管理

| 方法 | 端點路徑 | 功能說明 |
|------|---------|---------|
| `POST` | `/iam/applications/{application_uuid}/deployments` | 建立部署 |
| `GET` | `/iam/applications/{application_uuid}/deployments` | 列出應用程式部署 |
| `GET` | `/iam/deployments/{deployment_uuid}` | 取得部署詳情 |
| `PATCH` | `/iam/deployments/{deployment_uuid}` | 更新部署 |
| `POST` | `/iam/deployments/{deployment_uuid}/keys` | 建立部署金鑰 |
| `GET` | `/iam/deployments/{deployment_uuid}/keys` | 列出部署金鑰 |
| `DELETE` | `/iam/deployments/{deployment_uuid}/keys/{key_uuid}` | 刪除部署金鑰 |
| `POST` | `/iam/deployments/{deployment_uuid}/assign-key` | 指派 API 金鑰至部署 |
| `POST` | `/iam/deployments/{deployment_uuid}/unassign-key` | 取消指派 API 金鑰 |
| `GET` | `/iam/deployments/{deployment_uuid}/manifest` | 取得部署清單（YAML/JSON） |
| `GET` | `/iam/user/my-deployments` | 取得個人可見部署（PRD-123） |

### 2.10 資源配額

| 方法 | 端點路徑 | 功能說明 |
|------|---------|---------|
| `POST` | `/iam/tenants/{tenant_uuid}/group-quotas` | 建立群組資源配額 |
| `GET` | `/iam/tenants/{tenant_uuid}/group-quotas` | 列出群組配額 |
| `PUT` | `/iam/tenants/{tenant_uuid}/group-quotas/{quota_uuid}` | 更新群組配額 |
| `GET` | `/iam/tenants/{tenant_uuid}/quota-summary` | 取得租戶配額摘要 |
| `POST` | `/iam/admin/node-allocations` | 建立節點分配 |
| `GET` | `/iam/admin/node-allocations` | 列出節點分配 |
| `PUT` | `/iam/admin/node-allocations/{allocation_uuid}` | 更新節點分配 |
| `DELETE` | `/iam/admin/node-allocations/{allocation_uuid}` | 刪除節點分配 |
| `GET` | `/iam/applications/{application_uuid}/resource-profile` | 取得應用程式資源設定 |
| `PUT` | `/iam/applications/{application_uuid}/resource-profile` | 更新應用程式資源設定 |

### 2.11 插件與技能（Marketplace）

| 方法 | 端點路徑 | 功能說明 |
|------|---------|---------|
| `GET` | `/iam/plugins` | 列出插件（租戶 + 平台） |
| `GET` | `/iam/plugins/{slug}` | 取得插件詳情 |
| `POST` | `/iam/plugins/{slug}/install` | 安裝插件 |
| `GET` | `/iam/plugins/{slug}/versions` | 列出插件版本 |
| `POST` | `/iam/plugins/{slug}/versions` | 發布新插件版本 |
| `GET` | `/iam/plugins/installations` | 列出所有安裝記錄 |
| `DELETE` | `/iam/plugins/installations/{installation_uuid}` | 解除安裝插件 |
| `GET` | `/iam/groups/{group_uuid}/skills` | 列出群組已安裝技能 |
| `POST` | `/iam/groups/{group_uuid}/skills/install` | 安裝技能至群組 |
| `DELETE` | `/iam/groups/{group_uuid}/skills/{installation_uuid}` | 從群組卸載技能 |
| `GET` | `/iam/applications/{application_uuid}/skills` | 列出應用程式已啟用技能 |
| `GET` | `/iam/applications/{application_uuid}/skills/drift` | 取得技能漂移報告 |
| `GET` | `/iam/applications/{application_uuid}/skills/mount-plan` | 取得技能掛載計畫 |
| `PATCH` | `/iam/applications/{application_uuid}/skills/selections` | 更新應用程式技能選擇 |
| `POST` | `/iam/applications/{application_uuid}/skills/reconcile` | 協調技能掛載狀態 |

### 2.12 模型目錄（Catalog）

| 方法 | 端點路徑 | 功能說明 |
|------|---------|---------|
| `POST` | `/iam/catalog/reconcile` | 協調模型目錄（從 Fleet 同步） |
| `GET` | `/iam/catalog/reconcile/status` | 取得目錄協調狀態 |
| `GET` | `/iam/catalog/models` | 列出目錄模型定義 |
| `GET` | `/iam/catalog/models/{name}` | 取得模型定義與所有版本 |
| `GET` | `/iam/catalog/models/{name}/versions/{version}` | 取得特定版本詳情 |
| `POST` | `/iam/catalog/deployments` | 建立目錄部署 |
| `GET` | `/iam/catalog/deployments` | 列出目錄部署 |
| `GET` | `/iam/catalog/deployments/by-alias/{alias}` | 按別名取得部署 |
| `GET` | `/iam/catalog/deployments/{deployment_uuid}` | 取得目錄部署詳情 |
| `PATCH` | `/iam/catalog/deployments/{deployment_uuid}` | 更新目錄部署 |
| `DELETE` | `/iam/catalog/deployments/{deployment_uuid}` | 刪除目錄部署 |
| `POST` | `/iam/applications/{application_uuid}/bind-deployment` | 綁定應用程式至目錄部署 |
| `GET` | `/iam/applications/{application_uuid}/bound-deployments` | 列出應用程式綁定的部署 |
| `POST` | `/iam/models/{model_uuid}/override` | 手動覆蓋模型欄位 |
| `DELETE` | `/iam/models/{model_uuid}/override/{field}` | 移除模型欄位覆蓋 |

### 2.13 LLM 代理（LLM Proxy，PRD-161）

| 方法 | 端點路徑 | 功能說明 |
|------|---------|---------|
| `GET` | `/iam/applications/{app_uuid}/proxies` | 列出應用程式代理 |
| `POST` | `/iam/applications/{app_uuid}/proxies` | 建立代理應用程式 |
| `GET` | `/iam/applications/{proxy_uuid}/model-sources` | 列出代理模型來源 |
| `POST` | `/iam/applications/{proxy_uuid}/model-sources` | 新增模型來源至代理 |
| `PATCH` | `/iam/applications/{app_uuid}/proxies/active` | 切換主動代理 |

### 2.14 OIDC 使用者對應（管理員）

| 方法 | 端點路徑 | 功能說明 |
|------|---------|---------|
| `GET` | `/iam/oidc/user-mappings` | 列出所有 OIDC 使用者對應 |
| `POST` | `/iam/oidc/user-mappings` | 建立 OIDC 使用者對應 |
| `GET` | `/iam/oidc/user-mappings/{mapping_uuid}` | 取得特定對應 |
| `PUT` | `/iam/oidc/user-mappings/{mapping_uuid}` | 更新對應 |
| `DELETE` | `/iam/oidc/user-mappings/{mapping_uuid}` | 刪除對應 |
| `POST` | `/iam/oidc/user-mappings/{mapping_uuid}/emergency-unlock` | 緊急解鎖帳號 |
| `POST` | `/iam/oidc/user-mappings/{mapping_uuid}/reactivate` | 重新啟用帳號 |
| `GET` | `/iam/oidc/tenant-group-bindings` | 列出租戶-群組綁定 |
| `POST` | `/iam/oidc/tenant-group-bindings` | 建立租戶-群組綁定 |
| `GET` | `/iam/oidc/tenant-group-bindings/{binding_uuid}` | 取得綁定詳情 |
| `DELETE` | `/iam/oidc/tenant-group-bindings/{binding_uuid}` | 刪除租戶-群組綁定 |

### 2.15 控制檯能力與初始化

| 方法 | 端點路徑 | 功能說明 |
|------|---------|---------|
| `GET` | `/iam/console/capabilities` | 取得目前帳號可用功能列表 |
| `GET` | `/iam/console/edition` | 取得部署版本（basic / pro / enterprise） |
| `POST` | `/iam/bootstrap` | 一次性系統初始化（無需認證） |
| `GET` | `/health` | 健康檢查（無需認證） |

---

## 三、後端 API 清單

> 以下端點由後端服務對後端服務（B2B）呼叫，或由排程任務觸發，不開放給前端直接存取。

### 3.1 閘道驗證（Gateway Internal）

| 方法 | 端點路徑 | 所屬服務 | 功能說明 | 呼叫來源 |
|------|---------|---------|---------|---------|
| `POST` | `/iam/auth/validate` | IAM | 驗證 API 金鑰（公開內部驗證） | Gateway / 其他後端 |
| `POST` | `/iam/derive` | IAM | 衍生新 API 金鑰（受限範圍） | Gateway |
| `POST` | `/iam/internal/gateway-validate` | IAM | 閘道完整驗證：含認證解密，回傳解密後 `resolved_api_key` | Gateway（NemoClaw） |

### 3.2 排程器內部端點（Scheduler Internal）

| 方法 | 端點路徑 | 所屬服務 | 功能說明 | 呼叫來源 |
|------|---------|---------|---------|---------|
| `GET` | `/iam/internal/node-allocations` | IAM | 取得租戶的節點分配清單 | Scheduler |
| `GET` | `/iam/internal/group-quotas/{group_uuid}` | IAM | 取得群組資源配額 | Scheduler |
| `GET` | `/iam/internal/resource-profiles/{application_uuid}` | IAM | 取得應用程式資源設定 | Scheduler |
| `GET` | `/iam/internal/deployment-count/{application_uuid}` | IAM | 取得應用程式活躍部署數量 | Scheduler |

### 3.3 供應商認證解析（Agentd Internal）

| 方法 | 端點路徑 | 所屬服務 | 功能說明 | 呼叫來源 |
|------|---------|---------|---------|---------|
| `POST` | `/iam/internal/resolve-provider-credential` | IAM | 解析供應商認證，回傳解密後令牌 | xparse_node_mgr（agentd） |

### 3.4 Fleet 運行時事件（Fleet Runtime）

| 方法 | 端點路徑 | 所屬服務 | 功能說明 | 呼叫來源 |
|------|---------|---------|---------|---------|
| `POST` | `/iam/fleet-runtime/deployments/{deployment_uuid}/events` | IAM | 記錄部署階段事件（deployed / failed / pending） | Fleet 節點代理 |
| `GET` | `/iam/fleet-runtime/deployments/{deployment_uuid}` | IAM | 取得部署運行狀態 | Fleet / Console |
| `GET` | `/iam/fleet-runtime/deployments/{deployment_uuid}/events` | IAM | 取得部署事件時間軸 | Fleet / Console |

### 3.5 節點啟用碼（Node Activation）

| 方法 | 端點路徑 | 所屬服務 | 功能說明 | 呼叫來源 |
|------|---------|---------|---------|---------|
| `POST` | `/iam/node-activations` | IAM | 發行節點啟用碼 | 管理員 / Console |
| `POST` | `/iam/node-activations/validate` | IAM | 驗證啟用碼（不消費） | xparse_node_mgr（agentd） |
| `POST` | `/iam/node-activations/consume` | IAM | 消費啟用碼並完成節點綁定 | xparse_node_mgr（agentd） |

### 3.6 Responses 綁定（Gateway 邊界）

| 方法 | 端點路徑 | 所屬服務 | 功能說明 | 呼叫來源 |
|------|---------|---------|---------|---------|
| `POST` | `/iam/responses-binding` | IAM | 建立 Responses API 會話綁定 | Gateway |
| `GET` | `/iam/responses-binding/lookup` | IAM | 查詢綁定狀態與關聯資訊 | Gateway |
| `PATCH` | `/iam/responses-binding/{binding_uuid}/delete` | IAM | 標記綁定為已刪除 | Gateway |

### 3.7 指標端點

| 方法 | 端點路徑 | 所屬服務 | 功能說明 | 呼叫來源 |
|------|---------|---------|---------|---------|
| `GET` | `/metrics` | IAM | Prometheus 格式指標資料 | Prometheus / 監控系統 |

---

## 四、工作流程

### 4.1 使用者以 API 金鑰發送請求（主要請求路徑）

**流程名稱**：Gateway API Key 驗證與授權

**發起方**：外部用戶端（Client）

```
Client
  │
  │  POST /v1/chat/completions
  │  Authorization: Bearer <api_key>
  ▼
Gateway (NemoClaw / bustream)
  │
  │  POST /iam/internal/gateway-validate
  │  body: { api_key, request_context }
  ▼
IAM
  │  1. 查找 APIKey 表，驗證金鑰有效性
  │  2. 解析關聯的 Application / Group / Tenant
  │  3. 使用 KEK 解密 credential_material → resolved_api_key
  │  4. 回傳認證上下文（tenant_uuid, group_uuid, application_uuid,
  │     rate_limit_policy, guardrail_policy, routing_strategy）
  ▼
Gateway
  │  5. 套用策略核心（Policy Kernel，純函數決策）
  │  6. Admission 控制（Rate Limit 檢查）
  │  7. 解析路由策略 → 目標供應商端點
  │  8. 以 resolved_api_key 轉發至 Provider
  ▼
Provider（OpenAI / Azure / vLLM）
  │
  │  回應串流
  ▼
Gateway → StreamingManager → SSE → Client
```

**回應路徑**：Provider → Gateway SSE 管道 → Client

---

### 4.2 OIDC SSO 登入流程

**流程名稱**：OIDC ID Token 交換為 IAM 會話

**發起方**：Console App（使用者）

```
使用者
  │
  │  點擊 SSO 登入
  ▼
Console App
  │
  │  GET /iam/oidc/config  →  取得 OIDC 設定（issuer, client_id）
  ▼
IAM
  │  回傳 { issuer, client_id, enabled }
  ▼
Console App
  │  重導至 Keycloak 授權端點
  ▼
Keycloak（OIDC Provider）
  │  使用者完成認證
  │  回傳 Authorization Code
  ▼
Console App
  │
  │  POST /iam/oidc/exchange
  │  body: { id_token }
  ▼
IAM
  │  1. 向 XPARSE_OIDC_JWKS_URL 驗證 JWT 簽章
  │  2. 解析 claims（sub, email, tenant_claim）
  │  3. 查找或建立 OIDCUserMapping 記錄
  │  4. 若啟用 XPARSE_OIDC_AUTO_PROVISION → 建立租戶
  │  5. 建立 IAM session key（有效期 XPARSE_IDENTITY_COOKIE_TTL）
  │  6. 回傳 { session_key, tenant_uuid, group_uuid, roles }
  ▼
Console App
  │  儲存 session_key，後續請求帶入 Authorization: Bearer
  ▼
使用者完成登入
```

---

### 4.3 建立部署流程

**流程名稱**：應用程式部署建立與排程

**發起方**：Console App（管理員）

```
Console App
  │
  │  [前置] GET /iam/applications/{app_uuid}/deploy-preflight
  │         驗證：模型綁定、策略、資源配額、群組配額是否充足
  ▼
IAM
  │  回傳 preflight 結果 + 警告項目
  ▼
Console App
  │
  │  POST /iam/applications/{application_uuid}/deployments
  │  body: { target_group, resource_profile, ... }
  ▼
IAM
  │  1. 驗證群組資源配額（GroupQuota）不超限
  │  2. 原子寫入：建立 Deployment 記錄（state = PENDING）
  │  3. 呼叫 Scheduler API
  │     POST http://xparse-scheduler:8030/scheduler/placements
  │     body: { deployment_uuid, resource_profile, group_uuid }
  ▼
Scheduler
  │  4. 分析節點可用性（NodeAllocation）
  │  5. 回傳 placement 結果（node, endpoint）
  ▼
IAM
  │  6. 更新 Deployment 記錄（state = SCHEDULED, node 資訊）
  │  7. 回傳部署詳情給 Console
  ▼
Console App
  │  顯示部署進度
  │
  │  [後續] Fleet 節點代理開始拉取映像檔，部署完成後：
  │  POST /iam/fleet-runtime/deployments/{deployment_uuid}/events
  │  body: { phase: "deployed" }
  ▼
IAM
  │  更新 Deployment state → RUNNING
  ▼
Console App
  │  GET /iam/fleet-runtime/deployments/{deployment_uuid}
  │  顯示 RUNNING 狀態
```

---

### 4.4 節點啟用（Node Activation）流程

**流程名稱**：GPU 節點三步驗證啟用（PRD-131）

**發起方**：管理員 / xparse_node_mgr（agentd）

```
管理員（Console App）
  │
  │  POST /iam/node-activations
  │  body: { group_uuid, node_alias, ttl_seconds }
  ▼
IAM
  │  1. 生成一次性啟用碼（NodeActivationCode），設定 TTL
  │  2. 回傳 { activation_code, expires_at }
  ▼
管理員
  │  將啟用碼傳遞給節點端（例如：貼入安裝腳本）
  │
  │
節點（agentd / xparse_node_mgr）
  │
  │  POST /iam/node-activations/validate
  │  body: { activation_code }
  ▼
IAM
  │  3. 驗證碼有效性（是否過期、是否已消費）
  │  4. 回傳驗證結果（不改變狀態）
  ▼
節點
  │
  │  POST /iam/node-activations/consume
  │  body: { activation_code, node_metadata }
  ▼
IAM
  │  5. 原子消費：標記啟用碼為 USED
  │  6. 建立 Node 記錄，綁定至對應群組
  │  7. 回傳節點憑證（node_key）
  ▼
節點
  │  使用 node_key 與平台後續通訊
```

---

### 4.5 供應商認證解析流程（Agentd）

**流程名稱**：Container 內代理解析供應商令牌

**發起方**：xparse_node_mgr（agentd）

```
Container（Agent App 內部）
  │
  │  POST /iam/internal/resolve-provider-credential
  │  body: { credential_uuid, application_uuid }
  │  （依賴 Docker 網路信任，無 API 金鑰）
  ▼
IAM
  │  1. 查找 ProviderCredential 記錄
  │  2. 使用 XPARSE_KEK（金鑰加密金鑰）解密 credential_material
  │  3. 回傳明文供應商令牌 { resolved_key, provider_code, endpoint }
  ▼
Agentd
  │  使用明文令牌直接呼叫供應商 API
```

---

### 4.6 模型目錄協調流程（Catalog Reconcile）

**流程名稱**：Fleet 模型定義同步至 IAM

**發起方**：排程任務 / Console App（管理員）

```
管理員（或定時任務）
  │
  │  POST /iam/catalog/reconcile
  ▼
IAM
  │  1. 呼叫 Fleet API（FLEET_API_URL）
  │     GET /v1/fleet/config/models
  │     取得 models.yaml 定義
  ▼
Fleet 服務
  │  回傳模型定義清單（名稱、版本、硬體需求）
  ▼
IAM
  │  2. 比對現有 ModelDefinition 記錄
  │  3. 新增 / 更新 / 標記棄用
  │  4. 回傳協調摘要 { added, updated, deprecated }
  ▼
管理員
  │
  │  GET /iam/catalog/reconcile/status  （輪詢協調狀態）
  │
  │  [後續] 對目錄模型建立部署：
  │  POST /iam/catalog/deployments
  │  body: { model_name, version, group_uuid, resource_profile }
  ▼
IAM → Scheduler → Fleet
  │  執行與 §4.3 相同的部署排程流程
```

---

### 4.7 群組邊車延遲建立流程（ADR-141）

**流程名稱**：首次存取時建立群組 Sidecar Proxy

**發起方**：IAM 內部（由 `resolve_deployment` 觸發）

```
Console App 或 Gateway
  │
  │  GET /iam/auth/resolve-deployment
  │  body: { deployment_uuid, group_uuid }
  ▼
IAM
  │  1. 查找 GroupSidecar 表
  │
  │  [若 GroupSidecar 不存在] ─────────────────────
  │                                                 │
  │  2. 呼叫 Fleet API                              │
  │     POST http://xparse-fleet:8090/v1/fleet/     │
  │          group-sidecars                         │
  │     body: { group_uuid, sidecar_spec }          │
  │                                    ▼            │
  │                               Fleet 服務        │
  │                                    │            │
  │                              建立 Sidecar       │
  │                              容器與 nginx       │
  │                                    │            │
  │  3. 輪詢直到 Sidecar READY ◄───────┘            │
  │  4. 寫入 GroupSidecar 記錄（含 endpoint）       │
  │  ──────────────────────────────────────────────
  │
  │  [若 GroupSidecar 存在] 直接取得 endpoint
  │
  │  5. 回傳 { sidecar_endpoint, deployment_url }
  ▼
Console App / Gateway
  │  使用 sidecar_endpoint 路由後續請求
```

---

## 附錄：認證機制摘要

### A.1 API 金鑰認證

所有受保護端點均使用 Bearer Token：

```
Authorization: Bearer <api_key>
```

金鑰型別：
- `tenant_key`：租戶層級，管理操作
- `group_key`：群組層級，群組內管理
- `application_key`：應用程式層級，AI 請求
- `deployment_key`：部署層級，特定部署使用

### A.2 無需認證的端點

| 端點 | 說明 |
|------|------|
| `GET /health` | 健康檢查 |
| `GET /iam/oidc/config` | OIDC 設定查詢 |
| `POST /iam/oidc/exchange` | OIDC token 交換 |
| `POST /iam/bootstrap` | 一次性初始化 |

### A.3 內部端點（網路信任）

`/iam/internal/*` 端點不驗證 API 金鑰，依賴 Docker 網路邊界隔離（僅限同一 Docker 網路內呼叫）。

### A.4 關鍵環境變數

| 環境變數 | 預設值 | 說明 |
|---------|-------|------|
| `XPARSE_MASTER_SECRET` | — | 主加密金鑰 |
| `XPARSE_KEK` | — | 金鑰加密金鑰（供應商認證加解密） |
| `XPARSE_EDITION` | `basic` | 部署版本：basic / pro / enterprise |
| `XPARSE_OIDC_ENABLED` | `false` | 是否啟用 SSO |
| `XPARSE_OIDC_ISSUER` | — | Keycloak 發行者 URL |
| `SCHEDULER_API_URL` | `http://xparse-scheduler:8030` | Scheduler 服務位址 |
| `FLEET_API_URL` | `http://xparse-fleet:8090` | Fleet 服務位址 |
| `XPARSE_AUDIT_URL` | `http://localhost:8020` | Audit 服務位址 |
| `XPARSE_IAM_DB_ENGINE` | `sqlite` | 資料庫引擎：sqlite / postgres |
