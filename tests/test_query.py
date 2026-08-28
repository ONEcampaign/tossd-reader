"""Unit tests for the query layer (D6/D7): get_tossd and its D7 binding semantics."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import requests

import tossd_reader
from tests.fixtures import build_tossd_table
from tossd_reader import discovery, fetch, query
from tossd_reader.discovery import VintageInfo
from tossd_reader.exceptions import (
    InvalidPillarError,
    SchemaDriftError,
    UnknownCodeError,
)

# --- shared fetch/discovery patching (mirrors tests/test_fetch.py's own helpers) --


def _url_for(year: int) -> str:
    return f"https://tossd.online/tossddata_{year}.parquet"


def _patch_discovery(
    monkeypatch: pytest.MonkeyPatch, vintages: dict[int, VintageInfo]
) -> None:
    def _head_one(_session: requests.Session, year: int) -> VintageInfo | None:
        return vintages.get(year)

    monkeypatch.setattr(discovery, "_head_one", _head_one)


def _patch_fetcher_by_url(
    monkeypatch: pytest.MonkeyPatch, sources: dict[str, tuple[bytes, str | None]]
) -> None:
    def _factory(
        url: str, _session: requests.Session, *, year: int, expected_etag: str | None
    ):
        captured: dict[str, str | int | None] = {"etag": None, "size_bytes": None}

        def _fetch(ctx: object) -> None:
            payload, true_etag = sources[url]
            captured["etag"] = true_etag
            captured["size_bytes"] = len(payload)
            ctx.path.write_bytes(payload)  # type: ignore[attr-defined]

        return _fetch, captured

    monkeypatch.setattr(fetch, "_make_fetcher", _factory)


def _setup_years(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tables: dict[int, pa.Table]
) -> None:
    """Serve `tables` (one per year) through the normal fetch/discovery path."""
    published: dict[int, VintageInfo] = {}
    sources: dict[str, tuple[bytes, str | None]] = {}
    for year, table in tables.items():
        path = tmp_path / f"fixture_{year}.parquet"
        pq.write_table(table, path, row_group_size=table.num_rows)
        url = _url_for(year)
        etag = f'"e{year}"'
        published[year] = VintageInfo(url=url, etag=etag)
        sources[url] = (path.read_bytes(), etag)
    _patch_discovery(monkeypatch, published)
    _patch_fetcher_by_url(monkeypatch, sources)


def _setup_default_years(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    years: list[int],
    n_rows: int = 40,
    seed: int = 0,
) -> None:
    tables = {year: build_tossd_table(year, n_rows=n_rows, seed=seed) for year in years}
    _setup_years(monkeypatch, tmp_path, tables)


def _with_bad_parent_channel_code(
    table: pa.Table, bad_code: str = "99999999"
) -> pa.Table:
    """Return a copy of `table` with row 0's `ParentChannelCode` set to `bad_code`."""
    index = table.column_names.index("ParentChannelCode")
    values = table.column("ParentChannelCode").to_pylist()
    values[0] = bad_code
    return table.set_column(
        index, "ParentChannelCode", pa.array(values, type=pa.string())
    )


def _with_known_parent_channel_code(table: pa.Table, code: str = "11000") -> pa.Table:
    """Return a copy of `table` with row 0's `ParentChannelCode` set to `code`.

    `code="11000"` ("Provider Government") is present in the packaged
    `channel.csv` codelist.
    """
    index = table.column_names.index("ParentChannelCode")
    values = table.column("ParentChannelCode").to_pylist()
    values[0] = code
    return table.set_column(
        index, "ParentChannelCode", pa.array(values, type=pa.string())
    )


# --- D6: categorical dtype survives a multi-year concat -----------------------


