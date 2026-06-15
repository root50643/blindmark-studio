from __future__ import annotations

import base64
import hashlib
import io
import math
import struct
import zlib
from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np
from blind_watermark import WaterMark, bw_notes
from PIL import Image, ImageOps, UnidentifiedImageError

from .errors import AppError, extraction_failed, invalid_image

bw_notes.close()

MAGIC = b"BWV1"
VERSION = 1
KIND_TEXT = 1
KIND_IMAGE = 2
HEADER = struct.Struct(">4sBBHIIII")
HEADER_BITS = HEADER.size * 8
BUCKETS = tuple(2**power for power in range(8, 18))  # 256 .. 131072 bits
DEFAULT_PASSPHRASE = "blind-watermark-web-default"


@dataclass
class DecodedImage:
    array: np.ndarray
    width: int
    height: int
    mode: str
    mime: str
    format: str


@dataclass
class PreparedWatermark:
    binary: np.ndarray
    png: bytes
    width: int
    height: int
    resized: bool
    capacity_bits: int
    used_bits: int


@dataclass
class ExtractedWatermark:
    kind: Literal["text", "image"]
    text: str | None = None
    png: bytes | None = None
    width: int | None = None
    height: int | None = None


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def derive_seeds(passphrase: str) -> tuple[int, int]:
    secret = (passphrase or DEFAULT_PASSPHRASE).encode("utf-8")

    def derive(label: bytes) -> int:
        digest = hashlib.sha256(label + b"\0" + secret).digest()
        return int.from_bytes(digest[:4], "big") & 0x7FFFFFFF or 1

    return derive(b"image"), derive(b"watermark")


