# Agent Policy（Tool 規則）— 新 session 交接文件

> **用途**：給新開的 agent session 快速接手。讀完這份就知道這個功能是什麼、做到哪、還缺什麼、要去哪裡找東西、有哪些不能碰的規則。
> **更新時間**：2026-10-17。基準是 `origin/main` `e329c51c2`（2026-10-17 10:26Z，#6723）。上一版是 2026-10-16（`4fb8be4ee`）；這段期間有 61 個 commit，跟本功能有關的 PR 列在 §4.6–§4.9。
> **事實以 repo 為準**：這份是導覽，不是權威來源。權威是 `xparse/docs/` 裡的 PRD-337、ADR-490、SPEC-304；這份與它們衝突時，以它們為準。
> **路徑慣例**：除非寫明絕對路徑，路徑都相對於 repo 根目錄 `/Users/peter/Desktop/X-parse/xparse`。
> **部署狀態只依 git 分支判斷**，沒有查過主機。標「待查」的地方就是沒驗證過。

---

## 0. 一句話

新增第三種 runtime policy kind `tool_governance`，顯示名「Tool 規則」。它讓管理員限制透過 Xparse 呼叫模型的 agent（Claude Code、Codex、OpenCode、客戶自建 agent）**能用哪些工具**，以及（Amendment D）**工具參數可以帶什麼值**：

- **請求端**：拿掉被禁的工具宣告（`/v1/responses` 的 namespace 成員也算，以 flat 名稱比對，Amendment E），或整個拒絕帶工具的請求。
- **回應端**：模型仍呼叫被禁工具時，預設**不再整輪擋下**：
  - 那個呼叫改名成 `tool_denied_by_policy` 交付（B3），agent 回報「沒有這個工具」，模型可以改用別的工具。
  - 同一份對話已經有 2 筆改名的呼叫時，改成模型文字加一句固定說明、正常結束（B2）。
  - 整輪擋下（R-A）只剩三種情況：參數不合契約、部署開關沒列出的入口、`/v1/responses` 的 provider 自己失敗。
  - 三條 API 路徑都有（Amendment F）。

另外兩種 kind 的分工：Guardrail（防護規則）管「說了什麼」，LLM Operational（運行規則）管「量」，本 kind 管「模型要 agent 做什麼」。

**狀態（2026-10-17）**：

| 範圍 | main | rel 分支 | prod 分支 |
|---|---|---|---|
| v1（IAM、gateway G1–G4、Console、Q2 #5709） | ✅ | ✅（`release/v1.77.0`＝`origin/rel` `662eeef76`，tag v1.77.1.3） | ❌（v1.76.4） |
| v1.1 Responses 回應端（#5806）、#5988 修正 | ✅ | ✅ | ❌ |
| Q1 custom、Amendment A／B／C | ✅ | ❌ | ❌ |
| Amendment D（參數契約，含 C2 Console 表單） | ✅（寫入一律拒絕） | ❌ | ❌ |
| #6640 修正（#6666）、範本重抓（#6671、#6686） | ✅ | ❌ | ❌ |
| Amendment E（Q15：namespace 成員以 flat 名稱受管，#6710） | ✅ | ❌ | ❌ |
| Amendment F（Q14：被拒的呼叫照常交付，#6713 → #6720 → #6723） | ✅（三個入口預設都開） | ❌ | ❌ |

- rel 是 10-08 從 main（`d08a1e794`）切的。之後 main 上的東西只有 backport 才在 rel；工具治理相關的 backport 仍只有 #6345。10-14 到 10-16 進 rel 的 backport 是 IAM、Fleet、Console、chart／k3s 與 CVE 修正（例如 #6501、#6285、#6237），都與工具治理無關。
- #5667 的留言說 dev 與 rel 曾部署 v1.77.0.9（這個 tag 含 v1 與 #5806）。**主機現在跑哪個 image：待查**。
- registry 有兩個本功能的 entry：
  - `tool_governance`：stage REL，所以 rel 看得到，prod 與未設標籤的客戶安裝扣住。prod 的 tree 根本還沒有這個功能。
  - `tool_argument_contracts`：stage DEV，只有 Console 讀，rel 與 prod 都是 false。

---

## 1. 功能本身

### 1.1 使用者能設的選項

| 欄位 | 值 | 預設 | 意義 |
|---|---|---|---|
| `mode` | `shadow`／`enforce` | `shadow` | 影子模式（只記錄）／強制模式（拿掉、處置） |
| `tool_use` | `allow`／`deny` | `allow` | `deny`：請求只要帶任何工具（含歷史裡的工具回合）就回 400 |
| `tool_names.deny` | 名稱清單（exact 或 glob，只收 `*` 和 `?`） | 空 | 命中的工具在請求端拿掉；模型仍回傳命中的名稱時，依 §1.3 處置（預設改名交付） |
| `tool_names.allow` | `null` 或非空清單 | `null` | 清單外的工具在請求端拿掉；模型回傳清單外的名稱時，同上 |
| `tool_arguments` | `[{tool, arguments}]` | 缺席 | **Amendment D 參數契約**，見 §1.7。已 merge，但 IAM 在所有環境一律拒寫；只有 dev 的 Console 有撰寫表單 |

其他固定欄位：
- `schema: tool_governance/v1`：判別欄位。加 `tool_arguments` 沒有升版。
- `actions`：保留欄位，帶值會回 400 `POLICY_KIND_HAS_NO_TRIGGER`。

名稱比對規則：
- `deny` 不分大小寫，`allow` 區分大小寫。
- 不收 regex；拒絕只由萬用字元組成的樣式。
- 每層每份清單最多 256 條、每條最多 128 字元。
- **Codex 的 namespace 成員**（Amendment E）：規則名稱是 `<namespace>__<tool>`，例如 `mcp__github__create_issue`；`functions` 這個 namespace 的成員用原名，所以 code mode 的 shell 就是 `exec`。chat 與 `/v1/messages` 沒有 namespace，規則名稱就是 `function.name`。

### 1.2 繼承（fold）

- 套用層級：tenant → group → application → deployment，**只能收緊**，下層放寬不了上層。
- **雙 lattice**：`enforced` 只收強制模式的貢獻，`observed` 收全部。gateway 只依 `enforced` 動作；兩者的差集發 `would_*` 稽核。這點和 guardrail 的 enforce-wins 刻意不同。
- `deny` 取聯集。`allow` 是各層合取：一個名稱要在每一層都命中才算允許，`null` 的層不參與。
- binding 的 `effect`（`mandatory`／`selected`）不影響 fold：lineage 上每一個 active 的貢獻都照同一套單調規則合併。
- 沒有 `enabled` 欄位。要停用，就**從政策集移除這條規則的項目**，或取消套用只含本 kind 的政策集；絕不能用 Invalidate（它會讓所有 kind 一起 fail-closed）。
- tenant／group 層級的 key 不投影本 kind（值是 null）。不能套到 `app_type=llm_proxy` 的 app，所有寫入路徑都會回 400。
- deployment 層只在推論 key 指派給該 deployment 時才生效；託管 agent 的 runtime key 沒綁 deployment，所以要放在 application 層或以上。

### 1.3 三條 API 路徑的行為（名稱規則）

| | `/v1/chat/completions`（OpenCode、自建） | `/v1/messages`（Claude Code） | `/v1/responses`（Codex） |
|---|---|---|---|
| 請求端 `tool_use: deny` | 400 `tool_not_allowed` | 400（Anthropic `invalid_request_error`） | 400 |
| 請求端名稱拿掉 | ✅ | ✅ | ✅ `function`、`custom` 與 namespace 成員（flat 名稱，#6710）；`input` 裡的 `additional_tools`／`tool_search_output` 也算 |
| 回應端：模型叫了被禁的工具 | B3／B2（#6723 起預設） | B3／B2（#6713 起預設） | B3／B2（#6720 起預設） |
| 仍整輪扣下（R-A） | 開關沒列出、參數契約擋下 | 同左 | 同左，另加 provider 失敗終端 |

**處置怎麼決定**（Amendment F；只在 `gateway/tool_denial.py::decide`，依序第一條成立就採用）：
1. 這個入口不在部署開關裡 → R-A。
2. `/v1/responses` 的 provider 終端自己失敗（`response.failed`／`error`）→ R-A。
3. 擋下的原因是 `tool_use: deny` → B2（B3 會在 history 留下工具回合，下一個請求就會被 400）。
4. 請求宣告了與 sentinel 同名的工具（含 namespace 成員的 flat 名稱，casefold）→ B2。
5. 有狀態續輪（`previous_response_id`）、被擋的是沒有名稱的內建呼叫（`shell_call`、`local_shell_call`、`computer_call`、`apply_patch_call`），或 provider 回 `response.incomplete` → B2。
6. 這個請求的 history 裡已有 2 筆 sentinel 呼叫 → B2。
7. 其他 → B3。

`decide` 不讀 provider、模型、client 身分或 header。三條路徑、串流與非串流、`/v1/responses` 的原生與翻譯出口，都經 `ResponseToolGovernance.deny` 走到它。

**B3（改名交付）**：
- sentinel 名稱是 `tool_denied_by_policy`（`DENIED_TOOL_SENTINEL`），刻意不以 `xparse_` 開頭：帶 management key 時，Xparse 工具迴圈會吞掉 `xparse_*` 的呼叫。
- id 與 arguments 不變，同一輪其他呼叫照常交付。
- chat 只換 `function.name`、`finish_reason=tool_calls` 不變；messages 只換 `tool_use.name`，所以 Claude 的 thinking 簽章保留。
- `/v1/responses` 換 held 的 added／done item、終端 `response.output` 與 `function_call_arguments.done` 裡的名稱，並拿掉 `namespace`；`call_id`、`output_index`、`sequence_number` 不變，終端仍是 provider 的 `response.completed`，不 retire binding。
- 改名一律交出複本，不就地改 provider 的資料；複製不了的形狀以 sentinel 重建，永遠不以原名交付。

**B2（以一句說明結束那一輪）**：
- 那一輪的工具呼叫**一筆都不交付**（包括沒被禁的），模型自己的文字保留，後面接固定句 `MSG_TOOL_CALL_DENIED_TURN_ENDED`：「The model asked to use a tool this application does not allow, so that step was not run. Continue without that tool, or contact your administrator.」不含工具名、規則或參數。
- chat 以 `finish_reason=stop`、messages 以 `stop_reason=end_turn` 結束；被輸出上限截斷的回合保留 `length`／`max_tokens`。
- `/v1/responses`：先送非呼叫的項目（`output_index` 重新連續編號），再送政策句 message，最後送 gateway 自己的 `response.completed`（`xparse.code=tool_call_denied`）。有 binding 時先 retire，`store=true` 時 best-effort DELETE。

**上限怎麼數**（C-304-383）：
- 無狀態，只在 TG stage 從請求原樣（剝除之前）讀一次，存進 `DenialContext`。
- 一筆 history 呼叫算 sentinel 呼叫有兩種情況：名稱就是 sentinel；或 arguments 是 JSON 物件、頂層 `tool` 是 sentinel（Rev.38，#6723）。
  - 後者是為了 OpenCode 1.19.2：它的 AI SDK tool-call repair 把改名的呼叫改寫成自己的 `invalid` 工具呼叫（call id 不變）。
  - 判斷只在 `tool_denial.is_sentinel_call`，看的是 history 的形狀，不判斷 client。
  - 只有含 sentinel 字串的 arguments 才解碼，而且在每個請求一份的 `ContainerBudget` 之內。
- 數不到的情況：client 用 `tool` 以外的鍵、丟掉那筆呼叫、壓縮 history；sub-agent 的 history 各自從 0 算。這些只影響體驗與成本，B3、B2 下被禁的工具都不會被執行。

**部署開關** `XPARSE_TOOL_RULES_DENY_AS_TOOL_ERROR_SURFACES`（讀法只在 `gateway/tool_denial_switch.py`）：
- 值是 `messages,chat,responses` 的逗號分隔子集。
- 未設：三個入口都開（#6723 起；#6720 時是 `messages,responses`，#6713 時是 `messages`）。
- 空字串：三條路都回到 R-A，回滾用。只撤回 chat 設 `messages,responses`。
- 其他值：`gateway/app.py` import 時就 fail，gateway 起不來。
- 是部署設定，不是 tenant 選項；改了要重啟。repo 裡沒有任何部署設定設定它。

`/v1/responses` 回應端（`gateway/responses_tool_rules.py` 的 `tool_rule_stage`）：
- 從第一個 client 執行的 call item 的 `output_item.added` 起扣住事件，一直到 provider 終端，判定沿用 `judge_turn`。
- 名稱規則讀**同一呼叫的每一筆 item**（C-304-302 Rev.35，#6710），名稱與 namespace 由 `responses_call_names.resolve_call_names` 解析；「只看第一筆」的缺口已修。
- R-A 擋下時 retire binding；`store=true` 時 DELETE provider 端的 response。
- 真 Codex 的證據：A22（#5810）當年是 BLOCKED（模型不再叫被拿掉的工具）。現在的預設改由 PB-4 支撐（§5）。

