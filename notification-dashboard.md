# Notification + Dashboard 後端工作流程

**最後更新：** 2026-07-08  
**範圍：** PRD-215 audit-derived dashboard + in-app notification backend，以及 dashboard 將複用的 ADR-264 usage/cost rollup。

這份文件說明目前的工作流程、feature 如何運作、涉及哪些資料表、這些資料表彼此的依賴關係，以及後續還需要完成的工作。

---

## 1. 目前架構

這個 feature 有一個 source of truth，後面分成三條 derived read path：

```text
Audit producers
  Gateway / IAM / Fleet / scheduler / resource producers
        |
        v
Evidence plane
  append-only JSONL/S3 style audit evidence
  source of truth, not a dashboard table
        |
        v
Postgres query projection
  audit_events
        |
        +--> Dashboard summary path
        |      DashboardRollupWorker
        |      -> audit_dashboard_rollups
        |      -> audit_dashboard_rollup_watermarks
        |      -> GET /dashboard/surfaces
        |      -> GET /dashboard/summary
        |
        +--> Usage/cost path
        |      BackgroundRollupWorker
        |      -> usage_cost_rollup
        |      -> rollup_cursor
        |      -> /stats/summary and /stats/top-*
        |      -> GET /dashboard/usage-cost
        |
        +--> Notification path
               AlertCandidateWorker
               -> audit_alert_candidates
               -> GET /internal/alert-candidates
               -> IAM puller
               -> notification_outbox
               -> notification_inbox
               -> Console polling /iam/notifications*
```

重要邊界：

- `audit_events`、dashboard rollups、usage/cost rollups、alert candidates 都是從 evidence 推導出來的 derived data。
- `notification_outbox` 與 `notification_inbox` 是 IAM 擁有的 delivery/read-state tables。
- Gateway execution 與 IAM validate 不依賴 dashboard rollups 或 notification delivery。
- Console 不應直接讀 database tables，只能讀 HTTP APIs。

---

## 2. Dashboard 工作流程

### 2.1 Surface 探索

Console 會先向 audit 詢問目前角色可以看到哪些 dashboard surfaces：

```text
GET /dashboard/surfaces
```

Audit service 會解析：

1. `AuthContext`
2. normalized product role，例如 `system_admin`、`tenant_admin`、`group_admin`、`tenant_user`
3. `dashboard_surface_catalog`
4. `role_visibility_policy`

未知角色或 catalog 未接線時，一律 fail closed 回 `403`。

目前角色行為：

- `system_admin` 可以看到所有 enabled surfaces。
- `tenant_admin` 可以看到 tenant-scoped surfaces。
- `group_admin` 可以看到 group/application-scoped surfaces，但不含 fleet。
- `tenant_auditor` 可以看到 governance/risk surfaces。
- `group_developer` 可以看到 app-scoped operational surfaces。
- `app_user` 會 normalize 成 `tenant_user`。
- `tenant_user` 目前只看得到 `dashboard.usage_cost`，而且是 `self` scope。

### 2.2 Summary 指標

Dashboard summary endpoint 是：

```text
GET /dashboard/summary
```

它只讀 `audit_dashboard_rollups`，不掃 raw audit events。

Request path：

```text
AuthContext
  -> normalize product role
  -> resolve visible surfaces
  -> remove surfaces without dashboard summary metric_ids
  -> enforce scope ceiling
  -> read audit_dashboard_rollups
  -> return metrics + freshness metadata
```

Freshness 行為：

- Rollup store 不存在：回 explicit degraded response，不 fallback 掃 raw events。
- Rollups 過期：response 會帶 stale/degraded metadata。
- Valid rollup 沒資料：metrics 可以是空，但原因必須明確。

目前 guard：

- `/dashboard/summary?surface_id=dashboard.usage_cost` 會回 `400`。
- 這是刻意設計。`dashboard.usage_cost` 沒有 `audit_dashboard_rollups` summary metrics。
- 它不能回 `200` 加空 metrics，因為那看起來像「成功查詢且 usage 為 0」。

