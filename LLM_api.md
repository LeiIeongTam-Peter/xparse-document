# LLM API 面（Gateway 治理核心）交接文件

> **給誰**：接手這條工作線的 LLM／工程師。讀完這份就能知道架構長什麼樣、做到哪裡、還差什麼。
> **基準**：`origin/main` `4a4a93331`（2026-10-07）；2026-10-14 對 `ee1a40564` 重新核對過 §0–§3、§5–§8、§10。repo 根目錄 `/Users/peter/Desktop/X-parse/xparse`；下文 `G/` = `apps/gateway/bustream/gateway/`，`B/` = `apps/gateway/bustream/`。
> **權威來源**：本文是導覽，不是規格。規格以 repo 內 `docs/` 為準（見 §3）；與本文衝突時以 `docs/` 為準。
> **開工前必做**：`git fetch origin && git rev-list --count HEAD..origin/main`，結果不是 0 就別信本機舊樹。
> **2026-10-14 更新**：
> - 部署狀態改成現況：rel（`v1.77.0.16`）已有 §4 列的全部；10-08 之後的 API 面工作只在 main。
> - 補上 10-07 之後的新東西：`xparse_tools` stage（共 19 個）、回應端登記表（§1.8，Amendment B）、terminal 的新規則與新 gate。
> - §6、§7 的票與待辦改成現況：#5667、#450 已關，Codex 工具、o-series temperature 已修，新增三張 `KnownGap` 票。

---

## 0. 三十秒版

- **問題**：chat、messages、responses、embeddings、speech、transcriptions 六種 API 面，原本各自決定要跑哪些治理（guardrail、定址、預算、Policy Kernel……），遇到「不認得的面」就預設跳過，治理會靜默漏接。
- **決策**（ADR-494 Amendment A，2026-10-05 Peter 核定）：不拆 service。所有面共用**一條** pre-dispatch pipeline 和**一個** terminal。每個面登記在**登記表**上，每個 adapter 對每個 stage **逐格宣告**處置（`RUN`／`NotApplicable(文件)`／`KnownGap(#issue)`），**沒有預設值**。漏宣告或未登記時，執行期回 500 並寫稽核，CI 也會先擋下。
- **進度**：
  - M0–M9 全部 merge 進 main。
  - 過程中另外發現並修好約 25 個 bug。
  - 做過一輪本機實機 e2e（六個面＋Claude Code／Codex／OpenCode），找到的 13 個 bug 也都修好並 merge。
- **刻意保留**：三個非對話面（embeddings、speech、transcriptions）有 5 個治理開關目前是「**只記錄、不擋**」。Peter 2026-10-06 決定等部署後看 prod 稽核再決定何時切換。
- **部署**：
  - `origin/rel`（`release/v1.77.0`，tag `v1.77.0.16`，`2534867ad`）：本文 §4 列的全部都在，包括 M8⑧、e2e 那 13 個修正、#6070–#6073。
  - 不在 rel：10-08 rel 切點之後的 API 面工作，例如 #6314 xparse_tools stage、#6474 回應端登記表、#6447、#6457、#6367、#6289。
  - **prod（v1.76.4）還沒有任何一項**。

---

## 1. 架構（現在長什麼樣）

### 1.1 三層

```
HTTP ─▶ L1 Wire adapter（每個面一個）：wire → 中立輸入；宣告處置表；渲染錯誤／結果
        ─▶ L2 治理核心（只有一份）：面登記表 → PIPELINE（順序寫死）→ 逐格處置 → terminal
            ─▶ L3 執行家族：generate_stream（chat 狀態機／Responses：原生 passthrough，或經翻譯軸由 Claude、chat 家族無狀態回答，ADR-503 P8 #6190）｜unary（embeddings／speech／transcriptions）
```

- **順序只寫在一個地方**：`G/dispatch_pipeline.py::_build_pipeline`，共 19 個 stage。adapter 只宣告「哪些 stage 適用」，不宣告順序，所以這不是 ADR-494 §4 B 否決的「宣告式排序」。
- **Stage 依序**：`auth → request_fields → session → policy_actions → tool_results → tool_rules → xparse_tools → input_rail → semantic_cache → request_policy → store → addressing → budget → routing → policy_kernel → agent_mode → chain → classifier_and_admission → endpoint_lease`。
  - `xparse_tools` 由 #6314 加入（ADR-501／SPEC-314，只在 main）。chat、messages 是 `RUN`；responses 是 `KnownGap(#6166)`；三個 unary 面是 `NotApplicable(ADR-501)`。
- **強制 stage**（`MANDATORY_STAGES`）：`auth`、`request_fields`、`policy_actions`、`budget`、`classifier_and_admission`。這五個只能是 `RUN` 或 `KnownGap`，不得宣告不適用（INV-494-8）。

### 1.2 面登記表

`G/surface_registry.py` 全用 literal 寫，讓 stdlib AST gate 能直接讀：

| name | path | family | usage_unit |
|---|---|---|---|
| chat | `/v1/chat/completions` | generate_stream | tokens |
| messages | `/v1/messages` | generate_stream | tokens |
| responses | `/v1/responses` | generate_stream | tokens |
| embeddings | `/v1/embeddings` | unary | tokens |
| audio.speech | `/v1/audio/speech` | unary | characters |
| audio.transcriptions | `/v1/audio/transcriptions` | unary | seconds |

