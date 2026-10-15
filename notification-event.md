# Notification Event 內容設計 — Title / Content Template × 變數

**Date:** 2026-07-14（同日對全部 producer emit sites 逐條驗證後修訂）
**Status:** Verified Draft（變數可得性已對真 producer 程式碼驗證；模板尚未實作）
**落地進度（2026-07-14）：** §4 的 A（`matched_event_types`）、B（🟡 `payload_extract` 批次）、D（`credential.resolution_failing` scope-key fix）已在 audit repo 落地（Xparse-Audit `fix/notification-rule-variables`）；C(1)（tenant status 明文欄位）已在 xparse `fix/tenant-status-audit-cleartext` 落地。合併後本文各表的 🟡 皆升級為 ✅。
**Sources:**
- 規則清單：`3rd/xparse_audit/src/audit/alerts/seed_rules.py`（21 條，version-guarded seed）
- 產品 curation 決策：`docs/plans/prd-215-catalog-curation-v1.md`
- 變數機制：`3rd/xparse_audit/src/audit/alerts/candidate_projector.py`（`payload_json` 組裝 + `payload_extract` + `_event_value` 取值）
- 現行渲染：`xparse_iam/xparse_iam/notifications/alert_puller.py::_context_for`
- **Producer 驗證出處**：本文各變數表附 emit site `file:line`（2026-07-14 對 origin/main 驗證）

---

## 0. 問題與目標

現行每則通知的 title/body 是通用字串：

```python
"title": f"[{severity}] {rule_id}",           # 例：[critical] policy.binding.invalidated
"body":  f"Audit alert {rule_id} (severity={severity}).",
```

使用者看到的是 rule id，不是「發生了什麼、對誰、該做什麼」。目標：**每個 event 一組 title/content template + 明確變數表**，讓 inbox 一眼可讀、可行動。

**模板落點建議**：在 IAM 側以 `rule_id` 為 key 建 per-rule template registry（取代 `_context_for` 的通用字串），查無模板時 fallback 到現行通用格式——加新規則永遠不會 crash，只是先用醜版。模板語言為英文（Console 產品文案），變數用 `{var}` 佔位。

## 0.5 變數可得性圖例（本次驗證後的三態）

| 標記 | 意義 | 要動什麼 |
|------|------|---------|
| ✅ | candidate `payload_json` **現在就有**（projector 共同欄位或已宣告的 `payload_extract`） | 不用動後端，模板直接用 |
| 🟡 | **producer 已 emit 該欄位**，只是規則沒宣告 `payload_extract` | audit 端 seed 一行改（加 extract path + bump rule version），零 producer 變更 |
| ⚠️ | producer **沒有 emit**（多半只存在 hashed snapshot 裡） | 要改 producer 才拿得到 |

取值機制（`candidate_projector.py::_event_value`）：依序在 event 的 `payload` → `payload.extra` → envelope 找 key，支援 dotted path（`extra.reason`）與 producer dotted-key 慣例（`resource.endpoint_id` 可用 key `endpoint_id` 命中）。IAM CRUD 事件（`emit_iam_crud_event`，`_emit_base.py:376`）的 before/after snapshot **一律只 emit hash**（`change_before_hash`/`change_after_hash`），snapshot 內欄位拿不到——這是多數 ⚠️ 的成因。

**⚠️ First-event-only 限制（重要）**：projector 對 `scope_fields` 與 `payload_extract` 都用 `setdefault`——一個 bucket 收斂多筆 event 時（`count > 1`），抽出的 per-event 變數**只反映第一筆**。per-event 變數只有在「一 event 一 candidate」的規則（scope_keys 含 `event_id`，即四條 identity 規則）才完全可信；其他 event-pattern 規則的模板在 `count > 1` 時必須退回 aggregate 文案。

---

## 1. 共同變數（所有 candidate 都有）

