# LLM Proxy 翻譯軸：任何 agent 都能用任何 provider 的模型

> **日期**：2026-10-08 起稿；10-10、10-12、10-13、10-14 四次更新。
> **2026-10-14 更新**：
> - §2.1.11 加入 readiness 稽核的 19 支修正（#6447 於 10-13 20:07 先合，其餘 18 支 10-14 03:45～03:56 合併，到 #6471 `e2923aeef`）；§2.1.12 加入 10-14 本機真 CLI 實測後的 11 支修正（10-14 18:14～18:26，到 #6515 `ee1a40564`），其中 #6514 是 owner 的決定：gateway 不再替 client 補輸出上限。
> - 依這 30 支更正過時的敘述：#6376 已合併；`claude/gifted-shamir-220761` 已被 #6459 取代；`/v1/messages` 對非 Claude 模型已逐段輸出；DeepSeek 的強制 `tool_choice`、`json_schema`、`developer` 已處理；Claude 現行家族改成版本規則；被截斷的工具呼叫；rel（v1.77.0.16）與 IAM migration（到 `0387`）；正式文件的 Rev 號；本機 dev stack 的版本。
> - 10-14 已在 `bff643332` 用三個真 CLI 跑過一輪（§2.3）；之後的 11 支沒有整體重跑。
>
> **2026-10-13 更新**：
> - §2 加入 10-12～13 合併的 20 支 PR（§2.1.7–2.1.10）：12 支修正、5 支 token 計數、1 份研究，以及 silvia 的兩支 Budget 修正。來源是 10-12 的程式審查與兩輪真 agent 實測（§2.3；報告 `/Users/peter/Desktop/testing/results/e2e_20261012/REPORT.md`）。
> - 更正過時的敘述：`main`／rel 的 head 與本機 dev stack 的版本；正式文件的 Rev 號；Codex 的 `custom`「在翻譯路徑上剝除」、`namespace`／`tool_search`「一律剝除」、`tool_search_output`「載入的工具不併入請求」；「帶 `context_management` 就退翻譯」；「原生優先」的定義；遮罩只影響「那一輪」的 cache；IAM migration 的範圍（`0369`–`0378` → `0369`–`0381`）；KEY2 app 的 judge 與 pool；Codex catalog「不覆寫就沒有工具」。
> - §1.3、§2.4、§2.5、§3、§4 依新狀態重寫；刪掉已結案或過期的內容（「main 是紅的」、10-09 的額度歷史、舊的 dev stack 描述、console dev server 停過一次）。
> - 之前的更新：10-12 加入 typed tool 分類（#6300）、信封金鑰自動佈建（#6302）、hosted `web_search`／`web_fetch`（#6301、#6311、#6313、#6315、#6316）；10-10 加入 §2.1.1–2.1.3 的後續修正與實測。
>
> **狀態**（2026-10-14 晚上）：
> - P1–P9 九支 PR 都已合併到 `main`（最後一支 P9 是 #6218 `b32114bc5`）。
> - 之後依 §3.3 的 issue 與兩輪 agent 實測，合併了 19 支修正 PR（§2.1.1–2.1.3，到 #6290 `880d83612`，2026-10-09 23:56）。
> - 10-11～12 再合併 7 支（§2.1.4–2.1.6，到 #6315 `bc0107d31`，10-12 08:01）。
> - 10-12 做了一次程式審查加兩輪真 client 實測，10-12～13 合併 18 支（§2.1.7–2.1.9，到 #6382 `ae9b63515`，10-13 12:00），另有 silvia 的 #6367、#6397（§2.1.10）。
> - 10-13～14 再合併 30 支：readiness 稽核的 19 支（§2.1.11，到 #6471 `e2923aeef`）與 10-14 實測後的 11 支（§2.1.12，到 #6515 `ee1a40564`）。這 30 支都只在 `main`。`main` 目前在 `ee1a40564`（10-14 18:26）。
> - 還開著：沒有。#6376 已合併（`ed7790fde`，10-13 13:48，8 個檔的審查後續）；分支 `claude/gifted-shamir-220761` 已被 #6459 取代（遠端分支保留，要不要刪由你決定，§3.3）。
> - issue：§3.3 共 14 張（原 12 張加 Budget 的 #6353、#6354），13 張已關閉，只剩 #6199（要實測 Bedrock）。
> - **rel 只到 P8，prod 全無**（10-14 重新核對，結論不變）：`origin/rel` = `2534867ad`（tag v1.77.0.16，commit 10-14 12:06）。它比 v1.77.0.10 多了 IAM／Fleet 權限修正、console 與 CVE 修正、一次 IAM OpenAPI 重產，以及一支 gateway 修正 #6345（`TOOL_CALL_RESOLVED` 帶 group 與 proxy 範圍；不是翻譯軸），沒有 migration。翻譯軸的內容跟 v1.77.0.10 一樣：只有 P1–P8 與 Phase 0 的 4 支修正（#6195、#6197、#6203、#6207），不含 P9 #6218 和之後任何一支 PR；`origin/prod` = `ed62d8223`（v1.76.4，10-02 17:38）全部都不含。10-12～14 的修正也都只在 `main`。上線見 §3.1。
> - 本機 dev stack 跑的是最新 main `ee1a40564`（gateway 與 IAM 容器 10-14 19:17 重建），含到 #6515 為止的全部修正；信封金鑰已自動產生（§3.5）。10-12 的兩輪實測直接打本機 stack（第一輪 `54ce1e9dc`、第二輪 `0d732f166`）。10-14 在本機 dev stack（main `bff643332`，含到 readiness 19 支為止的全部修正）用真 Claude Code 2.1.296、Codex 0.154、OpenCode 1.18.34 跑了一輪，共 779 個請求，0 個 5xx（§2.3）。**之後合併的 11 支（§2.1.12）只有各自的直連或錄製檔證據，合併後沒有再用三個真 CLI 重跑。**
>
> **正式文件**（以這三份為準）：
> - `docs/prd/PRD-350-any-agent-any-provider-translation-axis.md`（B3 的 document 部分已由 #6359 解決）
> - `docs/adr/ADR-503-llm-translation-axis-items-pivot-and-wire-codecs.md`：Rev.11（Rev.6 = #6338 跨家族歷史、Rev.7 = #6361 thinking 與前綴、Rev.8 = #6359 document、Rev.9 = #6446 client profile 與 G1、Rev.10 = #6512 只收 `json_object` 的模型、Rev.11 = #6516 prefill 接續）
> - `docs/spec/SPEC-312-llm-translation-axis-contracts.md`：10-12 新增 C-312-29c、§5.5 C-312-30a～30g、C-312-52..55、§13（C-312-56..59）；10-13～14 新增 C-312-58a、C-312-60～67
>
> **工具與計量的正式文件**：
> - `docs/adr/ADR-490-tool-governance-policy-kind.md` Rev.16（Amendment B §13：hosted 工具；Amendment C §14：`namespace`／client `tool_search`／code mode／apply_patch 歷史放行，Q15、INV-490-33..36）
> - `docs/spec/SPEC-304-tool-governance-behavioral-contracts.md` Rev.28（§23 hosted；Rev.25：C-304-143／143a／143b；Rev.26：§24，C-304-400..407；Rev.27 = #6465 `/v1/responses` 只記錄、`tool_flat_name`；Rev.28 = #6526 provider 說沒收完的工具呼叫）、`docs/prd/PRD-337-agent-tool-governance-policy.md` Rev.9（Amendment A，§15）
> - `docs/adr/ADR-489-usage-ledger-single-metering-record-iam-only-pricer.md` Amendment A、`docs/spec/SPEC-302-single-metering-record-and-pricer-behavioral-contracts.md` Rev.19（Rev.12：C-302-112..114；Rev.15 = #6451 用量可見性；Rev.16 = #6469 用量軸跨 owner；Rev.17 = #6471 盤點；Rev.18 = #6509 classifier degraded；Rev.19 = #6513 OpenAI cache-write 事實）
> - SPEC-312 §12（C-312-46..50）、§5.1 C-312-22（信封金鑰狀態與佈建）
>
> **10-12～14 修訂的其他正式文件**：
> - 參數與訊息形狀：SPEC-256 Rev.21（Rev.15 = §1.8 C-256-D16；Rev.16 = §1.9 D17、INV-256-16；Rev.17 = #6452；Rev.18 = #6476 矩陣；Rev.19 = #6503 D18；Rev.20 = #6514 D19；Rev.21 = #6534 D9m）、ADR-338 Amendment 2026-10-12 與 Amendment 2026-10-14（#6514）、ADR-455 Rev.5、ADR-239 §2.1.10、SPEC-035 Rev.3
> - 10-13～14 另有：ADR-239 Amendment C（#6475）、ADR-494 Amendment B（#6474）、ADR-285 Amendment A（#6459）
> - 串流時限：ADR-313 Amendment A（INV-313-7／8）、ADR-334、SPEC-311 C-311-42a
> - 路由、session、健康分數：SPEC-264 Rev.14、SPEC-266 Rev.11、ADR-406 Amendment H、ADR-411 Amendment F；SPEC-290 Rev.12（Rev.11 = `/compact`；Rev.12 = 健康分數）、ADR-447 Rev.8（Amendment G）；SPEC-307 Rev.7（RF-8）；ADR-321 Amendment B（B-3）
> - token 計數：ADR-419 Amendment D～I、SPEC-270（C-270-29..55）、SPEC-276 Rev.21（OBJ-C4）
> - Budget（silvia）：ADR-300 Amendment S、ADR-423 Amendment O、ADR-390 Amendment B、SPEC-215 Rev.20（Rev.19 = 回 400；Rev.20 = pre-flight 時限）
>
> **其他文件**：
> - 研究：`docs/research/RESEARCH-llm-translation-axis-cross-gateway-2026-10-07.md`、`docs/research/RESEARCH-web-search-native-passthrough-2026-10-10.md`、`docs/research/RESEARCH-cjk-proxy-accuracy-claude-gemini-2026-10.md`（#6377）
> - 10-12 的審查與實測報告（repo 外）：`/Users/peter/Desktop/testing/results/e2e_20261012/REPORT.md`
> - 10-14 的真 CLI 實測報告（repo 外）：`/Users/peter/Desktop/testing/results/rdy_20261014/REPORT.md`；readiness 稽核與兩批修正的摘要：`/Users/peter/Desktop/X-parse/docs/llm_readiness_audit.md` §11–§13
> - 草案（歷史，Rev.4）：`/Users/peter/Desktop/X-parse/docs/草案/llm_proxy_統一.md`

---

## 0. 白話說明

客戶拿同一把 Xparse 的 key，可能用 Claude Code、Codex 或 OpenCode，背後的模型可能是 OpenAI、Claude、DeepSeek，或客戶機房裡的模型。我們要的是：**不管用哪個工具、選哪個模型都能直接用，公司的管控規則也照樣生效。**

改之前有兩個問題：

- **孤島**：Codex 只能用 OpenAI 的模型；另一類只講 Responses API 的模型，也只有 Codex 用得到。
- **打折**：Claude Code 經過我們用 Claude 時，gateway 會把請求拆開再重組，結果對話歷史吃不到 prompt cache，成本比直連高。Phase 0 量測還發現更糟的事：Anthropic 把 Claude Code 的整段 system prompt 丟掉了（§2.1 的 #6195）。

這次的改法是在 gateway 裡放一層「翻譯」，原則有三條：

- 每種工具的協定、每家模型的協定，各配一個雙向翻譯器（codec）。
- 同一家族就不翻譯，原文直送。
- 翻不過去的東西不會默默消失：要嘛模擬，要嘛明講不支援，要嘛拿掉並留下紀錄。

治理（ADR-494 那一軸：policy、rail、admission、budget）的流程不動，翻譯只發生在治理之後、送出之前。10-12～13 依 owner「使用者功能優先，稽核、計價、guardrail 之後補」的決定，留下兩個已記載的治理缺口：Codex 的 namespace 工具（MCP、sub-agent、code mode）不受 Tool 規則的名稱規則管轄；`/v1/messages` 的 PDF 沒有任何 rail 讀（§3.2）。

10-11～12 多了一塊：Claude Code 的網頁搜尋、Codex 的 `web_search` 這類「由模型廠商代跑」的工具（hosted 工具），現在在同家族的原生路徑上直接轉給廠商跑，搜尋次數記帳（例外見 §3.2「計量的限制」，§2.1.6）。

10-12～13 再補一輪：10-12 的程式審查與兩輪真 agent 實測找出的問題裡，會讓 agent 直接不能用的幾類已修正並合併。新的 OpenAI 家族（gpt-6、o4）不再被當成舊模型；Codex 的 MCP、sub-agent、tool search、code mode 工具到得了模型；Claude Code 讀得到 PDF；長思考不再被 60 秒逾時砍掉；同一個 session 換模型家族後歷史送得出去；一則很長的訊息不再讓整個 gateway 停住。這些都只在 `main`（§2.1.7–2.1.10）。

10-13～14 又補兩輪：先依 readiness 稽核合併 19 支（大多是紀錄、gate 和不需要取捨的修正）；再用真的三個 agent 在本機跑一輪（779 個請求，沒有 5xx），把找到的問題修掉 11 支。看得到的變化：用非 Claude 模型時，Claude Code 的字會逐段出現；gateway 不再替 agent 偷偷設輸出上限，Codex 打 Claude 寫長檔案不再卡在 16000 token，撞到上限後的重試大多能接下去；Codex 能用沒設金鑰的地端模型；DeepSeek 遇到強制工具改成關掉 thinking 照答，帶結構化輸出的請求改由其他模型回答，不再依路由時好時壞。這些也都只在 `main`（§2.1.11–2.1.12）。

---

## 1. 這是什麼

### 1.1 三種 agent、三種協定

| agent | 講的協定（入口） | Xparse 的入口 |
|---|---|---|
| Claude Code | Anthropic Messages | `/v1/messages` |
| Codex | OpenAI Responses（0.154 起只剩這個） | `/v1/responses` |
| OpenCode 與大多數 SDK | OpenAI Chat Completions | `/v1/chat/completions` |

模型那一側也有三種協定（出口）：

- `openai_chat`：DeepSeek、vLLM 與其他 chat 系模型；
- `openai_responses`：只講 Responses API 的模型；`openai` 列的模型兩種都講；
- `anthropic_messages`：Claude。

入口 3 種乘以出口 3 種，就是 9 個「格子」。

### 1.2 改之前（2026-10-07，dev 實測）

| 模型 ↓ ／ 入口 → | chat（OpenCode） | messages（Claude Code） | responses（Codex） |
|---|---|---|---|
| gpt-5.4（`openai`） | ✅ | ✅（有損失） | ❌ 400 |
| claude-sonnet-5-5（`anthropic`） | ✅ | ⚠️ 雙重翻譯、cache 掉 | ❌ 400 |
| deepseek-flash（`deepseek`） | ✅ | ✅ | ❌ 400 |
| gpt-4.1-nano（`openai_responses`） | ❌ 422 | ❌ 422 | ✅ |

### 1.3 現在每一格怎麼走

| 入口 ＼ 出口 | openai_chat | openai_responses | anthropic_messages |
|---|---|---|---|
| **chat** | 原生。`api.openai.com` 上輸出上限一律送 `max_completion_tokens`，推理家族不收的 sampling 剝除並記 `D17`；第三方 OpenAI 相容端點（DeepSeek、vLLM）照舊（#6331）；帶 `json_schema` 時 DeepSeek 不進候選（#6512） | 翻譯（P3） | 翻譯（既有的 Anthropic worker）。system 的 text parts、`developer`、assistant 同時有 `tool_calls` 與陣列 content、沒有頂層 `type` 的工具 schema 都帶得過去（#6330）；對話以 assistant 結尾、被 Claude 以不收 prefill 拒絕時，補一則 user 接續回合重送一次（#6516） |
| **messages** | 翻譯（既有的入口翻譯）。文字類 document 與 search_result 以文字帶過去；PDF 只有 OpenAI 自家 API 的 `openai` 列收（`file` part），其他 chat 系模型不進候選（#6359）；符合 append-only 條件時文字逐段送出（#6475） | 翻譯（P3）。PDF 送成 `input_file`（#6359）；符合 append-only 條件時文字逐段送出（#6475） | **原生直送**（P9）；document 與 search_result 原樣轉送（#6359）；`thinking.block_binding` 與它的 beta 成對轉送（#6329）；`X-Xparse-Dropped` 只列原生 body 真的沒帶的欄位（#6498）；遇到例外情況改走翻譯；帶 hosted web 工具時不退翻譯（見下） |
| **responses** | 翻譯（P8，只限無狀態請求）。`custom`、`namespace` 成員、client 執行的 `tool_search` 降成 function，回程還原成 client 宣告的樣子（#6360）；帶 `json_schema` 時 DeepSeek 不進候選（#6512） | 原生；`openai` 列也走原生（P3）；hosted `web_search` 在模型可用時原樣轉送（#6313）；`namespace` 與 client `tool_search` 原樣轉送，模型不收時那次嘗試剝除並記錄（#6360）；翻譯回合留在歷史裡的 reasoning item 送出前移除（#6338） | 翻譯（P8，只限無狀態請求；thinking 經信封往返）。工具形狀同左（#6360）；回送的 thinking 前綴對不上時，由 Anthropic 丟掉該 block，或由 worker 剝除後重送一次（#6361）；對話以 assistant 結尾、被 Claude 以不收 prefill 拒絕時，補一則 user 接續回合重送一次（#6516） |

messages 打 Claude 改走翻譯的例外情況（`native_fallback_reason`，10-13 依 `origin/main` 的程式列全）：

- `text_masked`：input rail 的遮罩改了文字（沒帶 hosted 工具時）；
- `kill_switch`：`XPARSE_TRANSLATION_FORCE_OFF` 開著；
- `envelope_unconfigured`：歷史帶 thinking，但沒有載入任何信封金鑰；
- `other:item:system`：這次嘗試的 Claude 不收對話中途的 system 訊息；
- `other:context_management`：`context_management` 帶 `clear_*` 以外的 edit，或形狀不對。只有 `clear_*` 的照走原生（10-12 版寫成「帶 `context_management` 就退翻譯」，不精確）；
- `other:tool:<型別>`、`other:<欄位名>`、`other:messages`：表上不是 FORWARD 的工具、標 REJECT 的頂層欄位（`container`、`mcp_servers`）、`thinking`／`output_config` 不是物件、`messages` 不是清單。入口通常已先擋掉，這裡是第二道防線；
- `other:document`：視圖帶不了的 document 來源（#6359；入口已先回 400，同屬第二道防線）；
- `other:verification`、`other:build_error`：送出前讀回比對失敗（有遮罩時記 `text_masked`）、組 body 失敗；
- `other:<種類>`：治理改了套不回原 body 的東西，認不出種類時是 `other:unknown`。

**帶 hosted web 工具的 messages 請求**（#6315）：

- 不能走原生時一律不退回翻譯，回 400 `hosted_tool_unsupported`（原因帶 `other:hosted_tool:<reason>`）。
- 例外：只被 rail 遮罩、而遮罩能以 token 取代的方式精確套回原生 body、讀回比對一致時，照走原生，記 `native_rewritten`。沒帶 hosted 工具的遮罩請求照舊走翻譯。遮罩套回時，文字類 document 與 search_result 的文字也一併替換，PDF 的資料不動（#6359）。

**Responses 原生出口唯一不照送的歷史**（#6338）：翻譯回合留在對話裡的 reasoning item。本 gateway 的信封記 `item.reasoning:drop:foreign_origin`；沒有 `encrypted_content`、id 是 gateway 自己發的（`rs_xp_` 開頭，舊形狀也認）記 `item.reasoning:drop:summary_only`。以前這種 item 原樣送給 OpenAI，DeepSeek 回合之後換到 OpenAI 模型每一輪都 404。

### 1.4 設計要點（ADR-503）

- **中介格式與 codec**：
  - 翻譯經過一個中介格式 `xparse.items.v1`；每種協定一個 codec 模組，放在 `apps/gateway/bustream/translation/`。
  - 這裡只放純函式：不碰 I/O、不讀環境變數、不寫稽核。金鑰來源刻意放在 `gateway/envelope_key_source.py`，不在 `translation/`。
- **單一能力表**（`translation/capabilities.py::serves()`）：
  - 「這個模型能不能在這個入口用、是原生還是翻譯」只在這裡回答。核心路徑裡不准出現 provider 名稱或 agent 名稱的特判，由 gate G1 擋。
  - 模型層級的判斷也在這份表：hosted 工具（`accepts_hosted_web_tool`、`accepts_hosted_web_search`）、Codex 的工具形狀（`accepts_custom_tools`、`accepts_namespace_tools`、`accepts_tool_search`）、檔案（`accepts_file_input`、`accepts_file_url_input`）。
  - 不在這份表的：OpenAI 家族的請求形狀（輸出上限欄位、sampling 鎖）在 `backend/openai_model_family.py`（#6331，INV-256-16）；Claude 的現行家族改成版本規則（#6452，SPEC-256 Rev.17，INV-256-17）：`backend/param_capabilities.CURRENT_CLAUDE_SURFACE_RE` 認 `claude-<家族>-<major>[-<minor>]`，major ≥ 5 或 opus ≥ 4.7，新家族不必改程式。解析不出版本的名稱（別名、舊命名、日期尾碼、`claude-sonnet-45` 這類拼法）維持舊款形狀。`CLAUDE_SYSTEM_MESSAGE_FAMILIES` 與 `translation/thinking_binding.py` 仍是清單。
- **原生優先**（這裡的「原生」指本面候選，不是 wire 相同）：
  - 本面候選＝翻譯軸之前就在這個入口上的模型。chat 打 Claude、messages 打 OpenAI／DeepSeek 都算；`openai` 列在 `/v1/responses` 上 wire 相同，卻是延伸候選。
  - app 有本面候選時，自動路由只在本面候選裡選。延伸候選只在三種情況使用：client 指名該模型、app 沒有本面候選、R3 備援（依 tenant 的 `resilience.cross_surface_fallback`，預設開）。
  - 既有 app 的自動路由因此不變。也因此 Claude Code 用自動路由時不會偏好 Claude：10-12 實測 KEY2 的 app 三個入口的候選都是同樣 5 顆。
  - `/v1/messages` 請求帶 hosted web 工具或 PDF 時，不能服務的模型先被排除，本面候選也一樣；`/v1/responses` 的 hosted `web_search` 不縮候選，不能跑的那次嘗試看得見地剝除。
- **處置表**：
  - 每個欄位、item、part、工具都有明確處置，五選一，沒有預設值：FORWARD／TRANSLATE／EMULATE／STRIP_RECORD／REJECT。
  - 表與 SPEC 逐列相同，由 gate G2 擋。#6313、#6315 的 hosted 工具列、#6360 的 Codex 工具列、#6359 的 document 列都在 G2 的比對範圍內（§2.4）。
