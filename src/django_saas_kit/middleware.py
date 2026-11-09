from __future__ import annotations

from typing import Callable

from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse

from django_saas_kit.conf import saas_settings
from django_saas_kit.utils import get_current_tenant, is_master_instance

CACHE_KEY_PREFIX = "saas_kit:tenant_active:"


def _cache_key(schema_name: str) -> str:
    return f"{CACHE_KEY_PREFIX}{schema_name}"


def clear_tenant_status_cache(schema_name: str) -> None:
    """Invalidate the cached active status for a given tenant schema."""
    cache.delete(_cache_key(schema_name))


class TenantActiveMiddleware:
    """
    Lightweight subscription guard for process-bound tenant instances.
    Checks whether the current tenant is active in the master 'public' database,
    caching the result locally for SAAS_STATUS_CACHE_TTL seconds.
    Never modifies database search_path.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if is_master_instance():
            return self.get_response(request)

        schema_name = saas_settings.TENANT_SCHEMA
        key = _cache_key(schema_name)
        is_active = cache.get(key)

        if is_active is None:
            tenant = get_current_tenant()
            is_active = bool(tenant is not None and tenant.is_active)
            cache.set(key, is_active, timeout=saas_settings.STATUS_CACHE_TTL)

        if not is_active:
            return self.handle_inactive_tenant(request, schema_name)

        return self.get_response(request)

    def handle_inactive_tenant(
        self, request: HttpRequest, schema_name: str
    ) -> HttpResponse:
        accept = request.META.get("HTTP_ACCEPT", "")
        if "application/json" in accept:
            return JsonResponse(
                {
                    "detail": f"Tenant '{schema_name}' is currently suspended or inactive.",
                    "code": "tenant_suspended",
                },
                status=403,
            )
        return HttpResponseForbidden(
            f"Tenant '{schema_name}' is currently suspended or inactive."
        )
