# Xparse Warden — 技術文件

> **版本**：v0.1.0  
> **更新日期**：2026-05-31  
> **參考文件**：PRD-147、ADR-178

xparse-warden 是一個輕量級自託管 Ops 監視服務，作為 docker-compose stack 中的獨立容器運行。它週期性執行三類健康檢查、將狀態變化寫入本地 SQLite，並對外提供 Prometheus 指標端點，是 Xparse 平台的唯讀觀測層。

---

## 一、服務端口清單（Service Ports）

| 服務名稱 | 端口號碼 | 通訊協定 | 用途說明 |
|----------|----------|----------|----------|
| xparse-warden | `9100` | HTTP | 主服務端口（FastAPI / uvicorn）：REST API、健康檢查、Prometheus 指標 |
| xparse-audit（被監視） | `8001` | HTTP | Warden C3 檢查呼叫 audit diagnostics 端點時所使用的目標端口 |

**環境變數控制：**

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `WARDEN_HOST` | `0.0.0.0` | FastAPI 綁定地址 |
| `WARDEN_PORT` | `9100` | FastAPI 綁定端口 |
| `WARDEN_AUDIT_URL` | `http://xparse-audit:8001` | xparse-audit 服務位址 |
| `WARDEN_CHECK_INTERVAL_SEC` | `60` | 檢查迴圈預設間隔（秒） |
| `WARDEN_HISTORY_DIR` | `/var/warden` | SQLite 歷史資料庫存放目錄 |
| `WARDEN_HISTORY_RETENTION_DAYS` | `7` | 歷史資料保留天數 |
| `WARDEN_COMPOSE_FILE` | `/opt/xparse/docker-compose.yml` | 受監視的 docker-compose 檔案路徑（唯讀） |
| `WARDEN_ENV_FILE` | `/opt/xparse/.env` | 受監視的環境變數檔案路徑（唯讀） |
| `WARDEN_AUDIT_BEARER_KEY` | `""` | 呼叫 audit 服務時使用的 Bearer token |
| `WARDEN_SLACK_WEBHOOK` | `""` | Slack Webhook URL（P5，尚未實作） |
| `WARDEN_HEARTBEAT_URL` | `""` | 外部心跳 URL（如 healthchecks.io） |
| `WARDEN_LOG_LEVEL` | `INFO` | 日誌等級 |

---

## 二、前端 API 清單（Frontend APIs）

> xparse-warden 設計為純後端觀測服務，**不提供前端使用者介面**。  
> 以下端點為 Console 運維人員或外部監控工具（Prometheus、Grafana、healthchecks.io）直接呼叫的 HTTP API。

| HTTP 方法 | 端點路徑 | 目標服務 | 功能說明 |
|-----------|----------|----------|----------|
| `GET` | `/health` | xparse-warden | Docker HEALTHCHECK 目標；回傳服務整體狀態與最後一次週期的摘要資訊 |
| `GET` | `/metrics` | xparse-warden | Prometheus exposition format；Grafana / Prometheus scrape 端點 |
| `GET` | `/check` | xparse-warden | 取得所有檢查項目的最新結果（JSON 格式） |
| `GET` | `/check/{name}` | xparse-warden | 取得指定單一檢查項目的詳細結果與子結果 |
| `GET` | `/history` | xparse-warden | 取得指定時間窗口內的狀態變化歷史記錄（`?since=1h\|30m\|7d\|60s`） |
| `POST` | `/alerts/test` | xparse-warden | 測試 Slack Webhook 警報（P5 stub，目前回傳 `{"sent": false}`） |

**`/health` 回應格式：**
```json
{
  "status": "healthy" | "degraded",
  "version": "0.1.0",
  "checks_run": 3,
  "checks_count": 3,
  "last_cycle_age_sec": 12.4,
  "history_degraded": false
}
```

**`/check` 回應格式：**
```json
{
  "compose_drift": {
    "check_name": "compose_drift",
    "status": "pass" | "fail" | "error",
    "detail": { "declared_count": 12, "running_count": 12, "missing": [], "unexpected": [] },
    "ts": "2026-05-31T10:00:00+00:00",
    "sub_results": []
  },
  "container_health": { "..." },
  "audit_diagnostics": { "..." }
}
```

**`/history` 回應格式：**
```json
{
  "since": "1h",
  "events": [
    {
      "check_name": "container_health",
      "status": "fail",
      "detail": { "total_containers": 10, "unhealthy_count": 1 },
      "ts": "2026-05-31T09:45:00+00:00"
    }
  ]
}
```

---

## 三、後端 API 清單（Backend APIs）

### 3.1 Warden 對外公開的 API

| HTTP 方法 | 端點路徑 | 所屬服務 | 功能說明 | 呼叫來源 |
|-----------|----------|----------|----------|----------|
| `GET` | `/health` | xparse-warden | 服務健康狀態摘要 | Docker daemon（HEALTHCHECK）、Prometheus、外部監控 |
| `GET` | `/metrics` | xparse-warden | Prometheus 格式指標導出 | Prometheus scraper、Grafana |
| `GET` | `/check` | xparse-warden | 所有檢查項目最新結果（JSON） | 運維人員、監控腳本 |
| `GET` | `/check/{name}` | xparse-warden | 指定檢查詳細結果（含子結果） | 運維人員、Grafana drill-down |
| `GET` | `/history` | xparse-warden | 狀態變化時序記錄（SQLite） | 運維人員、告警系統 |
| `POST` | `/alerts/test` | xparse-warden | Slack 警報測試（P5 stub） | 運維人員 |

