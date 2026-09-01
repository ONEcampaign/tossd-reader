"""Unit tests for the aggregation-verb layer: `tossd_reader.verbs`."""

from __future__ import annotations

import pandas as pd
import pytest

from tossd_reader import verbs

# --- rank_entities ---------------------------------------------------------------


def test_rank_entities_missing_columns_raises_with_analysis_hint() -> None:
    """Missing `{dimension}_code`/`{dimension}_name` names both columns, with the preset hint."""
    df = pd.DataFrame({"usd_disbursement": [1.0], "is_aggregate": [False]})

    with pytest.raises(ValueError, match="sector_code") as excinfo:
        verbs.rank_entities(df, dimension="sector")

    message = str(excinfo.value)
    assert "sector_name" in message
    assert "columns='analysis'" in message


def test_rank_entities_value_not_numeric_raises() -> None:
    """A non-numeric `value=` column raises, naming its actual dtype."""
    df = pd.DataFrame(
        {
            "provider_code": [1],
            "provider_name": ["A"],
            "usd_disbursement": ["not-a-number"],
            "is_aggregate": [False],
        }
    )

    with pytest.raises(ValueError, match="numeric") as excinfo:
        verbs.rank_entities(df)
    assert "usd_disbursement" in str(excinfo.value)


def test_rank_entities_missing_is_aggregate_raises_naming_the_default() -> None:
    """No `is_aggregate` column, `include_aggregates=False` (the default): teaching error."""
    df = pd.DataFrame(
        {"provider_code": [1], "provider_name": ["A"], "usd_disbursement": [10.0]}
    )

    with pytest.raises(ValueError, match="is_aggregate"):
        verbs.rank_entities(df)


def test_rank_entities_include_aggregates_true_skips_the_is_aggregate_check() -> None:
    """`include_aggregates=True` needs no `is_aggregate` column at all."""
    df = pd.DataFrame(
        {"provider_code": [1], "provider_name": ["A"], "usd_disbursement": [10.0]}
    )

    result = verbs.rank_entities(df, include_aggregates=True)

    assert result["usd_disbursement"].tolist() == [10.0]


def test_rank_entities_correctness_and_share_pct() -> None:
    """Hand-computed totals, shares, and exclusion of the aggregate row."""
    df = pd.DataFrame(
        {
            "provider_code": [1, 1, 2, 0],
            "provider_name": ["A", "A", "B", "Aggregate"],
            "usd_disbursement": [10.0, 20.0, 30.0, 999.0],
            "is_aggregate": [False, False, False, True],
        }
    )

    result = verbs.rank_entities(df)

    assert list(result.columns) == [
        "provider_code",
        "provider_name",
        "usd_disbursement",
        "share_pct",
        "rank",
    ]
    row_b = result.loc[result["provider_name"] == "B"].iloc[0]
    row_a = result.loc[result["provider_name"] == "A"].iloc[0]
    assert row_b["usd_disbursement"] == 30.0
    assert row_a["usd_disbursement"] == 30.0
    # 30 + 30 = 60 total (999 excluded as an aggregate row).
    assert row_b["share_pct"] == pytest.approx(50.0)
    assert row_a["share_pct"] == pytest.approx(50.0)


def test_rank_entities_ties_get_competition_min_rank() -> None:
    """Two entities tied for the top total both get rank 1; the next gets rank 3, not 2."""
    df = pd.DataFrame(
        {
            "provider_code": [1, 2, 3],
            "provider_name": ["A", "B", "C"],
            "usd_disbursement": [100.0, 100.0, 50.0],
            "is_aggregate": [False, False, False],
        }
    )

    result = verbs.rank_entities(df)

    ranks_by_name = dict(zip(result["provider_name"], result["rank"], strict=True))
    assert ranks_by_name["A"] == 1
    assert ranks_by_name["B"] == 1
    assert ranks_by_name["C"] == 3


