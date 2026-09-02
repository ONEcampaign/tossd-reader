"""Unit tests for fetch.py: caching, offline fallback rules, provenance, structural validation."""

from __future__ import annotations

import hashlib
import importlib.resources
import json
from collections.abc import Callable, Iterable, Iterator
from datetime import datetime
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest
import requests
from readerkit import FetchContext, refresh_scope

import tossd_reader
from tests.factories import write_tossd_fixture
from tests.fakes import patch_discovery, patch_fetcher_by_url, url_for
from tossd_reader import _discovery, config, fetch
from tossd_reader._discovery import VintageInfo
from tossd_reader.exceptions import TossdNetworkError, VintageValidationError


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    """Reset fetch's own warn-once state before each test.

    `tests/conftest.py` resets _discovery's and config's per-module state; the
    degraded-revalidation warn-once state added to this module is reset here
    instead, same as _schema.py's own local fixture.
    """
    fetch._reset_for_tests()


def _read_schema() -> pd.DataFrame:
    schema_resource = importlib.resources.files("tossd_reader") / "_data" / "schema.csv"
    with importlib.resources.as_file(schema_resource) as schema_path:
        return pd.read_csv(schema_path, dtype=str, keep_default_na=False)


# --- Happy path -------------------------------------------------------------


def test_get_tossd_raw_years_none_uses_known_years_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`years=None` fetches the packaged known-years set, not just one year."""
    published: dict[int, VintageInfo] = {}
    sources: dict[str, tuple[bytes, str | None]] = {}
    for year in _discovery.known_years():
        url = url_for(year)
        fixture = write_tossd_fixture(
            tmp_path / f"fixture_{year}.parquet", year, n_rows=2
        )
        published[year] = VintageInfo(url=url, etag=f'"e{year}"')
        sources[url] = (fixture.read_bytes(), f'"e{year}"')
    patch_discovery(monkeypatch, published)
    patch_fetcher_by_url(monkeypatch, sources)

    df = fetch.get_tossd_raw()

    assert len(df) == 2 * len(_discovery.known_years())


def test_get_tossd_raw_single_year_roundtrip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A single-year fetch caches, then round-trips through `get_tossd_raw`."""
    year = 2019
    url = url_for(year)
    fixture = write_tossd_fixture(tmp_path / "fixture.parquet", year, n_rows=15)
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"e19"')})
    patch_fetcher_by_url(monkeypatch, {url: (fixture.read_bytes(), '"e19"')})

    df = fetch.get_tossd_raw(years=year)

    schema_df = _read_schema()
    assert list(df.columns) == list(schema_df["published_name"])
    assert len(df) == 15


def test_get_tossd_raw_multi_year_concatenates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Multiple years concatenate into one frame, column order still as published."""
    years = (2019, 2020)
    published: dict[int, VintageInfo] = {}
    sources: dict[str, tuple[bytes, str | None]] = {}
    row_counts = {2019: 5, 2020: 8}
    for year in years:
        url = url_for(year)
        fixture = write_tossd_fixture(
            tmp_path / f"fixture_{year}.parquet", year, n_rows=row_counts[year]
        )
        published[year] = VintageInfo(url=url, etag=f'"e{year}"')
        sources[url] = (fixture.read_bytes(), f'"e{year}"')
    patch_discovery(monkeypatch, published)
    patch_fetcher_by_url(monkeypatch, sources)

    df = fetch.get_tossd_raw(years=years)

    schema_df = _read_schema()
    assert list(df.columns) == list(schema_df["published_name"])
    assert len(df) == sum(row_counts.values())


# --- GET response's ETag re-keys the cache entry on a HEAD/GET mismatch ------


def test_etag_rekey_on_head_get_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The GET response's ETag is authoritative; a HEAD/GET mismatch re-keys the entry."""
    year = 2021
    url = url_for(year)
    fixture = write_tossd_fixture(tmp_path / "fixture.parquet", year, n_rows=5)
    head_etag, get_etag = '"head-etag"', '"get-etag"'
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag=head_etag)})
    patch_fetcher_by_url(monkeypatch, {url: (fixture.read_bytes(), get_etag)})

    path = fetch.fetch_year(year)

    cache = config.get_cache()
    entries = [
        entry for entry in cache.entries() if entry.key.startswith(f"tossd_{year}_")
    ]
    assert len(entries) == 1
    assert entries[0].key == f"tossd_{year}_{get_etag}"
    assert entries[0].path == path


# --- `_make_fetcher` itself (not the higher-level fake used elsewhere) --------


class _FakeGetResponse:
    """A minimal stand-in for a `requests.Response` from a streaming GET."""

    def __init__(self, *, headers: dict[str, str], chunks: tuple[bytes, ...]) -> None:
        self.headers = headers
        self._chunks = chunks

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int) -> tuple[bytes, ...]:
        return self._chunks

    def __enter__(self) -> _FakeGetResponse:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


class _FakeGetSession:
    """A minimal stand-in for a `requests.Session`, returning one canned response."""

    def __init__(self, response: _FakeGetResponse) -> None:
        self._response = response

    def get(self, _url: str, **_kwargs: object) -> _FakeGetResponse:
        return self._response


