from __future__ import annotations

from django.apps import AppConfig


class DjangoSaasKitConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "django_saas_kit"
    verbose_name = "Django SaaS Kit"
