# LLM API 架構重整建議（草案）

> **狀態**：草案，不是 ADR。給 Peter 決定方向用；核定後再拆成 ADR／SPEC（見 §9）。
> **日期**：2026-10-05
> **基準**：`origin/main` `3d78bf885`。文中程式路徑都相對於 xparse repo 根目錄 `/Users/peter/Desktop/X-parse/xparse`；`G/` = `apps/gateway/bustream/gateway/`。文中只寫檔名的（例如 `chat.py:1503`），完整路徑與所有來源的絕對路徑見 **§12 來源索引**。
> **依據**：[ADR-494](../../xparse/docs/adr/ADR-494-shared-dispatch-pipeline.md)（共用 pre-dispatch pipeline、每面 adapter、一個 terminal，已核定，P0–P3 已交付）· [ADR-492](../../xparse/docs/adr/ADR-492-cross-surface-governance-conformance-suite.md)（跨面 conformance）· SPEC-308 · SPEC-306。
> **外部對照**：LiteLLM（sep-29）、Bifrost、Portkey OSS 1.15.2、One-API、vLLM，原始碼都在 `~/Desktop/research/`（附錄 A）。

---

## 執行狀態（2026-10-06）

Peter 10-05 核定 §8 Q1–Q11 全照建議，範圍 M0–M9。正式文件：ADR-494 §11 Amendment A、ADR-492 Accepted＋Amendment A、ADR-479 Amendment A、SPEC-308 §10、SPEC-306 Rev.3、PRD-341（決定 D-1..D-4）、`docs/research/RESEARCH-llm-api-surface-architecture-2026-10-05.md`。本草案此後只是歷史紀錄，以上述文件為準。

| 切片 | PR | 狀態 |
|---|---|---|
| M0 設計文件 | #5901 | merged |
| M0b PRD-341＋研究＋SPEC-039 | #5908 | merged |
| M1 面登記表、未登記面 fail-closed | #5904 | merged |
| M2 處置表取代 `Stage.surfaces`、Protocol、處置 gate | #5910 | merged |
| M3 conformance 從登記表導出、執行期軌跡、gate (j)(k) | #5914 | merged |
| M4＋M9 路由覆蓋 gate、count_tokens 歸非執行 | #5909 | merged |
| M5 STARTED／非串流 FAILED 走 terminal | #5906 | merged |
| M6 embeddings 併入 | #5919 | merged |
| M7 speech／transcriptions 併入（`LEGACY_UNPIPED` 清空） | #5933 | merged |
| M8 ①–⑨ 補缺口 | #5937 #5939 #5942 #5950 #5940 #5947 #5938 #5962 #5936 | merged |
| 途中發現的 bug | #5893 #5898 #5900 #5905 #5911 #5924 #5925 #5929 | merged |

先只記錄、待 Peter 看稽核後再切換的項目（追蹤票）：Policy Kernel 403（#5941）、音訊定址與 embeddings 隱藏名稱拒絕（#5949）、transcription output rail 照政策模式（#5965）、input rail shadow→enforce（PRD-341 D-3）。另開：IAM 模型類型欄位（#5948）。總 Epic #5899。MCP gateway／A2A／Operator MCP 未動（§6「之後」）。

---

## 0. 結論

1. **不拆 service。** 繼續用「一個 gateway owner、一份治理核心、每個面一個 adapter」。五家平台沒有一家為每種 API 各開一個 service；而且在 PRD-302 share-nothing 下，另開一個 app 就不能共用治理程式碼，治理勢必寫第二份（§5.2）。
2. **真正的問題是「預設跳過」，我們自己也有。** 五家的共同漏洞，都是功能內部依 API 種類分流，遇到沒處理的種類就直接放行。我們的 `run_pre_dispatch` 也一樣：stage 不認得的面就 `continue`，認不得的面會跳過全部 stage（`G/dispatch_pipeline.py:465-467`）。INV-494-4（fail-closed）寫在 ADR 裡，但程式碼沒有實作。
3. **要補的是一張明確、窮舉、不能留白的「面 × 治理 stage」表。** 每個面對每個 stage 都要宣告「跑」、「不適用（附文件編號）」或「已知缺口（附 issue）」三選一，沒有預設值。CI 從路由表導出面的清單，再檢查這張表填滿了沒有。
4. **embeddings／audio 併進同一份核心。** 執行方式另成一個 unary 家族（一次請求、一次回應），每個 stage 依上述的表決定跑不跑。
5. **MCP 有三種意思，要分開放。**
   - Responses 裡的 hosted MCP tool：留在 Responses 面。
   - MCP gateway（agent 經 Xparse 打上游 MCP server）：在 gateway owner 內新增一個面家族。
   - Operator MCP（#1226，用 MCP 操作 Xparse 控制面）：屬於 IAM，不走推論 pipeline。
   - A2A：等選定標準再做，屆時比照 MCP gateway。

---

## 1. 成功標準與限制

| # | 標準 | 本案對應的機制 |
|---|---|---|
| S1 | 新增一個 API 面，只寫 adapter，不改治理程式碼 | 型別化的 adapter Protocol＋面登記表＋adapter 自帶處置宣告（§3.2、§3.3） |
| S2 | 新增一個治理功能，只接一次，所有面一起生效 | `PIPELINE` 只有一份；新 stage 一加，每個已登記的面都必須宣告處置，強制 stage 不得宣告不適用（§3.3） |
| S3 | 任一面漏接任一治理功能，CI 會紅，不會靜默放行 | 路由↔面登記表 gate、處置窮舉 gate、conformance 的執行期 stage 軌跡、未知的面執行期 fail-closed（§7） |

**限制**：
- **ADR-093**：拒絕都在 side-effect-free 的 stage 發生；寫入只在全部通過之後；identity 在認證 stage 綁一次（附錄 B）。
- **PRD-302 share-nothing**：跨 app 只走 HTTP 或 pinned artifact，不共用 package、不 import 其他 owner 的 private 實作。
- **未知的面一律 fail-closed**：執行期拒絕並寫稽核，同時要在 CI 就被擋下來，不能等到線上才發現。

**S1 的誠實邊界**：同一個執行家族內新增一個面，只需要寫 adapter，例如 images 屬於 unary 家族。但第一次出現的工作負載形狀（MCP 的 JSON-RPC session、A2A 的長任務）需要新增一個執行家族（§3.1 L3）。治理核心仍然不動。

---

## 2. 現況

### 2.1 每個面走哪條路

| 面 | 入口 | pre-dispatch | 執行／串流 | terminal（COMPLETED／FAILED） | conformance |
|---|---|---|---|---|---|
| `/v1/chat/completions` | `G/routes/chat.py:1057-1061` `run_pre_dispatch` | `PIPELINE` | `StreamingManagerV3`（`chat.py:1503`）；非串流 `non_streaming_handler.py` | COMPLETED 走 `G/terminal.py:110`；串流 FAILED 走 `settle_failed`（`chat_streaming_audit.py:342`）；**非串流 FAILED 自己 emit**（`non_streaming_handler.py:2000-2090`） | 有 |
| `/v1/messages` | `G/routes/messages.py:444`，經 `execute_chat` | `PIPELINE`；adapter 共用 chat 的，依路徑切換（`surface_adapters/chat.py:89-97`） | chat 的串流重新編碼成 Anthropic（`messages.py:298`） | 同 chat | 有 |
| `/v1/responses` | `G/routes/responses.py:257-262` | `PIPELINE`（含只屬此面的 `store`／`agent_mode`／`chain`） | passthrough 鏈（`responses_stream.py:725-744`） | `settle_*`（`responses_execution_audit.py:183,356`） | 有 |
| `/v1/embeddings` | `G/routes/embeddings.py:111` auth、`:175` `admit_audio` | **無** | 一次 worker 呼叫 | 自己 emit（`embeddings.py:316,453`）；直接呼叫 `record_usage_to_ledger`（`:284`） | **無** |
| `/v1/audio/transcriptions` | `G/routes/transcriptions.py:93`、`:122` | **無** | 一次 HTTP 呼叫 | `G/audio_governance.py:230,280,317`；`record_audio_usage_to_ledger`（`:273`） | **無** |
| `/v1/audio/speech` | `G/routes/tts.py:59`、`:107` | **無** | 同上 | 同上 | **無** |
| `/v1/messages/count_tokens` | `messages.py:527-630` | 只做認證（`:565`） | 不呼叫 provider | 無 | 無 |
| `/v1/models` | `G/routes/models.py:279` | 只做認證；label `Models` 跳過 PDP（`auth_handler.py:484-486`） | — | 無 | 無 |

### 2.2 哪些治理有接、哪些沒接

✅ 有接　◐ 部分　❌ 沒接　— 依設計不適用

