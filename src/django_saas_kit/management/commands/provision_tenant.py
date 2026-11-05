from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError, CommandParser

from django_saas_kit.conf import saas_settings
from django_saas_kit.schema import create_schema, tenant_migration_context
from django_saas_kit.utils import get_tenant_model
from django_saas_kit.validators import validate_schema_name


class Command(BaseCommand):
    help = "Provision a new tenant schema in PostgreSQL, register it in 'public', and run tenant migrations."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "schema_name",
            type=str,
            help="PostgreSQL schema identifier for the tenant (e.g. 'tenant_acme').",
        )
        parser.add_argument(
            "--name",
            type=str,
            default="",
            help="Commercial or display name for the tenant.",
        )
        parser.add_argument(
            "--domain",
            type=str,
            default="",
            help="Primary domain or subdomain for the tenant.",
        )
        parser.add_argument(
            "--no-migrate",
            action="store_true",
            default=False,
            help="Create the schema and tenant record without running migrations.",
        )
        parser.add_argument(
            "--inactive",
            action="store_true",
            default=False,
            help="Register the tenant with is_active=False.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        schema_name: str = options["schema_name"].strip()
        if schema_name == "public":
            raise CommandError("Cannot provision 'public' as a tenant schema.")

        try:
            validate_schema_name(schema_name)
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from exc

        display_name = options["name"].strip() or schema_name
        domain = options["domain"].strip()
        is_active = not options["inactive"]
        public_db = saas_settings.PUBLIC_DB_ALIAS
        default_db = saas_settings.DEFAULT_DB_ALIAS

        TenantModel = get_tenant_model()
        tenant, created = TenantModel.objects.using(public_db).update_or_create(
            schema_name=schema_name,
            defaults={
                "name": display_name,
                "domain": domain,
                "is_active": is_active,
            },
        )

        create_schema(schema_name)
        action = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(f"{action} tenant '{tenant.name}' (schema: {schema_name}).")
        )

        if not options["no_migrate"]:
            self.stdout.write(f"Running tenant migrations for schema '{schema_name}'...")
            with tenant_migration_context(schema_name, using=default_db):
                call_command(
                    "migrate",
                    database=default_db,
                    interactive=False,
                    verbosity=options.get("verbosity", 1),
                )
            self.stdout.write(
                self.style.SUCCESS(f"Migrations completed for schema '{schema_name}'.")
            )