def test_multi_year_concat_unifies_divergent_categorical_dictionaries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A 3-year query keeps `provider_name` dictionary-encoded, even with divergent per-year vocab.

    Each year uses a different `n_rows` (and seed) so its `provider_name`
    dictionary covers a genuinely different subset of the fixture's 5
    providers plus the aggregate row (2019: 2 distinct, 2020: all 6, 2021: 4
    distinct) -- unlike a same-seed/same-size fixture (every year already
    carrying an identical dictionary), this can't pass merely because
    `.unify_dictionaries()` was a no-op; only genuinely reconciling
    different per-chunk dictionaries into one shared dictionary does.
    """
    tables = {
        2019: build_tossd_table(2019, n_rows=4, seed=0),
        2020: build_tossd_table(2020, n_rows=8, seed=1),
        2021: build_tossd_table(2021, n_rows=6, seed=2),
    }
    _setup_years(monkeypatch, tmp_path, tables)

    combined, _paths = query._build_table(
        years=[2019, 2020, 2021],
        providers=None,
        recipients=None,
        pillars=None,
        columns="all",
        units="usd_thousand",
        refresh=False,
        op_name="test:unify_dictionaries",
    )
    provider_column = combined.column("provider_name")
    dictionaries = [chunk.dictionary.to_pylist() for chunk in provider_column.chunks]
    assert len(dictionaries) > 1, "fixture setup should produce multiple chunks"
    assert all(dictionary == dictionaries[0] for dictionary in dictionaries), (
        "unify_dictionaries should give every chunk an identical dictionary"
    )

    df = combined.to_pandas()
    assert isinstance(df["provider_name"].dtype, pd.CategoricalDtype)
    assert set(df["provider_name"]) == {
        "Aggregate",
        "Provider Alpha",
        "Provider Beta",
        "Provider Delta",
        "Provider Epsilon",
        "Provider Gamma",
    }
    assert len(df) == 4 + 8 + 6


# --- one discovery sweep per call, not once per requested year ----------------


def test_get_tossd_multi_year_refresh_sweeps_discovery_exactly_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A multi-year get_tossd(refresh=True) call sweeps discovery once, not once per year."""
    years = [2019, 2020, 2021]
    _setup_default_years(monkeypatch, tmp_path, years, n_rows=5)

    calls: list[bool] = []
    real_discover = discovery.discover

    def _spy(*, refresh: bool = False) -> dict:
        calls.append(refresh)
        return real_discover(refresh=refresh)

    monkeypatch.setattr(discovery, "discover", _spy)

    query.get_tossd(years=years, refresh=True)

    assert len(calls) == 1


def test_export_multi_year_refresh_sweeps_discovery_exactly_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A multi-year export(refresh=True) call sweeps discovery once, not once per year."""
    years = [2019, 2020, 2021]
    _setup_default_years(monkeypatch, tmp_path, years, n_rows=5)

    calls: list[bool] = []
    real_discover = discovery.discover

    def _spy(*, refresh: bool = False) -> dict:
        calls.append(refresh)
        return real_discover(refresh=refresh)

    monkeypatch.setattr(discovery, "discover", _spy)

    tossd_reader.export(tmp_path / "out", years=years, refresh=True)

    assert len(calls) == 1


# --- providers / recipients: code / name / digit-string / miss ----------------


def test_provider_filter_by_int_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A plain int is trusted directly as a provider code."""
    _setup_default_years(monkeypatch, tmp_path, [2019], n_rows=40)

    df = query.get_tossd(years=2019, providers=1)

    assert not df.empty
    assert (df["provider_code"] == 1).all()
    # Names always come from the file, never the codelist (913/914-style
    # collisions make name-keyed decode unsafe) -- code 1 is "Austria" in the
    # packaged codelist, but the file's own fixture name must win.
    assert set(df["provider_name"]) == {"Provider Alpha"}


def test_provider_filter_by_name_case_folded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A str resolves against the packaged codelist's name column, case-foldedly."""
    _setup_default_years(monkeypatch, tmp_path, [2019], n_rows=40)

    df = query.get_tossd(years=2019, providers="aUsTrIa")  # code 1 in provider.csv

    assert not df.empty
    assert (df["provider_code"] == 1).all()