| 治理功能 | chat／messages | responses | embeddings | transcriptions／speech | 證據 |
|---|---|---|---|---|---|
| 認證（`authenticate_request`） | ✅ | ✅ | ✅ | ✅ | `embeddings.py:111`、`transcriptions.py:93`、`tts.py:59`。transcription 的 label 不在 action 對照表裡，落到 `inference.execute`（`auth_handler.py:449-466`） |
| 請求欄位去向（ADR-493） | ✅ | ✅ | ❌ | ❌ | `G/request_fields.py:177-180` 只有三面的表 |
| policy actions（ADR-461） | ✅ | ✅ | ❌ | ❌ | `run_policy_actions`（`dispatch_stages.py:183`）在這些面不會跑；admission 沒帶 `conversation_scope`（`audio_governance.py:138-153`），所以 action 是 inert |
| Tool 規則（請求端／回應端） | ✅ | ✅ | — | — | 這些面沒有工具 |
| input rail（guardrail／PII／字詞過濾） | ✅ | ✅ | ❌ | ❌ | 三個 route 都沒有 guardrail 呼叫；embeddings 的 `input`、speech 的 `input` 都沒掃。**沒有任何文件說這是刻意排除** |
| output rail | ✅ | ✅ | — | ❌ transcription | transcript 原樣回傳（`transcriptions.py:260-282`） |
| semantic cache | ✅ | ◐ 缺口 #4247 | — | — | `dispatch_pipeline.py:419-420` |
| request policy（`streaming_allowed` 等） | ✅ | ✅ | ❌ | ❌ | — |
| 定址／可見性 | ✅ | ✅ | ◐ | ◐／❌ | embeddings 自己解析，不查 binding（`embeddings.py:330-355`）；transcription 遇到未知模型會退回預設 openai 端點（`streaming/workers/transcription_worker.py:20,54`）；speech 不查模型 |
| 預算閘 | ✅ | ✅ | ✅ | ✅ | 經 `run_admission`（`admission_handler.py:1339-1396`） |
| routing | ✅ | ✅ | ❌ 繞過 | ❌ 繞過 | label `audio_passthrough`（`audio_governance.py:55`） |
| Policy Kernel／執行邊界 | ✅ | ◐ shadow（`kernel_rollout`，#1060） | ❌ | ❌ | speech 的 provider 寫死 `"openai"`（`tts.py:79,120,134`） |
| admission／slot | ✅ | ✅ | ✅ | ✅ | `embeddings.py:175/324` |
| endpoint lease（Resource Manager） | ✅ | ✅ | ❌ | ❌ | `dispatch_stages_execution.py:444` 只在 pipeline 內 |
| idle／read deadline | ✅ | ✅ | ◐ 只有 HTTP timeout | ◐ 120s／60s | `streaming_deadline.py:137` 是共用的 |
| 稽核生命週期 | ✅ | ✅ | ◐ | ✅ | embeddings 的 FAILED 少了 `model`、`model_uuid`、`error_status_code`（`embeddings.py:450`） |
| 記帳（`TerminalUsage`） | ✅ | ✅ | ❌ 自己記 | ❌ 自己記 | `terminal.py` 與 `TerminalUsage` 都沒用到 |
| 錯誤渲染 | ✅ adapter | ✅ adapter | ◐ | ✅ | embeddings 丟掉 admission 的 response headers（`embeddings.py:186-190`） |

### 2.3 我們自己身上的「預設跳過」

以下第 1、2、9 項我已回原始碼確認；其餘來自盤點，附 file:line。

1. **pipeline 對不認得的面整條跳過。** `run_pre_dispatch` 寫的是 `if not stage.applies_to(ctx.surface) ...: continue`（`G/dispatch_pipeline.py:465-467`），`Stage.surfaces` 的預設值是 `ALL_SURFACES`（`:396`）。不在名單裡的面會跳過全部 stage、原封不動回傳 context；route 接著讀 `dispatch.auth`，變成沒有稽核的 500。INV-494-4 沒有實作，SPEC-308 的 traceability 表也沒列它。
2. **adapter 把未知路徑當 chat。** `self.surface = SURFACE_MESSAGES if endpoint_path == MESSAGES_PATH else SURFACE_CHAT`（`G/surface_adapters/chat.py:92`）。
3. **面的清單是好幾份手寫常數。**
   - conformance harness 寫死 `SURFACES = ("chat","messages","responses")`（`tests/conformance/harness.py:59`）；
   - gate 自己又寫一份（`.github/scripts/surface-conformance-gate.py:84`）；
   - `request-field-dispositions-gate.py` 的 `SURFACE_TABLES` 也只有三面（`:41-45`），快照裡出現第四面時會靜默忽略。
4. **新 route 不會讓 CI 紅。** `test_coordination_coverage.py:90-112` 要求每條 route 都要分類，但歸成 `governed` 只需要一個 admission seam 字串，不要求它跑 `run_pre_dispatch`，也不要求進 conformance。現在就有三條受治理的 route 在 pipeline 和 suite 之外（embeddings、speech、transcriptions）。
5. **gate 的範圍是「事件名稱」，不是「事件 × 面」。** embeddings 自己 emit `EXECUTION_COMPLETED`（`embeddings.py:316`），gate 把它算成已覆蓋（`surface-conformance-gate.py:117-127`）。
6. **conformance 的宣告沒有和 pipeline 對帳。**
   - 測試上標的 `gaps`／`not_applicable` 沒和 `Stage.surfaces` 比對；
   - xfail 沒有 `raises=`，缺口面因為別的原因失敗也是綠的（`tests/conformance/conftest.py:53-65`）；
   - 「哪個 stage 真的跑了」完全是宣告，執行期沒有追蹤（ADR-492 的方案 D 延後了）。
7. **terminal 的鎖是手寫清單。** `test_one_terminal.py:20-25` 只檢查 4 個檔案有呼叫 `settle_completed`，不會發現其他地方自己 emit，FAILED 也沒有鎖。
8. **還沒收乾淨的重複。**
   - `EXECUTION_STARTED` 在 4 個地方 emit：`chat.py:1590`、`non_streaming_handler.py:729`、`chat_agent_audit.py:80`、`responses_execution_audit.py:108`；
   - 非串流的 output rail 是自己組的（`non_streaming_handler.py:1107-1160`），沒用共用的 buffered rail；
   - request／trace id 的推導在兩個 route 各寫一次。
9. **embeddings 失敗時可能發兩個終端事件（讀碼確認、未實跑）。** 內層 `finally`（`embeddings.py:271-316`）無條件 emit `EXECUTION_COMPLETED`，`except` 分支又 emit `EXECUTION_FAILED`，所以一次失敗會同時有 FAILED 和 COMPLETED。`attempt_scope` 拒絕時則只有 COMPLETED。既有測試（`tests/integration/test_embeddings_audit_completed.py:238-257`）只斷言恰好一個 FAILED，沒斷言沒有 COMPLETED。
10. **agent mode 少了串流段的治理（待確認是不是刻意的）。** `routes/chat_agent.py:107-160` 沒有 output rail、idle deadline 和回應端 Tool 規則；盤點也發現它可能沒有釋放 endpoint lease（`chat.py:1473` 的 return 跳過了釋放），**需要實測確認**。
11. **文件落後程式碼。**
    - ADR-492 的 Status 還是 Proposed，但 suite 已經 merge（#5756）；
    - ADR-494 的 status 行寫「#5753 等 S6」，但已經接上了（`responses_stream.py:726`）；
    - SPEC-308 DP-4.6 還列著已實作的 #1508。

### 2.4 外部對照：五家怎麼做、漏在哪

| 平台 | 架構 | 共同漏洞的具體位置 | MCP／A2A |
|---|---|---|---|
| LiteLLM | 一個 app，共用 `base_process_llm_request`；guardrail 依 `call_type` 各配翻譯 adapter | 沒 adapter 的 call_type 直接 `return data`（`unified_guardrail.py:222-226`）；speech／transcription 手刻流程、略過 post-call hook（`proxy_server.py:12428-12551`）；內容 hook 只看 `{"completion","acompletion","aresponses"}`，漏掉 `/v1/messages`（`_content_utils.py:27,40-43`） | 兩者都有，同一個 process、同一條 pipeline，`call_type=call_mcp_tool`，有自己的翻譯 adapter（`mcp_server_manager.py:5838-5842`） |
| Bifrost | 一個 union 型別 `BifrostRequest`＋一條 plugin pipeline，連串流也共用 | 治理 plugin 的 token 計數 switch 沒寫 image／rerank／OCR／video，算成 0（`plugins/governance/main.go:1661-1683`）；plugin 錯誤只記 log（`core/bifrost.go:8675-8679`） | MCP 共用同一個 pipeline 物件，但走另一組 `PreMCPHook`（`plugins/governance/main.go:1354`）；沒有 A2A |
| Portkey OSS | 一條 `tryPost`；每個面只是一個 `fn` 字串 | `shouldSkipHook` 寫死 4 種，Responses、圖片、音訊的 guardrail 靜默跳過（`src/middlewares/hooks/index.ts:449-464`） | 都沒有 |
| One-API | 一個 binary；auth、選 channel 在 middleware | 計費在 text／image／audio helper 各寫一份，有三個寫 log 的地方；proxy 完全不計費（`relay/controller/proxy.go:17-41`） | 都沒有 |
| vLLM | 共用 `BaseServing`；Messages 是 chat 的 adapter | auth 只看路徑前綴，`/tokenize`、`/score`、`/rerank` 沒有保護（`vllm/entrypoints/serve/middleware/authenticate.py:11`） | MCP tool server 只接給 Responses |

