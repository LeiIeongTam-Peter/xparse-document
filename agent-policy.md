# Agent Policy v1（Tool 規則）— 新 session 交接文件

> **用途**：給新開的 agent session 快速接手。讀完這份就知道這個功能是什麼、做到哪、還缺什麼、要去哪裡找東西、有哪些不能碰的規則。
> **更新時間**：2026-10-02。基準是 `origin/main`，已含 #5709（`320cc4391`）。
> **事實以 repo 為準**：這份是導覽，不是權威來源。權威是 `xparse/docs/` 裡的 PRD-337、ADR-490、SPEC-304；這份與它們衝突時，以它們為準。
> **路徑慣例**：除非寫明絕對路徑，路徑都相對於 repo 根目錄 `/Users/peter/Desktop/X-parse/xparse`。

---

## 0. 一句話

新增第三種 runtime policy kind `tool_governance`，顯示名「Tool 規則」。它讓管理員限制透過 Xparse 呼叫模型的 agent（Claude Code、Codex、OpenCode、客戶自建 agent）**能用哪些工具**：

- **請求端**：拿掉被禁的工具宣告，或整個拒絕帶工具的請求。
- **回應端**：模型仍呼叫被禁工具時，擋下那一整輪。

另外兩種 kind 的分工：Guardrail 管「說了什麼」，LLM Operational 管「量」，本 kind 管「模型要 agent 做什麼」。

**狀態**：v1 的 IAM、gateway、Console **全部已合入 main，但都還沒部署**。prod 由 pre-release registry（stage REL）扣住。

---

## 1. 功能本身

### 1.1 使用者能設的四個選項

| 欄位 | 值 | 預設 | 意義 |
|---|---|---|---|
| `mode` | `shadow`／`enforce` | `shadow` | 影子模式（僅稽核）／強制模式（拿掉／擋下） |
| `tool_use` | `allow`／`deny` | `allow` | `deny`：請求只要帶任何工具（含歷史裡的工具回合）就回 400 |
| `tool_names.deny` | 名稱清單（exact 或 glob，只收 `*` 和 `?`） | 空 | 命中的工具在請求端拿掉；模型仍回傳命中的名稱，就擋下整輪 |
| `tool_names.allow` | `null` 或非空清單 | `null` | 清單外的工具在請求端拿掉；模型回傳清單外的名稱，就擋下整輪 |

其他固定欄位：
- `schema: tool_governance/v1`：判別欄位。
- `actions`：保留欄位，v1 帶值會回 400 `POLICY_KIND_HAS_NO_TRIGGER`。

名稱比對規則：
- `deny` 不分大小寫，`allow` 區分大小寫。
- 不收 regex；拒絕只由萬用字元組成的樣式。
- 每層每份清單最多 256 條、每條最多 128 字元。

### 1.2 繼承（fold）

- 套用層級：tenant → group → application → deployment，**只能收緊**，下層放寬不了上層。
- **雙 lattice**：`enforced` 只收強制模式的貢獻，`observed` 收全部。gateway 只依 `enforced` 動作；兩者的差集發 `would_*` 稽核。這點和 guardrail 的 enforce-wins 刻意不同。
- `deny` 取聯集。`allow` 是各層合取：一個名稱要在每一層都命中才算允許，`null` 的層不參與。
- 沒有 `enabled` 欄位。要停用，就**從政策集移除這條規則的項目**，絕不能用 Invalidate（它會讓所有 kind 一起 fail-closed）。
- tenant／group 層級的 key 不投影本 kind（值是 null）。不能套到 `app_type=llm_proxy` 的 app，所有寫入路徑都會回 400。

### 1.3 三條 API 路徑的行為

| | `/v1/chat/completions`（OpenCode、自建） | `/v1/messages`（Claude Code） | `/v1/responses`（Codex） |
|---|---|---|---|
| 請求端 `tool_use: deny` | 400 `tool_not_allowed` | 400（Anthropic `invalid_request_error`） | 400 |
| 請求端名稱拿掉 | ✅ | ✅ | ✅（只比 `type=function`） |
| 回應端整輪擋下 | ✅ R-A in-band error | ✅ | ❌ v1.1 才做 |
| 對外說法 | — | — | 只能說「被禁工具的定義不送給模型」，**不能說「叫不動」**（P16：Codex 會執行模型吐出的被禁工具） |

