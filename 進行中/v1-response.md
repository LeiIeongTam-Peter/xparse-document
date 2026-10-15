# `/v1/responses` 結構性落後：進度（第一輪 2026-10-04 完成；第二輪 2026-10-05 修補已 merge，只剩 #5870；兩輪都待部署）

計畫：`docs/草案/解決-v1-response.md`（Rev.2）。評審與修訂後的切片：`docs/草案/解決-v1-response-評審.md` §5。

## 一句話

- **計畫內的切片全部完成、全部 merge**：S1–S6，最後一個是 #5811（`bf73f8ad2`）。
- **都還沒部署**：rel（`v1.79.0`）和 prod（`v1.76.4`）上看不到這些改變。
- **剩下的事**：部署驗證、關 issue（兩輪共 29 張，都是部署驗證後才關），以及「以後可以做」裡的範圍外項目。
- **2026-10-05 複查**：讀碼（4 路）加本機實測（最新 main `213fea709`、真 Codex／Claude Code／OpenCode），找到 9 個文件沒列的缺口，guardrail 有兩個是真的繞過。詳見下方「2026-10-05 複查」。第二輪的工作清單在 `docs/進行中/v1-response-checklist.md`。
- **第二輪（2026-10-05）**：16 個 PR 已 merge（#5838–#5869，未部署），修好 I1–I9、#5671，以及修補途中新發現的 7 個缺口（#5852–#5854、#5861–#5864）；只剩 #5861（semantic cache 繞過）在 PR #5870。見下方「第二輪切片」。

## 四個問題的狀態

| 問題 | 做了什麼 | 還沒好的 |
|---|---|---|
| **Cost** | 斷線也照實記帳（S4）；三個面共用一個結尾，先記帳再發事件（S5 P3）；Responses 的失敗事件帶模型與狀態碼，Console 的每模型錯誤拆分算得到它（T-5）；被 output rail 擋下也記模型健康（T-3） | prod 不扣 Codex 用量：#5257、#5681 還沒上 prod，跟架構無關。`service_tier`、`prompt_cache_options` 目前記錄後剝除，等計價支援。10-05 新發現的 I4–I6（斷線只記 user 文字、中途失敗 prompt 記 0、失敗記帳丟 cached tokens）**已修、未部署**（#5844、#5842）。殘留：串流 chat 在 usage chunk 之後才失敗仍記 0 cache（罕見） |
| **Guardrail** | 擋下格式改成 Codex 不會重試（S1；政策類 403 改 400，#5801）；這輪補了反方向的缺口：chat／messages 串流以前完全沒檢查輸出（#1508，#5811） | Responses 的執行邊界仍是 shadow（#1060），等營運切換。10-05 新發現的 I1–I3、I7、#5671，以及修補途中找到的非串流工具參數不檢查（#5852）、semantic cache 繞過（#5861）**都已修**：前者已 merge、未部署；#5861 在 PR #5870。殘留：denylist／`ExecutionRefused` 的 403 仍讓 Codex 重試（刻意不改，同 Amendment B） |
| **Agent policy** | 請求端 Tool 規則三個面共用一份（P2b）；Responses 新增回應端規則：模型叫到被禁的工具，整輪扣下（S6，#5806；10-05 讀碼確認 hold 涵蓋 6 種 client 端呼叫型別、`invalid_prompt` 不重試） | 真 Codex 驗收 A22 BLOCKED：測試模型不會去叫被拿掉的工具，觸發不了；gateway 這一半由 conformance 測試覆蓋。v1.1 其餘功能（session 上限、deny 當成工具錯誤）不在這次範圍。10-05 的 C-304-310／C-304-152 隨第二輪改寫（output rail 擋下時整輪丟掉，Tool 規則不再判定；已檢查的文字先送、再 R-A） |
| **Smart routing** | Responses 改走和 chat 同一條前置流程，routing、session affinity、預算、policy 同一份（S5 P2）；`llm_judge_routing` 會真的問判官（#4248，#5804；10-05 實測 gpt-5.4 當判官也正常）；provider 卡住時會逾時（#5751，#5795） | Responses 沒有 semantic cache（#4247，設計延後）。10-05 新發現的 I8（換到 DeepSeek 會 400）、I9（TTFT 量到 `response.created`）**已修、未部署**（#5839、#5840）。殘留：加密 reasoning 只在 R3 守住憑證（#4878，已補充留言）；用 `openai`／`vllm` 註冊、指向 DeepSeek 的模型不在 #5836 範圍 |

