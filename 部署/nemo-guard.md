# NemoGuard 自架判定源 — 現況、缺口、與 endpoint 部署

> **文件定位**：部署與現況盤點。設計權威在 `docs/prd/PRD-279`（what & why）與 `docs/adr/ADR-375`（how），契約在 `docs/specs/SPEC-223`。本文衝突時以那三份為準。
>
> **最後更新**：2026-09-03 · 對應實作：WP1–WP6 已落 main（PR #3302–#3306、#3308）

---

## 0. 先消歧：repo 裡有兩個「Nemo」

| | 是什麼 | 現況 |
|---|---|---|
| **NeMo Guardrails**（框架） | NVIDIA 的對話 rail 框架（Colang、jailbreak 偵測、RAG grounding），跑在 `xparse-guardrails` sidecar | **已退役**。ADR-139 → ADR-202 → **ADR-309 PR-7 刪除**。`xparse_guardrail/engine/nemo/` 現在是空目錄，`registry.py` 只註冊 `gliner_pii` |
| **NemoGuard**（兩顆模型） | NVIDIA 訓練的兩顆 LoRA 分類器，掛 OpenAI 相容端點 | **這份文件講的東西**。ADR-375，只拿權重不拿框架 |

這個區分很重要，因為**部署腳本與安裝指南目前還是寫給退役的 sidecar 路徑的**（見 §5 陷阱）。

---

## 1. 一句話

把 NVIDIA 兩顆專用分類器裝在**客戶自己的 GPU 機房**，讓 guardrail 的判定過程**不離開客戶信任邊界** —— 客戶提供機器與 endpoint，模型與 prompt/parser 由我方釘死。

---

## 2. 現在有什麼功能

### 2.1 覆蓋哪些 rail — 只有兩條

| Rail | 可選判定源（`policies/schema.py`） | NemoGuard |
|---|---|---|
| `content_filter` | `llm_classifier` · `openai_moderation` · **`nemoguard_content_safety`** | ✅ |
| `on_topic` | `llm_classifier` · **`nemoguard_topic_control`** | ✅ |
| `pii` | `gliner_pii` | ❌ **明確 non-goal** |
| `word_filters` | 無 engine 軸（ADR-389 確定性規則） | ❌ 不適用 |

**PII 為什麼不做**：遮罩必須本地執行且必須能 MODIFY，NemoGuard 是分類器**不會遮罩**。PRD-241 的 `pii` 區塊任何欄位語意完全不動。

**word filter 為什麼不適用**：ADR-389 是自訂詞確定性比對（只有 `block` / `mask` 動作），根本不經模型。

### 2.2 兩顆模型的契約 —— 不同構，別假設對稱

| | content-safety | topic-control |
|---|---|---|
| HF repo | `nvidia/llama-3.1-nemoguard-8b-content-safety` | `nvidia/llama-3.1-nemoguard-8b-topic-control` |
| 現名 | Llama Nemotron Safety Guard **V2** | Llama Nemotron Topic Guard **V1** |
| LoRA rank | **16**，`target_modules` **含 `lm_head`** | **8**，無 `lm_head` |
| 輸入 | 一份渲染好的 prompt，內嵌**完整** Aegis S1–S23 分類法 | 原生 OpenAI messages array，約束寫在 system message |
| 輸出 | JSON：`User Safety` / `Response Safety` / `Safety Categories` | 二元字串：`on-topic` / `off-topic` |
| parser | JSON 解析 | 字串比對 |
| 判定範圍 | 對話內容 | **最後一個 user turn** |
| served model name | `content_safety` | `topic_control` |

兩套 parser 在 `xparse_guardrail/contract/nemoguard/`（629 行：`mapping.py` / `parser.py` / `prompts.py`），gateway in-process 執行，**sidecar 永遠看不到、也永不持有判定憑證**（INV-318-2）。

> `topic_control` 的 system message 帶的是 **policy 的 topic 約束**，**絕不轉發 app 自己的 system prompt**（注入風險）。且 system prompt 必須以廠商規定的固定句收尾。

### 2.3 授權與 fold 語意（已實作）

- **`content_filter.engines`**：set-union fold、OR-block fan-in、`unavailable` 永不 coerce 成 pass
- **`on_topic` 新增 evaluator 軸**：與 `template` 正交的獨立欄位，fold 方向也是 **set-union**（`template` 是 ancestor-pin，**方向相反**）
- **子層只能加防線，永遠無法移除祖先的**（INV-279-1，繼承 INV-250-1）
- **類別分類法改 per-engine 命名空間**；Aegis 21 個 harm 類與我方 5 類的對映表在 `mapping.py`，**無對應者不得靜默併類**（`UNCOVERED_AEGIS_CODES`）
- **`honors_content_threshold = False`**：模型只回二元，寬鬆/中等/嚴格在此源不生效，UI 灰掉 + audit 標明