請求端與回應端的細節：
- **全部拿掉時**：刪掉 `tools` 和 `tool_choice`。如果歷史裡還有工具回合，回 400。`/v1/responses` 清空的 namespace 整個拿掉，namespace 以淺拷貝送出。
- **`tool_choice`**：chat／messages 指名的工具被拿掉時改成 `auto`。`/v1/responses` 依每次嘗試實際送出的工具重新綁定（SPEC-307 RF-7 Rev.11／12，`streaming/workers/responses_tool_choice.bind_tool_choice`）。
- **判定時點**：在 semantic cache lookup 之前。Tier V 稽核在拿掉之前擷取。
- **交付的回合算成功完成**：記 `EXECUTION_COMPLETED`、模型健康成功；非串流的 denial 要等 output rail 放行之後才記；交付了被拒呼叫的非串流回合不寫 semantic cache。
- **R-A 的出口**（只剩 §1.3 表末列的情況，也是開關設成空字串回滾時的行為）：
  - client 收到的形狀：chat 串流是一個 in-band error frame、非串流 HTTP 400（`code=tool_call_denied`，帶 `X-Policy-Error-Code`）；`/v1/messages` 是 Anthropic `invalid_request_error`（串流在 `message_start` 之後，非串流 400）；`/v1/responses` 是 `response.failed`，`error.code=invalid_prompt`、`xparse.code=tool_call_denied`。
  - 不走 503，不觸發換模型的 fallback，也不記模型健康失敗。
  - 先 `aclose` manager 再讀 usage（P18 的結論）。
  - ledger 與 `EXECUTION_FAILED(tool_call_denied)` 都帶實際執行的模型。
- **一個被擋的回合可能是 2–3 個請求**：只在 R-A 下成立。Claude Code 在串流被擋後會改送非串流，auto 模式還會拿掉 safeguards 再送一次，每個請求都各自判定、各自留稽核（C-304-158）。B 交付之後就沒有重送。
- **工具呼叫審視（SPEC-304 Rev.25，#6363）**：缺 `required` 參數、或 arguments 不是 JSON 物件的呼叫**照交付**（只在終端記錄），不再是 503。被輸出上限截斷的呼叫不交付，回合以 `length`／`max_tokens` 結束。503 只在 `XPARSE_TOOL_CALL_ARGUMENTS_ENFORCE=1` 時出現。入口是 `tool_call_validation.review_tool_calls`。`/v1/responses` 只記錄（C-304-408，#6465）；provider 自己說沒收完的呼叫由 worker 標出（Rev.28，#6526）。被拒呼叫自己的參數問題不算審視的 finding。

**對外說法**：
- Codex 的說法以本段為準（Console 的「Tool 規則的限制」說明框，含 `scopeNoticeCodex`，2026-10-19 起不在表單上顯示，SPEC-304 Rev.41；Console 上帶 namespace 說法的只剩範本的 `codexNotes`）：「被禁工具的定義不會送給模型；client 的指示或先前的對話提到它時，模型仍可能嘗試呼叫，強制模式下那個呼叫不會被執行。exec 執行的腳本裡呼叫的工具看不到；在 client 上把 MCP server 改名，規則就對不上。」舊的 Q5 原句已由 Q15／Q14 定案取代，但 ADR-490 §10 的 Q5 列本身沒跟著改（文件漂移，§6.5）。
- 名稱規則**管得到** Codex 的 MCP、sub-agent 與 code mode 工具（Amendment E 取代了 Amendment C 的「不得聲稱」）。必須同時寫明兩個上限：`exec` 腳本裡呼叫的工具看不到；client 改 MCP server 名稱就對不上。不可再寫「名稱規則管不到 code mode」或「只有 Tool 使用設為禁止才擋得住」。
- 強制模式的 Console 說明先寫「agent 會看到什麼依平台的設定而定」，再寫預設行為；不再寫「那一輪就會以 API Error: 400 結束」或「預設仍會擋下那一輪」；不寫「工具錯誤」「tool error」；sentinel 名稱不進 Console 文案（glossary §3.5.1「coding agent 的保護程度」列）。
- 仍有效的紅線（PRD-337 §3.8）：不得寫「防止 agent 執行危險指令」「模型看不到被禁的工具」「保證叫不動」「Codex 叫不動」；保護程度寫「減少暴露」。
- 不得暗示參數契約涵蓋 client 的 `tool_search`（C-304-437）。

### 1.4 稽核事件（Q7、Q12）

- `audit.policy.violation`：
  - 真正的拒絕或擋下（請求端 400、R-A、參數契約擋下 `violation_code=tool_arguments_denied`）。
  - **交付了的被拒呼叫也用它**（Amendment F，不新增事件型別）：每筆被拒呼叫一筆，`violation_code=tool_call_denied`，`action` 是 `deny_as_tool_error`（B3）或 `end_turn`（B2），`extra.disposition` 是 `tool_error`／`turn_ended`（R-A 與契約扣下時仍是 `blocked`），`http_status_code=200`，另帶 `extra.delivered`（有沒有以 sentinel 名稱送到 client）與 `extra.prior_sentinel_calls`。
- 終端事件新增（只在有被拒呼叫的回合被交付時出現）：`tool_calls_denied_count`、`tool_call_denied_disposition`、`delivered_finish_reason`。`finish_reason` 維持 provider 的值。
- `audit.policy.tool_stripped`、`tool_would_block`、`tool_call_undeclared`、`tool_executed_despite_policy`：其他處置各有自己的事件。影子參數契約沿用 `tool_would_block`（`rule_id=tool_arguments`）。
- namespace 成員（Amendment E）：
  - 名稱規則的決策事件 `tool_name` 是成員原名（可與 `TOOL_CALL_DETECTED` join），另帶 `tool_namespace` 與 `tool_flat_name`。參數契約事件的 `tool_name` 是 flat 名稱。
  - `EXECUTION_COMPLETED.tools_offered` 的成員從 `<namespace>.<tool>` 改成 flat 名稱（`functions` 的成員寫原名）。部署前後格式不同，普查要以部署日期分段。
  - 規則寫了成員原名、卻沒命中 flat 名稱時，記在終端事件的 `name_rule_near_miss_count`／`_first`（只記錄、不擋），參數契約是 `contract_name_near_miss_count`／`_first`。
- `tool_executed_despite_policy` 的跳過規則（`gateway/tool_governance_posthoc.py`）：
  - namespace 成員以 flat 名稱判斷（#6666 先跳過，#6710 改回以 flat 名稱判斷）；deny 只寫了成員原名時不報。
  - 名稱是 sentinel、或 call id 在 `DenialContext.sentinel_call_ids` 裡（例如 OpenCode 的 `invalid` 代替呼叫）的結果不報。請求自己宣告了同名工具時照報。
- 名稱等於 sentinel 的呼叫永遠不算 `tool_call_undeclared`。
- `audit.execution.platform_tool_stripped`：平台自己剝除 Responses 的工具時發（S0-b），回應也帶 `x-xparse-tools-stripped` header；成員條目寫 flat 名稱。
- 決策事件每請求上限 128 筆。只有該請求的**第一筆**拒絕類事件豁免上限（OQ-S9）：請求端的拒絕，或回應端那一輪的第一筆 `audit.policy.violation`（交付了的被拒呼叫也算）；同一輪其餘的 violation 照常受 128 筆限制。
- `tool_flat_name`（SPEC-064 §5.1）是跨 client 的彙總鍵，Q15 之後也是名稱規則與參數契約比對 namespace 成員的名字；它不唯一，也不保證等於翻譯出口送給模型的名字。
- Console 對交付了的被拒呼叫仍顯示 `tool_call_denied` →「工具呼叫被擋下」。要不要換標籤，產品負責人還沒決定（§6.2）。
- 相關但不屬本 kind：#6718（ADR-268 Amendment C）讓 Codex（`session-id`）與 OpenCode（`x-session-id`）的執行事件也帶 `extra.session_id`／`session_id_source`。

### 1.5 舊開關 `PolicyProfile.tool_call_allowed`

- 過渡期跟本 kind 取 AND。這段期間沒有改。
- 三條路徑都回 400 `tool_not_allowed`：Responses 是 S0-c2（#5634）；chat／messages 是 Q2（#5709，403 → 400）。
- 稽核的 `violation_code` 仍是 `TOOL_CALL_NOT_ALLOWED`。
- **R-a**（INV-490-25、C-304-100）：舊開關會拒絕、而且本 kind 依 `enforced` 也會動作時，由舊開關先回。它決定 client 收到 400 還是拿掉後照送，**不能**簡化成只決定稽核歸屬。

### 1.6 Responses 上的其他工具型別（Q1、Amendment A／B／C／E）

| 型別 | 現況 | 來源 |
|---|---|---|
| `custom`（Codex apply_patch） | 原生出口開放，受名稱規則管；只送給接受 custom 的模型（`accepts_custom_tools`）；翻譯出口自 Amendment C 起不再剝除，降成只有一個字串參數 `input` 的 function，回程還原成 `custom_tool_call`（code mode 的 `exec` 是 `functions` namespace 的成員，見下一列） | Q1（#6255）、Amendment A（#6283）、Amendment C（#6360） |
| hosted `web_search`／`web_fetch` | **預設開放**，不需租戶 opt-in，不經 Tool 規則；只在同家族原生出口；逐次計量。止血只有 kill switch（只影響 messages）或回滾 image | Amendment B（#6311、#6313、#6315、#6316） |
| `namespace`、client `tool_search`、code mode `additional_tools`、apply_patch 歷史 | 原生出口原樣轉送沒被剝除的成員；翻譯出口降成 function（`<namespace>__<tool>`）再還原。**名稱規則以 flat 名稱管成員**（`functions` 用原名）；client 執行的 `tool_search` 本身不受管 | Amendment C（#6360）、Amendment E（#6710） |
| 其他 hosted 型別 | 仍剝除，可見（header＋稽核） | S0-b |

- 名稱規則管不到的：`exec` 的 JavaScript 裡呼叫的工具（只判 `exec` 本身）；client 把 MCP server 改別名或換 namespace；其他 client 的 MCP 命名不同（OpenCode 是 `{server}_{tool}`）。flat 名稱可能撞名，撞名時 deny 兩個都剝、allow 兩個都放。
- `tool_types` 被 Amendment B 取代，改成日後選配的「租戶關閉開關」。
- Amendment B 的真 client 驗收 P5（PW-4 Claude Code、PW-5 Codex）**還沒跑**，跑之前不得宣稱完成。
- Console 範本（`tool-name-templates.ts`）依 Claude Code 2.1.301、Codex 0.163.0、OpenCode 1.19.2 的抓包（`docs/research/poc/tool-name-templates-2026-10-16/`）：
  - Claude Code：沒有 Glob／Grep，fileRead 只剩 `Read`，禁 Bash 也會拿掉檔案搜尋；`SubagentHandback` 列在全部名稱裡，但不放進任何能力組，禁了它 sub-agent 交不回結果（#6686）。
  - Codex：shell 組是 `exec_command`、`write_stdin`、`exec`（禁 `exec` 等於關掉 code mode）；sub-agent 組是 `multi_agent_v1__spawn_agent`、`collaboration__spawn_agent`；成員一律用 flat 名稱。
  - OpenCode：寫檔組是 `apply_patch`、`edit`、`write`。

### 1.7 參數契約（Amendment D；程式切片與 C2 Console 表單已 merge，寫入仍一律拒絕）

**切片狀態**：F0、I1a、W1、G-A、G-B、G-C、C1、C2 都已 merge，I1b 隨 C2 交付。剩 R0、P、R，之後是畢業（§6.3）。

**能表達什麼**：以工具名為鍵、租戶撰寫的參數值條件。例如：
- `refund` 的 `amount` ≤ 1000。
- `send_email` 的收件人只能是公司網域、不能多帶副本。

**形狀**：`tool_arguments: [{tool, arguments}]`，`arguments` 是 **profile 1**：
- 封閉、線性的 JSON Schema 子集，**沒有 regex**。另有 `x-xparse-glob`、`x-xparse-charset`、`x-xparse-email-domain-in`。
- 每個 `type: object` 節點都必須明寫 `additionalProperties`（`true` 或 `false`）；每個節點都必須有約束，不收空節點（D-D4）。
- 每版最多 32 份契約、每份 8 KiB、每版 64 KiB。投影上限 64 份／65536 字元，超量的工具 fail-closed。
- `tool` 不收萬用字元；比對 flat 名稱，原樣或 casefold 相等就適用。namespace 成員用 flat 名稱（`mcp__crm__refund`，D-D12），和名稱規則共用 `resolve_call_names`。

