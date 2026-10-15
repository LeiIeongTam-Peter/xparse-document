# NemoGuard 自架判定源 — 交接文件（設計＋實作皆已交付，等 GPU 端點）

**目的**：給接手的 agent 或工程師一份能**獨立接續工作**的參考文件。
**最後更新**：2026-08-07（第三次更新：實作交付完成 + 完整交接）
**狀態**：設計閉環 ✅、**WP1–WP6 前後端實作 ✅ 全數落 main（7 個 PR：#3302–#3306、#3308、#3309）**，交付停在 **Phase 2**（授權開放、預設 shadow、enforce 不動）。**probe P1–P5 未執行（無 GPU 端點）**——Phase 3 enforce 與任何「verified」宣稱仍 gated 於 probe transcript。
**Canonical source**：本文是導覽層。權威內容以 repo 內的 PRD/ADR/SPEC 為準（路徑見 §6）；衝突時以 repo 為準。

---

## 1. 這個功能是什麼（一段話）

讓客戶可以**把 guardrail 的判定模型裝在自己的機房裡**。用 NVIDIA 訓練好的兩顆 NemoGuard LoRA 分類器——一顆判內容安全（`content_safety`）、一顆判主題（`topic_control`）——掛在客戶自架的 vLLM 端點上。受檢文字**從頭到尾不離開客戶的信任邊界**。

### 1.1 動機與紅線

| # | 動機 | 證據強度 |
|---|---|---|
| ① | 標案／客戶指名 NVIDIA 技術棧 | 商務事實 |
| ② | **自架、資料不出邊界**（含繁中市場脈絡） | **強**——對 OpenAI 路徑的真差異 |
| ③ | turnkey 主題控制（專用模型 vs 通用判官） | **強**——廠商 model card 有契約支持 |
| ~~④~~ | ~~中文判準更好~~ | **❌ REFUTED，禁止復活** |

> **紅線（non-negotiable）**：不得宣稱本判定源對中文（或任何語言）判得更準。Aegis 2.0 論文明文 *"the dataset primarily focuses on English-language data"*。任何文件／UI／標案文案都不得復活此宣稱。**Console 已有 banned-words 測試守著**（`policy-content-form.test.ts` 的 red-line 測試）。

---

## 2. 拍板決策（實作時遇分岔先查這裡）

### 2.1 設計期拍板（D-1..D-10，出處 `docs/plans/nemo-guardrail.md`）

| # | 決策 |
|---|---|
| D-2 | 兩條 rail（content_filter + on_topic）一起做 |
| D-3 | 類別分類法 per-engine 命名空間 |
| D-4 | 端點錨點 = `ProviderCredential.endpoint`；policy 指名 credential **name** |
| D-5 | GPU **客戶自架 per-tenant**；平台不代管、不代付、不共用 |
| D-6 | `honors_content_threshold=False`（誠實留白，不模擬分級） |
| D-7 | Console Engine 單選擴為三態（Xparse / OpenAI / NVIDIA） |
| D-8 | 遮罩前原文只給**不出信任邊界**的來源（capability 宣告驅動） |
| D-9 | 續走 v2 世代（重開條件寫在 ADR-375 §2.2.1） |

### 2.2 實作期拍板（2026-08-07，本輪新增）

| 決策 | 內容 |
|---|---|
| build-first | 無端點先建造：probe 只擋「驗證與 enforce」，不擋建造（§4.2 盤點經執行證實） |
| 交付停點 | **Phase 2**（authoring 開放）；Phase 3 enforce 完全不動 |
| `MAX_CONTENT_FILTER_ENGINES` | **抬到 3**（同步抬 schema `engines max_length` 這個**第二個獨立 cap**） |
| 未授權類別命中 | **進 audit**：`classifier_unauthorized_category_hits`，明標 non-enforcing observation（永不參與判決，INV-375-10） |
| PRD-263 正交性 | **已驗正交**：`level` 管 binding 可及範圍（fold 之前的鏈組成）；`engines` 是 fold 內容運算子且 set-union 可交換 |
| 端點形狀 | 未定（使用者「還沒想」）；**碼一律照 vLLM OpenAI 相容契約寫**；若日後要走 NIM 須先修 ADR-375 INV-375-13（NVAIE 付費 + 48GB） |
| wire 識別字（已定版，別再發明） | engine ids：`nemoguard_content_safety` / `nemoguard_topic_control`（**各屬一條 rail 的 literal，成員不互通**）；provider_code：`nemoguard`；served models：`content_safety` / `topic_control`；投影鍵：`resolved_judgement_credential`（帶 `judgement_url`）；Console authoring 值：`nvidia` |