def test_rank_entities_top_truncates_after_ranking() -> None:
    """`top=` keeps the highest-ranked rows; rank numbers reflect the full set, not the slice."""
    df = pd.DataFrame(
        {
            "provider_code": [1, 2, 3, 4],
            "provider_name": ["A", "B", "C", "D"],
            "usd_disbursement": [100.0, 100.0, 50.0, 10.0],
            "is_aggregate": [False, False, False, False],
        }
    )

    result = verbs.rank_entities(df, top=2)

    assert len(result) == 2
    assert set(result["rank"]) == {1}
    assert set(result["provider_name"]) == {"A", "B"}


def test_rank_entities_n_activities_excludes_0000_placeholder() -> None:
    """`n_activities` counts distinct `tossd_id`, excluding the `"0000"` bundled-line placeholder."""
    df = pd.DataFrame(
        {
            "provider_code": [1, 1, 1],
            "provider_name": ["A", "A", "A"],
            "usd_disbursement": [10.0, 20.0, 30.0],
            "tossd_id": ["t1", "t2", "0000"],
            "is_aggregate": [False, False, False],
        }
    )

    result = verbs.rank_entities(df)

    assert result["n_activities"].iloc[0] == 2


def test_rank_entities_n_activities_zero_when_only_0000_rows() -> None:
    """A group whose only `tossd_id` values are `"0000"` counts zero activities, not an error."""
    df = pd.DataFrame(
        {
            "provider_code": [1, 1],
            "provider_name": ["A", "A"],
            "usd_disbursement": [10.0, 20.0],
            "tossd_id": ["0000", "0000"],
            "is_aggregate": [False, False],
        }
    )

    result = verbs.rank_entities(df)

    assert result["n_activities"].iloc[0] == 0


def test_rank_entities_omits_n_activities_when_tossd_id_absent() -> None:
    """No `tossd_id` column in `df`: `n_activities` is simply omitted, not an error."""
    df = pd.DataFrame(
        {
            "provider_code": [1],
            "provider_name": ["A"],
            "usd_disbursement": [10.0],
            "is_aggregate": [False],
        }
    )

    result = verbs.rank_entities(df)

    assert "n_activities" not in result.columns


def test_rank_entities_works_for_an_arbitrary_dimension() -> None:
    """Any `{dimension}_code`/`{dimension}_name` pair works, not just provider."""
    df = pd.DataFrame(
        {
            "sector_code": [110, 110, 311],
            "sector_name": ["Education", "Education", "Agriculture"],
            "usd_disbursement": [5.0, 5.0, 20.0],
            "is_aggregate": [False, False, False],
        }
    )

    result = verbs.rank_entities(df, dimension="sector")

    assert set(result["sector_name"]) == {"Education", "Agriculture"}
    row = result.loc[result["sector_name"] == "Education"].iloc[0]
    assert row["usd_disbursement"] == 10.0


def test_rank_entities_empty_input_returns_empty_typed_frame() -> None:
    """An empty input yields an empty, correctly-columned result, silently."""
    df = pd.DataFrame(
        {
            "provider_code": pd.Series([], dtype="Int64"),
            "provider_name": pd.Series([], dtype="object"),
            "usd_disbursement": pd.Series([], dtype="float64"),
            "is_aggregate": pd.Series([], dtype="bool"),
        }
    )

    result = verbs.rank_entities(df)

    assert result.empty
    assert list(result.columns) == [
        "provider_code",
        "provider_name",
        "usd_disbursement",
        "share_pct",
        "rank",
    ]


def test_rank_entities_copies_attrs() -> None:
    """`df.attrs` propagates onto the result (A7)."""
    df = pd.DataFrame(
        {"provider_code": [1], "provider_name": ["A"], "usd_disbursement": [1.0]}
    )
    df.attrs["tossd_reader"] = {"years": [2024]}

    result = verbs.rank_entities(df, include_aggregates=True)

    assert result.attrs == {"tossd_reader": {"years": [2024]}}


def test_rank_entities_does_not_mutate_input() -> None:
    """Ranking leaves the caller's original frame unchanged."""
    df = pd.DataFrame(
        {
            "provider_code": [1, 0],
            "provider_name": ["A", "Aggregate"],
            "usd_disbursement": [10.0, 20.0],
            "is_aggregate": [False, True],
            "tossd_id": ["t1", "0000"],
        }
    )
    original = df.copy()

    verbs.rank_entities(df)

    pd.testing.assert_frame_equal(df, original)