**fold**：不進 lattice。IAM 把 lineage 上每份契約串成一份清單，每筆帶 source 與 mode（跟該版本的 `mode`）。判定是合取，子層移除或放寬不了父層。

**三條路徑**：
- chat／messages（串流與非串流同序）：名稱判定 → 純審視 `review_tool_calls` → 契約 `judge_arguments` → 才輪到 env 的 503。擋下回 400 `tool_arguments_denied`，不是 503、不進 R1／R3、不記健康。
- `/v1/responses`（原生與翻譯、串流與非串流）：在 `tool_rule_stage` 裡、名稱判定之後判；擋下是 `response.failed`（`invalid_prompt`，`xparse.code=tool_arguments_denied`）。
- 文案依第一筆失敗原因三選一（違規／沒辦法檢查／被截斷），代碼都一樣（D-D10，owner to confirm）。
- gateway **永遠不改** `tools[]` 或 arguments。
- **和 Amendment F 的關係**：契約的扣下仍是 R-A；被名稱擋下、改名交付的呼叫不受契約判定；同一輪若有其他呼叫違反 enforce 契約，整輪照 R-A 扣下，被名稱擋下的那筆這時記 `blocked`。

**fail-closed**（有適用 enforce 契約時，以下一律整輪扣下）：
- 違規（violated）。
- 讀不了（unparsable）：NaN／Infinity、重複鍵、超長整數、深巢狀、超量（陣列在解碼前就計數）。
- 契約不可用（unavailable）、無法評估（unevaluable，含 Codex apply_patch／code mode 這類非 JSON 參數的 call item，D-D13）、超出預算（budget_exceeded）、判定器出錯。
- 只有影子契約時，任何非 pass 都只記 `would_block`、照常交付。

**做不到的**（ADR-490 §15.4 誠實上限）：
- shell／任意程式碼（`Bash`、`exec_command`、code mode `exec`）：只能限字串長相，管不到效果。
- 累計上限：10 筆 999 元的退款每一筆都合法。
- client 端實際怎麼執行：gateway 只看得到它看到的參數。
- 改名、換 namespace 就不適用；自由文字欄位的內容；provider 託管工具的參數；依角色分級。
- client 的 `tool_search_call` 不在 hold 與判定範圍，而且沒有任何訊號。

**能力 header**：gateway 送 `X-Gateway-Tool-Argument-Contracts: 1`（G-C）。IAM 只對宣告者送契約；enforce 契約遇到沒宣告的 gateway 回 409（在解密 custody 之前），只有影子契約就剝掉並警告。部署順序 IAM 先、gateway 後。

**Console「Tool 參數限制」表單（C2，#6657）**：
- 只在 `usePreReleaseFeature("tool_argument_contracts")` 為 true 時出現，也就是只有 `XPARSE_ENVIRONMENT=dev` 的部署看得到。扣住三個地方：建立對話框、新版本對話框、應用「政策」分頁的 effective panel。值不是 true 時，表單與送出的 body 都和 C1 完全相同。
- 只有結構化表單（D-D23）：每份限制對一個精確工具名；欄位逐一選型別（文字、數字、整數、是或否、物件、清單）；每層物件都有「允許其他欄位」開關，預設關。永遠不產生 `pattern`、`format`、`$ref`、組合條件，也沒有手寫 JSON 的入口。
- 送出前用 IAM profile 1 驗證器的 TS 移植（`tool-argument-profile.ts`）檢查，一致性以 IAM 全部 127 個 compile_cases 的釘住副本驗證，只有 `refuse-max-length-float` 一個具名例外（`JSON.parse` 把 `10.0` 讀成整數）。C-304-454 另記兩項已知差異：casefold 以 `toUpperCase().toLowerCase()` 近似，以及 canonical_cases 裡 `1000.0` 那一筆。權威仍是 IAM。
- 「從工具宣告匯入」：貼 OpenAI chat、Responses、Anthropic、MCP 形狀的工具定義，只在瀏覽器解析、不送出；表單表達不了的關鍵字丟掉並列出路徑。
- 新版本對話框把讀到的契約放成「保留原樣」，作者沒動就原樣送回；只有能無損表示的才能按「編輯」轉成表單。
- 工具名是 `bash`、`exec_command`、`exec`、`shell` 這類 shell 工具時，卡片顯示「不是安全邊界」（D-D18）。
- 按儲存會得到 NOT_WRITABLE 的固定文案：「Tool 參數限制的內容都通過檢查，但這個部署還不能儲存。移除參數限制即可儲存其餘設定。」（這個檢查排在最後，所以代表其餘內容都合法。）
- effective panel 每份契約一列（工具名、生效／只在觀察、來源層級與政策），不列限制內容。IAM 端是 I1b：`GET /iam/effective-policy?policy_kind=tool_governance` 每份契約一列 `field="tool_arguments"`、`value`＝工具名，不帶 schema 或 digest，openapi 不變。

**現在的實際效果是零**：
- IAM 的 `_refuse_argument_contracts()` 對非空 `tool_arguments` 一律回 400 `TOOL_ARGUMENT_CONTRACTS_NOT_WRITABLE`，**所有環境**、HTTP 與 GitOps 都一樣，**不讀** registry（D-D17）。C2 只改了它上方的註解。
- 所以任何環境都存不進契約，effective panel 的契約列與版本描述的契約摘要目前都不會出現。
- R0 的意思已改成：在既有 entry `tool_argument_contracts` 上，把無條件拒絕換成 entry 的述詞（§6.3）。

### 1.8 和主管（June）的 ADR-427 草案的關係

- ADR-427 指的是 PR #3978 的草案（未 merge，仍 OPEN），編號與 main 上的 ADR-427（slot lease）撞號。
- 兩案定位為正交並寫出組合規則（Q3）。本案是草案路線圖 P4 的「宣告層授權」。
- **U10（2026-10-14）重劃了分界**：以工具名為鍵、租戶撰寫的參數值契約改歸 ADR-490 Amendment D；依形狀分類的條件（verb／target、opaque_execute、shell 指令內容）仍歸草案。**主管同意尚待記錄**（ADR-490 Decision Makers 仍寫「待記錄」）。
- 回應端同一個掛點上，本案的名稱判定與參數契約先跑。
- **不要動 PR #3978，也不要聯絡主管**（Peter 自己處理）。

### 1.9 三個 client 被擋時會看到什麼（2026-10-17 的證據）

| Client | 被擋時（預設 B） | 證據 |
|---|---|---|
| Claude Code（`/v1/messages`） | 回「No such tool available」，模型改用別的工具；沒有替代工具時照實說做不到。R-A 下是 3/3 `API Error: 400` | PB-1（`docs/research/poc/tool-rules-b-disposition-claude-code-2026-10-16/`） |
| Codex 0.163（`/v1/responses`） | 禁 code mode 的 `exec`：記 `unsupported custom tool call`，模型照實說做不到（任務 0/7）；禁 namespace 成員且有替代工具：記 `unsupported call`，模型改用別的工具完成（5/5）。16/16 次 run `rc=0`；R-A 下 Codex exit 1 | PB-4（`tool-rules-b-disposition-opencode-codex-2026-10-17/`） |
| OpenCode 1.19.2（chat） | 改名的呼叫被導到它自己的 `invalid` 工具。模型一直重叫時，修正前 240 秒內 B3 142／154 次逾時；修正後 B3、B3、B2、每次 run 4 個請求 | PB-3（同上目錄）、PB-3 重跑（`tool-rules-b-sentinel-cap-opencode-2026-10-17/`） |

- 這些 client 看到的處置，都是攔截器或模擬器改寫的：
  - PB-3／PB-4 照 gateway 的形狀做（`tool_denied_by_policy`、上限 2、gateway 的政策句）；`/v1/responses` 的 B3 與 gateway 自己的 `responses_tool_denial.renamed_turn` 逐事件比對 3/3 相同。
  - PB-1（Claude Code）的攔截器早於正式實作：sentinel 是 `xparse_policy_denied`、上限 5（沒有到）、B2 政策句寫了工具名，與正式形狀不同。觸發點是自然的：`claude-haiku-5-5` 自己去叫被拿掉的 Bash。
  - gateway 自己的 B 程式碼搭真 client 的定版證據沒有存進 repo；repo 外的 testing kit 有幾筆（見下一點）。
- PB-2（provider 收不收含 sentinel 的 history）經本機 gateway 重放 6/6 回 200，限三個模型、每格 n=1。
- 經上限（history 已有 2 筆 sentinel）走到 B2 的只有 OpenCode：PB-3 重跑 6/6 以 B3、B3、B2 結束。Claude Code 的 B2 只測過攔截器強制的 b2 模式（3/3 `rc=0`、每次 run 1 個請求）。Codex 每次都在兩次 B3 後自己停，`/v1/responses` 的 B2 沒有 client 證據。Codex 搭非 OpenAI 模型只有 2/2 的非定版紀錄；TUI、MCP 工具、history 壓縮都沒有 client 證據。
- 另有 repo 外的本機測試結果（§7.5 testing kit），這是 gateway 自己的 B 程式碼碰到自然觸發的紀錄：在共用 gateway（當時只開 messages）上，Claude Code × `claude-haiku-5-5` 叫被禁的 `Bash` 時改名交付、不再 400；在三個入口全開的 probe gateway 上，Codex × `deepseek-flash` 收到改名呼叫 2/2、exit 0。Codex × `gpt-6-luna` 禁 `exec` 時 3/3 在請求端被拿掉，影子模式記到 `tool_would_block exec`。

---

## 2. 權威文件

| 文件 | 路徑 | 備註 |
|---|---|---|
| PRD | `docs/prd/PRD-337-agent-tool-governance-policy.md` | 到 Rev.17。需求、驗收（A／U／I／N 編號）、白話層。§4 A22（Rev.16 起預設依 AC-B5）、§4.5 被禁的呼叫照常交付（AC-B1..B7）、§16 參數契約（PRD 的 Amendment B）、§16.6 Console 撰寫表單（AC-E1..E11）、§14 Rev.14 的 AC-Q15-1..5 |
| ADR | `docs/adr/ADR-490-tool-governance-policy-kind.md` | 到 Rev.23，INV 到 490-59。決策 D1–D21、§7 分段與 probe、§10 Q 表；§13 Amendment B、§14 Amendment C、§15 Amendment D（D-D1..D-D23、§15.4 誠實上限、§15.8 切片表、§15.12 C2）、§16 Amendment E（D-E1..D-E7）、§17 Amendment F（D-F1..D-F11，§17.9 PB-3／PB-4、§17.10 數代替 sentinel 的呼叫） |
| SPEC | `docs/spec/SPEC-304-tool-governance-behavioral-contracts.md` | 到 Rev.38，C-304 編號到 460，NEG-304 到 221。§8.6 Responses 回應端、§17 OQ-S 表、§23 HOSTED、§24 NAMESPACE（Rev.35 起以 flat 名稱涵蓋成員）、§25 ARGUMENTS（§25.13 CONSOLE，C-304-451..460）、§26 DENIAL（C-304-380..389、PB-1..PB-4） |
| 研究（v1） | `docs/research/RESEARCH-agent-tool-governance-proxy-enforcement-2026-09-30.md` | 結論：「能擋工具」不是差異化，站得住的只有組合 |
| 研究（參數） | `docs/research/RESEARCH-agent-tool-argument-constraints-2026-10-14.md`（#6545） | 參數層先例、PRB-1..6 陷阱（PRB-6：jsonschema 的錯誤訊息帶值，不能直接寫進稽核）、放在哪一案 |
| 研究（namespace 與處置） | `docs/research/RESEARCH-tool-rules-namespace-and-denied-call-disposition-2026-10-16.md`（#6710、#6713） | 五個開源 gateway：三家把成員攤平成 `<namespace>__<member>`；沒有一家替 client 執行的工具合成「不准」結果。Status 列與白話版仍說 B 未定案，§5.2 寫已定案（文件內部不一致） |
| 研究（web） | `docs/research/RESEARCH-web-search-native-passthrough-2026-10-10.md` | Amendment B 的依據 |
| Probe 證據（v1） | `docs/research/poc/agent-tool-governance-probes-2026-10-01/README.md` | P2、P3、P7、P11、P16、P20，以及當年的攔截器工具 |
| 本機驗證 | `docs/research/poc/agent-tool-governance-local-verification-2026-10-01/` | S0-b、P-POL-2、IAM 影子規則、P18、P19、G4 |
| A22 證據 | `docs/research/poc/responses-tool-rules-a22-codex-2026-10-04/` | 真 Codex，BLOCKED |
| 10-16／10-17 證據 | `docs/research/poc/` 下的 `tool-rules-codex-namespace-6640-2026-10-16/`（#6666）、`tool-name-templates-2026-10-16/`（#6671、#6686）、`tool-rules-namespace-members-2026-10-17/`（#6710）、`tool-rules-b-disposition-claude-code-2026-10-16/`（#6713，PB-1、PB-2）、`tool-rules-b-disposition-opencode-codex-2026-10-17/`（#6720，PB-3、PB-4）、`tool-rules-b-sentinel-cap-opencode-2026-10-17/`（#6723，PB-3 重跑） | 另有非本 kind 專屬的 `claude-code-codex-client-switches-2026-10-17/`（#6711） |
| client 設定指引 | `docs/runbooks/agent-cli-setup.md`（#6711 更新） | Claude Code auto mode 的 `CLAUDE_CODE_AUTO_MODE_SERVER=0`、`CLAUDE_CODE_MAX_CONTEXT_TOKENS`；Codex 0.163.0 的 `model_context_window`，不建議 `model_catalog_url`／`model_catalog_json` |
| 回滾 runbook | `docs/runbooks/tool-governance-rollback.md` | 混版、409→500、migration 0357；§5.5、§5.6 參數契約的回滾前查詢；Amendment F 的開關列（空字串＝全部 R-A）。開頭狀態塊仍是 2026-10-01，§8 進度表 dev／rel／prod 全空白，沒有 Amendment E 要求的 namespace 普查步驟 |
| Wiki | `xparse-wiki/wiki/concepts/tool-governance-policy.md` | 概念頁 |
| Glossary | `docs/governance/console-i18n-zh-tw-glossary.md` | 「Tool 規則」等譯名（§3.5.1）。已加「Tool 參數限制」（量詞「份」）、`tool_arguments_denied`「工具呼叫的參數被擋下」與表單欄位詞；「coding agent 的保護程度」列有 10-16／10-17 多次補記，是 Console 文案紅線的正本 |
| Core | `docs/adr/core/Core-ADR-02-*.md`、`docs/prd/core/Core-PRD-02-*.md` | 主領域 02；01、03、04、05、06、08、10、12 有 cross-ref；另外 Core-PRD-13（FinOps）以 PRD-337 Amendment A 的逐次計量 cross-ref（Core-ADR-13 還沒建） |
| 被取代的文件 | ADR-331（整份）、PRD-257（整份）、PRD-316 的 `agent` 半邊 | issue #2634 已改掛 PRD-337（仍 OPEN） |

