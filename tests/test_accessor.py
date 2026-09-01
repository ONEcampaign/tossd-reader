"""Tests for the `df.tossd` accessor: `tossd_reader._accessor.TossdAccessor`."""

from __future__ import annotations

import subprocess
import sys

import pandas as pd
import pytest

from tossd_reader import analysis, verbs

# --- registration -----------------------------------------------------------------


def test_accessor_registers_after_analysis_import_not_on_bare_import() -> None:
    """`df.tossd` is unavailable after a bare `import tossd_reader`, available once analysis.py loads."""
    script = (
        "import pandas as pd\n"
        "import tossd_reader\n"
        "df = pd.DataFrame({'a': [1]})\n"
        "assert not hasattr(df, 'tossd'), "
        "'tossd accessor must not register on a bare import'\n"
        "import tossd_reader.analysis\n"
        "assert hasattr(df, 'tossd'), "
        "'tossd accessor must register once analysis.py is imported'\n"
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


def test_registering_from_both_query_and_analysis_emits_no_pandas_warning() -> None:
    """query.py and analysis.py both import `_accessor` for its side effect; only one registration fires.

    `_accessor.py`'s module body -- where `register_dataframe_accessor` runs
    -- executes exactly once no matter how many importers pull it in, so a
    fresh interpreter importing both `query` and `analysis` must raise no
    warning at all (`warnings.simplefilter('error')` turns any into a
    failure).
    """
    script = (
        "import warnings\n"
        "warnings.simplefilter('error')\n"
        "import tossd_reader.query\n"
        "import tossd_reader.analysis\n"
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


# --- summary() ----------------------------------------------------------------


def _summary_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "year": [2019, 2019, 2020, 2020, 2020],
            "tossd_pillar": [1, 1, 2, 2, 0],
            "tossd_subpillar": [pd.NA, pd.NA, "21", "22", pd.NA],
            "is_aggregate": [False, True, False, False, False],
            "unit": ["usd_thousand"] * 5,
            "usd_disbursement": [1.0, 2.0, 3.0, 4.0, 5.0],
        }
    )


def test_summary_exact_fields_on_a_known_frame() -> None:
    """`summary()` reports years, sizes, per-pillar row counts, unit, and column count."""
    df = _summary_df()

    result = df.tossd.summary()

    assert result["years"] == (2019, 2020)
    assert result["n_rows"] == 5
    assert result["n_aggregate_rows"] == 1
    assert result["n_pillar_0_rows"] == 1
    assert result["n_pillar_1_rows"] == 2
    assert result["n_pillar_2_rows"] == 2
    assert result["unit"] == "usd_thousand"
    assert result["n_columns"] == 6
    assert list(result.index) == [
        "years",
        "n_rows",
        "n_aggregate_rows",
        "n_pillar_0_rows",
        "n_pillar_1_rows",
        "n_pillar_2_rows",
        "unit",
        "n_columns",
    ]


def test_summary_unit_multiple_values_reports_a_sorted_tuple() -> None:
    """More than one distinct `unit` value: the field carries a sorted tuple, not a scalar."""
    df = _summary_df()
    df.loc[0, "unit"] = "usd"

    result = df.tossd.summary()

    assert result["unit"] == ("usd", "usd_thousand")


def test_summary_empty_frame() -> None:
    """A 0-row (but correctly columned) frame: empty years/unit, zero counts, no pillar entries."""
    df = pd.DataFrame(
        {
            "year": pd.Series([], dtype="Int64"),
            "tossd_pillar": pd.Series([], dtype="Int64"),
            "tossd_subpillar": pd.Series([], dtype="object"),
            "is_aggregate": pd.Series([], dtype="bool"),
            "unit": pd.Series([], dtype="object"),
        }
    )

    result = df.tossd.summary()

    assert result["years"] == ()
    assert result["n_rows"] == 0
    assert result["n_aggregate_rows"] == 0
    assert result["unit"] == ()
    assert result["n_columns"] == 5
    assert list(result.index) == [
        "years",
        "n_rows",
        "n_aggregate_rows",
        "unit",
        "n_columns",
    ]


def test_summary_missing_forced_column_raises() -> None:
    """A frame missing one of `FORCED_COLUMNS` (here, `unit`) raises, naming it."""
    df = _summary_df().drop(columns=["unit"])

    with pytest.raises(ValueError, match="unit"):
        df.tossd.summary()


# --- exclude_aggregates() ------------------------------------------------------