- `lookup_path(path)` 回傳面的**名稱**，查不到回 `UNREGISTERED`。
- `run_pre_dispatch` 在跑任何 stage 之前先檢查三件事：面未登記、缺處置、強制 stage 被宣告不適用。
  - 任一成立就回 `StageRejection(stage="surface_gate", 500)`，並寫恰好一筆 `REQUEST_REJECTED`。
  - 頂層 `rejection_reason` 與 `extra.reason` 同值：`surface_unregistered` 或 `disposition_missing`。
- 不執行推論的 route 不登記，例如 `/v1/messages/count_tokens`、`/v1/models`、`/v1/usage`。它們歸為「非執行」，並附文件依據（`B/production/coordination/coverage.py::NON_EXECUTION`）。

### 1.3 處置與參數

- **型別**在 `G/surface_adapters/__init__.py`：
  - `RUN`
  - `NotApplicable(ref)`：`ref` 必須是 `ADR-`／`SPEC-`／`PRD-` 編號。
  - `KnownGap(stage, issue, gap, aspect=None)`
  - aspect 層級另有 `not_applicable_aspects` 與 `skips_aspect()`（SPEC-308 SR-9a）。
- **面與面的差異只能用具名參數 `SurfaceParams` 表達**（INV-494-3）。每個欄位都要有文件依據，沒有預設值，`__post_init__` 會擋非法組合。目前的欄位：
  - 請求欄位與 session：`refuse_fields`、`record_held_fields_at_ingress`、`scope_keyed_by_session`
  - 工具與參數：`legacy_tool_call_at_tool_rules`、`platform_strip`、`validate_generation_params`
  - 路由：`pin_runs_resolver`、`follows_binding`
  - Policy Kernel：`kernel_rollout`、`kernel_record_only`、`kernel_judges_prepared_target`
  - 預算與 admission：`prepares_target_before_budget`、`budget_gates_in_admission`、`admission_budget_by_requested_model`
  - 防護規則：`input_rails_shadow_only`、`judge_binds_prepared_target`、`output_rail_shadow_only`
  - endpoint lease：`lease_on_prepared_target`
  - 定址：`addresses_without_routing`、`addressing_hidden_name_record_only`、`addressing_unbound_record_only`
- **Adapter 用 `runtime_checkable` Protocol 型別化**（`G/surface_adapters/protocols.py`）。`STAGE_REQUIRES` 與 `PARAM_REQUIRES` 保證：宣告 `RUN` 的 adapter，真的具備那個 stage 需要的方法。
- **Adapter 檔案**：
  - `chat.py`：`ChatCoreAdapter`、`ChatSurfaceAdapter`、`MessagesSurfaceAdapter`
  - `responses.py`、`embeddings.py`
  - `audio.py`（speech 與 transcriptions 共用的部分）、`speech.py`、`transcriptions.py`

### 1.4 「只記錄」開關（刻意，不是 bug）

`.github/scripts/surface-dispositions-gate.py::RECORD_ONLY_PARAMS`（規則 (m)）把這些開關釘在指定的面上。要切換，就得同時改這張表：

| 參數 | 面 | 依據 | 切換追蹤票 |
|---|---|---|---|
| `kernel_record_only` | 三個非對話面 | PRD-341 D-1 | #5941 |
| `addressing_hidden_name_record_only` | 三個非對話面 | PRD-341 D-2b | #5949 |
| `addressing_unbound_record_only` | speech、transcriptions | PRD-341 D-2c | #5949 |
| `input_rails_shadow_only` | 三個非對話面 | PRD-341 D-3 | #5976 |
| `output_rail_shadow_only` | transcriptions | PRD-341 D-4 | #5965 |

注意兩張票的差別：

- **#5976 不是改參數就能切**。這三個面還沒有 input rail 的 enforce 路徑：
  - 參數一關不會報錯，但 stage 會改傳 `surface_text=None`（`G/dispatch_stages.py::run_input_rail`，約 369 行），rail 退回讀對話格式的欄位。結果 transcription 的 `prompt` 完全不會被檢查，embeddings 的 `input` 也不再逐筆檢查。
  - `guardrail_handler.py` 那道 `ValueError` 守門（有 `surface_text` 卻不是 `observe_only`）就是之後 enforce 路徑要取代的地方。
  - adapter 遇到 graceful block 會丟 `TypeError`。
- **#5965 保留了 enforce 路徑**。切換要改兩處：transcriptions adapter 把 `output_rail_shadow_only` 設成 `False`，並從 gate 的 `RECORD_ONLY_PARAMS` 移除那一列。

### 1.5 Terminal 與用量

