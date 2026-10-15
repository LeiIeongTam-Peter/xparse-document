# Xparse Audit 系統技術文件

> **版本**：v0.7.1　|　**更新日期**：2026-05-31　|　**依據**：`3rd/xparse_audit`、`bustream/audit/`、`xparse_iam/`、`frontend/console-app/`

---

## 一、服務端口清單（Service Ports）

| 服務名稱 | 容器名稱 | 端口號碼 | 通訊協定 | 用途說明 |
|---------|---------|---------|---------|---------|
| **Audit Query API** | `xparse-audit` | `8001` | HTTP | 審計事件查詢、統計、證據包管理 (FastAPI) |
| **IAM 服務** | `xparse-iam` | `8010` | HTTP | 身份驗證、Token 驗證（Audit 認證端點） |
| **Gateway** | `xparse-gateway` | `8000` | HTTP | LLM API 閘道，是 Audit 事件的主要發射來源 |
| **PostgreSQL（Audit）** | `xparse-db` | `5432` | TCP | 存放證據包中繼資料（`evidence_package_records` 表） |
| **OTel Collector / Tempo** | — | 由 `OTEL_EXPORTER_OTLP_ENDPOINT` 設定 | OTLP（HTTP 或 gRPC） | 接收 Gateway 的 OpenTelemetry Span，用於 Per-User 用量關聯（ADR-141） |
| **Evidence 本機存儲** | — | 路徑：`/var/audit/evidence` | 本機檔案系統 | JSONL append-only 審計證據檔，旋轉大小 100 MB |

### 環境變數快速參照

| 環境變數 | 預設值 | 說明 |
|---------|-------|------|
| `AUDIT_API_PORT` | `8001` | Audit Query API 監聽端口 |
| `AUDIT_DB_PORT` | `5432` | PostgreSQL 端口 |
| `IAM_VALIDATE_URL` | `http://xparse-iam:8010/iam/auth/validate` | Audit 認證驗證端點 |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | OTel Collector 端點 |
| `AUDIT_EVIDENCE_DIR` | `/var/audit/evidence` | JSONL 事件儲存目錄 |
| `AUDIT_EVIDENCE_ROTATE_SIZE_MB` | `100` | 單檔旋轉大小 |
| `AUDIT_S3_BUCKET` | `xparse-audit` | S3 備份桶名（選用） |

---

## 二、前端 API 清單（Frontend APIs）

> **發起方**：`frontend/console-app/src/services/auditApi.ts`  
> **基址**：`${API_BASE}/audit`（由 `src/config/api.ts` 的 `auditUrl` 設定）  
> **認證**：所有端點均需 `Authorization: Bearer <token>`（呼叫 `getApiKey()`）

### 2.1 事件查詢（Events）

| HTTP 方法 | 端點路徑 | 目標服務 | 功能說明 |
|----------|---------|---------|---------|
| `GET` | `/audit/events` | Audit API | 查詢審計事件（支援 `event_type`、`tenant_id`、`trace_id`、`start_time`、`end_time`、`application_codes`、`limit`、`offset` 篩選） |
| `POST` | `/audit/events/query` | Audit API | 以 JSON body 查詢審計事件，功能同 GET 版本但支援更複雜的 request body |
| `GET` | `/audit/events/types` | Audit API | 取得當前使用者角色可存取的事件類型前綴 |
| `GET` | `/audit/events/trace/{traceId}` | Audit API | 取得特定 Trace 的所有審計事件（用於請求追蹤視圖） |
| `GET` | `/audit/events/{eventId}` | Audit API | 取得單一審計事件的完整詳情 |

### 2.2 統計數據（Statistics）

| HTTP 方法 | 端點路徑 | 目標服務 | 功能說明 |
|----------|---------|---------|---------|
| `GET` | `/audit/stats/summary` | Audit API | 取得統計摘要（總事件數、請求數、錯誤數、Token 消耗、延遲、預估成本），支援時間區間比較 |
| `GET` | `/audit/stats/time-series` | Audit API | 取得時間序列資料（`metric` 可為 `requests`、`tokens`、`errors`、`latency`），用於儀表板折線圖 |
| `GET` | `/audit/stats/distribution` | Audit API | 取得事件類型分佈統計，用於圓餅圖 |
| `GET` | `/audit/stats/top-applications` | Audit API | 取得按請求量排名的應用程式清單（`limit` 1–100） |

