"""Unit tests for the post-query analysis toolkit: `tossd_reader.analysis`."""

from __future__ import annotations

import subprocess
import sys
import warnings

import pandas as pd
import pytest

from tossd_reader import analysis, codelists, exceptions

# --- _require_columns hint (missing analysis-preset column names the fix) -----


def test_require_columns_hints_when_missing_column_is_analysis_preset_only() -> None:
    """A missing column that's only in the 'analysis' preset gets a re-query hint."""
    df = pd.DataFrame({"other": [1]})

    with pytest.raises(ValueError) as excinfo:
        analysis._require_columns(df, "sector_code", func_name="some_func")

    message = str(excinfo.value)
    assert "sector_code" in message
    assert "columns='analysis'" in message
    assert "columns= list" in message


def test_require_columns_no_hint_when_missing_column_is_not_analysis_preset() -> None:
    """A missing column outside the 'analysis' preset gets the generic message, no hint."""
    df = pd.DataFrame({"other": [1]})

    with pytest.raises(ValueError) as excinfo:
        analysis._require_columns(df, "not_a_real_column", func_name="some_func")

    assert str(excinfo.value) == (
        "some_func() needs column(s) not_a_real_column, not present in df."
    )


def test_explode_sdg_missing_column_message_includes_analysis_hint() -> None:
    """explode_sdg's own missing-column error carries the analysis-preset hint end to end."""
    df = pd.DataFrame({"other": [1]})

    with pytest.raises(ValueError, match="columns='analysis'"):
        analysis.explode_sdg(df)


# --- explode_sdg -----------------------------------------------------------------


def test_explode_sdg_missing_column_raises() -> None:
    """`explode_sdg` names the missing column when `sdg_codes_raw` is absent."""
    df = pd.DataFrame({"other": [1, 2]})
    with pytest.raises(ValueError, match="sdg_codes_raw"):
        analysis.explode_sdg(df)


def test_explode_sdg_grammar_and_weights() -> None:
    """Bare-int goals, `x.y` targets, the rare `N.0` variant, and per-row weights."""
    df = pd.DataFrame(
        {
            "tossd_id": ["a", "b", "c", "d"],
            "usd_commitment": [100.0, 90.0, 50.0, 10.0],
            "sdg_codes_raw": ["5", "4.2", "5.0", "13;10.a;1"],
        }
    )

    result = analysis.explode_sdg(df)

    row_a = result.loc[result["tossd_id"] == "a"]
    assert row_a["sdg_code"].tolist() == ["5"]
    assert row_a["sdg_goal"].tolist() == [5]
    assert row_a["sdg_is_target"].tolist() == [False]
    assert row_a["sdg_weight"].tolist() == [1.0]

    row_b = result.loc[result["tossd_id"] == "b"]
    assert row_b["sdg_code"].tolist() == ["4.2"]
    assert row_b["sdg_goal"].tolist() == [4]
    assert row_b["sdg_is_target"].tolist() == [True]

    # the rare "N.0" variant is a goal-level tag, not a "target 0".
    row_c = result.loc[result["tossd_id"] == "c"]
    assert row_c["sdg_code"].tolist() == ["5.0"]
    assert row_c["sdg_goal"].tolist() == [5]
    assert row_c["sdg_is_target"].tolist() == [False]

    # multi-token row: 3 tokens, each weight 1/3, summing to 1.
    row_d = result.loc[result["tossd_id"] == "d"]
    assert sorted(row_d["sdg_code"].tolist()) == ["1", "10.a", "13"]
    assert row_d["sdg_weight"].tolist() == pytest.approx([1 / 3, 1 / 3, 1 / 3])
    assert row_d["sdg_weight"].sum() == pytest.approx(1.0)
    assert row_d.loc[row_d["sdg_code"] == "10.a", "sdg_goal"].tolist() == [10]
    assert row_d.loc[row_d["sdg_code"] == "10.a", "sdg_is_target"].tolist() == [True]


def test_explode_sdg_drops_empty_and_null_rows() -> None:
    """A row with no SDG tag (empty or null) contributes zero rows to the result."""
    df = pd.DataFrame(
        {
            "tossd_id": ["a", "b", "c"],
            "sdg_codes_raw": ["5", "", None],
        }
    )

    result = analysis.explode_sdg(df)

    assert result["tossd_id"].tolist() == ["a"]


def test_explode_sdg_renormalisation_identity() -> None:
    """A grouped sum of `amount * sdg_weight` equals the SDG-tagged subtotal."""
    df = pd.DataFrame(
        {
            "tossd_id": ["a", "b", "c"],
            "usd_commitment": [90.0, 60.0, 1000.0],
            "sdg_codes_raw": ["1;4;13", "5.2;6.b", ""],
        }
    )
    sdg_tagged_total = 90.0 + 60.0  # row "c" carries no SDG tag.

    result = analysis.explode_sdg(df)
    weighted_total = (result["usd_commitment"] * result["sdg_weight"]).sum()

    assert weighted_total == pytest.approx(sdg_tagged_total)


