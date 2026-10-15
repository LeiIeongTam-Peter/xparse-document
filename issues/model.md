# 一個 model 只能服務一個入口面：問題、證據與修法

> 一句話總結：一筆 model 在建立當下就被綁死在單一 API 入口。**這件事本身是客戶知情選擇的結果，不是 bug**（§5.4）—— 讓兩個入口共用一筆 model 是 feature（#2551），不是修復。真正該修的是三個**靜默行為**：pin 被無聲換成別顆模型、Console 顯示的難度分級與實際執行不符、混面 pool 配 smart routing 被靜默降級卻無任何提示。

文件對象：不需要懂 routing 實作細節的人也能看懂；每個結論都附實測或 code 位置。
日期：2026-09-10（rel = `98227f91f`，2026-09-09；local dev stack 同日）
相關 ADR：**319**（surface 是內部能力，不是客戶選項）、**323**（surface 權威屬性 + cross-surface 決定性，D1–D4）、**260 D9**（cross-surface 翻譯）、**406 / SPEC-264**（complexity routing）、**430 / SPEC-276**（routing objective + responses 面路由）、**437**（responses 治理對稱）、**339**（responses wire fidelity / passthrough）、**138 Rev.3/Rev.5**（addressing / pin）
相關 PRD：**157 §3.7**（responses 面）、**190 / ADR-239**（`/v1/messages` ingress）、**251**（Azure surface collapse）
相關 issue：**#4558**（本文 P1，已開）、**#712**（chat 面剔除 responses 模型的起因）、**#2551**（translate 半，未做）、**#2566**（reject 半，已上線）、**#2571**（addressing 撞名，prod 事故）、**#3821**（responses 面過去不跑 resolver）

---

## 1. 名詞（先講清楚四個）

- **入口面（surface）**：客戶用哪個 URL＋哪種請求格式打我們。目前推論面有 `/v1/chat/completions`（OpenAI chat）、`/v1/responses`（OpenAI Responses）、`/v1/messages`（Anthropic，flag 預設 OFF）。
- **`provider_code`**：model row 上的一個字串（`openai` / `azure_openai` / `azure_openai_responses` / `azure_ai_inference` / `bedrock` / `vllm`…）。**它同時決定兩件事** —— 我們用什麼協定打上游、以及客戶能從哪個入口打它。這個雙重職責就是本文的根因。
- **routing 候選集**：strategy 能挑的模型清單，順序＝operator 的強弱排序（`sort_order` 遞增，第一個最強）。
- **complexity routing 的映射**（SPEC-264 §2.1）：`anchor = round(t × (N-1) / 3)`，`t` 是難度序位（REASONING=0、COMPLEX=1、MEDIUM=2、SIMPLE=3），`N` 是**候選集大小**。所以 **N 一變，四級的落點整組重算**。

---

## 2. 問題怎麼被發現的

症狀：同一句英文題（「Refactor the typescript api endpoint…」），在 local 會打到標記為 COMPLEX 的那顆模型，在 rel **永遠打不到**。

兩邊的池（都是 4 顆，Console 顯示的 `complexity_tiers` 標籤也都齊全）：

| | sort_order 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| **rel**（proxy `aif`） | claude-sonnet-5<br>`bedrock` | gpt-5.6-luna<br>**`azure_openai_responses`** | gpt-5.5<br>`azure_ai_inference` | gpt-5.6-sol<br>**`azure_openai_responses`** |
| **local**（proxy `gpt-4o`） | gpt-5.5<br>`openai` | gpt-5.4<br>`openai` | gpt-5.6-luna<br>`openai` | gpt-4o<br>`openai` |

差別只有一個：**rel 有兩顆是 Responses-surface 的 provider**。

---

## 3. 實測證據

### 3.1 四級落點對照（rel 4/4 吻合 N=2）

題目取自 smart routing 測試問題集 §4（分數是 repo 內真計分器算出來的）：

