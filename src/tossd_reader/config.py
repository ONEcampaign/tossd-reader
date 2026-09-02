"""Module-level cache-directory and offline-mode state for tossd_reader.

Cache-directory resolution defers to readerkit's own precedence: an explicit
`set_cache_dir` override wins, then the `TOSSD_READER_CACHE_DIR` environment
variable (readerkit derives this name itself from `app="tossd-reader"`), then
platformdirs. `get_cache()` is the lazy singleton `fetch.py` uses to store
downloaded vintages: one `readerkit.ArtifactCache` in the `"raw"` namespace,
with hardcoded size/count bounds and no user-facing config surface.

Offline mode (`get_offline`/`set_offline`) follows the identical precedence
pattern, one level down: an explicit `set_offline` override wins, then the
`TOSSD_READER_OFFLINE` environment variable, re-read on every call.

No pandas import at module scope: `import tossd_reader` must stay light (see
`__init__.py`'s own docstring), so `cache_info()` -- the one function here that
returns a `DataFrame` -- imports pandas inside its own body instead.
"""

from __future__ import annotations

import enum
import os
import warnings
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final

from readerkit import ArtifactCache, ArtifactEntry, resolve_cache_dir

from tossd_reader import _provenance

if TYPE_CHECKING:
    import pandas as pd

_APP_NAME: Final = "tossd-reader"
_CACHE_GENERATION: Final = "1"
"""Coarse cache-layout generation, passed as readerkit's `app_version`, kept
independent of the package's semver `__version__`. Bump only when the on-disk
artifact/key layout this cache depends on changes — a patch release must not
force re-downloading the ~2.4M-row dataset."""

_NAMESPACE: Final = "raw"
_KEEP_N: Final = 24
_MAX_BYTES: Final = 4 * 1024**3  # 4 GB, hardcoded (no user config surface)

_OFFLINE_ENV_VAR: Final = "TOSSD_READER_OFFLINE"
_OFFLINE_TRUTHY_VALUES: Final = frozenset({"1", "true", "yes"})
_OFFLINE_FALSY_VALUES: Final = frozenset({"0", "false", "no"})
"""Case-insensitive. Every other non-empty, unrecognised value (e.g. `"offline"`, `"2"`) still
reads as not-offline, but warns once per process -- see `_warn_unrecognized_offline_value` --
since the caller likely meant to enable offline mode and didn't. `""` and unset stay silent."""


class _Sentinel(enum.Enum):
    """Sentinel values for `_CacheState.dir_override`/`built_for`.

    `None` can't serve as the "not set" marker here because `None` is
    itself a meaningful user-supplied value: `set_cache_dir(None)` requests
    ephemeral bypass mode, which must stay distinguishable from `set_cache_dir`
    never having been called at all. Members compare by `is` identity, unlike
    the `isinstance` checks a pair of sentinel classes would need (which would
    also, wrongly, accept a subclass instance).
    """

    UNSET = enum.auto()
    """`set_cache_dir` has never been called."""

    BYPASS = enum.auto()
    """`set_cache_dir(None)` requested ephemeral bypass mode."""


class _CacheState:
    """Mutable singleton state backing this module's cache accessors.

    A plain class instead of module globals so `set_cache_dir`/`get_cache`
    can mutate it by attribute assignment rather than a `global` statement.
    """

    def __init__(self) -> None:
        self.dir_override: _Sentinel | Path = _Sentinel.UNSET
        self.cache: ArtifactCache | None = None
        self.built_for: _Sentinel | Path | None = _Sentinel.UNSET


_state = _CacheState()


class _OfflineState:
    """Mutable singleton state backing `get_offline`/`set_offline`.

    Same shape as `_CacheState`: a plain class instead of a module global so `set_offline` can
    mutate it by attribute assignment. Reuses `_Sentinel.UNSET` (defined above for the cache-dir
    override) as its own "no explicit override" marker -- a second, offline-specific sentinel
    would mean the same thing.
    """

    def __init__(self) -> None:
        self.override: bool | _Sentinel = _Sentinel.UNSET
        self.warned_unrecognized_value: bool = False
        """Whether `_warn_unrecognized_offline_value` has already fired this process."""


_offline_state = _OfflineState()