def test_explode_sdg_preserves_row_order() -> None:
    """Exploded rows stay grouped in the source frame's original order."""
    df = pd.DataFrame(
        {
            "tossd_id": ["a", "b", "c"],
            "sdg_codes_raw": ["1;2", "3", "4;5"],
        }
    )

    result = analysis.explode_sdg(df)

    assert result["tossd_id"].tolist() == ["a", "a", "b", "c", "c"]


def test_explode_sdg_does_not_mutate_input() -> None:
    """`explode_sdg` leaves the caller's original frame unchanged, byte-for-byte."""
    df = pd.DataFrame({"tossd_id": ["a"], "sdg_codes_raw": ["5"]})
    original = df.copy()

    analysis.explode_sdg(df)

    pd.testing.assert_frame_equal(df, original)


def test_explode_sdg_rejects_already_exploded_input() -> None:
    """Re-running `explode_sdg` on its own output raises instead of duplicating columns."""
    df = pd.DataFrame({"tossd_id": ["a"], "sdg_codes_raw": ["5"]})
    once = analysis.explode_sdg(df)

    with pytest.raises(ValueError, match="sdg_code"):
        analysis.explode_sdg(once)


def test_explode_sdg_strips_whitespace_only_tokens() -> None:
    """A whitespace-only token between delimiters is dropped like an empty one."""
    df = pd.DataFrame({"tossd_id": ["a"], "sdg_codes_raw": ["5; ;6"]})

    result = analysis.explode_sdg(df)

    assert sorted(result["sdg_code"].tolist()) == ["5", "6"]


def test_explode_sdg_empty_input_has_documented_dtypes() -> None:
    """A 0-row input yields a 0-row result whose columns keep the documented dtypes."""
    df = pd.DataFrame(
        {
            "tossd_id": pd.Series([], dtype="object"),
            "usd_commitment": pd.Series([], dtype="float64"),
            "sdg_codes_raw": pd.Series([], dtype="object"),
        }
    )

    result = analysis.explode_sdg(df)

    assert len(result) == 0
    assert result["sdg_weight"].dtype == "float64"
    assert result["sdg_goal"].dtype == "Int8"
    assert result["sdg_is_target"].dtype == "bool"
    # Would raise TypeError if sdg_weight had come back object/str-dtyped.
    assert (result["usd_commitment"] * result["sdg_weight"]).empty


def test_explode_sdg_non_empty_output_dtypes() -> None:
    """Declared output dtypes hold on a non-empty, multi-row case too."""
    df = pd.DataFrame({"tossd_id": ["a", "b"], "sdg_codes_raw": ["5", "4.2"]})

    result = analysis.explode_sdg(df)

    assert result["sdg_goal"].dtype == "Int8"
    assert result["sdg_is_target"].dtype == "bool"
    assert result["sdg_weight"].dtype == "float64"


# --- explode_sdg value= ------------------------------------------------------------


def test_explode_sdg_value_none_is_byte_identical_to_the_default() -> None:
    """`value=None` (the default) leaves output columns and content unchanged."""
    df = pd.DataFrame(
        {
            "tossd_id": ["a", "b"],
            "usd_commitment": [90.0, 60.0],
            "sdg_codes_raw": ["1;4;13", ""],
        }
    )

    explicit = analysis.explode_sdg(df, value=None)
    default = analysis.explode_sdg(df)

    pd.testing.assert_frame_equal(explicit, default)
    assert "usd_commitment_weighted" not in explicit.columns


def test_explode_sdg_value_adds_weighted_column_alongside_the_original() -> None:
    """`{value}_weighted` sits beside the untouched original `value` column."""
    df = pd.DataFrame(
        {
            "tossd_id": ["a"],
            "usd_commitment": [90.0],
            "sdg_codes_raw": ["1;4;13"],
        }
    )

    result = analysis.explode_sdg(df, value="usd_commitment")

    assert (result["usd_commitment"] == 90.0).all()
    assert result["usd_commitment_weighted"].tolist() == pytest.approx([30.0] * 3)


def test_explode_sdg_value_weighted_column_hand_computed() -> None:
    """`{value}_weighted` equals `value * sdg_weight` row by row, hand-checked."""
    df = pd.DataFrame(
        {
            "tossd_id": ["a", "b"],
            "usd_commitment": [100.0, 40.0],
            "sdg_codes_raw": ["5", "4.2;6.b"],
        }
    )

    result = analysis.explode_sdg(df, value="usd_commitment")

    by_row = result.set_index("sdg_code")["usd_commitment_weighted"]
    assert by_row["5"] == pytest.approx(100.0)  # single tag: full weight
    assert by_row["4.2"] == pytest.approx(20.0)  # two tags: half weight each
    assert by_row["6.b"] == pytest.approx(20.0)


