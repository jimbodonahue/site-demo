# Site Layout Overview

## Core Apps
- **authentication** – User registration, login, password reset, and profile management.
- **courses** – Course catalog, detail pages, enrollment handling.
- **exercises** – Interactive exercises, difficulty presets, data generation (simulated/real).
- **sessions** – User session tracking (used by the JWT auth system).
- **token_blacklist** – JWT token revocation support.

## URL Structure
| Path | Purpose |
|------|---------|
| `/admin/` | Django admin interface (manage models, migrations, etc.) |
| `/courses/` | List of available courses and related views |
| `/exercises/` | Exercise listings, detail pages, and API endpoints |
| `/accounts/` | Account‑related pages (login, logout, signup, password reset) |
| `/terms/` | Terms of Service page |
| `/privacy/` | Privacy Policy page |
| `/cookies/` | Cookie Policy page |
| `/sitemap.xml` | Dynamically generated sitemap for SEO |
| `/` (home) | Welcome page with navigation links (see `templates/home.html`) |

## Template Structure
- **templates/home.html** – Landing page with links to the sections above.
- **templates/terms_of_services.html**, **privacy_policy.html**, **cookie_policy.html** – Static informational pages.
- **templates/robots.txt** – Simple robots file served via a view.

## Static & Media
- Static files are collected into `staticfiles/` (configured via `STATIC_ROOT`).
- Development static files live under `static/`.

## Settings Highlights
- `DEBUG` is enabled when `SERVER=development` (default via `.env`).
- CORS is open for localhost during development (`CORS_ALLOW_ALL_ORIGINS`).
- Database: SQLite for development, PostgreSQL for production.

## Navigation Flow
1. User lands on `/` → clicks a navigation link.
2. Accesses `/admin/` for admin tasks (requires superuser).
3. Browses courses or exercises via their respective endpoints.
4. Uses the authentication endpoints under `/accounts/` to manage their account.
5. Legal pages reachable from the footer links.

---
*All URLs respect the Django project’s `project_core.urls` configuration.*