def image_capacity_bits(width: int, height: int) -> int:
    return ((height + 1) // 8) * ((width + 1) // 8)


def usable_buckets(capacity: int) -> list[int]:
    return [bucket for bucket in BUCKETS if bucket < capacity]


def decode_image(data: bytes, max_pixels: int) -> DecodedImage:
    try:
        with Image.open(io.BytesIO(data)) as source:
            image_format = (source.format or "").upper()
            if image_format not in {"PNG", "JPEG", "WEBP"}:
                raise invalid_image("僅支援 PNG、JPEG 與 WebP 圖片。")
            width, height = source.size
            if width * height > max_pixels:
                raise AppError(
                    413,
                    "image_pixel_limit_exceeded",
                    "圖片像素過大",
                    f"圖片不得超過 {max_pixels:,} pixels。",
                )
            image = ImageOps.exif_transpose(source)
            image.load()
            has_alpha = image.mode in {"RGBA", "LA"} or "transparency" in image.info
            normalized = image.convert("RGBA" if has_alpha else "RGB")
            array = np.asarray(normalized)
            if has_alpha:
                array = cv2.cvtColor(array, cv2.COLOR_RGBA2BGRA)
            else:
                array = cv2.cvtColor(array, cv2.COLOR_RGB2BGR)
            mime = {
                "PNG": "image/png",
                "JPEG": "image/jpeg",
                "WEBP": "image/webp",
            }[image_format]
            return DecodedImage(
                array=array,
                width=normalized.width,
                height=normalized.height,
                mode=normalized.mode,
                mime=mime,
                format=image_format,
            )
    except AppError:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise invalid_image() from None


def encode_png(array: np.ndarray) -> bytes:
    success, encoded = cv2.imencode(".png", array)
    if not success:
        raise AppError(500, "image_encode_failed", "圖片輸出失敗", "無法建立 PNG 圖片。")
    return encoded.tobytes()


def data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _choose_bucket(bit_length: int, capacity: int) -> int:
    for bucket in usable_buckets(capacity):
        if bucket >= bit_length:
            return bucket
    raise AppError(
        422,
        "watermark_capacity_exceeded",
        "浮水印容量不足",
        "原圖可容納的資訊不足，請縮短文字、縮小浮水印圖片或改用較大的原圖。",
    )


def _bytes_to_bits(value: bytes) -> np.ndarray:
    return np.unpackbits(np.frombuffer(value, dtype=np.uint8)).astype(bool)


def _bits_to_bytes(value: np.ndarray) -> bytes:
    return np.packbits(value.astype(np.uint8)).tobytes()


def _build_packet(
    kind: int,
    payload: bytes,
    width: int = 0,
    height: int = 0,
) -> bytes:
    header = HEADER.pack(
        MAGIC,
        VERSION,
        kind,
        0,
        width,
        height,
        len(payload),
        zlib.crc32(payload) & 0xFFFFFFFF,
    )
    return header + payload


def _parse_packet(raw: bytes) -> ExtractedWatermark:
    if len(raw) < HEADER.size:
        raise extraction_failed()
    magic, version, kind, _flags, width, height, length, expected_crc = HEADER.unpack(
        raw[: HEADER.size]
    )
    if magic != MAGIC or version != VERSION or kind not in {KIND_TEXT, KIND_IMAGE}:
        raise extraction_failed()
    if length > len(raw) - HEADER.size:
        raise extraction_failed()
    payload = raw[HEADER.size : HEADER.size + length]
    if zlib.crc32(payload) & 0xFFFFFFFF != expected_crc:
        raise extraction_failed()
    if kind == KIND_TEXT:
        try:
            return ExtractedWatermark(kind="text", text=payload.decode("utf-8"))
        except UnicodeDecodeError:
            raise extraction_failed() from None
    if width <= 0 or height <= 0 or width * height > length * 8:
        raise extraction_failed()
    bits = np.unpackbits(np.frombuffer(payload, dtype=np.uint8))[: width * height]
    image = (bits.reshape((height, width)) * 255).astype(np.uint8)
    return ExtractedWatermark(
        kind="image",
        png=encode_png(image),
        width=width,
        height=height,
    )


def _pad_bits(bits: np.ndarray, bucket: int, passphrase: str) -> np.ndarray:
    if len(bits) == bucket:
        return bits
    digest = hashlib.sha256(b"padding\0" + (passphrase or DEFAULT_PASSPHRASE).encode()).digest()
    seed = int.from_bytes(digest[:4], "big")
    padding = np.random.RandomState(seed).randint(0, 2, bucket - len(bits)).astype(bool)
    return np.concatenate([bits, padding])


class WatermarkService:
    def __init__(self, max_pixels: int):
        self.max_pixels = max_pixels

    def inspect(self, data: bytes) -> DecodedImage:
        return decode_image(data, self.max_pixels)

    def prepare_image_watermark(
        self, cover: DecodedImage, watermark_data: bytes
    ) -> PreparedWatermark:
        watermark = decode_image(watermark_data, self.max_pixels)
        if watermark.array.ndim == 3:
            if watermark.array.shape[2] == 4:
                gray = cv2.cvtColor(watermark.array, cv2.COLOR_BGRA2GRAY)
            else:
                gray = cv2.cvtColor(watermark.array, cv2.COLOR_BGR2GRAY)
        else:
            gray = watermark.array

        buckets = usable_buckets(image_capacity_bits(cover.width, cover.height))
        if not buckets:
            raise AppError(
                422,
                "cover_image_too_small",
                "原圖尺寸過小",
                "原圖至少需要可容納 256 bits 的浮水印資料。",
            )
        max_payload_pixels = ((max(buckets) - HEADER_BITS) // 8) * 8
        if max_payload_pixels <= 0:
            raise AppError(422, "cover_image_too_small", "原圖尺寸過小", "原圖容量不足。")
        original_pixels = gray.shape[0] * gray.shape[1]
        resized = original_pixels > max_payload_pixels
        if resized:
            scale = math.sqrt(max_payload_pixels / original_pixels)
            new_width = max(1, int(gray.shape[1] * scale))
            new_height = max(1, int(gray.shape[0] * scale))
            while new_width * new_height > max_payload_pixels:
                if new_width >= new_height:
                    new_width -= 1
                else:
                    new_height -= 1
            gray = cv2.resize(gray, (new_width, new_height), interpolation=cv2.INTER_AREA)
        _threshold, binary = cv2.threshold(
            gray.astype(np.uint8), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        payload = np.packbits(binary.flatten() > 0).tobytes()
        packet_bits = len(_build_packet(KIND_IMAGE, payload, binary.shape[1], binary.shape[0])) * 8
        bucket = _choose_bucket(packet_bits, image_capacity_bits(cover.width, cover.height))
        return PreparedWatermark(
            binary=binary,
            png=encode_png(binary),
            width=binary.shape[1],
            height=binary.shape[0],
            resized=resized,
            capacity_bits=max(buckets),
            used_bits=bucket,
        )

    def embed_text(self, cover: DecodedImage, text: str, passphrase: str) -> bytes:
        if not text:
            raise AppError(422, "watermark_text_required", "缺少文字", "請輸入浮水印文字。")
        packet = _build_packet(KIND_TEXT, text.encode("utf-8"))
        return self._embed_packet(cover, packet, passphrase)

    def embed_image(
        self,
        cover: DecodedImage,
        watermark_data: bytes,
        passphrase: str,
    ) -> tuple[bytes, PreparedWatermark]:
        prepared = self.prepare_image_watermark(cover, watermark_data)
        payload = np.packbits(prepared.binary.flatten() > 0).tobytes()
        packet = _build_packet(KIND_IMAGE, payload, prepared.width, prepared.height)
        return self._embed_packet(cover, packet, passphrase), prepared

    def _embed_packet(self, cover: DecodedImage, packet: bytes, passphrase: str) -> bytes:
        capacity = image_capacity_bits(cover.width, cover.height)
        packet_bits = _bytes_to_bits(packet)
        bucket = _choose_bucket(len(packet_bits), capacity)
        bits = _pad_bits(packet_bits, bucket, passphrase)
        password_img, password_wm = derive_seeds(passphrase)
        engine = WaterMark(password_img=password_img, password_wm=password_wm)
        engine.read_img(img=cover.array.copy())
        engine.read_wm(bits, mode="bit")
        return encode_png(engine.embed())

    def extract(self, encoded: DecodedImage, passphrase: str) -> ExtractedWatermark:
        capacity = image_capacity_bits(encoded.width, encoded.height)
        candidates = usable_buckets(capacity)
        if not candidates:
            raise extraction_failed()
        password_img, password_wm = derive_seeds(passphrase)
        engine = WaterMark(password_img=password_img, password_wm=password_wm)
        core = engine.bwm_core
        core.wm_size = 1
        raw = core.extract_raw(encoded.array)

        for candidate in candidates:
            averages = np.array([raw[:, index::candidate].mean() for index in range(candidate)])
            if not np.isfinite(averages).all():
                continue
            low, high = float(averages.min()), float(averages.max())
            threshold = (low + high) / 2 if high > low else 0.5
            encrypted = averages > threshold
            permutation = np.arange(candidate)
            np.random.RandomState(password_wm).shuffle(permutation)
            decrypted = np.empty_like(encrypted)
            decrypted[permutation] = encrypted
            try:
                return _parse_packet(_bits_to_bytes(decrypted))
            except AppError:
                continue
        raise extraction_failed()

    def legacy_extract(
        self,
        encoded: DecodedImage,
        mode: Literal["text", "image"],
        password_img: int,
        password_wm: int,
        bit_length: int | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> ExtractedWatermark:
        engine = WaterMark(password_img=password_img, password_wm=password_wm)
        if mode == "text":
            if not bit_length or bit_length <= 0:
                raise AppError(422, "legacy_shape_required", "缺少長度", "請提供文字 bit 長度。")
            text = engine.extract(embed_img=encoded.array, wm_shape=bit_length, mode="str")
            return ExtractedWatermark(kind="text", text=text)
        if not width or not height or width <= 0 or height <= 0:
            raise AppError(422, "legacy_shape_required", "缺少尺寸", "請提供浮水印寬度及高度。")
        size = width * height
        engine.wm_size = size
        values = engine.bwm_core.extract(img=encoded.array, wm_shape=(height, width))
        values = engine.extract_decrypt(values)
        image = ((values.reshape((height, width)) >= 0.5) * 255).astype(np.uint8)
        return ExtractedWatermark(kind="image", png=encode_png(image), width=width, height=height)