| 難度題 | 分數 | rel 實測 | N=2 預測 | N=4 預測（若沒被過濾） |
|---|---|---|---|---|
| SIMPLE `hi` | −0.15 | gpt-5.5 | gpt-5.5 ✅ | gpt-5.6-sol ❌ |
| MEDIUM（M2 python json function） | 0.30 | gpt-5.5 | gpt-5.5 ✅ | gpt-5.5 ✅ |
| **COMPLEX（C2 refactor typescript）** | 0.425 | **claude-sonnet-5** | **claude-sonnet-5 ✅** | gpt-5.6-luna ❌ |
| REASONING（R3 analyze distributed） | 0.725 | claude-sonnet-5 | claude-sonnet-5 ✅ | claude-sonnet-5 ✅ |

**N=2 命中 4/4，N=4 只命中 2/4。** local 同四題各中一級（gpt-4o / luna / gpt-5.4 / gpt-5.5），完全 1:1。

結論：**rel 的 chat 面候選集只有 2 顆**，luna 與 sol 從不進候選 —— 不是「選不到」，是「不在名單裡」。

### 3.2 真元件 probe（不是推論）

```bash
cd ~/Desktop/X-parse/xparse && python3 - <<'PY'
import sys; sys.path.insert(0,'apps/gateway')
from xparse_routing.application.strategies.complexity_routing import tier_band, TIER_STRENGTH_ORDER
chat=['claude-sonnet-5','gpt-5.5']            # bedrock + azure_ai_inference
resp=['gpt-5.6-luna','gpt-5.6-sol']           # azure_openai_responses
for t,name in enumerate(TIER_STRENGTH_ORDER):
    a,_=tier_band(t,2); print(f'{name:<10}{chat[a]:<20}{resp[a]}')
PY
```

### 3.3 雙向排他（chat 模型也進不了 responses 面）

```
POST /v1/responses  model=gpt-5.5         → 422 "bound to provider 'azure_ai_inference',
                                                 which routes via /v1/chat/completions"
POST /v1/responses  model=claude-sonnet-5 → 422 同上（provider 'bedrock'）
POST /v1/responses  model=gpt-5.6-luna    → 200 SSE 正常
POST /v1/responses  model=gpt-4o (local, 真 OpenAI key) → 422 model_not_on_responses_surface
```

最後一行很重要：**OpenAI 官方兩個面都支援 gpt-4o，我們照樣拒** —— 因為那筆 row 的 provider 是 `openai`。**面綁在 model row 上，不綁在 credential 上。**

### 3.4 附帶發現：pin 一顆 responses 模型走 chat 面會靜默換模型（真 bug）

```
POST /v1/chat/completions  model=gpt-5.6-luna  + COMPLEX 題
→ response.model = "gpt-5.6-luna"   但  xparse.providers.fast = "bedrock"   ← 真跑 claude-sonnet-5

POST /v1/chat/completions  model=gpt-5.6-luna  + "hi"
→ response.model = "gpt-5.6-luna"   但  xparse.providers.fast = "azure_ai_inference"  ← 真跑 gpt-5.5
```

沒有 `X-Xparse-Model-Substituted` header。成因在 `chat_helpers.py:94 pin_trimmed_models` —— surface filter 先把 luna 剔掉，pin 找不到對應候選就「回全池」，於是照走 strategy 執行別顆。註解自己寫了 “this only covers surface filtering having dropped it”，但選了回全池而不是 fail loud。

**違反 ADR-138 INV-138-13（named model 必須被 exactly 執行）與 ADR-093 inv-4（no silent fallback）。**

> 自查技巧：`xparse.providers.fast` 才是**真正執行**的 provider；`response.model` 對 pin 請求只是回顯。

---

## 4. 根因

### 4.1 chat 面主動剔除 responses 模型

`apps/gateway/bustream/gateway/routing_adapter.py:108 chat_surface_models()` 把 `RESPONSES_PROVIDERS = {azure_openai_responses, openai_responses}` 的候選整個移除，`routes/chat_helpers.py:190` 套用它、`:196` 在全數被移除時回 `422 model_not_on_chat_surface`。

