# 系統架構

## 元件

- **React frontend**：靜態網站，由 Nginx 提供，runtime `config.js` 決定 API 位址。
- **FastAPI backend**：唯一業務入口，提供 `/api/v1` REST API、OpenAPI 與管理驗證。
- **Watermark service**：正規化圖片、封裝資料並呼叫 `blind-watermark 0.4.4`。
- **Audit service**：依保存模式寫入 SQLite 與 artifacts 目錄。
- **SQLite WAL**：保存操作資訊、artifact 索引及不可刪除的管理事件。

前端不直接讀取 SQLite 或 artifacts。保存檔只能透過需要管理 JWT 的 API 下載。

## 資料流

1. 瀏覽器以 `multipart/form-data` 上傳圖片。
2. 後端驗證實際圖片格式、位元組上限、像素上限及 EXIF 方向。
3. 浮水印工作進入全域 semaphore，避免 CPU 工作同時耗盡主機。
4. 後端回傳 PNG 或 JSON。
5. 稽核服務依 `storage.mode` 寫入 metadata 與 artifacts。

## 自描述封包

本站使用 bit 模式，不使用上游的文字序列化。封包採 big-endian：

| 欄位 | 大小 | 說明 |
| --- | ---: | --- |
| magic | 4 bytes | `BWV1` |
| version | 1 byte | 目前為 `1` |
| kind | 1 byte | `1=text`、`2=image` |
| flags | 2 bytes | 保留 |
| width | 4 bytes | 圖片浮水印寬度 |
| height | 4 bytes | 圖片浮水印高度 |
| payload length | 4 bytes | bytes |
| CRC32 | 4 bytes | payload 校驗 |
| payload | variable | UTF-8 或 packed monochrome bitmap |

封包補齊至 256 到 131,072 bits 的 2 次方級距。解碼只從圖片擷取一次
raw blocks，再依級距重組、解除 watermark seed 排列並以 magic 和 CRC32
驗證。這使本站產生的圖片不需要外部保存 `wm_shape`。

## 安全邊界

- 浮水印口令是 seed，不是端對端內容加密。
- 保存的口令才使用 AES-256-GCM，主金鑰不進入設定檔或資料庫。
- CORS 不使用 cookies；管理 JWT 僅保存在 React 記憶體。
- 僅 `trusted_proxies` 來源可影響 `Forwarded` 或 `X-Forwarded-For`。
- artifacts 使用 UUID 檔名且不掛載為公開靜態目錄。
