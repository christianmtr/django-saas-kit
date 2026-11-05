from __future__ import annotations

import pytest
from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from django_saas_kit.middleware import TenantActiveMiddleware, clear_tenant_status_cache
from django_saas_kit.models import Tenant


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()


@pytest.mark.django_db(databases=["default", "public"])
def test_middleware_allows_active_tenant_and_caches_status(django_assert_num_queries):
    Tenant.objects.using("public").create(
        schema_name="tenant_acme", name="Acme", is_active=True
    )
    rf = RequestFactory()
    middleware = TenantActiveMiddleware(lambda req: HttpResponse("OK"))

    with override_settings(SAAS_TENANT_SCHEMA="tenant_acme"):
        # First request hits DB and caches
        res1 = middleware(rf.get("/dashboard/"))
        assert res1.status_code == 200

        # Second request uses cache (0 DB queries)
        with django_assert_num_queries(0, using="public"):
            res2 = middleware(rf.get("/dashboard/"))
            assert res2.status_code == 200


@pytest.mark.django_db(databases=["default", "public"])
def test_middleware_blocks_suspended_tenant_with_403():
    tenant = Tenant.objects.using("public").create(
        schema_name="tenant_unpaid", name="Unpaid Co", is_active=False
    )
    rf = RequestFactory()
    middleware = TenantActiveMiddleware(lambda req: HttpResponse("OK"))

    with override_settings(SAAS_TENANT_SCHEMA="tenant_unpaid"):
        res_html = middleware(rf.get("/dashboard/"))
        assert res_html.status_code == 403

        res_json = middleware(rf.get("/api/items/", HTTP_ACCEPT="application/json"))
        assert res_json.status_code == 403
        assert b"suspended" in res_json.content.lower()

        # Reactivate and clear cache
        tenant.is_active = True
        tenant.save(using="public", update_fields=["is_active"])
        clear_tenant_status_cache("tenant_unpaid")

        res_after = middleware(rf.get("/dashboard/"))
        assert res_after.status_code == 200


@pytest.mark.django_db(databases=["default", "public"])
def test_middleware_always_allows_master_public_instance(django_assert_num_queries):
    rf = RequestFactory()
    middleware = TenantActiveMiddleware(lambda req: HttpResponse("Master OK"))
    with override_settings(SAAS_TENANT_SCHEMA="public"):
        with django_assert_num_queries(0, using="public"):
            res = middleware(rf.get("/admin/"))
            assert res.status_code == 200
