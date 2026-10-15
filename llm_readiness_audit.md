# LLM Proxy 現況稽核與改善建議（2026-10-13）

> **給誰**：Peter，以及接手這條線的 LLM／工程師。讀完要知道三件事：現在做到哪裡、哪些地方還會咬到使用者、開始做 tool／MCP／sandbox policy 之前該先收什麼。
> **基準**：`origin/main` `0925e5a13`（2026-10-13 12:22）。repo 根目錄 `/Users/peter/Desktop/X-parse/xparse`；下文 `B/` = `apps/gateway/bustream/`，`G/` = `apps/gateway/bustream/gateway/`，`IAM/` = `apps/iam/xparse_iam/xparse_iam/`。
> **方法**：兩輪唯讀工作。第一輪 7 個面向各派一個 agent 讀碼、跑 gate、查 issue，再各派一個專門反駁的 agent 逐條核對（153 條結論，另補 37 條漏掉的）。第二輪對照 LiteLLM、Bifrost、Portkey、one-api、vLLM 的原始碼找改善做法，同樣每個主題再挑戰一次。
> **限制**：沒有打 gateway、沒有跑測試套件、沒有碰 rel／prod。所以這份是「程式碼、gate、git、issue 的現況」，不是新的實機驗證。10-12～13 合併的修正組合，到今天都還沒用真的 Claude Code／Codex／OpenCode 重跑過。（10-14 已在本機 `bff643332` 用三個真 CLI 重跑，見 §12）
> **權威來源**：repo 內 `docs/` 的 ADR／SPEC／PRD。本文與它們衝突時以它們為準。
> **10-14 註**：§0–§10 是 10-13 的快照。之後合併的 30 支（§11、§13）修掉的項目沒有逐條回寫，只在 §1.4、§4、§5、§8.2、§10、§12 幾處加了「（10-14 已由 #NNNN 處理）」；要看某一條現在的狀態，先查 §11.1 與 §13 的表。
> **逐條證據**：`docs/llm_readiness_audit-evidence/audit.json`（稽核）、`improvements.json`（改善提案）。下文括號裡的 `A-8`、`E-M1` 這類代號是 `audit.json` 裡的條目編號。

---

## 0. 三十秒版

- **`main` 上「使用者能用」這一層差不多做完。** 13 個 provider 在三個入口（chat、messages、responses）結構上都有路可走；送出前的治理是三個面共用一條流程、一個結尾，有 gate 鎖住。
- **可以開始 tool／MCP／sandbox policy 的設計**，但開工前建議先收 5 件事（§6），多數是決策或驗證。
- **prod 完全沒有這條線**（v1.76.4，落後 main 1261 個 commit）；**rel 是半套**（有「Codex 打 Claude」，沒有 #6360，Codex 預設設定在 rel 會拿到 0 個工具卻回 200）。
- **真 agent 驗過的 provider 只有三家**：Anthropic 直連、OpenAI 直連、DeepSeek。Gemini 在 agent 情境實質不可用；Bedrock、Azure、vLLM、Foundry 只有測試。
- **「限制」多數預設不擋**（shadow 或被 rel 扣住），符合「先能用」的順序。**「記錄」做到了**，但有四項金額會錯、一類稽核事件發不出去。
- **`/v1/responses` 的根因修掉一半**：送出前的治理不會再漏接；回應端（串流中）的邏輯仍是每個面各寫一份、沒有 gate。新的 tool／MCP policy 大多是回應端判定，正好落在這塊。

各問題的結論（7 個面向的結論在反駁後都維持「大致完成」，沒有一個被推翻）：

| 問題 | 結論 |
|---|---|
| 1. 三種 agent 能不能用不同 provider 的模型 | 結構上都通；實測只有三家；Gemini 有實質缺口 |
| 2. 新增 provider／agent 快不快 | OpenAI 相容的快（約 10 檔）；其他不快。coupling 中等 |
| 3. 新增影音這類 API 面快不快 | 同步型的面快；影片輪詢、realtime、batch 要新的執行家族 |
| 4. audit／cost／routing／policy | 記錄做到；限制都接上但預設不擋；四項金額會錯 |
| 5. `/v1/responses` 以前的問題 | 送出前那一半修掉了；回應端那一半沒有 |

---

## 1. 三種 agent × 不同 provider（問題 1）

### 1.1 每個 provider 在三個入口怎麼走

依 `B/translation/capabilities.py::serves()` 與 `B/streaming/workers/factory.py`。「原生」＝入口協定就是模型自己講的；「翻譯」＝gateway 轉一次；「bridge」＝ADR-455 改打 Responses API。

| provider | chat（OpenCode、SDK） | messages（Claude Code） | responses（Codex） | 真 agent 實測 |
|---|---|---|---|---|
| `openai`（api.openai.com） | 原生；gpt-5.4+ 帶工具且開 reasoning 時 bridge | 翻譯；同樣會 bridge | 原生 | 有 |
| `openai`（自架端點）、`openai_compat` | 原生 | 翻譯 | 翻譯（只限無狀態） | 無 |
| `openai_responses` | 翻譯 | 翻譯 | 原生 | 有 |
| `azure_openai` | 原生；**沒有 bridge** | 翻譯 | 翻譯 | 無 |
| `azure_openai_responses` | 翻譯 | 翻譯 | 原生 | 無 |
| `azure_ai_inference`（Foundry） | 原生 | 翻譯 | 翻譯 | 無 |
| `deepseek` | 原生 | 翻譯 | 翻譯 | 有 |
| `vllm` | 原生 | 翻譯 | 翻譯 | 無 |
| `anthropic` | 翻譯 | **原生直送**；例外情況退翻譯 | 翻譯（只限無狀態） | 有（主要是 claude-haiku-5-5） |
| `google`、`vertex_ai` | 原生（worker 內轉換）；**圖片靜默丟掉** | 翻譯 | 翻譯 | 無 |
| `bedrock` | 原生（worker 內轉 Converse） | 翻譯；Bedrock 上的 Claude 不算原生 | 翻譯 | 無 |
| `ollama` | 不能用（沒有 worker，IAM 只讓存憑證） | 不能用 | 不能用 | — |

### 1.2 確認成立的

- 「哪個入口能用哪個模型」只有一個答案來源（`serves()`），定址、路由候選池、每次嘗試三個地方都讀它（A-3）。
- Codex 打 Claude、DeepSeek、vLLM 等非 Responses 模型已接上，只限無狀態請求（A-4）。
- Claude Code 打 `provider=anthropic` 走原生直送：body 原樣上游，含 `cache_control`、thinking 簽章、成對的 beta（A-5）。
- 翻譯矩陣 9 格 × 12 情境：80 項通過、28 項明確不支援、0 項已知缺口；四支 gate 與 self-test 全綠（A-19）。
- IAM 與 gateway 的 provider 名單一致，沒有「IAM 能建模型但 gateway 沒 worker」的情況（A-2）。

### 1.3 缺口與風險

| # | 問題 | 嚴重度 | 位置 |
|---|---|---|---|
| A-8 | **Gemini 在 agent 情境實質不可用**：user 訊息裡的圖片被靜默丟掉，模型在沒看到圖的情況下回答；3.x thinking 模型多輪工具缺 `thoughtSignature`，provider 回 400 | P1 | `B/streaming/workers/google_worker.py:263-281`、`:26-34` |
| A-M2 | 結構化輸出（`response_format`）在 `google`、`vertex_ai`、`azure_ai_inference` 被靜默丟掉，沒有任何紀錄 | P2 | `B/streaming/workers/factory.py:565-596`、`:789-830` |
| A-12 | `/v1/responses` 的結構化輸出打 Claude 不通，錯誤訊息還誤導（回一般的 422）；同一個需求從 chat 入口打 Claude 卻有支援 | P2 | `B/translation/capabilities.py:180-182` |
| A-7 | Azure chat 上的 gpt-5.5+ 帶工具沒有 bridge。OpenAI 直連這個組合會 400（所以直連才有 bridge）；Azure 是否同樣拒絕沒驗過 | P2（未驗證） | `B/backend/responses_bridge.py:136-139` |
| A-M1 | client 的 `max_tokens` 不夾模型上限：Claude Code 送 32000 以上，路由到上限較低的模型時是 provider 的 400，不換模型 | P2（設計如此） | `G/worker_setup.py:993-994` |
| A-21 | Claude「現行家族」是封閉清單，下一個新家族（例如 claude-opus-6）會被當成舊款送出不收的參數而 400。這種清單在 #6203 已經壞過一次 | P2 | `B/backend/param_capabilities.py:200` |
| A-22 | 真元件證據很窄：Bedrock、Azure 三條 wire、vLLM、Foundry、Gemini 在三入口矩陣上都沒有真 agent 實測 | P1（風險） | — |
| A-14 | 宣告式的欄位處置表只涵蓋 9 格裡的 3 格；其餘 6 格的欄位處置散在各 worker 裡 | P2 | `B/translation/dispositions.py` |
| A-20 | 矩陣有兩段過期敘述（仍寫 `/v1/messages` 拒絕 web_search、S05 是剝除） | P3 | `B/tests/conformance/translation_matrix.py:78-89` |

### 1.4 使用者感覺得到的落差（都是設計如此或已宣告）