class _ScriptedResponse:
    """A `_FakeGetResponse` that can drop mid-stream after yielding some chunks."""

    def __init__(
        self,
        *,
        headers: dict[str, str],
        chunks: tuple[bytes, ...] = (),
        drop_mid_stream: bool = False,
    ) -> None:
        self.headers = headers
        self._chunks = chunks
        self._drop_mid_stream = drop_mid_stream

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int) -> Iterator[bytes]:
        yield from self._chunks
        if self._drop_mid_stream:
            raise requests.exceptions.ChunkedEncodingError("simulated mid-stream drop")

    def __enter__(self) -> _ScriptedResponse:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


class _ScriptedSession:
    """A fake `requests.Session` that returns one canned response per `get()` call, in order."""

    def __init__(self, responses: Iterable[_ScriptedResponse]) -> None:
        self._responses = list(responses)

    def get(self, _url: str, **_kwargs: object) -> _ScriptedResponse:
        return self._responses.pop(0)


def test_make_fetcher_streams_body_and_captures_get_headers(tmp_path: Path) -> None:
    """The real `_make_fetcher` writes the body and captures the GET's own ETag."""
    payload = b"PAR1-fake-body-bytes"
    response = _FakeGetResponse(
        headers={"ETag": '"e1"', "Content-Length": str(len(payload))},
        chunks=(payload,),
    )
    session = _FakeGetSession(response)

    fetcher, captured = fetch._make_fetcher(
        "https://tossd.online/tossddata_2019.parquet",
        session,
        year=2019,
        expected_etag='"e1"',
    )
    dest = tmp_path / "out.parquet"
    fetcher(FetchContext(key="k", path=dest, refresh=False))

    assert dest.read_bytes() == payload
    assert captured["etag"] == '"e1"'


def test_make_fetcher_raises_etag_mismatch_before_writing_bytes(tmp_path: Path) -> None:
    """A GET ETag that differs from the candidate raises before any bytes are written."""
    response = _FakeGetResponse(headers={"ETag": '"actual"'}, chunks=(b"body",))
    session = _FakeGetSession(response)

    fetcher, _captured = fetch._make_fetcher(
        "https://tossd.online/tossddata_2019.parquet",
        session,
        year=2019,
        expected_etag='"expected"',
    )
    dest = tmp_path / "out.parquet"

    with pytest.raises(fetch._EtagMismatchError) as excinfo:
        fetcher(FetchContext(key="k", path=dest, refresh=False))

    assert excinfo.value.get_etag == '"actual"'
    assert not dest.exists()


def test_make_fetcher_rekeys_when_head_had_no_etag_but_get_does(tmp_path: Path) -> None:
    """A HEAD sweep with no ETag still lets the GET's own ETag win."""
    response = _FakeGetResponse(headers={"ETag": '"get-only-etag"'}, chunks=(b"body",))
    session = _FakeGetSession(response)

    fetcher, _captured = fetch._make_fetcher(
        "https://tossd.online/tossddata_2019.parquet",
        session,
        year=2019,
        expected_etag=None,
    )
    dest = tmp_path / "out.parquet"

    with pytest.raises(fetch._EtagMismatchError) as excinfo:
        fetcher(FetchContext(key="k", path=dest, refresh=False))

    assert excinfo.value.get_etag == '"get-only-etag"'
    assert not dest.exists()


def test_fetch_year_rekeys_under_get_etag_when_head_reported_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The entry is keyed under the GET's ETag, not left `unknown`."""
    year = 2022
    url = url_for(year)
    fixture = write_tossd_fixture(tmp_path / "fixture.parquet", year, n_rows=4)
    get_etag = '"only-the-get-has-this"'
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag=None)})
    patch_fetcher_by_url(monkeypatch, {url: (fixture.read_bytes(), get_etag)})

    path = fetch.fetch_year(year)

    cache = config.get_cache()
    entries = [
        entry for entry in cache.entries() if entry.key.startswith(f"tossd_{year}_")
    ]
    assert len(entries) == 1
    assert entries[0].key == f"tossd_{year}_{get_etag}"
    assert entries[0].path == path


