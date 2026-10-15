# 評審：〈解決 `/v1/responses` 的結構性落後〉Rev.2

> **日期**：2026-10-03
> **評審對象**：`docs/草案/解決-v1-response.md`（Rev.2）
> **基準**：`origin/main` `94090ec30`（唯讀 worktree：`/Users/peter/Desktop/X-parse/pr-worktrees/responses-coupling`）
>
> **本次新做的證據**：
> 1. 真 Codex `0.154.0` 本機實測 12 種擋下格式。不經 gateway、不打真模型、不用 key。
>    - 腳本：`/Users/peter/Desktop/testing/codex_block_shape_probe.py`
>    - 結果：`/Users/peter/Desktop/testing/results/codex_block_shape_probe/`（整組跑兩次，結果一致）
> 2. Codex 原始碼 `rust-v0.154.0`（`6b9826e3`），並比對 main `8f7a0f7a`（2026-10-03）。
> 3. gateway chat ↔ responses 接線逐項對照，涵蓋 24 個治理關注點。
> 4. LiteLLM `39d14bd` 與 Portkey gateway 原始碼複核（§3.6）。
> 5. OpenAI 官方 SDK 的 `response_create_params.py`（2026-09-24 版）。

---

## 0. 結論

1. **診斷正確，方向正確。** 中立契約、每個 API 面一個轉接層、決策與呈現分離、能力宣告，這四件事可以照走。
2. **有三處照做會出事**，都在 Rev.2 新增的段落：
   - LiteLLM 的擋下格式會讓**被禁工具照樣執行**（§2.1）。
   - refusal 格式在 Codex 上**整則訊息被丟掉**，使用者什麼都看不到（§2.2）。
   - 「未知欄位預設轉送」等於**治理 fail-open**（§2.3）。
3. **有兩處設計過重，或順序放反了**：
   - hook 登記表加宣告式排序 → 改成一條共用、在程式碼裡寫死順序的 pipeline（§3.1）。
   - gate 放在最後一階段 → 改成第一步就做跨面 conformance 測試（§3.2）。
4. **漏接是雙向的。** chat 串流的 output guardrail 與 V2 classifier 實際上從未生效，呼叫到的是 V1 退場後留下的 no-op；Responses 反而有接（§4）。所以根因是「兩份編排 × N 個功能」，不是「Responses 很特殊」。
5. **LiteLLM 與 Portkey 都沒解決這個問題，而且都在 Responses 上 fail-open**（§3.6）。草案把 LiteLLM 當成已驗證的參考，這個說法要降級。真正能擋住回歸的，是走真 dispatcher 的跨面測試。
6. **最貴的現行缺口不是架構問題。** prod 對 Codex 不扣 Budget，原因是 #5257、#5681 只進了 rel（`v1.79.0`），還沒進 prod（`v1.76.4`）。已重新用 `merge-base` 確認，這要靠部署解決。

---

## 1. 新證據：Codex 對擋下格式的反應

這一節回答了草案 §10 的 Q2、Q12、Q13，也回答了 Q3 的大半。

### 1.1 實測（Codex 0.154.0，本機假上游）

| 格式 | 請求數 | 工具被執行 | 使用者看得到說明 |
|---|---|---|---|
| 對照：正常文字 | 1 | — | — |
| 對照：正常 function_call | 2 | **是**（確認 probe 能偵測到執行） | — |
| 不送 tool-call frame，改送說明 message 加 `response.completed` | 1 | 否 | 是 |
| 同上，但終端事件的 `response.output` 仍列出 function_call | 1 | 否 | 是 |
| 送了 function_call 的 `added` 與 args，但不送 `output_item.done`，之後接說明加 completed | 1 | 否 | 是 |
| **LiteLLM 做法：function_call 以 `status:"incomplete"` 關閉，接說明加 completed** | 2 | **是** | 是 |
| 用 `refusal` content part，加 completed | 1 | 否 | **否（空白）** |
| `response.failed`，`code: invalid_prompt` | **1** | 否 | 是（顯示成 ERROR） |
| `response.failed`，`code: server_error` 或自訂 `tool_call_denied` | 6 | 否 | 是 |
| `response.incomplete`（content_filter） | 6 | 否 | 是 |
| `event: error` | 6 | 否 | 否 |

### 1.2 原始碼機制（`codex-rs/`，`rust-v0.154.0`）

