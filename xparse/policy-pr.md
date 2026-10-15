# ADR-191 Policy-as-Code 實作報告

## 概覽

這 10 個 PR 是一個完整的連貫實作鏈，圍繞 **ADR-191 / PRD-156 / SPEC-168**——「Policy-as-Code 與 Runtime Policy Planes」——展開。整體工作從架構文件制定，一路走到 DB schema、manifest 驗證、GitOps reconciler、API 防護層，Phase 1 全數完成。

---

## PR #571 — 架構治理文件（PRD-156 / ADR-191 / SPEC-168）

**性質**：純文件 PR，建立整個系列的理論基礎。

**問題**：原 ADR-185 draft（operational policy）提出在 `RateLimitPolicy`/`GuardrailPolicy` 行上直接存 `scope_id`，有三個致命缺陷：
1. resolver 沒接到 Gateway 真正執行路徑
2. policy 是可重用 template，不能放 single `scope_id`
3. 將五個不同 enforcement boundary 的 policy 混為一談

**解法**：建立三份新文件：
- **PRD-156**：定義 Policy-as-Code、PolicyAssignment 關係、5 個 policy plane 概念（後精簡為 3 個）
- **ADR-191**：正式決策，取代 ADR-185 operational draft；定義 3 個 in-scope plane + `PolicyAssignment` binding relation
- **SPEC-168**：行為契約，17 條 contract test + 9 條 negative case

**現在的架構**：
- Policy 內容（bundle）= 可重用 template
- 目標關係（assignment）= 獨立 binding row（one-to-many 扇出）
- 3 個 in-scope plane，各自有 enforcement owner：
  - `LLMOperationalPolicy` → IAM validate snapshot → Gateway
  - `RuntimeEgressPolicy` → agentd network boundary
  - `DeploymentRuntimePolicy` → Scheduler / Fleet / agentd
- 另外 2 個 plane（SidecarAccessPolicy、DataHandlingPolicy）明確 defer，需 future ADR 才能解封

**變更檔案（15 個）**
```
AGENTS.md
CLAUDE.md
docs/adr/ADR-185-operational-policy-scope-level-membership.md  ← 標 Superseded
docs/adr/ADR-191-policy-as-code-and-runtime-policy-planes.md   ← 新增
docs/adr/ADR_INDEX.md
docs/adr/core/Core-ADR-02-Policy-Authorization.md
docs/diagrams/policy-as-code-runtime-planes.html               ← 新增
docs/diagrams/policy-as-code-runtime-planes.mmd                ← 新增
docs/diagrams/policy-sync-lifecycle.html                       ← 新增（swimlane 圖）
docs/prd/PRD-132-policies-page-restructure.md
docs/prd/PRD-156-policy-as-code-and-runtime-policy-planes.md   ← 新增
docs/prd/PRD_INDEX.md
docs/specs/SPEC-152-operational-policy-scope-resolution-contract.md  ← 標 Superseded
docs/specs/SPEC-168-policy-as-code-runtime-policy-contract.md  ← 新增
docs/specs/SPEC_INDEX.md
```

---

## PR #597 — P1-a：DB schema + deferred-plane guard

**性質**：第一個實作 PR，在 DB 層落實 ADR-191 治理規則。

**問題**：文件只有文字，DB 沒有任何防線阻止 deferred plane 編碼（`sidecar_access`、`data_handling`）滲入 `PolicyBundle.policy_kind`。

**解法**：
- 新增 4 個 `TextChoices`：`PolicyKind`、`ManagedBy`、`PolicyBundleScopeType`、`PolicyBindingTargetScopeType`
- 在 `PolicyBundle` 和 `PolicyBinding` 上加 `managed_by` 欄位（預設 `console`）
- 6 個 `CheckConstraint`，物理阻擋 deferred 編碼在 DB 層寫入
- Migration `0116`，可雙向 rollback

**現在的效果**：對 `PolicyBundle.objects.create(policy_kind='sidecar_access')` 會直接拋 `IntegrityError`，ORM / raw SQL / admin 任何路徑皆無法繞過。

