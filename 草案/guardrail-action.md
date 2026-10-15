# Guardrail Action：觸發後把對話收斂到可信範圍 — 草案 Rev.3

> **狀態**：草案 Rev.3（2026-09-15）。**設計閉環已產出**：RESEARCH-guardrail-conversation-scope-restriction-evidence-2026-09-15 · PRD-325 · ADR-459 · SPEC-292（分支 `docs/guardrail-action-conversation-scope`）。本檔自此為歷史紀錄，衝突時以正式文件為準。
> **Rev.5 註記（2026-09-16）— 這個 action 已經不屬於 guardrail**：後續拍板（PA-D1–PA-D17）把 `restrict_conversation_scope` 從 `GuardrailPolicySpecV2` 的欄位抬成**任何 PolicyKind 的 `content` 都能攜帶**的 kind-agnostic `actions` map，「什麼算這條 policy 被觸發」改由 per-kind `TRIGGER_REGISTRY` 定義，wire 改為頂層 `policy_actions`，latch PK 改 `(key, action_id, policy_kind)`。設計輸入見 **`docs/草案/policy-actions.md` Rev.1**，正式文件見 **ADR-461**（amends ADR-459，不 supersede）+ SPEC-292 Rev.6 + PRD-325 Amendment A。本檔凡以「guardrail 的 action」為主詞的敘述（標題、§0 決策、§4.2、§4.6）**在所有權層面已被取代**；機制層敘述（latch 語意、pre-filter 位置、三條 400）仍與 ADR-459 一致。**衝突時一律以 `docs/` 為準。**
> **Rev.4 註記（2026-09-16）**：Peter 再拍板 D8–D14（見 ADR-459 頁首 Rev.2 決策表）：保留窗改閒置 sliding 30 天；latch 只記事實、範圍讀取時展開；拿不到對話 id 不 400（request-local 收斂 + 可選 `always_restrict`）；判官不套範圍；Responses 三分支同一條 `candidates ∩ 範圍` 規則、binding 在範圍內 chain 不斷、不強制 `store=false`、step 5 403→400 不再前置；credential guard 歸 #4878；verdict 出口統一為一個 sink。本檔 §4.2 D2/D3、§4.6、§4.6.1、§4.7 已被取代。
> **Rev.3 改了什麼**：Codex encrypted_content 實測結果（客戶端半邊已驗）；發現 gateway 吞掉 `include` 使整個風險目前被遮住；§4.6 新增「provider-signed opaque state 與 credential 切換」小節，guard 寫成通用形式（不綁 latch，同時擋 R3 failover）；三張順手 issue（`include` 吞掉、`/v1/messages` thinking 不可往返、R3 failover 跨 credential 待驗）。
> **Rev.2 改了什麼**：§0 決策紀錄（六項拍板）、可信範圍單位改為 Model + 三種 matcher、Responses 面三分支行為與 `store=false` 提前到 v1、修正 Rev.1 引用的過期事實（key 段數、解析鏈層數、Redis 依賴、pre-filter 鏈、`store_source`）、補三個 Rev.1 沒點到的坑（L5 fallback、failover 集、路由後 rail 皆 block）。
> **現況基準**：本地 `f36e826e7`，`origin/main` `28688540b`（落後 43 commit，差異全為 ADR-449 驗收測試與文件，未觸及 routing / guardrail / responses 檔案）。引用的程式碼位置皆為當日實讀。
> 本文與 `docs/` 衝突時以 `docs/` 為準。相關既有文件：ADR-447（session affinity）· ADR-430（routing objective 兩軸）· ADR-318 / SPEC-223（classifier rails）· ADR-448 / SPEC-219（PII 偵測面）· ADR-138（模型定址）· ADR-192 / PRD-157（Responses binding）· ADR-321（reliability tiering）· ADR-268（client identity）· ADR-437（Responses surface）。

---

## 0. 一句話與決策紀錄

**當這個對話被 guardrail 判定為敏感，從那一刻起，這個對話的後續推論只會送到管理員指定、客戶已審查／已簽約的供應範圍；範圍內沒有可用模型時，拒絕請求而不是悄悄送出去。**

### 0.1 已拍板（2026-09-15，Peter）

| # | 決策 | 結果 | 詳見 |
|---|---|---|---|
| D1 | 哪些 verdict 算 trigger | **全部**：PII mask、word_filter mask/block、on_topic、content_filter，任一 enforce 命中即寫 latch | §4.4 |
| D2 | latch store | **v1 gateway-local 持久檔**（同 `routing.db` 型態，重啟不解除）；Redis 等 SPEC-289 多副本再接 | §4.2 |
| D3 | TTL | **absolute 24h**，不 sliding | §4.2 |
| D4 | 多條 policy fold | **intersection**（子 scope 只能更嚴） | §4.8 |
| D5 | Responses 面 scope | **三條分支都有明確行為**：resolver 收斂；pin / binding 觸發後 400。**`store=false` 強制提前到 v1**（規則見 §4.6）；step 5 `403→400` 為**上線前的實作前置**（獨立 PR，非 PRD 前置） | §4.6 |
| D6 | 與 pin 的優先序 | **latch 壓過 pin**；指名不可信模型回 400，不靜默改路由 | §4.5 |
| D7 | 可信範圍的儲存單位 | **Model uuid**；UI 以三種 matcher 選取（單顆模型 / credential / serving_locality），儲存為選取器、動態解析 | §4.1 |

