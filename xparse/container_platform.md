# xparse_container_platform — 技術報告

> **生成日期**：2026-05-29
> **來源路徑**：`xparse_container_platform/`
> **關聯文件**：ADR-093、ADR-102、ADR-103、ADR-136、ADR-140、RCA-005

---

## 1. 是什麼應用

| 屬性 | 內容 |
|------|------|
| **類型** | Library（Python package，非獨立 HTTP 服務） |
| **架構模式** | Clean Architecture（Hexagonal / Ports & Adapters） |
| **協議** | 不對外暴露 HTTP；內部透過 Unix socket 連接 Docker Engine（aiodocker）；透過 subprocess 呼叫 nsjail |
| **面向對象** | 由 `xparse_node_mgr`（Node Runtime Agent）引入，提供容器與網路的生命週期管理能力 |
| **部署方式** | 作為 Python package 被 import；不需獨立容器或程序；由呼叫方（xparse_node_mgr）決定部署形態 |
| **主要職責** | Sandbox 容器的完整生命週期（create / start / stop / destroy / exec）+ Docker network 的建立與隔離管理 |
| **安全約束** | ADR-103 硬性規定：無 privileged 容器；預設 cap_drop=ALL、read-only rootfs、no-new-privileges；支援 per-execution nsjail 二次沙箱 |

---

## 2. 資料夾結構總覽

```
xparse_container_platform/                    # 套件根目錄（177 行）— 公開 API export 與版本說明
├── __init__.py                               # 公開 API：所有 use case、protocol、DTO、entity 的 re-export
│
├── interface/
│   ├── __init__.py                           # 空
│   └── container.py                          # 90 行 — 依賴注入容器，工廠函式 wire 所有相依
│
├── application/
│   ├── __init__.py                           # 空
│   ├── dto/
│   │   ├── __init__.py                       # 空
│   │   ├── sandbox_dto.py                    # 78 行 — CreateSandboxRequest、ExecRequest、SandboxDTO、ExecResultDTO
│   │   └── network_dto.py                    # 32 行 — CreateNetworkRequest、NetworkDTO
│   │
│   ├── protocols/                            # Ports（介面定義）
│   │   ├── __init__.py                       # 空
│   │   ├── container_runtime.py              # 64 行 — ContainerRuntime protocol（7 個非同步方法）
│   │   ├── network_runtime.py                # 62 行 — NetworkRuntime protocol（8 個非同步方法）
│   │   ├── sandbox_store.py                  # 35 行 — SandboxStore protocol（5 個非同步方法）
│   │   ├── network_store.py                  # 47 行 — NetworkStore protocol（5 個非同步方法）
│   │   └── execution_sandbox.py              # 35 行 — ExecutionSandbox protocol（wrap 命令包裝）
│   │
│   └── use_cases/
│       ├── __init__.py                       # 空
│       ├── create_sandbox.py                 # 120 行 — 建立並啟動 sandbox 容器
│       ├── start_sandbox.py                  # 101 行 — 重啟已停止的 sandbox（ADR-140）
│       ├── stop_sandbox.py                   # 91 行 — 優雅停止（保留 volumes）（ADR-140）
│       ├── destroy_sandbox.py                # 76 行 — 停止並移除容器與持久化記錄
│       ├── exec_in_sandbox.py                # 63 行 — 在 sandbox 內執行命令（可選 nsjail 包裝）
│       ├── get_sandbox_status.py             # 50 行 — 同步容器實際狀態並回傳 DTO
│       ├── list_sandboxes.py                 # 22 行 — 列出 sandbox（可依 tenant 過濾）
│       ├── create_network.py                 # 77 行 — 建立 Docker network + 套用 iptables 規則
│       ├── remove_network.py                 # 29 行 — 移除 Docker network
│       └── list_networks.py                  # 34 行 — 列出 Docker networks（可依 label 過濾）
│
├── domain/
│   ├── __init__.py                           # 空
│   ├── exceptions.py                         # 69 行 — 完整例外階層（5 個語意例外類別）
│   ├── entities/
│   │   ├── __init__.py                       # 3 行
│   │   └── sandbox.py                        # 90 行 — Sandbox entity + 狀態機（state machine）
│   │
│   └── value_objects/
│       ├── __init__.py                       # 6 行
│       ├── enums.py                          # 38 行 — SandboxState、NetworkZone 枚舉
│       ├── container_config.py               # 62 行 — ContainerConfig（凍結 dataclass）+ ProxyConfig（ADR-136）
│       ├── container_info.py                 # 28 行 — ContainerInfo、ExecResult（不可變快照）
│       ├── container_stats.py                # 25 行 — ContainerStats（資源使用快照）
│       ├── network_config.py                 # 41 行 — NetworkRule、NetworkConfig（不可變）
│       └── network_info.py                   # 23 行 — NetworkInfo（網路狀態快照）
│
├── infrastructure/
│   ├── __init__.py                           # 空
│   ├── runtime/
│   │   ├── __init__.py                       # 空
│   │   └── docker_runtime.py                 # 587 行 — DockerRuntime（最大檔案，aiodocker 完整實作）
│   │
│   ├── sandbox/
│   │   ├── __init__.py                       # 1 行
│   │   └── nsjail_sandbox.py                 # 135 行 — NsjailSandbox（Google nsjail per-execution 沙箱）
│   │
│   └── store/
│       ├── __init__.py                       # 空
│       ├── in_memory_store.py                # 43 行 — InMemoryStore（MVP dict-backed SandboxStore）
│       └── in_memory_network_store.py        # 44 行 — InMemoryNetworkStore（MVP dict-backed NetworkStore）
│
└── tests/
    ├── __init__.py                           # 空
    ├── test_domain.py                        # 279 行 — domain entity 狀態機與例外測試
    ├── test_use_cases.py                     # 539 行 — use case（MockRuntime + InMemoryStore）
    ├── test_network_domain.py                # 113 行 — 網路 value object 測試
    ├── test_network_use_cases.py             # 257 行 — 網路 use case 測試
    ├── test_integration_network.py           # 346 行 — 網路整合測試
    └── test_nsjail_sandbox.py                # 381 行 — nsjail 包裝測試
```