| 變數 | 說明 | 範例 |
|------|------|------|
| `rule_id` | 觸發的規則 | `policy.binding.invalidated` |
| `severity` | `info` / `warning` / `critical` | `critical` |
| `count` | bucket 內匹配事件數 | `12` |
| `bucket_size` | 聚合窗大小（5m/10m/15m/1h/1d） | `15m` |
| `bucket_start` | bucket 起點（ISO 8601） | `2026-07-14T08:00:00+00:00` |
| `event_type_prefixes` | 規則監聽的來源 event 清單（**不是實際命中者**） | `["iam.api_key.revoked", ...]` |
| `comparator` | `gte` / `spike` | `gte` |
| `dedupe_key` / `candidate_id` | 去重與追蹤用，不進文案 | — |

**條件性共同變數**（projector 從 event 的 `group_id`/`group_uuid`、`application_id`/`application_uuid`、`application_code` 解析；**event 沒帶就沒有**——驗證結果見各規則）：

| 變數 | 驗證後實際有此欄位的規則 |
|------|------------------------|
| `group_uuid` | `membership.user_added/removed`（extra.group_uuid）、`guardrail.block_spike`、`policy.llm_operational_violation`、`quota.pressure` 的 `audit.admission.rejected` 半邊。**binding 類與 apikey 類都沒有**（見 §3） |
| `application_uuid` | gateway runtime 類全有（guardrail/violation/quota/credential-failing） |
| `application_code` | gateway runtime 類**除了** `audit.credential.resolution_failed`（只有 application_id） |
| `scope_id` / `scope_keys` | 規則有 `scope_keys` 者（值為 `:` 串接） |

**每規則專屬變數**：規則宣告 `payload_extract=("extra.group_name", ...)` 時，projector 把安全 scalar 欄位以**最後一段**為 key 複製進 **`payload_json["event"]` 巢狀物件**（`extra.group_name` → `event.group_name`；list/dict 與 None 不複製）——renderer 取值路徑是 `payload.event.<name>`，不是 payload top-level。本次驗證證實**大多數規則的理想變數 producer 早就 emit 了（🟡）**，補 extract 即可，見 §3。

**`matched_event_types`**（2026-07-14 起為共同變數）：projector 另 emit bucket 內**實際命中**的 distinct event types（sorted）——與 `event_type_prefixes`（規則宣告全清單）不同，多 prefix 規則的 renderer 用它分辨動作（如 revoked vs rotated）。

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
| 13 | `tenant_user.deactivated` | `oidc.mapping_deactivated` | event-pattern（per event） | info | tenant_admins | ✅ live | tenant user 停用/resync 為 inactive |
| 14 | `tenant_user.reactivated` | `oidc.mapping_reactivated` · `oidc.mapping_emergency_unlocked` | event-pattern（per event） | info | tenant_admins | ✅ live | user 恢復可登入；保留一般恢復 vs 緊急解鎖差異 |
| 15 | `guardrail.block_spike` | `audit.guardrail.blocked` | spike（≥10/15m 且倍增，per app） | warning | group_admins | ✅ live | 個別 block 是正常運作，spike 才是安全訊號 |
| 16 | `policy.llm_operational_violation` | `audit.policy.violation`（`policy_kind=llm_operational`） | event-pattern（per app/1h） | warning | group_admins | ✅ live | llm_operational hard reject（如 token limit）直接影響 client request |
| 17 | `budget.threshold.warning` | `budget.threshold.warning` | threshold（per scope×axis/1d） | warning | tenant_admins | ✅ live* | 部門預算跨過 80% 警戒線（PRD-237 G1）；*delivery 受 `XPARSE_NOTIFICATIONS_ENABLED` gate |
| 18 | `credential.resolution_failing` | `audit.credential.resolution_failed` | threshold（≥5/5m per app） | critical | group_admins | ⛔ disabled | 請求正在 5xx，root cause 在 credential 設定。**🚨 驗證發現 scope key 不匹配，照現狀 enable 也永遠不會 fire（§3.2）** |
| 19 | `quota.pressure` | `audit.policy.rate_limit_applied` · `.concurrency_exhausted` · `audit.admission.rejected` | threshold（≥20/15m per app） | warning | group_admins | ⛔ disabled | 持續拒絕代表容量/policy 需調整；scope key `application_code` **已驗證三個來源都有** |
| 20 | `resource.capacity_exhausted` | `resource.queue.full` · `.timeout` | threshold（≥10/15m per endpoint） | warning | tenant_admins | ⛔ disabled | endpoint 容量長期不足；producer 用 dotted key `resource.endpoint_id`，projector dotted-match **可命中**（仍建議 live probe） |
| 21 | `security.login_rejected_spike` | `oidc.login_rejected` | threshold（≥5/10m per issuer+subject） | warning | system_admins | ⛔ disabled | 重複拒登＝可疑；**部分 reject path 不帶 issuer/subject，會被 fail-closed 排除（§3.4）** |

