# Default Policy / Default Policy Bundle Implementation Note

更新日期：2026-07-31  
相關 branch：`codex/tenant-default-policy-bundle`  
主 repo：`/Users/peter/Desktop/X-parse/xparse`

## 目標

當 system admin 建立 tenant 時，後端會自動建立一組 tenant-level default rate limit：

- 一個 default policy。
- 一個 default policy bundle。
- bundle 內只 pin 這個 default policy 的一個 `llm_operational` version。
- bundle 自動用 mandatory binding 綁到該 tenant。

這個 default resource 不是 `managed_by=system`。目前後端 enum 只有 `console` / `gitops`，所以實作採用：

- `managed_by = "console"`：仍在一般 Console / versioned policy 表面顯示。
- `system_default_role = "tenant_rate_limit"`：後端 computed marker，讓 API 與前端知道這是系統建立的 tenant default。

## Default Resource Identity

Default policy 與 default bundle 共用 reserved code：

```text
tenant-default-rate-limit
```

Default policy 內容：

```text
name = Default Rate Limit
description = <tenant name> system default policy
policy_kind = llm_operational
owner_scope_type = tenant
owner_scope_id = tenant_uuid
tenant_uuid = tenant_uuid
managed_by = console
level = tenant
system_default_role = tenant_rate_limit
```

Default policy bundle 內容：

```text
name = Default Rate Limit
description = <tenant name> system default policy set
owner_scope_type = tenant
owner_scope_id = tenant_uuid
tenant_uuid = tenant_uuid
managed_by = console
level = tenant
system_default_role = tenant_rate_limit
```

`<tenant name>` 來自 `Tenant.name`。如果 helper 被測試或舊工具用裸 UUID 呼叫，且找不到 tenant row，會 fallback 成 tenant UUID；如果 tenant name 是空字串，會 fallback 成 `tenant_code`。

新 tenant 初始 default rate-limit values：

```json
{
  "req_per_sec": 1.0,
  "burst": 5,
  "max_concurrency": 2,
  "max_queue_depth": 10,
  "queue_timeout_sec": 30
}
```

Policy version content 會用目前 schema 驗證後寫入：

```json
{
  "rate_limit": {
    "req_per_sec": 1.0,
    "burst": 5,
    "max_concurrency": 2,
    "max_queue_depth": 10,
    "queue_timeout_sec": 30
  },
  "limits": null
}
```

## Backend Workflow

### 1. Create Tenant

Tenant 建立流程會呼叫：

```text
create_tenant()
  -> seed_tenant_default_rate_limit(tenant_uuid)
```

`seed_tenant_default_rate_limit()` 是 normalizer，不只是 one-time seed。它會：

1. 先解析目前有效 default rate-limit。
2. 如果已有有效值，保留該值。
3. 如果沒有有效值，使用 platform default。
4. 讀取 `Tenant.name`，產生 default policy / bundle description。
5. 建立或修復 default policy identity。
6. 建立或修復 default bundle identity。
7. 建立或重用 matching active policy version。
8. 確保 default bundle 只有一個 item，且該 item pin 到 default policy version。
9. 確保 mandatory tenant binding 存在。
10. transaction commit 後重新讀取並驗證 post-condition。

這符合 ADR-093 的 state-changing safety pattern：

- pre-condition validation before writes
- atomic transaction
- post-condition re-read verification

### 2. Backfill / Normalize Existing Tenants

`backfill_tenant_default_rate_limit` command 會對所有 tenant 執行同一個 normalizer。

它會修復舊資料，例如：

- 沒有 `tenant-default-rate-limit` chain 的 tenant。
- 舊的 `managed_by=gitops` tenant default rows。
- 舊的空 description，或不符合目前 `<tenant name> system default ...` 規則的 description。
- 舊的 version label，例如 `"1"`。
- bundle 內有非 default item 或結構不符合目前規則。

有效的既有 rate-limit values 會被保留，不會直接覆蓋成新 default。

### 3. Authoring Rules

Default policy / bundle 的修改權限：

- 只有 `system_admin` 可以 author default policy version。
- 只有 `system_admin` 可以 replace default bundle item。
- default bundle item replacement 只能 pin 同一 tenant 的 default `llm_operational` policy version。
- replacement 必須使用 `replace=true`。
- tenant admin / group admin / developer / auditor 都不能改 default resource。

被禁止的 default resource mutation：

- HTTP 建立另一個 `code=tenant-default-rate-limit` 的 policy 或 bundle。
- rename / edit identity / lifecycle transition default policy。
- activate / deactivate / delete default policy version。
- set default-version pointer。
- edit / lifecycle transition default bundle。
- add unrelated bundle item。
- remove default bundle item。
- direct binding mutation / unbind default mandatory binding。

### 4. Legacy Endpoint

舊的 tenant default endpoint 仍保留作為 compatibility path：

```text
PATCH /iam/tenants/{tenant_uuid}/default-rate-limit
```

它仍然只允許 `system_admin` 使用。內部行為也改成：

1. seed / normalize default chain。
2. 建立新的 immutable policy version。
3. replace default bundle item 到新 version。
4. 重新 resolve 並回傳有效值。

## API Response Changes

Versioned policy API 現在會把 computed default marker 回傳給 Console。

Policy response：

```json
{
  "name": "Default Rate Limit",
  "description": "<tenant name> system default policy",
  "system_default_role": "tenant_rate_limit"
}
```

Bundle response：

```json
{
  "name": "Default Rate Limit",
  "description": "<tenant name> system default policy set",
  "system_default_role": "tenant_rate_limit"
}
```

Binding / effective binding response：

