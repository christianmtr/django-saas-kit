from __future__ import annotations

import re

from django.core.exceptions import ValidationError

SCHEMA_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
RESERVED_SCHEMAS = frozenset({"information_schema"})
RESERVED_PREFIXES = ("pg_",)


def validate_schema_name(value: str) -> None:
    """Validate that a string is a safe, valid PostgreSQL schema identifier."""
    if not isinstance(value, str) or not SCHEMA_NAME_RE.match(value):
        raise ValidationError(
            f"Invalid PostgreSQL schema name '{value}'. Must match ^[a-z][a-z0-9_]{{0,62}}$."
        )
    if value in RESERVED_SCHEMAS or value.startswith(RESERVED_PREFIXES):
        raise ValidationError(
            f"Schema name '{value}' uses a reserved PostgreSQL system identifier."
        )
