# AGENTS.md - Repository Context & Guide for AI Coding Agents

## 1. Project Overview & Tech Stack

- **Project Name**: Jim's Data Gym (`django-site`)
- **Framework**: Django 6.0 / 5.0+ (Python 3.x), Django Template Language views
- **Database**: SQLite in development (`db.sqlite3`); PostgreSQL in production
- **Frontend / Content**: DTL HTML5, Markdown (`fenced_code`, `tables`), WhiteNoise
- **Execution Sandbox**: Server-side Python notebook runner (`apps/exercises/services.py`) with AST import checks and Matplotlib figure capture
- **Identity**: Passkey/token membership for learners (`CustomUser.token`); email+password for staff/admin only
- **Deployment**: Google Cloud Run (`Dockerfile`), GitHub Actions CI (`.github/workflows/ci.yml`)

## 2. Runtime & Configuration

- **Settings**: `project_core.settings` via `DJANGO_SETTINGS_MODULE`
- **Env**: `python-dotenv` / `.env` — `DJANGO_SECRET_KEY`, `SERVER` (`development` | `production`)
- **Auth user model**: `AUTH_USER_MODEL = "authentication.CustomUser"` (`USERNAME_FIELD = "email"` for staff)
- **Exercise content**: `apps/exercises/content/exercises/<slug>/` synced with `manage.py sync_exercise_content`

## 3. Core Apps

```
apps/
├── authentication/  # Passkey membership, profiles, connections, account deletion
├── exercises/       # Tracks, notebook sandbox, Data Zoo, Cardio placeholder
├── forum/           # Topics/posts, CoC, Alert Admin, forum-only suspension
├── badges/          # Award catalog tied to passkey accounts
├── challenges/      # Weekly challenges
├── metrics/         # Optional anonymous usage metrics
├── sitepages/       # Landing, About, feedback/bug reports
└── courses/         # Migration history only (curriculum removed)
```

## 4. Helpful Commands

- Interpreter: `.venv/bin/python`
- Dev server: `.venv/bin/python manage.py runserver`
- Migrations: `.venv/bin/python manage.py makemigrations && .venv/bin/python manage.py migrate`
- Tests: `.venv/bin/python manage.py test apps`
- Purge due account deletions: `.venv/bin/python manage.py purge_account_deletions`