# --- compare_years -----------------------------------------------------------------


def _compare_years_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "year": [2019, 2019, 2020, 2020, 2021],
            "provider_code": [1, 2, 1, 2, 1],
            "provider_name": ["A", "B", "A", "B", "A"],
            "usd_disbursement_deflated": [10.0, 20.0, 15.0, 25.0, 30.0],
            "is_aggregate": [False, False, False, False, False],
        }
    )


def test_compare_years_missing_columns_raises() -> None:
    """Missing `provider_code`/`provider_name`/`year`/`value` is named."""
    df = pd.DataFrame({"other": [1]})

    with pytest.raises(ValueError, match="provider_code"):
        verbs.compare_years(df)


def test_compare_years_value_not_numeric_raises() -> None:
    """A non-numeric `value=` column raises."""
    df = pd.DataFrame(
        {
            "year": [2019],
            "provider_code": [1],
            "provider_name": ["A"],
            "usd_disbursement_deflated": ["x"],
        }
    )

    with pytest.raises(ValueError, match="numeric"):
        verbs.compare_years(df)


def test_compare_years_bad_cohort_raises() -> None:
    """An unrecognised `cohort=` raises, naming the two valid values."""
    df = _compare_years_df()

    with pytest.raises(ValueError, match="cohort"):
        verbs.compare_years(df, cohort="bogus")


def test_compare_years_missing_is_aggregate_raises() -> None:
    """No `is_aggregate` and `include_aggregates=False` (the default): teaching error."""
    df = _compare_years_df().drop(columns=["is_aggregate"])

    with pytest.raises(ValueError, match="is_aggregate"):
        verbs.compare_years(df)


def test_compare_years_consistent_cohort_correctness() -> None:
    """`cohort="consistent"` restricts to providers present every year; hand-computed totals."""
    df = _compare_years_df()

    result = verbs.compare_years(df)

    # Only provider A (1) reports in every one of 2019/2020/2021; B (only
    # 2019/2020) is excluded entirely.
    assert result["usd_disbursement_deflated"].tolist() == [10.0, 15.0, 30.0]
    assert (result["n_providers"] == 1).all()
    assert pd.isna(result["pct_change"].iloc[0])
    assert result["pct_change"].iloc[1] == pytest.approx(50.0)
    assert result["pct_change"].iloc[2] == pytest.approx(100.0)


def test_compare_years_all_cohort_correctness() -> None:
    """`cohort="all"` counts every row; `n_providers` is the year's own distinct-pair count."""
    df = _compare_years_df()

    result = verbs.compare_years(df, cohort="all")

    assert result["usd_disbursement_deflated"].tolist() == [30.0, 40.0, 30.0]
    assert result["n_providers"].tolist() == [2, 2, 1]


def test_compare_years_empty_consistent_cohort_raises_teaching_cohort_all() -> None:
    """No provider pair spans every year: raises, naming `cohort='all'` as the fix."""
    df = pd.DataFrame(
        {
            "year": [2019, 2020],
            "provider_code": [1, 2],
            "provider_name": ["A", "B"],
            "usd_disbursement_deflated": [10.0, 20.0],
            "is_aggregate": [False, False],
        }
    )

    with pytest.raises(ValueError, match="cohort='all'"):
        verbs.compare_years(df)


def test_compare_years_single_year_pct_change_is_na() -> None:
    """A single-year frame works; `pct_change` is NA for that one row."""
    df = pd.DataFrame(
        {
            "year": [2019, 2019],
            "provider_code": [1, 2],
            "provider_name": ["A", "B"],
            "usd_disbursement_deflated": [10.0, 20.0],
            "is_aggregate": [False, False],
        }
    )

    result = verbs.compare_years(df)

    assert len(result) == 1
    assert pd.isna(result["pct_change"].iloc[0])


