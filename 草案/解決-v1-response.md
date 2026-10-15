# 解決 `/v1/responses` 的結構性落後：問題、證據與推薦方案（研究輸入草案）

> **用途**：給新 session 的 agent 做 research 與設計用。讀完要知道四件事：
> - 為什麼每個新功能在 `/v1/responses` 上都落後一版。
> - 目前四個領域的缺口修到哪裡。
> - 推薦的結構性解法長什麼樣子。
> - 要去哪些檔案找證據。
>
> **性質**：這是**研究輸入，不是決策**。權威來源是 `xparse/docs/` 底下的 ADR／SPEC／PRD；本文與它們衝突時，以它們為準。推薦方案要先經過 research（§10）與設計閉環（§11），才能變成 ADR。
>
> **撰寫日期**：2026-10-02。
>
> **Rev.2（2026-10-03）**：加入 LiteLLM 原始碼對照（§15，commit `39d14bd`，2026-09-28）。這一版依對照結果修訂了 §2.2、§6.3、§6.5、§6.7、§6.8、§6.9、§9、§10，修訂處都標了「Rev.2」。
>
> **基準**：`origin/main` `1ab639567`（2026-10-02 17:47 +0800，#5742 merge）。
> - §3 各表的 PR 編號與行號，大多來自三個調查 agent 對 `origin/main` `be5975658` 的查證（同一天，相差數個 commit）。
> - 本文作者另外抽查了兩件事：
>   - §13 所有 issue 的狀態。
>   - #5257、#5681、#4242 在 prod／rel 分支上的包含關係。
>
> **行號會漂移**，引用前請重新 grep。
>
> **現況（2026-10-05）**：本文推薦的切片 S1–S6 已全部 merge（第一輪）。10-05 複查找到 I1–I9，第二輪又在修補途中找到 7 個缺口；第二輪 16 個 PR 已 merge，只剩 #5861 在 PR #5870。兩輪都還沒部署。進度：`docs/進行中/v1-response.md`；工作清單：`docs/進行中/v1-response-checklist.md`；評審與落地後複查：`docs/草案/解決-v1-response-評審.md` §5、§8。§3 與 §13 的主表是 10-02 的快照，現況以上述文件為準。
>
> **路徑慣例**：
> - 除非寫明絕對路徑，路徑都相對於 repo 根目錄 `/Users/peter/Desktop/X-parse/xparse`。
> - `GW/` 是 `apps/gateway/bustream/gateway/` 的縮寫。
> - `ST/` 是 `apps/gateway/bustream/streaming/` 的縮寫。

---

## 0. 給接手 agent 的說明

### 0.1 先確認本機是不是舊的

```bash
cd /Users/peter/Desktop/X-parse/xparse && git fetch origin && git rev-list --count HEAD..origin/main
```

- 結果不是 0，就不要相信本機的樹。改用 `git show origin/main:<path>`，或從 `origin/main` 開 worktree。
- ⚠️ 在 zsh 裡寫 `git show $SHA:apps/...` 時，`:a` 會被當成修飾詞吃掉。請寫成 `"origin/main:apps/..."`，或用 `${SHA}:apps/...`。

### 0.2 硬性規則（沿用 `/Users/peter/Desktop/X-parse/docs/agent-policy.md` §7.4）

- 不部署，也不碰遠端環境（rel／prod）。需要的查詢只能寫成 follow-up。
- 不准用 `git stash`：所有 worktree 共用 `refs/stash`，裡面有 Peter 的舊 stash。
- 主 checkout 的本機狀態要保留，不准 reset、clean 或 stash：`3rd/xparse_audit` 的改動、`frontend/console-app/`、`pr-worktrees/`。
- 一律在 worktree 工作：`/Users/peter/Desktop/X-parse/pr-worktrees/<name>`，分支從 `origin/main` 開。
- **不動 PR #3978**（June 的 ADR-427 草案），也不聯絡 June。
- 不把任何 key 寫進 commit、PR、文件或證據。測試用的 key 在 `/Users/peter/Desktop/testing/.env`，只能用 `grep -E '^NAME='` 讀單一變數，不要 cat 整個檔。
- 沒有 Peter 明確同意，不建強制模式（enforce）的 Tool 規則。

### 0.3 建議的工作順序

1. 讀 §1–§4，理解問題。
2. 讀 §6 的推薦方案。
3. 依 §10 做 research，這包括 §17.1b 規定的外部證據。
4. 用 `/research` 產出 `docs/research/RESEARCH-*.md`。
5. 依 §11 走設計閉環（PRD → ADR → SPEC）。

---

## 1. 一句話問題

**新的治理功能都先蓋在 chat 管線上。`/v1/responses` 是透明轉送的另一套架構，所以每個功能都要在它上面另外接一次，而且經常默默漏接。** 漏接時沒有任何東西會報錯：Console 設定照樣顯示生效，CI 照樣綠燈，直到有人實測才發現。

被這個問題咬過的有 smart routing、guardrail、Tool 規則，以及成本記帳。使用者（Peter）的問題是：**能不能一次解決這個 coupling，讓之後的新功能自動適用 `/v1/responses`？**

---

## 2. 背景：三條 API 面怎麼走

### 2.1 chat 與 messages 為什麼能「白拿」所有功能

- **ADR-280**（`docs/adr/ADR-280-gateway-chat-governance-service-extraction.md`）把治理核心抽成跟框架無關的服務，流程是：
  `IAM validate → guardrail → policy → admission → routing → StreamingManager → audit`
  - 型別定義在 `GW/chat_service.py`：`ChatRequestContext`、`ChatExecutionResult`。
  - 執行點在 `GW/routes/chat.py:1079`，也就是 `execute_chat`。
  - 行為契約是 SPEC-208（`docs/spec/SPEC-208-gateway-chat-service-seam-behavioral-contracts.md`）。
- **ADR-239**（`docs/adr/ADR-239-anthropic-messages-ingress-translation.md`）：`/v1/messages` 是「薄翻譯殼」。
  - 請求進來時，`GW/anthropic_translation.py` 把 Anthropic 格式翻成內部的 OpenAI chat 形狀，然後走同一個 `execute_chat`。
  - 出去時再翻回 Anthropic 的 envelope 和 SSE。
  - 所以 chat 上的每個功能，messages 都自動有。
- chat 管線的內部事件型別定義在 `ST/sse_event.py`：`DeltaEvent`、`ReverseEvent`、`PatchEvent`、`CheckpointEvent`、`ToolCallsEvent`、`DoneEvent`。
  - 產生這些事件的是 `ST/manager_v3.py`（StreamingManagerV3），搭配 `manager_v3_events.py` 與 `manager_v3_workers.py`。
  - gateway 對這條管線有完整控制權，要插一關、扣住、改寫都很自然。

### 2.2 `/v1/responses` 為什麼不能也翻成 chat

- **歷史**：
  - Phase 1 是 PRD-157 加 ADR-192（`docs/prd/PRD-157-responses-api-phase1-gateway-governed.md`、`docs/adr/ADR-192-responses-api-phase1-architecture.md`），2026-05 上線。
  - route 的 docstring 自己列了五項 Phase 1 不做的事：admission、semantic cache、guardrail output、agent-mode、retry。
- **ADR-339**（`docs/adr/ADR-339-responses-streaming-fidelity-transparent-passthrough.md`）：
  - 當初 worker 把 provider 的 `response.*` 事件**壓扁**成 chat 風格的 `{content}` 片段，最後再加一個 `[DONE]`。
  - Codex 0.142.5 起只講 Responses，它等不到 `response.completed`，就重連 5 次然後失敗。
  - 決策是**透明轉送**：provider 的 named SSE 原封不動轉給 client，永遠不送 `[DONE]`。
  - §3 的替代方案 B「從正規化片段重建 Responses 事件」被否決，理由是會失真、會跟 OpenAI 的 schema 漂移。
  - **關鍵句（§1.2）**：*"The normalize-to-chat transform was appropriate for feeding the internal audit/token pipeline … but it was wrongly placed on the client-facing wire."*
    意思是：正規化本身沒錯，錯在把它放上 client 看得到的線路。**這正是 §6 推薦方案「雙通道」的前例。**
  - 行為契約是 SPEC-234（`docs/spec/SPEC-234-responses-streaming-fidelity-behavioral-contracts.md`）。
  - **Rev.2 補充：「Codex 非常挑」需要講得更精確。** ADR-339 記錄的致命問題是「完全沒有 `response.*` 事件」，不是 `[DONE]` 或少了 `event:` 行本身。
    - LiteLLM 的 HTTP Responses 路徑會解析事件再重新序列化：只送 `data:` 行、不送 `event:` 行、刪掉 null 欄位、最後補 `[DONE]`（§15.2）。它官方仍提供 Codex 設定。
    - 這表示 Codex 能容忍的範圍可能比我們以為的寬。但這只是推論，沒有對真 Codex 驗證過（§10 Q12）。
    - 對本案的意義：轉接層的 renderer 在「扣住、合成同格式事件」時，可以動的空間可能比 ADR-437 假設的大。即便如此，預設仍應維持原始 frame 透明轉送，只做外科式修改。
- **ADR-437 Phase 2**（`docs/adr/ADR-437-responses-surface-governance-parity-phase2.md`，契約是 `docs/spec/SPEC-282-responses-governance-parity-behavioral-contracts.md`）：把 Phase 1 的缺口補成一條「永遠串流的 named-SSE 治理管線」。
  - **三動作規則**（§1.2 Forces、§3.1）：每一層只能扣住（hold）、觀察，或合成**同格式**的事件；不改事件語法；`response.completed` 之後不再送內容。
  - **commit point**（INV-437-1）：第一個 `__binding__` sentinel，或第一個轉送出去的事件。retry 和 failover 只能發生在 commit 之前。
  - **D7**：`create_response` 縮成「編號步序的組合層」，邏輯放進扁平的 `GW/responses_*.py`。**刻意不做** `execute_responses(ctx)` 這種 seam，理由是「SPEC-208 的 seam 是因為兩個 ingress 共用 `execute_chat` 才存在，這個面只有一個 ingress」。
    → **本文要挑戰的就是這個理由**：問題不在 ingress 的數量，在**功能的數量**。每多一個功能，就要多接一次。
- **現行步序**（`GW/routes/responses.py`，`create_response` 裡的編號註解，行號以 `1ab639567` 為準）：

| 步序 | 行號 | 內容 |
|---|---|---|
| 1 | :524 | Auth，在邊界綁定身分（ADR-093 inv 5） |
| 1.2 | :537 | 這次請求新出現的 tool 結果，在任何閘門之前先稽核（RSP-AUD-8） |
| 1.3 | :539 | Tool 規則（`GW/responses_tool_governance.py:472` `apply_tool_governance`） |
| 1.5 | :543 | Guardrail input rails |
| 3 | :550 | Store 正規化 |
| 4 | :555 | 模型定址閘門（ADR-138） |
| 4.05 | :558 | 預算閘門（#5450、RSP-ADM-10） |
| 4.1 | :565 | Routing（ADR-430） |
| 4.2 | :579 | 可觀測性 header |
| 4.5 | :584 | Policy Kernel 邊界檢查 |
| 4.6 | :592 | `agent_mode` → 400 |
| 5 | :597 | Chain 驗證（`previous_response_id`） |
| 5.5 + 6 | :609 | Classifier INPUT 與 admission |
| 6.1 | :622 | SPEC-086 L2 endpoint lease |
| 7 | :628 | Setup window：每個 attempt 的 credential、worker、binding closure，以及 R1／R3 |
| 8 | :640 | 串流：ADR-339 透明轉送。依序經過 `output_rail_stage`（`GW/responses_output_rail.py:157`）、capture tap、終端稽核 |

### 2.3 Responses 協定的本質差異（chat 的假設在這裡會踩空）

| 差異 | 說明 | 對治理的影響 |
|---|---|---|
| 永遠串流、named SSE、沒有 `[DONE]` | 終止事件是 `response.completed`／`response.incomplete`／`response.failed`／`event: error` | chat 的 `data:` 加 `[DONE]` 狀態機（`FAST_STREAMING → … → FINALIZE`）不能用 |
| 伺服器端對話狀態 | `previous_response_id` 串起整段對話；`store=true` 時歷史存在 provider 那邊 | 走 chain 的請求，gateway 只看得到這一輪新送的 item，**看不到也改不了完整歷史**。Codex 是例外：它 `store=false`、不送 `previous_response_id`、每輪重送全部歷史（memory `reference_codex_is_responses_only_and_stateless.md`） |
| input 是多型 item | `message`（role）、`function_call`、`function_call_output`（沒有 role）、`custom_tool_call`、`reasoning`、`item_reference`、`computer_call*`、`local_shell_call` 等 | chat 的「依 role 讀 messages」會分錯類。例子：`_responses_input_slots` 曾把沒有 role 的 `function_call_output` 當成 user 項，已由 #4958 修掉（`GW/guardrail_detection.py:564`） |
| 加密 reasoning | `encrypted_content` 不透明 | 看不到內容。跨憑證 failover 有重放風險（#4878） |
| hosted 工具 | `web_search` 等由 provider 自己執行 | gateway 只能管「宣告」，管不到「執行」。平台會把非 function 的工具剝掉（`GW/responses_tools_filter.py`，S0-b） |
| client 行為 | Codex 的終止狀態集合只有 HTTP {400, 429}；串流中的 `event: error`、`response.incomplete`、`response.failed` 都會讓它重試 5 次 | 「擋下要送什麼格式」必須對真 client 實測，否則一次擋下會被放大成 6 次請求（§3.2、§6.8） |

