from __future__ import annotations

import copy
from typing import Any

from django_saas_kit.conf import saas_settings
from django_saas_kit.validators import validate_schema_name


def _append_search_path_option(existing_options: str, search_path_flag: str) -> str:
    prefix = existing_options.strip()
    if not prefix:
        return search_path_flag
    return f"{prefix} {search_path_flag}"


def configure_saas_databases(
    base_config: dict[str, Any],
    tenant_schema: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Build Django DATABASES dict with process-bound search_path for 'default' and 'public'."""
    active_schema = tenant_schema if tenant_schema is not None else saas_settings.TENANT_SCHEMA
    validate_schema_name(active_schema)

    default_db = copy.deepcopy(base_config)
    public_db = copy.deepcopy(base_config)

    default_options = dict(default_db.get("OPTIONS", {}))
    public_options = dict(public_db.get("OPTIONS", {}))

    existing_default_opt = str(default_options.get("options", ""))
    existing_public_opt = str(public_options.get("options", ""))

    if active_schema == "public":
        default_flag = "-c search_path=public"
    else:
        default_flag = f"-c search_path={active_schema},public"

    public_flag = "-c search_path=public"

    default_options["options"] = _append_search_path_option(
        existing_default_opt, default_flag
    )
    public_options["options"] = _append_search_path_option(
        existing_public_opt, public_flag
    )

    default_db["OPTIONS"] = default_options
    public_db["OPTIONS"] = public_options

    return {
        saas_settings.DEFAULT_DB_ALIAS: default_db,
        saas_settings.PUBLIC_DB_ALIAS: public_db,
    }