---

## 3. 各模組功能說明

### 3.1 Domain 層

| 模組 | 職責 | 關聯文件 |
|------|------|---------|
| `domain/entities/sandbox.py` | Sandbox 實體，持有狀態機轉換邏輯；驗證 state transition 合法性；更新 `updated_at` | ADR-093（invariant #1 原子性）|
| `domain/exceptions.py` | 語意例外階層：`SandboxNotFoundError`、`InvalidStateTransitionError`、`SandboxNotRunningError`、`ContainerRuntimeError`、`PrivilegeEscalationError` | ADR-093、ADR-103 |
| `domain/value_objects/enums.py` | `SandboxState`（5 態）、`NetworkZone`（DMZ / PRIVATE / INTERNAL）| — |
| `domain/value_objects/container_config.py` | `ContainerConfig` 凍結 dataclass：所有容器安全參數的單一真相來源；`ProxyConfig`：nginx sidecar 設定 | ADR-103、ADR-136 |
| `domain/value_objects/container_info.py` | `ContainerInfo`（runtime 快照）、`ExecResult`（命令執行結果） | — |
| `domain/value_objects/container_stats.py` | `ContainerStats`：CPU/memory/pids 資源用量快照 | — |
| `domain/value_objects/network_config.py` | `NetworkRule`（防火牆規則）、`NetworkConfig`（不可變網路設定）| — |
| `domain/value_objects/network_info.py` | `NetworkInfo`：網路 runtime 狀態快照 | — |

### 3.2 Application 層（Use Cases）

| Use Case | 主要流程 | 關聯文件 |
|----------|----------|---------|
| `CreateSandbox` | 建構 `ContainerConfig` → 建立容器 → 啟動容器 → 驗證狀態 → 持久化 | ADR-093、ADR-102 M3/M4、ADR-103 |
| `StartSandbox` | 取得 sandbox → 啟動容器（保留既有 container_id）→ 驗證後設為 RUNNING | ADR-140、ADR-093 |
| `StopSandbox` | 取得 sandbox → 停止容器（不移除）→ 設為 STOPPED | ADR-140 |
| `DestroySandbox` | 停止 → 移除容器 → 設為 DESTROYED → 從 store 刪除 | ADR-093 |
| `ExecInSandbox` | 驗證 RUNNING → 可選 nsjail 包裝 → exec → 回傳結果 | ADR-103 Rev.2（nsjail Track A3） |
| `GetSandboxStatus` | 取得 sandbox → 若 RUNNING 則同步 runtime 狀態 → 若有差異則更新 store | ADR-093 invariant #3 |
| `ListSandboxes` | 查詢 store（可依 tenant 過濾） | — |
| `CreateNetwork` | 建構 `NetworkConfig` → 建立 Docker network → 套用 iptables 規則 → 持久化 | — |
| `RemoveNetwork` | 移除 Docker network → 從 store 刪除 | — |
| `ListNetworks` | 直接查詢 runtime（Docker 為 source of truth）| — |

### 3.3 Application 層（Protocols / Ports）

| Protocol | 方法數 | 用途 |
|----------|--------|------|
| `ContainerRuntime` | 8 | 容器 CRUD + exec + stats |
| `NetworkRuntime` | 7 | 網路 CRUD + container attach |
| `SandboxStore` | 5 | sandbox 持久化（save / get / get_by_tenant / delete / list_all）|
| `NetworkStore` | 5 | network 設定持久化 |
| `ExecutionSandbox` | 1 | 命令包裝（`wrap(command, language)`） |