- **Claude Code 的文字要等回合結束才一次出現**，生成期間線上只有 ping（ADR-239 §2.1 D2；`G/anthropic_translation.py:721-734`）。這是三個入口裡最直接的體感落差。（10-14 已由 #6475 處理一半：非 Claude 模型在條件都成立時逐段送出；Claude 仍整回合）
- **`/v1/responses` 沒有非串流**：`stream: false` 也回 SSE，一般 SDK 的非串流用法與 `responses.parse()` 不能用；Codex 不受影響（`G/routes/responses.py:266`、`:359-366`）。
- **`/v1/responses` 只有 POST 與 DELETE**：沒有 `GET /v1/responses/{id}`、沒有 compact；`background`、`conversation`、`prompt` 一律 400。
- **混合 pool 上 Codex 的自動路由**：只在「本面候選」裡選。pool 裡只要有 Responses-only 模型，Claude、DeepSeek、一般 `openai` 列都只能靠指名或 failover 用到（`capabilities.py:633-637`）。
- **不在 pool 的模型名一律 404**：Claude Code 只設 base URL 與 key 時，第一個請求送 `claude-opus-5-5` 就失敗。
- **DeepSeek 對每個租戶預設不可見**（`cn_origin_providers_enabled` 預設關）。

---

## 2. 擴充性：provider、agent、憑證（問題 2）

**整體評級：中等。** 15 條結論裡 13 條成立、2 條修正。

### 2.1 做得好的

- **provider 憑證是統一的**：IAM 一張 `ProviderCredential` 表，解密只在 IAM，gateway 只挑 IAM 解好的那一把。新增 provider 不用改 gateway 的憑證路徑（B-13）。
- **新增 OpenAI 相容 provider 約 10 個檔、2 個 owner**；Console 的 provider 選單由 catalog 驅動，前端、i18n、contract pin 都不用動（B-1、B-2）。樣本：DeepSeek（#4991）共 20 檔 +267／−18。
- **最危險的地雷有 gate 擋**：把新 provider 併進 `openai` 分支會把對方的 key 與 prompt 送到 api.openai.com，靜態 gate 會擋（B-5）。
- **新增入口的登記面是結構化的**：登記表一列、adapter 一個、每個 stage 必須表態，漏了 CI 會紅（B-8）。

### 2.2 不成立的

| # | 問題 | 位置 |
|---|---|---|
| B-4 | provider 名單沒有單一來源：gateway 與 IAM 至少 9 處手抄同步；`WorkerFactory` 是寫死的 if／elif；「只靠設定就能新增 provider」沒做 | `B/streaming/workers/factory.py:129-193`、`B/backend/plan.py:11` |
| B-12 | 模型能力資料散在 12 份以上名單，#2783 還開著 | `capabilities.py`、`openai_model_family.py`、`param_capabilities.py` 等 |
| B-7 | 非 OpenAI 相容的 provider 要寫一支新 worker（既有的 500～1000 行）；翻譯軸沒有 Bedrock、Gemini、Foundry 的 codec | `B/translation/codecs/` 只有兩個 |
| B-9 | **新增 agent 入口不是「加一個模組」**：中介格式 `xparse.items.v1` 只有 `/v1/responses` 在用；`/v1/messages` 入口與 chat→Responses 是另外兩套翻譯 | `G/responses_translation.py`、`G/anthropic_translation.py`（1022 行） |
| B-10 | agent 身分判斷沒有收斂：Codex 的判斷有 4 種寫法散在 3 個檔，其中一個 gate 看不到 | `B/production/session_affinity.py` 等 |
| B-6 | 零程式的通用路有坑：用 `vllm` 那一項接 xAI 這類雲端服務可以動，但邊界判定只看 provider 名稱，會被當成地端 | `G/pre_execution.py:848` |
| B-3 | 新 provider 預設拿不到檔案輸入、tool result 圖片、OpenAI tokenizer 這幾項能力，要另外加名單 | — |
| A-2 | IAM 那幾份鏡像名單的「一致性檢查」只是 IAM 自己比自己，不是跨 owner 比對 | `IAM/api/ninja_api/_helpers.py:1383-1402` |

purity gate 的「20 條例外、只減不增」是防止新增的棘輪，不是耦合總量：它看不到以模型名稱判斷、regex 比對 UA、以 provider 為 key 的查表，也不掃 `translation/`、`production/`、`streaming/`。

---

## 3. API 面擴充性（問題 3）

**結論：同步型的新面可以照既有模式加，不會靜默漏治理；需要新執行模型的面（影片、realtime、batch）不行。** 22 條結論裡 15 條成立、7 條修正。

### 3.1 確認成立的

- 六個面（chat、messages、responses、embeddings、speech、transcriptions）的 route 都真的走共用 pipeline（C-1）。
- 未登記的面、缺處置、強制 stage 被宣告不適用，都在任何 stage 執行前回 500 並寫稽核（C-2）。
- 三種終端事件只由 `G/terminal.py` 發出，先記帳再發事件（C-4）。
- 三支 gate 與 self-test 全綠（C-3）。

### 3.2 加一個面的實際成本

- **同步 unary 面**（影像生成、rerank、moderation）：登記表一列、一個 adapter（21 個必填參數加 19 格處置）、route、worker、用量 resolver、請求欄位表、conformance 表態。樣本是 M7（#5933）。
- **便宜的只有「送出前加一格」**。回應側的治理由各執行家族自己接，不在處置表內。

### 3.3 不成立的

| # | 問題 | 位置 |
|---|---|---|
| C-6 | **IAM 的模型沒有「類型」欄位**（#5948 開著）：綁上去的 TTS／STT／embedding 模型會被當成 chat 候選，音訊面也無法用 application code 定址。這是加任何非對話面的共同前置 | `IAM/db/models/provider.py` |
| C-M2 | **語音現在是寫死的**：speech 只收 `tts-1`／`tts-1-hd` 與六個 voice，只打 OpenAI 的固定網址 | `B/models/tts.py:12-15`、`B/streaming/workers/tts_worker.py:20-25` |
| C-17 | 非對話面沒有翻譯軸，provider 是寫死的小集合。「pool 混多家 provider」只在三個對話面成立 | `G/surface_adapters/transcriptions.py:81` |
| C-14 | 執行家族只有兩個，而且登記表的 `family` 欄位沒有任何程式讀它來分派。影片（建任務再輪詢）、realtime（WebSocket）、batch 各要一個新家族 | `G/surface_registry.py:31` |
| C-13 | 新增一個用量單位要動 gateway 6 處、IAM 至少 7 處、OpenAPI 與 7 份 consumer pin | `G/terminal_usage.py`、`IAM/db/models/budget_usage_ledger.py:89-110` |
| C-12 | 音訊有用量沒有價格，以金額為單位的 Budget 看不到 TTS／STT 的花費 | `IAM/authorization/usage_aggregate_fold.py:263-268` |
| C-M3 | 語音轉文字只有 `verbose_json` 才記用量；預設格式一筆都不記，也不受預算約束 | `G/usage_ledger_hook.py:197-200` |
| C-16 | route 盤點看不到 WebSocket：將來加一條 realtime route 不會被要求走 pipeline（未來風險） | `B/tests/contract/test_coordination_coverage.py:80-88` |
| C-9 | #5976（非對話面 input rail 由只記錄改成擋）不是改一個參數就能切：沒有 enforce 路徑，一關掉反而整段不檢查 | `G/dispatch_stages.py:368-369` |
| C-7 | #5948 必須排在 #5949 之前，否則綁上去的音訊模型會進 chat 的自動路由 | — |

五個「只記錄不擋」的開關都還開著，由 gate 釘住；另有第六個不在那張表裡：`/v1/responses` 的 Policy Kernel 由環境變數控制，預設 shadow。

---

## 4. audit、cost、routing、policy（問題 4）

### 4.1 記錄：做到了

- 終端事件與記帳只走 `G/terminal.py`，六個面、原生與翻譯、串流與非串流、agent mode 都經過它（D-1、D-2）。
- 記帳無條件且先於稽核；成功、失敗、incomplete、斷線、被 failover 取代的嘗試各有明確規則（D-3）。
- 翻譯路徑的用量帶 cached／cache_write（D-4）；`translation_path`、`routing_attempt`、`native_fallback_reason`、處置清單都真的寫進稽核（D-14）。
- 兩支 parity gate 全綠。它們只檢查「有沒有呼叫記帳」，看不到金額對不對（D-17）。

**但 prod 的 Console 成本畫面讀的不是這本帳**：`COST_SURFACES_FROM_IAM` 還被 rel 扣住，prod 與客戶安裝顯示的是 Audit 來源的數字；兩本帳的對帳（#5143）沒做完（D-M1）。

### 4.2 限制：都接上，多數預設不擋

| 項目 | chat／messages | responses | 非對話面 |
|---|---|---|---|
| Budget、admission | 擋（用完回 400） | 擋 | 擋 |
| Policy Kernel（資料邊界） | 擋（403） | **shadow**（#1060） | 只記錄 |
| input rail | 依政策；shadow 不擋 | 同左 | 只記錄 |
| output rail | 預設 `stream` 模式，事後觀察不擋；`buffer` 才擋 | 同左 | transcription 只記錄 |
| Tool 規則 | 請求端與回應端都接上；被 rel 扣住，prod 不生效 | 同左；namespace 成員不受名稱規則管 | 不適用 |

### 4.3 金額會錯的四項（都還在）

| # | 問題 | 方向 | 位置 |
|---|---|---|---|
| D-6 | OpenAI 的 cache-write token 在 `/v1/responses` 入口以 0 元計。只發生在價格段有 pricing JSON、卻沒有 cache_write 元件時（10-14 註：當初「只有 Anthropic 收 cache write，沒寫價格就等於不收」這個前提不成立。OpenAI 從 GPT-5.6 起收 cache write，chat 入口也有回報，但 gateway 只在 Responses 路徑讀。所以 0 元的是整段寫入的 prompt，不只是加價的部分；同一段 prompt 走 chat 會照 input 價收。#6513 已更正文件與註解，計價規則沒改，待 Peter 決定。#6451、#6471 讓這種情況看得到） | 少扣 | `B/streaming/workers/azure_responses_worker.py:854`（`_capture_usage`，讀值在 `:892`；原寫 `:801`） |
| D-7 | client 中途斷線的回合以估算值入帳，快取命中當 0，整段 prompt 全價 | 多扣 | `G/terminal_usage.py:338-374` |
| D-8 | 未定價的模型成本是 0，金額預算管不到（設計如此） | 少扣 | `IAM/authorization/usage_pricing.py:199-211` |
| D-9 | Azure 的 hosted web_search 在回應沒有 `usage.tool_usage` 時完全不入帳，Azure 也沒有價格 | 少扣 | `B/streaming/hosted_tool_usage.py:212-220` |

