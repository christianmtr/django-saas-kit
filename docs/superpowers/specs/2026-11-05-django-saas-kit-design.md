# django-saas-kit (Phase 1: Core PIP Package) Design Spec

## 1. Intent & Why
Traditional Django multi-tenant libraries (`django-tenants`, `django-tenant-schemas`) rely on an HTTP middleware that mutates `SET search_path` on every request. This introduces concurrency hazards in ASGI/async, breaks context in Celery/WebSockets/Cache, and forces business code to be aware of multi-tenancy.

`django-saas-kit` solves this by adopting a **Process-Bound Schema Architecture (Isolated Instance on Shared PostgreSQL DB)**:
- Each tenant runs as an independent Single-Tenant Django process/container bound at startup to its PostgreSQL schema via `OPTIONS['options'] = '-c search_path=<tenant_schema>,public'`.
- A **Master Instance (Control Plane)** runs with `SAAS_TENANT_SCHEMA='public'`, managing shared models (`SAAS_PUBLIC_MODELS`) and the central directory of tenants (`SAAS_TENANT_MODEL`).
- Business application code (models, views, serializers, Celery tasks) remains 100% single-tenant and agnostic.

## 2. Goals, Non-Goals, and Anti-Goals
- **Goals**:
  - Provide a clean `configure_saas_databases()` helper that configures `default` (bound to `<tenant_schema>,public`) and `public` (bound to `public`) database connections.
  - Provide an extensible, swappable `Tenant` model (`AbstractTenant` + `SAAS_TENANT_MODEL`, similar to `AUTH_USER_MODEL`) stored in `public`.
  - Provide `PublicTenantRouter` to route reads, writes, relations, and migrations between `public` and `default` connections, automatically treating `SAAS_TENANT_MODEL` as a public model and preventing non-master instances from mutating the `Tenant` registry unless explicitly allowed.
  - Provide `TenantActiveMiddleware` (optional) so tenant instances can verify their `is_active` subscription status from `public` with local TTL caching, blocking access (`403 Forbidden`) when suspended without ever mutating `search_path`.
  - Provide safe PostgreSQL schema utilities (`validate_schema_name`, `create_schema`, `schema_exists`, `list_schemas`).
  - Provide management commands: `provision_tenant` and `migrate_all_schemas`.
- **Non-Goals (Phase 1)**:
  - Docker/Kubernetes container orchestration templates (deferred to Phase 2 scaffolding).
  - Billing provider (Stripe/Paddle) SDK integrations.
- **Anti-Goals**:
  - Never mutate `search_path` dynamically per HTTP request inside a middleware.
  - Never require business models to inherit from custom tenant mixins.

## 3. Constraints & Tech Stack
- **Package Name**: `django-saas-kit` (importable as `django_saas_kit`).
- **Layout**: `src/django_saas_kit/` (`src-layout` with PEP 621 `pyproject.toml`).
- **Python**: `>=3.10`
- **Django**: `>=4.2`
- **Schema Naming Rules**: Valid PostgreSQL identifier matching `^[a-z][a-z0-9_]{0,62}$`, forbidding reserved PostgreSQL system prefixes (`pg_`, `information_schema`).

## 4. Approaches Considered
1. **Catalog-Only (`information_schema.schemata`)**: Zero extra tables, discovers schemas from Postgres catalog. Rejected as standalone because it cannot store business metadata (`is_active`, `name`) needed to suspend unpaid tenants or manage tenants from Django Admin.
2. **Hardcoded Concrete `Tenant` Model**: Includes a fixed model in `public`. Rejected because SaaS owners often need custom fields (plans, Stripe IDs, container ports) later.
3. **Swappable `AbstractTenant` + Default `django_saas_kit.Tenant` in `public` (Selected)**: Follows Django's `AUTH_USER_MODEL` pattern (`SAAS_TENANT_MODEL = 'django_saas_kit.Tenant'`). Works out-of-the-box with Django Admin, supports `is_active` subscription checks across containers, and can be swapped for a custom model anytime.

## 5. Architecture & Component Specifications

### 5.1 Settings & Database Helper (`conf.py`, `helpers.py`)
- `SAAS_TENANT_SCHEMA`: Current instance schema (default from `os.environ.get("TENANT_SCHEMA", "public")`).
- `SAAS_PUBLIC_MODELS`: List of `'app_label.ModelName'` or `'app_label.*'` strings (e.g. `['auth.*', 'sessions.*']`). Always implicitly includes `SAAS_TENANT_MODEL` and `'django_saas_kit.*'`.
- `SAAS_TENANT_MODEL`: Swappable model string, default `'django_saas_kit.Tenant'`.
- `SAAS_PUBLIC_DB_ALIAS`: Default `'public'`.
- `SAAS_DEFAULT_DB_ALIAS`: Default `'default'`.
- `SAAS_PROTECT_TENANT_MODEL_WRITES`: Default `True` (blocks writes to `SAAS_TENANT_MODEL` when `SAAS_TENANT_SCHEMA != 'public'`).
- `SAAS_STATUS_CACHE_TTL`: Default `60` seconds.
- `configure_saas_databases(base_config: dict, tenant_schema: str | None = None) -> dict`: Returns `{'default': ..., 'public': ...}` with `OPTIONS['options']` properly set to `-c search_path=<tenant_schema>,public` for `default` and `-c search_path=public` for `public`.

