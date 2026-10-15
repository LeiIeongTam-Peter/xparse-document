# Xparse Console — 前端結構說明

React + Vite 管理後台。提供 Tenant / Group / Application / Fleet / Audit 等資源的管理介面，部署在 nginx auth_request 保護的路徑後面。

> **改前必讀順序**：本文件 → `frontend/console-app/design-system/Design.md` → 目標 component 的現有程式碼

---

## Frontend 目錄全貌

`frontend/` 下有多個子目錄，**只有 `console-app/` 是正式產品程式碼**：

```
frontend/
├── console-app/          ← ✅ 正式產品（本文件的主題）
├── web-demo/             ← Next.js 互動 Demo，展示 SSE 串流與 Agent 模式
├── console/              ← ⛔ 封存的早期 JSX 原型（4 個版本），不要修改
├── dashboard/            ← ⛔ PNG 截圖設計稿，無程式碼
└── setting/              ← ⛔ PNG 截圖設計稿，無程式碼
```

`console/`、`dashboard/`、`setting/` 是設計過程的產物，已封存，**不要在這些目錄裡修改或新增任何東西**。功能開發一律在 `console-app/` 進行。

---

## 技術棧


| 項目    | 選擇                                                                |
| ----- | ----------------------------------------------------------------- |
| 框架    | React 19 + Vite 7                                                 |
| 語言    | TypeScript（`strict: true`，禁止新增 `.js/.jsx`）                        |
| UI 元件 | shadcn/ui + Radix UI primitives                                   |
| 樣式    | Tailwind CSS v4 + CSS variables（design token）                     |
| 測試    | Vitest + React Testing Library                                    |
| 套件管理  | pnpm                                                              |
| Auth  | sessionStorage + HttpOnly cookie（後端設置）+ OIDC via `oidc-client-ts` |


---

## 啟動路徑

```
index.html
  └── src/main.tsx           掛載 React root
       └── src/App.tsx        殼，只 render XparseConsole
            └── src/XparseConsole.tsx   ← 整個 app 的核心
```

`XparseConsole.tsx` 負責三件事：

1. **Auth 狀態機**：驗登入、處理 OIDC callback、判斷是否授權進入 Console
2. **Layout**：Sidebar、Breadcrumb、頁尾 User dropdown
3. **導航**：用 `useState` 管理 `currentPage` / `currentView` / 所有選中的 entity ID

---

## 目錄結構與職責

```
src/
├── XparseConsole.tsx    ← 導航狀態機（2000 行，所有頁面切換邏輯）
├── App.tsx              ← 殼（只有一行 return <XparseConsole />）
├── main.tsx             ← React root 掛載點
├── index.css            ← 全域 design token（CSS variables）
│
├── services/            ← 純函數，不含 React state
├── hooks/               ← services + React state 的膠水層
├── contexts/            ← 跨元件全域狀態
├── config/              ← URL 設定、品牌預設、i18n
├── constants/           ← 靜態常數
├── utils/               ← 純工具函數
├── lib/                 ← cn() helper
├── test/                ← 測試初始化
│
└── components/
    ├── ui/              ← shadcn 原生元件（不要修改）
    ├── common/          ← 跨頁面共用元件
    └── <domain>/        ← 每個功能頁面一個資料夾
```

---

## 導航系統

這個 app **沒有** URL routing（沒有 react-router）。導航完全是 React state：

```typescript
// XparseConsole.tsx — 所有導航狀態
const [currentPage, setCurrentPage] = useState('dashboard');
const [currentView, setCurrentView] = useState('list');

// 選中的 entity（每個有 detail 頁的資源各一對）
const [selectedApp, setSelectedApp] = useState<string | null>(null);
const [selectedAppName, setSelectedAppName] = useState<string | null>(null);
const [selectedGroup, setSelectedGroup] = useState<string | null>(null);
const [selectedGroupName, setSelectedGroupName] = useState<string | null>(null);
const [selectedTenantUuid, setSelectedTenantUuid] = useState<string | null>(null);
const [selectedTenantName, setSelectedTenantName] = useState<string | null>(null);
const [selectedModelName, setSelectedModelName] = useState<string | null>(null);
```

