# Role Mapping & Permit Workflow

This document describes the complete flow from account creation to page capability resolution in Xparse — covering every component, table, and file involved.

---

## Overview

The system has three distinct phases:

1. **Setup** — Admin pre-configures role mappings in the DB (done once per deployment)
2. **Login** — User authenticates via Keycloak; IAM creates a session key with a role FK
3. **Capability Resolution** — On every capabilities request, IAM reads the role's page permissions from DB and returns them to the frontend

Capabilities are stored at the **role level** (shared across all users with the same role), not the user level. A session key carries only a foreign key (`console_role_id`) pointing to a `ConsoleRole` record.

---

## Data Model

```
OIDCRoleMapping          TenantAPIKey              ConsoleRole
─────────────────        ──────────────────        ──────────────────────────
external_role (str)  →   console_role_id (FK) →    role_uuid
console_role (FK)        key_type                  name (e.g. "system_admin")
provider                 status                    scope_level
tenant (nullable)        expires_at                ui_capabilities (JSON)
priority                 oidc_mapping (FK)         is_builtin
                                                   policy_bindings
```

**Key point:** `ConsoleRole.ui_capabilities` is the single source of truth for page permissions. It is a JSON field containing one entry per page (`page_id → PageCapability`). All users assigned to the same `ConsoleRole` share this data.

### Relevant files

| Component             | File                                      |
| --------------------- | ----------------------------------------- |
| ConsoleRole model     | `xparse_iam/xparse_iam/db/models/auth.py` |
| TenantAPIKey model    | `xparse_iam/xparse_iam/db/models/auth.py` |
| OIDCRoleMapping model | `xparse_iam/xparse_iam/db/models/auth.py` |
| OIDCUserMapping model | `xparse_iam/xparse_iam/db/models/auth.py` |

---

## Phase 1 — Setup (One-time, done by admin)

### 1.1 ConsoleRole records seeded via migrations

Built-in roles are created in the DB by Django migrations. Each role has a `ui_capabilities` JSON field that defines which pages it can access.

**Built-in roles:**

| Role name         | Scope           | Description             |
| ----------------- | --------------- | ----------------------- |
| `system_admin`    | system (global) | Full platform access    |
| `tenant_admin`    | tenant          | Manage own tenant       |
| `tenant_auditor`  | tenant          | Read-only within tenant |
| `group_admin`     | group           | Manage own group        |
| `group_developer` | group           | Manage own applications |
| `app_user`        | tenant          | Agent app portal only   |

**Migration history:**

| Migration                                | What it does                                                                                             |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `0036_console_role.py`                   | Seeds system_admin, tenant_admin, tenant_auditor, group_admin (initial, incomplete — missing many pages) |
| `0046_group_developer_console_role.py`   | Seeds group_developer role                                                                               |
| `0058_agent_app_phase1.py`               | Seeds app_user role (ADR-110)                                                                            |
| `0063_seed_app_user_group_developer.py`  | Re-seeds group_developer and app_user with more complete page list                                       |
| `0069_consolerole_add_member_actions.py` | Adds `add_member`/`remove_member` actions to groups page                                                 |
| `0101_seed_infra_admin_console_role.py`  | Seeds custom infra_admin role                                                                            |
| `0126_consolerole_add_tenants_page.py`   | Hotfix — adds `tenants` page to system_admin, tenant_admin, tenant_auditor                               |

All migration files are located at:

```
xparse_iam/xparse_iam/migrations/
```

### 1.2 OIDCRoleMapping records configured by admin

The `OIDCRoleMapping` table maps an external Keycloak role string to a `ConsoleRole` record. This table is what connects a Keycloak identity to an IAM capability set.

**Default global mappings (seeded in migration 0036):**

| Keycloak role    | → ConsoleRole    |
| ---------------- | ---------------- |
| `platform_admin` | `system_admin`   |
| `tenant_auditor` | `tenant_auditor` |

Additional tenant-scoped mappings can be configured per-tenant by admins via the IAM API.

