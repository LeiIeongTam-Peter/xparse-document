# 價格形狀去留決策備忘（2026-10-01）

**範圍**：四個價格（input／output／cache read／cache write）以外、只有 API 寫得進去的價格形狀。reasoning 價已經決定收掉（Amendment Q），不在這份備忘裡。
**依據**：origin/main f239dc6、Audit 33f8f35。rel／prod 一次都沒有查，表中「可能有資料」全是推估。

## 一、總表

| 形狀 | 誰在寫（會執行的寫入者） | Console 設得到嗎 | prod 可能有資料嗎（信心） | 對計價／路由的影響 | 建議 | 收掉的成本 |
|---|---|---|---|---|---|---|
| `length_tiers` | 只有 price-schedule API：凡是有 `model.update` 權限的主體都能寫，Console 登入者自己打 API 也算。伺服器端的 carry 和截斷段只複製既有值 | 不能；但編輯、reprice、缺口「延長前一段」這三條路會把既有值原樣送回 | 推估沒有，但沒有證據（中）。寬鬆 dict 時期在 prod 開到 09-23，在 rel 開到 09-22 | **會改變金額**。IAM 逐筆依 prompt 長度選階，影響 admission 429；prod／rel 跑的是舊 `budget_usage_query`，一樣會套。FOCUS、Audit 快照聚合、OTel 都用第 0 階。Audit 會把倍率 0 當成 1。路由不讀 | 先只收寫入，盤點確認 0 筆後再全收 | 停寫：低。全收：中高，要改三個計價引擎、6 個 vector、Audit 兩個 repo，還要做客戶自架的升級檢查；若真有資料，歷史金額會重述 |
| `modifiers`／`modifier_compat` | 只有 API | 不能；會原樣送回 | 推估低，沒有證據 | **金額不會變**：gateway 從來不送 `active_modifiers`，倍率永遠是 1。只有兩個作用：讓該日不能走 rollup；它是 `PricingError` 唯一的觸發來源。Audit 不讀 | 寫入、讀取都收掉 | 中：2 個 vector 加上每案的欄位、三處 pin 要重釘、`pricing_error` 要換觸發來源。**這會推翻 C-302-10、Am.P②、ADR-489 Rev.2#3** |
| `components.cache_storage_rate` | 只有 API | 不能；而且會讓 Console 上改的 cache write 被悄悄忽略 | 有實際值的推估極低（中高）。照抄 ADR 範例寫入的列可能帶 null 鍵，但不起作用 | 只在 Anthropic／Bedrock 上把 cache write 改成 input 價。Audit dashboard 對這種段算的是 band 價，不是 $0（SPEC-302 C-302-7 寫錯了）。對 Gemini 沒有效果。路由不讀 | 寫入、讀取都收掉，和 reasoning 放同一個 PR | 低到中：刪 ③ 分支、改 1 個 vector 和 22 個 expected 欄位、三處 pin、C-302-19。若有資料：IAM 的歷史金額會變成 band 價，FOCUS 快照仍是 input 價 |
| cache write `per_ttl` 舊形狀（只有 mult、或多檔）＋ API 的 `mult` 寫法（含 `cache_read.mult`） | 舊形狀過去由 synthesis、0256、Am.I 編輯器、backfill、seed 寫過；現在只剩 API 接受 mult 輸入，存檔時會換成 flat | 不能；Console 只寫一檔 flat | active 多檔：0（09-23 部署時跑過 0312）。active 只有 mult：推估 0（中）。inactive 很可能有，但沒有人讀。舊的 `cache_read:{mult}`：未知 | 金額不變：多檔一律取第一檔，只有 mult 的算 0 並記 warning。路由不讀 | API 的 mult 寫法只收寫入；讀取端的 warning 保留；儲存形狀不改 | 低：改 schema 和 3 支測試，和 reasoning 共用一次 OpenAPI 重產 |
| `line_items` | 沒有（09-09 起新寫入一律 400） | 不能；會原樣送回 | 未知，推估 0；ADR 範例裡有這個鍵，照抄去打 API 就可能寫進去 | 沒有讀取者。例外：pricing 裡只有 line_items 時，三個引擎會把該段當成未定價 | 全收，加一支防禦式清除 migration | 低。migration 要保留「pricing 不是空的」這個狀態，並逐列在改前改後比對 `resolve_pricing` |
| 純量段（`pricing=NULL`） | **Console 每天都在寫**：沒有 cache 預設的 provider（vllm、deepseek、ollama 等）兩個 cache 欄都空白時就會寫出；Console 也會把 JSON 段降回純量段 | 會間接寫出，但不是操作者能選的選項 | 很可能有（中） | cache write 用 input 價；但 JSON 段缺 cache write 時算 0，同一模型有兩種結果。以目前流量算金額影響是 0，因為只有 Anthropic／Bedrock 會產生 cache write token。路由不讀 | 只收寫入：寫入時一律補上 input／output 鏡射；讀取保留 | 低：改一個函式，約 10 支測試改用 raw create，C-302-6 和 INV-300-21 改措辭 |
| `currency`／`unit` | 沒有生產環境的寫入者；`unit` 目前仍可新寫 | 不能；沒有 cache 類別時，Console 會連整包 pricing 一起丟掉 | 幾乎 0（高） | 沒有讀取者；FOCUS 直接寫死 USD／tokens | `unit` 改成只放行原樣送回；盤點確認 0 筆後兩者都改成直接拒絕 | 極低；要修訂 INV-300-42 |