## 2026-10-05 複查（讀碼＋本機實測）

- **方法**：4 個 agent 對 `origin/main` `c61161f41` 讀碼（cost／guardrail／routing／agent policy），重點自己抽查原始碼；再對本機最新 main（`213fea709`，gateway 掛 source）實測。
- **證據**：`~/Desktop/testing/results/responses_gap_probe/REPORT-2026-10-05.md`（每列有 request_id）；腳本 `responses_gap_probe.py`、`agent_block_probe.py`、`agent_e2e_analyze.py`；三家 client 的錄製在 `results/agent_e2e_1005/interceptor.jsonl`。
- **原本的宣稱**：S1–S6 的內容大致都對上了。被推翻的只有讀碼時的一個推論：「判官送 `temperature=0` 會讓 openai_responses 的 gpt-5 失敗」，實測正常。

| # | 缺口 | 嚴重度 | 證據類型 | issue |
|---|---|---|---|---|
| I1 | Responses buffer 模式只在 `response.completed` 檢查；provider 回 `incomplete`／`failed` 時，終端事件帶全文原樣送出，連 output_check 稽核都沒有 | 高 | 實測（暴力文字原樣送出） | #5829 → 已修 #5838 |
| I2 | Responses buffer 模式不扣、不掃工具呼叫：被擋那輪的 function_call 已送出（Codex 收到 `.done` 就執行）；寫在工具參數裡的內容完全不檢查 | 高 | 實測（G2b frame 12／14；真 Codex 把暴力文字放進 `echo` 執行） | #5830 → 已修 #5838 |
| I3 | chat 串流 buffer 模式：有工具呼叫的那輪跳過扣住檢查，文字被默默丟掉，工具呼叫送出，`finish_reason=stop`，擋下只記在稽核 | 高 | 實測（真 OpenCode，`marker.txt` 被建出來） | #5831 → 已修 #5847 |
| I4 | Responses 的 input 估算只讀 `role=user` 文字（`instructions`、`function_call_output` 都不算）：斷線記帳、預算預留嚴重偏低 | 中高 | 實測（14／9,829；真 Codex 40／約 6,079） | #5832 → 已修 #5844 |
| I5 | Responses 串流中途失敗（idle deadline、截斷、worker error）和 reaped，prompt 記 0 | 中 | 讀碼 | #5833 → 已修 #5844 |
| I6 | 失敗嘗試記帳沒傳 cached／cache-write tokens，快取命中全部按原價算 | 中 | 讀碼 | #5834 → 已修 #5842 |
| I7 | Responses 開串流前的 404（未知模型）、422（模型只在另一個面）、admission 403（denylist、`ExecutionRefused`）仍讓 Codex 重試 5 次 | 中 | 實測 404／422；403 讀碼 | #5835 → 已修 #5841 |
| I8 | 同一個 session 中途從別的模型換到 deepseek（thinking 模式）時，前面的 assistant 回合沒有 `reasoning_content`，provider 回 400，agent session 中斷 | 中高 | 實測（真 OpenCode，gpt-5.5 → deepseek） | #5836 → 已修 #5839 |
| I9 | Responses 的 TTFT 記在第一個轉發事件（`response.created`），不是第一個 token，所以 latency objective 在這個面幾乎沒有鑑別力 | 中 | 讀碼 | #5837 → 已修 #5840 |
| — | #5671：`tools[].type` 是 list 或 dict 時回沒有說明的 500 | 中 | 實測 | 既有 #5671 → 已修 #5843 |
| — | 加密 reasoning 只在 R3 failover 時守住憑證，第一次選模型和 tier 升級時沒有 | 中 | 讀碼 | 已留言 #4878 |

