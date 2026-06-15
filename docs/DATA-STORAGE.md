# 資料保存

## 模式

| 模式 | 操作 metadata | IP/時間 | 文字 | 加密口令 | 圖片檔案 |
| --- | --- | --- | --- | --- | --- |
| `off` | 否 | 否 | 否 | 否 | 否 |
| `metadata` | 是 | 是 | 依設定 | 是 | 否 |
| `full` | 是 | 是 | 依設定 | 是 | 是 |

`retention_days: null` 表示永久保存。目前版本不會自動清理；管理員可在
管理頁刪除單筆紀錄，系統會留下不含原內容的刪除事件。

## SQLite schema

- `audit_records`：請求、IP、User-Agent、輸入 metadata、參數、結果與加密口令。
- `artifacts`：檔案角色、原始名稱、UUID 保存路徑、MIME、大小與 SHA-256。
- `admin_events`：登入、查看、下載、揭露及刪除事件。

資料庫啟用 foreign keys 與 WAL。刪除 `audit_records` 時，其 artifact
索引會 cascade 刪除；應用程式再刪除磁碟檔案。

## 目錄

```text
/data/
  watermark.sqlite3
  watermark.sqlite3-wal
  watermark.sqlite3-shm
  artifacts/
    <audit UUID>/
      <artifact UUID>.png
```

原始檔名只存在 SQLite，不用來建立路徑，以防止 path traversal。

## 容量規劃

`full` 模式每次嵌入通常保存原圖、浮水印原圖、預處理浮水印及輸出。
估算空間時至少以每日上傳總量的 2.5 至 4 倍計算，再加上備份。永久保存
必須監控 volume 容量，建議在 70% 與 85% 設定告警。

## 隱私注意

目前公開頁依需求不顯示保存政策或同意欄位。`metadata` 與 `full` 可能
永久保存 IP、完整浮水印文字、上傳內容及可還原口令。部署者必須自行確認
適用法規、組織政策、告知義務與存取授權；若無法滿足，應使用 `off`。
