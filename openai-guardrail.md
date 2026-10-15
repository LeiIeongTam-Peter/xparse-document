# OpenAI Guardrail Engine — 功能說明、完整工作流、檔案地圖、後續與待修

| Field | Value |
|---|---|
| Date | 2026-08-03（**Rev.2 — 本文取代上一版**：上一版記的是隨 #3044 revert 掉的第一版實作） |
| Branch | `feat/openai-moderation-guardrail-engine-v2` + `fix/3045-name-keyed-fallback-same-name-raise` |
| PR | [#3062](https://github.com/futurenestit/xparse/pull/3062)（主線，merge=`798a5e884`）+ [#3063](https://github.com/futurenestit/xparse/pull/3063)（#3045 修正，merge=`46c774601`） |
| 狀態 | **兩個 PR 已 merge 進 main**（`merge-base --is-ancestor` 驗證過）；probe P1/P2/P3/P4 對真元件全綠（本版程式碼）；**prod 未部署** |
| 設計閉環 | PRD-271 Rev.2 · ADR-356 Rev.2 · SPEC-223 C-223-13a + C-223-28..40 · RESEARCH addendum Rev.2 |
| 權威知識庫 | `docs/plans/openai-guardrail-engine-rebuild-plan.md`（決策 D1–D5 的完整前因後果） |

---

## 1. 這個功能是什麼

**一句話**：租戶建 guardrail policy 時，可以在「Xparse 自架引擎」之外選「OpenAI 引擎」——content filter 改由 OpenAI 專訓的 `omni-moderation-latest` 分類器判斷（免費、零 token），on-topic 改用 OpenAI Guardrails 的離題檢查問法（MIT 移植樣板，判官仍是租戶自己指定的模型）。

**白話版（可以直接講給客戶聽）**：

- 現在的內容過濾是「拿一顆通用 AI 當裁判」；這次多給一個選擇——**用 OpenAI 專門訓練來做內容審查的分類器**，用起來免費，客戶只要有自己的 OpenAI 金鑰。
- **不是換掉，是可以並用**：公司層綁自家引擎、部門加一道 OpenAI，兩道都跑、任一道踩線就擋。下層只能加防線、拆不掉上層的。
- **金鑰是明著指名的**：建 policy 時直接挑一把你建好的 OpenAI credential（可以是專門給 guardrail 用的），旁邊有「Test」按鈕當場驗證打不打得通。之後有人換掉任何 model 的金鑰，guardrail 用的還是你指名的那把。
- **強度分級（low/medium/high）在 OpenAI 這條路上不生效**——它只回答有沒有踩線。我們不偽造分級：介面直接變灰並寫原因，稽核也標明。
- **PII 遮罩永遠走自架偵測器**，原文不外流，不受引擎選擇影響。
- 誠實界線：**不宣稱 OpenAI 引擎更安全**（on-topic 那條是同一類 LLM 判官機制，弱點是機制級的）；免費 ≠ 無限（受 OpenAI 帳號 tier 的 RPM 限制，enforce 下 429 會 fail-closed 擋請求）。

**三層語意（核心設計，不衝突）**：

| 層 | 規則 | 條款 |
|---|---|---|
| authoring（一份 policy version） | 恰好一個 evaluator，UI 單選、API 400 | C-223-39 |
| fold（跨 scope/binding） | `engines` set-union——子層可加、永遠移不掉祖先的 | C-223-31 |
| runtime（一次請求） | 所有 arm 並行；任一 block ⇒ block；`unavailable` 永不當 pass | C-223-32 |

**與被 revert 的第一版三個關鍵不同**：

1. **D2-B 憑證指名投影**：policy 存的是 credential **名字**（`moderation_credential_ref`，租戶內 unique、GitOps 可攜），IAM 在 validate 時走 ADR-310 授權邊驗證後只投影**恰好一把**給 gateway；gateway 零挑選，「沒指名／不存在／無權使用」三態訊息可區分。model 完全退出憑證路徑（ADR-358 後 model-name anchor 結構性不可行）。
2. **D1 樣板真的接上了**：OpenAI off-topic 樣板以 MIT 授權移植且 `template` 參數**真的**接進 `build_topic_prompt`——第一版「選了不會怎樣」的 runtime-inert 缺陷，這次有「兩樣板必不同」的紅燈測試守著。不做 `confidence_threshold`（verdict 維持二元）。
3. **audit 欄位一次宣告齊**：revert 曾把 `3e688e378` 的欄位宣告掃掉（silent-drop 復活）；這次 10+ 個 classifier 欄位全部宣告 + allowlist，判官 uuid 用 `classifier_model_uuid`（不撞 ADR-358 的主推論 `model_uuid` 維度）。

---

## 2. 完整工作流

### 2.1 使用者授權流（Console 六步）

| Step | 位置 | 動作 |
|---|---|---|
| 1 | `AI Gateway` → `Credentials` | **Add Credential**，Provider=`openai`，貼 `sk-...`（可建一把專用的，例如叫 `openai-guardrail`——不必掛在任何 model 上） |
| 2 | `AI Gateway` → `Policies` → **New Policy** → Kind=Guardrail | Protection 區塊：**Engine 單選** `Xparse (self-hosted)` / `OpenAI` |
| 3 | 選 OpenAI 後 | **OpenAI Credential combobox** 列出候選（可搜尋、可自由輸入名字）→ 旁邊 **Test** 按鈕打真 `/v1/moderations` 驗證（成功 = 200 + 13 類別鍵齊全；失敗分四類：401 憑證無效 / 403 權限不足 / 類別鍵漂移 / 網路不通） |
| 4 | 同一表單 | Content Filter 開、勾類別；Mode 留 `Shadow`；threshold 在 OpenAI 下自動 disabled + 顯示原因 |
| 5 | `Policies` → `Sets` → **New Set** → Add Policy → 綁到 Application（policy 一律經 set 綁 app） | 綁定後生效 |
| 6 | `Cockpit` → `Audit` | 查 `classifier_engine: "openai_moderation"` 的 per-arm 記錄 |

### 2.2 Runtime 請求流（enforce、input、兩引擎並用時）

```
Client → Gateway 認證
  └─ IAM gateway-validate：
       ① 折疊 guardrail policy（engines union、credential_ref ancestor-pin）
       ② 讀折疊後的 moderation_credential_ref
       ③ ADR-310 entitlement 檢查（access_scope=tenant 或 GroupCredentialGrant）
       ④ 通過 → 投影恰好一把 resolved_moderation_credential（含解密後 key）
          不通過 → 投影 status=not_named / not_found / not_entitled
  └─ PII 遮罩（pre-routing，自架 GLiNER，不受引擎選擇影響）
  └─ routing → policy kernel → classifier stage：
       on_topic        → 一次 bounded LLM call（判官=classifier.model，
                          問法=folded template：xparse 或 openai_offtopic）
       content_filter  → asyncio.gather(
            llm_classifier:    build_content_prompt → 租戶自己的判官 LLM
            openai_moderation: POST api.openai.com/v1/moderations
                               （key = IAM 投影的那把；gateway 不做任何挑選）
         )
         verdict = 任一 arm block ⇒ block ∣ 全 pass ⇒ pass ∣ 其餘 unavailable
         unavailable 永不當 pass → 走 on_failure（closed ⇒ enforce 擋下）
  └─ pass → admission → generation
     trip → SPEC-213 graceful refusal（HTTP 200 + finish_reason=content_filter）
     shadow → 永不擋，audit 記 would-block
  └─ Audit：每個 arm 一筆（engine / verdict / latency / threshold_honored /
     credential_ref+uuid / 序列化 categories+scores / classifier_model_uuid）
```

### 2.3 部署流（prod 要上時照這個）

- **上線順序強制：gateway 先、IAM 後**——反向時舊 gateway 會容忍地忽略新 evaluator 鍵、靜默降級成只跑內建判官（C-223-38 fail-open）。
- 部署 delta：無新容器、無 migration、無新 pip 依賴、無新密鑰儲存。prod 三個 image 都要 rebuild（gateway + IAM + console）。
- Egress 檢查（目標環境 gateway 容器內）：`curl -s -o /dev/null -w '%{http_code}' https://api.openai.com/v1/moderations` → 401/404 = 通；000/逾時 = SG/Squid 沒開。
- 環境變數（選填）：`XPARSE_MODERATION_TIMEOUT_MS`，預設 3000。
- enforce 翻轉照 ADR-318 §7.3：≥1 週 shadow 流量 + 人工抽查 would-block，**moderation 免費不是跳過覆核的理由**。

---

## 3. 檔案地圖（兩個 PR 全部觸及路徑）

### 3.1 設計文件（PR #3062）

| 路徑 | 內容 |
|---|---|
| `docs/prd/PRD-271-tenant-selectable-external-content-classifier.md` | 需求 Rev.2：白話層、§4 驗收（A1-13/U1-10/I1-9/N1-11）、§0 Rev.2 變更紀錄 |
| `docs/adr/ADR-356-openai-moderation-content-filter-peer-engine.md` | 架構 Rev.2：D2-B 投影、Alternatives J/K、INV-356-1..13、**§7.3 本版 probe transcript** |
| `docs/specs/SPEC-223-guardrail-v2-contract.md` | C-223-13a 三 fold 方向 + C-223-28..40（34=指名投影、36=移植樣板、40=connection test、21=後半句降級 #3046） |
| `docs/research/RESEARCH-openai-moderation-engine-entry-addendum-2026-07-31.md` | 證據包 Rev.2（§3.7 兩處過時事實修正：PII check 已 Presidio 本地化、內建 check 現為 9 個；§3.8 MIT 授權定案） |
| `docs/research/openai-guardrails/off-topic-template-port.md` | 樣板移植紀錄（比照 NeMo 先例） |
| `docs/adr/core/Core-ADR-{01,02,04,06}.md` · `docs/prd/core/Core-PRD-{02,05}.md` | §17.4 Core 回寫 |
| `docs/adr/ADR_INDEX.md` · `docs/prd/PRD_INDEX.md` · `docs/prd/GUARDRAIL-FAMILY-INDEX.md` | 註冊 |
| `docs/research/研究智庫-HUB.md` | 來源登錄 + backlog |
| `xparse-wiki/wiki/concepts/openai-moderation-peer-engine.md` | wiki 概念頁 |
| `docs/plans/openai-guardrail-engine-rebuild-plan.md` | （untracked，June 保存）決策知識庫 |

### 3.2 Contract 層（`xparse_guardrail/`）

| 路徑 | 內容 |
|---|---|
| `contract/openai_moderation/mapping.py` | 5→13 類別對映表、`UNCOVERED_PROVIDER_CATEGORIES`（harassment 系列明列不涵蓋）、`MODERATION_MODEL/PATH` |
| `contract/openai_moderation/parser.py` | `parse_moderation_response`：**刻意忽略頂層 `flagged`**、**缺請求鍵 raise 不當 False**（兩個載重決策各有反向測試） |
| `contract/openai_moderation/__init__.py` | 公開介面 |
| `contract/capabilities.py` | `openai_moderation` descriptor（CONTENT_SAFETY `profile_fields` **不含** `content_threshold` = inert 訊號）、`classifier_evaluator_enabled` 軸、`classifier_evaluator_engine_ids()`、`validate_content_filter_engines()`、`honors_content_threshold()`、`MAX_CONTENT_FILTER_ENGINES=2` |
| `contract/llm_classifier/prompt_templates.py` | `build_topic_prompt(..., template=)` + **移植的 openai_offtopic 樣板**（檔頭 MIT attribution 全文） |

### 3.3 IAM 層（`xparse_iam/xparse_iam/`，無 migration）

| 路徑 | 內容 |
|---|---|
| `policies/schema.py` | `GuardrailContentEngineLiteral` / `GuardrailTopicTemplateLiteral`；`content_filter.engines`（1..2）、`moderation_credential_ref`、`on_topic.template` |
| `authorization/guardrail_policy_merge.py` | engines union（identity `[]`）、template + credential_ref ancestor-pin、clamps override notices |
| `authorization/guardrail_resolver.py` | 四個 placement 欄的 same-scope 衝突斷言、折疊後 evaluator set 能力重驗 |
| `application/use_cases/policy/validate_policy_content.py` | C-223-39 單一 evaluator、enabled+空集合拒絕 |
| `api/ninja_api/_versioned_policies.py` | `_assert_moderation_credential_exists`（N7：指名不存在的 credential → 授權時 400） |
| `core/auth_engine.py` | `_resolve_moderation_credential_projection`：折疊 ref → ADR-310 entitlement → 投影單把（**永不投影目錄**） |
| `api/ninja_api/_internal.py` | gateway-validate 對投影解密成 `resolved_api_key` + 剝密文（比照 model entries） |
| `api/ninja_api/_helpers.py` | `_probe_openai_moderation`（固定良性字串、斷言 13 鍵、四類失敗分類） |
| `api/ninja_api/_providers.py` | `POST /iam/provider-credentials/{uuid}/test-moderation`（共用 preamble 抽成 `_load_and_decrypt_credential_for_test`） |
| `api/schemas/_core.py` + `api/schemas/__init__.py` | `TestModerationCredentialResponse`（含 `failure_class`） |

### 3.4 Gateway + Audit 層（`bustream/`）

| 路徑 | 內容 |
|---|---|
| `gateway/classifier_handler.py` | content_filter 多臂扇出（gather）、`ClassifierCheckResult` 三態 verdict + credential 欄、`_resolved_moderation_credential`（消費投影、三態訊息）、`_call_openai_moderation`、`_run_moderation_arm`、`_run_content_filter_check`、**template 接進 `_run_topic_check`**、per-arm audit emit、`XPARSE_MODERATION_TIMEOUT_MS` |
| `gateway/cache_handler.py` | `_classifier_cache_variant` 加 engines/template/credential_ref（拿掉任一就紅的測試守著） |
| `gateway/guardrail_policy_adapter.py` | 容忍解析新鍵（缺鍵 = 今日行為，C-223-38） |
| `gateway/iam_http_client.py` | `HttpModerationCredentialData` 載體 + `HttpGuardrailClassifierData` 新欄 + parser |
| `audit/schema.py` | 宣告全部 classifier 欄位（engine/threshold_honored/unavailable_reason/model/**model_uuid**/tokens×2/credential_ref/credential_uuid/categories/scores） |
| `audit/xparse_bridge.py` | 同組欄位進 `PAYLOAD_ALLOWLIST` |
| `production/key_resolver.py`（**PR #3063**） | name-keyed fallback 同名 >1 ⇒ hard fail 點名全部 `model_uuid/credential_uuid` 對 |

### 3.5 Console（`frontend/console-app-refactor/src/`）

| 路徑 | 內容 |
|---|---|
| `app/(main)/(ai-gateway)/policies/_components/policy/policy-content-form.tsx` | **主改動**：真 Engine 單選（拆掉假 `Nemo\|OpenAI` 下拉）、`ModerationCredentialField`（combobox + Test 按鈕 + 空候選警告）、有出路 gating 文案、threshold disabled-with-reason、on-topic 誠實文案（「檢查定義來自 OpenAI，判官是你指定的模型」） |
| `app/(main)/(ai-gateway)/policies/_components/policy/policy-version-describe.ts` | Filter evaluators / Topic wording / Moderation credential 顯示列；移除死的 nemo/openai label |
| `types/iam.ts` | `GuardrailContentEngineId` / `GuardrailTopicTemplateId` / `moderation_credential_ref` / `ModerationTestResponse` |
| `services/iam.ts` | `useTestModerationCredential` |

### 3.6 測試與工具

| 路徑 | 內容 |
|---|---|
| `xparse_guardrail/tests/contract/test_openai_moderation.py` | mapping/parser 契約（含反向測試） |
| `xparse_guardrail/tests/contract/test_capabilities.py` | evaluator set 驗證 + 前後端 literal anti-drift |
| `xparse_guardrail/tests/llm_classifier/test_prompts_and_parser.py` | 樣板測試（**兩樣板必不同**、未知 template raise、預設 byte-identical） |
| `xparse_iam/tests/unit/test_guardrail_policy_merge_v2.py` | union/pin/clamps/預設值 fold 契約（39 tests） |
| `tests/unit/test_classifier_handler.py` | 扇出合成 + **投影三態可區分**測試 |
| `tests/unit/test_gateway_cache_handler.py` | 指紋隔離（含 credential_ref 旋轉） |
| `tests/unit/test_classifier_audit_fields_survive_bridge.py` | 真 AuditRecord+XparseBridge 落盤（反向斷言升級為 ValidationError fail-loud） |
| `tests/unit/test_key_resolver.py`（PR #3063） | 同名 fail-closed + 單名照常 + uuid 路徑不受影響 |
| `scripts/probe_openai_moderation.py` | §8.1 probe（修掉「有效 key 使 P2 必敗」缺陷；P2 用自己的壞 key） |

---

## 4. 接下來要做什麼（What's next）

1. **Prod 部署**（本輪完成線刻意不含）：rebuild gateway+IAM+console 三個 image → **gateway 先上、IAM 後上** → 目標環境 egress 檢查 → E2E 冒煙。走 `/deploy-ec2`。
2. **[#3046](https://github.com/futurenestit/xparse/issues/3046) — guardrail token 成本進 cost rollup**（C-223-21 後半句，D4 層 2）：跨 `3rd/xparse_audit` submodule，要 stacked PR + parent pointer bump。**gateway 端前置已備齊**（`classifier_model_uuid` / tokens / provenance 全部 top-level），rollup source 讀鍵即可，不用再回頭改 gateway。
3. **Shadow → enforce 營運節奏**：讓真流量在 shadow 跑起來，累積 would-block 報表（per-arm 歸因已可 GROUP BY），觀察 429 出現率（見 §5-5），再依 ADR-318 §7.3 per-tenant 翻 enforce。
4. **`not_entitled` 的 IAM 產生側驗證**（ADR-356 §7.3 明列的 residue）：gateway 消費側已由 probe 驗過，IAM 產生側需要一把 `access_scope=department` 且無 grant 的 credential 情境——共用 dev credential 上不宜翻 flag，找乾淨情境補一次或寫 IAM 單元測試。
5. **產品面候選（要就開獨立 PRD）**：content category 分類法擴充（我方 5 類 vs 供應商 13 類的 `harassment` 缺口；順帶檢視 `illicit` ⊇ `illegal_activity` 的未校準近似）；threshold 的 EMULATED 路線（阻擋因素是**校準語料**不是 API）；PRD-200 其餘部分（per-tenant engine registry / BYO endpoint / conditional 選擇）。
6. **銷售/導入話術**：租戶自己的 OpenAI 帳號 tier（RPM）在 enforce+closed 下會影響 Xparse 請求成功率——這是刻意的 fail-closed，但要先講。

---

## 5. 待修 / 已知缺口（What bugs to fix）

### 高（有 tracking）

1. **#3046 — `llm_classifier` 的 token 花費扣了配額但不進任何成本報表**。pre-existing 缺口（與本功能正交）：quota_counter 有扣、cost rollup 只掃 `audit.execution.completed` 看不到 guardrail 事件。部門主管看得到預算被扣、看不到花在哪。SPEC 已誠實降級為 tracked gap，**修它 = 開工 #3046**（audit submodule 的 rollup source 讀 `classifier_*` 鍵）。

### 中

2. **`classifier_degraded` / `classifier_degraded_allowed` 沒宣告成 AuditRecord 欄位**——E2E 時 gateway log 有警告：`Non-schema audit key 'classifier_degraded' folded into 'extra'`。目前落在 `payload.extra`（primitive，不會丟，但不能直接 GROUP BY）。是 pre-existing 的 emit（非本輪新增），但既然這輪把其他欄位都提上 top-level，這兩個補宣告 + allowlist 是幾行的事——**下個碰 audit 的 PR 順手修**。
3. **`not_entitled` 產生側未對真 IAM 驗**（見 §4-4）。消費側訊息已驗可區分，風險低，但 §8.1 紀律上是張工作單。
4. **SPEC-223 C-223-9 vs ADR-318 §3.1 的既有矛盾**（v2 snapshot 打到 pre-V2 gateway 是 fails-loudly 還是 silently-degrades；實際行為 = 後者）。改動前就存在，屬 ADR-318 owner 的決定——只回報不動手。

### 低 / 觀察項

5. **429 刻意未涵蓋**：無法隨需觸發，模擬只測到模擬本身。走的是 P2 已證實的非-2xx 分支；等 shadow 期真實 audit 記錄觀察到再關。
6. **dev 資料殘留**（無害，記錄在案）：`test` app（a0607 group）的 gpt-4o model 已改指 `openai-guardrail` credential（原 credential 本來就失效——算修好）；`qqwwwww` app 留一顆綁定的 `dup-probe-4o`（#3045 dogfood 殘留；平台 last-model guard 擋移除，app 是 on_prem 路由不到 cloud，inert）。另一顆解綁的 `dup-probe-4o` model row 因 membership 稽核史（#3059 守衛）不可刪。
7. **前端 3 個既有紅測試**（`audit-event.test.ts` ×2、`cost-token-trend-card.test.ts` ×1）與本功能無關；本機 Python 也有 ~90 個既有失敗（`audit_tests` 的 7 個已用 stash baseline 驗證非本輪造成）。
8. **判官 model 的 `YAML_FALLBACK_USED` log**（INV-318-12 既有行為）：dev 的判官呼叫因 model 無 DB endpoint 走 YAML profile registry——正常 fallback，非 bug，觀察即可。
9. **legacy `ApplicationModel` dual-read 的同名守衛**：歸 ADR-358 INV-358-3 既有追蹤（刻意不塞進 #3045），#3045 只修了 name-keyed fallback 那一條。

---

## 6. 驗證證據（本版程式碼，全部真元件）

| 項 | 結果 |
|---|---|
| P1 回應形狀 | **PASS** — 13 類別鍵對真 API 逐字相符；真 parser 接受真 body |
| P2 失敗轉譯 | **PASS 7/7** — 五種 fail-closed 訊息可區分 + 真 401 + 真 192.0.2.1 逾時；無例外逃出 |
| P3 D2-B 投影 | **PASS** — 真 IAM 投影 `resolved`（material 解密、密文剝除）與 `not_named`；`not_found` 授權時 400；C-223-39 雙引擎 400 |
| P4 union 活性 | **PASS** — 同一請求：`openai_moderation → block`（violence、0 token）+ `llm_classifier → pass`（159 token）；shadow 200 完成 + would-block 落 audit；跨 binding union 真實觀測到 |
| T6 connection test | **PASS** — 對真 credential：「13 expected category keys present」（1030ms）；也 dogfood 了三把 credential 的 401 分類 |
| AC-13 | audit 不做 JSONB extract 答得出「用了哪把 credential」（top-level `classifier_credential_ref`） |
| 測試 | Python 256 + fold 39 + key_resolver 11 綠；`tsc --noEmit` clean；form suite 41/41；兩個 PR CI 零紅 |
| probe 資料 | 用完即清（binding deactivate——絕不 invalidate——bundle inactive、policy tombstone、key revoke） |

> 附註：dev DB 的 `openai-guardrail` credential（admin tenant）存有**有效的真 OpenAI key**，P1/P4/E2E 都靠它跑完——下次要重跑 probe 或 E2E 不用另外準備 key。

---

## 7. 一頁速查

```
選擇引擎     Policies → New Policy → Protection → Engine 單選（Xparse | OpenAI）
             一份 version 一個引擎；跨 binding 折疊後可兩個都跑、任一擋就擋

憑證         Credentials 建 openai key（可專用、不必掛 model）
             → policy 裡 combobox 指名它 → 旁邊 Test 按鈕當場驗
             runtime 由 IAM 驗授權後投影單把給 gateway（gateway 零挑選）

本地驗證     docker restart xparse-gateway xparse-iam（live mount 即載入；無 migration）
             probe: PYTHONPATH=".:xparse_iam" python3 scripts/probe_openai_moderation.py \
                    --failures-only        ← P2 不用 key
                    --api-key sk-...       ← P1+P2+P4

Production   rebuild gateway+IAM+console；gateway 先上、IAM 後上（強制）
             egress: curl api.openai.com/v1/moderations（401/404=通）
             XPARSE_MODERATION_TIMEOUT_MS 選填（預設 3000）

audit 查詢   classifier_engine / guardrail_verdict / classifier_threshold_honored /
             classifier_credential_ref / classifier_model_uuid /
             classifier_provider_categories(_scores 序列化字串)  ← 全部 top-level

成本         moderation 臂：0 token、免費、受帳號 tier RPM（429 → unavailable → closed 擋）
             on-topic 判官臂：仍燒租戶自己的 token（成本報表缺口 = #3046）

enforce      預設 shadow；翻轉需 ≥1 週 shadow 流量 + would-block 人工抽查（ADR-318 §7.3）
```