### 2.3 三個最容易做錯的地方（仍然成立，讀完再動手）

**(a) Console 的 Engine 耦合不可假設**（C-223-39/43a）：兩條 rail 的 evaluator 欄位是獨立契約欄位、fold 方向不同；單選只是 authoring 簡化。要的保證是**逐條 rail 的誠實性**：來源不可用走 `on_failure`，**不得用內建 LLM judge 頂替**。

**(b) 同一個 check 內 fold 方向相反是刻意的**：`on_topic.template` = ancestor-pin（問法）；`on_topic.engines` = set-union（獨立評估者）。方向跟著「東西的種類」走。

**(c) dispatch 陷阱已修除但別復發**：兩條 rail 都是 explicit match，未知 engine fail-closed 帶 `classifier_unknown_engine`（`guardrail_response.block_error_code` 有顯式對映，否則會被預設誤呈現成 content block）。anti-drift 靠 dispatchability 測試鎖（每個 declared evaluator id 必須到得了一條 arm），**已 dogfood**（seed 假第四成員看它變紅）。加第四個 evaluator 時：literal + capability flag + dispatch branch 三處同 PR。

---

## 3. 已完成（全部落 main）

### 3.1 設計閉環（2026-08-07 上午，PR #3299）

| 產出 | 路徑 |
|---|---|
| PRD-279（what & why + 驗收 A1-A14/U1-U8/I1-I8/N1-N12） | `xparse/docs/prd/PRD-279-nemoguard-self-hosted-judgement-source.md` |
| ADR-375（how + INV-375-1..14 + 部署硬約束） | `xparse/docs/adr/ADR-375-nemoguard-self-hosted-judgement-source.md` |
| SPEC-223 amend（C-223-42..48） | `xparse/docs/specs/SPEC-223-guardrail-v2-contract.md` |
| 外部證據包（動機④證偽、NVAIE/48GB、Llama 標示義務、21≠23） | `xparse/docs/research/RESEARCH-nemoguard-lora-judgement-source-evidence-2026-08-07.md` |
| 拍板紀錄 D-1..D-10 | `xparse/docs/plans/nemo-guardrail.md` |
| §8.1 probe harness（603 行，未執行） | `xparse/scripts/probe_nemoguard.py` |

### 3.2 實作（2026-08-07 下午，6 個線性 PR + 1 個收尾，逐個 merge + merge-base 驗收）