---

## 3. Per-event Template 設計（含驗證後變數表）

### 3.1 Policy / Governance（group_admins）

#### 1. `policy.binding.invalidated` — critical

Producer：`_emit_versioned_policy.py:327`（call site `ninja_api/_versioned_policies.py:1616`）。**event 不帶任何 group 欄位**（binding 的 scope 資訊只在 hashed snapshot），candidate 因此無 `group_uuid`——audience 解析為 tenant 內全體 group admins（curation plan §2.1a 的既有語意，本次證實）。

> **Title:** `Policy binding invalidated — affected group is now fail-closed`
> **Content:** `Policy binding {binding_uuid} was invalidated by {actor_identity}. Reason: {reason}. All requests from the bound group are rejected until an administrator re-binds a valid policy bundle — this cannot be undone from the Console.`

| 變數 | 出處 | 狀態 |
|------|------|------|
| `binding_uuid` | payload `target_id` | 🟡 extract `target_id` |
| `reason` | payload `extra.reason`（API 的 `data.reason`） | 🟡 extract `extra.reason` |
| `actor_id` / `actor_identity` | IAM CRUD 共同 top-level 欄位 | 🟡 extract |
| `group_uuid` / `group_name` / `bundle_name` | 只在 hashed snapshot | ⚠️ producer |

#### 4. `policy.binding.deactivated` — info

Producer：`_emit_versioned_policy.py:288`。**無 `extra`**（連 reason 都沒有），有 `target_id`、`actor_id`/`actor_identity`。

> **Title:** `Policy binding deactivated`
> **Content:** `Policy binding {binding_uuid} was deactivated by {actor_identity}. The affected group falls back to its remaining bindings or defaults.`

變數：`binding_uuid`（target_id）/ `actor_identity` 🟡；group/bundle 名稱 ⚠️。

#### 5. `policy.binding.created` — info

Producer：`_emit_versioned_policy.py:274`（含 rebind 的新 binding）。同上：`target_id` + actor 🟡，無 extra；bundle 名稱 ⚠️。

> **Title:** `New policy binding activated`
> **Content:** `A policy binding ({binding_uuid}) was created by {actor_identity}. Runtime behavior for the bound group may have changed.`

#### 10. `policy.governance_change` — info

五種來源 event 欄位形狀不一（version 事件 `target_code`=版號、`extra.reason`；grant 事件無 extra；group default `target_id`=group_uuid）。candidate 只帶規則宣告的全清單、且 1h bucket 可能收斂多筆（first-event-only 限制）→ **v1 只能寫 aggregate 通用文案**，分動作需 §4 建議 A。

> **Title:** `Policy governance change in your group`
> **Content:** `{count} policy governance change(s) (version publish/revoke, default policies, or grant lifecycle) occurred in the last {bucket_size}. Review the policy audit log for details.`

變數：`count`/`bucket_size` ✅；`matched_event_type` ⚠️（建議 A）；單事件細節（版號/actor）🟡 但受 first-event-only 限制，`count>1` 時不可信。