### 0.2 前置條件

**PRD 前置（做 PRD 前必須先完成）——只有一條**：

1. **外部證據閉環**（§17.1b）：`/research` 產 evidence pack，回補研究智庫 HUB。

**實作前置（設計閉環之後、本功能 PR 之前的序列；不是寫 PRD 的門檻）**——完整見 §7：

- #4876 `include` 修復 ＋ credential guard（§4.6.1）**同批**：guard 的規則由本 PRD/ADR 定義，不在它之前先實作；它今天是否 inert（include 被吞是否遮住風險）為 CONTESTED，不影響 PRD 寫得出來。
- step 5 `response_store_disabled` 403 → 400（PRD-157 amendment）：這是 `store=false` 強制**上線**時的前置（step 5 變熱路徑），不是寫 PRD 的前置。

> 三張順手 issue（#4876 / #4877 / #4878）到建檔上板為止，**不動工**；主線回到 `/research` → `/doc-prd` → `/doc-adr`。

---

## 1. 這是什麼功能

### 1.1 客戶看到什麼

管理員在 policy 上多勾一個 action：「觸發時把對話收斂到這些供應範圍」，並用三種方式選出範圍（依 system role 只看得到自己 scope 內的）：

- 單顆模型（Model Pool 的一列）
- 「這個 credential 底下的全部模型」——例：我們自己簽約的 Azure EU tenancy
- 「全部地端模型」（`serving_locality=onprem`）

員工在第 3 輪貼進一段敏感內容 → guardrail 觸發 → 從第 3 輪起，這個對話的推論只落在管理員選的範圍內，直到 24 小時後或對話換 session。員工不需要做任何事，也不會被要求「切回去」。

### 1.2 為什麼要做

PII 遮罩與關鍵字封鎖是**內容層**的控制——改寫或擋下單一則訊息。但有一類風險是**對話層**的：一旦這個對話被判定敏感，後續每一輪都可能夾帶相關脈絡，而**單則掃描抓不到脈絡**。把整條對話收斂到**客戶已審查、已簽約的供應範圍**（自己的 tenancy、簽過 DPA 的 region、地端叢集），是內容層控制之外的第二道防線。

> **定位不是「資料不出境」**。地端只是可信範圍的一種；客戶信任的雲端 credential 同樣是可信範圍。這是治理／採購故事，適用面比 data-residency 大。Rev.1 把定位綁死在地端是偏差，已修。
>
> ⚠️ **這句宣稱還沒經過對抗式查證**（§17.1b）。寫 PRD 前必須走 `/research` 產 evidence pack，每條差異化宣稱要指向一手來源或標 WEAK。

### 1.3 它不是什麼（先寫，免得賣錯）

| 不是 | 為什麼要講 |
|---|---|
| **不是對抗惡意使用者的控制** | latch 的 key 含 client 可控的 session id（§4.2）。使用者換一個 session id 就解除。這是「保護誠實使用者的對話不外流」，不是「擋得住想繞過的人」。 |
| **不是把已經送出去的內容收回來** | 第 3 輪觸發，第 1–2 輪的內容早就到了原本的 provider。只管觸發之後。 |
| **不保護 classifier 判斷器那一次外送（除非 §4.7 A 生效）** | `classifier.model: auto` 綁的是已路由的那顆模型（`classifier_handler.py:259`）。 |
| **沒送對話 id 的 raw API caller 完全不生效** | 解析不出明示 session id（§4.2 的層級表）→ `source=none` → 不寫也不讀 latch，一輪一輪各自判斷。 |
| **Responses 面：可信範圍沒有 cloud Responses 模型時，三條分支的生效方式是「拒絕」** | `RESPONSES_PROVIDERS = {azure_openai_responses, openai_responses}`（`routing_adapter.py:98`）——平台沒有地端 Responses provider。可信範圍只有地端 → Responses 面裁完必為空 → 400。**要寫在顯眼處，它決定客戶怎麼配置。** |
| **綁了這個 action 的 app，Responses 客戶端一律無狀態** | v1 強制 `store=false`（§4.6）。每輪要自帶完整歷史；OpenAI SDK 預設 chain 的用法會拿不到可 chain 的 id。 |
| **Responses 面即使可信範圍含 cloud credential，Codex 類客戶端在 latch 切換那一輪仍會被拒絕（除非同 credential）** | Codex 逐位元回送 provider 發的 encrypted reasoning（已實測）；那個 blob 綁發出它的 organization。latch 換 credential → §4.6.1 的通用 guard 擋下 → 400。這是 latch **自己造成**的（affinity 本來讓 credential 在 session 內穩定），不是「OpenAI 的限制」。 |
| **選了 credential / locality matcher 的可信範圍是動態的** | 之後在該 credential 下新增的模型會自動納入。UI 必須明示（§4.1）。 |
| **不是合規認證** | 跟 PII 一樣：技術控制，不是「我們符合某某法規」的證明。 |

