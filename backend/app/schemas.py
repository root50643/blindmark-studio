from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ProblemDetail(BaseModel):
    type: str
    title: str
    status: int
    detail: str
    code: str
    request_id: str | None = None


class CapabilitiesResponse(BaseModel):
    api_version: str = "v1"
    formats: list[str]
    output_format: str
    max_upload_bytes: int
    max_pixels: int
    watermark_types: list[str]
    legacy_decode: bool
    storage_mode: str


class ImageInfo(BaseModel):
    filename: str
    mime: str
    bytes: int
    width: int
    height: int
    color_mode: str
    sha256: str


class PreviewResponse(BaseModel):
    image_data_url: str
    width: int
    height: int
    resized: bool
    capacity_bits: int
    used_bits: int


class ExtractionResponse(BaseModel):
    kind: Literal["text", "image"]
    text: str | None = None
    image_data_url: str | None = None
    width: int | None = None
    height: int | None = None


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class AuditRecordSummary(BaseModel):
    id: str
    request_id: str
    operation: str
    created_at: str
    completed_at: str | None
    client_ip: str
    status: str
    http_status: int | None
    error_code: str | None
    duration_ms: int | None


class AuditRecordList(BaseModel):
    items: list[AuditRecordSummary]
    total: int
    limit: int
    offset: int


class AuditRecordDetail(BaseModel):
    id: str
    request_id: str
    operation: str
    created_at: str
    completed_at: str | None
    client_ip: str
    direct_ip: str
    forwarded_chain: list[str]
    user_agent: str
    status: str
    http_status: int | None
    error_code: str | None
    duration_ms: int | None
    input_files: list[dict[str, Any]]
    parameters: dict[str, Any]
    result: dict[str, Any]


class ArtifactResponse(BaseModel):
    id: str
    role: str
    original_name: str
    mime: str
    size: int
    sha256: str
    created_at: str


class PassphraseRevealResponse(BaseModel):
    passphrase: str


class DeleteAuditRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)
