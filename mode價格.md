# Model Pricing Management 變更說明

日期：2026-07-21

## 目的

這次變更讓平台可以針對每個 LLM model 管理價格，並讓後續 usage billing / cost reporting 使用「請求當下的價格快照」計算成本。

支援兩種價格：

- Normal Price：model 層級的預設價格，沒有 promotion 時使用。
- Promotional Price：有開始與結束日期的限時價格，期間內覆蓋 Normal Price。

Promotional Price 採 half-open interval：`[effective_from, effective_to)`。也就是 `effective_from <= now < effective_to` 時 promotion 生效。Frontend 目前只讓使用者選日期，不選 hour/minute；日期會轉成 UTC midnight ISO datetime，例如 `2026-07-21` 會送成 `2026-07-21T00:00:00Z`。

## End-to-End Workflow

1. 使用者在 Console 建立或編輯 model。
2. Normal Price 寫在 model 本身的 `cost_per_input_token`、`cost_per_output_token`、`pricing`。
3. 使用者在 edit model dialog 管理 Promotional Prices。
4. Frontend 先做基本 validation：必填 start/end date、價格不可空白或負數、區間不可重疊。
5. Backend 是 authoritative validation：
   - Promotional Price 必須有 `effective_to`。
   - `effective_to` 必須晚於 `effective_from`。
   - active promotional windows 不可重疊。
   - write boundary 使用 transaction，edit 會 retire 舊 row 並建立新 active row。
6. IAM validate runtime path 解析 effective price：
   - 如果目前時間落在 promotion window，使用 promotion price。
   - 如果沒有 promotion 或目前時間在 promotion gap，使用 Normal Price。
7. Gateway 收到 IAM auth context 後，把實際執行 model 的價格 freeze 成 audit price snapshot：
   - `price_in`
   - `price_out`
   - `price_source`
   - `price_version_uuid`
8. Audit event / OTel span / Tempo correlation 都攜帶 price snapshot。
9. Dashboard、stats、legacy usage time-series 依照 snapshot 計算 cost：
   - `input_tokens * price_in + output_tokens * price_out`
   - 沒有 price snapshot 的 legacy/unpriced records 不再套用固定估算價。

## Backend Data Model

### Normal Price

Normal Price 仍存在 model row 上：

- `Model.cost_per_input_token`
- `Model.cost_per_output_token`
- `Model.pricing`

這代表一個 model 只能有一組 default price。

### Promotional Price

Promotional Price 使用 `ModelPriceVersion`：

- `price_version_uuid`
- `model`
- `tenant_uuid`
- `effective_from`
- `effective_to`
- `cost_per_input_token`
- `cost_per_output_token`
- `pricing`
- `version`
- `active`
- `created_by`

重要設計：

- Promotional Price 是 bounded period，不允許 open-ended promotion。
- active rows 不可重疊。
- edit 不覆寫原 row，而是 retire 舊 active row，再建立新 active row。
- retired rows 保留 audit history。

## Backend API

### Price Schedule API

- `GET /iam/models/{model_uuid}/price-schedule`
  - 取得 model 的 active promotional price windows。
- `POST /iam/models/{model_uuid}/price-schedule`
  - 新增 promotional price window。
- `PATCH /iam/models/{model_uuid}/price-schedule/{price_version_uuid}`
  - 編輯 promotional price window；backend 會 retire 舊 row 並建立新 row。
- `DELETE /iam/models/{model_uuid}/price-schedule/{price_version_uuid}`
  - retire promotional price window。

### Application Model Effective Price

Application model response 新增 effective price 欄位，讓 frontend table 可以直接顯示目前實際價格：

- `effective_cost_per_input_token`
- `effective_cost_per_output_token`
- `price_source`
- `price_version_uuid`

如果 `price_source = "promotion"`，Console 顯示 promotional price；否則顯示 normal price。

## Cost Calculation Behavior

### 已修正

之前 legacy usage correlation path 還有固定估算：

