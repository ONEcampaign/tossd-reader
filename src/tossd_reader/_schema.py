"""Read-time schema layer for published TOSSD parquet vintages.

Private module. Consumed by query.py (and the tests).

Drift contract: a published file missing a column the packaged schema expects
is a hard `SchemaDriftError` — never silently dropped or nulled. A published
file carrying a column the packaged schema doesn't know about is not an
error: it warns once per session and passes through raw, visible only in
`columns="all"`.
"""

from __future__ import annotations

import csv
import warnings
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import pyarrow as pa
import pyarrow.compute as pc

from tossd_reader import _resources
from tossd_reader.exceptions import SchemaDriftError

_SEPARATOR_TABLE = str.maketrans("", "", "_- ")

_INT_TARGET_TYPES: dict[str, pa.DataType] = {
    "Int8": pa.int8(),
    "Int16": pa.int16(),
    "Int32": pa.int32(),
}

_CODE_CASE_FIXES: dict[str, dict[str, str]] = {
    # {snake_name: {published variant: canonical form}}. One documented case
    # today (modality `c01` -> `C01`); a future one is a single extra line.
    "modality_code": {"c01": "C01"},
}


@dataclass(frozen=True)
class SchemaField:
    """One row of the packaged schema table (`_data/schema.csv`).

    Attributes:
        published_name: The column name as it appears in the publisher's file.
        snake_name: The renamed, snake_case column name this package exposes.
        arrow_type: The raw arrow type the column arrives as (`"string"` or
            `"double"`), before any typed cast.
        target_dtype: The dtype `apply_schema` casts the column to:
            `"Int8"`/`"Int16"`/`"Int32"` (nullable arrow ints), `"category"`
            (dictionary-encoded), `"float64"`, or `"string"` (left as-is).
        nullable: Whether the publisher has ever shipped a real null/empty
            value for this column. Informational only; not consumed
            anywhere in this package.
        preset_minimal: Whether the column is included in the `"minimal"`
            preset.
        preset_analysis: Whether the column is included in the `"analysis"`
            preset.
        is_usd_thousand_amount: Whether the column is one of the 8 USD amount
            fields (reported in USD thousands). Consumed by the query layer,
            not by anything in this module.
    """

    published_name: str
    snake_name: str
    arrow_type: str
    target_dtype: str
    nullable: bool
    preset_minimal: bool
    preset_analysis: bool
    is_usd_thousand_amount: bool


class _SchemaState:
    """Mutable singleton state backing this module's warn-once accessor."""

    def __init__(self) -> None:
        self.warned_unknown_columns: set[str] = set()


_state = _SchemaState()


@lru_cache
def load_schema() -> tuple[SchemaField, ...]:
    """Parse the packaged schema table (`_data/schema.csv`) once, in file order.

    Cached for the life of the process — the packaged schema table never
    changes at runtime.
    """
    with _resources.data_path("schema.csv") as path, path.open(newline="") as handle:
        return tuple(_parse_row(row) for row in csv.DictReader(handle))


def _parse_row(row: dict[str, str]) -> SchemaField:
    """Build one `SchemaField` from a `csv.DictReader` row."""
    return SchemaField(
        published_name=row["published_name"],
        snake_name=row["snake_name"],
        arrow_type=row["arrow_type"],
        target_dtype=row["target_dtype"],
        nullable=row["nullable"] == "true",
        preset_minimal=row["preset_minimal"] == "true",
        preset_analysis=row["preset_analysis"] == "true",
        is_usd_thousand_amount=row["is_usd_thousand_amount"] == "true",
    )


def preset_columns(preset: Literal["minimal", "analysis", "all"]) -> list[str]:
    """Return the snake_case column names for `preset`, in schema.csv order.

    Args:
        preset: `"minimal"`, `"analysis"`, or `"all"`.

    Returns:
        Snake_case column names. Validation of arbitrary user-supplied column
        lists happens in the query layer, not here.

    Raises:
        ValueError: `preset` is not one of the three recognised names.
    """
    fields = load_schema()
    if preset == "all":
        return [field.snake_name for field in fields]
    if preset == "minimal":
        return [field.snake_name for field in fields if field.preset_minimal]
    if preset == "analysis":
        return [field.snake_name for field in fields if field.preset_analysis]
    raise ValueError(
        f"Unknown preset {preset!r}; expected 'minimal', 'analysis', or 'all'."
    )


