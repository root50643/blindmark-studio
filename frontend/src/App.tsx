import { useEffect, useState } from "react";
import { api } from "./api/client";
import { AdminApp } from "./components/AdminApp";
import { DecodePanel } from "./components/DecodePanel";
import { EmbedPanel } from "./components/EmbedPanel";

type Tab = "embed" | "decode";

export function App() {
  const [tab, setTab] = useState<Tab>("embed");
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);

  useEffect(() => {
    api.capabilities().then(() => setApiOnline(true)).catch(() => setApiOnline(false));
  }, []);

  if (window.location.pathname.startsWith("/admin")) {
    return <AdminApp />;
  }

  return (
    <div className="site-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Blindmark Studio 首頁">
          <span className="brand-mark"><i>B</i></span>
          <span>
            <strong>Blindmark</strong>
            <small>STUDIO</small>
          </span>
        </a>
        <div className={`api-status ${apiOnline === false ? "offline" : ""}`}>
          <span />
          {apiOnline === null ? "連線中" : apiOnline ? "API 就緒" : "API 離線"}
        </div>
      </header>

      <main>
        <section className="hero">
          <p className="eyebrow">DWT · DCT · SVD</p>
          <h1>看不見的標記，<br />清楚可驗證。</h1>
          <p className="hero-copy">
            在圖片中嵌入文字或圖像，不改變觀看體驗。需要時，再用同一把口令取回。
          </p>
        </section>

        <section className="workspace">
          <div className="tabs" role="tablist">
            <button
              className={tab === "embed" ? "active" : ""}
              onClick={() => setTab("embed")}
              role="tab"
            >
              嵌入浮水印
            </button>
            <button
              className={tab === "decode" ? "active" : ""}
              onClick={() => setTab("decode")}
              role="tab"
            >
              解碼浮水印
            </button>
          </div>
          {tab === "embed" ? <EmbedPanel /> : <DecodePanel />}
        </section>
      </main>

      <footer>
        <span>輸出採用無損 PNG</span>
        <a href="/admin">管理紀錄</a>
      </footer>
    </div>
  );
}