def get_cache_dir() -> Path | None:
    """Resolve the effective cache directory right now.

    Re-reads `TOSSD_READER_CACHE_DIR` on every call (unless an explicit
    `set_cache_dir` override is active), so environment changes between calls
    take effect without any extra reset step.

    Returns:
        The resolved, existing, writable directory, or `None` when
        `set_cache_dir(None)` put the module into ephemeral bypass mode.
    """
    override = _state.dir_override
    if override is _Sentinel.BYPASS:
        return None
    if override is _Sentinel.UNSET:
        return resolve_cache_dir(
            app=_APP_NAME, app_version=_CACHE_GENERATION, cache_dir=None
        )
    return resolve_cache_dir(
        app=_APP_NAME, app_version=_CACHE_GENERATION, cache_dir=override
    )


def set_cache_dir(path: str | Path | None) -> None:
    """Re-point tossd_reader's cache to `path`.

    Args:
        path: Explicit cache-directory override, taking precedence over
            `TOSSD_READER_CACHE_DIR`. `None` switches to an ephemeral,
            session-scoped bypass instead: fetches go to a `TemporaryDirectory`
            for the life of the process (or until `set_cache_dir` is called
            again), and nothing written during the bypass persists.
    """
    if _state.cache is not None:
        _state.cache.close()
    _state.cache = None
    _state.built_for = _Sentinel.UNSET
    _state.dir_override = _Sentinel.BYPASS if path is None else Path(path)


def get_cache() -> ArtifactCache:
    """Return the module-level `"raw"`-namespace `ArtifactCache` singleton.

    Rebuilt whenever the effective cache directory changes: on first access,
    right after `set_cache_dir`, or whenever `TOSSD_READER_CACHE_DIR` itself
    changes between calls (which is how the test suite's per-test `tmp_path`
    isolation reaches this singleton with no extra reset hook).

    Returns:
        The current `ArtifactCache`, backed by a real directory or, in
        ephemeral bypass mode, a `TemporaryDirectory` owned by the cache
        itself.
    """
    current_dir = get_cache_dir()
    if _state.cache is None or _state.built_for != current_dir:
        if _state.cache is not None:
            _state.cache.close()
        _state.cache = ArtifactCache(
            cache_dir=current_dir,
            namespace=_NAMESPACE,
            keep_n=_KEEP_N,
            max_bytes=_MAX_BYTES,
        )
        _state.built_for = current_dir
    return _state.cache


def get_offline() -> bool:
    """Resolve whether tossd_reader is in offline mode right now.

    Re-reads `TOSSD_READER_OFFLINE` on every call (unless an explicit `set_offline` override is
    active), the same precedence `get_cache_dir` follows for the cache directory.

    Returns:
        `True` when offline mode is active: no fetch touches the network -- every requested
        vintage is served from the local cache instead (a loud warning either way, the same one
        an unplanned network outage triggers), or `TossdNetworkError` is raised when nothing
        usable is cached. `False` (the default, with no override and no env var set) leaves
        fetch behaviour untouched. `False` too when the env var is set but unrecognised (neither
        truthy nor recognised-falsy) -- that case also warns once per process, naming the value
        seen, since the caller likely meant to enable offline mode and didn't.
    """
    override = _offline_state.override
    if isinstance(override, bool):
        return override
    raw = os.environ.get(_OFFLINE_ENV_VAR)
    if raw is None:
        return False
    normalized = raw.strip().casefold()
    if normalized in _OFFLINE_TRUTHY_VALUES:
        return True
    if normalized and normalized not in _OFFLINE_FALSY_VALUES:
        _warn_unrecognized_offline_value(raw)
    return False


def _warn_unrecognized_offline_value(raw: str) -> None:
    """Warn once per process that `TOSSD_READER_OFFLINE` is set to a value nobody recognises.

    Loud, and only once: a silent fallback to not-offline here would leave a caller who typo'd
    (e.g. `"offline"`, `"on"`) believing offline mode is active while `get_offline()` quietly
    disagrees and every fetch keeps hitting the network.
    """
    if _offline_state.warned_unrecognized_value:
        return
    _offline_state.warned_unrecognized_value = True
    truthy = ", ".join(sorted(_OFFLINE_TRUTHY_VALUES))
    warnings.warn(
        f"{_OFFLINE_ENV_VAR}={raw!r} is not a recognized value; offline mode is NOT "
        f"active. Recognised truthy values are {truthy} (case-insensitive).",
        stacklevel=3,
    )


def set_offline(flag: bool | None) -> None:
    """Override tossd_reader's offline mode.

    Args:
        flag: `True` forces offline mode on; `False` forces it off, even if
            `TOSSD_READER_OFFLINE` is set. `None` resets to env-var-driven resolution -- the
            state `set_offline` has never been called at all.
    """
    _offline_state.override = _Sentinel.UNSET if flag is None else bool(flag)