### 2.3 證據包（Evidence Packages）

| HTTP 方法 | 端點路徑 | 目標服務 | 功能說明 |
|----------|---------|---------|---------|
| `POST` | `/audit/evidence/packages` | Audit API | 建立證據包請求（202 Accepted，非同步生成），需提供 `tenant_id`、`start_time`、`end_time`、`reason`（5–500 字元） |
| `GET` | `/audit/evidence/packages` | Audit API | 列出所有證據包（支援 `limit`、`offset`、`status` 篩選） |
| `GET` | `/audit/evidence/packages/{packageId}/download` | Audit API | 下載證據包 ZIP 檔案（含完整性清單與雜湊值） |

### 2.4 使用量追蹤（Usage）

| HTTP 方法 | 端點路徑 | 目標服務 | 功能說明 |
|----------|---------|---------|---------|
| `GET` | `/audit/usage/per-user` | Audit API | 取得每位使用者的 LLM 使用統計（請求數、Token 消耗）；資料來源為 Sidecar-Gateway Span 關聯（ADR-141 Phase 1） |
| `GET` | `/audit/usage/per-user/time-series` | Audit API | 取得單一使用者的 Token 消耗時間序列 |
| `GET` | `/audit/usage/correlation-health` | Audit API | 取得 Tempo/Sidecar 關聯機制健康指標 |

### 2.5 健康檢查

| HTTP 方法 | 端點路徑 | 目標服務 | 功能說明 |
|----------|---------|---------|---------|
| `GET` | `/audit/health` | Audit API | 檢查 Audit 服務可用性，前端每 30 秒輪詢一次，3 次失敗後停止自動重試 |

### 2.6 前端 React Hooks 對照

| Hook（`src/hooks/useAudit.ts`） | 呼叫的 API | 使用頁面 |
|-------------------------------|-----------|---------|
| `useAuditHealth()` | `GET /health` | `AuditLog.tsx`、`AuditTab.tsx` |
| `useAuditEvents(filters)` | `GET /events` | `AuditLog.tsx`、`AuditTab.tsx` |
| `useTraceEvents(traceId)` | `GET /events/trace/{traceId}` | `AuditLog.tsx`、`AuditTab.tsx` |
| `useEventTypes()` | `GET /events/types` | `AuditLog.tsx` |
| `useAuditStats(filters)` | `GET /stats/summary` | `AuditTab.tsx` |
| `useTimeSeries(metric, range)` | `GET /stats/time-series` | `AuditLog.tsx` |
| `useEventDistribution(filters)` | `GET /stats/distribution` | `AuditLog.tsx` |
| `useTopApplications(params)` | `GET /stats/top-applications` | `AuditLog.tsx` |
| `useEvidencePackages()` | `GET /evidence/packages` | `AuditLog.tsx` |
| `useEvidencePackageMutations()` | `POST /evidence/packages`、`GET /evidence/packages/{id}/download` | `AuditLog.tsx` |
| `usePerUserUsage(params)` | `GET /usage/per-user` | 使用量分析頁面 |
| `useDashboardData(timeRange)` | 組合 stats + time-series + distribution | `AuditLog.tsx` |

---

## 三、後端 API 清單（Backend APIs）

### 3.1 Audit Query API（`xparse-audit`，Port 8001）

> **框架**：FastAPI　|　**源碼**：`3rd/xparse_audit/src/audit/api/routers/`

#### Events Router（`/events`）

| HTTP 方法 | 端點路徑 | 所屬服務 | 功能說明 | 呼叫來源 |
|----------|---------|---------|---------|---------|
| `POST` | `/events/query` | xparse-audit | 查詢審計事件，以 JSON body 傳遞篩選條件；結果依呼叫者角色進行重新過濾與遮蔽（ADR-007） | 前端 Console、合規工具 |
| `GET` | `/events` | xparse-audit | 以 Query String 查詢審計事件（`POST /events/query` 的便利版） | 前端 Console |
| `GET` | `/events/types` | xparse-audit | 列出呼叫者角色可存取的事件類型前綴及 raw data 存取權限 | 前端 Console |
| `GET` | `/events/trace/{trace_id}` | xparse-audit | 取得特定 Trace 的所有事件，計算 span_count 與 duration_ms | 前端 Console |
| `GET` | `/events/{event_id}` | xparse-audit | 依事件 ID 取得單一事件（目前採全表掃描，Production 應有直接索引） | 前端 Console |