### 2.3 Dashboard Rollup 投影

Dashboard projector 會讀 `audit_events`，把事件放進 deterministic buckets，然後把 absolute metric values upsert 到 `audit_dashboard_rollups`。

目前特性：

- 支援 `5m`、`1h`、`1d` buckets。
- 會寫 tenant/group/application slices。
- 支援 scalar metrics 與 `dim_value` breakdown metrics。
- Upsert 的是 absolute bucket values，所以 replay 具備 idempotency。
- 會維護 `audit_dashboard_rollup_watermarks`。
- 如果 configured scan limit 被超過，會在寫入 partial state 前 fail loud。

---

## 3. Usage/Cost 工作流程

Usage/cost 已存在，但目前不是由 `/dashboard/summary` 提供。

目前 usage/cost path：

```text
audit.execution.completed events
  with input_tokens / output_tokens / total_tokens
  with price_in / price_out snapshot
        |
        v
audit_events
        |
        +--> SQL pushdown aggregate for fresh/narrow/cross-filtered reads
        |
        +--> ADR-264 usage/cost rollup
              usage_cost_rollup
              rollup_cursor
```

Cost 公式：

```text
input_tokens  = payload.input_tokens or payload.tokens_in
output_tokens = payload.output_tokens or payload.tokens_out
total_tokens  = payload.total_tokens or input_tokens + output_tokens

cost_in       = input_tokens * price_in
cost_out      = output_tokens * price_out
cost_total    = cost_in + cost_out
unpriced_count = completed events where both price_in and price_out are absent
```

規則：

- `price_in` 與 `price_out` 是 completed event 上的 price-at-time-of-use snapshots。
- 缺 price 不會被當作 0 計價。
- 缺 price 會累加到 `unpriced_count`。
- `estimated_cost` 是 display compatibility field；backend 上 `cost_total` 更清楚。

目前 HTTP surfaces：

- `/stats/summary` 從 events 計算 summary usage/cost。
- `/stats/top-keys` 回傳 by API key 的 usage/cost。
- `/stats/top-models` 回傳 by model 的 usage/cost。
- `/stats/top-credentials` 透過 trace join，把 usage 歸因到 provider credential。
- `/dashboard/usage-cost` 回傳 dashboard 專用 exact totals，以及 by API key、model、application、group、provider credential 的 top-N breakdown。

Dashboard-specific endpoint：

- `dashboard.usage_cost` 在 catalog 中可見，對應 `GET /dashboard/usage-cost`。
- 這條 endpoint 複用既有 usage/cost aggregation logic，不把 usage/cost metrics 塞進 `audit_dashboard_rollups`。
- Totals 使用 non-dimensional aggregate，不能用 top-N breakdown 加總，避免 breakdown limit 截斷總數。
- Console cost-usage dashboard 應優先讀 `/audit/dashboard/usage-cost`，不要再用 `/audit/stats/summary` + `/audit/stats/top-*` 拼 dashboard usage/cost。

---

## 4. Notification 工作流程

### 4.1 Audit 側 Candidate 投影

Notification 從 audit 開始，不是從 IAM 開始。

```text
notification_rule_catalog
  enabled rules
        |
        v
AlertCandidateWorker
  reads audit_events
  evaluates event-pattern / threshold rules
        |
        v
audit_alert_candidates
```

Alert candidate 代表：

- 發生了某件事
- 有 rule match
- 這個 audience strategy 可能需要知道

Alert candidate 不代表：

- final recipients 已經解析完成
- notification rows 已經建立
- user 已經讀過任何東西

Candidate idempotency：

- `candidate_id` 由 `dedupe_key` deterministic 產生。
- `dedupe_key` 是 unique。
- 重新 project 同一份 evidence 不會產生 duplicate candidates。

Candidate cursor 行為：

- Internal API 現在使用基於 `(created_at, dedupe_key)` 的 v2 opaque cursor。
- 這可避免相同 `created_at` 的 candidates 被跳過。

### 4.2 內部 Candidate API