- **只看 data，不看 `event:` 行。** 事件型別取自 data JSON 裡的 `type`；`data: [DONE]` 解析失敗後略過（`codex-api/src/sse/responses.rs:575,611-625`）。
  → **Q12 的答案**：Codex 接受只有 `data:` 行的串流。ADR-339 當年的致命問題是「完全沒有 `response.*` 事件」。
- **工具在 `response.output_item.done` 當下就 spawn 執行**，不等 completed（`core/src/stream_events_utils.rs:298-329`、`core/src/tools/parallel.rs:147`）。
  - 不檢查 `status`：`ResponseItem::FunctionCall` 根本沒有這個欄位（`protocol/src/models.rs:1042-1061`）。
  - 不讀 `response.completed.response.output`。
  - arguments 只取自 done item，`function_call_arguments.*` 事件被忽略。
- **`response.failed` 依 `error.code` 分類**（`sse/responses.rs:417-471`）：
  - 終止：`context_length_exceeded`、`insufficient_quota`、`usage_not_included`、`cyber_policy`、`misalignment_policy_violation`、`invalid_prompt`、`bio_policy`、`server_is_overloaded`、`slow_down`。
  - 其他 code 都會重試 5 次。
- **`response.incomplete` 一律重試**，不看 reason（:472-482）。**`type:"error"` 直接被忽略**，之後 EOF 變成 "stream closed before response.completed"，也會重試。
- **`refusal` content part 會讓整則 message 解析失敗**：`ContentItem` 沒有 refusal 這個 variant（`models.rs:856-874`），錯誤是 serde 的 unknown variant，整則被靜默丟棄。
- **完全不驗證 `sequence_number`、`output_index`、`item_id`**。delta 會掛在最後一個 `output_item.added` 上。
- **main 已經改了行為。** `incomplete(content_filter)` 變成「重試，並先往 history 塞一段提示」；`interrupted` 改成自動 follow-up。
  → 擋下格式表必須綁定 client 版本，Codex 升版就重跑 probe。

### 1.3 Responses × Codex 擋下格式表（取代草案 §6.8 Codex 那一列）

| 情境 | 用這個 | 不要用 |
|---|---|---|
| 串流前，硬拒絕 | HTTP **400** | 403、422、451（都重試 5 次，#4854） |
| 串流前或串流中，要讓使用者讀到說明 | 說明 message：`output_text` part，必須送 `output_item.done`；再接 `response.completed`，要有 `response.id`，`end_turn` 不得為 false | refusal part（看不到）、`response.incomplete`（重試） |
| 串流中，硬錯誤 | `response.failed`，`error.code = "invalid_prompt"` | `event: error`（被忽略後重試）、自訂 code（重試） |
| 擋下 tool call | 把該輪所有 function_call 的 `output_item.done` 扣住，等整輪判定完。擋下就丟掉這些 frame，補一則說明 message，再接 completed | 把 function_call 標 `incomplete`（照樣執行） |

**現行實作的狀況**：`responses_graceful.py:93-137` 的 graceful 拒答，用的是 `output_text` 說明訊息加 `response.incomplete`（函式叫 `_refusal_part`，但產生的其實是 `output_text`）。
- 說明看得到。
- 但終端是 `incomplete`，Codex 會重試 5 次，所以說明出現 6 次，最後 turn 還是失敗。

這就是 #5669。只要把終端改成 `response.completed`，就能修好這個問題。上表也可以一併修掉 #4854，而且正好是 Tool 規則 v1.1 回應端要用的格式。

---

## 2. 必改：照做會出事的三處

### 2.1 §6.8 Rev.2「function_call 標 `incomplete` 讓 Codex 不執行」——被實測與原始碼推翻

- Codex 不看 status，在 done 當下就執行（§1.1、§1.2）。照抄 LiteLLM 的話，Tool 規則回應端會「稽核寫擋下、實際照跑」。
- LiteLLM 那段程式碼的註解 *"can never authorize acting on it"* 對 Codex 不成立。
- 正確做法是讓 done **根本不送出去**。§6.2 的 Hold 必須涵蓋 `output_item.done`。

### 2.2 §6.8「`response.completed` 加 refusal」這個候選——Codex 看不到

- refusal part 會讓整則 message 被丟掉（§1.2），turn 照樣正常結束，但畫面是空的。說明一律用 `output_text`。
- 被擋的事實留在稽核裡（`finish_reason=content_filter`），不必放在 wire 上。

### 2.3 §6.9 Rev.2「預設轉送未知欄位」——治理 fail-open

