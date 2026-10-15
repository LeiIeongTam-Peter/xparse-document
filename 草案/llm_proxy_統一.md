# LLM Proxy 統一：任何 agent 都能用任何 provider 的模型（草案 Rev.4）

> **狀態（Rev.4，2026-10-08）**：**已轉為正式文件**——PRD-350、ADR-503、SPEC-312（`docs/`，以那三份為準）；P1–P9 全部合併（P9 #6218 `b32114bc5`，2026-10-08）。本檔只留作歷史與交接脈絡；與正式文件衝突時一律以正式文件為準。對照見附錄 E Rev.4。
> **原狀態**：草案，不是 ADR。用途有兩個：(1) 給 Peter 決定方向（§14）；(2) 給接手實作的 agent 當完整交接（§9、§15、附錄 A）。核定後拆成 PRD／ADR／SPEC 與 issue（§9 Phase 1）。
> **日期**：2026-10-07（Rev.3：併入同日的 surfaces lane 測試報告；Rev.2、Rev.1 同日稍早）
> **基準**：`origin/main` `4a4a93331`。本文所有 xparse 路徑與行號都在這個 commit 上重讀過（Rev.3 新增的也是；到 `b5e168cca` 為止 `apps/gateway` 沒有變動）。**開工前先跑 `git fetch origin && git rev-list --count HEAD..origin/main`，不是 0 就重新核對行號。**
> **路徑縮寫**（repo 根目錄 `/Users/peter/Desktop/X-parse/xparse`）：
> - `GW/` = `apps/gateway/bustream/gateway/`
> - `BS/` = `apps/gateway/bustream/`
> - `BE/` = `apps/gateway/bustream/backend/`
> - `WK/` = `apps/gateway/bustream/streaming/workers/`
> - `IAM/` = `apps/iam/xparse_iam/xparse_iam/`
> - `TST/` = `/Users/peter/Desktop/testing/`（repo 外，實測腳本與結果）
>
> 注意：Rev.1 的 `B/` 指 `backend/`，`LLM_api.md` 的 `B/` 指 `bustream/`。本文一律改用上面這組，不再用 `B/`。
>
> **相關文件**：
> - `docs/草案/LLM-api-重構.md`：ADR-494，統一「API 面 × 治理流程」（治理軸）。已核定，M0–M9 已 merge，尚未上 prod。
> - `docs/草案/解決-v1-response.md`：`/v1/responses` 的結構性落後。§2.3 協定本質差異、§8 本質限制、§15 LiteLLM 對照。
> - `docs/LLM_api.md`：ADR-494 交接文件（治理軸的現況、部署狀態、坑）。
> - `docs/LLM_PROXY.md`：模型定址（ADR-138）與路由的全程紀錄。§12 是 `/v1/responses`，§22 是 D10 bridge。
> - `docs/測試報告/llm-api.md`（Rev.3）：2026-10-07 surfaces lane 報告，六個 API 面 91 case 加 17 個修正的回歸。測的是治理軸，**沒有測任何跨 wire 的格子**；本文用到的事實整理在 §4.8。
> - 本文處理另一條軸：**「API 面 × provider」（翻譯軸）**。

---

## 目錄

- §0 三十秒版（給接手者）
- §1 白話版
- §2 想解決的問題與成功標準
- §3 名詞
- §4 現況（含程式證據）
- §5 既有決策與脈絡（§17.4 必須處理）
- §6 外部對照：五家平台怎麼做
- §7 目標架構（建議）
- §8 各路徑的處置表（草案，SPEC 的起點）
- §9 實作計畫（Phase、切片、要動的檔案、測試、退出條件）
- §10 防回歸 gate
- §11 測試計畫
- §12 ADR-093 compliance 預想
- §13 §17.4 Core 對比表（預填）
- §14 需要 Peter 決定的事
- §15 接手 agent 工作守則
- §16 風險與取捨
- 附錄 A 程式證據索引
- 附錄 B 實測證據
- 附錄 C 外部平台證據
- 附錄 D 相關 issue／discussion
- 附錄 E 修訂紀錄

---

## 0. 三十秒版（給接手者）

- **要做什麼**：讓任何 agent（Claude Code 講 Anthropic Messages、Codex 講 OpenAI Responses、OpenCode 講 OpenAI Chat）都能經 Xparse 使用任何 provider 的模型。以後新增 agent 協定或 provider 時，只要加一個 codec 或一筆資料，不碰治理核心。
- **現況**：chat 與 messages 一座島，responses 一座島（§4.2）。看起來「通」的格子也有隱性損失：Claude Code 打 Claude 時，thinking 簽章被丟、cache 斷點從 3 個縮成 1 個、`context_management` 被丟（§4.5）。
- **建議的方向**（§7，細節等 Peter 核定 §14）：
  1. 治理維持 ADR-494（吃各面 adapter 的視圖）。翻譯放在出口端。
  2. 單一中介格式：有順序的 item 模型，對齊 Open Responses 規格。
  3. 每種 wire 一個雙向 codec。
  4. 同家族優先原生直送：一律先解析給治理看，再送治理過的原生 body；寫不回去就走宣告過的退路，並記錄。
  5. 不透明狀態（簽章、加密推理）用加簽信封夾帶，出口主動剝除。
  6. 有狀態的 Responses 功能不模擬，用能力過濾候選，沒有候選就明確拒絕。
  7. 能力是資料。
  8. client 怪癖集中在一個模組。
- **不要碰**：ADR-494 pipeline 的 stage 順序與處置語意、四張「只記錄 → 執行」切換票（#5941、#5949、#5965、#5976）、chat SSE 狀態機（CLAUDE.md §7）、ADR-339 對 OpenAI 原生 Responses 的透明轉送。
- **開工順序**：先做 §9 Phase 1 的文件（RESEARCH → PRD → ADR → SPEC），再從 Phase 2a 最便宜的切片開始。每片都要有 §8.1 真元件證據。
- **最大的三個坑**：
  - ResponsesBinding **沒有**存對話內容（Rev.1 寫錯）。
  - gateway 在兩個方向都沒帶 thinking `signature`；而且 messages 面對**任何**推理模型（含 DeepSeek）都會回沒有簽章的 thinking block。只做 Claude Code 請求側的直送，會讓 Anthropic 拒絕 client 回送的無簽章或外家族 thinking（§4.5、§4.8、§9 Phase 3）。
  - **`/v1/responses` 今天只轉送 `function` 工具**（SPEC-304 S0-b）：Codex 的 `custom apply_patch`、`namespace` 在原生路徑也被剝除，Codex 改用 shell 改檔。開放這些型別是 ADR-490 Q1，還沒拍板；翻譯路徑不能比原生路徑放得更寬（§4.8、§8.1、§14 Q11）。
- **Rev.3 併入測試報告**（`docs/測試報告/llm-api.md`）：治理軸的地基是穩的（91 case 中 88 PASS、0 個真失敗；17 個修正全部 VERIFIED；每個請求恰好一個終端事件），但報告帶出十幾處要補的設計，摘要在 §4.8。

---

## 1. 白話版（給非工程讀者；PRD 的白話層可以從這裡改寫）

客戶拿同一把 Xparse 的 key，可能用 Claude Code、Codex、OpenCode，或之後出現的任何 AI 寫程式工具。背後接的模型可能是 OpenAI、Claude、DeepSeek，或客戶自己機房的模型。

我們要的是：**不管客戶用哪個工具、選哪個模型，都能直接用，而且公司的管控規則都一樣生效。**

現在的情況有兩個問題。

第一，有一塊是孤島：Codex 只能用 OpenAI 某一類模型，那類模型也只有 Codex 用得到。

第二，看起來能用的組合也可能「能用但打了折」。例如 Claude Code 透過我們用 Claude 時，對話歷史吃不到快取（成本較高），而且模型上一輪的思考過程沒有傳回去。

做法是在 Xparse 裡蓋一套「翻譯層」：
- 每種工具講的語言、每家模型講的語言，各配一個雙向翻譯器，全部翻成同一種內部格式。
- 同一家族就不翻，原文直送。
- 翻不過去的功能不會默默消失：要嘛模擬，要嘛明講不支援，要嘛拿掉並留紀錄。

以後新增工具或模型，只要加一個翻譯器或一筆設定。

---

## 2. 想解決的問題與成功標準

> 原始問題：「我們要不要做一個中間件來統一管理、防止 coupling？因為以後 agent 和 LLM provider 都可能會增加。」

| # | 要求 | 意思 |
|---|---|---|
| R1 | **任意組合可用** | 每個 agent（API 協定）× 每個 provider 的模型，都能經 Xparse 使用 |
| R2 | **擴充不碰核心** | 新增一種 agent 協定或一家 provider，只寫一個 codec（或一筆設定）和測試。治理核心不必改：政策、路由、admission、effort seam、稽核 |
| R3 | **同家族不打折**（Rev.2 新增） | agent 和模型同一家族時（Claude Code 打 Claude、Codex 打 OpenAI），保真度等同直連：快取斷點、思考簽章、加密推理、新 beta 都不丟。**治理刻意拿掉的不算**（Rev.3）：例如 Codex 的 `custom`／`namespace` 工具今天被 SPEC-304 S0-b 剝除，屬於 ADR-490 Q1 的範圍，不是翻譯問題（§4.8） |

成功標準（可驗收；PRD §4 從這裡改寫）：

- **S1 矩陣沒有空格**：相容性矩陣（§11.2）每一格都是「通」，或「明確宣告的不支援並附理由」，沒有「不知道」。**每一格要寫清楚測了哪些情境**，不能只寫 ✅。
- **S2 擴充成本可量測**：
  - 新增一家既有 wire 的相容 provider（例如另一家 OpenAI 相容廠商）：只改 IAM catalog 資料，加上 gateway 一筆「依 wire 選 codec」的設定。
  - 新增一種 wire：只新增一個 codec 模組、一列能力資料、矩陣一列。
  - CI 用 gate 檢查核心路徑沒有新增 provider 或 agent 名稱的特判（§10 G1）。
- **S3 沒有默默丟失**：任何翻不過去的欄位、content-part、工具型別或串流事件，處置必須是「翻譯／模擬／明確拒絕／剝除並記錄」之一（ADR-093 #4），而且**記錄要讓稽核和 client 都看得到**（§7.9）。
- **S4 走哪條路看得到**（Rev.2 新增）：每個請求的稽核都記錄 `translation_path`（native／native_rewritten／translated／bridged）與處置清單。走原生或翻譯不能因為治理設定改變而默默切換。這是 One-API 的教訓，見 §6.3。
- **S5 跨 provider 換手**（Rev.2 新增）：同一個 session 中途換到不同家族的模型（ADR-447 升級、R3 fallback）時，請求不會因為前幾輪的不透明狀態而 400。外家族的簽章或加密推理一律在出口主動剝除。
- **S6 同家族保真**（Rev.2 新增）：Claude Code 經 Xparse 打 Claude 的多輪 session 中，第 3 輪起對話前綴能命中快取（`cached_tokens > 0`），帶 thinking 的 tool loop 不會 400。
- **S7 回應層一致**（Rev.3 新增）：不論哪個面、走原生還是翻譯：
  - (a) 每個錯誤回應都帶 `X-Request-Id` 與 `X-Trace-Id`，包括 auth 失敗與定址拒絕；
  - (b) 同一個上游錯誤，串流與非串流記成同一個分類；
  - (c) `model` 欄位依 ADR-221 回報；
  - (d) 不透明 app（opaque app）的回應、header、錯誤訊息都不透露背後的模型或 provider。

  依據：報告 SURF-2、§4(a)、O-1、#6071（§4.8）。

---

## 3. 名詞

「effort 格式不同」**不是 agent 的差別，也不是模型的差別，是 API 協定的差別**。Rev.2 再補一層：同一種協定的 agent，行為仍有差異（client profile）。

| 層 | 是什麼 | 例子 |
|---|---|---|
| Client profile（Rev.2 新增） | 同協定下 agent 的行為怪癖 | Codex 只對 HTTP 400、429 不重試；Codex 會把 `refusal` content part 整則丟掉；Codex 用 `originator` header 自報身分。見 ADR-437 Amendment A 與 `docs/research/poc/responses-terminal-shapes-2026-10-03/` |
| Agent | 使用者操作的工具，生來講某一種協定 | Claude Code → Anthropic Messages；Codex → OpenAI Responses（只講這個，`wire_api="chat"` 已被拒）；OpenCode → OpenAI Chat |
| Ingress wire（入口協定，Xparse 稱「API 面」） | client 送進來的 wire 格式 | `/v1/messages` 的 `output_config.effort`；`/v1/responses` 的 `reasoning.effort`；`/v1/chat/completions` 的 `reasoning_effort` |
| Egress wire（出口協定） | Xparse 對上游打的 wire 格式 | `openai_chat`、`openai_responses`、`anthropic_messages`、`bedrock_converse`、`gemini` |
| Deployment | 一筆可路由的上游。在 Xparse 就是一筆 IAM `Model` row（group × provider × model_name，含 endpoint 與 credential） | `gpt-5.4`＠api.openai.com、`claude-sonnet-5-5`＠api.anthropic.com |
| 模型 | 實際推理的 LLM。看不到 JSON，只決定「能不能做」和「做到什麼程度」 | gpt-4o 不推理；gpt-5.4 推理但不收 `minimal`；claude-sonnet-5-5 不收 sampling 參數 |

本文用到的術語：

- **中介格式（pivot）**：Xparse 內部統一的請求、回應、串流事件表示。
  - 現在事實上是「chat 形狀的 dict」加上「worker 吐的無型別 chunk dict」，沒有成文。
  - 目標是 `xparse.items.v1`（§7.3）。
- **Codec**：某種 wire 與中介格式之間的雙向轉換，含請求、回應、串流事件、錯誤。
- **原生路徑（native）**：入口 wire 等於出口 wire，送的是治理過的原生 body。
- **翻譯路徑（translated）**：入口 wire 不等於出口 wire，經 codec 轉換。
- **處置（disposition）**：一個欄位、content-part、工具型別或串流事件，在某條路徑上的去向，共五選一：
  - `FORWARD`：原樣轉送
  - `TRANSLATE`：換成對方的對應物
  - `EMULATE`：由 Xparse 模擬
  - `STRIP_RECORD`：拿掉並記錄
  - `REJECT`：明確拒絕

  沒有預設值，做法比照 ADR-494 的處置表。
- **不透明狀態（opaque state）**：只對原 provider 有意義的資料，例如 Anthropic thinking `signature`、`redacted_thinking.data`、OpenAI `reasoning.encrypted_content`、Gemini thought signature。
- **信封（envelope）**：Xparse 把不透明狀態包起來、加簽、標上來源，放進 client 一定會原樣回送的欄位。

---

## 4. 現況（含程式證據）

### 4.1 架構：兩條軸，一條已統一、一條還沒

```
                 ┌──────────── 軸一：治理（ADR-494，已統一）─────────────┐
入口（API 面）     │ auth → request_fields → … → routing → … → admission → lease │     出口（provider worker）
chat      ─┐     └──────────────────────────────────────────────────────┘    ┌─ OpenAI chat
messages  ─┼─▶ 翻譯成 chat 形狀（GW/anthropic_translation.py）─────────────▶ ├─ Anthropic / Bedrock / Gemini（worker 再翻一次）
responses ─┘──▶ 另一條 Responses 管線（ADR-339 直通 + ADR-437 治理）──────▶ └─ OpenAI／Azure Responses
                 └──────────── 軸二：翻譯（未統一）──────────────┘
```

- **軸一（治理）已統一**。治理吃的是各面 adapter 提供的**視圖**，不是某個統一格式：
  - 依據：ADR-494 的共用 pipeline、面登記表、「面 × stage」處置表，加上 CI gate。
  - Adapter Protocol 在 `GW/surface_adapters/protocols.py`：`user_text`、`transcript`、`tool_reading`、`strip_tools`、`bind_tool_choice`、`route_request`、`previous_response_id` 等。
- **軸二（翻譯）沒統一**，各寫各的：
  - messages 在入口翻成 chat dict（`GW/routes/messages.py:421` `to_openai_chat`），再交給 chat 核心（`:468` `execute_chat`）。所以 **messages 的治理整條跑在翻譯後的 chat 請求上**，見 `GW/surface_adapters/chat.py:353` `MessagesSurfaceAdapter`，docstring 寫的是「the chat core over the translated request」。
  - 各 provider worker 再從 chat dict 編碼成上游 wire（`WK/anthropic_worker.py`、`WK/bedrock_worker.py`、`WK/google_worker.py`……）。
  - Responses 是獨立管線，只接 Responses 原生 provider（`openai_responses`、`azure_openai_responses`）。worker 有兩種輸出：
    - `stream_events()`：ADR-339 透明轉送給 client（`WK/azure_responses_worker.py:422`），在 `response.created` 前多吐一個 `("__binding__", …)` sentinel。
    - `stream()`：正規化成 chat chunk，給 chat 系統內部重用（`:409`）。
  - 兩島之間只有特例橋接：
    - **ADR-260 D9**：chat 的 fallback rung 落在 Responses 模型時，用 `GW/cross_surface.py:108` `chat_messages_to_responses_input` 翻譯。在 `GW/worker_setup.py:1039-1062` 的 translate block 接線。
    - **ADR-455 D10**：chat 帶工具又要推理，打 gpt-5.4 以上時，`GW/worker_setup.py:919` `apply_responses_bridge` 把 provider 換成 `openai_responses`，再走同一個 translate block。決策在 `BE/responses_bridge.py`，五層 containment，endpoint 只限 api.openai.com。
    - 兩者**共用同一份 chat→Responses 翻譯器**，而且 D10 已對真 OpenAI 驗過（`docs/LLM_PROXY.md` §22.3）。

### 4.2 相容性矩陣（dev 實測 2026-10-07，app `gpt_4o_816e`；Rev.2 補上每格的實際語意）

| 模型 ↓ ／ API 面 → | chat（OpenCode） | messages（Claude Code） | responses（Codex） |
|---|---|---|---|
| gpt-5.4（provider `openai`） | ✅ 原生（帶工具＋推理時走 D10 bridge 到 Responses） | ✅ 單次翻譯。損失：thinking 簽章、cache 斷點、document | ❌ 400 `model_not_on_responses_surface`。**同一把 key 本來就能打 Responses API**，這格不是翻譯問題（§9 2a-1） |
| claude-sonnet-5-5（`anthropic`） | ✅ 單次翻譯（worker） | ⚠️ **雙重翻譯**（messages→chat→messages）。損失見 §4.5 | ❌ 400。需要翻譯，並且要 amend ADR-192 §4.9（§5） |
| deepseek-flash（`deepseek`） | ✅ 原生 | ✅ 單次翻譯 | ❌ 400 |
| gpt-4.1-nano（`openai_responses`） | ❌ 422 `model_not_on_chat_surface`。**翻譯器已存在**（cross_surface），只是被過濾 | ❌ 422（同左） | ✅ 原生，**但打折**（Rev.3）：非 `function` 工具全被剝除，Codex 沒有 `apply_patch`，改用 shell 改檔（§4.8） |

- **✅ 的依據很薄**。claude × messages 能找到的實測只有單輪 effort probe（`TST/results/effort_lane_20261006-221720/`，每格 1 個請求，200）。沒有多輪 tool loop＋thinking 的證據。
- Rev.2 起，矩陣每一格都要拆成 §11.2 的情境列，逐一填結果。

### 4.3 現有翻譯程式一覽（方向、用途、已知損失）