- 三種終端事件（`EXECUTION_STARTED`、`EXECUTION_COMPLETED`、`EXECUTION_FAILED`）**只能**由 `G/terminal.py` 發出，入口是 `settle_started`、`settle_completed`、`settle_failed`。
- `B/tests/contract/test_one_terminal.py` 用 AST 掃整個 `gateway/` 和 `streaming/` 來鎖住這條規則，例外清單已清空。
- **進入執行**的請求恰好一個終端事件（COMPLETED 或 FAILED，SPEC-308 TP-1），而且一律先記帳再發事件。
- 執行前就被拒的請求（認證 401、預算或 interim quota 用完 400〔#6367 起，只在 main；rel 仍是 429〕、rate／concurrency 429、定址 404、`surface_gate` 500）不發終端事件，只發 `REQUEST_REJECTED` 或什麼都不發。unary 家族遇到 client 斷線（`CancelledError`）也不發。
- **每次路由嘗試一筆 STARTED**（TP-6，#6123，已在 rel）：帶 `routing_attempt`（primary 為 1，R3 每換一次加 1）。終端事件帶產生它的那次嘗試的模型與 `translation_path`。#6509 起（只在 main），chat／messages 的 STARTED 也帶 `model_uuid`（SPEC-308 §9.14）。
- **失敗終端的健康判定要寫在呼叫點上**（SPEC-308 §9.13，#6447，只在 main）：`settle_failed`、`emit_streaming_error`、`emit_responses_execution_failed` 每個呼叫都要寫明 `record_health=` 或健康碼，由 `failure-health-attribution-gate` 鎖住，沒有例外清單。
- **記帳函式**：`terminal.COMPLETED_BOOKERS` 每個 `UsageUnit` 恰好一個 booker，缺了 gateway 在 import 時就起不來（SR-32，#6469，只在 main）。
- `G/terminal_usage.py` 有一張「用量單位 → resolver」的表（tokens、characters、seconds）。遇到不認得的形狀直接拋例外，絕不算成 0（`test_terminal_usage_resolvers.py`）。

### 1.6 unary 執行家族

- `G/unary_execution.py::run_unary`：在 `attempt_scope` 內呼叫 worker，最後用 `settle_*` 收尾。其中的 `with_correlation_headers` 讓每個錯誤回應都帶 `X-Request-Id` 和 `X-Trace-Id`。
- transcription 的 output rail 在 `G/unary_output_rail.py`，重用 chat 非串流用的 buffered rail。
- Policy Kernel「只記錄」的寫法在 `G/policy_kernel_record.py`。

### 1.7 防回歸（CI 會紅的地方）

| Gate／測試 | 鎖什麼 |
|---|---|
| `B/tests/contract/test_surface_registry.py` | 面常數只能定義在登記表；`lookup_path` 精確比對 |
| `B/tests/contract/test_dispatch_fail_closed.py` | 未登記的面或缺處置 → 500＋一筆稽核，沒有任何 stage 執行 |
| `.github/scripts/surface-dispositions-gate.py`（+`--self-test`） | 見下方說明 |
| `.github/scripts/surface-conformance-gate.py` | conformance 的面清單來自登記表；(j) 測試標記與處置一致；(k) 終端事件只在經 terminal 發出的面上算覆蓋；(l) adapter 宣告 `RUN` 的每一格，在該面要有一支通過的測試（#6457，SPEC-306 Rev.4） |
| `B/tests/conformance/`（`harness.py`、`conftest.py`） | 六個面跑同一套測試；執行期軌跡要求測試宣稱的 stage 真的以 `RUN` 跑到；缺口的 xfail 帶 `raises=AssertionError` |
| `B/tests/contract/test_coordination_coverage.py` | 每條受治理 route 都經 `run_pre_dispatch`（或宣告的委派）；`LEGACY_UNPIPED` 已清空、只能縮小；非執行 route 必須附文件；route 盤點也包含 WebSocket 與 mount 的 route（#6457） |
| `.github/scripts/request-field-dispositions-gate.py` | 六個面都有請求欄位去向表，且與 SDK 快照一致 |
| `.github/scripts/conversation-scope-layer-gate.*` | 每個 admission 呼叫端都帶 `conversation_scope` |
| `.github/scripts/guardrail-detection-surface-gate.py` | guardrail 讀取文字的 reader 都已登記 |
| `provider-call-usage-parity-gate.py`、`usage-ledger-surface-parity-gate.py` | 呼叫 provider 或發 COMPLETED 的地方都有記帳（已改指向 `terminal.py`） |
| `.github/scripts/response-checks-gate.py` | 回應端每條路徑 × 每個檢查的處置與 driver 實際接線一致（§1.8，#6474） |
| `.github/scripts/failure-health-attribution-gate.py` | 每個失敗終端呼叫都寫明健康判定（SPEC-308 §9.13，#6447） |

`surface-dispositions-gate.py` 檢查的內容：

- 每個面 × 每個 stage 恰好一個處置。
- 強制 stage 不得宣告不適用。
- `ref` 與 issue 編號的格式正確。
- 規則 (k)：被跳過的 stage 寫出的欄位，不能被後面宣告 `RUN` 的 stage 讀取。例外要登記在 `NONE_TOLERANT_READS` 並附理由。
- 規則 (l)：aspect 層級的不適用。
- 規則 (m)：只記錄開關表（§1.4）。

### 1.8 回應端登記表（ADR-494 Amendment B，#6474）

- `G/response_checks.py` 列出五條回應路徑：chat 串流、chat 非串流、agent mode、Responses 串流、unary。也列出四個回應端檢查：output rail、回應端 Tool 規則、工具呼叫審視、terminal。
- 每條路徑 × 每個檢查都要宣告 `Run(進入點)`、`NotApplicable(文件)` 或 `KnownGap(#issue)`，沒有預設值（INV-494-11）。
- 這個檔只宣告、不執行，執行期沒有人 import 它。`.github/scripts/response-checks-gate.py` 用 AST 對照 driver 模組。driver 新 import 的 `bustream.gateway.*` 模組也要先分類（INV-494-12）。
- 目前唯一的缺口：agent mode 沒有 output rail（`KnownGap(#5897)`）。
- gate 只證明接線與宣告一致，不證明檢查真的跑到。