請求端與回應端的細節：
- **全部拿掉時**：刪掉 `tools` 和 `tool_choice`。如果歷史裡還有工具回合，回 400。
- **`tool_choice` 指名的工具被拿掉**：改成 `auto`。
- **判定時點**：在 semantic cache lookup 之前。Tier V 稽核在拿掉之前擷取。
- **回應端出口**：
  - 不走 503，不觸發換模型的 fallback，也不記模型健康失敗。
  - 先 `aclose` manager 再讀 usage（P18 的結論）。
  - ledger 與 `EXECUTION_FAILED(tool_call_denied)` 都帶實際執行的模型。
- **一個被擋的回合可能是 2–3 個請求**：Claude Code 在串流被擋後會改送非串流，auto 模式還會拿掉 safeguards 再送一次。每個請求都各自完整判定、各自留稽核（C-304-158）。

### 1.4 稽核事件（Q7、Q12）

- `audit.policy.violation`：只用於真正的拒絕或擋下（請求端 400、回應端整輪擋下）。
- `audit.policy.tool_stripped`、`tool_would_block`、`tool_call_undeclared`、`tool_executed_despite_policy`：其他處置各有自己的事件。
- `audit.execution.platform_tool_stripped`：平台自己剝除 Responses 的非 function 工具時發（S0-b），回應也帶 `x-xparse-tools-stripped` header。
- 決策事件每請求上限 128 筆；拒絕事件不受這個上限限制（OQ-S9）。

### 1.5 舊開關 `PolicyProfile.tool_call_allowed`

- 過渡期跟本 kind 取 AND。
- 三條路徑都回 400 `tool_not_allowed`：
  - Responses：S0-c2（#5634）。
  - chat／messages：Q2，#5709 從 403 改成 400。
- 稽核的 `violation_code` 仍是 `TOOL_CALL_NOT_ALLOWED`，沒改。
- **R-a**（INV-490-25、C-304-100）：舊開關會拒絕、而且本 kind 依 `enforced` 也會動作時，由舊開關先回。
  - 這條規則仍有實質作用：本 kind 會拿掉工具時，它決定 client 收到 400 還是拿掉後照送。
  - **不能**簡化成只決定稽核歸屬。

### 1.6 和 June 的 ADR-427 的關係

- ADR-427 指的是 PR #3978 的草案（未 merge），編號與 main 上的 ADR-427（slot lease）撞號。
- 兩案定位為**正交並寫出組合規則**（Q3）：本案就是她路線圖 P4 的「宣告層授權」，參數層條件歸她。
- 回應端同一個掛點上，本案的名稱判定先跑。Responses 回應端要做成兩案共用的門。
- **不要動 PR #3978，也不要聯絡 June**（Peter 自己處理）。

---

## 2. 權威文件

| 文件 | 路徑 | 備註 |
|---|---|---|
| PRD | `docs/prd/PRD-337-agent-tool-governance-policy.md` | 需求、驗收（A／U／I／N 編號）、白話層 |
| ADR | `docs/adr/ADR-490-tool-governance-policy-kind.md` | 決策 D1–D21、§10 的 Q 表、§7 分段與 probe 表 |
| SPEC | `docs/spec/SPEC-304-tool-governance-behavioral-contracts.md` | 約 123 條 C-304、真值表 §10.1、OQ-S 表 |
| 研究 | `docs/research/RESEARCH-agent-tool-governance-proxy-enforcement-2026-09-30.md` | 競品先反駁的查證。結論：「能擋工具」不是差異化，站得住的只有組合 |
| Probe 證據 | `docs/research/poc/agent-tool-governance-probes-2026-10-01/README.md` | P2、P3、P7、P11、P16、P20，以及攔截器工具 |
| 本機驗證證據 | `docs/research/poc/agent-tool-governance-local-verification-2026-10-01/` | S0-b、P-POL-2、IAM 影子規則、P18、P19、G4 |
| 回滾 runbook | `docs/runbooks/tool-governance-rollback.md` | 混版、409→500、migration 0357 |
| Wiki | `xparse-wiki/wiki/concepts/tool-governance-policy.md` | 概念頁 |
| Glossary | `docs/governance/console-i18n-zh-tw-glossary.md` | 「Tool 規則」等譯名（§3.5.1） |
| Core | `docs/adr/core/Core-ADR-02-*.md`、`docs/prd/core/Core-PRD-02-*.md` | 主領域 02；01、03、04、05、06、08、10、12 有 cross-ref |
| 被取代的文件 | ADR-331（整份）、PRD-257（整份）、PRD-316 的 `agent` 半邊 | issue #2634 已改掛 PRD-337 |