**Resolution logic** (`xparse_iam/xparse_iam/core/oidc.py` — `_resolve_console_role()`):

1. Check tenant-scoped `OIDCRoleMapping` records first (ordered by `-priority`)
2. Fall back to global mappings (`tenant=NULL`)
3. If no mapping matches → legacy `key_type` fallback

---

## Phase 2 — Login Flow

Every login triggers a full session key rotation. Previous session keys are revoked.

```
Browser
  │
  ├─► Keycloak (authenticate)
  │     └─ ID token returned (contains realm_access.roles)
  │
  └─► POST /iam/oidc/exchange  (sends ID token)
        │
        │  File: xparse_iam/xparse_iam/api/ninja_api/_oidc.py
        │  Handler: oidc_exchange()  →  core/oidc.py: exchange_token()
        │
        ├─ 1. Verify ID token (signature, expiry, audience, issuer)
        │
        ├─ 2. Resolve or create OIDCUserMapping
        │      (maps OIDC subject → IAM user record)
        │      File: xparse_iam/xparse_iam/db/models/auth.py :: OIDCUserMapping
        │
        ├─ 3. Extract Keycloak roles from token claims
        │      claims["realm_access"]["roles"]
        │      e.g. ["platform_admin", "default-roles-xparse"]
        │
        ├─ 4. Resolve ConsoleRole  ← _resolve_console_role()
        │      File: xparse_iam/xparse_iam/core/oidc.py
        │
        │      a. Query OIDCRoleMapping (tenant-scoped first, then global)
        │         "platform_admin" → ConsoleRole(system_admin)
        │
        │      b. If no match → legacy fallback:
        │         "platform_admin" in roles → key_type = "platform_admin"
        │         "tenant_admin" in roles  → key_type = "tenant_admin"
        │         anything else            → key_type = "console_session" (least privilege)
        │
        ├─ 5. Enforce scope guard (_enforce_platform_admin_tenant_scope)
        │      Prevents system_admin from binding to a non-global tenant scope
        │
        ├─ 6. Revoke all previous active session keys for this OIDC user
        │      TenantAPIKey.objects.filter(oidc_mapping=mapping, status=ACTIVE).update(REVOKED)
        │
        ├─ 7. Create new TenantAPIKey
        │      key_type        = "platform_admin"   (derived from ConsoleRole.name)
        │      console_role_id = ConsoleRole.role_uuid  ← only an FK, not capabilities
        │      oidc_mapping    = OIDCUserMapping
        │      expires_at      = now + XPARSE_OIDC_SESSION_TTL_HOURS (default 8h)
        │
        └─ 8. Return session_key to frontend
```

**The session key stores only `console_role_id` (a FK). Capabilities are NOT copied into the session key or the user record.**

---

## When `console_role_id` is NULL

`TenantAPIKey.console_role` is `null=True` (`xparse_iam/xparse_iam/db/models/auth.py:220–222`). A session key can be created without a `console_role_id` in the following situations:

### Situation 1 — No OIDCRoleMapping matches (most common)

During login, `_resolve_console_role()` (`xparse_iam/xparse_iam/core/oidc.py:692`) queries `OIDCRoleMapping` for any of the user's Keycloak roles. Only **two global mappings exist by default** (seeded in `migration 0036`):

| Keycloak role    | → ConsoleRole    |
| ---------------- | ---------------- |
| `platform_admin` | `system_admin`   |
| `tenant_auditor` | `tenant_auditor` |

The following roles have **no default global mapping**:

| Keycloak role     | Default global mapping                           |
| ----------------- | ------------------------------------------------ |
| `tenant_admin`    | ❌ None — must be configured per-tenant by admin |
| `group_admin`     | ❌ None                                          |
| `group_developer` | ❌ None                                          |
| `app_user`        | ❌ None                                          |

If a user holds one of these roles and no tenant-scoped `OIDCRoleMapping` has been configured, `_resolve_console_role()` returns `None`. The session key is created via the legacy key_type path, and `console_role_id` is NULL.