```text
(input_tokens + output_tokens) / 1000 * 0.04
```

現在已改為：

```text
input_tokens * price_in + output_tokens * price_out
```

這讓 billing/cost reporting 可以正確反映：

- 不同 model 的不同價格。
- promotion 生效期間的價格。
- promotion gap 期間回到 normal price。
- request-time snapshot，不會被事後改價影響歷史成本。

### Unpriced Records

如果舊資料沒有 `price_in` / `price_out`：

- correlation summary 的 `estimated_cost` 會是 `None`。
- time-series cost bucket 只累加有 price snapshot 的 records。
- 不會用固定 `$0.04 / 1K tokens` 自動估價。

## Frontend UI

### Create Model Dialog

建立 model 時可設定 Normal Price。

UI 使用 `$ / M tokens` 顯示，送到 backend 前轉成 `$ / token`。

### Edit Model Dialog

Edit model dialog 包含：

- Normal Price section。
- Promotional Prices section。
- Promotional Price 的 date range 與 price setting 分開呈現，但依照最新要求，start date / end date 回到同一 row。
- 不提供 hour/minute input；只提供 date input。

### Models Table

`models-tab.tsx` 現在顯示 effective price：

- 有 active promotion 時顯示 promotion price 和 `Promo` badge。
- 沒有 active promotion 時顯示 normal price。
- 價格 schedule mutation 後會 invalidate `["iam", "applications"]`，讓 table refresh effective price。

## 主要檔案路徑

### Main repo: `xparse`

Backend IAM / pricing:

- `/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/db/django_database/_model_pricing.py`
- `/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/api/schemas/_pricing.py`
- `/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/api/schemas/_application.py`
- `/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/api/ninja_api/_models.py`
- `/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/api/ninja_api/_helpers.py`
- `/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/core/auth_engine.py`
- `/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/application/dto/auth_context_model.py`
- `/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/application/use_cases/model/create_model.py`
- `/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/application/use_cases/model/update_model.py`
- `/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/client.py`

Gateway / audit snapshot:

- `/Users/peter/Desktop/X-parse/xparse/bustream/gateway/iam_http_client.py`
- `/Users/peter/Desktop/X-parse/xparse/bustream/gateway/audit_helpers.py`
- `/Users/peter/Desktop/X-parse/xparse/bustream/audit/schema.py`
- `/Users/peter/Desktop/X-parse/xparse/bustream/audit/xparse_bridge.py`
- `/Users/peter/Desktop/X-parse/xparse/bustream/audit/otel.py`

Frontend Console:

- `/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/components/features/llm-proxy/models/create-model-dialog.tsx`
- `/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/components/features/llm-proxy/models/edit-model-dialog.tsx`
- `/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/components/features/llm-proxy/models/models-tab.tsx`
- `/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/components/features/llm-proxy/models/price-schedule-section.tsx`
- `/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/lib/price-schedule.ts`
- `/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/services/iam.ts`
- `/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/types/iam.ts`

Main repo tests:

- `/Users/peter/Desktop/X-parse/xparse/xparse_iam/tests/unit/test_model_create_pricing.py`
- `/Users/peter/Desktop/X-parse/xparse/xparse_iam/tests/unit/test_model_price_version.py`
- `/Users/peter/Desktop/X-parse/xparse/tests/unit/test_use_case_model_crud.py`
- `/Users/peter/Desktop/X-parse/xparse/tests/unit/audit_tests/test_price_snapshot.py`
- `/Users/peter/Desktop/X-parse/xparse/tests/unit/audit_tests/test_otel_mapping.py`
- `/Users/peter/Desktop/X-parse/xparse/tests/unit/audit_tests/test_tempo_client.py`
- `/Users/peter/Desktop/X-parse/xparse/tests/contract/test_sidecar_trace_correlation.py`
- `/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/components/features/llm-proxy/models/price-schedule-section.test.tsx`

### Submodule repo: `3rd/xparse_audit`

