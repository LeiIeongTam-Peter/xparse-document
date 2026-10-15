# xparse_iam — 系統分析報告

> **文件版本**：2026-05-29
> **分析對象**：`/xparse/xparse_iam/`
> **定位**：Xparse 平台的身分驗證與授權中心（Governance / Control Plane）

---

## 1. 是什麼應用？

`xparse_iam` 是 Xparse 平台的 **Governance / Control Plane 核心**，一個 **Django + Django Ninja-based REST API 服務**。

- **類型**：後端微服務（Identity & Access Management）
- **協議**：REST（Django Ninja / FastAPI 風格）
- **面向**：同時服務 **前端應用程式**（Console App）、**其他後端服務**（Gateway/bustream、Scheduler、Fleet）
- **不包含**：無 HTML/CSS/JS UI，非串流服務，不直接暴露給終端用戶（End User）
- **部署方式**：Docker 容器，監聽預設 Port（Gunicorn / Uvicorn），搭配 SQLite 或 PostgreSQL

**在 Xparse 四平面架構中的位置：**

```
Runtime Plane       → bustream（Gateway）
Governance Plane    → xparse_iam ★（本服務）+ frontend/console-app
Capacity Plane      → xparse_resource_manager
Agent Platform Plane→ xparse_container_platform + xparse_node_mgr
```

---

## 2. 資料夾結構總覽

```
xparse_iam/                         # Django 專案根目錄
├── manage.py                       # Django 管理命令進入點
├── README.md                       # 專案說明
├── docker-compose.test-db.yml      # 測試資料庫 Docker 設定
└── xparse_iam/                     # 主套件
    ├── __init__.py
    ├── admin.py                    # Django Admin 設定
    ├── apps.py                     # App 設定（啟動驗證 ADR-039）
    ├── asgi.py                     # ASGI 進入點
    ├── wsgi.py                     # WSGI 進入點
    ├── client.py                   # IAMClient（供 bustream direct mode 使用）
    ├── settings.py                 # Django 設定（700+ LOC）
    ├── models.py                   # Model re-export hub
    ├── urls.py                     # URL 路由入口
    │
    ├── api/                        # API 層（~18,718 LOC）
    │   ├── authentication.py       # Bearer token 認證 decorator / helper
    │   ├── console_capabilities.py # Console 功能權限解析
    │   ├── console_edition.py      # Edition / tier 識別（Basic / Pro / Enterprise）
    │   ├── oidc_audit.py           # OIDC 鑑識日誌
    │   ├── permissions.py          # 權限工具函式
    │   ├── plugin_schemas.py       # Plugin API Schema
    │   ├── quota_audit.py          # 配額審計日誌
    │   ├── quota_schemas.py        # 配額 API Schema
    │   ├── rate_limit.py           # 限速強制執行
    │   ├── skill_schemas.py        # Skill API Schema
    │   ├── schemas/                # Request / Response Pydantic Schema
    │   │   ├── _application.py     # Application 相關 Schema
    │   │   ├── _core.py            # 通用 Schema
    │   │   ├── _group.py           # Group 相關 Schema
    │   │   ├── _policy.py          # Policy 相關 Schema
    │   │   └── __init__.py
    │   └── ninja_api/              # Django Ninja 路由模組
    │       ├── __init__.py         # API 初始化與路由註冊
    │       ├── _app_auth.py        # API Key 驗證、衍生、Session
    │       ├── _applications.py    # Application CRUD
    │       ├── _bootstrap.py       # Bootstrap 初始化 + 連線測試
    │       ├── _catalog.py         # 模型 / Deployment Catalog、Binding
    │       ├── _common.py          # 共用認證 helper
    │       ├── _deployments.py     # Deployment 管理（呼叫 Scheduler）
    │       ├── _fleet.py           # Fleet 查詢
    │       ├── _group_sidecar.py   # Group Sidecar 建立（呼叫 Fleet）
    │       ├── _groups.py          # Group CRUD（PRD-057）
    │       ├── _helpers.py         # Fleet 整合 + Provider 連線測試
    │       ├── _internal.py        # ★ 內部端點（Gateway / Scheduler 專用）
    │       ├── _models.py          # Model 管理
    │       ├── _oidc.py            # OIDC 設定 + Token Exchange + Mapping 管理
    │       ├── _policy.py          # Policy 管理（Rate Limit, Guardrail）
    │       ├── _provider_credentials.py  # Provider Credential CRUD
    │       ├── _roles.py           # Role 管理（PRD-071）
    │       ├── _skills.py          # Skill 管理（PRD-091）
    │       ├── _tenants.py         # Tenant 管理
    │       └── _users.py           # User 管理
    │
    ├── application/
    │   └── use_cases/              # Business Logic Use Cases
    │       ├── application/
    │       │   └── trigger_deployment.py   # 觸發 Container 部署
    │       └── ...
    │
    ├── core/                       # 核心引擎
    │   ├── auth_engine.py          # ★ API Key 解析與驗證引擎（ADR-023）
    │   ├── crypto.py               # 加密 / 解密（Master Secret + KEK）
    │   ├── key_hash.py             # SHA-256 Key 雜湊
    │   └── oidc.py                 # OIDC Token 驗證 + JWKS 快取
    │
    ├── domain/
    │   └── value_objects/          # Enum、Domain 型別
    │
    ├── db/                         # Django Models + 資料庫抽象
    │   └── models/                 # 所有 ORM Model 定義
    │
    └── migrations/                 # Django Migrations（0001–0037+）
```

