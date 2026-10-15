# Agent client 打不進 LLM Proxy：PII rail 對結構化 content 的三個缺陷

> 一句話總結：**任何用 OpenAI SDK 形狀（`content` 是 parts 陣列）的 agent client，只要對話裡出現一個被 GLiNER 判定的 span，就會拿到 451 且永遠無法自癒。** 不是 endpoint 不支援結構化 content —— 三個入口面都正常收、正常推論；451 純粹來自 guardrail **偵測得到、但寫不回去**，於是依 fail-closed 轉成擋。平台把遮罩寫回結構化 content 的能力**已經有三份現成實作**（稽核路徑、tool_calls 參數、`/v1/messages` 翻譯層），只差沒有接到外送路徑上。

文件對象：接手修這條的人。每個結論都附實測指令或 code 位置，可原地重跑。
日期：2026-09-14
環境：local dev stack（`xparse-gateway` / `xparse-guardrails`，GLiNER 指向 `XPARSE_GLINER_SERVER_URL=http://220.133.105.233:18005`），application code `gpt_4o_816e`，rail `mode=enforce` / `pii.action=mask`
證據取得時的本地 HEAD：`0dbd6f07b`

> **狀態（2026-09-14 晚）**：三個缺陷已在 **PR #4806**（branch `fix/adr448-amendment-e-text-parts-rewrite`，base main）修復——設計閉環 ADR-448 Amendment E / SPEC-219 Rev.6 / ADR-296 Amendment C，gateway 程式碼 + 20 個新測試，並對真 sidecar／真 GLiNER 跑 ephemeral gateway 矩陣（§3 的 a–g 全數翻綠：parts 陣列 200 且模型回遮罩 token、夾圖仍 451、`/v1/responses` 變 422、15k 字 system prompt 走預設預算 200）。**待 merge → dev 樹 pull → recreate gateway 之後**，§8 的 `.env` 兩個 override 與 OpenCode 的 anthropic provider 才可撤。本文兩處事實已依複驗更正（缺陷 B 的狀態碼、§4 的「預設送法」）。

> ⚠️ **本地樹落後 `origin/main` 31 個 commit**（`git rev-list --count HEAD..origin/main` = 31）。下列行號以 `0dbd6f07b` 為準，動手前先對 `origin/main` 重新定位這幾個函式，不要照抄行號。

相關 ADR / SPEC：**ADR-448**（偵測面與內容衍生 token；D3 / Amendment B B-2 / B-3 是本文的直接關係人）、**ADR-296**（redact action 與 input mutation，INV-296-4 fail-closed）、**ADR-309 / SPEC-219**（GLiNER PII v1）、**ADR-239**（`/v1/messages` ingress）
觸發本文的實際場景：OpenCode（`@ai-sdk/openai-compatible` → `http://localhost:4001/v1`）對 `gpt_4o_816e` 送一句 `hi` 就被擋。

---

## 1. 症狀

使用者在 OpenCode 裡只打了一句 `hi`，輪流拿到三種錯誤：

```
Request blocked by guardrail: engine_timeout   [retrying in 8s attempt #3]
Request blocked by guardrail: pii
Request blocked by guardrail: unredactable_span
```

同一把 API key、同一個 application、同一個 local gateway，用 `~/Desktop/testing/main.py`（送**純字串** content 的單則 user message）**完全正常**。

差別不在 key、不在 application、不在 rail 設定，而在**訊息形狀**：agent client 送的是

```json
{"role": "user", "content": [{"type": "text", "text": "hi"}]}
```

而不是 `"content": "hi"`。

---

## 2. 三個獨立缺陷

三種錯誤訊息對應三個獨立問題，修一個不會讓另外兩個消失。

### 缺陷 A（主因）— 遮罩寫不回結構化 content，於是 fail-closed 成 451

rail 設定是 `pii.action = "mask"`，sidecar 也確實回 `modify` 並附上遮罩後的文字。卡在最後一步：gateway 要把結果寫回訊息時，發現 `content` 是 list，直接放棄。

兩條路徑各有一份，**都只認 `str`**：