**編號對照**：
- PRD-337 的 Amendment A／B 對應 ADR-490 的 Amendment B／D。ADR-490 另有 Amendment A（custom 的模型閘門）與 Amendment C（namespace）。
- ADR-490 Amendment E（Q15）對應 PRD-337 Rev.14（AC-Q15-1..5）與 SPEC-304 §24（Rev.35）。
- ADR-490 Amendment F（Q14）對應 PRD-337 §4.5（Rev.15–17）與 SPEC-304 §26（Rev.36–38）。
- ADR-490 §15.12（C2）對應 PRD-337 §16.6 與 SPEC-304 §25.13（Rev.34）。

**原始草案**（Rev.4）：原本記在 `/Users/peter/Desktop/X-parse/docs/草案/agent-policy.md`，2026-10-17 查過，這個路徑已經不存在，位置待查。

⚠️ **三份權威文件的 Status 行仍然過時**：這批 PR 只在 ADR-490 的 Status 後面補了 Amendment E／F；PRD-337 只補了 Q15（E），SPEC-304 的 Status 仍只有「Draft」。下一次純文件 PR 一起修：
- ADR-490 第 3 行：仍寫 Q2「未合入」、v1「皆未部署」、Amendment B／D「Proposed，未實作」。§13、§15 的狀態塊也寫「未實作」。D-D18 仍寫「Console 撰寫輔助（下一批）」；§15.8 的「主管不同意時的撤回」沒列 C2 與 registry entry。
- SPEC-304：Status 仍是 Draft；§0.1 標題仍是「交付狀態（2026-10-01，Rev.5）」；§23、§25 標題與 Scope 行寫「未實作」；§17 的 Q1 列仍寫「產品決策，v1.1」；Non-scope 行仍把 `deny_as_tool_error` 列為 v1.1（§26 已實作）；C-304-456 的固定文案與 zh-TW catalog 實際字串有小差異。
- PRD-337：Status 仍寫 OQ-2「已實作、未合入」、Amendment A／B「未實作」，沒寫進 Q14／§4.5；§16 標題仍寫「未實作」。另外幾段沒跟上 Rev.17：§0 白話段與誠實聲明第 6 點仍寫 OpenCode 那條路還沒開；G4、A15–A18 只有 Rev.15／16 註記；U11 仍要求 Codex 文案附「Codex 會照做」；§3.8 表仍寫 Codex「v1.1 才擋」。

---

## 3. 程式碼地圖

### 3.1 IAM（`apps/iam/xparse_iam/xparse_iam/`）

| 檔案 | 作用 |
|---|---|
| `migrations/0357_adr490_tool_governance_policy_kind.py` | 放寬 versioned kind 的 CheckConstraint（expand-contract）。legacy `hierarchy.PolicyKind` **刻意不加** |
| `policies/tool_governance_content.py` | content schema 與驗證 |
| `policies/tool_name_matching.py` | 名稱比對：雙指標 glob，不用 regex |
| `policies/tool_argument_{contracts,profile,strings,types,values}.py` | 參數契約的讀取、profile 1 驗證、字串與數值規則 |
| `application/use_cases/policy/validate_policy_content.py` | `_refuse_argument_contracts()`：一律拒寫（D-D17），排在其他驗證之後；註解寫明 registry entry 存在但不讀它，R0 才換成述詞 |
| `authorization/tool_governance_resolver.py`、`tool_governance_fold.py`、`tool_governance_projection.py` | 解析、雙 lattice fold、validate 投影；`tool_governance_projection.py` 另有 I1b 的 `_contract_entries`（effective-policy 的契約 provenance 列） |
| `authorization/tool_argument_fold.py` | 契約串接 fold 與投影上限 |
| `api/ninja_api/_tool_governance_capability.py` | 能力 header `X-Gateway-Tool-Governance`：缺 header 且有強制貢獻時回 409（Q4 fail-closed）。W1 起也辨認 `X-Gateway-Tool-Argument-Contracts` |
| `db/django_database/_tool_governance_targets.py` | 套用目標檢查，拒絕 llm_proxy |
| `db/models/hosted_tool_price.py`、`migrations/0378_adr489_hosted_tool_usage_meter.py` | Amendment B 逐次計量的價表 |
| `core/pre_release_features.py` | `tool_governance`：stage REL、owner Peter、expires 2026-12-21。`tool_argument_contracts`：stage DEV、owner Peter、expires 2027-01-12，IAM 沒有 call site |
| `../contracts/tool-governance-policy.v1.schema.json` | 投影的 wire 契約 |
| `../contracts/tool-name-match.v1.json`（+publisher） | 名稱比對 golden vectors，gateway 有逐位元相同的副本 |
| `../contracts/tool-argument-contract.v1.json`（+publisher）、`tool-governance-policy.v1.samples.json`（+publisher） | 參數契約 vectors 與投影樣本；gateway 兩份都有逐位元相同的副本，Console 只有 compile vectors（`tool-argument-contract`）的副本 |
| 測試 | `../tests/{unit,integration,contract}/test_spec304_*.py`（即 `apps/iam/xparse_iam/tests/`；含 `test_spec304_tool_argument_contracts_gate.py`、`_profile.py`、`_vectors.py`、`test_spec304_tool_governance_effective_policy.py` 的 I1b 測試）、`../tests/unit/test_adr473_pre_release_features.py` |

Amendment E 與 F 不動 IAM：IAM 沒有變更、沒有 migration。改的是 gateway，以及 Console 的文案、範本與 dashboard 版面。

wire 的形狀：
- `/iam/internal/gateway-validate` 投影頂層鍵 `tool_governance_policy: {enforced, observed}`，沒套用時是 `null`（Q11 規定一定送）。
- 對宣告能力的 gateway，多一對選填鍵 `arguments`（`{tool, mode, profile, schema_json, digest, source}`）與 `arguments_overflow`。
- 這些鍵**沒有**宣告進 `/iam/auth/validate`。

### 3.2 Gateway（`apps/gateway/bustream/`）

| 檔案 | 作用 |
|---|---|
| `gateway/tool_governance_projection.py` | 把投影解析成不可變 DTO；記 skew metric（Q11） |
| `gateway/tool_name_matching.py` + `contracts/tool-name-match.consumer.v1.json` | gateway 端的比對器與 vectors 副本 |
| `gateway/contracts/tool-governance-policy.consumer.v1.json` | 釘住的 consumer 契約 |
| `gateway/tool_governance_request.py` | 請求端計畫：拿掉工具、拒絕、`tool_choice` 處理（事後偵測已搬到 `tool_governance_posthoc.py`） |
| `gateway/tool_governance_posthoc.py` | `tool_executed_despite_policy` 的事後偵測（#6710 搬出；sentinel 與代替呼叫的跳過） |
| `gateway/tool_governance_stage.py` | 三條路徑共用的 TG 請求 stage（`decide_request_tools`，legacy 先行，#5771） |
| `gateway/chat_tool_governance.py` | chat／messages 的形狀讀取：宣告工具、arming、`strip_chat_tools` |
| `gateway/responses_tool_governance.py` | `/v1/responses` 的形狀讀取：arming、`input` 裡宣告的工具、平台剝除；`strip_responses_tools` 回傳 `DeclaredPositions` |
| `gateway/tool_governance_response.py` | chat／messages 回應端；`ResponseToolGovernance.deny` 是進 `tool_denial.decide` 的唯一入口；含 `judge_arguments` |
| `gateway/tool_denial.py` | **Amendment F**：`Disposition`、`DenialContext`、`decide`、`is_sentinel_call`、`count_sentinel_calls_{chat,responses}`、`render_tool_calls_event`、`render_chat_body`、`review_without`、`ended_finish_reason`。全部是純函式 |
| `gateway/tool_denial_switch.py` | 部署開關的唯一讀法（`DEFAULT_SURFACES = KNOWN_SURFACES`） |
| `gateway/responses_tool_denial.py` | `/v1/responses` 的 B3（`renamed_turn`）與 B2（`ended_turn`） |
| `gateway/responses_tool_rules.py` | Responses 回應端 `tool_rule_stage`（#5806）；`_call_groups`／`turn_calls` 讀每個呼叫的每一筆 item，`_deliver_denied` 交付 |
| `gateway/responses_call_names.py` | `/v1/responses` 一個呼叫怎麼取名（`resolve_call_names`），名稱規則與參數契約共用 |
| `gateway/responses_held_calls.py`、`responses_argument_calls.py` | Responses 扣住的 call item、逐事件收集參數候選 |
| `translation/tool_shapes.py` | `rule_name(namespace, name)`：規則比對名（`functions` 用原名，其他 `<namespace>__<name>`），建在 `flat_tool_name` 上 |
| `audit/tool_member_fields.py`、`audit/tool_flat_name.py` | 成員決策事件的 `tool_namespace`／`tool_flat_name` |
| `streaming/workers/responses_tool_items.py`、`responses_tool_choice.py` | namespace 剝除的唯一規則（`namespace_keeping`）；`tool_choice` 依實際送出的工具綁定（SPEC-307 RF-7） |
| `gateway/surface_adapters/{chat,protocols,responses}.py` | 各入口的 `denial_context` 計數所在（C-304-383） |
| `gateway/tool_call_validation.py` | `review_tool_calls`：純審視，不 raise（Rev.25） |
| `gateway/tool_argument_{contracts,profile,compiled,evaluation,judgement,index,matchers,charsets,scalars,strings,values,verdicts}.py` | 參數契約：讀投影、編譯、嚴格讀取、判定、結果 |
| `gateway/tool_governance_events.py` | 稽核事件組裝 |
| `gateway/tool_governance_decisions.py`、`tool_governance_errors.py`、`tool_governance_metrics.py` | 決策計數（128 上限）與終端欄位、固定文案與 sentinel 常數、metric |
| `gateway/responses_tools_filter.py` | 平台剝除的計算與 header 編碼器 |
| `gateway/pre_execution.py` | `reject_tool_calls_not_allowed`：舊開關拒絕的唯一產生點 |
| `gateway/iam_http_client.py` | 送出兩個能力 header（G-C 起含參數契約） |
| `gateway/routes/{chat,messages,responses}.py` | 三條路徑的接線 |
| `gateway/json_nesting.py`、`gateway/json_body_bound.py`、`json_containers.py` | event loop 上的 JSON 解碼上限（深度、容器數；#6547..#6634） |
| `streaming/hosted_tool_usage.py` | Amendment B 託管工具次數 |
| `contracts/tool-argument-contract.consumer.v1.json`、`tool-governance-policy.samples.consumer.v1.json` | 參數契約與樣本的 consumer 副本 |
| `scripts/responses_tool_call_allowed_census.py` | 唯讀普查：找出 `tool_call_allowed=false` 的 app 與流量 |
| 測試 | `tests/integration/test_spec304_*.py`（含 `test_spec304_{chat,responses}_argument_contracts.py`、`test_spec304_denied_calls_delivered.py`、`test_spec304_responses_denied_calls.py`、`test_spec304_sentinel_cap_rerouted_calls.py`、`test_spec304_tool_executed_despite_policy.py`）、`tests/unit/test_spec304_*.py`（含 `test_spec304_tool_denial.py`）、fixture `tests/fixtures/opencode_1_19_2_rerouted_sentinel_call.json`、`tests/contract/test_spec304_*_wiring.py`、`test_*_decode_budget*.py`；`tests/conftest.py` 的 autouse `_denied_call_switch_unset`；root 的 `tests/contract/test_gateway_iam_http_cutover.py`（PD-9；#6723 起斷言 chat 以 sentinel、200 交付） |

