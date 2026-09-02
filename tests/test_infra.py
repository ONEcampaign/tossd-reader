"""Smoke tests for infra: package import, fixture generator, schema.csv sanity."""

import importlib.resources
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

import tossd_reader
from tests.factories import build_tossd_table, write_tossd_fixture
from tossd_reader import _export, codelists


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


def test_schema_hash_matches_the_published_literal() -> None:
    """schema.csv's exact bytes are published as a hash in the documentation.

    Every byte of the file feeds `_export._schema_hash`, whose value each
    export manifest carries and four documentation pages quote literally.
    That includes the `nullable` column, which no code reads. Changing
    schema.csv means updating this literal alongside
    docs/about/reproducibility.md, docs/how-to/reconcile-a-figure.md,
    docs/tutorials/reproducible-extract.md, and docs/reference/export.md.
    """
    assert (
        _export._schema_hash()
        == "0a95f2c54852817a9db1a2174cffa5bd371d601e5d137a37cb27491182367df9"
    )


# --- packaged group tables: recipient_groups.csv, instrument_groups.csv -------------


def _read_data_csv(*parts: str) -> pd.DataFrame:
    resource = importlib.resources.files("tossd_reader") / "_data"
    for part in parts:
        resource = resource / part
    with importlib.resources.as_file(resource) as path:
        return pd.read_csv(path)


def _read_data_json(*parts: str) -> dict[str, object]:
    resource = importlib.resources.files("tossd_reader") / "_data"
    for part in parts:
        resource = resource / part
    with importlib.resources.as_file(resource) as path:
        return json.loads(path.read_text())


def test_recipient_groups_covers_every_packaged_recipient_code_exactly_once() -> None:
    """Every packaged recipient code is classified exactly once -- no missing, no extra."""
    recipient_codes = set(codelists.load_codelist("recipient")["code"].astype(int))
    groups_df = _read_data_csv("recipient_groups.csv")

    assert groups_df["recipient_code"].is_unique
    assert set(groups_df["recipient_code"]) == recipient_codes


def test_recipient_groups_scheme_columns_only_carry_documented_values() -> None:
    """Each scheme column only carries a value from its documented vocabulary."""
    groups_df = _read_data_csv("recipient_groups.csv")

    valid_ldc = {
        "Least Developed Countries",
        "Other Developing Countries",
        "Regional / Multi-country Unallocated",
    }
    valid_income = {
        "Low income",
        "Lower middle income",
        "Upper middle income",
        "High income",
        "Unclassified",
        "Regional / Multi-country Unallocated",
    }
    assert set(groups_df["ldc_group"]) <= valid_ldc
    assert set(groups_df["income_group"]) <= valid_income


def test_recipient_groups_no_row_is_blank_in_any_scheme_column() -> None:
    """No packaged row leaves any of the three scheme columns blank."""
    groups_df = _read_data_csv("recipient_groups.csv")
    assert not groups_df[["ldc_group", "income_group", "region"]].isna().any().any()


def test_recipient_groups_income_unclassified_is_disjoint_from_unallocated() -> None:
    """The six-territory 'Unclassified' bucket never coincides with the no-iso3 Unallocated one."""
    groups_df = _read_data_csv("recipient_groups.csv")
    unclassified = groups_df.loc[groups_df["income_group"] == "Unclassified"]
    assert (unclassified["ldc_group"] != "Regional / Multi-country Unallocated").all()


_OBSERVED_FINANCE_INSTRUMENT_CODES = frozenset({0, 1101, 1102, 4221, 4222})
"""Codes seen on real rows in the six cached TOSSD vintages (2019-2024) but
absent from OECD's own live List 15 `tossd`-applicable flag as of
2026-09-01 (verified via a direct fetch of codelist_id "15" -- a codelist
refresh can never add them on its own, see
notes/incantation/instrument-groups-spec.md §3 and analysis.py's
add_instrument_group docstring). Pinned here, offline, independent of the
packaged CSV's own `source` column, so this test verifies that column
rather than trusting it."""


def test_instrument_groups_covers_the_codelist_and_the_observed_codes_exactly() -> None:
    """The table maps every packaged codelist code plus every pinned observed code, no others."""
    codelist_codes = set(
        codelists.load_codelist("finance_instrument")["code"].astype(int)
    )
    groups_df = _read_data_csv("instrument_groups.csv")

    assert groups_df["finance_instrument_code"].is_unique
    assert set(groups_df["finance_instrument_code"]) == (
        codelist_codes | _OBSERVED_FINANCE_INSTRUMENT_CODES
    )
    assert codelist_codes.isdisjoint(_OBSERVED_FINANCE_INSTRUMENT_CODES)


def test_instrument_groups_source_column_matches_each_code_s_real_population() -> None:
    """`source` reads 'codelist' for packaged-codelist codes, 'observed' for the pinned set."""
    codelist_codes = set(
        codelists.load_codelist("finance_instrument")["code"].astype(int)
    )
    groups_df = _read_data_csv("instrument_groups.csv")
    by_code = groups_df.set_index("finance_instrument_code")["source"]

    assert set(by_code.loc[list(codelist_codes)]) == {"codelist"}
    assert set(by_code.loc[list(_OBSERVED_FINANCE_INSTRUMENT_CODES)]) == {"observed"}


def test_recipient_groups_version_stamp_parses() -> None:
    """The recipient-groups version JSON parses, with a non-empty version and fetched_at."""
    payload = _read_data_json("recipient_groups_version.json")

    assert payload["version"]
    datetime.fromisoformat(payload["fetched_at"])  # round-trips without raising


def test_instrument_groups_version_stamp_parses() -> None:
    """The instrument-groups version JSON parses, with a non-empty version and fetched_at."""
    payload = _read_data_json("instrument_groups_version.json")

    assert payload["version"]
    datetime.fromisoformat(payload["fetched_at"])  # round-trips without raising
