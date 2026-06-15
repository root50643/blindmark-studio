import { type FormEvent, useCallback, useEffect, useState } from "react";
import { ApiError, api, type Artifact, type AuditRecord } from "../api/client";

export function AdminApp() {
  const [token, setToken] = useState("");
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [records, setRecords] = useState<AuditRecord[]>([]);
  const [selected, setSelected] = useState<AuditRecord | null>(null);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  async function login(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const result = await api.login(username, password);
      setToken(result.access_token);
      setPassword("");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "登入失敗");
    }
  }

  const loadRecords = useCallback(async (search: string) => {
    if (!token) return;
    try {
      const result = await api.records(token, search);
      setRecords(result.items);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "讀取紀錄失敗");
    }
  }, [token]);

  useEffect(() => {
    void loadRecords("");
  }, [loadRecords]);

  async function openRecord(id: string) {
    const [record, files] = await Promise.all([
      api.record(token, id),
      api.artifacts(token, id),
    ]);
    setSelected(record);
    setArtifacts(files);
  }

  async function reveal() {
    if (!selected) return;
    const value = await api.revealPassphrase(token, selected.id);
    window.alert(value ? `口令：${value}` : "此紀錄沒有保存口令。");
  }

  async function remove() {
    if (!selected) return;
    const reason = window.prompt("請輸入刪除原因（至少 3 個字元）：");
    if (!reason) return;
    await api.deleteRecord(token, selected.id, reason);
    setSelected(null);
    setArtifacts([]);
    await loadRecords(query);
  }

  if (!token) {
    return (
      <main className="admin-login">
        <form onSubmit={login}>
          <a className="brand" href="/">
            <span className="brand-mark"><i>B</i></span>
            <strong>Blindmark Admin</strong>
          </a>
          <h1>管理紀錄</h1>
          <p>登入後可查看保存內容、下載檔案及揭露加密口令。</p>
          <label>
            帳號
            <input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
            />
          </label>
          <label>
            密碼
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          {error && <div className="error-message">{error}</div>}
          <button className="primary-button">登入</button>
        </form>
      </main>
    );
  }

  return (
    <div className="admin-shell">
      <header className="topbar">
        <a className="brand" href="/">
          <span className="brand-mark"><i>B</i></span>
          <strong>Blindmark Admin</strong>
        </a>
        <button className="secondary-button" onClick={() => setToken("")}>
          登出
        </button>
      </header>
      <div className="admin-toolbar">
        <h1>操作紀錄 <span>{records.length}</span></h1>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void loadRecords(query);
          }}
        >
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜尋 request ID 或 IP"
          />
          <button className="secondary-button">搜尋</button>
        </form>
      </div>
      <div className="admin-layout">
        <div className="record-list">
          {records.map((record) => (
            <button
              key={record.id}
              className={selected?.id === record.id ? "selected" : ""}
              onClick={() => void openRecord(record.id)}
            >
              <span className={`status-dot ${record.status}`} />
              <span>
                <strong>{record.operation}</strong>
                <small>{new Date(record.created_at).toLocaleString()}</small>
              </span>
              <span>
                <code>{record.client_ip}</code>
                <small>{record.duration_ms ?? "-"} ms</small>
              </span>
            </button>
          ))}
        </div>
        <aside className="record-detail">
          {selected ? (
            <>
              <div className="detail-heading">
                <div>
                  <span className="eyebrow">AUDIT RECORD</span>
                  <h2>{selected.operation}</h2>
                </div>
                <span className={`status-pill ${selected.status}`}>
                  {selected.status}
                </span>
              </div>
              <dl className="detail-grid">
                <div>
                  <dt>Request ID</dt>
                  <dd><code>{selected.request_id}</code></dd>
                </div>
                <div><dt>用戶端 IP</dt><dd>{selected.client_ip}</dd></div>
                <div><dt>HTTP</dt><dd>{selected.http_status}</dd></div>
                <div><dt>耗時</dt><dd>{selected.duration_ms} ms</dd></div>
              </dl>
              <h3>參數</h3>
              <pre>{JSON.stringify(selected.parameters, null, 2)}</pre>
              <h3>保存檔案</h3>
              <div className="artifact-list">
                {artifacts.length ? (
                  artifacts.map((artifact) => (
                    <button
                      key={artifact.id}
                      onClick={() => void api.downloadArtifact(token, artifact)}
                    >
                      <span>{artifact.role}</span>
                      <strong>{artifact.original_name}</strong>
                      <small>{artifact.size.toLocaleString()} bytes</small>
                    </button>
                  ))
                ) : (
                  <p>此模式沒有保存二進位檔案。</p>
                )}
              </div>
              <div className="danger-actions">
                <button className="secondary-button" onClick={() => void reveal()}>
                  揭露口令
                </button>
                <button className="danger-button" onClick={() => void remove()}>
                  刪除紀錄
                </button>
              </div>
            </>
          ) : (
            <div className="empty-result"><p>選取左側紀錄查看詳細資訊</p></div>
          )}
        </aside>
      </div>
    </div>
  );
}
