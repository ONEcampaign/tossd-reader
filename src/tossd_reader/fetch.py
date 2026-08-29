"""Fetch and cache raw TOSSD parquet vintages.

`fetch_year` returns a path to one year's cached, publisher-bytes-verbatim
parquet file. `get_tossd_raw` is the public entry point that fetches one or
more years and concatenates them, still as published (no renaming, no dtype
work — that's the schema layer).
"""

from __future__ import annotations

import warnings
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import requests
from readerkit import ArtifactCorruptError, FetchContext, Fetcher
from readerkit.refresh import effective_refresh

from tossd_reader import _discovery, _provenance, config
from tossd_reader.exceptions import TossdNetworkError, VintageValidationError

_KEY_PREFIX = "tossd_"
_TTL = timedelta(days=3650)
"""Effectively unbounded: the cache key already embeds the vintage's ETag, so
a fixed key's content never goes stale. Staleness is decided at the discovery
layer (whether a *new* ETag exists upstream), not by this TTL."""


def get_tossd_raw(
    *, years: int | Iterable[int] | None = None, refresh: bool = False
) -> pd.DataFrame:
    """Return raw TOSSD activity-level data, exactly as published.

    No renaming, no dtype casting, no unit conversion — publisher column
    names, dtypes, and column order, verbatim.

    Args:
        years: A single year, or an iterable of years (a `range` included).
            `None` (the default) fetches the packaged known-years set.
        refresh: Re-run discovery's HEAD sweep and force a readerkit
            conditional GET for every requested year. An enclosing
            `readerkit.refresh_scope()` has the same effect.

    Returns:
        A `pandas.DataFrame`, one row per activity, across every requested
        year.

    Raises:
        ValueError: `years` resolves to an empty set of years.
    """
    resolved_years = normalise_years(years)
    # Resolved once for every requested year, rather than once per year: a
    # per-year `discover()` call would re-run the whole HEAD sweep N times
    # under `refresh=True` (or an enclosing `refresh_scope()`).
    effective = effective_refresh("tossd_reader:get_tossd_raw", explicit=refresh)
    vintages = sweep_or_none(effective)
    tables = [
        pq.read_table(resolve_year(year, vintages=vintages, refresh=effective))
        for year in resolved_years
    ]
    combined = pa.concat_tables(tables)
    return combined.to_pandas()


def normalise_years(years: int | Iterable[int] | None) -> tuple[int, ...]:
    """Normalise `years` (scalar / iterable / range) to a sorted tuple immediately.

    Raises:
        ValueError: `years` is an empty iterable (an empty `pa.concat_tables`
            call raises an opaque pyarrow error, so this is caught early).
    """
    if years is None:
        return _discovery.known_years()
    if isinstance(years, int):
        return (years,)
    resolved = tuple(sorted({int(year) for year in years}))
    if not resolved:
        raise ValueError(
            "years is empty: pass at least one year, or None for the packaged "
            "known-years set."
        )
    return resolved


def fetch_year(year: int, *, refresh: bool = False) -> Path:
    """Return the path to the cached raw parquet for `year`, publisher bytes verbatim.

    A network outage (at discovery time, or a connection dropped partway
    through the download) or a since-unpublished year is served from the
    newest local vintage with a loud warning when one is cached, and raises
    `TossdNetworkError` when nothing usable exists locally.

    Args:
        year: The reporting year to fetch. Need not be in `known_years()`;
            an explicitly requested year is honoured when discovery finds it.
        refresh: Re-run discovery's HEAD sweep and force a readerkit
            conditional GET. An enclosing `readerkit.refresh_scope()` has the
            same effect even when this stays `False`.

    Returns:
        Path to the cached parquet payload.

    Raises:
        TossdNetworkError: The publisher is unreachable (at discovery time,
            or the GET connection dropped partway through downloading a new
            vintage) and nothing is cached for `year`; `year` is not
            currently published (and `refresh` was requested, or nothing is
            cached for it either); or the GET response's ETag kept changing
            across every retry attempt.
        VintageValidationError: A newly downloaded vintage failed structural
            validation.
        ValueError: `year` is not currently published by the source and
            nothing is cached for it.
    """
    effective = effective_refresh(f"tossd_reader:fetch_year:{year}", explicit=refresh)
    vintages = sweep_or_none(effective)
    return resolve_year(year, vintages=vintages, refresh=effective)