---

## 2. 核心檔案地圖

| 用途 | 路徑 |
|---|---|
| 面登記表 | `G/surface_registry.py` |
| Pipeline 與 runner | `G/dispatch_pipeline.py`（`_build_pipeline`、`run_pre_dispatch`、`MANDATORY_STAGES`、trace sink） |
| Stage 實作 | `G/dispatch_stages.py`、`G/dispatch_stages_execution.py`、`G/routing_stage.py`、`G/tool_governance_stage.py`、`G/xparse_tools_stage.py`（#6314，只在 main） |
| Adapter | `G/surface_adapters/{__init__,protocols,chat,responses,embeddings,audio,speech,transcriptions}.py` |
| Route | `G/routes/{chat,messages,responses,embeddings,tts,transcriptions,chat_agent}.py` |
| 非串流 chat | `G/non_streaming_handler.py` |
| 回答報哪個模型 | `G/answer_model.py`（`answer_model()` 是唯一決定點，`plan_model_name()` 給 route 與非串流用；#6067 選項 A；#6161 起 messages／responses 也用它，ADR-221 Amendment B） |
| 回應端登記表 | `G/response_checks.py`（Amendment B，只宣告不執行） |
| 串流格式 | `G/sse_formatter.py`（只負責把傳進來的 `client_model` 寫進每個 chunk，不做決定） |
| Terminal 與用量 | `G/terminal.py`、`G/terminal_usage.py` |
| unary 家族 | `G/unary_execution.py`、`G/unary_output_rail.py`、`G/audio_governance.py`（現在只剩 slot 與請求視圖） |
| 稽核小工具 | `G/pre_auth_audit.py`（認證前的拒絕）、`G/policy_kernel_record.py` |
| 請求欄位 | `G/request_fields.py`、`B/scripts/sdk_request_params_snapshot.py`、`B/scripts/sdk-request-params.v1.json` |
| 路由覆蓋 | `B/production/coordination/coverage.py` |
| Worker | `B/streaming/workers/`（`errors.raise_on_stream_error_chunk`、`responses_tool_items.py`） |
| 測試 | `B/tests/conformance/`、`B/tests/contract/`、`B/tests/integration/test_*characterization*.py`、`B/tests/resource_manager_transport.py` |
| CI 測試清單 | `B/gateway-ci-suite.txt`（新測試檔必須登記在這裡，否則 orphan gate 會紅） |

---

## 3. 設計文件（source of truth）

| 文件 | 內容 |
|---|---|
| `docs/adr/ADR-494-shared-dispatch-pipeline.md` §11 Amendment A | 登記表、處置表、強制 stage、unary 家族、INV-494-7..10；§11.7 記錄 Q1–Q17 的決定；**§12 Amendment B**（回應端登記表，INV-494-11..12） |
| `docs/adr/ADR-492-cross-surface-governance-conformance-suite.md` | 已 Accepted，加上 Amendment A：面清單從登記表導出、範圍改成「事件 × 面」、執行期 stage 軌跡 |
| `docs/adr/ADR-479-audio-surface-governance-parity.md` | Amendment A：audio 改走完整的共用核心 |
| `docs/adr/ADR-221-model-identity-reconciliation-response-model-layer.md` | Amendment A／INV-221-5：選單型 app 回報實際執行的模型（#6067 選項 A）；Amendment B 把同一條規則擴到 messages／responses（#6161）。ADR-221 仍是 Proposed，#450 已以「不做」關閉，正式核定只剩 #471 |
| `docs/spec/SPEC-308-shared-dispatch-pipeline-contracts.md` | §9 是 terminal 契約（TP-1..6；§9.10 R3 建不起來、§9.11 每次嘗試一筆 STARTED、§9.13 健康判定明寫、§9.14 STARTED 帶 `model_uuid`）；§10 是 SR-1..SR-32，§10.11 起是每一片的實作紀錄；§11 是 Amendment B |
| `docs/spec/SPEC-306-cross-surface-governance-conformance-contracts.md` | Rev.4：conformance 規則 (a)–(l)，(l) 是逐面的 RUN 覆蓋；CONF-9 執行期軌跡 |
| `docs/prd/PRD-341-non-conversational-surface-governance-parity.md` | 非對話面的治理一致性；§4 驗收條件；§10 決定 D-1..D-4（含 D-2c、D-2d） |
| `docs/spec/SPEC-039-openai-embeddings.md` | 從 Rev.2 起：§10 終端事件、§11 admission header、H39-7 錯誤回應 header |
| `docs/spec/SPEC-307-*`、`docs/adr/ADR-493-*` | 請求欄位去向（Amendment A 擴到 unary 面） |
| `docs/spec/SPEC-256-*` | 參數正規化（D9i：responses 對非推理模型丟掉 `reasoning.effort`；D11d：`stop`） |
| `docs/research/RESEARCH-llm-api-surface-architecture-2026-10-05.md` | 五家平台（LiteLLM、Bifrost、Portkey、One-API、vLLM）的對照證據 |
| repo 外 `/Users/peter/Desktop/X-parse/docs/草案/LLM-api-重構.md` | 原始草案，已被上面的文件取代；檔案頂端有執行狀態表 |