---

## 2. 為什麼這件事不像看起來那麼簡單

### 2.1 Guardrail 的三條 rail 跑在路由的不同側——但這個問題比看起來小

`routes/chat.py` 的實際執行序：

| 階段 | 行號 | 相對於路由 | 命中時的行為 |
|---|---|---|---|
| input rails（PII mask / word_filters） | `:1061` | **之前** | mask 後轉送，或 block |
| 路由決策 `_route_via_routing_module` | `:1140` | — | — |
| classifier rails（on_topic / content_filter） | `:1276` | 之後（admission `:1308` 之前） | **一律 block**（schema 沒有 action 欄位） |
| output rails | 回應之後 | 之後 | block / mask 輸出 |

→ **所有路由之後才跑的 rail，命中都是 block，那一輪根本沒送到 provider**。PII mask 在路由之前，同輪自然收斂。所以「trigger 之後的第一次路由決策生效」（§4.3）對客戶可以講成「觸發那一輪起」，唯一例外是 §4.7 判官那一次外送。這比 Rev.1 講的「結構上做不到同輪」樂觀得多。

### 2.2 Session 記憶這一層已經有人（ADR-447），但語意相反

| | ADR-447 affinity | 本功能 |
|---|---|---|
| 性質 | 最佳化（保 provider prompt cache） | 安全控制 |
| 模型不合格 | evict + fail-open 回全池（D6） | fail-open = 管制失效 |
| **failover 集** | **不收斂**（D11：affinity 掛了就換） | **必須收斂**——否則 primary 一失敗就 failover 到不可信模型 |
| gateway 重啟 | 少一次命中 | 重啟即解除管制 → D2 選持久 store |
| TTL | sliding idle 3600 s | absolute 24h（D3） |
| key | 六段 `tenant\|app\|credential\|surface\|session\|prefix_digest`（Amendment B，`production/session_affinity.py:309`） | 三段 `tenant\|app\|session_id`（§4.2） |
| session id 來源 | 九層，含內容衍生 L5 | 只吃明示對話 id 的層（§4.2） |

→ **解析鏈可以複用，key、store、降級語意都不能共用。**

### 2.3 `/v1/responses` 有自己的決定模型的階梯

`responses_routing.resolve_responses_routing` 的三條分支（`responses_routing.py:411/490/501`）：

| 分支 | 條件 | 有候選集嗎 | 本功能行為（D5） |
|---|---|---|---|
| `SOURCE_PIN` | 客戶端指名模型（非 opaque） | ❌ | 觸發後：指名模型不在可信範圍 → 400 |
| `SOURCE_BINDING` | 帶 `previous_response_id` | ❌ 不呼叫 resolver、`candidates == []` | 觸發後：binding 的模型不在可信範圍 → 400（殘餘路徑，v1 強制 `store=false` 後新鏈不會走到） |
| `SOURCE_RESOLVER` | opaque 且無 `previous_response_id` | ✅ | 收斂候選集（同 chat） |

binding 分支的困難不是實作，是 chained turn 的對話狀態在 provider 那邊，`ResponsesBinding` 只存 mapping 不存內容。「把第 N+1 輪轉去可信模型」既做不到（沒有 transcript），做到了也沒意義（第 1..N 輪早就在原 provider 的 storage 裡）。這就是 D5 選擇強制 `store=false` 的根本理由。

### 2.4 Rev.1 引用錯的事實（已修）

| Rev.1 說 | 實際 |
|---|---|
| affinity key 三段 | 六段（Amendment B / INV-447-16） |
| 解析鏈四層 | 九層：`Application.session_id_header` → `x-xparse-session-id` → `x-session-id` → `x-claude-code-session-id` → Codex `session-id`/`thread-id`（UA-gated）→ `metadata.user_id` → `prompt_cache_key` → W3C `baggage` `session.id` → **L5 內容衍生**（`apply_prefix_fallback`，system+tools hash） |
| Redis 是新依賴 | gateway 已正式依賴 `redis>=5`（`pyproject.toml:20`，`quota_counter.py` 在用）；pro / enterprise compose 有 Redis，basic 沒有 |
| pre-filter 鏈四步 | 實際：`models_from_auth_context` → `chat_surface_models` → `pin_trimmed_models` → `build_strategy_config` → `apply_prefix_fallback` → `session_affinity_trimmed_models` → `_classify_for_routing` → `apply_tier_escalation` → `resolver.resolve` → `record_session_affinity_decision`（`chat_helpers.py:257–415`） |
| `store_source="policy"` 已存在 | 只有 `default` / `client`；`policy` 是 Phase 2 註解（`azure_responses_worker.py:205–221`） |
| ADR-138 INV-138-16 定了優先序 | INV-138-16 只講 pin 不 failover；`pin > binding > affinity > resolver` 只出自 ADR-447 INV-447-6 |
| `normalize_store_or_response` 回二元組 | 三元組 `(Optional[bool], Optional[str], Optional[JSONResponse])`，在 `responses_pipeline.py:253` |
| （Rev.2 假設）client 送的 `include` 會到 provider | **不會**。`ResponsesCreateRequest`（`routes/responses.py:162–196`）沒宣告 `include`，pydantic 預設 `extra="ignore"` 靜默吞掉（`instructions` #4249 同類第四次）；worker payload 白名單（`openai_responses_worker.py:140–164`）也沒有。→ **是否**因此遮住 §4.6.1 的風險，OpenAI 兩頁一手文件互相矛盾（API reference 說要 `include` 才回；reasoning guide 說 `store:false` 預設就回、`include` 已 legacy）——RESEARCH §3 #6 標 **CONTESTED**，guard 不得依賴它。 |
| （Rev.2 假設）Responses `input` 會被 gateway 處理 | verbatim 轉發（`openai_responses_worker.py:58–60`），repo 零處 `encrypted_content` 處理；客戶端自帶的 blob 原封送到任何 provider |
| `/v1/messages` 面有同類 signed-state 問題 | 沒有——它是翻譯殼，`thinking`/`signature` 在翻譯層**靜默丟棄**（`anthropic_translation.py:154,191`），回送的 thinking 也不帶 signature（`:358–363`）。該面不往返 signed state，但 extended thinking 不可往返是獨立 bug |
| recorder 舊配方用 `gpt-4o` | **假陰性**——非 reasoning 模型不觸發 `include`；要用 reasoning 模型名才看得到 |

