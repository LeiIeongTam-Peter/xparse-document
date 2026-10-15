# Xparse Audit Events

Last reviewed: 2026-07-02

本文件整理目前 Xparse codebase 中已定義、已 emit，或 audit 查詢端明確相容的 audit events。這裡列的是現有會被記錄的事件，不包含尚未實作的 notification 候選事件，例如 `api_key.expiring_soon`。

## Reading Guide

| Column | Meaning |
| --- | --- |
| Event | 寫入 audit record 或 local event log 的 `event_type` 值。 |
| What it records | 這個事件記錄的行為或狀態。 |
| Triggered when | 事件會在什麼程式路徑或操作下被觸發。 |

## Audit SDK And Evidence Core

| Event | What it records | Triggered when |
| --- | --- | --- |
| `audit.execution.request_started` | 請求進入被稽核的執行路徑。 | 應用程式在 request entry 呼叫 audit SDK。 |
| `audit.execution.request_finished` | 請求完成，結果可能是成功、失敗或被阻擋。 | 應用程式在 request exit 呼叫 audit SDK。 |
| `audit.execution.tool_invoked` | 執行期間發生 tool invocation。 | tool call 依 audit SDK 參考契約被記錄。 |
| `audit.observability.event` | latency、token、model、cost 等結構化觀測資料。 | `AuditClient.record_observability()` 記錄 runtime observability data。 |
| `audit.observability.metrics` | 文件化的 metrics-style observability event。 | 舊版或參考 SDK 文件記錄彙總效能資料時使用。 |
| `audit.governance.policy_decision` | typed policy decision，包含 decision、reason、actor、target。 | `AuditClient.record_policy_decision()` 記錄 allow、deny 或 conditional decision。 |
| `audit.governance.guardrail_triggered` | typed guardrail trigger，包含 guardrail type 與 enforcement mode。 | `AuditClient.record_guardrail_triggered()` 記錄 safety、compliance 或 operational guardrail trigger。 |
| `audit.identity.auth_attempt` | 認證嘗試的 metadata。 | SDK mandatory event type；identity audit producer 可記錄此事件。 |
| `audit.identity.key_issued` | key issuance metadata。 | SDK mandatory event type；key issue flow 可記錄此事件。 |
| `audit.identity.key_revoked` | key revocation metadata。 | SDK mandatory event type；key revoke flow 可記錄此事件。 |
| `audit.policy.decision` | SDK config 中的 mandatory policy decision event name。 | policy engine 或 caller 使用 legacy/simple policy namespace 記錄 policy decision。 |
| `audit.system.healthy` | audit buffer 或 audit system 處於 healthy。 | audit SDK self-audit 發出 health state。 |
| `audit.system.degraded` | audit buffer 或 audit system 進入 degraded。 | buffer utilization 超過 degradation threshold。 |
| `audit.system.saturated` | audit buffer 進入 saturated。 | audit buffer 達到容量上限。 |
| `audit.system.recovered` | audit system 從 degraded 狀態恢復。 | 文件化 system event；audit system recovery 後記錄。 |
| `audit.system.flush` | audit system flush 行為。 | 文件化 system event；flush operation 發生時記錄。 |
| `audit.custody.exported` | evidence package 已 export 並封存。 | chain-of-custody state 進入 `exported`。 |
| `audit.custody.handed_over` | evidence package 已交付給接收方。 | chain-of-custody state 進入 `handed_over`。 |
| `audit.custody.received` | 接收方確認收到 evidence。 | chain-of-custody state 進入 `received`。 |
| `audit.custody.external` | evidence 進入外部 custody 流程。 | chain-of-custody state 進入 terminal `external`。 |
| `storage.tier_transition` | evidence 在 storage tiers 之間移動。 | storage lifecycle 記錄 hot/warm/cold/archive transition。 |

## Gateway Runtime Audit