**實測時看到的正常現象**（不是缺口，留作紀錄）：
- 三家 client 的多步驟任務都能完成。
- Codex 被擋時只送 1 次請求，說明訊息正確顯示，S1 和 #5801 有效。
- Claude Code 被擋時，串流內錯誤之後會重送一次、收到 451 才停，等於一次擋下花兩次請求（低，觀察中）。
- 這個 app 沒開 session affinity，所以 agent 每一輪都會跑一次判官（設定面，不是缺口）。
- 模型多數沒設價，`price_source=unpriced`，成本算成 0（設定面，不是缺口）。
- output 階段不做 PII 遮罩，這是 ADR-309 INV-309-9 的設計，不是缺口。

## 第二輪切片（2026-10-05，全部未部署；細節與證據見 `v1-response-checklist.md`）

| 片 | 修什麼 | issue | PR | 設計文件 |
|---|---|---|---|---|
| W1 | Responses buffer 模式扣住整輪、`incomplete` 也裁決、工具參數一起送檢 | #5829、#5830 | #5838 | ADR-437 Am.D、SPEC-282 Rev.27、SPEC-304 Rev.13 |
| W2 | chat 串流 buffer：工具呼叫回合先檢查再放行 | #5831 | #5847 | ADR-318 Am.D、SPEC-217 C-217-21、SPEC-304 Rev.14 |
| W3 | Responses prompt 估算納入整段計費輸入；中途失敗／reaped 也記估算 | #5832、#5833 | #5844 | SPEC-282 Rev.28 |
| W4 | 失敗記帳帶 cached／cache-write tokens（三個面） | #5834 | #5842 | SPEC-302 Rev.11 |
| W5 | Responses 定址拒絕 404／422 改 400 | #5835 | #5841 | ADR-437 Am.E、SPEC-282 Rev.29 |
| W6 | 送 DeepSeek 前補空 `reasoning_content` | #5836 | #5839 | ADR-208 Am.9、SPEC-174 Rev.2 |
| W7 | Responses TTFT 從第一個輸出事件算 | #5837 | #5840 | SPEC-276 Rev.19、SPEC-282 Rev.30 |
| W8 | 過期 docstring | — | #5850 | — |
| W9 | Responses `tools[i].type`／`input[i].type` 非字串 → 400 | #5671 | #5843 | SPEC-307 Rev.1 |
| W10 | 非串流 chat／messages 檢查工具參數 | #5852 | #5859 | ADR-318 Am.E、SPEC-217 C-217-22 |
| W11 | `/v1/messages` tool `type` 非字串 → 400 | #5853 | #5860 | SPEC-307 Rev.2 |
| W12 | 串流工具呼叫回合結尾 `finish_reason="tool_calls"` | #5854 | #5858 | SPEC-217 C-217-23、SPEC-304 Rev.15 |
| W13 | semantic cache 只存 output rail 放行過的回答 | #5861 | #5870（CI 中） | ADR-054 Am.A |
| W14 | 非串流「文字＋工具呼叫」保留文字 | #5862 | #5867 | SPEC-210 Rev.1 |
| W15 | `/v1/messages` image `source`／`text`／`budget_tokens` 格式錯誤 → 400 | #5863 | #5869 | SPEC-307 Rev.3 |
| W16 | TC-264-42 計時測試改相對量測（CI flake） | #5864 | #5868 | SPEC-264 Rev.13 |

## 結構上的改變（以後加功能不會再漏一邊）

- **一條前置流程、一個結尾**：chat、messages、Responses 走同一套程式（ADR-494：`dispatch_pipeline.py`、`terminal.py`），不再各寫各的。
- **三面一致性測試**：同一支測試跑三個面，有一邊沒做到 CI 就紅；已知缺口必須登記 issue 才能放過（ADR-492）。
- **請求欄位分類**：每個欄位明定轉送、拒絕或記錄後剝除；SDK 加新欄位時 CI 會發現（ADR-493）。

## 第一輪切片進度（S1–S6）