---

## 3. 各模組功能說明

| 模組 | 功能 | 關聯文件 |
|------|------|---------|
| `api/ninja_api/_internal.py` | ★ 內部專用端點：Gateway 驗證、Scheduler 查詢資源配額 | ADR-023, ADR-039 |
| `api/ninja_api/_oidc.py` | OIDC 設定查詢、ID Token Exchange、User Mapping CRUD | PRD-075, ADR-174 |
| `api/ninja_api/_bootstrap.py` | 一次性初始化（建立 Tenant + API Key）、Provider 連線測試 | — |
| `api/ninja_api/_applications.py` | Application CRUD（建立、查詢、更新、刪除） | PRD-081, PRD-082 |
| `api/ninja_api/_deployments.py` | Deployment 管理，呼叫 Scheduler 進行 Container 部署 | ADR-121, PRD-082 |
| `api/ninja_api/_groups.py` | Group CRUD，含 Developer Role 管理 | PRD-057, PRD-071 |
| `api/ninja_api/_group_sidecar.py` | Group Sidecar Proxy 建立，呼叫 Fleet 命令佇列 | ADR-136 |
| `api/ninja_api/_catalog.py` | 模型 Catalog 與 Application Binding 管理 | ADR-089, ADR-138 |
| `api/ninja_api/_policy.py` | Rate Limit Policy、Guardrail Policy CRUD | PRD-033 |
| `api/ninja_api/_provider_credentials.py` | Provider Credential 加密儲存與 BYOK 管理 | ADR-057 |
| `api/ninja_api/_helpers.py` | Fleet 整合（endpoint 解析）+ Provider 連線測試邏輯 | ADR-129 |
| `api/ninja_api/_fleet.py` | Fleet 節點狀態查詢 | PRD-062 |
| `api/ninja_api/_skills.py` | Skill 管理 | PRD-091-01 |
| `api/authentication.py` | Ninja Bearer token 認證 decorator，呼叫 `auth_engine` | ADR-018, ADR-074 |
| `api/console_capabilities.py` | 依 Edition + Role 解析 Console 可用功能 | PRD-130 |
| `api/permissions.py` | Scope 比對與 RBAC 工具函式 | PRD-059, PRD-060 |
| `core/auth_engine.py` | ★ API Key 三層查找（TenantKey → GroupKey → AppKey），SHA-256 比對 | ADR-023 |
| `core/oidc.py` | OIDC ID Token RS256 驗證，JWKS 1 小時 TTL 快取 | PRD-075 |
| `core/crypto.py` | Master Secret + KEK 加密 / 解密 Provider Credential | — |
| `core/key_hash.py` | SHA-256 單向雜湊，原文不入庫 | — |
| `db/models/` | Django ORM 全部 Model 定義 | — |
| `settings.py` | Django 設定：DB、Middleware、Crypto Key、OIDC、Edition | — |

---

## 4. 對外 API 端點完整列表

### 4.1 內部端點（僅供後端服務使用，無認證，網路層信任）

| 方法 | 路徑 | 說明 | 呼叫方 |
|------|------|------|-------|
| `POST` | `/iam/internal/gateway-validate` | API Key 驗證 + 解密 Provider Credential | Gateway（bustream） |
| `POST` | `/iam/internal/resolve-provider-credential` | 依 Provider Code 取得明文 Token | agentd（Artifact Store） |
| `GET` | `/iam/internal/node-allocations` | 查詢租戶 GPU Node 配置清單 | Scheduler |
| `GET` | `/iam/internal/group-quotas/{group_uuid}` | 查詢 Group 資源配額 | Scheduler |
| `GET` | `/iam/internal/resource-profiles/{application_uuid}` | 查詢 Application 資源需求 | Scheduler |
| `GET` | `/iam/internal/deployment-count/{application_uuid}` | 查詢 Deployment 數量（PRD-113 INV-113-5） | Scheduler |

---

### 4.2 Bootstrap（初始化，無認證）

| 方法 | 路徑 | 說明 |
|------|------|------|
| `POST` | `/iam/bootstrap` | 一次性系統初始化，建立第一個 Tenant + API Key |
| `POST` | `/iam/models/test-connection` | 測試 Provider API Key 連線（需 Bearer） |