**事實（接線對照）**
- `ResponsesCreateRequest`（`routes/responses.py:185-229`）只宣告 11 個欄位，預設 `extra="ignore"`，所以至少 16 個參數被靜默丟掉。轉給 provider 的 body 是從 model 重組的，不是 raw body。
- Codex 實際會送、卻被丟掉的有：`tool_choice`、`parallel_tool_calls`、`include`、`text`、`service_tier`、`client_metadata`。
  - `text` 被丟：Codex 的 `--output-schema` 靜默失效，`requires_json` 在這個面恆為 False。
  - `include` 被丟：加密 reasoning 回不到 Codex（#4876）。
- chat 是 `extra="allow"`，但 worker 逐欄映射，未知欄位**收下卻不送**。messages 只映射固定清單。三個面都在默默丟欄位。

**但「預設轉送」會放行以下欄位**（OpenAI SDK 2026-09-24 版）：
- `conversation`：官方說明是 *"Items from this conversation are prepended to input_items"*，provider 會在端上補入整段對話，input rail 看不到。
- `prompt`：template 內容存在 provider 那邊。
- `context_management`：provider 端壓縮上下文。
- `background`：脫離串流與記帳；我們沒有 GET，client 也無法輪詢。
- `service_tier`、`prompt_cache_options`：會改變價格。

此外，OpenAI 這份 schema 9 月就有 6 個 commit 動過它。

**建議**
- 每個欄位明確三分類：**治理後轉送**／**原樣轉送**／**拒絕 400**。分類寫成程式碼常數，不是文件。
- CI gate 對照「釘版的官方 SDK schema」：出現沒分類的新欄位就紅，升級 SDK 版本時一定會看到。
- 今天的對應：
  - 可以轉送：`tool_choice`（經 Tool 規則改寫後）、`parallel_tool_calls`、`include`、`text`、`top_p`、`truncation`、`metadata`。
  - 拒絕並寫清楚原因：`conversation`、`prompt`、`background`、`context_management`。
  - `service_tier` 要等計價支援才能轉。
- chat 和 messages 用同一套做法。

---

## 3. 建議調整

### 3.1 §6.4：不要做「hook 登記表加宣告式排序」，改成一條共用的 pipeline

- **依據**：接線對照顯示，pre-dispatch 的葉節點幾乎都已經是同一個函式，或共用核心外包一層薄 wrapper。例如 `enforce_budget_gates`、`admit()`、`authenticate_request`、`plan_request`、`run_input_classifier`、`decide_execution_policy`。**重複的只是編排**：`chat.py:1079-1763` 是 inline 寫法，`responses.py:516-626` 是分步寫法。
- **做法**：
  - pre-dispatch 一份、terminal 一份，順序直接寫在程式碼裡。
  - 每個 API 面的 adapter 只負責：文字讀取、tool arming、候選集過濾、拒絕的渲染。
  - 刻意不同的契約改成 adapter 參數：Kernel 預設 shadow、legacy 工具拒絕的先後、`pin > binding > affinity`、chat 的 cache 與 agent mode。
- 順序由**一支** AST 測試鎖住，取代現在兩邊各自一套。
- 宣告式排序等於自建一個小型依賴求解器：難讀、難 debug，違反 CLAUDE.md §1 的優先序 1 和 2。功能只有十幾個，一張寫死的清單就夠了。
- **主要阻礙**：`execute_chat` 是一個超過 2,000 行的 inline 函式，沒有可以注入的 seam。第一步要先把 pre-dispatch 和串流迴圈（`chat.py:247-317`）抽成接受 adapter 的函式。這是 ADR-280 Phase 1 刻意沒做的部分。

### 3.2 §9：把 gate 從最後一階段移到第一步，形式改成 conformance 測試

- **做法**：每個治理行為寫一支測試，自動對 chat、messages、responses 三個面各跑一次。
  - 已知缺口用 `xfail(strict=True)` 加 issue 登記；修好後若沒拿掉標記，`strict` 會讓 CI 變紅。
  - 這就是 §6.7 想要的登記表，但它是**從測試導出、而且會紅**，不是手寫 YAML。依 repo 的 monorepo 規則，手寫清單不能拿來證明自己是完整的。
  - 完整性要另外從程式碼導出，例如「每個治理 stage 都必須至少有一支 conformance 測試」。
- **為什麼放第一步**：
  - 它立刻止血，而且雙向都擋（§4）。
  - 它是後面所有重構的回歸網。