| 程式 | 方向 | 用途 | 已知損失（有證據的） |
|---|---|---|---|
| `GW/anthropic_translation.py` `to_openai_chat`（:322） | messages → chat dict | messages 入口 | ① thinking／redacted_thinking block 被丟（`_messages_to_openai` :157 只保留 text、image）<br>② `document` block 靜默消失（`_content_blocks_to_openai_user` :107 只處理 text、image）<br>③ `cache_control` 只轉成「有沒有意圖」的布林（:226）<br>④ `system` 攤平成字串（:84）<br>⑤ server tools 與部分 beta 直接拒絕（:38、:48，PRD-190 N1／N2） |
| `GW/anthropic_translation.py` `OpenAIToAnthropicStreamBuilder`（:458）、`_openai_message_to_blocks`（:398） | chat chunk → Anthropic 事件／訊息 | messages 回程 | thinking block **沒有 `signature`**（全檔 0 處 `signature`） |
| `WK/anthropic_worker.py` | chat dict → Anthropic Messages；Anthropic SSE → chat chunk | provider=anthropic | ① cache 只在 system 前綴補一個斷點（:280-286，註解自承「exact client positions are unpreservable」）<br>② 回程只取 `thinking_delta` 文字（:402-406），**不收 `signature_delta`**（全檔 0 處 `signature`）<br>③ 不轉送 client 的 `anthropic-beta` |
| `WK/bedrock_worker.py` | chat dict → Converse | provider=bedrock | 同上（0 處 `signature`）；cachePoint 只在 system |
| `GW/cross_surface.py`（:108、:180、:215、:236） | chat dict → Responses input／tools／text | ADR-260 fallback、D10 | chat 的 `stop`／`seed`／penalties 在 Responses 沒有對應（處置表未成文） |
| `WK/azure_responses_worker.py` `_handle_event`／`stream()` | Responses SSE → chat chunk | D10、ADR-260 的回程 | reasoning 只剩 summary 文字；`encrypted_content` 不往 chat 側帶 |
| `WK/azure_responses_worker.py:213` `_filter_tools`（OpenAI worker 共用；保留規則是 `:73` `ALLOWED_TOOL_TYPES = {"function"}` 與 `:76` `is_forwarded_tool`） | Responses tools 過濾 | Responses 原生 | 非 `function` 工具一律不送，包括 Codex 的 `custom apply_patch`、`namespace`。S0-b（#5618）起 route 會記 `platform_tool_stripped` 並列入 `X-Xparse-Tools-Stripped`，**已經不是無聲**（Rev.2 寫「無聲濾掉」已過時）。`additional_tools`、`tool_search_output` 裡的工具從 #6020 起也一樣處理（SPEC-304 Rev.16） |

**結論**：今天的「中介格式」是兩種沒有成文、沒有型別的 dict：請求是 chat 形狀，回程是 `WK/base_worker.py:111` `stamp_token`、`:134` `stamp_tool_calls`、`:160` `stamp_finish` 吐出的 chunk。入口翻譯與出口 worker 是兩份互為鏡像的程式，`anthropic_translation.py` 的 docstring 自己寫「This is the *reverse* of `streaming/workers/anthropic_worker.py`」。

### 4.4 「API 面寫死在 provider 上」的耦合點（全部列出；#2783）

| 位置 | 內容 |
|---|---|
| `GW/routing_adapter.py:98` | `RESPONSES_PROVIDERS` frozenset |
| `GW/routing_adapter.py:108`、`:125` | `chat_surface_models`、`responses_surface_models` |
| `GW/cross_surface.py:60`、`:66` | 第二份集合 `RESPONSES_SURFACE_PROVIDERS` 與 `is_responses_surface` |
| `GW/addressing_refusals.py:161-165` | `runs_on(model, surface)`：**API 面資格的唯一判斷式** |
| `GW/addressing_refusals.py:205`、`:217` | 兩種 422 |
| `GW/model_addressing.py:116`、`:120` | 定址閘門呼叫上面兩個 refusal |
| `GW/route_resolution.py:250`、`:254-261` | `surface_models()` |
| `GW/responses_routing.py:150-154` | routing plan 選到非 Responses provider → 500 `routing_plan_model_not_on_responses_surface` |
| `GW/responses_routing.py:175` | binding 查詢只看 Responses provider |
| `GW/routes/responses.py:364` | `delete_response`（:326）只看 Responses provider |
| `GW/worker_setup.py:1046` | `is_responses_surface` → translate-or-skip |
| `GW/classifier_handler.py:1171`、`GW/tier_judge_handler.py:726` | judge 呼叫時的面判斷 |
| `IAM/application/use_cases/application/inference_target.py:48`、`:53` | IAM 的鏡像集合 `RESPONSES_ONLY_PROVIDERS` 與 `is_chat_surface`。部署期 INV-269-3 會擋掉 Responses-only 目標，鏡像一致性由 SPEC-204 SURFACE-1 鎖住 |
| `IAM/api/ninja_api/_providers.py:240`、`:256`、`:289`、`:307`、`:367` | provider catalog 的 `"surface"`：ADR-323 D2 的權威屬性 |
| `IAM/domain/value_objects/provider_surface.py` | Azure 依 `custom_params.requires_responses_api` 改寫成 `azure_openai_responses`（ADR-319） |
| `IAM/db/models/provider.py:374` `class Model` | `provider` 是 identity tuple 的一部分（`UniqueConstraint(group, provider, model_name)`，#2783 證據 1） |

### 4.5 「通但打折」：Claude Code × Claude 的隱性損失（證據）

Claude Code `claude-cli/2.1.291` 實測（`TST/results/effort_lane_20261006-221720/wire_cc.jsonl` 與 `analysis.json`）：

- **請求頂層**：`model, messages, system, tools, metadata, max_tokens, thinking, context_management, safeguards, output_config, stream`
- **`thinking`**：`{"type": "adaptive", "display": "updates"}`；**`output_config.effort`**：`high`／`low`／`max`
- **`cache_control` 有 3 處**：`system[1]`、`system[2]`、`messages[1].content[0]`。最後一個是對話層的斷點。
- **`context_management`**：`{"edits": [{"type": "clear_thinking_20251015", "keep": "all"}]}`
- **`anthropic-beta`**（12 個）：`claude-code-20250219, interleaved-thinking-2025-05-14, thinking-token-count-2026-05-13, context-management-2025-06-27, prompt-caching-scope-2026-01-05, mid-conversation-system-2026-04-07, per-turn-control-2026-07-01, mid-conversation-tool-changes-2026-07-01, effort-2025-11-24, dangerous-tool-use-2026-09-03, thinking-display-updates-2026-08-18, afk-mode-2026-01-31`
- **gateway 的處置紀錄**：`context_management:drop:unknown_field; safeguards:drop:unknown_field; temperature:drop:D12; reasoning_effort:reasoning_forward:D9`

因此今天 Claude Code 經 Xparse 打 Claude 時：

| 損失 | 原因 | 影響 |
|---|---|---|
| 對話歷史吃不到快取 | 3 個斷點縮成 system 前綴 1 個（`WK/anthropic_worker.py:280-286`，ADR-382 INV-382-1） | 長 session 的 input 全額計費。**Phase 0 要量化**（§9） |
| 前幾輪 thinking 不回傳 | `_messages_to_openai` 丟 thinking（`GW/anthropic_translation.py:157`），而且回程本來就沒給 client 簽章 | Anthropic 文件要求 tool loop 中最後一個 assistant 回合的 thinking block 必須原樣回傳；只是今天整段丟掉，所以沒有 400。模型推理連續性受影響 |
| `context_management` 被丟 | messages 去向表沒有這個欄位，被當成 `unknown_field`（`GW/request_fields.py:163-185`） | provider 端的 context 編輯不生效 |
| `interleaved-thinking` 等 beta 不轉送 | worker 不轉送 client beta | 新功能失效。目前沒有逐一盤點影響 |
| `document` block 消失 | `_content_blocks_to_openai_user` 只處理 text、image | PDF 等輸入靜默遺失，違反 S3 |

### 4.6 這幾天已經統一的部分（推理深度 effort；當作「統一做法」的樣板）

| Issue／PR | 做了什麼 | 帶來的統一 |
|---|---|---|
| #6008／#6010 | `/v1/messages` 的 `output_config.effort` 接上 reasoning seam | 三個面的標準 effort 欄位都進同一個 seam，**只看 wire 欄位，不看 client 身分** |
| #5987／#6024 | `/v1/responses` 對不會推理的模型剝掉 `reasoning.effort` | Codex 帶 effort 打非推理模型，不再整輪失敗 |
| #6035／#6039 | 能力閘只留一份（`BE/param_capabilities.py` `reasoning_drop_notice`），加 AST 守門（`BS/tests/unit/test_param_capabilities.py`）；統一值域納入 `max` | 規則改一處、三面生效；第二份實作會被 CI 擋 |
| #6037／#6041 | provider=anthropic 改用新版 Claude 的請求格式（`thinking: adaptive` + `output_config.effort`、剝 sampling；`BE/param_capabilities.py:175` `CURRENT_CLAUDE_SURFACE_RE`） | 修前 claude-sonnet-5-5 每個請求都 400，修後全通 |
| #6036／#6050 | IAM `Model.reasoning_effort_levels`（migration `IAM/migrations/0364_model_reasoning_effort_levels_adr396.py`）加上 seam 的「最近等級」降級（`BE/reasoning_levels.py`） | 模型能力用資料描述，不寫在程式裡 |

這組修正示範的模式（Rev.2 照樣推廣到整條翻譯軸）：

1. **入口**：每個 API 面只把自己的標準欄位翻成統一的內部值。
2. **中間**：只有一份規則（seam），每次改動都記錄（`PARAM_NORMALIZED`）。
3. **出口**：每家 provider 的 wire 編碼由能力表與 worker 決定。
4. **模型能力**：由 IAM 資料描述（`supports_reasoning`、`reasoning_effort_levels`），不在程式裡比對名稱。
5. **防回歸**：每一條規則都有測試，必要時加 AST 守門。

能力資料的傳遞鏈可以照抄：IAM `Model` 欄位 → validate 投影 → `GW/iam_http_client.py:749` DTO 欄位 → `:2447` 映射 → seam 使用。

Rev.3：報告在 e2e 驗過這個樣板的三個環節——#6024（responses 對不推理的模型剝 `reasoning.effort`）、#6001（`stop:drop:D11`）、#5993（五個面的 `PARAM_NORMALIZED` 都帶同一個 `trace_id`）。這個樣板在五個面都成立。

### 4.7 造成孤島與打折的根因（Rev.2 更新）

1. **API 面寫死在 provider 上**（#2783、ADR-323 D2）：provider 同時決定「打哪個上游 wire」和「哪個 API 面能用它」。§4.4 的十幾個點都在問同一個問題：`provider in RESPONSES_PROVIDERS`。
2. **中介格式沒成文、沒型別、沒順序**：
   - chat 形狀的 message 是「`content` 字串＋另外的 `tool_calls`」，表達不了 Anthropic 那種「thinking → text → tool_use → thinking」的區塊順序。
   - Anthropic 是依位置驗證 thinking 簽章。LiteLLM 為此得另外重建順序，見附錄 C。
3. **入口翻譯與出口 worker 各寫一份**：同一個協定有兩份互為鏡像的程式，修一邊漏一邊。
4. **Responses 有 chat 沒有的狀態**：`previous_response_id`、`store`、加密的 reasoning items、hosted tools（`解決-v1-response.md` §2.3、§8）。
5. **雙向翻譯器缺一半**：
   - Responses → Chat（#5528）沒做。
   - Chat → Responses 已有，但只接在 fallback 與 D10 上，一般 dispatch 被過濾（#2551）。
   - Foundry ↔ Responses（#5525）沒做。

### 4.8 2026-10-07 surfaces lane 測試報告：對本案有用的事實（Rev.3 新增）

- **報告**：`docs/測試報告/llm-api.md`；結果在 `TST/results/e2e_20261007/surfaces/`。
- **範圍**：治理軸。六個 API 面的 91 case 矩陣，加上 17 個已 merge 修正的回歸。**沒有測任何跨 wire 的格子**（還刻意不建 openai_responses 模型），也沒有測 Claude Code 多輪 thinking＋tool loop 或快取命中率，所以 Phase 0 照做。
- **整體結論**：88 PASS、0 個真失敗，17 個修正全部 VERIFIED，進入執行的請求都恰好 1 STARTED＋1 終端事件。本案「治理不動、翻譯放在出口」的前提站得住。

| # | 報告的事實（證據） | 對本案的影響 | 改了哪裡 |
|---|---|---|---|
| F1 | `custom` 工具被剝除，頂層宣告與 `additional_tools` 裡的一樣（#6020）；10-06 e2e 的 Codex s3「沒有可用的 apply_patch 工具，只能走 shell」；程式 `WK/azure_responses_worker.py:73` | §8.1 的 `custom`／`namespace` 列不能直接 TRANSLATE：原生路徑也剝，開放是 ADR-490 Q1；翻譯路徑不能比原生寬 | §2 R3、§4.2、§4.3、§5、§8.1、§9 2b、§14 Q11 |
| F2 | `/v1/responses` 不論 `stream` 都回 SSE（O-2；ADR-437、SPEC-282 RSP-RES-8） | 翻譯路徑只需要串流輸出。Open Responses 合規測試多數是非串流，對我們必紅，原因不是翻譯 | §5、§8.1、§9 2b 證據 #3 |
| F3 | SURF-1：非串流 R3 換手成功時記兩筆 STARTED（`GW/non_streaming_handler.py:777`，R3 經 `:1445` 在 `:2103` 重跑 `handle_non_streaming`）；串流 R3 在同一個 driver 換 manager，只記一筆 | 同一個請求的兩次嘗試可能一次原生、一次翻譯；`translation_path` 記在哪要先定。3b 的兩種 R3 要分開驗 | §5、§7.9、§9 3b、§11 S09、§14 Q13 |
| F4 | `PARAM_NORMALIZED` 已是扁平的 `param:action:divergence`、上限 20、帶 `trace_id`（#5993 五面一致），但**只在 chat 的 primary path 發**（`GW/param_normalization_audit.py:10`） | 處置紀錄直接沿用它，不另開管道；要改成每次嘗試都發 | §7.9、§12、§13 |
| F5 | 回應層各面各做各的：SURF-2（chat／messages／responses 的 401 兩個 header 都沒有，`GW/auth_handler.py:399-404`；unary 面有 `with_correlation_headers`）；§4(a)（messages 回報 `req.model`，`GW/routes/messages.py:487`、`:503`）；O-1（同一個 provider 400，非串流記 `provider_error`、串流記 `provider_client_error`）；O-5（429 的 header 集合各面不同） | codec 只管 body；header、`model`、錯誤分類若不統一，每加一個 codec 就多一份分歧。本案新增的拒絕放在 `GW/addressing_refusals.py`，那裡的 422（`:186`）一個 header 都沒帶 | §2 S7、§5、§7.4、§8.1、§8.4、§10 G5 |
| F6 | 不透明 app 的不洩漏契約：回應 `model` 一律 `application_code`；錯誤訊息「Its detail is withheld」（#6002、#6071、INV-138-22） | §7.9 的翻譯 header 與 REJECT 訊息會透露 provider 家族 | §5、§7.4、§7.9、§14 Q10 |
| F7 | 執行前就被拒的請求沒有終端事件；建 worker 時失敗是 1 STARTED＋1 FAILED（#6070） | 要看出口才知道要不要拒的 key，若在建 worker 時才拒，會變成 FAILED，R3 時還會把能成功的備援 rung 弄失敗 | §7.5、§8.1 |
| F8 | messages 面對任何推理模型都回無簽章的 thinking（PRD-190 G4，報告 §4(b)）；`WK/anthropic_worker.py:402-406` 只處理 `thinking_delta` | Claude Code 歷史裡一定會有外家族或無簽章的 thinking；§8.2 的 FORWARD 要加條件；3a 送原始簽章還是信封要先定 | §7.7、§8.2、§9 3a／3b、§14 Q12 |
| F9 | ADR-221 Amendment A（2026-10-07，#6067）：menu app 回報實際執行的模型，只在 chat；messages、responses 明文排除；opaque app 一律 `application_code` | 2b 合成的 Responses 事件 `response.model` 要有規則；三個對話面一致需要 Amendment B | §5、§8.1、§14 Q14 |
| F10 | O-9：本機 `gpt-5.6-luna` 的 `supports_reasoning` 是 1，`reasoning_effort_levels` 是 NULL（#6068） | 「能力是資料」的每個欄位都要定義缺值語意 | §7.6 |
| F11 | O-1：測試當下 Anthropic credit 用完，所有 Anthropic 請求回 400。使用者 2026-10-07 回報已補 | 跑真 Anthropic 證據前先打一個請求確認 | §9 Phase 0、§15.4 |

**可以直接沿用**：
- 報告 harness 每個 case 的自動檢查（恰好 1 STARTED＋1 終端、錯誤回應帶兩個 header、用量單位正確、`PARAM_NORMALIZED` 的 `trace_id` 等於 `X-Trace-Id`），搬到翻譯矩陣的每一格（§9 1.7）。
- O-1 的錯誤對應表，就是矩陣 S12 在 chat／messages × anthropic 的現況基線（§11.2）。
- `GW/addressing_refusals.py:161` 的 `runs_on` 只由 `GW/model_addressing.py:109` 呼叫；unary 面走 `decide_unary_addressing`。所以 Phase 2a 改 `runs_on` 不會動到 D-2b／D-2c 在 unary 面的「只記錄」結果。

---

## 5. 既有決策與脈絡（§17.4 必須處理）

