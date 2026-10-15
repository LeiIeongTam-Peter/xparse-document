# Xparse Notification Fan-out：機制與實作解析

> 依據 PRD-215（Audit-Derived Dashboard and In-App Notification Backend）、PRD-203（Notification Framework）、ADR-271。
> 狀態快照：2026-07-07。所有 file:line 皆從當日 code 實際驗證。
> 本文是學習用文件：解釋「一個事件如何變成 N 個人各自的通知」，以及每一跳（hop）用了什麼機制、為什麼需要它。

---

## 1. 什麼是 Fan-out？我們為什麼選它

**Fan-out（扇出）**：一個邏輯事件（例如「node X 掛了」）要通知一群人時，系統為**每位收件者各建立一列**自己的通知，而不是所有人共讀同一列。

```
1 個 alert candidate ──► N 位收件者 ──► N 列 notification_inbox
                                         （每列有自己的 is_read / is_archived）
```

這是經典的 **fan-out on write**（寫入時展開）取捨：

| 方案 | 寫入成本 | 讀取成本 | per-user 狀態 |
|------|---------|---------|--------------|
| **Fan-out on write**（我們的選擇） | 高：一事件寫 N 列 | 低：查自己的列，一條 index scan | 天然支援——`is_read`/`is_archived` 就在自己那列上 |
| Fan-out on read（共用一列，讀時展開） | 低：一事件一列 | 高：每次讀都要 join 可見性規則 | 需要額外的 per-user read-state 表，join 才知道讀沒讀 |

我們選 fan-out on write 的理由：

1. **收件者集合很小**。audience 是 admin 集合（tenant admins / group admins / system admins），放大倍率通常是個位數，不是社交網路那種百萬 follower 場景——寫入放大的代價可以忽略。
2. **read/unread/archive 必須是個人狀態**（PRD-215 A9/A13：一個人標讀不影響別人）。fan-out on write 讓這件事變成「一列一欄位」，零額外設計。
3. **收件者要在「發送當下」快照**。事後角色變動不能回溯改變「當時通知了誰」（PRD-203 §3.1）——fan-out 寫下的列本身就是快照。
4. **Console 讀取路徑要極簡**。polling API 只需 `WHERE user_id = me` 一個條件，不需要在讀取時重算可見性。

代價是表會隨事件×收件者成長——所以整條管線的機制設計，核心目標就是**控制每一跳的放大倍率**，並讓**每一跳都冪等**（重跑不增列）。

---

## 2. 全鏈路總覽：每一跳做什麼、放大倍率是多少

```
audit events（可能上千個）
     │  機制 1：時間桶去重 ——「N 個事件 → 1 個 candidate」（縮減）
     ▼
audit_alert_candidates（1 列 / rule × scope × bucket）
     │  機制 2：audience_hint 延遲解析 ——「策略 id → 具體收件者」（此刻才展開）
     │  機制 3：global candidate → platform-operator tenants（受控的跨 tenant 扇出）
     ▼
RecipientRef 清單（通常個位數）
     │  機制 4：冪等 enqueue ——「1 candidate × N 收件者 → N 列 outbox，重跑不增列」
     ▼
notification_outbox（N 列，durable）
     │  機制 5：state-machine 投遞 ——「outbox → inbox，crash 也不重複」
     ▼
notification_inbox（N 列，一人一列）
     │  機制 6：per-user 狀態 + 擁有權過濾
     │  機制 7：cursor 分頁 + 複合索引（讀取成本與表大小脫鉤）
     ▼
Console 60 秒 polling
```

貫穿全鏈的兩個原則：

- **冪等鏈（idempotency chain）**：每一跳都有自己的確定性 key——`dedupe_key` → `uuid5(dedupe_key)` → `UNIQUE(notification_id, recipient, channel)` → `inbox.id = outbox.id`。任何一跳的 worker 重跑、重試、多副本並發，都不會讓使用者多收到一則通知。
- **Fail-closed**：任何「不確定該通知誰」的情況（未知 audience、非 operator tenant、無效 candidate）一律解析成 **0 收件者** 並記 log，絕不廣播（PRD-215 §3.8 / N1）。

以下逐一拆解每個機制。

---

## 3. 機制 1：時間桶去重——把「事件數」和「通知數」脫鉤

**檔案**：`3rd/xparse_audit/src/audit/alerts/candidate_projector.py`