### 3.4 Infrastructure 層（Adapters）

| Adapter | 實作 Protocol | 說明 |
|---------|-------------|------|
| `DockerRuntime` | `ContainerRuntime` + `NetworkRuntime` | aiodocker 非同步 Docker Engine client；Lazy init；hard-coded `Privileged: False`（第 49 行） |
| `NsjailSandbox` | `ExecutionSandbox` | Google nsjail subprocess 包裝；每次 exec 建立獨立 namespace |
| `InMemoryStore` | `SandboxStore` | Dict-backed MVP；非 thread-safe；deep copy 防 aliasing |
| `InMemoryNetworkStore` | `NetworkStore` | Dict-backed MVP；非 thread-safe；deep copy 防 aliasing |

### 3.5 Interface 層

| 模組 | 職責 |
|------|------|
| `interface/container.py` | 依賴注入容器：工廠函式組裝所有 use case 所需的 runtime、store 實例 |

---

## 4. 對外 API 端點完整列表

**`xparse_container_platform` 是純 Library，不暴露任何 HTTP 端點。**

本模組提供 Python 公開 API，由 `xparse_node_mgr` 等上層服務引入後封裝成 HTTP 端點。
公開 API 入口為 `xparse_container_platform/__init__.py`：

```python
from xparse_container_platform import (
    # Sandbox use cases
    CreateSandbox, StartSandbox, StopSandbox,
    DestroySandbox, ExecInSandbox, GetSandboxStatus, ListSandboxes,
    # Network use cases
    CreateNetwork, RemoveNetwork, ListNetworks,
    # Protocols (Ports)
    ContainerRuntime, NetworkRuntime, SandboxStore, NetworkStore, ExecutionSandbox,
    # DTOs
    CreateSandboxRequest, ExecRequest, SandboxDTO, ExecResultDTO,
    CreateNetworkRequest, NetworkDTO,
    # Domain entities & value objects
    Sandbox, SandboxState, ContainerConfig, ContainerInfo, ExecResult,
    # Exceptions
    SandboxNotFoundError, SandboxNotRunningError, ContainerRuntimeError,
    PrivilegeEscalationError, InvalidStateTransitionError,
    # Infrastructure adapters
    DockerRuntime, InMemoryStore, InMemoryNetworkStore, NsjailSandbox,
)
```

**依賴注入範例（`interface/container.py`）**：
```python
runtime = get_container_runtime(docker_url="unix:///var/run/docker.sock")
store   = get_sandbox_store()
uc      = get_create_sandbox(runtime, store)
dto     = await uc.execute(CreateSandboxRequest(...))
```

---

## 5. 服務通訊全貌

### 5.1 ASCII 架構圖

```
┌─────────────────────────────────────────────────────────────────────┐
│                         xparse_node_mgr                             │
│                    （HTTP REST API，對外 caller）                     │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ Python import（library call）
                            │
              ┌─────────────▼──────────────────────────┐
              │       xparse_container_platform         │
              │  ┌──────────┐  ┌──────────────────────┐ │
              │  │ Use Cases│  │  Domain (entities,    │ │
              │  │  (10 UC) │  │  value objects,       │ │
              │  └─────┬────┘  │  exceptions)          │ │
              │        │       └──────────────────────┘ │
              │   ┌────▼────────────────────────────┐   │
              │   │         Protocols (Ports)        │   │
              │   └────┬──────────────┬─────────────┘   │
              └────────┼──────────────┼─────────────────┘
                       │              │
           ┌───────────▼───┐    ┌─────▼──────────────────┐
           │  DockerRuntime│    │  NsjailSandbox           │
           │  (aiodocker)  │    │  (subprocess)            │
           └───────┬───────┘    └──────────┬───────────────┘
                   │ Unix socket (HTTP/1.1)  │ fork/exec
                   │                        │
    ┌──────────────▼──────┐   ┌────────────▼────────────┐
    │   Docker Engine     │   │  nsjail binary           │
    │  /var/run/docker.sock│  │  /usr/local/bin/nsjail   │
    │   (Container mgmt) │   │  (namespace isolation)    │
    └─────────────────────┘   └─────────────────────────-┘

    ┌──────────────────────────────────────────────────────┐
    │               InMemoryStore / InMemoryNetworkStore    │
    │              （in-process dict，MVP，無外部通訊）      │
    └──────────────────────────────────────────────────────┘
```

### 5.2 通訊連結總表