| Event | What it records | Triggered when |
| --- | --- | --- |
| `audit.execution.request_received` | Gateway 收到 runtime request。 | client request 進入 admission handling。 |
| `audit.admission.decided` | Admission controller 做出決策。 | Gateway 評估 admission mode 與 request admission state。 |
| `audit.execution.request_queued` | request 被放入 queue。 | Gateway 因 admission 或 endpoint capacity 將 request 排隊。 |
| `audit.execution.request_dequeued` | request 離開 queue。 | Gateway 開始處理已排隊的 request。 |
| `audit.execution.started` | provider 或 worker execution 開始。 | Gateway 啟動 non-streaming 或 streaming execution。 |
| `audit.execution.completed` | execution 成功完成。 | Gateway 完成 runtime request 並記錄 usage/latency。 |
| `audit.admission.rejected` | request 在 execution 前被拒絕。 | Gateway 因 admission、policy、quota 或 validation failure 拒絕 request。 |
| `audit.execution.failed` | request admission 後執行失敗。 | Gateway 捕捉 provider、worker、timeout 或 execution error。 |
| `audit.admission.timeout` | request 在 queue 中等待逾時。 | Gateway queue wait 超過 timeout。 |
| `audit.policy.rate_limit_applied` | rate limit check result 被套用。 | Gateway 在 admission 階段套用 rate-limit policy。 |
| `audit.policy.concurrency_exhausted` | concurrency capacity 已耗盡。 | Gateway 因 concurrency limit 無法 admit request。 |
| `audit.policy.violation` | runtime policy violation。 | Gateway policy enforcement 拒絕或阻擋 request。 |
| `audit.execution.tool_call_detected` | model response 包含 tool calls。 | Gateway 在 execution output 中偵測到 tool calls。 |
| `audit.execution.streaming_phase_changed` | streaming state 發生變更。 | Streaming pipeline 切換 phase，例如 fast stream 到 buffering。 |
| `audit.execution.cache_hit` | request 由 cache 回應。 | Gateway cache handler 回傳 cached response。 |
| `audit.governance.quality_gate_decided` | quality gate 做出 runtime governance decision。 | Gateway safety 或 quality gate 接受、修補或阻擋 output。 |
| `audit.governance.safety_patch_applied` | safety patch 已套用到 output。 | Gateway 為 safety 或 compliance 修改 output。 |
| `audit.execution.provider_fallback` | Gateway 切換 provider 或 model。 | provider fallback logic 在失敗後選擇替代 provider 或 model。 |
| `audit.execution.resource_queue_degraded` | ResourceManager queue degraded to direct execution。 | endpoint queue integration 不可用或 degraded。 |
| `audit.credential.resolved` | runtime credential 已解析。 | Gateway 為 request 解析 provider credential material。 |
| `audit.credential.resolution_failed` | runtime credential 解析失敗。 | credential resolver 無法解析可用 credential。 |
| `audit.guardrail.input_check` | input guardrail check 已執行。 | Gateway 檢查 request input 是否符合 guardrail。 |
| `audit.guardrail.output_check` | output guardrail check 已執行。 | Gateway 檢查 model output 是否符合 guardrail。 |
| `audit.guardrail.blocked` | guardrail 阻擋 request 或 response。 | guardrail verdict action 為 `block`。 |
| `audit.guardrail.error` | guardrail evaluation 失敗。 | guardrail service 或 evaluation path 回傳錯誤。 |

## Responses API Audit

