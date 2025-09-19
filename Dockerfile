# Dockerfile
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml poetry.lock* requirements.txt* /app/
# If you use Poetry, install it; otherwise fallback to pip + requirements.txt
RUN if [ -f "pyproject.toml" ]; then \
      pip install --no-cache-dir poetry && poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi; \
    elif [ -f "requirements.txt" ]; then \
      pip install --no-cache-dir -r requirements.txt; \
    fi

COPY . /app

# collectstatic is a no-op for API, but handy if you add admin assets
RUN python manage.py collectstatic --noinput || true

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
