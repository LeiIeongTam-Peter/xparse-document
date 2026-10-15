# Guardrail V1 — PII 遮罩 Policy — Frontend 實作參考（給 frontend agent）

> 目標：在 `frontend/console-app-refactor/` 上操作「PII 遮罩 guardrail policy」的建立／發佈／綁定／檢視。
> ⚠️ **後端狀態更正（2026-07-17）**：ADR-309 七個 PR（#2214→#2234）GitHub 顯示 MERGED，但因 stacked-merge 方向錯誤，**PR-2..7 的程式碼從未落到 main**（main 只有 PR-1 docs，仍是舊 nemo/profile schema）。reland 進行中：**PR #2311**。#2311 merge 前，對 main/現行環境送 v1 形狀會被舊 schema 400 拒絕（`extra="forbid"`）；本文其餘內容描述的是 #2311 落地後的世界。
> **API service 層與 policy 編輯表單已寫好——你只做組裝與調整，不要重寫 hooks、不要直接 fetch、不要自己發明 content 形狀**。
> 契約來源：`docs/specs/SPEC-219-guardrail-pii-v1-contract.md`（xparse repo 內）；後端寫入邊界 `xparse_iam/xparse_iam/application/use_cases/policy/validate_policy_content.py`。

---

## 0. 這個功能是什麼（一句話 + 白話）

**一句話**：管理員勾選要保護的 PII 類別（姓名、電話、身分證⋯共 12 類），之後任何走該 policy 的 chat 請求，輸入裡的個資會在**送到 LLM provider 之前**被換成 `[NAME_1]`、`[PHONE_1]` 這類 token——偵測模型（GLiNER）自架在客戶環境內，**個資原文不出境**。

白話流程：使用者送「我叫陳大文，電話0912345678，我叫什麼名字？」→ provider 實際收到「我叫[NAME_1]，電話[PHONE_1]，我叫什麼名字？」→ 模型回「你的名字是[NAME_1]」。Client 拿 API key 照常呼叫 `/v1/chat/completions`，**不能**用 request body 選擇或關閉 guardrail——一切由 key 綁定的 policy 決定。

V1 範圍（out-of-scope 別做 UI）：只遮 input（output 遮罩是 V2）；只有 mask 動作（沒有 block）；沒有 content-safety 分級、judge、keyword 欄位（全部已被 ADR-309 移除）。

---

## 1. 後端 API：有，而且是一條鏈（不是單一端點）

`POST /apis/iam/policies` 200 只是第一步（建 policy 殼）。讓 policy **真正生效**要走完整條 versioned-policy 鏈（PRD-204 / ADR-259 物件模型）：

| 步驟 | 端點 | 前端 hook（`src/services/iam.ts`） |
|---|---|---|
| 1. 建 policy 殼 | `POST /iam/policies`（body：`code`, `policy_kind:"guardrail"`, `owner_scope_type`, `owner_scope_id`, `tenant_uuid`） | `useCreateVersionedPolicy()` / `versionedPolicyApi.createPolicy()` |
| 2. 建版本（帶 v1 content） | `POST /iam/policies/{policy_uuid}/versions`（body：`version`, `content`＝§2 形狀） | `useCreatePolicyVersion(policyUuid)` |
| 3. 發佈版本 | `POST /iam/policy-versions/{version_uuid}/publish` | `usePublishPolicyVersion()` |
| 4. 建 bundle + 加 item + 轉 active | `POST /iam/policy-bundles` → `POST /iam/policy-bundles/{u}/items`（`policy_version_uuid`）→ status→`active` | `useCreatePolicyBundle()` / `useAddPolicyBundleItem()` / `useUpdatePolicyBundleStatus()` |
| 5. 綁定到 scope | `POST /iam/policy-bundle-bindings`（`policy_bundle_uuid`, `target_scope_type`: tenant/group/application/deployment, `target_scope_id`, `effect:"mandatory"`） | `useCreatePolicyBundleBinding()` |
| （檢視）生效預覽 | effective-policy 端點（回 folded spec + provenance chain） | `useEffectivePolicy({policy_kind:"guardrail", tenant_id, ...})` |

- `create-policy-dialog.tsx` 已把 1→2→3 串成一個 mutation（`createPolicyWithVersion`）；4/5 在 policies 頁的 bundle/binding 流程裡。
- 生產環境 `/apis/iam/*` 是 nginx ingress 前綴；前端一律走 `iamClient`（自動帶 cookie 與路徑映射），**不要**手寫 fetch。
- 生效條件：runtime resolver 需在 `XPARSE_POLICY_RESOLVER_MODE=bundle_item_fold` 模式（rel/dev 現行模式）。

---

## 2. Content 契約（SPEC-219 v1）——唯一合法形狀

```json
{
  "version": "v1",
  "engine": "gliner_pii",
  "enabled": true,
  "mode": "shadow",
  "pii": {
    "enabled": true,
    "entities": ["person_name", "phone", "national_id"],
    "action": "mask",
    "score_threshold": 0.5
  }
}
```

- TS 型別：`VersionedGuardrailPolicyContent`（`src/types/iam.ts`）；由 `buildGuardrailContent(form)` 產生（`policies/_components/policy/policy-content-form.tsx`），**不要手組 dict**。
- `entities` 是 12 類閉集（`SupportedPiiEntity`）：`person_name 姓名 · email 電子郵件 · phone 電話 · national_id 身分證/居留證 · passport 護照 · address 地址 · birthdate 出生日期 · age 年齡 · gender 性別 · credit_card 信用卡 · messaging_id 通訊軟體ID · secret 金鑰/憑證`。UI 選項連雙語標籤都在 `PII_ENTITY_OPTIONS`。
- `score_threshold` ∈ (0, 1]，越低越敏感（只影響語意層；格式型如身分證/手機是精確比對）。
- `mode`：`shadow`＝只稽核不遮（預設，rollout 護欄）；`enforce`＝真的遮。
- `action` 固定 `"mask"`；`entities: []` 是**合法 no-op**（後端不會擋，表單有黃字警告）。