完整的絕對路徑與行號見附錄 A。

**對本案的教訓**：
- **共用 pipeline 是必要條件，但不是充分條件。** 五家都有某種共用 pipeline，漏洞全出在「功能內的 per-surface 分流＋預設跳過」。決定性的是：沒有預設值、遇到未知 fail-closed，而且完整性由 CI 從程式碼導出。這三件事五家都沒做。
- **手刻流程的面漏最多**：LiteLLM 的音訊、One-API 的圖片與音訊、我們的 embeddings 與音訊。
- **MCP 的成熟作法**：共用治理核心，工具呼叫另配一組 stage 或 adapter，不硬套推論用的 stage。

---

## 3. 目標架構

### 3.1 三層

```
            ┌──────────────── L1 Wire adapter（每個面一個）────────────────┐
 HTTP ───▶  │ 解析 wire → 中立 SurfaceInput ｜ 候選集過濾 ｜ 中立結果 → wire  │
            └───────────────────────────────┬──────────────────────────────┘
                                            ▼
            ┌──────────────── L2 治理核心（只有一份）─────────────────────┐
            │ 面登記表 ｜ PIPELINE（順序寫死）｜ 處置表 ｜ terminal          │
            └───────────────────────────────┬──────────────────────────────┘
                                            ▼
            ┌──────────────── L3 執行家族（依工作負載形狀）───────────────┐
            │ generate-stream（chat 狀態機／Responses passthrough）          │
            │ unary（embeddings／speech／transcription／images）              │
            │ tool-invoke（MCP gateway，未來）｜ agent-task（A2A，未來）      │
            │ 只共用元件：deadline、resilience、usage 解析                    │
            └────────────────────────────────────────────────────────────────┘
```

| 層 | 負責 | 不准做 |
|---|---|---|
| **L1 adapter** | 1. 把 wire 讀成中立的 `SurfaceInput`：要送進模型的文字、工具宣告、模型參照、用量估計單位。2. 宣告自己的面描述（名稱、路徑、執行家族、處置表）。3. 依面過濾候選模型。4. 把中立的拒絕與終端渲染成自己的 wire（OpenAI、Anthropic、Responses 的形狀）。 | 做任何治理判斷；在 stage 裡讀 wire 原文。今天 chat adapter 的 reader 會退回去讀 Responses 的 reader（`surface_adapters/chat.py:182-204`），這種跨面讀取要拿掉。 |
| **L2 治理核心** | 1. 面登記表：所有可執行的面都要登記，是唯一的來源。2. `PIPELINE`：順序寫死的一份清單（ADR-494 D1 不變）。3. 處置表：面 × stage，一律明確宣告。4. terminal：`EXECUTION_STARTED`／`COMPLETED`／`FAILED` 與記帳只有一條路徑。5. 未知的面、處置沒填的格子 → fail-closed 並寫稽核。 | 知道任何 wire 形狀；依面寫 `if`。差異只能是具名的 adapter 參數（INV-494-3）。 |
| **L3 執行家族** | provider 呼叫、串流、扣住後重發、重試／fallback、deadline；把上游終端解析成 `TerminalUsage`。 | 合併不同扣住語意的串流引擎（ADR-494 §4 C 維持否決）；自己 emit 終端事件。 |

### 3.2 面登記表與型別化 adapter

- **面登記表**：一個模組列出每個可執行的面，欄位是 `name`、`path`、`family`、`adapter`、`usage_unit`。
  - FastAPI 路由、conformance 的 surface fixture、請求欄位 gate、terminal 的鎖，都從這裡導出，不再各自手寫。
  - adapter 用精確路徑查面，查不到就 raise，不再「其他一律當 chat」。
  - 登記表本身是手寫的，所以**不能拿它自己證明完整**（評審 §3.2、monorepo 規則）。它的完整性由 G3 從真 app 列舉出的路由反向比對：路由在、登記表沒有，就紅。
- **adapter Protocol**：把今天的 duck typing（`adapter: Any`＋`getattr`）改成 `typing.Protocol`（CLAUDE.md §2.2）。
  - messages 拆成自己的 adapter，不再用路徑在 chat adapter 裡切換。
  - Anthropic 的錯誤渲染從 route（`messages.py:443-454`）搬進 adapter。

### 3.3 處置表：取代 `Stage.surfaces` 的預設值

每個 stage 對每個已登記的面，必須宣告下面三種之一。**沒有預設值。**

| 處置 | 意思 | 必須附 |
|---|---|---|
| `RUN` | 這個面跑這個 stage | — |
| `NotApplicable(ref)` | 依設計不適用，例如 embeddings 沒有工具 | ADR／SPEC／PRD 編號（gate 檢查） |
| `KnownGap(issue)` | 應該跑但還沒接 | `#issue`；conformance 有對應的 strict xfail |

另有兩條規則：
- **強制 stage**：`auth`、`request_fields`、`policy_actions`、`budget`、`classifier_and_admission` 和 terminal，任何面都只能是 `RUN` 或 `KnownGap`，不能宣告不適用。這樣 adapter 作者無法靠「不適用」把治理關掉。
- **宣告放在 adapter 裡**，不放在核心：新增一個面只動 adapter（S1）。核心只保留「哪些 stage 是強制的」。gate 檢查每個 adapter 的宣告涵蓋 `PIPELINE` 的每一個 stage。

**為什麼這不是 ADR-494 §4 B 否決的「hook 登記表＋宣告式排序」**：
- §4 B 否決的是**順序**由各功能宣告、再由求解器排出來。本案的順序仍然只寫在 `PIPELINE` 一個地方，一字不改。
- 本案宣告的是**適用性**。適用性今天就已經是宣告的（`Stage.surfaces`），只是它有預設值，而且不適用時會靜默跳過。本案拿掉預設值、要求逐格填寫，並在 CI 和執行期都強制檢查。
- 也就是把 §4 B 想避免的「隱式」再往前推一步，不是走回頭路。

**執行期行為**（實作 INV-494-4）：`run_pre_dispatch` 依處置表執行。
- 面沒有登記，或某一格沒填 → 拒絕，並寫 `REQUEST_REJECTED`（`extra.reason="surface_unregistered"` 或 `"disposition_missing"`），不呼叫 provider；
- `KnownGap` → 跳過，並在 context 上記一筆 gap 軌跡；
- `NotApplicable` → 跳過，同樣記軌跡。

CI 必須在 merge 前就擋下前兩種情況，執行期的拒絕只是最後一道防線。

### 3.4 terminal 收成唯一路徑

- 三種終端事件都只能從 `G/terminal.py` emit，包括今天各處自己發的 `EXECUTION_STARTED`，以及非串流 chat 自己 emit 的 FAILED。
- `TerminalUsage` 依面的 `usage_unit` 解析：tokens、秒數、字元數，以及未來的工具呼叫次數與任務數。每個登記的面都必須有解析函式，沒有就紅。這是為了避開 Bifrost 那種 switch 漏 case、算成 0 的問題。
- embeddings／audio 的記帳改走同一個 terminal，ledger 寫入的數字和稽核事件讀同一個值（ADR-439 Amendment F 的規則延伸）。

### 3.5 對成功標準

| 標準 | 新增時要做的事 | 什麼會讓 CI 紅 |
|---|---|---|
| S1 新增面 | 寫 adapter（Protocol）＋在登記表加一列＋在 adapter 裡填處置 | 處置沒填滿；強制 stage 被宣告不適用；路由沒登記；沒有 usage 解析函式 |
| S2 新增治理功能 | 在 `PIPELINE` 加一個 stage＋寫一支跑所有已登記面的 conformance 測試 | 有 adapter 沒有宣告新 stage；stage 沒有被測試認領（rule h） |
| S3 漏接 | — | 路由在登記表外；處置宣告與執行軌跡不一致；conformance 的標記與處置不一致；終端事件不是從 terminal 發出 |

---

## 4. embeddings／audio 怎麼併入

### 4.1 作法

1. 登記三個面：`embeddings`、`audio.speech`、`audio.transcriptions`，執行家族都是 `unary`。
2. 各寫一個 adapter：
   - 中立文字：embeddings 是 `input`（字串或陣列）；speech 是 `input`；transcription 的輸入是音訊，選填的 `prompt` 算文字，輸出的 transcript 交給 output rail。
   - 候選集：只看 embedding／TTS／STT 模型。
   - 渲染：OpenAI envelope，**保留** admission 的 response headers。
   - `usage_unit`：tokens／字元／秒。
3. **第一片行為不變**：今天沒接的 stage 一律先宣告 `KnownGap(#issue)`。所以「併入 pipeline」本身不改變任何行為，之後每補一個缺口就是一個獨立的 PR，並各自宣告行為變更（比照 ADR-494 §9 第 3 項）。

### 4.2 建議的處置（待 Peter 決定的標 Q）

