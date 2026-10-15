# Policy Actions：把「觸發後動作」從 guardrail 抬到 Policy 層 — 草案 Rev.1

> **狀態**：**已全案交付並 merge main（2026-09-17）**：ADR-461 · SPEC-292 Rev.10 · PRD-325 Am.A · PR #4937/#4936/#4935/#4938/#4942/#4941/#4940/#4943/#4947/#4944/#4945/#4946；本檔轉為歷史紀錄，衝突時以 `docs/` 為準。原狀態：草案 Rev.1（2026-09-16）。設計閉環的**輸入**，不是結論。**設計閉環已產出於 PR #4937**（`docs/adr461-policy-actions-design-closure`）：ADR-461（Accepted）+ SPEC-292 Rev.6 + PRD-325 Amendment A + RESEARCH-policy-level-actions-prior-art-2026-09-16 + Core 回寫 + glossary + wiki。**本檔自此為歷史紀錄，衝突時一律以 `docs/` 為準。**
> **產出時的兩處修正（本檔未回改，記錄於此）**：① `tighten_merge_guardrail` 實際在 `guardrail_policy_merge.py:449`（本檔 §3.4 寫 `:486`）；② §6 兩條被 evidence pack 收窄——Cloudflare 動作只確認 **Flag／Block**（未見 `Ignore`），Sentry 的「共用 action 目錄」官方頁**未明說**（標 WEAK）；Bedrock `ANONYMIZE` 只對 PII 有效在 `CreateGuardrail` 頁看不到（標 UNVERIFIED）。
> **起因**：Peter 2026-09-16 指出：trigger action 的對象應該是 **policy**，不是 guardrail。未來有不同 PolicyKind 時都可以觸發這個 action；conversation scope 只是 action 的其中一種；建立／編輯 policy 時應有一個 action section，未來可有多種 action、現在只有 conversation scope 可選；`llm_operational` 這個 kind 觸發後也應該能觸發 conversation scope；action 不應與 guardrail 耦合。
> **現況基準**：`origin/main` = `0e11d6aa7`，本地落後 0。PRD-325 / ADR-459 Rev.5 / SPEC-292 Rev.5 全案已 merge main（#4894 → #4901/#4907/#4908 → #4909 → #4927/#4929/#4930），**dev / rel / prod 三個環境皆未部署**。本檔每個 `file:line` 皆為當日實讀。
> **本檔怎麼來的**：七個並行讀者（IAM／gateway／Console／LiteLLM 2026-09-14 快照／Portkey OSS gateway／外部產品一手文件／既有 docs）→ 三位設計者從「最小改動」「乾淨架構」「管理員心智模型」三個角度各出一版 → 三位評審打分（UX 24.5 / MINIMAL 23 / CLEAN 22，各自贏一位評審）→ 合成 → 16 條關鍵宣稱對程式碼做對抗式查證，**8 條被推翻**，勘誤已折進本檔（§2.3）。
> **D 編號空間**：本檔用 `PA-D1…PA-D17`，與 `guardrail-action.md` 的 D1–D7、ADR-459 的 D8–D16 / G1–G10 是不同編號空間，不得互引。
> 相關文件：PRD-325 · ADR-459 Rev.5 · SPEC-292 Rev.5 · ADR-249（kind 三層：profile / orchestration / limits）· ADR-259（每 kind 一次 fold）· ADR-191（PolicyKind 與三個 enforcement plane）· ADR-093。可點的 UI 原型：https://claude.ai/artifact/49zjPN1kiJVS47JBtH2A8g（§5.0）。

---

## 0. 一句話與決策紀錄

**一句話**：把 `restrict_conversation_scope` 從 `GuardrailPolicySpecV2` 的一個欄位（`apps/iam/xparse_iam/xparse_iam/policies/schema.py:653`）改成任何 PolicyKind 都能攜帶的 `actions` map；「什麼算這條 policy 被觸發」由每個 kind 的 **trigger registry** 定義、管理員在動作卡上顯式勾選、IAM 在 write boundary 驗證；gateway 只讀一個頂層 `policy_actions` wire 鍵，pre-filter / latch store / 三段 key / 空集合 400 全部原封不動。

**規則決定什麼算違規；動作決定違規之後做什麼。** 這句話同時是資料模型、Console 區段的說明文字、也是 Peter 論點的白話版。

### 0.1 待拍板（★ = 建議）

| # | 決策 | 建議 ★ | 詳見 |
|---|---|---|---|
| **PA-D1** | `actions` 的容器形狀 | **以 `action_type` 為 key 的 map**；一份 policy 每型別最多一個實例 | §3.2 |
| **PA-D2** | `triggers` 是不是 authored 欄位 | **是**。管理員勾選，值域由 `TRIGGER_REGISTRY[kind]` 決定，write boundary 驗證 | §2.2 / §3.3 |
| **PA-D3** | `llm_operational` 的 trigger 值域 | **v1 只有一個：`admission_rejected`**（涵蓋這份 policy 的 `rate_limit` 造成的 429／503／504）。真元件只吐 `rate_limit / queue_overflow / queue_timeout` 三種理由，且 reject-mode 的併發用盡在 wire 上就是 `rate_limit`——**拆不開，就不要假裝拆得開**。`limits` 永不觸發 | §2.2 |
| **PA-D4** | 觀察窗（observe）機制 | **不新增 authored `mode` 欄位**；由 registry 的 `default_enforcement` 決定，`llm_operational` v1 = `observe`（沿用 `would_latch`）。翻 enforce 的前置是觀察窗報告 | §2.2 / §9 |
| **PA-D5** | wire 形狀 | **頂層 `policy_actions`**，接受五處 consumer digest 重釘 | §3.5 |
| **PA-D6** | audit evidence 第八鍵 | **新增 `conversation_scope_sources`**，獨立三檔 PR | §4.4 |
| **PA-D7** | latch 列形狀 | `PRIMARY KEY (key, action_id, policy_kind)`；key material 仍三段；`policy_ref` 只做診斷不比對；**同 PR 補 `PRAGMA user_version` 讀回** | §4.3 |
| **PA-D8** | 未知 action 的前向相容 | 加 `requirement: mandatory \| advisory`（XACML Obligation／Advice）；gateway 不認得 `mandatory` → fail-closed。v1 固定 `mandatory` | §3.2 / §4.2 |
| **PA-D9** | 跨 kind fold 方向 | **交集（CNF），且只計入真的被觸發的 kind** | §3.4 |
| **PA-D10** | trigger 集合為空的 kind 掛 action | **write boundary 400**，不提供 draft | §3.3 |
| **PA-D11** | 驗證失敗的 HTTP status | **維持 400，改文件**（ADR-459 §2.2.1 與 C-292-1 寫 422，實作是 400） | §2.3 |
| **PA-D12** | 文件形狀 | **新 ADR-461**（amends ADR-459，不 supersede）+ SPEC-292 Rev.6 + PRD-325 Amendment A；不開新 PRD | §7 |
| **PA-D13** | 三件改名延後 | audit 事件名、capability 契約搬 owner、sink 檔名：**全部延後**，各開 tracking issue | §7.3 |
| **PA-D14** | 中文區段名 | **「觸發後動作」**；word-filter 每列的 `Action`＝「動作」不動，glossary 兩條並列 | §5.6 |
| **PA-D15** | 部署順序 | **gateway → IAM → Console**；**Rev.5 不單獨部署**，與本案同批 | §8.3 |
| **PA-D16** | v1 範圍 | **只有一個 action type**；`llm_operational` 的 registry **先空著**，與真 `run_admission` probe 綠的同一個 commit 才填 | §8.1 |
| **PA-D17** | 舊鍵 `restrict_conversation_scope` 的相容 | **parse 時 coercion 一個 release**（`null` 直接丟、非 null 搬進 `actions`、兩者並存 → 400），之後移除。理由見 §2.3 #1：`_StrictModel` 是 `extra="forbid"`，resolver 會把落盤 content 重新 parse，直接刪欄位會讓任何帶舊鍵的 row 在 resolve 時 fail-closed | §3.3 |

### 0.2 前置條件

**寫 ADR 之前**：無。本案不新增商務需求（跨輪治理的需求 PRD-325 已立），只搬架構——依 §17.1a 這是 ADR 的工作。

**實作之前（缺一不得動 PR-3 以後）**：

1. `/research` 產 `docs/research/RESEARCH-policy-level-actions-prior-art.md`（§17.1b），內容以本檔 §6 為底，並回補研究智庫 HUB。
2. `apps/gateway/bustream/tests/contract/` 對真 `run_admission` 的 probe（§4.7 (d)(e)）。**這條不綠，PA-D16 的 registry 就留空。**
3. `/doc-inventory` 盤點三套既有 shadow/enforce 開關（guardrail `mode`、ADR-448 PII flag、budget `shadow/warn/enforce`）的 producer × consumer，作為 PA-D4「不新增第四軸」的依據。

---

## 1. 這是什麼

### 1.1 客戶看到什麼

李小姐是某製造業客戶的租戶管理員。她建了兩份政策：

- 一份**防護規則**（guardrail），偵測身分證字號。今天它只會遮罩，遮完就結束——下一句話還是可能送到境外模型。現在她可以在同一張表單下方按「＋ 新增動作」，加一張「對話範圍限縮」卡，勾選「OpenAI、地端 vLLM」。卡片告訴她：**命中的那一次請求就會生效**。
- 一份**運行規則**（llm_operational），限制某個應用的併發與速率。她在**同一個位置、同一張卡**加同一個動作，選「地端」。卡片這次告訴她兩件不同的事：**何時觸發**是「這份政策的限制拒絕了一次請求」，**生效時機**是「從下一次請求起，而且只有客戶端帶了對話識別碼才記得住」，並且有一行「目前為觀察模式：只記錄會限縮誰，不真的限縮」。

她不需要知道哪個 kind 支援哪個機制——那是卡片自己說的。

### 1.2 為什麼現在做

**機制早就是 kind-agnostic 的，只是放在錯的抽屜。** `conversation_scope_prefilter.py` 的 `expand_scope` / `expand_effective_scope` / `scope_check` / `conversation_scope_trimmed_models`（`:95 / :126 / :138 / :277`）全檔零 guardrail import；latch key 三段（`conversation_scope_store.py:105`）不含 kind；七個 evidence key 前綴是 `conversation_scope_` 不是 `guardrail_`；`schema.py:637-640` 的 docstring 自己就寫著「It is a policy-level **ACTION** (sibling of `mode`), not a rail」。

