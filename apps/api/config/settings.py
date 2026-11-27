import os
from pathlib import Path
from decimal import Decimal
from corsheaders.defaults import default_headers

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent.parent

# Database variables are loaded from the repository's local .env and used only here.
load_dotenv(REPO_ROOT / ".env")
load_dotenv(BASE_DIR / ".env", override=True)

FINANCE_ESTIMATE_PER_100K = {
    "36m": Decimal(os.environ.get("NEXT_PUBLIC_FINANCE_36M_PER_100K", "3575.84")),
    "60m": Decimal(os.environ.get("NEXT_PUBLIC_FINANCE_60M_PER_100K", "2483")),
    "72m": Decimal(os.environ.get("NEXT_PUBLIC_FINANCE_72M_PER_100K", "2275")),
    "od": Decimal(os.environ.get("NEXT_PUBLIC_FINANCE_OD_PER_100K", "1330")),
}

DEBUG = os.environ.get("DJANGO_DEBUG", "1").lower() in {"1", "true", "yes", "on"}
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-change-me")
if not DEBUG and SECRET_KEY == "dev-only-change-me":
    raise RuntimeError("DJANGO_SECRET_KEY must be configured when DEBUG is disabled")


def _get_allowed_hosts(environ=None):
    environ = os.environ if environ is None else environ
    hosts = [
        host.strip()
        for host in environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
        if host.strip()
    ]
    render_hostname = environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
    if render_hostname and render_hostname not in hosts:
        hosts.append(render_hostname)
    return hosts


ALLOWED_HOSTS = _get_allowed_hosts()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"safe_csrf": {"()": "accounts.security.SafeCsrfLogFilter"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
        "csrf_console": {"class": "logging.StreamHandler", "filters": ["safe_csrf"]},
    },
    "loggers": {
        "django.security.DisallowedHost": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.security.csrf": {
            "handlers": ["csrf_console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "rest_framework",
    "corsheaders",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["POSTGRES_DB"],
        "USER": os.environ["POSTGRES_USER"],
        "PASSWORD": os.environ["POSTGRES_PASSWORD"],
        "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "PORT": os.environ.get("POSTGRES_PORT", "5433"),
    }
}

AUTH_USER_MODEL = "accounts.User"
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_RATES": {"anon": "10/minute", "public_enquiry": "5/hour", "import_tracking": "5/minute"},
}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # The same-origin web client reads this to send X-CSRFToken.
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SAMESITE = "Lax"
# The reverse proxy returns host-only CSRF cookies on the frontend origin.
# Never share authentication cookies across Render subdomains.
CSRF_COOKIE_DOMAIN = None
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.environ.get(
    "CSRF_TRUSTED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
).split(",") if origin.strip()]
CORS_ALLOW_CREDENTIALS = True
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend" if DEBUG else "accounts.email_backend.BrevoEmailBackend",
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "25"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "false").lower() in {"1", "true", "yes", "on"}
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "SSP Motor Trading <no-reply@localhost>")
COMPANY_LOCATION = os.environ.get("COMPANY_LOCATION", "").strip()
COMPANY_PHONE = os.environ.get("COMPANY_PHONE", os.environ.get("NEXT_PUBLIC_COMPANY_PHONE", "")).strip()
COMPANY_EMAIL = os.environ.get("COMPANY_EMAIL", os.environ.get("NEXT_PUBLIC_COMPANY_EMAIL", "")).strip()
ACCOUNT_PORTAL_URL = os.environ.get(
    "ACCOUNT_PORTAL_URL",
    "http://localhost:3000" if DEBUG else "https://ssp-frontend-xrli.onrender.com",
).rstrip("/")
SECURE_SSL_REDIRECT = not DEBUG
# Render terminates TLS at its proxy and forwards the original scheme. Trust
# that header so Django recognizes HTTPS and avoids redirect loops.
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]
CORS_ALLOW_HEADERS = [*default_headers, "idempotency-key"]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Colombo"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", BASE_DIR / "media"))
PRIVATE_PAYMENT_EVIDENCE_ROOT = Path(os.environ.get(
    "PRIVATE_PAYMENT_EVIDENCE_ROOT", BASE_DIR / "private_payment_evidence"
))
PRIVATE_HANDOVER_EVIDENCE_ROOT = Path(os.environ.get(
    "PRIVATE_HANDOVER_EVIDENCE_ROOT", BASE_DIR / "private_handover_evidence"
))
if not DEBUG:
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }
CSRF_FAILURE_VIEW = "accounts.security.csrf_failure"
DATA_UPLOAD_MAX_NUMBER_FILES = 10
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