def test_compare_years_empty_input_returns_empty_typed_frame() -> None:
    """An empty input (after exclusion) yields an empty result, silently -- no cohort error."""
    df = pd.DataFrame(
        {
            "year": pd.Series([], dtype="Int64"),
            "provider_code": pd.Series([], dtype="Int64"),
            "provider_name": pd.Series([], dtype="object"),
            "usd_disbursement_deflated": pd.Series([], dtype="float64"),
            "is_aggregate": pd.Series([], dtype="bool"),
        }
    )

    result = verbs.compare_years(df)

    assert result.empty
    assert list(result.columns) == [
        "year",
        "usd_disbursement_deflated",
        "n_providers",
        "pct_change",
    ]


def test_compare_years_structural_breaks_attrs_attachment() -> None:
    """`result.attrs["structural_breaks"]` carries the breaks intersecting the covered years."""
    df = _compare_years_df()

    result = verbs.compare_years(df)

    breaks = result.attrs["structural_breaks"]
    assert isinstance(breaks, pd.DataFrame)
    assert "reporters" in breaks["dimension"].tolist()


def test_compare_years_copies_attrs() -> None:
    """`df.attrs` propagates onto the result alongside `structural_breaks` (A7)."""
    df = _compare_years_df()
    df.attrs["tossd_reader"] = {"years": [2019, 2020, 2021]}

    result = verbs.compare_years(df)

    assert result.attrs["tossd_reader"] == {"years": [2019, 2020, 2021]}
    assert "structural_breaks" in result.attrs


def test_compare_years_does_not_mutate_input() -> None:
    """Comparing years leaves the caller's original frame unchanged."""
    df = _compare_years_df()
    original = df.copy()

    verbs.compare_years(df)

    pd.testing.assert_frame_equal(df, original)


# --- sdg_totals --------------------------------------------------------------


def _sdg_totals_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "tossd_id": ["a", "b", "c", "d"],
            "usd_disbursement": [100.0, 90.0, 50.0, 10.0],
            "sdg_codes_raw": ["5", "4.2", "5.0", "13;10.a;1"],
            "is_aggregate": [False, False, False, False],
        }
    )


def test_sdg_totals_missing_value_raises() -> None:
    """A missing `value=` column raises."""
    df = pd.DataFrame({"sdg_codes_raw": ["5"], "is_aggregate": [False]})

    with pytest.raises(ValueError, match="usd_disbursement"):
        verbs.sdg_totals(df)


def test_sdg_totals_value_not_numeric_raises() -> None:
    """A non-numeric `value=` column raises."""
    df = pd.DataFrame(
        {
            "usd_disbursement": ["x"],
            "sdg_codes_raw": ["5"],
            "is_aggregate": [False],
        }
    )

    with pytest.raises(ValueError, match="numeric"):
        verbs.sdg_totals(df)


def test_sdg_totals_missing_sdg_codes_raw_names_sdg_totals() -> None:
    """No `sdg_codes_raw`: sdg_totals() raises its own teaching error, naming itself."""
    df = pd.DataFrame({"usd_disbursement": [1.0], "is_aggregate": [False]})

    with pytest.raises(ValueError, match="sdg_codes_raw") as excinfo:
        verbs.sdg_totals(df)

    assert "sdg_totals()" in str(excinfo.value)


def test_sdg_totals_rejects_already_exploded_input() -> None:
    """`df` already carrying `explode_sdg`'s own output columns: sdg_totals() raises, naming itself."""
    df = _sdg_totals_df().assign(sdg_code=["5", "4.2", "5.0", "13"])

    with pytest.raises(ValueError, match="sdg_code") as excinfo:
        verbs.sdg_totals(df)

    assert "sdg_totals()" in str(excinfo.value)


def test_sdg_totals_bad_level_raises() -> None:
    """An unrecognised `level=` raises, naming the two valid values."""
    df = _sdg_totals_df()

    with pytest.raises(ValueError, match="level"):
        verbs.sdg_totals(df, level="bogus")


def test_sdg_totals_missing_is_aggregate_raises() -> None:
    """No `is_aggregate`, `include_aggregates=False` (the default): teaching error."""
    df = _sdg_totals_df().drop(columns=["is_aggregate"])

    with pytest.raises(ValueError, match="is_aggregate"):
        verbs.sdg_totals(df)


