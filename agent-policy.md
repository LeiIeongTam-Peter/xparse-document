# Agent Policy（Tool 規則）— 新 session 交接文件

> **用途**：給新開的 agent session 快速接手。讀完這份就知道這個功能是什麼、做到哪、還缺什麼、要去哪裡找東西、有哪些不能碰的規則。
> **更新時間**：2026-10-16。基準是 `origin/main` `4fb8be4ee`（2026-10-15，#6634），已含 Amendment D 全部程式切片。
> **事實以 repo 為準**：這份是導覽，不是權威來源。權威是 `xparse/docs/` 裡的 PRD-337、ADR-490、SPEC-304；這份與它們衝突時，以它們為準。
> **路徑慣例**：除非寫明絕對路徑，路徑都相對於 repo 根目錄 `/Users/peter/Desktop/X-parse/xparse`。
> **部署狀態只依 git 分支判斷**，沒有查過主機。標「待查」的地方就是沒驗證過。

---

## 0. 一句話

新增第三種 runtime policy kind `tool_governance`，顯示名「Tool 規則」。它讓管理員限制透過 Xparse 呼叫模型的 agent（Claude Code、Codex、OpenCode、客戶自建 agent）**能用哪些工具**，以及（Amendment D）**工具參數可以帶什麼值**：

- **請求端**：拿掉被禁的工具宣告，或整個拒絕帶工具的請求。
- **回應端**：模型仍呼叫被禁工具、或參數不合契約時，擋下那一整輪。三條 API 路徑都有。

另外兩種 kind 的分工：Guardrail 管「說了什麼」，LLM Operational 管「量」，本 kind 管「模型要 agent 做什麼」。

**狀態（2026-10-16）**：

| 範圍 | main | rel 分支 | prod 分支 |
|---|---|---|---|
| v1（IAM、gateway G1–G4、Console、Q2 #5709） | ✅ | ✅（`release/v1.77.0`，tag v1.77.1） | ❌（v1.76.4） |
| v1.1 Responses 回應端（#5806）、#5988 修正 | ✅ | ✅ | ❌ |
| Q1 custom、Amendment A／B／C | ✅ | ❌ | ❌ |
| Amendment D（參數契約） | ✅（寫入一律拒絕） | ❌ | ❌ |

- rel 是 10-08 從 main（`d08a1e794`）切的。之後 main 上的東西只有 backport 才在 rel；工具治理相關的 backport 只有 #6345。
- #5667 的留言說 dev 與 rel 曾部署 v1.77.0.9（這個 tag 含 v1 與 #5806）。**主機現在跑哪個 image：待查**。
- registry entry `tool_governance` 是 stage REL，所以 rel 看得到、prod 與未設標籤的客戶安裝扣住。prod 的 tree 根本還沒有這個功能。

---

## 1. 功能本身

### 1.1 使用者能設的選項

| 欄位 | 值 | 預設 | 意義 |
|---|---|---|---|
| `mode` | `shadow`／`enforce` | `shadow` | 影子模式（僅稽核）／強制模式（拿掉／擋下） |
| `tool_use` | `allow`／`deny` | `allow` | `deny`：請求只要帶任何工具（含歷史裡的工具回合）就回 400 |
| `tool_names.deny` | 名稱清單（exact 或 glob，只收 `*` 和 `?`） | 空 | 命中的工具在請求端拿掉；模型仍回傳命中的名稱，就擋下整輪 |
| `tool_names.allow` | `null` 或非空清單 | `null` | 清單外的工具在請求端拿掉；模型回傳清單外的名稱，就擋下整輪 |
| `tool_arguments` | `[{tool, arguments}]` | 缺席 | **Amendment D 參數契約**，見 §1.7。已 merge，但 IAM 在所有環境一律拒寫 |

其他固定欄位：
- `schema: tool_governance/v1`：判別欄位。加 `tool_arguments` 沒有升版。
- `actions`：保留欄位，帶值會回 400 `POLICY_KIND_HAS_NO_TRIGGER`。

名稱比對規則：
- `deny` 不分大小寫，`allow` 區分大小寫。
- 不收 regex；拒絕只由萬用字元組成的樣式。
- 每層每份清單最多 256 條、每條最多 128 字元。

### 1.2 繼承（fold）

- 套用層級：tenant → group → application → deployment，**只能收緊**，下層放寬不了上層。
- **雙 lattice**：`enforced` 只收強制模式的貢獻，`observed` 收全部。gateway 只依 `enforced` 動作；兩者的差集發 `would_*` 稽核。這點和 guardrail 的 enforce-wins 刻意不同。
- `deny` 取聯集。`allow` 是各層合取：一個名稱要在每一層都命中才算允許，`null` 的層不參與。
- 沒有 `enabled` 欄位。要停用，就**從政策集移除這條規則的項目**，絕不能用 Invalidate（它會讓所有 kind 一起 fail-closed）。
- tenant／group 層級的 key 不投影本 kind（值是 null）。不能套到 `app_type=llm_proxy` 的 app，所有寫入路徑都會回 400。

### 1.3 三條 API 路徑的行為（名稱規則）

| | `/v1/chat/completions`（OpenCode、自建） | `/v1/messages`（Claude Code） | `/v1/responses`（Codex） |
|---|---|---|---|
| 請求端 `tool_use: deny` | 400 `tool_not_allowed` | 400（Anthropic `invalid_request_error`） | 400 |
| 請求端名稱拿掉 | ✅ | ✅ | ✅ `function` 與 `custom`；`input` 裡的 `additional_tools`／`tool_search_output` 也算（#5988） |
| 回應端整輪擋下 | ✅ R-A in-band error | ✅ | ✅（#5806，v1.1）`response.failed`，`error.code=invalid_prompt`、`xparse.code=tool_call_denied` |
| 不受名稱規則管 | — | — | namespace 成員（MCP、sub-agent、code mode）：只記錄（Amendment C） |