- **不透明狀態用信封**：
  - Anthropic 的 thinking 簽章封成 `xpenv1.…` 信封（AES-256-GCM）交給 client；client 回送時，gateway 打開、核對文字的 sha256，再還原成原始簽章送回 Anthropic。
  - 信封綁 tenant、application、credential、provider，不綁 model，所以 R3 或升級換模型時仍能還原。細節：AAD 只有 `tenant_uuid|application_uuid`；credential 與 provider 放在加密內容的 `origin` 裡，開啟時核對。
  - 外家族的簽章一律剝除並記錄，不會 400。
  - hosted 工具回傳的 `encrypted_content` **不**封信封，原樣轉送（#6315）。
  - 現行的 Claude 5.5 家族把 thinking 簽章綁在它簽章時的前綴（`system`、`tools`、之前的 messages）上，前綴一變 Anthropic 就回 400。翻譯路徑（`/v1/responses` 打 Claude）回送 thinking 時有三層（#6361，SPEC-312 C-312-30a～30g）：Responses→Anthropic 只把開頭的 `developer`／`system` 當 system，之後的留在原位當 user 文字；`thinking.block_binding`（`drop_block`）與它的 beta 成對送給 `api.anthropic.com`，由 provider 自己丟掉對不上的 block；仍被拒時 worker 剝除 thinking 重送一次，被救回的 400 不算失敗、不記健康、不觸發 R1／R3。
  - 翻譯回合自己發的 reasoning id 以 `rs_xp_` 開頭；原生 Responses 出口送出前移除這種 item 與本 gateway 的信封（#6338）。
- **有狀態請求**：
  - `previous_response_id`、`store: true` 只會送給能保存狀態的模型（OpenAI）。
  - 沒有這種模型時回 400 `stateful_responses_unsupported`。用 400 而不是 422，是因為 Codex 遇到 422 會重試。owner 10-10 決定維持這個 400（§3.6 末）。
- **messages 打 Claude 原生直送**（P9）：
  - 比對同一個請求「治理前」與「治理後」的 chat 視圖。
  - 只有能套回原 body 的改寫，才走原生：模型名、`max_tokens`、移除的工具、跟著改的 `tool_choice`。其他差異一律走翻譯，並記原因。
  - 原生 body 的 sampling 與 reasoning 直接套 seam 對這次嘗試的決定，和翻譯路徑送的值相同。
  - 只送治理看過的內容。
  - 送出前把 body 讀回來再比一次。
  - document 與 search_result 原樣轉送，頂層與 `tool_result` 內都一樣，`cache_control` 保留（#6359；之前被剝除，Claude Code 讀 PDF 一律失效）。
  - `thinking` 依型別只轉送 Anthropic 收的鍵；`block_binding` 與 `thinking-binding-controls-*` beta 成對決定，兩個都送或都不送（#6329；之前 beta 被剝、鍵照送，OpenCode 用 `@ai-sdk/anthropic` 每個請求都 400）。
- **hosted 工具**（ADR-490 Amendment B，Rev.15；owner 10-11 決定）：
  - 預設開啟，不需要租戶 opt-in；不加網域白名單，也不注入平台的 `max_uses`／網域上限（client 送什麼就轉什麼）。
  - 只走同家族原生出口：Anthropic 原生 `/v1/messages`、OpenAI／Azure 原生 Responses。跨家族映射不做。
  - messages：先縮候選，只讓能跑的模型進路由與 R3，沒有就 400。responses：不縮路由，不能跑的那次嘗試看得見地剝除（R-strip）。
  - 搜尋次數記帳（例外見 §3.2「計量的限制」），只記錄、永不擋請求；沒定價也照常服務（#6316）。
- **Codex 的工具形狀**（#6360，ADR-490 Rev.16 Amendment C，owner 10-12 決定）：
  - 原生 Responses 出口照 client 宣告的送：`function`、`custom`、`namespace`、client 執行的 `tool_search`；模型不收時那次嘗試看得見地剝除。
  - 翻譯出口只有具名 function：namespace 成員攤平成 `<namespace>__<tool>`、`custom` 變成單一字串參數的 function、tool search 變成名為 `tool_search` 的 function；回程依這個請求的宣告表還原（`translation/tool_shapes.py`）。
  - Tool 規則的名稱規則還不涵蓋 namespace 成員（§3.2）。
- **`/v1/messages` 的內容 block**（#6359，SPEC-312 §13）：一個 block 進不進治理視圖、長什麼樣，只問 `translation/messages_view.py`，入口翻譯與原生 body 都讀它。文字類 document／search_result 是 rail 讀得到的文字；PDF 是 chat core 內部的 `file` part，沒有 rail 讀；吃不下檔案的模型擋在候選池外（400 `document_unsupported`），不會剝除後照樣回 200。
- **翻譯軸以外、同一條請求路徑上的規則**（10-12～13 新增，細節在各自的 SPEC）：
  - OpenAI 模型家族只有一個判斷，列的是舊世代，新家族不必改程式（#6331，SPEC-256 Rev.16）。
  - chat 形狀送 Claude／Bedrock 前先正規化（#6330，SPEC-256 C-256-D16）。
  - 串流 idle deadline 量上游有沒有送位元組，不量 worker 有沒有 yield；等待分三段（#6348，ADR-313 Amendment A）。
  - 路由分級在 event loop 上同步執行，所以輸入要有長度上限、比對要線性；只有一個候選時不分級（#6347，SPEC-264 Rev.14）。
  - 工具呼叫的參數審視不擋回合（#6363，SPEC-304 C-304-143a／143b）。
  - 整段 token 計數一個請求只算一次，大請求不在 event loop 上算；計數只問 `tokenizer.count_tokens`（#6374 起，ADR-419 Amendment D～I）。
  - session affinity 的 key 不含 Claude Code 的 billing 行（#6356）；不是 provider 造成的失敗不動模型健康分數（#6362）。
  - 10-13～14 新增：
    - 輸出上限：client 沒送就不補，Claude 送 provider 公布的上限（#6514，SPEC-256 D19）。
    - DeepSeek thinking 模型遇到強制 `tool_choice` 時，那一回合關 thinking（#6503，D18）。
    - `json_schema` 是模型層級的需求，只收 `json_object` 的 DeepSeek 不進候選（#6512，C-312-66；判斷在 `capabilities.accepts_json_schema_output`）。
    - `/v1/messages` 逐段送出只問 `gateway/messages_incremental.py::declare_append_only`（#6475）。
    - 「這個請求是不是 Codex／Claude Code」只寫在 `gateway/client_profiles.py`，G1 的掃描範圍也一起擴大（#6446，ADR-503 Rev.9）。
    - 沒宣告推理等級的模型只送 `low`／`medium`／`high`，Codex 的 `xhigh` 會降成 `high`（#6534，SPEC-256 D9m）。
    - 模型可以宣告 context length，Codex 的 `/v1/models` 讀得到；以前一律報 128000（#6535）。
    - 失敗出口必須在呼叫點寫明要不要記健康分數（#6447）。
- **看得到走哪條路**：
  - 每次嘗試的稽核帶 `translation_path`，值為 `native`、`native_rewritten`、`translated` 或 `bridged`，另帶 `routing_attempt`；沒走原生時記 `native_fallback_reason`；處置清單記在 `native_dispositions`／`translation_output_dispositions`。
  - menu app 的回應另帶 `X-Xparse-Translation`、`X-Xparse-Dropped`、`X-Xparse-Params-Dropped`、`X-Xparse-Tools-Stripped`。opaque app 不送這些 header，稽核照記。
  - `/v1/messages` 請求帶沒有 rail 讀過卻送到模型的 PDF 時，STARTED 與終端事件多帶 `unread_parts=document:<n>`；`X-Xparse-Dropped` 開始列 part 級項目（#6359）。
  - 回送的 thinking 沒被 provider 採用時記在終端事件的 `translation_output_dispositions`（`part:thinking:strip_record:prefix_mismatch`／`prefix_mismatch_retry`／`binding_controls_rejected`），不在 `X-Xparse-Dropped`（#6361）。
  - `/v1/responses` namespace 成員的呼叫，`TOOL_CALL_DETECTED` 與 `tool_call_undeclared` 帶 `tool_namespace`；`tools_offered` 逐成員列 `<namespace>.<tool>`；`X-Xparse-Tools-Stripped` 也列 namespace 裡被拿掉的成員（#6360）。
  - 其他新增的紀錄值：`PARAM_NORMALIZED` 的 `D16`（#6330）與 `D17`（#6331）；`fallback_scope="translated_only"`、`item.reasoning:drop:summary_only`（#6338）；`decision_evidence.cause=single_candidate`、訊號 `windowed`（#6347）；`tool_arguments_invalid_*`、`tool_calls_truncated_*`（#6363）；idle timeout 事件的 `cause`（`upstream_silent`／`no_first_output`／`upstream_active_no_output`，#6348）。
  - 10-12～13 沒有新增回應 header。新 metric 只有 `xparse_gateway_event_loop_lag_seconds`（#6347）；`/health` 的 `tokenizer` 區塊多 `heuristic_estimator_id`（#6380）。
  - 10-13～14 新增（§2.1.11–2.1.12）：
    - `unread_parts` 三個入口都有：`/v1/messages` 是 `document:<n>;image:<n>`，chat 是 `image:<n>`，`/v1/responses` 是沒有 rail 讀的 item type 加上 `image`／`document` part（例 `custom_tool_call:3;image:1`）（#6463、#6511；只是紀錄，不改 verdict）。
    - 原生直送的 `X-Xparse-Dropped` 只列原生 body 真的沒帶的欄位（#6498）。
    - 路由決策的 `decision_evidence` 帶 `surface_pool_kind`（`home`／`extended`／`pinned`）與本面、池外的候選數（#6459）。
    - 每次嘗試記 `exec_max_tokens_source`（#6514）；prefill 被救回時，終端的 `translation_output_dispositions` 記 `assistant_prefill:emulate:prefill_unsupported`（#6516）。
    - 工具呼叫帶 `tool_flat_name`，只是彙總鍵、不是規則比對的名字（#6465）。
    - chat／messages 的 R3 換到 Policy Kernel 不准的模型時，`PROVIDER_FALLBACK` 帶 `alternative_boundary_would_block=true` 並計數，只記錄、不擋（#6461）。
    - chat／messages 的 STARTED 帶 `model_uuid`（#6509）。
    - 用量可見性：Claude 的 thinking token 進 `reasoning_tokens`，另有 `cache_write_zero_rated` 與 hosted 搜尋次數（#6451）。
- **開關**：
  - `XPARSE_TRANSLATION_FORCE_OFF=1`：kill switch，關掉翻譯軸新開的路，回到以前的行為。
  - 信封金鑰（#6302 起，`gateway/envelope_key_source.py`）依序找：
    1. `XPARSE_TRANSLATION_ENVELOPE_SECRET` 有非空值就用它；值為 `off`（不分大小寫）代表刻意關閉。空字串視同未設。
    2. 讀 `/var/lib/xparse/translation_envelope.keyring`。
    3. 檔案不存在、目錄存在且是真的 mount、可寫，而且不在 Kubernetes（沒有 `KUBERNETES_SERVICE_HOST`）時，原子產生一把，kid 為 `a<YYYYMMDDHHMM>`，mode 0600。
    4. 其他情況關閉並印一行 WARNING。變數或金鑰檔格式錯（含 kid 重複）→ gateway 不啟動。
  - 金鑰狀態：`/health` 與 `/v1/health` 多了 `translation_envelope`：on 時 `{state, source, kids, sealing_kid}`（source = env、file 或 generated），off 時 `{state, source, variable, reason}`（source = none 或 disabled），不影響 `status`；另有 gauge `xparse_translation_envelope_configured{source}`。
  - runbook：`docs/runbooks/translation-envelope-secret.md`（#6302 已改寫：單機安裝含 local-dev 不需要手動步驟）。
  - 10-12～13 新增的環境變數（都有預設值；部署 recipe 沒有設任何一個）：

    | 變數 | 預設 | 作用 |
    |---|---|---|
    | `XPARSE_STREAMING_FIRST_OUTPUT_TIMEOUT_SEC`（#6348） | 240 | 串流：第一個輸出之前，上游可以完全靜默多久 |
    | `XPARSE_STREAMING_LIVE_SILENT_MAX_SEC`（#6348） | 240 | 串流：上游有送位元組但沒有產出，最多多久 |
    | `XPARSE_NONSTREAMING_REASONING_TIMEOUT_SEC`（#6348） | 240 | 非串流：推理模型的總時限 |
    | `XPARSE_TOOL_CALL_ARGUMENTS_ENFORCE`（#6363） | 關 | 開：參數不能用的 tool call 恢復回 503 `model_tool_arguments_invalid` |
    | `XPARSE_PROMPT_COUNT_OFF_LOOP`（#6374） | 開 | 關：大請求的 token 計數回到 event loop（「只算一次」照留） |
    | `XPARSE_HEURISTIC_COUNT_LONG_RUNS`（#6380） | 關 | 開：heuristic 把超過 16 字元的非 CJK 詞依片段計數（`cjk_word_v2`）；屬治理數字的變更 |
    | `XPARSE_BUDGET_USAGE_LEDGER_PREFLIGHT_DEADLINE_SECONDS`（#6397） | 2 | pre-flight ledger 寫入（含 retry）的總時限 |
    | `XPARSE_BUDGET_USAGE_LEDGER_PREFLIGHT_FAILURE_MEMORY_SECONDS`（#6397） | 10 | 寫入失敗後記住多久，期間新請求直接拒絕；0 = 關 |

    寫死、不能用環境變數調的：`/v1/messages` 的 ping 間隔 15 秒；路由計分視窗（ask 超過 32,768 字元只讀頭尾各 16,384）；送給 judge 的 ask 上限（前 12,000＋後 4,000 字元）；大請求門檻 32,768 bytes；namespace 成員攤平後的名稱上限 64 字元。既有而相關的：`XPARSE_STREAMING_IDLE_TIMEOUT_SEC`（60）。`XPARSE_REASONING_NULL_MAX_TOKENS`、`XPARSE_DEFAULT_NULL_MAX_TOKENS` 已由 #6514 移除（10-14），設了也沒有作用。

---

## 2. 已經做完的

### 2.1 交付清單（全部 base `main`、squash merge）

| 片 | PR | merge | 內容 |
|---|---|---|---|
| P1 | #6114 | `53811f6c6` | 設計閉環：PRD-350、ADR-503、SPEC-312、RESEARCH，以及 ADR-192／323／455／269／221／239／382、SPEC-308／307、PRD-190 的 amendment |
| P2 | #6123 | `3231a2f4f` | 每次路由嘗試一筆 `EXECUTION_STARTED`，各自帶 provider context 與 `routing_attempt` |
| P3 | #6158 | `71595796e` | 2a：單一能力表 `serves()`、原生優先候選池；chat／messages 能用 Responses-only 模型；`/v1/responses` 能用 `openai` 列；Responses→chat 回程不再把失敗當成功 |
| P4 | #6154 | `79cccf066` | 三個對話面在 pipeline 階段的拒絕（401／404／422／400）都帶 `X-Request-Id`、`X-Trace-Id`（G5） |
| P5 | #6161 | `2038820ab` | menu app 的 messages／responses 回應，`model` 回報實際執行的模型（ADR-221 Amendment B） |
| P6 | #6155 | `eb13385c0` | 被截斷或過濾的答案不再顯示為正常結束（`length`／`content_filter`／`max_tokens`／`refusal`）；有工具呼叫的回合保留 reasoning |
| P7 | #6170 | `660de720b` | 3a：Claude 回給 `/v1/messages` 的 thinking 帶封好的簽章 |
| P8 | #6190 | `a52f4b5eb` | 2b：`/v1/responses` 能用 Claude 與 chat 系模型（只限無狀態請求）；信封承載 Claude 的 thinking；Open Responses 事件合成 |
| P9 | #6218 | `b32114bc5` | 3b：`/v1/messages` 打 Claude 原生直送；處置表 41 列；矩陣補齊 chat 與 messages 兩列 |

**Phase 0**（用真 Claude Code 量快取基準）另外修出四個既有缺陷：

| PR | merge | 修了什麼 |
|---|---|---|
| #6195 | `d57d9ebb4` | **Anthropic 把 Claude Code 的整段 system prompt 丟掉**：gateway 把 billing 行（`x-anthropic-billing-header:`）和其餘 system 併成同一塊，Anthropic 遇到以 billing 行開頭的 block 會整塊丟棄。修正後模型才真的照 Claude Code 的 system prompt 行事 |
| #6197 | `edbde4ace` | `/v1/messages` 的 `usage.input_tokens` 改用 Anthropic 的語意（不含 cache 部分） |
| #6203 | `8ac75651a` | claude-haiku-5 加入現行 Claude 家族清單：以前打它的每個請求都是 400 |
| #6207 | `e07f6759c` | 帶圖片的請求送 Claude 時改成 Anthropic `image` block：以前一律 400 |

#### 2.1.1 §3.3 那 11 張 issue 的修正（2026-10-08 16:12～18:05 合併）

| issue | PR | merge | 修了什麼 |
|---|---|---|---|
| #6200 | #6239 | `8164fa542` | `/v1/messages` 的 4xx 錯誤型別對齊 Anthropic：402 `billing_error`、409 `conflict_error`、504 `timeout_error`、529 `overloaded_error`；沒列到的 4xx 一律 `invalid_request_error`，不再出現 `api_error` |
| #6206 | #6240 | `f9e21537b` | client 沒送的 temperature 不再補 0.7，provider 用自己的預設（SPEC-256 C-256-D13） |
| #6201 | #6242 | `78b9b6496` | Claude 用 `output_config.format` 做結構化輸出，Claude 當 judge 能拿到判決；judge 只引用 caller system prompt 的前 2000 字 |
| #6205、#6199 | #6247 | `97a7f4411` | Bedrock 的圖片送成 Converse `image` block；送不出去的回 400，不再轉成文字。billing 行獨立成一塊，`cachePoint` 放在 client 自己的 system prompt 之後 |
| #6202 | #6249 | `e83316c90` | provider 帳號沒額度（402、"credit balance is too low" 等）→ `provider_account_unavailable`：不在同一端點重試，直接換下一個模型（R3）；稽核記 `effective_error_code` |
| #6202 | #6267 | `f1036b225` | 上一支的後續：只用 provider 自己的錯誤訊息判斷，不會被 client 送來的文字冒充（例如圖片 media type 寫成 `spend limit`） |
| #6204 | #6250 | `7b7834120` | tool result 裡的圖片：Anthropic／Bedrock／Responses 照原位送，只收文字的 chat 出口搬到下一則 user 訊息，並記 `tool_result.image:relocate` |
| #6217 | #6253 | `812e5c3a7` | chat 請求走 Responses wire 時被剝掉的非 function 工具，改成留稽核紀錄並回 `X-Xparse-Tools-Stripped`（可見剝除） |
| #6198 | #6255 | `b5516ec76` | 當時只開放 `custom`，只在原生 Responses 出口；Codex 的 `apply_patch` 能用（模型能力的限制見 §2.1.2 #6283）。10-13 起 #6360 再開放 `namespace` 與 client `tool_search`，`custom` 在翻譯出口也送得到（§2.1.7） |
| #6196 | #6257 | `2a70eb299` | client 帶 `prompt_cache_key` 就視為要快取：Claude 會被加上 system 斷點與頂層自動快取（ADR-382 Amendment C） |
| #6220 | — | — | 沒改程式：IAM migration 撞號已由 silvia 的 #6219 修好（`0369_adr466…`，#6192 改號為 `0370_…`），留言後關閉 |

合併前先把 9 支 PR 合成一條分支跑全套（11218 passed），並派 reviewer 檢查 PR 之間的交互。抓到一個只在合併後才出現的 bug：#6247 的 Bedrock 本地拒絕會照抄 client 的 media type，被 #6249 誤判成「帳號沒額度」。這個 bug 修好後才 merge。

#### 2.1.2 第一輪 agent 實測抓到的問題（2026-10-09）

用 KEY2 的 app 跑真的 Claude Code 2.1.294、Codex 0.154、OpenCode 1.18.34（§2.3），抓到這些 gateway bug：

| 問題 | PR | merge | 修了什麼 |
|---|---|---|---|
| FX-1：#6198 造成的回歸 | #6283 | `ebdd28b70` | `custom` 只送給吃得下的模型。舊家族（gpt-4o*、gpt-4.1*、gpt-4、gpt-3.5*、o1／o3／o4-mini、codex-mini）改成剝除並留紀錄；新家族預設可用。以前路由或 failover 到這些模型時，整個回合會 400 |
| OC9-1／OC9-2：OpenCode × Claude | #6284 | `697ab5474` | chat 的 content part 帶 `cache_control` 不再回 400（OpenCode 讀圖後整個 session 掛掉）。message 或 part 上的 `cache_control` 都視為快取意圖：Claude 打斷點，其他出口剝除並記錄 |
| CC9-1：Claude Code 每個 process 開頭白打兩次 400 | #6282 | `df9331b36` | 原生 `/v1/messages` 放行 `per-turn-control-` beta，連同 system 訊息上的 `output_config.effort`（走同一套 effort 正規化）；其他 message 層級的未知鍵剝除並記錄 |
| CC9-3：bridge 強迫填可選參數 | #6281 | `f4781bc42` | chat→Responses bridge 保留 client 的 `strict`，沒送就是 `false`（以前 Responses 預設 strict，gpt-5.x 會把 `Read` 的 `pages` 填成 `""`） |
| OC9-5：工具回合被記成 `content_empty` | #6280 | `7c2de653e` | 只有工具呼叫、沒有文字的回合不算違規（ADR-321 Amendment B）；以前 agent 流量會把健康的模型擠出候選池 |

#### 2.1.3 第一輪剩下的 P3（2026-10-09 23:22～23:56 合併）

| 問題 | PR | merge | 修了什麼 |
|---|---|---|---|
| FX-2、CC9-2、FX-5 | #6290 | `880d83612` | Claude 無參數工具呼叫回 `"{}"` 而不是 `""`；`/v1/messages` 回報 Claude 自己的 `stop_reason`（`stop_sequence`＋命中字串、`pause_turn`）；非 function 工具在 Anthropic／Bedrock／Gemini wire 上改成剝除並記錄，不再被改造成 function（指 chat core 的 worker；`/v1/responses` 的 `custom` 在翻譯出口後來由 #6360 改成明確降為 function） |
| CX-2／OC9-3、CX-3 | #6288 | `56874e9fc` | `/v1/responses` 打 Claude 時，`function_call_output` 裡的圖片會送到模型（Codex `view_image`、OpenCode 讀圖）；翻譯路徑的用量多帶 `cache_write_tokens` |
| FX-6、FX-4 | #6287 | `6e998e678` | 翻譯／bridge 到 Responses 出口時，`max_tokens` 小於 16 會調到 16 並記錄（C-256-D15）；Claude 結構化輸出被拿掉的 schema 限制改寫進 description |
| FX-7 | #6289 | `5adbe5710` | `/v1/messages`、`count_tokens` 在 pipeline 之前的 400 也帶 `X-Request-Id`／`X-Trace-Id` |

#### 2.1.4 `/v1/messages` 的 typed tool 分類（2026-10-11 18:37，修 #6299）

| PR | merge | 修了什麼 |
|---|---|---|
| #6300 | `e1edb6bd2` | `/v1/messages` 收到帶 `type` 的工具，只要不是 `custom` 一律 400，改用明確分類（`TYPED_TOOL_FAMILIES`、`CLIENT_TOOL_TYPES = (None, "custom")`、`refuse_typed_tool`）。以前不在前綴黑名單裡的 `web_fetch_*`、`advisor_*`、`memory_*` 會被偷偷改成空 schema 的 function。400 訊息點名型別、結尾帶 `(Input tag '<type>' is not accepted)`，依「誰執行」分三種寫法（server 端工具、Anthropic-defined client tool、其他）；認證前就拒絕，記一筆 `REQUEST_REJECTED`。`web-fetch-*` beta 當時也加進拒絕名單（#6315 又拿掉）。文件：ADR-239 §2.1.9、PRD-190 Rev.7 N1b、SPEC-304 Rev.21、SPEC-312 |