def raise_if_offline_refresh_conflict(*, refresh: bool, func_name: str) -> None:
    """Raise `ValueError` naming the conflict when `refresh=True` while offline mode is active.

    A forced refresh needs the network by definition, which offline mode exists to rule out --
    shared by every public entry point whose `refresh=` would otherwise silently do nothing (or
    silently ignore the request): `get_tossd`, `get_tossd_raw`, `export` (via
    `query.build_table`), and `get_vintages`.

    Args:
        refresh: The caller's own `refresh=` argument, exactly as passed (not
            `readerkit.refresh.effective_refresh`'s resolved value -- an ambient
            `readerkit.refresh_scope()` is not "explicit" in the sense this conflict is about).
        func_name: The caller's own name, named in the raised message.

    Raises:
        ValueError: `refresh` is `True` and `get_offline()` is `True`.
    """
    if refresh and get_offline():
        raise ValueError(
            f"{func_name}(refresh=True) conflicts with offline mode (config.get_offline() is "
            "True): a forced refresh needs the network. Call tossd_reader.config.set_offline"
            "(False) first, or omit refresh=True."
        )


def _reset_for_tests() -> None:
    """Clear the cache-dir/offline overrides and close the cache singleton.

    Test-only. Lets a test that calls `set_cache_dir`/`set_offline` (or that relies on a fresh
    singleton, or that triggers `_warn_unrecognized_offline_value`'s warn-once state) restore
    module state without leaking into later tests that never touch this module directly.
    """
    if _state.cache is not None:
        _state.cache.close()
    _state.cache = None
    _state.built_for = _Sentinel.UNSET
    _state.dir_override = _Sentinel.UNSET
    _offline_state.override = _Sentinel.UNSET
    _offline_state.warned_unrecognized_value = False


# --- cache inspection / cleanup -------------------------------------------------

_CACHE_INFO_COLUMNS: Final = (
    "year",
    "etag",
    "retrieved_at",
    "downloaded_at",
    "size_bytes",
    "path",
)


def cache_info() -> pd.DataFrame:
    """List every locally cached vintage, superseded ones included -- start here to free space.

    One row per `get_cache().entries()` entry: a year with more than one cached vintage (a
    republished file downloaded again under a new ETag) gets one row per vintage, not one per
    year. Call `clear_cache()` directly to drop everything but each year's newest row here.

    Returns:
        `year` (parsed from the cache key; `None` for a foreign entry that doesn't match this
        package's own key shape -- should not happen in practice), `etag`, `retrieved_at` (both
        read from that vintage's own provenance sidecar, `None` when the sidecar is missing or
        corrupt), `downloaded_at` (a tz-aware `datetime`, from the cache's own sidecar metadata
        -- unlike `retrieved_at`, always present), `size_bytes`, `path`. Empty (with these
        columns) when nothing is cached, including in ephemeral bypass mode
        (`set_cache_dir(None)`).
    """
    import pandas as pd  # noqa: PLC0415 - lazy: config.py imports no pandas at module scope

    from tossd_reader import (  # noqa: PLC0415 - lazy: avoid a fetch<->config cycle at module scope
        fetch,
    )

    rows = [
        _cache_info_row(entry, key_year=fetch.key_year)
        for entry in get_cache().entries()
    ]
    return pd.DataFrame(rows, columns=list(_CACHE_INFO_COLUMNS))


def _cache_info_row(
    entry: ArtifactEntry, *, key_year: Callable[[str], int | None]
) -> dict[str, object]:
    """Build one `cache_info()` row from a `readerkit.ArtifactEntry`.

    Args:
        entry: One cached entry.
        key_year: `fetch.key_year`, threaded in rather than imported again per row.
    """
    provenance = _provenance.read_provenance(entry.path) or {}
    etag = provenance.get("etag")
    retrieved_at = provenance.get("retrieved_at")
    return {
        "year": key_year(entry.key),
        "etag": etag if isinstance(etag, str) else None,
        "retrieved_at": retrieved_at if isinstance(retrieved_at, str) else None,
        "downloaded_at": entry.downloaded_at,
        "size_bytes": entry.size_bytes,
        "path": entry.path,
    }


