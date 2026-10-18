# vLLM prefix cache（前情共用）：已完成的工作與待修清單

- **狀態日期**：2026-10-18
- **基準**：`futurenestit/xparse` origin/main `cd1b1e84b`（§1–§8 原文以 2026-10-17 的 `e329c51c2` 為準）
- **讀者**：接手修理剩餘問題的 agent／工程師
- **一句話**：
  - 快取在 main 上已經修好，本機實測重用率約 99%。
  - 13 張 issue 修好 12 張；W11（聊天機器人打 Claude 自動快取）已 merge，並在本機驗過。
  - 範圍外的發現也處理了一批，見 §0a。
  - **這些都還沒部署到 rel 和 prod**；本機 stack 也還跑在 `8133bb33e`，所以本機看不到今天 merge 的修正。

---

## 0a. 2026-10-18 狀態更新（先讀）

- 13 張 issue 已修好 12 張並 merge 到 `main`。#6725 只剩「全新預設安裝」那一項驗收，Peter 決定留到下一次真的安裝，所以 issue 還開著。
- W11（聊天機器人打 Claude 拿不到快取）的定性已由 owner 推翻，改為預設自動快取。文件、IAM、gateway、Console 四片都已 merge，2026-10-18 本機端到端通過；剩 rel 驗收與發佈。
- 看板 #6 的卡在 issue 關閉時已自動移到 Done。

**還沒做完的事**（2026-10-18 晚）

1. **部署**（要 Peter 授權）：先 rel 再 prod；IAM 先上，gateway 與 Console 後上。這批要一起帶上哪些變更、有什麼要注意，見下方「部署要多注意的」。
2. **rel 驗收**：快取的 E2E（§4 W2），以及 W11 的 SPEC-331 CT-331-19。通過後的發佈 PR 刪掉 ADR-473 entry `prefix_cache_sharing_scope`（W3）與 `auto_prompt_cache`，兩端 call site 一起刪。
3. **#6725**：下一次全新預設安裝時，照 runbook 跑三個 CLI。
4. **手冊**：Xparse-Manual#45、#46 等 maintainer 審核，合併後推進產品端的 gitlink。見下方「手冊」。
5. **開著的 issue**：
   - 本批：#6774、#6775；
   - 第二輪 agent 實測開出的：#6785–#6788、#6790–#6794。
6. **範圍外發現還沒開 issue 的**：第 6–8、10–15 項。
7. **#3 還有一點沒驗證**：GPT-5.6 以前的 OpenAI 模型，冷請求會不會回報寫入數。它決定新的計價規則會影響多少既有的價格段；要驗證，需要一把能打這些模型的 key。
8. **已部署環境的自簽憑證要重簽**（#6724，`agent-cli-setup.md` §0）。本機 ingress 的憑證也還是 `CA:TRUE`，Codex 仍無法直連 `https://localhost:3000`。

**13 張 issue**

| Issue | PR | merge commit | 重點 |
|---|---|---|---|
| #6724 | #6747 | `3f6343535` | 四個產生器改成 `CA:FALSE`＋`serverAuth`，**不帶 keyUsage**：帶了之後 OpenCode 與 LibreSSL client 會失敗（實測）。經臨時的第二個 ingress 實測 Codex 可完成 `/v1/responses` |
| #6725 | #6749 | `65496a8d2` | runbook 已寫；**issue 仍開**，等全新預設安裝照 runbook 跑三個 CLI |
| #6726 | #6738 | `8eba058ee` | 「本輪」改為最後一則 assistant 之後的訊息。switch on 的驗收由協調者翻 gemma 開關實測（`f6726-switch-on-1792247289`：`tool_result_turn=True rotation=on applied=True`），測完改回 `false` |
| #6727 | #6742 | `f1c6e410a` | 只在 `/v1/messages`、`context_overflow` 時改用 Anthropic 措辭。input 估算用 `estimate_for_client`（含 assistant 工具呼叫）；Peter 若要改回治理估算，改一行即可 |
| #6728 | #6749 | `65496a8d2` | 重跑通過：Claude Code 2.1.302、60k gemma、31903 token、exit 0（`eee8d88a-bae4-49f3-a8c1-fcd654195b12`） |
| #6729 | #6737 | `d3e49c3a5` | SPEC-308 §9.15 |
| #6730 | #6745 | `049360613` | Peter 選 (a)：沒帶 `stream`、`false` 或 `null` 回非串流 JSON；`stream` 不是布林值回 400 `invalid_type`（SPEC-307 RF-21） |
| #6731 | #6743 | `aa31dbe47` | billing 區塊在 OpenAI 自家 wire 也在 egress 剝除；ADR-055 Rev.5 |
| #6732 | #6752 | `44dc4b759` | `/v1/messages` 回 `output_tokens_details.thinking_tokens` |
| #6733 | #6739 | `3595a9b56` | 只改對外的 count_tokens；治理估算逐位元不變 |
| #6734 | #6740 | `15c6c9b53` | DeepSeek 的推理封進 `xpenv1`（新 block kind `reasoning_text`），同 provider、同 credential、帶 `include` 才還原 |
| #6735 | #6741 | `1a3fd2480` | `finish_reason` 只在 done chunk 送一次，`xparse` 也放在 done chunk。沒用 `choices: []`，因為 OpenAI SDK README 的串流迴圈會 `IndexError` |
| #6736 | #6746 | `be75f541b` | BuStream 欄位搬到 `xparse`，EVENT_STREAM_SPEC 升 2.0。**對自己讀 `chunk["metadata"]` 的客戶整合是 breaking change**，發佈時要通知 BD／客戶 |

**2026-10-18 本機回歸（更新後的本機 stack，main `8133bb33e`）**：報告在 `/Users/peter/Desktop/testing/agent-e2e-regression-2026-10-18/REPORT.md`。

- 三個 CLI × 四模型 × 兩次標準任務，24 次全部 exit 0，133 個請求、0 個失敗。
- 雲端模型 9 組的測試全部通過。gemma 的失敗當時歸為模型能力，與 10-17 相同。**（2026-10-18 更正：判斷錯了。後來的 agent 實測找到根因：vLLM 0.24.0 的 gemma4 reasoning parser 在串流模式下，把沒有 thinking 標記的回答整段歸成 reasoning；gateway 對上游一律串流，所以工具輪次之後的回答消失。見 #6788。）**
- #6726：Claude Code × gemma 的 tool 輪次判為 `true`，fingerprint 不變，第 2 輪之後重用約 99%。
- #6734：Codex × deepseek 沒有任何 reasoning 被丟掉。
- W11 端到端通過：聊天機器人打 Claude，第 2 輪起約 99%；應用關閉時不加任何標記，記為 `app_off`。

**W11（ADR-382 Amendment D、PRD-362、SPEC-331）**

- 決定（Peter，2026-10-17）：預設自動、虧了會停，既有應用一併適用。
- 範圍：OpenAI 協定入口（chat、Responses）打 Anthropic 直連的 Claude，client 沒標記時：
  - system 前綴一律標；
  - 多輪才加 top-level 自動快取；
  - 應用可關；
  - 讀寫 token 比低於 0.28 時暫停 60 分鐘。
- 實測依據：不帶標記的聊天機器人打 Claude 每輪都是 0；只多帶 `prompt_cache_key` 就約 99%，5 輪輸入 −67%。證據在 `/Users/peter/Desktop/testing/claude-chatbot-cache/`。

| 片 | PR | 狀態 |
|---|---|---|
| 文件：RESEARCH、PRD-362、ADR-382 Amendment D、SPEC-331，連動 PRD-299／ADR-300／SPEC-312 | #6744 `af9f6697b` | merged |
| S1 IAM：`Application.auto_prompt_cache_enabled`（migration 0395 → 0393）、ADR-473 `auto_prompt_cache`（stage=rel）、投影生效值 | #6748 `c94528aaf` | merged |
| S2 gateway：決策、紀錄、breaker（`gateway/auto_prompt_cache/`） | #6750 `c0bf18561` | merged；live（第二個 gateway＋只設 `peter` 的測試 shim）：5 輪 chat 第 2–5 輪 99.0–99.5%、輸入 −66.7%；Responses 5 輪 98.9–99.4%；system 每次不同時第 20 個請求跳閘、之後不帶標記。跳閘紀錄是 5 個平鋪的 `prompt_cache_auto_breaker*` key（稽核只收純量 extra），SPEC-331 CT-331-13 已勘誤（#6770 `f5183bd3e`） |
| S3 Console：開關（中文標籤依 glossary 寫成「自動 Prompt Caching（Claude）」） | #6751 `37afc34e6` | merged；手冊頁由 Xparse-Manual#45 落地（含 #44），等 maintainer |

**部署（W1）要多注意的**

- **順序**：IAM 先、gateway 後（#6726、W11、#6779 都依賴）。migration 0392、0393、0395 都只新增欄位。
- **這批要帶上的**：快取（§2）、13 張 issue 的修正、W11、#6776、#6777、#6779、#6797。
- **#6779（快取寫入計價改成 B2）**：
  - IAM 一定要先上。gateway 先上的話，chat 開始記寫入數，舊 IAM 會把沒寫寫入價的價格段算成 0。
  - IAM 在查詢時才計價，所以過去的用量會照新規則重算：2026-10-01 起，`/v1/responses` 打 OpenAI／Azure、而價格段沒寫寫入價的那些用量，會從 0 改成 input 價。
  - 這些 tenant 本期的 Budget 用量會跳升；接近上限的 tenant，下一個請求可能被擋（400 `cost_budget_exhausted`）。
  - 部署前在各環境跑 `inventory_pricing_schema`，看 `cache_write_unstated_vs_reference`，就知道影響多大。本機是 0。
  - 回退就是版本回退：沒有 migration，也不改資料。
  - Audit 計價引擎的同步改動是 Xparse-Audit#206（已 merge），gitlink 由 #6779 推進。
