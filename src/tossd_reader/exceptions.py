"""tossd_reader's public exception hierarchy.

One base, `TossdReaderError`, with a shallow tree of purpose-specific
subclasses below it. `SchemaDriftError`, `UnknownCodeError` and
`InvalidPillarError` are defined here so the whole hierarchy is importable
from this module alone, but they are raised by later slices (the schema layer
and the query layer respectively), not by anything in this one.
"""

from __future__ import annotations

from pathlib import Path


class TossdReaderError(Exception):
    """Base for every error tossd_reader raises."""


class TossdNetworkError(TossdReaderError):
    """Raised when the publisher is unreachable and no usable cached vintage exists.

    Attributes:
        cache_dir: The cache directory that was checked for a usable vintage,
            or `None` when the cache is in ephemeral bypass mode
            (`set_cache_dir(None)`).
    """

    def __init__(self, message: str, *, cache_dir: Path | None = None) -> None:
        """
        Args:
            message: Human-readable description, already naming the cache
                directory and offline state.
            cache_dir: The cache directory that was checked for a usable
                vintage, or `None` in ephemeral bypass mode.
        """
        self.cache_dir = cache_dir
        super().__init__(message)


class VintageValidationError(TossdReaderError):
    """Raised when a freshly downloaded vintage fails D10 structural validation.

    Never raised for an already-cached vintage; validation runs once, on a new
    download only.

    Attributes:
        year: The reporting year of the rejected vintage.
        url: The URL the vintage was downloaded from.
    """

    def __init__(self, message: str, *, year: int, url: str) -> None:
        """
        Args:
            message: Human-readable description naming the year and url.
            year: The reporting year of the rejected vintage.
            url: The URL the vintage was downloaded from.
        """
        self.year = year
        self.url = url
        super().__init__(message)


class SchemaDriftError(TossdReaderError):
    """Raised when a published file's columns no longer match the packaged schema.

    Raised by the schema layer (slice 1.2), not by anything in this slice.
    """


class UnknownCodeError(TossdReaderError):
    """Raised when a provider/recipient name or code cannot be resolved.

    Raised by the query layer (slice 2.2), which attaches ranked resolvekit
    suggestions to the message. Left as a minimal placeholder here.
    """


class InvalidPillarError(TossdReaderError):
    """Raised when a sub-pillar filter is requested for a year that cannot support it.

    Raised by the query layer (slice 2.2). Left as a minimal placeholder here.
    """