def test_explode_sdg_value_renormalisation_identity_matches_named_column() -> None:
    """A grouped sum of `{value}_weighted` equals the SDG-tagged subset's original total."""
    df = pd.DataFrame(
        {
            "tossd_id": ["a", "b", "c"],
            "usd_commitment": [90.0, 60.0, 1000.0],
            "sdg_codes_raw": ["1;4;13", "5.2;6.b", ""],
        }
    )
    sdg_tagged_total = 90.0 + 60.0  # row "c" carries no SDG tag.

    result = analysis.explode_sdg(df, value="usd_commitment")

    assert result["usd_commitment_weighted"].sum() == pytest.approx(sdg_tagged_total)
    # Same identity the un-named ad hoc multiplication already gave.
    ad_hoc = (result["usd_commitment"] * result["sdg_weight"]).sum()
    assert result["usd_commitment_weighted"].sum() == pytest.approx(ad_hoc)


def test_explode_sdg_value_missing_column_raises_with_analysis_hint() -> None:
    """A `value=` column absent from `df` raises, with the analysis-preset hint."""
    df = pd.DataFrame({"sdg_codes_raw": ["5"]})

    with pytest.raises(ValueError, match="columns='analysis'") as excinfo:
        analysis.explode_sdg(df, value="sector_code")
    assert "sector_code" in str(excinfo.value)


def test_explode_sdg_value_non_numeric_raises() -> None:
    """A `value=` column that isn't numeric-dtyped raises, naming the dtype."""
    df = pd.DataFrame(
        {
            "sdg_codes_raw": ["5"],
            "provider_name": pd.Series(["Alpha"], dtype="category"),
        }
    )

    with pytest.raises(ValueError, match="numeric") as excinfo:
        analysis.explode_sdg(df, value="provider_name")
    message = str(excinfo.value)
    assert "provider_name" in message
    assert "category" in message


def test_explode_sdg_value_rejects_already_weighted_input() -> None:
    """Re-running with the same `value=` on already-exploded output raises, not overwrites."""
    df = pd.DataFrame(
        {"tossd_id": ["a"], "usd_commitment": [90.0], "sdg_codes_raw": ["5"]}
    )
    once = analysis.explode_sdg(df, value="usd_commitment")

    with pytest.raises(ValueError, match="usd_commitment_weighted"):
        analysis.explode_sdg(once, value="usd_commitment")


def test_explode_sdg_value_does_not_mutate_input() -> None:
    """`explode_sdg(value=...)` leaves the caller's original frame unchanged."""
    df = pd.DataFrame(
        {"tossd_id": ["a"], "usd_commitment": [90.0], "sdg_codes_raw": ["5"]}
    )
    original = df.copy()

    analysis.explode_sdg(df, value="usd_commitment")

    pd.testing.assert_frame_equal(df, original)


def test_explode_sdg_value_copies_attrs() -> None:
    """`df.attrs` propagates onto the result with `value=` given, same as without it."""
    df = pd.DataFrame(
        {"tossd_id": ["a"], "usd_commitment": [90.0], "sdg_codes_raw": ["5"]}
    )
    df.attrs["source"] = "test"

    result = analysis.explode_sdg(df, value="usd_commitment")

    assert result.attrs == {"source": "test"}


def test_explode_sdg_value_empty_input_has_documented_dtype() -> None:
    """A 0-row input with `value=` yields a 0-row result; the weighted column is float64."""
    df = pd.DataFrame(
        {
            "tossd_id": pd.Series([], dtype="object"),
            "usd_commitment": pd.Series([], dtype="float64"),
            "sdg_codes_raw": pd.Series([], dtype="object"),
        }
    )

    result = analysis.explode_sdg(df, value="usd_commitment")

    assert len(result) == 0
    assert result["usd_commitment_weighted"].dtype == "float64"


# --- add_iso3 --------------------------------------------------------------------


def test_add_iso3_missing_columns_raises() -> None:
    """`add_iso3` raises when neither provider_code nor recipient_code is present."""
    df = pd.DataFrame({"other": [1]})
    with pytest.raises(ValueError, match="provider_code"):
        analysis.add_iso3(df)


def test_add_iso3_resolves_real_country_codes() -> None:
    """Real provider/recipient codes resolve to the packaged codelist's own iso3."""
    provider_codelist = codelists.load_codelist("provider")
    recipient_codelist = codelists.load_codelist("recipient")
    france_code = int(
        provider_codelist.loc[provider_codelist["name"] == "France", "code"].iloc[0]
    )
    turkiye_code = int(
        recipient_codelist.loc[recipient_codelist["iso3"] == "TUR", "code"].iloc[0]
    )

    df = pd.DataFrame(
        {"provider_code": [france_code], "recipient_code": [turkiye_code]}
    )

    result = analysis.add_iso3(df)

    assert result["provider_iso3"].tolist() == ["FRA"]
    assert result["recipient_iso3"].tolist() == ["TUR"]
    assert isinstance(result["provider_iso3"].dtype, pd.CategoricalDtype)
    assert isinstance(result["recipient_iso3"].dtype, pd.CategoricalDtype)