### 4.4 其他稽核與成本缺口

- **憑證解析的稽核事件發不出去**（D-16、B-14）：`B/production/key_resolver.py:19` 寫的是 `from bustream.audit import emit`，而套件裡同時有 `emit.py` 子模組與同名函式；子模組一被 import，這個名字就變成模組，呼叫時丟 `TypeError`，被 fail-open 吞掉。反駁的 agent 實際重現了。沒有 issue。修法本身很小，但接上後會啟動一條從沒跑過的 Audit 管線，所以要先決定幾件事（§8.2）。
- **用量帳本事前寫入失敗時回 503**，而且失敗記憶是行程層級：任何一筆寫入失敗後 10 秒內，這座 gateway 上所有租戶的請求都直接 503（D-M2；`B/production/quota_counter.py:632-709`）。這與「體驗優先」相反，要你裁定。
- 401 與 FastAPI 驗證 400 沒有稽核事件（D-15）；Claude 的 thinking token 數不進稽核，金額不受影響（D-5）（10-14 已由 #6451 處理：進 `reasoning_tokens`）。
- token 預算的事前預留不含 tools 定義（`XPARSE_BUDGET_COUNT_TOOLS` 預設關），agent 流量被系統性少預留（D-M3）。

### 4.5 routing

- 三個對話面走同一個 resolver；四種難度判定 × 四種目標都是真實作（prod 因為 Jev 被扣住，實際是 3 × 4）（E-1、E-2、E-3）。
- **已知壞掉的模型不會被自動路由排除**（E-6）：健康分數與 breaker 狀態有寫進候選資料，但 `xparse_routing` 的 resolver 與所有 picker 都沒讀，唯一讀者是 session pin 的驅逐。breaker 開了也沒有任何程式拒絕請求。（10-14 #6459 只加了計數器 `xparse_gateway_routing_breaker_open_selected_total`，仍不剔除；剔除與否待 Peter 決定，見 §8.2）
- **chat／messages 的 failover 換模型時不再問 Policy Kernel**（E-M1，這輪新發現）：kernel 內建「fallback 不得跨邊界」的規則要 `is_fallback=True` 才走，但整個 gateway 沒有任何呼叫點傳 True。on_prem 的 app 如果 pool 同時有地端與雲端模型，地端失敗後可以換到雲端而沒有任何違規紀錄。`/v1/responses` 反而有做。位置：`G/dispatch_stages_execution.py:254-264`、`G/routes/chat.py:2110-2126`。
- routing 仍在 event loop 上對整份對話做無上限掃描（E-8）；修正在分支 `claude/gifted-shamir-220761`，沒有 PR。（10-14 已由 #6459 處理：刪掉 5 個沒人讀的掃描、token 估算移出 event loop；那條分支視為被取代，見 §11.2）
- 開了 tier escalation 的 app，命中 pin 的請求仍每個都重判一次（owner 待決）。

### 4.6 一設成 enforce 就會讓真 agent 壞掉的

| # | 問題 | 位置 |
|---|---|---|
| E-12 | PII／word filter 的偵測面上限是 24 則，超過就整個請求 451，不是只掃前面。agent 跑十來個工具回合後，同一個 session 每次送出都 451 | `G/guardrail_detection.py:65-66`、`G/guardrail_input_surface.py:247-273` |
| E-M2 | 整個請求的掃描預算 30 秒；程式註解自己量到 17k 字元要 8.2 秒。agent 讀一個大檔就會超過 | `G/guardrail_input_surface.py:83-92` |
| E-M2 | 偵測到的內容落在不能改寫的位置（例如含圖片的訊息）→ 451 | 同上 `:98-103` |
| E-15 | 遮罩生效後 Claude Code 退出原生路徑，prompt cache 命中掉下來 | `G/native_messages.py:214-254` |
| E-24 | `tool_use: deny` 或舊開關 `tool_call_allowed=false`：真 agent 每個請求都 400（設計如此） | `G/tool_governance_request.py:248` |
| E-13 | content_filter 對 tool result 也有 24 的上限，但要政策另外開 `scan_tool_results` 才會觸發 | `G/classifier_handler.py:2981-2997` |

rail 的盲點：`/v1/messages` 的 PDF、provider 代跑的 web 搜尋抓回的內容（owner 已接受）；另外 `/v1/responses` 的 PII 面直接跳過 Codex 的 `custom_tool_call`（`apply_patch`、code mode 的 `exec`），而且沒有任何「沒讀到」的紀錄（E-M3；`G/guardrail_detection.py:752-786`）。

---

## 5. `/v1/responses` 以前的問題（問題 5）

### 5.1 修掉的

- **根因的前半**：POST `/v1/responses` 的所有前置步驟走共用 pipeline，結束事件與記帳走共用 terminal（F-1）。
- 草案四張缺口表裡當時未修的項目：`llm_judge_routing`、chat 面指名 Responses 模型、擋下格式讓 Codex 重試、斷線記帳、回應端 Tool 規則，都已修（F-4～F-7）。
- 第二輪 I1–I9、W1–W16 全部 merge，#5870 也已 merge（F-9）。
- 請求不再靜默丟欄位：每個欄位都有明確去向，`tool_choice`、`parallel_tool_calls`、`include` 都會轉送（F-3）。
- 重工量下降：route 從 853 行降到 558 行；重複治理的四個檔縮最多（例如 input_guard 372 → 61）（F-22）。
- 指名查的 23 張 issue：14 張已關、9 張還開。

### 5.2 沒修掉的

**結構上的另一半**（F-M2）：gate 保護的是「送出前的 stage」與「稽核事件 × 面」。回應端（輸出 rail、工具呼叫判定、參數審視）在 `G/routes/chat.py`、`G/non_streaming_handler.py`、`G/responses_stream.py` 各接一次，新功能可以只做兩個面而 CI 不紅。10-12 的 #6363（工具呼叫審視）就只接了 chat／messages，五支 gate 全綠，也沒有登記缺口。（10-14 已由 #6474 補上回應端的登記表與 `response-checks-gate`：每條回應路徑 × 每個檢查都要表態。它只管宣告與接線一致，執行期沒有改，各面仍各自執行）

還會咬到使用者的：

| # | 問題 | 位置 |
|---|---|---|
| F-12 | 沒有非串流（§1.4） | `G/responses_request_model.py:55-61` |
| F-17 | 翻譯路徑上（Codex 打 Claude／DeepSeek／vLLM）被輸出上限截斷的 function_call 仍以 `completed` 送出。chat／messages 會丟掉被截斷的那一筆（10-14 已由 #6526 部分處理：翻譯路徑上被切的呼叫**仍照送 `completed`**，但終端事件記 `tool_arguments_invalid_reason=truncated`，Claude 被切成 `"{}"` 的也記得到；原生路徑讀 `status=incomplete` 也記 truncated。chat／messages 改看 Claude worker 的「沒收完」訊號，被切成 `"{}"`、工具又沒宣告 `required` 的那一筆以前會交付，現在也不交付。翻譯路徑要不要不交付（D3-B）待 Peter 決定，見 §13） | `B/translation/stream/responses_renderer.py:331-337` |
| F-15 | 原生路徑每輪在 `response.created` 同步寫 IAM binding，不論 `store` 的值。IAM 抖動時回合失敗、Codex 重試 | `G/responses_stream.py:309`、`G/responses_pipeline.py:744-759` |
| F-M3 | 上一項的失敗還被記成「模型」的健康失敗，會拉低分數、踢掉別人的 session pin。同一段程式裡 gateway 自己的例外有排除，這個分支漏了（10-14 已由 #6447 處理：binding 寫入失敗不再記模型健康，另加 gate 要求每個失敗出口明寫健康判定） | `G/terminal.py:254-256`、`B/production/health_tracker.py:131-137` |
| F-16 | provider 自送的 `response.failed` 與被截斷的串流仍以未分類錯誤記健康 | — |
| F-18 | ADR-455 bridge 在 `response.incomplete` 時，連已經完整收到的工具呼叫也一起丟（#5668）（10-14 已由 #6460 處理：輸出上限截斷時交付已收完的呼叫；#6526 再記下被丟掉的那一筆。#5668 只用 Refs，仍開著） | `B/streaming/workers/azure_responses_worker.py:913-944` |
| F-19 | 加密 reasoning 的憑證守衛只在 failover 時生效，第一次選模型與升級時沒有（#4878）。只影響 pool 裡有多把 OpenAI／Azure 憑證的 app | `G/request_fields.py:588-623` |
| F-10 | 執行邊界預設 shadow（#1060）；沒有 semantic cache（#4247） | — |
| F-21 | Xparse 管理工具在這個面不執行：帶管理金鑰的請求直接 400（#6166） | `G/routes/responses.py:276-283` |

---

## 6. 下一階段（tool／MCP／sandbox policy）的地基

### 6.1 已經在的

- Tool 規則的請求端是單一 stage，三個入口共用同一個函式（G-1）。
- 回應端「整輪扣住」三個入口都接上（G-2）；`TOOL_CALL_DETECTED`／`TOOL_CALL_RESOLVED` 三個入口都有發出點（G-3）。
- IAM 與 gateway 之間的 Tool 規則契約有 pin 與 parity gate（G-4）。
- 在送出前加一個 stage 很便宜：最近一次（xparse_tools）是 27 檔 +965 行，每個 adapter 只多 2～5 行（C-19）。

