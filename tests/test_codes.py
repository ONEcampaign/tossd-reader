"""Unit tests for `tossd_reader.codes`: browse/lookup, the filters= companion."""

from __future__ import annotations

import pandas as pd
import pytest

from tossd_reader import _matching, codes
from tossd_reader.exceptions import UnknownCodeError

# --- browse ---------------------------------------------------------------------


def test_browse_returns_the_packaged_codelist_frame() -> None:
    """browse() is a thin pass-through to codelists.load_codelist."""
    frame = codes.browse("modality")

    assert isinstance(frame, pd.DataFrame)
    assert {"code", "name", "tossd_only"} <= set(frame.columns)
    assert (
        frame.loc[frame["code"] == "B02", "name"]
        == "Core contributions to multilateral institutions"
    ).any()


def test_browse_covers_pillar_unlike_lookup() -> None:
    """browse() accepts "pillar" -- a wider set than lookup()'s LOOKUP_DIMENSIONS."""
    frame = codes.browse("pillar")

    assert isinstance(frame, pd.DataFrame)
    assert "pillar" not in codes.LOOKUP_DIMENSIONS


def test_browse_returns_a_fresh_copy_each_call() -> None:
    """Mutating one browse() result never poisons a later call (mirrors load_codelist's contract)."""
    first = codes.browse("sector")
    first.loc[first.index[0], "name"] = "mutated"

    second = codes.browse("sector")

    assert second.loc[second.index[0], "name"] != "mutated"


def test_browse_unknown_dimension_raises_value_error() -> None:
    """An unrecognised dimension raises ValueError, naming the packaged dimensions."""
    with pytest.raises(ValueError, match="Unknown codelist dimension"):
        codes.browse("not_a_real_dimension")


def test_browse_sector_contains_the_700_supplemental_row() -> None:
    """`browse("sector")` surfaces the packaged `700` row and its `source`."""
    sector = codes.browse("sector")
    row = sector.loc[sector["code"] == "700"]

    assert len(row) == 1
    assert row["name"].item() == "VIII. Humanitarian Aid"
    assert row["source"].item() == "dac-sector-classification"


# --- lookup: int-coded dimensions -------------------------------------------------


def test_lookup_int_coded_dimension_by_code() -> None:
    """lookup() resolves a digit-string code for an Int-backed dimension, returning int."""
    result = codes.lookup("sector", "110")

    assert result == 110
    assert isinstance(result, int)


def test_lookup_int_coded_dimension_by_name() -> None:
    """lookup() resolves a name (case-folded) for an Int-backed dimension."""
    result = codes.lookup("provider", "austria")

    assert result == 1


def test_lookup_int_coded_dimension_accepts_int_token() -> None:
    """A plain int token is trusted directly, same as providers=/recipients=."""
    assert codes.lookup("recipient", 55) == 55


def test_lookup_sector_resolves_the_supplemental_700_row_by_name() -> None:
    """The packaged `700` supplemental row resolves by name, same as any fetched sector row."""
    assert codes.lookup("sector", "VIII. Humanitarian Aid") == 700


def test_lookup_sector_accepts_int_700_token() -> None:
    """A plain int `700` token is trusted directly, same as any other sector code."""
    assert codes.lookup("sector", 700) == 700


# --- lookup: str-coded dimensions -------------------------------------------------


def test_lookup_str_coded_dimension_by_code() -> None:
    """lookup() resolves an exact code for a category<string>-backed dimension, returning str."""
    result = codes.lookup("modality", "B02")

    assert result == "B02"
    assert isinstance(result, str)


def test_lookup_str_coded_dimension_by_name_case_folded() -> None:
    """lookup() resolves a case-folded name match for a str-coded dimension."""
    result = codes.lookup("financing_arrangement", "islamic finance")

    assert result == "FA02"


def test_lookup_str_coded_dimension_rejects_int_token() -> None:
    """An int token for a str-coded dimension raises TypeError -- those codes aren't numeric."""
    with pytest.raises(TypeError, match="modality"):
        codes.lookup("modality", 2)


# --- lookup: matches the same path a filter uses ----------------------------------


def test_lookup_agrees_with_matching_resolve_one_code() -> None:
    """lookup() and the internal resolver `_matching.resolve_one_code` never disagree."""
    assert codes.lookup(
        "framework_of_collaboration", "FC01"
    ) == _matching.resolve_one_code(
        "FC01",
        dimension="framework_of_collaboration",
        label="framework_of_collaboration",
    )


# --- lookup: errors ----------------------------------------------------------------


def test_lookup_unknown_token_raises_unknown_code_error_with_suggestions() -> None:
    """A near-miss token raises UnknownCodeError naming the closest match."""
    with pytest.raises(UnknownCodeError, match="Austrai") as excinfo:
        codes.lookup("provider", "Austrai")

    assert "Austria" in str(excinfo.value)


def test_lookup_unknown_dimension_raises_value_error_naming_valid_ones() -> None:
    """An unrecognised dimension raises ValueError naming LOOKUP_DIMENSIONS."""
    with pytest.raises(ValueError, match="Unknown lookup\\(\\) dimension") as excinfo:
        codes.lookup("not_a_real_dimension", "x")

    for dimension in codes.LOOKUP_DIMENSIONS:
        assert dimension in str(excinfo.value)


def test_lookup_pillar_dimension_points_at_pillars_kwarg() -> None:
    """lookup("pillar", ...) is rejected, pointed at get_tossd(pillars=...) instead."""
    with pytest.raises(ValueError, match="pillars="):
        codes.lookup("pillar", "1")