| 文件 | 內容 | 與本案的關係 | 行動 |
|---|---|---|---|
| **ADR-192 §4.9**（`docs/adr/ADR-192-responses-api-phase1-architecture.md:577`，Amendment 2026-06-29，#1559） | 「Responses 入口 egress 到非 OpenAI 家族」定為**永久 out-of-scope**。Option B（在 stateless 後端上模擬 Responses）被否決，理由：lossy、高維護；已有乾淨 workaround：改用 chat | **衝突**。Phase 2b 等於推翻它 | 寫 amendment，只開**無狀態子集**。新理由：Codex 已不支援 chat wire（`wire_api="chat"` 被拒，openai/codex#7782），當時的 workaround 不存在了。有狀態部分維持 Option A |
| **ADR-494**（含 Amendment A）、ADR-492、SPEC-308 | 治理軸：面登記表、處置表、強制 stage、terminal | **延伸**。翻譯軸與治理軸並列；adapter 視圖不變 | ADR 引用；不改 pipeline |
| **ADR-339**、SPEC-234 | Responses 串流透明轉送；否決「從正規化片段重建 Responses 事件」 | **相容**。OpenAI 原生 Responses 維持直通；翻譯路徑才合成事件，這是另一個情境，ADR 要寫清楚 | ADR 說明分界 |
| **ADR-437**、SPEC-282 | Responses 治理管線（扣住／觀察／合成同格式事件、commit point）；**永遠串流**（`stream:false` 也回 SSE，RSP-RES-8，報告 O-2） | **延伸**。合成的事件要能被這條管線原樣消化；翻譯路徑只需要 `stream_events()`，不用做非串流 JSON | SPEC 定事件契約；Open Responses 合規的非串流項目預先標 by-design（§9 2b） |
| **ADR-239**、**PRD-190** | messages 入口翻譯成 chat，單一治理平面（INV-239-1）；server tools 與部分 beta 拒絕（N1／N2） | **延伸／amend**。Phase 3 加原生直送路徑 | ADR-239 amendment；PRD-190 加驗收 |
| **ADR-260 D9**、INV-260-12 | chat 打 Responses rung：translate-or-skip；per-scope 開關 `resilience.cross_surface_fallback` | **延伸**。翻譯器拿來給一般 dispatch 用 | §14 Q8：一般 dispatch 是否沿用此開關 |
| **ADR-455 D10**、SPEC-256 Rev.2 | chat → Responses bridge 五層 containment | **延伸**。Phase 2a-1 是反向 D10 | ADR 引用 |
| **ADR-382** | Claude 後端 prompt cache：只搬 client 意圖、斷點放 system 前綴（INV-382-1） | **amend**。原生路徑可以保留 client 的精確斷點位置 | Phase 3 寫 amendment |
| **ADR-396**（Rev.6） | reasoning 控制參數轉送 seam | **相容**。原生路徑也要套 seam（§9 3b） | 引用 |
| **ADR-493**、**SPEC-307** | 請求欄位去向；**巢狀欄位明列 out of scope**（SPEC-307 §0.2）；chat、messages 只記錄 | **延伸**。翻譯軸的處置表要涵蓋 content-part、工具型別、串流事件；messages 原生路徑要「依表執行」 | SPEC-307 新 Rev 或新 SPEC |
| **ADR-490**、**SPEC-304** | 工具治理 policy kind；S0-b 平台剝除＋`X-Xparse-Tools-Stripped`（`GW/tools_stripped_header.py:39`）。**S0-b 剝的是所有非 `function` 工具**，包括 `custom`、`namespace`（C-304-107；Rev.16 起含 `additional_tools`）。開放這些型別是 **ADR-490 Q1，未拍板**；開放時要同時補 guardrail 的 `custom_tool_call` 偵測面（今天只掃 `function_call`，`GW/guardrail_detection.py:322`），messages 也要保留原本的工具型別（`GW/anthropic_translation.py:205` 一律壓成 function）。見 SPEC-304 :893 | **沿用＋依賴**（Rev.3）。hosted 工具在翻譯路徑剝除時走同一套；§8.1 的 `custom`／`namespace` 列**依 Q1**：開放前與原生路徑一樣 STRIP_RECORD | 引用；§14 Q11 |
| **ADR-447**（Am.E／F） | session affinity；升級只往上走，可能**跨 provider 家族** | **相關**。跨家族換手是常態（S5） | 矩陣加情境 |
| **ADR-323**（Accepted Rev.2）D2 | API 面是 provider catalog 的權威屬性（`{chat, responses, judgement}`，ADR-472 擴充） | **延伸**。Phase 2 先在 gateway 以「provider × endpoint 支援哪些 wire」衍生；Phase 4 再把 catalog 的單值 `surface` 擴成 wire 集合 | Phase 4 amendment |
| **ADR-319** | Azure 把 Responses 當內部能力；**否決 Alternative A**（`Model.api_surface` 二維 dispatch） | **相關**。#2783 要求重議 Alt A；Rev.2 建議 Phase 4 才決定（§9） | Phase 4 |
| **ADR-269**、**SPEC-204** | opencode 部署期：目標必須是 chat 面（INV-269-3），IAM 鏡像集合 | **amend**。Phase 2a-2 之後 Responses-only 目標也可用 | ADR-269 amendment、SPEC-204 SURFACE-1 更新 |
| ADR-095、ADR-221（Proposed；**Amendment A 2026-10-07，#6067**） | 模型身分三層。Amendment A：menu app 回報實際執行的模型（R3 之後是備援），**只在 chat**；`/v1/messages` 用請求自己的 `model`，`/v1/responses` 不在範圍；opaque app 一律 `application_code`（INV-138-22）（`docs/adr/ADR-221-model-identity-reconciliation-response-model-layer.md:138-146`） | **相關，要補**（Rev.3）。2b 合成的 Responses 事件與 messages 原生路徑的 `model` 都要有規則；三個對話面要一致，需要 Amendment B（報告 §4(a)） | SPEC 定 codec 的 `model` 規則；§14 Q14；身分模型本體仍在 Phase 4（#2783） |
| ADR-468 | CN-origin provider 名單、tenant flag | **限制**。config-only provider 仍要過這道 | Phase 4 |
| ADR-093 | 五個不變量 | 每片都要 compliance 表 | §12 |
| **SPEC-308**、ADR-084（Rev.3） | 一個 STARTED 對一個終端事件；STARTED「經 terminal 發出」（§9.9）；TP-1 只規定終端事件的數量 | **相關**。報告 SURF-1：非串流 R3 換手成功時記兩筆 STARTED，串流只記一筆。`translation_path` 記「每次嘗試」還是「整個請求」取決於這題 | §14 Q13 先拍板，再定 §7.9 的欄位 |
| **#5667**（Rev.3） | 錯誤回應缺關聯 header 這一類問題 | **相關**。報告 SURF-2：chat／messages／responses 的 401 兩個 header 都沒有（`GW/auth_handler.py:399-404`）；對話面定址拒絕的 404 只帶 `X-Request-Id`，422（`GW/addressing_refusals.py:186`）一個都沒帶；unary 面已用 `with_correlation_headers`（`GW/unary_execution.py:190`） | 本案新增的拒絕一律帶兩個 header（§8.4）；S7 |
| **INV-138-22**、#5990、#6002、#6071（Rev.3） | 不透明 app：回應的 `model` 是 `application_code`；錯誤訊息不透露被隱藏的名稱（「Its detail is withheld」） | **限制**。§7.9 的翻譯 header 與 REJECT 訊息不得透露 provider 家族 | §7.4、§7.9、§14 Q10 |
| Discussion **#2527**（2026-07-21）＋ **#2504**、#2497 | 同一願景：「任一 client 協定 ⇄ 任一 provider 表面」，含目標矩陣與兩層心智模型。7/25 回報把 chat × Responses 模型標 ✅，**實際上只有 fallback 路徑通**（#2783 證據 6） | **接續**。本文是它的落地版 | 在 #2527 回一則連到新 PRD／ADR |
| `docs/草案/解決-v1-response.md` §15 | LiteLLM 對照：「**沒有單一內部格式**，共用的是治理視圖」 | Rev.1 引它支持「單一 proxy」沒問題，但 CanonicalRequest 框架與它相反。Rev.2 已改：治理吃視圖，中介格式只在翻譯層 | — |

---

## 6. 外部對照：五家平台怎麼做（2026-10-07 讀碼）

研究方法：五個本機 clone，分五個 agent 讀碼，refute-first；每條都附 file:line（附錄 C）。**接手者寫 RESEARCH 證據包時，附錄 C 每條要在 clone 裡重新打開確認。**

| 平台 | clone（commit） | 備註 |
|---|---|---|
| LiteLLM | `/Users/peter/Desktop/research/lite-llm/litellm-versions/litellm-sep-29`（`39d14bd`，2026-09-28） | 最完整 |
| Bifrost | `/Users/peter/Desktop/research/bifrost/bifrost-2026-10-05`（`ed9869f73`，2026-10-05） | 快速提交中 |
| Portkey gateway OSS | `/Users/peter/Desktop/research/gateway`（`669825cb`，2026-05-25） | OSS 自該日起無新 commit |
| vLLM | `/Users/peter/Desktop/research/vllm-version/vllm-2026-10-05`（`92044241a0`，2026-10-04） | 推論伺服器，不是 gateway |
| One-API | `/Users/peter/Desktop/research/one-api/2026-10-05`（`8df4a26`，2025-02-21） | 實質停更，只當結構樣本 |

### 6.1 總表

| | 任意入口 × 任意 provider | 中介格式 | 同家族直送 | 治理在哪一層 | 不透明狀態 | 有狀態 Responses | 測試 |
|---|---|---|---|---|---|---|---|
| LiteLLM | 最完整：messages／responses／chat 雙向互轉，另有 generateContent、A2A、MCP | chat 加大量延伸欄位（`thinking_blocks`、`reasoning_items`、`provider_specific_fields`、`cache_control`） | 有（provider 有 Messages config 或 deployment 宣告 `supported_endpoints`） | 路由前，在原生 body 上做：中立掃描視圖，依位置寫回，對不上就報錯 | 塞進 client 會回送的欄位，加前綴標籤（**明文 base64，可偽造**）；跨家族靠 400 錯誤字串回推 | 用 spend log 模擬，預設關，沒設就默默只送新輸入 | 共用抽象測試套件、VCR（Redis 24h 重錄）、腳本化假上游的精確 body 契約、Claude Code CLI 矩陣 |
| Bifrost | 有；非 OpenAI 也能接 Responses 請求 | 兩套：chat，以及 **Responses 形狀**（Anthropic、Gemini、Bedrock 入口都轉成後者） | 很窄：只限 Claude Code（看 UA）× Claude。一律先解析，再視情況送原始 body；跨家族 fallback 自動關掉 raw | 型別化的統一請求上（hooks） | 型別欄位（`signature`、`encrypted_content`）；id 夾帶（`brid_`、`<id>_ts_<sig>`）；跨家族也是 400 後才剝 | 不存狀態；非 OpenAI 默默丟 | Go 真 API 情境矩陣、官方 SDK × provider、**Claude Code／Codex／OpenCode CLI 測試**；跨 provider 換手測試被 skip |
| Portkey | 部分：messages 只給 Anthropic 系；responses 只給 OpenAI 系，沒有橋 | 每個入口一套；chat 加臨時延伸，型別 `[key]: any` | 有 | 原始 JSON，只看最後一則，出錯就放行 | `content_blocks`；`strictOpenAiCompliance` 預設 true，延伸欄位要 opt-in | 只 OpenAI 系 | — |
| vLLM | Anthropic、Cohere 轉成 ChatCompletionRequest；Responses 另一條 | chat 形狀 TypedDict；輸出端有型別化的 Parser | — | — | Anthropic 簽章丟掉，回程塞 `uuid4` 假簽章 | store 預設關；`store=true` 默默降級；未知 id 回 404；記憶體存，註解自承 memory leak | 官方 SDK e2e、**跨入口 parity 測試**、每個協定一個 `/render` dry-run |
| One-API | 只有 OpenAI 入口 | 封閉的 OpenAI struct | **只在沒開任何治理改寫時**才直送原文 | pivot 上 | 無 | 無 | — |

### 6.2 值得學，以及我們要怎麼改

| 做法 | 出處 | 合不合我們 | 怎麼用 |
|---|---|---|---|
| 一律先解析給治理看，同家族時送原始 body；寫不回就退回翻譯路徑；跨家族 fallback 自動關 raw | Bifrost | **改過再用** | 退路必須是宣告過的處置，並記錄在稽核與 header（ADR-093 #4；One-API 反例） |
| 治理在原生 body 上做：中立視圖＋依位置寫回，對不上就報錯 | LiteLLM | **合** | ADR-494 adapter Protocol 已是這個形狀。成本是「每種入口協定一次」，不是每條路徑一次 |
| 不透明狀態塞進 client 一定會回送的欄位，加前綴標籤；出口剝外家族的 | LiteLLM、Bifrost | **改過再用** | 標籤要加簽或加密（AEAD、AAD），用 gateway 自有金鑰；**出口主動剝**，不要等 400 |
| 加密推理的親和順序：原 deployment → 同憑證 → 剝除但留摘要 | LiteLLM `encrypted_content_affinity_check.py` | **合** | 接在 ADR-447 session pin 與 credential 上；#4878 |
| 一種 wire 一個 codec，入口出口共用 | Bifrost | **合** | 合併 `anthropic_translation.py` 與 anthropic worker 的鏡像程式 |
| 豐富協定轉成 Responses 形狀的中介格式，不轉 chat | Bifrost | **合（只能有一套）** | 中介格式對齊 Open Responses。Bifrost 兩套並存，每個 plugin 寫兩次，這是反例 |
| `custom` 工具 ↔ 單一字串參數的 function，回程還原 | LiteLLM、Bifrost | **合** | 回程要發原生的 `custom_tool_call` 事件。LiteLLM 發的是 function 事件，Codex 收不收要實測 |
| namespace 工具攤平，回程用 alias map 還原 | Bifrost | **合** | — |
| 「服務哪些端點」做成多值資料，可依 deployment 覆寫（`supported_endpoints`） | LiteLLM | **合** | key 要細到 deployment，不能只用模型名（Bifrost 反例）。缺值一律當「未知」 |
| 既有 wire 的相容 provider 只要設定（Bifrost custom provider、LiteLLM providers.json 30 家、Portkey 約 38 行） | Bifrost、LiteLLM、Portkey | **改過再用** | 放在 IAM catalog；**endpoint 必填、不繼承預設**（我們記錄過的地雷：endpoint 為空會繼承 api.openai.com） |
| client 怪癖集中在純函式模組，回傳自己改了什麼 | LiteLLM `codex_compat.py` | **合** | 對上 SurfaceParams 與 `PARAM_NORMALIZED` |
| 降級讓 client 看得到（回應裡帶 `converted_request_type`、`dropped_*`） | Bifrost | **改過再用** | 放 HTTP header 與稽核，不放 body，避免動 wire |
| 跨入口 parity 測試、每個協定一個 dry-run render | vLLM | **合** | parity 進 CI；dry-run 做成稽核欄位或內部除錯端點 |
| 精確 body 契約對腳本化假上游；fixture 從真 provider 錄 | LiteLLM | **改過再用** | 我們的 CI 不打真 key、不排程 → fixture 進 git（大的走 DVC），手動重錄 |
| 真 agent CLI 矩陣 | Bifrost、LiteLLM | **合（P3 手動）** | 沿用 `TST/e2e1006_*` |
| Open Responses 合規測試（對 base URL 跑） | openresponses.org | **合（P3 手動）** | 對 dev gateway 以非 OpenAI 模型跑 |

### 6.3 不要學

| 做法 | 出處 | 為什麼 |
|---|---|---|
| 對 Claude Code、Codex 的 UA 自動開 `drop_params`，而且不記錄丟了什麼 | LiteLLM | 違反 ADR-093 #4、SPEC-307 |
| 等 provider 回 400，比對錯誤字串，剝掉後重試 | LiteLLM、Bifrost | 依賴對方的錯誤措辭，還多打一次上游 |
| 把 Codex 的 `web_search` 換成 provider 自己的搜尋 | LiteLLM、Bifrost | 與現行立場衝突：messages 入口拒絕 server tools（PRD-190 N1）；provider 端執行的工具，gateway 只管得到宣告、管不到執行（`解決-v1-response.md` §8）。要做得先有 ADR-490 範圍的新決策 |
| 用 log 模擬對話狀態 | LiteLLM | 資料保管問題；ADR-192 已否決 |
| 執行期從 GitHub 抓能力表 | LiteLLM | 與離線安裝（PRD-302 M5）衝突；我們用打包的快照 |
| 依 User-Agent 決定走不走直送 | Bifrost | 我們的原則是看 wire 欄位、不看 client 身分（#6010）。client profile 只處理怪癖 |
| 胖 provider 介面（約 60 個必實作方法、小 provider 有 44 個 stub） | Bifrost | 違反 CLAUDE.md §2.1 Interface Segregation |
| 能力只用模型名當 key、忽略 provider | Bifrost | 同一顆模型在不同 endpoint 的能力不同（D10 的 endpoint containment 就是例子） |
| 治理只看最後一則訊息、出錯就放行、未登記的請求型別跳過 | Portkey、LiteLLM | 與 ADR-494 fail-closed 相反 |
| 只在沒開治理改寫時才送原文 | One-API | 開一個治理選項，保真度就默默變差 |
| 回程塞假簽章（`uuid4`） | vLLM | 下一輪回送必被上游拒絕 |
| 兩套中介格式並存 | Bifrost | 每個治理 plugin 寫兩次 |

### 6.4 對本案判斷的影響（Rev.1 → Rev.2）

| 項目 | Rev.1 | Rev.2 | 依據 |
|---|---|---|---|
| 中介格式 | chat 形狀＋延伸欄位（漸進） | **有順序的 item 模型，對齊 Open Responses，封閉＋版本化**；用 strangler 遷移 | LiteLLM 的 chat 加延伸越長越亂（六份剝除清單、thinking 存兩份、兩種串流形狀、扁平 content 需要重建順序）；Bifrost 讓豐富協定都轉 Responses 形狀 |
| 同家族直送 | messages→anthropic 不另開直送（擔心治理要重寫一份） | **原生直送**：一律先解析給治理看，送治理過的原生 body，寫不回走宣告退路 | LiteLLM：成本是每個入口一次；Bifrost：raw 可選、fail-closed、跨家族自動關。前提：請求與回應兩半一起做（§9 Phase 3） |
| 統一表示的位置 | Rev.1 圖把 CanonicalRequest 放在治理前 | 治理吃視圖；中介格式只在出口翻譯層 | 現有 ADR-494；LiteLLM、Bifrost 都是治理先、翻譯後 |
| hosted 工具 | 明確拒絕 | **剝除並記錄** | Codex 每個請求都帶 `web_search`（15/15），拒絕＝永遠不通 |
| `previous_response_id`、`store` | 由 Xparse 模擬 | **不模擬**：用能力過濾候選，沒有候選就明確拒絕 | ResponsesBinding 沒存內容；五家沒一家模擬得好；Codex 是無狀態的 |
| 不透明狀態 | 未提 | **加簽信封＋主動剝除＋親和三步** | LiteLLM、Bifrost 的標籤沒簽、靠 400 回推 |
| 能力資料 | IAM 欄位、解掉 #2783 | 先在 gateway 以 provider × endpoint 衍生（Phase 2），IAM 多值欄位留到 Phase 4 | 降低前期成本；LiteLLM `supported_endpoints` 可證可行 |
| 測試 | 用假 provider 跑矩陣 | **四層**：codec 單元＋性質＋parity；錄好的 fixture；情境矩陣；真 CLI 與 Open Responses 合規手動跑 | §8.1；我們的 CI 規則 |
| 新增：client profile、一 wire 一 codec、config-only provider、走哪條路看得到 | — | 新增 | §7 |

### 6.5 Open Responses 規格（外部標準）

- 網址：<https://www.openresponses.org/specification>，規格日期 2026-04-24。
- 定位：以 OpenAI Responses API 為基礎的開放規格，目的是多 provider 互通。支持者包括 OpenAI、NVIDIA、Vercel、OpenRouter、Hugging Face、Databricks、AWS、Ollama。
- 與本案相關的條文：
  - **items** 是對話的原子單位：`message`、`function_call`、`reasoning`……，各自有 `in_progress`／`completed`／`incomplete` 生命週期。
  - **延伸**一律加實作者前綴，例如 `acme:search_result`，適用於 item、hosted tool、串流事件。
  - **reasoning** 有三個欄位：`content`（原始推理）、`encrypted_content`（provider 不透明，供來回用）、`summary`，三者皆可選。
  - **`previous_response_id`** 可選；HTTP 模式不要求儲存。找不到時回 `previous_response_not_found`。
  - **串流**：所有事件帶單調遞增的 `sequence_number`。
- **合規測試**：<https://www.openresponses.org/compliance>（repo `github.com/openresponses/openresponses`）。設定 base URL、model、API key 就能跑：瀏覽器 10 項（文字、SSE、system、工具、圖片、多輪、compaction），CLI 7 項（WebSocket、`previous_response_id` 續接）。

---

## 7. 目標架構（建議）

### 7.1 總圖

```
                       ┌───────────── 治理（ADR-494，不改）──────────────┐
client ─▶ 入口 adapter ─▶│ 讀「視圖」：user_text / transcript / tool_reading … │─▶ 出口選擇（能力資料 §7.6）
 (chat/messages/       │ 改寫只經 adapter 方法：strip_tools / 遮罩寫回 …    │        │
  responses/…)         └────────────────────────────────────────────────┘        │
                                                                                 ├─ ① 原生路徑：入口 wire == 出口 wire
                                                                                 │     送「治理過的原生 body」（寫回成功）
                                                                                 │     或改走 ② 並記錄 native_fallback_reason
                                                                                 │
                                                                                 └─ ② 翻譯路徑：入口 codec ─▶ xparse.items.v1 ─▶ 出口 codec
                                                                                       （處置表；不透明狀態信封）
上游 provider ◀──────────────────────────────────── worker（只負責 HTTP 傳輸與 SSE 解析）
  回程：provider 事件 ─▶ 出口 codec（解碼成 items 事件）─▶ 入口 codec（渲染成 client 的事件）─▶ 輸出治理（output rail / terminal）─▶ client
```

### 7.2 設計原則（每條附理由與執行方式）

| # | 原則 | 理由 | 怎麼確保 |
|---|---|---|---|
| P1 | **治理吃視圖，翻譯在出口** | ADR-494 已經這樣做；LiteLLM、Bifrost 也是治理先、翻譯後 | ADR 明文；不新增 stage |
| P2 | **單一中介格式 `xparse.items.v1`**：有順序的 item 模型，對齊 Open Responses，封閉＋版本化 | 能保留區塊順序（Anthropic 依位置驗簽）；豐富協定都能裝；有外部標準 | 型別化（frozen dataclass）；只能由 codec 產生與消費；版本號進稽核 |
| P3 | **一種 wire 一個雙向 codec**（請求、回應、串流事件、錯誤） | N 個 codec，不是 N×M；不再有鏡像程式 | `BS/translation/codecs/<wire>.py`；codec 是純函式，回傳結果與處置清單 |
| P4 | **同家族優先原生直送**：先解析給治理看，送治理過的原生 body；改寫寫不回就走宣告退路，並記錄 | 新 beta、新欄位不需要每次改程式；保真度等同直連（R3） | 「governed delta」判斷（§9 3b）；`translation_path` 稽核；跨家族 fallback 自動關 raw |
| P5 | **處置表涵蓋欄位、content-part、工具型別、串流事件**；五選一，沒有預設值 | SPEC-307 只管頂層；今天的靜默丟失都在巢狀層 | 表格放在 codec 旁；§10 G2 gate 比對 SDK 快照 |
| P6 | **不透明狀態走信封**：加簽或加密，AAD 綁 tenant／application／credential；出口主動剝外家族；親和三步 | LiteLLM 明文標籤可偽造；兩家都靠 400 回推 | `BS/translation/envelope.py` 是唯一能產生與解析信封的地方（§10 G3） |
| P7 | **有狀態功能不模擬**：用能力過濾候選，沒有候選就明確拒絕 | ResponsesBinding 沒存內容；模擬要新建對話儲存（資料保管）；Codex 不需要 | 候選過濾（§9 2a-3）；拒絕碼沿用或對齊 `previous_response_not_found` |
| P8 | **能力是資料**，key 在 deployment | 同一顆模型在不同 endpoint 能力不同 | Phase 2：gateway 能力模組（provider × endpoint）；Phase 4：IAM 欄位 |
| P9 | **核心不准有 provider 或 agent 名稱特判**；client 怪癖的唯一落點是 client profile 模組 | 防止耦合回流；給特判一個合法位置，比全面禁止實際 | §10 G1 gate，baseline 只縮不增 |
| P10 | **走哪條路、丟了什麼都看得到** | S3、S4 | 稽核 `translation_path`；請求端處置進 `PARAM_NORMALIZED`、輸出端進 `translation_output_dispositions`；header（§7.9，Rev.3） |
| P11 | **測試四層** | §8.1：fake 只證明 fake 的契約 | §11 |
| P12 | **漸進**：不動 ADR-494 pipeline、chat 狀態機（§7）、ADR-339 對 OpenAI 原生的直通 | 剛交付、還沒上 prod | 新程式放 `BS/translation/`；舊 worker 先用 chat codec 包住 |

