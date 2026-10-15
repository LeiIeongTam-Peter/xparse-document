# Word filters（自訂詞過濾）— 功能說明與交接文件

**狀態：** 已上線（PR [#3449](https://github.com/futurenestit/xparse/pull/3449) **已 merged**，後續修正 [#3450](https://github.com/futurenestit/xparse/pull/3450) shadow dispatch 500）
**第二輪（偵測強度還債）：** 見 §10 — 字元類別從列舉改推導、關掉無分隔拉丁詞、fold 後詞數界、probe 改引用真模組
**日期：** 2026-08-13（初版）· 2026-08-13 第二輪更新
**設計文件：** PRD-285（what/why）· ADR-389（how，含 §4.1 amendment）· SPEC-224（行為契約 `C-224-*`，含 C-224-53）
**證據：** [RESEARCH-word-filter-recognition-third-party-landscape-2026-08-13](../xparse/docs/research/RESEARCH-word-filter-recognition-third-party-landscape-2026-08-13.md)（第三方景觀 + 三支 probe）
**起點：** `docs/草案/自訂PII.md`（2026-08-12 需求草案）

---

## 0. 一句話

讓管理員直接列出「不能流出公司的字詞」，選擇**擋下來**或**換掉**——因為自動個資偵測在結構上抓不到它們。

---

## 1. 這是什麼

### 1.1 要解決的問題

Guardrail 原本有三條 rail：

| rail | 判斷什麼 | 機制 |
|---|---|---|
| `pii` | 有沒有個資 | GLiNER 語意層 + regex 格式層（機率式）→ 遮罩 |
| `on_topic` | 有沒有離題 | LLM 判官 / 專用模型 → 阻擋 |
| `content_filter` | 有沒有踩線 | LLM 判官 / 外部分類器 → 阻擋 |

三條都**無法表達「這個特定字串不准出去」**：

- `pii` 的分類法是**平台定義的封閉 12 類**。`Project Falcon` 不屬於任何一類，它沒有任何個資特徵，`score_threshold` 調到多低都不會出現它。
- `on_topic` / `content_filter` 是主題與內容分級判斷，不是字面比對。要它們攔一個代號，等於用 LLM 判官做 exact match——不可靠、有 token 成本、且會被 prompt injection 影響。

結果是一整類客戶明講的需求完全沒有落點：金融的 MNPI 與併購案代號、國防與政府的 CUI marking 與 program 代號、法律的 matter codename、科技業的未發布產品代號與競品名、企業內部的系統與主機名。

### 1.2 新增的第四條 rail

```yaml
guardrail:
  version: v2
  mode: shadow | enforce
  pii: { ... }                      # 完全不動
  classifier: { ... }               # 完全不動

  word_filters:                     # 新增
    enabled: true
    terms:
      - term: "iPhone 18 Pro"
        action: mask
        replacement: "我們即將推出的旗艦手機"
      - term: "獵鷹計畫"
        action: mask                # replacement 省略 → 自動變 [CUSTOM_1]
      - term: "Project Falcon"
        action: block               # block 不接受 replacement
```

### 1.3 為什麼不併進 `pii`

六個面向**全部相反**——併在一起等於把兩種相反的調校方向塞進同一組旋鈕：

| # | 面向 | `pii` | `word_filters` |
|---|---|---|---|
| 1 | 偵測機制 | 機率式（`score_threshold` 0~1） | 確定性（中就是中） |
| 2 | 動作集 | 只有 `mask`（ADR-309 已把 block 降級） | 需要 `block` + `mask` |
| 3 | 分類法性質 | 封閉 12 類、平台定義 | 開放清單、租戶自訂 |
| 4 | 機密性 | 類別名不敏感（`person_name`） | **詞本身就是機密** |
| 5 | 每項附屬屬性 | 無（只是勾選） | 每個詞帶 `action` + `replacement` |
| 6 | 失敗模式 | 漏抓（recall） | 誤抓（precision） |

第 2 點還有額外代價：在 `pii` 內復活 `block` 會推翻已交付的 PRD-241 NG3。

---

## 2. 怎麼用（管理員視角）

### 2.1 授權路徑

Console → **Policies** → 建立或編輯 guardrail policy → **自訂詞過濾** 區塊 → 開啟開關 → **新增詞**。

每一列填三件事：

| 欄位 | 說明 |
|---|---|
| **詞** | 要控管的確切字詞，至少 2 個字元 |
| **動作** | `封鎖`（整個請求擋下）或 `遮罩`（換掉後照樣送出） |
| **替換文字** | 只有 `遮罩` 才有。留空則自動換成 `[CUSTOM_1]` 這類編號代號 |

### 2.2 兩種動作怎麼選

| 客戶意圖 | 詞的性質 | 該選 |
|---|---|---|
| 「這東西不能被外部模型知道」 | 未發布代號、deal codename、MNPI、CUI marking | **封鎖** |
| 「值不能外流，但事情要照做」 | 產品代號、內部系統名、競品名 | **遮罩** + 概括性的替換文字 |

**遮罩的價值在於它把「挖空語意」變成「泛化語意」：**

```
使用者問：iPhone 18 Pro 的螢幕多大？

→ [CUSTOM_1] 的螢幕多大？          模型：「請問是哪款產品？」   ❌ 白問
→ 我們即將推出的旗艦手機的螢幕多大？  模型：可以正常回答           ✅
```

### 2.3 ⚠️ 兩種動作的**涵蓋範圍不一樣**（最容易誤解的一點）

| 動作 | 檢查範圍 |
|---|---|
| **封鎖** | **整個送出內容**：system 指示 + 所有對話輪次 |
| **遮罩** | **只有最後一則 user 訊息** |

**後果**：如果一個詞出現在對話的更早幾輪、而你選的是「遮罩」，那個詞**在更早那一輪就已經送出去了**，不會被遮。

要絕對不外流，只能選 **封鎖**。

> 這個不對稱是刻意的：封鎖的威脅模型是「這個詞不能離開公司」，而離開公司的是整個 request body；只檢查最後一句，會讓封鎖在多輪對話下形同虛設（提一次代號、之後用「那個案子」指代，是正常用法而不是攻擊）。遮罩則沿用既有的 input-mutation 契約，該契約今天只能改寫最後一則訊息。

### 2.4 ⚠️ 抓得到什麼、抓不到什麼

**確定抓得到**（已由 repo 內可重跑的 probe 釘住）：

```
iPhone 18 Pro          大小寫
IPHONE 18 PRO          全大寫
ｉＰｈｏｎｅ　１８　Ｐｒｏ    全形（含全形空格）
iPhone １８ Pro         半形字母 + 全形數字
ip​hone 18 pro          夾零寬字元
iphone­ 18 pro          夾軟連字號
iP⁠hone 18 pro          夾 WORD JOINER / 雙向控制字元 / 變體選擇符 / TAG 字元
iphone  18\n pro       多重空白 / 換行
iphone-18-pro          連字號（_ . · / 、亦同）
iPhone–18–Pro          EN/EM dash 與任何其他 Unicode 標點（: + ~ | * ( 「 …）
STRASSE                完整 Unicode case folding（ß↔ss、ς↔σ）
iPhone18Pro            完全無分隔
我的iPhone18Pro壞了      無分隔 + 中英緊鄰
Ｉ​Ｐhone－１８_Ｐｒｏ      多種手法疊加
```

> **2026-08-13 更新**：字元類別從**手挑清單**改為**Unicode 屬性推導**（不可見字元＝`Default_Ignorable_Code_Point` 全 4174 碼位，原本只列 6 個；分隔符＝任何非字母非數字非組合符，原本只列 21 個），並補上 `casefold` 與無分隔拉丁詞。原因是手挑清單在結構上就輸——對手從十幾萬個碼位挑，我們從想得到的 27 個挑。

**確定抓不到**（同一支 probe 反向釘住；這是對外必須誠實講的邊界）：

| 手法 | 例子 | 為什麼不做 |
|---|---|---|
| 同形異字 | `iрhone`（西里爾 р 冒充 p） | 可做，但需 UTS #39 skeleton + mixed-script 閘門，且 skeleton 隨 Unicode 版本改變 ⇒ 偵測面變成版本綁定契約，需獨立 ADR |
| 錯字 | `iph0ne 18 pro` | **已量測不可分**：`iph0ne 18 pro` 與另一款真實產品 `iphone 17 pro` 的相似度同為 92.3，沒有門檻能同時收前者擋後者 |
| 改寫 | `蘋果十八代旗艦` | **架構上排除**（非暫未實作）：需把機密詞表餵給語意模型，與 §2.7 剛縮小的讀者範圍直接衝突 |
| **簡繁變體** | 詞 `獵鷹計畫`、正文 `猎鹰计划` | 只有一部分是字形問題：`獵`→`猎` 是字形，但 `計畫` vs `计划` 是**詞彙**差異（逐字元轉換得 `计画`，仍不匹配）⇒ 逐字元折疊在結構上修不掉，只有詞側變體展開可以，需獨立 ADR |
| 跨字組合的相容字元 | 半形片假名 `ｶ`＋`ﾞ` → `ガ` | 與「逐字元正規化以保 offset 精確」的契約衝突 |

**還有一項**：只處理 input。模型**自己吐出**那個詞不會被過濾（既有缺口 #1508）。

### 2.5 替換文字的四個坑

1. **不能撞到 PII 遮罩代號**：`NAME` / `EMAIL` / `PHONE` / `NATIONAL_ID` / `PASSPORT` / `ADDRESS` / `DATE` / `AGE` / `GENDER` / `CREDIT_CARD` / `MESSAGING_ID` / `TOKEN` 這 12 個保留字（含 `[PHONE]`、`[phone_2]` 等變形）一律拒絕。`CUSTOM` 是本 rail 自己的命名空間，可以用。
2. **不能是空字串**：那等於靜默刪除輸入，會留下不通順的句子。
3. **不能有換行或控制字元**：替換文字是**直接寫進送給模型的 prompt** 的；而且經繼承鏈之後，上層設的替換文字會對底下每個 application 的每個請求生效、下層拿不掉——這是注入通道。（刻意**不**做字元白名單：限成 `[A-Z_]` 會讓所有中文替換文字非法，整個功能的價值就沒了。）
4. **同一份 policy 內不能兩個詞共用同一替換文字**：模型會無法區分，比較題直接答錯。

第五個坑擋不掉、只能靠文案提醒：**替換文字本身可能就在洩密**。

```
iPhone 18 Pro → "Apple 尚未發布的 2026 年旗艦"   ← 你剛把要藏的事告訴模型商了
iPhone 18 Pro → "我們即將推出的旗艦手機"          ← 這才對
```

### 2.6 繼承（fold）行為

policy 可以綁在 tenant / group / application / deployment 四層，往下折疊時：

| 欄位 | 規則 |
|---|---|
| 詞的集合 | **union**（依正規化後的詞為鍵）——子層只能加，永遠不能移除上層的詞 |
| 同一詞的動作 | **封鎖勝過遮罩**（封鎖嚴格更嚴，可排序） |
| 同一詞的替換文字 | **祖先的勝**；**同一層**兩個 bundle item 給不同替換文字 → 直接拒絕（不讓順序偷偷決定） |

### 2.7 詞表機密性（重要限制，要對客戶明講）

- 詞表在**資料庫內是明文**。任何有權編輯這條 policy 的人都看得到。
- **但**：只是「被這條 policy 管到」的單位（例如被 tenant 強制綁上 policy 的某個 group）**看不到具體的詞**，只看得到數量與動作分佈。

第二點是這次特別補的。原本 PRD-263 的 binder read 會把整份 policy content 給被綁單位——那代表一個部門會讀到全公司的併購案代號清單，而它根本不是作者。

**這是「縮小讀者範圍」，不是加密。** 導入時要講清楚。

---

## 3. 怎麼運作（工程視角）

### 3.1 執行位置與順序

```
Client → Gateway
  ├─ [此處] guardrail input rails    ← routing / semantic cache / admission 之前
  │    engine 內固定順序：
  │      1. block 掃「整個送出內容」  → 任一命中 ⇒ 立即回 block，不做任何遮罩
  │      2. mask  掃「最後一則 user 訊息」→ 產 word-filter span（priority 高）
  │      3. PII 兩層偵測（同一段文字）  → 產 PII span（priority 低）
  │      4. merge_spans → mask_text（一次）
  ├─ semantic cache lookup
  ├─ routing → classifier rails（on_topic / content_filter）
  ├─ admission
  └─ Provider
```

**為什麼 block 必須先於 mask**：反過來的話，被遮掉的詞就找不到了，block 規則會變成死碼。

**為什麼是 span 合併而不是兩條 rail 順序執行**：順序執行的話，PII rail 之後會看到作者指定的替換文字，`陳大文 → 某高層主管` 有機會被 GLiNER 再抓成 person_name 遮成 `[NAME_1]`，作者的意圖被吃掉。span 合併 + priority 從結構上排除這個失效。

### 3.2 比對演算法

```
normalize(text, ignore_separators) -> (shadow, offset_map)
  層序：去 Default_Ignorable（4174 碼位）→ 逐字 NFKC（全半形折疊）
        → casefold（完整 Unicode，非 .lower()）→ 分隔符類別（非字母非數字非組合符）
        → 空白收斂
  保證：len(offset_map) == len(shadow)，每個 shadow 字元可歸因到恰一個原文字元
        ⇒ 反向映射精確（NFKC 與 casefold 的 1→N 展開都記同一個原文索引）
```

> 兩個字元類別都是**推導**而非列舉，見 §10.1。先丟 ignorable 是安全的：實測沒有任何字元的 NFKC 或 casefold 會產生 default-ignorable 字元。

三個關鍵設計：

**① 分隔符策略由詞的文字系統自動推導，不開放設定**

兩種文字的正確預設**剛好相反**：

| 詞 | 正文 | 保留分隔符 | 忽略分隔符 |
|---|---|---|---|
| `獵鷹計畫`（中文） | `獵鷹 計畫` | MISS ❌ | HIT ✅ |
| `iphone 18 pro`（拉丁） | `iphone 18 professional` | 正確不命中 ✅ | **誤遮** ❌（僅在**沒有** ② 詞界檢查時） |

中文詞內本來就沒有分隔符（正文出現的都是雜訊）；拉丁文的分隔符是詞結構的一部分。由詞自身推導後兩邊都對，而且客戶完全不需要知道這件事。

> **精確版（2026-08-13 修正）**：上表第二列的「誤遮」只在**關掉 ② 詞界檢查**時成立——實測在 ② 開啟下，`iphone 18 professional` 在兩種策略下都正確不命中。忽略分隔符真正的問題是**它把詞界資訊一起刪掉了**，於是 ② 反過來否決合法命中（`iPhone18Pro` 也 MISS）。所以拉丁詞現在跑**第二個 pass**：在刪掉分隔符的 shadow 上比對，但**詞界改對原文的鄰居求值**——這樣 `iPhone18Pro` 命中，而 `iphone18proxy` / `iphone18pros` / `iphone 18 professional` 仍正確不命中。兩個 pass 的 span 合併時丟棄重疊（長者勝），所以單一詞不會產生互相破壞的重疊 span。第二個 pass 重用中文詞已經在建的那份「刪分隔符」shadow，因此每請求的 shadow 數仍是 ≤2。

**② 詞界檢查是必要條件，不是可選最佳化**

沒有它，**預設層**就會產生使用者看得到的爛輸出：

```
「iphone 18 professional 版本？」→ 我們即將推出的旗艦手機fessional 版本？
```

規則是 script-aware：**只在拉丁詞的邊界碰到拉丁字元時拒絕**（中文沒有詞界概念，中英緊鄰本來就是合法邊界）。

**③ post-condition 驗證**

span 映回原文後，覆蓋的文字重新正規化必須等於正規化後的詞，否則丟棄——與 `extract.py::verify_offsets` 同一紀律（ADR-093 #3）。

**效能**：每個分隔符策略對整段文字建**一份** shadow，跨全部詞共用（最多兩份，拉丁詞的第二個 pass 重用其中一份）。實測 200 詞 × 19.6KB = **約 17ms**（加入第二個 pass 前是 9.7ms），所以 v1 明確**不採用** Aho-Corasick，那是過早最佳化。

**詞數上限**：`MAX_TERMS_PER_POLICY = 200` 只在**寫入時、每個 policy version** 檢查，而 fold 是**無上限的單調 union**（子層只能加）⇒ 四層折下來可達 800 詞而沒有任何地方重新檢查。2026-08-13 補上 `MAX_TERMS_AFTER_FOLD = 800`，在 resolver 的 post-fold 位置 **fail-closed**（超界不截斷——截斷等於靜默弱化作者以為在生效的控制）。實測（12.8K 字元正文）：200 詞 3.6ms、800 詞 7.2ms、2000 詞 14.5ms、10000 詞 62.3ms。

### 3.3 為什麼不進 semantic cache fingerprint

這條與 classifier rails 不同，值得記住：

- `mask`：遮罩**就地改寫** `request.messages`，而改完的文字才拿去算 cache key ⇒ 兩份只差詞表的 policy 對同一輸入產生不同文字 ⇒ 不同 key，隔離**自動成立**。
- `block`：在 cache lookup 之前就回 refusal 了 ⇒ 根本不查 cache。

這與 `pii` 不在 fingerprint 內是同一個理由。classifier rails 之所以必須進，是因為它們是 block-only 且**不改文字**。

⚠️ **這個結論依賴一個前提**：「這條 rail 跑在 cache lookup 之前且會改寫請求」。前提一旦被搬動就崩，而且失敗是靜默的。所以 `cache_handler.py` 的明列欄位處補了說明註解，並有 cache 隔離測試釘住。

### 3.4 稽核

可記：命中筆數、動作分佈（block/mask 各幾筆）、**詞在授權清單中的索引**、no-op 標記。
**絕不可記：原詞本身。** 記「命中 Project Falcon」等於把最敏感的東西寫進稽核庫——那比原本要防的洩漏更嚴重。

索引以逗號串成字串傳遞，因為 audit bridge 的 `_filter_extra` 只保留 primitive，list 會被靜默丟棄。

---

## 4. 涉及的檔案（完整清單）

### 4.1 設計文件（`xparse/docs/`）

| 路徑 | 內容 |
|---|---|
| `docs/prd/PRD-285-guardrail-word-filters-deterministic-custom-terms.md` | 需求：what/why、商業定位、§4 客戶端驗收條件、風險 |
| `docs/adr/ADR-389-guardrail-word-filters-deterministic-rail.md` | 架構：六個決策、七個替代方案、`INV-389-*` 不變量、檔案影響表 |
| `docs/specs/SPEC-224-guardrail-word-filters-contract.md` | 行為契約 `C-224-1` ~ `C-224-52`、驗證錨點、NFR |
| `docs/governance/console-i18n-zh-tw-glossary.md` | 新增 4 條譯名（自訂詞過濾／詞／替換文字／封鎖・遮罩） |
| `docs/adr/ADR_INDEX.md` | 自動產生的索引 |

### 4.2 Contract + Matcher（`xparse_guardrail/`）

| 路徑 | 新/改 | 內容 |
|---|---|---|
| `xparse_guardrail/word_filters/__init__.py` | **新** | 套件出口 |
| `xparse_guardrail/word_filters/matcher.py` | **新** | **唯一的正規化與比對實作**（純 stdlib）：`normalize` / `separator_policy` / `normalized_term` / `find_spans` / `verify_span` / `scan_terms` / `TermHit`。第二輪加 `_boundary_ok_in_text` / `_merge_passes` / `_find_spans_one_pass`（§10） |
| `xparse_guardrail/word_filters/unicode_classes.py` | **新（第二輪）** | **推導式字元類別**（純 stdlib）：`DEFAULT_IGNORABLE`（17 個 range 表 = 4174 碼位，以 bisect 做 `in`）+ `is_separator()`。取代原本手挑的 6 + 21 個字元 |
| `xparse_guardrail/contract/word_filters.py` | **新** | `WordFilterTerm` model、保留 token 集合（由 PII 分類法推導）、上限常數、**8 條寫入驗證規則**（IAM 與 runtime 共用）。第二輪加 `MAX_TERMS_AFTER_FOLD` |
| `xparse_guardrail/contract/profile.py` | 改 | `GuardrailProfile` 加 `word_filters_enabled` / `word_filter_terms` |
| `xparse_guardrail/contract/request.py` | 改 | `GuardrailRequest` 加 `scan_text` + `detection_text` property |
| `xparse_guardrail/contract/verdict.py` | 改 | 加 5 個 word-filter provenance 欄位 |
| `xparse_guardrail/contract/http.py` | 改 | `CheckResponse` 同上 |
| `xparse_guardrail/contract/__init__.py` | 改 | re-export |

### 4.3 Engine（`xparse_guardrail/engine/`）

| 路徑 | 新/改 | 內容 |
|---|---|---|
| `xparse_guardrail/engine/gliner_pii/spans.py` | 改 | `PiiSpan` 加 `replacement` / `token_type` / `priority` / `term_index`（預設值保持既有 PII 行為不變） |
| `xparse_guardrail/engine/gliner_pii/mask.py` | 改 | `merge_spans` 排序鍵加 `priority`；`mask_text` 支援字面 replacement |
| `xparse_guardrail/engine/gliner_pii/adapter.py` | 改 | **rail 組合**：block 掃描 → mask span → PII span → 合併 → 一次遮罩 |
| `xparse_guardrail/server/app.py` | 改 | `CheckResponse` 帶出 word-filter 欄位 |

### 4.4 Gateway（`bustream/`）

| 路徑 | 新/改 | 內容 |
|---|---|---|
| `bustream/gateway/request_text.py` | 改 | **新增** `extract_full_request_text()`（含 system，block 的偵測面）。刻意**不**改 `extract_conversation_transcript`（它為 C-223-41 排除 system） |
| `bustream/gateway/guardrail_enforcer.py` | 改 | **閘門修正**（原本只看 PII 欄位）、profile 帶詞表、送 `scan_text`、解析 provenance |
| `bustream/gateway/guardrail_handler.py` | 改 | 擷取 `scan_text` 並串到 enforce 與 shadow 兩條路徑；audit 欄位 helper |
| `bustream/gateway/guardrail_response.py` | 改 | rail 專屬 reason code `word_filter_match`、不洩漏內部 rail 名的訊息、**graceful 的確定性 refusal 內容** |
| `bustream/gateway/guardrail_policy_adapter.py` | 改 | snapshot → policy data 的 `word_filters` 對映 |
| `bustream/gateway/iam_http_client.py` | 改 | 加 `word_filters_enabled` / `word_filter_terms`；**刪除**死欄位 `redacted_keywords` / `redaction_token_prefix` |
| `bustream/gateway/cache_handler.py` | 改 | **僅加註解**說明為何刻意缺席 |
| `bustream/audit/schema.py` | 改 | 5 個 `word_filter_*` 欄位宣告 |
| `bustream/audit/xparse_bridge.py` | 改 | `PAYLOAD_ALLOWLIST` 加同 5 個（缺一即靜默丟棄） |

### 4.5 IAM（`xparse_iam/`）

| 路徑 | 新/改 | 內容 |
|---|---|---|
| `xparse_iam/xparse_iam/policies/schema.py` | 改 | `GuardrailWordFilterTermSpec` / `GuardrailWordFiltersSpec` + `GuardrailPolicySpecV2.word_filters` |
| `xparse_iam/xparse_iam/application/use_cases/policy/validate_policy_content.py` | 改 | 呼叫共用驗證，新錯誤碼 `INVALID_GUARDRAIL_WORD_FILTERS` |
| `xparse_iam/xparse_iam/authorization/guardrail_policy_merge.py` | 改 | `_merge_word_filters`（三種運算子）+ identity element + v1 downgrade 保護 |
| `xparse_iam/xparse_iam/authorization/guardrail_resolver.py` | 改 | 同層 replacement 衝突 fail-closed。第二輪加 **`_assert_word_filter_term_budget()`**，接在兩處既有 `_assert_capability()` 之後 |
| `xparse_iam/xparse_iam/api/ninja_api/_versioned_policies.py` | 改 | **`redact_word_filter_terms()`** + binder read / effective-policy 套用 + `word-filters:N` 摘要標籤 |
| `xparse_iam/xparse_iam/api/audit_catalog.py` | 改 | 欄位 kind 與三個 guardrail 事件的參數清單 |
| `xparse_iam/xparse_iam/policies/word_filter_normalization_shift.py` | **新（第二輪）** | 正規化位移的唯讀分析（純函式 + 一支 ORM 取列）。`normalized_term()` 是 fold union 鍵，動它會改變**已儲存**詞的身分，所以需要在部署前量 |
| `xparse_iam/xparse_iam/policies/_word_filter_legacy_normalization.py` | **新（第二輪，有壽命）** | ADR-389 當時正規化的凍結副本，唯一用途是當上面那支的比較基準。**切換完成後整檔刪除** |
| `xparse_iam/xparse_iam/management/commands/check_word_filter_normalization_shift.py` | **新（第二輪）** | 唯讀就緒命令，照既有 `check_*_cutover_readiness` 慣例。findings 只帶 `(version, term_index)`，永不帶原詞（C-224-42） |

### 4.6 Console（`frontend/console-app-refactor/`）

| 路徑 | 新/改 | 內容 |
|---|---|---|
| `src/app/(main)/(ai-gateway)/policies/_components/policy/policy-content-form.tsx` | 改 | 表單狀態、`buildWordFilterTerms()`（client 端鏡像驗證）、v1/v2 判定、parse（含 redacted 拒絕）、UI 區塊、列操作 handlers |
| `src/app/(main)/(ai-gateway)/policies/_components/policy/policy-version-describe.ts` | 改 | 唯讀檢視兩列 + **consumed-keys 陣列加 `word_filters`**（沒加就會以 raw JSON 露出整份詞表） |
| `src/types/iam.ts` | 改 | `VersionedGuardrailWordFilterTerm` / `VersionedGuardrailWordFiltersSpec`（含 `terms_redacted`） |
| `src/i18n/messages/en.json` · `zh-TW.json` | 改 | `policies.contentForm.wordFilters*` 31 鍵 + `policies.describe.wordFilter*` 2 鍵 |

### 4.7 測試與 probe

| 路徑 | 新/改 | 覆蓋 |
|---|---|---|
| `scripts/probe_word_filters.py` | **新** | 10 項檢查：正規化涵蓋 / 詞界 / 中文 / offset / **偵測面對比** / **誠實邊界反向釘住** / 效能 / **真 encoder**，第二輪加 **(i) 新涵蓋類正向釘住** / **(j) 無分隔 pass 不得誤遮**。第二輪起**import 真 matcher**（原本自帶一份副本，見 §10.4） |
| `xparse_guardrail/tests/word_filters/test_matcher.py` | **新** | 28（原 22 + 第二輪 6）— matcher 全行為 |
| `xparse_guardrail/tests/contract/test_word_filters_validation.py` | **新** | 41 — 8 條寫入規則 |
| `xparse_guardrail/tests/engine/test_word_filters_rail.py` | **新** | 17 — rail 順序、span 優先權、replacement、no-op、PII 連續性 |
| `xparse_guardrail/tests/engine/conftest.py` | 改 | **收窄 NeMo skip**（原本整包跳過，讓 36 個測試從未執行） |
| `tests/unit/test_spec224_word_filters_gateway.py` | **新** | 20 — adapter、偵測面、**enforcer 閘門**、block presentation |
| `tests/unit/test_word_filter_audit_fields_survive_bridge.py` | **新** | 12 — audit 欄位存活 + 原詞不可達 |
| `tests/integration/test_word_filters_end_to_end.py` | **新** | 9 — **真 IAM 驗證 → 真 fold → 真 adapter → 真 engine** |
| `xparse_iam/tests/unit/test_word_filters_fold_and_validation.py` | **新** | 41（原 36 + 第二輪 5）— fold 三運算子、寫入邊界、**遮蔽投影**、**fold 詞數界**（含「四層各自合法卻折爆」的可達性測試） |
| `xparse_iam/tests/unit/test_word_filter_normalization_shift.py` | **新（第二輪）** | 18 — 凍結基準的已知行為、碰撞偵測真的觸發、既有重複詞不被誤歸因、findings 不帶原詞、薄資料集的誠實警告 |
| `frontend/.../policy-word-filters.test.ts` | **新** | 22 — build/parse round-trip、拒絕規則、redacted 拒絕 |
| `frontend/.../policy-content-form.test.ts` | 改 | 收窄一個過寬的 selector |
| `tests/unit/test_spec303_output_coverage.py` | 改 | 移除已刪欄位的引用 |

---

## 5. 實作過程中發現的三個既有缺陷

這三個都是「用真元件跑」才會現形的，值得記住：

### 5.1 enforcer 的閘門只看 PII 欄位

`_call_pii_engine`（現已改名 `_call_guardrail_engine`）原本在 `pii_redaction_enabled` 為假或 `pii_entities` 為空時**直接回 pass、不做任何網路呼叫**。

代表**只設 word filters、沒設 PII 的 policy 會完全不呼叫 engine**——授權了、Console 顯示了、實際上什麼都沒做。而所有既有測試（都帶 PII）會全綠。

### 5.2 graceful block 回 `content: null`

`run_input_guardrail` 從來沒傳過 `refusal_message`——因為 PII rail 永遠不 block，沒有 caller 需要過。

結果：狀態碼 200 對、`finish_reason: content_filter` 對，但客戶端收到一個**空的 assistant 訊息**，對 chat client 而言與「provider 壞掉」無法區分。

這是實作前用 probe 打真的 `guardrail_response` 模組量到的，不是猜的。

### 5.3 `tests/engine/` 整包被靜默跳過

該目錄的 conftest 寫著「這些測試需要 nemoguardrails」——那是 ADR-309 移除 NeMo adapter **之前**寫的。之後只有一個檔案真的需要 NeMo，但整包 `test_*.py` 仍被忽略。

代表釘住 `merge_spans` 排序的 36 個測試（**正是這次改動碰的碼**）在任何沒裝 nemoguardrails 的環境從來沒跑過。已收窄到那一個檔案。

---

## 6. 驗證現況

| 項目 | 結果 |
|---|---|
| `scripts/probe_word_filters.py` | **8/8 asserted**（2026-08-13 起 **import 真 matcher**，不再自帶副本）：拉丁 17/17、中文 7/7、誤遮修復 2/2、零 offset 漂移、誠實邊界 5/5 仍抓不到、**新涵蓋類 13/13**、**無分隔 pass 誤遮防線 3/3**、200 詞×20KB ≈17ms、真 encoder 5 confirmed / 0 pending。dogfood：植入回歸（從 `INVISIBLE` 移除 ZWSP）→ 2 項變紅、exit code 1；還原後 exit 0 |
| `xparse_guardrail` | **328 passed**（322 基準 + 6 個新涵蓋類測試；含 36 個原本靜默跳過的） |
| IAM word-filter 相關 | **59 passed**（fold 36 + fold budget 5 + 正規化位移 gate 18） |
| IAM unit 全套（容器） | **2017 passed / 18 failed**；那 18 個在 `origin/main` baseline worktree 上**逐項相同** ⇒ 零新增失敗 |
| gateway 相關 | **216 passed** |
| IAM unit（容器） | **1986 passed**；失敗集合與 `origin/main` 的 27 個既有**逐項相同**（baseline worktree 實測，零新增） |
| Console | typecheck 乾淨、eslint 乾淨、4 個 i18n gate 乾淨、**635 tests passed** |
| **端到端** | **9/9**：真 IAM 驗證 → 真 fold → 真 gateway adapter → 真 engine |

---

## 7. 未來要做／要修的事

### 7.1 治理債（#3449 已 merged，但這三項仍未做）

| # | 項目 | 狀態 |
|---|---|---|
| R1 | ADR-389 狀態仍是 `Proposed`；依 repo 規則 acceptance 需要 peer review | **未做** |
| R2 | Core 整合層回寫（§17.4）：更新 `Core-ADR-02` / `Core-PRD-02` / `Core-ADR-01` / `Core-ADR-04` / `Core-PRD-05`，加編號 + 一行說明 + 調整計數 | **未做**（第二輪的 ADR/SPEC 修訂也要一起） |
| R3 | wiki 同步（§17.2 #3） | **未做** |

### 7.2 上線前必須補的驗證（SPEC-224 §7.1 明列）

| # | 項目 | 狀態 | 為什麼重要 |
|---|---|---|---|
| V1 | **enforcer ↔ sidecar 的真 HTTP hop** | 未做 | 兩端各自有測試，但從未在這條 rail 上跨 socket 接起來 |
| V2 | **真 gateway 的客戶端可觀察行為**（PRD-285 A1–A14） | 未做 | 特別是 graceful 200 的 body 實際長什麼樣 |
| V3 | **Console UI 用瀏覽器實看**（U1–U8） | 未做 | U2（兩種動作涵蓋範圍不同）與 U3（抓不到什麼）是 release gate——它們正是誠實性的那一半。**第二輪改了 U3 的文案，這條的必要性更高** |
| V4 | **binder read 遮蔽用真 `group_admin` key 驗**（U7） | 未做 | 投影 helper 有單元測試，但它背後的授權路徑沒有端到端跑過 |
| V5 | **shadow 期量測** | 未做 | 遮罩誤判率（precision，與 PII 的 recall 問題方向相反）＋ **多模態 fail-closed 觸發率** |
| **V6** | **對 prod 資料跑 `check_word_filter_normalization_shift`** | **未做——第二輪部署的硬前提** | 第二輪動了 `normalize()`，而 `normalized_term()` 是 fold union 鍵 ⇒ 已儲存詞的**身分**會變（見 §10.3）。dev 上回報 NO SHIFT，但只掃到 4 個詞，命令自己會印「這不可外推」 |

### 7.3 上線順序（**強制，不是建議**）

```
Phase 1  runtime first  — gateway 與 IAM resolver 先會解析／折疊／傳遞，IAM 寫入邊界仍拒絕
Phase 2  authoring flip — 開放寫入邊界 + Console 授權介面
Phase 3  enforce gate   — 一律 shadow 先行，per-tenant flip 走 ADR-318 §7.3 覆核
```

反過來做，未升級的 gateway 會**靜默忽略**詞表——「以為有擋、其實沒擋」是這個功能最壞的失效模式。

### 7.4 已知會變差的地方（要盯著）

| # | 項目 | 說明 |
|---|---|---|
| K1 | **多模態 fail-closed 觸發率會明顯上升** | 遮罩無法套用到多模態陣列時會擋下整個請求（既有契約）。今天只有「PII 命中且多模態」才會撞到（罕見）；詞表是**必然命中**的東西，之後不會罕見 |
| K2 | `PiiSpan` 這個名字之後承載非 PII 的 span | 命名債，刻意接受 |
| K3 | engine 類別名與 `engine_id` 字串不一致 | `engine_id` 維持 `gliner_pii` 以保 policy content 連續性 |
| K4 | 詞表**明文落盤且不可回溯保護** | 事後改加密無法保護已寫入的資料，導入時要明講 |
| K5 | `guardrail_policy_merge.py` 更長了 | 手寫非表格驅動；若再加第五條 rail，應把 rail 組合抽成獨立 composition 層而不是繼續往 engine 裡疊 |

### 7.5 明確不做（另案）

> 第二輪（2026-08-13）對其中三項做了量測，結論分成**已證明不可做**與**可做但需 ADR**兩類——差別很重要，別把後者當前者引用。完整證據見 [RESEARCH-word-filter-recognition-third-party-landscape-2026-08-13](../xparse/docs/research/RESEARCH-word-filter-recognition-third-party-landscape-2026-08-13.md)、裁定寫在 ADR-389 §4.1。

**已證明不可做／架構上排除**

- **fuzzy / 編輯距離比對**——**已量測**：`rapidfuzz` 下真錯字 `iph0ne 18 pro` = **92.3**，另一款真實產品 `iphone 17 pro` **也是 92.3**。沒有門檻能同時收前者擋後者。從「誤遮率不可接受」升級為「已證明不可分」
- **改寫（paraphrase）偵測**——**架構上排除，不是暫未實作**：需把機密詞表餵給語意模型，與 §2.7 剛縮小的讀者範圍直接衝突。不留為 roadmap 債
- **把自訂類別餵給 GLiNER 做 zero-shot**——四個結構性理由（單一全域 threshold 不可能同時適合內建 12 類與自訂類、label→entity 是全域 static map、label 吃掉 transformer 序列預算、且該模型是在 PII 資料上 fine-tune 的，泛化**無法先驗保證**⇒ 沒辦法在銷售時承諾效果）
- **詞表加密儲存**——會破壞 `content_hash` 可比較性、GitOps 匯出入、以及 fold 的 set-union

**可做，但需獨立 ADR（原否決理由已不成立或不完整）**

- **同形異字（homoglyph）防護**——原理由「會誤折正常俄文／希臘文內容」**已被實測推翻**：UTS #39 的 mixed-script 偵測正好分離攻擊與正常內容（`is_mixed_script('привет')`=False、`('iрhone')`=**True**），只對 mixed-script run 套用即零影響。實作陷阱：貪婪「往拉丁折」會把 `18` 折成 `lȣ`（數字也在 confusables 表內），正解是 `skeleton()` 對詞與正文**對稱**套用。真正需要 ADR 的是：skeleton **「not stable across versions of Unicode」**（規範原文）⇒ 偵測面變成 Unicode 版本綁定契約
- **簡繁折疊**——**只能在詞側做**。逐字元 OpenCC 得 `計畫`→`计画`，與 `计划` 不匹配，因為那是**詞彙**差異不是字形差異 ⇒ 文字側加 shadow 在結構上修不掉（且實測貴 6.4×）。可行解是 authoring 時對**詞**整串轉換展開變體（實測 +100 變體僅 +0.7ms／每詞 0.016ms，且變體可顯示給作者確認），但那會改變 `normalized_term` 這個 fold 鍵的產生方式
- **自訂 regex / 自訂格式類別**（`EMP-\d{6}`）——需 ReDoS 防護與另一套授權形狀

**仍未動**

- **output（回應端）過濾**——既有缺口 [#1508](https://github.com/futurenestit/xparse/issues/1508)
- **可逆遮罩（unmask 還原）**——沿用 PRD-241 NG4
- **`mask` 涵蓋全部輪次**——目前 `mask` 只改最後一則 user 訊息（§2.3）。改它等於重寫 ADR-296 的 input-mutation 契約並擴大多模態 fail-closed 面 ⇒ 需獨立 ADR
- **authoring 時的影響預覽**——作者打下一個詞時，沒有任何東西告訴他這個詞在正常流量裡會命中幾次；下限只有「至少 2 字元」。shadow 期資料本來就在，這是把盲配置變成可量測配置的一步，且五家廠商都沒做

---

## 8. 對外溝通的兩條紅線

### 8.1 這是 commodity，不是差異化

AWS Bedrock（Word filters）、Google DLP（custom dictionary）、Azure（blocklists）、Presidio（`deny_list`）、LiteLLM（custom blocked keywords）**五家全部**都有，而且全都把它做成與自動 PII 分開的獨立功能。

五家獨立收斂到同一架構，證明的是**需求真實**，同時證明**我們在「有這個功能」這一項上沒有差異空間**。

> **第二輪修正（2026-08-13）**：原句「我們在這一項上沒有差異空間」對「**功能存在**」是對的，對「**偵測強度**」是**錯的**。實測（同一組規避語料）：
>
> | | 結果 |
> |---|---|
> | Presidio `deny_list` | **4/10**，且因 Python `\w` 含漢字，對「中文詞出現在中文正文中」是**結構性零命中**（實測後鄰 `已`/`a`/`1` 皆 MISS） |
> | Xparse matcher | **10/10** |
> | AWS Bedrock · Azure Content Safety | **完全不公布匹配語意**（Azure 的 how-to 全文 5687 字沒有定義大小寫／正規化／regex 行為） |
> | Google DLP | 唯一公布規則的廠商，水準相當，但無簡繁與同形異字 |
>
> **可宣稱**（有實測支撐）：Xparse 是唯一**公布並用可重跑 probe 雙向釘住**偵測邊界的實作。
> **不可宣稱**：「更準」——除非把第三方元件也接上（§7.5 那兩項需 ADR 的）。現在的正確說法是「**同級功能 + 可稽核的邊界宣告**」。
> **絕不可宣稱**：能防刻意繞過（§8.2 不變，而且第二輪讓「抓不到」清單多了簡繁，是更長不是更短）。

可以宣稱的是**組合**：自訂詞與自動 PII 在同一份 policy、同一條繼承鏈、同一個稽核面，且判斷全在客戶部署範圍內完成。

英文名維持 `Word filters` 對位 AWS Bedrock 的同名元件，是為了標案功能表比對——那是文件層的考量，不改 Console 的中文標籤。

### 8.2 不得宣稱能防止刻意繞過

§2.4 的抓不到清單必須主動講。否則 shadow 期一定被客戶用「我打成 project falcon 就漏了」打臉，而且會連帶折損整套 guardrail 的可信度。

> **第二輪的教訓比原則本身更值得記**：初版公布的清單**漏了四類**（簡繁、Unicode dash 全族、`casefold`、不可見字元全族），而客戶是按那份清單做風險評估的。漏項比功能弱更傷——功能弱是已知限制，漏項是誤導。現在兩份清單（抓得到／抓不到）**都**由 probe 雙向釘住：關掉任一限制會讓 build 變紅，直到公布的文案被同步修正。

定調是「**補**」自動 PII，不是取代：Word filters 管「已知字面詞」，PII rail 管「未知但有格式／語意特徵的值」。

---

## 9. 附註：文件編號的坑

這個 PR 原本開成 ADR-387。`scripts/sync_adr_index.py --next` 讀的是**本地工作樹**的檔案，而這條分支的 base 落後 `origin/main` 11 個 commit——上游那 11 個 commit 裡已經有 ADR-387（budget enforcement）落地。

依 repo 的撞號慣例（先 merge 者保留編號，見 PRD-263 header），改為 **ADR-389**。PRD-285 與 SPEC-224 未受影響。

**教訓**：配號前要對 `origin/main` 撈，不是對本地樹。`git fetch` 不夠——那支腳本不看 remote。

---

## 10. 第二輪：偵測強度還債（2026-08-13）

起點是一個問題：「§2.4 那五項是**自建的極限**，還是**這件事的極限**？外面有沒有現成的 recognition 層接上去就比自己做的強？」

答案：**沒有引擎可買，只有元件可買**。詳見 [RESEARCH-word-filter-recognition-third-party-landscape-2026-08-13](../xparse/docs/research/RESEARCH-word-filter-recognition-third-party-landscape-2026-08-13.md)。這一輪做的是**還債**，不是加功能——弱點不在演算法，在三件性質不同的事。

### 10.1 債一：字元覆蓋是「列舉」而不是「推導」

`INVISIBLE` 手挑 6 個字元、`SEPARATORS` 手挑 21 個、用 `.lower()` 而非 `.casefold()`。這不是四個 bug，是**一個設計氣味的四個症狀**：

> 對手從 Unicode 的十幾萬個碼位裡挑，我們從想得到的 27 個裡挑。**列舉在結構上就輸。**

實測漏掉的：`U+2060` WORD JOINER、`U+200E`/`U+200F` 雙向標記、`U+FE00`–`FE0F` 變體選擇符、**`U+E0020`–`E007F` TAG 字元**（隱形指令注入的載體）、EN/EM dash（BMP 有 25 個 `Pd`，只涵蓋 3 個）、`:` `+` `~` `|` `*` `(` `「`、以及 `ß`/`ς`。

改成規則：

| 類別 | 規則 | 依據 |
|---|---|---|
| 不可見字元 | Unicode `Default_Ignorable_Code_Point`（**4174** 碼位，17 個 range） | UTS #39 `skeleton()` 剝除的同一個屬性——跟著標準走，不自創集合 |
| 分隔符 | 任何**非字母、非數字、非組合符**的字元 | Google Cloud DLP 對 custom dictionary 公布的規則；五家廠商中唯一寫得夠精確可被檢查的 |

三個實作細節：組合符（`U+0301` 等）明確算**內容**不算分隔符，否則會把每個分解式重音、天城文母音符號、阿拉伯短母音都切成詞界。`casefold` 會 1→N（`ß`→`ss`），既有的逐字元迴圈本來就吸收得了（跟 NFKC 展開同形狀）。先丟不可見字元是**安全的**而非只是方便——實測沒有任何字元的 NFKC 展開或 casefold 會**產生** default-ignorable 字元。

代價要誠實講：分隔符規則變寬後，句末標點也是分隔符 ⇒ 一個詞可以跨句子邊界命中。但這個代價**原本就在**（`.` 和 `,` 本來就在手挑清單裡），而且與 DLP 公布的行為一致。它用精度換規避抵抗力——精度是作者可以自己救的（改詞），規避抵抗力不是。

### 10.2 債二：`iPhone18Pro` 不是「做不到」，是論證寫錯了

初版 §3.2① 說拉丁詞若「忽略分隔符」會誤遮 `iphone 18 professional`。**實測兩種策略下都是 MISS**——因為 ② 詞界檢查已經擋掉了。真正的阻礙是：**忽略分隔符會把詞界資訊一起刪掉**，於是 ② 反過來否決合法命中。

解法是給拉丁詞跑**第二個 pass**：在刪掉分隔符的 shadow 上比對，但**詞界改對原文的鄰居求值**。實測 7/7 正確：

```
iPhone18Pro leak          → HIT  'iPhone18Pro'
我的iPhone18Pro壞了         → HIT  'iPhone18Pro'
ip​hone18pro（夾零寬）       → HIT
iphone 18 professional    → MISS ✓
iphone18proxy service     → MISS ✓
my iphone18pros here      → MISS ✓
```

兩個 pass 的 span 合併時丟棄重疊（長者勝），所以單一詞不會產生互相破壞的重疊 span。第二個 pass **重用中文詞已經在建的那份「刪分隔符」shadow**，所以每請求的 shadow 數仍是 **≤2**（原本計畫寫要改成 ≤3，實測後改回來：`ignore` 與 `strip` 在 `normalize()` 裡是同一個操作，差別只在詞界對誰求值）。延遲 9.7 → **16.8ms**（200 詞 × 19.6KB），預算 250ms。

### 10.3 債三：「我們的上限是 200」在 runtime 是假的

`MAX_TERMS_PER_POLICY = 200` 只在**寫入時、每個 policy version** 檢查。而 `_merge_word_filters` 是**無上限的單調 union**，方向是「子層只能加」⇒ 四層折下來必然只增不減，**沒有任何地方重新驗證**請求實際掃的數量。

補上 `MAX_TERMS_AFTER_FOLD = 800`（四層 × 各自上限），在 resolver 的 post-fold 位置緊接既有 `_assert_capability()` 之後 **fail-closed**。

超界不截斷：截斷等於靜默弱化作者以為在生效的控制。錯誤訊息給「折疊後總數 / 上限 / 貢獻 scope」，**不給原詞**（C-224-42）。

這是**宣告的界**不是效能懸崖——實測（12.8K 字元正文）：200 詞 3.6ms、800 詞 7.2ms、2000 詞 14.5ms、10000 詞 62.3ms。

> **同一形狀值得在別處找**：任何「寫入時 per-scope 檢查 + fold 是 union」的組合都有這個洞。

### 10.4 順手修掉的一個錨點問題

`scripts/probe_word_filters.py` **自帶一份 matcher 副本**（156 行），而 SPEC-224 §7 把它列為 C-224-26..31 的**驗證錨點**。移除時跑了 44 組差分測試，兩份**行為剛好等價**（0 差異）——所以它沒有掩蓋任何東西，但**那是運氣不是保證**：真模組漂移時，這個錨點會繼續全綠。

已改為 import 真模組。並且驗證了「它現在真的看得到改動」：植入回歸（從 `INVISIBLE` 移除 ZWSP）→ 2 項變紅、**exit code 1**；還原 → exit 0。

> 教訓：**任何被文件指名為錨點的 probe，必須 import 而非重寫。** 改 matcher 前先確認錨點看得到你的改動。

### 10.5 部署前的硬前提（V6）

`normalized_term()` 不只是比對用的 needle，它同時是：**fold union 鍵**（C-224-17）、**寫入去重鍵**（C-224-3）、**`MIN_TERM_LENGTH` 的判準對象**。

所以放寬正規化會**改變已儲存詞的身分**，而已儲存內容永不重新驗證（active version content immutable，INV-259-1）。兩個後果都不會自己出聲：

1. **靜默合併**——兩個原本相異的詞塌成同一鍵，fold 只留一個（action 取 max、replacement ancestor-pin），另一位作者的意圖被丟掉且不報錯。
2. **新的 fail-closed**——同一 scope 兩個 bundle item 各自 pin 了不同 replacement，原本因鍵不同而相安無事；改後同鍵 ⇒ 觸發 resolver 的同層歧義檢查 ⇒ **昨天能解析的 policy 今天整條失效**。

因此新增唯讀命令 `check_word_filter_normalization_shift`（照既有 `check_*_cutover_readiness` 慣例），對每個已儲存詞用**凍結的舊規則**與**當前 matcher** 各算一次鍵，報告三類：版本內新碰撞、跨 scope 合併候選、新落到 `MIN_TERM_LENGTH` 以下。

dogfood 過（用真的新舊 normalization）：`iPhone–18–Pro` 從 `iphone–18–pro` 位移到 `iphone 18 pro`，與 `iPhone 18 Pro` 同鍵 → 正確報出碰撞、2 個不同 replacement、`ready=False`、findings 不含原詞。

**dev 上回報 NO SHIFT，但只掃到 4 個詞**，所以命令自己會印警告說這不可外推。**上 prod 前必須對 prod 資料重跑**——這正是它存在的理由。凍結副本放在獨立檔案 `_word_filter_legacy_normalization.py`，切換完成後刪整檔即可。

### 10.6 這一輪的驗證

| 項目 | 結果 |
|---|---|
| `scripts/probe_word_filters.py` | **8/8 asserted**（新增 (i) 新涵蓋類 13/13、(j) 無分隔 pass 誤遮防線 3/3）；dogfood：植入回歸 exit 1、還原 exit 0 |
| `xparse_guardrail` | **328 passed**（322 基準 + 6 新） |
| gateway 側 guardrail | **122 passed** |
| IAM word-filter 相關 | **59 passed**（fold 41 含 5 個 budget + 位移 gate 18） |
| IAM unit 全套（容器） | **2017 passed / 18 failed**；那 18 個在 `origin/main` baseline worktree 上**逐項相同** ⇒ 零新增失敗 |
| Console i18n 四道 gate | 全綠（0 glossary violation、100% translated） |
| radon（§2.3 品質閘） | MI 53.10 / 63.51 / 53.84 / 76.68（需 >50）· CC 全部 <15 |

### 10.7 這一輪順手發現的既有問題（未修）

`tests/unit/test_guardrail_wave1_write_gate.py` 的 9 個測試 import `_validate_wave1_guardrail_mode`，該函式在 `origin/main` 也**不存在**（早被移除、測試沒跟上）。它一直是紅的，屬 repo 既有紅底，與這一輪無關。要不要修是另一件事。