原始動機（issue #712 / PRD-157 §3.7）是**正當的**：responses worker 的 constructor 硬性要求 `store_flag` / `store_source`，chat 請求沒有 → raw `ValueError` → 500。剔除是當時的止血。

但它的副作用沒人算到：**候選集少一顆 = N 變小 = 難度分級整組折疊**。rel 就是 COMPLEX 折進 REASONING。

### 4.2 `provider_code` 一個字串背兩個職責

- **上游協定**：`streaming/workers/factory.py:89` 用 provider 選 worker
- **客戶入口**：`routing_adapter.py:99` 的 `RESPONSES_PROVIDERS` 用同一個字串做 surface 過濾

ADR-323 D2 把 `surface` 提升成 provider catalog 的權威靜態屬性（消掉硬編碼白名單，方向正確），但也把「1 筆 model = 1 個入口」**固化進資料模型**。

而 ADR-319 的原話是相反的：

> “the Chat-vs-Responses API surface is **NOT** a provider the customer picks — it is an internal capability we switch to only when the model declares it needs a Responses-only capability (built-in tools / server-side conversation state / computer-use)”

也就是 surface 本來設計成**內部機制**，落地成 `provider_code` 之後洩到了客戶的定址面 —— 正是 CLAUDE.md §17.1a 講的「機制不該洩進客戶決策面」（ADR-319 的 docstring 自己引了這條）。

### 4.3 這不是 Azure 的問題

兩層證據：

1. **我們這邊**：`apps/iam/xparse_iam/xparse_iam/domain/value_objects/provider_surface.py::resolve_azure_surface` —— Console 只提供一個「Azure OpenAI」選項，**預設就是 Chat Completions**；只有 model 在 `custom_params` 宣告 `requires_responses_api: true` 才被 remap 成 `azure_openai_responses`。同一個 Azure resource 兩條 API path 都在。
2. **Azure 那邊**（一手文件，2026-08-24 更新）：`gpt-5.6` 系列在 Chat Completions **可用**，只是 reasoning 模型參數不同 —— 用 `max_completion_tokens`（非 `max_tokens`）、不支援 `temperature` / `top_p` / penalty，且帶 function tools 時要 `reasoning_effort: "none"` 否則失敗。文件裡唯一標明 Responses-only 的是 `computer-use-preview`。
   - <https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/responses>
   - <https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/chatgpt>

所以 luna / sol 在 responses 面是**我們建 model 時的宣告結果**，不是 Azure 只開了那條路由。

---

## 5. 現況的代價

### 5.1 同一個 app 有三套分級數字

| 難度 | Console 標的（全池 N=4） | chat 面實際（N=2） | responses 面實際（N=2） |
|---|---|---|---|
| REASONING | claude-sonnet-5 | claude-sonnet-5 | gpt-5.6-luna |
| COMPLEX | **gpt-5.6-luna** | claude-sonnet-5 | gpt-5.6-luna |
| MEDIUM | gpt-5.5 | gpt-5.5 | gpt-5.6-sol |
| SIMPLE | **gpt-5.6-sol** | gpt-5.5 | gpt-5.6-sol |

- chat 面欄：**實測 4/4**（§3.1）
- responses 面欄：真元件計算（§3.2）。rel 上 opaque 請求的 `response.model` 回顯 `"default"`（不揭露 backend name，INV-138-1），從外部看不出實際模型，要 audit `routing_decision_recorded` 才能核對。
- Console 欄：`complexity_tiers` 由 `tier_bands()`（SPEC-268 ORDER-01）用**全池 N** 算，不知道有 surface 過濾。

**同一句話從兩個 URL 打會得到不同模型，兩者都「正確」，而 Console 顯示的跟兩邊都不符。**

> 補充：`/v1/responses` 現在**有**跑 strategy（#3821 / ADR-430 §2.1 #12 修好，三源＝pin / binding / resolver）。在那之前它從不呼叫 resolver，opaque 一律取 `sort_order` 序首，Console 設的 `routing_strategy` 在那個面是靜默無效的。