### 7.3 中介格式 `xparse.items.v1`（草圖；SPEC 定稿）

用 Python frozen dataclass 寫成型別，與 Open Responses 的 item 概念一一對齊。以下是**概念草圖**，欄位名定稿時要對照 Open Responses 規格與 OpenAI SDK 型別。

```python
# BS/translation/items.py（新檔；草圖）
ITEMS_SCHEMA_VERSION = "xparse.items.v1"

@dataclass(frozen=True)
class Origin:
    """Where an opaque blob came from; used to decide forward vs strip."""
    wire: str            # "anthropic_messages" | "openai_responses" | ...
    provider: str        # IAM provider code
    credential_uuid: str # binding boundary (LiteLLM: blobs are tied to the org/key)
    model_uuid: str

@dataclass(frozen=True)
class OpaqueBlob:
    kind: str            # "anthropic_signature" | "anthropic_redacted_thinking" | "openai_encrypted_reasoning" | "gemini_thought_signature"
    data: str
    origin: Origin

@dataclass(frozen=True)
class CacheMarker:       # 保留 client 斷點的「位置」；egress codec 決定怎麼編碼
    ttl: Optional[str]   # e.g. "5m" | "1h"

# Content parts（順序有意義）
InputText, OutputText, ImagePart, FilePart(document), RefusalPart  # 各自可帶 cache: Optional[CacheMarker]

# Items（順序有意義）
MessageItem(role, parts: tuple[Part, ...])
ReasoningItem(summary: tuple[str, ...], content: tuple[str, ...], opaque: tuple[OpaqueBlob, ...])
FunctionCallItem(call_id, name, arguments_json)
FunctionCallOutputItem(call_id, output, is_error: Optional[bool])   # #4160 的 is_error 語意
CustomToolCallItem(call_id, name, input_text)                       # Codex apply_patch
CustomToolCallOutputItem(call_id, output)
HostedToolCallItem(kind, payload)       # 只在原生路徑出現；翻譯路徑一律 STRIP_RECORD

# Tool declarations
FunctionTool(name, description, parameters_schema, strict)
CustomTool(name, description, format)   # freeform / grammar
HostedTool(kind, config)                # web_search / tool_search / file_search / ...

# Request（只放 codec 需要的；治理仍讀入口 adapter 的視圖）
ItemsRequest(model, instructions, items, tools, tool_choice, max_output_tokens,
             reasoning_effort, sampling, response_format, stop, extensions)
# extensions: dict[str, Any]，key 必須帶前綴（"anthropic:context_management"），只有同家族 codec 會讀

# Stream events（typed；取代 WK/base_worker.py 的 chunk dict，逐步遷移）
ItemAdded / TextDelta / ReasoningDelta / OpaqueAttached / ToolArgsDelta / ItemDone /
UsageReported(input, output, cached, cache_write, reasoning) / Terminal(status, reason) / StreamError(code, message)
```

規則：

- **封閉**：新增 item 或事件型別要升版（`xparse.items.v2`）。未知型別在入口 codec 就決定處置，不能「先放著」。
- `extensions` 只放帶前綴的同家族專屬資料，跨家族的 codec 一律剝除並記錄。這是 Open Responses 的 `slug:` 規則。
- usage 欄位對齊 `GW/terminal_usage.py:100-134` 的 `cached_tokens`、`cache_write_tokens`（ADR-373／ADR-380）。沒有回報的值留 `None`，**不准補 0**。

### 7.4 Codec 介面（草圖）

```python
# BS/translation/codecs/base.py（新檔；草圖）
class WireCodec(Protocol):
    wire: str
    def decode_request(self, body: Mapping[str, Any]) -> tuple[ItemsRequest, Dispositions]: ...
    def encode_request(self, req: ItemsRequest, target: EgressTarget) -> tuple[dict, Dispositions]: ...
    def decode_stream(self, events: AsyncIterator[tuple[str, dict]]) -> AsyncIterator[ItemsEvent]: ...
    def encode_stream(self, events: AsyncIterator[ItemsEvent], ctx: RenderCtx) -> AsyncIterator[tuple[str, dict]]: ...
    def encode_error(self, err: TranslationError | WorkerError) -> RenderedError: ...
```

- **純函式**（除串流 iterator 外沒有 I/O）。不 import IAM，不讀 env。
- 每個方法都回傳處置清單（`Dispositions`），交給稽核。
- 同一個 codec 同時服務入口與出口。例如 `anthropic_messages` codec：Claude Code 入口時 `decode_request` 加 `encode_stream`；Anthropic 出口時 `encode_request` 加 `decode_stream`。
- **回應層的橫切規則不屬於任何一個 codec**（Rev.3）。報告的 SURF-2、§4(a)、O-1、O-5 都是「同一件事每個 route 各做一次、做法還不一樣」。codec 只決定 body 的形狀；以下四項由共用的 render 層決定，經 `RenderCtx` 傳給 codec：
  - **關聯 header**：`X-Request-Id`、`X-Trace-Id` 由共用 wrapper 加上（比照 `GW/unary_execution.py:190` `with_correlation_headers`），涵蓋 auth 失敗、定址拒絕、處置 REJECT、上游錯誤。codec 不自己加，也不能漏。
  - **`model` 欄位**：依 ADR-221，opaque app 回 `application_code`，menu app 回實際執行的模型。目前 messages 用 `req.model`（`GW/routes/messages.py:487`、`:503`），responses 不在 Amendment A 範圍；三個面要一致需要 Amendment B（§14 Q14）。
  - **錯誤分類**：`encode_error` 吃重分類後的碼（`effective_error_code`，也就是 `GW/fallback_handler.py:67-74` 判斷能不能 R3 的那一套），串流與非串流用同一套。報告 O-1：同一個 provider 400，非串流記 `provider_error`、串流記 `provider_client_error`（ADR-441 已記載），新路徑不准再分岔。
  - **不透明 app**：錯誤訊息不得點名 provider 或被隱藏的模型（#6071）。

### 7.5 處置（disposition）格式

```python
# BS/translation/dispositions.py（新檔；草圖）
class Disposition(Enum):
    FORWARD = "forward"; TRANSLATE = "translate"; EMULATE = "emulate"
    STRIP_RECORD = "strip_record"; REJECT = "reject"

@dataclass(frozen=True)
class Rule:
    key: str          # "field:store" | "part:document" | "tool:web_search" | "event:response.reasoning_summary_text.delta" | "item:item_reference"
    disposition: Disposition
    ref: str          # ADR/SPEC/PRD 依據（比照 ADR-494 NotApplicable(ref)）
    note: str

# 每個 (ingress_wire, egress_wire) 一張表；表上沒有的 key → 入口就 REJECT 或 STRIP_RECORD，由表的 `unknown` 規則明定（不准默默放行）
```

§8 是三張主要的表的初稿。

**REJECT 在哪裡發生**（Rev.3）。依據報告 §2.2：執行前就被拒的請求沒有終端事件；#6070：建 worker 時失敗是 1 筆 STARTED＋1 筆 FAILED。

| 類型 | 例子 | 在哪裡拒 | 稽核 |
|---|---|---|---|
| 只看入口就能決定 | `conversation`、`background`、`item_reference` | request_fields stage（與 SPEC-307 同一處） | 執行前拒絕，沒有終端事件 |
| 要看出口才知道 | `top_logprobs`（Anthropic 沒有）、`text.format`（出口不支援結構化輸出）、有狀態請求（§8.4） | **候選過濾**：只留出口做得到的模型；過濾後沒有候選才 422 | 執行前拒絕，沒有終端事件 |
| 不准出現 | 路由完、建 worker 時才發現某個 key 要 REJECT | — | 會變成 STARTED 之後的 FAILED；R3 時還會把本來能成功的備援 rung 弄失敗。表上的 REJECT 必須能在候選過濾階段判斷，判斷不了就改成 STRIP_RECORD |

### 7.6 能力資料與「誰能服務哪個面」

- 新模組 `BS/translation/capabilities.py`（或 `GW/egress_capabilities.py`），取代 `GW/addressing_refusals.py:161` 的 `runs_on`：
  - `native_wires(model) -> frozenset[str]`：Phase 2 由 provider × endpoint 推導。例如：
    - `openai`＠api.openai.com → `{openai_chat, openai_responses}`（D10 已證明同一把 key 兩種 API 都能用）
    - `openai_responses` → `{openai_responses}`
    - `anthropic` → `{anthropic_messages}`
    - `deepseek`、`vllm` → `{openai_chat}`
    - Phase 4 改由 IAM 欄位提供，並可依 deployment 覆寫。
  - `serves(model, ingress_wire, traits) -> Verdict(NATIVE | TRANSLATED | NO(reason))`：同 wire 回 NATIVE；有 codec 對就回 TRANSLATED；需要狀態但沒有原生能力就回 NO。
  - `supports_stateful_responses(model)`：等於 `openai_responses ∈ native_wires(model)`。
- §4.4 列的所有耦合點都改呼叫這個模組。`RESPONSES_PROVIDERS`、`RESPONSES_SURFACE_PROVIDERS` 最後只准出現在這裡（§10 G1）。
- endpoint containment 沿用 D10 第二層（`BE/responses_bridge.py`）：自架的 OpenAI 相容 endpoint 不會有 `/responses`，所以不推導出 `openai_responses`。
- **每個能力欄位都要寫明缺值語意**（Rev.3）。報告 O-9：本機 `gpt-5.6-luna` 的 `supports_reasoning` 已是 1，`reasoning_effort_levels` 仍是 NULL；#6068 指出 `minimal` 可能因此拿到 provider 400。每個欄位都要定義「沒有值」代表什麼（未知 → 保守處置），並有測試，不能只有 `supported_endpoints` 一欄有規則。

### 7.7 不透明狀態信封

- **格式**（草圖）：`xpenv1.<kid>.<base64url(nonce || ciphertext || tag)>`
  - AEAD，例如 AES-256-GCM。
  - AAD = `tenant_uuid | application_uuid | credential_uuid | provider | model_uuid`，對應 ADR-093 #5 身分綁定。
  - 明文 = `{"v":1, "kind": ..., "blocks": [...], "origin": {...}}`。
- **金鑰**：gateway 自有。PRD-302 禁止 gateway import IAM 加密模組。
  - 新 env，例如 `XPARSE_TRANSLATION_ENVELOPE_KEYS`（`kid → key`，可多把以便輪替）。
  - 要重產 `BS/config/runtime.schema.json`（不重產會讓 gateway 的 owner suite job 紅）。
  - 要寫佈建與輪替 runbook。**部署變更要另外授權。**
- **放在哪**（都是 client 一定會原樣回送的欄位）：
  - Responses 入口：reasoning item 的 `encrypted_content`。Codex 會逐位元回送，見 memory `reference_codex_is_responses_only_and_stateless.md`。
  - Messages 入口：thinking block 的 `signature`，或 `redacted_thinking.data`。Phase 3 之後才用。
- **解碼規則**：
  - 驗證失敗、偽造、kid 已退役 → **剝除並記錄**（`envelope_invalid`），不回 400。key 輪替後舊 session 不會被打斷，偽造的也拿不到任何東西。
  - 來源與目標同 provider、同 credential → 還原成原生 blob 轉送。
  - 不同 → 剝除並記錄（S5）。
- **親和**：ADR-447 已會把 session 釘在同一個模型。升級或 fallback 換家族時，依上面規則剝除，不靠 provider 回 400。
- **3a 送給 client 的 signature 要不要包信封，必須在 3a merge 前決定**（Rev.3，§14 Q12）：
  - 原始的 Anthropic signature 不帶「來自哪個 credential」的資訊，而且一旦寫進 client 的對話歷史就收不回來。
  - 之後 3b 原生直送時，gateway 無法分辨歷史裡的 signature 是不是同一個 credential 產生的；R3 可能換過 credential，或換到 Bedrock。
  - 建議 3a 就輸出 `xpenv1` 信封。client 只會原樣回送，不會解讀內容。
- **外家族、無簽章的 thinking 一定會出現在歷史裡**（Rev.3，報告 §4(b)）：
  - messages 面依 PRD-190 G4，對任何推理模型（含 DeepSeek、經 messages 打的 gpt-5 系）都把 `reasoning_content` 轉成 thinking block，而且沒有 signature。
  - Claude Code session 只要有一輪落在這類模型（ADR-447 升級、R3），之後轉到 Anthropic 原生路徑時，這些 block 都必須剝除（§8.2）。

### 7.8 Client profile 模組

- 新檔 `GW/client_profiles.py`（或 `GW/surface_adapters/client_profiles.py`）：
  - 依 `originator`、UA 辨識 client（只用來處理怪癖，不決定治理或路徑）。
  - 提供純函式的轉換。每個函式回傳「改了什麼」，由呼叫端寫進 `PARAM_NORMALIZED` 類的稽核。
- 現有要收進來的點：
  - `GW/routes/models.py:62`：Codex 的 `/v1/models` 形狀
  - `GW/tool_result_status.py:117`：Codex 的 exit-code 解析
  - Codex 擋下格式規則（ADR-437 Amendment A）
- §10 G1 gate：`originator`、UA 字串比對只准出現在這個模組。現有兩處列 baseline，或搬進來。

### 7.9 可觀測性

- **稽核**（Rev.3 改寫）：
  - **請求端的處置沿用 `PARAM_NORMALIZED`，不另開管道**。理由：
    - 它已經是扁平的 `param:action:divergence` 字串，最多 20 筆並標記截斷（`GW/param_normalization_audit.py:30`、`:33`）；
    - 帶 route 綁定的 `trace_id`（`:96`，#5981；報告 #5993 在五個面驗過）；
    - 不存內容。
  - 翻譯處置照同一格式寫，例如 `tools.web_search:strip_record:SPEC-304`、`include.reasoning.encrypted_content:emulate:envelope`。key 用點路徑、不能含 `:`，否則三段解析會壞。
  - **缺口**：`PARAM_NORMALIZED` 目前只在 chat 的 primary path 發（同檔 `:10`）；R3 換手那次的處置只有 WARNING log。翻譯路徑上線前要改成每次嘗試都發（attempt 語意依 §14 Q13）。
  - **終端事件**（`EXECUTION_COMPLETED`、`EXECUTION_FAILED`，`GW/terminal.py`）只加兩個欄位：
    - `translation_path`：`native` | `native_rewritten` | `translated` | `bridged`，記產生這個終端事件的那次嘗試；
    - `translation_output_dispositions`：只有串流中才知道的輸出端處置（例如 refusal 轉 `output_text`、signature 包信封），扁平字串，有上限。
  - 要走 audit allowlist（memory：audit extra 會丟掉巢狀 dict，見 `reference_audit_extra_drops_nested_dicts.md`），**一律扁平化成字串**。
- **Header**（名稱待 §14 Q10）：
  - `X-Xparse-Translation: translated`
  - `X-Xparse-Dropped: field:include,tool:web_search`（沿用 `GW/tools_stripped_header.py` 的長度與截斷規則）
  - 串流時 header 在開始就送出，所以只能放請求端已決定的處置。輸出端的降級只進稽核。
  - **opaque app 不送這兩個 header**（Rev.3）：例如 `X-Xparse-Dropped: field:top_logprobs` 會透露背後是哪一家，違反 #6071 的不洩漏契約。只寫進稽核。

---

## 8. 各路徑的處置表（草案，SPEC 的起點）

> 依據：Codex 實測（附錄 B）、`解決-v1-response.md` §2.3、SPEC-307 §1、LiteLLM／Bifrost 對照（附錄 C）。SPEC 定稿時每一列要補 ref 與測試 ID。

### 8.1 Responses 入口 → 非 Responses 原生的出口（anthropic_messages／openai_chat）。Codex 打 Claude、DeepSeek、vLLM

**請求頂層欄位**

| key | 處置 | 說明 |
|---|---|---|
| `model` | TRANSLATE | 路由後換成出口模型（served name） |
| `instructions` | TRANSLATE | → Anthropic `system`／chat system message |
| `input`（見下表） | TRANSLATE | 逐 item |
| `tools`、`tool_choice`、`parallel_tool_calls` | TRANSLATE | 見工具表；`parallel_tool_calls=false` → Anthropic `disable_parallel_tool_use` |
| `stream` | TRANSLATE | Codex 一律串流；而且 `/v1/responses` 不論 `stream` 都回 SSE（ADR-437、RSP-RES-8），翻譯路徑只需要串流輸出（Rev.3） |
| `max_output_tokens` | TRANSLATE | → `max_tokens` |
| `temperature`、`top_p` | TRANSLATE | 走 seam（新版 Claude 剝 sampling，D12） |
| `reasoning.effort` | TRANSLATE | 走 seam：Claude 新家族 → `output_config.effort`，其他 → `reasoning_effort` 或剝除（#6039） |
| `reasoning.summary` | STRIP_RECORD | Anthropic 的 thinking 本身就是摘要；不另外支援 |
| `include: ["reasoning.encrypted_content"]` | EMULATE | 用信封承載 Claude thinking＋signature（§7.7） |
| `include` 的其他值 | STRIP_RECORD | — |
| `store` | 見 §8.4 | — |
| `previous_response_id` | 見 §8.4 | 候選過濾；沒有能力就拒絕 |
| `truncation` | STRIP_RECORD | — |
| `text.format`（json_schema） | TRANSLATE；出口不支援 → 候選過濾 | 出口模型支援結構化輸出才 TRANSLATE；不支援的模型在候選過濾階段就排除，沒有候選才在執行前 422（§7.5，不默默降級；Rev.3） |
| `text.verbosity` | STRIP_RECORD | — |
| `metadata`、`user`、`safety_identifier` | 沿用 SPEC-307 §1.1 | 不轉送給非 OpenAI provider，只記稽核 |
| `prompt_cache_key` | CONSUMED | SPEC-290 C-290-36 affinity；不轉送 |
| `max_tool_calls` | STRIP_RECORD | 跨 provider 無法強制 |
| `top_logprobs` | REJECT（候選過濾） | Anthropic 沒有；只留出口支援的模型，沒有候選才在執行前 422（§7.5，Rev.3） |
| `conversation`、`prompt`、`background`、`context_management` | REJECT | 與 SPEC-307 §1.1 一致 |
| 表上沒有的 | STRIP_RECORD（`unknown_field`） | 與 SPEC-307 HOLD 一致 |

**input items**

| item | 處置 | 說明 |
|---|---|---|
| `message` | TRANSLATE | content parts 逐一轉；`input_file`、`input_image` 依出口支援 |
| `function_call`、`function_call_output` | TRANSLATE | → `tool_use`、`tool_result`（保留 id） |
| `custom_tool_call` | 依 ADR-490 Q1（Rev.3） | Q1 開放後 TRANSLATE → `tool_use`，input 包成 `{"input": "<text>"}`。開放前不會出現（工具已被剝除）；若出現，與對應的 output 成對 STRIP_RECORD，不讓出口收到沒有宣告的工具呼叫 |
| `custom_tool_call_output` | 依 ADR-490 Q1（Rev.3） | 同上；開放後 → `tool_result` |
| `reasoning`，`encrypted_content` 是 **Xparse 信封**，來源與目標同 provider＋credential | TRANSLATE | 還原成 Anthropic thinking＋signature，放回正確位置（Phase 2b） |
| `reasoning`，信封來源不同家族 | STRIP_RECORD | S5 |
| `reasoning`，`encrypted_content` 是 **OpenAI 原生** blob | STRIP_RECORD | 只有 OpenAI 同 org 看得懂（#4878） |
| `item_reference` | REJECT | 需要伺服器狀態 |
| hosted tool call items（`web_search_call`、`local_shell_call`、`mcp_*`、`computer_call*`） | STRIP_RECORD | 出口沒有對應的執行者 |