def test_provider_filter_by_digit_string_tries_code_first(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A digit-string resolves as a code match before falling back to a name match."""
    _setup_default_years(monkeypatch, tmp_path, [2019], n_rows=40)

    df = query.get_tossd(years=2019, providers="4")  # code 4 ("France") in provider.csv

    assert not df.empty
    assert (df["provider_code"] == 4).all()


def test_recipient_filter_by_name_and_iterable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`recipients=` accepts an iterable mixing a name and a code."""
    _setup_default_years(monkeypatch, tmp_path, [2019], n_rows=40)

    df = query.get_tossd(years=2019, recipients=["Türkiye", 269])

    assert not df.empty
    assert set(df["recipient_code"]) <= {55, 269}


def test_provider_int_outside_int16_range_raises_unknown_code_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A plain-int provider code outside Int16 range raises UnknownCodeError, not ArrowInvalid."""
    _setup_default_years(monkeypatch, tmp_path, [2019], n_rows=5)

    with pytest.raises(UnknownCodeError, match="123456789"):
        query.get_tossd(years=2019, providers=123456789)


def test_recipient_int_outside_int16_range_raises_unknown_code_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A plain-int recipient code outside Int16 range raises UnknownCodeError, not ArrowInvalid."""
    _setup_default_years(monkeypatch, tmp_path, [2019], n_rows=5)

    with pytest.raises(UnknownCodeError, match="-99999"):
        query.get_tossd(years=2019, recipients=-99999)


def test_unknown_provider_name_raises_unknown_code_error_with_suggestions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A near-miss provider name raises `UnknownCodeError`, naming the token + a suggestion."""
    _setup_default_years(monkeypatch, tmp_path, [2019], n_rows=5)

    with pytest.raises(UnknownCodeError, match="Austrai") as excinfo:
        query.get_tossd(years=2019, providers="Austrai")

    assert "Austria" in str(excinfo.value)


# --- lazy resolvekit import (module-level import is forbidden) ----------------


def test_resolvekit_is_imported_lazily_only_on_the_unknown_code_error_path() -> None:
    """`resolvekit` is never imported by the module itself, only on an actual miss."""
    script = (
        "import sys\n"
        "import tossd_reader.query as query\n"
        "assert 'resolvekit' not in sys.modules\n"
        "try:\n"
        "    query._resolve_dimension_codes(\n"
        "        'Definitely Not A Real Provider', dimension='provider', label='providers'\n"
        "    )\n"
        "except Exception:\n"
        "    pass\n"
        "assert 'resolvekit' in sys.modules\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK"


def test_suggestion_falls_back_to_difflib_when_resolvekit_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If resolvekit's suggestion helper raises, the difflib fallback still suggests sensibly."""
    _setup_default_years(monkeypatch, tmp_path, [2019], n_rows=5)

    def _boom(dimension: str, token: str) -> list[str]:
        raise RuntimeError("resolvekit exploded")

    monkeypatch.setattr(query, "_suggest_with_resolvekit", _boom)

    with pytest.raises(UnknownCodeError, match="Austrai") as excinfo:
        query.get_tossd(years=2019, providers="Austrai")

    assert "Austria" in str(excinfo.value)


# --- pillars: every token, filter semantics, pillar-0 --------------------------


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        (1, ("1", None)),
        ("1", ("1", None)),
        ("I", ("1", None)),
        ("i", ("1", None)),
        (2, ("2", None)),
        ("2", ("2", None)),
        ("II", ("2", None)),
        (21, ("2", "21")),
        ("21", ("2", "21")),
        ("II.A", ("2", "21")),
        ("ii.a", ("2", "21")),
        (22, ("2", "22")),
        ("22", ("2", "22")),
        ("II.B", ("2", "22")),
    ],
)
def test_every_pillar_token_normalises_correctly(
    token: int | str, expected: tuple
) -> None:
    """Every documented D7 pillar token maps to the right (pillar, subpillar) pair."""
    assert query._normalise_pillar_token(token) == expected


def test_unknown_pillar_token_raises_value_error() -> None:
    """An unrecognised pillars= token raises ValueError, not a silent no-op."""
    with pytest.raises(ValueError, match="pillars"):
        query._normalise_pillar_token("III")