def clear_cache(
    *,
    years: int | Iterable[int] | None = None,
    before: str | date | datetime | None = None,
    keep_latest: bool = True,
) -> int:
    """Free local cache space. The bare `clear_cache()` call drops only superseded vintages.

    Args:
        years: Restrict to these years. `None` (the default) considers every cached year.
        before: Restrict to vintages retrieved before this point (a `date`, a `datetime`, or an
            ISO 8601 string -- a bare `date`/date-only string means midnight UTC that day; a
            naive `datetime`/datetime string is treated as UTC). Compared against each entry's
            own provenance `retrieved_at`, falling back to the cache's `downloaded_at` when the
            sidecar is missing or corrupt (see `cache_info()`). `None` (the default) applies no
            date filter.
        keep_latest: `True` (the default) never removes the single newest entry for a year, even
            one that otherwise matches `years=`/`before=` -- so the bare `clear_cache()` call
            (every argument at its default) removes exactly the superseded, non-newest vintages,
            freeing space while a fetch for any already-downloaded year still serves instantly
            from cache. `False` removes every entry matching `years=`/`before=`, the newest
            included -- `clear_cache(keep_latest=False)` with no other arguments empties the
            whole cache.

    Returns:
        The number of cache entries removed.

    Raises:
        OSError: A filesystem fault (e.g. a permission error) unlinking an entry's payload,
            sidecar, or provenance file propagates as-is, rather than being swallowed per-entry --
            a silent under-deletion would be worse than an abrupt stop. The cache may be left
            partially cleared; the `removed` count from a prior, non-raising call is the only way
            to know how much of a partial run actually completed.
    """
    from tossd_reader import (  # noqa: PLC0415 - lazy: avoid a fetch<->config cycle at module scope
        fetch,
    )

    years_filter = None if years is None else _as_year_set(years)
    before_at = _parse_before(before)
    cache = get_cache()
    entries = cache.entries()

    protected_keys = (
        _newest_key_per_year(entries, key_year=fetch.key_year) if keep_latest else {}
    )

    removed = 0
    for entry in entries:
        year = fetch.key_year(entry.key)
        if year is None:
            continue
        if years_filter is not None and year not in years_filter:
            continue
        if before_at is not None and _entry_retrieved_at(entry) >= before_at:
            continue
        if protected_keys.get(year) == entry.key:
            continue
        if cache.invalidate(entry.key):
            removed += 1
            # `cache.invalidate` only knows its own payload + internal sidecar; it has no idea
            # this package writes its own `<payload>.provenance.json` beside them. Left alone,
            # this file orphans: `_provenance.write_provenance_if_absent` no-ops when a file
            # already exists at this path, so a later re-fetch under the same cache key (a
            # closed-out historical year re-downloaded with an unchanged ETag) would silently
            # resurrect this stale sidecar instead of recording the fresh retrieval.
            # `missing_ok=True` since not every entry necessarily got a sidecar written for it.
            _provenance.sidecar_path(entry.path).unlink(missing_ok=True)
    return removed


def _as_year_set(years: int | Iterable[int]) -> set[int]:
    """Normalise `clear_cache`'s `years=` to a plain `set[int]`."""
    if isinstance(years, int):
        return {years}
    return {int(year) for year in years}


def _parse_before(before: str | date | datetime | None) -> datetime | None:
    """Parse `clear_cache`'s `before=` to a tz-aware `datetime`, or `None`."""
    if before is None:
        return None
    if isinstance(before, datetime):
        return before if before.tzinfo is not None else before.replace(tzinfo=UTC)
    if isinstance(before, date):
        return datetime(before.year, before.month, before.day, tzinfo=UTC)
    parsed = datetime.fromisoformat(before)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _newest_key_per_year(
    entries: list[ArtifactEntry], *, key_year: Callable[[str], int | None]
) -> dict[int, str]:
    """The single newest (`downloaded_at`) cache key per year, across every entry given."""
    newest: dict[int, ArtifactEntry] = {}
    for entry in entries:
        year = key_year(entry.key)
        if year is None:
            continue
        current = newest.get(year)
        if current is None or entry.downloaded_at > current.downloaded_at:
            newest[year] = entry
    return {year: entry.key for year, entry in newest.items()}


def _entry_retrieved_at(entry: ArtifactEntry) -> datetime:
    """`entry`'s own provenance `retrieved_at`, falling back to the cache's `downloaded_at`.

    A naive `retrieved_at` is normalised to UTC, the same rule `_parse_before` applies to a naive
    `before=` -- this package's own sidecar writes are always tz-aware, but a hand-edited or
    foreign sidecar need not be, and comparing a naive value against `_parse_before`'s always-aware
    result would raise `TypeError` rather than degrade.
    """
    provenance = _provenance.read_provenance(entry.path) or {}
    raw = provenance.get("retrieved_at")
    if isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            pass
        else:
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return entry.downloaded_at