def test_sdg_totals_goal_level_correctness_and_weighting() -> None:
    """Hand-computed weighted goal totals: multi-tag rows split their amount across goals."""
    df = _sdg_totals_df()

    result = verbs.sdg_totals(df)

    by_goal = dict(zip(result["sdg_goal"], result["usd_disbursement"], strict=True))
    # goal 5: row a (bare "5", weight 1) -> 100, row c ("5.0" goal-level, weight
    # 1) -> 50.
    assert by_goal[5] == pytest.approx(150.0)
    # goal 4: row b ("4.2", weight 1) -> 90.
    assert by_goal[4] == pytest.approx(90.0)
    # goal 13/10/1: row d's three tokens each get weight 1/3 of 10.
    assert by_goal[13] == pytest.approx(10.0 / 3)
    assert by_goal[10] == pytest.approx(10.0 / 3)
    assert by_goal[1] == pytest.approx(10.0 / 3)

    # The weighted total equals the SDG-tagged subset (every row here is
    # tagged), not some other grand total.
    assert result["usd_disbursement"].sum() == pytest.approx(100 + 90 + 50 + 10)


def test_sdg_totals_code_level_keeps_goals_and_targets_apart() -> None:
    """`level="code"` groups by the exact published token, not the goal."""
    df = _sdg_totals_df()

    result = verbs.sdg_totals(df, level="code")

    assert set(result["sdg_code"]) == {"5", "4.2", "5.0", "13", "10.a", "1"}


def test_sdg_totals_ties_get_competition_min_rank() -> None:
    """Tied weighted totals share the lower rank number."""
    df = _sdg_totals_df()

    result = verbs.sdg_totals(df)

    ranks_by_goal = dict(zip(result["sdg_goal"], result["rank"], strict=True))
    # goals 1, 10, 13 are tied at 10/3 each -- all three share rank 3 (goals
    # 5 and 4 rank 1 and 2 ahead of them).
    assert ranks_by_goal[1] == ranks_by_goal[10] == ranks_by_goal[13] == 3


def test_sdg_totals_top_truncates_after_ranking() -> None:
    """`top=` keeps only the top-ranked rows after the full ranking runs."""
    df = _sdg_totals_df()

    result = verbs.sdg_totals(df, top=2)

    assert len(result) == 2
    assert set(result["sdg_goal"]) == {5, 4}


def test_sdg_totals_empty_input_returns_empty_typed_frame() -> None:
    """An empty input yields an empty, correctly-typed result, silently."""
    df = pd.DataFrame(
        {
            "usd_disbursement": pd.Series([], dtype="float64"),
            "sdg_codes_raw": pd.Series([], dtype="object"),
            "is_aggregate": pd.Series([], dtype="bool"),
        }
    )

    result = verbs.sdg_totals(df)

    assert result.empty
    assert list(result.columns) == ["sdg_goal", "usd_disbursement", "share_pct", "rank"]


def test_sdg_totals_copies_attrs() -> None:
    """`df.attrs` propagates onto the result (A7)."""
    df = _sdg_totals_df()
    df.attrs["tossd_reader"] = {"years": [2024]}

    result = verbs.sdg_totals(df)

    assert result.attrs == {"tossd_reader": {"years": [2024]}}


def test_sdg_totals_include_aggregates_true_keeps_aggregate_rows() -> None:
    """`include_aggregates=True` includes rows the default would drop."""
    df = pd.DataFrame(
        {
            "usd_disbursement": [100.0, 999.0],
            "sdg_codes_raw": ["5", "5"],
            "is_aggregate": [False, True],
        }
    )

    excluded = verbs.sdg_totals(df)
    included = verbs.sdg_totals(df, include_aggregates=True)

    assert excluded["usd_disbursement"].iloc[0] == pytest.approx(100.0)
    assert included["usd_disbursement"].iloc[0] == pytest.approx(1099.0)


def test_sdg_totals_does_not_mutate_input() -> None:
    """`sdg_totals` leaves the caller's original frame unchanged."""
    df = _sdg_totals_df()
    original = df.copy()

    verbs.sdg_totals(df)

    pd.testing.assert_frame_equal(df, original)


