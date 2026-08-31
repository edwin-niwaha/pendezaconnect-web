from sys import stdout

import colorama
from colorama import Fore, Style

from .base import *  # noqa: F403

colorama.init(autoreset=True)
stdout.write(f"{Fore.GREEN}{Style.BRIGHT}================ Loading Development Settings =====================\n")

DEBUG = True
SITE_URL = "http://localhost:8000"

# Local development should not require a Redis service merely to render pages.
# Set USE_REDIS_CACHE_IN_DEV=true only when intentionally testing Redis locally.
if not env_bool("USE_REDIS_CACHE_IN_DEV", False):  # noqa: F405
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "pendeza-connect-development-cache",
            "TIMEOUT": 300,
        }
    }
SOCIAL_AUTH_GOOGLE_OAUTH2_REDIRECT_URI = "http://localhost:8000/oauth/complete/google-oauth2/"

ALLOWED_HOSTS = ["localhost", "127.0.0.1", *ALLOWED_HOSTS]  # noqa: F405
CSRF_TRUSTED_ORIGINS = [  # noqa: F405
    "http://localhost",
    "http://127.0.0.1",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    *CSRF_TRUSTED_ORIGINS,
]
CORS_ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:8081",
    "http://127.0.0.1:8081",
    *env_list("CORS_ALLOWED_ORIGINS"),  # noqa: F405
]

if env_bool("USE_DATABASE_URL_IN_DEV", False):  # noqa: F405
    DATABASES = database_config(ssl_require=env_bool("DATABASE_SSL_REQUIRE", False))  # noqa: F405
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "sms_db"),
            "USER": os.environ.get("DB_USER", "postgres"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        }
    }

INSTALLED_APPS += [  # noqa: F405
    "django_browser_reload",
]

MIDDLEWARE += [  # noqa: F405
    "django_browser_reload.middleware.BrowserReloadMiddleware",
]

ENABLE_DEBUG_TOOLBAR = env_bool("ENABLE_DEBUG_TOOLBAR", False)  # noqa: F405
if ENABLE_DEBUG_TOOLBAR:
    INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
    MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]  # noqa: F405

INTERNAL_IPS = ["127.0.0.1"]

DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
MEDIA_URL = LOCAL_MEDIA_URL  # noqa: F405

SECURE_SSL_REDIRECT = False
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