---

## 4. 做了什麼

### 4.1 主線 M0–M9（全部 merge）

| 片 | PR | 內容 |
|---|---|---|
| M0 | #5901 | ADR-494 Am.A、ADR-492 改 Accepted、ADR-479 Amendment、SPEC-308 §10、SPEC-306 Rev.3 |
| M0b | #5908 | PRD-341、研究文件、SPEC-039 Rev.2 |
| M1 | #5904 | 面登記表；未登記的面 fail-closed 並寫稽核 |
| M2 | #5910 | 用處置表取代 `Stage.surfaces`；拆出 `MessagesSurfaceAdapter`；Protocol 化；處置 gate |
| M3 | #5914 | conformance 的面清單改由登記表產生；執行期 stage 軌跡；gate 規則 (j)(k)；請求欄位 gate 規則 (f) |
| M4＋M9 | #5909 | 路由覆蓋 gate；count_tokens 歸為非執行 |
| M5 | #5906 | STARTED 與非串流 FAILED 改由 terminal 發出；AST 鎖 |
| M6 | #5919 | embeddings 併入 pipeline 與 terminal；建立 unary 家族 |
| M7 | #5933 | speech／transcriptions 併入；`LEGACY_UNPIPED` 清空（關閉 #5887） |
| M8 ①–⑨ | #5937 #5939 #5942 #5950 #5940 #5947 #5938 #5962 #5936 | 見下方 |

M8 九片：

- ① policy_actions（#5937）
- ② request_fields（#5939）
- ③ request_policy（#5942）
- ④ addressing（#5950）
- ⑤ policy_kernel，只記錄（#5940）
- ⑥ endpoint_lease（#5947）
- ⑦ input rail，shadow（#5938）
- ⑧ transcription output rail，shadow（#5962）
- ⑨ embeddings 的 admission header（#5936）

### 4.2 途中發現並修好的 bug

| PR | 問題 |
|---|---|
| #5898 | embeddings 一次失敗同時發 FAILED 與 COMPLETED |
| #5893 | speech／transcriptions 被 `attempt_scope` 拒絕時沒有終端事件 |
| #5900、#5905 | agent mode 與 chat setup 失敗路徑漏放 endpoint lease |
| #5911 | 非串流 chat 在 provider 回答後才失敗：兩個終端事件、重複記帳、重複計 quota |
| #5924、#5925 | 串流中途出錯：responses 的稽核欄位改成與 chat 一致；messages 補送已收到的文字 |
| #5929 | openai／Azure worker 沒偵測到串流中途的 error chunk，被截斷的回答當成正常完成 |

### 4.3 本機實機 e2e（2026-10-06）與修正

- **報告**：`/Users/peter/Desktop/testing/results/e2e_20261006/REPORT.md`。六個面共 91 個 case，外加三個 agent CLI；找到 13 個真 bug，報告附 issue 草稿與證據。
- **13 個 bug 全部修好並 merge**：
  - #6001：非推理的 gpt-5.x 仍被送 `stop`
  - #6024：responses 對非推理模型丟掉 `reasoning.effort`（比本輪的 #5997 先 merge，#5997 因此關閉。#5997 審查時加的兩項沒帶進 main：Azure 版的參數化測試，以及把 `audit_emitter` 改成必填）
  - #6020：`additional_tools` 繞過工具治理
  - #5996：Responses worker 對 gpt-5.x 送 temperature，`auto` judge 因此一律回 503
  - #6002：串流 chat 露出隱藏的模型名稱
  - #6022：#5667 的主要修正，非串流 chat／messages 的三個錯誤出口補上 `X-Request-Id`／`X-Trace-Id`（#5667 已於 10-08 關閉，部署驗收收在 #6243）
  - #5998、#5995、#5993、#6021、#5992、#6025、#6023：其餘 P3
- **接著修的四張票**：
  - #6070（#6064）：R3 備援 worker 建不起來時沒有終端事件
  - #6071（#6065）：embeddings 的錯誤訊息露出隱藏的模型名稱
  - #6073（#6066）：unary 面的錯誤回應補上 trace header
  - #6072（#6067）：選單型 app 的模型身分，採選項 A

### 4.4 Peter 的決定（摘要）

- **範圍**：草案 Q1–Q11 全照建議，範圍 M0–M9。MCP gateway、A2A、Operator MCP 不在這一輪。
- **PRD-341 的決定**：
  - D-1：資料邊界先只記錄，之後再改 403。
  - D-2a：只存在 YAML 的 embedding 模型先盤點；盤點完成前用只縮不增的例外清單放行，之後回 404。
  - D-2b：隱藏模型名稱的 app，改用它綁定的唯一同類模型；超過一個就拒絕，沒有就回 404。隱藏的名稱被點名時，先只記錄。
  - D-2c：音訊面的定址先只記錄。
  - D-2d：用 app 代碼呼叫時也套同一條規則，`select_available=true` 的 app 也一樣。
  - D-3：input rail 先 shadow，embeddings 只跑不呼叫 LLM 的 rail。
  - D-4：transcription 的 output rail 先 shadow。
