# e2e 2026-10-07 surfaces lane 報告：六個 API 面 × 已 merge 修正的回歸驗證

> 本 lane 只測原始 API 面（chat、messages、responses、embeddings、audio.speech、audio.transcriptions）與 LLM_api.md §4.2／§4.3 宣稱已 merge 的修正。報告與結果檔都**沒有任何 key 值**；key 一律從 `/Users/peter/Desktop/testing/.env` 讀，或每次執行時在記憶體裡現發、結束時撤銷。
> 結果根目錄：`/Users/peter/Desktop/testing/results/e2e_20261007/surfaces/`（下文 `raw/`、`fixes/`、`repro_surf*/` 等相對路徑都相對於此）；同一份報告也留在該目錄的 `LANE_REPORT.md`。所有 case 的總表：`summary_all_cases.json`（168 筆）；每個 case 的原始事件：`raw/<case-id>.json`。

## §0 結論

1. **六個面的矩陣**（沿用 10-06 的 91 個 case）：**88 PASS、0 個真失敗**。另有 2 筆 FAIL 經判定是預期行為（見 §2.1），1 筆跳過（KER-6，避免建立刪不掉的 openai_responses 模型）。PRD-341 D-1..D-4 的「只記錄」開關仍然只記錄；每個進入執行的請求都恰好一個終端事件；執行前被拒的請求沒有終端事件；用量單位 tokens／characters／seconds 都正確。
2. **17 個修正全部 VERIFIED**。其中 3 個只驗到主要路徑：#6022 沒測 504／500 出口；#6020 沒測拒絕路徑；#5995 沒測 messages／responses 的 classifier 紀錄。
3. **2 個新 finding，都是 P3**，都不是已宣稱修正的回歸：
   - **SURF-1**：非串流 R3 換模型成功時，同一個請求記兩筆 `EXECUTION_STARTED`。
   - **SURF-2**：chat／messages／responses 的 401 兩個關聯 header 都沒有。這屬於 #5667 同一類問題，但 §6.1 沒有列出。
4. **兩個觀察都判定為設計如此**，有文件依據：
   - (a) `/v1/messages` 回報請求自己的 `model`，ADR-221 Amendment A 明文排除。
   - (b) 沒開 thinking 也會回傳 thinking block，PRD-190 G4 規定無條件轉發。缺少 `signature` 則是規格沒寫到的缺口，見 §4。
5. **清理**：本 lane 建立的 app、proxy、model、key 全部清掉，已用 DB 唯讀查詢確認。留下 3 個停用的 policy 空殼（沒有刪除 API）。另外有 1 個已經刪不掉的舊模型被重用，已恢復成 disabled，但它可刪除的時間會往後延（見 §6）。

## §1 環境

| 項目 | 值 |
|---|---|
| 程式碼 | 本機 main `4a4a93331`；origin/main 多 4 個 commit，都不碰 `apps/gateway`（`git diff --stat` 為空），結論適用 |
| gateway | `xparse-gateway` 以 bind-mount 跑本機樹；process 在 02:00:29Z 啟動，晚於最後一個 gateway commit（00:55Z） |
| guardrails sidecar | `xparse-guardrails` 全程 **Up / healthy**（02:39:40Z 起）。本 lane 沒有停止或重啟它；I3（sidecar 停機）沒跑，避免影響其他 lane |
| 入口 | 主要走 `http://localhost:4001`；串流、中斷與 R3 測試走 `https://localhost:3000` |
| 稽核 | `xparse/var/audit/evidence/evidence-2026-10-07T02-20-55.jsonl`，以 X-Request-Id／trace id 串接 |
| app 5260605d | 只用 `XPARSE_API_KEY2` 推論與 GET 讀取，**沒有寫入**。03:40:49Z 的池子變更（claude-sonnet-5-5 換成 claude-haiku-4-5）由使用者本人進行，**不是本 lane** |
| luna 旗標 | `gpt-5.6-luna` 的 `supports_reasoning` 已在 2026-10-06 12:09Z 改成 1，但 `reasoning_effort_levels` 仍是 NULL（見 §5 O-9） |

