# config/settings.py
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# I’m keeping secrets/dev knobs in this file for now; prod will move to env vars.
SECRET_KEY = "django-insecure-gr-wwms)((ba(-e)gvrpzfhu^)xxys@48v25pwd2&*%1deq5nq"
DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

# --- Apps ---
INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    # Local
    "apps.accounts.apps.AccountsConfig",
    "apps.rbac",
    "apps.patients",
    "apps.appointments",
    "apps.clinical",
    "apps.documents",
    "apps.audit",
]

# --- Middleware ---
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    #  serving static assets via Whitenoise (keeps dev/prod simple).
    "whitenoise.middleware.WhiteNoiseMiddleware",
    # CORS placed early so headers are added before common middleware runs.
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Templates ---
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # I want a global templates dir for base layouts + includes.
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Database (SQLite in dev; I’ll move to Postgres via DATABASE_URL later) ---
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# --- Auth ---
# The app label is `accounts` because the app lives in apps/accounts/.
AUTH_USER_MODEL = "accounts.User"

# --- I18N / TZ ---
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Europe/Paris"  # I’m aligning to my working timezone.
USE_I18N = True
USE_TZ = True

# --- Static & Media ---
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Django 5 storage API. I’m using the compressed manifest storage for cache busting.
STORAGES = {
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
}

# --- DRF & OpenAPI ---
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    # Pagination: limit/offset (limit defaults to PAGE_SIZE if omitted)
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 25,
    # Filters
    "DEFAULT_FILTER_BACKENDS": [
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    # keep our param names human: q for search, sort for ordering
    "SEARCH_PARAM": "q",
    "ORDERING_PARAM": "sort",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Nouvel API",
    "VERSION": "0.2.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SWAGGER_UI_SETTINGS": {
    "persistAuthorization": True,        # want the padlock to remember auth on reload
    "displayRequestDuration": True,      # like seeing timing in the UI
    "tryItOutEnabled": True,             # ensure Try it out is present
    },
}


# --- CORS (open in dev; I’ll lock this down in prod) ---
CORS_ALLOW_ALL_ORIGINS = True

# --- Passwords / defaults ---
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "nouvel@localhost"


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