**問題**：如果一個 node 反覆 down，10 分鐘內噴 500 個 `fleet.node.down` 事件，難道要發 500 則通知？

**解法**：projector 不是「一事件一通知」，而是把符合規則的事件**按 (tenant, 時間桶) 分組**，一個桶只產生一個 candidate：

```python
# candidate_projector.py:120-127
bucket_start = bucket_start_for(occurred_at, rule.bucket_size)   # floor 到桶邊界
key = (_tenant(event), bucket_start)
buckets.setdefault(key, []).append(_event_ref(event, occurred_at))
...
dedupe_key = f"{rule.rule_id}:tenant:{tenant}:{bucket_start.isoformat()}"
```

三個實作重點：

1. **`dedupe_key` 是確定性的**——由 `rule_id + scope + bucket_start` 組成，不含任何隨機成分。同一個桶不管重算幾次，key 都一樣。
2. **`candidate_id = uuid5(dedupe_key)`**（`candidate_projector.py:137`）——UUID v5 是 namespace + name 的雜湊，**同輸入永遠同輸出**。這讓 candidate 的 primary key 本身就是冪等鎖：重跑 projector 時 `upsert_candidates` 插不進重複列。這也是「rebuildable」的基礎——truncate 全表重放 evidence，會收斂到一模一樣的列。
3. **`_EVENT_REF_CAP = 100`**（`candidate_projector.py:45-47`）——candidate 只帶前 100 個事件 id 參照，真實數量放 `payload_json["count"]`。熱桶再熱也撐不爆單列。

另外兩個防禦：

- **`scan_limit` 有界掃描**（`:103-108`）：掃到上限會大聲 log warning（"candidates may be partial; raise the scan limit"），絕不靜默截斷——bounded 但 fail-loud。
- **Redaction**（N3）：candidate 只帶事件 id 參照與聚合統計（count、bucket），永不帶 raw prompt/response；`AlertCandidate` constructor 會直接拒絕 forbidden payload keys。

**學習點**：fan-out 系統的第一道防線不在扇出那一跳，而在**扇出之前把輸入壓扁**。事件量是不可控的（取決於系統多壞），但 candidate 量是可控的（rule 數 × scope 數 × 時間桶數）。

---

## 4. 機制 2：`audience_hint` 延遲解析——扇出時機的選擇

**檔案**：`xparse_iam/xparse_iam/notifications/audience.py`

**問題**：誰該收到通知？這個決定該在哪一層做？

**解法**：audit 側的 candidate **不存最終收件者**，只存一個策略 id（`audience_hint`，如 `"group_admins"`）。真正解析成人，發生在 IAM puller 拉走 candidate 的那一刻：

```
audit 側存的：audience_hint = "group_admins"        （抽象策略）
IAM 側解析成：["oidc-sub-alice", "oidc-sub-bob"]     （具體 OIDC subjects）
```

為什麼要拆兩層？

1. **服務邊界**（ADR-271）：「誰是 group admin」是 IAM 的身分職權，audit 服務根本沒有這個資料——candidate 只能描述 *what happened / who may need to know*，不能描述 *who exactly*。
2. **解析時效**：收件者在 enqueue 當下解析並**快照到 outbox**，之後角色變動不會回溯改變已發送的通知（PRD-203 §3.1）。太早解析（projection 時）會拿到過時名單；解析後不快照則會被未來的角色變動污染。

實作是一個**策略 registry**（`audience.py:104-108`），新增 audience 是加一個 entry，不用改 puller：

```python
_STRATEGIES = {
    "tenant_admins": _resolve_tenant_admins,
    "group_admins": _resolve_group_admins,
    "system_admins": _resolve_system_admins,
}
```

各策略的行為：

| 策略 | 解析邏輯 | 縮小範圍的關鍵 |
|------|---------|--------------|
| `tenant_admins` | 該 tenant 內 accepted admin membership 的 distinct subjects | tenant 邊界 |
| `group_admins` | 同上，再用 `payload["group_uuid"]` 過濾到**單一 group**（`audience.py:74-79`） | 只有事發 group 的 admin 收到；其他 group 的 admin 連列都不會產生 |
| `system_admins` | 只對 `Tenant.is_platform_operator=True` 的 tenant 生效，否則 0 收件者（`:92-100`） | 錯 scope 的規則永遠不會廣播進客戶 tenant |
| `specific_user:<sub>` | 單一 subject，且必須 active（`:124-136`） | 停用帳號收不到 |
| **未知 hint** | **回 `[]` + log warning**（`:138-146`） | fail-closed 的兜底 |