#### 2.1.5 信封金鑰自動佈建（2026-10-11 19:06，ADR-503 D6）

| PR | merge | 修了什麼 |
|---|---|---|
| #6302 | `744b4f186` | 信封金鑰不必再手動設定：env → 金鑰檔 → gateway 自動產生（§1.4「開關」）。寫入用 temp file 加 `os.link`，多個 gateway 同時啟動也只產生一把。9 個 compose recipe 的 gateway 都共用 `xparse-routing-db` named volume，pro、enterprise、enterprise-aws、ami 的 blue 與 green 共用同一把。Kubernetes 不自動產生，Helm 用選配的既有 Secret。`/health` 顯示 `translation_envelope`，另有 gauge。installer 全新安裝時寫一把 `k<YYYYMMDD>:` 的 key，reinstall／upgrade 不補。`blue-green-deploy.sh` 加 Phase 0.8 preflight（先擋格式錯誤與重複 kid），CI 加「Deploy Translation-Envelope Key Preflight Gate」。runbook 改寫。CI 依賴 #6295（`86b790c64`，13 個 PRD-302 config leaf wrapper 延期 30 天，SPEC-269 由 #6309 記錄） |

#### 2.1.6 hosted `web_search`／`web_fetch`（2026-10-11～12）

| PR | merge | 修了什麼 |
|---|---|---|
| #6301 | `45b752ebb` | 設計閉環（10-11 18:53）：ADR-490 Amendment B（§13）、PRD-337 Amendment A（§15）、SPEC-304 §23（Rev.22）、SPEC-312 §12（C-312-46..50），加研究包 `RESEARCH-web-search-native-passthrough-2026-10-10.md`。原設計是租戶 opt-in，經兩輪對抗式審查（governance／security／cost），確認的意見都已修正；**同一天被 #6311 取代**（ADR-490 §13.1–13.14 標〔Rev.15 取代〕） |
| #6311 | `97c3fd228` | owner 決策「預設開啟」（10-11 23:35）：ADR-490 Rev.15 §13.0、SPEC-304 Rev.24、PRD-337 Rev.9。撤回租戶 opt-in（`tool_types` 延後）、網域白名單、平台夾制、hosted 專屬的資料邊界／再出網／live_access 閘門。messages 沒有能跑的模型 → 400 `hosted_tool_unsupported`；responses 是軟需求＋可見剝除；計量只記錄不擋，沒價格顯示為「未定價」 |
| #6316 | `b3135c828` | 逐次計量（10-11 23:37，ADR-489 Am.A、SPEC-302 Rev.12）。gateway：`Usage.hosted_tool_calls`（`streaming/usage.py`；解析在 `streaming/hosted_tool_usage.py`），ledger 新 axis `web_search_requests`／`web_fetch_requests`，新四欄 `hosted_tool_provider`／`hosted_tool_type`／`hosted_tool_model_class`／`meter_source`。IAM：**migration `0378_adr489_hosted_tool_usage_meter`**（只擴不縮）、`HostedToolPriceVersion`（鍵 `(provider, tool_type, model_class?)`），查詢時計價。種子價：Anthropic search $10／1k、fetch $0；OpenAI search $10／1k；`web_search_preview` 非推理模型 $25／1k、推理模型 $10／1k；Azure 未定價。Budget、admission、告警、aggregate 都算進 hosted 費用（aggregate 新增 `web_search_requests`、`web_fetch_requests`、`hosted_tool_calls_estimated`、`cost_hosted_tools_usd`）。OpenAPI 改了，7 個 consumer pin 重釘。**上線順序 IAM 先、gateway 後**；#6313、#6315 不可在缺這支的 gateway image 上線 |
| #6313 | `238eb086b` | `/v1/responses` 原生 OpenAI／Azure 出口原樣轉送 `web_search`、`web_search_2025_08_26`、`web_search_preview`、`web_search_preview_2025_03_11`（10-12 07:48）。模型判斷 `accepts_hosted_web_search`：排除 effort `minimal`，也排除 OpenAI 模型頁沒列 web_search 的舊家族（`o1*`、`o3-mini`、`gpt-4.1-nano`、`gpt-3.5*`、`gpt-4`／`gpt-4-*`、`codex-mini*`）。不能服務的嘗試（含翻譯出口、ADR-455 chat bridge）逐次看得見地剝除（`platform_tool_stripped`＋`X-Xparse-Tools-Stripped`），不縮路由、不回 400；`tool_choice` 指名 web_search 時每次嘗試重新綁定（改 `auto` 或刪掉）。回應的 `web_search_call`、`url_citation` 原樣給 client，`web_search_call` 不當成 client 端工具呼叫。處置表新增 `item:web_search_call`、`tool:web_search*` |
| #6315 | `bc0107d31` | `/v1/messages` 放行 web_search／web_fetch，只限表上 7 個版本、只走直連 Anthropic 的原生出口（10-12 08:01）。`HOSTED_WEB_TOOL_FAMILIES`、`NEED_HOSTED_WEB_TOOL`、`accepts_hosted_web_tool`：路由與 R3 只看得到能跑的模型。沒有能跑的候選、或 client 指名不能跑的模型 → 400 `hosted_tool_unsupported`；原生走不了（kill switch、遮罩放不回、NotNative、verification、build error）一律 400，不退翻譯（遮罩例外見 §1.3）。新 `translation/hosted_blocks.py`：server block（含 `encrypted_content`）、citations、`pause_turn`、`usage.server_tool_use` 原樣回 client，`encrypted_content` 不封信封；歷史不論由哪個 credential 產生都轉送。帶 hosted 工具的請求不走語意快取。output rail 改寫過文字時拿掉 citations，記 `text_rewritten`。`web-fetch` beta 從拒絕名單拿掉 |

同期另有 #6314／#6319（Xparse tools 在 chat／messages 請求內執行，SPEC-314、#6228），之後又有 #6371（`692d0d455`，10-12 18:50：每一輪 Xparse tool 都過 input rail）、#6394（`e3797e0a1`，10-13 01:15：production image 補裝 `jsonschema`）、#6345（`f0ab64ad9`，10-12 15:45：`TOOL_CALL_RESOLVED` 帶 group 與 proxy 範圍）。它們動到 chat／messages 的請求路徑，但屬另一條軸，不是翻譯軸。#6228 仍開著。

#### 2.1.7 10-12 審查與兩輪實測的修正（2026-10-12 13:00～10-13 07:20 合併）

來源是 10-12 的程式審查與兩輪真 agent 實測（§2.3）。「報告」欄是 `e2e_20261012/REPORT.md` 的節號。每支「沒涵蓋」的部分在 §3.2。

| PR | merge | 合併 | 報告 | 修了什麼 |
|---|---|---|---|---|
| #6330 | `d13e3d547` | 10-12 13:00 | §1.7 | **chat 入口打 Claude 的訊息形狀**（Anthropic 與 Bedrock worker 同一套）：`system` 寫成 text parts 不再整段不見；`role: developer` 讀成 system，不再 400；assistant 同時帶 `tool_calls` 與陣列 content 時文字保留；function `parameters` 沒有頂層 `type` 時補 `type: "object"`。原本靜默丟掉的（system 裡的圖片）改成 400 並點名。新檔 `translation/chat_message_shape.py`。文件：SPEC-256 Rev.15（§1.8 C-256-D16） |
| #6329 | `6683b9e34` | 10-12 13:11 | §1.4、§1.5 | **`/v1/messages` 生成期間照發 `ping`**：改成依「距離上次對 client 送出資料」計時，每 15 秒一個（以前上游持續吐字時線上零位元組）。**`thinking.block_binding` 跟著 beta 走**：兩個都送或都不送（以前 beta 被剝、鍵照送，OpenCode 用 `@ai-sdk/anthropic` 每個請求 400）。文件：ADR-239 §2.1.10、SPEC-312 §3.2／§10／§11 |
| #6331 | `0d732f166` | 10-12 14:04 | §1.1 | **OpenAI 模型家族只有一個判斷**（`backend/openai_model_family.py`，列的是舊世代，其餘 `o<N>`／`gpt-<N>` 都算推理家族）。gpt-6-luna 不帶 function 工具的請求不再 100% 回 400；`api.openai.com` 一律送 `max_completion_tokens`，第三方端點維持 `max_tokens`；推理家族不收的 sampling 剝除並記 `D17`。IAM 的鏡像（`provider_surface.py`）與 parity gate 同步改寫。文件：SPEC-256 Rev.16（D17、INV-256-16）、ADR-338 Amendment 2026-10-12、ADR-455 Rev.5 |
| #6348 | `11f4277af` | 10-12 16:06 | §1.3 | **串流 idle deadline 量 provider，不量 worker**：Claude 長思考、推理模型第一個 token 前、單一長 tool call 不再在 60 秒被砍。等待分三段（輸出前靜默 240 秒、輸出後靜默 60 秒、有位元組沒輸出 240 秒）；gateway 自己判定的逾時只有 provider 從未回應時才記 model health；推理模型的非串流總時限 240 秒。新增 3 個環境變數（§1.4）。文件：ADR-313 Amendment A（INV-313-7／8）、ADR-334、SPEC-311 C-311-42a |
| #6338 | `15be934eb` | 10-12 21:54 | §1.6、§10.2 | **`/v1/responses` 歷史跨模型家族**：session 有過 DeepSeek 回合後換到 OpenAI 模型不再每輪 404（翻譯回合的 reasoning item 送原生出口前移除，id 改成 `rs_xp_…`）。帶 OpenAI 加密 reasoning、主模型是翻譯模型且失敗時，R3 不再把 OpenAI 模型排除。文件：SPEC-312 C-312-29c、SPEC-307 Rev.7（RF-8）、ADR-503 Rev.6 |
| #6347 | `f7b6b9212` | 10-12 21:54 | §1.8 | **routing 分級不再卡住 event loop**：一則 80 KB 的訊息不再讓整個 gateway 停 4～9 秒。計分只讀視窗（頭尾各 16,384 字元）、比對改成線性、只有一個候選時不分級不讀內容（`cause=single_candidate`）、送 judge 的 ask 有上限。新 histogram `xparse_gateway_event_loop_lag_seconds`。文件：SPEC-264 Rev.14、SPEC-266 Rev.11、ADR-406 Amendment H、ADR-411 Amendment F |
| #6356 | `78a949b0c` | 10-12 21:54 | §10.2 | **Claude Code `/compact` 後保留 session pin**：affinity key 雜湊前略過 system prompt 開頭的 billing header 區塊（新檔 `billing_header.py`）。以前 `/compact` 後下一輪掉回最弱模型（3/3）。文件：SPEC-290 Rev.11、ADR-447 Rev.7 |
| #6362 | `f78d4948c` | 10-13 02:35 | §10.2 | **不是 provider 造成的失敗不再壓低模型健康分數**：請求造成的 `provider_client_error`、`provider_param_rejected`、`context_overflow`，以及 gateway 自己造成的 `internal_error`、`upstream_format_error`，都不動 EWMA，別人送壞請求不再逐出這顆模型上其他 session 的 pin。`/v1/responses` 的健康紀錄改用分類後的錯誤碼。文件：ADR-447 Rev.8（Amendment G）、SPEC-290 Rev.12 |
| #6363 | `37ab3d520` | 10-13 07:19 | §2.1 | **缺參數或被截斷的 tool call 交給 agent，不回 503**（chat 與 messages）：漏了 required 參數的呼叫照送，讓 agent 用 tool error 自我修正；被輸出上限截斷的那一筆不送，回合以 `length`／`max_tokens` 結束。兩種都不記 model health failure。以前 Claude Code 重試 7～11 次後整輪失敗，每次都計費。要硬擋設 `XPARSE_TOOL_CALL_ARGUMENTS_ENFORCE=1`。文件：SPEC-304 Rev.25（C-304-143、143a、143b） |
| #6359 | `f41f326a9` | 10-13 07:19 | §1.10 | **`/v1/messages` 的 document（PDF）送得到模型**：Claude 原生原樣轉送；OpenAI 是 `file` part 或 `input_file`；不能讀檔的模型回 400 `document_unsupported`（以前每個出口都丟掉、回 200）。文字型 document 與 `search_result` 進治理視圖。新檔 `translation/messages_view.py`。owner 10-12 接受 PDF 是 rail 盲點。文件：SPEC-312 §13（C-312-56..59）、ADR-503 Rev.8、SPEC-035 Rev.3 |
| #6361 | `802c78872` | 10-13 07:19 | §1.5、§10.2 | **回送的 Claude thinking 前綴變了不再讓整輪失敗**：Codex 打 Claude 的 session 在自動 compaction、切回 Claude、工具或 instructions 改變後不再每輪 400（三層處理，§1.4）。新檔 `translation/thinking_binding.py`。文件：SPEC-312 §5.5 C-312-30a～30g、ADR-503 Rev.7 |
| #6360 | `718406c7b` | 10-13 07:20 | §1.2、§1.6 | **Codex 的 namespace 工具、tool search、code mode、apply_patch 歷史**（owner 10-12 決定「全部放行，治理之後補」，推翻 ADR-490 Q1 的 namespace 部分）：Codex 預設 catalog 在 gpt-5.6-luna 有工具可用；MCP、sub-agent、client `tool_search` 在原生與翻譯出口都叫得到；換到 Claude／DeepSeek 後 `apply_patch` 歷史保留。新檔 `translation/tool_shapes.py`。文件：ADR-490 Rev.16（§14 Amendment C、Q15）、SPEC-304 Rev.26（§24）、SPEC-312 C-312-52..55 |

合併時另外加了一個不在任何原 PR 裡的修正（併在 #6360 的 squash，commit `03c7c5f1e`）：只有 client tool search 呼叫、沒有文字的 `/v1/responses` 回合不再被記成 `content_empty`。放行 tool search 之後，這種回合會被算進 `hard_constraint_rate`，把健康的模型擠出候選池（ADR-321 Amendment B 的 B-3）。

合併方式：這些 PR 是平行 session 寫的，互相衝突，所以排成 merge train 依序 squash，每個節點合併前跑過 gateway 全套與 static gates。合併時改了幾個撞號：#6360 的 SPEC-304 由 Rev.25 改為 Rev.26；#6359 的契約由 C-312-51..54 改為 C-312-56..59（main 上沒有 C-312-51）。

#### 2.1.8 token 計數（2026-10-13 07:20～12:00 合併；ADR-419 Amendment D～I）

從 #6347 衍生：治理那一側每個請求在 event loop 上對整份對話算 2～4 次 token。

| PR | merge | 合併 | 修了什麼 |
|---|---|---|---|
| #6374 | `3cb764af6` | 10-13 07:20 | **一個請求的 prompt 只算一次；大請求的計數離開 event loop**（body 超過 32,768 bytes 時在計數 thread 上算）。治理的數字逐位元不變。開關 `XPARSE_PROMPT_COUNT_OFF_LOOP`。Amendment D、SPEC-270 §2.9（C-270-29..35） |
| #6375 | `31ab5117e` | 10-13 07:21 | **`count_tokens` 標 heuristic 時回 heuristic 的數**：以前 header 寫 heuristic，body 卻是 `cl100k_base` 的數。只有 client 看得到的這個數變（CJK 內容小約三成）。Amendment E、C-270-36 |
| #6378 | `75e9343fb` | 10-13 07:21 | **tiktoken 拒絕的文字由它標示的 encoder 計數**（special token 字面、約一百萬字元的空白連續段），不再退回 heuristic。這類請求在 tokenizer 就緒的行程上**治理數字會變**（例：minified JSON tool result 1 → 94,008）。Amendment G、C-270-44..46 |
| #6380 | `9e0e47f94` | 10-13 07:21 | **heuristic 把長的非 CJK 詞依片段計數**，放在旗標 `XPARSE_HEURISTIC_COUNT_LONG_RUNS` 之後，**預設關**，合併不動任何數字。何時翻預設待裁（OQ-5）。Amendment H、C-270-47..54 |
| #6382 | `ae9b63515` | 10-13 12:00 | **routing 的 prompt 估算讀 `count_tokens`**：對 #6378 那兩類文字不再退回 heuristic。只有 `routing_objective=cost`、文字含那兩類之一、tokenizer 就緒三個條件同時成立時路由決策會變。呼叫 encoder 的程式只剩 `tokenizer.py`。Amendment I、SPEC-276 Rev.21（OBJ-C4）。**同一個 squash 也帶進 #6376 的原始內容**（Amendment F、SPEC-270 §2.10 C-270-37..43、C-270-55）：`count_tokens` 端點的整段讀取離開 event loop；請求中途才出現的文字由能等的讀者計數；預先計數改由第一個讀者觸發；heuristic 每次讀 8,192 字元 |

#6376 與 #6382：#6382 的分支疊在 #6376 上，而 #6382 先合併，所以 #6376 的原始內容是經 `ae9b63515` 進 main 的。#6376 提出時自稱 Amendment E、契約編 C-270-36..43，合併時改為 Amendment F，「heuristic 的數不變」一條改取 C-270-55。審查後續由 #6376 本身在 10-13 13:48 合併（`ed7790fde`）。

routing 的整段估算由 #6459 移出 event loop（§2.1.11）。

#### 2.1.9 研究：`cjk_proxy` 對 Claude、Gemini 的準確度（2026-10-12 22:46）

| PR | merge | 內容 |
|---|---|---|
| #6377 | `9ee2af224` | `docs/research/RESEARCH-cjk-proxy-accuracy-claude-gemini-2026-10.md` 與 PoC；沒有改 gateway 程式。129 條語料，Claude 13 個模型用 Anthropic `count_tokens`，Gemini 4 個模型用 SDK 內附的本地 tokenizer（測試環境沒有 Gemini 金鑰）。結論：對 Claude，heuristic 只在近乎純中文、日文時比 cl100k 接近；中英混合與韓文是 cl100k 較準。對 Gemini，有 CJK 時 heuristic 都較準。Claude 4.7 起換了 tokenizer，cl100k 對英文低估 33%、程式碼 37%。文件列五個選項，不做選擇 |

#### 2.1.10 Budget（silvia；10-12 報告開的兩張 issue）

| issue | PR | merge | 合併 | 修了什麼 |
|---|---|---|---|---|
| #6354 | #6367 | `727347730` | 10-12 18:00 | **Budget 與 interim quota 用完改回 HTTP 400**（原 429），所有跑 budget gate 的入口都是。`code`／`scope_type`／`basis`／`message` 不變，不帶 `Retry-After`。限流與併發仍是 429。10-12 實測只有 400 能讓三家 agent 在幾秒內停手並顯示訊息。對外契約變更。文件：ADR-300 Amendment S、SPEC-215 Rev.19、ADR-390 Amendment B |
| #6353 | #6397 | `8a987978d` | 10-13 10:15 | **用量帳本的 pre-flight 寫入有 2 秒總時限，失敗後記住 10 秒**：IAM 慢或斷線時 503 `budget_usage_ledger_unavailable` 很快回來，不再等 30～54 秒。拒絕本身不變（仍是 fail-closed）；issue 要求的「依租戶 fail mode 預設放行」沒有做。文件：ADR-423 Amendment O、SPEC-215 Rev.20 |

同期相鄰、沒列進上面的：#6325（`54ce1e9dc`，10-12 09:48，silvia：一個 application 可以有多個 Budget Limit；它也是 10-12 第一輪實測的基準 commit）。

#### 2.1.11 readiness 稽核的修正（#6447 於 10-13 20:07 先合；其餘 18 支 10-14 03:45～03:56 依序合併，到 #6471 `e2923aeef`）

來源是 10-13 的 readiness 稽核（摘要在 `/Users/peter/Desktop/X-parse/docs/llm_readiness_audit.md` §11）。全部沒有 live 驗證；10-14 實測（§2.3）證實沒有造成回歸。

| PR | merge | 合併 | 修了什麼 |
|---|---|---|---|
| #6447 | `e3cf0babc` | 10-13 20:07 | 原生 `/v1/responses` 的 IAM binding 寫入失敗不再記成模型健康失敗；三個失敗出口的每個呼叫都要寫明健康判定，新 `failure-health-attribution-gate`（SPEC-308 §9.13） |
| #6446 | `c3cb98d9b` | 10-14 03:45 | 「是不是 Codex／Claude Code」收進 `gateway/client_profiles.py`；G1 擴大到 `production`、`registry`、`streaming`（不含 workers）與 regex 比對（ADR-503 Rev.9） |
| #6457 | `b3cd033cc` | 10-14 03:46 | route 盤點看得到 WebSocket 與 mounted route；adapter 跑的每個 stage 都要有自己面上的通過測試（SPEC-306 Rev.4） |
| #6452 | `2c59d8c68` | 10-14 03:47 | Claude 現行家族改成版本規則；chat→Responses bridge 帶 `response_format`；DeepSeek 收 `developer`、無型別 schema（SPEC-256 Rev.17） |
| #6453 | `11b0a10fe` | 10-14 03:47 | 未知模型的拒絕訊息指路（application code、`"default"`、`GET /v1/models`）；`/v1/responses` 帶不過去的三種需求有專屬拒絕碼；`GET /v1/models` 收 `x-api-key`；新 runbook `docs/runbooks/agent-cli-setup.md`（SPEC-312 C-312-60） |
| #6460 | `ab720c56f` | 10-14 03:47 | bridge 在輸出上限截斷時，交付 provider 已經收完的工具呼叫（SPEC-312 C-312-15a） |
| #6467 | `7a60edda1` | 10-14 03:48 | user 訊息裡的 base64 圖片（含搬移過的 tool result 圖片）送到 Gemini（SPEC-175 REQ-4a） |
| #6459 | `efb893b0a` | 10-14 03:48 | routing 不再掃內文找沒人讀的訊號，估算移出 event loop；記錄候選池種類；選到 breaker 開著的模型只計數（ADR-285 Amendment A、SPEC-276、SPEC-312 C-312-61） |
| #6451 | `89728d487` | 10-14 03:52 | 用量可見性：Claude 的 thinking token、cache write 以 0 計、未定價與帳本寫入失敗的次數、hosted 工具次數（SPEC-302 Rev.15 §6.8） |
| #6465 | `6bdd8c7f9` | 10-14 03:52 | 工具呼叫帶 `tool_flat_name`；原生 `/v1/responses` 在終端事件記參數有問題的呼叫（SPEC-304 Rev.27 C-304-408） |
| #6463 | `0f195a846` | 10-14 03:53 | `/v1/responses` 的 item 與 `/v1/messages` 的圖片，沒被 rail 讀過的記進 `unread_parts`，item 歸類由一張表決定（SPEC-312 C-312-58、62、63） |
| #6461 | `23a5d7435` | 10-14 03:53 | chat／messages 的 R3 換到 Policy Kernel 不准的模型時記錄並計數，換手照舊（SPEC-032 §10.1.4） |
| #6468 | `796ad0432` | 10-14 03:53 | json transcript 依 provider 回報的音訊秒數記帳（SPEC-308 SR-28a） |
| #6475 | `768a20a2c` | 10-14 03:54 | `/v1/messages` 對非 Claude 模型逐段送出文字；串流的 `output_tokens` 用 provider 的數（ADR-239 Amendment C、SPEC-312 C-312-64／65） |
| #6474 | `4580e13f1` | 10-14 03:54 | 回應端登記表 `gateway/response_checks.py`：每條路徑 × 每個檢查都要宣告，新 `response-checks-gate`（ADR-494 Amendment B） |
| #6476 | `a0c1e4e20` | 10-14 03:55 | provider × 請求項目的「不得靜默丟」矩陣，現有 23 筆缺口放進只減不增的 baseline（SPEC-256 Rev.18） |
| #6448 | `6997e3c7e` | 10-14 03:55 | 新 `provider-roster-parity-gate`：gateway 與 IAM 的 provider 名單、Responses-only 名單、預設 host 一致（ADR-208 INV-208-2／3） |
| #6469 | `45de41322` | 10-14 03:56 | 用量帳本的 axis 跨 owner 比對；沒有 booker 的用量單位在 import 時就失敗（SPEC-302 §6.1a、SPEC-308 SR-32） |
| #6471 | `e2923aeef` | 10-14 03:56 | IAM：價格快照保留 Responses-only 模型；價格盤點列出 cache write 以 0 計的價格段（SPEC-265 Rev.3、SPEC-302 C-302-28a） |