## §2 六個面的矩陣

腳本 `e2e1007_surfaces_probe.py`，是 10-06 harness 的副本，改動如下：
- 輸出改到本目錄。
- **不建立 openai_responses 模型**：需要 `/v1/responses` 的 case 改用 app 5260605d 池子裡原有的 `gpt-4.1-nano`。
- 每個 case 自動加兩項檢查：(1) unary 面的錯誤回應要帶 #6073 的 header；(2) COMPLETED 要帶該面的用量單位。

### 2.1 結果（91 case）

| 面 | PASS | 其他 | 代表證據（X-Request-Id 前 8 碼） |
|---|---|---|---|
| chat | 8 | — | CONV-1 ef509188、CONV-2 c54ddb91、NEG-10 ab184169、ADM-3 9b1fb1cc |
| messages | 4（另有 count_tokens 1） | — | CONV-3 999917fa、CONV-4 aec941f0、CONV-4b 0882c815、EXT-1 55d7b141 |
| responses | 2 | KER-6 OBS（跳過） | CONV-5 0a67cc44、REP-PN-responses 7adbab06 |
| embeddings | 29 | REP-EMB12 判定為預期 | EMB-1 e2160f58、EMB-7 1622471f、EMB-8 cc463ee6、KER-1 c85e9d03、MISC-4 037b06b6 |
| audio.speech | 11 | SPE-2b 判定為預期 | SPE-1 373a5a65、SPE-3 bddea741、SPE-4 2440761d、KER-3 9dfdb24a |
| audio.transcriptions | 23 | — | STT-2 27b3d8d1、STT-5-R 3146118b、STT-9 db088243、KER-4 eff52b64 |
| 未登記路徑（NEG） | 9 | — | NEG-1 18527a03、NEG-3 7ee2bbe6、NEG-8 34de6309 |
| /v1/models | 1 | — | REP-0 |

兩筆 FAIL 的判定：
- **SPE-2b**（speech 帶 `instructions` 回 400，沒有 header）：這是 FastAPI／pydantic 在 route 執行前就拒絕的請求。#6073 的 PR 本文明寫這類請求不帶 header，LLM_api.md §6.4 也已列出。判定為 known／by-design；後續已在 harness 把它列進 `PRE_ROUTE_REFUSALS`。
- **REP-EMB12**（`dimensions=3072`）：現在回本地 400 `unsupported_dimensions`，沒有呼叫 provider，所以也沒有終端事件。這正是 #6025 要的新行為（10-06 時是 503 加一筆 FAILED）。

### 2.2 Pipeline 一致性（逐項）