| 路徑 | 位置（`0dbd6f07b`） | 行為 |
|---|---|---|
| last-turn 改寫 | `apps/gateway/bustream/gateway/guardrail_handler.py:949-967` `_write_last_user_message` | `isinstance(msg.get("content"), str)` 才寫；否則 `return False  # multimodal/list content — caller fail-closes` |
| 同上的 caller | `guardrail_handler.py:380-390` | `applied` 為 False → `raise _redaction_failclosed(...)` → 451 `input_blocked` |
| Responses `input` | `guardrail_handler.py:939-946` `_apply_input_redaction` | `isinstance(input_value, str)` 才寫，list input 同樣回 False |
| 寬偵測面 | `apps/gateway/bustream/gateway/guardrail_detection.py:196-214` `_content_text` | list content 抽得出 text，但一律標 `rewritable=False` |
| 寬面的 caller | `apps/gateway/bustream/gateway/guardrail_input_surface.py:271-285` | `not entry.rewritable` → `done("block", VIOLATION_UNREDACTABLE, ...)` → 451 |

`_apply_input_redaction` 的 docstring 自己寫明了：

```
Only **string** content is mutated in v1; list / multimodal content returns ``False``
so the caller fail-closes rather than mis-applying a text mask onto a structured payload
(ADR-296 §2.3 / INV-296-4).
```

決定性 log（使用者實際請求，`XPARSE_PII_WIDE_SURFACE_ENFORCE=false` 時走 last-turn 路徑）：

```
[guardrail] {"guardrail_event":"input_check", "guardrail_verdict":"modify", "violation_type":"pii", ...}
[Guardrail] Input modify verdict could not be applied (empty or non-string/multimodal payload)
            — fail-closed block. request_id=f59ebddd-366c-45fd-87a2-b78c13684940
```

verdict 是 **modify**（遮罩算出來了），最後卻變成 block。

寬面開啟時走另一條，log 會指名位置：

```
[Guardrail] unredactable_span — a detected span sits where v1 cannot rewrite
            (position=2:content); failing closed (request_id=0455e57b-...).
```

### 缺陷 B — per-call timeout（5s）比 scan budget（8s）還短

```python
# apps/gateway/bustream/gateway/app.py:671
GUARDRAIL_TIMEOUT_SEC = float(os.getenv("XPARSE_GUARDRAIL_TIMEOUT_SEC", "5.0"))

# apps/gateway/bustream/gateway/guardrail_input_surface.py:75
DEFAULT_SCAN_BUDGET_MS = 8000.0
```

兩個獨立常數，單次 sidecar 呼叫的上限比整個請求的掃描總預算還短 —— budget 永遠輪不到就先被 per-call timeout 砍掉。

而 agent client 的 system prompt 動輒 10–20 KB，ADR-448 B-4 自己量的是 **「sidecar 延遲 ≈ 0.43 ms/字，13k 字冷啟動 5–7 s」** —— 也就是說**設計時就知道冷啟動會超過 5 秒**，卻把 per-call timeout 留在 5 秒。

實測（本機遠端 GLiNER，`/v1/extract`，chunk 384 / overlap 32）：

| 文字長度 | 延遲 |
|---|---|
| 157 chars | 0.25 s |
| 785 chars | 0.42 s |
| 3,140 chars | 1.40 s |
| 9,420 chars | 4.36 s |

17 KB 的 system prompt 實測單次 engine call **8.2 s**（gateway log `surface_duration_ms=8189.5`）。

超時後 `guardrail_enforcer.py:504-512` 回 `violation_type="engine_timeout"`，經 `guardrail_response._FAIL_CLOSED_VIOLATIONS` 對映成 **503 `guardrail_timeout`**（**更正**：本文初版寫 451；`engine_timeout` 是 fail-closed 引擎類，一律 5xx）。這也解釋了 §1 畫面上的 `retrying in 8s attempt #3`：AI SDK 對 5xx 自動重試、對 451 不會。

另外，fail-closed 的代價本來就是拒絕，「早 3 秒失敗」換不到任何東西 —— 這個 timeout 短設沒有任何收益。

