# Notification Event 內容設計 — Title / Content Template × 變數

**Date:** 2026-07-14
**Status:** Draft（內容設計提案；模板尚未實作）
**Sources:**
- 規則清單：`3rd/xparse_audit/src/audit/alerts/seed_rules.py`（21 條，version-guarded seed）
- 產品 curation 決策：`docs/plans/prd-215-catalog-curation-v1.md`
- 變數來源：`3rd/xparse_audit/src/audit/alerts/candidate_projector.py`（candidate `payload_json` 組裝 + `payload_extract`）
- 現行渲染：`xparse_iam/xparse_iam/notifications/alert_puller.py::_context_for`

---

## 0. 問題與目標

現行每則通知的 title/body 是通用字串：

```python
"title": f"[{severity}] {rule_id}",           # 例：[critical] policy.binding.invalidated
"body":  f"Audit alert {rule_id} (severity={severity}).",
```

使用者看到的是 rule id，不是「發生了什麼、對誰、該做什麼」。目標：**每個 event 一組 title/content template + 明確變數表**，讓 inbox 一眼可讀、可行動。

**模板落點建議**：在 IAM 側以 `rule_id` 為 key 建 per-rule template registry（取代 `_context_for` 的通用字串），查無模板時 fallback 到現行通用格式——加新規則永遠不會 crash，只是先用醜版。模板語言為英文（Console 產品文案），變數用 `{var}` 佔位。

---

## 1. 共同變數（所有 candidate 都有）

candidate 的 `payload_json` 由 audit 端 projector 組出，IAM puller 原樣放進 inbox context payload。以下欄位**每條規則都可用**：

| 變數 | 說明 | 範例 |
|------|------|------|
| `rule_id` | 觸發的規則 | `policy.binding.invalidated` |
| `severity` | `info` / `warning` / `critical` | `critical` |
| `count` | bucket 內匹配事件數（event-pattern 規則恆為每 bucket 實際數；threshold 規則為聚合數） | `12` |
| `bucket_size` | 聚合窗大小（5m/10m/15m/1h/1d） | `15m` |
| `bucket_start` | bucket 起點（ISO 8601） | `2026-07-14T08:00:00+00:00` |
| `event_type_prefixes` | 規則監聽的來源 event 清單 | `["iam.api_key.revoked", ...]` |
| `comparator` | `gte` / `spike` | `gte` |
| `dedupe_key` / `candidate_id` | 去重與追蹤用，不進文案 | — |

**條件性共同變數**（來源 event 有帶才有）：

| 變數 | 條件 | 說明 |
|------|------|------|
| `scope_id` / `scope_keys` | 規則有 `scope_keys` | scope 值串接（如 `app-123` 或 budget 的 `tenant:uuid:cost`） |
| `group_uuid` | event 帶 group | audience 解析也靠它 |
| `application_uuid` / `application_code` | event 帶 app | app-scoped 規則可用 |

**每規則專屬變數**：規則宣告 `payload_extract=("extra.group_name", ...)` 時，projector 會把安全 scalar 欄位以**最後一段**為 key 複製進 payload（`extra.group_name` → `group_name`）。目前只有 §2.1d 的四條 identity 規則有宣告；其他規則要做好文案，多半需要**補 `payload_extract`**（表中以 ⚠️ 標記）。

---

## 2. 事件總表（21 條）

