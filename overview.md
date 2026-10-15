# Xparse — 企業級 AI 推論編排與治理平台

## 這個專案在做什麼

Xparse 是一個讓企業在內部安全地使用 AI 模型的平台。

企業面臨的問題是：他們想用 GPT-4、Azure OpenAI、或自架的 vLLM / NemoClaw，但這些模型的 API 沒有提供**治理、追蹤、存取控制、流量保護**的能力。每個部門直接打模型 API 意味著：沒有辦法知道誰花了多少、沒有辦法限制某個應用只能用某個模型、也無法審計某筆請求。

Xparse 的解法是在企業與 AI Provider 之間加一層**智慧 Proxy**，提供：


| 能力            | 說明                                                           |
| ------------- | ------------------------------------------------------------ |
| **統一入口**      | 所有 AI 請求走同一個 OpenAI-compatible API，客戶端程式碼不用改                 |
| **身份與授權**     | 每個 API Key 屬於某個 Tenant → Group → Application，帶有明確的策略綁定       |
| **流量保護**      | Rate limit、circuit breaker、endpoint lease 排隊，防止 Provider 被打爆 |
| **政策執行**      | Guardrail 過濾、content policy、每個 Application 有獨立的模型使用規則        |
| **Audit 追蹤**  | 每筆請求都有 evidence-grade JSONL 日誌，含 chain of custody            |
| **自架 GPU 支援** | 企業可以把自己的 GPU 機器接進 Xparse，由平台統一管理模型部署                         |


---

## 系統架構

```
┌─────────────────────────────────────────────────────────────────┐
│                  Clients / SDK / Console App                     │
└──────────────────────────────┬──────────────────────────────────┘
                               │  OpenAI-compatible API
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│               Gateway  (bustream/)          port 8000            │
│                                                                  │
│  Auth → Policy → Admission → Endpoint Lease → StreamingManager  │
│                                      ↕                           │
│                               Audit emit (async)                 │
└──────┬──────────────┬─────────────────┬───────────────┬─────────┘
       │              │                 │               │
       ▼              ▼                 ▼               ▼
  IAM Service   ResourceManager   Fleet API     AI Providers
  (xparse_iam)  (xparse_resource  (xparse_      (OpenAI / Azure /
  port 8010     _manager)         fleet/)        vLLM / NemoClaw)
                port 8020         port 8090
                                       │
                               ┌───────┴──────────┐
                               ▼                  ▼
                          GPU Node Mgr      Container Platform
                          (agentd)          (Docker / nsjail)
```

**一句話記憶**：Xparse 的核心不是「接多少模型」，而是把推論請求放進一個可治理、可追蹤、可替換的執行系統。

---

## 四個平面

### 平面一 — Runtime Plane (`bustream/`)

所有流量的入口。接收 AI 請求 → 驗身份 → 檢查 Policy → 限流排隊 → 呼叫 Provider → 串流回傳。

完整請求路徑：

```
Client POST /v1/chat/completions
  → auth_handler        向 IAM 驗 API key，取得 tenant context
  → policy kernel       Policy 決策（純函數，不打 I/O）
  → admission           Rate limit + Circuit breaker
  → endpoint lease      向 ResourceManager 排隊申請 slot
  → StreamingManager    驅動 worker 打 Provider，管理 SSE 狀態機
  → audit emit          非同步寫 JSONL（不阻塞主流程）
  → SSE response        回傳給 client
```

### 平面二 — Governance Plane (`xparse_iam/`)

管理「誰是誰、誰可以用什麼、用多少」。所有資源的 CRUD、認證、授權都在這裡。

核心資源階層：`Tenant → Group → Application → APIKey`。每個 Application 可綁定 Policy Bundle、Guardrail、Rate Limit、Provider Credential（BYOK）。

### 平面三 — Endpoint Capacity Plane (`xparse_resource_manager/`)

保護每個 inference endpoint 不被打爆。Gateway 執行推論前必須申請一個 lease，拿到才能打 Provider，完成後釋放，超時未釋放的 lease 由 TTL reaper 自動清理。

### 平面四 — Agent Platform Plane (`xparse_fleet/` + `xparse_node_mgr/`)

讓企業把自己的 GPU 機器接進 Xparse，在上面部署 AI 模型（NemoClaw、vLLM）或 Agent App（OpenWebUI 等）。Fleet API 是 control plane；agentd 跑在每台 GPU 機器上做心跳、部署、監控。

---

## 跨平面請求流（典型案例）

```
① Client → Gateway        POST /v1/chat/completions
② Gateway → IAM           驗身份，取得 tenant / application / policy context
③ Gateway → ResourceMgr   排隊申請 endpoint lease
④ Gateway → Provider      HTTP 串流（帶 lease）
⑤ Gateway → ResourceMgr   釋放 lease
⑥ Gateway → Audit         非同步寫入 evidence-grade log（fail-open）

Gateway 另每 30 秒向 Fleet 拉一次 model-profiles，更新可路由的 endpoint 列表。
```

---

## 關鍵架構規則


| 規則                          | 原因                            |
| --------------------------- | ----------------------------- |
| Gateway 不可直讀 IAM DB         | 服務邊界清晰，IAM 是 Governance 的唯一來源 |
| Policy Kernel 是純函數          | 可測試、可快取、不引入隱藏 I/O 延遲          |
| Identity 在 request 邊界綁定後不可變 | 防止 mid-flight 身份替換，安全不變量      |
| Audit emit 必須 fail-open     | Audit 失敗不可阻斷推論服務（PRD-041）     |
| SSE reverse 事件只能發一次         | 狀態機規則，發完後不可再有 delta           |


完整規則：`docs/adr/ADR-093-execution-safety-invariants.md`

---

## 部署方式

```bash
# Pro（生產）
cd install_service && ./install.sh --edition pro --domain xparse.example.com --yes

# Enterprise（+ NemoClaw + Grafana）
./install.sh --edition enterprise --observability self-hosted --yes

# 本地開發（source-mounted）
docker compose -f docker-compose.pro.yml -f docker-compose.pro.dev.yml up -d

# Basic（單容器版，含 Console + SQLite）
cd docker/standalone && docker compose up -d
```

詳細部署說明：`docs/how-to-run.md`、`install_service/README.md`