| Event | What it records | Triggered when |
| --- | --- | --- |
| `audit.responses.tool_rejected` | Responses API 拒絕 tool request。 | Responses route 拒絕 unsupported 或 invalid tool usage。 |
| `audit.responses.create_invalid_store` | create request 使用 invalid store settings。 | Responses create path 收到 invalid `store` configuration。 |
| `audit.responses.created` | stored response 已建立。 | Responses API 成功建立 stored response binding。 |
| `audit.responses.deleted` | stored response 已刪除。 | Responses API 刪除 stored response data。 |
| `audit.responses.binding_validated` | stored-response binding 已驗證。 | Gateway 為 chained request 驗證 response binding。 |
| `audit.responses.binding_insert_failed` | binding insert 失敗。 | IAM 或 persistence layer 插入 binding 時失敗。 |
| `audit.responses.binding_unknown_id` | binding lookup 找不到 response ID。 | request 參照 IAM 無法解析的 response ID。 |
| `audit.responses.binding_deleted_reject` | deleted binding 被拒絕。 | chained request 參照已刪除的 binding。 |
| `audit.responses.binding_expired` | expired binding 被拒絕。 | chained request 參照已過期的 response binding。 |
| `audit.responses.binding_store_false_chain` | 嘗試 chain `store=false` 的 response。 | Responses chain validation 拒絕 non-stored response。 |
| `audit.responses.binding_tenant_mismatch` | binding tenant 與 current tenant 不符。 | chained response 屬於不同 tenant。 |
| `audit.responses.binding_app_mismatch` | binding application 與 current app 不符。 | chained response 屬於不同 application。 |
| `audit.responses.binding_backend_drift` | binding backend drift 被偵測。 | stored response backend identity 非預期變更。 |
| `audit.responses.binding_model_drift` | binding model drift 被偵測。 | stored response model identity 非預期變更。 |
| `audit.responses.binding_iam_unavailable` | binding validation 時 IAM 不可用。 | Responses binding validation 無法連線 IAM。 |
| `audit.responses.delete_unknown_id` | delete request 參照 unknown response ID。 | Responses delete path 找不到 response binding。 |
| `audit.responses.delete_tenant_mismatch` | delete request tenant 與 binding tenant 不符。 | tenant 嘗試刪除其他 tenant 的 response binding。 |
| `audit.responses.delete_app_mismatch` | delete request app 與 binding app 不符。 | app 嘗試刪除其他 app 的 response binding。 |
| `audit.responses.delete_iam_unavailable` | delete validation 時 IAM 不可用。 | delete path 無法透過 IAM 驗證 binding。 |
| `audit.responses.outbound_no_id` | provider response 缺少 outbound response ID。 | Responses path 預期 response ID，但 provider output 沒有提供。 |

## IAM Management Audit

