from __future__ import annotations

import hashlib
import ipaddress
import mimetypes
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import Request

from .config import AppConfig
from .database import Database, json_dumps, json_loads
from .security import SecretCipher


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class RequestNetwork:
    client_ip: str
    direct_ip: str
    forwarded_chain: list[str]


@dataclass
class ArtifactInput:
    role: str
    original_name: str
    mime: str
    data: bytes


def _valid_ip(value: str) -> str | None:
    value = value.strip().strip('"')
    if value.startswith("[") and "]" in value:
        value = value[1 : value.index("]")]
    elif value.count(":") == 1 and "." in value:
        value = value.split(":", 1)[0]
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def request_network(request: Request, config: AppConfig) -> RequestNetwork:
    direct = request.client.host if request.client else "unknown"
    try:
        direct_address = ipaddress.ip_address(direct)
        trusted = any(direct_address in network for network in config.audit.trusted_proxies)
    except ValueError:
        trusted = False

    chain: list[str] = []
    if trusted:
        forwarded = request.headers.get("forwarded", "")
        for item in forwarded.split(","):
            for part in item.split(";"):
                if part.strip().lower().startswith("for="):
                    parsed = _valid_ip(part.split("=", 1)[1])
                    if parsed:
                        chain.append(parsed)
        if not chain:
            for item in request.headers.get("x-forwarded-for", "").split(","):
                parsed = _valid_ip(item)
                if parsed:
                    chain.append(parsed)
    return RequestNetwork(
        client_ip=chain[0] if chain else direct,
        direct_ip=direct,
        forwarded_chain=chain,
    )


def file_metadata(
    filename: str,
    declared_mime: str,
    actual_mime: str,
    data: bytes,
    width: int | None = None,
    height: int | None = None,
    color_mode: str | None = None,
) -> dict[str, Any]:
    return {
        "filename": filename,
        "declared_mime": declared_mime,
        "actual_mime": actual_mime,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "width": width,
        "height": height,
        "color_mode": color_mode,
    }