---

## 3. 證據：同一個根因，在四個領域各出現一次

> 來源：
> - 三個調查 agent 在 2026-10-02 對 `origin/main` `be5975658` 逐項查證。
> - 本文作者抽查了 §13 的 issue 狀態，以及 §3.5 的分支包含關係。
> - 部署狀態只核對了 git 分支，**沒有驗證主機上實際跑的版本**。

### 3.1 Smart routing／模型定址（對照 `/Users/peter/Desktop/X-parse/docs/LLM_PROXY.md`）

| 項目 | Responses 上的問題 | 現況 | 證據 |
|---|---|---|---|
| routing_strategy／objective（#3821） | 這條路根本沒呼叫 routing，一律用排序第一的模型；Console 的設定在這裡靜默無效 | **已修** | PR #4241；`GW/responses_routing.py` 呼叫 resolver；cost／latency 實測值回寫在 `GW/responses_resilience.py` |
| `llm_judge_routing` | 不呼叫判官，直接退回 heuristic | **延後**（#4248 OPEN） | `GW/responses_routing.py:268`，`judge.source = "judge_surface_unsupported"` |
| Jev routing | — | **已支援** | PR #5149 |
| 候選池 | 只收 `RESPONSES_PROVIDERS`（`GW/routing_adapter.py:98`、`responses_surface_models` 在 `:125`）；同一個 app 在兩個面各有一套分級 | **設計如此**；根因是 #2783（OPEN） | — |
| chat 面候選池變小 | `chat_surface_models`（`GW/routing_adapter.py:108`）把 Responses 模型剔掉，池子變小、分級折疊；但 IAM 的 `complexity_tier_bands` 是用全池算的 | **未修**，沒有專屬 issue | memory `reference_chat_surface_filter_shrinks_routing_pool.md` |
| chat 面指名 Responses 模型 | 實際跑的是別顆，回應裡卻照樣寫指名的名字 | **未修**（#3822 OPEN） | agent 報告的位置是 `GW/routes/chat_helpers.py` 的 `named or models` |
| app 只綁 Responses 模型卻打 chat | 回 422 `model_not_on_chat_surface`，不做轉譯 | **部分**：已經明確報錯；轉譯是 #2551、#5528、#5525（全部 OPEN） | `GW/cross_surface.py` |
| Session affinity（#4592） | Codex 無狀態，以前每輪都重新路由 | **已修**（ADR-447 Amendment B） | PR #4726 |
| Retry／failover | 以前一出錯就終止 | **已修**：commit 前可以 R1／R3（PR #4246）。跨憑證重放加密 reasoning 是 #4878（OPEN，未驗證） | `GW/responses_resilience.py` |
| ADR-455 bridge 遇到 incomplete／failed | 已累積的 tool calls 被丟掉，client 拿到 200 加空回答 | **未修**（#5668 OPEN） | `ST/workers/azure_responses_worker.py`、`apps/gateway/bustream/backend/responses_bridge.py` |
| `tool_choice`／`parallel_tool_calls` | 請求收下了，但被默默丟掉 | **未修**（#5670 OPEN） | `GW/routes/responses.py:185` `ResponsesCreateRequest`；`:204-216` 的註解記錄了前三次 `extra="ignore"` 默默丟欄位的歷史 |
| `include` | 被默默丟掉，加密 reasoning 回不到 Codex | **未修**（#4876 OPEN） | 同上 |
| Policy Kernel 邊界檢查 | rel／prod 仍是 shadow | **ops 決定時機**（#1060 OPEN） | `docs/runbooks/responses-boundary-enforce-cutover.md` |
| 憑證 provider 不符 | `openai` 憑證綁 `openai_responses` 模型，validate 會回 500 | OpenAI 這條已修（#4400）；Azure 與 Console 是 #3677、#4405（OPEN） | — |

### 3.2 Guardrail／policy（對照 `/Users/peter/Desktop/X-parse/docs/guardrail.md`）

| 項目 | Responses 上的問題 | 現況 | 證據 |
|---|---|---|---|
| Kernel shadow 稽核 | `policy.boundary_shadow_would_block` 不在 enum 裡，事件從來沒寫進資料庫，「先量再開強制」卡了 14 個月 | **已修** | PR #4240；`apps/gateway/bustream/audit/schema.py`、`audit/xparse_bridge.py`；memory `reference_responses_shadow_audit_never_persisted.md` |
| Kernel enforce | 只告警、不擋；on_prem app 走 Codex 時資料邊界實際沒擋 | **未修**，要等 ops 決定（#1060） | `GW/responses_pipeline.py` 預設 `"shadow"`；compose 寫 `${XPARSE_POLICY_RESPONSES_MODE:-shadow}` |
| Admission | 不排隊、不佔槽 | **已修** | PR #4242 |
| Output rail | `stream` 模式只觀察；`buffer` 模式才能擋 | **設計如此**（ADR-437 D1）。PR #4243 落地；#4281 補上 part／item.done 的洩漏 | `GW/responses_output_rail.py`。⚠️ `buffer` **只扣住文字事件，tool call 與 reasoning 照原樣送出**。#4845 起 Console 拿掉 buffer 選項，只能從 API 寫 |
| `instructions` 被丟掉 | 欄位沒轉送，classifier 也看不到 | **已修** | PR #4277（#4249）。PII 要不要掃由 `scan_system` 決定，預設關（#4860） |
| PII 寬面（guardrail.md §3.8 #9） | 只掃 `instructions` 和 user 項；tool 輸出裡的個資每一輪都原樣出境 | **已修** | PR #4958；`GW/guardrail_input_surface.py`、`GW/guardrail_detection.py` |
| content_filter 判的範圍 | 判的是所有 user 項串起來的文字 | **已修**，改成只判最後一則 user | PR #4961；`GW/request_text.py:337` `responses_last_user_text`；`GW/responses_input_guard.py` |
| word_filters 掃描文字 | 不含 `function_call` 參數與工具輸出 | **已修** | PR #4961；`GW/guardrail_handler.py` 的 `_word_filter_scan_text` |
| `scan_tool_results` | tool 結果不送 classifier | **已修** | PR #4969 |
| Classifier／Jev | judge 是 chat 形狀，Responses 的 provider 會炸 | **已修**：共用 `run_input_classifier`；`auto` judge 轉成 Responses 形狀（#4243）；資料邊界 gate（#5235） | `GW/classifier_handler.py`、`GW/responses_input_guard.py` |
| `x-guardrail-redacted` | Responses 串流從來不帶這個 header | **已修** | PR #5258 |
| chat 與 responses 行為相反（OQ-4） | 同一筆個資，chat 漏出去、responses 回 451 | **已修**，統一成 fail-closed | PR #4729、#4806 |
| 451 讓 Codex 重試 5 次 | 擋一次等於 6 次寬面掃描加 6 筆稽核 | **未修**（#4854 OPEN） | `docs/research/RESEARCH-agent-client-block-status-retry-behaviour-2026-09-15.md` |
| 串流中的終止事件 | `event: error` 與 graceful `response.incomplete` 都讓 Codex 0.154 重試 5 次，使用者看不到 gateway 的訊息 | **未修**（#5669 OPEN）。#4250 雖由 #4281 關閉，但它的前提已被實測推翻 | `GW/responses_pipeline.py` 的 `error_frame`、`GW/responses_graceful.py` 的 docstring 仍寫「每個 client 都會處理」 |
| 擋下後刪除 provider 端狀態 | provider 存的狀態裡還有被擋的文字 | **已修**（best-effort） | #4251、PR #4278；`GW/responses_delete_handler.py` |

### 3.3 成本（對照 `/Users/peter/Desktop/X-parse/docs/cost.md`、`/Users/peter/Desktop/X-parse/docs/issues/cost-issue.md`）

| 項目 | Responses 上的問題 | 現況 | 證據 |
|---|---|---|---|
| 准入與事件 | ADR-437 之前沒有准入，所以沒有預算或限流閘；也不發 `EXECUTION_*` 事件 | **已修，prod 也有** | PR #4242；`GW/admission_handler.py` 的預算估算讀 `input`（RSP-ADM-9） |
| 沒記帳（#5136） | 會發出有價的 `COMPLETED` 事件，但從來不寫 ledger；Codex 的用量好幾個月沒算進 Budget、ADR-398 上限和 `/v1/usage` | **已修，prod 沒有** | PR #5257；`GW/responses_execution_audit.py`；`.github/scripts/usage-ledger-surface-parity-gate.py` |
| 失敗嘗試（#5137） | `response.failed` 或串流中途斷掉時，已經用掉的量沒入帳 | **已修，prod 沒有** | PR #5277；之後 #5596 改走 `book_failed_attempt`（`GW/audit_helpers.py:455`） |
| 用量取錯終止事件（#5680） | 只從 `response.completed` 拿用量，`incomplete`／`failed` 的量都丟了；`cached_tokens` 從沒讀，快取命中照全價算（約貴 3.5 倍） | **已修（10-02），prod 沒有**；P-AUD-4 要部署後才能驗 | PR #5681；`ST/workers/azure_responses_worker.py` |
| 預算檢查太晚（#5450） | 預算排在 Jev 判級與 classifier 判官之後，預算用完了還要先付判官的錢 | **已修，prod 沒有** | PR #5474；步序 4.05；`GW/responses_admission.py`；`GW/admission_handler.py:1235` `enforce_budget_gates` |
| ledger 共同鍵（C-302-83） | Responses 的 `COMPLETED`／`FAILED` 沒帶 ledger 鍵，對帳 join 不到 | **已修，prod 沒有** | PR #5596 |
| 用戶端斷線 | 沒有終止事件也沒有 usage：input 記 0、output 用 `len//4` 估，整筆當成功。chat 也一樣 | **未修**。設計已在 #5726 merge（PRD-313 Am.E、C-284-29），實作沒有 PR | `GW/responses_execution_audit.py`；`GW/usage_ledger_hook.py:357` `record_usage_to_ledger` |
| commit 前的 retry 嘗試 | 沒有實際用量，所以不記 | **設計上不做**（INV-272-4，不捏造用量） | ADR-423 Am.G |
| 歷史漏帳 | #5136 修好之前的用量 | **設計上不做**，不回填（C-302-100） | ADR-423 Am.E |
| 判官先於擋下 | 限流與 denylist 排在判官之後；被擋的請求仍付一次判級的錢。chat 也一樣 | **未修**（#5458、#5222 OPEN） | — |

### 3.4 Tool 規則（Agent Policy v1，對照 `/Users/peter/Desktop/X-parse/docs/agent-policy.md`）

| 項目 | chat（OpenCode） | messages（Claude Code） | responses（Codex） |
|---|---|---|---|
| 請求端拿掉工具、拒絕 | ✅ | ✅ | ✅（只比 `type=function`） |
| 回應端整輪擋下（R-A） | ✅ `GW/tool_governance_response.py` | ✅ | ❌ **沒有地方扣住 tool call**，排在 v1.1（ADR-490 §7.2.1） |
| 對外說法 | — | — | 只能說「被禁工具的定義不送給模型」。P16 實測：模型若依歷史吐出被禁工具，Codex 會照執行 |

**2026-10-02 真 client 實測**（本 session 做的）：
- 腳本：`/Users/peter/Desktop/testing/tool_gov_agent_e2e.py`
- 結果：`/Users/peter/Desktop/testing/results/tool_gov_agent_e2e/README.md`

| 規則 | 三家結果 |
|---|---|
| shadow，禁 shell | 三家照跑 `ls`，稽核記 `would_strip`；chat／messages 另有回應端 `would_block`；Responses 沒有回應端事件 |
| enforce，禁 shell | 三家都拿不到 shell 工具；每個請求記一筆 `tool_stripped`；messages 回應帶 `x-xparse-tools-stripped: Bash` |
| enforce，只允許唯讀工具 | Claude Code 只剩 Glob／Grep／Read；OpenCode 只剩 glob／grep／read；Codex 的 function 工具全部被拿掉 |
| enforce，`tool_use: deny` | 三家都收到 400、都不會一直重試；違規稽核 `tool_not_allowed` |

**沒測到：回應端擋下的 enforce 路徑。** gpt-5.4 和 deepseek-flash 在工具被拿掉後都不會再呼叫它，所以用真 provider 觸發不了。

### 3.5 最要緊的部署落差

- prod 分支在 `v1.76.4`，rel 分支在 `v1.79.0`，兩者都用 `git describe --tags` 確認過。
- `git merge-base --is-ancestor` 的結果：

