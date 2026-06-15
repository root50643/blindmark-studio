from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import AppConfig, AuditConfig, LimitsConfig, StorageConfig
from app.main import create_app


@pytest.fixture
def config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        storage=StorageConfig(mode="metadata", root=tmp_path / "artifacts"),
        audit=AuditConfig(store_passphrases="encrypted"),
        limits=LimitsConfig(max_upload_bytes=2_000_000, max_pixels=2_000_000),
        database_path=tmp_path / "db.sqlite3",
        allowed_origins=("http://localhost:3000",),
        admin_username="admin",
        admin_password="test-password",
        admin_password_hash=None,
        jwt_secret="test-secret",
        jwt_ttl_minutes=30,
        master_keys={"v1": b"x" * 32},
        active_key_id="v1",
    )


@pytest.fixture
def client(config: AppConfig) -> TestClient:
    return TestClient(create_app(config))
