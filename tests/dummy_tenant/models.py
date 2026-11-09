from __future__ import annotations

from django.conf import settings
from django.db import models


class Invoice(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    total = models.IntegerField(default=0)

    class Meta:
        app_label = "dummy_tenant"