### 3.3 Console（`frontend/console-app-refactor/src/`）

| 檔案 | 作用 |
|---|---|
| `app/(main)/(ai-gateway)/policies/_components/policy/tool-governance-settings.tsx`、`tool-governance-content.ts` | 建立與編輯表單。#5732 攤平成一個區塊、一個範本選擇器；名稱輸入接受任何逗號或空白；C1（#6586）原樣保留 `tool_arguments`，C2 起在 feature 開時改成有序的 draft／kept 項目 |
| 同目錄 `tool-argument-contracts-editor.tsx`、`tool-argument-node-editor.tsx` | C2 撰寫表單：區塊、保留原樣卡片、匯入、shell 提示；欄位與各型別的限制 |
| 同目錄 `tool-argument-{draft,profile,canonical,declaration,describe,messages}.ts` | 撰寫模型與 builder、IAM profile 1 移植、canonical 長度、工具宣告匯入、人話摘要、錯誤句 |
| 同目錄 `tool-name-templates.ts` | client 名稱範本（Claude Code 2.1.301、Codex 0.163.0、OpenCode 1.19.2） |
| 同目錄 `create-policy-dialog.tsx`、`create-policy-version-dialog.tsx` | 讀 `usePreReleaseFeature("tool_argument_contracts")`；寫入錯誤經 `tool-argument-messages.ts` 的 `toolArgumentWriteErrorMessage` 呈現 |
| 同目錄 `policy-version-describe.ts` | 版本內容的檢視摘要（參數限制摘要用 `describeToolArguments`） |
| `components/features/policy/tool-governance-binding.ts` | 套用目標檢查（隱藏 LLM Proxy） |
| `components/features/policy/tool-governance-effective*.ts(x)`、`components/features/application/policies-tab.tsx` | effective-policy 逐欄來源的顯示，含契約列（feature 關時濾掉） |
| `app/(main)/(overview)/(dashboard)/_components/pre-release-rows.ts`、`_tabs/safety-policy/initial-layout.ts` | dashboard 的 Tool 規則違規列（G4） |
| `lib/pre-release-features.ts` | `PRE_RELEASE_FEATURE_NAMES` 含 `tool_governance` 與 `tool_argument_contracts` |
| `i18n/messages/{en,zh-TW}.json` | 譯名照 glossary。`policy_violation_code` 已有 `tool_call_denied` 與 `tool_arguments_denied`；`modeEnforceBlocks`、`denyNamesBlocks`、`codexNotes`（`scopeNotice*` 五個鍵隨說明框於 2026-10-19 刪除）、`claudeCodeSearchViaBash`；Policies 教學 `tutorial.pages.policies.fields.*` 也改成「那個呼叫不會被執行」 |
| `../contracts/tool-argument-contract.consumer.v1.json` | IAM compile vectors 的 consumer 副本（project.yaml 登記為 `console-next-tool-argument-contract`） |

kind 的選項由 `usePreReleaseFeature('tool_governance')` 控制顯示。

### 3.4 CI gate

- `.github/scripts/tool-governance-parity-gate.py`（含 `--self-test`）：IAM vectors 與 gateway 副本逐位元一致、consumer 契約完整。W1 加了第 3、4 節（參數契約與樣本），C2 加了第 5 節（Console 的 compile vectors 副本，tree 裡有 Console root 時才跑）。
- #5675 的 AST 檢查：每個 `StreamingManagerV3(...)` 都必須接上 audit emitter。
- `pre-release-feature-registry-gate`：Console 列的每個名字（含 `tool_argument_contracts`）都必須在 IAM 註冊；手寫環境判斷不得增加。
- `response-checks-gate`：`gateway/response_checks.py` 的宣告（D-D15 把 `judge_arguments` 加進 chat 的 Run cell；#6710、#6713 加了 `declared_rule_names` 與 `tool_denial` 的 helper；chat 登記 `render_tool_calls_event`／`render_chat_body`）。
- root 的 `tests/contract/test_console_backend_consumer_contracts.py` 要求 Console 的 compile vectors 副本與 publisher pin 逐位元相同。
- `.github/scripts/manual-gitlink-gate.sh` 已在 10-16 由 #6683 刪除：手冊 gitlink 現在沒有 CI 擋。

---

## 4. 交付時間軸

### 4.1 v1（9/30–10/02，在 rel、不在 prod）

| PR | 內容 |
|---|---|
| #5593 | 設計閉環：RESEARCH、PRD-337、ADR-490、SPEC-304 |
| #5612、#5683 | 第一、二輪決策；probe 的 20 點影響 |
| #5623、#5685 | probe 證據、本機實機驗證證據 |
| #5618、#5621、#5634 | S0-b 平台剝除可見；S0-c1／c2 Responses 舊開關影子 → 400 |
| #5614 | S1 IAM（migration 0357） |
| #5675、#5679、#5684 | 串流補 `TOOL_CALL_DETECTED`；P18 抓到的記帳 bug |
| #5688、#5691、#5696、#5697 | G1 投影、G2 請求端、G3 chat／messages 回應端＋能力 header、G4 dashboard |
| #5656 | Console 建立與編輯 |
| #5709 | Q2：chat／messages 的舊開關 403 → 400 |

### 4.2 v1.1 與後續修正（10/02–10/08，多數在 rel；#6253 只在 main）

| PR | 內容 |
|---|---|
| #5732、#5739 | Console 表單攤平、名稱輸入放寬 |
| #5771 | 三條路徑共用一個 Tool 規則請求 stage（ADR-494 P2b） |
| #5803 | v1.1 前置：真 OpenAI 模型實測（A40／A31 pass） |
| #5806 | **v1.1：`/v1/responses` 扣下被 Tool 規則拒絕的回合**（關 #5753） |
| #5810 | A22 真 Codex：BLOCKED |
| #5750、#5757、#5843、#6022 | 修 #5669、#5670、#5671、#5667 |
| #6020 | `input` 裡宣告的工具也受管（修 #5988，行為改變） |
| #6253 | OQ-S6：Responses wire 帶不了的 chat 工具可見剝除（關 #6217）。只在 main（rel 切點 d08a1e794 之後才 merge） |

### 4.3 Q1 與 Amendment A／C（10/08–10/12，只在 main）

| PR | 內容 |
|---|---|
| #6255 | Q1：原生 Responses 出口開放 `custom`（Codex apply_patch） |
| #6283 | Amendment A：custom 只送給接受它的模型 |
| #6300 | `/v1/messages` typed tool 改成明確分類（修 #6299） |
| #6360 | Amendment C：namespace、tool_search、code mode、apply_patch 歷史 |

### 4.4 Amendment B：hosted web 工具（10/11–10/13，只在 main）

| PR | 內容 |
|---|---|
| #6301、#6311 | 設計閉環；預設開放（owner 10-11 拍板） |
| #6313、#6315 | OpenAI／Azure 原生 Responses 轉送；`/v1/messages` 原生 Anthropic |
| #6316、#6451 | 逐次計量（ADR-489 Am.A）；終端事件看得到次數 |

### 4.5 工具呼叫審視改版（10/12–10/14，只在 main）

| PR | 內容 |
|---|---|
| #6363 | Rev.25：缺參數／壞參數照交付、截斷不交付，不再 503 |
| #6465 | `tool_flat_name`；Responses 記錄壞參數（C-304-408） |
| #6526 | Rev.28：provider 沒收完的呼叫由 worker 標出 |
| #6345 | `TOOL_CALL_RESOLVED` 帶 group 與 proxy scope（**有 backport 到 rel**） |

### 4.6 Amendment D：參數契約（10/14–10/16，只在 main）

| PR | 內容 |
|---|---|
| #6545 | 研究：參數層先例 |
| #6561 | D0 設計：ADR-490 §15、SPEC-304 Rev.29 §25、PRD-337 Rev.10 |
| #6584 | I1a：IAM 讀得懂、驗得了、可 fold，所有環境拒寫 |
| #6586 | C1：Console 原樣保留欄位，畫面不變 |
| #6609 | W1：IAM 只送給有宣告的 gateway；gateway 解析、編譯但不動作 |
| #6614、#6623 | G-A chat／messages 執行；G-B `/v1/responses` 執行 |
| #6625 | G-C：gateway 送能力 header，三條路徑生效 |
| #6645 | IAM 參數契約 overflow 測試的偶發失敗修正（隨機 UUID 的 hex） |
| #6657 | **C2**（`38a9c9f3c`，10-16）：Console「Tool 參數限制」撰寫表單、I1b、registry `tool_argument_contracts`（DEV）、compile vectors 的 Console 副本與 parity gate 第 5 節、glossary、`tool_arguments_denied` 標籤。ADR-490 Rev.19（§15.12 D-D23）、SPEC-304 Rev.34（§25.13）、PRD-337 Rev.12（§16.6）。帶 Manual-Exempt（被 stage DEV 扣住） |

**前置與順手修**：#6547、#6549、#6553、#6554、#6559（深巢狀／非物件 JSON 不再 500）、#6560（超長整數）、#6619（非有限數值）、#6618、#6629、#6630、#6634（event loop 上的解碼上限，SPEC-304 Rev.30–32、SPEC-219 Rev.12）、#6624（請求 body 容器數上限，SPEC-307 RF-20）、#6588（Console 新版本對話框保留預填的 enforce）。

**部署順序**（已查證）：`deployments/operations/scripts/blue-green-deploy.sh` 的 `cmd_deploy` 依序是 IAM → gateway（切流量）→ Console。`cmd_rollback` 只切 gateway 的顏色，回滾後有強制規則的 app 會回 500（Q4 fail-closed，runbook 有記錄）。

### 4.7 #6640 修正、範本重抓與 client 指引（10/16–10/17，只在 main）

| PR | 內容 |
|---|---|
| #6666 | `a27683d11`：#6640 不需要核心決策的部分。`tool_executed_despite_policy` 不再對 namespace 成員以名稱規則發出（C-304-450，之後由 #6710 改寫）；Q5 說法在 Codex 0.163 × OpenAI 模型不成立，改寫說法與 `scopeNoticeCodex`。ADR-490 Rev.18、SPEC-304 Rev.33、PRD-337 Rev.11。手冊走 Xparse-Manual#36 |
| #6671 | `c8b17322e`（關 #6669）：範本改用 Claude Code 2.1.301、Codex 0.163.0、OpenCode 1.19.2 的抓包；改寫 `codexNotes`，新增 `claudeCodeSearchViaBash`。PRD-337 Rev.13。手冊走 Xparse-Manual#40 |
| #6683 | 移除 CI 的 User Manual Gitlink Gate |
| #6686 | `77f32b665`：Claude Code 範本補 `SubagentHandback`（只放在全部名稱，不放進能力組） |
| #6711 | `27ada8c40`：client 設定指引（`docs/runbooks/agent-cli-setup.md`），不改 Tool 規則行為。SPEC-307 Rev.13、ADR-340 Rev.3 等 |

#6640 已在 10-17 02:43Z 關閉：#6666 先修說法與稽核，#6710（Q15）與 #6713（Q14）補上行為。

### 4.8 Amendment E：namespace 成員（10/17，只在 main）

| PR | 內容 |
|---|---|
| #6710 | `76e593fdf`：Q15 定案。namespace 成員以 flat 名稱受名稱規則管（請求端剝除與回應端判定）；回應端讀同一呼叫的每一筆 item；`tools_offered` 改列 flat 名稱；near-miss 記在終端欄位；`tool_choice` 依每次嘗試實際送出的工具重新綁定（SPEC-307 RF-7）；Console Codex 範本加 code mode 名稱。ADR-490 Rev.20（§16）、SPEC-304 Rev.35、PRD-337 Rev.14、SPEC-307 Rev.11／12。新增研究文件。手冊依產品負責人指示延後 |