- **#6736 是 breaking change**：chat 串流的 BuStream 欄位搬到 `xparse` 底下。自己讀 `chunk["metadata"]` 的客戶整合會受影響，發佈時要通知 BD 與客戶。
- **#6695／#6699**（不在這批）：原本的 `0394` 與 main 上的 `0395 → 0393` 會形成兩個 leaf。2026-10-18 確認作者已改成 `0396 → 0395`，不再撞號；兩個 PR 仍開著。
- **W11**：要在 rel 跑 SPEC-331 CT-331-19 的端到端驗收；通過後的發佈 PR 刪掉 ADR-473 entry `auto_prompt_cache`，兩端 call site 一起刪。
- **憑證**：已部署環境的自簽憑證仍是 `CA:TRUE`，Codex 連不上，要照 `agent-cli-setup.md` §0 重新簽發。

**本文件的修正**（§3 原本的做法有漏洞，以下為準）

- §3.1 的 `grep CacheSaltGenerator` 在 `docker logs` 裡看不到，不能用來確認 salt 有開。改看 `cache_salt_decision` 有沒有 fingerprint。
- §3.2 的 `docker run` 少了下列 mount 或設定：
  - `-v <scratch>/audit:/app/var/audit`：不加，稽核事件不會落盤。不要 mount 主 checkout 的 `var/audit`。
  - 主 checkout 的 `apps/guardrails/xparse_guardrail` → `/app/xparse_guardrail:ro`。
  - 主 checkout 的 `install_service/configs/model_profiles.yaml` → `/app/configs/model_profiles.yaml:ro`（live gateway 掛的就是這一份）。
  - live gateway 的 `XPARSE_TRANSLATION_ENVELOPE_SECRET` 是空的，金鑰在 `xparse_xparse-routing-db` volume 上，所以第二個 gateway 的翻譯信封是**關的**。依賴信封的驗證要傳一把一次性金鑰（格式見 `docs/runbooks/translation-envelope-secret.md`），不要 mount 那個 volume。
  - image 內建的 healthcheck 打 8443，所以會顯示 unhealthy；`/health` 回 200 就可以用。
- perf 的 `decisions.py` 與 `probe_gateway_multiturn.py::salt_decisions` 還讀 Rev.1 的欄位（`cache_salt_mode`、`tool_call_guard_applied`），遇到現在的事件會出錯。
- 共用的 scratchpad 被多個 agent 同時寫過，各組要用自己的子目錄。

**範圍外的新發現**（第 1–5、9 項已於 2026-10-18 處理，見清單後的表；其餘還沒開 issue，要開請走 `/doc-issue`）

1. 直連 gateway 時，Codex 正常完成（`finish=stop`）的請求常被記成 `client_closed`／`mid_stream`，main 上也一樣（4 個請求中 3 個）。
2. SPEC-223 C-223-49「tool-shaped 結尾就跳過 input classifier」也只看 `messages[-1]`：Claude Code 的 system 提醒可能讓每個 tool 輪次多跑一次 judge（未驗證）。
3. OpenAI 文件說 GPT-5.6 以上寫入收 1.25×，但 gpt-6-luna 的回應與稽核都沒有 cache write，可能少計。
4. AWS 文件說 Bedrock 上的 Claude 有 implicit caching（best effort），與「沒標記就不快取」的假設衝突，待真 Bedrock 實測。
5. `cache_control_missing` 只看 `/v1/messages`，聊天機器人的情況在 Console 永遠是 0。
6. 程式註解把快取決策寫成 ADR-372（實為 ADR-382）；`production/prefix_affinity.py` 的最短快取長度表過時（改它會動 session affinity 的行為）。
7. Xparse 工具迴圈的結束說明在串流裡沒有 `finish_reason`（SPEC-314 C-314-53／54）。
8. 非串流 `X-BuStream-Debug: true` 回的 `metadata` 物件同樣會撞 `ChatCompletion.metadata`。
9. `xparse_doctor.py:283` 的修復提示寫 `xparse restart ingress`，compose 服務名稱是 `xparse-ingress`。
10. CLAUDE.md §17.2 #7 只叫人跑 `.github/scripts/*.sh`，但 `ci.yml` 還跑約 80 支 `.py` gate（surface-conformance-gate 就因此本地沒抓到）。
11. `test_gateway_iam_http_cutover` 偶發 flake（IAM fixture 逾時或 500，rerun 即綠）。
12. 只在本地失敗、不在 CI suite 的舊測試：`tests/test_spec171_served_name.py`、`tests/contract/test_spec196_governed_claude_code.py`、`test_issue711…::test_delete_route_is_registered_without_trailing_slash`。
13. Console：稽核員頁面上「模型限制與路由」卡的其他開關仍可點（沒有儲存鈕）。
14. IAM：LLM Proxy 列可以存 `auto_prompt_cache_enabled`，但不生效（只讀 consumer）；可比照 ADR-267 Amendment A 拒絕寫入。
15. §5.2 原本已列的照舊：`/v1/messages` → DeepSeek 丟 `thinking` block；chat 串流每個 chunk 帶 `delta.role`；tool-call 回合 `xparse.empty_output=true`。

**2026-10-18 處理結果**（編號同上面清單）