### 6.2 開工前建議先收的 5 件

1. **把 `main` 推到 rel，用三個真 CLI 重跑一輪。** 沒部署也拿不到 Codex namespace 工具的普查資料，而 ADR-490 Q15 的補法明寫要先普查。
2. **先定「MCP policy」管哪一層，並處理名稱正規化**（G-5、G-6、G-M1）。
   - 同一個 MCP 工具：Claude Code／OpenCode 送成 `mcp__server__tool`，受名稱規則管；Codex 送成 namespace 加成員，不受管。
   - 翻譯層已經有把成員壓成 `<namespace>__<tool>` 的 `ToolNameTable`（`B/translation/tool_shapes.py:154-209`），但只有 codec 在用，治理 stage 讀的是 client 原樣。
   - June 有兩支未合併的設計 PR 與這塊重疊：#3938（PRD-317 企業 MCP 治理，定義了宣告層／供給層／動作層）與 #3978（ADR-427 草案，參數層）。#3938 裡的 PRD-316 與 `main` 上的 PRD-316 撞號。
   - code mode 的工具是在 `exec` 的 JavaScript 裡呼叫的，名稱規則日後涵蓋 namespace 成員也管不到腳本內部（G-7）。
3. **決定擴充 `tool_governance` 還是開新 policy kind**（G-11、G-12）。
   - `tool_governance/v1` 的投影是封閉 schema，gateway 讀到未知鍵就讓整個 validate 失敗。在同一個 kind 加欄位，混版或 IAM 回滾時會整條失敗。
   - 開新 kind 沒有單一登記表：以 `tool_governance` 為前例約 45～50 個觸點、三個 owner、四份 pinned 契約。
4. **sandbox policy 先定落點**（G-17）。它現在是 `SandboxProfile` 上的欄位，egress 走舊的 `runtime_egress`，不在 versioned policy 模型裡；gateway 與 sandbox 之間沒有任何連結。`SandboxProfile.allowed_tools` 只有寫入，找不到任何讀取或強制的程式。
5. **Tool 規則本身還沒通過自己的驗收**（G-14）。pre-release registry 寫明 7 天真流量影子、P4／P5／P15 probe、P14 回滾演練都沒做，到期日 2026-12-21。新 policy 是疊在它上面。

### 6.3 可以邊做邊補

- Console 的 Tool 規則「Codex 範本」已過期（G-M2）：照它擋 shell，在 Codex 現在的形狀下擋不到。檔案 `frontend/console-app-refactor/src/app/(main)/(ai-gateway)/policies/_components/policy/tool-name-templates.ts`，最後修改 10-02。
- 參數層沒有現成掛點（G-10）：Tool 規則的判定與稽核一律不含 arguments。
- 後果層（policy actions）不是「加一筆登記」就好：還要改 gateway 與 Console 的鏡像，並在 gateway 的觸發點寫程式；它本身也還被 rel 扣住（G-13）。
- `tool_use: deny` 對 hosted web 工具在 Codex 擋、在 Claude Code 看起來不擋（G-9，讀碼推論，未實跑）。
- Tool 規則的投影只對 application 層級的 key 生效；tenant／group 層級的 key 不受任何 Tool 規則管。
- ADR-490、ADR-243、ADR-232、ADR-500、ADR-503 的 Status 都還是 Proposed，SPEC-312、PRD-350 是 Draft，而程式已經在 main／rel。

---

## 7. 改善建議：工程上做得到、而且不用取捨的

### 7.0 怎麼篩的

7 個主題各提案一次（共 90 個），再各由一個專門找「隱藏取捨」的 agent 挑戰。四條都成立才算「不用取捨」：

1. 不改變你已決定、或 ADR／SPEC 寫明理由的行為。
2. 不犧牲別的性質：延遲、成本、wire 原樣、安全（fail-closed 改 fail-open 一律算取捨）、對既有 client 的相容性。
3. 是純修正或純收斂：靜默丟掉 → 送到模型；記錯 → 記對；多份手抄名單 → 單一來源加 gate；缺 gate → 補 gate；封閉清單 → 開放規則。
4. 做得到：指得出要動的檔，也能用真元件驗證。

結果：原提案標「不用取捨」的 44 個，挑戰後剩 33 個，另有 11 個被改列成「有取捨」。挑戰者另外補了 17 個（這 17 個沒有再被第二個人挑戰，標 ＊）。去掉重複後是下面 40 項。規模：**S** = 一支小 PR，沒有 migration 或 contract 變更；**M** = 2～5 支 PR 或需要改 SPEC 契約列。

提案編號（`T2-P1` 等）對應 `improvements.json`。稽核之後 `main` 多了 7 個 commit，挑戰者確認沒有動到相關的檔。

### 7.1 問題 1：三種 agent × 不同 provider

| # | 改善 | 做法與位置 | 規模 | 參考 |
|---|---|---|---|---|
| 1 | **`/v1/messages` 逐段輸出文字（第一階段）**。使用者效益最大的一項：Claude Code、OpenCode 打非 Claude 模型時，文字隨生成出現 | 由 chat core 宣告「這個回合的文字不會被改寫、也不會被整輪收回」，成立才逐段送，其餘維持現狀。條件要正面表列、預設不逐段：單模型路由、output rail 不是 buffer、沒有生效的回應端 Tool 規則、沒有 hosted web 工具、出口不是 Claude。要補一條 gate 把串流中途的拒絕點與宣告綁在一起。`G/anthropic_translation.py`、`G/routes/messages.py`（T2-P1） | M | LiteLLM、Bifrost 都逐段送 |
| 2 | **Claude「現行家族」改成版本規則**。下一個家族上市當天就能用 | 名稱解析得出版本、且版本 ≥ 5（或 opus ≥ 4.7）就是現行；解析不出來的名稱維持今天的行為。同步改 SPEC-256 的 D9k、D12a、D12d。`B/backend/param_capabilities.py:200-211`（T3-P2、T1-P8） | S | repo 內 `openai_model_family.py` 同型做法 |
| 3 | **Gemini 把圖片送到模型**（只限 base64，三個 CLI 的圖都是 base64） | user 回合逐 part 轉換，data URL 轉 `inlineData`。URL 圖片不在這項內。`B/streaming/workers/google_worker.py`（T1-P1）。**沒有 Gemini key，只能離線證明內容進了 payload** | S | LiteLLM、Bifrost、Portkey 都有做 |
| 4 | **chat→Responses bridge 帶上 `response_format`**，不再丟棄 | 用既有的轉換函式放進 `text.format`，從 `_BRIDGE_UNCARRIABLE_PARAMS` 移除。今天就能用真 OpenAI 驗。`G/worker_setup.py`、`G/cross_surface.py`（T1-M1＊） | S | — |
| 5 | DeepSeek：`developer` 改成 `system`、沒有頂層 `type` 的工具 schema 補上 | 只對 `provider == "deepseek"`，只影響 chat 入口。同步改 SPEC-256 C-256-D16h。`B/streaming/workers/factory.py`（T1-P9） | S | LiteLLM、Portkey |
| 6 | 結構化輸出被擋時回專屬的錯誤碼與訊息，不要說「模型不在這個入口」 | 狀態碼現在就是 400，只改 `error.code` 與訊息。`G/model_addressing.py::_refuse_for_a_need`（T1-P5） | S | repo 內 `document_unsupported` 的先例 |
| 7 | 未知模型名稱的 404 訊息指出該填什麼 | 訊息補上「用 application code，清單見 `GET /v1/models`」；順手拿掉已關的 #2551 與過期的說明。`G/addressing_refusals.py::refuse_unknown_model`（T2-P5） | S | — |
| 8 | `GET /v1/models` 接受 `x-api-key` | Anthropic 系的 client 才拿得到模型清單。`G/routes/models.py`（T2-P6） | S | — |
| 9 | `/v1/messages` 串流的 `output_tokens` 一律用 provider 的數 | 不再用字數除以 4。builder 要另收一個「這個請求有 cache 意圖」的旗標。`G/anthropic_translation.py:903`（T2-P9） | S | LiteLLM |
| 10 | 路由稽核記下「本面候選」把哪些模型留在池外 | 三個扁平欄位進 `decision_evidence`，路由決策不變。回答「為什麼 Codex 的自動路由沒選到 Claude」。`G/route_resolution.py`（T2-P8） | S | Bifrost |
| 11 | 三個 CLI 的接入設定文件（模型名稱填 application code） | 純文件。Console 與手冊目前是 0 筆（T2-M2＊） | S | — |
| 12 | **「不得靜默丟」的契約矩陣**：每個 provider 對每個參數與內容 part，只能是送出、留紀錄、或拒絕 | 一支參數化測試跑真的 seam → 真的 `WorkerFactory` → 真 worker 的 `_build_payload()`。先讓它對現況變紅，再逐項收。同一份矩陣也就是對外的 provider 相容性表。新的 provider 判斷要放 `param_capabilities.py`，不要加在 `worker_setup.py`（G1 會擋）（T1-P4、T1-P11） | M | LiteLLM 的「宣告支援清單」、Bifrost 的情境矩陣 |

### 7.2 問題 2：擴充性