**Bootstrap Response：**
```json
{
  "tenant_uuid": "...",
  "tenant_code": "default",
  "application_uuid": "...",
  "api_key": "xp_live_...",
  "message": "Bootstrap complete. Save your API key now."
}
```

---

### 4.3 OIDC（Console SSO，部分無認證）

| 方法 | 路徑 | 認證 | 說明 |
|------|------|------|------|
| `GET` | `/iam/oidc/config` | 無 | 取得 OIDC 設定（issuer, client_id, enabled） |
| `POST` | `/iam/oidc/exchange` | 無 | 用 Keycloak ID Token 換取 Session Key |
| `GET` | `/iam/oidc/user-mappings` | Bearer | 列出 OIDC User Mapping |
| `POST` | `/iam/oidc/user-mappings` | Bearer | 建立 OIDC User Mapping |
| `PATCH` | `/iam/oidc/user-mappings/{uuid}` | Bearer | 更新 OIDC User Mapping |

**OIDC Exchange Request：**
```json
{ "id_token": "<JWT from Keycloak>" }
```

**OIDC Exchange Response：**
```json
{
  "session_key": "xp_live_...",
  "tenant_uuid": "...",
  "tenant_code": "acme",
  "display_name": "Alice"
}
```

---

### 4.4 Tenant 管理（需 Bearer）

| 方法 | 路徑 | 說明 |
|------|------|------|
| `GET` | `/iam/tenants` | 列出 Tenant |
| `POST` | `/iam/tenants` | 建立 Tenant |
| `GET` | `/iam/tenants/{uuid}` | 取得 Tenant 詳細 |
| `PATCH` | `/iam/tenants/{uuid}` | 更新 Tenant |
| `DELETE` | `/iam/tenants/{uuid}` | 刪除 Tenant |

---

### 4.5 API Key 管理（需 Bearer）

| 方法 | 路徑 | 說明 |
|------|------|------|
| `GET` | `/iam/api-keys` | 列出 API Keys（不含原文） |
| `POST` | `/iam/api-keys` | 建立新 API Key |
| `POST` | `/iam/api-keys/{uuid}/revoke` | 撤銷 API Key |
| `POST` | `/iam/api-keys/derive` | 衍生 Application-scoped Key |
| `POST` | `/iam/api-keys/validate` | 驗證 API Key（Console 用） |

---

### 4.6 Application 管理（需 Bearer）

| 方法 | 路徑 | 說明 |
|------|------|------|
| `GET` | `/iam/applications` | 列出 Applications |
| `POST` | `/iam/applications` | 建立 Application（PRD-081） |
| `GET` | `/iam/applications/{uuid}` | 取得 Application 詳細 |
| `PATCH` | `/iam/applications/{uuid}` | 更新 Application |
| `DELETE` | `/iam/applications/{uuid}` | 刪除 Application |
| `POST` | `/iam/applications/{uuid}/deploy` | 觸發 Container 部署（呼叫 Scheduler） |

---

### 4.7 Group 管理（需 Bearer，PRD-057）

| 方法 | 路徑 | 說明 |
|------|------|------|
| `GET` | `/iam/groups` | 列出 Groups |
| `POST` | `/iam/groups` | 建立 Group |
| `GET` | `/iam/groups/{uuid}` | 取得 Group 詳細 |
| `PATCH` | `/iam/groups/{uuid}` | 更新 Group |
| `DELETE` | `/iam/groups/{uuid}` | 刪除 Group |
| `POST` | `/iam/groups/{uuid}/sidecar` | 建立 Group Sidecar Proxy（呼叫 Fleet） |

---

### 4.8 Model / Catalog 管理（需 Bearer）

| 方法 | 路徑 | 說明 |
|------|------|------|
| `GET` | `/iam/models` | 列出可用模型 |
| `POST` | `/iam/models` | 新增模型 |
| `POST` | `/iam/models/{uuid}/bind` | 綁定模型至 Application |
| `DELETE` | `/iam/models/{uuid}/bind` | 解除綁定 |
| `GET` | `/iam/catalog` | 系統 Model Catalog |
| `POST` | `/iam/catalog/binding` | 建立 Catalog Binding |

---

### 4.9 Policy 管理（需 Bearer）

| 方法 | 路徑 | 說明 |
|------|------|------|
| `GET` | `/iam/policies/rate-limit` | 列出 Rate Limit Policy |
| `POST` | `/iam/policies/rate-limit` | 建立 Rate Limit Policy |
| `PATCH` | `/iam/policies/rate-limit/{uuid}` | 更新 Rate Limit Policy |
| `GET` | `/iam/policies/guardrail` | 列出 Guardrail Policy |
| `POST` | `/iam/policies/guardrail` | 建立 Guardrail Policy |

---

### 4.10 Provider Credential（需 Bearer）