### Situation 2 — Old API keys (pre-migration 0036)

API keys created before `ConsoleRole` existed have no `console_role_id`. These are legacy keys and hit the legacy capability path.

### Consequence of NULL `console_role_id`

When `auth_context` has no `console_role_id`, `resolve_capabilities()` (`xparse_iam/xparse_iam/api/console_capabilities.py:977`) falls through to the **legacy path**, which reads directly from the hardcoded `CAPABILITY_MATRIX` Python dict instead of the DB.

---

## Phase 3 — Capability Resolution (Per Request)

Every time the frontend loads or refreshes, it calls `GET /iam/console/capabilities`. The response tells the frontend which sidebar pages to show and which actions to enable.

```
Frontend
  │
  └─► GET /iam/console/capabilities  (Authorization: Bearer <session_key>)
        │
        │  File: xparse_iam/xparse_iam/api/ninja_api/_app_auth.py  (auth layer)
        │  File: xparse_iam/xparse_iam/api/console_capabilities.py (resolution)
        │
        ├─ 1. Validate session_key → build auth_context dict
        │      auth_context = {
        │        "console_role_id": "uuid-of-console-role",
        │        "tenant_uuid": "...",
        │        "group_uuid": "...",
        │        "oidc_mapping_uuid": "...",
        │        ...
        │      }
        │
        ├─ 2. resolve_capabilities(auth_context)
        │      File: xparse_iam/xparse_iam/api/console_capabilities.py
        │
        │      Path A — DB-driven (has console_role_id):
        │        └─ _resolve_from_db_role(console_role_id, auth_context)
        │             ├─ Query ConsoleRole by UUID
        │             ├─ For each page in PAGE_ORDER:
        │             │    if page in role.ui_capabilities → use DB value
        │             │    else → fallback to CAPABILITY_MATRIX[page][role.name]
        │             ├─ Apply service availability filter  (PRD-083)
        │             ├─ Apply feature flag ceiling         (PRD-134 / ADR-164)
        │             └─ Apply OIDC mapping gate for my_deployments (PRD-123)
        │
        │      Path B — Legacy fallback (no console_role_id):
        │        └─ derive_ui_role(auth_context)  → reads CAPABILITY_MATRIX directly
        │             File: xparse_iam/xparse_iam/authorization/role_derivation.py
        │
        ├─ 3. evaluate_allowed_actions(auth_context)
        │      File: xparse_iam/xparse_iam/api/console_capabilities.py
        │      Runs PDP evaluation against system_policy_seed.py rules
        │      Returns list of allowed action strings (e.g. "application.create")
        │
        └─ 4. Return to frontend:
               {
                 "ui_role": "system_admin",
                 "visibility_scope": "global",
                 "visible_pages": ["dashboard", "tenants", "fleet", ...],
                 "pages": { "dashboard": { "visible": true, "actions": [...] }, ... },
                 "allowed_actions": ["application.create", "group.read", ...],
                 "services": { "iam": true, "audit": true, "fleet": true, ... },
                 "scope_mode": "tenant",
                 "my_deployments_visible": false
               }
```

---

## Capability Sources: How Priority Works

For the DB path, pages are resolved in this priority order:

```
1. ConsoleRole.ui_capabilities (DB)          ← authoritative for built-in and custom roles
       ↓ page not found in DB?
2. CAPABILITY_MATRIX[page][role.name]        ← runtime fallback for missing pages only
       ↓ page not in CAPABILITY_MATRIX either?
3. HIDDEN_CAPABILITY                         ← default: not visible
```

**Critical caveat:** If a page IS present in the DB but with wrong values (e.g. `settings: hidden`), the fallback does NOT fire. The wrong DB value wins. This is the root cause of the current `settings` page bug affecting `tenant_admin`, `tenant_auditor`, `group_admin`, `group_developer`, and `app_user`.

### File locations