IAM 透過 HTTP 讀 candidates：

```text
GET /internal/alert-candidates
```

它使用：

- service-account authentication
- optional `tenant_uuid`
- `limit`
- `since` cursor

IAM 不直接讀 audit DB tables。

### 4.3 IAM Puller

IAM 執行：

```text
python manage.py enqueue_audit_alert_notifications --once
```

Puller 會：

1. 從 audit 拉 candidates。
2. 在任何 side effect 前驗證 candidate shape。
3. 把 `audience_hint` 解析成具體 OIDC subjects。
4. 產生 `notification_id = uuid5(dedupe_key)`。
5. 對每個 recipient/channel enqueue 一筆 outbox row。
6. 把 in-app outbox rows drain 成 inbox rows。

目前 safety 行為：

- Invalid candidate 會被計數並 skip，不會卡住整個 page。
- No audience 時 fail closed；沒有 broadcast fallback。
- Full pages 會用 bounded `max_pages` loop drain。
- Cursor 必須前進，否則 puller raise。
- 相同 timestamp 的 candidates 不會被跳過。

### 4.4 Console 輪詢

Console 讀 IAM notification APIs：

```text
GET  /iam/notifications/counts
GET  /iam/notifications/unread-count
GET  /iam/notifications?before=<cursor>&limit=<n>&status=all|unread|archived&event_type=<type>
POST /iam/notifications/{notification_id}/read
POST /iam/notifications/{notification_id}/archive
POST /iam/notifications/{notification_id}/unarchive
POST /iam/notifications/read-all
```

Contract：

- 只支援 polling。
- 沒有 SSE。
- 沒有 WebSocket。
- 沒有 browser long-polling。
- 每個 polling response 都帶 `poll_after_seconds: 60`。
- Inbox reads/writes 都以 caller 的 OIDC subject 與 tenant 為 scope。
- 缺 OIDC subject 時回 `403`，不是回 empty inbox。

---

## 5. 資料表

### 5.1 Audit 資料表

| 資料表                              | 擁有者         | 來源                                                 | 使用者                                                              | 用途                                                                                                                                                    |
| ----------------------------------- | -------------- | ---------------------------------------------------- | ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `audit_events`                      | `xparse_audit` | Evidence projector                                   | query APIs、dashboard projector、alert projector、usage/cost rollup | Audit evidence 的 derived Postgres JSONB projection，不是 source of truth。                                                                             |
| `audit_dashboard_rollups`           | `xparse_audit` | `DashboardRollupWorker` from `audit_events`          | `/dashboard/summary`                                                | 預聚合 dashboard summary buckets，維度包含 tenant/group/application、metric、family、`dim_value`、bucket size、bucket start。                           |
| `audit_dashboard_rollup_watermarks` | `xparse_audit` | `DashboardRollupWorker`                              | `/dashboard/summary` freshness                                      | 儲存 dashboard rollup projector progress 與 freshness。                                                                                                 |
| `dashboard_surface_catalog`         | `xparse_audit` | version-guarded seed/operator writes                 | `/dashboard/surfaces`、`/dashboard/summary`                         | 定義 enabled dashboard surfaces、`metric_ids`、allowed scopes、redaction profile、version。                                                             |
| `role_visibility_policy`            | `xparse_audit` | version-guarded seed/operator writes                 | `/dashboard/surfaces`、`/dashboard/summary`                         | 依 role 與 scope constraint grant/deny surface visibility。未知 role fail closed。                                                                      |
| `notification_rule_catalog`         | `xparse_audit` | version-guarded seed/operator writes                 | `AlertCandidateWorker`                                              | 定義 event-pattern/threshold/spike rules、severity、audience hint、channels、dedupe window、scope keys、comparator、max bucket age。                    |
| `audit_alert_candidates`            | `xparse_audit` | `AlertCandidateWorker`                               | `/internal/alert-candidates`、IAM puller                            | Derived、deduped alert candidates。包含 rule id、dedupe key、scope、severity、event refs、audience hint、redacted payload、created/expires timestamps。 |
| `usage_cost_rollup`                 | `xparse_audit` | ADR-264 `BackgroundRollupWorker` from `audit_events` | `/stats/top-*`、`/dashboard/usage-cost`                             | Hourly usage/cost rollup，依 `dim_type` 與 `dim_value` 聚合：API key、application、group、model。                                                       |
| `rollup_cursor`                     | `xparse_audit` | ADR-264 `BackgroundRollupWorker`                     | usage/cost rollup worker                                            | 儲存 `audit_events.seq` dirty-bucket recompute 的 seq cursor。                                                                                          |