頁面渲染方式是條件式 mount/unmount：

```tsx
{currentPage === 'applications' && currentView === 'list' && <ApplicationsList />}
{currentPage === 'applications' && currentView === 'app-detail' && <ApplicationDetail appId={selectedApp!} />}
```

**已知限制**：重新整理頁面回到 dashboard、瀏覽器 Back 鍵無效、無法 deep link。這是已知技術債，未來遷移方向是加 react-router v6，不是換 Next.js（這個 app 不需要 SSR，純靜態部署在 nginx 後面）。

---

## 四層資料流

```
component
  └── hook（useApi.ts）            — React state + 呼叫 service
       └── useDataFetch(fetchFn)   — 通用 fetch wrapper（loading/error/refresh）
            └── services/api.ts   — 純函數，發 HTTP，接 apiKey 作參數
```

### Layer 1：`services/api.ts`（純函數）

每個函數簽名：`someAction(apiKey: string, params?) → Promise<T>`。不碰任何 React state。

```typescript
// 例：呼叫方式
export async function listApplications(apiKey: string, groupUuid?: string) {
  const res = await fetch(`${config.iamUrl}/applications?group_uuid=${groupUuid}`, {
    headers: { Authorization: `Bearer ${apiKey}` },
  });
  // ...
}
```

### Layer 2：`hooks/useApi.ts`（React 狀態包裝）

兩個通用 hook，所有 domain hook 都建在這上面：

```typescript
// 讀取資料（自動在 mount 時 fetch）
useDataFetch<T>(fetchFn, deps?) → { data, loading, error, refresh, setData }

// 寫入操作
useMutationState() → { run, loading, error }
```

`useDataFetch` 會在 HTTP 401 時自動呼叫 `handle401()` → 清 sessionStorage → 重整頁面。

### Layer 3：Domain hooks

```typescript
// hooks/useApi.ts 裡的 domain hook 範例
export function useApplications(tenantId?: string, groupId?: string) {
  return useDataFetch(
    (apiKey) => api.listApplications(apiKey, groupId),
    [tenantId, groupId]
  );
}
```

### Layer 4：`useQueryScope()`

從 AuthContext 推導出 `tenantId` / `groupId`，決定 API 查詢範圍：

```typescript
const { tenantId, groupId } = useQueryScope();
const { data: apps } = useApplications(tenantId, groupId);
```


| `visibility_scope` | tenantId      | groupId       | 效果                |
| ------------------ | ------------- | ------------- | ----------------- |
| `global`           | undefined     | undefined     | 看全部（system_admin） |
| `tenant`           | 來自 auth_scope | undefined     | 只看此 tenant        |
| `group`            | 來自 auth_scope | 來自 auth_scope | 鎖在此 group         |


---

## Auth 流程

### 登入

```
使用者輸入 API key
  → POST /iam/auth/validate（Bearer token）
  → 後端回傳 auth context（tenant_uuid, key_type, scopes…）
  → deriveAuthScope()：key_type → ui_role + visibility_scope
  → sessionStorage 存 xparse_api_key + xparse_auth_context
  → 後端同步設置 HttpOnly cookie（xparse_session）← JS 無法讀寫
  → fetchCapabilities()：拿後端 capability overrides
  → render ConsoleApp
```

### OIDC / SSO

```
使用者點 SSO 按鈕
  → UserManager.signinRedirect()（oidc-client-ts）
  → Keycloak 驗身份（prompt=login，強制重新驗，不接受 silent session）
  → callback 回 [BASE_URL]/oidc/callback
  → POST /iam/oidc/exchange（id_token）
  → 同普通登入：後端回 auth context → 存 sessionStorage
```

### 六個 UI 角色