**成本窗口是單向的。** 今天沒有任何環境部署過，`origin/rel` 的 `schema.py` 沒有這個欄位、`origin/prod` 連路徑都沒有，沒有任何不可變的 `PolicyVersion.content` row 帶這個 key（INV-259-1：active content 不可改，只能出新版）。部署之後再改形狀，就要永遠背一個 read-compat coercion（ADR-309 `guardrail_compat` 前例）。**PA-D15 因此禁止 Rev.5 單獨先部署。**

### 1.3 它不是什麼（先寫，免得賣錯）

| 不是 | 為什麼要講 |
|---|---|
| **不是「任何 PolicyKind 都能用」** | kind-agnostic ≠ enforcement-owner-agnostic。`runtime_egress` 由 agentd + egress proxy 執行、`deployment_runtime` 由 Scheduler／Fleet 執行（ADR-191 §2.2），它們看不見 gateway 的對話。契約：一個 action 的效果面由**看得見該 trigger 的 enforcement owner** 擁有；v1 只有 gateway-owned trigger 的兩個 kind |
| **不是第二種 action** | v1 只有 `restrict_conversation_scope`。picker 的存在是「可擴充目錄」的承諾，不是「已經有很多可選」 |
| **不是即時的（對運行規則而言）** | admission 在 routing **之後**（`routes/chat.py:1322` > `:1151`），被拒的那一輪沒有路由可裁。效果從下一輪起，且需明示對話識別碼 |
| **不是安全邊界** | 換一個對話識別碼就解除；要擋繞過得靠 IAM 身分綁定（PRD-325 §1.5 原文成立） |
| **不是 token 上限的出口** | `enforce_token_limits` 是刻意留空的 stub（`admission_handler.py:202-218` 逐字「must not reject, audit a token-limit violation, or mutate request parameters」）；`limits` 永遠不會觸發任何動作 |
| **不是「業界都這樣做」** | 最接近的先例是 LiteLLM 的 `on_sensitive_data: route` + `sticky_session_routing`（§6），它是**單一 guardrail 的設定**、指向**一顆**模型；「policy 層的 action 目錄 × 多 kind × 收斂到一個集合」找不到同類 shipped 產品。這是 negative evidence，不是市場驗證 |

---

## 2. 為什麼這件事不像看起來簡單

### 2.1 六個掛載點：耦合到底在哪

| # | 層 | 掛載點 | 性質 |
|---|---|---|---|
| 1 | IAM schema | `GuardrailPolicySpecV2.restrict_conversation_scope`（`schema.py:653`） | **唯一的型別耦合**；`RestrictConversationScopeSpec`（`:405`）與 `ConversationScopeSelectorsSpec`（`:377`）本身零 guardrail 欄位 |
| 2 | IAM fold | `_merge_conversation_scope`（`guardrail_policy_merge.py:192`）純函數，但只被 `tighten_merge_guardrail`（`:486`）呼叫；chain 由 `collect_kind_contributions(policy_kind="guardrail")` 收集 | 純函數可抽、鏈要重接 |
| 3 | IAM validate | `_validate_adr459_dimensions` → `INVALID_GUARDRAIL_CONVERSATION_SCOPE`（`validate_policy_content.py:148`） | error code 帶 kind 名 |
| 4 | wire | 巢狀在 `guardrail_kind_policy.spec` 內（`iam_http_client.py:377`） | gateway 要翻 guardrail 才拿得到 |
| 5 | gateway 取值 | `scope_spec_for` 呼叫 `effective_guardrail_policy` 並以 guardrail 的 `effective_mode == "enforce"` 當閘（`conversation_scope_prefilter.py:160-175`） | 唯一把 pre-filter 綁回 guardrail 的地方 |
| 6 | gateway sink | `record_guardrail_verdict`（`guardrail_verdict_sink.py:136`）是唯一寫 latch 的出口；`_HIT_ACTIONS = {"modify","block"}`（`:62`）、`if hit and latch_mode == "enforce"`（`:186`） | 這是 guardrail 的 **trigger adapter**，不是通用 sink |

另外三處是**命名**耦合：`REJECTION_MESSAGES` 三則逐字寫「after a guardrail verdict」（`conversation_scope_prefilter.py:55-72`）；IAM 事件 `iam.guardrail_policy.conversation_scope_empty` 與 Audit seed rule `guardrail.conversation_scope_empty`（C-292-38）；capability 契約住在 guardrails owner（`apps/guardrails/xparse_guardrail/contracts/policy-capabilities.v1.json:59-65`）。

### 2.2 `llm_operational` 的「觸發」到底是什麼（本案最弱的一環，先講死）

**先把不可能的講死**：

| 候選 | 能不能 | 根據（實讀） |
|---|---|---|
| `limits` / token cap | **結構上不可能** | `enforce_token_limits` no-op stub（`admission_handler.py:202-218`）；`resolve_token_limits` 零 runtime caller |
| budget / cost 429 | **不屬於這個 kind** | 讀 `auth_context.budget_layers`（PRD-237 / ADR-300 / ADR-429），不是 policy content；`PolicyKind.BUDGET` 是另一個 kind（`db/models/hierarchy.py:27`） |
| `resilience.cross_surface_fallback` | **寫不進去** | gateway 讀它（`llm_operational_consumer.py:360-385`），但 `LLMOperationalPolicySpec` 是 `extra="forbid"`，authoring 與 resolve-time drift guard 兩處都拒。**這個既存的 inert 旋鈕正是本案的正面論據**：kind 內已經有「gateway 認得、schema 寫不進去」的東西 |
| `quota` / `runtime_budget` / `model_access` | **沒有契約** | `schema.py:277-279` 逐字「NOT in this schema until they have a Gateway consumer」 |

**真元件實際會產生的**：`production/admission/controller.py` 唯一的 `admit()` 只回三種 `rejection_reason`——`"blocked"`（`:662`，ADR-241 denylist → 403，與 rate_limit 無關）、`"rate_limit"`（`:695`，註解「Rate limited or concurrency exhausted」——**reject-mode 的併發用盡也標成 rate_limit**）、`"queue_overflow"`（`:709`）；另有獨立的 queue timeout（`admission_handler.py:154` 串流 / `:1244` 非串流 → 504）。`admission_handler.py:1143` 那個 `in ("concurrency", "queue_overflow")` 分支裡的 `"concurrency"` **是死碼**（沒有任何非測試碼產生它），而 `_emit_concurrency_exhausted` 的 payload 在 `:1436` 硬寫 `"rejection_reason": "concurrency"`，所以連 audit 都不能拿來反推真實原因。

> 合成稿原本建議「只取 concurrency_exhausted 與 queue_timeout、排除 rate_limit_applied」——**查證後推翻**：所謂的「併發用盡」在 wire 上就是 `rate_limit`，設計上拆不開。硬拆等於在問題裡假設答案（§8.1 紅旗）。

**因此 PA-D3 ★**：`llm_operational` v1 只有一個 trigger `admission_rejected` = 「這份 policy 的 `rate_limit` 區塊拒絕了一次請求」，涵蓋 429（rate_limit）／503（queue_overflow）／504（queue_timeout），不再細分。誠實的敘事是「這段對話正在超過它自己的配額，之後把它推到指定的池子」；它與「該用哪些模型」的因果是弱的，所以：

- **PA-D4** 讓它 v1 只在**觀察模式**跑（registry `default_enforcement = "observe"`，沿用 `would_latch`，零寫入）；
- 觀察窗報告必須含「同一 `(key, action_id, kind)` 的重複觸發次數分佈」——因為存在**自我增強迴圈**風險：被限縮到更小的池 → 更容易再用盡 → 再觸發、`last_seen_at` 前滑 → 對話被自己造成的限制釘住；guardrail 的內容型 trigger 沒有這個形狀，既有設計沒有防線；
- 報告若顯示這個 trigger 沒有可用性價值，正確反應是**撤回**，不是辯護。

**「被拒的那一次」與「從下一輪起」的完整語意**：

1. 第 N 輪帶明示對話識別碼（`LATCH_SOURCES` 六個 header 層之一，`guardrail_verdict_sink.py:51`）→ 路由跑完 → `run_admission` 拒絕 → 回 429/503/504。**這一輪的回應完全不受動作影響。**
2. 同一條路徑寫入一列 `policy_kind='llm_operational'` 的 latch（observe 時只記 `would_latch`）。
3. 第 N+1 輪同識別碼 → pre-filter 在 routing **之前**讀到 latch → 候選集與 failover 集都裁到核准範圍。
4. 第 N+1 輪**沒帶**識別碼：`per_turn` 什麼都不發生（request-local flag 在 post-decision 設置毫無意義）；`always_restrict` 視為已觸發（既有 read-side 規則）。

由此導出兩條 non-negotiable：**C-A** `trigger_timing = post_decision` 的 kind，其動作效果必定從下一輪起，C-292-42 的同輪收斂對它結構上不成立，契約與 Console 都必須明說；**C-B** `post_decision` 的動作只能靠 latch 生效，沒有明示對話識別碼就完全無效。

### 2.3 合成過程被推翻的八個宣稱（已折進本檔）