| stage | embeddings | speech | transcriptions | 備註 |
|---|---|---|---|---|
| auth | RUN | RUN | RUN | 強制 |
| request_fields | RUN | RUN | RUN | 強制；需要新的去向表與 SDK 快照 |
| session | 不適用 | 不適用 | 不適用 | 沒有多輪對話（ADR-447） |
| policy_actions | RUN | RUN | RUN | 強制；今天是 inert |
| tool_results／tool_rules | 不適用 | 不適用 | 不適用 | 沒有工具（ADR-490） |
| input_rail | **Q3** | **Q3** | prompt 跑、音訊不適用 | embeddings 的 PII 會進客戶的向量庫，是最實際的外洩點 |
| semantic_cache | 不適用 | 不適用 | 不適用 | ADR-054 只針對生成 |
| request_policy | RUN | RUN | RUN | — |
| store／agent_mode／chain | 不適用 | 不適用 | 不適用 | PRD-157、ADR-437 D5 |
| addressing | RUN | RUN | RUN | 取代各自的解析；transcription 的未知模型會從「退回預設」變成 404（行為變更） |
| budget | RUN | RUN | RUN | 強制；今天已經有 |
| routing | **Q5** | **Q5** | **Q5** | 建議 v1 不適用，引用本案核定後的 ADR |
| policy_kernel | RUN | RUN | RUN | speech 的 `"openai"` 寫死要拿掉 |
| classifier_and_admission | RUN | RUN | RUN | 強制；今天已經有 |
| endpoint_lease | RUN | RUN | RUN | 只有地端端點才有實際作用 |
| output rail（L3） | 不適用 | 不適用 | **Q4** | 屬於串流／執行段，由 unary 家族提供 |

### 4.3 要先修的 bug

embeddings 的雙終端事件（§2.3 第 9 項）要**在併入之前**單獨修，走 `/flow-bugfix`。理由是：併入那一片承諾行為不變，不能夾帶修 bug。修之前先寫一支跑真 route 的測試，證明 COMPLETED 真的會在失敗時發出（CLAUDE.md §8.1），再改。

---

## 5. MCP／A2A 放哪

### 5.1 先分清三種 MCP

| | 誰呼叫誰 | 平面 | 現況 |
|---|---|---|---|
| **(a) Responses 裡的 hosted MCP tool** | client 在 `tools` 帶 `{"type":"mcp","server_url":...}`，由 provider 去呼叫 MCP server | Runtime（現有的 Responses 面） | 今天整個剝除（`G/responses_tools_filter.py:57-66` 的 `PROVIDER_HOSTED_TYPES`）；開放的設計在 ADR-490 v2 的 `allow_server_urls` |
| **(b) MCP gateway** | agent 經 Xparse 打上游 MCP server（`tools/list`、`tools/call`） | Runtime（新的面家族） | 沒有程式碼；#1104（已關閉）留下「只當 registry，還是也代理執行」這題，#1226 主張也代理執行，但還沒定案 |
| **(c) Operator MCP**（#1226） | agent 用 MCP tools 操作 Xparse 控制面（建租戶、改 policy），寫入要 HITL 核可 | Governance／Control（IAM） | discussion 階段 |
| A2A（#1107） | agent 之間委派任務 | Runtime（新的面家族） | discussion 已以 outdated 關閉，標準未定 |

### 5.2 放哪、為什麼

- **(a)** 留在 Responses 面。由 Tool 規則 stage 判定，不另開面。
- **(b) MCP gateway** 放在 **gateway owner（`apps/gateway`）內**，作為新的執行家族 `tool-invoke`：
  - 有自己的 route（`/mcp`，Streamable HTTP）、adapter 與 JSON-RPC session 管理；
  - 共用同一份 `PIPELINE`、處置表和 terminal。
  - **為什麼不另開一個 app**：PRD-302 禁止跨 owner 共用 package 或 import private 實作。另開的 MCP app 不能 import gateway 的治理核心，只剩兩條路：自己重寫一份治理（違反 S2，就是 ADR-494 要消除的「兩份編排」），或每個 stage 都經 HTTP 問 gateway（多一跳，而且等於另造一個治理 API）。
  - 要不要拆 process 是部署層的事：同一個 image、不同的路由 allowlist，就像 LiteLLM 把 `/mcp` 放在 backend plane（`gateway/main.py:33-67`、`backend/routes/allowlist.py:152,159`）。程式碼不用分家。
- **(c) Operator MCP** 屬於 **IAM（控制面 owner）**：
  - 它操作的是管理 API，治理是 IAM 的授權加 HITL，加上 ADR-093 的五步（dry-run → 核可 → atomic commit → 重讀驗證 → 稽核）；
  - 不走推論 pipeline，也不碰預算或 routing；
  - 驅動它的模型呼叫本身照常走 gateway，所以已經受治理。
- **A2A**：選定標準之後，比照 (b) 在 gateway owner 內新增執行家族 `agent-task`。額外的重點是委派鏈的 identity binding（ADR-093 inv 5）：`on_behalf_of` 鏈在邊界綁一次，之後不得替換。

### 5.3 (b)／A2A 跟推論 pipeline 共用什麼、不共用什麼

| 共用（同一份實作） | 不共用 |
|---|---|
| 認證（IAM validate）、請求欄位去向、policy actions、預算閘、admission／並發、稽核生命週期、terminal 與記帳（單位是工具呼叫次數或任務數）、面登記表、處置表、conformance | 定址、routing、semantic cache（沒有模型）；串流引擎；session 狀態（MCP session id、A2A task id 屬於各自的執行家族） |
| **待定（Q7）**：input／output rail 套在工具參數與工具結果上（LiteLLM 有做）；Policy Kernel 的資料邊界套在上游 MCP server 的位置上 | 只屬工具的 stage：上游 server allowlist（ADR-490 v2）、單一工具呼叫頻率。這些加進同一份 `PIPELINE`，推論面一律宣告不適用 |

---

## 6. 遷移切片

每一片都可以獨立 merge，對 client 的行為不變（INV-494-1）。標「行為變更」的片各自一個 PR，並各自宣告。

| # | 內容 | 行為 | 前提 |
|---|---|---|---|
| M0 | 文件：ADR-494 Amendment（面登記表、處置表、unary 家族、INV-494-4 的實作）＋SPEC-308 修訂；ADR-492 Amendment（面清單從登記表導出、範圍改成「事件 × 面」、執行期軌跡） | 無 | 本草案核定 |
| M1 | 面登記表＋adapter 用精確路徑查面；`run_pre_dispatch` 對未登記的面 fail-closed 並寫稽核 | 現有三面不變；未登記的面原本是沒有稽核的 500，改成有稽核的拒絕 | M0 |
| M2 | 處置表取代 `Stage.surfaces`：三面的處置照今天的行為填（`store` 對 chat 不適用；`semantic_cache` 對 responses 是 `KnownGap(#4247)`）；adapter 改成 Protocol；messages 拆出自己的 adapter | 不變 | M1 |
| M3 | conformance 改版：surface fixture 從登記表導出；gate rule (g) 讀登記表；範圍改成「事件 × 面」；xfail 加 `raises=`；harness 記錄執行期 stage 軌跡並和處置比對；標記和處置對帳 | 純測試 | M2 |
| M4 | 路由 gate：每個 `POST /v1/*`（之後加 `/mcp`）若不是已登記的面，就必須歸類為「非執行」並附文件編號（例如 `/v1/models`、`/v1/usage`）。embeddings／audio 暫時列為 `legacy_unpiped`，附 tracking issue，名單只能縮小（零成長） | 純 CI | M1 |
| M5 | terminal 唯一化：`EXECUTION_STARTED` 收成一處；非串流 FAILED 改走 `settle_failed`；`test_one_terminal` 改成 AST 掃描「誰 emit 終端事件」，並涵蓋 FAILED | 不變（事件內容逐位元相同） | — |
| M6a | **bugfix**：embeddings 雙終端事件 | **行為變更** | — |
| M6 | embeddings adapter＋unary 家族；沒接的 stage 一律 `KnownGap`；記帳改走 terminal；從 `legacy_unpiped` 移除 | 不變 | M2、M5、M6a |
| M7 | speech、transcriptions 同 M6 | 不變 | M6 |
| M8… | 逐一補缺口，每個缺口一個 PR：policy_actions → request_fields → addressing → policy_kernel → endpoint_lease → input rail（Q3）→ transcription output rail（Q4） | **各自宣告行為變更** | M6／M7 |
| M9 | `count_tokens`：登記成面（大多數 stage 不適用），或歸類為非執行（Q6） | 依決定 | M4 |
| 之後 | MCP gateway（先寫 PRD／ADR）；A2A（先選標準） | — | M1–M5 |

**為什麼 M1–M5 排在 embeddings 之前**：先讓「漏接會紅」成立，再把新的面搬進來。否則搬的過程本身就沒有回歸網。