- **2026-10-06**：所有「只記錄」開關**維持不切**，等部署後看 prod 稽核的實際用量再決定。
- SPEC-304 C-304-149 維持不變：messages 被工具規則擋下的那一輪，不送任何內容。
- 音訊面的 `auto` judge 會綁到 TTS／Whisper，維持現狀（只在 shadow 下發生）。
- **#6067 選選項 A**：選單型 app 的每個 chunk 和非串流 body，都回報實際執行的模型；R3 換模型後改成備援模型。
  - 理由一：符合 INV-221-2 原文與它的 Q5 答案。
  - 理由二：與 OpenAI 回報實際 snapshot 的慣例一致。
  - 理由三：對串流 client 的改動最小。
  - 限制：串流的 response header 在開始串流時就已送出，所以 R3 之後串流的 `X-Xparse-Model-Default` 無法更新。

---

## 5. 部署狀態

| 環境 | 狀態 |
|---|---|
| main | 全部都在 |
| `origin/rel`（`2534867ad`，tag `v1.77.0.16`，10-14） | §4 全部都在（M0–M9、§4.2、§4.3 的 13 個修正、#6070–#6073）；**沒有** 10-08 切點之後的 #6314、#6474、#6447、#6457、#6367、#6289、#6509 |
| `origin/prod`（`ed62d8223`，2026-10-02） | 都沒有 |

- **部署前必做 #6068（先查再改）**：rel／prod 的 IAM 資料還沒查過。
  - 先在各環境做唯讀比對：每一列 Model 的 `supports_reasoning`，對照打包快照裡的值。不一致的才改。
  - 改成 true 時要同時設定 `reasoning_effort_levels` 並排除 `minimal`。只改旗標的話，原本會被丟掉的 `minimal` 請求，會變成 provider 回 400。
    - main 上 #6534（D9m，只在 main）之後，沒宣告等級、以字串送等級的推理模型只送 low／medium／high，`minimal` 會被夾成 low，所以這一條只對還沒有 #6534 的 rel／prod 必要。
    - #6534 本身有部署順序：IAM＋Console 先上，gateway 上之前先在目標環境跑唯讀的 `python manage.py inventory_reasoning_effort_levels`，把各模型的等級宣告好，否則 Claude Code 的 `max`、Codex 的 `xhigh` 會被夾成 `high`。
  - `reasoning_effort_levels` 要等 #6050 的 migration 套用後才能設。
- **部署後要做**：
  - 線上前後對照實測。只有部分 PR 附了實測腳本（#6001、#5996、#6002、#5998、#5993、#6021、#6073），都在 `/Users/peter/Desktop/testing/e2e1006_*`；其餘 PR 要自己補。
  - 看 prod 稽核，再決定四張切換票什麼時候切。

---

## 6. 還沒做／待決

### 6.1 開著的票

| 票 | 內容 |
|---|---|
| #5899 | 總 Epic |
| #5941 #5949 #5965 #5976 | 四個「只記錄 → 執行」的切換（見 §1.4；#5976 要先建好 enforce 路徑） |
| #5948 | IAM 的模型沒有「類型」欄位（chat／embedding／TTS／STT），音訊面用 app 代碼時挑不出模型。目前回 400 `model_name_required`，以 aspect `KnownGap` 登記 |
| #6068 | luna 推理旗標的資料修正（部署前，P2） |
| #6243 | rel（v1.77.0.9）已部署修正的部署驗收清單，其中有 #5667 的主要修正 #6022。#5667 已於 10-08 關閉；同類修正 #6070、#6154（pipeline 拒絕，在 rel）與 #6289（messages pipeline 前的拒絕，只在 main）不在 #6243 的清單內，部署後要另外驗。worker setup／model resolution／routing plan 這幾個執行前錯誤是否都帶兩個 header，待重新核對 |
| #5955 | gpt-oss-120b 會推理卻被當成非推理（`_requires_completion_tokens_api` 只看名稱；#6331 起改讀 `backend/openai_model_family.py`，`gpt-oss-*` 不算推理家族，所以仍判成非推理） |
| #471 | ADR-221 尚未正式核定（#450 已於 10-08 以閒置關閉，ADR-221 仍是 Proposed） |
| #6166 | `/v1/responses` 不執行 Xparse tools，`xparse_tools` stage 宣告為 `KnownGap` |
| #5897 | chat agent mode 沒有 output rail 與 idle deadline，是回應端登記表上唯一的 `KnownGap` |
| #4247 | `/v1/responses` 的 semantic cache（`KnownGap`） |

### 6.2 已寫好草稿、還沒開票（要 Peter 同意）

草稿放在 `/Users/peter/Desktop/X-parse/docs/LLM_api-drafts/`。草稿裡的行號是對 `cbb78f0bf` 寫的，main 已有漂移，開票前要重新核對：

1. **`issue-draft-audit-seam.md`（重要）**：`B/production/key_resolver.py` 的 `_audit_emit`，在執行中的 gateway 裡綁到的是 `bustream.audit.emit` 模組而不是函式。呼叫時丟 `TypeError`，又被 fail-open 吞掉，所以所有 `credential_resolved`／`credential_resolution_failed` 稽核事件都遺失了（已實測）。
2. **`issue-draft-chat-422.md`**：chat 的 key-resolution 422 仍會露出模型名稱或 uuid（`G/worker_setup.py` 約 1491–1494 行，`detail=f"Provider key resolution failed: {error}"`）。
3. **`issue-draft-attempt-unmapped.md`**：協調（多副本）模式下，IAM profile 的 embedding 一律回 503 `attempt_unmapped`。目前潛伏，因為 prod 是單副本。

