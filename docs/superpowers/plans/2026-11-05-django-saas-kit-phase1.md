# django-saas-kit (Phase 1: Core PIP Package) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `django-saas-kit` installable Python package providing process-bound PostgreSQL schema configuration, a swappable `Tenant` model in `public`, `PublicTenantRouter`, `TenantActiveMiddleware`, and `provision_tenant` / `migrate_all_schemas` management commands.

**Architecture:** Single-tenant Django process architecture on a shared PostgreSQL database where `default` is bound to `<tenant_schema>,public` at startup and `public` is bound to `public`. `PublicTenantRouter` directs `SAAS_PUBLIC_MODELS` (including the swappable `SAAS_TENANT_MODEL`) to `public` while isolating tenant models and migrations to each tenant schema.

**Tech Stack:** Python `>=3.10`, Django `>=4.2`, `pytest`, `pytest-django`, `hatchling` (`pyproject.toml` with `src/` layout).

**Spec:** `docs/superpowers/specs/2026-11-05-django-saas-kit-design.md`

## Global Constraints

- Package name: `django-saas-kit`, importable module: `django_saas_kit` under `src/django_saas_kit/`.
- Python `>=3.10`, Django `>=4.2`.
- Schema names must match `^[a-z][a-z0-9_]{0,62}$`, never start with `pg_`, and never equal `information_schema`.
- Never mutate `search_path` inside an HTTP request middleware; `search_path` is only set at startup via `OPTIONS['options']` or temporarily inside management command `tenant_migration_context`.
- Follow Git-Flow: commit on `feature/*` branches branched off `develop`.

## Review Focus

- **SQL injection via schema names in DDL (`CREATE SCHEMA` / `SET search_path`)**: `validate_schema_name` must reject uppercase, hyphens, semicolons, quotes, `pg_*`, and `information_schema` before any SQL execution.
- **Unintended table shadowing in tenant schemas during `migrate`**: `PublicTenantRouter.allow_migrate` must return `False` for `SAAS_PUBLIC_MODELS` when migrating a tenant schema on `default`, and `False` for tenant models when migrating `public`.
- **Unauthorized writes to `Tenant` registry from a tenant container**: `PublicTenantRouter.db_for_write` must raise `PermissionDenied` when `SAAS_TENANT_SCHEMA != 'public'` and a write is attempted on `SAAS_TENANT_MODEL` without `hints={'force_public_write': True}`.
- **Cross-connection ForeignKey failures (`allow_relation`)**: Assigning a `public` model instance (e.g., `auth.User` or `Tenant`) to a `default` tenant model `ForeignKey` must succeed without `ValueError`.
- **Operations without `model_name` in `allow_migrate` (`RunPython` / `RunSQL`)**: When `model_name is None` and no `hints['model']` is provided, `allow_migrate` must evaluate based on whether `f"{app_label}.*"` is in `SAAS_PUBLIC_MODELS`.

---

### Task 1: Package Scaffolding, Settings Configuration & Database Helper

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/django_saas_kit/__init__.py`
- Create: `src/django_saas_kit/apps.py`
- Create: `src/django_saas_kit/validators.py`
- Create: `src/django_saas_kit/conf.py`
- Create: `src/django_saas_kit/helpers.py`
- Test: `tests/conftest.py`
- Test: `tests/settings.py`
- Test: `tests/test_conf_and_helpers.py`

**Interfaces:**
- Consumes: Django `settings`
- Produces:
  - `django_saas_kit.validators.validate_schema_name(value: str) -> None`
  - `django_saas_kit.conf.saas_settings` (properties: `TENANT_SCHEMA: str`, `PUBLIC_MODELS: set[str]`, `TENANT_MODEL: str`, `PUBLIC_DB_ALIAS: str`, `DEFAULT_DB_ALIAS: str`, `PROTECT_TENANT_MODEL_WRITES: bool`, `STATUS_CACHE_TTL: int`)
  - `django_saas_kit.helpers.configure_saas_databases(base_config: dict[str, Any], tenant_schema: str | None = None) -> dict[str, dict[str, Any]]`

- [ ] **Step 1: Create `pyproject.toml`, test harness (`tests/settings.py`, `tests/conftest.py`), and write failing tests in `tests/test_conf_and_helpers.py`**

```python
# tests/test_conf_and_helpers.py
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
```

- [ ] **Step 2: Run `pytest` to verify the tests fail**

Run: `pytest tests/test_conf_and_helpers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'django_saas_kit'`

- [ ] **Step 3: Implement `validators.py`, `conf.py`, `helpers.py`, `apps.py`, and install package in editable mode**

Implement:
- `validate_schema_name(value: str) -> None` in `src/django_saas_kit/validators.py`
- `SaasSettings` and `saas_settings` in `src/django_saas_kit/conf.py`
- `configure_saas_databases(base_config: dict[str, Any], tenant_schema: str | None = None) -> dict[str, dict[str, Any]]` in `src/django_saas_kit/helpers.py`
- `DjangoSaasKitConfig` in `src/django_saas_kit/apps.py`

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_conf_and_helpers.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml README.md src/ tests/
git commit -m "feat: add package scaffolding, schema validators, conf, and db helper"
```