### 4.9 Amendment F：被拒的呼叫照常交付（10/17，只在 main）

| PR | 內容 |
|---|---|
| #6713 | `8f4296560`：Q14 定案。B3／B2，處置只在 `tool_denial.decide`，新增部署開關；當時預設只開 `messages`。ADR-490 Rev.21（§17）、SPEC-304 Rev.36（§26，OQ-S11 已定：不做「剛擋過」記錄）、PRD-337 Rev.15（§4.5）。證據 PB-1、PB-2 |
| #6718 | `ae8f78ee4`（相關但不屬本 kind，Refs #6716）：Codex 與 OpenCode 的執行事件也記 `extra.session_id`。ADR-268 Amendment C、SPEC-290 C-290-51 |
| #6720 | `7a3bdba23`：PB-4（Codex）四項都成立，`/v1/responses` 也預設交付；chat 仍 R-A（OpenCode 讓上限算不到）。Console `modeEnforceBlocks`、`scopeNoticeCodex` 與 Policies 教學文案、glossary 同步。ADR-490 Rev.22（§17.9）、SPEC-304 Rev.37、PRD-337 Rev.16 |
| #6721 | `07d94e561`：`test_spec304_denied_calls_delivered.py` 掃 OpenCode 重試字串時跳過隨機 message id（只改測試） |
| #6723 | `e329c51c2`：上限也數「代替 sentinel」的呼叫（arguments 頂層 `tool` 是 sentinel），這些呼叫的結果不再被誤報成 `tool_executed_despite_policy`；PB-3 重跑後上限生效；chat 也預設交付。ADR-490 Rev.23（§17.10）、SPEC-304 Rev.38、PRD-337 Rev.17 |

---

## 5. 實測得到的關鍵事實（設計依據）

- **P16**：請求端拿掉 `exec_command` 後，模型若依歷史仍吐出它，Codex **會照執行**。
- **P7**：Codex 對 Responses 的 `event: error` 和 `response.incomplete` 都會重試 5 次。v1.1 因此定案用 E 類 `response.failed`（`invalid_prompt`），Codex 收到就停。模型最多連續重叫被拒的工具 15 次，所以交付被拒呼叫要先有次數上限（Amendment F 的上限 2）。
- chat／messages 的 R-A：串流是一個 in-band error frame，非串流是 HTTP 400（帶 `X-Policy-Error-Code: tool_call_denied`）。OpenCode 不重試；Claude Code 會改送非串流，auto 模式再重送一次。
- **OpenCode 的重試字串**：錯誤文案不得含 429、500、502、503、504、524、try again later、timeout、rate limit 等字樣（golden TC，C-304-157）。
- **P2**：OpenAI 與 DeepSeek 在「全部拿掉＋歷史有工具回合」時回 200，但輸出不可用。所以這種情況維持 400。
- **P3**：OpenAI 在沒有 tools 時，`tool_choice` 連 `"none"` 也回 400。
- **P18**：被擋時 `manager.run()` 的 finally 不會自動在讀 usage 之前跑完，必須先 `aclose`。
- **P19**：tenant／group 層級的 key 打不到推論。但 tenant_auditor、group_admin、app_user 是靠授權資料擋住，不是結構性的閘。
- **A22**（Codex 0.154 × gpt-4o-mini／gpt-4.1-nano）：模型不再叫被拿掉的工具，所以回應端擋下沒機會觸發。其他模型會叫，例如 #6640 的 Claude Code × `claude-haiku-5-5`。repo 裡的 B 證據（PB-1～PB-4），處置都由攔截器或模擬器扮演 gateway（§1.9）。
- **#6640（10-16）**：Codex 0.163 搭 OpenAI 模型走 code mode，shell 是 `functions` namespace 的 `exec`，沒有頂層 `exec_command`；Claude Code × `claude-haiku-5-5` 在 Bash 被拿掉後仍會去叫，R-A 下 3/3 `API Error: 400`。這是 Q15 與 Q14 定案的起因。
- **PB-1～PB-4（10-16／10-17）**：見 §1.9。OpenCode 的 AI SDK repair 把未知工具的呼叫改寫成 `invalid`，這是 #6723 改計數的起因；Codex 會在 history 保留 sentinel 名稱，所以計數在 Codex 上算得到。
- **參數研究的四個陷阱**（PRB-1..5）：jsonschema 的 `pattern` 有 ReDoS（24 字元要 0.6 秒）；NaN 通過上下限；重複鍵 last-wins；深巢狀丟 `RecursionError`。Python 3.11 對 4301 位以上整數丟純 `ValueError`。這些都是 F0 與解碼上限 PR 的起因。
- **twin 路徑**：所有 ExecutionPlan 都是 direct，twin 是死路。

---

## 6. 還沒做的事、open 項目

### 6.1 需要部署或遠端授權（Peter 未授權，不要自己做）

- **v1 上 prod 前**：
  - dev 真流量影子觀察 ≥7 天、P5、P14 回滾演練都還沒做。P4 已在本機真元件 VERIFIED（`agent-tool-governance-local-verification-2026-10-01/P4/`）；P15 的 Gateway 半 VERIFIED，Audit 半只以 Audit image 0.7.1 驗過。C-304-203 (b) 要 P4、P5、P15 綠。registry 的 reason 仍寫 P4／P15 沒做，已過時，畢業 PR 要一起改。
  - prod 唯讀普查 `tool_call_allowed=false` 的 profile 數量（S0-c2、#5709 需要）。rel／prod 部署前的唯讀普查是 SPEC-304 C-304-11 的後續待辦（S0-c2 列），目前只附了 dev 普查（TC-304-7）；**rel 有沒有跑過，在 repo 找不到紀錄**。另外 runbook §8 進度表（§5.1 查詢／P14 回滾演練／§5.6 查詢）在 dev、rel、prod 三個環境都空白。
  - registry 畢業（C-304-203）：上述全部完成後，同一個 PR 刪 entry 與兩端 call site。
- **Amendment E 部署到 rel 前**（C-304-407、ADR-490 §16.5，都還沒做，也沒有 runbook 或腳本）：
  - 逐個 application 普查：哪些 allow 清單會把 `functions` 的成員（`exec`／`wait`／`request_user_input`）或 MCP、sub-agent 成員剝光（剝光後帶工具歷史就是 400，Codex 第二輪就斷）；哪些 deny 只寫了成員原名（只會變成 near-miss）。
  - `tools_offered` 格式在部署前後不同，普查要以部署日期分段。
- **Amendment F 部署到 rel 前**（ADR-490 §17.5）：用 PB-2 的 6 個 request body 對要部署的 gateway 重跑，結果要與 `sentinel-replay-results-2026-10-17.jsonl` 相同。
- **Amendment D**：W1、G-C、C1、C2 部署到 dev，且 dev 的 IAM 回滾目標含 W1（R0 的前提）。實際部署了沒有：待查。
- **Amendment B**：P5 真 client 驗收（PW-4、PW-5）。在哪個環境跑：待查。
- rel／prod 主機現在跑的版本：待查。

### 6.2 等 Peter 或主管決定的事

| 項目 | 內容 | 狀態 |
|---|---|---|
| 主管同意 | U10 重劃分界，要記錄到 ADR-490 Decision Makers（姓名、日期）；R0 的前提 | 待記錄（Peter 處理） |
| 交付後的稽核標籤 | 交付了的被拒呼叫仍是 `violation_code=tool_call_denied`、Console 顯示「工具呼叫被擋下」，要不要換（#6713） | 未定 |
| sentinel 命名的規則 | IAM 要不要拒絕以 `tool_denied_by_policy` 為名的規則或契約（#6713） | 未定 |
| D-D23 的兩個取捨 | effective panel 不列限制內容；prefill 一律保留原樣、按編輯才轉成表單 | 待產品負責人確認 |
| D-D7（Q13／OQ-S8） | 演進通則：先能讀後開放寫、每個新投影欄位一個能力 header | owner to confirm（暫採） |
| D-D10 | 代碼 `tool_arguments_denied` 與三句英文文案 | owner to confirm |
| D-D18 | shell／exec 工具可寫契約，文案誠實說明 | owner to confirm |
| D-D19 | 門檻是政策內容、不是秘密；effective-policy 只加 provenance | owner to confirm |
| D-D22 | 預算數字；等 PD-6 容器實測（本機估計每輪節點預算也許降到 8192） | owner to confirm |
| 十進位精度 | 小數字面值以 IEEE double 比較，或拒收 >17 位有效數字 | **R0 之前要定** |
| 孤兒參數事件 | provider 失敗終端上的孤兒參數事件只計數、不判定 | owner to confirm |
| Amendment B | C-304-355 的 allowed_callers 規則、C-304-367 的 STRIP_RECORD | owner to confirm |
| Q9 | v1.1 `tool_denied` trigger 的 `default_enforcement`（建議 observe） | 未定 |
| ADR-268 編號 | ADR-490（D15、§7.2、§7.2.1、§8）與 SPEC-304 §18 保留編號表（C-304-330..349）都把「session 呼叫上限」的前提寫成 ADR-268 Amendment C，但這個字母已被 #6718 用掉（session_id 稽核） | 兩份一起改編號 |
| OQ-S2 | chat 的舊開關把 `tools: []` 算成帶工具，messages 不算 | 未定 |
| OQ-S13 | `tool_choice` 用 `allowed_tools` 形狀、指名的工具被拿掉時怎麼處理 | 未定 |
| — | P19 三種角色要不要加結構性 guard；串流純文字多 1 筆 `streaming_phase_changed` | 未定 |

已定：Q1（10-08）、OQ-S6（10-08）、D-D4、D-D12（Q16）、D-D13（Q17）、D-D17（10-15）、**Q15／OQ-S14（10-17，Amendment E）**、**Q14／OQ-S11（10-17，Amendment F：不做「剛擋過」記錄，改成交付被拒呼叫）**。

v1.1 待做清單剩：session 呼叫上限（ADR-268 的 amendment 編號要另定）、rewrite 評估、ADR-461 `tool_denied` trigger。`deny_as_tool_error`（含拒絕次數上限）已由 Amendment F 交付（sentinel、上限 2）。

### 6.3 Amendment D 剩下的切片

1. **主管同意記錄**（§6.2）。
2. **R0**：在既有 entry `tool_argument_contracts`（C2 已加）上，把 `_refuse_argument_contracts()` 的無條件拒絕換成 entry 的述詞，開放 dev 寫入（HTTP 與 GitOps 同一個述詞）。前提：主管同意已記錄；W1、G-C、C1、C2 已部署到 dev；dev 的 IAM 回滾目標含 W1；十進位精度已定案（若定案是在 profile 1 內收緊，含收緊的 gateway 要先部署到 dev）。SPEC-295 的 C-295 新列隨 R0 補。
3. **P**：PD-1..PD-10 實測。PD-9 標「本機已跑」，其餘九項都標「未跑」；其中 PD-5、PD-8 的 responses 半與 PD-10 的 Codex 半，只在本機用錄到的串流經真 route 跑過，不是 live probe；PD-6 只有本機估計。PD-6 是容器預算；PD-2 是真 provider；PD-3、PD-4 是真 client；PD-5、PD-10 還缺錄製的 namespace／custom 呼叫串流。
4. **R**：晉級 REL；之後才是畢業。這一批要交齊使用者手冊兩頁（C2 因 stage DEV 帶 Manual-Exempt）。前提：P 綠；G-A、G-B、G-C、C1 已部署到 rel；rel 的 IAM 連續兩個 release 含 W1；dev 影子 ≥7 天、未解釋的 `would_block`＝0。dev 影子觀察可能需要一個合成的 ERP-like 測試 agent（目前沒有帶業務工具的 agent）。
5. **Codex apply_patch 路徑限制**：patch 文法，不是 JSON Schema。PRD-337 §16.6 列為 Out of Scope，沒有切片。同一份清單還有「N 天內 0 次評估」的提示、effective panel 顯示限制內容。

已完成：Console 編輯表單、glossary「Tool 參數限制」、`tool_arguments_denied` 標籤、I1b（都由 C2，#6657）。GitHub 上沒有 R0 或 Amendment D 後續的 open PR／issue。

### 6.4 Open issue 與 PR（2026-10-17 查過）