## 二、調查和查證說法不同時的裁定（全部以查證為準）

- **length_tiers 停寫不等於比照 Amendment Q。** reasoning 是寫入、讀取都收，而且本來就不影響金額；length_tiers 只收寫入、讀取保留，所以仍會影響金額。
- **「原樣送回就放行」的比對方式。** 不是比原值，而是拿「DB 存的原值」比「`to_wire()` 處理後的值」。所以存了整數倍率、`null` 鍵或多餘鍵的舊列，今天可能已經不能從 Console 編輯。
- **Console 的 reprice-from 兩邊比的不是同一段。** Console 送的是「現在生效的那一段」，伺服器比的是「日期 X 所在的那一段」。X 落在別段或缺口時，正常操作也會被 400；reasoning 的 C-302-9③ 也會遇到同一個問題。
- **用 API 拿掉鍵是放行的。** 拿掉 length_tiers 會回溯改變那段時間的金額。
- **部署狀態以 DEPLOYMENT-LEDGER 為準，不能看 branch head。**
- **「Claude／GPT-5 也有長 prompt 分級價」查不到出處，標成未驗證。** 本機重現不出來，也和 repo 的研究結論（只有 Gemini 有）衝突。「我們的 length_tiers 不乘 cache 價」這一點仍然成立。
- **cache write 留空不是「沒有預設就免費」。** 實際有三種結果：provider 預設、0、input 價。
- **#4516 不要關掉。** 只拿掉「放寬成多檔」那一段，其餘快取能力缺口（和計價無關）保留。

## 三、#5490（路由套用分級價）還要不要做

如果 length_tiers 停寫，而且盤點 active 為 0 筆，C-302-22 解出來的單價就是 `components.input.flat`。Amendment M 之後，這個值一定等於純量 `cost_per_*_token`，所以路由排序完全不會變，#5490 沒有任何正面效果。modifiers 跟這件事無關，因為 C-302-22 本來就不估 modifier。

做了反而有風險：寬鬆時期留下的舊列如果缺 input／output 鏡射，`resolve_pricing` 會回 None，模型變成未定價、算 $0，被排成最便宜的。

**建議**：先凍結，盤點確認 0 筆後撤回；`routing_adapter.py:593` 那段錯誤註解另開小 PR 修。不建議改成 no-op，那只是多一段沒有價值的程式。撤回等於推翻你 09-30 的決定，所以放進下面的決策清單。

## 四、需要你決定的事

1. **length_tiers**
   - A：先只收寫入，盤點（包含客戶自架環境）確認 0 筆後全收【建議】
   - B：現在就全收
   - C：維持現狀
2. **用 API 拿掉既有段的 length_tiers**
   - A：不允許；要停用就從某個日期開新段【建議】
   - B：允許，但記一筆回溯改價稽核
