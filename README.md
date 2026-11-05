# django-saas-kit

Process-bound PostgreSQL schema orchestration kit for Single-Tenant Django SaaS instances on a shared database.

## Key Features
- **Zero Request-Level Schema Switching**: Binds each tenant instance at startup via PostgreSQL `-c search_path=<tenant_schema>,public`.
- **`PublicTenantRouter`**: Routes shared models (`SAAS_PUBLIC_MODELS`) and the central `Tenant` directory to `public`, while keeping tenant business models isolated in their own schema.
- **Swappable `Tenant` Model**: Built-in `django_saas_kit.Tenant` (`AbstractTenant`) with `SAAS_TENANT_MODEL` support.
- **`TenantActiveMiddleware`**: Optional lightweight subscription status guard with local TTL caching to block suspended tenants (`403 Forbidden`) without touching `search_path`.
- **Management Commands**: `provision_tenant` and `migrate_all_schemas`.
