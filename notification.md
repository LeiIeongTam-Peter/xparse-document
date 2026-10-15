# Xparse Notification 設計參考

> 狀態：設計討論彙整（對應 PRD-195 / ADR-249 / SPEC-192，PR #1478 — **目前為設計閉環，尚無實作碼**）
> 來源討論：[Discussion #737 Notifications & Inbox](https://github.com/futurenestit/xparse/discussions/737)
> 大周會（2026-06-17）優先序：**In-app Inbox `P0` › Email `P1` › 第三方（Slack/Line/Teams）`P2`**
> 最後更新：2026-06-23

本文整合五件事：**(1) 所有 role**、**(2) 所有事件 + 收件人建議**、**(3) 事件等級**、**(4) SSE vs Poll 比較**、**(5) 第三方收 notification 的建議**。

---

## 1. 所有 Role

系統裡有**多套正交的 role 分類法**，服務不同用途。通知收件人主要用 §1.1 的 `SystemRole`。

### 1.1 `SystemRole` — 授權角色（最主要的「role」）

> 來源：`xparse_iam/xparse_iam/domain/value_objects/authorization.py`
> 用途：授權決策的 base permission set（policy 規則評估前的基礎權限）。
> 推導：`system_role` 不直接儲存，而是在 `xparse_iam/xparse_iam/client.py` 由 `key_type + scopes + risk_level` 以 priority cascade 推導。


| Role                | 值                 | 範圍                            |
| ------------------- | ----------------- | ----------------------------- |
| **System Admin**    | `system_admin`    | 平台層，跨所有 tenant 的最高權限          |
| **Tenant Admin**    | `tenant_admin`    | 單一 tenant 內的管理者               |
| **Group Admin**     | `group_admin`     | tenant 內某 group 的管理者（PRD-057） |
| **Tenant Auditor**  | `tenant_auditor`  | tenant 內的稽核 / 唯讀角色            |
| **Tenant User**     | `tenant_user`     | 一般使用者（預設角色）                   |
| **Group Developer** | `group_developer` | group 內的開發者                   |


### 1.2 其他正交分類（非「授權 role」，但設計通知時會用到）


| 分類               | 來源                                                      | 值                                                                                      | 說明                                                 |
| ---------------- | ------------------------------------------------------- | -------------------------------------------------------------------------------------- | -------------------------------------------------- |
| `ActorType`      | `domain/value_objects/authorization.py`                 | `system` / `tenant_user` / `application` / `runtime`                                   | 「誰在動作」，非權限 role（`runtime` 為 SPEC-088 容器 runtime）   |
| `MembershipRole` | `db/models/identity.py`                                 | `admin` / `member`                                                                     | 某 user 在某 **group** 內的身分，與全域 `SystemRole` 正交       |
| `AuditRole`      | `3rd/xparse_audit/.../retention/audit_role.py`（ADR-007） | `security` / `sre` / `compliance` / `billing` / `app_owner` / `group_admin` / `system` | **稽核可見性**角色（誰能查哪些 audit 事件），與 `SystemRole` 是不同的分類法 |


> **通知設計重點**：稽核角色（`tenant_auditor` / AuditRole `compliance`）**不該收 push 通知**。框架本來就會 emit `iam.notification.*` 到 audit surface 供其查詢，再推一份只會重複又吵。

---

## 2. 所有事件 + 收件人建議

### 2.1 收件人設計原則

每個通知拆成兩種收件人：

- **主收件人（actionable）**：要*採取行動*的人 → 一律是「**受影響的當事人 / 資源擁有者**」，與 `SystemRole` 無關，由 **resource ownership** 決定。
- **監管副本（informational，選擇性）**：需要*知情*的管理者 → 依資源 scope 映射到 `group_admin` 或 `tenant_admin`。

三條去噪規則：

1. `tenant_auditor` / AuditRole 不收 push，走 audit surface 查詢。
2. `system_admin` 基本不收 tenant-scoped 通知（會變噪音），僅平台層事件例外。
3. 「擁有者」由 **resource scope** 決定：tenant-level key → `tenant_admin`；group-level key / app → `group_admin`；personal → 僅 creator 本人。

### 2.2 事件清單


| #   | 事件                                 | event_type（建議）                               | 主收件人（要行動）                                              | 監管副本（知情）                                                         | 備註                                                 |
| --- | ---------------------------------- | -------------------------------------------- | ------------------------------------------------------ | ---------------------------------------------------------------- | -------------------------------------------------- |
| 1   | **API key 即將到期**                   | `apikey.expiring` ⭐                          | key 的 **creator**（`created_by`）                        | scope 對應 owning admin                                            | creator 可能離職 → tenant/group-level key 必須有 admin 兜底 |
| 2   | **被 block**（denylist / rate-limit） | `creator.blocked`                            | 被封的 **creator / 當事 user**                              | owning admin（`group_admin`/`tenant_admin`）                       | 自動封鎖（ADR-241）admin 需知情；admin 手動封則去重                |
| 3   | **被重新啟用（reactivated）**             | `creator.reactivated`                        | 同 #2 的當事人                                              | 同 #2 的 admin                                                     | 與 block 對稱，服務恢復                                    |
| 4   | **違反 policy**                      | `policy.violated`                            | 違規的 **當事 principal**                                   | `**tenant_admin`**（security/治理，必收）                               | 最敏感；auditor 走 audit surface 不另推                    |
| 5   | **被邀請進 group**                     | `group.invited`                              | **被邀請的 user**（membership PENDING）                      | 邀請的 `group_admin`（對方 accept/decline **後**收結果）                    | invite 與其回應是兩個事件                                   |
| 6   | **被踢出 group**                      | `group.removed`                              | **被移除的 user**                                          | `group_admin`（發起者，通常已知 → 可選/去重）                                  | 當事人必收，否則不知權限沒了                                     |
| 7   | **App 部署結果**                       | `deployment.completed` / `deployment.failed` | 觸發部署的 **deployer**（常為 `group_developer`/`tenant_user`） | 該 app 的 `group_admin`；失敗且屬基礎設施層才升給 `tenant_admin`/`system_admin` | PRD 痛點即「deployer 只能 poll」                          |
| 8   | **配額超限**（候選）                       | `quota.exceeded`                             | tenant 的擁有者 / 觸發的 user                                 | `tenant_admin`                                                   | PRD 點名候選，尚未列入 v1 seed                              |


> **v1 seed producers**（PRD-195 §3.4，為證框架非 inert 而先接線）：`apikey.expiring`（建議的端到端第一刀）、`creator.blocked`。其餘為增量補上 —— 加事件 = registry 一筆 + template 一個，**不動 worker**（Open/Closed）。

### 2.3 可複用的 `RecipientStrategy`

不需每個事件寫一套，只需少數幾個 strategy（`resolve(context) -> list[RecipientRef]`）：

- `ResourceCreator` — 解析資源 `created_by`（#1 / #2 / #3）
- `AffectedUser` — 事件 context 帶的當事 user id（#4 / #5 / #6）
- `Deployer` — 部署請求發起者（#7）
- `OwningAdmins` — 依 scope 解析 owning `group_admin` / `tenant_admin`（所有監管副本共用）

---

## 3. 事件等級（Severity）

等級用來驅動 **channel eligibility**（`eligible(event_type)`）與 **預設監管副本是否開啟**。


| 等級           | 定義              | 預設 eligible channels      | 預設監管副本 |
| ------------ | --------------- | ------------------------- | ------ |
| **CRITICAL** | 立即影響服務或安全，需馬上處理 | in-app + email（+ webhook） | **開**  |
| **WARNING**  | 需注意，有時間窗可處理     | in-app + email            | 視情況    |
| **INFO**     | 知會性質            | in-app only               | 關      |


事件對映：


| #   | 事件           | 等級           | 理由               |
| --- | ------------ | ------------ | ---------------- |
| 1   | API key 即將到期 | **WARNING**  | 有 N 天緩衝，但不處理會斷   |
| 2   | 被 block      | **CRITICAL** | 服務中斷 + 安全事件      |
| 3   | 被重新啟用        | **INFO**     | 好消息，知會即可         |
| 4   | 違反 policy    | **CRITICAL** | 安全 / 治理，admin 必收 |
| 5   | 被邀請進 group   | **INFO**     | 社交性質             |
| 6   | 被踢出 group    | **WARNING**  | 權限狀態改變，當事人該知道    |
| 7a  | App 部署成功     | **INFO**     | 狀態知會             |
| 7b  | App 部署失敗     | **WARNING**  | 需 deployer 介入    |
| 8   | 配額超限         | **WARNING**  | 限流中，需擴容/調整       |


> **建議**：CRITICAL / WARNING 性質中，**security 類（#2 被封、#4 違規）預設開監管副本**；**社交類（#5/#6 group 進出）預設關**（admin 自己操作的不必再通知自己）。

---

## 4. SSE vs Poll 比較（即時性決議）

> 對應 PRD-195 §9 open question（push vs poll，owner：Peter + June）。
> 範圍：**in-app inbox 的瀏覽器如何得知有新通知**。Email / Slack 是 egress channel，不適用此題（見 §5）。

### 4.1 成本試算（以 1000 名使用者為例）

**Poll 每 30 秒一次**

- 1000 ÷ 30 ≈ **33 req/s** 持續
- 一天 ≈ **288 萬次請求**
- 絕大多數回傳「沒有新通知」→ 完整 TCP/TLS + session 驗證 + DB 查詢結果為 0，**純浪費**
- 此負載落在 **IAM web process**，與 validate auth 熱路徑搶資源

**SSE（長連線、server push）**

- 1000 條常駐連線
- **idle 時流量 ≈ 0、CPU ≈ 0**，僅真有通知才送 → 無浪費
- 成本從「請求率」轉為「連線數」（memory + fd + coroutine / 連線）

### 4.2 取捨


| 面向            | Poll 30s                            | SSE                                                          |
| ------------- | ----------------------------------- | ------------------------------------------------------------ |
| 純資源效率         | 差（288 萬空 poll/天）                    | **佳**（idle 近零）                                               |
| 延遲            | ≤ 30s                               | 即時                                                           |
| 新基礎設施         | **不需要**                             | 需跨 replica fan-out（Redis pub/sub 或 Postgres `LISTEN/NOTIFY`） |
| 多 replica 友善度 | **佳**（stateless，任何 replica 讀 DB 即回） | 差（連線 sticky，需 fan-out 到持有連線的 replica）                        |
| 與 IAM auth 隔離 | 需做輕量專用 endpoint                     | 1000 常駐連線恐吃掉 auth worker 併發，須獨立 process                      |
| 出貨速度          | **快**                               | 慢（要先建 fan-out）                                               |


### 4.3 建議

> **1000 人量級 → 先做 Poll，但要做對：**
>
> - 用**獨立、極輕的 `unread-count` endpoint**（非重用會驗一堆東西的一般 API），**不放在 validate 熱路徑**。
>   - `NotificationInbox` 已建 `(user_id, is_read, created_at)` 索引，count 查詢為微秒級，33 req/s 對吞吐不痛。
> - **自適應間隔**：idle 時 30–60s，使用者剛有動作後短暫加密。
> - 零新基礎設施、stateless、replica-safe，可立即出貨。

**SSE 升級觸發條件**（任一成立再上）：

1. 使用者量級往上跳（空 poll 從 33 → 數百 req/s 才開始真的浪費）；
2. 產品確實需要秒級通知延遲。

> 屆時應為**獨立的 SSE/WebSocket 服務 + Redis/`LISTEN-NOTIFY` fan-out**，而非塞進 IAM。

**一句話**：SSE 較「省資源」，Poll 較「省總成本（infra + 風險 + 工）」。1000 人量級下，省下的 288 萬次空 poll 抵不過 SSE 要付的跨 replica fan-out 與 auth 容量隔離成本 → **先 Poll，SSE 當有明確觸發條件的 v2**。

---

## 5. 第三方收 Notification 的建議

### 5.1 v1 現況（重要）


| Channel                               | v1 會收到？   | 即時性                    | 說明                                                               |
| ------------------------------------- | --------- | ---------------------- | ---------------------------------------------------------------- |
| **In-app inbox**                      | ✅         | 最快（取決於 §4 poll/SSE 決議） | DB insert，無對外 egress，恆可用、無 transient 失敗                          |
| **Email**                             | ✅         | **非即時**（秒~分鐘級）         | 走 Keycloak SMTP relay；async outbox + retry                       |
| **Webhook**                           | ✅         | 非即時                    | HMAC 簽章 POST；憑證走 ADR-233 `IntegrationCredential`                 |
| **Slack / Line / Teams / SMS / Push** | ❌ **未實作** | N/A                    | P2，**registered-but-unimplemented adapter slots**，只有槽位無 `send()` |


> **結論**：選 Email 的用戶**會收到但有延遲**；選 **Slack 的用戶 v1 收不到任何東西**（要等 P2 排上）。

### 5.2 為什麼 Email / 第三方不是即時的（刻意的 trade-off）

投遞流程**沒有任何一段是同步的**：

```
producer enqueue → NotificationOutbox (PENDING) → [週期 worker] → channel.send() → 用戶端
```

延遲三段組成：

1. **worker 排程間隔** — delivery worker 是 out-of-process 的週期性 management command（`manage.py notifications run`，沿用 `reconcile_token_quota` / `reap_idle_sidecars` pattern），**禁止跑在 IAM web worker 內**（隔離 SMTP egress / retry storm，免拖垮 auth）。文件**未釘死間隔** → 這是可調旋鈕。
2. **channel 外部投遞** — SMTP relay 有佇列 / greylisting（不在我們控制內）；Slack/Webhook 為外部 HTTP。
3. **失敗 retry** — `PENDING→SENDING→RETRY` 指數退避，`next_attempt_at` 決定下次嘗試。

ADR-249 明確**否決 inline send**（Alternative A）：理由是 SMTP latency 會 block producer 的 transaction、且 caller rollback 會造成 phantom email。框架刻意以「**非同步 outbox**」換取**原子性、durability、不拖垮 IAM auth**。

### 5.3 第三方實作建議（P2）

當 P2 開始實作 Slack/Line/Teams 等：

1. **無核心改動**：加一個 channel = 一個 `Channel` adapter（`resolve_address → render → send → classify_error`）+ 註冊到 `ChannelRegistry`，不動 outbox / worker / selector（INV-249-9 Open/Closed）。
2. **憑證走 ADR-233 `IntegrationCredential`**（per-tenant、加密），框架**不自建憑證儲存**（bot token / signing secret / API key）。
3. **偏好 raw HTTP over `httpx`**，避免重 SDK（sovereignty 考量）；vendor SDK 僅在不得已時用。
4. **每 channel 獨立 retry / 失敗隔離**：一筆邏輯通知 fan-out 成 `one row per (notification_id, channel)`，Slack 失敗不影響 email retry（INV-249-8）。
5. **MVP 工具集仍待調查**（#737 待辦）：Slack / Line / Teams 先選哪些、各自 webhook vs bot API 的取捨。
6. **即時性**：第三方 channel 的延遲天花板同樣被 worker 間隔 + 外部投遞綁死，**不應追求秒級**；秒級需求請走 in-app channel（§4）。

### 5.4 §8.1 驗證要求（真元件，非 fake）

每個 channel adapter 的 `send` 在宣稱 done 前，須對**真元件**驗證：

- Email → 真 SMTP sink（MailHog）+ 真 Keycloak（或 boundary-level HTTP stub 吐真 Admin response shape）
- In-app → 真 `NotificationInbox` row 可被真 Console 查詢讀到
- Webhook → 對真 receiver 投出帶合法 HMAC 簽章的 POST
- 第三方 → 對真 endpoint（或 sandbox）投遞成功

> 假設 trigger 的 fake 不算證據（RCA #1025 教訓）。

---

## 附錄：關鍵不變量速查（ADR-249）


| INV       | 內容                                                                                                               |
| --------- | ---------------------------------------------------------------------------------------------------------------- |
| INV-249-3 | 每筆 outbox 終結於 `SENT` 或 `DEAD`；`DEAD` 必帶 typed reason + emit `iam.notification.failed`。**無 silent drop**          |
| INV-249-7 | `enqueue_notification` **禁止**在 validate / authorize 熱路徑呼叫；producer 僅可掛 control-plane write 或 out-of-process scan |
| INV-249-8 | one row per `(notification_id, channel)`；各 channel 獨立投遞 / retry                                                  |
| INV-249-9 | delivery worker 為 channel-agnostic，僅透過 `Channel` port 觸及 channel；加減 channel 不動核心                                 |


> 通知失敗**不適用** ADR-041 audit fail-open 例外 —— `DEAD` 必須 loud（`iam.notification.failed` + typed reason），不得靜默丟。

