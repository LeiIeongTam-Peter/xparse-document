# How to Run Xparse Locally

## Prerequisites

- Docker Desktop (running)
- Node.js + pnpm (for frontend hot-reload dev)
- Project root: `/Users/peter/Desktop/X-parse/xparse`

---

## 1. Environment Files

Two `.env` files must exist before starting:

| File | Purpose |
|------|---------|
| `xparse/.env` | Backend secrets (bootstrap key, DB password, LLM keys) |
| `xparse/frontend/console-app/.env.local` | Frontend dev proxy target |

Both are already configured. Do not commit them to git.

For local development, keep unified notification subscriptions enabled in
`xparse/.env`:

```bash
XPARSE_UNIFIED_SUBSCRIPTIONS_ENABLED=true
```

This makes the PRD-238 `/apis/iam/notification-subscriptions/*` API surface available
locally. Without this flag, those endpoints intentionally return `404` because
the feature is dark. After changing `xparse/.env`, run `./dev.sh up` again so
Compose recreates containers with the updated environment; plain
`docker restart` does not re-read `.env`.

---

## 2. Start the Backend Stack

From the project root (`xparse/`):

```bash
./dev.sh up
```

This starts **10 services** using three layered Compose files:

```
docker compose -f docker-compose.mvp.yml \
               -f docker-compose.mvp-audit.yml \
               -f docker-compose.mvp-fleet.yml up -d --build
```

### What starts

| Container | Role | Port |
|-----------|------|------|
| `xparse-ingress` | nginx TLS termination, main entry point | 3000 (HTTPS), 3080 (HTTP) |
| `xparse-gateway` | Inference proxy (FastAPI) | internal |
| `xparse-iam` | Identity & auth (Django + SQLite) | internal |
| `xparse-scheduler` | Resource scheduler (stub in MVP mode) | internal |
| `xparse-keycloak` | SSO / OIDC identity provider | 8180 |
| `xparse-console` | Frontend (pre-built image) | internal |
| `xparse-db` | PostgreSQL (audit storage only) | internal |
| `xparse-audit` | Audit query API (FastAPI) | 8001 |
| `xparse-notify-worker` | Notification pipeline looper (PRD-215 pull + PRD-203 drain, 30s) | internal |
| `xparse-fleet` | Fleet node registry (FastAPI, local build) | 8090 |

### Optional: Guardrails (sidecar + GLiNER detector)

Guardrail is safe to add to local Docker, but keep it **optional** so normal dev does
not have to run the 3.7GB detector image.

Start the full stack with guardrails:

```bash
./dev.sh up-guardrails
```

Or add/rebuild only the guardrail containers after the normal stack is already running:

```bash
./dev.sh guardrails
```

This activates the `guardrails` Compose profile and starts **two** containers
(ADR-309 / Guardrail V1 is PII-only via GLiNER; the NeMo engine and its judge
endpoint were retired in ADR-309 PR-7 — `gliner_pii` is the only registered
engine):

| Container | Role | Port | Image |
|-----------|------|------|-------|
| `xparse-guardrails` | Check-only sidecar shim (~239MB) — `POST /v1/guardrails/check` | internal `8400` | built from source → `xparse-guardrails:dev` |
| `xparse-gliner` | Self-hosted GLiNER PII detector (~3.7GB, model weights baked in, runs air-gapped `HF_HUB_OFFLINE=1`) | internal `8401` | **not built by `dev.sh`** — uses the local `xparse-gliner-server:probe` tag |

Call chain: `gateway → xparse-guardrails:8400 → xparse-gliner:8401`
(`XPARSE_GUARDRAIL_SIDECAR_URL` → `XPARSE_GLINER_SERVER_URL`; both have working
compose defaults, nothing needed in `.env`).

`dev.sh` also waits for the detector health check and runs a PII warmup call —
first GLiNER inference is slow, and without warmup the first guarded request can
hit `engine_timeout`.

