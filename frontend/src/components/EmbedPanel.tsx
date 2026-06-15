import { type FormEvent, useEffect, useState } from "react";
import { ApiError, api, downloadBlob, type PreviewResult } from "../api/client";
import { FileField } from "./FileField";

export function EmbedPanel() {
  const [cover, setCover] = useState<File | null>(null);
  const [kind, setKind] = useState<"text" | "image">("text");
  const [text, setText] = useState("");
  const [watermarkImage, setWatermarkImage] = useState<File | null>(null);
  const [passphrase, setPassphrase] = useState("");
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [outputUrl, setOutputUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setPreview(null);
  }, [cover, watermarkImage]);

  useEffect(
    () => () => {
      if (outputUrl) URL.revokeObjectURL(outputUrl);
    },
    [outputUrl],
  );

  async function previewWatermark() {
    if (!cover || !watermarkImage) return;
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("cover_image", cover);
      form.append("watermark_image", watermarkImage);
      setPreview(await api.preview(form));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "無法建立預覽");
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!cover) return;
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("cover_image", cover);
      form.append("watermark_type", kind);
      form.append("watermark_text", text);
      form.append("passphrase", passphrase);
      if (watermarkImage) form.append("watermark_image", watermarkImage);
      const blob = await api.embed(form);
      if (outputUrl) URL.revokeObjectURL(outputUrl);
      setOutputUrl(URL.createObjectURL(blob));
      downloadBlob(blob, "watermarked.png");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "嵌入浮水印失敗");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="panel-grid" onSubmit={submit}>
      <div className="form-column">
        <FileField
          label="01 · 原始圖片"
          hint="PNG、JPEG 或 WebP"
          file={cover}
          onChange={setCover}
        />

        <div className="form-section">
          <label className="field-label">02 · 浮水印內容</label>
          <div className="segmented">
            <button
              type="button"
              className={kind === "text" ? "active" : ""}
              onClick={() => setKind("text")}
            >
              文字
            </button>
            <button
              type="button"
              className={kind === "image" ? "active" : ""}
              onClick={() => setKind("image")}
            >
              圖片
            </button>
          </div>
          {kind === "text" ? (
            <textarea
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="輸入要藏進圖片裡的文字..."
              rows={5}
              required
            />
          ) : (
            <>
              <FileField
                label=""
                hint="將自動轉成黑白並縮放"
                file={watermarkImage}
                onChange={setWatermarkImage}
              />
              <button
                className="secondary-button preview-button"
                type="button"
                disabled={!cover || !watermarkImage || busy}
                onClick={previewWatermark}
              >
                產生實際浮水印預覽
              </button>
            </>
          )}
        </div>

        <div className="form-section">
          <label className="field-label" htmlFor="embed-passphrase">
            03 · 解碼口令（選填）
          </label>
          <input
            id="embed-passphrase"
            type="password"
            value={passphrase}
            onChange={(event) => setPassphrase(event.target.value)}
            placeholder="留空使用公開預設值"
          />
          <p className="field-help">此口令是解碼金鑰，不等同於內容加密。</p>
        </div>

        {error && <div className="error-message">{error}</div>}
        <button
          className="primary-button"
          disabled={!cover || busy || (kind === "image" ? !watermarkImage : !text)}
        >
          {busy ? "處理中..." : "嵌入並下載 PNG"}
        </button>
      </div>

      <aside className="result-column">
        <span className="result-label">OUTPUT PREVIEW</span>
        {outputUrl ? (
          <img className="result-image" src={outputUrl} alt="嵌入浮水印後的輸出" />
        ) : preview ? (
          <div className="preview-card">
            <img src={preview.image_data_url} alt="實際浮水印預覽" />
            <dl>
              <div>
                <dt>尺寸</dt>
                <dd>{preview.width} × {preview.height}</dd>
              </div>
              <div>
                <dt>處理</dt>
                <dd>{preview.resized ? "已等比例縮小" : "保留原尺寸"}</dd>
              </div>
              <div>
                <dt>容量</dt>
                <dd>{preview.used_bits.toLocaleString()} bits</dd>
              </div>
            </dl>
          </div>
        ) : (
          <div className="empty-result">
            <span className="scan-lines" />
            <p>完成後的圖片會顯示在這裡</p>
          </div>
        )}
      </aside>
    </form>
  );
}