#### 16. `policy.llm_operational_violation` — warning

Producer：`policy_violation_audit.py:123`，token-limit caller `pre_execution.py:357`。**驗證結果比原設計樂觀**：violation 細節全部都在 `extra`。

> **Title:** `Requests blocked by {limit_name} limit on {application_code}`
> **Content:** `{count} request(s) on application {application_code} were rejected by an llm_operational policy in the last {bucket_size}. First occurrence: {limit_name} limit {limit_value}, actual {actual_value} (HTTP {http_status_code}). Review the policy limits if this is unexpected.`

| 變數 | 出處 | 狀態 |
|------|------|------|
| `application_code` / `application_uuid` / `group_uuid` / `group_code` | top-level | ✅（app）/ 🟡（group_code） |
| `limit_name` · `limit_value` · `actual_value` · `policy_violation_code` · `policy_name` · `http_status_code` | `extra.*` | 🟡 extract |
| `count` / `bucket_size` | 共同 | ✅ |

注意：per-app 1h bucket 可能收多筆，`limit_*` 只反映第一筆（文案用 "First occurrence" 措辭規避）。

### 3.2 Credential / API Key（group_admins）

#### 6. `apikey.lifecycle` — warning

Producer：`_emit_a.py:206/:222`。**修正**：`group_uuid`/`application_uuid` 只在 hashed snapshot → candidate **沒有** group_uuid（原標 ✅ 錯誤）；audience 解析為 tenant 內全體 group admins。無 key label；有 `extra.key_scope`（tenant/group/application），rotated 另有 `extra.new_key_id`。revoked vs rotated 不可分（建議 A）。

> **Title:** `API key revoked or rotated in your tenant`
> **Content:** `{count} API key lifecycle change(s) (revoke/rotate) occurred in the last {bucket_size} (key {key_id}, scope: {key_scope}). Integrations using an old key will start failing — verify your clients.`

| 變數 | 出處 | 狀態 |
|------|------|------|
| `key_id` | payload `target_id`（per-scope key uuid） | 🟡 extract `target_id` |
| `key_scope` | `extra.key_scope` | 🟡 extract |
| `new_key_id` | `extra.new_key_id`（僅 rotated） | 🟡 extract（缺值時省略） |
| `action`（revoked/rotated）· key label | — | ⚠️（action 走建議 A；label 需 producer） |
| `group_uuid` | hashed snapshot only | ⚠️ |

#### 7. `credential.rotated` — warning

Producer：`_emit_a.py:463/:478`。**好消息**：`target_code` 就是 credential 的人類可讀名稱。

> **Title:** `Provider credential "{credential_name}" was rotated or revoked`
> **Content:** `Provider credential "{credential_name}" changed (rotate/revoke) by {actor_identity} in the last {bucket_size}. Runtime requests may fail until dependent applications pick up the new credential.`

| 變數 | 出處 | 狀態 |
|------|------|------|
| `credential_name` | payload `target_code`（=`cred.name`） | 🟡 extract `target_code` |
| `credential_uuid` | payload `target_id` | 🟡 |
| `actor_identity` | top-level | 🟡 |
| `action`（rotated/revoked）· `provider` | —（provider_code 在 hashed snapshot） | ⚠️（action 走建議 A） |

#### 18. `credential.resolution_failing` — critical（disabled）

Producer：`key_resolver.py:250-391` 經 `emit_audit`（`key_resolver.py:48`）注入 `tenant_id`、`application_id`、`request_id`；callers 傳 `credential_uuid`、`provider_code`、`error`（折進 `extra`）。

> **🚨 驗證發現（enable 前必修）**：規則 `scope_keys=("application_code",)`，但 producer **只 emit `application_id`，沒有 `application_code`** → 每筆 event 都因 scope key 缺失被 fail-closed 排除，**這條規則照現狀 enable 也永遠不會 fire**。修法：規則改 `scope_keys=("application_id",)`（同 `guardrail.block_spike`），或 producer 補 `application_code`。這正是 curation plan §8.1「enable 前必須 probe 真 event」要抓的事。