| PR | 層 | 內容 | 規模 |
|---|---|---|---|
| **#3302** | contract | `contract/nemoguard/`（mapping：5→9 碼保守對映、S13/S14 排除、S11/S17 留 uncovered；prompts：完整 taxonomy 樣板 + topic messages builder；parser：**兩套不同構**，unsafe-無類別/任何不可讀 ⇒ raise 絕不 pass，模型自身 verdict 永不決定判決）；capabilities 三新欄位（`topic_evaluator_enabled`／`judgement_within_trust_boundary`／`content_categories`）+ `validate_on_topic_engines` + INV-375-11（無來源可 honor 的類別 400） | +1446/-22 |
| **#3303** | IAM | **migration 0243**（`ProviderCredential.endpoint` AddField + seed `nemoguard` ProviderDefinition，`url_pattern={endpoint}/v1/chat/completions`）；schema 兩 literal + `on_topic.engines` + `judgement_credential_ref`（第五 placement 欄位）+ max_length 2→3；fold（topic union + 第五欄 ancestor-pin）+ resolver re-assert + same-scope conflict；`_resolve_judgement_credential_projection`（四態 + **`no_endpoint` 第五態**、帶 validate-time 組好的 `judgement_url`）；HTTP 邊界共用解密 helper；**phase guard**（Phase 1 語意，#3308 撤除） | +1068/-83 |
| **#3304** | gateway | dispatch 改 explicit match + fail-closed；`_run_topic_check` 多臂 fan-out（共用 `_gather_arm_results` 組合器）；`nemoguard_arms.py` 兩條臂（零 token、憑證歸因）；**`XPARSE_JUDGEMENT_EGRESS_ALLOWLIST` default-deny**（共用 matcher `judgement_egress.py`，不套禁 RFC1918 通用規則）；pre-mask 供文（chat.py 在 PII rail 前快照原文，只給 capability 宣告在邊界內的 evaluator）；cache variant 加 `on_topic_engines`/`judgement_credential_ref` 兩鍵；wire：`HttpJudgementCredentialData` | +1440/-91 |
| **#3305** | audit | `classifier_unauthorized_category_hits` + `classifier_pre_mask_input`（schema 宣告 + `PAYLOAD_ALLOWLIST` + emit 三處同動）；**blocked/degraded 事件補 engine 歸因**（`ClassifierUnavailableError.engine_id` 由 fan-out 蓋章；GUARDRAIL_BLOCKED 只列實際擋下的 arm）——三臂後不可再靠排除法推斷 | +226/-7 |
| **#3306** | IAM | `POST /iam/provider-credentials/{uuid}/test-judgement`（C-223-48）：**雙 adapter 各測**（單 adapter 部署在授權時就現形，N11）、每顆需 2xx **且** parser 過、五類 failure_class（`egress_denied`/`network_unreachable`/`rejected_credential`/`provider_error`/`unparseable_verdict`）、probe 字串固定常數、不落盤。**2026-09-18 起 `success` 只由 content-safety 決定**（C-223-48 Rev.2 / PR #5074）——單顆部署不再恆紅，缺口改由 `topic_control_ok` + `provider_info` 承載 | +517/-0 |
| **#3308** | flip | 撤 phase guard → 真閘門（topic source-cardinality 恰一 + capability 閘）；credential API 收/驗/回 `endpoint`（http/https + host，格式而非可達性）；**Console**：Engine 三態、judgement 憑證 combobox（只列帶 endpoint 的 active nemoguard 憑證、顯示端點、test 按鈕、U7 出路文案）、threshold 灰化+原因、讀取端反推改 **data-driven**（混 rail 折疊快照拒載，N12）、U4 資料落地文案、**紅線 banned-words 測試**、i18n en+zh-TW 四 gate 全綠 | +568/-116 |
| **#3309** | docs | Core 回寫（ADR-02/PRD-02 主列 + 01/03/04/05/06/10 引用列）、ADR-375/PRD-279 status 更新、plans 收案紀錄、wiki 同步 | 文檔 |

**測試證據**：guardrail 套件 194 綠（本機）、gateway 影響面 369 綠（本機）、IAM 126 綠（prod-image ephemeral 容器 + migration 0243 對 fresh DB 乾淨 + `makemigrations --check` 無 drift）、前端 vitest 388 綠 + tsc/eslint/i18n 四 gate 綠。每個 PR 過 CI 才 merge。**dispatch anti-drift gate 已 dogfood**（seeded 假第四成員 → 測試變紅 → 撤除）。

### 3.3 工程記憶（repo 外，`~/.claude/projects/-Users-peter-Desktop-X-parse-xparse/memory/`）

- `project_adr375_nemoguard_implementation_delivered.md`（**本輪新增**：wire 識別字定版、部署開關、接手指引）
- `reference_guardrail_engine_coupling_not_assumable.md` / `project_nemoguard_v2_english_only.md` / `reference_recover_deleted_engine_config_from_git.md`

---

## 4. 之後要做什麼（依序）

### 4.0 唯一的硬阻擋：GPU 端點（人類要提供的東西）

一台跑 vLLM + 兩顆 LoRA adapter 的機器（~16GB VRAM 起，已驗 2× RTX 4000 Ada 20GB；HF token，base 是 gated）：

