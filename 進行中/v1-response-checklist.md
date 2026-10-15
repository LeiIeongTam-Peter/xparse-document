# `/v1/responses` 第二輪：工作清單（2026-10-05 起）

> **用途**：讓任何時候都看得出第二輪做到哪裡。每完成一格就勾掉，並在「證據」欄寫 PR 編號、commit 或 request_id。
> **來源**：`docs/進行中/v1-response.md` 的「2026-10-05 複查」（缺口 I1–I9）；評審 `docs/草案/解決-v1-response-評審.md` §8。
> **實測證據**：`~/Desktop/testing/results/responses_gap_probe/REPORT-2026-10-05.md`。
> **重跑實測**：在 `~/Desktop/testing` 執行 `uv run --no-project python responses_gap_probe.py <phase>`，phase 可選 `cost`、`schema`、`routing`、`guardrail`；三家 client 被擋的情境用 `agent_block_probe.py`。
> **狀態記號**：⬜ 未開始 · 🔄 進行中 · ✅ 完成 · ⏸ 等決定 · ➖ 不適用

## 0. 現在在哪裡

- **目前階段**：B 收尾：程式面只剩 W13 #5870（CI 中）；其餘 16 個 PR 已 merge，全部未部署
- **下一步**：#5870 綠 → merge；之後部署到 rel（需 Peter 授權）→ 重跑 `responses_gap_probe.py` 與 `agent_block_probe.py`（§B 第 8 步）→ 關 §D 列出的 issue
- **卡住的事**：無（C1、C2 已決定）。Peter 10-05 授權：全部修、CI 綠就 merge，有決策才問

## A. 開 issue（`/doc-issue`；每張都要上敏捷看板 #6，六個欄位都要讀回確認）

| # | 缺口 | issue | 看板 #6 | 狀態 |
|---|---|---|---|---|
| A1 | I1 buffer 模式在 `incomplete`／`failed` 時放行沒檢查的全文 | #5829 | ✅ | ✅ |
| A2 | I2 buffer 模式不扣、不掃 tool call | #5830 | ✅ | ✅ |
| A3 | I3 chat 串流 buffer：有 tool call 的那輪跳過扣住檢查 | #5831 | ✅ | ✅ |
| A4 | I4 Responses 的 input 估算只讀 user 文字 | #5832 | ✅ | ✅ |
| A5 | I5 Responses 串流中途失敗／reaped 時 prompt 記 0 | #5833 | ✅ | ✅ |
| A6 | I6 失敗嘗試記帳丟掉 cached tokens | #5834 | ✅ | ✅ |
| A7 | I7 開串流前 404／422／部分 403 讓 Codex 重試 | #5835 | ✅ | ✅ |
| A8 | I8 session 中途換到 DeepSeek thinking 會 400 | #5836 | ✅ | ✅ |
| A9 | I9 Responses 的 TTFT 量的是 `response.created` | #5837 | ✅ | ✅ |
| A10 | #4878 補充：第一次選模型和 tier 升級沒有加密 reasoning 的憑證守門 | 已留言 #4878 | ➖ | ✅ |

## B. 修補切片（依序；每片獨立 worktree、獨立 PR，base 一律是 `main`）

每片都要走完同一組步驟。勾完才算這片完成：

1. 設計閉環：amend 對應的 ADR／SPEC，並附 Core 對比表（§17.4）
2. 先寫測試：integration test 跑**真元件**，並附「真元件確會產生 trigger」的證據（§8.1）
3. 實作
4. conformance 補上新的 fake provider 形狀：`incomplete`、`failed`、文字和 tool call 混在同一輪（評審 §8.2 第 2 點）
5. 本機跑過命中的 static gates（§17.2 #7）
6. PR 內文附 ADR-093 表、Core 對比表、`Acceptance-Impact:` 行
7. CI 綠、merge
8. 部署到 rel 後，用 `responses_gap_probe.py` 重跑對應的 phase，結果寫進「證據」欄