| Commit | 內容 | prod | rel |
|---|---|---|---|
| `41a571f92` | #4242 admission 與預算檢查 | 有 | 有 |
| `4ac862990` | #5257 Responses 寫 ledger | 沒有 | 有 |
| `7b076583f` | #5681 用量與 cached_tokens | 沒有 | 有 |

**結論：prod 從 09-06 起已經對 Responses 做預算檢查，但它讀的 ledger 從來沒收到 Responses 的用量，所以 prod 上 Codex 的花費到今天仍然不會扣 Budget。** 這是「功能在 Responses 上只接了一半」最昂貴的例子。

另外，`guardrail.md`、`cost-issue.md`、`LLM_PROXY.md` 裡有幾處部署狀態已經過時，例如「Am.H 未部署」、「rel 是 v1.77.0.1」。

---

## 4. 根因分析：coupling 的具體形狀

### 4.1 功能直接依賴 chat 的資料形狀

治理功能是對著 chat 管線的具體結構寫的：
- 請求端讀 `messages[*].role/content/tool_calls`。
- 回應端看 `ToolCallsEvent`、`DeltaEvent`（`ST/sse_event.py`）。
- 結束點掛在 StreamingManagerV3 的 finalize，以及 `GW/routes/chat_streaming_audit.py`、`GW/non_streaming_handler.py`。

沒有一層「API 面中立」的抽象。所以換到 Responses，每個功能都要依 Responses 的 item 與事件形狀**重寫一次**。

### 4.2 重工量（`origin/main` `1ab639567`）

- Responses 專屬模組：`GW/responses_*.py` 共 17 個檔，約 6,700 行；`GW/routes/responses.py` 另有 853 行。
  - 相比之下，`GW/routes/chat.py` 3,144 行，`GW/routes/messages.py` 627 行，因為 messages 是共用 chat 的。
- 共用模組裡「依 API 面分支」的密度。數字是 `grep -ciE 'responses|surface'` 的粗略計數，只當指標，不是精確量測：

| 模組 | 行數 | responses／surface 字樣 |
|---|---|---|
| `GW/guardrail_detection.py` | 1,090 | 107 |
| `GW/guardrail_handler.py` | 1,442 | 85 |
| `GW/guardrail_input_surface.py` | 569 | 60 |
| `GW/cross_surface.py` | 231 | 47 |
| `GW/classifier_handler.py` | 5,206 | 35 |
| `GW/request_text.py` | 357 | 35 |
| `GW/routing_adapter.py` | 679 | 25 |
| `GW/tool_governance_request.py` | 609 | 22 |
| `GW/tool_governance_response.py` | 469 | 20 |
| `GW/admission_handler.py` | 2,413 | 15 |
| `GW/pre_execution.py` | 1,102 | 14 |
| `GW/chat_tool_governance.py` | 307 | 13 |
| `GW/non_streaming_handler.py` | 2,198 | 13 |
| `GW/usage_ledger_hook.py` | 635 | 9 |

這表示 API 面的知識**散落在每個功能裡**，而不是集中在一個轉接層。

### 4.3 五類失敗模式

| 類別 | 說明 | 例子 |
|---|---|---|
| (a) 忘了接 | chat 有，Responses 根本沒呼叫 | ledger（#5136）、routing（#3821）、shadow enum（#4240 之前）、session affinity（#4592）、預算排序（#5450） |
| (b) 接了，但帶著 chat 的假設 | 把 item 當 messages 處理 | `_responses_input_slots` 把沒有 role 的 `function_call_output` 當 user；content_filter 判所有 user 串接；PII 只掃 user 項；用量只從 `response.completed` 取（#5680） |
| (c) wire 限制，只能做半套 | 透明轉送下 stream 模式擋不了；擋下格式讓 client 重試 | output rail 在 stream 模式只觀察；`buffer` 只扣文字；Tool 規則回應端沒做；Codex 重試 5 次（#4854、#5669） |
| (d) schema 默默丟欄位 | pydantic 預設 `extra="ignore"`，沒宣告的欄位就消失 | `instructions`（已修）、`prompt_cache_key`、`reasoning`（已修）、`tool_choice`／`parallel_tool_calls`（#5670）、`include`（#4876）。`GW/routes/responses.py:204-216` 的註解記錄了前三次 |
| (e) API 面寫死在模型身分裡 | provider 字串同時決定「哪家」和「哪個 API 面」 | #2783；候選池分裂、分級折疊、chat 面偷換模型（#3822）、跨面轉譯（#2551、#5528、#5525） |

### 4.4 為什麼現有的 gate 擋不住

- gate 是**逐功能**寫的，沒有一張「功能 × API 面」的登記表。新功能上線時，沒有任何機制會問「Responses 呢？」。
- 既有的 API 面相關 gate（`.github/scripts/`）：

| gate | 守什麼 | 缺口 |
|---|---|---|
| `usage-ledger-surface-parity-gate.py` | 會 emit `EXECUTION_COMPLETED` 的模組必須呼叫記帳 | 只檢查**有沒有呼叫**，不檢查數字對不對，所以擋不到 #5680 |
| `provider-call-usage-parity-gate.py` | `_named_sse_parser.py` 的豁免只指名 chat 的兩個記帳模組 | 沒把 Responses 的記帳模組算進去 |
| `guardrail-detection-surface-gate.py`（加 `.sh`） | guardrail 偵測面 | — |
| `tool-governance-parity-gate.py` | IAM 與 gateway 的名稱比對 vectors 逐位元一致 | 跨 owner，不是跨 API 面 |
| `session-affinity-layer-gate.py`、`conversation-scope-layer-gate.py` | 各自功能的分層 | — |

- **擋下格式從來沒對真 Codex 量過**，結果是重試放大。#4250 的前提被實測推翻後，程式碼註解仍寫「每個 client 都會處理」。

---

## 5. 目標與非目標

**目標**
1. **新功能只寫一次**：針對 API 面中立的契約寫，不直接碰 `messages` 或 `response.*`。
2. **每個 API 面寫一個轉接層**：chat、messages（沿用翻到 chat 的做法）、responses。以後若有 embeddings、audio、或 Anthropic 原生透明轉送，也照同一套。
3. **能力差異明確宣告**：某個 API 面做不到的事（例如改寫伺服器端歷史），功能要明確降級或報錯，**不准默默失效**（ADR-093 inv 4）。
4. **不再有沉默缺口**：每個功能在每個 API 面上的狀態都登記在案，由 CI 檢查。
5. **保持 ADR-339 的 wire fidelity**：Responses 的事件照樣原封不動轉送。

**非目標**
- 把 Responses 重新正規化成 chat（ADR-339 已否決）。
- 在本案解 #2783（API 面寫死在模型身分裡）。它是相鄰的架構題，見 §10 的 Q7。
- 重寫 chat 管線，或推翻 ADR-280。本案是**擴充** ADR-280 的轉接層概念。

---

## 6. 推薦方案：API 面中立的治理契約

### 6.0 總覽

```
                      治理功能（只寫一次）
   Tool 規則 · guardrail · routing · 預算／admission · 記帳／稽核 · 以後的新功能
   ┌──────────────────────────────────────────────────────────────┐
   │ on_request(view: ConversationView)  -> RequestDecision          │
   │ on_pre_dispatch(dispatch_ctx)       -> DispatchDecision         │
   │ on_observation(obs: Observation)    -> StreamDecision           │
   │ on_terminal(outcome, usage)         -> None   (記帳／稽核／回饋) │
   └───────────────┬──────────────────────────────────────────────┘
                   │ 同一份 hook 登記表，同樣的生命週期點，同樣的順序約束
       ┌───────────┴──────────────┬───────────────────────────────┐
  chat 轉接層                messages 轉接層                 responses 轉接層
 （execute_chat，ADR-280）   （翻成 chat，ADR-239）     （透明轉送不變，ADR-339）
   view：messages[]            同 chat                     view：input items
   obs：sse_event.*            同 chat                     obs：從 response.* 推導
   renderer：chat SSE 錯誤     Anthropic error 事件       renderer：pre-stream 4xx／
                                                           實測過的終止格式
   capabilities: {...}         {...}                       {...}（§6.6）
```

核心想法是一句話：**功能只回答「要做什麼」，轉接層負責「怎麼在這條線路上做出來」。**

這是 ADR-437 三動作規則的一般化。現在每個功能各自實作「扣住、觀察、合成同格式事件」；改成由轉接層統一實作，功能只回傳決策。Policy Kernel 已經是這個模式：純函數決策、沒有 I/O、不負責執行。

### 6.1 元件 1：請求視圖 `ConversationView`

**目的**：讓功能用統一的方式讀寫請求，不碰原生格式。

**介面草圖**（僅供研究，名稱可改）：

```python
class ItemKind(Enum):
    USER_TEXT; ASSISTANT_TEXT; SYSTEM_INSTRUCTIONS; TOOL_CALL; TOOL_RESULT; REASONING_OPAQUE; OTHER_OPAQUE

@dataclass(frozen=True)
class ItemRef:              # 穩定位址；寫回時用
    index: int; kind: ItemKind; role: str | None; tool_name: str | None

class ConversationView(Protocol):
    surface: Surface                            # chat | messages | responses
    def items(self) -> Sequence[ItemRef]: ...
    def text_leaves(self, ref: ItemRef) -> Sequence[TextLeaf]: ...   # 可寫回的文字葉值
    def declared_tools(self) -> Sequence[ToolDecl]: ...               # name, type, raw
    def last_user_text(self) -> str: ...
    def tail_is_tool_shaped(self) -> bool: ...
    def has_tool_turns(self) -> bool: ...
    # 寫入：只產生「修改計畫」，由 adapter 套用到原生 body，不改形狀
    def plan_remove_tools(self, names: Collection[str]) -> BodyEdit: ...
    def plan_rewrite_leaf(self, leaf: TextLeaf, new_text: str) -> BodyEdit: ...
    capabilities: SurfaceCapabilities                                 # §6.6
```

**現有雛形**：都是散裝的 per-surface 函式，要收斂成上面這組。
- `GW/request_text.py`：`extract_*` 系列、`responses_tail_is_tool_shaped`（:311）、`responses_last_user_text`（:337）、`extract_responses_transcript`、`chat_tail_is_tool_shaped`。
- `GW/guardrail_input_surface.py`：PII 寬面的抽取與寫回，含 `responses_input_text`／`write_responses_input`。
- `GW/guardrail_detection.py`：`_responses_input_slots`（:564）與 chat 的 slot 函式。
- `GW/tool_governance_request.py`：請求端計畫（拿掉工具、`tool_choice` 處理），已經分 surface。
- `GW/responses_tools_filter.py`：Responses 工具分類。

**要注意**：
- 寫回必須保持原生形狀（ADR-339）。例如 `reasoning`、`encrypted_content` 永遠不碰（ADR-448 Am.H）。
- `ItemKind` 的分類規則是**先看 `type`、再看 `role`**，這是 #4958 的教訓。

### 6.2 元件 2：觀察通道（雙通道）

**目的**：回應端的功能只看中性的「觀察」，原生事件照樣原封不動往下送。

**做法**：轉接層對每個原生事件同時做兩件事：
1. 把原生 frame 放進 wire 通道，交給 renderer 決定立刻送、扣住，還是丟掉。
2. 推導出 0 到多個 `Observation`，交給功能。

```python
Observation =
    TextDelta(text, item_ref)                     # chat: DeltaEvent；responses: response.output_text.delta
  | ToolCallStarted(call_id, name, tool_type)     # chat: ToolCallsEvent（名稱已知）；responses: response.output_item.added(type=function_call...)
  | ToolCallArgsDelta(call_id, delta)             # responses: response.function_call_arguments.delta
  | ToolCallCompleted(call_id, name, args)
  | ReasoningOpaque(item_ref)
  | Usage(input, output, cached, reasoning)       # chat: finalize；responses: completed／incomplete／failed 的 usage（#5680 教訓）
  | Terminal(kind: COMPLETED|INCOMPLETE|FAILED|CLIENT_DISCONNECT|ERROR, detail)
```

**前例**：
- ADR-339 D1 讓 worker 輸出原生事件流（`ST/workers/azure_responses_worker.py:410` `stream_events`，OpenAI 版綁在 `ST/workers/openai_responses_worker.py`），也明確說「正規化給內部用是對的」。
- `GW/responses_stream.py`、`GW/responses_content_capture.py`、`GW/responses_tool_calls.py` 已經在做類似的事，例如 `tool_call_detected` 稽核。
- chat 那邊的 `audit.execution.tool_call_detected`、`tool_call_resolved` 是同一個概念的另一份實作。

**研究重點**：
- 雙通道的效能成本：每個事件多一次推導。
- 推導規則要對照 SPEC-234 的事件序列契約。

### 6.3 元件 3：決策與呈現分離

```python
RequestDecision  = Allow | Modify(edits: list[BodyEdit]) | Reject(code, http_status, message, audit)
StreamDecision   = Pass | Hold(until: HoldCondition) | Block(code, message, audit) | Observe(audit)
DispatchDecision = Proceed | Reject(...) | Queue(...)          # 預算、admission、kernel 邊界
```