| # | rule_id | 來源 events | 類型 | severity | audience | 狀態 | 一句話說明 |
|---|---------|-------------|------|----------|----------|------|-----------|
| 1 | `policy.binding.invalidated` | `policy.binding.invalidated` | event-pattern | critical | group_admins | ✅ live | binding 失效 → 整個 group fail-closed，且 Console 無自助復原（#1704），必須立刻通知 |
| 2 | `tenant.status_changed` | `iam.tenant.status_changed` | event-pattern | critical | tenant_admins | ✅ live | tenant 狀態轉換（含 suspended/disabled）＝全租戶服務中斷級事件 |
| 3 | `fleet.node.down` | `fleet.node.deactivated` | event-pattern | critical | system_admins（global 扇出） | ✅ live | GPU 節點停用＝容量損失，需人工介入 |
| 4 | `policy.binding.deactivated` | `policy.binding.deactivated` | event-pattern | info | group_admins | ✅ live | binding 停用是正常治理操作，但改變 group 行為契約，告知級 |
| 5 | `policy.binding.created` | `policy.binding.created` | event-pattern | info | group_admins | ✅ live | 新 binding 掛上即改變該 scope 的 runtime 行為契約 |
| 6 | `apikey.lifecycle` | `iam.api_key.revoked` · `.rotated` | event-pattern | warning | group_admins | ✅ live | key 撤銷/輪替直接弄斷整合，低頻單事件可行動 |
| 7 | `credential.rotated` | `iam.provider_credential.rotated` · `.revoked` | event-pattern | warning | group_admins | ✅ live | provider credential 變動可能即刻中斷 runtime |
| 8 | `audit.pipeline_degraded` | `audit.system.degraded` · `.saturated` · `iam.notification.failed` | event-pattern | warning | system_admins（可 global） | ✅ live | fail-soft 架構下 audit/notification 壞掉是靜默的（RCA-016），必須主動推 |
| 9 | `security.access_anomaly` | `oidc.platform_admin_downgraded` · `oidc.layer_conflict_detected` | event-pattern | warning | system_admins | ✅ live | forensic 級單事件：平台管理員被降權 / 授權層衝突 |
| 10 | `policy.governance_change` | `policy.version.revoked` · `.published` · `iam.group.default_policies_set` · `policy.grant.created` · `.revoked` | event-pattern | info | group_admins | ✅ live | 行為契約變更告知（version/grant/default-policy） |
| 11 | `membership.user_added` | `iam.membership.created`（`membership_status=accepted`） | event-pattern（per event） | info | group_admins | ✅ live | direct-add 即刻生效，group 成員/權限邊界改變 |
| 12 | `membership.user_removed` | `iam.membership.deleted`（`removal_reason=explicit`） | event-pattern（per event） | info | group_admins | ✅ live | 成員被明確移除，權限邊界改變 |
| 13 | `tenant_user.deactivated` | `oidc.mapping_deactivated` | event-pattern（per event） | info | tenant_admins | ✅ live | tenant user 停用/resync 為 inactive；recipient 名單也應同步收斂 |
| 14 | `tenant_user.reactivated` | `oidc.mapping_reactivated` · `oidc.mapping_emergency_unlocked` | event-pattern（per event） | info | tenant_admins | ✅ live | user 恢復可登入；保留一般恢復 vs 緊急解鎖差異 |
| 15 | `guardrail.block_spike` | `audit.guardrail.blocked` | spike（≥10/15m 且倍增，per app） | warning | group_admins | ✅ live | 個別 block 是正常運作，spike 才是安全訊號 |
| 16 | `policy.llm_operational_violation` | `audit.policy.violation`（`policy_kind=llm_operational`） | event-pattern（per app/1h） | warning | group_admins | ✅ live | llm_operational hard reject（如 token limit）直接影響 client request |
| 17 | `budget.threshold.warning` | `budget.threshold.warning` | threshold（per scope×axis/1d） | warning | tenant_admins | ✅ live* | 部門預算跨過 80% 警戒線（PRD-237 G1）；*delivery 受 `XPARSE_NOTIFICATIONS_ENABLED` gate |
| 18 | `credential.resolution_failing` | `audit.credential.resolution_failed` | threshold（≥5/5m per app） | critical | group_admins | ⛔ disabled | 請求正在 5xx，root cause 在 credential 設定；門檻待調參 |
| 19 | `quota.pressure` | `audit.policy.rate_limit_applied` · `.concurrency_exhausted` · `audit.admission.rejected` | threshold（≥20/15m per app） | warning | group_admins | ⛔ disabled | 持續拒絕代表容量/policy 需調整；門檻待調參 |
| 20 | `resource.capacity_exhausted` | `resource.queue.full` · `.timeout` | threshold（≥10/15m per endpoint） | warning | tenant_admins | ⛔ disabled | endpoint 容量長期不足；`endpoint_id` payload key 待驗證 |
| 21 | `security.login_rejected_spike` | `oidc.login_rejected` | threshold（≥5/10m per issuer+subject） | warning | system_admins | ⛔ disabled | 重複拒登＝可疑存取；`issuer`/`subject` payload key 待驗證 |

---

## 3. Per-event Template 設計

變數表圖例：✅ = candidate payload 現在就有；⚠️ = 需補（producer 欄位或規則 `payload_extract`）才可用，補上前模板需 graceful degrade（變數缺值時退段落或退 fallback 模板）。

### 3.1 Policy / Governance（group_admins）

#### 1. `policy.binding.invalidated` — critical