**開工時機**：`/v1/responses` 第二輪（W1–W16）已 merge，但還沒部署到 rel，也還沒重跑 `responses_gap_probe.py`（`docs/進行中/v1-response-checklist.md` §0、§D）。M1–M5 會動到同一批檔案（`dispatch_pipeline.py`、`surface_adapters/`、`terminal.py`、conformance harness），建議等第二輪在 rel 驗完再開 M1，這樣 probe 比的是穩定的基準。

**M3、M5 的注意事項**：
- M3 改 harness 時，要保留第二輪加進 fake provider 的形狀：`incomplete`、`failed`、文字加工具呼叫混在同一輪（評審 §8.2 第 2 點）。
- M5 把非串流 FAILED 改走 `settle_failed` 時，兩邊的順序不同：今天是「記帳 → 事件；健康由呼叫端記」，`settle_failed` 是「健康 → log → 記帳 → 事件」（SPEC-308 §9.1）。要比照 P3c 附中性證明。

---

## 7. 防回歸機制

| # | 機制 | 鎖什麼 | 種類 | 對應 |
|---|---|---|---|---|
| G1 | 面登記表是唯一來源 | 路由、conformance fixture、請求欄位 gate、terminal 鎖都從同一張表導出，不再有手寫的面清單 | AST／import 測試 | S1、S3 |
| G2 | 處置窮舉 gate | 每個「已登記面 × `PIPELINE` stage」恰好一個處置；強制 stage 不得宣告不適用；不適用必附文件編號；缺口必附 `#issue` | stdlib AST，跑在 Static Gates | S2、S3 |
| G3 | 路由覆蓋 gate | 每條會執行的 route 都經過 `run_pre_dispatch`，否則必須歸類為非執行並附理由 | 延伸 `test_coordination_coverage` | S3 |
| G4 | conformance＋執行期軌跡 | 每個 stage 至少一支測試；每支測試跑所有已登記的面；**實際跑到的 stage 等於宣告的處置**（真元件，不是宣告；呼應 CLAUDE.md §8.1） | gateway owner suite | S3 |
| G5 | 單一 terminal | 只有 `G/terminal.py` emit 三種終端事件；每個家族都以 `settle_*` 結束 | AST | S2 |
| G6 | 執行期 fail-closed | 未登記的面、缺處置 → 拒絕＋稽核 | 單元測試＋植入回歸 | S3 |
| G7 | usage 解析窮舉 | 每個 `usage_unit` 都有解析函式；不認得的終端形狀要紅，不能算成 0 | 單元測試 | S2 |

- 每個 gate 都要有 `--self-test`，並先看它對植入的回歸變紅過，才算數（CLAUDE.md P4）。
- G1、G2、G5 是純 stdlib 的靜態檢查，CI 成本可忽略；G4 沿用現有的 gateway owner suite。
- **G4 是 S3 能不能成立的關鍵**：沒有執行期軌跡的話，處置表只是另一份宣告。宣告和實際行為可以不一致，綠燈照樣亮（所以 ADR-492 延後的方案 D 這次要做）。

---

## 8. 需要你決定的問題

| # | 問題 | 選項 | 建議 |
|---|---|---|---|
| Q1 | 處置宣告放哪 | (A) 放在各 adapter，核心只標哪些是強制 stage；(B) 核心一張總表 | **A**：S1 字面要求「不改治理程式碼」；強制 stage 的規則守住「不准關掉治理」 |
| Q2 | `PIPELINE` 是一份還是每個家族各一份 | (A) 一份，含所有家族的 stage；(B) 每個家族一份清單，共用 stage 實作 | **A**：B 會讓新功能要接好幾次，違反 S2。等 MCP 的順序真的和推論衝突時再拆 |
| Q3 | embeddings／speech 要不要跑 input rail | 跑（先 shadow，再 enforce）／不跑（寫成不適用並附理由） | **跑，先 shadow**：embeddings 的 PII 會進客戶的向量庫 |
| Q4 | transcription 的輸出要不要過 output rail | 跑／不適用 | 跑，比照 chat 的非串流 |
| Q5 | embeddings／audio 要不要 routing | v1 不適用／接 `routing_objective` | v1 不適用 |
| Q6 | `count_tokens` | 登記成面／歸類為非執行 | 非執行：不呼叫 provider、不記帳 |
| Q7 | MCP 的產品優先序 | (a)／(b)／(c) 哪個先；(b) 要不要對工具參數與結果跑 rail | 先 (a)（ADR-490 v2 已有設計），(b) 等「也代理執行」正式定案後再做（#1104 已關閉，這題目前掛在 #1226） |
| Q8 | A2A | 現在設計／等標準 | 等標準；先保留 `agent-task` 家族的位置 |
| Q9 | 文件形式 | ADR-494 Amendment／新 ADR；ADR-492 要不要改 Accepted | ADR-494 Amendment A（是同一個決策的延伸）＋ADR-492 Accepted 並出 Amendment |
| Q10 | agent mode 少了串流段的治理 | 缺口／依設計 | 先實測 lease 釋放；output rail 若無依據就標缺口 |
| Q11 | 未登記面的拒絕狀態碼 | 500（程式錯誤）／503 | 500，加稽核 `surface_unregistered`；CI 應該讓它在線上永遠不發生 |

---

## 9. 之後要寫的文件

| 類型 | 文件 | 內容 |
|---|---|---|
| ADR | ADR-494 Amendment A | 面登記表、處置表（取代 `Stage.surfaces` 的預設值）、強制 stage、unary 家族、INV-494-4 的實作、Protocol adapter |
| ADR | ADR-492 Amendment | 面清單從登記表導出；範圍改成「事件 × 面」；執行期 stage 軌跡（方案 D 轉為採用） |
| ADR | ADR-479 Amendment | audio 從「audit＋admission」擴成走完整核心 |
| ADR | MCP 放置 ADR（新） | §5 的 (a)／(b)／(c) 分界；(b) 在 gateway owner 內的理由（PRD-302） |
| PRD | 非對話面治理一致性（新） | embeddings／audio 補上 guardrail、定址、執行邊界後，客戶看得到的變化與 §4 驗收條件；附白話層（CLAUDE.md §17.1b） |
| PRD | MCP gateway、Operator MCP（新，各一份） | 從 #1104、#1226 收斂 |
| SPEC | SPEC-308 修訂 | 處置契約、登記表、fail-closed 契約；補上 INV-494-4／-6 的 traceability |
| SPEC | SPEC-306 修訂 | harness 從登記表導出、軌跡比對；刪除 `:23` 對 embeddings／audio 的排除 |
| SPEC | SPEC-039 修訂 | embeddings 的錯誤 headers 與終端事件 |
| 研究 | `docs/research/RESEARCH-llm-api-surface-architecture-*.md` | 附錄 A 的五家證據（file:line） |

**Core 對比（預估）**：

| 領域 | Core 文件 | 關係 |
|---|---|---|
| 01 Gateway & Streaming | Core-ADR-01 | extends ADR-494、ADR-492 |
| 02 Policy & Authorization | Core-ADR-02 | extends：policy actions 與 Kernel 套到新的面；政策語意不變 |
| 04 Audit & Observability | Core-ADR-04 | extends：終端事件單一路徑；新增 `surface_unregistered` |
| 13 FinOps | Core-PRD-13 | extends：usage 單位窮舉 |
| 03 IAM | Core-ADR-03 | Operator MCP 落點（新 ADR 時） |

---

## 10. Out of scope

- 合併串流引擎（ADR-494 §4 C 維持否決）。
- 宣告式排序或 hook 登記表（ADR-494 §4 B 維持否決，理由見 §3.3）。
- 為每個面拆成獨立的 service 或 app。
- 「全部轉成 chat」的萬用中立格式，以及 Responses 與 chat 互相橋接。
- commit point 延後（ADR-494 §9 第 4 項）。
- Realtime／WebSocket 面（目前沒有；未來新增時照本案的規則登記）。
- 音訊計價（ADR-479 的 follow-up）。
- Operator MCP 的 HITL 細節（在它自己的 PRD）。
- 改變任何政策語意：本案只改「誰會被套用」，不改「怎麼判」。

---

## 11. 與 `/v1/responses` 兩輪修補的關係

本案接在同一條決策鏈的後面：〈解決 `/v1/responses` 的結構性落後〉Rev.2 → 評審 → ADR-492／ADR-494 → S1–S6 與 W1–W16。沒有推翻其中任何一個決定。

| 既有文件的內容 | 本案的處理 |
|---|---|
| 草案 §6.4 hook 登記表＋宣告式排序 | 評審 §3.1 與 ADR-494 §4 B 已否決；本案維持否決 |
| 草案 §6.7 API 面對齊登記表（手寫 YAML，四種狀態） | 評審 §3.2 改成「從測試導出、會紅」。本案的處置表是同一個想法的延伸：放在程式碼裡，執行期照它跑，並用 G4 的執行軌跡對帳。草案的 `observe_only` 不另設狀態，維持 ADR-494 D3 的具名參數（例如 `kernel_rollout`） |
| 草案 §6.7 Rev.2 第 3 條「解不出 API 面時一律 fail-closed」 | 就是 INV-494-4；本案 M1 實作它 |
| 草案 §6.6 依 API 面的能力旗標 | 評審 §3.3 改成「依請求 × client」；本案不碰 |
| 草案 Q6：embeddings／audio 要不要納入 | 本案 §4 回答：要，跑子集 |
| 草案 §6.9 未知欄位預設轉送 | 評審 §2.3 推翻，S3 定為記錄後剝除；本案要求 embeddings／audio 也照這個規則建去向表 |
| 第二輪決定 C1–C3、W1–W16 | 不動 |
| 清單 §D：#1060 維持 shadow、#4247 延後 | 在處置表裡分別是具名參數與 `KnownGap(#4247)`，不改變 |