| Event | What it records | Triggered when |
| --- | --- | --- |
| `iam.tenant.created` | tenant 建立。 | Tenant management API 建立 tenant。 |
| `iam.tenant.updated` | tenant metadata 更新。 | Tenant management API 更新 tenant fields。 |
| `iam.tenant.status_changed` | tenant status transition。 | tenant 被啟用、停用、暫停或其他 status change。 |
| `iam.tenant.settings_updated` | tenant settings 更新。 | tenant-level settings 被修改。 |
| `iam.group.created` | group 建立。 | Group management API 建立 group。 |
| `iam.group.updated` | group metadata 更新。 | Group management API 更新 group fields。 |
| `iam.group.deleted` | group 刪除。 | Group management API 刪除或停用 group。 |
| `iam.membership.created` | user/group membership 建立。 | user mapping 被加入 group。 |
| `iam.membership.updated` | user/group membership 更新。 | membership role 或 metadata 變更。 |
| `iam.membership.deleted` | user/group membership 移除。 | user mapping 被從 group 移除。 |
| `iam.application.created` | application 建立。 | Application management API 建立 app。 |
| `iam.application.updated` | application 更新。 | application settings 或 metadata 變更。 |
| `iam.application.deleted` | application 刪除。 | application 被刪除或停用。 |
| `iam.application.reactivated` | application 重新啟用。 | previously inactive application 被 reactivated。 |
| `iam.application.terminated` | application 終止。 | application 被 terminated。 |
| `iam.api_key.created` | API key 建立。 | tenant、group 或 application API key 被 issued。 |
| `iam.api_key.revoked` | API key revoke。 | API key 被 revoked。 |
| `iam.api_key.rotated` | API key rotation。 | API key 被 rotated key 取代。 |
| `iam.rate_limit_policy.created` | rate-limit policy 建立。 | IAM 建立 rate-limit policy。 |
| `iam.rate_limit_policy.updated` | rate-limit policy 更新。 | IAM 更新 rate-limit policy。 |
| `iam.rate_limit_policy.deleted` | rate-limit policy 刪除。 | IAM 刪除 rate-limit policy。 |
| `iam.rate_limit_policy.assigned` | rate-limit policy assignment。 | policy 被 assigned 到 target scope。 |
| `iam.guardrail_policy.created` | guardrail policy 建立。 | IAM 建立 guardrail policy。 |
| `iam.guardrail_policy.updated` | guardrail policy 更新。 | IAM 更新 guardrail policy。 |
| `iam.guardrail_policy.deleted` | guardrail policy 刪除。 | IAM 刪除 guardrail policy。 |
| `iam.guardrail_policy.assigned` | guardrail policy assignment。 | guardrail policy 被 assigned 到 app 或 group。 |
| `iam.provider_credential.created` | provider credential 建立。 | provider API credential metadata 被建立。 |
| `iam.provider_credential.rotated` | provider credential rotation。 | provider credential 被 rotated。 |
| `iam.provider_credential.revoked` | provider credential revoke。 | provider credential 被 revoked。 |
| `iam.provider_credential.deleted` | provider credential 刪除。 | provider credential record 被刪除。 |
| `iam.provider_definition.created` | provider definition 建立。 | admin 建立 provider definition。 |
| `iam.provider_definition.updated` | provider definition 更新。 | admin 更新 provider metadata 或 capabilities。 |
| `iam.provider_definition.deleted` | provider definition 刪除。 | admin 刪除 provider definition。 |
| `iam.model.created` | model 建立。 | IAM 建立 model resource。 |
| `iam.model.updated` | model 更新。 | IAM 更新 model metadata、endpoint 或 policy fields。 |
| `iam.model.deleted` | model 刪除。 | IAM 刪除或停用 model。 |
| `iam.application_model.bound` | application-model binding 建立。 | model 被 bound 到 application。 |
| `iam.application_model.reordered` | application-model priority/order 變更。 | application 的 model bindings 被 reordered。 |
| `iam.application_model.cost_updated` | application-model cost metadata 更新。 | per-model cost metadata 變更。 |
| `iam.application_model.unbound` | application-model binding 移除。 | model 被 unbound from application。 |
| `iam.deployment.created` | deployment 建立。 | IAM 建立 deployment record。 |
| `iam.deployment.updated` | deployment 更新。 | deployment metadata 或 config 變更。 |
| `iam.deployment.key_created` | deployment key 建立。 | deployment-scoped key 被 issued。 |
| `iam.deployment.key_revoked` | deployment key revoke。 | deployment key 被 revoked。 |
| `iam.deployment.key_assigned` | API key assigned to deployment。 | key 被 attached 到 deployment。 |
| `iam.deployment.key_unassigned` | API key removed from deployment。 | key 被 detached from deployment。 |
| `iam.deployment.endpoint_secret_rotated` | deployment endpoint secret rotation。 | deployment endpoint secret 被 rotated。 |
| `deployment.manifest.exported` | deployment manifest export attempt。 | manifest export 成功、被拒絕或發生錯誤。 |

## IAM Policy, Proxy, Catalog, Plugin, Skill, And Sandbox Audit

