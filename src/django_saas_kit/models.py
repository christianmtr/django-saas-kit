from __future__ import annotations

from typing import Any

from django.db import models

from django_saas_kit.validators import validate_schema_name


class AbstractTenant(models.Model):
    """Base abstract model for registered SaaS tenants living in the 'public' schema."""

    schema_name = models.CharField(
        max_length=63,
        unique=True,
        db_index=True,
        validators=[validate_schema_name],
        help_text="PostgreSQL schema identifier for this tenant.",
    )
    name = models.CharField(
        max_length=150,
        help_text="Human-readable commercial or organization name.",
    )
    domain = models.CharField(
        max_length=253,
        blank=True,
        default="",
        help_text="Optional primary domain or subdomain for this tenant.",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Controls whether this tenant instance is allowed to serve traffic.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["schema_name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.schema_name})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        super().save(*args, **kwargs)
        from django_saas_kit.middleware import clear_tenant_status_cache

        clear_tenant_status_cache(self.schema_name)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        schema_name = self.schema_name
        result = super().delete(*args, **kwargs)
        from django_saas_kit.middleware import clear_tenant_status_cache

        clear_tenant_status_cache(schema_name)
        return result


class Tenant(AbstractTenant):
    """Default concrete Tenant model. Swappable via SAAS_TENANT_MODEL."""

    class Meta(AbstractTenant.Meta):
        swappable = "SAAS_TENANT_MODEL"
        verbose_name = "Tenant"
        verbose_name_plural = "Tenants"