`/v1/responses` 回應端（`gateway/responses_tool_rules.py` 的 `tool_rule_stage`）：
- 從第一個 client 執行的 call item 的 `output_item.added` 起扣住事件，一直到 provider 終端，判定沿用 `judge_turn`。
- 擋下時 retire binding；`store=true` 時 DELETE provider 端的 response。
- 名稱只看同一 `call_id` 第一筆 item 的名稱（C-304-302），是已知缺口（§6.5）。
- **A22 真 Codex 驗收是 BLOCKED**（#5810）：模型不再呼叫被拿掉的工具，回應端沒東西可觸發。請求端剝除與 hold-release 已用真 Codex 驗過。

請求端與回應端的細節：
- **全部拿掉時**：刪掉 `tools` 和 `tool_choice`。如果歷史裡還有工具回合，回 400。
- **`tool_choice` 指名的工具被拿掉**：改成 `auto`。
- **判定時點**：在 semantic cache lookup 之前。Tier V 稽核在拿掉之前擷取。
- **回應端出口**：
  - 不走 503，不觸發換模型的 fallback，也不記模型健康失敗。
  - 先 `aclose` manager 再讀 usage（P18 的結論）。
  - ledger 與 `EXECUTION_FAILED(tool_call_denied)` 都帶實際執行的模型。
- **一個被擋的回合可能是 2–3 個請求**：Claude Code 在串流被擋後會改送非串流，auto 模式還會拿掉 safeguards 再送一次。每個請求都各自完整判定、各自留稽核（C-304-158）。
- **工具呼叫審視（SPEC-304 Rev.25，#6363）**：缺 `required` 參數、或 arguments 不是 JSON 物件的呼叫**照交付**（只在終端記錄），不再是 503。被輸出上限截斷的呼叫不交付，回合以 `length`／`max_tokens` 結束。503 只在 `XPARSE_TOOL_CALL_ARGUMENTS_ENFORCE=1` 時出現。入口是 `tool_call_validation.review_tool_calls`。`/v1/responses` 只記錄（C-304-408，#6465）；provider 自己說沒收完的呼叫由 worker 標出（Rev.28，#6526）。

**對外說法**：
- Q5 的原句（Responses 只能說「被禁工具的定義不送給模型」）在 ADR 沒改。它的前提是「只有回應端 stage 能改變這個說法」，現在 stage 已存在，但 A22 沒有真 client 證據。改說法前先問 Peter。
- **不得聲稱 Tool 規則管得到 MCP、sub-agent 或 code mode 工具**（Amendment C）。
- 不得暗示參數契約涵蓋 client 的 `tool_search`（C-304-437）。

### 1.4 稽核事件（Q7、Q12）

- `audit.policy.violation`：只用於真正的拒絕或擋下（請求端 400、回應端整輪擋下、參數契約擋下 `violation_code=tool_arguments_denied`）。
- `audit.policy.tool_stripped`、`tool_would_block`、`tool_call_undeclared`、`tool_executed_despite_policy`：其他處置各有自己的事件。影子參數契約沿用 `tool_would_block`（`rule_id=tool_arguments`）。
- `tool_call_undeclared` 對 namespace 成員帶 `tool_namespace`；`tools_offered` 列 `<ns>.<tool>`。
- `audit.execution.platform_tool_stripped`：平台自己剝除 Responses 的工具時發（S0-b），回應也帶 `x-xparse-tools-stripped` header。
- 決策事件每請求上限 128 筆；拒絕事件不受這個上限限制（OQ-S9）。
- `tool_flat_name`（SPEC-064 §5.1）只是跨 client 的彙總鍵，不是規則比對的名字。

### 1.5 舊開關 `PolicyProfile.tool_call_allowed`

- 過渡期跟本 kind 取 AND。
- 三條路徑都回 400 `tool_not_allowed`：Responses 是 S0-c2（#5634）；chat／messages 是 Q2（#5709，403 → 400）。
- 稽核的 `violation_code` 仍是 `TOOL_CALL_NOT_ALLOWED`。
- **R-a**（INV-490-25、C-304-100）：舊開關會拒絕、而且本 kind 依 `enforced` 也會動作時，由舊開關先回。它決定 client 收到 400 還是拿掉後照送，**不能**簡化成只決定稽核歸屬。

### 1.6 Responses 上的其他工具型別（Q1、Amendment A／B／C）

| 型別 | 現況 | 來源 |
|---|---|---|
| `custom`（Codex apply_patch） | 原生出口開放，受名稱規則管；只送給接受 custom 的模型（`accepts_custom_tools`）；翻譯出口剝除並記 `tool:custom` | Q1（#6255）、Amendment A（#6283） |
| hosted `web_search`／`web_fetch` | **預設開放**，不需租戶 opt-in，不經 Tool 規則；只在同家族原生出口；逐次計量。止血只有 kill switch（只影響 messages）或回滾 image | Amendment B（#6311、#6313、#6315、#6316） |
| `namespace`、client `tool_search`、code mode `additional_tools`、apply_patch 歷史 | 原生出口原樣轉送；翻譯出口降成 function（`<namespace>__<tool>`）再還原；名稱規則不管 namespace 成員 | Amendment C（#6360） |
| 其他 hosted 型別 | 仍剝除，可見（header＋稽核） | S0-b |

- `tool_types` 被 Amendment B 取代，改成日後選配的「租戶關閉開關」。
- Amendment B 的真 client 驗收 P5（PW-4 Claude Code——ADR-490 引用 Claude Code 2.1.295 的 web_search 版本，非正式版本門檻；PW-5 Codex）**還沒跑**，跑之前不得宣稱完成。

### 1.7 參數契約（Amendment D，2026-10-15 全部程式切片已 merge）