| # | 改善 | 做法與位置 | 規模 | 參考 |
|---|---|---|---|---|
| 13 | **provider 名單的跨 owner parity gate** | 一支純 stdlib 的 gate 比對：factory 的分支、`AVAILABLE_PROVIDERS`、IAM 的 `_WORKER_BACKED_PROVIDERS`；兩邊的 Responses-only 名單；兩邊的預設 host。補上 ADR-208 INV-208-2 宣稱但實際不存在的檢查（T3-P1、T3-M1＊） | S | one-api 名單長度不符就啟動失敗 |
| 14 | Codex 身分判斷原樣搬進 `client_profiles.py`，G1 的掃描範圍補上 `production`、`registry`、`streaming`，regex 形式的比對也擋 | 零行為變更。把 4 種寫法「收成一條 regex」不在這項內（T3-P3 第 1 步、T3-M2＊） | S | LiteLLM 單一 `is_codex_user_agent` |
| 15 | provider 事實完整性測試 | 一張測試側的表，對每個 provider 寫出每個既有判斷的預期答案；新增 provider 不補一列就紅（T3-M3＊） | S | — |

### 7.3 問題 3：API 面

| # | 改善 | 做法與位置 | 規模 | 參考 |
|---|---|---|---|---|
| 16 | **價格快照不再丟掉 `mode=responses` 的模型** | Console 註冊 Codex 用的 Responses-only 模型時，能力與公開定價會自動帶出來。百分位只用 chat 列計算，才不會動到既有列。`scripts/gen_model_defaults_snapshot.py:85-86`（T4-P4） | S | LiteLLM 的 `mode` |
| 17 | **語音轉文字的預設格式也記秒數** | provider 的 `usage` 回 `{type: duration, seconds}` 時讀它。先擷取一份真的 OpenAI 回應確認。不把 token 寫進語音稽核事件（ADR-479 D3）。`G/surface_adapters/transcriptions.py:111-119`（T4-P1） | S | vLLM、Bifrost |
| 18 | 用量軸的跨 owner parity gate；booker 在 import 時對齊 | 加「張數」「影片秒數」時漏改任何一處會在 PR 上變紅（T4-P2、T4-M2＊） | S | Bifrost 兩處靜默歸零是反面教材 |
| 19 | route 盤點看得到 WebSocket；執行家族由登記表驅動檢查 | `B/tests/contract/test_coordination_coverage.py`（T4-P3） | S | LiteLLM、Portkey 的 realtime 都繞過共用路徑 |
| 20 | conformance gate 加逐面規則：宣告 RUN 的 stage，在該面至少要有一個通過的測試 | 現況已是綠的，防的是未來加面時整批標「不適用」（T4-M1＊） | S | — |
| 21 | speech 收帶日期的 `tts-1` 名稱，voice 改成依模型分開的表 | 前提：先對 OpenAI 文件核對 voice 清單。不加 `gpt-4o-mini-tts`（T4-M3＊） | S | — |
| 22 | gateway 的用量單位收成一張表 | 等加第四個單位時同批做，現在單獨做不划算（T4-P9） | M | — |

### 7.4 問題 4：audit、cost、routing、policy

| # | 改善 | 做法與位置 | 規模 | 參考 |
|---|---|---|---|---|
| 23 | Claude 的 thinking token 數進稽核 | 讀 `message_delta` 的 `output_tokens_details.thinking_tokens`。金額不變。`B/streaming/workers/anthropic_worker.py`（T5-P3） | S | LiteLLM |
| 24 | cache-write 以 0 元計的時候要看得到 | 終端事件加旗標、計數器、每個模型警告一次；IAM 的唯讀盤點指令加一格。不動計價規則。訊息不要寫成「設定錯誤」，那是合法的價格形狀（T5-P5、T5-M1＊） | S | LiteLLM 的 zero-cost 診斷 |
| 25 | 未定價的執行、帳本寫入失敗，各加一個計數器 | 地端模型未定價是既定設計，告警規則要能排除（T5-P9） | S | — |
| 26 | hosted 搜尋次數進稽核事件 | 只做「把已有的次數寫進事件」這一半（T5-P7） | S | LiteLLM |
| 27 | 刪掉一支沒有呼叫者、卻把 reasoning 加進 output 的成本函式 | `B/production/pricing.py::estimate_cost_breakdown_micro`（T5-M3＊） | S | — |
| 28 | **刪掉 routing 裡 5 個沒有讀者的全文掃描** | 分支 `claude/gifted-shamir-220761` 的前半，要在 main 上重做（分支落後 54 個 commit）。`G/routing_adapter.py:384-392`（T6-P2） | S | — |
| 29 | routing 的 token 估算離開 event loop，數字不變 | 只對 routing 那一筆文字用能等的讀者。不要在 routing 直接等整批計數，否則沒有 budget 的 app 被拒時會多等（T6-P3） | S | — |
| 30 | `/v1/responses` 裡 rail 沒讀到的 item 留紀錄；item 型別名單加 gate；「哪些 item 帶工具文字」收成一張表；圖片也記進 `unread_parts` | 只加紀錄，不改任何請求的處置。要改 SPEC-312 C-312-58 的文字（T6-P5、T6-M2＊、T6-M4＊） | S | LiteLLM 單一欄位表 |
| 31 | 記下「路由選到 breaker 開著的模型」的次數 | 只做 Prometheus 計數器。有數字才能決定要不要剔除（T6-P9） | S | — |
| 32 | chat／messages 的 failover 換到 Policy Kernel 不准的模型時先留紀錄（不擋） | 直接做 §8.1 的第 1 項就可以省略這項（T6-M1＊） | S | — |
| 33 | 三個 guardrail 451 訊息不再指名「personal data」 | 狀態碼與 error code 不動（T6-M3＊） | S | — |

### 7.5 問題 5：`/v1/responses` 與回應端

| # | 改善 | 做法與位置 | 規模 | 參考 |
|---|---|---|---|---|
| 34 | **IAM binding 寫入失敗不記成模型的健康失敗** | 一行：該分支補 `record_health=False`。不要補 `error_status_code`（SPEC-287 寫明必須是 None）。`G/responses_stream.py:1031-1066`（T7-P3、T2-P10） | S | — |
| 35 | 失敗終端的健康判定不准用預設值（AST gate） | 現有 16 個呼叫點有 4 個沒明寫。上一項與 #6362 都屬這一型（T7-M1＊） | S | — |
| 36 | bridge 在 `response.incomplete` 時交付已完整收到的工具呼叫（#5668 剩下的一半） | 只送已收完的，沒收完的不送。`B/streaming/workers/azure_responses_worker.py:913-944`（T7-P5） | S | — |
| 37 | 翻譯矩陣加「被輸出上限截斷的工具呼叫」情境 | 讓既有的 gate 逼每一格表態，缺口先以 KnownGap 進 CI（T7-M2＊） | S | — |
| 38 | 原生 `/v1/responses` 的終端事件補記工具呼叫的截斷與參數問題 | 只記錄，不動 wire（T7-M3＊） | S | — |
| 39 | **回應端的登記表、處置表與 gate（ADR-494 的另一半）** | 一份純 literal 的表列出回應路徑（chat 串流、chat 非串流、agent mode、responses 串流、unary）與每條路徑上的檢查（output rail、Tool 規則判定、參數審視、截斷），每格必須表態。三塊都不改執行期行為。建議做成模組層級的檢查。新的 tool／MCP policy 多半在回應端判定，這項做了之後漏一個面 CI 會紅（T7-P1、T4-P6） | M | 沒有參考產品做到；LiteLLM 的登記表只衡量、不強制 |
| 40 | 工具的扁平名稱進稽核 | `TOOL_CALL_DETECTED` 多帶一欄 `<namespace>__<tool>`，三家 agent 的同一個 MCP 工具用同一個鍵查得到。欄位用中性名稱（例如 `tool_flat_name`），只當彙總鍵。ADR-490 Q15 要的普查靠它才算得出來（T7-P6） | S | LiteLLM 一律看攤平後的名字 |

### 7.6 建議的順序

1. **先做一行到一支小 PR、今天就能驗的**：34、7、8、4、2、23、9。
2. **補 gate**（零行為變更）：13、14、15、18、19、20、35、37。
3. **補可見性**（只加紀錄）：10、24、25、26、30、31、32、38、40。
4. **兩個結構項**：39（回應端登記表，建議在動 tool／MCP policy 之前做）、12（不得靜默丟）。
5. **體感**：1（`/v1/messages` 逐段輸出）。
6. 其餘（3、5、6、11、16、17、21、27、28、29、33、36）隨手排。22 等加第四個用量單位時再做。

---

## 8. 有取捨、或要你決定的

### 8.1 有先例的行為變更（做得到，但會改變看得到的行為）

| 項目 | 會變什麼 | 規模 |
|---|---|---|
| **chat／messages 的 failover 候選先過 Policy Kernel**（T6-P1）。這一輪最重要的行為修正 | on_prem 的 app 綁到混合 pool 時，地端失敗不再換到雲端。這些 app 在路由選到雲端 primary 時今天就已經 403，所以是把同一條規則補到 failover | S |
| **翻譯路徑上被截斷的 function_call 不交付**（T7-P2、T2-M1）。先例是 #6363 | 被截斷的 `apply_patch` 目前把半截字串當成完整輸入交給 Codex。修了之後不會減少 Codex 的重試，只是每次重試不再帶半截呼叫 | S |
| Claude 斷線回合用 provider 的數入帳（T5-P2） | 斷線不再多扣。連帶地，`message_start` 之後才失敗的嘗試會依既有規則新增帳本列，租戶的 budget 消耗會變 | S |
| 事前寫帳失敗的記憶只對「路徑不健康」生效（T5-P4） | 改的是 10-13 才定的 SPEC-215 C-215-145。建議縮成「409 與 422 不觸發記憶，重試不動」 | S |
| `/v1/responses` 的 `stream: false` 回 JSON（T2-P3） | 沒帶 `stream` 的請求要不要也回 JSON 要你點頭：OpenAI SDK 預設就是不帶，不翻等於沒修；翻了，現在不帶 `stream` 卻照 SSE 解析的 client 會壞。另外要定非串流的總時限 | M |
| `/v1/responses` 的 `json_schema` 送到 Claude（T1-P6） | 400 變 200；舊 Claude 家族會是「沒被強制的 200」。要改 SPEC-312 的契約列與兩支 gate | S |
| Gemini 補 `response_format`、具名 `tool_choice`、`developer`、`seed`（T1-P2） | 部分請求從靜默丟掉的 200 變成 provider 的 400 | M |
| Gemini 3 以上多輪工具填佔位簽章（T1-P3） | 明確的 400 換成品質可能下降的 200。沒有 Gemini key 前不該動工 | S |
| `max_tokens` 超過上限時照 provider 回的上限重送一次（T1-P7） | 失敗路徑多一次呼叫；重送時 client 的值被改小 | M |
| guardrail 偵測面上限改數「還沒快取的條目」（T6-P4） | 要改 9-13 定的 D12。只在 session 不中斷 15 分鐘、gateway 不重啟時有效 | M |
| sidecar 不再把平台自己的遮罩 token 當成個資再遮一次（T6-P8）；做完才能做「遮罩後留在原生 body」（T6-P7） | 前者有少量漏判代價；後者要解除 SPEC-312 寫下的範圍，效益未實測 | S、M |
| provider 自送的 `response.failed` 分類後再記健康（T7-P4、T7-P13） | 要同時改 SPEC-287 與 SPEC-290，否則 chat 與 responses 的健康規則會分家 | S |

