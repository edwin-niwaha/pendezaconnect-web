import os
import sys
from datetime import timedelta
from pathlib import Path

import dj_database_url
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
IS_TESTING = "test" in sys.argv


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() == "true"


NOTIFICATION_DELIVERY_ENABLED = env_bool(
    "NOTIFICATION_DELIVERY_ENABLED",
    not IS_TESTING,
)


def env_float(name, default):
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


def env_list(name):
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


def database_config(ssl_require=False):
    if os.getenv("DATABASE_URL"):
        return {
            "default": dj_database_url.config(
                default=os.getenv("DATABASE_URL"),
                conn_max_age=600,
                ssl_require=ssl_require,
            )
        }

    return {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "default_db_name"),
            "USER": os.environ.get("DB_USER", "default_user"),
            "PASSWORD": os.environ.get("DB_PASSWORD", "default_password"),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        }
    }


SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "development-only-fallback-secret-key-change-in-railway-env-2026",
)

DEBUG = env_bool("DEBUG", False)

SITE_NAME = "Sponsorship Database"
BASE_DOMAIN = "sponsorwithpendeza.org"
SITE_URL = os.environ.get("SITE_URL", f"https://{BASE_DOMAIN}")

RAILWAY_PUBLIC_DOMAIN = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
ALLOWED_HOSTS = [BASE_DOMAIN, ".up.railway.app"]
if RAILWAY_PUBLIC_DOMAIN:
    ALLOWED_HOSTS.append(RAILWAY_PUBLIC_DOMAIN)
ALLOWED_HOSTS.extend(env_list("ALLOWED_HOSTS"))

CSRF_TRUSTED_ORIGINS = ["https://sponsorwithpendeza.org"]
if RAILWAY_PUBLIC_DOMAIN:
    CSRF_TRUSTED_ORIGINS.append(f"https://{RAILWAY_PUBLIC_DOMAIN}")
CSRF_TRUSTED_ORIGINS.extend(env_list("CSRF_TRUSTED_ORIGINS"))

CORS_ALLOWED_ORIGINS = [SITE_URL, *env_list("CORS_ALLOWED_ORIGINS")]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "social_django",
    "bootstrap5",
    "formtools",
    "crispy_forms",
    "crispy_bootstrap5",
    "django.contrib.humanize",
    "django_select2",
    "cloudinary",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_yasg",
    "corsheaders",
    "apps.users",
    "apps.child",
    "apps.staff",
    "apps.sponsor",
    "apps.finance",
    "apps.sponsorship",
    "apps.client",
    "apps.reports",
    "apps.dashboard",
    "apps.loans",
    "apps.savings",
    "apps.inventory.customers",
    "apps.inventory.supplier",
    "apps.inventory.products",
    "apps.inventory.sales",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "social_django.middleware.SocialAuthExceptionMiddleware",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR, BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "social_django.context_processors.backends",
                "social_django.context_processors.login_redirect",
                "apps.users.context_processors.guest_profiles_context",
                "apps.users.context_processors.guest_user_feedback_context",
                "apps.users.context_processors.low_stock_alerts_context",
                "apps.loans.context_processors.loan_dashboard_context",
                "apps.savings.context_processors.savings_notifications_context",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"

DATABASES = database_config(ssl_require=env_bool("DATABASE_SSL_REQUIRE", False))

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

AUTHENTICATION_BACKENDS = (
    "social_core.backends.github.GithubOAuth2",
    "social_core.backends.google.GoogleOAuth2",
    "django.contrib.auth.backends.ModelBackend",
)

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_L10N = True
USE_TZ = True

MEDIA_ROOT = BASE_DIR / "media"
LOCAL_MEDIA_URL = "/media/"

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = (
    "django.contrib.staticfiles.storage.StaticFilesStorage"
    if IS_TESTING
    else "whitenoise.storage.CompressedManifestStaticFilesStorage"
)

CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")

CLOUDINARY_STORAGE = {
    "CLOUD_NAME": CLOUDINARY_CLOUD_NAME,
    "API_KEY": CLOUDINARY_API_KEY,
    "API_SECRET": CLOUDINARY_API_SECRET,
}

