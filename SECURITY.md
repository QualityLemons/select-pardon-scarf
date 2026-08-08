# Security Policy

## Supported Versions

PLeC is an actively maintained project. Security fixes are applied to the current `main` branch only.

| Version | Supported |
|---------|-----------|
| Latest (`main`) | ✅ |
| Older snapshots / forks | ❌ |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

If you discover a vulnerability, email the maintainer directly:

**John Parman — j.parman@dudleycol.ac.uk**

Include as much of the following as possible:

- A description of the vulnerability and its potential impact
- The URL or file path where the issue occurs
- Steps to reproduce (proof-of-concept or screenshot if safe to share)
- Your suggested fix, if you have one

You will receive an acknowledgement within **5 working days**. If the issue is confirmed, a fix will be prioritised and you will be credited in the release notes unless you prefer to remain anonymous.

## Scope

The following are **in scope**:

- Authentication and session handling (`/login/`, `/register/`, `/password-reset/`)
- Learner data isolation (one user accessing another user's results or reflections)
- Admin panel access control (`/admin/`)
- CSRF, XSS, and injection vulnerabilities in any view or form
- Sensitive data exposure (keys, tokens, or PII in responses or logs)
- Rate limiting and brute-force protections

The following are **out of scope**:

- Findings from automated scanners submitted without a proof of concept
- Issues that require physical access to the server
- Social engineering attacks against staff

## Security Design Notes

For contributors and reviewers, the key security decisions in this codebase are:

- **No secrets in source** — `DJANGO_SECRET_KEY`, `DATABASE_URL`, and all credentials are read exclusively from environment variables. The app refuses to start if `DJANGO_SECRET_KEY` is absent.
- **DEBUG off in production** — `DEBUG` defaults to `False`; all HTTPS/HSTS/secure-cookie settings activate automatically when `DJANGO_DEBUG` is not `True`.
- **Learner data isolation** — Every view that touches assessment results or reflection entries is scoped to `user=request.user`. URL-guessing is not sufficient to access another learner's data.
- **Brute-force protection** — `django-axes` enforces a 5-attempt lockout on login, keyed on `(username, ip_address)`. The password-reset endpoint applies the same limit via cache-based rate limiting.
- **Open redirect protection** — The `?next=` parameter on the login page is validated with Django's `url_has_allowed_host_and_scheme()` before any redirect is issued.
- **CSRF protection** — All state-changing forms use Django's built-in CSRF middleware. CSRF cookies are marked `Secure` in production.
