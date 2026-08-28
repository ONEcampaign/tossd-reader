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

from tests.fixtures import build_tossd_table
from tossd_reader import discovery, fetch, query
from tossd_reader.discovery import VintageInfo
from tossd_reader.exceptions import InvalidPillarError, UnknownCodeError

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


# --- D6: categorical dtype survives a multi-year concat -----------------------


def test_multi_year_concat_keeps_categorical_dtype(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A 3-year query keeps `provider_name` dictionary-encoded end to end."""
    years = [2019, 2020, 2021]
    _setup_default_years(monkeypatch, tmp_path, years, n_rows=20)

    df = query.get_tossd(years=years)

    assert isinstance(df["provider_name"].dtype, pd.CategoricalDtype)
    assert len(df) == 20 * len(years)


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