> **2026-09-14 晚補記（PR #4806 merge 後 dev 實測）**：鏈上其實有**三個**常數，不是兩個——gateway per-call（已改為剩餘預算）、gateway 預算（已改 30 s）、**sidecar → GLiNER 的 `XPARSE_GLINER_TIMEOUT_MS`（`gliner_client.py:38`，預設 15000）**。GLiNER 負載高時 15k 字要 24 s，sidecar 15 s 就回 502，gateway 記成 `engine_error` **503**——所以 #4806 之後長 system prompt 仍可能 503，只是錯誤碼從 `guardrail_timeout` 變 `guardrail_service_unavailable`。dev compose 的 guardrails service 沒有這個 knob 的 passthrough，`.env` 寫了也無效；本機暫用 `~/Desktop/testing/guardrails-gliner-timeout.override.yml` 拉到 30000。**這是 Amendment E 沒涵蓋的第四個缺陷，修在 PR #4807（ADR-448 Amendment F / SPEC-219 Rev.7 C-219-46）**：gateway 把剩餘預算以 `timeout_ms` 帶進 `POST /v1/guardrails/check`，sidecar 以它為 GLiNER timeout（真元件判別：同一段 15k 字，`timeout_ms=2000` → 502@2.1 s、不帶 → 502@15.1 s）；compose 補 `XPARSE_GLINER_TIMEOUT_MS` passthrough。merge 後本地要 rebuild sidecar image 才吃到。

### 缺陷 C — block / timeout 從不進 cache，失敗永久重演

```python
# apps/gateway/bustream/gateway/guardrail_input_surface.py:265
if cache is not None and result.action in ("pass", "modify"):
    cache.put(...)
```

`guardrail_mask_cache.py` 的設計前提是「agent loop 每輪重送整串歷史，所以 1..N-1 上一輪掃過」。但**只有 pass/modify 會被記住**。一旦某則訊息第一次掃就 timeout 或 block：

- 不寫 cache
- 下一輪同樣的訊息 → 再掃一次 → 再 timeout/block
- client 自動重試 → 完全相同的結果

使用者看到的 `[retrying in 8s attempt #3]` 就是這個。**沒有任何自癒路徑**，只能改設定或改 client。

---

## 3. 實測矩陣：面 × content 形狀

同一段含 PII 的文字（`Peter Chen is 19 years old, email peter@example.com.`），只改入口面與 content 形狀：

| 入口面 | content 形狀 | 結果 |
|---|---|---|
| `/v1/chat/completions` | 純字串 | ✅ 200，真的遮罩 |
| `/v1/chat/completions` | 純文字 parts 陣列 | ❌ **451** `Request blocked by guardrail: pii` |
| `/v1/chat/completions` | parts 陣列、**不含 PII** | ✅ 200（沒偵測到就不會走到寫回） |
| `/v1/messages` | 純字串 | ✅ 200 |
| `/v1/messages` | 純文字 parts 陣列 | ✅ 200，**遮罩正確** |
| `/v1/responses` | `input` = item list 含 PII | ❌ **451** |

**關鍵對照**：同一份內容，`/v1/messages` 會遮、`/v1/chat/completions` 會擋。差別在 Anthropic 面的翻譯層把 text block 摺成 `str` 之後才進 guardrail，chat 面沒有這一層。

`/v1/messages` 完整 agent loop 實測（`system` 為 array 帶 `cache_control`、`tool_use` + `tool_result` 往返、寬偵測面開啟）：

```
HTTP 200 (3.1s)
模型收到：OWNER = '[NAME_91dcf772]'  # [EMAIL_5e2d1b13]
log: surface_messages=5, scanned=4, engine_calls=4, masked_messages=2, unrewritable_detections=0
```

連 **tool_result 裡的 PII 都被正確遮罩**，零 451。證明「遮罩結構化對話歷史」這件事在平台上是**做得到的**，chat 面只是沒接。

> 附帶發現（另一條線，不在本文修法範圍）：`/v1/responses` 上，**含 PII 的請求拿到 451，不含 PII 的同一請求拿到 422**（`this application has no model on the /v1/responses surface`）。guardrail 跑在 admission 之前，於是 451 掩蓋了真正的 422。這會讓 client 看到誤導性的錯誤分類。

---

## 4. ADR-448 的決策前提與實測不符