**能表達什麼**：以工具名為鍵、租戶撰寫的參數值條件。例如：
- `refund` 的 `amount` ≤ 1000。
- `send_email` 的收件人只能是公司網域、不能多帶副本。

**形狀**：`tool_arguments: [{tool, arguments}]`，`arguments` 是 **profile 1**：
- 封閉、線性的 JSON Schema 子集，**沒有 regex**。另有 `x-xparse-glob`、`x-xparse-charset`、`x-xparse-email-domain-in`。
- 每個 `type: object` 節點都必須明寫 `additionalProperties`（`true` 或 `false`）；每個節點都必須有約束，不收空節點（D-D4）。
- 每版最多 32 份契約、每份 8 KiB、每版 64 KiB。投影上限 64 份／65536 字元，超量的工具 fail-closed。
- `tool` 不收萬用字元；比對 flat 名稱，原樣或 casefold 相等就適用。namespace 成員用 flat 名稱（`mcp__crm__refund`，D-D12）。

**fold**：不進 lattice。IAM 把 lineage 上每份契約串成一份清單，每筆帶 source 與 mode（跟該版本的 `mode`）。判定是合取，子層移除或放寬不了父層。

**三條路徑**：
- chat／messages（串流與非串流同序）：名稱判定 → 純審視 `review_tool_calls` → 契約 `judge_arguments` → 才輪到 env 的 503。擋下回 400 `tool_arguments_denied`，不是 503、不進 R1／R3、不記健康。
- `/v1/responses`（原生與翻譯、串流與非串流）：在 `tool_rule_stage` 裡、名稱判定之後判；擋下是 `response.failed`（`invalid_prompt`，`xparse.code=tool_arguments_denied`）。
- 文案依第一筆失敗原因三選一（違規／沒辦法檢查／被截斷），代碼都一樣（D-D10，owner to confirm）。
- gateway **永遠不改** `tools[]` 或 arguments。

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

**現在的實際效果是零**：IAM 對非空 `tool_arguments` 一律回 400 `TOOL_ARGUMENT_CONTRACTS_NOT_WRITABLE`，**所有環境**、HTTP 與 GitOps 都一樣，不看 registry（D-D17）。要等主管同意記錄進 ADR-490 Decision Makers，再由 R0 加 registry stage DEV 的 `tool_argument_contracts` 才開放 dev 寫入。

### 1.8 和主管（June）的 ADR-427 草案的關係

- ADR-427 指的是 PR #3978 的草案（未 merge，仍 OPEN），編號與 main 上的 ADR-427（slot lease）撞號。
- 兩案定位為正交並寫出組合規則（Q3）。本案是草案路線圖 P4 的「宣告層授權」。
- **U10（2026-10-14）重劃了分界**：以工具名為鍵、租戶撰寫的參數值契約改歸 ADR-490 Amendment D；依形狀分類的條件（verb／target、opaque_execute、shell 指令內容）仍歸草案。**主管同意尚待記錄**。
- 回應端同一個掛點上，本案的名稱判定與參數契約先跑。
- **不要動 PR #3978，也不要聯絡主管**（Peter 自己處理）。

---

## 2. 權威文件

| 文件 | 路徑 | 備註 |
|---|---|---|
| PRD | `docs/prd/PRD-337-agent-tool-governance-policy.md` | 需求、驗收（A／U／I／N 編號）、白話層。§4 A22（BLOCKED 結果見 §14 Rev.6）、§16 參數契約（PRD 的 Amendment B） |
| ADR | `docs/adr/ADR-490-tool-governance-policy-kind.md` | 決策 D1–D21、§7 分段與 probe、§10 Q 表；§13 Amendment B、§14 Amendment C、§15 Amendment D（D-D1..D-D22、§15.4 誠實上限、§15.8 切片表） |
| SPEC | `docs/spec/SPEC-304-tool-governance-behavioral-contracts.md` | 到 Rev.32，C-304 編號到 449。§8.6 Responses 回應端、§17 OQ-S 表、§23 HOSTED、§24 NAMESPACE、§25 ARGUMENTS |
| 研究（v1） | `docs/research/RESEARCH-agent-tool-governance-proxy-enforcement-2026-09-30.md` | 結論：「能擋工具」不是差異化，站得住的只有組合 |
| 研究（參數） | `docs/research/RESEARCH-agent-tool-argument-constraints-2026-10-14.md`（#6545） | 參數層先例、PRB-1..5 陷阱、放在哪一案 |
| 研究（web） | `docs/research/RESEARCH-web-search-native-passthrough-2026-10-10.md` | Amendment B 的依據 |
| Probe 證據 | `docs/research/poc/agent-tool-governance-probes-2026-10-01/README.md` | P2、P3、P7、P11、P16、P20，以及攔截器工具 |
| 本機驗證 | `docs/research/poc/agent-tool-governance-local-verification-2026-10-01/` | S0-b、P-POL-2、IAM 影子規則、P18、P19、G4 |
| A22 證據 | `docs/research/poc/responses-tool-rules-a22-codex-2026-10-04/` | 真 Codex，BLOCKED |
| 回滾 runbook | `docs/runbooks/tool-governance-rollback.md` | 混版、409→500、migration 0357；§5.5 IAM 回滾前查被套用的參數契約、§5.6 gateway 從 G-C 回滾前查 enforce 契約。§8 進度表 dev／rel／prod 全空白 |
| Wiki | `xparse-wiki/wiki/concepts/tool-governance-policy.md` | 概念頁 |
| Glossary | `docs/governance/console-i18n-zh-tw-glossary.md` | 「Tool 規則」等譯名（§3.5.1）。「Tool 參數限制」還沒加 |
| Core | `docs/adr/core/Core-ADR-02-*.md`、`docs/prd/core/Core-PRD-02-*.md` | 主領域 02；01、03、04、05、06、08、10、12 有 cross-ref |
| 被取代的文件 | ADR-331（整份）、PRD-257（整份）、PRD-316 的 `agent` 半邊 | issue #2634 已改掛 PRD-337（仍 OPEN） |