#### 2.1.12 10-14 實測後的修正（10-14 18:14～18:26 合併，到 #6515 `ee1a40564`）

來源是 10-14 在 `bff643332` 用三個真 CLI 跑的那一輪（§2.3；摘要在 `llm_readiness_audit.md` §13）。合併方式是 merge train；#6515 那一節的 CI 涵蓋全部 11 支並且全綠，本機 gateway 全套 16,142 passed。

| PR | merge | 合併 | 修了什麼 |
|---|---|---|---|
| #6489 | `fa23339d0` | 10-14 18:14 | `/v1/responses` 上沒綁憑證的地端模型由 500 變 200，跟 chat 一樣（ADR-029 §13、SPEC-282 Rev.34） |
| #6498 | `665a2f667` | 10-14 18:19 | 原生 `X-Xparse-Dropped` 依原生 body 重算；`/v1/messages`、`count_tokens`、`/v1/models` 沒帶 key 的 401 訊息兩種 header 都提；runbook 依實測更正 |
| #6509 | `8027a8d2e` | 10-14 18:22 | 稽核歸屬：STARTED 帶模型；client 中途離開記 `client_closed`，不是 `provider_dropped`；Responses 計 reasoning；classifier degraded 也記用量 |
| #6511 | `460fae3a8` | 10-14 18:23 | chat 與 `/v1/responses` 沒被 rail 讀的圖片、檔案 part 也進 `unread_parts`，每個入口各算一次（SPEC-312 C-312-58a、62） |
| #6513 | `7d5fc3a7e` | 10-14 18:23 | 只改文件：OpenAI 從 GPT-5.6 起收 cache write，兩個入口都有回報（SPEC-302 Rev.19） |
| #6503 | `de603a416` | 10-14 18:23 | 強制 `tool_choice` 打 DeepSeek thinking 模型時，那一回合關 thinking（SPEC-256 Rev.19 D18） |
| #6512 | `c82cffdaf` | 10-14 18:24 | 帶 `json_schema` 的請求不路由到 DeepSeek，指名 DeepSeek 時送出前回 400（SPEC-312 C-312-66、ADR-503 Rev.10） |
| #6514 | `010323c1e` | 10-14 18:24 | **owner 決定**：gateway 不再替 client 補輸出上限；Claude 用 Anthropic Models API 公布的上限；稽核記 `exec_max_tokens_source`（ADR-338 Amendment 2026-10-14、SPEC-256 Rev.20） |
| #6516 | `b56757e3a` | 10-14 18:25 | 翻譯請求被 Claude 以 prefill 拒絕時，補一則 user 接續回合重送一次；每種可救的 400 最多救一次（SPEC-312 C-312-67、ADR-503 Rev.11） |
| #6526 | `cb9471b45` | 10-14 18:25 | provider 沒收完的工具呼叫由 worker 標記：chat 與 messages 不交付，`/v1/responses` 記成 truncated，bridge 記下丟掉的那一筆（SPEC-304 Rev.28） |
| #6515 | `ee1a40564` | 10-14 18:26 | IAM：proxy 的 active consumer 數與 code 清單排除已終止的 application（SPEC-171 RESPONSE-05） |

同期別人的合併、跟這條線相關的：#6534（推理等級 D9m）、#6535（per-model context length，IAM migration `0387`）。

### 2.2 使用者看得到的行為變更

- **Codex 能用 Claude、DeepSeek、vLLM**：只限無狀態請求。有狀態請求在沒有 OpenAI 模型可用時回 400 `stateful_responses_unsupported`，以前是 422／400。
- **OpenCode／Claude Code 能用 Responses-only 模型**：以前是 422。
- **`/v1/responses` 能用 `openai` 列的模型**：以前是 400。
- **Claude Code 打 Claude 送出原樣的 body**：system block、斷點、對話中途 system 訊息、圖片、document（PDF，#6359）都在 client 放的位置；快取命中接近直連（§2.3）。
- **R3 多了換手對象**：混合池 app 的 chat 模型失敗時，可以換到 Responses 模型；Responses 模型失敗時，可以換到 `openai` 列。tenant 關掉 `cross_surface_fallback` 就回到以前。
- **回應更誠實**：
  - 截斷、過濾、拒答都照實回報；
  - menu app 的 messages 與 responses 回應，`model` 改為實際執行的模型；
  - pipeline 拒絕帶兩個關聯 header。
- **稽核**：
  - 新欄位：`translation_path`、`routing_attempt`、`native_fallback_reason`、`native_dispositions`、`translation_output_dispositions`。
  - R3 的每次嘗試各有一筆 STARTED 與 `PARAM_NORMALIZED`。
- **後續修正帶來的變更（§2.1.1–2.1.3）**：
  - Codex 用 GPT-5 時拿得到 `apply_patch`（custom）；被路由到舊家族的原生模型時，這個工具會被剝除並留紀錄，回合照樣完成。10-13 起（#6360）Claude、DeepSeek 等翻譯出口也拿得到。
  - Claude 在 chat 面與 Codex 翻譯路徑上都吃得到 prompt cache：OpenCode（chat 線路，預設設定）從第 2 個請求起命中；Codex 與 OpenCode 的 Responses 線路每輪約 95%。
  - provider 帳號沒額度時，沒指定模型的請求會自動換下一個模型；指定了模型就照實回 400。
  - 工具結果裡的圖片在所有入口都送得到模型。
  - client 沒送 temperature 時不再補 0.7。被 `temperature:drop:D12` 稽核嚇到的情況也跟著消失。
  - Claude 當 judge 能用。
  - `/v1/messages` 的錯誤型別與 `stop_reason` 都對齊 Anthropic。
- **10-11～12 的變更（§2.1.4–2.1.6）**：
  - `/v1/messages` 帶非 `custom` 的 typed tool（advisor、code_execution、computer、bash、memory 等）→ 400 並點名型別，不再偷偷變成空 function。Claude Code 2.1.280 以後看到這個 400 會拿掉 advisor 自動重試；更舊的版本若設了 advisor，會直接看到 400。
  - **Claude Code 的 WebSearch 能用**：在直連 Anthropic 的 Claude 上原生執行；pool 裡沒有能跑的模型時回 400 `hosted_tool_unsupported`。
  - **Codex 的 `web_search` 能用**：在原生 OpenAI／Azure Responses 上、模型吃得下時原樣轉送；其他情況那次嘗試剝除並回 `X-Xparse-Tools-Stripped`，不回 400。
  - 搜尋次數記帳（例外見 §3.2「計量的限制」），Budget、admission、告警、aggregate 都算進去；永遠不擋請求；Azure 記為未定價。
  - 信封金鑰在既有單機安裝與 EC2 上自動產生（installer 全新安裝會直接寫變數，所以是 `source=env`），`/health` 看得到狀態。
- **10-12～13 的變更（§2.1.7–2.1.10）**：
  - **新的 OpenAI 家族直接能用**（#6331）：gpt-6-luna 不帶工具的請求不再 400（Claude Code 的權限分類器與 WebFetch 摘要、OpenCode 的標題與 compaction 都是這種請求）；`/v1/responses` 帶 `temperature` 不再失敗；之後的新家族不必改程式。稽核會多出 `temperature:drop:D17` 這類紀錄。
  - **chat 入口打 Claude**（#6330）：system 以 text parts 送（OpenRouter、LiteLLM、Roo、Cline 的寫法）不再整段消失；`developer` 與沒有頂層 `type` 的工具 schema 不再 400。
  - **`/v1/messages` 生成期間每 15 秒一個 ping**（#6329）：長回合不再被幾十秒沒資料就斷線的中介層切斷。文字仍在回合結束時一次送到。OpenCode 用 `@ai-sdk/anthropic` 接 Claude 不必再加 workaround。
  - **長思考與長工具參數不再被 60 秒砍掉**（#6348）：第一個輸出前可以等 240 秒；錯誤訊息會指出是哪一段等待用完。
  - **Codex 的 MCP、sub-agent、tool search、code mode 能用**（#6360），在原生 OpenAI 與 Claude／DeepSeek 上都能；Codex 預設 catalog 的 gpt-5.6-luna 不必覆寫就有工具；`apply_patch` 在 Claude／DeepSeek 上可用，換模型後也看得到先前的 patch。Tool 規則的名稱規則管不到這些 namespace 工具。
  - **Codex 的 session 換模型家族後不再壞掉**（#6338、#6361）：DeepSeek 回合後換到 OpenAI 模型不再 404；釘在 Claude 的 session 遇到自動 compaction、切回 Claude、工具或 instructions 改變不再整輪 400。
  - **Claude Code 讀 PDF 能用**（#6359）：Claude 上原生執行；OpenAI 模型也讀得到；DeepSeek 這類模型改回 400 `document_unsupported`，不再回一個沒看到文件的 200。
  - **工具呼叫缺參數或被截斷不再回 503**（#6363）：Claude Code 不再重試多次後報 server 錯誤。
  - **Claude Code `/compact` 之後不再掉回最弱的模型**（#6356）；**別人送壞請求不再逐出自己 session 的 pin**（#6362）。
  - **一則 80 KB 的訊息不再讓整個 gateway 停住**（#6347、#6374）。指名模型的請求稽核裡不再有 `tier`／`score`。
  - **`count_tokens` 的數與它標示的估算器一致**（#6375、#6378）：對 CJK 內容，非 OpenAI 模型池回的數變小約三成。
  - **Budget 用完回 400 而不是 429**（#6367）：Claude Code、Codex、OpenCode 幾秒內停手並顯示訊息；IAM 變慢時 pre-flight 的 503 在 2 秒內回來（#6397）。
  - 稽核新增的欄位與紀錄值見 §1.4「看得到走哪條路」。
- **10-13～14 的變更（§2.1.11–2.1.12）**：
  - Claude Code、OpenCode 指名非 Claude 模型時，`/v1/messages` 的文字逐段出現（#6475）；Claude 仍是回合結束才一次送到。
  - gateway 不再替 client 補輸出上限：Claude 的翻譯路徑從 16000 變成模型公布的上限（haiku-5-5 是 128000），Codex 打 Claude 的長輸出不再卡在 16000（#6514）。
  - Codex 打 Claude 撞到上限後重試，多數情況不再整輪失敗（#6516；半截文字以空白結尾、截在 thinking 或工具呼叫上的仍會失敗）。
  - Codex 能用沒綁憑證的地端模型（原本 500，#6489）。
  - DeepSeek：強制 `tool_choice` 由 400 變成沒有 thinking 的 200（#6503，限標了 `supports_reasoning` 的列）；帶 `json_schema` 的請求改由其他模型回答，指名 DeepSeek 時回 400 `structured_output_unsupported`（#6512）。
  - 未知模型名、`/v1/responses` 帶不過去的需求，拒絕訊息會說要改什麼（#6453）；`GET /v1/models` 收 `x-api-key`。
  - Claude 被切掉的最後一筆工具呼叫，在 chat 與 messages 上不再以 `{}` 交付（#6526）。
- **不變的**：
  - 混合池 app 的自動路由（原生優先）；
  - ADR-494 的 stage 順序；
  - chat SSE 的狀態轉移；
  - 每個請求恰好一個終端事件。

### 2.3 真元件證據

| 情境 | 結果 |
|---|---|
| 真 Claude Code 2.1.293 × claude-haiku-5-5，原生直送，5 輪 | 每輪快取讀取 45／92／93／94／95%，每次呼叫都走 `native`；審查修正後重跑結果相同 |
| 同一份 5 輪腳本，直連 Anthropic | 73／89／91／92／93% |
| 同一份 5 輪腳本，走翻譯路徑（修好 billing 行後） | 38／63／54／47／42% |
| 對話中途的 system 訊息打 claude-haiku-4-5 | P9 修正前，上游 400 `role 'system' is not supported on this model`；修正後 200，走翻譯 |
| 同一個 session 先 DeepSeek 再 Claude | 不 400；DeepSeek 留下的無簽章 thinking 剝除並記錄 |
| 真 Codex 0.154 × claude-sonnet-5-5、× deepseek-flash，兩輪（resume），用 shell 改檔 | 都成功，檔案確實被改了 |
| 真 Codex：第一輪 Claude、第二輪 gpt-5.4（同一個 session） | 成功：Claude 的信封在送 OpenAI 前移除 |
| Claude 的 thinking 經信封往返（P7／P8） | 解開後拿到 Anthropic 的原始簽章；回送後 Claude 接受 |
| Open Responses 合規（clone 在 `/Users/peter/Desktop/research/openresponses`） | streaming-response 項目：Claude、DeepSeek 翻譯與 gpt-5.4 原生都通過；其餘失敗都是非串流、WebSocket、compact，屬設計如此 |
| owner suite（P9） | 本機 11027 passed、0 failed；CI 11231 passed |

**2026-10-09～10 的 agent 實測**（本機 dev stack，KEY2 的 app，報告：`/Users/peter/Desktop/testing/results/e2e_20261009/REPORT.md`，§8、§9 是修正後的重測）：

| 情境 | 結果 |
|---|---|
| 11 張 issue 的修正，直接打 HTTP 驗證 | #6196、#6198、#6200、#6201、#6202、#6204、#6206、#6217 通過；#6205、#6199 的 Bedrock 部分因 pool 沒有 Bedrock 而無法實測 |
| Claude（claude-haiku-5-5）當 judge | 5/5 拿到 `llm_verdict`；長 system prompt 的 judge 只用 1417 tokens，修前約 33k |
| #6202：臨時 probe app 掛真的沒額度的 `claude-api-june` | 沒指定模型的 chat（串流與非串流）、`/v1/messages` 都換到下一個模型並回 200，稽核記 `provider_account_unavailable`；指定那個模型時回 400 並附 Anthropic 原文 |
| 真 Claude Code 2.1.294 × claude-haiku-5-5 | 修 CC9-1 後 33 個請求全部 200；讀圖答對；`--resume` 的快取比例 45／92%，與 10-08 基準相同；`--model gpt-5.5` 經 bridge 不再被迫填可選參數 |
| 真 Codex 0.154 | gpt-5.5 的 `apply_patch` 照送並成功套用；gpt-4o-mini 的 custom 被剝除，回合照樣完成；打 Claude 時 `view_image` 答對顏色，跨 resume 有 cache write／read |
| 真 OpenCode 1.18.34 | chat 線路打 Claude：讀圖答對，從第 2 個請求起命中快取；Responses 線路讀圖答對；工具回合都不再記成 `content_empty` |
| 兩輪修正後的回歸檢查 | 沒有發現新的回歸 |

**2026-10-11 的驗收**（#6300：本機 probe；hosted 工具：用 4 支 PR 合併後的樹建一座 probe gateway，模型 claude-haiku-5-5，key 用 KEY2。紀錄在該 session 的暫存輸出，沒搬進 `testing/`）：

| 情境 | 結果 |
|---|---|
| #6300 抓包（P13） | Claude Code 2.1.295 只送兩種帶日期的型別：`advisor_20260301`、`web_search_20250305` |
| #6300 真 Claude Code，預設設定 2 輪 | 4 個請求全部 200、`native`，沒有 400 |
| #6300 真 Claude Code，開 advisor | 第一個請求 400，Claude Code 自動拿掉 advisor 重送，接著 200 |
| #6300 測試 | gateway owner suite 11632 passed；seeded regression 讓 32 個測試變紅 |
| 真 Claude Code 2.1.295 WebSearch | **PASS**：子請求 `tools=[web_search_20250305 max_uses=8]` 回 200；stream 有 2 個 `server_tool_use`、2 個 `web_search_tool_result`，`web_search_requests=2`；`translation_path=native`，整個 session 沒有 400；ledger 寫 units=2、`provider_usage` |
| 真 Claude Code WebFetch | PASS，但**沒有測到 server 端 web_fetch**：Claude Code 在本機自己抓網頁，子請求 0 個工具；3 個請求 200、`native`；沒寫 `web_fetch_requests` |
| 真 Claude Code 2 輪 Read／Bash 回歸 | PASS：4 個請求 200、`native`，沒有 400 或重試 |
| Sonnet 強制 `tool_choice` 指名 web_search（研究 C-4） | **NOT RUN**：pool 的 sonnet 是 `claude-sonnet-5-5-peter-no-money`，上游 400 `credit balance is too low`。替代：直接打 API、用 haiku 強制指名 web_search，200、`native`、units=1。Sonnet 與 Opus 仍未驗證 |
| 真 Codex 0.154 live 搜尋 | PASS，但要覆寫 catalog：內建 catalog 的 `gpt-5.6-luna` 是 `code_mode_only`，Codex 永遠不送 web_search。用 gpt-5.5 的條目覆寫後送出 `{type:web_search, external_web_access:true}`，`web_search_call` completed、`native`，ledger units=1、`item_count` |
| 真 Codex shell 與 apply_patch 回歸 | PASS：全部 200、`native` |
| 真 Codex 第 2 輪改派到 deepseek-flash | PASS：200、`translated`；web_search 看得見地剝除（`x-xparse-tools-stripped` 含 `web_search`）；歷史的 `item:web_search_call` 丟掉，記 `SPEC312-3.1` |
| #6313 整合測試 | 67 passed |
| Azure web_search | **NOT RUN**：pool 沒有 Azure 模型；Azure 是否回 `usage.tool_usage` 未驗證 |
| live `pause_turn`、`encrypted_content` 跨 credential／模型重送（A-10） | **NOT RUN**：只有測試證明 |
| IAM 0378 跑在真 Postgres 16 | PASS：從零 migrate 429 個、29.9s；v1.77.0.10 舊程式跑在 0378 schema 上不 crash，但會少算 hosted 費用；真 append 計價：Anthropic 2 次搜尋＋1 次 fetch = $0.02、OpenAI 1 次 = $0.01、Azure unpriced（calls=1）；有 hosted fact 時 reverse 大聲失敗並整筆 rollback，沒有時 reverse／forward 都正常。抓到一個 bug：`model_class` 為 NULL 的萬用價格列可重複，已在 #6316 改 partial unique（`8835b1db0`） |
| 信封金鑰兩色驗證 | PASS：兩座 SCR gateway 以 uid 1001 跑在同一個 volume，一座 `source=generated`、一座 `source=file`，kid 同為 `a202610111440`，檔案 mode 600、59 bytes；重建容器 kid 不變。blue 回的簽章 `xpenv1.a202610111440.` 送到 green 被原生接受、沒有 fallback。第三座用不同 volume 重送：200，簽章剝除記 `part:thinking:partial_thinking`。（#6302 的 PR 說明寫「沒在真的兩容器 Docker 驗證」，那是在這次驗收之前寫的） |
| #6302 的 race 與 preflight 測試 | 6 個 process × 25 輪只產生一把；Phase 0.8 preflight 30 個案例 |

**2026-10-12 的程式審查與兩輪實測**（本機 dev stack，KEY2 的 app；報告 `/Users/peter/Desktop/testing/results/e2e_20261012/REPORT.md`）：

- 程式審查：12 個面向，加上與 LiteLLM、one-api、Bifrost、Portkey、vLLM 五家的對照。105 個發現，其中 78 個 P0–P2 各派一個以反駁為目標的驗證者（讀碼＋打本機 gateway）：74 確認、3 反駁、1 無法驗證。
- 實測：7 條線（真 Claude Code 2.1.296、Codex 0.154.0、OpenCode 1.18.34、SDK 矩陣、cost／audit、guardrail、routing）。92 個發現，55 個 P0–P2 全部由第二個 agent 獨立重現並追到根因。
- 兩邊去重後約 45 個獨立問題。

| 情境 | 結果 |
|---|---|
| 第一輪（`54ce1e9dc`）主流程 | 三個 agent 的寫程式迴圈、resume、讀圖、平行工具、跨家族換模型，在 claude-haiku-5-5、gpt-5.6-luna、deepseek-flash、AUTO 上都通過；10-09 修好的項目沒有回歸；SDK 矩陣的單工具往返 32/32、平行工具 32/32 |
| 第一輪：會讓 agent 直接不能用的問題 | 10 類（報告 §1）。9 類已由 §2.1.7 修正（其中「`/v1/messages` 生成期間零位元組」只修了 ping，文字仍在回合結束時才到）；guardrail 設成 enforce 那一類還沒開工（§3.2） |
| 第一輪：帳本 | 93 個完整服務的請求各恰好一筆，模型歸屬正確，沒有重複扣款、沒有漏記；進 pipeline 的 952 個 SDK 請求都恰好一個終端事件。有兩處金額算錯（§3.2） |
| 第一輪：routing | 這個 app 的 LLM judge 一次都沒判過：釘的 judge 模型已不在 pool，gateway 靜默退回池尾，而池尾是沒額度的 sonnet。所以「judge 正常時的 AUTO」留到第二輪 |
| 第二輪（`0d732f166`）驗 #6331 | gpt-6-luna 無工具請求 10/10 回 200；真 Claude Code 指名 gpt-6-luna 的寫程式迴圈 32 個請求全 200、Bash 被擋 0 次（第一輪被擋 32／11 次）；真 OpenCode 的標題與 compaction 不再 400；gpt-6-luna 當 classifier judge 從 35/35 失敗變 35/35 通過 |
| 第二輪驗 #6330 | system parts、developer、assistant 陣列內容＋`tool_calls`、無型別工具 schema 全過；三種寫法讀到同一份 prompt cache |
| 第二輪驗 #6329 | 40 秒以上的回合每 15 秒一個 ping（第一輪同腳本 83.4 秒零位元組）；真 OpenCode 用 `@ai-sdk/anthropic` 不加 workaround 全過 |
| 第二輪：SDK 核心矩陣 323 格 | 26 格改善、0 格退步 |
| 第二輪：judge 正常的 AUTO（judge 改釘 deepseek-flash、沒額度的 sonnet 暫停） | 功能面沒有 P0：Claude Code 8 個 session 188 個請求全 200；OpenCode 11 個 session 220 個請求全 200；Codex 14 個 session 78 輪中 76 輪完成。但變慢、變貴（§3.2「Routing、session 與健康分數」）。跨家族的問題改由 routing 自己觸發，後來由 #6338、#6361、#6360 修掉 |
| 第二輪：兩次未定位的 gateway 凍結 | 是整台 Docker VM 與 macOS host 記憶體不足造成的全系統停頓，不是 gateway 的阻塞呼叫。在健康的 VM 上重放 25～35 個並行的 agent 請求，event loop 最長只卡 0.18 秒 |

