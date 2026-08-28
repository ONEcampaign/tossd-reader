"""Fetch and cache raw TOSSD parquet vintages (D2 offline rules, D3, D4, D10).

`fetch_year` returns a path to one year's cached, publisher-bytes-verbatim
parquet file. `get_tossd_raw` is the public entry point that fetches one or
more years and concatenates them, still as published (no renaming, no dtype
work — that's the schema layer, slice 1.2).
"""

from __future__ import annotations

import hashlib
import json
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

from tossd_reader import __version__, config, discovery
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
    """
    resolved_years = _normalise_years(years)
    tables = [
        pq.read_table(fetch_year(year, refresh=refresh)) for year in resolved_years
    ]
    combined = pa.concat_tables(tables)
    return combined.to_pandas()


def _normalise_years(years: int | Iterable[int] | None) -> tuple[int, ...]:
    """Normalise `years` (scalar / iterable / range) to a sorted tuple immediately."""
    if years is None:
        return discovery.known_years()
    if isinstance(years, int):
        return (years,)
    return tuple(sorted({int(year) for year in years}))


def fetch_year(year: int, *, refresh: bool = False) -> Path:
    """Return the path to the cached raw parquet for `year`, publisher bytes verbatim.

    Applies D2's offline rules: a network outage or a since-unpublished year
    is served from the newest local vintage with a loud warning when one is
    cached, and raises `TossdNetworkError` when nothing usable exists locally.

    Args:
        year: The reporting year to fetch. Need not be in `known_years()`;
            an explicitly requested year is honoured when discovery finds it.
        refresh: Re-run discovery's HEAD sweep and force a readerkit
            conditional GET. An enclosing `readerkit.refresh_scope()` has the
            same effect even when this stays `False`.

    Returns:
        Path to the cached parquet payload.

    Raises:
        TossdNetworkError: The publisher is unreachable and nothing is
            cached for `year`; or `year` is not currently published (and
            `refresh` was requested, or nothing is cached for it either).
        VintageValidationError: A newly downloaded vintage failed D10
            validation.
        ValueError: `year` is not currently published by the source and
            nothing is cached for it.
    """
    effective = effective_refresh(f"tossd_reader:fetch_year:{year}", explicit=refresh)

    try:
        vintages = discovery.discover(refresh=effective)
    except TossdNetworkError:
        return _serve_offline(year, reason="the network is unreachable")

    info = vintages.get(year)
    if info is None:
        return _serve_missing(
            year, refresh=effective, available=tuple(sorted(vintages))
        )

    return _download_and_cache(year, info, refresh=effective)


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
    provenance = _read_provenance(newest.path) or {}
    etag = _as_str(provenance.get("etag"))
    retrieved_at_raw = _as_str(provenance.get("retrieved_at"))
    retrieved_at = (
        datetime.fromisoformat(retrieved_at_raw)
        if retrieved_at_raw is not None
        else None
    )
    return _CachedVintage(path=newest.path, etag=etag, retrieved_at=retrieved_at)


def _as_str(value: object) -> str | None:
    """Narrow a provenance-JSON field to `str`, or `None` if it isn't one."""
    return value if isinstance(value, str) else None


def _serve_offline(year: int, *, reason: str) -> Path:
    """D2 rules (a)/(b): network is unreachable for this whole sweep."""
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
    """D2 rules (c)/(d): the sweep ran, but `year` was not among its results."""
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
    """Emit D2's one loud warning naming the vintage date being served instead."""
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
        stacklevel=3,
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


def _download_and_cache(
    year: int, info: discovery.VintageInfo, *, refresh: bool
) -> Path:
    """Download (or reuse) the cached artifact for `year`, honouring Fable condition 2.

    The HEAD-derived `info.etag` only forms the *candidate* cache key. If the
    GET response's own ETag differs, the download is retried once under the
    corrected, authoritative key.
    """
    cache = config.get_cache()
    session = discovery.get_session()
    etag = info.etag

    for _attempt in range(2):
        key = f"{_KEY_PREFIX}{year}_{etag or 'unknown'}"
        fetcher, captured = _make_fetcher(info.url, session, expected_etag=etag)
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
            continue
        except ArtifactCorruptError as exc:
            raise VintageValidationError(
                f"The downloaded {year} vintage failed validation: {exc.reason}",
                year=year,
                url=info.url,
            ) from exc

        _write_provenance_if_absent(path, url=info.url, captured=captured)
        return path

    raise AssertionError("unreachable: ETag mismatch retried more than once")


def _make_fetcher(
    url: str, session: requests.Session, *, expected_etag: str | None
) -> tuple[Fetcher, dict[str, str | int | None]]:
    """Build a `Fetcher` that streams `url`, capturing the GET response's own ETag/size.

    Raises `_EtagMismatchError` before writing any bytes if the GET response's
    ETag differs from `expected_etag` — per Fable condition 2, the GET
    response is authoritative for the cache key and provenance, not the HEAD
    sweep's.
    """
    captured: dict[str, str | int | None] = {"etag": None, "size_bytes": None}

    def _fetch(ctx: FetchContext) -> None:
        with session.get(url, stream=True, timeout=(10.0, 60.0)) as response:
            response.raise_for_status()
            get_etag = response.headers.get("ETag")
            if (
                expected_etag is not None
                and get_etag is not None
                and get_etag != expected_etag
            ):
                raise _EtagMismatchError(get_etag)
            captured["etag"] = get_etag
            content_length = response.headers.get("Content-Length")
            captured["size_bytes"] = (
                int(content_length) if content_length is not None else None
            )
            with open(ctx.path, "wb") as handle:
                for chunk in response.iter_content(chunk_size=1 << 20):
                    if chunk:
                        handle.write(chunk)

    return _fetch, captured


def _validate_new_vintage(path: Path) -> None:
    """D10: reject a newly downloaded vintage that fails structural validation.

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


def _write_provenance_if_absent(
    path: Path, *, url: str, captured: dict[str, str | int | None]
) -> None:
    """Write `<path stem>.provenance.json` beside `path`, unless one already exists (D4)."""
    provenance_path = path.with_suffix(".provenance.json")
    if provenance_path.exists():
        return
    parquet_file = pq.ParquetFile(path)
    record = {
        "url": url,
        "etag": captured.get("etag"),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "row_count": parquet_file.metadata.num_rows,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "tossd_reader_version": __version__,
    }
    provenance_path.write_text(json.dumps(record, indent=2))


def _read_provenance(path: Path) -> dict[str, object] | None:
    """Read `<path stem>.provenance.json`, or `None` if it doesn't exist."""
    provenance_path = path.with_suffix(".provenance.json")
    if not provenance_path.is_file():
        return None
    return json.loads(provenance_path.read_text())


def _sha256(path: Path) -> str:
    """Hash `path`'s full contents."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
