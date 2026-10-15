# FinOps FOCUS — Xparse 對齊與 Dashboard Tab 交付全紀錄

> 最後更新：2026-08-12（PRD-284 Rev.2 全鏈交付當日）
> 正式 source of truth 在 repo 內（見 §5 文件清單）；本檔是給人看的全景筆記。

---

## 1. 這是什麼

**FOCUS**（FinOps Open Cost and Usage Specification）是 FinOps Foundation（Linux Foundation 旗下）維護的**帳單資料開放規格**：固定欄位名、固定語意、可機器驗證的 MUST/SHOULD 規則。最新版 1.4（2026-06），1.5（目標 2026-12）將加入 AI 原生欄位（模型識別、input/output token）。它不是計費引擎、不是 API——只規定「帳單資料集長什麼樣」。企業 FinOps 團隊採購時會問「你們支援 FOCUS 嗎」，因為支援就代表他們不用為我們寫專用 ETL。

**Xparse 的定位（已拍板，ADR-324）**：
- 我們是 BYOK gateway，**不開發票、不收費**——成本永遠是「牌價估算」（list-price estimate），不是帳單金額。
- 對外話術固定為「**FOCUS 1.4 schema-faithful；usage conformant-shaped；cost 為 labeled estimate**」，**永不**宣稱「FOCUS-conformant cost」。
- `BilledCost` 欄存在但**恆空**（紅線）：規格要求它可對帳發票，我們沒有發票，填估算值 = 主動違規。估算走 spec 官方的 `x_` extension（`x_CostBasis=estimated_list_price` + `x_CostIn`/`x_CostOut`）。
- 差異化不在「有 FOCUS」（commodity），在**治理歸屬細度**：group→application 雙層 SubAccount + creator/end-user/policy 歸屬——雲廠單層帳單給不了。

**兩個成本平面並存（by design，最容易被問「數字為什麼對不上」的點）**：

| 平面 | 端點 | 計價基準 | 回答的問題 |
|------|------|---------|-----------|
| FOCUS 面 | `/audit/dashboard/focus`、`/focus/rows`、`/audit/export/focus` | **at-time-of-use**（事件上的 `price_in`/`price_out` 快照，ADR-265） | 「消費當下花了多少」 |
| latest-price 面 | `/audit/dashboard/usage-cost`、`/stats/*` | **最新價目表重估**（ADR-330，改價會重算歷史） | 「以今天的價，歷史用量值多少」 |

同一期間兩邊數字**必然不同**——價格一調整即分裂。這不是 bug；客訴時引 ADR-383 §1.3 / Core-ADR-04 補記。

---

## 2. 歷史脈絡（為什麼有 Rev.2）

- **2026-07-21**：PRD-254/ADR-324 交付 FOCUS CSV 匯出（`GET /audit/export/focus`，24 欄）。
- **2026-08-08**：PRD-284/ADR-383/SPEC-255 設計閉環（xparse#3354）。
- **2026-08-10**：v1 FinOps tab 交付——8 張 GridCanvas 卡片（xparse#3388-#3392 + Audit#101/#102）。
- **2026-08-11**：**整批 revert**（xparse#3396-#3400 + Audit#103/#104）。原因：June 不喜歡呈現——版面/視覺不好、缺欄位明細表、內容太單薄。v1 還有「UI schema 卡列了 10 個 CSV 沒有的欄」的所見≠所得問題。
- **2026-08-12**：**Rev.2 重做並全鏈 re-land**（本文 §3/§4）。形態改為**表格為主**：KPI 條 + FOCUS 聚合列資料表（欄 = 真實 Column ID）+ 雙粒度匯出；「表格可挑欄 ⊆ CSV 欄」成為硬不變量（INV-284-8）。

