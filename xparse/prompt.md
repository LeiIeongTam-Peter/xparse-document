write me a report for the folder. 報告必須涵蓋以下所有章節：

1. **是什麼應用** — 類型（Frontend / Backend / Library）、協議、面向對象、部署方式
2. **資料夾結構總覽** — 完整樹狀結構，每個檔案一行說明
3. **各模組功能說明** — 表格形式，含關聯文件（ADR/PRD/SPEC）
4. **對外 API 端點完整列表** — 每個端點：方法、路徑、用途、Request Headers/Body、Response 格式
5. **服務通訊全貌** — 這是最重要的章節，必須包含：
   - ASCII 架構圖，標示所有連線的協議與方向
   - 通訊連結總表（對象 / 類型 Frontend or Backend / 協議 / 方向 / 發起點檔案 / 失敗行為）
   - 每條連線的詳細說明，包含：
     - 確切的 HTTP endpoint URL（含 env var 名稱）
     - 完整 Request（Headers + Body JSON 範例）
     - 完整 Response（JSON 範例）
     - Timeout 設定與 env var
     - 失敗時的行為（fail-fast / fail-open / fail-closed）
     - 對應的程式碼檔案路徑與行號
6. **請求主流程** — ASCII 流程圖，標示每一步對應的檔案
7. **關鍵類別索引** — 表格：類別名稱 / 檔案 / 職責
8. **重要環境變數** — 表格：變數名稱 / 預設值 / 說明
9. **關聯文件索引** — ADR / PRD / SPEC 分組表格
10. **規模統計** — 各模組估計程式碼行數

語言：繁體中文（程式碼、檔案路徑、技術名詞保持英文）。
格式：Markdown，表格使用 | 語法。

list all apis in this backend services,分類成 前端和 後端，what api is for frontend, and what api is for backend 如果是backend 他的對像是誰？其他backend? and also list the port.

does it has any workflow when request is send to this backend services, or will it send request to other services regularly?

請根據提供的專案資料與架構文件，自動分析並生成一份完整的 warden.md 技術文件。文件須全程使用繁體中文撰寫，並包含以下四個章節：

一、服務端口清單（Service Ports）
以表格形式列出所有相關服務的端口資訊，欄位包含：

服務名稱
端口號碼
通訊協定（HTTP / HTTPS / gRPC / TCP 等）
用途說明

二、前端 API 清單（Frontend APIs）
列出所有由前端應用程式發起呼叫的 API 端點，每筆資料需包含：

HTTP 方法（GET / POST / PUT / DELETE 等）
端點路徑
目標服務
功能說明

三、後端 API 清單（Backend APIs）
列出所有由後端服務對外公開或內部使用的 API 端點，每筆資料需包含：

HTTP 方法
端點路徑
所屬服務
功能說明
呼叫來源（前端 / 其他後端服務 / 排程任務等）

四、工作流程（Workflows）
針對每個核心工作流程，以流程圖或步驟清單描述完整的請求流向，說明項目包含：

流程名稱
發起方（哪個服務或使用者操作）
請求路徑（經過哪些中間服務）
接收方（最終處理服務）
回應路徑（如有回傳資料）