### 8.2 要你決定的

- **憑證解析的稽核事件接回去**（T5-P1）。成因與修法都對，但接上後會啟動一條從沒跑過的 Audit 管線：prod 成本畫面的 rollup 會對這類事件做全歷史掃描（上限 100 萬，超過就停更），同一個 trace 的 judge／classifier 會讓「依憑證」的歸屬記錯，evidence 量約加倍。要先決定事件帶不帶 `model_uuid` 與用途、Audit 端先改 join 還是先調上限。它仍是最該做的一件，規模 M。
- **`/v1/messages` 逐段輸出的第二階段**（Claude 出口，含 thinking 簽章與 hosted block）：要放寬 SPEC-312 C-312-27 的「簽章全給或全不給」。Claude Code 打 Claude 開 thinking 的主場景要等這個。
- **cache-write 缺價時改退 input 價**：LiteLLM 與 Bifrost 都這樣做；Xparse 現在的 0 是刻意的價格形狀。（10-14 註：「刻意」的理由是只有 Anthropic 收 cache write，這個前提已由 #6513 更正；選項 a／b／c 見 §13 與 #6513 的 Future work）
- **自動路由剔除 breaker 開著的模型**：全部都開的時候要放行（Portkey 的做法）還是拒絕（LiteLLM 的做法）。
- **模型類型欄位**（#5948）、**能力資料改由 catalog 提供**（#2783）、**只靠設定新增 OpenAI 相容 provider**：各需要 PRD／ADR。
- **Azure 的 tools × reasoning**：不是取捨，是缺真元件。要一個 gpt-5.5+ 的 Azure 部署才能驗。
- **Gemini 的 thinking 簽章真正往返**：Phase 4c，與 ADR-503「不透明狀態只走信封」要先對齊。
- 其餘：串流在第一個位元組前失敗時回真正的 HTTP 狀態；operator 可設的模型別名；輔助請求跟著 session 的模型（提案的辨識規則會推翻 SPEC-290 C-290-30）；tier escalation 的重判；`/v1/responses` 的周邊端點；`custom_tool_call` 進偵測面；加密 reasoning 的憑證守衛；binding 同步寫入要不要改；`tool_search_call` 要不要記事件；namespace 成員納入名稱規則；401 寫稽核；預算預留含 tools；`/v1/responses` 邊界切 enforce（#1060）。

### 8.3 不建議做

- gateway 代抓圖片 URL（違反 ADR-035，多出 SSRF 面）。
- 工具呼叫參數逐段送給 client（與 SPEC-304 C-304-143b 的截斷規則互斥）。
- 把三套翻譯收成單一中介格式（沒有一家參考產品這樣做）。
- 每次 failover 重跑整條治理（rail 判的是請求內容，換模型答案不變）。
- 以 client 自報的 session id 記「已掃過的片段」（LiteLLM 這個機制在遮罩開著時自己就停用）。
- 把憑證寫進 `encrypted_content`（要改寫 provider 的事件，違反 ADR-339）。

---

## 9. 參考產品怎麼做

版本：LiteLLM `39d14bd`（2026-09-28）、Bifrost `ed9869f73`（2026-10-05）、Portkey gateway `669825cb`（2026-05-25）、one-api `8df4a26`（2025-02-21，較舊）、vLLM `92044241a0`（2026-10-04，推論伺服器）。每條的 file:line 在 `improvements.json`，挑戰者逐條打開核對過。

| 主題 | 別人怎麼做 | 對 Xparse 的意義 |
|---|---|---|
| Gemini 的圖片、結構化輸出 | LiteLLM、Bifrost、Portkey 都有做，連 one-api 都有圖片 | Xparse 的 Gemini worker 還停在「文字加工具」。可以搬 |
| Gemini 的 thinking 簽章 | LiteLLM 與 Bifrost 都把簽章接在 tool call id 後面，沒有簽章時填 Google 文件化的佔位值 | 佔位值可以搬；接在 id 後面與 ADR-503 的信封規則衝突 |
| 參數不靜默消失 | LiteLLM 每個 provider 宣告支援清單，不在清單就拒絕或明示丟棄 | 紀律可以搬成一支契約測試（§7 第 12 項）；預設 400 不能照抄 |
| `/v1/messages` 逐段輸出 | LiteLLM 逐 chunk 轉；Bifrost 對 Claude 原樣逐 frame 轉出 | 可以搬（§7 第 1 項） |
| `/v1/responses` 非串流 | LiteLLM 有收集器；vLLM 分成兩個 generator | 可以搬，但預設值要你決定 |
| 串流前的錯誤狀態 | LiteLLM 先取第一個 chunk 再決定 HTTP 狀態；Portkey 看上游狀態 | Xparse 有 retry／failover，等待時間不固定，屬取捨 |
| 新增 OpenAI 相容 provider | LiteLLM 一份隨程式出貨的 JSON；Bifrost 純設定；Portkey 每家兩個小檔 | LiteLLM 那份是 preset 表，不是 operator 執行期設定 |
| 新增非相容 provider | 四家都是實作一個介面 | 沒有比寫一支 worker 更省的結構 |
| 入口協定 | LiteLLM 是三份獨立的轉接；Bifrost 兩種中介型別並存 | 沒有一家用單一中介格式，不值得為此重寫 |
| 模型類型 | LiteLLM 每個模型一個 `mode`（17 種值）；vLLM 用 `supported_tasks` 決定掛哪些路由 | #5948 可以參考這個形狀 |
| 用量單位與計價 | LiteLLM 一張表，費率欄位名帶單位；Bifrost 寬表加 switch，漏項會靜默歸零 | Bifrost 是反面教材；Xparse 要的是 parity gate |
| cache-write 缺價 | LiteLLM 與 Bifrost 都退回 input 價 | Xparse 的 0 是刻意的，改屬決策 |
| 斷線的部分計費 | 兩家都用 `message_start` 已到手的用量 | 可以搬（§8.1） |
| 算不出成本 | LiteLLM 有分原因的診斷與計數器；Bifrost 只打 debug log、成本為 0 | 可見性可以搬（§7 第 24、25 項） |
| 健康進選路 | LiteLLM 選路前先濾掉 cooldown 中的；Portkey 濾掉 breaker 開著的；Bifrost 開源版沒有 | Xparse 有訊號但沒有讀者，剔除屬決策 |
| failover 時重跑檢查 | LiteLLM 對每個目標重跑權限與預算；Bifrost 重跑整條 pre hook | Xparse 只需要補 Policy Kernel 那一項 |
| guardrail 對長對話 | LiteLLM 沒有條數上限，用三個旗標調範圍 | Xparse 的 24 則硬上限是自己的設計 |
| 遮罩後保留原生直送 | Bifrost 由入口把文字替換同步寫回原生 JSON | 可以搬，但要先解決遮罩不穩定 |
| 被截斷的工具呼叫 | Bifrost、vLLM 標成 incomplete；LiteLLM 沒處理，一律 completed | Xparse 的 ADR-437:386 把「標 incomplete」說成 LiteLLM 的做法，與這個版本不符 |
| 加密 reasoning 的憑證 | LiteLLM 第一次選模型就守，把來源寫進 item id | Xparse 只在 failover 守（#4878） |
| 工具名稱 | LiteLLM 把 namespace 成員一律攤平成 `<namespace>__<tool>`，guardrail 看攤平後的名字 | 可以搬成稽核欄位（§7 第 40 項） |
| **回應端一致性** | **沒有一家做到「登記表加會紅的 gate」**。LiteLLM 的覆蓋率登記表只衡量、不強制；Bifrost 的 hook 回錯誤也不擋請求；Portkey 的 hook 直接跳過 Responses | 只能學形狀，預設值要反過來（§7 第 39 項） |

---

## 10. 部署現實

| 環境 | 有什麼 |
|---|---|
| `main`（`0925e5a13`） | 全部 |
| `origin/rel`（`469e46b6d`，v1.77.0.11） | 共用 pipeline、面登記表、單一 terminal、`/v1/responses` 兩輪修補、翻譯軸 P1–P8。**沒有** P9（Claude Code 原生直送）、#6338、#6360、#6362、#6363 與 10-12～13 的其他修正（10-14 註：rel 已到 `2534867ad`／v1.77.0.16，多了 IAM／Fleet 權限、console 與 CVE 修正和一支 gateway 的 #6345，結論不變；§11、§13 的 30 支也都只在 `main`） |
| `origin/prod`（`ed62d8223`，v1.76.4） | 都沒有。連 `translation/capabilities.py`、`surface_registry.py`、`dispatch_pipeline.py`、`terminal.py` 都不存在 |