### 後端會拒絕的寫入（4xx，錯誤碼給 UI 顯示）

| 情境 | 錯誤碼 |
|---|---|
| 送舊版 `profile` 形狀（content_filter_level / judge / keywords⋯） | `GUARDRAIL_LEGACY_SCHEMA`（附新形狀指引） |
| entity 不在 12 類閉集、threshold 超界、engine 不是 `gliner_pii` | `INVALID_GUARDRAIL_CONTENT` |

---

## 3. 三條紅線（違反即錯）

1. **不要用 legacy guardrail API 做新東西**。`/iam/guardrail-policies`（`useGuardrailPolicies` / `useCreateGuardrailPolicy` 等 hooks）是舊 Django FK plane——它的 content-safety 欄位 runtime 已忽略，新 PII policy 一律走 §1 的 versioned 鏈。service 檔內已加註 deprecation 註解。
2. **繼承只會變嚴**：多層 scope（tenant→group→application→deployment）各自綁 guardrail 時，生效值是 fold 結果——`entities` 取聯集、`mode` enforce-wins、threshold 取最小。UI **不要**做「子 scope 移除父 scope entity」的互動，做了也不會生效。
3. **開啟 enforce 前要有延遲意識**：GLiNER CPU 實測 1KB p50≈2.2s、8KB p50≈19s（ADR-309 R2）。UI 若提供 shadow→enforce 切換，保留 shadow 為預設、不要引導使用者輕率切 enforce。

---

## 4. 已完成的工作（AI 接手前的現況地圖）

ADR-309 campaign（7 個 stacked PR，#2214 docs → #2215 GLiNER 容器 → #2216 sidecar engine → #2219 gateway → #2230 IAM → #2231 Console → #2234 刪 NeMo/Presidio）。前端側已 done 的：

| 檔案 | 狀態 |
|---|---|
| `src/types/iam.ts` | `GuardrailEngine="gliner_pii"`、`SupportedPiiEntity`（12 類）、`VersionedGuardrailPiiSpec`、v1 `VersionedGuardrailPolicyContent`；舊形狀保留為唯讀 `LegacyVersionedGuardrailPolicyContent`（只給讀取視圖用） |
| `src/services/iam.ts` | versioned-policy 鏈 hooks 全數存在（§1 表）；guardrail 區段已加「legacy 勿用／v1 鏈導引」註解。**沒有需要新增的端點** |
| `policy-content-form.tsx` | `GuardrailFormState={enabled, mode, piiEnabled, entities[], scoreThreshold}`；`GuardrailSettings` 是雙語 12-entity checkbox grid（含空選 no-op 警告、union 繼承提示）；`buildGuardrailContent` 產 v1 payload（threshold 驗證）；`guardrailFormFromContent` 同時吃 v1 與 legacy（legacy 用 client 端 coercion 映射顯示，存檔一律產生新 v1 版本） |
| `create-policy-dialog.tsx` / `create-policy-version-dialog.tsx` | 已接 `GuardrailSettings`，create→version→publish 一鍵串好 |

後端側（供 debug 對照）：偵測服務 `services/gliner-server/`（port 8401，`/v1/extract`）；sidecar `xparse_guardrail/`（port 8400，`/v1/guardrails/check`）；gateway enforcer 只在 input 遮、fail-closed（偵測服務掛掉 + enforce ⇒ 擋請求；shadow ⇒ 放行記 degraded）；audit 只記 entity **類別與計數，永不記原值**。

---

## 4.1 Authoring dry-run（2026-07-17 新增，PRD-241 AC-17 / SPEC-219 §5.5）

Create Policy / Create Version dialog 的 entity selector 下方有 **Test masking** 卡
（`GuardrailDryRunTester`，在 `policy-content-form.tsx`）：輸入樣本文字（上限 2000 字）→
`POST /iam/guardrails/dry-run`（hook：`useGuardrailDryRun()`，`src/services/iam.ts`）→
顯示遮罩後輸出（token 高亮）+ 偵測到的 entity 雙語標籤。用的是**表單當下尚未存檔**的
entities/threshold；跟 runtime `/v1/guardrails/preview` 是兩個 surface——runtime 那條仍然
不吃 policy 覆寫（AC-16 不變）。錯誤處理：sidecar 未部署/不可達 → 503
`GUARDRAIL_DETECTOR_UNAVAILABLE`，卡片顯示紅色 Alert；unknown entity / threshold 超界 /
超長 → 400。後端：`xparse_iam/api/ninja_api/_guardrail_dry_run.py`。

## 5. 待做／可做的 UI（本文件的 open items）

- bundle/binding 流程對 guardrail kind 的引導（目前是通用 versioned-policy UI，可加「建完 policy 順手綁定」的 wizard）。
- effective-policy 預覽視圖顯示 folded `pii.entities`（`useEffectivePolicy` 已有資料，缺專屬渲染）。
- shadow 模式的觀測面（audit 端 `would_mask` 事件）尚無 dashboard 卡片。
- 驗收參考：PRD-241 §4 AC-1..15（xparse repo `docs/prd/PRD-241-guardrail-v1-pii-only.md`）。