def test_fetch_year_keeps_unknown_key_and_warns_once_with_no_etag_anywhere(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Neither HEAD nor GET has an ETag -> stays `unknown`, warns once."""
    year = 2023
    url = url_for(year)
    fixture = write_tossd_fixture(tmp_path / "fixture.parquet", year, n_rows=4)
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag=None)})
    session = _FakeGetSession(
        _FakeGetResponse(headers={}, chunks=(fixture.read_bytes(),))
    )
    monkeypatch.setattr(_discovery, "get_session", lambda: session)

    with pytest.warns(UserWarning, match=str(year)):
        path = fetch.fetch_year(year)

    cache = config.get_cache()
    entries = [
        entry for entry in cache.entries() if entry.key.startswith(f"tossd_{year}_")
    ]
    assert len(entries) == 1
    assert entries[0].key == f"tossd_{year}_unknown"
    assert entries[0].path == path

    # Forced re-fetch of the same year, same process: no repeat warning. With
    # `filterwarnings = ["error"]` set globally, an unexpected warning here
    # would itself raise and fail the test.
    fetch.fetch_year(year, refresh=True)


# --- downloaded-file validation (bad magic / truncated file) ------------------


def test_d10_validator_rejects_bad_magic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bytes not starting with the PAR1 magic fail validation loudly, naming the year/url."""
    year = 2022
    url = url_for(year)
    corrupt = b"NOTP" + b"\x00" * 128
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"e"')})
    patch_fetcher_by_url(monkeypatch, {url: (corrupt, '"e"')})

    with pytest.raises(VintageValidationError, match=str(year)) as excinfo:
        fetch.fetch_year(year)
    assert excinfo.value.year == year
    assert excinfo.value.url == url

    cache = config.get_cache()
    assert not any(entry.key.startswith(f"tossd_{year}_") for entry in cache.entries())


def test_d10_validator_rejects_truncated_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A truncated (footer-less) download fails validation loudly."""
    year = 2023
    url = url_for(year)
    fixture = write_tossd_fixture(tmp_path / "fixture.parquet", year, n_rows=20)
    truncated = fixture.read_bytes()[: fixture.stat().st_size // 2]
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"e"')})
    patch_fetcher_by_url(monkeypatch, {url: (truncated, '"e"')})

    with pytest.raises(VintageValidationError, match=str(year)):
        fetch.fetch_year(year)


# --- provenance sidecar --------------------------------------------------------


def test_provenance_sidecar_written_and_write_if_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The provenance sidecar carries the right fields and is written only once."""
    year = 2024
    url = url_for(year)
    fixture = write_tossd_fixture(tmp_path / "fixture.parquet", year, n_rows=10)
    etag = '"prov-etag"'
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag=etag)})
    patch_fetcher_by_url(monkeypatch, {url: (fixture.read_bytes(), etag)})

    path = fetch.fetch_year(year)
    provenance_path = path.with_suffix(".provenance.json")
    assert provenance_path.exists()
    assert not list(path.parent.glob("*.provenance.json.tmp-*")), (
        "atomic-write temp file left behind"
    )

    record = json.loads(provenance_path.read_text())
    assert record["url"] == url
    assert record["etag"] == etag
    assert record["size_bytes"] == path.stat().st_size
    assert record["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert record["row_count"] == 10
    assert record["tossd_reader_version"] == tossd_reader.__version__
    datetime.fromisoformat(record["retrieved_at"])  # must not raise

    # write-if-absent: a cache hit on the second call must not touch it.
    provenance_path.write_text(json.dumps({"sentinel": True}))
    fetch.fetch_year(year)
    assert json.loads(provenance_path.read_text()) == {"sentinel": True}


def test_provenance_rewritten_after_sidecar_loss_falls_back_to_key_etag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A cache hit with a lost sidecar still records the key's own ETag, not null."""
    year = 2021
    url = url_for(year)
    fixture = write_tossd_fixture(tmp_path / "fixture.parquet", year, n_rows=6)
    etag = '"stable-etag"'
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag=etag)})
    patch_fetcher_by_url(monkeypatch, {url: (fixture.read_bytes(), etag)})

    path = fetch.fetch_year(year)
    path.with_suffix(".provenance.json").unlink()

    fetch.fetch_year(year)  # a cache hit: the fetcher must not run again

    record = json.loads(path.with_suffix(".provenance.json").read_text())
    assert record["etag"] == etag


# --- offline fallback rules -----------------------------------------------------


def test_offline_rule_a_network_down_serves_cached_with_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Network down + year cached -> serve the newest local vintage, one warning."""
    year = 2019
    url = url_for(year)
    fixture = write_tossd_fixture(tmp_path / "fixture.parquet", year, n_rows=5)
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"e"')})
    patch_fetcher_by_url(monkeypatch, {url: (fixture.read_bytes(), '"e"')})
    cached_path = fetch.fetch_year(year)

    _discovery._reset_for_tests()

    def _offline_head_one(_session: requests.Session, _year: int) -> VintageInfo | None:
        raise TossdNetworkError("simulated outage")

    monkeypatch.setattr(_discovery, "_head_one", _offline_head_one)

    with pytest.warns(UserWarning, match=str(year)):
        served_path = fetch.fetch_year(year)

    assert served_path == cached_path


def test_offline_rule_a_falls_back_to_mtime_without_a_provenance_sidecar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With no provenance sidecar, the stale-serve warning falls back to file mtime."""
    year = 2019
    url = url_for(year)
    fixture = write_tossd_fixture(tmp_path / "fixture.parquet", year, n_rows=5)
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"e"')})
    patch_fetcher_by_url(monkeypatch, {url: (fixture.read_bytes(), '"e"')})
    cached_path = fetch.fetch_year(year)
    cached_path.with_suffix(".provenance.json").unlink()

    _discovery._reset_for_tests()

    def _offline_head_one(_session: requests.Session, _year: int) -> VintageInfo | None:
        raise TossdNetworkError("simulated outage")

    monkeypatch.setattr(_discovery, "_head_one", _offline_head_one)

    with pytest.warns(UserWarning, match=str(year)):
        served_path = fetch.fetch_year(year)

    assert served_path == cached_path


