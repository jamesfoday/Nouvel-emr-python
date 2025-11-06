from pathlib import Path
import environ
import os

BASE_DIR = Path(__file__).resolve().parent.parent

# --- env bootstrap -----------------------------------------------------------
env = environ.Env()
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    environ.Env.read_env(ENV_FILE)

# --- core toggles ------------------------------------------------------------
SECRET_KEY = env.str("DJANGO_SECRET_KEY", default="dev-secret-please-change")
DEBUG = env.bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["127.0.0.1", "localhost"])
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# --- installed apps ----------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
 

    # Media via Cloudinary (media only; static stays on WhiteNoise)
    "cloudinary",
    "cloudinary_storage",

    # APIs
    "rest_framework",
    "drf_spectacular",
    "corsheaders",

    # Project apps
    "apps.accounts.apps.AccountsConfig",
    "apps.rbac",
    "apps.patients",
    "apps.appointments",
    "apps.clinical",
    "apps.documents",
    "apps.audit",
    "apps.clinicians.apps.CliniciansConfig",
    "apps.messaging.apps.MessagingConfig",
    "apps.prescriptions",
    "apps.encounters",
    "apps.labs",
    "apps.portal",
    "apps.reception",
    "apps.services",
    "apps.subscriptions",
    "apps.healthplans",
    "apps.invoices",
    "apps.inquiry",
    "apps.bugtracker",
    "apps.core",
    "apps.menus.apps.MenusConfig",
]

# --- middleware --------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # static in prod
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

# --- templates ---------------------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR / "templates",
            BASE_DIR / "apps" / "portal" / "templates",
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.menus.context_processors.menus_debug",
            ],
        },
    },
]

# --- database ---------------------------------------------------------------
DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
}

# --- auth / i18n / tz --------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
LANGUAGE_CODE = "en-us"
TIME_ZONE = env.str("DJANGO_TIME_ZONE", default="Europe/Paris")
USE_I18N = True
USE_TZ = True

# Login/Logout redirects
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/portal/"
LOGOUT_REDIRECT_URL = "/"

# --- static & media ----------------------------------------------------------
STATIC_URL = "/static/"
MEDIA_URL = "/media/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = BASE_DIR / "media"
STATICFILES_DIRS = [BASE_DIR / "static"]

# Use WhiteNoise for static (manifest) and choose media storage based on env.
USE_CLOUDINARY_MEDIA = env.bool("USE_CLOUDINARY_MEDIA", default=not DEBUG)
CLOUDINARY_URL = env.str("CLOUDINARY_URL", default="")

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
    "default": {
        # Cloudinary in prod (or when explicitly enabled), local FS in dev
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage"
        if (USE_CLOUDINARY_MEDIA and CLOUDINARY_URL)
        else "django.core.files.storage.FileSystemStorage"
    },
}

# Cloudinary extra options (media only)
if USE_CLOUDINARY_MEDIA and CLOUDINARY_URL:
    CLOUDINARY_STORAGE = {
        "DEFAULT_TAGS": ["nouvel-emr"],
        "PREFIX": "nouvel-emr/media",
        "OVERWRITE": False,
        # Leave FORMAT=None to keep the original format
    }

# --- DRF & OpenAPI -----------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": [
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "SEARCH_PARAM": "q",
    "ORDERING_PARAM": "sort",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Nouvel API",
    "VERSION": "0.2.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SWAGGER_UI_SETTINGS": {
        "persistAuthorization": True,
        "displayRequestDuration": True,
        "tryItOutEnabled": True,
    },
    "SECURITY": [{"bearerAuth": []}],
    "COMPONENT_SPLIT_REQUEST": True,
}

# --- CORS --------------------------------------------------------------------
CORS_ALLOW_ALL_ORIGINS = env.bool("CORS_ALLOW_ALL_ORIGINS", default=True)
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])

# --- passwords ---------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- email -------------------------------------------------------------------
DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL", default="no-reply@nouvel.local")
EMAIL_BACKEND = env.str("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env.str("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env.str("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env.str("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)

# --- Celery ------------------------------------------------------------------
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=True)
CELERY_TASK_EAGER_PROPAGATES = True
if CELERY_TASK_ALWAYS_EAGER:
    CELERY_BROKER_URL = "memory://"
    CELERY_RESULT_BACKEND = "cache+memory://"
else:
    CELERY_BROKER_URL = env.str(
        "CELERY_BROKER_URL",
        default=env.str("REDIS_URL", default="redis://localhost:6379/0"),
    )
    CELERY_RESULT_BACKEND = env.str("CELERY_RESULT_BACKEND", default=CELERY_BROKER_URL)

# --- flags & security --------------------------------------------------------
NOTIFY_APPOINTMENTS = env.bool("NOTIFY_APPOINTMENTS", default=True)
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=False)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=False)

if env.bool("USE_X_FORWARDED_PROTO", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# --- Render/WhiteNoise optimization ------------------------------------------
# Avoid repeated collectstatic issues on Render
os.environ.setdefault("DJANGO_COLLECTSTATIC", "1")

# (Do NOT set STATICFILES_STORAGE separately; STORAGES handles it.)
