import ipaddress
from dataclasses import replace
from pathlib import Path

from starlette.requests import Request

from app.audit import ArtifactInput, AuditService, request_network
from app.config import AppConfig, AuditConfig, LimitsConfig, StorageConfig
from app.database import Database


def _config(tmp_path: Path, mode: str) -> AppConfig:
    return AppConfig(
        storage=StorageConfig(mode=mode, root=tmp_path / mode),
        audit=AuditConfig(store_passphrases="encrypted"),
        limits=LimitsConfig(),
        database_path=tmp_path / f"{mode}.sqlite3",
        allowed_origins=(),
        admin_username="admin",
        admin_password="password",
        admin_password_hash=None,
        jwt_secret="secret",
        jwt_ttl_minutes=30,
        master_keys={"v1": b"a" * 32},
        active_key_id="v1",
    )


def test_storage_modes_create_expected_artifacts(tmp_path, client):
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
        }
    )
    for mode, expected in (("off", 0), ("metadata", 0), ("full", 1)):
        config = _config(tmp_path, mode)
        database = Database(config.database_path)
        service = AuditService(config, database)
        service.record(
            request=request,
            request_id=f"request-{mode}",
            operation="test",
            created_at="2026-01-01T00:00:00+00:00",
            completed_at="2026-01-01T00:00:01+00:00",
            duration_ms=1000,
            status="success",
            http_status=200,
            error_code=None,
            input_files=[],
            parameters={},
            result={},
            passphrase="secret",
            artifacts=[ArtifactInput("input", "test.png", "image/png", b"png")],
        )
        rows = database.fetchall("SELECT * FROM artifacts")
        assert len(rows) == expected
        records = database.fetchall("SELECT * FROM audit_records")
        assert len(records) == (0 if mode == "off" else 1)


def test_forwarded_ip_is_only_used_for_trusted_proxy(tmp_path):
    base = _config(tmp_path, "metadata")
    trusted_config = replace(
        base,
        audit=replace(
            base.audit,
            trusted_proxies=(ipaddress.ip_network("127.0.0.1/32"),),
        ),
    )
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"x-forwarded-for", b"203.0.113.10, 127.0.0.1")],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }
    assert request_network(Request(scope), trusted_config).client_ip == "203.0.113.10"

    scope["client"] = ("10.0.0.2", 1234)
    assert request_network(Request(scope), trusted_config).client_ip == "10.0.0.2"