```bash
# 在既有 install_service/scripts/deploy-nemoguard-judge.sh 基礎上加第二顆 adapter
--enable-lora
--lora-modules content_safety=nvidia/llama-3.1-nemoguard-8b-content-safety \
               topic_control=nvidia/llama-3.1-nemoguard-8b-topic-control
--max-loras 2 --max-lora-rank 16      # 16 = 兩顆 rank 的最大值，不可調降
--tensor-parallel-size 2              # 不要開 --fully-sharded-loras
```

> ⚠️ **不得**改走 NVIDIA NIM 容器（INV-375-13：生產自架觸發付費 NVAIE + 需 48GB GPU）。vLLM+HF 權重是唯一合規路徑。

### 4.1 端點到位後的第一件事：跑 probe

```bash
cd /Users/peter/Desktop/X-parse/xparse
python3 scripts/probe_nemoguard.py --base-url http://<judge-host>:18000/v1
```

| Probe | 擋什麼 | 若結果不如預期 |
|---|---|---|
| P1 雙 adapter 共存 + `lm_head` 真生效 + 不互污染 | 部署形狀（D-2/D-7 地基） | 失敗 ⇒ 部署翻倍成兩台（ADR-375 Alternatives I），**只動部署文件與運維**，schema/Console/audit 不動 |
| P2 模型是否尊重 prompt 類別限縮 | WP2 介面認知 | 實作已按「不可信、一律事後過濾」寫；若反證只需縮 gateway 側，契約不動 |
| P3 繁中判準 + 延遲分位 | **Phase 3 enforce 的前置量測**（非行銷素材） | 誤判率不可接受 ⇒ 觸發 ADR-375 §2.2.1 世代重開條件 |
| P4 遮罩前後命中率差 | D-8 定量佐證（決策已拍板） | — |
| P5 topic-control 真實輸出格式 | **parser 的字面契約** | 格式不同 ⇒ 改 `contract/nemoguard/parser.py`（現在的行為是 fail-loud→unavailable，不會靜默錯判） |

**probe transcript 貼進 evidence pack 之前，任何東西不得宣稱 verified**（含 A5/A7 真失敗形狀、INV-375-3）。

### 4.2 部署級開關（端點上線時要設，忘了就是全擋）

| 開關 | 現值 | 要做的事 |
|---|---|---|
| `XPARSE_JUDGEMENT_EGRESS_ALLOWLIST` | 未設 = **全拒** | 把 judge host（`host` 或 `host:port`）加進 **gateway 與 IAM 兩個** process 的環境；容器要 **recreate**（env 改了 `docker restart` 不生效） |
| `XPARSE_JUDGEMENT_TIMEOUT_MS` | 預設 5000ms（**P3 量測前的猜測值**） | P3 跑完後依 p99 調整 |
| dev DB migration 0243 | dev 執行中容器尚未套用 | 重啟 xparse-iam（entrypoint 會 migrate）；記得 stale-module 陷阱：改 IAM 後必 `docker restart` |

### 4.3 補跑計畫內遺留的 E2E（建議與 probe 一起做）

Phase 2 的 dev 端到端驗證當時**刻意沒跑**：egress allowlist 是 gateway env，改它要 recreate 共用 dev stack 的容器，會干擾平行 session。流程：起假（或真）judgement server → `POST /iam/provider-credentials`（provider_code=`nemoguard`、帶 `endpoint`）→ Console 建三態 policy（Engine 選 NVIDIA）→ 綁 test app → 打 gateway 驗 shadow 判定 → audit 查 per-arm 歸因（`classifier_engine`/`classifier_pre_mask_input`/`classifier_unauthorized_category_hits`）→ cache 隔離（I7）→ 三態 fail-closed 可區分（A9）。可參考 memory `reference_guardrail_policy_binding_e2e_recipe`。

### 4.4 Phase 3（enforce gate）——本輪完全沒動，前置全在上面

shadow 先行 → P3 繁中誤判率量測 → per-tenant would-block 覆核（ADR-318 §7.3）→ **兩條 rail 節奏可不同步**（主題可先 enforce、內容維持 shadow）。歷史教訓：2026-06-03 單 judge 容量 fail-closed 噴 503 被改回 shadow；多來源 fail-closed ⇒ 可用度是乘積。