| # | 合成稿說 | 實際（實讀） | 對本檔的影響 |
|---|---|---|---|
| 1 | 「移除 `restrict_conversation_scope`、新增 `actions` 只是換一個 null 鍵，`content_hash` 不受影響」 | **錯**。`content` 存的是 `spec.model_dump()`（`validate_policy_content.py:288` → `_versioned_policies.py:1760-1761`），鍵名在 payload 裡，hash 必變（實測 `2560bc4d…` → `8c1e061f…`）。更硬的：`_StrictModel extra="forbid"` + resolver 對落盤 content 重新 parse（`guardrail_resolver.py:148-176` drift guard）→ 直接刪欄位會讓任何帶舊鍵的 row resolve 時 fail-closed。另外 C-292-33 管的是 `decision_evidence`，不是 wire spec；`schema.py:637-640` 與 `iam_http_client.py:373-376` 兩處註解把它外推成「snapshot byte-identical」是**過度宣稱**（snapshot 今天就多一個 `"restrict_conversation_scope": null`） | **PA-D17** coercion；SPEC 改寫 C-292-33 為三層區分；修兩處註解與 `test_absent_block_is_none_and_byte_identical_to_pre_adr459` 的測試名 |
| 2 | 「llm_operational 的拒絕事件有 concurrency / rate_limit / queue_timeout 三類，本設計只取前後兩者」 | **錯**。真 controller 只吐 `blocked / rate_limit / queue_overflow`；`"concurrency"` 分支是死碼（§2.2） | **PA-D3** 改為單一 `admission_rejected` |
| 3 | 「跨 kind fold 攤平 layer list 是一行改動」 | **錯**。兩個純函數可複用（`_merge_conversation_scope`、`expand_effective_scope`），但整條鏈綁 guardrail：fold 入口、`collect_kind_contributions(policy_kind="guardrail")`、`HttpGuardrailPolicyData`、`scope_spec_for` 的 mode 閘；且 `[selectors, *inherited_selectors]` 在非測試碼有**四處**副本（gateway ×2、IAM preview、IAM capabilities）+ 前端一處 | §3.4 / §8 的 PR 切片按實際工作量重估 |
| 4 | 「把 `record_policy_trigger` 留在 `guardrail_verdict_sink.py` 是因為 gate 規則 1/2/9 都 key basename」 | **部分錯**。規則 1/2 比 basename（gate `.py:57-58`），規則 9 走 `.sh:36` 寫死的**絕對路徑** `${GW}/guardrail_verdict_sink.py`。結論（檔案不搬則三條規則不動）成立，理由要寫對；`admission_handler.py` 今天完全沒碰 store／`GUARDRAIL_*` | §4.1 |
| 5 | 「describe 對只有 `actions` 的 llm_operational content 會把整包 JSON 印給使用者，今天零測試」 | **今天不會發生**：`actions` 不在 schema，寫入即 400；落盤 content 必有 `rate_limit` 鍵（`model_dump` 全欄位）。但**改造後**若 `describeLlmOperational` 的 consumed list（`policy-version-describe.ts:371-375`，今天 `["rate_limit","limits"]`）漏加 `"actions"`，`leftoverSection` 會把 `actions` 以一列 `JSON.stringify` 呈現——是「一列醜字串」不是「整包」；零測試覆蓋屬實 | §5.4 |
| 6 | 「Console 四處 hardcode `policy_kind: "guardrail"` 撈 scope preview，是靜默漏看」 | **今天不是缺陷**：只有兩處（`application/policies-tab.tsx:36`、`llm-proxy/policies-tab.tsx:37`），另兩個 dialog 走綁定回應、與 kind 無關；而今天 llm_operational 根本掛不上 action。改造後這兩處才需要跨 kind | §5.5 |
| 7 | 「`run_admission` / `admit_responses` 要改 def + 四個呼叫端」 | 生產呼叫端 **3 處 3 檔**（`routes/chat.py:1322`、`responses_admission.py:133`、`routes/responses.py:585`）；per-request carrier 已存在（`conversation_scope_state.py:22`），是「穿進 admission」不是「新增 carrier」 | §4.6 |
| 8 | 「effective-policy 的 guardrail 閘在 `:788 / :2747 / :2816`」 | `:788` 是 `_content_tags()`（列表 summary tag）；正確三處為 `:2713 / :2747 / :2816`，全在 `effective_policy_endpoint`。順帶：`replace_binding_endpoint`（`:2627-2656`）**不附 scope_preview 也不觸發 C-292-38 通知**——既有缺口 | §5.5、§7 |

另四條**確認**的硬事實：五處 consumer digest 必重釘（`ValidateSuccessResponse` 封閉 39 個 property，pin 是 `sha256(openapi 檔案 bytes)`，`test_iam_http_consumer_contracts.py:72`）；latch store 的 `PRAGMA user_version` 只寫不讀（`conversation_scope_store.py:55 / :251`），且 `__init__` 會無條件把它蓋成新值——加欄位後新 binary 讀舊檔 = 每個帶 session id 的請求 500；`buildConversationScope` 在 `enabled:false` 時 `return null`（`policy-content-form.tsx:564`）→ **今天 main 上一個關閉的 block 連同 API 授權的 models／credentials 一存檔就整個消失**；`max_queue_depth` 允許 0（`schema.py:200`，語意「0 = no queue, reject immediately」）→ depth=0 時 queue timeout 結構上不可達。

---

## 3. 概念模型與資料形狀

### 3.1 三層分解

```
Policy
 ├─ policy_kind : guardrail | llm_operational | <future>
 ├─ rules       : kind-specific（判定「命中了沒有」）   ← 與 kind 耦合，天經地義
 └─ actions     : kind-agnostic（決定「命中之後怎樣」） ← 與 kind 正交
       └─ 每個 action：type / requirement / enabled / triggers / params
```

每個 kind 用一張 **trigger registry** 描述自己能提供什麼觸發：

```python
# apps/iam/xparse_iam/xparse_iam/policies/policy_actions.py（新）
@dataclass(frozen=True)
class KindTriggerSpec:
    owner: str                     # "gateway"
    timing: str                    # "pre_routing" | "post_decision"
    reasons: frozenset[str]        # 該 kind 可撰寫的 trigger 值域
    default_enforcement: str       # "enforce" | "observe"  ← rollout 屬性，不進 content

TRIGGER_REGISTRY: dict[str, KindTriggerSpec] = {
    "guardrail": KindTriggerSpec("gateway", "pre_routing",
                                 frozenset({"guardrail_enforce_hit"}), "enforce"),
    "llm_operational": KindTriggerSpec("gateway", "post_decision",
                                 frozenset(),          # PA-D16：probe 綠才填 {"admission_rejected"}
                                 "observe"),
}
```

`reasons` 為空 ⇒ 該 kind 不得掛任何 gateway-owned action，write boundary 直接 400（PA-D10）。這是防 inert 的門閂，而且是**結構性的**：任何合併順序都不可能在 main 上出現「存得進去但永不觸發」的狀態。

**每 kind 的「觸發」定義**：

| kind | fires when（Console 逐字） | 生效時機 | 程式來源 |
|---|---|---|---|
| `guardrail` | 「這份政策的任一條防護規則在**強制**模式下遮罩或封鎖內容時。影子模式不會觸發。」 | 「命中的那一次請求就會生效。」（input rail `routes/chat.py:1071` 早於 routing `:1151`） | `_HIT_ACTIONS`、`verdict_is_hit`、`latch_mode == "enforce"`（`guardrail_verdict_sink.py:62/78/186`）；degraded 出口 `hit=False` 不觸發 |
| `llm_operational` | 「這份政策的速率／併發限制**拒絕了一次請求**時（429／503／504）。」 | 「從**下一次**請求起。被擋下的那一次已經回錯誤，沒有可以改的路由；只有客戶端帶了對話識別碼才會記住。」 | `controller.py:695/709` + `admission_handler.py:154/1244`；`_read_mode()` 恆回 `"enforce"`（`llm_operational_consumer.py:121-132`）——**這個 kind 沒有 shadow 軸**，所以需要 PA-D4 |

### 3.2 兩個 kind 的 policy content

**`guardrail`**（`PolicyVersion.content`）：

```json
{
  "version": "v2",
  "engine": "gliner_pii",
  "enabled": true,
  "mode": "enforce",
  "pii": { "enabled": true, "entities": ["email", "phone"], "action": "mask" },
  "word_filters": { "enabled": true, "terms": [] },
  "actions": {
    "restrict_conversation_scope": {
      "requirement": "mandatory",
      "enabled": true,
      "triggers": ["guardrail_enforce_hit"],
      "params": {
        "selectors": { "models": [], "credentials": [], "providers": ["vllm"], "serving_locality": [] },
        "idle_ttl_days": 30,
        "on_missing_conversation_id": "per_turn"
      }
    }
  }
}
```

**`llm_operational`**（同一個 action 元素，逐欄位相同）：

```json
{
  "rate_limit": { "req_per_sec": 5.0, "burst": 20, "max_concurrency": 4, "max_queue_depth": 50, "queue_timeout_sec": 30 },
  "limits": null,
  "actions": {
    "restrict_conversation_scope": {
      "requirement": "mandatory",
      "enabled": true,
      "triggers": ["admission_rejected"],
      "params": {
        "selectors": { "models": [], "credentials": [], "providers": [], "serving_locality": ["onprem"] },
        "idle_ttl_days": 30,
        "on_missing_conversation_id": "per_turn"
      }
    }
  }
}
```

形狀決定：

- **map 而非 array**（PA-D1）：fold 本來就以 `action_type` 配對；`extra="forbid"` 讓未知型別自然變 400；同型別掛兩次在型別層就不可能；Console describe 的 consumed list 永遠只有 `"actions"` 一個字串。
- `restrict_conversation_scope` **從 `GuardrailPolicySpecV2` 移除，不雙掛**（配 PA-D17 coercion 一個 release）。`RestrictConversationScopeSpec` / `ConversationScopeSelectorsSpec` 本體零改動，只改掛點；`inherited_selectors` 仍是 fold-only 欄位，authored 非空 → 400。
- `requirement`（PA-D8）借 XACML 3.0 Obligation／Advice 二分：`mandatory` 的 action gateway 不認得就 fail-closed（XACML §2.12：「required to deny access unless they understand and can discharge all of the Obligations」，對齊 ADR-093 #4）；`advisory` 記 warning 後忽略。v1 固定 `mandatory`。
- `actions` 缺席時 content 與改造前**逐位元相同**（沒有這個鍵就沒有這個鍵）；有 `actions` 的 content 當然 hash 不同——這是新內容，不是相容問題。

### 3.3 Validation（唯一入口 `validate_policy_version_content(policy_kind, content)`，`validate_policy_content.py:201`）

API（`_versioned_policies.py:1749`）與 GitOps（`versioned_sync.py:185`）共用它。新增 kind-neutral 的 `_validate_policy_actions(policy_kind, spec.actions)`，兩個 kind 分支各呼叫一次：