### 5.2 「建兩筆」不只是兩筆 model

| 層 | 要不要兩份 | 依據 |
|---|---|---|
| Provider 端（Azure deployment / OpenAI 模型） | **不用** | 同一個 deployment、同一把 key |
| Xparse credential | **要** | `_credential_provider.py::assert_credential_provider_matches` 嚴格相等；錯誤訊息自己寫「an OpenAI key used for both chat and Responses must be registered once per provider code」 |
| Xparse model row | **要** | 一筆 chat provider、一筆 responses provider |
| 對外 `model_name` | **要不同** | 同 pool 撞名沒有 gate 擋，見下 |

credential 這個檢查是後來才補到寫入邊界的。在那之前錯綁的 row 會讓**整個 app 每一發都 500**（`ValueError: provider mismatch` 在 gateway-validate 才炸），而 Console 顯示模型 `healthy`（連通性 probe 不檢查 provider）。

**撞名沒人擋**：ADR-323 D4（pool 內 addressing-key 唯一性）**未落地**，#2571 已證缺席會造成 prod 全鏈不可用。

其他代價：兩個 `model_uuid` → 價格、health、latency EWMA 各自獨立 → 同一顆模型的成本在 audit 分裂成兩列。

### 5.3 `/v1/messages` 也吃同一個虧

`app.py:1061` flag-gated（`XPARSE_ANTHROPIC_MESSAGES_ENABLED`，預設 OFF）。它翻譯後走 **chat internal flow**（PRD-190 / ADR-239）→ 一樣經過 `chat_surface_models()` → **Anthropic 客戶端同樣看不到 responses-surface 模型**。

修 chat 面等於一次修兩個入口。

### 5.4 客戶是知情選擇的嗎？—— 是（所以「單面」本身不是 bug）

這是本文最重要的界線，先講結論：**「responses 模型只能從 `/v1/responses` 打」是我們告知過、客戶自己勾的，不需要 fix。**

證據：

1. **Azure 家族有明確的勾選項**。`step-provider-connection.tsx:184` 的 checkbox，i18n 文案（`en.json` `modelPool.register.cloud.connection.responsesApi`）：
   > title: "Use the Responses API"
   > description: "This model uses server-side conversation state and built-in tools **instead of the standard chat endpoint**. Leave this off for regular chat models."

   中文版：「此模型使用伺服器端對話狀態與內建工具，**而非標準聊天端點**。一般聊天模型請保持關閉。」

   勾了才寫 `custom_params.requires_responses_api = true`（`use-cloud-register-form.ts:546`），後端才 remap 成 `azure_openai_responses`。**「而非標準聊天端點」已經把後果說出來了。**

2. **OpenAI 家族可以直接選**。`creatable_as` 對照（`_providers.py`）：

   | provider_code | surface | creatable_as |
   |---|---|---|
   | `openai` / `azure_openai` / `azure_ai_inference` / `bedrock` / `vllm` / `google` / `vertex_ai` | chat | 含 `"model"` |
   | `openai_responses` | responses | 含 `"model"` ← **客戶可在下拉選單直接選** |
   | `azure_openai_responses` | responses | **只有 `"credential"`** ← 不在下拉選單，靠上面的 checkbox |

所以 §4.2 講的 `provider_code` 雙職責仍然是事實，但它造成的「單面」後果**對客戶是可見、可選、有文案說明的**。§6 的 A / B / C 因此全部是 **feature（cross-surface serving）**，不是 bug fix —— #2551 原本的 GTM 定位是對的。

**但下面三件事與客戶選了什麼 provider 完全無關，是我們的缺陷**：

