# 部署、備份與升級

## Docker Compose

1. 複製 `config.example.yaml` 為 `config.yaml`。
2. 複製 `.env.example` 為 `.env` 並替換所有密鑰。
3. 執行 `docker compose config` 確認展開內容。
4. 執行 `docker compose up -d --build`。
5. 檢查 `http://localhost:8000/healthz` 與前端。

前端與後端是不同 origin。`ALLOWED_ORIGINS` 必須精確列出前端 origin，
不可在含管理功能的正式環境設定為 `*`。

## HTTPS

內網正式環境仍應在兩個服務前放置 TLS reverse proxy。若 proxy 要傳遞
真實 IP，必須把 proxy 的 CIDR 加入 `audit.trusted_proxies`；不要信任
整個內網或 `0.0.0.0/0`。

## 備份

先建立 SQLite 一致性備份，再備份 artifacts：

```bash
docker compose exec backend python -c \
  "import sqlite3; s=sqlite3.connect('/data/watermark.sqlite3'); d=sqlite3.connect('/data/backup.sqlite3'); s.backup(d); d.close(); s.close()"
docker run --rm -v watermark_watermark-data:/data -v "$PWD/backup:/backup" \
  alpine tar czf /backup/artifacts.tgz -C /data artifacts backup.sqlite3
```

另外備份所有仍在使用的 `WM_MASTER_KEYS`。沒有舊主金鑰就無法還原既有口令。
主金鑰備份必須與資料備份分開保存。

## 還原

1. 停止 backend。
2. 還原 SQLite 與完整 artifacts 目錄。
3. 還原所有歷史主金鑰及正確 key ID。
4. 執行 `PRAGMA integrity_check`。
5. 抽查 SQLite artifact 路徑、SHA-256 與實際檔案。
6. 啟動服務並測試管理下載與口令揭露。

## 升級與回滾

- 升級前備份資料、主金鑰與目前 image tag。
- 閱讀 `CHANGELOG.md`，先在備份副本執行測試。
- `docker compose build --pull` 後啟動，完成健康與往返測試。
- 回滾時使用先前 image tag；若版本包含不可逆 schema migration，必須同時
  還原升級前資料庫。