| # | 規則 | error code |
|---|---|---|
| R1 | `action_type` ∈ registry（`extra="forbid"` 自然產生） | `UNKNOWN_POLICY_ACTION` |
| R2 | `action_type` ∈ `ACTION_TYPES_BY_KIND[policy_kind]` | `POLICY_ACTION_NOT_APPLICABLE_TO_KIND` |
| R3 | `triggers` 非空且每個值 ∈ `TRIGGER_REGISTRY[kind].reasons`；**錯誤訊息列出這個 kind 實際提供哪些** | `POLICY_ACTION_TRIGGER_NOT_AVAILABLE` |
| R4 | `reasons` 為空 → 該 kind 不得掛任何 action（PA-D10） | `POLICY_KIND_HAS_NO_TRIGGER` |
| R5 | conversation-scope：四個 matcher 不得同時為空（原 C-292-1） | `INVALID_POLICY_ACTION_CONVERSATION_SCOPE` |
| R6 | conversation-scope：authored `inherited_selectors` 非空（D15） | 同上 |
| R7 | conversation-scope：`idle_ttl_days ≤ 365`（capability） | 同上 |
| **R8** | **可達性**：`llm_operational` 掛 action 但 `rate_limit` 為 `null` → 沒有 admission 決策可觸發 | `POLICY_ACTION_TRIGGER_UNREACHABLE` |
| R9 | 舊鍵 coercion（PA-D17）：`restrict_conversation_scope` 為 `null` → 丟棄；非 null → 搬進 `actions`；與 `actions.restrict_conversation_scope` 並存 → 400 | `POLICY_ACTION_DUPLICATE_LEGACY_KEY` |

R3 + R4 + R8 把 §8.1「在能指出真元件確實會產生該 trigger 之前不得視為完成」**前移到 authoring 時刻**。error code 一律 kind-neutral（今天是 `INVALID_GUARDRAIL_CONVERSATION_SCOPE`）。HTTP status **維持 400**（PA-D11）。

> **R8 的射程限制（誠實）**：它是 authoring-time 檢查，而 INV-259-1 讓 active content 不可改。若之後的版本移除 `rate_limit`，較早那個仍在生效的版本的 action 會靜默變成不可達。補救是 resolve-time 非致命偵測（§4.6），不是再加 authoring 規則。（合成稿另有一條 `queue_timeout × max_queue_depth == 0` 的規則；PA-D3 合併 trigger 後不再需要，但 `max_queue_depth = 0` 讓 504 不可達這個事實留在 SPEC 註記。）

### 3.4 Fold

**kind 內**：`_merge_conversation_scope`（`guardrail_policy_merge.py:192`，函式體零 guardrail 依賴）抽成共用 `policies/actions_merge.py::merge_policy_actions()`，由 `tighten_merge_guardrail`（`:486`）與 `llm_policy_merge.tighten_merge`（`:86`）**各呼叫一次**。兩個 lattice 既有方向（guardrail tighten / llm_operational min-wins）一行不動；ADR-259 §2.1 #8「fold once per kind」完整成立。以 `action_type` 為鍵：

| 欄位 | 折法 |
|---|---|
| `enabled` | OR |
| `triggers` | 聯集（多一個觸發來源＝更容易觸發＝更嚴） |
| `requirement` | `mandatory` wins |
| `params.selectors` | 交集，寫成 CNF（子層留 `selectors`、祖先層推 `inherited_selectors`；D15 原封） |
| `params.idle_ttl_days` | max-wins |
| `params.on_missing_conversation_id` | strictest-wins（`always_restrict` 勝） |

`_downgrade_if_v1_only`（`:416`）改讀 `actions`。

**跨 kind（PA-D9）：全部交集，且只計入實際被觸發的 kind。** 兩個理由缺一不可：(1) INV-459-8 已定死「子 scope 不得放寬父 scope」，多掛一份治理控制只能收緊，聯集會讓一份寬鬆的 llm_operational action 稀釋既有 guardrail 管制；(2) 沒被觸發的 policy 不該產生任何約束，否則「綁上第二份 policy」本身就縮小了所有對話的可用模型。

**Peter 問的那一題**：tenant 的 guardrail policy 核准 `providers: ["openai"]`，application 的 llm_operational policy 核准 `serving_locality: ["onprem"]`：

| 本輪觸發狀態 | 有效範圍 |
|---|---|
| 都沒觸發 | 不限縮（pre-filter 惰性，零 `conversation_scope_*` 鍵） |
| 只有 guardrail 觸發過 | OpenAI 的模型 |
| 只有 llm_operational 觸發過 | 地端模型 |
| 兩個都觸發過 | OpenAI ∩ 地端 = **常常為空 → 400 `conversation_scope_empty`** |

最後一列是本設計最大的可用性風險，所以 §5.5 的跨 kind 三列預覽**必須與跨 kind fold 同一切片交付**。契約性質要寫進 SPEC：**有效範圍是 `policy × 觸發歷史` 的函數，不是 policy 單獨的函數**。

### 3.5 Wire（PA-D5）

IAM validate 回應新增**頂層**鍵，與 `guardrail_kind_policy`、`llm_operational_policy` 平行；`restrict_conversation_scope` 從 `guardrail_kind_policy.spec` 消失：

```jsonc
"policy_actions": {
  "restrict_conversation_scope": {
    "action_id": "restrict_conversation_scope",
    "requirement": "mandatory",
    "idle_ttl_days": 90,                              // max across sources
    "on_missing_conversation_id": "always_restrict",  // strictest across sources
    "sources": [
      { "policy_kind": "guardrail", "trigger_timing": "pre_routing", "enforcement": "enforce",
        "triggers": ["guardrail_enforce_hit"], "policy_code": "tenant-pii", "policy_version": "2026.09.16.1",
        "bundle_uuid": "…", "resolved_from": "tenant",
        "layers": [ {"models": [], "credentials": [], "providers": ["openai"], "serving_locality": []} ] },
      { "policy_kind": "llm_operational", "trigger_timing": "post_decision", "enforcement": "observe",
        "triggers": ["admission_rejected"], "policy_code": "shared-capacity", "policy_version": "2026.09.16.1",
        "bundle_uuid": "…", "resolved_from": "application",
        "layers": [ {"models": [], "credentials": [], "providers": [], "serving_locality": ["onprem"]} ] }
    ]
  }
}
```

四個理由：gateway 不做 fold、也不列舉 kind（巢狀方案下 gateway 要逐一點名 `[guardrail_kind_policy, llm_operational_policy]`，正是要拆的耦合）；evaluator 已吃扁平 layer list；每個 source 帶 kind + code + version 才答得出「是哪一份 policy 把這段對話鎖住」；`LLMOperationalPolicySpec` 沒有 version discriminator，巢狀新欄位會被舊 gateway 靜默丟掉，頂層新鍵則是「舊 gateway 看不到 ⇒ 惰性」。

**代價（明碼）**：`openapi.v1.json` bytes 改變 → 五處 consumer artifact 同 PR 重釘（`frontend/console-app-refactor/contracts/iam-http.consumer.v1.json`、`apps/{gateway/bustream/gateway,fleet/fleet,node-agent/xparse_node_mgr}/contracts/iam-http.consumer.v1.schema.json`、`apps/scheduler/contracts/iam-admission.consumer.v1.schema.json`），IAM 與 gateway image 同批部署。

**Capability 契約 v1 不搬**（PA-D13）：`restrict_conversation_scope` 的上限（`selector_kinds` / `serving_locality_values: ["onprem","cloud"]` / `on_missing_conversation_id: ["per_turn","always_restrict"]` / `max_idle_ttl_days: 365`）住在 guardrails owner，IAM 以 `source_sha256` 消費（`contracts/guardrails-policy.consumer.v1.json:6`）。概念上 owner 錯了（sidecar 根本不評估這個 action），但跨 owner 以 pinned artifact 消費是 ADR-418 允許的模式；搬動要踩 PRD-302 M5 guard，收益零行為改變。

---

## 4. Gateway 落地

### 4.1 Trigger sink 一般化——不搬檔、不改名

`guardrail_verdict_sink.py` 保持原檔名原位置：gate 規則 1/2 比 basename（`.github/scripts/conversation-scope-layer-gate.py:57-58`），規則 9 走 `.sh:36` 寫死的路徑；檔案不動則三條規則零 churn。在同檔內把 latch 副作用（`:186-208`）抽成公開函式：

```python
@dataclass(frozen=True)
class PolicyTriggerRef:
    policy_kind: str            # "guardrail" | "llm_operational"
    policy_ref: str             # bundle_uuid
    policy_version: str | None
    trigger_timing: str         # "pre_routing" | "post_decision"

def record_policy_trigger(*, ref: PolicyTriggerRef, action_id: str, trigger: str,
                          enforcement: str, scope, now=None) -> dict:
    """enforce → latch（有明示對話 id）+ request-local 旗標；observe → 只回 would_latch。回傳 audit decorations。"""
```

`record_guardrail_verdict(...)` 變成它的 guardrail adapter：算出 `hit` / `trigger` / `PolicyTriggerRef` 後呼叫，拿回 decorations 再 emit。既有五個出口、byte-identical payload 承諾（Rev.4 G9）與 `trigger` 字串格式（`"pii:input"`，`test_spec292_conversation_scope_contracts.py:481,490` 釘住）不變。**誠實標記**：`admission_handler` 之後會從一個叫 `guardrail_verdict_sink` 的模組 import `record_policy_trigger`，名字讀起來是錯的；模組 docstring 寫明，改名列 tracking issue（PA-D13）。注意 `admission_handler.py` 不得 import store 模組（gate 規則 2），store 實例一律走 carrier `scope.store`。

### 4.2 Action executor registry 與 fail-closed

```python
POLICY_ACTION_EXECUTORS = {"restrict_conversation_scope": ConversationScopeExecutor()}
```

boundary entry（carrier 建立處 `routes/chat.py:1015` / `responses_routing.py:150`）檢查 `auth_context.policy_actions` 的每個 `action_id`：不認得且 `requirement == "mandatory"` → 拒絕並發 audit；`advisory` → warning 後忽略。v1 唯一新增的 fail-closed 路徑，也是 action #2 的前向相容保證。

### 4.3 Latch 列（PA-D7）

```sql
CREATE TABLE IF NOT EXISTS conversation_scope_latch (
  key TEXT NOT NULL,            -- sha256(tenant|application|session_id)，維持三段
  action_id TEXT NOT NULL,      -- 新
  policy_kind TEXT NOT NULL,    -- 新
  policy_ref TEXT,              -- 新：bundle_uuid，只做診斷
  latched_at REAL NOT NULL, last_seen_at REAL NOT NULL, expires_at REAL NOT NULL,
  trigger TEXT NOT NULL,
  PRIMARY KEY (key, action_id, policy_kind))
```