**原始草案**（repo 外，僅供歷史參考）：`/Users/peter/Desktop/X-parse/docs/草案/agent-policy.md`（Rev.4）。

⚠️ **ADR-490 第 3 行的 Status 已過時**：還寫著 Q2「未合入」，實際 #5709 已 merge。下次文件同步時修正。

---

## 3. 程式碼地圖

### 3.1 IAM（`apps/iam/xparse_iam/xparse_iam/`）

| 檔案 | 作用 |
|---|---|
| `migrations/0357_adr490_tool_governance_policy_kind.py` | 放寬 versioned kind 的 CheckConstraint（expand-contract）。legacy `hierarchy.PolicyKind` **刻意不加** |
| `policies/tool_governance_content.py` | content schema 與驗證 |
| `policies/tool_name_matching.py` | 名稱比對：雙指標 glob，不用 regex |
| `authorization/tool_governance_resolver.py`、`tool_governance_fold.py`、`tool_governance_projection.py` | 解析、雙 lattice fold、validate 投影 |
| `api/ninja_api/_tool_governance_capability.py` | 能力 header `X-Gateway-Tool-Governance`：缺 header 且有強制貢獻時回 409（Q4 fail-closed） |
| `db/django_database/_tool_governance_targets.py` | 套用目標檢查，拒絕 llm_proxy |
| `core/pre_release_features.py` | registry entry `tool_governance`：stage REL、owner Peter、expires 2026-12-21 |
| `contracts/tool-governance-policy.v1.schema.json` | 投影的 wire 契約 |
| `contracts/tool-name-match.v1.json`（+`publisher`） | 名稱比對的 golden vectors，gateway 有逐位元相同的副本 |
| 測試 | `tests/{unit,integration,contract}/test_spec304_*.py` |

wire 的形狀：
- `/iam/internal/gateway-validate` 投影頂層鍵 `tool_governance_policy: {enforced, observed}`，沒套用時是 `null`（Q11 規定一定送）。
- 這個鍵**沒有**宣告進 `/iam/auth/validate`。

### 3.2 Gateway（`apps/gateway/bustream/`）

| 檔案 | 作用 |
|---|---|
| `gateway/tool_governance_projection.py` | 把投影解析成不可變 DTO；記 skew metric（Q11） |
| `gateway/tool_name_matching.py` + `contracts/tool-name-match.consumer.v1.json` | gateway 端的比對器與 vectors 副本 |
| `gateway/contracts/tool-governance-policy.consumer.v1.json` | 釘住的 consumer 契約 |
| `gateway/tool_governance_request.py` | 請求端計畫：拿掉工具、拒絕、`tool_choice` 處理 |
| `gateway/chat_tool_governance.py` | chat／messages 的 TG stage，含 R-a 先行 |
| `gateway/responses_tool_governance.py` | Responses 步驟 1.3：legacy、本 kind、平台剝除 |
| `gateway/tool_governance_response.py` | 回應端整輪擋下（R-A） |
| `gateway/tool_governance_decisions.py`、`tool_governance_errors.py`、`tool_governance_metrics.py` | 決策計數（128 上限）、固定文案、metric |
| `gateway/responses_tools_filter.py` | 平台剝除的計算與 header 編碼器 |
| `gateway/pre_execution.py` | `reject_tool_calls_not_allowed`：舊開關拒絕的唯一產生點 |
| `gateway/iam_http_client.py` | 送出能力 header（G3 起） |
| `gateway/routes/{chat,messages,responses}.py` | 三條路徑的接線 |
| `scripts/responses_tool_call_allowed_census.py` | 唯讀普查：找出 `tool_call_allowed=false` 的 app 與流量 |
| 測試 | `tests/integration/test_spec304_*.py`、`tests/unit/test_spec304_*.py`、`tests/contract/test_spec304_*_wiring.py`、`test_responses_tool_call_allowed_*.py`、`test_responses_platform_tool_strip.py`、`test_streaming_tool_call_detected.py` |