| Event | What it records | Triggered when |
| --- | --- | --- |
| `iam.policy_bundle.created` | legacy policy bundle 建立。 | IAM 建立 policy bundle。 |
| `iam.policy_bundle.status_changed` | legacy policy bundle status transition。 | policy bundle status 變更。 |
| `iam.policy_binding.created` | legacy policy binding 建立。 | IAM 建立 policy binding。 |
| `iam.policy_binding.status_changed` | legacy policy binding status transition。 | policy binding status 變更。 |
| `iam.policy_profile.created` | policy profile 建立。 | IAM 建立 policy profile。 |
| `iam.policy_profile.updated` | policy profile 更新。 | IAM 更新 profile limits 或 settings。 |
| `iam.policy_profile.deleted` | policy profile 刪除。 | IAM 刪除 policy profile。 |
| `iam.proxy.model_source_added` | proxy model-source membership 新增。 | model source 被加入 LLM proxy pool。 |
| `iam.proxy.model_source_removed` | proxy model-source membership 移除。 | model source 被從 LLM proxy pool 移除。 |
| `iam.proxy.connected` | consumer app 連到 proxy。 | proxy connection 被建立。 |
| `iam.proxy.active_switched` | active proxy connection 切換。 | consumer app 的 active proxy 變更。 |
| `iam.proxy.connections_reordered` | proxy connection order 變更。 | proxy connection priorities 被 reordered。 |
| `iam.proxy.deactivated` | proxy connection deactivated。 | proxy connection 被 deactivated。 |
| `iam.proxy.connection_removed` | proxy connection removed。 | proxy connection 被刪除。 |
| `iam.catalog.reconciled` | model catalog reconciliation。 | catalog batch reconcile 執行。 |
| `iam.catalog.deployment_created` | catalog deployment intent 建立。 | ModelDeployment intent 從 catalog 被建立。 |
| `iam.catalog.deployment_updated` | catalog deployment intent 更新。 | ModelDeployment intent 變更。 |
| `iam.catalog.deployment_stopped` | catalog deployment stopped。 | ModelDeployment intent 被 stopped。 |
| `iam.catalog.deployment_bound` | catalog deployment bound to app/model。 | deployment intent 被 bound 到 application 或 model。 |
| `iam.catalog.model_override_set` | manual model override set。 | admin 設定 catalog/model override。 |
| `iam.catalog.model_override_cleared` | manual model override cleared。 | admin 清除 catalog/model override。 |
| `audit.governance.cross_tenant_endpoint_bound` | cross-tenant endpoint binding。 | model endpoint override 指向另一個 tenant 的 backing deployment。 |
| `iam.plugin.definition_created` | plugin definition 建立。 | marketplace plugin definition 被建立。 |
| `iam.plugin.version_published` | plugin version publication。 | plugin version 被 published。 |
| `iam.plugin.installed` | plugin installation。 | plugin 被 installed for group。 |
| `iam.plugin.uninstalled` | plugin uninstallation。 | plugin 被 removed from group。 |
| `iam.skill.installed` | skill installation。 | skill 被 installed into group allowlist。 |
| `iam.skill.uninstalled` | skill uninstallation。 | skill 被 removed from group allowlist。 |
| `iam.skill.selections_updated` | application skill selections changed。 | app skill selection set 被更新。 |
| `iam.skill.reconciled` | skill deployment reconciled。 | skill resolver redeploy 或 reconcile drift。 |
| `iam.embedding_profile.created` | embedding profile 建立。 | IAM 建立 embedding profile。 |
| `iam.embedding_profile.updated` | embedding profile 更新。 | IAM 更新 embedding profile settings。 |
| `iam.embedding_profile.deleted` | embedding profile 刪除。 | IAM 刪除 embedding profile。 |
| `iam.embedding_profile.assigned` | embedding profile assignment。 | profile 被 assigned 到 app 或 group。 |
| `iam.group.default_embedding_set` | group default embedding profile set。 | group default embedding config 變更。 |
| `iam.group.default_policies_set` | group default policy set changed。 | group default rate-limit/guardrail policies 變更。 |
| `iam.group.oidc_mapping_created` | group OIDC mapping 建立。 | Keycloak/OIDC group 被 mapped 到 IAM group。 |
| `iam.group.oidc_mapping_deleted` | group OIDC mapping 刪除。 | OIDC group mapping 被移除。 |
| `iam.tenant.oidc_provision_mode_set` | tenant OIDC provision mode change。 | tenant group-provision mode 被更新。 |
| `iam.node_activation.issued` | node activation code issuance。 | admin issued node enrollment activation codes。 |
| `iam.node_activation.consumed` | node activation code consumption。 | node 在 enrollment 時 consumed activation code。 |
| `iam.responses_binding.created` | Responses binding 建立。 | IAM 記錄 stored-response binding。 |
| `iam.responses_binding.deleted` | Responses binding 刪除。 | IAM 刪除 stored-response binding。 |
| `iam.fleet_runtime.version_promoted` | Fleet runtime active version promotion。 | Fleet 回報 successful serving phase 並 advance active version。 |
| `iam.sandbox.execution_completed` | sandbox execution completion。 | sandbox execution 完成且 IAM 記錄結果。 |