- key material 仍三段（`conversation_scope_store.py:105-116` docstring：三段保證與 ADR-447 六段永不碰撞）；kind 進欄位不進 key。
- **per-kind 一列**：沒有這欄，llm_operational 的觸發會去啟動一份從未被觸發的 guardrail policy 的 selectors。
- 不存 scope（D9 原封）：效果每請求依當下 policy 重算。
- `policy_ref` 讀端不比對：比對的話管理員換一份 policy 就等於偷偷釋放所有進行中的限制。
- **`PRAGMA user_version` 必須真的讀回**：今天只寫不讀，且 `__init__` 無條件蓋成新值，抹掉唯一可偵測漂移的訊號。加欄位後若新 binary 讀舊檔 → `OperationalError` → `ConversationScopeStoreError` → 每個帶 session id 的請求 500。**同 PR 補讀回 + 不相容時開機 fail-fast。**

### 4.4 Pre-filter 與 evidence

`scope_spec_for`（`:160-175`）改為 `policy_action_sources_for(auth_context, *, action_id, guardrail_effective_mode)`：從頂層 `policy_actions` 讀；guardrail source 沿用既有 G5 四條閘一字不改；llm_operational source 的 `enforcement` 來自 wire。`resolve_conversation_scope` 對每個 source 的 `(key, action_id, policy_kind)` 各查一次 latch，`triggered` 的才進 `layers`；`expand_effective_scope` 攤平成跨 source（`:129` 一行），交集迴圈與 `scope_check` 不動——但要記得 `[selectors, *inherited_selectors]` 有四處副本 + 前端一處要同步（§2.3 #3）。

**Evidence（PA-D6）**：七鍵全留，新增第八鍵 `conversation_scope_sources`：

```json
[{"kind":"guardrail","ref":"…","version":"…","triggered":true,"source_present":true},
 {"kind":"llm_operational","ref":"…","version":"…","triggered":true,"source_present":false}]
```

`source_present: false` = 有一列活著的 latch，但這個 kind 已不在 wire 上貢獻 layer——這是 policy 被解綁後**跨 kind 部分放寬**的可觀測記號（放寬是正確行為：解綁必須立刻釋放它的控制，D9 原則；但必須可觀測）。第八鍵必須同 PR 改 `routing_decision.py:77-85` 與 gate `EVIDENCE_KEYS`（`.py:67-75`，規則 7 在 `:251` 是 `set != set` 精確比對，dogfood 已對 seeded 第八鍵變紅）。

### 4.5 Kill switch 與文案

`XPARSE_CONVERSATION_SCOPE` / `XPARSE_CONVERSATION_SCOPE_DB_PATH` 不改名（改名要重產 `runtime.schema.json`、動 tier compose 與 host `.env`）。改的是**文字**：`REJECTION_MESSAGES` 三則今天逐字「after a guardrail verdict」——llm_operational 觸發後的 400 會告訴客戶「你踩到 guardrail」。新文案：「這段對話在觸發政策管制後被限制在一組核准的模型內，目前沒有任何一顆可用。請開新對話，或請管理員放寬核准範圍。」`responses_chain_validator._MESSAGES` 同步（gate 規則 6）。`_log_inert_once` 的 marker 改成 `(policy_kind, bundle_uuid)`。

### 4.6 llm_operational adapter 與 resolve-time 可達性

- 既有 carrier `ConversationScopeRequestState`（`conversation_scope_state.py:22`）穿進 `run_admission`（def `admission_handler.py:936-949`）與 `admit_responses`（`responses_admission.py:105-113`）；生產呼叫端 3 處 3 檔（`routes/chat.py:1322`、`responses_admission.py:133`、`routes/responses.py:585`）。三個拒絕分支（`:1139` rate_limit、`:1143` queue_overflow、`:154/:1244` queue_timeout）接 `record_policy_trigger(trigger="admission_rejected:<reason>")`。
- `llm_operational_resolver` 在 fold 之後、組 wire 之前，檢查每個 authored trigger 對折後的 `rate_limit` 是否可達；不可達時**不擋請求**，把該 source 從 `policy_actions` 剔除並發 `iam.policy_action.trigger_unreachable`（沿用 `conversation_scope_empty` 的告警管道與 24h dedupe）。

### 4.7 靜態 gate 與 §8.1 真元件 probe

| 規則 | 動作 |
|---|---|
| 1／2／3／4／5／6／9／10 | **不動**（sink 留原檔；admission_handler 不 import store；pre-filter 順序、Responses、訊息 code、`LATCH_SOURCES`、`registry=` 皆不變） |
| 7（`EVIDENCE_KEYS` 精確集合） | **改**：+1，獨立 PR |
| 8（rail entry point 帶 `conversation_scope=`） | **擴**：新增 admission entry point 同型檢查 |
| **新 11** | IAM 的 `TRIGGER_REGISTRY` 與 gateway 鏡射常數逐字相同（跨 owner 不得 import，一致性放 `.github/scripts`） |
| **新 12** | `reasons` 非空的每個 kind 必須有對應 adapter 呼叫點——registry 加了 kind 卻沒呼叫點就紅 |
| **新 13** | store `get`/`latch` 呼叫點必須帶 `action_id=` 與 `policy_kind=` |

`GATE-TRACK` marker 兩處（`.sh:19` + `ci.yml:541-545`）同步；每條新規則先看到對 seeded regression 變紅才算數。

既有三個 probe（`test_spec292_conversation_scope_contracts.py:276 / :372 / :449`）全保留，新增三條，**缺一不得宣稱完成**：

- **(d)** 用**真的** admission controller（`max_concurrency=1`、`max_queue_depth=0`）讓真 `run_admission` 吐出真的 `rate_limit` 拒絕，斷言 latch 真的多一列 `(key, "restrict_conversation_scope", "llm_operational")`。**禁止**用會 raise 的 fake controller（#1025 同型）。
- **(e)** 第 N 輪被拒之後，第 N+1 輪同 session id 進來，斷言真 `_route_via_routing_module` 的 winner ∈ `expanded`。這是「從下一輪生效」的唯一證據。
- **(f)** 兩個 kind 都帶 action、只有 guardrail 觸發時，llm_operational 的 layer **不得**參與交集。釘的是 fold 的**選擇**語意。

probe (d) 做不出來 ⇒ `TRIGGER_REGISTRY["llm_operational"].reasons` 保持空集合，IAM 對它一律 400，Console 灰掉並說明理由。**這個設計的失敗模式是「擋在 write boundary」，不是「綠燈儀式下的 inert 功能」。**

---

## 5. Console UI

### 5.0 可點的原型

本節的 wireframe 有一份可操作的原型（純前端 mockup，假資料，機器字串取自真實程式碼）：https://claude.ai/artifact/49zjPN1kiJVS47JBtH2A8g（Claude Artifact「政策觸發後動作」，私有，可由頁面分享）。原型能切換 kind、新增／移除動作卡、看 review 步驟的 describe 列、看即時組出的 content JSON、以及套用後的三列預覽。

### 5.1 區段位置——以及明確排除的兩個方向

`create-policy-dialog.tsx` 的 identity 欄位（名稱／版本／說明／指派）在 `<Tabs>` 裡面但在 `<TabsContent>` 外面——已證明這個位置對兩個 kind 都渲染。「觸發後動作」插在兩個 `<TabsContent>`（`:717-726`）之後、`</Tabs>` 之前。`create-policy-version-dialog.tsx` 插在左欄三元分支（`:296-310`）之後。`edit-policy-dialog.tsx` 只編 metadata（ADR-337 content 不可變），不動。

| 排除的方向 | 為什麼 |
|---|---|
| 第三個頂層 tab「動作」 | `<Tabs value={policyKind}>` 的 value 就是 `policy_kind` 且直接寫進 payload；加第三個值等於在 kind 值域裡塞非 kind（§18.2）。而且它把「動作屬於這份 policy」的關係切斷 |
| per-rule inline action（LiteLLM／Portkey 式，每條 rail 旁邊放 on_flagged） | rail 是 guardrail 專屬概念，llm_operational 沒有 rail；且會把 `guardrail_verdict_sink.py` 剛合併掉的五個出口重新拆開。LiteLLM 這條路的下場是 14 個 `on_flagged*` 名字值域互相打架、class 宣告掛 `pyright: ignore`（§6） |

### 5.2 Wireframe——空狀態

區段 `defaultExpanded={actions.length > 0}`，未加動作時只佔一行；區段**不帶 toggle**（`PolicyConfigSection` 的 toggle 會套 `<fieldset disabled>` 把整段變灰，`policy-config-section.tsx:114-121`），「有沒有動作」由清單長度表達。

```
┌ 建立新政策 ─────────────────────────────────── 步驟 1/2 · 設定 ─┐
│  ┌ 防護規則 ─┬─ 運行規則 ─┐        ← Tabs（value = policy_kind） │
│  └───────────┴────────────┘                                      │
│  名稱 *   [____________]   版本 [ 2026.09.16.1 ]                 │
│  說明     [_______________________________]                      │
│  指派給   [ 群組：研發部 ▾ ]     層級 [ 租戶 ▾ ]                  │
│  ─────────────────────────────────────────────────────────────  │
│  ▸ 防護   ▸ PII   ▸ 自訂詞過濾   ▸ 內容過濾   ▸ 主題限制          │
│                                        ← 依 kind 變形的「規則」  │
│  ─────────────────────────────────────────────────────────────  │
│  ▾ 觸發後動作                                           尚未新增 │
│     規則決定什麼算違規；動作決定違規之後做什麼。                   │
│     ┌──────────────────────────────────────────────────┐        │
│     │ 尚未加入任何動作。這條政策被觸發時只會留下稽核紀錄，│        │
│     │ 不會改變後續請求。                                 │        │
│     └──────────────────────────────────────────────────┘        │
│     [ ＋ 新增動作 ]                                              │
│                                        [ 取消 ]  [ 下一步 → ]    │
└──────────────────────────────────────────────────────────────────┘
```

「＋ 新增動作」**即使只有一個選項也是 picker**——它的存在本身就是「可擴充、跨 kind 共用的目錄」的視覺承諾。v1 照既有紀律（`create-policy-dialog.tsx:391-393`：「a one-option control the author must still open reads as a bug」）渲染成一顆 outline 按鈕，按下直接加入唯一那張卡；第二個型別出現時換成可搜尋的 `DropdownMenu`，外框零改動。已掛上的型別從候選移除。

### 5.3 Wireframe——動作卡