---

## 3. 推薦的解法（總圖）

```
                    ┌─────────────────────────────────────────┐
  任何 rail          │  guardrail verdict（任何階段、任何種類）  │
  任何階段     ──────▶│  只做一件事：寫 latch                    │
                    │  (session_key → 展開後的可信集合 + policy 版本) │
                    └─────────────────────────────────────────┘
                                      │
                        兩邊唯一的接觸面是這個 latch
                                      │
                    ┌─────────────────▼───────────────────────┐
  每一次路由    ──────▶│  只做一件事：讀 latch，有就收斂候選集     │
                    │  （resolver_models 與 failover models 都裁）│
                    └─────────────────────────────────────────┘
```

落到 chat 面的 routing pipeline，是**第四個同型 pre-filter**，插在 pin 之後、affinity 之前：

```
models_from_auth_context
  → chat_surface_models
  → pin_trimmed_models              (ADR-138)      ← latch 在此之前先判：pin 到不可信 → outcome=pinned_outside_scope
  → trusted_scope_trimmed_models    ← 新增（純函數，不 raise，回 outcome；同時裁 failover 集）
  → apply_prefix_fallback / session_affinity_trimmed_models (ADR-447)
  → classification → apply_tier_escalation
  → resolver.resolve                ← 完全不動
```

**不動的東西**：resolver、所有 strategy、`routing-parameters` contract artifact、audit schema。ADR-430 INV-430-3（合格集只由 classifier 與候選序決定）不受影響，因為收斂發生在 resolver **之外**——跟 ADR-447 同一個論證。

**跟前三個 pre-filter 形狀不同的一點**：ADR-447 只裁 `resolver_models`，回給 R3 failover 的 `models` 不裁（D11）。本 pre-filter **兩個都裁**。ADR 要明寫。

**契約寫成**：「latch 在 trigger 之後的**第一次路由決策**生效」（§4.3）。

---

## 4. 決策點與選項

★ = 推薦；✅ = 已拍板。

### 4.1 Policy 裡存什麼 ✅ D7

**單位不能是 credential**：`Model.credential` 是 nullable FK（IAM `models.py:528`），wire 上 `HttpAuthContextModel.credential_uuid` 也是 `Optional`（`iam_http_client.py:466`）。地端 vLLM / openai_compat 常無 credential（dev 上 34 顆全無），用 credential 當單位這些模型永遠納不進去。

**單位不能是 provider code**：同一個 `openai` 底下可以同時有「我們自己的 Azure EU tenancy」和「某個共用美國帳號」。

**對「誰收到資料」，真正的身分是 `(provider, endpoint, credential)` 三元組，Model row 剛好同時帶齊。** 所以：

| 層 | 決定 |
|---|---|
| 儲存單位 | **Model uuid** |
| 儲存形狀 | **選取器**（三種 matcher，任一命中即可信）：`models: [uuid]` / `credentials: [uuid]` / `serving_locality: [onprem\|cloud]` |
| 解析 | 一個純函數 evaluator，三個 matcher 分支；對 `auth_context.models` 逐顆判定 |
| 動態語意 | credential / locality matcher **動態解析**：之後新增的模型自動納入 |

**三個配套（缺一不可）**：

1. **UI 明示動態**：選了 credential 或 locality matcher 時顯示「此 credential／locality 之後新增的模型會自動納入可信範圍」。不明示，管理員會以為選的是快照。
2. **audit 記「展開後」的集合，不只 selector**：latch 寫入時與每次 routing decision 都要落當下展開的 model uuid 集合（走 `plan.metadata` → `decision_evidence`，§6 #7）。selector 會隨時間解析出不同結果，事後要答得出「那個時間點可信範圍是哪幾顆」。
3. **預檢做成持續監控，不是綁定時算一次**：
   - 綁定時：對每個受影響 app **分 surface** 算交集，顯示「chat N 顆 / Responses M 顆」；任一為 0 → 警告並明講「此 app 的 &lt;surface&gt; 客戶端觸發後即拒絕」。
   - 綁定後：模型異動（新增／刪除／paused / credential 失效）時重算，或定期重算；0 顆或低於門檻告警。靜態清單的失效模式是「模型輪替 → 可信集合逐漸萎縮 → 某天空集合 → fail-closed 整個 app 掛」，而且是靜默逼近。

