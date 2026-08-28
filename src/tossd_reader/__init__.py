"""Python package to access TOSSD activity-level data."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING

try:
    __version__ = version("tossd-reader")
except PackageNotFoundError:
    __version__ = "0.0.0"

if TYPE_CHECKING:
    from tossd_reader.codelists import get_available_filters as get_available_filters
    from tossd_reader.codelists import get_codelists_version as get_codelists_version
    from tossd_reader.config import set_cache_dir as set_cache_dir
    from tossd_reader.exceptions import InvalidPillarError as InvalidPillarError
    from tossd_reader.exceptions import SchemaDriftError as SchemaDriftError
    from tossd_reader.exceptions import TossdNetworkError as TossdNetworkError
    from tossd_reader.exceptions import TossdReaderError as TossdReaderError
    from tossd_reader.exceptions import UnknownCodeError as UnknownCodeError
    from tossd_reader.exceptions import VintageValidationError as VintageValidationError
    from tossd_reader.fetch import get_tossd_raw as get_tossd_raw
    from tossd_reader.query import get_tossd as get_tossd

__all__ = [
    "InvalidPillarError",
    "SchemaDriftError",
    "TossdNetworkError",
    "TossdReaderError",
    "UnknownCodeError",
    "VintageValidationError",
    "__version__",
    "get_available_filters",
    "get_codelists_version",
    "get_tossd",
    "get_tossd_raw",
    "set_cache_dir",
]

_LAZY_ATTRS: dict[str, tuple[str, str]] = {
    "get_tossd_raw": ("tossd_reader.fetch", "get_tossd_raw"),
    "get_tossd": ("tossd_reader.query", "get_tossd"),
    "set_cache_dir": ("tossd_reader.config", "set_cache_dir"),
    "get_available_filters": ("tossd_reader.codelists", "get_available_filters"),
    "get_codelists_version": ("tossd_reader.codelists", "get_codelists_version"),
    "TossdReaderError": ("tossd_reader.exceptions", "TossdReaderError"),
    "TossdNetworkError": ("tossd_reader.exceptions", "TossdNetworkError"),
    "VintageValidationError": ("tossd_reader.exceptions", "VintageValidationError"),
    "SchemaDriftError": ("tossd_reader.exceptions", "SchemaDriftError"),
    "UnknownCodeError": ("tossd_reader.exceptions", "UnknownCodeError"),
    "InvalidPillarError": ("tossd_reader.exceptions", "InvalidPillarError"),
}


def __getattr__(name: str) -> object:
    """Lazily resolve public attributes (PEP 562).

    Keeps `import tossd_reader` itself free of network access and of any
    module (`fetch`, `discovery`, `config`) that could open a socket, since
    none of those are imported until one of their exported names is actually
    accessed.
    """
    try:
        module_name, attr_name = _LAZY_ATTRS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    module = __import__(module_name, fromlist=[attr_name])
    return getattr(module, attr_name)


def __dir__() -> list[str]:
    """Report the lazily-resolved public attributes alongside the eager ones."""
    return sorted(__all__)
