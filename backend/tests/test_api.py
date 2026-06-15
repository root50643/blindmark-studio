from __future__ import annotations

import base64
import io

from PIL import Image


def png_bytes(size=(256, 256), color=(80, 120, 180, 255)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_capabilities(client):
    response = client.get("/api/v1/capabilities")
    assert response.status_code == 200
    assert "image/png" in response.json()["formats"]
    assert response.json()["storage_mode"] == "metadata"


def test_invalid_upload_returns_problem_json(client):
    response = client.post(
        "/api/v1/watermark-extractions",
        files={"encoded_image": ("bad.png", b"not an image", "image/png")},
        data={"passphrase": ""},
    )
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "invalid_image"


def test_admin_login_and_empty_records(client):
    login = client.post(
        "/api/v1/admin/auth/login",
        json={"username": "admin", "password": "test-password"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    response = client.get(
        "/api/v1/admin/audit-records",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["total"] >= 0


def test_admin_endpoint_requires_problem_json_authentication(client):
    response = client.get("/api/v1/admin/audit-records")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "admin_authentication_required"


def test_text_round_trip(client):
    cover = png_bytes((512, 512))
    embedded = client.post(
        "/api/v1/watermarked-images",
        files={"cover_image": ("cover.png", cover, "image/png")},
        data={
            "watermark_type": "text",
            "watermark_text": "繁體中文 Watermark",
            "passphrase": "demo",
        },
    )
    assert embedded.status_code == 200, embedded.text
    extracted = client.post(
        "/api/v1/watermark-extractions",
        files={"encoded_image": ("encoded.png", embedded.content, "image/png")},
        data={"passphrase": "demo"},
    )
    assert extracted.status_code == 200, extracted.text
    assert extracted.json()["text"] == "繁體中文 Watermark"


def test_image_round_trip(client):
    cover = png_bytes((512, 512))
    watermark_buffer = io.BytesIO()
    watermark = Image.new("L", (16, 8), 255)
    for x in range(8):
        for y in range(8):
            watermark.putpixel((x, y), 0)
    watermark.save(watermark_buffer, format="PNG")

    embedded = client.post(
        "/api/v1/watermarked-images",
        files={
            "cover_image": ("cover.png", cover, "image/png"),
            "watermark_image": (
                "mark.png",
                watermark_buffer.getvalue(),
                "image/png",
            ),
        },
        data={"watermark_type": "image", "passphrase": "image-key"},
    )
    assert embedded.status_code == 200, embedded.text
    extracted = client.post(
        "/api/v1/watermark-extractions",
        files={"encoded_image": ("encoded.png", embedded.content, "image/png")},
        data={"passphrase": "image-key"},
    )
    assert extracted.status_code == 200, extracted.text
    body = extracted.json()
    assert body["kind"] == "image"
    assert body["width"] == 16
    assert body["height"] == 8
    assert base64.b64decode(body["image_data_url"].split(",", 1)[1]).startswith(b"\x89PNG")


def test_wrong_passphrase_uses_generic_error(client):
    cover = png_bytes((512, 512))
    embedded = client.post(
        "/api/v1/watermarked-images",
        files={"cover_image": ("cover.png", cover, "image/png")},
        data={
            "watermark_type": "text",
            "watermark_text": "secret",
            "passphrase": "correct",
        },
    )
    extracted = client.post(
        "/api/v1/watermark-extractions",
        files={"encoded_image": ("encoded.png", embedded.content, "image/png")},
        data={"passphrase": "wrong"},
    )
    assert extracted.status_code == 422
    assert extracted.json()["code"] == "watermark_extraction_failed"