| 片 | 範圍 | 對應缺口 | 設計文件 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 證據 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **W1** ✅ | Responses buffer output rail：terminal 一律等裁決（`completed`／`incomplete`／`failed`）；整輪的 tool-call frame 扣到裁決後才放出；tool 參數也送進 rail | I1 #5829、I2 #5830 | ADR-437 amendment、SPEC-282 RSP-OUT | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⬜ | **PR #5838 merged `3ce532cdb`**（branch `fix/responses-buffer-rail-terminals-tool-calls`）；完整 gateway suite 8,545 passed；static gates 119/120（1 跳過 setup）；dogfood：舊 rail 三支 conformance Responses 測試紅、新 rail 綠 |
| **W2** ✅ | chat 串流 buffer：`tool_calls` 這個 terminal 分支先跑 held check；擋下時不送 tool call，並用 R-A 或 graceful 呈現，不再默默拿掉文字 | I3 #5831 | ADR-318 Amendment D、SPEC-217、SPEC-304 Rev.14 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⬜ | **PR #5847 merged `8c644767e`**；ADR-318 Amendment D、SPEC-217 C-217-21、SPEC-304 Rev.14（C-304-152：已通過檢查的文字先送、再 R-A）；full suite 8,582 passed；dogfood 25 支紅→綠 |
| **W3** ✅ | Responses 的 prompt 估算納入 `instructions` 與所有 input item（含 `function_call_output`）；串流中途失敗和 reaped 時用這個估算記 prompt，並標 estimated | I4 #5832、I5 #5833 | SPEC-282 Rev.28、SPEC-284 補註 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⬜ | **PR #5844 merged `37448fff0`**；SPEC-282 Rev.28（TC-282-43/44）；probe body 估算 8,680／實際 9,829（−11.7%）；full suite 8,597 passed；dogfood 17 支紅→綠 |
| **W4** ✅ | 失敗嘗試記帳帶 cached／cache-write tokens（三個面） | I6 #5834 | SPEC-302 Rev.11（C-302-86）；ADR-439 §12.2 更正註記 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⬜ | **PR #5842 merged `291283408`**；三個面；full suite 8,555 passed；dogfood 9 支紅→綠。殘留：串流 chat 在 usage chunk 之後才失敗時仍記 0 cache（罕見） |
| **W5** ✅ | Responses 開串流前的拒絕改成 Codex 不重試的狀態碼 | I7 #5835 | ADR-437 Amendment E、SPEC-282 Rev.29 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⬜ | **PR #5841 merged `10df46c18`**；ADR-437 Amendment E（INV-437-20）、SPEC-282 Rev.29（RSP-ADDR-1、TC-282-42）；dogfood 6 支紅→綠 |
| **W6** ✅ | 跨模型 history 相容：換到 DeepSeek thinking 時，處理前面缺 `reasoning_content` 的 assistant 回合 | I8 #5836 | ADR-208 Amendment 9、SPEC-174 Rev.2 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⬜ | **PR #5839 merged `aaa2f7092`**（未部署）；full suite 8,536 passed；dogfood 4 案例紅→綠；provider 以 `deepseek` 判斷（`openai`／`vllm` 註冊、指向 DeepSeek endpoint 的列不在範圍，ADR-208 A9.5 已知限制） |
| **W7** ✅ | Responses 的 TTFT 改記第一個輸出事件 | I9 #5837 | SPEC-276 Rev.19、SPEC-282 Rev.30 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⬜ | **PR #5840 merged `c963332a2`**；SPEC-276 Rev.19、SPEC-282 Rev.30；full suite 8,534 passed；dogfood 7 支紅→綠；§8.1 真 `AzureResponsesWorker` probe |
| **W9** ✅ | `tools[i].type`／`input[i].type` 非字串 → 400（step 1.05，`invalid_type`，記 `audit.policy.violation`），不再 500 | #5671 | SPEC-307 Rev.1（RF-12） | ✅ | ✅ | ✅ | ➖ | ✅ | ✅ | ✅ | ⬜ | **PR #5843 merged `0b998e102`**（CI 一次 complexity routing 計時 flake，重跑綠）；full suite 8,573 passed；dogfood 26 支紅→綠。行為變更：數字／布林／null 的 tool type 由「剝除後 200」改 400 |
| **W8** ✅ | 收尾：修正過期的 docstring（`responses_output_checks.py:62-66`、`routes/responses.py:37-48`、`responses_admission.py:187`、`responses_routing.py:84`、`tier_judge_handler.py:97-102`） | — | ➖ | ➖ | ➖ | ⬜ | ✅ | ⬜ | ✅ | ✅ | ➖ | **PR #5850 merged `30d4db180`**；只改 docstring：5 個檔，gates 0 失敗 |