```
│  ▾ 觸發後動作                                          已新增 1 項 │
│  ┌ 對話範圍限縮 ──────────────────────────  [ 啟用 ●] [ ✕ ] ┐    │
│  │ 觸發後，這段對話接下來只會用你核准的供應商。             │    │
│  │ ────────────────────────────────────────────────────── │    │
│  │ 何時觸發     這份政策的任一條防護規則在「強制」模式下     │    │
│  │              遮罩或封鎖內容時。影子模式不會觸發。         │    │
│  │ 生效時機     命中的那一次請求就會生效。                   │    │
│  │ 目前狀態     ✔ 生效中（這份政策目前為「強制」模式）       │    │
│  │ ────────────────────────────────────────────────────── │    │
│  │ 核准的供應商 *  [ OpenAI ✕ ] [ vllm ✕ ]      [ ＋ 選擇 ] │    │
│  │   ⓘ 核准一個供應商，等於核准它底下所有模型，             │    │
│  │      包括你存檔之後才登記的模型。                         │    │
│  │ 沒有工作階段 ID 時  ( ) 只限縮這一輪  (•) 一律限縮        │    │
│  │ ────────────────────────────────────────────────────── │    │
│  │ ⓘ 這個動作必須被履行：閘道不認得它就會拒絕請求。         │    │
│  └────────────────────────────────────────────────────────┘    │
```

`llm_operational` 時只有三塊不同：

```
│  │ 何時觸發     [✓] 這份政策的速率／併發限制拒絕了一次請求   │
│  │              （429／503／504）                            │
│  │ 生效時機     從下一次請求起。被擋下的那一次已經回錯誤，   │
│  │              沒有可以改的路由。只有客戶端帶了對話識別碼   │
│  │              時才會生效。                                 │
│  │ 目前狀態     ◐ 觀察模式：只記錄會限縮誰，不真的限縮。     │
```

三層分工的理由：**效果**是 action 型別的屬性（哪個 kind 觸發結果都一樣）；**何時觸發**與**生效時機**是 kind × action 的交叉屬性；**目前狀態**是 authored 值與外部狀態 AND 之後的結果（guardrail 顯示「✔ 生效中／◌ 不生效（影子模式）」，必須把政策自己的 mode 寫在同一行——它住在同一個對話框的另一個區段，使用者不會自己對照）。今天的 `conversationScopeDescription` 把前兩者焊死成「防護規則擋下或遮罩過內容之後…」，action 一掛到 llm_operational 這句話就是假的。

四個 UX 決定，各防一種不誠實：(1) trigger 是顯式勾選，不由 kind 隱含；(2) 未來若某個 trigger 對某 kind 不可選，**留在畫面上並附理由**，不消失（對位 Bedrock 的 `ANONYMIZE` 只對 PII 有效、Foundry 的「Some intervention points will not be available for a risk if inapplicable」）；(3) 生效時機是固定渲染的一等欄位，不是 tooltip；(4) `rate_limit` 整塊關閉時 picker 裡的動作直接灰掉並附理由（R8）。「何時觸發」「生效時機」的句子從 `policies.actions.trigger.<kind>.<trigger>` / `policies.actions.timing.<timing>` 的 i18n 查表取得，`timing` 由 registry 導出，不手寫——第三個 kind 進來時它自動仍為真。

### 5.4 Describe／Review（三處共用 `describeVersionContent()`）

```
觸發後動作
  對話範圍限縮              觀察模式
  何時觸發                  限制拒絕請求時
  生效時機                  從下一次請求起
  核准的供應商              OpenAI、vllm
  沒有工作階段 ID 時        一律限縮
```

必改三處：`describeConversationScope()`（`policy-version-describe.ts:117-173`）改回傳自己的 section「觸發後動作」，不再塞進 protection rows；`describeGuardrailV1V2` 與 `describeLlmOperational` 兩條分支各 append `describeActions()`；**兩條分支的 consumed list 都加 `"actions"`**（漏了會出現一列 `JSON.stringify` 醜字串，零測試覆蓋，PR 必附兩條 `policy-version-describe.test.ts` case）。dispatch 改由呼叫端傳 `policyKind`（三個呼叫端都拿得到），shape 猜測（`:409`）降為 legacy fallback。

### 5.5 綁定預覽必須跨 kind，而且要顯示組合

```
┌ 套用後的可用模型 ───────────────────────────────────────┐
│  應用：客服機器人                                        │
│  防護規則「個資稽核」觸發時          →  12 顆可用         │
│  運行規則「共享容量」觸發時          →   8 顆可用         │
│  兩者都觸發過時                     →   0 顆可用   ⚠     │
│  ⚠ 兩個動作的範圍沒有交集。若這段對話先後被兩條政策觸發， │
│    後續請求會被拒絕（400 conversation_scope_empty）。     │
│  ⓘ 只預覽前 500 個應用，其餘未檢查。                      │
└──────────────────────────────────────────────────────────┘
```

IAM 側 `preview_for_application`（`conversation_scope_preview.py:104-128`）跨 kind 化；`effective_policy_endpoint` 的三個 kind 閘（`_versioned_policies.py:2713 / :2747 / :2816`）拆掉；Console 兩處 `policy_kind: "guardrail"` hardcode（`application/policies-tab.tsx:36`、`llm-proxy/policies-tab.tsx:37`）改掉。`truncated_after`（payload 已有，Console 已渲染）維持。順帶修兩個既有缺口：`replace_binding_endpoint` 不附 scope_preview 也不觸發 C-292-38 通知；recompute 路徑截斷時只寫 log 不進 payload。

### 5.6 i18n 與譯名

24 個 `policies.contentForm.conversationScope*` key 搬到 `policies.actions.restrictConversationScope.*`；新增 kind 無關的 `policies.actions.{title,description,empty,add,remove,typeLabel,triggerLabel,timingLabel,statusLabel,requirementNote}` 與 kind-dependent 的 `policies.actions.trigger.<kind>.<trigger>`、`policies.actions.timing.<timing>`。**先改 glossary 再改 catalog**（`scripts/i18n-glossary-conformance.mjs` 是唯一看得到「翻錯」的 gate）：

| 英文 | 中文 | 備註 |
|---|---|---|
| Policy action（新頂層概念） | **觸發後動作** | 較長的名字才與下一列分得開 |
| Action（word-filter 每列，既有） | **動作** | 不動；同一張表單不能有兩個層級不同的「動作」 |
| Trigger | **觸發** | |

### 5.7 前端六個必踩陷阱

1. `policy-actions-section.tsx` **必須是獨立檔**：`moderation-credential-field.test.tsx` 會讀 `policy-content-form.tsx` 原始碼並斷言「exactly one Popover」。抽 `<ConversationScopeFields>` 時 `<Popover modal>` 的 `modal` 不能掉——沒有它 Radix Dialog 裡的清單畫得出來但點不到，jsdom 測不出。
2. `ConversationScopeFormState` 從「扁平前綴 + `GuardrailFormState extends`」（`policy-content-form.tsx:105`）改成巢狀放進 `PolicyActionFormState.conversationScope`；三個純函數簽章原封。
3. version dialog 的 `handleActionsChange` 必須 `setContentTouched(true)` + `setPrefillError(null)`，否則 prefill effect（`:150-165`）會在比對版本載入時洗掉使用者剛編的動作；prefill 拆兩段（kind-specific `*FromContent` + kind 無關 `actionsFromContent`）。
4. `hidden` 屬性打不過 Tailwind display class：用 `cn(..., cond && "hidden")` 或條件 render。
5. i18n gate per-file：`policies/_components/policy/**` 已在 `I18N_ENFORCED_PATHS` 與 `ENFORCED_GLOBS` 內，新檔自動受八條規則管；改完跑 `node scripts/i18n-hardcoded-text.mjs --import-leaks`。
6. 改 `zh-TW.json` 就要重產 acceptance workbook，**PR squash 進 main 之後從 main tip 單獨一個 PR**（#4903 → #4909 教訓）。
7. **卡片自帶「啟用」開關**：card 存在 ⇒ key 存在，開關值 ⇒ `enabled`；`enabled:false` 的 API／GitOps 內容渲染成關閉狀態的卡並原樣存回。這比今天嚴格更好（今天 `enabled:false` 一存檔整個消失，§2.3）。
8. 唯讀角色走 `describeActions` 的檢視路徑，不得渲染可互動的 picker。

### 5.8 第二種 action 型別怎麼進來而不動框架

框架是：**區段 → 卡片清單 → 每張卡〔型別名／效果句／何時觸發／生效時機／目前狀態／requirement／參數〕**。新增一個型別只需要：registry 加一筆（`defaultState` / `isEmpty` / `buildWire` / `fromWire` / `i18nPrefix` / `applicableKinds`）、一組 i18n key、一個參數表單元件。區段、對話框、review、describe、預覽的形狀都不改。

---

## 6. 業界對照（一手來源；完整證據表待 `/research` 產 RESEARCH pack）

