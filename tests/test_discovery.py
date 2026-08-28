"""Unit tests for the discovery HEAD-sweep layer."""

from __future__ import annotations

from collections.abc import Callable

import pytest
import requests

from tossd_reader import discovery
from tossd_reader.exceptions import TossdNetworkError


def _fake_head_one(
    published: dict[int, dict[str, object]],
) -> Callable[[requests.Session, int], discovery.VintageInfo | None]:
    """Build a stand-in for `discovery._head_one` backed by a plain dict.

    `published[year]` may be a dict of `VintageInfo` fields, or the sentinel
    string `"offline"` to simulate a transport failure for that year.
    """

    def _head_one(
        _session: requests.Session, year: int
    ) -> discovery.VintageInfo | None:
        entry = published.get(year)
        if entry is None:
            return None
        if entry == "offline":
            # `_head_one` is replaced wholesale, including its own
            # RequestException -> TossdNetworkError conversion, so the fake
            # raises the already-converted error directly.
            raise TossdNetworkError("simulated network outage")
        return discovery.VintageInfo(
            url=f"https://tossd.online/tossddata_{year}.parquet",
            etag=entry.get("etag"),
            last_modified=entry.get("last_modified"),
            size_bytes=entry.get("size_bytes"),
        )

    return _head_one


def test_known_years_accessor() -> None:
    """The packaged known-years set is exactly 2019-2024."""
    assert discovery.known_years() == (2019, 2020, 2021, 2022, 2023, 2024)


def test_discover_returns_only_published_years(monkeypatch: pytest.MonkeyPatch) -> None:
    """A year absent from the sweep (404) is simply absent from the mapping."""
    monkeypatch.setattr(
        discovery, "_head_one", _fake_head_one({2019: {"etag": '"e19"'}})
    )
    result = discovery.discover()
    assert set(result) == {2019}
    assert result[2019].etag == '"e19"'


def test_discover_memoises_until_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    """A second `discover()` call reuses the memo; `refresh=True` re-sweeps."""
    calls: list[int] = []

    def _counting_head_one(
        _session: requests.Session, year: int
    ) -> discovery.VintageInfo | None:
        calls.append(year)
        if year not in discovery.known_years():
            return None  # avoid the unknown-new-year warning path in this test
        return discovery.VintageInfo(
            url=f"https://tossd.online/tossddata_{year}.parquet"
        )

    monkeypatch.setattr(discovery, "_head_one", _counting_head_one)

    discovery.discover()
    calls_after_first_sweep = len(calls)
    assert calls_after_first_sweep > 0

    discovery.discover()
    assert len(calls) == calls_after_first_sweep, "second call must not re-sweep"

    discovery.discover(refresh=True)
    assert len(calls) == 2 * calls_after_first_sweep, "refresh=True must re-sweep"


def test_discover_raises_tossd_network_error_when_host_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transport failure anywhere in the sweep surfaces as `TossdNetworkError`."""
    monkeypatch.setattr(discovery, "_head_one", _fake_head_one({2019: "offline"}))
    with pytest.raises(TossdNetworkError):
        discovery.discover()


def test_unknown_new_year_warns_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """A year beyond `known_years()` warns once; a later sweep does not repeat it."""
    published = {2019: {"etag": '"e19"'}, 2025: {"etag": '"e25"'}}
    monkeypatch.setattr(discovery, "_head_one", _fake_head_one(published))

    with pytest.warns(UserWarning, match="2025"):
        result = discovery.discover()
    assert 2025 in result

    # Same unknown year seen again on a fresh sweep: no repeat warning. With
    # `filterwarnings = ["error"]` set globally, an unexpected warning here
    # would itself raise and fail the test.
    discovery.discover(refresh=True)


def test_unknown_new_year_warning_points_at_the_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unknown-new-year warning's stacklevel attributes it to the caller."""
    monkeypatch.setattr(
        discovery, "_head_one", _fake_head_one({2025: {"etag": '"e25"'}})
    )

    with pytest.warns(UserWarning, match="2025") as record:
        discovery.discover()

    assert record[0].filename.endswith("test_discovery.py")