## C. 等 Peter 決定

| # | 問題 | 選項 | 決定 |
|---|---|---|---|
| C1 | W5：404／422 改 400 會改變對所有 client 的 API 契約，不只 Codex | (a) 只在 Responses 面改，比照 #5801；(b) 不改，接受 Codex 重試；(c) 依 User-Agent 分支（評審 §3.3 不建議） | ✅ (a)：只改 404／422 為 400，code／message 不變；denylist／ExecutionRefused 的 403 不動（Peter 10-05） |
| C2 | W6：DeepSeek 缺 `reasoning_content` 時怎麼處理 | (a) 前面回合補空的 `reasoning_content`（要先實測 DeepSeek 收不收）；(b) 對 DeepSeek 關 thinking；(c) 只靠開 session affinity，文件寫清楚 | ✅ (a)：送 DeepSeek 前替缺的 assistant 回合補 `""`。實測：重放失敗請求 400、全部拿掉仍 400、補空字串 200（Peter 10-05） |
| C3 | W1：tool 參數要不要進 output rail | (a) 進，跟文字一起判；(b) 不進，但整輪扣到裁決，擋下就不放 tool call | ✅ 兩個都做（Peter 10-05） |

## D. 第一輪留下、仍待處理（沿用 `v1-response.md`）

- [ ] S1–S6 與 Audit #197 上 rel，驗證後關第一輪 12 張 issue（清單見 `v1-response.md`）
- [ ] 第二輪上 rel，驗證後關：#5829–#5837、#5671、#5852–#5854、#5861–#5864（共 17 張；commit 都用 `Refs`，不會自動關）
- [ ] prod 補 #5257、#5681
- [ ] #1060 Responses 執行邊界從 shadow 改成 enforce（營運決定）
- [ ] #4247 Responses semantic cache（設計延後）
- [x] #5671 → W9（PR #5843）

## F. 這輪修補途中新發現（都已開 issue，Peter 10-05 核准）

| # | 缺口 | 證據 | 狀態 |
|---|---|---|---|
| F1 #5852 → W10 | 非串流 chat／messages 的 output 檢查只看 `message.content`，不看工具參數；純工具呼叫的回合等於沒檢查 | `non_streaming_handler.py:1027`、`:1031`、`:1038`、`:1083`（W2 回報） | ✅ PR #5859 merged `669e2e497` |
| F2 #5853 → W11 | `/v1/messages` 的 tool `type` 是 list／dict／數字時，`anthropic_translation._tools_to_openai` 在 `ttype.startswith` 拋 `AttributeError` → 500 | W9 回報 | ✅ PR #5860 merged `20b572a8b`（不寫稽核，Peter） |
| F3 #5854 → W12 | stream 模式（非 buffer）chat 的工具呼叫回合，done chunk 仍是 `finish_reason="stop"` | W2 回報 | ✅ PR #5858 merged `db2c4e111` |
| G1 #5861 → W13 | 非串流 chat 先寫 semantic cache、後跑 output rail：被擋的回答被快取，下一個相似請求繞過檢查拿到（P1） | `non_streaming_handler.py:998-1005` vs `:1036`／`:1080`；`dispatch_stages.py:331-356` | 🔄 PR #5870（CI 中）；ADR-054 Amendment A（INV-054-5）；dogfood 8 支紅→綠 |
| G2 #5862 → W14 | 非串流「文字＋工具呼叫」的回合，文字被 `from_tool_calls` 丟掉 | `models/response_models.py:150` | ✅ PR #5867 merged `fda4e52f3` |
| G3 #5863 → W15 | `/v1/messages` image `source` 非物件、`thinking.budget_tokens` 非數字 → 500 | `anthropic_translation.py:95`、`:344-345` | ✅ PR #5869 merged `e421628a9`；另修 block `text` 非字串的 500 |
| G4 #5864 → W16 | TC-264-42 絕對計時門檻在 CI 上 flake | `test_spec264_complexity_routing.py:1407` | ✅ PR #5868 merged `e9d458aed` |