## OIDC And SSO Audit

| Event | What it records | Triggered when |
| --- | --- | --- |
| `oidc.token_verified` | OIDC token verification。 | IAM 驗證 OIDC token。 |
| `oidc.mapping_lookup` | user mapping lookup。 | OIDC login flow 查詢 local mapping。 |
| `oidc.tenant_resolved` | tenant resolution。 | OIDC login 解析 tenant。 |
| `oidc.mapping_created` | auto-created user mapping。 | OIDC login auto-provisions user mapping。 |
| `oidc.group_resolved` | group resolution。 | OIDC login 解析 IAM group。 |
| `oidc.role_resolved` | role resolution。 | OIDC login 解析 role/capability。 |
| `oidc.platform_admin_downgraded` | platform admin role 被降級。 | OIDC role resolution 防止不安全的 platform-admin elevation。 |
| `oidc.auto_create_group_deprecated` | deprecated auto-create-group path 被使用。 | OIDC provisioning 命中 deprecated behavior。 |
| `oidc.session_issued` | console session issued。 | OIDC login 成功並發出 session。 |
| `oidc.login_rejected` | OIDC login rejected。 | IAM 因 mapping、trust、tenant 或 group rules 拒絕 login。 |
| `oidc.session_terminated` | console session terminated。 | logout 或 session termination path 執行。 |
| `oidc.mapping_reactivated` | user mapping reactivated。 | admin recovery 重新啟用 OIDC mapping。 |
| `oidc.mapping_emergency_unlocked` | emergency mapping unlock。 | admin emergency recovery unlocks mapping。 |
| `oidc.mapping_admin_created` | admin-created user mapping。 | admin 直接建立 OIDC mapping。 |
| `oidc.mapping_updated` | user mapping update。 | admin 更新 mapping fields。 |
| `oidc.mapping_deactivated` | user mapping deactivation。 | admin deactivates OIDC mapping。 |
| `oidc.tenant_group_binding.created` | tenant group binding creation。 | admin binds OIDC group to tenant/group behavior。 |
| `oidc.tenant_group_binding.deleted` | tenant group binding deletion。 | admin deletes OIDC tenant group binding。 |
| `oidc.mapping_tenant_succeeded` | mapping tenant succession。 | OIDC login auto-follows tenant succession rules。 |
| `oidc.mapping_offboarded` | mapping offboarded。 | OIDC empty-group/offboarding rule changes mapping state。 |
| `oidc.layer_conflict_detected` | OIDC layer conflict。 | Layer 1 與 Layer 2a resolution 都 match 但結果不一致。 |
| `oidc.unregistered_issuer_used` | transitional unregistered issuer used。 | registry fallback 在 registry empty 時接受 env issuer。 |
| `oidc.trusted_issuer.registered` | trusted issuer registration。 | admin registers OIDC trusted issuer。 |
| `oidc.trusted_issuer.deactivated` | trusted issuer deactivation。 | admin deactivates trusted issuer。 |
| `oidc.issuer_tenant_binding.created` | issuer-tenant binding creation。 | admin binds issuer to tenant。 |
| `oidc.issuer_tenant_binding.deactivated` | issuer-tenant binding deactivation。 | admin deactivates issuer-to-tenant binding。 |

## Versioned Policy And GitOps Policy Audit