**編號對照**：PRD-337 的 Amendment A／B 對應 ADR-490 的 Amendment B／D。ADR-490 另有 Amendment A（custom 的模型閘門）與 Amendment C（namespace）。

**原始草案**（repo 外，僅供歷史參考）：`/Users/peter/Desktop/X-parse/docs/草案/agent-policy.md`（Rev.4）。

⚠️ **三份權威文件的 Status 行都過時**，下一次純文件 PR 一起修：
- ADR-490 第 3 行：仍寫 Q2「未合入」、v1「皆未部署」、Amendment B／D「未實作」。§15 開頭也寫「Proposed、未實作」。
- SPEC-304：§23、§25 標題寫「未實作」；§17 的 Q1 列仍寫「產品決策，v1.1」。
- PRD-337：Status 仍寫 OQ-2「已實作、未合入」、Amendment A／B「未實作」。

---

## 3. 程式碼地圖

### 3.1 IAM（`apps/iam/xparse_iam/xparse_iam/`）

| 檔案 | 作用 |
|---|---|
| `migrations/0357_adr490_tool_governance_policy_kind.py` | 放寬 versioned kind 的 CheckConstraint（expand-contract）。legacy `hierarchy.PolicyKind` **刻意不加** |
| `policies/tool_governance_content.py` | content schema 與驗證 |
| `policies/tool_name_matching.py` | 名稱比對：雙指標 glob，不用 regex |
| `policies/tool_argument_{contracts,profile,strings,types,values}.py` | 參數契約的讀取、profile 1 驗證、字串與數值規則 |
| `application/use_cases/policy/validate_policy_content.py` | `_refuse_argument_contracts()`：一律拒寫（D-D17），排在其他驗證之後 |
| `authorization/tool_governance_resolver.py`、`tool_governance_fold.py`、`tool_governance_projection.py` | 解析、雙 lattice fold、validate 投影 |
| `authorization/tool_argument_fold.py` | 契約串接 fold 與投影上限 |
| `api/ninja_api/_tool_governance_capability.py` | 能力 header `X-Gateway-Tool-Governance`：缺 header 且有強制貢獻時回 409（Q4 fail-closed）。W1 起也辨認 `X-Gateway-Tool-Argument-Contracts` |
| `db/django_database/_tool_governance_targets.py` | 套用目標檢查，拒絕 llm_proxy |
| `db/models/hosted_tool_price.py`、`migrations/0378_adr489_hosted_tool_usage_meter.py` | Amendment B 逐次計量的價表 |
| `core/pre_release_features.py` | `tool_governance`：stage REL、owner Peter、expires 2026-12-21。還沒有 `tool_argument_contracts` |
| `../contracts/tool-governance-policy.v1.schema.json` | 投影的 wire 契約 |
| `../contracts/tool-name-match.v1.json`（+publisher） | 名稱比對 golden vectors，gateway 有逐位元相同的副本 |
| `../contracts/tool-argument-contract.v1.json`（+publisher）、`tool-governance-policy.v1.samples.json`（+publisher） | 參數契約 vectors 與投影樣本 |
| 測試 | `tests/{unit,integration,contract}/test_spec304_*.py`（含 `test_spec304_tool_argument_contracts_gate.py`、`_profile.py`、`_vectors.py`） |

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
| `gateway/tool_governance_request.py` | 請求端計畫：拿掉工具、拒絕、`tool_choice` 處理 |
| `gateway/chat_tool_governance.py` | chat／messages 的 TG stage，含 R-a 先行 |
| `gateway/responses_tool_governance.py` | Responses 步驟 1.3：legacy、本 kind、平台剝除 |
| `gateway/tool_governance_response.py` | chat／messages 回應端整輪擋下（R-A），含 `judge_arguments` |
| `gateway/responses_tool_rules.py` | Responses 回應端 `tool_rule_stage`（#5806） |
| `gateway/responses_held_calls.py`、`responses_argument_calls.py` | Responses 扣住的 call item、逐事件收集參數候選 |
| `gateway/tool_call_validation.py` | `review_tool_calls`：純審視，不 raise（Rev.25） |
| `gateway/tool_argument_{contracts,profile,compiled,evaluation,judgement,index,matchers,charsets,scalars,strings,values,verdicts}.py` | 參數契約：讀投影、編譯、嚴格讀取、判定、結果 |
| `gateway/tool_governance_events.py` | 稽核事件組裝 |
| `gateway/tool_governance_decisions.py`、`tool_governance_errors.py`、`tool_governance_metrics.py` | 決策計數（128 上限）、固定文案、metric |
| `gateway/responses_tools_filter.py` | 平台剝除的計算與 header 編碼器 |
| `gateway/pre_execution.py` | `reject_tool_calls_not_allowed`：舊開關拒絕的唯一產生點 |
| `gateway/iam_http_client.py` | 送出兩個能力 header（G-C 起含參數契約） |
| `gateway/routes/{chat,messages,responses}.py` | 三條路徑的接線 |
| `gateway/json_nesting.py`、`gateway/json_body_bound.py`、`json_containers.py` | event loop 上的 JSON 解碼上限（深度、容器數；#6547..#6634） |
| `streaming/hosted_tool_usage.py` | Amendment B 託管工具次數 |
| `contracts/tool-argument-contract.consumer.v1.json`、`tool-governance-policy.samples.consumer.v1.json` | 參數契約與樣本的 consumer 副本 |
| `scripts/responses_tool_call_allowed_census.py` | 唯讀普查：找出 `tool_call_allowed=false` 的 app 與流量 |
| 測試 | `tests/integration/test_spec304_*.py`（含 `test_spec304_{chat,responses}_argument_contracts.py`）、`tests/unit/test_spec304_*.py`、`tests/contract/test_spec304_*_wiring.py`、`test_*_decode_budget*.py`；root 的 `tests/contract/test_gateway_iam_http_cutover.py`（PD-9） |