| 產品 | trigger kinds | action 語彙 | action 與 kind 正交？ | 跨輪有狀態？ | 來源 |
|---|---|---|---|---|---|
| **LiteLLM proxy（2026-09-14 快照）** | 各家 vendor guardrail | 每家一套 `on_flagged` / `on_flagged_action`（14 個名字，值域互打，`types/guardrails.py:1057` 掛 `pyright: ignore … on_flagged literal diverges across mixins`）；policy engine 的 `Policy` 只有 guardrails add/remove + scoping，**沒有 action 欄位**（`policy_types.py:170`） | ❌ action 塞在每個 check 的設定裡 | **⚠️ 有，且是最接近的先例**：`on_sensitive_data: "route"` + `sensitive_data_route_to_model` + `sticky_session_routing`（`types/guardrails.py:977-995`），狀態存 DualCache `{sensitive_route:<tenant>:<session_id>}:model`、TTL 3600（`proxy/hooks/sensitive_data_routing.py:32-55`）。差異：它是**單一 guardrail 的設定**、指向**一顆**模型、走 exception 旁路（`SensitiveDataRouteException`，policy engine 不參與）、沒有 session id 時降級成 block | 本機快照 |
| | | `content_policy_fallbacks` 的觸發是 **provider** 的 `ContentPolicyViolationError`，方向是**放寬**（丟給另一個 model group），而且「有 fallback 才 raise、沒配就原樣回被擋的回應」（`router.py:8485-8487`）——fail-open | | | |
| **Portkey OSS gateway** | 任何 check（含純 operational 的 `modelRules` / `jwt` / `requiredMetadataKeys`，manifest 裡 type 全標 guardrail） | action 全在 `HookObject`（policy 信封）上：`deny` / `onFail` / `onSuccess` / `async`（`src/middlewares/hooks/types.ts:17-27`）；check 型別層無法攜帶 action（`plugins/types.ts:13-20`）；`deny` 的計算在 MUTATOR/GUARDRAIL 分支之外（`hooks/index.ts:439-443`） | **✅ 天生正交**——Portkey 無意間證明了 action 機制與 kind 無關 | ❌ per-request、每個 target attempt 獨立 | 本機快照 |
| | | 反例：`plugins/portkey/pii.ts:147-158` 的 check 參數 `redact` 直接把 verdict 翻成通過，policy 層勾的 `deny` 永遠不觸發——**action 洩進 check 參數導致 policy 層設定靜默失效** | | | |
| | | 修正 PRD-325 研究：fallback target **會**繼承父層 hooks（override-on-redeclare，`handlerUtils.ts:604-624`），組織級 default guardrails 無條件下灌（`:638-643`） | | | |
| **Google CX Agent Studio Guardrail** | `contentFilter` / `llmPromptSecurity` / `llmPolicy` / `modelSafety` / `codeCallback`（oneof） | `action: TriggerAction`（`respondImmediately` / `transferAgent` / `generativeAnswer`）**站在 oneof 之外**，UI 叫「Outcomes」 | ✅ | ⚠️ `transferAgent` 轉移整段對話，持久語意未查證 | docs.cloud.google.com/gemini-enterprise-cx/cx-agent-studio/reference/rest/v1/projects.locations.apps.guardrails |
| **XACML 3.0** | 任何 Rule / Policy | `ObligationExpression` / `AdviceExpression`，只 key `FulfillOn`（Permit／Deny） | ✅ 形式上的先例；PEP 不能履行 Obligation 就必須 deny | ❌ | docs.oasis-open.org/xacml/3.0/xacml-core-v3-schema-wd-17.xsd |
| **AWS Bedrock Guardrails** | 六種 policy | `inputAction` / `outputAction`：`BLOCK` / `ANONYMIZE` / `NONE` | ⚠️ 同名欄位跨六種；`ANONYMIZE` 只對 PII 有效——**不適用者灰掉不分家** | ❌ | docs.aws.amazon.com/bedrock/latest/APIReference/API_CreateGuardrail.html |
| **Azure AI Foundry Guardrails** | risk × intervention point | `Annotate` / `Annotate and block` | ✅ 三元組正交；「Some intervention points will not be available for a risk if inapplicable」 | ❌ | learn.microsoft.com/azure/foundry/guardrails/how-to-create-guardrails |
| **Kong AI Gateway** | 每個 plugin 一種 | 無共用語彙：400／403／429 各自寫死 | ❌ | ❌ | developer.konghq.com/plugins/ai-prompt-guard/ |
| **Kyverno** | validate / mutate / generate | `failureAction` 只屬 `validate` | ❌ action 隨 rule type 改形狀——走這條路 llm_operational 永遠碰不到 action | ❌ | kyverno.io/docs/policy-types/cluster-policy/validate/ |
| **Sentry Issue Alerts** | issue-state triggers | 共用 action 目錄 | ✅ 「**Actions run when triggers and filters match.**」 | n/a | docs.sentry.io/product/alerts/create-alerts/issue-alert-config/ |

**observe-only 檔位是通例**：Bedrock `NONE`、Cloudflare `Flag`、Model Armor inspect-only、Kyverno `Audit`、GitHub rulesets `Evaluate`、Foundry `Annotate`、LiteLLM `logging_only`。PA-D4 因此不是新發明，只是把它放在 registry 而不是 authored 欄位。

**借什麼、不借什麼**：借 Sentry 的那一句句型（「規則決定什麼算違規；動作決定違規之後做什麼」）、Google CES 的「action 在 kind union 之外」schema 形狀、XACML 的 Obligation／Advice 二分、Bedrock／Foundry 的「不適用者灰掉並說明」；不借 LiteLLM 的 per-vendor `on_flagged`、不借 Portkey 讓 check 參數翻 verdict、不借 Kyverno 讓 rule type 決定 action 形狀。

---

## 7. 文件落地

### 7.1 要改的既有文件

| 文件 | section | 動作 |
|---|---|---|
| **ADR-459** | 標題／§1.2／§2.1 #1 | 「Guardrail Action」→「Policy Action」（檔名保留舊 slug）；「rails 不能知道路由、resolver 不能知道 guardrail」→「…不能知道 policy」；§2.1 #1 改成「任何 kind 的 content 都可攜帶 `actions` map」 |
| | §2.1 #2／§2.2.9（D14） | 標記為 **guardrail trigger adapter 契約**，非通則 |
| | §2.2.1／§2.2.2 | code block 換 `PolicyActionsSpec` + 兩個 kind 掛點，**422 改 400**；latch DDL 換複合 PK + `user_version` 讀回 |
| | §6 INV-459-1 | 前半（唯一出口）降為 guardrail adapter；後半（store importer 閉集）維持；INV-459-2..13, 15 原文不動 |
| | §7.2／§8／§9 | rollout 補 llm_operational 半邊與部署序；Supersede Chain 加「Amended by ADR-461」；Rev.6 |
| **SPEC-292** | C-292-1 | 型別路徑改 `actions["restrict_conversation_scope"].params`；422 → 400 |
| | C-292-3／C-292-4／C-292-12／40／41／42 | fold 一般化 + 跨 kind 交集；capability 檔維持 owner 只改述語；12/40/41 標 guardrail adapter；42 補「只對 `pre_routing` 成立」 |
| | C-292-32／33／38／39 | 七鍵 → 八鍵；33 改寫成三層（`decision_evidence` 逐位元相同／wire spec 多一 null 鍵／content bytes 任何鍵名增刪都變）；38 事件名不改、payload 加 `policy_kind`；39 落點改「觸發後動作」 |
| | **新 C-292-45..56** | actions map 形狀／registry 四元組是契約／R1–R9 400／跨 kind 只交集已觸發的／latch PK／llm_operational 單一 trigger 與 `limits` 排除／mandatory fail-closed／第八鍵形狀／`REJECTION_MESSAGES` 不含 kind 名／Console 三列必渲染／describe 兩分支 + `policyKind` dispatch／resolve-time 可達性不擋請求 |
| **PRD-325** | 標題／§3.1／§1.4 G4／§3.2／新 §3.9／§7／§4 | 去 guardrail 化；G4「不綁哪一條 rail」→「**不綁 PolicyKind**」（既有文件最接近本案的支點，也最容易被誤讀成「已經做到」）；D1 標為 guardrail 的 trigger 定義；新 §3.9 寫 llm_operational 的限制（下一輪生效 + 需明示識別碼 + `limits` 不觸發 + 觀察模式）；§4 新增驗收條件必須斷言**可觀察屬性**（「llm_operational policy POST 一個 conversation-scope action 回 200；其限制拒絕一次帶 session id 的請求後，下一輪同 session 的路由結果落在核准範圍內」），不是斷言 `actions` 鍵存在 |
| **ADR-461**（新；寫時複查撞號） | — | 「Policy actions — kind-agnostic consequence layer」，`Amends ADR-459`。§Alternatives 必列並駁回：per-kind 鏡射、content 外欄位（`content_hash` 只 hash `content`，會繞過兩個 resolver 的 drift guard ⇒ 違 ADR-093 #3）、per-rule inline action（Portkey `pii.ts` 反例）、Kyverno 式 rule-type-owned action。§2 收錄 §2.2 的「不能當 trigger」逐條源碼證據。ADR-093 五列表必填 |
| Core-ADR-02:81／Core-PRD-02:62 | primary | ADR-459 介入面改寫為「已由 ADR-461 提升為 kind-agnostic policy action」 |
| Core-ADR-01:72／Core-PRD-01:56 | extends | 加一列「policy trigger sink + action executor registry」 |
| Core-PRD-05 | extends | Console 新增 kind-agnostic「觸發後動作」區段 |
| Core-ADR-04／06、Core 08／10／12 | orthogonal | 事件名不改；selector 仍以 Model uuid 為單位；enforcement owner 不同——明說不影響 |
| glossary §2.1 | — | 兩條並列（§5.6） |
| `docs/research/RESEARCH-policy-level-actions-prior-art.md` | 新增 | §6 擴寫成 evidence pack，回補 HUB |
| `docs/草案/guardrail-action.md` 頁首 | — | 加 Rev.5 註記指向本檔 |
| wiki + 根 `CLAUDE.md` | — | 「policy action」概念條目 |

> 沿 ADR-191 → ADR-206 → ADR-259 → ADR-337 → ADR-343 檢查 supersede 鏈；**不要引用已被 ADR-343 撤回的 INV-337-4/5/10/12**。

### 7.2 Core 對比表（可直接貼進 PR）

| 領域 | Core-ADR/PRD | 關係 | 行動 |
|---|---|---|---|
| 02 Policy & Authorization | Core-ADR-02 / Core-PRD-02 | **primary**；extends ADR-191／206／249（§F3 三層之外的第四層 consequence）／259；**amends ADR-459** | 各改一行 + 計數 |
| 01 Gateway & Streaming | Core-ADR-01:72 / Core-PRD-01:56 | extends | 加一列 |
| 04 Audit & Observability | Core-ADR-04 / Core-PRD-04 | orthogonal（事件名不改） | 明說零變更 |
| 05 Console Frontend | Core-PRD-05 | extends | 加一行 |
| 06 Provider Integration | Core-ADR-06:56 / Core-PRD-06:57 | orthogonal-but-adjacent | 加引用 |
| 08／10／12 | — | orthogonal | 明說不影響 |

### 7.3 三件延後項（PA-D13）

| 延後項 | 為什麼延後 | 觸發條件 | 護欄 |
|---|---|---|---|
| audit 事件 `iam.guardrail_policy.conversation_scope_empty` → `iam.policy_action.*` | 跨 repo PR + submodule pointer bump；ADR-429 §7 前例：seed rule 不 bump version 會讓 upsert guard 靜默不生效 | rel 部署之後 | v1 payload 加 `policy_kind`（additive）；`/flow-gate` 鎖事件名只出現在已知兩處 |
| capability 契約搬到 IAM 自有 artifact | 踩 PRD-302 M5 guard，收益零行為改變 | M5 結束或該區塊首次改值 | tracking issue |
| `guardrail_verdict_sink.py` 改名 | 動三個 gate 常數 + `.sh --sink` | 第三個 kind-agnostic 呼叫端出現 | 模組 docstring 寫明 |