| Event | What it records | Triggered when |
| --- | --- | --- |
| `policy.created` | policy object 建立。 | Versioned policy API 建立 policy object。 |
| `policy.version.created` | policy version 建立。 | Versioned policy API 建立新 version。 |
| `policy.version.published` | policy version publication。 | policy version 被 published。 |
| `policy.version.deprecated` | policy version deprecation。 | policy version 被 deprecated。 |
| `policy.version.revoked` | policy version revocation。 | policy version 被 revoked。 |
| `policy.default_moved` | default policy version 變更。 | default pointer 移到另一個 version。 |
| `bundle.created` | bundle object 建立。 | Versioned policy API 建立 bundle。 |
| `bundle.composition.updated` | bundle composition update。 | bundle membership/composition 被修改。 |
| `bundle.item.added` | bundle item addition。 | policy item 被加入 bundle。 |
| `bundle.item.replaced` | bundle item replacement。 | bundle item 被 replaced。 |
| `bundle.item.removed` | bundle item removal。 | policy item 被從 bundle 移除。 |
| `policy.grant.created` | policy grant creation。 | grant 被 created for policy or bundle。 |
| `policy.grant.revoked` | policy grant revocation。 | grant 被 revoked。 |
| `policy.binding.created` | versioned policy binding creation。 | policy 或 bundle 被 bound 到 target。 |
| `policy.binding.deactivated` | versioned policy binding deactivation。 | binding 被 deactivated。 |
| `policy.binding.window_updated` | binding effective window update。 | start/end/effective time window 變更。 |
| `policy.binding.invalidated` | binding invalidation。 | binding 被 policy model rules invalidated。 |
| `policy.drift.skipped` | GitOps policy drift 被偵測並 skipped。 | `sync_policies --apply` 發現 content drift 且繼續執行。 |
| `policy.bundle.activated` | GitOps policy bundle activated。 | GitOps apply 建立 active bundle row。 |
| `policy.bundle.deprecated` | GitOps policy bundle deprecated。 | GitOps apply deprecates orphan 或 old bundle。 |
| `policy.binding.activated` | GitOps policy binding activated。 | GitOps apply 建立 active binding row。 |
| `policy.binding.deprecated` | GitOps policy binding deprecated。 | GitOps apply disables orphan 或 old binding。 |
| `policy.binding.updated` | GitOps policy binding updated。 | GitOps apply 更新 binding assignment 或 precedence。 |

## Quota, Scheduler, And Resource Manager Audit

| Event | What it records | Triggered when |
| --- | --- | --- |
| `quota.node_allocation.created` | node allocation quota creation。 | IAM quota API 建立 tenant node allocation。 |
| `quota.node_allocation.updated` | node allocation quota update。 | IAM quota API 更新 node allocation。 |
| `quota.node_allocation.revoked` | node allocation quota revocation。 | IAM quota API revokes node allocation。 |
| `quota.group_quota.created` | group quota creation。 | IAM quota API 建立 group quota。 |
| `quota.group_quota.updated` | group quota update。 | IAM quota API 更新 group quota。 |
| `quota.app_resource.overridden` | application resource override。 | IAM quota API overrides app resource profile。 |
| `placement.requested` | placement request submitted。 | Scheduler 收到 non-dry-run placement request。 |
| `placement.completed` | placement became active。 | Scheduler consume node report 並將 pending placement 標記為 active。 |
| `placement.released` | placement released。 | Scheduler release endpoint 將 placement 轉出 active use。 |
| `placement.restarted` | placement restarted。 | Scheduler restart endpoint requests replacement/restart。 |
| `resource.lease.acquired` | endpoint capacity lease acquired。 | ResourceManager 經 queue/capacity checks 後 grant lease。 |
| `resource.lease.released` | endpoint capacity lease released。 | caller releases active lease。 |
| `resource.lease.reclaimed` | expired lease reclaimed。 | ResourceManager TTL reaper reclaims stale lease。 |
| `resource.queue.timeout` | endpoint queue wait timed out。 | lease request 超過 queue timeout。 |
| `resource.queue.full` | endpoint queue is full。 | lease request 到達時 max queue depth 已滿。 |

## Fleet And Node Manager Audit