def test_add_iso3_aggregates_and_multilaterals_are_na() -> None:
    """Aggregate (code 0) and multilateral provider codes resolve to NA."""
    provider_codelist = codelists.load_codelist("provider")
    multilateral_code = int(
        provider_codelist.loc[provider_codelist["name"] == "UNEP", "code"].iloc[0]
    )
    df = pd.DataFrame({"provider_code": [0, multilateral_code]})

    result = analysis.add_iso3(df)

    assert result["provider_iso3"].isna().all()


def test_add_iso3_only_provider_present() -> None:
    """Only `provider_code` present in `df` yields only `provider_iso3` added."""
    df = pd.DataFrame({"provider_code": [1]})

    result = analysis.add_iso3(df)

    assert "provider_iso3" in result.columns
    assert "recipient_iso3" not in result.columns


def test_add_iso3_only_recipient_present() -> None:
    """Only `recipient_code` present in `df` yields only `recipient_iso3` added."""
    df = pd.DataFrame({"recipient_code": [1]})

    result = analysis.add_iso3(df)

    assert "recipient_iso3" in result.columns
    assert "provider_iso3" not in result.columns


def test_add_iso3_tossd_only_entity_is_na() -> None:
    """A TOSSD-only entity (no DAC iso3 link) resolves to NA, not an error."""
    provider_codelist = codelists.load_codelist("provider")
    tossd_only_code = int(
        provider_codelist.loc[
            provider_codelist["name"] == "Palestinian Authority", "code"
        ].iloc[0]
    )
    df = pd.DataFrame({"provider_code": [tossd_only_code]})

    result = analysis.add_iso3(df)

    assert result["provider_iso3"].isna().all()


def test_add_iso3_does_not_mutate_input() -> None:
    """`add_iso3` leaves the caller's original frame unchanged, byte-for-byte."""
    df = pd.DataFrame({"provider_code": [1]})
    original = df.copy()

    analysis.add_iso3(df)

    pd.testing.assert_frame_equal(df, original)