**變更檔案（3 個）**
```
tests/integration/test_adr191_policy_governance_fields.py  ← 新增（16 tests）
xparse_iam/xparse_iam/db/models/hierarchy.py
xparse_iam/xparse_iam/migrations/0116_policy_governance_fields.py  ← 新增
```

---

## PR #598 — P1-b：Manifest Pydantic Schema

**性質**：manifest YAML 的解析層，在任何 DB 寫入前先攔截非法內容。

**問題**：`sync_policies` 還沒有 manifest 層的 fail-fast，壞 YAML 可能跑到 plan 階段才半透明被拒，違反 ADR-093 #2。

**解法**：純 pydantic v2，零 Django 依賴：
- `apiVersion: xparse.policy/v1` 固定
- Closed discriminated union：4 個 manifest 類別
  - `LLMOperationalPolicyManifest`
  - `RuntimeEgressPolicyManifest`（spec 已 pinned）
  - `DeploymentRuntimePolicyManifest`
  - `PolicyAssignmentManifest`
- Deferred kind（`SidecarAccessPolicy`、`DataHandlingPolicy`）不在 union 中 → pydantic union exhaustion 直接拒
- 全部 model `extra="forbid"` + `frozen=True`
- `ManifestValidationError` 穩定 exception 介面

**變更檔案（3 個）**
```
tests/contract/test_adr191_manifest_schema.py  ← 新增（36 tests）
xparse_iam/xparse_iam/policies/__init__.py     ← 新增
xparse_iam/xparse_iam/policies/schema.py       ← 新增
```

---

## PR #603 — P1-c：sync_policies 管理命令（dry-run only）

**性質**：GitOps reconciler 的第一層：掃 manifest → 算 diff → 產 plan，但不寫入 DB。

**解法**：
- **`planner.py`**（純函式，零 Django 依賴）：接受 manifest set + DB snapshot，輸出有序 `list[PlanItem]`，6 種 state：`CREATE / UPDATE_ASSIGNMENT / DEPRECATE / NOOP / DRIFT / ERROR`
- **`sync_policies.py`**（Django CLI wrapper）：遞迴掃 `*.yaml` → `parse_manifest()` → ORM 讀 `managed_by='gitops'` rows → planner → 印 plan
- `content_hash` 演算法 pinned（SHA-256 of canonical JSON），跨 dry-run / apply 一致
- `--apply` / `--fail-on-drift` 在本 PR exit 2，留 P1-d 實作

**變更檔案（5 個）**
```
tests/contract/test_adr191_planner.py                      ← 新增（20 tests）
tests/integration/test_adr191_sync_policies_dry_run.py     ← 新增（6 tests）
xparse_iam/xparse_iam/management/commands/sync_policies.py ← 新增
xparse_iam/xparse_iam/policies/__init__.py
xparse_iam/xparse_iam/policies/planner.py                  ← 新增
```

---

## PR #609 — P1-d：sync_policies --apply ACID Transaction

**性質**：實際將 plan 寫入 DB，完整實作 swimlane（`policy-sync-lifecycle.html`）。

**解法**：
- **`applier.py`**（332 LOC）：`apply_plan()` 入口
  - `_preflight()`：在 BEGIN TX 前拒 ERROR + DRIFT（when flagged）
  - Two-pass in `transaction.atomic()`：pass 1 全部 bundle，pass 2 全部 binding（確保 FK lookup 可見 same-run create）
  - DRIFT bundle 不覆寫（content immutable per ADR-191 INV-191-1）
  - DEPRECATE = soft delete（`status='deprecated'`），保留 audit trail
  - `_reverify()`：re-read 每個 touched row，比對 `content_hash / precedence / status / FK`，不一致即 `ApplyError` → ROLLBACK
  - 結構化 audit logger，在 transaction 內 emit（rollback 同時 roll audit intent）
- `coerce_target_scope_id()`：UUIDv5 hash，讓 `plugin_slug` 等 slug-based target 在 planner / applier 兩層算出同 UUID（修正 P1-c 隱性 bug）