| `ui_role`         | 來源 `key_type`     | 資料範圍                          |
| ----------------- | ----------------- | ----------------------------- |
| `system_admin`    | `system`          | 全域                            |
| `tenant_admin`    | `tenant`          | 單一 tenant                     |
| `tenant_auditor`  | `tenant_audit`    | 單一 tenant（唯讀）                 |
| `group_admin`     | `group`           | 單一 group                      |
| `group_developer` | `group_developer` | 單一 group（限制操作）                |
| `app_user`        | `application`     | 禁止進入 Console（直接導去 app portal） |


---

## 權限系統

### Capability Matrix

`services/pageCapabilities.ts` 是唯一來源。每個 `[pageId][ui_role]` 對應一個 `PageCapability`：

```typescript
interface PageCapability {
  visible: boolean;       // nav item 是否顯示
  route_access: boolean;  // 是否允許進入此頁
  data_scope: string;     // "global" | "tenant" | "group" | "own_group_detail"
  mode: string;           // "hidden" | "read_only" | "read_write"
  actions: string[];      // 允許的操作（"create", "edit", "delete"…）
  disabled_reason?: string; // "feature_disabled" | "feature_preview" | "role_readonly"
}
```

### Route Guard

在 `XparseConsole.tsx` 的 `useEffect` 裡執行，每次 `currentPage` 改變就重新檢查：

```typescript
useEffect(() => {
  const cap = resolvePageCapability(authScope, currentPage);
  if (!cap.route_access) {
    setCurrentPage(defaultPage); // 導回預設頁
  }
}, [currentPage, authScope]);
```

### 新增頁面的必要步驟

1. 在 `CAPABILITY_MATRIX` 加入新的 `pageId`（每個 ui_role 都要填）
2. 在 `XparseConsole.tsx` 的 sidebar 加 nav item
3. 在渲染區域加 `{currentPage === 'new_page' && <NewPage />}`
4. 如果有 detail view，加對應的 `selectedXxx` / `selectedXxxName` state

---

## Services 目錄


| 檔案                    | 職責                                                       |
| --------------------- | -------------------------------------------------------- |
| `api.ts`              | 所有 IAM API endpoint 包裝（~90 個函數，2200 行）                   |
| `auth.ts`             | login / logout / getApiKey / handle401 / deriveAuthScope |
| `oidc.ts`             | SSO 流程（Keycloak）、callback 處理                             |
| `pageCapabilities.ts` | Capability Matrix + resolvePageCapability()              |
| `roleSimulation.ts`   | system_admin 模擬其他角色（存 localStorage）                      |
| `auditApi.ts`         | Audit log 專屬 API                                         |
| `fleetApi.ts`         | Fleet / Node 管理 API                                      |
| `quotaApi.ts`         | 配額查詢 API                                                 |
| `registryApi.ts`      | Docker registry API                                      |
| `editionApi.ts`       | 版本 / feature flag API                                    |
| `myDeployments.ts`    | 我的部署資料                                                   |


---

## Hooks 目錄


| 檔案                                  | 職責                                                                                                       |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `useApi.ts`                         | 所有 domain hooks 的集合（`useApplications`, `useTenants`, `useGroups`…） + `useDataFetch` + `useMutationState` |
| `useQueryScope.ts`                  | 從 AuthContext 推導 tenantId / groupId                                                                      |
| `usePageCapability.ts`              | 查詢目前角色在指定頁面的 capability                                                                                  |
| `useRoleSimulation.ts`              | 角色模擬狀態管理                                                                                                 |
| `useAudit.ts`                       | Audit log 資料                                                                                             |
| `useFleet.ts` / `useFleetGroups.ts` | Fleet 節點資料                                                                                               |
| `useQuota.ts` / `useUsage.ts`       | 配額與用量                                                                                                    |
| `useRegistry.ts`                    | Docker registry 資料                                                                                       |
| `useSortable.ts`                    | 拖曳排序（dnd-kit）                                                                                            |
| `use-mobile.ts`                     | 偵測行動裝置                                                                                                   |


