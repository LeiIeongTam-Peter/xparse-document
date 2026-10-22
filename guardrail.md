# Xparse PII 遮罩 — 這是什麼、我們怎麼做、什麼還沒做

> 交接文件，寫給新 session／另一個 agent／想知道我們到底做了什麼的人。
> **2026-10-21 更新（AWS Bedrock 成為 PII 的第二個語意偵測器，也是 content_filter 的第五個判定來源；ADR-522／PRD-375／SPEC-219 C-219-50..56／SPEC-223 C-223-69..76。細節見新增的 §2.9 與 §3.9）**：
> - **怎麼開**：政策的 Engine 選「AWS Bedrock」，PII 的語意偵測就改由 AWS `InvokeGuardrailChecks`（東京 `ap-northeast-1`）做；選其他 Engine 照舊用 GLiNER。#6977 起 PII 區塊沒有自己的偵測引擎選單，偵測器跟著 Engine 走。政策要指名一把 `bedrock` 憑證（`bedrock_credential_ref`），這把憑證必須以「Guardrail」用途、選了 region 建立。
> - **§0 那句「原文不出境」從此只對 GLiNER 成立。** 選 Bedrock 的政策會把**未遮罩的原文**送到 AWS——要找出個資在哪裡，就得送原文。INV-309-2 改寫成「選用，且出境前先過資料邊界閘」（C-219-55）：地端 app（`profile_type: on_prem`）、`data_egress=denied` 的 key、設了 `XPARSE_ONPREM_ENFORCE` 的部署 → 零連線、503，shadow 也一樣零連線。regex 層與遮罩仍在地端 sidecar，`mask_text` 仍是唯一產生代號的地方。
> - **Bedrock 偵測不到四類**：`national_id`、`birthdate`、`gender`、`messaging_id` 只靠 regex，Console 標「僅限地端比對」。
> - **fold 改依 engine 分組**（`pii.detectors[]`，最多兩組）：兩層指名不同偵測器時兩個都跑、結果聯集、只遮一次；同一個偵測器跨層照舊（entities 聯集、門檻取最低）。content_filter 的設定也改依 engine 合併。
> - **PR**：#6900（PRD-375／ADR-522）→ #6901、#6904（憑證）→ #6958–#6961、#6964–#6966、#6969、#6972、#6973（IAM、sidecar、gateway）→ #6974、#6975、#6977、#6978（Console），全部已 merge。**#7021 把 Bedrock 和 Jev 從 pre-release 畢業到所有部署**（rel、prod、客戶安裝都算；2026-10-21 merge，`915aff71a`）。**尚無環境部署**，目前只在 Peter 本機 stack 跑過。
> - **實測（2026-10-21，本機 stack、真 AWS）**：「陳大文／手機／email」遮成 `[NAME_…]`／`[PHONE_…]`／`[EMAIL_…]`，身分證由 regex 遮；威脅句 451（violence 0.8）；`on_prem` app 回 503、PII 檢查 0.14 ms、零 AWS 呼叫。報告在 `~/Desktop/testing/bedrock-guardrail-2026-10-21/REPORT.md`。
> - **還沒做的**：繁中校準的 held-out 驗收題組、在共用 dev 環境用真 key 跑端到端。見 §3.9。
> - **2026-10-22 中文姓名偵測率（118 題，兩輪結果相同）**：全名 100%（含複姓、英文、中英混合）；漏抓集中在「姓＋稱謂」（林小姐、王經理，6 個漏 5 個）；沒有姓名的對照題有 4/25 被誤遮成 `[NAME_…]`（李子、王道、白天、文明），enforce 時會改壞送給 LLM 的文字。報告 `~/Desktop/testing/bedrock-guardrail-2026-10-21/calibration/names/REPORT.md`。
> - **2026-10-22 第一輪校準（dev set，153 題）**：0.4／0.6／0.8 維持不變，`medium` 已是最佳值（145/153）。報告 `~/Desktop/testing/bedrock-guardrail-2026-10-21/calibration/REPORT.md`。
> - **錯誤路徑實測與修正（2026-10-21）**：用真元件觸發了截斷、逾時與斷路器、GLiNER 停掉、air gap、AWS 429，行為都符合 spec。另外找到三個問題，修正在 PR #7039（2026-10-21 已 merge，`ef9c06ea0`）。另有兩個後續項目，見 §3.9：Console 稽核頁有沒有名稱的列、shadow preview 的 `degraded` 語意。報告在 `~/Desktop/testing/bedrock-guardrail-2026-10-21/error-paths/` 與 `error-path-fixes/`。
>
> **2026-09-29 更新（PII 這條 rail 的 fold 改了一條，[#5443](https://github.com/futurenestit/xparse/pull/5443) 已 merge main，本地 dev 實測：停用層的 phone 不再被遮）**：下一段提到「`pii` 與 `word_filters` 理論上有同一種漏法」——**實測證實且已修**：某層 `pii: {enabled: false, entities: [phone], score_threshold: 0.4}` 以前會把 `phone` 與 0.4 聯進生效政策（實跑真的遮 phone）；現在停用的 `pii` 區塊是 fold identity（不貢獻 `entities`、門檻取 1.0 的 identity），只有 `enabled` 仍是 OR（SPEC-219 **C-219-49**，ADR-476 Amendment H）。`word_filters` 同步（SPEC-224 C-224-21）。policy-level `scan_system` 不受影響。部署時對靠停用層漏進來的 entity 是一次放寬。
>
> **2026-09-22 更新（Jev guardrail 對打實測；PII 這條 rail 仍零改動）**：對 dev 真 gateway 跑了 175 題 Jev vs 內建 gpt-5.4 judge 的同題對打（`~/Desktop/testing/問題集.md` §12、PRD-332 §9 補記），結論與四項修正見同資料夾 `policy.md` 頂端。跟本文有關的只有一件：**classifier rail 的 fold 改為「停用即空」（SPEC-223 C-223-61，#5208）**——但 `pii` 與 `word_filters` 沒改，它們的 `enabled` OR + `entities`／`terms` 聯集理論上有同一種漏法（停用的 `pii` 區塊仍貢獻 `entities`），這輪未實測、SPEC-219 另案，ADR-476 §7.4 留了 follow-up。**（2026-09-29：已實測證實並修掉，見上一則。）**
>
> > **2026-09-22 傍晚更新（guardrail × engine × routing 全矩陣，PR [#5258](https://github.com/futurenestit/xparse/pull/5258)，CI 綠待 merge；紀錄 `~/Desktop/testing/問題集.md` §14）**：三個真缺陷修掉——① `content_filter.stages: ["output"]` 以前 input 臂照跑照擋（gateway 沒讀 `input`）；② Jev 臂冷連線 deadline +2 s（3→5 s，breaker 探針不再永遠逾時）；③ `x-guardrail-redacted: true` 以前從不發出，現在遮罩成功的 chat（非串流／串流）與 Responses 串流都帶。矩陣本身：PII／word_filters／四種 content engine／三種 topic engine／`allow_small_talk`／`on_failure=degraded`／shadow／threshold 全部與本文一致；NemoGuard topic_control 在 air520 沒 adapter → 503 fail-closed 如 Test 按鈕所警告。
> > **2026-09-21 更新（Jev 成為 classifier rails 的第四個判定來源；PII 這條 rail 零改動）**：ADR-476／PRD-332／SPEC-223 C-223-52..60，六個 PR 全部進 main（#5191 docs · #5192 owner artifact · #5193 IAM 憑證面＋Test 路由 · #5194 gateway arms · #5198 IAM schema／fold／投影 · #5199 Console Engine 選項），**尚無環境部署**；prod 由 pre-release registry（`jev_guardrail`，`stage=rel`）扣住。**Jev 只判 `on_topic` 與 `content_filter`，不做 PII、不做 word filters**（理由見 §1.3）。跟本文有交集的只有一件事，但很重要：**Jev 是信任邊界外的 evaluator，拿到的是「送往 provider 的那份文字」——PII rail 在 enforce 時是遮罩後的，在 shadow 或沒開時就是原文**（C-223-45）。所以「PII enforce」是 Jev 政策的實質前提，不是可選加分。§3.8 末尾有 Jev 對那九項的影響。白話版見同資料夾 `policy.md` 的 guardrail kind 一節。
> **2026-09-17 更新（掃描範圍收斂，設計閉環 PR-D）**：對照 LiteLLM（09-14）與 Portkey 後的 review 找出九項（§3.8），Peter 全部拍板。契約已寫進 **ADR-448 Amendment H**（Responses 寬面 D23、跳過進 audit D24、word_filters block 面含工具參數 D25、`scan_system` 升為 policy 層 D26）與 **ADR-318 Amendment A**（tool 形狀結尾跳過 classifier、verdict memo、content_filter 吃 transcript、`scan_tool_results` 開關、Responses 最後一則 user item）；SPEC-219 Rev.9、SPEC-223 C-223-41 Rev + C-223-49..51、SPEC-224 C-224-32 Rev + 32b；PRD-285／ADR-389 翻 Accepted。實作六個 PR（base 皆 main、不 stack）**2026-09-17 全部 merge**：#4951 docs、#4959 IAM、#4961 G1、#4957 G3、#4954 Console（merge commit）、#4958 G2；G4 #4969（`scan_tool_results` runtime，#3）也於同日 merge——**九項全部進 main**；docs follow-up **#4974** 也 merge（`fdf573bcf`，回填 ADR-448 Am.H／ADR-318 Am.A 兩處驗證段 + SPEC/wiki/Core 的 PR 引用）。**全案八張 PR 收尾；剩部署（IAM → gateway → Console）與 A-4 `scan_tool_results` 的真判官 probe（需 provider key）。**G1 的 §8.1 真 sidecar probe：block 詞只在 `\uXXXX` 逃逸的 `tool_calls` 參數、寬面關 → main 漏、分支 451（PR #4961 comment）。細節 §3.8。
> **2026-09-15 更新（system 掃描改為政策開關，預設關閉）**：**PR #4860 已 merge**（`f36e826e7`，15 pass / 0 fail）—— `system` 指令與 Responses `instructions` 是否在 PII 面上，改由生效政策的 **`pii.scan_system`** 決定（fold **OR**、**預設 `false`**；ADR-448 **Amendment G** / SPEC-219 **Rev.8** C-219-47）。起因：Amendment C 明碼接受的代價（persona 名字／客服聯絡資訊被遮成代號）在部署前告知客戶時被部分租戶否決——**他們的 system 是產品文案，不是使用者貼的個資**；而平台在 wire 上分不出「注入型 system（RAG 名冊）」與「文案型 system（persona）」，所以這是**租戶級取捨**，不該是平台級單一答案。**未表態的政策從此不掃 system**，個資原樣出境且稽核仍記 `pass`（只有 `input_check` 的 `surface_system_skipped` 可事後判別）；連帶 word-filter **mask** 在 system 上退回 SPEC-224 C-224-32 的範圍（**block 不受影響**，走 body-wide `scan_text`，已對真 payload 驗過）。**部署序與前幾次相反：IAM + Console 先，gateway 後**——新欄位預設站在較鬆的一邊，要先讓管理員有地方把它打開。
> **2026-09-15 更新（block 呈現面，兩個 PR）**：**#4845 已 merge** —— classifier rails（on_topic / content_filter）的 graceful 預設**撤回**，未 authored `block_presentation` 一律 derive `error`（SPEC-223 C-223-25/27 修訂）；Console 的 `output_redaction_mode` / `block_presentation` 兩個下拉**移除**，存檔一律歸一化為 `stream` + 不送 presentation（SPEC-219 C-219-9a **Rev.3**），兩鍵仍可經 API 寫入。**#4851 已 merge**（`5fb1058e85`）—— 每個 violation type 都有 curated 客戶端訊息（含本文三個 PII 451 碼），退場了 `Request blocked by guardrail: <violation_type>` 這個會洩漏 rail 名的 fallback（SPEC-213 §3.1 / C-213-13..17）；Anthropic 面補 `451 → invalid_request_error`（原落 `api_error`，違反 SPEC-196 COMPAT-3）。**新發現且未解**：451 會讓 Codex 重試 5 次 → 一次 PII block = **6 次完整寬面掃描**，見 §3.6 與 issue #4854。
> **2026-09-14 更新**：June 對 merge 後的五個 PR 做真元件 review，開了 #4738–#4743 六張 issue。逐項複驗後四項成立、#4739 問題成立但論證的外推不成立、#4740 不成立（已附證據關閉）。另發現 **ADR-448 從來沒有 Amendment C**——程式碼三處引用它、INV-448-2 還寫著「system 明文排除」。處置在 PR #4764（契約）／#4765（guardrails）／#4766（gateway），已全部 merge（序：契約 → sidecar → gateway）。逐項判定見 **§3.6a**。
> **2026-09-14 晚更新**：#4764／#4765／#4766 已 merge。OpenCode 一句 `hi` 被 451 揭出三個缺陷 → **ADR-448 Amendment E（#4806）**：純文字 parts 陣列進改寫面、PII input 每次呼叫以剩餘預算為 timeout（預算 8 s → 30 s）、快取只存裁決；部署 dev 後長 system prompt 仍 503 → **Amendment F（#4807）**：sidecar 對 GLiNER 的 15 s timeout 是第三個常數，改為 gateway 把剩餘預算以 `timeout_ms` 帶下去。兩個都 merge 並部署到 dev（sidecar image 13:29 重建）。**剩下的是容量**：OpenCode 在 repo 目錄會把 `AGENTS.md`（36k 字）摺進 system prompt，CPU GLiNER 高載 ~1.3k 字/s、30 s 掃不完，dev `.env` 暫把 `XPARSE_PII_SCAN_BUDGET_MS` 拉到 120000；設計選項見 `docs/issues/agent_llmproxy.md` §9a。
> 現況基準（2026-09-17 12:xx，`26f7b70f3` = #4958 squash）：下一行 09-15 基準的全部 **+ #4951（Am.H／Am.A 契約）+ #4959（IAM `scan_system` policy 層 + `scan_tool_results` + audit_catalog 四欄）+ #4961（G1：tool 形狀結尾跳過 classifier、`ClassifierVerdictCache`、Responses content_filter 最後一則 user item、`guardrail_surface_system_skipped` 進 audit、`scan_text` 含工具參數葉值）+ #4957（G3：content_filter llm_classifier arm 吃 transcript、gateway 讀 policy 層 `scan_system` OR alias）+ #4954（Console：開關搬「保護設定」、`scan_tool_results` 開關）+ #4958（G2：Responses PII 寬面涵蓋 assistant 項／`function_call.arguments`／`function_call_output`、step-1 slot 依 type 分類）**。**+ #4969（G4：`content_filter.scan_tool_results` runtime——每個 tool 結果各判一次、per-tool memo、stage memo key 含 tool 文字、`classifier_target` audit 欄位、ceiling 走 `classifier_surface_too_large`、Semaphore(4)）**（`404b54a28`）。dev/rel/prod 都還沒部署這批——部署序 IAM → gateway → Console；Codex 使用者的 tool 輸出個資會開始被遮、首輪冷啟動變慢。
> 現況基準：`origin/main` @ 2026-09-15 18:02（`9845e3db6`，含 #4806 / #4807 / **#4860**）—— **#4727 契約 · #4728 guardrails 偽陽性過濾 · #4729 gateway enforce 切換 · #4735 system 納入 · #4733 legacy `blocked_keywords` 接上 word_filters · #4764–#4766 review 修復 · #4806 Amendment E · #4807 Amendment F，全部已 merge**；#4527、#4528 已關閉。**main = 全對話（user／assistant／tool 訊息、tool 參數）遮罩；`system` 與 Responses `instructions` 則是 per-policy、`pii.scan_system` 預設 `false` ⇒ 未表態的政策不掃**（#4860 Amendment G，2026-09-15 起——**這一行在 09-15 之前寫的是「含 system」，那句自 #4860 起不再成立**）。 **rel 與 prod 都還沒帶這批**（兩個分支都沒有 `guardrail_input_surface.py`），部署面仍是「只遮最後一則 user 訊息」。部署序：#4728 sidecar image **先**，再 gateway。文中「PR-5 前」= rel/prod 目前的行為。**word filters（PRD-285）整條 rail 也只在 main**——rel（落後 **621** commits）與 prod（落後 **1061**，2026-09-15 重算）連 `guardrails/word_filters.py` 都沒有，見 §2.8。
> 權威來源是 `docs/`：**PRD-241**（what/why）· **ADR-309**（how）· **ADR-448**（偵測面 ⊥ 改寫面）· **SPEC-219**（行為契約）· AWS Bedrock 那一層：**PRD-375**／**ADR-522**（2026-10-20 起）。本文與它們衝突時以 `docs/` 為準。

---

## 0. 一句話

**使用者貼進 AI 的個資，在送出公司之前被換成型別化代號；偵測個資的模型裝在客戶自己的機房，原文不出境。**

一句話的代價也要講清楚：**main 已遮「輸入」的全部——user/assistant/tool 訊息、tool call 參數**（#4729，2026-09-13），而 **system 指令與 Responses `instructions` 是租戶自己決定要不要掃、預設不掃**（#4735 給了能力、#4860 Amendment G 把預設翻成關，2026-09-15）——但直到 **ADR-448 Amendment E（PR #4806，2026-09-14）** 之前這句只對 `str` content 成立：任何 list content（**含純文字 parts 陣列**，OpenAI SDK／AI SDK agent client 對多 part user turn 的送法）偵測到就 451，OpenCode 一句 `hi` 就被擋；Amendment E 起純文字 parts 逐 part 寫回，451 只留給夾 image／audio 的 list；**rel/prod 部署前仍只遮「最後一則 user 訊息」**。「只遮輸入」這個限定詞仍是缺口（輸出側不遮，見 §3.2）。

> **2026-10-21**：「偵測個資的模型裝在客戶自己的機房」這半句只對預設的 GLiNER 成立。政策 Engine 選 AWS Bedrock 時，PII 的語意偵測在 AWS 東京做，送出去的是**未遮罩的原文**；regex 層與遮罩仍在地端 sidecar。見 §2.9。

---

## 1. 這是什麼

### 1.1 客戶看到什麼

員工把「我叫陳大文，身分證 A123456789，手機 0912-345-678，幫我寫封信」貼進 AI。

- **沒有 Xparse**：這句話原封不動送到 OpenAI／任何模型商，個資出了公司。
- **有 Xparse**：模型商收到的是「我叫 `[NAME_1]`，身分證 `[NATIONAL_ID_1]`，手機 `[PHONE_1]`，幫我寫封信」。信照寫、工作照做。

管理員在 Console 勾選要保護哪幾類（姓名／電話／身分證／地址⋯共 12 類）就完成設定。

### 1.2 我們賭的是什麼（PRD-241 §1.2）

PII 遮罩本身是 **commodity**——AWS Bedrock、LiteLLM、Portkey、Presidio 都有。經對抗式查證後，差異化不在「有沒有」，而在兩件可驗證、可演示的事：

1. **中文覆蓋**：主流方案的中文姓名／地址偵測普遍薄弱。我們上一代用 Presidio + spaCy `en_core_web_lg`，中文姓名偵測率 **≈ 0%**（#2048）——繁中 prompt 的個資實質裸奔。
2. **資料不出境**：hosted PII 偵測 API（把原文送去另一朵雲判斷）與「個資不出境」的訴求自相矛盾。我們的偵測模型跑在客戶部署範圍內（INV-309-2）。

> **不要把這兩點寫成「我們有 PII 遮罩」去賣。** 那句話沒有差異化，而且一講就會被拿去跟人家的 feature 清單並排。
>
> **2026-10-21：接上 AWS Bedrock 不改變這兩點的賣法。** Bedrock 是給「已經核准用 AWS」的客戶的選項：
> - 它的繁中偵測品質沒有評測證據，文案不得寫「更準／更安全／更適合中文」（PRD-375 U8 紅線）。
> - 選它的政策就放棄了第 2 點，因為原文會送到 AWS。
>
> 差異化仍然是 GLiNER 地端那條路。

### 1.3 它不是什麼

| 不是 | 為什麼要講 |
|---|---|
| 不是可逆的 | V1 遮罩不可逆（SPEC-219 §4）。模型看到的是代號，你拿不回原文。 |
| 不是輸出側防護 | `check_output` 在 V1 是 pass-through（INV-309-9）。模型把個資**吐回來**時完全不遮。見 §3.2。 |
| 不是合規認證 | 它是一個技術控制，不是「我們符合 GDPR/個資法」的證明。 |
| 不是全對話保護（**rel/prod 部署前**；且 system 預設不在內） | 見 §3.1。main 已修（#4729），涵蓋 user／assistant／tool 與 tool 參數。**`system` 要另外開**（`pii.scan_system`，預設 `false`，#4860）——開了才遮，代價是 persona 名字與客服聯絡資訊也會被遮成代號；不開則 system 裡的個資原樣出境且稽核仍記 `pass`。見 §3.6。 |
| 不是 prompt injection / jailbreak 防護 | 那些維度在 V1 收斂時全數移出（PRD-241 §1.1），由 ADR-318 的 classifier rails 另案處理。 |
| 不是 Jev（或任何 hosted 判定服務）的工作 | 2026-09-21 Jev 進了 classifier rails（ADR-476），自然會有人問「PII 也交給 Jev 判不就好了」。**不行，兩個理由**：① Jev 回的是「是／否、機率、等級」，**沒有 span**——不知道個資在字串的哪裡就沒辦法遮；② 要判就得把**原文**送到 TypeSafe 的雲，直接違反 INV-309-2「偵測模型跑在客戶部署範圍內、原文不出境」，也就是 §1.2 我們賭的那件事。word filters 同理不用 Jev：決定性 matcher 誤擊 0%、個位數毫秒、免費、會回 span，而 Jev 在 held-out 上誤擊 16.7%，且**整份詞表每個請求都會送到第三方**（租戶的禁用詞本身常常就是機密）。出處：ADR-476 §3.1（workload-fit 論證，明文把 PII 與 word filters 列為 out of scope）· PRD-332 §1.4 Non-Goals。**（2026-10-21：AWS Bedrock 是這兩個理由的例外，見 §2.9。① `InvokeGuardrailChecks` 會回位置（`beginOffset`／`endOffset`，以 code point 計），所以能接進遮罩；② INV-309-2 已改成「選用，且先過資料邊界閘」（C-219-55）。Jev 仍然不做 PII。）** |
| 不是「選了 AWS Bedrock 就全部交給 AWS」（2026-10-21 起） | Bedrock 只取代 GLiNER 那一層語意偵測：<br>• regex 層照跑，遮罩仍在 sidecar；<br>• `national_id`、`birthdate`、`gender`、`messaging_id` 四類 Bedrock 偵測不到，只靠 regex；<br>• sidecar 仍要活著，`/ready` 仍要求 GLiNER（ADR-522 §5.2）。<br>只選 Bedrock 的政策不會真的呼叫 GLiNER，但部署上還拿不掉它。 |

---

## 2. 我們怎樣做

### 2.1 全鏈

```
Console 作者面                IAM（治理）                    Gateway（執行）                  Guardrails sidecar          GLiNER server
─────────────                ───────────                    ───────────────                  ──────────────────          ─────────────
勾 12 類 entity      ──▶  GuardrailPolicy spec      ──▶  validate 拿到 policy      ──▶  POST /v1/guardrails/check  ──▶  POST /v1/extract
設 score_threshold        pii{enabled,entities,          抽文字 → 呼叫 sidecar          兩層偵測 + span merge          零樣本 NER
選 shadow/enforce         action:mask,threshold}         拿 modified_content            + 型別化 token 遮罩             (urchade/gliner_multi_pii-v1)
                          跨 scope fold（§2.4）          寫回 request.messages
                                                         ↓
                                                       provider 收到遮罩後的 payload
```

**邊界紀律**：Gateway 不 import guardrails 的 engine（INV-202-3，CI gate 擋）；IAM 與 guardrails 只透過 wire 與 pinned artifact 整合（PRD-302 / ADR-418）。

**2026-10-21 起，政策 Engine 選 AWS Bedrock 時**（ADR-522 §2.2.6–2.2.7）：AWS 是由 gateway 呼叫的，因為 sidecar 不持有任何憑證。AWS 只回位置，遮罩照舊在 sidecar 做：

```
Gateway                                    AWS Bedrock（ap-northeast-1）           Guardrails sidecar
───────                                    ─────────────────────────────           ──────────────────
資料邊界閘 vendor_call_block_source ─不過─▶ 503 pii_detector_boundary_blocked（零連線，shadow 亦然）
  │ 過
  ▼
POST /guardrail-checks/invoke  ─────────▶  sensitiveInformation：type、confidenceScore、
（未遮罩原文；一次 ≤40 block／50k 字）       beginOffset／endOffset（code point）
  ◀──────────────────────────────────────
門檻過濾 → 反查 entity id → external_spans ───────────────────────────────▶ POST /v1/guardrails/check
                                                                            regex 照跑；GLiNER 不跑（gliner_entities: []）
                                                                            external span score ≤ 0.99，重疊時 regex 勝
                                                                            merge_spans → mask_text（唯一的代號產生點）
  核對 external_spans_accepted == 送出筆數 ◀────────────────────────────────  回 external_spans_accepted
```

### 2.2 兩層偵測，12 類 entity

單一來源：`apps/guardrails/xparse_guardrail/contract/pii_entities.py`（公開鏡像在 `contracts/policy-capabilities.v1.json`）。

| entity id | token | 語意層（GLiNER label） | 語意層（AWS Bedrock type，2026-10-21 起） | 決定性層（regex） |
|---|---|---|---|---|
| `person_name` | `NAME` | person | `NAME` | 中英文姓名介紹句、標記欄位 |
| `email` | `EMAIL` | email | `EMAIL` | email 格式、標記欄位 |
| `phone` | `PHONE` | phone number | `PHONE` | 台灣手機／市話、北美電話、標記欄位 |
| `national_id` | `NATIONAL_ID` | national id number | —（只靠 regex） | 台灣身分證／居留證、中國身分證 |
| `passport` | `PASSPORT` | passport number | `US_PASSPORT_NUMBER`（台灣護照號碼沒有實測） | 標記欄位 |
| `address` | `ADDRESS` | address | `ADDRESS` | 標記欄位 |
| `birthdate` | `DATE` | date of birth | —（只靠 regex） | 標記欄位 |
| `age` | `AGE` | age | `AGE` | 一般年齡、標記欄位 |
| `gender` | `GENDER` | gender | —（只靠 regex） | 標記欄位 |
| `credit_card` | `CREDIT_CARD` | credit card number | `CREDIT_DEBIT_CARD_NUMBER` | 卡號 |
| `messaging_id` | `MESSAGING_ID` | —（決定性專屬） | —（只靠 regex） | 標記欄位 |
| `secret` | `TOKEN` | —（決定性專屬） | `AWS_ACCESS_KEY`、`AWS_SECRET_KEY`、`PASSWORD` | OpenAI key／JWT／AWS key／GitHub token／bearer／DB URL |

Bedrock 那一欄的對應只有一份常數，在 gateway 的 `guardrails/bedrock.py`（`PII_ENTITY_MAPPING`）。artifact 有鏡射，由 `bedrock-guardrail-parity-gate` 鎖住。AWS 回來的 type 若反查不到 entity id 就丟掉，因為那不是我們要求的。

- 決定性 span 帶 score 1.0，**永遠不被語意 span 擠掉**（C-219-19）。Bedrock 的 span 進 sidecar 時 score 上限 0.99，所以同樣贏不了 regex（INV-522-5）。
- 語意層 span 先過**偽陽性過濾**（#4728，四條規則；決定性層永不過濾），再把兩層結果經 `merge_spans` 去重疊（priority → score → 長度 → 位置），最後一次遮罩。過濾器自 #4765 起可用 `XPARSE_PII_FALSE_POSITIVE_FILTER=false` 關掉，見 §3.3。2026-10-20 起過濾器也套用在 Bedrock 的 span 上（`SEMANTIC_SOURCES = {"gliner", "external:bedrock_pii"}`）：四條規則看的是字面值，跟偵測器無關。
- **刻意不做**姓氏 heuristic（`likely-chinese-full-name`）——誤判類別，設計上排除（C-219-5）。

**引擎部署**：`apps/gliner-server/`，模型 `urchade/gliner_multi_pii-v1`，權重在 build 時烘進 image、runtime `HF_HUB_OFFLINE=1`。sidecar 只透過 HTTP 消費它（`XPARSE_GLINER_SERVER_URL`，預設 `http://xparse-gliner:8401`），零 import。

**但 prod 與 rel 都沒有跑這個容器**——`gliner-server` 刻意不在 CI build matrix（2.43GB 權重），沒有 ECR image，兩邊都指向 air520 的地端機。所以那個 compose 預設值在任何真實環境都是錯的：漏設 `XPARSE_GLINER_SERVER_URL` 的環境會對每個 check 回 502。詳見 §5.2 與 `docs/runbooks/guardrail-gliner-onprem-endpoint-for-aws-xparse.md`。

**Bedrock 不需要部署任何東西**（2026-10-21）：主機固定是 `https://bedrock-runtime.ap-northeast-1.amazonaws.com`，region 允許清單目前只有東京（IAM `domain/bedrock_guardrail.py` 的 `BEDROCK_GUARDRAIL_REGIONS`）。要的是租戶自己的一把 `bedrock` 憑證，用「Guardrail」用途建立並選 region，IAM 會把 region 推導成 endpoint 存起來。只用推論用途建立、沒有 region 的 `bedrock` key 不能拿來做 guardrail：投影回 `no_endpoint`，請求 503。細節見 §2.9。

> ⚠️ **本機 dev 連 sidecar 本身都預設不會起**（2026-09-17 實測）。`docker-compose.dev-mvp.yml` 的
> `xparse-guardrails` 同時被兩件事關著：`profiles: [guardrails]`（一般 `up` 不含它）**和** ECR image
> tag（本機沒有）。所以就算想開 profile 也會失敗。
>
> **失敗是靜默的，而且只掉一半。** PII 與 word_filters 在 sidecar 裡評估；classifier 兩條
> （content_filter / on_topic）跑在 gateway in-process。沒有 sidecar 時整個 stack 看起來健康、
> classifier 照常擋人，而**這兩條 rail 直接沒有任何效果**——不報錯，Console 上也看不出差別。
> 一個已經設定 PII 遮罩的租戶，會在所有燈都綠的情況下把沒遮的原文送給模型商。
>
> 起法（用**既有的** overlay，別再加新檔——`docker-compose.guardrails-local.yml` 早就存在）：
>
> ```bash
> docker compose -p xparse --project-directory . \
>   -f deployments/compose/tiers/docker-compose.dev-mvp.yml \
>   -f deployments/compose/overlays/docker-compose.guardrails-local.yml \
>   up -d --no-build xparse-guardrails
> ```
>
> **明確指名 service** 是繞過 profile 的關鍵（同一組 `-f` 下 `config --services` 不會列出它）。
> `xparse-gliner` 是 peer service 不是依賴，不指名就不起——本機用 `.env` 的
> `XPARSE_GLINER_SERVER_URL` 指向地端 detector 即可，省掉 3.71GB 的權重 image。
> 起來後 `docker exec xparse-guardrails ...:8400/ready` 應回 `{"status":"ready","gliner":"ok"}`。

### 2.3 遮罩 token 的兩種形式

`[<TYPE>_<SUFFIX>]`，由 `profile.pii_token_salt` 決定用哪一種（SPEC-219 §4）。

| | 序數形式 | 內容衍生形式 |
|---|---|---|
| 長相 | `[NAME_1]` | `[NAME_3f2a9c17]` |
| 何時 | 沒送 salt（歷史行為） | 送了 salt（ADR-448 後的新路徑） |
| 範圍 | **一次引擎呼叫**內同值同號 | 跨呼叫、跨請求、跨訊息位置皆同 |
| 算法 | 依處理順序遞增 | `blake2s(type\x00NFKC-strip-casefold(值), key=blake2s(tenant salt, 32))` 取 8 hex |

**為什麼要有第二種**：序數配置器的範圍是「一次引擎呼叫」，而 SPEC-219 §4 寫的是「per distinct value **within a request**」。這兩句話只在「一個 request 只掃一次」時等價。一旦逐則掃描，兩個不同的人會各自拿到 `[NAME_1]`——**那不是遮得不夠，是靜默捏造一個不存在的身分關係**，模型會把兩個人讀成同一個。

現況：gateway 已經在送 salt（`XPARSE_PII_CONTENT_DERIVED_TOKENS=false` + 重啟可回退）。audit retention 路徑（`redact_pii`）**刻意維持序數**。

> ⚠️ **key 導出在 PR #4631 改過，那之前的實作是壞的。** 原文（SPEC-219 §4 Rev.2、ADR-448 INV-448-6 都字面寫著）是 `key=salt[:32]`；blake2s 的 key 上限就是 32 bytes，而 gateway 送的 salt 是 `f"{tenant_uuid}:{epoch}"`，光 UUID 就 36 字元——**epoch 永遠被截掉**，`XPARSE_PII_TOKEN_SALT_EPOCH` 轉動不產生任何效果，而且前 32 字元相同的兩個 tenant 會共用同一個化名空間。現在改成把 salt **壓縮**成 key 而非截斷。細節見 ADR-448 Amendment A。
>
> 同一個 PR 補上另一件事：`check_input` 的 `tenant_uuid` 是**有預設值的 keyword-only 參數**，而空值是合法狀態（⇒ 序數），所以「忘記傳」在引擎端跟「這個請求沒有 tenant」**完全無法區分**。四個呼叫點裡 `guardrail_detection.observe_detection_surface` 與 `/v1/guardrails/preview` 原本都沒傳——前者把序數結果寫進 enforce 期要消費的快取，後者讓作者面看到的 token 與 runtime 不一致（而且兩個不同的人都預覽成 `[NAME_1]`）。

> ⚠️ **改 token 格式時必查**：`is_reserved_replacement` 擋 word-filter 的 `replacement` 假冒 PII token（C-224-6 / C-219-33），邏輯在 `apps/guardrails/.../contract/word_filters.py` 與 `apps/iam/.../guardrails/word_filters.py` **各有一份逐字複製**，必須同批改。它們不會出現在 guardrail 的 grep 結果裡（檔名是 word_filters）。

### 2.4 政策怎麼寫、怎麼 fold

```yaml
apiVersion: xparse.policy/v1
kind: GuardrailPolicy
metadata: { name: pii-baseline }
spec:
  version: v1
  engine: gliner_pii          # V1 唯一可寫值；v2 起可寫 bedrock_pii（ADR-522，2026-10-20），
                              # 且同一個 version 必須帶 spec 層的 bedrock_credential_ref（C-219-56）
  enabled: true
  mode: shadow                # shadow | enforce，預設 shadow
  pii:
    enabled: true
    entities: [person_name, phone, national_id]
    action: mask              # V1 固定字面值
    score_threshold: 0.5      # (0, 1]
    scan_system: false        # 預設 false —— system 指令與 Responses `instructions`
                              # 只有在這裡打開時才在偵測／改寫面上（C-219-47）
  # v2 起同一份政策可再帶第二條 rail（ADR-389 / SPEC-224，見 §2.8）：
  # word_filters:
  #   enabled: true
  #   terms:
  #     - { term: "獵鷹計畫", action: block }
  #     - { term: "iPhone 18 Pro", action: mask, replacement: "我們即將推出的旗艦手機" }
```

跨 scope（tenant / group / application）fold，**單調收緊、只會變嚴不會變鬆**：

| 欄位 | operator | 方向 |
|---|---|---|
| `enabled` / `pii.enabled` | OR | on-wins |
| `mode` | enforce-wins | 嚴的贏 |
| `pii.entities` | set-union（**只算啟用的層**；`enabled: false` 的區塊＝沒寫，C-219-49，2026-09-29 #5443） | 多的贏 |
| `pii.score_threshold` | **min**（只算啟用的層） | 低的贏（更敏感） |
| `pii.scan_system` | OR | on-wins（子 scope 可以把 system 加回面上，**永遠關不掉**） |
| `engine`（**只指 PII 偵測器**，不是 classifier 的判定來源） | **依 engine 分組**（2026-10-20 起，C-219-50；之前是 child-overrides）。每個不同的值是一個偵測器，最多兩組，bundle 裡每個偵測器各跑一次。組內 `entities` 聯集、`score_threshold` 取最低；組與組不混。fold 後的快照多帶 `pii.detectors: [{engine, entities, score_threshold}]`，只由 fold 產生，作者寫入帶它會 400。 | 多的贏：下層可以加偵測器，拿不掉上層的 |
| `bedrock_credential_ref`（spec 層，PII 與 content 兩條 rail 共用；2026-10-20 起） | ancestor-pin；同層依 binding `precedence`（C-223-67） | 上層釘了用誰的 AWS key，下層換不掉 |
| `word_filters.enabled` | OR | on-wins（§2.8） |
| `word_filters.terms` | set-union（**只算啟用的層**，C-224-21；fold 後上限 800、停用層的詞不算，超過 fail-closed C-224-53） | 多的贏；同一個詞在兩層動作不同時 **block 贏**（收緊） |
| `word_filters.terms[].replacement` | ancestor-pin；同層依 binding `precedence` | 跨層上層的贏；**同一層**兩個 binding 給同一個詞不同 replacement → 依 binding `precedence`（小者優先，同分先建者）選一個（ADR-488 / SPEC-224 C-224-19，已 merge 未部署；之前是綁定 409，更早是綁定成功、每個請求 fail-closed）。fold 後超過 800 詞仍會綁定 409（SPEC-195 C-195-47） |

> ⚠️ **「單調收緊」是政策層的性質，不是引擎層的。** `entities` 是 set-union，而 set 沒有順序——但實測（2026-09-11，對真 sidecar）**同一個集合換個順序會得到不同的偵測結果**，而且是 deterministic 的（各跑 5 次一致）：`["national_id","person_name"]` 對「好的，我記住了。」什麼都沒找到，`["person_name","national_id"]` 找到 `person_name`。**真陽性不受影響**（真名在四種排列下都被抓到），受影響的只有門檻邊緣的偽陽性。集合**變大**也一樣：`剛才`、`客戶` 只在 12 類全開時才被誤判成姓名。→ 見 §3.3。

> classifier 兩條 rail（`on_topic`／`content_filter`）的 fold 不在這張表：`engines` 跨層**聯集**（子層只能加、不能換掉上層的 engine，全部並跑、任一個擋就擋）、`on_topic.constraints` 跨層聯集但 runtime 要求**每一條都成立**（兩層寫不同主題 ≈ 全擋）。兩者都是刻意設計；2026-09-29 起綁定 dialog 會用一行 `composition_preview` 講出來（SPEC-223 C-223-64）。完整說明見 `policy.md`〈Inherit 怎麼算〉。
>
> **ADR-522（2026-10-20，PR-10 #6969）**：`content_filter` 的類別、門檻、stage、`scan_tool_results` 改成**依 engine 分組**合併，輸出 `classifier.content_filter.engine_configs[]`。不同 engine 只判各層指名給自己的部分，不再每個 engine 都拿整條 rail 合併後的設定。
> - 單一 engine 的政策逐位元不變。
> - 不同層指名不同 content engine、而且設定不同的 bundle，實際執行會變寬：不變量是「每一層自己寫的要求都還在」（INV-522-3），不是「每個 engine 都判全部」。
> - 盤點指令 `inventory_guardrail_engine_configs`（唯讀）可以在部署前列出受影響的單位。
>
> **ADR-488（2026-09-29，已 merge 未部署）**：內建 judge 釘的模型（`auto` 不算）、on_topic 範本（`xparse` 算）、NemoGuard 端點改成跨層、同層都**疊加、每個都跑**（主題限制＝模型 × 範本各判一次）；`fallback_model`、OpenAI moderation／Jev 憑證跨層上層贏、同層依 binding `precedence` 選。部署順序 gateway → IAM → Console。完整規則見 `policy.md`〈Inherit 怎麼算〉。

寫入邊界 fail-fast：未知 entity id → 4xx；threshold 出界 → 4xx；帶任何 legacy 欄位 → 4xx `GUARDRAIL_LEGACY_SCHEMA`（C-219-1/2）。`entities: []` **合法**，folds/enforces 成 no-op（C-219-3）。`engine: bedrock_pii` 的 version 會在這三種情況被擋成 400（C-219-56）：不是 v2；沒帶 `bedrock_credential_ref`；ref 指不到本租戶一把現存的 `bedrock` 憑證。ref 是指到別家 provider 的同名憑證也算指不到。entitlement 留到 runtime 才驗。

### 2.5 shadow / enforce 與失敗語意（SPEC-219 §6）

| 情境 | enforce | shadow |
|---|---|---|
| 偵測到 PII | 遮罩後轉送，audit 記型別+數量；**回應帶 `x-guardrail-redacted: true`**（SPEC-213 C-213-6；⚠️ 2026-09-22 傍晚 #5258 前這個 header 從沒發出過——helper 在、沒人呼叫） | **轉送原文**，audit 記 `would_mask`，**無** header |
| 什麼都沒偵測到 | 轉送 | 轉送 |
| **偵測服務掛掉／逾時** | **擋下**（**503** `guardrail_timeout`／`guardrail_service_unavailable`，原文絕不轉送——是 5xx 不是 451，AI SDK 類 client 會對它自動重試，OpenCode 的 `retrying in 8s attempt #3` 就是這個） | 轉送原文，audit 記 `degraded` |
| fold 後 `entities=[]` | no-op 轉送 | 同左 |
| 偵測到但**改寫不了**（**含非文字 part** 的 list content、壞 JSON 參數、遮罩拆不回同數葉值） | **451** `guardrail_unredactable_span`。⚠️ Amendment E（PR #4806）之前**任何** list content 都算改寫不了，含純文字 parts 陣列——step 1 路徑回 `input_blocked`、寬面回 `guardrail_unredactable_span`，同一個請求兩種 451 | 轉送原文，observe |
| 掃描**超時**（`XPARSE_PII_SCAN_BUDGET_MS`，**Amendment E 起預設 30000**；每次引擎呼叫的 HTTP timeout 也由剩餘預算導出） | **451** `guardrail_scan_budget_exceeded`。⚠️ Amendment E 之前 per-call 受 `XPARSE_GUARDRAIL_TIMEOUT_SEC`=5 s 約束、比 8 s 預算短——預算從未真正生效，17k 字 system prompt 一律 503 `guardrail_timeout`。**還有第三個常數（2026-09-14 晚 dev 實測）**：sidecar 對 GLiNER 自己的 `XPARSE_GLINER_TIMEOUT_MS` 預設 **15000**，超過回 502 → gateway 記 `engine_error` 503；dev compose 的 guardrails service 只 passthrough `XPARSE_GLINER_SERVER_URL`，這個 knob 寫進 `.env` 也到不了容器。GLiNER 負載高時 15k 字要 24 s（低載 10 s），所以 gateway 預算 30 s 對單一長訊息仍不成立。本機暫時用 `~/Desktop/testing/guardrails-gliner-timeout.override.yml`（`-f` 附在四個 dev compose 之後）把它拉到 30000；正解 = **PR #4807（ADR-448 Amendment F）**：gateway 把剩餘預算以 `timeout_ms` 帶進 check 請求、sidecar 以它為 GLiNER timeout，15 s 預設只剩無 deadline 呼叫者的退路；compose 也補了 passthrough。merge 後要 **rebuild** 本地 `xparse-guardrails:dev`（無 live mount）再 recreate，override 檔才可刪。**#4807 部署到 dev 後（2026-09-14 21:45）**：deadline 傳遞正確（sidecar 準時在 30.07 s 回 502），但 OpenCode 在 repo 目錄下會把 `AGENTS.md`（xparse/ 36k 字、X-parse/ 16k+37k 字）摺進 system prompt，CPU GLiNER 高載時只掃 ~1.3k 字/s，30 s 掃不完那一則、timeout 依 C-219-45 不進快取 → 每輪重炸、永遠暖不起來。dev 的 `.env` 已把 `XPARSE_PII_SCAN_BUDGET_MS` 拉到 120000（首輪約 40–60 s，之後命中快取）。**這是容量／設計題**：長 system prompt 的冷啟動成本，選項見 issue 文件 §9 補記 | n/a（shadow 只截斷記 log） |
| 偵測面**超過上限**（`XPARSE_PII_DETECTION_SURFACE_MAX_MESSAGES`，24） | **451** `guardrail_surface_too_large` | 同上 |
| **Bedrock 偵測器被資料邊界閘擋下**（2026-10-21 起；`on_prem` app、`data_egress=denied` 的 key、`XPARSE_ONPREM_ENFORCE`） | **503** `guardrail_service_unavailable`，零連線；audit 的 violation 是 `pii_detector_boundary_blocked`（C-219-53／55） | 轉送原文、零連線、記錄邊界來源 |
| **Bedrock 憑證不能用**（沒指名、不存在、沒授權、沒有 region endpoint、host 不是允許的 `bedrock-runtime` region） | **503** `engine_error`，零連線；gateway log 會寫明原因，例如「credential has no guardrail endpoint」 | 轉送原文，audit 記 `degraded` |
| **AWS 回錯**（401／403／429／400／5xx、格式錯、位置超出範圍、sidecar 回的 `external_spans_accepted` 跟送出數不符） | **503** `engine_error`（`guardrail_service_unavailable`）。429 永不重試，連線層失敗重試一次 | 轉送原文，audit 記 `degraded` |
| **Bedrock 逾時**（單次上限 = min(剩餘掃描預算, `XPARSE_BEDROCK_PII_TIMEOUT_MS`，預設 10 s)；Bedrock 花掉的時間會先從預算扣，再算給 sidecar 的 `timeout_ms`） | **503** `engine_timeout`（`guardrail_timeout`） | 轉送原文，audit 記 `degraded` |
| **AWS 回 `truncated: true`**（它沒看完） | **451** `guardrail_surface_too_large`（violation `pii_detector_truncated`），絕不送出部分遮罩的內容（INV-522-6） | 轉送原文，observe |
| 綁了政策但**沒有任何 active rail** | 轉送——寬面根本不進入，任何長度都不會 451（C-219-41，PR #4766） | 同左 |

> ⚠️ **第一列的「audit 記型別」在 #4766 之前是文件寫了、實作沒做。** `pii_entities_found` 從來沒進過任何 audit event——兩個 emit 點都只帶 `_word_filter_audit_fields`，而 tuple 會被 audit bridge 的 `_filter_extra` 靜默丟棄。所以 rel/prod 今天的 audit **看得到「擋了」、看不到「偵測到什麼」**。#4766 補上 `guardrail_pii_entities_found` / `guardrail_pii_entity_count`（三處宣告：handler + `audit/schema.py` + `PAYLOAD_ALLOWLIST`，漏一處靜默丟棄）。

> **這三個 451 的客戶端訊息（PR #4851，已 merge）**：`guardrail_unredactable_span` / `guardrail_scan_budget_exceeded` / `guardrail_surface_too_large` 在 #4851 之前的 `message` 是 `Request blocked by guardrail: unredactable_span` 這類內插——**把內部 violation type 吐給客戶端**，而且完全不 actionable。#4851 起三者各有 curated 文案（「請求含無法遮罩的個資，請移除或改寫」／「對話太長，時間內掃不完，請縮短或開新對話」／「對話太大，請縮短或開新對話」），機器可讀身分留在 `code` 欄位。**這對 agent client 是有感的**：實測 Claude Code 把 `message` 逐字印給使用者（`API Error: 451 <message>`），所以這串字就是使用者唯一看得到的東西。

> **Bedrock 的五列都不寫進遮罩快取**（C-219-53／54，INV-522-7）。換了憑證也不會命中前一把的結果：有 Bedrock 時，快取指紋含偵測器設定與 `credential_uuid`。2026-10-21 實測過：同一句話換到一把會被 AWS 拒絕的 key，連送三次，三次都重打 AWS、都拿到 403，沒有吃到舊的遮罩結果。
>
> ⚠️ **429 是租戶自己的配額問題，但看起來會像我們壞了。** AWS 的上限是每個帳號、每個 region 1,500 RPM，同帳號的推論也算在內。PII 寬面一個請求通常兩次 Bedrock 呼叫：step 1 一次，其餘沒命中快取的條目批次送，每批最多 40 個 block、50k 字。agent loop 的穩定狀態也是兩次，因為舊條目都命中遮罩快取。超過配額時，該租戶 enforce 的請求會全部 503。導入前先在 shadow 量一下用量。

兩條硬規則：客戶端 request body **不能**覆寫任何 guardrail 行為（C-219-20）；audit／log／response 只帶 entity id 與數量，**原文不得出現**（C-219-21，grep 可驗）。2026-10-21 起 Bedrock 也一樣：audit 只多帶呼叫次數與文字單位（`guardrail_pii_detector_calls`、`guardrail_pii_detector_text_units`），8 筆 trace 都 grep 不到原文。

### 2.6 作者面

| 面 | 端點 | 用途 |
|---|---|---|
| **Console dry-run** | `POST /iam/guardrails/dry-run` | 測**未儲存**的草稿設定。body 帶 draft entities + threshold + 樣本文字。sidecar 不可用 → 503，**絕不回一個沒遮的「成功」**。送出的文字不記 log、不進 audit。 |
| **Runtime preview** | `POST /v1/guardrails/preview` | 用 API key 解析出的**實際生效政策**跑，拒絕任何 override（C-219-20/22）。 |

Console 的遮罩結果會把 token 高亮（兩種尾碼形式都認）。

**Bedrock 在作者面上的樣子**（2026-10-21；#6974、#6977、#6978）：
- **偵測器跟著 Engine 走**：Engine 選 AWS Bedrock 就寫 `bedrock_pii`，其他 Engine 寫 `gliner_pii`。PII 區塊沒有自己的偵測引擎選單。API 與 GitOps 仍可以「content 用 A、PII 用 B」分開寫；Console 載入這種版本時，會在 PII 區塊說明存檔後偵測器會改成什麼。
- **一個共用的 Bedrock 憑證欄位**（content 與 PII 共用）：下拉只列有 region endpoint 的 `bedrock` 憑證，推論用的 key 不會出現。
- **四類「僅限地端比對」標示**：`national_id`、`birthdate`、`gender`、`messaging_id`。
- **資料外送揭露**：「受檢文字會送到 AWS」。
- **content 的限制**：門檻旁標「未校準」，不提供 `self_harm` 並說明原因（Bedrock 沒有這一類）。
- **dry-run 不呼叫 AWS**：Bedrock 草稿只跑 regex（`gliner_entities: []`），回應帶 `semantic_layer_previewed: false`，畫面寫「這次測試不會呼叫 AWS Bedrock」。所以沒有自我介紹句型的姓名在 Bedrock 草稿的 dry-run 裡不會被遮；這是預覽的限制，不是 runtime 的行為。
- **runtime preview（`/v1/guardrails/preview`）會真的呼叫 Bedrock**，也一樣過資料邊界閘（C-219-52）。
- **憑證頁**：
  - Bedrock 憑證有「測試」按鈕（`POST /iam/provider-credentials/{uuid}/test-bedrock-guardrail`），一次測 content 與 PII，含 😀 與 👨‍👩‍👧 的位置；
  - 「適用於」欄逐把判斷，沒帶 region 的 Bedrock key 只列「模型推論」。

### 2.7 檔案地圖

```
apps/guardrails/xparse_guardrail/
  contract/pii_entities.py        12 類 taxonomy（單一來源）
  contract/profile.py             wire profile（含 pii_token_salt）
  contract/word_filters.py        WordFilterTerm + validate_word_filter_terms（寫入邊界規則）+ is_reserved_replacement（⚠ IAM 有第二份）
  word_filters/matcher.py         自訂詞 matcher：normalize / separator_policy / Latin 詞界（SPEC-224 §4.2 normative）
  word_filters/unicode_classes.py 可忽略字元與分隔符兩個 class，**derived 不是列舉**
  contracts/http-api.v1.schema.json   provider 契約（#4807 起 check_request 多選填 `timeout_ms`）
  contract/request.py             GuardrailRequest（#4807 起 `timeout_ms: Optional[int]` = 呼叫端剩餘 deadline）
  engine/gliner_pii/gliner_client.py  GLiNER httpx client；#4807 起 `extract(timeout_ms=)`——合法正整數（≤ 600 s）當 timeout，否則退回 `XPARSE_GLINER_TIMEOUT_MS`（15000，只管無 deadline 的呼叫者）
  engine/gliner_pii/adapter.py    三條 rail 的編排（PR #4728 起在 merge_spans 前接偽陽性過濾；#4807 起把 request.timeout_ms 傳給 gliner_client）
  engine/gliner_pii/false_positive_filter.py   ⬅ PR #4728：語意層 span 字面值後置過濾（四條規則，來源寫在 docstring）
                                  #4765 起加 kill switch XPARSE_PII_FALSE_POSITIVE_FILTER + 實測殘餘 ai/one 寫進 docstring
  config/runtime.schema.json      owner 的 env roster（project.yaml 的 configuration_schema；新增 env 要註冊）
  engine/gliner_pii/mask.py       span merge + token 產生（兩種尾碼形式的唯一產生點）
  engine/gliner_pii/spans.py      PiiSpan
  server/app.py                   POST /v1/guardrails/check

apps/gliner-server/app/main.py    POST /v1/extract（零樣本 NER）

apps/gateway/bustream/gateway/
  guardrail_handler.py            run_input_guardrail（政策解析→抽文字→呼叫→寫回）
                                  #4766 起：寬面 gate 加 active_input_rails、_pii_audit_fields（entity ids 進 audit）
  guardrail_enforcer.py           check_input / _call_guardrail_engine / pii_token_salt；#4806 起 `check_input(timeout_sec=)`；#4807 起 `_build_check_payload(timeout_sec=)` 把它以 `timeout_ms` 放上 wire（無 deadline 的呼叫 body 不變）
  guardrail_detection.py          ADR-448 偵測面 + shadow 觀測（PR #4729 起 iter_detectable_messages 也吐 tool_calls 參數 entry）
                                  #4806 起 = PII rail 整個面的唯一 owner：`LEAF_SEPARATOR` 純文字 parts 葉值級寫回、`write_content` 唯一寫回實作、`last_user_turn_text`／`write_last_user_turn`（step-1 slot）、`responses_input_text`／`write_responses_input`
  guardrail_input_surface.py      ⬅ PR #4729：enforce 逐則掃描／快取／寫回、tool 參數 JSON 葉值改寫、預算與上限 fail-closed
                                  #4806 起：`DEFAULT_SCAN_BUDGET_MS` 30000、`_resolve` 以剩餘預算為 per-call timeout、`_cacheable`（內容類 block 入快取、`is_fail_closed` 不入）
  guardrail_mask_cache.py         逐則遮罩快取（#4729 起 key 含 salt epoch；#4766 起指紋涵蓋整組 rail 設定不只 PII；#4806 起 `MaskResult.violation_type`）
  guardrail_response.py           451 error code 對映（PR #4729 加 guardrail_unredactable_span / _scan_budget_exceeded / _surface_too_large）
  request_text.py                 ⚠ 三個寬度不同的抽文字函式，見 §3.1；#4806 起 PII rail 的 step-1 slot 不再讀它（roster gate 的兩個 extractor 消費者已移除 handler），它只剩 classifier pre-mask 與 admission 估算
  guardrail_policy_adapter.py     IAM spec → gateway policy 形狀（含 word_filters.terms → WordFilterTerm）
  guardrails/word_filters.py      gateway-local WordFilterTerm DTO（不 import guardrails 的 source）
  classifier_verdict_cache.py     ⬅ #4961（C-223-50）：input classifier 的 verdict memo，process singleton 同 `PiiMaskCache`（bind／unbind／`XPARSE_CLASSIFIER_VERDICT_CACHE_IDLE_TTL_SEC`／`_MAX_ENTRIES`，任一為 0 即關）；key 含 text／transcript／pre-mask／classifier 指紋／tenant／stage／mode／judge target；只存 pass／block、degraded 不存
  classifier_handler.py           #4961：`tail_is_tool_shaped` 在 rate bucket 之前 return（log `classifier_skipped` + counter，無 audit）；memo lookup 也在 bucket 之前；`_present_input_evaluation`／`_present_shadow_evaluation` 讓 hit 與 miss 同一條出口；**G3 #4957（待 merge）**：content_filter 的 llm_classifier arm 吃 transcript
  request_text.py                 #4961 加三個非 `extract_*` 前綴的純函式：`chat_tail_is_tool_shaped`／`responses_tail_is_tool_shaped`／`responses_last_user_text`（roster gate 只釘 `extract_*`）
  guardrail_metrics.py            #4961：`xparse_guardrail_classifier_skipped_total{app,stage,reason}`
  guardrail_handler.py            #4961：`_word_filter_scan_text`（chat = `extract_full_request_text` + tool_calls 參數 JSON 解碼葉值；Responses = instructions + user + `function_call` 參數 + `function_call_output`）；`_emit_guardrail_check`／`_blocked` 帶 `surface=` → `guardrail_surface_system_skipped`
  iam_http_client.py              legacy FK 解析點；#4733 起 blocked_keywords CSV → block terms（§3.4）

apps/gateway/bustream/audit/
  schema.py                       AuditRecord 欄位宣告（#4766 加 guardrail_pii_entities_found/_entity_count）
  xparse_bridge.py                PAYLOAD_ALLOWLIST — 沒註冊的欄位被 _filter_extra 靜默丟棄（tuple 一律丟）

apps/iam/xparse_iam/xparse_iam/
  policies/schema.py              GuardrailPiiSpec（作者面 schema）
  authorization/guardrail_policy_merge.py   fold
  api/ninja_api/_guardrail_dry_run.py       dry-run
  guardrails/word_filters.py      is_reserved_replacement 第二份 + 寫入驗證（與 guardrails owner 同批改）

frontend/console-app-refactor/src/app/(main)/(ai-gateway)/policies/_components/policy/policy-content-form.tsx   word_filters 作者面（terms 表格：term / action / replacement）

.github/scripts/guardrail-detection-surface-gate.py   偵測面 roster gate（新）

# ── 2026-10-20／21：AWS Bedrock（ADR-522）──
apps/guardrails/xparse_guardrail/
  contract/request.py             ExternalSpan + external_spans 驗證（≤1000 筆、code point 邊界、entity ∈ pii_entities）→ 422
  contract/profile.py             gliner_entities（None = 同 pii_entities；() = 不呼叫 GLiNER）
  engine/gliner_pii/adapter.py    external spans 在 regex 之後注入（score ≤ 0.99、source "external:bedrock_pii"），回 external_spans_accepted
  engine/gliner_pii/false_positive_filter.py   SEMANTIC_SOURCES = {"gliner", "external:bedrock_pii"}

apps/gateway/bustream/gateway/
  guardrails/bedrock.py           凍結的詞彙：PII_ENTITY_MAPPING、CATEGORY_MAPPING、SEVERITY_CUTOFFS、region／host／path（純資料，無 I/O）
  bedrock_guardrail_arms.py       content arm 與 AWS 呼叫（邊界閘、憑證斷言、強度對應）；HTTP 走跟 Jev 共用的
                                  jev_transport.post_systemone（每把憑證一個只因逾時而跳的斷路器：3 次 → 開 30 s）
  pii_detectors.py                PiiDetectorRuntime：邊界閘、預取、span 轉換；check_input 的 detectors 是必填
  guardrails/engine_configs.py    依 engine 讀設定（沒有新欄位就從舊單值推導 = 今天的行為）

apps/iam/xparse_iam/xparse_iam/
  domain/bedrock_guardrail.py                 BEDROCK_GUARDRAIL_REGIONS（只有 ap-northeast-1）、host 規則
  api/ninja_api/_bedrock_guardrail_probe.py   憑證「測試」按鈕的 probe
  authorization/guardrail_engine_configs.py   依 engine 合併（pii.detectors[]、content_filter.engine_configs[]）
  policies/bedrock_guardrail_content.py       engine id 常數、「指名 Bedrock 就要帶 ref」規則
  management/commands/inventory_guardrail_engine_configs.py   唯讀盤點：依 engine 合併後，哪些單位的實際執行會變

.github/scripts/bedrock-guardrail-parity-gate.py   gateway 常數 × artifact × IAM region 規則
```

### 2.8 同一份政策裡的第二條 rail：word filters（自訂詞，PRD-285 / ADR-389 / SPEC-224）

PII rail 管「有格式或語意特徵、但你列不出來的值」；**word filters 管「你列得出來的字面詞」**——未發表的產品代號、併購案代號、競品名、內部系統名。這些詞 GLiNER 沒有理由攔，所以要管理員自己列。兩條 rail **在同一份 GuardrailPolicy、同一條 fold 鏈、同一次 sidecar 呼叫**裡跑（`profile.word_filter_terms` 跟 `pii_entities` 一起送進 `POST /v1/guardrails/check`）。

**每個詞兩種動作**：`block`（整個請求 451 `word_filter_match`）或 `mask`（把詞換掉再送；`replacement` 自訂，沒給就出 `[CUSTOM_<N>]` token）。

**它是「列清單」型防護，擋不住刻意繞過**（打錯字、同形異字、換講法）——PRD-285 §0 對客戶的四句話，別替它宣稱更多。但比舊的 keyword 清單強在**正規化是 derived 不是列舉**（SPEC-224 §4.2）：casefold（`ß`=`ss`）、全半形、Unicode `Default_Ignorable`（零寬字元、bidi 標記、變體選擇子全部丟掉）、分隔符 class（所有非字母數字）、separator-free pass（`iPhone18Pro` 中 `iPhone 18 Pro`）；Latin 詞界保護（`secret` **不**中 `secretary`）、Han 詞無詞界（`特斯拉` 中 `我覺得特斯拉的車`）；majority-Han 的詞忽略分隔符（`獵鷹 專案` 中 `獵鷹專案`）。

**偵測面 vs 改寫面——2026-09-17 起規格已依實作改寫（SPEC-224 C-224-32 Rev + C-224-32b、PRD-285 U2 Rev、ADR-389 INV-389-4 Rev，PR #4951）**：`block` 面 = 整個 body 含 system、所有輪次、**工具參數的 JSON 解碼葉值與工具輸出**，且不依賴 PII 寬面或 kill switch（#4961 已 merge，真 sidecar probe 證實）；`mask` 面 = 最後一則 + ADR-448 寬面涵蓋的較早 user／assistant／tool 輪次，system 只在 policy 層 `scan_system` 開時改寫。下表是 09-13 那次「規格與現況不同」的實測紀錄，留作歷史：

| | SPEC-224 C-224-32 寫的 | main 實際（2026-09-13 本地實測，enforce + 寬面預設開） |
|---|---|---|
| `block` | 整個 request body 含 system 與所有輪次（`scan_text`） | 同規格：block 詞只在**較早**輪次 → 照樣 **451** ✅ |
| `mask` | **只改最後一則 user 訊息**；較早輪次的詞「不會被遮且已送出」（PRD-285 U2 紅線文案） | **較早 user 輪也被改寫**（system 含 `peter`、前一輪含 `Iphone`，模型只知道「new phone」；log `surface_messages: 3, surface_scanned: 2`）。原因：ADR-448 PR-5 的 `guardrail_input_surface` 對每則訊息呼叫 `check_input(policy, text)`，policy 帶著 word_filter_terms，sidecar 就一起遮了。**這是 PII 寬面的副作用，不是 word filters 自己的設計**——`XPARSE_PII_WIDE_SURFACE_ENFORCE=false` 一關就退回「只改最後一則」。**#4860（Amendment G）起 system 那一半退回規格**：`pii.scan_system` 預設 `false` ⇒ system 不進 per-entry 面 ⇒ system 裡的 mask 詞不再被改寫（**block 不受影響**，走 step 1 的 body-wide `scan_text`）。較早的 **user／assistant／tool** 輪次仍比 C-224-32 寬。 |

→ （已解決）上面那個落差在 2026-09-17 由 PR-D 收掉：SPEC 改成「as built」而不是要實作退回舊文案；剩下的行為變更只有 G1 的 block 面擴到工具參數（#4961）。

**寫入邊界（fail-fast 4xx，`contract/word_filters.py`）**：詞正規化後 ≥ 2 字元；每版 ≤ 200 詞；正規化後不得重複；`block` 不得帶 `replacement`；`replacement` 1–128 字元、無控制字元、**不得假冒 PII token**（`[NAME_1]`、`[phone_3f2a9c17]` 兩種尾碼都擋，C-224-6 / C-219-33——這條在 guardrails 與 IAM 各一份逐字複製，同批改）。**sidecar 在 check 時不再驗**（只驗寫入），所以 gateway 端自己投影出來的詞（#4733 的 legacy CSV）要自己做最短長度與去重。

**wire / audit**：sidecar 回 `violation_type: "word_filters"`；gateway 對客戶端是 **451 + `code: word_filter_match`**（graceful presentation 則 200 拒答——**但 2026-09-15 起 Console 不再提供 `block_presentation` 下拉，graceful 只剩 API 可寫**，SPEC-219 C-219-9a Rev.3 / PR #4845）。audit 只帶 `word_filter_hits / block_hits / mask_hits / term_indexes / noop`（**授權詞的索引，永不帶詞本身**，C-224-41/42；讀取投影對非作者遮蔽詞清單，SPEC-224 §6）。shadow 模式下 block 記 `would_block`、不擋。

**狀態（2026-09-13）**：
- 碼在 **main**：engine matcher、gateway rail、IAM 寫入驗證與 fold、Console 作者面（`policy-content-form.tsx`）都有；本地實測 `peter→my name`、`Iphone→my new phone`、`sexy→451` 三條皆對。
- **rel / prod 沒有這條 rail**（連 DTO 檔都不存在），部署 main 才會有。
- 文件狀態落後於碼：PRD-285 仍 `Draft — design closure`、ADR-389 仍 `Proposed`。要嘛補 Accepted + 驗證紀錄，要嘛在文件標明「已實作、未部署」。
- legacy `blocked_keywords`（舊 FK 平面的 CSV）自 #4733 起投影成這條 rail 的 `block` terms，見 §3.4。

### 2.9 第二個語意偵測器：AWS Bedrock（ADR-522／PRD-375，2026-10-20／21）

**為什麼要有它**（PRD-375 §1）：
- 已經核准用 AWS 的客戶，可以用自己的 AWS 帳號做內容過濾與 PII 語意偵測，費用記在他們自己的帳上。
- 雲端部署的 PII 遮罩不必只靠 air520 那一台地端 GLiNER（§2.2）。

它**不是**比 GLiNER 更好的偵測器。繁中品質沒有評測證據，文案紅線見 §1.2。

**用的是哪一支 API**：`InvokeGuardrailChecks`，`POST {endpoint}/guardrail-checks/invoke`，Bearer key。
- 不用 `ApplyGuardrail`：那支要先在 AWS 建 guardrail resource，繁中還要 Standard tier、強制跨 region。
- `InvokeGuardrailChecks` 不需要任何 resource，只回分數與位置、不攔截，攔不攔由我們決定。
- 實測紀錄：`docs/research/RESEARCH-bedrock-guardrail-checks-probe-2026-10-20.md`。

**什麼時候會跑**：生效政策裡有 `bedrock_pii` 偵測器時（任何一層綁定指名都算，§2.4）。流程見 §2.1 的第二張圖：
- **在 gateway 端呼叫**：sidecar 不持憑證、gateway 不 import guardrails 引擎，所以 AWS 由 gateway 打。
- **位置轉成 span**：先過門檻（`confidenceScore ≥ score_threshold`），再反查 entity id（§2.2 表），只留這個偵測器自己要求的 entity，然後當 `external_spans` 送進原本的 `POST /v1/guardrails/check`。
- **sidecar 驗證後遮罩**：位置越界或 entity 不在選定集合 → 422 → gateway 記 `engine_error`。驗證過的 span 跟 regex span 合併，一次遮罩。
- **只選 Bedrock 時**，sidecar 收到 `gliner_entities: []`，不呼叫 GLiNER。
- **兩個偵測器都在時**（兩層各指名一個），GLiNER 只看 `gliner_pii` 那一組的 entities，結果與 Bedrock 聯集、只遮一次、代號照舊。2026-10-21 實測過：Bedrock 補上了 GLiNER 那組沒選的 `address`。
- **位置以 Unicode code point 計**，跟 Python 字串索引、`PiiSpan.start/end` 同一個單位。實測過 😀 和 👨‍👩‍👧 之後的姓名位置都正確（INV-522-12）。
- **送給 AWS 的 role 一律是 `user`**：PII 偵測跟角色無關。實測過 assistant 歷史和 tool_result 裡的個資都抓得到。

**資料邊界**（C-219-55，改寫 INV-309-2）：
- **出去的是什麼**：PII 原文只在生效政策有 `bedrock_pii` 時才離開部署範圍，出去的是**未遮罩**的條目原文。
- **出去之前**：先跑跟 classifier 同一個 `vendor_call_block_source`（SPEC-223 C-223-55），三條腿：
  - 部署 air gap（`XPARSE_ONPREM_ENFORCE`）；
  - app 的 `profile_type` 不允許雲端（`on_prem`）；
  - key 的 `data_egress=denied`。

  任一成立 → 零連線、503，enforce 與 shadow 都一樣。
- **實測（2026-10-21）**：
  - `on_prem` app：503，audit 記 `pii_detector_boundary_blocked`，PII 檢查 0.14 ms，沒有 `guardrail_pii_detector_calls`。對照組 hybrid app 有呼叫 Bedrock，耗時 541 ms。
  - `data_egress=denied` 的 key：同樣 503、零連線（0.11 ms）。
- ⚠️ **key 的 `execution_boundary` 不是其中一條腿。** 那是 ADR-267 退場、Console 已不能設定的舊軸。實測 `execution_boundary: on_prem` 的 key 在 hybrid app 上，文字照樣送 AWS。2026-10-21 的決定是**不改**：要讓文字留在地端，就把 **app** 設成地端（`profile_type: on_prem`）。不要對客戶說「on_prem 的 key 不會出境」。

**憑證**（ADR-522 §2.2.9；ADR-208 Amendment 12）：
- **怎麼建**：provider `bedrock`、用途「Guardrail」、選 region。IAM 把 region 推導成 `https://bedrock-runtime.<region>.amazonaws.com` 存進 `ProviderCredential.endpoint`；Console 只送 region，不送網址。
- **region**：允許清單只有 `ap-northeast-1`，其他 region 實測過才加。存下 endpoint 之後，這把 key 也被鎖在東京主機。
- **政策怎麼指名**：用 spec 層的 `bedrock_credential_ref`（名稱）指名，PII 與 content 共用一把。
- **gateway 撥號前的斷言**：IAM 投影 `resolved_bedrock_guardrail_credential`，gateway 撥號前再獨立斷言三件事：provider 是 `bedrock`、host 是允許 region 的 `bedrock-runtime`、狀態是 `resolved`。任一不成立 → 零連線、`engine_error`。
- **沒有 region 的推論用 key**，投影狀態是 `no_endpoint`。

**fold**：見 §2.4。PII 依 detector 分組、content 依 engine 分組；`bedrock_credential_ref` 上層釘了，下層換不掉。

**content_filter 那一半**（`bedrock_content_safety`；SPEC-223 C-223-69..76）：

| 項目 | 值 |
|---|---|
| 類別對應 | `hate→HATE`、`sexual→SEXUAL`、`violence→VIOLENCE`、`illegal_activity→MISCONDUCT` |
| 不支援 | `self_harm` 沒有對應類別：只用 Bedrock 判時要求它，寫入時 400（C-223-44）。`INSULTS` 不請求，不硬併進 `hate` |
| 分數 | AWS 只回六階 `severityScore`（0、0.2、0.4、0.6、0.8、1.0）；每個請求的類別每次都會回，0 分也有 |
| 門檻切點 | `low ≥ 0.4`、`medium ≥ 0.6`、`high ≥ 0.8`（`guardrails/bedrock.py` 的 `SEVERITY_CUTOFFS`），Console 標「未校準」。2026-10-22 第一輪 dev set 校準後維持不變：`medium` 最佳；`low` 0.4 漏掉大部分輕度題，改 0.2 會多誤擋無害題；`high` 在 0.8 與 level 2 重疊，改 1.0 會漏擋 11/33 題嚴重題。還不是驗收證據 |
| 判的文字 | 在信任邊界外，所以拿到的是送往 provider 的那份：PII enforce 時是遮罩後的（C-223-45），跟 Jev 一樣 |
| 失敗 | 走 `on_failure`。資料邊界擋下記 `classifier_boundary_blocked` |
| 逾時與斷路器 | content 單次 deadline `XPARSE_BEDROCK_GUARDRAIL_TIMEOUT_MS`（預設 3 s，夾 0.5–8 s）。每把憑證一個斷路器，只因逾時而跳（連續 3 次 → 開 30 秒） |

實測：威脅句 451（violence 0.8、illegal_activity 0.6，門檻 medium）。兩層各用不同 engine 時各用自己的設定（Bedrock 判 4 類、OpenAI 只判 hate）；兩層都用 Bedrock 時只呼叫一次，類別聯集、門檻取最嚴。

**計量**：每次真的打到 AWS 記一筆 count-only 的 ledger fact（producer `guardrail_bedrock`），不在 `CHARGEABLE_PRODUCERS`，不扣 token 配額與預算。AWS 的費用在租戶自己的 AWS 帳上；判決 memo 命中不記。實測 45 筆全是 0 token、0 units。

**發佈狀態**：
- **IAM 寫入**：2026-10-20 起以 pre-release `bedrock_guardrail`（stage DEV）扣住，只有 dev 能寫。
- **畢業**：**#7021（2026-10-21 merge，`915aff71a`）** 把它跟 Jev 一起畢業到所有部署，客戶安裝也看得到選項。
- **還沒驗收**：繁中切點的 held-out 題組（2026-10-22 已跑第一輪 dev set，見 §3.9）、中文姓名偵測率、共用 dev 環境的真 key 端到端。owner 決定先開放。
- **部署順序**：sidecar → gateway → IAM → Console。#7021 的 IAM 和 Console 要一起上。

---

## 3. 沒做的 / 壞的 / 未來要 fix

> 按嚴重度排。每一項都寫清楚「現在會發生什麼」而不只是「還沒做」。

### 3.1 🔴 P0 — 只遮最後一則 user 訊息（#4527，**main 已修、rel/prod 未部署**）

> 這一節有兩張表，**別混著讀**：A 是 rel/prod 今天的行為（PR-5 前），B 是 main 的行為（PR-5 + Amendment G/H）。2026-09-17 之前這裡只有一張表、main 的變化用括號塞在 rel/prod 的列裡，讀者要讀到第三段才知道哪句是哪個環境。

**A. rel/prod 現況（PR-5 前）外洩矩陣**：PII rail 只檢查並改寫**最後一則 user 訊息**，而同一個函式裡的 word-filter rail 已經掃整個 request body。prod 實測（2026-09-09，enforce + 12 類全開）：

| 個資放在哪 | rel/prod 結果 |
|---|---|
| 當前這一則 user 訊息 | ✅ 有遮 |
| system 系統指令 | ❌ 外洩 |
| 較早的 user 訊息 | ❌ 外洩 |
| 較早的 assistant 訊息 | ❌ 外洩 |
| 兩輪前（中間隔一輪乾淨對話） | ❌ 外洩 |
| agent 形狀（最後一則是 tool 輸出） | ❌ 外洩 |
| **拆散在兩則訊息** | ❌ 外洩（每則單看都無害） |
| **個資寫在 tool call 參數裡** | ❌ 外洩，**而且 ADR-448 的寬偵測面（shadow 觀察窗）也看不到** |

**六個位置只有一個受保護。** 而且所有外洩請求的稽核紀錄都記 `guardrail_verdict: "pass"`——依 C-219-14 那等於宣告「什麼都沒偵測到」。**所以「稽核裡沒有 PII 告警」在 rel/prod 不是「沒有 PII 出境」的證據。**

**B. main 現況（ADR-448 PR-5 + Amendment G；Amendment H 已定契約、程式碼待 PR-G2）**：

| 個資放在哪 | chat `/v1/chat/completions`、`/v1/messages` | Responses `/v1/responses`（Codex） |
|---|---|---|
| 當前這一則 user 訊息 | ✅ step 1 遮 | ✅ step 1 遮（全部 user 項一次） |
| system 指令／`instructions` | 依 `scan_system`：**預設不掃**（原樣出境、稽核 `pass`；Am.H 起 audit 帶 `guardrail_surface_system_skipped`）；打開才遮 | 同左 |
| 較早的 user 訊息 | ✅ 寬面逐則遮（快取） | ✅ step 1 已含全部 user 項 |
| 較早的 assistant 訊息 | ✅ 寬面 | ✅ **#4958 起**寬面（`output_text` parts 葉值級） |
| agent 形狀（最後一則是 tool 輸出） | ✅ tool 訊息在寬面上 | ✅ **#4958 起** `function_call_output.output` 在寬面上（真 sidecar probe：main 漏且記 `pass`，分支 `[NAME_…]`／`[NATIONAL_ID_…]` + `modify`） |
| 拆散在兩則訊息 | ⚠️ 逐則各自判，跨則語意仍看不到（設計限制） | 同左 |
| 個資寫在 tool call 參數裡 | ✅ JSON 字串葉值改寫（C-219-38） | ✅ **#4958 起** `function_call.arguments` JSON 葉值改寫 |
| word_filters `block` 詞在 tool 參數裡 | ✅ **#4961 起** `scan_text` 直接含 JSON 解碼葉值，寬面關著也擋（真 sidecar probe：main 漏、分支 451 `word_filter_match`）；09-17 前只靠寬面 per-entry 補、`XPARSE_PII_WIDE_SURFACE_ENFORCE=false` 就漏 | ✅ **#4961 起** `function_call` 參數與 `function_call_output` 進 `scan_text`（C-224-32b） |

Responses 那一欄是 2026-09-16 review 的新發現（§3.8 #9）：Codex 無狀態、每輪重送全歷史，tool 輸出裡的個資在 main 上每輪原樣出境——這是 #4527 在第二個 API 面的同型缺口。

**agent 客戶端結構性必漏**：任何 tool call 都讓 tool 輸出變成最後一則 user 訊息，把使用者貼個資的那一輪擠掉。Claude Code 每一次 tool 呼叫都是這個形狀。

**根因不是某個函式寫錯**：`request_text.py` 有三個寬度遞增的抽文字函式，兩次有人發現窄的太窄就加一個更寬的、只把自己那條 rail 接過去（#3243 給 on_topic、ADR-389 給 word filters），兩次都把 PII rail 留在最窄的那個。

**現在到哪**（ADR-448，九個 PR 已 merge 進 main）：
- ✅ 設計閉環（ADR-448 + SPEC-219 Rev.2 + ADR-296 Amendment A）
- ✅ 內容衍生 token + tenant salt（逐則掃描的先決條件）
- ✅ 偵測面 `iter_detectable_messages` + 遮罩快取 `PiiMaskCache`
- ✅ roster gate（防第三次同型漂移）
- ✅ strict xfail guard（#4533，**仍是 xfail**——洩漏還在，guard 標記著它）
- ✅ **enforce 切換 = gateway PR #4729 已 merge**（2026-09-13 09:33Z；closes #4527）← main 上 P0 已修，**prod 部署後才算關閉**
- ✅ OQ-8 偽陽性過濾 = guardrails PR #4728 已 merge（**部署須先於 #4729**，sidecar image 要重建）
- ⚠️ 契約：#4727 merge 的**只有** ADR-448 Amendment B + SPEC-219 Rev.3 + ADR-296 Amendment B。**Amendment C 與 SPEC-219 Rev.4 從來沒被寫進文件**——#4735 的程式碼與測試五處引用它們，ADR 的修訂表卻停在 B，`INV-448-2` 還寫著「system 訊息明文排除」，與 main 的實際行為直接矛盾。**這一行原本就照著那個漂移寫，本身即是證據。** 補正在 PR #4764（Amendment C §C-0 明記這是事後補正），同批帶 Amendment D 與 Rev.4/Rev.5。
- ✅ **Amendment C 程式碼 = PR #4735 已 merge**（12:56Z；system + Responses `instructions` 納入；#4729 在 fork push 前就被 merge，所以拆成新 PR；真元件矩陣 11/11、persona 探針 `你是「[NAME_47a1b666]」`）
- ✅ **合成真元件驗證（2026-09-13）**：#4729 的 ephemeral gateway × #4728 重建的 sidecar，11 個形狀全符合：B/D/E/F/G/M2 → MASKED（`surface_masked_messages` 1–2）、C 依 D1 維持、H/R1 451；偽陽性 7/8 → **1/8**（剩 `剛才`）；token 五項不變。結果貼在 #4729 comment。
- ✅ **merge 後 review 的四項修復（2026-09-14）**：#4764 契約（Amendment C 補正 + D）／#4765 guardrails FP kill switch／#4766 gateway rail gate + cache 指紋 + entity ids 進 audit。全部已 merge，見 §3.6a
- ✅ **Amendment E = #4806、Amendment F = #4807**（2026-09-14 晚，皆已 merge 並部署 dev）：純文字 parts 陣列進改寫面、per-call timeout 由預算導出、快取只存裁決；deadline 以 `timeout_ms` 傳到 sidecar。見 §2.5／§3.6
- ✅ **Amendment G = #4860 已 merge**（2026-09-15，`f36e826e7`）：`system` 與 Responses `instructions` 改由 `pii.scan_system` 決定、**預設 `false`**。**這一項把本節的結論改了一半**——六個位置裡 system 那格從「已修」變成「租戶自己選，預設不修」。部署序也跟前幾次相反：**IAM + Console 先、gateway 後**（新欄位預設較鬆，要先讓管理員有地方打開）。見 §3.6 與文末 ADR-448 Amendment G
- ✅ **Amendment H 設計閉環（2026-09-17，PR-D）**：D23 Responses 寬面、D24 跳過進 audit、D25 block 面含工具參數、D26 `scan_system` 升 policy 層；同批 ADR-318 Amendment A（classifier 四項）。程式碼待 PR-IAM／G1／G2／G3／G4／Console，見 §3.8
- ⬜ **dev / rel / prod 皆未部署**（#4860 只在 main）

> ⚠️ **#4527 在 2026-09-11 被誤關過一次**：PR #4631 body 寫「this PR does **not** close #4527」，GitHub 關鍵字解析不看否定詞，merge 那一秒自動關閉。2026-09-13 已 reopen 並留言記錄現況與決策。**寫 PR body 提到 issue 時避免 `close/fix/resolve #NNN` 字樣**，改寫成 `see #NNN` 或 `#NNN stays open`。

**觀察窗已跑過**（2026-09-11 本地，真 sidecar + 真 GLiNER，配方見 §5.2）。六種請求形狀、種入已知個資當 ground truth，逐則比對窄 rail 的窗口（`extract_user_text_from_messages` = 最後一則 `role=user`）：

| | 結果 |
|---|---|
| 窗外帶真個資的訊息 | **6 則**（其中 4 則稽核記 `pass`） |
| 其中連寬偵測面也看不到的 | **2 則**（system 一則、tool call 參數一則） |
| 沒種個資卻被偵測的（偽陽性） | **4 則** |

agent loop（6 輪、歷史逐輪增長）的快取行為符合設計：穩定狀態每輪 **2 次 engine call**（新的 tool 結果 + 新的 user 訊息），命中率第 6 輪 **0.82**，單次掃描 ~310 ms。

**兩個新發現**：

1. **`tool_calls[].function.arguments` 不在偵測面上。** `_content_text` 只讀 `content`；agent 把個資寫進 tool call 參數時 `content=None` → 該則 text 為空 → `iter_detectable_messages` 整則跳過。gateway 自己回報的 `surface_messages` 數字印證了這點。**窄 rail 與寬面都看不到，而它照樣送到 provider。**
2. **這個 flag 在任何 compose 檔都沒有 passthrough**（`XPARSE_GUARDRAIL_MODE` 有）。所以「開 flag + 重啟」在現行部署**做不到**，要自己疊一個 override compose 檔。

**下一步**：偽陽性過濾（OQ-8，§3.3）仍然擋在 enforce 切換前面——先拓寬只會把既有的品質缺陷擴散到整段對話。

### 3.2 🔴 輸出側完全沒有（#1508，OPEN）

**現在會發生什麼**：`check_output` 在 V1 是**無條件回 `pass`**（ADR-309 INV-309-9 — 「V1 只遮輸入」）。模型回覆裡的個資——RAG 撈回來的、模型從上下文重述的、工具查詢結果——**一律不遮**。

這是兩層原因疊在一起，別搞混：

1. **引擎層**：V1 把 output rails 整條退場了（ADR-309 PR-7）。就算路徑有覆蓋，`check_output` 也只會回 `pass`。
2. **路徑層**：ADR-303 本來要為輸出側定一份覆蓋矩陣，**被 ADR-309 defer 到 V2**；`streaming/manager_v3_events.py` 的 buffer hooks 保留但休眠（未刪）。

載重限制是 SSE 狀態機：fast-only / large-only 在 finalize 時 delta 早就送出去了，事後遮罩要嘛整段先緩衝（毀掉快路徑的延遲價值）、要嘛送一個 retroactive patch 事件（違反 *no delta after reverse*）。**這是為什麼 #1508 被 defer，不是疏忽。**

未覆蓋的路徑會發 `output_redaction_uncovered` warning（fail-loud，不是靜默）。

**2026-09-07 起有一條半開的路**：`output_redaction_mode`（`stream` | `buffer`，fold buffer-wins）重新回到可寫面並抵達 gateway（SPEC-219 C-219-9a），所以 `/v1/responses` 的 buffer rail 與休眠的 chat hooks **在政策上變得可達**。**2026-09-15 起這條路只剩 API**（C-219-9a **Rev.3** / PR #4845）：Console 的下拉已移除、存檔一律歸一化為 `stream`，理由是 **chat 面的 `buffer` 是零檢查的白 hold**——`manager_v3_events.py` 從不呼叫 classifier，`_emit_buffered_output_and_done` 只呼叫上面那個永遠回 `pass` 的 `check_output`，所以在 chat policy 上開 `buffer` = 扣住全部 token（毀 TTFT）換**零保護**，而 Console 上它跟真的會擋的 `/v1/responses` buffer 長得一模一樣。**要在 `/v1/responses` 開 output 攔截，現在必須用 API 寫 policy。**但 V2 的啟用地圖（ADR-318）只開「非串流 output enforcement + 串流 shadow primitives」，串流的 buffer-enforce hooks 仍休眠，等 shadow 期的延遲／偽陽性數據（V2.1）。

### 3.3 🟠 誤判：`person` 標籤命中代名詞與角色名詞（OQ-8，**過濾器 PR #4728 已 merge**）

**PR-4 前（= rel/prod 的 sidecar image）會發生什麼**：`person_name` 對映到零樣本標籤 `person`，它命中所有佔「人」語意位置的成分：

| 輸入 | 結果 |
|---|---|
| `You are a helpful assistant.` | `[NAME_1] are a helpful assistant.` |
| `你是一個有幫助的助理。` | `[NAME_1]是一個有幫助的助理。` |
| `The assistant is helpful.` | `[NAME_1] is helpful.` |
| `這是一個有幫助的助理。` | 未改（正確） |

8 句寫實 system prompt **8 句全部**被判定要改寫。**這在今天的生產路徑上就已經在發生**——任何以指令句式書寫的 user 訊息（「You must …」）今天就會被誤遮。同批測試裡，一段要求列出「姓名 / Email」欄位的指令，其**指令文字本身**的「姓名」「Email」也被當成實體遮掉。

**調高門檻不是解**：0.5 → 偽陽性 7/8、召回 18/18；0.9 → 偽陽性 0/8、召回 16/18。偽陽性歸零要付 **11% 召回**。兩種錯誤代價不對稱——偽陽性弄壞一句指令（可見、可復原），偽陰性讓個資外洩（不可見，而且正是這條 rail 存在的唯一理由）。

**方向已知、未驗證**：對偵測到的 span **字面值**做後置過濾。代名詞與角色名詞是封閉、可列舉的類別，且與 18 個真名完全不相交，理論上零召回代價。但清單必須來自有原則的來源（各語言代名詞表 + 角色名詞詞庫），從 8 句樣本手工歸納是過擬合。

**2026-09-11 補測，三件讓這一項更難的事**（對真 sidecar，12 類全開）：

| 輸入 | 結果 |
|---|---|
| `好的，我記住了。` | `好的，[NAME_1]記住了。`（代名詞「我」） |
| `剛才那件事，回覆 ok 就好。` | `[NAME_1]那件事⋯`（副詞「剛才」） |
| `他的身分證是 A123456789` | `[NAME_1]的身分證是 [NATIONAL_ID_1]`（代名詞「他」，ID 是真陽性） |
| `{"status": "ok", "record_id": 8821}` | `{"status": "ok", "record_id": [NATIONAL_ID_1]}` |

1. **偽陽性不只出現在 system prompt。** 一般對話的代名詞、副詞、角色名詞都會中。
2. **tool 結果裡的裸數字會被判成身分證。** agent 流量裡到處都是 `record_id` / `order_id` 這種欄位——**這是偵測面拓寬後才會大量出現的類別，今天的窄 rail 看不到它**。
3. **偽陽性率取決於勾了哪幾類，也取決於清單順序。** `剛才`、`客戶` 只在 12 類全開時才誤判；同一個集合換順序會翻轉門檻邊緣的判定（§2.4）。→ **shadow 量到的偽陽性率不可跨租戶轉用**，因為每個租戶勾的不一樣。

**2026-09-13 決定：與 enforce 切換同批**（Peter；ADR-448 Amendment B D11），guardrails 先部署。PR #4728 的過濾器只作用**語意層** span 的正規化字面值，四條規則各有可列舉來源：① 代名詞（封閉詞類 zh/en/ja）② chat 參與者角色名詞（system/user/assistant/tool/agent/客戶/助理…，含純角色名詞複合詞如 `system administrator`）③ taxonomy 標籤字不是實例（`姓名`/`Email`/`電話`/`person`/`phone number`…，由 `pii_entities.py` 導出 + 短形如 `信箱`/`手機`/`卡號`）④ `national id number` 語意 span 壓縮後 < 8 字元不合理。**決定性層（regex，score 1.0）永不過濾。**

**真元件結果（2026-09-13，真 GLiNER）**：12 句無個資樣本偽陽性 **11/12 → 1/12**（剩 `剛才`，副詞，已知殘餘）；20 句真名語料召回 **20/20 不降**。合成測（#4729 gateway × #4728 sidecar）上面那 8 句從 7/8 誤遮降到 1/8。**上面兩張「現況」表在 #4728 部署後只剩 `剛才` 那一列成立。**

仍要注意：偽陽性率隨 entity 集合與清單順序變動（§2.4），所以租戶 A 量到的數字不能直接套到租戶 B。

**過濾器自己的召回殘餘（#4741 → PR #4765）**：docstring 原本宣稱「列封閉詞類 by construction 零召回代價——沒有人叫『你』『assistant』『姓名』」。這句話對兩個條目不成立：`_ROLE_NOUNS_EN` 的 `ai`（收來對應縮寫「AI」，但 `Ai` 是日文女性名 愛／あい 的羅馬拼寫）與 `_PRONOUNS_EN` 的 `one`。span 的正規化值**剛好等於**這兩個字時會被丟，而 `person_name` 沒有決定性層兜底——被丟的 span 直接出境。

**決定保留兩者**（Peter 2026-09-14，ADR-448 D17）：觸發條件是名字單獨出現，其餘 21 個實測名字（`愛`、`Kim`、`Hunter`、`Baker`、`Mei`、`Ken`、`Jun`、`Rin`、`Ren`、`Sora`、`An`、`Ann`、`陳建宏`、`王大明`⋯）全部保留；而拿掉 `ai` 會讓**使用者真的會寫的 `AI`** 回到偽陽性池，代價更大更常見。改的是誠實度：docstring 改列實測殘餘，並由 `test_the_measured_recall_residue_is_pinned` 釘住——以後有人「順手」清 vocab 會變紅，被導回這個決定而不是那份清單。

同批補上 **kill switch `XPARSE_PII_FALSE_POSITIVE_FILTER`**（預設 `true`、重啟生效）。這是 PII rail 裡**唯一會減少偵測**的旋鈕，卻是唯一沒有退路的——其他四個（`XPARSE_PII_WIDE_SURFACE_ENFORCE`、`XPARSE_PII_SCAN_BUDGET_MS`、`XPARSE_PII_DETECTION_SURFACE_MAX_MESSAGES`、`XPARSE_PII_TOKEN_SALT_EPOCH`）都有。

### 3.4 🟠 `blocked_keywords` 接了但沒有人執行（#4528，**main 已修 #4733、rel/prod 未部署**）

**PR #4733 前（= rel/prod 現況）會發生什麼**：Console 顯示、IAM 驗證儲存並投影上 wire、Gateway 反序列化——然後**沒有任何程式碼讀它**。ADR-309 退場關鍵字 rail 時只拆了執行端，authoring／storage／wire／display 四端都還在。

**一個 tenant admin 看著 enforce 政策上一串「Blocked Keywords」，會合理地認為那些詞被擋了。它們沒有。**

（注意區分：**word filters** 是另一條真的在跑的 rail（ADR-389）。壞掉的是 legacy 的 `blocked_keywords` 欄位。）

**修法（#4733，2026-09-13 merged）**：在 gateway 的 `IAMHttpClient._parse_guardrail_policy` 把 legacy CSV 投影成 `block` 動作的 word-filter terms（與 ADR-309 D8 把 `pii_redaction_enabled` 映成全 entity mask 同一個位置）。ADR-309 §2.6a Amendment B、SPEC-224 C-224-54。

> ⚠️ **部署當天會變行為**：prod `futurenest/rd_group_guardrail`（enforce）的 legacy 清單 `api_key, apikey, secret, password, private_key, access_token, client_secret, BEGIN RSA` 會開始真的 451 `word_filter_match`（whole-word、casefold）——之前只是顯示。**先告知該 group owner。** 另四列是 shadow 只記 audit。sidecar 真正的 `violation_type` 是 `word_filters`，`word_filter_match` 是 gateway 的 error code，寫 fake 時別搞混。

### 3.5 🟡 容量：偵測面一拓寬就是 20 倍

對 prod sidecar 實測：延遲對字元數**近似線性**（約 0.43 ms/字元），所以成本由**推論量**決定，不是往返次數。

| 策略（16 則、13,400 字元的真實 Claude Code 請求） | 耗時 |
|---|---|
| 現況（只掃最後一則，400 字元） | **313 ms** |
| 逐則序列 | 7,067 ms |
| 併發上限 8 | 5,789 ms（只省 18%） |

**併發只換到 18% → 遠端那台單節點 GLiNER 是吞吐受限。**

遮罩快取讓**穩定狀態**回到今天的量級——**2026-09-11 在真實路徑上量到**（原型數字是 8 輪 loop、36 次查詢 → 8 次引擎呼叫、命中 77.8%）：6 輪 agent loop、歷史逐輪增長，穩定狀態每輪 **2 次 engine call**（新的 tool 結果 + 新的 user 訊息），命中率隨輪數爬到 **0.82**，單次掃描 ~310 ms。

> ⚠️ 量這個數字時注意：**快取活在 gateway process 裡、跨 run 不會清**。第一次測拿到命中率 1.0，是因為上一輪跑過的樣板字串被直接命中——每一則生成訊息都要帶 run nonce，而且要重啟 gateway 才算冷測。

但**冷啟動救不了**：使用者第一次貼 13k 字元的長 prompt，仍是單次 5–7 秒。

**已決（Peter 2026-09-13，已實作於 PR #4729）**：這一輪**不擴** GLiNER 容量。enforce 給每請求一個掃描時間預算，超過預算、或超過 `XPARSE_PII_DETECTION_SURFACE_MAX_MESSAGES`（今天 24，shadow 只在 log 標 `truncated`）→ **451 + 專屬錯誤碼**，不得靜默只掃前段。容量擴充另開 issue 排程。

> ⚠️ **這個 ceiling 原本連「沒開任何 rail 的政策」都擋**（#4738，P1，修在 PR #4766）。`run_input_guardrail` 進寬面的條件只有 「上一步沒 block」+ kill switch，沒問政策到底有沒有 rail；而 ceiling 在任何 rail 判定之前就 return block。所以一個 `pii.enabled=false` 且無 word filter 的政策，對話超過 24 條目就開始 451——為一個從來不會跑的偵測器。真元件 probe：`rails=() msgs=25 engine_calls=0 → HTTP 451`。**24 條目以下也不是無害的**：每個 entry 仍各發一次 `check_input`（短路不打網路，但 `surface_engine_calls` 已計數）並把 no-op 結果寫進 mask cache——後者正是 #4742 最糟糕那一格的成因。
>
> 順帶：**`surface_engine_calls` 不等於 sidecar 呼叫數**，拿它當容量基準會高估（#4739 要量分布時注意）。

### 3.6 🟡 其他已知缺口

| 缺口 | 現在會發生什麼 |
|---|---|
| **Console 預覽與 shadow 共用同一個盲點** | 預覽頁與 shadow 都只看最後一則（而且在 PR #4631 之前，預覽連 salt 都沒送，顯示的 token 形式與 runtime 不一致——見 §2.3）。租戶貼多輪對話樣本想驗證政策，**預覽在結構上不可能揭露 §3.1 的缺陷**；用 shadow 評估「切 enforce 會攔多少」會得到系統性偏低的數字，然後帶著錯誤的信心切換。「先 shadow 觀察再開 enforce」這道安全網對這條缺陷是空的。 |
| **兩個端點行為相反**（OQ-4） | 同一份政策、同一批個資，`/v1/chat/completions` 靜默外洩，`/v1/responses` 直接 451 fail-closed。不是環境差異，是兩條抽取路徑的必然結果。**已決（Peter 2026-09-13）：往 fail-closed 統一。** 偵測到但改寫不了 → 451 + `unredactable_span`，絕不記 `pass`（INV-448-4）；chat 向 responses 靠，不是反過來。前提是改寫面先擴到所有 `str` content 的 user/assistant/tool 訊息，~~451 只留給 list content 與 `tool_calls[].function.arguments`~~ → **Amendment E 收窄**：451 只留給含非文字 part 的 list content 與壞 JSON 的參數，純文字 parts 陣列可改寫。 |
| **~~tool call 參數不在偵測面上~~（PR #4729 已納入）** | PR-5 前（rel/prod 現況）：`_content_text` 只讀 `content`，`content=None` + 個資在 `tool_calls[].function.arguments` 時整則被跳過。**已決（Peter 2026-09-13，C-219-38）**：納入偵測與改寫面，解析 JSON 後只對字串葉值一次呼叫偵測、拆回、`json.dumps(ensure_ascii=False)` 寫回；壞 JSON → `unredactable_span` 451。合成測形狀 E `surface_masked_messages=2`（user 訊息 + tool 參數）。 |
| **~~tool 內容本身該不該被判定~~（已決）** | tool 結果（`role=tool`，str content）逐則偵測並改寫，與 user/assistant 同等；tool 結果裸數字被判身分證的問題由 #4728 規則④（< 8 字元不合理）處理。 |
| **~~多模態 content 一律 fail-closed 451~~（Amendment E 收窄，PR #4806，2026-09-14）** | Amendment E 前：chat completions 的**任何** list content 寫不回去就擋掉——包括**純文字 parts 陣列**，也就是 OpenAI SDK／AI SDK 對多 part user turn 的送法。ADR-448 B-2 與本列原文都寫「只有夾圖才會落到這裡」，2026-09-14 OpenCode 一句 `hi` 就 451 把這個前提戳破（`/v1/messages` 沒事只因翻譯層先把純文字 block 摺成 str）。同一個請求還會拿到**兩種** 451：step 1 寫回失敗是 `input_blocked`、寬面是 `guardrail_unredactable_span`——因為寫回有兩份實作。Amendment E 起純文字 parts 以葉值分隔符一次呼叫、拆回同數葉值才逐 part 寫回（chat `messages` 全角色與 Responses `input` user 項皆然；`guardrail_detection.write_content` 是唯一實作），451 只留給含 image／audio／document part 的 list 與壞 JSON 參數。同批：per-call timeout 由預算導出、預算 30 s；快取存內容類 block、不存 timeout。真元件矩陣：parts 陣列 200 且模型回遮罩 token、夾圖 451、15k 字 system prompt 走預設預算 200（單次呼叫 10 s）。 |
| **~~salt epoch 完全無效~~（PR #4631 已修）** | knob 轉了不產生任何效果——`key=salt[:32]` 把 epoch 截掉了。**在 #4631 merge 前，`XPARSE_PII_TOKEN_SALT_EPOCH` 是一個看起來完整、實際上死的旋鈕**；ADR-448 §5.2 把它列為長期化名串接的唯一緩解手段。兩側測試各測一半、沒人測合成（gateway 斷言 salt 字串不同、從不導出化名；guardrails 用 13 字元的合成 salt，碰不到 key 上限）。 |
| **~~salt epoch 未進 cache key~~（PR #4729 已併入）** | PR-5 前（rel/prod 現況）：INV-448-8 要求涵蓋，`mask_cache_key` 未涵蓋。**今天觸發不到**：epoch 以 `os.getenv` 讀取、runtime 沒有人寫 `os.environ`，所以只能經重啟改變，而重啟會清空 in-process 快取。這是真的保證但是間接的——**任何人把 epoch 做成可熱重載，它就不成立了**。正式收斂留在 PR-5。 |
| **salt 輪換週期未量測** | 有 knob（#4631 之後才真的會動），沒有排程。週期太短會在對話中途換代號，那正是 per-conversation salt 被否決的原因。 |
| **Console `PII_ENTITY_OPTIONS` 是手抄鏡像** | 後端 taxonomy 的手抄副本，**沒有任何 CI gate 釘住**；唯一引用它的 unit test 拿它自己當預期值，是自我參照。同一份 roster 散在三個檔（`pii_entities.py` / gliner-server `DEFAULT_LABELS` / SPEC-219 表格）。 |
| **OQ-8b：system prompt 殘餘偽陽性** | 職業名詞（可列舉，是 OQ-8 規則②的延伸）、產品／品牌名（需 tenant allowlist 或大寫專名判斷）、年齡區間（`AGE` 標籤對「25-34 歲」這類族群描述誤判）。三類都會改到指令本身。 |
| **shadow 觀察窗對 enforce 租戶收不到數據** | 偵測面觀測只接在 `_run_shadow_input_check`（`guardrail_handler.py:797`）。2026-09-13 本地實測：enforce 政策 + `XPARSE_PII_DETECTION_SURFACE_SHADOW=true`，12 個請求 **0 筆** `detection_surface_observed`。這是 D2 的結構性後果——最需要量偽陽性率的族群（已開 enforce 的租戶）正好量不到。要量得先把政策切回 shadow，或讓觀測在 enforce 路徑上 observe-only 跑。 |
| **`system` 指令是否進偵測面 = 政策決定（Amendment C 推翻 D1 給了能力；Amendment G / #4860 把預設改回不掃；Amendment H D26 把旋鈕升到 policy 層 `scan_system`——IAM #4959 已 merge、寫 top-level 並鏡像 `pii.scan_system`；gateway 讀 OR 在 #4957、Console 開關搬到「保護設定」在 #4954，皆待 merge）** | Peter 2026-09-13 同日改變決定：skill 指令、RAG、persona 名冊注入 system 越來越多，D1 缺口不可接受。含過濾器 sidecar 重測 12 句 system prompt：純指令不再誤改；殘餘 **3/5** 無個資句仍中（產品名 `Claude Code`、職業名詞 `法務助理／律師`、年齡區間 `25-34 歲` → **OQ-8b**）；**persona 名字與客服信箱／電話會被遮成代號**（`你是「[NAME_x]」`），這是明碼代價；RAG 名冊正確遮住。12 類全部、同對話規則、改寫不了 451。Responses `instructions` 同等納入。**Amendment G（2026-09-15）**：上面那個代價對「system = RAG 注入」的租戶划算、對「system = 產品文案」的租戶不划算，而平台分不出兩者 ⇒ 改成 `pii.scan_system`（fold OR、**預設 `false`**）。能力保留、預設翻面；未表態的政策回到本表 §3.1 的 ❌，且稽核仍記 `pass`——只有 `surface_system_skipped` 看得出來是「沒掃」而不是「沒找到」。 |
| ~~**word filters `mask` 改寫面文案過時**~~（§2.8；**2026-09-17 PR #4951 已解決**：SPEC-224 C-224-32 / PRD-285 U2 / INV-389-4 改為 as built） | SPEC-224 C-224-32 與 PRD-285 U2 說 `mask` 只改最後一則 user 訊息；main 上 ADR-448 寬面讓每則訊息都經 `check_input(policy)`，mask 詞在 system／較早輪次也會被改寫（本地實測）。行為比文案**嚴**，不是外洩，但 SPEC 要修訂、`XPARSE_PII_WIDE_SURFACE_ENFORCE=false` 會同時退掉這個副作用。 |
| **451 讓 Codex 把一次 PII block 變成 6 次寬面掃描**（#4854，OPEN） | 本文三個 fail-closed 碼都回 **451**。2026-09-15 實測（`docs/research/RESEARCH-agent-client-block-status-retry-behaviour-2026-09-15.md`）：**Codex 的 terminal 狀態集合只有 `{400, 429}`**，451 / 403 / 422 一律吃 5 次指數退避重試，所以一次被擋的 Codex 請求 = **6 次完整請求 = 6 次寬面掃描 + 6 筆 audit**。這直接乘上 §3.5 的 20 倍容量問題：dev 上一則長 system prompt 首輪要 40–60 s，6 次就是四分鐘 GLiNER 時間，換來同一個拒絕。Claude Code 與 OpenCode 不受影響（兩種狀態碼行為相同）。**要讓 Codex 停手只有「content block 回 400」一條路**，但 451 是 SPEC-106 §3.3 的 as-built 契約（83 處測試斷言、40 份文件），屬 PRD/ADR 拍板範圍。**當下決定：維持 451**，追蹤票 #4854。順帶已修：Anthropic 面 451 因無對映列落 `api_error`（可重試類），PR #4851 補 `invalid_request_error`。 |
| **PRD-285 / ADR-389 狀態落後於碼** | 碼在 main、本地驗過，文件仍 `Draft` / `Proposed`；rel/prod 尚無此 rail。 |
| **~~ADR-448 沒有 Amendment C~~（PR #4764 已補）** | #4735 把 system 納入偵測面並在三處原始碼、五處測試引用「ADR-448 Amendment C / C-219-35 Rev.4」，但 ADR 的修訂表只到 B、SPEC-219 沒有 Rev.4、**INV-448-2 還寫著「system 訊息明文排除」**——invariant 表與 main 行為直接矛盾了一天。沒有 gate 出聲：roster gate 管的是 `request_text.py` 的 extractor × consumer 對映，不是 `DETECTABLE_ROLES` 的成員。 |

### 3.6a merge 後 review 的六張 issue（June，2026-09-13）

| # | 級別 | 判定 | 處置 |
|---|---|---|---|
| #4738 | P1 | ✅ 成立 | 寬面 enforce 加 `active_input_rails(policy)` 閘（**any rail**，不是 pii-only——per-entry `check_input` 是 `tool_calls[].function.arguments` 上唯一的 word-filter 評估）。PR #4766 |
| #4739 | P2 | ⚠️ 問題成立，論證的數字錯 | ceiling 數「條目」、budget 實質數「字元」（0.43 ms/char），兩個單位沒共同校準——這點對。但「24 條目 ≈ 10.6 s」是把 char-linear 當 message-linear 外推（7.1 s 是 16 則 **13,400 字元**）；真正的 dead zone 邊界是總字元 > ~18.6k。**保持 open**，等 rel 實測分布 |
| #4740 | P2 | ❌ 不成立 | `apps/guardrails` 走 owner capsule 不是逐檔登記：`guardrails-envelope` → `capsule-run --project guardrails` → `project.py::test` → `pytest xparse_guardrail/tests`（整棵樹）。#4728 的 job log 有 `command=test status=succeeded duration_seconds=1.811`，本地重現 441 passed in 1.84s，seeded regression 變紅。已附證據 closed |
| #4741 | P3 | ✅ 成立 | `Ai`（愛/あい）與 `One` 被當 role_noun/pronoun 丟掉。**決定保留**——`AI` 是使用者真的會寫的字，它回到偽陽性池的代價大於這兩個罕見名字的偽陰性風險；改為誠實 docstring + kill switch `XPARSE_PII_FALSE_POSITIVE_FILTER`。PR #4765 |
| #4742 | P3 | ✅ 成立，範圍更廣 | 不只「同 PII profile 不同 word filter」：**零 rail 政策與 word-filter-only 政策也共用 key**（`Z key == W key`），而零 rail 政策會主動把 `pass` 寫進 cache。指紋改為涵蓋整組 rail 設定。PR #4766 |
| #4743 | P3 | ✅ 成立，根因更深 | 不只 block 路徑丟掉——`pii_entities_found` **從來沒進過任何 audit event**（兩個 emit 點都只帶 `_word_filter_audit_fields`，而 tuple 會被 `_filter_extra` 靜默丟棄）。修完整鏈：block 帶 ids + `_pii_audit_fields` + `PAYLOAD_ALLOWLIST` + `audit/schema.py` 三處宣告。PR #4766 |

### 3.7 建議優先序

> **歷史（2026-09-13 的拍板，數字已過時：預算 8 s 已改 30 s、system 決策已翻兩次）——留作決策紀錄，不是現況**：① OQ-8 過濾與 enforce 切換**同批**（guardrails PR-4 先部署）② OQ-4 統一 fail-closed 451（`unredactable_span`，推翻 ADR-296 A-2「只標不擋」）③ 容量走 8 s 掃描預算 + 24 則上限皆 451、不擴 GLiNER ④ `tool_calls[].function.arguments` 納入偵測與改寫面、JSON 字串葉值級 ⑤ kill switch `XPARSE_PII_WIDE_SURFACE_ENFORCE`。~~system 仍明文排除（D1）~~ ← **同一天稍晚就被 Amendment C 推翻**（#4735），這句只反映 #4727 當下。gateway PR-5 關閉 #4527。**仍未決**：shadow flag 的 compose passthrough；enforce 租戶的觀察窗（D2 盲區，見 §3.6）。


1. ~~review + merge~~ **全部已 merge**（#4727 / #4728 / #4729 / #4735 / #4733，2026-09-13）。
   **2026-09-14 追加三個 PR**（merge 序：契約 → sidecar → gateway）：**#4764** ADR-448 Amendment C（補正）+ D + SPEC-219 Rev.4/Rev.5 ·
   **#4765** guardrails FP 過濾器 kill switch + 誠實 docstring · **#4766** gateway rail gate + cache 指紋 + entity ids 進 audit。
   部署序不變：sidecar image 先於 gateway。
   **2026-09-14 晚再追加 PR #4806（ADR-448 Amendment E，gateway only；已 merge、dev 已 pull + recreate、三個繞法已撤）**：⚠️ 撤掉後冒出**第四個缺陷**：sidecar→GLiNER 的 15 s timeout（見 §2.5 預算列），dev 暫用 override 檔拉到 30 s，正解 = **PR #4807**（Amendment F，deadline 隨請求下傳；merge 後 rebuild sidecar image、刪 override）。純文字 parts 陣列 451、per-call timeout 5 s < 8 s 預算、block／timeout 不進 cache——OpenCode 一句 `hi` 就被擋的三個缺陷同批修（`docs/issues/agent_llmproxy.md`）。merge 後 dev 樹 pull + recreate gateway，本地 `.env` 的 `XPARSE_GUARDRAIL_TIMEOUT_SEC=25`／`XPARSE_PII_SCAN_BUDGET_MS=40000` 兩個繞法可刪，OpenCode 的 `xparse-local-claude`（anthropic provider 繞法）可撤回 `xparse-local`。
2. **部署（現在的主線）**：sidecar image（#4728 **+ #4765**）**先於** gateway（#4729 + #4735 + #4733 **+ #4766**）。部署前三件要先跟客戶／group owner 講：① ~~system prompt 裡的真人名 persona 會變 `[NAME_x]`（#4735）~~ → **Amendment G / #4860 之後不必再講這條**：未表態的政策預設**不掃** system，persona 名字不動；要講的反而是相反那句——**要保護 system 內容的租戶得自己把「掃描系統指令」打開**，而且 IAM/Console 必須**先於** gateway 部署，他們才有地方打開；② prod `rd_group_guardrail` 的 legacy `blocked_keywords` 會開始真的 451（#4733，見 §3.4）；③ 多輪對話裡歷史訊息的個資會開始被遮，模型回覆可能改用代號稱呼。退路 `XPARSE_PII_WIDE_SURFACE_ENFORCE=false` + 重啟（只退 PII 面，不退 #4733）。部署後用 §5.2 的矩陣腳本加 `--post-pr5` 驗。
3. **OQ-8b**：system prompt 殘餘偽陽性（職業名詞／產品名／年齡區間，§3.6），過濾器下一批來源。
4. **觀察窗盲區**：shadow 偵測面觀測在 enforce 租戶收不到事件（§3.6）；shadow flag 沒有顯式 `environment:` 條目，但 gateway 的 `env_file: .env` 會把整個 root `.env` 帶進容器，所以寫進 `.env` + recreate 即可（早先「沒 passthrough」的判斷是看錯：只 grep 了變數名）。要量 prod 偽陽性率得先解這兩件。
5. **ceiling × budget 校準（#4739，open）**：ceiling 數「條目」、budget 實質數「字元」（0.43 ms/char），兩個 knob 沒共同校準，誰先觸發取決於流量形狀而非設計。要 rel 的實測分布才能重推——量 `input_check` 的 `surface_messages` 與 `surface_duration_ms`，**別用 `surface_engine_calls`**（它把短路、沒出網路的呼叫也算進去）。
6. **#1508 輸出側**——`output_redaction_mode=buffer` 的 opt-in 路徑（**2026-09-15 起 Console 不再提供這個開關，只剩 API 可寫**；chat 面的 buffer 仍是零檢查的白 hold，見 §3.2）。
7. **salt 輪換週期**與 **Console `PII_ENTITY_OPTIONS` gate**（§3.6）。

---

### 3.8 2026-09-16 掃描範圍 review：九項發現與處置（對照 LiteLLM／Portkey）

把三條 input rail 的範圍與 LiteLLM（2026-09-14 checkout，18 個 guardrail hook）、Portkey gateway（43 個 plugin）逐一對照。先講對照結論，再列九項。

**三家「掃 system？掃歷史？只看當前？」對照**：

| | PII | Content / safety | Word / keyword | On-topic |
|---|---|---|---|---|
| **Xparse main（review 當時）** | 全對話 user／assistant／tool／tool_calls 參數；`system` 由 `pii.scan_system` 決定，預設不掃；**Responses 面只掃 instructions + user 項** | chat 面只看最後一則 user；Responses 面卻是所有 user 項串接 | `block` 掃整個 body 含 system（但不含 tool 參數）；`mask` 跟著 PII 寬面 | user + assistant 全部，排除 system 與 tool |
| **LiteLLM** | Presidio 逐則掃、不看角色（含 system、tool） | Bedrock／Lakera v2／內建 content_filter 預設全角色含 system；OpenAI moderation／Model Armor／Javelin 只看最後一則 user | `hide_secrets` 全訊息；內建 content_filter 連 `tool_calls` 參數也掃 | 沒有這條 rail |
| **Portkey** | 只看最後一則 message 的 content、不分角色；Anthropic top-level `system` 永遠不進 | 同左（43 個 plugin 走 `getText`）；Lasso／Aporia／Mistral 例外送整個 `messages` | 同左 | Azure Prompt Shield 反而拿 system 當 `userPrompt` |

LiteLLM 把範圍做成四顆 rail 通用旋鈕（`skip_system_message_in_guardrail`／`skip_tool_message_in_guardrail`／`experimental_use_latest_role_message_only`／`only_scan_new_messages`）；Portkey 只有 Qualifire 有 `ignoreRequestHistory`。Xparse 的 PII 面已比 Portkey 寬得多、接近 LiteLLM 預設；差的是 classifier 那兩條與 Responses 面。Bedrock 的 input 掃描**不信任 caller 的角色標籤**（防「放進 system 就不被查」）——`scan_system=false` 正是這個反向風險，Am.H 記進 ADR-448 §5.2。

**九項與處置**（Peter 2026-09-16 拍板；契約 = PR-D 已寫，程式碼分六個 PR）：

| # | 問題 | 拍板 | 落點 |
|---|---|---|---|
| 1 | classifier 在 agent 迴圈每輪重判同一句舊 user 訊息、無快取（每次 tool 迭代 = 1～2 次判官 LLM 呼叫，卡 pre-admission、計租戶預算） | 跳過 **tool 形狀**結尾（純 assistant prefill 照判，防 prefill bypass）+ verdict memo（hit 不消耗 rate bucket、不計 token、degraded 不存） | ADR-318 Am.A；SPEC-223 C-223-49/50；PR-G1 |
| 2 | content_filter chat 面只看最後一則 user，Responses 面是所有 user 項串接 | 收斂成最後一則 user item（pre-mask 同步收窄） | SPEC-223 C-223-41 Rev；PR-G1 |
| 3 | tool 結果／tool_calls 參數不在任何 classifier 面上 | `content_filter.scan_tool_results` 開關，預設關；開了每個 tool 結果各判一次、memo 去重、audit `classifier_target` | SPEC-223 C-223-51；PR-IAM + PR-G4 + Console |
| 4 | `pii.scan_system` 一顆 PII 旋鈕同時管 word_filters mask 的 system 面 | 升為 policy 層 `scan_system`（fold OR）；`pii.scan_system` 讀相容一版、IAM 鏡像 | ADR-448 Am.H D26；PR-IAM + PR-G3 + Console |
| 5 | `scan_system=false` 時 audit 分不出「沒掃」與「沒找到」（`surface_system_skipped` 只在 log） | 進 audit 欄位 `guardrail_surface_system_skipped`（推翻 Am.G「不加」） | ADR-448 Am.H D24；PR-G1 |
| 6 | word_filters `block` 的 `scan_text` 只走 `content`，tool 參數靠 PII 寬面補、kill switch 一關就漏；raw JSON 是 `\uXXXX` 逃逸、中文詞比不到 | `scan_text` 在 handler 組裝、含 JSON 解碼葉值；Responses 含 `function_call` 參數與 `function_call_output` | ADR-448 Am.H D25；SPEC-224 C-224-32 Rev + 32b；PR-G1 |
| 7 | content_filter 沒有上下文（多輪拆分看不到） | `llm_classifier` arm 吃 user/assistant transcript、只判最後一則 USER；provider-API arm 維持單句；output stage 不動 | SPEC-223 C-223-41 Rev；PR-G3 |
| 8 | 文件過時：SPEC-223 C-223-41「PII 只改最後一則」、SPEC-224 C-224-32 mask 面、PRD-285 Draft／ADR-389 Proposed、本文 §3.1 混寫 | 全部修正（PR-D）；本文 §3.1 拆成兩張表 | PR-D |
| 9 | **新發現**：Responses 面 PII 寬面只掃 `instructions` + user 項；assistant 項、`function_call.arguments`、`function_call_output` 不掃（Codex tool 輸出個資每輪原樣出境）；另 `_responses_input_slots` 把 role-less `function_call_output` 當 user 項、modify 時寫 `content=""` | Responses 寬面涵蓋三類、分類先看 `type`、`reasoning`／`encrypted_content` 永不碰；共用 chat 的 cache／budget／ceiling | ADR-448 Am.H D23；SPEC-219 C-219-48；PR-G2 |

**PR 狀態（2026-09-17 12:xx）**：六張全部 merge——#4951 docs（`b7ceac5c6`）· #4959 IAM（`99e7d8581`）· #4961 G1（`8644da0dd`，§8.1 真 sidecar probe 在 PR comment）· #4957 G3（`a9e1d400b`；rebase 時一個 G1 測試依 C-223-41 Rev 改成「最後一則 USER 是目標、較早 item 只在 transcript 段」）· #4954 Console（`42f3ddde2`，**merge commit**：acceptance workbook manifest 綁 catalog commit sha，squash 會讓 `verify` 紅；跟 main 的重產撞了兩次、各重釘一次）· #4958 G2（`26f7b70f3`）。三張 gateway PR 之間只有測試檔尾端互撞，全部 keep-both 解。**#4969 G4**（`404b54a28`；stage memo key 加了 tool 文字——否則同一 user turn 換一個 tool 輸出會命中舊裁決，把開關悄悄關掉）。**七張全部 merge、九項全部落地；尚無環境部署。** 部署序 IAM → gateway → Console；新欄位預設 = 今日行為，memo env `0` 關，#9 受 `XPARSE_PII_WIDE_SURFACE_ENFORCE`。

**2026-09-21 補記：Jev engine（ADR-476）對上面九項的影響**——只動 classifier 那幾列，PII／word_filters 的列零影響：

| 對應 # | Jev 上線後要知道的 | 契約 |
|---|---|---|
| 1（verdict memo） | memo 命中時 `per_check` 原樣重發，**唯一例外**是 `classifier_external_input_tokens` 歸 0——沒外呼就不該讓租戶對 TypeSafe 帳單重複計。memo 與 semantic-cache 兩個 key 都含 `jev_credential_ref`，換憑證不會命中舊裁決 | C-223-58（C-223-50 逐位元重發的唯一例外） |
| 3（`scan_tool_results`） | 允許跟 Jev 併用，但 Jev 單次「state＋最長題目」上限約 32k tokens：tool 輸出超過就判不了 → `classifier_surface_too_large` → 走 `on_failure`。>100,000 字元在本地就擋、零外呼；其間由廠商回 400（實測 90k 字元 64/64 全 400） | C-223-56（上限）· C-223-57（失敗對映） |
| 7（content_filter 吃 transcript） | 「provider-API arm 維持單句」**多了一個例外**：Jev arm 吃**前文視窗**——被判的那一則永不截斷，前文取最近**連續**整輪（≤8 輪、state 12,000 字元預算），有丟輪就在 audit 記 `classifier_context_truncated`。`openai_moderation`／NemoGuard 仍是單句；output stage 無前文 | C-223-56（amends C-223-41） |
| —（新，**2026-09-22 已一般化**） | ~~Jev 是唯一有資料邊界 gate 的 evaluator~~ → **所有判定會出境的 evaluator 都過同一道 gate**（#5235，SPEC-223 C-223-55；ADR-356 Am.A／ADR-318 Am.B／ADR-476 Am.D）：`on_prem` app／`data_egress=denied` 的 key／`XPARSE_ONPREM_ENFORCE` → 零外呼、503 `classifier_boundary_blocked`，shadow 亦然。涵蓋 Jev 兩臂、`openai_moderation`、**pin 到雲端模型的內建 judge**（`classifier.model` 非 `auto`／C-223-28 fallback）；`auto` 的內建 judge 不 gate（kernel 核准的 route），NemoGuard 宣告 in-boundary 不 gate。**直接 enforce，無 observe 期**——`profile_type` 可 PUT 改，租戶自救：改 `hybrid` 重 mint／自架 evaluator／`on_failure=degraded`。綁定時的預告見 C-223-63（#5238） | C-223-55（amended）· C-223-63 |
| —（新） | 遮罩後文字對 Jev 判定的影響實測：on_topic 0/24、content medium 0/48 翻盤——**PII enforce 不會拖累 Jev 的準度**，所以沒有理由為了「判得準」把 PII 留在 shadow | `docs/research/poc/jev-guardrail-evaluator-2026-09-21/` |

| —（新，2026-09-22 傍晚，PR [#5258](https://github.com/futurenestit/xparse/pull/5258)） | **冷連線握手寬限**：閒置 ≥30 s（keep-alive 過期）或首次外呼的那一次，deadline = 3 s + 2 s；熱連線仍 3 s；寬限後仍逾時照樣計入 breaker。起因：breaker cooldown 30 s = keep-alive 過期 30 s，半開探針永遠冷，當天實測冷連線 1.2–2.6 s > 1.5 s（routing）——矩陣 G4d 首兩發 503 `guardrail_timeout` 就是這個。`stages: ["output"]` 同 PR 修：以前 input 臂照跑 | SPEC-294 Rev.5 §3.1 · ADR-476 Amendment F · SPEC-223 §1（stages） |

部署序跟上面那批**相反**：Jev 是 **gateway → IAM → Console**（IAM 先上會讓政策寫得出 gateway 還不會跑的 engine → 每個請求 `classifier_unknown_engine`，而且那個碼目前回 451 不是 503，#5197）。

### 3.9 AWS Bedrock 的缺口與要注意的事（2026-10-21）

> 按嚴重度排。Bedrock 怎麼運作見 §2.9。

| 級別 | 項目 | 現在會發生什麼 |
|---|---|---|
| 🟠 | **未遮罩的原文會出境**（設計如此，選用） | 選了 Bedrock 的政策，每個條目的原文都送到 AWS 東京。要擋只有三條路：app 設成 `on_prem`、key 設 `data_egress=denied`、部署設 `XPARSE_ONPREM_ENFORCE`。key 的 `execution_boundary` **擋不住**（§2.9）。客戶若把「有 PII 遮罩」理解成「原文不出境」，選 Bedrock 時這個理解就錯了；Console 有揭露文字，業務也要講。 |
| 🟠 | **沒驗收就畢業** | #7021 把它開放到 rel、prod 與客戶安裝，但兩項驗收還沒做：<br>• 繁中切點校準：2026-10-22 跑了第一輪 dev set（DeepSeek 產的 153 題，`~/Desktop/testing/bedrock-guardrail-2026-10-21/calibration/REPORT.md`），結論是 0.4／0.6／0.8 維持；但題目與 level 不是人工標的，還需要另一個人出的 held-out 題組才算驗收；<br>• 共用 dev 環境的真 key 端到端：只在 Peter 本機 stack 跑過。<br>PII 那一半：2026-10-22 跑了中文姓名偵測率（`~/Desktop/testing/bedrock-guardrail-2026-10-21/calibration/names/REPORT.md`），全名幾乎全抓，但「姓＋稱謂」多半漏抓，一般詞（李子、王道、白天、文明）會被誤遮；其他 entity 仍沒有繁中評測集。`passport` 對的是 `US_PASSPORT_NUMBER`，台灣護照號碼沒有實測。文案紅線：不得寫「更準／更安全／更適合中文」。 |
| 🟠 | **AWS 429 → 該租戶 enforce 全部 503** | 配額是每個帳號、每個 region 1,500 RPM，跟同帳號的推論共用。fail-closed 是對的（INV-522-1），但租戶會以為是我們壞了。導入前先在 shadow 量用量（§2.5）。 |
| 🟡 | **開了跨副本協調的 gateway 一律拒絕 Bedrock PII** | 設了 `XPARSE_COORDINATION_REDIS_URL`（SPEC-289）的 gateway 會直接回 `engine_error` 503、零連線。原因是 PII rail 在 admission 之前跑，那時還沒有 root permit，這次外呼不在任何 permit 底下，作法跟 NemoGuard arm 一樣（`pii_detectors.py` 的 `_coordinated`）。content arm 不受影響。**rel 與 prod 目前都是 single-active、沒設這個值**（`deploy/ec2/envs/xparse-{rel,prod}.env`），所以今天沒事；哪天開多副本協調，選了 Bedrock PII 的租戶會全部 503。 |
| 🟡 | **四類只靠 regex** | `national_id`、`birthdate`、`gender`、`messaging_id` 是 Bedrock 偵測不到的，只剩 §2.2 的 regex 那一欄。只選 Bedrock 的政策，這四類的語意偵測等於沒有。 |
| 🟡 | **`/ready` 仍要求 GLiNER** | 只選 Bedrock 的政策不會呼叫 GLiNER，但 sidecar 的 `/ready` 還是要 GLiNER 活著。雲端部署還拿不掉 air520 那台（ADR-522 §5.2，另案）。 |
| 🟡 | **生效政策的舊單值 `engine` 可能跟實際偵測器不同** | 例如一層 PII 關閉（`gliner_pii`）、另一層是 `bedrock_pii` 時，單值顯示 `gliner_pii`，但 `pii.detectors` 是 `[bedrock_pii]`。新 gateway 以 `detectors` 為準，行為正確；只有讀單值欄位的地方會顯示不一致（2026-10-21 實測發現）。 |
| 🟡 | **依 engine 合併改變了既有多判官 bundle 的實際執行** | PR-10（#6969）沒先跑盤點就 merge（Peter 決定）。只影響「不同層各自指定不同 content evaluator、而且設定不同」的 bundle。部署含 PR-10 的 IAM 到 dev／rel／prod 之前，先跑唯讀的 `inventory_guardrail_engine_configs` 看受影響的單位（§2.4）。 |
| 🟠 | **shadow 的 preview 遇到資料邊界擋下時回 `degraded:false`**（2026-10-21 真元件實測發現；**修正：PR [#7039](https://github.com/futurenestit/xparse/pull/7039)，2026-10-21 已 merge，`ef9c06ea0`**：preview 改用共用的 `guardrail_response.is_fail_closed()`，修正後實測回 `degraded:true`） | 這違反 SPEC-219 C-219-24。air gap 下 shadow 政策的 `/v1/guardrails/preview` 回 200，沒遮罩、也沒標 degraded，看起來像「沒偵測到個資」。原因是 `routes/guardrails.py:36-38` 自己那份 fail-closed 清單漏了 `pii_detector_boundary_blocked`。chat 路徑沒問題（shadow 本來就照轉原文）。 |
| 🟠 | **單則超過 100,000 字元必定 503，訊息卻叫人「Retry shortly」**（2026-10-21 實測；**修正：PR #7039，已 merge**。gateway 記下上限 `BEDROCK_TEXT_BLOCK_MAX_CHARS = 100_000`，兩邊都在送出前就擋：PII 改回 451 `guardrail_surface_too_large`，violation 是 `pii_detector_input_too_large`，訊息請使用者縮短或拆開，結果不進快取；content arm 比照 Jev 回 `classifier_surface_too_large`。修正後實測：100,000 字元照送 AWS，100,001 字元零連線擋下） | AWS 的上限以字元計算：100,000 字元可以過，100,001 字元回 400 → `engine_error` 503。中文 40k 字元（120 KB）可以過。這是確定性的失敗，重試永遠不會成功，agent client 會一直重試。建議比照 C-223-17 在本地先擋：零連線、回 451 加「請縮短」的訊息。相關程式：`pii_detectors.py:327-331`（所有非 200 一律當 engine_error）、`:379-404`（太大的條目單獨送、不切分）。 |
| 🟡 | **PII 的邊界來源沒進 audit**（2026-10-21 實測；**修正：PR #7039，已 merge**。新增 audit 欄位 `guardrail_pii_boundary_source`，enforce 與 shadow 都記；修正後實測記到 `deployment_onprem`） | audit 只記 `pii_detector_boundary_blocked`，看不出是三條腿的哪一條擋的；content arm 有記 `classifier_boundary_source`。SPEC-219 C-219-53 的 shadow 列與 ADR-522 §2.2.11 都要求記。原因是 `guardrail_enforcer.py:665-672` 丟掉了 `exc.boundary_source`，`pii_detectors.py:277` 其實有設。 |
| 🟡 | **Console 稽核頁把 Bedrock 的 audit 欄位顯示成沒有名稱的列**（2026-10-21 發現，另開處理） | IAM 的 audit 欄位目錄（`apps/iam/xparse_iam/xparse_iam/api/audit_catalog.py` 的 `PARAM_DICTIONARY`）是 audit 欄位的「第四個宣告點」：handler、gateway `audit/schema.py`、`xparse_bridge.PAYLOAD_ALLOWLIST` 之外，沒登記的欄位在 Console 稽核頁只會顯示成沒有名稱的列。<br>ADR-522 只登記了 `classifier_engine`。沒登記的有：<br>• `guardrail_pii_detector_calls`<br>• `guardrail_pii_detector_text_units`<br>• `classifier_external_text_units`<br>• #7039 新增的 `guardrail_pii_boundary_source`<br>連更早的 `classifier_boundary_source`、`classifier_provider_scores`、`classifier_provider_categories`、`classifier_credential_ref` 也缺。<br>要修得同時改 IAM 目錄與 Console 的 i18n。這已經是第三次漏登記（#4766、ADR-488 Amendment A 都踩過），值得加一個「gateway 的 allowlist ⊆ IAM 目錄」的 gate。 |
| ⚪ | **shadow preview 遇到過長或被截斷的訊息時回 `degraded:false`**（產品決定，未改） | 這符合目前 C-219-24 的寫法：截斷與過長不算「偵測器無法使用」。但作者可能把「沒遮罩」讀成「沒有需要遮的個資」。要不要標示「沒有完整檢查」，由產品決定。 |
| 🟡 | **中文姓名偵測不穩** | 「陳大文」抓得到，「林小美」三次都沒抓到。只選 Bedrock 的政策，非介紹句型的中文姓名可能漏掉；regex 層只認介紹句型（§2.2）。這是「繁中沒有評測集」那一列的具體例子。 |
| 🟡 | **已用真元件觸發過的錯誤路徑**（2026-10-21，`~/Desktop/testing/bedrock-guardrail-2026-10-21/error-paths/REPORT.md`） | 以下都符合 SPEC-219 C-219-53／SPEC-223 C-223-74：<br>• `truncated`（超過 AWS 1,000 筆）→ 451，不進快取；<br>• 超過 100k 字元 → 503；<br>• PII 與 content 逾時 → 503，連續 3 次後斷路器打開，30 秒後恢復；<br>• GLiNER 停掉時只選 Bedrock 的政策照常遮罩；<br>• air gap 零連線 503；<br>• 320 個並發請求觸發 AWS 429 ×124，回 503，斷路器沒開、失敗不進快取；<br>• 順帶碰到 AWS 500 四次，回 503。<br>仍然只有假 server 測試的：AWS 回格式錯誤、連線層重試、401／403、content arm 的 429、`_coordinated`。 |
| ⚪ | **輸出側照舊沒有 PII 遮罩** | Bedrock 的 content arm 可以判 output stage，但 PII 的 `check_output` 仍是 pass-through（§3.2）。Bedrock 沒有改變這一點。 |

---

## 4. 五條別再走的死路

每一條都經過實測推翻，不是推論。**請不要重走。**

| 想法 | 為什麼不行 |
|---|---|
| 把 sidecar 契約改成批次 | 省的是 N−1 次往返。瓶頸是 GLiNER 推論吞吐——併發 8 只省 18%，**推論成本一毫秒都沒少**，卻要付跨 owner 契約變更的代價。 |
| ~~連 system prompt 一起遮~~（**前提已變兩次**：Amendment C 改為可納入，Amendment G 把預設改回不掃） | 原因是 8/8 誤改，成因是 `You are…` 的代名詞／角色名詞——#4728 過濾器移除這一類後純指令不再誤改。所以它**不是死路，是一個帶明碼代價的選項**（persona 名字會被遮、殘餘 3/5 偽陽性列 OQ-8b）；#4860 起這個選擇權交給租戶（`pii.scan_system`），**平台預設不掃**。真正的死路是原本那個版本——「平台一律遮 system」——那會系統性破壞把 system 當產品文案的租戶。 |
| 每個對話一組 salt（隱私更好） | `/v1/messages` **根本沒有 conversation id**。唯一代理值（首則訊息雜湊）在 system prompt 帶時鐘時每輪都變 → 快取命中率 **0%**，且同一個人在八輪拿到八個代號。模型把一個人讀成八個人，比它要防的串聯風險更糟。 |
| 改用 `name` 零樣本標籤 | 18 句真名語料召回 **0/18**，唯一命中是字面字「姓名」。已於 #4532 移除。 |
| 調高 `pii_score_threshold` | 偽陽性歸零要付 **11% 召回**。對一個偽陰性完全靜默的控制，這是反方向的最佳化。 |

---

## 5. 怎麼驗證

### 5.1 prod 復現（五分鐘，不用 checkout）

兩個 curl 在 #4531 的 comment 裡。

> ⚠️ **oracle 的問法是承重的。** 問模型「你收到的那段設定檔，值是**方括號代號**還是**可讀原文**？只回一個詞。」
>
> **不要**叫模型把收到的內容逐字重印——它會拒絕並自己把個資遮起來（`陳*宏`），那個畫面**看起來像平台攔住了，其實證明它看到了原文**。最初的回報之所以模糊一小時，就是問法用錯了。

### 5.2 本地

```bash
# guardrails owner 全套（main 上 441 passed；#4765 之後 457）
cd apps/guardrails && python3 xparse_guardrail/scripts/project.py test
# venv 沒裝時可直接：python3 -m pytest xparse_guardrail/tests -q -o addopts=''

# 跨 owner 契約
python3 -m pytest tests/contract/test_guardrails_consumer_contract.py

# 偵測面 roster gate
python3 .github/scripts/guardrail-detection-surface-gate.py --self-test
bash .github/scripts/guardrail-detection-surface-gate.sh

# gateway 那側（主機 python 缺 otel，一律在容器內跑；-i 不能漏）
WT=$(git rev-parse --show-toplevel)
docker run --rm -i --network xparse-network --entrypoint /opt/xparse/gateway/venv/bin/python \
  -v $WT/apps/gateway/bustream:/app/bustream -v $WT/apps/gateway/xparse_routing:/app/xparse_routing \
  -w /app xparse-scr:celery-local -m pytest bustream/tests/unit/test_adr448_pr5_enforce_surface.py -q
```

> **`apps/guardrails` 的測試覆蓋 `grep .github/` 看不到。** 它走 owner capsule 不是逐檔登記：
> `monorepo-inventory.yml` 的 `guardrails-envelope`（paths `apps/guardrails/**`）→ `capsule-run --project guardrails`
> → `project.yaml` 的 `commands.test` → `scripts/project.py::test` → `pytest xparse_guardrail/tests`（整棵樹）。
> 2026-09-14 有人據 grep 結果開了「engine 測試零覆蓋」的 P2（#4740），實際上 #4728 的 job log 就有
> `command=test status=succeeded duration_seconds=1.811`，本地重現是同一個 `441 passed in 1.84s`。
> 走策展清單的（gateway / IAM）才 grep `*-ci-suite.txt`；走 capsule 的要讀 `apps/<name>/project.yaml`。

> ⚠️ **本地 bundle 目前指到 policy v3：`mode: enforce` 但 `entities: []`**（2026-09-13 11:20 由 Console tenant_admin 建立）。這是 no-op fold——**什麼都不偵測、所有請求 verdict `pass`**。fork 跑矩陣時第一輪全 `pass` 就是這個原因，它暫時指回 v2 量完後**又還原成 v3**。要在本地測遮罩，先把 bundle item 指回 v2（12 類）。若這個 v3 不是刻意建的，可能是 Console 儲存流程在 entities 沒選時仍建了版本——值得查。
>
> ℹ️ **本地 `xparse-guardrails:dev` image 最後一次重建：2026-09-14 13:29，來源 main（含 #4807）**；本地 `xparse-gateway` 是 main（live-mount）。改了 `apps/guardrails` 就要重建，沒重建就是在測舊碼。
>
> 🔴 **最大的坑：sidecar 跑的不是你的工作樹。** gateway 是 live-mount（`apps/gateway/bustream` → `/app/bustream`），但 **`xparse-guardrails` 沒有任何 mount**——它在 build 時把 `xparse_guardrail/` COPY 進 image。2026-09-11 踩到：本地 image 建於 08-14，`mask_text(text, spans)` 連 salt 參數都沒有，所以第一輪「驗 ADR-448 內容衍生 token」量到的**全是舊行為**。
>
> 查：`docker exec xparse-guardrails python -c "import inspect;from xparse_guardrail.engine.gliner_pii import mask;print(inspect.signature(mask.mask_text))"`，跟主樹比。
> 重建（root compose 檔已退場，路徑在 `deployments/compose/`）：`docker compose --project-directory . -f deployments/compose/tiers/docker-compose.dev-mvp.yml -f deployments/compose/overlays/docker-compose.mvp-audit.yml -f deployments/compose/overlays/docker-compose.mvp-fleet.yml -f deployments/compose/overlays/docker-compose.guardrails-local.yml build xparse-guardrails` → `docker rm -f xparse-guardrails` → 同一串 `up -d --no-build --no-deps`。**`-f docker-compose.guardrails-local.yml` 不能漏**，否則 image 會解析成 ECR 那顆。

**GLiNER 不必在本機跑。** prod 與 rel 都沒有 gliner 容器——`gliner-server` 刻意不在 CI build matrix（2.43GB 烘進 image 的權重），兩邊的 `XPARSE_GLINER_SERVER_URL` 都指向 air520 的地端機。本機在 root `.env` 加同一行即可（`deployments/compose/tiers/docker-compose.dev-mvp.yml` 本來就有 `${XPARSE_GLINER_SERVER_URL:-...}` passthrough），從 docker 內 ~30 ms。沒有它時 sidecar 對每個 check 回 `502 gliner server unreachable`，shadow 全部記 degraded——**看起來會像「沒偵測到 PII」**。⚠️ 該端點是裸 HTTP 公網 NAT、無 auth/TLS/allowlist，別拿真客戶資料下去跑。

**enforce 全矩陣一鍵驗證**（2026-09-13 起）：`~/Desktop/testing/pii_enforce_matrix.py --phase all`（對 PR-5 之後的 gateway 加 `--post-pr5`，判定會讀 `input_check` 的 `surface_masked_messages`）（matrix / tokens / fp / failclosed / surface 五個 phase；報告樣本 `results/pii_enforce_report_2026-09-13.md`）。判定以 gateway `input_check` verdict 為主證據——enforce 下只有 `modify` 會改寫、且只改最後一則 user，所以 `pass` + 有種 PII 就是外洩；模型 oracle 在 agent 形狀下會答錯，只當輔證。`surface` phase 需要政策是 **shadow**（見 §3.6）。另：測試措辭含「他的身分證是…」會被 provider 自己的內容過濾以 200 拒答（`illegal activity related content is forbidden`、無 `xparse` 區塊），那不是 gateway。

**跑偵測面 shadow 觀察窗**（§3.1 的數字就是這樣來的）：

1. 確認 GLiNER 端點活著（上面那段）。
2. `XPARSE_PII_DETECTION_SURFACE_SHADOW=true` — 寫進 root `.env` 再 recreate gateway 即可（dev-mvp 與 pro tier 的 gateway 都 `env_file: .env`）；疊 override 檔也行但非必要。
3. API key 的 folded policy 要真的有 PII entities。用 `POST /v1/guardrails/preview` 驗：`entities_found: []` 是**沒綁到**，不是沒個資。綁定鏈是 policy → version → bundle → item → binding（全部 `docker exec xparse-iam` 打 `localhost:8010`，路徑 `/iam/...` 無前綴）。
4. 證據讀 gateway log 的 `input_check`（窄 rail 的 verdict）與 `detection_surface_observed`（`surface_*`）。shadow 走 detached task，**回應回來之後才落 log**，要 poll。

**shadow 模式下不要用「問模型收到什麼」當 oracle**——shadow 本來就一律轉送原文，模型永遠回「可讀原文」，證明不了任何事（那個問法只在 §5.1 的 enforce 情境有效）。要判「窄 rail 漏了什麼」只能自己種個資當 ground truth，再逐則比對窗口位置。探針：`~/Desktop/testing/pii_shadow_surface_probe.py`（`--check` / 預設形狀矩陣 / `--agent`）。

**gateway 測試的兩個坑**：① 主機 python 缺 otel，`tests/unit/audit_tests/` 與 `test_audit_guardrail_schema_promotion.py` 在 collection 期就 ERROR ② `test_guardrail_structured_log.py` 有 5 個、`test_guardrail_phase4_wave1_mode.py` 有 4 個**順序相依**的既有失敗（`_drain_shadow_input_tasks` 跨 event loop），單獨跑檔案就過。排查時**先單獨跑，再對乾淨 `origin/main` 在第二個 worktree 比對失敗集合**。

**word filters 本地驗證（2026-09-13 跑過）**：用 `~/Desktop/testing/.env` 的 `XPARSE_API_KEY2`（**`XPARSE_ADMIN_KEY` 是 tenant_admin key，推論一律 403 `tenant_admin keys cannot be used for inference`**，只能查 `/apis/iam/*`）。先 `GET /apis/iam/effective-policy-bundle-bindings?target_scope_type=application&target_scope_id=<app>` 確認 guardrail bundle 是 `active` / `mandatory`，再打 `/v1/chat/completions`：`mask` 詞不要用「照抄這句」當 oracle（gpt-4o 會拒答），改用「翻成法文」或「逐字列出每個詞」——回覆出現 `replacement` 就是遮了；`block` 詞直接看 **451 `word_filter_match`**；對照組 200。要驗「較早輪次」把詞放在 system 或前一則 user 再問模型。gateway log 的 `input_check` 行有 `violation_type`（`word_filters`）與 `surface_*` 欄位可當一手證據。**本地 `var/audit/*.jsonl` 是空的**，別拿它當證據。真元件 probe（不動共用樹）：`docker run --rm -i --network xparse-network --entrypoint /opt/xparse/gateway/venv/bin/python -v $WT/apps/gateway/bustream:/app/bustream -v $WT/apps/gateway/xparse_routing:/app/xparse_routing -w /app xparse-scr:celery-local -` 餵一段呼叫 `GuardrailEnforcer(sidecar_base_url="http://xparse-guardrails:8400").check_input(...)` 的腳本——**`-i` 不能漏**，漏了整段沒輸出。

### 5.3 真元件 probe（§8.1）

研究的 9 支 probe 在 `docs/research/poc/guardrail-pii-detection-surface-2026-09-09/`，全部對**真 sidecar** 跑。要驗任何「錯誤路徑會不會觸發」的宣稱時用它們，不要用 fake——用「會吐出你所假設的 trigger 的 fake」測 handler，只證明了 fake 的契約。

**零替身的做法（2026-09-14 驗 #4738 用的，值得抄）**：要問「這條路徑到底有沒有跑到 rail」時，不要 mock sidecar——把 `sidecar_base_url` 指到一個**不存在的 host**，然後用真 `run_input_guardrail` + 真 `GuardrailEnforcer` + 真 `guardrail_policy_adapter` 跑。這樣 **451 vs 503 本身就是判別式**：

- `451 guardrail_surface_too_large` = 連 sidecar 都沒打就被 ceiling 擋了（rail 沒跑）
- `503 guardrail_service_unavailable` = 真的去打了 sidecar（rail 跑了，只是打不通）

整段驗證裡一個替身都沒有，比「用會 raise 的 fake 測 handler」強一個量級。同樣的技巧驗 #4742 時連容器都不用：直接 import 真 `profile_fingerprint` / `mask_cache_key`，對四種 policy 形狀印出 key 比對就好。

---

## 6. 延伸閱讀

| 文件 | 管什麼 |
|---|---|
| `docs/prd/PRD-241-guardrail-v1-pii-only.md` | what & why、商業賭注、§4 客戶端驗收條件 |
| `docs/adr/ADR-309-guardrail-v1-gliner-pii-collapse.md` | 為什麼收斂成單一能力、為什麼自架 GLiNER |
| `docs/adr/ADR-448-...-content-derived-tokens.md` | 偵測面 ⊥ 改寫面、內容衍生 token、快取、shadow-first；**Amendment A**（salt key）、**Amendment B**（enforce 切換／451／tool 參數／預算／過濾，PR #4727）、**Amendment C**（system + `instructions` 納入——程式碼 #4735 先 merge，契約由 #4764 事後補正，§C-0 有記）、**Amendment D**（本輪四項：rail gate／cache 指紋／FP kill switch／entity ids 進 audit，#4764）、**Amendment E**（純文字 parts 陣列進改寫面、per-call timeout 由預算導出、快取只存裁決，#4806）、**Amendment F**（deadline 以 `timeout_ms` 隨請求下傳到 sidecar，#4807）、**Amendment G**（`system` 掃描改政策開關預設關，#4860）、**Amendment H**（2026-09-17，#4951：D23 Responses 寬面／D24 跳過進 audit／D25 block 面含工具參數／D26 `scan_system` 升 policy 層；INV-448-24～27） |
| `docs/adr/ADR-296-...-input-mutation.md` | 改寫面契約（+ Amendment A；**Amendment B** 推翻 A-2「只標不擋」） |
| `docs/adr/ADR-303-guardrail-output-path-coverage.md` | 輸出側覆蓋矩陣與 SSE 邊界 |
| `docs/spec/SPEC-213-guardrail-response-contract.md` | **客戶端看到什麼**：四種 block 呈現、`block_presentation` 與 derive 規則；**§3.1 全表 + C-213-13..17**（2026-09-15）= 每個 violation type 的 curated 訊息、不得洩漏 rail 名、content_filter 點出 category、output stage 用「答案被withheld」措辭、fail-closed 說「沒送出去」 |
| `docs/spec/SPEC-223-guardrail-v2-contract.md` | classifier rails（on_topic / content_filter）；**C-223-25/27 於 2026-09-15 修訂**——graceful 不再是預設，未 authored 一律 `error`；**2026-09-17（#4951）**：C-223-41 Rev（content_filter llm arm 吃 transcript 只判最後一則 USER、Responses 最後一則 user item、撤回「PII 只改最後一則」）、C-223-49 tool 形狀結尾跳過、C-223-50 verdict memo、C-223-51 `scan_tool_results` + audit `classifier_target` |
| `docs/adr/ADR-318-guardrail-v2-in-gateway-llm-classifier.md` | classifier 架構 owner；**Amendment A（2026-09-17，#4951）**：上面四條 SPEC-223 條款的決策與 INV-318-12～15；A-1 只跳 tool 形狀結尾（純 assistant prefill 照判，防 prefill bypass）、A-2 memo hit 在 rate bucket 前、A-3 只有 llm_classifier arm 吃 transcript、A-4 `scan_tool_results` 預設關 |
| `docs/adr/ADR-476-jev-hosted-guardrail-judgement-source.md` | **Jev 當 classifier rails 的第四個判定來源（2026-09-21）**：§3.1 為什麼只做 on_topic／content_filter、**不做 PII 與 word filters**；§2.2 請求形狀、資料邊界 gate、前文視窗、失敗對映；§7.2 rollback 盤點查詢；INV-476-1..15。契約在 SPEC-223 **C-223-52..60**（C-223-55 邊界 gate、C-223-56 amends C-223-41、C-223-58 是 C-223-50 的唯一例外、C-223-60 prod 扣住） |
| `docs/prd/PRD-332-jev-guardrail-judgement-source.md` | Jev engine 的 what & why、§0 白話層、§1.4 Non-Goals（PII／word filter 不交給 Jev 的理由與數字）、§4 驗收 |
| `docs/research/RESEARCH-jev-guardrail-evaluator-evidence-2026-09-21.md` · `docs/research/poc/jev-guardrail-evaluator-2026-09-21/` | Jev 的評測證據與凍結題組：遮罩後文字不翻盤、長前文的穩定度、90k 字元 64/64 回 400；**明列缺口**（繁中違規樣本、`sexual`／`self_harm`、`high` 門檻未校準、未與現有三個 engine 對照）——這些是 prod 發佈的前提 |
| `docs/research/RESEARCH-agent-client-block-status-retry-behaviour-2026-09-15.md` | 三家 agent CLI 對 block 狀態碼的實測：Codex terminal 集合只有 `{400,429}`、451 吃 5 次重試；Claude Code 逐字顯示 `message`。追蹤票 #4854 |
| `docs/spec/SPEC-219-guardrail-pii-v1-contract.md` | **行為契約**——taxonomy、fold、wire、token、mode；Rev.3 = C-219-36（451）/38（tool 參數）/39（預算、上限、kill switch）/40（過濾規則）；**Rev.4** = C-219-35 改寫（system + `instructions` 納入）+ C-219-36 撤回「排除角色」尾句；**Rev.5** = C-219-41（rail gate）/42（cache 指紋）/43（FP kill switch 與已量測殘餘），並在 C-219-40 補上殘餘例外條款；**Rev.6** = C-219-44（純文字 parts 葉值級改寫）/45（快取政策）+ C-219-36/39 修訂；**Rev.7** = C-219-46（`timeout_ms` deadline 下傳）；**Rev.8** = C-219-47（`scan_system` 開關）；**Rev.9**（2026-09-17）= C-219-35/47 改寫（policy 層 `scan_system`、alias、audit 欄位、block 面）+ C-219-48（Responses 寬面） |
| `docs/adr/ADR-309-...md` §2.6a Amendment B · SPEC-224 C-224-54 | legacy `blocked_keywords` → word_filters 投影（#4733） |
| `xparse-wiki/wiki/concepts/pii-detection-surface.md` | wiki 概念頁（PR #4727） |
| `~/Desktop/testing/pii_enforce_matrix.py` · `results/pii_enforce_report_2026-09-13.md` | 真元件驗證腳本與報告（§5.2） |
| `docs/research/RESEARCH-guardrail-pii-detection-surface-root-cause-2026-09-09.md` | 八層根因、外洩矩陣、五個被推翻的修法、門檻曲線 |
| `docs/research/RESEARCH-prd232-pii-keyword-redaction-evidence-2026-07-10.md` | 差異化的對抗式查證（commodity 結論的來源） |
| `docs/prd/PRD-285-guardrail-word-filters-deterministic-custom-terms.md` | word filters 的 what & why、§0 對客戶的四句話、U2 紅線文案（**Accepted**，2026-09-17 #4951；U2 依 C-224-32 Rev 改寫） |
| `docs/adr/ADR-389-guardrail-word-filters-deterministic-rail.md` | matcher 演算法、rail 組合、span 優先權、fold、投影遮蔽；擁有 INV-389-*（**Accepted**，2026-09-17 #4951；INV-389-4 Rev） |
| `docs/spec/SPEC-224-guardrail-word-filters-contract.md` | word filters 行為契約：§1.1 寫入驗證、§4.2 normative 正規化、§4.3 偵測面 vs 改寫面（**C-224-32 在 main 上已過時，見 §2.8**）、§5 verdict/audit、C-224-54 legacy 投影；**2026-09-17 Rev（#4951）**：C-224-32 改為 as built（block 面含工具參數 JSON 解碼葉值、mask 面 = 最後一則 + 寬面較早輪次、system 依 policy 層 `scan_system`）+ C-224-32b（Responses `function_call*`） |
| `docs/research/RESEARCH-custom-term-redaction-real-requirements-2026-07-12.md` | word filters 的需求查證（列清單型防護的天生弱點、業界對照） |
| `docs/prd/PRD-375-bedrock-guardrail-engine-content-and-pii.md` | **Bedrock 當 PII 語意層與 content_filter 判定來源（2026-10-20）**：what & why、§4 驗收（I／N 系列）、U8 文案紅線、§3.8 畢業條件與 2026-10-21 owner 修訂 |
| `docs/adr/ADR-522-bedrock-guardrail-engine-and-per-engine-fold.md` | 怎麼做：`InvokeGuardrailChecks` 加外部 span、§2.2.2 對應表、§2.2.6 gateway 偵測 runtime、§2.2.8 依 engine 合併、§2.2.9 憑證與 region、§7.3 實測紀錄；INV-522-1..13；改寫 ADR-309 INV-309-2 |
| `docs/spec/SPEC-219-guardrail-pii-v1-contract.md` **Rev.13–15** | C-219-50（依 engine 合併）· 51（external spans）· 52（gateway runtime）· 53（失敗對映）· 54（快取）· 55（資料邊界，改寫 INV-309-2）· 56（寫入；Rev.14 偵測器跟著 Engine 走、Rev.15 畢業） |
| `docs/spec/SPEC-223-guardrail-v2-contract.md` C-223-69..76 | Bedrock content arm：類別、六階分數、切點、憑證投影、傳輸層、Test 路由 |
| `docs/research/RESEARCH-bedrock-guardrail-checks-probe-2026-10-20.md` | 東京真 API 實測：位置以 code point 計、回應形狀、為什麼不用 `ApplyGuardrail` |
| `~/Desktop/testing/bedrock-guardrail-2026-10-21/REPORT.md` | 本機 stack 的真元件測試（S0–S13、I 系列、三個入口、三個 agent CLI、on_prem app、畢業後以 prod 標籤跑的 E2E） |