### 3.3 Console（`frontend/console-app-refactor/src/`）

| 檔案 | 作用 |
|---|---|
| `app/(main)/(ai-gateway)/policies/_components/policy/tool-governance-settings.tsx`、`tool-governance-content.ts` | 建立與編輯表單。#5732 攤平成一個區塊、一個範本選擇器；名稱輸入接受任何逗號或空白；C1（#6586）原樣保留 `tool_arguments` |
| `components/features/policy/tool-governance-binding.ts` | 套用目標檢查（隱藏 LLM Proxy） |
| `components/features/policy/tool-governance-effective*.ts(x)` | effective-policy 逐欄來源的顯示 |
| `app/(main)/(overview)/(dashboard)/_components/pre-release-rows.ts`、`_tabs/safety-policy/initial-layout.ts` | dashboard 的 Tool 規則違規列（G4） |
| `i18n/messages/{en,zh-TW}.json` | 譯名照 glossary。`policy_violation_code` 對照表還沒有 `tool_arguments_denied` |

kind 的選項由 `usePreReleaseFeature('tool_governance')` 控制顯示。參數契約**沒有編輯畫面**（下一批）。

### 3.4 CI gate

- `.github/scripts/tool-governance-parity-gate.py`（含 `--self-test`）：IAM vectors 與 gateway 副本逐位元一致、consumer 契約完整。W1 加了第 3、4 節（參數契約與樣本）。
- #5675 的 AST 檢查：每個 `StreamingManagerV3(...)` 都必須接上 audit emitter。
- `pre-release-feature-registry-gate`：IAM 與 Console 兩邊都必須列 `tool_governance`。
- `response-checks-gate`：`gateway/response_checks.py` 的宣告（D-D15 把 `judge_arguments` 加進 chat 的 Run cell）。

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

**前置與順手修**：#6547、#6549、#6553、#6554、#6559（深巢狀／非物件 JSON 不再 500）、#6560（超長整數）、#6619（非有限數值）、#6618、#6629、#6630、#6634（event loop 上的解碼上限，SPEC-304 Rev.30–32、SPEC-219 Rev.12）、#6624（請求 body 容器數上限，SPEC-307 RF-20）、#6588（Console 新版本對話框保留預填的 enforce）。

**部署順序**（已查證）：`deployments/operations/scripts/blue-green-deploy.sh` 的 `cmd_deploy` 依序是 IAM → gateway（切流量）→ Console。`cmd_rollback` 只切 gateway 的顏色，回滾後有強制規則的 app 會回 500（Q4 fail-closed，runbook 有記錄）。

---

## 5. 實測得到的關鍵事實（設計依據）

- **P16**：請求端拿掉 `exec_command` 後，模型若依歷史仍吐出它，Codex **會照執行**。
- **P7**：Codex 對 Responses 的 `event: error` 和 `response.incomplete` 都會重試 5 次。v1.1 因此定案用 E 類 `response.failed`（`invalid_prompt`），Codex 收到就停。模型最多連續重叫被拒的工具 15 次，所以 `deny_as_tool_error` 要先有次數上限。
- chat／messages 採 R-A（in-band error）。OpenCode 不重試；Claude Code 會改送非串流加 auto 重送。
- **OpenCode 的重試字串**：錯誤文案不得含 429、500、502、503、504、524、try again later、timeout、rate limit 等字樣（golden TC，C-304-157）。
- **P2**：OpenAI 與 DeepSeek 在「全部拿掉＋歷史有工具回合」時回 200，但輸出不可用。所以這種情況維持 400。
- **P3**：OpenAI 在沒有 tools 時，`tool_choice` 連 `"none"` 也回 400。
- **P18**：被擋時 `manager.run()` 的 finally 不會自動在讀 usage 之前跑完，必須先 `aclose`。
- **P19**：tenant／group 層級的 key 打不到推論。但 tenant_auditor、group_admin、app_user 是靠授權資料擋住，不是結構性的閘。
- **A22**：模型不再叫被拿掉的工具，所以回應端擋下在真 Codex 上沒機會觸發。
- **參數研究的四個陷阱**（PRB-1..5）：jsonschema 的 `pattern` 有 ReDoS（24 字元要 0.6 秒）；NaN 通過上下限；重複鍵 last-wins；深巢狀丟 `RecursionError`。Python 3.11 對 4301 位以上整數丟純 `ValueError`。這些都是 F0 與解碼上限 PR 的起因。
- **twin 路徑**：所有 ExecutionPlan 都是 direct，twin 是死路。

---

## 6. 還沒做的事、open 項目

### 6.1 需要部署或遠端授權（Peter 未授權，不要自己做）

- **v1 上 prod 前**：
  - dev 真流量影子觀察 ≥7 天、probe P4／P5／P15、P14 回滾演練（registry reason 與 C-304-203 列的三組條件，都沒做）。
  - prod 唯讀普查 `tool_call_allowed=false` 的 profile 數量（S0-c2、#5709 需要）。rel／prod 部署前的唯讀普查是 SPEC-304 C-304-11 的後續待辦（S0-c2 列），目前只附了 dev 普查（TC-304-7）；**rel 有沒有跑過，在 repo 找不到紀錄**。另外 runbook §8 進度表（§5.1 查詢／P14 回滾演練／§5.6 查詢）在 dev、rel、prod 三個環境都空白。
  - registry 畢業（C-304-203）：上述全部完成後，同一個 PR 刪 entry 與兩端 call site。