**wire 改動**：`ModelInfo`（`xparse_routing/domain/protocols.py`）沒有 `credential_uuid`，`models_from_auth_context` 把它丟掉。補一個欄位（或塞 `capabilities`）即可，**不用改 IAM validate wire、不用重釘五處 consumer digest**。

**命名**（§17.1a）：PRD 不要寫「trusted provider」——`provider` 已有精確意思會撞名。驗收要斷言可觀察屬性（「觸發後這個對話的後續請求只落在管理員指定的範圍，audit 可查」）。

### 4.2 Latch 存在哪裡 ✅ D2 / D3

| 選項 | 優點 | 缺點 |
|---|---|---|
| A. 沿用 ADR-447 in-process store | 零新基礎設施 | 重啟即解除管制 |
| ✅ **B-local. gateway-local 持久檔**（同 `routing.db` 型態） | 重啟不解除；single-active 今天夠用（multi-active 只是 SPEC-289 Draft，NOT IMPLEMENTED）；basic tier 沒 Redis 也能用 | 多副本不共享——等 SPEC-289 |
| B-redis. Redis | 跨副本 | basic tier 沒有；Redis 掛掉的 fail-open/closed 要拍板 |
| C. 存進 IAM | 最持久 | 熱路徑多一次 IAM 往返 |

**v1 = B-local，store 介面抽成 Protocol，Redis backend 隨 SPEC-289 接。** 「Redis 不可用時」的問題因此在 v1 不存在。

**共通決定**：

- **解析鏈複用 ADR-447 的 `resolve_session_id`**，但 latch **只認明示對話 id 的層**：

  | 層 | latch 是否採用 | 理由 |
  |---|---|---|
  | `Application.session_id_header`、`x-xparse-session-id`、`x-session-id`、`x-claude-code-session-id`、Codex `session-id`/`thread-id`、W3C `baggage` `session.id` | ✅ | 明示對話身分 |
  | `metadata.user_id` | ❌（待議，預設不用） | 鎖的是人不是對話；一個人所有對話會一起被收斂 |
  | `prompt_cache_key` | ❌（待議） | 語意是 cache 分桶，不保證對應對話 |
  | **L5 內容衍生（system+tools hash）** | **❌ 絕對不用** | 一個員工貼敏感內容 → **所有用同一 system prompt 的對話**都被收斂，整個 app 鎖死 |

  其餘 → `source=none` → 不寫不讀。
- **key 另導，三段** `sha256(len:tenant | len:app | len:session_id)`。不含 credential（同一對話換 API key 仍是同一對話）、不含 surface（chat/responses 混用仍是同一對話）、不含 prefix（system prompt 改了不該解除管制）。
- **TTL absolute 24h**（D3），到期即解除；不 sliding。
- **存展開後的可信集合 + trigger 當下的 policy 版本**，不存 selector。policy 中途被改，既有 session 行為不漂移；新 session 用新版本。
- **latch 內容再命中 trigger 時**：不延長 TTL（absolute），但若新 policy 版本的集合更窄，取 intersection 後覆寫（單調收緊）。

> ⚠️ **session id 是 client 可控的**。ADR-268 INV-268-2 + Amendment A 只允許它作路由最佳化 key，不得作 authorization。本功能正面撞這條——ADR 必須明寫 amendment 與威脅模型（換 session 即解除，結構性，§1.3）。

### 4.3 生效時機 ★ C

| 選項 | 評語 |
|---|---|
| A. 同輪生效 | 對 classifier / output rails 結構上做不到——但 §2.1 說明這些 rail 命中都是 block，那一輪本來就沒送出去 |
| B. 下一輪生效 | PII / word_filters 本來就同輪，要讓它下一輪得額外寫碼擋掉，而且讓掉的正是貼進敏感內容的那一輪 |
| ★ **C. 「trigger 之後的第一次路由決策」** | stage-agnostic；未來新增 rail 不用改契約；對客戶可講成「觸發那一輪起」 |

### 4.4 可信集合空了怎麼辦 ✅ fail-closed；哪些 verdict 算 trigger ✅ D1