### 4.5 交付義務（非程式碼）

- **Meta Llama「Built with Llama」標示**：附 Agreement 副本 + 網站／UI／blog／about／產品文件**擇一**顯著標示 + Notice 檔。**目前任何一面都還沒放**。
- 客戶導入文件：可用度乘積（U5）、GPU 自備自維運（D-5）要明講。

---

## 5. 要修／要注意的事（接手 agent 的 known issues 清單）

| # | 事項 | 嚴重度 | 說明 |
|---|---|---|---|
| 1 | **PRD-279 N7 偏離**：「指名不存在的端點憑證 → 授權時 400」**未實作** | 中 | 刻意決定：`validate_policy_version_content` 是純函式（無 DB），且 entitlement 授權後會變，寫入時查存在性是假保證——runtime 三態 fail-closed（A9）+ 連線測試已覆蓋。**要嘛**在有 DB 的 version-create use case 補存在性檢查、**要嘛** amend PRD-279 N7 把「授權時 400」改為「runtime 可區分 fail-closed」。二選一，別放著 |
| 2 | `no_endpoint` 是 SPEC C-223-34 三態之外的**第四個投影態** | 低 | 程式碼與測試已定版；SPEC-223 C-223-47 下次 amend 時補一句把它列入規範（現在是 SPEC 落後於碼的微小 drift） |
| 3 | Console 讀取檢視（`policy-version-describe.ts`）**沒顯示** `on_topic.engines` 與 `judgement_credential_ref` | 低 | 編輯表單完整；唯讀 describe 檢視少這兩欄。純顯示補強 |
| 4 | `_evaluate_classifier` CC=D(23)、`compute_guardrail_clamps` CC=E(33) | 低 | **既有債**（baseline 29/33），本輪把前者 29→23、後者新增部分抽 helper 沒推高，但都仍超 CC<15 閘。獨立重構 PR 處理，別順手 |
| 5 | `moderation-credential-field.test.tsx` docstring 指向不存在的 `fae/moderation-credential-combobox-verify.ts` | 低 | 既有死引用（tripwire 成了唯一證據）。修 docstring 或補 fae 腳本 |
| 6 | `frontend/console-app-refactor/CLAUDE.md` 的 route group 表過時（寫 `(configuration)/policy`，實際 `(ai-gateway)/policies`） | 低 | repo 根 CLAUDE.md 已修過，前端那份沒跟上 |
| 7 | parser 契約是**轉錄非觀察** | 高（已知，非 bug） | `contract/nemoguard/` 的 JSON 形狀/label 詞彙/taxonomy 拼字來自 git 撈回的舊 prod config + 廠商 model card。行為是 fail-loud（不可讀 ⇒ unavailable ⇒ on_failure），所以錯了不會靜默錯判，但功能會不可用——P1/P5 transcript 是修正依據 |
| 8 | prod 部署順序 | 注意 | 全部變更已在同一 repo 的 main，一起部署即可；但若 gateway/IAM 分批上，**gateway 先**（舊 gateway 對新欄位缺鍵靜默忽略——N6 是順序強制的原因）。注意 memory：現行 blue-green 慣例是 IAM 先 gateway 後，與本功能要求相反，分批時要顯式指定 |
| 9 | 前端 dev server 跨 merge 的 i18n 陷阱 | 注意 | `src/i18n/request.ts` 靜態 import 兩份 messages JSON 並在 module load 合併一次；**跑著的 `next dev` 不會因 JSON 變更而重載 server 端 catalog**（client component 會 HMR），症狀是新 component 要新 key → `MISSING_MESSAGE`（例：`policies.contentForm.nvidiaUnavailable`，2026-08-07 實際發生）。修法：重啟 dev server（頑固時 `rm -rf .next`）。catalog 本身是齊的，別誤判成缺 key |

---

## 6. 完整檔案索引（本次實作全部觸及的路徑）

### 6.1 權威文件（docs/）

