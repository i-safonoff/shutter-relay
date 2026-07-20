"""Settings, read from the environment with defaults that work against
docker-compose.yml's service names. No settings/dev.py vs settings/prod.py
split -- one file, one source of truth for what changes between a laptop
and a real deploy, which is the environment itself."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-not-a-real-secret")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "apps.gallery",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "relay.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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

WSGI_APPLICATION = "relay.wsgi.application"
ASGI_APPLICATION = "relay.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "relay"),
        "USER": os.environ.get("POSTGRES_USER", "relay"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "relay"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5544"),
    }
}

# Redis backs two independent things here, deliberately not shared: the
# Channels layer (ephemeral pub/sub, groups) and, if it's ever needed,
# Django's cache. Splitting them by DB index means flushing one for a test
# doesn't touch the other.
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6389/0")

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# S3-compatible storage (MinIO locally, any real S3 in prod -- the client
# code never knows the difference, which is the point of the API).
AWS_ACCESS_KEY_ID = os.environ.get("S3_ACCESS_KEY", "relay-minio")
AWS_SECRET_ACCESS_KEY = os.environ.get("S3_SECRET_KEY", "relay-minio-secret")
AWS_STORAGE_BUCKET_NAME = os.environ.get("S3_BUCKET", "shutter-relay")
AWS_S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "http://localhost:9100")
# The endpoint the browser uses to reach the same bucket. Inside Docker
# Compose, Django talks to MinIO over the service network (`minio:9000`);
# a presigned URL built with that hostname is useless to a browser on the
# host, which has never heard of a host named `minio`. Two settings, not
# one, because the signer and the URL's audience are not the same machine.
AWS_S3_PUBLIC_ENDPOINT_URL = os.environ.get("S3_PUBLIC_ENDPOINT_URL", "http://localhost:9100")

# imgproxy: HMAC key + salt, hex-encoded, must match imgproxy's own
# IMGPROXY_KEY / IMGPROXY_SALT exactly or every signed URL 403s.
IMGPROXY_BASE_URL = os.environ.get("IMGPROXY_BASE_URL", "http://localhost:9101")
IMGPROXY_KEY = os.environ.get("IMGPROXY_KEY", "")
IMGPROXY_SALT = os.environ.get("IMGPROXY_SALT", "")