| 切片 | 內容 | 狀態 | PR |
|---|---|---|---|
| S1 | Responses 擋下格式（Codex 不再重試 6 次） | merged，未部署 | #5750 |
| S2 | 三面 conformance 測試＋缺口登記 gate | merged（只有測試，不需部署） | #5756 |
| S3 | 請求欄位分類（轉送／400／記錄後剝除）＋SDK 漂移 gate | merged，未部署 | #5757 |
| S4 | 終止用量一處解出；斷線記為取消 | merged，未部署 | #5758 |
| S4 後續 | Audit `usage_outcome()` 認得取消；指標 bump；`token_estimate_source` 改用 ADR-419 詞彙；3.12 race 測試 skipif | merged，未部署 | Audit#197、#5763、#5764、#5765 |
| S4 驗證 | 真 Claude Code／OpenCode／OpenAI SDK 斷線測試 | A39、A41、A42、OpenCode PASS；A40（Codex）BLOCKED | #5768 |
| S5 | pre-dispatch 合一（ADR-494）：P0–P2g | merged，未部署 | P0 #5762、P1 #5769、P2a #5770、P2b #5771、P2c #5773、P2d #5779／#5783、P2e-1 #5784、P2e-3 #5786、P2f-1 #5788、P2f-2 #5790、P2f-3 #5792、P2g #5793 |
| S5 缺口修補 | #5755 Responses 定址拒絕補稽核（同 chat 的拒絕） | merged，未部署 | #5776 |
| S5 收斂 | #3822／#4558 定址前置條件兩面一致：chat 釘選只在 Responses 面的模型改回 422（以前被靜默換模型）；沒綁模型兩面 400 | merged，未部署 | #5780 |
| S5 收斂 | D-16：Responses routing 的非預期錯誤回 500 `Policy evaluation failed`、binding 服務不可達回 502（以前都是框架 500） | merged，未部署 | #5785 |
| S5 收斂 | D-17：chat／messages 的 Policy Kernel 403 改用 SPEC-032 §10.1.1 envelope（帶 `code`） | merged，未部署 | #5787 |
| S5 收斂 | D-21：chat 被 endpoint queue（Layer 2）拒絕時也還 fleet root permit | merged，未部署 | #5789 |
| S5 收斂 | D-20：Responses shadow 模式下 kernel 評估錯誤也寫稽核（以前只寫 log） | merged，未部署 | #5791 |
| S5 缺口修補 | #5754：Responses 也執行 `streaming_allowed=false`（每個請求 403，同 chat） | merged，未部署 | #5796 |
| S5 P4 | #5751：Responses 套用串流 idle deadline，httpx read timeout 跟著設定值 | merged，未部署 | #5795 |
| S5 P3 | 單一 terminal：設計（SPEC-308 §9）；P3b 串流 chat＋Responses 走 `gateway/terminal.py`；P3c 非串流＋agent mode（先記帳） | merged，未部署 | #5794、#5797、#5798 |
| S5 P3 T-5 | Responses 的 EXECUTION_FAILED 帶 `error_status_code`／`model`／`error_code`；chat 半查證不需改碼（已帶 `routing_mode`／`param_*`），conformance 鎖住 | merged，未部署 | #5800、#5807 |
| 收尾 | ADR-494、SPEC-308、Core-ADR-01 狀態列 | merged | #5799 |
| S5 收斂 | ADR-437 Amendment B：Responses 上帶 policy code 的 403（Kernel enforce、`streaming_allowed`）改回 400，Codex 不再重試 5 次 | merged，未部署 | #5801 |
| S5 P3 T-4 | gateway 自己的例外（非 `WorkerError`）不再算 provider 健康失敗（chat 串流＋Responses） | merged，未部署 | #5802 |
| S5 P2 #4248 | ADR-411 Amendment E：Responses 的 `llm_judge_routing` 也問判官（判官＝本面候選尾，經 Responses API 呼叫；`response_format`→`text.format`） | merged，未部署 | #5804 |
| 並行修補 | Foundry worker 把傳輸錯誤報成 `WorkerError`（以前串流 chat 會把 provider 斷線記成成功的空回覆） | merged，未部署 | #5805 |
| S5 P3 T-3 | Responses 被 output rail 擋下也記 provider 健康成功與 routing actuals | merged，未部署 | #5808 |
| S5 P3 T-2 | 非串流被 output rail／classifier 擋下時 `finish_reason` 記 `content_filter` | merged，未部署 | #5809 |
| S6 前提 | P8（`function_call`；平行呼叫逐筆關閉）、P10、hold 延遲實測；A40、A31 PASS；A33 BLOCKED | merged（文件） | #5803 |
| S6 | Responses 回應端 Tool 規則（ADR-490 v1.1，#5753）：hold 到終端、整輪扣下為 E 類 `response.failed`、retire binding | merged，未部署 | #5806 |
| S6 驗收 | PRD-337 A22 真 Codex：BLOCKED；請求端 21/21 剝除、hold-release 對真 Codex 正常 | merged（文件） | #5810 |
| S6（另一半） | chat／messages 串流 output rail（#1508，ADR-318 Amendment C）：buffer 模式跑真檢查可擋（R-A／graceful／transient）、stream 模式事後 observe-only | merged，未部署 | #5811 |
| 並行 | prod 部署 #5257、#5681（Codex 用量扣 Budget） | rel 有、prod 沒有 | ops 決定 |