> **Title:** `Credential resolution failing on application {application_id}`
> **Content:** `{count} credential resolution failures (provider {provider_code}, credential {credential_uuid}) in the last {bucket_size}. Client requests are receiving 5xx — check the provider credential configuration now.`

| 變數 | 出處 | 狀態 |
|------|------|------|
| `application_id` | emit_audit 注入 | ✅（改 scope key 後） |
| `provider_code` / `credential_uuid` / `error` | `extra.*` | 🟡 extract（error 為 redacted message；first-event-only） |
| `application_code` | — | ⚠️ producer 未 emit |

### 3.3 Identity / Membership（已有 `payload_extract`，全數驗證吻合）

Producer extra 由 `membership_notification_extra`（`_emit_base.py:494-530`）與 `_oidc.py` 各 call site 構造；**欄位名與規則的 `payload_extract` 完全一致**。注意：`target_subject`/`target_email` 與 OIDC 的 `subject`/`email` 都是 **masked 值**（producer 端遮罩，`verbose` 無人使用）——模板顯示的是遮罩後字串，設計文案時當作「可識別但非完整 email」。

#### 11. `membership.user_added` — info

> **Title:** `{target_display_name} joined group {group_name}`
> **Content:** `{target_display_name} ({target_email}) was added to group {group_name} ({group_code}) as {membership_role} by {actor_id}. Membership is effective immediately.`

變數：`group_uuid` · `group_code` · `group_name` · `target_mapping_uuid` · `target_subject` · `target_email` · `target_display_name` · `membership_role` · `membership_status` · `actor_id` · `action` — **全部 ✅**（scope 含 `event_id`，一 event 一 candidate，無 first-event 問題）。

#### 12. `membership.user_removed` — info

> **Title:** `{target_display_name} was removed from group {group_name}`
> **Content:** `{target_display_name} ({target_email}) was removed from group {group_name} ({group_code}) by {actor_id}. Their access through this group ends immediately.`

變數同上 + `removal_reason` ✅。

#### 13. `tenant_user.deactivated` — info

Producer 三個 path（`_oidc.py:523` 手動停用 / `:595` resync / `:794` batch）欄位略異：`reason` 只在 resync path、`batch` 只在 batch path——模板按缺值省略。

> **Title:** `User {email} was deactivated`
> **Content:** `User {email} was deactivated ({previous_status} → {new_status}) by {deactivated_by}.` + 條件段：` Reason: {reason}.` / ` (batch resync)`

變數：`mapping_uuid` · `subject` · `email` · `previous_status` · `new_status` · `deactivated_by` · `reason` · `batch` · `action` — ✅。

#### 14. `tenant_user.reactivated` — info

Producer：`_emit_recovery_event`（`_oidc.py:619-656`；emergency unlock `:922` 帶必填 `reason` 與 `unlock_actor_id`，一般恢復帶 `reactivate_actor_id`）。

> **Title:** `User {email} was reactivated`
> **Content:** `User {email} is active again ({previous_status} → {new_status}).` + 依欄位存在擇一：` Reactivated by {reactivate_actor_id}.` / ` Emergency unlock by {unlock_actor_id} — reason: {reason}.`

變數：✅（另有 `previous_deactivated_by` / `previous_deactivated_at` 也已 extract 可用）。

### 3.4 Security（system_admins）

#### 9. `security.access_anomaly` — warning

Producer：downgrade（`core/oidc.py:912`）帶 `extra.mechanism`、`extra.dropped_role_name`；layer conflict（`:475`）帶 `extra.layer1_tenant`、`extra.layer2a_tenant`、`extra.resolved_by`。兩種 event 欄位互斥——extract 全宣告、模板按存在的欄位分段渲染，即可**間接分辨事件種類**（不用等建議 A）。