- 今天的測試全部是各面各寫一份，例如 `test_spec304_legacy_truth_table.py:203` 只參數化了 `["chat", "messages"]`，Responses 另外一段。這本身就是 coupling 的一部分。

### 3.3 §6.6：能力要依「請求 × client」決定，不是依 API 面

- `sees_full_history` 取決於請求有沒有 chain：`previous_response_id`、`conversation`、`prompt` 都算。
- 能不能擋而不被重試，取決於 client。
- 用 User-Agent 判斷 client 不可靠。好在 §1.3 的格式對所有 client 都安全，預設就用它，不需要依 client 分支。

### 3.4 §6.2：名稱層的判定不需要扣住文字

- function_call 的名稱在 `response.output_item.added` 就拿得到，名稱規則可以在第一個 frame 就判定。
- 要扣住的只有 `output_item.done`，因為 Codex 的觸發點在那裡。
- 但「整輪擋下」的語意要求：一輪裡只要有一個 call 被擋，其他 call 的 done 也不能送。所以要扣到該輪的終端事件為止。成本只有幾個 frame 的延遲。
- 參數層規則（ADR-427 草案）本來就要等到 `arguments.done`。

### 3.5 Q14 與 Q15

- **Q14（commit point 延後）：可行。**
  - binding 的 INSERT 綁在 worker 於 `response.created` 之前吐出的 sentinel 上（`azure_responses_worker.py:416-440`）。
  - 改成先扣住 `created`／`in_progress`，等到第一個輸出事件才 INSERT 並放行即可。
  - 好處：「`created` 之後馬上 `response.failed`」這種失敗也能 retry 或 failover。
  - 這件事與 decoupling 無關，建議另開一片。
- **Q15（三面共用一個處理函式）**：
  - pre-dispatch 與 terminal 共用：**要**，見 §3.1。
  - 串流段**不要**硬合。chat 的 output rail 寫在 StreamingManagerV3 的狀態機裡，Responses 是 passthrough 的 stage 鏈，「扣住再重發」的語意跟著 wire 走。
  - 串流段可以共用的是：R1/R3 的 commit 狀態機、`drive_with_idle_deadline`（任何 AsyncIterator 都能包，Responses 直接套上就有串流期限）、`judge_turn`、DETECTED 稽核。

### 3.6 LiteLLM 與 Portkey 複核：兩家都沒解決，而且都在 Responses 上 fail-open

草案 §15 說 LiteLLM 的做法「可以直接當設計參考」。複核後的結論是：**方向可以參考，實作不行**。標「probe」的結論是實際跑過程式碼驗證的。

**LiteLLM（`39d14bd`）**

| 草案的說法 | 複核結果 |
|---|---|
| 三個面共用 `base_process_llm_request` | 成立。但 **Responses WebSocket** 路徑幾乎繞過所有 hook（`response_api_endpoints/endpoints.py:1476-1602`） |
| 中立 view 加上每個面一個 translator | 只做到一半：<br>- 中立 view 其實是 chat 的形狀（`types/utils.py:4511-4522`）。<br>- 55 個 guardrail 模組裡，有 21 個沒實作 `apply_guardrail`，所以不走這條路，其中包含 `tool_permission`。 |
| 擋下格式：關閉開著的 item、補說明、用 completed 結束 | 細節有出入：<br>- 只關閉**最後一個**開著的 item。<br>- 擋下事件沒有 `sequence_number`。<br>- mid-stream 擋下時 usage 記 0（probe）。<br>- 預設的抽查模式下，上游的 function_call done 和 `response.completed` 可能已經先送出，擋下後又補送**第二個** completed（probe）。<br>- 終端 `output` 和 client 實際看到的不一致。 |
| buffer 模式會扣住 tool call | 會。但擋下時**另造一個新的 response id**，上游真正的 response 變成孤兒，之後用 `previous_response_id` 接續就會斷 |
| 解不出 call_type 時 fail-open | 成立，而且 pre_call、moderation、post_call、streaming 四個位置都放行 |
| 白名單加逃生口 | `conversation` 會被丟掉；`allowed_openai_params` 也救不回白名單外的欄位（probe） |
| — | **實例**：LiteLLM 自家的 `tool_permission` 設成 default-deny，chat 會擋，Responses 的 tools 和 function_call 輸出全部放行（probe） |
| — | translator 只從 `input`、`instructions` 抽文字，**抽不到就根本不呼叫 guardrail**。Agent loop 的典型回合（`previous_response_id` 加 `function_call_output`）和只送 `prompt` 的請求，都完全沒被掃到（probe） |
| — | 沒有任何跨面 parity 測試，也沒有任何機制強迫新的 call_type 被處理 |