| Component                                          | File                                                        |
| -------------------------------------------------- | ----------------------------------------------------------- |
| `CAPABILITY_MATRIX` (Python, reference + fallback) | `xparse_iam/xparse_iam/api/console_capabilities.py`         |
| `resolve_capabilities()`                           | `xparse_iam/xparse_iam/api/console_capabilities.py`         |
| `_resolve_from_db_role()`                          | `xparse_iam/xparse_iam/api/console_capabilities.py`         |
| `CAPABILITY_MATRIX` (frontend mirror)              | `frontend/console-app/src/services/pageCapabilities.ts`     |
| System policy seed (action rules)                  | `xparse_iam/xparse_iam/authorization/system_policy_seed.py` |
| Role derivation (legacy path)                      | `xparse_iam/xparse_iam/authorization/role_derivation.py`    |
| Feature flag definitions                           | `xparse_iam/xparse_iam/authorization/feature_flags.py`      |
| IAM PEP (authorization entry point)                | `xparse_iam/xparse_iam/authorization/iam_pep.py`            |

---

## Page Capability Matrix (Current — CAPABILITY_MATRIX)

The authoritative definition of which role can access which page. Used both as the frontend display matrix and the backend fallback for pages missing from DB roles.

| Page             | system_admin | tenant_admin | tenant_auditor |   group_admin   | group_developer |   app_user   |
| ---------------- | :----------: | :----------: | :------------: | :-------------: | :-------------: | :----------: |
| dashboard        | ✅ RW global | ✅ RW tenant |  👁 RO tenant  |   ✅ RW group   |   👁 RO group   |      ❌      |
| my_deployments ¹ | 👁 RO tenant | 👁 RO tenant |  👁 RO tenant  |  👁 RO tenant   |  👁 RO tenant   |      ❌      |
| tenants          | ✅ RW global |      ❌      |       ❌       |       ❌        |       ❌        |      ❌      |
| fleet            | ✅ RW global |      ❌      |       ❌       |       ❌        |       ❌        |      ❌      |
| resources        | ✅ RW global | ✅ RW tenant |  👁 RO tenant  |   ✅ RW group   |   👁 RO group   |      ❌      |
| images           | ✅ RW global |      ❌      |       ❌       |       ❌        |       ❌        |      ❌      |
| applications     | ✅ RW global | ✅ RW tenant |  👁 RO tenant  |   ✅ RW group   |   ✅ RW group   |      ❌      |
| groups           | ✅ RW global | ✅ RW tenant |  👁 RO tenant  | ✅ RW own_group | 👁 RO own_group |      ❌      |
| profiles         | ✅ RW global | ✅ RW tenant |  👁 RO tenant  |       ❌        |       ❌        |      ❌      |
| credentials      | ✅ RW global | ✅ RW tenant |  👁 RO tenant  |       ❌        |       ❌        |      ❌      |
| marketplace      | ✅ RW global | ✅ RW tenant |  👁 RO tenant  |   ✅ RW group   |   👁 RO group   |      ❌      |
| runtime          | 👁 RO global | 👁 RO tenant |  👁 RO tenant  |   👁 RO group   |   👁 RO group   |      ❌      |
| audit            | ✅ RW global | ✅ RW tenant |  👁 RO tenant  |   👁 RO group   |   👁 RO group   |      ❌      |
| settings         | ✅ RW global | ✅ RW tenant |  👁 RO tenant  |   ✅ RW group   |   ✅ RW group   | ✅ RW tenant |
| app_launcher     | 👁 RO global | 👁 RO tenant |  👁 RO tenant  |   👁 RO group   |   👁 RO group   | 👁 RO tenant |
| identity         | ✅ RW global | ✅ RW tenant |  👁 RO tenant  |       ❌        |       ❌        |      ❌      |

> ¹ `my_deployments` has an additional runtime gate: session must have `oidc_mapping_uuid` (i.e. SSO login, not API key). Applied by `_apply_oidc_mapping_gate()`.

---

## Known Issues

### Issue 1: Dual source of truth (architectural)

Two capability sources exist in parallel with no automated sync:

| Source                                | File                                                   | When used                                                   |
| ------------------------------------- | ------------------------------------------------------ | ----------------------------------------------------------- |
| `ConsoleRole.ui_capabilities` (DB)    | `xparse_iam/xparse_iam/db/models/auth.py`              | DB path — evaluated first when `console_role_id` is present |
| `CAPABILITY_MATRIX` (Python hardcode) | `xparse_iam/xparse_iam/api/console_capabilities.py:56` | Two scenarios (see below)                                   |

**`CAPABILITY_MATRIX` is used in exactly two scenarios:**

**Scenario A — Legacy path** (`console_capabilities.py:994–1009`): triggered when `auth_context` has no `console_role_id`. The entire page map is built from Python. Affected users: those without a matching `OIDCRoleMapping`, or holders of pre-migration-0036 API keys.

**Scenario B — New-page fallback** (`console_capabilities.py:896–907`): triggered inside `_resolve_from_db_role()` when `console_role_id` IS present but a specific `page_id` key is missing from `role.ui_capabilities`. This prevents newly-added pages from showing as hidden during the window between code deploy and migration run.

```python
# _resolve_from_db_role() line 902–907
for page_id in PAGE_ORDER:
    if page_id in role.ui_capabilities:      # key exists in DB → use DB value (right or wrong)
        pages[page_id] = role.ui_capabilities[page_id]
    else:                                     # key missing from DB → use CAPABILITY_MATRIX
        matrix_entry = CAPABILITY_MATRIX.get(page_id, {})
        pages[page_id] = matrix_entry.get(role.name, HIDDEN_CAPABILITY)
```

**Critical constraint:** The fallback fires only when the page key is **absent** from DB. If the key exists in DB with a wrong value, the wrong value wins and the fallback never fires. This is the root cause of Issue 2.

Any change to `CAPABILITY_MATRIX` has no effect for users with a `console_role_id` unless the DB is also updated via a migration.

### Issue 2: Settings page hidden for 5 roles (live bug)

**Root cause timeline:**

1. `migration 0036_console_role.py` (`xparse_iam/xparse_iam/migrations/0036_console_role.py:70, 93, 117`) seeded `settings: hidden` for `tenant_admin`, `tenant_auditor`, and `group_admin` — this was the original design.
2. `migration 0058_agent_app_phase1.py` and `0063_seed_app_user_group_developer.py` seeded the same `hidden` value for `group_developer` and `app_user`.
3. PRD-127 later changed the requirement: settings must be visible to **all roles** (each within their own scope).
4. `CAPABILITY_MATRIX` in `console_capabilities.py:396–438` was updated to reflect PRD-127 (all roles → visible).
5. **No migration was written to update the DB.** The `settings` key now exists in DB with the old `hidden` value.
6. Because the key exists (even though wrong), `_resolve_from_db_role()` uses the DB value and the CAPABILITY_MATRIX fallback never fires.

**Consequence:**

- Users with roles `tenant_admin`, `tenant_auditor`, `group_admin`, `group_developer`, `app_user` have **no Settings entry in their sidebar**.
- They cannot access tenant-level or group-level settings (OIDC config, provider keys, group metadata, etc.) through the console UI.
- Direct URL navigation to `/settings` is also blocked (`route_access: false`).
- The bug is invisible to `system_admin` (their `settings` key in DB is present and partially correct — only `manage_platform` action is missing).
- Fixing `CAPABILITY_MATRIX` alone does nothing for these users, because they all have `console_role_id` and hit the DB path exclusively.

**PRD-127 requires settings to be visible to all roles.**

Affected roles — DB value vs required value:

| Role              | DB value                | Required value                           | Migration that set it                   |
| ----------------- | ----------------------- | ---------------------------------------- | --------------------------------------- |
| `tenant_admin`    | `hidden`                | `read_write`                             | `0036_console_role.py:70`               |
| `tenant_auditor`  | `hidden`                | `read_only`                              | `0036_console_role.py:93`               |
| `group_admin`     | `hidden`                | `read_write`                             | `0036_console_role.py:117`              |
| `group_developer` | `hidden`                | `read_write`                             | `0063_seed_app_user_group_developer.py` |
| `app_user`        | `hidden`                | `read_write`                             | `0058_agent_app_phase1.py`              |
| `system_admin`    | `actions: [view, edit]` | `actions: [view, edit, manage_platform]` | `0036_console_role.py:41`               |