| 對象 | 類型 | 協議 | 方向 | 發起點檔案 | 失敗行為 |
|------|------|------|------|-----------|---------|
| Docker Engine | Backend | HTTP/1.1 over Unix socket | 出向（xparse → Docker） | `infrastructure/runtime/docker_runtime.py` | Fail-fast：`ContainerRuntimeError`（含 operation + detail）|
| nsjail binary | Backend | subprocess（fork/exec） | 出向（runtime → binary） | `infrastructure/sandbox/nsjail_sandbox.py` | Fail-fast：`SandboxNotRunningError` 或 non-zero exit code 透傳 |
| InMemoryStore | Backend | in-process Python call | 雙向 | `infrastructure/store/in_memory_store.py` | `SandboxNotFoundError`（get 失敗時）|
| InMemoryNetworkStore | Backend | in-process Python call | 雙向 | `infrastructure/store/in_memory_network_store.py` | `KeyError` 包裝為 None（get 失敗）|
| iptables（透過 Docker network hook） | Backend | subprocess（via docker_runtime.apply_rules） | 出向 | `infrastructure/runtime/docker_runtime.py::apply_rules` | Fail-fast：`ContainerRuntimeError` |

### 5.3 各連線詳細說明

---

#### 連線 A：DockerRuntime → Docker Engine

**協議**：HTTP/1.1 over Unix socket（aiodocker）

**Socket 路徑**：
- 預設：`aiodocker` 內建預設（通常為 `unix:///var/run/docker.sock`）
- 可覆蓋：`DockerRuntime(docker_url="unix:///var/run/docker.sock")` 或 `tcp://host:port`

**發起點**：`infrastructure/runtime/docker_runtime.py:28`（`__init__`）、`:32`（`_get_client`，lazy-init）

**操作一覽**：

| 操作 | Docker API endpoint | 說明 |
|------|---------------------|------|
| 建立容器 | `POST /containers/create` | 含所有安全參數 |
| 啟動容器 | `POST /containers/{id}/start` | |
| 停止容器 | `POST /containers/{id}/stop?t=10` | timeout=10s（可覆蓋）|
| 移除容器 | `DELETE /containers/{id}?force={bool}` | |
| Exec（命令） | `POST /containers/{id}/exec` + `POST /exec/{id}/start` | 流式 stdout/stderr |
| 查詢狀態 | `GET /containers/{id}/json` | inspect |
| 查詢資源 | `GET /containers/{id}/stats?stream=false` | CPU/memory/pids |
| 批次資源 | `GET /containers/json?filters=…` + stats | 依 labels 過濾 |
| 建立網路 | `POST /networks/create` | IPAM config |
| 查詢網路 | `GET /networks/{id}` | |
| 移除網路 | `DELETE /networks/{id}` | |
| 列出網路 | `GET /networks?filters=…` | |
| Connect container | `POST /networks/{id}/connect` | attach 容器到網路 |
| Disconnect container | `POST /networks/{id}/disconnect` | detach |
| 查詢 image entrypoint | `GET /images/{name}/json` | 取得 ENTRYPOINT |
| Pull image | `POST /images/create?fromImage=…` | 串流進度 |

**Request 範例（建立容器）**：
```json
POST /containers/create?name=sandbox-abc123
{
  "Image": "python:3.11-slim",
  "Labels": {"tenant_id": "tenant-001"},
  "Env": ["LANG=C.UTF-8"],
  "Cmd": ["python3", "-c", "print('hello')"],
  "HostConfig": {
    "Privileged": false,
    "CapDrop": ["ALL"],
    "ReadonlyRootfs": true,
    "SecurityOpt": ["no-new-privileges"],
    "PidsLimit": 256,
    "Memory": 536870912,
    "CpuQuota": 100000,
    "NetworkMode": "none"
  }
}
```

**Response 範例（建立容器）**：
```json
{
  "Id": "a1b2c3d4e5f6...",
  "Warnings": []
}
```

**Timeout 設定**：
- `stop_container`：預設 `t=10`（秒），可透過 `StopSandbox` use case 傳入覆蓋
- aiodocker 本身：無明確 request timeout（由呼叫方 event loop 控制）

**失敗行為**：
- `aiodocker.exceptions.DockerError` → `ContainerRuntimeError(operation=..., detail=...)`（fail-fast，含 operation 名稱與 Docker 原始訊息）
- Image 不存在（404）→ auto-pull → 若 pull 失敗則 `ContainerRuntimeError`（`docker_runtime.py:124-148`）
- Container 建立後 start 失敗 → `sandbox.mark_error(...)` → store 持久化 ERROR 狀態（`create_sandbox.py`）

**程式碼位置**：
- Lazy init：`docker_runtime.py:32-36`
- `create_container`：`docker_runtime.py:44-152`
- `start_container`：`docker_runtime.py:178-189`
- `stop_container`：`docker_runtime.py:191-201`（timeout=10）
- `exec_in_container`：`docker_runtime.py:~220-260`
- `get_container_status`：`docker_runtime.py:~270-320`
- `get_container_stats`：`docker_runtime.py:~330-380`
- `create_network`：`docker_runtime.py:~400-450`
- `apply_rules`（iptables）：`docker_runtime.py:~460-530`

