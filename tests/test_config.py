"""Unit tests for cache-directory resolution, offline mode, and cache inspection/cleanup."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from readerkit import ArtifactEntry

from tests.factories import write_tossd_fixture
from tests.fakes import patch_discovery, patch_fetcher_by_url, url_for
from tossd_reader import config, fetch
from tossd_reader._discovery import VintageInfo


def test_get_cache_dir_follows_env_var(tmp_path: Path) -> None:
    """With no explicit override, `get_cache_dir` resolves under the env var's tmp_path."""
    resolved = config.get_cache_dir()
    assert resolved is not None
    assert resolved.is_relative_to(tmp_path)


def test_set_cache_dir_explicit_path_wins_over_env_var(tmp_path: Path) -> None:
    """An explicit `set_cache_dir` override takes precedence over the env var."""
    override = tmp_path / "explicit-override"
    config.set_cache_dir(override)
    resolved = config.get_cache_dir()
    assert resolved is not None
    assert resolved.is_relative_to(override)


def test_set_cache_dir_none_is_ephemeral_bypass() -> None:
    """`set_cache_dir(None)` puts the cache in bypass mode: no resolved directory."""
    config.set_cache_dir(None)
    assert config.get_cache_dir() is None

    cache = config.get_cache()
    assert cache.entries() == []  # bypass mode persists nothing


def test_get_cache_rebuilds_when_effective_dir_changes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The cache singleton is rebuilt once the effective directory changes."""
    first = config.get_cache()
    monkeypatch.setenv("TOSSD_READER_CACHE_DIR", str(tmp_path / "other"))
    second = config.get_cache()
    assert first is not second


def test_get_cache_is_stable_when_effective_dir_is_unchanged() -> None:
    """Repeated calls with no directory change reuse the same singleton."""
    first = config.get_cache()
    second = config.get_cache()
    assert first is second


def test_cache_namespace_dir_matches_where_ensure_actually_writes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`cache_namespace_dir()` must track wherever `ArtifactCache.ensure()` really writes, so a
    readerkit layout change fails this test loudly rather than silently breaking
    `fetch._sweep_orphaned_provenance`'s fallback path."""
    year = 2019
    url = url_for(year)
    fixture = write_tossd_fixture(tmp_path / "fixture.parquet", year, n_rows=3)
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"e"')})
    patch_fetcher_by_url(monkeypatch, {url: (fixture.read_bytes(), '"e"')})

    path = fetch.fetch_year(year)

    assert path.parent == config.cache_namespace_dir()


def test_cache_namespace_dir_none_in_bypass_mode() -> None:
    """Ephemeral bypass mode (`set_cache_dir(None)`) has no namespace directory."""
    config.set_cache_dir(None)
    assert config.cache_namespace_dir() is None


def test_set_cache_dir_closes_an_already_built_singleton(tmp_path: Path) -> None:
    """Calling `set_cache_dir` after `get_cache()` closes the old singleton, not just drops it."""
    config.get_cache()  # builds and caches the singleton
    config.set_cache_dir(tmp_path / "new-explicit-dir")
    assert config.get_cache_dir() is not None
    assert config.get_cache_dir().is_relative_to(tmp_path / "new-explicit-dir")


# --- offline mode -------------------------------------------------------------