---

## Contexts 目錄


| 檔案                 | 用途                               | 取用方式         |
| ------------------ | -------------------------------- | ------------ |
| `AuthContext.tsx`  | 目前登入狀態、authScope、logout callback | `useAuth()`  |
| `BrandContext.tsx` | 主題顏色、字型、locale 字串                | `useBrand()` |


### Brand 系統

`useBrand()` 回傳 `{ brand, t, setBrand, setCustomTheme }`。

`**brand` 物件完整 shape：**

```typescript
{
  name: string;            // 品牌名稱
  title: string;           // 頁面 <title>
  logo: string;            // Logo 識別碼（對應 BrandLogo 的 logos map）
  primaryColor: string;    // 主色（按鈕、active nav、連結）
  primaryHover: string;    // 主色 hover（比 primaryColor 深 10-15%）
  accentColor: string;     // 強調色（成功狀態、亮點）
  backgroundColor: string; // 頁面背景
  sidebarBg: string;       // Sidebar 背景
  headerBg: string;        // Header 背景（深色 headerBg 會讓文字自動轉白）
  textPrimary: string;     // 主要文字
  textSecondary: string;   // 次要文字、說明
  borderColor: string;     // 邊框、分隔線
  fontFamily: string;      // CSS font-family stack
  locale: string;          // 'en' | 'zh-TW'
}
```

`**t` 翻譯物件：** 根據 `brand.locale` 從 `config/locales.ts` 取得，包含所有 nav label 與 UI 字串。

```typescript
const { t, brand } = useBrand();
<h1>{t.dashboard}</h1>         // "Dashboard" 或 "儀表板"
<span>{t.applications}</span>  // "Applications" 或 "應用程式"
```

**內建 brand presets**（定義在 `config/brandPresets.ts`）：


| Preset key   | 說明           | 主色           |
| ------------ | ------------ | ------------ |
| `xparse`     | 官方預設         | `#3B5EE8` 藍色 |
| `darkMode`   | 深色模式         | `#60A5FA` 淺藍 |
| `cathayBank` | 國泰世華（Demo 用） | `#00594F` 墨綠 |
| `ctbcBank`   | 中國信託（Demo 用） | `#C8102E` 紅色 |
| `esunBank`   | 玉山銀行（Demo 用） | `#007A3D` 綠色 |
| `fubon`      | 富邦金控（Demo 用） | `#0033A0` 深藍 |


> 金融業 presets 僅供展示，不得用於生產環境。

**新增自訂品牌：**

1. 在 `config/brandPresets.ts` 的 `brandPresets` 物件加入新 key
2. 在 `components/brand/BrandLogo.tsx` 的 `logos` map 加入對應 SVG
3. 可用 `VITE_DEFAULT_BRAND=myBrand` 環境變數指定預設品牌，或在 `XparseConsole.tsx` 改 `<BrandProvider initialBrand="myBrand">`
4. 執行期可用 `setBrand('myBrand')` 切換，`setCustomTheme(partialBrand)` 做局部覆蓋

---

## Components 目錄

### 底層（不要修改）


| 資料夾       | 說明                                                                                                           |
| --------- | ------------------------------------------------------------------------------------------------------------ |
| `ui/`     | shadcn/ui 原生元件（button, dialog, table, badge, input, tabs, sidebar…）。這些是 Radix 的標準封裝，不要直接修改                   |
| `common/` | 跨頁面共用：`Breadcrumb`, `PageLayout`, `ConfirmDialog`, `RoleSimulationBanner`, `ReadOnlyBanner`, `PreviewBanner` |
| `brand/`  | Logo、品牌設定畫面                                                                                                  |
| `dev/`    | 設計系統 sample，不出現在正式 nav（button-sample, badge-sample…）                                                         |


### 頁面元件（對應 Sidebar 入口）