def apply_schema(
    table: pa.Table, *, file_column_names: Iterable[str] | None = None
) -> pa.Table:
    """Rename, clean, and typecast one published TOSSD vintage table.

    Arrow-level throughout: no pandas conversion happens here. In order:
    1. Match `schema.csv`'s `published_name`s to `table`'s actual column names
       by normalised key (casefold, `_`/`-`/space-insensitive).
    2. Two or more actual column names normalising to the same key is
       ambiguous and raises `SchemaDriftError` naming every colliding column,
       before any of the missing/extra logic below runs.
    3. A schema-expected column absent from `file_column_names` raises
       `SchemaDriftError`.
    4. A `file_column_names` entry not in the schema warns once per session.
       If it's also present in `table`, it passes through under its original
       name, unchanged.
    5. Matched columns actually present in `table` are renamed to
       `snake_name`.
    6. Empty strings become null, for every string- or large-string-typed
       column.
    7. Known code-case drift is normalised (e.g. modality `c01` -> `C01`).
    8. Matched columns are cast to `target_dtype`. A cast failure raises
       `SchemaDriftError` naming the column and the offending value — never a
       silent null.

    A schema-expected column absent from `table` but present in
    `file_column_names` is neither an error nor a warning: it's simply
    omitted from the result, on the assumption the caller deliberately chose
    not to read it (a column projection narrower than the file).

    Args:
        table: One vintage's raw, publisher-bytes-verbatim table (as returned
            by reading `fetch_year`'s cached parquet with pyarrow, unmodified
            or narrowed by a column projection).
        file_column_names: The full column-name list as published in the
            source file (e.g. from `pyarrow.parquet.read_schema`, cheap
            metadata that needs no data read). Defaults to
            `table.column_names`, which is correct whenever `table` already
            carries every published column. Pass this explicitly
            when `table` was read with a column projection narrower than the
            file, so the missing-expected-column drift check and the
            unknown-extra warn-once still see the file's true column set —
            a column deliberately not read is then never mistaken for the
            publisher having dropped it.

    Returns:
        A new `pa.Table`: schema columns actually present in `table` renamed
        and typed, schema.csv order first, followed by any unknown extra
        columns (also actually present in `table`) passed through raw.

    Raises:
        SchemaDriftError: Two or more actual columns normalise to the same
            key; a schema-expected column is missing from
            `file_column_names`; or a matched column's values cannot be cast
            to its `target_dtype`.
    """
    fields = load_schema()
    matched_keys = {_normalise_key(field.published_name) for field in fields}

    table_names_by_key: dict[str, list[str]] = {}
    for name in table.column_names:
        table_names_by_key.setdefault(_normalise_key(name), []).append(name)

    colliding_names = sorted(
        name
        for names in table_names_by_key.values()
        if len(names) > 1
        for name in names
    )
    if colliding_names:
        raise SchemaDriftError(
            "Multiple published columns normalise to the same key and cannot "
            f"be matched unambiguously: {', '.join(colliding_names)}."
        )

    table_by_key = {key: names[0] for key, names in table_names_by_key.items()}

    file_names = (
        list(table.column_names)
        if file_column_names is None
        else list(file_column_names)
    )
    file_keys = {_normalise_key(name) for name in file_names}

    missing = [
        field.published_name
        for field in fields
        if _normalise_key(field.published_name) not in file_keys
    ]
    if missing:
        raise SchemaDriftError(
            "The published file is missing expected column(s): "
            f"{', '.join(missing)}. This usually means the publisher changed "
            "its schema; tossd_reader's packaged schema.csv may need updating."
        )

    extra_in_file = [
        name for name in file_names if _normalise_key(name) not in matched_keys
    ]
    _warn_unknown_columns(extra_in_file)

    names: list[str] = []
    arrays: list[pa.ChunkedArray | pa.Array] = []
    for field in fields:
        key = _normalise_key(field.published_name)
        if key not in table_by_key:
            # Deliberately not read (a narrower-than-file projection); already
            # confirmed present in file_column_names above, so this is not drift.
            continue
        actual_name = table_by_key[key]
        column = table.column(actual_name)
        if pa.types.is_string(column.type) or pa.types.is_large_string(column.type):
            column = _empty_string_to_null(column)
        column = _apply_code_case_fix(column, field.snake_name)
        column = _cast_column(column, field)
        names.append(field.snake_name)
        arrays.append(column)

    extra_names_in_table = [
        name for key, name in table_by_key.items() if key not in matched_keys
    ]
    for name in extra_names_in_table:
        names.append(name)
        arrays.append(table.column(name))

    return pa.table(arrays, names=names)