def sweep_or_none(refresh: bool) -> dict[int, _discovery.VintageInfo] | None:
    """Run discovery's HEAD sweep, or `None` when the publisher host is unreachable."""
    try:
        return _discovery.discover(refresh=refresh)
    except TossdNetworkError:
        return None


def resolve_year(
    year: int, *, vintages: dict[int, _discovery.VintageInfo] | None, refresh: bool
) -> Path:
    """Resolve one year against an already-swept `vintages` mapping (or `None`).

    Shared by `fetch_year` and `get_tossd_raw`, so a caller fetching several
    years in one `get_tossd_raw` call sweeps discovery exactly once and
    threads the same mapping and refresh flag through every year, instead of
    re-sweeping per year.
    """
    if vintages is None:
        return _serve_offline(year, reason="the network is unreachable")

    info = vintages.get(year)
    if info is None:
        return _serve_missing(year, refresh=refresh, available=tuple(sorted(vintages)))

    try:
        return _download_and_cache(year, info, refresh=refresh)
    except _FetcherNetworkError as exc:
        return _serve_offline(year, reason=f"the network is unreachable ({exc})")


@dataclass(frozen=True)
class _CachedVintage:
    """One locally cached vintage, with enough metadata to describe it in a warning."""

    path: Path
    etag: str | None
    retrieved_at: datetime | None


def _latest_cached(year: int) -> _CachedVintage | None:
    """Return the newest cached entry for `year`, or `None` if nothing is cached."""
    cache = config.get_cache()
    prefix = f"{_KEY_PREFIX}{year}_"
    candidates = [entry for entry in cache.entries() if entry.key.startswith(prefix)]
    if not candidates:
        return None
    newest = max(candidates, key=lambda entry: entry.downloaded_at)
    provenance = _provenance.read_provenance(newest.path) or {}
    etag = _as_str(provenance.get("etag"))
    retrieved_at_raw = _as_str(provenance.get("retrieved_at"))
    try:
        retrieved_at = (
            datetime.fromisoformat(retrieved_at_raw)
            if retrieved_at_raw is not None
            else None
        )
    except ValueError:
        # A garbage date inside otherwise-valid JSON: degrade to the mtime
        # fallback, same as a missing sidecar.
        retrieved_at = None
    return _CachedVintage(path=newest.path, etag=etag, retrieved_at=retrieved_at)


def _as_str(value: object) -> str | None:
    """Narrow a provenance-JSON field to `str`, or `None` if it isn't one."""
    return value if isinstance(value, str) else None


def _serve_offline(year: int, *, reason: str) -> Path:
    """Serve the newest cached vintage, or raise, when the network is unreachable for this whole sweep."""
    cached = _latest_cached(year)
    if cached is None:
        cache_dir = config.get_cache_dir()
        raise TossdNetworkError(
            f"Cannot fetch {year}: {reason}, and no cached vintage for {year} "
            f"exists in {cache_dir}.",
            cache_dir=cache_dir,
        )
    _warn_serving_stale(year, cached, reason=reason)
    return cached.path


def _serve_missing(year: int, *, refresh: bool, available: tuple[int, ...]) -> Path:
    """Serve the newest cached vintage, or raise, when the sweep ran but `year` was not among its results."""
    cached = _latest_cached(year)
    if cached is None:
        raise ValueError(
            f"{year} is not currently published by the source. Years "
            f"available right now: {list(available)}."
        )
    if refresh:
        raise TossdNetworkError(
            f"The publisher no longer lists {year}, so refresh=True cannot "
            "revalidate it. Omit refresh to keep serving the cached vintage.",
            cache_dir=config.get_cache_dir(),
        )
    _warn_serving_stale(year, cached, reason=f"the publisher no longer lists {year}")
    return cached.path