| 項目 | 結果 | 證據 |
|---|---|---|
| `surface_gate` 對未登記面 fail-closed（500＋一筆 `REQUEST_REJECTED`） | 外部打不到：所有 route 都已登記。改在 gateway 容器內跑 contract test：`test_dispatch_fail_closed.py`、`test_surface_registry.py`、`test_one_terminal.py` 共 **126 passed**；conformance 套件 **410 passed／358 skipped／6 xfailed**（排除兩支需要 `anthropic` SDK 的檔案） | 容器內 pytest |
| 不存在的 /v1 路徑 | 404 `Invalid URL (...)`，沒有 `code`，也沒有任何稽核（#5992） | NEG-1、NEG-3、NEG-8 |
| 進入執行的請求恰好 1 STARTED＋1 終端事件 | 六個面都成立。例外是 SURF-1（非串流 R3 成功時有 2 筆 STARTED） | 所有 `check_one_terminal` |
| 執行前就被拒的請求沒有終端事件 | 404／400／422／503 都成立 | EMB-4、STT-8、ADM-2..6、MISC-3/4 |
| 用量單位 | tokens：`input_tokens>0`；speech：`audio_input_characters`；transcriptions：`audio_duration_seconds` 或 `audio_input_bytes` | 自動檢查全部 PASS |
| D-1 Kernel 只記錄 | 三個 unary 面都是 `boundary_shadow_would_block` 加 200；chat 照常 403 | KER-1..5 |
| D-2b／D-2c 定址只記錄 | `MODEL_TARGET_NOT_ALLOWED`／`MODEL_NOT_FOUND`，`record_only`，有 `would_status_code`，沒有 `http_status_code` | EMB-8、SPE-3、SPE-4、STT-6、STT-7 |
| D-3 input rail 走 shadow | sidecar 開著時 PII、word filter、moderation 都只記 shadow；embeddings 不跑 llm_classifier | EMB-9-R、EMB-10-R、SPE-5-R、STT-4-R、CLS-4 |
| D-4 transcription output rail 走 shadow | 逐字稿不變，`output_check` 都是 shadow | STT-5-R、STT-5b-R、EXT-srt、EXT-text |
| admission 拒絕 | queue 模式下回 503 `queue_overflow`；embeddings 與 chat 的 header 集合相同 | ADM-2..7 |
| 429 | 見 §5 O-7：interim app token quota 的 429 | — |
| client 中途斷線 | unary 面：1 STARTED＋1 COMPLETED（JSON route 不取消，DISC-1..3）。串流 chat／messages／responses 送 RST：各 1 STARTED＋1 COMPLETED，`termination=client_closed`、`finish_reason=incomplete`（×2） | 7050e5b6、9129a6fb、26b7cf9e、d9bc8c47、4ee6f7e9、bc399e83 |

## §3 修正回歸驗證

腳本：
- `e2e1007_surf_fixes.py`（`quick`、`setup`、`fix`、`tp`、`disc` 幾個階段）
- `e2e1007_surf_vF2_probe.py`（#6020）
- `e2e1007_surf_v5996.py`（#5996）

結果在 `fixes/`、`verify_6020/`、`verify_5996/`。

