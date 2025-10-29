# Nouvel-EMR Dockerfile
FROM python:3.13-slim

# ----------------------------------------------------------------------
# Environment defaults
# ----------------------------------------------------------------------
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    WEB_CONCURRENCY=2 \
    PORT=8000 \
    DJANGO_SETTINGS_MODULE=config.prod

WORKDIR /app

# ----------------------------------------------------------------------
# System dependencies
# ----------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
 && rm -rf /var/lib/apt/lists/*

# ----------------------------------------------------------------------
# Python dependencies
# ----------------------------------------------------------------------
COPY requirements.txt* pyproject.toml* poetry.lock* /app/

# Use pip by default (safe for both Poetry & pip projects)
RUN if [ -f requirements.txt ]; then \
      pip install --upgrade pip && \
      pip install -r requirements.txt; \
    fi

# ----------------------------------------------------------------------
# Copy app code
# ----------------------------------------------------------------------
COPY . /app

# ----------------------------------------------------------------------
# Collect static files (optional – you can also run this in Render build)
# ----------------------------------------------------------------------
RUN python manage.py collectstatic --noinput || true

# ----------------------------------------------------------------------
# Expose and default command
# ----------------------------------------------------------------------
EXPOSE 8000

CMD gunicorn config.wsgi:application \
    --bind 0.0.0.0:${PORT} \
    --workers=${WEB_CONCURRENCY} \
    --access-logfile '-' \
    --error-logfile '-'

# ----------------------------------------------------------------------
# Optional health check (Docker/Compose)
# ----------------------------------------------------------------------
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://127.0.0.1:${PORT}/admin/login/ || exit 1
