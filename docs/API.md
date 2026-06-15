# REST API

完整且可互動的契約位於 `/docs`，機器可讀版本為 `/openapi.json`。
所有業務 API 使用 `/api/v1` 前綴。

## 公開 API

### 查詢能力

```http
GET /api/v1/capabilities
```

回傳格式、上傳限制、像素限制、保存模式與 legacy 支援狀態。

### 圖片浮水印預覽

```bash
curl -X POST http://localhost:8000/api/v1/watermark-previews \
  -F "cover_image=@cover.png" \
  -F "watermark_image=@logo.png"
```

回傳黑白化後的 Data URL、尺寸、是否縮放及使用容量。

### 嵌入

```bash
curl -o watermarked.png \
  -X POST http://localhost:8000/api/v1/watermarked-images \
  -F "cover_image=@cover.png" \
  -F "watermark_type=text" \
  -F "watermark_text=機密文件 A-001" \
  -F "passphrase=example"
```

圖片模式將 `watermark_type` 改為 `image`，並加上
`watermark_image=@logo.png`。

### 本站格式解碼

```bash
curl -X POST http://localhost:8000/api/v1/watermark-extractions \
  -F "encoded_image=@watermarked.png" \
  -F "passphrase=example"
```

回傳：

```json
{"kind":"text","text":"機密文件 A-001"}
```

或：

```json
{"kind":"image","image_data_url":"data:image/png;base64,...","width":64,"height":32}
```

### Legacy 解碼

```bash
curl -X POST http://localhost:8000/api/v1/legacy-watermark-extractions \
  -F "encoded_image=@legacy.png" \
  -F "mode=text" \
  -F "password_img=1" \
  -F "password_wm=1" \
  -F "bit_length=120"
```

## 錯誤格式

錯誤回傳 `application/problem+json`：

```json
{
  "type": "https://example.invalid/problems/invalid_image",
  "title": "圖片無效",
  "status": 400,
  "detail": "無法讀取圖片或圖片格式不受支援。",
  "code": "invalid_image",
  "request_id": "..."
}
```

常用代碼包括 `invalid_image`、`upload_size_limit_exceeded`、
`image_pixel_limit_exceeded`、`watermark_capacity_exceeded`、
`watermark_extraction_failed` 及 `validation_error`。

## 管理 API

先呼叫 `POST /api/v1/admin/auth/login` 取得 Bearer JWT。其餘管理端點可：

- 分頁與搜尋 `/admin/audit-records`
- 讀取單筆紀錄與 artifacts
- 下載 artifact
- 明確揭露加密口令
- 提供刪除原因後刪除紀錄

JWT 預設 30 分鐘失效，重新整理管理頁後不保留。
