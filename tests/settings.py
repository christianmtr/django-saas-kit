from __future__ import annotations

SECRET_KEY = "test-secret-key-for-django-saas-kit"
DEBUG = True
USE_TZ = True

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.admin",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django_saas_kit",
    "tests.dummy_public",
    "tests.dummy_tenant",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
    "public": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

SAAS_TENANT_SCHEMA = "public"
SAAS_PUBLIC_MODELS = [
    "auth.*",
    "contenttypes.*",
    "sessions.*",
    "admin.*",
]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