---

#### 連線 B：NsjailSandbox → nsjail binary

**協議**：subprocess（`asyncio.create_subprocess_exec` 或 `subprocess.run`）

**Binary 路徑**：
- 預設：`/usr/local/bin/nsjail`（可透過建構子 `nsjail_bin` 覆蓋）

**Config 路徑**：
- 預設：`/etc/nsjail/`（可透過建構子 `config_dir` 覆蓋）
- 語言對應：`python-sandbox.cfg`、`bash-sandbox.cfg` 等

**發起點**：`infrastructure/sandbox/nsjail_sandbox.py:wrap()`

**命令包裝格式**：
```
原始命令：["python3", "-c", "print('hello')"]

包裝後：
[
  "/usr/local/bin/nsjail",
  "--config", "/etc/nsjail/python-sandbox.cfg",
  "--seccomp_policy", "/etc/nsjail/python-seccomp.policy",  # 若存在
  "--time_limit", "30",                                       # 若設定
  "--",
  "python3", "-c", "print('hello')"
]
```

**語言偵測對照表**：

| binary basename | language |
|-----------------|---------|
| `python3` / `python` | `python` |
| `node` / `nodejs` | `nodejs` |
| `bash` / `sh` | `bash` |

**外部容器需求**（ADR-103 Rev.2 Track A3）：
- 外層容器必須具備 `CAP_SYS_ADMIN`
- seccomp profile：`unconfined`
- AppArmor profile：`unconfined`

**失敗行為**：
- nsjail binary 不存在：直接傳播 `FileNotFoundError`（fail-fast）
- 非零 exit code：透過 `ExecResultDTO` 回傳（`exit_code ≠ 0`），不拋例外

**程式碼位置**：`infrastructure/sandbox/nsjail_sandbox.py:wrap()`（約 60-120 行）

---

#### 連線 C：Use Cases → InMemoryStore / InMemoryNetworkStore

**協議**：in-process Python 方法呼叫

**資料結構**：
- `InMemoryStore`：`Dict[str, Sandbox]`（sandbox_id → Sandbox）
- `InMemoryNetworkStore`：`Dict[str, NetworkConfig]`（network_id → NetworkConfig）

**Deep copy 保證**：save/get 均 deep copy，防止外部修改影響 store 內部狀態（`in_memory_store.py:~20-40`）

**Thread safety**：**不具備**（MVP；生產環境需替換為 DB-backed store）

**失敗行為**：
- `get(sandbox_id)` 找不到 → `SandboxNotFoundError(sandbox_id=...)`（fail-fast）
- `get_by_name` 找不到 → 回傳 `None`（fail-open，由呼叫方決定）

---

## 6. 請求主流程

### 6.1 Sandbox 建立流程

```
Caller（xparse_node_mgr）
    │
    │  CreateSandboxRequest(tenant_id, image, name, memory_limit, ...)
    ▼
CreateSandbox.execute()                          [create_sandbox.py:execute()]
    │
    ├─① 建構 ContainerConfig（套用安全預設值）
    │      cap_drop=ALL, read_only_rootfs=True,
    │      no_new_privileges=True, pids_limit=256
    │
    ├─② 建立 Sandbox entity（state=CREATING）
    │      sandbox_id = Fleet 提供的 id 或 uuid4()（ADR-102 M4）
    │
    ├─③ store.save(sandbox)                     [in_memory_store.py:save()]
    │      持久化 CREATING 狀態
    │
    ├─④ runtime.create_container(config)        [docker_runtime.py:create_container()]
    │      ├─ POST /containers/create（含安全 HostConfig）
    │      └─ 若 Image 404：auto-pull → retry create
    │
    ├─⑤ runtime.start_container(container_id)  [docker_runtime.py:start_container()]
    │      POST /containers/{id}/start
    │
    ├─⑥ runtime.get_container_status(container_id)  [docker_runtime.py:get_container_status()]
    │      GET /containers/{id}/json（post-condition 驗證，ADR-093 invariant #3）
    │
    ├─⑦ sandbox.mark_running(container_info)   [sandbox.py:mark_running()]
    │      state: CREATING → RUNNING
    │
    ├─⑧ store.save(sandbox)                     [in_memory_store.py:save()]
    │      持久化 RUNNING 狀態
    │
    └─⑨ return SandboxDTO(state=RUNNING, ...)

    ▼（若 ④⑤⑥ 任一失敗）
    sandbox.mark_error(message) → store.save() → raise ContainerRuntimeError
```

### 6.2 命令執行流程