底層查詢用的是真實的身分權威 `OIDCUserGroupMembership`（role=admin、status=accepted），`.distinct()` 保證同一人跨多個 admin group 也只出現一次（`audience.py:47-56`）。

**學習點**：fan-out 的「展開點」要放在**擁有身分資料的服務**、且在**發送當下**。展開太早會過時，展開太晚（讀取時）就變成 fan-out on read。而「未知 → 空集合」的 fail-closed 預設，是防止設定錯誤演變成全員廣播事故的保險絲。

---

## 5. 機制 3：Global Candidate 的受控跨 tenant 扇出

**檔案**：`xparse_iam/xparse_iam/notifications/alert_puller.py:162-176`

**問題**：fleet 事件（如 `fleet.node.down`）不屬於任何 tenant——candidate 的 `tenant_uuid` 是空字串。但 inbox 是 tenant-scoped 的（polling API 用 caller 的 tenant 過濾），沒有 tenant 的通知誰都看不到。

**解法**：puller 在 tenant 維度做第二層扇出——空 tenant 的 candidate 展開到**每一個 platform-operator tenant**：

```python
# alert_puller.py:164
scope_tenants = [cand_tenant] if cand_tenant else _platform_operator_tenant_uuids()
```

然後對每個 scope tenant 各跑一次 audience 解析 + enqueue，通知列上帶著**該 tenant 的 uuid**，tenant-scoped 的 polling API 才查得到。

兩個 fail-closed 細節：

- 全系統沒有任何 platform-operator tenant 時，candidate 被 skip 並 log warning（`:165-172`），不會硬塞給誰。
- 這個扇出與機制 2 的 `system_admins` 策略配合：就算 rule 設錯把 `system_admins` 用在客戶 tenant 上，策略層還會再擋一次（非 operator tenant → 0 收件者）——**兩層獨立的防線**。

**學習點**：扇出可以是多維的（收件者維度 × tenant 維度）。每加一個扇出維度，就要問「這個維度的邊界誰把關」——這裡的答案是 `is_platform_operator` flag，一個明確的、可查詢的邊界，而不是 worker 裡的 if/else 猜測。

---

## 6. 機制 4：冪等 Enqueue——扇出寫入的原子性與去重

**檔案**：`xparse_iam/xparse_iam/notifications/enqueue.py` + `alert_puller.py`

這是真正「一變 N」的寫入點，也是最容易出事的一跳：worker 重跑怎麼辦？寫到一半 crash 怎麼辦？兩個 puller 副本同時跑怎麼辦？三個機制疊起來回答：

### 6.1 確定性 notification_id（重跑不重複）

```python
# alert_puller.py:29,47-48
_NOTIFICATION_NAMESPACE = uuid.UUID("a1c0de00-0000-5203-a1e7-000000000000")

def _notification_id_for(dedupe_key: str) -> str:
    return str(uuid.uuid5(_NOTIFICATION_NAMESPACE, dedupe_key))
```

`notification_id` 不是隨機產生，而是從 candidate 的 `dedupe_key` 確定性導出。於是「同一個 candidate」不管被 pull 幾次，logical notification id 永遠相同——冪等性從機制 1 的 dedupe_key 一路**傳遞**下來。

### 6.2 資料庫層的 UNIQUE 鎖（並發也不重複）

```python
# db/models/notification.py:112-117
models.UniqueConstraint(
    fields=["notification_id", "recipient_user_id", "channel"],
    name="unique_notification_recipient_channel",
)
```

配合 enqueue 用 `get_or_create`（`enqueue.py:91`）而非裸 insert：重複的 (notification, recipient, channel) 組合會拿回既有列而不是報錯或插新列。**冪等的最終防線放在 DB constraint，不是應用層記憶**——多副本並發時應用層檢查會有 race，UNIQUE constraint 沒有。

### 6.3 原子扇出（all-or-none）

```python
# enqueue.py:88-113
with transaction.atomic():          # savepoint 嵌在 caller 的交易裡
    for recipient in recipient_list:
        for channel in ntype.eligible_channels:
            row, _created = NotificationOutbox.objects.get_or_create(...)
    for row_id in created_row_ids:
        transaction.on_commit(lambda ...: _emit_queued_after_commit(row_id))
```

