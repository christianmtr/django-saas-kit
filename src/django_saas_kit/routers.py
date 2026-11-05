from __future__ import annotations

import threading
from typing import Any

from django.core.exceptions import PermissionDenied
from django.db.models import Model

from django_saas_kit.conf import saas_settings

_migration_state = threading.local()


def set_active_migration_schema(schema_name: str | None) -> None:
    """Set thread-local migration target schema override used by management commands."""
    _migration_state.schema_name = schema_name


def get_migration_schema_override() -> str | None:
    """Return raw thread-local migration schema override (or None if unset)."""
    return getattr(_migration_state, "schema_name", None)


def get_active_migration_schema() -> str:
    """Return active migration schema override or fall back to SAAS_TENANT_SCHEMA."""
    override = get_migration_schema_override()
    return override if override is not None else saas_settings.TENANT_SCHEMA


def _is_public_label(app_label: str, model_name: str | None = None) -> bool:
    app_lower = app_label.lower()
    public_models = saas_settings.PUBLIC_MODELS

    if f"{app_lower}.*" in public_models:
        return True
    if model_name:
        return f"{app_lower}.{model_name.lower()}" in public_models
    return False


def _is_tenant_registry_model(model: type[Model]) -> bool:
    label = f"{model._meta.app_label}.{model._meta.model_name}".lower()
    return label == saas_settings.TENANT_MODEL.strip().lower()


class PublicTenantRouter:
    """Routes SAAS_PUBLIC_MODELS to 'public' connection and business models to 'default'."""

    def db_for_read(self, model: type[Model], **hints: Any) -> str:
        if _is_public_label(model._meta.app_label, model._meta.model_name):
            return saas_settings.PUBLIC_DB_ALIAS
        return saas_settings.DEFAULT_DB_ALIAS

    def db_for_write(self, model: type[Model], **hints: Any) -> str:
        if (
            _is_tenant_registry_model(model)
            and saas_settings.TENANT_SCHEMA != "public"
            and saas_settings.PROTECT_TENANT_MODEL_WRITES
            and not hints.get("force_public_write", False)
        ):
            raise PermissionDenied(
                "Tenant instances cannot modify the master Tenant registry."
            )

        if _is_public_label(model._meta.app_label, model._meta.model_name):
            return saas_settings.PUBLIC_DB_ALIAS
        return saas_settings.DEFAULT_DB_ALIAS

    def allow_relation(self, obj1: Model, obj2: Model, **hints: Any) -> bool | None:
        allowed_dbs = {saas_settings.DEFAULT_DB_ALIAS, saas_settings.PUBLIC_DB_ALIAS}
        db1 = obj1._state.db or self.db_for_read(type(obj1))
        db2 = obj2._state.db or self.db_for_read(type(obj2))
        if db1 in allowed_dbs and db2 in allowed_dbs:
            return True
        return None

    def allow_migrate(
        self,
        db: str,
        app_label: str,
        model_name: str | None = None,
        **hints: Any,
    ) -> bool | None:
        if model_name is None and "model" in hints and hints["model"] is not None:
            model_name = hints["model"]._meta.model_name

        is_public = _is_public_label(app_label, model_name)

        if db == saas_settings.PUBLIC_DB_ALIAS:
            return is_public

        if db == saas_settings.DEFAULT_DB_ALIAS:
            active_schema = get_active_migration_schema()
            if active_schema == "public":
                return is_public
            return not is_public

        return None