**Portkey（`@portkey-ai/gateway` v1.15.2）**
- Responses 是同格式直通，不轉成 chat。request 參數走白名單，未知欄位同樣被丟。
- **guardrail 在 Responses 上根本不跑。** `shouldSkipHook` 只允許 chatComplete、complete、embed、messages 四種（`middlewares/hooks/index.ts:449-463`），所以 Responses 的 hook 一律被標成 skipped。deny 的判斷會忽略 skipped，client 也看不到。
  - node probe：同一個 deny guardrail，chat 會擋，Responses 直接放行。
- 設定 schema 卻允許使用者選 `createModelResponse`；外掛測試直接呼叫 handler，所以 CI 是綠的。

**對本案的意義**
1. 這不是業界已有定論的問題。**依 §17.1b 的標準，草案「LiteLLM 已驗證這條路」的說法應降為 WEAK。** 兩家的病和我們一模一樣，Portkey 更嚴重。
2. 兩家失敗的共同模式是：**handler 的單元測試綠燈，但真正的 dispatcher 沒有觸發**。這正好是 CLAUDE.md §8.1 的反例。所以 §3.2 的 conformance 測試必須走真 route 加真 pipeline，只在 provider 的 HTTP 邊界放 fake。
3. 有三條要寫進 ADR invariant：
   - 解不出 API 面，或功能沒登記某個面時，在政策已啟用的情況下 **fail-closed** 並留稽核。
   - 擋下時**沿用上游的 response id**，`sequence_number` 要連續，終端 `output` 要和已送出的事件一致，而且裁決出來之前不放出 terminal event。
   - 擋下時 usage 要記上游的真實值，不能歸零。整輪判定本來就要等上游的 terminal，所以這時已經拿得到 usage。
4. 伺服器端狀態（`previous_response_id`、`conversation`、`prompt`、hosted tools）要當成一等的「看不到的內容」，依政策明確 deny 或 flag。這和 §2.3 一致。

---

## 4. 草案沒列到的缺口

| 缺口 | 證據 | 建議 |
|---|---|---|
| **chat 串流的 output guardrail 與 V2 classifier 實際上從未生效**（Console 設了也無效；shadow 路徑只會記一筆永遠 pass 的 log） | chat 串流只呼叫 `GuardrailEnforcer.check_output`，包括 enforce 路徑（`ST/manager_v3_events.py:537/705`）和 manager 自己的 shadow 路徑（:43-69）。這個函式自 ADR-309 V1 退場後就是 pass-through（`guardrail_enforcer.py:352`）。真正的 `run_output_guardrail` 與 `run_output_classifier` 只有 `non_streaming_handler.py:1017/1058` 和 `responses_output_checks.py` 在呼叫。<br>既有的 #1508（OPEN）只講到「非 twin 路徑沒有 output rail」，其實連 twin 路徑也是 no-op。INV-318-7 寫的「audit-only」並沒有實作 | 擴大 #1508 的範圍，或另開一張 issue；修正 INV-318-7 的文字；登記成 conformance 測試的 xfail<br>**2026-10-04**：修補為 #5811（ADR-318 Amendment C，INV-318-7 改寫；conformance 的 #1508 xfail 移除） |
| Responses 少了 idle deadline、`streaming_allowed`、addressing 拒絕時的稽核、llm_judge | 接線對照（`responses_routing.py:261-288` 直接 short-circuit 掉 judge） | conformance 登記 |
| 至少 16 個 Responses 參數被靜默丟掉，含 Codex 的 `text`、`service_tier` | §2.3 | §2.3 |
| `store=true` 時擋下 tool call，下一輪 chain 會壞：provider 存的 response 裡有一個沒回覆的 function_call | 由 Responses 的 chain 語意推得，**未實測** | 擋下時刪除 provider 端狀態（沿用 `responses_stream.py:746-768` 的做法），或明確斷鏈 |
| graceful 拒答兩頭壞 | §1.3 | §1.3 |
| `binding_tap`（`responses_pipeline.py:815`）是死碼 | 接線對照 | 順手刪 |

---

## 5. 修訂後的方案與順序