- **Amendment D**：W1、G-C、C1 部署到 dev，且 dev 的 IAM 回滾目標含 W1（R0 的前提）。
- **Amendment B**：P5 真 client 驗收（PW-4、PW-5）。在哪個環境跑：待查。
- rel／prod 主機現在跑的版本：待查。

### 6.2 等 Peter 或主管決定的事

| 項目 | 內容 | 狀態 |
|---|---|---|
| 主管同意 | U10 重劃分界，要記錄到 ADR-490 Decision Makers（姓名、日期）；R0 的前提 | 待記錄（Peter 處理） |
| D-D7（Q13／OQ-S8） | 演進通則：先能讀後開放寫、每個新投影欄位一個能力 header | owner to confirm（暫採） |
| D-D10 | 代碼 `tool_arguments_denied` 與三句英文文案 | owner to confirm |
| D-D18 | shell／exec 工具可寫契約，文案誠實說明 | owner to confirm |
| D-D19 | 門檻是政策內容、不是秘密；effective-policy 只加 provenance | owner to confirm |
| D-D22 | 預算數字；等 PD-6 容器實測（本機估計每輪節點預算也許降到 8192） | owner to confirm |
| 十進位精度 | 小數字面值以 IEEE double 比較，或拒收 >17 位有效數字 | **R0 之前要定** |
| 孤兒參數事件 | provider 失敗終端上的孤兒參數事件只計數、不判定 | owner to confirm |
| Amendment B | C-304-355 的 allowed_callers 規則、C-304-367 的 STRIP_RECORD | owner to confirm |
| Q9 | v1.1 `tool_denied` trigger 的 `default_enforcement`（建議 observe） | 未定 |
| Q14／OQ-S11 | 「剛擋過」的短時效記錄，讓 Claude Code 的重送在打 provider 前就被擋 | 未定 |
| Q15 | 名稱規則要不要管 namespace 成員；tracking issue 等產品負責人開 | 未定 |
| OQ-S2 | chat 的舊開關把 `tools: []` 算成帶工具，messages 不算 | 未定 |
| OQ-S13 | `tool_choice` 用 `allowed_tools` 形狀、指名的工具被拿掉時怎麼處理 | 未定 |
| — | P19 三種角色要不要加結構性 guard；串流純文字多 1 筆 `streaming_phase_changed` | 未定 |

已定：Q1（10-08）、OQ-S6（10-08）、D-D4、D-D12（Q16）、D-D13（Q17）、D-D17（10-15）。

v1.1 待做清單剩：session 呼叫上限（需 ADR-268 Amendment C）、`deny_as_tool_error`（要有拒絕次數上限）、rewrite 評估、ADR-461 `tool_denied` trigger。

### 6.3 Amendment D 剩下的切片

1. **主管同意記錄**（§6.2）。
2. **R0**：registry 加 stage DEV 的 `tool_argument_contracts`，取代無條件拒絕，開放 dev 寫入。前提：主管同意已記錄、W1／G-C／C1 已部署到 dev、dev 的 IAM 回滾目標含 W1、十進位精度已定。
3. **P**：PD-1..PD-10 實測，10-15 全部標「未跑」，只有 PD-9 在本機跑過。PD-6 是容器預算、PD-2／PD-4 真 client、PD-5／PD-10 錄製的 namespace／custom 呼叫串流。
4. **R**：晉級 REL；之後才是畢業。dev 影子觀察可能需要一個合成的 ERP-like 測試 agent（目前沒有帶業務工具的 agent）。
5. **Console 編輯表單**：glossary 加「Tool 參數限制」、`policy_violation_code` 對照表加 `tool_arguments_denied`（目前**沒有切片負責**）、手冊兩頁。
6. **Codex apply_patch 路徑抽取器**：patch 文法，不是 JSON Schema，另開切片。
7. **I1b**：effective-policy provenance，延後。

### 6.4 Open issue（2026-10-16 查過）

| Issue | 內容 | 狀態 |
|---|---|---|
| #5666 | `tools: []` 加 `tool_choice` 送到 OpenAI 回 400（P3） | OPEN |
| #5668 | ADR-455 bridge 遇到 incomplete／failed 時，已累積的工具呼叫被丟掉（P1） | OPEN |
| #5672 | C-304-68 套用預覽（IAM）未交付 | OPEN |
| #5673 | 「從稽核挑名稱」與 7 天工具流量的彙總查詢 | OPEN |
| #5674 | validate 熱路徑：每個 kind 各讀一次 scope，本 kind 多 6–20 個查詢 | OPEN |
| #2634 | tool-type authorization（已改掛 PRD-337） | OPEN |
| #6243 | rel v1.77.0.9 部署驗證清單（含 #5667、#5669、#5671 的修正） | OPEN |

已關閉：
- 在 rel、不在 prod：#5667（#6022）、#5669（#5750）、#5670（#5757）、#5671（#5843）、#5753（#5806）、#5988（#6020）。
- 只在 main（修正在 rel 切點 d08a1e794 之後才 merge）：#6217（#6253）、#6299（#6300）。
相關但不屬本 kind：#5897、#6166、#5503、#5502。

### 6.5 已知缺口（Amendment D 期間發現，都還沒開 issue）

- client 執行的 `tool_search_call` 不被 hold 或判定，針對它的契約永遠不適用，而且沒有訊號（C-304-437）。
- `/v1/responses` 名稱規則只看第一筆 item 的名稱（C-304-302）。
- `responses_tool_rules._turn_call_items` 在 2000 個呼叫時要 70–84 ms（本機）。
- 契約扣下時，provider 失敗不記健康。
- 無狀態的 `/v1/responses` 請求仍需要 `XPARSE_BOOTSTRAP_ADMIN_KEY`（既有問題）。
- G-A 的 fuzz 測試在 Python 3.12 失敗（CI 固定 3.11）。
- 本機 Python 3.11.1 跑 redis 相關測試要補 `async_timeout`。
- 舊的小 follow-up 仍在：skew metric 告警規則、R3 fallback 後稽核 provider 歸屬、`tests/contract/test_azure_plan_resolver.py::test_azure_twin_plan` 死測試、SPEC-290 C-290-34 註記、三份文件的 Status 行（§2）。