| Event | What it records | Triggered when |
| --- | --- | --- |
| `fleet.node.registered` | Fleet node registration。 | Fleet 收到 unknown node 的 first heartbeat。 |
| `fleet.node.activated` | Fleet node 進入 active/approved/admitted state。 | node 被 approved、admitted 或 passes validation。 |
| `fleet.node.deactivated` | Fleet node deactivated。 | node 被 rejected、quarantined 或 fails validation。 |
| `fleet.node.removed` | Fleet node removal。 | node 從 Fleet state 移除。 |
| `node.plugin.template_synced` | plugin template synced to node host。 | Node manager plugin sync writes 或 overwrites template。 |
| `node.plugin.template_removed` | plugin template removed from node host。 | plugin sync 移除 image manifest 中不存在的 host file。 |
| `node.plugin.sync_completed` | plugin template sync completed。 | plugin sync 完成一個 cycle。 |
| `node.plugin.sync_failed` | plugin template sync failed。 | plugin sync 無法 load manifest 或發生 unrecoverable failure。 |
| `node.plugin.sync_skipped_readonly` | plugin sync skipped due to read-only target。 | host plugin directory 不可寫。 |
| `model_download_started` | local model download started。 | Node manager 啟動 artifact-store model download process。 |
| `model_download_cancelled` | local model download cancelled。 | operator cancels pending 或 active download。 |
| `model_deleted` | local model deleted。 | operator deletes downloaded local model。 |
| `model_instance_healthy` | model serving instance became healthy。 | vLLM health poll returns healthy。 |
| `model_serve_started` | model serving container started。 | Node manager starts vLLM serving container。 |
| `model_serve_stopped` | model serving container stopped。 | Node manager stops serving instance。 |
| `model_instance_restarted` | model serving instance restarted。 | Watchdog restarts failing container。 |
| `model_instance_error` | model serving instance marked error。 | Watchdog 或 runtime marks instance permanently errored。 |
| `deploy_failed` | service deployment failed。 | Node service deploy path 失敗，通常是 image pull 或 compose failure。 |
| `gateway_sync_failed` | Gateway model profile sync failed。 | Node service deploy 無法寫入 generated gateway profile。 |
| `apply` | service apply/deploy record。 | Node service apply path writes service state。 |
| `gateway_unsync_failed` | Gateway model profile removal failed。 | service delete 無法移除 gateway drop-in profile。 |
| `delete` | service delete record。 | Node service delete path removes deployed service。 |

## Legacy-Compatible Guardrail Names

以下名稱是 audit stats aggregation 為歷史資料保留的相容名稱。Current Gateway 會寫入上方列出的 `audit.guardrail.*` 名稱。

| Event | What it records | Triggered when |
| --- | --- | --- |
| `audit.execution.guardrail_input_check` | legacy input guardrail check name。 | 舊版 deployed Gateway builds 以此名稱記錄 input checks。 |
| `audit.execution.guardrail_output_check` | legacy output guardrail check name。 | 舊版 deployed Gateway builds 以此名稱記錄 output checks。 |
| `audit.execution.guardrail_blocked` | legacy guardrail blocked name。 | 舊版 deployed Gateway builds 以此名稱記錄 guardrail blocks。 |
| `audit.execution.guardrail_error` | legacy guardrail error name。 | 舊版 deployed Gateway builds 以此名稱記錄 guardrail errors。 |
| `guardrail_input_check` | pre-bridge input guardrail check name。 | audit bridge namespace mapping 前的 historical records。 |
| `guardrail_output_check` | pre-bridge output guardrail check name。 | audit bridge namespace mapping 前的 historical records。 |
| `guardrail_blocked` | pre-bridge guardrail blocked name。 | audit bridge namespace mapping 前的 historical records。 |
| `guardrail_error` | pre-bridge guardrail error name。 | audit bridge namespace mapping 前的 historical records。 |

## Known Gaps

| Area | Current state |
| --- | --- |
| API key expiration | 目前已有 `iam.api_key.created`、`iam.api_key.revoked`、`iam.api_key.rotated`。尚未看到明確的 `api_key.expiring_soon` 或 `api_key.expired` event。 |
| Usage threshold notifications | 目前已有 quota CRUD 與 ResourceManager queue/lease events。尚未看到明確的 threshold-crossed notification events。 |
| Routing module | `xparse_routing` 目前會寫 routing decision logs，但未看到直接 emit `routing.*` audit event 的 producer。 |
| Guardrail service | `xparse_guardrail` 本身回傳 verdict；audit events 由 Gateway 以 `audit.guardrail.*` 記錄。 |
| User added directly to tenant | 目前已有 group membership 與 OIDC mapping events；尚未看到獨立的 `tenant_user.added` event。 |