| 資料夾               | 對應頁面                     | 重點元件                                                               |
| ----------------- | ------------------------ | ------------------------------------------------------------------ |
| `dashboard/`      | Dashboard                | 統計圖表、bar chart、line chart                                          |
| `tenants/`        | Tenants / My Tenant      | TenantsList, TenantDetail                                          |
| `groups/`         | Groups                   | GroupsList, GroupDetail, GroupModelPool, GroupMembers              |
| `applications/`   | Applications / LLM Proxy | ApplicationsList, ApplicationDetail（含 6 個 tab）, DeploymentSelector |
| `profiles/`       | Profiles (Policy)        | ProfilesList, RateLimitPolicyModal, GuardrailPolicyModal           |
| `credentials/`    | Credentials              | CredentialsList, CreateCredentialModal, RotateCredentialModal      |
| `identity/`       | Identity                 | IdentityList, OidcSettingsSection                                  |
| `fleet/`          | Fleet                    | FleetOverview, FleetAgentTable, FleetAgentDetail, DeployAppModal   |
| `resources/`      | Resources                | ResourcesPage, GroupQuotasView, NodeAllocationsView                |
| `images/`         | Images                   | ImagesPage, RepositoryList, TagList                                |
| `models/`         | Models                   | ModelsPage, CatalogModelDetail, CreateLLMProxyModal                |
| `audit/`          | Audit Log                | AuditLog, AuditFilters                                             |
| `runtime/`        | Runtime Events           | RuntimeEvents                                                      |
| `marketplace/`    | Marketplace              | MarketplacePage, PluginDetailModal, InstallPluginModal             |
| `settings/`       | Settings                 | SettingsPage, RoleSimulationSection, TenantsFeatureFlagsSection    |
| `my-deployments/` | My Deployments           | MyDeploymentsPage, MyDeploymentCard                                |
| `keys/`           | Key Distribution         | KeyDistributionDashboard                                           |
| `onboarding/`     | Customer Onboarding      | CustomerOnboardingPage, handoverTemplate                           |
| `app-launcher/`   | App Launchers            | AppLauncher                                                        |
| `usage/`          | Usage Dashboard          | UsageDashboard                                                     |
| `poc/`            | POC（system_admin only）   | DesktopMonitor                                                     |


---

## Config 目錄


| 檔案                | 說明                                                                                                                               |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `api.ts`          | 組裝所有 API base URL（`iamUrl`, `auditUrl`, `fleetUrl`…）。支援 `VITE_API_URL` 環境變數，由 nginx `sub_filter` 在 runtime 置換，不是只在 build time 決定 |
| `brandPresets.ts` | 預設品牌主題（顏色、字型）                                                                                                                    |
| `locales.ts`      | i18n 字串                                                                                                                          |


## Constants 目錄與 Mock Data 降級

`constants/mockData.ts` 存放 Audit / Runtime 的假資料。當後端 Audit service 不可用時（SCR tier 沒有 audit container），`DemoDataBadge` 元件會出現在頁面上，提示目前顯示的是示範資料。

```
Audit service 不可用
  → useDataFetch() 回傳 error
  → 頁面 fallback 到 constants/mockData.ts 的靜態資料
  → 顯示 <DemoDataBadge />（黃色標籤，提示「Demo Data」）
```

這個 fallback 是刻意設計的降級行為，不是 bug。本地開發時沒啟動 audit container 會常見到這個標籤，正常。

---

## Design System 規則

所有 UI 改動前先讀 `frontend/console-app/design-system/Design.md`。

**黃金法則（違反即 bug）**：

```css
/* ✅ 正確 */
color: var(--color-primary-600);
padding: var(--spacing-4);
border-radius: var(--radius-md);

/* ❌ 錯誤 */
color: #2563eb;
padding: 16px;
border-radius: 8px;
```

字級用 `.text-h1` ~ `.text-h4`（標題）、`.text-b1` ~ `.text-b3`（內文）CSS class，不要 inline `font-size`。

`cn()` helper（`lib/utils.ts`）合併 Tailwind class：