def test_get_offline_defaults_false_with_no_override_and_no_env_var() -> None:
    """No `set_offline` call and no env var: not offline."""
    assert config.get_offline() is False


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "True", "yes", "YES", "Yes"])
def test_get_offline_env_var_truthy_forms(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    """`TOSSD_READER_OFFLINE` is truthy for `1`/`true`/`yes`, case-insensitively."""
    monkeypatch.setenv("TOSSD_READER_OFFLINE", raw)
    assert config.get_offline() is True


@pytest.mark.parametrize("raw", ["0", "false", "False", "no", ""])
def test_get_offline_env_var_falsy_forms(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    """Recognised-falsy values (and unset) read as not-offline, silently -- no warning."""
    monkeypatch.setenv("TOSSD_READER_OFFLINE", raw)
    assert config.get_offline() is False


@pytest.mark.parametrize("raw", ["offline", "2", "on"])
def test_get_offline_env_var_unrecognized_forms_warn_but_stay_false(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    """A value that's neither truthy nor recognised-falsy warns, naming it, but still resolves
    to not-offline -- a typo must not silently leave the caller believing offline mode is on."""
    monkeypatch.setenv("TOSSD_READER_OFFLINE", raw)
    with pytest.warns(UserWarning) as record:
        assert config.get_offline() is False
    message = str(record[0].message)
    assert raw in message
    assert "TOSSD_READER_OFFLINE" in message
    assert "NOT" in message


def test_get_offline_env_var_unrecognized_value_warns_once_per_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unrecognised-value warning fires once per process, not on every `get_offline()` call."""
    monkeypatch.setenv("TOSSD_READER_OFFLINE", "offline")
    with pytest.warns(UserWarning):
        config.get_offline()

    # Second call, same unrecognised value, same process: no repeat warning. With
    # `filterwarnings = ["error"]` set globally, an unexpected warning here would itself
    # raise and fail the test.
    assert config.get_offline() is False


def test_get_offline_re_reads_env_var_on_every_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No explicit override: an env var change between calls takes effect immediately."""
    assert config.get_offline() is False
    monkeypatch.setenv("TOSSD_READER_OFFLINE", "1")
    assert config.get_offline() is True


def test_set_offline_true_wins_over_falsy_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit `set_offline(True)` overrides even a falsy env var."""
    monkeypatch.setenv("TOSSD_READER_OFFLINE", "0")
    config.set_offline(True)
    assert config.get_offline() is True


def test_set_offline_false_wins_over_truthy_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit `set_offline(False)` overrides even a truthy env var."""
    monkeypatch.setenv("TOSSD_READER_OFFLINE", "1")
    config.set_offline(False)
    assert config.get_offline() is False


def test_set_offline_none_resets_to_env_var_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`set_offline(None)` clears an explicit override, falling back to the env var again."""
    monkeypatch.setenv("TOSSD_READER_OFFLINE", "1")
    config.set_offline(False)
    assert config.get_offline() is False

    config.set_offline(None)
    assert config.get_offline() is True


def test_reset_for_tests_clears_the_offline_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_reset_for_tests` clears a `set_offline` override, same as the autouse fixture between tests."""
    monkeypatch.setenv("TOSSD_READER_OFFLINE", "1")
    config.set_offline(False)
    config._reset_for_tests()
    assert config.get_offline() is True


def test_raise_if_offline_refresh_conflict_raises_when_both_true() -> None:
    """`refresh=True` while offline mode is active raises, naming the caller and the fix."""
    config.set_offline(True)
    with pytest.raises(ValueError, match="my_func") as excinfo:
        config.raise_if_offline_refresh_conflict(refresh=True, func_name="my_func")
    message = str(excinfo.value)
    assert "offline" in message
    assert "set_offline(False)" in message


@pytest.mark.parametrize(
    ("offline", "refresh"), [(True, False), (False, True), (False, False)]
)
def test_raise_if_offline_refresh_conflict_silent_otherwise(
    offline: bool, refresh: bool
) -> None:
    """Every combination except (offline=True, refresh=True) is silent."""
    config.set_offline(offline)
    config.raise_if_offline_refresh_conflict(refresh=refresh, func_name="my_func")


# --- cache_info -----------------------------------------------------------------


def _cache_one_year(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, year: int, *, etag: str
) -> Path:
    """Cache one year's vintage under `etag`, faking discovery/fetch. Returns its cache path."""
    url = url_for(year)
    fixture = write_tossd_fixture(
        # The etag's own quote characters are illegal in Windows filenames.
        tmp_path / f"fixture_{year}_{etag.strip('"')}.parquet",
        year,
        n_rows=4,
    )
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag=etag)})
    patch_fetcher_by_url(monkeypatch, {url: (fixture.read_bytes(), etag)})
    return fetch.fetch_year(year, refresh=True)


def test_cache_info_empty_cache_has_the_right_columns_and_no_rows() -> None:
    """An empty cache still returns a frame with every documented column."""
    info = config.cache_info()
    assert list(info.columns) == [
        "year",
        "etag",
        "retrieved_at",
        "downloaded_at",
        "size_bytes",
        "path",
    ]
    assert len(info) == 0


