# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | Yes       |

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Instead, email the details to the maintainer privately. Include:

- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

You can expect an acknowledgement within **48 hours** and a resolution timeline within **7 days** for critical issues.

## Security Design Notes

- **JWT secrets** are never logged. The startup log records only the database scheme and scenario directory path.
- **Database credentials** (the full `DATABASE_URL`) are never exposed in logs or API responses.
- **Error responses** return only the `detail` string from `HTTPException` — no stack traces are returned to clients.
- **CORS** is restricted to the origin(s) listed in `ALLOWED_ORIGINS`.
- **Docker** containers run as a non-root user (uid 1001).
- The `.env` file is listed in `.gitignore` and must never be committed.