**tools**

| tool type | 處置 | 說明 |
|---|---|---|
| `function` | TRANSLATE | → Anthropic tool（`input_schema = parameters`） |
| `custom`（`apply_patch` freeform） | **依 ADR-490 Q1**（Rev.3） | 原生路徑今天也被 S0-b 剝除，翻譯路徑不能比原生寬，所以 **Q1 開放前 STRIP_RECORD**（同樣記 `platform_tool_stripped`、列入 header）。Q1 開放後：→ 只有一個字串參數 `input` 的 tool，grammar 放進 description（不強制），回程還原成 `custom_tool_call` item 與事件。Rev.2 寫的「Codex 能改檔全靠這一列」不成立：Codex 經 Xparse 今天就沒有 `apply_patch`，改用 shell 改檔（10-06 e2e s3） |
| `namespace` | **依 ADR-490 Q1**（Rev.3） | Q1 開放前 STRIP_RECORD（原生路徑同樣剝除）；開放後攤平，回程用 alias map 還原名稱（Bifrost） |
| `web_search`、`tool_search`、`file_search`、`code_interpreter`、`computer*`、`local_shell`、`image_generation`、`mcp` | STRIP_RECORD | 走 `platform_stripped_tools`（`GW/responses_tools_filter.py:82`）與 `X-Xparse-Tools-Stripped`。映射成 provider 原生工具另案（§14 Q5） |

**輸出與串流**（出口事件 → Responses 事件）

| 來源 | 處置 | 說明 |
|---|---|---|
| `response.model`（Rev.3） | TRANSLATE | 依 ADR-221：opaque app → `application_code`；menu app → 實際執行的模型。Responses 不在 Amendment A 範圍，規則由本案 SPEC 定（§14 Q14） |
| text delta | TRANSLATE | → `response.output_text.delta`（`output_item.added`、`content_part.added`、`delta`、`done` 的完整序列，帶 `sequence_number`）。`id`、`created_at`、`sequence_number` 各自只能有一個來源（比照 #6023 修過的 chat `created`；Rev.3） |
| thinking 文字 | TRANSLATE | → reasoning item 的 `summary`（Claude 4 以後回的是摘要）。事件：`response.reasoning_summary_text.delta` |
| thinking `signature`、`redacted_thinking` | EMULATE | → 同一個 reasoning item 的 `encrypted_content`（信封）。只在 `include` 有要求時輸出 |
| tool_use（function） | TRANSLATE | → `function_call` item 與 `function_call_arguments.delta`、`done` |
| tool_use（由 custom 而來） | TRANSLATE（ADR-490 Q1 開放後才會出現） | → `custom_tool_call` item 與 `custom_tool_call_input.delta`、`done`。**要用真 Codex 驗**：Codex 在 `output_item.done` 當下執行工具 |
| refusal | TRANSLATE | → `output_text` 說明＋`completed`。Codex 遇到 `refusal` content part 會整則丟掉（`docs/research/poc/responses-terminal-shapes-2026-10-03/README.md`） |
| stop_reason `end_turn`、`tool_use` | TRANSLATE | → `response.completed` |
| stop_reason `max_tokens` | TRANSLATE | → `response.incomplete`（`max_output_tokens`） |
| usage | TRANSLATE | → Responses usage。`input_tokens_details.cached_tokens` = cache read；cache write 照 ADR-380；reasoning tokens 只有回報時才填 |
| 第一個事件前的錯誤 | TRANSLATE | → HTTP status。Codex 只有 400、429 是終止狀態，其他會重試。一律帶 `X-Request-Id`、`X-Trace-Id`；分類用重分類後的碼，串流與非串流同一套（§7.4，Rev.3） |
| 串流中途錯誤 | TRANSLATE | → `response.failed`，code 對齊 SPEC-282 與 Codex 的終止集合 |

### 8.2 Messages 入口 → Anthropic 出口（原生路徑；Phase 3。SPEC-307 messages 表改成「依表執行」）

| key | 原生路徑處置 | 說明 |
|---|---|---|
| `model` | FORWARD（改寫） | 換成 served name |
| `messages`、`system` | FORWARD | 治理改寫只有在 §9 3b 的 governed delta 允許時才寫回，否則走退路 |
| thinking／redacted_thinking blocks | FORWARD（**有條件**，Rev.3） | 只轉送 signature 驗得過、而且來源是同 provider＋同 credential 的 block（§7.7 信封）。其他一律 STRIP_RECORD：Xparse 從 DeepSeek 等 `reasoning_content` 合成的無簽章 block、3a 上線前的舊歷史、外家族的 block。前提：回程已把 signature 給 client（§9 3a） |
| `cache_control`（所有位置） | FORWARD | ADR-382 amendment：原生路徑保留 client 的精確斷點 |
| `document`、`search_result` 等 block | FORWARD | 治理看不到的 block 要先列入 adapter 視圖，否則依 §14 Q6 決定 |
| `tools`、`tool_choice` | FORWARD（改寫） | 工具治理剝除後寫回 |
| server tools（`web_search_*`、`code_execution_*`、`computer_*` …） | REJECT | 維持 PRD-190 N1 |
| `thinking`、`output_config` | FORWARD（seam 投影） | seam 仍決定 effort、sampling（D12） |
| `temperature`、`top_p`、`top_k`、`stop_sequences` | FORWARD（seam 投影） | — |
| `metadata` | §14 Q6 | 建議：不轉送 `user_id`（維持 ADR-268 只稽核） |
| `context_management` | §14 Q6 | 建議：`clear_*` 類（只刪不增）FORWARD；compaction 類 REJECT，理由同 `GW/request_fields.py:292` |
| `service_tier` | HOLD | `pending_pricing`，計價未定 |
| `inference_geo` | HOLD | 資料落地屬治理決策 |
| `diagnostics`、`user_profile_id`、`workspace_id`、`safeguards`、未知欄位 | STRIP_RECORD | — |
| `container`、`mcp_servers` | REJECT | 不變 |
| `anthropic-beta` header | 允許清單 FORWARD，其他 STRIP_RECORD | §14 Q6。拒絕清單 `GW/anthropic_translation.py:48` 照舊 |

**回程的 thinking**（Rev.3，報告 §4(b)）：翻譯路徑依 PRD-190 G4，即使 client 沒開 thinking，也把 `reasoning_content` 轉成 thinking block；Anthropic 原生只在開啟時回傳。Claude Code 一律帶 `thinking: adaptive`，不受影響；其他 Anthropic SDK client 會看到差異。SPEC 要把這條寫成明確的處置（建議維持 FORWARD 並記錄），不要留在隱含。

### 8.3 Chat／Messages 入口 → Responses 原生出口（Phase 2a-2；沿用 `GW/cross_surface.py`）

| key | 處置 | 說明 |
|---|---|---|
| chat `messages` | TRANSLATE | `chat_messages_to_responses_input`（`GW/cross_surface.py:108`） |
| chat `tools` | TRANSLATE | `chat_tools_to_responses_tools`（`:180`） |
| chat `response_format` | TRANSLATE | `chat_response_format_to_responses_text`（`:215`） |
| `store` | EMULATE | 固定 `false`（`synthesize_responses_fallback_extra_params` `:236` 的現行作法） |
| chat `stop` | STRIP_RECORD | Responses 沒有 |
| chat `seed`、`presence_penalty`、`frequency_penalty`、`logit_bias` | STRIP_RECORD | Responses 沒有 |
| chat `n>1` | REJECT | 已是 400（#366） |
| messages `thinking` 的 signature 回送 | STRIP_RECORD | 出口是 OpenAI，看不懂 Anthropic 簽章 |
| messages `cache_control` | STRIP_RECORD | OpenAI 是自動快取 |
| 回程 reasoning | TRANSLATE | → `reasoning_content`（chat）或 thinking block（messages）。要不要把 OpenAI `encrypted_content` 用信封放進 thinking `signature` 回給 Claude Code，留到 Phase 4 |

### 8.4 有狀態 Responses 功能的決策規則

`store` 的有效值由 `WK/azure_responses_worker.py` 的 `normalize_outbound_store` 計算：省略時是 `(True, "default")`（PRD-157 §3.4），明送時是 `(值, "client")`。

| 情境 | 規則 |
|---|---|
| 有 `previous_response_id` | 候選只留 `supports_stateful_responses` 的模型。binding 優先順序不變（pin > binding > affinity > resolver） |
| `store` 明送 `true`（source=client） | 候選只留有狀態能力的模型（§14 Q4 建議） |
| `store` 省略（source=default） | **不過濾**。落到翻譯路徑時改成 `false`，記錄 `store_default_downgraded`，回應物件的 `store` 照實回 `false` |
| `store=false`（Codex） | 不過濾 |
| 過濾後沒有候選 | 422，新 refusal code（例如 `stateful_responses_unsupported`），訊息說明改用無狀態用法。**一律帶 `X-Request-Id` 與 `X-Trace-Id`**（Rev.3：同檔現有的 422 `refuse_model_on_other_surface` 一個 header 都沒帶，`GW/addressing_refusals.py:186`，屬 #5667 這一類）；opaque app 的訊息不點名模型 |
| 翻譯路徑的回應 | **不寫 ResponsesBinding**（不 yield `__binding__` sentinel）。之後用這個 id 續接，會落到 chain validator 的 `unknown_response_id`（`GW/responses_chain_validator.py:76`）。SPEC 要決定要不要對齊 Open Responses 的 `previous_response_not_found` |
| DELETE `/v1/responses/{id}` 指向翻譯路徑的 id | 404（沒有 binding） |

---

## 9. 實作計畫

> 每片都要遵守：設計閉環先行（CLAUDE.md §17.1）、先寫 integration／contract test（§8）、§8.1 真元件證據、§17.2 commit checklist、PR base 是 `main`、不疊 PR。
> 新測試檔要登記在 `BS/gateway-ci-suite.txt`，否則 orphan gate 會紅。

### Phase 0：確認需求並量測（1–2 天）

1. **問 FAE／業務**：客戶實際會怎麼搭？依需求排出 Codex × Claude、Claude Code × Responses-only 模型、OpenCode × Responses-only 模型的優先序。
2. **量測 Claude Code 快取命中**（決定 Phase 3 要不要提前）：
   - 唯讀查 dev／rel 稽核：`surface=messages`、`provider=anthropic` 的 `EXECUTION_COMPLETED`，算 `sum(cached_tokens) / sum(input_tokens)`，依 session 的第 N 輪分組。欄位見 `GW/terminal_usage.py:100-134`。
   - 對照組：同一段 Claude Code session 直連 Anthropic 的 `cache_read_input_tokens`。
   - **不要動 KEY2 那個 app**（`docs/LLM_api.md` §9）。需要不同設定就自己建 probe app，測完清掉。
3. **先確認 Anthropic 憑證能用**（Rev.3）：報告 O-1 測試當下 credit 用完，所有 Anthropic 請求都回 400；使用者 2026-10-07 回報已補。量測前先用自建 probe app 打一個請求確認 200。
4. **把兩個前置決策送 Peter**（Rev.3）：
   - §14 Q13：SURF-1 的 STARTED 是每次嘗試一筆，還是每個請求一筆。這決定 `translation_path` 的語意。
   - §14 Q11：ADR-490 Q1 要不要開放 `custom`／`namespace`。這決定 §8.1 那兩列，以及 Codex 能不能用 `apply_patch`。
5. **退出條件**：決定 Phase 2b 與 Phase 3 的先後；記下快取命中率的基準值，當作 S6 的驗收門檻；Q11、Q13 有答案，或明確延後。

### Phase 1：設計閉環＋規則（不寫產品程式）

| 片 | 產物 | 怎麼做 | 退出條件 |
|---|---|---|---|
| 1.1 | `docs/research/RESEARCH-llm-translation-axis-cross-gateway-2026-10-07.md` | `/research`。以本文 §6 與附錄 C 為輸入，**每條外部引用在 clone 裡重驗**。依 house style 寫 §0 可信度表；回補 `docs/research/研究智庫-HUB.md`（§17.1b） | 每條差異化、業界做法的宣稱都有一手出處，或標 WEAK |
| 1.2 | PRD（下一個號碼，寫的時候查；目前最大 PRD-343） | `/doc-prd`。R1–R3、S1–S6 改寫成客戶端驗收（API、Integration、Negative）；附白話層（§1）；**驗收寫可觀察屬性**，例如「Codex 能用 Claude 改檔」，不寫「走 codec X」（§17.1a） | Peter 核定 |
| 1.3 | ADR：翻譯軸（下一個號碼；目前最大 ADR-499） | `/doc-adr`。決策 P1–P12；Alternatives 寫 chat＋延伸（LiteLLM 路線）、兩套中介格式（Bifrost）、模擬有狀態（LiteLLM）、全面原生直送；invariants；ADR-093 表 | 同上 |
| 1.4 | ADR-192 §4.9 amendment | 只開無狀態子集；理由見 §5 | 同上 |
| 1.5 | SPEC（下一個號碼；目前最大 SPEC-311） | 中介格式定義、codec 契約、§8 的處置表（含 ref 與測試 ID）、事件對應、錯誤對應、矩陣定義（§11.2） | 同上 |
| 1.6 | Core 整合層 | 依 §13 更新 `docs/adr/core/Core-ADR-01-Gateway-Streaming.md`、`Core-ADR-06-Provider-Integration.md`、`Core-PRD-01`、`Core-PRD-06`（必要時 03、04） | PR description 附 Core 對比表 |
| 1.7 | 矩陣骨架 | `BS/tests/conformance/translation_matrix/`（新目錄；先讀 `BS/tests/conformance/harness.py`、`conftest.py`）；現況不通的格子標 `KnownGap(#issue)`。**每格沿用報告 harness 的自動檢查**（Rev.3，`TST/e2e1007_surfaces_probe.py`）：進入執行恰好 1 STARTED＋1 終端（依 Q13 調整）、錯誤回應帶兩個 header、用量單位正確、`PARAM_NORMALIZED` 的 `trace_id` 等於 `X-Trace-Id` | 在 CI 跑；不通的格子都有 issue |
| 1.8 | gate | §10 G1（core purity）先上；G2–G4 隨 Phase 2 上 | 對刻意植入的回歸會紅（dogfood） |

**開 issue**：依 Phase 2–4 的切片開票，掛在一個 Epic 下。一律走 `/doc-issue`，**要 Peter 同意**。agent 不能自己開票。

### Phase 2a：便宜、疊加型的切片（不需要新中介格式）

#### 2a-1 Codex × provider=`openai` 的模型 → 改打 OpenAI Responses API（反向 D10）

- **目的**：讓 §4.2 的 gpt-5.4 × responses 從 400 變原生通。同一把 key、零損失。
- **條件**：`model.provider == "openai"`，而且 endpoint 通過 D10 第二層（api.openai.com 或子網域，或 `endpoint is None`）。Azure 暫不納入（ADR-455 §7 同樣排除）。
- **要動的檔**：

| 檔案 | 改動 |
|---|---|
| `GW/addressing_refusals.py:161` `runs_on` | 改呼叫 §7.6 的 `serves()` |
| `GW/routing_adapter.py:108`、`:125` | 同上 |
| `GW/responses_routing.py:150` | 同上 |
| `GW/responses_routing.py:175`（`resolve_bound_model`） | binding 查詢的 provider 改用「有效的 Responses provider」：openai 列 → `openai_responses` |
| `GW/routes/responses.py:326` `delete_response`（:364） | 同上 |
| `GW/responses_stream.py:126` `create_responses_worker` | 建 BackendConfig 時把 `provider` 換成有效 wire（同 `GW/worker_setup.py:919` `apply_responses_bridge` 的作法）。**credential 先用 routed Model 宣告的 provider 解析，再換 wire**（INV-455-2） |
| `WK/factory.py` | 確認 `openai_responses` 分支吃得下 openai 列的 endpoint 與 credential |

- **ResponsesBinding**：`provider` 欄位寫有效 wire 的 provider（`openai_responses`），維持 `(provider, provider_response_id)` 的命名空間隔離（INV-192-8）。`model` FK 指原列。
- **測試**：
  - contract：`serves()` 的真值表；
  - conformance：responses × openai(chat 註冊) 的基本、串流、工具、`previous_response_id` 續接、DELETE；
  - **§8.1**：對真 OpenAI 用同一把 key 打 gpt-5.4 的 Responses API，收到 `response.created` 與 `completed`；
  - 真 Codex 跑一次多輪（`TST/e2e1006_codex*.sh`，模型換 gpt-5.4）。
- **退出條件**：上述全綠；矩陣該格 ✅（附情境）。

#### 2a-2 Chat／Messages 入口 → Responses 原生模型（一般 dispatch 走既有 cross_surface）

- **目的**：§4.2 的 gpt-4.1-nano × chat／messages 從 422 變通（#2551）。
- **要動的檔**：

| 檔案 | 改動 |
|---|---|
| `GW/addressing_refusals.py:161` `runs_on`（改成 `serves()`）、`:205` | chat、messages 對 Responses 原生模型回 TRANSLATED，不再 422 |
| `GW/route_resolution.py:254-261` `surface_models` | 同上 |
| `GW/model_addressing.py:116`、`:120` | 同上 |
| `GW/worker_setup.py:1039-1062` translate block | 一般 dispatch 也進這裡。**開關怎麼接是 §14 Q8**：ADR-260 的 `resolve_cross_surface_fallback` 是 resilience 開關，不適合直接拿來管一般 dispatch |
| `GW/cross_surface.py` | 補齊 §8.3 處置並記錄（`stop`、`seed`、penalties 等目前沒記錄） |
| `IAM/application/use_cases/application/inference_target.py:48-56` | INV-269-3 放寬（ADR-269 amendment），並同步更新 SPEC-204 SURFACE-1 鏡像測試 |

- **測試**：conformance chat × Responses 原生、messages × Responses 原生（基本、串流、工具、effort）；§8.1：D10 已有真 OpenAI 證據，換成 `openai_responses` 列重跑一次。
- **退出條件**：矩陣 gpt-4.1-nano 那一列 chat、messages 兩格有情境結果。

#### 2a-3 `serves()` 能力模組＋有狀態感知的候選過濾

- **目的**：2a-1、2a-2 的共同基礎；也是 2b 的前提，因為 Claude 進入 Responses 候選池之後，需要狀態的請求不能落到 Claude。
- **新檔**：`BS/translation/capabilities.py`（或 `GW/egress_capabilities.py`）。
- **規則**：§7.6 與 §8.4。新 refusal code 加在 `GW/addressing_refusals.py`，**而且要帶兩個關聯 header**（Rev.3）。同檔現有的 422 都沒帶；最好順手把對話面的 404／422 一起收進共用 wrapper，這是 #5667 的範圍。
- **gate**：`RESPONSES_PROVIDERS`、`RESPONSES_SURFACE_PROVIDERS` 的成員判斷只准出現在能力模組（§10 G1 的一部分）。
- **建議**：2a-3 先做，2a-1、2a-2 建在它上面。也可以三片合成一個 PR，但要拆 commit。

### Phase 2b：Responses 入口 → 任意 provider（Codex 打 Claude、DeepSeek、vLLM；只做無狀態）

**前置**：ADR-192 §4.9 amendment 已核定；2a-3 已 merge。