### 6.6 未來可以做的（超出名稱與參數）

依 10-14 的競品調查排序（沒寫成正式文件；「誰在做」只記當時查到的，工作量是粗估）：

| # | 選項 | 做什麼 | 誰已經在做 | 歸屬 | 工作量 | 建議 |
|---|---|---|---|---|---|---|
| 1 | 工具結果的 prompt injection 篩檢 | 掃歷史裡的 tool result | LiteLLM `scan_only_tool_results`、MS Foundry、Lakera、LlamaFirewall PromptGuard | guardrail 領域（今天 classifier rail 不讀 tool role；PII／word filter 有讀） | 中 | 先做，影子起步 |
| 2 | 送往雲端的工具結果做 DLP | 例如 `cat .env` 的輸出，依 `route_target` 決定 | 沒查到前例 | proxy 原生；ADR-511 route_target＋ADR-448 PII | 中 | 做，Xparse 位置獨有 |
| 3 | 工具參數裡的 secrets／DLP | output rail 掃參數 | IBM ContextForge Secrets Detection、LiteLLM content filter、Lakera DLP、Cloudflare DLP（多在 MCP hop） | guardrail output rail；只在 buffer 模式擋得住 | 小–中 | 做 |
| 4 | session／每工具呼叫上限、拒絕重試上限 | `deny_as_tool_error` 的前提（P7 看過 15 次重叫） | AWS AgentCore temporal count（AWS 自己說不是安全控制）、gh-aw-mcpg、ContextForge、LiteLLM `mcp_rpm_limit` | ADR-490 v1.1／v2（需 ADR-268 Am.C） | 中 | 做，已在 backlog |
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

- **gateway 與 IAM**：容器 `xparse-gateway`、`xparse-iam`，原始碼 **bind-mount 主 checkout** `/Users/peter/Desktop/X-parse/xparse`。
  - 主 checkout 目前在 `b1f5708d9`（10-15，#6621），含 #5709 與 G-C，落後 origin/main 16 個 commit。
  - 要跑最新程式碼，得先 `git merge --ff-only origin/main` 再重啟容器（先確認不會動到 §7.4 列的本機狀態）。
- **入口**：
  - gateway：`https://localhost:3000/v1/*`，自簽憑證。Node client 要設 `NODE_EXTRA_CA_CERTS=/Users/peter/Desktop/X-parse/xparse/certs/cert.pem`。
  - IAM：`https://localhost:3000/apis/iam/*`，或 Console dev server `http://localhost:4001/apis/iam/*`。
- **測試用 key**：在 `/Users/peter/Desktop/testing/.env`。只用 `grep -E '^NAME='` 讀單一變數，**不要 cat 整個檔**。
  - `XPARSE_ADMIN_KEY`：tenant_admin，打推論回 403。
  - `XPARSE_PROBE_KEY_816E`：app 5260605d 的 native key。
  - `XPARSE_PROBE_KEY_HYBRID`：Responses 用的 app 603adf8b。
  - 細節見 `docs/research/poc/agent-tool-governance-probes-2026-10-01/facts.md`。
- **app `5260605d-a3d8-4068-873e-b2ee5bf29c48`**：Peter 的測試 app，**不要動**。驗證時另建專用的 profile 和 app，驗完清掉。
- **client 版本**（10-02 時；Amendment B 的 PW-4：ADR-490 引用 Claude Code 2.1.295 的 web_search 版本，≥2.1.295 是推論、不是正式門檻）：
  - Codex 0.154.0：用隔離的 `CODEX_HOME`，不要改 `~/.codex/config.toml`。
  - Claude Code 2.1.285：用 `ANTHROPIC_BASE_URL` 和 `ANTHROPIC_AUTH_TOKEN`。
  - OpenCode 1.18.31：`~/.config/opencode/opencode.json` 指向 `http://localhost:4001/v1`。
- **攔截器**：`/Users/peter/Desktop/testing/tool_gov_interceptor.py`（錄製、`--strip-tools`、`--block-on-tool-call`）。
- **跑 PR 程式碼的 probe gateway**：從 worktree 起獨立容器，不要重啟共用容器。見 memory `reference_live_ab_two_probe_gateways.md`。

### 7.2 跑測試

不要用主機的 python。用 ephemeral 容器，**固定 Python 3.11**（CI 也是 3.11；G-A 的 fuzz 測試在 3.12 會紅）：

```bash
WT=<worktree>
docker run --rm --network none -v $WT:/w:ro -v apv1-g3-gwvenv:/w/apps/gateway/bustream/.venv \
  -w /w/apps/gateway/bustream -e XPARSE_ROUTING_DB_URL=sqlite:////tmp/r.db -e XPARSE_CACHE_SALT_SECRET=x \
  python:3.11-slim sh -c 'PYTHONPATH=/w/apps/gateway:/w/apps/gateway/bustream .venv/bin/python -m pytest -q -o addopts="" tests/integration/test_spec304_*.py'
```

- 共用 venv volume 若是用 3.12 建的，要換一個 3.11 的 volume。本機 3.11.1 跑 redis 相關測試要補 `async_timeout`。
- 新測試要登記進 `gateway-ci-suite.txt`。
- IAM：`python:3.11-slim` + `uv sync --extra dev --extra postgres --frozen`。見 memory `reference_iam_ephemeral_test_run.md`。
- Console：在 worktree 的 `frontend/console-app-refactor` 先跑 `pnpm install --offline --frozen-lockfile --ignore-scripts`，再跑 `tsc --noEmit`、`vitest`、`scripts/i18n-*.mjs`。