**變更檔案（7 個）**
```
tests/contract/test_adr191_planner.py
tests/integration/test_adr191_sync_policies_apply.py       ← 新增（10 tests）
tests/integration/test_adr191_sync_policies_dry_run.py
xparse_iam/xparse_iam/management/commands/sync_policies.py
xparse_iam/xparse_iam/policies/__init__.py
xparse_iam/xparse_iam/policies/applier.py                  ← 新增
xparse_iam/xparse_iam/policies/planner.py
```

---

## PR #613 — P1-e：GitOps Mutation Guard + Binder Validator Branch

**性質**：API 層防護，關閉 P1-a 標的兩個 known gap。

**解法**：
1. **`_assert_not_gitops(row, label)`** helper：PATCH endpoint 讀 row 後先過 guard，`managed_by='gitops'` 的 row 直接 HTTP 403，含 ADR-191 §3.3 / INV-191-6 原因
2. **`_allowed_target_scope_types(policy_kind)`** in `binder.py`：
   - `authorization / budget / guardrail` → PRD-060 set（`system/tenant/group/application/task`）
   - `llm_operational / runtime_egress / deployment_runtime` → ADR-191 §2.3 set（多 5 個新 target）
3. **`_VALID_*`** 常數改從 model TextChoices 讀取，消除 drift

**變更檔案（4 個）**
```
tests/integration/test_adr191_gitops_mutation_guard.py     ← 新增（14 tests）
xparse_iam/xparse_iam/api/ninja_api/_policies.py
xparse_iam/xparse_iam/api/ninja_api/_policy_config.py
xparse_iam/xparse_iam/authorization/binder.py
```

---

## PR #616 — P1-f：Required-Baseline Guard + Multi-Plane Fixture（P1 close-out）

**性質**：Phase 1 收尾，補最後一個 SPEC-168 contract item（C-168-5）。

**解法**：
- **`--require-baseline CODE`**（可重複）：deploy CI 列出必須存在的 baseline manifest code，在 parse 後、plan 前 check，缺任何一個 → `exit 2` + 完整缺失清單
- Multi-plane E2E fixture：單次 apply 跑三個 in-scope plane + 三個 assignment（各用不同 ADR-191 §2.3 target type）；第二次 apply 全 NOOP（C-168-3）

**Phase 1 SPEC-168 完整對照（C-168-1 ~ C-168-8, 15, 16, 17 + N-168-1/2/4/8/9）全部覆蓋。**

**變更檔案（2 個）**
```
tests/integration/test_adr191_sync_policies_required_and_multiplane.py  ← 新增（5 tests）
xparse_iam/xparse_iam/management/commands/sync_policies.py
```

---

## PR #620 — P1-g：PolicyBundle.code 身份驗證（Peer-Review #1）

**性質**：修補 peer review 發現的 ADR-093 #5 identity binding 缺陷。

**問題**：`PolicyBundle` 沒有 `code` 欄位，planner/applier 只用 `(policy_kind, version)` 配對 bundle，寫錯 `policy_code` 但 kind+version 對到其他 bundle 時 sync 仍會 commit 並綁錯目標。

**解法**：
- Migration `0118`：新增 `PolicyBundle.code` CharField + `(code, version)` 複合 index
- Backfill seed row `code='system-authorization'`
- `_assert_bundle_code_matches()`：binding 寫入前驗 `bundle.code == spec.policy_code`，不符即 `ApplyError` → ROLLBACK
- `_reverify()` 也比對 `bundle.code`

**變更檔案（6 個）**
```
tests/integration/test_adr191_bundle_code_identity.py       ← 新增（6 tests）
xparse_iam/xparse_iam/db/models/hierarchy.py
xparse_iam/xparse_iam/management/commands/sync_policies.py
xparse_iam/xparse_iam/migrations/0118_policy_bundle_code.py ← 新增
xparse_iam/xparse_iam/policies/applier.py
xparse_iam/xparse_iam/policies/planner.py
```

---

## PR #623 — P1-h：DEPRECATE Binding 精確度（Peer-Review #2）