@pytest.mark.parametrize(
    ("corrupt_content", "warns_corrupt"),
    [
        (b'{"url": "trunc', True),
        (b'"not-a-json-object"', True),
        (b"\x80\x81\x82", True),
        (b'{"retrieved_at": "not-a-date"}', False),
    ],
    ids=["truncated-json", "non-object-json", "non-utf8", "garbage-date"],
)
def test_offline_rule_a_tolerates_corrupt_provenance_sidecar(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    corrupt_content: bytes,
    warns_corrupt: bool,
) -> None:
    """A corrupt or unparseable-date sidecar degrades to the mtime-based
    stale-serve warning, and the offline fallback keeps serving the cached
    vintage.

    An unparseable sidecar (truncated, non-object, or non-UTF-8) also warns
    about the corrupt sidecar; a sidecar that parses but holds a bad date
    degrades silently.
    """
    year = 2019
    url = url_for(year)
    fixture = write_tossd_fixture(tmp_path / "fixture.parquet", year, n_rows=5)
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"e"')})
    patch_fetcher_by_url(monkeypatch, {url: (fixture.read_bytes(), '"e"')})
    cached_path = fetch.fetch_year(year)
    cached_path.with_suffix(".provenance.json").write_bytes(corrupt_content)

    _discovery._reset_for_tests()

    def _offline_head_one(_session: requests.Session, _year: int) -> VintageInfo | None:
        raise TossdNetworkError("simulated outage")

    monkeypatch.setattr(_discovery, "_head_one", _offline_head_one)

    # The corrupt cases emit two warnings, one per concern. A
    # `pytest.warns(match=...)` re-emits whichever one it did not match,
    # which filterwarnings=["error"] then escalates; capture everything and
    # assert on each warning directly.
    with pytest.warns(UserWarning) as record:
        served_path = fetch.fetch_year(year)

    messages = [str(warning.message) for warning in record]
    assert served_path == cached_path
    assert any(str(year) in message for message in messages)
    assert (
        any("corrupt provenance sidecar" in message for message in messages)
        == warns_corrupt
    )


def test_offline_rule_b_network_down_nothing_cached_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Network down + nothing cached -> raise, never an empty frame."""

    def _offline_head_one(_session: requests.Session, _year: int) -> VintageInfo | None:
        raise TossdNetworkError("simulated outage")

    monkeypatch.setattr(_discovery, "_head_one", _offline_head_one)

    with pytest.raises(TossdNetworkError, match="2019") as excinfo:
        fetch.fetch_year(2019)
    assert excinfo.value.cache_dir == config.get_cache_dir()


def test_offline_rule_c_known_year_unpublished_serves_cached_then_refresh_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A known cached year 404s; refresh=True on it raises instead."""
    year = 2020
    url = url_for(year)
    fixture = write_tossd_fixture(tmp_path / "fixture.parquet", year, n_rows=5)
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"e"')})
    patch_fetcher_by_url(monkeypatch, {url: (fixture.read_bytes(), '"e"')})
    cached_path = fetch.fetch_year(year)

    _discovery._reset_for_tests()
    patch_discovery(monkeypatch, {})  # the sweep now succeeds, but 2020 404s

    with pytest.warns(UserWarning, match=str(year)):
        served_path = fetch.fetch_year(year)
    assert served_path == cached_path

    _discovery._reset_for_tests()
    patch_discovery(monkeypatch, {})
    with pytest.raises(TossdNetworkError, match=str(year)):
        fetch.fetch_year(year, refresh=True)


def test_offline_rule_d_unknown_year_honoured_when_discovered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A year outside `known_years()` is honoured once discovery finds it."""
    year = 2025
    assert year not in _discovery.known_years()
    url = url_for(year)
    fixture = write_tossd_fixture(tmp_path / "fixture.parquet", year, n_rows=3)
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"e"')})
    patch_fetcher_by_url(monkeypatch, {url: (fixture.read_bytes(), '"e"')})

    # Discovering an unknown year also fires the once-per-process discovery
    # warning (tested in isolation in test_discovery.py); expected here too.
    with pytest.warns(UserWarning, match=str(year)):
        path = fetch.fetch_year(year)
    assert path.exists()


def test_offline_rule_d_unknown_year_raises_naming_available_years(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Not discovered and nothing cached -> raise naming available years."""
    patch_discovery(monkeypatch, {2019: VintageInfo(url=url_for(2019), etag='"e"')})

    with pytest.raises(ValueError, match="2025"):
        fetch.fetch_year(2025)


# --- a GET that fails mid-stream routes into the offline fallback -------------