- **fail-closed**。pre-filter 不 raise，回 outcome `trusted_scope_empty`，由 `execute_chat` 渲染錯誤，走 guardrail block 同一條渲染路徑（`guardrail_response.py`）。
- **error code 400**。Codex terminal 只對 `{400, 429}` 停下來，其他 4xx 吃 5 次重試；Claude Code 逐字印 `message`，訊息要 actionable（例：「此對話已被政策限制在指定供應範圍，該範圍目前無可用模型；請聯絡管理員或開新對話」）。
- **健康判斷不在 latch 裡做**。IAM connectivity `unhealthy` 本來就不踢候選；真正踢的只有 ADR-321 reliability guard（`hard_constraint_rate`）。裁完集合交給 resolver 自己判；resolver 在裁後集合內全被踢 → 一樣 400（§6 #8 要驗 resolver 此時的實際行為）。
- **D1：所有 enforce verdict 都算 trigger**——PII mask、word_filter mask/block、on_topic、content_filter（input / output stage）。shadow 模式記 `would_latch` 不寫（§6 #4）。

### 4.5 跟 pin 的優先序 ✅ D6

新的優先序：**trusted latch > pin > binding > affinity > resolver**。pin 到不可信模型 → 400（outcome `pinned_outside_scope`），不靜默改路由。ADR 要明寫這是 ADR-447 INV-447-6 的 amendment（不是 ADR-138）。

### 4.6 Responses 面 ✅ D5

**三條分支都有明確行為（措辭：「生效方式是拒絕」，不是「v1 不支援」）**：

| 分支 | 觸發後 |
|---|---|
| `SOURCE_RESOLVER` | 收斂候選集（Amendment B / INV-447-20 已把 pre-filter 接上這條，同一支 `session_affinity_prefilter.py` 旁邊加） |
| `SOURCE_PIN` | 指名模型 ∉ 可信範圍 → 400 |
| `SOURCE_BINDING` | binding 的 model ∉ 可信範圍 → 400。掛在 `resolve_bound_model` 回來之後，回 `ChainValidationFailure`（型別已存在，`chain_reject` 已會渲染），`responses_chain_validator._MESSAGES` 加一條。`ResponsesBinding` 有 model FK 與 credential FK，直接比對。 |

**`store=false` 強制，v1 一起做**（不另案）。理由：先上「觸發後才斷線」等於製造一批真實事故——客戶正在聊的對話突然 400。一次到位，綁了這個 action 的 app 從一開始就拿不到可 chain 的 id，新鏈不會走到 binding 分支。而且 `store=false` 跟「對話不落在客戶未審查的 storage」的定位本來就一致。

**精確規則**（worker 已區分 `default` 與 `client`）：

| 客戶端送的 `store` | 行為 |
|---|---|
| 沒送 | 強制 false；回應 `store: false`；audit `store_source=policy`（**要實作**，目前是 Phase 2 註解） |
| 明送 `false` | 照常 |
| 明送 `true` | **400 拒絕**，訊息 actionable：「此應用已停用 server-side 對話儲存，請移除 `store` 參數並自行帶完整歷史」 |

明送 true 還靜默改掉違反 §1.1 #4，且客戶端會以為能 chain。OpenAI SDK 預設「沒送」，落第一列，不會被擋。

**掛點**（`routes/responses.py`）：input rails `:508` → `normalize_store_or_response`（`responses_pipeline.py:253`，多收 auth_context）→ `route_model_or_response` `:532` → chain validation → classifier `:576`。latch 在三個點都讀得到。

**殘餘**：policy 綁上去之前已建立的鏈（`store_flag=true` 的 binding row）下一輪仍走 binding 分支 → 靠上表的 400 擋。

**前置獨立 PR：step 5 `response_store_disabled` 403 → 400**（`responses_chain_validator.py:203–209`）。理由：① 403 語意是 authorization，這是請求狀態問題；② 403 讓 Codex 重試 5 次，強制 `store=false` 後 step 5 從邊緣路徑變熱路徑；③ 它影響所有 app，不該混進本功能的 PR 放大 rollback 範圍。做法：PRD-157 store 章節小 amendment + 獨立 PR，**先落地**，本功能直接繼承。

**Responses 面的切換只在「可信範圍含 cloud Responses credential」時發生**：

| 可信範圍 | Responses 面 |
|---|---|
| 只有地端 | 候選集必為空 → 三條分支全 400（§1.3） |
| 含 cloud Responses credential | 候選集非空 → 切換真的會發生 → **cloud→cloud 換 credential 就是換 organization，正是 encrypted reasoning 咬人的情境** → §4.6.1 |

#### 4.6.1 provider-signed opaque state 與 credential 切換 ✅ 拒絕 400，規則寫成通用形式

**這是 latch 自己造成的問題，不是「OpenAI 的限制」。** 純 Xparse 內的機制：

1. Codex 從第一輪就走 Xparse，turn 1 路由到 credential A 的模型 → A 回帶 `encrypted_content` 的 reasoning item
2. turn 2、3 本來會一直停在 A——ADR-447 affinity 預設開，pin 住同一顆模型＝同一個 credential，blob 永遠對得上
3. turn 3 latch 觸發 → **我們刻意打破那個 pin**，改到 credential B
4. blob 是 A 的 organization 簽的，B 不認得 → `invalid_encrypted_content`