> ⚠️ **反直覺但必守**：Console 的 "Engine" 單選同時寫兩條 rail，但那**只是 authoring 簡化**。折疊多個 binding 後「主題來源來自祖先、內容來源來自子層」是合法組合，**讀取端不得假設兩條 rail 耦合**（C-223-39 / INV-279-10）。

### 2.4 憑證與授權邊（已實作）

- `ProviderCredential` 新增 endpoint 欄位；IAM seed 了 `provider_code="nemoguard"` 的 ProviderDefinition（**migration 0243**）
- policy 只**指名憑證**（`classifier.judgement_credential_ref`，掛在 classifier envelope 上因為**一把憑證服務兩條 rail**）
- IAM 依既有授權邊（ADR-310 `access_scope` / `GroupCredentialGrant`）驗證後**投影恰好一把**，URL 由 provider definition 的 `url_pattern` 在 validate-time 組成
- 五態回覆：`resolved` / `not_named` / `not_found` / `not_entitled` / **`no_endpoint`**（憑證存在且有權但沒掛 endpoint —— 必須與 not_found 可區分，作者才知道要去補什麼）
- **gateway 對每個非 `resolved` 狀態 fail closed，永不在候選間挑選、永不投影憑證目錄**
- **授權時可打真 probe**：`POST /iam/provider-credentials/{uuid}/test-judgement` —— 用固定 benign 字串探**兩顆** adapter，每顆的成功條件是 **2xx 且 verdict 可依契約解析**（單純連得上不算成功）。**`success` 只看 content-safety 那顆**（C-223-48 **Rev.2**，2026-09-18）：topic-control 缺席會在 `topic_control_ok` 與 `provider_info` 中曝出，但**不否決**整體判定——因為兩條 rail 的 evaluator 是獨立契約欄位（C-223-43a），只 author `content_filter` 的政策用單顆部署是完全可用的

---

## 3. 缺什麼

### 3.1 交付缺口（最重要）

| 缺口 | 影響 | 現況 |
|---|---|---|
| **§8.1 真元件 probe（P1–P5）未執行** | PRD §4 驗收與 Phase 3 enforce **都被 gate 住**。依 §8.1，probe 前不得宣稱 verified | 部分鬆動：2026-08-28 在 air520（2× RTX 4000 Ada）做過 fp8 vs lora 等價性測試，10 case verdict 與類別清單 **byte-identical 10/10**。但那是**變體等價性**，不是完整 P1–P5 |
| **停在 Phase 2** | authoring 開放、**預設 shadow**；enforce 尚未開放 | Phase 3 需 per-tenant would-block 覆核（ADR-318 §7.3） |
| **繁中誤判率未量測** | 這是 enforce 的**本 PRD 特有前置條件**（§8 R1） | 無資料 |

> 兩條 rail 的 enforce 節奏**可以不同步** —— 主題判定可先 enforce 而內容判定維持 shadow。

### 3.2 證據缺口（未定案的模型行為）

| 未知 | 為什麼要緊 |
|---|---|
| **限縮類別清單時，模型會不會仍回報清單外的類別**（O2 / P2） | 廠商 model card 說「可提供新類別」，我們刪掉的舊 config 記錄「限縮後仍吐 Profanity」。兩者不互斥（**能加 ≠ 能減**），但**沒有任何一手文件保證限縮完備**。目前是**我方事後過濾** → 意思是**未授權類別的命中照樣發生** |
| **`lm_head` LoRA 在 vLLM 是否真的生效**（O8） | 社群大量回報 adapter 含 `lm_head` 載不進 vLLM。**載入成功但分類品質靜默崩壞**是最壞情況 —— 必須與 HF PEFT 參考實作逐 case 比對，不可只看「有回 200」 |
| **雙 adapter 併發是否互相污染**（O9） | 交叉驗證：對 `topic_control` 名字送 content-safety prompt，輸出應是 topic-control 行為 |
| **TP=2 + Ada 卡的 LoRA startup**（O10） | vLLM #42583 是否命中；**先不要開 `--fully-sharded-loras`** |

### 3.3 部署工具缺口