現行行為出自兩個已拍板的決策：

- **D3**（2026-09-11，Peter）：「list content 維持 fail-closed」
- **D8 / Amendment B B-2**（2026-09-13）：`unredactable_span` 改為 fail-closed 451

但 B-2 接受 451 的理由寫的是：

> 「Amendment B 之後改寫面已涵蓋所有 `str` content 訊息與 tool call 參數的字串葉值，`/v1/messages` 的純文字 block 在翻譯層摺成 `str`，所以**會落到 451 的只剩夾帶圖片的多模態訊息**與無法解析的參數」

**實測推翻這個前提**：OpenAI chat 面的**純文字** parts 陣列（沒有圖片、沒有任何非文字 part）一樣落到 451，而 OpenCode 實際就會送出這個形狀。（**更正**：初版寫「多數 OpenAI SDK 的預設送法」過度概括——OpenCode 內嵌的 AI SDK openai-compatible provider 對**單一** text part 的 user turn 會摺成字串〔binary 可 grep 到 `content.length===1&&…type==="text"` 的摺疊分支〕，只有**多 part** 的 user turn 才送陣列；OpenCode 的 user turn 會帶多個 text part，所以精確說法是「任何多 part 的 user turn」，結論不變。）當初以為只會影響「夾帶圖片」的邊緣情況，實際上影響的是 agent client 大部分的請求。

所以要改的不是「推翻 fail-closed 原則」，而是**修正 D3 的適用範圍**：純文字 parts 可以安全改寫，真正該維持 451 的只有 B-2 原本設想的那些（image block、無法解析的 arguments）。

---

## 5. 這個能力平台已經有三份現成實作

修法不需要發明任何東西，照抄即可：

| # | 位置 | 做法 |
|---|---|---|
| 1 | `apps/gateway/bustream/audit/content_redactor.py:182-209` `_enrich_messages` | list content **逐 part 遮 `text`，非文字 part 原樣 append** |
| 2 | `apps/gateway/bustream/gateway/guardrail_detection.py:157-175` `tool_call_arguments_text` + `_string_leaves` / `_replace_string_leaves` | JSON 字串葉值級遮罩，拆回原結構；`rewritable=True` |
| 3 | `/v1/messages` 翻譯層 | text block 摺成 `str` 再進 guardrail |

第 1 份跟本文要修的形狀**一模一樣**（同一個 `content` 欄位、同一種 list-of-dict-with-text）。ADR-448 §1.2 自己記了這件事：

> 「平台已經在做正確的事，只是方向朝內 —— 保護自家稽核庫的力度高於保護客戶資料的外送路徑。」

---

## 6. 修法提案

> 依 CLAUDE.md §17.1，先補設計閉環再寫碼。

### P1 — 設計

**ADR-448 Amendment E**：修正 D3 的適用範圍。要寫清楚的三件事：

1. 純文字 parts 陣列（每個 part 都是 `{"type": "text"|"input_text", "text": str}`）納入**改寫**面，做法為 leaf-wise（照 `tool_call_arguments_text` 的既有形狀）。
2. 維持 451 的精確條件：含非文字 part（image / audio / document block）、或無法解析的 arguments。條件要能靜態判定，不能靠「試著寫寫看」。
3. B-2 的前提更正：記錄「當初以為只剩圖片多模態會落 451，實測純文字 parts 陣列也落」這件事本身，避免下一次又據此推論。

同步更新 **SPEC-219** 的 `unredactable_span` 契約條款（`docs/spec/SPEC-219-guardrail-pii-v1-contract.md:224` 附近）。

§17.4 Core 對比表：領域 02 Policy & Authorization。

### P2 — 實作

