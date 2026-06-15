# 維護手冊

本文件是 Blindmark Studio 的日常維運與交接依據。正式變更前應先在備份
資料上演練，並把操作結果記錄到組織的變更單。

## 系統元件與啟動順序

1. 掛載 `/data` 持久化 volume 與唯讀 `config.yaml`。
2. 注入 AES 主金鑰、管理帳密、JWT secret 與 CORS origins。
3. 啟動 backend；初始化 SQLite、WAL 與必要 schema。
4. backend `/healthz` 通過後啟動 frontend。
5. frontend entrypoint 依 `API_BASE_URL` 產生 runtime `config.js`。

後端只提供 API，不提供業務 HTML。前端故障時 Swagger 仍可獨立測試；
後端故障時前端右上角會顯示 API 離線。

## 設定與環境變數

`config.yaml`：

- `storage.mode`：`off`、`metadata`、`full`。
- `storage.root`：artifact 根目錄。
- `storage.retention_days`：`null` 代表永久保存；目前無自動清理工作。
- `audit.trusted_proxies`：可提供真實 IP header 的 CIDR。
- `audit.store_watermark_text`：是否保存嵌入文字。
- `audit.store_extracted_text`：是否保存解碼文字。
- `audit.store_passphrases`：`encrypted` 或 `none`。
- `limits.max_upload_bytes`：單檔上限。
- `limits.max_pixels`：解碼後像素上限。
- `limits.max_concurrent_jobs`：CPU 浮水印同時工作數。
- `database_path`：SQLite 路徑。

環境變數：

- `WATERMARK_CONFIG`：設定檔路徑。
- `STORAGE_MODE`、`STORAGE_ROOT`：覆寫保存設定。
- `WM_MASTER_KEYS`：`{"key-id":"base64url..."}`，每把解碼後必須為 32 bytes。
- `WM_ACTIVE_KEY_ID`：新紀錄使用的 key ID。
- `ADMIN_USERNAME`：管理員帳號。
- `ADMIN_PASSWORD_HASH`：建議的 Argon2 hash。
- `ADMIN_PASSWORD`：啟動時在記憶體產生 Argon2 hash 的替代方式。
- `JWT_SECRET`、`JWT_TTL_MINUTES`：管理 token。
- `ALLOWED_ORIGINS`：逗號分隔 CORS origins。
- `API_BASE_URL`：前端呼叫的 backend base URL。

正式環境不得提交 `.env`、`config.yaml`、主金鑰、SQLite 或 artifacts。

## 資料庫 migration 與版本升級

目前 schema 由 `backend/app/database.py` 的 idempotent DDL 建立。新增欄位時：

1. 為 schema 建立明確 migration 編號與可重複執行的 SQL。
2. 先備份 SQLite。
3. 在 transaction 中執行 migration。
4. 記錄 schema version，不要刪除既有欄位。
5. 新程式必須能處理 migration 前的 null/default 值。
6. CI 增加「舊 schema 升級到最新」測試。

若變更不可逆，release notes 必須註明回滾只能還原升級前備份。

## 主金鑰備份與輪替

`WM_MASTER_KEYS` 可同時放多把 key，資料列會保存自己的 key ID。

輪替：

1. 產生新的 32-byte key，使用新的 key ID。
2. 將新舊 key 同時放入 `WM_MASTER_KEYS`。
3. 把 `WM_ACTIVE_KEY_ID` 改為新 ID 並重啟。
4. 建立測試紀錄並確認可揭露。
5. 抽查舊紀錄仍可揭露。

除非已重新加密所有舊資料或確認其全部刪除，否則不可移除舊 key。主金鑰
備份與 SQLite/artifacts 備份分開保存，並定期演練還原。

## SQLite 與檔案一致性

每週或大量刪除後執行：

```sql
PRAGMA integrity_check;
PRAGMA foreign_key_check;
```

一致性檢查工具應逐筆確認：

- `artifacts.stored_path` 位於設定的 storage root。
- 檔案存在、大小相同且 SHA-256 相符。
- 磁碟上沒有不屬於任何 `artifacts` row 的 UUID 檔案。