## 12. 來源索引

> 給接手的 agent：本文每一個事實都可以從下面的路徑查回去。2026-10-05 對 `origin/main` `3d78bf885` 逐一確認存在。

### 12.0 怎麼讀

- repo 根目錄：`/Users/peter/Desktop/X-parse/xparse`。
- 先跑 `git fetch origin && git rev-list --count HEAD..origin/main`。結果不是 0，本機的樹就是舊的，改用 `git show "origin/main:<path>"` 讀，或從 `origin/main` 開 worktree。
- zsh 裡 `git show $SHA:apps/...` 的 `:a` 會被吃掉，要加引號或寫 `${SHA}:apps/...`。
- 行號會漂移，引用前先 grep 函式名稱，不要只信行號。

### 12.1 Gateway 程式（相對於 repo 根目錄）

| 路徑 | 本文引用的內容 |
|---|---|
| `apps/gateway/bustream/gateway/dispatch_pipeline.py` | `PIPELINE`（`_build_pipeline` :402-444）、`Stage.surfaces` 預設值（:396）、`run_pre_dispatch` 的跳過邏輯（:465-467）、`ALL_SURFACES`（:39） |
| `apps/gateway/bustream/gateway/dispatch_stages.py` | `run_policy_actions`（:183） |
| `apps/gateway/bustream/gateway/dispatch_stages_execution.py` | endpoint lease（:444） |
| `apps/gateway/bustream/gateway/surface_adapters/__init__.py` | `SurfaceParams`（:20-70）、`KnownGap`（:73-97） |
| `apps/gateway/bustream/gateway/surface_adapters/chat.py` | 用路徑切 chat／messages（:89-97，:92）、reader 退回 Responses（:182-204）、`known_gaps`（:82） |
| `apps/gateway/bustream/gateway/surface_adapters/responses.py` | `known_gaps`（:72）、`kernel_rollout`（:68） |
| `apps/gateway/bustream/gateway/routes/chat.py` | 進 pipeline（:1057-1061）、`StreamingManagerV3`（:1503）、`EXECUTION_STARTED`（:1590）、agent mode 的 return（:1473） |
| `apps/gateway/bustream/gateway/routes/messages.py` | 進 `execute_chat`（:444）、Anthropic 錯誤渲染（:443-454）、串流轉碼（:298）、`count_tokens`（:527-630） |
| `apps/gateway/bustream/gateway/routes/responses.py` | 進 pipeline（:257-262） |
| `apps/gateway/bustream/gateway/routes/embeddings.py` | auth（:111）、`admit_audio`（:175）、直接記帳（:284）、內層 `finally` 的 COMPLETED（:271-316）、`_emit_execution_failed`（:450）、自己的模型解析（:330-355）、丟 headers（:186-190） |
| `apps/gateway/bustream/gateway/routes/transcriptions.py` | auth（:93）、admission（:122）、transcript 原樣回傳（:260-282） |
| `apps/gateway/bustream/gateway/routes/tts.py` | auth（:59）、admission（:107）、provider 寫死 `"openai"`（:79,120,134） |
| `apps/gateway/bustream/gateway/routes/models.py` | auth label `Models`（:279） |
| `apps/gateway/bustream/gateway/routes/chat_agent.py` | agent mode 沒有串流段治理（:107-160） |
| `apps/gateway/bustream/gateway/routes/chat_agent_audit.py` | `EXECUTION_STARTED`（:80） |
| `apps/gateway/bustream/gateway/routes/chat_streaming_audit.py` | 串流 FAILED 走 `settle_failed`（:342） |
| `apps/gateway/bustream/gateway/non_streaming_handler.py` | `EXECUTION_STARTED`（:729）、自組的 output rail（:1107-1160）、自己 emit FAILED（:2000-2090） |
| `apps/gateway/bustream/gateway/responses_stream.py` | Responses passthrough 鏈（:725-744） |
| `apps/gateway/bustream/gateway/responses_execution_audit.py` | `EXECUTION_STARTED`（:108）、`settle_*`（:183,356） |
| `apps/gateway/bustream/gateway/responses_tools_filter.py` | `PROVIDER_HOSTED_TYPES` 含 `"mcp"`（:57-66） |
| `apps/gateway/bustream/gateway/terminal.py` | 唯一的 COMPLETED emit（:110） |
| `apps/gateway/bustream/gateway/terminal_usage.py` | `TerminalUsage` |
| `apps/gateway/bustream/gateway/audio_governance.py` | audio 的 admission 與稽核（:138-153、:230、:273、:280、:317），label `audio_passthrough`（:55） |
| `apps/gateway/bustream/gateway/admission_handler.py` | `run_admission` 的預算閘（:1339-1396） |
| `apps/gateway/bustream/gateway/auth_handler.py` | action 對照表（:449-466）、`Models` 跳過 PDP（:484-486） |
| `apps/gateway/bustream/gateway/request_fields.py` | 去向表只有三面（:177-180） |
| `apps/gateway/bustream/gateway/streaming_deadline.py` | 共用的 idle deadline（:137） |
| `apps/gateway/bustream/streaming/workers/transcription_worker.py` | 未知模型退回預設端點（:20,54） |
| `apps/gateway/bustream/production/coordination/coverage.py` | route 分類 `ROUTES`（:64-99） |

### 12.2 測試與 CI gate（相對於 repo 根目錄）

| 路徑 | 本文引用的內容 |
|---|---|
| `apps/gateway/bustream/tests/conformance/harness.py` | 寫死的 `SURFACES`（:59） |
| `apps/gateway/bustream/tests/conformance/conftest.py` | surface fixture（:68-70）、gap → strict xfail（:53-65） |
| `apps/gateway/bustream/tests/contract/test_dispatch_pipeline_order.py` | DP-5.1 順序測試 |
| `apps/gateway/bustream/tests/contract/test_one_terminal.py` | 手寫的 `COMPLETED_SETTLERS`（:20-25） |
| `apps/gateway/bustream/tests/contract/test_coordination_coverage.py` | 每條 route 都要分類（:90-112） |
| `apps/gateway/bustream/tests/integration/test_embeddings_audit_completed.py` | 只斷言一個 FAILED（:238-257） |
| `apps/gateway/bustream/gateway-ci-suite.txt` | 新測試檔要登記在這裡 |
| `.github/scripts/surface-conformance-gate.py` | rule (a)–(i)、寫死的 `SURFACES`（:84）、範圍取自稽核事件（:117-127） |
| `.github/scripts/request-field-dispositions-gate.py` | 只認三面的 `SURFACE_TABLES`（:41-45） |
| `.github/scripts/usage-ledger-surface-parity-gate.py` | emit COMPLETED 就必須記帳 |
| `.github/scripts/provider-call-usage-parity-gate.py` | 呼叫 provider 就必須記帳 |
| `apps/gateway/bustream/scripts/sdk-request-params.v1.json` | SDK 請求欄位快照 |

### 12.3 設計文件（相對於 repo 根目錄）

