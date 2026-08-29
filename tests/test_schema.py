"""Unit tests for the schema layer: apply_schema, preset_columns, drift."""

from __future__ import annotations

import pyarrow as pa
import pytest

from tests.factories import build_tossd_table
from tossd_reader import _schema
from tossd_reader.exceptions import SchemaDriftError


@pytest.fixture(autouse=True)
def _reset_schema_state() -> None:
    """Clear _schema.py's warn-once state before each test.

    `tests/conftest.py` resets _discovery's, config's, and query's per-module
    state; _schema's own warn-once state is reset here instead, same as
    fetch.py's own local fixture.
    """
    _schema._reset_for_tests()


def test_apply_schema_round_trip() -> None:
    """A full apply_schema pass renames, types, and cleans a fixture correctly.

    n_rows=21 with year=2024 guarantees the fixture's deterministic
    modality-case-drift row lands on the literal `c01` variant (index 20,
    `20 % 4 == 0` selects modality code `C01` from the fixture's rotation).
    """
    table = build_tossd_table(2024, n_rows=21, seed=0)

    result = _schema.apply_schema(table)

    expected_names = [field.snake_name for field in _schema.load_schema()]
    assert list(result.column_names) == expected_names

    # dtypes: nullable ints, dictionary-encoded categories, float64 amounts.
    assert result.schema.field("year").type == pa.int16()
    assert result.schema.field("provider_code").type == pa.int16()
    assert result.schema.field("purpose_code").type == pa.int32()
    assert result.schema.field("tossd_pillar").type == pa.int8()
    assert pa.types.is_dictionary(result.schema.field("provider_name").type)
    assert pa.types.is_dictionary(result.schema.field("modality_code").type)
    assert result.schema.field("usd_commitment").type == pa.float64()
    assert result.schema.field("tossd_id").type == pa.string()

    # empty-string -> null, including the degenerate all-empty columns.
    assert result.column("parent_channel_name").null_count == table.num_rows
    assert result.column("mobilisation_origin").null_count == table.num_rows
    assert result.column("provider_agency_name").null_count > 0

    # c01 -> C01 code-case normalisation.
    assert table.column("modality")[-1].as_py() == "c01"
    assert result.column("modality_code")[-1].as_py() == "C01"


def test_duplicate_normalised_column_names_raise_schema_drift_error() -> None:
    """Two case-variant columns normalising to the same key raise, naming both."""
    table = build_tossd_table(2019, n_rows=5, seed=2)
    duplicated = table.append_column("Sector_3", table.column("sector3"))

    with pytest.raises(SchemaDriftError, match="sector3") as excinfo:
        _schema.apply_schema(duplicated)
    assert "Sector_3" in str(excinfo.value)


def test_missing_column_raises_schema_drift_error() -> None:
    """A schema-expected column absent from the file raises SchemaDriftError."""
    table = build_tossd_table(2019, n_rows=5, seed=0)
    dropped = table.drop_columns(["ProviderNameE"])

    with pytest.raises(SchemaDriftError, match="ProviderNameE"):
        _schema.apply_schema(dropped)


def test_extra_column_warns_once_and_passes_through() -> None:
    """An unrecognised extra column warns once, then passes through raw thereafter."""
    table = build_tossd_table(2019, n_rows=5, seed=0)
    with_extra = table.append_column("SomeNewColumn", pa.array(["x"] * table.num_rows))

    with pytest.warns(UserWarning, match="SomeNewColumn"):
        result = _schema.apply_schema(with_extra)
    assert "SomeNewColumn" in result.column_names
    assert result.column("SomeNewColumn").to_pylist() == ["x"] * table.num_rows

    # Same extra column again, same process: no repeat warning. With
    # `filterwarnings = ["error"]` set globally, an unexpected warning here
    # would itself raise and fail the test.
    _schema.apply_schema(with_extra)


def test_cast_failure_raises_schema_drift_error() -> None:
    """A value that cannot be cast to its target dtype raises, naming column and value."""
    table = build_tossd_table(2020, n_rows=10, seed=0)
    poisoned_values = table.column("purposecode").to_pylist()
    poisoned_values[0] = "abc"
    poisoned = table.set_column(
        table.column_names.index("purposecode"),
        "purposecode",
        pa.array(poisoned_values, type=pa.string()),
    )

    with pytest.raises(SchemaDriftError, match="purpose_code") as excinfo:
        _schema.apply_schema(poisoned)
    assert "abc" in str(excinfo.value)


def test_preset_columns_counts() -> None:
    """Regression pins for preset sizes: update these if schema.csv's preset flags change."""
    assert len(_schema.preset_columns("minimal")) == 17
    assert len(_schema.preset_columns("analysis")) == 42
    assert len(_schema.preset_columns("all")) == len(_schema.load_schema())


def test_preset_columns_unknown_preset_raises_value_error() -> None:
    """An unrecognised preset name raises ValueError, not a silent empty list."""
    with pytest.raises(ValueError, match="bogus"):
        _schema.preset_columns("bogus")  # type: ignore[arg-type]


def test_normalised_key_matching_tolerates_case_variant() -> None:
    """A case/separator-variant published header still matches its schema field."""
    table = build_tossd_table(2019, n_rows=5, seed=1)
    renamed = ["Sector_3" if name == "sector3" else name for name in table.column_names]
    variant_table = table.rename_columns(renamed)

    result = _schema.apply_schema(variant_table)

    assert "sector_code" in result.column_names
    assert (
        result.column("sector_code").to_pylist()
        == table.column("sector3").cast(pa.int16()).to_pylist()
    )


def test_large_string_empty_values_become_null() -> None:
    """Empty strings in a large_string column also become null, not just `string`."""
    table = build_tossd_table(2019, n_rows=20, seed=3)
    column_index = table.column_names.index("agencyname_E")
    large_string_column = table.column("agencyname_E").cast(pa.large_string())
    with_large_string = table.set_column(
        column_index, "agencyname_E", large_string_column
    )
    assert pa.types.is_large_string(with_large_string.schema.field("agencyname_E").type)

    result = _schema.apply_schema(with_large_string)

    assert result.column("provider_agency_name").null_count > 0