**性質**：修補 DEPRECATE binding 的 over-disable 缺陷。

**問題**：`PlanItem` 沒帶 `target_scope_type / target_scope_id`，applier DEPRECATE binding 只能用 `(policy_kind, bundle__version, managed_by)` 批次 update，導致同一個 bundle 下還在 manifest 的其他 binding 也被誤停用。

**解法**：
- `PlanItem` 加兩個 Optional 欄位：`target_scope_type`、`target_scope_id`
- Planner 的 5 種 emission site（CREATE / UPDATE_ASSIGNMENT / NOOP / DEPRECATE / ERROR）全部填寫
- Applier DEPRECATE binding narrow 到精確 triple，並斷言 exactly 1 row（否則 `ApplyError` → ROLLBACK）
- Reverify 改用精確 `.get()`

**變更檔案（3 個）**
```
tests/integration/test_adr191_deprecate_binding_precision.py  ← 新增（4 tests）
xparse_iam/xparse_iam/policies/applier.py
xparse_iam/xparse_iam/policies/planner.py
```

---

## PR #628 — P1-i：Console Override + Slug Coercion + Docs Honesty（Peer-Review #3/4/5）

**性質**：修補 peer review 發現的最後三個問題。

**問題**：
- **#3**：P1-e 的 GitOps mutation guard + uniqueness check 合力造成 Console 無法建立 override（structural deadlock）
- **#4**：`target_scope_id` 是 UUIDField，但 `plugin_slug` 等 slug-based target 進 API 一律 400
- **#5**：`--edition` / `--site-overlay` flag 假裝支援，實際 P1-c 就沒實作

**解法**：
1. **Console override 開通**：POST / PATCH uniqueness check 只看 `managed_by='console'` row，gitops baseline + console override 可共存，runtime resolver 走 `precedence`
2. **Slug → UUIDv5 at API boundary**：API CREATE binding 對 `plugin_slug / application_type / edition / site` 跑 `coerce_target_scope_id()`，與 sync 共享同一個 deterministic UUID
3. **Docs honesty**：`--edition / --site-overlay` 改成 `ACCEPTED BUT NOT IMPLEMENTED in Phase 1`，引 PRD-156 FR-16

**ADR-191 §3.3 三層現在全部就位**：

| 層 | 行為 |
|---|---|
| GitOps baseline | Console / API mutation 全拒（P1-e） |
| Console override | 可建立、可更新，與 baseline 共存（P1-i） |
| Runtime resolution | precedence 決定 winner（P2/P3 範圍） |

**變更檔案（3 個）**
```
tests/integration/test_adr191_console_override_path.py     ← 新增（5 tests）
xparse_iam/xparse_iam/api/ninja_api/_policy_config.py
xparse_iam/xparse_iam/management/commands/sync_policies.py
```

---

## 完整變更檔案彙總

### 文件層（PR #571）

| 檔案 | 狀態 |
|---|---|
| `AGENTS.md` | 修改 |
| `CLAUDE.md` | 修改 |
| `docs/adr/ADR-185-*.md` | 修改（標 Superseded） |
| `docs/adr/ADR-191-*.md` | **新增** |
| `docs/adr/ADR_INDEX.md` | 修改 |
| `docs/adr/core/Core-ADR-02-*.md` | 修改 |
| `docs/diagrams/policy-as-code-runtime-planes.html` | **新增** |
| `docs/diagrams/policy-as-code-runtime-planes.mmd` | **新增** |
| `docs/diagrams/policy-sync-lifecycle.html` | **新增** |
| `docs/prd/PRD-132-*.md` | 修改 |
| `docs/prd/PRD-156-*.md` | **新增** |
| `docs/prd/PRD_INDEX.md` | 修改 |
| `docs/specs/SPEC-152-*.md` | 修改（標 Superseded） |
| `docs/specs/SPEC-168-*.md` | **新增** |
| `docs/specs/SPEC_INDEX.md` | 修改 |

### IAM DB 層（PR #597、#620）