### 7.3 Git 與 PR 的固定套路

- **一律在 worktree 工作**：`/Users/peter/Desktop/X-parse/pr-worktrees/<name>`，從 `origin/main` 開分支。
  - 已 merge、可以清的：`apv1-*`、`tool-arg-contracts-*`、`tool-arg-constraints`、`codex-custom-6198`、`chat-strip-6217`、`custom-model-gate`、`tool-rule-*` 等。清之前確認分支已 merge、沒有未推的東西。
- **驗收產生檔**（`docs/testing/feature-inventory/*.json`、`docs/testing/qa-evidence-v2/excel-inventory.json`、兩個 `docs/testing/*.xlsx`）幾乎每次 merge main 都會衝突：
  1. `git merge origin/main`，不要 rebase。
  2. 這幾個檔取 theirs。
  3. 另開 commit 跑 `python3 scripts/testing/build_feature_acceptance_workbook.py --write`，再跑 `--check`。
- **merge main 時的 commit 用 `--no-verify`**：否則 pre-commit hook 會把 main 帶進來的前端檔重新排版。
- **多支 PR 互相衝突時用 squash merge train**（memory `reference_squash_merge_train_procedure.md`）：
  - 建鏈：節點 K = 節點 K-1 merge PR K 的 head。
  - 前一支 squash 之後，在下一節點先 `git merge <前一節點 head>`（也就是 `<squash>^` 那一側的內容），再 `git merge -s ours <squash commit>`。先確認 `git diff --quiet <squash> <前一節點 head>`，推之前確認 PR 的檔案清單縮回自己的檔案。
  - main 若進了別人的 commit，不能直接 `-s ours`，要把那些路徑改回 main 的版本。gitlink 用 `git ls-tree` 判斷，不要用 `cat-file -e`。
  - 動到 `apps/iam/` 的 PR 排在鏈尾。
- **PR 描述**：`Acceptance-Impact: none` 單獨一行；改到程式碼的 PR 附 ADR-093 五列表；結尾加 `🤖 Generated with [Claude Code](https://claude.com/claude-code)`。
- **commit 訊息**結尾加 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。
- **合併**：repo **不允許 auto-merge**，要手動 `gh pr merge <n> --squash`；base 必須是 `main`。main 沒有 branch protection，樹相同且驗過的節點不必每支等 CI。auto mode 有時會擋合併指令，不要繞過，請 Peter 自己合。
- Claude 桌面 app 的 Auto-fix（PR 列的 CI 監看開關，不在 repo 裡）：開了之後 CI 紅或出現衝突會叫醒該 session 修；CI 綠不會通知，merge 要手動下（repo 不允許 auto-merge）。
- `~/.gitconfig` 的 `insteadOf` 空 token 會讓 `git fetch` 401。不要改 global config，遇到時回報 Peter。見 memory `reference_git_push_insteadof_empty_token.md`。

### 7.4 Peter 的硬性規則

- **不准用 `git stash`**：所有 worktree 共用 `refs/stash`，裡面有 Peter 的舊 stash。
- **主 checkout 的本機狀態要保留**：`3rd/xparse_audit` 的改動、`frontend/console-app/`、`pr-worktrees/` 都不准 reset、clean 或 stash。
- **不准建強制模式的 Tool 規則或參數契約**（本機也不行，除非 Peter 明說）。
- **不做部署或遠端環境操作**（rel／prod 的查詢只能寫成 follow-up）。
- **不動 PR #3978，不聯絡主管**（Peter 處理）。
- **不把任何 key 寫進 commit、PR、文件或證據。**
- **遇到以下情況要停下來問**：要建強制規則、要部署或遠端操作、結果推翻 ADR-490／SPEC-304 的核心決策、要改到 #3978、要開放參數契約寫入（R0）。

### 7.5 其他參考

- **Memory**：`/Users/peter/.claude/projects/-Users-peter-Desktop-X-parse-xparse/memory/project_agent_policy_v1_design_closure.md`，以及 `MEMORY.md` 索引裡的相關 reference。
- **既有研究**：`docs/research/RESEARCH-agent-client-block-status-retry-behaviour-2026-09-15.md`（三家 client 對 HTTP 狀態碼的重試行為）。

---

## 8. 建議的下一步（依優先順序）

1. `git fetch` 後看 `git log origin/main`，確認 §4 的 PR 都在、有沒有新的相關 commit。
2. **純文件 PR**：同步 ADR-490 Status 與 §15 開頭、SPEC-304 §23／§25 標題與 §17 Q1 列、PRD-337 Status（§2 的清單）。
3. **開 issue**（走 `/doc-issue`）：§6.5 的 `tool_search_call`、第一筆 item 名稱、`_turn_call_items` 成本；以及 Console `tool_arguments_denied` 對照表沒人負責。
4. **Amendment D 往前推**：Peter 記錄主管同意 → 定十進位精度 → dev 部署 W1／G-C／C1 → R0 → PD-1..PD-10 → R。每一步都要 Peter 授權。
5. **Amendment B 驗收**：P5（PW-4 Claude Code、PW-5 Codex）。跑之前不得宣稱完成。
6. **v1 上 prod**：prod 唯讀普查、補記 rel 普查、dev 影子觀察 ≥7 天、P4／P5／P15、P14 回滾演練、registry 畢業。都要授權。
7. 依 Peter 的優先順序處理 §6.4 issue（#5668 是 P1）、§6.2 待決題、v1.1 剩下的項目，以及 §6.6 的延伸方向（建議先看 1、2、5、12）。