### 5.2 IAM 資料表

| 資料表                | 擁有者       | 來源                                      | 使用者                          | 用途                                                                                                                                                       |
| --------------------- | ------------ | ----------------------------------------- | ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `notification_outbox` | `xparse_iam` | IAM alert puller / notification framework | delivery worker、in-app channel | Durable per-recipient/per-channel delivery row。擁有 delivery state machine，並用 `UNIQUE(notification_id, recipient_user_id, channel)` 保證 idempotency。 |
| `notification_inbox`  | `xparse_iam` | in-app channel from outbox                | Console polling APIs            | User-visible in-app notification rows。擁有 per-user/per-tenant read/archive state。                                                                       |

### 5.3 作為依賴的 Identity 資料

以下不是 PRD-215 tables，但 notification delivery 依賴它們：

| Table/Model                       | 擁有者       | 用途                                                                         |
| --------------------------------- | ------------ | ---------------------------------------------------------------------------- |
| `Tenant`                          | `xparse_iam` | 解析 global audit candidates 要送到哪些 platform-operator tenants。          |
| OIDC user/group membership models | `xparse_iam` | 從 `audience_hint` 解析 `tenant_admins`、`group_admins` 與 user recipients。 |
| IAM session/auth context          | `xparse_iam` | 提供 Console notification polling 需要的 OIDC subject 與 tenant scope。      |

---

## 6. 資料表依賴圖

```text
Evidence JSONL/S3
  -> audit_events

audit_events
  -> audit_dashboard_rollups
  -> audit_dashboard_rollup_watermarks

dashboard_surface_catalog
role_visibility_policy
  -> /dashboard/surfaces
  -> /dashboard/summary

audit_events
  -> usage_cost_rollup
  -> rollup_cursor
  -> /stats/top-*
  -> /dashboard/usage-cost

notification_rule_catalog
audit_events
  -> audit_alert_candidates
  -> /internal/alert-candidates
  -> IAM puller
  -> notification_outbox
  -> notification_inbox
  -> /iam/notifications*
```

Dependency rules：

- `audit_dashboard_rollups` 依賴 `audit_events`，不依賴 `usage_cost_rollup`。
- `usage_cost_rollup` 依賴 `audit_events`，不依賴 `audit_dashboard_rollups`。
- `audit_alert_candidates` 依賴 `notification_rule_catalog` 與 `audit_events`。
- `notification_outbox` 透過 HTTP 依賴 `audit_alert_candidates`，不是 direct DB access。
- `notification_inbox` 依賴 `notification_outbox`。
- Console 只依賴 APIs。

---

## 7. API 職責