| PR | 結果 | 證據與說明 |
|---|---|---|
| #6001 | **VERIFIED** | luna 的旗標已改成 true，用它測不出差別。改建一個 `gpt-5-nano`（openai，`supports_reasoning=false`）：chat 與 messages 帶 stop，各 2 次都回 200，PARAM_NORMALIZED 有 `stop:drop:D11`（013feed5、f00162bd、8a30aac0、5d18f4ce） |
| #6024 | **VERIFIED** | `/v1/responses` 用 gpt-4.1-nano，`reasoning={effort}` 與 `{effort,summary}` 各 2 次：都是 `response.completed`，PARAM_NORMALIZED 有 `reasoning.effort:reasoning_drop:D9`（24f8a675、99452d4c、eea82e15、fa282936） |
| #6020 | **VERIFIED（剝除路徑）** | 把 custom 工具放進 `additional_tools`（LEAK）×2：`x-xparse-tools-stripped: custom:exec`，並有 `platform_tool_stripped` 事件（2e994de3、f5312a22），與頂層工具的對照組（9778eded）一致。放進去的 function 工具受治理（`tool_call_detected`）。**拒絕路徑（`tool_call_allowed=false`）沒測**，因為要在帶 openai_responses 模型的 app 上掛政策 |
| #5996 | **VERIFIED** | 重用已經刪不掉的 `4aeefdcb`（openai_responses gpt-5.5）。client 帶 temperature=0 共 2 次，都是 `response.completed`（54ee73c5、e9f34c9d）。enforce／`on_failure=closed`／`classifier.model=auto` 的 judge 共 2 次：200，judge 是 `vcf3-gpt55`，判定 pass（7c90b315、38838302） |
| #6002 | **VERIFIED** | opaque app 串流，用 app code ×2、省略 model、`default`：每個 chunk 的 `model` 都是 app code，`metadata.model` 也沒有其他值，body 裡沒有出現綁定的名稱（feef23a9、4eb5b025、a88fd990、cfd3d845） |
| #6022 | **VERIFIED（4xx 出口）** | 非串流的 provider 400（圖片讀不了）：chat 與 messages 各 2 次都有兩個 header，FAILED 的 `request_id` 與 header 一致；messages 用 Anthropic envelope（19b384b7、6817c1fc、b370e1f9、b3a49c3c）。504／500 出口在本機觸發不了 |
| #5998 | **VERIFIED** | opaque app 用 app code 呼叫 embeddings，回應的 `model` 是 app code（EMB-7 1622471f、REP-EMB7-1 80632f5e、REP-EMB7-2 536e912a） |
| #5995 | **VERIFIED（speech／transcriptions／chat）** | classifier 的 input_check、output_check、blocked 都帶 `guardrail_policy_name`、`guardrail_bundle_uuid`、`guardrail_resolved_from`，與同請求 PII 紀錄的值相同（CLS-1 6019b1a9、CLS-2 91b19b9e、CLS-3 66c0650a、STT-5-R 3146118b） |
| #5993 | **VERIFIED** | 五個面 PARAM_NORMALIZED 的 trace_id 都等於其他事件與 X-Trace-Id（REP-PN chat 5852889d、messages 5c2cd117、responses 7adbab06、embeddings bea87f64、transcriptions ac38f7d8） |
| #6021 | **VERIFIED** | 非串流 chat、messages，以及三個 unary 面（含 admission 拒絕的事件），每個事件都是 `streaming=false`；串流 chat 與 responses 都是 true（CONV-1、CONV-3、EMB-1、SPE-1、STT-1、ADM-2..5、CONV-2、CONV-5） |
| #5992 | **VERIFIED** | `/v1/audio/translations`、`/v1/chat/legacy-completions`、`GET /v1/models/gpt-4o` ×2：都回 404 `not_found_error`「Invalid URL」，沒有 `code`（7ee2bbe6、18527a03、7b919d03、bb46d891） |
| #6025 | **VERIFIED** | `dimensions=3072` 回本地 400 `unsupported_dimensions`，沒有呼叫 provider（REP-EMB12 1f7699f3）。provider 回 400（輸入超過 context）時是 400 `provider_error` 而不是 503，並有 1 筆 FAILED，`error_status_code=400`（68e2027b、3c7b2ce1、0246b9e5、04773b14） |
| #6023 | **VERIFIED** | 串流加上 `include_usage`：delta、done、usage、xparse 各種 chunk 共用同一個非 0 的 `created`（90b447ae、d77d4b66） |
| #6070 | **VERIFIED** | 自建 app：primary 是死掉的 vllm endpoint，備援是沒有憑證的 gpt-4o-mini。非串流 chat 與 messages 各 2 次：422，帶 X-Request-Id 與 X-Trace-Id；稽核順序是 PROVIDER_FALLBACK、ROUTING_DECISION、恰好 1 筆 FAILED（`worker_setup_error`、422、`model_uuid` 是備援模型、ledger 0/0）（1451d4e3、db346bd1、ff13885d、20bfedb8） |
| #6071 | **VERIFIED** | opaque app 用 app code 或 `default`：422 的訊息是「...for application `<code>`...」（f4d6a15b、2a2b0766、940ffbb8、a2b6c0f1）；provider 4xx 的訊息是「...Its detail is withheld...」（68e2027b、0246b9e5）。沒有 embedding 模型時，404 回的是 client 自己送的字串（`Model '<app code>'` 或 `Model 'default'`），不洩漏被隱藏的名稱。harness 對 `default` 要求「訊息必須寫出 app code」太嚴格，2 筆 FAIL 改判為 PASS |
| #6072 | **VERIFIED（chat）** | 選單型 app 5260605d 用 app code：串流每個 chunk 與非串流 body 都是實際執行的模型 `deepseek-flash`，等於 COMPLETED `model_uuid` 對應的名稱（90b447ae、d77d4b66、21d63651、7937f6cc）。R3 之後回報備援的 `gpt-4o-mini`：非串流 3929c950、56c25e29，串流 c14d8d81。`default` 經 R3 後 `X-Xparse-Model-Default: applied=gpt-4o-mini`（3db57551）。messages 依設計除外（§4 a） |
| #6073 | **VERIFIED（route 內的錯誤）** | unary 面的 404、400、415、422、500、502、503，以及 401，都有兩個 header（EMB-4 cde21516、FIX-6073-415 0cbf27cc、STT-8 55d8217c、STT-9 db088243、SPE-4 2440761d、ADM-2 3d197cb1）。帶 traceparent 時，X-Trace-Id 等於它的 trace id（8d8d8aea、5b5e986f、048f3e7f、3da24c54）。speech／transcription 在 route 執行前被 FastAPI 拒絕的請求（錯的 Content-Type、speech 的模型名稱清單）沒有 header，屬設計如此（#6073 PR 本文、§6.4） |