---

### Task 2: Swappable `Tenant` Model, `utils.py`, and Django Admin

**Files:**
- Create: `src/django_saas_kit/models.py`
- Create: `src/django_saas_kit/utils.py`
- Create: `src/django_saas_kit/admin.py`
- Create: `src/django_saas_kit/migrations/__init__.py`
- Create: `src/django_saas_kit/migrations/0001_initial.py`
- Test: `tests/test_models_and_utils.py`

**Interfaces:**
- Consumes: `validate_schema_name`, `saas_settings`
- Produces:
  - `django_saas_kit.models.AbstractTenant`
  - `django_saas_kit.models.Tenant` (`Meta.swappable = "SAAS_TENANT_MODEL"`)
  - `django_saas_kit.utils.get_tenant_model() -> type[AbstractTenant]`
  - `django_saas_kit.utils.get_current_tenant(using: str | None = None) -> AbstractTenant | None`
  - `django_saas_kit.utils.is_master_instance() -> bool`

- [ ] **Step 1: Write the failing tests in `tests/test_models_and_utils.py`**

```python
# tests/test_models_and_utils.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models_and_utils.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'django_saas_kit.models'`

- [ ] **Step 3: Implement `models.py`, `utils.py`, `admin.py`, and generate `0001_initial.py`**

Implement:
- `AbstractTenant` and `Tenant` in `src/django_saas_kit/models.py`
- `get_tenant_model()`, `is_master_instance()`, and `get_current_tenant(using: str | None = None)` in `src/django_saas_kit/utils.py`
- `TenantAdmin` in `src/django_saas_kit/admin.py`
- Initial migration in `src/django_saas_kit/migrations/0001_initial.py`

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_models_and_utils.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/django_saas_kit/models.py src/django_saas_kit/utils.py src/django_saas_kit/admin.py src/django_saas_kit/migrations/ tests/test_models_and_utils.py
git commit -m "feat: add swappable Tenant model, lookup utilities, and admin registration"
```

---

### Task 3: Custom Database Router (`PublicTenantRouter`)

**Files:**
- Create: `src/django_saas_kit/routers.py`
- Modify: `tests/settings.py`
- Create: `tests/dummy_public/models.py`
- Create: `tests/dummy_tenant/models.py`
- Test: `tests/test_router.py`

**Interfaces:**
- Consumes: `saas_settings`
- Produces:
  - `django_saas_kit.routers.PublicTenantRouter` (`db_for_read`, `db_for_write`, `allow_relation`, `allow_migrate`)
  - `django_saas_kit.routers.set_active_migration_schema(schema_name: str | None) -> None`
  - `django_saas_kit.routers.get_active_migration_schema() -> str`

- [ ] **Step 1: Create dummy test apps (`dummy_public` and `dummy_tenant`) and write failing router tests in `tests/test_router.py`**

```python
# tests/test_router.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'django_saas_kit.routers'`

- [ ] **Step 3: Implement `PublicTenantRouter` in `src/django_saas_kit/routers.py`**

Implement `PublicTenantRouter`, `set_active_migration_schema`, and `get_active_migration_schema` in `src/django_saas_kit/routers.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_router.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/django_saas_kit/routers.py tests/
git commit -m "feat: implement PublicTenantRouter for read/write, relation, and migration isolation"
```

---

### Task 4: Tenant Active Subscription Guard (`TenantActiveMiddleware`)

**Files:**
- Create: `src/django_saas_kit/middleware.py`
- Test: `tests/test_middleware.py`

**Interfaces:**
- Consumes: `saas_settings`, `get_current_tenant`, `is_master_instance`
- Produces:
  - `django_saas_kit.middleware.TenantActiveMiddleware`
  - `django_saas_kit.middleware.clear_tenant_status_cache(schema_name: str) -> None`