### 3.3 Console（`frontend/console-app-refactor/src/`）

| 檔案 | 作用 |
|---|---|
| `app/(main)/(ai-gateway)/policies/_components/policy/tool-governance-settings.tsx`、`tool-governance-content.ts` | 建立與編輯表單（4 個選項、名稱清單、範本） |
| `components/features/policy/tool-governance-binding.ts` | 套用目標檢查（隱藏 LLM Proxy） |
| `components/features/policy/tool-governance-effective*.ts(x)` | effective-policy 逐欄來源的顯示 |
| `app/(main)/(overview)/(dashboard)/_components/pre-release-rows.ts`、`_tabs/safety-policy/initial-layout.ts` | dashboard 的 Tool 規則違規列（G4） |
| `i18n/messages/{en,zh-TW}.json` | 譯名照 glossary：「Tool 規則」等 |

kind 的選項由 `usePreReleaseFeature('tool_governance')` 控制顯示。

### 3.4 CI gate

- `.github/scripts/tool-governance-parity-gate.py`（含 `--self-test`）：IAM vectors 與 gateway 副本逐位元一致，consumer 契約也完整。
- #5675 加的 AST 檢查：每個 `StreamingManagerV3(...)` 都必須接上 audit emitter，否則紅。
- `pre-release-feature-registry-gate`：IAM 與 Console 兩邊都必須列 `tool_governance`。

---

## 4. 交付時間軸（都已 merge，未部署）

| PR | 內容 |
|---|---|
| #5593 | 設計閉環：RESEARCH、PRD-337、ADR-490、SPEC-304 |
| #5612 | 第一輪決策（Q3、Q4、Q6、Q7、Q8、Q11、Q12；顯示名「Tool 規則」；S1 拆分） |
| #5623 | probe 證據（P2、P3、P7、P11、P16、P20） |
| #5621 | S0-c1：Responses 的 `tool_call_allowed` 影子 |
| #5618 | S0-b：平台剝除變得看得見 |
| #5614 | S1 IAM（migration 0357） |
| #5634 | S0-c2：Responses 的 `tool_call_allowed` 強制，回 400。只附 dev 普查，Peter 接受 |
| #5683 | 文件 Rev.3：probe 的 20 點影響與第二輪決策 |
| #5675 | 串流 chat／messages 補 `TOOL_CALL_DETECTED`（之前從沒發過） |
| #5685 | 本機實機驗證證據 |
| #5679、#5684 | P18 抓到的 bug：失敗回合的 tool call token 與 usage 記帳 |
| #5688 | G1：gateway 讀投影、DTO、契約、parity gate、skew metric（不處置、不送 header） |
| #5691 | G2：三條路徑的請求端 |
| #5696 | G3：chat／messages 回應端擋下，開始送能力 header |
| #5656 | Console：建立與編輯、effective 顯示、LLM Proxy 防護 |
| #5697 | G4：dashboard 列與 Console 鏡像 |
| #5709 | Q2：chat／messages 的舊開關 403 → 400 |

**部署順序**（已查證）：`deployments/operations/scripts/blue-green-deploy.sh` 的 `cmd_deploy` 依序是 IAM → gateway（切流量）→ Console，同一個版本，所以 Console 不會比 gateway 先上。
- 例外：`cmd_rollback` 只切 gateway 的顏色。回滾後如果有強制規則，那個 app 會回 500（Q4 fail-closed，runbook 有記錄）。

---

## 5. 實測得到的關鍵事實（設計依據）

