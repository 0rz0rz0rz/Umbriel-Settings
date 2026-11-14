"""Installed Umbriel schema access for the GUI; the logic lives in umbriel_core.schema."""

from umbriel_core import schema as _core_schema
from umbriel_core.schema import (  # noqa: F401  re-exported
    check_schema_coverage,
    load_umbriel_schema,
    schema_field_catalog,
    schema_options_by_path,
)

from . import state


def field_schema_option(path):
    """Find an installed-schema entry for a field's fully qualified TOML path."""
    return _core_schema.field_schema_option(state.ACTIVE_SCHEMA_OPTIONS, path)
