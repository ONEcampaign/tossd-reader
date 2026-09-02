"""Unit tests for the discovery HEAD-sweep layer."""

from __future__ import annotations

from collections.abc import Callable

import pytest
import requests

from tossd_reader import _discovery
from tossd_reader.exceptions import TossdNetworkError


def _fake_head_one(
    published: dict[int, dict[str, object]],
) -> Callable[[requests.Session, int], _discovery.VintageInfo | None]:
    """Build a stand-in for `_discovery._head_one` backed by a plain dict.

    `published[year]` may be a dict of `VintageInfo` fields, or the sentinel
    string `"offline"` to simulate a transport failure for that year.
    """

    def _head_one(
        _session: requests.Session, year: int
    ) -> _discovery.VintageInfo | None:
        entry = published.get(year)
        if entry is None:
            return None
        if entry == "offline":
            # `_head_one` is replaced wholesale, including its own
            # RequestException -> TossdNetworkError conversion, so the fake
            # raises the already-converted error directly.
            raise TossdNetworkError("simulated network outage")
        return _discovery.VintageInfo(
            url=f"https://tossd.online/tossddata_{year}.parquet",
            etag=entry.get("etag"),
            last_modified=entry.get("last_modified"),
            size_bytes=entry.get("size_bytes"),
        )

    return _head_one


class _FakeHeadResponse:
    """A minimal stand-in for a `requests.Response` from a HEAD request."""

    def __init__(
        self, *, status_code: int, headers: dict[str, str] | None = None
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} error")


class _FakeHeadSession:
    """A minimal stand-in for a `requests.Session`, returning one canned HEAD response."""

    def __init__(
        self,
        *,
        response: _FakeHeadResponse | None = None,
        exc: Exception | None = None,
    ) -> None:
        self._response = response
        self._exc = exc

    def head(self, _url: str, **_kwargs: object) -> _FakeHeadResponse:
        if self._exc is not None:
            raise self._exc
        assert self._response is not None
        return self._response


# --- _discovery._head_one, called directly (never mocked wholesale) ------------


def test_head_one_connection_error_raises_tossd_network_error() -> None:
    """A transport-level failure on the HEAD request itself raises TossdNetworkError."""
    session = _FakeHeadSession(exc=requests.exceptions.ConnectionError("boom"))

    with pytest.raises(TossdNetworkError, match="2020"):
        _discovery._head_one(session, 2020)


def test_head_one_404_returns_none() -> None:
    """A genuine 404 HEAD response resolves to None (year not currently published)."""
    session = _FakeHeadSession(response=_FakeHeadResponse(status_code=404))

    assert _discovery._head_one(session, 2020) is None


def test_head_one_500_raises_uncaught_via_raise_for_status() -> None:
    """A non-404 error status surfaces via raise_for_status, not swallowed as a 404."""
    session = _FakeHeadSession(response=_FakeHeadResponse(status_code=500))

    with pytest.raises(requests.exceptions.HTTPError):
        _discovery._head_one(session, 2020)


def test_head_one_200_populates_vintage_info_from_headers() -> None:
    """A 200 response's ETag/Last-Modified/Content-Length populate VintageInfo."""
    session = _FakeHeadSession(
        response=_FakeHeadResponse(
            status_code=200,
            headers={
                "ETag": '"e1"',
                "Last-Modified": "Tue, 01 Jan 2024 00:00:00 GMT",
                "Content-Length": "12345",
            },
        )
    )

    info = _discovery._head_one(session, 2020)

    assert info == _discovery.VintageInfo(
        url="https://tossd.online/tossddata_2020.parquet",
        etag='"e1"',
        last_modified="Tue, 01 Jan 2024 00:00:00 GMT",
        size_bytes=12345,
    )


def test_known_years_accessor() -> None:
    """The packaged known-years set is exactly 2019-2024."""
    assert _discovery.known_years() == (2019, 2020, 2021, 2022, 2023, 2024)


def test_discover_returns_only_published_years(monkeypatch: pytest.MonkeyPatch) -> None:
    """A year absent from the sweep (404) is simply absent from the mapping."""
    monkeypatch.setattr(
        _discovery, "_head_one", _fake_head_one({2019: {"etag": '"e19"'}})
    )
    result = _discovery.discover()
    assert set(result) == {2019}
    assert result[2019].etag == '"e19"'


def test_discover_memoises_until_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    """A second `discover()` call reuses the memo; `refresh=True` re-sweeps."""
    calls: list[int] = []

    def _counting_head_one(
        _session: requests.Session, year: int
    ) -> _discovery.VintageInfo | None:
        calls.append(year)
        if year not in _discovery.known_years():
            return None  # avoid the unknown-new-year warning path in this test
        return _discovery.VintageInfo(
            url=f"https://tossd.online/tossddata_{year}.parquet"
        )

    monkeypatch.setattr(_discovery, "_head_one", _counting_head_one)

    _discovery.discover()
    calls_after_first_sweep = len(calls)
    assert calls_after_first_sweep > 0

    _discovery.discover()
    assert len(calls) == calls_after_first_sweep, "second call must not re-sweep"

    _discovery.discover(refresh=True)
    assert len(calls) == 2 * calls_after_first_sweep, "refresh=True must re-sweep"


def test_discover_raises_tossd_network_error_when_host_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transport failure anywhere in the sweep surfaces as `TossdNetworkError`."""
    monkeypatch.setattr(_discovery, "_head_one", _fake_head_one({2019: "offline"}))
    with pytest.raises(TossdNetworkError):
        _discovery.discover()


def test_unknown_new_year_warns_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """A year beyond `known_years()` warns once; a later sweep does not repeat it."""
    published = {2019: {"etag": '"e19"'}, 2025: {"etag": '"e25"'}}
    monkeypatch.setattr(_discovery, "_head_one", _fake_head_one(published))

    with pytest.warns(UserWarning, match="2025"):
        result = _discovery.discover()
    assert 2025 in result

    # Same unknown year seen again on a fresh sweep: no repeat warning. With
    # `filterwarnings = ["error"]` set globally, an unexpected warning here
    # would itself raise and fail the test.
    _discovery.discover(refresh=True)


def test_unknown_new_year_warning_points_at_the_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unknown-new-year warning's stacklevel attributes it to the caller."""
    monkeypatch.setattr(
        _discovery, "_head_one", _fake_head_one({2025: {"etag": '"e25"'}})
    )

    with pytest.warns(UserWarning, match="2025") as record:
        _discovery.discover()

    assert record[0].filename.endswith("test_discovery.py")