> **Title:** `Security access anomaly detected`
> **Content:** 有 `dropped_role_name` → `Platform admin role "{dropped_role_name}" was downgraded (mechanism: {mechanism}).`；有 `layer1_tenant` → `Authorization layer conflict between tenants {layer1_tenant} and {layer2a_tenant} (resolved by {resolved_by}).`；否則 aggregate fallback。

| 變數 | 狀態 |
|------|------|
| `mechanism` · `dropped_role_name` · `layer1_tenant` · `layer2a_tenant` · `resolved_by` | 🟡 extract |
| `subject` / `issuer` | 🟡（僅 layer_conflict 有；downgrade 無） |

#### 21. `security.login_rejected_spike` — warning（disabled）

Producer 七個 call site（`core/oidc.py:353-1254`），都帶 `extra.reason`。**覆蓋注意**：`:681`（strict_no_group_mapping）**不帶 issuer/subject** → 被 scope_keys=(issuer, subject) fail-closed 排除，該類拒登不會計入 spike。subject 為 masked 值，scope 穩定可用。

> **Title:** `Repeated login rejections for {subject}`
> **Content:** `{count} rejected login attempts for subject {subject} (issuer {issuer}) in the last {bucket_size}. Latest reason: {reason}. This may indicate credential stuffing or a misconfigured client.`

變數：`issuer`/`subject`（scope keys，top-level ✅）；`reason` 🟡 extract（first-event-only，文案用 "Latest/First" 措辭）。

### 3.5 Platform / Capacity

#### 2. `tenant.status_changed` — critical（tenant_admins）

Producer：`_emit_a.py:59`。**證實**：`before={"status":...}`/`after={"status":...}` 只 emit hash（`emit_values` 未開），**payload 無明文前後狀態**；有 `target_code`（tenant_code）與 actor。

> **Title:** `Tenant {tenant_code} status changed`
> **Content:** `The status of tenant {tenant_code} was changed by {actor_identity}. If the tenant was suspended or disabled, all requests are rejected until an operator restores it.`

| 變數 | 出處 | 狀態 |
|------|------|------|
| `tenant_code` | payload `target_code` | 🟡 extract |
| `actor_identity` | top-level | 🟡 |
| `previous_status` / `new_status` | hashed snapshot only | ⚠️ producer（補明文欄位或 `emit_values`；理想 title：`Tenant {tenant_code} is now {new_status}`） |

#### 3. `fleet.node.down` — critical（system_admins，global）

Producer：`fleet_audit.py:81-95`（call sites `fleet_state.py:1079/:1242`）。**修正（比原標樂觀）**：node id 與 reason **早就都在 payload**。

> **Title:** `Fleet node {node_uuid} deactivated ({reason})`
> **Content:** `Fleet node {node_uuid} transitioned {previous_state} → {new_state} (reason: {reason}). Capacity is reduced — check the Fleet console and remediate.`

| 變數 | 出處 | 狀態 |
|------|------|------|
| `node_uuid`（=target_id）· `previous_state` · `new_state` · `reason`（`rejected`/`quarantined`/`validation_failed`）· `tenant_code`（可為空） | top-level payload | 🟡 extract |

#### 8. `audit.pipeline_degraded` — warning（system_admins）

三種來源形狀不同：`audit.system.*` 由 audit SDK 自身 emit（`sdk/client.py:795`），payload=`BufferMetrics.to_dict()`（`total_received`/`total_dropped`/`mandatory_dropped`/`current_size`/`max_size`/`health` 等）；`iam.notification.failed`（`notifications/worker.py:59-71`）帶 `channel`/`attempts`/`reason`/`notification_event_type`。欄位互斥 → 同 §3.4 #9 的「按欄位存在分段」策略。

