from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS audit_records (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    operation TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    client_ip TEXT NOT NULL,
    direct_ip TEXT NOT NULL,
    forwarded_chain_json TEXT NOT NULL,
    user_agent TEXT NOT NULL,
    frontend_version TEXT,
    status TEXT NOT NULL,
    http_status INTEGER,
    error_code TEXT,
    duration_ms INTEGER,
    input_files_json TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    passphrase_key_id TEXT,
    passphrase_nonce TEXT,
    passphrase_ciphertext TEXT
);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    audit_id TEXT NOT NULL REFERENCES audit_records(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    original_name TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    mime TEXT NOT NULL,
    size INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_events (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    admin_username TEXT NOT NULL,
    action TEXT NOT NULL,
    target_id TEXT,
    client_ip TEXT NOT NULL,
    details_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_records(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_operation ON audit_records(operation);
CREATE INDEX IF NOT EXISTS idx_artifacts_audit ON artifacts(audit_id);
CREATE INDEX IF NOT EXISTS idx_admin_events_created ON admin_events(created_at DESC);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        with self._lock, self.connect() as conn:
            conn.execute(sql, params)
            conn.commit()

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute(sql, params).fetchall())

    def transaction(self):
        return self.connect()


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def json_loads(value: str) -> Any:
    return json.loads(value)
