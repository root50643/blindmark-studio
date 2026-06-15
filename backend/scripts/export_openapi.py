from __future__ import annotations

import json
from pathlib import Path

from app.config import AppConfig, AuditConfig, LimitsConfig, StorageConfig
from app.main import create_app

root = Path(__file__).resolve().parents[2]
temporary = root / ".openapi"
config = AppConfig(
    storage=StorageConfig(mode="off", root=temporary),
    audit=AuditConfig(store_passphrases="none"),
    limits=LimitsConfig(),
    database_path=temporary / "openapi.sqlite3",
    allowed_origins=("http://localhost:3000",),
    admin_username="admin",
    admin_password="unused",
    admin_password_hash=None,
    jwt_secret="unused",
    jwt_ttl_minutes=30,
    master_keys={},
    active_key_id=None,
)
schema = create_app(config).openapi()
(root / "openapi.json").write_text(
    json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