# --- keyword_totals ------------------------------------------------------------


def _keyword_totals_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "usd_disbursement": [10.0, 20.0, 30.0, 5.0],
            "keywords_raw": ["#GENDER", "#GENDER|#MITIGATION", "#MITIGATION", ""],
            "is_aggregate": [False, False, False, False],
        }
    )


def test_keyword_totals_missing_keywords_raw_generic_message() -> None:
    """No `keywords_raw` and no stale `kw_*` columns: the generic teaching error."""
    df = pd.DataFrame({"usd_disbursement": [1.0], "is_aggregate": [False]})

    with pytest.raises(ValueError, match="keywords_raw"):
        verbs.keyword_totals(df)


def test_keyword_totals_missing_keywords_raw_with_stale_kw_columns_names_them() -> None:
    """`kw_*` columns present but `keywords_raw` absent: message points at keeping keywords_raw."""
    df = pd.DataFrame({"kw_gender": [True], "usd_disbursement": [1.0]})

    with pytest.raises(ValueError, match="kw_gender") as excinfo:
        verbs.keyword_totals(df)

    assert "keywords_raw" in str(excinfo.value)


def test_keyword_totals_missing_value_raises() -> None:
    """A missing `value=` column raises."""
    df = pd.DataFrame({"keywords_raw": ["#GENDER"], "is_aggregate": [False]})

    with pytest.raises(ValueError, match="usd_disbursement"):
        verbs.keyword_totals(df)


def test_keyword_totals_value_not_numeric_raises() -> None:
    """A non-numeric `value=` column raises."""
    df = pd.DataFrame(
        {
            "keywords_raw": ["#GENDER"],
            "usd_disbursement": ["x"],
            "is_aggregate": [False],
        }
    )

    with pytest.raises(ValueError, match="numeric"):
        verbs.keyword_totals(df)


def test_keyword_totals_missing_is_aggregate_raises() -> None:
    """No `is_aggregate`, `include_aggregates=False` (the default): teaching error."""
    df = _keyword_totals_df().drop(columns=["is_aggregate"])

    with pytest.raises(ValueError, match="is_aggregate"):
        verbs.keyword_totals(df)


def test_keyword_totals_bad_marker_raises_with_suggestions() -> None:
    """An unrecognised marker name raises, listing the packaged vocabulary."""
    df = _keyword_totals_df()

    with pytest.raises(ValueError, match="gender") as excinfo:
        verbs.keyword_totals(df, markers="gendre")

    assert "not recognised" in str(excinfo.value)


def test_keyword_totals_accepts_marker_names_with_or_without_kw_prefix() -> None:
    """`"gender"` and `"kw_gender"` both resolve to the same marker."""
    df = _keyword_totals_df()

    bare = verbs.keyword_totals(df, markers="gender")
    prefixed = verbs.keyword_totals(df, markers="kw_gender")

    assert bare["marker"].tolist() == prefixed["marker"].tolist()
    assert bare["usd_disbursement"].tolist() == prefixed["usd_disbursement"].tolist()


def test_keyword_totals_deduplicates_repeated_markers() -> None:
    """The same marker requested twice (with and without prefix) yields one row for it."""
    df = _keyword_totals_df()

    result = verbs.keyword_totals(df, markers=["gender", "kw_gender"])

    assert result["marker"].tolist() == ["gender", "Combined"]


def test_keyword_totals_correctness_and_combined_union() -> None:
    """Hand-computed per-marker totals; Combined unions, avoiding the multi-tag double count."""
    df = _keyword_totals_df()

    result = verbs.keyword_totals(df, markers=["gender", "mitigation"])

    by_marker = dict(zip(result["marker"], result["usd_disbursement"], strict=True))
    # gender: rows 0 (10) and 1 (20) = 30. mitigation: rows 1 (20) and 2 (30) = 50.
    assert by_marker["gender"] == 30.0
    assert by_marker["mitigation"] == 50.0
    # Combined: union of rows {0, 1, 2} = 10 + 20 + 30 = 60, row 1's 20 counted
    # once, not twice -- less than the naive sum of the two marker rows (80).
    assert by_marker["Combined"] == 60.0
    assert by_marker["gender"] + by_marker["mitigation"] >= by_marker["Combined"]
    assert result["marker"].tolist()[-1] == "Combined"


