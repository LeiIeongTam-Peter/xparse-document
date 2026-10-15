# Model 是什麼？（白話版）

> 一份給「想快速搞懂 Xparse 怎麼跑模型」的人看的文件。盡量用簡單的話 + 比喻，技術名詞保留英文。

---

## 1. 「Model」到底是什麼？

先破除一個直覺誤會：

> 在 Xparse 裡，**「Model」不是只有那一坨神經網路權重檔案**。它是一個「**受管理的 LLM 部署單位**」。

用開餐廳比喻：

- 「Model」**不是**「冰箱裡那塊生牛肉」。
- 「Model」**是**「菜單上那道菜」——包含食材（權重）、食譜（設定）、誰能點（哪個租戶可用）、出餐狀態（有沒有在供應）。

所以一個 Model 是「**權重 + 設定 + 授權 + 運行狀態**」綁在一起的東西。

---

## 2. 一個 Model 包含哪些東西？

Xparse 把 Model 拆成三層（這是 ADR-157 / ADR-158 的設計）：

| 層 | 名字 | 它是什麼 | 比喻 |
|---|---|---|---|
| 身分 | **ModelDefinition** | 模型的「產品名」，跨版本不變 | 「Qwen3-32B 這道菜」 |
| 版本 | **ModelVersion** | 某個**不可變**的版本（含 engine、image、權重來源、參數） | 「Qwen3-32B 的 1.2.0 版食譜」 |
| 部署 | **ModelDeployment** | 「誰要用、用哪版、配多少額度」 | 「法務部點了 1.2.0 這版」 |

再加上實際的「料」和「運行狀態」：

| 東西 | 它是什麼 | 存在哪 |
|---|---|---|
| **權重 bytes** | 真正那幾十 GB 的 `.safetensors` 檔 | MinIO / S3 倉庫 |
| **ModelManifest** | 清單 + 每個檔的 sha256（用來驗有沒有被竄改） | 跟權重放一起 |
| **Runtime state** | 現在跑在哪台、哪個 port、健不健康、endpoint URL | IAM 的 Postgres |

### 一個重要觀念：權重是「共享的」，不是「租戶私有的」

`qwen3-32b@1.2.0` 那一坨 bytes，**不管哪個租戶用都是同一份、一模一樣**。
真正「屬於某個租戶」的只是 **ModelDeployment**（誰能用、配多少）——而這個隔離是在 **Postgres + IAM 那一層**做的，**不在儲存層**。

> 這就是為什麼模型倉庫用「一個 bucket 裝全部」就好，不需要「每個租戶一個 bucket」。

---

## 3. 什麼時候、在哪裡會用到 Model？

有兩個時間點會「用到」Model，很容易搞混，要分開看：

### 時機 A — 上架時（把一個 Model 準備好、跑起來）

由**管理員 / 工程師**觸發。目標是「讓這道菜可以開始供應」。

### 時機 B — 服務時（客戶真的送出一個聊天請求）

由**終端客戶**觸發。目標是「把客戶的問題送到正在跑的模型、把答案串回去」。

下面第 5 節會分別畫出這兩條流程。

---

## 4. 後端服務有哪些？誰依賴誰？（重點）

### 4.1 每個服務負責什麼

| 服務 | 角色（一句話） | 有沒有 DB |
|---|---|---|
| **Gateway**（`bustream/`） | 所有請求的入口；驗證、路由、串流、發 audit。**每個請求都會經過它** | ❌ 無 |
| **IAM**（`xparse_iam/`） | 治理資料中心：租戶/群組/應用/API key/policy/模型目錄/運行狀態。**唯一握有 Postgres 的服務** | ✅ **Postgres** |
| **Fleet**（`xparse_fleet/`） | GPU 排程、模型目錄 reconcile、給節點派工的命令佇列 | (本地狀態) |
| **agentd**（`xparse_node_mgr/`） | 跑在 GPU 機器上的代理：下載權重、開 vLLM 容器、回報健康 | (本地檔) |
| **artifact_store**（`xparse_artifact_store/`） | 權重倉庫的抽象層：可換 MinIO / HuggingFace / tar / 本地檔 | ❌（檔案/S3） |
| **resource_manager**（`xparse_resource_manager/`） | 共享端點的容量管制：排隊、租約、限流 | (本地狀態) |
| **audit**（`3rd/xparse_audit/`） | 把所有事件寫成不可竄改的證據；**壞掉也不擋請求**（fail-open） | (JSONL 檔) |

### 4.2 一條鐵則（non-negotiable）

> **Gateway 和 Console 只能透過 IAM 的 HTTP API 拿資料，絕對不准直接讀 IAM 的 Postgres。**

為什麼：保證 tenant 隔離、scope 驗證在邊界做、所有存取都留下 audit。

### 4.3 依賴方向（箭頭：A → B 代表「A 依賴 B」）

```
客戶請求
   │ HTTP
   ▼
Gateway ──── HTTP API（驗證/policy） ────▶ IAM ──握有──▶ Postgres
   │                                         ▲
   │ HTTP（每 30s 拉模型 endpoint 清單）        │ HTTP API（回報運行狀態，身分=fleet_writer）
   ▼                                         │ POST /iam/fleet-runtime/deployments/{uuid}/events
 Fleet ◀──── HTTP（心跳 + 領命令）──── agentd
                                       │ in-process import
                                       ▼
                                 artifact_store ──▶ MinIO / HuggingFace / tar
                                       │
                                       ▼
                                 開 vLLM 容器（讀唯讀掛載的權重）

所有服務 ──（fail-open，不擋請求）──▶ audit
IAM ──（入場時查容量，選配）──▶ resource_manager
```