| 路徑 | 用途 |
|---|---|
| `docs/adr/ADR-494-shared-dispatch-pipeline.md` | 本案的基礎：D1–D8、§4 否決的方案、INV-494-1..6 |
| `docs/spec/SPEC-308-shared-dispatch-pipeline-contracts.md` | stage 清單、`DispatchContext`、§9 terminal 的 T-1..T-7 |
| `docs/adr/ADR-492-cross-surface-governance-conformance-suite.md` | conformance 的範圍與 gate；Status 仍是 Proposed |
| `docs/spec/SPEC-306-cross-surface-governance-conformance-contracts.md` | `:23` 把 embeddings／audio 排除在 suite 外 |
| `docs/adr/ADR-493-request-field-dispositions.md` | 請求欄位去向 |
| `docs/adr/ADR-479-audio-surface-governance-parity.md` | audio 目前只做 audit＋admission |
| `docs/adr/ADR-038-openai-embeddings-api-boundary.md`、`docs/spec/SPEC-039-openai-embeddings.md` | embeddings 的契約 |
| `docs/adr/ADR-437-responses-surface-governance-parity-phase2.md`、`docs/spec/SPEC-282-responses-governance-parity-behavioral-contracts.md` | Responses 面（D5 agent mode、D7 已由 ADR-494 修訂） |
| `docs/adr/ADR-339-responses-streaming-fidelity-transparent-passthrough.md` | Responses 串流保真（不合併串流的理由） |
| `docs/adr/ADR-280-gateway-chat-governance-service-extraction.md` | 「service」指行程內模組，不是另一個 process |
| `docs/adr/ADR-490-tool-governance-policy-kind.md` | Tool 規則；v2 的 `allow_server_urls`；替代方案 G（工具執行邊界屬 Plane 5） |
| `docs/adr/ADR-461-policy-actions-kind-agnostic-consequence-layer.md` | policy actions |
| `docs/adr/ADR-447-session-affinity-pre-resolver-candidate-freeze.md` | session |
| `docs/adr/ADR-054-semantic-cache-architecture.md` | semantic cache |
| `docs/adr/ADR-439-wasted-spend-visibility-instrumentation.md`、`docs/spec/SPEC-284-wasted-spend-visibility-behavioral-contracts.md` | Amendment F：終止用量一處解出 |
| `docs/adr/ADR-423-budget-usage-durable-ledger-retry-then-reject-accept.md`、`docs/spec/SPEC-302-single-metering-record-and-pricer-behavioral-contracts.md` | 記帳 |
| `docs/adr/ADR-243-five-plane-architecture-and-sandbox-execution-plane.md` | 五個平面 |
| `docs/adr/ADR-093-execution-safety-invariants.md` | 附錄 B 的五條 invariant |
| `docs/prd/PRD-157-responses-api-phase1-gateway-governed.md` | `store`、`chain` 只屬 Responses |
| `docs/prd/PRD-302-share-nothing-monorepo-migration.md` | share-nothing（§5.2 的理由） |
| `docs/prd/PRD-041-audit-log-sdk-integration.md` | 稽核 fail-open 的例外 |
| `docs/spec/SPEC-032-policy-kernel-v1.4.md` | Responses 上 Kernel 預設 shadow（§10.1.2） |
| `docs/adr/core/Core-ADR-01-Gateway-Streaming.md`、`Core-ADR-02-Policy-Authorization.md`、`Core-ADR-03-IAM-Identity.md`、`Core-ADR-04-Audit-Observability.md` | §9 的 Core 對比（都在 `docs/adr/core/`） |
| `docs/prd/core/Core-PRD-13-FinOps-Cost-Governance.md` | §9 的 Core 對比 |
| `docs/PROJECT_ROADMAP.md` | §18 MCP 願景、§19.3 L2 Tool Policy（#1226） |
| `docs/knowledge_base/23_system_architecture_recovery_guide.md` | 架構重建入口 |

### 12.4 repo 外的相關文件（絕對路徑）

| 路徑 | 關係 |
|---|---|
| `/Users/peter/Desktop/X-parse/docs/草案/解決-v1-response.md` | 上游草案 Rev.2：§6.4 hook 登記表、§6.7 對齊登記表、Q6 embeddings／audio |
| `/Users/peter/Desktop/X-parse/docs/草案/解決-v1-response-評審.md` | 評審：§3.1 共用 pipeline、§3.2 conformance 先行、§8 落地後複查 |
| `/Users/peter/Desktop/X-parse/docs/進行中/v1-response.md` | `/v1/responses` 兩輪的進度 |
| `/Users/peter/Desktop/X-parse/docs/進行中/v1-response-checklist.md` | 第二輪 W1–W16 的工作清單（§6 開工時機的依據） |

### 12.5 實測腳本與結果（絕對路徑）

| 路徑 | 用途 |
|---|---|
| `/Users/peter/Desktop/testing/responses_gap_probe.py` | 第二輪的重跑實測（`cost`／`schema`／`routing`／`guardrail`） |
| `/Users/peter/Desktop/testing/results/responses_gap_probe/REPORT-2026-10-05.md` | 第二輪實測報告 |

### 12.6 外部平台原始碼（絕對路徑）

| 平台 | 根目錄 |
|---|---|
| LiteLLM | `/Users/peter/Desktop/research/lite-llm/litellm-versions/litellm-sep-29` |
| Bifrost | `/Users/peter/Desktop/research/bifrost/bifrost-2026-10-05` |
| Portkey OSS 1.15.2 | `/Users/peter/Desktop/research/gateway` |
| One-API | `/Users/peter/Desktop/research/one-api/2026-10-05` |
| vLLM | `/Users/peter/Desktop/research/vllm-version/vllm-2026-10-05` |

每個檔案的絕對路徑、行號、證明什麼、本文用在哪，見附錄 A。

### 12.7 GitHub（`futurenestit/xparse`）

- Discussions：#1226 Operator MCP（open）、#1107 A2A（closed，outdated）、#1104 MCP 與 AI Artifact Registry 願景（closed）。
- Issues：#4247（Responses semantic cache）、#1060（Responses 執行邊界 shadow → enforce）、#5753、#5754、#5751、#1508、#5756（ADR-492 suite）。

### 12.8 本文的衍生物

| 路徑 | 內容 |
|---|---|
| `/Users/peter/Desktop/X-parse/docs/草案/LLM-api-重構-assets/llm-api-architecture.html` | 給 senior 看的架構頁（已發佈：https://claude.ai/artifact/WpFTtsnfgzeCiNwevDVez6） |
| `/Users/peter/Desktop/X-parse/docs/草案/LLM-api-重構-assets/gen_architecture_page.py` | 產生上面那個 HTML 的腳本：改內容就改這支，再跑 `python3 gen_architecture_page.py` |
| `/Users/peter/.claude/projects/-Users-peter-Desktop-X-parse-xparse/memory/project_llm_api_surface_restructure_draft.md` | 本案的 memory 筆記 |
| `/Users/peter/.claude/projects/-Users-peter-Desktop-X-parse-xparse/memory/project_responses_surface_coupling_review.md` | `/v1/responses` 評審與切片的 memory 筆記 |

---

## 附錄 A：外部平台證據

> 2026-10-05 逐一確認：每個檔案都存在，而且標的符號就在所寫的行號附近（腳本比對）。其中 Portkey 的 `shouldSkipHook`、LiteLLM 的 `return data`、Bifrost 的計數 switch 三處，我另外讀過原始碼全文。標「MCP／A2A 參考」的列，本文沒有直接引用，但之後設計 §5 的 (b) MCP gateway 或 A2A 時值得先讀。

### A.1 LiteLLM（sep-29）

根目錄：`/Users/peter/Desktop/research/lite-llm/litellm-versions/litellm-sep-29`

| 檔案（絕對路徑:行號） | 證明什麼 | 本文用在哪 |
|---|---|---|
| `/Users/peter/Desktop/research/lite-llm/litellm-versions/litellm-sep-29/litellm/proxy/guardrails/guardrail_hooks/unified_guardrail/unified_guardrail.py:222-226` | 沒有翻譯 adapter 的 call_type 直接 `return data`（fail-open） | §2.4 |
| `/Users/peter/Desktop/research/lite-llm/litellm-versions/litellm-sep-29/litellm/proxy/guardrails/_content_utils.py:27,40-43` | 內容 hook 只認 `completion`／`acompletion`／`aresponses`；註解自承漏掉 `anthropic_messages`、`responses`、`call_mcp_tool` | §2.4 |
| `/Users/peter/Desktop/research/lite-llm/litellm-versions/litellm-sep-29/litellm/proxy/common_request_processing.py:2452` | 所有面共用的 `base_process_llm_request` | §2.4 |
| `/Users/peter/Desktop/research/lite-llm/litellm-versions/litellm-sep-29/litellm/proxy/proxy_server.py:12428-12551` | transcription endpoint 手刻流程，不呼叫 `post_call_success_hook` | §2.4 |
| `/Users/peter/Desktop/research/lite-llm/litellm-versions/litellm-sep-29/litellm/proxy/hooks/prompt_injection_detection.py:163-176` | prompt injection 偵測只接受 chat／text completion，Responses、Messages 落到 `return data` | §2.4 的同類例子 |
| `/Users/peter/Desktop/research/lite-llm/litellm-versions/litellm-sep-29/litellm/llms/__init__.py:83-126` | 掃描各 provider 的 `guardrail_translation` 建出 call_type → adapter 對照表 | §2.4（「依面配 adapter」的實作） |
| `/Users/peter/Desktop/research/lite-llm/litellm-versions/litellm-sep-29/litellm/responses/main.py:427-431` | provider 沒有 Responses 設定時才橋接到 chat | §2.4（橋接，本案不採用） |
| `/Users/peter/Desktop/research/lite-llm/litellm-versions/litellm-sep-29/litellm/llms/anthropic/pass_through/messages/handler.py:581-612` | Messages 依 provider 走原生、轉 Responses 或轉 chat | §2.4（橋接，本案不採用） |
| `/Users/peter/Desktop/research/lite-llm/litellm-versions/litellm-sep-29/litellm/proxy/_experimental/mcp_server/mcp_server_manager.py:5838-5842` | MCP 工具呼叫走同一個 `pre_call_hook(call_type=call_mcp_tool)` | §2.4、§5.3 |
| `/Users/peter/Desktop/research/lite-llm/litellm-versions/litellm-sep-29/litellm/proxy/_experimental/mcp_server/rest_endpoints.py:365-371` | MCP 工具呼叫也走共用的 pre-call 與花費記錄 | MCP／A2A 參考 |
| `/Users/peter/Desktop/research/lite-llm/litellm-versions/litellm-sep-29/litellm/proxy/agent_endpoints/a2a_endpoints.py:779-786` | A2A 走 `common_processing_pre_call_logic(route_type="asend_message")` | MCP／A2A 參考 |
| `/Users/peter/Desktop/research/lite-llm/litellm-versions/litellm-sep-29/litellm/proxy/auth/route_checks.py:398-413` | 預算檢查只對列在 LLM route 清單上的路徑生效（含 MCP、agent routes） | MCP／A2A 參考 |
| `/Users/peter/Desktop/research/lite-llm/litellm-versions/litellm-sep-29/gateway/main.py:28-63` | 同一個 app 啟動時依路由 allowlist 修剪成 data plane（`_is_gateway_route`） | §5.2 |
| `/Users/peter/Desktop/research/lite-llm/litellm-versions/litellm-sep-29/backend/routes/allowlist.py:152-159` | `/mcp` 被放在管理 plane，不在 data plane | §5.2 |

