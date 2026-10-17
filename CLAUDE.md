# CLAUDE.md

這個 repo 是 **Xparse**（企業級 AI 推論編排與治理平台）的設計與開發文件庫，不是程式碼 repo。
Remote：`https://github.com/LeiIeongTam-Peter/xparse-document.git`，唯一分支 `main`。

## Git 規則（必須遵守）

**每次新增、修改、刪除、搬移任何文件後，都要 commit 並 push 到 `main`。** 不需要另外詢問使用者，這已是常態授權。

流程：

```bash
git add -A
git commit -m "docs: <簡述變更>"
git push origin main
```

- 直接在 `main` 上作業，不開 branch、不開 PR。
- 一個任務完成後就 push，不要累積到最後；同一個任務內多個相關檔案可合成一個 commit。
- Commit message 格式：`docs: <變更摘要>`（英文或中文皆可，參考 `git log` 既有風格），結尾加上 attribution 行。
- Push 前先 `git pull --rebase origin main`，避免與其他裝置的變更衝突；若有衝突，停下來告知使用者，不要 force push。
- 絕對不要 `git push --force`、`git reset --hard` 或改寫已 push 的歷史。
- `.DS_Store` 已在 `.gitignore`，不要 commit 系統檔或暫存檔。

## 目錄結構

| 位置 | 內容 |
| --- | --- |
| 根目錄 `*.md` | 各主題的設計文件（`overview.md` 為平台總覽，另有 guardrail、policy、routing、LLM proxy、cost、notification、audit 等） |
| `xparse/` | 各服務模組文件（routing、iam、scheduler、fleet、audit…），`xparse/apis/` 為對應 API 文件 |
| `草案/` | 尚未定案的提案與設計草稿 |
| `進行中/` | 正在進行的工作與 checklist |
| `測試報告/` | 測試結果報告 |
| `部署/` | 部署相關文件 |
| `issues/` | 問題紀錄與調查（檔名常帶日期，如 `*-2026-10-01.md`） |
| `LLM_api-drafts/` | LLM API 相關 issue 草稿 |
| `llm_readiness_audit-evidence/` | `llm_readiness_audit.md` 的佐證資料（JSON、腳本） |
| `frontend/`、`UI/` | 前端與 UI 文件 |

## 撰寫慣例

- 文件以繁體中文（台灣用語）撰寫，技術名詞、程式碼、指令保持英文。
- 修改既有文件時，沿用該文件原有的章節結構與格式，不要大幅改寫無關段落。
- 新文件放到符合性質的資料夾；不確定時放根目錄並在回覆中說明。
- 有日期的紀錄（handoff、issue、報告）使用絕對日期 `YYYY-MM-DD`。