| 項目 | 內容 | 狀態 |
|---|---|---|
| #5666 | `tools: []` 加 `tool_choice` 送到 OpenAI 回 400（P3） | OPEN |
| #5668 | ADR-455 bridge 遇到 incomplete／failed 時，已累積的工具呼叫被丟掉（P1） | OPEN |
| #5672 | C-304-68 套用預覽（IAM）未交付 | OPEN |
| #5673 | 「從稽核挑名稱」與 7 天工具流量的彙總查詢 | OPEN |
| #5674 | validate 熱路徑：每個 kind 各讀一次 scope，本 kind 多 6–20 個查詢 | OPEN |
| #2634 | tool-type authorization（已改掛 PRD-337）；10-16 被加進 milestone「展會 Demo（11/02 前）」 | OPEN，P0 |
| #6243 | rel v1.77.0.9 部署驗證清單。與本 kind 直接相關的是 #5753（#5806，Responses 回應端 Tool 規則；驗收要先經 Peter 同意建強制規則），另含 #5667、#5669、#5671 的修正 | OPEN，P1 |
| #6715 | 互動式 Codex（originator `codex-tui`）的工具結果不走 exec-output parser，`TOOL_CALL_RESOLVED` 狀態是 `unknown`，`tool_executed_despite_policy` 在 headless 與互動模式下不一致 | OPEN，P2，在敏捷看板 |
| #6716 | `extra.session_id` 只記 Claude Code。實作已由 #6718 merge（寫的是 Refs），要做本機驗收再關 | OPEN，P2 |
| Xparse-Manual#36 | #6666 的手冊：Codex 在 OpenAI 模型上的 shell、Claude Code 的 API Error: 400。內容已被 Amendment E／F 推翻，merge 前要重看 | OPEN，等 code owner review |
| Xparse-Manual#40 | #6671 的手冊：範本名稱重抓（合進了 #36 的分支） | OPEN，等 code owner review |

已關閉：
- 在 rel、不在 prod：#5667（#6022）、#5669（#5750）、#5670（#5757）、#5671（#5843）、#5753（#5806）、#5988（#6020）。
- 只在 main：#6217（#6253）、#6299（#6300）、#6669（#6671）、#6640（#6666、#6710、#6713）。
相關但不屬本 kind：#5897、#6166、#5503、#5502；10-17 新開的 client 設定 issue：#6724（Codex 的 rustls 不接受本機自簽的 `CA:TRUE` 憑證）、#6725（`agent-cli-setup.md` 沒有 TLS 信任步驟）、#6728（`agent-cli-setup.md` 對 Claude Code 只設 `CLAUDE_CODE_MAX_CONTEXT_TOKENS` 不夠）。

**手冊 gitlink**：main 上的 `3rd/Xparse-Manual` 指向 `c3573dd`（Xparse-Manual#40 的 head），不在手冊 `main` 上，違反 CLAUDE.md §18.6；#6683 移除 gate 之後沒有 CI 擋。Amendment E／F 的手冊依產品負責人指示延後；它們改到的 Console 文案在 rel 看得到（`tool_governance` 是 stage REL），所以進 rel 時手冊會落後。C2 不一樣：它被 `tool_argument_contracts`（stage DEV）扣住，依 §18.6 在晉級 rel 那一批（§6.3 的 R）才交手冊兩頁，不算延後。

### 6.5 已知缺口（都還沒開 issue）

- client 執行的 `tool_search_call` 不被 hold 或判定，針對它的契約永遠不適用，而且沒有訊號（C-304-437）。
- `/v1/responses` 名稱規則改成讀每一筆 item 之後（#6710），原本 `_turn_call_items` 在 2000 個呼叫時 70–84 ms 的成本，新實作沒有重量。
- Amendment F：
  - client 用 `tool` 以外的鍵改寫未知工具、或整個丟掉那筆呼叫時，計數仍是 0。
  - B2 只在模擬器或攔截器下有 client 證據（§1.9）：Codex 沒走到 B2，Claude Code 沒有經上限觸發過。chat 的 B 程式碼沒有搭真 OpenCode 跑過，client 看到的處置都是模擬器改寫的。
  - client 壓縮 history 會讓計數歸零；無狀態的上限管不到 sub-agent 扇出。
- #6710 未驗：code mode 的 `tool_choice: "required"`／具名 custom、只放在 `additional_tools` 的工具，api.openai.com 收不收。
- 契約扣下時，provider 失敗不記健康。
- 無狀態的 `/v1/responses` 請求仍需要 `XPARSE_BOOTSTRAP_ADMIN_KEY`（既有問題）。
- G-A 的 fuzz 測試在 Python 3.12 失敗（CI 固定 3.11）。
- testing kit 的發現 #3：Codex 禁 shell 就連讀寫檔都不能（code mode 只有 `exec` 能碰檔案），Console `codexNotes` 沒提。
- 文件與註解漂移（下一次純文件 PR 一起修）：
  - §2 列的三份文件 Status 行與幾段過時內容。
  - ADR-490 §10 的 Q5 列仍寫「OpenAI 模型上名稱規則管不到 Codex 的 shell」。
  - `gateway/app.py:1177` 的註解仍寫「unset = messages」。
  - 研究文件 `RESEARCH-tool-rules-namespace-and-denied-call-disposition` 的 Status 列與白話版仍說 B 未定案。
- 舊的小 follow-up 仍在：skew metric 告警規則、R3 fallback 後稽核 provider 歸屬、`apps/gateway/bustream/tests/contract/test_azure_plan_resolver.py::TestPlanResolverAzureProfile::test_azure_twin_plan` 死測試、SPEC-290 C-290-34 註記。

### 6.6 未來可以做的（超出名稱與參數）

依 10-14 的競品調查排序（沒寫成正式文件；「誰在做」只記當時查到的，工作量是粗估）：

| # | 選項 | 做什麼 | 誰已經在做 | 歸屬 | 工作量 | 建議 |
|---|---|---|---|---|---|---|
| 1 | 工具結果的 prompt injection 篩檢 | 掃歷史裡的 tool result | LiteLLM `scan_only_tool_results`、MS Foundry、Lakera、LlamaFirewall PromptGuard | guardrail 領域（今天 classifier rail 不讀 tool role；PII／word filter 有讀） | 中 | 先做，影子起步 |
| 2 | 送往雲端的工具結果做 DLP | 例如 `cat .env` 的輸出，依 `route_target` 決定 | 沒查到前例 | proxy 原生；ADR-511 route_target＋ADR-448 PII | 中 | 做，Xparse 位置獨有 |
| 3 | 工具參數裡的 secrets／DLP | output rail 掃參數 | IBM ContextForge Secrets Detection、LiteLLM content filter、Lakera DLP、Cloudflare DLP（多在 MCP hop） | guardrail output rail；只在 buffer 模式擋得住 | 小–中 | 做 |
| 4 | session／每工具呼叫上限 | 粗粒度防濫用；拒絕重試上限已由 Amendment F 的上限 2 做了（只算同一份 history） | AWS AgentCore temporal count（AWS 自己說不是安全控制）、gh-aw-mcpg、ContextForge、LiteLLM `mcp_rpm_limit` | ADR-490 v1.1／v2（需 ADR-268 新的 amendment） | 中 | 做，已在 backlog |
| 5 | provider 託管工具的參數夾限 | Anthropic web_fetch `allowed_domains`／`max_uses`；OpenAI hosted MCP `allowed_tools`／`require_approval` | provider 自己執行 | ADR-490 Amendment B 的租戶開關 | 小 | 做，成本低 |
| 6 | 不可信來源的 taint latch | 讀過 web／MCP 後限制網路與寫入 | LiteLLM tool_policy、Archestra、GitHub gh-aw DIFC | 需修 ADR-034「不掃歷史」範圍 | 大 | 先設計 |
| 7 | 工具定義釘選／漂移稽核 | 抓 MCP rug-pull | LiteLLM catalog guard、Invariant mcp-scan | ADR-490，先只稽核 | 小–中 | 做，先稽核 |
| 8 | `tool_choice: allowed_tools` 代替剝除 | 保留 prompt cache | OpenAI | OQ-S13；只限 OpenAI 上游 | 小 | 視快取成本 |
| 9 | 參數大小、每輪呼叫數上限 | 粗粒度防濫用 | 沒查到前例 | ADR-490 | 小 | 可順手 |
| 10 | LLM 判斷動作是否符合意圖 | 機率性判定 | LlamaFirewall AlignmentCheck、Lakera | guardrail／Jev | 大 | 晚點，不能當硬閘 |
| 11 | 綁參數雜湊的帶外核准 | 人工核准後才放行 | Archestra、AgentCore | 需要儲存與處置決策 | 大 | 等需求 |
| 12 | 依 route_target 的情境 ABAC | 地端／雲端不同規則 | AWS AgentCore principal tag、Alibaba AI Gateway context（都不是依執行邊界） | ADR-490＋ADR-511 | 小 | 做，便宜 |

不建議：把更嚴的 schema 注入 `tools[]`（傷快取、provider 行為不一）、改寫參數（違反 fail-fast）、終端使用者 ABAC（沒有使用者身分）。

**誠實上限**：proxy 看不到工具實際執行；shell 參數一定繞得過；串流要做參數檢查就得 hold；以 session 為鍵的規則換一個 session 就重來。對外只主張組合價值（LLM hop、對 client 內建工具也有效、fail-closed、多層收緊），不主張「管得住 agent 做的事」。

---

## 7. 環境與工作方式

### 7.1 本機 dev stack

- **主 checkout** `/Users/peter/Desktop/X-parse/xparse`：10-15 重新 clone，2026-10-17 19:24（+0800）pull 到 `e329c51c2`，等於 `origin/main`。
- **gateway 與 IAM**：容器 `xparse-gateway`、`xparse-iam`，原始碼**唯讀 bind-mount 主 checkout**，在那次 pull 之後重啟過，所以共用 stack 跑的是 `e329c51c2`。
  - gateway 沒有設 `XPARSE_TOOL_RULES_DENY_AS_TOOL_ERROR_SURFACES`，所以三個入口都交付被拒的呼叫。10-17 早上的 testing kit 實測跑的是 `c8220461d`，那時未設只開 messages。
  - IAM 容器設 `XPARSE_ENVIRONMENT=dev`，registry 照 dev 解析（Console 看得到 C2 表單）。
  - image 是 `xparse-scr:celery-local`（10-15 建）。
  - 稽核寫到 `var/audit`（gitignore）。
- **入口**：
  - Console dev server（`next-server`）在 `http://localhost:4001`，從主 checkout 的 `frontend/console-app-refactor` 熱載入；推論 `/v1/*` 與 IAM `/apis/iam/*` 都可以走這裡，純 HTTP，不需要憑證設定。
  - ingress：`https://localhost:3000/v1/*`，自簽憑證。Node client（OpenCode、Claude Code）走這裡要設 `NODE_EXTRA_CA_CERTS=/Users/peter/Desktop/X-parse/xparse/certs/cert.pem`。Codex（rustls）連不上：這張憑證是 `CA:TRUE`（#6724），Codex 要走 Console dev server 或 probe gateway 的純 HTTP。
- **測試應用與 key**：
  - 10-17 的實測用 app `peter`（`55c3e729-78f1-4f61-9a06-85fd6e3c3519`）。模型池有 `claude-haiku-5-5`、`deepseek-flash`、`gpt-6-luna`，以及地端的 `gemma-4-E2B-it`（vLLM，`192.168.1.143:18004`）。
  - 同一個 app 同時段也有別的 agent 在用（`/Users/peter/Desktop/testing/agent-e2e/`），10-17 的測試規則就套到了另一個 Claude Code（testing kit README §5 #4）。**驗證時另建專用的 profile 和 app，驗完清掉**；稽核用 session id 或工具組分開。
  - key 由 Peter 提供，只放在環境變數或 testing kit 的 `env.local`（從 `env.example` 複製後自己填 `XPARSE_APP_KEY`、`XPARSE_TENANT_KEY`）。**不要讀 `env.local` 或 `env.example` 裡的 key 行，也不要寫進任何檔案。**
  - 舊的 `/Users/peter/Desktop/testing/.env`（`XPARSE_ADMIN_KEY`、`XPARSE_PROBE_KEY_*`）已經不存在；舊 app `5260605d…` 也不在本機 IAM 了（10-15 重建後查不到）。
- **client 版本**：
  - Claude Code：PATH 上是 `2.1.302`（10-17 05:15 +0800 起）。testing kit README 寫 2.1.301 是錯的：實測（10:08–10:33 +0800）比切換晚，`run_agent.sh` 用的是 PATH 上的 `claude`。範本是 2.1.301 抓的，2.1.302 的工具組有沒有落差：待查。
  - Codex `0.163.0`、OpenCode `1.19.2`：testing kit 的 `agents/node_modules` 與 Homebrew 都是這個版本。
  - `~/.codex/config.toml` 與 `~/.config/opencode/opencode.json` 都不存在：testing kit 每次 run 臨時產生設定（Codex 用 `CODEX_HOME`，OpenCode 用 `XDG_*`，Claude Code 用 `CLAUDE_CONFIG_DIR`、`ANTHROPIC_BASE_URL`、`ANTHROPIC_AUTH_TOKEN`），三者都在 `env -i` 下跑：上層 Claude Code session 的 `CLAUDE_CODE_*` 變數會改變 Claude Code 的工具組。
  - client 端的設定建議見 `docs/runbooks/agent-cli-setup.md`。