| 方法 | 路徑 | 說明 |
|------|------|------|
| `GET` | `/iam/provider-credentials` | 列出 Provider Credentials（不含原文） |
| `POST` | `/iam/provider-credentials` | 建立並加密儲存 Provider Credential |
| `PATCH` | `/iam/provider-credentials/{uuid}` | 更新 Credential |
| `DELETE` | `/iam/provider-credentials/{uuid}` | 刪除 Credential |

---

### 4.11 Health

| 方法 | 路徑 | 說明 |
|------|------|------|
| `GET` | `/iam/health` | 服務健康狀態 |

---

## 5. 服務通訊全貌

### 5.0 通訊架構一覽圖

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                       FRONTEND (Console App)                                 │
│                  frontend/console-app/  (:3000)                              │
│                                                                              │
│  GET /iam/oidc/config      POST /iam/oidc/exchange                           │
│  POST /iam/applications    POST /iam/groups    GET /iam/models               │
│  POST /iam/api-keys        POST /iam/bootstrap  POST /iam/models/test-conn   │
└─────────────────────────────┬────────────────────────────────────────────────┘
                              │  HTTP REST  (Bearer token / anonymous)
                              │  Authorization: Bearer <session_key | api_key>
                              ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                        xparse_iam  (:8010)                                   │
│             [Django Ninja API + Auth Engine + OIDC + Crypto]                 │
└──┬──────────────┬──────────────┬──────────────┬──────────────┬──────────────┘
   │              │              │              │              │
   │ (← 呼叫方)  │ HTTP GET     │ HTTP POST    │ HTTP GET/POST│ HTTP GET/POST
   │ POST /iam/  │ {JWKS_URL}  │ /scheduler/  │ /fleet/      │ Provider APIs
   │ internal/   │ (OIDC驗證)  │ placements   │ apps/{code}/ │ (連線測試用)
   │ gateway-    │              │              │ endpoint     │
   │ validate    │              │              │              │
   ▼              ▼              ▼              ▼              ▼
┌────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐
│Gateway │  │Keycloak  │  │Scheduler │  │  Fleet   │  │ Provider APIs    │
│bustream│  │(OIDC IdP)│  │ :8030    │  │  :8800   │  │ OpenAI / Azure / │
│ :8000  │  │          │  │          │  │          │  │ Anthropic / vLLM │
└────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘
   ↑
   │  (← 呼叫方)
   │  POST /iam/internal/gateway-validate
   │  + 回傳明文 Provider Key
   │