**10-12～13 各修正的驗證**：

- 每支 PR 各附整合測試（§4），新增的 28 個測試檔都登記在 `gateway-ci-suite.txt`。合併前每個 merge train 節點跑過 gateway 全套與 static gates；#6376 那個節點的本機全套是 13,915 passed、0 failed（合併當時跑的，紀錄只在 session 裡；PR 說明寫的是較早一版的 13,290 passed）。
- 第二輪只實測到 #6329、#6330、#6331 三支（上表）。其餘各支的真 client 證據出自各自的 PR 說明與 SPEC，這次沒有重跑：#6360 用真 Codex 0.154.0、預設 catalog、gpt-5.6-luna 原生，`exec` 能跑、檔案確實被改；#6359 用真 Claude Code 2.1.296 帶 PDF，快取讀取比例 0.941／0.997，與直連相同。
- **沒做的**（10-13 當時）：合併後的組合沒有用真的 Claude Code／Codex／OpenCode 重跑；Bedrock、Azure、vLLM 出口沒有實測（pool 沒有）；三個 CLI 都只測 headless，沒測互動式 TUI；超過 5 分鐘的長回合沒有實跑。第一項由下面 10-14 的實測補上。

**2026-10-14 的真 CLI 實測**（本機 dev stack，main `bff643332`，含到 readiness 19 支為止的全部修正；KEY2 的 app；報告 `/Users/peter/Desktop/testing/results/rdy_20261014/REPORT.md`）：

| 情境 | 結果 |
|---|---|
| 真 Claude Code 2.1.296、Codex 0.154、OpenCode 1.18.34 | 209／232／338 個請求，共 779 個，0 個 5xx；4xx 只有預期中的（未知模型、非 Claude 跑 WebSearch、DeepSeek 讀 PDF） |
| 10-12 當時壞的 | 都好了：gpt-6-luna 不再整輪 400、Codex 預設 catalog 拿得到工具、MCP 與 sub-agent 叫得到、跨家族換手不再 404／400、Claude Code 讀得到 PDF |
| 帳本 | 1,014 個請求沒有一個有兩個終端事件；997 個完成的請求各恰好一筆用量列與一筆成本列，與稽核逐筆相同 |
| readiness 19 支 | 沒有造成回歸；有執行期行為的 12 支全部實測成立，其餘 7 支是 gate、測試或這個環境測不到 |
| `/v1/messages` 逐段輸出（#6475） | gpt-5.6-luna 第一個字 3.4 秒、中間 1,407 個 delta；Claude 仍是 21.1 秒整回合一次到 |
| 大訊息（#6459） | 送 100 KB 以上的訊息時 `/v1/health` 仍即時 |
| 新找到的問題 | 1 個 P1、2 個 P2 的既有 bug 與幾個已記載缺口的實際後果，由 §2.1.12 的 11 支處理 |

- 之後合併的 11 支（§2.1.12）只有各自的直連或錄製檔證據，合併後沒有再用三個真 CLI 重跑。
- 「中斷」相關的觀察不算數：中間的 `ncat` 轉發器不會把 client 斷線傳到上游。
- 仍沒測的：Bedrock、Azure、Gemini、真 vLLM、Responses-only 模型、Sonnet／Opus、互動式 TUI、超過幾分鐘的長回合。

### 2.4 防回歸的 gate（CI 的 Static Gates；G1–G4 與 parity gate 附 self-test）

| Gate | 鎖什麼 |
|---|---|
| G1 `translation-core-purity-gate` | 核心路徑不准出現 provider 名稱、Responses 集合成員判斷、agent UA 比對；baseline 只減不增（#6446 擴大範圍，見表下） |
| G2 `translation-dispositions-gate` | 三張處置表（Responses→chat 65 列、Responses→Anthropic 65 列、Messages→Anthropic 55 列）跟 SDK 欄位與 SPEC-312 §3.1／§3.2 逐列相同。#6313、#6315 的 hosted 工具列、#6360 的工具列（`tool:custom`、`item:custom_tool_call*` 由剝除改成翻譯；新增 `tool:namespace`、`tool:tool_search`、`item:tool_search_call`、`item:tool_search_output`）、#6359 的 `part:document`、`part:search_result`（改成轉送）都在比對範圍 |
| G3 `envelope-single-owner-gate` | `xpenv1.` 只能出現在信封模組 |
| G4 `translation-matrix-completeness-gate` | 9 格 × 12 情境每一格都有結果；Green 引用的測試必須存在；Unsupported 必須附決策文件；KnownGap 必須附 issue |
| G5（conformance 測試） | 每個對話面的 401／404／422／400 都帶兩個關聯 header |
| Deploy Translation-Envelope Key Preflight Gate（#6302，`GATE-TRACK adr=ADR-503`） | 跑 `tests/deploy/test_envelope_preflight.sh`，驗 `blue-green-deploy.sh` 的 Phase 0.8 金鑰 preflight |
| `azure-request-shape-class-parity-gate`（ADR-438 D7 T2；**#6331 改寫**） | gateway 的 OpenAI 家族判斷（`backend/openai_model_family.py`）與 IAM 的鏡像（`provider_surface.probe_request_shape_class`）必須一致。改寫前只比兩個前綴 tuple；現在比 3 個字面值，再把兩邊模組各自載入，對 2,567 個產生的名稱比答案。載不進來或判斷函式拋錯算失敗，不算跳過 |
| Tokenizer Single-Owner Gate（#3838）、Token Estimator Convergence Gate（ADR-419） | 既有、寫在 `ci.yml` 內：只有 `bustream/tokenizer.py` 能 import tiktoken；只准兩個 token 估算器。#6382 只改了第一支的錯誤訊息文字。token 計數那幾支 PR 都要過這兩支 |
| `failure-health-attribution-gate`（#6447） | 三個失敗出口的每個呼叫都要寫明健康判定 |
| `provider-roster-parity-gate`（#6448） | gateway 與 IAM 的 provider 名單、Responses-only 名單、預設 host 一致；搭配 `tests/contract/test_provider_facts_complete.py` |
| `response-checks-gate`（#6474，ADR-494 Amendment B） | 回應端每條路徑 × 每個檢查都要宣告 |
| `ledger-producer-parity-gate`（#6469 擴大到用量軸） | gateway 與 IAM 的 producer、axis 詞彙相等 |

G2–G4 從 P9 之後沒改過。G1 由 #6446 擴大掃描範圍：加入 `production`、`registry`、`streaming`（不含 workers），client 判斷補上 regex 形式，身分判斷收進 `gateway/client_profiles.py`（ADR-503 Rev.9）。10-12～13 這批 PR **沒有新增任何 static gate**：動到 `.github/` 的只有 #6331（改寫 parity gate）與 #6382（`ci.yml` 一行訊息文字）。10-13～14 新增了上表最後四列。`tests/contract/provider_param_matrix.py` 與 `no_silent_drop_baseline.py`（#6476）是只減不增的契約測試，不是 gate。hosted 工具、計量、document、namespace、idle deadline、token 計數都只有 owner 測試（§4），其中兩支是掃原始碼的測試，作用接近 gate：

- `tests/unit/test_streaming_idle_liveness.py::TestEveryStreamingWorkerFeedsTheClock::test_every_base_worker_opens_its_client_with_the_request_clock`（#6348）：每個 worker 開 client 都要帶 `activity=self.upstream_activity`。
- `tests/test_spec276_rev21_routing_estimate_counter.py::TestTokenizerIsTheOnlyCallerOfAnEncoder::test_no_other_gateway_module_reaches_for_the_encoder`（#6382）：只有 `tokenizer.py` 呼叫 encoder。

### 2.5 矩陣現況（`tests/conformance/translation_matrix.py`）

9 格 × 12 情境，共 108 項（2026-10-13，`0925e5a13`）。各格狀態與 `bc0107d31`、`880d83612` 相同，10-12～13 沒有任何一格換狀態：

- **80 項 Green**：附通過的測試。
- **28 項 Unsupported**：附決策文件，例如 chat 與 Messages 本來就沒有伺服器端狀態。
- **0 項 KnownGap**。P9 時的 3 項都已轉成 Green：
  - (responses, Claude) S10、(chat, Claude) S10：由 #6257、#6284 修好；
  - (chat, Responses-only) S06：由 #6253 修好。
- 另外 (chat, Claude) S06 也由 Unsupported 轉成 Green（#6290）。

（P9 時是 76／29／3。）

10-12～13 只有兩支 PR 改了這個檔，改的都是 Green 格子引用的測試（引用數 144 → 152）：

- **#6338**：(responses, responses) 與 (responses, chat) 的 S09 加上 `tests/integration/test_responses_cross_family_history.py` 的測試。
- **#6360**：三個 responses 格子的 S05。翻譯出口的 S05 把 `test_a_custom_tool_is_dropped_on_the_record_on_the_translated_path` 換成 `test_a_custom_tool_reaches_a_translated_egress_as_a_function`，再加 `tests/integration/test_responses_namespace_tools.py` 的測試。也就是 S05 在翻譯出口的意思從「custom 被剝除並留紀錄」變成「custom 與 namespace 成員變成 function 送出、呼叫照原名回來」。

**矩陣裡仍有過期內容**：

- `_SERVER_TOOLS_REFUSED`（`translation_matrix.py:86-89`，messages 三格的 S06 都引用）仍寫「`web_search_*`、`web_fetch_*` 在 `/v1/messages` 入口被拒」。#6315 之後已經不對，#6338、#6360 改這個檔時都沒動這段。
- `_NO_CUSTOM_MESSAGES`（`:78-80`）的說明寫「S05 strips」，#6360 之後 S05 在翻譯出口已不是剝除。
- 情境仍只有 S01～S12。hosted 工具只有 S06（剝除）這一個情境，hosted `web_search`／`web_fetch` 的原樣轉送（#6313、#6315）沒有情境，也沒有任何一格引用它們的測試；document／PDF **沒有**矩陣情境；namespace、client tool search、apply_patch 歷史沒有獨立情境，只掛在 S05 的測試裡；thinking 前綴綁定、tool call 參數、idle deadline 也都不在矩陣內，只有各自的整合測試。

---

## 3. 還沒做的

### 3.1 上線前要做的（都需要另外授權）

1. **部署**：
   - **分支現況（2026-10-14 核對）**：
     - `origin/main` = `ee1a40564`（10-14 18:26）；這條線最後合併的是 #6515 `ee1a40564`。
     - `origin/rel` = `2534867ad`（tag v1.77.0.16，commit 10-14 12:06）。它比 v1.77.0.10 `418a732c7` 多了 IAM／Fleet 權限修正、console 與 CVE 修正、一次 IAM OpenAPI 重產，以及一支 gateway 修正 #6345（`TOOL_CALL_RESOLVED` 帶 group 與 proxy 範圍；不是翻譯軸），沒有 migration。翻譯軸的內容跟 v1.77.0.10 一樣：只有 P1–P8 與 Phase 0 的 4 支（#6195、#6197、#6203、#6207）。tag 只代表建立時間，實際部署時間 git 看不出來。
     - `origin/prod` = `ed62d8223`（v1.76.4，10-02 17:38），全部都不含。
     - 只在 `main` 的：P9 #6218、§2.1.1–2.1.6、10-12～13 的 18 支（§2.1.7–2.1.9）、silvia 的 #6367、#6397（§2.1.10），以及 10-13～14 的 30 支（§2.1.11–2.1.12）。main 領先 rel 260 個 commit。
   - **rel 已有 P3、P7、P8**（單一能力表、原生優先候選池、IAM 的 INV-269-3 放寬；Claude thinking 封進信封；`/v1/responses` 能用 Claude 和 chat 系模型）。rel 那份程式還沒有 #6302 的自動產生，所以若 rel 主機沒設 `XPARSE_TRANSLATION_ENVELOPE_SECRET`，下面第 2 點列的 P7／P8 後果可能已經在 rel 發生。**待核對**：rel 主機有沒有設這個變數。
   - **IAM 的翻譯軸相關改動仍是兩項**：P3 的放寬 INV-269-3，和 #6316 的計量（migration `0378`、`HostedToolPriceVersion`、OpenAPI）。10-12～13 的 PR 都沒有 migration，沒改 OpenAPI、consumer pin、compose 或 installer。只有 #6331 碰了 IAM 的一個程式檔與它的測試（`domain/value_objects/provider_surface.py`，註冊時分類 request shape 用的鏡像，跟 gateway 的 `backend/openai_model_family.py` 由 parity gate 鎖相等）：IAM 與 gateway 要出自同一版 main，照 main 同批部署就滿足。10-13～14 另有幾支 IAM 與 gateway 一起改的 PR：#6535（migration `0387`、IAM OpenAPI 與 consumer pin 重釘；Codex `/v1/models` 的 context length 由 IAM 提供）、#6534（推理等級）、#6469（用量軸兩端比對）。照 main 同批部署、IAM 先，就能滿足。
   - **部署順序仍是 IAM 先（`0378`），再 gateway**（#6316 的規則，SPEC-302 §10 Rev.12 那列）。`blue-green-deploy.sh` 本來就是這個順序：Phase 1 先更新 `xparse-iam`（entrypoint 啟動時跑 `migrate_locked`），Phase 2 才起新顏色的 gateway。
   - **照 main 上線不只套 `0378`**：rel 的 IAM 只到 `0368`，會一次套 `0369`–`0387` 共 19 支；prod 只到 `0347`，會套 `0348`–`0387` 共 40 支。`0379`–`0387`（notification mute、ADR-466 P2b／P2c／P3 的 Budget Limit、system admin 通知 backfill、sandbox usage、alert threshold、模型 context length #6535）都不是翻譯軸。`0374` 已由 #6327 修過（原本在有 Application Limit 列的 DB 上會 crash）。
   - #6316 重釘了 7 個 consumer 的 IAM OpenAPI digest（console、gateway、fleet、node-agent、scheduler、forecast、operator-mcp）；之後 IAM OpenAPI 又被其他 PR 改過（gateway 的 pin 另重釘 5 次）。同批要有對應的各 image。
   - **rel 不受下面的順序衝突影響**：rel 的 IAM 與 gateway 都已有 P3，rel 上線只需照「IAM 先（`0378`）、gateway 後」。
   - **與 P3 的規則衝突（只出現在 prod，v1.76.4 → main，兩邊都還沒有 P3）**：ADR-269「部署與回滾順序」（`:328-329`）寫「gateway 先，IAM 後；回滾反過來」，ADR-503 §7.2 的 2a 回滾也是「IAM 先回滾，再回滾 gateway」。這兩條到今天都沒被修訂。兩邊的空窗都不致命：
     - 照 IAM 先：空窗期間 IAM 已放行目標是 Responses-only 模型的 agent app 部署，但舊 gateway 還不會翻譯，這類請求在 chat 面會是改之前的 422（§1.2）。部署腳本走的就是這條。
     - 照 gateway 先：舊 IAM 對新 axis 回 422，gateway 重試三次後只寫 loss marker，那段期間的搜尋次數不入帳、沒有自動補記；token／cost 與服務都不受影響。要走這條得手動調整腳本的順序。
     - 要選一邊並接受它的空窗（§3.6 #2）。
   - **回滾**：先回 gateway，再回 IAM。`blue-green-deploy.sh rollback` 只切回前一個 gateway 顏色，不動 IAM、不跑 migrate；IAM 要退版得另外用舊版號再 deploy。`0378` 只在沒有 hosted fact 時可反向。IAM 回滾後，Budget、admission、告警、aggregate 的金額不含逐次費用，被 cost budget 擋住的 scope 可能暫時解除。
   - **`0378` 的鎖**：三個 axis CHECK（ledger 與兩張 rollup）是先移除再用一般的 `ADD CONSTRAINT` 加回，持有 ACCESS EXCLUSIVE lock 並重掃整張表；#6316 實測 2M 列 ledger（805 MB）整個 `migrate 0378` 花 4.5 秒（數字出自 PR 說明，沒有重量），期間 append 與 admission 的 `query-batch` 都會排隊。上線前先量 rel／prod 的 ledger 列數，挑低流量時段。
   - **硬規則**：#6313、#6315 不可在缺 #6316 的 gateway image 上線。照 main 部署就自然滿足。
   - **10-12～13 新增的環境變數都有預設值，不設也能上線**（清單見 §1.4「開關」）。部署 recipe 沒有任何一處設定它們。`XPARSE_STREAMING_FIRST_OUTPUT_TIMEOUT_SEC` 與 `XPARSE_STREAMING_LIVE_SILENT_MAX_SEC` 要留在 `queue_timeout_sec`（300 秒）以下；想回到 #6348 之前的行為，把這兩個設成 60。
   - **上線時要告訴營運與客戶的行為變更**（細節見 §2.2）：
     - Codex 的 `namespace` 工具（MCP、sub-agent、code mode 的全部工具）與 client 端 `tool_search` 現在照送到模型（#6360）。**Tool 規則的 `tool_names.allow`／`deny` 管不到 namespace 成員**：請求端不剝、回應端不擋；`tool_use: deny` 與舊的 `tool_call_allowed=false` 照舊生效。稽核有紀錄。
     - `/v1/messages` 的 `document`（PDF）現在送得到模型（#6359）。PDF 內容沒有任何 rail 讀得到；吃不下檔案的模型不進候選，指名它回 400 `document_unsupported`。跨部署的 session 若歷史裡有 PDF、原本落在 DeepSeek 這類模型（以前回 200、模型其實沒看到文件），部署後指名時會變成 400（§3.2）。
     - 模型回的工具呼叫缺參數或被截斷，不再回 503，改成照送給 agent（#6363）；要舊行為設 `XPARSE_TOOL_CALL_ARGUMENTS_ENFORCE=1`。
     - 串流的等待上限變長：第一個輸出前最多 240 秒（以前 60 秒就切）；provider 收了請求卻不回時，佔住 slot 的時間也從 60 秒變成最多 240 秒（#6348）。
     - client 造成的 4xx 不再拉低模型健康分數、不再踢掉別的 session 的 pin（#6362）。`/v1/responses` 上連續 5 次 provider 失敗現在會開 breaker（與 chat 相同；breaker 只是健康訊號，不擋請求）。
     - 部署當下進行中的 Claude Code session 各掉一次 pin、重新判級一次（#6356 改了 affinity key 的算法，key 沒有版本段）。
     - 含 special token 字面（`<|endoftext|>` 等）或超長空白連續段的請求，在 tokenizer 就緒的行程上治理數字會變（#6378；例：minified JSON tool result 1 → 94,008），變大的請求會比以前早碰到預留或 pre-flight 的上限。其他請求逐位元不變。
     - 預算或額度用完改回 **400**，不再是 429（#6367，silvia）。靠 429 判斷「預算用完」的整合要改讀 `error.code`。
     - pre-flight ledger 寫入最多等 2 秒，失敗後 10 秒內的請求直接回 503（#6397，silvia）；「寫不進帳就拒絕」的行為沒變。
     - `/v1/messages` 生成期間每 15 秒送一個 `ping`（#6329）；gpt-6、o4 這類新家族改送 `max_completion_tokens`（#6331）；指名模型的請求稽核裡不再有 `tier`／`score`（#6347）。
     - **輸出上限**：client 沒送上限時 gateway 不再補 16000／4096（#6514）。OpenAI、DeepSeek、vLLM、Bedrock 由 provider 自己決定。Claude 的翻譯路徑會先打一次該 endpoint 的 `GET /v1/models/{id}` 查上限（新的出站呼叫，用同一把 credential；每個 endpoint × 模型在行程內只查一次；查詢被拒時那次嘗試失敗）。單回合的輸出、計費與 slot 佔用時間可能變大。
     - 不收 prefill 的 Claude 收到以 assistant 結尾的對話時，補一則 user 回合重送一次（#6516）；chat 故意送 prefill 的請求由 400 變 200，語意是「接續」。
     - DeepSeek：強制 `tool_choice` 那一回合關 thinking（#6503）；`json_schema` 不再路由到 DeepSeek，指名時回 400 `structured_output_unsupported`（#6512）。
     - 新的 `error.code`：`structured_output_unsupported`、`logprobs_unsupported`、`audio_unsupported`（`/v1/responses`，狀態碼仍是 400，#6453）。未知模型的訊息與沒帶 key 的 401 訊息都換了文字（#6453、#6498）。
     - `/v1/messages` 對非 Claude 模型逐段送出文字（#6475）。
     - Claude 被輸出上限切掉的最後一筆工具呼叫，在 chat 與 messages 上不交付（#6526）。
     - proxy 的 active consumer 數不再算已終止的 application（#6515）。
   - **真 CLI 的重跑**：10-14 已在 `bff643332`（含 readiness 19 支）用三個真 CLI 跑過一輪（§2.3）；之後合併的 11 支（§2.1.12）沒有整體重跑，rel 上線前建議先在 dev 再跑一輪。
2. **信封金鑰**（#6302 之後；10-12～13 沒有變動）：
   - 單機 compose（EC2、既有安裝、local-dev）**不用再手動佈建**：新 gateway 第一次啟動就在 `xparse-routing-db` volume 上自動產生，blue／green 共用同一把。部署 gateway 本身就完成佈建，所以授權併在部署裡。本機 dev stack 已經這樣跑（`source=file`，§3.5）。
   - 手動設 `XPARSE_TRANSLATION_ENVELOPE_SECRET` 變成選擇性覆寫；設 `off` 代表刻意關閉。
   - **Kubernetes（Helm／k3s）仍要自己建 Secret**，gateway 不會自動產生。
   - installer 寫的 kid 是 `k<YYYYMMDD>`；手動輪替照 runbook 用 `k<YYYYMMDDHHMM>`，否則同一天會撞名，gateway 不啟動、EC2 的 Phase 0.8 會擋下部署。
   - 部署後看 `/health` 的 `translation_envelope.source` 確認。
   - 只有 `translation_envelope.state` 為 `off`（`source` 為 `none` 或 `disabled`）時才會出現下面三個後果：
     - Claude 的 thinking 不帶簽章（P7），`/v1/messages` 的 client 拿不到 thinking；
     - Codex 的 `encrypted_content` 不承載 Claude thinking（P8），`include=reasoning.encrypted_content` 會被剝除並記錄；
     - **P9 的原生直送遇到帶 thinking 的歷史回合就會改走翻譯**（`native_fallback_reason=envelope_unconfigured`）：Claude Code 開著 thinking 的多輪 session，cache 優勢會不見。

### 3.2 已知限制（SPEC-312 §11–§13 與後續 PR，屬設計取捨、已宣告，或尚未處理）

**回應與串流**