def test_exclude_aggregates_drops_rows_and_copies_attrs() -> None:
    """Drops `is_aggregate` rows; `df.attrs` propagates onto the result (A7)."""
    df = pd.DataFrame({"provider_code": [1, 0], "is_aggregate": [False, True]})
    df.attrs["tossd_reader"] = {"years": [2024]}

    result = df.tossd.exclude_aggregates()

    assert result["provider_code"].tolist() == [1]
    assert result.attrs == {"tossd_reader": {"years": [2024]}}


def test_exclude_aggregates_missing_is_aggregate_raises() -> None:
    """No `is_aggregate` column: teaching error, naming it."""
    df = pd.DataFrame({"provider_code": [1]})

    with pytest.raises(ValueError, match="is_aggregate"):
        df.tossd.exclude_aggregates()


def test_exclude_aggregates_does_not_mutate_input() -> None:
    """Leaves the caller's original frame unchanged."""
    df = pd.DataFrame({"provider_code": [1, 0], "is_aggregate": [False, True]})
    original = df.copy()

    df.tossd.exclude_aggregates()

    pd.testing.assert_frame_equal(df, original)


# --- groupby_entity() -----------------------------------------------------------


def test_groupby_entity_sums_match_a_manual_groupby() -> None:
    """The default `dimension="provider"` groupby matches a hand-rolled equivalent."""
    df = pd.DataFrame(
        {
            "provider_code": [1, 1, 2],
            "provider_name": ["A", "A", "B"],
            "usd_disbursement": [10.0, 20.0, 30.0],
        }
    )

    grouped = df.tossd.groupby_entity()["usd_disbursement"].sum()
    manual = df.groupby(["provider_code", "provider_name"], observed=True)[
        "usd_disbursement"
    ].sum()

    pd.testing.assert_series_equal(grouped, manual)


def test_groupby_entity_honours_dimension_kwarg() -> None:
    """`dimension=` groups by any `{dimension}_code`/`{dimension}_name` pair."""
    df = pd.DataFrame(
        {
            "sector_code": [110, 110, 311],
            "sector_name": ["Education", "Education", "Agriculture"],
            "usd_disbursement": [5.0, 5.0, 20.0],
        }
    )

    grouped = df.tossd.groupby_entity(dimension="sector")["usd_disbursement"].sum()

    assert grouped.loc[(110, "Education")] == 10.0


def test_groupby_entity_missing_columns_raises() -> None:
    """No `provider_code`/`provider_name`: teaching error, naming them."""
    df = pd.DataFrame({"other": [1]})

    with pytest.raises(ValueError, match="provider_code"):
        df.tossd.groupby_entity()


# --- verbs.py delegates: parity with the canonical function ------------------------


def test_rank_entities_delegate_matches_canonical() -> None:
    df = pd.DataFrame(
        {
            "provider_code": [1, 2],
            "provider_name": ["A", "B"],
            "usd_disbursement": [10.0, 20.0],
            "is_aggregate": [False, False],
        }
    )

    pd.testing.assert_frame_equal(df.tossd.rank_entities(), verbs.rank_entities(df))


def test_rank_entities_delegate_passes_through_kwargs() -> None:
    df = pd.DataFrame(
        {
            "provider_code": [1, 2, 3],
            "provider_name": ["A", "B", "C"],
            "usd_disbursement": [10.0, 20.0, 30.0],
            "is_aggregate": [False, False, False],
        }
    )

    pd.testing.assert_frame_equal(
        df.tossd.rank_entities(top=1), verbs.rank_entities(df, top=1)
    )


def _compare_years_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "year": [2019, 2019, 2020, 2020],
            "provider_code": [1, 2, 1, 2],
            "provider_name": ["A", "B", "A", "B"],
            "usd_disbursement_deflated": [10.0, 20.0, 15.0, 25.0],
            "is_aggregate": [False, False, False, False],
        }
    )


def test_compare_years_delegate_matches_canonical() -> None:
    df = _compare_years_df()

    accessor_result = df.tossd.compare_years()
    canonical_result = verbs.compare_years(df)

    pd.testing.assert_frame_equal(accessor_result, canonical_result)
    pd.testing.assert_frame_equal(
        accessor_result.attrs["structural_breaks"],
        canonical_result.attrs["structural_breaks"],
    )


def test_compare_years_delegate_passes_through_kwargs() -> None:
    df = _compare_years_df()

    pd.testing.assert_frame_equal(
        df.tossd.compare_years(cohort="all"), verbs.compare_years(df, cohort="all")
    )


def _sdg_totals_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "usd_disbursement": [100.0, 90.0],
            "sdg_codes_raw": ["5", "4.2"],
            "is_aggregate": [False, False],
        }
    )


