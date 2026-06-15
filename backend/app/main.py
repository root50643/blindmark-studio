import asyncio
import copy
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

import anyio
import jwt
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .audit import (
    ArtifactInput,
    AuditService,
    file_metadata,
    request_network,
    utc_now,
)
from .config import AppConfig, load_config
from .database import Database
from .errors import AppError
from .schemas import (
    AdminLoginRequest,
    ArtifactResponse,
    AuditRecordDetail,
    AuditRecordList,
    AuditRecordSummary,
    CapabilitiesResponse,
    DeleteAuditRequest,
    ExtractionResponse,
    PassphraseRevealResponse,
    PreviewResponse,
    ProblemDetail,
    TokenResponse,
)
from .security import AdminAuth
from .watermark import WatermarkService, data_url

API_PREFIX = "/api/v1"
bearer = HTTPBearer(auto_error=False)


def _problem(
    request: Request,
    status: int,
    code: str,
    title: str,
    detail: str,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    body = ProblemDetail(
        type=f"https://example.invalid/problems/{code}",
        title=title,
        status=status,
        detail=detail,
        code=code,
        request_id=request_id,
    )
    return JSONResponse(
        status_code=status,
        content=body.model_dump(),
        media_type="application/problem+json",
    )


async def _read_upload(upload: UploadFile, config: AppConfig) -> bytes:
    data = await upload.read(config.limits.max_upload_bytes + 1)
    if len(data) > config.limits.max_upload_bytes:
        raise AppError(
            413,
            "upload_size_limit_exceeded",
            "上傳檔案過大",
            f"單一檔案不得超過 {config.limits.max_upload_bytes:,} bytes。",
        )
    if not data:
        raise AppError(400, "empty_upload", "空白檔案", "上傳檔案不可為空白。")
    return data


def _result_metadata(extracted) -> dict:
    if extracted.kind == "text":
        return {"kind": "text", "text": extracted.text, "text_length": len(extracted.text or "")}
    return {
        "kind": "image",
        "width": extracted.width,
        "height": extracted.height,
        "size": len(extracted.png or b""),
    }


def create_app(config: AppConfig | None = None) -> FastAPI:
    settings = config or load_config()
    database = Database(settings.database_path)
    audit = AuditService(settings, database)
    watermark = WatermarkService(settings.limits.max_pixels)
    auth = AdminAuth(settings)
    job_semaphore = asyncio.Semaphore(settings.limits.max_concurrent_jobs)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield

    app = FastAPI(
        title="Blind Watermark REST API",
        version="1.0.0",
        description="文字與圖片盲浮水印嵌入、解碼及稽核管理 API。",
        lifespan=lifespan,
    )
    app.state.config = settings
    app.state.database = database
    app.state.audit = audit
    app.state.watermark = watermark
    app.state.auth = auth

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition", "X-Request-ID"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request.state.request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return _problem(request, exc.status, exc.code, exc.title, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return _problem(
            request,
            422,
            "validation_error",
            "請求資料錯誤",
            "請檢查必要欄位、資料型別與允許的值。",
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException):
        if exc.status_code == 401:
            return _problem(
                request,
                401,
                "admin_authentication_required",
                "需要管理員驗證",
                "管理 token 無效、已過期或未提供。",
            )
        return _problem(
            request,
            exc.status_code,
            "http_error",
            "請求失敗",
            str(exc.detail),
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception):
        return _problem(
            request,
            500,
            "internal_error",
            "伺服器處理失敗",
            "處理時發生未預期錯誤，請使用 request ID 查詢伺服器日誌。",
        )

    async def run_job(function, *args):
        async with job_semaphore:
            return await anyio.to_thread.run_sync(function, *args)

    def record_operation(
        *,
        request: Request,
        operation: str,
        started_at: str,
        start_time: float,
        status: str,
        http_status: int,
        error_code: str | None,
        input_files: list[dict],
        parameters: dict,
        result: dict,
        passphrase: str,
        artifacts: list[ArtifactInput],
    ) -> None:
        audit.record(
            request=request,
            request_id=request.state.request_id,
            operation=operation,
            created_at=started_at,
            completed_at=utc_now(),
            duration_ms=round((time.perf_counter() - start_time) * 1000),
            status=status,
            http_status=http_status,
            error_code=error_code,
            input_files=copy.deepcopy(input_files),
            parameters=copy.deepcopy(parameters),
            result=copy.deepcopy(result),
            passphrase=passphrase,
            artifacts=artifacts,
        )

    async def require_admin(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> str:
        if not credentials:
            raise HTTPException(status_code=401, detail="Missing bearer token")
        try:
            return auth.validate_token(credentials.credentials)
        except jwt.InvalidTokenError as exc:
            raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    @app.get("/healthz", tags=["system"])
    async def healthz():
        return {"status": "ok"}

    @app.get(
        f"{API_PREFIX}/capabilities",
        response_model=CapabilitiesResponse,
        tags=["public"],
    )
    async def capabilities():
        return CapabilitiesResponse(
            formats=["image/png", "image/jpeg", "image/webp"],
            output_format="image/png",
            max_upload_bytes=settings.limits.max_upload_bytes,
            max_pixels=settings.limits.max_pixels,
            watermark_types=["text", "image"],
            legacy_decode=True,
            storage_mode=settings.storage.mode,
        )

    @app.post(
        f"{API_PREFIX}/watermark-previews",
        response_model=PreviewResponse,
        responses={400: {"model": ProblemDetail}, 422: {"model": ProblemDetail}},
        tags=["public"],
    )
    async def watermark_preview(
        request: Request,
        cover_image: UploadFile = File(...),
        watermark_image: UploadFile = File(...),
    ):
        operation = "watermark_preview"
        started_at, start_time = utc_now(), time.perf_counter()
        input_files: list[dict] = []
        artifacts: list[ArtifactInput] = []
        try:
            cover_data = await _read_upload(cover_image, settings)
            artifacts.append(
                ArtifactInput(
                    "cover_input",
                    cover_image.filename or "cover",
                    cover_image.content_type or "application/octet-stream",
                    cover_data,
                )
            )
            watermark_data = await _read_upload(watermark_image, settings)
            artifacts.append(
                ArtifactInput(
                    "watermark_input",
                    watermark_image.filename or "watermark",
                    watermark_image.content_type or "application/octet-stream",
                    watermark_data,
                )
            )
            cover = watermark.inspect(cover_data)
            source = watermark.inspect(watermark_data)
            input_files = [
                file_metadata(
                    cover_image.filename or "cover",
                    cover_image.content_type or "",
                    cover.mime,
                    cover_data,
                    cover.width,
                    cover.height,
                    cover.mode,
                ),
                file_metadata(
                    watermark_image.filename or "watermark",
                    watermark_image.content_type or "",
                    source.mime,
                    watermark_data,
                    source.width,
                    source.height,
                    source.mode,
                ),
            ]
            prepared = await run_job(watermark.prepare_image_watermark, cover, watermark_data)
            cover_name = cover_image.filename or "cover"
            watermark_name = watermark_image.filename or "watermark"
            artifacts[0] = ArtifactInput("cover_input", cover_name, cover.mime, cover_data)
            artifacts[1] = ArtifactInput(
                "watermark_input",
                watermark_name,
                source.mime,
                watermark_data,
            )
            artifacts.append(
                ArtifactInput("watermark_preview", "preview.png", "image/png", prepared.png)
            )
            result = {
                "width": prepared.width,
                "height": prepared.height,
                "resized": prepared.resized,
                "capacity_bits": prepared.capacity_bits,
                "used_bits": prepared.used_bits,
            }
            record_operation(
                request=request,
                operation=operation,
                started_at=started_at,
                start_time=start_time,
                status="success",
                http_status=200,
                error_code=None,
                input_files=input_files,
                parameters={},
                result=result,
                passphrase="",
                artifacts=artifacts,
            )
            return PreviewResponse(image_data_url=data_url(prepared.png), **result)
        except AppError as exc:
            record_operation(
                request=request,
                operation=operation,
                started_at=started_at,
                start_time=start_time,
                status="failed",
                http_status=exc.status,
                error_code=exc.code,
                input_files=input_files,
                parameters={},
                result={},
                passphrase="",
                artifacts=artifacts,
            )
            raise

    @app.post(
        f"{API_PREFIX}/watermarked-images",
        responses={200: {"content": {"image/png": {}}}},
        tags=["public"],
    )
    async def create_watermarked_image(
        request: Request,
        cover_image: UploadFile = File(...),
        watermark_type: Literal["text", "image"] = Form(...),
        watermark_text: str = Form(""),
        watermark_image: UploadFile | None = File(None),
        passphrase: str = Form(""),
    ):
        operation = "embed_watermark"
        started_at, start_time = utc_now(), time.perf_counter()
        input_files: list[dict] = []
        artifacts: list[ArtifactInput] = []
        parameters = {
            "watermark_type": watermark_type,
            "watermark_text": watermark_text,
            "watermark_text_length": len(watermark_text),
        }
        try:
            cover_data = await _read_upload(cover_image, settings)
            artifacts.append(
                ArtifactInput(
                    "cover_input",
                    cover_image.filename or "cover",
                    cover_image.content_type or "application/octet-stream",
                    cover_data,
                )
            )
            cover = watermark.inspect(cover_data)
            input_files.append(
                file_metadata(
                    cover_image.filename or "cover",
                    cover_image.content_type or "",
                    cover.mime,
                    cover_data,
                    cover.width,
                    cover.height,
                    cover.mode,
                )
            )
            cover_name = cover_image.filename or "cover"
            artifacts[0] = ArtifactInput("cover_input", cover_name, cover.mime, cover_data)
            if watermark_type == "text":
                output = await run_job(watermark.embed_text, cover, watermark_text, passphrase)
            else:
                if watermark_image is None:
                    raise AppError(
                        422,
                        "watermark_image_required",
                        "缺少浮水印圖片",
                        "圖片模式必須上傳浮水印圖片。",
                    )
                watermark_data = await _read_upload(watermark_image, settings)
                artifacts.append(
                    ArtifactInput(
                        "watermark_input",
                        watermark_image.filename or "watermark",
                        watermark_image.content_type or "application/octet-stream",
                        watermark_data,
                    )
                )
                watermark_source = watermark.inspect(watermark_data)
                input_files.append(
                    file_metadata(
                        watermark_image.filename or "watermark",
                        watermark_image.content_type or "",
                        watermark_source.mime,
                        watermark_data,
                        watermark_source.width,
                        watermark_source.height,
                        watermark_source.mode,
                    )
                )
                artifacts[-1] = ArtifactInput(
                    "watermark_input",
                    watermark_image.filename or "watermark",
                    watermark_source.mime,
                    watermark_data,
                )
                output, prepared = await run_job(
                    watermark.embed_image, cover, watermark_data, passphrase
                )
                parameters.update(
                    {
                        "prepared_width": prepared.width,
                        "prepared_height": prepared.height,
                        "watermark_resized": prepared.resized,
                    }
                )
                artifacts.append(
                    ArtifactInput(
                        "watermark_prepared",
                        "prepared-watermark.png",
                        "image/png",
                        prepared.png,
                    )
                )
            artifacts.append(
                ArtifactInput("watermarked_output", "watermarked.png", "image/png", output)
            )
            result = {"mime": "image/png", "size": len(output)}
            record_operation(
                request=request,
                operation=operation,
                started_at=started_at,
                start_time=start_time,
                status="success",
                http_status=200,
                error_code=None,
                input_files=input_files,
                parameters=parameters,
                result=result,
                passphrase=passphrase,
                artifacts=artifacts,
            )
            return Response(
                output,
                media_type="image/png",
                headers={"Content-Disposition": 'attachment; filename="watermarked.png"'},
            )
        except AppError as exc:
            record_operation(
                request=request,
                operation=operation,
                started_at=started_at,
                start_time=start_time,
                status="failed",
                http_status=exc.status,
                error_code=exc.code,
                input_files=input_files,
                parameters=parameters,
                result={},
                passphrase=passphrase,
                artifacts=artifacts,
            )
            raise

    @app.post(
        f"{API_PREFIX}/watermark-extractions",
        response_model=ExtractionResponse,
        tags=["public"],
    )
    async def extract_watermark(
        request: Request,
        encoded_image: UploadFile = File(...),
        passphrase: str = Form(""),
    ):
        operation = "extract_watermark"
        started_at, start_time = utc_now(), time.perf_counter()
        input_files: list[dict] = []
        artifacts: list[ArtifactInput] = []
        try:
            encoded_data = await _read_upload(encoded_image, settings)
            artifacts.append(
                ArtifactInput(
                    "encoded_input",
                    encoded_image.filename or "encoded",
                    encoded_image.content_type or "application/octet-stream",
                    encoded_data,
                )
            )
            encoded = watermark.inspect(encoded_data)
            input_files = [
                file_metadata(
                    encoded_image.filename or "encoded",
                    encoded_image.content_type or "",
                    encoded.mime,
                    encoded_data,
                    encoded.width,
                    encoded.height,
                    encoded.mode,
                )
            ]
            artifacts[0] = ArtifactInput(
                "encoded_input",
                encoded_image.filename or "encoded",
                encoded.mime,
                encoded_data,
            )
            extracted = await run_job(watermark.extract, encoded, passphrase)
            result = _result_metadata(extracted)
            if extracted.png:
                artifacts.append(
                    ArtifactInput(
                        "extracted_watermark",
                        "extracted-watermark.png",
                        "image/png",
                        extracted.png,
                    )
                )
            record_operation(
                request=request,
                operation=operation,
                started_at=started_at,
                start_time=start_time,
                status="success",
                http_status=200,
                error_code=None,
                input_files=input_files,
                parameters={},
                result=result,
                passphrase=passphrase,
                artifacts=artifacts,
            )
            return ExtractionResponse(
                kind=extracted.kind,
                text=extracted.text,
                image_data_url=data_url(extracted.png) if extracted.png else None,
                width=extracted.width,
                height=extracted.height,
            )
        except AppError as exc:
            record_operation(
                request=request,
                operation=operation,
                started_at=started_at,
                start_time=start_time,
                status="failed",
                http_status=exc.status,
                error_code=exc.code,
                input_files=input_files,
                parameters={},
                result={},
                passphrase=passphrase,
                artifacts=artifacts,
            )
            raise

    @app.post(
        f"{API_PREFIX}/legacy-watermark-extractions",
        response_model=ExtractionResponse,
        tags=["public"],
    )
    async def legacy_extract_watermark(
        request: Request,
        encoded_image: UploadFile = File(...),
        mode: Literal["text", "image"] = Form(...),
        password_img: int = Form(...),
        password_wm: int = Form(...),
        bit_length: int | None = Form(None),
        width: int | None = Form(None),
        height: int | None = Form(None),
    ):
        operation = "legacy_extract_watermark"
        started_at, start_time = utc_now(), time.perf_counter()
        input_files: list[dict] = []
        parameters = {
            "mode": mode,
            "password_img": password_img,
            "password_wm": password_wm,
            "bit_length": bit_length,
            "width": width,
            "height": height,
        }
        artifacts: list[ArtifactInput] = []
        try:
            encoded_data = await _read_upload(encoded_image, settings)
            artifacts.append(
                ArtifactInput(
                    "encoded_input",
                    encoded_image.filename or "encoded",
                    encoded_image.content_type or "application/octet-stream",
                    encoded_data,
                )
            )
            encoded = watermark.inspect(encoded_data)
            input_files = [
                file_metadata(
                    encoded_image.filename or "encoded",
                    encoded_image.content_type or "",
                    encoded.mime,
                    encoded_data,
                    encoded.width,
                    encoded.height,
                    encoded.mode,
                )
            ]
            artifacts[0] = ArtifactInput(
                "encoded_input",
                encoded_image.filename or "encoded",
                encoded.mime,
                encoded_data,
            )
            extracted = await run_job(
                watermark.legacy_extract,
                encoded,
                mode,
                password_img,
                password_wm,
                bit_length,
                width,
                height,
            )
            result = _result_metadata(extracted)
            if extracted.png:
                artifacts.append(
                    ArtifactInput(
                        "extracted_watermark",
                        "legacy-extracted.png",
                        "image/png",
                        extracted.png,
                    )
                )
            record_operation(
                request=request,
                operation=operation,
                started_at=started_at,
                start_time=start_time,
                status="success",
                http_status=200,
                error_code=None,
                input_files=input_files,
                parameters=parameters,
                result=result,
                passphrase="",
                artifacts=artifacts,
            )
            return ExtractionResponse(
                kind=extracted.kind,
                text=extracted.text,
                image_data_url=data_url(extracted.png) if extracted.png else None,
                width=extracted.width,
                height=extracted.height,
            )
        except AppError as exc:
            record_operation(
                request=request,
                operation=operation,
                started_at=started_at,
                start_time=start_time,
                status="failed",
                http_status=exc.status,
                error_code=exc.code,
                input_files=input_files,
                parameters=parameters,
                result={},
                passphrase="",
                artifacts=artifacts,
            )
            raise

    @app.post(
        f"{API_PREFIX}/admin/auth/login",
        response_model=TokenResponse,
        tags=["admin"],
    )
    async def admin_login(request: Request, payload: AdminLoginRequest):
        network = request_network(request, settings)
        if not auth.verify(payload.username, payload.password):
            audit.admin_event(payload.username, "login_failed", None, network.client_ip, {})
            raise AppError(401, "admin_login_failed", "登入失敗", "帳號或密碼錯誤。")
        audit.admin_event(payload.username, "login_success", None, network.client_ip, {})
        return TokenResponse(
            access_token=auth.create_token(),
            expires_in=settings.jwt_ttl_minutes * 60,
        )

    @app.get(
        f"{API_PREFIX}/admin/audit-records",
        response_model=AuditRecordList,
        tags=["admin"],
    )
    async def admin_list_records(
        request: Request,
        username: Annotated[str, Depends(require_admin)],
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        operation: str | None = None,
        status: str | None = None,
        query: str | None = None,
    ):
        items, total = audit.list_records(limit, offset, operation, status, query)
        audit.admin_event(
            username,
            "list_audit_records",
            None,
            request_network(request, settings).client_ip,
            {"limit": limit, "offset": offset},
        )
        return AuditRecordList(
            items=[AuditRecordSummary(**item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    @app.get(
        f"{API_PREFIX}/admin/audit-records/{{audit_id}}",
        response_model=AuditRecordDetail,
        tags=["admin"],
    )
    async def admin_get_record(
        audit_id: str,
        request: Request,
        username: Annotated[str, Depends(require_admin)],
    ):
        record = audit.get_record(audit_id)
        if not record:
            raise AppError(404, "audit_record_not_found", "找不到紀錄", "指定紀錄不存在。")
        audit.admin_event(
            username,
            "view_audit_record",
            audit_id,
            request_network(request, settings).client_ip,
            {},
        )
        return AuditRecordDetail(**record)

    @app.get(
        f"{API_PREFIX}/admin/audit-records/{{audit_id}}/artifacts",
        response_model=list[ArtifactResponse],
        tags=["admin"],
    )
    async def admin_list_artifacts(
        audit_id: str,
        _username: Annotated[str, Depends(require_admin)],
    ):
        if not audit.get_record(audit_id):
            raise AppError(404, "audit_record_not_found", "找不到紀錄", "指定紀錄不存在。")
        return [ArtifactResponse(**item) for item in audit.list_artifacts(audit_id)]

    @app.get(
        f"{API_PREFIX}/admin/artifacts/{{artifact_id}}/content",
        tags=["admin"],
    )
    async def admin_download_artifact(
        artifact_id: str,
        request: Request,
        username: Annotated[str, Depends(require_admin)],
    ):
        artifact = audit.get_artifact(artifact_id)
        if not artifact or not Path(artifact["stored_path"]).is_file():
            raise AppError(404, "artifact_not_found", "找不到檔案", "指定保存檔案不存在。")
        audit.admin_event(
            username,
            "download_artifact",
            artifact_id,
            request_network(request, settings).client_ip,
            {"audit_id": artifact["audit_id"]},
        )
        return FileResponse(
            artifact["stored_path"],
            media_type=artifact["mime"],
            filename=artifact["original_name"],
        )

    @app.post(
        f"{API_PREFIX}/admin/audit-records/{{audit_id}}/passphrase-reveal",
        response_model=PassphraseRevealResponse,
        tags=["admin"],
    )
    async def admin_reveal_passphrase(
        audit_id: str,
        request: Request,
        username: Annotated[str, Depends(require_admin)],
    ):
        if not audit.get_record(audit_id):
            raise AppError(404, "audit_record_not_found", "找不到紀錄", "指定紀錄不存在。")
        value = audit.reveal_passphrase(audit_id)
        audit.admin_event(
            username,
            "reveal_passphrase",
            audit_id,
            request_network(request, settings).client_ip,
            {},
        )
        return PassphraseRevealResponse(passphrase=value)

    @app.delete(
        f"{API_PREFIX}/admin/audit-records/{{audit_id}}",
        status_code=204,
        tags=["admin"],
    )
    async def admin_delete_record(
        audit_id: str,
        payload: DeleteAuditRequest,
        request: Request,
        username: Annotated[str, Depends(require_admin)],
    ):
        deleted = audit.delete_record(
            audit_id,
            username,
            request_network(request, settings).client_ip,
            payload.reason,
        )
        if not deleted:
            raise AppError(404, "audit_record_not_found", "找不到紀錄", "指定紀錄不存在。")
        return Response(status_code=204)

    return app