3. **#5490**
   - A：先凍結，盤點 0 筆後撤回【建議】
   - B：照原計畫做
   - C：改成 no-op
4. **modifiers**
   - A：寫入、讀取都收掉【建議】
   - B：只收寫入
   - C：維持 C-302-10／Am.P② 的原決定
5. **`PricingError` 失去唯一觸發來源後怎麼辦**
   - A：改成「既有價格資料解析不了」時觸發，並補上對真元件的證據【建議】
   - B：連 `pricing_error` 回應一起退場
   - C：不處理，留下一條永遠不會觸發的路徑
6. **cache_storage_rate、line_items、API 的 mult 寫法、unit**
   - A：照總表的建議一次核准【建議】
   - B：全部只收寫入
7. **cache write 欄位留空代表什麼**
   - A：有 provider 預設就用預設，沒有就是 0，同時停止寫出純量段【建議】
   - B：一律用 input 價
   - C：四個價格欄位都改成必填

**不需要你決定、我會直接做的事**：
- 「原樣送回」的比對改成兩邊都先正規化再比
- Console reprice-from 改成用日期 X 所在的那段預填
- `inventory_pricing_schema` 補計上面這些形狀，也掃 inactive 列
- 走純量路徑的測試改用 raw create
- 修正過期的文件和註解

## 五、請 operator 在 rel／prod 跑的唯讀檢查

以下在 IAM 容器內執行，全部只讀不寫。客戶自架環境在升級前也要跑同一段，這是走到「全收」前的條件。

```
python manage.py inventory_pricing_schema
python manage.py shell -c "
from collections import Counter
from django.db.models import Count
from xparse_iam.db.django_models import ModelPriceVersion as V, Model, UsageLedgerEntry as L
from xparse_iam.api.schemas import PricingSchema
from xparse_iam.db.pricing_normalize import _canonical
c=Counter(); odd=[]
for v in V.objects.all().iterator():
    t='A' if v.active else 'I'; p=v.pricing
    if p is None: c[t+':scalar']+=1; continue
    try:
        comp=p.get('components') or {}
        if not comp: c[t+':no_components']+=1
        for k in ('length_tiers','modifiers','modifier_compat','line_items','currency','unit'):
            if p.get(k) is not None: c[t+':'+k]+=1
        for k in ('cache_storage_rate','reasoning'):
            if comp.get(k) is not None: c[t+':'+k]+=1
        bands=(comp.get('cache_write') or {}).get('per_ttl') or []
        if len(bands)>1: c[t+':multi_band']+=1
        if any(b.get('flat') is None for b in bands): c[t+':mult_only']+=1
        cr=comp.get('cache_read')
        if isinstance(cr,dict) and cr.get('flat') is None: c[t+':cache_read_mult']+=1
        if v.active and _canonical(p)!=_canonical(PricingSchema.model_validate(p).to_wire()): odd.append(str(v.price_version_uuid))
    except Exception: c[t+':unparseable']+=1
print(dict(c)); print('round-trip candidates', odd)
print(list(V.objects.filter(active=True,pricing__isnull=True).values('model__provider').annotate(n=Count('pk'))))
claude=Model.objects.filter(provider__in=['anthropic','bedrock']).values('model_uuid')
print('non-Claude cache_write facts', L.objects.filter(phase='final',cache_write_tokens__gt=0).exclude(model_uuid__in=claude).count())
print('active_modifiers rows', L.objects.filter(active_modifiers__isnull=False).exclude(active_modifiers=None).exclude(active_modifiers=[]).count())
"
```

**怎麼看結果**：
- `A:length_tiers` 為 0 → 決策 1 和 3 可以往全收、撤回走。
- `non-Claude cache_write facts` 為 0 → 純量段停寫不會改變任何金額。
- `round-trip candidates` 列出來的是今天在 Console 可能編輯不了的段，需要人工逐筆看。

另外請對照 `docs/deployment/DEPLOYMENT-LEDGER.md` 確認目前部署的版本；如果 09-23 那次部署的 log 還在，再 grep `0311 skip`。
