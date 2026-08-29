"""Unit tests for the post-query analysis toolkit: `tossd_reader.analysis`."""

from __future__ import annotations

import subprocess
import sys

import pandas as pd
import pytest

from tossd_reader import analysis, codelists

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
        "tossd_reader.pillar2_provider_costs(\n"
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


# --- pillar2_provider_costs -------------------------------------------------------


def test_pillar2_provider_costs_missing_columns_raises() -> None:
    """Raises naming whichever of `tossd_pillar`/`sector_code` is absent."""
    df = pd.DataFrame({"tossd_pillar": [2]})
    with pytest.raises(ValueError, match="sector_code"):
        analysis.pillar2_provider_costs(df)


def test_pillar2_provider_costs_filters_to_carveout_sectors() -> None:
    """Keeps only pillar-2 rows whose sector_code is 910 or 930."""
    df = pd.DataFrame(
        {
            "tossd_id": ["a", "b", "c", "d", "e"],
            "tossd_pillar": [2, 2, 2, 1, 2],
            "sector_code": [910, 930, 110, 910, 720],
        }
    )

    result = analysis.pillar2_provider_costs(df)

    assert sorted(result["tossd_id"].tolist()) == ["a", "b"]


def test_pillar2_provider_costs_excludes_null_sector_code_rows() -> None:
    """A null `sector_code` is excluded, not a crash."""
    df = pd.DataFrame(
        {
            "tossd_id": ["a", "b"],
            "tossd_pillar": [2, 2],
            "sector_code": [910, None],
        }
    )

    result = analysis.pillar2_provider_costs(df)

    assert result["tossd_id"].tolist() == ["a"]


def test_pillar2_provider_costs_does_not_mutate_input() -> None:
    """Filtering leaves the caller's original frame unchanged."""
    df = pd.DataFrame({"tossd_pillar": [2, 1], "sector_code": [910, 110]})
    original = df.copy()

    analysis.pillar2_provider_costs(df)

    pd.testing.assert_frame_equal(df, original)
