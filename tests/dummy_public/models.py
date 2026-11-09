from __future__ import annotations

from django.db import models


class SubscriptionPlan(models.Model):
    code = models.CharField(max_length=50)
    price_cents = models.PositiveIntegerField(default=0)

    class Meta:
        app_label = "dummy_public"