- N 列 outbox **要嘛全部 commit、要嘛全部消失**（ADR-093 #1 no partial state）——不會出現「10 個 admin 有 6 個收到」的半套狀態。
- `iam.notification.queued` audit event 掛在 `transaction.on_commit` 上（`enqueue.py:20-25`）——rollback 掉的 enqueue 不會留下「已排隊」的假證據。**審計證據不能比狀態先行**。

### 6.4 Poison-pill 隔離（一顆壞 candidate 不毒死整批）

```python
# alert_puller.py:151-161
try:
    candidate = _validate_candidate(candidate)
except InvalidAlertCandidate:
    summary["invalid"] += 1
    logger.exception("dropping invalid candidate %r — batch continues", ...)
    continue
```

無效 candidate 被**計數、記 log、跳過**，不會 abort 批次、也不會卡住 `next_since` watermark——否則一列壞資料會讓 watermark 永遠前進不了，**壓制之後所有告警**（這比重複通知嚴重得多）。注意這不是吞例外：`invalid` 有計數器、有 `logger.exception`，是典型的「fail-loud 但 fail-isolated」。

**學習點**：扇出寫入的三問——「重跑會怎樣？」（確定性 id + UNIQUE）、「寫一半 crash 會怎樣？」（transaction.atomic）、「一筆壞資料會怎樣？」（poison-pill 隔離 + 計數）。三問都有明確答案，這一跳才算完成。

---

## 7. 機制 5：Outbox → Inbox 投遞——顯式狀態機

**檔案**：`xparse_iam/xparse_iam/notifications/worker.py` + `channels.py`

**問題**：為什麼不在 enqueue 時直接寫 inbox，要多一層 outbox？

因為 outbox 承擔的是 **durable 投遞語意**：inbox 只是 `inapp` channel 的落點，未來還有 email/webhook 等會失敗、要重試的 channel。把「決定通知誰」（enqueue）和「實際送達」（drain）分開，各自才能冪等。

投遞 worker（`drain_once`）是一個顯式狀態機：

```
PENDING ──claim──► SENDING ──成功──► SENT
   ▲                  │
   └──RETRY◄──失敗(transient)──┘
                      └──失敗(permanent / 重試耗盡)──► DEAD（+ iam.notification.failed）
```

四個關鍵設計：

1. **原子單一認領（single-claim）**（`worker.py:213-221`）：
   ```python
   claimed = NotificationOutbox.objects.filter(
       id=row_id, status__in=[STATUS_PENDING, STATUS_RETRY]
   ).update(status=STATUS_SENDING, next_attempt_at=deadline)
   if claimed != 1:
       continue  # 別的 worker 搶到了
   ```
   用「條件式 UPDATE 的 rowcount」當鎖——只有 UPDATE 命中的那個 worker 擁有這列。兩個 worker 副本同時跑也不會 double-send（INV-203-5），而且這招在 SQLite 和 Postgres 都可攜。

2. **Inbox 寫入本身冪等**（`channels.py:62-72`）：
   ```python
   NotificationInbox.objects.get_or_create(
       id=outbox.id,   # 確定性：直接複用 outbox row id 當 inbox id
       ...
   )
   ```
   worker 在「插入 inbox 之後、標記 SENT 之前」crash，下輪重投時 `get_or_create` 撞到同 id 直接返回——使用者不會看到兩則。**冪等鏈的最後一環**。

3. **成功要重讀確認**（`worker.py:182-187`，ADR-093 #3）：標 SENT 後重新 SELECT 那列驗證狀態真的是 SENT，不信任 `update()` 的返回值。

4. **絕不靜默丟失**（INV-203-3）：每列的終態只有 `SENT` 或 `DEAD`；`DEAD` 必發 `iam.notification.failed` audit event 帶 typed reason。另有 stale-SENDING 回收（`worker.py:103-158`）：worker crash 留下的 SENDING 列會在 lease 過期後被撿回 RETRY 或送 DEAD——不會有列永遠卡在中間態。

**學習點**：投遞層的正確性不是「盡量送到」，而是**每列在狀態機裡有唯一去向、每個中間態有回收路徑、每個終態有證據**。retry 用指數退避（60s 起跳、上限 1h，`worker.py:47-49`），耗盡 `max_attempts` 就 DEAD——失敗是有界的，不是無限重試。

---

## 8. 機制 6：Per-user 狀態與擁有權過濾——fan-out 的收穫期