- **P16**：請求端拿掉 `exec_command` 後，模型若依歷史仍吐出它，Codex **會照執行**。所以 Responses 的對外說法只能是「定義不送給模型」。
- **P7**：Codex 對 Responses 的 `event: error` 和 `response.incomplete` 都會重試 5 次（既有的 #4250 graceful 形狀也一樣）。
  - v1.1 的 Responses 擋下形狀候選：`response.completed`＋refusal，或 `response.failed(invalid_prompt)`。
  - chat／messages 採 R-A（in-band error）。OpenCode 不重試；Claude Code 會改送非串流加 auto 重送。
- **OpenCode 的重試字串**：錯誤文案不得含 429、500、502、503、504、524、try again later、timeout、rate limit 等字樣。有 golden TC 檢查（C-304-157）。
- **P2**：OpenAI 與 DeepSeek 在「全部拿掉＋歷史有工具回合」時回 200，但輸出不可用。所以這種情況維持回 400。
- **P3**：OpenAI 在沒有 tools 時，`tool_choice` 連 `"none"` 也回 400。
- **P18**：被擋時 `manager.run()` 的 finally 不會自動在讀 usage 之前跑完，必須先 `aclose`。
- **P19**：tenant／group 層級的 key 都打不到推論。但 tenant_auditor、group_admin、app_user 這三種是靠授權資料擋住，不是結構性的閘（待決，見 §6）。
- **Claude Code 2.1.285**：工具數 21–30 個。0 工具的命名請求只在互動 TUI 出現；`-p` 模式只送一個請求。
- **twin 路徑**：所有 ExecutionPlan 都是 direct，twin 是死路。

---

## 6. 還沒做的事、open 項目

### 6.1 需要部署或遠端授權（Peter 未授權，不要自己做）

- dev 真流量影子觀察至少一週。
- P14 回滾演練。
- 上 rel／prod 前，唯讀普查 `tool_call_allowed=false` 的 profile 數量（S0-c2 與 #5709 都需要）。0 就直接上，不是 0 就列出受影響的 app。
- **registry 畢業條件**（C-304-200）：上述三項加 P4、P5、P15 全部完成後，在同一個 PR 刪掉 registry entry 與兩端的 call site。

### 6.2 未決的設計問題

| 編號 | 問題 |
|---|---|
| Q1 | Responses 要不要開放 hosted 工具（`web_search` 等）。產品決策，v1.1 |
| Q13／OQ-S8 | v1.1 在同一個 kind 加欄位時的演進規則（回滾安全） |
| Q14／OQ-S11 | 「剛擋過」的短時效記錄，讓 Claude Code 的重送在打 provider 之前就被擋。v1 不做 |
| OQ-S2 | chat 的舊開關把 `tools: []` 算成帶工具，messages 不算，兩邊不一致 |
| OQ-S6 | chat 經 ADR-455 bridge 時，非 function 工具被無聲丟掉 |
| OQ-S13 | `tool_choice` 用 `allowed_tools` 形狀、而指名的工具被拿掉時怎麼處理（要先在 OpenAI 實測） |
| Q9 | v1.1 `tool_denied` trigger 的 `default_enforcement`（建議 observe） |
| — | P19 那三種角色要不要加結構性的 guard |
| — | 串流純文字回覆每次多 1 筆 `streaming_phase_changed` 稽核，能不能接受 |

### 6.3 v1.1 範圍（還沒開工）

- Responses 回應端 stage，要做成和 ADR-427 共用的門。
- `tool_types`（依 AG-D16 決定）。
- session 呼叫上限（需要 ADR-268 Amendment C）。
- `deny_as_tool_error`（error tool result 形狀，要有次數上限）。
- ADR-461 的 `tool_denied` trigger。

### 6.4 已開的 issue（都是 open）

| Issue | 內容 |
|---|---|
| #5666 | `tools: []` 加 `tool_choice` 送到 OpenAI 回 400 |
| #5667 | 4xx／5xx 錯誤缺 `X-Request-Id` |
| #5668 | ADR-455 bridge 遇到 incomplete 時，已累積的工具呼叫被丟掉 |
| #5669 | Responses 的終止 error frame 讓 Codex 重試 5 次 |
| #5670 | Responses 靜默丟掉 `tool_choice`／`parallel_tool_calls` |
| #5671 | Responses 工具的 `type` 是 list 或 dict 時回 500 |
| #5672 | C-304-68 套用預覽（IAM）未交付 |
| #5673 | Audit 的「從稽核挑名稱」彙總查詢 |
| #5674 | validate 熱路徑：每個 kind 各讀一次 scope |