## §4 協調者交辦的兩個觀察

### (a) `/v1/messages` 回報 app code，chat 回報實際執行的模型：**設計如此**

- **規格依據**：ADR-221 Amendment A §2.6.2 的「不變」清單：
  - 第 144 行：「`/v1/messages`：用 Anthropic 請求自己的 `model`，不讀 chunk 的 `model`（`routes/messages.py`），不變。」
  - 第 145 行：「`/v1/responses`：不經 `format_sse_event`，不在範圍。」
  - #6072 的 PR 本文也把 messages 與 responses 列在「Unchanged」。
  - 測試 `tests/integration/test_menu_app_answer_model.py:416`（`test_messages_surface_keeps_the_requested_model`）把這個行為鎖住。
- **程式位置**：
  - 串流：`G/routes/messages.py:487` 把 `model=req.model` 傳進 stream builder（`anthropic_translation.py:567` 的 message_start）。
  - 非串流：`messages.py:503` 呼叫 `to_anthropic_message_safe(openai_json, req.model)`，在 `anthropic_translation.py:447` 寫入 model。
  - chat core 已經把實際執行的模型寫進 `openai_json["model"]`，但這個值被丟掉了。
  - `answer_model()` 只有 chat 會呼叫。
- **實測**：
  - R3 之後 messages 仍回 app code，但實際執行的是 gpt-4o-mini（dbd3e9f0）。
  - pinned 的請求回報被點名的模型，例如 `claude-sonnet-5-5`。
- **規格缺口（不算 bug）**：
  - INV-221-2 原文是通用的：response.model 要報「實際 resolved／ran」的身分。
  - Amendment A 排除 messages 和 responses 的理由是「程式怎麼寫」，不是契約層面的決定。
  - 要讓三個對話面一致，需要再修一次 ADR-221（Amendment B）。

### (b) 沒有要求 thinking，`/v1/messages` 也回傳沒有 `signature` 的 thinking block

- **回傳 thinking 本身：設計如此（隱含）**。
  - PRD-190 G4（第 34 行）無條件規定：「內部 `reasoning_content` 翻成 Anthropic `thinking` content block」。依據是 ADR-056 的透明轉發。
  - 程式在 `anthropic_translation.py:400-403`（非串流）與 `:627-635`（串流）。
  - 請求的 `thinking` 欄位只影響 `reasoning_effort`（`:371-376`）。註解寫明「the worker forwards reasoning_content regardless」。
  - 測試 `test_messages_inband_failure_forwards_text.py:130-134` 鎖住「沒帶 thinking 參數也會出 thinking block」。
  - 驗收條件 A5／I4 只涵蓋 thinking 開啟的情況。沒有文件把這點和 Anthropic「只在開啟時回傳」的行為放在一起權衡過。
- **缺 `signature`／`signature_delta`：規格沒寫到的缺口，不是回歸**。
  - wire 上從來沒有 signature，Xparse 的文件也沒有提到 Anthropic thinking signature。
  - 往外送時，`streaming/workers/anthropic_worker.py:402-406` 只處理 `thinking_delta`，所以就算後端是真的 Claude，signature 也會被丟掉。
  - 往內收時，translator 不讀歷史裡的 thinking block（SPEC-307 RF-14），所以 Xparse 自己不會因此壞掉。至於轉送到原生 Anthropic 時下一輪會不會壞，由協調者另行實測。

