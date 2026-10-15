# Policy 是什麼？（白話版）

> 給第一次接觸 Xparse policy 的人。用最簡單的話講清楚：policy 是什麼、誰在用、裡面有什麼、什麼時候會被用到。
> 技術名詞保留英文，說明用中文。
>
> **2026-09-29 更新（第四輪：inherit 實測抓到的缺陷，docs [#5427](https://github.com/futurenestit/xparse/pull/5427)／IAM [#5443](https://github.com/futurenestit/xparse/pull/5443)／gateway [#5446](https://github.com/futurenestit/xparse/pull/5446)／SQLite [#5447](https://github.com/futurenestit/xparse/pull/5447)，全部已 merge main；本地 dev 已實測通過、未部署遠端）**：用 `~/Desktop/testing/inherit_probe.py` 對本地真 IAM＋gateway 實測後修的四件事。① **PII 與 word filter 也「停用即空」**（SPEC-219 C-219-49、SPEC-224 C-224-21，ADR-476 Amendment H）——以前某層 `pii.enabled: false` 仍把它的 `entities`／門檻聯進來（實測 app 層停用的 `phone` 照樣被遮），某層 `word_filters.enabled: false` 的 block 詞仍會 **451**，停用層的詞也算進 800 上限；現在只有 `enabled` 本身仍是 OR。**部署時是一次放寬**（回到作者原意）。② **`GET /iam/effective-policy` 只帶 `application_id` 會補齊 tenant／group**（SPEC-195 C-195-48）——以前只 fold app 那一層；group_admin 讀 tenant-owned bundle 那條分支原本會 500。③ **稽核寫「真的判的那一個」**（SPEC-223 C-223-23b，ADR-488 Amendment A）——moderation／NemoGuard／Jev 臂記自己的模型（`omni-moderation-latest` 等、不帶 uuid），失敗時多 `classifier_unavailable_reason`＋`classifier_unavailable_detail`（例如「moderation call returned HTTP 401」）。④ **conversation scope 要送哪個 header**（SPEC-292 C-292-58）：latch 只認 `X-Xparse-Session-Id`／`X-Session-Id`／app 設的 `session_id_header` 等；**`X-Conversation-Id` 只是 cache salt**，只帶它的對話永遠不會被鎖，稽核會多一個 `conversation_scope_latch_hint` 提示。另：本地 SQLite IAM 併發時停用 binding 偶發 500，改 `transaction_mode=IMMEDIATE`（ADR-039 §2.6，[#5447](https://github.com/futurenestit/xparse/pull/5447)）。

> **2026-09-22 更新（Jev guardrail 對打實測後的四項修正，全部已進 main）**：① `classifier` 兩條 rail 的 fold 改為「**停用即空**」——`enabled: false` 的 rail 不再把它的 `engines`／`constraints`／`categories` 聯進子層（SPEC-223 C-223-61，#5208）；之前租戶層一個從未啟用的 `on_topic` 會把預設 `llm_classifier` 塞給每個選 Jev 的 app，變成兩臂同跑、延遲吃掉 Jev 的優勢。② `on_topic` 多一個 `allow_small_talk` 旋鈕（C-223-62，#5211）：寒暄／道謝／道別不算離題；預設 false；fold **false-wins**（上層沒開、下層開了也不生效，Console 會顯示 clamp）。③ 判不了的超大單則改回 **503**（不再是 451「判過且擋」，#5205）。④ Console 選 Jev 時多一行提示：門檻「中」對「論證某族群該被剝奪權利」這類仇恨問句判得偏鬆，仇恨為主要顧慮建議選「低」（PRD-332 §9，#5212）。實測數字見本文 Jev 一節第 6 點。⑤ Jev 兩條 guardrail 臂各自有 **circuit breaker**（ADR-476 Amendment C，#5220）：對 TypeSafe **連續 3 次 timeout** 就開路 30 s，期間零外呼、直接走 `on_failure`（enforce 下 = 503，仍記 `classifier_timeout`，只有指標 `xparse_guardrail_jev_call_total{outcome="circuit_open"}` 分得出來）；30 s 後放一個探測請求成功才關回。跟 routing 那條 `jev_routing` 的 breaker 是分開計的（routing 逾時 1.5 s 不會拖垮 guardrail 的 3 s）。
>
> **2026-09-22 更新（第三輪：guardrail × routing 全矩陣抓到的三個缺陷，PR [#5258](https://github.com/futurenestit/xparse/pull/5258)，CI 綠待 merge）**：① `content_filter.stages: ["output"]` 以前照樣在 input 判定並回 `input_blocked`——gateway 四個 input gate 只看 `enabled`+`categories`、沒讀 `stages`；現在 `input` 不在 `stages` 就不跑 input 臂，缺省仍是 `[input]`，`on_topic` 不受影響。② Jev 冷連線（閒置 ≥30 s 或首次）deadline 自動 +2 s（guardrail 臂 3→5 s、routing 1.5→3.5 s），breaker 探針不再永遠逾時；逾時照計。③ 遮罩成功的請求現在真的帶 `x-guardrail-redacted: true`（chat 非串流／串流、Responses 串流）——helper 從 #1971 起存在但沒人呼叫。
>
> **2026-09-22 更新（第二輪：資料邊界，#5196 收尾，三個 PR 全部已 merge main、未部署）**：① **所有「判定會出境」的 evaluator 都過同一道資料邊界 gate**（#5235，SPEC-223 C-223-55 一般化）——不只 Jev，`openai_moderation` 與 **pin 到雲端模型的內建 judge**（`classifier.model` 非 `auto`）也一樣：`on_prem` 的 app／`data_egress=denied` 的 key／`XPARSE_ONPREM_ENFORCE` → 零外呼、503 `classifier_boundary_blocked`、`on_failure` 決定放不放行；`auto` 的內建 judge 不 gate（那是 kernel 核准的 route）。**直接 enforce，沒有 observe 期**——因為 `profile_type` 其實可以 PUT 改（見下），租戶有自救路。② **綁定時不擋、但會預告**（#5238，C-223-63）：綁 guardrail 政策（tenant／group／app）與讀 effective policy 都回 `boundary_preview`——範圍內哪些 `on_prem` app 會因為這張政策的出境 evaluator 被 503；Console 在綁定 dialog、應用的 Policies tab、以及把 app 改成 on-prem 的確認框顯示。③ **LLM Proxy 那一列的 `profile_type` 變成惰性欄位**（#5233）：proxy 頁不再有 Use Case，盤點 on_prem app 要排除 proxy。
>
> **2026-09-21 更新**：① `guardrail` kind 的說明改成現況——ADR-249 起它是**獨立的內容安全 kind**（PII 遮罩／自訂詞／主題限制／內容過濾），`llm_operational` 裡**已經沒有** `guardrail` 子區塊；② 補上 guardrail 兩條 classifier rail 的「判定來源（engine）」，含新加入的 **Jev**（ADR-476／PRD-332，六個 PR #5191–#5194、#5198、#5199 已進 main，prod 由 pre-release registry 扣住）；③ `routing_strategy` 的值改成現行四值＋`agent`。

>
> **2026-09-29 更新（第三輪：成本與額度的現況校正，純文件、沒有程式改動）**：① **`token_quota_k` 改成現況**——它是 application 的**累計** token 額度（PRD-289 Addendum A），Gateway admission 從 **IAM usage ledger** 讀累計用量來判斷（ADR-423 Phase 4b 起 Redis 不再是判斷依據），用完就 **429**、不會按月重置；舊文的「Redis 計數、fail-open 軟上限、每月上限、`0` = 無限」都已過時。② **Jev 的用量不是「只在 audit」**：2026-09-23 起（ADR-423 Amendment K，#5296）usage ledger 另記一筆**不扣款**的事實列（`guardrail_jev`），仍不扣配額、不進 Budget／Dashboard；ADR-476／SPEC-223 還寫「不寫 ledger」，文件矛盾追在 #5437。③ 對照：內建 judge（`llm_classifier`）與 routing 的 tier judge 自 #5274 起 **token 與 cost 兩軸都計入租戶預算**，但 Dashboard／FOCUS 還看不到這筆（#3046／#3494），而且 completion 目前被當 input 單價計（#5432）。
>
> **2026-09-29 更新（第二輪：ADR-488 判官疊加 + 同層 precedence，PR #5416 docs／#5420 gateway／#5417 IAM／#5418 Console，全部已 merge main、未部署；部署順序 gateway → IAM → Console）**：① **判官類設定「設了就跑」**——內建 judge 釘的模型（`auto` 不算）、on_topic 範本（`xparse` 算）、NemoGuard 端點，跨層與同層都**疊加**，每個都各判一次（主題限制＝模型 × 範本）；子層仍拿不掉上層的。② **選擇類設定同層不再 409**——`fallback_model`、OpenAI moderation／Jev 憑證、word filter 同一詞的 `replacement`：跨層上層贏，同層依 binding `precedence`（數字小者優先，同分先建者）選一個；Console 綁定／替換 dialog 可設 precedence（替換不再悄悄重設成 100），預覽會標出「哪一層有多個值、採用哪個」（word filter 不顯示詞與替換字）。③ 成本：判官呼叫會相乘，rate limit 每多一個判官多扣一次；單一判官的計量與快取與之前逐位元相同。
>
> **2026-09-29 更新（第一輪 inherit 收尾，PR #5406 docs／#5407 IAM／#5408 Console／#5410 gateway，全部已 merge main、未部署）**：① **綁定當下就擋「會讓 app 解析失敗」的寫入**（SPEC-195 C-195-47）——以前這類衝突會綁定成功、之後那些 app 的每個請求都 fail-closed；現在直接 409 並列出受影響的 app（ADR-488 之後，同層判官／選擇類差異已不算衝突，剩下的觸發是 word filter 超過 800 詞、偵測器不支援的 entities 等）。只擋「這次寫入**新**弄壞的」，原本就壞的不擋；deactivate／invalidate／移除 item 永遠不擋（那是修復手段）。② **綁定 dialog 多一行組合預告**（SPEC-223 C-223-64）：跨層主題條款會連乘、跨層 engine 會疊加（下層拿不掉上層的）。③ **enforce 下多 engine 先擋先回**（SPEC-223 C-223-65）：任一個 engine 判擋就立刻回，其餘 engine 在背景跑完、照樣記稽核與計量；coordinated gateway 不適用。

---

## 一句話定義

**Policy 就是一張「規則卡」：規定一個請求「可以做什麼、不能做什麼」。**

它管的是這類問題：

- 這個請求每秒最多打幾次？（rate limit）
- 一次最多用多少 token？（quota）
- 可不可以連到外面的 cloud（OpenAI / Anthropic）？還是只能用機房內的模型？（execution boundary / egress）
- 內容要不要過濾髒話、要不要遮 PII？（guardrail）
- 可不可以開 streaming、可不可以呼叫 tool？

重點觀念：**policy 是一張「可以重複使用的模板」，不是綁死在某個人身上。** 同一張規則卡可以發給很多 tenant、group、application 用。誰要套用，是另外一條「綁定關係」（PolicyBinding）來決定的。

---

## Policy 管到誰？（四層角色）

Policy 是**一層套一層**的，上層畫底線，下層只能更嚴、不能更鬆。

```
System Admin（平台管理員）
   │  畫「硬底線」guardrail：所有人都不能突破（例如單次最多 10000 token）
   ▼
Tenant（租戶）
   │  在 system 底線內，訂租戶自己的規則（例如最多 8000 token）
   ▼
Group（群組）
   │  在 tenant 規則內，再收緊（例如最多 6000 token）
   ▼
Application（應用）／ Deployment（部署）
      實際發請求的人，吃的是上面層層收緊後的「最終規則」
```


| 角色                       | 他能訂什麼 policy                        | 限制                  |
| ------------------------ | ----------------------------------- | ------------------- |
| **System Admin**         | 全平台硬底線（guardrail）、平台預設              | 最高權限，誰都不能突破         |
| **Tenant Admin**         | 租戶層 policy、幫底下 group / app 綁 policy | 不能超過 system 底線      |
| **Group Admin**          | 群組層 policy（ADR-206 新增的能力）           | 不能超過 tenant         |
| **Group Developer**      | 自己建的 application（自己擁有）              | 只能管自己建的，且吃上層 policy |
| **Application（runtime）** | 不訂規則，只「被規則管」                        | 跑請求時被最終 policy 擋    |


**關鍵規則：往下只能收緊，不能放寬。**
如果 group 設 6000，app 想設 12000 → **直接拒絕、不容妥協**（fail-loud）。

---

## Policy 裡面裝什麼？（policy kind 全列表）

一張 policy 卡（PolicyBundle）是個「容器」，裡面可以放好幾張不同種類的規則（PolicyEntry）。
`PolicyKind` enum（`xparse_iam/.../db/models/hierarchy.py`）目前有 **6 種啟用中的 kind**，外加 **2 種保留、被 DB 擋掉**的 kind。

> ⚠️ 容易誤會：有人會說「policy 只有 3 種」——那是指 ADR-191/SPEC-168 的**「policy-as-code runtime 平面」**（`llm_operational` / `runtime_egress` / `deployment_runtime`）。但**完整的 `PolicyKind` enum 其實有 6 種**，另外 3 種是更早就在 enum 裡的 `authorization`（legacy RBAC）、`guardrail`（同一批進 enum，但 **ADR-249 起改承載獨立的內容安全 spec**，現在是 runtime 真的在擋請求的 kind）和一個 placeholder（`budget`）。下面列全部。

### 6 種啟用 kind 一覽


| #   | policy_kind              | 一句話用途                        | 由誰執行                      | 有 operator？           | 一個 bundle 可多筆？ | 狀態          |
| --- | ------------------------ | ---------------------------- | ------------------------- | --------------------- | -------------- | ----------- |
| 1   | `**llm_operational`**    | LLM 流量上限 + token 上限           | Gateway（請求時）              | ✅ tighten-fold        | ✅ 可多筆          | ✅ 已上線、實際擋請求 |
| 2   | `**authorization**`      | RBAC：誰能對什麼資源做什麼動作            | IAM auth engine           | ✅ rules-by-precedence | ✅ 可多筆          | ✅ 已上線       |
| 3   | `**guardrail**`          | 內容安全：遮 PII／自訂詞／主題限制／內容過濾   | Gateway（請求時）+ guardrails sidecar | ✅ 逐欄位 fold（收緊／聯集／child-overrides） | ✅ 可多筆          | ✅ 已上線、實際擋請求 |
| 4   | `**budget**`             | 預算 / 花費上限                    | （尚無 resolver）             | ❌ 無                   | ❌ 最多 1 筆       | ⬜ 佔位、無 spec |
| 5   | `**runtime_egress**`     | 容器能對外連去哪（網路出口管制）             | container_platform（部署時凍結） | ❌ 無（已 defer）          | ❌ 最多 1 筆       | 🟡 設計中、部分實作 |
| 6   | `**deployment_runtime**` | 部署運行設定（image 核准 / 權限 / 資源上限） | （尚無 spec）                 | ❌ 無                   | ❌ 最多 1 筆       | ⬜ 佔位        |


**現在真正在 production 擋請求的，主要是 `llm_operational` 與 `guardrail`（+ RBAC 的 `authorization`）。**

### 每一種 kind 到底有什麼用

**1️⃣ `llm_operational`** — 控制「打 LLM 的流量上限 + token 上限」。Gateway 在**每個請求**時把關。實際欄位：

- rate limit：`req_per_sec`、`burst`、`max_concurrency`、`max_queue_depth`、`queue_timeout_sec`
- limits：`max_input_tokens`、`max_output_tokens`、`max_total_tokens`
- actions：政策被觸發**之後**要做什麼（ADR-461，kind-agnostic）
- operator = `tighten_merge`（**單調收緊**：上層設限，下層只能更嚴）→ 可多筆 fold 成一筆。
- ⚠️ **這裡已經沒有 `guardrail` 子區塊了**（ADR-249 把它抽成獨立 kind，見 3️⃣）。舊文件／舊 YAML 裡的 `content_filter_level`、`pii_redaction_enabled`、`blocked_keywords` 都是抽離前的形狀。

**2️⃣ `authorization`** — 傳統 RBAC：一組 `PolicyRule`（effect allow/deny、action、resource、precedence）。決定 API 請求 allow 還是 deny。由 IAM auth engine（`resolver.py` 的 `authorize()`）執行；operator = `merge_layer_rules`（按 precedence 排序，`0 = system guardrail` 最高優先）。

**3️⃣ `guardrail`** — **內容安全**。歷史上這個 kind 是 RBAC 規則風格；**ADR-249 起它承載獨立的內容安全 spec**（`GuardrailPolicy` manifest，現行 `version: v2`），跟 `llm_operational` 分開改、分開發版。Gateway 在**每個請求**時執行。裡面有四塊：

| 區塊 | 做什麼 | 在哪裡跑 |
| --- | --- | --- |
| `pii` | 把個資換成型別化代號（偵測模型在客戶機房，原文不出境） | guardrails sidecar |
| `word_filters` | 自訂詞：遮罩或擋下 | guardrails sidecar |
| `classifier.on_topic` | 主題限制：離題就擋；`allow_small_talk: true` 時寒暄不算離題（2026-09-22 起） | Gateway in-process |
| `classifier.content_filter` | 內容過濾：仇恨／違法／自傷／性／暴力，`threshold` = low／medium／high | Gateway in-process |

共用旋鈕：`mode`（`shadow` 只記錄不擋／`enforce` 真的擋）、`on_failure`（判不了的時候 `closed` 擋下／`degraded` 放行）、`actions`（ADR-461）。

> **fold 的一條新規則（2026-09-22，C-223-61）**：一個 rail 在某層寫了 `enabled: false`，那一層對這條 rail 就等於「沒寫」——不貢獻規則、類別、門檻，也不貢獻 engine；只有 `enabled` 本身仍是 OR（子層關不掉上層開的）。實務意義：租戶層留一個「沒啟用」的 on_topic 區塊，不會再讓每個 app 多跑一臂內建 judge。**2026-09-29 起 PII 與 word filter 也適用**（SPEC-219 C-219-49、SPEC-224 C-224-21，#5443）：停用的 `pii` 不貢獻 `entities`／門檻，停用的 `word_filters` 不貢獻任何詞（也不算進 800 詞上限）。

> **稽核怎麼看是哪一臂判的（2026-09-29，SPEC-223 C-223-23b，#5446）**：每一臂一筆紀錄，`classifier_engine` 是判定來源；`classifier_model` 是**真的做判斷的那個模型**——內建 judge 記它的 judge 模型（配 `classifier_model_uuid`），OpenAI moderation 記 `omni-moderation-latest`、NemoGuard 記 `content_safety`／`topic_control`、Jev 記 Jev 的模型 id，這三種**不帶** uuid（它們不在模型目錄裡）。`GUARDRAIL_BLOCKED` 記的是**真正擋下的那一臂**。判不了時多兩個欄位：`classifier_unavailable_reason`（原因代碼）與 `classifier_unavailable_detail`（我們自己寫的一句說明，例如 `moderation call returned HTTP 401`、憑證名字找不到／沒授權），gateway log 也印同一句。以前 moderation 臂會被記成「gpt-5.4 判的」，失敗也只有一個 `classifier_error`。

**兩條 classifier rail 要「誰來判」= engine（判定來源）**，Console 的 policy 表單 Engine 下拉：

| Console 選項 | wire 上的 evaluator | 判定在哪裡做 | 需要的憑證 |
| --- | --- | --- | --- |
| Xparse (self-hosted)（預設） | `llm_classifier` | 平台內建 LLM judge（judge 模型由 `classifier.model` 解析；多層釘了不同模型時每個都跑，ADR-488；用量逐模型計入租戶） | 無 |
| OpenAI | `openai_moderation`（只有 content_filter） | OpenAI 雲端 | `content_filter.moderation_credential_ref` |
| NemoGuard (self-hosted) | `nemoguard_content_safety`／`nemoguard_topic_control` | 自架端點（信任邊界內） | `classifier.judgement_credential_ref` |
| **Jev**（ADR-476，2026-09-21） | `jev_content_safety`／`jev_topic_control` | **TypeSafe 雲端（平台外）** | `classifier.jev_credential_ref` |

Jev 這一列要記住的五件事：

1. **流程**：Credentials 頁新增 provider = `jev` 的憑證 → policy 表單 Engine 選 Jev → 選「Jev 憑證」→ 按 **Test**（真的打一次 TypeSafe，送一題四級評分＋一題是非題）→ Save。
2. **憑證用「名字」參照，不是 uuid**（guardrail 家族慣例）。fold 時 engines 取**聯集**、憑證名跨層由**上層釘住**、同層依 binding `precedence` 選（ADR-488）；每個 policy version 每條 rail 只能寫一個 engine，要多個並跑只能靠不同層各綁一張。指名的 engine 判不了 → 走 `on_failure`，**絕不**偷偷退回內建 judge。
3. **資料會出境**：判定內容送到 TypeSafe；PII rail 沒在 enforce 時送的就是原文。所以外呼前有一道**資料邊界 gate**：`on_prem` 的 application、`data_egress=denied` 的 key、或部署開了 `XPARSE_ONPREM_ENFORCE` → **零外呼**、回 503 `classifier_boundary_blocked`（shadow 也一樣不外呼）。⚠️ Test 按鈕綠**不代表** runtime 邊界允許。**2026-09-22 起（#5235）這道 gate 不再是 Jev 專屬**：`openai_moderation`、pin 到雲端模型的內建 judge 都過同一個 predicate；只有 NemoGuard（自架、宣告 in-boundary）和 `auto` 的內建 judge 不經過它。Console 的 OpenAI 憑證欄現在也有同一段揭露文字。
3a. **連不上 TypeSafe 時**：單次逾時 3 s（`XPARSE_JEV_GUARDRAIL_TIMEOUT_MS`；**冷連線那一次 +2 s**，2026-09-22 傍晚 #5258——閒置 ≥30 s 後首發要先握手，實測 1.2–2.6 s）走 `on_failure`；連續 3 次逾時後 breaker 開 30 s、不再外呼，enforce 政策這 30 s 內每個請求都是 503——所以 hosted 判定源的可用性是「TypeSafe 的可用性 × 你的 on_failure 選擇」，`degraded` 才會放行（2026-09-22，#5220）。
4. **費用不進 Xparse 的 cost**：TypeSafe 直接向憑證擁有者收費（輸入 US$0.042／百萬 tokens、輸出免費）。Xparse 在 audit 記 `classifier_external_input_tokens` 供對帳，usage ledger 另記一筆**不扣款**的事實列（producer `guardrail_jev`，ADR-423 Amendment K，#5296）——不扣 token 配額、不進 Budget、不進 Dashboard cost／FOCUS。⚠️ ADR-476 INV-476-9／SPEC-223 仍寫「不寫 ledger」，跟 Amendment K 矛盾，追在 #5437。
5. **prod 看不到**：`jev_guardrail` 登記在 pre-release registry（ADR-473，`stage=rel`），只有 `XPARSE_ENVIRONMENT` 是 `dev`／`rel` 的部署會出現這個選項；沒設或拼錯 = `prod` = 扣住，寫入會回 `400 FEATURE_NOT_RELEASED`。
6. **實測怎麼樣（2026-09-22，dev 對真 gateway 175 題，同題同請求跟內建 gpt-5.4 judge 對打；證據 `~/Desktop/testing/問題集.md` §12）**：主題限制兩者幾乎一樣準（足球規則 34 題全對）；內容過濾在「中」門檻上 Jev 抓到 88.6% 違規、良性只誤擋 2.5%，內建 judge 抓到 100% 但良性誤擋 **37.5%**（歷史題、定義題、性教育、新聞摘要全擋）；中文違規 10 題兩者都 10/10。每臂延遲 Jev p50 約 280 ms，內建 judge 約 1.4 s；成本主題約 US$0.02、內容五類約 US$0.08 每千次。Jev 漏的是「論證某族群該被剝奪權利」這種問句（「中」放行、「低」擋）——rubric 不改，Console 會提示。閒置超過 30 s 的 app 每次多付一次 TLS 握手（約 +400 ms），是設計值。

> 註：`authorization` 的規則分層裡有一層叫「system guardrail」（precedence 0，最難被覆蓋的安全底線）——那是 **RBAC 規則的一個優先層名稱**，跟這個 `guardrail` **kind** 是兩回事，別搞混。

**4️⃣ `budget`** — 意圖是「花費 / 額度上限」，但目前**沒 spec、沒 resolver、沒 operator**，只是 enum 保留位。

**5️⃣ `runtime_egress`** — 控制「一個部署的容器能對外連去哪」（air-gap / 供應鏈安全關鍵）。欄位：`mode`（`deny_all` / `allowlist_only` / …）+ allow/deny 目的地清單。特別之處：**不是請求時解析，而是在「部署建立的那一刻解析一次」**，凍結成 `Deployment.resolved_egress` 不可變快照，由 container_platform 執行。沒 operator（合併語意難——allow 取交集、deny 取聯集，無單一收緊軸線，SPEC-173 §7 已 defer）。

**6️⃣ `deployment_runtime`** — 部署層運行參數，目前只是 `dict[str, Any]` placeholder，無正式 spec、無 operator。

### Operator 是什麼？為什麼有的 kind 沒有？

**Operator = 「把多筆同類型 policy 合併成一筆有效 policy 的規則」。** 沒有 operator = 不知道怎麼合併多筆，所以：

> **ADR-240 D6：沒 operator 的 kind（`budget` / `runtime_egress` / `deployment_runtime`），一個 bundle 最多 1 筆。** 放多筆會在 author/sync validation **和** resolve 時都 fail-loud（INV-240-5），絕不默默取第一筆。

### ⚠️ Embedding profile 不是 policy kind

很容易誤會：**embedding profile（ADR-089）不是 policy 的一種 kind。** 它是掛在 application/group 上的一個**扁平設定**（`embedding_profile_config`，走 `effective_embedding_profile_config_uuid` / `resolved_from` 自己的解析路徑），程式碼在 `xparse_iam/.../client.py`，跟 PolicyBundle/Entry/Binding 那一整套完全無關。**policy 是「規則容器」，embedding profile 是「一個設定欄位」。**

### 🚫 保留中（被 DB 擋掉）的 kind

`PolicyKind` enum **故意不放**這兩個，連 raw SQL 寫進去都會被 `chk_policy_bundle_kind_enum` CheckConstraint 拒絕（INV-191-10）：


| 保留 kind          | 觸發理由（未來才解鎖）                                       |
| ---------------- | ------------------------------------------------- |
| `sidecar_access` | 當 ingress ACL + verify-session 表達不了 sidecar 存取控制時 |
| `data_handling`  | 當 egress + sidecar + audit 都蓋不到資料處理規則時            |


> 刻意的 fail-closed 設計：plane 沒設計好之前，寧可在 DB 層擋死，也不讓半成品 kind 混進來。

### `llm_operational` 長相（YAML 範例）

```yaml
kind: LLMOperationalPolicy
metadata:
  code: tenant-default-llm-ops
  version: "2026.06.20.1"
spec:
  rate_limit:
    req_per_sec: 10        # 每秒最多 10 次
    burst: 20              # 短時間可衝到 20
    max_concurrency: 8     # 同時最多 8 個在跑
  limits:
    max_total_tokens: 12000
```

### `guardrail` 長相（YAML 範例，v2；engine 選 Jev）

```yaml
kind: GuardrailPolicy
metadata:
  code: tenant-default-guardrail
  version: "2026.09.21.1"
spec:
  version: v2
  enabled: true
  mode: shadow               # 先 shadow 觀察，再切 enforce
  on_failure: closed         # 判不了就擋（Jev 被資料邊界擋下時也走這裡）
  pii:
    enabled: true
  classifier:
    jev_credential_ref: my-jev-key      # Credentials 頁那把 jev 憑證的「名字」
    on_topic:
      constraints: ["只回答公司產品相關的問題"]
      allow_small_talk: false             # 2026-09-22 起；true = 「你好／謝謝／再見」不算離題（fold false-wins）
      engines: [jev_topic_control]
    content_filter:
      categories: [hate, violence, self_harm]
      threshold: medium                 # low / medium / high
      engines: [jev_content_safety]
```

> 欄位以 `apps/iam/xparse_iam/xparse_iam/policies/schema.py::GuardrailPolicySpecV2` 為準；`pii` 的細項見 `guardrail.md` §2.4。

---

## Inherit 怎麼算（tenant → group → application）

預設 resolver 是 `bundle_item_fold`：tenant、group、application（、deployment）上**所有**生效的 binding 一起 fold，不是最近那層說了算。

> 本節每一列都在 2026-09-29 對本地真 IAM＋gateway 實測過（`~/Desktop/testing/inherit_probe.py`，情境 F1–F10／C1–C3／W1–W7／G，結果在 `~/Desktop/testing/results/inherit-*`）。要看 fold 後的結果用 `GET /iam/effective-policy?policy_kind=guardrail&application_id=<app>`——2026-09-29 起只帶 `application_id` 也會把 tenant／group 一起算進來（SPEC-195 C-195-48，#5443；以前只算 app 那一層）；word filter 的詞在這個預覽會被遮成 `[]`，要看實際效果只能打請求。

| 區塊 | 規則 |
| --- | --- |
| PII | `entities` 聯集、`score_threshold` 取小（**只算啟用的層**，停用層＝沒寫，C-219-49）、`enabled`／`scan_system` OR |
| word_filters | 詞表聯集（**只算啟用的層**，停用層的詞不生效、不算進 800 詞，C-224-21）；同一個詞 `block` 贏 `mask`；`replacement` 跨層上層贏、同層依 binding `precedence`；fold 後超過 800 詞 → 綁定時 409 |
| content_filter | `categories`／`stages`／`engines` 聯集；`threshold` 取最嚴（`low` 最嚴）；內建 judge 釘的模型（非 `auto`）與 NemoGuard 端點**全部都跑**；moderation／Jev 憑證、`fallback_model` 跨層上層贏、同層依 `precedence` |
| on_topic | `constraints` 聯集，但 runtime **每一條都要成立** → 兩層寫不同主題 ≈ 全擋；`allow_small_talk` false 贏；`engines` 聯集；**每套範本（含 `xparse`）× 每個 judge 模型各判一次** |
| Conversation scope restriction（`actions.restrict_conversation_scope`） | **唯一取交集**：各層 selectors 展開成模型後取交集，子層只能縮小；`triggers` 聯集、`idle_ttl_days` 取大、`on_missing_conversation_id` 取 `always_restrict`；交集為空 → 綁定**不擋**、只在 `scope_preview_warnings` 預告；觸發之後那個對話的**下一輪**才回 400 `conversation_scope_empty` |
| 共用 | `mode` enforce 贏、`on_failure` closed 贏、`output_redaction_mode` buffer 贏 |

**Conversation scope 怎麼認「同一個對話」**（SPEC-292 C-292-5／C-292-58，2026-09-29）：任一條 rail 在 enforce 下命中（擋下或遮罩）就觸發；之後要靠**對話 id** 記住。只認這些 header：application 設定的 `session_id_header`（Console「Session ID header」）→ `X-Xparse-Session-Id` → `X-Session-Id` → `X-Claude-Code-Session-Id` → Codex 的 `session-id`／`thread-id` → `baggage` 的 `session.id`。**`X-Conversation-Id` 不算**——它只是 cache salt，只帶它的對話永遠不會被鎖（稽核會記 `conversation_scope_latch: request_only`，外加 `conversation_scope_latch_hint: x_conversation_id_is_cache_salt_only` 提示）；要沿用它就把 app 的 `session_id_header` 設成 `x-conversation-id`（同時會啟用以它為鍵的 session affinity 路由）。沒帶任何對話 id 時：`per_turn` 只限縮觸發的那一輪，`always_restrict` 每一輪都限縮。

**不同層選了不同 engine**：`engines` 聯集，全部並跑、任一個擋就擋；子層**只能加、不能換**（要多個 engine 就只能疊加；enforce 下任一個判擋就先回，判通過要等全部）。**ADR-488（2026-09-29，#5416／#5420／#5417／#5418 已 merge、未部署）起**：內建 judge 釘的模型（`auto` 不算）、on_topic 範本（`xparse` 算）、NemoGuard 端點也改成**跨層、同層都疊加、每個都跑**（主題限制是「模型 × 範本」每組各判一次）；`fallback_model`、moderation／Jev 憑證、word filter 同一詞的 `replacement` 跨層仍上層贏，**同層改依 binding `precedence`（小者優先，同分先建者）選，不再 409**，Console 綁定 dialog 可以設 precedence。部署順序 gateway → IAM。`threshold` 只有內建 judge 與 Jev 內容臂看，OpenAI／NemoGuard 不看。某層 rail `enabled: false` = 那層等於沒寫（不貢獻任何 engine）——2026-09-29 起 PII 與 word filter 也一樣（C-219-49／C-224-21，#5443）。

**同一層多個 binding**：可以（聯集照算）。ADR-488 之後同一層給不同值也不會 409：判官類疊加、選擇類依 `precedence` 選。

**什麼會被擋、在哪裡擋**（2026-09-29 實測）：

| 在哪裡擋 | 情況 | 回應 |
| --- | --- | --- |
| 寫 policy version 時 | 同一個 version 的一條 rail 寫了 2 個以上 engine | 400（要多個 engine 就分成不同 policy 綁在不同層／不同 binding） |
| 寫 policy version 時 | 同一個 version 的 `on_topic.constraints` 寫 2 條以上 | 400（同上，每個 version 一條規則） |
| 寫 policy version 時 | 單一 version 超過 200 個 word filter 詞 | 400 |
| 寫 policy version 時 | PII entity 不在 12 種清單內（例如 `ssn`） | 400 |
| 寫 policy version 時 | 手寫 fold 才會產生的欄位（`classifier.models`、`on_topic.templates`、`inherited_selectors`） | 400 |
| 綁定時 | 這次綁定會讓某些 app 的 fold **新**壞掉——目前實際會觸發的是 fold 後超過 800 詞（停用層的詞不算） | 409，列出受影響的 app；停用／invalidate／移除 item 永遠不擋 |
| 綁定時不擋、只預告 | conversation scope 交集為空、資料邊界外呼（on_prem app） | 綁定成功＋預覽警告；請求時才 400／503 |

## Policy 跟「application proxy / model」有什麼關係？

兩個常見問題分開講：

### 1. Model（模型存取）

- Policy **不負責「選哪個模型」**（那是 routing 的事，ADR-085/088）。
- Policy 負責的是「**這個請求能不能去 cloud**」。
  - 例如：app 設定是 `on_prem`（只能用機房內模型），但請求被路由到 OpenAI（cloud）→ **Policy Kernel 擋下，回 403**。
  - 例如：key 標記 `data_egress = denied`，請求又要去 cloud → **擋下（資料不准外流）**。
  - **guardrail 的判定也算「出境」**（2026-09-22，#5235）：同一個 `on_prem` app，如果生效的 guardrail 政策用 `openai_moderation`／Jev／pin 到雲端模型的內建 judge 判定，那次判定在外呼**之前**就被拒（503 `classifier_boundary_blocked`，`on_failure=degraded` 才放行）——受檢文字不會因為「這只是 guardrail」就溜出去。
- **綁定時會不會擋？不會，但會預告**（#5238，SPEC-223 C-223-63）：綁一張含出境 evaluator 的 guardrail 政策到 tenant／group／app，回應多一個 `boundary_preview`，列出範圍內會被擋的 `on_prem` app；Console 綁定 dialog 停下來讓你看。**不在 IAM 擋**的理由：三條腿裡 IAM 只看得到一條（`data_egress` 是 key 的、air-gap 是部署的），而且 tenant／group 綁定治理的是**以後才建**的 app；裁決永遠在 gateway 逐請求做。
- **`profile_type` 不是真的不可變**：文件說「建立後不可變」，實際上 `PUT /iam/applications/{uuid}` 可以改（PRD-033 INV-2 只保證單一請求內不變）。撞到 503 的 on_prem app 有三條路：改 `hybrid` 再重 mint key、改用自架 evaluator（NemoGuard／本地 judge）、或 `on_failure=degraded`。把 app 改成 on-prem 時 Console 會先告訴你生效政策用了哪些出境 evaluator。

### 2. Application Proxy（agent app 的對外連線）

- 這是 `runtime_egress` 這種 policy 管的（還在實作中）。
- 它規定一個跑在容器裡的 agent app（例如 NemoClaw、Open WebUI）**可以連到哪些外部網址**，並硬擋危險目標（cloud metadata `169.254.169.254`、docker socket）。

---

## Workflow：一個請求進來，policy 什麼時候被用到？

這是最重要的「依賴順序」。Policy **不是只在一個點被用，而是在好幾關被檢查**。

```
Client 送請求
   │
   ▼
① Gateway 收到 → 呼叫 IAM 驗證 API key
   │   （IAM 此時順便把「最終 policy」算好、凍結成一張快照 snapshot）
   │
   ▼
② IAM 解析 policy（一個請求只算一次！）
   │   走 tenant → group → application → deployment
   │   每一層用「收緊合併」(tighten_merge) 疊起來
   │   → 得到這個請求的「最終規則」
   │   （快照塞進 auth_context，傳回 Gateway）
   │
   ▼
③ Gateway 第一關：enforce_request_policy
   │   檢查 streaming 准不准、tool 准不准、max_tokens 有沒有超
   │   → 違反就 403
   │
   ▼
④ Routing 決定要送去哪個 provider（on_prem 或 cloud）
   │
   ▼
⑤ Policy Kernel：執行合法性判斷（最核心的一關）
   │   純函數、不碰資料庫、同樣輸入永遠同樣結果
   │   檢查 boundary（on_prem/cloud）、data egress
   │   → 不合法就 403，而且任何人都不能 override
   │
   ▼
⑥ Admission Control：rate limit / 併發數
   │   → 超量就 429（太快）或 503（排隊滿了）
   │
   ▼
⑦ 開始執行 + streaming
   │
   ▼
⑧ Guardrail Enforcer：內容過濾 / 遮 PII / 擋關鍵字 / token 上限
   │   → 內容過濾與主題限制由 policy 指名的 engine 判；engine 是 Jev／OpenAI 時
   │     判定內容會送到平台外（Jev 會先過資料邊界 gate，不允許就 503、零外呼）
   │
   ▼
回傳結果給 Client
```

### 兩個平面（plane）要分清楚


| 平面                                  | 做什麼                                            | 由誰負責                        |
| ----------------------------------- | ---------------------------------------------- | --------------------------- |
| **Authoring plane（policy-as-code）** | 寫規則。用 YAML 檔案管理，走 CI/CD，再 `sync_policies` 進資料庫 | GitOps（檔案是 source of truth） |
| **Runtime plane（執行）**               | 套規則、擋請求。**不直接讀 YAML**，只讀資料庫快照                  | IAM 算、Gateway 擋             |


> 一句話：**「寫規則」和「執行規則」是兩件事、兩個地方。** Console 上可以加 override，但 GitOps 管的 baseline 在 Console 是唯讀的。

---

## Policy Kernel：為什麼它很特別？

`bustream/policy/kernel.py` 裡的 `evaluate()` 是整個系統最關鍵的「判官」：

- **純函數（pure function）**：不碰資料庫、不打 API、不看時間。同樣輸入永遠同樣輸出。
- **不能被繞過**：Gateway、Router、Worker 都**無權推翻**它的決定。
- **只有兩種答案**：Allow 或 Reject，沒有中間狀態。
- **Fail-fast**：拒絕時一定給明確錯誤碼（例如 `DATA_EGRESS_DENIED`），不會默默放行。

它要回答的就是一個問題：**「這個請求跨越了不該跨的界線嗎？」**

---

## 依賴關係速查（誰需要 policy 才能動）


| 元件                     | 對 policy 的依賴                       | 拿不到會怎樣                |
| ---------------------- | ---------------------------------- | --------------------- |
| **IAM**                | 負責「算」policy（resolve + merge），存在資料庫 | 算不出來 → 驗證失敗           |
| **Gateway**            | 從 IAM 拿凍結好的 policy 快照來擋請求          | 沒有 policy → 拒絕執行（不放行） |
| **Policy Kernel**      | 吃 app/key 的 boundary + egress 資訊   | 缺欄位 → 直接 reject       |
| **Admission Control**  | 吃 `rate_limit` 那段                  | 沒有 → 無法做限流            |
| **Guardrail Enforcer** | 吃 `guardrail` 那段                   | 沒有 → 無法過濾內容           |
| **Routing**            | **不依賴 policy**（policy 只判合法性，不選模型）  | —                     |


重要邊界：**Gateway 永遠只透過 IAM API 拿 policy，絕不直接讀 IAM 的資料庫。**

---

## ⚠️ 陷阱：Console 的「policy 區塊」會騙人

打開一個 application 的 Application Contract，你會看到一個 `policy` 區塊：

```json
"policy": {
    "routing_strategy": "complexity_routing", // 🔴 routing，不是 policy
    "token_quota_k": 0,                        // 🟡 純量 quota，非 PolicyBundle
    "rate_limit_policy": null,                 // 🟢 真 policy（未綁）
    "guardrail_policy": null,                  // 🟢 真 policy（未綁）
    "embedding_profile_config": null           // 🔴 ADR-089，根本不是 policy
}
```

> **關鍵觀念：「出現在 `policy` 區塊」或「出現在 Console 的 Gateways & Security 區塊」≠「是一個正式的 PolicyBundle kind」。**
> 這個 `policy` 區塊只是 AuthContext 的**方便分組**（程式碼在 `xparse_iam/.../client.py`），把一堆「跟請求把關有關」的欄位塞在一起——裡面混了真政策、純量設定、和完全不同的子系統。**5 個欄位裡只有 2 個是真 policy。**

### 5 個欄位的真實歸屬


| 欄位                         | 本質                       | 是 policy？      | 定義檔（IAM）                                                                      | 誰消費（執行）                                                      | fail 行為            |
| -------------------------- | ------------------------ | -------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------ | ------------------ |
| `rate_limit_policy`        | rate limit 政策物件（ADR-026） | 🟢 是           | `db/models/policy.py::RateLimitPolicy`                                        | Gateway admission                                            | 限流 429/503         |
| `guardrail_policy`         | 內容安全政策物件                 | 🟢 是           | `db/models/policy.py::GuardrailPolicy`                                        | Gateway guardrail enforcer                                   | 過濾/擋               |
| `routing_strategy`         | routing（選模型策略）           | 🔴 否           | `domain/value_objects/enums.py::RoutingStrategy` + `db/models/application.py` | Gateway routing 層（`plan_resolver.py`）                        | 選後端                |
| `token_quota_k`            | 純量 quota 欄位（累計額度）        | 🟡 否（非 Bundle） | `db/models/application.py:538`（`token_quota`，PRD-148；PRD-289 Addendum A 起是 application interim quota） | Gateway admission 從 IAM usage ledger 讀累計用量（`reserve_from_ledger`，scope `application_interim`、period `unbounded`） | 用完 **429**（`interim_application_token_quota_exhausted`）；ledger 讀取失敗時放行＋ERROR／metric |
| `embedding_profile_config` | embedding 子系統（ADR-089）   | 🔴 否           | `db/models/policy.py:264`（檔名誤導！）                                              | **只有 embedding worker**                                      | RAG 用              |


### 三個「非 policy」欄位細節

**🔴 `routing_strategy`** — 決定「要不要由系統自動選模型、怎麼選」。

- enum 值（2026-09-21 現況）：`none` / `complexity_routing`（ADR-406）/ `llm_judge_routing`（ADR-411）/ `jev_routing`（ADR-472，外部服務 TypeSafe Jev 判難度）/ `agent`（marketplace plugin app）。舊值 `smart_routing`、`base/twin/full/fast_only/large_only` 已由 ADR-397 P2 移除。
- ⚠️ **`jev_routing` 跟 guardrail 的 Jev engine 是同一家廠商、兩個獨立功能**：routing 用 `routing_parameters.jev_credential_uuid`（by uuid）、任何失敗 **fail-open** 退回 heuristic；guardrail 用 `classifier.jev_credential_ref`（by name）、失敗走 `on_failure`（預設 **fail-closed**）。兩者各有自己的 pre-release 開關（`jev_routing`／`jev_guardrail`），共用同一種 `jev` 憑證與同一個 TypeSafe 帳號額度（1,200 req/min）。
- **只能來自 Application，不能來自 API key**（routing 鐵則）
- 由 Gateway routing 層消費（`bustream/registry/plan_resolver.py`、`gateway/worker_setup.py`）

**🟡 `token_quota_k`** — application 的**累計** token 額度（UI 以 1K 為單位，故 contract 叫 `_k`）。不設（NULL）= 不限；API 只接受 ≥ 1 的整數，`0` 會回 400。**不會按月重置**，用完只能手動調高（PRD-289 G3）。

- 是 `applications.token_quota` 純量欄位（**不是** PolicyBundle，也不是 `budget` kind）。PRD-289 Addendum A／ADR-398 Amendment A 起它是 application 層的 interim quota，cost 軸對應 `interim_cost_quota_usd`
- **現況（2026-09-29）**：Gateway admission 在請求前從 IAM usage ledger 讀這個 app 的累計用量（`admission_handler.py` → `reserve_from_ledger`，scope `application_interim`、period `unbounded`），加上這次的估算量超過上限就回 **429** `interim_application_token_quota_exhausted`；請求完成後才用實際 token 入帳。ledger 讀取失敗時放行，並記 ERROR 與 metric
- Redis `TokenQuotaCounter` 還在寫，但 ADR-423 Phase 4b 起**不再是判斷依據**（只有沒設 ledger writer 的 gateway 模式，正式 Budget 才會退回 Redis）。`reconcile_token_quota` command 是從 audit 回寫 Redis，在一般部署下已沒有實際作用
- 已知缺口（#5439）：IAM 在 validate 時查額度設定若出錯，會當成「沒設額度」直接放行；Console 讀用量失敗時會顯示成「已用 0」
- 重點：**硬上限**（會 429 擋人），但不是 Policy Kernel 那種 403

**🔴 `embedding_profile_config`** — RAG / 知識檢索用哪個 embedding 模型（ADR-089）。

- model 是 `EmbeddingProfileConfig`，欄位含 `provider` / `model`（如 `text-embedding-3-small`）/ `endpoint` / `max_tokens` / `credential`
- API：`api/ninja_api/_embedding_profile.py`（CRUD + 指派給 application）
- **只被 embedding worker 讀**（INV-089-3），跟 chat routing、PolicyBundle 都無關
- 🎯 **最容易被誤認成 policy 的原因**：它的 model class physically 住在 `db/models/policy.py` 這個檔案裡（跟真 policy 同檔）——但檔名騙人，它是獨立子系統

> **共同點**：三個都存在 IAM、由 tenant_admin 在 Console 設定、被塞進 AuthContext 的 `policy` 區塊傳給 Gateway——但**三個都不是 PolicyBundle kind**，各自由不同子系統消費。

---

## 對照的正式文件（要深入再看）


| 文件                                                                      | 講什麼                                   |
| ----------------------------------------------------------------------- | ------------------------------------- |
| `docs/adr/core/Core-ADR-02-Policy-Authorization.md`                     | Policy & 授權的總導航                       |
| `docs/prd/core/Core-PRD-02-Policy-Authorization.md`                     | Policy Kernel 的 13 條 invariant        |
| `docs/adr/ADR-191-policy-as-code-and-runtime-policy-planes.md`          | policy-as-code 與 runtime 兩平面的分界       |
| `docs/adr/ADR-206-policy-inheritance-resolution-and-group-authoring.md` | group 可以自己訂 policy + 收緊合併             |
| `docs/adr/ADR-240-multi-kind-policy-bundle-container-model.md`          | 一張 bundle 裝多種 kind 的容器模型              |
| `docs/specs/SPEC-168-policy-as-code-runtime-policy-contract.md`         | policy-as-code 與三種 runtime policy 的契約 |
| `docs/specs/SPEC-173-policy-inheritance-merge-contract.md`              | 每個欄位「收緊」的合併規則                         |
| `docs/specs/SPEC-188-multi-kind-bundle-behavioral-contract.md`          | multi-kind bundle 的解析行為               |
| `docs/adr/ADR-249-guardrail-standalone-policy-kind.md`                  | guardrail 抽成獨立 PolicyKind               |
| `docs/spec/SPEC-223-guardrail-v2-contract.md`                           | classifier 兩條 rail 的契約；**C-223-52..60 = Jev**（依序：evaluator 與上限、請求形狀、憑證投影、邊界 gate、前文視窗、失敗對映、audit 與不計量、Test 契約、prod 扣住） |
| `docs/adr/ADR-476-jev-hosted-guardrail-judgement-source.md`             | Jev 當 guardrail 判定來源的架構決策（含 rollback §7.2） |
| `docs/adr/ADR-488-guardrail-judge-sets-and-precedence-selection.md`     | 判官疊加（SPEC-223 C-223-66）與同層 precedence 選擇（C-223-67） |
| `docs/spec/SPEC-195-policy-bundle-composition-and-versioning-contract.md` C-195-47 ＋ `docs/adr/ADR-259` Amendment A | 綁定時擋「會讓 app 新解析失敗」的寫入 |
| `docs/prd/PRD-332-jev-guardrail-judgement-source.md`                    | Jev engine 的需求與驗收、白話層              |
| `docs/adr/ADR-473-pre-release-feature-registry.md` ＋ `docs/spec/SPEC-295-pre-release-feature-registry-contract.md` | pre-release feature registry（為什麼 prod 看不到 Jev） |
| `guardrail.md`（同資料夾）                                                  | PII 遮罩的交接文件；Jev **不**做 PII            |



| 程式碼                  | 位置                                                                                      |
| -------------------- | --------------------------------------------------------------------------------------- |
| Policy Kernel（純函數判官） | `bustream/policy/kernel.py`                                                             |
| Policy 解析 + 合併       | `xparse_iam/xparse_iam/authorization/llm_operational_resolver.py`、`llm_policy_merge.py` |
| Gateway 各關卡          | `bustream/gateway/pre_execution.py`、`guardrail_enforcer.py`                             |
| Guardrail classifier  | `bustream/gateway/classifier_handler.py`（dispatch）、`classifier_judges.py`（逐判官臂，ADR-488）、`classifier_background.py`（先擋先回的背景臂，C-223-65）、`jev_guardrail_arms.py`（Jev 兩條 arm）、`execution_boundary.py`（資料邊界 gate）、`guardrails/jev/`（題目與 parser） |
| Guardrail 政策 schema／fold | `xparse_iam/xparse_iam/policies/schema.py`（`GuardrailPolicySpecV2`）、`authorization/guardrail_policy_merge.py`、`authorization/guardrail_judge_sets.py`（判官集合／同層選擇，ADR-488）、`authorization/bundle_item_fold.py`（同層 precedence 排序） |
| 綁定時檢查／預覽 | `application/use_cases/policy/resolution_gate.py`（C-195-47）、`composition_preview.py`（C-223-64）、`boundary_preview.py`（C-223-63） |
| 限流                   | `bustream/production/admission/controller.py`                                           |