```
Caller
    │
    │  ExecRequest(sandbox_id, command=["python3", "-c", "..."],
    │              sandboxed=True, language="python")
    ▼
ExecInSandbox.execute()                         [exec_in_sandbox.py:execute()]
    │
    ├─① store.get(sandbox_id)                  [in_memory_store.py:get()]
    │
    ├─② sandbox.require_running()              [sandbox.py:require_running()]
    │      assert state == RUNNING
    │
    ├─③（若 sandboxed=True 且 execution_sandbox 已注入）
    │      execution_sandbox.wrap(command, language)  [nsjail_sandbox.py:wrap()]
    │      command → nsjail 包裝 argv
    │
    ├─④ runtime.exec_in_container(container_id, command)
    │      [docker_runtime.py:exec_in_container()]
    │      POST /containers/{id}/exec + POST /exec/{id}/start
    │      串流 stdout/stderr
    │
    └─⑤ return ExecResultDTO(exit_code, stdout, stderr)
```

### 6.3 Network 建立流程

```
Caller
    │
    │  CreateNetworkRequest(name, zone=PRIVATE, subnet, gateway,
    │                       ingress_rules=[...], egress_rules=[...])
    ▼
CreateNetwork.execute()                         [create_network.py:execute()]
    │
    ├─① 建構 NetworkConfig（含 NetworkRule 列表）
    │
    ├─② runtime.create_network(config)         [docker_runtime.py:create_network()]
    │      POST /networks/create（含 IPAM config）
    │      zone=INTERNAL → internal=True flag
    │
    ├─③ runtime.apply_rules(network_id, config) [docker_runtime.py:apply_rules()]
    │      依 zone 套用 iptables FORWARD chain 規則：
    │      INTERNAL  → no-op（Docker 自行處理）
    │      PRIVATE   → INSERT DROP → 依規則 INSERT ACCEPT
    │      DMZ       → ACCEPT by default，依規則限制
    │
    ├─④ store.save(network_id, config)         [in_memory_network_store.py:save()]
    │      持久化 NetworkConfig（重啟恢復用）
    │
    └─⑤ return NetworkDTO(network_id, name, zone, ...)
```

---

## 7. 關鍵類別索引

| 類別名稱 | 檔案 | 職責 |
|---------|------|------|
| `Sandbox` | `domain/entities/sandbox.py` | Sandbox 實體，狀態機，唯一可變 entity |
| `SandboxState` | `domain/value_objects/enums.py` | CREATING / RUNNING / STOPPED / DESTROYED / ERROR |
| `NetworkZone` | `domain/value_objects/enums.py` | DMZ / PRIVATE / INTERNAL 網路隔離層級 |
| `ContainerConfig` | `domain/value_objects/container_config.py` | 凍結 dataclass，container 建立的全部參數（含安全預設）|
| `ProxyConfig` | `domain/value_objects/container_config.py` | nginx sidecar 設定（ADR-136） |
| `ContainerInfo` | `domain/value_objects/container_info.py` | 凍結快照：container_id、status、ip_address、ports |
| `ExecResult` | `domain/value_objects/container_info.py` | 凍結：exit_code、stdout、stderr |
| `ContainerStats` | `domain/value_objects/container_stats.py` | 凍結：cpu_percent、memory_usage、pids |
| `NetworkConfig` | `domain/value_objects/network_config.py` | 凍結：name、zone、subnet、rules |
| `NetworkRule` | `domain/value_objects/network_config.py` | 凍結：direction、src/dst cidr、port、protocol |
| `SandboxNotFoundError` | `domain/exceptions.py` | sandbox_id 查找失敗 |
| `InvalidStateTransitionError` | `domain/exceptions.py` | 不合法狀態轉換 |
| `SandboxNotRunningError` | `domain/exceptions.py` | 操作要求 RUNNING 但不在 RUNNING 態 |
| `ContainerRuntimeError` | `domain/exceptions.py` | Docker Engine 操作失敗（含 operation + detail）|
| `PrivilegeEscalationError` | `domain/exceptions.py` | 試圖啟用 privileged 容器（ADR-103）|
| `ContainerRuntime` | `application/protocols/container_runtime.py` | Protocol（Port）：容器 8 方法非同步介面 |
| `NetworkRuntime` | `application/protocols/network_runtime.py` | Protocol（Port）：網路 7 方法非同步介面 |
| `SandboxStore` | `application/protocols/sandbox_store.py` | Protocol（Port）：5 方法持久化介面 |
| `NetworkStore` | `application/protocols/network_store.py` | Protocol（Port）：5 方法持久化介面 |
| `ExecutionSandbox` | `application/protocols/execution_sandbox.py` | Protocol（Port）：`wrap(command, language)` 介面 |
| `CreateSandbox` | `application/use_cases/create_sandbox.py` | 建立 + 啟動 sandbox（最複雜 UC） |
| `StartSandbox` | `application/use_cases/start_sandbox.py` | 重啟已停止 sandbox（ADR-140） |
| `StopSandbox` | `application/use_cases/stop_sandbox.py` | 優雅停止，保留 volumes（ADR-140） |
| `DestroySandbox` | `application/use_cases/destroy_sandbox.py` | 停止 + 移除 + 刪除持久化 |
| `ExecInSandbox` | `application/use_cases/exec_in_sandbox.py` | 在 sandbox 執行命令（可選 nsjail）|
| `GetSandboxStatus` | `application/use_cases/get_sandbox_status.py` | 同步 runtime 狀態（ADR-093 invariant #3）|
| `ListSandboxes` | `application/use_cases/list_sandboxes.py` | 列出（可依 tenant 過濾）|
| `CreateNetwork` | `application/use_cases/create_network.py` | 建立 Docker network + iptables 規則 |
| `RemoveNetwork` | `application/use_cases/remove_network.py` | 移除 network |
| `ListNetworks` | `application/use_cases/list_networks.py` | 列出 network（直接查 runtime）|
| `DockerRuntime` | `infrastructure/runtime/docker_runtime.py` | aiodocker 完整 adapter（最大類別，587 行）|
| `NsjailSandbox` | `infrastructure/sandbox/nsjail_sandbox.py` | nsjail subprocess 包裝 |
| `InMemoryStore` | `infrastructure/store/in_memory_store.py` | MVP dict-backed SandboxStore（非 thread-safe）|
| `InMemoryNetworkStore` | `infrastructure/store/in_memory_network_store.py` | MVP dict-backed NetworkStore（非 thread-safe）|
| `CreateSandboxRequest` | `application/dto/sandbox_dto.py` | 呼叫方輸入 DTO |
| `ExecRequest` | `application/dto/sandbox_dto.py` | 執行命令輸入 DTO |
| `SandboxDTO` | `application/dto/sandbox_dto.py` | 回傳給呼叫方的 Sandbox 快照 |
| `ExecResultDTO` | `application/dto/sandbox_dto.py` | 命令執行結果 DTO |
| `CreateNetworkRequest` | `application/dto/network_dto.py` | 建立 network 輸入 DTO |
| `NetworkDTO` | `application/dto/network_dto.py` | 回傳給呼叫方的 network 快照 |