def test_cache_info_bypass_mode_is_empty() -> None:
    """Ephemeral bypass mode (`set_cache_dir(None)`) persists nothing, so `cache_info` is empty."""
    config.set_cache_dir(None)
    assert len(config.cache_info()) == 0


def test_cache_info_reports_one_row_per_cached_entry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A freshly cached vintage's row carries the year, etag, and a real path/size."""
    path = _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e19"')

    info = config.cache_info()

    assert len(info) == 1
    row = info.iloc[0]
    assert row["year"] == 2019
    assert row["etag"] == '"e19"'
    assert row["path"] == path
    assert row["size_bytes"] == path.stat().st_size
    datetime.fromisoformat(row["retrieved_at"])
    assert isinstance(row["downloaded_at"], datetime)


def test_cache_info_includes_superseded_vintages(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A republished year (two ETags) gets one row per cached vintage, not one per year."""
    _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e1"')
    _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e2"')

    info = config.cache_info()

    assert len(info) == 2
    assert set(info["etag"]) == {'"e1"', '"e2"'}
    assert set(info["year"]) == {2019}


def test_cache_info_multiple_years(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Distinct years each get their own row."""
    _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e19"')
    _cache_one_year(monkeypatch, tmp_path, 2020, etag='"e20"')

    info = config.cache_info()

    assert sorted(info["year"]) == [2019, 2020]


def test_cache_info_missing_provenance_sidecar_reads_none_not_raise(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A lost provenance sidecar degrades `etag`/`retrieved_at` to `None`, no raise."""
    path = _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e19"')
    path.with_suffix(".provenance.json").unlink()

    info = config.cache_info()

    row = info.iloc[0]
    assert row["etag"] is None
    assert row["retrieved_at"] is None


# --- clear_cache ------------------------------------------------------------------


def test_clear_cache_empty_cache_returns_zero() -> None:
    """Nothing cached: `clear_cache()` removes nothing and doesn't raise."""
    assert config.clear_cache() == 0


def test_clear_cache_default_drops_only_superseded_vintages(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The bare call keeps the newest vintage per year, drops the rest."""
    _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e1"')
    newest = _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e2"')
    _cache_one_year(
        monkeypatch, tmp_path, 2020, etag='"only"'
    )  # single vintage: untouched

    removed = config.clear_cache()

    assert removed == 1
    remaining = config.cache_info()
    assert len(remaining) == 2
    assert newest.exists()
    assert set(remaining["etag"]) == {'"e2"', '"only"'}


def test_clear_cache_keep_latest_false_removes_everything_matching(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`keep_latest=False` with no other filters empties the whole cache."""
    _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e1"')
    _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e2"')
    _cache_one_year(monkeypatch, tmp_path, 2020, etag='"only"')

    removed = config.clear_cache(keep_latest=False)

    assert removed == 3
    assert len(config.cache_info()) == 0


def test_clear_cache_years_filter_restricts_to_named_years(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`years=` restricts which years are ever touched, even under `keep_latest=False`."""
    _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e19"')
    _cache_one_year(monkeypatch, tmp_path, 2020, etag='"e20"')

    removed = config.clear_cache(years=2019, keep_latest=False)

    assert removed == 1
    remaining = config.cache_info()
    assert list(remaining["year"]) == [2020]


def test_clear_cache_years_accepts_an_iterable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`years=` also accepts an iterable of years, not just a single int."""
    _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e19"')
    _cache_one_year(monkeypatch, tmp_path, 2020, etag='"e20"')
    _cache_one_year(monkeypatch, tmp_path, 2021, etag='"e21"')

    removed = config.clear_cache(years=[2019, 2021], keep_latest=False)

    assert removed == 2
    assert list(config.cache_info()["year"]) == [2020]


@pytest.mark.parametrize(
    "before_arg_factory",
    [
        lambda future: future,  # a tz-aware datetime
        lambda future: future.replace(tzinfo=None),  # a naive datetime, treated as UTC
        lambda future: future.date(),  # a bare date
        lambda future: future.isoformat(),  # an ISO datetime string
        lambda future: future.date().isoformat(),  # an ISO date string
    ],
    ids=["datetime", "naive-datetime", "date", "iso-string", "iso-date-string"],
)
def test_clear_cache_before_accepts_date_datetime_and_iso_string(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, before_arg_factory
) -> None:
    """`before=` accepts a `date`, a `datetime`, or an ISO 8601 string, all comparably."""
    _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e19"')
    future = datetime.now(UTC) + timedelta(days=1)

    removed = config.clear_cache(before=before_arg_factory(future), keep_latest=False)

    assert removed == 1
    assert len(config.cache_info()) == 0


def test_clear_cache_before_excludes_entries_retrieved_after_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An entry retrieved after `before=` is left alone."""
    _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e19"')
    past = datetime.now(UTC) - timedelta(days=1)

    removed = config.clear_cache(before=past, keep_latest=False)

    assert removed == 0
    assert len(config.cache_info()) == 1


def test_clear_cache_before_falls_back_to_downloaded_at_without_a_sidecar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A missing provenance sidecar degrades `before=`'s comparison to `downloaded_at`, not a raise."""
    path = _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e19"')
    path.with_suffix(".provenance.json").unlink()
    future = datetime.now(UTC) + timedelta(days=1)

    removed = config.clear_cache(before=future, keep_latest=False)

    assert removed == 1


def test_clear_cache_nothing_matches_returns_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A `years=` filter matching nothing cached removes nothing."""
    _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e19"')

    assert config.clear_cache(years=2099) == 0
    assert len(config.cache_info()) == 1


def test_clear_cache_returns_a_plain_int_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The return value is the exact count of entries removed."""
    _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e1"')
    _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e2"')
    _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e3"')

    removed = config.clear_cache(keep_latest=False)

    assert removed == 3
    assert isinstance(removed, int)


def test_clear_cache_unlinks_the_provenance_sidecar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`clear_cache` removes an entry's `.provenance.json` sidecar alongside its payload.

    `cache.invalidate` (readerkit's own) only knows its own payload and internal sidecar -- it
    has no idea this package writes its own provenance file beside them. Left behind, that file
    would orphan.
    """
    path = _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e19"')
    sidecar_path = path.with_suffix(".provenance.json")
    assert sidecar_path.exists()

    removed = config.clear_cache(keep_latest=False)

    assert removed == 1
    assert not path.exists()
    assert not sidecar_path.exists()


def test_clear_cache_then_refetch_same_key_does_not_resurrect_stale_provenance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A stale orphaned sidecar must not survive a re-fetch under the same cache key.

    Mirrors a real scenario: a closed-out historical year re-downloaded under an unchanged ETag
    regenerates the identical cache key and payload path. Before the fix, `clear_cache` left the
    old sidecar in place, and `write_provenance_if_absent`'s "no-op when a file already exists at
    this path" rule meant that leftover silently won over the fresh retrieval.
    """
    path = _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e19"')
    sidecar_path = path.with_suffix(".provenance.json")
    original_retrieved_at = json.loads(sidecar_path.read_text())["retrieved_at"]

    config.clear_cache(keep_latest=False)
    assert not sidecar_path.exists()

    # Re-fetch the same year under the same ETag -- same cache key, so `cache.ensure` writes to
    # the identical payload path readerkit uses for that key.
    refetched_path = _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e19"')
    assert refetched_path == path

    fresh_retrieved_at = json.loads(sidecar_path.read_text())["retrieved_at"]
    assert fresh_retrieved_at != original_retrieved_at


def test_clear_cache_handles_invalidate_returning_false(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A no-op `invalidate()` (nothing actually removed) doesn't inflate the `removed` count."""
    _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e1"')
    _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e2"')
    cache = config.get_cache()
    monkeypatch.setattr(cache, "invalidate", lambda key: False)

    removed = config.clear_cache(keep_latest=False)

    assert removed == 0
    assert (
        len(cache.entries()) == 2
    )  # untouched: the faked invalidate() never really ran


def test_clear_cache_ignores_a_foreign_cache_entry() -> None:
    """A cache entry whose key doesn't match this package's own `tossd_<year>_...` shape is left alone."""
    cache = config.get_cache()
    cache.ensure(
        "not-a-tossd-key",
        fetcher=lambda ctx: ctx.path.write_bytes(b"x"),
        ttl=timedelta(days=1),
    )

    removed = config.clear_cache(keep_latest=False)

    assert removed == 0
    assert len(cache.entries()) == 1


def test_clear_cache_keep_latest_default_ignores_a_foreign_cache_entry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A foreign entry is skipped in `_newest_key_per_year` too, under the default `keep_latest=True`."""
    _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e1"')
    _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e2"')
    cache = config.get_cache()
    cache.ensure(
        "not-a-tossd-key",
        fetcher=lambda ctx: ctx.path.write_bytes(b"x"),
        ttl=timedelta(days=1),
    )

    removed = config.clear_cache()  # keep_latest=True (the default)

    assert removed == 1  # the superseded 2019 vintage only
    assert len(cache.entries()) == 2  # newest 2019 vintage + the foreign entry


def test_clear_cache_before_normalizes_a_naive_retrieved_at_to_utc(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A well-formed but naive (no tzinfo) `retrieved_at` in the sidecar is treated as UTC,
    not compared raw against the always-aware `before=` (which would raise `TypeError`)."""
    path = _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e19"')
    sidecar_path = path.with_suffix(".provenance.json")
    record = json.loads(sidecar_path.read_text())
    record["retrieved_at"] = "2020-01-01T00:00:00"  # naive: no timezone offset
    sidecar_path.write_text(json.dumps(record))
    future = datetime.now(UTC) + timedelta(days=1)

    removed = config.clear_cache(before=future, keep_latest=False)

    assert removed == 1


def test_clear_cache_before_naive_retrieved_at_excludes_entries_retrieved_after_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A naive `retrieved_at` normalizes to UTC, not local time or some other zone -- an entry
    naively retrieved after `before=` is still left alone, not just tolerated without raising."""
    path = _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e19"')
    sidecar_path = path.with_suffix(".provenance.json")
    record = json.loads(sidecar_path.read_text())
    record["retrieved_at"] = "2099-01-01T00:00:00"  # naive, far in the future
    sidecar_path.write_text(json.dumps(record))
    past = datetime.now(UTC) - timedelta(days=1)

    removed = config.clear_cache(before=past, keep_latest=False)

    assert removed == 0


def test_clear_cache_before_tolerates_a_garbage_retrieved_at_date(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An unparseable `retrieved_at` in the sidecar degrades to `downloaded_at`, no raise."""
    path = _cache_one_year(monkeypatch, tmp_path, 2019, etag='"e19"')
    sidecar_path = path.with_suffix(".provenance.json")
    record = json.loads(sidecar_path.read_text())
    record["retrieved_at"] = "not-a-real-date"
    sidecar_path.write_text(json.dumps(record))
    future = datetime.now(UTC) + timedelta(days=1)

    removed = config.clear_cache(before=future, keep_latest=False)

    assert removed == 1


def test_cache_info_ignores_a_foreign_cache_entry() -> None:
    """A foreign cache entry's `year` reads `None` rather than raising."""
    cache = config.get_cache()
    cache.ensure(
        "not-a-tossd-key",
        fetcher=lambda ctx: ctx.path.write_bytes(b"x"),
        ttl=timedelta(days=1),
    )

    info = config.cache_info()

    assert len(info) == 1
    assert info.iloc[0]["year"] is None


def test_newest_key_per_year_finds_the_true_newest_regardless_of_scan_order() -> None:
    """`_newest_key_per_year` doesn't just take the first entry seen per year."""
    now = datetime.now(UTC)
    older = ArtifactEntry(
        key="tossd_2019_older",
        path=Path("/tmp/older"),
        size_bytes=1,
        downloaded_at=now - timedelta(days=1),
        last_access_at=now,
        ttl=timedelta(days=1),
        version=None,
    )
    newer = ArtifactEntry(
        key="tossd_2019_newer",
        path=Path("/tmp/newer"),
        size_bytes=1,
        downloaded_at=now,
        last_access_at=now,
        ttl=timedelta(days=1),
        version=None,
    )

    assert config._newest_key_per_year([older, newer], key_year=fetch.key_year) == {
        2019: "tossd_2019_newer"
    }
    # newer scanned first: the older entry must not overwrite it.
    assert config._newest_key_per_year([newer, older], key_year=fetch.key_year) == {
        2019: "tossd_2019_newer"
    }