| # | 問題 | 為什麼與 surface 選擇無關 | 證據 |
|---|---|---|---|
| **P1** | pin 一顆 responses 模型走 chat 面 → 靜默改跑別顆，回顯 pin 的名字 | 客戶明確指名了模型。無論他選什麼 provider，平台都不該回顯 A 卻執行 B | §3.4，違反 ADR-138 INV-138-13 + ADR-093 inv-4 |
| **P2** | Console 的 `complexity_tiers` 標籤用全池 N 算，與 chat / responses 兩個面的實際落點都不符 | 客戶知道 luna 只走 responses，但**沒有任何地方**能看到「這個 pool 在 chat 面的分級長什麼樣」 | §5.1 三套數字表 |
| **P3** | 混面 pool 配 `complexity_routing` 被靜默接受，實際只用一半候選、難度級折疊，無警告無 audit 標記 | 客戶知道「luna 只走 responses」，但不會自己推出「因此我的 chat 分級從四級變兩級」—— 那是 `anchor = round(t × (N-1)/3)` 的算術後果 | §3.1（rel 4/4）、§1 公式 |

P1–P3 都是「fail-loud vs 靜默降級」問題，與 A/B/C 的 feature 決策**互不依賴**。

---

## 6. 修法分層（難度差很多）

> **先分類**：下表 A / B / C 是 **feature**（讓一筆 model 服務多個入口），依 §5.4 的結論，它們是產品優先序決策、不是修復義務。必修的是 §5.4 的 P1–P3。

| 段 | 內容 | 難度 | 依據 |
|---|---|---|---|
| **A** chat 入口能用 responses 模型 | 候選集過濾從「剔除」改成「翻譯」 | **小** | 輸入翻譯零件已存在且在 fallback 路徑跑著（`worker_setup.py:816`，per-tenant 預設 ON）；**輸出完全不用改** —— responses worker 早就把上游 named-SSE 正規化成內部 chat chunk（`cross_surface.py` 檔頭）。改動集中在 `chat_helpers.py` 一處 + `worker_setup.py` 已有分支。等於把 ADR-323 D3 的 translate 半接上（＝#2551） |
| **B** responses 入口能用 chat 模型 | 反向 | **大** | responses 路由是 ADR-339 **transparent passthrough**（原封轉發上游 named-SSE，連未知事件都 passthrough，`responses_pipeline.py`）。要服務 chat 模型得**從零合成** `response.created` / `output_text.delta` / `response.completed` + response id + store/鏈接語意，還要與 passthrough 在同一路由並存 —— 直接挑戰 ADR-339 的 wire fidelity 不變量 |
| **C** 根治：拆 `provider_code` 雙職責 | model row 改宣告 `upstream_protocol` + `capabilities`，入口不再讀 surface | **ADR 級** | 動 IAM 寫入面、provider catalog（ADR-323 D2）、migration（D4 唯一性還沒做）、Console、gateway 兩個讀取點 |

**A 不依賴 C**，零件也都在（成本最低的那個 feature）。但 **A 不是 rel 那個 pool 的必要解** —— 客戶若接受「luna / sol 只走 responses 面」，那個 pool 需要的是 P3 的警告（讓他知道 chat 面只有 2 顆、分級會折疊），而不是翻譯。

**A 的觸發條件**：有客戶要「同一顆模型兩個入口都打」。屆時注意一個不對稱 —— A 之後，建成 responses provider 的 model 兩個面都通（chat 面走翻譯），但建成 chat provider 的 model 仍只有 chat 面（那要 B）。而這個 workaround 只限 OpenAI / Azure OpenAI 家族：bedrock、vllm、Foundry 沒有 Responses 版本。

### 6.1 能翻與不能翻的界線（寫需求時必須分清）

正確的原則寫成兩句才可實作：

> **一筆 model row 對所有入口都可定址（協定翻譯是平台的責任）；一個請求能不能被服務由「這次用到的能力」決定，失敗必須是明確 4xx，不是靜默降級。**