| 片 | 內容 | 檔案 |
|---|---|---|
| 2b-1 | 中介格式＋處置型別 | 新增 `BS/translation/__init__.py`、`items.py`、`dispositions.py`。**先看 `BS/pyproject.toml` 的 package 探索設定**，必要時把新 package 加進去；同 owner（gateway），不違反 PRD-302 |
| 2b-2 | codec：`openai_responses`（近乎 identity）、`openai_chat`、`anthropic_messages` | `BS/translation/codecs/{base,openai_responses,openai_chat,anthropic_messages}.py`。`openai_chat` 可以重用 `GW/cross_surface.py` 的函式。`anthropic_messages` 這一步**先只做「items → Anthropic 請求」與「Anthropic SSE → items 事件」**，不動 `GW/anthropic_translation.py` |
| 2b-3 | Responses 事件合成器 | `BS/translation/stream/responses_renderer.py`：items 事件 → Responses 具名事件。要做到：完整的 added／delta／done 序列、單一 `sequence_number` 來源（vLLM 的作法）、終止事件依 §8.1 |
| 2b-4 | `TranslatingResponsesWorker` | `WK/translating_responses_worker.py`：包住出口 worker，實作 `stream_events()`，契約同 `WK/azure_responses_worker.py:422`。**不 yield `__binding__`**。`usage` 屬性回傳出口的 usage。`/v1/responses` 永遠串流，不需要非串流 JSON 輸出（Rev.3） |
| 2b-5 | 接線 | `GW/responses_stream.py:126` `create_responses_worker` 依 `serves()` 的結果選 worker：NATIVE 用既有 worker；TRANSLATED 用 2b-4。`GW/responses_routing.py` 允許翻譯目標進候選 |
| 2b-6 | 工具 | hosted 剝除（`GW/responses_tools_filter.py:82` `platform_stripped_tools`＋`X-Xparse-Tools-Stripped`）。custom ↔ function、namespace 攤平還原**等 ADR-490 Q1 開放後才做**；開放前兩者照原生路徑剝除（Rev.3） |
| 2b-7 | 信封 | `BS/translation/envelope.py`；新 env、`BS/config/runtime.schema.json`、runbook（§7.7） |
| 2b-8 | 稽核與 header | 請求端處置寫進 `PARAM_NORMALIZED`（每次嘗試都發）；終端事件加 `translation_path`、`translation_output_dispositions`；opaque app 不送翻譯 header（§7.9，Rev.3）。改 `GW/terminal.py` 的呼叫端時，記得 `provider-call-usage-parity-gate.py`、`usage-ledger-surface-parity-gate.py` |
| 2b-9 | 文件 | SPEC 定稿、PRD 驗收對齊、`docs/LLM_PROXY.md` 補一節 |

**ADR-437 管線相容性（2b-4 必看）**：合成的事件要被 Responses 管線原樣消化，包括：
- `GW/responses_resilience.py:288` 驅動 `stream_events()`；
- `GW/responses_output_rail.py` 的 output rail；
- `GW/responses_content_capture.py` 的 capture tap；
- 終端稽核；
- commit point（INV-437-1）：第一個轉送出去的事件之前才能 retry 或 failover。

先讀 `GW/responses_output_events.py`，確認 rail 處理哪些事件名。

**§8.1 證據**（缺一不可）：
1. 真 Anthropic 收到 2b 產生的請求，含 custom tool、多輪 tool loop、thinking → 200，而且 `tool_use` 正確；
2. 真 Codex CLI 對 dev gateway 用 claude-sonnet-5-5 與 deepseek-flash 跑多輪，**用 shell 改檔**、執行 shell。`apply_patch` 要等 ADR-490 Q1 開放 `custom` 之後另驗；今天原生路徑也沒有（Rev.3）。腳本改自 `TST/e2e1006_codex*.sh`，Codex 工作目錄放 `/private/tmp`；
3. Open Responses 合規測試對 dev gateway（模型 claude-sonnet-5-5）跑瀏覽器那 10 項。**先把必紅的項目宣告為 by-design**（Rev.3）：
   - 官方頁（2026-10-07 查）列的 Basic Text Response、Assistant Message Phase、Response Output Phase Schema 明確是非串流，而 `/v1/responses` 永遠回 SSE（ADR-437）；
   - 2 項 compaction 我們本來就拒絕；
   - 其餘幾項頁面沒寫明是否串流，要實跑判讀；
   - 有效訊號以 Streaming Response 為主。CLI 那 7 項全是 WebSocket，不適用；
4. 跨家族換手：同一個 Codex session 先 gpt-5.4、後 claude，不會 400，外家族 blob 有剝除紀錄。

**退出條件**：矩陣 responses 那一欄全部有情境結果（通或明確宣告）；S5 情境綠。

### Phase 3：Claude Code × Claude 保真（R3、S6）

#### 3a 回程帶出 signature（安全，可以單獨上）

| 檔案 | 改動 |
|---|---|
| `WK/anthropic_worker.py`（:402 附近的事件處理） | 收 `signature_delta` 與 `redacted_thinking` block，經 chunk 的新欄位傳出（過渡期 chunk 仍是 dict，但欄位名要先在 SPEC 定好） |
| `GW/anthropic_translation.py:458` `OpenAIToAnthropicStreamBuilder`、`:622` `_content_block_events`、`:398` `_openai_message_to_blocks` | 對 client 輸出完整的 thinking block（含 `signature`）與 `redacted_thinking` |
| `WK/bedrock_worker.py` | Bedrock 的 reasoning signature 同步評估（可以拆另一片） |

- 這一片不改請求側：client 回送的 thinking 仍在 `:157` 被丟，所以不會產生新的 400。
- **merge 前要先定 §14 Q12**（Rev.3）：送給 client 的是原始 signature 還是 `xpenv1` 信封（§7.7）。寫進 client 歷史就收不回來。
- **§8.1**：真 Anthropic 回應給 client 的 thinking block 有非空 `signature`。

#### 3b 請求側原生直送（governed delta 判斷）

**做法**：治理照舊跑在翻譯後的 chat 上，MessagesSurfaceAdapter 不改。出口時比對治理前後的差異，決定能不能送原生 body。

1. `GW/routes/messages.py:421` 前後各留一份不可變快照：原始 body（`req.model_dump()` 後 deep-freeze），以及治理前的 `openai_dict`。
2. 新純函式 `BS/translation/native_delta.py::governed_delta(pre_chat, post_chat) -> Delta`，把差異分類為：
   - `none`
   - `model_only`
   - `max_tokens`
   - `tools_removed(names)`、`tool_choice_changed`
   - `text_masked`：來自 `GW/guardrail_detection.py:508-511` 的寫回
   - `other`
3. 在 `GW/worker_setup.py` 建 anthropic worker 前判斷：
   - 出口是 `anthropic`，路由選到的也是 Claude 家族，而且差異是 `none`、`model_only`、`max_tokens` 或工具類 → **原生路徑**。從原始快照重建 body，套用改寫：model 改 served name、max_tokens、移除工具並修 `tool_choice`、套 seam 投影（D12、effort）、依 §8.2 處置欄位與 beta、剝除驗不過或外家族的 thinking block（§8.2，Rev.3）。放進 `BackendConfig.extra_params["anthropic_native_body"]`。
   - 其他情況 → 翻譯路徑（今天的行為），記錄 `native_fallback_reason`。
   - R3 fallback 到非 Anthropic 家族 → 強制翻譯路徑（Bifrost 的作法）。**兩種 R3 要分開做、分開驗**（Rev.3，報告 SURF-1）：非串流是整個 `handle_non_streaming` 重跑（`GW/non_streaming_handler.py:1445` → `:2103`），串流是在同一個 driver 換 manager。原生或翻譯的判斷要在每次嘗試各做一次。
4. `WK/anthropic_worker.py`：有 `anthropic_native_body` 就直接送它，beta header 照允許清單轉送；沒有就照舊。
5. SPEC-307 新 Rev：messages 的原生路徑「依表執行」（§8.2）。`GW/request_fields.py:163-185` 的 `MESSAGES_FIELDS` 要補 `context_management`、`safeguards` 等列。

- **§8.1 證據**：真 Claude Code 對 dev gateway 用 claude-sonnet-5-5 跑 ≥3 輪、含 tool use 與 thinking：
  - 不會 400；
  - 第 3 輪起 `cached_tokens > 0`，命中率接近直連，門檻用 Phase 0 的基準；
  - 稽核顯示 `translation_path=native`。
  - 再開 PII 遮罩重跑一次：看到 `native_fallback_reason=text_masked`，請求仍成功。
  - **跨家族歷史**（Rev.3）：同一個 session 先讓一輪落在 deepseek-flash（產生無簽章 thinking），再換到 claude-sonnet-5-5：不會 400，稽核有對應的 STRIP_RECORD。

#### 3c 遮罩寫回（可選，讓原生路徑也能套 PII 遮罩）

- 依 LiteLLM 的作法：依型別化的位置，把遮罩寫回原生 Anthropic text block；數量對不上就報錯，**不准默默退回**（附錄 C 的 LiteLLM AG:85-125、668-669）。
- 新檔 `BS/translation/rewriters/anthropic_masking.py`；`governed_delta` 的 `text_masked` 從「退路」變成「native_rewritten」。

#### 3d 文件

ADR-239 amendment（原生路徑）、ADR-382 amendment（精確斷點）、SPEC-307 Rev、PRD-190 加驗收。

### Phase 4：能力資料進 IAM、其他雲、收斂中介格式

| 片 | 內容 | 要點 |
|---|---|---|
| 4a | IAM 能力欄位（#2783） | `Model` 加 wire 集合或可服務面的覆寫欄位（expand migration，§8.3 安全）→ validate 投影 → `GW/iam_http_client.py:749`、`:2447` 加 DTO 欄位。**IAM openapi 改了要同 PR 重釘六處 consumer digest**（CLAUDE.md §17.2 #7）。Console 顯示走 i18n 與 design system。最後退役 gateway 兩份與 IAM 一份的 Responses provider 集合。ADR-323 D2 amendment；重議 ADR-319 Alt A |
| 4b | 既有 wire 的相容 provider 改成 config-only | IAM catalog 加 `base_wire`、**endpoint 必填**、怪癖旗標；factory 依 `base_wire` 選 codec。現在加一家要動的約十處（memory `reference_new_inference_provider_touchpoints.md`）縮成 catalog 資料。**不准繼承預設 endpoint**（地雷：會把 prompt 與別家 key 送到 api.openai.com）。ADR-468 CN 名單、計價預設、憑證用途照舊 |
| 4c | Foundry ↔ Responses（#5525）、Bedrock 新版 Claude reasoning 與 cachePoint 位置、Gemini thought signature | 各自一個 codec 或 codec 擴充 |
| 4d | strangler：chat 出口 worker 改用 items codec | 先 anthropic（合併 `GW/anthropic_translation.py` 與 `WK/anthropic_worker.py` 的鏡像程式），再 bedrock、google。**ADR 要寫 chat-as-pivot 的退場條件**，避免長期兩套（Bifrost 反例） |

### 依賴關係

```
P0 ─▶ P1(1.1→1.2→1.3/1.4→1.5→1.6, 1.7, 1.8)
          │
          ├─▶ 2a-3 ─▶ 2a-1
          │      └──▶ 2a-2 ─(ADR-269 amend)
          ├─▶ 3a（可與 2a 並行）
          │
          ├─▶ 2b-1 ─▶ 2b-2 ─▶ 2b-3 ─▶ 2b-4 ─▶ 2b-5 ─▶ 2b-6/2b-7/2b-8 ─▶ 2b-9   （需 ADR-192 amend + 2a-3）
          └─▶ 3b（需 3a）─▶ 3c ─▶ 3d
                                        └─▶ P4（4a 可在 2b 之後任何時間；4d 最後）
```

**建議順序**：P1 → 2a-3 → 2a-1 → 3a → 2a-2 → 2b → 3b → 3c → P4。如果 Phase 0 顯示 Claude Code 快取命中很低，就把 3b 提到 2b 前面。

---

## 10. 防回歸 gate（P4 Lock；`/flow-gate add #ISSUE`）

| Gate | 鎖什麼 | 作法 |
|---|---|---|
| **G1 translation-core-purity** | provider 名稱字串、`RESPONSES_PROVIDERS` 與 `RESPONSES_SURFACE_PROVIDERS` 成員判斷、`originator`／UA 比對，只准出現在允許的模組：codecs、workers、能力模組、`BE/param_capabilities.py`、client profile | stdlib AST 掃描 `GW/`、`BE/`、`BS/translation/`。**baseline 只縮不增**：目前 `GW/`、`GW/routes/`、`BE/` 有 12 個檔含 provider 字串，`GW/routes/models.py:62` 與 `GW/tool_result_status.py:117` 有 originator 比對。範本：`BS/tests/unit/test_param_capabilities.py` 的 AST 守門 |
| **G2 translation-dispositions** | 每個 `(ingress_wire, egress_wire)` 的處置表，涵蓋 SDK 快照（`BS/scripts/sdk-request-params.v1.json`）的所有頂層欄位，以及 SPEC 列出的 content-part、工具型別、串流事件；沒有預設值 | 比照 `.github/scripts/request-field-dispositions-gate.py` 與 `surface-dispositions-gate.py` |
| **G3 envelope-single-owner** | `xpenv1.` 只能由 `BS/translation/envelope.py` 產生與解析；codec 不得直接轉送 `OpaqueBlob`，必須經「來源比對」函式 | AST |
| **G4 matrix-completeness** | 矩陣每格不是綠，就是帶 issue 的 `KnownGap` | 比照 `.github/scripts/surface-conformance-gate.py` |
| **G5 refusal-correlation-headers**（Rev.3，可選） | 對話面的拒絕（`GW/addressing_refusals.py` 等）不准建出沒有關聯 header 的 `HTTPException` | AST 掃 `HTTPException(` 呼叫是否帶 `headers=` 或經共用 wrapper；現有缺 header 的列入 baseline，只縮不增。範本同 G1 |

- 每個 gate 都要先看它對刻意植入的回歸變紅（dogfood）。
- script 與 `ci.yml` 的 marker 兩處要一致。
- 本機跑時要設 `GITHUB_EVENT_NAME=pull_request GITHUB_BASE_REF=main`。

---

## 11. 測試計畫

### 11.1 四層

| 層 | 內容 | 跑在哪 |
|---|---|---|
| L1 codec 單元＋性質 | 每個 codec 的請求、回應、串流、錯誤對應<br>**同家族來回不變**：wire → items → wire 等於原文，只差已宣告的處置<br>**跨入口 parity**：同一段對話從 chat、messages、responses 進來，正規化後的 items 相同（vLLM `test_render_parity.py` 的作法） | CI |
| L2 精確 body 契約 | 對腳本化的假上游，斷言送出的 body 逐欄相同；fixture 從真 provider 錄（Codex、Claude Code、Anthropic、OpenAI 的真 SSE）；小檔進 git，大型語料走 DVC（CLAUDE.md §19） | CI |
| L3 情境矩陣 | §11.2；由能力資料展開；不通的格子標 `KnownGap(#issue)` | CI |
| L4 真 client＋外部合規 | Codex、Claude Code、OpenCode CLI 對 dev gateway；Open Responses 合規測試；client 或 provider 升版就重錄 L2 fixture（比照 `TST/codex_block_shape_probe.py`） | 手動（P3 驗證、交付前） |

### 11.2 矩陣定義

- **入口 wire**：chat、messages、responses
- **出口 wire**：openai_chat、openai_responses、anthropic_messages（之後 bedrock_converse、gemini）
- **情境**：

| ID | 情境 | 備註 |
|---|---|---|
| S01 | 基本單輪 | — |
| S02 | 串流 | 事件順序、`sequence_number`、終止事件 |
| S03 | 工具呼叫 | 單次 |
| S04 | 多輪 tool loop | ≥3 輪 |
| S05 | custom 工具來回 | Codex `apply_patch` |
| S06 | hosted 工具剝除 | 有 header 與稽核 |
| S07 | effort | 各等級與降級 |
| S08 | 同家族 thinking 回放 | 簽章 |
| S09 | 跨家族換手 | 外家族 blob 剝除，S5。串流與非串流兩種 R3 都要測（報告 SURF-1）；`translation_path` 記在產生終端事件的那次嘗試（Rev.3） |
| S10 | cache 斷點保留 | S6 |
| S11 | 有狀態請求處理 | 過濾與拒絕，§8.4 |
| S12 | 錯誤對應 | 第一個事件前與串流中途；兩個關聯 header；串流與非串流同一個分類。chat／messages × anthropic 的現況基線見報告 O-1（Rev.3） |

每格 × 每個情境的結果寫進 SPEC 附表。**兩家競品都缺的 S08、S09 是我們最該先補的。**

### 11.3 真 client 與資源

- **腳本與結果**：`TST/e2e1006_*`（三個 agent 完整 e2e）、`TST/effort_agent_lane.py`、`TST/codex_block_shape_probe.py`、`TST/results/`。
- **surfaces lane 腳本**（Rev.3）：結果在 `TST/results/e2e_20261007/surfaces/`。
  - `TST/e2e1007_surfaces_probe.py`：六個面的矩陣與 cleanup
  - `TST/e2e1007_surf_r3_double_started.py`：SURF-1 重現，自建自清
  - `TST/e2e1007_surf_401_headers.py`：SURF-2 重現
  - `TST/e2e1007_surf_anthropic_4xx.py`：Anthropic 400 在各面的處理
- **Codex**：
  - 工作目錄放 `/private/tmp`，否則會讀到 `~/.codex/config.toml`。
  - prompt 從 stdin 進。
  - `wire_api` 只能是 `responses`。
  - 攔截配方見 memory `reference_codex_is_responses_only_and_stateless.md`。
- **Claude Code**：`claude` 的 shell alias 會自動加 `--dangerously-skip-permissions`，腳本要呼叫真正的 binary。
- **金鑰**：在 `TST/.env`。**不要印出來、不要寫進報告**。不要動 KEY2 app 的模型、政策、綁定。

---

## 12. ADR-093 compliance 預想（各片 PR 要填正式版）

| 不變量 | 本案怎麼滿足 | 證據（測試或程式） |
|---|---|---|
| #1 No partial state transition | 翻譯路徑不寫任何持久狀態，翻譯路徑的回應不寫 ResponsesBinding。Phase 4a 的 IAM migration 照 §8.3 expand/contract | Phase 2：無寫入的 contract test；4a：migration 測試 |
| #2 Pre-condition validation before commit | codec 解碼與處置判斷都在送出前、無副作用；REJECT 在任何上游呼叫前發生 | 「REJECT 不打上游」測試（假上游呼叫數 = 0） |
| #3 Post-condition verification after commit | 原生路徑送出前比對「重建 body」與「允許的改寫」一致（`governed_delta` 重算）；4a migration 後回讀 | `native_delta` 測試；migration 回讀 |
| #4 Fail-fast, no silent fallback | 處置五選一、沒有預設；原生退路是宣告過的處置，而且有記錄；信封驗證失敗會記錄；請求端處置寫進 `PARAM_NORMALIZED`，R3 每次嘗試都記（Rev.3） | G2 gate；`PARAM_NORMALIZED`、`translation_output_dispositions` 的稽核測試 |
| #5 Identity binding stability | `correlation_id`、`trace_id`、`tenant_uuid`、`credential_uuid` 不因翻譯改變；每個錯誤回應都帶 `X-Request-Id`、`X-Trace-Id`（S7，Rev.3）；信封 AAD 綁 tenant／app／credential／provider／model；credential 先依 routed Model 宣告的 provider 解析，再換 wire（INV-455-2） | 信封 AAD 錯配就剝除的測試；2a-1 的 credential 解析測試；矩陣每格的 header 檢查（§9 1.7） |

---

## 13. §17.4 Core 對比表（預填；PR description 用）

| 領域 | Core-ADR／PRD | 關係 | 行動 |
|---|---|---|---|
| 01 Gateway & Streaming | `docs/adr/core/Core-ADR-01-Gateway-Streaming.md`、`docs/prd/core/Core-PRD-01-Gateway-Streaming.md` | extends ADR-494（翻譯軸與治理軸並列）；amends ADR-192 §4.9、ADR-239；extends ADR-260 D9、ADR-455 D10、ADR-339／437 | 加新 ADR／PRD 編號與一行說明；記錄 ADR-192 amendment |
| 06 Provider Integration & LLM Proxy | `docs/adr/core/Core-ADR-06-Provider-Integration.md`、`docs/prd/core/Core-PRD-06-Provider-Integration.md` | extends ADR-323 D2（wire 集合）、ADR-396 seam；amends ADR-382（Phase 3）；相關 ADR-319 | 同上 |
| 03 IAM & Identity | `docs/adr/core/Core-ADR-03-IAM-Identity.md`、`docs/prd/core/Core-PRD-03-IAM-Identity.md` | Phase 2a-2：amends ADR-269（INV-269-3）；Phase 4a：Model 能力欄位（#2783） | 對應階段才更新 |
| 04 Audit & Observability | `docs/adr/core/Core-ADR-04-Audit-Observability.md`、`docs/prd/core/Core-PRD-04-Audit-Observability.md` | 請求端處置沿用 `PARAM_NORMALIZED`（改成每次嘗試都發）；終端事件新增 `translation_path`、`translation_output_dispositions`；attempt 語意依 SURF-1 的決定（SPEC-308；Rev.3） | 更新 |
| 13 FinOps & Cost Governance | `docs/prd/core/Core-PRD-13-FinOps-Cost-Governance.md` | 相關：Claude Code 原生路徑會提高快取命中、降低成本；usage 對應必須保留 `cached_tokens`／`cache_write_tokens`（ADR-380） | 註記 |
| 02 Policy & Authorization | Core-ADR-02 | **depends on ADR-490 Q1**（Rev.3）：工具治理仍在入口視圖上做；hosted 剝除沿用 SPEC-304 S0-b；`custom`／`namespace` 能不能翻譯取決於 Q1 | 引用；Q1 拍板後再看要不要更新 |
| 05 Console Frontend | Core-PRD-05 | Phase 4a 才顯示能力欄位 | 屆時更新 |
| 其他（07–12） | — | orthogonal | 不影響 |