- **部署腳本只 serve `content_safety` 一顆**（單一 `--lora-modules`）。要開 topic control 得手動加第二個 `--lora-modules` + `--max-loras 2`，**腳本還沒做**
- **安裝指南寫的是退役的 sidecar 路徑**（見 §5）
- 沒有 `topic_control` 的 smoke test（腳本的 `verify` 只測 content-safety 的 safe/unsafe）

### 3.4 產品能力缺口（結構性，不是待辦）

- **無 severity / confidence**：`llm_classifier` 是 `honors_content_threshold=True`，NemoGuard 是 False。三處一手來源確認只有 binary + 類別字串
  > 對照組值得知道：**OpenAI Guardrails 的 `off_topic_prompts` check 反而有 confidence 0.0–1.0 + 可設 threshold**。所以「專用模型 vs prompt 框架」是真的，但在**可調嚴格度**這個維度我們輸
- **streaming output enforce** 仍是 V2.1（issue #2446）
- **不是廠商背書的部署方式**：vLLM + LoRA 是 vLLM 支援、NVIDIA 未背書（官方教學是一個 adapter 一個 NIM 容器）。代價是失去 TRT-LLM 優化與 vendor 支援面
- **誤擋機率上升**：union + OR 意味著並用兩個主題判定源時誤擋嚴格上升，而主題誤報本來就是 PRD-250 風險矩陣首要項。緩解是 shadow-first，**不是改 fold 方向**

---

## 4. 部署什麼來提供 endpoint

### 4.1 誰負責什麼

| | 誰的 | 說明 |
|---|---|---|
| GPU 主機、維運、可用度 | **客戶** | 平台**不代管、不代付、不提供共用判定端點**（PRD-279 non-goal） |
| 模型選擇 | **我方釘死** | served name 必須是 `content_safety` / `topic_control`；serve 不同名字是**部署錯誤**，由連線測試曝出來，契約不會靜默適應 |
| prompt / parser / fold / fail-closed | 我方 | 在 gateway in-process |

判定**不消耗租戶 token 額度**（它不是在跟聊天模型對話），代價是客戶自付 GPU。

### 4.2 硬約束：必須 vLLM + HF 權重，不得走 NIM

| | 理由（皆一手來源） |
|---|---|
| **MUST**：OSS 推論伺服器 + HuggingFace 權重自架 | 權重走 NVIDIA Open Model License（no-charge、royalty-free、**無 production 限制**），不觸發 NVAIE |
| **MUST NOT**：改走廠商 NIM 容器 | (a) developer program 軟體明文 "**not for use, distribution or deployment in production**"，生產要買 NVAIE 訂閱；(b) ContentSafety NIM support matrix 要求 **48 GB GPU memory**（支援 A100/H100/L40S/A6000），遠超目標硬體 |

> 這不是偏好，是**唯一可行**路徑。若日後為了省事改用 NIM，生產部署就從零成本變成付費訂閱。

### 4.3 兩個部署變體

腳本：`install_service/scripts/deploy-nemoguard-judge.sh`　指南：`install_service/GUARDRAIL_JUDGE_NEMOGUARD.md`

| | `fp8`（預設） | `lora` |
|---|---|---|
| 權重來源 | `GaleneAI/llama-3.1-nemoguard-8b-content-safety-merged-FP8-Dynamic`（預合併、公開） | `meta-llama/Llama-3.1-8B-Instruct` + `nvidia/llama-3.1-nemoguard-8b-content-safety` |
| GPU | **1 張** | 2 張（預設 TP=2） |
| 記憶體 | weights 8.49 GiB + KV 4.02 GiB ≈ **13.5 GiB** @ `GPU_MEM_UTIL=0.70` | ~15.1 GiB weights（bf16），**≥16 GB VRAM**，實測 2× RTX 4000 Ada (20 GB)，跨兩卡 ~20.5 GiB |
| `HF_TOKEN` | **不需要** | **需要**（Meta base 是 gated） |
| 能掛第二顆 adapter | ❌ merged 模型做不到 | ✅ |
| 精度 | FP8 W8A8，Ada (sm_89) 以上原生 | bf16 |

**選哪個**：
- 只要 content filter → **`fp8`**（一張卡、不用處理 Meta gated repo）
- 要**同時**開 topic control → **必須 `lora`**（同一顆 base 熱掛兩個 adapter）

### 4.4 部署指令