def _warn_serving_stale(year: int, cached: _CachedVintage, *, reason: str) -> None:
    """Emit the one loud warning naming the vintage date being served instead."""
    if cached.retrieved_at is not None:
        vintage_date = cached.retrieved_at.isoformat()
    else:
        vintage_date = datetime.fromtimestamp(
            cached.path.stat().st_mtime, tz=UTC
        ).isoformat()
    etag_note = f" (etag {cached.etag})" if cached.etag else ""
    warnings.warn(
        f"{reason.capitalize()}; serving the cached {year} vintage retrieved "
        f"{vintage_date}{etag_note}.",
        # 5 frames up from here: _warn_serving_stale -> _serve_offline/
        # _serve_missing -> resolve_year -> fetch_year/get_tossd_raw ->
        # the caller.
        stacklevel=5,
    )


class _EtagMismatchError(Exception):
    """Internal signal: the GET response's ETag differs from the expected one.

    Raised by `_make_fetcher`'s `Fetcher` before any bytes are written, so the
    caller can retry `ArtifactCache.ensure` under the correct key without
    discarding a partial download.
    """

    def __init__(self, get_etag: str | None) -> None:
        self.get_etag = get_etag
        super().__init__(
            f"GET ETag {get_etag!r} does not match the candidate cache key"
        )


class _FetcherNetworkError(TossdNetworkError):
    """Internal signal: the GET connection failed or truncated mid-transfer.

    A `TossdNetworkError` subclass (so it satisfies that public contract on
    its own), but kept distinct so `resolve_year` can route only *this*
    failure into the cached-vintage fallback. A retry-exhaustion
    `TossdNetworkError` (mismatching ETags on every attempt) is raised as the
    plain base class instead, so it propagates directly rather than being
    mistaken for an offline condition.
    """


_MAX_ETAG_ATTEMPTS = 2


def _download_and_cache(
    year: int, info: _discovery.VintageInfo, *, refresh: bool
) -> Path:
    """Download (or reuse) the cached artifact for `year`.

    The HEAD-derived `info.etag` only forms the *candidate* cache key. If the
    GET response's own ETag differs, the download is retried once under the
    corrected, authoritative key.

    Raises:
        TossdNetworkError: The GET connection dropped or truncated
            mid-transfer (a `_FetcherNetworkError`, so `resolve_year` can
            route it into the offline fallback); or the GET response's ETag
            kept changing across every retry attempt.
        VintageValidationError: The downloaded vintage failed structural
            validation.
    """
    cache = config.get_cache()
    session = _discovery.get_session()
    etag = info.etag
    etag_history = [etag]

    for _attempt in range(_MAX_ETAG_ATTEMPTS):
        key = f"{_KEY_PREFIX}{year}_{etag or 'unknown'}"
        fetcher, captured = _make_fetcher(
            info.url, session, year=year, expected_etag=etag
        )
        try:
            path = cache.ensure(
                key,
                fetcher=fetcher,
                ttl=_TTL,
                validator=_validate_new_vintage,
                suffix=".parquet",
                refresh=refresh,
            )
        except _EtagMismatchError as exc:
            etag = exc.get_etag
            etag_history.append(etag)
            continue
        except ArtifactCorruptError as exc:
            raise VintageValidationError(
                f"The downloaded {year} vintage failed validation: {exc.reason}",
                year=year,
                url=info.url,
            ) from exc

        _provenance.write_provenance_if_absent(
            path, url=info.url, captured=captured, etag_fallback=etag
        )
        return path

    raise TossdNetworkError(
        f"Could not fetch {year} from {info.url}: the GET response's ETag kept "
        f"changing across all {_MAX_ETAG_ATTEMPTS} attempts "
        f"({' -> '.join(repr(seen) for seen in etag_history)}) — the publisher's "
        "content is changing faster than the retry window. Try again shortly.",
        cache_dir=config.get_cache_dir(),
    )