---

## 14. 需要 Peter 決定的事（附建議）

| # | 問題 | 選項 | 建議與理由 |
|---|---|---|---|
| Q1 | 方向 | 在 gateway 內補翻譯軸；或另蓋中間件服務 | **在 gateway 內**。治理都在 gateway；另蓋要嘛治理寫兩份，要嘛多跳一次；PRD-302 share-nothing 也不允許共用治理程式 |
| Q2 | ADR-192 §4.9 | 維持永久不做；amend 開放無狀態子集；全開含模擬 | **amend 開放無狀態子集**。Codex 已不支援 chat wire，當時的 workaround 不存在；有狀態部分維持原決策 |
| Q3 | 中介格式 | (A) 對齊 Open Responses 的 items，漸進遷移；(B) chat 形狀加延伸欄位 | **(A)**。chat 表達不了區塊順序；LiteLLM 走 (B) 已經長出六份剝除清單；有外部標準可以對齊。代價是要有明確的遷移與退場計畫（§9 4d） |
| Q4 | 有狀態功能 | 模擬（要新的對話儲存 PRD）；能力過濾＋明確拒絕；默默降級 | **能力過濾＋明確拒絕**。`store` 省略（source=default）時不過濾，落到翻譯路徑就降成 false 並記錄；明送 `store=true` 或有 `previous_response_id` 才過濾（§8.4） |
| Q5 | Codex 的 hosted 工具（`web_search`、`tool_search`） | 拒絕；剝除並記錄；映射成 provider 自己的搜尋 | **剝除並記錄**。拒絕等於 Codex 永遠不通；映射涉及 provider 端執行，要另做 ADR-490 範圍的決策。注意：剝掉 `tool_search` 後，Codex 用 Claude 時可能載不到延遲載入的 MCP 工具，要寫進 PRD 的已知限制 |
| Q6 | Claude Code 原生直送 | 同意與否，以及四個子題 | **同意**。子題建議：<br>(a) beta 用允許清單（先放 `claude-code-*`、`interleaved-thinking-*`、`context-management-*`、`prompt-caching-scope-*`、`effort-*`、`thinking-token-count-*`、`thinking-display-updates-*`；`dangerous-tool-use-*`、`afk-mode-*` 等語意未審的先不轉）<br>(b) `context_management` 只轉 `clear_*`、拒絕 compaction<br>(c) `metadata.user_id` 不轉送<br>(d) `inference_geo`、`service_tier` 維持 HOLD |
| Q7 | 信封金鑰 | gateway 自有 secret；向 IAM 要簽章服務 | **gateway 自有**（PRD-302 禁止 gateway import IAM 加密；向 IAM 要會多一次 hot path 呼叫）。需要佈建與輪替 runbook，部署時另外授權 |
| Q8 | 一般 dispatch 的跨面翻譯開關 | 沿用 ADR-260 per-scope 開關；新的 per-scope 開關；只有 ops kill switch | **只有 ops kill switch**（例如 `XPARSE_TRANSLATION_FORCE_OFF`）。資料去哪由模型綁定決定，翻譯本身不改變資料去向；ADR-260 開關留給 fallback |
| Q9 | 優先序 | — | 照 §9 的建議順序；Phase 0 量完再定 3b 要不要提前 |
| Q10 | 可見性 | header 名稱與是否對 client 公開 | 稽核一定要有；header 建議 `X-Xparse-Translation`、`X-Xparse-Dropped`，沿用 `X-Xparse-Tools-Stripped` 的長度規則。**opaque app 不送**（Rev.3，#6071） |
| Q11（Rev.3） | ADR-490 Q1：開放 `custom`／`namespace` 工具 | 維持剝除；開放（同時補 guardrail 的 `custom_tool_call` 偵測面，以及 messages 的工具型別保留） | 這是 ADR-490 的決策，本案只依賴它。**建議本案先照「維持剝除」設計**，翻譯路徑與原生路徑一致；Q1 開放後 §8.1 那兩列改成 TRANSLATE。Codex 經 Xparse 今天已靠 shell 改檔，不開放也能用 |
| Q12（Rev.3） | 3a 回給 client 的 thinking signature | 原始 Anthropic signature；包成 `xpenv1` 信封 | **信封**。原始 signature 沒有來源資訊，寫進 client 歷史之後，3b 無法分辨是不是同一個 credential 產生的；信封可以驗證，再決定轉送或剝除 |
| Q13（Rev.3） | SURF-1：非串流 R3 換手成功時的 STARTED | 每次嘗試一筆並加 attempt 編號（改 SPEC-308 §9）；每個請求只一筆（R3 重跑時略過 STARTED） | **每次嘗試一筆＋attempt 編號**。翻譯路徑上，同一個請求的兩次嘗試可能走不同路徑（原生 → 翻譯），處置也不同，按嘗試記才記得清楚。報告也把這題列為要 Peter 決定 |
| Q14（Rev.3） | ADR-221 Amendment B：messages 與 responses 的 `model` 欄位 | 維持 Amendment A 的排除；三個對話面一致回報實際執行的模型 | **一致**（opaque app 仍是 `application_code`）。2b 合成的 Responses 事件本來就要新定規則，趁這次一起定 |

---

## 15. 接手 agent 工作守則

### 15.1 開工 checklist

1. `cd /Users/peter/Desktop/X-parse/xparse && git fetch origin && git rev-list --count HEAD..origin/main`。不是 0 就別信本機舊樹。
2. **在 worktree 裡工作**（例如 `/Users/peter/Desktop/X-parse/pr-worktrees/<slug>`）。主 repo 是多個 job 共用的。**不要用 `git stash`**：所有 worktree 共用同一份 stash。
3. **依序讀**：
   - 本文
   - `docs/LLM_api.md`（§1、§2、§8 的坑）
   - `docs/knowledge_base/23_system_architecture_recovery_guide.md`
   - `docs/草案/解決-v1-response.md` §2.2、§2.3、§8、§15
   - ADR-494 §11、ADR-192 §4.9（:577）、ADR-239、ADR-260 D9、ADR-455、ADR-382、ADR-323、ADR-339、ADR-437
   - SPEC-307、SPEC-308 §9–10、SPEC-304（S0-b）
   - Core-ADR-01、06
4. **設計閉環先行**：Phase 1 的文件 merge 之前不寫產品程式（CLAUDE.md §17.1）。編號會撞號：寫的時候再查最大號，後 merge 的人負責改號。
5. **開 issue 只能走 `/doc-issue`，而且要 Peter 同意**。

### 15.2 每一片

- 先讀 `conftest.py`、既有 fixture 與測試範式，再寫測試；先寫 integration 或 contract test。
- **§8.1**：每條 fallback、except、處置分支，都要有真元件會產生該觸發條件的證據。紅旗：你的 fake 做的正是 handler 要判斷的那件事。
- 新測試檔登記在 `BS/gateway-ci-suite.txt`。
- 跑 gateway 測試：`cd apps/gateway/bustream && python3 scripts/project.py install && python3 scripts/project.py test`（約 7 分鐘、約 9,700 個測試）。
  - 本機已知會紅、main 上也一樣紅的有兩個：FinOps columns-parity、Audit startup contract。原因是 worktree 沒有 checkout `3rd/xparse_audit`。
- **static gates**：照 CLAUDE.md §17.2 #7，比對 `.github/scripts/*.sh` 哪些涵蓋你改的檔，本機跑過再 push。新增 env 要重產 `BS/config/runtime.schema.json`。
- **IAM openapi 改了**：同 PR 重釘六處 consumer digest（§17.2 #7 有清單）。
- **migration**：照 §8.3 expand/contract；砍欄位要拆兩個 release。
- **PR**：
  - base 一律 `main`，不疊 PR；
  - description 附 ADR-093 表與 Core 對比表；
  - `Acceptance-Impact:` 那一行只能是 `none` 或 TC 清單，後面不能接說明；
  - commit 拆開：程式、測試、文件分開；純註解的改動與邏輯分開。
- **zsh 不做 word splitting**：pytest 只印 `in 0.00s` 而沒有 passed 數字，代表一個測試都沒跑。

### 15.3 不要碰

- ADR-494 pipeline 的 stage 順序與處置語意；`.github/scripts/surface-dispositions-gate.py` 的 `RECORD_ONLY_PARAMS`（四張切換票）。
- chat SSE 狀態機（CLAUDE.md §7）。
- ADR-339 對 OpenAI 原生 Responses 的透明轉送。
- prod、rel 部署，以及任何遠端重啟或資料操作。**需要另外授權**；ADR-494 還沒上 prod，部署前還卡 #6068。
- KEY2 app 的模型、政策、綁定。

### 15.4 已知的坑

- **ResponsesBinding 沒有存對話內容**（`IAM/db/models/responses_binding.py:34`），只有 id、租戶、app、模型、憑證、store_flag。
- **gateway 兩個方向都沒帶 thinking `signature`**。3b 一定要等 3a 之後。
- **加新的 OpenAI 形狀 provider 不可併入 factory 的 openai 分支**：endpoint 為空時會繼承 api.openai.com，把 prompt 和別家的 key 送過去（memory `reference_new_inference_provider_touchpoints.md`）。
- **audit extra 會丟掉巢狀 dict**：處置清單要扁平化（memory `reference_audit_extra_drops_nested_dicts.md`）。
- **把函式參數改成必填時，要搜 main 上所有呼叫點**（`docs/LLM_api.md` §8）。
- **Codex 的 `include: ["reasoning.encrypted_content"]` 每個請求都會送**，reasoning item 會逐位元回送。測這題要用推理模型，`gpt-4o` 會得到假陰性。
- **dev gateway 改了 mount 的程式**，validate cache 可能吃舊 snapshot（positive TTL 30 秒，`GW/iam_validate_cache.py`），probe 前重啟 gateway。
- **`/v1/responses` 只轉 `function` 工具**（Rev.3）：`WK/azure_responses_worker.py:73`。Codex 的 `custom apply_patch`、`namespace` 在原生路徑也被剝除（SPEC-304 S0-b、Rev.16），Codex 改用 shell。
- **`/v1/responses` 永遠串流**（ADR-437）：Open Responses 合規測試的非串流項目必紅，不是翻譯 bug。
- **`PARAM_NORMALIZED` 只在 chat 的 primary path 發**：R3 換手那次的處置只有 WARNING log。
- **非串流 R3 會整個重跑 `handle_non_streaming`**（`GW/non_streaming_handler.py:2103`），每次嘗試都發 STARTED（SURF-1）；串流 R3 不會。
- **對話面的錯誤常缺關聯 header**：401（`GW/auth_handler.py:399-404`）兩個都沒有；定址 404 只有 `X-Request-Id`；422（`GW/addressing_refusals.py:186`）都沒有。新增的拒絕要自己帶。
- **opaque app 不能透露背後的模型或 provider**：回應的 `model`、header、錯誤訊息都算（#6071、INV-138-22）。
- **Anthropic 憑證**：10-07 測試時 credit 用完（報告 O-1），使用者回報已補；跑證據前先打一個請求確認。

---

## 16. 風險與取捨

| 風險 | 說明 | 對策 |
|---|---|---|
| 翻譯造成語意損失 | 兩種協定的功能不等價（hosted 工具、加密推理、`stop`） | §8 處置表逐條明定；同家族走原生 |
| 工作量 | 成熟平台的全保真翻譯是萬行級：LiteLLM 光 Messages pass_through 約 11.3k 行，Bifrost 的 Anthropic Responses 轉換一個檔就九千多行 | Phase 0 先確認需求；Phase 2a、3a 便宜先做；2b 只做無狀態；codec 架構讓每多一種協定只多一個模組 |
| 中介格式變成第三套 | 遷移期 chat dict、items、Responses 直通並存 | ADR 寫退場條件；items 只在翻譯層；4d strangler 有明確終點 |
| client 行為不可控 | agent 改版會改送的欄位，例如 Claude Code 一次帶 12 個 beta | 原生路徑讓未知 beta 依允許清單處理；L4 手動重跑；fixture 重錄 |
| 原生路徑的治理覆蓋 | 治理改寫寫不回原生 body | governed delta 判斷＋宣告退路＋記錄（S4）；3c 補遮罩寫回 |
| 跨家族換手 400 | 外家族簽章或加密推理被轉送 | 信封＋主動剝除；矩陣 S09；#4878 |
| 信封金鑰 | 外洩、輪替 | AEAD＋AAD；可多把 kid；驗證失敗就剝除，不中斷 session |
| 延遲 | 多一次翻譯 | 純記憶體轉換；同家族直送 |
| #2783 牽動 IAM 與 Console | 模型身分要改 | 延到 Phase 4；Phase 2 只在 gateway 由 provider × endpoint 推導 |
| 與 ADR-494 部署撞期 | ADR-494 尚未上 prod | Phase 1 只寫文件；2a 是疊加型；動到 Responses 管線的 2b 等 ADR-494 在 prod 穩定後再上 |
| 翻譯層比原生路徑寬（Rev.3） | 原生路徑因治理剝掉的東西（`custom`、`namespace`），翻譯路徑卻轉送過去 | 翻譯路徑一律先經入口視圖的治理（P1）；§8.1 那兩列依 ADR-490 Q1 |
| opaque app 從翻譯資訊洩漏 provider（Rev.3） | header、REJECT 訊息、`response.model` 都可能透露背後是哪一家 | §7.4 共用 render 規則；§7.9 opaque app 不送 header |
| 新路徑重演「每個 route 各做一次」（Rev.3） | 報告的 SURF-2、§4(a)、O-1 都是這一類 | §7.4 header、`model`、錯誤分類由共用層決定；G5 |

---

## 附錄 A　程式證據索引（xparse `4a4a93331`）

| 主題 | 位置 |
|---|---|
| messages 入口翻譯 | `GW/anthropic_translation.py`：:38 `_UNSUPPORTED_TOOL_PREFIXES`、:48 `_UNSUPPORTED_BETA_PREFIXES`、:84 `_system_to_text`、:107 `_content_blocks_to_openai_user`、:142 `_messages_to_openai`、:157 只保留 text／image、:205 `_tools_to_openai`、:226 `_has_cache_control_intent`、:300 `output_config_reasoning_effort`、:322 `to_openai_chat`、:398 `_openai_message_to_blocks`、:458 `OpenAIToAnthropicStreamBuilder`、:622 `_content_block_events`。全檔 0 處 `signature` |
| messages route | `GW/routes/messages.py:421`（`to_openai_chat`）、`:468`（`execute_chat`） |
| messages adapter | `GW/surface_adapters/chat.py:353` `MessagesSurfaceAdapter`（「chat core over the translated request」） |
| Adapter Protocol | `GW/surface_adapters/protocols.py` |
| Anthropic worker | `WK/anthropic_worker.py`：:162-164 `cache_passthrough`、:280-286 system 斷點、:299-307 thinking、:339-381 cache usage、:402-406 `thinking_delta`。全檔 0 處 `signature` |
| Claude 家族正則 | `BE/param_capabilities.py:175` `CURRENT_CLAUDE_SURFACE_RE` |
| chat→Responses 翻譯 | `GW/cross_surface.py`：:60、:66、:108、:180、:215、:236 |
| D10 | `BE/responses_bridge.py`；`GW/worker_setup.py:448` `_resolve_responses_bridge`、:919 `apply_responses_bridge`、:1037、:1039-1062 translate block |
| API 面耦合 | §4.4 全表 |
| Responses worker | `WK/azure_responses_worker.py`：:91 `_USAGE_TERMINALS`、:213 `_filter_tools`、:384 `_raw_events`、:409 `stream`、:422 `stream_events`（`__binding__`）；`normalize_outbound_store`（省略 → `(True, "default")`）。`WK/openai_responses_worker.py:111`、:225 |
| Responses 建 worker | `GW/responses_stream.py:126` `create_responses_worker`；`GW/responses_resilience.py:288` |
| Chain 驗證 | `GW/responses_chain_validator.py:76`（`unknown_response_id`） |
| Worker chunk 契約 | `WK/base_worker.py:111`、:134、:160 |
| 請求欄位去向 | `GW/request_fields.py`：:99（Responses `context_management` REFUSE）、:163-185 `MESSAGES_FIELDS`、:189、:278-292 refusal 理由 |
| 工具剝除 | `GW/responses_tools_filter.py:82` `platform_stripped_tools`；`GW/tools_stripped_header.py:39` `X-Xparse-Tools-Stripped` |
| 治理改寫點 | `GW/chat_tool_governance.py:83-90`（剝工具）；`GW/guardrail_detection.py:508-511`（chat 遮罩寫回）、:614（Responses item） |
| client 特判 | `GW/routes/models.py:62`；`GW/tool_result_status.py:117` |
| usage 欄位 | `GW/terminal_usage.py:100-134`（`cached_tokens`、`cache_write_tokens`） |
| 能力資料樣板 | `IAM/migrations/0364_model_reasoning_effort_levels_adr396.py`；`IAM/db/models/provider.py:374` `class Model`；`GW/iam_http_client.py:749`、:2447；`BE/reasoning_levels.py` |
| IAM 面設定 | `IAM/api/ninja_api/_providers.py:240`、:256、:289、:307、:367（ADR-323 D2）；`IAM/domain/value_objects/provider_surface.py`；`IAM/application/use_cases/application/inference_target.py:48`、:53 |
| ResponsesBinding | `IAM/db/models/responses_binding.py:34`（無對話內容） |
| Responses 工具保留規則（Rev.3） | `WK/azure_responses_worker.py:73` `ALLOWED_TOOL_TYPES = {"function"}`、`:76` `is_forwarded_tool`；開放 custom 的前置條件 `docs/spec/SPEC-304-tool-governance-behavioral-contracts.md:893`；Rev.16 `:931`；guardrail 只掃 `function_call` `GW/guardrail_detection.py:322`；messages 工具一律壓成 function `GW/anthropic_translation.py:205` |
| 定址與拒絕（Rev.3） | `GW/addressing_refusals.py:161` `runs_on`（只由 `GW/model_addressing.py:109` 呼叫；unary 面走 `decide_unary_addressing`）、`:186` 422 沒有 header；`GW/auth_handler.py:399-404` 401 沒有 header；`GW/unary_execution.py:190` `with_correlation_headers` |
| R3 與 STARTED（Rev.3） | `GW/non_streaming_handler.py:777`（STARTED）、`:1445`（呼叫 fallback）、`:2032` `_execute_fallback_non_streaming`、`:2103`（重跑 `handle_non_streaming`）；`GW/fallback_handler.py:67-74` `FALLBACK_ELIGIBLE_CODES` |
| 處置紀錄（Rev.3） | `GW/param_normalization_audit.py:10`（只在 primary path）、`:30` `MAX_RECORDED_NORMALIZATIONS = 20`、`:33` `normalization_fields`、`:96`（`trace_id`，#5981） |
| 回應 `model`（Rev.3） | `GW/routes/messages.py:487`（串流）、`:503`（非串流）用 `req.model`；`docs/adr/ADR-221-model-identity-reconciliation-response-model-layer.md:3`、`:138-146`（Amendment A） |
| 測試與 gate | `BS/gateway-ci-suite.txt`；`BS/tests/conformance/harness.py`、`conftest.py`；`BS/tests/unit/test_param_capabilities.py`（AST 守門範本）；`.github/scripts/surface-dispositions-gate.py`、`surface-conformance-gate.py`、`request-field-dispositions-gate.py`、`provider-endpoint-value-gate.py`、`provider-call-usage-parity-gate.py`、`usage-ledger-surface-parity-gate.py` |
| env schema | `BS/config/runtime.schema.json` |
| 文件 | `docs/adr/ADR-192-responses-api-phase1-architecture.md:577`（§4.9）；`docs/adr/ADR-323-azure-surface-authority-and-cross-surface-determinism.md`（D2）；`docs/adr/ADR-382-claude-backend-prompt-cache-client-intent-passthrough.md`（INV-382-1）；`docs/spec/SPEC-307-request-field-dispositions-contracts.md`（§0.2） |

## 附錄 B　實測證據