---

## 8. 交付切片與部署

### 8.1 不變量與 PR 表

- **INV-SHIP-1**：`main` 在每一個 merged commit 上，conversation-scope 功能都可用。
- **INV-SHIP-2**：`main` 任何時刻不得存在「llm_operational 的 action 存得進去但永不觸發」——由 registry 空集合結構性保證。
- 所有 PR base `main`、不 stack（repo squash 且不刪 head branch，stacked child 蒸發且不跑 CI）。

| # | PR | 內容 | CI 變化 | Rollback |
|---|---|---|---|---|
| 0 | 設計閉環 | ADR-461 + SPEC-292 Rev.6 + PRD-325 Am.A + RESEARCH pack + Core 回寫 + glossary + 本檔轉歷史 | 純文件 | revert |
| 1 | `feat(gateway): latch schema v2 + user_version 讀回` | DDL 加三欄 + 複合 PK；`get`/`latch` 加參數（呼叫端全傳 `"restrict_conversation_scope"` / `"guardrail"`）；讀回 + fail-fast；gate 新規則 13 | store 單元測試約 15 條 | revert；任何環境都沒有這個 SQLite 檔 |
| 2 | `feat(gateway): evidence key #8` | `routing_decision.py` +1；gate `EVIDENCE_KEYS` +1；一條測試 | 規則 7 由紅轉綠必在同 PR | revert（三檔） |
| 3 | `feat(iam): policy actions schema + registry + fold + wire` | `policies/policy_actions.py`（llm_operational `reasons` **空**）；`actions` 掛兩個 kind；移除舊欄位 + PA-D17 coercion；`actions_merge.py`；R1–R9；resolve-time 可達性；**同 PR 雙寫**：舊巢狀鍵與新頂層 `policy_actions` 並存一個 release（否則 PR-3 與 PR-5 之間 main 上功能退化成惰性，違反 INV-SHIP-1）；openapi 重產 + 五處 digest | `test_adr459_conversation_scope_schema.py` 23 處、`test_adr459_scope_preview_api.py` 3 處改路徑；五個 consumer contract test 同 PR 轉綠 | revert 需同批還原五處 digest |
| 4 | `feat(gateway): record_policy_trigger + 跨 kind 選擇` | 抽 `record_policy_trigger`（留原檔）；`policy_action_sources_for`；`expand_effective_scope` 攤平（含四處副本）；`selector_summary` per-source；`REJECTION_MESSAGES` 去 guardrail 化（兩處）；`HttpPolicyActionsData`；gate 新規則 11/12；**probe (f)** | 16 處引用改路徑 | revert |
| 5 | `chore(iam): 移除巢狀舊鍵雙寫` | PR-4 merge 後 | — | revert |
| 6 | `feat(gateway): llm_operational admission adapter`（**條件式**） | carrier 穿進 `run_admission` / `admit_responses`（3 呼叫端）；三個拒絕分支接 sink；gate 規則 8 擴充；**probe (d)(e)**；**同 PR 填** `reasons = {"admission_rejected"}` | 規則 12 由紅轉綠 | revert 回「llm_operational action 一律 400」。**probe 做不出來就不 merge** |
| 7 | `feat(console): policy actions section` | `policy-actions.ts` + `policy-actions-section.tsx`（新檔）；`ConversationScopeFields` 抽出；型別扁平→巢狀；build/parse/describe + `policyKind` dispatch；兩個 dialog 掛載 + prefill 拆兩段；i18n 兩份 + glossary | `policy-content-form.test.ts:1032-1104` 六個 case、`conversation-scope-section.test.tsx` 改巢狀；新增 describe 測試 ×2；測試遷移約佔 diff 六成 | revert |
| 8 | `feat(iam,console): 跨 kind scope preview` | `preview_for_application` 跨 kind；三個 kind 閘拆除；Console 兩處 hardcode；三列組合預覽；順帶修 `replace_binding_endpoint` 不附 preview | 預覽整合測試 | revert（預覽退回只顯示 guardrail） |
| 9 | acceptance workbook 重釘 | PR-7 squash 後從 main tip 單獨 PR | — | — |

**切點**：PR 0–5 + 7 是 Peter 論點的完整交付（欄位在 policy 層、Console 區段跨 kind、gateway 讀單一頂層 wire、零 action↔guardrail 耦合）。**PR-6 從未合入也不影響這個結論**——差別只是 llm_operational 的觸發來源清單暫時是空的，而且這件事在 UI 上是明說的、fail-loud 的。

### 8.2 跨 kind fold 契約測試歸屬

IAM 擁有組裝（`tests/contract/` 對兩 kind fixture 斷言 wire `sources` 形狀與 attribution）；gateway 擁有選擇與交集（probe (f)，真 store + 真 prefilter）。**兩邊都要**，任一邊用 fake 都只證明 fake 的契約。

### 8.3 部署（PA-D15）：gateway → IAM → Console

| 情境 | 行為 |
|---|---|
| 新 gateway + 舊 IAM | wire 沒有 `policy_actions`（且舊巢狀鍵仍在，PR-3 雙寫）→ 動作照舊 |
| 舊 gateway + 新 IAM | 舊 gateway 不認得頂層鍵 → 忽略；仍讀巢狀舊鍵 → 動作照舊。`mandatory` 的 fail-closed 只在「認得 `policy_actions` 但不認得某個 `action_id`」時觸發 |
| Rev.5 單獨先部署 | **不做**（§1.2） |

**首次部署後的 rollback runbook**（寫進 ADR §7.2）：latch store 是控制面資料，回退舊 binary 前 (1) 停 gateway、(2) 刪 `XPARSE_CONVERSATION_SCOPE_DB_PATH` 指向的檔、(3) 起舊 binary。代價是進行中的限制全部釋放（fail-open 方向，已知接受）。若檔案被留下，`user_version` 讀回讓舊 binary **開機就大聲失敗**而非每請求 500。最外層保險 `XPARSE_CONVERSATION_SCOPE=off`。

---

## 9. 風險與最強反對意見

### 9.1 對本設計最強的反對

> 「你為了一個只有一項的目錄蓋了一整套 actions 框架，而你自己承認唯一的非 guardrail trigger 與『該用哪些模型』因果薄弱、慢一輪、要對話識別碼、觸發機率不明。這是 §17.1a 的紅旗：機制變成了需求。把欄位改個名就好。」

**(a) 框架的邊際成本已經被既有設計付掉了。** ADR-459 的 15 條 invariant 有 12 條、SPEC-292 的 44 條有約 30 條逐字成立；機制層根本不認識 guardrail。真正的耦合是 §2.1 的六個掛載點。新增的抽象是：一個 `PolicyActionsSpec`、一個 `merge_policy_actions()`、一張 `TRIGGER_REGISTRY`、一張 executor registry、一個 wire 鍵。這不是蓋框架，是把已經通用的東西從誤放的抽屜拿出來。

**(b) 成本窗口是單向的。** 今天零部署、零不可變 row。明天之後每一個 `PolicyVersion.content` row 都是永久相容債（§2.3 #1 已證明：`extra="forbid"` + resolve-time 重 parse 讓「以後再改」的價格是一個 coercion 層 + 一次 data migration）。

**(c) 接受核心、縮小範圍：** 不出第二種 action（PA-D16）；llm_operational 只留一個誠實的 trigger 且 v1 只觀察（PA-D3／D4）；PR-6 條件式交付；觀察窗報告若顯示沒有可用性價值就撤回，不辯護。

### 9.2 其餘風險

| 風險 | 嚴重度 | 緩解 |
|---|---|---|
| 自我增強迴圈（限縮 → 更容易再用盡 → 再觸發 → 對話被釘住） | **高**（guardrail 沒有這個形狀，既有設計沒防線） | PA-D4 觀察模式；翻 enforce 的必要證據＝重複觸發次數分佈；SPEC 加防洪線（latch 存活期間同一 `(key, action_id, kind)` 的重複觸發，同一閒置窗內 audit 至多一次） |
| 跨 kind 交集為空 → 組合爆炸的 400 | **高**（可用性） | §5.5 三列預覽在 authoring 端算出並警示；`selector_summary` per-source；第八鍵讓 audit 答得出誰撞誰 |
| store DDL 改在部署之後 → 500 風暴 | **高** | 硬排在 PR-1；同 PR 補 `user_version` 讀回 |
| 直接刪舊欄位 → 帶舊鍵的 row resolve 時 fail-closed | 高（若有任何環境已部署） | PA-D17 coercion；PA-D15 禁止 Rev.5 單獨部署 |
| `describeLlmOperational` consumed list 漏 `"actions"` → 醜字串列 | 中（零測試覆蓋） | PR-7 兩條新測試 |
| Console 兩處 `policy_kind: "guardrail"` hardcode → 改造後靜默漏看 | 中（不是編譯錯誤） | PR-8 專責；review checklist 點名 |
| gate 規則 7 exact-set 漏改／五處 digest 漏一處 | 低（CI 紅且訊息明確） | PR-2、PR-3 獨立 |
| 市場證據缺口（§17.1a） | 中 | PRD-325 Am.A 不新增任何商務宣稱；RESEARCH pack 把 LiteLLM sticky routing 標為最接近先例、把「policy 層 action 目錄」標為 negative evidence |

---

## 附：12 歲白話層（給客戶、業務、新人）

我們的「政策」以前只會做一件事：**擋下來**。

現在政策多了一半：**擋下來之後，接下來怎麼辦。**

舉例：客服人員在對話裡貼了一份客戶名冊，系統把身分證字號遮掉了。以前就到此為止——下一句話還是可能被送到境外的模型。現在管理員可以在政策上加一個「觸發後動作」：**這段對話從此只走我核准的供應商。**

而這個「觸發後動作」不是資安功能專屬的。同一個動作也可以掛在「運行規則」上：某段對話一直把共享的配額用光，那就讓它接下來走指定的模型池，不要再跟別人搶。

所以管理員只要記住一句話：**規則決定什麼算違規，動作決定違規之後做什麼。** 規則長得不一樣，動作是同一份清單。
