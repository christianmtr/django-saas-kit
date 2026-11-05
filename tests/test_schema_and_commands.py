from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError

from django_saas_kit.models import Tenant
from django_saas_kit.routers import (
    get_active_migration_schema,
    get_migration_schema_override,
)
from django_saas_kit.schema import create_schema, tenant_migration_context


@pytest.mark.django_db(databases=["default", "public"])
def test_create_schema_rejects_invalid_names():
    with pytest.raises(ValidationError):
        create_schema("bad-schema; DROP TABLE users;")


@pytest.mark.django_db(databases=["default", "public"])
def test_tenant_migration_context_restores_previous_state():
    with patch("django_saas_kit.schema._execute_set_search_path") as mock_set_path:
        assert get_migration_schema_override() is None
        assert get_active_migration_schema() == "public"
        with tenant_migration_context("tenant_acme"):
            assert get_migration_schema_override() == "tenant_acme"
            assert get_active_migration_schema() == "tenant_acme"
        assert get_migration_schema_override() is None
        assert get_active_migration_schema() == "public"
        assert mock_set_path.call_count == 2


@pytest.mark.django_db(databases=["default", "public"])
def test_provision_tenant_creates_record_schema_and_runs_migrations():
    out = StringIO()
    with patch(
        "django_saas_kit.management.commands.provision_tenant.create_schema"
    ) as mock_create, patch(
        "django_saas_kit.schema._execute_set_search_path"
    ), patch(
        "django_saas_kit.management.commands.provision_tenant.call_command"
    ) as mock_call:
        call_command(
            "provision_tenant",
            "tenant_globex",
            name="Globex Corp",
            domain="globex.example.com",
            stdout=out,
        )
        mock_create.assert_called_once_with("tenant_globex")
        mock_call.assert_called_once()

    tenant = Tenant.objects.using("public").get(schema_name="tenant_globex")
    assert tenant.name == "Globex Corp"
    assert tenant.domain == "globex.example.com"
    assert tenant.is_active is True


@pytest.mark.django_db(databases=["default", "public"])
def test_provision_tenant_forbids_public_schema():
    with pytest.raises(CommandError, match="public"):
        call_command("provision_tenant", "public", name="Public")


@pytest.mark.django_db(databases=["default", "public"])
def test_migrate_all_schemas_migrates_public_then_active_tenants():
    Tenant.objects.using("public").create(
        schema_name="tenant_one", name="One", is_active=True
    )
    Tenant.objects.using("public").create(
        schema_name="tenant_two", name="Two", is_active=True
    )
    Tenant.objects.using("public").create(
        schema_name="tenant_suspended", name="Suspended", is_active=False
    )

    migrated_contexts = []

    def fake_call_command(cmd, *args, **kwargs):
        if cmd == "migrate":
            migrated_contexts.append(
                (kwargs.get("database"), get_active_migration_schema())
            )

    with patch("django_saas_kit.schema._execute_set_search_path"), patch(
        "django_saas_kit.management.commands.migrate_all_schemas.call_command",
        side_effect=fake_call_command,
    ):
        call_command("migrate_all_schemas")

    assert migrated_contexts == [
        ("public", "public"),
        ("default", "tenant_one"),
        ("default", "tenant_two"),
    ]