Rev.2 關鍵裁定（June，2026-08-12）：
- **OQ-4 粒度**：聚合為主（小時/日 bucket，ChargePeriod 為真實區間）、per-request 明細留在匯出。
- **OQ-5 PricingUnit**：CSV 維持 per-token（不改已出貨語意）、UI 顯示層格式化 per-1M。
- **OQ-6 成本欄**：補齊 21 個 Mandatory 欄，`ListCost`/`ContractedCost`/`EffectiveCost` 承載 `(estimated)` 估算（三欄同值——我們沒有折扣/攤銷軸）；連帶具名退役 INV-284-7 原「估算只走 x_」句（它與 SPEC-255 C-255-18/19 在同一天的 closure 裡互相矛盾）。
- 單一 `ListUnitPrice` 在 in+out 合併列上會破 FOCUS 列數學（`ListCost = ListUnitPrice × PricingQuantity`）→ 改 emit `x_ListUnitPriceIn`/`x_ListUnitPriceOut`。
- embeddings price snapshot（#3388）納入 re-land；InvoiceIssuerName 恆空（不開發票即無開票方）；BillingPeriod = calendar month UTC 合成。

---

## 3. 這次做了什麼（全部 merged，2026-08-12）

### 交付鏈（依 landing 順序）

| # | PR | 內容 |
|---|----|------|
| D1 | xparse **#3428** | 文件先行：PRD-284 Rev.2、SPEC-255 Rev.2（C-255-23..26 + probes P6-P10 + copy-gate 精確 allowlist carve-out）、ADR-383 Amendment A（rows 端點形狀 + granularity + bucketing）、ADR-324 Amendment A（INV-324-2 措辭釐清）、gap-analysis §7 七項 open decision 全結案、PRD-254 Amendment A、Core-ADR-04/Core-PRD-04/Core-PRD-05 回寫、ADR/PRD/SPEC 三 index 補漏 |
| A1 | Audit **#105** | CSV 24→**40 欄**：21 Mandatory 全齊 + SkuId/SkuPriceId/ResourceId/BillingAccountName + x_ListUnitPriceIn/Out + x_XparseEndUser；雙向 header-parity 測試鎖 `extrasaction` 靜默丟欄陷阱 |
| A2 | Audit **#106** | Revert-of-revert #101/#102（`/dashboard/focus` 復活 + creator fix：`x_XparseCreatorId` 只讀 `payload.creator_id`，不再 fallback 到裝著 api_key_uuid 的 actor.user_id）+ 新 **`GET /audit/dashboard/focus/rows`**（bucket × dimension Python fold）+ probes P6-P8 |
| A3 | Audit **#107** | `GET /audit/export/focus?granularity={per_request,aggregated}`，**兩粒度同一組 header**（PRD-254 I1）；self-audit event 帶 granularity；probes P9/P10 |
| P2 | xparse **#3432** | gateway audit 事件帶執行模型 `provider`（HostProviderName 資料源）；PAYLOAD_ALLOWLIST 是 load-bearing line，有 seeded-red dogfood |
| P3 | xparse **#3433** | Re-land embeddings price snapshot（#2573）；embeddings 從此可計價、也帶 provider |
| P5 | xparse **#3431** | C-255-16 收斂：移除 revert 放回來的死 finops 視圖、hoist trend-math/format-cost、修「not invoiced amounts」違規文案、刪 5 個 orphan i18n key |
| P6 | xparse **#3429** | dev-only tab gating re-land（這次**先於** tab 落地——v1 曾有 40 分鐘 tab 無 gate 直見 prod 的窗） |
| P4 | xparse **#3434** | submodule pointer bump `874fec6` → **`2486a905c`**（帶 A1-A3 進部署配對） |
| P7a | xparse **#3436** | FinOps tab shell：plain layout（**第一個非 GridCanvas dashboard tab**）、KPI 條、types/hooks 還原 + rows 新 types、eslint fence + import/copy gate（兩者皆有 seeded-red 證據） |
| P7b | xparse **#3440** | **FOCUS 聚合列表格**（挑欄/排序/分頁、localStorage 偏好、`__unattributed__` 原樣呈現）+ **columns-parity CI gate**（表格欄 ⊆ CSV 欄，dogfood 紅過） |
| P7c | xparse **#3441** | 匯出對話框：聚合列/per-request 雙粒度、範疇 = 頁面當前視圖（C-255-13）、純 href builder 有測試 |
| P8 | xparse **#3442** | wiki 概念頁修正還原（去掉 stale 宣稱、補 Rev.2 章節） |

### 驗證證據（貼在各 PR body）

