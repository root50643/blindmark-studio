from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AppError(Exception):
    status: int
    code: str
    title: str
    detail: str


def invalid_image(detail: str = "無法讀取圖片或圖片格式不受支援。") -> AppError:
    return AppError(400, "invalid_image", "圖片無效", detail)


def extraction_failed() -> AppError:
    return AppError(
        422,
        "watermark_extraction_failed",
        "無法解碼浮水印",
        "圖片不含可辨識的本站浮水印，或解碼口令不正確。",
    )