def test_keyword_totals_n_rows_is_a_plain_row_count() -> None:
    """`n_rows` counts rows matching the mask, not distinct `tossd_id`."""
    df = _keyword_totals_df()

    result = verbs.keyword_totals(df, markers="gender")

    gender_row = result.loc[result["marker"] == "gender"].iloc[0]
    assert gender_row["n_rows"] == 2


def test_keyword_totals_markers_none_covers_all_twelve_plus_combined() -> None:
    """`markers=None` (the default) reports every packaged marker plus Combined."""
    df = _keyword_totals_df()

    result = verbs.keyword_totals(df)

    assert len(result) == 13
    assert result["marker"].iloc[-1] == "Combined"


def test_keyword_totals_empty_input_returns_empty_typed_frame() -> None:
    """An empty input yields an empty result, silently -- no marker rows at all."""
    df = pd.DataFrame(
        {
            "usd_disbursement": pd.Series([], dtype="float64"),
            "keywords_raw": pd.Series([], dtype="object"),
            "is_aggregate": pd.Series([], dtype="bool"),
        }
    )

    result = verbs.keyword_totals(df)

    assert result.empty
    assert list(result.columns) == ["marker", "usd_disbursement", "n_rows"]


def test_keyword_totals_include_aggregates_true_keeps_aggregate_rows() -> None:
    """`include_aggregates=True` includes rows the default would drop."""
    df = pd.DataFrame(
        {
            "usd_disbursement": [10.0, 999.0],
            "keywords_raw": ["#GENDER", "#GENDER"],
            "is_aggregate": [False, True],
        }
    )

    excluded = verbs.keyword_totals(df, markers="gender")
    included = verbs.keyword_totals(df, markers="gender", include_aggregates=True)

    assert excluded["usd_disbursement"].iloc[0] == 10.0
    assert included["usd_disbursement"].iloc[0] == 1009.0


def test_keyword_totals_copies_attrs() -> None:
    """`df.attrs` propagates onto the result (A7)."""
    df = _keyword_totals_df()
    df.attrs["tossd_reader"] = {"years": [2024]}

    result = verbs.keyword_totals(df)

    assert result.attrs == {"tossd_reader": {"years": [2024]}}


def test_keyword_totals_does_not_mutate_input() -> None:
    """`keyword_totals` leaves the caller's original frame unchanged."""
    df = _keyword_totals_df()
    original = df.copy()

    verbs.keyword_totals(df)

    pd.testing.assert_frame_equal(df, original)


# --- subpillar_breakdown -------------------------------------------------------


def _subpillar_breakdown_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "year": [2023, 2023, 2023, 2023, 2024, 2024],
            "tossd_pillar": [2, 2, 2, 1, 2, 2],
            "tossd_subpillar": ["21", "22", pd.NA, "1", "21", "21"],
            "usd_disbursement": [10.0, 20.0, 30.0, 999.0, 40.0, 60.0],
            "is_aggregate": [False, False, False, False, False, False],
        }
    )


def test_subpillar_breakdown_missing_columns_raises() -> None:
    """Missing `year`/`tossd_pillar`/`tossd_subpillar`/`value` is named."""
    df = pd.DataFrame({"other": [1]})

    with pytest.raises(ValueError, match="tossd_pillar"):
        verbs.subpillar_breakdown(df)


def test_subpillar_breakdown_value_not_numeric_raises() -> None:
    """A non-numeric `value=` column raises."""
    df = pd.DataFrame(
        {
            "year": [2023],
            "tossd_pillar": [2],
            "tossd_subpillar": ["21"],
            "usd_disbursement": ["x"],
            "is_aggregate": [False],
        }
    )

    with pytest.raises(ValueError, match="numeric"):
        verbs.subpillar_breakdown(df)