| 來源 | 內容 |
|---|---|
| `TST/results/effort_lane_20261006-221720/wire_cc.jsonl`、`analysis.json` | Claude Code 2.1.291 的請求：頂層欄位、`thinking: adaptive + display: updates`、3 處 `cache_control`、`context_management.clear_thinking_20251015`、12 個 beta、gateway 處置紀錄（§4.5）。每格 1 個請求，單輪 |
| `TST/results/effort_lane_20261006-{163702,164843,192136,192305,215414}/wire_codex.jsonl` | Codex 的 Responses 請求：15/15 帶 `web_search`；依模型帶 `custom`（`apply_patch`）；另有 `tool_search`；`include: ["reasoning.encrypted_content"]`、`store: false`、沒有 `previous_response_id` |
| memory `reference_codex_is_responses_only_and_stateless.md` | Codex 0.154：只講 Responses；`store=false`；不送 `previous_response_id`；`include` 每次都送；reasoning item 逐位元回送（跨 user turn 與 tool loop 都會）；攔截配方 |
| ADR-437 Amendment A；`docs/research/poc/responses-terminal-shapes-2026-10-03/` | Codex 對擋下格式的反應（16 種終端形狀實測）；`output_item.done` 當下就執行工具；終止 code 集合；refusal 會整則丟掉 |
| memory `reference_agent_client_http_status_retry_behaviour.md` | Codex 的終止 HTTP 狀態只有 {400, 429} |
| `docs/LLM_PROXY.md` §22.3 | D10 對真 OpenAI 的驗證（chat ↔ Responses，同一把 key） |
| `TST/results/e2e_20261006/REPORT.md` | 六個面、91 case、三個 agent CLI 的 e2e。`:74` Codex s3：「沒有可用的 apply_patch 工具，只能走 shell」（Rev.3） |
| `docs/測試報告/llm-api.md`（Rev.3） | 2026-10-07 surfaces lane：六個面 91 case（88 PASS、0 個真失敗）、17 個修正 VERIFIED、SURF-1、SURF-2、O-1..O-9。結果在 `TST/results/e2e_20261007/surfaces/`。摘要見 §4.8 |
| openresponses.org/compliance（2026-10-07 查，Rev.3） | 瀏覽器 10 項：3 項明確非串流、1 項 SSE、2 項 compaction、其餘頁面沒寫明；CLI 7 項全是 WebSocket |

## 附錄 C　外部平台證據（研究 agent 2026-10-07 讀碼；**引用前在 clone 內重開該行確認**）

路徑相對於各 clone 根目錄（§6 表）。

### LiteLLM（`39d14bd`）

| 主題 | 位置 |
|---|---|
| Messages 入口決策樹 | `litellm/llms/anthropic/pass_through/messages/handler.py:564-632`：原生條件 :92-102、:571-580；Responses 只給 `{"openai"}` :45-47、:73-89；其餘 chat :612-632。Azure 走 chat，再被 chat→Responses 重橋（`litellm/main.py:1180-1188`） |
| 原生路徑的治理 | 路由前在原生 body 上做（`litellm/proxy/common_request_processing.py:2202-2207` vs 路由 :2610）；中立掃描＋依位置寫回、數量不符就 raise（`litellm/llms/anthropic/chat/guardrail_translation/handler.py:85-125, 496-521, 604-624, 668-669, 1072-1124`）；thinking、document block 不掃（:1008-1014）；未登記型別跳過（`litellm/proxy/guardrails/guardrail_hooks/unified_guardrail/unified_guardrail.py:222-226`） |
| 信封與跨家族 | `litellm/litellm_core_utils/prompt_templates/common_utils.py:1943-2085`（`litellm_encrypted_reasoning:` 前綴；Anthropic 簽章 → 只留 summary 的 Responses reasoning :2057-2084）；Gemini 簽章藏在 `tool_call_id` 的 `__thought__<sig>`（`litellm/litellm_core_utils/prompt_templates/factory.py:72-75, 1163-1219`）；400 invalid signature 後重試（`litellm/llms/base_llm/anthropic_messages/transformation.py:150-178`；`litellm/llms/custom_httpx/llm_http_handler.py:1914-1930`） |
| 加密推理親和 | `litellm/router_utils/pre_call_checks/encrypted_content_affinity_check.py:4-9, 171-221, 296-336`；預設關（`litellm/router.py:2219-2262`）；標籤是明文 base64（`litellm/responses/utils.py:385-432, 467-556`） |
| Responses → chat | `litellm/responses/litellm_completion_transformation/transformation.py`：items :1375-1431、:1489-1558、:1719-1725；tools :1985-2048；`include`、`store`、`truncation` 不讀；session 沒設時默默只送新輸入 :549-557 |
| custom 工具 | `litellm/responses/litellm_completion_transformation/custom_tools.py:96-151, 169-213`；回程 `transformation.py:2196-2207`；串流用 function 事件（`streaming_iterator.py:288-296`） |
| 串流合成 | `litellm/responses/litellm_completion_transformation/streaming_iterator.py:104-149`；`response.created` 寫死 `store:true`（:513）；`sequence_number` 缺漏（:745-795、:1191-1196） |
| session 模擬 | `litellm/responses/litellm_completion_transformation/session_handler.py:266-320`；需要 `store_prompts_in_spend_logs`（`litellm/proxy/_types.py:2931-2934`） |
| response id | `litellm/responses/utils.py:602-665`；id 加密與擁有權（`litellm/proxy/hooks/responses_id_security.py:145-200, 272-303`） |
| cache 斷點 | 逐元素複製（`factory.py:1845-1859`；`litellm/llms/anthropic/chat/transformation.py:849-862`）；Gemini 合成一個（`litellm/llms/vertex_ai/context_caching/transformation.py:24-49`） |
| 不支援參數 | 預設 raise（`litellm/utils.py:4467-4509`；`litellm/exceptions.py:945-957`）；對 Claude Code、Codex 的 UA 自動 drop（`litellm/proxy/litellm_pre_call_utils.py:858-871, 2447-2448`）；drop 不記錄（`litellm/utils.py:4487-4489`） |
| 能力資料 | `model_prices_and_context_window.json`（42 個 `supports_*`；`supported_endpoints` 954 筆，198 筆同時列 chat＋responses，84 筆只有 responses）；Bedrock Mantle 只改 JSON、不比對名稱（`litellm/llms/bedrock_mantle/common_utils.py:130-145`）；執行期從 GitHub 抓（`litellm/__init__.py:425-427`） |
| client 怪癖模組 | `litellm/llms/base_llm/responses/codex_compat.py:1-18` |
| config-only provider | `litellm/llms/openai_like/providers.json`、`README.md:17-60`（30 家） |
| 測試 | `tests/llm_translation/base_llm_unit_tests.py:65-1475`（共用套件）；VCR Redis 24h（`tests/llm_translation/Readme.md:5-21`）；假上游 wire 契約（`tests/integration/README.md:3, 19, 31`）；Claude Code 矩陣（`tests/e2e/claude_code/manifest.yaml:1-35`）；三面對話矩陣（`tests/e2e/llm_translation/conversational_matrix.py:1-10, 108-133`） |

### Bifrost（`ed9869f73`）

| 主題 | 位置 |
|---|---|
| tagged union | `core/schemas/bifrost.go:622-678`；回應 :1200-1212 |
| chat schema 與延伸 | `core/schemas/chatcompletions.go:198-250`、`reasoning_details` :1801-1818、cache 標記 :1311-1333、document→file :1335-1345、`ExtraParams` :248-250 |
| Responses schema | `core/schemas/responses.go:42-59, 1496-1545`；`signature`、`encrypted_content` :1920-1927、:2646-2649 |
| 入口轉 Responses | `transports/bifrost-http/integrations/anthropic.go:131-146`、`genai.go:137-140`、`bedrock.go:40-51`；OpenAI → chat `openai.go:412` |
| 窄原生直送 | `integrations/anthropic.go:899-901`；`core/providers/anthropic/utils.go:4566-4571`；raw 改寫器 `integrations/anthropic.go:386-466`、`core/schemas/redaction.go:10-43`、`integrations/rawrequestredaction.go:109-160`；跨家族 fallback 關 raw `core/bifrost.go:7201-7234` |
| 工具 | custom → 空 schema tool（`core/providers/anthropic/responses.go:9088-9111`）；hosted 對應表（`core/providers/anthropic/utils.go:140-181`）；namespace 攤平還原（`core/bifrost.go:7998-8030, 8175-8202`） |
| id 夾帶 | `core/providers/utils/utils.go:39-42, 95-170` |
| 400 後才剝 | `core/encryptedreasoning.go:151-189`；`core/bifrost.go:7093-7121` |
| 降級欄位 | `core/schemas/bifrost.go:1898-1904`；`plugins/compat/main.go:161-221` |
| 胖介面 | `core/schemas/provider.go:691-814` |
| 能力資料 | `core/schemas/modelcapabilities.go:24-104`；只用模型名當 key（`framework/modelcatalog/pricing.go:46-51`、`framework/modelcatalog/datasheet/store.go:327-334`） |
| custom provider | `core/schemas/provider.go:338-402, 543-551` |
| 測試 | `core/internal/llmtests/account.go:30-108`；`tests/integrations/python/config.yml:9-21, 265, 657-707`；`tests/e2e/clis/README.md:1-5`；跨 provider 換手測試被 skip（`core/internal/llmtests/cross_provider_scenarios.go:112, 157, 201`） |

### Portkey（`669825cb`）

| 主題 | 位置 |
|---|---|
| hooks 只跑四種請求型別 | `src/middlewares/hooks/index.ts:449-464`；出錯放行 :271-273 |
| strict 模式 | `src/handlers/services/requestContext.ts:99-108`（預設 true） |
| thinking 與簽章承載 | `src/providers/anthropic/chatComplete.ts:143-161, 597-601` |
| 宣告式參數表 | `src/providers/types.ts:19-32`；`src/services/transformToProviderRequest.ts:75-127` |
| 入口限制 | 沒有 messages 設定 → 500（`src/services/transformToProviderRequest.ts:157-159`）；Responses 只給 OpenAI 系（`src/providers/openai/index.ts:65`） |
| OpenAI 相容 provider | 約 38 行（`src/providers/cerebras/index.ts:6-19`） |

### One-API（`8df4a26`）

| 主題 | 位置 |
|---|---|
| Adaptor 介面 | `relay/adaptor/interface.go:11-21` |
| 封閉 pivot | `relay/model/general.go:24-69` |
| 只在沒有治理改寫時送原文 | `relay/controller/text.go:90-98` |
| Claude 損失 | `relay/adaptor/anthropic/model.go:44-57`；`relay/adaptor/anthropic/main.go:212-214` |

### vLLM（`92044241a0`）

| 主題 | 位置 |
|---|---|
| Anthropic 轉 chat | `vllm/entrypoints/anthropic/serving.py:318-345`；串流重新解析 chat SSE 文字 :993-1010；簽章丟掉 :486-493；回程簽章是 `uuid4` :851, 909, 938-953；`cache_control` 消失（`tests/entrypoints/anthropic/test_anthropic_messages_conversion.py:811-874`） |
| Responses 狀態 | store 預設關（`vllm/envs.py:268`）；`store=true` 默默降級（`vllm/entrypoints/openai/responses/serving.py:352-359`）；未知 id 404（:362-367）；記憶體 store 自承 leak（:160-196） |
| Responses 工具與推理 | custom、hosted 被剝（`vllm/tool_parsers/utils.py:201-218`）；input 帶 `encrypted_content` 會 400（`vllm/entrypoints/openai/responses/utils.py:296-301`） |
| 串流 | 狀態機 `vllm/entrypoints/openai/responses/streaming_events.py:804-808, 1158-1188`；單一 `sequence_number` 來源 `serving.py:1336-1346` |
| parity 與 dry-run | `tests/entrypoints/openai/test_render_parity.py:3-16, 265-317`；`vllm/entrypoints/scale_out/render/api_router.py:28-120` |
| parser registry | `vllm/reasoning/abs_reasoning_parsers.py:216-359`；`vllm/parser/response_template.py:135-159` |
| Codex 文件 | `docs/serving/integrations/codex.md:13-15`（宣稱可直接接，但 custom、web_search 被剝） |

## 附錄 D　相關 issue／discussion（2026-10-07 查）

| 編號 | 狀態 | 內容 |
|---|---|---|
| Discussion #2527 | open | 通用跨平台轉譯層：願景＋目標矩陣（本文的上層） |
| Discussion #2504 | open | chat ⇄ responses 雙向轉譯（機制） |
| #2497 | — | Anthropic Messages → Azure Foundry／Responses（#2527 列為子場景） |
| #2783 | OPEN | API 面寫死在 Model identity（provider）上 |
| #2551 | OPEN | chat 入口打 responses 面模型（現回 422） |
| #5528 | OPEN | Responses → Chat 反向轉譯 |
| #5525 | OPEN | Foundry ↔ Responses |
| #4878 | OPEN | R3 跨模型 failover 可能把憑證 A 的加密推理送給憑證 B |
| #2571 | OPEN | aif gpt-5.5 撞名 RCA（ADR-323 D4） |
| #5984 | — | stop 送到 luna |
| #6064–#6068 | — | 見 `docs/LLM_api.md` §6 |

## 附錄 E　修訂紀錄

### Rev.4（2026-10-08）：轉為正式文件，九片全部落地

**交付對照**（全部 base main、squash merge）：

| 片 | PR | 內容 |
|---|---|---|
| P1 | #6114 | PRD-350、ADR-503、SPEC-312 與各 amendment |
| P2 | #6123 | 每次路由嘗試一筆 STARTED、各自的 provider context（Q13） |
| P3 | #6158 | `serves()`、原生優先候選池、2a-1、2a-2 |
| P4 | #6154 | 對話面錯誤帶兩個關聯 header（G5） |
| P5 | #6161 | messages／responses 回報實際執行的模型（Q14） |
| P6 | #6155 | Anthropic／Bedrock 的 finish_reason bugfix |
| P7 | #6170 | 3a：thinking 簽章信封 |
| P8 | #6190 | 2b：`/v1/responses` 經翻譯打 Claude 與 chat 系模型 |
| P9 | #6218（`b32114bc5`） | 3b：`/v1/messages` 打 Claude 原生直送 |

Phase 0（真 Claude Code 量快取）另外修出四個既有缺陷：#6195（Anthropic 把 Claude Code 的整段 system prompt 丟掉：billing 行被併進第一塊）、#6197（`input_tokens` 的語意）、#6203（claude-haiku-5 不在現行家族清單）、#6207（圖片送 Claude 一律 400）。

**本檔哪裡錯了**（實作時才發現；正式文件已改，依本檔寫查詢或程式的人要改）：

1. 編號：PRD-345 → **PRD-350**（撞號）；ADR-501 → **ADR-503**（被 MCP #6110、#6115 先佔）。
2. §7.7 的 Responses 信封：「一個回應一個信封、整包還原到回合開頭」會重排 interleaved thinking，改成每個 reasoning item 一個、原位還原（SPEC-312 C-312-29）。
3. §9 3b 的 `native_fallback_reason`：沒有 `fallback_cross_family` 這個值；出口不是 Claude 家族的嘗試記 `translated`、不記原因（C-312-32）。
4. §9 3b 的 seam 投影：原生 body 不能自己重做一份 effort／budget／temperature 規則，要直接套 seam 對這次嘗試的決定，否則漏掉模型可接受的 effort 等級、thinking 與 sampling 的互斥（ADR-503 Rev.3）。
5. §8.2 沒料到的兩條：Claude Code 不管指名哪個模型都會送對話中途的 `role: system`，舊款 Claude 收到會 400，原生路徑要依模型能力判斷；`tool_result` 裡和文字並存的 document／image 不在治理視圖內，原樣轉送會繞過 rail。

**S6（同家族保真）的實測**：真 Claude Code 2.1.293 × claude-haiku-5-5，原生路徑每輪快取讀取 45／92／93／94／95%；直連 Anthropic 73／89／91／92／93%；翻譯路徑（修 billing 行後）38／63／54／47／42%。

**仍開著的**（皆已上敏捷看板，Sprint 待 Peter 定）：#6196（Claude 在原生以外的路徑沒有 cache，含 Codex）、#6198–#6202、#6204–#6206、#6217（Responses wire 無聲剝除非 function 工具）。

Rev.3 全文的備份：`/private/tmp/claude-501/-Users-peter-Desktop-X-parse-xparse/63bac011-e947-4a2b-a00f-c8fe3eb3c1dc/scratchpad/llm_proxy_統一.rev3.backup.md`（session 暫存區，會被清掉）。

### Rev.3（2026-10-07）

依據：同日的 surfaces lane 測試報告（`docs/測試報告/llm-api.md`）。報告測的是治理軸，沒有測跨 wire 的格子；它帶出的事實整理在 §4.8（F1–F11）。

**事實更正**：

1. `custom`、`namespace` 工具今天在 `/v1/responses` 的原生路徑也被剝除（S0-b）。Rev.2 §8.1 把它們標 TRANSLATE、寫「Codex 能改檔全靠這一列」不成立；改成依 ADR-490 Q1。
2. Rev.2 §4.3 說非 `function` 工具「無聲濾掉」已過時：S0-b（#5618）起有 `platform_tool_stripped` 與 header。
3. ADR-221 已有 Amendment A（2026-10-07，#6067），明文把 messages、responses 排除在「回報實際執行的模型」之外。Rev.2 §5 只寫 Proposed。

**新增與修改**：

- §0 三個坑；§2 R3 但書、S7（回應層一致）；§4.2、§4.3、§4.6 補充；**§4.8 報告摘要**。
- §5：更新 ADR-490、ADR-437、ADR-221 三列；新增 SPEC-308、#5667、opaque app 三列。
- §7.4 回應層橫切規則；§7.5 REJECT 的位置；§7.6 能力缺值語意；§7.7 3a 信封決策與外家族 thinking；§7.9 改成沿用 `PARAM_NORMALIZED`、opaque app 不送翻譯 header。
- §8.1、§8.2、§8.4 對應修改。
- §9：Phase 0 前置（Anthropic 憑證、Q11、Q13）；1.7 沿用報告 harness 的檢查；2a-3 拒絕帶 header；2b 證據 #2、#3；3a、3b 補充。
- §10 G5；§11 的 S09、S12 與腳本；§12、§13 對應修改；§14 Q11–Q14；§15.4、§16 新增條目；附錄 A、B 補證據。

Rev.2 全文的備份：`/private/tmp/claude-501/-Users-peter-Desktop-X-parse-xparse/e23ddbee-5648-403f-b901-80807369b5c0/scratchpad/llm_proxy_統一.rev2.backup.md`（session 暫存區，會被清掉；要保留請自行複製）。

### Rev.2（2026-10-07）

**事實更正**：

1. ResponsesBinding **沒有**存對話內容。Rev.1 §4.3 說「用既有 ResponsesBinding 存的歷史模擬 `previous_response_id`」是錯的（證據：`IAM/db/models/responses_binding.py:34`）。
2. hosted 工具「明確拒絕」會讓 Codex 永遠不通：實測 15/15 個請求都帶 `web_search`。改成剝除並記錄。
3. 「Responses 是 chat 的超集」是錯的：chat 有 `stop`、`seed`、penalties，Responses 沒有。
4. claude × messages 的 ✅ 只來自單輪 effort probe；隱性損失見 §4.5。
5. Phase 3 的工作量高估了：chat→Responses 翻譯器已存在，而且 D10 已對真 OpenAI 驗過；擋住的是過濾函式。

**新增**：

- 既有決策表（§5）：ADR-192 §4.9 衝突、Discussion #2527、ADR-323、ADR-382、ADR-269。
- 五家外部對照（§6、附錄 C）。
- 目標架構改版（§7）：治理吃視圖、items 中介格式、一 wire 一 codec、原生直送、信封、client profile、可觀測性。
- 處置表初稿（§8）；切片級實作計畫（§9）；gate（§10）；四層測試（§11）；ADR-093 表（§12）；Core 對比表（§13）。
- 決策題（§14）更新為 Q1–Q10；接手守則（§15）。

**移除**：Rev.1 §4.2 圖中「CanonicalRequest 在治理之前」的畫法。

Rev.1 全文的備份：`/private/tmp/claude-501/-Users-peter-Desktop-X-parse-xparse/240df5e7-b85c-4dbd-b44c-e0c9f46f128e/scratchpad/llm_proxy_統一.rev1.backup.md`（session 暫存區，會被清掉；要保留請自行複製）。

### Rev.1（2026-10-07）

初版：問題（R1、R2）、三層名詞、相容性矩陣、effort 樣板、根因、建議（不另蓋服務）、Phase 0–4、決策題 Q1–Q4。