| 情境 | 該怎樣 | 現在 |
|---|---|---|
| chat 入口打 responses 模型，純文字無狀態單發 | ✅ 翻譯後服務 | ❌ 從候選集剔除 |
| responses 入口打 chat 模型，無狀態單發 | ✅ 翻譯後服務 | ❌ 422 |
| responses 入口用 `previous_response_id` 鏈 / `store=true` server-side state | ❌ 只有真支援的上游能服務，其餘**必須** 422 | 正確，不該改 |
| chat 入口打 embeddings / TTS 模型 | ❌ 能力不存在，永遠 4xx | 正確 |

第三列是硬邊界：`cross_surface.py:230` 翻譯時把 `previous_response_id` 設 `None` —— **有狀態語意翻不過去**，這是能力邊界不是實作偷懶。

### 6.2 A 要注意的一件事

翻譯後的請求不會建 responses binding、不佔 slot（chat 面沒有這個概念）。要顯式確認不會漏計 —— 這是 #4133 那類併發槽洩漏的相鄰面。

---

## 7. 入口面盤點

現有（實查 `routes/` + `app.py`）：

| 入口 | 依據 | 狀態 |
|---|---|---|
| `POST /v1/chat/completions` | — | 主路徑 |
| `POST /v1/responses`、`DELETE /v1/responses/{id}` | PRD-157 / ADR-192 / ADR-437 | 上線 |
| `POST /v1/messages`、`/v1/messages/count_tokens` | PRD-190 / ADR-239 | flag 預設 OFF，翻譯走 chat flow |
| `POST /v1/embeddings` | PRD-039 | 上線 |
| `POST /v1/audio/speech`、`/v1/audio/transcriptions` | — | 上線 |
| `GET /v1/models` | — | 目錄 |

沒有入口面、但外面常要求的（grep `docs/prd` `docs/adr` 找不到規劃 —— 是產品優先序，不是技術債）：

| 入口 | 現況 |
|---|---|
| Google Gemini `/v1beta/models/{m}:generateContent` | 只有**出向** native worker（PRD-170 / ADR-355 Vertex），無入口面 |
| OpenAI legacy `/v1/completions` | 無 |
| `/v1/rerank` | 無 |
| `/v1/images/generations` | 無 |

**該鎖的不變量**：`入口面（客戶協定） ⊥ 模型能力（上游協定）`。model row 宣告需要什麼能力，入口決定用什麼協定講話，adapter 負責翻譯或明確拒絕。這樣 Gemini 入口、legacy completions 之後接進來時，不會各自再長一套 surface 白名單。

---

## 8. 建議行動

依 §5.4 的界線分成「必修」與「等需求」。

**必修（靜默行為，與 surface 選擇無關）**

1. **P1 — pin 靜默替換**（→ **#4558**，2026-09-10 已開）：pin 的名字在 bound set 裡、但不在該入口的**可服務**集時，回 `422 model_not_on_chat_surface` 並說明原因，不要回全池跑別顆。改動點 `chat_helpers.py:94 pin_trimmed_models`（現行註解 “a name that matches no current candidate leaves the set unchanged” 就是這個行為的來源）。有現成 curl 證據（§3.4）。
2. **P2 — Console tier 標籤**：`complexity_tiers` / `complexity_band_offset` 應按入口面分開算，或至少在混面 pool 上標明「此標籤未計入 surface 過濾，chat 面實際為 N=x」。
3. **P3 — 混面 pool 無提示**：proxy 設非 `none` 策略且池內跨 surface 時，Console 顯示可服務候選數與該面的實際分級；audit 的 `routing_decision_recorded` 已有 `candidate_count`，可作為驗證錨點（chat 面看到 2 就是被過濾了）。

**等需求（feature，不是修復）**

4. **A（#2551）**：保持 GTM 定位。觸發條件＝有客戶要一筆 model 兩個入口都打。範圍限無狀態單發；驗收用 §3.1 的 rel 四級表（COMPLEX 回到 luna）。需先決定 `cross_surface_fallback = false` 的 tenant 行為（建議 skip rung + audit 標 degraded，與 ADR-260 INV-260-12 一致）。
5. **B**：只在有客戶要用 Responses SDK 打**非** OpenAI 家族模型時才評估（bedrock / vllm / Foundry 沒有 Responses 版本，A 的 workaround 救不到）。動 ADR-339 wire fidelity，風險大。
6. **C**：寫成 tracking，跟 ADR-323 D4（addressing 唯一性，已有 prod 事故 #2571）綁一起排。在 C 落地前，雙 row 撞名風險真實存在。