---

## 8. 重要環境變數

本模組**不使用** `os.environ` — 所有設定均透過 Python 建構子參數注入。以下列出等效的「設定點」及其預設值：

| 設定點（建構子參數） | 預設值 | 說明 | 傳入位置 |
|---------------------|--------|------|---------|
| `DockerRuntime(docker_url=...)` | `None`（aiodocker 預設：`unix:///var/run/docker.sock`） | Docker Engine 連接位址（Unix socket 或 tcp://host:port）| `docker_runtime.py:28` |
| `NsjailSandbox(nsjail_bin=...)` | `"/usr/local/bin/nsjail"` | nsjail binary 路徑 | `nsjail_sandbox.py:__init__` |
| `NsjailSandbox(config_dir=...)` | `"/etc/nsjail"` | nsjail 語言 .cfg 設定目錄 | `nsjail_sandbox.py:__init__` |
| `NsjailSandbox(time_limit=...)` | `None`（使用 .cfg 內設定）| 覆蓋 nsjail `--time_limit`（秒）| `nsjail_sandbox.py:__init__` |
| `NsjailSandbox(verbose=...)` | `False` | 啟用 nsjail verbose logging | `nsjail_sandbox.py:__init__` |
| `stop_container(timeout=...)` | `10`（秒）| Docker stop 等待時間 | `docker_runtime.py:191` |

**外層容器必備能力**（ADR-103 Rev.2 Track A3，若使用 NsjailSandbox）：

| 容器設定 | 必要值 | 說明 |
|---------|--------|------|
| `cap_add` | `CAP_SYS_ADMIN` | nsjail 建立 user namespace 所需 |
| seccomp profile | `unconfined` | nsjail 需要 clone syscall |
| AppArmor profile | `unconfined` | nsjail 需要完整 mount 能力 |

---

## 9. 關聯文件索引

### 9.1 ADR（架構決策記錄）

| ADR | 標題 | 相關範圍 |
|-----|------|---------|
| ADR-093 | Execution Safety Invariants | 5 個跨系統 invariant；直接影響所有 use case 的原子性、pre/post-condition 驗證、identity binding |
| ADR-102 M3 | Xparse Container Platform — Container Lifecycle Management Library | 本模組的架構定義文件 |
| ADR-102 M4 | Preserve Fleet-supplied sandbox identifier | `CreateSandboxRequest.sandbox_id` 的設計理由（identity binding stability）|
| ADR-103 | No Privileged Containers | hard-coded `Privileged: False`（`docker_runtime.py:49`）；`PrivilegeEscalationError` |
| ADR-103 Rev.2 | Track A3: Sandbox Executor | nsjail per-execution 隔離的外層容器需求（CAP_SYS_ADMIN、seccomp=unconfined）|
| ADR-136 | Per-deployment Sidecar Reverse Proxy | `ProxyConfig` dataclass；nginx sidecar 設定封裝 |
| ADR-140 | Idle-timeout Lifecycle: RUNNING → STOPPED → RUNNING | `StartSandbox` + `StopSandbox` use case 的設計根據；volumes 保留語意 |