Audit correlation / usage cost:

- `/Users/peter/Desktop/X-parse/xparse/3rd/xparse_audit/src/audit/correlation/models.py`
- `/Users/peter/Desktop/X-parse/xparse/3rd/xparse_audit/src/audit/correlation/engine.py`
- `/Users/peter/Desktop/X-parse/xparse/3rd/xparse_audit/src/audit/correlation/tempo_client.py`
- `/Users/peter/Desktop/X-parse/xparse/3rd/xparse_audit/src/audit/api/routers/usage.py`

### External documentation file

- `/Users/peter/Desktop/X-parse/docs/mode價格.md`

注意：這份文件位於外層 `/Users/peter/Desktop/X-parse/docs`，不屬於 `xparse` git repository。`xparse` PR 不會包含這個外層文件，除非另外複製到 `/Users/peter/Desktop/X-parse/xparse/docs/`。

## Verification 已執行

Backend / audit:

```bash
python -m compileall -q 3rd/xparse_audit/src/audit/correlation/models.py 3rd/xparse_audit/src/audit/correlation/engine.py 3rd/xparse_audit/src/audit/correlation/tempo_client.py 3rd/xparse_audit/src/audit/api/routers/usage.py bustream/audit/otel.py
uv run pytest -q -o addopts='' tests/contract/test_sidecar_trace_correlation.py tests/unit/audit_tests/test_tempo_client.py tests/unit/audit_tests/test_otel_mapping.py
git diff --check
git -C 3rd/xparse_audit diff --check
```

結果：

- `69 passed`
- `compileall` passed
- `git diff --check` passed

之前也已執行過：

- frontend `pnpm` type/test checks for the pricing UI path
- Python compile checks for IAM pricing changes
- targeted unit tests for model pricing and audit snapshot behavior

已知環境限制：

- Full backend pytest 曾被既有環境問題阻擋：`pytest-cov` / `pytest-django` / `jwt` 相關 dependency 或 pytest config 問題。
- `uv run pytest` 會自動修改 `uv.lock`，每次測試後已還原 `uv.lock`。

## PR 結構

因為 `3rd/xparse_audit` 是獨立 git submodule，這次實際需要兩個 PR：

1. `Xparse-Audit` PR
   - 包含 audit correlation / usage cost 修正。
   - 先 merge 或至少確保 branch commit 存在 remote。
2. `xparse` PR
   - 包含 IAM / Gateway / Frontend / tests。
   - 包含 `3rd/xparse_audit` submodule pointer update，指向 audit PR 的 commit。

## ADR-093 Compliance

| Invariant | Status | Evidence |
| --- | --- | --- |
| No partial state transition | Satisfied | `upsert_price_segment()` 使用 `transaction.atomic()`；edit retire + create 在同一 transaction。 |
| Pre-condition validation before commit | Satisfied | API validation 檢查 bounded promotion、`effective_to > effective_from`；DB write boundary 檢查 overlap。 |
| Post-condition verification after commit | N/A for request runtime; covered by tests for persisted behavior | Pricing schedule behavior以 unit tests 驗證 create/edit/list/delete 與 effective resolution。 |
| Fail fast, no silent fallback | Satisfied | overlap / malformed promotion 回 400；legacy cost 不再 silent fallback 到固定價格。 |
| Identity binding stability | Satisfied | price snapshot 在 runtime auth/audit boundary freeze；historical usage cost 使用 snapshot，不受事後改價影響。 |

## Reviewer Notes

- Normal Price 是 model default；Promotional Price 是 bounded override。
- Promotional windows 不可重疊；相鄰 windows 允許，因為使用 half-open interval。
- Frontend 只輸入日期，因此 backend 看到的是 UTC midnight datetime。
- Cost calculation 目前是 list-price estimate；沒有做 currency conversion / tax / discount stacking。
- Legacy unpriced records 不會被硬套預估價，避免 billing 報表產生錯誤成本。