| 檔案 | 狀態 |
|---|---|
| `xparse_iam/xparse_iam/db/models/hierarchy.py` | 修改（TextChoices + CheckConstraints + code field） |
| `xparse_iam/xparse_iam/migrations/0116_policy_governance_fields.py` | **新增** |
| `xparse_iam/xparse_iam/migrations/0118_policy_bundle_code.py` | **新增** |

### Policy-as-Code 模組（PR #598、#603、#609、#620、#623）

| 檔案 | 狀態 |
|---|---|
| `xparse_iam/xparse_iam/policies/__init__.py` | **新增**，多次修改 |
| `xparse_iam/xparse_iam/policies/schema.py` | **新增** |
| `xparse_iam/xparse_iam/policies/planner.py` | **新增**，多次修改 |
| `xparse_iam/xparse_iam/policies/applier.py` | **新增**，多次修改 |
| `xparse_iam/xparse_iam/management/commands/sync_policies.py` | **新增**，多次修改 |

### IAM API 層（PR #613、#628）

| 檔案 | 狀態 |
|---|---|
| `xparse_iam/xparse_iam/api/ninja_api/_policies.py` | 修改 |
| `xparse_iam/xparse_iam/api/ninja_api/_policy_config.py` | 修改 |
| `xparse_iam/xparse_iam/authorization/binder.py` | 修改 |

### 測試層

| 檔案 | PR | Tests |
|---|---|---|
| `tests/integration/test_adr191_policy_governance_fields.py` | #597 | 16 |
| `tests/contract/test_adr191_manifest_schema.py` | #598 | 36 |
| `tests/contract/test_adr191_planner.py` | #603 | 20 |
| `tests/integration/test_adr191_sync_policies_dry_run.py` | #603 | 6 |
| `tests/integration/test_adr191_sync_policies_apply.py` | #609 | 10 |
| `tests/integration/test_adr191_gitops_mutation_guard.py` | #613 | 14 |
| `tests/integration/test_adr191_sync_policies_required_and_multiplane.py` | #616 | 5 |
| `tests/integration/test_adr191_bundle_code_identity.py` | #620 | 6 |
| `tests/integration/test_adr191_deprecate_binding_precision.py` | #623 | 4 |
| `tests/integration/test_adr191_console_override_path.py` | #628 | 5 |

---

## 累計測試進度

| Phase | 測試數 | 累計 |
|---|---|---|
| P1-a（DB schema） | 16 | 16 |
| P1-b（Manifest pydantic） | 36 | 52 |
| P1-c（dry-run） | 26 | 78 |
| P1-d（--apply） | 10 | 88 |
| P1-e（GitOps guard + binder） | 14 | 102 |
| P1-f（required-baseline） | 5 | 107 |
| PRD-060 binder regression | 16 | 123 |
| P1-g（bundle code） | 6 | 129 |
| P1-h（DEPRECATE precision） | 4 | 133 |
| P1-i（console override） | 5 | **138** |

**ADR-191 Phase 1 正式完成。** 下一步為 P2（LLMOperationalPolicy 接 `validate_api_key()` live path）、P3（RuntimeEgressPolicy 在 agentd 執行）、P4（DeploymentRuntimePolicy）、P5（Console UX）。

---

## Frontend API 變更摘要（給前端 AI 審閱）

> **範圍**：以下僅列出影響 Console 前端的 API 行為變更。純後端異動（`sync_policies` 管理命令、planner/applier、manifest schema）不在此範圍。

### 1. 擴充的 Enum 值

#### `policy_kind` — 新增 3 個值（PR #597）

| 新值 | 說明 | Enforcement owner |
|---|---|---|
| `llm_operational` | LLM 請求配額 / guardrail | IAM validate snapshot → Gateway |
| `runtime_egress` | agentd 網路邊界 egress 控制 | agentd network |
| `deployment_runtime` | 容器部署運行時限制 | Scheduler / Fleet / agentd |

原有值仍有效：`authorization`、`budget`、`guardrail`。

