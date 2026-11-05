from __future__ import annotations

from typing import TYPE_CHECKING

from django.apps import apps
from django.core.exceptions import ImproperlyConfigured

from django_saas_kit.conf import saas_settings

if TYPE_CHECKING:
    from django_saas_kit.models import AbstractTenant


def get_tenant_model() -> type[AbstractTenant]:
    """Return the active Tenant model class configured in SAAS_TENANT_MODEL."""
    try:
        return apps.get_model(saas_settings.TENANT_MODEL, require_ready=False)
    except ValueError as exc:
        raise ImproperlyConfigured(
            "SAAS_TENANT_MODEL must be of the form 'app_label.model_name'"
        ) from exc
    except LookupError as exc:
        raise ImproperlyConfigured(
            f"SAAS_TENANT_MODEL refers to model '{saas_settings.TENANT_MODEL}' "
            "that has not been installed"
        ) from exc


def is_master_instance() -> bool:
    """Return True when the current process is bound to the master 'public' schema."""
    return saas_settings.TENANT_SCHEMA == "public"


def get_current_tenant(using: str | None = None) -> AbstractTenant | None:
    """Fetch the Tenant record from 'public' matching the current process SAAS_TENANT_SCHEMA."""
    if is_master_instance():
        return None
    db_alias = using or saas_settings.PUBLIC_DB_ALIAS
    TenantModel = get_tenant_model()
    return (
        TenantModel.objects.using(db_alias)
        .filter(schema_name=saas_settings.TENANT_SCHEMA)
        .first()
    )