- **messages 的回應側仍經 chat core 重建**：上游回的 block 經 builder 輸出，回應側的原生串流依 ADR-503 延後。#6290 之後 Claude 自己的 `stop_reason`／`stop_sequence` 走 side channel 帶回。#6315 用 trace 把 server block 與 citations 依上游順序原樣插回（`hosted_blocks.py::rebuild_hosted`），但這仍不是原生回應串流。
- **`/v1/messages` 的文字**：#6475（ADR-239 Amendment C，SPEC-312 C-312-64）起，chat core 宣告這次嘗試是 append-only 才逐段送出。條件全部成立才算：routing mode 是 `fast_only`／`large_only`、output rail 不是 buffer、沒有 Tool 規則、沒有 hosted web 工具、出口 wire 是 `openai_chat` 或 `openai_responses`、模型不是 Claude（看模型名稱，所以 Bedrock／Vertex 上的 Claude 也算在內）。其餘情況（包括所有 Claude）仍是回合結束才一次送到，生成期間只有每 15 秒一個 `ping`（#6329）。10-14 實測：指名 gpt-5.6-luna 時 3.4 秒出現第一個字；Claude 仍是 21 秒才一次到（10-12 實測 gateway 2.6 秒拿到第一個 token，client 21.6 秒才看到字）。Claude 要逐段，得先有真元件證據，而且 messages 回應側的原生串流仍延後。
- **`/v1/responses` 一律回 SSE**：client 送 `stream: false` 也一樣（ADR-339／ADR-437）。OpenAI SDK 的非串流用法與 `responses.parse()` 不能用，Codex 不受影響。非串流收集器還沒開工。
- **串流時上游 4xx 變成 HTTP 200 加一個 SSE error**：Claude Code「`encrypted_content` 解密失敗就剝掉重試」要求 `status===400`，經 Xparse 永遠不會觸發。`encrypted_content` 跨 credential／模型能否重送（A-10）也未驗證。
  - 200 改不了：串流一開始就先送 keepalive（`sse_transport.py`），否則 ingress 會斷線；要等第一個事件才開串流是另一個 wire 決定（SPEC-282 RSP-RES-8）。
  - chat 的錯誤 frame 之後**不送 `data: [DONE]`**，是規格寫明的（EVENT_STREAM_SPEC §8.2、SPEC-304 C-304-147）。例外：排隊中被拒（queued admission）的兩個出口會送 `[DONE]`（`routes/chat.py:2629`、`:2640`）。`/v1/messages` 送 `event: error`、不送 `message_stop`（同 Anthropic 原生）；`/v1/responses` 送 `response.failed`（RSP-TERM-1）。
  - 其他平台沒有共識（2026-10-23 讀原始碼）：Bifrost 刻意不送 `[DONE]`（#5546）；vLLM、NeMo Guardrails 一律補 `[DONE]`；LiteLLM 兩種都有。client 要看 `data:` 裡有沒有 `error`，不能把 `[DONE]` 當成成功。owner 10-23 決定不改。
- **同一個拒絕，`/v1/responses` 的狀態碼和另外兩面不同**（owner 10-23 決定不改，aiap02p 測試報告 #10、#17）：

  | 情況 | chat | messages | responses | 依據 |
  |---|---|---|---|---|
  | 模型名不在 pool | 404 `model_not_found` | 404 | **400** | ADR-437 Amendment E（INV-437-20）、SPEC-282 RSP-ADDR-1 |
  | guardrail 擋下（請求端） | 451 | 451 | **400** | ADR-437 Amendment A、SPEC-282 RSP-IN-1／RSP-IN-3 |
  | 串流開始後才擋 | 200 + SSE error | 200 + `event: error` | 200 + `response.failed`（`invalid_prompt`） | RSP-TERM-1 |

  原因：Codex 只把 400、429 當成不重試的錯誤，404／451 會被重試 5 次。轉換點只有一個：`responses_terminals.py::as_responses_refusal_status`。參考平台也沒有統一的做法：LiteLLM 未知模型三面都是 400、無權限 403、guardrail 預設 400；Portkey guardrail 446；OpenAI 自己未知模型回 404。
- `/v1/messages` 串流中的 gateway 逾時仍標成 `overloaded_error`，Claude Code 會當成可重試（#6348 沒處理）。
- 工具呼叫的參數仍在呼叫結束時一次送給 client，不逐段串流。
- `/v1/messages` 串流的 `output_tokens` 從 #6475 起是 provider 的數（SPEC-312 C-312-65；agent mode 仍是估算）。`input_tokens` 與快取欄位只在請求帶 `cache_control` 時出現在 `message_delta.usage`；沒帶時 client 拿不到真實的 input 數（10-14 實測 client 看到的 `input_tokens` 是 0）。Claude Code 的主要請求有帶，不受影響。

**逾時**（#6348，ADR-313 Amendment A）

- 串流的等待分三段，量的是上游有沒有送位元組，不是 worker 有沒有 yield：第一個輸出前上游靜默最多 240 秒；有輸出後靜默最多 60 秒（`XPARSE_STREAMING_IDLE_TIMEOUT_SEC`，ADR-334 階梯不變）；上游一直送位元組卻沒有輸出最多 240 秒。operator 的 `idle_timeout_sec` 比預設大時三段一起拉高，都被 1800 秒硬上限夾住。
- 代價：provider 收了請求卻什麼都不回時，佔住一個 slot 最長 240 秒（以前 60 秒）。
- gateway 自己時鐘判定的逾時，只在上游從未回應時才記模型健康失敗（INV-313-7）。
- 非串流沒有 liveness 判斷，仍是總時限：推理模型預設 240 秒，其他模型照舊約 60～70 秒，超過就 504、不換模型。
- slot reaper 的單請求上限不跟 `idle_timeout_sec`：把 idle 調到約 300 秒以上時要同時調高 `Model.timeout`。被砍掉的回合只記已送出的 token。

**messages 打 Claude 的原生直送**

- **遮罩生效之後**：沒帶 hosted 工具時走翻譯（`native_fallback_reason=text_masked`），對話歷史的斷點與 client 的 system block 結構不保留，cache 命中會掉；被遮的文字還在偵測面內的每一輪都一樣，不只那一輪（10-12 實測 cache 讀取比例 0.999 → 0.254）。帶 hosted 工具時把遮罩套回原生 body（`native_rewritten`），套不回就 400。
- **只有 `provider=anthropic` 走原生**：Bedrock／Vertex 上的 Claude 仍走翻譯，hosted web 工具也只能在 `provider=anthropic` 上用。這些路徑上：
  - `stop_reason` 只能回 `end_turn`；
  - chat 的 `cache_control` 標記與 `prompt_cache_key` 都不會變成 Bedrock 的 `cachePoint`，只記為 drop；
  - PDF 送不到：Bedrock 與 Google 的 worker 沒寫檔案 part，帶 PDF 的請求不會選到它們（#6359）；
  - thinking 前綴綁定的處理（#6361）沒有在這些路徑上驗證；#6330 的訊息形狀在 Bedrock 上只有 contract 測試；
  - #6199 的 Bedrock 部分還沒實測。
- **`thinking` 只轉送 Anthropic 對該型別收的鍵**（#6329）：其他鍵剝除並記 `field:thinking.<key>:<reason>`；`block_binding` 只在 client 同送 `thinking-binding-controls-*` beta 時保留，beta 也只在 `block_binding` 真的送出時轉送。
- **`context-1m-*` beta 不在原生路徑的轉送清單**，會被剝除並記錄。#6329 的說明寫現行家族不帶它也有 1M window（直連實測：210,619 token 的 prompt 不帶 beta 打 claude-haiku-5-5 回 200）；經 gateway、超過 200k 的 session 沒有實測。
- **舊家族 Claude 的 thinking 預算**：原生路徑送 seam 的 budget（1024／2048／8192），不保留 client 的精確 `budget_tokens`；與翻譯路徑相同。
- **claude-sonnet-5 收到對話中途 system 時走翻譯**：文件說不支援，實測卻是 200；照文件排除。
- **Claude Code 的 per-turn effort**（#6282）：只在 `role: system` 的訊息上、而且 beta 同送時轉送；放在其他訊息上會被剝除並記錄，那一輪退回頂層 effort。
- **`pause_turn`**：#6315 之後經 provider-stop side channel 回報；證據仍只有測試（假 transport 加研究包錄下的形狀），還沒有真 Anthropic 的實測。
- **`/v1/messages` 的 typed tool**（#6300）：只有沒有 `type` 或 `type: "custom"` 的工具會變成 client function；advisor、code_execution、tool_search_tool_*、mcp_toolset、computer、bash、text_editor、memory、browser_toolset 與未知型別都回 400。Claude Code 2.1.280 之前的版本設了 advisor 會直接 400。

**Claude 的 thinking 與前綴綁定**（#6361、#6360；SPEC-312 C-312-30a～30g、C-312-55）

- 事實：現行的 Claude 5.5 家族把 thinking 簽章綁在產生它的那次請求的前綴上（`system`、`tools`、它之前的 messages）；前綴一變再送回同一個 block，Anthropic 回 400。直連相同，是 provider 的既定行為。
- 今天會把簽過章的 thinking 經翻譯送回 Claude 的入口只有 `/v1/responses`。三層處理見 §1.4「不透明狀態用信封」。
- 限制：
  - compaction 之後 Claude 先前的 thinking 一定被丟（`tools` 真的變了），只有「切回 Claude」保得住；
  - 對話中途的 `developer` 文字位階從 system 降為 user 回合的內容，沒有做對抗式測試；
  - 非 `api.anthropic.com` 的 Anthropic wire 端點不送 controls，只靠重送一次；
  - 紀錄只在終端事件的 `translation_output_dispositions`，不在 `X-Xparse-Dropped`（header 在 Anthropic 回答前就送出了）；
  - 工具由對話中途的項目宣告時，位在它之前的 reasoning item 不還原成 thinking，記 `item.reasoning:drop:tools_declared_later`。
- chat 入口仍把對話中途的 system／developer 提到頂層 `system` 尾端（ADR-382 Amendment B）。這條路不回送簽章所以不會 400，但會讓訊息快取失效。
- **強制工具＋新家族 Claude 開 thinking**：`tool_choice` 為 `required` 或指名工具時，Anthropic 回 400。Codex 只送 `auto`，目前碰不到。`tool_choice: "required"` 旁邊只有 namespace 工具時會被降回預設。
- **`reasoning.summary` 沒對應到 Claude 的 thinking display**：Codex 看不到 Claude 的推理摘要。

**跨家族換模型的 Responses 歷史**（#6338）

- **有狀態的 Responses 不模擬**：打非 OpenAI 模型時回 400。要模擬就得自建對話儲存，屬資料保管問題，ADR-192 Option B 維持否決（owner 10-10 再確認）。
- 翻譯回合的 reasoning item 送原生 OpenAI 前移除（§1.3）。以前 DeepSeek 回合之後換到 OpenAI 模型會 404，而且之後每一輪都失敗。
- R3 與加密 reasoning（SPEC-307 RF-8 Rev.7）：只有走原生 Responses 出口的主模型，才用它的 credential 限縮替代模型。主模型走翻譯出口時，池內原生 Responses 模型只有一個 credential 就不限縮；有多個時無法判斷是哪一個發的，原生模型都不當替代（`fallback_scope="translated_only"`）。這種情況下 session affinity 仍會把 session 釘在 R3 落到的翻譯模型。
- 沒有「provider 回 invalid encrypted content 就剝掉重試」的保底。
- 歷史裡的 `custom_tool_call`／`custom_tool_call_output` 送到舊家族的**原生** OpenAI 模型時沒有另外處理，未驗證（翻譯出口已由 #6360 處理）。

**Codex 的工具**（#6360，ADR-490 Rev.16 Amendment C；owner 10-12 決定「全部放行，治理之後補」）

- 原生 Responses 出口（OpenAI、Azure）照送的：`function`；`custom`（舊家族除外，#6283）；`namespace`（成員照自己型別的規則）；client 執行的 `tool_search`（`execution: "client"`）；hosted `web_search` 系列（#6313）。頂層 `tools` 與 `additional_tools`／`tool_search_output` 裡的工具同一套規則。
- 模型不收時那次嘗試剝除並記錄（`platform_tool_stripped`＋`X-Xparse-Tools-Stripped`），不回 400、不縮路由。不收的名單都是封閉的舊家族：`namespace` 是 gpt-3.5；`tool_search` 是 gpt-3.5、gpt-4*、chatgpt-4o、o1、o3、o4、codex-mini、gpt-5（含 mini、nano）、gpt-5.1、所有 `-nano`。不收 `tool_search` 的模型，`tool_search_call` 不送、`tool_search_output` 改成 `additional_tools`。
- **仍一律剝除並記錄**：`file_search`、`code_interpreter`、`image_generation`、`mcp`、`computer_use*`、provider 執行的 tool search、形狀不對的 `namespace`。
- 翻譯出口（Claude、chat 系）只有具名 function：namespace 成員成為 `<namespace>__<tool>`（預設 namespace `functions` 保留原名，最長 64 字元）；`custom` 成為只有一個字串參數 `input` 的 function；client `tool_search` 成為名為 `tool_search` 的 function；歷史的 `custom_tool_call*`、帶 `namespace` 的 `function_call`、`tool_search_*` 都成為工具回合，搜尋載入的工具併入請求的工具。回程依這個請求自己的宣告表還原成 client 宣告的形狀。
- 翻譯出口的回應物件 `tools` 回報的是降階後的 function，不是 client 宣告的原形（Codex 不讀這個欄位）。
- **Tool 規則不涵蓋 namespace 成員**（SPEC-304 C-304-404，已記載的缺口）：`tool_names.allow`／`deny` 不讀 MCP、sub-agent、code mode 的工具，請求端不剝除、回應端不擋，只留紀錄（`tools_offered` 逐成員列 `<namespace>.<tool>`；`TOOL_CALL_DETECTED` 與 `tool_call_undeclared` 帶 `tool_namespace`）。code mode 的工具是在 `exec` 的 JavaScript 裡呼叫的，將來補上名稱規則也看不到腳本叫了什麼。待決題在 ADR-490 Q15／SPEC-304 OQ-S14，還沒有 tracking issue。
- 模型判斷後面沒有「provider 回 400 就剝除重試」的保底；Azure 沒有驗證。`tool_search_call` 不記 `TOOL_CALL_DETECTED`。
- `web_search` 系列的 `tool_choice` 指名只是軟需求；路由不會因為請求帶了 `custom` 就偏好吃得下的模型（產品決定）。
- Codex 內建 catalog 的 `gpt-5.6-luna`（responses-lite＋code mode）：#6360 之後不覆寫 catalog 也拿得到工具。code mode 下 Codex 不送 `web_search` 是 Codex 端的行為，要搜尋仍得覆寫 catalog（#6360 之後沒重驗）。
- Codex 在 Claude／DeepSeek 上 `web_search` 被剝除時，Codex 沒有任何提示（R-strip 的設計）。

**chat 入口的訊息形狀**（#6330，SPEC-256 C-256-D16）

- 出口是 `anthropic` 或 `bedrock` 時：system／developer 的 text parts 接成一則 system 文字（`cache_control` 的位置不保留，斷點放在整段 system 上）；`developer` 視同 system；assistant 的文字 parts 排在 `tool_use` 之前；沒有頂層 `type` 的工具 schema 補成 `type: "object"`。
- 帶不過去的由 gateway 在送出前回 400 `upstream_format_error`：system／developer 裡的非文字 part；送 Anthropic 的 schema 頂層有 `anyOf`／`oneOf`／`allOf` 或 `type` 不是 `object`。
- **DeepSeek 已補上**（#6452，SPEC-256 D16i／D16j）：`developer` 在原位改成 `system`，記 `role.developer:rename:D16`；沒有頂層 `type` 的 schema 補 `type: "object"`。**其他 OpenAI 相容端點（vLLM、`openai_compat`）仍沒有**：`developer` 可能 422、無型別 schema 可能 400，不換模型；自動路由下同一個請求依落點時好時壞。
- **自動 cache 斷點只認 client 的意圖**：client 帶 `prompt_cache_key`（#6257），或在 chat 訊息／part 上放 `cache_control`（#6284），Claude 才會被加斷點（INV-382-2）。OpenCode 依模型「名稱」決定送不送 `cache_control`：用 application code 當模型名時，自動路由落到 Claude 沒有 prompt cache；用含 `claude` 的別名 key 才有。
- **chat 系出口沒有 `parallel_tool_calls`**：`false` 剝除並記錄。
- **Claude 結構化輸出**（#6242、#6287）：`json_object` 沒有 Anthropic 對應，剝除並記錄。文法不支援的 schema 限制改寫進 description，只是給模型的提示。
- **chat 入口的 FastAPI 驗證 400**（例如未知的 content part 鍵）仍沒有 `X-Request-Id`／`X-Trace-Id`；`type: file` 的 part 仍是入口 400。

**OpenAI 家族的請求形狀**（#6331，SPEC-256 Rev.16、INV-256-16）

- 保守多剝：reasoning 關著時（gpt-5.1～5.4 沒設 effort、送 `reasoning_effort: "none"`）模型其實收 sampling，gateway 仍剝除並記錄。
- 沒涵蓋的：`chat-latest` 這類不帶世代的別名認不到；Azure 三條 wire 共用同一個判斷但沒有 D17 紀錄，也沒有對真 Azure 驗證；Claude 的「現行家族」已由 #6452 改成版本規則（§1.4），解析不出版本的名稱仍當舊款；`gateway/pre_execution.REASONING_MODELS` 與 `factory` 的 `supports_streaming` 兩份名單沒動。

**輸出上限與工具呼叫**

- **gateway 不再替 client 補輸出上限**（#6514，owner 10-14 決定；SPEC-256 Rev.20 C-256-D19、ADR-338 Amendment 2026-10-14）：16000／4096 與 `XPARSE_REASONING_NULL_MAX_TOKENS`、`XPARSE_DEFAULT_NULL_MAX_TOKENS` 都已拿掉。上限選填的 wire（OpenAI、DeepSeek、vLLM、Azure、Bedrock）client 沒送就不送，由 provider 自己決定。Anthropic 的 wire 必須帶上限，翻譯路徑（chat→Claude、Responses→Claude）改送該 endpoint 的 Models API（`GET /v1/models/{id}`）公布的上限，例如 claude-haiku-5-5 是 128000；每個 endpoint × 模型在行程內只查一次。endpoint 沒公布就不送，provider 的 400 原樣回給 client。原生 `/v1/messages` 不變。稽核的 `exec_max_tokens_source` 記這次上限的來源：`client`、`provider_limit` 或 `omitted`。
- **Codex 打 Claude 撞到上限後重試**：10-14 live codex-1 的情況是，Codex 重送的歷史以半截 assistant 結尾，Claude 不收 prefill、回 400。現在翻譯嘗試遇到這個 400，會補一則 user 接續回合（`Continue exactly where you stopped.`）再重送一次（#6516，SPEC-312 C-312-67，ADR-503 Rev.11）。被救回的 400 不算失敗、不記健康，終端事件記 `assistant_prefill:emulate:prefill_unsupported`。仍會失敗的有三種：半截文字以空白結尾（provider 先回另一種 400，要不要剪掉尾端空白待 Peter 決定）、截在 thinking 上、截在 tool_use 上。原生路徑不救。
- **client 的 `max_tokens` 不夾模型上限**：Claude Code 送 32000／128000，路由到上限較低的模型時是 provider 的 400，不換模型。
- **`max_tokens` 下限**（#6287）：翻譯／bridge 到 Responses 出口時，小於 16 會調到 16。原生 `/v1/responses` 照 client 的值送。
- **工具呼叫的參數審視不擋回合**（#6363）：只涵蓋 chat 與 `/v1/messages`。
- `/v1/responses` 只記錄、不改事件（#6465，SPEC-304 C-304-408）：參數不是 JSON 物件時，終端事件帶 `tool_arguments_invalid_*`。被輸出上限切掉的呼叫記 `reason=truncated`（#6526，Rev.28）。翻譯路徑上被切的 `function_call` 仍以 `completed` 交付（10-12 報告寫 Codex 會照樣執行，repo 內沒有可核對的證據），要不要改成不交付等真 Codex 的前後對照再決定（D3-B）。這個入口不寫 `tool_calls_truncated_*`，所以看不到這個欄位不代表沒有被切。
- Claude（Anthropic 直連）被切掉的最後一筆 `tool_use`：以前工具沒宣告 `required` 時會被當成 `"{}"` 交付。#6526 起依 provider 的訊號（沒收到 `content_block_stop`）判定，chat 與 messages 都不交付，記 `tool_calls_truncated_*`。bridge 在上限截斷時交付已經收完的呼叫（#6460），丟掉的那一筆也記。
- 非串流請求對被截斷的呼叫不記 `TOOL_CALL_DETECTED`。OpenCode 遇到 `finish_reason=length` 會靜默停下。
- **`function_call_output` 裡的 `input_file`** 仍剝除並記錄；圖片已可送到模型（#6288）。

**`/v1/messages` 的 document（PDF）**（#6359，SPEC-312 §13）

- 各出口：Claude 原生原樣轉送；OpenAI 自家 API 的 `openai` 列送 `file` part 或 `input_file`；Responses-only provider 送 `input_file`；DeepSeek、vLLM、其他 OpenAI 相容端點、Bedrock、Google 不進候選。URL 來源只有直連 Anthropic 收。沒有能讀的模型，或指名不能讀的模型 → 400 `document_unsupported`。Files API 的 `file_id` 與不認得的來源在入口、認證前回 400。
- **PDF 沒有任何 rail 讀**（input rail、PII、word filter、classifier、conversation scope 都只看文字），只有每次嘗試的 `unread_parts=document:<n>`。owner 10-12 接受。同一則訊息裡文字帶 PII、旁邊有 PDF 時，enforce 遮罩寫不回去 → 451（與圖片相同）。
- 估 token 與預算不計 PDF 的頁數；內容擷取開著時 PDF 的 base64 原樣進擷取紀錄；`file_input` 的接受名單是 provider 層級，指名不讀 PDF 的 OpenAI 模型時由 provider 自己回 400；非原生出口沒有 citations。
- **上線時的過渡**：需求是從整份 messages 算的，歷史裡只要有一份 PDF，之後每一輪都帶 `file_input` 需求。跨部署的 session 若原本落在 DeepSeek 這類模型，部署後自動路由只會選讀得了的模型，指名時直接 400。這一點是從程式推得，SPEC 沒有另列過渡條款。

**hosted web 工具**（#6313、#6315、#6316；10-12～13 沒有變動）

- 只接受表上 7 個版本；`web_search_preview` 或未來的新版本在 messages 入口回 400。
- 非原生出口上的 hosted 歷史剝除並記 `hosted_history: not_native_egress`。帶 hosted 工具或其歷史的請求不查也不寫語意快取。
- 原生 `/v1/messages` 上，hosted 工具不受 Tool 規則管轄，也沒有 `max_uses` 或網域夾制。
- output rail 改寫過文字會拿掉 citations；output rail 暫存釋出路徑會把多則 message 併成一則，citation 位置會偏移。
- Claude Code 指名非 Claude 模型時 WebSearch 一律 400，即使 pool 裡有能跑的 Claude（#6315 的設計）。
- **沒有關閉開關**：沒有租戶開關，也沒有部署層級開關，pre-release registry 也沒有條目。唯一止血手段是 `XPARSE_TRANSLATION_FORCE_OFF`（關掉整個翻譯軸；帶 hosted 工具的 messages 請求會 400；不影響原生 Responses 的 web_search）或回滾 image。所以 ZDR、HIPAA 租戶目前排除不了。
- **guardrail 盲點**：provider 抓回的網頁內容，gateway 在模型使用前看不到。owner 10-11 決定接受。PDF 同屬這一類（上節）。
- **計量的限制**（#6316）：
  - OpenAI 直連沒有官方次數，只數 `action.type=search` 的 `web_search_call`（`meter_source=item_count`）；金額沒按估計與否拆開。
  - Azure 沒有價格，記為 unpriced，cost budget 管不到；Azure 的次數只看 `usage.tool_usage.web_search.num_requests`，回應沒有這個 block 就不推算。Azure 沒實測，搜尋可能完全沒入帳。
  - 失敗與 client 中斷的嘗試會記帳，但被 retry 或 fallback 取代掉的嘗試仍不記。
  - Console 的 Current Spend 卡片：In＋Out 小於標題的 `cost_usd`，差額就是搜尋費；Console 型別還沒加新欄位。
  - 草稿 #5640 的 R2 rollup 要從原始 ledger 計 hosted 費用。