#### Stats Router（`/stats`）

| HTTP 方法 | 端點路徑 | 所屬服務 | 功能說明 | 呼叫來源 |
|----------|---------|---------|---------|---------|
| `GET` | `/stats/summary` | xparse-audit | 彙總統計（`total_events`、`requests`、`errors`、`tokens`、`latency_p50/p99`、`cost_estimated`），支援 `1h/6h/24h/7d/30d` 時間區間 | 前端 Console |
| `GET` | `/stats/time-series` | xparse-audit | 按時間序列回傳指定指標（`requests`、`tokens`、`errors`、`latency`、`ttft`、`tps`） | 前端 Console |
| `GET` | `/stats/distribution` | xparse-audit | 事件類型分佈統計 | 前端 Console |
| `GET` | `/stats/top-applications` | xparse-audit | 依請求量排名應用，回傳 requests、errors、tokens、estimated_cost | 前端 Console |

#### Evidence Router（`/evidence`）

| HTTP 方法 | 端點路徑 | 所屬服務 | 功能說明 | 呼叫來源 |
|----------|---------|---------|---------|---------|
| `POST` | `/evidence/packages` | xparse-audit | 建立證據包（202 Accepted），後台非同步執行 `_generate_package_with_assembler()`；計算 `bundle_hash` 與 `manifest_hash` | 前端 Console（COMPLIANCE/SYSTEM 角色） |
| `GET` | `/evidence/packages` | xparse-audit | 列出所有證據包（`limit`、`offset`、`status` 篩選） | 前端 Console |
| `GET` | `/evidence/packages/{package_id}` | xparse-audit | 取得證據包元數據（狀態查詢：`pending → generating → ready`） | 前端 Console |
| `GET` | `/evidence/packages/{package_id}/download` | xparse-audit | 以 `StreamingResponse` 串流下載 ZIP 封存（含 JSON 事件、manifest、hash proofs） | 前端 Console、合規系統 |
| `DELETE` | `/evidence/packages/{package_id}` | xparse-audit | 刪除證據包 | 前端 Console（COMPLIANCE/SYSTEM 角色） |

#### Usage Router（`/usage`）

| HTTP 方法 | 端點路徑 | 所屬服務 | 功能說明 | 呼叫來源 |
|----------|---------|---------|---------|---------|
| `GET` | `/usage/per-user` | xparse-audit | 每位使用者 LLM 使用統計（`total_requests`、`total_input_tokens`、`total_output_tokens`），透過 Tempo Span 關聯計算（ADR-141 Phase 1） | 前端 Console |
| `GET` | `/usage/per-user/time-series` | xparse-audit | 單一使用者 Token 消耗時間序列 | 前端 Console |
| `GET` | `/usage/correlation-health` | xparse-audit | Sidecar/Tempo 關聯機制健康診斷指標 | 前端 Console、SRE 監控 |

#### Health Router（`/health`）

| HTTP 方法 | 端點路徑 | 所屬服務 | 功能說明 | 呼叫來源 |
|----------|---------|---------|---------|---------|
| `GET` | `/health` | xparse-audit | 回傳 `{status, version, timestamp, components}`；檢查 EventStore、DB 連線等元件狀態 | 前端 Console（每 30 秒）、Docker healthcheck |
| `GET` | `/health/live` | xparse-audit | Kubernetes Liveness Probe，回傳 `{status: "alive"}` | K8s、容器編排 |
| `GET` | `/health/ready` | xparse-audit | Kubernetes Readiness Probe，任一元件不健康則回 503 | K8s、容器編排 |

#### Diagnostics Router（`/diagnostics`）

