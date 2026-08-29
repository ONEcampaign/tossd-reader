"""Smoke tests for infra: package import, fixture generator, schema.csv sanity."""

import importlib.resources
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

import tossd_reader
from tests.factories import build_tossd_table, write_tossd_fixture


def test_import_exposes_version() -> None:
    """`import tossd_reader` works and exposes `__version__`."""
    assert isinstance(tossd_reader.__version__, str)
    assert tossd_reader.__version__


def _read_schema() -> pd.DataFrame:
    schema_resource = importlib.resources.files("tossd_reader") / "_data" / "schema.csv"
    with importlib.resources.as_file(schema_resource) as schema_path:
        return pd.read_csv(schema_path, dtype=str, keep_default_na=False)


def test_fixture_roundtrip_matches_schema(tmp_path: Path) -> None:
    """Writing and reading back a 2024 fixture matches the schema table exactly."""
    schema_df = _read_schema()
    fixture_path = write_tossd_fixture(tmp_path / "tossddata_2024.parquet", 2024)

    parquet_file = pq.ParquetFile(fixture_path)
    assert parquet_file.num_row_groups == 1

    arrow_schema = parquet_file.schema_arrow
    assert arrow_schema.names == list(schema_df["published_name"])

    for field_name, expected_arrow_type in zip(
        arrow_schema.names, schema_df["arrow_type"], strict=True
    ):
        assert str(arrow_schema.field(field_name).type) == expected_arrow_type, (
            field_name
        )

    table = parquet_file.read()
    string_columns = schema_df.loc[
        schema_df["arrow_type"] == "string", "published_name"
    ]
    for column_name in string_columns:
        assert table.column(column_name).null_count == 0, column_name

    project_titles = table.column("ProjectTitle").to_pylist()
    provider_codes = table.column("provider").to_pylist()
    assert any(
        code == "0" and title == "Non-concessional flows: semi-aggregates"
        for code, title in zip(provider_codes, project_titles, strict=True)
    )

    sdgcodes = table.column("sdgcode").to_pylist()
    keywords = table.column("keywords").to_pylist()
    assert any(";" in value for value in sdgcodes if value)
    assert any("|" in value for value in keywords if value)


def test_fixture_generator_is_deterministic() -> None:
    """Identical arguments to `build_tossd_table` produce an identical table."""
    first = build_tossd_table(2024, n_rows=50, seed=7)
    second = build_tossd_table(2024, n_rows=50, seed=7)
    assert first.equals(second)


def test_schema_csv_sanity() -> None:
    """schema.csv row counts, preset counts, and name uniqueness hold."""
    schema_df = _read_schema()

    assert len(schema_df) == 53
    assert (schema_df["is_usd_thousand_amount"] == "true").sum() == 8
    assert (schema_df["preset_minimal"] == "true").sum() == 17
    assert (schema_df["preset_analysis"] == "true").sum() == 42
    assert schema_df["snake_name"].is_unique
    assert schema_df["published_name"].is_unique