### 交叉參照（不重複開 finding）

smoke 裡 messages 非串流的 `stop_reason=max_tokens`、串流卻是 `end_turn`，是 Claude Code lane 的 **CC7-F3**（`anthropic_translation.py:530-549`）。refusal 或 max_tokens 變成 `end_turn` 的情況見 **CC7-F2**。

## §5 Findings 與其他觀察

### SURF-1（P3，NEW；R3 上線以來就存在，不是已宣稱修正的回歸）：非串流 R3 換模型成功時，記兩筆 `EXECUTION_STARTED`

- **症狀**：
  - 非串流 chat 或 `/v1/messages` 的 primary 失敗、R3 換到的備援成功時，稽核順序是：`request_received → started → provider_fallback → started → completed`，共 2 筆 STARTED、1 筆 COMPLETED。
  - 對照組：
    - 同一個 app 的串流請求只有 1 筆 STARTED（3a68e417、e115441f、c14d8d81）。
    - #6070 的路徑（備援建不起來）是 1 筆 STARTED＋1 筆 FAILED。
- **重現**：`uv run --no-project python e2e1007_surf_r3_double_started.py 2`。腳本自建資源並自己清掉。4/4 重現：81ab2331、c796ca43、eb1e07d1、b2006cdd，結果在 `repro_surf1/`。在 fixes 階段另外重現 6/6：3929c950、dbd3e9f0、3db57551、56c25e29、ad53a0c1、52e457ae。
- **根因**：
  - `G/non_streaming_handler.py:777` 在 `handle_non_streaming` 裡呼叫 `settle_started`。
  - R3 的重跑 `_execute_fallback_non_streaming`（`:2032`，由 `:1445` 呼叫）在 `:2103` 又呼叫一次 `handle_non_streaming`，所以每次 attempt 都發一筆 STARTED。
  - 串流的 R3 在同一個 driver 裡換 manager，不會重發。
- **契約**：SPEC-308 TP-1 只規定終端事件的數量；ADR-084 的生命週期是一個 STARTED 對一個終端事件；SPEC-308 §9.9 寫的是 STARTED「經 terminal 發出」。本 lane 依交辦的一致性準則（1 STARTED＋1 terminal）判為不一致。
- **影響**：
  - 用 STARTED 與終端事件比例做「有開始、沒結束」偵測或計數的盤點，會在每次 R3 多出一筆孤兒 STARTED。
  - #6072 讓非串流的 `default` 請求也會走 R3，觸發面跟著擴大。
- **修法方向**：R3 重跑時讓 `handle_non_streaming` 略過 STARTED（例如帶旗標），或在 SPEC-308 §9 明文規定 STARTED 是「每次 attempt」並補上 attempt 編號。二擇一要由 Peter 決定。

### SURF-2（P3，known family #5667，但 LLM_api.md §6.1 沒列出）：chat／messages／responses 的 401 兩個 header 都沒有

- **症狀**：用無效 key 打 `/v1/chat/completions`、`/v1/messages`、`/v1/responses`，回 401，沒有 X-Request-Id，也沒有 X-Trace-Id（:3000 與 :4001 都一樣）。同樣的 401 打到 embeddings、speech、transcriptions，兩個 header 都有（#6073）。
- **重現**：`uv run --no-project python e2e1007_surf_401_headers.py 2`。對話面 12/12 重現；unary 面 12/12 兩個 header 都有。結果在 `repro_surf2/`。
- **根因**：
  - `G/auth_handler.py:399-404` 丟 `HTTPException(401, "Invalid API key")` 時沒有帶 `headers`。
  - unary 面的 route 用 `with_correlation_headers` 把 pipeline 的結果包起來（`G/routes/embeddings.py:63,67`、`G/unary_execution.py`）；chat、messages、responses 的 route 對 pipeline 在 auth stage 丟出的例外沒有做同樣處理。