- prod 上 Codex 打 Claude 不通；Codex 的用量也不扣 Budget（#5257、#5681 不在 prod）。
- rel 不適合拿來判斷「Codex 能不能用」：有翻譯、沒有 #6360，Codex 0.154 預設 catalog 打 gpt-5.6 會拿到 0 個工具卻回 200。
- 部署順序與 migration 的細節見 `docs/llm_proxy_agent.md` §3.1。

---

## 11. 修正 PR（2026-10-13 開出；#6447 於 10-13 20:07 先合，其餘 18 支 2026-10-14 凌晨 merge 進 `main`）

§7 的 40 項做了 38 項，分成 19 支 PR。每支都是自己的 worktree（`/Users/peter/Desktop/X-parse/pr-worktrees/rdy-<名稱>`）、base `main`、ready。流程是實作 → 另一個 agent 獨立審查 → 修審查意見、跑整套 gateway 測試與相關 gate → push 一次。每支 PR 的完整回報（測了什麼、審查意見、沒採納的理由）在 `llm_readiness_audit-evidence/fixes.json`。

**都沒有 live 驗證**：沒有對任何 gateway 或 provider 發請求。

**合併結果（2026-10-14 04:20 前後完成）**：19 支全部 squash-merge 進 `main`，最後一個 commit 是 `e2923aeef`（#6471）。

- **做法**：#6447 先合；其餘 18 支排成一條鏈（節點 K 包含節點 1..K-1），衝突只解一次。鏈上每個節點的 CI 在合併前都是綠的，而且合併當下 `main` 的 tree 逐支核對過等於前一個節點。
- **合併順序**：#6447 → #6446 → #6457 → #6452 → #6453 → #6460 → #6467 → #6459 → #6451 → #6465 → #6463 → #6461 → #6468 → #6475 → #6474 → #6476 → #6448 → #6469 → #6471。
- **途中併入的別人的 commit**：`main` 在過程中前進了兩次（共 13 個 commit，到 `1509b814c`），都真的 merge 進整條鏈並重跑測試。
- **一個超出原範圍的修正**：#6479 把 gateway 測試改成平行執行後，`main` 既有的幾個測試會因為兩個行程層級的 guardrail memo 而互相干擾。修正是 `apps/gateway/bustream/tests/conftest.py` 的一個 autouse fixture，隨 #6446 進 `main`。
- **CI 紅燈**：全部是 runner 負載（18 支同時觸發時 Gateway CI 撞 20 分鐘逾時、IAM 連不上本機 Postgres、light lane 的 job 被取消），重跑後通過；沒有一個是程式造成的。
- **沒有 live 驗證**：沒有對任何 gateway 或 provider 發請求。

### 11.1 PR 清單

| PR | 內容 | §7 項 | 要注意的 |
|---|---|---|---|
| #6475 | **`/v1/messages` 逐段輸出文字**；串流的 `output_tokens` 用 provider 的數 | 1、9 | 六個條件都成立才逐段，預設整回合送出。Claude（Anthropic wire）不在內 |
| #6474 | **回應端的登記表、處置表與 gate**（ADR-494 Amendment B） | 39 | 執行期一行不動。表裡預列了 #6461 與 #6475 新增的模組 |
| #6476 | **「不得靜默丟」契約矩陣**；現況 23 筆缺口放在只減不增的 baseline | 12 | 只登記、不修。要排在 #6467、#6452 之後 merge |
| #6452 | Claude 家族改版本規則；bridge 帶 `response_format`；DeepSeek 收 `developer` 與無型別 schema | 2、4、5 | — |
| #6453 | 未知模型的訊息指路；`/v1/responses` 三種需求的專屬拒絕碼；`GET /v1/models` 收 `x-api-key`；CLI 接入 runbook | 6、7、8、11 | 依 `error.code` 判斷的 client 會看到新的代碼（狀態碼不變） |
| #6467 | Gemini 把 base64 圖片送到模型 | 3 | 沒有 Gemini key，只證明內容進了 payload |
| #6459 | routing：刪 5 個沒人讀的掃描；token 估算離開 event loop；記下本面候選；breaker 計數器 | 10、28、29、31 | — |
| #6451 | Claude thinking token、cache-write 以 0 計、未定價、帳本寫入失敗、hosted 搜尋次數進稽核與計數器；刪死碼 | 23–27 | — |
| #6469 | 用量軸的跨 owner gate；用量單位沒有 booker 時 import 就失敗 | 18 | — |
| #6471 | 價格快照保留 Responses-only 模型（新增 47 筆）；IAM 盤點指令多一格 | 16、24 | 動到 IAM，CI 跑得久 |
| #6447 | binding 寫入失敗不記模型健康；失敗出口必須明寫健康判定的 gate | 34、35 | — |
| #6460 | bridge 在輸出上限截斷時交付已完整收到的工具呼叫 | 36 | #5668 用 Refs，沒有關 |
| #6465 | 工具的扁平名稱進稽核；原生 `/v1/responses` 記下不能用與被截斷的工具呼叫 | 38、40 | — |
| #6463 | rail 沒讀到的 item 與圖片留紀錄；item 文字表收成一張；451 訊息不指名個資 | 30、33 | — |
| #6461 | chat／messages 的 failover 換到 Policy Kernel 不准的模型時留紀錄並計數（不擋） | 32 | 稽核確認：同一顆雲端模型，路由選到是 403，failover 換到是 200 |
| #6448 | provider 名單、Responses-only 名單、預設 host 的跨 owner gate；provider 事實完整性測試 | 13、15 | — |
| #6446 | Codex／Claude Code 身分判斷收進 `client_profiles.py`；G1 掃描範圍擴大 | 14 | — |
| #6457 | route 盤點看得到 WebSocket 與 mount；conformance gate 的逐面規則 | 19、20 | — |
| #6468 | 語音轉文字的 json 格式記秒數；speech 收帶日期的 `tts-1` 名稱 | 17、21 | voice 的依模型分表沒做 |

沒做的兩項：第 22 項（用量單位收成一張表，等加第四個單位時同批做）、第 37 項（翻譯矩陣加截斷情境，已知缺口必須掛 issue 編號）。

部分完成的：

- 第 25 項：兩個計數器都有；「每個模型警告一次」與告警規則沒做。
- 第 26 項：只做「次數進事件」；Azure 未計量的標記沒做（缺真元件證據）。
- 第 21 項：只加模型名；voice 分表沒做（要讀的 OpenAI 頁面不在這次允許的範圍內）。
- 第 12 項：只做離線矩陣；錄製回放與 live smoke 沒做（需要 key）。

### 11.2 已代為決定的事（Peter 2026-10-13 晚：「要我決定的事都交給你決定」）

| PR | 問題 | 決定 | 理由 |
|---|---|---|---|
| #6474 | ADR-494 Amendment B 標 Accepted 還是 Proposed | **維持 Accepted** | 執行期一行不動，只是登記表與 gate；隨 PR 一起進 main，文件狀態與程式一致 |
| #6475 | Bedrock／Vertex 上的 Claude 要不要逐段輸出 | **不逐段**，與直連 Claude 一樣維持整回合 | 這一階段的原始條件就是「Claude 出口排除」；這兩條 wire 沒有任何真元件證據；預設 hold |
| #6465 | 沒有真 provider 佐證的「被截斷的工具呼叫」計數 | **拿掉**，只留已驗證的「參數不是 JSON 物件」計數 | §8.1：沒有證據證明會觸發的路徑不算完成，留著是 inert 欄位 |
| #6468 | `tts-1-1106`、`tts-1-hd-1106` | **OpenAI 官方文件查得到才留，否則拿掉** | 沒有一手來源就不放進封閉名單 |
| #6452 | Claude 版本規則的 major 限一位數 | **維持** | 避免把 `claude-sonnet-45` 這類拼法讀成版本；有測試鎖住 |
| #6467 | Gemini 不讀的圖片格式從 200 變成 provider 的 4xx；URL 圖片 | **接受** 4xx；URL 圖片這支不處理 | 明確的錯誤好過模型沒看到圖卻回 200（#6359 的先例）；URL 那一半要有 Gemini key 才能驗 |
| #6459 | breaker 計數器的 label；`claude/gifted-shamir-220761` 的草稿 | label **維持 endpoint**；那條分支視為被 #6459 取代，不刪 | 值域有界；刪遠端分支不在這次範圍 |
| #6463 | `additional_tools` 算不算「沒讀到」 | **改列 opaque，不計入** | 它是工具宣告，頂層 `tools` 本來就不計；每個 Codex 請求多一筆只會稀釋訊號 |
| #6471 | 盤點要不要列「明寫 0 元」的價格段 | **不列** | 明寫 0 是 operator 的刻意設定；這一格要抓的是「沒寫」 |

### 11.3 merge 之後要做的

1. **rel 與 dev 的實機驗證**：這 19 支都沒有對真的 provider 跑過。優先用三個真 CLI 驗 #6475（Claude Code、OpenCode 打非 Claude 模型時文字是否逐段出現）與 #6452（bridge 的 `response_format`、DeepSeek 的 `developer`）。
2. **#6476 的 baseline 還有 19 筆已知的靜默丟**（Foundry 6、google 與 vertex_ai 各 6、bedrock 1），都是 §8 需要 Gemini key 或你決定的項目。
3. **沒做的兩項**（第 22、37 項）與部分完成的四項，見 §11.1 下方。
4. **§8 的行為變更與待決事項都沒有動**，其中「failover 候選先過 Policy Kernel」現在已有紀錄可看（#6461 的計數器與稽核旗標）。

## 12. 本機實測（2026-10-14，`main` `bff643332`）

