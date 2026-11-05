from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings

from django_saas_kit.conf import saas_settings
from django_saas_kit.helpers import configure_saas_databases
from django_saas_kit.validators import validate_schema_name


@pytest.mark.parametrize("valid_name", ["public", "tenant_acme", "client_123", "a"])
def test_validate_schema_name_accepts_valid_identifiers(valid_name):
    validate_schema_name(valid_name)


@pytest.mark.parametrize(
    "invalid_name",
    [
        "",
        "Tenant_Upper",
        "123_starts_with_number",
        "tenant-hyphen",
        "pg_catalog",
        "pg_temp",
        "information_schema",
        "acme; DROP SCHEMA public;--",
        "a" * 64,
    ],
)
def test_validate_schema_name_rejects_invalid_identifiers(invalid_name):
    with pytest.raises(ValidationError):
        validate_schema_name(invalid_name)


def test_configure_saas_databases_injects_search_path():
    base = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "saas_db",
        "USER": "postgres",
    }
    dbs = configure_saas_databases(base, tenant_schema="tenant_acme")
    assert dbs["default"]["OPTIONS"]["options"] == "-c search_path=tenant_acme,public"
    assert dbs["public"]["OPTIONS"]["options"] == "-c search_path=public"
    # Ensure original dict wasn't mutated in place
    assert "OPTIONS" not in base


def test_configure_saas_databases_rejects_invalid_schema():
    base = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "saas_db",
    }
    with pytest.raises(ValidationError):
        configure_saas_databases(base, tenant_schema="bad-schema!")


@override_settings(
    SAAS_PUBLIC_MODELS=["auth.*", "billing.Plan"],
    SAAS_TENANT_MODEL="custom_app.CustomTenant",
)
def test_saas_settings_normalizes_and_includes_tenant_model():
    public_models = saas_settings.PUBLIC_MODELS
    assert "auth.*" in public_models
    assert "billing.plan" in public_models
    assert "custom_app.customtenant" in public_models
    assert "django_saas_kit.*" in public_models