**renderer 的職責**（每個 API 面一個）：
- **Reject**：在開始串流之前回一般 HTTP 4xx，格式依 API 面而定（chat、Anthropic、OpenAI Responses 的 error envelope）。
  - D2 已實測：Codex 收到串流前的 400 不會重試（`docs/research/poc/agent-tool-governance-local-verification-2026-10-01/D2/`）。
- **Hold**：決定扣哪些原生 frame。
  - Responses 扣文字時，現行做法是 `output_rail_stage` 只扣 `response.output_text.delta`／`.done`（INV-437-3）。
  - 擴充到扣 tool call 時，要扣 `response.output_item.added(function_call)` 與 `function_call_arguments.*`。
- **Block**：送「該 API 面 × 該 client」實測過不會重試的終止格式（§6.8）。
- **合成同格式事件**：例如 buffer 放行後合成**一個** `response.output_text.delta`，並正確填 `item_id`、`output_index`、`content_index`、`sequence_number`（ADR-437 §5.3 的風險列）。
- **commit 規則**：commit point 之後只允許 `Observe`，或終止型的 `Block`；`Modify` 永遠只能在 commit 之前（INV-437-1）。
- **Rev.2：commit point 可以往後延。** LiteLLM 的 router 會先扣住輸出前的 lifecycle 事件（`response.created`、`response.in_progress`、`response.queued`），等到第一個真正的輸出出現才放行，最多扣 200 個（`litellm/router.py:620-627`），所以 retry 與 fallback 的窗口一直延到第一個輸出為止（§15.3）。我們的 INV-437-1 把 commit point 定在「第一個 `__binding__` sentinel 或第一個轉送出去的事件」，窗口比較窄。值得研究是否改成「第一個輸出事件」（§10 Q14）。要注意的是，我們的 binding INSERT 綁在 sentinel 上，延後 commit 會牽動 binding 的時機。

**現有雛形**：
- `GW/responses_output_rail.py`（buffer／stream）。
- `GW/responses_graceful.py`（graceful refusal 合成）。
- `GW/responses_pipeline.py`（`error_frame`、`encode_sse`）。
- `GW/tool_governance_response.py`（chat 的 R-A in-band error）。
- `GW/tool_governance_errors.py`（固定文案，含 OpenCode 重試字串禁令 C-304-157）。
- `GW/stream_termination.py`、`GW/sse_formatter.py`（chat 側）。

### 6.4 元件 4：生命週期 hook 登記表

把現在 chat 與 Responses 各自「寫死」的步序，抽成同一份登記表。每個功能宣告自己掛在哪個 hook、要排在誰前後，兩個轉接層依登記表呼叫。

| Hook 點 | 用途（現有功能） | chat 現在在哪 | Responses 現在在哪 | 順序約束 |
|---|---|---|---|---|
| `on_ingress` | 身分綁定 | `GW/auth_handler.py`（共用） | 步序 1 | 最先；identity 不可變（ADR-093 inv 5） |
| `on_request` | tool 結果稽核、Tool 規則、舊開關 `tool_call_allowed`、guardrail input rails（PII／word_filters） | `GW/chat_tool_governance.py`、`GW/guardrail_policy_adapter.py`／`GW/guardrail_handler.py`、`GW/pre_execution.py`（`reject_tool_calls_not_allowed`） | 步序 1.2、1.3、1.5 | Tool 規則在 cache 和 rail 之前（C-304）；R-a 舊開關先回（INV-490-25） |
| `on_pre_dispatch` | 定址、預算、routing（判官／Jev）、kernel 邊界、classifier input、admission、lease | `GW/admission_handler.py`（`enforce_budget_gates` :1235）、`GW/routing_decision.py`、`GW/session_affinity_prefilter.py`、`GW/slot_lease_adoption.py` | 步序 4 到 6.1 | 預算在判官之前（#5450）；限流與 denylist 也應在判官之前（#5458、#5222，chat 和 Responses 都還沒做） |
| `on_attempt` | R1／R3、每個 attempt 的 credential 與 binding | chat 的 resilience（ADR-260、ADR-353） | 步序 7，`GW/responses_resilience.py` | 只在 commit 前 |
| `on_observation` | 回應端 Tool 規則、output guardrail、`tool_call_detected` 稽核、串流期限 | `ST/manager_v3*.py`、`GW/tool_governance_response.py`、`GW/streaming_deadline.py` | 步序 8，`GW/responses_output_rail.py`、`GW/responses_stream.py` | 名稱判定先於參數層（ADR-490 Q3 與 ADR-427 草案的組合規則） |
| `on_terminal` | 記帳（含失敗、incomplete、斷線）、execution 稽核、routing 回饋（EWMA）、session affinity pin | `GW/usage_ledger_hook.py`（`record_usage_to_ledger` :357、`record_failed_usage_to_ledger` :299）、`GW/audit_helpers.py`（`book_failed_attempt` :455）、`GW/routes/chat_streaming_audit.py`、`GW/non_streaming_handler.py` | `GW/responses_execution_audit.py` | 每個請求恰好一個終端稽核（INV-437-10）；先 `aclose` 再讀 usage（P18、INV-490-10） |

**現有雛形**：`GW/responses_pipeline.py` 的 stage 組合（async generator over `(event_name, data)`），以及 ADR-437 D7 的編號步序。差別在於：現在步序寫死在 `create_response` 裡，由 AST contract test 鎖住，例如 `test_tool_governance_is_step_1_3_between_the_tool_results_and_the_input_rail`；改成登記表之後，順序約束本身變成資料，可以由 gate 檢查。

### 6.5 元件 5：結束點與記帳 hook

- 單一的 `on_terminal(outcome, usage)` 同時餵給 ledger、execution 稽核和 routing 回饋。
- **用量由轉接層負責抽取**，功能不碰原生事件。這樣就不會再有 #5680 那種「只從一種終止事件取用量」的錯。
- 一定要涵蓋 `COMPLETED`、`INCOMPLETE`、`FAILED`、`CLIENT_DISCONNECT`。斷線的設計在 #5726（PRD-313 Am.E、C-284-29）已經 merge，實作還沒做。
- **Rev.2：LiteLLM 的對應做法**（§15.4）：
  - 用單一函式 `_transform_response_api_usage_to_chat_usage`（`litellm/responses/utils.py:1142-1250`）把 Responses 的 usage 轉成共同的 Usage，`cached_tokens`、`cache_write_tokens`、`reasoning_tokens` 都會轉。
  - 三種終止事件都記帳；終止事件缺 usage 時用估算補上。
  - **算不出成本就大聲失敗**：拋 "Cost tracking failed" 並發告警（`litellm/proxy/hooks/proxy_track_cost_callback.py:436-470`）。這正是我們 #5136 能拖好幾個月的反面：我們是默默不記。建議 `on_terminal` 也照這個規則。
  - LiteLLM 自己也有洞，例如 client 斷線時的部分計費對 Responses 可能失效，fallback 合併 usage 時丟掉 cached 細項。這再次證明 gate 只能檢查「有沒有接」，數字對不對還是要靠真元件 probe。
- 權威契約：ADR-423（`docs/adr/ADR-423-budget-usage-durable-ledger-retry-then-reject-accept.md`）、ADR-489（`docs/adr/ADR-489-usage-ledger-single-metering-record-iam-only-pricer.md`）、SPEC-302（`docs/spec/SPEC-302-single-metering-record-and-pricer-behavioral-contracts.md`）。

### 6.6 元件 6：能力旗標與明確降級

每個轉接層宣告自己的能力；每個功能宣告自己需要哪些能力。不相符時，依功能的宣告**明確報錯**，或**照文件降級並留稽核**，不准默默失效。

| 能力 | chat | messages | responses（Codex 式：`store=false`、重送全部歷史） | responses（chain：`store=true` 加 `previous_response_id`） |
|---|---|---|---|---|
| `sees_full_history` | ✅ | ✅ | ✅ | ❌ 只看得到新的 item |
| `can_rewrite_history` | ✅ | ✅ | ✅（寫回 input items） | ❌ |
| `can_hold_text` | ✅（但 chat 串流的 output rail 現在只觀察，ADR-303、INV-318-7） | ✅ | ✅（buffer 模式） | ✅ |
| `can_hold_tool_calls` | ✅（`ToolCallsEvent` 本來就是累積後才送） | ✅ | ⚠️ 技術上可行，尚未實作（§10 Q3） | 同左 |
| `can_block_in_stream_without_retry` | ✅（OpenCode 不重試） | ⚠️ Claude Code 會改送非串流加 auto 重送（C-304-158） | ❌ 目前所有串流內的格式都會讓 Codex 重試 5 次（#5669） | 同左 |
| `tool_execution_visible` | client 執行 | client 執行 | function 由 client 執行；hosted 工具由 provider 執行（看不到） | 同左 |
| `reasoning_visible` | `reasoning_content` 透明轉送（ADR-056） | — | ❌ `encrypted_content` | ❌ |

這張表的具體數值要在 research 階段逐格實測確認（§10）。

### 6.7 元件 7：API 面對齊登記表加 CI gate

把 `usage-ledger-surface-parity-gate` 的概念一般化：用一份登記表（例如 `docs/governance/surface-parity.yaml`，**名稱待定**）記錄每個治理功能在每個 API 面上的狀態。

```yaml
tool_governance.response_block:
  chat: implemented        # GW/tool_governance_response.py
  messages: implemented    # via chat
  responses: deferred      # issue: ADR-490 v1.1；必須附 issue 或 ADR 章節
guardrail.output_block:
  chat: observe_only       # INV-318-7
  responses: buffer_only   # ADR-437 D1
```

**gate 規則**（草案）：
- 新增 hook 註冊時，必須在登記表補齊每個 API 面的狀態。
- 狀態只能是 `implemented`／`observe_only`／`not_applicable`／`deferred`；`deferred` 必須附 issue。
- `implemented` 的格子要能對應到一個 contract test，或 §8.1 的真元件 probe。

**限制**：gate 只能檢查「有沒有登記」「有沒有接」，**不能檢查行為對不對**，#5680 就是例子。行為正確性仍要靠真元件 probe。

**Rev.2：LiteLLM 的教訓（§15.5）**
- LiteLLM 有一份 e2e 覆蓋率登記表（`tests/e2e/coverage_registry/`），每個行為一格，用 `exercised_on` 標出測過哪些 API 面。但它**只衡量、不強制**，結果大多數 reliability 格子只標了 `[chat_completions]`（`reliability.yaml:2-16`）。登記表只讓缺口「看得見」，不會讓缺口「關得上」。所以我們的登記表必須配一個會紅的 gate。
- LiteLLM 的缺口幾乎都來自**逃生門**：
  - 讓 guardrail 繞過轉接層、直接碰原生格式的 `use_native_lifecycle_hooks`。
  - 某個模式只支援 chat 時，在 Responses 上**默默降級**（`incremental_diff` 退回 `block_only`）。
  - `call_type` 解不出來時 fail-open。
- 所以登記表 gate 還要再加三條規則：
  1. 繞過轉接層的功能必須逐一登記並附理由。
  2. 能力不符時不准默默降級，必須留稽核或報錯。
  3. 解不出 API 面時一律 fail-closed。

### 6.8 元件 8：擋下格式按「API 面 × client」各實測一次，之後共用

| API 面 × client | 串流前 HTTP 4xx | 串流內擋下 | 已知事實 | 來源 |
|---|---|---|---|---|
| chat × OpenCode | 400 不重試 | R-A in-band error，不重試 | 錯誤文案不得含 429、5xx、timeout、rate limit 等重試字串（C-304-157） | `docs/research/poc/agent-tool-governance-probes-2026-10-01/` P7 |
| messages × Claude Code | 400 會顯示 `message`；本 session 觀察到 2 個請求，各留一筆稽核 | 串流被擋後會改送非串流，auto 模式會再送一次，一輪可能 2 到 3 個請求 | 每個請求各自判定、各自稽核（C-304-158） | 同上；`RESEARCH-agent-client-block-status-retry-behaviour-2026-09-15.md` |
| responses × Codex | **只有 400、429 是終止狀態**；451、403、422 都重試 5 次（#4854） | `event: error`、`response.incomplete`、`response.failed(tool_call_denied)` 都重試 5 次（P7、#5669） | v1.1 的候選格式：`response.completed` 加 refusal，或 `response.failed(invalid_prompt)`，**都還沒實測** | ADR-490 §7.4 P7；D2 |

**做法**：把實測結果寫成 renderer 的一張表，所有功能共用。新的 client 或新的 client 版本出現時，只需要補測這張表，不用每個功能各測一次。

**Rev.2：LiteLLM 給了 #5669、#4854 一個具體的候選格式**（§15.3，`litellm/llms/openai/responses/guardrail_translation/handler.py:1505-1670`、`1773-1793`）

LiteLLM 的 guardrail 在 Responses 串流中途擋下時，**不送錯誤，而是「接續、正常結束」**：

1. 先關閉還開著的 output item：
   - message item 以 `completed` 關閉，內容是 client 已經收到的文字。
   - function_call 這類 item 以 **`status: "incomplete"`** 關閉，讓 client 不能據此執行（程式註解原文：*"can never authorize acting on it"*）。