class AuditService:
    def __init__(self, config: AppConfig, database: Database):
        self.config = config
        self.database = database
        self.cipher = SecretCipher(config.master_keys, config.active_key_id)
        if config.storage.mode != "off":
            config.storage.root.mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        return self.config.storage.mode != "off"

    def record(
        self,
        *,
        request: Request,
        request_id: str,
        operation: str,
        created_at: str,
        completed_at: str,
        duration_ms: int,
        status: str,
        http_status: int,
        error_code: str | None,
        input_files: list[dict[str, Any]],
        parameters: dict[str, Any],
        result: dict[str, Any],
        passphrase: str,
        artifacts: list[ArtifactInput],
    ) -> str | None:
        if not self.enabled:
            return None
        audit_id = str(uuid.uuid4())
        network = request_network(request, self.config)
        encrypted = None
        if self.config.audit.store_passphrases == "encrypted":
            encrypted = self.cipher.encrypt(passphrase)
        key_id, nonce, ciphertext = encrypted or (None, None, None)
        if not self.config.audit.store_watermark_text:
            parameters.pop("watermark_text", None)
        if not self.config.audit.store_extracted_text:
            result.pop("text", None)

        artifact_rows: list[tuple[str, ArtifactInput, str]] = []
        audit_dir = self.config.storage.root / audit_id
        try:
            if self.config.storage.mode == "full":
                audit_dir.mkdir(parents=True, exist_ok=False)
                for artifact in artifacts:
                    artifact_id = str(uuid.uuid4())
                    extension = mimetypes.guess_extension(artifact.mime) or ".bin"
                    path = audit_dir / f"{artifact_id}{extension}"
                    path.write_bytes(artifact.data)
                    artifact_rows.append((artifact_id, artifact, str(path)))

            with self.database.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO audit_records (
                        id, request_id, operation, created_at, completed_at,
                        client_ip, direct_ip, forwarded_chain_json, user_agent,
                        frontend_version, status, http_status, error_code, duration_ms,
                        input_files_json, parameters_json, result_json,
                        passphrase_key_id, passphrase_nonce, passphrase_ciphertext
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        audit_id,
                        request_id,
                        operation,
                        created_at,
                        completed_at,
                        network.client_ip,
                        network.direct_ip,
                        json_dumps(network.forwarded_chain),
                        request.headers.get("user-agent", ""),
                        request.headers.get("x-frontend-version"),
                        status,
                        http_status,
                        error_code,
                        duration_ms,
                        json_dumps(input_files),
                        json_dumps(parameters),
                        json_dumps(result),
                        key_id,
                        nonce,
                        ciphertext,
                    ),
                )
                for artifact_id, artifact, stored_path in artifact_rows:
                    conn.execute(
                        """
                        INSERT INTO artifacts (
                            id, audit_id, role, original_name, stored_path,
                            mime, size, sha256, created_at
                        ) VALUES (?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            artifact_id,
                            audit_id,
                            artifact.role,
                            artifact.original_name,
                            stored_path,
                            artifact.mime,
                            len(artifact.data),
                            hashlib.sha256(artifact.data).hexdigest(),
                            completed_at,
                        ),
                    )
                conn.commit()
        except Exception:
            if audit_dir.exists():
                shutil.rmtree(audit_dir, ignore_errors=True)
            raise
        return audit_id

    def list_records(
        self, limit: int, offset: int, operation: str | None, status: str | None, query: str | None
    ) -> tuple[list[dict[str, Any]], int]:
        clauses: list[str] = []
        params: list[Any] = []
        if operation:
            clauses.append("operation = ?")
            params.append(operation)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if query:
            clauses.append("(request_id LIKE ? OR client_ip LIKE ?)")
            params.extend([f"%{query}%", f"%{query}%"])
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        total_row = self.database.fetchone(
            f"SELECT COUNT(*) AS count FROM audit_records{where}", tuple(params)
        )
        rows = self.database.fetchall(
            f"""
            SELECT id, request_id, operation, created_at, completed_at, client_ip,
                   status, http_status, error_code, duration_ms
            FROM audit_records{where}
            ORDER BY created_at DESC LIMIT ? OFFSET ?
            """,
            tuple(params + [limit, offset]),
        )
        return [dict(row) for row in rows], int(total_row["count"] if total_row else 0)

    def get_record(self, audit_id: str) -> dict[str, Any] | None:
        row = self.database.fetchone("SELECT * FROM audit_records WHERE id = ?", (audit_id,))
        if not row:
            return None
        value = dict(row)
        for source, target in (
            ("forwarded_chain_json", "forwarded_chain"),
            ("input_files_json", "input_files"),
            ("parameters_json", "parameters"),
            ("result_json", "result"),
        ):
            value[target] = json_loads(value.pop(source))
        return value

    def list_artifacts(self, audit_id: str) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.database.fetchall(
                """
                SELECT id, role, original_name, mime, size, sha256, created_at
                FROM artifacts WHERE audit_id = ? ORDER BY created_at
                """,
                (audit_id,),
            )
        ]

    def get_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        row = self.database.fetchone("SELECT * FROM artifacts WHERE id = ?", (artifact_id,))
        return dict(row) if row else None

    def reveal_passphrase(self, audit_id: str) -> str:
        row = self.database.fetchone(
            """
            SELECT passphrase_key_id, passphrase_nonce, passphrase_ciphertext
            FROM audit_records WHERE id = ?
            """,
            (audit_id,),
        )
        if not row or not row["passphrase_ciphertext"]:
            return ""
        return self.cipher.decrypt(
            row["passphrase_key_id"], row["passphrase_nonce"], row["passphrase_ciphertext"]
        )

    def admin_event(
        self,
        username: str,
        action: str,
        target_id: str | None,
        client_ip: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        if not self.enabled:
            return
        self.database.execute(
            """
            INSERT INTO admin_events (
                id, created_at, admin_username, action, target_id, client_ip, details_json
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                str(uuid.uuid4()),
                utc_now(),
                username,
                action,
                target_id,
                client_ip,
                json_dumps(details or {}),
            ),
        )

    def delete_record(self, audit_id: str, username: str, client_ip: str, reason: str) -> bool:
        record = self.get_record(audit_id)
        if not record:
            return False
        artifacts = self.database.fetchall(
            "SELECT stored_path FROM artifacts WHERE audit_id = ?", (audit_id,)
        )
        self.admin_event(
            username,
            "delete_audit_record",
            audit_id,
            client_ip,
            {
                "reason": reason,
                "request_id": record["request_id"],
                "operation": record["operation"],
                "created_at": record["created_at"],
            },
        )
        with self.database.transaction() as conn:
            conn.execute("DELETE FROM audit_records WHERE id = ?", (audit_id,))
            conn.commit()
        for artifact in artifacts:
            path = Path(artifact["stored_path"])
            if path.exists():
                path.unlink()
        directory = self.config.storage.root / audit_id
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=True)
        return True
