# Dockerfile
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
 && rm -rf /var/lib/apt/lists/*

# Python deps
COPY pyproject.toml poetry.lock* requirements.txt* /app/
# Use either Poetry or pip; pick one. Here using pip requirements if present.
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi

# App code
COPY . /app

# Collect static at build if you prefer (compose already runs it too)
# RUN python manage.py collectstatic --noinput

EXPOSE 8000