**已實測（真 Codex 0.154.0 → 本機 recorder，reasoning 模型名）**：Codex 每個請求送 `store:false` + `include:["reasoning.encrypted_content"]`，不送 `previous_response_id`；收到帶 `encrypted_content` 的 reasoning item 後，**跨 user turn（resume）與單輪 tool loop 都逐位元原樣回送**。證據 `encprobe/turn_{1,2}.json`。provider 端會拒絕他 org 的 blob 這一半仍是二手（LiteLLM `encrypted_content_affinity_check.py` docstring + `common_utils.py:2004` #40280：「a provider that did not mint the block rejects it signed and unsigned alike」）。

**可能被遮住（CONTESTED）**：gateway 不轉發 `include`（§2.4），但 OpenAI 是否在 `store:false` 下預設仍回 blob，兩頁一手文件矛盾（RESEARCH §3 #6，OQ-1 待一次真 API 驗證）。**設計上假設風險今天就可能是活的**；guard 與 include 修復同批或更早落地。

**同一個洞的第二條路（既有行為，與本功能無關）**：R3 cross-model failover 在 Responses 面是接著的（`responses_resilience.py`，ADR-437 D4，first event 之前）。credential A 的模型在第一個 event 前失敗 → failover 換到 credential B 的模型 → 請求原樣重送 → 同樣炸。觸發條件：Responses 面 + 池子跨 credential（一個池同時掛 Azure 與 OpenAI 的 Responses 模型＝鐵定不同 org，配置很合理）+ 一次 failover + Codex。**未實證，獨立 issue 標待驗證。**

| | 誰造成的 |
|---|---|
| latch 切 credential | 我們的功能，刻意的 |
| R3 failover 切 model | 已經在跑，意外的 |

**Guard 規則（通用，不提 latch）**：

> 請求的 `input` 帶 `encrypted_content`，且本次要送去的 credential ≠ 發出該 blob 的 credential → **400**，訊息 actionable（「此對話含前一供應商簽發的推理狀態，無法轉送至目前指定的供應範圍；請開新對話」）。

guard 管「blob 和 credential 對不對得上」，latch 管「候選集是什麼」，兩件事互不知道；同一條規則自動擋掉 failover 那條意外路徑。

**前提：blob 必須可歸屬 credential。** blob 是不透明的，Xparse 今天沒有任何機制知道它是誰發的。兩個選項（ADR 決策點）：

| 選項 | 做法 | 優點 | 缺點 |
|---|---|---|---|
| ★ **A. 出站時把 credential 標記編進 item** | 回應的 reasoning item `encrypted_content` 包成 `xparse_enc:{credential_hint};{原 blob}`（LiteLLM `litellm_enc:` 先例）；入站解包、比對、還原後轉發 | **無狀態**、不需 store、不依賴 session id；Codex 逐位元回送已實測所以包裝可行 | 改寫回應 body；item 有 `id` 時可改編 id 而非內容（LiteLLM 兩種策略） |
| B. 存 session→credential 對應 | latch/affinity store 記「這個 session 上一次發 encrypted output 的 credential」 | 不動回應 | 依賴 session id（raw caller 無效）、重啟丟失、多副本不共享 |

**v2 alternative：strip-and-switch**（LiteLLM #40280 在 origin deployment cooldown 時的作法：`strip_encrypted_reasoning_from_input` 後換 deployment，`encrypted_content_affinity_check.py:370`）。剝掉的是 reasoning 不是對話內容，audit 記 `stripped_reasoning_items=<n>`。Codex + 可信雲端 credential 要真的能用，得走這條；v1 不做，先拒絕。

**跟 store 的關係**：guard 與 `store=false` 強制正交。`store=true` 的 chained turn 不會帶 blob（state 在 provider），走 binding 分支的 400；`store=false` 的無狀態 turn 才會帶 blob，走本 guard。

### 4.7 classifier 判斷器那一次外送 ★ A

綁了這個 action 的 app，`classifier.model: auto` 必須解析到可信範圍內（平台把 classifier 的模型解析也套同一個 evaluator），**且不只在 latch 之後**——第一則敏感訊息的判斷就要在範圍內，否則判斷本身已外送。這是本功能對 guardrail 側**唯一的反向約束**。Console 目前 `model: "auto"` 寫死（`policy-content-form.tsx:619`），不用改 UI。

### 4.8 多條 policy fold ✅ D4

**intersection**。tenant → group → application → deployment 左折（`guardrail_policy_merge.py:404`），可信集合的「收緊」方向是交集（範圍愈小愈嚴），跟 PII entities 的 union 方向相反，fold 函式要獨立寫、契約測試要 seed「子 scope 放寬父 scope」的反例。只有一層設定時取該層。

---

## 5. 業界對照（LiteLLM，版本 `litellm-sep-14`）

**guardrail → routing 這條線 LiteLLM 沒有**（本輪重驗）。實作 `async_filter_deployments` 的全部是 routing / budget / managed-resource 類：`deployment_affinity_check`、`responses_api_deployment_check`、`prompt_caching_deployment_check`、`encrypted_content_affinity_check`、`budget_limiter`、`model_max_budget_limiter`、`managed_files` / `managed_vector_stores`。`litellm/proxy/guardrails/` 完全不碰 `healthy_deployments`。

三個相鄰但都不是：`content_policy_fallbacks`（per-request 無狀態、provider 觸發）、`on_violation: "end_session"` 與 `end_session_after_n_fails`（只在 `/v1/realtime`，關連線）。