~~Codex lite／code mode 經過 Xparse 沒有可用的工具~~：已解決。Peter 2026-10-12 決定先全部轉送、治理之後再加（ADR-490 Q1 Amendment C），由 #6360 修好（只在 main）。

### 6.3 等 Peter 確認

**#6064 的做法**：問 Peter 的時候被中斷，還沒有答案。目前已 merge 的做法：

- `PROVIDER_FALLBACK.succeeded` 維持 `true`，意思是「換了模型」。
- 新增的 FAILED 算在備援模型上，不記帳。
- 主模型那次嘗試只在 PROVIDER_FALLBACK 記一次帳。
- 語意寫在 SPEC-308 §9.10。

另一種做法是改成 `false`、把帳移到 FAILED。缺點是按模型統計時，備援模型的錯會算到主模型頭上。

### 6.4 已知但還沒處理的小缺口

- speech 在認證前就擋掉未知欄位（400）時，不會留下稽核紀錄。#5970 列了選項但沒有定案；可以用 `G/pre_auth_audit.py` 補。
- FastAPI 在進 route 之前就拒絕的請求沒有 request id，例如 speech 的 body 驗證、transcription 表單缺欄位。
- 以下幾種拒絕沒有稽核紀錄：認證失敗 401、embeddings 的執行目標 422／500、transcription 用 app 代碼的 400。
- 選單型 app 命中 semantic cache 時，回傳的是存入當時的 `model`（ADR-221 §2.6.2 列為範圍外）。
- 協調模式下，opaque 請求的 `budget_model_uuid` 是 None，所以查不到執行模型在整個機隊的上限（未驗證）。
- o-series 拒絕 `temperature`：已由 #6331 修好，兩個 Responses worker 都依 `backend.openai_model_family` 省略（只在 main）。worker 省略 temperature 時 `exec_temperature` 稽核仍記設定值：未再核對。
- `docs/runbooks/responses-api-error-envelopes.md` 第 190、221 行仍描述 #670 之前的作法。
- `test_openai_compat_spec.py` 還在 orphan baseline，裡面有一個在 main 上本來就紅的測試。

### 6.5 清理

- **7 個 e2e 測試模型**（openai_responses）被 ResponsesBinding 擋著刪不掉，目前已設成 disabled，也不屬於任何 proxy 或 app。**2026-10-08 03:00 UTC 之後**用 admin key 執行 `DELETE /apis/iam/models/<uuid>` 刪除。UUID（e2e 報告 §6 也有）：
  - `845772bd-3ed3-4903-98c2-b3bafdbb1676`
  - `938527b3-6ce0-444f-8e4d-b4459ccede5e`
  - `1c1e99a0-22d3-440a-9269-4ad115ed241d`
  - `e11c84f8-f916-4cf5-b57d-520477b4bd31`
  - `a8612df2-e4f8-47d9-b38f-4325bc19e81e`
  - `4aeefdcb-f783-41d4-becd-e8bff6d3776d`
  - `9428d052-d723-4120-ab01-cd6dca0f1869`
- **幾個 policy 空殼**（沒有刪除 API）：`b59652c0`、`fbe83b72`、`1647ae3f`、`c6cdc8ab` 等，都已停用。
- ~~`/private/tmp/e2e1006-{claude,codex,opencode}/`~~：已不存在（10-14 確認）。
- **`/Users/peter/Desktop/X-parse/pr-worktrees/` 下的 `llmapi-*`、`fix1006-*`、`fix1007-*` worktree**（在 repo 的上一層，不是 `xparse/pr-worktrees/`）：可以清掉。只有 `fix1006-responses-reasoning-effort-non-reasoning`（#5997）是關閉而非 merge，它的 branch 在 origin 上同一個 sha，刪 worktree 不會丟東西。

---

## 7. 可優化方向（建議）

1. **先修 §6.2 的 audit seam bug**：憑證解析的稽核整條都沒在運作，影響所有面，而且修法很小。
2. **做 #5948 模型類型欄位**：做完後音訊面的 D-2b（用 app 代碼挑模型）和定址才算完整，候選集過濾也不必再靠名稱猜。
3. **把「切換只記錄開關」的流程標準化**：每張切換票都寫好了部署後要看哪些稽核。建議先寫一支 prod 稽核查詢腳本，依 endpoint／app 統計以下幾項，讓四張票可以一次決定：
   - `boundary_shadow_would_block`
   - `policy.violation` 裡 `record_only` 的紀錄
   - guardrail 的 shadow 判定
   - `classifier_degraded`
