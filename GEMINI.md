# GEMINI.md - Repository Context & Guide for AI Coding Agents

This file provides comprehensive architectural context, project metadata, structural layout, and runtime conventions for AI coding assistants working in this repository.

---

## 1. Project Overview & Tech Stack

- **Project Name**: Django Interactive Learning & Exercise Platform (`django-platform` / `huzaifazahoor/django-boilerplate`)
- **Framework**: Django 6.0 / 5.0+ (Python 3.x) with Django REST Framework (DRF) & SimpleJWT authentication.
- **Database**:
  - Development: SQLite (`db.sqlite3`)
  - Production: PostgreSQL via `psycopg2-binary` / `dj-database-url`
- **Frontend / Content**: Django Template Language (DTL) HTML5 views, Markdown rendering (`markdown` package with `fenced_code` and `tables` extensions), WhiteNoise static file handling.
- **Execution Sandbox**: In-browser interactive Python notebook runner using standard library `ast` parsing, sandboxed safe builtins, and Matplotlib PNG figure extraction.
- **Cloud & Deployment**: Google App Engine (`app.yaml`), Google Cloud Run (`Dockerfile`), Cloud Functions (`scripts/deploy_cloud_functions.sh`), Google Cloud SQL Proxy (`cloud_sql_proxy.exe`), GitHub Actions CI/CD (`.github/workflows/`).

---

## 2. Runtime & Configuration Rules