> **Title:** `Policy binding invalidated — group {group_name} is now fail-closed`
> **Content:** `A policy binding on group {group_name} was invalidated. All requests from this group are now rejected until an administrator re-binds a valid policy bundle. This cannot be undone from the Console — contact your platform operator if you cannot re-bind.`

| 變數 | 來源 | 狀態 |
|------|------|------|
| `group_uuid` | projector 共同欄位 | ✅ |
| `group_name` / `group_code` | 需 `payload_extract` | ⚠️ |
| `binding_uuid` / `bundle_name` / `invalidation_reason` | 需 producer 欄位 + `payload_extract` | ⚠️ |

缺 `group_name` 時 fallback：title 用 `group {group_uuid}`。此條是全 catalog 最高價值（fail-closed 無自助復原），變數補齊優先級最高。

#### 4. `policy.binding.deactivated` — info

> **Title:** `Policy binding deactivated on group {group_name}`
> **Content:** `A policy binding on group {group_name} was deactivated by {actor_id}. The group falls back to its remaining bindings or defaults.`

變數同上（`group_name`/`actor_id` ⚠️）。

#### 5. `policy.binding.created` — info

> **Title:** `New policy binding on group {group_name}`
> **Content:** `A policy binding ({bundle_name}) was created on group {group_name} by {actor_id}. Runtime behavior for this group may have changed.`

變數同上（`bundle_name`/`actor_id` ⚠️）。

#### 10. `policy.governance_change` — info

單一規則涵蓋 5 種來源 event，candidate 只帶 `event_type_prefixes`（規則宣告的全清單），**不知道實際命中哪個**。v1 模板只能寫通用文案；要分動作需補「命中 event type」變數（見 §4 建議 A）。

> **Title:** `Policy governance change in your group`
> **Content:** `{count} policy governance change(s) (version publish/revoke, default policies, or grant lifecycle) occurred in the last {bucket_size}. Review the policy audit log for details.`

| 變數 | 狀態 |
|------|------|
| `count` / `bucket_size` | ✅ |
| `matched_event_type` / `policy_version_id` / `grant_uuid` | ⚠️（建議 A） |

#### 16. `policy.llm_operational_violation` — warning

> **Title:** `LLM operational policy blocked requests on {application_code}`
> **Content:** `{count} request(s) on application {application_code} were rejected by an llm_operational policy (e.g. token limit) in the last {bucket_size}. Clients receive hard errors — review the policy limits if this is unexpected.`

| 變數 | 狀態 |
|------|------|
| `application_code` / `application_uuid` / `count` / `bucket_size` | ✅ |
| `violation_detail`（哪條 limit） | ⚠️ |

### 3.2 Credential / API Key（group_admins）

#### 6. `apikey.lifecycle` — warning

同規則涵蓋 revoked 與 rotated，candidate 無法區分（同 §4 建議 A）。v1 通用版：

> **Title:** `API key revoked or rotated in your group`
> **Content:** `{count} API key lifecycle change(s) (revoke/rotate) occurred in the last {bucket_size}. Integrations using an old key will start failing — verify your clients.`

| 變數 | 狀態 |
|------|------|
| `count` / `bucket_size` / `group_uuid` | ✅ |
| `action`（revoked/rotated）· `key_label` / `key_prefix` · `application_code` | ⚠️（理想 title：`API key {key_label} was {action}`） |

#### 7. `credential.rotated` — warning

> **Title:** `Provider credential rotated or revoked`
> **Content:** `{count} provider credential change(s) (rotate/revoke) occurred in the last {bucket_size}. Runtime requests may fail until dependent applications pick up the new credential.`

| 變數 | 狀態 |
|------|------|
| `count` / `bucket_size` | ✅ |
| `action` · `credential_name` / `provider` | ⚠️（理想 title：`Provider credential {credential_name} was {action}`） |

#### 18. `credential.resolution_failing` — critical（disabled）

> **Title:** `Credential resolution failing on {application_code}`
> **Content:** `{count} credential resolution failures on application {application_code} in the last {bucket_size}. Client requests are receiving 5xx — check the provider credential configuration now.`

| 變數 | 狀態 |
|------|------|
| `application_code`（= scope key）/ `count` / `bucket_size` | ✅ |

### 3.3 Identity / Membership（已有 `payload_extract`，變數最完整）

#### 11. `membership.user_added` — info

> **Title:** `{target_display_name} joined group {group_name}`
> **Content:** `{target_display_name} ({target_email}) was added to group {group_name} ({group_code}) as {membership_role} by {actor_id}. Membership is effective immediately.`