4. **#5976 先補 enforce 路徑**：unary 面的 input rail 目前沒有可切換的 enforce 實作，切換前要先做出來。
5. **錯誤 header 一致**：主體已完成（#6022、#6070、#6154、#6289；#5667 已關）。剩下的是更新 conformance `harness.py` 的 `SURFACE_CORRELATION_HEADERS` 註解，並看能不能改成所有面通用；另外確認 worker setup 等執行前錯誤也帶 header。
6. **把推理能力的判斷收成一處**：名稱這一半已由 #6331 收進 `backend/openai_model_family.py`，`_requires_completion_tokens_api` 也改讀它。還剩旗標（D9 的 `supports_reasoning`）與名稱規則兩套並存。gpt-oss-120b 兩邊都判成非推理（#5955），luna 的旗標資料錯（#6068）。
7. **補強規則 (j)**：#6457 的規則 (l) 已擋下「RUN 的格子只有帶缺口標記的測試」的情況。還剩：另有一支通過的測試時，殘留的缺口標記仍要靠 strict xfail 的 XPASS 才會發現。可以在 gate 加一條靜態檢查。
8. **MCP gateway／A2A**（草案 §5）：建議 MCP 的 (b) 放在 gateway owner 內，新增 `tool-invoke` 執行家族，共用同一份 PIPELINE。動工前要先寫 PRD／ADR。相關進度：ADR-501 的 Xparse MCP 管理工具（gateway 執行、由 `apps/operator-mcp` 提供），已用 PIPELINE 裡的 `xparse_tools` stage 接上 chat／messages（#6314、#6319、#6371，只在 main）；`/v1/responses` 是 `KnownGap(#6166)`。這是 Operator MCP，不是 (b) 的 MCP gateway，(b) 仍未動工。
9. **整理共用測試 helper**：conformance 的 judge／classifier helper 散在好幾支測試裡，可以收進 `harness.py`。

---

## 8. 給下一個接手者的工作方式與坑

- **多個 PR 改同一批檔案時用 merge train**：把 PR 疊成一條鏈，衝突只解一次。
  - 前一個 squash 之後，如果 `apps/gateway`、`.github`、`tests` 三個目錄的 tree 和 CI 驗過的 node 完全相同，可以直接 merge，不必重跑 CI。
  - 不相同時，要在本機對「main＋PR」的完整 tree 跑 owner suite 與 gate，通過才 merge。
- **版次與編號很容易撞**：SPEC-308 §10.x、SPEC-256 Rev.x、ADR-494 的 Q 編號、IAM migration 編號都是。後 merge 的那個負責改號。
- **把函式參數改成必填時，要搜尋 main 上所有呼叫點**。#5993 差一點讓 #6024 新增的呼叫點在執行時回 500。
- **不要用 `git stash`**：所有 worktree 共用同一份 stash。
- **本機重播 ci.yml 時跳過寫 `url.insteadOf` 的那一步**：本機的 `GH_PAT` 是空的，那一步會把空 token 寫進 `~/.gitconfig`，之後 git 全部 401。用 `git config --global --get-regexp 'url\..*insteadof'` 檢查，有就 `--unset`。
- **平行 agent 的暫存檔放在各自的子目錄**，否則會互相覆寫。
- **開 issue 一律走 `/doc-issue`，而且要 Peter 同意**。agent 不能自己開票，只能寫草稿。
- **gateway 測試**：`cd B && python3 scripts/project.py install && python3 scripts/project.py test`，約 15,800 個測試（10-14 #6526 為 15,787 passed），時間比 7 分鐘長。
  - 本機固定會紅的 gate（CI 會過）：Submodule Sanity、FinOps Columns-Parity、Audit Startup Contract、Notification Audience-Hint Parity（#6365 起）。原因都是 worktree 沒有 checkout `3rd/xparse_audit`。
- **zsh 不做 word splitting**：pytest 只印 `in 0.00s` 而沒有 passed 數字，代表一個測試都沒跑。
- **Codex 實測的工作目錄要放 `/private/tmp`**：放在家目錄底下會讀到 `~/.codex/config.toml`。
- **auth context 的測試替身**：`dataclasses.replace` 只保留宣告過的欄位，用 `setattr` 加上去的屬性過了 auth 邊界就消失（#5945 已加防護）。

---

## 9. 實測資源（本機）

- **測試腳本與結果**：`/Users/peter/Desktop/testing/`（`e2e1006_*`、`results/e2e_20261006/`）。
- **本機服務**：
  - gateway：`http://localhost:4001/v1/*`（經 console dev server 代理）
  - IAM：`http://localhost:4001/apis/iam/*`
- **金鑰**：在 `/Users/peter/Desktop/testing/.env`。
  - `XPARSE_API_KEY2`：app `5260605d-a3d8-4068-873e-b2ee5bf29c48` 的 key。
  - `XPARSE_ADMIN_KEY`：tenant_admin。
  - 程式一律從 `.env` 讀，**不要印出來，也不要寫進任何報告**。
  - 測試時不要動這個 app 的模型、政策，也不要動 tenant 層級的綁定。需要不同設定就自己建 probe app，測完清掉。
- **三個 agent CLI**：`claude`、`codex`、`opencode`，設定方式見各個 `e2e1006_*.sh`。`claude` 的 shell alias 會自動加 `--dangerously-skip-permissions`，所以腳本裡要呼叫真正的 binary。

---

## 10. 相關記憶（`~/.claude/projects/-Users-peter-Desktop-X-parse-xparse/memory/`）

- `project_llm_api_surface_restructure_draft.md`：本案摘要。
- `project_responses_surface_coupling_review.md`：前一輪 `/v1/responses` 的工作。
- 踩坑紀錄：
  - `reference_git_push_insteadof_empty_token.md`
  - `reference_git_stash_shared_across_worktrees.md`
  - `reference_codex_home_ancestor_config_leak.md`
  - `reference_auth_context_copy_drops_undeclared_attrs.md`
  - `reference_zsh_shell_traps.md`（不做 word split；`$R:a…` 會被當成 `:a` 修飾子吃掉路徑）