**前端影響**：
- Policy Bundle / Policy Binding 的建立表單中，`policy_kind` 下拉選單需加入這 3 個新選項
- 列表頁的 `policy_kind` filter 下拉需同步更新
- 顯示時建議加上 "Runtime Plane" 標籤區分新舊 kind

---

#### `target_scope_type` — 對 runtime plane 新增 5 個值（PR #613、#628）

> **重要**：這 5 個新 target 只在 `policy_kind` 為 `llm_operational / runtime_egress / deployment_runtime` 時有效。`authorization / budget / guardrail` 仍只能使用舊有 target set。

| 新值 | 說明 | `target_scope_id` 格式 |
|---|---|---|
| `deployment` | 特定 Deployment | UUID 字串 |
| `application_type` | Application 類型 | **Slug 字串**（如 `"agent"`），server 轉 UUIDv5 |
| `plugin_slug` | Plugin slug | **Slug 字串**（如 `"jupyterlab"`），server 轉 UUIDv5 |
| `edition` | 授權版本 | **Slug 字串**（如 `"enterprise"`），server 轉 UUIDv5 |
| `site` | 站點 | **Slug 字串**，server 轉 UUIDv5 |

**Slug → UUID 說明**：對 `plugin_slug / application_type / edition / site` 這四種 target，`target_scope_id` 欄位直接傳人類可讀字串（如 `"jupyterlab"`），server 會用 UUIDv5 把它 hash 成固定 UUID 存 DB。前端**不需要**做轉換，直接傳字串即可。

**前端影響**：
- 建立 Binding 的表單中，當選擇 runtime plane `policy_kind` 時，需切換到更寬的 `target_scope_type` 選單
- `plugin_slug / application_type / edition / site` 的 `target_scope_id` 欄位應顯示為文字輸入（非 UUID picker）
- 建議依 `policy_kind` 動態切換 `target_scope_type` 選項集合

---

### 2. 端點行為變更

#### `PATCH /iam/policy-bundles/{uuid}/status`（PR #613）

**新增 HTTP 403 回應**：當 bundle 的 `managed_by = 'gitops'` 時，任何 status 變更都被拒絕。

```
HTTP 403
{
  "detail": "PolicyBundle ... is managed by GitOps (ADR-191 §3.3 / INV-191-6).
             To change this bundle, ship a new manifest via sync_policies
             or create a separate console-managed override."
}
```

**前端影響**：
- 需在 status 操作失敗後捕捉 403，顯示「此 Policy Bundle 由 GitOps 管理，無法從 Console 修改」的提示訊息
- 理想情況下：若能事先從 API response 取得 `managed_by` 欄位（見 §3），應 disable 操作按鈕並顯示唯讀標示

---

#### `PATCH /iam/policy-bindings/{uuid}/status`（PR #613）

**新增 HTTP 403 回應**：同上，`managed_by = 'gitops'` 的 binding 不可修改。

```
HTTP 403
{
  "detail": "PolicyBinding ... is managed by GitOps (ADR-191 §3.3 / INV-191-6). ..."
}
```

**前端影響**：同上，需捕捉 403 並顯示 GitOps 唯讀說明。

---

#### `POST /iam/policy-bindings`（PR #613、#628）

兩個行為改變：

**(a) 唯一性約束放寬（PR #628）**

舊行為：同 `(policy_kind, target_scope_type, target_scope_id)` triple 只能存在一個 active binding，有任何 active binding 就擋。

新行為：同 triple 允許「一個 gitops baseline + 一個 console override」共存。以下情況才會被擋（HTTP 400）：
- 嘗試建立第二個 **console-managed** active binding at the same triple

舊 400 錯誤訊息（已替換）：
```
"An active binding already exists for (kind, target_type, target_id). Disable the existing binding first."
```

新 400 錯誤訊息：
```
"An active console-managed binding already exists for (kind, target_type, target_id). Disable the existing binding first."
```

**前端影響**：
- 錯誤訊息更新：舊訊息中沒有「console-managed」字眼，需更新前端的錯誤提示文字
- Console 在建立 binding 時不用擔心與 gitops baseline 衝突