### 9.2 RCA（根因分析）

| RCA | 相關範圍 |
|-----|---------|
| RCA-005 | DNS aliases 在 `create_container` 中的 `NetworkingConfig.EndpointsConfig.Aliases` 設定（`docker_runtime.py:107-117`）；解決 ingress 無法解析 UUID-named container 的問題 |

### 9.3 Core 整合導航層對照

| 領域 | 對應 Core 文件 | 關係說明 |
|------|---------------|---------|
| 08 Application Platform | `docs/adr/core/Core-ADR-08-*.md` | 本模組是 Agent App 容器生命週期的核心 library |
| 01 Gateway & Streaming | `docs/adr/core/Core-ADR-01-*.md` | 間接關聯：streaming 需要容器提供 LLM runtime |
| 07 Fleet Node Management | `docs/prd/core/Core-PRD-07-*.md` | Fleet 的 workload_id 透過 ADR-102 M4 流入本模組 |

---

## 10. 規模統計

### 10.1 各模組程式碼行數

| 模組 / 檔案 | 行數 | 類別 |
|------------|------|------|
| `infrastructure/runtime/docker_runtime.py` | 587 | Infrastructure（最大）|
| `tests/test_use_cases.py` | 539 | 測試 |
| `tests/test_nsjail_sandbox.py` | 381 | 測試 |
| `tests/test_integration_network.py` | 346 | 測試 |
| `tests/test_domain.py` | 279 | 測試 |
| `tests/test_network_use_cases.py` | 257 | 測試 |
| `__init__.py` | 177 | Public API |
| `tests/test_network_domain.py` | 113 | 測試 |
| `infrastructure/sandbox/nsjail_sandbox.py` | 135 | Infrastructure |
| `application/use_cases/create_sandbox.py` | 120 | Use Case |
| `application/use_cases/start_sandbox.py` | 101 | Use Case |
| `application/use_cases/stop_sandbox.py` | 91 | Use Case |
| `interface/container.py` | 90 | DI Container |
| `domain/entities/sandbox.py` | 90 | Domain Entity |
| `application/dto/sandbox_dto.py` | 78 | DTO |
| `application/use_cases/create_network.py` | 77 | Use Case |
| `application/use_cases/destroy_sandbox.py` | 76 | Use Case |
| `domain/exceptions.py` | 69 | Domain |
| `application/protocols/container_runtime.py` | 64 | Protocol |
| `application/use_cases/exec_in_sandbox.py` | 63 | Use Case |
| `domain/value_objects/container_config.py` | 62 | Value Object |
| `application/protocols/network_runtime.py` | 62 | Protocol |
| `application/use_cases/get_sandbox_status.py` | 50 | Use Case |
| `application/protocols/network_store.py` | 47 | Protocol |
| `infrastructure/store/in_memory_network_store.py` | 44 | Infrastructure |
| `infrastructure/store/in_memory_store.py` | 43 | Infrastructure |
| `domain/value_objects/network_config.py` | 41 | Value Object |
| `domain/value_objects/enums.py` | 38 | Value Object |
| `application/protocols/execution_sandbox.py` | 35 | Protocol |
| `application/protocols/sandbox_store.py` | 35 | Protocol |
| `application/use_cases/list_networks.py` | 34 | Use Case |
| `application/dto/network_dto.py` | 32 | DTO |
| `application/use_cases/remove_network.py` | 29 | Use Case |
| `domain/value_objects/container_info.py` | 28 | Value Object |
| `domain/value_objects/container_stats.py` | 25 | Value Object |
| `domain/value_objects/network_info.py` | 23 | Value Object |
| `application/use_cases/list_sandboxes.py` | 22 | Use Case |
| **全部合計** | **4,393** | |

### 10.2 層次分佈

| 層次 | 估計行數 | 占比 |
|------|---------|------|
| Tests | 1,915 | 43.6% |
| Infrastructure | 766 | 17.4% |
| Application（Use Cases + Protocols + DTOs） | 924 | 21.0% |
| Domain（Entities + Value Objects + Exceptions）| 341 | 7.8% |
| Public API + DI Container | 267 | 6.1% |
| `__init__` 空檔案 | 180（空）| 4.1% |

> 測試覆蓋比例達 **43.6%**（測試行數/總行數），顯示本模組高度重視測試紀律。
> 最大非測試檔案為 `DockerRuntime`（587 行），接近 §5 軟限制（300 行 class），未來可考慮拆分網路操作為獨立 `DockerNetworkRuntime`。