| # | 切片 | 修什麼 | 為什麼排在這裡 |
|---|---|---|---|
| **S1** | Responses 擋下 renderer（§1.3） | #5669、#4854；graceful 與硬拒絕的格式 | 證據已經齊了；現在每擋一次都燒 6 倍請求，而且使用者看不到說明。**2026-10-03 已 merge、未部署**：PR #5750（merge commit `4031ef50a`，ADR-437 Amendment A） |
| **S2** | 跨面 conformance 測試加缺口登記（§3.2） | 不再有沉默缺口，雙向都擋 | 止血；後面所有切片的回歸網。**2026-10-03 已 merge**：PR #5756（merge commit `e6426d141`，ADR-492／SPEC-306）。35 支測試×三面，gate 從 40 個 `AuditEventType` 導出範圍。登記的缺口：#1508（chat／messages 串流 output rail）；Responses 的 #5751 idle deadline、#5752 丟 18 個欄位、#5753 回應端 Tool 規則、#5754 `streaming_allowed`、#5755 定址稽核、#4248、#4247、#1060 |
| **S3** | 欄位三分類加 schema 漂移 gate（§2.3） | #5670、#4876、`text`、`service_tier`；`conversation`／`prompt`／`background` 改回 400 | 小、獨立。**2026-10-03 已 merge、未部署**：PR #5757（`31cb414ea`，ADR-493／SPEC-307／PRD-157 §11）。Responses 12 欄轉送、4 欄 400、改價／未審／未知欄位記錄後剝除；`tool_choice` 只指向送出的工具；`include`＋R3 同憑證 guard（#4878 保守版）；chat／messages 只記錄；漂移 gate 對 openai 3.24.0／anthropic 1.11.0 |
| **S4** | terminal 合一 | 斷線記帳（#5726 已有設計）；usage 抽取集中一處 | ledger 已經是同一份，風險低。**2026-10-03 已 merge、未部署**：PR #5758（`55290309f`，ADR-439 Amendment E 的 gateway 端＋Amendment F／SPEC-284 C-284-31/32）。`gateway/terminal_usage.py` 一處解出三面的終止用量，事件與帳本讀同一個值；三面斷線都是 COMPLETED `client_closed`、帶模型與輸入（無回報用預算 preflight 的估算並標示）；chat 的 `StreamCancelled` 競態不再發 FAILED；非串流問 `is_disconnected()`。後續（2026-10-03 第二輪）：Audit `usage_outcome()` 已 merge（Xparse-Audit#197 `b841408`、xparse 指標 bump #5763 `b8e5204`，皆未部署）；`token_estimate_source` 依 Peter 決定改用 ADR-419 詞彙、原值搬到 `output_tokens_source`（#5764 `406c25a`，未部署）。真 client 驗證（工作 6，PR #5768）：A39 Claude Code Esc、A41、A42、OpenCode Esc 皆 PASS，帳本同數，Audit #197 分類器重算為取消；A40 Codex BLOCKED（本機 app 沒有 Responses 模型）。Console 報表畫面要等 Audit 部署 |
| **S5** | pre-dispatch 合一，從 `execute_chat` 抽出（§3.1） | (a) 類失敗從結構上消失 | 範圍最大，要等 S2 的回歸網就位。**2026-10-03 已核定**：ADR-494（#5759 設計、#5761 核定紀錄 `e2a190173`）修訂 ADR-437 D7；先抽 chat（P1）再接 Responses（P2），P2 缺口各自 PR，Q14 不納入。**2026-10-04 進度（皆已 merge、未部署）**：P0 #5762、P1 #5769、P2a #5770（Responses 步驟 1–1.2）、P2b #5771（Tool 規則請求端一份實作）、P2c #5773（input rail）、P2d #5779（`KnownGap` 機制、`store` stage；`request_policy` 在 Responses 為已知缺口 #5754）；缺口修補 #5776（#5755 定址稽核）。之後皆已 merge、未部署：#5780（#3822／#4558）、P2d-2 #5783、P2e-1 #5784、D-16 #5785、P2e-3 #5786（routing stage）、D-17 #5787、P2f-1 #5788（policy_kernel）、D-21 #5789、P2f-2 #5790（agent_mode、chain）、D-20 #5791、**P2f-3 #5792：P2 完成，`/v1/responses` 跑完整的共用 pipeline**、P2g #5793（每個 stage 都要有 conformance 測試）、#5754 修補 #5796（`streaming_allowed`）。P3（單一 terminal）：設計 #5794、P3b #5797、P3c #5798 皆已 merge，三個面的 COMPLETED 都由 `gateway/terminal.py` 先記帳再發；T-5 Responses 半 #5800（Responses 失敗帶 `error_status_code`）已 merge。P4：#5751 idle deadline #5795 已 merge；#5753 掛點等 S6。#4248（Responses 的 LLM 判官）依授權選 B（判官＝本面候選尾，經 Responses API 呼叫），#5804 已 merge；另依授權：Responses 治理 403→400（#5801）、T-4（#5802）皆已 merge、未部署 |
| **S6** | 回應端 observer 加 tool-call 扣住（§3.4） | Tool 規則 v1.1 回應端；chat 串流的 output rail | 用 S1 的 renderer、S2 的測試。**2026-10-03 前提狀態**：P7、P9 齊（P9 由 S1 回答：Codex 在 `output_item.done` 就執行，hold 必須擋在它之前）；P8、P10、延遲量測 BLOCKED——授權的 app 是 consumer，模型來自共用 proxy，沒有 Responses 模型。所以**還不能開工**。**2026-10-04**：Peter 在 proxy 加入兩顆 Responses 模型後量完前提（#5803：平行呼叫逐筆關閉、`store=true` 續輪 400、hold p95 ≤ 249 ms）；Responses 回應端 Tool 規則實作為 #5806（hold 到終端、整輪扣下為 E 類 `response.failed`、retire binding）。chat 串流 output rail（#1508）：ADR-318 INV-318-7 明文 buffer hook 等 shadow data，列為 Peter 的決定。**2026-10-04 第二輪（Peter 核准改寫 INV-318-7）**：A22 真 Codex 驗收 BLOCKED（#5810 已 merge；規則已刪、已還原）；#1508 實作 #5811（ADR-318 Amendment C：buffer 模式對 held 全文跑 PII rail → classifier 可擋，error＝R-A in-band `make_openai_error`、graceful＝拒答、fail-closed＝transient 503；stream 模式事後 observe-only；擋下記 COMPLETED＋`content_filter`＋健康成功）。OpenCode／Claude Code 對回放 frame 的反應與 P7 相同 |
| 並行 | prod 部署 #5257、#5681 | Codex 用量扣 Budget | ops 決定，跟架構無關 |

