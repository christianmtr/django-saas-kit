from __future__ import annotations

from django.contrib import admin

from django_saas_kit.conf import saas_settings
from django_saas_kit.models import Tenant


class TenantAdmin(admin.ModelAdmin):
    list_display = ("schema_name", "name", "domain", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("schema_name", "name", "domain")
    readonly_fields = ("created_at", "updated_at")


if saas_settings.TENANT_MODEL.lower() == "django_saas_kit.tenant":
    admin.site.register(Tenant, TenantAdmin)