完整報告：`/Users/peter/Desktop/testing/results/rdy_20261014/REPORT.md`。用 application `gpt_4o_816e` 的 key 跑真的 Claude Code、Codex、OpenCode，另以 HTTP 與 SDK 逐支驗 PR，再對帳、獨立重現。

- **19 支 PR 沒有造成回歸。** 有執行期行為的 12 支全部成立；7 支是 gate、測試或這個環境測不到（#6467 的 Gemini、#6447 的 IAM 故障路徑）。
- **三個 agent 都能用**：共 779 個請求，0 個 5xx。10-12 當時壞的項目在三個 CLI 上都已不再出現。
- **#6475 的實際效果**：指名 gpt-5.6-luna 時第一個字 3.4 秒到、18.4 秒結束，中間 1,407 個 delta；Claude 仍是 21 秒整回合一次到。
- **帳對得起來**：1,014 個請求沒有任何一個有兩個終端事件；997 個完成的請求用量與稽核逐筆相同。

新找到的問題（都不是這 19 支造成的）：

| 問題 | 嚴重度 | 修法需不需要取捨 |
|---|---|---|
| 沒有綁憑證的 vLLM 模型在 `/v1/responses` 直接 500（chat／messages 正常）。`G/routes/responses.py:196-226` 的憑證解析沒有問「免憑證」的判斷 | P1 | 不需要。修正：#6489 |
| Claude 經 `/v1/responses` 被截斷的工具呼叫以 `"{}"`、`completed` 交付，稽核沒有紀錄；#6465 的 SPEC 有一句與此不符 | P2 | 補紀錄不需要。修正：#6526（交付與否待定）（10-14 已由 #6526 處理紀錄：記 `tool_arguments_invalid_reason=truncated`，SPEC 那句已更正；這個出口仍照送，D3-B 待定） |
| Codex 打 Claude 的輸出撞到 gateway 補的 16000 上限後整輪失敗（重送的歷史以 assistant 結尾，Anthropic 回 400） | P2 | 需要。2026-10-14 處置中（未合併）：上限改由 provider 決定（#6514），被拒時補 user 接續回合重送一次（SPEC-312 C-312-67，分支 `fix/live-claude-continuation-after-prefill-refusal`）；以空白結尾的半截文字仍失敗（10-14 已由 #6514、#6516 合併處理；以空白結尾的那種 400 仍救不到，見 §13） |
| DeepSeek 的結構化輸出與強制 `tool_choice` 是 provider 的 400，自動路由下時好時壞 | P2（已記載） | 需要。修正：#6503、#6512（10-14 已合併：強制 `tool_choice` 打標了 `supports_reasoning` 的 DeepSeek 列時，那一回合送 `reasoning_effort: "none"` 關 thinking，400 → 200；帶 `json_schema` 的請求不路由到 DeepSeek，指名時送出前回 400 `structured_output_unsupported`） |
| OpenAI 的 cache-write 以 0 元計：這次時間窗約佔該模型應收的 43%；chat 入口其實也有回報，是 gateway 沒讀 | P2（已記載） | 補價不需要；改規則需要。只修文件：#6513，規則待 Peter（10-14 #6513 已合併，計價沒變） |

測試方法的一個限制：我開的轉發器不會把 client 斷線傳到上游，所以這一輪「中斷」相關的觀察不算數；直連 ingress 重測時 gateway 約 1 秒內就發現斷線。

---

## 13. 實測後的修正 PR（2026-10-14 開出，同日全部 merge 進 `main`，最後一支 `ee1a40564`）

Peter 10-14 的指示：「fix them；取捨太多的保留原樣」，以及「gateway 不 default 幫模型設上限，把選擇權交給用戶」。每支都是 ready、base `main`、各有獨立審查；gateway 整套測試在各自 head 上全綠（約 15,700 passed）。研究與挑戰者裁定：`/Users/peter/Desktop/testing/results/rdy_20261014/show_design.py`；實機證據：同目錄 `fixes/`。

| PR | 內容 | 看得到的行為變更 | 實機驗證 |
|---|---|---|---|
| #6489 | `/v1/responses` 上沒綁憑證的地端模型不再 500 | 原本 500 → 200 | 修前 500、修後 200，上游沒收到任何憑證 header |
| #6514 | gateway 不再補輸出上限（拿掉 16000／4096 與兩個環境變數）；Claude 必填，改用 Anthropic Models API 公布的上限；稽核記實際送出的值與來源 | 沒送上限時由 provider 決定；Claude 從 16000 變成模型上限（haiku-5-5 為 128000） | Responses→Claude 長輸出原本在 16000 截斷，修後完成（26,402 tokens） |
| #6516（含 #6514） | Claude 拒絕「以 assistant 結尾」時補一則 user 接續訊息重送一次 | chat 面故意送 prefill 的請求 400 → 200 | 真 Anthropic：修前 failed、修後 completed |
| #6526（含 #6514、#6516） | 被截斷的工具呼叫由 worker 明確標記；`/v1/responses` 記紀錄；chat／messages 不交付被切成 `"{}"` 的最後一筆 | chat／messages 少交付一筆壞掉的呼叫 | 用 10-14 的真 provider 錄製檔測 |
| #6503 | DeepSeek 收到強制 `tool_choice` 時，該回合關 thinking 並留紀錄；OpenAIWorker 的錯誤字樣改用實際 provider | 原本 400 → 200 | 依 10-14 的真 DeepSeek 證據 |
| #6512（含 #6503） | 帶 `json_schema` 的請求不路由到 DeepSeek；指名時回 400 `structured_output_unsupported` | 自動路由改由其他模型回 | 依 10-14 證據 |
| #6498 | 原生 Claude 的 `X-Xparse-Dropped` 不再誤列；401 訊息同時提兩種 header；runbook 更正 | 只有 header 與訊息文字 | — |
| #6509 | 稽核歸屬：STARTED 帶 model_uuid、估算原因 `client_closed`、Responses 的 reasoning token 計數、classifier degraded 帶 token | 只有稽核與 metrics | — |
| #6511 | 圖片／檔案 part 的 `unread_parts` 在三個入口一致 | 只有稽核 | — |
| #6513 | cache-write 的事實與過時註解（不改計價） | 無 | — |
| #6515 | IAM：proxy 的 active consumer 排除已終止的 application | 已終止 app 的歷史從 proxy 面板消失 | — |

**merge 方式**：Peter 說「auto fix and merge them」之後，用 merge train 依序合併：#6489 → #6498 → #6509 → #6511 → #6513 → #6503 → #6512 → #6514 → #6516 → #6526 → #6515。衝突在本機一次解完，順便把 main 新進的 commit 合進來。期間 main 新的推理等級收斂（#6534 的 D9m）會把 DeepSeek 的 `none` 改成 `low`，打壞 #6503，已在 train 裡修正（SPEC-256 C-256-D18d）。
- **合起來的版本**：本機 gateway 整套測試 16,142 passed；#6515 那一節包含全部 11 支，它的 CI（gateway、IAM sqlite／postgres、static gates）全綠。
- **CI 沒有各自跑完的節點**：#6513～#6526 沒等各自的 CI，靠上面那次涵蓋全部的 CI 把關。

**主 session 代為接受的範圍收窄**（#6509）：D6-J 不套用到非串流 JSON 路徑；`TOOL_CALL_DETECTED` 先不帶 model_uuid（串流那條要改 manager）。

**仍要 Peter 決定**：
- 計價規則 ②（沒有 cache-write 價時退 input 價）與補價的部署順序：#6513 的 Future work。
- Anthropic 對「半截輸出以空白結尾」回另一種 400，#6516 救不到：要不要剪掉尾端空白再送（會改送出的文字）。
- `/v1/responses` 翻譯出口要不要不交付被截斷的工具呼叫（D3-B），要等真 Codex 的前後對照。
- chat 的音訊 part 要不要進 `unread_parts`。

**沒驗到**：Bedrock（沒有憑證）、第三方 Anthropic 相容端點的 Models API、真 Codex 端到端（用重放代替）。

**實測順帶看到、與這批無關**：gateway 打 vLLM 上游時沒帶 `X-Request-Id`（ADR-499 說預設應帶）；tenant 的 shadow content_filter 判官設成 auto 時，指名模型的請求會讓判官打到執行模型本身。

---

## 附錄 A：還開著的相關 issue（2026-10-13 查）

| 類別 | issue |
|---|---|
| 模型身分與能力 | #2783、#5528、#5525、#3677、#4405、#5948、#6068、#5955 |
| `/v1/responses` | #1060、#4247、#5668、#4878、#6166 |
| 只記錄 → 執行的切換 | #5941、#5949、#5965、#5976 |
| 順序與浪費 | #5222、#5458 |
| 工具與 policy | #2634、#6228；PR #3938、#3978（June，未合併） |
| 成本 | #5143、#5616、#6199 |

**還沒有 issue 的**：憑證解析稽核事件發不出去；failover 不過 Policy Kernel；四項金額問題；翻譯路徑被截斷的 function_call；IAM binding 失敗記成模型健康失敗；namespace 成員的名稱規則；Console 的 Codex 範本過期；guardrail 偵測面上限。

## 附錄 B：這次沒驗到的

- 任何執行期行為。全部結論來自讀碼、靜態 gate、git、gh。
- 真 Azure 對 gpt-5.5+ tools × reasoning 的回應；Bedrock、Vertex、vLLM、Foundry 的實際 wire。
- 「guardrail 設 enforce 後 agent 會壞」的現象本身（只確認上限常數與路徑還在，現象出自 10-12 的實測報告）。
- 「Codex 會照樣執行被截斷的 function_call」（出自 10-12 報告，repo 內沒有可核對的證據）。
- IAM 寫入邊界是否禁止 on_prem 的 app 綁雲端模型（沒找到這種檢查）。