> **Title:** `Audit/notification pipeline degraded`
> **Content:** 有 `health` → `Audit buffer {health}: {current_size}/{max_size} queued, {total_dropped} dropped.`；有 `channel` → `Notification delivery failed on channel {channel} after {attempts} attempt(s): {reason}.`；否則 aggregate fallback。`Observability is fail-soft — evidence or notifications may be silently dropping. Investigate now.`

| 變數 | 狀態 |
|------|------|
| `health` · `current_size` · `max_size` · `total_dropped` · `mandatory_dropped` | 🟡 extract（audit.system 半邊） |
| `channel` · `attempts` · `reason` · `notification_event_type` | 🟡 extract（notification 半邊） |

#### 15. `guardrail.block_spike` — warning（group_admins）

Producer：`guardrail_handler.py:605`。**證實** `application_id`/`application_code`/`group_id`/`group_code` 全在 top-level。

> **Title:** `Guardrail blocks spiking on {application_code}`
> **Content:** `Guardrail blocks on application {application_code} doubled to {count} in the last {bucket_size}. Individual blocks are normal; a spike may indicate probing or a prompt-pattern change. Review the risk dashboard.`

| 變數 | 狀態 |
|------|------|
| `application_uuid` / `application_code` / `group_uuid` / `count` / `bucket_size` | ✅ |
| `guardrail_violation_type` | 🟡 extract，但 spike 聚合下 first-event-only——**不建議進模板**（分佈仍 ⚠️） |

#### 19. `quota.pressure` — warning（disabled，group_admins）

Producer：`admission_handler.py:866/:898/:929`。**證實**三個來源都有 top-level `application_code` → scope key 有效。細節 extras：`rejection_reason`（`rate_limit`/`concurrency`/admission 值）、`req_per_sec`+`burst`、`max_concurrency`。

> **Title:** `Sustained quota pressure on {application_code}`
> **Content:** `{count} requests on application {application_code} were rejected by rate limit / concurrency / admission control in the last {bucket_size}. Sustained rejection means capacity or policy limits need adjustment.`

變數：`application_code` / `count` / `bucket_size` ✅；`rejection_reason` 等 🟡（first-event-only，慎用）。

#### 20. `resource.capacity_exhausted` — warning（disabled，tenant_admins）

Producer：`xparse_resource_manager/audit/events.py:54-69`，attrs 用 **dotted keys**（`resource.endpoint_id` 等）。projector 的 dotted-key 容錯（`_event_value` 的 `endswith("."+key)`）可命中 → scope key `endpoint_id` **可解析**（enable 前仍應照 plan 做一次 live probe）。

> **Title:** `Endpoint capacity exhausted: {endpoint_id}`
> **Content:** `{count} queue-full or queue-timeout events on endpoint {endpoint_id} in the last {bucket_size}. The endpoint is under-provisioned for current demand.`

變數：`endpoint_id` ✅（dotted-match）；`max_queue_depth`/`current_depth`/`waited_ms`/`queue_depth` 🟡 extract（兩 event 欄位互斥 + first-event-only）。

### 3.6 FinOps（tenant_admins）

#### 17. `budget.threshold.warning` — warning

Producer：`quota_counter.py:103-113`（emitter 接線 `gateway/app.py:791-800`）。**修正（比原標樂觀）**：金額與比率**都在 payload**——`used`（目前累計）、`budget`（上限）、`pct`（`used/budget` 比率，如 `0.8123`，**是比率不是百分比**）。沒有的只有 scope 顯示名。

> **Title:** `Budget alert: {axis} usage at {pct_display} for {scope_type} {scope_ref}`
> **Content:** `The {axis} budget for {scope_type} {scope_ref} has reached {pct_display} of its limit ({used} of {budget}). Consider raising the budget or curbing usage before the enforce threshold.`
> （`pct_display` = 渲染層把 `pct` × 100 格式化；`scope_ref` = `scope_name` 缺值時退 `scope_uuid`）