def _make_fetcher(
    url: str, session: requests.Session, *, year: int, expected_etag: str | None
) -> tuple[Fetcher, dict[str, str | int | None]]:
    """Build a `Fetcher` that streams `url`, capturing the GET response's own ETag/size.

    Raises `_EtagMismatchError` before writing any bytes whenever the GET
    response's ETag differs from `expected_etag` — the GET response is
    authoritative for the cache key and provenance, not the HEAD sweep's.
    This includes the case where `expected_etag` is `None` but the GET
    response carries one: the HEAD sweep's missing ETag never gets a chance
    to become authoritative, so the GET's own ETag re-keys the entry instead.
    Only when neither HEAD nor GET ever carries an ETag does the entry stay
    keyed `unknown`, warning once per year that revalidation is degraded for
    it.

    Raises `_FetcherNetworkError` (a `TossdNetworkError`) instead of a raw
    `requests` exception when the connection fails or the transfer
    truncates, mirroring `_discovery._head_one`'s own conversion.
    """
    captured: dict[str, str | int | None] = {"etag": None, "size_bytes": None}

    def _fetch(ctx: FetchContext) -> None:
        try:
            response = session.get(url, stream=True, timeout=(10.0, 60.0))
        except requests.exceptions.RequestException as exc:
            raise _FetcherNetworkError(
                f"Could not reach {url}: {exc}. The publisher host appears unreachable."
            ) from exc

        with response:
            response.raise_for_status()
            get_etag = response.headers.get("ETag")
            if get_etag is not None and get_etag != expected_etag:
                raise _EtagMismatchError(get_etag)
            if get_etag is None and expected_etag is None:
                _warn_degraded_revalidation(year)
            captured["etag"] = get_etag
            content_length = response.headers.get("Content-Length")
            expected_size = int(content_length) if content_length is not None else None
            captured["size_bytes"] = expected_size

            written = 0
            try:
                with open(ctx.path, "wb") as handle:
                    for chunk in response.iter_content(chunk_size=1 << 20):
                        if chunk:
                            handle.write(chunk)
                            written += len(chunk)
            except requests.exceptions.RequestException as exc:
                raise _FetcherNetworkError(
                    f"Could not download {url}: {exc}. The connection dropped "
                    "partway through the transfer."
                ) from exc

        if expected_size is not None and written != expected_size:
            raise _FetcherNetworkError(
                f"Truncated download from {url}: expected {expected_size} bytes, "
                f"received {written} before the connection ended."
            )

    return _fetch, captured


class _FetchState:
    """Mutable singleton state backing this module's warn-once accessor."""

    def __init__(self) -> None:
        self.warned_degraded_years: set[int] = set()


_state = _FetchState()


def _warn_degraded_revalidation(year: int) -> None:
    """Warn once per year that neither HEAD nor GET ever carried an ETag for it.

    Without an ETag from either request, the cache entry stays keyed
    `unknown` and a republished vintage cannot be detected; only
    `refresh=True` (or an enclosing `refresh_scope()`) forces a fresh
    download.
    """
    if year in _state.warned_degraded_years:
        return
    _state.warned_degraded_years.add(year)
    warnings.warn(
        f"Neither the HEAD nor GET response for {year} carried an ETag, so "
        "this vintage's cache entry cannot be revalidated against a "
        "republish. Pass refresh=True (or wrap the call in "
        "readerkit.refresh_scope()) to force a fresh download.",
        stacklevel=2,
    )


def _validate_new_vintage(path: Path) -> None:
    """Reject a newly downloaded vintage that fails structural validation.

    Checks the `PAR1` parquet magic, that pyarrow can read the footer and
    metadata, and that every string column's data validates fully. Raises on
    any failure; readerkit wraps the raise into `ArtifactCorruptError`, which
    `_download_and_cache` re-raises as `VintageValidationError`.
    """
    with path.open("rb") as handle:
        magic = handle.read(4)
    if magic != b"PAR1":
        raise ValueError(f"{path} does not start with the PAR1 parquet magic bytes.")

    parquet_file = pq.ParquetFile(path)
    table = parquet_file.read()
    for field in table.schema:
        if pa.types.is_string(field.type):
            table.column(field.name).validate(full=True)


def _reset_for_tests() -> None:
    """Clear the degraded-revalidation warn-once state.

    Test-only. `tests/conftest.py`'s autouse fixture resets _discovery's,
    config's, and query's per-module state; this module's own warn-once state
    is reset locally instead, same as _schema.py's own local fixture.
    """
    _state.warned_degraded_years.clear()
