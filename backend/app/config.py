from __future__ import annotations

import base64
import ipaddress
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, cast

import yaml

StorageMode = Literal["off", "metadata", "full"]


@dataclass(frozen=True)
class StorageConfig:
    mode: StorageMode = "full"
    root: Path = Path("/data/artifacts")
    retention_days: int | None = None


@dataclass(frozen=True)
class AuditConfig:
    trusted_proxies: tuple[ipaddress._BaseNetwork, ...] = field(default_factory=tuple)
    store_watermark_text: bool = True
    store_extracted_text: bool = True
    store_passphrases: Literal["encrypted", "none"] = "encrypted"


@dataclass(frozen=True)
class LimitsConfig:
    max_upload_bytes: int = 25 * 1024 * 1024
    max_pixels: int = 24_000_000
    max_concurrent_jobs: int = 1


@dataclass(frozen=True)
class AppConfig:
    storage: StorageConfig
    audit: AuditConfig
    limits: LimitsConfig
    database_path: Path
    allowed_origins: tuple[str, ...]
    admin_username: str
    admin_password: str | None
    admin_password_hash: str | None
    jwt_secret: str
    jwt_ttl_minutes: int
    master_keys: dict[str, bytes]
    active_key_id: str | None


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _parse_master_keys(raw: str | None) -> dict[str, bytes]:
    if not raw:
        return {}
    parsed = json.loads(raw)
    keys: dict[str, bytes] = {}
    for key_id, encoded in parsed.items():
        value = base64.urlsafe_b64decode(encoded)
        if len(value) != 32:
            raise ValueError(f"Master key {key_id!r} must decode to 32 bytes")
        keys[str(key_id)] = value
    return keys


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path if path is not None else os.getenv("WATERMARK_CONFIG", "config.yaml"))
    raw = _load_yaml(config_path)
    storage_raw = raw.get("storage", {})
    audit_raw = raw.get("audit", {})
    limits_raw = raw.get("limits", {})

    mode = os.getenv("STORAGE_MODE", storage_raw.get("mode", "full"))
    if mode not in {"off", "metadata", "full"}:
        raise ValueError("storage.mode must be off, metadata, or full")

    root = Path(os.getenv("STORAGE_ROOT", storage_raw.get("root", "/data/artifacts")))
    database_path = Path(
        os.getenv("DATABASE_PATH", raw.get("database_path", str(root / "watermark.sqlite3")))
    )
    trusted = tuple(
        ipaddress.ip_network(item, strict=False) for item in audit_raw.get("trusted_proxies", [])
    )
    passphrase_mode = audit_raw.get("store_passphrases", "encrypted")
    if passphrase_mode not in {"encrypted", "none"}:
        raise ValueError("audit.store_passphrases must be encrypted or none")

    allowed_origins = tuple(
        origin.strip()
        for origin in os.getenv(
            "ALLOWED_ORIGINS",
            ",".join(raw.get("allowed_origins", ["http://localhost:3000"])),
        ).split(",")
        if origin.strip()
    )
    keys = _parse_master_keys(os.getenv("WM_MASTER_KEYS"))
    active_key_id = os.getenv("WM_ACTIVE_KEY_ID")
    if mode != "off" and passphrase_mode == "encrypted":
        if not keys or not active_key_id or active_key_id not in keys:
            raise ValueError(
                "WM_MASTER_KEYS and a matching WM_ACTIVE_KEY_ID are required "
                "when encrypted passphrase storage is enabled"
            )

    return AppConfig(
        storage=StorageConfig(
            mode=cast(StorageMode, mode),
            root=root,
            retention_days=storage_raw.get("retention_days"),
        ),
        audit=AuditConfig(
            trusted_proxies=trusted,
            store_watermark_text=bool(audit_raw.get("store_watermark_text", True)),
            store_extracted_text=bool(audit_raw.get("store_extracted_text", True)),
            store_passphrases=passphrase_mode,
        ),
        limits=LimitsConfig(
            max_upload_bytes=int(limits_raw.get("max_upload_bytes", 25 * 1024 * 1024)),
            max_pixels=int(limits_raw.get("max_pixels", 24_000_000)),
            max_concurrent_jobs=int(limits_raw.get("max_concurrent_jobs", 1)),
        ),
        database_path=database_path,
        allowed_origins=allowed_origins,
        admin_username=os.getenv("ADMIN_USERNAME", "admin"),
        admin_password=os.getenv("ADMIN_PASSWORD"),
        admin_password_hash=os.getenv("ADMIN_PASSWORD_HASH"),
        jwt_secret=os.getenv("JWT_SECRET", "development-only-change-me"),
        jwt_ttl_minutes=int(os.getenv("JWT_TTL_MINUTES", "30")),
        master_keys=keys,
        active_key_id=active_key_id,
    )