**The detector image is not rebuilt by `dev.sh`.** `docker-compose.guardrails-local.yml`
only re-tags `xparse-gliner` to a local image (`XPARSE_GLINER_IMAGE`, default
`xparse-gliner-server:probe`) — it has no `build:` block, because baking the model
weights is a slow one-off. Rebuild it by hand when `services/gliner-server/` changes:

```bash
docker build -t xparse-gliner-server:probe services/gliner-server
```

The sidecar *is* built from local source (`services/guardrail-shim/Dockerfile`,
tagged `xparse-guardrails:dev`) so local runs never need the private ECR image.

Health check:

```bash
docker exec xparse-guardrails python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8400/health').read().decode())"
docker exec xparse-gliner     python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8401/health').read().decode())"
```

Notes:

- Starting the containers only makes the engine available. Gateway decides
  whether to run checks or block traffic from the **bound guardrail policy** and
  its `shadow` / `enforce` mode — not from env vars.
- In `enforce` mode, if a policy needs the sidecar and the sidecar is unavailable,
  Gateway fail-closes (HTTP 451 `engine_error`, INV-309-6) instead of silently
  passing traffic.
- CPU latency is the enforce-mode blocker, not wiring — probe with
  `scripts/probe_gliner_pii.py` before flipping any policy to `enforce`.
- `XPARSE_GUARDRAIL_JUDGE_BASE_URL` / `_API_KEY` are **dead for local dev** —
  `docker-compose.mvp.yml` no longer passes them to the sidecar. They survive
  only in the `install_service/tiers/*enterprise*` tiers (NeMo-era judge). Delete
  them from a local `.env` if still present.
- Guardrail V2 (`on_topic` / `content_filter`, ADR-318 / SPEC-223) needs **no new
  container and no judge endpoint**: the classifier LLM call happens in the
  gateway process against the tenant's own target model and credential.
- Full deployment/verify/troubleshooting guide: `deploy-guardrail-pii.md` (V1 PII)
  and `ontopic-contentfilter.md` (V2 classifier rails).

> **Notification pipeline（PRD-215/PRD-203）** 在本地是全自動的：
> audit 服務內建 60s 的 candidate projector；`xparse-notify-worker` 每 30s
> 把 candidates 拉進 IAM outbox 並派送到 inbox（用 `.env` 的
> `XPARSE_BOOTSTRAP_ADMIN_KEY` 當 audit internal API 的 service token）。
> 觸發一個已 seed 的規則事件（例如 deactivate 一個 policy bundle binding）
> 後，約 90 秒內 Console inbox 會出現通知。debug 順序：
> `docker logs xparse-audit`（candidates）→ `docker logs xparse-notify-worker`
> （`pull:`/`drain:` summary，`skipped_no_audience` 代表受眾解析為空）。

### Access points

| URL | What |
|-----|------|
| https://localhost:3000 | Main console (full stack) |
| http://localhost:8180/auth | Keycloak admin panel |
| http://localhost:8001 | Audit API directly |
| http://localhost:8090 | Fleet API directly (debug) |
| https://localhost:3000/fleet/ | Fleet API via ingress |

> The TLS certificate is self-signed — click through the browser warning on first visit.

---

## 3. Frontend Development (Hot-Reload)

For active frontend work, run the Vite dev server locally instead of using the pre-built image:

```bash
cd frontend/console-app
pnpm dev
```

Open: **http://localhost:5173**

All API calls (`/iam`, `/v1`, `/audit`, `/fleet`, `/app`) are automatically proxied to `https://localhost:3000` (the Docker ingress). The backend stack must be running.

> `VITE_PROXY_TARGET` in `frontend/console-app/.env.local` controls the proxy destination.

---

## 4. Common Commands

All managed via `dev.sh` in the project root:

