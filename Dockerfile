FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Collect static at build time so the runtime user needs no write access to /app.
RUN SERVER=development DJANGO_SECRET_KEY=build-only-not-used \
    python manage.py collectstatic --noinput

# Student code runs in a subprocess of this process, so never run it as root.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

# Worker count tracks the Cloud Run CPU allocation. Keep the gunicorn timeout
# above EXERCISE_RUN_TIMEOUT so a slow notebook returns an error to the student
# rather than having its worker killed mid-request.
CMD exec gunicorn --bind :8080 --workers 2 --threads 4 --timeout 120 project_core.wsgi:application
