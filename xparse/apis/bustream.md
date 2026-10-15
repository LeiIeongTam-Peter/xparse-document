# Bustream 技術文件

> **適用版本**：Phase 6+（生產強化版）
> **最後更新**：2026-06-01
> **服務定位**：Xparse 核心 AI 推理編排引擎（Gateway）——實作 OpenAI 相容 API，負責認證、Admission 控制、路由決策、串流編排、稽核發送。

---

## API 流量方向總覽

Bustream（`xparse-gateway`）在平台中扮演 **邊界 Gateway**：對外接收 HTTP 請求，對內以 HTTP Client / SDK 呼叫其他後端。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         bustream Gateway (:8000)                        │
│                                                                         │
│  ① 前端 / 瀏覽器 ──────────►  /v1/*, /v2/*, 部分 /admin/*              │
│  ② 其他後端 / SDK / 監控 ──►  同上 + /metrics, /admin/*（運維）        │
│                                                                         │
│  ③ bustream 主動呼叫 ──────►  IAM, Resource Manager, Guardrails,       │
│                               AI Provider, Audit SDK, OTel Collector    │
└─────────────────────────────────────────────────────────────────────────┘
```


| 方向                    | 說明                                                             | 詳見章節                                        |
| --------------------- | -------------------------------------------------------------- | ------------------------------------------- |
| **① 前端 → bustream**   | Console App、Playground、Agent App UI 透過 Bearer API 金鑰呼叫 Gateway | [二、前端 API](#二前端-api-清單)                     |
| **② 其他後端 → bustream** | OpenAI SDK 客戶端、批次任務、IAM、運維腳本、Prometheus 等呼叫 Gateway 暴露的端點      | [三、後端 API（Inbound）](#三後端-api-清單inbound)     |
| **③ bustream → 其他後端** | Gateway 在請求處理過程中主動發出的 HTTP / SDK 呼叫                            | [四、對外呼叫（Outbound）](#四bustream-對外呼叫outbound) |


> **注意**：`/v1/chat/completions` 等 OpenAI 相容端點同時被前端與後端使用；兩邊都會收到請求，差別在 **呼叫方身份**（瀏覽器 UI vs. 服務間 M2 金鑰 / SDK），而非端點路徑不同。

---

## 一、服務端口清單（Service Ports）


| 服務名稱                                | 端口號碼           | 通訊協定         | 用途說明                                                                                     |
| ----------------------------------- | -------------- | ------------ | ---------------------------------------------------------------------------------------- |
| **xparse-gateway**（bustream）        | `8000`         | HTTP         | 主 API 網關；對外公開 `/v1/`*、`/v2/*`、`/admin/*` 端點。容器內固定 8000，對外端口由 `XPARSE_PORT` 控制（預設同 8000）。 |
| **xparse-iam**                      | `8010`         | HTTP         | IAM 服務；bustream 以 HTTP 模式呼叫此端口進行身份驗證（`GATEWAY_IAM_MODE=http`）。                           |
| **xparse-resource-manager**         | `8020`         | HTTP         | 共享端點優先佇列；Layer 2 Admission 控制（SPEC-086）。                                                 |
| **xparse-guardrails**（NeMo sidecar） | `8400`         | HTTP         | NeMo Guardrails sidecar；內容審查 sidecar。                                                    |
| **xparse-console**                  | `8080` / `443` | HTTP / HTTPS | React 前端（SPA）；**不直接呼叫 Resource Manager**，推理請求走 Gateway。                                  |
| **xparse-traffic**（反向代理）            | `8000`（對外）     | TCP          | nginx/HAProxy 流量代理；blue-green 切換。                                                        |
| **Prometheus metrics**              | `8000/metrics` | HTTP         | 與 Gateway 同端口，路徑 `/metrics`。                                                             |


> **環境變數對照**：
>
> - `GATEWAY_PORT`（預設 `8000`）：bustream Gateway 監聽端口
> - `GATEWAY_IAM_URL`（預設 `http://xparse-iam:8010`）：IAM 服務 URL
> - `RESOURCE_MANAGER_URL`（預設 `http://localhost:8020`）：Resource Manager URL
> - `XPARSE_GUARDRAIL_SIDECAR_URL`（預設 `http://xparse-guardrails:8400`）：Guardrail sidecar URL
> - `XPARSE_PORT`（預設 `8000`）：Docker 對外公開端口

---

## 二、前端 API 清單

> **發起方**：Console App（`frontend/console-app/`）、Playground、Agent App 前端 UI、Open WebUI 等 **使用者介面**。
> **認證**：`Authorization: Bearer <api-key>`（M1 用戶金鑰為主）。
> **基址**：`${GATEWAY_URL}`（通常經 `xparse-traffic` 或 `:8000` 進入）。

以下端點由前端直接呼叫 bustream；**前端不應直接呼叫 IAM（:8010）或 Resource Manager（:8020）**。

### 2.1 AI 推理（OpenAI Compatible）


| HTTP 方法  | 端點路徑                          | 功能說明                                       | 典型前端場景                   |
| -------- | ----------------------------- | ------------------------------------------ | ------------------------ |
| `POST`   | `/v1/chat/completions`        | 聊天補全；支援 `stream=true`（SSE）與 `stream=false` | Playground 對話、Open WebUI |
| `POST`   | `/v1/embeddings`              | 文字嵌入向量（SPEC-039）                           | 語意搜尋 UI                  |
| `POST`   | `/v1/audio/speech`            | 文字轉語音 TTS（PRD-037）                         | 語音播放                     |
| `POST`   | `/v1/audio/transcriptions`    | 語音轉文字 STT                                  | 錄音上傳逐字稿                  |
| `GET`    | `/v1/models`                  | 列出可用模型（ADR-138）                            | 模型選擇下拉選單                 |
| `POST`   | `/v1/responses`               | 建立代理回應綁定（PRD-157）                          | Agent App 前端             |
| `DELETE` | `/v1/responses/{response_id}` | 刪除回應綁定                                     | Agent App 前端             |


### 2.2 信號與 Agent 任務


| HTTP 方法 | 端點路徑                              | 功能說明                   | 典型前端場景       |
| ------- | --------------------------------- | ---------------------- | ------------ |
| `POST`  | `/v1/signals/{request_id}`        | 發送取消信號（TD-004 Phase 3） | 「停止生成」按鈕     |
| `GET`   | `/v1/signals/{request_id}/status` | 查詢信號狀態                 | 對話狀態指示器      |
| `POST`  | `/v2/tasks`                       | 建立 Agent 任務            | Agent 工作流 UI |
| `GET`   | `/v2/tasks/{task_id}`             | 查詢任務狀態                 | 任務列表 / 詳情頁   |
| `POST`  | `/v2/tasks/{task_id}/resume`      | 恢復暫停任務                 | 任務控制面板       |
| `POST`  | `/v2/tasks/{task_id}/execute`     | 觸發任務執行                 | 任務控制面板       |
| `GET`   | `/v2/tasks/{task_id}/events`      | 訂閱任務事件流（SSE）           | 即時任務進度       |


### 2.3 Console 管理（部分 Admin 端點）

> 僅限具備 admin 權限的 Console 管理頁面使用；一般 Playground 不呼叫。


| HTTP 方法 | 端點路徑                               | 功能說明                |
| ------- | ---------------------------------- | ------------------- |
| `GET`   | `/admin/routing/config/{app_uuid}` | 取得 Application 路由配置 |
| `PUT`   | `/admin/routing/config/{app_uuid}` | 更新 Application 路由配置 |


### 2.4 健康檢查


| HTTP 方法 | 端點路徑         | 功能說明                   |
| ------- | ------------ | ---------------------- |
| `GET`   | `/health`    | 詳細健康狀態；Console 部署狀態指示器 |
| `GET`   | `/v1/health` | 同 `/health` 的 v1 別名    |
| `GET`   | `/`          | 服務版本資訊                 |


---

## 三、後端 API 清單（Inbound）

> **發起方**：其他後端服務、OpenAI SDK 客戶端、Agent Runtime（OpenClaw）、IAM、部署腳本、Prometheus、K8s 探針等。
> **說明**：本節列出 **呼叫 bustream Gateway 的端點**；與第二節路徑相同者，代表該端點為 **共用入口**，差別在呼叫方與金鑰類型（M0 / M1 / M2）。

### 3.1 核心推理 API（OpenAI Compatible）


| HTTP 方法  | 端點路徑                          | 功能說明                                                           | 典型呼叫來源                                |
| -------- | ----------------------------- | -------------------------------------------------------------- | ------------------------------------- |
| `POST`   | `/v1/chat/completions`        | **核心入口**；串流 / 非串流、tool calling、Vision、reasoning model（ADR-056） | OpenAI SDK、Agent App 後端、OpenClaw、批次任務 |
| `POST`   | `/v1/embeddings`              | 嵌入向量；轉發至 embedding provider                                    | 後端語意搜尋服務                              |
| `POST`   | `/v1/audio/speech`            | TTS；轉發至 TTS provider                                           | 後端語音合成管線                              |
| `POST`   | `/v1/audio/transcriptions`    | STT；轉發至 Whisper-compatible provider                            | 後端語音處理管線                              |
| `GET`    | `/v1/models`                  | 模型清單；從 model registry 讀取                                       | SDK 初始化、健康檢查腳本                        |
| `POST`   | `/v1/responses`               | Responses API 綁定（PRD-157, ADR-192）                             | Agent Runtime 後端                      |
| `DELETE` | `/v1/responses/{response_id}` | 刪除回應綁定                                                         | Agent Runtime 後端                      |


#### `/v1/chat/completions` 請求標頭


| 標頭名稱                            | 必填  | 說明                                     |
| ------------------------------- | --- | -------------------------------------- |
| `Authorization: Bearer <token>` | 是   | API 金鑰（M0 / M1 / M2，由 IAM 發行）          |
| `X-Request-Id`                  | 否   | 請求追蹤 ID（未提供時 Gateway 自動生成）             |
| `X-Tenant`                      | 否   | 租戶 UUID 覆寫（僅限 M0 管理員金鑰）                |
| `X-Conversation-Id`             | 否   | vLLM prefix cache salt 的對話 ID（PRD-034） |
| `X-Cache-Salt`                  | 否   | 顯式指定 cache salt                        |
| `X-Agent-Task-Id`               | 否   | Agent 任務層級 cache 共享（ADR-055）           |
| `X-Bustream-Debug`              | 否   | 啟用 debug 模式                            |


> **金鑰類型**：
>
> - **M0**：Admin 金鑰；可存取 `/admin/`*，可覆寫 `X-Tenant`
> - **M1**：標準用戶金鑰；綁定 Application
> - **M2**：Service-to-Service 金鑰；後端整合首選

### 3.2 管理員 API

> **認證要求**：M0 admin-level API 金鑰。**前端 Console 僅使用 3.2 中的 routing 端點**；其餘由 IAM / 運維工具呼叫。


| HTTP 方法  | 端點路徑                               | 功能說明                       | 典型呼叫來源               |
| -------- | ---------------------------------- | -------------------------- | -------------------- |
| `POST`   | `/admin/keys`                      | 建立 API 金鑰                  | IAM 金鑰輪替流程           |
| `GET`    | `/admin/keys`                      | 列出 API 金鑰                  | 運維工具                 |
| `DELETE` | `/admin/keys/{key}`                | 撤銷 API 金鑰                  | IAM / 運維工具           |
| `POST`   | `/admin/registry/reload`           | 重新載入 `model_registry.json` | 部署腳本                 |
| `GET`    | `/admin/routing/config/{app_uuid}` | 取得路由配置                     | Console 管理頁（亦見 §2.3） |
| `PUT`    | `/admin/routing/config/{app_uuid}` | 更新路由配置                     | Console 管理頁（亦見 §2.3） |


### 3.3 信號與 Agent 任務 API


| HTTP 方法 | 端點路徑                              | 功能說明                  | 典型呼叫來源            |
| ------- | --------------------------------- | --------------------- | ----------------- |
| `POST`  | `/v1/signals/{request_id}`        | 發送取消信號至 SignalHub     | Agent Runtime、SDK |
| `GET`   | `/v1/signals/{request_id}/status` | 查詢信號狀態                | Agent Runtime     |
| `POST`  | `/v2/tasks`                       | 建立 Agent 任務           | Agent App 後端      |
| `GET`   | `/v2/tasks/{task_id}`             | 查詢任務狀態                | Agent App 後端、編排器  |
| `POST`  | `/v2/tasks/{task_id}/resume`      | 恢復暫停任務                | Agent App 後端      |
| `POST`  | `/v2/tasks/{task_id}/execute`     | 觸發 planner + executor | Agent App 後端      |
| `GET`   | `/v2/tasks/{task_id}/events`      | 任務事件 SSE 流            | Agent App 後端      |


### 3.4 可觀測性與基礎設施


| HTTP 方法 | 端點路徑         | 功能說明          | 典型呼叫來源                 |
| ------- | ------------ | ------------- | ---------------------- |
| `GET`   | `/health`    | 各元件健康狀態       | Docker HEALTHCHECK、監控  |
| `GET`   | `/v1/health` | 同 `/health`   | OpenAI-compatible 健康腳本 |
| `GET`   | `/`          | 版本與基本資訊       | K8s liveness probe     |
| `GET`   | `/metrics`   | Prometheus 指標 | Prometheus / Grafana   |


### 3.5 端點歸類速查


| 端點                           | 前端  | 後端 Inbound | 備註                |
| ---------------------------- | --- | ---------- | ----------------- |
| `/v1/chat/completions`       | ✓   | ✓          | 最常用；非串流模式多由後端批次使用 |
| `/v1/embeddings`             | ✓   | ✓          |                   |
| `/v1/audio/`*                | ✓   | ✓          |                   |
| `/v1/models`                 | ✓   | ✓          |                   |
| `/v1/responses`              | ✓   | ✓          |                   |
| `/v1/signals/*`              | ✓   | ✓          |                   |
| `/v2/tasks/*`                | ✓   | ✓          |                   |
| `/admin/routing/config/*`    | ✓   | ✓          | Console 管理頁       |
| `/admin/keys`                | —   | ✓          | 僅 IAM / 運維        |
| `/admin/registry/reload`     | —   | ✓          | 僅部署腳本             |
| `/health`, `/v1/health`, `/` | ✓   | ✓          | 前端輪詢 + 基礎設施探針     |
| `/metrics`                   | —   | ✓          | 僅監控系統             |


---

## 四、Bustream 對外呼叫（Outbound）

> bustream Gateway 作為 orchestrator，在處理每個 inbound 請求時，依序或並行呼叫以下後端。
> **這些端點不由前端直接存取**；詳細規格請參考各服務文件（`iam.md`、`resource_manager.md`、`audit.md`）。

### 4.1 IAM（`xparse-iam:8010`）


| HTTP 方法 | 端點路徑                                           | 功能說明                                  | 呼叫時機                                   |
| ------- | ---------------------------------------------- | ------------------------------------- | -------------------------------------- |
| `POST`  | `/iam/internal/gateway-validate`               | 完整 Gateway 驗證；回傳 `AuthContext` 與解密後金鑰 | 每個 inbound 請求（`GATEWAY_IAM_MODE=http`） |
| `POST`  | `/iam/auth/validate`                           | 公開內部金鑰驗證                              | 部分輕量驗證路徑                               |
| `POST`  | `/iam/derive`                                  | 衍生受限範圍 API 金鑰                         | 金鑰衍生流程                                 |
| `POST`  | `/iam/responses-binding`                       | 建立 Responses API 會話綁定                 | `POST /v1/responses` 處理時               |
| `GET`   | `/iam/responses-binding/lookup`                | 查詢綁定狀態                                | Response API 查詢                        |
| `PATCH` | `/iam/responses-binding/{binding_uuid}/delete` | 標記綁定已刪除                               | `DELETE /v1/responses/{id}` 處理時        |


> **本地模式**：`GATEWAY_IAM_MODE=direct` 時，bustream 直接讀取本地 SQLite（`xparse_iam`），不發 HTTP 至 IAM 容器。

### 4.2 Resource Manager（`xparse-resource-manager:8020`）


| HTTP 方法 | 端點路徑                                        | 功能說明                        | 呼叫時機                          |
| ------- | ------------------------------------------- | --------------------------- | ----------------------------- |
| `POST`  | `/resource/endpoints/{endpoint_id}/acquire` | 申請端點容量租賃（Layer 2 Admission） | 推理請求進入 StreamingManager 前     |
| `POST`  | `/resource/endpoints/{endpoint_id}/release` | 釋放租賃（fire-and-forget）       | LLM 請求完成後                     |
| `GET`   | `/resource/endpoints/{endpoint_id}/status`  | 查詢端點容量狀態                    | 監控 / 診斷                       |
| `GET`   | `/resource/endpoints`                       | 列出已註冊端點                     | `EndpointResolver` 每 60 秒背景刷新 |


> 詳見 `[resource_manager.md](./resource_manager.md)`。

### 4.3 Guardrail Sidecar（`xparse-guardrails:8400`）


| HTTP 方法 | 端點路徑            | 功能說明                 | 呼叫時機                                                            |
| ------- | --------------- | -------------------- | --------------------------------------------------------------- |
| `POST`  | `/v1/guardrails/{config_id}/check` | NeMo Guardrails 內容審查 / PII | 啟用 `XPARSE_GUARDRAIL_ENABLED=true` 且 policy 需 content filter 時 |


> **模式**：`XPARSE_GUARDRAIL_MODE=shadow`（僅記錄）或 `enforce`（強制攔截）。

### 4.4 AI Provider（外部推理端點）


| 目標                             | 協定         | 端點                       | 呼叫時機                                             |
| ------------------------------ | ---------- | ------------------------ | ------------------------------------------------ |
| OpenAI / Azure OpenAI          | HTTPS      | `/v1/chat/completions` 等 | `StreamingWorker` / `NonStreamingCollector` 轉發推理 |
| vLLM（自託管）                      | HTTP       | provider-specific        | 同上                                               |
| Anthropic / Bedrock 等          | HTTPS      | provider-specific        | Worker provider-aware sanitization 後轉發           |
| TTS / STT / Embedding provider | HTTPS/HTTP | provider-specific        | 對應 `/v1/audio/`*、`/v1/embeddings` 路由             |


> Provider 金鑰由 `key_resolver.py` 從 IAM 解析的 `AuthContext` 取得。

### 4.5 Audit SDK（本地，非 HTTP）


| 介面                       | 目標                      | 功能說明          | 呼叫時機      |
| ------------------------ | ----------------------- | ------------- | --------- |
| `bustream/audit/emit.py` | `3rd/xparse_audit/` SDK | 寫入 JSONL 稽核事件 | 請求生命週期各節點 |


**主要事件**：`REQUEST_RECEIVED` → `ADMISSION_DECIDED` → `ROUTING_RESOLVED` → `PROVIDER_RESPONSE` → `STREAMING_COMPLETED` / `STREAMING_ERROR`

> 詳見 `[audit.md](./audit.md)`。Audit Query API（`:8001`）由 Console 前端直接呼叫，**非 bustream outbound**。

### 4.6 OpenTelemetry（選配）


| 協定              | 目標                            | 功能說明          | 呼叫時機                                  |
| --------------- | ----------------------------- | ------------- | ------------------------------------- |
| OTLP（HTTP/gRPC） | `OTEL_EXPORTER_OTLP_ENDPOINT` | 發送 trace span | 啟用 `BUSTREAM_OBSERVABILITY_ENABLED` 時 |


### 4.7 Outbound 呼叫時序（簡圖）

```
Inbound: POST /v1/chat/completions
  │
  ├─① IAM validate              （每請求）
  ├─② Guardrail input check     （選配；見 §5.8；本地規則或 Outbound §4.3 sidecar）
  ├─③ Admission Layer 1         （Gateway 本地）
  ├─④ RM acquire                （Layer 2，若 endpoint 已註冊）
  ├─⑤ AI Provider streaming   （核心推理）
  ├─⑥ Guardrail output check    （選配；reverse 事件前，StreamingManagerV3 內）
  ├─⑦ Audit emit                （各階段，含 guardrail_check / guardrail_blocked）
  ├─⑧ RM release                （完成後，fire-and-forget）
  └─⑨ OTel / Prometheus         （若啟用）
```

---

## 五、工作流程（Workflows）

### 5.1 核心串流請求（`stream=true`）

**發起方**：前端 Playground / OpenAI SDK 客戶端（Inbound §2 / §3）

> **Guardrail**：Step 2 與 Step 8 為**選配**路徑，需 `XPARSE_GUARDRAIL_ENABLED=true` 且 IAM 已指派 `guardrail_policy` 才會執行；詳見 [§5.8](#58-guardrail-工作流程spec-106--adr-139)。

```
客戶端
  │  POST /v1/chat/completions  { stream: true }
  ▼
bustream Gateway
  │  Step 1  認證 → IAM gateway-validate（Outbound §4.1）
  │  Step 2  Guardrail Input（選配）→ token / keyword / NeMo sidecar（Outbound §4.3）
  │  Step 3  Admission Layer 1 → TokenBucket / Semaphore
  │  Step 4  政策評估 → policy/kernel.py（純函數，無 I/O）
  │  Step 5  路由決策 → RoutingResolver → ExecutionPlan
  │  Step 6  RM acquire（Outbound §4.2，Layer 2）
  │  Step 7  Worker 初始化 → FastWorker / LargeWorker / SafetyWorker
  │  Step 8  StreamingManagerV3 編排 → SSE delta
  │          └─ Output Guardrail（選配，reverse 前）→ reverse / error / [DONE]
  │  Step 9  AI Provider 串流（Outbound §4.4；貫穿 Step 7–8）
  │  Step 10 Audit + OTel + RM release + Layer 1 release_concurrency
  ▼
客戶端  ←  text/event-stream
```

### 5.2 非串流請求（`stream=false`）

**發起方**：後端服務 / 批次任務（Inbound §3.1，較少由前端 UI 使用）

```
POST /v1/chat/completions  { stream: false }
  → Gateway Step 1–6 同串流（含選配 Step 2 Guardrail Input）
  → NonStreamingCollector 累積 chunks（含 output guardrail，若啟用）
  → HTTP 200 application/json（含 usage）
  → Step 10 收尾同串流
```

### 5.3 雙層 Admission 控制

```
請求到達
  ▼
Layer 1（Gateway 本地）
  TokenBucket + Semaphore + Queue
  → EXECUTE_NOW / QUEUED / REJECTED（429 / 503）
  ▼
Layer 2（Resource Manager，Outbound §4.2）
  POST /resource/endpoints/{id}/acquire
  → 成功進推理 / timeout → 503 / queue_full → fail-open（SPEC §8.4）
```

### 5.4 認證流程（M0 / M1 / M2）

```
Authorization: Bearer <token>
  ▼
auth_handler.authenticate_request()
  ├─ GATEWAY_IAM_MODE=direct  → 本地 SQLite → AuthContext
  └─ GATEWAY_IAM_MODE=http    → POST /iam/internal/gateway-validate → AuthContext

AuthContext（immutable）：
  tenant_uuid, credential_uuid, application_uuid,
  rate_limit_policy, guardrail_policy, routing_strategy, allowed_models
```

### 5.5 StreamingManagerV3 狀態機

```
FAST_STREAMING → LARGE_BUFFERING → REVERSE_EMIT → DONE → FINALIZE
                     ↓（品質 < 0.7）
                  fast_only → DONE
```

> **不變量**（ADR-030, ADR-031）：`id` 請求級穩定；`seq` 單調遞增；`reverse` 最多一次；reverse 後不再發 delta。

### 5.6 Message Normalization（ADR-130）

三層：Gateway Input → Worker Provider-Aware → Client Fix。Normalization 永不 invent content，每次皆 WARNING log + audit。

### 5.7 稽核事件生命週期

```
REQUEST_RECEIVED
  → GUARDRAIL_CHECK / GUARDRAIL_BLOCKED（選配，input/output）
  → ADMISSION_DECIDED → ROUTING_RESOLVED
  → PROVIDER_RESPONSE → STREAMING_COMPLETED / STREAMING_ERROR
```

`correlation_id` 邊界入口綁定後全程不可變；`tenant_uuid` 從 AuthContext 傳播。

### 5.8 Guardrail 工作流程（SPEC-106 / ADR-139）

> **政策來源**：IAM `guardrail_policy`（§2.7）或 llm_operational binding 內的 `guardrail.mode`；**執行位置**：bustream Gateway（非 IAM HTTP 端點）。

**啟用條件（三者缺一不可才會「真的檢查」）**：

| 條件 | 預設 | 說明 |
|-----|------|------|
| `XPARSE_GUARDRAIL_ENABLED=true` | `false` | 未設則不建立 `GuardrailEnforcer`，Step 2 / 8 整段跳過 |
| `AuthContext.guardrail_policy` 非空 | 需 IAM 指派 | Application 或 Group 繼承的 guardrail policy |
| 端點為 `/v1/chat/completions` | — | `/v1/responses` 等目前無 guardrail（Phase 2） |

**兩個 checkpoint**：

| 階段 | 時機 | 模組 | 違規時（`enforce` 模式） |
|-----|------|------|------------------------|
| **Input** | Step 1 之後、Admission 之前 | `guardrail_handler.run_input_guardrail` | HTTP 413（token）、451（keyword/content）、503（sidecar 故障） |
| **Output** | Large 輸出 reverse 之前 | `StreamingManagerV3` → `check_output` | SSE error 事件，不發 reverse |

**檢查順序**（`GuardrailEnforcer`）：

1. `policy.enabled == false` → pass  
2. 本地：`max_input_tokens` / `max_output_tokens`、`blocked_keywords`  
3. NeMo sidecar：`POST /v1/guardrails/{config_id}/check`（需 `content_filter_level` 或 PII 設定）

**模式**（`shadow` vs `enforce`）：

| 模式 | 行為 |
|-----|------|
| `shadow` | 照常檢查 + audit + metrics；**不 block、不 modify**（log `shadow_would_block`） |
| `enforce` | 違規時 input 拒絕或 output 截斷 |

模式優先序：llm_operational binding > legacy `GuardrailPolicy.mode` > `XPARSE_GUARDRAIL_MODE`（預設 `enforce`）。

**為何常見部署「像沒在跑」**：Gateway 預設關閉 guardrail；僅在 IAM 建 policy 而不開 env，或設 `shadow` 模式，都不會對使用者可見地「擋住」請求。

---

## 附錄

### A. 環境變數速查


| 環境變數                                  | 預設值                             | 說明                       |
| ------------------------------------- | ------------------------------- | ------------------------ |
| `GATEWAY_PORT`                        | `8000`                          | Gateway 監聽端口             |
| `GATEWAY_IAM_MODE`                    | `direct`                        | IAM 模式：`direct` 或 `http` |
| `GATEWAY_IAM_URL`                     | `http://xparse-iam:8010`        | IAM URL（http 模式）         |
| `BUSTREAM_IAM_ENABLED`                | `true`                          | 啟用 IAM 認證                |
| `BUSTREAM_AUTH_ENABLED`               | `false`                         | 啟用認證（生產應設 `true`）        |
| `BUSTREAM_RATE_LIMIT_ENABLED`         | `true`                          | 啟用速率限制                   |
| `RESOURCE_MANAGER_URL`                | `http://localhost:8020`         | Resource Manager URL     |
| `RESOURCE_MANAGER_ACQUIRE_TIMEOUT_MS` | `30000`                         | 租賃取得逾時                   |
| `XPARSE_GUARDRAIL_ENABLED`            | `false`                         | 啟用 GuardrailEnforcer（§5.8） |
| `XPARSE_GUARDRAIL_SIDECAR_URL`        | `http://xparse-guardrails:8400` | NeMo sidecar URL（content filter / PII） |
| `XPARSE_GUARDRAIL_MODE`               | `enforce`                       | 全域預設模式：`enforce` 或 `shadow` |
| `XPARSE_GUARDRAIL_TIMEOUT_SEC`        | `5.0`                           | Sidecar HTTP 逾時（秒） |
| `XPARSE_QUALITY_GATE_ENABLED`         | `true`                          | 品質閘門（雙模型）                |
| `XPARSE_QUALITY_THRESHOLD`            | `0.7`                           | 品質閾值                     |
| `AUDIT_ENABLED`                       | `true`                          | 啟用稽核事件                   |
| `AUDIT_EVIDENCE_DIR`                  | `/var/audit/evidence`           | 稽核證據目錄                   |


### B. 關鍵原始碼位置


| 模組                                          | 路徑                                                          |
| ------------------------------------------- | ----------------------------------------------------------- |
| Gateway 應用入口                                | `bustream/gateway/app.py`                                   |
| Chat Completions                            | `bustream/gateway/routes/chat.py`                           |
| Embeddings / TTS / STT / Models / Responses | `bustream/gateway/routes/`                                  |
| Admin 端點                                    | `bustream/gateway/routes/admin.py`                          |
| Signals / Agent Tasks                       | `bustream/signals/router.py`, `bustream/agent/api/tasks.py` |
| StreamingManagerV3                          | `bustream/streaming/manager_v3.py`                          |
| Auth Handler                                | `bustream/gateway/auth_handler.py`                          |
| Admission Controller                        | `bustream/production/admission/controller.py`               |
| Guardrail Input Handler                     | `bustream/gateway/guardrail_handler.py`                     |
| Guardrail Enforcer                          | `bustream/gateway/guardrail_enforcer.py`                      |
| Resource Manager Client                     | `bustream/` 內 `ResourceManagerClient`                       |
| Audit Emitter                               | `bustream/audit/emit.py`                                    |


### C. 相關文件


| 文件                                             | 內容                                     |
| ---------------------------------------------- | -------------------------------------- |
| `[iam.md](./iam.md)`                           | IAM Inbound / Outbound；Gateway 驗證端點詳規  |
| `[resource_manager.md](./resource_manager.md)` | Layer 2 Admission；acquire / release 詳規 |
| `[audit.md](./audit.md)`                       | 稽核 Query API（前端 :8001）；事件 schema       |
| `[routing.md](./routing.md)`                   | 路由決策模組（Gateway 進程內，無獨立 HTTP 端口）        |


