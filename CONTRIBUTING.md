# Contributing

## Development

- Python 3.11 is the supported backend baseline.
- Node.js 22 and pnpm are the supported frontend baseline.
- Create branches from the default branch and keep changes focused.
- Never commit `.env`, `config.yaml`, databases, uploads, or encryption keys.

Run before opening a pull request:

```bash
cd backend
ruff check .
mypy app
pytest

cd ../frontend
pnpm lint
pnpm test
pnpm build
```

When the REST contract changes, regenerate `openapi.json` and
`frontend/src/api/schema.d.ts` as described in `docs/MAINTENANCE.md`.

## Commits and pull requests

- Use an imperative, concise commit subject.
- Explain behavior changes, data migration, security implications, and tests.
- Add or update tests for every changed API behavior.
- Update documentation and `CHANGELOG.md` for user-visible changes.
- Preserve compatibility with existing self-describing watermark version 1,
  or introduce an explicit new version.