def test_get_mid_stream_drop_serves_cached_vintage_with_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A connection drop partway through a GET falls back to the cached vintage."""
    year = 2019
    url = url_for(year)
    fixture = write_tossd_fixture(tmp_path / "fixture.parquet", year, n_rows=5)
    # Drives the real `_make_fetcher` (not the higher-level `patch_fetcher_by_url`
    # fake), so the mid-stream drop below exercises the actual code under test:
    # one successful response for the initial download, then a dropped one.
    session = _ScriptedSession(
        [
            _ScriptedResponse(headers={"ETag": '"e1"'}, chunks=(fixture.read_bytes(),)),
            _ScriptedResponse(
                headers={"ETag": '"e2"'}, chunks=(b"partial",), drop_mid_stream=True
            ),
        ]
    )
    monkeypatch.setattr(_discovery, "get_session", lambda: session)
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"e1"')})
    cached_path = fetch.fetch_year(year)

    # Simulate a republish (a new ETag, so a fresh download is attempted this
    # time) whose GET connection then drops mid-transfer.
    _discovery._reset_for_tests()
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"e2"')})

    with pytest.warns(UserWarning, match=str(year)):
        served_path = fetch.fetch_year(year)

    assert served_path == cached_path


def test_get_mid_stream_drop_with_nothing_cached_raises_tossd_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With nothing cached, a mid-stream drop raises TossdNetworkError, not a requests error."""
    year = 2022
    url = url_for(year)
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"e"')})
    session = _ScriptedSession(
        [
            _ScriptedResponse(
                headers={"ETag": '"e"'}, chunks=(b"partial",), drop_mid_stream=True
            )
        ]
    )
    monkeypatch.setattr(_discovery, "get_session", lambda: session)

    with pytest.raises(TossdNetworkError) as excinfo:
        fetch.fetch_year(year)

    assert not isinstance(excinfo.value, requests.exceptions.RequestException)


def test_truncated_content_length_raises_named_error_not_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A body shorter than the declared Content-Length raises, naming expected/actual."""
    year = 2020
    url = url_for(year)
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"e"')})
    session = _FakeGetSession(
        _FakeGetResponse(
            headers={"ETag": '"e"', "Content-Length": "1000"}, chunks=(b"short-body",)
        )
    )
    monkeypatch.setattr(_discovery, "get_session", lambda: session)

    with pytest.raises(TossdNetworkError, match="1000") as excinfo:
        fetch.fetch_year(year)
    assert "10" in str(excinfo.value)

    cache = config.get_cache()
    assert not any(entry.key.startswith(f"tossd_{year}_") for entry in cache.entries())


# --- ETag-retry exhaustion ------------------------------------------------------


def test_etag_thrash_exhausts_retries_raises_tossd_network_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An ETag that keeps changing across every retry raises TossdNetworkError."""
    year = 2020
    url = url_for(year)
    fixture = write_tossd_fixture(tmp_path / "fixture.parquet", year, n_rows=3)
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"head-etag"')})
    call_count = 0

    def _factory(
        _url: str, _session: requests.Session, *, year: int, expected_etag: str | None
    ) -> tuple[Callable[[object], None], dict[str, str | None]]:
        captured: dict[str, str | None] = {"etag": None}

        def _fetch(ctx: object) -> None:
            nonlocal call_count
            call_count += 1
            true_etag = f'"attempt-{call_count}"'  # always different: never settles
            if true_etag != expected_etag:
                raise fetch._EtagMismatchError(true_etag)
            captured["etag"] = true_etag
            ctx.path.write_bytes(fixture.read_bytes())  # type: ignore[attr-defined]

        return _fetch, captured

    monkeypatch.setattr(fetch, "_make_fetcher", _factory)

    with pytest.raises(TossdNetworkError, match=str(year)) as excinfo:
        fetch.fetch_year(year)
    assert url in str(excinfo.value)

    cache = config.get_cache()
    assert not any(entry.key.startswith(f"tossd_{year}_") for entry in cache.entries())


# --- one discovery sweep per get_tossd_raw call, not one per year -------------