**Routing、session 與健康分數**

- **routing 的 request context 不再讀內文**（#6459，ADR-285 Amendment A，SPEC-276 OBJ-W5）：沒有策略在讀的 5 個訊號已刪；`prompt_token_estimate` 經同一份請求範圍記憶計數，用 `estimate_prompt_tokens_off_loop` 在 event loop 外算，數字逐位元不變、不取樣。10-14 實測送 100 KB 以上的訊息，`/health` 仍即時。
- 分級器只讀計分視窗（#6347），所以超過 32,768 字元的 ask 可能分到不同級；`decision_duration_ms` 在 `llm_judge_routing` 下包含 judge 的往返。
- **開了 tier escalation 的 app，命中 pin 的請求仍每個都判一次級**，直到 pin 升到最強級為止：工具迴圈的每一步、permission classifier、標題、compaction 各判一次，判的是同一句話。三種設定的行為：沒開 affinity → 每個請求都判；affinity 開、escalation 關（預設）→ 一個 session 只在第一個請求判一次；兩個都開 → 每個請求都判。10-12 第二輪實測（兩個都開）judge 中位數約 2.5 秒、佔 session 時間約 35%；同一個寫程式迴圈 AUTO 74 秒、指名同一顆模型 33 秒。要不要讓工具迴圈沿用該輪的判定，owner 還沒決定（§3.6）。
- **session 升級只升不降**（ADR-447，owner 10-12 決定維持）：判高一次就留在較強的模型。judge 對同一句話的判定不穩（10-12 實測 Claude Code 三分之一的迴圈判出不同級），兩者相加，session 會被推到最貴的模型。
- **輔助請求**（permission classifier、標題、摘要、compaction）跟著 session 釘住的模型：owner 已決定要做，還沒開工。
- judge 判不出來的那一輪不寫 pin；一旦發生 failover，session 會被釘在備援模型上（10-12 報告 §3.2，修正後沒重驗）。
- 已知壞掉的模型仍不會被排除在自動路由之外，resolver 不讀健康分數。#6459 起，自動路由選到 breaker 開著的模型時，會累加 `xparse_gateway_routing_breaker_open_selected_total{endpoint}`，只計數、不改決策。每個請求都回 4xx 的模型（operator 設錯）也不會被標成不健康（#6362）。**2026-10-23 #7170 起**（ADR-321 Amendment C、SPEC-276 Rev.23）：5 分鐘內被 provider 拒絕 ≥10 次、比例 ≥90%、來自 ≥2 把不同 key 的模型會被排除在自動路由之外，300 秒後自動恢復；健康分數與 breaker 不變（INV-447-34），只有一把 key 的 tenant 不會觸發。計數器 `xparse_gateway_routing_reliability_excluded_total{endpoint, model_id, reason}`。
- 不在 pool 的模型名仍是 404／400，沒有別名（Claude Code 只設 base URL 與 key 時送 `claude-opus-5-5`，第一個請求就失敗）。#6453 起訊息會指路：把 model 設成 application code（或 `"default"`，chat 也可以省略），`GET /v1/models` 列出可用的名稱。但 Claude Code 會把 404 換成自己的通用訊息，使用者看不到這段指路（10-14 實測）。設定方式見 `docs/runbooks/agent-cli-setup.md`。
- 原生優先指的是本面候選，不是 wire 相同（§1.4）：Claude Code 用自動路由時不會偏好 Claude。
- Claude Code 被路由到 OpenAI 系模型時，billing 行仍是送往上游的 system 第一行，`/compact` 後上游的自動 prefix cache 會失效（#6356 沒處理）。
- `/v1/responses` 的 `response.failed` 與 `truncated_stream` 仍是未分類的失敗（會移動健康分數）；`provider_error` 仍含 429／408。

**token 計數**（ADR-419 Amendment D～I）

- heuristic 依片段計長詞的修訂在旗標 `XPARSE_HEURISTIC_COUNT_LONG_RUNS` 之後，**預設關**（#6380）。關著時 heuristic 把沒有空白的內容整段算成一個詞：200,000 字元的 minified JSON 回 1。這影響沒有 tokenizer 的行程（退化，或 `XPARSE_TIKTOKEN_DISABLED=true`）的每一個估算。何時翻預設是 ADR-419 OQ-5，未裁定；Helm chart 也沒有這個旗標的值。
- heuristic 對 Anthropic／Gemini 池準不準沒有裁定：#6377 只量測、列五個選項，不做選擇。Claude 4.7 起換了 tokenizer，cl100k 對英文低估約三成。
- 四條計數 thread 同時算中文時 event loop 仍會停約 53 ms；請求 body 沒有大小上限。
- `XPARSE_HEURISTIC_COUNT_LONG_RUNS` 沒登記在 `runtime.schema.json`（同檔另外三個 tokenizer 旗標也沒登記）。

**Budget 與帳務**

- pre-flight ledger 寫入失敗仍是拒絕（503，fail-closed）；#6397 只把等待縮到 2 秒。issue #6353 提的「依 tenant fail mode 放行」沒有採用。
- OpenAI 的 cache-write token 仍以 0 元計（少扣）。10-14 實測約佔該模型應收的 43%。chat 入口其實也有回報 cache write，是 gateway 的解析器沒讀，所以同一個模型、同一段 prompt，價格會因入口不同而不同。目前已經看得到：終端事件帶 `cache_write_zero_rated`，計數器是 `xparse_gateway_cache_write_zero_rated_tokens_total`（#6451）；IAM 盤點會列出沒寫 cache-write 價的價格段（#6471）；SPEC-302 已更正為「OpenAI 從 GPT-5.6 起收 cache write」（#6513）。計價規則（沒有 cache-write 價時要不要退回 input 價）待 Peter 決定；在 Console 補上價格段可以先止血。
- client 中途斷線的回合以估算值入帳，整段 prompt 當成沒命中快取的全價輸入：仍在。#6509 起估算原因記成 `client_closed`，不再是 `provider_dropped`。

**guardrail 設成 enforce 後 agent 會壞**（10-12 報告 §1.9；全部還沒開工）

- 偵測面上限 `DEFAULT_MAX_MESSAGES = 24`（`gateway/guardrail_detection.py`，env `XPARSE_PII_DETECTION_SURFACE_MAX_MESSAGES`）是以聊天對話估的：有 word_filters 或 PII 的 enforce 政策會讓真 agent 在第 8～12 個工具回合被 451，之後 session 每次送出都被擋。
- 其他：block 詞進到工具結果後 session 永久被擋；`block_presentation=graceful` 在 `/v1/messages` 串流回空白；judge 沒吐出文字就 503；PII 遮罩不冪等、會遮掉 Claude Code 的 `Co-Authored-By` 行；`scan_tool_results=true` 第 25 個工具結果起 503。細節與位置看報告。

**10-12 報告裡其他還沒處理的**（修正後沒有逐項重驗；位置與重現腳本看報告 §2、§3、§5）

- 結構化輸出跨家族仍不通：`/v1/responses` 的 `text.format` 打 Claude 帶不過去，`codex exec --output-schema` 只有原生 OpenAI 可用。拒絕訊息已改成專屬的 400 `structured_output_unsupported`，並點名要拿掉 `text.format`（#6453，C-312-60），不再說「沒有這個入口的模型」。
- DeepSeek 已修（10-14）：強制 `tool_choice` 打 `supports_reasoning=true` 的 DeepSeek 列時，那一回合送 `reasoning_effort: "none"`，記 `reasoning_effort:fill／clamp:D18`，由 400 變成 200（#6503，SPEC-256 D18）。旗標沒開、但模型其實會 thinking 的列，以及 `openai_compat` 指向 DeepSeek 的端點不在內，仍是 provider 的 400（D18f／D18g）。帶 `json_schema` 的請求（chat 的 `response_format`、responses 的 `text.format`）不進 DeepSeek 候選：自動路由由其他模型回答；指名 DeepSeek 時，gateway 在送出前就回 400 `structured_output_unsupported`（#6512，SPEC-312 C-312-66）。`json_object` 照舊送到 DeepSeek。
- 原生 `/v1/responses` 在 `store:false` 時仍同步寫 IAM binding，IAM 抖動時已產生的回應會被改成 `response.failed`。#6447 起這種失敗不再記成模型的健康失敗，但 client 看到的結果沒變。
- 平台自己的 provider key 失效（上游 401／403）原碼回給 client 且不換模型。
- `/v1/messages` 把空的 assistant 內容寫成空 text block；content part 的 schema 比 OpenAI 嚴。
- `X-Xparse-Translation` 只描述第一次嘗試；failover 之後，串流 `/v1/messages` 的 `message_start.model` 仍指向失敗的模型。（`GET /v1/models` 已由 #6453 改成收 `x-api-key`；`/v1/messages`、`count_tokens`、`/v1/models` 沒帶 key 的 401 訊息也改成兩種 header 都提，#6498。）
- provider client 沒有重用：`provider_http.provider_async_client` 每次上游呼叫都新建 `httpx.AsyncClient`，在 event loop 上同步解析 CA bundle（10-12 量到每次約 3.5 ms），也沒有連線重用。
- IAM 在併發壓力下記憶體成長（10-12 第二輪 0.55 → 1.45 GiB，原因未定位）。
- 架構：模型能力仍散在多處（#6331 只收掉 OpenAI 家族那一類）；`/v1/messages` 騎在 chat core 上；執行與回應各寫一套；`execute_chat` 與 `handle_non_streaming` 遠超複雜度門檻。

**文件與程式的漂移**

- ADR-490 的 Status 行（`:3`）、SPEC-304 §23 標題（`:1061`）與 Non-scope 行（`:11`）、PRD-337 的 Status 行（`:3`）都還寫「未實作」；PRD-350 `:265` 的 N7 仍寫 messages 的 `web_search_*`「照舊拒絕」。
- 矩陣的過期內容見 §2.5。
- ADR-503 的 Status 仍是 Proposed，SPEC-312、PRD-350 仍是 Draft。

### 3.3 issue、PR 與分支狀態（2026-10-13；PR 與分支 10-14 更新）

| issue | 優先 | 問題 | 狀態 |
|---|---|---|---|
| #6220 | P1 | main 上兩支 `0368` IAM migration | 已關閉：#6219 修好，沒改翻譯軸的程式 |
| #6196 | P2 | Claude 在 chat 面與 Codex 翻譯路徑的 prompt cache 是 0% | 已關閉：#6257、#6284。實測已命中 |
| #6198 | P2 | Codex 用 GPT-5 時失去 `apply_patch` | 已關閉：#6255、#6283；翻譯出口與 namespace 那一半由 #6360 補上（沒重開 issue） |
| #6201 | P2 | Claude 當 judge 拿不到有效判定 | 已關閉：#6242。實測 5/5 |
| #6202 | P2 | provider 帳號沒 credit 時不 failover | 已關閉：#6249、#6267。用真的沒額度帳號實測通過 |
| #6204 | P2 | tool result 裡的圖片變成文字或不見 | 已關閉：#6250、#6288。實測通過 |
| #6205 | P2 | Bedrock 把多 part 的 user content 轉成 JSON 文字 | 已關閉：#6247。**只有測試證明**：pool 沒有 Bedrock 模型 |
| #6199 | P3 | Bedrock 的 Claude 可能丟 Claude Code 的 system prompt、讀不到 cache | **仍開著**（0 則留言，最後更新 10-08）：程式修正已隨 #6247 合併，Bedrock 要等有憑證才能實測 |
| #6200 | P3 | `/v1/messages` 的 422 被標成 `api_error` | 已關閉：#6239。實測通過 |
| #6206 | P3 | client 沒送 temperature 時送出 0.7 | 已關閉：#6240。實測通過 |
| #6217 | P3 | 送上 Responses wire 的非 function 工具被無聲剝除 | 已關閉：#6253、#6290。實測通過 |
| #6299 | P2 | `/v1/messages` 把不認得的 typed tool 偷偷改成 function | 已關閉（10-11）：#6300。真 Claude Code 實測通過 |
| #6353 | P2 | usage-ledger 的 pre-flight 寫入等 30–54 秒才回 503，沒設預算也一樣（Budget，assign silvia） | 已關閉（10-13 10:15）：#6397，改成最多等 2 秒、失敗記住 10 秒。**issue 要求的另一半沒做**：寫不進帳時依 tenant fail mode 放行，要先修 ADR-423／SPEC-215 C-215-82 |
| #6354 | P2 | 預算／額度用完回 429，Claude Code 空轉約 3 分鐘、OpenCode 睡到週期結束（Budget，assign silvia） | 已關閉（10-12 18:00）：#6367，改回 400；rate 與 concurrency 限制維持 429。驗收第 1 項（三個真 CLI 對用完的預算跑一次）沒跑 |

共 14 張，13 張已關閉，只剩 #6199。10-12 報告的發現只有 Budget 那兩項開成 issue；§2.1.2、§2.1.3、§2.1.5、§2.1.6 與 10-12～13 的 18 支 PR 都沒有另開 issue，直接以 PR 交付。

**仍開著的 PR**（#6376 已在 10-13 13:48 合併，`ed7790fde`，從這張表移除）：

| PR | 分支 | 狀態 |
|---|---|---|
| #5640 | `feat/iam-usage-rollup-switch-r2` | draft，IAM 的 usage rollup R2，不屬這條線 |

**沒有 PR 的分支**：

| 分支 | 內容 | 狀態 |
|---|---|---|
| `claude/gifted-shamir-220761`（head `775919ad8`） | routing 的 request context 只讀有界的一段 body：`prompt_token_estimate` 超過 32,768 字元時取樣估算並標 `prompt_token_estimate_sampled`；移除沒有策略在讀的五個訊號。ADR-285 Amendment A、SPEC-276 Rev.20（main 上留著這個空號） | 自己的 commit 3 個（另 5 個是 #6347 的原始 commit，已在 main）；落後 main 50 個。試合併有 6 個檔衝突（`CLAUDE.md`、`gateway-ci-suite.txt`、`gateway/routing_adapter.py`、`tests/unit/test_routing_adapter.py`、Core-ADR-01、SPEC-264）。合併時它的 `_count_text_tokens` 要改成 `max(1, count_tokens(text))`（ADR-419 已寫明）。本機 worktree 在 `.claude/worktrees/gifted-shamir-220761`。**已被 #6459 取代**（10-13 代為決定；#6459 不取樣、改成移出 event loop；遠端分支保留不刪） |

10-12～13 那 18 支 PR 的 head 分支（`claude/busy-maxwell-662cd8` 等）都還在遠端：這個 repo squash 後不刪分支，內容都已在 main，可以不管。合併用的 `mergetrain/*` 分支與暫存 worktree 已清掉。

**其他相關、仍開著的 issue**：#2783（Phase 4a，能力資料改由 IAM catalog 提供）、#2634（tool-type 授權 policy；namespace 成員的 Tool 規則最接近這條線）、#6228（Xparse tools 在 chat／messages，另一條軸）。**還沒有 issue 的**：namespace 成員的名稱規則（#6360 留下的治理缺口）、清理已終止 app 的 ResponsesBinding、§3.2 列的未開工項目。

### 3.4 延後的設計工作

| 項目 | 等什麼 |
|---|---|
| 能力資料改由 IAM catalog 提供（INV-323-2，#2783） | Phase 4a。入口資格與工具／檔案的模型判斷在 `translation/capabilities.py`（G1 鎖住）；OpenAI 家族的請求形狀在 `backend/openai_model_family.py`（#6331 把三份互相矛盾的名單收成一份）；Claude 的現行家族已由 #6452 改成版本規則（`backend/param_capabilities.CURRENT_CLAUDE_SURFACE_RE`） |
| 只靠設定就能新增 provider | Phase 4b |
| Bedrock、Gemini、Foundry 的 codec，以及它們的 thought signature | Phase 4c |
| 把 OpenAI 的 `encrypted_content` 放進 Claude Code 的 thinking `signature` | Phase 4 |
| messages 回應側的原生串流 | ADR-503 延後；ADR-239 D2 的 buffer→finalize 維持不變。#6329 只補了生成期間的 ping |
| `/v1/messages` 逐段輸出文字 | 非 Claude 已完成（#6475）；Claude 與 Bedrock／Vertex 上的 Claude 維持整回合（10-13 代為決定，ADR-239 Amendment C） |
| `/v1/responses` 非串流（收集器） | 尚未開工 |
| 輔助請求跟著 session 釘住的模型 | owner 已決定，尚未開工 |
| tier escalation 開著時，工具迴圈沿用該輪的 judge 判定 | owner 待決（SPEC-290 C-290-13 沒有區分新提問與 tool result 續傳） |
| Tool 規則的名稱規則涵蓋 namespace 成員（MCP、sub-agent、code mode） | ADR-490 Q15／SPEC-304 OQ-S14；先用 `tool_namespace` 的紀錄做普查。還沒有 tracking issue |
| PDF 內容的 rail、計價與頁數估算 | owner 10-12：之後補 |
| `/v1/chat/completions` 開放 `type: file`；Bedrock／Google 的檔案 part | 產品決定 |
| DeepSeek 等 OpenAI 相容端點的 `developer`／無型別 schema 正規化 | DeepSeek 已完成（#6452）；其他相容端點仍不在範圍 |
| OpenAI 推理家族在 reasoning 關閉時轉送 sampling | 要有每一代的預設 effort（#6331 未做） |
| `XPARSE_HEURISTIC_COUNT_LONG_RUNS` 翻成預設開；heuristic 對 Claude／Gemini 池的取捨 | ADR-419 OQ-5；#6377 的五個選項 |
| guardrail 偵測面上限（agent 迴圈）、provider client 重用、IAM 記憶體成長 | 尚未開工 |
| hosted 工具的租戶層級開關（`tool_types`） | ADR-490 Rev.15 延後；目前沒有任何關閉開關 |
| hosted 工具受 Tool 規則／tool-type 授權管轄 | #2634 |
| Azure 的 web_search、namespace／tool_search 判斷、D17 | 等 pool 有 Azure 模型實測 |
| 有狀態 Responses 的未來選項 | `store:true` 改成看得見的降級，或擴大有原生 Responses 狀態的 provider；現行 400 維持 |
| 帶 `custom` 的請求在路由時偏好吃得下的模型 | 產品決定 |
| chat 入口驗證 400 的關聯 header | 跨入口決定 |

已完成、從這張表移除：hosted 工具同家族原生（#6313、#6315、#6316；跨家族映射已否決）；Codex 的 `namespace`／`tool_search`／`custom` 在翻譯出口（#6360）；`/v1/messages` 的 document（#6359）；routing 的整段估算移出 event loop（#6459，取代分支 `claude/gifted-shamir-220761` 的取樣做法）。

### 3.5 測試留下的狀態（2026-10-13 唯讀核對，10-14 補上 dev stack 與實測留下的物件；要不要還原請你決定）

- **KEY2 的 app**（`name` 是 `gpt-4o`，`application_code` 是 `gpt_4o_816e`，`5260605d-…`）：
  - `llm_judge_routing`、`routing_objective=quality`、`session_affinity_enabled=true`、`session_affinity_tier_escalation=true`、`select_available=true`；`routing_parameters` 有 `judge_timeout_ms=10000`、`reliability_tier_threshold=0.5`、`keyword_tier_rules_enabled=true`。
  - **judge 已改釘 `baad099f`（deepseek-flash）**：owner 在 10-12 12:08 改的。它是 pool 成員、healthy。原本的 `8222876c`（openai `gpt-4o`，顯示名 `gpt-4o-peter-123`）還在、healthy、不在 pool。10-12 第一輪就是因為舊設定讓 judge 一次都沒判過，第二輪前才換的。
  - app 綁的是 proxy `841deb51`（"gpt-4o (proxy)"）。
  - policy：有效綁定只有 tenant 層的兩筆（`builtin-judge-probe-bundle-a1`、`tenant-default-rate-limit`）；application 層 119 筆全部 disabled。
- **pool 現在 4 個模型**（model-order `customized=true`）：

  | 序 | 模型 | 憑證 | 難度級 | 狀態 |
  |---|---|---|---|---|
  | 0 | claude-haiku-5-5 | peter-claude | REASONING | healthy |
  | 1 | gpt-6-luna | openai-guardrail | COMPLEX | healthy |
  | 2 | deepseek-flash | peter-test-deepseek | MEDIUM | healthy；**未定價** |
  | 3 | gpt-5.6-luna | openai-guardrail | SIMPLE | healthy |

  - **沒額度的 claude-sonnet-5-5 已暫停**（source `a80306fc`，模型 `eb98b151`，顯示名 claude-sonnet-5-5-peter-no-money）：10-12 第二輪開始前暫停。模型本身仍 unhealthy（`Endpoint returned HTTP 400`，最後檢查 10-13 12:32）。
  - 暫停讓分級重排：暫停前 deepseek-flash 是 COMPLEX（offset 1）、gpt-5.6-luna 是 MEDIUM、sonnet 是 SIMPLE（快照 `results/e2e_20261012/round2/app_before.json`）。
  - **這個暫停是 proxy 層的**：IAM 顯示 proxy `841deb51` 有 15 個 consumer，其中 active 的 app 只有 3 個（`gpt_4o_816e`、`peter_test_dorian`、`peter_test_gpt`），另 2 個 suspended、10 個 terminated（10-13 讀到的數字；#6515 起 IAM 的 active consumer 數與 code 清單排除已終止的 app）。還原：`POST /iam/applications/841deb51-9b12-4efc-8be3-14530ef10d0e/model-sources/eb98b151-fe79-4f9b-86c0-3e82b2d50194/resume`。
  - deepseek-flash 的價格只有一段（2026-09-18 到 09-30），之後沒有接續，現在是未定價；它同時是 judge 與 MEDIUM 級的模型，所以 judge 的用量有入帳但金額是 0。
  - pool 沒有 Responses-only（`openai_responses`）模型，也沒有 Bedrock、Azure、vLLM。
- **Anthropic 額度**：
  - no-money 那把從 10-11 起沒額度；10-13 的 IAM 連線檢查仍是 HTTP 400。Sonnet 與 Opus 因此還是測不到。
  - 「`anthropic_api_key3` 就是 no-money-peter 憑證」這個對應**沒驗證**（要讀密鑰值才能比對）。
  - IAM 憑證 `claude-api-june` 沒額度，#6202 就是用它實測的。