def test_pillar_filter_matches_tossd_pillar_and_excludes_pillar_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """pillars=1/2 filter tossd_pillar; pillar-0 placeholder rows are always excluded."""
    _setup_default_years(monkeypatch, tmp_path, [2022], n_rows=10)

    unfiltered = query.get_tossd(years=2022)
    assert (unfiltered["tossd_pillar"] == 0).any(), "fixture must carry pillar-0 rows"

    pillar_1 = query.get_tossd(years=2022, pillars=1)
    assert not pillar_1.empty
    assert (pillar_1["tossd_pillar"] == 1).all()

    pillar_2 = query.get_tossd(years=2022, pillars="II")
    assert not pillar_2.empty
    assert (pillar_2["tossd_pillar"] == 2).all()


def test_pillar_none_includes_pillar_zero_placeholder_rows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """pillars=None (the default) includes the pillar-0 placeholder rows."""
    _setup_default_years(monkeypatch, tmp_path, [2022], n_rows=10)

    df = query.get_tossd(years=2022)

    assert (df["tossd_pillar"] == 0).any()


def test_subpillar_filter_matches_only_that_subpillar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """pillars=21/'II.A' matches only tossd_subpillar=='21' rows, all under pillar 2."""
    _setup_default_years(monkeypatch, tmp_path, [2024], n_rows=60)

    df = query.get_tossd(years=2024, pillars="II.A")

    assert not df.empty
    assert (df["tossd_subpillar"] == "21").all()
    assert (df["tossd_pillar"] == 2).all()


# --- sub-pillar year policy -----------------------------------------------------


def test_subpillar_with_explicit_year_2022_raises_invalid_pillar_error() -> None:
    """A sub-pillar filter with an explicit year before 2023 raises, naming 2022's trace rows.

    Raises before any fetch/discovery I/O, so no fixtures are needed here.
    """
    with pytest.raises(InvalidPillarError, match="24") as excinfo:
        query.get_tossd(years=2022, pillars="II.A")

    assert "pillars=2" in str(excinfo.value)


def test_subpillar_with_explicit_year_2021_raises_invalid_pillar_error() -> None:
    """A sub-pillar filter with any other pre-2023 explicit year also raises."""
    with pytest.raises(InvalidPillarError, match="2021"):
        query.get_tossd(years=2021, pillars=22)


def test_subpillar_default_years_auto_narrows_with_one_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """years=None + a sub-pillar filter narrows to >=2023 years, warning once.

    The narrowed default (>=2023) always includes 2023 itself, so the
    coverage warning (D7) fires alongside the narrowing warning in the same
    call: `pytest.warns` is used unmatched here and both are asserted
    explicitly, rather than `match=`, which only tolerates a single warning
    under this suite's `filterwarnings = ["error"]`.
    """
    _setup_default_years(monkeypatch, tmp_path, [2023, 2024], n_rows=40)

    with pytest.warns(UserWarning) as record:
        df = query.get_tossd(pillars="II.A")

    messages = [str(warning.message) for warning in record]
    assert any("narrowing" in message for message in messages)
    assert any("49%" in message for message in messages)
    assert not df.empty
    assert (df["tossd_subpillar"] == "21").all()


def test_subpillar_touching_2023_warns_coverage_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An explicit sub-pillar query that includes 2023 warns about incomplete coverage."""
    _setup_default_years(monkeypatch, tmp_path, [2023, 2024], n_rows=40)

    with pytest.warns(UserWarning, match="49%"):
        query.get_tossd(years=[2023, 2024], pillars=21)

    # Same warning, same session: suppressed the second time (filterwarnings
    # = ["error"] globally means an unexpected repeat would fail this test).
    query.get_tossd(years=[2023, 2024], pillars=21)


def test_warn_once_per_session_and_reset_hook(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The narrowing warning fires once per session, and again after `_reset_for_tests`."""
    _setup_default_years(monkeypatch, tmp_path, [2023, 2024], n_rows=20)

    with pytest.warns(UserWarning) as record:
        query.get_tossd(pillars="II.A")
    assert any("narrowing" in str(warning.message) for warning in record)

    query.get_tossd(
        pillars="II.A"
    )  # no repeat warning: would fail under filterwarnings=error

    query._reset_for_tests()

    with pytest.warns(UserWarning) as record:
        query.get_tossd(pillars="II.A")
    assert any("narrowing" in str(warning.message) for warning in record)