def _normalise_key(name: str) -> str:
    """Casefold `name` and drop `_`, `-`, and spaces for drift-tolerant matching."""
    return name.casefold().translate(_SEPARATOR_TABLE)


def _empty_string_to_null(
    column: pa.ChunkedArray | pa.Array,
) -> pa.ChunkedArray | pa.Array:
    """Turn every empty-string value in a string column into a real null."""
    is_empty = pc.equal(column, "")  # ty: ignore[unresolved-attribute]
    return pc.if_else(  # ty: ignore[unresolved-attribute]
        is_empty, pa.scalar(None, type=column.type), column
    )


def _apply_code_case_fix(
    column: pa.ChunkedArray | pa.Array, snake_name: str
) -> pa.ChunkedArray | pa.Array:
    """Normalise known code-case drift (declarative `_CODE_CASE_FIXES`) for one column."""
    fixes = _CODE_CASE_FIXES.get(snake_name)
    if not fixes:
        return column
    for variant, canonical in fixes.items():
        is_variant = pc.equal(column, variant)  # ty: ignore[unresolved-attribute]
        column = pc.if_else(  # ty: ignore[unresolved-attribute]
            is_variant, pa.scalar(canonical, type=column.type), column
        )
    return column


def _cast_column(
    column: pa.ChunkedArray | pa.Array, field: SchemaField
) -> pa.ChunkedArray | pa.Array:
    """Cast one matched column to its `target_dtype`, per `SchemaField`."""
    target = field.target_dtype
    if target == "string":
        return column
    if target == "category":
        return pc.dictionary_encode(column)  # ty: ignore[unresolved-attribute]
    if target == "float64":
        return _safe_cast(column, pa.float64(), column_name=field.snake_name)
    if target in _INT_TARGET_TYPES:
        return _safe_cast(
            column, _INT_TARGET_TYPES[target], column_name=field.snake_name
        )
    raise AssertionError(f"schema.csv has an unrecognised target_dtype {target!r}")


def _safe_cast(
    column: pa.ChunkedArray | pa.Array, target_type: pa.DataType, *, column_name: str
) -> pa.ChunkedArray | pa.Array:
    """Cast `column` to `target_type`, or raise `SchemaDriftError` naming the offender.

    Never falls back to silently coercing an uncastable value to null.
    """
    try:
        return pc.cast(column, target_type)
    except pa.lib.ArrowInvalid as exc:
        sample = _first_uncastable_value(column, target_type)
        raise SchemaDriftError(
            f"Column {column_name!r} contains a value that cannot be cast to "
            f"{target_type}: {sample!r}."
        ) from exc


def _first_uncastable_value(
    column: pa.ChunkedArray | pa.Array, target_type: pa.DataType
) -> str | None:
    """Find the first distinct value in `column` that fails to cast to `target_type`."""
    for value in column.drop_null().unique().to_pylist():
        try:
            pc.cast(pa.array([value], type=pa.string()), target_type)
        except pa.lib.ArrowInvalid:
            return value
    return None


def _warn_unknown_columns(names: list[str]) -> None:
    """Warn once per never-before-seen unknown column name in `names`."""
    new_names = [name for name in names if name not in _state.warned_unknown_columns]
    if not new_names:
        return
    _state.warned_unknown_columns.update(new_names)
    warnings.warn(
        "The published file has column(s) not in tossd_reader's packaged "
        f"schema: {', '.join(new_names)}. Passed through unchanged; only "
        'visible with columns="all".',
        stacklevel=3,
    )


def _reset_for_tests() -> None:
    """Clear the warn-once state for unknown columns.

    Test-only. `conftest.py` does not reset per-module state between tests,
    so this module's own tests reset it directly instead.
    """
    _state.warned_unknown_columns.clear()