```
docs/prd/PRD-279-nemoguard-self-hosted-judgement-source.md      需求（status 已更新）
docs/adr/ADR-375-nemoguard-self-hosted-judgement-source.md      架構（status 已更新）
docs/specs/SPEC-223-guardrail-v2-contract.md                    契約 C-223-42..48
docs/research/RESEARCH-nemoguard-lora-judgement-source-evidence-2026-08-07.md
docs/plans/nemo-guardrail.md                                    拍板紀錄（含實作狀態塊）
docs/adr/core/Core-ADR-{01,02,03,04,06}-*.md                    已回寫（02 為主列）
docs/prd/core/Core-PRD-{02,05,10}-*.md                          已回寫（02 為主列）
scripts/probe_nemoguard.py                                      §8.1 probe harness（未執行）
install_service/GUARDRAIL_JUDGE_NEMOGUARD.md                    單 adapter 安裝指南
install_service/scripts/deploy-nemoguard-judge.sh               部署腳本（要加第二顆 adapter）
```

### 6.2 Guardrail contract 層（純函式，gateway 與 IAM 共用）

```
xparse_guardrail/contract/nemoguard/__init__.py                 facade（新）
xparse_guardrail/contract/nemoguard/mapping.py                  Aegis 對映 + served-model/path 常數（新）
xparse_guardrail/contract/nemoguard/prompts.py                  兩套 prompt/messages builder（新）
xparse_guardrail/contract/nemoguard/parser.py                   兩套 parser，fail-loud（新）
xparse_guardrail/contract/judgement_egress.py                   egress default-deny matcher（新）
xparse_guardrail/contract/capabilities.py                       descriptors/flags/MAX=3/validate 函式（改）
xparse_guardrail/tests/contract/test_nemoguard.py               52+ 測試（新）
xparse_guardrail/tests/contract/test_judgement_egress.py        egress 矩陣（新）
xparse_guardrail/tests/contract/test_capabilities.py            anti-drift 對偶更新（改）
```

### 6.3 IAM

```
xparse_iam/xparse_iam/db/models/provider.py                     ProviderCredential.endpoint（改）
xparse_iam/xparse_iam/migrations/0243_provider_credential_endpoint_seed_nemoguard.py（新）
xparse_iam/xparse_iam/policies/schema.py                        兩 literal + on_topic.engines + judgement_credential_ref + max_length=3（改）
xparse_iam/xparse_iam/authorization/guardrail_policy_merge.py   topic union + 第五欄 pin + clamps（改）
xparse_iam/xparse_iam/authorization/guardrail_resolver.py       re-assert + same-scope 第五欄（改）
xparse_iam/xparse_iam/application/use_cases/policy/validate_policy_content.py   寫入邊界（phase guard 已撤、真閘門在）（改）
xparse_iam/xparse_iam/core/auth_engine.py                       _resolve_judgement_credential_projection（改）
xparse_iam/xparse_iam/api/ninja_api/_internal.py                共用解密 helper（改）
xparse_iam/xparse_iam/api/ninja_api/_providers.py               endpoint 收/驗/回 + test-judgement route（改）
xparse_iam/xparse_iam/api/ninja_api/_helpers.py                 _probe_judgement_endpoint（改）
xparse_iam/xparse_iam/api/schemas/_core.py                      TestJudgementCredentialResponse（改）
xparse_iam/xparse_iam/api/schemas/_policy.py                    Register/Response + endpoint（改）
xparse_iam/xparse_iam/api/schemas/__init__.py                   export（改）
xparse_iam/xparse_iam/db/django_database/_provider_plugin.py    create_provider_credential + endpoint（改）
xparse_iam/tests/unit/test_adr375_judgement_projection.py       12 測試，真 ORM（新）
xparse_iam/tests/unit/test_adr375_judgement_connection_test.py  15 測試（新）
xparse_iam/tests/unit/test_guardrail_policy_merge_v2.py         +9 fold 測試（改）
xparse_iam/tests/integration/test_validate_policy_content.py    authoring-open 套件（改）
```

### 6.4 Gateway（bustream）