┌──────────┐
│Scheduler │  ← GET /iam/internal/node-allocations
│          │  ← GET /iam/internal/group-quotas/{uuid}
│          │  ← GET /iam/internal/resource-profiles/{uuid}
│          │  ← GET /iam/internal/deployment-count/{uuid}
└──────────┘
```

---

### 5.1 通訊連結總表

| 對象 | 類型 | 協議 | 方向 | 發起點檔案 | 失敗行為 |
|------|------|------|------|-----------|---------|
| **Console App（前端）** | Frontend | HTTP REST | Console → IAM | `api/ninja_api/` 各 router | HTTP 4xx/5xx，JSON 錯誤格式 |
| **Gateway（bustream）** | Backend（呼叫方） | HTTP POST | Gateway → IAM | `bustream/gateway/iam_http_client.py` | IAM 回 500 → Gateway fail-fast |
| **Keycloak** | External IdP | HTTP GET (JWKS) | IAM → Keycloak | `core/oidc.py` | Token 驗證失敗 → 403 |
| **Scheduler** | Backend（呼叫方） | HTTP GET | Scheduler → IAM | `api/ninja_api/_internal.py` | 404/500 回給 Scheduler |
| **Scheduler**（部署） | Backend | HTTP POST | IAM → Scheduler | `api/ninja_api/_deployments.py` | 503 hard fail（ADR-121） |
| **Fleet**（查詢） | Backend | HTTP GET | IAM → Fleet | `api/ninja_api/_helpers.py` | Fail-open（回空清單） |
| **Fleet**（命令） | Backend | HTTP POST | IAM → Fleet | `api/ninja_api/_group_sidecar.py` | 錯誤向上傳遞 |
| **Provider APIs** | External | HTTP GET/POST | IAM → Provider | `api/ninja_api/_helpers.py` | 回傳連線失敗訊息給 Console |
| **agentd**（Artifact） | Backend（呼叫方） | HTTP POST | agentd → IAM | `api/ninja_api/_internal.py` | 404 Provider 未設定 |

---

### 5.2 Gateway（bustream）↔ IAM

**類型：Backend → Backend（最關鍵連線）**

Gateway 在每個請求進入時必須先向 IAM 驗證 API Key，取得完整的 `AuthContext`（含解密後的 Provider Key）。

#### 端點 1：`/iam/internal/gateway-validate`

```
Gateway  →  POST /iam/internal/gateway-validate
            Base URL: ${GATEWAY_IAM_URL}  (預設: http://localhost:8010)
            Header:   X-Gateway-Secret: ${XPARSE_GATEWAY_IAM_SECRET}  (選用)
            Timeout:  ${GATEWAY_IAM_TIMEOUT}  (預設: 10s)
```

**Request：**
```json
{ "api_key": "xp_live_abc123..." }
```

**Response（200 OK）：**
```json
{
  "valid": true,
  "tenant_uuid": "550e8400-...",
  "tenant_code": "acme",
  "application_uuid": "660e8400-...",
  "application_code": "my-app",
  "routing_strategy": "performance",
  "system_role": "tenant_admin",
  "actor_type": "application",
  "actor_id": "660e8400-...",
  "models": [
    {
      "model_uuid": "...",
      "provider": "openai",
      "model_name": "gpt-4o",
      "endpoint": "https://api.openai.com/v1",
      "resolved_api_key": "sk-..."
    }
  ],
  "rate_limit_policy": {
    "req_per_sec": 10,
    "burst": 20,
    "max_concurrency": 5,
    "max_queue_depth": 50,
    "queue_timeout_sec": 30
  },
  "guardrail_policy": {
    "content_filter_level": "medium",
    "pii_redaction_enabled": false,
    "blocked_keywords": [],
    "max_input_tokens": 4096,
    "max_output_tokens": 2048,
    "max_total_tokens": 6144
  },
  "embedding_profile_config": { ... },
  "policy_bindings": [ ... ]
}
```

**實作位置：** `xparse_iam/api/ninja_api/_internal.py:144-223`

**安全性：** 明文 Provider Key 只在 Docker 內部網路傳輸；Phase 2 計畫加入 mTLS。

**Gateway 端快取：** `IAMValidateCache`（bustream 側）— 正向結果 TTL 30s，負向 60s。

---

#### 端點 2：`/iam/internal/resolve-provider-credential`

```
agentd  →  POST /iam/internal/resolve-provider-credential
           無認證（網路層信任）
```

**Request：**
```json
{
  "provider_code": "huggingface",
  "tenant_uuid": "550e8400-..."
}
```

**Response（200 OK）：**
```json
{
  "credential_uuid": "...",
  "provider_code": "huggingface",
  "key_version": 3,
  "resolved_token": "hf_abc123..."
}
```

**Response（404）：**
```json
{ "error": "no active credential for provider huggingface" }
```

**實作位置：** `xparse_iam/api/ninja_api/_internal.py:229-323`

---

### 5.3 Console App（前端）↔ IAM

**類型：Frontend → Backend**

Console App 是 IAM 的主要 **管理界面使用方**，透過 Bearer Token 存取所有管理 API，部分端點（OIDC config、Bootstrap）無需認證。

**認證流程（OIDC SSO）：**
```
Console  →  GET  /iam/oidc/config           ← 取得 issuer, client_id
         →  [Browser redirect to Keycloak]  ← PKCE 流程
         ←  [Keycloak 回傳 id_token]
         →  POST /iam/oidc/exchange          ← 換取 session_key
         ←  { session_key: "xp_live_..." }
         →  所有後續請求帶 Authorization: Bearer <session_key>
```

**典型請求 Headers：**
```
Authorization: Bearer xp_live_...
Content-Type: application/json
```

**CORS：** 由 Django settings 或上游 Nginx 設定（`CSRF_TRUSTED_ORIGINS` env var）。

---

### 5.4 IAM → Keycloak（OIDC Token 驗證）

**類型：Backend → External IdP**

IAM 在 OIDC Token Exchange 時，需向 Keycloak 取得 JWKS 驗證 JWT 簽章。

```
IAM  →  GET ${XPARSE_OIDC_JWKS_URL}
        例: https://kc.example.com/realms/xparse/protocol/openid-connect/certs
        Auth: 無
        Library: requests
        TTL Cache: 1 小時（module-level dict）
```

**Response（JWKS 格式）：**
```json
{
  "keys": [
    {
      "kid": "...",
      "kty": "RSA",
      "alg": "RS256",
      "n": "...",
      "e": "..."
    }
  ]
}
```

**Token 驗證步驟（`core/oidc.py`）：**
1. Fetch JWKS（有快取則用快取）
2. 驗證簽章（RS256）
3. 驗證 `exp`（過期時間）
4. 驗證 `aud`（須等於 `XPARSE_OIDC_CLIENT_ID`）
5. 驗證 `iss`（須等於 `XPARSE_OIDC_ISSUER`）

**失敗行為：** Token 驗證失敗 → `403 Forbidden`，不 fallback。

---

### 5.5 IAM → Scheduler（部署觸發）

**類型：Backend → Backend（呼叫方）**

Console 請求部署 Application 時，IAM 負責呼叫 Scheduler 執行 Container Placement。

```
IAM  →  POST ${SCHEDULER_URL}/scheduler/placements
        Auth: 無（Docker 內部網路）
        Library: httpx（async）
        Timeout: 依設定
```

**Request：**
```json
{
  "application_uuid": "...",
  "deployment_uuid": "...",
  "image": "registry.example.com/my-app:latest",
  "env": { "KEY": "VALUE" },
  "gpu_count": 1,
  "gpu_memory_gb": 24
}
```

**Response（201 Created）：**
```json
{
  "placement_uuid": "...",
  "node_id": "node-01"
}
```

**實作位置：** `xparse_iam/api/ninja_api/_deployments.py:630-644`

**失敗行為：** Scheduler 不可用 → **503 hard fail**（ADR-121，不 fallback）。

---

### 5.6 IAM → Fleet（Instance 查詢 & 命令）

**類型：Backend → Backend（呼叫方）**

IAM 在兩個場景呼叫 Fleet：
1. 解析 App / Deployment 的實際 endpoint（路由用）
2. 建立 Group Sidecar Proxy（ADR-136）

#### 查詢 App Endpoint

```
IAM  →  GET ${FLEET_API_URL}/apps/{app_code}/endpoint
        預設: http://localhost:8800/v1/fleet
        Header: Authorization: Bearer ${FLEET_API_TOKEN}  (選用)
        TTL Cache: 內存 dict，可設定 TTL
```

**Response：**
```json
{
  "instances": [
    {
      "instance_id": "inst-01",
      "endpoint": "http://10.0.1.5:8080",
      "status": "running"
    }
  ],
  "lb_strategy": "round_robin"
}
```

**實作位置：** `xparse_iam/api/ninja_api/_helpers.py:256-408`

#### 查詢 Deployment Endpoint（ADR-129 Phase 1）

```
IAM  →  GET ${FLEET_API_URL}/apps/{app_code}/deployments/{deploy_code}/endpoint
```

#### 建立 Group Sidecar 命令

```
IAM  →  POST ${FLEET_API_URL}/nodes/{node_id}/commands
        Body: { "action": "create_group_sidecar", "params": {...} }
```

**實作位置：** `xparse_iam/api/ninja_api/_group_sidecar.py:216-237`

**失敗行為：** Fleet 不可用 → Fail-open（回傳空 instance 清單）。

---

### 5.7 IAM → Provider APIs（連線測試）

**類型：Backend → External Cloud API（僅限 Console 連線測試功能）**

**注意：這不是推論路徑**，只有在 Console 按下「Test Connection」時才觸發。

```
IAM  →  各 Provider API
        Library: requests（sync）
        Timeout: 10-15s
```

| Provider | 測試端點 | 認證 |
|----------|---------|------|
| OpenAI | `GET https://api.openai.com/v1/models` | `Authorization: Bearer <key>` |
| Azure OpenAI | `GET {endpoint}/openai/deployments/{id}?api-version=2024-02-01` | `api-key: <key>` |
| Anthropic | `POST https://api.anthropic.com/v1/messages` | `x-api-key: <key>` |
| Google Gemini | `GET https://generativelanguage.googleapis.com/v1beta/models/{model}?key={key}` | Query param |
| vLLM | `GET {endpoint}/v1/models` | `Authorization: Bearer <key>` |

**實作位置：** `xparse_iam/api/ninja_api/_helpers.py:483-764`

**失敗行為：** 連線失敗 → 回傳測試結果 `{ "success": false, "message": "..." }` 給 Console，不影響系統運作。

---

### 5.8 Scheduler → IAM（內部查詢）

**類型：Backend → Backend（被呼叫方）**

Scheduler 在 Placement 決策前查詢 IAM 取得資源限制。

| 端點 | 目的 | Timeout |
|------|------|---------|
| `GET /iam/internal/node-allocations?tenant=<uuid>` | 取得租戶現有 GPU 配置 | — |
| `GET /iam/internal/group-quotas/{group_uuid}` | 取得 Group 資源上限 | — |
| `GET /iam/internal/resource-profiles/{application_uuid}` | 取得 App 所需資源規格 | — |
| `GET /iam/internal/deployment-count/{application_uuid}` | 取得 App 現有 Deployment 數量 | — |

**實作位置：** `xparse_iam/api/ninja_api/_internal.py:64-141`

---

## 6. 請求主流程

### 6.1 API Key 驗證流程（被 Gateway 呼叫）

```
Gateway
  ↓  POST /iam/internal/gateway-validate  {"api_key": "xp_live_..."}
  │
  ├─ [_internal.py] 接收請求
  ├─ [core/auth_engine.py] 三層 Key 查找：
  │   ├─ Step 1: TenantAPIKey.objects.get(key_hash=sha256(api_key))
  │   ├─ Step 2: GroupAPIKey.objects.get(key_hash=...) （若 Step 1 miss）
  │   └─ Step 3: APIKey.objects.get(key_hash=...) （若 Step 2 miss）
  ├─ 驗證 Key 狀態（ACTIVE / DEPRECATED / EXPIRED / REVOKED）
  ├─ [core/crypto.py] 解密 ProviderCredential（Master Secret + KEK）
  ├─ 組裝 AuthContext（tenant, application, models, policies）
  └─ Response 200 + AuthContext（含明文 Provider Key）
```

### 6.2 OIDC Login 流程（前端 Console）

```
Console
  ↓  GET /iam/oidc/config
  ←  { enabled: true, issuer: "https://kc.example/realms/xparse", client_id: "xparse-console" }
  │
  [Browser 執行 OIDC PKCE 流程，Redirect 到 Keycloak]
  [Keycloak 驗證後回傳 id_token]
  │
  ↓  POST /iam/oidc/exchange  { "id_token": "<JWT>" }
  │
  ├─ [_oidc.py] 接收請求
  ├─ [core/oidc.py] 驗證 id_token：
  │   ├─ Fetch JWKS from ${XPARSE_OIDC_JWKS_URL}（有快取則用快取，TTL 1h）
  │   ├─ 驗證 RS256 簽章
  │   ├─ 驗證 exp / aud / iss
  │   └─ 解析 sub（subject），取得 email, display_name
  ├─ 查找或建立 OIDCUserMapping（tenant binding）
  ├─ 產生 Session Key（xp_live_...，SHA-256 入庫，原文不存）
  └─ Response 200 { session_key, tenant_uuid, tenant_code, display_name }
```

### 6.3 Application 部署流程（Console 觸發）

```
Console
  ↓  POST /iam/applications/{uuid}/deploy
  │
  ├─ [_deployments.py] 驗證 Bearer token
  ├─ 取得 Application 設定（image, env, resource_profile）
  ├─ 呼叫 Scheduler：
  │   ↓  POST ${SCHEDULER_URL}/scheduler/placements
  │   ←  { placement_uuid, node_id }
  ├─ 更新 Deployment 狀態
  └─ Response 201 { deployment_uuid, placement_uuid, node_id }
```

---

## 7. 關鍵類別索引

| 類別 | 檔案 | 職責 |
|------|------|------|
| `IAMClient` | `client.py` | bustream direct mode 使用的 in-process client |
| `XparseAPIKeyAuth` | `api/authentication.py` | Ninja Bearer 認證 decorator，呼叫 auth_engine |
| `AuthEngine` | `core/auth_engine.py` | 三層 API Key 查找（TenantKey → GroupKey → AppKey） |
| `OIDCVerifier` | `core/oidc.py` | OIDC ID Token RS256 驗證 + JWKS TTL 快取 |
| `CryptoEngine` | `core/crypto.py` | Master Secret + KEK 加密 / 解密 Provider Credential |
| `KeyHasher` | `core/key_hash.py` | SHA-256 單向雜湊，原文不入庫 |
| `GatewayValidateAPI` | `api/ninja_api/_internal.py:144` | Gateway 驗證端點實作 |
| `ResolveCredentialAPI` | `api/ninja_api/_internal.py:229` | agentd Credential 解析端點 |
| `OIDCExchangeAPI` | `api/ninja_api/_oidc.py:72` | ID Token → Session Key 交換 |
| `DeploymentAPI` | `api/ninja_api/_deployments.py` | Deployment 管理 + 呼叫 Scheduler |
| `FleetHelpers` | `api/ninja_api/_helpers.py` | Fleet endpoint 解析 + Provider 連線測試 |
| `GroupSidecarAPI` | `api/ninja_api/_group_sidecar.py` | Group Sidecar 建立（呼叫 Fleet 命令） |
| `ConsoleCapabilities` | `api/console_capabilities.py` | 依 Edition + Role 解析 Console 可用功能 |
| `TenantAPIKey` | `db/models/` | 租戶級 API Key ORM Model |
| `ProviderCredential` | `db/models/` | 加密儲存 Provider API Key |
| `OIDCUserMapping` | `db/models/` | OIDC Subject → Tenant Mapping |

---

## 8. 重要環境變數

| 變數 | 預設值 | 說明 |
|------|-------|------|
| `XPARSE_IAM_DB_ENGINE` | `sqlite` | 資料庫引擎（`sqlite` / `postgres`） |
| `XPARSE_IAM_DB_PATH` | `./xparse_iam.db` | SQLite 路徑 |
| `XPARSE_IAM_DB_HOST` | — | PostgreSQL Host |
| `XPARSE_IAM_DB_PORT` | `5432` | PostgreSQL Port |
| `XPARSE_IAM_DB_USER` | — | PostgreSQL 帳號 |
| `XPARSE_IAM_DB_PASSWORD` | — | PostgreSQL 密碼 |
| `XPARSE_MASTER_SECRET` | — | ★ 加密主金鑰（必填） |
| `XPARSE_KEK` | — | Key Encryption Key |
| `XPARSE_GATEWAY_IAM_SECRET` | — | Gateway → IAM 呼叫共享密鑰（選用） |
| `XPARSE_OIDC_ENABLED` | `false` | 啟用 OIDC SSO |
| `XPARSE_OIDC_ISSUER` | — | Keycloak Realm URL（瀏覽器可達） |
| `XPARSE_OIDC_JWKS_URL` | — | JWKS fetch URL（內部可達） |
| `XPARSE_OIDC_CLIENT_ID` | `xparse-console` | OIDC Client ID |
| `XPARSE_OIDC_SESSION_TTL_HOURS` | `8` | Session Key 有效時間 |
| `XPARSE_OIDC_AUTO_PROVISION` | `false` | 首次 SSO 自動建立 Tenant |
| `XPARSE_OIDC_TENANT_CLAIM` | `tenant` | JWT claim 名稱（Tenant 識別） |
| `SCHEDULER_URL` | — | Scheduler 服務 URL |
| `FLEET_API_URL` | `http://localhost:8800/v1/fleet` | Fleet API URL |
| `FLEET_API_TOKEN` | — | Fleet API Bearer Token（選用） |
| `XPARSE_GATEWAY_INTERNAL_URL` | `http://xparse-scr:8000/v1` | 注入 Container 的 Gateway URL |
| `CSRF_TRUSTED_ORIGINS` | — | CORS 信任來源（Console URL） |

---

## 9. 關聯文件索引

### ADR（架構決策）

| ADR | 主題 |
|-----|------|
| ADR-018 | Identity & Auth 基礎設計 |
| ADR-023 | API Key 三層查找順序 |
| ADR-039 | Startup 驗證（App 啟動時自動檢查） |
| ADR-057 | Azure OpenAI + Provider Credential 設計 |
| ADR-074 | Auth Engine 進階設計 |
| ADR-081 | Authorization Policy Rev.2 |
| ADR-082 | Authorization Policy |
| ADR-089 | IAM EmbeddingProfileConfig 整合 |
| ADR-096 | Authorization Policy |
| ADR-121 | Deployment hard-fail on Scheduler unavailable |
| ADR-129 | Fleet Deployment Endpoint 解析 Phase 1 |
| ADR-136 | Group Sidecar Proxy 架構 |
| ADR-174 | OIDC Issuer Allowlist（PRD-144） |

### PRD（產品需求）

| PRD | 主題 |
|-----|------|
| PRD-057 | Group 管理（Developer Role） |
| PRD-059 | Permission 系統設計 |
| PRD-060 | Auth Engine 設計 |
| PRD-063 | Data Visibility 管理 |
| PRD-071 | Group Developer Role |
| PRD-075 | OIDC User Mapping 管理 |
| PRD-081 | Application 建立（Type-based） |
| PRD-082 | Universal Deployment Model |
| PRD-091-01 | Skills Platform |
| PRD-113 | Deployment Count Limit（INV-113-5） |
| PRD-130 | Console Edition / Feature Gating |
| PRD-144 | OIDC Issuer Allowlist |

---

## 10. 規模統計

| 模組 | 估計程式碼行數 |
|------|--------------|
| `api/` (含 ninja_api/) | ~18,700 |
| `settings.py` | ~700 |
| `core/` | ~600 |
| `db/models/` | ~1,000 |
| `application/use_cases/` | ~400 |
| `domain/value_objects/` | ~200 |
| `migrations/` (0001–0037+) | ~3,000 |
| **合計** | **~25,000+ 行** |

---

## 11. 總結

`xparse_iam` 是 Xparse 平台的 **Governance / Control Plane 核心**，是整個平台的**安全與授權中心**。

**面向：**
- **前端應用**（Console App）：管理 Tenant、Application、Group、Model、Policy 的完整 CRUD，以及 OIDC SSO 登入
- **後端服務**（Gateway/bustream）：提供 API Key 驗證 + 解密 Provider Credential（最關鍵的內部 API）
- **後端服務**（Scheduler）：提供資源配額查詢（GPU allocations、group quotas、resource profiles）

**呼叫其他服務：**
- **Keycloak** — 取得 JWKS 驗證 OIDC Token
- **Scheduler** — 觸發 Container 部署（hard fail on unavailable）
- **Fleet** — 查詢 App Instance Endpoint、建立 Group Sidecar（fail-open）
- **Provider APIs** — 僅限 Console 連線測試功能（OpenAI / Azure / Anthropic / vLLM）

**不是：**
- 前端應用（無 UI）
- 推論路徑（不處理 AI 請求）
- 直接管理 Container（委託 Scheduler）
