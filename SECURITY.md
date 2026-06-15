# Security Policy

## Reporting a vulnerability

Do not open a public issue for vulnerabilities involving authentication,
arbitrary file access, secret disclosure, IP spoofing, cryptography, or stored
uploads. Use the repository owner's private security contact or GitHub private
vulnerability reporting when enabled.

Include affected version, reproduction steps, impact, and suggested mitigation.
Do not include real user images, passphrases, keys, or database files.

## Deployment warnings

- Watermark passphrases control extraction but do not encrypt image content.
- `metadata` and `full` modes can retain personal data and recoverable secrets.
- The example `full` configuration stores data permanently.
- The public UI intentionally does not display a retention notice. Deployers
  are responsible for legal notice, consent, and access requirements.
- Use HTTPS for every non-local deployment.
- Restrict CORS origins and trusted proxy CIDRs.
- Store `WM_MASTER_KEYS`, admin credentials, and `JWT_SECRET` outside Git.
- Back up historical master keys separately from application data.
- Do not expose `/data` or artifacts as static files.

## Supported versions

Security fixes are applied to the latest released minor version. Older
development snapshots are not supported.
