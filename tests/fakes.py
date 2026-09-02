"""Shared fetch/discovery patching helpers for tests that stand up fixture years.

`test_fetch.py`, `test_query.py`, and `test_export.py` each need to make
`_discovery` report a fixed set of published vintages and make `fetch`'s own
GET fetcher serve fixture bytes for them, without touching the network.

These are plain functions taking `monkeypatch` explicitly, rather than pytest
fixtures — a test opts in by importing and calling one, the same way it uses
`tests/script_loading.py`'s `import_script`.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
import requests

from tossd_reader import _discovery, fetch
from tossd_reader._discovery import VintageInfo


def url_for(year: int) -> str:
    return f"https://tossd.online/tossddata_{year}.parquet"


def patch_discovery(
    monkeypatch: pytest.MonkeyPatch, vintages: dict[int, VintageInfo]
) -> None:
    """Patch `_discovery._head_one` so the sweep sees exactly `vintages`."""

    def _head_one(_session: requests.Session, year: int) -> VintageInfo | None:
        return vintages.get(year)

    monkeypatch.setattr(_discovery, "_head_one", _head_one)


def patch_fetcher_by_url(
    monkeypatch: pytest.MonkeyPatch, sources: dict[str, tuple[bytes, str | None]]
) -> None:
    """Patch `fetch._make_fetcher` to serve `sources[url]` bytes under its own ETag.

    `sources` is read fresh on every call, so a test can mutate it between two
    `fetch_year` calls to simulate an upstream republish. The fake reproduces
    `_make_fetcher`'s own ETag cross-check (including when `expected_etag` is
    `None` but the source has its own ETag), so the `_EtagMismatchError` retry
    path is exercised the same way it would be against a real GET response.
    """

    def _factory(
        url: str,
        _session: requests.Session,
        *,
        year: int,
        expected_etag: str | None,
    ) -> tuple[Callable[[object], None], dict[str, str | None]]:
        captured: dict[str, str | None] = {"etag": None}

        def _fetch(ctx: object) -> None:
            payload, true_etag = sources[url]
            if true_etag is not None and true_etag != expected_etag:
                raise fetch._EtagMismatchError(true_etag)
            captured["etag"] = true_etag
            ctx.path.write_bytes(payload)  # type: ignore[attr-defined]

        return _fetch, captured

    monkeypatch.setattr(fetch, "_make_fetcher", _factory)