| # | 結果 | 位置 |
|---|---|---|
| 1 | **已修並 merge**（`6c41836fb`）。<br>原因：Codex 讀到 `response.completed` 就關連線，gateway 還在等 provider 的串流結束而被取消。<br>後果不只是標籤錯：健康成功、routing actuals、Content Vault capture 都沒記；provider 的 `response.failed` 也記不成 FAILED。<br>修正：終端 frame 交給 transport 之後的取消記 `completed`，並照串流讀完的方式結算。<br>真 Codex × gpt-6-luna 直連 A/B：main 4 次中 3 次記錯，修正後 0 次 | [#6777](https://github.com/futurenestit/xparse/pull/6777)；SPEC-064 §6.4、SPEC-282 Rev.37；實測 `testing/responses-close-after-terminal-probe/` |
| 2 | **已修並 merge**（`0b0d53702`）。<br>現行 Claude Code 2.1.302 的每個請求都以 `system` 訊息結尾，所以 C-223-49 的跳過從未對它生效。<br>修正：結尾改為最後一則不是 `system`／`developer` 的訊息。<br>真 `/v1/messages` 路由上，judge 次數 `[1,1,1]` → `[1,0,0]` | [#6776](https://github.com/futurenestit/xparse/pull/6776)；SPEC-223 C-223-49 Rev.、ADR-318 INV-318-12；實測 `testing/classifier-tool-tail-probe/` |
| 3 | **已決定並 merge**（`d2199f252`）。<br>原因：OpenAI chat wire 有回報寫入數（`prompt_tokens_details.cache_write_tokens`），但 gateway 不讀，寫入以 input 價計。這是 SPEC-302 Rev.19 已記下、刻意延後的缺口。<br>Peter 選 B2：<br>・chat 也讀寫入數；<br>・價格段沒寫寫入價（留空，或勾「寫入不另收費」）時，照 input 價計；<br>・只有寫入價明確設成 0 才免費。<br>gateway、IAM、Audit 三個計價引擎一起改。<br>live 驗證：gpt-6-luna 的 chat 冷請求記到 12,539 個寫入 token，與 `/v1/responses` 的記法相同。<br>還沒驗證：GPT-5.6 以前的模型會不會回報寫入數 | [#6779](https://github.com/futurenestit/xparse/pull/6779)、[Xparse-Audit#206](https://github.com/futurenestit/Xparse-Audit/pull/206)；PRD-237 Addendum N、ADR-300 Amendment T、SPEC-302 Rev.21；live 證據在 [PR 留言](https://github.com/futurenestit/xparse/pull/6779#issuecomment-6245384537) 與 `testing/cache-write-metering-probe/` |
| 4 | 已開 issue（Bedrock implicit caching 實測） | [#6774](https://github.com/futurenestit/xparse/issues/6774)，敏捷看板 #6、S10 |
| 5 | 已開 issue（`cache_control_missing` 只看 `/v1/messages`） | [#6775](https://github.com/futurenestit/xparse/issues/6775)，敏捷看板 #6、S10 |
| 9 | 已修並 merge：提示改為 `xparse restart xparse-ingress` | [#6773](https://github.com/futurenestit/xparse/pull/6773)（`93aa124fc`） |

**手冊**（CLAUDE.md §18.6 的第二步還沒完成）

- **誰能合併**：手冊 repo 自 10/16 起由 maintainer 把關，要 code owner（justinkclin、FN-Kenny）approve，而且只有 maintainer 能合併 main。Peter 的帳號沒有合併權限。#6778（`8fae3f63f`）已把這條規則寫進產品端的說明文件。
- **[Xparse-Manual#45](https://github.com/futurenestit/Xparse-Manual/pull/45)**：一次落地五個更新頁 PR——#29、#33、#42（prefix cache 共用範圍）、#43（工具輪換鎖）、#44（W11 自動快取）。PR 裡請 maintainer 用 merge commit 合併，這樣五個 PR 會自動標成 merged。
- **[Xparse-Manual#46](https://github.com/futurenestit/Xparse-Manual/pull/46)**：2026-10-18 的盤點。
  - 撤下 stage=dev 的政策集效果標籤頁；
  - 每一列的上線狀態與日期重新核對過（rel v1.77.1.5、prod v1.76.4）；
  - 修正平台通知等三頁的收件人，以及內容金庫的選項文字；
  - 拿掉一張含 dev-only 按鈕的截圖。
- **#36、#40（Tool 規則）已關閉**：產品 main 在 10-17 把它們描述的行為改掉了，owner 決定延後這批手冊頁。
- **gitlink**：產品 main 的 `3rd/Xparse-Manual` 還指向 `c3573dd`，它是 #36＋#40 的 merge commit，不在手冊 main 上。#45、#46 合併後，「手冊」session 會開產品 PR，把 gitlink 推進到手冊 main。
- **留給 June 決定**：模型入境的兩頁（`model-ingest.md`、`promotion-approval.md`），以及註冊頁的「安全掃描模型庫」文字，寫的都是 stage=dev 的畫面。
- **手冊 session 另外點出、還沒處理的產品問題**：
  - 在被扣住的部署上，地端「來源」步驟的說明文字仍寫著「安全掃描模型庫」；
  - 預算分頁用 `CONSOLE_ENVIRONMENT` 控制顯示，沒走 ADR-473 registry；
  - CLAUDE.md 裡 forecast 那一行「尚未接 compose／deploy」已過期，rel 與 prod 的部署流程都有建置 forecast。

**2026-10-18 第二輪 Agent CLI 實測**（從 #6779 的驗證 session 開出）

- 報告：`/Users/peter/Desktop/testing/agent-ops-2026-10-18/REPORT.md`。
- 規模：
  - Claude Code 2.1.302、Codex 0.163.0、OpenCode 1.19.2，共 827 個 agent 請求；
  - 另有直接打 API 的聊天與工具呼叫各 30 組。
- 一般工作流在三個 client 上都穩定。client 收到的 usage 與稽核，645 筆中 638 筆一致，其餘 7 筆是既定設計。
- 開出的 issue（除 #6789 外都還開著）：

  | Issue | 問題 |
  |---|---|
  | #6785 | PII 或 word filter 開成 enforce 時，每個 agent session 過了 24 個偵測面條目就被拒（約 6–13 個請求） |
  | #6786 | PII 的 person_name 會遮掉路徑與指令裡的使用者名稱 |
  | #6787 | 單向假名經 coding agent 寫進檔案；agent 也會用 byte dump 繞過遮罩 |
  | #6788 | gemma 的回答在 vLLM 0.24.0 的串流 reasoning parser 下被歸成 reasoning，工具輪次之後的回答消失。先前兩份報告把它歸為模型能力，是判斷錯了 |
  | #6789 | 只有 reasoning 的回合，`empty_output` 記成 false。**已修**：#6797（`42ff86d92`） |
  | #6790 | 503 `queue_overflow` 沒有 `Retry-After`；預設 rate limit 下，約 20 個並行請求就開始被拒 |
  | #6791 | chat 與 Responses 把 provider 的 context overflow 以 vLLM 原文加 `provider_error` 回報，client 認不出來 |
  | #6792 | 驗證失敗的 400 沒有 `X-Request-Id`，也沒有稽核紀錄 |
  | #6793 | 讀過一次 PDF，`/v1/messages` session 在不收檔案的模型上就永久 400 |
  | #6794 | IAM `PUT /applications/{uuid}` 回 200，但會靜默忽略打錯的欄位 |

- 同一輪 merge 的 PR：
  - #6795（`37566f64d`）：`agent-cli-setup` runbook 補上實測驗證過的 client 設定；
  - #6797（`42ff86d92`）：`/v1/responses` 與 agent mode 的 `empty_output` 改成與 chat 一致。
- **key 的注意事項**：那個 session 一開始把 app key 與 tenant admin key 寫進了 `env.local`（權限 600），違反規定。它收到限制後已刪除，並確認 `testing/` 裡沒有留下任何 key 的片段。保險起見，可以考慮換掉這兩把 key。

另：#6776 第一次 CI 因新測試檔沒登記進 `gateway-ci-suite.txt` 被 CI-Suite Orphan Gate 擋下（就是第 10 項：本地只照 §17.2 #7 跑 `.sh` 會漏）。已補登記。之後在本地把 `ci.yml` Static Gates 的 124 支 script 全跑一次，並與 origin/main 對照：只多出 `cython-pydantic-method-gate.sh`，它掃到 worktree 裡的 `.venv`，CI 沒有這個資料夾。

---

## 0. 接手前先讀

1. **所有修改都在 `futurenestit/xparse` 開 PR，base 一律 `main`**，不要開 stacked PR（CLAUDE.md §17.2 #9）。
2. **先補設計文件。** §5 每一列都標了「同 PR 要改的設計文件」。13 張裡**幾乎每張都要在同一個 PR 修訂指定的 SPEC 或 ADR 條文**（CLAUDE.md §17.1），不要直接只改程式。
3. **PR 描述要附 ADR-093 表和 Core 對比表**（CLAUDE.md §1.1、§17.4）。push 前跑涵蓋改動檔案的 static gates（§17.2 #7）。
4. **不要部署，也不要動 Peter 的 live stack**：
   - 不要改主 checkout `/Users/peter/Desktop/X-parse/xparse`，不要在那裡 `git pull` 或 `checkout`。
   - 不要重啟或 recreate 任何 `xparse-*` 容器。
   - 主 checkout 裡沒有 commit 的 `3rd/Xparse-Manual`、`3rd/xparse_audit` 變動也不要碰。
   - 一律在自己的 worktree 工作（CLAUDE.md §19）。§3 有怎麼起第二個 gateway 來驗證。
5. **改到 Console 畫面要同批寫使用者手冊**（CLAUDE.md §18.6）。手冊是另一個 repo `futurenestit/Xparse-Manual`，以 submodule 掛在 `3rd/Xparse-Manual`。
6. **帳號與 key 一律向 Peter 要**，不要寫進任何檔案、commit、PR 或 issue。驗收需要的是：
   - **綁 gemma 的 application key**：快取量測、#6726、#6727 會用到。
   - **綁雲端模型的 application key**（`deepseek-flash`、`gpt-6-luna`、`claude-haiku-5-5`）：先確認可以花雲端額度。#6731、#6732、#6734 的驗收要真的打雲端模型。
   - **Console／IAM 的 tenant_admin 登入**：只有要改 Model 的 `rotate_cache_salt_on_tool_calls` 或 application 的 `prefix_cache_sharing_scope` 時才需要。gemma Model 是共用的，翻開關會影響別人，翻之前先問，測完改回原值。
   - **Claude Code 一定要明確設 `ANTHROPIC_BASE_URL` 指向 gateway**（或用 `env -i` 起乾淨環境），不要繼承 shell 的設定。E2E 時曾有一次繼承到 `https://api.anthropic.com`，把 key 送了出去。
   - **Codex 的 `shell_snapshot` 會存下整個 env（含 key）**，跑完就刪。
   - **本機 E2E 的 app key 已有檔案**：`/Users/peter/Desktop/testing/agent-e2e/opencode-cloud/home/.appkey`（`peter` 應用）。2026-10-18 Peter 同意的用法：只在用它的那個指令裡讀進 shell 變數，例如 `K="$(tr -d '\n' < …/.appkey)"`，用完 `unset`；不印出、不複製到新檔案，也不放進 argv 或 log。
   - **E2E 用的 application（`55c3e729-78f1-4f61-9a06-85fd6e3c3519`）也有其他測試者在用**，他們的 Tool 規則曾經靜默拿掉 OpenCode 的 `bash`（E2E F22）。需要乾淨的環境，就請 Peter 開一個專用的 application。
7. **PR、merge 與看板**：
   - 原則上一張 issue 一個 PR；同組要合在一起做時，在 PR 裡寫明。PR 描述寫 `Closes #NNNN`。
   - 交辦給你的 PR，CI 失敗就自己修到綠，全綠後 squash-merge 到 `main`，不必每次問（Peter 的既有偏好）。
   - 以下情況 merge 前先問 Peter：需要產品決定（例如 #6730 的 (a)／(b)）、改動超出 PR 範圍、reviewer 要求修改。
   - 開工與 merge 後，用 `/flow-board agile` 更新敏捷看板 #6 的卡。bug fix 的 commit 可以用 `/flow-bugfix` 的格式。

---

## 1. 原本的問題

vLLM 的 prefix cache 只在 `cache_salt` 相同的請求之間共用。salt 只會算進第一個 KV block 的 hash，後面每個 block 都從前一個鏈下去，所以 salt 不同就完全不共用。gateway 會替每個請求注入 salt，client 不能自己設。

2026-10-16 經過真的 gateway、讀 vLLM 自己的 `prefix_cache_hits_total`／`prefix_cache_queries_total` 量測，結果如下。原始數據在 `perf/projects/cache-salt-toolcall-probe/results/2026-10-16-local-gateway/`。

| 問題 | 原因 | 量測 |
|---|---|---|
| 所有多輪對話的跨輪重用都是 0%，chatbot 也一樣 | 預設 salt 每個請求都不同 | 4 輪對話，每一輪都 0% |
| `X-Conversation-Id` 的 opt-in 從來沒生效過 | `session_cache_allowed` 在 IAM 與 gateway 都沒有 producer | 帶了 header 照樣 0% |
| tool-result 輪次會換 salt | 舊的 tool-call guard（ADR-034 §3.4），依據的前提已被證否 | tool 輪 0% |
| Claude Code 的 billing 行打斷前綴 | system 第一行 `x-anthropic-billing-header: cc_version=<v>.<3 hex>` 跟著 `messages[0]` 變 | `/compact` 後第一輪：0%，剝掉後 89.1%；新 session：0%，剝掉後 99.9% |
| Codex 打 vLLM 完全不帶 salt（E2E 才發現） | `/v1/responses` 翻譯路徑傳 `cache_salt=None` | 所有不帶 salt 的請求共用同一個 KV namespace，造成跨租戶 timing side channel |

salt 一旦穩定，同樣的對話重用率約 99%。

---

## 2. 做了什麼

### 2.1 設計（都已 merge）

| 文件 | 內容 |
|---|---|
| ADR-055 Rev.3（`docs/adr/ADR-055-agent-cache-salt-integration.md` §R3） | 預設改為 per-caller salt（`api_key_uuid` + `system_prefix_digest`）。tool 輪換改成 per-Model 開關，預設關，在 routing 之後逐 step 決定。vLLM egress 剝除 billing 區塊。稽核欄位照實記錄。部署採 expand/contract（§R3.7）。同時修訂 ADR-034 §3.2／§3.3／§3.4／§3.5／§6／§8／§9 |
| ADR-516／PRD-360／SPEC-328 | 應用自選共用範圍：`none`／`api_key`（預設）／`application`／`group`。salt = `HMAC(tenant ‖ scope_kind ‖ scope_subject ‖ system_prefix_digest ‖ narrowing)`，所以雙方都選了同一範圍才共用，跨租戶永不共用；client id 只會讓範圍變窄。只有 tenant_admin 與該群組的 group_admin 能改。以 ADR-473 `stage=rel` 扣住 |
| PRD-034 Rev.2 Amendment、SPEC-034 Rev.2 | 客戶端驗收條件；CT-034-016..027 |
| `docs/research/RESEARCH-conversation-caching-layers-semantic-vs-prefix-2026-10-14.md` §2.2c、§3.5 | 實測數據；LiteLLM、Bifrost、Portkey、one-api、vLLM 的原始碼對照 |

### 2.2 實作（都已 merge 到 main）

| PR | merge commit | 內容 |
|---|---|---|
| #6662 | `4a4b5389e` | ADR-055 Rev.3、SPEC-034 Rev.2、PRD-034 Amendment、probe 腳本與實測結果 |
| #6672 | `4b5d90a69` | ADR-516、PRD-360、SPEC-328 |
| #6673 | `51b1ed50a` | IAM：`Model.rotate_cache_salt_on_tool_calls`（migration 0392）、`Application.prefix_cache_sharing_scope`（migration 0393），以及寫入規則、validate 投影、稽核 |
| #6688 | `b39756fc9` | vLLM egress 剝除 Claude Code billing 區塊，每次剝除記一筆 `NormalizationNotice`（#6654） |
| #6697 | `3529c3ea3` | gateway 依範圍導出 salt，routing 之後逐 step 決定；每個 vLLM step 一筆 `cache_salt_decision` |
| #6689 | `cc31a9b53` | Console：應用 configuration 卡的「前情共用範圍」選項 |
| #6719 | `a19149d39` | `/v1/responses` 翻到 vLLM 時補上 salt（#6717，即 E2E 的 F1） |
| #6722 | `e9e495110` | Console：模型設定分頁的「工具輪換鎖」開關（英文 label：Re-read on tool turns） |

### 2.3 現在 main 上的行為

- **每個送往 vLLM 的 step 都帶 salt**：`/v1/chat/completions`、`/v1/messages`、`/v1/responses` 三個入口都一樣。salt 只在 `apps/gateway/bustream/cache_salt/` 裡導出。
  - **前提**：gateway 要有 `XPARSE_CACHE_SALT_SECRET`，而且 `XPARSE_CACHE_SALT_ENABLED` 不是 false。
  - 缺 secret 時，`apps/gateway/bustream/gateway/app.py:866-879` 只記一行 WARNING，整個功能就關掉，vLLM 請求一律不帶 salt。這是 #3443 記載的既有靜默降級，結果跟 F1 一樣，所有請求共用 namespace。
- **兩條決定 salt 的路徑**。每個請求都先算一次與模型無關的候選 salt（`plan_cache_salt`：scope salt 加 per-request salt）：
  - **chat 與 `/v1/messages`**：在 `gateway/routes/chat.py`，於 routing 決策之後、`build_routing_plan` 之前計算（`gateway/pre_execution.py` 的 `plan_request_cache_salt`）。之後 `build_routing_plan` 對每個 vLLM step 用 `CacheSaltPlan.for_step` 決定。
  - **`/v1/responses` 翻到 vLLM**：不經過 `build_routing_plan`。由 `gateway/responses_cache_salt.py` 的 `ResponsesCacheSalt`，在第一個 vLLM attempt 時，從該 attempt 的 chat 視圖算一次；再由 `worker_setup.chat_seam_backend_config(cache_salt_planner=...)` 逐 attempt 決定（接線在 `gateway/responses_translation.py:235` 附近；SPEC-328 CT-328-13b）。
  - **兩條路徑的規則相同**：如果是 tool-result 輪次，而且該 Model 的 `rotate_cache_salt_on_tool_calls` 開著、或 gateway 沒收到這個值，就改用 per-request salt。
- **前綴摘要**只用 `production/prefix_affinity.system_prefix_digest`：取開頭連續的 system 訊息，去掉 billing 區塊，不含 tools。它同時也是 session affinity 的 `prefix_digest`（SPEC-290 C-290-30）。
- **稽核事件** `cache_salt_decision`：每個 vLLM step 一筆，帶 `routing_attempt`、`cache_salt_scope`、`cache_salt_narrowed_by`、`tool_call_rotation`、`rotation_applied`、`tool_result_turn`、`conversation_id_present`、`agent_task_id_present`、`cache_salt_fingerprint`。
- **E2E 實測**（2026-10-17，gemma-4-E2B-it，vLLM 0.24.0）：

  | CLI | 重用率 | 備註 |
  |---|---|---|
  | Claude Code | 98.9% | fingerprint 跨輪次、跨 `--continue` 都穩定 |
  | OpenCode | 94.9% | 同上 |
  | Codex | 74.6% | 當時 F1 尚未修，請求都不帶 salt |

### 2.4 還沒生效的地方

| 範圍 | 狀態 |
|---|---|
| rel（`origin/rel` `662eeef76`）、prod（`origin/prod` `ed62d8223`） | 都還沒有這批改動 |
| 本地 Mac mini stack | 跑的是主 checkout，Peter 會自己更新，所以可能落後 main 幾個 commit |
| Console「前情共用範圍」 | 被 ADR-473 registry `prefix_cache_sharing_scope`（`stage=rel`）扣住，prod 與客戶安裝看不到 |

---

## 3. 怎麼驗證（本地）

### 3.1 環境

- 這台機器是 Peter 的 Mac mini，經 SSH 操作。
- **live gateway**：對外 `https://localhost:3000`（自簽憑證，見 #6724）；容器內 `http://localhost:8000`。
  - 它 bind-mount 的是**主 checkout**，所以 `docker exec xparse-gateway` 量到的永遠是 main，**不是你 worktree 裡的修改**。在 A/B 比較裡，live gateway 就是「修改前」。
- **IAM admin API**：`https://localhost:3000/apis/iam/...`，帶 `Authorization: Bearer <tenant-admin key>`。
- **vLLM**：`http://192.168.1.143:18004`（gemma-4-E2B-it，vLLM 0.24.0，max_model_len 60000），LAN 上不需認證。
  - 命中指標：`curl -s http://192.168.1.143:18004/metrics | grep -E '^vllm:prefix_cache_(hits|queries)_total'`。
  - counter 是全域的，沒辦法歸屬到單一請求。量測前後各跑一次 `curl -s http://192.168.1.143:18004/metrics | grep -E '^vllm:num_requests_(running|waiting)\{'`，兩次都要是 0；有其他流量就等，或先問 Peter。
- **macOS 限制**：Homebrew 的 Python 連不到區網上的 vLLM，curl 可以。所以 probe 要在容器裡跑；容器裡只有 stdlib。
- **確認 salt 功能是開的**：量測前先跑 `docker logs <gateway 容器> 2>&1 | grep CacheSaltGenerator`，要看到 `initialized`，不是 `not initialized`。rel、prod 部署後也要查一次。

### 3.2 讓 worktree 的程式接上真 IAM 與真 vLLM

- **起第二個 gateway**，跑你 worktree 的程式，可以接真 CLI；用完 `docker rm -f xparse-gateway-wt`。
  - 這段指令是核對時提出的，使用前先確認 network 名稱（目前是 `xparse-network`）與 entrypoint 路徑。
  - env 裡有 secret，不要把它印出來。
  ```bash
  docker run -d --name xparse-gateway-wt --network xparse-network --user 501:20 \
    --entrypoint /app/build/gateway-entrypoint.sh \
    --env-file <(docker inspect xparse-gateway --format '{{range .Config.Env}}{{println .}}{{end}}') \
    -v <worktree>/apps/gateway/bustream:/app/bustream:ro \
    -v <worktree>/apps/gateway/xparse_routing:/app/xparse_routing:ro \
    -p 127.0.0.1:18800:8000 xparse-scr:celery-local
  ```
  - **`--entrypoint` 不可省略**：image 預設的 SCR entrypoint 會跑 Django migration，然後中止。
  - **18800 是純 HTTP**，Codex 也能直接連，不受 #6724 影響。
  - **稽核事件**改看 `docker logs xparse-gateway-wt`。
- **只跑單一腳本**：
  ```bash
  docker run --rm --entrypoint /opt/xparse/gateway/venv/bin/python -e PYTHONPATH=/app -v <worktree>/apps/gateway/bustream:/app/bustream:ro -v <worktree>/apps/gateway/xparse_routing:/app/xparse_routing:ro xparse-scr:celery-local <script>
  ```

### 3.3 Probe 腳本

- 位置：`perf/projects/cache-salt-toolcall-probe/scripts/`。
- 在容器內跑的腳本：`probe_gateway_multiturn.py`、`probe_agent_task_id.py`、`probe_gateway_messages.py`、`probe_billing_header.py`。
  - 執行前，要連同 `common.py` 一起 `docker cp` 到 gateway 容器的 `/tmp/cache-salt/`。
- `decisions.py` 在 host 上跑，讀容器拷出來的 `request_ids.txt`。
- 完整指令見 `results/2026-10-16-local-gateway/README.md`。
- Claude Code 錄製檔：`/Users/peter/Desktop/testing/cache-salt/cc_2_1_301_capture_bodies.json`，用 `XPARSE_CC_CAPTURE` 指定。裡面有錄製機器的環境文字，不要 commit。

### 3.4 測試環境

- **gateway 測試**：容器裡沒有 pytest；主機 Python 是 3.15，要改用 3.11。
  ```bash
  cd <worktree>
  uv venv --python 3.11 apps/gateway/bustream/.venv
  uv pip install --python apps/gateway/bustream/.venv/bin/python --no-deps -r apps/gateway/bustream/requirements-dev.lock
  (cd apps/gateway && PYTHONPATH=$PWD bustream/.venv/bin/python -m pytest bustream/tests/<path> -q)   # 單檔
  (cd apps/gateway/bustream && PYTEST_ADDOPTS='-n 4' .venv/bin/python scripts/project.py test)       # 全套，約 3 分鐘
  ```
  `.venv` 已在 `.gitignore` 裡，不要 commit。它會讓本地的 Cython gate 失敗，這是預期的。
- **IAM 測試**（W6、W9 會用到）：
  - 在 `apps/iam/xparse_iam` 先跑 `uv sync --extra dev --extra postgres --frozen`，再跑：
    ```bash
    DJANGO_SETTINGS_MODULE=xparse_iam.settings PYTHONPATH=<worktree>/apps/iam/xparse_iam:<worktree>/apps/iam .venv/bin/python -m pytest -o addopts='' <path>
    ```
  - IAM 的 conftest 把 `pre_release_features._current_environment` 換成 `"dev"`。測 ADR-473 扣住的行為時，要 monkeypatch 回 `resolve_deployment_environment`，並設定 `XPARSE_ENVIRONMENT`。
  - 重產 `openapi.v1.json` 一定要用 Python 3.11 的環境（`UV_PROJECT_ENVIRONMENT=<scratch>/venv311 uv sync --python 3.11 --extra dev --extra postgres --frozen`），之後重釘七處 consumer digest（CLAUDE.md §17.2 #7）。
- **#6724 的 owner 測試**：
  - installer：`bash packaging/installer/tests/run_tests.sh`。
  - Web installer：照 `tools/xdeploy/README.md` 的「Owner-local tests」。
  - `generate_certs.sh` 與 SCR entrypoint 目前沒有測試，要新增。
- **本地有 6 個 static gate 必定失敗，原因在環境**：
  - audit submodule 不在（3 個）
  - in-tree `.venv` 被 Cython gate 掃到
  - 沒有 `$GITHUB_OUTPUT`
  - 一個 `docs/research` 檔只在 Python ≥3.12 才能編譯

  除此之外的紅燈都是真的。

### 3.5 #6724 的特別注意

- **不要換掉 live ingress 的憑證。**
  - `xparse-ingress` 直接 mount 主 checkout 的 `certs/`（→ `/etc/nginx/certs`）。
  - 重新產生 `certs/cert.pem` 會改變指紋，所有信任舊檔的 client 都會斷線。
- **驗證方式**：照 issue Evidence 4。把新產生器的輸出放在 scratch 目錄，用 `openssl s_server -state` 在 `127.0.0.1:18443` 起一個臨時 TLS 端點，再對它跑：
  - Codex（`CODEX_CA_CERTIFICATE`）
  - Node（`NODE_EXTRA_CA_CERTS`）
  - `curl --cacert`
  - Python `ssl`
- **要先問 Peter 的驗收**：issue 要求「對 ingress 跑 Codex」，#6725 要求「全新安裝」。這兩項都需要換 ingress 憑證，或另外裝一套，動手前先問 Peter 要用哪一種方式。
- **#6724 改的是 packaging、deployments、tools/xdeploy**，所以 CLAUDE.md 的 PRD-302 Migration Guard 適用：
  - 開工前先讀 PRD-302、ADR-418、SPEC-269，以及 marker 指定的 current phase plan。
  - 只在各 owner 內原地修，不搬路徑、不抽共用 helper。
  - PR 只跑 owner 的 functional 測試，不跑 app build（SPEC-269 §7.3.1）。

### 3.6 E2E 報告

`/Users/peter/Desktop/testing/agent-e2e/REPORT.md` 是 Claude Code、Codex、OpenCode × 4 個模型的完整紀錄與證據。各 CLI 的隔離設定在同目錄的 `*/home/`，裡面有 key，不要 commit。

---

## 4. 不屬於 issue、但還沒完成的工作

| # | 工作 | 狀態／下一步 | 接手 agent 可以做嗎 |
|---|---|---|---|
| W1 | 部署到 rel，再到 prod | 未部署。順序依 ADR-055 §R3.7：IAM 先上（migration 0392、0393 只新增欄位）→ **跑 W6 盤點，把有風險的 vLLM Model 設成 true**（W6 還沒實作，在那之前至少要人工對照 Fleet `extra_args` 做一次，並留紀錄）→ 再上 gateway 和 Console。2026-10-18 起這批還要一起帶上 W11（migration 0395）、#6776、#6777、#6779（IAM 先上）與 #6797，見 §0a「部署要多注意的」 | 不行，要 Peter 授權 |
| W2 | rel E2E 驗收 | 等 W1。有一個 session（「rel E2E evidence」）在等 rel 部署 | 不行 |
| W3 | 發佈（S4）：刪掉 ADR-473 entry `prefix_cache_sharing_scope` 與兩端 call site | 等 W2 通過 | 不行，W2 通過前不得刪 |
| W4 | 使用者手冊：Xparse-Manual #42（前情共用範圍）、#43（工具輪換鎖）、#44（W11） | 2026-10-18 改由 #45 一次落地（含 #29、#33），另有盤點 #46；都等 code owner @justinkclin 或 @FN-Kenny review | 不行 |
| W5 | 手冊 gitlink | 「手冊」session 在監看 #45、#46，合併後開產品 PR 推進 gitlink；見下方說明 | 由那個 session 做 |
| W6 | 部署前盤點指令（ADR-055 §R3.7 第 2 步）：列出所有 vLLM Model，標出 Fleet `extra_args` 含 `--speculative-config`、`--kv-cache-dtype fp8*`，或 hybrid／GDN 架構的模型 | **沒有實作**（`apps/iam/.../management/` 找不到）。這是 W1 的前置條件 | 先用 `/doc-issue` 開 issue，Peter 同意後才實作 |
| W7 | 風險組合警告（#6598 Desired 5）：endpoint 用了上述參數、開關卻關著時要顯示警告；外部 vLLM 顯示「engine args unknown」 | **沒有實作，也沒開獨立 issue**，目前只掛在 #6598 底下 | 從 #6598 拆出來，用 `/doc-issue` 開 |
| W8 | 收尾 #6598 | 見下方說明 | 不要自己關 #6598，等 W7 開好後問 Peter |
| W9 | IAM `PATCH /iam/models/{uuid}` 沒有欄位層級的角色規則 | 見下方說明 | 先用 `/doc-issue` 開 issue。這是行為改動，要先補設計閉環 |
| W10 | node-agent 的 vLLM 沒有明確帶 `--enable-prefix-caching`／`--enable-prompt-tokens-details` | 已有 issue #6647 | 不在這批 |
| W11 | Claude 自動快取：聊天機器人沒標 `cache_control` 就沒有快取 | ~~這是產品決定，不是 bug~~ **2026-10-17 Peter 決定：預設自動快取、虧了會停、既有應用一併適用**（ADR-382 Amendment D／PRD-362／SPEC-331）。文件 #6744、IAM #6748、gateway #6750、Console #6751 都已 merge，2026-10-18 本機端到端通過，見 §0a | rel 驗收（CT-331-19）後發佈 |

**W5 手冊 gitlink 的細節**

- 主 repo `origin/main` 上的 `3rd/Xparse-Manual` 指向 `c3573ddbc`。它是手冊 PR #40 的 head（由 #6671 帶進來），它的歷史裡也包含 #36 的 head `1551a5a74`（由 #6666 帶進來）。兩張都還沒 merge。
- #6689、#6722 這兩個 Console PR merge 時，都沒有推進 gitlink。
- ~~要等手冊 #36、#40、#42、#43 **四張都** merge 進手冊 main，再開一個小 PR，把 gitlink 推到包含這四張的手冊 main commit。先推的話，會丟掉 #6666、#6671 的手冊頁。~~
- **2026-10-18 更新**：#36、#40 已關閉（產品行為在 10-17 改了，owner 延後那批手冊頁），所以推進 gitlink 時，不再需要保留 #6666、#6671 的手冊頁。#42、#43、#44 改由 #45 一次落地。等 #45、#46 合併後，把 gitlink 推進到手冊 main 即可。
- 手冊 repo 的 merge commit 和 squash 兩種方式都用過，所以不要假設 `c3573ddbc` 會自己變成 main 的祖先。推之前，在 `3rd/Xparse-Manual` 裡跑 `git merge-base --is-ancestor <新 gitlink> origin/main` 確認。

**W8 收尾 #6598 的細節**

- #6598 還開著（看板 #6：S10、Triaged）。
- 已完成的 Desired 與對應 PR：

  | Desired | 對應 PR |
  |---|---|
  | 7 | #6662（ADR-055 Rev.3） |
  | 1–4 | #6673（IAM 欄位與 read API）、#6697（gateway 逐 step 決定 salt、`/v1/messages`）、#6719（`/v1/responses`）、#6722（Console 開關，Desired 4） |
  | 6 | #6597（`probe_air520_revalidate.py`） |

- Desired 1 原本要的是 **per-endpoint** 開關，ADR-055 Rev.3 改成 **per-Model**。結案說明要寫出這一點。
- 建議把 W7 拆成新 issue 後關掉 #6598，或把 #6598 改寫成只剩 W7。

**W9 IAM PATCH 權限的細節**

- `PATCH /iam/models/{uuid}` 只有 `model.update` 的 action 授權（`_models.py:1182-1188`）和租戶檢查（`:1196`），沒有欄位層級的角色規則。
- 任何能編輯該模型的角色都能改 `rotate_cache_salt_on_tool_calls`，包括只被授權使用 tenant 模型的 group_admin。而這個開關會影響所有使用該模型的群組。
- 這是 PRD-272 §3.5／§3.6 記載的、整個設定分頁的既有缺口；SPEC-034 CT-034-027 註明「是現況，不是契約」。修法要針對整個分頁，不只這個開關。

---

## 5. 待修 issues

> **2026-10-18**：除了 #6725，這 13 張都已修好並關閉，看板上的卡已移到 Done。現況與對應的 PR 見 §0a；本節保留 10-17 的原始索引，供查設計文件與禁止事項。

13 張都在敏捷看板 #6，欄位都是：Status Triaged、Sprint S10 10/20-11/02、assignee LeiIeongTam-Peter。

每張 issue 本文都有完整的 Evidence、Desired、Acceptance、Out of scope。**修之前先讀 issue 本文**，下表只是索引。關鍵檔案以 origin/main `e329c51c2` 為準；gateway 各列的路徑相對於 `apps/gateway/bustream/`，#6724、#6725、#6728 相對於 repo root。

| Issue | P | 摘要 | 關鍵檔案 | 修法要點 | 同 PR 要改的設計文件 |
|---|---|---|---|---|---|
| [#6724](https://github.com/futurenestit/xparse/issues/6724) | P2 | 自簽憑證被產生成 `CA:TRUE`，ingress 卻拿它當網站憑證，Codex（rustls）一律拒絕 | `packaging/installer/install.sh:777-783`、`deployments/operations/scripts/generate_certs.sh:44-50`、`packaging/distributions/scr/runtime/scr-entrypoint.sh:14-17`、`tools/xdeploy/install_service/web/installer.py:209-220` | 四個產生器各自原地加上 `basicConstraints=critical,CA:FALSE`、`keyUsage=critical,digitalSignature,keyEncipherment`、`extendedKeyUsage=serverAuth`；SCR 另補 `subjectAltName=DNS:localhost,IP:127.0.0.1`。產生後讀回憑證檢查，不符就 exit 非 0（ADR-093 #3／#4）。可參考 `scripts/generate_registry_certs.sh:87-91` | 是：ADR-107 新增 §2.7「自簽憑證 profile」，Core-ADR-10 補 INV-107-3（領域 10 的 Core 對比表） |
| [#6725](https://github.com/futurenestit/xparse/issues/6725) | P4（看板填 P3） | `docs/runbooks/agent-cli-setup.md` 沒寫自簽或私有 CA 的信任步驟 | `docs/runbooks/agent-cli-setup.md` | 加一節：OpenCode／Claude Code 設 `NODE_EXTRA_CA_CERTS`，Codex 設 `CODEX_CA_CERTIFICATE`。Codex 的驗收要等 #6724 修好 | 否 |
| [#6726](https://github.com/futurenestit/xparse/issues/6726) | P3 | tool-result 偵測只看 `messages[-1]`。Claude Code 在 tool_result 後面會再插一則 system 訊息，所以永遠判成 `tool_result_turn=false`，工具輪換鎖對它沒作用 | `cache_salt/tool_detection.py:80-87`、`cache_salt/decision.py:158`、`cache_salt/context.py:47` | 「本輪」改為最後一則 assistant 之後的訊息，其中有 `role:tool` 就算 tool-result 輪次。三個入口都要涵蓋，包括 `/v1/responses` 那條。測試要用真 Claude Code 的 fixture。見 §7.1 的部署順序 | 是：SPEC-034 CT-034-019／020 的 tool-result 輪次定義、ADR-055 §R3.2 括號內的說明、`context.py:47` 與 `decision.py:57` 的 docstring |
| [#6727](https://github.com/futurenestit/xparse/issues/6727) | P2 | context overflow 的 400 照 vLLM 原文轉給 `/v1/messages`，Claude Code 認不出來，不會自動縮小 `max_tokens` 或 compact | `streaming/workers/vllm_worker.py:382-384`、`gateway/non_streaming_handler.py:1800-1803`、`gateway/routes/messages.py:604` | 只在 `/v1/messages`、而且 `effective_error_code(e) == "context_overflow"` 時，改用 Anthropic 的錯誤措辭。禁止事項見 §5.3 | 是：ADR-239 amendment（措辭對照表，加一列「讀不到 window 就不改寫」；先例見 ADR-239 §2.1.9 第 3 項），加一條 SPEC-312 新條文 |
| [#6728](https://github.com/futurenestit/xparse/issues/6728) | P4（看板填 P3） | runbook 只叫人設 `CLAUDE_CODE_MAX_CONTEXT_TOKENS`；60k 的模型在輸入約 28k 時照樣回 400 | `docs/runbooks/agent-cli-setup.md:82-93`（§1「不認得的模型名稱與 context window」，:89 是 `CLAUDE_CODE_MAX_CONTEXT_TOKENS` 那一列） | 加一列 `CLAUDE_CODE_MAX_OUTPUT_TOKENS`。不必等 #6727：照 issue Desired 4，在 :92 寫明前提「目前實測不成立，等 #6727 修好再回來看」。#6727 merge 時再複驗 | 否 |
| [#6729](https://github.com/futurenestit/xparse/issues/6729) | P3 | 同一種 context overflow，非串流記成 `error_type=provider_error`，串流記成 `context_overflow` | `gateway/non_streaming_handler.py:1782-1791`、`gateway/routes/chat.py:2987` | 兩條路徑都用 `effective_error_code(e) or "worker_error"`。只改 `non_streaming_handler.py:1784`。PR 要註明：dashboard 上非串流的 `error_type` 會改變 | 是（小）：ADR-441 §1.3 註記，或 SPEC-308 §9 的終端條文，二選一 |
| [#6730](https://github.com/futurenestit/xparse/issues/6730) | P2 | `/v1/responses` 不理會 `stream:false`（或沒帶 stream），一律回 SSE。OpenAI SDK 非串流的 `responses.create()` 拿到字串（SDK 根本不送 `stream`）。SPEC-234 C-234-14 寫了，但從沒實作 | `gateway/responses_request_model.py:56-62`、`gateway/surface_adapters/responses.py:197`、`gateway/routes/responses.py:326` | 分兩段，見 §6 C 組 | 是：C1 修 SPEC-307 RF-3。C2 先由 Peter 在 ADR-339 D5 Amendment 決定（a）或（b），之後改 SPEC-234 C-234-14、SPEC-282 RSP-ADM-12／TC-282-37、PRD-157 G1，並回寫 Core-ADR-01:112 |
| [#6731](https://github.com/futurenestit/xparse/issues/6731)（enhancement） | P3 | billing 區塊只在 vLLM egress 剝除；走 OpenAI wire（chat 與 D10 Responses bridge）時，`/compact` 後第一個請求 cached 為 0 | `translation/chat_message_shape.py:69`、`streaming/workers/openai_worker.py:226`、`:261`、`gateway/worker_setup.py:809-811`、`:846-848`、`:1635`、`tests/contract/provider_param_matrix.md:69`（證據：`vllm_worker.py:686`、`anthropic_translation.py:234-242`） | 只在 egress 剝除，不改 request 或 worker 的 `self.messages`。矩陣要重產；`no_silent_drop_baseline.py` 不得增加 | 是：先修 SPEC-256 C-256-D16h 與 C-256-D16k，再寫 ADR-055 §R3.6 amendment；ADR-382 AM-B 補一段，說明 Alternative B 的否決理由為什麼不適用於 OpenAI egress |
| [#6732](https://github.com/futurenestit/xparse/issues/6732) | P3 | `/v1/messages` 從不回傳 thinking token 數：串流與非串流都把 `output_tokens_details` 丟掉（SPEC-302 C-302-9a 的缺口） | `translation/native_body.py:71`、`streaming/workers/anthropic_worker.py:157-171`、`gateway/anthropic_translation.py:879-888`（`OpenAIToAnthropicStreamBuilder.feed_chunk`／`finish`） | 串流 builder 保留 `completion_tokens_details`，`finish()` 時輸出 `output_tokens_details.thinking_tokens`；非串流比照 | 是（小）：SPEC-302 C-302-9a 的下游清單加 `/v1/messages`，ADR-239 用量段補一行 |
| [#6733](https://github.com/futurenestit/xparse/issues/6733) | P3 | `/v1/messages/count_tokens` 沒計入 assistant `tool_use` 的 input，agent 對話越長少算越多（違反 ADR-419 INV-419-9） | 要改：`gateway/token_estimate.py:570-618`（`estimate_text`、`estimate_for_client`）。只是證據、不必改：`anthropic_translation.py:351-366`、`routes/messages.py:807` | **只改對外的 count_tokens**，禁止事項見 §5.3。tokenizer 本身約 33% 的低估另由 #3897 追 | 是（小）：SPEC-270 C-270-21 點名 assistant `tool_use` input，並補一個 TC |
| [#6734](https://github.com/futurenestit/xparse/issues/6734) | P3 | `/v1/responses` 翻到 DeepSeek 時，回放會丟掉 DeepSeek 自己的 reasoning，每輪送 `reasoning_content:""` | `translation/stream/chat_pivot_decoder.py:121-129`、`:191-196`、`gateway/responses_translation.py:199`、`:239-240` | 把該輪的 `reasoning_content` 封進 reasoning item 的 `encrypted_content`；沿用 ADR-503 D6 的 `xpenv1` 信封，只在 `translation/envelope.py` 加一種 block kind。回放時還原 | 是：SPEC-312 C-312-17、C-312-29 與 §3.1 `item:reasoning` 列；ADR-208 Amendment 9（修正 D1 的前提，A9.5 補列 `/v1/responses`）；Core-ADR-01、Core-ADR-06 同步更新。ADR-503 不用改 |
| [#6735](https://github.com/futurenestit/xparse/issues/6735) | P3 | chat 串流在 tool-call 回合送兩次 `finish_reason`，每個串流最後還多一個 `finish_reason:null` 的 choice chunk；LangChain 會把它讀成 `tool_callstool_calls` | `gateway/sse_formatter.py:279`（`_format_tool_calls`）、`streaming/manager_v3_held.py:204-229`、`gateway/routes/chat.py:2845-2853`（tail chunk）、`anthropic_translation.py::feed_chunk`（tool_calls 分支） | 每個 choice 只送一次非 null 的 `finish_reason`，放在 done chunk；calls chunk 改成 `null`。Desired 3 要決定 tail meta 放哪裡，建議放 `choices: []` chunk（見 §6 D 組） | 是：SPEC-217 C-217-23、SPEC-304 §8.3（:439、:446） |
| [#6736](https://github.com/futurenestit/xparse/issues/6736) | P3 | chat 串流 chunk 帶頂層 `metadata` 物件，OpenAI SDK 的 `.stream()` 把它當成 `ChatCompletion.metadata: Dict[str,str]`，每次都警告，嚴格驗證會失敗 | `gateway/sse_formatter.py:151-163`、`streaming/agent_manager.py:545-547`、`gateway/non_streaming_handler.py:1491`；同 PR 要搬的內部讀者：`gateway/anthropic_translation.py:842`、`gateway/messages_stream_blocks.py:89`、`tests/contract/helpers/sse_parser.py:284` | 把 BuStream 欄位移到 `xparse` 下（非串流 body 與串流 tail chunk `routes/chat.py:2851` 已經用這個 key）。同 PR 搬動內部讀者，不得同時寫兩份 | 是：EVENT_STREAM_SPEC §3、§5、§7、§10.1、§10.2 改版並升版號；更新 ROUTING_SPEC :590 的範例；改 SPEC-304 C-304-151 的措辭 |

### 5.1 相關但不需要新開的 issue

| Issue | 內容 |
|---|---|
| #3644 | OTel span 屬性洗版（E2E 的 F13）。已經有 issue，同一個原因、同一個修法 |
| #3897 | `count_tokens` 對非 OpenAI 模型用 proxy tokenizer。E2E 的量測已補成留言：Claude 少算約 33% |
| #6647 | node-agent 的 vLLM 沒有明確開啟 prefix caching 與 per-request cached tokens（W10） |
| #6649 | FAE：驗證地端客戶對 prefix-cache 重用的實際需求 |
| #6598 | 原始需求，見 W8 |

### 5.2 已知、但還沒開 issue

不要把這些併進上面任何一張的 PR。要做的話，先走 `/doc-issue` 開 issue。

| 來源 | 內容 |
|---|---|
| #6735、#6736 的 Out of scope | chat 串流每個 delta chunk 都帶 `delta.role: "assistant"`（`sse_formatter.py:126`、`:147`）。OpenAI SDK 的 `.stream()` 會把它串成 `assistantassistant…`，嚴格驗證報 literal_error。開好之後排進 D 組，跟 #6735、#6736 依序做（同一個 serializer） |
| #6735 的 Out of scope | tool-call 回合的 `xparse.empty_output: true`（ADR-338 INV-338-5 的語意） |
| #6724 的 Out of scope | `generate_certs.sh --force` 沒有實作；`generate_certs.sh` 與 `installer.py` 產生的 `key.pem` 權限是 0644 |
| #6734 的 Out of scope | `/v1/messages` → DeepSeek 會丟掉 `thinking` block |
| #6731 的 Out of scope | `azure_openai`／`azure_openai_responses` 的 billing 區塊。要先 probe，再加 SPEC 列 |
| #6728 的 Out of scope | `SPEC-196:206` 的敘述已過期，交給 `/doc-governance` |
| E2E 報告 | vLLM `192.168.1.143:18004` 在 LAN 上不需認證，尚未評估 |
| W6、W7、W9 | 見 §4 |

### 5.3 各 issue 的禁止事項（摘自 issue 本文）

- **#6733**：只改對外的 `count_tokens`。
  - `estimate_text(..., include_tool_calls=False)` 預設關，只有 `estimate_for_client` 傳 `True`。
  - `estimate_prompt_tokens`，以及 budget、ceiling、admission、routing、audit 讀到的文字，都要逐位元不變（SPEC-270 C-270-22）。否則 429 的邊界會跟著移動。
  - count-once 與 off-loop 的測試要維持綠。
- **#6727**：
  - 判斷只用既有的 `effective_error_code(e) == "context_overflow"`。不得新增字串比對，也不得依 provider 引用的 client 文字判斷（INV-397-10）。分類結果以資料的形式傳給 renderer。
  - window 從 provider 的訊息讀；`max_tokens` 用 gateway 送出的值；input 取估算值與 provider 所述兩者中較大的。讀不到 window 就保留原文。
  - 稽核的 `error_message`、chat 與 responses 的錯誤 body 都不變。
  - 不得夾或補 `max_tokens`（INV-332-10）。
- **#6729**：只改 `non_streaming_handler.py:1784` 的 `error_type`。health 的判定與 client 收到的 `error.code` 都不變。
- **#6731**：
  - 不得改 request 或 worker 的 `self.messages`，只在 egress 剝除。
  - 矩陣重產後，`no_silent_drop_baseline.py` 不得增加。
- **#6734**：
  - 只能從 gateway 自己的 `xpenv1` 信封還原，而且必須是同一個 provider、同一個 credential（C-312-23），前提是請求有 `include: ["reasoning.encrypted_content"]`。
  - 不得從明文 `summary` 還原，也不得用 `rs_xp_` id 判斷來源。
- **#6736**：不得同時寫 `metadata` 與 `xparse` 兩份。
- **#6724**：四個產生器分屬不同 owner，各自原地修，不得抽跨 owner 的共用 helper 或 symlink（PRD-302／ADR-418）。

---

## 6. 建議的修理順序與分組

依「影響大小」和「會不會改到同一個檔案或同一份文件」分組。同一組交給**同一個 agent 依序做**。

| 順序 | 組 | Issues | 理由 |
|---|---|---|---|
| 1 | A：連線與文件 | #6724 → #6725 + #6728 | #6724 影響最大：Codex 在預設安裝下連不上。#6725 與 #6728 都改 `docs/runbooks/agent-cli-setup.md`，合成一個 docs PR（兩張 issue 都這樣建議）。#6725 的 Codex 驗收要等 #6724 |
| 2 | B：context overflow | #6727 → #6729 | 都改 `non_streaming_handler.py` 約 :1780-1803 那一段錯誤處理 |
| 3 | C：`/v1/responses` 非串流 | #6730-C1 →（Peter 決策）→ #6730-C2 | 見下方說明 |
| 4 | D：串流格式與 `/v1/messages` 串流 builder | #6735 → #6736 → #6732（→ 5.2 的 `delta.role`） | 見下方說明 |
| 5 | E：count_tokens | #6733 | 只改 `gateway/token_estimate.py`，加上 SPEC-270，不碰其他組的檔案 |
| 6 | F：快取相關 | #6726、#6731 | 見下方說明 |
| 7 | G：DeepSeek reasoning | #6734 | 程式檔獨立。契約要改 SPEC-312（與 #6727 同一份文件）和 ADR-208 A9 |

**C 組（#6730）分兩段**
- **C1**：只有明確帶 `stream:false` 時回 400 `unsupported_parameter`，同 PR 修 SPEC-307 RF-3。不需要決策，可以先做。
- **C2**：先請 Peter 在 ADR-339 D5 Amendment 二選一：
  - (a) 沒帶 `stream` 時，照 OpenAI 語意回非串流 JSON；
  - (b) 維持串流，在對外文件註明要帶 `stream=True`。

  決定之後才實作 C-234-14、登記 `responses_json` path、收窄 SPEC-282 RSP-ADM-12、修 PRD-157 G1，並回寫 Core-ADR-01:112。
- OpenAI SDK 預設的 `responses.create()`，要等 C2 選 (a) 並完成後才會正常。

**D 組（#6735 → #6736 → #6732）**
- 三張都改 `anthropic_translation.py::OpenAIToAnthropicStreamBuilder.feed_chunk`：
  - #6735 改 tool_calls 分支對 calls chunk `finish_reason` 的依賴；
  - #6736 把 `chunk.get("metadata")` 改讀新的 key；
  - #6732 加 `completion_tokens_details`，以及 `finish()`／`to_anthropic_message` 的 `output_tokens_details`。
- #6735、#6736 另外共用 `sse_formatter.py` 與 SPEC-304（:439、:446）。只有 #6735 會改 `routes/chat.py:2845-2853` 的 tail chunk。
- 做 #6735 Desired 3 時，要先定好 tail meta 放哪裡，建議放 `choices: []` chunk。如果放到 done chunk，#6736 就要把 done chunk 的 BuStream 欄位與 tail meta 合併成同一個 `xparse` 物件（目前兩邊的欄位名不衝突）。

**F 組（#6726、#6731）**
- 程式檔不重疊，可以並行做：
  - #6726：`cache_salt/tool_detection.py`、`decision.py`、`context.py`
  - #6731：`translation/chat_message_shape.py`、`streaming/workers/openai_worker.py`、`gateway/worker_setup.py`、`provider_param_matrix.md`
- 但兩張都修訂 ADR-055（§R3.2、§R3.6，以及檔頭的 Rev／Date 行），也都要回寫 Core-ADR-01 的 ADR-055 列。所以 PR 要依序 merge，第二個 rebase 後改用下一個 Rev 號。

**跨組的衝突**
- **程式檔**：各組大致不重疊，例外有兩處：
  - B（#6727，`routes/chat.py` :3016 附近的串流錯誤 chunk）與 D（#6735，同檔 :2845-2853 的 tail chunk）改同一個檔案的不同段落。
  - C（#6730）與 G（#6734）都會碰 `gateway/responses_translation.py`（salt 接線在 :235），不要並行。
- **契約文件**會被多組同時修訂：

  | 文件 | 修訂的組 |
  |---|---|
  | Core-ADR-01 | B、C、D、F、G |
  | Core-ADR-06 | F、G |
  | SPEC-312 | B（#6727）、G（#6734） |
  | ADR-239 | B（#6727）、D（#6732） |
  | ADR-055 | F 組內兩張 |

  這些文件的 `**Date:**` 檔頭只有一行，平行開 PR 一定會在那一行衝突。規則：**每份共用文件同一時間只開一個 PR**；後 merge 的負責 rebase，並把自己的 revision 接在最新一筆後面。
- **可以完全並行的**：#6724、#6733、#6726（注意 F 組的 ADR-055 順序），以及 B 組（和 D 組錯開 `routes/chat.py`）。

---

## 7. 修的時候要守的規則（摘自 CLAUDE.md）

- **測試先行**（§8），而且要有「真元件確實會觸發」的證據（§8.1）；只用 fake 證明的是 fake 的契約，不算數。
- **gateway 的硬性規則**都在 CLAUDE.md「Roadmap 精簡版」那幾條，改到相關路徑前先讀對應的那條：
  - **參數與內容 part 不得無聲消失（INV-256-18）**：新增 provider、seam 參數或 `NormalizationAction`，或者改變某一格送不送（例如 #6731），都要先在 `apps/gateway/bustream/tests/contract/provider_param_matrix.py` 有處置，並重產同目錄的 `provider_param_matrix.md`。`no_silent_drop_baseline.py` 只減不增：修掉一格，就在同一個 PR 移除該筆，並把測試裡 `KNOWN_GAPS_PER_ROW` 對應列的數字調降。
  - **用量可見性只加在共用終端**。
  - **失敗終端的健康判定要寫在呼叫點上**。
- **migration 只能先加後減**（§8.3）。
- **建 issue 一律走 `/doc-issue`**，包括看板同步。
- **CI 失敗時**，先找另一個不相關的 PR、對照同一個 job，判斷是不是 flake（§17.2 #7.3）。

### 7.1 不要弄壞已 merge 的快取行為

- **不要改這些**：
  - `cache_salt/` 的 HMAC 輸入，以及各段的順序。一改，所有 caller 的 salt 都會變，快取全部歸零一次，三個入口的 salt 也可能不再一致。
  - `production/prefix_affinity.system_prefix_digest`。它同時是 session affinity 的 `prefix_digest`（SPEC-290 C-290-30）。
  - `cache_salt/decision.py` 的 `rotated = self.tool_result_turn and switch is not False`。
  - IAM `rotate_cache_salt_on_tool_calls` 的預設值 `False`。
  - migration 0392、0393。
  - ADR-473 entry `prefix_cache_sharing_scope`（W2 通過前不得刪）。
  - `_BILLING_HEADER_DROPPING_PROVIDERS` 裡的 `vllm`。
- **#6726 會改變 Claude Code 的 salt**：
  - 修好後，Claude Code 的 tool-result 輪次會變成 `tool_result_turn=true`。開關是 `false` 時 salt 不變；但如果 gateway 沒收到開關值（`unknown`，例如 IAM 版本比 gateway 舊），就會改用 per-request salt，Claude Code 的重用率掉到 0%。
  - 測試要涵蓋：switch=False 時，fixture 的三輪是同一個 salt。
  - PR 要寫明部署順序必須是 IAM 先、gateway 後（W1），也要寫明 chat 的 `[..., tool, user]` 會變成 tool-result 輪次。
- **新增任何會建出 vLLM worker 的路徑，都要接上 salt**（例如 #6730 的非串流 `/v1/responses`）：
  - 多 step 走 `build_routing_plan(cache_salt_plan=...)`；
  - 單一 model 的 seam 走 `chat_seam_backend_config(cache_salt_planner=...)`。

  漏接就是 F1 再犯：請求不帶 salt，所有 tenant 共用同一個 KV namespace。
- **#6731、#6734 改的 `worker_setup.py`、`responses_translation.py`，就是 salt 接線所在。** 改完要確認每個 vLLM step 仍然有一筆 `cache_salt_decision`。
- **改到 gateway 的 PR，下列測試都要維持綠**（路徑在 `apps/gateway/bustream/tests/` 下）：
  - `contract/test_cache_salt_policy.py`
  - `contract/test_spec328_prefix_cache_sharing_scope.py`
  - `contract/test_agent_cache_salt_integration.py`
  - `contract/test_billing_header_vllm_egress.py`
  - `integration/test_cache_salt_per_step_routes.py`
  - `integration/test_responses_cache_salt.py`
  - `unit/test_cache_salt.py`
  - `unit/test_responses_cache_salt.py`
- **動到 salt、billing 或 tool 偵測的 PR，要在 live 上再量一次**：
  - 對 §3.2 的第二個 gateway 跑 `probe_gateway_multiturn.py` 與 `probe_gateway_messages.py`。
  - 第 2～4 輪的重用率應該約 99%，`cache_salt_fingerprint` 跨輪不變。
  - 結果和 `results/2026-10-16-local-gateway/README.md` 對照。

---

## 8. 參考路徑

- **設計**：
  - `docs/adr/ADR-055-agent-cache-salt-integration.md`（§R3）
  - `docs/adr/ADR-516-prefix-cache-sharing-scope.md`
  - `docs/adr/ADR-034-vllm-prefix-cache-policy.md`
  - `docs/prd/PRD-034-vllm-cache-salt-strategy.md`（§0）
  - `docs/prd/PRD-360-prefix-cache-sharing-scope.md`
  - `docs/spec/SPEC-034-vllm-prefix-cache-contrast-test.md`（Rev.2）
  - `docs/spec/SPEC-328-prefix-cache-sharing-scope-contracts.md`
- **研究**：
  - `docs/research/RESEARCH-conversation-caching-layers-semantic-vs-prefix-2026-10-14.md`
  - `docs/research/RESEARCH-cache-salt-tool-call-guard-coding-agent-2026-09-04.md`
- **程式**（相對於 `apps/gateway/bustream/`，IAM 那行除外）：
  - `cache_salt/`（導出：`decision.py`、`tool_detection.py`、`context.py`）
  - `gateway/pre_execution.py`（`plan_request_cache_salt`）
  - `gateway/worker_setup.py`（`build_routing_plan`、`_step_cache_salt`、`chat_seam_backend_config`）
  - `gateway/responses_cache_salt.py`
  - `gateway/responses_translation.py`（`cache_salt_planner` 接線，約 :235）
  - `production/prefix_affinity.py`（`system_prefix_digest`）
  - `billing_header.py`
  - `streaming/workers/vllm_worker.py`
  - `apps/iam/xparse_iam/xparse_iam/core/pre_release_features.py`（`PREFIX_CACHE_SHARING_SCOPE`）
- **證據**：
  - `perf/projects/cache-salt-toolcall-probe/`（腳本與結果）
  - `/Users/peter/Desktop/testing/agent-e2e/REPORT.md`（E2E 報告）
  - `/Users/peter/Desktop/testing/cache-salt/`（本地 probe 與 Claude Code 錄製檔）
- **wiki**：
  - `xparse-wiki/wiki/concepts/vllm-prefix-cache.md`
  - `xparse-wiki/wiki/concepts/vllm-cache-salt-policy.md`
  - `xparse-wiki/wiki/concepts/prefix-cache-sharing-scope.md`
