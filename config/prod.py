# config/prod.py
from .base import *  # noqa
import os
import dj_database_url  # pip install dj-database-url

# ---------------- Core toggles ----------------
DEBUG = False

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost"])
CSRF_TRUSTED_ORIGINS = env.list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    default=["http://localhost:8000", "http://127.0.0.1:8000"],
)

# ---------------- Database & Celery/Redis ----------------
DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL", default="postgres://nouvel:nouvel@db:5432/nouvel"),
        conn_max_age=600,
    )
}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=env("REDIS_URL", default="redis://redis:6379/0"))
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=CELERY_BROKER_URL)

# ---------------- Static files (WhiteNoise) ----------------
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

WN = "whitenoise.middleware.WhiteNoiseMiddleware"
if WN not in MIDDLEWARE:
    try:
        i = MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1
    except ValueError:
        i = 1
    MIDDLEWARE.insert(i, WN)

# ---------------- DRF sane defaults ----------------
REST_FRAMEWORK.setdefault("DEFAULT_PAGINATION_CLASS", "rest_framework.pagination.PageNumberPagination")
REST_FRAMEWORK.setdefault("PAGE_SIZE", 25)
REST_FRAMEWORK.setdefault(
    "DEFAULT_THROTTLE_CLASSES",
    [
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
    ],
)
REST_FRAMEWORK.setdefault(
    "DEFAULT_THROTTLE_RATES", {"user": "1000/hour", "anon": "100/hour"}
)

# ---------------- Structured logging (JSON) ----------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": "pythonjsonlogger.jsonlogger.JsonFormatter"},  # pip install python-json-logger
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "json"},
    },
    "root": {"handlers": ["console"], "level": os.getenv("DJANGO_LOG_LEVEL", "INFO")},
}

# ---------------- Security hardening ----------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"

# ---------------- Sentry (optional) ----------------
SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    try:
        import sentry_sdk  # pip install sentry-sdk
        from sentry_sdk.integrations.django import DjangoIntegration

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[DjangoIntegration()],
            traces_sample_rate=0.2,
        )
    except Exception:
        pass