```json
{
  "bundle_system_default_role": "tenant_rate_limit"
}
```

前端不需要從 `code` 字串推論 default resource；直接使用這些 marker。

## Frontend Workflow

### 1. Display

Default policy、default policy bundle、default bundle item 會顯示 `System` tag。

這個 tag 代表：

- row 是系統建立的 tenant default。
- 一般 tenant / group actor 只能讀，不能直接修改。
- system admin 才能透過受限流程 author。

### 2. Non-System Admin UX

當 actor 不是 `system_admin` 時：

- default policy item disabled。
- default policy version picker disabled。
- default policy action menu disabled。
- default policy row navigation disabled。
- default policy set row disabled。
- default bundle item disabled。
- default bundle item view-content / expand / navigation disabled。
- default binding unbind disabled。

### 3. System Admin UX

當 actor 是 `system_admin` 時：

- 可以在 default policy detail 建立新的 policy version。
- 不能改 identity / lifecycle / default pointer。
- 可以在 default bundle detail replace item。
- replace picker 只允許選同一個 default `llm_operational` policy 的 active version。
- default binding 仍不可直接 unbind，因為它是 default chain 的 structural binding。

## Files Involved

### Backend Source

```text
/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/db/django_database/_tenant_default_rate_limit.py
/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/api/ninja_api/_versioned_policies.py
/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/api/ninja_api/_tenants.py
/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/api/schemas/_versioned_policy.py
/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/management/commands/backfill_tenant_default_rate_limit.py
/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/management/commands/sync_policies.py
```

### Backend Tests

```text
/Users/peter/Desktop/X-parse/xparse/xparse_iam/tests/unit/test_adr332_tenant_default_rate_limit.py
/Users/peter/Desktop/X-parse/xparse/xparse_iam/tests/unit/test_adr332_tenant_default_authoring.py
/Users/peter/Desktop/X-parse/xparse/xparse_iam/tests/unit/test_adr332_default_rate_limit_api.py
/Users/peter/Desktop/X-parse/xparse/xparse_iam/tests/unit/test_adr332_backfill_and_planner.py
/Users/peter/Desktop/X-parse/xparse/xparse_iam/tests/integration/test_versioned_policy_api.py
```

### Frontend Source

```text
/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/types/iam.ts
/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/lib/policy-default-authority.ts
/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/lib/policy-binding-authority.ts
/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/app/(main)/(ai-gateway)/_components/policy-format.tsx
/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/app/(main)/(ai-gateway)/policies/individual-policy/page.tsx
/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/app/(main)/(ai-gateway)/policies/individual-policy/[policy-id]/page.tsx
/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/app/(main)/(ai-gateway)/policies/set/page.tsx
/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/app/(main)/(ai-gateway)/policies/set/[bundle-id]/page.tsx
/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/app/(main)/(ai-gateway)/policies/_components/policy/policy-collapse-item.tsx
/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/app/(main)/(ai-gateway)/policies/_components/policy/policy-item-actions.tsx
/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/app/(main)/(ai-gateway)/policies/_components/policy/policy-version-actions.tsx
/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/app/(main)/(ai-gateway)/policies/_components/policy/policy-version-select.tsx
/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/app/(main)/(ai-gateway)/policies/_components/policy/policy-batch-actions.tsx
/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/app/(main)/(ai-gateway)/policies/_components/bundle/policy-bundle-detail.tsx
/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/app/(main)/(ai-gateway)/policies/_components/bundle/add-bundle-item-dialog.tsx
/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/app/(main)/(ai-gateway)/policies/_components/bundle/policy-version-selection-table.tsx
/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/app/(main)/(ai-gateway)/policies/_components/bundle/policy-bundle-status-actions.tsx
/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/app/(main)/(ai-gateway)/policies/_components/bundle/policy-bundle-batch-actions.tsx
```

### Frontend Tests

```text
/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/lib/policy-binding-authority.test.ts
```

### External Note

This file is outside the git repo:

```text
/Users/peter/Desktop/X-parse/docs/default-policy.md
```

It documents the change but is not included in the `xparse` repo pull request unless copied into `/Users/peter/Desktop/X-parse/xparse/docs/`.

## Verification Run

Frontend:

```text
pnpm typecheck
pnpm test:run src/lib/policy-binding-authority.test.ts
pnpm exec prettier --check <changed frontend files>
```

Backend:

```text
PYTHONPATH=.:xparse_iam:3rd/xparse_audit/src xparse_iam/.venv/bin/python -m pytest -c pytest.ini \
  xparse_iam/tests/unit/test_adr332_tenant_default_rate_limit.py \
  xparse_iam/tests/unit/test_adr332_tenant_default_authoring.py \
  xparse_iam/tests/unit/test_adr332_default_rate_limit_api.py \
  xparse_iam/tests/unit/test_adr332_backfill_and_planner.py \
  xparse_iam/tests/integration/test_versioned_policy_api.py \
  -k 'TenantDefaultRateLimitAuthoringAPI or effective_bundle_bindings_include_inherited_lineage or not integration'
```

Static diff check:

```text
git diff --check
```

Observed result:

```text
frontend typecheck: passed
frontend policy-binding-authority tests: 18 passed
backend affected tests: 28 passed, 48 deselected
git diff --check: passed
```

## Operational Notes

- Do not use `managed_by=system`; the database/API enum does not support it.
- Use `system_default_role` / `bundle_system_default_role` as the source of truth for UI and API authority.
- Existing GitOps-managed default rows are normalized to the current console-managed + computed-marker shape.
- `tenant-default-rate-limit` is now reserved for this system-created default chain.
- `dump.rdb` was present as an unrelated untracked file and should not be included in the PR.