- **分類**：屬於 #5667（錯誤回應缺關聯 header）這一類問題。§6.1 剩餘清單只列了 worker setup／model resolution／routing plan 的錯誤，以及「pipeline stage 拒絕只帶 X-Request-Id」，401 兩個 header 都沒有並不在清單上。建議在 #5667 補一則留言，不另開新票。
- **連帶確認**（屬 known §6.1）：這三個面的 404（未知模型）只有 X-Request-Id（ENV-chat-404 dd9b8fe5、ENV-messages-404 202fbcee）；PRD-190 §3.5 規定 messages 錯誤回應 MUST 帶兩個 header。

### 其他觀察（不列為 finding）

- **O-1　Anthropic provider 400**：credit 用完，是環境問題，不算 bug。腳本 `e2e1007_surf_anthropic_4xx.py`，自建 app，第一個模型是 claude-sonnet-5-5，第二個是 gpt-4o-mini，每格跑 2 次：

  | 面／模式 | client 收到 | 稽核 | R3 |
  |---|---|---|---|
  | chat 非串流（pinned 與 app code 都一樣） | 400 OpenAI envelope：`invalid_request_error`、`code: provider_error`，原樣轉出 provider 訊息，兩個 header 都有 | 1 STARTED＋1 FAILED（`error_type=provider_error`、400） | 無 |
  | chat 串流 | 200，in-band `data: {"error":...}`，兩個 header 都有 | 1 FAILED（`error_type=provider_client_error`、400） | 無 |
  | messages 非串流 | 400 Anthropic envelope：`{"type":"error","error":{"type":"invalid_request_error",...}}`，兩個 header 都有 | 1 FAILED（`provider_error`） | 無 |
  | messages 串流 | 200，`message_start` 後接 `event: error`（Anthropic 形狀） | 1 FAILED（`provider_client_error`） | 無 |
  | responses | anthropic 模型不在此面（cross-surface 400） | — | — |

  證據：2d22bf61、f1cba970、1351a800、a08b02fa、a0d1c7ca、b766d2a8、1e8218b9、3273dfac 等，結果在 `anthropic_4xx/`。
  - 不做 R3 是正確的：`effective_error_code` 把 provider 4xx 分類成 `provider_client_error`，不在 `FALLBACK_ELIGIBLE_CODES` 裡（`G/fallback_handler.py:67-74`）。
  - 同一個 400，非串流 FAILED 記成 `provider_error`、串流記成 `provider_client_error`。ADR-441 第 35 行已經記載 `error_type` 混用原始碼與重分類碼，判為 known。
  - 補充：claude-sonnet-5-5 在 03:40Z 已經從 5260605d 的池子移除，所以對 5260605d pinned 會回 404 `model_not_found`（`anthropic_4xx_1007114457.json`）。
- **O-2　`/v1/responses` 沒帶 `stream` 或 `stream:false` 仍回 SSE**（2a09beba、6a80b273）：設計如此。ADR-437 第 26 行「永遠串流」；SPEC-282 RSP-RES-8。
- **O-3　speech 的模型名稱清單在認證前就檢查**：只接受 tts-1 與 tts-1-hd；未知名稱與 app code 都回 400，沒有 header，也沒有稽核（05f94522）。設計如此：PRD-341 第 231 行與 D-2c，以及 §6.4。
- **O-4　transcription 上傳空檔回 500**：body 是 `text/plain` 的「Internal Server Error」，不是 OpenAI 的 JSON envelope（STT-9 db088243）。與 10-06 相同，現在多了兩個 header。SPEC-308 §10.13（第 758 行）宣告 client 的回應不變。這是早就存在的 envelope 小瑕疵，可以列入 P3 清理。
- **O-5　interim 應用 token quota 的 429**（PRD-289／ADR-398，quota 設 1K）：
  - chat 與 messages 的 429 只有 X-Request-Id；embeddings 兩個 header 都有；兩邊都沒有 Retry-After。
  - speech 與 transcriptions 不受 token quota 限制：1200 字元仍回 200（音訊的單位不是 tokens）。
  - 正式的 A20（budget layer token 預算）沒有測。