### 5.2 Swappable Tenant Model & Utilities (`models.py`, `utils.py`, `admin.py`)
- `validate_schema_name(value: str) -> None`: Raises `ValidationError` if `value` does not match `^[a-z][a-z0-9_]{0,62}$`, starts with `pg_`, or equals `information_schema`.
- `AbstractTenant(models.Model)`:
  - `schema_name = models.CharField(max_length=63, unique=True, db_index=True, validators=[validate_schema_name])`
  - `name = models.CharField(max_length=150)`
  - `domain = models.CharField(max_length=253, blank=True, default="")`
  - `is_active = models.BooleanField(default=True, db_index=True)`
  - `created_at = models.DateTimeField(auto_now_add=True)`
  - `updated_at = models.DateTimeField(auto_now=True)`
- `Tenant(AbstractTenant)`: Concrete model with `Meta.swappable = "SAAS_TENANT_MODEL"`.
- `get_tenant_model()`: Wraps `django.apps.apps.get_model(saas_settings.TENANT_MODEL)`.
- `get_current_tenant(using: str | None = None) -> AbstractTenant | None`: Queries `get_tenant_model().objects.using(public_alias).filter(schema_name=current_schema).first()`.

### 5.3 Custom Database Router (`routers.py`)
- `PublicTenantRouter`:
  - `db_for_read(model, **hints)`: Returns `SAAS_PUBLIC_DB_ALIAS` (`'public'`) if model matches `SAAS_PUBLIC_MODELS`, else `SAAS_DEFAULT_DB_ALIAS` (`'default'`).
  - `db_for_write(model, **hints)`:
    - If model is `SAAS_TENANT_MODEL` and `SAAS_TENANT_SCHEMA != 'public'` and `SAAS_PROTECT_TENANT_MODEL_WRITES` is `True` (and `hints.get("force_public_write")` is not `True`), raises `PermissionDenied("Tenant instances cannot modify the master Tenant registry.")`.
    - Returns `'public'` if model matches `SAAS_PUBLIC_MODELS`, else `'default'`.
  - `allow_relation(obj1, obj2, **hints)`: Returns `True` if both `obj1._state.db` and `obj2._state.db` belong to `{SAAS_DEFAULT_DB_ALIAS, SAAS_PUBLIC_DB_ALIAS}`.
  - `allow_migrate(db, app_label, model_name=None, **hints)`:
    - If `db == SAAS_PUBLIC_DB_ALIAS`: Returns `True` only for public models; `False` for tenant models.
    - If `db == SAAS_DEFAULT_DB_ALIAS`:
      - When `SAAS_TENANT_SCHEMA == 'public'` (and no active override schema in thread-local migration context): behaves like `'public'` (migrates public models only).
      - When migrating a tenant schema (`SAAS_TENANT_SCHEMA != 'public'` or active tenant migration context): returns `False` for public models and `True` for tenant models.

### 5.4 Tenant Active Guard Middleware (`middleware.py`)
- `TenantActiveMiddleware`:
  - If `SAAS_TENANT_SCHEMA == 'public'`, passes through immediately.
  - Checks Django cache (`saas_kit:tenant_active:<schema_name>`) with TTL `SAAS_STATUS_CACHE_TTL`.
  - On cache miss, queries `get_current_tenant()` from `'public'` DB and caches `bool(tenant and tenant.is_active)`.
  - If inactive or missing, returns `HttpResponseForbidden` (or JSON `403` if `Accept: application/json`).

### 5.5 Schema DDL & Management Commands (`schema.py`, `management/commands/`)
- `schema.py`:
  - `create_schema(schema_name: str, using: str = 'public') -> bool`: Validates name and executes `CREATE SCHEMA IF NOT EXISTS "<schema_name>"`.
  - `schema_exists(schema_name: str, using: str = 'public') -> bool`: Queries `information_schema.schemata`.
  - `tenant_migration_context(schema_name: str, using: str = 'default')`: Context manager that sets thread-local active tenant schema for the router and runs `SET search_path TO "<schema_name>", public` on the connection (restoring previous `search_path` on exit).
- `provision_tenant <schema_name> [--name NAME] [--domain DOMAIN] [--no-migrate] [--inactive]`:
  - Validates `schema_name` (cannot be `'public'`).
  - Creates or updates the `Tenant` record in `'public'`.
  - Executes `create_schema(schema_name)`.
  - Unless `--no-migrate`, enters `tenant_migration_context(schema_name)` and runs `call_command('migrate', database='default')`.
- `migrate_all_schemas [--public-only] [--tenants-only] [--include-inactive] [--schema SCHEMA]`:
  - Unless `--tenants-only`, runs `call_command('migrate', database='public')`.
  - Unless `--public-only`, queries `get_tenant_model().objects.using('public')` (filtered by `is_active=True` unless `--include-inactive`, or filtered by `--schema`), and for each tenant enters `tenant_migration_context(tenant.schema_name)` and runs `call_command('migrate', database='default')`.