# --- columns / presets ----------------------------------------------------------


def test_minimal_preset_still_carries_always_present_columns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """columns='minimal' still carries is_aggregate/unit alongside the pillar columns."""
    _setup_default_years(monkeypatch, tmp_path, [2019], n_rows=10)

    df = query.get_tossd(years=2019, columns="minimal")

    for name in ("tossd_pillar", "tossd_subpillar", "is_aggregate", "unit"):
        assert name in df.columns
    assert "project_description" not in df.columns  # analysis/all-only column


def test_user_column_list_forces_always_present_columns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An explicit columns= list still gets the four always-present columns appended."""
    _setup_default_years(monkeypatch, tmp_path, [2019], n_rows=10)

    df = query.get_tossd(years=2019, columns=["provider_code"])

    assert next(iter(df.columns)) == "provider_code"
    for name in ("tossd_pillar", "tossd_subpillar", "is_aggregate", "unit"):
        assert name in df.columns


# --- F12: read-time column projection ------------------------------------------


def _spy_on_read_table(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Wrap `pyarrow.parquet.read_table` to record each call's kwargs, real read intact."""
    calls: list[dict[str, object]] = []
    real_read_table = pq.read_table

    def _spy(path: object, **kwargs: object) -> pa.Table:
        calls.append(kwargs)
        return real_read_table(path, **kwargs)

    monkeypatch.setattr(query.pq, "read_table", _spy)
    return calls


def test_minimal_preset_only_reads_published_columns_it_needs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """columns='minimal' pushes projection down: an analysis/all-only column is never read."""
    _setup_default_years(monkeypatch, tmp_path, [2019], n_rows=10)
    calls = _spy_on_read_table(monkeypatch)

    query.get_tossd(years=2019, columns="minimal")

    assert len(calls) == 1
    requested = calls[0]["columns"]
    assert requested is not None
    assert "ProjectDescription" not in requested  # project_description: not in minimal
    assert (
        "provider" in requested
    )  # provider_code: in minimal, and is_aggregate needs it


def test_columns_all_reads_every_column_no_projection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """columns='all' (the default) still reads the whole file -- no columns= kwarg at all."""
    _setup_default_years(monkeypatch, tmp_path, [2019], n_rows=10)
    calls = _spy_on_read_table(monkeypatch)

    query.get_tossd(years=2019, columns="all")

    assert len(calls) == 1
    assert calls[0].get("columns") is None


def test_missing_column_raises_drift_even_when_projection_would_not_have_read_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A file genuinely missing a schema column is still caught under a narrow projection.

    `project_description` isn't in the `minimal` preset, so a naive
    projection-only read would never notice it's gone; the missing check
    runs against the file's full column list (`pq.read_schema`), not the
    narrowed read, so it still raises.
    """
    table = build_tossd_table(2019, n_rows=5, seed=0).drop_columns(
        ["ProjectDescription"]
    )
    _setup_years(monkeypatch, tmp_path, {2019: table})

    with pytest.raises(SchemaDriftError, match="ProjectDescription"):
        query.get_tossd(years=2019, columns="minimal")


def test_extra_column_warns_under_minimal_projection_even_though_not_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An unrecognised extra column still warns once under a narrow projection, but stays absent.

    Unlike `columns="all"` (F1's own passthrough contract), a preset never
    surfaces the extra in its output -- it just was never read.
    """
    table = build_tossd_table(2019, n_rows=5, seed=0)
    with_extra = table.append_column(
        "SurpriseColumnUnderProjection", pa.array(["x"] * table.num_rows)
    )
    _setup_years(monkeypatch, tmp_path, {2019: with_extra})

    with pytest.warns(UserWarning, match="SurpriseColumnUnderProjection"):
        df = query.get_tossd(years=2019, columns="minimal")

    assert "SurpriseColumnUnderProjection" not in df.columns