發現 orphan file 時先隔離，不要直接刪除；確認備份與管理事件後再處理。

## 備份、還原與災難復原演練

至少備份：

- SQLite 一致性 snapshot。
- 完整 artifacts。
- 所有歷史 AES 主金鑰。
- 實際部署的 `config.yaml`、image tag 與版本。

每季在隔離環境演練一次：

1. 從零建立服務。
2. 還原資料庫、artifacts 與 keys。
3. 執行 integrity 與 SHA-256 檢查。
4. 登入管理頁並下載隨機 artifacts。
5. 揭露不同 key ID 的口令。
6. 進行文字與圖片的新資料往返測試。

## 常見錯誤與診斷

### API 無法啟動

- `WM_MASTER_KEYS ... required`：保存模式需要有效主金鑰與 active key ID。
- SQLite permission denied：確認 backend UID 10001 可寫 `/data`。
- CORS：比對瀏覽器 origin 與 `ALLOWED_ORIGINS`，包含 scheme 與 port。

### 解碼失敗

- 確認口令完全相同。
- 確認圖片沒有被 JPEG 重壓、裁切、縮放或套用濾鏡。
- 上游 legacy 圖片必須輸入正確 bit 長度或圖片尺寸與兩個 seed。

### 保存資料未出現

- 檢查 `/api/v1/capabilities` 的 `storage_mode`。
- `metadata` 不會建立 artifacts。
- 查看 backend 日誌中的 request ID，但日誌不得包含口令或內容。

### IP 不正確

- 直接連線時只記錄 socket IP。
- proxy IP 必須落在 `trusted_proxies` 才會讀取 forwarded header。
- 不可為了方便信任 `0.0.0.0/0`。

日誌：

```bash
docker compose logs -f --tail=200 backend
docker compose logs -f --tail=200 frontend
```

## 升級 blind-watermark

1. 閱讀上游 changelog、commit 與 Python/NumPy/OpenCV 相容性。
2. 在分支更新 `backend/requirements.txt` 的固定版本。
3. 執行本站文字、Unicode、圖片、alpha 與 legacy fixture 測試。
4. 使用舊版本產生圖片，以新版本解碼；再反向驗證。
5. 比較輸出失真、處理時間與記憶體。
6. 若不相容，增加本站封包 version，不可悄悄改變既有解碼語意。
7. 更新 `NOTICE.md`、文件與 changelog。

## OpenAPI 與前端型別

後端 API 改動後：

```powershell
cd backend
python scripts/export_openapi.py
cd ..\frontend
pnpm generate:api
pnpm build
```

提交 `openapi.json` 與 `frontend/src/api/schema.d.ts`。CI 會重新產生並以
`git diff --exit-code` 檢查不同步。

## 發行、回滾與安全清單

發行前：

- 後端 lint、mypy、pytest 全部通過。
- 前端 lint、Vitest、TypeScript build 全部通過。
- OpenAPI 無未提交差異。
- Docker images 可建置，Trivy 與 Gitleaks 無阻擋項目。
- `.env`、SQLite、artifacts、keys 未進入 Git。
- 備份與回滾 image tag 已確認。
- `CHANGELOG.md` 已移動內容到實際版本與日期。

建立 `vX.Y.Z` tag 後，GitHub workflow 會建置 images、保存 artifacts 並建立
Release，但不會推送到 registry。

回滾：

1. 停止新版本寫入。
2. 若 schema 相容，切回上一個 image tag。
3. 若 schema 不相容，還原升級前 SQLite 與 artifacts snapshot。
4. 保留所有主金鑰。
5. 驗證健康、管理登入、下載、揭露與往返。

## 隱私與治理

預設範例會永久保存完整圖片、IP、文字與可還原口令，而公開頁不顯示告知。
這是高風險設定。維運者必須自行完成法規審查、權限控管、HTTPS、備份加密、
磁碟監控與存取稽核；若無明確需求，應將 `storage.mode` 改為 `off`。