**用一句話記每條依賴：**

- `Gateway → IAM`：驗證每個請求，走 **HTTP API**（不准直連 DB）。
- `Gateway → Fleet`：每 30 秒拉一次「哪個模型在哪個 endpoint」。
- `Fleet → IAM`：把運行狀態（endpoint URL、健康、phase）**寫回 IAM**，身分是 `fleet_writer`。
- `agentd → Fleet`：心跳上去、把命令領下來（命令佇列）。
- `agentd → artifact_store → MinIO`：下載權重（in-process 呼叫，不是另一個服務）。
- `IAM → resource_manager`：入場控管時查容量（選配）。
- `所有人 → audit`：發事件；audit 掛掉也不影響主流程。

> 關鍵：**IAM 是唯一的「真相來源」**（握 DB）。Fleet 是它的 client（只能透過 API 寫），Gateway 也是它的 client（只能透過 API 讀）。

---

## 5. 完整 Workflow

### 流程 A — 上架（怎麼把一個 Model 弄上線）

```
① 工程師寫 YAML（engine / image / 權重來源 / 參數）
        │  git PR review
        ▼
② Fleet 的 reconciler 把 YAML 同步進 IAM Postgres
        │  （變成 ModelDefinition + ModelVersion，唯讀目錄）
        ▼
③ 權重 bytes 被匯入 MinIO 倉庫：s3://xparse-models/<def>/<ver>/
        │
        ▼
④ 管理員在 Console 按「部署 1.2.0 給法務部」
        │  （寫入 ModelDeployment：desired_version=1.2.0）
        ▼
⑤ Fleet 發現「想要的版本 ≠ 正在跑的版本」，發一個 deploy 命令進命令佇列
        │
        ▼
⑥ agentd（GPU 機器上）心跳時領到命令，開始：
        ├─ 從 artifact_store 拉權重（MinIO → 本機 content-addressed 快取）
        ├─ 驗 sha256（對不上就中止，舊版本繼續服務）← 安全保證
        ├─ 把快取唯讀 bind-mount 給容器
        ├─ 開 vLLM 容器、分配 port
        └─ 一直 poll /health 直到 200 OK
        ▼
⑦ agentd 心跳回報 Fleet：「serving，endpoint=http://...:18000」
        │
        ▼
⑧ Fleet 透過 HTTP API 把 endpoint_url 寫回 IAM Postgres
        │  POST /iam/fleet-runtime/deployments/{uuid}/events
        ▼
   ✅ 這個 Model 現在「上架、可服務」了
```

### 流程 B — 服務（客戶送一個聊天請求）

```
① 客戶 POST /v1/chat/completions（帶 API key）到 Gateway
        │
        ▼
② Gateway 呼叫 IAM 驗證（HTTP API）
        │  IAM 回 AuthContext：這個 key 屬於誰、能用哪些 model、
        │  以及每個 model 的 endpoint_url（從流程 A ⑧ 存進去的）
        ▼
③ Gateway 解出 provider key + 套 routing 策略 + 找到 endpoint_url
        │  （找不到 endpoint → 直接 422 報錯，不會默默亂送）
        ▼
④ Gateway 把請求送到那台 vLLM 容器（流程 A 開起來的）
        │
        ▼
⑤ vLLM 回 token，Gateway 用 SSE 串流回客戶
        │
        ▼
⑥ 全程發 audit 事件（fail-open，不擋請求）
```

---

## 6. 三十秒總結

- **Model** = 一個受管理的 LLM 部署單位 = 權重 + 設定 + 授權 + 運行狀態（拆成 Definition / Version / Deployment 三層）。
- **權重是共享公共財**，租戶隔離在 IAM/Postgres 層，不在儲存層。
- **IAM 握有唯一的 DB，是真相來源**；Gateway 和 Fleet 都只能透過它的 HTTP API 存取（鐵則：不准直連 DB）。
- **上架流程**：YAML → reconcile 進 IAM → 權重進 MinIO → Console 部署 → Fleet 派工 → agentd 拉權重+驗證+開 vLLM → 把 endpoint 寫回 IAM。
- **服務流程**：客戶 → Gateway → IAM 驗證（拿到 endpoint）→ 送到 vLLM → SSE 串流回去 → 全程 audit。

---

## 參考（想深入再看）

- 架構決策：`docs/adr/ADR-157`（catalog 三層）、`ADR-158`（三實體資料模型）、`ADR-159`（artifact plane）
- 邊界鐵則：`docs/adr/ADR-205`（Gateway 只能走 IAM API）、`ADR-093`（執行安全不變量）
- 關鍵程式碼：
  - `bustream/gateway/iam_http_client.py` — Gateway 怎麼呼叫 IAM
  - `xparse_iam/.../api/ninja_api/_fleet_runtime.py` — Fleet 回寫運行狀態的 endpoint
  - `xparse_node_mgr/core/download_manager.py` — agentd 怎麼下載權重
  - `xparse_node_mgr/core/instance_manager.py` — agentd 怎麼開 vLLM
  - `xparse_artifact_store/domain/ports.py` — 倉庫的三個抽象 port