### Issue 3: Four frontend pages not in backend CAPABILITY_MATRIX

The frontend `pageCapabilities.ts` defines capability matrices for pages that do not exist in the backend `console_capabilities.py`:

| Page         | Defined in frontend | Defined in backend |
| ------------ | :-----------------: | :----------------: |
| `llm_proxy`  |         ✅          |         ❌         |
| `onboarding` |         ✅          |         ❌         |
| `my_tenant`  |         ✅          |         ❌         |
| `models`     |         ✅          |         ❌         |

---

## Proposed Fix

### Step 1 — Full-overwrite migration (fixes Issues 1 & 2)

Write a single migration that **completely overwrites** `ui_capabilities` for all built-in roles using a snapshot of `CAPABILITY_MATRIX` as the source. Must be a full overwrite (not additive) to correct explicitly-wrong values like `settings: hidden`.

```python
# Pseudocode — actual migration must hardcode a snapshot, not import CAPABILITY_MATRIX
for role_name, pages in CAPABILITY_MATRIX_SNAPSHOT.items():
    role = ConsoleRole.objects.get(name=role_name, is_builtin=True)
    role.ui_capabilities = pages  # full overwrite
    role.save()
```

Only touches `is_builtin=True` roles. Custom roles are not affected.

### Step 2 — Remove legacy fallback from resolve_capabilities()

After the migration, the legacy CAPABILITY_MATRIX path in `resolve_capabilities()` and the in-function fallback in `_resolve_from_db_role()` can be removed. DB becomes the only runtime source.

```python
# After Step 2: no console_role_id → return empty capabilities
return {**base, "ui_role": None, "visibility_scope": None,
        "allowed_actions": [], "pages": {}, "visible_pages": []}
```

### Step 3 — Mark CAPABILITY_MATRIX as documentation-only

Add a docstring to `CAPABILITY_MATRIX` in `console_capabilities.py` making clear it is a reference template for writing migrations, not a runtime source. Do not delete it — it is valuable for authoring future migrations.

---

## Related Files Quick Reference

```
xparse_iam/xparse_iam/
├── api/
│   ├── console_capabilities.py       # CAPABILITY_MATRIX, resolve_capabilities(), PAGE_ORDER
│   └── ninja_api/
│       ├── _oidc.py                  # POST /iam/oidc/exchange endpoint
│       └── _app_auth.py              # Session key auth layer
├── core/
│   └── oidc.py                       # exchange_token(), _resolve_console_role()
├── authorization/
│   ├── system_policy_seed.py         # Policy rules (action-level permissions)
│   ├── role_derivation.py            # Legacy key_type → SystemRole derivation
│   ├── feature_flags.py              # Feature flag tri-state ceiling
│   └── iam_pep.py                    # Authorization entry point (PDP)
├── db/
│   └── models/auth.py                # ConsoleRole, TenantAPIKey, OIDCRoleMapping, OIDCUserMapping
└── migrations/
    ├── 0036_console_role.py          # Initial ConsoleRole seed (incomplete)
    ├── 0046_group_developer_console_role.py
    ├── 0058_agent_app_phase1.py      # app_user role
    ├── 0063_seed_app_user_group_developer.py
    ├── 0069_consolerole_add_member_actions.py
    ├── 0101_seed_infra_admin_console_role.py
    └── 0126_consolerole_add_tenants_page.py  # Hotfix for tenants page drift

frontend/console-app/src/
└── services/
    └── pageCapabilities.ts           # Frontend mirror of CAPABILITY_MATRIX
```

1. CAPABILITY_MATRIX 是什麼？

它是一個 Python hardcode 的 dict，位於：
xparse_iam/xparse_iam/api/console_capabilities.py:56

