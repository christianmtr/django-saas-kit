from __future__ import annotations

from typing import Any

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandParser

from django_saas_kit.conf import saas_settings
from django_saas_kit.routers import set_active_migration_schema
from django_saas_kit.schema import tenant_migration_context
from django_saas_kit.utils import get_tenant_model


class Command(BaseCommand):
    help = "Run migrations for the master 'public' schema followed by all registered tenant schemas."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--public-only",
            action="store_true",
            default=False,
            help="Only migrate the 'public' schema.",
        )
        parser.add_argument(
            "--tenants-only",
            action="store_true",
            default=False,
            help="Skip 'public' and only migrate tenant schemas.",
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            default=False,
            help="Also migrate tenants marked with is_active=False.",
        )
        parser.add_argument(
            "--schema",
            type=str,
            default="",
            help="Migrate only a specific tenant schema name.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        public_db = saas_settings.PUBLIC_DB_ALIAS
        default_db = saas_settings.DEFAULT_DB_ALIAS
        verbosity = options.get("verbosity", 1)

        if not options["tenants_only"]:
            self.stdout.write("Migrating 'public' schema...")
            set_active_migration_schema("public")
            try:
                call_command(
                    "migrate",
                    database=public_db,
                    interactive=False,
                    verbosity=verbosity,
                )
            finally:
                set_active_migration_schema(None)
            self.stdout.write(self.style.SUCCESS("Master 'public' schema migrated."))

        if options["public_only"]:
            return

        TenantModel = get_tenant_model()
        qs = TenantModel.objects.using(public_db).all().order_by("schema_name")

        target_schema = options["schema"].strip()
        if target_schema:
            qs = qs.filter(schema_name=target_schema)
        elif not options["include_inactive"]:
            qs = qs.filter(is_active=True)

        tenants = list(qs)
        self.stdout.write(f"Found {len(tenants)} tenant schema(s) to migrate.")

        for tenant in tenants:
            self.stdout.write(f"Migrating tenant schema '{tenant.schema_name}'...")
            with tenant_migration_context(tenant.schema_name, using=default_db):
                call_command(
                    "migrate",
                    database=default_db,
                    interactive=False,
                    verbosity=verbosity,
                )
            self.stdout.write(
                self.style.SUCCESS(f"Schema '{tenant.schema_name}' migrated.")
            )