```bash
./dev.sh up                  # Start all backend services
./dev.sh up-guardrails       # Start backend services + guardrails (sidecar + GLiNER detector)
./dev.sh guardrails          # Start/rebuild only the guardrail containers
./dev.sh guardrails --no-build   # Same, but skip image builds — use when offline (see §7)
./dev.sh down                # Stop all services
./dev.sh status              # Show container health
./dev.sh logs                # Follow all logs
./dev.sh logs gateway        # Follow a specific service log
./dev.sh restart iam         # Restart a specific service
./dev.sh clean               # Remove stopped containers + dangling images
./dev.sh fix-db              # Fix SQLite readonly error (see Troubleshooting)
```

---

## 5. Which Compose File to Use

The project has many `docker-compose.*.yml` files for different deployment scenarios. For local development, only these three matter:

| File | Role |
|------|------|
| `docker-compose.mvp.yml` | Core services (gateway, IAM, keycloak, console, scheduler) |
| `docker-compose.mvp-audit.yml` | Overlay: adds PostgreSQL + Audit API |
| `docker-compose.mvp-fleet.yml` | Overlay: adds Fleet API (built from local source) |
| `docker-compose.guardrails-local.yml` | Overlay used by `dev.sh` guardrails commands: builds `xparse-guardrails:dev` locally + re-tags the detector image |

`xparse-guardrails` and `xparse-gliner` are both already defined in
`docker-compose.mvp.yml`, behind the `guardrails` profile (pointing at private ECR
images). `dev.sh up-guardrails` and `dev.sh guardrails` add
`docker-compose.guardrails-local.yml` so local runs build the **sidecar** from
source and point the **detector** at a locally built tag instead of pulling from
ECR.

**Do not use** the other files locally:

| File pattern | Purpose |
|-------------|---------|
| `*.pro.*` | Full production stack (includes Fleet, Registry, Observability) |
| `*.enterprise.*` | Enterprise/AWS deployment |
| `*.fleet.*` | Fleet node management tier |
| `*.cloud.*` | Cloud deployment |
| `install_service/tiers/*` | Used by the xdeploy installer, not for manual dev |

---

## 6. First-Time Setup Notes

The `XPARSE_BOOTSTRAP_ADMIN_KEY` in `.env` is used on first startup to create the initial admin tenant and API key (migration 0012). It only applies once — if you reset the database, the same key can be used again.

To reset the IAM database:
```bash
./dev.sh down
docker volume rm xparse_xparse-data
./dev.sh up
```

To reset the Audit database:
```bash
./dev.sh down
docker volume rm xparse_xparse-pg-data
./dev.sh up
```

---

## 7. Troubleshooting

### ❌ 重啟後 IAM 出現 500，log 顯示 `attempt to write a readonly database`

**原因**：SQLite 資料庫檔案是由不同 UID 建立的，目前的 container user 沒有寫入權限。

**修復**：
```bash
./dev.sh fix-db
docker restart xparse-iam
```

或手動執行：
```bash
docker run --rm -v xparse_xparse-data:/data alpine \
  chmod 666 /data/xparse_iam.db /data/xparse_iam.db-shm /data/xparse_iam.db-wal
docker restart xparse-iam
```

---

### ❌ Docker Desktop 的 Start 按鈕出現 `could not find audit-db-init: not found`

**原因**：Docker Desktop 的 Start 按鈕執行的是 `docker compose start`，它只能啟動已存在的 container。`audit-db-init` 是一次性 init container，跑完就消失，所以找不到。

**修復**：不要用 Docker Desktop Start 按鈕。永遠用：
```bash
./dev.sh up
```

---

### ❌ 離線／Docker Hub 連不上時 `./dev.sh up*` 直接 build 失敗

症狀（即使所有 layer 都 `CACHED`）：

```
ERROR [internal] load metadata for docker.io/library/python:3.12-slim
failed to authorize: ... dial tcp: lookup auth.docker.io: i/o timeout
```

**原因**：BuildKit 每次 build 都會重新向 registry 解析 base image 的 manifest
（`FROM python:3.12-slim`），這一步不吃本機 layer cache。網路不通就 build 不了，
而 `dev.sh` 是 `set -e`，build 失敗就整個中止——連 `up` 都沒跑到。
**已在跑的容器不受影響**，這只是啟動指令中止。