| 變數 | 狀態 |
|------|------|
| `group_uuid` · `group_code` · `group_name` · `target_mapping_uuid` · `target_subject` · `target_email` · `target_display_name` · `membership_role` · `membership_status` · `actor_id` · `action` | ✅（皆已 `payload_extract`） |

#### 12. `membership.user_removed` — info

> **Title:** `{target_display_name} was removed from group {group_name}`
> **Content:** `{target_display_name} ({target_email}) was removed from group {group_name} ({group_code}) by {actor_id}. Their access through this group ends immediately.`

變數同上 + `removal_reason` ✅。

#### 13. `tenant_user.deactivated` — info

> **Title:** `User {email} was deactivated`
> **Content:** `User {email} was deactivated ({previous_status} → {new_status}) by {deactivated_by}.{reason_sentence}` — `reason_sentence` 有 `reason` 時渲染為 ` Reason: {reason}.`，batch resync（`batch=true`）時附 ` (batch resync)`。

| 變數 | 狀態 |
|------|------|
| `mapping_uuid` · `subject` · `email` · `previous_status` · `new_status` · `deactivated_by` · `reason` · `batch` · `action` | ✅ |

#### 14. `tenant_user.reactivated` — info

> **Title:** `User {email} was reactivated`
> **Content:** `User {email} is active again ({previous_status} → {new_status}).` 若來源是 `oidc.mapping_emergency_unlocked`（`action` 可區分）：`Emergency unlock performed by {unlock_actor_id}.`；一般恢復：`Reactivated by {reactivate_actor_id}.`

| 變數 | 狀態 |
|------|------|
| `mapping_uuid` · `subject` · `email` · `previous_status` · `new_status` · `reactivate_actor_id` · `unlock_actor_id` · `reason` · `batch` · `action` | ✅ |

### 3.4 Security（system_admins）

#### 9. `security.access_anomaly` — warning

涵蓋兩種 forensic 單事件，需區分（同 §4 建議 A）。v1 通用版：

> **Title:** `Security access anomaly detected`
> **Content:** `{count} access anomaly event(s) (platform-admin downgrade or authorization layer conflict) detected in the last {bucket_size}. Review the security audit log immediately.`

| 變數 | 狀態 |
|------|------|
| `count` / `bucket_size` | ✅ |
| `matched_event_type` · `subject` · `issuer` | ⚠️ |

#### 21. `security.login_rejected_spike` — warning（disabled）

> **Title:** `Repeated login rejections for {subject}`
> **Content:** `{count} rejected login attempts for subject {subject} (issuer {issuer}) in the last {bucket_size}. This may indicate credential stuffing or a misconfigured client.`

| 變數 | 狀態 |
|------|------|
| `issuer` / `subject`（= scope keys，`scope_id` 內）/ `count` / `bucket_size` | ✅*（*啟用前需驗 payload key 名，curation plan §8.1） |

### 3.5 Platform / Capacity（tenant_admins / system_admins）

#### 2. `tenant.status_changed` — critical

producer 目前把前後狀態 hash 進 snapshot，**候選拿不到 target status**（seed_rules 註記）。v1 通用版：

> **Title:** `Tenant status changed`
> **Content:** `Your tenant's status changed. If the tenant was suspended or disabled, all requests are rejected until an operator restores it. Contact your platform operator for details.`

| 變數 | 狀態 |
|------|------|
| `previous_status` / `new_status` | ⚠️（需 producer 補明文欄位 + `payload_extract`；理想 title：`Tenant status changed to {new_status}`） |

#### 3. `fleet.node.down` — critical

> **Title:** `Fleet node deactivated`
> **Content:** `{count} fleet node(s) were deactivated in the last {bucket_size}. Capacity is reduced — check the Fleet console for the node state (rejected/quarantined/validation-failed) and remediate.`

| 變數 | 狀態 |
|------|------|
| `count` / `bucket_size` | ✅ |
| `node_id` · `deactivation_reason` | ⚠️（理想 title：`Fleet node {node_id} deactivated ({deactivation_reason})`） |

#### 8. `audit.pipeline_degraded` — warning

> **Title:** `Audit/notification pipeline degraded`
> **Content:** `{count} pipeline health event(s) (audit buffer degraded/saturated or notification delivery failure) in the last {bucket_size}. Observability is fail-soft — evidence or notifications may be silently dropping. Investigate now.`