```bash
# 預設 fp8：公開權重、一張 GPU、不需 token
./scripts/deploy-nemoguard-judge.sh up

# bf16 base + LoRA —— 之後要在同一顆 base 上加掛 topic_control 就走這個
JUDGE_VARIANT=lora HF_TOKEN=hf_xxx ./scripts/deploy-nemoguard-judge.sh up

# 卡跟別的工作負載共用 → 縮 KV 預算
GPU_MEM_UTIL=0.55 MAX_NUM_SEQS=16 ./scripts/deploy-nemoguard-judge.sh up

# 其他子命令
./scripts/deploy-nemoguard-judge.sh status   # 容器 + /v1/models
./scripts/deploy-nemoguard-judge.sh verify   # safe→safe, pipe-bomb→unsafe
./scripts/deploy-nemoguard-judge.sh logs
./scripts/deploy-nemoguard-judge.sh down
```

常用覆寫：`PORT`（預設 18000）· `CUDA_DEVICES` · `TENSOR_PARALLEL` · `MAX_MODEL_LEN`（預設 4096）· `VLLM_IMAGE`（預設 `vllm/vllm-openai:v0.19.1`）· `READY_TIMEOUT`（預設 600s）

**要同時 serve topic_control（腳本尚未支援，須手動）**：以 `lora` 變體為底，加第二個 `--lora-modules topic_control=nvidia/llama-3.1-nemoguard-8b-topic-control` 與 `--max-loras 2`，並**保持 `--max-lora-rank 16`**（取兩顆的最大值；為單顆 content-safety 設的 16 不可順手調降成 8）。**不要開 `--fully-sharded-loras`**（vLLM #10342 / #42583）。

驗收不能只看「載得起來」—— 要驗**輸出正確性**（O8）與**交叉不污染**（O9）。

### 4.5 接進 Xparse（三步，全部走既有機制）

```
1. 建 ProviderCredential
   provider = nemoguard（migration 0243 已 seed）
   endpoint = http://<judge-host>:18000
   授權邊 = ADR-310 access_scope / GroupCredentialGrant

2. 開 egress allowlist（預設全拒）
   XPARSE_JUDGEMENT_EGRESS_ALLOWLIST=judge.internal:18000
   ← 沒加就連 authoring 期的 test-judgement 都打不出去

3. policy 指名該憑證
   classifier.judgement_credential_ref = <credential name>
   classifier.content_filter.engines += nemoguard_content_safety
   classifier.on_topic.engines       += nemoguard_topic_control
```

驗收：`POST /iam/provider-credentials/{uuid}/test-judgement` → **content-safety 那顆** 2xx 且 verdict 可解析即 `success: true`；
topic-control 缺席時 `topic_control_ok: false` 且 `provider_info` 會點名缺哪顆、缺了會怎樣（C-223-48 Rev.2）。

> **2026-09-18 之前這裡寫的是「兩顆都要過」**，而預設部署只 serve 一顆 ⇒ 這個按鈕在正常環境下**永遠是紅的**。
> 一個恆紅的驗證等於沒有驗證：真正該抓的失敗（金鑰被撤、allowlist 被改）會躲在那片紅後面。判準已於
> PR #5074 改為只看 content-safety，SPEC-223 C-223-48 同步 Rev.2。

---

## 5. ⚠️ 部署前必讀的陷阱：兩條 wiring 路徑不是同一回事

部署腳本跑完會印出這段「next steps」，**它是給退役的 sidecar 路徑的**：

```
XPARSE_GUARDRAIL_JUDGE_BASE_URL=http://<host>:18000/v1
XPARSE_GUARDRAIL_JUDGE_API_KEY=EMPTY
docker compose --profile guardrails up -d xparse-guardrails
```

| | 舊 sidecar 路徑 | 新 ADR-375 路徑 |
|---|---|---|
| endpoint 從哪來 | process-global env `XPARSE_GUARDRAIL_JUDGE_BASE_URL` | **per-tenant `ProviderCredential.endpoint`** |
| 誰呼叫模型 | `xparse-guardrails` sidecar（:8400） | **gateway in-process** |
| 現況 | NeMo engine 已被 ADR-309 PR-7 刪除；`engine/nemo/` 空目錄、registry 未註冊 | 活的 |

程式碼註解講得很白（`xparse_iam/api/schemas/_policy.py:158`）：那個 env var **「no gateway code reads」**。

> **實務結論**：GPU 端那半（`deploy-nemoguard-judge.sh up`）照用，**忽略它印出的 sidecar next-steps**，改走 §4.5 的三步。腳本與指南該更新，這是 §3.3 的待辦。

---

