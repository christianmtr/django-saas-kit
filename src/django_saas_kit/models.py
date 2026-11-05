from __future__ import annotations

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


class Tenant(AbstractTenant):
    """Default concrete Tenant model. Swappable via SAAS_TENANT_MODEL."""

    class Meta(AbstractTenant.Meta):
        swappable = "SAAS_TENANT_MODEL"
        verbose_name = "Tenant"
        verbose_name_plural = "Tenants"
