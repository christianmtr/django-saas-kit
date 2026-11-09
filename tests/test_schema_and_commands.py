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
from django_saas_kit.schema import (
    _execute_set_search_path,
    create_schema,
    list_schemas,
    tenant_migration_context,
)


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
def test_provision_tenant_rerun_preserves_existing_metadata_when_flags_omitted():
    Tenant.objects.using("public").create(
        schema_name="tenant_acme",
        name="Acme Original",
        domain="acme.original.com",
        is_active=False,
    )
    with patch(
        "django_saas_kit.management.commands.provision_tenant.create_schema"
    ), patch("django_saas_kit.schema._execute_set_search_path"), patch(
        "django_saas_kit.management.commands.provision_tenant.call_command"
    ):
        call_command("provision_tenant", "tenant_acme", no_migrate=True)

    tenant = Tenant.objects.using("public").get(schema_name="tenant_acme")
    assert tenant.name == "Acme Original"
    assert tenant.domain == "acme.original.com"
    assert tenant.is_active is False


@pytest.mark.django_db(databases=["default", "public"])
def test_execute_set_search_path_ensures_isolated_migration_table_on_postgres():
    executed_sql = []

    class DummyCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, sql, params=None):
            executed_sql.append(sql)

    with patch("django_saas_kit.schema.connections") as mock_conns, patch(
        "django_saas_kit.schema.MigrationRecorder"
    ) as mock_recorder:
        conn = mock_conns.__getitem__.return_value
        conn.vendor = "postgresql"
        conn.ops.quote_name.side_effect = lambda s: f'"{s}"'
        conn.cursor.return_value = DummyCursor()

        _execute_set_search_path("default", "tenant_acme", ensure_migration_table=True)

        assert executed_sql == [
            'SET search_path TO "tenant_acme"',
            'SET search_path TO "tenant_acme", public',
        ]
        mock_recorder.assert_called_once_with(conn)
        mock_recorder.return_value.ensure_schema.assert_called_once()


def test_list_schemas_returns_non_system_schemas():
    with patch("django_saas_kit.schema.connections") as mock_conns:
        cursor = mock_conns.__getitem__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [("tenant_a",), ("tenant_b",)]
        assert list_schemas() == ["tenant_a", "tenant_b"]


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