| HTTP 方法 | 端點路徑 | 所屬服務 | 功能說明 | 呼叫來源 |
|----------|---------|---------|---------|---------|
| `GET` | `/diagnostics/store` | xparse-audit | 診斷 JSONL EventStore 狀態（`reload_count`、`events_loaded`、`per_file_positions`、`per_file_errors`），用於偵測無聲失敗 | SRE（需 COMPLIANCE / SRE / SYSTEM 角色） |

#### Root Endpoint

| HTTP 方法 | 端點路徑 | 所屬服務 | 功能說明 | 呼叫來源 |
|----------|---------|---------|---------|---------|
| `GET` | `/` | xparse-audit | 回傳服務基本資訊（`name`、`version`、`docs`、`openapi`） | 探索性工具、健康確認 |

---

### 3.2 IAM 審計發射介面（非 HTTP，內部呼叫）

> **源碼**：`xparse_iam/xparse_iam/api/quota_audit.py`、`xparse_iam/xparse_iam/api/oidc_audit.py`

| 函式 / 介面 | 所屬服務 | 功能說明 | 呼叫來源 |
|------------|---------|---------|---------|
| `emit_quota_event(event_type, actor_id, tenant_uuid, details)` | xparse-iam | 發射 Quota 操作審計事件（`quota.node_allocation.created/updated/deleted`）；失敗僅記錄 Warning，不中斷主流程 | IAM 配額管理 Use Case |
| `emit_oidc_event(event_type, issuer, subject, email, tenant_uuid, ...)` | xparse-iam | 發射 OIDC Token-Exchange 審計事件（10+ 種事件型別）；`subject`/`email` 預設遮蔽（`verbose=False`） | IAM OIDC 認證流程 |

**OIDC 審計事件型別**（`OIDCAuditEventType`）：

| 事件型別 | 說明 |
|---------|------|
| `oidc.token_verified` | Token 驗證成功 |
| `oidc.mapping_lookup` | OIDC Mapping 查詢 |
| `oidc.tenant_resolved` | 租戶解析 |
| `oidc.session_issued` | Session 簽發 |
| `oidc.login_rejected` | 登入拒絕 |
| `oidc.mapping_created` | Mapping 建立 |
| `oidc.group_resolved` / `oidc.role_resolved` | 群組 / 角色解析 |
| `oidc.platform_admin_downgraded` | 平台管理員降級 |
| `oidc.mapping_reactivated` / `oidc.mapping_emergency_unlocked` | Mapping 恢復 / 緊急解鎖 |
| `oidc.tenant_group_binding.created` / `.deleted` | 租戶群組繫結操作 |
| `oidc.mapping_tenant_succeeded` / `oidc.mapping_offboarded` | Mapping 租戶轉移 / 下線 |
| `oidc.layer_conflict_detected` | 層級衝突偵測 |

---

### 3.3 Gateway 審計發射（BuStream，非 HTTP，內部呼叫）

> **源碼**：`bustream/audit/emit.py`、`bustream/audit/schema.py`

**主要發射介面**：`AuditEmitter.emit(event_type, data, force=False)`

| 事件型別 | 發射位置 | 說明 |
|---------|---------|------|
| `REQUEST_RECEIVED` | `streaming/manager_v3_workers.py` | 請求抵達 Gateway |
| `ADMISSION_DECIDED` | `production/admission/` | 准入決定（execute_now / queued / rejected） |
| `REQUEST_QUEUED` / `REQUEST_DEQUEUED` | `production/admission/` | 請求進出佇列 |
| `EXECUTION_STARTED` | `streaming/manager_v3_workers.py` | 執行開始 |
| `EXECUTION_COMPLETED` | `streaming/manager_v3_workers.py` | 執行完成（含 Token 指標、延遲） |
| `EXECUTION_FAILED` | `streaming/manager_v3_workers.py` | 執行失敗 |
| `REQUEST_REJECTED` | `production/admission/` | 請求被拒（速率限制、佇列溢出） |
| `QUEUE_TIMEOUT` | `production/admission/` | 佇列等待逾時 |
| `RATE_LIMIT_APPLIED` / `CONCURRENCY_EXHAUSTED` | `production/admission/` | 速率限制 / 並行上限觸發 |
| `CREDENTIAL_RESOLVED` / `CREDENTIAL_RESOLUTION_FAILED` | `production/key_resolver.py` | 認證解析結果 |
| `GUARDRAIL_INPUT_CHECK` / `GUARDRAIL_OUTPUT_CHECK` | Gateway guardrail 模組 | 護欄檢查（ADR-139） |
| `GUARDRAIL_BLOCKED` / `GUARDRAIL_ERROR` | Gateway guardrail 模組 | 護欄阻擋 / 錯誤 |
| `TOOL_CALL_DETECTED` | `streaming/manager_v3_workers.py` | 工具呼叫偵測 |
| `STREAMING_PHASE_CHANGED` | `streaming/manager_v3_workers.py` | 串流階段變更 |
| `PROVIDER_FALLBACK` | Gateway routing 模組 | Provider 後備切換 |
| `RESOURCE_QUEUE_DEGRADED` | `production/admission/` | 資源管理器連線異常（SPEC-086） |
| `CACHE_HIT` | `streaming/` | 快取命中 |