**Prometheus 指標清單（`/metrics`）：**

| 指標名稱 | 類型 | 說明 | 常見標籤 |
|----------|------|------|----------|
| `xparse_warden_check_status` | gauge | 1=pass, 0=fail, -1=error | `{check="compose_drift"}` `{check="compose_drift", service="xparse-prometheus", kind="missing"}` |
| `xparse_warden_last_check_age_seconds` | gauge | 距上次檢查完成的秒數 | — |
| `xparse_warden_cycle_count_total` | counter | 自啟動以來的總檢查週期數 | — |
| `xparse_warden_history_degraded` | gauge | 1 = SQLite 歷史層已降級 | — |

---

### 3.2 Warden 主動呼叫的外部 API

| HTTP 方法 | 端點路徑 | 所屬服務 | 功能說明 | 呼叫來源 |
|-----------|----------|----------|----------|----------|
| `GET` | `/diagnostics/store` | xparse-audit（port 8001） | 取得 audit 儲存層診斷資訊（重載狀態、錯誤計數）；C3 檢查使用 | Warden 排程器（每 30 秒） |
| `GET` | `${WARDEN_HEARTBEAT_URL}` | healthchecks.io（外部） | 心跳 ping，確保 Warden 自身存活被外部偵測到（INV-178-4） | Warden 排程器（每 5 分鐘，P5） |

**Docker Engine API（本地 Unix Socket）：**

| 操作 | Docker API 路徑 | 說明 | 使用檢查 |
|------|-----------------|------|----------|
| 列出運行中容器 | `GET /containers/json?filters={"status":"running"}` | 比對 compose 聲明 vs 實際運行 | C1 ComposeDriftCheck |
| 取得容器詳情 | `GET /containers/{id}/json` | 讀取健康狀態與重啟計數 | C2 ContainerHealthCheck |

> **重要**：Docker socket 以 `:ro`（唯讀）方式掛載，且合約測試（INV-178-1）靜態分析原始碼，確保不存在任何寫入呼叫。

**`/diagnostics/store` 回應格式：**
```json
{
  "reload_count": 123,
  "events_loaded": 45678,
  "last_reload_error": null,
  "per_file_errors": {},
  "last_reload_at": "2026-05-31T10:30:00+00:00"
}
```

---

## 四、工作流程（Workflows）

### 4.1 啟動序列

**發起方**：Docker daemon / `docker compose up`

```
[Docker daemon]
  │
  └─▶ 啟動 xparse-warden 容器
        │
        ├─ 1. 初始化 HistoryStore
        │      └─ 連接 / 建立 SQLite（/var/warden/state.db，WAL 模式）
        │
        ├─ 2. 建構 CheckContext
        │      └─ docker client、httpx client、compose 路徑、env 路徑、設定
        │
        ├─ 3. 建立 CheckRegistry
        │      ├─ C1 ComposeDriftCheck（interval=60s）
        │      ├─ C2 ContainerHealthCheck（interval=30s）
        │      └─ C3 AuditDiagnosticsCheck（interval=30s）
        │
        ├─ 4. 預熱週期（Warmup）
        │      └─ 同步執行一輪所有檢查 → 確保 /metrics 有初始資料
        │
        ├─ 5. 啟動獨立非同步任務
        │      ├─ Task: C1 迴圈（每 60s）
        │      ├─ Task: C2 迴圈（每 30s）
        │      └─ Task: C3 迴圈（每 30s）
        │
        └─ 6. FastAPI / uvicorn 就緒，開始接受 HTTP 連線
```

---

### 4.2 週期性健康檢查執行流程

**發起方**：Warden 排程器（Scheduler._loop_check）  
**週期**：C1 每 60s、C2 & C3 每 30s

```
[Scheduler] ── 等待 interval_sec ──▶
  │
  ├─ check.run(ctx)
  │    │
  │    ├─ [C1 ComposeDriftCheck]
  │    │    ├─ 讀取 /opt/xparse/docker-compose.yml（唯讀）
  │    │    ├─ 解析 services: 鍵（排除 init 服務、profile-gated 服務）
  │    │    ├─ Docker Socket → GET /containers/json?status=running
  │    │    └─ 比對差異 → CheckResult(status, detail, sub_results)
  │    │
  │    ├─ [C2 ContainerHealthCheck]
  │    │    ├─ Docker Socket → GET /containers/{id}/json（全部容器）
  │    │    ├─ 提取 Health.Status + RestartCount + StartedAt
  │    │    ├─ 計算本週期重啟增量（delta）
  │    │    └─ 分類狀態 → CheckResult(status, detail, sub_results)
  │    │
  │    └─ [C3 AuditDiagnosticsCheck]
  │         ├─ HTTP GET http://xparse-audit:8001/diagnostics/store
  │         │    （Authorization: Bearer <WARDEN_AUDIT_BEARER_KEY>，若已設定）
  │         ├─ 解析 last_reload_error + per_file_errors
  │         └─ 判斷結果 → CheckResult(status, detail)
  │
  ├─ 例外處理（任一 check 拋出例外）
  │    └─ 捕捉 → CheckResult(status=ERROR, detail={error: ...})
  │         └─ 不影響其他並行檢查（INV-178-2）
  │
  ├─ 更新 Scheduler.latest[check.name]（記憶體快取）
  │
  ├─ 非同步寫入 HistoryStore（只記錄狀態變化）
  │    ├─ 成功 → 繼續
  │    └─ 失敗 → is_degraded = True（不阻塞指標，INV-178-3）
  │
  └─ 重複
```