**檔案**：`xparse_iam/xparse_iam/db/models/notification.py:126-172` + `api/ninja_api/_notifications.py`

前面所有機制的成果，就是 inbox 的「一人一列」。這讓 per-user 狀態變得 trivial：

```python
# notification.py:144-151
is_read = models.BooleanField(default=False)
is_archived = models.BooleanField(default=False)   # 2026-07-07 archive amendment
read_at = models.DateTimeField(null=True, blank=True)
archived_at = models.DateTimeField(null=True, blank=True)
```

- 你標讀只翻你那列的 `is_read`；同 group 另一位 admin 的未讀數完全不受影響。
- **Archive implies read**：archive 一則未讀通知會原子性地同時標讀（`_notifications.py:180-187`，兩個 UPDATE 包在同一交易），未讀數永不包含 archived 列。
- Archive 只是 flag 翻轉，不搬資料、不刪列——unarchive 清掉 `archived_at` 但保留 `read_at`。

**擁有權過濾**：所有讀寫 endpoint 一律以 caller 身分過濾——

```python
# _notifications.py:155-156（mark_read；archive/unarchive/list 同型）
NotificationInbox.objects.filter(
    id=notification_id, user_id=user_id, tenant_uuid=tenant_uuid, ...
)
```

動別人的通知 id（或別的 tenant 的）filter 直接落空 → 回 `404`。用 404 而不是 403 是刻意的：**不洩漏該 id 是否存在**（PRD-215 A16 existence-leak 防護）。

**身分邊界**：`_caller_scope`（`_notifications.py:64-78`）要求 session 帶 `oidc_sub`——收件者解析全部以 OIDC subject 為單位，API key 不是「人」，用 API key 登入打 notification endpoint 一律 `403` fail-closed（issue #1828 的已知產品議題）。

---

## 9. 機制 7：讀取成本與表大小脫鉤——cursor 分頁 + 複合索引

**檔案**：`db/models/notification.py:156-169` + `_notifications.py:113-127`

fan-out 表會持續長大，但只要**每條查詢路徑都是 index range scan + LIMIT**，讀取成本就與表總大小無關：

**Cursor 分頁，明文禁 offset**（PRD-215 §3.6 backpressure）：

```python
# _notifications.py:113-127
qs = NotificationInbox.objects.filter(user_id=user_id, tenant_uuid=tenant_uuid)
...
qs = qs.filter(created_at__lt=cursor)   # cursor = 上一頁最後一列的 created_at
```

`OFFSET 100000` 要先掃過十萬列再丟掉；`WHERE created_at < cursor ORDER BY created_at DESC LIMIT n` 直接從索引定位。表一億列時兩者差距是數量級的。

**三條複合索引各服務一條查詢路徑**：

| 索引 | 服務的查詢 |
|------|-----------|
| `(user_id, is_read, created_at)` | unread-count |
| `(tenant_uuid, user_id, is_read, created_at)` | 預設清單（`status=all/unread`） |
| `(tenant_uuid, user_id, is_archived, created_at)` | archived 清單（archive amendment 新增） |

索引欄位順序 = 「等值過濾欄位在前、range/排序欄位（`created_at`）在最後」——這樣一條索引同時吃掉 WHERE 和 ORDER BY。

**機制 8（2026-07-07 落地）：30 天 retention purge**（PRD-203 §3.7，OQ-4/OQ-5 定案）。`xparse_iam/notifications/retention.py::purge_expired`：

- **Inbox**：`created_at` 超過 `XPARSE_NOTIFICATION_RETENTION_DAYS`（預設 30，`<= 0` 停用）的列 hard delete——**但 archived 列豁免**（archive 就是使用者的「keep」訊號，刪掉會廢掉 archive 功能）。
- **Outbox**：只刪**終態**列（SENT/DEAD）；PENDING/RETRY/SENDING 是還沒送完的工作，永不清。
- 可以放心 hard delete 的前提：`iam.notification.*` audit events 才是合規紀錄，inbox/outbox 只是 read model / 投遞狀態——刪列不損失證據。
- 實作紀律：批次刪除（bounded transaction）、刪除時重新套用資格過濾（select 和 delete 之間被 archive 的列會存活）、跑完後以同一 cutoff 重數資格列驗證歸零（ADR-093 #3）、有刪東西就發一則 `iam.notification.retention_purged` 摘要 audit event。
- 排程：`manage.py notifications purge` 掛在 pro/enterprise compose 的 notification worker loop（每 60 秒一輪）；purge 不受 `XPARSE_NOTIFICATIONS_ENABLED` 閘門——資料衛生不是投遞功能。