- **O-6　R3 加上 `default`**：COMPLETED 的 `target.resource_id` 寫的是失敗 primary 的名稱，`model_uuid` 才是備援模型。依 ADR-221 Amendment A 第 142 行（「`target.resource_id` 仍是 `request.model`」），屬設計如此。
- **O-7　admission 只回 503**：queue 模式下打不到 rate-limit 的 429，與 10-06 相同。
- **O-8　新建 app 的第一個請求偶爾很慢**：14 s（f4d6a15b）、37.6 s（26175b7d），之後都在 1 s 以內。沒有重現，可能是當時其他 lane 的並行負載，不列入 finding。
- **O-9　#6068 的前提已經改變**：本機 luna 的 `supports_reasoning` 已改成 1，但 `reasoning_effort_levels` 是 NULL。依 #6068，`minimal` 的請求現在可能拿到 provider 400。這只是本機資料，部署前的唯讀比對仍要照 #6068 的流程做。

## §6 建立的資源與清理

| 類別 | 狀態 |
|---|---|
| app | 本 lane 建了 12 個（harness 5 個，fixes 加上 bud、anth 共 7 個），repro 與 #5996 各 1 個。DB 唯讀查詢：名稱以 `e2e1007` 開頭的 app **43 個全是 terminated**，這個數字也包含其他 lane 的 app |
| proxy | 主 proxy 1 個、額外 6 個，加上 repro 與 #5996 各 1 個，全部 terminate |
| 模型 | 本 lane 建的 17 個全部 `removed_at` 已設定，沒有任何仍掛著的 source。**沒有建立任何 openai_responses 模型** |
| API key | harness 31 個，加上 #5996 與 repro 的 key，全部 revoked |
| 政策 | version、bundle、binding 都已停用。policy 本體沒有刪除 API，留下空殼：`7a5d71dc-0611-4e9b-b16d-c27af23e0426`（guard）、`cac99879-f9b8-4b0f-aff9-315fc10bd1ba`（ratelimit）、`e837843d-f714-48ef-b387-6a7f589722dc`（#5996 的 guard） |
| 重用的舊模型 `4aeefdcb-f783-41d4-becd-e8bff6d3776d` | 測試期間由 disabled 改成 pending，掛到臨時 proxy；結束後已拆掉 source，恢復成 **disabled**。但這次新增了 5 筆 ResponsesBinding（store=false，最晚的 expires_at 是 2026-10-07 04:42:43Z），**它可以刪除的時間會比 LLM_api.md §6.5 寫的 2026-10-08 03:00 UTC 晚**，刪除前請再確認 |
| app 5260605d | 沒有寫入。只用 key 推論；它池子裡的 gpt-4.1-nano 因 `/v1/responses` 呼叫多了幾筆 ResponsesBinding（那是它自己的模型） |
| repo | 沒有修改（`git status` 與開始時相同）。容器內的 pytest 跑在 bind-mount 的樹上，conformance 那次有設 `PYTHONDONTWRITEBYTECODE`，第一次 contract test 可能留下 gitignore 的 `__pycache__` |
| guardrails sidecar | 沒有動，全程 healthy |

## §7 腳本清單（都在 `/Users/peter/Desktop/testing/`）

| 腳本 | 用途 |
|---|---|
| `e2e1007_surfaces_probe.py` | 六個面的矩陣與 `cleanup`，已擴充成也會清理額外的 proxy |
| `e2e1007_surf_fixes.py` | 修正回歸（`quick`／`setup`／`fix`／`f6001`／`r3`／`f6071`／`tp`／`disc`／`envelopes`） |
| `e2e1007_surf_vF2_probe.py`、`e2e1007_surf_vF2_common.py` | #6020 |
| `e2e1007_surf_v5996.py` | #5996（重用 4aeefdcb，`run`／`cleanup`） |
| `e2e1007_surf_anthropic_4xx.py` | Anthropic provider 400 在各面的處理 |
| `e2e1007_surf_r3_double_started.py` | SURF-1 的獨立重現（自建、自清） |
| `e2e1007_surf_401_headers.py` | SURF-2 的獨立重現 |