```typescript
import { cn } from '@/lib/utils';
<div className={cn('base-class', isActive && 'active-class', className)} />
```

---

## TypeScript 規則

- 新增檔案一律 `.ts` / `.tsx`，CI 有 `frontend-ts-gate` 會擋 `.js` / `.jsx`
- `tsconfig.json` 的 `strict: true` 不得關閉
- 不確定的型別用 `unknown`，加 `// TODO: type` 標注
- API response / context 物件必須定義明確 interface，不得用 `{}` 或 `Object`
- path alias：`@/` 等於 `src/`（tsconfig + vite 都設好了）

---

## 測試

框架：Vitest + React Testing Library，環境是 jsdom。

```bash
pnpm test:run src/services/pageCapabilities.test.ts   # 單一檔案
pnpm test:run                                          # 全部
pnpm coverage                                          # 產生 coverage report
```

Mock 慣用寫法：

```typescript
vi.mock('@/services/auth', () => ({
  isAuthenticated: vi.fn(() => true),
  getAuthContext: vi.fn(() => mockAuthContext),
  handle401: vi.fn(() => false),
}))

vi.mock('@/hooks/useApi', () => ({
  useApplications: vi.fn(() => ({ data: [], loading: false, error: null, refresh: vi.fn() })),
}))
```

測試重點覆蓋：auth 狀態轉換、role-based nav 可見性、capability matrix、OIDC logout、component 渲染。

---

## 環境變數


| 變數                            | 用途                             | 設定位置         |
| ----------------------------- | ------------------------------ | ------------ |
| `VITE_PROXY_TARGET`           | dev server 反向代理目標              | `.env.local` |
| `VITE_API_URL`                | API base URL（nginx runtime 置換） | Docker env   |
| `VITE_BASE_PATH`              | Vite base path                 | Docker env   |
| `VITE_OIDC_ENABLED`           | 顯示 SSO 登入按鈕                    | Docker env   |
| `VITE_PASSWORD_LOGIN_ENABLED` | 顯示密碼登入 tab                     | Docker env   |


dev proxy 預設打 `http://localhost:3000`（unified docker mode）。切換到 SCR mode 改成 `http://localhost:8080`。

---

## 加入新功能的標準流程

### 新增一個有 list + detail 的頁面（最常見）

1. `**services/api.ts**` — 加 `listFoo()` / `createFoo()` / `deleteFoo()` 函數
2. `**hooks/useApi.ts**` — 加 `useFoo()` / `useFooMutations()` hook
3. `**services/pageCapabilities.ts**` — 在 `CAPABILITY_MATRIX` 加 `foo` 的每個角色設定
4. `**components/foo/**` — 建資料夾，加 `FooList.tsx` + `FooDetail.tsx` + `index.ts`
5. `**XparseConsole.tsx**` — 加四個東西：
  - `selectedFoo` / `selectedFooName` 兩個 `useState`
  - Sidebar nav item（`setCurrentPage('foo')`）
  - 渲染條件：`{currentPage === 'foo' && currentView === 'list' && <FooList />}`
  - Breadcrumb 條件（複製現有同類結構）

### 新增一個簡單頁面（無 detail）

步驟 1 → 3 → 4（只需 `FooPage.tsx`）→ 5（只需 sidebar + 渲染條件，不需新 state）

---

## 已知技術債


| 項目                    | 說明                                                 | 優先級 |
| --------------------- | -------------------------------------------------- | --- |
| 無 URL routing         | 重新整理回 dashboard、無 deep link、Back 鍵無效               | 中   |
| XparseConsole.tsx 過大  | 2000 行，每個新 detail view 都加在這裡                       | 中   |
| 每次導航重新 fetch          | 無頁面間 cache，切回來的頁面重新打 API                           | 低   |
| 淺色 design token drift | `src/index.css` 的 50/100/200 色階與 design-system 不一致 | 低   |


修法方向：URL routing 加 react-router v6（不換 Next.js，這個 app 不需要 SSR）。