def test_columns_all_preserves_schema_drift_extra_columns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A schema-drift passthrough column survives columns="all" and export(), not presets/lists.

    `schema.apply_schema` passes an unknown extra column through raw (with a
    warning), documented as "only visible with columns='all'" -- this checks
    that promise actually holds end to end, for both `get_tossd` and
    `export()`.
    """
    table = build_tossd_table(2019, n_rows=10, seed=0)
    with_extra = table.append_column(
        "SurpriseNewColumn", pa.array(["x"] * table.num_rows)
    )
    _setup_years(monkeypatch, tmp_path, {2019: with_extra})

    with pytest.warns(UserWarning, match="SurpriseNewColumn"):
        df_all = query.get_tossd(years=2019, columns="all")
    assert "SurpriseNewColumn" in df_all.columns
    assert df_all["SurpriseNewColumn"].tolist() == ["x"] * 10
    # schema columns first, extras appended before the always-forced derived
    # columns (is_aggregate/unit).
    assert list(df_all.columns)[-3:] == ["SurpriseNewColumn", "is_aggregate", "unit"]

    df_minimal = query.get_tossd(years=2019, columns="minimal")
    assert "SurpriseNewColumn" not in df_minimal.columns

    df_analysis = query.get_tossd(years=2019, columns="analysis")
    assert "SurpriseNewColumn" not in df_analysis.columns

    df_explicit = query.get_tossd(years=2019, columns=["provider_code"])
    assert "SurpriseNewColumn" not in df_explicit.columns

    destination = tossd_reader.export(tmp_path / "out", years=2019)
    written = pq.read_table(destination)
    assert "SurpriseNewColumn" in written.column_names
    assert written.column("SurpriseNewColumn").to_pylist() == ["x"] * 10


def test_unknown_column_name_raises_value_error_with_suggestion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An unrecognised columns= entry raises ValueError naming it and a close match."""
    _setup_default_years(monkeypatch, tmp_path, [2019], n_rows=5)

    with pytest.raises(ValueError, match="provider_cod") as excinfo:
        query.get_tossd(years=2019, columns=["provider_cod"])  # typo

    assert "provider_code" in str(excinfo.value)


# --- units ------------------------------------------------------------------


def test_units_usd_million_divides_exact_8_amount_columns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """units='usd_million' divides exactly the 8 is_usd_thousand_amount columns by 1000."""
    _setup_default_years(monkeypatch, tmp_path, [2019], n_rows=30)

    thousands = query.get_tossd(years=2019, units="usd_thousand")
    millions = query.get_tossd(years=2019, units="usd_million")

    amount_columns = [
        "usd_commitment",
        "usd_commitment_deflated",
        "usd_disbursement",
        "usd_disbursement_deflated",
        "usd_reflow",
        "usd_reflow_deflated",
        "usd_amount_mobilised",
        "usd_amount_mobilised_deflated",
    ]
    for name in amount_columns:
        pd.testing.assert_series_equal(
            millions[name], thousands[name] / 1000, check_names=False
        )
    # A non-amount numeric column is untouched.
    pd.testing.assert_series_equal(
        millions["salary_cost"], thousands["salary_cost"], check_names=False
    )


