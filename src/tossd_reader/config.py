"""Module-level cache-directory state for tossd_reader.

Cache-directory resolution defers to readerkit's own precedence: an explicit
`set_cache_dir` override wins, then the `TOSSD_READER_CACHE_DIR` environment
variable (readerkit derives this name itself from `app="tossd-reader"`), then
platformdirs. `get_cache()` is the lazy singleton `fetch.py` uses to store
downloaded vintages: one `readerkit.ArtifactCache` in the `"raw"` namespace,
with hardcoded size/count bounds and no user-facing config surface.
"""

from __future__ import annotations

import enum
from pathlib import Path
from typing import Final

from readerkit import ArtifactCache, resolve_cache_dir

_APP_NAME: Final = "tossd-reader"
_CACHE_GENERATION: Final = "1"
"""Coarse cache-layout generation, passed as readerkit's `app_version`, kept
independent of the package's semver `__version__`. Bump only when the on-disk
artifact/key layout this cache depends on changes — a patch release must not
force re-downloading the ~2.4M-row dataset."""

_NAMESPACE: Final = "raw"
_KEEP_N: Final = 24
_MAX_BYTES: Final = 4 * 1024**3  # 4 GB, hardcoded (no user config surface)


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


def _reset_for_tests() -> None:
    """Clear the cache-dir override and close the cache singleton.

    Test-only. Lets a test that calls `set_cache_dir` (or that relies on a
    fresh singleton) restore module state without leaking into later tests
    that never touch this module directly.
    """
    if _state.cache is not None:
        _state.cache.close()
    _state.cache = None
    _state.built_for = _Sentinel.UNSET
    _state.dir_override = _Sentinel.UNSET