## G. 尚未開 issue、待 Peter 決定

| # | 問題 | 來源 | 建議 |
|---|---|---|---|
| H1 | 非串流的工具呼叫回合，`reasoning_content` 被丟掉（`from_tool_calls` 沒有 reasoning 參數） | W14 | 開 issue 修（ADR-056 要求轉送） |
| H2 | `supports_streaming=False` 的模型（目前 o1）在 `_post_once` 遇到工具呼叫時，直接丟掉文字與 reasoning；串流與非串流的 client 都受影響 | W14 | 開 issue 修 |
| H3 | 純工具呼叫的 chat 回合沒有 `content` 欄位（OpenAI 回 `content: null`） | W14 | 影響小，可不理 |
| H4 | `/v1/messages` 有些非字串欄位（`source.type`／`media_type`／`data`、`tool_use.name`／`id`、`tools[i].name`／`input_schema`、`tool_choice.*`、`thinking.type`）不會 500，但會原樣送給 provider 或當成未設定 | W15 | 可另開 issue 統一做形狀檢查 |
| H5 | 串流 chat 在 provider 送出 usage chunk 之後、正常結束之前失敗時，cache 數仍記 0 | W4 | 罕見，先記錄 |
| H6 | Claude Code 被擋時，串流內錯誤之後會重送一次，一次擋下等於兩次請求 | 10-05 實測 | 觀察中 |
| H7 | 以 `openai`／`vllm` 註冊、但 endpoint 指向 DeepSeek 的模型，不在 #5836 的修補範圍（只認 provider=`deepseek`） | W6 | 改用 `deepseek` provider 重新註冊即可 |
| H8 | semantic cache 命中時，回應固定 `finish_reason="stop"`、只回文字 | W13 | 既有行為，先記錄 |

## E. 變更紀錄

- 2026-10-05：建立。
- 2026-10-05：文件複查：W3、W8 列補 merged；§D 補第二輪要關的 17 張 issue；新增 §G（尚未開 issue 的 H1–H8）。
- 2026-10-05：W16 #5868、W14 #5867、W10 #5859、W15 #5869 merged（W10／W15 的 CI 紅是 TC-264-42 flake；rebase 到含 #5868 的 main 後綠）；W13 開 PR #5870。
- 2026-10-05：W11 #5860、W12 #5858 merged；W14 #5867、W16 #5868、W15 #5869 開 PR；W13 等 #5859。
- 2026-10-05：W3 #5844、W8 #5850 merged；開 #5852–#5854（W10–W12，PR #5859／#5860／#5858）與 #5861–#5864（W13–W16）。W11 決定：格式錯誤的 400 不寫稽核（Peter）。
- 2026-10-05：W7 #5840、W4 #5842、W5 #5841、W9 #5843、W2 #5847 merged；W3 #5844、W8 #5850 CI 中。
- 2026-10-05：W6 #5839 merged（`aaa2f7092`）；W7 #5840、W5 #5841 開 PR；W2 設計選擇定 A（buffer 模式文字通過 rail、Tool 規則擋工具時：先送已檢查文字、再 R-A，同 stream 模式與 Responses；改 SPEC-304 C-304-152）。
- 2026-10-05：W1 #5838 merged（`3ce532cdb`，CI：gateway suite 6m34s 綠）；未部署。W2–W7、W9（#5671）開工。
- 2026-10-05：W1 設計閉環（ADR-437 Amendment D、SPEC-282 Rev.27、SPEC-304 Rev.13 改 C-304-310）、測試、實作完成；conformance 補 `text_and_tool_call`／`incomplete` 兩種 provider 形狀，chat／messages 的工具呼叫缺口以 #5831 strict xfail 登記。
- 2026-10-05：A 完成。#5829–#5837 已開，都上了敏捷看板 #6（Triaged／Bug／S9，指派 Peter）；#4878 已留言。C3 決定兩個都做；W1 開工。