**(b) Slug-style `target_scope_id` 支援（PR #628）**

對 `plugin_slug / application_type / edition / site` 四種 target，`target_scope_id` 現在接受人類可讀字串（slug），不需傳 UUID。

```json
// 舊方式（仍可用於 tenant/group/application/deployment）
{ "target_scope_type": "tenant", "target_scope_id": "550e8400-e29b-41d4-a716-446655440000" }

// 新方式（適用於 slug-based target）
{ "target_scope_type": "plugin_slug", "target_scope_id": "jupyterlab" }
```

Server 回應中，`target_scope_id` 欄位會返回 server 計算的 UUIDv5（不是原始 slug），前端顯示時需注意這個欄位是 UUID 格式，不是原始 slug。

---

### 3. Response Schema 待補欄位（目前缺失，需後續 PR 補上）

> 以下欄位已在 DB 層落地但**尚未出現在 API 回應中**。前端 AI 需知悉這個 gap，並在對應欄位加入 response schema 後再處理 UI 顯示。

#### `managed_by` 欄位（PR #597 加入 DB，尚未在 response 中）

欄位位置：`PolicyBundleResponse`、`PolicyBundleListItemResponse`、`PolicyBindingResponse`、`PolicyBindingListItemResponse`

值：`"gitops"` | `"console"`

**現在的問題**：前端在呼叫 PATCH 前無法預先知道一個 bundle/binding 是否為 gitops-managed，只有在 PATCH 失敗（403）後才知道。這導致 UX 不佳——按鈕無法提前 disable。

**期望的 UI 行為（待 `managed_by` 加入 response 後）**：
- 列表與詳情頁顯示 `managed_by='gitops'` 的 row 標示「GitOps managed」badge
- 對 gitops row 的 status PATCH 按鈕應 disable，tooltip 說明原因
- `managed_by='console'` 的 row 行為不變

#### `code` 欄位（PR #620 加入 DB，尚未在 response 中）

欄位位置：`PolicyBundleResponse`、`PolicyBundleListItemResponse`

值：字串，如 `"egress-default"`、`"system-authorization"`（空字串代表 pre-migration legacy row）

此欄位是 GitOps manifest 的 stable cross-reference identifier，未來 Console 的 override UI 可能需要顯示（對應哪個 baseline bundle）。

---

### 4. 完整端點清單（不變的部分）

以下端點在這 10 個 PR 中**行為未改變**，request/response schema 不動：

| 端點 | 方法 | 說明 |
|---|---|---|
| `/iam/policy-bundles` | POST | 建立 policy bundle（schema 未變，但 `policy_kind` enum 擴充） |
| `/iam/policy-bundles` | GET | 列出 bundles（filter `policy_kind` 可帶新值） |
| `/iam/policy-bundles/{uuid}` | GET | 取得單一 bundle |
| `/iam/policy-bindings` | GET | 列出 bindings |
| `/iam/policy-bindings/{uuid}` | GET | 取得單一 binding |

---

### 5. 前端工作清單（依優先順序）

| 優先 | 工作項目 | 觸發 PR |
|---|---|---|
| P0 | PATCH bundle/binding status 端點加入 403 錯誤處理，顯示 GitOps 說明訊息 | #613 |
| P0 | `POST /iam/policy-bindings` 的 400 錯誤訊息由「An active binding」更新為「An active console-managed binding」 | #628 |
| P1 | `policy_kind` 下拉新增 `llm_operational / runtime_egress / deployment_runtime` | #597 |
| P1 | `target_scope_type` 選單依 `policy_kind` 動態切換（runtime planes 顯示 5 個新 target） | #613 |
| P1 | Slug-based target 的 `target_scope_id` 欄位改為文字輸入（非 UUID picker） | #628 |
| P2 | 待 `managed_by` 加入 API response 後：顯示 GitOps badge、disable 對應 PATCH 按鈕 | 待補 PR |
| P2 | 待 `code` 加入 API response 後：列表/詳情頁顯示 bundle code | 待補 PR |