- **10-12 guardrail 線留下的 IAM 物件**（都已停用，IAM 沒有硬刪的路）：probe app `2e6a75b9`（`e2e1012_guardrail_101640_probe`，terminated）、key `e9634f11`（revoked）、policy `3bf2f92b`（軟刪，11 個 version 列還在）、bundle `958f7549`（軟刪）、兩筆 application 層 binding（disabled）。這個 probe app 在 10-13 還算在 proxy `841deb51` 的 15 個 consumer 裡；#6515 起已終止的 app 不再算進 active consumer 數。沒有建立 model、credential、proxy。
- **10-14 實測留下的**：另外建立了 11 個 probe application 與 proxy，都已 terminate、key 已 revoke；tenant 裡留下幾組已停用的測試 policy 物件與兩顆軟刪除的模型。KEY2 app 的路由設定、model order、有效綁定測後讀回與測前相同（rdy_20261014 REPORT §6）。
- **dev 上有 4 顆刪不掉的 probe 模型**（10-13 確認還在，都在 Notification Local Test 群組、healthy、enabled）：`aecb6959` p8 gpt-5.4 1007231416、`b1663dde` p8 gpt-5.4 1007233110、`0fe3741b` p8 gpt-5.4 1008000921、`2354833d` gpt-5.4-resp-probe-1005103932。原因（被原生回合寫入的 ResponsesBinding 擋住、所屬 app 已終止、IAM 沒有清理路徑）**沒重驗**，因為要真的刪。**還沒開 issue**。
- **本機 dev stack 跑的是最新 main**：
  - 主 checkout HEAD = origin/main = `ee1a40564`。gateway 與 IAM 容器在 10-14 19:17 重建，所以到 #6515 為止的修正都在跑（10-13 的紀錄：整組容器 10-13 12:31 重建；`xparse-guardrails` 與 `xparse-gliner` 兩個 sidecar 會起來，gliner 佔約 2.1 GiB，會擠壓下面說的 7.65 GiB VM；程式碼是唯讀掛載的）。10-12～13 新增的環境變數一個都沒設，全部跑預設。
  - image 仍是 `xparse-scr:celery-local`（`55a94bc10419`）。這個 image 沒有 tiktoken，token 計數走 heuristic，跟 production 的路徑不同。
  - 信封金鑰已自動產生，10-14 重建後不變：`/v1/health` 的 `translation_envelope` 是 `state=on`、`source=file`、kid `a202610120202`（10-12 10:02 產生，放在 volume `xparse_xparse-routing-db`）。容器裡 `XPARSE_TRANSLATION_ENVELOPE_SECRET` 是空值，等同沒設。
  - 本機 IAM 的 migration 應該已套到 `0387`，待核對（10-13 是 `0381`）。
  - `3rd/xparse_audit` submodule 本機是 `123b6701`（10-02），main 釘的是 `999cef9e`（#6366，10-12 bump），本機連這個 commit 都還沒抓；IAM 有掛它的 `src`，所以本機 IAM 跑的是舊的 Audit SDK。
  - Docker VM 只有 7.65 GiB：`xparse-audit` 啟動要約 3 GiB，IAM 的記憶體一長大，audit 就會被 OOM kill 反覆重啟（10-12 第二輪發生過，重啟 `xparse-iam` 後恢復）。
- **暫存 worktree**：`git worktree list` 共約 308 個，`.claude/worktrees/` 下 83 個。與這條線有關的：`gifted-shamir-220761`（沒有 PR 的那條分支）、#6376 的 `distracted-swartz-356929`，以及 10-12～13 那 18 支已合併 PR 各自的 worktree（都還在，內容已在 main）。10-11 session 另留兩個在 repo 外的 session 暫存目錄（`wt-meter-nulluq`，分支 `fix/meter-nulluq-tmp`；`wt6313`）。10-12～13 合併用的 worktree 與 `mergetrain/*` 分支都已清掉。
- **repo 外的檔案**（`/Users/peter/Desktop/testing/`）：`e2e1012_*.py` 533 支、`e2e1012_finish_merge_train.sh`（merge train 的收尾腳本）、`results/e2e_20261012/`（2.7 GB、約 73,000 個檔案，主要是 wire 錄檔）。10-09 的在 `e2e1009_*.py`、`results/e2e_20261009/`。沒有殘留的 probe gateway 容器。

### 3.6 需要你決定或點頭的事

1. ~~**#6376**~~：已合併（`ed7790fde`）。
2. **rel／prod 的部署時程與順序**（§3.1）：rel（v1.77.0.16）照 IAM 先即可，一次套 19 支 migration；prod 要在 IAM 先（#6316 的規則，也是部署腳本的順序）與 gateway 先（ADR-269 的規則）之間選一邊並接受它的空窗；`0378` 的低流量時段。上線前要不要再用三個真 CLI 跑一輪（10-14 已在 `bff643332` 跑過一次，之後的 11 支沒有整體重跑）。
3. **escalation 開著時，工具迴圈的後續請求要不要沿用該輪的 judge 判定**（現在每個請求都重判，§3.2）。建議沿用：判的是同一句話，重判只增加延遲與判定雜訊。要改 SPEC-290 C-290-13。
4. ~~**`claude/gifted-shamir-220761` 要不要開 PR**~~：已被 #6459 取代；遠端分支要不要刪由你決定。
5. **還沒開工的項目要不要排、先後順序**：guardrail 偵測面上限（agent 迴圈）、`/v1/responses` 非串流、輔助請求跟著 session 的模型、provider client 重用。
6. **namespace 成員納入 Tool 規則**：#6360 先照送、之後補；還沒有排程，也沒有 issue（最接近的是 #2634）。要不要開一張。
7. **`XPARSE_HEURISTIC_COUNT_LONG_RUNS` 何時翻成預設開**（ADR-419 OQ-5）；#6377 的五個選項要不要選。
8. **測試 app 要不要還原**（§3.5）：judge 留在 deepseek-flash 還是改回；proxy `841deb51` 上暫停的 sonnet 要不要 resume；deepseek-flash 要不要補一段價格。
9. **#6199／#6205 的 Bedrock 實測**：給一組 Bedrock 憑證、加進 pool，就能測完並關掉 #6199。
10. **Sonnet（與 Opus）的 hosted 驗收**：等有額度的 key 再跑強制 `tool_choice`。
11. **hosted 工具的租戶關閉開關**：目前沒有，ZDR／HIPAA 租戶排除不了（§3.2）。
12. **#6353 沒做的那一半**：寫不進帳時要不要依 tenant fail mode 放行。silvia 判定要先修 ADR-423；要不要推。
13. **Console 的 Current Spend 卡片**：要不要開 PR 把搜尋費列出來並補上型別。
14. **要不要開 issue**：串流 4xx 變 200＋SSE error；4 顆刪不掉的 probe 模型（ResponsesBinding 清理）；10-12 報告 §4 的兩處金額算錯。
15. **Codex 的使用說明**：三個 CLI 的接入說明已有 `docs/runbooks/agent-cli-setup.md`（#6453 新增，#6498 依 10-14 實測更正，#6514、#6516 補了輸出上限與接續的說明），repo 內找不到依據的項目標成「未驗證」。仍缺的：code mode 下 Codex 不送 `web_search`、要覆寫 catalog 的作法（runbook 把 `model_catalog_json` 標成未驗證）。要不要補，或整理成對外文件。
16. **§3.4 兩個待決的設計**：帶 `custom` 時路由偏好吃得下的模型；chat 驗證 400 的關聯 header。
17. **Discussion #2527 要不要回文更新進度**（目前只有 07-25 一則留言）。
18. **`results/e2e_20261012/`（2.7 GB）與暫存 worktree（`.claude/worktrees/` 下 83 個，§3.5）要不要清**。

已決定（10-12～13）：

- 使用者看得到的功能優先；稽核、計價、guardrail 的細節之後補。
- Codex 的 namespace 工具、client `tool_search`、code mode、`apply_patch` 歷史現在就照送；Tool 規則涵蓋 namespace 成員之後再做（#6360，推翻 ADR-490 Q1 的 namespace 部分）。
- `/v1/messages` 的 PDF 原生轉送，接受它是 rail 盲點（#6359）。
- 工具呼叫的參數審視不擋回合（#6363）。
- session 升級維持只升不降（ADR-447 不改）。
- 輔助請求跟著 session 釘住的模型（方向已定，還沒做）。
- Budget 的兩項交給 silvia（#6353、#6354，都已結案）。

已決定（10-10～11，維持）：`stateful_responses_unsupported` 的 400 維持；web_search／web_fetch 預設開、不 opt-in、不加網域白名單或平台上限；只走同家族原生；responses 採 R-strip；接受 guardrail 盲點；計量只記錄不擋；撤回 hosted 專屬的資料邊界／再出網／live_access 閘門；信封金鑰由 gateway 在共用 volume 自動產生。

（只升不降、輔助請求、工具迴圈待決這三項，repo 裡沒有對應的決策文字：輔助請求與工具迴圈待決記在報告 §11；只升不降維持的決定只在 10-12 的對話裡，報告 §10.2 只把它列為問題。）

---

## 4. 程式與文件位置

路徑沒寫前綴的都在 `apps/gateway/bustream/` 之下（`tests/…` 也是）。例外：`.github/`、`packaging/`、`tools/`、`deployments/`、`docs/`、`tests/deploy/` 開頭的在 repo 根目錄；標「IAM」的列裡，`authorization/`、`migrations/` 在 `apps/iam/xparse_iam/xparse_iam/` 之下，測試在 `apps/iam/xparse_iam/tests/` 之下；`openai_worker.py` 是 `streaming/workers/openai_worker.py`。

| 東西 | 位置 |
|---|---|
| 中介格式、處置表、能力表 | `translation/{items,dispositions,capabilities}.py` |
| codec | `translation/codecs/{openai_responses,chat_pivot}.py` |
| Responses 事件合成 | `translation/stream/{chat_pivot_decoder,responses_renderer}.py`、`streaming/workers/translating_responses_worker.py` |
| 信封、thinking 簽章 | `translation/{envelope,thinking_signatures}.py` |
| 信封金鑰來源與狀態（#6302） | `gateway/envelope_key_source.py`；`/health` 組裝在 `gateway/translation_output.py::envelope_health`、`gateway/routes/health.py`；gauge 在 `observability/metrics.py` |
| 信封金鑰佈建（#6302） | `packaging/installer/install.sh`、`tools/xdeploy/install_service/web/installer.py`、`deployments/operations/scripts/blue-green-deploy.sh::translation_envelope_preflight`、`tests/deploy/test_envelope_preflight.sh`、`docs/runbooks/translation-envelope-secret.md` |
| 原生直送 | `translation/{native_delta,native_body,native_sampling}.py`、`gateway/native_messages.py` |
| 每次嘗試的判斷（seam、翻譯、原生） | `gateway/worker_setup.py`（`_backend_config_from_assignment`） |
| 稽核與 header | `gateway/translation_audit.py` |
| typed tool 分類與 hosted 判定（messages，#6300、#6315） | `gateway/anthropic_translation.py`（`TYPED_TOOL_FAMILIES`、`HOSTED_WEB_TOOL_FAMILIES`、`is_hosted_web_tool`、`refuse_typed_tool`） |
| hosted 回程 block 重建（#6315） | `translation/hosted_blocks.py`（`rebuild_hosted`） |
| hosted 的原生判斷與拒絕（#6315） | `gateway/native_messages.py`（`_masks_native`、`HostedToolNotNative`、`hosted_tool_refusal`）、`gateway/addressing_refusals.py`（`HOSTED_TOOL_UNSUPPORTED`、`refuse_hosted_tool_not_native`）、`translation/native_delta.py::text_substitutions`、`translation/native_body.py::apply_text_substitutions` |
| hosted 能力判斷（#6313、#6315） | `translation/capabilities.py::accepts_hosted_web_tool`、`accepts_hosted_web_search`、`NEED_HOSTED_WEB_TOOL`；Responses 剝除 `gateway/responses_tools_filter.py` |
| hosted 計量（gateway，#6316） | `streaming/hosted_tool_usage.py`、`gateway/usage_ledger_hook.py::record_hosted_tool_calls_to_ledger` |
| hosted 計價（IAM，#6316） | `apps/iam/xparse_iam/xparse_iam/db/models/hosted_tool_price.py`（`HostedToolPriceVersion`）、`authorization/usage_pricing.py`（`cost_hosted_tools`）、`migrations/0378_adr489_hosted_tool_usage_meter.py` |
| tool result 圖片搬移（#6204） | `translation/tool_result_images.py`（#6359 起 tool result 裡的檔案也跟著搬） |
| Claude 結構化輸出（#6201、#6287） | `streaming/workers/_anthropic_output_format.py` |
| Bedrock content block（#6205） | `streaming/workers/_converse_content.py` |
| 快取意圖（#6196、#6284） | `gateway/prompt_cache_intent.py`、`gateway/worker_setup.py` 的 `_resolve_prompt_cache_key_intent`／`_resolve_cache_control_markers` |
| 帳號沒額度的判斷（#6202） | `streaming/workers/errors.py::is_provider_account_unavailable`、`gateway/fallback_handler.py::effective_error_code` |
| 模型吃不吃 `custom`（#6283） | `translation/capabilities.py::accepts_custom_tools` |
| `/v1/messages` 的 `ping` 節奏（#6329） | `gateway/routes/messages.py`（`_PING_INTERVAL_SECONDS`、`_chunk_arrives_within`） |
| `thinking` 的鍵與 `block_binding`（#6329） | `translation/native_sampling.py`（`THINKING_KEYS`、`BLOCK_BINDING`）、`translation/native_body.py`（`BETA_ALLOWLIST`、`THINKING_BINDING_BETA`） |
| chat 訊息形狀送 Claude／Bedrock（#6330） | `translation/chat_message_shape.py`（`system_text`、`tool_input_schema`、`chat_shape_facts`）；紀錄在 `gateway/worker_setup.py`（`CHAT_SHAPE_DIVERGENCE = "D16"`） |
| OpenAI 家族判斷（#6331） | `backend/openai_model_family.py`（`is_openai_reasoning_family`、`chat_output_cap_field`、`LEGACY_GPT_MAJORS`）；讀它的有 `streaming/workers/base_worker.py::is_reasoning_model_name`、`openai_worker.py`、兩個 Responses worker、`backend/responses_bridge.py`、`backend/param_capabilities.py`（D17）；IAM 鏡像 `apps/iam/xparse_iam/xparse_iam/domain/value_objects/provider_surface.py::probe_request_shape_class` |
| 串流 idle deadline 量上游（#6348） | `streaming/upstream_activity.py`（`UpstreamActivity`）、`provider_http.py::provider_async_client(activity=...)`、`gateway/streaming_deadline.py`（`StreamingIdleBudget`、`IdleDeadlineExceeded`、`drive_with_idle_deadline`）、`gateway/responses_idle_deadline.py`、`gateway/non_streaming_handler.py`（推理模型的非串流總時限） |
| Responses 歷史跨家族（#6338） | `translation/item_ids.py`（`gateway_reasoning_id`、`is_gateway_reasoning_id`）、`gateway/responses_pipeline.py::native_input_items`、`gateway/request_fields.py::encrypted_reasoning_scope`、`gateway/responses_resilience.py` |
| routing 分級的上限（#6347） | `gateway/complexity_classifier.py`（計分視窗、`CAUSE_SINGLE_CANDIDATE`）、`gateway/tier_judge_prompt.py`（judge 的 ask 上限）、`gateway/route_resolution.py`；event loop 延遲監看 `observability/event_loop_lag.py` |
| billing 行不進 session affinity key（#6356） | `billing_header.py`（`split_billing_header`）、`production/prefix_affinity.py::system_prefix_text` |
| 不動健康分數的失敗碼（#6362） | `production/health_tracker.py`（`HEALTH_NEUTRAL_FAILURE_CODES`）、`gateway/responses_execution_audit.py::emit_responses_execution_failed` |
| tool call 參數審視（#6363） | `gateway/tool_call_validation.py`（`review_tool_calls`、`ToolCallReview`）、`gateway/non_streaming_handler.py`、`gateway/routes/{chat,chat_streaming_audit,messages}.py` |
| `/v1/messages` 的 document／PDF（#6359） | `translation/messages_view.py`（內容 block 的視圖，入口翻譯與原生 body 都讀它）、`models/multimodal.py::FileBlock`、`translation/capabilities.py`（`NEED_FILE_INPUT`、`accepts_file_input`、`accepts_file_url_input`）、`gateway/addressing_refusals.py`（`DOCUMENT_UNSUPPORTED`）、`gateway/native_messages.py`（`UNREAD_PARTS_FIELD`） |
| 回送 thinking 的前綴綁定（#6361） | `translation/thinking_binding.py`（`controls_apply`、`with_controls`、`without_thinking`、`disposition`）、`streaming/workers/anthropic_worker.py`、`production/retry.py`、`translation/codecs/chat_pivot.py` |
| Codex 的 namespace／tool search／custom（#6360） | `translation/tool_shapes.py`（`ToolNameTable`、`name_table`、`declared_members`）、`translation/capabilities.py`（`accepts_namespace_tools`、`accepts_tool_search`）、`streaming/workers/azure_responses_worker.py`（`sent_tool`、`tool_gates`）、`streaming/workers/responses_tool_items.py`、`gateway/responses_tools_filter.py`、`gateway/responses_tool_governance.py`、`gateway/tool_governance_response.py`、`translation/codecs/openai_responses.py`、`translation/stream/responses_renderer.py` |
| tool search 回合不算空回答（併在 #6360） | `gateway/responses_tool_calls.py`（`ToolCallRecorder.output_calls`）、`gateway/responses_stream.py` |
| token 計數（#6374、#6375、#6378、#6380、#6382） | `gateway/token_estimate.py`（`start_request_counts`、`count_ahead`、`estimate_prompt_tokens_off_loop`、`estimate_for_client`）、`tokenizer.py`（`count_tokens`、`heuristic_token_count`、`counts_long_runs`）、`gateway/dispatch_pipeline.py`（`_start_prompt_counts`）、`gateway/routing_adapter.py::estimate_prompt_tokens` |
| Budget 用完的狀態碼、pre-flight 時限（#6367、#6397，silvia） | `gateway/admission_handler.py`（`BUDGET_EXHAUSTED_STATUS`）、`production/budget_usage_retry.py`、`production/quota_counter.py` |
| 輸出上限的來源與 Claude 上限查詢（#6514） | `output_cap.py`、`streaming/workers/_anthropic_output_ceiling.py`、`context/request_params_context.py`（`exec_max_tokens_source`） |
| prefill 接續（#6516） | `translation/trailing_assistant.py`（`CONTINUATION_TEXT`、`REASON_PREFILL_UNSUPPORTED`）、`streaming/workers/base_worker.py`（`PREFILL_CONTINUED_SIGNAL`）、`streaming/workers/anthropic_worker.py` |
| DeepSeek D18（#6503） | `backend/param_capabilities.py::is_forced_tool_choice` |
| `json_schema` 需求（#6512） | `translation/capabilities.py`（`JSON_OBJECT_ONLY_PROVIDERS`、`accepts_json_schema_output`） |
| `/v1/messages` 逐段送出（#6475） | `gateway/messages_incremental.py`（`declare_append_only`） |
| client 身分（#6446） | `gateway/client_profiles.py` |
| 沒讀過的 part／item（#6463、#6511） | `gateway/unread_parts.py`、`gateway/responses_item_surface.py` |
| 候選池紀錄（#6459） | `gateway/surface_pool.py` |
| R3 的 Kernel 紀錄（#6461） | `gateway/failover_boundary_record.py` |
| 回應端登記表（#6474） | `gateway/response_checks.py` |
| 工具扁平名稱（#6465） | `audit/tool_flat_name.py` |
| 不得靜默丟的矩陣（#6476） | `tests/contract/provider_param_matrix.py`、`tests/contract/no_silent_drop_baseline.py` |
| 矩陣宣告 | `tests/conformance/translation_matrix.py` |
| 主要整合測試 | `tests/integration/test_{translation_2a,responses_translation,messages_thinking_signature,messages_native_passthrough,translation_matrix_cells}.py` |
| 10-11～12 新增的測試 | gateway 整合：`tests/integration/test_{messages_typed_tool_classification,messages_hosted_web_tools,responses_web_search_native}.py`；gateway 單元：`tests/unit/test_{hosted_blocks,translation_envelope_key_source,translation_envelope_visibility,translation_capabilities_hosted,hosted_tool_usage_meter}.py`；IAM：`apps/iam/xparse_iam/tests/unit/test_hosted_tool_pricing_golden_vectors.py`、`tests/integration/test_hosted_tool_{usage_meter,meter_migration_compat}.py` |
| 10-12～13 新增的測試（都在 `tests/`，都登記在 `gateway-ci-suite.txt`） | #6329：`integration/test_{messages_keepalive_while_generating,native_thinking_binding_oc12}.py`。#6330：`contract/test_chat_shapes_reach_claude.py`、`integration/test_chat_shapes_to_claude_d16.py`、`unit/test_chat_message_shape.py`。#6331：`integration/test_openai_family_wire_shape.py`、`unit/test_openai_model_family.py`。#6348：`integration/test_idle_deadline_upstream_liveness.py`、`unit/test_streaming_idle_liveness.py`。#6338：`integration/test_responses_cross_family_history.py`、`unit/test_translation_item_ids.py`。#6347：`test_spec264_rev14_bounded_scoring.py`、`unit/test_event_loop_lag_monitor.py`。#6356、#6362：加在 `contract/test_spec290_session_affinity_contracts.py`。#6363：`integration/test_tool_call_arguments_passthrough.py`。#6359：`integration/test_messages_documents.py`、`unit/test_messages_view.py`。#6361：`integration/test_responses_thinking_prefix_binding.py`、`unit/test_thinking_binding.py`。#6360：`integration/test_responses_namespace_tools.py`、`unit/test_translation_tool_shapes.py`；tool search 回合不算空回答的測試加在既有的 `integration/test_tool_call_turn_not_content_empty.py`（#6280 建立）。token 計數：`contract/test_spec270_{prompt_count_once,heuristic_long_runs,heuristic_segments,readers_that_wait}.py`、`integration/test_prompt_count_{once_real_routes,readers_real_routes}.py`、`unit/test_tokenizer_encoder_refusal.py`、`test_spec276_rev21_routing_estimate_counter.py` |
| gate | `.github/scripts/translation-{core-purity,dispositions,matrix-completeness}-gate.py`、`envelope-single-owner-gate.py`、`azure-request-shape-class-parity-gate.py`（#6331 改寫）、`failure-health-attribution-gate.py`、`provider-roster-parity-gate.py`、`response-checks-gate.py`、`ledger-producer-parity-gate.py`（#6469 擴大）；金鑰 preflight 與 tokenizer 的兩支 gate 寫在 `ci.yml` 的 static-gates 裡 |
| 實測腳本（repo 外） | `/Users/peter/Desktop/testing/`：`p0_claude_code_cache_baseline.py`、`agent_e2e_key2.py`、`p9_*_probe.py`；10-09～10 的 `e2e1009_*.py`；10-12 的 `e2e1012_*.py`（533 支，第二輪是 `e2e1012_r2_*`；app 設定快照與還原 `e2e1012_r2_app_setup.py`；冒煙 `e2e1012_smoke.py`）；`e2e1012_finish_merge_train.sh` |
| 實測報告（repo 外） | `/Users/peter/Desktop/testing/results/e2e_20261009/REPORT.md`；`/Users/peter/Desktop/testing/results/e2e_20261012/REPORT.md`（§0–§9 第一輪與審查、§10 第二輪、§11 修正與合併狀態；原始結果 `live_workflow_result.json`、`review_workflow_result.json`、`round2/round2_workflow_result.json`、五家對照 `reference/*.json`）。報告 §11 寫於 #6382 合併、#6353／#6354 關閉之前，以本文件為準。10-11 驗收紀錄只在 session 暫存輸出，沒搬進來 |