- Audit repo 無 CI：本地全套件逐 PR 遞增全綠（baseline 2470 → #105 2488 → #106 2522 → #107 2542 passed，**零失敗**）。
- **§8.1 probes P1–P10 全綠**，跑在真 JsonlEventStore + **100× 價差 fixture**（snapshot 價 vs latest 價刻意差 100 倍——錯接 rollup 平面必然當場爆）：P1 同源、P2 基準正確、P3 歸屬真實、P4 誠實 null、P5 copy-gate dogfood、P6 Σrows==totals、P7 bucket 無縫鋪滿、P8 聚合列 unpriced 誠實、P9 三面 totals 相等+同 header、P10 BilledCost 雙粒度恆空。
- 前端：typecheck/vitest（最終 600 tests 0 failed）/i18n 三腳本/兩道 fence 全綠；每個 gate 都先看過**紅**（seeded regression）才信。

---

## 4. 涉及檔案路徑（完整清單）

### Audit repo（`3rd/xparse_audit`，獨立 repo，pin = 2486a905c）
- `src/audit/export/focus.py` — 40 欄 `FOCUS_1_4_COLUMNS` + `extract_usage()`（唯一投影，三個出口共用）+ row builder。**陷阱**：`csv.DictWriter(extrasaction="ignore")` 會靜默丟沒登記的欄——欄位清單與 builder 必須同 commit 改
- `src/audit/export/focus_aggregate.py` — `/dashboard/focus` 的 totals/breakdowns/series fold
- `src/audit/export/focus_rows.py` — 聚合列 fold（bucket × dimension；**不得** import 任一 rollup 平面）
- `src/audit/api/routers/focus_dashboard.py` — `GET /dashboard/focus` + `GET /dashboard/focus/rows`（RBAC：BILLING/COMPLIANCE/TENANT_ADMIN/TENANT_AUDITOR）
- `src/audit/api/routers/focus_export.py` — `GET /export/focus`（granularity 參數；self-audit event `audit.export.focus`）
- `src/audit/dashboard/rollup_projector.py` — `bucket_start_for()` / `BUCKET_WIDTHS`（bucketing 詞彙）
- `tests/integration/test_focus_export.py` · `test_focus_dashboard.py` · `test_focus_dashboard_probes.py`（P1-P10 + 100× 價差 fixture）

### Gateway（`bustream/`）
- `bustream/gateway/audit_helpers.py` — `price_snapshot_fields()`：executed-model 解析（INV-265-1），emit price 快照 + `provider`
- `bustream/audit/schema.py` — `AuditRecord.provider` 欄
- `bustream/audit/xparse_bridge.py` — `PAYLOAD_ALLOWLIST`（**不在清單的欄位會被靜默丟**——每次加欄都要記得這裡）
- `bustream/gateway/routes/embeddings.py` — embeddings completed 事件帶 model_uuid + price snapshot
- `tests/gateway-ci-suite.txt` — curated suite（新收錄 price-snapshot 與 embeddings 測試檔，讓 pin 真正 bind 在 CI）

### 前端（`frontend/console-app-refactor/`）
- `src/app/(main)/(overview)/(dashboard)/_tabs/finops/`
  - `index.tsx` — plain-layout tab（disclaimer + KPI 條 + 表格 + 匯出鈕）
  - `_components/finops-table-columns.ts` — **picker-eligible 欄位 const（parity gate 解析這裡）** + `deriveGroupBy()`
  - `_components/focus-rows-table.tsx` — 主表格（`rowCellValue`/`sortRows` 純函式可測）
  - `_components/finops-export-dialog.tsx` — 雙粒度匯出（`buildFinopsExportHref` 純函式）
  - `_components/focus-columns.ts` — 21 Mandatory roster（`FOCUS_MANDATORY_COLUMNS`）
  - `_components/unpriced-share.ts` · `subaccount-rows.ts` · `use-focus-data.ts`
  - `finops-import-gate.test.ts` · `finops-copy-gate.test.ts` — 兩道 fence 的 source-grep 測試