結構是 page_id → role_name → PageCapability：

CAPABILITY_MATRIX = {
"dashboard": {
"system_admin": { "visible": True, "mode": "read_write", ... },
"tenant_admin": { "visible": True, "mode": "read_write", ... },
"tenant_auditor": { "visible": True, "mode": "read_only", ... },
...
},
"settings": {
"system_admin": { "visible": True, "mode": "read_write", ... },
"tenant_admin": { "visible": True, ... }, # ← Python 說 visible
...
}
}

它的定位是什麼：

┌──────────┬────────────────────────────────────────────────────────┐
│ 身份 │ 說明 │
├──────────┼────────────────────────────────────────────────────────┤
│ 設計意圖 │ 寫 migration 的參考模板，migration 從這裡抄資料存進 DB │
├──────────┼────────────────────────────────────────────────────────┤
│ 實際運作 │ 兩種 runtime fallback（見下方第 3 點） │
├──────────┼────────────────────────────────────────────────────────┤
│ 不是 │ 唯一的真實來源，DB 才是 │
└──────────┴────────────────────────────────────────────────────────┘

---

2. 用戶登入時 role mapping 看哪張表？

流程是三張表依序查：

Keycloak token
│ claims["realm_access"]["roles"] = ["tenant_admin", ...]
│
▼
① OIDCRoleMapping ← 第一張查的表
db_table = "oidc_role_mappings"
先查 tenant-scoped（priority 高者優先）
再查 global（tenant=NULL）
│
│ 找到 → 取得 ConsoleRole FK
│ 找不到 → 走 legacy key_type fallback（不查 DB，hardcode 判斷）
│
▼
▼
③ TenantAPIKey ← 最終建立的 session key
db_table = "tenant_api_keys"
帶著 console_role_id 回傳給前端

重點：session key 裡只存 console_role_id（FK），不複製任何頁面權限資料進去。

---

3. IAM 回應前端「你可以看哪些 page」時看哪張表？

前端每次呼叫 GET /iam/console/capabilities，IAM 執行 resolve_capabilities()，查詢順序如下：

auth_context.console_role_id 有值？
│
├─ YES → Path A（DB-driven）
│ ↓
│ ① ConsoleRole.ui_capabilities ← 主要來源（DB JSON 欄位）
│ for page_id in PAGE_ORDER:
│ if page_id IN role.ui_capabilities:
│ 用 DB 的值 ← 即使值是錯的也用這個
│ else:
│ ↓
│ ② CAPABILITY_MATRIX fallback ← 次要來源（只有 DB 沒這個 key 才用）
│ 如果連這裡也沒有：
│ ③ HIDDEN_CAPABILITY ← 兜底（hidden）
│
└─ NO → Path B（Legacy）
↓
直接讀 CAPABILITY_MATRIX ← 整張 Python dict
（適用於沒有 OIDCRoleMapping 對應的使用者）

---

三者關係一覽

Migration 建立時 登入時 每次 GET /capabilities
───────────────── ──────────────── ──────────────────────
CAPABILITY_MATRIX OIDCRoleMapping ConsoleRole.ui_capabilities
（Python hardcode） →seed→ （查這張，找 ConsoleRole） （主要來源，DB JSON）
│ │ │
└──────────────────────────────→│──────────────────────→ │
migration 把它的內容 如果 key 不在 DB：
寫進 ConsoleRole.ui_capabilities CAPABILITY_MATRIX fallback

---

為什麼 settings Bug 會發生？

CAPABILITY_MATRIX["settings"]["tenant_admin"] = { visible: true } ← Python 已改
ConsoleRole.ui_capabilities["settings"] = { visible: false } ← DB 沒改

Path A 執行時：
page_id "settings" IN role.ui_capabilities → YES
→ 用 DB 值：visible = false ✗
→ CAPABILITY_MATRIX fallback 永遠不觸發

所以改 Python code 沒用，一定要寫 migration 覆寫 DB 裡的 ui_capabilities。