2. 送出一組完整的新 message item（`output_item.added` → `content_part.added` → `output_text.delta`／`.done` → `content_part.done` → `output_item.done`），內容是擋下的說明。
3. 用 **`response.completed`** 結束：沿用同一個 response id，`sequence_number` 接續，並帶真實 usage。
4. 如果串流還沒開始，就直接送一整組合成的事件序列，從 `response.created` 到 `response.completed`。

一般的 provider 錯誤則走另一條：送 `event: response.failed`，沿用同一個 response id，`sequence_number` 接續（`litellm/proxy/common_utils/responses_stream_errors.py:139-171`）。

**對我們的意義**：
- 這個「completed 加替換 item」的格式很可能讓 Codex 不重試，因為從 Codex 的角度看，這一輪是正常結束的。
- 把 function_call 標成 `incomplete`，正是我們 Tool 規則 v1.1 回應端需要的「讓 Codex 不執行」。
- 但 **LiteLLM 程式碼裡沒有任何針對 Codex 重試行為的測試或註解**，所以必須用我們的攔截器對真 Codex 0.154 實測（§10 Q2、Q13）。
- 我們在 ADR-490 P7 已經實測過：`response.failed(tool_call_denied)` 會讓 Codex 重試 5 次。所以 LiteLLM 用 `response.failed` 收尾一般錯誤的做法，在 Codex 上很可能同樣會重試，不能直接照抄。

### 6.9 元件 9：request schema 不准默默丟欄位

- 問題：`GW/routes/responses.py:185` 的 `ResponsesCreateRequest` 用 pydantic 預設的 `extra="ignore"`，已經有至少五個欄位被默默丟掉過（§4.3 (d)）。
- 兩個選項，要在 research 階段決定：
  1. 未知欄位原樣轉送給 provider（透明轉送的精神），只有明確要治理的欄位才解析。
  2. 明確的 allowlist 加 `extra="forbid"` 或記錄丟掉了什麼，再配一個 gate：OpenAI Responses 的 request schema 有、而我們沒處理的欄位，必須登記成「轉送」或「拒絕」。
- 同樣的問題可能也存在 chat、messages 的 request model，要一起查。
- **Rev.2：傾向選項 1。** LiteLLM 原生路徑用 TypedDict 白名單（`ResponsesAPIOptionalRequestParams`，`litellm/types/llms/openai.py:1279-1310`；判斷式在 `litellm/utils.py:4199-4213`），不在白名單的頂層欄位**同樣會被默默丟掉**，跟我們是同一類 bug（§15.6）。
  - 它靠兩個逃生口補救：`allowed_openai_params` 和 `extra_body`（原樣併入請求）。
  - 這證明「白名單加逃生口」擋不住這類 bug。建議改成：預設轉送未知欄位，用明確的黑名單擋掉不該送的；丟棄任何欄位都要記 log 或留稽核。

---

## 7. 替代方案比較（依 CLAUDE.md §11，寫成情境）

| 方案 | 內容 | 適合的情境 | 不適合的情境 | 判斷 |
|---|---|---|---|---|
| A. 維持現狀 | 每個功能自己移植到 Responses（ADR-437 的模式） | 功能很少、Responses 流量小 | 功能持續增加；Codex 是錨定客戶（ADR-437 §3.1） | 已經證實會一直落後一版，而且會默默漏接（§3） |
| B. 把 Responses 正規化成 chat | 入口翻成 chat、出口重建 `response.*` | 協定很穩定、client 不挑剔 | Codex 對事件格式非常挑；伺服器端狀態、加密 reasoning、hosted 工具無法對應 | **ADR-339 已否決**（替代方案 B） |
| C. 改以 Responses 為內部標準格式 | chat、messages 翻成 Responses items | 長期看 OpenAI 往 Responses 走 | 要重寫整條 chat 管線，風險和成本都最高；Anthropic、vLLM 等 provider 都不是 Responses 原生 | 可以列為遠期研究，不建議現在做 |
| D. 只加 API 面對齊 gate | 不動架構，只強制登記 | 想先止血、成本最低 | 不減少重工；每個功能還是要寫兩次 | 單獨做不夠，**但是 E 的一部分** |
| **E. 推薦** | §6：中立契約、轉接層、決策與呈現分離、能力旗標，加上 D 的 gate，分階段遷移 | 功能會持續增加；要保留 wire fidelity；要能逐步上線 | 若 research 證實雙通道成本過高，或扣住 tool call 會破壞 Codex，就要調整 §6.2、§6.3 | **推薦**，但要先過 §10 的研究問題 |

---

## 8. 本質限制：解決不了，只能明確宣告

| 限制 | 為什麼解不了 | 推薦方案怎麼處理 |
|---|---|---|
| 伺服器端歷史 | chain 請求的歷史存在 provider 那邊 | 能力旗標 `sees_full_history=false`；需要完整歷史的功能明確降級或拒絕 |
| hosted 工具由 provider 執行 | gateway 不在執行路徑上 | 只能治理「宣告」；文件與對外說法要寫清楚（同 P16 的教訓） |
| 加密 reasoning | 內容不透明 | 永遠不碰；failover 時注意憑證邊界（#4878） |
| client 重試行為 | client 的行為不受我們控制 | §6.8 的實測矩陣；client 改版就重測 |
| 要看全文才能判斷 | 不管哪個 API 面，都得先扣住輸出 | 用首字延遲換覆蓋率，由 policy 決定，例如 `output_redaction_mode` |
| API 面寫死在模型身分裡（#2783） | 是模型資料模型的問題，不是管線問題 | 本案不處理；轉接層的 routing hook 要能接受「每個 API 面有不同的候選池」 |

---

## 9. 遷移路徑（建議，等 research 確認）

每一階段都要有：PRD 驗收條件、ADR invariant、SPEC contract test、§8.1 真元件 probe、ADR-093 五列表。

| 階段 | 內容 | 第一個使用者 | 退出條件 |
|---|---|---|---|
| **P0** research | 回答 §10 的問題；產出 `docs/research/RESEARCH-*.md`；跑 §6.8 的擋下格式實測 | — | 擋下格式定案；能力表實測過；外部證據查完 |
| **P1** 回應端 hook | `Observation`、`StreamDecision`、Responses 的 tool-call 扣住點，以及 renderer 的擋下格式表 | **Tool 規則 v1.1 回應端**（ADR-490 Q3 說的「共用的門」） | Codex 對被禁 tool call 不執行、不重試；chat 與 messages 改走同一個 hook 且行為不變（回歸測試） |
| **P2** 結束點 | `on_terminal` 統一記帳與稽核，含斷線 | 成本（#5726 的斷線實作）、guardrail output 搬過來 | 兩個面的記帳由同一個函式完成；`usage-ledger-surface-parity-gate` 改成檢查 hook 註冊 |
| **P3** 請求視圖 | `ConversationView` 加上各 API 面的 adapter；把 `request_text.py`、`guardrail_input_surface.py`、`guardrail_detection.py` 的散裝函式收斂進來 | guardrail input、Tool 規則請求端 | 共用模組裡的 API 面分支數明顯下降（§4.2 的量表當基線） |
| **P4** 對齊登記與 gate | §6.7 的登記表與 gate；§6.9 的 schema gate | 所有功能 | 新增功能少一個 API 面的狀態，CI 就紅；dogfood：對植入的回歸變紅 |

**順序理由**：
- P1 先做，因為它有一個正在等的真實使用者（Tool 規則 v1.1），也能順便解掉 #5669、#4854 的擋下格式問題。
- P3 的範圍最大，放在已經有兩個 hook 驗證過設計之後。

**Rev.2：P0 研究要多驗兩件事，這兩件會影響 P1 的形狀。**
1. LiteLLM 的「completed 加替換 item，function_call 標 `incomplete`」格式在真 Codex 上會不會重試、會不會執行被標成 incomplete 的 function_call（Q13）。
2. 把 commit point 延到第一個輸出事件，能不能和我們的 binding INSERT 時機相容（Q14）。

如果 Q13 成立，P1 的 Responses renderer 可以直接採用這個格式，#5669、#4854、Tool 規則 v1.1 回應端三件事就由同一個實作解掉。

---

## 10. 給 research agent 的研究問題

| # | 問題 | 為什麼重要 | 建議做法 |
|---|---|---|---|
| Q1 | 業界 gateway 怎麼治理 Responses？（LiteLLM、Portkey、Kong AI Gateway、Cloudflare AI Gateway、OpenRouter 等） | §17.1b 要求外部證據；確認「中立契約加轉接層」是否已是業界定論，或有更好的做法 | **Rev.2：LiteLLM 已讀原始碼（§15）**；Portkey、Kong 等還沒查。先讀 `docs/research/研究智庫-HUB.md`，再上網對抗式查證；LiteLLM 的結論也要對照它的官方文件與 issue tracker 再驗一次 |
| Q2 | 哪一種串流內的擋下格式能讓 Codex 不重試？候選：`response.completed` 加 refusal、`response.failed(invalid_prompt)`，或其他 | 卡住 guardrail 和 Tool 規則（#5669、#4854） | 用 `/Users/peter/Desktop/testing/tool_gov_interceptor.py` 的 `--block-on-tool-call SHAPE` 對真 Codex 0.154 實測；參考 P7 的做法 |
| Q3 | 扣住 `response.output_item.added(function_call)` 與 `function_call_arguments.*`，再放行或擋下，會不會破壞 Codex 對 `output_index`／`sequence_number` 的期待？ | 決定 `can_hold_tool_calls` 能不能成立 | 用攔截器模擬扣住再放行，對真 Codex 跑 |
| Q4 | 雙通道（verbatim 加推導觀察）的效能成本 | 每個事件多一次推導；Codex 的串流事件很多 | 對 `GW/responses_stream.py` 做 micro-benchmark |
| Q5 | OpenAI Responses 事件 schema 的演進風險：新的 item type 出現時，推導規則怎麼 fail loud？ | 透明轉送的好處是不用跟著改，觀察通道卻要跟著改 | 查 OpenAI 的 changelog；設計「未知 item type」的預設行為（觀察成 `OTHER_OPAQUE` 並留稽核） |
| Q6 | embeddings、audio（`GW/routes/embeddings.py`、`transcriptions.py`、`tts.py`）要不要納入同一套契約？ | #5136 也漏了 embeddings 的記帳；它們是第四、五條 API 面 | 盤點它們的 hook 需求（大概只有 `on_request`、`on_pre_dispatch`、`on_terminal`） |
| Q7 | 與 #2783（API 面寫死在模型身分裡）的邊界 | routing hook 要能處理「每個 API 面不同的候選池」 | 讀 #2783 與 `GW/cross_surface.py`、`GW/routing_adapter.py` |
| Q8 | 與 ADR-427 草案（PR #3978，June）的關係：回應端「共用的門」怎麼讓兩案都接 | ADR-490 Q3 已決定兩案共用回應端的門 | **只讀不動** #3978；讀 `docs/adr/ADR-490-tool-governance-policy-kind.md` 的 Q3 與組合規則 |
| Q9 | chat 串流的 output rail 為什麼只觀察（INV-318-7）？中立契約下能不能讓 chat 也用 HOLD？ | 能力表裡 chat 的 `can_hold_text` 是「理論可行、實際只觀察」 | 讀 `docs/adr/ADR-303-guardrail-output-path-coverage.md`、`ADR-318-guardrail-v2-in-gateway-llm-classifier.md` |
| Q10 | request schema：轉送未知欄位，還是 allowlist 加 gate？chat 和 messages 是否也有默默丟欄位？ | §6.9 | 對照 OpenAI 的 Responses、Chat Completions 與 Anthropic Messages 的 request schema |
| Q11 | 現有 contract test 與 AST gate，遷移時要怎麼轉成「登記表加 gate」而不失去保護？ | §4.4；guard 永不靜默刪（`/flow-gate`） | 盤點 `apps/gateway/bustream/tests/contract/` 與 `.github/scripts/` |
| Q12（Rev.2） | Codex 0.154 能不能接受只有 `data:` 行、沒有 `event:` 行、結尾補 `[DONE]` 的 Responses 串流？（LiteLLM 就是這樣送） | 決定 renderer 能不能重新序列化事件；也澄清 ADR-339 的「Codex 非常挑」到底挑在哪 | 用 `tool_gov_interceptor.py` 改寫 frame 後對真 Codex 跑 |
| Q13（Rev.2） | LiteLLM 的擋下格式（關閉開著的 item、function_call 標 `incomplete`、補一個說明 item、`response.completed` 結束）在真 Codex 上：會不會重試？會不會執行被標成 incomplete 的 function_call？使用者看得到說明嗎？ | 這是 #5669、#4854、Tool 規則 v1.1 回應端的共同解 | 攔截器新增一個 `--block-on-tool-call` 格式，照 `litellm/llms/openai/responses/guardrail_translation/handler.py:1505-1670`、`1773-1793` 產生事件 |
| Q14（Rev.2） | commit point 能不能從「第一個事件」延到「第一個輸出事件」，像 LiteLLM 那樣先扣住 `response.created`／`in_progress`／`queued`？ | retry 與 fallback 窗口變大（LiteLLM `litellm/router.py:620-627`、`3343-3352`） | 對照我們 `GW/responses_resilience.py` 的 sentinel 與 binding INSERT 時機（INV-437-1） |
| Q15（Rev.2） | 要不要學 LiteLLM，讓三條 API 面共用同一個請求處理函式（`base_process_llm_request(route_type=...)`），只把差異留在兩端？ | 比 hook 登記表更強的收斂；但會 amend ADR-437 D7 更多 | 讀 `litellm/proxy/common_request_processing.py`、`litellm/proxy/response_api_endpoints/endpoints.py`，對照我們的 `execute_chat` 與 `create_response` |