def test_sdg_totals_delegate_matches_canonical() -> None:
    df = _sdg_totals_df()

    pd.testing.assert_frame_equal(df.tossd.sdg_totals(), verbs.sdg_totals(df))


def test_sdg_totals_delegate_passes_through_kwargs() -> None:
    df = _sdg_totals_df()

    pd.testing.assert_frame_equal(
        df.tossd.sdg_totals(level="code"), verbs.sdg_totals(df, level="code")
    )


def _keyword_totals_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "usd_disbursement": [10.0, 20.0],
            "keywords_raw": ["#GENDER", "#MITIGATION"],
            "is_aggregate": [False, False],
        }
    )


def test_keyword_totals_delegate_matches_canonical() -> None:
    df = _keyword_totals_df()

    pd.testing.assert_frame_equal(df.tossd.keyword_totals(), verbs.keyword_totals(df))


def test_keyword_totals_delegate_passes_through_kwargs() -> None:
    df = _keyword_totals_df()

    pd.testing.assert_frame_equal(
        df.tossd.keyword_totals(markers="gender"),
        verbs.keyword_totals(df, markers="gender"),
    )


def _subpillar_breakdown_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "year": [2023, 2023],
            "tossd_pillar": [2, 2],
            "tossd_subpillar": ["21", "22"],
            "usd_disbursement": [10.0, 20.0],
            "is_aggregate": [False, False],
        }
    )


def test_subpillar_breakdown_delegate_matches_canonical() -> None:
    df = _subpillar_breakdown_df()

    pd.testing.assert_frame_equal(
        df.tossd.subpillar_breakdown(), verbs.subpillar_breakdown(df)
    )


# --- analysis.py delegates: parity with the canonical function ---------------------


def test_add_iso3_delegate_matches_canonical() -> None:
    df = pd.DataFrame({"provider_code": [1]})

    pd.testing.assert_frame_equal(df.tossd.add_iso3(), analysis.add_iso3(df))


def test_add_recipient_group_delegate_matches_canonical() -> None:
    df = pd.DataFrame({"recipient_code": [225]})

    pd.testing.assert_frame_equal(
        df.tossd.add_recipient_group(), analysis.add_recipient_group(df)
    )


def test_add_recipient_group_delegate_passes_through_scheme() -> None:
    df = pd.DataFrame({"recipient_code": [225]})

    pd.testing.assert_frame_equal(
        df.tossd.add_recipient_group(scheme="region"),
        analysis.add_recipient_group(df, scheme="region"),
    )


def _instrument_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "finance_instrument_code": pd.array([110], dtype="Int16"),
            "concessionality_flag": pd.array([pd.NA], dtype="Int8"),
        }
    )


def test_add_instrument_group_delegate_matches_canonical() -> None:
    df = _instrument_frame()

    pd.testing.assert_frame_equal(
        df.tossd.add_instrument_group(), analysis.add_instrument_group(df)
    )


def test_extract_keywords_delegate_matches_canonical() -> None:
    df = pd.DataFrame({"keywords_raw": ["#GENDER"]})

    pd.testing.assert_frame_equal(
        df.tossd.extract_keywords(), analysis.extract_keywords(df)
    )


def test_explode_sdg_delegate_matches_canonical() -> None:
    df = pd.DataFrame({"sdg_codes_raw": ["5;13"]})

    pd.testing.assert_frame_equal(df.tossd.explode_sdg(), analysis.explode_sdg(df))


def test_explode_sdg_delegate_passes_through_value() -> None:
    """`value=` is forwarded, adding `{value}_weighted` -- same as calling the function directly."""
    df = pd.DataFrame({"sdg_codes_raw": ["5;13"], "usd_disbursement": [100.0]})

    pd.testing.assert_frame_equal(
        df.tossd.explode_sdg(value="usd_disbursement"),
        analysis.explode_sdg(df, value="usd_disbursement"),
    )


def test_filter_provider_costs_delegate_matches_canonical() -> None:
    df = pd.DataFrame({"tossd_pillar": [2, 1], "sector_code": [910, 110]})

    pd.testing.assert_frame_equal(
        df.tossd.filter_provider_costs(), analysis.filter_provider_costs(df)
    )


# --- df.tossd surfaces the underlying teaching errors on a malformed frame ---------


def test_delegate_missing_columns_raises_the_canonical_teaching_error() -> None:
    """A delegate on a frame missing required columns raises the same error its function would."""
    df = pd.DataFrame({"other": [1]})

    with pytest.raises(ValueError, match="provider_code"):
        df.tossd.rank_entities()