| API                                 | 服務  | 讀取                                                                     | 寫入                  | 職責                                                       |
| ----------------------------------- | ----- | ------------------------------------------------------------------------ | --------------------- | ---------------------------------------------------------- |
| `GET /dashboard/surfaces`           | audit | `dashboard_surface_catalog`、`role_visibility_policy`                    | none                  | 回傳目前 role 可見的 dashboard surfaces。                  |
| `GET /dashboard/summary`            | audit | `audit_dashboard_rollups`、`audit_dashboard_rollup_watermarks`、catalogs | none                  | 回傳 rollup-backed summary metrics 與 freshness metadata。 |
| `GET /stats/summary`                | audit | `audit_events`                                                           | none                  | 既有 stats summary，包含 usage/cost；可掃描/聚合 events。  |
| `GET /stats/top-keys`               | audit | `usage_cost_rollup` 或 SQL pushdown over `audit_events`                  | none                  | By API key 的 usage/cost。                                 |
| `GET /stats/top-models`             | audit | `usage_cost_rollup` 或 SQL pushdown over `audit_events`                  | none                  | By model 的 usage/cost。                                   |
| `GET /stats/top-credentials`        | audit | SQL trace join over `audit_events`                                       | none                  | 歸因到 provider credential 的 usage/cost。                 |
| `GET /internal/alert-candidates`    | audit | `audit_alert_candidates`                                                 | none                  | IAM 專用 internal candidate pull API。                     |
| `enqueue_audit_alert_notifications` | IAM   | audit internal API、IAM identity tables                                  | `notification_outbox` | Pull candidates、resolve audience、enqueue notifications。 |
| `GET /iam/notifications*`           | IAM   | `notification_inbox`                                                     | none                  | Console polling/list/count APIs。                          |
| `POST /iam/notifications/*`         | IAM   | `notification_inbox`                                                     | `notification_inbox`  | Mark read/archive/unarchive/read-all。                     |

---

## 8. 目前狀態

### 8.1 已完成或已就位

- Evidence-to-query projection 已透過 `audit_events` 存在。
- Dashboard summary rollup table 與 watermark table 已存在。
- Dashboard surface catalog 與 role visibility policy 已存在。
- `/dashboard/surfaces` 已存在。
- `/dashboard/summary` 是 rollup-only，並且具備 fail-closed/freshness-aware 行為。
- `/dashboard/summary` 現在會拒絕沒有 summary metrics 的 surfaces。
- `dashboard.usage_cost` 不再從 `/dashboard/summary` 回 `200` empty metrics。
- `tenant_user`/`app_user` 不再取得 tenant-wide `dashboard.traffic`；目前可見 surface 只有 `dashboard.usage_cost`。
- Alert rule catalog 與 alert candidates table 已存在。
- Internal alert candidate API 已存在。
- Alert candidate cursor 現在使用 `(created_at, dedupe_key)`，相同 timestamp rows 不會被跳過。
- IAM puller 會用 bounded cursor loop drain full pages。
- IAM notification outbox/inbox 已存在。
- In-app polling APIs 已存在。
- Archive/read state 是 per-user 且 tenant-scoped。
- ADR-264 usage/cost rollup 已存在，成本計算為 token count 乘上 event-time price snapshot。

### 8.2 目前刻意保留的缺口

- `dashboard.usage_cost` 不是由 `/dashboard/summary` 提供。
- `dashboard.usage_cost` 需要一條專用 dashboard endpoint。
- `tenant_user/self` usage/cost 目前不能安全回傳，因為 `usage_cost_rollup` 還沒有 user dimension。
- 部分 threshold/spike rules 已 seed 但 disabled，需等真實 thresholds 與 producer payload keys 驗證後才能啟用。
- Frontend dashboard widgets 還需要接 rollup APIs，並正確渲染 freshness/degraded state。

---

## 9. 後續工作

### 9.1 Dashboard Usage/Cost Endpoint

已實作：

```text
GET /dashboard/usage-cost
```

目前行為：

- 複用 dashboard visibility 與 scope enforcement。
- 在 permission 允許時接受 tenant/group/application filters。
- 支援 `api_key_uuid` filter。
- 在 user dimension 存在前拒絕 `self`。
- 回傳 totals 與 breakdowns。
- 使用既有 `AuditQueryService` aggregation paths。
- Totals 使用 non-dimensional aggregate，不從 top-N breakdown rows 加總。
- Breakdown 使用既有 usage/cost aggregation path，依 API key、model、application、group、provider credential 回傳 top-N rows。

回應形狀：