def test_resolvekit_is_imported_lazily_only_by_add_iso3() -> None:
    """`resolvekit` stays out of `sys.modules` until `add_iso3` actually runs."""
    script = (
        "import sys\n"
        "import tossd_reader\n"
        "assert 'resolvekit' not in sys.modules\n"
        "import pandas as pd\n"
        "tossd_reader.explode_sdg(pd.DataFrame({'sdg_codes_raw': ['5']}))\n"
        "tossd_reader.extract_keywords(pd.DataFrame({'keywords_raw': ['#GENDER']}))\n"
        "tossd_reader.get_structural_breaks()\n"
        "tossd_reader.filter_provider_costs(\n"
        "    pd.DataFrame({'tossd_pillar': [2], 'sector_code': [910]})\n"
        ")\n"
        "assert 'resolvekit' not in sys.modules\n"
        "tossd_reader.add_iso3(pd.DataFrame({'provider_code': [1]}))\n"
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


# --- extract_keywords --------------------------------------------------------------


def test_extract_keywords_missing_column_raises() -> None:
    """`extract_keywords` names the missing column when `keywords_raw` is absent."""
    df = pd.DataFrame({"other": [1]})
    with pytest.raises(ValueError, match="keywords_raw"):
        analysis.extract_keywords(df)


def test_extract_keywords_casefold_and_hash_variants() -> None:
    """`COVID-19` and `#covid-19` both count as the `covid_19` marker."""
    df = pd.DataFrame({"keywords_raw": ["COVID-19", "#covid-19", "#COVID-19"]})

    result = analysis.extract_keywords(df)

    assert result["kw_covid_19"].tolist() == [True, True, True]


def test_extract_keywords_null_row_matches_no_marker() -> None:
    """A null `keywords_raw` value is treated like an empty one, not an error."""
    df = pd.DataFrame({"keywords_raw": [None]})

    result = analysis.extract_keywords(df)

    kw_columns = [col for col in result.columns if col.startswith("kw_")]
    assert not result.loc[0, kw_columns].any()


def test_extract_keywords_all_twelve_columns_present() -> None:
    """Every one of the 12 packaged markers gets its own `kw_<marker>` column."""
    df = pd.DataFrame({"keywords_raw": [""]})

    result = analysis.extract_keywords(df)

    expected = {
        "kw_gender",
        "kw_adaptation",
        "kw_mitigation",
        "kw_biodiversity",
        "kw_ppr_preparedness",
        "kw_ppr_response",
        "kw_covid_19",
        "kw_refugees_hostcommunities",
        "kw_idps_hostcommunities",
        "kw_voluntaryrefugeereturn_reintegration",
        "kw_transnational_benefits_global",
        "kw_non_17_3_1",
    }
    kw_columns = {col for col in result.columns if col.startswith("kw_")}
    assert kw_columns == expected
    assert not result.loc[0, list(expected)].any()


def test_extract_keywords_empty_input_kw_columns_are_bool_dtype() -> None:
    """The `kw_*` columns keep bool dtype even on a 0-row input."""
    df = pd.DataFrame({"keywords_raw": pd.Series([], dtype="object")})

    result = analysis.extract_keywords(df)

    kw_columns = [col for col in result.columns if col.startswith("kw_")]
    assert len(kw_columns) == 12
    for column in kw_columns:
        assert result[column].dtype == bool


def test_extract_keywords_unknown_tokens_ignored() -> None:
    """An unrecognised token is silently ignored."""
    df = pd.DataFrame({"keywords_raw": ["R&D|CLIMATE"]})

    result = analysis.extract_keywords(df)

    kw_columns = [col for col in result.columns if col.startswith("kw_")]
    assert not result.loc[0, kw_columns].any()


def test_extract_keywords_specific_marker_tokens() -> None:
    """The published, non-obvious marker spellings match (brackets, hyphens, dots)."""
    df = pd.DataFrame(
        {
            "keywords_raw": [
                "#Transnational_benefits_[Global]",
                "#NON-17.3.1",
                "#Refugees_HostCommunities",
                "#IDPs_HostCommunities",
                "#VoluntaryRefugeeReturn_Reintegration",
            ]
        }
    )

    result = analysis.extract_keywords(df)

    assert result["kw_transnational_benefits_global"].tolist() == [
        True,
        False,
        False,
        False,
        False,
    ]
    assert result["kw_non_17_3_1"].tolist() == [False, True, False, False, False]
    assert result["kw_refugees_hostcommunities"].tolist() == [
        False,
        False,
        True,
        False,
        False,
    ]
    assert result["kw_idps_hostcommunities"].tolist() == [
        False,
        False,
        False,
        True,
        False,
    ]
    assert result["kw_voluntaryrefugeereturn_reintegration"].tolist() == [
        False,
        False,
        False,
        False,
        True,
    ]


def test_extract_keywords_raw_column_untouched() -> None:
    """`keywords_raw` itself is left exactly as it came in."""
    df = pd.DataFrame({"keywords_raw": ["#GENDER|#MITIGATION"]})

    result = analysis.extract_keywords(df)

    assert result["keywords_raw"].tolist() == ["#GENDER|#MITIGATION"]


def test_extract_keywords_does_not_mutate_input() -> None:
    """`extract_keywords` leaves the caller's original frame unchanged, byte-for-byte."""
    df = pd.DataFrame({"keywords_raw": ["#GENDER"]})
    original = df.copy()

    analysis.extract_keywords(df)

    pd.testing.assert_frame_equal(df, original)


# --- get_structural_breaks ----------------------------------------------------------


def test_get_structural_breaks_exact_row_count_and_columns() -> None:
    """The packaged structural-breaks table has exactly 5 verified rows."""
    result = analysis.get_structural_breaks()

    assert len(result) == 5
    assert {"dimension", "break_year", "end_year", "description", "source"} <= set(
        result.columns
    )
    assert set(result["dimension"]) == {
        "sub_pillar",
        "modality",
        "reporters",
        "methodology",
    }


def test_get_structural_breaks_end_year_marks_the_reporters_drift() -> None:
    """`end_year` matches `break_year` for discrete breaks, 2024 for the reporters drift."""
    result = analysis.get_structural_breaks()

    discrete = result.loc[result["dimension"] != "reporters"]
    assert (discrete["end_year"] == discrete["break_year"]).all()

    reporters_row = result.loc[result["dimension"] == "reporters"].iloc[0]
    assert reporters_row["break_year"] == 2019
    assert reporters_row["end_year"] == 2024


def test_get_structural_breaks_reporters_row_states_its_counting_rule() -> None:
    """The reporters figures are reproducible, so the row names the rule behind them.

    97 (2019) and 130 (2024) are distinct `provider_code` values excluding the
    aggregate pseudo-provider (code 0). A reader who runs that count on the
    published files gets the same pair, which is the point of stating it.
    """
    result = analysis.get_structural_breaks()

    description = result.loc[result["dimension"] == "reporters", "description"].iloc[0]
    assert "97" in description
    assert "130" in description
    assert "provider_code != 0" in description


def test_get_structural_breaks_no_mutation_across_calls() -> None:
    """get_structural_breaks() returns a fresh copy each call, so mutating one result leaves the cache and later calls unaffected."""
    first = analysis.get_structural_breaks()
    first.loc[0, "dimension"] = "corrupted"

    second = analysis.get_structural_breaks()

    assert "corrupted" not in second["dimension"].tolist()


def test_get_structural_breaks_years_none_returns_every_row() -> None:
    """years=None (the default) is unchanged: every packaged row, still."""
    result = analysis.get_structural_breaks(years=None)

    assert len(result) == len(analysis.get_structural_breaks())


def test_get_structural_breaks_single_discrete_year_keeps_only_intersecting_rows() -> (
    None
):
    """A single year keeps only rows whose [break_year, end_year] covers it."""
    all_breaks = analysis.get_structural_breaks()
    modality_row = all_breaks.loc[all_breaks["dimension"] == "modality"].iloc[0]

    result = analysis.get_structural_breaks(years=int(modality_row["break_year"]))

    assert "modality" in result["dimension"].tolist()
    assert len(result) < len(all_breaks)


def test_get_structural_breaks_reporters_row_spans_its_whole_range() -> None:
    """The reporters row (2019-2024) matches every year across that continuous span."""
    for year in (2019, 2021, 2024):
        result = analysis.get_structural_breaks(years=year)
        assert "reporters" in result["dimension"].tolist()


def test_get_structural_breaks_iterable_years_unions_the_matches() -> None:
    """An iterable of years keeps a row if it intersects any one of them."""
    all_breaks = analysis.get_structural_breaks()
    modality_row = all_breaks.loc[all_breaks["dimension"] == "modality"].iloc[0]
    methodology_row = all_breaks.loc[all_breaks["dimension"] == "methodology"].iloc[0]

    result = analysis.get_structural_breaks(
        years=[int(modality_row["break_year"]), int(methodology_row["break_year"])]
    )

    assert {"modality", "methodology"} <= set(result["dimension"])


def test_get_structural_breaks_year_matching_nothing_returns_empty_frame() -> None:
    """A year outside every row's range returns an empty, still correctly-columned frame."""
    result = analysis.get_structural_breaks(years=1900)

    assert result.empty
    assert list(result.columns) == list(analysis.get_structural_breaks().columns)


def test_get_structural_breaks_years_filter_does_not_mutate_the_cache() -> None:
    """Filtering by years still returns rows independent of the cached table."""
    result = analysis.get_structural_breaks(years=2024)
    result.loc[result.index[0], "dimension"] = "corrupted"

    fresh = analysis.get_structural_breaks(years=2024)

    assert "corrupted" not in fresh["dimension"].tolist()


# --- filter_provider_costs -------------------------------------------------------


def test_filter_provider_costs_missing_columns_raises() -> None:
    """Raises naming whichever of `tossd_pillar`/`sector_code` is absent."""
    df = pd.DataFrame({"tossd_pillar": [2]})
    with pytest.raises(ValueError, match="sector_code"):
        analysis.filter_provider_costs(df)


def test_filter_provider_costs_filters_to_carveout_sectors() -> None:
    """Keeps only pillar-2 rows whose sector_code is 910 or 930."""
    df = pd.DataFrame(
        {
            "tossd_id": ["a", "b", "c", "d", "e"],
            "tossd_pillar": [2, 2, 2, 1, 2],
            "sector_code": [910, 930, 110, 910, 720],
        }
    )

    result = analysis.filter_provider_costs(df)

    assert sorted(result["tossd_id"].tolist()) == ["a", "b"]


def test_filter_provider_costs_excludes_null_sector_code_rows() -> None:
    """A null `sector_code` is excluded, not a crash."""
    df = pd.DataFrame(
        {
            "tossd_id": ["a", "b"],
            "tossd_pillar": [2, 2],
            "sector_code": [910, None],
        }
    )

    result = analysis.filter_provider_costs(df)

    assert result["tossd_id"].tolist() == ["a"]


def test_filter_provider_costs_does_not_mutate_input() -> None:
    """Filtering leaves the caller's original frame unchanged."""
    df = pd.DataFrame({"tossd_pillar": [2, 1], "sector_code": [910, 110]})
    original = df.copy()

    analysis.filter_provider_costs(df)

    pd.testing.assert_frame_equal(df, original)


# --- add_recipient_group -----------------------------------------------------------

# Real codes from src/tossd_reader/_data/codelists/recipient.csv, chosen for
# their known recipient_groups.csv values (notes/incantation/recipient-groups-sources.md):
# 225 Angola (LDC / Lower middle income / South of Sahara), 218 South Africa
# (Other Developing / Upper middle income / South of Sahara), 276 Saint
# Helena (Other Developing / Unclassified income -- non-self-governing
# territory / South of Sahara), 89 "Europe, regional" (no iso3 -> Unallocated
# under ldc/income, real "Europe" under region), 55 Türkiye (Other
# Developing / Upper middle income / Europe).


def test_add_recipient_group_missing_column_raises() -> None:
    """`add_recipient_group` names the missing column when `recipient_code` is absent."""
    df = pd.DataFrame({"other": [1]})
    with pytest.raises(ValueError, match="recipient_code"):
        analysis.add_recipient_group(df)


def test_add_recipient_group_invalid_scheme_raises() -> None:
    """An unrecognised `scheme=` raises, naming the valid options."""
    df = pd.DataFrame({"recipient_code": [225]})
    with pytest.raises(ValueError, match="'income'") as excinfo:
        analysis.add_recipient_group(df, scheme="bogus")
    message = str(excinfo.value)
    assert "'ldc'" in message
    assert "'region'" in message


def test_add_recipient_group_rejects_already_grouped_input() -> None:
    """Re-running `add_recipient_group` on its own output raises, not silently overwrites."""
    df = pd.DataFrame({"recipient_code": [225]})
    once = analysis.add_recipient_group(df)

    with pytest.raises(ValueError, match="recipient_group"):
        analysis.add_recipient_group(once)


def test_add_recipient_group_ldc_scheme_real_codes() -> None:
    """LDC, Other Developing, and the no-iso3 Unallocated bucket resolve correctly."""
    df = pd.DataFrame({"recipient_code": [225, 218, 89]})

    result = analysis.add_recipient_group(df, scheme="ldc")

    assert result["recipient_group"].tolist() == [
        "Least Developed Countries",
        "Other Developing Countries",
        "Regional / Multi-country Unallocated",
    ]
    assert isinstance(result["recipient_group"].dtype, pd.CategoricalDtype)


def test_add_recipient_group_income_scheme_unclassified_territory() -> None:
    """A non-self-governing territory gets 'Unclassified', distinct from Unallocated."""
    df = pd.DataFrame({"recipient_code": [276, 89]})

    result = analysis.add_recipient_group(df, scheme="income")

    assert result["recipient_group"].tolist() == [
        "Unclassified",
        "Regional / Multi-country Unallocated",
    ]


def test_add_recipient_group_region_scheme_covers_regional_codes_too() -> None:
    """Every code, including no-iso3 regional ones, resolves to a real region."""
    df = pd.DataFrame({"recipient_code": [55, 89]})

    result = analysis.add_recipient_group(df, scheme="region")

    assert result["recipient_group"].tolist() == ["Europe", "Europe"]


def test_add_recipient_group_unknown_code_warns_once_and_returns_na() -> None:
    """A recipient_code absent from the packaged table -> NA, warned once, then quiet."""
    analysis._reset_for_tests()
    df = pd.DataFrame({"recipient_code": [225, 999999]})

    with pytest.warns(UserWarning, match="999999"):
        result = analysis.add_recipient_group(df)
    assert result["recipient_group"].tolist()[0] == "Least Developed Countries"
    assert pd.isna(result["recipient_group"].tolist()[1])

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        analysis.add_recipient_group(df)  # same unknown code again: no warning


def test_add_recipient_group_does_not_mutate_input() -> None:
    """`add_recipient_group` leaves the caller's original frame unchanged."""
    df = pd.DataFrame({"recipient_code": [225]})
    original = df.copy()

    analysis.add_recipient_group(df)

    pd.testing.assert_frame_equal(df, original)


def test_add_recipient_group_copies_attrs() -> None:
    """`df.attrs` propagates onto the result (A7)."""
    df = pd.DataFrame({"recipient_code": [225]})
    df.attrs["source"] = "test"

    result = analysis.add_recipient_group(df)

    assert result.attrs == {"source": "test"}


def test_add_recipient_group_empty_input_returns_empty_correctly_typed() -> None:
    """A 0-row input yields a 0-row, category-dtyped result, silently."""
    df = pd.DataFrame({"recipient_code": pd.Series([], dtype="Int16")})

    result = analysis.add_recipient_group(df)

    assert result.empty
    assert isinstance(result["recipient_group"].dtype, pd.CategoricalDtype)


def test_get_recipient_groups_version_names_both_sources() -> None:
    """The version stamp independently names the LDC-list and WB-income vintages."""
    version = analysis.get_recipient_groups_version()
    assert "ldc" in version
    assert "wb-fy27" in version


def test_get_recipient_groups_version_is_cached() -> None:
    """Repeated calls return the identical cached string object."""
    assert (
        analysis.get_recipient_groups_version()
        is analysis.get_recipient_groups_version()
    )


# --- add_instrument_group -----------------------------------------------------------

# Real codes from src/tossd_reader/_data/codelists/finance_instrument.csv,
# chosen for their known instrument_groups.csv values
# (notes/incantation/instrument-groups-spec.md): 110 Standard grant (Grants),
# 421 Standard loan (loan family -- concessionality_flag decides), 510 Common
# equity (Equity), 1100 Guarantees/insurance (Guarantees), 2100 Direct
# provider spending (its own group), 431 Subordinated loan (Hybrid/Mezzanine,
# per the ORCHESTRATOR RULING keeping the mezzanine family out of the loan
# split), 310 Capital subscription on deposit basis (Other Instruments).


def _instrument_df(codes: list[int | None], flags: list[int | None]) -> pd.DataFrame:
    """Build a minimal analysis-shaped frame with nullable Int dtypes, like get_tossd()."""
    return pd.DataFrame(
        {
            "finance_instrument_code": pd.array(codes, dtype="Int16"),
            "concessionality_flag": pd.array(flags, dtype="Int8"),
        }
    )


def test_add_instrument_group_missing_columns_raises() -> None:
    """Raises naming whichever of the two required columns is absent, with the analysis hint."""
    df = pd.DataFrame({"other": [1]})
    with pytest.raises(ValueError, match="columns='analysis'") as excinfo:
        analysis.add_instrument_group(df)
    message = str(excinfo.value)
    assert "finance_instrument_code" in message
    assert "concessionality_flag" in message


def test_add_instrument_group_rejects_already_grouped_input() -> None:
    """Re-running `add_instrument_group` on its own output raises, not silently overwrites."""
    df = _instrument_df([110], [None])
    once = analysis.add_instrument_group(df)

    with pytest.raises(ValueError, match="instrument_group"):
        analysis.add_instrument_group(once)


def test_add_instrument_group_grants_equity_and_direct_provider_spending() -> None:
    """Codes outside the loan family classify from `finance_instrument_code` alone."""
    df = _instrument_df([110, 510, 2100, 1100, 431, 310], [None] * 6)

    result = analysis.add_instrument_group(df)

    assert result["instrument_group"].tolist() == [
        "Grants",
        "Equity",
        "Direct Provider Spending",
        "Guarantees",
        "Hybrid/Mezzanine",
        "Other Instruments",
    ]
    assert isinstance(result["instrument_group"].dtype, pd.CategoricalDtype)


def test_add_instrument_group_concessionality_flag_splits_the_loan_family() -> None:
    """Code 421 (Standard loan) splits on `concessionality_flag` alone."""
    df = _instrument_df([421, 421], [1, 0])

    result = analysis.add_instrument_group(df)

    assert result["instrument_group"].tolist() == [
        "Concessional Loans",
        "Non-concessional Loans",
    ]


def test_add_instrument_group_observed_codes_classify_without_raising() -> None:
    """The 5 codes real 2023-2024 data carries but OECD's live codelist doesn't -- all mapped.

    0 "NON FLOW ITEMS" -> Other Instruments (real, non-blank code on real
    rows with real dollar amounts -- an honest bucket, not NA). 1101/1102
    (loan/portfolio guarantees) -> Guarantees, same as 1100. 4221/4222
    (reimbursable-grant sub-variants of the 422 loan-family code) join the
    debt family and split on concessionality_flag exactly like 421/422.
    """
    df = _instrument_df([0, 1101, 1102, 4221, 4221], [None, None, None, 1, 0])

    result = analysis.add_instrument_group(df)

    assert result["instrument_group"].tolist() == [
        "Other Instruments",
        "Guarantees",
        "Guarantees",
        "Concessional Loans",
        "Non-concessional Loans",
    ]


def test_add_instrument_group_blank_concessionality_flag_on_loan_code_is_na() -> None:
    """A blank `concessionality_flag` on a loan-family code -> NA, not a default."""
    df = _instrument_df([421], [None])

    result = analysis.add_instrument_group(df)

    assert pd.isna(result["instrument_group"].tolist()[0])


def test_add_instrument_group_blank_instrument_code_is_na() -> None:
    """A blank/NA `finance_instrument_code` (pseudo-aggregate rows) -> NA, never a raise."""
    df = _instrument_df([None, 110], [None, None])

    result = analysis.add_instrument_group(df)

    assert pd.isna(result["instrument_group"].tolist()[0])
    assert result["instrument_group"].tolist()[1] == "Grants"


def test_add_instrument_group_unmapped_code_raises_unknown_code_error() -> None:
    """A non-null code absent from the table raises `UnknownCodeError`, naming it and the version."""
    df = _instrument_df([9999], [None])

    with pytest.raises(exceptions.UnknownCodeError, match="9999") as excinfo:
        analysis.add_instrument_group(df)
    assert analysis.get_instrument_groups_version() in str(excinfo.value)


def test_add_instrument_group_does_not_mutate_input() -> None:
    """`add_instrument_group` leaves the caller's original frame unchanged."""
    df = _instrument_df([110], [None])
    original = df.copy()

    analysis.add_instrument_group(df)

    pd.testing.assert_frame_equal(df, original)


def test_add_instrument_group_copies_attrs() -> None:
    """`df.attrs` propagates onto the result (A7)."""
    df = _instrument_df([110], [None])
    df.attrs["source"] = "test"

    result = analysis.add_instrument_group(df)

    assert result.attrs == {"source": "test"}


def test_add_instrument_group_empty_input_returns_empty_correctly_typed() -> None:
    """A 0-row input yields a 0-row, category-dtyped result, silently."""
    df = _instrument_df([], [])

    result = analysis.add_instrument_group(df)

    assert result.empty
    assert isinstance(result["instrument_group"].dtype, pd.CategoricalDtype)


def test_get_instrument_groups_version_names_both_components() -> None:
    """The version stamp independently names the OECD list vintage and this repo's methodology."""
    version = analysis.get_instrument_groups_version()
    assert "oecd-dac-cl15" in version
    assert "instrument-groups-methodology" in version


def test_get_instrument_groups_version_is_cached() -> None:
    """Repeated calls return the identical cached string object."""
    assert (
        analysis.get_instrument_groups_version()
        is analysis.get_instrument_groups_version()
    )