- [ ] **Step 1: Write the failing tests in `tests/test_middleware.py`**

```python
# tests/test_middleware.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_middleware.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'django_saas_kit.middleware'`

- [ ] **Step 3: Implement `TenantActiveMiddleware` and `clear_tenant_status_cache` in `src/django_saas_kit/middleware.py`**

Implement `TenantActiveMiddleware` and `clear_tenant_status_cache(schema_name: str)` (plus automatic cache invalidation via `post_save` signal on `Tenant` or inside `Tenant.save`).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_middleware.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/django_saas_kit/middleware.py tests/test_middleware.py
git commit -m "feat: add TenantActiveMiddleware with TTL cache to block suspended tenants"
```

---

### Task 5: Schema Management Utilities & Management Commands (`provision_tenant` & `migrate_all_schemas`)

**Files:**
- Create: `src/django_saas_kit/schema.py`
- Create: `src/django_saas_kit/management/__init__.py`
- Create: `src/django_saas_kit/management/commands/__init__.py`
- Create: `src/django_saas_kit/management/commands/provision_tenant.py`
- Create: `src/django_saas_kit/management/commands/migrate_all_schemas.py`
- Test: `tests/test_schema_and_commands.py`

**Interfaces:**
- Consumes: `validate_schema_name`, `saas_settings`, `get_tenant_model`, `set_active_migration_schema`
- Produces:
  - `django_saas_kit.schema.create_schema(schema_name: str, using: str | None = None) -> None`
  - `django_saas_kit.schema.schema_exists(schema_name: str, using: str | None = None) -> bool`
  - `django_saas_kit.schema.tenant_migration_context(schema_name: str, using: str | None = None)`
  - Management command `provision_tenant`
  - Management command `migrate_all_schemas`

- [ ] **Step 1: Write the failing tests in `tests/test_schema_and_commands.py`**

```python
# tests/test_schema_and_commands.py
from io import StringIO
from unittest.mock import patch
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from django_saas_kit.models import Tenant
from django_saas_kit.routers import get_active_migration_schema
from django_saas_kit.schema import create_schema, tenant_migration_context


@pytest.mark.django_db(databases=["default", "public"])
def test_create_schema_rejects_invalid_names():
    with pytest.raises(Exception):
        create_schema("bad-schema; DROP TABLE users;")


@pytest.mark.django_db(databases=["default", "public"])
def test_provision_tenant_creates_record_schema_and_runs_migrations():
    out = StringIO()
    with patch("django_saas_kit.management.commands.provision_tenant.create_schema") as mock_create, \
         patch("django_saas_kit.management.commands.provision_tenant.call_command") as mock_call:
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
    Tenant.objects.using("public").create(schema_name="tenant_one", name="One", is_active=True)
    Tenant.objects.using("public").create(schema_name="tenant_two", name="Two", is_active=True)
    Tenant.objects.using("public").create(schema_name="tenant_suspended", name="Suspended", is_active=False)

    migrated_contexts = []

    def fake_call_command(cmd, *args, **kwargs):
        if cmd == "migrate":
            migrated_contexts.append((kwargs.get("database"), get_active_migration_schema()))

    with patch("django_saas_kit.schema._execute_set_search_path"), \
         patch("django_saas_kit.management.commands.migrate_all_schemas.call_command", side_effect=fake_call_command):
        call_command("migrate_all_schemas")

    assert migrated_contexts == [
        ("public", "public"),
        ("default", "tenant_one"),
        ("default", "tenant_two"),
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_schema_and_commands.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'django_saas_kit.schema'`

- [ ] **Step 3: Implement `schema.py`, `provision_tenant.py`, and `migrate_all_schemas.py`**

Implement:
- `create_schema`, `schema_exists`, and `tenant_migration_context` in `src/django_saas_kit/schema.py`
- `Command` in `src/django_saas_kit/management/commands/provision_tenant.py`
- `Command` in `src/django_saas_kit/management/commands/migrate_all_schemas.py`

- [ ] **Step 4: Run test suite to verify all tests pass**

Run: `pytest -v`
Expected: PASS (all test files green)

- [ ] **Step 5: Commit**

```bash
git add src/django_saas_kit/schema.py src/django_saas_kit/management/ tests/test_schema_and_commands.py
git commit -m "feat: add schema DDL helpers and provision_tenant / migrate_all_schemas commands"
```
