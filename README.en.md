# Blindmark Studio

Blindmark Studio is a separated React and FastAPI application for embedding
and extracting invisible text or image watermarks through a versioned REST API.
It uses
[`blind-watermark` 0.4.4](https://github.com/guofei9987/blind_watermark)
as an external MIT-licensed dependency.

## Highlights

- UTF-8 text and monochrome image watermarks.
- Self-describing payloads with version, dimensions, length, and CRC32.
- Compatibility mode for watermarks produced by the upstream project.
- Configurable `off`, `metadata`, and `full` audit storage.
- SQLite WAL, AES-256-GCM protected passphrases, and trusted proxy handling.
- React administration UI, FastAPI OpenAPI schema, and Docker Compose.

## Quick start

1. Copy `config.example.yaml` to `config.yaml`.
2. Copy `.env.example` to `.env`.
3. Replace every placeholder secret, including a Base64URL encoded 32-byte
   `WM_MASTER_KEYS` value.
4. Run `docker compose up --build`.

The UI is available at `http://localhost:3000`, the admin UI at
`http://localhost:3000/admin`, and Swagger UI at
`http://localhost:8000/docs`.

The default example configuration permanently stores full uploads and
outputs. Review the [Traditional Chinese README](README.md),
[maintenance guide](docs/MAINTENANCE.md), and [security policy](SECURITY.md)
before deployment.