## 6. 對客戶怎麼說（可宣稱 / 不可宣稱）

**可宣稱**：
1. **NVIDIA 生態可宣稱** —— 標案技術要求，可直接驗證
2. **判定資料落地** —— 對 OpenAI 路徑是**結構性**差異：那條路徑必須把原文送出
3. **判定不花 token** —— guardrail 每個 request 都跑，8B 本地分類器把這條疊加成本歸零
4. **主題判定用專用模型** —— topic-control 是 LoRA 微調於 ~1,080 筆合成多輪對話、9 個域（finance / health / education / taxes / real estate / computer troubleshooting / travel / banking / legal）

**不可宣稱（紅線）**：
- ❌ **中文判得更準** —— dataset card 明寫語言為 "**English (may contain small samples in other languages)**"；model card 唯一的「多語」指的是 base model，非微調後能力。此宣稱經對抗式查證判定為 **REFUTED as written**，不是「證據弱」。任何對外文案、Console 文案、標案文件都不得以任何形式復活它
- ❌ **準確度優於通用判官** —— 廠商 benchmark 全在英文，我們**沒跑過對比**
- ❌ **有分級強度** —— 結構上沒有
- ⚠️ **v3（CultureGuard）** 有 9 語言含 Mandarin **zh-CN**、386k 樣本，model card 另宣稱 zero-shot 支援 20+ 語言 —— 但**全篇無 Traditional Chinese / zh-Hant**，且 TWGuard 顯示繁中 regional variety 是已知弱點。換世代換不到繁中保證。**重開條件**：shadow 期實測繁中誤判率不可接受時，重開世代評估

---

## 7. 一手來源

| 主題 | URL |
|---|---|
| content-safety model card | https://huggingface.co/nvidia/llama-3.1-nemoguard-8b-content-safety |
| topic-control model card | https://huggingface.co/nvidia/llama-3.1-nemoguard-8b-topic-control |
| Aegis 2.0 論文（12 top-level + 9 fine-grained = 21 harm 類） | https://arxiv.org/abs/2501.09004 |
| Aegis 2.0 dataset card（語言聲明、33,416 樣本） | https://huggingface.co/datasets/nvidia/Aegis-AI-Content-Safety-Dataset-2.0 |
| ContentSafety NIM（48 GB 要求） | https://docs.nvidia.com/nim/llama-3-1-nemoguard-8b-contentsafety/latest/index.html |
| NVAIE Product-Specific Terms | https://www.nvidia.com/en-us/agreements/enterprise-software/product-specific-terms-for-ai-products/ |
| OpenAI Guardrails off-topic（對照組） | https://openai.github.io/openai-guardrails-python/ref/checks/off_topic_prompts/ |
| v3 / CultureGuard | https://huggingface.co/nvidia/Llama-3.1-Nemotron-Safety-Guard-8B-v3 · https://arxiv.org/html/2508.01710 |

> **樣本數口徑打架**：論文摘要說 **34,248**，dataset card 說 **33,416**（train 30,007 / val 1,445 / test 1,964）。引用時標明來源，別混用。
>
> **taxonomy 計數口徑**：model card 是 prompt 面 S1–S23；dataset card 是 12 core + 9 fine = **21 harm** + 2 non-unsafe（Safe / Needs Caution）。**21 是 harm 本體**，授權介面只該出現 harm 類。

### 交付義務（法務）

底層 base 帶 **Meta Llama 3.1 Community License §1(b)(i)** 標示義務，觸發語含「提供**含有**它們的產品或服務」——**不是只有散佈權重才觸發**。義務 = 附 Agreement 副本 + 在網站／UI／blog／about／產品文件**擇一**顯著標示 **"Built with Llama"** + Notice 檔。命名義務只約束對外散佈的衍生**模型名**，本案不微調故不觸發。

---

## 8. 相關文件

- `docs/prd/PRD-279-nemoguard-self-hosted-judgement-source.md` — what & why
- `docs/adr/ADR-375-nemoguard-self-hosted-judgement-source.md` — how
- `docs/specs/SPEC-223-guardrail-v2-contract.md` — 契約（C-223-39/42/43/44/47/48）
- `docs/research/RESEARCH-nemoguard-lora-judgement-source-evidence-2026-08-07.md` — evidence pack
- `docs/plans/nemo-guardrail.md` — D-1..D-10 拍板紀錄
- `install_service/GUARDRAIL_JUDGE_NEMOGUARD.md` — 安裝指南（**sidecar 段已過期**）