- `src/app/(main)/(overview)/(dashboard)/_components/tab-visibility.ts` — **`DEV_ONLY_TABS = {"finops"}`（開 prod 就改這裡）**
- `src/app/(main)/(overview)/(dashboard)/_components/format-cost.ts` · `trend-math.ts` — hoisted 共用工具
- `src/services/audit.ts` — `useDashboardFocus` / `useDashboardFocusRows` / `focusExportHref(granularity, bucketSize)`
- `src/types/audit.ts` — `DashboardFocusResponse` / `FocusAggregatedRow` / `DashboardFocusRowsResponse` 等
- `src/i18n/messages/{en,zh-TW}.json` — `dashboard.finops.*`（disclaimer 措辭固定「not payable amounts」——「invoiced」會被 copy gate 擋）
- `eslint.config.mjs` — scoped fence：finops/** 禁 import `useDashboardUsageCost` 與 `cost-usage/**`（INV-383-1）

### CI（`.github/`）
- `.github/scripts/finops-columns-parity-gate.py` — 表格欄 ⊆ CSV 欄（`--self-test` 3 情境；zero-parse 即紅）
- `.github/workflows/ci.yml` — static-gates job 新 step「FinOps Columns-Parity Gate」（GATE-TRACK adr=ADR-383）。**放這個 job 是因為只有它 checkout submodule**；前端 vitest job 看不到 audit repo

### 設計文件（`docs/`，repo 內 source of truth）
- `docs/prd/PRD-284-focus-1-4-dedicated-dashboard-page.md`（Rev.2）· `docs/prd/PRD-254-focus-aligned-governed-usage-cost-export.md`（Amendment A）
- `docs/spec/SPEC-255-focus-finops-dashboard-behavioral-contracts.md`（Rev.2，契約 C-255-1..26 + probes P1-P10）
- `docs/adr/ADR-383-focus-dashboard-aggregation-source.md`（Amendment A）· `docs/adr/ADR-324-focus-aligned-export-architecture.md`（Amendment A）
- `docs/architecture/focus-1.4-cost-usage-gap-analysis.md`（§7 全結案）
- `docs/adr/core/Core-ADR-04-*.md` · `docs/prd/core/Core-PRD-04-*.md` · `Core-PRD-05-*.md`（回寫）
- `xparse-wiki/wiki/concepts/finops-focus-dashboard.md`（概念頁）
- 研究底稿：`docs/research/RESEARCH-focus-1.4-cost-usage-alignment-2026-07-20.md` 等四篇 + `/Users/peter/Desktop/research/FOCUS-規格研究報告.md`（本次分析的規格全景）

---

## 5. 怎麼看 / 怎麼驗收

```bash
git pull && git submodule update --init 3rd/xparse_audit
cd frontend/console-app-refactor && pnpm dev   # port 4001
# 開 http://localhost:4001/dashboard?tab=finops
```

- **tab 只在 dev build 可見**（`DEV_ONLY_TABS` gate；prod build 連 deep link 都 fallback）。
- 後端資料需要本地 audit 服務跑到新 code（`/dashboard/focus*` 端點）——audit 容器要 rebuild/restart（audit 改動需 rebuild image 才生效，不像 IAM mount source）。沒更新時 tab 誠實顯示「資料不可用」。
- 驗收滿意 → 從 `tab-visibility.ts` 的 `DEV_ONLY_TABS` 移除 `"finops"`（一行 PR）即對 prod 開放。

---

## 5b. 與相鄰功能的交互

### PRD-229 Part C（end-user ↔ Keycloak 綁定，2026-08-12 merge：#3403/#3404/#3405）
- **對 FOCUS 零破壞**：FOCUS 三個出口（CSV / `/dashboard/focus` / `/focus/rows`）只讀 `end_user` **標籤**；Part C 是 additive——事件多了 `end_user_issuer`/`end_user_subject` 兩欄（`bustream/audit/xparse_bridge.py` allowlist :205-206），FOCUS 投影不讀即忽略。PRD-229 Part C 契約明文標籤行為不變（I1）、識別鍵不做 dashboard 分組維度（Non-Goal）。已驗證 #3404 與同日的 #3432/#3433（同三個 bustream 檔案）在 origin/main 上並存無衝突。
- **短期加分**：Console list-only 選人 → 新綁定 key 的標籤一致性提升，`Alice`/`alice` 碎片化（PRD-256 §1.3 已知債）對新 key 開始收斂。歷史 key 不回填（D11），`__unattributed__` 與既有碎片照舊。
- **未來接點**：見 §6 #12「照人算錢維度」。

### PRD-237 budget（進行中）
- **正交，勿耦合**：FOCUS 規格沒有 budget 欄位；budget 讀 latest-price 平面、FOCUS 讀 at-time-of-use。**不要**把 budget 線疊進 FinOps tab（兩平面數字互打）。

## 6. 未來待辦與已知問題

### 開放 prod 前（必做）
1. **June 視覺驗收** dev build 的 tab → 移除 dev-only gate（一行 PR）。
2. 開 prod 前跑一次 **`/fae-verify` 級 UI 驗證**（PRD-284 U1-U10 的 FAE 截圖驗收目前未跑——dev-only 階段刻意省略）。
3. 部署後跑 `/test-postdeploy` 對 rel/prod 驗證（PRD-247/ADR-316 紀律）。

### 正確性缺口（與 FOCUS 正交，但影響數字，建議開 issue）
4. **cache read/write token 沒乘進成本**：`cached_tokens`/`cache_write_tokens` 有抓、pricing resolver 有費率、但沒有任何地方做乘法（`bustream/production/pricing.py` 明標 deferred）。**兩個成本平面的數字對 cache 用量大的流量都是錯的**。這是今天就存在的 correctness bug，不是 FOCUS gap。
5. `HostProviderName` 歷史事件恆空（#3432 之後的新事件才有）——不回填、不虛構，屬預期，但報表讀者要知道。

### Phase 2 備選（有文件錨點，視需求排）
6. **聚合 SQL pushdown**（ADR-383 Amendment A §A.3）：目前 rows 端點是 Python fold + bounded-scan（`events_scanned`/`event_limit` 誠實截斷）；大 tenant 長視窗會截斷。pushdown = `aggregate_grouped`（有成本無 bucket）× `aggregate_time_buckets`（有 bucket 無成本）的機械合併，Python fold 降為 parity reference；需補 `_DIM_SQL` 的 creator/policy 條目。
7. **`by_policy` 維度**：populated 率未驗（wiki 註記），表格已有欄但預設隱藏。
8. **creator 顯示名**：`x_XparseCreatorId` 是 opaque id；等 SPEC-211 P6 masking 的 display-name 面接上。
9. **FOCUS 1.5（2026-12）對齊**：AI 原生欄位（模型識別、input/output token 欄）落地後加 `focus_1_5` mapping profile（ADR-324 預留切換點）；屆時考慮 input/output **拆列**（官方建議），影響 PricingUnit/單價欄設計。
10. **budget（PRD-237）與 FOCUS 保持正交**：FOCUS 規格沒有 budget 欄位；budget 讀 latest-price 平面、FOCUS 讀 at-time-of-use——**不要**把 budget 線疊進 FinOps tab（會製造兩平面數字互打的困惑）。
12. **「照人算錢」維度（等有需求再開，PRD-229 Part C 已鋪路）**：目前 end_user 維度按**標籤字串**分組——標籤是建 key 當下凍結的，同一個人改名後新舊 key 標籤不同、會被拆成兩列。若要跨改名/改 email 穩定的 per-person 維度，把 `(end_user_issuer, end_user_subject)` 升級為 rows 端點新 dimension + CSV 新欄（如 `x_XparseEndUserRef`）。要動的點：audit `extract_usage` + `FOCUS_1_4_COLUMNS` + rows fold 維度映射 + 前端 `finops-table-columns.ts`（columns-parity gate 自動盯前後端一致）+ SPEC-255 補一條契約。Additive 小工項。
11. 認證（選配）：FinOps Certified FOCUS Conformant 只驗到 1.2、需 Linux Foundation 會員 + 2-3 位 FOCUS Analyst 個人認證；目前定位不宣稱 conformant cost，暫不追（SPEC-255 明列不在範圍）。

### 維運注意
- 改前端表格欄位或後端 `FOCUS_1_4_COLUMNS` 時，static-gates 的 **columns-parity gate** 會自動重驗（含每次 submodule pointer bump）；gate 解析不到任何欄會直接紅（non-vacuous）。
- FinOps 頁散文禁 `invoice`/`billed`/`FOCUS-conformant cost`（copy gate；`BilledCost`/`InvoiceIssuerName` 識別字走精確 allowlist）。
- finops 目錄禁 import `useDashboardUsageCost` / `cost-usage/**`（eslint fence + gate test）——有人圖方便接回 latest-price 平面會被擋。
