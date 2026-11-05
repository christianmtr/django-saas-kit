from __future__ import annotations

import os
from typing import Iterable

from django.conf import settings


class SaasSettings:
    """Centralized, dynamic access to django-saas-kit configuration."""

    @property
    def TENANT_SCHEMA(self) -> str:
        return getattr(
            settings,
            "SAAS_TENANT_SCHEMA",
            os.environ.get("TENANT_SCHEMA", "public"),
        )

    @property
    def TENANT_MODEL(self) -> str:
        return getattr(settings, "SAAS_TENANT_MODEL", "django_saas_kit.Tenant")

    @property
    def PUBLIC_DB_ALIAS(self) -> str:
        return getattr(settings, "SAAS_PUBLIC_DB_ALIAS", "public")

    @property
    def DEFAULT_DB_ALIAS(self) -> str:
        return getattr(settings, "SAAS_DEFAULT_DB_ALIAS", "default")

    @property
    def PROTECT_TENANT_MODEL_WRITES(self) -> bool:
        return bool(getattr(settings, "SAAS_PROTECT_TENANT_MODEL_WRITES", True))

    @property
    def STATUS_CACHE_TTL(self) -> int:
        return int(getattr(settings, "SAAS_STATUS_CACHE_TTL", 60))

    @property
    def PUBLIC_MODELS(self) -> set[str]:
        configured: Iterable[str] = getattr(settings, "SAAS_PUBLIC_MODELS", [])
        normalized = {item.strip().lower() for item in configured if item and item.strip()}
        normalized.add("django_saas_kit.*")
        normalized.add(self.TENANT_MODEL.strip().lower())
        return normalized


saas_settings = SaasSettings()