---

### 3.4 角色與存取控制

| 角色 | 可存取事件前綴 | 特殊能力 | 租戶範圍限制 |
|-----|-------------|---------|------------|
| `COMPLIANCE` | 所有（`audit.*`） | 可建立 / 下載證據包 | 無（全租戶） |
| `SYSTEM` | 所有 | 可建立 / 下載證據包 | 無 |
| `SRE` | `system.*`、`observability.*` | 可存取 `/diagnostics/store` | 無 |
| `SECURITY` | `identity.*`、`policy.*`、`access.*` | — | 無 |
| `BILLING` | `execution.*`、`observability.*` | — | 無 |
| `APP_OWNER` | `execution.*` | 可下載自己租戶的證據包 | **是**（限自身租戶） |

---

## 四、工作流程（Workflows）

### Workflow A：LLM 請求審計事件生命週期

```
發起方：Client（呼叫 LLM API）
接收方：Provider（OpenAI / Azure / vLLM）
```

```
┌─────────────────────────────────────────────────────────────────────┐
│  Client 發送 LLM 請求                                               │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  [Gateway] 收到請求                                                  │
│  emit(REQUEST_RECEIVED, {request_id, tenant_id, model, ...})        │
│    ├─ → OTel Tracer (OTLP → Tempo，受取樣率影響)                   │
│    └─ → Evidence Bridge → JSONL /var/audit/evidence（100% 寫入）    │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  [IAM] Token 驗證                                                   │
│  POST http://xparse-iam:8010/iam/auth/validate                      │
│  emit_oidc_event(oidc.token_verified, ...)  ← IAM 內部              │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  [Gateway] 准入控制決策                                              │
│  emit(ADMISSION_DECIDED, {decision: execute_now | queued | reject}) │
│                                                                      │
│  [若被佇列] emit(REQUEST_QUEUED, {queue_position, queue_depth})     │
│  [若超時]  emit(QUEUE_TIMEOUT)                                      │
│  [若被拒]  emit(REQUEST_REJECTED) → 回應 429/503                   │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ (execute_now 路徑)
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  [Gateway] 認證解析 & 護欄輸入檢查                                   │
│  emit(CREDENTIAL_RESOLVED, {credential_uuid, key_version})          │
│  emit(GUARDRAIL_INPUT_CHECK, {guardrail_id, confidence_score})      │
│  [若阻擋] emit(GUARDRAIL_BLOCKED) → 回應 400                        │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  [Gateway] 執行開始 → 呼叫 Provider                                  │
│  emit(EXECUTION_STARTED, {model, endpoint, streaming})              │
│                                                                      │
│  [串流中] emit(STREAMING_PHASE_CHANGED)                             │
│  [工具呼叫] emit(TOOL_CALL_DETECTED)                                │
│  [快取命中] emit(CACHE_HIT)                                         │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  [Gateway] 執行完成 & 護欄輸出檢查                                   │
│  emit(GUARDRAIL_OUTPUT_CHECK, {confidence_score})                   │
│  emit(EXECUTION_COMPLETED, {                                        │
│    execution_duration_ms,                                           │
│    input_tokens, output_tokens, total_tokens,                       │
│    ttft_ms, streaming_completed                                     │
│  })                                                                  │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
                     SSE 串流回應 → Client
```

