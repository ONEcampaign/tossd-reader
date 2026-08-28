"""Unit tests for the runtime codelist loader: round-trip, filters, version."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from tossd_reader import codelists


def test_load_codelist_round_trips_a_packaged_dimension() -> None:
    """Loading a known packaged dimension returns a non-empty, correctly-typed frame."""
    frame = codelists.load_codelist("provider")

    assert not frame.empty
    assert {"code", "name", "tossd_only"} <= set(frame.columns)
    assert pd.api.types.is_string_dtype(frame["code"])
    assert frame["tossd_only"].dtype == bool


def test_load_codelist_returns_a_fresh_copy() -> None:
    """A caller's in-place edit can't poison later calls to the same dimension."""
    first = codelists.load_codelist("pillar")
    first.loc[0, "name"] = "mutated"
    second = codelists.load_codelist("pillar")
    assert first is not second
    assert (second["name"] != "mutated").all()


def test_load_codelist_unknown_dimension_raises() -> None:
    """An unrecognised dimension name raises `ValueError` naming what is available."""
    with pytest.raises(ValueError, match="not_a_real_dimension"):
        codelists.load_codelist("not_a_real_dimension")


@pytest.mark.parametrize(
    "dimension",
    [
        "provider",
        "recipient",
        "pillar",
        "financing_arrangement",
        "framework_of_collaboration",
        "purpose",
        "sector",
        "channel",
        "modality",
        "finance_instrument",
    ],
)
def test_every_packaged_dimension_is_non_empty_with_required_columns(
    dimension: str,
) -> None:
    """Every packaged dimension file loads, is non-empty, and has the required columns."""
    frame = codelists.load_codelist(dimension)
    assert not frame.empty
    assert {"code", "name", "tossd_only"} <= set(frame.columns)
    assert frame["code"].is_unique


def test_provider_and_recipient_carry_iso3() -> None:
    """The two area dimensions additionally carry an `iso3` column."""
    assert "iso3" in codelists.load_codelist("provider").columns
    assert "iso3" in codelists.load_codelist("recipient").columns


def test_get_available_filters_covers_every_dimension_plus_years() -> None:
    """`get_available_filters` returns every packaged dimension plus a `years` entry."""
    filters = codelists.get_available_filters()

    assert "years" in filters
    assert "provider" in filters
    assert "pillar" in filters
    for frame in filters.values():
        assert isinstance(frame, pd.DataFrame)
        assert not frame.empty

    years_frame = filters["years"]
    assert list(years_frame.columns) == ["year"]
    assert 2024 in years_frame["year"].to_list()


def test_get_codelists_version_is_an_iso_date() -> None:
    """`get_codelists_version` returns a bare ISO date (no time component)."""
    version = codelists.get_codelists_version()
    assert len(version) == len("YYYY-MM-DD")
    date.fromisoformat(version)  # round-trips without raising


def test_get_codelists_version_is_cached() -> None:
    """Repeated calls return the identical cached string object."""
    assert codelists.get_codelists_version() is codelists.get_codelists_version()