## S2 登記的缺口（8 個：6 個已修、2 個未修）

| Issue | 面 | 缺口 | 狀態 |
|---|---|---|---|
| #5754 | Responses | 不看 `streaming_allowed=false` | 已修（#5796，未部署） |
| #5755 | Responses | 定址被拒不寫稽核 | 已修（#5776，未部署） |
| #4248 | Responses | `llm_judge_routing` 直接退回 heuristic | 已修（#5804，未部署） |
| #5751 | Responses | 沒有 provider 卡住時的 idle deadline | 已修（#5795，未部署） |
| #5753 | Responses | 沒有回應端 Tool 規則 | 已修（#5806，未部署） |
| #1508 | chat／messages | 串流的 output rail 是 no-op | 已修（#5811，未部署） |
| #4247 | Responses | 沒有 semantic cache | **未修**：設計延後（ADR-437 D3） |
| #1060 | Responses | 邊界檢查仍是 shadow | **未修**：等營運切換 |

## 已修、issue 仍開（依 10-03 決定 6：部署驗證完才關）

- #5669（S1）
- #5670、#4876、#5752（S3）
- #5755（#5776）
- #3822、#4558（#5780）
- #5754（#5796）
- #5751（#5795）
- #4248（#5804）
- #5753（#5806）
- #1508（#5811）

例外：#4854 在 S1 merge 時已被 PR 內文的 "closes #4854" 自動關閉（10-03 04:45Z，早於決定 6）。

第二輪（commit 一律用 `Refs`，不會自動關）：#5829–#5837、#5671、#5852–#5854、#5861–#5864，共 17 張。

## 以後可以做

1. **部署**：S1–S6、第二輪 W1–W16 與 Audit #197 上 rel，驗證後關掉上面兩輪共 29 張 issue；prod 另外補 #5257、#5681。驗證腳本：`~/Desktop/testing/responses_gap_probe.py`、`agent_block_probe.py`。
2. **#1060**：Responses 執行邊界從 shadow 改成 enforce。
3. **#4247**：Responses 的 semantic cache。
4. **#5222、#5458**：stage 順序造成的浪費，例如被擋的請求仍付判級費、限流排在判官之後。兩個面都有，改了是行為變更。
5. **#5668**：ADR-455 bridge 在 incomplete／failed 時丟掉已累積的工具呼叫。
6. **#4878**：R3 換模型時可能重送加密 reasoning（S3 已做保守版：只換同憑證的模型）。
7. **Agent policy v1.1 其餘功能**：session 上限、deny 當成工具錯誤（C-304-330..389）。A22 要用會吐出被拿掉工具名稱的模型才能真機驗。
8. **計價**：`service_tier`、`prompt_cache_options` 計價支援後改成轉送。
9. **#1508 做的時候發現、沒改的**：
   - 非串流 chat 的 graceful output 擋下回 `200`，但 body 是 SPEC-213 refusal 欄位，不是 `chat.completion`；`/v1/messages` 因此變成空文字＋`end_turn`。只影響有寫 `graceful` 的 policy。
   - chat agent mode（`show_planning`）沒有任何 output rail（串流與非串流都沒有）。
   - 串流 `/v1/messages` 的 `length` 仍對映成 `end_turn`（#5811 刻意只改 `content_filter`；#5858 也沒動）。
   - T-4 的 agent mode 那一半：#5805 修好 Foundry worker 後前提已成立。
