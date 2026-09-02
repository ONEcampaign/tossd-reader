"""Python package to access TOSSD activity-level data."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING

try:
    __version__ = version("tossd-reader")
except PackageNotFoundError:
    __version__ = "0.0.0"

if TYPE_CHECKING:
    from tossd_reader import codes as codes
    from tossd_reader._export import export as export
    from tossd_reader._export import load_export as load_export
    from tossd_reader._export import verify_export as verify_export
    from tossd_reader.analysis import add_instrument_group as add_instrument_group
    from tossd_reader.analysis import add_iso3 as add_iso3
    from tossd_reader.analysis import add_recipient_group as add_recipient_group
    from tossd_reader.analysis import explode_sdg as explode_sdg
    from tossd_reader.analysis import extract_keywords as extract_keywords
    from tossd_reader.analysis import filter_provider_costs as filter_provider_costs
    from tossd_reader.analysis import (
        get_instrument_groups_version as get_instrument_groups_version,
    )
    from tossd_reader.analysis import (
        get_recipient_groups_version as get_recipient_groups_version,
    )
    from tossd_reader.analysis import get_structural_breaks as get_structural_breaks
    from tossd_reader.codelists import get_available_filters as get_available_filters
    from tossd_reader.codelists import get_codelists_version as get_codelists_version
    from tossd_reader.config import cache_info as cache_info
    from tossd_reader.config import clear_cache as clear_cache
    from tossd_reader.config import get_cache_dir as get_cache_dir
    from tossd_reader.config import get_offline as get_offline
    from tossd_reader.config import set_cache_dir as set_cache_dir
    from tossd_reader.config import set_offline as set_offline
    from tossd_reader.exceptions import ExportIntegrityError as ExportIntegrityError
    from tossd_reader.exceptions import InvalidPillarError as InvalidPillarError
    from tossd_reader.exceptions import SchemaDriftError as SchemaDriftError
    from tossd_reader.exceptions import TossdNetworkError as TossdNetworkError
    from tossd_reader.exceptions import TossdReaderError as TossdReaderError
    from tossd_reader.exceptions import UnknownCodeError as UnknownCodeError
    from tossd_reader.exceptions import VintageValidationError as VintageValidationError
    from tossd_reader.fetch import get_tossd_raw as get_tossd_raw
    from tossd_reader.fetch import get_vintages as get_vintages
    from tossd_reader.query import FORCED_COLUMNS as FORCED_COLUMNS
    from tossd_reader.query import get_tossd as get_tossd
    from tossd_reader.verbs import compare_years as compare_years
    from tossd_reader.verbs import get_provenance as get_provenance
    from tossd_reader.verbs import keyword_totals as keyword_totals
    from tossd_reader.verbs import rank_entities as rank_entities
    from tossd_reader.verbs import reconcile as reconcile
    from tossd_reader.verbs import sdg_totals as sdg_totals
    from tossd_reader.verbs import subpillar_breakdown as subpillar_breakdown

__all__ = [
    "FORCED_COLUMNS",
    "ExportIntegrityError",
    "InvalidPillarError",
    "SchemaDriftError",
    "TossdNetworkError",
    "TossdReaderError",
    "UnknownCodeError",
    "VintageValidationError",
    "__version__",
    "add_instrument_group",
    "add_iso3",
    "add_recipient_group",
    "cache_info",
    "clear_cache",
    "codes",
    "compare_years",
    "explode_sdg",
    "export",
    "extract_keywords",
    "filter_provider_costs",
    "get_available_filters",
    "get_cache_dir",
    "get_codelists_version",
    "get_instrument_groups_version",
    "get_offline",
    "get_provenance",
    "get_recipient_groups_version",
    "get_structural_breaks",
    "get_tossd",
    "get_tossd_raw",
    "get_vintages",
    "keyword_totals",
    "load_export",
    "rank_entities",
    "reconcile",
    "sdg_totals",
    "set_cache_dir",
    "set_offline",
    "subpillar_breakdown",
    "verify_export",
]

_LAZY_ATTRS: dict[str, tuple[str, str | None]] = {
    "codes": ("tossd_reader.codes", None),
    "get_tossd_raw": ("tossd_reader.fetch", "get_tossd_raw"),
    "get_vintages": ("tossd_reader.fetch", "get_vintages"),
    "get_tossd": ("tossd_reader.query", "get_tossd"),
    "FORCED_COLUMNS": ("tossd_reader.query", "FORCED_COLUMNS"),
    "export": ("tossd_reader._export", "export"),
    "verify_export": ("tossd_reader._export", "verify_export"),
    "load_export": ("tossd_reader._export", "load_export"),
    "set_cache_dir": ("tossd_reader.config", "set_cache_dir"),
    "get_cache_dir": ("tossd_reader.config", "get_cache_dir"),
    "set_offline": ("tossd_reader.config", "set_offline"),
    "get_offline": ("tossd_reader.config", "get_offline"),
    "cache_info": ("tossd_reader.config", "cache_info"),
    "clear_cache": ("tossd_reader.config", "clear_cache"),
    "get_available_filters": ("tossd_reader.codelists", "get_available_filters"),
    "get_codelists_version": ("tossd_reader.codelists", "get_codelists_version"),
    "TossdReaderError": ("tossd_reader.exceptions", "TossdReaderError"),
    "TossdNetworkError": ("tossd_reader.exceptions", "TossdNetworkError"),
    "VintageValidationError": ("tossd_reader.exceptions", "VintageValidationError"),
    "SchemaDriftError": ("tossd_reader.exceptions", "SchemaDriftError"),
    "UnknownCodeError": ("tossd_reader.exceptions", "UnknownCodeError"),
    "InvalidPillarError": ("tossd_reader.exceptions", "InvalidPillarError"),
    "ExportIntegrityError": ("tossd_reader.exceptions", "ExportIntegrityError"),
    "explode_sdg": ("tossd_reader.analysis", "explode_sdg"),
    "add_iso3": ("tossd_reader.analysis", "add_iso3"),
    "extract_keywords": ("tossd_reader.analysis", "extract_keywords"),
    "get_structural_breaks": ("tossd_reader.analysis", "get_structural_breaks"),
    "filter_provider_costs": ("tossd_reader.analysis", "filter_provider_costs"),
    "add_recipient_group": ("tossd_reader.analysis", "add_recipient_group"),
    "add_instrument_group": ("tossd_reader.analysis", "add_instrument_group"),
    "get_recipient_groups_version": (
        "tossd_reader.analysis",
        "get_recipient_groups_version",
    ),
    "get_instrument_groups_version": (
        "tossd_reader.analysis",
        "get_instrument_groups_version",
    ),
    "rank_entities": ("tossd_reader.verbs", "rank_entities"),
    "compare_years": ("tossd_reader.verbs", "compare_years"),
    "sdg_totals": ("tossd_reader.verbs", "sdg_totals"),
    "keyword_totals": ("tossd_reader.verbs", "keyword_totals"),
    "subpillar_breakdown": ("tossd_reader.verbs", "subpillar_breakdown"),
    "reconcile": ("tossd_reader.verbs", "reconcile"),
    "get_provenance": ("tossd_reader.verbs", "get_provenance"),
}


def __getattr__(name: str) -> object:
    """Lazily resolve public attributes (PEP 562).

    Keeps `import tossd_reader` itself free of network access and of any
    module (`fetch`, `_discovery`, `config`) that could open a socket, since
    none of those are imported until one of their exported names is actually
    accessed. A `None` `attr_name` (only `"codes"` today) means the whole
    submodule is the public name -- `tossd_reader.codes.browse(...)`, not a
    single flattened function -- so the import itself, not a `getattr` on
    it, is the resolved value.
    """
    try:
        module_name, attr_name = _LAZY_ATTRS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    module = __import__(module_name, fromlist=[attr_name or module_name])
    return module if attr_name is None else getattr(module, attr_name)


def __dir__() -> list[str]:
    """Report the lazily-resolved public attributes alongside the eager ones."""
    return sorted(__all__)
