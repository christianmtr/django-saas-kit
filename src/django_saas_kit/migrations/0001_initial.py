from __future__ import annotations

from django.db import migrations, models

import django_saas_kit.validators


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Tenant",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "schema_name",
                    models.CharField(
                        db_index=True,
                        help_text="PostgreSQL schema identifier for this tenant.",
                        max_length=63,
                        unique=True,
                        validators=[django_saas_kit.validators.validate_schema_name],
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="Human-readable commercial or organization name.",
                        max_length=150,
                    ),
                ),
                (
                    "domain",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Optional primary domain or subdomain for this tenant.",
                        max_length=253,
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        db_index=True,
                        default=True,
                        help_text="Controls whether this tenant instance is allowed to serve traffic.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Tenant",
                "verbose_name_plural": "Tenants",
                "ordering": ["schema_name"],
                "abstract": False,
                "swappable": "SAAS_TENANT_MODEL",
            },
        ),
    ]