```
bustream/gateway/classifier_handler.py       explicit dispatch / topic fan-out / _gather_arm_results / pre-mask 穿線 / emit 歸因（改，核心檔）
bustream/gateway/nemoguard_arms.py           兩條臂傳輸 + 投影消費 + egress 檢查（新）
bustream/gateway/iam_http_client.py          HttpJudgementCredentialData + parse + 快照欄位（改）
bustream/gateway/guardrail_policy_adapter.py 新欄位平移（改）
bustream/gateway/cache_handler.py            ⚠️ cache fingerprint 在這裡（_classifier_cache_variant），已加兩鍵（改）
bustream/gateway/guardrail_response.py       classifier_unknown_engine 對映（改）
bustream/gateway/routes/chat.py              pre-mask 快照 + 傳遞（改）
bustream/gateway/request_text.py             ⚠️ 沒動、也不要動（與 PII 遮罩寫回契約綁定）
bustream/audit/schema.py                     兩個新宣告欄位（改）
bustream/audit/xparse_bridge.py              PAYLOAD_ALLOWLIST 兩條（改）
tests/unit/test_nemoguard_gateway_arms.py    39+ 測試（新，含 dispatch anti-drift）
tests/unit/test_classifier_handler.py        fallback fake 簽名更新（改）
tests/unit/test_gateway_cache_handler.py     fingerprint 釘住更新（改）
tests/unit/test_classifier_audit_fields_survive_bridge.py   bridge-survival 擴充（改）
```

### 6.5 Console（frontend/console-app-refactor/）

```
src/app/(main)/(ai-gateway)/policies/_components/policy/policy-content-form.tsx   主檔：三態/WIRE/data-driven 反推/GuardrailCredentialField(kind)/threshold 灰化（改）
src/app/(main)/(ai-gateway)/policies/_components/policy/policy-content-form.test.ts   +7 測試含紅線 banned-words（改）
src/types/iam.ts                             GuardrailTopicEngineId / JudgementTestResponse / ProviderCredentialResponse.endpoint 等（改）
src/services/iam.ts                          useTestJudgementCredential（改）
src/i18n/messages/en.json + zh-TW.json       8 組新 key（改；en 是 source of truth）
```

### 6.6 Wiki 與知識層

```
xparse-wiki/wiki/concepts/guardrail-enforcement.md   實作狀態已同步
xparse-wiki/wiki/log.md                              doc-sync 紀錄
docs/research/研究智庫-HUB.md                          設計期已回補
~/.claude/projects/-Users-peter-Desktop-X-parse-xparse/memory/   四條工程記憶（見 §3.3）
```

### 6.7 參考樣板（照抄對象，勿改）

```
xparse_guardrail/contract/openai_moderation/{__init__,mapping,parser}.py   contract 層樣板
scripts/probe_openai_moderation.py                                         probe 紀律樣板
xparse_iam/.../ninja_api/_helpers.py::_probe_openai_moderation             connection test 樣板
```

---

## 7. 給接手 agent 的最短指引

1. **先讀本文件 §2（拍板 + 三個易錯點）與 §5（known issues）**；行為契約疑義查 `SPEC-223` C-223-42..48，不要憑 PRD/ADR 散文推斷。
2. **你的第一個任務幾乎必然是 §4.1 跑 probe**（前提：人類提供了端點）。跑完把 transcript 貼進 evidence pack、依結果更新 ADR-375 status，再談 Phase 3。
3. **要寫任何「中文更準」的字之前**，先讀 §1.1 紅線——它是 REFUTED，且有測試守著。
4. **加第四個 evaluator 時**：literal + capability flag + dispatch branch **三處同 PR**（anti-drift 測試會紅給你看，那是 feature 不是 bug）。
5. **沒有 probe transcript 就沒有 verified**——green tests + CI + ADR-093 表是儀式不是證據（§8.1）；本次所有整合測試用的是 fake transport 餵真 parser，只證明「建造正確」。
6. 部署面三件事一次記牢：egress allowlist 預設全拒（兩個 process）、timeout 是猜測值、prod 分批上要 gateway 先（與現行 blue-green 慣例相反）。