def test_get_tossd_raw_refresh_sweeps_discovery_once_for_multiple_years(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """refresh=True across several years re-sweeps discovery once, not once per year."""
    years = (2019, 2020)
    published: dict[int, VintageInfo] = {}
    sources: dict[str, tuple[bytes, str | None]] = {}
    for year in years:
        url = url_for(year)
        fixture = write_tossd_fixture(
            tmp_path / f"fixture_{year}.parquet", year, n_rows=2
        )
        published[year] = VintageInfo(url=url, etag=f'"e{year}"')
        sources[url] = (fixture.read_bytes(), f'"e{year}"')
    patch_discovery(monkeypatch, published)
    patch_fetcher_by_url(monkeypatch, sources)

    discover_calls = 0
    real_discover = _discovery.discover

    def _counting_discover(*, refresh: bool = False) -> dict[int, VintageInfo]:
        nonlocal discover_calls
        discover_calls += 1
        return real_discover(refresh=refresh)

    monkeypatch.setattr(_discovery, "discover", _counting_discover)

    fetch.get_tossd_raw(years=list(years), refresh=True)

    assert discover_calls == 1


# --- warning stacklevel points at the caller, not fetch.py ---------------------


def test_serving_stale_warning_points_at_the_caller(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The stale-serve warning's stacklevel attributes it to fetch_year's caller."""
    year = 2019
    url = url_for(year)
    fixture = write_tossd_fixture(tmp_path / "fixture.parquet", year, n_rows=5)
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"e"')})
    patch_fetcher_by_url(monkeypatch, {url: (fixture.read_bytes(), '"e"')})
    fetch.fetch_year(year)

    _discovery._reset_for_tests()

    def _offline_head_one(_session: requests.Session, _year: int) -> VintageInfo | None:
        raise TossdNetworkError("simulated outage")

    monkeypatch.setattr(_discovery, "_head_one", _offline_head_one)

    with pytest.warns(UserWarning, match=str(year)) as record:
        fetch.fetch_year(year)

    assert record[0].filename.endswith("test_fetch.py")


# --- an empty years iterable ----------------------------------------------------


def test_get_tossd_raw_empty_years_raises_value_error() -> None:
    """`years=[]` raises early with a clear ValueError, not a raw pyarrow error."""
    with pytest.raises(ValueError, match="years is empty"):
        fetch.get_tossd_raw(years=[])


# --- teaching TypeError on an unexpected keyword argument ----------------------


def test_get_tossd_raw_unexpected_kwarg_names_it_and_points_at_get_tossd() -> None:
    """An unrecognised kwarg raises TypeError naming it and pointing at get_tossd()."""
    with pytest.raises(TypeError, match="columns") as excinfo:
        fetch.get_tossd_raw(columns="minimal")  # type: ignore[call-arg]

    assert "get_tossd()" in str(excinfo.value)


def test_get_tossd_raw_multiple_unexpected_kwargs_names_all_of_them() -> None:
    """Several unrecognised kwargs at once are all named, not just the first."""
    with pytest.raises(TypeError) as excinfo:
        fetch.get_tossd_raw(providers=1, units="usd_million")  # type: ignore[call-arg]

    assert "providers" in str(excinfo.value)
    assert "units" in str(excinfo.value)


# --- refresh_scope equivalence -------------------------------------------------


def test_refresh_scope_equivalent_to_refresh_true(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An enclosing `readerkit.refresh_scope()` has the same effect as `refresh=True`."""
    year = 2019
    url = url_for(year)
    fixture_v1 = write_tossd_fixture(tmp_path / "v1.parquet", year, n_rows=5, seed=1)
    fixture_v2 = write_tossd_fixture(tmp_path / "v2.parquet", year, n_rows=9, seed=2)

    sources: dict[str, tuple[bytes, str | None]] = {
        url: (fixture_v1.read_bytes(), '"e1"')
    }
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"e1"')})
    patch_fetcher_by_url(monkeypatch, sources)

    path_v1 = fetch.fetch_year(year)

    # Simulate an upstream republish. Discovery's in-process memo means this
    # alone changes nothing without a refresh.
    sources[url] = (fixture_v2.read_bytes(), '"e2"')
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"e2"')})

    path_again = fetch.fetch_year(year)
    assert path_again == path_v1, "no refresh requested: the memo must still win"

    with refresh_scope():
        path_v2 = fetch.fetch_year(year)

    assert path_v2 != path_v1
    assert pq.ParquetFile(path_v2).metadata.num_rows == 9


# --- get_tossd_raw attrs provenance ---------------------------------------------


def test_get_tossd_raw_attrs_shape_and_json_serializable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`df.attrs["tossd_reader"]` carries package_version/created_at/query/years, all JSON-able."""
    year = 2019
    url = url_for(year)
    fixture = write_tossd_fixture(tmp_path / "fixture.parquet", year, n_rows=5)
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"e19"')})
    patch_fetcher_by_url(monkeypatch, {url: (fixture.read_bytes(), '"e19"')})

    df = fetch.get_tossd_raw(years=year)

    provenance = df.attrs["tossd_reader"]
    assert set(provenance) == {"package_version", "created_at", "query", "years"}
    assert provenance["query"] == {"years": (year,), "refresh": False}
    assert set(provenance["years"]) == {str(year)}
    year_entry = provenance["years"][str(year)]
    assert year_entry["etag"] == '"e19"'
    assert year_entry["url"] == url
    datetime.fromisoformat(year_entry["retrieved_at"])
    json.dumps(provenance)  # never raises: every value is JSON-serializable
    datetime.fromisoformat(provenance["created_at"])


def test_get_tossd_raw_attrs_multi_year(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A multi-year call's `"years"` provenance mapping carries one entry per requested year."""
    years = (2019, 2020)
    published: dict[int, VintageInfo] = {}
    sources: dict[str, tuple[bytes, str | None]] = {}
    for year in years:
        url = url_for(year)
        fixture = write_tossd_fixture(
            tmp_path / f"fixture_{year}.parquet", year, n_rows=3
        )
        published[year] = VintageInfo(url=url, etag=f'"e{year}"')
        sources[url] = (fixture.read_bytes(), f'"e{year}"')
    patch_discovery(monkeypatch, published)
    patch_fetcher_by_url(monkeypatch, sources)

    df = fetch.get_tossd_raw(years=list(years))

    provenance = df.attrs["tossd_reader"]
    assert provenance["query"]["years"] == years
    assert set(provenance["years"]) == {"2019", "2020"}
    for year in years:
        assert provenance["years"][str(year)]["etag"] == f'"e{year}"'


def test_get_tossd_raw_offline_refresh_conflict_raises() -> None:
    """`refresh=True` while offline mode is active raises before touching the network."""
    config.set_offline(True)
    with pytest.raises(ValueError, match="get_tossd_raw"):
        fetch.get_tossd_raw(years=2019, refresh=True)


# --- get_vintages -----------------------------------------------------------------


def test_get_vintages_returns_the_live_sweep_as_a_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A live sweep result becomes one row per year, with `VintageInfo`'s own fields."""
    published = {
        2019: VintageInfo(
            url=url_for(2019), etag='"e19"', last_modified="Mon", size_bytes=100
        ),
        2020: VintageInfo(
            url=url_for(2020), etag='"e20"', last_modified="Tue", size_bytes=200
        ),
    }
    patch_discovery(monkeypatch, published)

    vintages = fetch.get_vintages()

    assert list(vintages.columns) == [
        "year",
        "url",
        "etag",
        "last_modified",
        "size_bytes",
    ]
    assert list(vintages["year"]) == [2019, 2020]
    row_2019 = vintages.loc[vintages["year"] == 2019].iloc[0]
    assert row_2019["url"] == url_for(2019)
    assert row_2019["etag"] == '"e19"'
    assert row_2019["last_modified"] == "Mon"
    assert row_2019["size_bytes"] == 100


def test_get_vintages_omits_years_that_404(monkeypatch: pytest.MonkeyPatch) -> None:
    """A year the sweep didn't see published (404) is simply absent, not a null row."""
    patch_discovery(monkeypatch, {2019: VintageInfo(url=url_for(2019), etag='"e"')})

    vintages = fetch.get_vintages()

    assert list(vintages["year"]) == [2019]


def test_get_vintages_offline_serves_from_cache_with_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Offline mode skips the sweep entirely, listing cached years instead, with one warning."""
    year = 2019
    url = url_for(year)
    fixture = write_tossd_fixture(tmp_path / "fixture.parquet", year, n_rows=4)
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"e19"')})
    patch_fetcher_by_url(monkeypatch, {url: (fixture.read_bytes(), '"e19"')})
    fetch.fetch_year(year)

    config.set_offline(True)

    with pytest.warns(UserWarning, match="offline"):
        vintages = fetch.get_vintages()

    assert list(vintages["year"]) == [year]
    row = vintages.iloc[0]
    assert row["url"] == url
    assert row["etag"] == '"e19"'
    assert row["last_modified"] is None


def test_get_vintages_offline_raises_when_nothing_cached() -> None:
    """Offline mode with an empty cache raises `TossdNetworkError`, no warning."""
    config.set_offline(True)
    with pytest.raises(TossdNetworkError, match="offline"):
        fetch.get_vintages()


def test_get_vintages_network_down_falls_back_to_cache_with_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A genuine (non-offline) sweep failure falls back to the cache too, warning why."""
    year = 2019
    url = url_for(year)
    fixture = write_tossd_fixture(tmp_path / "fixture.parquet", year, n_rows=4)
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"e19"')})
    patch_fetcher_by_url(monkeypatch, {url: (fixture.read_bytes(), '"e19"')})
    fetch.fetch_year(year)

    _discovery._reset_for_tests()

    def _offline_head_one(_session: requests.Session, _year: int) -> VintageInfo | None:
        raise TossdNetworkError("simulated outage")

    monkeypatch.setattr(_discovery, "_head_one", _offline_head_one)

    with pytest.warns(UserWarning, match="network is unreachable"):
        vintages = fetch.get_vintages()

    assert list(vintages["year"]) == [year]


def test_get_vintages_network_down_nothing_cached_raises() -> None:
    """A genuine sweep failure with nothing cached still raises `TossdNetworkError`."""

    def _offline_head_one(_session: requests.Session, _year: int) -> VintageInfo | None:
        raise TossdNetworkError("simulated outage")

    fetch._discovery._head_one = _offline_head_one
    with pytest.raises(TossdNetworkError, match="network is unreachable"):
        fetch.get_vintages()


def test_get_vintages_offline_ignores_a_foreign_cache_entry_and_keeps_the_newest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A foreign cache entry is skipped, and a republished year lists its newest vintage only."""
    year = 2019
    url = url_for(year)
    fixture_v1 = write_tossd_fixture(tmp_path / "v1.parquet", year, n_rows=2, seed=1)
    fixture_v2 = write_tossd_fixture(tmp_path / "v2.parquet", year, n_rows=3, seed=2)
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"e1"')})
    patch_fetcher_by_url(monkeypatch, {url: (fixture_v1.read_bytes(), '"e1"')})
    fetch.fetch_year(year)
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"e2"')})
    patch_fetcher_by_url(monkeypatch, {url: (fixture_v2.read_bytes(), '"e2"')})
    fetch.fetch_year(year, refresh=True)

    cache = config.get_cache()
    cache.ensure("not-a-tossd-key", fetcher=lambda ctx: ctx.path.write_bytes(b"x"))

    config.set_offline(True)
    with pytest.warns(UserWarning):
        vintages = fetch.get_vintages()

    assert list(vintages["year"]) == [year]
    assert vintages.iloc[0]["etag"] == '"e2"'


def test_get_vintages_offline_keeps_the_newest_regardless_of_cache_scan_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The newest vintage wins even when the cache lists an older entry after it."""
    year = 2019
    url = url_for(year)
    fixture_v1 = write_tossd_fixture(tmp_path / "v1.parquet", year, n_rows=2, seed=1)
    fixture_v2 = write_tossd_fixture(tmp_path / "v2.parquet", year, n_rows=3, seed=2)
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"e1"')})
    patch_fetcher_by_url(monkeypatch, {url: (fixture_v1.read_bytes(), '"e1"')})
    fetch.fetch_year(year)
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"e2"')})
    patch_fetcher_by_url(monkeypatch, {url: (fixture_v2.read_bytes(), '"e2"')})
    fetch.fetch_year(year, refresh=True)

    real_entries = config.get_cache().entries()
    newest = max(real_entries, key=lambda entry: entry.downloaded_at)
    reversed_order = sorted(
        real_entries, key=lambda entry: entry.downloaded_at, reverse=True
    )
    assert reversed_order[0] == newest  # newest scanned first, older scanned after

    class _ReversedScanCache:
        def entries(self) -> list:
            return reversed_order

    monkeypatch.setattr(config, "get_cache", _ReversedScanCache)
    config.set_offline(True)

    with pytest.warns(UserWarning):
        vintages = fetch.get_vintages()

    assert vintages.iloc[0]["etag"] == '"e2"'


def test_get_vintages_refresh_true_offline_raises_value_error() -> None:
    """`get_vintages(refresh=True)` while offline mode is active raises before any sweep."""
    config.set_offline(True)
    with pytest.raises(ValueError, match="get_vintages"):
        fetch.get_vintages(refresh=True)


def test_get_vintages_refresh_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    """`refresh=True` reaches `_discovery.discover` as an explicit refresh."""
    patch_discovery(monkeypatch, {2019: VintageInfo(url=url_for(2019), etag='"e"')})
    fetch.get_vintages()  # first sweep, memoised

    calls: list[bool] = []
    real_discover = _discovery.discover

    def _spy(*, refresh: bool = False) -> dict[int, VintageInfo]:
        calls.append(refresh)
        return real_discover(refresh=refresh)

    monkeypatch.setattr(_discovery, "discover", _spy)

    fetch.get_vintages(refresh=True)

    assert calls == [True]


# --- offline mode at the fetch layer ---------------------------------------------


def test_offline_mode_serves_cached_vintage_with_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Offline mode skips the sweep and serves the cached vintage, naming offline mode."""
    year = 2019
    url = url_for(year)
    fixture = write_tossd_fixture(tmp_path / "fixture.parquet", year, n_rows=4)
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"e19"')})
    patch_fetcher_by_url(monkeypatch, {url: (fixture.read_bytes(), '"e19"')})
    cached_path = fetch.fetch_year(year)

    config.set_offline(True)

    with pytest.warns(UserWarning, match="[Oo]ffline mode") as record:
        served_path = fetch.fetch_year(year)

    assert served_path == cached_path
    assert "set_offline(False)" in str(record[0].message)


def test_offline_mode_nothing_cached_raises_teaching_set_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Offline mode with nothing cached raises, teaching `set_offline(False)`/the env var."""
    config.set_offline(True)

    with pytest.raises(TossdNetworkError, match="offline mode") as excinfo:
        fetch.fetch_year(2019)

    assert "set_offline(False)" in str(excinfo.value)
    assert "TOSSD_READER_OFFLINE" in str(excinfo.value)


def test_offline_mode_never_attempts_a_head_sweep(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Offline mode short-circuits before `_discovery.discover` ever runs."""
    year = 2019
    url = url_for(year)
    fixture = write_tossd_fixture(tmp_path / "fixture.parquet", year, n_rows=4)
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"e19"')})
    patch_fetcher_by_url(monkeypatch, {url: (fixture.read_bytes(), '"e19"')})
    fetch.fetch_year(year)
    _discovery._reset_for_tests()

    calls = 0
    real_discover = _discovery.discover

    def _counting_discover(*, refresh: bool = False) -> dict[int, VintageInfo]:
        nonlocal calls
        calls += 1
        return real_discover(refresh=refresh)

    monkeypatch.setattr(_discovery, "discover", _counting_discover)
    config.set_offline(True)

    with pytest.warns(UserWarning):
        fetch.fetch_year(year)

    assert calls == 0


def test_offline_mode_env_var_true_also_triggers_the_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`TOSSD_READER_OFFLINE=1` (no explicit `set_offline` call) has the same effect."""
    year = 2019
    url = url_for(year)
    fixture = write_tossd_fixture(tmp_path / "fixture.parquet", year, n_rows=4)
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"e19"')})
    patch_fetcher_by_url(monkeypatch, {url: (fixture.read_bytes(), '"e19"')})
    cached_path = fetch.fetch_year(year)

    monkeypatch.setenv("TOSSD_READER_OFFLINE", "1")

    with pytest.warns(UserWarning, match="[Oo]ffline mode"):
        served_path = fetch.fetch_year(year)

    assert served_path == cached_path