| 變數 | 狀態 |
|------|------|
| `count` / `bucket_size` | ✅ |
| `matched_event_type`（degraded vs saturated vs notification.failed）· queue 深度等 detail | ⚠️（saturated 應升 critical——curation plan 已註記待 per-prefix severity） |

#### 15. `guardrail.block_spike` — warning

> **Title:** `Guardrail blocks spiking on {application_code}`
> **Content:** `Guardrail blocks on application {application_code} doubled to {count} in the last {bucket_size}. Individual blocks are normal; a spike may indicate probing or a prompt-pattern change. Review the risk dashboard.`

| 變數 | 狀態 |
|------|------|
| `application_uuid`（scope key `application_id`）/ `count` / `bucket_size` / `comparator` | ✅ |
| `application_code` | ✅（event 有帶時） |
| `violation_type` 分佈 | ⚠️ |

#### 19. `quota.pressure` — warning（disabled）

> **Title:** `Sustained quota pressure on {application_code}`
> **Content:** `{count} requests on application {application_code} were rejected by rate limit / concurrency / admission control in the last {bucket_size}. Sustained rejection means capacity or policy limits need adjustment.`

| 變數 | 狀態 |
|------|------|
| `application_code` / `count` / `bucket_size` | ✅ |

#### 20. `resource.capacity_exhausted` — warning（disabled）

> **Title:** `Endpoint capacity exhausted: {endpoint_id}`
> **Content:** `{count} queue-full or queue-timeout events on endpoint {endpoint_id} in the last {bucket_size}. The endpoint is under-provisioned for current demand.`

| 變數 | 狀態 |
|------|------|
| `endpoint_id`（scope key）/ `count` / `bucket_size` | ✅*（key 名待 §8.1 驗證） |

### 3.6 FinOps（tenant_admins）

#### 17. `budget.threshold.warning` — warning

> **Title:** `Budget alert: {scope_type} {scope_name} crossed {threshold_pct}% ({axis})`
> **Content:** `The {axis} budget for {scope_type} {scope_name} has crossed {threshold_pct}% of its limit. Current usage: {current_amount} of {budget_amount}. Consider raising the budget or curbing usage before the enforce threshold.`

| 變數 | 狀態 |
|------|------|
| `scope_type` / `scope_uuid` / `axis`（= scope keys，`scope_id` 內） | ✅ |
| `scope_name`（部門/群組顯示名）· `threshold_pct` · `current_amount` · `budget_amount` | ⚠️（producer event 若已帶，補 `payload_extract` 即可） |

---

## 4. 跨規則的模板機制建議

依變數表歸納，三個系統性缺口決定了模板品質上限：

- **A. 命中 event type 不可見**：多 prefix 規則（`apikey.lifecycle`、`policy.governance_change`、`security.access_anomaly`、`audit.pipeline_degraded`、`tenant_user.reactivated`）的 candidate 只帶規則宣告的全清單。建議 projector 在 payload 加 `matched_event_types`（bucket 內實際命中的 distinct types）——一次修改，五條規則的文案立即可分動作。`tenant_user.reactivated` 已可用 `action` extract 繞過，其餘不行。
- **B. `payload_extract` 覆蓋率**：§2.1d 四條證明了機制可行且變數表最完整。高價值目標依序：`policy.binding.invalidated`（group_name/binding/reason；critical 且無自助復原）、`budget.threshold.warning`（金額與百分比）、`apikey.lifecycle`（key label）、`fleet.node.down`（node_id/reason）。
- **C. producer 欄位缺口**：`tenant.status_changed` 的前後狀態只在 hash snapshot 裡，`payload_extract` 救不了，需 producer 補明文 `previous_status`/`new_status`。

其他設計不變量：

1. **Graceful degrade 是硬規則**：任何 ⚠️ 變數缺值時，模板必須能退（段落省略或 fallback 到 `[{severity}] {rule_id}` 通用版），不得渲染出 `{group_name}` 字面或空洞句。
2. **Threshold/spike 規則不引用單事件欄位**：聚合了 N 個 event 的 candidate 只有 aggregate 語意（count/bucket/scope）；per-event 欄位（如第一筆的 user）會誤導，禁止進模板。
3. **Redaction 邊界不變**：`payload_extract` 有 forbidden-key 防護（candidate 不得攜帶 raw content）；模板變數只能來自 candidate payload，IAM 側不回查敏感內容。
4. **模板新增不動 worker**：per-rule template registry 查無 key 時 fallback，與 PRD-203 G4（type 註冊制）同精神；規則先上、文案後補是合法路徑。
