from __future__ import annotations

import base64
import os
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import AppConfig

_password_hasher = PasswordHasher()


class SecretCipher:
    def __init__(self, keys: dict[str, bytes], active_key_id: str | None):
        self.keys = keys
        self.active_key_id = active_key_id

    def encrypt(self, value: str) -> tuple[str, str, str] | None:
        if not value or not self.active_key_id:
            return None
        nonce = os.urandom(12)
        ciphertext = AESGCM(self.keys[self.active_key_id]).encrypt(
            nonce, value.encode("utf-8"), self.active_key_id.encode("utf-8")
        )
        return (
            self.active_key_id,
            base64.urlsafe_b64encode(nonce).decode("ascii"),
            base64.urlsafe_b64encode(ciphertext).decode("ascii"),
        )

    def decrypt(self, key_id: str, nonce: str, ciphertext: str) -> str:
        key = self.keys[key_id]
        plain = AESGCM(key).decrypt(
            base64.urlsafe_b64decode(nonce),
            base64.urlsafe_b64decode(ciphertext),
            key_id.encode("utf-8"),
        )
        return plain.decode("utf-8")


class AdminAuth:
    def __init__(self, config: AppConfig):
        self.username = config.admin_username
        self.password_hash = config.admin_password_hash
        if not self.password_hash and config.admin_password:
            self.password_hash = _password_hasher.hash(config.admin_password)
        self.jwt_secret = config.jwt_secret
        self.ttl_minutes = config.jwt_ttl_minutes

    def verify(self, username: str, password: str) -> bool:
        if not self.password_hash or username != self.username:
            return False
        try:
            return _password_hasher.verify(self.password_hash, password)
        except VerifyMismatchError:
            return False

    def create_token(self) -> str:
        now = datetime.now(UTC)
        return jwt.encode(
            {
                "sub": self.username,
                "iat": now,
                "exp": now + timedelta(minutes=self.ttl_minutes),
                "scope": "admin",
            },
            self.jwt_secret,
            algorithm="HS256",
        )

    def validate_token(self, token: str) -> str:
        payload = jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
        if payload.get("scope") != "admin":
            raise jwt.InvalidTokenError("Invalid scope")
        return str(payload["sub"])