chained turn 的結構診斷仍有參考價值：他們把 `previous_response_id` 親和性做成候選集 filter 而非 ladder rung，全 fail-open，代價是從 SpendLogs 重建整段對話（並踩到 redact 後 tool-call 參數變 `{}` 的坑）。**這條我們不抄**——跟「對話不落在客戶未審查的 storage」的定位打架。

---

## 6. 還沒解決 / 待驗

| # | 事項 | 影響 | 狀態 |
|---|---|---|---|
| 1 | **encrypted reasoning × credential 切換**：客戶端半邊**已驗**（Codex 必回送，§4.6.1）；provider 半邊二手（LiteLLM #40280）。真打 OpenAI 驗 `invalid_encrypted_content` 只在選 strip-and-switch 或要放寬時才需要。reasoning 品質退化（`store=false` 下 tool-call 迴圈是否流失）假 provider 量不到，**維持推測、不進 PRD** | 已定：拒絕 400 + 通用 guard | ✅ 拍板；guard 為前置獨立 PR |
| 1b | **`include` 被 gateway 吞掉**（§2.4）——遮住 #1 的整個風險；修復必須在 guard 之後或同批 | Responses 面行為 | 獨立 issue（bug） |
| 1c | **R3 failover 跨 credential 重送 blob**（§4.6.1）——既有行為，目前被 1b 遮住 | 與本功能無關的既有洞 | 獨立 issue（待驗證） |
| 1d | **`/v1/messages` thinking.signature 靜默丟棄、回送無 signature** | 與本功能無關 | 獨立 issue（bug） |
| 2 | 外部證據閉環（§17.1b） | PRD 不能過 | **前置** |
| 3 | step 5 403 → 400 | 熱路徑重試風暴 | **前置獨立 PR** |
| 4 | shadow 模式：記 `would_latch` 不寫 latch（與「shadow 永不 mutate」一致，`guardrail_handler.py:360–370`） | SPEC | 建議定案 |
| 5 | fold 方向 | — | ✅ D4 intersection |
| 6 | `metadata.user_id` / `prompt_cache_key` 要不要當 latch 的對話 id | 鎖人 vs 鎖對話 | 待議，預設不用 |
| 7 | audit 鍵：`trusted_scope_latched` / `trusted_scope_source`（哪一層 session id）/ `trusted_scope_selector` / **`trusted_scope_expanded_models`** / `trusted_scope_outcome` / `trusted_scope_policy_version`；走 `plan.metadata` → `decision_evidence` 零 schema 路徑 | SPEC | 建議定案 |
| 8 | resolver 在裁後集合全被 reliability guard 踢掉時的實際行為（回 empty plan？raise？） | 決定 400 從哪裡渲染 | 待 probe（§8.1 真元件） |
| 9 | 持續預檢的觸發點：模型 CRUD hook？定時 job？告警走哪裡 | §4.1 配套 3 | 待設計 |
| 10 | `ModelInfo` 補 `credential_uuid` 的位置：正式欄位 vs `capabilities` | §4.1 wire | 小決策 |

---

## 7. 下一步

**設計序列（現在就走）**：

1. **`/research`** 產 §1.2 evidence pack（定位改為「收斂到客戶已審查／已簽約的供應範圍」，不是 data-residency）。
2. **`/doc-prd`** → 3. **`/doc-adr`** → 4. **SPEC + contract tests** → 5. **Core 對比表**（各項內容見下）。

**實作序列（設計閉環之後、本功能 PR 之前）**：

- a. **encrypted reasoning credential guard**（§4.6.1，規則由上面的 ADR 定義）：獨立 PR，含出站標記（選項 A）+ 入站比對；**與 #4876 `include` 修復同批或更早**。#4878 的驗證（跨 credential Responses 池 + Codex + 強制第一顆失敗）可借同一個 PR 的 fixture。
- b. **step 5 403 → 400**：PRD-157 amendment + 獨立 PR，在 `store=false` 強制上線前 merge。
- c. 本功能 PR。

設計序列各項：

1. **`/research`**（如上）。
2. **`/doc-prd`**：what / why + §4 客戶端驗收條件（斷言可觀察屬性），§1.3 的九條已知限制原樣搬進去；附 12 歲白話層。
3. **`/doc-adr`**：§4 八個決策點 + alternatives + invariants + ADR-093 表；必寫的 amendment：ADR-268（client-asserted id 作 authorization）、ADR-447（第四個 pre-filter、相反的降級語意、failover 集也裁、INV-447-6 優先序改為 latch > pin）、ADR-437 D4（§4.6.1 通用 credential guard，failover 候選受 minting credential 約束）、PRD-157（`store_source=policy` 落地、403→400）。
4. **SPEC + contract tests**：§6 的 4/7 兩項、fold intersection 反例、§8.1 真元件 probe（空集合真的走得到 400、failover 集真的被裁、L5 fallback 真的不寫 latch）。
5. **Core 對比表**（§17.4）：橫跨 **02 Policy & Authorization**、**01 Gateway & Streaming**、**06 Provider Integration & LLM Proxy**。