---

## 11. 設計閉環要求（CLAUDE.md §17.1、§17.4）

- **PRD**（`/doc-prd`）：商務需求是「新治理功能在所有 API 面一致生效、不再有沉默缺口」。驗收要斷言**可觀察屬性**，例如「Codex 對被禁 tool call 不執行」「預算在 Codex 流量下有扣」，不要寫實作身分（§17.1a）。附 12 歲白話層（§17.1b）。
- **ADR**（`/doc-adr`）：決策 §6、替代方案 §7、invariant、ADR-093 五列表。
  - **它會 amend ADR-437 D7**（「只有一個 ingress，所以不做 seam」），並延伸 ADR-280。
- **SPEC**：hook 契約、Observation 推導規則、renderer 格式表、能力旗標、登記表 gate，以及 contract tests。
- **Core 對比表**：

| 領域 | Core 文件 | 關係 | 行動 |
|---|---|---|---|
| 01 Gateway & Streaming | `docs/adr/core/Core-ADR-01-Gateway-Streaming.md`、`docs/prd/core/Core-PRD-01-Gateway-Streaming.md` | 主領域；延伸 ADR-280，amend ADR-437 D7 | 新增條目 |
| 02 Policy & Authorization | Core-ADR-02、Core-PRD-02 | Tool 規則、guardrail 改掛 hook | cross-ref |
| 04 Audit & Observability | Core-ADR-04、Core-PRD-04 | `on_terminal` 統一稽核 | cross-ref |
| 06 Provider Integration | `docs/adr/core/Core-ADR-06-Provider-Integration.md` | worker 的觀察通道、request schema | cross-ref |
| 13 FinOps & Cost Governance | `docs/prd/core/Core-PRD-13-*.md` | 記帳 hook | cross-ref |

- **§8.1 真元件**：每個 hook 都要對真 worker（`ST/workers/*_responses_worker.py`、`openai_worker.py`）與真 client（Codex、Claude Code、OpenCode）證明 trigger 真的會發生。fake 只能模擬 dependency 失敗，不能模擬 orchestrator 的行為。
- **§8.3**：如果動到 IAM 的 schema，要遵守 expand/contract。

---

## 12. 檔案路徑總表

> 全部對 `origin/main` `1ab639567` 查證存在。`GW/` = `apps/gateway/bustream/gateway/`，`ST/` = `apps/gateway/bustream/streaming/`。

### 12.1 Gateway：入口與共用服務

- `GW/routes/chat.py`（`execute_chat` :1079）
- `GW/routes/chat_helpers.py`
- `GW/routes/chat_streaming_audit.py`
- `GW/routes/chat_agent.py`
- `GW/routes/messages.py`
- `GW/routes/responses.py`（`ResponsesCreateRequest` :185，`create_response` 的步序在 :524-640）
- `GW/routes/embeddings.py`
- `GW/routes/transcriptions.py`
- `GW/routes/tts.py`
- `GW/chat_service.py`（ADR-280 的 `ChatRequestContext`、`ChatExecutionResult`）
- `GW/anthropic_translation.py`（ADR-239）

### 12.2 Gateway：chat 側治理模組（會被 hook 化）

- `GW/auth_handler.py`
- `GW/pre_execution.py`
- `GW/guardrail_policy_adapter.py`
- `GW/guardrail_handler.py`
- `GW/guardrail_detection.py`
- `GW/guardrail_input_surface.py`
- `GW/request_text.py`
- `GW/classifier_handler.py`
- `GW/admission_handler.py`
- `GW/routing_adapter.py`
- `GW/routing_decision.py`
- `GW/session_affinity_prefilter.py`
- `GW/slot_lease_adoption.py`
- `GW/slot_release.py`
- `GW/cross_surface.py`
- `GW/non_streaming_handler.py`
- `GW/sse_formatter.py`
- `GW/sse_transport.py`
- `GW/stream_termination.py`
- `GW/streaming_deadline.py`
- `GW/usage_ledger_hook.py`
- `GW/audit_helpers.py`
- `GW/chat_tool_governance.py`
- `GW/tool_governance_request.py`
- `GW/tool_governance_response.py`
- `GW/tool_governance_errors.py`
- `GW/tool_governance_decisions.py`
- `GW/tool_governance_projection.py`
- `GW/tool_name_matching.py`

### 12.3 Gateway：Responses 管線（17 個）

- `GW/responses_pipeline.py`
- `GW/responses_routing.py`
- `GW/responses_admission.py`
- `GW/responses_resilience.py`
- `GW/responses_output_rail.py`
- `GW/responses_output_checks.py`
- `GW/responses_input_guard.py`
- `GW/responses_stream.py`
- `GW/responses_execution_audit.py`
- `GW/responses_content_capture.py`
- `GW/responses_tool_calls.py`
- `GW/responses_tool_governance.py`
- `GW/responses_tools_filter.py`
- `GW/responses_graceful.py`
- `GW/responses_chain_validator.py`
- `GW/responses_iam_client.py`
- `GW/responses_delete_handler.py`

### 12.4 Streaming 與 worker

- `ST/manager_v3.py`
- `ST/manager_v3_events.py`
- `ST/manager_v3_workers.py`
- `ST/sse_event.py`
- `ST/state_machine.py`
- `ST/workers/openai_worker.py`
- `ST/workers/openai_responses_worker.py`
- `ST/workers/azure_responses_worker.py`（`stream_events` :410）
- `ST/workers/_named_sse_parser.py`
- `ST/workers/base_worker.py`
- `ST/workers/factory.py`
- `apps/gateway/bustream/backend/responses_bridge.py`（ADR-455 bridge）
- `apps/gateway/bustream/audit/schema.py`
- `apps/gateway/bustream/audit/xparse_bridge.py`

### 12.5 測試（`apps/gateway/bustream/tests/`）

- Responses 相關（unit／integration／contract，用 `git ls-tree -r --name-only origin/main apps/gateway/bustream/tests | grep test_responses_` 列出全部）：
  - `test_responses_governance_wiring.py`
  - `test_responses_route_integration.py`
  - `test_responses_resilience_real_worker_probe.py`（integration，真 worker probe）
  - `test_responses_slot_lifecycle.py`
  - `test_responses_output_rail.py`
  - `test_responses_admission.py`
  - `test_responses_routing.py`
  - `test_responses_execution_audit.py`
  - `test_responses_usage_capture.py`
  - `test_responses_tool_governance.py`
  - `test_responses_tools_filter.py`
  - `test_responses_platform_tool_strip.py`
  - `test_responses_tool_call_allowed_enforce.py`
  - `test_responses_tool_call_detected.py`
  - `test_responses_tool_call_resolved.py`
  - `test_responses_tool_loop_signals.py`
  - `test_responses_graceful.py`
  - `test_responses_truncated_stream.py`
  - `test_responses_workers.py`
  - `test_responses_bridge_seam.py`
  - `test_responses_bridge_decision.py`
  - `test_responses_model_addressing.py`
  - `test_responses_input_classifier.py`
  - `test_responses_chain_validator.py`
  - `test_responses_content_capture_2765.py`
  - `test_responses_delete_handler.py`
  - `test_responses_iam_client.py`
  - `test_responses_reasoning_field.py`
  - `test_responses_boundary_census.py`
  - `test_responses_tool_call_allowed_census.py`
- Tool 規則：`tests/{unit,integration,contract}/test_spec304_*.py`
- 本機跑法：用 ephemeral 容器，見 `/Users/peter/Desktop/X-parse/docs/agent-policy.md` §7.2。

### 12.6 CI gate（`.github/scripts/`）

- `usage-ledger-surface-parity-gate.py`
- `provider-call-usage-parity-gate.py`
- `guardrail-detection-surface-gate.py`、`guardrail-detection-surface-gate.sh`
- `tool-governance-parity-gate.py`
- `session-affinity-layer-gate.py`
- `conversation-scope-layer-gate.py`

### 12.7 文件（`docs/`）

| 類別 | 路徑 |
|---|---|
| Responses 架構 | `docs/prd/PRD-157-responses-api-phase1-gateway-governed.md`、`docs/adr/ADR-192-responses-api-phase1-architecture.md`、`docs/adr/ADR-339-responses-streaming-fidelity-transparent-passthrough.md`、`docs/spec/SPEC-234-responses-streaming-fidelity-behavioral-contracts.md`、`docs/adr/ADR-437-responses-surface-governance-parity-phase2.md`、`docs/spec/SPEC-282-responses-governance-parity-behavioral-contracts.md` |
| chat seam 前例 | `docs/adr/ADR-280-gateway-chat-governance-service-extraction.md`、`docs/spec/SPEC-208-gateway-chat-service-seam-behavioral-contracts.md`、`docs/adr/ADR-239-anthropic-messages-ingress-translation.md` |
| Routing | `docs/adr/ADR-430-routing-objective-two-axis-decomposition.md`、`docs/spec/SPEC-276-routing-objective-behavioral-contracts.md`、`docs/adr/ADR-447-session-affinity-pre-resolver-candidate-freeze.md`、`docs/adr/ADR-472-jev-tier-classification-routing.md`、`docs/spec/SPEC-294-jev-routing-behavioral-contracts.md`、`docs/adr/ADR-455-provider-parameter-combination-bridge-and-degradation.md` |
| Resilience | `docs/adr/ADR-260-resilient-dispatch-escalation-ladder-endpoint-pool.md`、`docs/adr/ADR-353-llm-proxy-cross-model-failover-and-resilience.md`、`docs/adr/ADR-427-slot-lease-registration-at-acquisition.md` |
| Guardrail | `docs/adr/ADR-303-guardrail-output-path-coverage.md`、`docs/adr/ADR-318-guardrail-v2-in-gateway-llm-classifier.md`、`docs/adr/ADR-448-guardrail-detection-surface-and-content-derived-tokens.md`、`docs/adr/ADR-476-jev-hosted-guardrail-judgement-source.md`、`docs/spec/SPEC-219-guardrail-pii-v1-contract.md`、`docs/spec/SPEC-223-guardrail-v2-contract.md`、`docs/spec/SPEC-224-guardrail-word-filters-contract.md` |
| 成本 | `docs/adr/ADR-423-budget-usage-durable-ledger-retry-then-reject-accept.md`、`docs/adr/ADR-489-usage-ledger-single-metering-record-iam-only-pricer.md`、`docs/spec/SPEC-302-single-metering-record-and-pricer-behavioral-contracts.md`、`docs/prd/PRD-313-wasted-spend-visibility.md` |
| Tool 規則 | `docs/prd/PRD-337-agent-tool-governance-policy.md`、`docs/adr/ADR-490-tool-governance-policy-kind.md`、`docs/spec/SPEC-304-tool-governance-behavioral-contracts.md`、`docs/runbooks/tool-governance-rollback.md` |
| 研究與證據 | `docs/research/RESEARCH-agent-client-block-status-retry-behaviour-2026-09-15.md`、`docs/research/RESEARCH-agent-tool-governance-proxy-enforcement-2026-09-30.md`、`docs/research/poc/agent-tool-governance-probes-2026-10-01/`（P2、P3、P7、P11、P16、P20，含攔截器）、`docs/research/poc/agent-tool-governance-local-verification-2026-10-01/`（D1 到 D4、P4、P15、P18） |
| Runbook | `docs/runbooks/responses-boundary-enforce-cutover.md` |
| Core | `docs/adr/core/Core-ADR-01-Gateway-Streaming.md`、`docs/prd/core/Core-PRD-01-Gateway-Streaming.md`、`docs/adr/core/Core-ADR-06-Provider-Integration.md` |

### 12.8 repo 外的筆記（`/Users/peter/Desktop/X-parse/docs/`）

- `cost.md`：成本系統全貌；Responses 在 §1、§gate 表。
- `issues/cost-issue.md`：每張 issue 的狀態。⚠️ rel 版本欄已過時。
- `guardrail.md`：guardrail 全貌；Responses 相關在 §3.8 與 OQ 表。⚠️ 部署狀態已過時。
- `LLM_PROXY.md`：模型定址與 routing；約 61 處提到 responses 或 codex。
- `agent-policy.md`：Tool 規則交接文件。
- `草案/agent-policy.md`：Tool 規則原始草案 Rev.4，只供歷史參考。

### 12.9 測試腳本與實測結果（`/Users/peter/Desktop/testing/`）