---

### 4.3 Prometheus 指標查詢流程

**發起方**：Prometheus scraper / Grafana  
**端點**：`GET http://xparse-warden:9100/metrics`

```
[Prometheus Scraper]
  │
  └─▶ GET /metrics
        │
        └─ PromExporter.render(Scheduler.latest)
             ├─ 從記憶體快取讀取（不觸碰 SQLite）（INV-178-3）
             ├─ 生成 xparse_warden_check_status{...} gauges
             ├─ 生成 xparse_warden_last_check_age_seconds
             ├─ 生成 xparse_warden_cycle_count_total
             ├─ 生成 xparse_warden_history_degraded
             └─ 回傳 Prometheus text exposition format
```

---

### 4.4 歷史記錄查詢流程

**發起方**：運維人員 / 告警系統  
**端點**：`GET http://xparse-warden:9100/history?since=1h`

```
[呼叫方]
  │
  └─▶ GET /history?since=1h
        │
        ├─ 解析 since 參數（1h=3600s, 30m=1800s, 7d=604800s, 60s=60s）
        │
        ├─ HistoryStore.query(since_sec=3600)
        │    ├─ 正常模式 → SQLite WAL 時間範圍查詢
        │    └─ 降級模式（is_degraded=True） → 回傳空列表
        │
        └─▶ 回傳 {"since": "1h", "events": [...]}
```

---

### 4.5 Docker HEALTHCHECK 流程

**發起方**：Docker daemon（每 30 秒）

```
[Docker daemon]
  │
  └─▶ curl -fsS http://localhost:9100/health
        │
        └─ /health handler
             ├─ checks_run = len(Scheduler.latest)
             ├─ last_cycle_age_sec = 現在 - 最後一次週期完成時間
             ├─ history_degraded = HistoryStore.is_degraded
             ├─ status = "healthy" 若 checks_run == checks_count 且 age < threshold
             └─ status = "degraded" 若任一條件未滿足
```

---

### 4.6 Compose Drift 偵測流程（詳細）

**情境**：某個聲明在 docker-compose.yml 中的服務意外停止  
**發起方**：C1 ComposeDriftCheck（每 60s 週期）

```
[Scheduler] ── 觸發 C1 ──▶

  1. 讀取 /opt/xparse/docker-compose.yml（唯讀掛載）
     ├─ 解析 services: 區塊
     ├─ 排除 _INIT_SERVICES: {audit-db-init, audit-volume-init}
     └─ 排除帶有 profiles: 鍵的服務（profile-gated，預期缺失）
     → 得出 declared_set

  2. Docker Socket → 列出 status=running 的容器
     → 得出 running_set（以容器名稱為 key）

  3. 差異計算
     ├─ missing   = declared_set - running_set  （聲明但未運行）
     └─ unexpected = running_set - declared_set  （運行但未聲明）

  4. 產生 CheckResult
     ├─ missing 或 unexpected 非空 → status=FAIL
     ├─ 全部對齊 → status=PASS
     └─ 檔案讀取/Docker socket 錯誤 → status=ERROR

  5. 子結果（sub_results）
     └─ 每個 missing/unexpected 服務生成一筆，攜帶 kind 標籤
        供 Prometheus 細粒度告警使用

  6. 更新 Scheduler.latest["compose_drift"]
     └─ /metrics 反映最新 xparse_warden_check_status{check="compose_drift",...}
```

---

## 附錄：核心設計不變量

| 不變量 | 編號 | 說明 | 驗證機制 |
|--------|------|------|----------|
| 唯讀監管 | INV-178-1 | Warden 永遠不修改被監視的系統 | CI 靜態分析（`test_warden_readonly.py`）；docker socket `:ro` 掛載 |
| 檢查隔離 | INV-178-2 | 單一檢查故障不阻塞其他檢查 | 合約測試（`test_check_isolation.py`）；Scheduler try/except 包裝 |
| 指標可用性 | INV-178-3 | `/metrics` 在 SQLite 降級時仍可用 | 合約測試（`test_metrics_survives_history_failure.py`） |
| 監視器自身監視 | INV-178-4 | 外部心跳確保 Warden 消失可被偵測 | `WARDEN_HEARTBEAT_URL` 外部 dead-man's-switch |
