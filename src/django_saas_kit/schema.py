from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from django.db import connections
from django.db.migrations.recorder import MigrationRecorder

from django_saas_kit.conf import saas_settings
from django_saas_kit.routers import (
    get_active_migration_schema,
    get_migration_schema_override,
    set_active_migration_schema,
)
from django_saas_kit.validators import validate_schema_name


def create_schema(schema_name: str, using: str | None = None) -> None:
    """Safely validate and execute CREATE SCHEMA IF NOT EXISTS on PostgreSQL."""
    validate_schema_name(schema_name)
    db_alias = using or saas_settings.PUBLIC_DB_ALIAS
    conn = connections[db_alias]
    quoted_schema = conn.ops.quote_name(schema_name)
    with conn.cursor() as cursor:
        cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {quoted_schema}")


def schema_exists(schema_name: str, using: str | None = None) -> bool:
    """Check whether a PostgreSQL schema exists in information_schema.schemata."""
    validate_schema_name(schema_name)
    db_alias = using or saas_settings.PUBLIC_DB_ALIAS
    conn = connections[db_alias]
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
            [schema_name],
        )
        return cursor.fetchone() is not None


def list_schemas(using: str | None = None) -> list[str]:
    """Return non-system, non-public PostgreSQL schemas from information_schema.schemata."""
    db_alias = using or saas_settings.PUBLIC_DB_ALIAS
    conn = connections[db_alias]
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name NOT IN ('public', 'information_schema')
              AND schema_name NOT LIKE 'pg_%%'
            ORDER BY schema_name
            """
        )
        return [row[0] for row in cursor.fetchall()]


def _execute_set_search_path(
    conn_alias: str,
    schema_name: str,
    ensure_migration_table: bool = False,
) -> None:
    validate_schema_name(schema_name)
    conn = connections[conn_alias]
    if conn.vendor != "postgresql":
        return
    quoted_schema = conn.ops.quote_name(schema_name)
    with conn.cursor() as cursor:
        if schema_name == "public":
            cursor.execute("SET search_path TO public")
        else:
            if ensure_migration_table:
                cursor.execute(f"SET search_path TO {quoted_schema}")
                MigrationRecorder(conn).ensure_schema()
            cursor.execute(f"SET search_path TO {quoted_schema}, public")


@contextmanager
def tenant_migration_context(
    schema_name: str,
    using: str | None = None,
) -> Iterator[None]:
    """
    Temporarily bind the migration router context and PostgreSQL search_path
    to `schema_name` for centralized administrative commands (`provision_tenant`, `migrate_all_schemas`).
    """
    validate_schema_name(schema_name)
    conn_alias = using or saas_settings.DEFAULT_DB_ALIAS
    previous_override = get_migration_schema_override()
    previous_effective_schema = get_active_migration_schema()

    set_active_migration_schema(schema_name)
    _execute_set_search_path(
        conn_alias,
        schema_name,
        ensure_migration_table=(schema_name != "public"),
    )
    try:
        yield
    finally:
        set_active_migration_schema(previous_override)
        _execute_set_search_path(
            conn_alias,
            previous_effective_schema,
            ensure_migration_table=False,
        )
