# 一個 Group 多個同名 Model — Per-Proxy Model Namespace

**日期：** 2026-08-01（主線已全數 merge 進 `main`）· **2026-08-02 追加一輪收尾，見 §10（PR 已開，未 merge）**
**規格文件：** PRD-273 · ADR-358 · SPEC-171 Rev.7（MEMBERSHIP-05）· DISCUSSION-2026-08-01
**PR：** [xparse#3052](https://github.com/futurenestit/xparse/pull/3052) · [Xparse-Audit#86](https://github.com/futurenestit/Xparse-Audit/pull/86) · [xparse#3054](https://github.com/futurenestit/xparse/pull/3054) · **[xparse#3058](https://github.com/futurenestit/xparse/pull/3058)（收尾）**
**Migration：** `xparse_iam` `0222_per_proxy_model_name_namespace`

---

## 0. 白話：解決了什麼

一個部門（group）底下有兩個團隊，各有自己的 LLM Proxy。

**改之前**：團隊一先建了 `gpt-4o`，團隊二就再也建不了自己的 `gpt-4o` —— 系統說這個名字部門裡已經有人用了。團隊二只有兩條路：跟團隊一**共用同一條線**（同一把 OpenAI 金鑰、同一份帳單、同一個價格），或者把名字改成 `gpt-4o-team2`（但那樣客戶端程式碼要改，而且脫離 provider 的標準命名）。

**改之後**：兩個團隊各有自己的 `gpt-4o`，各自綁自己的 provider 憑證、各自排自己的價格，客戶端仍然送標準的 `"model": "gpt-4o"`。

```
Group: 研發部
├─ Proxy A (團隊一) └─ Model#1  gpt-4o  cred=OpenAI-KeyA  $2.5/1M
└─ Proxy B (團隊二) └─ Model#2  gpt-4o  cred=OpenAI-KeyB  $3.0/1M
```

唯一的限制：**同一個 Proxy 內名字仍然唯一**（不然客戶端喊「gpt-4o」時系統不知道該接哪一個）。

---

## 1. 技術上做了什麼

把 Model 公開名的唯一性**作用域**，從 `group` 收窄到 `LLM Proxy pool`：

| | 舊 | 新 |
|---|---|---|
| Constraint | `uq_model_per_group_provider_name` on `Model(group, provider, model_name)` | `uq_active_proxy_model_name` on `ProxyModelSource(proxy, model_name_mirror)` where `status='active'` |
| 位置 | `iam_model` | `iam_proxy_model_source` |
| 含 provider？ | 是 | **否** |
| 對應 invariant | ADR-087 INV-087-3 | ADR-358 INV-358-1 |

### 為什麼 pool 是對的作用域

一個請求的候選集**本來就只有單一 proxy 的 pool**：

```
xparse_iam/xparse_iam/core/auth_engine.py:684  _resolve_active_proxy_pool_models
  → :641  _proxy_model_source_entries
  → :653  ProxyModelSource.objects.filter(proxy=proxy, status="active")
```

定址只需要「名字在候選集內唯一」。group 層唯一性**嚴格強於**這個需求 —— 它額外禁止了兩顆永遠不可能同時出現在一個請求候選集裡的 model，而那個超出的部分正好就是擋住部門級成本隔離的東西。

順帶修掉一個既有潛伏 bug：group-scoped 的 `gpt-4o` 與 tenant-scoped 的 `gpt-4o`（ADR-273，`group=NULL` 所以舊 constraint 管不到）**今天就能**同時被掛進一個 pool，沒有任何檢查會擋。只有 pool 層守衛擋得到。

### 為什麼 key 裡不含 provider

客戶端只送 `model_name`，而 `/v1/models` 依名字去重（`bustream/gateway/routes/models.py:89`）。一個 pool 裡同時放 `openai/gpt-4o` 和 `azure_openai/gpt-4o`，**第二顆對任何 client 都不可定址**。保留 provider 只會讓歧義搬家而不是消失。

**接受的代價**：放棄「同一模型跨 provider 的 `cost_first` 價格套利 pool」。2026-08-01 明確裁決，與 PRD-164 §1.3 既有立場一致（要多後端請用外部 LB 收成單一 Model）。

### 為什麼用鏡射欄位

`model_name` 在 `iam_model`，pool 邊在 `iam_proxy_model_source`。

- `GeneratedField` 不行 —— generated column 只能引用**同一列**的欄位
- Postgres `EXCLUDE` 不行 —— SQLite 是預設 engine（`settings.py:145`），不可攜
- 所以：`ProxyModelSource.model_name_mirror`，在 `save()` 裡從 FK 推導、本地建 partial unique index

它是**鏡射**不是快照：`save()` 無條件重新推導，而這之所以是 no-op，是因為 INV-087-5 保證 `Model.model_name` 建立後不可變。同一個模式的先例：`ModelPriceVersion.tenant_uuid`。

### 推翻 ADR-204 Alternative D

ADR-204 曾否決放寬這條 constraint，理由是「requires routing-among-same-name (a selection policy)」。**那個理由的前提是同名在同一候選集內。** 本案的同名位於**不同 pool**，永不同時進入一個候選集 —— 所以不需要 same-name 選擇策略。這也正是為什麼要禁止 pool 內同名：把 D 案真正的困難點用「禁止」迴避掉，而非解決。

`INV-087-5`（名稱不可變）不但沒被違反，還是本案的**承重牆**。

### 與 ADR-356 的收斂（不是衝突）

同一天有另一份在飛的 ADR-356 也在改同一條 constraint，方向相反（收成 `(group, model_name)`）。

分析結論：改 identity key 有**兩個正交的軸** —— *哪些欄位*在 key 裡、*作用域*多大。ADR-356 的所有論證都在欄位軸；沒有一句論證 `group` 這個作用域（它是沿用現狀的結果）。決定性證據：它自己的 Alternative B 就寫成 `UNIQUE(pool, model_name, surface)`（**已經是 pool-scoped**），否決理由完全針對 `surface` 這個欄位。

`(pool, model_name)` 一次做對兩個軸，是滿足兩份設計所有已陳述需求的**最弱** key。已透過 #3054 併回 ADR-356。

---

## 2. 五個交付面

### 2.1 IAM — 換 constraint、補守衛、修 500 風險

| 檔案 | 做了什麼 |
|---|---|
| `xparse_iam/xparse_iam/migrations/0222_per_proxy_model_name_namespace.py` | **新增**。移除舊 constraint → 加鏡射欄位 → 從 FK 回填 → **無副作用碰撞稽核（先 raise）** → 加新 constraint |
| `xparse_iam/xparse_iam/db/models/provider.py` | `Model` 移除 group constraint；`ProxyModelSource` 加 `model_name_mirror` + `save()` 推導 + `uq_active_proxy_model_name`；`ApplicationModel.save()` 加同名前置檢查 |
| `xparse_iam/xparse_iam/application/use_cases/proxy/add_model_source.py` | MEMBERSHIP-05 守衛（在既有無副作用階段，訊息指名既有那顆的 uuid + display_name） |
| `xparse_iam/xparse_iam/infrastructure/repositories/django/proxy_repository.py` | 新增 `pool_member_with_model_name` / `model_name_of`；`list_sources` 加 `select_related("model__credential")` 與全序 |
| `xparse_iam/xparse_iam/application/use_cases/model/create_model.py` | 移除 group 名稱前置檢查，改為 `display_name` 衝突檢查 |
| `xparse_iam/xparse_iam/infrastructure/repositories/django/model_repository.py` | `exists_by_group_provider_name` → `exists_by_group_display_name` |
| `xparse_iam/xparse_iam/api/ninja_api/_applications.py` | **刪除** `_preflight_llm_proxy_model_conflict`（409）與其 config-mirror 區塊；auto-provision 改鍵 `provisioned_by=app` |
| `xparse_iam/xparse_iam/api/ninja_api/_deployments.py` | `get_or_create` 改鍵 `deployment_uuid`（順帶修 endpoint 互相覆寫的既有 bug） |
| `xparse_iam/xparse_iam/application/use_cases/catalog/self_service.py` | 同上，改鍵 `deployment_uuid` |
| `xparse_iam/xparse_iam/management/commands/seed_frontend_test_data.py` | `get_or_create` key 補 `display_name` |
| `xparse_iam/xparse_iam/core/auth_engine.py` | 候選集改全序 `(sort_order, model_uuid)`；同名偵測 warning + metric |
| `xparse_iam/xparse_iam/observability/metrics.py` | 新 counter `candidate_set_name_collision` |
| `xparse_iam/xparse_iam/api/ninja_api/_proxy.py` | `_source_to_response` 加 `credential_uuid` / `credential_name` |
| `xparse_iam/xparse_iam/api/ninja_api/_tenant_models.py` | **新端點** `GET /iam/tenants/{uuid}/models/catalog` |
| `xparse_iam/xparse_iam/api/schemas/_proxy.py` | `ModelSourceSummary` 加 credential 欄位 |
| `xparse_iam/xparse_iam/api/schemas/_application.py` | 新增 `TenantModelCatalogItem` / `TenantModelCatalogResponse` |
| `xparse_iam/xparse_iam/api/schemas/__init__.py` | 匯出上述兩個 schema |

**四處 `get_or_create` 是必修項，不是順手改。** 拿掉 constraint 之後 `(group, provider, model_name)` 不再唯一，而 `get_or_create` 內部呼叫 `.get()` —— 一旦出現第二筆同名就會拋 `MultipleObjectsReturned`，也就是 **500**。

### 2.2 Gateway — 最後一哩改用 model_uuid

| 檔案 | 做了什麼 |
|---|---|
| `bustream/backend/plan.py` | `BackendConfig` 新增 `model_uuid` |
| `bustream/gateway/worker_setup.py` | `backend_metadata_by_model` → `backend_metadata_by_uuid`；`_backend_config_from_assignment` 改用 `assignment.model_id`；`resolve_provider_api_key` 透傳 `model_uuid`；YAML rung 的 warning 明說是 name-keyed |
| `bustream/production/key_resolver.py` | `_resolve_native` 以 uuid 比對；**uuid 給定卻查無時硬失敗，不退回名稱**；加 module logger |
| `bustream/gateway/routes/responses.py` | 傳 `model_meta.model_uuid` |

**誠實的理由**：不是因為目標情境下它壞了 —— 候選集只含單一 pool，Proxy A 的 context 裡只有 KeyA，名稱解析在兩邊都回傳正確憑證。（我在過程中曾寫錯這一點，後來在 commit message 與 PR 裡更正。）

真正的理由是**不變量的形狀**：名稱解析要求「每一條 membership 寫入路徑、永遠都要維持名稱唯一」—— 一個分散式不變量，任何新增的候選集組裝點都得記得守。改用主鍵之後變成區域性不變量，函式自證正確。它也讓 §1 那個既有潛伏碰撞從「靜默用錯憑證」降級為「確定性解析」。

**不改的部分**（在 per-pool 名稱唯一下本來就正確）：`chat_helpers.py` 的 pin 收斂、`responses.py` 的 name match、`/v1/models` 去重、substitution/default 偵測、worker factory 的 dispatch key。

### 2.3 Audit — 新增 model_uuid 彙總維度（獨立 submodule）

| 檔案 | 做了什麼 |
|---|---|
| `3rd/xparse_audit/src/audit/storage/postgres_event_store.py` | `_DIM_SQL["model_uuid"]`，讀 `payload.model_uuid`，`NULLIF(BTRIM(...))` |
| `3rd/xparse_audit/src/audit/access/query.py` | `GROUP_BY_DIMENSIONS` + `_event_dimension` 的 Python 鏡像（C-185-9 parity） |
| `3rd/xparse_audit/src/audit/api/usage_cost_aggregation.py` | `usage_dimension` 新分支；**改寫過度引用 INV-330-2 的 docstring** |
| `3rd/xparse_audit/src/audit/usage_cost/rollup_projector.py` | `DIM_TYPES` / `DIM_TO_GROUP_BY`；哨兵處理一般化為 `DIM_ABSENT_SENTINEL` map |
| `3rd/xparse_audit/src/audit/usage_cost/rollup_store.py` | 新常數 `UNKEYED_MODEL_DIM_VALUE = "__no_model_uuid__"` |
| `3rd/xparse_audit/src/audit/storage/rollup_store.py` | **legacy rollup 也註冊 `model_uuid`**（見下）+ DDL 註解 |
| `3rd/xparse_audit/src/audit/api/routers/dashboard.py` | `breakdowns.by_model_uuid` + meta（**optional 欄位**） |
| `3rd/xparse_audit/src/audit/api/routers/stats.py` | 新端點 `GET /audit/stats/top-model-uuids` |
| `3rd/xparse_audit/src/audit/api/models.py` | `TopModelUuidItem` / `TopModelUuidsResponse`（**獨立型別**） |
| `3rd/xparse_audit/src/audit/storage/rollup_rebuild.py` | runbook 註記：ADR-358 部署後必跑 |

**兩個看起來可選、實際不可省的決定：**

1. **兩個 rollup 都要對稱註冊。** `/stats/top-*` 的排名與 token 來自 legacy rollup，只有 cost 疊加來自 latest-price rollup。若 `model_uuid` 只存在其中一個，「拆開」視圖會走精確 SQL pushdown 而「合併」視圖走 legacy rollup 的 top-N + `__other__` 折疊 —— 切換 toggle 數字就會變。那正是這個 toggle 存在要避免的失敗。

2. **獨立的 `TopModelUuidItem`，不重用 `TopModelItem`。** 後者的 `model` 欄位被文件與 Console 當**名字**消費（去 join catalog 的 `definition_name`）。重載它去有時裝 uuid，等於重演這次要修的 name-vs-identity 錯配。

**哨兵**：沒有 `model_uuid` 的用量（embeddings 解析的是 `EmbeddingProfileConfig` 而非 Model row，結構上沒有 uuid、也因 `ModelPriceVersion` FK 到 Model 而不可計價；加上 ADR-330 之前的歷史事件）落入 `__no_model_uuid__`，**不丟棄**。丟棄會讓真實花費從維度裡消失（PRD-256 NEG-3 的教訓）並違反 AC-API-2 的「breakdown 總和等於 totals」。刻意**不用** `__unattributed__`（那是「沒有註冊的終端使用者」，不同的事實），也**不用** `__other__`（那是「排名在 top-N 之外」）。

### 2.4 Console — 同名可辨識 + 成本拆開/合併

前綴皆為 `frontend/console-app-refactor/src/`

| 檔案 | 做了什麼 |
|---|---|
| `components/features/llm-proxy/models/create-model-dialog.tsx` | New tab 改走 `provisioned_by` **原子 create+attach**；停止 `display_name` 靜默鏡射；Existing picker 加辨識副標；兩個行內預檢 |
| `components/features/llm-proxy/models/models-tab.tsx` | credential badge + wire-name 副標；未定價橫幅改用可辨識標籤；排序加 `model_uuid` tiebreak |
| `components/features/llm-proxy/models/edit-model-dialog.tsx` | 唯讀身分行補 endpoint |
| `app/(main)/(overview)/(dashboard)/_components/plugins/progress-tabs-plugin.tsx` | 新 tab source `top-model-uuid` + 標籤解析（provider → group → uuid 尾碼）+ `by_model_uuid` 缺席時顯示「不可用」 |
| `app/(main)/(overview)/(dashboard)/_tabs/cost-usage/initial-layout.ts` | 「By Model」分頁**預設改為拆開視圖** |
| `components/features/group/group-detail-view.tsx` | proxy 摘要標籤改為 `+N` |
| `app/(main)/(infrastructure)/models/_components/deployments-view.tsx` | 依名字 join 的註記（best-effort，附正解） |
| `services/iam.ts` | `useTenantModelCatalog` hook |
| `types/iam.ts` | `ModelSourceSummary` 加 credential 欄位；新增 `TenantModelCatalogItem/Response` |
| `types/audit.ts` | `by_model_uuid?`（**optional**）+ `UNKEYED_MODEL_DIM_VALUE` |

**根因先修**：`display_name` 原本在 create 時被靜默鏡射成 `model_name`。那在它只是裝飾時無害，但它現在是**唯一**能在清單、選擇器、成本報表裡區分兩顆同名 model 的欄位。不先修這個，下面每一項都會渲染出兩行一模一樣的字。

**原子化**：New tab 原本 create 完再 bind，兩次 API 呼叫。bind 失敗會留下孤兒 Model —— 而 group 層 constraint 拿掉後，沒有東西阻止孤兒累積。改傳 `provisioned_by` 讓 IAM 在同一個 transaction 內跑 `add_model_source`，守衛在 commit 前就擋下。

### 2.5 文件（§17.1 設計閉環 + §17.4 Core 對齊）

| 檔案 | 做了什麼 |
|---|---|
| `docs/prd/PRD-273-per-proxy-model-namespace.md` | **新增**。§0 白話層、§4 完整驗收（A1–A10 / U1–U5 / I1–I3 / N-1–N-5）、§17.1b 外部證據 |
| `docs/adr/ADR-358-per-proxy-model-identity-namespace.md` | **新增**。supersede INV-087-3、推翻 ADR-204 Alt D、§4.1 與 ADR-356 的收斂、ADR-093 五列表含 §5.4 例外 |
| `docs/discussions/DISCUSSION-2026-08-01-model-identity-key-scope-reconciliation.md` | **新增**。與 ADR-356 的收斂分析 + 兩項裁決 |
| `docs/spec/SPEC-171-llm-proxy-routing-container-behavioral-contracts.md` | Rev.7 — MEMBERSHIP-05；MEMBERSHIP-02 澄清（共用仍合法） |
| `docs/adr/core/Core-ADR-01-Gateway-Streaming.md` | 加 ADR-358（最後一哩改鍵；SSE 不變量不受影響） |
| `docs/adr/core/Core-ADR-04-Audit-Observability.md` | ADR-330 extended by ADR-358（新維度） |
| `docs/adr/core/Core-ADR-06-Provider-Integration.md` | 加 ADR-358；**修正對 ADR-204「preserves INV-087-3/5」的錯誤敘述** |
| `docs/adr/core/Core-ADR-11-Model-Lifecycle.md` | **主領域**；ADR-087 那列標註 INV-087-3 被取代 |
| `docs/prd/core/Core-PRD-11-Model-Lifecycle.md` | 加 PRD-273（primary） |
| `docs/prd/core/Core-PRD-05-Console-Frontend.md` | 加 PRD-273（Console 介入面） |
| `docs/adr/ADR_INDEX.md` · `docs/prd/PRD_INDEX.md` | 用 `scripts/sync_adr_index.py` 重建（不手改） |
| `docs/adr/ADR-087-group-owned-model-entity.md` | INV-087-3 標 superseded；註明 INV-087-5 成為承重前提 |
| `docs/adr/ADR-198-llm-proxy-routing-container.md` | Extended by ADR-358（MEMBERSHIP-05；MEMBERSHIP-02 不變） |
| `docs/adr/ADR-204-public-served-model-name-decoupling.md` | Amended by ADR-358（Alternative D 的否決被推翻） |
| `docs/adr/ADR-330-query-time-latest-effective-price-cost-display.md` | Extended by ADR-358（新增 INV-330-11） |
| `xparse-wiki/wiki/sources/adr-358-per-proxy-model-identity-namespace.md` | **新增** wiki 頁 |
| `xparse-wiki/wiki/sources/adr-204-public-served-model-name-decoupling.md` | 修掉已過時的 INV-087-3 宣稱 |

### 2.6 測試

| 檔案 | 做了什麼 |
|---|---|
| `tests/integration/test_adr358_model_id_propagation_probe.py` | **新增**。§8.1 真元件 probe + dogfood 測試 |
| `tests/integration/test_key_resolver_native_credential.py` | 新增 `TestResolveNativeKeysOnModelUuid`（4 個測試，雙向對稱） |
| `xparse_iam/tests/unit/test_spec171_models.py` | 新增 4 個 DB 層測試（INV-358-1/2、MEMBERSHIP-05、跨 provider） |
| `xparse_iam/tests/unit/test_spec171_usecases.py` | `FakeSourceRepo` 補新方法（真實模擬，非 stub） |
| `xparse_iam/tests/unit/test_spec171_resolver.py` | 翻轉 auto-provision 共享語意的斷言 |
| `xparse_iam/tests/unit/test_issue772_llm_proxy_endpoint_conflict.py` | 針對新機制重新 pin #772 的 hazard |
| `tests/unit/test_use_case_create_model.py` | 拆成「同名允許」+「display_name 衝突拒絕」 |
| `tests/unit/test_worker_setup_db_resolution.py` | 改成 uuid-keyed lookup |
| `tests/unit/test_issue1488_max_tokens_clamp.py` · `tests/unit/test_issue2946_bedrock_sampling_lock.py` · `tests/unit/test_self_service_model_routing.py` | fixture 補 `model_id` |
| `3rd/xparse_audit/tests/integration/dashboard/test_dashboard_usage_cost.py` | 新增 3 個（拆/合總額相等、哨兵、AC-API-2） |
| `3rd/xparse_audit/tests/integration/storage/test_postgres_event_store_aggregate.py` | 新增 C-185-9 parity（對真 PG） |

---

## 3. 順帶處理的既有債（非本功能，但擋住了本功能）

### 3.1 ADR / PRD 撞號（`14bcfb049`）

CI 的 ADR Index Completeness Gate 在 **`main` 自己身上就是紅的**。證據：對 `origin/main` 的乾淨 checkout 跑 gate 得到同樣 2 個 `DUP-NUMBER`。任何碰 `docs/adr/` 的 PR 都會繼承。

依 repo 自己記錄的慣例（`docs/guides/two-axis-policy-governance.md` §編號狀態：「碰撞時改動較晚合併、reference churn 較小的一側」）+ 「號碼被誰從程式碼引用」的證據：

| 撞號 | 保留 | 移動 | 依據 |
|---|---|---|---|
| ADR-331 | `tool-type-authorization` | `guardrail-v2` → **ADR-359** | tool-type 被 `bustream/gateway/responses_tools_filter.py` 與其測試引用；移 guardrail 只碰 4 個 md |
| ADR-354 | `resource-inventory`（Accepted, #3011） | `platform-periodic-task` → **ADR-360** | resource-inventory 被 `console_capabilities.py`、`_inventory.py`、contract test 引用 |
| PRD-269 | `tenant-resource-inventory` | `platform-periodic-task` → **PRD-274** | gate 看不到 PRD 撞號，但只修 ADR 一半會讓 ADR-360 指向它不擁有的 PRD 號 |

三份移動的文件都加了 `Previously known as` 註記（#445 的 acceptance 要求），所有引用**逐處按語意改**（全域替換會把保留號的那兩份也改壞）。

> **ADR-331 已被搶三次** —— 兩軸限流那組早先也讓位到 ADR-332。號碼是對著過期的 `origin/main` 配的。

### 3.2 本機 dev DB 的 500（僅資料，無程式碼變更）

`/v1/chat/completions` 回 `{"detail":"IAM service error"}`，IAM log 顯示：

```
GuardrailPolicyResolutionError: PolicyVersion (code=builtin-judge-probe-a1 v1)
  content failed GuardrailPolicySpec: 4 validation errors  (extra_forbidden)
    classifier.on_topic.template / confidence_threshold
    classifier.content_filter.engines / moderation_credential_model
```

那 4 個欄位屬於**被 revert 的 OpenAI moderation guardrail**（`4dae045a6`）。revert 把 schema 從程式碼移掉，但 dev DB 裡那版程式碼寫入的 policy row 留著。現有 codebase 裡沒有任何地方 seed 這些 probe policy —— seeding 的程式碼被 revert 掉了，資料沒有。

處置：4 筆全是 probe 產物（`openai-mod-probe-a1` v1–v3、`builtin-judge-probe-a1` v1）、0 active binding。只剝掉那 4 個欄位、**沒刪 row**（有 FK 指著），備份在 scratchpad 的 `guardrail_probe_backup.json`。

---

## 4. 工作流程（實際怎麼做的，含踩到的坑）

| 階段 | 做了什麼 | 值得記的坑 |
|---|---|---|
| **P0 調查** | 三個並行 Explore agent 掃 model 解析路徑 / audit+cost / Console+寫入路徑 | 先跑 `git rev-list --count HEAD..origin/main` 確認樹不 stale |
| **決策** | 四次 `AskUserQuestion` 確認需求本質、group 層防呆、報表呈現、範圍 | 「每個 proxy 都有 gpt-4o」有兩種解讀（共享同一顆 vs 各自獨立），差別是「今天就能做」還是「要改 constraint」 |
| **衝突偵測** | 發現 `origin/worktree-adr-353` 的 ADR-356 在改同一條 constraint、方向相反 | **這是 §17.4 存在的理由**。若沒查，會有兩個矛盾的 migration 在不同分支 |
| **收斂** | 寫 DISCUSSION 文件論證兩者正交（欄位軸 vs 作用域軸） | 決定性證據在對方 ADR 自己的 Alternatives 表裡 |
| **P1 計畫** | 兩個 Plan agent 壓力測試設計 | agent 抓到我一個**錯誤主張**（wrong-credential）和一個**會 ship 500 的漏洞**（4 處 `get_or_create`） |
| **P2 實作** | 先寫失敗測試 → 確認紅 → 實作 → 綠 | IAM 測試要在 ephemeral 容器跑，且要補掛 `xparse_guardrail` / `xparse_routing` / `3rd/xparse_audit/src` 三個 mount |
| **§8.1 驗證** | 對真元件 probe，含 dogfood 測試 | 沒有這個 probe，uuid 查詢可能永遠 None（靜默走 YAML），而所有單元測試照樣全綠 —— 事故 #1025 同型 |
| **回歸判定** | 用 baseline worktree diff 分辨「我弄壞的」與「本機既有的」 | repo 有 ~90 個既有本機失敗。**新 worktree 沒有 submodule**，會讓收集數不同而使比對靜默失效 |
| **P5 交付** | 5 個 commit（docs / IAM / gateway / gitlink / console） | `git add -A` 掃進了 `dump.rdb` 與不相關 plan 文件，事後移除 |
| **CI 修復** | 3 個 finding：1 個我的（手改 auto block）、2 個 main 既有的 | Static Gates **不跑 docs-only PR** —— 這就是撞號能進 main 的原因 |
| **真環境驗證** | 對 live dev stack 實測 | **找到三個測試 fixture 抓不到的問題**（見下） |

### 用真 DB 跑之後才發現的三件事（`80b77fa2a`）

1. **constraint 可能對「名字不同」的 model 報名字衝突。** mirror 由 `save()` 填，`bulk_create` 繞過 `save()` —— 同 pool 兩筆 bulk-create 的**不同** model 都帶 `""` 而互撞。加了 `& ~Q(model_name_mirror="")`：沒鏡射的列改為不受保護，而非被誤拒。誤導性錯誤比它擋住的漏洞更糟。
2. **`display_name` 被我寫成不變量，但既有資料違反它。** dev DB 裡有 **4 筆** `gpt-5.4-mini`，其中兩筆同在 `rd_team`、只差 provider —— 舊 constraint 因 provider 不同而合法。已改成明說是 create-time 檢查、明說刻意不升格為 DB constraint。
3. **Console 的標籤退路在真實案例上失效。** 原本 `display_name → group_code → uuid`。上面那兩顆 display_name 一樣、group 也一樣，直接掉到 uuid 尾碼，而 `provider` 明明能完美區分。已把 provider 排到最前面。

---

## 5. 驗證證據

| 範圍 | 結果 |
|---|---|
| SPEC-171 model 層 | 4 個新測試**先紅後綠**；12/12（MEMBERSHIP-02 共用守衛未破） |
| IAM unit 全套 | **1669 passed**（4 個既有失敗：缺 `xparse_dmz_promoter`） |
| 憑證選擇（真 `KeyResolver` + 真 `CryptoManager`） | 22/22，**雙向對稱**（避免「永遠取最後一個」也能過） |
| §8.1 真元件 probe | 4/4，**dogfood 測試證明它真的會紅** |
| audit dashboard 整合 | 21/21（合併↔拆開總額相等、哨兵不被丟棄、AC-API-2） |
| audit C-185-9 parity | **對真 Postgres 12/12**（丟棄式 DB，非 live） |
| audit integration 全套（真 PG） | 淨新增失敗 **0**（53 個既有，兩邊集合相同） |
| parent repo 全掃 vs 乾淨 baseline | 淨新增失敗 **0**（90 個既有，兩邊集合相同） |
| Console | `tsc --noEmit` 乾淨；eslint 全綠 |
| **CI（#3052）** | **8/8 SUCCESS** |

### 對 live dev stack 的實測

| 項目 | 結果 |
|---|---|
| migration `0222` | 已套用 |
| 既有資料 | **59 顆 model / 44 筆 membership 全在**，mirror 回填 0 個空值 |
| Constraint 換手 | group 移除 ✓ / tenant 保留 ✓ / pool 新建 ✓ / uuid membership 保留 ✓ |
| 舊 API `GET /iam/applications` | 200 |
| 舊 API `GET .../model-sources` | 200，正確回傳新的 `credential_name` |
| 同 group 建第二顆 `gpt-4o` | **201**（改之前是 400 duplicate） |
| 加到已有 `gpt-4o` 的同一 proxy | **409**，訊息指名既有那顆的 uuid + display_name |

**舊 model 不需要任何重建。** migration 只做「移除約束 → 加欄位 → 從 FK 回填 → 稽核 → 加新約束」，不改任何一筆 `Model`、不重建任何 membership。

---

## 6. 行為變更（不是壞掉，是刻意的）

呼叫既有 API 的人要知道：

1. **建 model 時 `display_name` 在同 group 內衝突 → 400。** 它從裝飾升格成辨識鍵了。**2026-08-02 起改名（`PATCH /iam/models/{uuid}`）也一樣會 400** —— 只守建立等於守衛差一次改名就被繞過。
2. **`POST /iam/groups/{g}/applications` 帶 `type_code=llm_proxy_cloud|existing`**：第二個 proxy 現在拿**自己的** Model，不再重用第一個的。（翻掉 Issue #306 的共享語意；#306 真正的回歸守衛「第二個 proxy 不可拿到 0 個 binding」保留。）
   ⚠️ **但這條與第 1 條互相矛盾**：auto-provision 直接寫 ORM、不走 `create_model`，`display_name` 一律等於 `model_name`。所以同 group 兩個 `llm_proxy_cloud` 都指向 `gpt-4o` 時，平台會**自己造出**一對第 1 條要拒絕的 model。詳見 §7.2 的 🔴 列。
3. **`409 MODEL_ENDPOINT_CONFLICT` 不再出現。** `_preflight_llm_proxy_model_conflict` 已刪。以那個 error code 分支的呼叫端會看到 201。
4. **反向 migration 一旦功能被使用就會失敗**（重建 group constraint 撞到真的重複列）。刻意的 fail-loud。

---

## 7. 尚未修 / 未來要改進

### 7.1 刻意延後（設計上就切出去）

| 項目 | 說明 | 出處 |
|---|---|---|
| **INV-358-3 — legacy `ApplicationModel` 的同名守衛** | `uq_active_app_model` 是依 UUID 的，所以一個 Application 仍可直接綁兩顆同名 model。該路徑在 `auth_engine.py:1114` 仍是活的（dual-read 窗口）。現況靠全序 + warning 保護，**沒有 DB 層守衛**。 | ADR-358 §7.2 Phase 4 |
| **tenant-scoped model 的唯一性** | `uq_model_per_tenant_provider_name` 維持不變（決策 #4）。跨 group 共享仍走 `GroupModelGrant`。 | PRD-273 §1.3 |
| **跨 provider 同名價格套利 pool** | `(pool, model_name)` 不含 provider，所以一個 pool 內不能放 `openai/gpt-4o` + `azure_openai/gpt-4o`。已明確裁決接受。 | ADR-358 §3.1 |

### 7.2 已知殘留缺陷

| 項目 | 影響 | 建議 |
|---|---|---|
| **`xparse_resource_manager` 的 endpoint id 未命名空間化** | `endpoint_resolver.py:76-84` 的 `f"{provider}-{model}".lower()` 既非 proxy 也非 group/tenant 命名空間化。兩顆獨立同名 model 會共用一個 RM endpoint id → 容量數字混同。只影響 shared on-prem endpoint + `throughput_first`，不碰憑證或 endpoint。 | 需 RM 側 endpoint-id 命名空間化，屬另一個 ADR |
| **`deployments-view.tsx` 依名字 join** | 把 audit 的 usage row 依 `definition_name` join catalog deployment。catalog 是不同命名空間（ADR-358 沒動），風險低，但若兩個 deployed model 共用 `definition_name` 會拿到 `/stats/top-models` 合併後的數字。已加註為 best-effort。**2026-08-02：姊妹檔 `deployment-detail.tsx:97-100` 做完全相同的 join 卻漏了註記，已補上。** | 改用 `/audit/stats/top-model-uuids` 依 `model_uuid` join，需先在該面曝露 deployment→model_uuid 連結 |
| **group 層完全無唯一性 → 孤兒 model** | 同 group 可堆出多顆同名 model，包含未加入任何 pool 的孤兒。Console 走原子路徑已關掉這條，但直接打 API 仍可造成。 | 需要就加一支盤點/清理指令；ADR-358 §5.2 已明白記錄這是接受的取捨 |
| ~~**`display_name` 只在 create 檢查**~~ **→ 2026-08-02 已修改名路徑** | 原本 `update_model.py` 把 `display_name` 列為可 patch 且**零檢查**，於是整條守衛只差一次改名就能繞過（先用暫時標籤建立、再改名到已被佔用的那個）。已加 `find_display_name_conflict`（依擁有面推導 scope、排除 subject）。**既有資料仍違反（4 筆 `gpt-5.4-mini`）**——守衛只管新寫入。 | 維持不升格為 DB constraint（會讓 migration 在真實資料上失敗）。任何依 identity 拆分的呈現面仍必須有退路 |
| **🟠 auto-provision 不受 `display_name` 守衛管（2026-08-02 發現；程式碼層確定，端到端未重現）** | **確定的部分**：`_applications.py:657` 直接對 ORM 做 `ModelEntity.objects.get_or_create(..., defaults={"display_name": _model_name})`，**不走 `create_model` use case**，所以結構上不受守衛管，且 `display_name` 恆等於 `model_name`。<br>**沒能證實的部分**：它是否真的會產生一對同標籤 model。dev DB 查證結果**反而不支持**——4 筆 `provisioned_by` 非空的 model 全部出自 Console 的原子 create 路徑（`display_name` 是使用者自訂的 `jkljkl` / `gpt-4o-02` / `gpt-4o-123` / `gpt-4o-testing`），**沒有任何一筆出自那個 auto-provision 區塊**；唯一的 `(group, display_name)` 碰撞對（`rd_team` / `gpt-5.4-mini`）兩顆也都不是 auto-provisioned。想端到端重現時被 §10.7 的 dev stack 缺件擋住（建 application 一律 500）。<br>**假如它真的觸發**，失效的只有一面：MEMBERSHIP-05 保證單一 pool 名稱唯一 → 任一 proxy 的 Models 分頁只會有一列（U1 不受影響）；dashboard 階梯會退到 uuid 尾碼（仍可讀）；壞的是**第三個 proxy 的 Add Model → Existing 選擇器**（A、B 都不在 C 的 pool 裡而並列，副標 `provider · [model_name] · [endpoint]` 在 display_name==model_name 時中段不印 → 兩個選項逐字相同，違反 U2）。 | **先補證據再修**：在有 `xparse_routing` mount 的 ephemeral 容器裡跑真 endpoint，確認同 group 兩個 `llm_proxy_cloud`+同 `model_name` 是否真的產出同 `display_name`。證實後三選一：① auto-provision 改走 `create_model`；② defaults 的 `display_name` 帶上 proxy code；③ Existing 選擇器副標補 credential／uuid 尾碼退路（純呈現面、最安全）|
| **未鏡射的 `ProxyModelSource` 列不受守衛** | `bulk_create` 繞過 `save()` → mirror 為 `""` → 被 constraint 的 `~Q(...="")` 條件排除。今天沒有任何 `bulk_create` 在這張表上，且 migration 回填了所有既有列。 | 若未來新增 bulk 寫入者，需在該處自行 derive mirror |
| **embeddings 沒有 `model_uuid`** | `routes/embeddings.py:228` 解析的是 `EmbeddingProfileConfig`／YAML profile 而非 Model row，結構上沒有 uuid；且 `ModelPriceVersion` FK 到 `Model`，所以本就不可計價。拆開視圖裡它們落在 `__no_model_uuid__`。 | PRD-215 已列 out of scope。要修需先讓 embeddings 走 Model row |
| **ADR-356 的 backend binding 邊界** | ADR-358 §2.1 item 6 宣告 `credential` 與 `ModelPriceVersion` 所有權留在 `Model`。若 ADR-356 未來讓 binding 吸走 credential，價格必須一起搬，否則 per-proxy 價格隔離會**靜默失效**（`uq_mpv_one_active_open_segment_per_model` 讓一顆 L1 model 只有一份價格表）。 | 已透過 #3054 寫進 ADR-356 §2.2 當明確邊界；作者仍需覆核 |

### 7.3 流程/工具問題（比程式碼更值得修）

| 問題 | 證據 | 建議 |
|---|---|---|
| **Static Gates 不跑 docs-only PR** | `ci.yml` 的 `pull_request.paths` 不含 `docs/**`。這就是 ADR 撞號能進 main 而沒人發現的原因。 | 把 `docs/adr/**` `docs/prd/**` 加進 paths，或把 ADR index gate 拆成獨立的輕量 workflow |
| **ADR 號碼對著過期的 main 配** | ADR-331 被搶三次、ADR-354 + PRD-269 雙撞。 | 配號前強制 `git fetch origin main`；或做一支 `scripts/next_free_adr.py` 直接查 remote |
| **`ADR_INDEX.md` 的 auto block 容易被手改** | 我自己就手改了一次（`STALE-INDEX`），CI 才抓到。 | 文件裡已有 §usage 說明，可考慮加 pre-commit hook |
| ~~**`console-app-refactor` 沒有 test runner**~~ **→ 這句話本身是錯的（2026-08-02 更正）** | `vitest.config.ts` 自 PR #1997 就存在，`src/` 下有 16 個測試檔，其中包含 `progress-tabs-plugin.test.ts`、`proxy-detail-view.test.ts`、`audit/_components/events-table.test.tsx` —— 正好涵蓋這次動到的檔案。真正的原因是**標籤階梯寫成 inline closure**（`:638-665`），結構上無法從測試檔匯入，所以那 67 行新邏輯零覆蓋。`frontend/console-app-refactor/CLAUDE.md:16` 的那句宣告是過期資訊，本身就是這個誤判的來源。 | 已修：抽成 module-level 純函式 `modelDisplayLabel`（比照 `appDisplayLabel`）+ 補 vitest；CLAUDE.md 已更正並補上「邏輯埋在 inline closure = 無法測試」的指引 |
| **守衛放在 use-case 層，寫入路徑卻不只一條** | `display_name` 的唯一性守衛在 `create_model` / `update_model`，但 `_applications.py` 的 auto-provision、seed 指令、backfill 都直接寫 ORM。ADR-358 明確選擇不加 DB constraint（真實資料會讓 migration 失敗），代價就是守衛**不是不變量**，任何繞過 use-case 的寫入者都免疫。這不是實作疏忽，是那個取捨的必然後果——但當時沒有被完整盤點。 | 決定不加 DB constraint 時，同時盤點「還有誰會寫這張表」並逐一決定要不要接守衛；否則守衛的覆蓋率會被誤認為 100% |
| **本機 git 憑證是沒權限的帳號** | `credential.helper=store` 存的是 `lei23lei`，對這兩個 repo 都無權限（私有 repo 回 404）。有權限的是 `LeiIeongTam-Peter`。 | `gh auth switch --user LeiIeongTam-Peter`，或清掉舊憑證讓它重新認證 |
| **dev DB 殘留 revert 分支寫入的資料** | 4 筆 guardrail probe policy 帶著已被移除的 schema 欄位，讓所有 inference 500。 | revert 一個含 schema 變更的 PR 時，同時清掉該分支 seed 的資料 |

---

## 8. 運維注意事項

### 部署順序（有硬依賴）

1. **audit image**（Xparse-Audit#86 已 merge）→ 部署後**必須跑**：
   ```bash
   docker exec xparse-audit python -m audit.storage.rollup_rebuild
   ```
   legacy rollup 是 watermark-cursor projector，已掃過的歷史桶**不會**自己長出新的 `dim_type`。在這之前，寬時間窗的「拆開／合併」成本視圖對歷史資料會不一致。

   > 這支指令**無法在本機 python 跑** —— 它從 `AUDIT_DB_HOST=xparse-db`（Docker 網路 hostname）解析 DSN，而該 DB 沒有對外 publish 5432。

2. **IAM migration `0222`** —— 正式環境建議先 dry-run。它會在任何 schema 變更**之前**做一次無副作用的碰撞稽核，乾淨 DB 上預期命中 0 筆；若某個 pool 同時掛了 group-scoped 與 tenant-scoped 的同名 model（今天合法、無人擋），它會逐筆列出 `(proxy, provider, model_name, uuids)` 與補救指令，且**不留半套 schema**。

3. **Console 要在 audit 之後** —— `by_model_uuid` 缺席期間前端會顯示「不可用」（刻意的，比謊稱「無花費」好）。

### 監控

新 counter `candidate_set_name_collision` —— 任何 > 0 都該告警，表示有 pool 早於 constraint 存在且帶著同名成員（最可能是 group-scoped + tenant-scoped 那個形狀）。配對的 `CANDIDATE_SET_NAME_COLLISION` warning log 會印出雙方 uuid。

---

## 9. Commit 追溯

**parent（`futurenestit/xparse`，merge commit `67ae25ec3`）**

```
c33fa473e  docs(model-identity): PRD-273 + ADR-358 + DISCUSSION + SPEC-171 + Core 層 + wiki
c68cbdc7c  feat(iam): per-proxy Model name namespace — drop the group constraint, guard the pool
a470533ea  feat(gateway): key the last mile on model_uuid instead of (provider, model_name)
3d0469775  chore(audit): bump submodule to the ADR-358 model_uuid dimension
66cc92994  feat(console): make same-named models tellable apart, and split cost by identity
1e977d4e6  fix(docs): regenerate the ADR_INDEX auto block with the script, not by hand
14bcfb049  fix(docs): resolve the ADR-331 and ADR-354 number collisions
80b77fa2a  fix: three corrections found by running ADR-358 against a real dev database
```

**audit submodule（`futurenestit/Xparse-Audit`）**

```
fb9138d  feat(audit): model_uuid as a first-class aggregation dimension (ADR-358 / PRD-273)
```

**ADR-356 收斂（#3054，base 是 `worktree-adr-353-decouple-surface-identity`）**

```
docs(adr): ADR-356 identity scope is the pool, not the group (converge with ADR-358)
```

**收尾一輪（[#3058](https://github.com/futurenestit/xparse/pull/3058)，branch `fix/adr358-console-followup`，base `main`）**

```
c544232e2  fix(console): stop the cost dashboard printing bare UUIDs for a platform operator
fb1a7da3d  fix(console): refresh the proxy pool list after an atomic create+attach
03abecf6d  feat(iam): guard display_name on the rename path, not only on create
ab2e56b17  fix(console): name the model identity on the audit pane, annotate the rest
```

---

## 10. 2026-08-02 追加一輪：主線 merge 後的收尾（[PR #3058](https://github.com/futurenestit/xparse/pull/3058)）

起點是三個被點名的 Console 檔案 —— `cost-usage/index.tsx`、`llm-proxy/proxy-detail-view.tsx`、`audit/page.tsx`。**結論是那三個都不用改**，但沿著它們往外查，發現主線交付有一個會出現在預設畫面上的缺陷、一個回歸，以及幾個沒收斂的名稱鍵面。

### 10.0 那三個檔案為什麼不用改

| 檔案 | 依據 |
|---|---|
| `_tabs/cost-usage/index.tsx` | 45 行的殼，只渲染 `<GridCanvas>` + `useState(INITIAL_LAYOUT)`。零 hook、零 API、零 model 邏輯，且無 localStorage 所以沒有舊 layout 殘留問題。model 的部分全在 `initial-layout.ts:143-155` 與 `progress-tabs-plugin.tsx` |
| `llm-proxy/proxy-detail-view.tsx` | 全檔對 model 只做兩件事：`:159` 抓 `useProxyModelSources`、`:300` 算 `modelCount` 當分頁 badge，`:664` 整包丟給 `ModelsTab`。不渲染任何名稱／憑證／uuid |
| `(overview)/audit/page.tsx` | `FIELD_DEFS`（`events-table.tsx:79-92`）與 `filterConfigs`（`:620-639`）都沒有 model 欄位或 filter；distribution / time-series 也沒有 model 維度。**但它展開列所開的 Details pane 有問題**，見 10.3 |

### 10.1 🔴 跨租戶時 By Model 分頁渲染裸 UUID（主線缺陷）

`GET /iam/tenants/{uuid}/models/catalog` 是嚴格租戶隔離的（`_tenant_models.py:218`，跨租戶 403），沒有 global 變體。而 system_admin 的 `tenantId` 來自 `?tenant=` URL 參數（`use-scope-resolution.ts:51`），**預設是 null（「All tenants」）**。

失效鏈：`progress-tabs-plugin.tsx:526` 傳 `undefined` → `services/iam.ts:1354` 的 `enabled: !!tenantUuid` 關掉 query → `modelCatalogLoading` / `modelCatalogError` 皆為 false → `:572` 的 loading 與 `:583-587` 的 error 都不觸發 → `byUuid` 是空 Map → `:646` 的 `if (!m) return modelUuid` 對每一列生效。

**平台管理員打開 dashboard，預設的 By Model 分頁就是五個裸 UUID，而且沒有任何錯誤或載入提示。**

證明這是遺漏而非設計：`top-app`（`:501`）與 `top-group`（`:536`）都寫了 `!tenantId` 的 cross-tenant fallback，只有 `top-model-uuid` 沒有。

**修法**（裁決：退回 merged 視圖 + 明示）：沒有租戶時改讀 `breakdowns.by_model`，並在列上方渲染 `⚠ Cross-tenant view — merged by name`。PRD-273 N-4 的「舊 audit build → 不可用」原樣保留，只是收斂到真的在跑拆開視圖時才適用 —— **兩個原因不能混在同一個條件裡**。

順帶：手動把來源切到 merged 的 `top-model` 時，執行期分頁下拉只顯示 `tab.label`（「By Model」），「(merged by name)」那串只在編輯模式看得到 —— 沒配置過面板的檢視者無從得知一列可能是兩顆 model。已抽出 `MergedByNameRows` 讓兩條路徑共用同一個標示。

### 10.2 🔴 建立 model 後清單不刷新（本次改動造成的回歸）

**這是 `66cc92994` 原子化改動造成的。** 改動前「New」分頁是 create → bind 兩步，刷新是 bind 的副作用（`useAddModelSource.onSuccess` invalidate `["iam","applications",proxyUuid,"model-sources"]`，也就是 Models 分頁真正在讀的 key）。ADR-358 為了避免 bind 失敗留下孤兒 Model 改成單次原子呼叫（`provisioned_by`），`create-model-dialog.tsx:541-547` 在 group scope 直接 return，**bind 不再被呼叫**，而 `useCreateGroupModel` 只 invalidate `["iam","groups",groupUuid,"models"]`（Existing picker 用的）。清單的 key 從此沒人動 → 要手動重新整理。

`models-tab.tsx:505` 也沒有傳 `onCreated`，所以 dialog 內的 `onCreated?.()` 是 no-op，不是備援。

**修法**：invalidation 跟著 mutation 走（CLAUDE.md 慣例）—— `useCreateGroupModel` 的 `onSuccess(_created, req)` 在 `req.provisioned_by` 存在時（代表後端同 transaction 也做了 attach）一併 invalidate 該 proxy 的 pool 清單。對所有呼叫端生效，不只這個 dialog。租戶共享 proxy 那條路徑不受影響（沒有原子路徑，仍走 create→bind）。

> **教訓**：把 N 步合併成 1 步時，要盤點「原本那 N-1 步各自帶了什麼副作用」。這裡被合併掉的不只是一次 API 呼叫，還有一次 cache invalidation。

### 10.3 Audit Details pane 查對了 uuid 卻印裸名稱

`event-explanation.tsx:96-98` 用 `flat.model_uuid` 呼叫 `useModel`（uuid-keyed，正確），但只取 `served_model_name ?? model_name` 這個裸名稱 —— 兩顆同名 model 的句子完全一樣。已改為額外輸出一列「實際執行的模型」，用 `display_name || model_name` + `provider` 修飾。

刻意**不做**成連結：查證後 `/models?focus=` 的唯一消費者是 `deployments-view.tsx`（catalog deployment 命名空間），用 IAM `model_uuid` 連過去會靜默什麼都不 highlight。`resolveEntityLink` 的 docstring 已補上這個 caveat。

身分列做成獨立 param row 而不是塞進句子，是為了避免無歧義的情況每次都多印一次 model 名稱。

### 10.4 rename 可以繞過 create 守衛

見 §7.2 修訂列。`create_model.py:98` 擋，`update_model.py` 零檢查。已補 `find_display_name_conflict`（依擁有面推導 scope、排除 subject、回傳衝突列以便訊息指名 uuid），配 8 個真 DB 測試 + 4 個 use-case 測試。PRD-273 N7 與 A7b/A7c、ADR-358 §7.1 已同步。

### 10.5 檔案清單

| 面向 | 檔案 |
|---|---|
| Dashboard | `progress-tabs-plugin.tsx`（fallback + `modelDisplayLabel` / `modelCostEntries` / `MergedByNameRows` 抽出 + 檔頭契約更新）· `.test.ts`（+13） |
| Cache | `services/iam.ts::useCreateGroupModel` · `services/iam-model-create-invalidation.test.tsx`（新增，3 測試） |
| Audit | `event-explanation.tsx` · `lib/audit-event.ts` · `.test.ts`（+4） |
| IAM | `update_model.py` · `model_repository.py` · `tests/unit/test_use_case_model_crud.py`（+4）· `tests/unit/test_model_repo_provisioner.py`（+8） |
| 前端 edit | `edit-model-dialog.tsx`（rename 前置檢查 + grant dialog 標題加 provider） |
| 註記／型別 | `deployment-detail.tsx` · `resource-inventory/page.tsx` · `types/audit.ts`（`by_model_uuid` meta + `top_model` 名稱合併註記）· `services/audit.ts` |
| 文件 | `PRD-273`（N7 + A7b/A7c）· `ADR-358`（§2.1 · §7.1）· `console-app-refactor/CLAUDE.md` |

### 10.6 驗證

| 範圍 | 結果 |
|---|---|
| Console typecheck | 乾淨 |
| Console vitest | **217 passed / 5 failed** —— 對 baseline worktree 逐項比對，**失敗集合完全相同**（5 個既有），淨新增 0 |
| IAM（ephemeral 容器，repo root 掛載） | **38 failed 前後集合完全相同**，淨新增 0；新增 12 個測試全綠 |
| §8.1 dogfood | 三處都先看它紅過：拿掉 cross-tenant fallback → 正好 3 個守衛紅（含「絕不輸出裸 UUID 標籤」）；拿掉 rename 守衛 → `DID NOT RAISE`；拿掉 invalidation → pool 清單那條紅，另兩條維持綠 |
| eslint / prettier | 錯誤全在未觸及的檔案（既有） |

> **baseline 比對是必要的**：repo 有數十個既有本機失敗，「我弄壞了幾個」只能靠對同一組指令跑 stash 前後的失敗集合 diff 得知，看絕對數字沒有意義。

### 10.7 對 live dev stack 的實測（2026-08-02）

IAM 有 mount source（`docker restart xparse-iam` 即載入）；**console 容器沒有 mount**，跑的是 prod image，所以前端要本機 `PROXY_TARGET=https://127.0.0.1:3000 pnpm dev` 才測得到改動。

| # | 驗收項 | 操作 | 結果 |
|---|---|---|---|
| 1 | **A7b** 改名到已佔用的 `display_name` | `PATCH /iam/models/{gpt-4o-02}` → `"gpt-4o-123"` | **400**，訊息指名 holder `fbb58a6b-…`（改動前是靜默成功） |
| 2 | **A7c** 重送自己現有的標籤 | 同上 → `"gpt-4o-02"` | **200**（exclude-self 正確，不會與自己衝突） |
| 3 | 改名到未佔用的標籤 | → `"gpt-4o-02-probe"` → 復原 | **200 / 200** |
| 4 | **U4 / 10.1** 跨租戶 By Model | system_admin，URL 無 `?tenant=` | 顯示 `⚠ Cross-tenant view — merged by name…` + `gpt-4o $0.3148` / `gpt-4o-mini $0.0567`，**無裸 UUID** |
| 5 | **U4 / A9** 拆開視圖 + 總額一致 | 同頁加 `?tenant=dbe4dcc7-…` | 切為 `gpt-4o-testing $0.3148` / `gpt-4o-mini · openai $0.0567` —— **金額與合併視圖逐項相同**，標籤換成身分，`gpt-4o-mini` 因偵測到同名而帶 provider |
| 6 | **U1** pool 清單可辨識 | proxy `gpt_4o_816e` 的 Models 分頁 | `gpt-4o-testing` + wire-name 副標 `gpt-4o` + credential badge `openai-guardrail` |
| 7 | **10.2** 建立後即時刷新 | Add Model → New → Create & Add，**全程不重新整理** | 分頁 badge `Models 1` → **`Models 2`**，新列立即出現 |
| 8 | **N7 前端** 改名前置檢查 | Edit Model 把標籤改成 `gpt-4o-testing` | 行內錯誤出現，**Save Changes 變 disabled**（送出前擋下） |
| 9 | **N7 前端** exclude-self | 同欄位改回自己的名字 | 錯誤消失（不與自己衝突） |
| 10 | **10.3** Audit Details 身分 | 展開一筆 `execution.completed` | 句子「呼叫模型 **gpt-4o**」＋新列「**實際執行的模型：gpt-4o-testing · openai**」 |

探測資料已全數還原（`gpt-4o-02` 標籤復原、probe model 與其 source 列刪除、`notification-local` 仍 7 顆 model、pool 仍 1 筆）。

#### 實測順帶暴露的既有問題（與本功能無關，但擋住驗證）

| 問題 | 證據 | 影響 |
|---|---|---|
| **dev stack 建不了 application** | `POST /iam/groups/{g}/applications` 一律 500：`ImportError: cannot import name 'get_parameters_schema' from 'xparse_routing'`。IAM 容器沒有 mount `xparse_routing`（memory 早記錄過這個缺件）。 | 這就是 §7.2 那條 auto-provision 假說無法端到端重現的原因。要驗它得補 mount |
| **`DELETE /iam/models/{uuid}` 在 detach 之後必定 500** | detach 只把 `ProxyModelSource` 改成 `status='removed'`（軟刪），而 FK 是 `PROTECT`；delete use case 的 `has_active_bindings` 只看 **active**，所以前置檢查放行、ORM 才炸 `ProtectedError`。**沒有任何 API 路徑能刪掉已 detach 的 model** —— 正是 §7.2「孤兒 model」那條的成因，而且以 500 而非可行動訊息呈現（違反 ADR-093 inv-4）。清理只能走 raw ORM。 | 既有缺陷，非本次造成。已開 [#3059](https://github.com/futurenestit/xparse/issues/3059) |
| **`iam_pep` 每個請求都拋 `KeyError: 'rule_id'`** | `loader.py:273` —— dev DB 有 policy bundle 的 content 缺 `rule_id`。被吃掉後退回 `authz_path=legacy_key_type`，請求照樣 200。 | PDP 實際上沒在跑，全靠 legacy key-type 授權（呼應 issue #1453 的 shadow-enforce 洞） |