**設計閉環**：
- 傘狀 PRD 加 ADR：amend ADR-437 D7，延伸 ADR-280。
- 每一片各自的 SPEC 契約加測試。
- S1 只需要 amend ADR-437 與 SPEC-282，再附上本次的 probe 當 §8.1 證據。

---

## 6. 回答「以後的新需求能不能用同一套解法、不 coupling」

**可以**，但邊界要講清楚：

| 功能在哪一段 | 新功能要寫幾次 |
|---|---|
| 請求前（大多數功能）與結束點 | **一次**，三個面自動生效 |
| 串流中 | 決策寫**一次**。每個「API 面 × client」的 renderer 表各維護**一份**；新 client 或 client 升版時，只需要重跑 probe |
| 物理上做不到的事（provider 端歷史、加密 reasoning、hosted 工具） | 寫不了，只能**宣告**：明確拒絕，或降級並留稽核 |

保證機制是 conformance 測試：新功能的測試一寫好，就會對三個面都跑一次。不需要靠人記得。

---

## 7. 證據位置

- Probe：
  - 腳本：`/Users/peter/Desktop/testing/codex_block_shape_probe.py`
  - 結果：`/Users/peter/Desktop/testing/results/codex_block_shape_probe/run-2026-10-03.jsonl`、`run-2026-10-03-full.json`（含每個請求的摘要）
- 原始碼：`openai/codex` 的 tag `rust-v0.154.0`。路徑見 §1.2。
- LiteLLM／Portkey 的 probe 腳本：`/Users/peter/Desktop/testing/results/gateway_peer_probes_2026-10-03/`（LiteLLM 要在有 litellm 的 venv 跑；Portkey 的 `probe.ts` 用 node 在 gateway checkout 裡跑）。
- 接線對照：worktree `/Users/peter/Desktop/X-parse/pr-worktrees/responses-coupling`。行號以 `94090ec30` 為準。

---

## 8. 落地後複查（2026-10-05）