DEFAULT_FILE_STORAGE = "cloudinary_storage.storage.MediaCloudinaryStorage"
MEDIA_URL = f"https://res.cloudinary.com/{CLOUDINARY_CLOUD_NAME}/"

LOGIN_REDIRECT_URL = "/"
LOGIN_URL = "login"

SOCIAL_AUTH_GITHUB_KEY = str(os.getenv("GITHUB_KEY"))
SOCIAL_AUTH_GITHUB_SECRET = str(os.getenv("GITHUB_SECRET"))
SOCIAL_AUTH_GOOGLE_OAUTH2_KEY = str(os.getenv("GOOGLE_KEY"))
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = str(os.getenv("GOOGLE_SECRET"))
MOBILE_GOOGLE_CLIENT_IDS = env_list("MOBILE_GOOGLE_CLIENT_IDS")
for google_client_id in (
    os.getenv("GOOGLE_CLIENT_ID"),
    os.getenv("GOOGLE_KEY"),
    os.getenv("EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID"),
):
    if google_client_id and google_client_id not in MOBILE_GOOGLE_CLIENT_IDS:
        MOBILE_GOOGLE_CLIENT_IDS.append(google_client_id)
SOCIAL_AUTH_REQUESTS_TIMEOUT = env_float("SOCIAL_AUTH_REQUESTS_TIMEOUT", 10)
SOCIAL_AUTH_PIPELINE = (
    "social_core.pipeline.social_auth.social_details",
    "social_core.pipeline.social_auth.social_uid",
    "social_core.pipeline.social_auth.auth_allowed",
    "social_core.pipeline.social_auth.social_user",
    "apps.users.pipeline.associate_verified_google_email",
    "social_core.pipeline.user.get_username",
    "social_core.pipeline.user.create_user",
    "social_core.pipeline.social_auth.associate_user",
    "social_core.pipeline.social_auth.load_extra_data",
    "social_core.pipeline.user.user_details",
    "apps.users.pipeline.require_google_login_token",
)

# Redis / Celery
# Prefer explicit Celery variables when set, otherwise fall back to REDIS_URL.
# This makes Railway deployments easier because web and worker services can use
# either REDIS_URL, CELERY_BROKER_URL, or CELERY_RESULT_BACKEND.
REDIS_URL = os.environ.get("REDIS_URL")

CACHES = {
    "default": {
        "BACKEND": (
            "django.core.cache.backends.redis.RedisCache"
            if REDIS_URL
            else "django.core.cache.backends.locmem.LocMemCache"
        ),
        "LOCATION": REDIS_URL or "pendeza-connect-local-cache",
        "TIMEOUT": 300,
    }
}

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL") or REDIS_URL
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND") or REDIS_URL

if not CELERY_BROKER_URL:
    raise Exception("CELERY_BROKER_URL or REDIS_URL is not set!")

if not CELERY_RESULT_BACKEND:
    raise Exception("CELERY_RESULT_BACKEND or REDIS_URL is not set!")

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Africa/Kampala"
CELERY_BEAT_SCHEDULE = {
    "daily-push-loan-reminders": {
        "task": "apps.loans.tasks.send_push_loan_reminders",
        "schedule": crontab(hour=8, minute=0),
    },
    "monthly-push-sponsorship-reminders": {
        "task": "apps.sponsorship.tasks.send_push_sponsorship_reminders",
        "schedule": crontab(day_of_month="5", hour=9, minute=0),
    },
}
CELERY_TASK_DEFAULT_QUEUE = os.environ.get(
    "CELERY_TASK_DEFAULT_QUEUE",
    "pendeza_connect",
)
CELERY_TASK_DEFAULT_EXCHANGE = CELERY_TASK_DEFAULT_QUEUE
CELERY_TASK_DEFAULT_ROUTING_KEY = CELERY_TASK_DEFAULT_QUEUE
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_WORKER_CONCURRENCY = int(os.environ.get("CELERY_WORKER_CONCURRENCY", "1"))
CELERY_WORKER_PREFETCH_MULTIPLIER = int(os.environ.get("CELERY_WORKER_PREFETCH_MULTIPLIER", "1"))
CELERY_WORKER_MAX_TASKS_PER_CHILD = int(os.environ.get("CELERY_WORKER_MAX_TASKS_PER_CHILD", "50"))
CELERY_WORKER_MAX_MEMORY_PER_CHILD = int(os.environ.get("CELERY_WORKER_MAX_MEMORY_PER_CHILD", "300000"))
CELERY_TASK_SOFT_TIME_LIMIT = int(os.environ.get("CELERY_TASK_SOFT_TIME_LIMIT", "300"))
CELERY_TASK_TIME_LIMIT = int(os.environ.get("CELERY_TASK_TIME_LIMIT", "360"))
CELERY_RESULT_EXPIRES = int(os.environ.get("CELERY_RESULT_EXPIRES", "3600"))

EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "10"))
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_API_URL = os.getenv("RESEND_API_URL", "https://api.resend.com/emails")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "")
DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL",
    RESEND_FROM_EMAIL or EMAIL_HOST_USER,
)
if not RESEND_FROM_EMAIL:
    RESEND_FROM_EMAIL = DEFAULT_FROM_EMAIL
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    ("core.email_backends.ResendEmailBackend" if RESEND_API_KEY else "django.core.mail.backends.smtp.EmailBackend"),
)

BOO_EMAIL = os.getenv("BOO_EMAIL", "")
HOF_EMAIL = os.getenv("HOF_EMAIL", "")
ED_EMAIL = os.getenv("ED_EMAIL", "")
ACCOUNTANT_EMAIL = os.getenv("ACCOUNTANT_EMAIL", "")
PROGS_ADMIN_EMAIL = os.getenv("PROGS_ADMIN_EMAIL", "")

SESSION_COOKIE_AGE = 7200
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/minute",
        "user": "600/minute",
        "login": "5/minute",
        "password_reset": "3/hour",
        "payment_start": "10/minute",
        "payment_status": "60/minute",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
}

SWAGGER_SETTINGS = {
    "SECURITY_DEFINITIONS": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "JWT access token. Enter: Bearer <access_token>",
        }
    },
    "USE_SESSION_AUTH": False,
    "PERSIST_AUTH": True,
    "DOC_EXPANSION": "none",
    "OPERATIONS_SORTER": "alpha",
    "TAGS_SORTER": "alpha",
}

REDOC_SETTINGS = {
    "LAZY_RENDERING": True,
    "EXPAND_RESPONSES": "200,201",
}

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "level": os.environ.get("DJANGO_LOG_LEVEL", "DEBUG"),
            "class": "logging.StreamHandler",
        },
        "file": {
            "level": os.environ.get("DJANGO_LOG_LEVEL", "DEBUG"),
            "class": "logging.FileHandler",
            "filename": LOGS_DIR / "app.log",
        },
    },
    "loggers": {
        "": {
            "handlers": ["console", "file"],
            "level": os.environ.get("DJANGO_LOG_LEVEL", "DEBUG"),
            "propagate": True,
        },
        "celery.utils.functional": {
            "handlers": ["console", "file"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

FLUTTERWAVE_PUBLIC_KEY = os.getenv("FLUTTERWAVE_PUBLIC_KEY")
FLUTTERWAVE_SECRET_KEY = os.getenv("FLUTTERWAVE_SECRET_KEY")
FLUTTERWAVE_ENCRYPTION_KEY = os.getenv("FLUTTERWAVE_ENCRYPTION_KEY")

SUBSCRIPTION_KEY = os.getenv("SUBSCRIPTION_KEY")
MOMO_API_USER = os.getenv("MOMO_API_USER")
MOMO_API_KEY = os.getenv("MOMO_API_KEY")
MOMO_CALLBACK_URL = os.getenv(
    "MOMO_CALLBACK_URL",
    default="https://sponsorwithpendeza.org/sponsorship/mtn-pay/callback/",
)
