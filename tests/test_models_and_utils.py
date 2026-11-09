from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings

from django_saas_kit.models import AbstractTenant, Tenant
from django_saas_kit.utils import get_current_tenant, get_tenant_model, is_master_instance


def test_get_tenant_model_returns_default_tenant():
    assert get_tenant_model() is Tenant
    assert issubclass(Tenant, AbstractTenant)


@pytest.mark.django_db(databases=["default", "public"])
def test_tenant_model_validates_schema_name():
    bad_tenant = Tenant(schema_name="Invalid-Schema!", name="Bad Corp")
    with pytest.raises(ValidationError):
        bad_tenant.full_clean()


@pytest.mark.django_db(databases=["default", "public"])
def test_get_current_tenant_fetches_from_public_db():
    Tenant.objects.using("public").create(
        schema_name="tenant_acme",
        name="Acme Corp",
        domain="acme.example.com",
        is_active=True,
    )
    with override_settings(SAAS_TENANT_SCHEMA="tenant_acme"):
        assert not is_master_instance()
        current = get_current_tenant()
        assert current is not None
        assert current.name == "Acme Corp"
        assert current.is_active is True

    with override_settings(SAAS_TENANT_SCHEMA="public"):
        assert is_master_instance()
        assert get_current_tenant() is None