10. **第二輪途中發現、還沒開 issue 的**（H1–H8，見工作清單 §G）：非串流工具呼叫回合丟 `reasoning_content`；o1 這類不串流模型遇到工具呼叫會丟文字；`/v1/messages` 一些非字串欄位原樣送給 provider；Claude Code 被擋時多送一次請求等。
11. **非目標（草案 §5）**：模型身分與跨面轉譯——#2783、#3822、#2551、#5528、#5525、#3677、#4405。

## 需要 Peter 的事

0. **第二輪**：#5870 綠了就 merge（已授權）。H1–H8 要不要開 issue，見工作清單 §G。
1. **部署**：見「以後可以做」第 1 項。
2. **要不要開 issue**：「以後可以做」第 9、10 項。
3. **本機設定（依你 10-04 的要求保留中）**：`gpt_4o_816e-proxy`（`841deb51-…`）原本的 model sources 依序是 gpt-5.5（`ff52614c-…`）、deepseek-flash（`baad099f-…`）、gpt-5.6-luna（`95d1d2b0-…`）、gpt-5.4（`dca422fb-…`）；10-04 加入 gpt-4o-mini（`a35d8d31-…`）、gpt-4.1-nano（`ea37630c-…`），排在第 5、6。要還原就 pause 或移除這兩顆。沒有建 credential；A22 建的 Tool 規則已全部刪除。
4. **輪替**：對話中貼過的 key，包括 10-05 貼的 tenant admin key 與 KEY2。
5. **10-05 實測留下的東西**：測試模型 `2354833d`（openai_responses、`gpt-5.4-resp-probe-*`、served `gpt-5.4`）在 `gpt_4o_816e-proxy` 上是 paused；因為還掛在 proxy 上，刪除會回 409，所以模型本身留著。實測用的 guardrail 綁定與 policy 已全部 deactivate。

## 已做的決定（依授權）

- SPEC-308 D-4：具名參數，Responses 不做 ADR-lite-032，行為不變。
- #4248 選 B：判官＝本面候選集尾，經 Responses API 呼叫。A（改用 chat 面模型）會繞過 conversation scope 的過濾。
- Responses 上的 policy 403 改 400：Codex 0.154 只在 400／429 停手，403 會重試 5 次。
- P3 的四個差異都做：T-2、T-3、T-4、T-5。
- #1508 兩半都做：核准改寫 ADR-318 INV-318-7（刪掉「C3 buffer hook 等 shadow data」）。
- A22 只在 `gpt_4o_816e` 建一條 enforce 規則，測完刪除。建立後已刪：policy `107cc0a4-…`、version `bad7fb15-…`、bundle `0235022b-…`、item `b36b2e00-…`、binding `915e9bdb-…`；effective policy 已回 `null`／`platform_default`。
- **2026-10-05 第二輪（Peter 授權：全部修、CI 綠就 merge、有決策才問）**：
  - C1：Responses 定址拒絕只改 404／422 為 400，denylist／`ExecutionRefused` 的 403 不動。
  - C2：送 DeepSeek 前替缺的 assistant 回合補 `reasoning_content: ""`（實測補了才會過）。
  - C3：output rail 扣住整輪工具呼叫，工具參數也一起送檢。
  - C-304-310（SPEC-304 Rev.13）：output rail 擋下時整輪丟掉，Tool 規則不再判定，graceful 與 error 呈現一致。
  - C-304-152（SPEC-304 Rev.14，選項 A）：buffer 模式文字已通過檢查、但工具被 Tool 規則擋下時，先送文字再接 R-A，同 stream 模式與 Responses。
  - #5671：非字串的 tool `type`（含數字、布林、`null`）改回 400，以前是剝除後 200。
  - #5853：格式錯誤的 400 不寫稽核，與同一面其他驗證失敗一致。
  - #5863：`budget_tokens` 不論 `thinking.type` 都檢查，必須是整數。