def test_subpillar_breakdown_missing_is_aggregate_raises() -> None:
    """No `is_aggregate`, `include_aggregates=False` (the default): teaching error."""
    df = _subpillar_breakdown_df().drop(columns=["is_aggregate"])

    with pytest.raises(ValueError, match="is_aggregate"):
        verbs.subpillar_breakdown(df)


def test_subpillar_breakdown_buckets_and_shares() -> None:
    """Hand-computed bucket totals, including the `"Untagged"` bucket and `coverage_pct`."""
    df = _subpillar_breakdown_df()

    result = verbs.subpillar_breakdown(df)

    year_2023 = result.loc[result["year"] == 2023].set_index("subpillar")
    assert year_2023.loc["II.A", "usd_disbursement"] == 10.0
    assert year_2023.loc["II.B", "usd_disbursement"] == 20.0
    assert year_2023.loc["Untagged", "usd_disbursement"] == 30.0
    # Pillar-1 row (999.0) never appears: total is 10 + 20 + 30 = 60.
    assert year_2023.loc["II.A", "share_pct"] == pytest.approx(10 / 60 * 100)
    # coverage_pct = (II.A + II.B) / total = 30/60 = 50%, repeated on every row.
    assert year_2023["coverage_pct"].tolist() == pytest.approx([50.0, 50.0, 50.0])


def test_subpillar_breakdown_full_grid_includes_empty_buckets() -> None:
    """Every year gets all three bucket rows, even a bucket with nothing in it that year."""
    df = _subpillar_breakdown_df()

    result = verbs.subpillar_breakdown(df)

    year_2024 = result.loc[result["year"] == 2024].set_index("subpillar")
    assert set(year_2024.index) == {"II.A", "II.B", "Untagged"}
    assert year_2024.loc["II.B", "usd_disbursement"] == 0.0
    assert year_2024.loc["Untagged", "usd_disbursement"] == 0.0
    assert year_2024.loc["II.A", "coverage_pct"] == pytest.approx(100.0)


def test_subpillar_breakdown_empty_input_when_no_pillar_2_rows() -> None:
    """A frame with no Pillar II rows yields an empty result, silently."""
    df = pd.DataFrame(
        {
            "year": [2023],
            "tossd_pillar": [1],
            "tossd_subpillar": [pd.NA],
            "usd_disbursement": [1.0],
            "is_aggregate": [False],
        }
    )

    result = verbs.subpillar_breakdown(df)

    assert result.empty
    assert list(result.columns) == [
        "year",
        "subpillar",
        "usd_disbursement",
        "share_pct",
        "coverage_pct",
    ]


def test_subpillar_breakdown_include_aggregates_true_keeps_aggregate_rows() -> None:
    """`include_aggregates=True` includes rows the default would drop."""
    df = pd.DataFrame(
        {
            "year": [2023, 2023],
            "tossd_pillar": [2, 2],
            "tossd_subpillar": ["21", "21"],
            "usd_disbursement": [10.0, 999.0],
            "is_aggregate": [False, True],
        }
    )

    excluded = verbs.subpillar_breakdown(df)
    included = verbs.subpillar_breakdown(df, include_aggregates=True)

    assert (
        excluded.loc[excluded["subpillar"] == "II.A", "usd_disbursement"].iloc[0]
        == 10.0
    )
    assert (
        included.loc[included["subpillar"] == "II.A", "usd_disbursement"].iloc[0]
        == 1009.0
    )


def test_subpillar_breakdown_copies_attrs() -> None:
    """`df.attrs` propagates onto the result (A7)."""
    df = _subpillar_breakdown_df()
    df.attrs["tossd_reader"] = {"years": [2023, 2024]}

    result = verbs.subpillar_breakdown(df)

    assert result.attrs == {"tossd_reader": {"years": [2023, 2024]}}


def test_subpillar_breakdown_does_not_mutate_input() -> None:
    """`subpillar_breakdown` leaves the caller's original frame unchanged."""
    df = _subpillar_breakdown_df()
    original = df.copy()

    verbs.subpillar_breakdown(df)

    pd.testing.assert_frame_equal(df, original)
