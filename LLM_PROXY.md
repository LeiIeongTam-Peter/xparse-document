# LLM Proxy 模型定址（ADR-138 Rev.6）——全程紀錄

> **2026-10-14 追加（09-29 之後跟定址有關的合併；rel = v1.77.0.16，內容是 main 到 10-08 #6191 為止＋cherry-pick；prod = v1.76.4，main 只到 09-22）**：**已在 rel、prod 還沒有**：① 定址只剩一個決策點——chat／`/v1/messages`／`/v1/responses` 共用 `gateway/model_addressing.py::decide_addressing`（#5783，ADR-494 P2d），路由也只剩 `route_resolution.resolve_route`（#5784／#5786）。三個前提每個面都一樣：app 沒綁任何模型 → 400；opaque 請求但本面沒模型、或指名的模型只綁在另一面 → 422；pin 不會再被悄悄換成別顆（#5780）。`/v1/responses` 的定址拒絕跟 chat 同形，且 404／422 改成 400，Codex 不再重試五次（#5776／#5841）。② `/v1/embeddings`、`/v1/audio/*` 也有定址了（#5950）：embeddings 用 app code 或 default 就跑該 app 唯一那顆 embedding 模型（0 顆 404、多顆 400 `model_ambiguous`），沒綁的名字 404（`mock-embedding`／`text-embedding-3-small`／`bge-m3` 三個只減不增的例外除外）；opaque app 指名真名目前只記錄（`would_status_code=400`）；audio 全部只記錄。切成 enforce 在 #5949（開著）。③ 回應裡的模型名（ADR-221 Amendment A／B）：menu app 的 chat 回應每個 chunk 與 body 都寫實際跑的模型，R3 後寫替代模型；default token 的非串流請求現在也會 R3（#6072）。`/v1/messages` 與 `/v1/responses` 也改寫實際跑的模型（#6161）；已知限制：串流 messages 的 `message_start` 與 Responses 的 `X-Xparse-Model-Default` 在串流開始前就定了，R3 後仍是 primary（SPEC-312 C-312-39）。opaque app 一律 `application_code`，串流 chunk 也是（#6002；之前 opaque 的串流 chunk 會露出綁定的模型名）。④ 翻譯軸 P3／P8（#6158／#6190，ADR-503）：「哪個面能用哪顆」只問 `translation/capabilities.serves()`。候選池原生優先：opaque 請求有本面候選就只在本面候選裡選，沒有才用延伸候選；指名任何能服務的模型都能 pin。R3 用完本面候選後，ADR-260 的 `resilience.cross_surface_fallback`（per-scope，預設開）允許才換到延伸候選；pin 不延伸。`/v1/responses` 現在可由 Claude 與 chat 家族模型無狀態回答（有狀態請求只留能存狀態的模型，否則 400 `stateful_responses_unsupported`），每個 R3 替代模型也過 Policy Kernel。kill switch 是 `XPARSE_TRANSLATION_FORCE_OFF`。⑤ `/v1/responses` 的 `llm_judge_routing` 真的會問 judge（#5804，#4248 已關）。⑥ `XPARSE_ANTHROPIC_MESSAGES_ENABLED` 退場，`/v1/messages` 永遠開（#5782）。⑦ session affinity：前綴雜湊只讀開頭的 system 回合（#5607）；coordinated 多副本經 Redis 共用 pin（#5663）。**只在 main、rel 還沒有**：`/v1/messages` 打 Claude 原樣直送（P9，#6218）。provider 帳號不能服務（402、credit balance 等）→ R3 換下一顆並進 breaker（#6249／#6267）。被拒的請求不再拉低模型健康分、不再驅逐別人的 pin（#6362）。Claude Code `/compact` 後保留 pin（#6356）。R3 換到 Policy Kernel 不准的模型時只標記與計數，照跑（#6461）。`decision_evidence` 記候選池 `surface_pool_kind`（home／extended／pinned）與兩個計數，自動路由選到 breaker 開著的模型只計數（#6459）。執行邊界 `route_target` 改看模型的 `serving_locality`，預設 shadow（#6406，ADR-511）。`json_schema` 請求不會路由到 DeepSeek，指名 DeepSeek 先回 400 `structured_output_unsupported`（#6512）。沒綁憑證的地端模型在 `/v1/responses` 也能回（#6489，之前 500）。proxy 的 active consumer 數與 code 清單排除已終止的 app（#6515）。Console 建 LLM Proxy 必選 group、system admin 先選 tenant（#6501），LLM Proxy 頁有教學（#6506）。設計文件 PRD-356／ADR-512／SPEC-324「一把憑證一次註冊多個雲端模型」（#6458，只有文件）。**補一筆 09-14 漏記的**：ADR-138 **Rev.10**（#4783）——menu app 的 `/v1/models` 第一個列 `application_code`、再列真名；會路由的 app 那一筆 `owned_by = "xparse-smart-routing"`；opaque app 不變（rel、prod 都有）。下文過時的「現在／未部署／待 merge」已原地加「2026-10-14 註」。
> **2026-09-22 追加（#5233 已 merge，ADR-267 Amendment A）：proxy 那一列的 `profile_type`（Console 的「Use Case」）變成惰性欄位。** ADR-414 之後 proxy 不再 mint client key，kernel 只讀 consumer app 的 `profile_type`，proxy 列唯一剩下的讀者是 model ping 的 probe key——這正是「on_prem proxy 測雲端模型必 403」那個坑的成因。現在：probe key 在兩條 validate 路徑一律投影 `hybrid`（INV-267-7）、proxy 出生即 `hybrid`、對 proxy PUT 改 `profile_type` 回 `400 PROXY_PROFILE_TYPE_INERT`（同值重送不算改，INV-267-8）、**proxy configuration 頁拿掉 Use Case 與 #3647 確認框**（INV-267-9），`inventory_on_prem_pinned_proxies` 命令刪除。consumer app 的 Use Case 不變。跟 §10.7 Rev.9 拿掉 Model Name Visibility 是同一個模式再用一次。
> **2026-09-22 傍晚再追加 §24 尾段（PR [#5258](https://github.com/futurenestit/xparse/pull/5258)，SPEC-294 Rev.5）**：全矩陣實測 breaker 在高 RTT 網路上死循環（探針永遠是冷連線、永遠逾時）——**冷連線那一次判級 deadline 自動 +2 s**（routing 1.5→3.5 s、guardrail 3→5 s），逾時照計、evidence 不變。定址規則零變動。完整紀錄 `路由v2.md` §27.9。
> **2026-09-22 追加 §24 尾段（PR #5220，CI 進行中；2026-10-14 註：09-22 已合併，在 rel、prod 還沒有）**：Jev 判級補了 **circuit breaker**（連續 3 次 timeout 後 30 秒零外呼、`jev.source=jev_circuit_open`）與 **assistant 回合進前文**（短回覆「ok go／yes」不再被判 SIMPLE）；guardrail 的 Jev 臂有自己的 breaker、對外仍 `classifier_timeout`。定址規則零變動。完整紀錄 `路由v2.md` §27.8。
> **2026-09-21 追加 §24（Jev——第三種難度判定 `jev_routing`；PRD-330 / ADR-472 / SPEC-294；#5145／#5146／#5149／#5151 全 merge `5f20bf7a1`，rel/prod 未部署（2026-10-14 註：程式已在 rel 與 prod 分支；prod 由 pre-release registry 的 `jev_routing`（stage=rel）扣住，rel 可用、prod 看不到）、真 key e2e 未做）**：「沒指定 model 時誰來挑」的第一軸（難度判定）從三選一變**四選一**：None／Complexity／LLM Judge／**Jev**（TypeSafe 的外部判斷服務，租戶自備 key）。憑證走 Credentials 頁的 `jev` provider → application configuration 的「Jev credential」下拉 → IAM validate 投影給 gateway；判級失敗一律退回 Complexity 的 heuristic、請求照樣 200、該結果不被 session 釘住。**這組控制只出現在 application configuration，proxy 頁沒有**（ADR-414）。完整紀錄 `路由v2.md` §27。
> **2026-09-16 追加 §23（外部引用地板——ADR-406 Amendment E / SPEC-264 Rev.10；#4924／#4922／#4931 全 merge，rel/prod 未部署（2026-10-14 註：已在 rel 與 prod 分支，prod = v1.76.4））**：ask 含檔案路徑／URL 的 complexity／judge app 分級至少 MEDIUM（per-app `external_reference_min_tier`，`SIMPLE`=關），路徑片段假命中消失；evidence 多 `cause=external_reference_floor` 與 `external_reference (path|url)` 訊號。完整紀錄 `路由v2.md` §26。
> **2026-09-15 追加 §22（tools × reasoning 撞 OpenAI 400 → ADR-455 Responses bridge + L1 降級；PR #4835（2026-10-14 註：09-15 已合併 `cff9151d4`，rel 與 prod 都有））**：OpenCode 對 proxy 第三句回 `Function tools with reasoning_effort are not supported for gpt-5.6-luna`——不是定址、不是 guardrail，是 OpenAI 對 gpt-5.4+ 在 chat 面拒「function tools × reasoning」這個**組合**；路由一落到 gpt-5.4+（MEDIUM 以上的帶）帶 tools 的 agent client 就必中。真元件 probe 定案 **gpt-5.5/5.6 預設開 reasoning、unset 照樣 400（關 `supports_reasoning` 救不了）；gpt-5.4 unset 為 200**。修法兩層：seam 五層閘事前 bridge 到 `/v1/responses`（credential 先以原 provider 解析再換 surface；tools 與 reasoning 都保住）+ `OpenAIWorker` 對 marker 400 以 `reasoning_effort="none"` 同模型重試一次。順帶接上 Responses worker 的 `reasoning:{effort}`、`reasoning_effort` 值域擴為 OpenAI 全集、chat manager 跳過 `_signal` chunk。**gateway image only、無 migration**；knob `XPARSE_RESPONSES_BRIDGE_FORCE_OFF`（預設不設）。
> **2026-09-02 追加 §11（ADR-430 PR-1a，PR #4070 已 merge `0e61be0b9`）**：「沒指定 model 時誰來挑」變成**兩軸**——`routing_strategy` 語意改為「難度判定」（值不變：`none`/`complexity_routing`/`llm_judge_routing`，決定合格集），新欄位 **`routing_objective`**（`quality`/`cost`/`latency`/`energy`，預設 `quality`）決定在合格集裡怎麼挑。objective 只掛 consumer app、proxy 頁不顯示；pin 仍勝過一切；failover 天然跟目標。PR-1a 只有 Quality 為真實作（逐位元同今天），其餘三個為暫行 fallback。§1 一句話、§2.1 步驟⑤、§2.4、§7、§9.4 已加註。**D28（2026-09-03，#4084 已 merge）**：Cost first 下未設價一律視為 0（含雲端），價格責任交給用戶。**PR-2 Cost 已交付（2026-09-03，PR #4092）**：真 cost pick、快照價格欄、proxy Models tab「套用公開定價」、application Models tab 的「價格」欄；Latency / Energy 仍暫行。**Console follow-ups（同日）**：#4098 價格欄常駐（不再只在 Cost first）、#4099 拆 `Model.tier` 欄只留分級欄（已 merge）、#4102 Smart Routing 面板 Quality first 不提供 None、None 說明依目標變（全池最便宜／最快／優先雲端）、Cost first 文案改為 D28 語意。細節在 `路由v2.md` **§16 / §16.9**。 **2026-09-04 追加**：四個目標實測全過（Cost 算式對到小數、Energy 三分支含 tp/vram 推導端到端、Latency 探索與同分帶皆對），但抓到 Latency 的 `avg_ttft_ms` 訊號層在 main 上是死的——PR-4a 的修復 commit 在 #4116 merge 後 7 分鐘才 push、從未進 main，而 ADR-320 / SPEC-276 / wiki 都已宣稱它修好了。reland = **#4158**（含修正那三處歸屬）。§11.4 FAQ 與 §16.19 有完整記錄。
> **2026-09-14 追加（不在定址鏈上，但操作者會撞到）**：OpenAI-SDK 形狀的 agent client（OpenCode）對 proxy 一句 `hi` 就 451／503——是 guardrail 不是定址。三個缺陷 + sidecar 第三個 timeout 常數修在 **#4806（ADR-448 Amendment E）／#4807（Amendment F）**，皆已 merge 並部署 dev；剩下的是 GLiNER 容量對長 system prompt（OpenCode 摺進 `AGENTS.md`）的冷啟動。見 §7「agent client…」段與 `guardrail.md`。
> **2026-09-10 追加 §21（Session Affinity，11 個 PR 全 merge；09-11 再加修正 PR #4612）**：「沒指定 model 時誰來挑」再加一軸——**同一個 client session 內，第一輪選中的模型之後就不再換**（閒置 1h 重挑），保住 provider prompt cache。開關在 consumer Application、**預設開**；不送 session id 的客戶端行為逐位元不變；pin 不受影響；**R3 failover 仍看完整池**。解析鏈七層（含 Application 自訂 header 與內容衍生 prefix）。migration 0318 + 0319。**推翻了 ADR-406 §2.1-7 / ADR-411 §4E 兩度的「v1 明文不做」**。**沒做的見 §21.3**：prod 未部署（2026-10-14 註：已在 prod 分支 v1.76.4，含 Amendment B）、A1/A3/A4 未跑 dev 真流量、**Codex 結構性不覆蓋（#4592）**。**交付後的 code review 又找出三個「測試全綠但 prod 行為不對」的缺口（§21.4，PR #4612 已 merge）**——L5 的 tools 前綴不穩定、store 的 Prometheus counter 從未註冊、failover 事件不帶 `user_agent`；follow-up **#4613** 補修被 #4612 改壞的診斷 SQL。完整紀錄 `路由v2.md` §24。 **09-13 Amendment B（§21.5）**：對照 LiteLLM 的第二次 review 修掉四個真缺口——Claude Code 首輪兩個請求搶同一把 key、failover 後 pin 不自癒、首輪探索被釘住、**Codex/Responses 面終於有 affinity（#4592）**；另加單向升級 knob。
> **2026-09-09 追加 §19（定價撰寫面重構——ADR-300 Amendment M，9 個 PR 全開、CI 全綠、待合併（2026-10-14 註：已全部合併；4 支 stacked 子 PR 的內容由 #4504／#4505 reland，之後 Amendment N 的 Console 由 #4520 reland，見 §19 尾段；rel、prod 都有））**：§18 只收了「入口」，這輪收「數字對不對」——快照帶 LiteLLM 每模型的 cache 價（openai 家族 cache read 猜值 0.5× → 真值 0.1×，5 倍高估修掉）、`cache_write` 改存絕對值（B2 `per_ttl[{ttl, flat}]`，migration **0311**——撰寫時是 0310，兩度被 main 搶號，見本節末「migration 撞號三連」）、`pricing` 進嚴格 schema、三個成本引擎對「缺 `cache_write`／`per_ttl: []`」統一為免費、`GET price-schedule` 回 `current_segment`＋`gaps[]`、新原子端點 `reprice-from`；Console Prices 區塊改成「現行價／缺口紅字一鍵修補／排程中／歷史」+ 四值主表單，套用公開價與 Register 一次帶四值。§18 的「mock 分支退場」follow-up 已在 #4468 做掉。合併序與部署序見 §19。
> **2026-09-08 追加**：「套用公開定價」入口自 proxy Models tab **移至 Model Pool**（`/models/{uuid}` Detail → Settings → Prices 單一模型按鈕 + Cloud Register Price 步驟預填；PRD-272 §3.5 INV-272-40、ADR-430 Amendment A）；proxy／application Models tab 價格改為只讀 + 連結；後端同 PR 拔除 `ApplicationModel.cost_per_*` 兩條寫入路徑與欄位（IAM 0308，ADR-300 Amendment L）。下文 §7／§11 提到的「proxy Models tab 的套用公開定價」為歷史。
>
> **2026-09-08 追加 §16（`/v1/responses` 收尾，PR #4391 已 merge `7f4cfa0c9`）**：盤點「還有什麼沒做」→ 主線全 merge（#4378 / #4385 已進 main），只剩兩個碼面缺口：output 端 guardrail block 的 `error.code` 改為 `output_blocked`（原不分 stage 落 `input_blocked`；chat 非串流 classifier output block 同修）、provider 自送 `response.failed` / `error` 的 audit 改記 `EXECUTION_FAILED(provider_response_failed)`（原記 `COMPLETED incomplete`，與 client 斷線無法區分）。wire 不變、只動 gateway。**dev 尚未吃到 #4378 / #4391**（主樹 `96fee004a`、gateway 容器早於 #4378），要 pull + recreate gateway。完整紀錄 `路由v2.md` **§22**。
>
> **2026-09-08 追加 §17（dev 直打 API 全矩陣驗證）**：不改碼、用外部探針程式對 dev 打真流量——chat 面 **3 種難度判定 × 4 個目標全部照契約**（含 judge × cost 疊加、keyword rule、帶內位移）、`/v1/responses` 治理對稱 31 案 + output/input block 7 案 + 真 `gpt-4.1-nano` 4 案全過（#4376 / #4378 / #4391 皆在 dev 真流量坐實；**§16 的「dev 未吃到」已過期**）。抓到 **1 個真 bug**（Latency first 第二訊號 `avg_latency_ms` 冷啟動從 0 起算 → 樣本最少的模型看起來最快）、**1 個資料面地雷**（`openai` 憑證綁 `openai_responses` 模型：寫入與探測都放行、validate 才 500）、**1 組規格漂移**（451 / 422 的 `error.type` 落 `internal_error`，SPEC-106 §3.3 對 HTTP 路徑不成立）。完整紀錄 `路由v2.md` **§23**。**同日收斂**：#4395 / #4398 / #4409 / #4400 / #4413 / #4415 五個修正 PR + #4417 / #4419 兩個文件 PR 全部 merge 並在 dev 驗過（§23.11–§23.15）；`/v1/messages` 兩軸 11 案全過（dev 旗標已開，prod 本來就開）。
> **2026-09-07 追加 §12.6（ADR-437 收尾，七 PR #4272→#4281 全 merge）**：`instructions` 轉發（#4249）、原生 graceful `response.incomplete`（#4250）、block 後 provider DELETE（#4251）、`param_*` audit + `record_actuals`（#4252）；**dev 已翻 enforce**、e2e probe 有真流量證據；抓到 buffer 模式漏字、`output_redaction_mode`/`block_presentation` 在 IAM spec 根本不存在（#4279 補）、`response.in_progress` 漏後端模型名。**Gateway 自 #4236 起在 `apps/gateway/bustream/`**。完整紀錄 `路由v2.md` **§18**。
> **2026-09-06 追加 §12（ADR-437 / SPEC-282 / PRD-157 §10，七 PR 全 merge）**：`/v1/responses` 的定址與 chat **對稱了**——opaque 首輪走同一條 resolver over Responses-surface 候選集（PR-1b 就是這裡）、續輪跟**綁定列**的模型（順帶修掉 ADR-415 重排後鏈 409）、指名真模型仍 PIN；同時接上 admission、output rail（`buffer` 可 enforce）、first-event 前 R1/R3 failover、`EXECUTION_*` audit，Policy Kernel shadow 事件終於落盤（14 個月從未寫進 audit）。`agent_mode` 在此面 400；semantic cache 只定規則（#4247）。enforce 翻轉為 ops-gated。
>
> **2026-08-31 同日追加 §10.7（Rev.9，PR #3926 docs / #3927 code）**：Peter 問「per-app 都做了，proxy 頁為什麼還留 Model Name Visibility？」——追下去發現 Rev.8 留開關的理由（ADR-312 direct mode）在**同週已被 ADR-414 掏空**（direct client 認證退場、僅剩 internal model ping 可達），而且開關唯一的實際效果是**弄壞 ping**（opaque proxy 的 Retest 在定址閘門必 400）。Rev.9：proxy 頁開關移除（欄位/API/預設/0291 全不變）+ INV-138-26 probe 豁免（兩條 validate 路徑對 `is_internal_health_probe_key()` 形狀解析 `select_available=true`）。§10.3 的「proxy 頁的開關保留」自此不成立。
>
> **2026-08-31 追加 §10**：`select_available` 的**所有權反轉**——由「綁定的 proxy 決定」改為「每個 application 自己那一列決定」（ADR-138 **Rev.8** / PRD-305 / SPEC-273，三 PR **全 merge**：`671b01e3d` / `a50c3672a` / `b0b5fc315`）。於是**綁同一個 proxy 的兩個 app 可以一個開、一個關**。§2.2 的三件職責、§4 的七條規則**全部不變**——變的只是「這個開關長在誰身上」。候選集合仍全歸 proxy。存量由 migration **0291** backfill 成當下生效值，部署對客戶端不可觀察。§8.1 那句「visibility 仍全歸 proxy」自此不成立（已原地更正）。
>
> **2026-08-29 追加 §9**：`GET /iam/applications/{app}/model-order` 每個 source 多兩個 additive 欄位 `complexity_tiers` / `complexity_band_offset`（該位置在 app **已儲存**策略下所屬的 Complexity 分級帶；策略非 Complexity／LLM Judge 則 null），app Models tab 多一欄「分級」；同時 ADR-406 的 tier→位置映射擴為「帶首錨定 + 帶內位移」（pool ≥ 5 顆才有差）。SPEC-268 Rev.1 / SPEC-264 Rev.8 / PR **#3835**（**已 merge**：`2808b2161`）。§8 端點與 Console 描述仍正確，§9 只講增量；完整機制在 `路由v2.md` §14。
>
> **2026-08-28 追加 §8**：後續三波變更的收束——① 路由值空間換血（ADR-406/411 + Twin 退場 #3783）：§2.1 步驟⑤與 §2.4 的「五模式」已成歷史，現行可寫值 = `none` / `complexity_routing` / `llm_judge_routing`（+`agent` marker）；② proxy client key 退場（ADR-414 / #3781）：client 打 proxy 池的唯一通路 = **consumer app key + active binding**；③ **per-app 模型排序（ADR-415 / PRD-297 / SPEC-268，本日交付四 PR #3787/#3788/#3789/#3791 全 merge + dev e2e）**：§2.1 步驟③與 §2.5 的「排序」自此是**該 app 的生效序**，proxy 池序只是未自訂 app 的預設。§1–§7 原文保留為 2026-08-21 當時現況，過時處有原地註記。
>
> **部署**：本文三波變更與 routing v2 共用同一批部署，完整清單、盤點 SQL 與「設定面零改動」的查證收在 `路由v2.md` **§15**。
> **2026-08-30 更新（ADR-414 Rev.2 / PR #3893）**：原本「migration 0285 撤銷所有 LLM Proxy client key＝cutover 當下呼叫方斷線」**已不成立**——0285 改為 migrate-then-revoke：live proxy client key 先自動 re-parent 到新建的 `api_consumer` app（繼承 proxy 原 `application_code`，proxy 改名 `<code>-proxy`；governance 姿態複製、active binding 自動建立），之後才撤銷 leftovers（expired、非 active proxy 上的 key）。**呼叫方零動作、零斷線**；APIKey 只存 hash + FK，換綁不需要客戶的明文 key。operator 工具：`manage.py migrate_llm_proxy_client_keys`（dry-run 盤點/事後補救/真 validate 驗證）。

| 欄位 | 值 |
|------|-----|
| 日期 | 2026-08-21 調查 + 實測 + 交付 · **2026-08-28 追加 §8（per-app 排序 + 值空間收束）** · **2026-08-29 追加 §9（model-order 分級欄位 + 帶內映射）** · **2026-08-31 追加 §10（visibility 所有權反轉為 per-app）** · **2026-09-02 追加 §11（Routing Objective 兩軸，ADR-430 PR-1a）** | · **2026-09-06 追加 §12（`/v1/responses` 治理對稱 Phase 2，ADR-437）** · **2026-09-07 追加 §12.6（ADR-437 收尾）* · **2026-09-15 追加 §22（tools × reasoning 撞 400 → ADR-455 bridge + 降級）** · **2026-09-16 §23** · **2026-09-21／22 §24** · **2026-10-14 追加（09-29 之後定址相關合併；rel／prod 狀態更正）** |
| 狀態 | **已交付並 merge（PR #3652，2026-08-21）**；§8 的 ADR-415 四 PR 亦已全 merge；§9 的 **PR #3835 亦已 merge**（`2808b2161`）；§10 的三 PR **#3920/#3921/#3922 亦已全 merge**（`671b01e3d`/`a50c3672a`/`b0b5fc315`） ；§11 的 **#4070 已 merge**（`0e61be0b9`）、D28 docs #4084/#4085 已 merge、**PR-2 #4092 已 merge**、Console follow-ups #4098/#4099/#4102 皆已 merge |；§12 的 **#4238 + #4239→#4246 七 PR 全 merge**（`f5b054a26` 為鏈尾，PR-1b 在其中；§22 的 **PR #4835**（2026-10-14 註：09-15 已合併 `cff9151d4`，rel 與 prod 都有）（gateway only） |
| 起因 | June 提問：「chat/completions 沒附 model 名，會用哪一顆？」→ 追出兩個對外契約破口 |
| 權威文件 | ADR-138 Rev.6（§2.7 + INV-138-21/22）· **Rev.8（§2.9 + INV-138-24/25，所有權）** · ADR-221（§2.2 修訂）· SPEC-171 §2.10 · **SPEC-273（per-app visibility 契約）** |
| 交付範圍 | 18 檔 · +767 / −205 · **無 migration** |
| 驗證 | seeded regression 兩次變紅 + dev 真 HTTP 三種 app 型態 + 策展套件 1546→1612 passed（零新增失敗） |

---

## 1. 這份文件回答什麼

一個客戶端打 `/v1/chat/completions` 到我們的 LLM Proxy，**到底會跑哪一顆模型**，以及這個決定由哪些設定共同組成。順帶記錄 2026-08-21 修掉的兩個破口。

如果你只想要一句話：**沒指定 model 就等於用 `application_code` 定址，然後由 `routing_strategy` 選（**2026-09-02 起**：由 `routing_strategy` 當難度判定定合格集、再由 `routing_objective` 在合格集裡挑，§11）；能不能指定 model 由 `select_available`（Console 上叫「Model Name Visibility」）單獨決定——而自 2026-08-31（Rev.8）起，這個開關屬於**每個 application 自己**，不是它綁的 proxy。**

> **2026-09-10 起這句要再加一個限定（§21）**：上面那套「誰來挑」**只在 session 的第一輪完整跑一次**。客戶端若送得出 session id（Claude Code、OpenCode 這類 agent 都送），同一個 session 之後的每一輪都沿用首輪那顆，難度判定與路由目標不再重新作用，直到閒置滿 1 小時或那顆模型離開池。不送 id 的客戶端不受影響；要關就關該 application 的「工作階段模型固定」。

---

## 2. 現在的機制（客戶端視角）

### 2.1 一個請求怎麼被解析到一顆模型

```
POST /v1/chat/completions  {"model": ?, "messages": [...]}
   ▼
① pydantic schema —— model 缺省時填 sentinel "bustream-default"
   （bustream/models/multimodal.py，欄位是 model: str 有預設值，所以省略不會 422）
   ▼
② 定址閘門 pre_execution._enforce_model_addressing（由上往下第一個命中就決定）
   ├─ key 沒有任何 bound model        → 不在此處理，交由 routing 層大聲失敗
   ├─ 是 default token（省略/sentinel/"default"）→ request.model = application_code
   ├─ 等於 application_code            → 原樣通過
   ├─ 是 pool 內某個 model_name
   │    ├─ select_available=true   → PIN（精確執行，見 2.2）
   │    └─ select_available=false  → 400 MODEL_TARGET_NOT_ALLOWED
   └─ 其他字串                      → 404 model_not_found
   ▼
③ 候選集排序 routing_adapter —— sorted by sort_order（所有策略的共同進場順序）
   （2026-08-28 起：wire 上的 sort_order 值 = 該 app 的生效索引——consumer 若在
    binding 上自訂了 model_order，IAM 在 validate 期已重編；gateway 這步照排即保序，§8）
   ▼
④ pin 裁切 pin_trimmed_models —— 若是 PIN，候選集裁成那一顆（策略無事可做）
   ▼
⑤ 選模型——**2026-09-02 起兩軸**（§11）：`routing_strategy`（難度判定，~~三值不變~~ **2026-09-21 起四值，＋`jev_routing`，§24**）定合格集，
   `routing_objective`（quality/cost/latency/energy）在合格集裡挑（2.4 的「五模式」與「三值」皆為歷史）
   ▼
⑥ 既有管線：Policy Kernel → Admission → Streaming → R3 failover → Audit
   （2026-09-06 起 `/v1/responses` 也走同一組：routing → Policy Kernel → admission → output rail → first-event 前 R1/R3 → EXECUTION_* audit，§12）
```

（2026-10-14 註：② 現在是 `gateway/model_addressing.py::decide_addressing`（#5783），chat／messages／responses 共用；前提檢查 `check_addressing_preconditions` 在可見性規則之前——沒綁任何模型 → 400、本面沒模型或指名的模型只在另一面 → 422（#5780）。④ 的 `pin_trimmed_models` 在 `route_resolution.py`，找不到 pin 時改回 422、不再放寬回全池。）

**關鍵認知**：省略 model **不是**一條獨立路徑，它在步驟 ② 被**改寫成 `application_code`**，之後與手寫 app_code 完全同路。這就是為什麼下面三種寫法行為一致。

### 2.2 Model Name Visibility 到底管什麼

Console 上這個開關對應後端的 `Application.select_available`。**它的名字只講了三件職責裡的第一件**：

> **所有權在 2026-08-31 改了（ADR-138 Rev.8 / PRD-305）**：這個開關現在**屬於每個 application 自己**，不再由綁定的 LLM Proxy 決定。
> 綁同一個 proxy 的兩個 app 可以一個開、一個關——內部團隊的 app 公布真名可 pin，賣給外部客戶的同池 app 維持 opaque。
> **候選模型集合仍然完全歸 proxy**（有哪些名字不變），改的只是「這個 app 對它的客戶端揭露多少」。
> Console 的開關因此回到 **Application 設定頁**；~~LLM Proxy 頁的開關仍在，但只影響「這個 proxy 以自己的金鑰被直接呼叫時」（ADR-312）~~ **← 同日 Rev.9 移除**（ADR-414 已把該路徑退場，見 §10.7）。
> 存量一律由 migration 0291 backfill 成當下的生效值，所以上線瞬間沒有任何 app 的行為改變。
> **查一個 app 露不露真名，看它自己那一列就好**——不必再追它綁了誰。完整記錄（含論證、migration 三規則、驗證證據、踩到的坑）見 **§10**。

| # | 職責 | 具體表現 |
|---|------|---------|
| 1 | **可見性** | `GET /v1/models` 列 `application_code` 還是每顆真實 model_name |
| 2 | **可定址性** | 客戶端**能不能**指定具體模型（關閉時指名 → 400） |
| 3 | **pin 語意** | 指定了算不算 PIN；PIN 後連 health failover 都不換（INV-138-16） |

第 2、3 項不在名字裡，是最容易誤解的地方。實測對照：

| | 關閉（opaque） | 開啟（menu） |
|---|---|---|
| `GET /v1/models` | 只列 app code | 列出每顆真名（2026-10-14 註：Rev.10／#4783 起先列 `application_code`、再列真名；會路由的 app 那筆 `owned_by="xparse-smart-routing"`） |
| 指定池內真名 | **400**，訊息指名 select_available 是那個旋鈕 | ✅ PIN，精確執行 |
| 指定不存在的名字 | 404 | 404 |
| `response.model` | 恆為 app code | 真名 |
| 省略 model | app code，**無** header | 真名 + `X-Xparse-Model-Default` header |
| PIN 後 failover | N/A | **不做**（客戶選的，換掉等於偷跑別的模型） |

**PIN 的代價要知道**：開啟 visibility 後，客戶端指定 `gpt-4`、`gpt-4` 掛了 → 直接失敗，不會救到 pool 裡其他模型。這是刻意的取捨（可用性換確定性），但 Console 的 tooltip 沒說。

> **預設值改了（ADR-138 Rev.7，2026-08-24）**：**新建的** LLM Proxy 現在**出生就是開啟**（`select_available=true`）。理由：proxy 存在的意義就是擁有一份值得對外公告的 model catalog，卻仍要操作者手動去翻一個開關。（Rev.7 當時的另一半理由是「proxy 是所有綁定 consumer 的 visibility 擁有者」——**該前提已被 Rev.8 推翻**，見上方 §2.2 的所有權說明；預設值本身不變。）
> **Rev.8（2026-08-31）續加**：新建的 **API consumer（`integration`）與 unbound（`application`）** 也預設開啟。**agent 系列刻意維持關閉**——`inference_target` 在 visible + 池內多顆 chat 模型時會**直接拒絕部署**（ADR-269 的 default-member 規則至今未實作），預設開啟等於讓新建的 OpenClaw／OpenCode／Open WebUI 掉進部署失敗。
> **既有 proxy 不受影響**——沒有 data migration，線上 proxy 的 `/v1/models` 與 `response.model` 逐位元不變；要開就照舊去 Console 翻。
> 適用範圍是三個 PRD-113 子型別（`llm_proxy_selfhost` / `llm_proxy_cloud` / `llm_proxy_existing`）。**legacy 的 `llm_proxy` type_code 刻意排除**——它是向後相容的 consumer code（`app_type="api"`），同時又是 `app_type_code` 的 column 預設，翻了會讓每個沒指定型別的 app 都變可見。
> **代價是上面那段 PIN 的代價變成預設姿態**：新 proxy 一出生就可被 pin，而 pin 過的模型不做 failover。

**兩個正交軸，別搞混**：`select_available` 管「誰能指定」，`routing_strategy` 管「沒指定時誰來挑」。實測驗證：`select_available` 在 `xparse_routing/` **零讀者**，只被 gateway 的 pin 判定讀 —— 所以關閉 visibility **不會**讓 smart routing 失效，開啟也**不會**繞過它（只有客戶端明確指名那條路被 pin 住）。

### 2.3 「沒給 model」有三種寫法，結果完全不同

這是最容易踩的地方：

| payload | 結果 | 原因 |
|---|---|---|
| **省略 `model` 鍵** | ✅ 200 | pydantic 填預設 `"bustream-default"` → default token |
| `"model": "default"` | ✅ 200 | 字面 `"default"` 也在 token 集合（大小寫不敏感） |
| `"model": null` | ❌ **400** `body -> model: Input should be a valid string` | 欄位型別是 `str` 非 `Optional[str]`，顯式 null 過不了 pydantic |
| `"model": ""` | ❌ **404** | 空字串是「提供了但無效」，刻意不當 token（ADR-138 Rev.3 N3） |

**而且「省略」這條路只有 raw HTTP 走得到。** OpenAI 官方規格裡 `model` 是必填（`openai-openapi` spec 的 `CreateChatCompletionRequest.required = ['model','messages']`），官方 Python SDK 在 **client 端**就強制：

```python
client.chat.completions.create(messages=[...])
# TypeError: Missing required arguments; Expected either ('messages' and 'model') ...
# ↑ HTTP 請求根本沒發出
```

所以：**Xparse 是 OpenAI 規格的寬鬆超集**，但用 SDK 的人唯一能寫的「不指定」是 `model="default"`。

> **實務建議**：程式裡別依賴「省略鍵」。寫 `"default"` 或直接寫 `application_code` —— 兩者在 raw HTTP 和 SDK 下都通，語意也是明示的而非靠預設值。

### 2.4 誰來挑：五個 routing 模式

> **⚠️ 本節為 2026-08-21 快照，值空間已於一週內兩度換血**：judged 三值（`llm_judge`/`energy_first`/`cost_first`）隨 ADR-406 退場（8/24，migration 0268 改寫存量）；`smart_routing`（Twin）隨 #3783 退場（migration 0284）；ADR-411 新增 `llm_judge_routing`（判請求 tier，與舊 `llm_judge` 判模型是不同 wire 值不同機制）。**現行可寫值 = `none` / `complexity_routing` / `llm_judge_routing`**（+`agent` marker，marketplace 專用）。下表與下方 Twin 段落保留為歷史紀錄。而且自 ADR-415（§8）起，**routing_strategy 與它消費的排序都在 consumer Application 上**——不再是「proxy 的設定」。 **2026-09-02 再更新（ADR-430）**：`routing_strategy` 不再是「誰來挑」的完整答案——它改稱**難度判定**、只決定合格集（`none` = 全池；complexity / judge = 該 tier 帶尾以上全部）；「怎麼挑」由新欄位 **`routing_objective`** 決定（Quality = 今天的落點、Cost = 最便宜、Latency = 最快、Energy = 雲端優先），見 §11。

改寫成 app_code 之後（或客戶端本來就用 app_code），由 `routing_strategy` 決定：

| API 值 | Console 顯示 | 挑選規則 |
|--------|------------|---------|
| `none` | None | pool 序首（`sort_order=0`） |
| `smart_routing` | **Twin** | 快慢分流啟發式（預設值，靠 `tier == "lightweight"` 分組） |
| `llm_judge` | **Default** | judge 逐請求判 → eligible 集**序首** → 空則 argmax → 無判決退 `pool[0]` |
| `energy_first` | Energy first | judge × **地端**子集優先，空了 fallback 雲端 |
| `cost_first` | Cost first | 鏡像：**雲端**子集優先、地端 fallback |

而 `select_available=true` 的 menu app，客戶端沒指定時同樣走上表；只有明確指名才 PIN。

> **Console 上這五個模式不在同一個控制項裡**（2026-08-24 起）：`none` / `llm_judge` / `cost_first` / `energy_first` 在「Routing Strategy」下拉，**`smart_routing`（Twin）是與它同層的獨立開關**——Twin 是本地快慢分流啟發式，不是 judge 型分派演算法。後端仍是**單一 enum 欄位**，所以兩者互斥：Twin 開 → 存 `smart_routing`、下拉 disabled 顯示「Managed by Twin」；Twin 關 → 落 `none`。**客戶端視角零變化**，這一格純粹是操作者介面的呈現。

### 2.5 `sort_order` 與 Console 的拖拉排序

Console 的 Model tab 有 drag-and-drop（`models/models-tab.tsx`，原生 HTML5 draggable + grip 握把，另有 dropdown 的 move up/down）。它寫的是 `PATCH /iam/applications/{uuid}/model-sources/reorder`，後端在 `transaction.atomic()` 內把 active 成員重編號成 `0..n-1`，並驗證送來的 order **剛好等於** active 成員集合（漏一個或多一個都拒 —— no implicit drop）。

**它的影響比「顯示順序」大得多**，因為 `sort_order` 是三條執行路徑的共同輸入：

1. **誰先跑** —— `routing_adapter` 在進入**任何**策略之前就先按 `sort_order` 排好候選集。`none` 直接取序首；`llm_judge` 判決平手時也退回序首。
2. **failover 降級路徑** —— `fallback_handler`（ADR-353 cascade）排除已失敗的模型後，取「next unseen model in `sort_order`」。所以拖拉同時在定義「第一顆掛了換誰、再掛了換誰」。
3. **Responses API 的預設** —— ~~同樣取 lowest `sort_order`~~ **2026-09-06 起（ADR-437 PR-3 #4241）**：opaque 首輪走**同一條 resolver**（`none`+`quality` 才等於序首）、續輪跟綁定列的模型、指名真模型仍 PIN；R3 failover 也沿同一生效序（§12）。

**所以 `sort_order` 是最終的兜底排序，而 Console 上的拖拉順序就是它。**

> **2026-08-28 兩層更新**：① ADR-406 把排序語意升級為**強弱序（第一顆＝最強）**，complexity/judge 的 tier→模型映射直接吃它；② ADR-415 之後上面這句要精確化為「**proxy 的拖拉順序是未自訂 app 的預設序**」——每個 consumer app 可在自己的 Models tab 拖出**自己的生效序**（存 binding 的 `model_order`），三條執行路徑（誰先跑／failover 降級／Responses 預設）自此全部按**該 app 的**生效序走。詳見 §8。③ **2026-08-29 ADR-406 Amendment C**：complexity/judge 的 tier→位置映射從「一級一個位置」擴為「一級一段位置（帶）」——pool ≥ 5 顆時同一級裡分數低的請求往帶尾走，原本永遠選不到的位置開始吃流量；每個位置屬於哪一級現在直接顯示在 app 的 Models tab。詳見 §9。

UI 護欄（設計得對，值得知道）：只有握住握把才可拖（整列其他區域仍可選取）；**搜尋／欄位篩選／日期排序時停用拖拉**（reorder 只在完整未篩選清單上才連貫）；optimistic 更新、失敗 snap back；`list_sources` 用 `(sort_order, model__model_uuid)` **total ordering**，避免 `sort_order` 撞號時列在相同請求間互換（ADR-358 INV-358-5）。

> **實測附註**：dev DB 確實有兩個 proxy 的 active 成員 `sort_order` 撞號（`adr397_e2e` 兩顆都 `0`、`seed-eng-llm-proxy` 兩顆都 `2`）。因為有上面那個 tie-break，行為仍然確定（按 model_uuid 字典序），只代表這些 pool 從沒被拖過 —— 拖一次就會正規化成 `0..n-1`。

---

## 3. 這次改了什麼（ADR-138 Rev.6 / PR #3652）

### 3.1 兩個破口

Rev.3 宣告 `select_available` 是「visibility **AND** addressability 的唯一權威」（INV-138-12），但閘門是**有條件**地執行這個權威：

```python
if not select_available and len(bound_names) > 1:   # ← 逃生門
```

所以 opaque **單模型** app 的守衛從來沒跑過。dev 真 HTTP 實測（app `test`，`select_available=false`，pool `[gpt-4o]`）：

| Probe | 修之前 | 矛盾在哪 |
|---|---|---|
| `GET /v1/models` | `["test"]` | —（正確：opaque） |
| `{"model": "gpt-4o"}` | **200，執行成功** | 清單藏起來的名字卻可定址 —— 違反 INV-138-12 |
| `{}`（省略） | `response.model == "gpt-4o"` | opaque app 回真名 —— 違反 **ADR-221 INV-221-2** |

**最麻煩的後果不是任一破口本身，而是對外契約隨 pool 大小翻轉。** 客戶端指名 `gpt-4o` 在 pool 1 顆時回 200，操作者在 Console 加了第二顆模型後、同一個呼叫變 400；`response.model` 也在同一個門檻從真名變成 app code。**客戶端什麼都沒改，破壞性變更由操作者的 pool 編輯觸發。**

另外 `model_request_policy = route_by_strategy` 這一格：opaque app **接受**客戶端指名，然後執行**另一顆**（發 `X-Xparse-Model-Substituted` header）。它在窄義上符合 ADR-093 inv-4（可觀測、非靜默），但它和它所屬的規則直接矛盾 —— `select_available=false` 本該意味著客戶端根本不能指定模型。

### 3.2 為什麼綠燈那麼久（這段值得單獨記住）

**① 兩個測試各自鎖住矛盾的兩半，而沒有測試比對它們。**
`test_single_model_opaque_app_stays_opaque` 鎖「`/v1/models` 隱藏真名」，`test_single_model_real_name_also_resolves` 鎖「真名可定址」—— 兩個都綠、兩個都是刻意寫的、互相矛盾，而**沒有任何測試把它們放在一起看**。

**② ADR-221 的斷言比它自己的 invariant 寬。**
INV-221-1/2 規定 opaque app 的 `response.model` 必須是 `application_code`，但 enforcement 欄寫的是 `value ∈ bound set ∪ {application_code}` —— 而洩漏出去的真名**本身就是 `bound` 的成員**，所以斷言永遠通過。**斷言比 invariant 寬，等於沒 enforce。**

**③ 順帶發現：`SPEC-171 SELECT-04` 點名的測試根本不存在。**
`test_auto_specific_model_route_by_strategy_transparent` 在 repo 裡找不到 —— 那條契約整個生命週期都沒被驗證過。引用 SPEC 的測試名前先 grep 它在不在。

### 3.3 改動與三個決策

June 拍板：① `route_by_strategy` → gateway 一律當 strict；② `response.model` → 改回 app_code；③ 直接改，不特別公告（視為 bug fix）。

實作：

1. **移除 `len(bound_names) > 1` 條件**（`pre_execution.py` 與 `routes/responses.py` 兩份平行閘門）。隱藏的名字在**每一種 pool 大小**下都 400。
2. **`application_code` stand-in 無條件化** —— 取代 `#367` 的單模型正規化。只在 app **沒有** `application_code` 時才退回單一真名，避免 `bustream-default` sentinel 流進 `response.model`／audit（INV-221-3）。
3. **不再改寫明確的 `application_code` 請求**（原本也會被換成真名 —— 同一個 INV-221-2 違反）。
4. **`route_by_strategy` gateway 側退役**：`is_route_by_strategy_named()` 恆回 `False`，讓 chat/responses 路由裡的 substitution seam **自然死掉而不必在同一個改動裡拔掉**。IAM 欄位／enum／migration 0129 保留為 deprecated，`choices`/`help_text` **刻意不動**所以 Django model state 未變、**無需 migration**。

不受影響的：routing（策略讀 `auth_context.models`，worker 打 provider 用 `assignment.model_name`，都不看 `request.model`）；menu app（`resolve_model_default()` 仍把 `response.model` 換成執行模型並發 header）。

**Responses surface 不需要等價修正** —— `ResponsesCreateRequest.model` 是 `model: str` 必填無預設，沒有「省略」路徑，`response.model` 永遠回客戶端送的值（2026-10-14 註：ADR-221 Amendment B／#6161 起此句只對 opaque app（回 `application_code`）與 pin（回自己指名的名字）成立；menu app 用 app code 或 default 定址時，每個事件寫實際跑的模型，R3 後寫替代模型。例外見 SPEC-312 C-312-39：`X-Xparse-Model-Default` header 在串流開始前就算好，R3 後仍是 primary；第一個事件前就失敗、gateway 自己合成的 envelope 沿用請求的 `model`。目前在 rel，prod 還沒有）。已在該處加註解，避免將來有人把欄位改成 optional 而無聲洩露。

新增 **INV-138-21**（可見性 ⇔ 可定址性**雙向**一致、且不得依賴 pool 大小）與 **INV-138-22**（opaque 的 `response.model` 恆為 app code），斷言用**等值**而非集合成員。

### 3.4 驗證（§8.1 紀律）

單元測試本身無法建立信心 —— 因為改動前的套件**帶著這兩個 bug 是全綠的**。

**先 seed 迴歸再信任 gate**：兩個破口分別加回去，看新測試變紅，然後 byte-identical 還原。

| Seed | 結果 |
|---|---|
| 把 `len(bound_names) > 1` 逃生門加回 | **5 紅** |
| 把單模型正規化改回真名 | **4 紅** |

`test_binding_a_second_model_does_not_change_the_client_contract` **兩個 seed 都攔下來** —— 那條最有價值。

**然後 dev 真 HTTP**（造 probe key，測完全部 revoke）：

| App | 型態 | 前 → 後 |
|---|---|---|
| `test` | opaque, pool 1 | 指名 `gpt-4o`：`200` → **`400`**；省略的 `response.model`：`gpt-4o` → **`test`** |
| `adr397_e2e` | opaque, pool 2 | **不變**（`/v1/models`=`["adr397_e2e"]`、指名 400、省略回 app code） |
| `1123123` | menu, pool 2 | **不變**（列真名、指名 PIN、未知 404） |

**策展套件**：`1546 → 1612 passed`，失敗數與改動前 baseline **完全相同**（11 failed / 25 errors，用 stash 比對過）—— 零新增失敗。CI 全綠。

---

## 4. 七條規則 vs 現況（全部成立）

June 定下的規則，逐條實測對照：

| 規則 | 現況 | |
|---|---|---|
| 1. Visibility 關 → 不讓指定 | 一律 400，每種 pool 大小、每種 tenant policy | ✅ 本次修好 |
| 2. 關 + 沒設 strategy → order 第一顆 | `none` 取序首 | ✅ |
| 3. Visibility **不**影響 smart routing 可用性 | `select_available` 在 `xparse_routing/` 零讀者 | ✅ 已加測試鎖住 |
| 4. 指定 + Visibility 開 → 用那顆 | `pin_trimmed_models` 裁成一顆 | ✅ |
| 5. 沒指定 → order 第一顆（不管 Visibility） | 見下方解讀 | ✅ |
| 6. 有指定 → 不用 smart routing | 裁成一顆後策略無事可做、judge 跳過、failover 停 | ✅ |
| 7. 沒指定 + 有 strategy → 用 strategy | ✅ | ✅ |

> **Rev.8（2026-08-31）對這七條的影響：零。** 七條講的是「visibility 開或關時的行為」，Rev.8 改的是「這個開關長在誰身上」——每一條的判定對象從「該 app 綁的 proxy 的旗標」變成「該 app 自己的旗標」，行為逐條不變。唯一的新事實是：**同一個 proxy 底下的兩個 app 可以各自落在不同的規則上**（A 走規則 4、B 走規則 1），這在 Rev.8 之前表達不出來。

> **規則 5 的解讀**：「沒指定 model → order 第一顆」隱含前提是「**且沒設 strategy**」，與規則 7 互補；「不管 Visibility 開或關」是針對 visibility 而非 strategy。若照字面讀成「沒指定 model 一律取第一顆、即使設了 strategy」，`routing_strategy` 將永遠不會被觸發（它只在沒指定 model 時才有機會），整個路由層失效 —— 故採前者。

---

## 5. 過程中踩到的坑（時序）

1. **tenant_admin key 不能 inference** —— 拿它打 `/v1/chat/completions` 回 403 `tenant_admin keys cannot be used for inference`。要 application-scoped key。
2. **suspended app 顯示為 `401 Invalid API key`** —— app `q` 是 suspended，key 造得出來、DB 裡是 active，但 gateway 回「Invalid API key」。真正原因（`Application is suspended`）只在 IAM 的 `/iam/internal/gateway-validate` 看得到。**debug 時會被帶去查 key，而問題在 app 狀態。**
3. **IAM internal 端點的 base path 不含 `/apis`** —— 是 `http://xparse-iam:8010/iam/internal/gateway-validate`（打 `/apis/...` 會 404）。它 `auth=None`（同 Docker 網路信任），假 key 也回 200 但 body 帶 `valid: false`。
4. **回歸基準選錯對象** —— 我第一次拿 `gpt_4o_816e` 當 opaque 多模型基準，但它的 `select_available` 在對話期間（今天 03:30:49）被改成 True，所以行為「變了」其實是設定變了。改用 `adr397_e2e`。**跨 session 的 dev 環境會被別人動，基準要即時查 DB 確認。**
5. **未被 gate 的測試檔看不見** —— `tests/contract/test_request_params_fail_fast.py` 不在 `tests/gateway-ci-suite.txt`，所以它受影響的 7 個測試在「策展清單 baseline 比對」裡完全隱形，要單獨跑才發現。**改行為契約後，除了策展清單也要 `grep -rln <關鍵字> tests/` 把未 gate 的相關檔一併跑過。**
6. **fixture 依賴了被修掉的行為** —— 有兩個測 `stop` 參數的測試，fixture 恰好是「opaque 單模型 + 指定真名」，改動後變 400。不是迴歸，是 fixture 借用了那個破口，改成 `select_available=True` 就回到測 stop 的本意。
7. **pytest-django plugin 讓 collection 整批爆掉** —— 本機缺 `django_celery_beat`，要 `-p no:django -o addopts=''` 才跑得動 gateway 測試。而多路徑要用 `xargs` 餵給 pytest（zsh 不做 word splitting，存變數傳會靜默收集 0 個）。
8. **改 Django model 的 `choices`/`help_text` 會需要 migration** —— 那是 model state。要標 deprecated 又不想生 migration，就只能用 `#` 註解。

---

## 6. 現在還沒解決的

| # | 事項 | 性質 |
|---|------|------|
| 1 | `X-Xparse-Model-Substituted` / `resolve_model_substitution` / IAM 的 `model_request_policy` 欄位是**死碼** | 刻意留給後續 cleanup PR（不在改定址契約的同一個 PR 裡拔） |
| 2 | Console 開關的**命名** —— 叫「Model Name Visibility」但實際管三件事 | 建議改成描述定址方式的二選一（單一端點 / 開放清單）；未動 |
| 3 | ~~開啟 visibility 會**關掉 failover**，UI 完全沒說~~ | ✅ **Rev.8 修掉（#3922）**：tooltip 補上「被指定的模型不會自動轉移——它無法使用時該次請求直接失敗，不會改用池中其他模型」。這在 `integration`/`application` 新建預設為開之後尤其必要 |
| 4 | ~~`models-tab.tsx` 的 **cost_first unpriced 警告已過時**~~ | ✅ **PR-2 #4092 拆掉**（`cost_first` 值已隨 0268 退場；現在的 D28 揭露 Alert 只在 `routing_objective=cost` 下出現，`src/` 只剩 `services/iam.ts` 兩行註解提到 `cost_first`） |
| 5 | suspended app 的錯誤訊息誤導（見 §5.2） | 值得開 issue |
| 6 | `SPEC-171 SELECT-04` 曾點名不存在的測試 | 已改指向真測試；但同型問題可能散落在其他 SPEC |
| 7 | `test_request_params_fail_fast.py` 未被 gate，且有 1 個既有紅 | 所以這次沒把它加進 gate 清單（加了 CI 會紅） |
| 8 | wiki 未同步 | 待確認要動哪幾頁 |

---

## 7. 給操作者的實務指引

**要讓客戶端能指定模型** → 開 Console 的 Model Name Visibility。**2026-08-31（Rev.8）起這個開關在該 application 自己的 configuration 頁**（~~proxy 頁那個只管 proxy 被直接呼叫時~~ 同日 Rev.9 起 proxy 頁已無此開關，§10.7）。代價：該客戶端 pin 的模型掛了不會 failover——這句現在 tooltip 上也寫了。

**要保留換供應商的彈性、不讓客戶知道你用誰** → 關閉它。**注意 2026-08-24 起新建的 proxy 預設是開的**（ADR-138 Rev.7），**2026-08-31 起新建的 API consumer／unbound app 也是**（Rev.8），所以這條現在是一個要主動去做的動作，不再是「什麼都不做就有」。**而且要關在那個 app 自己身上**——關掉 proxy 的開關不會讓綁定它的 app 變 opaque（Rev.8 起兩者各自獨立）。關掉之後客戶只能用 `application_code`（或省略 model）定址，`response.model` 永遠回 app code，你在背後加減模型、換順序，客戶端零感知。

**要改「沒指定時跑哪顆」** → （2026-08-28 起分兩層）改**全體未自訂 app 的預設**：拖 proxy Models tab 的池排序；改**某一個 app 自己的**：拖該 app detail 新的 Models tab（見 §8.3——這才是影響該 app 路由/failover/預設的生效序，且不波及共用同一 proxy 的其他 app）。兩處的搜尋／篩選狀態下拖拉都會被停用。

**在 Console 上找不到 Twin** → ~~它是同層的獨立開關~~ **Twin 已於 2026-08-27 整個退場**（#3783，migration 0284 把存量 `smart_routing` 改寫為 `none`）。現在 Smart Routing 開關打開後的策略下拉只有 Complexity 與 LLM Judge 兩項（**2026-09-21 起多一項 Jev，§24**），而且這組控制**只出現在 application 的 configuration**（proxy 端的 Smart Routing 區塊不顯示；2026-10-14 註：`SMART_ROUTING_HIDDEN` 已於 #4896 退場，現在看 IAM 回的 `supports_routing_strategy`，proxy 一律 false）。 **2026-09-02 再更新**：開關打開後是兩層——「路由目標」四選一 + 「難度判定」三選一（None 也在列；**2026-09-21 起四選一：＋Jev，§24**）；開關由兩欄儲存值推導（Quality first + None = 關）。Latency Preference 那個死控制項（選了亮 Save、存了沒事）同批拆除。

**要選路由目標（Quality / Cost / Latency / Energy first）** → （2026-09-02 起）打開該 application configuration 的 Smart Routing，第一格「路由目標」四選一、第二格「難度判定」三選一（None 也在列——Cost first + None 就是「全池最便宜」；**2026-09-21 起四選一：＋Jev，§24**）。開關由兩個儲存值推導：關 = Quality first + None；開啟時預設帶出 Quality first + Complexity。選 Latency / Energy 的實際行為**仍**等於 Quality（audit `selection_reason` 記 `no_*_data_fallback`），真 picker 在 PR-3/4（**尚未做**）（2026-10-14 註：已過時——Latency #4116／#4149／#4158、Energy #4155 於 09-03～04 合併，四個目標皆為真實作，rel 與 prod 分支都有；見 §11.5 #2）；**Cost 自 PR-2（#4092，2026-09-03）起為真實作**：合格集內有效成本最低者勝，audit 記 `cost_min` 或 `cost_unpriced_assumed_zero`。**Cost first 的價格責任在你（D28）**：沒設價的模型（含雲端）一律當 0 元、會被優先選到——想讓地端優先就給雲端設價或按「套用公開定價」（#4092；**2026-09-08 起入口在 Model Pool `/models/{uuid}` → Settings → Prices，proxy Models tab 只讀 + 連結**）。proxy 的 configuration 頁沒有這組控制（ADR-414：proxy 無路由效果）。

**改完設定要驗證** → gateway 的 validate snapshot 有快取（SPEC-155），改完**立刻**打 chat 會吃到舊 snapshot。要 `docker restart xparse-gateway` 或等 TTL。這個坑在 ADR-397 的 dev e2e 期間踩過兩次。

**agent client（OpenCode／Claude Code 這類 OpenAI-SDK 形狀）打進 proxy 被 451 `input_blocked`／`pii`，同一把 key 送純字串卻正常** → 不是定址問題，是 guardrail：多 part 的 user turn（`content` 是 parts 陣列）在 ADR-448 Amendment E（PR #4806，2026-09-14）之前遮罩寫不回去、fail-closed 成 451；Amendment E 起純文字 parts 可改寫，只有夾圖的 list 才 451。若看到的是 **503 `guardrail_timeout`** 加 client 自動重試，是 per-call timeout（Amendment E 前 5 s）先於掃描預算觸發，同一個 PR 修；若是 **503 `guardrail_service_unavailable`**（`engine_error`），是 sidecar 對 GLiNER 自己的 15 s timeout 先放棄，修在 **#4807（Amendment F）**：gateway 把剩餘預算以 `timeout_ms` 帶給 sidecar。兩個都部署後若**仍** 503 `engine_timeout`，那是容量：OpenCode 在 repo 目錄會把 `AGENTS.md`（36k 字）摺進 system prompt，CPU GLiNER 高載 ~1.3k 字/s、30 s 預算掃不完那一則，而 timeout 刻意不進快取所以永遠暖不起來——dev `.env` 暫把 `XPARSE_PII_SCAN_BUDGET_MS` 拉到 120000（首輪 40–60 s，之後命中快取）。細節見 `guardrail.md` §2.5／§3.6 與 `docs/issues/agent_llmproxy.md` §9a。

**opaque app 想知道真的跑了哪顆** → response 上看不到（那是刻意的）。查 audit：

```sql
-- trace_id = HTTP 回應的 x-request-id 去掉連字號
SELECT event->'payload' FROM audit_events
WHERE trace_id = '<x-request-id 去掉 ->' 
  AND event_type = 'audit.governance.routing_decision_recorded';
-- 看 winner_model_id / selection_reason / judge_verdict_summary
```

**judge 模式沒效果的常見原因** → ~~（舊 `llm_judge`，已隨 ADR-406 退場）~~ 現行 `llm_judge_routing`（ADR-411）判的是**請求難度 tier**、不判模型，之後照排序做 tier→position 映射——所以「沒效果」最常見的原因變成**排序沒排出強弱**：第一顆＝最強是映射的唯一模型側輸入（複雜題送序首、簡單題送序尾），全池亂排等於亂分。judge 自己預設是**該 app 生效序的最後一顆**（最弱），可在 app configuration 的 judge 選擇器改 pin（2026-08-28 起 consumer app 的 pin 才真的存得進去——之前後端驗證有 bug 必 400，§8.2）。

---

## 8. 後續 campaign：Per-Application 模型排序（ADR-415 / PRD-297 / SPEC-268，2026-08-28）

> 獨立完整交接。Peter 五題拍板（UI 放新 Models tab／judge picker 一起接／池新成員落尾端／未自訂＝動態跟隨池序／app 端只顯示 active 成員）。四 PR 當日全 merge 並逐一 `merge-base --is-ancestor` 驗證：**#3787** docs → **#3788** IAM backend → **#3789** Console hook 抽取 → **#3791** app Models tab + judge picker。dev e2e 全綠。

### 8.1 這是什麼、為什麼

ADR-198 讓 `routing_strategy` 歸 consumer app，但它消費的**排序**一直是 proxy 池屬性、全體 consumer 共用——任何一個 app 在 proxy Models tab 拖排序（或套 PRD-292 建議排序），兄弟 app 的路由、failover 降級序、omit-default 預設模型**同時被改且無訊號**。ADR-406 之後排序又升級成強弱真相（分級映射的唯一模型側輸入），矛盾放大。

修法：`ApplicationProxyBinding` 加 nullable JSON 欄位 **`model_order`**（migration **0286**）。NULL＝動態跟隨池序（存量 100% 零擾動）；自訂後脫鉤——池新成員落到該 app 生效序尾端、成員 pause→resume 位置存活、切換 active proxy 時各 binding 的 overlay 各自休眠/恢復。**candidate 集合與 membership 仍全歸 proxy**——ADR-415 當時 app 只擁有「序」。（~~visibility（select_available）亦歸 proxy~~ —— **2026-08-31 的 ADR-138 Rev.8 把 visibility 也移給 app 了**，見 §10；ADR-415 原文那句「catalog properties（names, visibility, addressability, pinnability）stay proxy-owned」已同步修訂為只剩 names/membership。）

**機制關鍵（零 gateway 改動）**：IAM 在 validate 期解析生效序，並把 models[] 每個 entry 的 `sort_order` **重編為生效索引 0..n-1**。§2.1 步驟③的 gateway 邊界重排是「按值排」——重編後它照排即保序，於是 `none` 序首、complexity position、judge auto=序尾、R3 failover、Responses 預設**全部自動變成 per-app**，bustream 一行未改。同週 ADR-414 把 proxy client key 退場後，direct 分支只剩 internal health probe 可達，overlay 明文不作用於該分支（INV-415-3）。

### 8.2 端點與順帶修掉的 bug

```
GET    /iam/applications/{app}/model-order   → {proxy_uuid, proxy_name, customized, sources[依生效序]}
                                               無 active binding = 200 + null/[]（不是 404）
                                               2026-08-29 起每個 source 另帶 complexity_tiers / complexity_band_offset（§9）
PUT    /iam/applications/{app}/model-order   body {proxy_uuid, order[]}
       驗證鏈：uuid 正規化(400) → 無重複(400) → 恰覆蓋 active 成員集(400 帶 missing/extra)
       → body 的 proxy_uuid 必須 = 當下 active binding（409，堵「拖到一半有人切 proxy」競態）
       寫後 re-read + audit APP_MODEL_ORDER_SET + push application-scope validate-cache 逐出
DELETE /iam/applications/{app}/model-order   → 重設 NULL（冪等）；audit APP_MODEL_ORDER_RESET + 逐出
```

**順帶修掉的既有 bug（SPEC-266 Rev.3）**：consumer app 的 judge pin 後端驗證原本查 `app.proxy_model_sources`——那是 proxy 側 FK，consumer 恆空集 → **任何 consumer 端 pin 必 400 `JUDGE_NOT_IN_POOL`**（PRD-295 的手動 pin 對 consumer 形同虛設）。修法 `_resolve_judge_pool_owner`：consumer 的池 = active binding 的 proxy 池。

### 8.3 Console

- **Application detail 新「Models」tab**（tab value=`model-order`，因 `models` 被 Proxy tab 佔用）：active proxy 池依**該 app 生效序**、「已自訂／跟隨 Proxy 順序」badge、拖拉＋move up/down（抽出的 `useDragReorder` hook，與 proxy 端共用同一套 optimistic/snap-back 機制）、「建議排序」dialog 原樣重用（套用改走 per-app PUT）、「恢復跟隨 Proxy 順序」確認後 DELETE。**無**加/刪/pause——membership 仍在 proxy 的 Models tab。
- **Judge picker 接進 app configuration**：選項 = active binding 之 proxy 的 active 成員；`use-configuration-form` 零改動（judge 狀態/送出本來就 app-ready，只是沒人餵池）。
- i18n 詞條（glossary 已登記）：跟隨 Proxy 順序／已自訂／恢復跟隨 Proxy 順序；「模型排序」≠「建議排序」（後者專指 PRD-292 的能力草稿）。

### 8.4 dev e2e 證據（2026-08-28，proxy `gpt_4o_816e`，池序 luna → 5.5 → 4o → 4）

| # | 情境 | 結果 |
|---|------|------|
| I1 | 同池兩 consumer app：A 未自訂、B PUT 反轉序；各發 omit-default `"hi"` | **A → `gpt-5.6-luna`（池序首）、B → `gpt-4`（B 序首）**——同一 proxy 兩種路由 |
| A5 | DELETE B 排序（冪等重打也 200）後再發 | B 收斂回 `gpt-5.6-luna` |
| A3/A4 | missing/extra/dup/壞 uuid → 400 帶 `MODEL_ORDER_*` 碼；錯 proxy_uuid → 409 | ✅ 全過 |
| A6 | consumer pin 池成員 → **200**（修復前必 400）；非成員 → 400 `JUDGE_NOT_IN_POOL` | ✅ |
| A7 | 未綁定 app：GET 200 空、PUT/DELETE 409 | ✅ |

測試面：IAM 全套件 2405 passed、18 failed **與 main 基準集合逐條一致**（零新紅）；`test_spec268_model_order.py` 30 條真 ORM＋真 resolver；Console 711 passed＋全 i18n gate 綠。

### 8.5 e2e 踩到的坑（下次省時間）

1. **典型 create 是 group 端點**：`POST /iam/groups/{group}/applications` 只吃 `{name}`；`POST /iam/applications` 是 legacy 全參數版（缺 tenant_uuid 等直接 422）。
2. **新 consumer app 打雲端模型會 403 `APPLICATION_PROFILE_IMMUTABLE`**（typed create 預設 profile 非 hybrid）→ PUT `profile_type=hybrid` 後**必須重 mint key**——舊 key 會變 403 `KEY_BOUNDARY_MISMATCH`（key 在 mint 當下繼承 app profile）。**2026-09-22 註**：這條只對 **consumer app** 成立；proxy 列的 `profile_type` 自 #5233 起惰性（probe 投影 `hybrid`），Retest 不會再被 proxy 的 profile 擋。
3. **app update 是 `PUT /iam/applications/{uuid}`**（PATCH 405）。
4. **寫後 cache 逐出在 dev 與 prod 都打不到**（**2026-08-29 更正：原文寫「prod 不受影響」是錯的**）：`evict_scope_from_gateway` 預設目標 `http://xparse-scr:8000/v1`（`authorization/gateway_cache_evict.py:32`）。dev 的 gateway 叫 `xparse-gateway`；**prod 同樣解不到 `xparse-scr`**——`install_service/tiers/docker-compose.pro.yml` 裡沒有任何 container 叫 `xparse-scr`，該 alias 只掛在 `agent-network`（:221，給 NemoClaw 用），而 `xparse-iam` 只加入 `xparse-network`（:456-457），該網路上的 alias 是 `xparse-gateway`（:217）。逐出因此每次 fail-open 靜默失敗（INV-372-7 的設計，不會壞資料），代價是 per-app 排序／budget flip 從「即時生效」退成「等 ≤30s passive TTL」。**修法**：給 IAM 設 `XPARSE_GATEWAY_INTERNAL_URL=http://xparse-gateway:8000/v1`——traffic router 是 L4 stream proxy（`configs/nginx/nginx-traffic.conf:18` 整條 TCP 轉發），端點 `/internal/validate-cache/evict` 確實存在（`bustream/gateway/routes/admin.py:258`）。dev 驗收斂仍可 `docker restart xparse-gateway`。
5. key 反查用 `POST /iam/api-keys/search`，body 是**原始 key**（`{"key": ...}`），不能按 app 列 key。

### 8.6 沒解決的事

| # | 事項 | 性質 |
|---|------|------|
| 1 | Prod 部署：純 IAM＋Console additive，**無 gateway image 耦合、無 same-batch 約束**（對照 ADR-406 的 0268 反例）；IAM-first blue-green 照常 | 需部署窗口（2026-10-14 註：已在 prod 分支 v1.76.4；部署期的盤點與公告有沒有做，git 看不出） |
| 2 | proxy Models tab 在有 paused 成員時 reorder 疑似 400（UI 送 active+paused 全列、後端只驗 active 集）——既有 bug，非本案引入 | 待對 dev 實池驗證後 `/doc-issue` |
| 3 | proxy 端池 reorder 至今不 push cache 逐出（30s TTL 空窗；per-app model-order 端點有做）——需 per-consumer fan-out | tracking issue 候選。**部分改善**：Rev.8（#3921）讓 **application update 端點**無條件逐出，所以改該 app 的 visibility／routing_strategy／routing_parameters 現在即時生效；proxy **池 reorder** 那條路徑仍是空窗 |
| 4 | §6 舊表的 #1（`X-Xparse-Model-Substituted` 死碼）、#2（Visibility 開關命名）仍未動 | 前案遺留 |

---

## 9. 後續 campaign：model-order 帶出分級 + 帶內映射（SPEC-268 Rev.1 / SPEC-264 Rev.8 / ADR-406 Amendment C，2026-08-29）

> 只講對「LLM Proxy 模型定址」這份文件的增量；完整機制、公式推導、測試與坑在 `路由v2.md` §14。PR **#3835**（**已 merge**：`2808b2161`）。

### 9.1 這是什麼、為什麼

Peter 的兩個問題：「pool 裡有 N 顆模型時，每顆落在哪個 tier？」「要不要顯示在前端？」——以及對 `round(t×(N-1)/3)` 是否最佳的追問。原公式四級對四個位置，pool ≥ 5 顆就有位置**永遠選不到**（只在 failover 才輪到），而且 Console 完全看不出來。裁定：A（顯示）+ B（分數細分映射）一起做、只顯示在 app 的 Models tab、不加開關。

### 9.2 端點增量（ORDER-01 Rev.1）

`GET /iam/applications/{app}/model-order` 的每個 source 多兩個欄位（additive，舊 client 不受影響）：

```
"complexity_tiers":       ["COMPLEX"]   # 該位置所屬分級（強→弱；pool < 4 顆時一個位置可掛多級）
"complexity_band_offset": 1            # 0 = 該分級的帶首；>0 = 帶內較弱位置（只有量尺低分請求會落到）
```

- Gate = consumer 的**已儲存** `routing_strategy`：`complexity_routing` / `llm_judge_routing` 才計算，`none`／`agent` → 兩欄 null。
- 由 IAM **鏡射** SPEC-264 §2.1 的位置函數（`xparse_iam/domain/complexity_tier_bands.py`），不 import xparse_routing——IAM CI 的 sys.path 沒有該套件；兩份拷貝由 gateway suite 的 TC-264-34 釘住逐格相等。
- proxy 層 `GET /iam/applications/{proxy}/model-sources` 共用同一個 `ModelSourceResponse` schema，所以也會看到這兩個鍵，**恆為 null**（proxy 池被多個 app 共用、沒有單一策略）。
- 這是**預覽**：N 取生效序的 active 成員數；執行期 reliability guard／pin／failover 把候選踢掉後會在剩餘模型上重算，真正落點看 audit 的 `selected_position` / `band_offset`。

### 9.3 Console 增量

- **App detail → Models tab 新欄「分級」**（en "Complexity tier"——刻意不叫 "Tier"，會撞 proxy Models tab 的 `Model.tier` lightweight/standard/heavy）：每級一個 badge（SIMPLE/MEDIUM/COMPLEX/REASONING 不譯）；帶尾位置灰色 + 向下箭頭 icon；欄標題 tooltip 講明預覽語意。badge **綁位置不綁模型**——拖拉中 badge 留在原位，模型換過去。策略是 None 或 payload 沒帶欄位時整欄不出現。
- **Keyword rules 的分級下拉**：每個選項描述追加「目前：<帶首模型名>」。規則命中永遠落帶首，所以顯示帶首就是精確的；反映**已儲存**策略，表單切換未存檔前不變。
- proxy 層 Models tab **不動**。

### 9.4 pool 有 N 顆時每顆落哪級（速查）

`起點(t) = round(t × (N−1) / 3)`，t = REASONING 0 / COMPLEX 1 / MEDIUM 2 / SIMPLE 3；起點到下一個起點之前都是那一級；第一顆恆 REASONING、最後一顆恆 SIMPLE。

| N | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| 2 | R·C | M·S | | | | | | |
| 3 | R | C·M | S | | | | | |
| 4 | R | C | M | S | | | | |
| 5 | R | C | C↓ | M | S | | | |
| 6 | R | R↓ | C | M | M↓ | S | | |
| 8 | R | R↓ | C | C↓ | C↓↓ | M | M↓ | S |

`↓` = 同級帶尾：該級分數區間依帶內模型數等分，分數落第幾段就落第幾顆（例：N=5 COMPLEX 帶兩顆，score > 0.475 → 帶首、0.35～0.475 → 帶尾）。規則命中／推理硬規則／LLM Judge 判級不帶可比分數，一律帶首。N ≤ 4 每級一顆 → 行為與改版前逐位元相同。

> **2026-09-02（SPEC-268 Rev.2 / SPEC-276 §8）**：這張表的計算與 gate 不變，但**語意依 app 的 `routing_objective` 換義**——Quality first 下是「落點」（該級請求落在這一顆）；Cost / Latency / Energy first 下是「合格下限」（該級請求可落在這一顆或任何更前面更強的顆，由目標在其中挑最便宜／最快／最省）。Console 的「分級」欄 tooltip 已依此切換文案。

### 9.5 證據

- dev（Peter 的 app，proxy `gpt-4o`）：N=4 時回 `5.5 [R] · luna [C] · 4o [M] · 4 [S]`；加入 `gpt-5.4` 成 N=5 後回 `5.5 [R] · 5.4 [C] · luna [C, offset 1] · 4o [M] · 4 [S]`——與 §9.4 表逐格相同。
- 契約：gateway TC-264-31..34（含真 classifier + 真 Resolver 的 §8.1 probe）、IAM TC-268-13 + `test_complexity_tier_bands.py`（進 iam-ci-suite）、Console vitest 134 綠 + i18n 四 gate + eslint。
- B 的執行期位移（audit `band_offset > 0`）尚未在 dev 實發；步驟在 `路由v2.md` §14.4。

### 9.6 給操作者的補充指引

- **想知道某顆模型會接哪一級** → 開 app 的 Models tab 看「分級」欄，不用再心算公式。
- **pool 超過 4 顆時發現某顆幾乎沒流量** → 看它是不是帶尾（灰色）：帶尾只接該級分數較低的請求，流量多寡由分數分布決定，不是壞掉。
- **想讓某類請求固定打某一顆** → 用 Keyword rules 指定分級，命中恆落該級帶首；要打帶尾那顆做不到（規則不帶分數）——把它拖到帶首位置即可。
- **`Model.tier`（lightweight/standard/heavy）與這裡的分級無關**：映射只看排序。

### 9.7 沒解決的事

| # | 事項 | 性質 |
|---|------|------|
| 1 | Prod 部署前盤點 N ≥ 5 且 Complexity／LLM Judge 的 app；公告寫明「原本永遠選不到的位置開始吃該級低分請求」。無 migration，IAM 與 gateway 可獨立滾動 | 部署期（2026-10-14 註：已在 prod 分支 v1.76.4；部署期的盤點與公告有沒有做，git 看不出） |
| 2 | B 執行期 e2e（dev 上 Peter 的 app 已 N=5，只差 restart gateway + 兩則題） | dev 驗證 |
| 3 | 帶內分段按分數等分、不按流量等分：若某 app 的分數分布集中，帶內某顆會明顯偏多——等 audit 的 `score` 分布數據再決定要不要分位數式切法 | 觀察項 |

---

## 10. 後續 campaign：Model Name Visibility 所有權反轉為 per-application（ADR-138 Rev.8 / PRD-305 / SPEC-273，2026-08-31）

### 10.1 這是什麼、為什麼

**問題**：`select_available` 由**綁定的 proxy** 決定（ADR-138 Rev.4），所以綁同一個 proxy 的所有 consumer **被迫共用一個揭露程度**。這只在「所有 consumer 面對同一群客戶」時才成立，而實際上不是——內部團隊的 app 想公布真名以便 pin `gpt-4o` 做 A/B，賣給外部客戶的同池 app 必須維持 opaque（不揭露供應商組合）。今天只能二選一。

**推翻 Rev.4 靠的是論證，不是新證據**。Rev.4 的所有權規則是「visibility 是關於 catalog 的陳述，歸 catalog 擁有者」——這句話混了兩個問題：

- **有哪些名字**（catalog membership）：確實歸 proxy，Rev.8 一行未動（INV-198-8）
- **這個 app 對它的客戶端揭露多少**：這是 app 與它的呼叫方之間的契約，同一份 catalog 本來就能對不同客戶端揭露不同程度——像同一張表可以有多個 view

Rev.4 的第三個理由是「per-consumer 差異化零證據」（inventory Q3）。那是 2026-07 當時的證據狀態，而**那份 inventory 自己訂了推翻條件**（§3 修正 2：「amendment 必須先補一個真實 multi-consumer-divergent-visibility 案例」）。PRD-305 就是那個案例。而 fan-in 早已是主流結構：dev 上 4 個被綁的 proxy 有 3 個被多 consumer 共用，其中一個被 14 個綁。

### 10.2 改了什麼

**解析**：`_resolve_select_available(app)` 從「查 binding、有就讀 proxy」變成 `bool(app.select_available)`——**無條件讀自己那一列，不查 binding、不繼承、沒有三態**。

> 為什麼不做 ADR-415 那種 `binding.select_available: bool | None` 三態 overlay：`model_order` 需要 NULL sentinel 是因為**池成員會漂移**（新加的模型得落到每個 consumer 的序裡某處）。visibility 是個 boolean，沒有東西要跟隨，sentinel 只會多一個 Console 狀態和第二個要查的來源。而且每個 app 都寫死自己的值之後，「這個 app 能不能 pin」看它自己那一列就有答案。

**一致性（INV-138-25）**：三個讀取端都必須讀同一列——HTTP validate、direct mode、以及 **agent 部署的 inference target**（ADR-269）。第三個是硬需求：`inference_target` 若讀 proxy 的旗標，agent 會被配置成一個真實模型名，然後 gateway 用該 app 自己的 `false` 拒絕它——跨平面的 advertise-then-reject。實作上直接**把 `select_available` 從 `ProxyView` 拿掉**，讓「讀錯來源」連編譯都過不了。

**新建預設**：`integration`（API consumer）與 `application`（unbound）加入 born-visible（沿用 Rev.7 的 app-type registry 機制）。**agent 系列刻意維持關閉**——`inference_target` 在 visible 且池內多於一顆 chat 模型時**直接拒絕部署**（「multiple pinnable chat models in the pool; set a default member (deferred)」），而那個 default-member 規則至今未實作。legacy `llm_proxy` type_code 同樣排除（它是 `app_type_code` 的 column 預設，翻了會讓每個沒指定型別的 app 曝光）。

**migration 0291 — 三條規則，缺一不可**：

| # | 列的形狀 | 寫入 |
|---|---|---|
| 1 | 有 active binding | 該 proxy 的當前值（＝現行生效值 → 部署對客戶端不可觀察） |
| 2 | 無 binding，但**自己擁有 catalog**：有 `ProxyModelSource`（自身是 proxy）**或** `ApplicationModel`（legacy 直綁） | 保持原值 |
| 3 | 兩者皆無（無 catalog 的空殼） | `true` |

規則 2 的 `ProxyModelSource` 分支是這次最容易漏的地方：**LLM Proxy 既沒有自己的 binding、也沒有 `ApplicationModel`**（它的 catalog 是 `ProxyModelSource`），所以直覺的兩分支寫法「無 binding → true」會把**每一個刻意 opaque 的 proxy 翻成可見**——dev 上有 19 個。

**順帶修掉的既有缺陷**：`validate_api_key.py:415`（direct mode）**從來沒跟上 Rev.4** ——ADR-138 §2.5.3 明寫兩個 validate 路徑都要改成 binding-aware，實際只改了 `auth_engine.py`。也就是同一個 app 在兩種 deploy mode 下的可見性長期不一致（同 #833 的形狀）。改成讀單一列後兩者結構性一致，這不是推論：對應測試在改動前就是紅的。

**cache 逐出**：application update 端點原本**完全沒有** `evict_scope_from_gateway`，改完要等 validate cache TTL。Rev.8 補上，且做成無條件——`routing_strategy`／`routing_parameters`／`risk_level`／`policy_profile` 都在同一份 validate payload 上，本來就有一樣的延遲。

### 10.3 Console

開關**回到 application configuration 頁**（Rev.4 曾把它藏起來，理由正當——當時那個值會被 proxy 靜默覆蓋，是典型的「設得到但無效」陷阱；Rev.8 之後它是唯一有效的那一列）。

~~proxy 頁的開關**保留但文案誠實化**：它只管「這個 proxy 以自己的金鑰被直接呼叫時」（ADR-312），不影響綁定它的 app。不改文案的話，操作者翻它會預期一個已經不存在的全域效果。~~ **← 同日被 Rev.9 推翻**：ADR-312 的路徑其實已被 ADR-414（8/28）退場，「誠實文案」描述的是一條不存在的路——開關整個移除（§10.7）。

tooltip 補上 failover 的可用性含義（§6 舊表 #3 自此關閉）。

### 10.4 驗證證據

- **TDD**：SPEC-273 八個契約測試先寫，對改動前的 resolver 跑出 **5 failed / 3 passed**，改完全綠。
- **三條 backfill 規則各做 seeded regression**：拿掉規則 1 → 紅 2 個（含零擾動斷言）；規則 2 → 紅 3 個（含 opaque proxy 那個）；規則 3 → 紅 1 個。
- **IAM 全 unit suite 對 origin/main baseline**：`23 failed / 2510 passed` vs `23 failed / 2490 passed`——**同樣的 23 個既有失敗**，零新紅。CI 上 IAM postgres + sqlite + gateway suite 亦全綠。
- **對 dev 真實資料副本**（335 apps、head 0287 的原子快照，migrate 到 0291）：

  ```
  49 個「今天服務流量」的列 effective visibility 逐一相同    PASS
  rule 1 改寫 18 列（正是 own != effective 的那 18 個）
  15/15 opaque proxy 保持 opaque                              PASS
  286/286 空殼變 visible                                      PASS
  共動 151/335 列
  ```

- **VIS-01 用真 resolver 對真 proxy**（`gpt_4o_816e-proxy`，4 個 consumer）：`gpt_4o_816e`=true、`peter_test_gpt`=false，兩者候選集合都是同樣 5 顆（VIS-03）。`peter_test_gpt` 正是先前記錄過「自己的 `false` 是啞的」那個 app——現在它真的生效了。

### 10.5 踩到的坑（下次省時間）

1. **migrate 印 `Applying 0291… OK` 卻一個 row 都沒動**。ephemeral 容器沒設 `XPARSE_IAM_DB_PATH`，settings 預設是 `BASE_DIR / "xparse_iam.db"`＝image 內建的空 DB。**驗收要讀目標 DB 檔的 `django_migrations`，別信 migrate 的 log。**
2. **image 裡沒有 `sqlite3` CLI**。要備份 dev DB 用容器內 `python -c "import sqlite3; sqlite3.connect(src).backup(sqlite3.connect(dst))"`（原子且含 WAL）。
3. **掛在 `/tmp` 的腳本要配 `PYTHONPATH=/app/xparse_iam`**，否則 `sys.path[0]` 是 `/tmp`、`django.setup()` 直接 ModuleNotFoundError。
4. **stacked PR 的 CI 是盲區**：`ci.yml` 的 PR trigger 是 `branches: [main]`，base 不是 main 的 PR **完全不跑那 11 個 static gate**——retarget 到 main 之後才第一次跑。
5. **squash + `delete_branch_on_merge=false` 時 GitHub 不會自動 retarget 下一個 PR**，而且直接改 base 會讓它重複顯示上一個 PR 的整份 diff（squash 產生的是新 sha、不是原 commit 的後代）。正解：先 `git rebase --onto origin/main <上一個PR的commit>` 再 force push。
6. **我自己寫了一段死碼又拿掉**：0291 初稿有「一個 app 有兩條 active binding」的防禦分支，但 `application_id` 有 UNIQUE 約束，真元件產生不出那個狀態。那是 §8.1 紀律說的「只證明自己 fake 的防禦」，已刪除並改成驗證那條約束本身。

### 10.6 沒解決的事

| # | 事項 | 性質 |
|---|------|------|
| 1 | **dev/prod 尚未實跑 0291**（只在 DB 副本上驗過）（2026-10-14 註：0285／0291 已在 prod 分支 v1.76.4；`XPARSE_LLM_PROXY_KEY_RETIREMENT_MODE` 預設仍是 `shadow`）。dev IAM 的 entrypoint 會自己 migrate，所以下次重啟就會執行 | 部署期 |
| 2 | 存量那 19 個 opaque proxy 底下的 app **維持 opaque**——backfill 刻意不碰。要把某個 app 翻成可見是**該 app 的對外契約變更**，逐一決定 | 營運決策 |
| 3 | **跨 group binding 的授權面**：per-app 之後，consumer app 的擁有者可以自行揭露池裡的真名，等於繞過 proxy 擁有者。當前資料形狀下不成立（dev 21 條 binding：跨 group 0、跨 tenant 0），但 ADR-273/278 的 grant 機制允許跨 group 綁定 → 屆時需要在 proxy 上加一道「允許下游自行開啟可見性」的閘門 | 前提條件，寫在 ADR-138 §2.9 |
| 4 | §6 舊表 #2（開關**命名**叫「Model Name Visibility」但管三件事）仍未動。Rev.8 只是讓兩個面各自有誠實的描述文字 | 前案遺留 |
| 5 | 沒打 gateway 的 HTTP round-trip（gateway 零改動；`/v1/models` 與定址閘門由既有 contract test 覆蓋且保持綠） | 驗證範圍 |
| 6 | ADR-138 Rev.8 的 status 標 **Proposed**（repo 兩種先例都有：Rev.6/Rev.7 merge 時是 Accepted，ADR-415 merge 後仍是 Proposed）。實作剛落地、未經 prod | 治理姿態 |

---

## 10.7 後續 campaign：Rev.9 — proxy 頁開關退場 + probe 豁免（2026-08-31，PR #3926 / #3927）

### 10.7.1 這是什麼、為什麼

起因是 Peter 的質疑：「api key 都從 application 發、proxy 只管加減 model，為什麼 proxy configuration 還留 Model Name Visibility？」追出三層事實：

1. **Rev.8 §2.9.7 留開關的理由已失效**：它引用 ADR-312（proxy 以自己金鑰被直接呼叫），但 **ADR-414（8/28，早 Rev.8 三天）已 supersede ADR-312**——0285 把 live proxy client key 全部 re-parent 到 `api_consumer`、proxy 上 mint key 一律 410、gateway `auth_handler._enforce_app_type_boundary` 拒 `app_type=llm_proxy` key。兩份同週文件沒對齊。
2. **開關唯一可達的讀者 = internal model ping（ADR-314 Retest），而且是負面耦合**：ping 以真名 pin 目標（`_model_ping.py:182`）、定址閘門無 probe 豁免（`pre_execution.py` 只認 `select_available`，INV-138-21）、probe key 的 validate 讀 proxy 自己那列 → **opaque proxy（dev 有 19 個）的 Retest 必 400**，與模型健康無關。code 級推論在 TDD 得到實證：新測試對未改的碼先紅（真 `mint_health_probe_key` + 真 validate 解析出 False）。
3. **過渡期注意**：gateway 的 ADR-414 拒絕預設 `shadow`（`XPARSE_LLM_PROXY_KEY_RETIREMENT_MODE`）且 prod 未跑 0285/0291（2026-10-14 註：0285／0291 已在 prod 分支 v1.76.4；`XPARSE_LLM_PROXY_KEY_RETIREMENT_MODE` 預設仍是 `shadow`）——enforce 翻開前，存量 direct caller（若有）仍吃 proxy 那列，API 仍可寫（只有 Console 編輯面移除）。

### 10.7.2 改了什麼

- **Console**：`proxy-configuration-view.tsx` 不再對 `ModelConstraintsCard` 傳 visibility props（`SMART_ROUTING_HIDDEN` 同型先例）；card 的 `visibilityScope` prop 整個拆掉、visibility pair 改成與 judge picker 同款 opt-in 雙 prop 契約；`visibilityDescriptionProxy` + 無讀者的 legacy `visibilityDescription` 從兩個 catalog 移除。**欄位、API、Rev.7 born-visible 預設、0291 三規則全部不動。**
- **IAM（INV-138-26）**：`auth_engine`（HTTP validate）與 `validate_api_key.py` use case（direct mode）**兩條路徑**對符合 `is_internal_health_probe_key()`（ADR-414 邊界例外的同一判準：`runtime_upstream` + `purpose=health-probe`）的 key 解析 `select_available=true`。只改 wire 值、不寫回 DB、gateway 閘門零改動；probe 因此走 PIN 語意（不 failover——正是 §2C.3「provider faults SURFACE」要的）。
- **Docs**：ADR-138 §2.10 + INV-138-26、PRD-305 Rev.1（U3 改為「不再顯示」）、SPEC-273 Rev.1（VIS-R3 + TC-273-15/16）、SPEC-171 DIRECT-04 加註、ADR-314 §2C.8 加註、ADR_INDEX（順手給 ADR-414 一列正式策展 row）、Core-ADR-06 回寫。

### 10.7.3 驗證

- TDD red-first：TC-273-15/16 對未改 resolver 先紅（§8.1 真元件 trigger 證據）、改後綠；TC-273-15 同時斷言 DB 列仍 False（豁免不寫回）+ INV-314-15 裁切不受影響。
- IAM 全 unit suite：23 failed / 2530 passed vs origin/main 基準 23 failed / 2528——失敗集合 diff **逐條相同**、零新紅。
- Console：vitest 817 passed、tsc/eslint 乾淨、i18n 四 gate + import-leaks + glossary 全綠。

### 10.7.4 沒解決的事

| # | 事項 | 性質 |
|---|------|------|
| 1 | 未做 dev 真 HTTP ping e2e（real-token ping 需 tenant feature flag，預設 off；IAM 層兩條 validate 路徑已用真元件測試鎖住） | 驗證範圍；flag 開啟的環境可補一發 Retest 實測 |
| 2 | §10.6 #3（跨 group binding 授權閘門）、#4（開關命名管三件事）原樣未動 | 前案遺留 |
| 3 | prod 部署順序：Rev.9 純 IAM read-path + Console，無 migration、無 gateway 耦合；與 0285/0291 無 same-batch 約束 | 部署期 |

---

## 11. 後續 campaign：Routing Objective 兩軸（PRD-308 / ADR-430 / SPEC-276，2026-09-02）

> 完整紀錄（機制、拍板、驗證、坑、指令）在 `路由v2.md` **§16**；交付總表與剩餘工作在 **§16.16**；本節只寫**對模型定址視角**有影響的部分。
>
> **狀態（2026-09-04，四批於 2026-09-03 23:44–23:45Z 連續 merge 後）**
>
> **已在 main**：PR-1a **#4070** · D28 docs **#4084** · **PR-2 Cost #4092** · Console follow-ups **#4098 / #4099 / #4102** · D29 **#4112** · **PR-4a Latency 核心 #4116** · **PR-4b Latency 參數／wire／Console／N10 gateway 半邊 #4149**（§16.13）· U6 證據 spec **#4150**（§16.15）· N10 Audit 側 **Xparse-Audit#130 + #4151**（§16.14）。origin/main = `400a2a11c`。
> **Energy 也已在 main**：#4153 曾因 stacked PR 的 base 沒改回 main、被 merge 進 4b 分支而未達 main（§16.17.1），重開的 **#4155 已 merge**（`9a36f11f1`），`0306` 與 `energy_pick` 都在 main，dev 實測已載入。
> **文件狀態**：ADR-430 → Accepted、PRD-308 / SPEC-276 → Active（**#4156**）。
> **未做**：~~PR-1b `/v1/responses`（OBJ-X\* / A9 / I7）~~（**✅ 2026-09-06 已 merge，§12**）· prod `serving_locality` 盤點（D-E2）· 存量地端補「資源規模」· PRD-303 gate（#4152）。
> **燃料覆蓋率**：picker 全在 main ≠ 目標真的在運作——dev 實測 Cost 有效價 7/73、`last_latency_ms` 12/73（地端 0/34）、`energy_structural_estimate` 0/73，基線與判準見 `路由v2.md` **§16.18**。
> **2026-09-04 下午交付 review**（`路由v2.md` **§16.20**）：四個 reviewer 分區審 main → 8 項缺口 → 三個修正 PR **#4201**（gateway/routing：ε seed 改 gateway salt + `request_id`、failover 重選不探索、fallback 取樣窗自換手起算、tracker 來源側丟棄壞樣本並 warning；**SPEC-276 Rev.8**）/ **#4202**（Console：切離 Latency first 時刪 ε 鍵、資源規模拒非正數）/ **#4203**（IAM：catalog 綁定出生點補 `onprem` + 估算、audit snapshot 補兩欄、價格 `ge=0`、估算 strict float、openapi 重產 + 六處 digest）——~~待 Peter merge~~ → ✅ 09-04 已合併。同時查明「地端 RTT 0/34」：dev 的 mvp compose 沒有掃描迴圈 ＋ 無憑證模型探測 fail-closed（後者 prod 也成立）。
> **環境注意**：同日 merge 的 **#4147** 把 IAM／gateway entrypoint 改成 per-owner venv（`/opt/xparse/*/venv`），dev 的 `xparse-scr:celery-local`（2026-08-14 建）只有舊的 `/opt/venv` → `./dev.sh up` 會 `exec: … not found`。重建 image 的指令見 `路由v2.md` §16.17.3。

### 11.1 對 §2.1 流程的影響

步驟 ⑤ 從「`routing_strategy` 選模型」變成兩步：`routing_strategy`（難度判定）算**合格集**，`routing_objective` 在合格集裡**挑**。其餘步驟不動：

- ② 定址閘門與 PIN **完全不變**——客戶指名真模型（`select_available=true`）仍是 PIN，候選裁成一顆後 objective 無事可做（PRD-308 N9）。
- ③ 候選序仍是 app 生效序（ADR-415）；Quality 下它是落點依據，其他目標下它定「至少要多強」的下限。
- ⑥ R3 failover：`resolve_fallback` 以同一 `StrategyConfig`（含 objective）重跑策略，所以 Cost 下降級序是「次便宜」、Latency 是「次快」、Energy 仍雲端優先；`objective=quality` 時才是「沿 sort_order 下一顆」（ADR-353 INV-353-1 已限縮）。
- ~~Responses API 目前仍恆取序首、不跑任何策略——**PR-1b** 才接同一條 resolver（首輪生效、`previous_response_id` 跟綁定、`model` 必填不變）。~~ → **✅ 2026-09-06 已交付（ADR-437 PR-3 #4241）**：首輪生效、`previous_response_id` 跟**綁定列**的模型、`model` 必填不變、`llm_judge_routing` 在此面短路退 heuristic（§12）（2026-10-14 註：#5804 起此面的 `llm_judge_routing` 會真的呼叫 judge，#4248 已關；在 rel、prod 沒有）。

**哪些 surface 真的跑 routing**（2026-09-04 逐檔覆核；下次別再重查）：

| Surface | 走 routing？ | 證據 |
|---|---|---|
| `/v1/chat/completions` | ✅ | 主路徑 |
| `/v1/messages`（Anthropic） | ✅ | `routes/messages.py::create_message` 翻成 `ChatCompletionRequest` 後走同一個 `execute_chat`（ADR-280），路由層零差異——**兩軸在這面完全生效**。**但它是旗標閘的**（2026-10-14 註：旗標已由 #5782 退場，rel／main 上 `/v1/messages` 無條件註冊；prod（v1.76.4）仍是舊旗標，靠部署設定開著）：`XPARSE_ANTHROPIC_MESSAGES_ENABLED` 預設 `false`；**prod 開著**（deploy ledger 列為 prod-only key）、dev 自 2026-09-08 起也開，兩軸在此面已由真流量驗過 11 案（`路由v2.md` §23.12）；碼面 ✅ ≠ 環境上有開，rel 要看 compose |
| `/v1/responses` | ❌ | `routes/responses.py:189-192` 明寫「has no routing candidate-set machinery」，恆取 `sort_order` 序首 → **四個目標在該面全部失效，不只 Quality**  **→ 2026-09-06 起 ✅**（ADR-437 PR-3；judge 例外見 §12.1） |

（`/v1/embeddings`、`/v1/audio/*` 等不適用——沒有候選集概念。）（2026-10-14 註：仍不路由，但 #5950 起有 ADR-138 定址：embeddings 用 app code／default 跑該 app 唯一那顆 embedding 模型、沒綁的名字 404（三個 D-2a 例外名稱除外）、opaque app 指名真名只記錄；audio 全部只記錄；切 enforce 在 #5949。rel 有、prod 沒有）

### 11.2 欄位歸屬與 wire

- `routing_objective` 跟 `routing_strategy` 一樣**只掛 consumer application**（ADR-198 INV-198-2 延伸）；proxy row 保留欄位（0285 handover parity）但 **proxy configuration 頁不顯示**（ADR-414：proxy 無路由效果）。
- Console 可見性走**同一個** `supports_routing_strategy` allowlist（INV-430-11）——沒有第二個 resolver，避免 INV-198-10 那個 7 週的靜默收窄重演。
- validate wire 多一鍵 `routing_objective`（tenant / group key 為 null）；**舊 gateway 忽略、新 gateway 缺鍵預設 quality**（dev 用 `origin/main` gateway 對照實測）。`GET/PUT /iam/applications/{uuid}` 多同名欄位；非法值 `400 INVALID_ROUTING_OBJECTIVE`，訊息列出四個合法值。
- audit：`decision_evidence` 多 `objective` 鍵；`strategy_name` 仍是難度判定值（INV-088-11 守住），`selection_reason` 詞表新增 fallback 三詞（PR-1a）；D28 後 Cost 改為 `cost_min` / `cost_unpriced_assumed_zero`。

### 11.3 對 §9.4 分級速查表的影響

表不變、gate 不變（仍看已儲存的 `routing_strategy`），語意換：Quality = 落點；其他 = 合格下限。N ≤ 4 時 Cost / Latency / Energy 與 Quality **仍有差**——差別在合格集是「該格加上所有更強的格」（前綴），不在帶寬；只有 REASONING（合格集 = `order[0]`）、池嚴格越強越貴、或缺資料退 Quality 時兩者相同。

### 11.4 給操作者（增量）

| 想要 | 做法 |
|---|---|
| 純成本導向、不管難度 | 路由目標 Cost first + 難度判定 None（全池最便宜） |
| 難題保底、簡單題省錢 | Cost first + Complexity（每題在「至少要多強」以上挑最便宜） |
| 讓地端優先 | **D28 後不再自動**：地端 0 與雲端未設價 0 同分 → 依排序取前者。給雲端設價（「套用公開定價」，#4092 起可用；**2026-09-08 起在 Model Pool Detail → Settings → Prices**，proxy Models tab 只讀），地端不填就是 0 |
| 看每顆的價格與分級（application Models tab） | 價格欄常駐（#4098）；分級欄只在難度判定為 Complexity / LLM Judge 時出現；`Model.tier` 不顯示（#4099） |
| Smart Routing 面板選 None | 只有 Cost / Latency / Energy first 提供 None（= 全池最便宜／最快／優先雲端）；Quality first 沒有 None——quality + none 就是總開關關閉的儲存值，切到 Quality first 會自動落 Complexity（#4102） |
| 知道這題為什麼選這顆 | audit `decision_evidence.objective` + `selection_reason`（`cost_unpriced_assumed_zero` = 因被當免費才選中）；`priced_candidate_count` = 合格集大小，可反推難度判定切到哪 |
| Cost first 為什麼沒選單價最便宜的 | **D29（#4112）之後不會再發生**：有效成本 = 單價 × (prompt + 共用常數 200)，排序就是你填的單價。之前會因 per-model 回覆長度 EWMA 反轉（gpt-4 2e-5 壓過 gpt-4o 1e-5 並鎖死，`路由v2.md` §16.10） |
| 選到誰要用 audit，不能看 `response.model` | proxy alias 永遠回 `gpt-4o`；`audit.execution.completed.model_uuid` 才是執行模型（無 name 欄） |
| Latency first 剛開沒差別 | 正常：gateway 重啟後延遲樣本為 0.0/None 視缺值 → 退 Quality（暖機期），audit 記 `no_latency_data_fallback`。第一題之後只有被選過的模型有樣本，會先「贏者全拿」，靠 ε 探索與其他路徑（pin、別的 app）把樣本補齊。**#4201 起**：failover 重選不探索（探索失敗後直接回剩餘最快者），且 fallback 模型的樣本自換手起算、不吃 primary 的逾時時間 |
| Console 為什麼不顯示「暖機中」 | **它看不到**：gateway 的延遲 EWMA 在進程記憶體、沒有 HTTP 面（也不為此新開端點）。Console 唯一能觀察的是連線探測 `last_latency_ms` 是否為 null，所以成員列只標「尚未探測」；真正的暖機期只在 audit 的 `no_latency_data_fallback` 看得到（#4149） |
| 調 Latency 的探索比例 | application configuration 在 Latency first 下有「探索比例」（整數百分比 0–50，預設 5%）。存 5% = 不寫入該鍵（缺鍵即預設）；`latency + none` 也可以存。探索請求**照樣計入 EWMA**，只在客戶延遲報表被排除（`execution.completed.routing_exploration=true`，#4149 + Audit#130）。**#4202 起**切離 Latency first 時該鍵一律不寫（之前同 session 填過再切目標會把看不見的 knob 寫進 DB）；**#4201 起**探索由 gateway 自己的 salt + `request_id` 決定，客戶端重送同一個 `X-Request-ID` 不能再把探索釘在 0% 或 100% |
| Energy first 選了雲端，我想讓它用地端 | **設計就是雲端優先**：只要合格集裡有雲端成員就走雲端（`energy_cloud_first`）——Energy first 最小化的是**自家機房用電**，雲端視為 0。要讓地端有機會，得讓合格集裡沒有雲端成員（暫停雲端成員，或用難度判定把合格集收窄到只剩地端） |
| Energy first 在純地端池沒差別 | 多半是**沒有「資源規模」估算**：`0306` 不 backfill，存量地端模型全是 NULL（dev 34 顆皆是），此時 Energy ≡ Quality 並記 `no_energy_data_fallback`，Console 標「無能耗資料」。修法 = 到 Model settings 填「資源規模」（越小越優先；自助註冊會自動算 GPU 記憶體 × 張量平行度）（#4153）。**#4202 / #4203 起**：資源規模只收正數（Console 擋 `0` / 負數 / `1e309`，API 對 `"48"` / `true` / `Infinity` 回 422 而非靜默轉型；之前 Console 輸入 `1e309` 會變 `null` 把估算**清掉**） |
| 雲端託管的 vLLM 被當成地端 | `0258` 把所有 `provider='vllm'` 一律回填 `onprem`（R15）。PR-3 起可修：Model settings 的「服務位置」改「雲端」，或 `PATCH /iam/models/{uuid} {"serving_locality":"cloud"}`。上線前建議整批盤點一次（SQL 在 cutover runbook addendum）。**#4203 起** catalog 綁定（`bind_application_to_deployment` → `materialize_model_for_deployment`）出生的 Model 也會蓋 `onprem` + 估算——之前這條路落成 `cloud`、無估算，Energy first 反而優先選它 |
| 為什麼 Latency first 比整體延遲不比首 token | 規則上：同一次決策只比一種訊號，所有有資料的候選都有 TTFT 才比 TTFT，非串流請求不產生 TTFT，所以混合流量的 app 多半比整體延遲；`decision_evidence.latency_signal_kind` 會寫出這次比的是哪種（#4116）。**但 2026-09-04 起要知道：在 main 上這個問題有第二個答案——就算你全部都是串流，也永遠比不到 TTFT。**`routes/chat.py` 用 `time.monotonic()` 蓋首事件時戳、卻減 `time.time()` 的 acquire 時戳，`ttft_ms ≈ −1.788e12`，tracker 原封存下、`valid(x)` 判缺 → `avg_ttft_ms` 這一層自 Latency first 上線起從未被選中過。dev 實測 26 發純串流，`latency_signal_kind` 始終停在 `avg_latency_ms`。**已修，#4158 merged（`7e55574b6`）**；修好的 gateway 同樣測法會翻成 `avg_ttft_ms`（872–1007 ms 真值）。詳見 `路由v2.md` §16.19。**#4201 再補一層**：兩個 tracker 在來源側就丟棄負值／NaN／inf 並 warning（之前只有 `chat.py` helper 擋串流 TTFT，非串流 `latency_ms` 與 NTP 倒退仍會污染） |

### 11.5 沒解決的事（定址視角）

| # | 事項 | 性質 |
|---|------|------|
| 1 | Responses API 尚未跟 objective（PR-1b）——該面沒有 `RequestContext`、`input` 不是 messages、自帶 pin 與綁定 TTL，是獨立一批 | **✅ 2026-09-06 已交付（§12）** |
| 2 | ~~四個目標的 picker~~ → **四個目標全部在 main 且皆為真實作**（Quality #4070 · Cost #4092+#4112 · Latency #4116+#4149 · Energy #4155；N10 Audit 側 Audit#130+#4151）。Energy 曾因 stacked PR base 未改回 main 而蒸發一次，見 §16.17.1。~~**Latency 附帶一個未 merge 的缺口**~~ → **#4158 已 merge**：三層訊號都活了（picker 是真的，第一層 `avg_ttft_ms` 曾因串流路徑時鐘錯配恆為缺值——commit 沒跟上 PR 而蒸發，§16.19） | 完成 |
| 3 | `serving_locality` 資料風險 R15：0258 把 `provider="vllm"` 一律回填 `onprem`，雲端託管 vLLM 會被 Energy 當地端（Cost 自 D28 起地端雲端同規則、不受影響）。D-E2 的修法（Console「服務位置」或 `PATCH /iam/models/{uuid} {"serving_locality":"cloud"}`）**已在 main**；**存量整批盤點仍未做**（SQL 在 cutover runbook addendum） | **Peter，prod 上線前** |
| 3b | 存量地端模型沒有「資源規模」估算：那 34 顆從未走過 self-service 註冊（`created_via` / `deployment_uuid` 全 NULL、`catalog_model_version` 與 `catalog_model_deployment` 各 0 列）→ `tp` / `min_vram_per_gpu_gb` 不存在，**backfill 不成立**，不只是 `0306` 刻意不做。純地端池的 Energy first 目前 ≡ Quality，可觀察不靜默（audit `no_energy_data_fallback` + Console「無能耗資料」）。**新註冊會自動算**，人工只需補存量，且只有 dev 那 7 個純地端池用得到（`路由v2.md` §16.18.1） | 營運補值（範圍比看起來小） |
| 3c | **地端連線探測從未取得 RTT（dev 0 / 34，雲端 12 / 39）——原因未知**：排程有跑（`scan_model_connectivity --stale-minutes 60`），但 34 顆 vLLM 一筆都沒有。可能是不 probeable、probe 在測到 round trip 前就失敗（`0227` 明說此時留 NULL 不假造 0）、或掃描沒選到這批。後果：純地端池的 Latency first 連第三訊號都沒有，只剩進程內 EWMA（重啟歸零）。**2026-09-04 下午查明**（`路由v2.md` §16.20.1 #9）：(a) `dev.sh` 的 mvp compose **根本沒有** `scan_model_connectivity` 迴圈（只有 local-dev/pro/prod/enterprise/ami/unified 有）→ dev 從沒探測過、probe 表 0 筆；(b) `probe_model_connectivity` 對無憑證模型在發請求前就 fail-closed（`unhealthy`、`latency_ms=None`），dev 34 顆 vLLM 全無憑證，**prod 也一樣** | ~~已查明；兩個 issue 候選~~ → **✅ 2026-09-07 兩者皆解**：dev-mvp 掃描迴圈 #4311、無憑證改匿名探測 #4315（§13） |
| 4 | `routing_strategy` 欄位名裝「難度判定」的命名債（D8 接受；API alias `difficulty_classifier` 可後補） | 另案 |
| 5 | ~~#4099 待 merge / main 樹殘留~~ → 皆已解（`路由v2.md` §16.9.3 #4d） | 完成 |
| 6 | dev 全矩陣（3 難度判定 × 4 目標）2026-09-03 實測：`response.model` 恆為 proxy alias、執行模型只能從 audit `model_uuid` 對——定址文件 §2 的「三個確認管道」第 1 條對 opaque proxy 無效，只剩 audit | 文件已註（本列） |
| 7 | `routing.db`（gateway 可寫層）被容器 recreate 清空；`none` 的 PUT 拒 `keyword_tier_rules_enabled` | ~~issue 候選~~ → **✅ 2026-09-07**：`routing.db` volume #4311、`none` 收分類器鍵 #4309（§13） |
| 8 | Latency 不做持久化 seed（D24）、Energy 不做量測層（D17，`joules_per_output_token` 仍 0/73）——皆為明文決定不做，不是遺漏 | 已決定不做 |
| 9 | PRD-303 INV-303-6 的 CI gate 未加：要擋的儀表板／歸因模組還不存在，加了會是永遠不可能變紅的 vacuous gate → tracking issue **#4152**，隨儀表板落地 | 追蹤中 |
| 10 | **2026-09-04 交付 review 的三個修正 PR 待 merge**：#4201（gateway/routing，SPEC-276 Rev.8：ε seed 加 salt、failover 不探索、取樣窗、tracker 丟壞樣本）· #4202（Console）· #4203（IAM，**動了 openapi digest，merge 後 IAM 與 gateway image 要同批部署**）。#4201 與 #4203 都改 SPEC-276 但不同段，先 merge 哪個都行 | ✅ 已合併（#4201 `571a9cacf`／#4202 `c430a3eef`／#4203 `70a44d4de`） |
| 11 | review 看到但沒修的 smell（gateway parser `int(last_latency_ms)` 截斷、`SERVING_LOCALITIES` 兩份詞表、PATCH 404/422 在租戶檢查前、`desired_version` 改了不重算估算、`latency+none` 改比例會 full-replace 掉分類器 keys、兩種 TTFT 定義…）完整清單在 `路由v2.md` **§16.20.4**（#4100 已於同日 merge，`5af92c016`） | ~~issue 候選~~ → **✅ 2026-09-07 全數處理**：gateway parser / 同分 / degraded #4317、IAM 詞表 / PATCH 順序 / `desired_version` #4321、Console 三項 #4318；兩種 TTFT 寫進 SPEC-276 Rev.12（§13） |
| 12 | **Latency first 第二訊號 `avg_latency_ms` 冷啟動偏差**（2026-09-08 dev 實測 + 真元件 probe）：`ModelHealthTracker.ewma_latency_ms` 初值 0.0、α 0.1 → 第 n 筆樣本只有真值的 (1−0.9ⁿ)，22 筆才到 90%；**樣本最少的模型看起來最快**（gpt-5.4 實測 1.3–3 s 卻以 409 ms 三連勝 0.6–0.9 s 的 gpt-4o），贏了之後 EWMA 爬升→換人→輸家凍在低估值→震盪。TTFT tracker 首筆直接初始化、沒這問題。`路由v2.md` §23.4 #1 | ✅ #4395 merged |
| 13 | **credential provider mismatch 只在 gateway-validate 才擋**：IAM 讓 `openai` 憑證綁 `openai_responses` 模型（建立 / PATCH 200、探測用它成功標 healthy），但該 app 每個請求 validate 500「IAM service error」。dev 的 `gpt-4.1-nano` / `gpt-4o-mini` 曾是這狀態（nano 已改綁 `openai_responses` 憑證）。`路由v2.md` §23.4 #2 | ✅ #4400 merged |

---

## 12. 後續 campaign：`/v1/responses` 治理對稱 Phase 2（ADR-437 / SPEC-282 / PRD-157 §10，2026-09-06）

> 完整紀錄（六缺口盤點、四題拍板、機制、§8.1 證據、坑、merge 序）在 `路由v2.md` **§17**；本節只寫**對模型定址視角**有影響的部分。七 PR 全部 squash merge 進 main（#4238 docs、#4239 骨架、#4240 audit 落盤、#4241 routing、#4242 admission、#4243 output rail、#4246 retry/failover；串疊基底 #4198）。~~**尚未部署 dev / rel / prod**~~ → 2026-09-07：dev 已跑這七個 PR 的 code 並翻 enforce（§12.6）；收尾的另七個 PR（#4272→#4281）在 main、**尚未進 dev 樹**；rel / prod 未動（2026-10-14 註：程式已在 rel 與 prod 分支；Responses 的 Policy Kernel enforce 翻轉仍未做，#1060 開著、compose 預設 `shadow`）。

### 12.1 `/v1/responses` 現在怎麼決定跑哪一顆

`model` 在此面**必填**（沒有省略路徑，`response.model` 永遠回客戶送的值——§3.3 那句不變（2026-10-14 註：ADR-221 Amendment B／#6161 起此句只對 opaque app（回 `application_code`）與 pin（回自己指名的名字）成立；menu app 用 app code 或 default 定址時，每個事件寫實際跑的模型，R3 後寫替代模型。例外見 SPEC-312 C-312-39：`X-Xparse-Model-Default` header 在串流開始前就算好，R3 後仍是 primary；第一個事件前就失敗、gateway 自己合成的 envelope 沿用請求的 `model`。目前在 rel，prod 還沒有））。決定「誰執行」的來源恰好三種（`responses_routing.py`）：

| 客戶送的 `model` | 有 `previous_response_id`？ | 來源 | 行為 |
|---|---|---|---|
| 真模型名（`select_available=true`） | 任意 | **pin** | 精確執行；resolver 不呼叫；**不 failover**（同 chat INV-138-16） |
| `application_code` / `default` / sentinel | 有 | **binding** | 模型取自**綁定列**（`model_uuid`+`provider`），不重選——否則 routing 過的 chain-head 續輪會 409 `backend_or_model_drift`；綁定過期／刪除仍 410（不會靜默變新對話） |
| `application_code` / `default` / sentinel | 無 | **resolver** | 同 chat 那條 `Resolver`：候選 = 該 app 生效序中 provider ∈ `RESPONSES_PROVIDERS` 的成員（2026-10-14 註：翻譯軸 #6158／#6190 起改問 `translation/capabilities.serves()`，在 rel、prod 還沒有。有本面候選就只在其中選——P3 起 `openai` 列若在 OpenAI 官方 API 上也算原生 Responses；沒有才用延伸候選（Claude、其他 chat 家族，無狀態翻譯）。帶 `previous_response_id`／`store:true` 時只留能存狀態的模型，否則 400 `stateful_responses_unsupported`）；`routing_strategy` 定合格集、`routing_objective` 挑；`input` 轉成 messages 餵 complexity classifier（轉不動只是不分級，永不 4xx） |

幾個定址上的差別要記住：

- **`none` + `quality` 逐位元等於舊行為**（序首），所以沒有 feature flag——app 自己的兩軸就是開關。
- **`llm_judge_routing` 在此面不叫 judge**：短路退 heuristic，audit `judge.source = judge_surface_unsupported`（judge worker 是 chat 形狀；Responses-only 池的 auto judge 會選到 Responses 模型）。所以 judge app 的 PRD-308 A9「chat / responses 同 evidence」**不保證**——#4248 要把 judge 池改從 chat surface 選。（2026-10-14 註：#5804 起此面的 `llm_judge_routing` 會真的呼叫 judge，#4248 已關；續輪仍跟綁定、不判級）
- **候選集只有 Responses-surface 模型**：一個 Model row 只屬一個 surface，所以「chat 與 responses 選到同一顆」字面不可能；A9 已改寫為「同 strategy / objective / selection evidence，`winner_model_id` = 對 Responses 候選集直呼 resolver 的結果」。（2026-10-14 註：翻譯軸 #6158／#6190 起一顆模型可服務多個面——chat 能用 Responses-only 模型，此面能用 Claude／chat 家族模型（延伸候選，原生優先）；R3 用完本面候選後，`cross_surface_fallback`（預設開）允許時可換到延伸候選。在 rel、prod 還沒有）
- 執行模型的確認管道與 chat 相同：opaque 時看 audit——`routing_decision_recorded`（`endpoint="/v1/responses"`、`winner_model_id`）與 `responses.created.model_uuid`（= 實際執行、failover 後 = 替代模型）。

### 12.2 `sort_order` 的第三條路徑（§2.5 #3 更新）

§2.5 說 `sort_order` 是三條執行路徑的共同輸入。第三條「Responses 預設」現在拆成兩層：**首輪**由 resolver 在生效序上決定（`quality` 落點 = 序首；其他目標 = 合格下限），**續輪**綁死在綁定列。**failover 降級序**（§2.5 #2）也對此面生效：first event 前 provider 503/429 → `resolve_fallback` 排除失敗集後重跑同一策略（Cost 下是次便宜、Latency 次快，`quality` 才是沿序下一顆）；PIN 與續輪的候選集為空 → **結構上不會 failover**。

### 12.3 其他跟 chat 對齊的治理面（定址之外，但操作者會撞到）

| 面 | 現在的行為 | 可觀察 |
|---|---|---|
| Admission | Responses 流量**首次**受 app rate-limit / concurrency policy（或 DEFAULT_POLICY）管；ceiling 滿時先收 `: xparse-queued` 再 `: xparse-started` comment frame；回應 header 含 `X-Trace-Id`、`x-ratelimit-*` | audit `REQUEST_REJECTED` / `REQUEST_QUEUED`、`EXECUTION_STARTED/COMPLETED/FAILED`（`routing_mode=responses_passthrough`） |
| Output guardrail | policy `output_redaction_mode=stream`（預設）：全文照出，只 log `output_redaction_uncovered` + shadow 觀察；`buffer`：hold **所有帶文字的事件**（delta / done / `content_part.done` / message item 的 `output_item.done`——2026-09-07 前只 hold 前兩種，後兩種帶全文照出，等於沒擋）、全文檢查、pass 依 provider 順序發合成 delta + patched done/part/item/completed；block 依 SPEC-213 presentation：**error** → `event: error` 終止、無 `response.completed`；**graceful**（#4250）→ 拒答 delta/done + 原生 `event: response.incomplete`（`status=incomplete`、`incomplete_details.reason=content_filter`），無 error frame。兩種都 `mark_deleted`（續輪 410）+ best-effort provider `DELETE /responses/{id}`（#4251，≤5s，`store:false` 跳過）| audit `responses.output_blocked`（`binding_deleted`、`provider_deleted` / `provider_delete_status` / `provider_delete_error`）、`audit.guardrail.*`、`EXECUTION_COMPLETED.finish_reason=content_filter` |
| Retry / failover | first event 前 R1（`app_type=llm_proxy/agent` 3 attempts，`chat` 1 = 關）+ R3；之後 terminal `event: error upstream_provider_error` | `EXECUTION_RETRY_ATTEMPTED`、`PROVIDER_FALLBACK` + 第二筆 `routing_decision_recorded` |
| Policy Kernel | ~~仍 **shadow**~~ → **dev 已 enforce（2026-09-07）**；rel / prod 仍 shadow（五個 tier compose 顯式預設 `shadow`）；差別是 `audit.policy.boundary_shadow_would_block` **終於落盤**（進 Console「Policy Violation」filter、帶 `api_key_uuid`）。翻 enforce 依 runbook `responses-boundary-enforce-cutover.md`，先跑 `bustream/scripts/responses_boundary_census.py` ≥3 天。enforce 後 `profile_type=on_prem` 的 app 在此面**永遠** 403（RESPONSES_PROVIDERS 全 cloud）（2026-10-14 註：P8／#6190 起地端模型也能經翻譯回答此面，`on_prem` app 不再必 403；R3 替代模型逐一過 Kernel。沒綁憑證的地端模型在 main 由 #6489 修好，rel 仍 500），Console 建 proxy 要送 `hybrid`（同 §7 model ping 那個坑；**2026-09-22 起不需要了**——#5233 讓 proxy 列的 `profile_type` 惰性、probe 投影 `hybrid`；**consumer app** 仍要 `hybrid` 才能上 Responses 面） | 普查腳本輸出 `application_code | profile_type | would_block | distinct_keys | error_codes | action` |
| agent-mode | `bustream.agent_mode=true` → 400 `agent_mode_not_supported`（不移植 chat 的 agent dispatch） | — |

### 12.4 給操作者（增量）

| 想要 | 做法 |
|---|---|
| Responses 首輪跟 chat 一樣選模型 | 不用做——app 的 `routing_strategy` / `routing_objective` 已對此面生效；只有 `llm_judge_routing` 例外（退 heuristic，#4248）（2026-10-14 註：#5804 起此面的 `llm_judge_routing` 會真的呼叫 judge，#4248 已關；續輪仍跟綁定、不判級） |
| 續輪為什麼沒重選 | 設計：`previous_response_id` 的續輪跟綁定列的模型；要換模型就開新對話（不帶 `previous_response_id`） |
| PIN 的模型掛了為什麼直接失敗 | 同 chat：指名 = PIN，不 failover；要 failover 就用 `application_code` 定址且池 ≥ 2 顆 Responses 模型（2026-10-14 註：翻譯軸 #6158／#6190 起一顆模型可服務多個面——chat 能用 Responses-only 模型，此面能用 Claude／chat 家族模型（延伸候選，原生優先）；R3 用完本面候選後，`cross_surface_fallback`（預設開）允許時可換到延伸候選。在 rel、prod 還沒有） |
| 開 output 攔截 | 把 guardrail policy 的 `output_redaction_mode` 設 `buffer`（per-policy opt-in，TTFT 變成整段 hold）；`stream` 只觀測不擋。**2026-09-07 前這個欄位在 IAM spec 根本不存在、gateway adapter 也不帶，設了也沒用**；#4279 起 versioned policy spec（v1/v2）可寫 `output_redaction_mode` / `block_presentation`（closed literal；fold buffer-wins / child-overrides），目前只能經 `POST /iam/policies/{uuid}/versions` 的 spec JSON，Console 表單是 #4285 |
| 擋下來要「拒答」而不是 4xx | policy `block_presentation=graceful`（#4279 可寫）→ input block 回 200 合成 stream（`resp_xpgrace_*`，末事件 `response.incomplete`）、output block 回拒答 + `response.incomplete`；classifier rails（content_filter / on_topic）**未授權時預設 graceful**，PII / word_filters 要顯式設 |
| 客戶送了 `instructions` 卻沒效果 | 2026-09-07 前被 pydantic 靜默丟掉（#4249）；現在 verbatim 轉發、complexity classifier 看到 system turn（`has_system_prompt` 變 True，分級可能改變）、word_filters 偵測面含它（不 mask）|
| 看 shadow 會擋誰 | dev（無 xparse-audit）：`python bustream/scripts/responses_boundary_census.py --source jsonl --evidence-dir ./var/audit/evidence`；rel/prod：`--source pg --dsn …` 或 `--source http --base-url … --api-key …` |
| 429/503 為什麼變多／變少 | admission 首次生效：先查 app 的 rate-limit policy 與 audit `REQUEST_REJECTED`；rel 先觀察再上 prod |

### 12.5 沒解決的事（定址視角）

| # | 事項 | 性質 |
|---|------|------|
| 1 | ~~**未部署**~~ → dev 已 pull 到 `f0fada48e`（含收尾七 PR + #4373/#4374/#4375/#4376/#4377）並 recreate IAM + gateway；**2026-09-08 後 dev 又落後**：#4378 / #4385 / #4391 進 main（鏈尾 `7f4cfa0c9`），主樹停在 `96fee004a`、gateway 容器起於 #4378 之前 → pull + recreate gateway（§16）；**rel / prod 未動**（2026-10-14 註：程式已在 rel 與 prod 分支；Responses 的 Policy Kernel enforce 翻轉仍未做，#1060 開著、compose 預設 `shadow`）；PR-4 admission 是行為變更 | 部署窗口 |
| 2 | ~~**dev e2e probe 未跑**~~ → ✅ A19 / A20 / A21 / R1-R3 / N9 / P-ADM-3（§12.6）＋ **A22–A25**（2026-09-07 晚，§15；#1060） | 完成 |
| 3 | ~~enforce 翻轉 ops-gated~~ → ✅ **dev 已翻**（2026-09-07，Peter 拍板跳過 ≥3 天）；rel shadow ≥7 天 → rel enforce → prod 照 runbook，核准附 #1060 | Peter / ops（rel/prod） |
| 4 | ~~ADR-437 `Proposed → Accepted`、SPEC-282 `Draft → Active`、`routes/responses.py` 過期 docstring~~ → ✅ **PR #4385 已 merge**（2026-09-08 00:54Z） | 完成 |
| 5 | judge 池改 chat surface（#4248，不做）（2026-10-14 註：#5804 起此面的 `llm_judge_routing` 會真的呼叫 judge，#4248 已關；續輪仍跟綁定、不判級）；semantic cache（#4247，deferred by design）；~~#4282 / #4284 / #4285 / #4286~~ → ✅ #4376 / #4378（09-08 00:47Z merge）/ #4377 / #4375；**#4283 留** | backlog |
| 6 | ~~`test_spec213_graceful_route.py` ×3~~ → ✅ #4281；~~`test_responses_content_capture_2765.py` ×7~~ → ✅ #4375 | 完成 |

### 12.6 2026-09-07 收尾增量（定址視角）

> 完整紀錄（盤點三分類、dev ops 細節、假 provider、坑、指令）在 `路由v2.md` **§18**；這裡只放定址／操作者會撞到的。

| 面 | 現在的行為 | 可觀察 |
|---|---|---|
| `response.model` 改寫 | **每個**帶 `response` envelope 的事件都改寫成客戶送的 `model`（原本只蓋 created / completed，`response.in_progress` 把真後端模型名漏給 opaque app 的 client——dev probe 抓到）（2026-10-14 註：ADR-221 Amendment B／#6161 起只對 opaque app 與 pin 成立；menu app 用 app code 或 default 定址時，每個事件寫實際跑的模型，R3 後寫替代模型。例外見 SPEC-312 C-312-39：`X-Xparse-Model-Default` header 在串流開始前就算好，R3 後仍是 primary；第一個事件前就失敗、gateway 自己合成的 envelope 沿用請求的 `model`。目前在 rel，prod 還沒有） | wire 上任何一行 `"model":` 都不會是後端名 |
| provider 斷線 | 中途斷線 / 連不上 → `WorkerError(503)`：first event 後 terminal `upstream_provider_error`（原本 `internal_error`），first event 前可 R1/R3；**乾淨 EOF 無 terminal 仍靜默結束**（#4282） | `EXECUTION_FAILED error_type=worker_error` |
| `param_*` / actuals | `EXECUTION_*` 帶 chat 同名 `param_max_tokens` / `param_temperature` / `exec_*`（failover 後是替代模型的）；完成後回寫 `routing_decision_log` 的 `actual_*_tokens` / hard-constraint（`incomplete` = chat 的 `length` 豁免） | audit `extra.param_*`；`routing.db` row 不再空 |
| `instructions` | verbatim 轉發；classifier 看到 system turn；word_filters 偵測面含它 | `routing_decision_recorded.input_summary.has_system_prompt=true` |
| dev 上的 probe 實體 | `resp_probe_proxy`（2 顆假 `openai_responses` 模型 → `host.docker.internal:18080`）、`resp_probe_hybrid` / `resp_probe_onprem` + native key、rate-limit policy ceiling=1、credential `fake-openai-responses`；名稱皆帶 `[__probe__]`，A22–A25 跑完再清 | dev IAM SQLite |
| Gateway 路徑 | `bustream/` → `apps/gateway/bustream/`（#4236，2026-09-07）；本文 §1–§12.5 的 `bustream/...` 路徑一律加 `apps/gateway/` 前綴；dev-mvp compose 的 gateway mount 已由 #4275 改、IAM mount 由 #4272 改 | — |


---

## 13. 後續 campaign：Routing Objective 收尾（2026-09-07；完整紀錄 `路由v2.md` §19）

> 只放定址／操作者會撞到的；機制、驗證、坑在 `路由v2.md` §19。**八 PR 已於 2026-09-07 11:52–12:09Z 全部 merge、內容核對在 `origin/main`（§19.3a）**；但 **dev 尚未 pull / recreate**，下表是 main 的行為，任一環境要看到它得先更新（#4309 動 contract → IAM + gateway 同批）。

| 面 | 現在的行為（main；環境更新後生效） | 可觀察 |
|---|---|---|
| `routing_strategy=none` 的 `routing_parameters` | 接受 complexity / judge 的鍵為 **inert**（#4309）：app 切到 `none` 後存量 `keyword_tier_rules` / `judge_model_uuid` 可原樣 PUT 回去、不再 400；不填任何外來 default（只有 `reliability_tier_threshold` 會被補 0.5）。§11.5 #7「`none` 的 PUT 拒 `keyword_tier_rules_enabled`」消失 | `GET /iam/applications/{uuid}` 讀回鍵仍在；gateway 對 `none` 完全不讀這些鍵（決策不變） |
| Console `latency + none` 改探索比例 | 從 `{...stored}` 起、保留全部既有鍵（#4318，**要 #4309 先部署到 IAM**） | Contract preview 顯示完整 dict |
| Console 價格欄 | 只有輸出價 → `— / 0.6 $/M`（不再是 ` / 0.6`）；探索比例顯示一位小數（0.123 → 12.3%）；zh-TW `未設價` → `未定價` | — |
| 「探測」欄（`last_latency_ms`） | 無憑證的 `vllm` / `openai_compat` 模型改**匿名探測**（#4315，ADR-314 §2D / INV-314-18）：200 → healthy + RTT；401/403 → unhealthy、`last_error = Credential required: …`、**RTT 仍記**。純地端池的 Latency first 第三訊號從此有燃料；其他 provider 無憑證維持 `Credential unavailable` | Model settings / proxy Models tab 的探測狀態；`iam_model_connectivity_probe` 有列 |
| dev 的探測 | dev-mvp 新 `xparse-conn-scan` service 每 5 分鐘跑 `scan_model_connectivity --stale-minutes 60`（#4311）；§11.5 #3c 的「dev 從沒跑過掃描」消失 | `docker ps` 多一個 `xparse-conn-scan` |
| `routing.db` | 每個 tier 一個共用 `xparse-routing-db` volume（#4311）；gateway recreate 不再清 `routing_decision_log`、EWMA pre-warm 有種子；§11.5 #7 前半消失。`uninstall.sh` 不帶 `--keep-data` 會刪 | `docker volume ls` |
| `PATCH /iam/models/{uuid}` | 跨租戶呼叫者一律 **403**（#4321；原本 bucket-A 欄位可用 404/422 探 model 存在與否）；`serving_locality` 詞表單一來源；`energy_structural_estimate` 非有限值一律 NULL；**deployment 切 `desired_version` 時**，估算若是出生值（NULL 或等於舊版 spec 算出的值）自動重算、operator 覆寫值保留並 log（SPEC-276 OBJ-E3） | IAM log `energy estimate recomputed / kept (operator override)` |
| D-E2 盤點 | `python manage.py inventory_serving_locality`（#4319）取代 runbook 那行漏 NULL endpoint 的 SQL：列 `provider=vllm AND onprem` 每列的 endpoint 分類 / deployment / created_via / credential / 估算 / 建議；第二段列 onprem 無「資源規模」的模型；`--apply` 只把「公網 FQDN 且無 deployment」改 cloud | 表 / `--json` |
| gateway 對 IAM snapshot 的容錯 | 五個 optional 訊號欄（`last_latency_ms` / `energy_structural_estimate` / `cost_per_*` / `joules_per_output_token`）壞值只丟該欄 + warning，不再 500 整把 key（#4317） | gateway log `ignoring non-numeric routing signal` |
| 非串流 failover | 不再被 `deps.health_tracker` 閘住（#4317）：self-host llm_proxy 非串流也會 R3 換手 | audit `provider_fallback` |

**§11.5 對照**：#3c（dev 沒掃描 + 無憑證 fail-closed）→ #4311 + #4315；#7（`routing.db` 被清 + `none` 拒兩鍵）→ #4311 + #4309；#11 的 smell → #4317 / #4321 / #4318。羊群/擺盪 → **#4314**（延後）。

---

## 14. 後續 campaign：Latency first 訊號過期 + `serving_locality` enum（2026-09-07 下午；完整紀錄 `路由v2.md` §20）

> 只放定址／操作者會撞到的。~~PR #4373 / #4374 已開、未 merge~~ → ✅ **皆已 merge，dev 已部署並驗過**（§15）；rel / prod 未動（2026-10-14 註：程式已在 rel 與 prod 分支；Responses 的 Policy Kernel enforce 翻轉仍未做，#1060 開著、compose 預設 `shadow`）。#4374 動 openapi digest → IAM + gateway 同批。

| 面 | 現在的行為（merge 後） | 可觀察 |
|---|---|---|
| Latency first 的兩個流量訊號（`avg_ttft_ms` / `avg_latency_ms`） | 某顆模型**超過 10 分鐘**沒有新的成功樣本，它的 EWMA 在路由決策裡視為**沒有資料**（SPEC-276 Rev.13，常數 600 s、不開 knob）。效果：長期沒被選到的模型不再拿一小時前的舊值跟 live 模型比（#4314「凍結輸家」）；它一有流量（含 5% 探索）就恢復參賽。若因此沒有任何候選帶該種訊號，決策退到下一種（TTFT → 整體延遲 → 探測 ping）；全部過期 → 退回 Quality 序 | audit `routing_decision_recorded.decision_evidence.latency_participant_count` 少一顆；閒置後 `selection_reason=no_latency_data_fallback` 重現；Console **看不到**（EWMA 在 gateway 記憶體，§11.4「尚未探測」語意不變） |
| 探測欄 `last_latency_ms` | **不受**上面的 10 分鐘窗約束（它由 IAM 掃描依自己的節奏刷新，dev 5 分鐘一輪、§13） | 同 §13 |
| `serving_locality` 在 openapi | `ModelResponse` / `ModelSourceSummary` 為 `enum: [cloud, onprem]`（DB 出現詞表外的值會 500 而非漏字串）；`PATCH /iam/models/{uuid}` 的 request 也標 enum，但送錯值仍是 **400 `INVALID_SERVING_LOCALITY`**（不是 422，契約不變） | `GET /iam/openapi.json` |

**§11.5 / §19.5 對照**：羊群/擺盪 → 「凍結」那半由 #4373 解；「贏家換手時整群跟著跳」（incumbent 留任）仍在 #4314 延後。

---

## 15. 後續 campaign：dev 驗證 + `/v1/responses` 收尾（2026-09-07 晚；完整紀錄 `路由v2.md` §21）

> 只放定址／操作者會撞到的。

| 面 | 現在的行為 | 可觀察 |
|---|---|---|
| §13 的八項在 dev 實測 | (B) `none` 收分類器鍵、(C) Console `latency+none` 改 ε 保留鍵、(D) 無憑證 vLLM 匿名探測拿到 RTT、(F) `inventory_serving_locality`、(G) `routing.db` recreate 不歸零 — **全部通過**；§14 的 Rev.13 訊號過期也已在 dev 驗（閒置 714 s 後退到探測 ping） | #4314 comment |
| dev 的 34 顆地端 vLLM 為何永遠沒 RTT | `inventory_serving_locality` 一跑就看到：30 顆 endpoint 是 `asd` / `12` 這種假值（`needs_human`），只有 3 顆是真的內網 URL、1 顆指 api.openai.com（建議改 cloud）。不是探測壞，是資料髒 | 命令輸出 |
| `/v1/responses` output 攔截 | **只有 classifier 會擋**（`check_output` 是 V1 passthrough）；`word_filters` / `pii` 只在 input 端。A22–A25 全部通過（#1060） | `guardrail.output_check` verdict |
| clean EOF（#4282，#4376 已 merge） | provider 送了 `response.created` 後乾淨關閉 → `event: error truncated_stream` + `EXECUTION_FAILED`，不再靜默結束 | audit `error_type=truncated_stream` |
| input classifier（#4284，#4378 已 merge 09-08 00:47Z；dev 容器尚未 recreate） | responses 在 input rails 後也跑 chat 同一支 classifier input stage；graceful → `resp_xpgrace_*` | `guardrail.input_check` 多一筆 classifier |
| Console guardrail 表單（#4285，#4377 已 merge） | `output_redaction_mode` / `block_presentation` 可在 Policies 頁設（`inherit` = 不送鍵） | — |
| 文件狀態（PR-F #4385，已 merge 09-08 00:54Z） | ADR-437 Accepted、SPEC-282 Active；PRD-157 §10.2 重號的 A24/A25 改 A29/A30 | — |

---

## 16. 後續 campaign：`/v1/responses` 收尾——兩個碼面缺口（2026-09-08；完整紀錄 `路由v2.md` §22）

> 只放定址／操作者會撞到的。**PR #4391 已 merge `7f4cfa0c9`（2026-09-08 01:15Z）；~~dev 尚未 pull / recreate~~ → dev 於 01:52Z 全 stack recreate、bind-mount 已是 `7f4cfa0c9`，§17 已在 dev 真流量驗過 #4378 與本節兩項**；下表是 main（= dev）的行為。只動 gateway，無 IAM / contract / migration。

| 面 | merge 後的行為 | 可觀察 |
|---|---|---|
| output 端 guardrail block 的 `error.code` | `/v1/responses` buffer 模式 block（error 呈現）的 `event: error` frame、以及 chat 非串流 classifier output block 的 451 envelope / graceful 200 body，`code` 都是 **`output_blocked`**（SPEC-106 §3.3 本來就有的詞彙）。之前一律 `input_blocked`，客戶端會以為是自己的 prompt 被擋。input 端不變（仍 `input_blocked` / `word_filter_match`）；fail-closed 仍 `guardrail_service_unavailable` | wire `error.code`；audit `responses.output_blocked.reason_code=output_blocked` |
| provider 自己宣告失敗（`response.failed` / `error` 事件） | wire 不變（那幀仍 verbatim、仍是最後一幀、不補第二個 terminal）；audit 從 `EXECUTION_COMPLETED finish_reason=incomplete` 改為 **`EXECUTION_FAILED error_type=provider_response_failed`**，`error_message` = `<event> <code>: <message>`（例 `response.failed server_error: upstream`）。不記 health / routing actuals；binding 列保留（provider 端狀態歸 provider） | audit `execution_failed`；查 FAILED 的儀表板現在看得到 provider 故障 |
| 文件 | PRD-157 §10.3「provider DELETE follow-up」與 SPEC-282「`instructions` follow-up」兩條已交付卻沒劃掉的 non-goal 已劃 | — |

**還沒做 / 不做**：#4283 semaphore live resize（要先定在途請求語意）· #4248 judge 池（不做）（2026-10-14 註：#5804 起此面的 `llm_judge_routing` 會真的呼叫 judge，#4248 已關；續輪仍跟綁定、不判級）· #4247 semantic cache（by design）· #4314 案 2 · rel / prod 部署與 enforce 翻轉（ops，#1060）（2026-10-14 註：程式已在 rel 與 prod 分支；Responses 的 Policy Kernel enforce 翻轉仍未做，#1060 開著、compose 預設 `shadow`）。

---

## 17. 後續 campaign：dev 直打 API 全矩陣驗證（2026-09-08；完整紀錄 `路由v2.md` §23）

> 只放定址／操作者會撞到的。探針程式與假 provider 在 `~/Desktop/testing/`（`routing_responses_probe.py {routing|responses|guardrail|real}`），證據全從 gateway evidence JSONL 對 `x-request-id`。

**定址視角坐實的事（chat `gpt_4o_816e`，池 N=5；responses `resp_probe_hybrid`）**：

| 面 | 實測 |
|---|---|
| 兩軸 × 三難度判定（chat） | complexity / none / llm_judge × quality / cost / latency / energy 全部照 SPEC-276：Cost 的合格集是 `order[0 : anchor+width]`（COMPLEX 在 N=5 是 order[0:3]，含帶尾 luna，所以 Cost 下 COMPLEX 落最便宜的 luna）、`effective_cost` 對到小數；Energy 全雲端 → quality 落點；judge × cost 疊加正確（judge COMPLEX → 合格集 3 顆 → cost_min） |
| 帶內位移 | **ZH4（0.425）在 N=5 落 luna（position 2、`band_offset=1`），不是帶首 gpt-5.4**——問題集 §1 的 N=4 對照表過期，Rev.4 已補 §10 |
| 切設定 | PUT 後 0.3–32 s 生效（validate cache TTL），不用重啟；dev 的 `evict_scope_from_gateway` 沒作用（§11.5 #10 那條既有落差） |
| `/v1/responses` 定址 | opaque 首輪跑 resolver（N=2：SIMPLE→beta、REASONING→alpha）、續輪 0 決策跟綁定列、pin 不記決策、`model=default` 同 app code、judge 短路 `judge_surface_unsupported`、未設價 → `cost_unpriced_assumed_zero`；R3 failover（alpha 503 → beta）、admission 排隊、on_prem 403、agent_mode 400 全對 |
| 失敗路徑 audit | socket 斷 → `worker_error`；clean EOF → `truncated_stream`（#4376）；**provider `response.failed` / bare `error` → `provider_response_failed`**（#4391）；output block → `event: error code=output_blocked`（#4391）+ `responses.output_blocked` 記 provider DELETE 200；input classifier stage → 451 `input_blocked`（#4378） |
| 真 provider | `gpt-4.1-nano`（`openai_responses`）串流 / 續輪 / pin / `instructions` 全通——**前提是憑證 provider 要對**（見 §11.5 #13） |

**這輪新抓到、還沒做的（定址視角）**：

| # | 事項 | 性質 |
|---|---|---|
| 1 | Latency first `avg_latency_ms` 冷啟動偏差（§11.5 #12） | ✅ **#4395 merged**，dev 驗過（冷模型首筆 942 ≈ 實測 941） |
| 2 | credential provider mismatch 寫入面不擋（§11.5 #13） | ✅ **#4400 merged**，dev 驗過（PATCH / POST 400、inventory 清空） |
| 3 | error envelope 三種形狀：HTTP 422 / 451 的 `type` 落 `internal_error`（ADR-390 `ERROR_MAPPING` 沒這兩碼，並剝掉 `policy_uuid` / `content_filter_level`）；route 自回的 404 / 410 沒 `type`；SSE error frame 才是 SPEC-106 §3.3 的 `guardrail_violation` 形狀。`word_filter_match` 也不在 SPEC-106 code 閉集 | ✅ **#4398 merged**（422 / 404 dev 驗過）+ **#4409** 補 `responses_pipeline.py` 三個 body（agent_mode 400 merge 後仍無 `type`） |
| 4 | `/v1/responses` 首事件前全候選失敗 → HTTP 200 + `event: error`——查證後**串流 chat 也一樣**，503 只在非串流 chat | ✅ **#4417 merged**（SPEC-282 Rev.5 RSP-RES-8 + docstring；非 bug） |
| 5 | pin 的 evidence：chat 記 `routing_decision_recorded`（candidate_count=1），responses 不記 | ✅ **#4419 merged**——文件化為已知差異（SPEC-276 OBJ-A4 / SPEC-282 RSP-AUD-7：跨面數決策要 `candidate_count > 1`）；收斂等 PRD-303 #4152 定口徑 |
| 6 | `/v1/messages` 旗標 dev 未開，兩軸在 Anthropic 面未驗 | ✅ dev 開旗標後 11 案全過（`路由v2.md` §23.12）；該面沒 `x-request-id`、error message 是 dict repr → **#4413 merged**，merge 後 dev 驗過 |
| 7 | dev IAM 每個 admin API 呼叫都噴 `Policy resolution failed KeyError: 'rule_id'` | ✅ 6 月 demo seed 殘留 62 筆，已備份刪除；**#4415 merged**，loader 報出是哪一筆（`路由v2.md` §23.13） |

## 18. 後續 campaign：定價撰寫面收斂到 Model Pool（2026-09-08，PR #4443；PRD-272 §3.5 修訂 / ADR-300 Amendment L / ADR-430 Amendment A）

> Peter 拍板：「把整套定價系統搬到 Models——它是唯一能動 price 的地方；LLM Proxy 和 Application 只能是價格接收者。」資料層本來就是 model-scoped（`ModelPriceVersion` FK `Model`，ADR-300 §2.-1 單一價格概念），這輪收的是**入口**與**殘留寫入路徑**，不是資料模型。

**為什麼**：改價入口散在三處——proxy Models tab → Edit model 的 Prices 區段、proxy Models tab 的「套用公開定價」整池批次 dialog（§11 / #4092）、Model Pool Detail → Settings 的 Prices 區段——而 Register 從來不寫價；後端還留著 `ApplicationModel.cost_per_*` 兩條寫入路徑（PATCH cost、bind body），runtime 自 2026-07-22 起就不讀、Console 也沒用，只剩管理面 echo。

**定址視角改了什麼**：

| 面 | 之前 | 現在 |
|---|---|---|
| 改價入口 | proxy Edit model 的 Prices 區段／proxy 批次「套用公開定價」／Model Pool Settings | **只有 Model Pool** `/models/{uuid}` → Settings → Prices（Cloud **與 On-Prem** 都掛，推翻 PRD-272「On-Prem 無 Prices」）；`tenant_admin`／`system_admin` 可寫，其他角色同一區塊唯讀 |
| 套用公開定價 | proxy Models tab 整池批次 dialog | Model Pool Settings Prices 的**單一模型**按鈕：僅 Cloud、快照有公開價、且目前無區間覆蓋「現在」時顯示；確認才寫一筆 ~~open-ended~~ 段，走的是與手填同一條新增路徑（**Amendment N 起改寫一年期段**：`[今天, 今天+365d)`，API 已不接受 open-ended，見 §19 補記）。**§20 起再改**：移進價格編輯表單內的一列，按下只把四值**填進欄位**，不自己寫入、也沒有自己的窗 |
| Register | 不收價格 | Cloud／On-Prem 各加**選填** Price 步驟（Platform Settings 之後）：Cloud 預填公開價（可改可清空、一經編輯不再覆寫）；空白＝未定價不擋 Create；半填擋 Next；建立成功後以註冊時間為錨 `POST price-schedule`，失敗誠實 toast（不被「建立成功」掩蓋） |
| proxy Models tab | 可編價 | 只讀價格欄（`ModelSourceSummary.cost_per_*` 是 effective price 投影，保留）+ 列選單「到模型池設定價格」連結；Edit model dialog 只剩一行提示 + 連結 |
| application Models tab | 只讀價格欄（#4098） | 不變，未定價列多一個到 Model Pool 的連結；D28 hint 改指 Model Pool |
| 後端 | `PATCH /iam/applications/{app}/models/{model}` cost、bind／model-sources body `cost_per_*`、`ApplicationModelResponse.cost_per_*` echo、`iam.application_model.cost_updated` | 全拔；**IAM migration 0308** drop `ApplicationModel.cost_per_*`；PATCH → 405（路徑仍由 DELETE 服務）；bind body 帶價格 → 忽略（201、`price_source=unpriced`），**不是 422**（Ninja `extra="ignore"`、ADR-201 先例、避免 IAM→Console rollout 窗口打斷）；openapi 重產 + 五處 consumer digest 重釘 → **IAM 與 Console image 同批部署** |
| 不變 | — | 價格資料模型與四個 `/iam/models/{uuid}/price-schedule` 端點；wire 上 `cost_per_*` 仍是 Model schedule 的 effective 值；D28／D29 Cost pick 規則；INV-265-2 帳單 |

**操作者要知道的**：
- 想給雲端設價讓地端不再自動優先（D28）：現在只有一個地方——Model Pool → 該模型 → Settings → Prices，按「套用公開定價」或手填。proxy／application 頁的價格欄都只是顯示，點連結會帶你過去。
- 新建 Cloud model 時 Register 會直接把公開價帶進來，不要就清空；On-Prem 沒有公開價，要就自己填內部攤提價。
- `group_admin`／`tenant_auditor` 看得到價格表但改不了；**後端目前沒有角色閘**（只有 tenant 隔離），Console 藏按鈕不等於 API 擋了——server-side 403 是 follow-up（PRD-272 §9 #23）。
- 舊 client 若還往 `PATCH /iam/applications/{app}/models/{model}` 送價格會拿到 405；往 bind body 塞 `cost_per_*` 會被靜默忽略，看回應的 `price_source` 才是真相。

**驗證**：前端全套 1015 綠、五道 i18n gate 綠、新 CI gate `console-price-authoring-boundary-gate.sh`（價格寫入 hook 只能在 `models/` 路由；dogfood seeded import 變紅）；IAM 受影響 9 檔 112 綠（含 `test_openapi_contract`）、新 integration test 對真端點斷言 405／不落地／`FieldDoesNotExist`；根目錄五處 digest 契約 9 綠。**未做**：dev 手點規格驗證、FAE TC-276-U6 evidence run（spec 已改寫到 `fae/tests/console/infrastructure/apply-list-price.spec.ts`，含 `tenant_auditor` 唯讀負向）——PR 先掛 draft。

**坑**：
- IAM `_application_to_response` 對 consumer app 一律 `models=[]`（ADR-198 Phase 4），要驗 detail `models[]` 的價格投影得用 llm_proxy。
- TC catalog 的 `versionContracts[].from` 必須是 SemVer、`sources` 必須 `git:<sha>:docs/...`；main commit 不能捏成版本號（scoping standard §3.2）——本輪只更新 description／disposition，APPLICABLE 契約等發布版本對映後再登。改 catalog 或 `zh-TW.json` 後要照 README「先 commit 來源 → `--write` → commit 產物」重綁 workbook manifest，否則 Feature acceptance inventory job 會紅。
- M3 Fleet／Scheduler envelope 的 `docker build` 在 self-hosted runner 逾時／exit 100 是網路 flake（pin 檔連 build context 都不在），重跑即過。

**Follow-ups**：server-side 角色 403；mock 分支 `[model-id]/_components/price-schedule-section.tsx` + `modelPool.detail.prices` 29 鍵退場；GATE-TRACK marker 補 tracking issue；audit repo `docs/audit-events.md` 拔 `.cost_updated`。

## 19. 後續 campaign：定價撰寫面重構——成本準確性 × UI/UX（2026-09-09；ADR-300 Amendment M / SPEC-215 Rev.6 / SPEC-265 Rev.2 / PRD-272 §3.5.1）

> 起點是一顆 model 的 `GET /price-schedule`：兩段都有結束日（06-11→06-30、09-22→09-28），今天落在缺口、09-28 後永久無價，Cost first 當 $0；`9e-05` = $90/1M 疑似 per-1K 手滑且 input == output；cache read 0.5× 是 OpenAI 家族猜值。決策輸入在 `docs/草案/model-price.md`（D1–D9）與 `model-price-ui.md`，Peter 拍板後折進 ADR-300 Amendment M。**§18 收的是「誰能改價」，這輪收的是「填進去的數字算不算對」。**

**Peter 拍板的七條**：① 範圍順位 1–5 全做；② 三引擎分岔以 gateway 為準——`components` 非空且 `cache_write` 缺席或 `{per_ttl: []}` 皆 = 免費 0；③ 「指定日期起改價」做成 IAM 原子端點（X == 覆蓋段起點整段換價、缺口內只建一段到下一段起點、superseded+created 共用 operation_id）；④ `cache_write` 存絕對值但保留 `per_ttl` 陣列（B2），representation-only migration 就地改寫、不 append 版本（C-215-31 例外）、形狀防禦 + 冪等；⑤ 改 base Input 時 cache 絕對值為真相，只提示「倍率已從 0.1× 變 0.083×，要依原倍率更新嗎？」；⑥ 完全 not-wired 的 `line_items`／`currency` 逐位元 round-trip 放行、authoring 400；⑦ 快照 `cache_read == 0` 帶 0 寫成 `{flat: 0}`（明確免費），不可套 `_price_or_none`。

**定址／計費視角改了什麼**：

| 面 | 之前 | 現在 |
|---|---|---|
| cache read 價 | provider 猜值（openai 家族 0.5×，真值中位 0.1×） | 快照帶 LiteLLM 每模型真值（565/1013 有值）→ Console 組進 `pricing.components`；沒值才落 provider 預設，且 openai 家族預設校準 0.1（#4469） |
| cache write 儲存 | `per_ttl[{ttl, mult}]`，query time 乘 input | `per_ttl[{ttl, flat}]` 絕對值；gateway／IAM budget 副本／audit 三處讀 `flat`，mult-only band → 0 + warning（#4467、Audit#138） |
| 缺 `cache_write` component | gateway 免費、audit 全價（分岔） | 三引擎皆免費 0；`per_ttl: []` 同義 |
| `pricing` 寫入 | 裸 `dict[str, Any]`，`cache_raed` 照存 → 整顆 unpriced | 嚴格 `PricingSchema`（未知鍵 422）；`mult` 捷徑在寫入邊界物化成 `flat`；scalar ≠ component 鏡射 → 400 `pricing_scalar_component_mismatch` |
| `GET price-schedule` | 只回 segments | 加 `as_of`、`current_segment`、`gaps[]`（head／interior／tail，恰一個 `covers_as_of`）（#4465） |
| 改價從 X 日起 | 手動對齊兩段日期，失手就是缺口 | `POST /iam/models/{uuid}/price-schedule/reprice-from` 一個 transaction 截舊段＋開新段，新段繼承原 `effective_to`；路由宣告在 `{price_version_uuid}` 之前（Ninja 依宣告序，反了會 405）（#4493） |
| Console Prices 區塊 | 五欄 grid 逐列即時儲存，cache 藏 Advanced | 「● 現行價（{from} 起，UTC）」→ 缺口紅字（延長上一段／~~改為無結束日~~／新增；**Amendment N 起改為「延長一年」**，見本節末補記）→ 排程中 → 歷史（收合）；四值主表單、`USD / 1M tokens` 字尾、>100 橙字、>1000 二次確認、input==output 提示、~~每張卡自己的 Save~~（**§20 起改為暫存 + Settings 單一 Save**）（#4468、#4494） |
| 套用公開定價／Register | 只帶 input／output | 一次帶四值（cache 兩欄以倍率顯示、絕對值儲存）；快照無 cache 值時明說「將套用供應商預設」；Register 生效日固定「模型建立時」（#4496） |
| 不變 | — | D28／D29 Cost pick；`ModelPriceVersion` 為唯一價格儲存；Model Pool 為唯一撰寫面（§18） |

**操作者要知道的**：
- 打開 Model Pool → Settings → Prices 第一眼就是「現在多少錢」；紅字出現代表這顆 model 現在或之後會沒價、Cost first 會當 $0，按旁邊的按鈕一鍵補。
- 改 Input 價不會連動 cache 絕對值；提示會告訴你倍率跑掉了，要就按「依原倍率更新」。
- OpenAI／Azure 模型不用再手動把 cache read 從 0.5 改 0.1——套用公開價會直接帶真值；老 segment 要重存一次才會吃到。
- 手寫 JSON 打 API：`line_items`／`currency` 新增或改值會 400（尚未接上計費路徑），既有值原樣帶回沒事。

**PR 與合併序**（皆 ready for review、CI 綠）：docs #4466 · gaps #4465 → flat migration #4467 → reprice #4493 · snapshot #4469 · Audit#138（merge 後補 parent pointer bump）· Console C1 #4468 → C2 #4494 → C3 #4496。子 PR 在父 PR merge 後 retarget 到 main（stacked squash 蒸發前例）。**部署序硬約束**：audit → gateway → IAM（`migrate` 跑 **0311**，撰寫時編號為 0310）→ Console；反序舊 gateway 對 flat-only band `mult=None` 會 TypeError。部署後跑 `manage.py inventory_pricing_schema`，該 migration summary 的 `skipped > 0` 要跟進。

**驗證**：IAM 新測 140+ 綠（真 route、真 bridge audit pair、cache_write flat migration 七形狀）；該 migration（當時 0310、現為 0311）在 dev SQLite 真跑兩次 `converted 1 / skipped 2` → `converted 0 / skipped 2`；gateway resolver 30 綠；Console 105 檔 / 1053 測試綠 + 五道 i18n gate + boundary gate。**未做**：dev 手點、FAE evidence run。

**坑**：
- 開 PR 到修 CI 之間 main 前進 12 個 merge：五處 consumer digest 撞（重產 openapi 重釘）、`0309` 被 `0309_seed_github_copilot_provider` 搶走（改 0310）、IAM 新 sibling 套件 `xparse_external_usage` 要 `PYTHONPATH=apps/iam` 才能 regen openapi。
- 前端 `feature-acceptance-inventory` workflow 要求每個前端 PR 自己重產 `docs/testing/` workbook（`--write`），堆疊的每一層都要各補一次。
- 三個孤兒測試檔從未在 CI 跑（IAM `test_model_price_version`、`test_provider_cache_default_pricing`、gateway `test_pricing_resolver`）已升進 suite；快照測試的 `parents[3]` 自 M4 搬家後失效，21 個 TC-265 測試被靜默 skip，#4469 順手修。
- dev stack 起不來（`xparse-iam unhealthy`）與本輪無關：`docker-compose.mvp.yml` 漏掛 `xparse_external_usage` live-mount（`dev-mvp.yml` 有），修在 #4497。

**Follow-ups**：~~Audit#138 merge 後 parent pointer bump~~（已隨 #4504 一起進 main）；D7（TTL／modifiers 上鏈）仍未做——~~TTL 分段 UI 標「尚未生效」~~ **Amendment N 直接拆掉該 UI 並把 `per_ttl` 限為一檔**（[#4516](https://github.com/futurenestit/xparse/issues/4516) 追蹤透傳）；~~`derivedDrift` 一鍵更新只做 cache read，cache write 多檔待補~~（單檔後不存在多檔問題）；server-side 角色 403 仍是 PRD-272 §9 #23。

**2026-09-09 下午補記（reland + Amendment N）**：上表「9 個 PR 全開、CI 全綠、待合併」之後全部 merge，但 **4 個 stacked 子 PR（#4467 flat migration、#4493 reprice-from、#4494 Console 缺口/現行價、#4496 四值套用公開價）merge 進了已 squash 的父分支，內容從未到 main**（`origin/main` 無 `pricing_normalize.py`、無該 migration、無 `reprice-from`、Console 無 `current_segment`）。原樣 rebase reland：**#4504**（後端 + Audit#138 pointer bump，唯一 delta 是 openai 預設 0.5→0.1 的測試期望；**已 merge**）、**#4505**（Console C2+C3）。

同日 Peter 再拍板 **ADR-300 Amendment N**——**#4506**（docs：ADR-300 Am.N／SPEC-215 Rev.7 §2.27 C-215-105..107／PRD-272 §3.5.1 U63-64、INV-272-47/48）· **#4508**（IAM + gateway，migration **0312**）· ~~**#4511**~~ → **#4520**（Console；#4511 又蒸發一次，見本節末補記）：

- **價格段結束日必填**：API 422、`_validate`、DB `ck_mpv_active_segment_bounded` 三層；撤 `uq_mpv_one_active_open_segment_per_model`。存量 open-ended 段由 0312 回填「**執行日 +365 天**」（不是 `effective_from +365d`——後者會讓一年前起算的段在部署當下立刻過期、模型瞬間 unpriced）。到期後語意不變（C-215-30／D28 仍當 $0），改由 Console 揭露：紅字「已到期」+「延長一年」單一 PATCH、到期前 30 天橙字；不做通知（PRD-238 訂閱面未實作）。
- **`cache_write.per_ttl` 最多一檔**：API 422、寫入邊界依 TTL 升冪排序、provider 預設只發 5m、Console 拆掉 TTL 進階區。理由是**band 順序就是價格**——三引擎都只讀第一檔，1h 排前面就以 2.0× 取代 1.25×（高估 60%）且無聲。
- `Output (includes reasoning)` → **`Output`**（reasoning 說明移進欄位提示）；reprice-from 無下一段時新段為 `[X, X+365d)`。
- 順手：串流 `chat_streaming_audit` 把 `reasoning_token_count` 再加一次進 cost gate 的不一致改為傳 0（兩個 tier 的 `_output_tokens` 都已含 reasoning，且該計數器數的是 chunk 不是 token）。**沒有真的算錯錢**——那個金額只當「有價／無價」開關，ledger 存 token 數、查詢時才計價；修的是與非串流路徑／audit 引擎／C-215-2 的分歧。
- 順手修正 Amendment M H.1 的風險描述：低估不是「快照無值的 GPT-4.1」（它有值，0.25×），而是 C3 落地前套用公開定價不帶快照 cache 真值，受害最深的是 **gpt-4o**（真值 0.5× 被寫成 0.1×，低估 5 倍）。

**部署序**：reland 批 audit → gateway → IAM（0311）→ Console(#4505)，再 IAM（0312）→ Console(**#4520**，不是 #4511——後者從未進 main)。部署後 SQL 確認 `SELECT count(*) FROM iam_model_price_version WHERE active AND effective_to IS NULL` 為 0。**未做**：dev Console 手點、FAE evidence run。追蹤 issue：[#4516](https://github.com/futurenestit/xparse/issues/4516)（TTL 全鏈不可達，含 OpenAI 形狀打 Claude 完全不建快取）· [#4517](https://github.com/futurenestit/xparse/issues/4517)（`cache_control_advisory` 盲區）· [#4518](https://github.com/futurenestit/xparse/issues/4518)（DELETE 可留中段缺口）· [#4519](https://github.com/futurenestit/xparse/issues/4519)（不存在的 `Prefetch`）。

> **squash-merge 後不能 rebase 子分支，要 cherry-pick**（同一個機制第二次咬人；**第三次見下方 #4511**）：父分支 #4504 以 squash 進 main 後，`git rebase origin/main` 會把「已經在 main 裡」的 reland commits 整批重播，在五個 consumer digest 檔上炸出衝突——patch-id 比對認不出 squash 過的父。正解是 `git checkout -B <branch> origin/main` 後**逐一 cherry-pick 自己那幾個 commit**（#4508 六個全乾淨落地），再 `gh pr edit --base main`。retarget 前先確認 `git log --oneline origin/main..HEAD` 只剩自己的 commit。

> **第三次蒸發（#4511）與它換來的 guard**：`#4511`（Console Am.N）的 base 是 `reland/console-price-schedule-view-four-values`，也就是 #4505 自己的分支——而它在 **#4505 squash 進 main 的 43 秒後**才 merge，於是 GitHub 顯示 MERGED、內容卻留在一條已死的分支上（當時 `main` 的 `gap-alerts.tsx` 沒有 `expiredAlert`／`extendOneYear`；查法是拿 `gh pr view 4511 --json commits` 的每個 oid 跑 `git merge-base --is-ancestor <oid> origin/main`）。原樣 reland = **#4520**（`5739b8d8d`），**main 上的 Console Amendment N 是 #4520，引用 #4511 找不到 commit**。同批補了機制層防護 **#4521**（issue #3642）：`gh pr merge` 遇到 base 不是 `main` 的 PR 直接拒絕——這是本輪三次蒸發後第一個不依賴人記得的攔截點。
>
> **兩個「看起來像殘留、實際不能刪」的東西**（本輪盤點時各自誤判過一次）：
> - `segment-card.tsx` 的 `openEnded` 分支與它的兩個 i18n key **是活的**。0312 只回填 `active=True`，inactive（superseded／retired）明文「left exactly as written」，而歷史區走同一個 `SegmentCard`——`src/lib/price-schedule.ts` 檔頭已寫明 `effective_to = null` 只存活在 migration 前寫的 history。刪了會讓舊歷史列的日期區間渲染不出來。
> - `console-price-authoring-boundary-gate.sh` 的 marker **不是「缺 `issue=`」**（`adr=ADR-300` 是合法 anchor）。它的 `terminal=promote:test` 不在 `/flow-gate` 規格的四個合法值內（`permanent`／`promote:unit`／`promote:e2e`／`until-closed`），但**repo 內另有 6 支 gate 用同一個值**（ADR-350／ADR-353／PRD-314／SPEC-174／SPEC-247 ×2），還有 `spec=`／`adr=none`／`terminal=review`／無 `#` 的 `issue=4117` 等寫法——即 marker 詞彙是**全 repo 相對規格的漂移**，不是本輪 gate 的缺陷。單獨改這一支只會製造第 7 種寫法；要收就是一次 `/flow-gate sweep` 全掃、或反過來把規格補齊。

> **migration 撞號三連**：本輪 campaign 的 `cache_write` flat migration 被迫改號兩次（0309 被 `0309_seed_github_copilot_provider` 搶走 → 0310，再被 `0310_budget_plan_period_end_inclusive` 搶走 → **0311**），Amendment N 的結束日回填隨之落 **0312**。開 PR 期間 main 每 merge 一次就要重查 `ls apps/iam/xparse_iam/xparse_iam/migrations/`；另 `iam-ci-suite.txt` 也會因為別的 PR 把同一支測試 promote 進來而出現重複行，`tests/contract/test_project_lifecycle.py` 會擋。

---

## 20. 後續 campaign：Prices 區塊的三個 UX 收斂（2026-09-10；PRD-272 §3.5 修訂 + INV-272-49 / ADR-300 Am.N §N.1 #6 改寫 + #10 新增 / PRD-308 §3.5 再修訂）

> Peter 三句話：「不用預設一年」「兩個 save 很怪，統一用最外面的」「套用公開定價那顆放進表單裡，按了把價格填進欄位」。三個都是 §19 落地後**實際點下去**才看得到的問題，都不動資料層——收的是「這一頁在教使用者什麼」。

**改了什麼**

| 面向 | §19 之後 | 現在（§20） |
|---|---|---|
| 結束日 | 新段預設帶「起算 + 365 天」，可改、留空擋存 | **不預填**（仍必填、留空一樣擋存）。365 天是 migration 0312 為**存量** open-ended 段選的界，不是新段的建議值——Console 替 operator 發明一個窗，只會讓「這個價要看多久」被預設值吃掉 |
| 必填標示 | 無 | 表單四個阻擋欄位（起算日／結束日／Input／Output）標紅 `*`（`FieldLabel required`）；Register 的價格是選填故不標 |
| 套用公開定價 | 價格區塊旁的獨立卡片 + 確認 dialog，自己寫一筆 `[今天, 今天+365d)` | **表單內的一列**（日期列與四值之間），按下只把快照四值**填進欄位**（cache 兩類走與 Register 同一個 `valuesFromOffer` 倍率推導）；日期與儲存都由 operator 決定 → 沒有自己的窗、沒有 dialog（填值不是寫入）。INV-407-1（不自動套用）與 INV-300-35（唯一寫入路徑）因此更強而非更弱 |
| 誰寫入 | 每張卡自己的 Save，逐筆即時寫 | **只有 Settings 頁那一顆「儲存」**（INV-272-49）。新增／編輯／移除／缺口一鍵修補一律暫存：虛線卡片 +「未儲存」／「未儲存的移除」／「未儲存的新價格」，可逐筆捨棄；區塊內按鈕改叫「新增」／「套用」 |
| 重疊預檢查 | 對伺服器現況 | 對**暫存後的排程**（移掉的段不再擋、改過的用新區間、待新增的也算）——否則兩筆暫存互撞要等到儲存才爆 |
| 指定日期起改價 | 隨時可按 | 暫存區非空時**停用**：它是伺服器端原子重寫，和暫存中的段互相假設對方不存在 |

**暫存批次的代價（明寫，不藏）**：沒有批次端點，一次「儲存」仍是 N 個各自 atomic 的呼叫，**整批不是 atomic**（ADR-093 #1 在單列成立、在批次不成立）。收斂方式：順序固定 **remove → edit → add**（先讓出區間再讓別人佔，是唯一不會誤觸 C-215-29 重疊檢查的順序）、第一個失敗**即停**、**已寫入的不回捲**（真實 audited 列，補寫「還原」只會製造更難解釋的歷史）、未寫入的留在暫存並帶伺服器原文，再按一次儲存只補剩下的。要真 atomic 得加一支整批 upsert 端點（比照 `reprice-from`）→ 記在 PRD-272 §9 #26。

**順手查清楚：cache 留空到底算多少**（問題來自實際操作，答案在 `provider_pricing_defaults.py` + `pricing.py`，不是單一值）

| 情況 | cache read | cache write |
|---|---|---|
| 雲端且在預設表內（openai / openai_responses / azure_openai / azure_openai_responses / azure_ai_inference / anthropic / bedrock / google / vertex_ai） | 儲存時補 **0.1 × Input**，凍成絕對值 | anthropic／bedrock 補 **1.25 × Input**（5m 一檔）；其餘不補 → **算 0** |
| 地端／表外 provider（vllm、ollama、mock、自訂 code） | **Input 全價** | **Input 全價**（`pricing` 整個是 null → 兩類都落 `price_in` fallback） |
| 有 `pricing` 但單一類缺席 | **Input 全價**（INV-300-18） | **0**（INV-300-39） |

已填的那一類永不被覆蓋（INV-300-19）——**包括填 0**（顯式免費）。**待修文案**：欄位下的「留空 = 套用供應商預設費率」對雲端正確，對**地端會誤導**（地端沒有預設可套，留空的真實效果是 read 照 Input 全價計，cache-heavy 的 agent 工作量會被系統性高估）。

**驗證**：Console **107 檔 / 1063 測綠**（新增 `use-pending-price-changes.test.ts` 5 測：提交順序、部分失敗後的殘留與重試、同段覆蓋、捨棄；`apply-list-price-row.test.tsx` 4 測：填值不寫入、無 lookup 不顯示）；`tsc --noEmit` 乾淨；五道 i18n gate（含 `--import-leaks`）+ `console-price-authoring-boundary-gate.sh` + `console-i18n-enforced-paths-sync-gate.sh` 綠。

**未做**：dev 手點；**FAE evidence run**——`fae/tests/console/infrastructure/apply-list-price.spec.ts` 已依新流程重寫（開表單 → 填值不寫入 → Add 暫存不寫入 → tab Save 才 201 → 重讀斷言 `effective_to` **非 null**），`typecheck:verify` 過，但**沒有跑過**。順帶一提它在本輪之前就已經對不上 main：斷言 `effective_to` 為 null（Amendment N 起不可能）、用 `getByLabel('Price start date')`（現實是 `Start date`）——§18／§19 兩輪都寫「未做 FAE evidence run」，代價就是這個 spec 已經連續三輪沒被執行過。

---

## 21. 後續 campaign：Session Affinity（2026-09-10，+ 09-11 交付 review；ADR-447 / PRD-322 / SPEC-290 + Amendment A。完整紀錄 `路由v2.md` §24）

**一句話**：同一個 client session 內，**第一輪選中哪顆模型，之後就用同一顆**（閒置滿 1 小時重挑），讓 agent loop 的 provider prompt cache 不被 per-turn 重新路由打斷。開關在 **consumer Application**，預設**開**。

這件事**推翻了 ADR-406 §2.1-7 與 ADR-411 §4 row E 兩度「v1 明文不做（Peter 拍板）」**——原依據是 LiteLLM 的 F7（1h TTL 下 switch-back 99.3% warm）；PRD-322 §1.1 以 workload 事實（主力流量是 agent loop、per-turn 換模型直接破壞 prompt cache，OpenHands #2904 同 benchmark $678 vs $198）重提。兩份原 ADR 已補 `Revisited by`。

**11 個 PR 全 merge**（origin/main `2402dbf8d`）：#4565 docs · #4566 IAM(0318) · #4568 gateway · #4583 Console · #4593 Amendment A · #4594 A1+A3 · #4595 A2 IAM(0319) · #4597 A2 gateway · #4598 A2 Console · #4601 A4 L5 · #4603 dev compose。
**2026-09-11 追加 PR #4612**（已 merge `54e93f332`）：交付後 code review 的三個修正 + 兩個 CI gate，見 §21.4。**#4613**（已 merge `561b9d9de`）：#4612 的 follow-up，修診斷 SQL。**2026-09-13 追加 §21.5（Amendment B，7 個 PR）**。

### 21.1 對客戶端的可觀察行為（§2 那條解析鏈之外的新軸）

| 情境 | 行為 |
|---|---|
| 客戶端**送** session id（下表任一層），開關開 | 同一 session 內 `response.model` / 實際執行模型**不再隨難度分級改變**；`routing_strategy` 與 `routing_objective` 只在**首輪**起作用 |
| 客戶端**不送**任何 id | 行為與改前**逐位元相同**（除了 `decision_evidence` 多五個鍵）——除非 L5 觸發（見下） |
| 開關關閉 | 每個請求獨立路由，完全回到改前 |
| pin（`select_available=true` 且指名真模型） | **不讀不寫** affinity；優先序 `pin > Responses binding > affinity > resolver` |
| pinned 的模型離開池／被 reliability guard 排除 | **fail-open**：正常重挑，`session_affinity_evict_reason` 記原因，不讓請求失敗 |
| R3 failover | **不受影響**——affinity 只收斂餵 resolver 的候選集，failover 拿到的是完整池（D11）。**（#4612 起）** 重解析自己那筆 audit 事件也會帶 `session_affinity_enabled` / `_source` / `user_agent`，但**不帶** `_hit` / `_evict_reason`（那次沒做 affinity 查表，缺席就是「這是重解析」的判讀依據） |

**解析鏈（先命中先用）**：`Application.session_id_header`（自訂）→ `x-xparse-session-id` → `x-session-id` → `x-claude-code-session-id` → body `metadata.user_id` → body `prompt_cache_key` → 內容衍生 prefix → 都沒有。實測：**Claude Code 2.1.267** 走第 3/4 層、**OpenCode 1.18.14** 走第 2 層。

**Console**（Application configuration → Model constraints 卡）多兩個控制項：「工作階段模型固定」開關、以及開啟時才出現的「工作階段 ID 標頭」選填欄位（填了會擋 `Authorization` / `X-API-Key` / `Cookie` 這類憑證性標頭——那個值會變成路由快取的鍵）。

### 21.2 操作者要知道的三件事

1. **Codex 拿不到這個功能**，而且不是設定問題。它只講 Responses API（0.154.0 已拒 `wire_api="chat"`）、`store=false`、不送 `previous_response_id`——chat 面的 affinity 與 Responses 面的 binding affinity **兩邊都接不到**。它送的識別碼其實都很穩定，所以這是**入口面**問題不是識別問題。tracking issue **#4592**。（2026-10-14 註：09-13 Amendment B（§21.5，#4726）起 Codex 已有 affinity——靠 UA 限定的 `session-id` header 或 `prompt_cache_key`；#4592 已於 09-16 關閉）
2. **gateway 重啟＝所有 affinity 失效**（store 是 in-process）。行為上等同「所有 session 同時閒置到期」——不會出錯，只是下一輪重挑。多副本要等 Redis 化（PRD-321 / SPEC-289）。（2026-10-14 註：#5663 起 coordinated profile 的多副本經 Redis 共用 pin；單一 active 的 gateway 仍是 in-process，重啟照樣失效）
3. **`/v1/messages` 省下來的錢會打折**：`to_openai_chat` 會 flatten system blocks，attribution block 的位置性在這條路徑上已經破了（ADR-382）。affinity 保住「同一顆模型」，但 cache 前綴本身已被動過。要拿滿得補 Anthropic native passthrough（獨立議題）。（2026-10-14 註：rel 已有 #6195——Claude Code 的 billing 行拆成獨立第一塊、快取斷點放在 client 自己的 system（ADR-382 Amendment B），system prompt 與快取斷點不再被整塊丟掉；完整的原樣直送由 ADR-503 P9／#6218 做到——`/v1/messages` 打 Claude 不再經 chat 翻譯，目前只在 main，rel 還沒有）

### 21.3 **還沒做的**（完整十項見 `路由v2.md` §24.4）

- ~~**prod 未部署**~~（2026-10-14 註：已在 prod 分支 v1.76.4） — 0318 + 0319 兩個 migration，IAM 與 gateway image **要同批**
- **`prompt_cache_key` 層 / `user_agent` 觀測 / L5 prefix 沒跑過 dev 真流量** — 只有 contract test + seeded regression；已驗的是開關、四鍵、eviction、真 Claude Code 兩輪
- **Codex（#4592）** — 見上（2026-10-14 註：已由 Amendment B 解決，見 §21.5）
- **命中 turn 的 `selection_reason` 是 `classification_missing_default`** — 借用了分級器的防禦標籤。功能正確（真相在四鍵），但查「分級器是不是壞了」要加 `session_affinity_hit IS DISTINCT FROM true`，否則會被 affinity 命中流量淹掉
- **turns-per-session 量不到** — `session_id` 刻意不落 audit（client 自報可偽造），所以「識別成功但值每 turn 都變」這個最陰的失敗模式只能靠命中率趨勢間接看。**注意**：寫這句話的當下那條路其實是斷的——`/metrics` 上的三個 `session_affinity_*` counter 從未被註冊（#4612 修好了），在那之前唯一的命中率來源是 audit `decision_evidence` 的 `session_affinity_hit`
- **L5 的地端 token 門檻** — vLLM 沒有公開的 minimum cacheable prefix，刻意不猜，全地端池落回 1024 預設
- **上游 `prompt_cache_key` 投遞** — 讀取做了，往上游送沒做（OpenAI 有 ~15 RPM/key 上限要先 probe）

### 21.4 交付後 review 修掉的三件事（2026-09-11，PR #4612；SPEC-290 Rev.3）

11 個 PR 全綠 merge 之後做的 code review。三個缺口的共同點是**測試全綠、CI 全綠、ADR-093 表齊，但 prod 行為不對**——各自「看不見」的理由不同，這才是值得記的部分：

| # | 缺口 | 為什麼所有測試都看不到 |
|---|---|---|
| 1 | **L5 的 tools 前綴每 turn 都可能變** | `ChatCompletionRequest.tools` 是 `list[Tool]`（pydantic），`json.dumps(..., sort_keys=True, default=str)` 把它丟給 `default=str`，序列化出的是 **Python repr**，成員順序就是 client 送來的順序，`sort_keys` 根本到不了巢狀的 `function` mapping。同一份 tool 定義換個成員順序＝另一個 digest → **每 turn miss，而 `session_affinity_source` 仍然讀 `"prefix"`**。↳ 契約測試 `TC-290-19` 餵的是**裸 dict**，而 dict 走的是 `sort_keys` 真的有效的那條路——測到的是 dict 的契約，不是真元件的（CLAUDE.md §8.1，跟 `路由v2.md` §24.5 #3 那個 blocklist 測試同一種錯誤） |
| 2 | **`/metrics` 上從來沒有 affinity counter** | `SessionAffinityStore` 只在收到 `registry` 時才建立三個 counter，而 `app.py` 呼叫的是 `from_env()`（沒傳）。↳ store 的單元測試**自己建了一個 registry 傳進去**，所以覆蓋得到、永遠是綠的；同一個檔案裡的 `IAMValidateCache`（這個 store 的骨架來源）是接好 `metrics_collector.registry` 的，少接的只有這一根線 |
| 3 | **failover 的 audit 事件不帶 `user_agent`** | 四鍵是在 primary 決策之後 stamp 到 `plan.metadata` 的；R3 重解析 emit 的是另一個 plan（`alternative_plan`），什麼都沒有。`user_agent` 是 D15 唯一能看出「某家 client 改了 header 名」的訊號，結果在**所有 failover 事件上都是空的**。↳ 契約測試呼叫 `_route_via_routing_module`，emit 的永遠是 primary 那筆，沒有一條測試走到 failover 的 emit 點 |

修法：(1) tools 進 sha256 前先正規化成 plain data；(2) `from_env(registry=metrics_collector.registry ...)`；(3) 新的 `carry_request_evidence` 把三個**請求層**鍵帶到重解析的 plan 上。

(2) 與 (3) 是**靜默回歸**（刪掉沒有任何測試會紅），所以鎖進 `session-affinity-layer-gate` 的 **check 7 / check 8**；三個 seeded regression 都確認過 gate 會變紅。

**可複製的判準**：一個「寫好了但沒接線」的功能，它的測試往往**自己提供了那個沒接上的東西**（自建 registry、自餵 dict、自己呼叫被測函式而繞過真入口）。看到測試 fixture 在替被測對象準備它在 prod 拿不到的東西，就要去 prod 的那條路上確認一次。

**#4613（follow-up）：修好的東西改壞了查它的方法**。第 3 項讓 failover 事件也帶 `user_agent` / `_source`，但依契約**不帶** `_hit`——於是 PRD-322 §3.6 的命中率查詢把 failover 事件算進分母卻不算進分子，**命中率被低估、低估幅度正比於 failover 率，看起來就像 affinity 在退化**。同源還有分級器健康查詢（命中 turn 的 re-resolve 也落 `classification_missing_default`，而既有的 `IS DISTINCT FROM 'true'` 條件攔不到它）。兩處都補 `AND decision_evidence ? 'session_affinity_hit'`（`_hit` 的有無就是 primary / re-resolve 的判準）。

> 順帶逼出一句沒有任何文件寫過的話：**affinity 命中的 turn 若發生 failover，重新決策時沒有難度分級可用**，退化為「候選序第一顆未失敗的」；非 affinity 的 turn 在 failover 時仍保有分級。這是兩個刻意決策相遇的結果（命中跳過分級、failover 從不重新分級），不是 bug，但操作者該知道。

> **改行為就要回頭看讀它的查詢**。這次改的是 audit 事件的形狀，而三條寫在 PRD 裡、operator 會直接複製的 SQL 全部因此失準——功能對、契約對、文件裡的查法錯。

### 21.5 Amendment B（2026-09-13）：對照 LiteLLM 的第二次 review 修掉什麼（完整紀錄 `路由v2.md` §24.9）

**客戶端可觀察的行為變化**

| 情境 | 09-13 之前 | 之後 |
|---|---|---|
| Claude Code 首輪（命名請求 + 主 turn 同一個 session id、不同 system prompt） | 兩個請求搶同一把 key，整個 session 的模型看誰先寫進 store | key 多一段 **system prompt 的 digest**（不含 tools），兩者各一把 pin；subagent 也各自一把 |
| pinned 模型回 5xx、R3 換手成功 | pin 留在壞模型，active session 每 turn 先試它再換手 | **換手成功（整段回應完成）後 pin 改寫成實際成功的模型**；健康分數 < 0.5 的 pin 直接 evict（reason `unhealthy`） |
| 首輪是 Latency-first 的探索樣本，或 judge timeout 退回 heuristic | 那個「刻意非最佳」的決定被釘一小時 | **不寫 pin**，下一輪重決 |
| 首輪 `hi`（SIMPLE → 最便宜）之後問 REASONING 題 | 整個 session 卡在便宜模型 | **單向升級**：命中 turn 仍分級，分級 band 不含 pin 就往上重釘（reason `tier_escalation`）；只升不降；knob `XPARSE_SESSION_AFFINITY_TIER_ESCALATION=false` 回到舊行為 |
| Codex（`/v1/responses`、`store=false`、無 `previous_response_id`） | 每 turn 重新路由（#4592） | 走同一套 pre-filter；靠 UA 限定的 `session-id` header 或 `prompt_cache_key`（欄位以前被 pydantic 丟掉）；binding 仍優先於 affinity |
| 同 app 兩把 API key 送同一個 session id | 共用 pin | key 含 `api_key_uuid`，互不可見 |

**evidence / 指標**：`decision_evidence` 多 `session_affinity_key_hint`（key 前 16 hex，PRD-322 §3.6 的 turns-per-session 終於量得到；完整 key 永不落 audit）；`session_affinity_evict_reason` 加 `unhealthy` / `tier_escalation`；`session_affinity_source` 加 `codex_header` / `baggage`；`/metrics` 加 `session_affinity_repinned_total`。命中 turn 的 `selection_reason` 在 knob 開時是真值 `complexity_tier_mapped`（§21.3 那個「借分級器防禦標籤」的問題只剩 knob off 時存在）。

**PR**：docs #4720 · #4719 · #4721 · #4722 · #4725 · #4724 · PR-5 #4726（解析鏈三層）——**七個全部已 merge（2026-09-13）**。**prod 仍未部署。**（2026-10-14 註：已在 prod 分支 v1.76.4）另開 #4723（circuit breaker 從未被實例化；2026-10-14 註：#4926 已修好並關閉，rel 與 prod 都有）。


## 22. 後續 campaign：tools × reasoning 撞 OpenAI 400 → Responses bridge + 降級 backstop（2026-09-15；ADR-455 / SPEC-256 Rev.2 / ADR-396 Rev.2；issue #4832）

### 22.1 這是什麼、為什麼

OpenCode 三句對話裡第三句 `sorry to say that` 回 `OpenAI error [400]: Function tools with reasoning_effort are not supported for gpt-5.6-luna in /v1/chat/completions…`。前兩句沒事只是因為路由沒落在 gpt-5.4+（依 pool `gpt-5.5 [R] / luna [C,M] / gpt-4o [S]` 與 complexity 分級推斷）：第一句 SIMPLE 帶 → gpt-4o（非 reasoning 模型，沒事）；第二句被 guardrail content_filter 擋在 provider 之前。第三句一落到 luna，OpenCode **永遠帶著的 tools** 加上 reasoning 就必中——這不是模型壞、不是 prompt 壞，是 OpenAI 對 gpt-5.4+ 在 chat 面拒絕「function tools × reasoning」這個**組合**（兩個參數各自都合法）。

真元件 probe（dev gateway 對真 api.openai.com）補了兩個此前沒人驗過的事實：

| 模型 | tools | effort 送出 | 結果 |
|------|-------|-------------|------|
| gpt-5.6-luna（dev `supports_reasoning=0`，effort 被 seam drop）| 有 | **無** | **400** |
| gpt-5.4 | 有 | `low` | **400** |
| gpt-5.4 | 有 | **無** | **200** |
| gpt-5.4 | 有 | `none` | **422**（gateway schema 只收 low/medium/high）|

→ **gpt-5.5/5.6 預設開 reasoning、unset 照樣 400；gpt-5.4 unset 沒事**。所以 issue 裡「關掉 `supports_reasoning`」的 workaround 對 luna **無效**；OpenAI 自己指名的補救 `reasoning_effort: "none"` 從 gateway 送不出去。

### 22.2 做了什麼（ADR-455，抄 LiteLLM 的好、補它沒有的）

- **L0 bridge（主路徑，LiteLLM `responses_api_bridge_check` 的移植）**：seam 純函數五層閘全成立才把 chat 請求搬到 `/v1/responses`——chat `openai` provider／端點是 `api.openai.com`（含子網域）或 worker default／`gpt-5.4+` 名／含 `type=="function"` tool／reasoning active（顯式 ≠ none，或 unset 且世代 ≥ 5.5）。**credential 先以原 provider + `model_uuid` 解析，之後才換 surface**（`key_resolver` 對 provider 不符會硬 422）。tools 與 reasoning 兩者都保住、零額外往返。
- **Responses reasoning 真的接上**：兩個 Responses worker 現在會送 `reasoning:{"effort"}`；`/v1/responses` 直打的 `reasoning` dict 不再被 pydantic 靜默丟。沒這段，bridge 過去 reasoning 照掉。
- **L1 backstop（LiteLLM 沒有的）**：`OpenAIWorker` 對命中 marker 的 400 用 `reasoning_effort:"none"` 同模型重試恰一次（零 token 前、tools/messages 不變），WARNING `PROVIDER_PARAM_DEGRADED`。蓋端點不可歸因（企業 proxy、`openai_compat`）、新模型名、kill switch 三種情況。
- 順帶：`reasoning_effort` 值域擴為 OpenAI 全集（含 `none`）；chat 串流 manager 跳過 Responses worker 的 `_signal` chunk（以前會被當第一個 token：TTFT 記錯、空 delta、之後錯誤被當 committed 吞掉）；`effective_error_code` 新碼 `provider_param_rejected`（不 failover）。
- knob：tenant 面沿用 ADR-260 的 `resilience.cross_surface_fallback`；ops kill switch `XPARSE_RESPONSES_BRIDGE_FORCE_OFF=true`。

### 22.3 驗證（ephemeral gateway 掛 worktree，對真 OpenAI，同一把 KEY2）

| 案 | bridge ON | kill switch ON（只剩 L1）|
|----|----|----|
| gpt-5.4 + tool + `low`（非串流／串流）| 200 `tool_calls`，串流 0 個空 delta | 200，`PROVIDER_PARAM_DEGRADED low→none` |
| luna + tool + 無 effort | 200（bridge，交 server 預設 reasoning）| 200，`requested=None applied='none'` |
| gpt-5.4 + tool + 無 effort | 200 **留在 chat** | 200 |
| gpt-5.4 + tool + `none` | 200 留在 chat | 200 |
| `/v1/messages` gpt-5.4 + `thinking` + tool（Claude Code 形狀）| 200 `stop_reason=tool_use` | 200，`requested='medium'` |

改前 main 同組：前兩列 **400**。

### 22.4 坑（下次省時間）

- 「關 `supports_reasoning`」救不了 5.5/5.6——OpenAI 世代預設開 reasoning，只有顯式 `"none"` 有效。
- bridge 不能在 seam 直接改 `provider`：`key_resolver._select_model` 對 `match.provider != target_provider` 硬失敗，會把每個 bridge 都變 422。要先解 credential 再換 surface。
- Responses worker 在 `response.created` 會 yield `{"_signal":"response_id"}`——chat manager 沒過濾就會當成第一個 token。ADR-260 reroute 路徑一直有這個問題，只是流量少沒人看到。
- `PARAM_NORMALIZED` audit event 有發，但 DB 路徑 `_filter_extra` 會把 `extra.normalizations`（list of dict）整個丟掉——ledger 上看得到「有正規化」、看不到內容；D1–D10 全部 notice 同病，另案。（2026-10-14 註：#5615 起改存扁平欄位 `normalization_count`／`normalizations`（`param:action:divergence`）／`divergences`／`providers`，看得到改了哪個參數、怎麼改；client 送的原值刻意不存，只在 WARNING log。在 rel、prod 沒有）
- ephemeral gateway 掛 scratch 的 `/app/var/audit` → audit 事件不會進 dev 的 ledger（spool 沒被收），要看 notice 只能看 WARNING log。
- 串流 tool_calls 後 DoneEvent `finish_reason=stop`（不是 `tool_calls`）——bridge 前後都一樣，既有行為。（2026-10-14 註：#5858 起串流 chat 的 tool-call 回合一律以 `tool_calls` 結束；在 rel、prod 沒有）

### 22.5 沒解決的事

Azure（`azure_openai`→`azure_openai_responses`）bridge 與 azure 兩個 worker 的 L1 接線（marker helper 已共用）；L2 把降級結果學起來（要 decay）；`minimal`/`xhigh`→thinking budget 映射；#2505 reasoning 輸出面；~~audit `normalizations` 清單落地~~（✅ #5615）。

## 23. 後續 campaign：外部引用（路徑／URL）地板（2026-09-16；ADR-406 Amendment E / SPEC-264 Rev.10 / SPEC-266 Rev.7；完整紀錄 `路由v2.md` §26）

定址視角只有一件事變了：`complexity_routing` / `llm_judge_routing` 的 app，ask 裡有檔案路徑或 URL 時分級至少 **MEDIUM**（per-app `external_reference_min_tier`，缺席 = MEDIUM、`SIMPLE` = 關），落點 = 該級 band head；`/var/log`→`var` 這類路徑片段假命中消失。`none` 不受影響。evidence 多一個 cause 值 `external_reference_floor` 與訊號 `external_reference (path|url)`。judge app 另有 API-only 的 `judge_rubric_preset`（legacy/chat/agentic）。PR-A #4924（後端＋契約＋docs）→ main `c9a43df46`、PR-B #4922（Console 旋鈕）→ `acfd68f99`、follow-up #4931 → `0e11d6aa7`（workbook manifest 在 main tip 重釘，因 main 被 #4930 推進而重做一輪）——**全部已 merge、rel/prod 未部署**（2026-10-14 註：已在 rel 與 prod 分支，prod = v1.76.4）；部署時 IAM 與 gateway 同批、Console 之後。操作者退出法：該 app 設 `external_reference_min_tier: "SIMPLE"`。

---

## 24. 後續 campaign：Jev——第三種難度判定 `jev_routing`（2026-09-21；PRD-330 / ADR-472 / SPEC-294；完整紀錄 `路由v2.md` §27）

定址視角變了兩件事：

1. **難度判定多一個值**。可寫值 = `none` / `complexity_routing` / `llm_judge_routing` / **`jev_routing`**（+ read-back 的 `agent`）。`jev_routing` 跟 `llm_judge_routing` 一樣只負責**判 tier**（SIMPLE／MEDIUM／COMPLEX／REASONING），之後走同一個 tier→position 映射、同一個 `routing_objective` picker、同一份 per-app 排序——所以 §2 的定址規則、`select_available`、pin、failover 集**全部不變**；「沒效果」最常見的原因也仍然是排序沒排出強弱（§7）。Quality first 底下不提供 None 的規則照舊，只是計分 classifier 從兩個變三個。
2. **它是第一個需要「憑證」的難度判定**。LLM Judge 的判官是 pool 成員（`judge_model_uuid`）；Jev 是平台外的雲端服務，用的是 Credentials 頁的一把 `jev` 憑證（`routing_parameters.jev_credential_uuid`）。下拉只列該 application 的 **group 可綁**的 Jev 憑證（ADR-310 entitlement），旁邊有 **Test**（真的打一次 TypeSafe；要 `credential.rotate` 權限才看得到）。沒選憑證不能存檔。

**對 proxy 沒有影響**：`jev_routing` 跟另外兩軸一樣只掛 consumer application（ADR-198／ADR-414）；proxy configuration 頁不顯示這組控制，proxy row 也不會有 Jev 憑證。`jev` provider 是 **judgement-only**：`creatable_as` 只有 `credential`，**不能註冊成 Model、進不了任何 pool**（`ProviderDefinition.is_judgement_only`；順帶也關掉了 nemoguard 能被建成 Model 的舊洞）。

**操作者要知道的**：

- **只有 `cloud`／`hybrid` 的 application 能選**（`on_prem` 存檔回 `400 JEV_ROUTING_BOUNDARY_FORBIDDEN`）。`data_egress=denied` 的 **key** 不會被擋在存檔，而是逐請求在 gateway 擋（該請求退回 heuristic、`jev.source=jev_boundary_blocked`）——`data_egress` 是 key 的屬性不是 app 的。air-gap（`XPARSE_ONPREM_ENFORCE`）同理。
- **送出去的東西**：最新一則訊息（頭 3000＋尾 1500 字）＋最多三則簡短前文，**不含 system prompt**；enforce 模式下 PII rail 在 routing 之前，Jev 看到的是遮罩後文字。Console 在欄位下方恆顯示這段揭露。
- **錢**：TypeSafe 向持有那把 key 的帳號收費（~US$0.000026／次）；**不計入這個 application 的 token／cost 預算**；稽核記 `tier_judge_external_input_tokens`，usage ledger 另記一筆**不扣款**的 `routing_jev` 事實列（2026-09-29 校正：ADR-423 Amendment K／#5296 起如此，原文寫「只落稽核」已過時）。
- **壞掉時**：任何失敗（timeout、401/403、429/529、憑證被 revoke、模型退役）→ 請求照樣 200、該次用 Complexity 的 heuristic 判、`decision_evidence.jev.source` 留失因，而且**那次結果不會被 session affinity 釘住**（下一輪重新判）。憑證被 revoke 後 Console 欄位會亮紅字「The saved credential can no longer be used」；此時改其他欄位仍可存檔，要重新選憑證或換難度判定才會再用到 Jev。
- **怎麼確認有在用**：audit `routing_decision_recorded` 的 `decision_evidence.jev.source == "jev_verdict"` 且 `cause == "jev_classifier"`；`jev` 鍵只在 `jev_routing` 出現、永不與 `judge` 並存。

四個 PR：#5145（docs）→ `ed88c361d`、#5146（IAM `jev` provider ＋ `/test`、`/test-tier-judgement`，migration 0340）→ `4c8e88ca7`、#5149（gateway 判級，先行且 dormant）→ `5a447321c`、#5151（IAM 治理＋投影、migration 0341、Console、新 parity gate）→ `5f20bf7a1`——**全部已 merge、rel/prod 未部署**（2026-10-14 註：程式已在 rel 與 prod 分支；prod 由 pre-release registry 的 `jev_routing`（stage=rel）扣住，rel 可用、prod 看不到）；部署順序 **gateway → IAM → Console**，IAM 與 gateway 同批。**回滾 IAM 前**要先把 `jev_routing` 的 rows 改寫回 `complexity_routing`（舊版 IAM 的 strict enum 讀到就炸）。**還沒做**：真 key 的成功 verdict e2e（需要 `TYPESAFE_API_KEY`）、QA 的 TC catalog（TC-APP-030 描述已過期）、三份設計文件的狀態翻轉——清單見 `路由v2.md` §27.6。過期文件與 ops runbook（`docs/runbooks/jev-routing-operations.md`）在 **PR #5158**（2026-10-14 註：09-21 已合併）。

**2026-09-22 追加（PR #5220；SPEC-294 Rev.4 / ADR-472 Amendment B）**——定址規則不變，判級行為兩處變：

- **Jev 掛掉時不再每個請求都等**：連續 3 次逾時後 gateway 30 秒內不再打 TypeSafe（`decision_evidence.jev.source = "jev_circuit_open"`，退 Complexity heuristic、不釘 session、無 `tier_judge_invoked`），之後放一個請求探測。routing 與 guardrail 的 Jev 臂**各自**一個 breaker；guardrail 那邊打開時對外仍是 `classifier_timeout`，只有 metric 分得出來。以前是每個請求各付 1.5 s（routing）＋ 3 s（guardrail 503）。
- **短回覆判得對了**：送給 Jev 的 `prior_turns` 現在帶 assistant 回合（`{"role","text"}`）。以前「ok go」接在 assistant 提的遷移計畫後面會判 SIMPLE、落到最便宜那顆；現在判 COMPLEX。翻譯一句、換時區這類仍是 SIMPLE。LLM Judge 不受影響。

- **冷連線不再誤觸 breaker（2026-09-22 傍晚，PR [#5258](https://github.com/futurenestit/xparse/pull/5258)）**：閒置超過 30 s 後的第一次判級（含 breaker 的探針）要先建 TCP+TLS，當天實測 1.2–2.6 s，比 1.5 s 的 deadline 還長，所以 breaker 一開就關不回來。現在冷連線那一次 deadline 自動加 2 s；熱連線不變；寬限後仍逾時照樣計入 breaker（vendor 真死還是會開）。看到 `jev_timeout_default` 先分清是冷連線還是 vendor 慢：gateway log 有 `jev cold connection … inside the … handshake allowance` 這行代表是前者且已救回。

**操作者要知道的**：runbook `jev_circuit_open` 列有處置；看到它先查前面三筆 `jev_timeout_default` 的原因。