**修復**：加 `--no-build`，直接用本機既有 image 起容器（不碰網路）：

```bash
./dev.sh guardrails --no-build
./dev.sh up --no-build
```

⚠️ sidecar 是在 build 時 `COPY xparse_guardrail/` 進 image 的，所以 `--no-build`
期間**本機的 guardrail 原始碼改動不會進到容器**（gateway 與 IAM 不受影響，它們是
mount `./xparse_guardrail:ro`，重啟即生效）。網路恢復後記得重跑一次不帶 flag 的指令。

---

### ❌ 所有 chat 請求 500 `routing_resolver not initialized — check XPARSE_ROUTING_DB_URL`

症狀：`POST /v1/chat/completions` 一律 500，但 gateway 的 healthcheck 是 healthy：

```
{"detail":"routing_resolver not initialized — check XPARSE_ROUTING_DB_URL"}
```

**原因不是那個環境變數。** `XPARSE_ROUTING_DB_URL` 有預設值
（`sqlite:////var/lib/xparse/routing.db`），沒設本來就能跑；訊息指向它是誤導。
真因在啟動 log 裡：

```bash
docker logs xparse-gateway 2>&1 | grep -A6 "Routing module not initialized"
# TypeError: Resolver.__init__() missing 1 required positional argument: 'config_repo'
```

這是 **mount skew**：`./bustream` 有 mount（caller `bustream/gateway/app.py` 來自工作樹），
但 `xparse_routing` 曾經**沒有** mount（callee 來自 image 內建的舊副本）。
ADR-088 Rev.4（`f393f76c5`，2026-07-24）移除了 `Resolver` 的 `config_repo` 參數並同步改了
caller，於是舊 callee 在啟動時炸 `TypeError` → 被 `except Exception` 降級成 warning →
gateway 照樣 healthy → 每個 chat 請求變成那句誤導的 500。

**修復**：`docker-compose.dev-mvp.yml` 的 gateway 已加上 `./xparse_routing:/app/xparse_routing:ro`。
compose 改動要**重建容器**才生效，光 `restart` 沒用：

```bash
./dev.sh up            # 或：docker compose -f docker-compose.mvp.yml -f docker-compose.mvp-audit.yml \
                       #        -f docker-compose.mvp-fleet.yml up -d xparse-gateway
docker logs xparse-gateway 2>&1 | grep -c "not initialized"   # 應為 0
```

> **通則 — 哪些是「活的」、哪些來自 image**：gateway 目前 live-mount
> `bustream` / `xparse_routing` / `xparse_guardrail`；IAM live-mount
> `xparse_iam/xparse_iam` / `xparse_guardrail`。其餘一律取自 image
> （image 可能比工作樹舊好幾個月），改了要重建 image 或另加 mount。
> gateway 仍會 import 三個**沒被 mount** 的套件——`xparse_resource_manager`、
> `audit`(3rd/xparse_audit)、`xparse_iam`——所以看到來自這些套件的
> `TypeError` / `AttributeError` / 參數不合，先懷疑同一種 skew，別先查設定。

---

### ⚠️ `xparse-fleet` 建置時間較長（首次 `./dev.sh up`）

**原因**：Fleet 是從本機原始碼建置（`xparse_fleet/fleet/Dockerfile`），首次執行需要下載 `python:3.12-slim` 基礎 image 並安裝 Python 依賴。

**後續啟動**：Docker 會快取 image layer，不再重新安裝，啟動速度與其他服務相同。

若要只重建 fleet image：
```bash
docker compose -f docker-compose.mvp.yml -f docker-compose.mvp-audit.yml -f docker-compose.mvp-fleet.yml build xparse-fleet
```

---

## 8. Disk Space

Docker images and build cache can accumulate. To reclaim space:

```bash
# Safe — removes only build cache (~15 GB)
docker builder prune -f

# Removes all unused images (~37 GB, need to re-pull to use again)
docker image prune -a

# Removes unused volumes (check first)
docker volume prune
```