- **Active Settings**: `project_core.settings` (configured via `DJANGO_SETTINGS_MODULE` in [`manage.py`](file:///home/jim/django-platform/manage.py)).
  - *Note*: The repository contains a legacy/experimental [`project/settings.py`](file:///home/jim/django-platform/project/settings.py) (featuring Django Unfold Admin / Tailwind configurations). The primary active application settings reside in [`project_core/settings.py`](file:///home/jim/django-platform/project_core/settings.py).
- **Environment Management**: Configured via `python-dotenv` reading `.env`. Required keys include `DJANGO_SECRET_KEY` and `SERVER` (`development` | `production`).
- **Custom User Model**: [`apps.authentication.models.CustomUser`](file:///home/jim/django-platform/apps/authentication/models.py) configured via `AUTH_USER_MODEL = "authentication.CustomUser"`. Login is email-based (`USERNAME_FIELD = "email"`).
- **Interactive Exercise Sandbox**: Code evaluation logic lives in [`apps/exercises/services.py`](file:///home/jim/django-platform/apps/exercises/services.py). Code cells are delimited by `# %%` markers. Raw import statements are blocked by AST analysis (`_validate_imports`); preloaded aliases include `numpy as np`, `pandas as pd`, and `matplotlib.pyplot as plt`.

---

## 3. Core Application Architecture

```
apps/
├── authentication/  # User identity, custom user model, email verification & auth views
├── courses/         # Course, Module, and Lesson curriculum models with markdown rendering
├── exercises/       # Interactive exercise definitions, visitor attempts & AST execution sandbox
└── forum/           # Community discussion topics & posts (optionally linked to exercises)
```

---

## 4. Annotated Directory & File Tree

Below is the complete human-readable directory structure, annotated with the functionality of each branch and file:

```
django-platform/
├── .github/                              # GitHub repository configuration and CI/CD pipelines
│   └── workflows/                        # GitHub Actions workflow definitions
│       ├── deploy-cloud-functions.yml    # Workflow for deploying Google Cloud Functions
│       ├── deploy-cloud-run.yml          # Workflow for building & deploying container to Google Cloud Run
│       └── deploy.yml                    # Workflow for deploying application to Google App Engine
├── apps/                                 # Modular Django applications container
│   ├── authentication/                   # User authentication, identity, and account management app
│   │   ├── admin.py                      # Admin interface registration for CustomUser
│   │   ├── apps.py                       # App configuration metadata (AuthenticationConfig)
│   │   ├── forms.py                      # Forms for signup, login, password reset, and verification
│   │   ├── managers.py                   # CustomUserManager handling email-based user creation
│   │   ├── migrations/                   # Database schema migrations for authentication models
│   │   ├── models.py                     # CustomUser model (email primary key, verification flags)
│   │   ├── tests.py                      # Unit tests for authentication logic
│   │   ├── tokens.py                     # Token generators for email verification & password reset
│   │   ├── urls.py                       # URL routing for authentication endpoints
│   │   └── views.py                      # Views for login, signup, verification, and logout
│   ├── courses/                          # Curriculum structure and content delivery app
│   │   ├── admin.py                      # Admin registration for Course, Module, and Lesson models
│   │   ├── apps.py                       # App configuration metadata (CoursesConfig)
│   │   ├── migrations/                   # Database schema migrations for courses models
│   │   ├── models.py                     # Course, Module, Lesson models with Markdown rendering
│   │   ├── tests.py                      # Unit tests for course data models and views
│   │   ├── urls.py                       # URL routing for course listings and lesson views
│   │   └── views.py                      # Catalog listing and lesson detail views
│   ├── exercises/                        # Interactive Python exercise & AST sandbox evaluation app
│   │   ├── admin.py                      # Admin registration for Exercise and ExerciseAttempt models
│   │   ├── apps.py                       # App configuration metadata (ExercisesConfig)
│   │   ├── migrations/                   # Database schema migrations for exercise models
│   │   ├── models.py                     # Exercise (starter code, rules) and ExerciseAttempt models
│   │   ├── services.py                   # Sandbox execution core: AST parsing, safe builtins & figure capture
│   │   ├── tests.py                      # Unit tests for sandbox security, AST validation & rules evaluation
│   │   ├── urls.py                       # URL routing for exercise views, run endpoint, and reset endpoint
│   │   └── views.py                      # ExerciseDetailView, run_exercise API, and reset_exercise API
│   └── forum/                            # Community discussion forum app
│       ├── admin.py                      # Admin registration for Topic and Post models
│       ├── apps.py                       # App configuration metadata (ForumConfig)
│       ├── forms.py                      # Forms for topic creation and reply posting
│       ├── migrations/                   # Database schema migrations for forum models
│       ├── models.py                     # Topic (linked to Exercise) and Post models
│       ├── tests.py                      # Unit tests for forum views and models
│       ├── urls.py                       # URL routing for forum thread listings and topic detail
│       └── views.py                      # Views for forum thread creation, listing, and reply submission
├── project_core/                         # Active primary Django project package
│   ├── __init__.py                       # Package initializer
│   ├── asgi.py                           # Asynchronous Server Gateway Interface entrypoint
│   ├── settings.py                       # Active project settings (DB, Installed Apps, DRF, JWT, Static)
│   ├── sitemap.py                        # Static view sitemap generator for SEO
│   ├── urls.py                           # Root URL configuration hub linking to app routes
│   ├── utils.py                          # Common model mixins (e.g., TimeStampMixin)
│   └── wsgi.py                           # Web Server Gateway Interface entrypoint for deployment
├── project/                              # Secondary / experimental settings package
│   └── settings.py                       # Alternate settings file (Unfold Admin, Tailwind, GCS setup)
├── scripts/                              # Utility scripts for maintenance and deployment
│   ├── common/                           # Shared utility Python modules for scripts
│   │   └── utils.py                      # Helper functions for automated script execution
│   ├── deploy_cloud_functions.sh         # Deployment shell script for Google Cloud Functions
│   ├── README.md                         # Documentation for executing repository maintenance scripts
│   └── requirements.txt                  # Python dependencies required specifically by deployment scripts
├── static/                               # Static source files directory
│   └── imgs/                             # Images, graphics, and visual assets used across templates
├── staticfiles/                          # Production collected static files output directory
├── templates/                            # Main HTML template directory (Django Template Language)
│   ├── authentication/                   # Templates for login, signup, verification, password reset
│   ├── courses/                          # Templates for course listing, course details, and lessons
│   ├── exercises/                        # Templates for interactive exercise runner notebook interface
│   ├── forum/                            # Templates for forum index, topic detail, and creation forms
│   ├── base.html                         # Master layout template (navbar, footer, global styles & scripts)
│   ├── home.html                         # Platform landing homepage template
│   └── robots.txt                        # Search engine crawling rules template
├── .dockerignore                         # Files excluded from Docker container build context
├── .env                                  # Local environment configuration file (secrets, server mode)
├── .gitignore                            # Files excluded from Git version control
├── Dockerfile                            # Docker container build specification for Cloud Run
├── EXERCISE_AUTHORING_GUIDE.md           # Instructions for creating and formatting exercise definitions
├── Local Progress Tracking Plan.md       # Architecture plan for client-side exercise state persistence
├── TEACHER_MISSING_VALUES_EXERCISE_GUIDE.md # Guide for creating data cleaning exercises
├── README.md                             # Repository setup guide, feature highlights & quickstart instructions
├── app.yaml                              # Google App Engine deployment descriptor
├── cloud_sql_proxy.exe                   # Binary tool for local connection to Google Cloud SQL database
├── db.sqlite3                            # Local development SQLite database file
├── dispatch.yaml                         # Google App Engine dispatch rules for routing requests
├── docker-compose.yml                    # Docker Compose configuration for local containerized environment
├── manage.py                             # Django command-line utility entrypoint script
├── plan-notebook.md                      # Technical design document for notebook execution UI
├── plan.md                               # Overall platform development plan & milestone roadmap
├── pyproject.toml                        # Build system configuration and project metadata
├── requirements.txt                      # Production Python package requirements list
├── site_layout.md                        # Platform site structure and navigation wireframe spec
└── uv.lock                               # Package lockfile for uv dependency manager
```

---

## 5. Helpful Commands for Agents

- **Virtual Environment Interpreter**: Use `.venv/bin/python`
- **Run Dev Server**: `.venv/bin/python manage.py runserver`
- **Run Migrations**: `.venv/bin/python manage.py makemigrations && .venv/bin/python manage.py migrate`
- **Run Tests**: `.venv/bin/python manage.py test apps`
- **Create Superuser**: `.venv/bin/python manage.py createsuperuser`
- **Collect Static Files**: `.venv/bin/python manage.py collectstatic --noinput`