### A.2 Bifrost

根目錄：`/Users/peter/Desktop/research/bifrost/bifrost-2026-10-05`

| 檔案（絕對路徑:行號） | 證明什麼 | 本文用在哪 |
|---|---|---|
| `/Users/peter/Desktop/research/bifrost/bifrost-2026-10-05/core/schemas/bifrost.go:622-678` | 一個 union 型別 `BifrostRequest`＋`RequestType` | §2.4 |
| `/Users/peter/Desktop/research/bifrost/bifrost-2026-10-05/core/bifrost.go:4988` | `RunPreRequestHooks`：所有 request type 共用的 plugin pipeline 入口 | §2.4 |
| `/Users/peter/Desktop/research/bifrost/bifrost-2026-10-05/core/bifrost.go:5052` | `RunLLMPreHooks` | §2.4 |
| `/Users/peter/Desktop/research/bifrost/bifrost-2026-10-05/core/bifrost.go:8675-8679` | plugin 錯誤只記 log（fail-open） | §2.4 |
| `/Users/peter/Desktop/research/bifrost/bifrost-2026-10-05/plugins/governance/main.go:1661-1683` | 治理 plugin 的 token 計數 switch 沒有 image／rerank／OCR／video，算成 0 | §2.4、§3.4（G7 的教訓） |
| `/Users/peter/Desktop/research/bifrost/bifrost-2026-10-05/plugins/semanticcache/main.go:393` | 不支援的 request type 直接放行 | §2.4 的同類例子 |
| `/Users/peter/Desktop/research/bifrost/bifrost-2026-10-05/plugins/compat/main.go:233-246` | 模型不支援時把 Responses 橋接到 chat | §2.4（橋接，本案不採用） |
| `/Users/peter/Desktop/research/bifrost/bifrost-2026-10-05/core/schemas/plugin.go:405-433` | `LLMPlugin` 與 `MCPPlugin` 兩組 hook 介面 | §5.3、MCP／A2A 參考 |
| `/Users/peter/Desktop/research/bifrost/bifrost-2026-10-05/plugins/governance/main.go:1354` | 治理 plugin 實作 `PreMCPHook` | §2.4、§5.3 |
| `/Users/peter/Desktop/research/bifrost/bifrost-2026-10-05/core/mcp/exec.go:84` | MCP 工具執行經過同一個 plugin pipeline 物件 | §2.4、§5.3 |
| `/Users/peter/Desktop/research/bifrost/bifrost-2026-10-05/transports/bifrost-http/handlers/mcpserver.go:158-162` | Bifrost 自己也是 MCP server（`/mcp`） | MCP／A2A 參考 |

### A.3 Portkey OSS 1.15.2

根目錄：`/Users/peter/Desktop/research/gateway`

| 檔案（絕對路徑:行號） | 證明什麼 | 本文用在哪 |
|---|---|---|
| `/Users/peter/Desktop/research/gateway/src/middlewares/hooks/index.ts:449-464` | `shouldSkipHook` 只認 4 種 request type，其他面的 hook 回 `{skipped:true}`、不進 deny 判斷 | §2.4 |
| `/Users/peter/Desktop/research/gateway/plugins/types.ts:3` | `requestType` 型別只允許 `complete`／`chatComplete`／`embed`／`messages` | §2.4 |
| `/Users/peter/Desktop/research/gateway/plugins/default/allowedRequestTypes.ts:99-104` | 用來擋 endpoint 類型的 guardrail，在被跳過的面上永遠不會跑 | §2.4 |
| `/Users/peter/Desktop/research/gateway/src/handlers/handlerUtils.ts:288` | `tryPost`：共用的治理路徑 | §2.4 |
| `/Users/peter/Desktop/research/gateway/src/handlers/handlerUtils.ts:476` | `tryTargetsRecursively`：每個面只傳一個 `fn` 字串進來 | §2.4 |
| `/Users/peter/Desktop/research/gateway/src/handlers/realtimeHandler.ts:30-76` | realtime 完全不走 `tryTargetsRecursively`，沒有 hook、重試、fallback | §2.4 的同類例子 |

### A.4 One-API

根目錄：`/Users/peter/Desktop/research/one-api/2026-10-05`

| 檔案（絕對路徑:行號） | 證明什麼 | 本文用在哪 |
|---|---|---|
| `/Users/peter/Desktop/research/one-api/2026-10-05/relay/controller/helper.go:68-141` | text 的預扣與結算計費 | §2.4 |
| `/Users/peter/Desktop/research/one-api/2026-10-05/relay/controller/audio.go:69-110` | audio 逐行重寫一份預扣與 rollback | §2.4 |
| `/Users/peter/Desktop/research/one-api/2026-10-05/relay/controller/image.go:185-228` | image 不預扣、另寫一份扣款與 log | §2.4 |
| `/Users/peter/Desktop/research/one-api/2026-10-05/relay/controller/proxy.go:17-41` | proxy 完全不計費、不寫 consume log | §2.4 |
| `/Users/peter/Desktop/research/one-api/2026-10-05/router/relay.go:21` | 共用的 middleware 鏈 `TokenAuth`、`Distribute` | §2.4 |
| `/Users/peter/Desktop/research/one-api/2026-10-05/controller/relay.go:26-43` | 依 relay mode 分派到 text／image／audio／proxy helper | §2.4 |
| `/Users/peter/Desktop/research/one-api/2026-10-05/relay/adaptor/interface.go:11-21` | provider adaptor 介面 | §2.4 |

### A.5 vLLM

根目錄：`/Users/peter/Desktop/research/vllm-version/vllm-2026-10-05`

| 檔案（絕對路徑:行號） | 證明什麼 | 本文用在哪 |
|---|---|---|
| `/Users/peter/Desktop/research/vllm-version/vllm-2026-10-05/vllm/entrypoints/serve/middleware/authenticate.py:11` | `GUARDED_PREFIX` 以外的路由（`/tokenize`、`/score`、`/rerank`…）沒有 auth | §2.4 |
| `/Users/peter/Desktop/research/vllm-version/vllm-2026-10-05/vllm/entrypoints/anthropic/serving.py:807-814` | Messages 轉成 chat completion 再執行 | §2.4 |
| `/Users/peter/Desktop/research/vllm-version/vllm-2026-10-05/vllm/entrypoints/serve/engine/serving.py:29` | `BaseServing`：各面共用的 base class | §2.4 |
| `/Users/peter/Desktop/research/vllm-version/vllm-2026-10-05/vllm/entrypoints/launchers/api_server/routers.py:12` | `register_api_routers`：所有面的路由註冊處 | §2.4 |
| `/Users/peter/Desktop/research/vllm-version/vllm-2026-10-05/vllm/entrypoints/openai/responses/serving.py:102` | `OpenAIServingResponses`：Responses 是原生實作，不經 chat | §2.4 |
| `/Users/peter/Desktop/research/vllm-version/vllm-2026-10-05/vllm/entrypoints/mcp/tool_server.py:234` | `init_tool_server`：MCP tool server 只接給 Responses | §2.4、MCP／A2A 參考 |

## 附錄 B：本案的 ADR-093 對照

| Invariant | 本案 |
|---|---|
| 1 No partial state | 處置表與登記表只影響「哪些 stage 會跑」；寫入（slot、lease、binding、ledger）仍然只在所有 stage 通過之後 |
| 2 Pre-condition | 未登記的面、缺處置，在任何 stage 之前就拒絕，沒有副作用 |
| 3 Post-condition | terminal 讀上游真實的 usage 記帳（INV-494-6）；G4 在測試裡重讀實際跑到的 stage，不信宣告 |
| 4 Fail-fast | 沒有預設值：未知的面、缺處置、未知的 usage 形狀都會失敗並寫稽核；強制 stage 不得宣告不適用 |
| 5 Identity binding | `request_id`、`trace_id`、`tenant_uuid`、`credential_uuid` 仍在 auth stage 綁一次；embeddings／audio 併入後也一樣；A2A 的委派鏈同樣在邊界綁一次 |