| 檔案 | 用途 |
|---|---|
| `tool_gov_agent_e2e.py` | 本 session 的三 client 實測腳本，指令有 setup／bind／use／run／probe／cleanup |
| `results/tool_gov_agent_e2e/README.md` | 本 session 的實測結果與清理紀錄 |
| `tool_gov_interceptor.py` | client 與 gateway 之間的攔截器，可以錄製、模擬拿掉工具（`--strip-tools`）、模擬擋下（`--block-on-tool-call SHAPE`） |
| `tool_gov_clients.py`、`tool_gov_claude_probe.py`、`tool_gov_codex_probe.py` | 三家 client 的乾淨執行環境配方 |
| `fake_responses_provider.py` | 假的 Responses provider，可以用來造出模型吐出被禁工具的情境 |
| `routing_responses_probe.py` | Responses routing 的 probe |

⚠️ Codex 的工作目錄要放在家目錄外，例如 `/private/tmp/...`。放在家目錄底下時，Codex 會把 `~/.codex/config.toml` 當成專案設定讀進來，帶入 `model_reasoning_effort` 與 MCP server。memory 筆記 `reference_codex_home_ancestor_config_leak.md` 有記。

### 12.10 Memory 筆記（`/Users/peter/.claude/projects/-Users-peter-Desktop-X-parse-xparse/memory/`）

- `project_responses_governance_parity_phase2.md`：ADR-437 全案。
- `reference_responses_shadow_audit_never_persisted.md`
- `reference_responses_surface_ignores_routing_strategy.md`：#3821，已修。
- `reference_chat_surface_filter_shrinks_routing_pool.md`
- `reference_codex_is_responses_only_and_stateless.md`
- `reference_agent_client_http_status_retry_behaviour.md`
- `reference_codex_home_ancestor_config_leak.md`
- `project_agent_policy_v1_design_closure.md`
- `project_param_combination_400_gap.md`：ADR-455 bridge。
- `project_cost_review_2026_09_29.md`
- `reference_cost_pricing_readwrite_inventory_2026_09_30.md`

---

## 13. Open issue 清單（2026-10-02 用 `gh issue view` 查證）

| Issue | 狀態 | 標題（摘要） | 屬於 §4.3 哪一類 |
|---|---|---|---|
| #2783 | OPEN | API 面寫死在模型身分裡，是定址衝突的結構根因 | (e) |
| #3822 | OPEN | chat 面被剔掉的指名模型，被默默換成別顆 | (e) |
| #4248 | OPEN | Responses 上的 `llm_judge_routing` 直接退回 heuristic | (a) |
| #4854 | OPEN | 451 讓 Codex 變成 6 次完整請求 | (c) |
| #4876 | OPEN | Responses 默默丟掉 `include` | (d) |
| #5222 | OPEN | 被 input classifier 擋下的請求仍付一次判級的錢 | (a)，兩個面都有 |
| #5458 | OPEN | 限流與 denylist 排在判官之後 | (a)，兩個面都有 |
| #5668 | OPEN | ADR-455 bridge 在 incomplete／failed 時丟掉已累積的 function calls | (b) |
| #5669 | OPEN | Responses 串流內的終止事件讓 Codex 重試 5 次 | (c) |
| #5670 | OPEN | Responses 默默丟掉 `tool_choice`、`parallel_tool_calls` | (d) |
| #1060 | OPEN | Responses 邊界檢查 shadow → enforce 的 rollout 追蹤 | ops |
| #4247 | OPEN | Responses semantic cache（ADR-437 D3 延後） | 設計延後 |
| #2551 | OPEN | chat 入口服務 Responses 模型（轉譯） | (e) |
| #5528 | OPEN | Responses → Chat 反向轉譯 | (e) |
| #5525 | OPEN | Foundry 與 Responses 的跨面轉譯 | (e) |
| #4878 | OPEN | R3 failover 可能把加密 reasoning 重放到另一個憑證 | (b)，未驗證 |
| #3677 | OPEN | Azure 憑證不符讓整個 app 的 validate 回 500 | (e) |
| #4405 | OPEN | Console 綁 Responses 模型時可能綁錯憑證 | (e)，未驗證 |
| #5672 | OPEN | Tool 規則的套用預覽（C-304-68）未交付 | IAM，非 API 面 |
| #5674 | OPEN | validate 熱路徑每個 kind 各讀一次 scope | IAM 效能，非 API 面 |

**2026-10-05 補充**（複查新發現，編號對應 `docs/進行中/v1-response.md`「2026-10-05 複查」）：

| Issue | 狀態 | 標題（摘要） | 屬於 §4.3 哪一類 |
|---|---|---|---|
| #5829（I1） | OPEN（已修 #5838，待部署驗證） | buffer 模式在 `response.incomplete`／`failed` 時放行沒檢查的全文 | (c) |
| #5830（I2） | OPEN（已修 #5838，待部署驗證） | buffer 模式不扣、不掃 tool call；被擋那輪的工具照樣執行 | (c) |
| #5831（I3） | OPEN（已修 #5847，待部署驗證） | chat 串流 buffer：有 tool call 的那輪跳過扣住檢查 | (c)，chat 面 |
| #5832（I4） | OPEN（已修 #5844，待部署驗證） | Responses 的 input 估算只讀 user 文字 | (b) |
| #5833（I5） | OPEN（已修 #5844，待部署驗證） | Responses 串流中途失敗／reaped 時 prompt 記 0 | (b) |
| #5834（I6） | OPEN（已修 #5842，待部署驗證） | 失敗嘗試記帳丟掉 cached tokens | (a)，三個面都有 |
| #5835（I7） | OPEN（已修 #5841，待部署驗證） | 開串流前 404／422／部分 403 仍讓 Codex 重試 | (c) |
| #5836（I8） | OPEN（已修 #5839，待部署驗證） | session 中途換到 DeepSeek thinking 會 400 | (e) 相鄰：跨模型 history |
| #5837（I9） | OPEN（已修 #5840，待部署驗證） | Responses 的 TTFT 量的是 `response.created` | (b) |
| #5671 | OPEN（已修 #5843，待部署驗證） | `tools[].type` 是 list／dict 時回 500（10-02 漏列） | (d) |

**2026-10-05 第二輪修補途中新發現**（都已修）：

| Issue | 狀態 | 標題（摘要） | 屬於 §4.3 哪一類 |
|---|---|---|---|
| #5852 | OPEN（已修 #5859） | 非串流 chat／messages 的 output 檢查不看工具參數 | (a)，非串流面 |
| #5853 | OPEN（已修 #5860） | `/v1/messages` tool `type` 非字串 → 500 | (d)，messages 面 |
| #5854 | OPEN（已修 #5858） | stream 模式工具呼叫回合結尾是 `stop` | (b)，chat 面 |
| #5861 | OPEN（PR #5870） | semantic cache 先寫、output rail 後檢查：被擋的回答被快取 | (a)，非串流面 |
| #5862 | OPEN（已修 #5867） | 非串流「文字＋工具呼叫」的文字被丟掉 | (b) |
| #5863 | OPEN（已修 #5869） | `/v1/messages` image `source`／`budget_tokens` 格式錯誤 → 500 | (d)，messages 面 |
| #5864 | OPEN（已修 #5868） | TC-264-42 計時測試在 CI 上 flake | 測試 |

> 這 7 個缺口有 5 個在 chat／messages 面，不在 Responses：§4 的「漏接是雙向的」再次成立。

已關閉、但可以當教案的：
- #3821：routing 沒跑。
- #4592：Codex 沒有 session affinity。
- #5136：沒記帳。
- #5680：用量取錯終止事件。
- #4250：graceful refusal；前提已被實測推翻，後續是 #5669。

---

## 14. 一段白話（給非工程讀者）

Xparse 像一個收發室，替公司管理所有寄給 AI 的信：檢查內容、決定交給哪個 AI、記帳、擋掉不該做的事。

大部分的信用的是同一種信封（chat）。收發室的每一道檢查，都是照著這種信封設計的。

Codex 用的是另一種信封（Responses），而且它很挑剔，信封只要被拆開重新包裝就拒收。所以收發室只能讓它原封不動地通過。

結果，每次收發室新增一道檢查，都得為這種信封另外再做一次。有幾次忘了做，Codex 的信就沒被記帳，或者沒被檢查。

這份文件提議的是：檢查員只負責判斷「這封信能不能過」，至於「怎麼在這種信封上執行這個判斷」，由每種信封各自的專人負責。以後新增檢查時，只要寫一次判斷，每種信封都會自動照做。真的做不到的地方（例如信封裡被加密的部分），會明確標示出來，不再默默跳過。

---

## 15. 外部對照：LiteLLM 怎麼處理（Rev.2，2026-10-03）

> **來源**：本機的 LiteLLM 原始碼 `/Users/peter/Desktop/research/lite-llm/litellm-versions/litellm-sep-29/`。
> - commit `39d14bd`，2026-09-28。
> - 下文路徑都相對於這個目錄。
>
> **方法**：三個調查 agent 讀原始碼，作者抽查以下幾處行號，確認與報告相符：
> - `proxy_server.py:9356-9359`、`9766-9772`：只送 `data:` 行，結尾補 `[DONE]`。
> - `router.py:618-628`：扣住輸出前的 lifecycle 事件。
> - `guardrail_translation/handler.py:1773-1795`：function_call 以 `incomplete` 關閉。
> - `tests/e2e/coverage_registry/reliability.yaml`：大多數格子只有 `chat_completions`。
>
> **限制**：
> - 全部是讀程式碼的結論，**沒有實際跑 LiteLLM**。
> - 沒有對照它的官方文件與 issue tracker。
> - 依 §17.1b，進 ADR 之前要再對抗式查證一次。

### 15.1 一句話結論

**LiteLLM 的解法跟本文 §6 的方向一致：用「共同的治理視圖」，不用「共同的傳輸格式」。** 它的缺口幾乎都出在「逃生門」與「默默降級」，這正好告訴我們 §6.7 的 gate 要多管哪些事。

### 15.2 架構：一條處理路徑，差異只留在兩端

- **三條 API 面共用同一個請求處理函式**：`ProxyBaseLLMRequestProcessing.base_process_llm_request`，只差 `route_type` 參數。
  - `/v1/responses` 用 `route_type="aresponses"`（`litellm/proxy/response_api_endpoints/endpoints.py:194-386`）。
  - `/chat/completions` 用 `"acompletion"`（`litellm/proxy/proxy_server.py:11758-11764`）。
  - `/v1/messages` 用 `"anthropic_messages"`（`litellm/proxy/anthropic_endpoints/endpoints.py:151-155`）。
- auth、budget、rate limit、pre-call 邏輯都共用（`litellm/proxy/common_request_processing.py:1910-2069`）。
- **沒有單一的內部標準格式**。`/v1/messages` 依 provider 分流（`litellm/llms/anthropic/pass_through/messages/handler.py:73-102`、`564-632`）：
  - 原生 provider：直接轉送。
  - OpenAI／Azure：走 Messages → Responses 的 adapter。
  - 其餘：轉成 chat。
  - 換句話說，chat 只是長尾 provider 的共同轉接點，不是整個系統的內部表示。
- **Responses 的 wire**：
  - HTTP 路徑會先解析事件、再重新序列化：只送 `data:` 行、不送 `event:` 行、`exclude_none` 刪掉 null 欄位、最後補 `[DONE]`（`proxy_server.py:9307-9313`、`9356-9359`、`9770-9771`）。
  - 未知事件型別落到 `GenericEvent`，所有事件類別都是 `extra="allow"`（`litellm/types/llms/openai.py:1884-1931`）。
  - response id 會被改寫成 base64，把 provider 與 deployment 編進去（`litellm/responses/utils.py:355-367`、`602-612`）。
- **兩條真正直通的路徑**：`/v1/messages` 的原生路徑原樣轉 bytes（`litellm/proxy/pass_through_endpoints/streaming_handler.py:196-209`）；Responses 的 WebSocket 路徑轉原始 frame，只在需要時 patch JSON（`litellm/responses/streaming_iterator.py:2035-2094`）。
- **雙向橋接**：
  - Responses → Chat：給沒有原生 Responses 的 provider 用，用狀態機合成 `response.*` 事件（`litellm/responses/litellm_completion_transformation/`）。
  - Chat → Responses：給只支援 Responses 的模型用（`litellm/main.py:1079-1190` `responses_api_bridge_check`、`litellm/completion_extras/litellm_responses_transformation/`）。
  - 用 `_skip_responses_api_bridge` 旗標防止來回打轉。
  - 這對應我們的 #2551、#5528、#5525。

### 15.3 Guardrail：「共同視圖」加上「各 API 面一個 translator」

- **新介面與 API 面無關**：`apply_guardrail(inputs: GenericGuardrailAPIInputs, request_data, input_type: "request"|"response")`（`litellm/integrations/custom_guardrail.py:1303-1331`）。
  - `inputs` 有 `texts`、`images`、`tools`、`tool_calls`、`structured_messages`、`model`、`stream_holdback_chars`（`litellm/types/utils.py:4511-4522`）。
  - 一個 guardrail 只要實作這個函式，就自動適用所有 API 面，由 `unified_guardrail` 負責呼叫（`litellm/proxy/guardrails/guardrail_hooks/unified_guardrail/unified_guardrail.py`）。
