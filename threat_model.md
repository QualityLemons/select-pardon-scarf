# Threat Model

## Project Overview

PLeC is a Django-based training platform for PLC engineering concepts. Production traffic enters a Django 5.2 application that serves static challenge pages and a small JSON API for assessment scoring and result history. Authentication uses Django sessions with a custom email-based user model and django-axes for login lockouts. Data is stored in PostgreSQL (Replit's managed database, configured via the `DATABASE_URL` environment variable); a local SQLite file (`plec.db`) is used only as a local-development fallback when `DATABASE_URL` is unset and must never be relied on in production. The project is not currently deployed, so this scan assumes a future production deployment exposed on the public internet unless deployment visibility later narrows that scope.

## Assets

- **User accounts and sessions** — administrator and learner accounts, password hashes, session cookies, and password-reset tokens. Compromise enables impersonation and access to protected pages and administrative functions.
- **Assessment history** — stored assessment results, timestamps, grades, milestone counts, and learner-entered notes. These records are user-specific education data and should not be readable or mutable by other users or anonymous visitors.
- **Administrative capabilities** — Django admin access, password changes, and user management. Abuse would allow broad application takeover.
- **Application secrets and email settings** — `DJANGO_SECRET_KEY`, mail configuration, and other environment-based secrets. Disclosure could enable session forgery or abuse of account-recovery flows.

## Trust Boundaries

- **Browser to Django application** — all client input from challenge pages, login forms, registration, and password-reset flows is untrusted and must be authenticated, authorized, and validated server-side.
- **Authenticated user to unauthenticated visitor** — challenge pages are public, but user-specific result history and all administrative functions must remain private.
- **Application to database** — Django ORM writes learner results and user data into PostgreSQL; API-layer authorization failures directly expose or corrupt stored records.
- **Application to email recipient** — password-reset links cross a trust boundary from server-generated secrets into user-controlled email clients and browsers.
- **Development-only to production** — `serve.py`, direct static serving under `DEBUG`, and other legacy/local-only paths should be ignored unless production routing explicitly uses them.

## Scan Anchors

- Production entry points: `plec_project/urls.py`, `plec_project/wsgi.py`, `plec_project/asgi.py`, `plec_project/settings.py`
- Highest-risk code areas: `apps/assessment/api_views.py`, `challenge/assess.js`, `apps/accounts/views.py`, `templates/registration/`, `apps/accounts/admin.py`
- Public surfaces: `/`, `/challenge/`, `/login/`, `/register/`, `/password-reset/`, `/api/modules`, `/api/tips/<module_id>`, `/api/assess`, challenge static assets under `challenge/`
- Authenticated/admin surfaces: `/profile/`, `/password-change/`, `/admin/`, `/api/results`, `/api/results/<rid>`
- Usually dev-only unless proven otherwise: `serve.py`, `create_db.py`, `DEBUG`-only `challenge/<path>` serving in `plec_project/urls.py`

## Threat Categories

### Spoofing

This project relies on Django sessions and password-based login for access to admin and learner-only pages. The application must validate credentials through Django’s authentication pipeline on every protected route, must preserve unpredictable session state, and must ensure redirect or recovery flows cannot be abused to steer users to attacker-controlled destinations.

### Tampering

Assessment results and administrative actions are sensitive because they represent user progress and can affect what learners or staff see. Any endpoint that creates, updates, or deletes stored results must enforce server-side authorization, must bind changes to the correct user, and must not trust browser-supplied score or grade data as authoritative evidence of challenge completion.

### Information Disclosure

The main confidentiality risk is exposure of user-specific assessment history or account-recovery data through public endpoints, overly broad JSON responses, or weak reset-link handling. User result records and reset flows must disclose only the minimum data required to the authenticated owner or authorized administrator.

### Denial of Service

Public login, registration, password-reset, and API endpoints can be abused for repeated requests or unbounded writes. Login protection must continue to rate-limit brute force attempts, and public write or recovery paths must not allow low-cost account lockout, mailbox flooding, or database growth that degrades service availability.

### Elevation of Privilege

The most likely privilege-escalation paths are broken access control in result APIs, missing ownership checks on object IDs, misuse of admin or authentication redirects, and password-reset token exposure. The system must enforce object-level authorization on every result record and keep administrative capabilities unreachable to ordinary or anonymous users.