- **攔截器**（舊的 `/Users/peter/Desktop/testing/tool_gov_interceptor.py` 已不存在，現在兩支都在 repo 裡）：
  - Claude Code（`/v1/messages`）：`docs/research/poc/tool-rules-b-disposition-claude-code-2026-10-16/interceptor.py`，模式 pass／ra／b2／b3。
  - OpenCode（chat）與 Codex（`/v1/responses`）：`b_emulator.py`（在 `tool-rules-b-disposition-opencode-codex-2026-10-17/` 與 `tool-rules-b-sentinel-cap-opencode-2026-10-17/`），模式 pass／b3／b2，strip `after_first`／`never`。本機工作副本在 `/Users/peter/Desktop/testing/tool-rules-pb34-2026-10-17/`（OpenCode 走 18150、Codex 走 18151）。
- **跑 PR 程式碼的 probe gateway**：從 worktree 起獨立容器，不要重啟共用容器。做法記在 memory `gateway-local-test-env.md`（`--entrypoint /app/build/gateway-entrypoint.sh`、`--env-file <(docker inspect xparse-gateway …)`、worktree 唯讀掛載、`-p 127.0.0.1:18800:8000`；一定要帶 `--entrypoint`，image 預設的 SCR entrypoint 會跑 Django migration 然後中止）。純 HTTP，Codex 可以直接連。

### 7.2 跑測試

- **gateway**：不要用主機的 python（是 3.15），`xparse-gateway` 容器裡也沒有 pytest，而且它掛的是主 checkout。在 worktree 裡建 uv 3.11 的 venv（CI 也是 3.11；G-A 的 fuzz 測試在 3.12 會紅）：

```bash
uv venv --python 3.11 apps/gateway/bustream/.venv
uv pip install --python apps/gateway/bustream/.venv/bin/python --no-deps -r apps/gateway/bustream/requirements-dev.lock
cd apps/gateway && PYTHONPATH=$PWD bustream/.venv/bin/python -m pytest -q bustream/tests/integration/test_spec304_*.py
```

  - 全套：在 `apps/gateway/bustream` 跑 `PYTEST_ADDOPTS='-n 4' .venv/bin/python scripts/project.py test`（約 3 分鐘）。
  - 新測試要登記：`apps/gateway/bustream/tests` 底下的進 `apps/gateway/bustream/gateway-ci-suite.txt`；root 的進 `tests/gateway-ci-suite.txt`。`ci-suite-orphan-gate.sh` 會擋漏登記的。
  - 本機跑 ci.yml 的 static gates 時，有 6 個會因為環境因素固定失敗（memory `gateway-local-test-env.md`）。
- **IAM**：做法記在 memory `iam-local-pytest-env.md`（PYTHONPATH／addopts 對齊 iam-ci；conftest 把 ADR-473 環境設成 dev）。重產 openapi 要用 Python 3.11（memory `iam-openapi-regen-python-311.md`）。
- **Console**：在 worktree 的 `frontend/console-app-refactor` 先跑 `pnpm install --offline --frozen-lockfile --ignore-scripts`，再跑 `tsc --noEmit`、`vitest`、`scripts/i18n-*.mjs`。`i18n-hardcoded-text.mjs` 需要 Node 22，本機是 Node 20，只能交給 CI。
- **改到 `zh-TW.json` 的 PR**：要重產 feature acceptance manifest，否則 `Feature acceptance inventory` 的 `verify` 會紅。主機的 `python3` 是 3.15、沒有 openpyxl，`python` 也不存在，所以用 uv 起 3.12：`uv run --no-project --python 3.12 --with 'openpyxl>=3.1,<4' --with 'jsonschema>=4.23,<5' python scripts/testing/build_feature_acceptance_workbook.py --write`，再跑 `--check`。manifest 記的是當時的 HEAD，所以先 commit 改動再重產。

### 7.3 Git 與 PR 的固定套路

- **一律在 worktree 工作**：`/Users/peter/Desktop/X-parse/pr-worktrees/<name>`，從 `origin/main` 開分支。Claude 桌面 app 自己開的 worktree 在 `/Users/peter/claude-worktrees/xparse-864fccd3300c993e/`。
  - 本 kind 的 11 個 worktree（`pr-worktrees/` 下 9 個，加上 `claude-worktrees/…/opencode-sentinel-cap` 與 `pb34-tool-denial-default`）對應的 PR（#6657、#6666、#6671、#6686、#6710、#6711、#6713、#6718、#6720、#6721、#6723）全部已 merge，沒有未 commit 的檔案。`git worktree list` 另外還有 10 個屬於別的工作（cache_salt、prefix cache 等），不要清。
- **驗收產生檔**（`docs/testing/feature-inventory/*.json`、`docs/testing/qa-evidence-v2/excel-inventory.json`、兩個 `docs/testing/*.xlsx`）幾乎每次 merge main 都會衝突：
  1. `git merge origin/main`，不要 rebase。
  2. 這幾個檔取 theirs。
  3. 另開 commit 跑 `build_feature_acceptance_workbook.py --write`（用 §7.2 的 uv 指令），再跑 `--check`。
- **merge main 時的 commit 用 `--no-verify`**：否則 pre-commit hook 會把 main 帶進來的前端檔重新排版。
- **多支 PR 互相衝突時用 squash merge train**：
  - 建鏈：節點 K = 節點 K-1 merge PR K 的 head。
  - 前一支 squash 之後，在下一節點先 `git merge <前一節點 head>`（也就是 `<squash>^` 那一側的內容），再 `git merge -s ours <squash commit>`。先確認 `git diff --quiet <squash> <前一節點 head>`，推之前確認 PR 的檔案清單縮回自己的檔案。
  - main 若進了別人的 commit，不能直接 `-s ours`，要把那些路徑改回 main 的版本。gitlink 用 `git ls-tree` 判斷，不要用 `cat-file -e`。
  - 動到 `apps/iam/` 的 PR 排在鏈尾。
- **PR 描述**：`Acceptance-Impact: none` 單獨一行（`feature-acceptance-inventory.yml` 會讀）；改到程式碼的 PR 附 ADR-093 五列表；新 ADR／PRD 附 Core 對比表；結尾加 `🤖 Generated with [Claude Code](https://claude.com/claude-code)`。
- **commit 訊息**結尾加 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。
- **合併**：
  - repo **不允許 auto-merge**（`allow_auto_merge=false`），預設 squash、不刪 head branch。要手動 `gh pr merge <n> --squash`；base 必須是 `main`。
  - main 沒有 branch protection，樹相同且驗過的節點不必每支等 CI。
  - Peter 交辦的 PR（含他開的 session 交辦的），CI 紅了就自己讀 log、修、推、再看；全部綠了就 `gh pr merge --squash`（base `main`），**不要停下來問**（memory `pr-fix-ci-through-merge.md`）。只有修正會超出 PR 範圍改變行為，或 reviewer 要求修改時才先問。auto mode 擋合併指令時不要繞過，請 Peter 自己合。
- **Claude 桌面 app 的 Auto-fix**（PR 列的 CI 監看開關，不在 repo 裡）：開了之後 CI 紅或出現衝突會叫醒該 session 修；CI 綠不會通知。兩個 session 同時改同一個 PR 分支時要先協調（10-17 的 #6720 就是兩個 session 各推了 commit）。

### 7.4 Peter 的硬性規則

- **不准用 `git stash`**：所有 worktree 共用 `refs/stash`。（10-15 重新 clone 後目前沒有 stash，規則照舊。）
- **主 checkout 的本機狀態要保留**：`3rd/Xparse-Manual`、`3rd/xparse_audit` 的 checkout 落後各自的 gitlink（`git status` 顯示 ` M`），`pr-worktrees/` 在 repo 外面同一層。都不准 reset、clean 或 stash。（`frontend/console-app/` 已在 9 月退役，主 checkout 裡沒有了。）
- **不准建強制模式的 Tool 規則或參數契約，本機也不行**，除非 Peter 明說。10-17 Peter 授權過一次：在 app `peter` 建強制規則跑實測、測完刪除（testing kit 的 `scripts/policy.py` 有 teardown；`policy-state.json` 不存在代表已清乾淨）。這個授權不延伸到下一次。
- **不做部署或遠端環境操作**（rel／prod 的查詢只能寫成 follow-up）。
- **不動 PR #3978，不聯絡主管**（Peter 處理）。
- **不把任何 key 寫進 commit、PR、文件或證據。**
- **遇到以下情況要停下來問**：要建強制規則、要部署或遠端操作、結果推翻 ADR-490／SPEC-304 的核心決策、要改到 #3978、要開放參數契約寫入（R0）、要改部署開關的預設值。

### 7.5 其他參考

- **Memory**（`/Users/peter/.claude/projects/-Users-peter-Desktop-X-parse-xparse/memory/`）：`gateway-local-test-env.md`、`iam-local-pytest-env.md`、`iam-openapi-regen-python-311.md`、`pr-fix-ci-through-merge.md`。舊版文件引用的 `project_agent_policy_v1_design_closure.md` 與各個 `reference_*.md` 都已不存在。
- **testing kit** `/Users/peter/Desktop/testing/tool-rules-agents-2026-10-17/`（沒有進 repo；repo 裡的 `run_agent_pb.sh` 寫死這個路徑，要重跑 PB-3／PB-4 就不能刪）：
  - `scripts/run_agent.sh <claude|codex|opencode> <model> <ls|wc|concat> <label>`：在 `env -i` 下以全新工作目錄跑一次 client，240 秒逾時，輸出一行 JSON。
  - `scripts/policy.py setup|use <config>|teardown|status`：建、換、拆一條 tenant 擁有的 Tool 規則，以 `mandatory` 綁到測試 app（`CONFIGS` 有影子與四個強制設定）。
  - `scripts/run_matrix.sh <run-id> [configs...]`：設定 × client／模型 × 任務的矩陣，跑完 teardown；`MATRIX_CELLS` 挑組合、`XPARSE_BASE` 改 gateway。
  - `scripts/analyze.py <results dir>`：把每次 run 對上同一個 app 的稽核（Claude Code 用 session id，Codex 與 OpenCode 用工具組特徵）。
  - `scripts/audit_summary.py`、`api/{xp,test_tool_calling,test_tool_rules}.py`；結果在 `results/{m1,pb34,api}`。
  - README §5 的七個發現：#1 已由 #6720、#6723 處理；#2 已由 #6718 處理（#6716 待驗收）；#3 未處理（§6.5）；#5 已寫進 `agent-cli-setup.md`。
- **既有研究**：`docs/research/RESEARCH-agent-client-block-status-retry-behaviour-2026-09-15.md`（三家 client 對 HTTP 狀態碼的重試行為）。

---

## 8. 建議的下一步（依優先順序）

1. `git fetch` 後看 `git log origin/main`，確認 §4 的 PR 都在、有沒有新的相關 commit。
2. **#6716 本機驗收**：本機 stack 已經跑 `e329c51c2`，用 Codex 與 OpenCode 各跑一輪、以 session_id 查稽核，過了就關 #6716。
3. **純文件 PR**：
   - 同步三份文件的 Status 行與 §2 列的過時段落。
   - 修 ADR-490 Q5 列、D-D18、§15.8 撤回清單；ADR-268 的 amendment 編號。
   - 修 `gateway/app.py:1177` 的註解、研究文件的 Status 列。
   - rollback runbook 補 Amendment E 的 namespace 普查步驟。
4. **開 issue**（走 `/doc-issue`）：§6.5 的 `tool_search_call`、Amendment F 的計數缺口、Codex 禁 shell 連讀寫檔都不能的說明。
5. **手冊**：Peter 決定時機。Xparse-Manual#36 的內容要依 Amendment E／F 改寫，再處理 gitlink 指回手冊 `main`。
6. **Amendment D 往前推**：Peter 記錄主管同意 → 定十進位精度 → dev 部署 W1／G-C／C1／C2 → R0（換述詞）→ PD-1..PD-10 → R（含手冊兩頁）。每一步都要 Peter 授權。
7. **rel 部署前的準備**（要授權）：Amendment E 的 namespace 普查、Amendment F 的 PB-2 重跑、Amendment B 的 P5（PW-4、PW-5）。
8. **v1 上 prod**：prod 唯讀普查、補記 rel 普查、dev 影子觀察 ≥7 天、P4／P5／P15、P14 回滾演練、registry 畢業。都要授權。
9. 依 Peter 的優先順序處理 §6.4 issue（#5668 是 P1、#2634 掛在 11/02 展會 milestone）、§6.2 待決題、v1.1 剩下的項目，以及 §6.6 的延伸方向（建議先看 1、2、5、12）。
