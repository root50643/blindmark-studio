import { useEffect, useRef, useState } from "react";

interface Props {
  label: string;
  hint: string;
  file: File | null;
  onChange: (file: File | null) => void;
}

export function FileField({ label, hint, file, onChange }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);

  useEffect(() => {
    if (!file) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  return (
    <div>
      {label && <label className="field-label">{label}</label>}
      <button
        type="button"
        className={`dropzone ${dragging ? "dragging" : ""}`}
        onClick={() => input.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          onChange(event.dataTransfer.files[0] ?? null);
        }}
      >
        {preview ? (
          <>
            <img src={preview} alt="" />
            <span className="file-name">{file?.name}</span>
          </>
        ) : (
          <>
            <span className="upload-icon">＋</span>
            <strong>拖曳圖片到這裡</strong>
            <span>{hint}</span>
          </>
        )}
      </button>
      <input
        ref={input}
        hidden
        type="file"
        accept="image/png,image/jpeg,image/webp"
        onChange={(event) => onChange(event.target.files?.[0] ?? null)}
      />
    </div>
  );
}