#5605（`stop_sequences` 送給 GPT-5.x 回 400）已關閉。

### 6.5 小的 follow-up（還沒開 issue）

- skew metric 的 Prometheus 告警規則。
- R3 fallback 之後，稽核的 provider 歸屬仍寫主路徑。
- `test_azure_plan_resolver.py::test_azure_twin_plan` 是死測試（twin 已死）。
- SPEC-290 C-290-34 的註記。
- ADR-490 Status 行過時（見 §2）。

---

## 7. 環境與工作方式

### 7.1 本機 dev stack

- **gateway 與 IAM**：容器 `xparse-gateway`、`xparse-iam`，原始碼是 **bind-mount 主 checkout** `/Users/peter/Desktop/X-parse/xparse`。
  - 主 checkout 目前停在 `37f32868f`，落後 main，不含 #5709。
  - 要讓本機跑最新程式碼，得先 `git merge --ff-only origin/main` 再重啟容器。
- **入口**：
  - gateway：ingress `https://localhost:3000/v1/*`，自簽憑證。Node client 要設 `NODE_EXTRA_CA_CERTS=/Users/peter/Desktop/X-parse/xparse/certs/cert.pem`。
  - IAM：`https://localhost:3000/apis/iam/*`，或 Console dev server `http://localhost:4001/apis/iam/*`。
- **測試用 key**：放在 `/Users/peter/Desktop/testing/.env`。只用 `grep -E '^NAME='` 讀單一變數，**不要 cat 整個檔**（裡面有 provider key）。
  - `XPARSE_ADMIN_KEY`：tenant_admin，打推論會回 403。
  - `XPARSE_PROBE_KEY_816E`：app 5260605d 的 native key。
  - `XPARSE_PROBE_KEY_HYBRID`：Responses 用的 app 603adf8b。
  - 細節見 `docs/research/poc/agent-tool-governance-probes-2026-10-01/facts.md`。
- **app `5260605d-a3d8-4068-873e-b2ee5bf29c48`**：Peter 的測試 app，**不要動**。驗證時另建專用的 profile 和 app，驗完清掉。
- **client 版本**：
  - Codex 0.154.0：用隔離的 `CODEX_HOME`，不要改 `~/.codex/config.toml`。
  - Claude Code 2.1.285：用 `ANTHROPIC_BASE_URL` 和 `ANTHROPIC_AUTH_TOKEN`。
  - OpenCode 1.18.31：`~/.config/opencode/opencode.json` 指向 `http://localhost:4001/v1`。
- **攔截器**：`/Users/peter/Desktop/testing/tool_gov_interceptor.py`。可以錄製、模擬拿掉工具（`--strip-tools`）、模擬擋下（`--block-on-tool-call`）。
- **跑 PR 程式碼的 probe gateway**：從 worktree 起一個 probe gateway 容器，不要重啟共用容器。做法見 memory `reference_live_ab_two_probe_gateways.md`。

### 7.2 跑測試

不要用主機的 python。用 ephemeral 容器：

```bash
WT=<worktree>
docker run --rm --network none -v $WT:/w:ro -v apv1-g3-gwvenv:/w/apps/gateway/bustream/.venv \
  -w /w/apps/gateway/bustream -e XPARSE_ROUTING_DB_URL=sqlite:////tmp/r.db -e XPARSE_CACHE_SALT_SECRET=x \
  python:3.11-slim sh -c 'PYTHONPATH=/w/apps/gateway:/w/apps/gateway/bustream .venv/bin/python -m pytest -q -o addopts="" tests/integration/test_spec304_*.py'
```

