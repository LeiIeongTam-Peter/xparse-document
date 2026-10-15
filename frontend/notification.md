# In-App Notification — Frontend 實作參考(給 frontend agent)

> 目標:在 `frontend/console-app-refactor/` 做 notification UI(header bell + `/notifications` inbox 頁)。
> 後端已全部就緒並 live 驗證(PRD-215 Phase 4,2026-07-06);**API service 層已寫好且 merge(PR #1829)——你只做 UI 組裝,不要重寫 hooks、不要直接 fetch**。
> 契約來源:PRD-215 §3.6;後端實作 `xparse_iam/xparse_iam/api/ninja_api/_notifications.py`。

---

## 0. 三條紅線(違反即錯)

1. **Polling only**。唯一的常駐輪詢是 `useNotificationCounts()` / 相容 alias `useUnreadCount()`(server 指示 60s)。禁止加 SSE、WebSocket、long-poll、或對 list 端點做常駐輪詢(PRD-215 NG1/A10)。
2. **403 = 「此 session 沒有通知面」,不是錯誤**。API-key 登入的 session(無 OIDC 身分)打任何 notification 端點都回 403(設計行為,issue #1828)。UI 必須**整個隱藏** notification 面(bell 不渲染),不可顯示錯誤、不可 retry(hooks 已內建停止 retry/polling)。判斷用 `isNotificationSurfaceUnavailable(error)`。
3. **不要照舊 mock UI 抄功能**。舊的 notification UI(commit `6cba2b4c`,已在 PR #1816 整個移除)是接假資料的 demo,含 **delete、mark-unread、bulk select** ——這些**真 API 都沒有**。Type filter 現在可用 `event_type` exact filter；可以參考舊 UI 的視覺與版面,功能面以本文為準。

---

## 1. 後端 API(7 個端點,全部 cookie session auth)

前端一律走 `iamClient`(自動帶 `xparse_session` cookie、自動映射 `/apis/iam/*` ingress 路徑)。

### 1.1 `GET /iam/notifications/counts`

tab/badge 計數的建議輪詢端點。回應:

```json
{
  "all_count": 9,
  "unread_count": 4,
  "archived_count": 2,
  "poll_after_seconds": 60
}
```

- `all_count` = `status=all` 的 rows 數量,包含 archived。
- `unread_count` = unread 且不含 archived。
- `archived_count` = `status=archived` 的 rows 數量。
- `poll_after_seconds` 是 server 權威的輪詢節奏。

### 1.2 `GET /iam/notifications/unread-count`

舊 unread-only poll endpoint。回應:

```json
{ "unread_count": 3, "poll_after_seconds": 60 }
```

保留給只需要 bell badge 的舊 client；Console refactor 目前用 `useNotificationCounts()` 走 `/counts`,避免 unread + archive badges 產生兩條常駐 poll。`poll_after_seconds` 是 server 權威的輪詢節奏——hook 已尊重它,UI 不要再自己加 timer。

### 1.3 `GET /iam/notifications?before=<cursor>&limit=<n>&status=all|unread|archived&event_type=<type>`

Cursor 分頁的 inbox list(newest-first,絕不 offset)。回應:

```json
{
  "items": [
    {
      "id": "69422997-50ae-40a8-84c8-05835b9694bf",
      "event_type": "audit.alert",
      "title": "[critical] fleet.node.down",
      "body": "Audit alert fleet.node.down (severity=critical).",
      "payload": {
        "rule_id": "fleet.node.down",
        "severity": "critical",
        "candidate_id": "…",
        "dedupe_key": "…",
        "count": 1,
        "bucket_size": "1h",
        "bucket_start": "2026-07-06T07:00:00+00:00"
      },
      "is_read": false,
      "is_archived": false,
      "created_at": "2026-07-06T07:20:38.970Z",
      "read_at": null,
      "archived_at": null
    }
  ],
  "next_before": "2026-07-06T07:20:38.970287+00:00",
  "poll_after_seconds": 60
}
```

- `next_before` = 下一頁(更舊)的 cursor;`null` 表示到底了。
- `status=all` 包含 archived；`status=unread` 不含 archived；`status=archived` 只回 archived。
- `event_type` 可省略；提供時為 exact match type filter,會和 `status` / `before` 一起套用。
- 其他 `status` 回 400。
- 空白 `event_type` 回 400,不可 silent fallback 成 all。
- `limit` 上限 100。
- 注意 `title` 格式固定 `[<severity>] <rule_id>`;`payload.severity` ∈ `info | warning | critical`(**不是** error/success——舊 UI 的 severity 集合是錯的)。

### 1.4 `POST /iam/notifications/{id}/read`

標讀單則(冪等;重複標讀仍回 ok)。只能標自己的——他人的/不存在的回 404(不洩漏存在性)。回應:

```json
{ "ok": true, "unread_count": 2 }
```

### 1.5 `POST /iam/notifications/read-all`

全部標讀。回應同上。

### 1.6 `POST /iam/notifications/{id}/archive`

封存單則。archive implies read；若原本 unread,後端在同一 transaction 標 read + archived。回應:

```json
{ "ok": true, "unread_count": 2 }
```

### 1.7 `POST /iam/notifications/{id}/unarchive`

取消封存單則。read state 保留,不會把通知恢復成 unread。回應同上。

### 1.8 錯誤形狀

| 狀況 | 回應 |
|------|------|
| 未登入 | 401 |
| session 無 OIDC 身分(API-key 登入) | **403** `{"detail": "notification user identity is not available"}` → 隱藏整個面 |
| `status` 亂填 / cursor 非 ISO-8601 | 400(明確訊息) |
| 標讀他人的通知 | 404 |

---

## 2. 已就緒的 service 層(直接用,勿重寫)

`src/services/notifications.ts` + `src/types/notifications.ts`(已在 main):

| Hook | 語意 |
|------|------|
| `useNotificationCounts()` | 常駐 poll;回傳 `all_count` / `unread_count` / `archived_count`;`refetchInterval` 尊重 `poll_after_seconds`;遇 403 **自動停止** polling 與 retry |
| `useUnreadCount()` | 相容 alias,目前同樣走 counts endpoint;舊 caller 可繼續讀 `unread_count` |
| `useNotifications(status, enabled?, eventType?)` | `useInfiniteQuery`;`eventType` 是 optional exact `event_type` filter;`fetchNextPage()` 用 `next_before` cursor;`hasNextPage` 判斷到底;**不輪詢**(list 只在開啟/mutation 後刷新);可用 `enabled` 延遲到 popover/頁面開啟才 fetch |
| `useMarkNotificationRead()` | mutation(傳 `notificationId`);成功後 invalidate 整個 `["iam","notifications"]` family(counts + list 都會刷新) |
| `useMarkAllNotificationsRead()` | 同上,全部標讀 |
| `isNotificationSurfaceUnavailable(error)` | **判斷 403 no-surface**;bell 渲染前用它 gate |

型別:`NotificationItem`、`NotificationSeverity`(`info|warning|critical`)、`NotificationStatusFilter`(`"all"|"unread"|"archived"`)。

React Query key 慣例:`["iam","notifications","counts"]` / `["iam","notifications","list",status]`——mutations 已 invalidate,UI 不需手動 refetch。

---

## 3. 要做的 UI 與擺放位置

依 `frontend/console-app-refactor/CLAUDE.md` 的 component placement 規則:

| 元件 | 位置 | 說明 |
|------|------|------|
| Notification bell(含未讀 badge) | `src/components/layout/notification-bell.tsx` | 加進 `(main)/layout.tsx` 的 header(breadcrumb 右側,`ml-auto`)。**用 `isNotificationSurfaceUnavailable` gate:403 時整顆 bell 不渲染** |
| Notification row(severity icon + title + body + timeAgo + 未讀點) | `src/components/features/notification/notification-row.tsx` | bell popover 與 inbox 頁共用 |
| Inbox 頁 | `src/app/(main)/(other)/notifications/page.tsx` | **stub 已存在**,填內容即可;breadcrumb 自動生成,不用配置 |

建議互動(參考舊 UI 視覺,功能收斂到真 API):

- **Bell**:未讀 badge(>9 顯示 `9+`);點開 popover 顯示最近幾則(用 `useNotifications("all", popoverOpen)` 延遲 fetch)+ mark-all-read 按鈕 + 「View all」連到 `/notifications`。或更簡:bell 直接 `router.push("/notifications")`——二選一,popover 是加分不是必須。
- **Inbox 頁**:`all | unread | archived` filter(tabs)、type filter(`event_type` exact match select)、逐列點擊標讀(`is_read=false` 的列才觸發 mutation)、mark-all-read、archive/unarchive、`fetchNextPage` 的 Load more(或 intersection observer)、empty/loading(skeleton)/error(retry)三態。
- **Severity 視覺**:`info` → `Info`/`text-info-500`;`warning` → `AlertTriangle`/`text-warning-500`;`critical` → `ShieldAlert`/`text-error-500`。未知值 fallback 到 info。色值一律用 design token class,不 hardcode(§18.4)。
- 時間顯示用現成的 `timeAgo()`(`src/lib/format.ts`)。

**不要做**(v1 範圍外):delete、mark-unread、通知偏好設定、deep-link 授權跳轉(payload 目前沒有 href;若未來有,記住 INV-215-7:deep link 不是授權,目標頁自己會再驗)、任何 realtime transport。

視覺參考:`git show 6cba2b4c` 可看舊 bell/popover/row 的樣式(注意其 severity 集合與功能面不可照抄)。

---

## 4. 本地驗證方式

- **SSO(OIDC)登入**的 session 才有通知面。dev DB 目前有真通知(4 則 `[critical] fleet.node.down` + 1 則 `tenant.status_changed`,收件者是 demo-* 的 platform-operator admins)。
- **API-key 登入**(含 bootstrap admin key)必定 403 → 驗收「bell 完全不出現、console 無錯誤」正是用這條路。
- 日常驗證跑 `pnpm typecheck` + lint 即可;交付前或動到 shared layout 才需要 browser 證據(repo P3 規則)。

## 5. 驗收清單

- [ ] SSO 登入:bell 顯示、badge 數字正確、60s 自動更新(可觀察 network:只有 counts 在輪詢)
- [ ] API-key 登入:無 bell、無 console error、network 上 403 後**不再重試**
- [ ] Inbox 頁:status/type filter 切換、點列標讀(badge 同步減)、read-all、cursor load more 到底後停
- [ ] 無任何 SSE/WebSocket 連線
- [ ] RWD:320px 寬度下 bell 與 inbox 頁可用(repo RWD 規則)
- [ ] 不新增 `.js/.jsx`;色彩/間距全走 design tokens

## 6. References

- 後端契約:`xparse_iam/xparse_iam/api/ninja_api/_notifications.py`(source of truth)
- PRD-215 §3.6(polling 契約)、NG1/A10(no realtime)、INV-215-7(deep link ≠ 授權)
- Issue #1828(403 no-surface 的產品決策——目前採「前端隱藏」路線)
- PR #1829(service 層)、PR #1816(舊 mock UI 移除)、commit `6cba2b4c`(視覺參考)
- 全流程背景:`/Users/peter/Desktop/X-parse/docs/notification-dashboard.md`
