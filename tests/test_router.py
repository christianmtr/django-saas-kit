from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.test import override_settings

from django_saas_kit.models import Tenant
from django_saas_kit.routers import PublicTenantRouter, set_active_migration_schema
from tests.dummy_public.models import SubscriptionPlan
from tests.dummy_tenant.models import Invoice


@override_settings(
    SAAS_PUBLIC_MODELS=["auth.*", "dummy_public.SubscriptionPlan"],
    SAAS_TENANT_SCHEMA="tenant_acme",
)
def test_router_reads_and_writes_route_to_correct_database():
    router = PublicTenantRouter()
    assert router.db_for_read(User) == "public"
    assert router.db_for_write(User) == "public"
    assert router.db_for_read(SubscriptionPlan) == "public"
    assert router.db_for_write(SubscriptionPlan) == "public"
    assert router.db_for_read(Tenant) == "public"
    assert router.db_for_read(Invoice) == "default"
    assert router.db_for_write(Invoice) == "default"


@override_settings(SAAS_TENANT_SCHEMA="tenant_acme", SAAS_PROTECT_TENANT_MODEL_WRITES=True)
def test_router_blocks_tenant_instance_from_writing_to_tenant_model():
    router = PublicTenantRouter()
    with pytest.raises(PermissionDenied):
        router.db_for_write(Tenant)
    # Allowed when force_public_write hint is provided or on master instance
    assert router.db_for_write(Tenant, force_public_write=True) == "public"


@override_settings(SAAS_TENANT_SCHEMA="public")
def test_router_allows_master_instance_to_write_to_tenant_model():
    router = PublicTenantRouter()
    assert router.db_for_write(Tenant) == "public"


def test_router_allows_cross_schema_relations_between_default_and_public():
    router = PublicTenantRouter()
    user = User(username="alice")
    user._state.db = "public"
    invoice = Invoice(total=100)
    invoice._state.db = "default"
    assert router.allow_relation(user, invoice) is True


@override_settings(
    SAAS_PUBLIC_MODELS=["auth.*", "dummy_public.SubscriptionPlan"],
    SAAS_TENANT_SCHEMA="tenant_acme",
)
def test_router_allow_migrate_isolates_public_and_tenant_tables():
    router = PublicTenantRouter()
    # On 'public' connection: only public models migrate
    assert router.allow_migrate("public", "auth", model_name="user") is True
    assert router.allow_migrate("public", "dummy_public", model_name="subscriptionplan") is True
    assert router.allow_migrate("public", "django_saas_kit", model_name="tenant") is True
    assert router.allow_migrate("public", "dummy_tenant", model_name="invoice") is False

    # On 'default' connection when schema is 'tenant_acme': only tenant models migrate
    assert router.allow_migrate("default", "auth", model_name="user") is False
    assert router.allow_migrate("default", "dummy_public", model_name="subscriptionplan") is False
    assert router.allow_migrate("default", "django_saas_kit", model_name="tenant") is False
    assert router.allow_migrate("default", "dummy_tenant", model_name="invoice") is True


@override_settings(
    SAAS_PUBLIC_MODELS=["auth.*"],
    SAAS_TENANT_SCHEMA="public",
)
def test_router_allow_migrate_handles_runpython_without_model_name():
    router = PublicTenantRouter()
    assert router.allow_migrate("public", "auth", model_name=None) is True
    assert router.allow_migrate("public", "dummy_tenant", model_name=None) is False
    set_active_migration_schema("tenant_acme")
    try:
        assert router.allow_migrate("default", "auth", model_name=None) is False
        assert router.allow_migrate("default", "dummy_tenant", model_name=None) is True
    finally:
        set_active_migration_schema(None)