```json
{
  "tenant_id": "t1",
  "group_id": null,
  "application_code": null,
  "api_key_uuid": null,
  "window_start": "...",
  "window_end": "...",
  "totals": {
    "request_count": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "total_tokens": 0,
    "cost_in": 0.0,
    "cost_out": 0.0,
    "cost_total": 0.0,
    "unpriced_count": 0
  },
  "breakdowns": {
    "by_api_key": [],
    "by_model": [],
    "by_application": [],
    "by_group": [],
    "by_credential": []
  }
}
```

實作注意事項：

- 不要用 top-N breakdown rows 加總後宣稱是 totals。
- 已新增真正的 aggregate-total path；totals 不能被 top-N breakdown limit 截斷。

### 9.2 為 Self Usage 新增 User Dimension

要支援 `tenant_user(self)`：

- producer 必須在 completed usage events 上 emit stable user identity，或
- projection 必須暴露可靠的 user dimension，且
- `usage_cost_rollup` 必須新增 `user` dim_type 或等價的安全 read path。

在此之前：

- `tenant_user/self` 的 usage-cost data reads 應 fail closed。
- Surface 可以維持 catalog-visible，用來表示產品方向。

### 9.3 Frontend Dashboard 整合

Console 應該：

- render dashboard panels 前先 call `/dashboard/surfaces`
- 只對有 summary metrics 的 surfaces call `/dashboard/summary`
- 不要對 `dashboard.usage_cost` call `/dashboard/summary`
- 對 usage/cost widgets call `/dashboard/usage-cost`
- render `freshness.degraded` 與 `freshness.is_stale`
- 不要把 degraded empty metrics 當成 0
- 把 `403` 視為 no-permission，把 `400` 視為 wrong endpoint/unsupported surface

### 9.4 Threshold/Spike Rules

啟用 disabled threshold/spike notification rules 前，需要：

- 用 real-component tests 確認真實 producer payload keys
- 從 production-like distributions 選 thresholds
- 驗證 `scope_keys`
- 驗證 `max_bucket_age`
- 確認 deployment 時的 replay behavior

目前需要這類工作的 rules：

- `quota.pressure`
- `credential.resolution_failing`
- `guardrail.block_spike`
- `resource.capacity_exhausted`
- `security.login_rejected_spike`

### 9.5 Selector 改進

有些想要的 rules 不能只靠 prefix 表達。

需要補：

- payload-value selectors
- per-prefix severity overrides
- 對 real producer events 做更強的 selector validation

例子：

- `manifest.export_denied` 需要 payload `result=denied`。
- `tenant.status_changed` 未來可能需要依 target status 過濾。
- `audit.pipeline_degraded` 應讓 saturated 是 critical，但 degraded 保持 warning。

### 9.6 Producer 缺口

已知 producer gaps：

- `placement.*` events 不是所有環境都已完整 evidence-backed。
- model instance failure events 需要先補 evidence production，dashboard/notification rules 才能依賴。
- API key expiring soon 目前是 time-based producer，不是 audit event。
- usage quota threshold crossing 需要 producer 或 rollup-driven rule。

### 9.7 維運 Runbooks

仍建議補：

- 從 evidence rebuild `audit_events`
- rebuild `audit_dashboard_rollups`
- rebuild `usage_cost_rollup`
- seed changes 後如何 replay 或 suppress historical alert candidates
- monitor rollup/candidate worker freshness
- alert on stuck IAM puller cursor

---

## 10. 實務建議與避免事項

建議：

- 把 evidence 視為 source of truth
- 把 rollups/candidates/inbox 視為 derived data 或 delivery state
- 用 catalogs 管理 role/surface/rule changes
- 保持 dashboard summary rollup-only
- 使用 explicit degraded/stale states
- 使用 deterministic ids 與 dedupe keys

避免：

- 讓 `/dashboard/summary` 掃 raw events
- 讓 `/dashboard/summary` 對 `dashboard.usage_cost` 回 `200` empty metrics
- 把 `tenant_user` 或 `app_user` widening 到 tenant-wide traffic
- 對 unknown notification audiences 做 broadcast
- 讓單一 malformed candidate 卡住 IAM puller
- 讓 IAM 或 Console 直接讀 audit DB
