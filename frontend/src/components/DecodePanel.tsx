import { type FormEvent, useState } from "react";
import { ApiError, api, type ExtractionResult } from "../api/client";
import { FileField } from "./FileField";

export function DecodePanel() {
  const [image, setImage] = useState<File | null>(null);
  const [passphrase, setPassphrase] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const [legacyMode, setLegacyMode] = useState<"text" | "image">("text");
  const [passwordImg, setPasswordImg] = useState("1");
  const [passwordWm, setPasswordWm] = useState("1");
  const [bitLength, setBitLength] = useState("");
  const [width, setWidth] = useState("");
  const [height, setHeight] = useState("");
  const [result, setResult] = useState<ExtractionResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!image) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const form = new FormData();
      form.append("encoded_image", image);
      if (advanced) {
        form.append("mode", legacyMode);
        form.append("password_img", passwordImg);
        form.append("password_wm", passwordWm);
        if (bitLength) form.append("bit_length", bitLength);
        if (width) form.append("width", width);
        if (height) form.append("height", height);
      } else {
        form.append("passphrase", passphrase);
      }
      setResult(await api.extract(form, advanced));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "解碼失敗");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="panel-grid" onSubmit={submit}>
      <div className="form-column">
        <FileField
          label="01 · 待解碼圖片"
          hint="上傳本站或 blind-watermark 產生的圖片"
          file={image}
          onChange={setImage}
        />
        {!advanced && (
          <div className="form-section">
            <label className="field-label" htmlFor="decode-passphrase">
              02 · 解碼口令（選填）
            </label>
            <input
              id="decode-passphrase"
              type="password"
              value={passphrase}
              onChange={(event) => setPassphrase(event.target.value)}
              placeholder="需與嵌入時相同"
            />
          </div>
        )}

        <button
          className="text-button"
          type="button"
          onClick={() => setAdvanced(!advanced)}
        >
          {advanced ? "返回本站自動解碼" : "開啟原專案進階解碼"} <span>↗</span>
        </button>

        {advanced && (
          <div className="advanced-box">
            <div className="segmented">
              <button
                type="button"
                className={legacyMode === "text" ? "active" : ""}
                onClick={() => setLegacyMode("text")}
              >
                文字
              </button>
              <button
                type="button"
                className={legacyMode === "image" ? "active" : ""}
                onClick={() => setLegacyMode("image")}
              >
                圖片
              </button>
            </div>
            <div className="input-row">
              <label>
                Image seed
                <input
                  type="number"
                  value={passwordImg}
                  onChange={(event) => setPasswordImg(event.target.value)}
                />
              </label>
              <label>
                Watermark seed
                <input
                  type="number"
                  value={passwordWm}
                  onChange={(event) => setPasswordWm(event.target.value)}
                />
              </label>
            </div>
            {legacyMode === "text" ? (
              <label>
                文字 bit 長度
                <input
                  type="number"
                  value={bitLength}
                  onChange={(event) => setBitLength(event.target.value)}
                  required
                />
              </label>
            ) : (
              <div className="input-row">
                <label>
                  寬度
                  <input
                    type="number"
                    value={width}
                    onChange={(event) => setWidth(event.target.value)}
                    required
                  />
                </label>
                <label>
                  高度
                  <input
                    type="number"
                    value={height}
                    onChange={(event) => setHeight(event.target.value)}
                    required
                  />
                </label>
              </div>
            )}
          </div>
        )}

        {error && <div className="error-message">{error}</div>}
        <button className="primary-button" disabled={!image || busy}>
          {busy ? "解碼中..." : "開始解碼"}
        </button>
      </div>

      <aside className="result-column">
        <span className="result-label">DECODED CONTENT</span>
        {result?.kind === "text" ? (
          <div className="decoded-text">
            <p>{result.text}</p>
            <button
              type="button"
              className="secondary-button"
              onClick={() => navigator.clipboard.writeText(result.text ?? "")}
            >
              複製文字
            </button>
          </div>
        ) : result?.image_data_url ? (
          <div className="preview-card">
            <img src={result.image_data_url} alt="解碼出的浮水印" />
            <a
              className="secondary-button link-button"
              href={result.image_data_url}
              download="extracted-watermark.png"
            >
              下載圖片
            </a>
          </div>
        ) : (
          <div className="empty-result">
            <span className="scan-lines" />
            <p>解碼內容會顯示在這裡</p>
          </div>
        )}
      </aside>
    </form>
  );
}
