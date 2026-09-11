FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run gunicorn - Cloud Run uses port 8080
CMD python manage.py collectstatic --noinput && exec gunicorn --bind :8080 --workers 1 --threads 8 --timeout 0 project_core.wsgi:application