"""HEAD-sweep discovery of published TOSSD vintages (D2).

One HEAD request per year, from 2019 through the current calendar year, swept
once per process and memoised in-process — there is no persisted TTL map.
`fetch.py` owns what happens when the sweep can't run at all (offline) or a
requested year comes back missing; this module only reports what it saw.
"""

from __future__ import annotations

import importlib.resources
import json
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache

import requests
from readerkit import build_session

from tossd_reader.exceptions import TossdNetworkError

_APP_NAME = "tossd-reader"
_URL_TEMPLATE = "https://tossd.online/tossddata_{year}.parquet"
_FIRST_YEAR = 2019


@dataclass(frozen=True)
class VintageInfo:
    """One year's HEAD-sweep result.

    Attributes:
        url: The vintage's download URL.
        etag: The HEAD response's `ETag`, when the server sent one. Only an
            optimisation for forming the candidate cache key — `fetch.py`
            treats the GET response's own ETag as authoritative (Fable
            condition 2).
        last_modified: The HEAD response's `Last-Modified`, when sent.
        size_bytes: The HEAD response's `Content-Length`, when sent.
    """

    url: str
    etag: str | None = None
    last_modified: str | None = None
    size_bytes: int | None = None


class _DiscoveryState:
    """Mutable singleton state backing this module's sweep/session accessors.

    A plain class instead of module globals so `get_session`/`discover` can
    mutate it by attribute assignment rather than a `global` statement.
    """

    def __init__(self) -> None:
        self.session: requests.Session | None = None
        self.memo: dict[int, VintageInfo] | None = None
        self.warned_years: set[int] = set()


_state = _DiscoveryState()


@cache
def known_years() -> tuple[int, ...]:
    """Return the packaged known-years set (`_data/known_years.json`)."""
    resource = importlib.resources.files("tossd_reader") / "_data" / "known_years.json"
    with importlib.resources.as_file(resource) as path:
        years = json.loads(path.read_text())
    return tuple(sorted(years))


def get_session() -> requests.Session:
    """Return the module-level readerkit HTTP session, building it on first use.

    Built with no HTTP disk cache: this module's own in-process memo already
    dedupes the HEAD sweep, and a payload GET bypasses the HTTP cache
    regardless (see `readerkit.bulk_fetcher`'s docstring), so there is nothing
    worth caching at the transport layer here.
    """
    if _state.session is None:
        _state.session = build_session(app=_APP_NAME, cache_dir=None)
    return _state.session


def discover(*, refresh: bool = False) -> dict[int, VintageInfo]:
    """Sweep every year from 2019 to the current calendar year, one HEAD each.

    Memoised in-process for the life of the session.

    Args:
        refresh: Invalidate the memo and re-sweep.

    Returns:
        Mapping of year to `VintageInfo`, for years that responded 200. A year
        that 404s is simply absent from the mapping.

    Raises:
        TossdNetworkError: The publisher host could not be reached at all.
    """
    if _state.memo is not None and not refresh:
        return _state.memo

    session = get_session()
    current_year = datetime.now(UTC).year
    results: dict[int, VintageInfo] = {}
    for year in range(_FIRST_YEAR, current_year + 1):
        info = _head_one(session, year)
        if info is not None:
            results[year] = info

    _warn_unknown_years(results)
    _state.memo = results
    return results


def _head_one(session: requests.Session, year: int) -> VintageInfo | None:
    """HEAD one year's vintage URL.

    Returns:
        `VintageInfo` on a 200 response, `None` on a 404.

    Raises:
        TossdNetworkError: The request could not complete at the transport
            level (the publisher host appears unreachable).
    """
    url = _URL_TEMPLATE.format(year=year)
    try:
        response = session.head(url, allow_redirects=True)
    except requests.exceptions.RequestException as exc:
        raise TossdNetworkError(
            f"Could not reach {url}: {exc}. The publisher host appears unreachable."
        ) from exc
    if response.status_code == 404:
        return None
    response.raise_for_status()
    content_length = response.headers.get("Content-Length")
    return VintageInfo(
        url=url,
        etag=response.headers.get("ETag"),
        last_modified=response.headers.get("Last-Modified"),
        size_bytes=int(content_length) if content_length is not None else None,
    )


def _warn_unknown_years(results: dict[int, VintageInfo]) -> None:
    """Warn once per never-before-seen year the sweep finds beyond `known_years()`.

    An unknown new year does not join the defaults; it is only honoured when
    passed explicitly to `fetch_year`/`get_tossd_raw`.
    """
    known = set(known_years())
    for year in sorted(results):
        if year in known or year in _state.warned_years:
            continue
        _state.warned_years.add(year)
        warnings.warn(
            f"The publisher now lists {year}, which is not yet in this "
            f"package's known-years set. Pass years={year} explicitly to "
            "fetch it.",
            # 3 frames up from here: _warn_unknown_years -> discover -> the
            # caller. Verified in test_discovery.py against the real call
            # chain, not just counted by eye.
            stacklevel=3,
        )


def _reset_for_tests() -> None:
    """Clear the in-process sweep memo and warn-once state.

    Test-only. `conftest.py` does not (yet) reset per-module state between
    tests, so tests that exercise `discover()`'s memoisation or warn-once
    behaviour call this themselves via a local fixture.
    """
    _state.memo = None
    _state.warned_years.clear()