> **基準**：讀碼用 `origin/main` `c61161f41`；實測用本機最新 main `213fea709`（gateway 掛 source），真 Codex 0.154.0、Claude Code 2.1.289、OpenCode 1.18.34。
> **證據**：`~/Desktop/testing/results/responses_gap_probe/REPORT-2026-10-05.md`。缺口編號 I1–I9 與 `docs/進行中/v1-response.md` 一致，工作清單見 `docs/進行中/v1-response-checklist.md`。

### 8.1 本評審的建議，落地到哪裡

| 評審條目 | 落地 | 複查結果 |
|---|---|---|
| §1.3 擋下格式表 | S1 #5750、#5801 | ✅ 真 Codex 被擋時只送 1 次請求，說明訊息正確顯示。❌ 開串流前的 404／422／部分 403 不在表內，仍會重試（I7）→ **已修 404／422（#5841，ADR-437 Am.E）**；無 policy code 的 403 刻意不改 |
| §2.1 hold 必須涵蓋 `output_item.done` | S6 #5806 | ✅ 只在**有綁 Tool 規則**時成立。❌ output rail 的 buffer 模式沒有同樣的 hold，被擋那輪的工具照樣執行（I2）→ **已修（#5838，ADR-437 Am.D）** |
| §2.3 欄位三分類 | S3 #5757 | ✅ 讀碼確認 12 個轉送、4 個 400、其餘記錄後剝除；SDK 漂移 gate 已釘版 |
| §3.1 共用 pipeline | S5 #5762–#5793 | ✅ pre-dispatch 和 terminal 都是一份 |
| §3.2 conformance 測試 | S2 #5756 | ✅ known gap 只剩 #1060、#4247。❌ 本次的 I1–I3 都沒被它攔下，因為測試用的 fake provider 永遠以 `response.completed` 結束，也不會在同一輪混合文字和工具呼叫 → **已補（#5838）**：fake provider 新增 `incomplete` 終端與 `text_and_tool_call`；三面測試都有 dogfood（舊碼紅） |
| §3.6 invariant 2：「裁決出來之前不放出 terminal event」 | — | ❌ buffer 模式遇到 `response.incomplete`／`failed` 會直接放行 terminal，終端事件裡帶著沒檢查過的全文（I1）→ **已修（#5838）** |
| §3.6 invariant 3：擋下時 usage 記真實值 | T-3 #5808 | ✅ completed 路徑成立。❌ 斷線與串流中途失敗時，prompt 只記 user 文字或記 0（I4、I5）→ **已修（#5844）** |
| §4「chat 串流 output rail 從未生效」 | #5811 | ✅ 純文字回答成立。❌ 有工具呼叫的那一輪走 terminal `tool_calls` 分支，跳過扣住檢查（I3）→ **已修（#5847）**；非串流同類缺口 #5852 也已修（#5859） |

### 8.2 這次學到的事（給後續設計）

1. **「擋下」要涵蓋整輪輸出，不只文字。** Codex 把被禁內容寫進 shell 指令參數執行，output rail 看不到。工具參數要嘛也進 rail，要嘛整輪等裁決才放出 tool-call frame，這兩條要擇一寫成 invariant。
2. **conformance 的 fake provider 要能吐出 `incomplete`、`failed`，以及「文字加工具呼叫」混在同一輪。** 不然 §3.2 的回歸網會在這三個形狀上漏接，這正是 §8.1 的反例。
3. **換模型是 agent 的常態，不是例外。** session affinity 沒開時，DeepSeek thinking 會因為前面回合缺 `reasoning_content` 而 400（I8）。跨模型的 history 相容性要列進 routing 的設計前提。

### 8.3 第二輪結果（2026-10-05）

- §8.1 的 ❌ 都已修並 merge（未部署），唯一刻意保留的是「無 policy code 的 403」（理由同 Amendment B）。
- §8.2 三點的落地：
  - 第 1 點：「擋下要涵蓋整輪」已做成 invariant：ADR-437 INV-437-19、ADR-318 INV-318-23／-24，三個面都把工具參數一起送檢。
  - 第 2 點：conformance 的 fake provider 已能吐 `incomplete` 與「文字＋工具呼叫」。
  - 第 3 點：DeepSeek 跨模型 history 已處理（#5839，ADR-208 Am.9）。
- 修補途中又找到 7 個缺口（#5852–#5854、#5861–#5864），其中 5 個在 chat／messages 面，最嚴重的是 #5861：semantic cache 讓被 output rail 擋下的回答繞過檢查（PR #5870）。§4「漏接是雙向的」再次成立。
- 清單與證據：`docs/進行中/v1-response-checklist.md`。