**給客戶的短期建議**

7. 要兩個面就拆成**兩個 proxy**（chat pool 全 chat-surface、responses pool 全 responses-surface）—— 分級不互相干擾、成本歸戶不分裂。單一混面 pool 在 P3 修好前，客戶看不到自己實際只用了一半。

---

## 附錄 A：重跑用的探針

```bash
# probe.sh <rel|local|prod> <label> <prompt>；key 從 ~/Desktop/testing/.env 讀
set -a; . ~/Desktop/testing/.env; set +a
curl -sS -D /tmp/h.txt -o /tmp/b.json \
  -X POST "https://xparse.genialtx.com/v1/chat/completions" \
  -H "Authorization: Bearer $XPARSE_API_KEY1" -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"hi"}],"temperature":1,"max_tokens":8}'
python3 -c "import json;d=json.load(open('/tmp/b.json'));print(d['model'],(d.get('xparse') or {}).get('providers'))"
grep -i '^x-xparse' /tmp/h.txt
```

要點：
- **不要**指定 `model` 欄位 —— 省略才會由 routing strategy 決定；填死就是 pin。
- 看 `xparse.providers.fast`（真正執行的 provider），不要只看 `response.model`。
- local 走 `https://localhost:3000/v1/chat/completions`（自簽憑證，加 `-k`）。`localhost:4001` 是 Console dev server，只有 `pnpm dev` 有跑時才通。
- rel 的 `/v1/responses` 目前 `model` 為必填（省略 → 400 `body -> model: Field required`）；`model=default` 可觸發 opaque 路由但回顯 `"default"`。

## 附錄 B：測試題庫（四級階梯）

完整題庫（含 CJK 詞包、陷阱題、離線計分器用法）在 `~/Desktop/testing/問題集.md`（Rev.4，2026-09-08）。本次用到的：

分級邊界：`<0.15` SIMPLE｜`<0.35` MEDIUM｜`<0.60` COMPLEX｜`≥0.60` REASONING

| # | 題目 | 分數 | tier |
|---|---|---|---|
| S1 | `hi` | −0.15 | SIMPLE |
| M2 | `Write a python function that reads a json file and returns a dict, with try/catch around the import.` | 0.30 | MEDIUM |
| C2 | `Refactor the typescript api endpoint that talks to our sql database so it holds up under concurrency, keeps latency low, and does not blow up cpu usage.` | 0.425 | COMPLEX |
| R3 | `Analyze this distributed architecture: the api endpoint hits our sql database with high concurrency, latency spikes, and throughput collapses. Refactor the schema and explain the trade-offs.` | 0.725 | REASONING（heuristic） |

中文四級（ADR-409 後）與陷阱題（T9 字元重疊雙計、T10 日常共現誤觸、T11 結構性盲區）見原題庫 §3、§5。

**權威確認管道**（可信度由低到高）：`response.model` / header → **audit 落盤**（唯一看得到 `tier` / `score` / `cause` / `selected_position` / `candidate_count`）→ 離線計分器。

```bash
docker exec xparse-db psql -U xparse -d xparse_audit -tA -c \
 "SELECT event->'payload'->'decision_evidence'->>'tier',
         event->'payload'->'decision_evidence'->>'selected_position',
         event->'payload'->'decision_evidence'->>'candidate_count'
  FROM audit_events WHERE event_type='audit.governance.routing_decision_recorded'
  ORDER BY seq DESC LIMIT 5;"
```

> `candidate_count` 就是判斷本文問題的決定性欄位：**chat 面看到 2 就是被 surface 過濾了。**