def test_unit_column_travels_and_survives_minimal_preset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The derived `unit` column carries the right value even under columns='minimal'."""
    _setup_default_years(monkeypatch, tmp_path, [2019], n_rows=5)

    df = query.get_tossd(years=2019, units="usd_million", columns="minimal")

    assert set(df["unit"]) == {"usd_million"}
    assert isinstance(df["unit"].dtype, pd.CategoricalDtype)


def test_invalid_units_raises_value_error() -> None:
    """An unrecognised units= value raises ValueError before any fetch happens."""
    with pytest.raises(ValueError, match="units"):
        query.get_tossd(units="usd_billion")


# --- is_aggregate ------------------------------------------------------------


def test_is_aggregate_matches_provider_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """is_aggregate is True exactly for provider_code == 0 rows, always present."""
    _setup_default_years(monkeypatch, tmp_path, [2019], n_rows=10)

    df = query.get_tossd(years=2019)

    assert (df.loc[df["provider_code"] == 0, "is_aggregate"]).all()
    assert not (df.loc[df["provider_code"] != 0, "is_aggregate"]).any()


# --- empty result --------------------------------------------------------------


def test_empty_result_after_filtering_warns_and_returns_typed_frame(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A filter matching nothing returns an empty, correctly-typed frame, with one warning."""
    _setup_default_years(monkeypatch, tmp_path, [2019], n_rows=10)

    with pytest.warns(UserWarning, match="no rows"):
        df = query.get_tossd(years=2019, providers=9999)

    assert df.empty
    assert "provider_code" in df.columns
    assert str(df["provider_code"].dtype) in {"int16", "Int16"}


# --- unknown decode codes: aggregated end-of-query warning --------------------


def test_unknown_parent_channel_code_warns_aggregated_and_passes_through_null(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A parent_channel_code absent from the channel codelist decodes to null, warns once."""
    table = _with_bad_parent_channel_code(build_tossd_table(2019, n_rows=20, seed=0))
    _setup_years(monkeypatch, tmp_path, {2019: table})

    with pytest.warns(UserWarning, match="not in the packaged codelists"):
        df = query.get_tossd(years=2019)

    assert pd.isna(df.loc[0, "parent_channel_name"])

    # Same unknown code, same session: no repeat warning (aggregated per new
    # code only). filterwarnings=["error"] means an unexpected repeat would
    # fail this test outright.
    query.get_tossd(years=2019)


def test_known_parent_channel_code_decodes_to_channel_codelist_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A parent_channel_code present in the packaged channel codelist decodes to its label."""
    table = _with_known_parent_channel_code(build_tossd_table(2019, n_rows=20, seed=0))
    _setup_years(monkeypatch, tmp_path, {2019: table})

    df = query.get_tossd(years=2019)

    assert df.loc[0, "parent_channel_name"] == "Provider Government"


def test_reset_for_tests_clears_unknown_code_warn_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`_reset_for_tests` clears the unknown-decode-code warn state too."""
    table = _with_bad_parent_channel_code(build_tossd_table(2019, n_rows=20, seed=0))
    _setup_years(monkeypatch, tmp_path, {2019: table})

    with pytest.warns(UserWarning, match="not in the packaged codelists"):
        query.get_tossd(years=2019)

    query._reset_for_tests()

    with pytest.warns(UserWarning, match="not in the packaged codelists"):
        query.get_tossd(years=2019)


# --- warning stacklevels point at the caller, not query.py's own frames -------


def test_empty_result_warning_points_at_the_caller(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _setup_default_years(monkeypatch, tmp_path, [2019], n_rows=5)

    with pytest.warns(UserWarning) as record:
        query.get_tossd(years=2019, providers=9999)

    assert record[0].filename.endswith("test_query.py")


def test_subpillar_narrowed_warning_points_at_the_caller(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _setup_default_years(monkeypatch, tmp_path, [2023, 2024], n_rows=10)

    # Narrowing default years always ends up including 2023, so the coverage
    # warning also fires in the same call; `record[0]` is still the
    # narrowing warning since it's issued first.
    with pytest.warns(UserWarning) as record:
        query.get_tossd(pillars="II.A")
    assert "narrowing" in str(record[0].message)

    assert record[0].filename.endswith("test_query.py")


def test_unknown_decode_code_warning_points_at_the_caller(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    table = _with_bad_parent_channel_code(build_tossd_table(2019, n_rows=10, seed=0))
    _setup_years(monkeypatch, tmp_path, {2019: table})

    with pytest.warns(UserWarning, match="not in the packaged codelists") as record:
        query.get_tossd(years=2019)

    assert record[0].filename.endswith("test_query.py")