- IAM：用 `python:3.11-slim` + `uv sync --extra dev --extra postgres --frozen`（Django 5.2）。見 memory `reference_iam_ephemeral_test_run.md`。
- Console：在 worktree 的 `frontend/console-app-refactor` 先跑 `pnpm install --offline --frozen-lockfile --ignore-scripts`，再跑 `tsc --noEmit`、`vitest`、`scripts/i18n-*.mjs`。

### 7.3 Git 與 PR 的固定套路

- **一律在 worktree 工作**：`/Users/peter/Desktop/X-parse/pr-worktrees/<name>`，從 `origin/main` 開分支。
  - 這次用過的是 `apv1-*`，都已 merge，可以清掉。
- **驗收產生檔**（5 個：`docs/testing/feature-inventory/*.json`、`docs/testing/qa-evidence-v2/excel-inventory.json`、兩個 `docs/testing/*.xlsx`）幾乎每次 merge main 都會衝突。處理方式：
  1. `git merge origin/main`，不要 rebase。
  2. 這 5 個檔取 theirs。
  3. 另開一個 commit 跑 `python3 scripts/testing/build_feature_acceptance_workbook.py --write`。
  4. 再跑 `--check`。
- **merge main 時的 commit 用 `--no-verify`**：否則 pre-commit hook 會把 main 帶進來的前端檔重新排版，混進 PR 的 diff。
- **堆疊分支的合併**：先合上游 PR，再把 main merge 進下游。衝突檔如果 `git diff --quiet <上游最後 head> origin/main -- <file>` 成立，就取 ours。
- **PR 描述**：
  - `Acceptance-Impact: none` 必須單獨一行。
  - 改到程式碼的 PR 要附 ADR-093 五列表。
  - 結尾加 `🤖 Generated with [Claude Code](https://claude.com/claude-code)`。
- **commit 訊息**結尾加 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。
- **合併**：repo 不允許 auto-merge，要手動 `gh pr merge <n> --squash`。PR 的 base 必須是 `main`。
- ⚠️ **`~/.gitconfig` 又出現 `url.https://x-access-token:...@github.com/.insteadof`**，`git fetch` 會 401。不要改 global config。遇到時回報 Peter，或用一次性的 URL 繞過。見 memory `reference_git_push_insteadof_empty_token.md`。

### 7.4 Peter 的硬性規則

- **不准用 `git stash`**：所有 worktree 共用 `refs/stash`，裡面有 Peter 的舊 stash。
- **主 checkout 的本機狀態要保留**：`3rd/xparse_audit` 的改動、`frontend/console-app/`、`pr-worktrees/` 都不准 reset、clean 或 stash。
- **不准建強制模式的 Tool 規則**（本機也不行，除非 Peter 明說）。
- **不做部署或遠端環境操作**（rel／prod 的查詢只能寫成 follow-up）。
- **不動 PR #3978，不聯絡 June。**
- **不把任何 key 寫進 commit、PR、文件或證據。**
- **遇到以下情況要停下來問**：要建強制規則、要部署或做遠端操作、結果推翻了 ADR-490／SPEC-304 的核心決策、要改到 #3978。

### 7.5 其他參考

- **Memory**：`/Users/peter/.claude/projects/-Users-peter-Desktop-X-parse-xparse/memory/project_agent_policy_v1_design_closure.md`（本功能的進度摘要），以及 `MEMORY.md` 索引裡的相關 reference。
- **既有研究**：`docs/research/RESEARCH-agent-client-block-status-retry-behaviour-2026-09-15.md`，記錄三家 client 對各種 HTTP 狀態碼的重試行為。

---

## 8. 建議的下一步

1. 先跑 `git fetch` 和 `git log origin/main`，確認 §4 的 PR 都在，也看看有沒有新的相關 commit。
2. 修 ADR-490 Status 行等小的文件落差（純文件 PR）。
3. Peter 授權部署後：
   - rel／prod 唯讀普查。
   - dev 影子觀察一週。
   - P14 回滾演練。
   - registry 畢業 PR。
4. 依 Peter 的優先順序處理 §6.4 的 issue，或 §6.2 的設計題。
5. 開 v1.1 之前，先決定 Q13（加欄位的演進規則）與 Q1（hosted 工具），並在 OpenAI 實測 OQ-S13。
