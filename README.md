# Blindmark Studio

以 REST API 為核心的文字與圖片盲浮水印系統。前端採 React，後端採
FastAPI，演算法使用
[`blind-watermark` 0.4.4](https://github.com/guofei9987/blind_watermark)。

[English summary](README.en.md)

## 功能

- 嵌入 UTF-8 文字或黑白圖片浮水印，輸出無損 PNG。
- 本站格式包含類型、長度、圖片尺寸及 CRC32，可自動解碼。
- 相容原專案文字 bit 長度與圖片尺寸解碼模式。
- 可選解碼口令，穩定衍生上游的兩個 seed。
- `off`、`metadata`、`full` 三種保存模式。
- SQLite WAL 稽核、AES-256-GCM 口令保存、可信代理 IP 判定。
- 受 JWT 保護的管理頁，可查詢、下載、揭露口令及帶原因刪除。
- OpenAPI、Swagger UI、Docker Compose 與 GitHub Actions。

## 快速啟動

需求：Docker Engine 24+ 與 Docker Compose v2。

```powershell
Copy-Item config.example.yaml config.yaml
Copy-Item .env.example .env
```

產生 32-byte 主金鑰並填入 `.env`：

```powershell
python -c "import base64,secrets,json; print(json.dumps({'v1': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()}))"
```

同時替換 `.env` 中的 `ADMIN_PASSWORD` 與 `JWT_SECRET`，再啟動：

```powershell
docker compose up --build
```

- 使用者介面：http://localhost:3000
- 管理介面：http://localhost:3000/admin
- Swagger UI：http://localhost:8000/docs
- OpenAPI：http://localhost:8000/openapi.json

> `config.example.yaml` 預設為 `full` 且永久保存。正式啟動前請先閱讀
> [資料保存說明](docs/DATA-STORAGE.md) 與 [安全政策](SECURITY.md)。

## 本機開發

後端：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
$env:WATERMARK_CONFIG = "..\config.yaml"
uvicorn app.main:create_app --factory --reload --port 8000
```

前端：

```powershell
cd frontend
corepack enable
pnpm install
pnpm dev
```

測試：

```powershell
cd backend
pytest
ruff check .
mypy app

cd ..\frontend
pnpm lint
pnpm test
pnpm build
```

## 設定

非敏感設定放在 `config.yaml`，格式參考
[`config.example.yaml`](config.example.yaml)。敏感值只能放在環境變數或
Docker secrets：

| 變數 | 用途 |
| --- | --- |
| `WM_MASTER_KEYS` | JSON 物件，key ID 對應 Base64URL 32-byte AES key |
| `WM_ACTIVE_KEY_ID` | 新資料使用的 key ID |
| `ADMIN_USERNAME` | 單一管理員帳號 |
| `ADMIN_PASSWORD` / `ADMIN_PASSWORD_HASH` | 管理密碼或預先產生的 Argon2 hash |
| `JWT_SECRET` | 管理 JWT 簽章密鑰 |
| `ALLOWED_ORIGINS` | 逗號分隔的前端 CORS origins |
| `API_BASE_URL` | 前端 runtime API 位址 |

完整維運資訊請見 [維護手冊](docs/MAINTENANCE.md)。

## 專案結構

```text
backend/                 FastAPI、演算法封裝、SQLite 與測試
frontend/                React、管理頁與前端測試
docs/                    架構、API、部署、資料與維護文件
.github/                 CI、Dependabot、Issue 與 PR 模板
compose.yaml             前後端獨立服務
config.example.yaml      可提交的非敏感設定範例
```

## 授權與來源

本專案採 [MIT License](LICENSE)。`blind-watermark` 是獨立的 MIT
第三方依賴，來源與版權資訊列於 [NOTICE.md](NOTICE.md)。