**雙平面寫入架構（ADR-041）**：

```
AuditEmitter.emit()
  ├─ OTel Tracer → OTLP Exporter → Tempo
  │   └─ 受 AUDIT_SAMPLING_RATE 影響（預設 1.0）
  │   └─ 用途：Observability 監控、Per-User 使用量關聯（ADR-141）
  │
  └─ Evidence Bridge（XparseBridge）
      ├─ 有界隊列（AUDIT_EVIDENCE_QUEUE_SIZE=10000）
      ├─ JSONL EventStore → /var/audit/evidence/
      ├─ PostgreSQL PackageStore（evidence_package_records）
      └─ S3 Sink（選用，AUDIT_S3_ENABLED）
          └─ 100% 寫入，不受取樣影響，用於合規審計軌跡
```

---

### Workflow B：證據包匯出（合規流程）

```
發起方：合規人員（Console 前端）
接收方：xparse-audit（Port 8001）
```

```
步驟 1 — 建立請求
  Client  →  POST /evidence/packages
  請求體：{
    tenant_id: "tenant-uuid",
    start_time: "2026-05-01T00:00:00Z",
    end_time: "2026-05-31T23:59:59Z",
    reason: "monthly_compliance_audit",
    event_types: ["audit.*"],
    include_raw_data: false
  }
  回應：202 Accepted, {package_id: "pkg-xxx", status: "pending"}

步驟 2 — 後台非同步生成（_generate_package_with_assembler）
  ① 建立 DisclosureScope（時間範圍、租戶 ID、事件類型）
  ② 從 JSONL EventStore 收集符合條件的事件
  ③ 計算 bundle_hash = H(所有事件)
  ④ 計算 manifest_hash = H(bundle 元數據)
  ⑤ 將事件序列化為 JSON 檔案
  ⑥ 建立 ZIP 封存（含事件 JSON + manifest + hash proofs）
  ⑦ 更新 PackageStore：status="ready"

步驟 3 — 輪詢狀態
  Client  →  GET /evidence/packages/{package_id}
  回應：{status: "pending" | "generating" | "ready" | "failed"}

步驟 4 — 下載
  Client  →  GET /evidence/packages/{package_id}/download
  回應：StreamingResponse（ZIP 檔案）
  ZIP 內容：
    ├─ events_YYYYMMDD_HHMMSS.json   ← 完整事件清單
    ├─ manifest.json                  ← 元數據 + 事件計數
    └─ integrity.json                 ← bundle_hash + manifest_hash
```

---

### Workflow C：Per-User 使用量關聯（ADR-141 Phase 1）

```
發起方：Console 前端（使用量分析頁面）
接收方：xparse-audit / Tempo
```

```
步驟 1 — Gateway 發射 Span
  [Gateway] 每個請求發送 OTel Span → OTLP → Tempo
  Span 包含：user_id、model、input_tokens、output_tokens

步驟 2 — Sidecar 捕獲
  [Sidecar] OpenTelemetry Instrumentation → 附加 Span metadata → Tempo

步驟 3 — 前端查詢
  Client  →  GET /usage/per-user?time_range=7d&tenant_id=xxx
  [Audit API] CorrelationEngine.correlate()
    → 查詢 Tempo 中的 user_id + model Span
    → 依使用者彙總（requests、input_tokens、output_tokens）
  回應：{users: [{user_id, total_requests, input_tokens, output_tokens}]}

步驟 4 — 關聯健康檢查
  Client  →  GET /usage/correlation-health
  回應：{correlation_rate, missing_spans, tempo_latency_ms}
```

---

### Workflow D：IAM 治理事件審計

```
發起方：IAM 內部業務邏輯（Use Cases）
接收方：Audit SDK / 結構化日誌
```