| # | 檔案 | 改動 |
|---|---|---|
| 1 | `gateway/guardrail_detection.py` `_content_text` | 全部 part 皆為 text ⇒ 回 `rewritable=True`；混入非文字 part ⇒ 維持 `False` |
| 2 | `gateway/guardrail_detection.py` `write_back` / `_write_content` | 新增 list 分支：把遮罩文字依 separator 拆回各 part 的 `text`，葉數不符則回 False（比照 `tool_call_arguments_text` 的葉數檢查） |
| 3 | `gateway/guardrail_handler.py` `_write_last_user_message` | 同樣支援 list content；**注意這裡與 #2 是兩份獨立實作，別只改一邊**（這正是今天兩種不同錯誤訊息的來源） |
| 4 | `gateway/guardrail_handler.py` `_apply_input_redaction` | Responses `input` 為 item list 時比照處理；若判定風險太高可分離為獨立 PR，但要在 Amendment E 明說 |
| 5 | `gateway/app.py:671` + `guardrail_input_surface.py:75` | per-call timeout 改為**從 scan budget 導出**，不再是兩個獨立常數；預設值以 ADR-448 B-4 的「13k 字 5–7 s」為基準往上取（建議 per-call ≥ 15 s、budget ≥ 30 s），讓 agent client 開箱即用、不必在 `.env` 覆寫 |
| 6 | `gateway/guardrail_input_surface.py:265` | 決定 timeout 是否值得記一筆負向 cache（避免同一則超長訊息每輪重炸）。**這是設計決策，要在 Amendment E 拍板**，不要逕自實作 |

同時要重產 `apps/gateway/bustream/config/runtime.schema.json`（`python3 scripts/publish_runtime_config.py`，勿手改），否則 owner-suite job 會紅。

### P3 — 驗證（§8.1，非協商）

不可只用 fake 驗 handler。必須對**真 gateway → 真 sidecar → 真 GLiNER** 跑矩陣：

- 三個入口面 × {純字串, 純文字 parts 陣列, 含 image block 的 parts 陣列} × {含 PII, 不含 PII}
- 斷言不只是「HTTP 200」，要斷言**模型實際收到的是遮罩後的文字**（做法：請模型列出收到的中括號 token，見 §7 的 probe）
- 含 image block 的那格要斷言**仍然 451** —— 這是唯一該保留的 fail-closed
- 既有測試 `tests/unit/test_adr448_pr5_enforce_surface.py`、`test_adr296_multi_turn_detection_surface.py`、`test_spec219_gateway_dual_shape.py` 要跟著更新

參考既有的真元件矩陣腳本：`~/Desktop/testing/pii_enforce_matrix.py`（ADR-448 Amendment B 就是用它量出來的）。

---

## 7. 重現腳本

都對 local dev stack 跑，key 取 `~/Desktop/testing/.env` 的 `XPARSE_API_KEY2`。

### 7.1 最小重現（缺陷 A）

```python
import json, urllib.request, urllib.error
key = [l.split('=',1)[1].strip() for l in open('/Users/peter/Desktop/testing/.env')
       if l.startswith('XPARSE_API_KEY2=')][0]
TEXT = "Peter Chen is 19 years old, email peter@example.com. Say hi."

def call(tag, content):
    payload = {"model": "gpt_4o_816e", "messages": [{"role": "user", "content": content}]}
    req = urllib.request.Request("http://localhost:4001/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            print(tag, "HTTP 200", json.loads(r.read())["choices"][0]["message"]["content"][:60])
    except urllib.error.HTTPError as e:
        print(tag, "HTTP", e.code, e.read().decode()[:120])

call("string:", TEXT)                              # → 200
call("array :", [{"type": "text", "text": TEXT}])  # → 451 guardrail: pii
```

### 7.2 證明遮罩真的到達模型（給修完之後驗收用）

```python
q = ("List every token in square brackets that appears in the following line, one per line. "
     "If there are none, say NONE.\nLine: Contact Peter Chen at peter@example.com or 0912-345-678.")
```

送成 parts 陣列，修好後模型應回 `[NAME_xxxxxxxx]` / `[EMAIL_xxxxxxxx]` 之類的 token。
目前在 `/v1/messages` 上會回（實測回了 `[MESSAGING_ID_17770f33]`），在 `/v1/chat/completions` 上會 451。

### 7.3 量 GLiNER 延遲（缺陷 B）

```python
payload = {"text": text, "labels": ["person", "email", "phone number"],
           "threshold": 0.5, "chunk_length": 384, "overlap": 32, "flat_ner": True}
# POST http://220.133.105.233:18005/v1/extract
```