- **每個 API 面一個 `BaseTranslation`**（契約在 `litellm/llms/base_llm/guardrail_translation/base_translation.py:147-265`），依 `call_type` 自動註冊（`litellm/llms/__init__.py:83-162`）。
  - 職責：抽取、寫回、串流掃描、組擋下事件（`build_block_sse_chunks`）、組錯誤事件（`build_stream_error_items`）、抽取請求的工具名稱。
  - Responses 版在 `litellm/llms/openai/responses/guardrail_translation/handler.py`：
    - 把 `input` 轉成 chat messages 當 `structured_messages`，讓 guardrail 能把 function_call／output 當成 tool 訊息看。
    - 寫回時追蹤每則 message 來自哪個 input item，只 patch 被改到的部分（318-442）。
    - 寫不回去就拋 `UnappliableRequestRewrite`，fail-closed（528-534）。
  - **這就是本文 §6.1 `ConversationView` 加 §6.3 renderer 的實作版**，可以直接當設計參考。
- **決策怎麼表達**：沒有型別化的 Decision 物件，用三種方式表達：
  - 回傳改過的 inputs，代表遮罩。
  - 拋 `ModifyResponseException`，代表以 200 回應、內容換成擋下說明。
  - 拋 `HTTPException`，代表拒絕（`custom_guardrail.py:75-107`、`284-332`）。
  - 本文建議用型別化的 Decision，比較好做靜態檢查與 gate。
- **串流**（`unified_guardrail.py:1002-1237`）：
  - 預設是「觀察加抽樣扣住」：每個 chunk 立刻轉送，只有每第 5 個會等掃描結束；串流中的改寫會被丟掉。
  - `end_of_stream_only`：扣住終止事件，掃描後改寫 completed envelope，但先前送出的 delta 是原文。
  - `buffer_until_moderated`：全部扣住，**還在傳輸中的 tool call 會一直扣到最後掃描**（`base_translation.py:38-55`）。這對應我們的 `can_hold_tool_calls`。
- **擋下格式**：見 §6.8 的 Rev.2 段落，也就是「接續、正常結束」：關閉開著的 item、function_call 標 `incomplete`、補說明 item、用 `response.completed` 收尾。
- **commit point**：router 先扣住 `response.created`、`in_progress`、`queued`，等到第一個真正的輸出才放行（`litellm/router.py:620-627`、`3343-3352`），所以第一個事件送出後仍可以換 deployment。
  - 輸出開始前的斷線或提早 EOF，會轉成 `MidStreamFallbackError`（`litellm/responses/streaming_iterator.py:981-995`）。
  - 輸出開始後若收到 5xx 或 429 的 in-stream error，仍會帶著接續用的 input 去 fallback（`streaming_iterator.py:652-673`）。

### 15.4 路由、成本、預算：全部共用，Responses 只多一層「attempt 包裝」

| 我們的 bug | LiteLLM 的做法 | 會不會避開 |
|---|---|---|
| routing 沒在 Responses 跑（#3821） | `Router.aresponses` 是 `factory_function(litellm.aresponses, call_type="aresponses")`（`router.py:1893`）。它跟 `acompletion` 走同一條 fallback → retry → 選 deployment → cooldown（`router.py:5236-5258`、`7494`、`7629`、`7827`） | 會。但它也出過同類 bug：semantic auto-router 遇到 Responses 的 `input` 回 400（PR #37333），修好後才寫進 registry |
| Responses 沒記帳（#5136） | 同一個 success callback 處理所有 call type（`litellm/proxy/hooks/proxy_track_cost_callback.py:107-120`）；算不出成本就拋例外並告警（`:436-470`） | 會 |
| 用量取錯終止事件、沒讀 cached（#5680） | `_transform_response_api_usage_to_chat_usage`（`litellm/responses/utils.py:1142-1250`）轉 cached、cache_write、reasoning；completed、incomplete、failed 都記帳（`streaming_iterator.py:483-520`、`629-647`） | 會。但 fallback 合併 usage 時丟掉 cached 細項（`router.py:3127-3131`），斷線時的部分計費對 Responses 可能失效（`common_request_processing.py:425-427`） |
| 預算排在判官之後（#5450） | 預算在 auth 階段檢查並預留（`litellm/proxy/auth/user_api_key_auth.py:2994`、`3027`、`3113`），排在所有 pre-call hook 之前；依「是不是 LLM route」決定套不套用，不看 call_type（`auth_checks.py:922-925`） | 會 |
| 只能在第一個事件前 retry | 扣住輸出前的 lifecycle 事件，retry 窗口延到第一個輸出 | 大幅改善 |
| 擋下讓 Codex 重試（#5669、#4854） | guardrail 擋下用 completed 正常結束；一般錯誤用 `response.failed` | 擋下的部分很可能會避開，但**沒對 Codex 驗證**。`response.failed` 在我們的 P7 實測中會讓 Codex 重試 |
| sticky routing（Codex 無狀態） | `DeploymentAffinityCheck` 依 `previous_response_id` 解出 deployment 並釘住（`litellm/router_utils/pre_call_checks/deployment_affinity_check.py:373-387`）；id 本身編了 deployment，所以不用另存狀態 | 只適用有 `previous_response_id` 的情況，Codex 不送這個欄位；我們 ADR-447 Am.B 的做法另有用途 |

### 15.5 LiteLLM 自己的缺口（反面教材）

這些缺口幾乎全部來自兩種原因：**逃生門**（功能繞過轉接層，直接碰原生格式），以及**默默降級**。

1. `use_native_lifecycle_hooks`：讓 guardrail 走舊的 hook、直接碰原生事件（例如 `model_armor.py:129`）。結果這類 guardrail 在 Responses 上收到原始事件物件，自己又寫了一套 Responses 串流分類（`model_armor.py:82-88`、`937-947`）。
2. `incremental_diff` 只支援 chat，在 Responses 上**默默降級**成 `block_only`（`unified_guardrail.py:414-436`、`1054-1081`）。
3. `ToolPermissionGuardrail` 完全沒有 Responses 分支：
   - 只讀 `tool.function.name`，Responses 扁平的 tools 被忽略（`tool_permission.py:608-628`）。
   - post_call 遇到非 `ModelResponse` 就放行（`858-863`）。
   - 測試沒有任何 Responses 案例。
   - 這跟我們 Tool 規則在 Responses 回應端缺席是同一型的缺口。
4. `ToolPolicyGuardrail` 的信任鏈檢查讀 `request_data["messages"]`，在 Responses 上默默跳過（`tool_policy_guardrail.py:198-206`）。
5. Responses 的 WebSocket 模式完全繞過 translator 層（`litellm/llms/custom_httpx/llm_http_handler.py:6511-6533`）。
6. `call_type` 解不出來時跳過檢查，fail-open（`unified_guardrail.py:336-355`、`1110-1115`）。
7. Responses translator 缺 chat 有的功能：`skip_tool_message`、`scan_only_tool_results`；input 裡的 function_call 不進 `tool_calls`；`function_call_output` 的內容不進 `texts`。
8. **沒有任何 CI 測試強制 API 面一致**。只有一份 e2e 覆蓋率登記表（`tests/e2e/coverage_registry/`，`exercised_on` 欄位），用來衡量、不強制，大多數 reliability 格子只有 `[chat_completions]`。

**教訓**：只有轉接層還不夠。還要（1）禁止或登記逃生門，（2）禁止默默降級，（3）解不出 API 面時 fail-closed，（4）登記表要有會紅的 gate。這些已寫進 §6.7 的 Rev.2 段落。

### 15.6 欄位與狀態

- **欄位**：
  - proxy 層收的是原始 dict，這一層不掉欄位。
  - 原生路徑用 TypedDict 白名單（`ResponsesAPIOptionalRequestParams`），**不在白名單的頂層欄位會被默默丟掉**，跟我們是同一類 bug。
  - `include`、`tool_choice`、`parallel_tool_calls`、`prompt_cache_key`、`reasoning` 在白名單內。
  - 逃生口是 `allowed_openai_params` 與 `extra_body`。
  - 橋接到 chat 時，`include`、`store`、`truncation` 會被丟掉（`litellm/responses/litellm_completion_transformation/transformation.py:438-466`）。
  - → §6.9 Rev.2 傾向「預設轉送、黑名單、丟棄就留紀錄」。
- **伺服器端狀態**：
  - 原生路徑：狀態留在 provider；`previous_response_id` 解碼後轉發，router 釘住 deployment。
  - 橋接路徑：從 `LiteLLM_SpendLogs` 依 session 回放重建對話（`litellm/responses/litellm_completion_transformation/session_handler.py:90-160`、`266-320`）。這有寫入競態，需要重試迴圈；它也忽略 `store`，一律回報 `store: true`。
  - → 如果我們要做 Responses → Chat 的橋接（#5528），不要借用 spend log，要自建以 response id 為 key、會遵守 `store=false` 的儲存。

### 15.7 對照表：本文 §6 的元件與 LiteLLM 的對應

| 本文元件 | LiteLLM 對應 | 差異與建議 |
|---|---|---|
| §6.1 `ConversationView` | `GenericGuardrailAPIInputs` 加 `BaseTranslation.process_input_messages`、`get_structured_messages` | 它把 Responses input 轉成 chat messages 當共同視圖。我們可以參考，但 `ItemKind` 要保留「先看 type 再看 role」 |
| §6.2 觀察通道 | `process_output_streaming_response`、`get_streaming_scan_key`，加上抽樣、`end_of_stream_only`、`buffer_until_moderated` 三種模式 | 它沒有獨立的觀察型別，直接掃事件物件。本文的 `Observation` 型別較嚴謹 |
| §6.3 決策與呈現分離 | 決策用例外與改寫後的 inputs 表達；呈現在 `build_block_sse_chunks`、`build_stream_error_items` | 方向一致；本文建議型別化 Decision |
| §6.4 hook 登記表 | 同一個 `base_process_llm_request(route_type)` 加 `ProxyLogging` 的 hook 鏈 | 它的收斂程度比本文更強，三條面共用同一個處理函式（§10 Q15） |
| §6.5 結束點與記帳 | 單一 usage 轉換函式加單一 success callback；算不出成本就拋例外 | 照抄「fail loud」 |
| §6.6 能力旗標 | 沒有明確的能力旗標；能力不符時默默降級（缺口 2） | 本文的做法較好，要保留 |
| §6.7 對齊登記加 gate | e2e coverage registry，只衡量、不強制 | 本文要求 gate 會紅，並多加三條規則 |
| §6.8 擋下格式 | completed 加替換 item、function_call 標 incomplete；一般錯誤用 `response.failed` | 擋下格式是 Q13 的首選候選，要對真 Codex 驗證 |
| §6.9 schema | TypedDict 白名單加逃生口，同樣會默默丟欄位 | 反面教材，支持預設轉送 |

### 15.8 LiteLLM 關鍵檔案（相對於 `/Users/peter/Desktop/research/lite-llm/litellm-versions/litellm-sep-29/`）

- `ARCHITECTURE.md`、`AGENTS.md`（`:106` 要求遇到 API 面分歧時先找共用 helper）
- `litellm/proxy/common_request_processing.py`
- `litellm/proxy/response_api_endpoints/endpoints.py`
- `litellm/proxy/proxy_server.py`
- `litellm/proxy/utils.py`（`ProxyLogging`）
- `litellm/integrations/custom_guardrail.py`
- `litellm/integrations/custom_logger.py`
- `litellm/proxy/guardrails/guardrail_hooks/unified_guardrail/unified_guardrail.py`
- `litellm/llms/base_llm/guardrail_translation/base_translation.py`
- `litellm/llms/openai/responses/guardrail_translation/handler.py`
- `litellm/proxy/guardrails/_content_utils.py`
- `litellm/proxy/guardrails/tool_name_extraction.py`
- `litellm/proxy/common_utils/responses_stream_errors.py`
- `litellm/responses/main.py`
- `litellm/responses/streaming_iterator.py`
- `litellm/responses/utils.py`
- `litellm/responses/litellm_completion_transformation/`（transformation、streaming_iterator、session_handler）
- `litellm/completion_extras/litellm_responses_transformation/handler.py`
- `litellm/router.py`
- `litellm/router_utils/pre_call_checks/deployment_affinity_check.py`
- `litellm/proxy/hooks/proxy_track_cost_callback.py`
- `litellm/proxy/auth/user_api_key_auth.py`
- `litellm/proxy/hooks/parallel_request_limiter_v3.py`
- `litellm/types/llms/openai.py`
- `litellm/types/utils.py`
- `tests/e2e/coverage_registry/`（`README.md`、`schema.py`、`reliability.yaml`）
- `tests/test_litellm/proxy/proxy_server/test_streaming_helpers.py`
- `tests/router_unit_tests/test_router_aresponses_streaming_fallback.py`