```
場景 D1 — OIDC 登入流程
  [IAM] 收到 OIDC Token Exchange 請求
    ↓
  emit_oidc_event(oidc.token_verified, issuer, subject="***masked***", tenant_uuid)
    ↓ (mapping lookup)
  emit_oidc_event(oidc.mapping_lookup, mapping_uuid)
    ↓ (tenant resolved)
  emit_oidc_event(oidc.tenant_resolved, tenant_uuid)
    ↓ (session issued)
  emit_oidc_event(oidc.session_issued, ...)
  → 若任一步驟失敗：
    emit_oidc_event(oidc.login_rejected, reason="...")
  
  設計保證：
  - subject/email 預設遮蔽（verbose=False）
  - 任何 emit 失敗只記錄 Warning，不中斷主流程（ADR-010）

場景 D2 — Quota 操作
  [IAM] 建立 Node Allocation
    ↓
  emit_quota_event(
    event_type="quota.node_allocation.created",
    actor_id=actor_uuid,
    tenant_uuid=tenant_uuid,
    details={"before": null, "after": {"cpu": 4, "memory": "8Gi"}}
  )
  → Phase 1：事件輸出至結構化日誌（logger.info with audit_event context）
  → Phase 2：直接接入 bustream.audit.emit()（一個 switch 切換）
```

---

### Workflow E：前端儀表板資料載入

```
發起方：Console 前端（AuditLog.tsx）
接收方：xparse-audit（Port 8001）
```

```
頁面載入
  │
  ├─ GET /health             → 確認 Audit 服務可用
  │   └─ 不可用：切換至 Demo 資料模式（mockAuditEvents）
  │
  ├─ GET /events/types       → 取得當前角色可存取的事件類型前綴
  │
  ├─ GET /stats/summary      → 載入統計摘要卡片
  │
  ├─ GET /stats/time-series  → 載入請求趨勢折線圖
  │
  ├─ GET /stats/distribution → 載入事件類型分佈圓餅圖
  │
  └─ GET /events             → 載入初始事件列表（limit=50, offset=0）

使用者互動
  │
  ├─ 篩選條件變更 → 重新 GET /events（帶新的 filters）
  │
  ├─ 滾動至底部  → GET /events（offset += limit，無限滾動）
  │
  ├─ 點擊事件列  → GET /events/{event_id} 顯示詳情
  │
  ├─ 點擊 Trace  → GET /events/trace/{trace_id} 顯示 Trace 視圖
  │
  └─ 建立證據包
      ├─ POST /evidence/packages（202 Accepted）
      ├─ 輪詢 GET /evidence/packages/{id}（直到 status=ready）
      └─ GET /evidence/packages/{id}/download（下載 ZIP）

錯誤處理
  - 3 次連續 API 失敗 → 停止自動重試，顯示手動重試按鈕
  - 401 回應 → 不觸發 IAM session 過期（Audit 獨立認證）
  - Audit 不可用 → 自動降級至 Demo 資料，功能不中斷
```

---

## 附錄：資料保留政策

| 事件類別 | 保留期限 | 說明 |
|---------|---------|------|
| Runtime 事件（`audit.execution.*`） | 14–30 天 | 高頻率運維資料 |
| Governance 事件（`audit.policy.*`、`audit.identity.*`） | 90 天 | 治理相關 |
| Compliance 事件（`audit.compliance.*`） | 365 天 | 合規審計軌跡 |
| Legal Hold | 永久 | 法律保留優先於所有 retention 規則 |

## 附錄：Audit SDK 設計不變量（Design Invariants）

| 不變量 | 參考 ADR | 說明 |
|--------|---------|------|
| **Non-blocking** | ADR-010 | Audit 絕不阻塞主請求路徑，失敗時靜默降級 |
| **Bounded Queue** | ADR-010 | Evidence Bridge 使用有界隊列（10,000 筆），滿時發出 `RESOURCE_QUEUE_DEGRADED` 事件 |
| **Append-only** | ADR-001 | 事件不可修改、不可刪除（Legal Hold 除外） |
| **Trace-driven** | ADR-003 / ADR-009 | 所有事件必須攜帶 `trace_id`，與 OTel Span 關聯 |
| **No Plaintext** | ADR-011 | Audit 索引不含敏感明文（Phase 3+ 啟用 hash-only 模式） |
| **Export Manifest** | ADR-012 | 所有證據匯出必附完整性清單（`bundle_hash`、`manifest_hash`） |
| **Dual-write** | ADR-041 | OTel（受取樣影響）與 Evidence Bridge（100% 寫入）並行，各自用途不同 |