---

## 10. 放大倍率總算：為什麼實際不會爆

把每一跳的倍率相乘：

```
事件數（不可控，可能很大）
  × 機制1: → rule × scope × bucket        ≪ 1（大幅縮減：500 個事件可能只剩 1 個 candidate）
  × 機制2: → 該 scope 的 admin 數          ≈ 2–10（audience 天生是小集合，不是全員廣播）
  × 機制3: → platform-operator tenant 數   ≈ 1–2（只對 global candidate 生效）
  × channel 數                             = 1（v1 只有 inapp）
```

v1 實際狀態：3 條 P0 規則 live、bucket 去重、每 scope 個位數 admin——就算天天有事件，inbox 一年增長也在 10⁴–10⁵ 列量級，Postgres 毫無壓力。而讀取端（機制 7）保證就算未來長到 10⁸ 列，polling 延遲也不變。

天花板由 retention 封頂（機制 8，2026-07-07 落地）：非 archived 的 inbox 列與終態 outbox 列最多活 30 天，穩態表大小 = 30 天的產生量，**有界**。使用者想留的走 archive（豁免清除），合規證據走 audit events（永久）。

---

## 11. 可以帶走的設計原則

1. **在扇出之前壓扁輸入**。放大倍率是乘法——最上游省 1 倍，下游每一跳都省 1 倍（機制 1 的時間桶去重）。
2. **冪等 key 要一路傳遞，不要每跳自己發明**。`dedupe_key → uuid5 → UNIQUE constraint → inbox.id = outbox.id`，一條鏈路上任何一跳重跑都被上游傳下來的確定性 key 吸收。隨機 id（`uuid4`）出現在冪等路徑上就是 bug 的前兆。
3. **冪等的最終防線放 DB constraint，不放應用層**。應用層檢查在並發下有 race；`UNIQUE` + `get_or_create` 沒有。
4. **扇出點放在擁有資料的服務、發生在發送當下、結果要快照**（機制 2）。抽象策略（audience_hint）跨服務傳遞，具體名單只在解析當下存在一次。
5. **Fail-closed 是廣播系統的保險絲**。未知策略、錯誤 scope、無效資料——一律 0 收件者 + log，寧可漏發（有 audit event 可查）也不誤發（收不回來）。
6. **壞資料要隔離，不能卡住 watermark**。poison-pill 毒死批次的後果（之後所有告警被壓制）比重複通知嚴重得多（機制 4.4）。
7. **投遞用顯式狀態機**：每列有唯一去向（SENT/DEAD）、中間態有 lease 回收、失敗有界（backoff + max_attempts）、終態有 audit 證據。
8. **寫入放大換讀取簡單，前提是讀取真的簡單**：cursor + 複合索引讓查詢成本與表大小無關，否則 fan-out 兩頭都貴。
9. **Retention 可以延後，但要先鋪好「可以刪」的架構**：合規證據（audit events）與 UI read model（inbox）分離，read model 才敢刪。

---

## 12. References

| 類型 | 位置 |
|------|------|
| PRD | `xparse/docs/prd/PRD-215-audit-derived-dashboard-notification-backend.md`（§3.4 candidate、§3.5 puller、§3.6 polling + archive amendment） |
| PRD | `xparse/docs/prd/PRD-203-notification-framework.md`（outbox/inbox 框架、OQ-4 retention） |
| 全流程文件 | `docs/notification-dashboard.md`（dashboard + notification 兩條管線總覽） |
| 機制 1 | `xparse/3rd/xparse_audit/src/audit/alerts/candidate_projector.py` |
| 機制 2 | `xparse/xparse_iam/xparse_iam/notifications/audience.py` |
| 機制 3、4 | `xparse/xparse_iam/xparse_iam/notifications/alert_puller.py`、`notifications/enqueue.py` |
| 機制 5 | `xparse/xparse_iam/xparse_iam/notifications/worker.py`、`notifications/channels.py` |
| 機制 6、7 | `xparse/xparse_iam/xparse_iam/db/models/notification.py`、`api/ninja_api/_notifications.py` |
| 機制 8 | `xparse/xparse_iam/xparse_iam/notifications/retention.py`、`tests/integration/test_notification_retention.py`、PRD-203 §3.7 |