### 7.4 看 verdict

```bash
docker logs xparse-gateway --since 5m 2>&1 | grep -E '"guardrail_event"|\[Guardrail\]'
```

---

## 8. 現況：本機已套的暫時繞法（修好後要撤掉）

為了讓使用者當下能繼續用 OpenCode，已經改了兩處。**這些都是繞法，不是修復**，PR 合併後應該回退：

1. `~/Desktop/X-parse/xparse/.env` 追加三個覆寫：

```
XPARSE_GUARDRAIL_TIMEOUT_SEC=25      # 繞缺陷 B
XPARSE_PII_SCAN_BUDGET_MS=40000      # 繞缺陷 B
XPARSE_PII_WIDE_SURFACE_ENFORCE=true # 維持完整偵測面（這個是正確值，不是繞法）
```

2. `~/.config/opencode/opencode.json` 新增 provider `xparse-local-claude`（`@ai-sdk/anthropic` → `http://localhost:4001/v1`），把 OpenCode 從 chat 面改走 `/v1/messages`。原檔備份在 `opencode.json.bak-2026-09-14`，原 provider `xparse-local` 保留可切回。

缺陷 A 修好後，`xparse-local`（chat 面）應該就能直接用；缺陷 B 修好後，`.env` 的兩個 timeout 覆寫應該可以整個刪掉。**這兩件事就是這次修法的驗收條件。**

---

## 9. 待決問題（留給 Amendment E 拍板）

1. **負向 cache**：engine timeout 要不要記一筆短 TTL 的負向結果？記了可避免每輪重炸，但會讓「暫時性 timeout」黏住一段時間。（缺陷 C）
2. **Responses `input` list** 要不要跟 chat 面同批修？結構不同（item list vs content parts），風險不同。
3. **guardrail 與 admission 的順序**：目前 guardrail 跑在前面，導致「不能服務的請求」回 451 而不是 422（§3 附帶發現）。這是否算 bug、要不要一起處理。
4. **真正該 451 的清單**：image / audio / document block 之外還有哪些？判定要能靜態完成。

---

## 9a. 補記（2026-09-14 21:45，#4806 + #4807 皆已部署到 dev）

三缺陷 + sidecar deadline 都修好之後，OpenCode 在 repo 目錄下**仍然** `engine_timeout`。這次不是 bug：gateway log 每輪 `surface_messages: 2, engine_calls: 1`，sidecar 準時在 **30.07 s** 回 502（deadline 傳遞正確）——那一則是 system prompt，OpenCode 會把 cwd 的 `AGENTS.md`／`CLAUDE.md` 摺進去（`xparse/AGENTS.md` 36k 字；`X-parse/` 16k + 37k 字），加上它自己的 base prompt 超過 40k 字；air520 那台 CPU GLiNER 高載時 ~1.3k 字/s（3k 字 2.2 s），30 s 掃不完。而 timeout 依 C-219-45 **刻意不進快取**，所以永遠暖不起來。

dev 暫解：`.env` `XPARSE_PII_SCAN_BUDGET_MS=120000`（首輪 40–60 s、之後 system prompt 命中快取）。**待決（設計題，不是 bug）**：
1. **容量**：GPU GLiNER 或多節點——唯一讓「冷啟動 40k 字」變合理的路（#4739）。
2. **per-message 字元上限**：超過即刻 451 帶專屬 code，讓失敗變成 0 s 且可行動，而不是等 30 s；不讓它變能用。
3. **政策旋鈕**：允許 tenant 對 `system` 角色關掉 PII 掃描（agent client 的 system prompt 是開發者寫的、幾乎不含終端使用者個資）——但這推翻 Amendment C 的一部分（RAG／persona 名冊也在 system），要 Peter 拍板。
4. **跨重啟的快取**／預熱——不救冷啟動，只救 gateway 重啟。

## 10. 一句話給接手的人

不要從「怎麼讓 OpenCode 過」下手，那是繞法。從**「遮罩寫回結構化 content」這個能力為什麼只存在於稽核路徑和 `/v1/messages`，沒接到 chat 面**下手 —— `audit/content_redactor.py:197-207` 那 11 行就是答案的形狀。