| 變數 | 出處 | 狀態 |
|------|------|------|
| `scope_type` / `scope_uuid` / `axis` | payload（也是 scope keys） | ✅ |
| `used` · `budget` · `pct` | payload（折入 extra） | 🟡 extract |
| `scope_name`（部門/群組顯示名） | producer 未 emit | ⚠️——替代方案：IAM 渲染時以 `scope_uuid` 反查名稱（IAM 本來就有這些表），不必動 gateway |

---

## 4. 跨規則的模板機制建議（驗證後修訂）

驗證改變了缺口的分佈：**原以為要改 producer 的，多數其實只要在 audit 端規則補 `payload_extract`（🟡，一行 seed change + version bump）**。真正的缺口收斂為：

- **A. 命中 event type 不可見**（不變）：多 prefix 規則的 candidate 只帶規則宣告全清單。受影響且無 workaround：`apikey.lifecycle`（revoked vs rotated）、`credential.rotated`（rotated vs revoked）、`policy.governance_change`。建議 projector 加 `matched_event_types`（bucket 內實際命中的 distinct types）。`security.access_anomaly` 與 `audit.pipeline_degraded` 可用「互斥欄位存在與否」間接分辨（§3.4/§3.5），`tenant_user.reactivated` 有 `action`——這三條不用等 A。
- **B. 補 `payload_extract`（🟡 清單，零 producer 變更）**：高價值優先序——`policy.binding.invalidated`（target_id/extra.reason/actor_identity）、`budget.threshold.warning`（used/budget/pct）、`fleet.node.down`（node_uuid/previous_state/new_state/reason/tenant_code）、`policy.llm_operational_violation`（limit_name/limit_value/actual_value）、`credential.rotated`（target_code/target_id/actor_identity）、`tenant.status_changed`（target_code/actor_identity）、`audit.pipeline_degraded`（兩組互斥欄位）、`apikey.lifecycle`（target_id/extra.key_scope/extra.new_key_id）、`security.access_anomaly`（兩組互斥欄位）。
- **C. 真 producer 缺口（⚠️，要改 producer）**：只剩四類——(1) `iam.tenant.status_changed` 明文 previous/new status（hash-only 證實）；(2) policy binding/bundle/group 與 API key 的**人類可讀名稱**（全部只在 hashed snapshot）；(3) `audit.credential.resolution_failed` 的 `application_code`；(4) budget 的 `scope_name`（可用 IAM 渲染時反查替代，免改 gateway）。
- **D. 🚨 Rule bug（enable 前必修）**：`credential.resolution_failing` 的 `scope_keys=("application_code",)` 對不上 producer（只 emit `application_id`）→ 照現狀 enable 也**永遠不 fire**。改 `scope_keys=("application_id",)` 或 producer 補欄位。（本次驗證即 curation plan §8.1 要求的 probe 的靜態版；enable 前仍應跑一次真 event。）

設計不變量（修訂）：

1. **Graceful degrade 是硬規則**：任何 🟡/⚠️ 變數缺值時，模板必須能退（段落省略或 fallback 到 `[{severity}] {rule_id}` 通用版），不得渲染出 `{group_name}` 字面或空洞句。
2. **First-event-only 限制**：projector 對 extract 欄位用 `setdefault`（只取 bucket 第一筆）。per-event 變數只有在 scope 含 `event_id` 的規則（四條 identity 規則）才完全可信；其他規則 `count > 1` 時 per-event 變數須以 "First/Latest occurrence" 措辭呈現或直接退 aggregate 文案。threshold/spike 規則一律只用 aggregate 變數。
3. **Masked PII 如實呈現**：membership/OIDC 的 subject/email 是 producer 端遮罩值，模板直接顯示遮罩字串，IAM 側不得反查還原。
4. **Redaction 邊界不變**：`payload_extract` 有 forbidden-key 防護（prompt/response/secret/api_key 等）；模板變數只能來自 candidate payload。
5. **模板新增不動 worker**：per-rule template registry 查無 key 時 fallback，與 PRD-203 G4 同精神；規則先上、文案後補是合法路徑。
