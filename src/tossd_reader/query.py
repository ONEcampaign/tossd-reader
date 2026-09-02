"""The typed, filtered `get_tossd` query layer.

Per requested year: `fetch.resolve_year` → a column-projected pyarrow read (only the
output columns plus internal-only needs -- `is_aggregate`'s `provider_code`, a row
filter's `recipient_code`, the decode join's `parent_channel_code` -- unless
`columns="all"`, which reads every column) → `_schema.apply_schema` (given the file's
full column list from the cheap, data-free `pq.read_schema`, so the projection never
masquerades as publisher drift) → `_mask_subpillar_sentinels` (folds every
`tossd_subpillar` value that isn't a real `"21"`/`"22"` tag to null) → arrow-level row
filters (provider/recipient/pillar). Then, once across every year:
`pa.concat_tables(...).unify_dictionaries()` (a categorical column stays
dictionary-encoded across a multi-year query), a categorical strip (only when at least
one row filter ran -- see `_strip_unused_categories`), derived columns (`is_aggregate`,
`unit`, the `parent_channel_code` decode -- skipped entirely when `parent_channel_name`
isn't requested), preset/column projection, units conversion, and exactly one
`.to_pandas()` call at the very end.

Discovery is swept once per `get_tossd` call (not once per requested year),
the same `sweep_or_none` pattern `fetch.get_tossd_raw` already uses. A
year outside the packaged known-years set is honoured or rejected by
`fetch.resolve_year` itself, the sole place that logic lives.

Pillar/sub-pillar token resolution lives in `_pillars.py`; `providers=`/
`recipients=` code resolution lives in `_matching.py`.
"""

from __future__ import annotations

import difflib
import warnings
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from readerkit.refresh import effective_refresh

from tossd_reader import (
    _accessor,  # noqa: F401 - registers df.tossd
    _matching,
    _pillars,
    _provenance,
    _schema,
    codelists,
    config,
    fetch,
)
from tossd_reader.exceptions import UnknownCodeError

# A bare `to_pandas()` widens any Arrow integer column holding nulls to
# `float64`, so `sector_code` would read `910.0` and `schema.csv`'s declared
# `Int16` would not survive the round-trip. Passing this as `types_mapper`
# keeps the delivered frame matching the packaged schema. Plain name:
# consumed by `_export.load_export` as well as `get_tossd`.
ARROW_TO_PANDAS_INT: dict[pa.DataType, pd.api.extensions.ExtensionDtype] = {
    pa.int8(): pd.Int8Dtype(),
    pa.int16(): pd.Int16Dtype(),
    pa.int32(): pd.Int32Dtype(),
}

_VALID_UNITS = ("usd_thousand", "usd_million", "usd")

# Columns `get_tossd` (and `export`) always include, regardless of `columns=`.
# Public (re-exported from `tossd_reader` via `__init__.py`'s lazy-attr map)
# so a caller can check membership before building an explicit `columns=`
# list, rather than rediscovering by trial that e.g. `year` survives any
# selection.
FORCED_COLUMNS = ("year", "tossd_pillar", "tossd_subpillar", "is_aggregate", "unit")

_DECODE_CHANNEL_DIMENSION = "channel"
_DECODE_CODE_COLUMN = "parent_channel_code"
_DECODE_NAME_COLUMN = "parent_channel_name"


_warned_unknown_codes: dict[str, set[str]] = {}


def get_tossd(
    *,
    years: int | Iterable[int] | None = None,
    providers: int | str | Iterable[int | str] | None = None,
    recipients: int | str | Iterable[int | str] | None = None,
    pillars: int | str | None = None,
    columns: Literal["all", "minimal", "analysis"] | list[str] = "all",
    units: Literal["usd_thousand", "usd_million", "usd"] = "usd_thousand",
    include_aggregates: bool = True,
    refresh: bool = False,
) -> pd.DataFrame:
    """Return typed, filtered TOSSD activity-level data.

    Args:
        years: A single year, an iterable of years (a `range` included, so
            `range(2022, 2024)` requests 2022 and 2023 only — Python's usual
            exclusive-end semantics), or `None` (the default) for the
            packaged known-years set. A year outside that set is honoured
            when the publisher's discovery sweep currently lists it,
            otherwise raises naming the years available right now.
        providers: Filter to one or more providers. An `int` (or iterable of
            `int`) is a provider code. A `str` is matched case-foldedly
            against the packaged provider codelist's `name` column; a
            digit-string (e.g. `"302"`) tries an exact code match first,
            then falls back to a name match. `None` (the default) applies
            no provider filter.
        recipients: Same resolution rules as `providers`, against the
            packaged recipient codelist.
        pillars: `1`/`"1"`/`"I"` (case-insensitive) for pillar 1;
            `2`/`"2"`/`"II"` for pillar 2 (both sub-pillars and untagged
            pillar-2 rows); `21`/`"21"`/`"II.A"` or `22`/`"22"`/`"II.B"` for
            one sub-pillar specifically. `None` (the default) applies no
            pillar filter — pillar-`0` placeholder rows (a 2020-2023
            publisher artefact) are then included; every other `pillars=`
            value excludes them. A sub-pillar filter combined with an
            *explicit* `years` that includes any year before 2023 raises
            `InvalidPillarError` (sub-pillar tagging did not exist yet,
            bar a 24-row 2022 trace); with the default `years=None` it
            instead silently narrows to years >= 2023, with one warning.
            Independent of this filter, the output `tossd_subpillar` column is `NA`
            unless a row carries a real `"21"`/`"22"` tag -- pillar-1 rows, untagged
            pillar-2 rows, and pillar-0 rows all read `NA`, so `.notna()` identifies
            sub-pillar-tagged rows specifically, a narrower set than pillar-2 rows
            overall.
        columns: `"all"` (default, every packaged column), `"minimal"`,
            `"analysis"` (see `_schema.preset_columns`), or an explicit
            `list[str]` of snake_case column names. `FORCED_COLUMNS`
            (`year`, `tossd_pillar`, `tossd_subpillar`, `is_aggregate`, and
            `unit`) are always present in the result regardless of this
            selection.
        units: `"usd_thousand"` (default, as published), `"usd_million"`
            (divides every `schema.csv` `is_usd_thousand_amount` column by
            1000), or `"usd"` (multiplies the same columns by 1000, since
            the published scale is thousands).
        include_aggregates: `True` (the default) keeps every row,
            including the `provider_code == 0` pseudo-aggregate rows the
            publisher includes alongside individual providers' own
            activity-level records -- so the default output matches the
            published records in full. `False` drops them (an arrow-level
            `provider_code != 0` filter, applied per year, before the
            cross-year concat). The `tossd_reader.verbs` aggregation
            functions default the other way (`include_aggregates=False`),
            since summing across both would double-count.
        refresh: Re-run discovery's HEAD sweep and force a readerkit
            conditional GET for every requested year. An enclosing
            `readerkit.refresh_scope()` has the same effect.

    Returns:
        A `pandas.DataFrame`, one row per activity matching every filter,
        across every requested year. An empty result (after filtering)
        still comes back correctly typed, with one warning. `df.attrs
        ["tossd_reader"]` carries this call's own provenance (the
        normalised query, plus each fetched year's etag/retrieved_at/url)
        -- read it back with `get_provenance(df)` rather than the raw
        `attrs` key directly.

    Raises:
        ValueError: `units` is not `"usd_thousand"`/`"usd_million"`/`"usd"`;
            `columns` names an unknown column (or an unrecognised preset);
            `years` resolves to an empty set of years; a requested year
            is not currently published and nothing is cached for it; or
            `refresh=True` while offline mode is active
            (`config.get_offline()` is `True`).
        UnknownCodeError: A `providers`/`recipients` token (name, code, or
            digit-string) does not match the packaged codelist.
        InvalidPillarError: A sub-pillar filter is requested for an
            explicit year before 2023.
        TossdNetworkError: The publisher is unreachable and nothing usable
            is cached for a requested year.
        SchemaDriftError: A requested year's published file no longer
            matches the packaged schema.
    """
    combined, paths = build_table(
        years=years,
        providers=providers,
        recipients=recipients,
        pillars=pillars,
        columns=columns,
        units=units,
        include_aggregates=include_aggregates,
        refresh=refresh,
        op_name="tossd_reader:get_tossd",
    )
    df = combined.to_pandas(types_mapper=ARROW_TO_PANDAS_INT.get)
    df.attrs[_provenance.ATTRS_KEY] = _build_get_tossd_provenance(
        providers=providers,
        recipients=recipients,
        pillars=pillars,
        columns=columns,
        units=units,
        include_aggregates=include_aggregates,
        refresh=refresh,
        paths=paths,
    )
    return df


def _build_get_tossd_provenance(
    *,
    providers: int | str | Iterable[int | str] | None,
    recipients: int | str | Iterable[int | str] | None,
    pillars: int | str | None,
    columns: Literal["all", "minimal", "analysis"] | list[str],
    units: Literal["usd_thousand", "usd_million", "usd"],
    include_aggregates: bool,
    refresh: bool,
    paths: dict[int, Path],
) -> dict[str, object]:
    """Build `get_tossd()`'s `df.attrs["tossd_reader"]` payload.

    `providers`/`recipients` are re-resolved to codes here (already resolved once, inside
    `build_table`) rather than threaded through its return value: both calls are pure,
    side-effect-free lookups against the packaged codelists, so recomputing them is cheaper than
    widening `build_table`'s own return contract (also used directly by `export()` and by
    existing tests) just to carry them out.
    """
    provider_codes = _matching.resolve_dimension_codes(
        providers, dimension="provider", label="providers"
    )
    recipient_codes = _matching.resolve_dimension_codes(
        recipients, dimension="recipient", label="recipients"
    )
    query_dict = {
        "years": tuple(paths),
        "providers": provider_codes,
        "recipients": recipient_codes,
        "pillars": pillars,
        "columns": columns,
        "units": units,
        "include_aggregates": include_aggregates,
        "refresh": refresh,
    }
    return _provenance.build_attrs(query=query_dict, paths=paths)


def build_table(
    *,
    years: int | Iterable[int] | None,
    providers: int | str | Iterable[int | str] | None,
    recipients: int | str | Iterable[int | str] | None,
    pillars: int | str | None,
    columns: Literal["all", "minimal", "analysis"] | list[str],
    units: Literal["usd_thousand", "usd_million", "usd"],
    include_aggregates: bool = True,
    refresh: bool,
    op_name: str,
) -> tuple[pa.Table, dict[int, Path]]:
    """Run `get_tossd`'s pipeline through unit conversion, stopping short of `to_pandas`.

    The seam `export()` reuses: everything `get_tossd` does (per-year fetch,
    schema, row filters; cross-year concat/unify; derived columns; column
    projection; units conversion) except the final `to_pandas()` call, so
    `export()` can write the arrow table straight to parquet without a
    pandas round-trip.

    Args:
        op_name: A cache-surface-qualified key for `effective_refresh`,
            distinct per caller (`get_tossd` vs `export`) so the two never
            share a `readerkit.refresh_scope()` claim.

    Returns:
        The combined, filtered, typed arrow table, alongside each resolved
        year's cache path (so `export()` can read per-year provenance
        sidecars without re-running discovery/fetch).

    Raises:
        ValueError: `refresh=True` while offline mode is active (`config.get_offline()` is
            `True`) -- shared by every caller (`get_tossd`, `export`) via this one seam.
    """
    config.raise_if_offline_refresh_conflict(
        refresh=refresh, func_name=op_name.removeprefix("tossd_reader:")
    )
    if units not in _VALID_UNITS:
        raise ValueError(f"Unknown units {units!r}; expected one of {_VALID_UNITS}.")

    years_was_none = years is None
    resolved_years = fetch.normalise_years(years)

    pillar_main, pillar_sub = (
        (None, None) if pillars is None else _pillars.normalise_pillar_token(pillars)
    )
    if pillar_sub is not None:
        resolved_years = _pillars.resolve_subpillar_years(
            resolved_years, years_was_none=years_was_none
        )

    provider_codes = _matching.resolve_dimension_codes(
        providers, dimension="provider", label="providers"
    )
    recipient_codes = _matching.resolve_dimension_codes(
        recipients, dimension="recipient", label="recipients"
    )
    column_names = _resolve_columns(columns)
    decode_parent_channel = _DECODE_NAME_COLUMN in column_names
    read_all = columns == "all"
    needed_snake_columns = _needed_read_columns(
        column_names,
        recipient_codes=recipient_codes,
        decode_parent_channel=decode_parent_channel,
    )

    # Resolved once for the whole call, not once per requested year: see
    # fetch.get_tossd_raw's own comment for why.
    effective = effective_refresh(op_name, explicit=refresh)
    vintages = fetch.sweep_or_none(effective)

    tables = []
    paths: dict[int, Path] = {}
    for year in resolved_years:
        path = fetch.resolve_year(year, vintages=vintages, refresh=effective)
        paths[year] = path
        file_column_names = list(pq.read_schema(path).names)
        if read_all:
            raw = pq.read_table(path)
        else:
            read_columns = _published_names_to_read(
                needed_snake_columns, file_column_names=file_column_names
            )
            raw = pq.read_table(path, columns=read_columns)
        typed = _schema.apply_schema(raw, file_column_names=file_column_names)
        typed = _mask_subpillar_sentinels(typed)
        filtered = _apply_row_filters(
            typed,
            provider_codes=provider_codes,
            recipient_codes=recipient_codes,
            pillar_main=pillar_main,
            pillar_sub=pillar_sub,
            include_aggregates=include_aggregates,
        )
        tables.append(filtered)

    combined = pa.concat_tables(tables).unify_dictionaries()
    row_filter_ran = (
        provider_codes is not None
        or recipient_codes is not None
        or pillar_main is not None
        or not include_aggregates
    )
    if row_filter_ran:
        combined = _strip_unused_categories(combined)
    combined = _add_derived_columns(
        combined, units=units, decode_parent_channel=decode_parent_channel
    )
    if columns == "all":
        column_names = _with_passthrough_extras(column_names, combined.column_names)
    combined = combined.select(column_names)
    combined = _convert_units(combined, units=units)

    if combined.num_rows == 0:
        warnings.warn(
            "get_tossd's filters matched no rows; returning an empty (but "
            "correctly typed) frame.",
            stacklevel=3,
        )

    return combined, paths


# --- row filters (arrow-level, applied per year before concat) ----------------


def _apply_row_filters(
    table: pa.Table,
    *,
    provider_codes: tuple[int, ...] | None,
    recipient_codes: tuple[int, ...] | None,
    pillar_main: str | None,
    pillar_sub: str | None,
    include_aggregates: bool,
) -> pa.Table:
    """Apply every requested filter to one year's already-typed table."""
    if provider_codes is not None:
        table = _filter_codes(table, "provider_code", provider_codes, label="providers")
    if recipient_codes is not None:
        table = _filter_codes(
            table, "recipient_code", recipient_codes, label="recipients"
        )
    if pillar_main is not None:
        table = _filter_pillar(table, pillar_main, pillar_sub)
    if not include_aggregates:
        table = _filter_aggregates(table)
    return table


def _filter_aggregates(table: pa.Table) -> pa.Table:
    """Keep only rows whose `provider_code` isn't the aggregate sentinel (`0`).

    `provider_code` is always read regardless of `columns=` (the forced
    `is_aggregate` derived column needs it too), so this needs no
    projection change.
    """
    mask = pc.not_equal(table.column("provider_code"), 0)  # ty: ignore[unresolved-attribute]
    return table.filter(mask)


def _filter_codes(
    table: pa.Table, column_name: str, codes: tuple[int, ...], *, label: str
) -> pa.Table:
    """Keep only rows whose `column_name` value is one of `codes`.

    A plain `int` token is trusted directly as a code (never checked against
    the packaged codelist -- see `_matching._resolve_one_code`), but it still has to
    fit the file's actual column type (`Int16` for both `provider_code` and
    `recipient_code` today). A value that doesn't raises `UnknownCodeError`
    naming the offender, rather than leaking pyarrow's own `ArrowInvalid`.
    """
    column = table.column(column_name)
    values = _codes_as_array(codes, column.type, label=label)
    return table.filter(pc.is_in(column, value_set=values))  # ty: ignore[unresolved-attribute]


def _codes_as_array(
    codes: tuple[int, ...], target_type: pa.DataType, *, label: str
) -> pa.Array:
    """Cast `codes` to `target_type`, raising `UnknownCodeError` naming any out-of-range value."""
    try:
        return pa.array(codes, type=target_type)
    except pa.lib.ArrowInvalid as exc:
        offending = [code for code in codes if _code_overflows(code, target_type)]
        values = ", ".join(str(code) for code in offending)
        raise UnknownCodeError(
            f"{values} did not match any {label} code: outside the range "
            f"representable by the published file's {target_type} column."
        ) from exc


def _code_overflows(code: int, target_type: pa.DataType) -> bool:
    """Whether `code` cannot be represented as `target_type` (e.g. Int16 overflow)."""
    try:
        pa.array([code], type=target_type)
    except pa.lib.ArrowInvalid:
        return True
    return False


def _filter_pillar(
    table: pa.Table, pillar_main: str, pillar_sub: str | None
) -> pa.Table:
    """Keep only rows matching `pillar_main` (and `pillar_sub`, if given).

    Pillar-`0` placeholder rows never match `tossd_pillar in {1, 2}`, so every
    `pillars=` filter excludes them automatically.
    """
    mask = pc.equal(table.column("tossd_pillar"), int(pillar_main))  # ty: ignore[unresolved-attribute]
    if pillar_sub is not None:
        subpillar_mask = pc.equal(table.column("tossd_subpillar"), pillar_sub)  # ty: ignore[unresolved-attribute]
        mask = pc.and_(mask, subpillar_mask)  # ty: ignore[unresolved-attribute]
    return table.filter(mask)


_REAL_SUBPILLAR_TAGS = ("21", "22")


def _mask_subpillar_sentinels(table: pa.Table) -> pa.Table:
    """Null out `tossd_subpillar` unless the row carries a real II.A/II.B tag.

    The published column also carries `"1"` (every pillar-1 row), `"2"`
    (untagged pillar-2 rows), and whatever placeholder value pillar-0 rows
    hold -- none of those is a sub-pillar tag, so `.notna()` on the raw
    column would be a false positive on most of the file. Only `"21"`/`"22"`
    survive; every other value (already-null included) becomes null, so
    `tossd_subpillar`'s categories become exactly `{"21", "22"}`. Applied
    per year, right after `_schema.apply_schema`, before the row filters --
    `_filter_pillar`'s own `"21"`/`"22"` equality checks are unaffected
    either way, since this never touches those two values.

    `get_tossd_raw()` never runs through this (or any) schema/derived step,
    so the published sentinels stay reachable there, verbatim.
    """
    index = table.column_names.index("tossd_subpillar")
    field = table.schema.field(index)
    column = table.column(index)
    decoded = pc.cast(column, field.type.value_type)
    real_tags = pa.array(_REAL_SUBPILLAR_TAGS, type=field.type.value_type)
    is_real_tag = pc.is_in(decoded, value_set=real_tags)  # ty: ignore[unresolved-attribute]
    masked = pc.if_else(  # ty: ignore[unresolved-attribute]
        is_real_tag, decoded, pa.scalar(None, type=field.type.value_type)
    )
    return table.set_column(index, "tossd_subpillar", pc.dictionary_encode(masked))  # ty: ignore[unresolved-attribute]


def _strip_unused_categories(table: pa.Table) -> pa.Table:
    """Re-encode every dictionary-typed column so its dictionary holds only values actually present.

    Only called when a `providers=`/`recipients=`/`pillars=` row filter ran:
    a categorical column's dictionary otherwise keeps every value from the
    unfiltered file even after row filtering has dropped every row carrying
    most of them, so a caller's `observed=False` groupby (pandas' own
    default) crosses filtered-out categories back in. Decoding to the plain
    value type and re-encoding collapses each dictionary to the filtered
    data's actual vocabulary; called once, right after the per-year tables
    are concatenated and their dictionaries unified, before column
    projection.
    """
    for index, field in enumerate(table.schema):
        if not pa.types.is_dictionary(field.type):
            continue
        column = table.column(index)
        decoded = pc.cast(column, field.type.value_type)
        table = table.set_column(index, field.name, pc.dictionary_encode(decoded))  # ty: ignore[unresolved-attribute]
    return table


# --- column projection (read-time pushdown) -----------------------------------


def _needed_read_columns(
    column_names: list[str],
    *,
    recipient_codes: tuple[int, ...] | None,
    decode_parent_channel: bool,
) -> list[str]:
    """Snake-case schema columns actually needed from the file for this query.

    Always the already-resolved output columns (`column_names`, schema
    columns among them), plus purely internal dependencies not necessarily
    in the output: `provider_code` (the forced `is_aggregate` derived column
    always reads it, regardless of any `providers=` filter or column
    selection), `recipient_code` when a `recipients=` filter is set, and
    `parent_channel_code` when the channel-codelist decode join is going to
    run (i.e. `parent_channel_name` is requested). `year`, `tossd_pillar`,
    and `tossd_subpillar` need no separate entry here: all three are
    always-forced output columns (`FORCED_COLUMNS`), already in
    `column_names`.
    """
    schema_snake_names = {field.snake_name for field in _schema.load_schema()}
    needed = [name for name in column_names if name in schema_snake_names]
    if "provider_code" not in needed:
        needed.append("provider_code")
    if recipient_codes is not None and "recipient_code" not in needed:
        needed.append("recipient_code")
    if decode_parent_channel and _DECODE_CODE_COLUMN not in needed:
        needed.append(_DECODE_CODE_COLUMN)
    return needed


def _published_names_to_read(
    snake_names: list[str], *, file_column_names: list[str]
) -> list[str]:
    """Map `snake_names` to published names, keeping only those present in the file.

    A schema column missing from the file entirely is real drift, surfaced
    by `_schema.apply_schema`'s `file_column_names`-driven check right after
    this projected read runs -- never silently narrowed away here.
    """
    file_names = set(file_column_names)
    published_by_snake = {
        field.snake_name: field.published_name for field in _schema.load_schema()
    }
    read_columns: list[str] = []
    for name in snake_names:
        published = published_by_snake.get(name)
        if (
            published is not None
            and published in file_names
            and published not in read_columns
        ):
            read_columns.append(published)
    return read_columns


# --- derived columns, decode, projection, units -------------------------------


def _add_derived_columns(
    table: pa.Table, *, units: str, decode_parent_channel: bool
) -> pa.Table:
    """Append `is_aggregate`/`unit`, then decode `parent_channel_name` if requested."""
    is_aggregate = pc.equal(table.column("provider_code"), 0)  # ty: ignore[unresolved-attribute]
    table = table.append_column("is_aggregate", is_aggregate)
    unit_values = pa.array([units] * table.num_rows, type=pa.string())
    table = table.append_column("unit", pc.dictionary_encode(unit_values))  # ty: ignore[unresolved-attribute]
    if decode_parent_channel:
        table = _decode_parent_channel(table)
    return table


def _decode_parent_channel(table: pa.Table) -> pa.Table:
    """Join `parent_channel_name` from the channel codelist (its in-file name is empty)."""
    channel = codelists.load_codelist(_DECODE_CHANNEL_DIMENSION)
    column = table.column(_DECODE_CODE_COLUMN)
    codes = pc.cast(pa.array(channel["code"]), column.type)
    names = pa.array(channel["name"])
    indices = pc.index_in(column, value_set=codes)  # ty: ignore[unresolved-attribute]
    decoded = pc.take(names, indices)

    missing_mask = pc.and_(  # ty: ignore[unresolved-attribute]
        pc.is_valid(column),  # ty: ignore[unresolved-attribute]
        pc.is_null(indices),  # ty: ignore[unresolved-attribute]
    )
    missing_values = pc.unique(column.filter(missing_mask)).to_pylist()  # ty: ignore[unresolved-attribute]
    _warn_unknown_decode_codes(_DECODE_CODE_COLUMN, missing_values)

    return table.set_column(
        table.column_names.index(_DECODE_NAME_COLUMN), _DECODE_NAME_COLUMN, decoded
    )


def _warn_unknown_decode_codes(column_name: str, missing_values: list[object]) -> None:
    """Warn once (per never-before-seen code) that a decode column's code is unmapped.

    Aggregated end-of-query warning: only the codes not already warned about
    this session are counted, so a second query over the same unknown codes
    stays quiet.
    """
    already_warned = _warned_unknown_codes.setdefault(column_name, set())
    new_missing = sorted(
        {str(value) for value in missing_values} - already_warned, key=str
    )
    if not new_missing:
        return
    already_warned.update(new_missing)
    warnings.warn(
        f"{len(new_missing)} code(s) across 1 column(s) not in the packaged "
        "codelists (vintage newer than snapshot?): "
        f"{column_name} has {', '.join(new_missing)}.",
        # 5 frames up from here: _warn_unknown_decode_codes ->
        # _decode_parent_channel -> _add_derived_columns -> build_table ->
        # get_tossd (or export()) -> the caller. Both wrap `build_table` at
        # the same depth, so this stacklevel is correct either way.
        stacklevel=6,
    )


def _resolve_columns(
    columns: Literal["all", "minimal", "analysis"] | list[str],
) -> list[str]:
    """Resolve `columns=` to the final column list, forcing the always-present four."""
    if isinstance(columns, str):
        selected = list(_schema.preset_columns(columns))
    else:
        valid_names = _valid_column_names()
        selected = []
        for name in columns:
            if name not in valid_names:
                raise ValueError(_unknown_column_message(name, valid_names))
            if name not in selected:
                selected.append(name)
    for forced in FORCED_COLUMNS:
        if forced not in selected:
            selected.append(forced)
    return selected


def _with_passthrough_extras(
    column_names: list[str], actual_names: list[str]
) -> list[str]:
    """Extend an already-resolved `columns="all"` list with any passthrough extras.

    `_schema.apply_schema` deliberately passes an unknown-extra column through
    raw (with a one-time warning) rather than dropping it, but a plain
    `combined.select(column_names)` built from `_schema.preset_columns("all")`
    silently drops it anyway, contradicting that warning's own text ("only
    visible with `columns='all'`"). Only called for `columns="all"`: presets
    and explicit `columns=` lists never gain extras.

    Args:
        column_names: The already-resolved `"all"`-preset column list (schema
            columns, in schema.csv order, plus the forced derived columns).
        actual_names: `combined.column_names` -- the combined table's actual
            columns, schema columns first, any extras next (in file order,
            per `apply_schema`), then the derived columns.

    Returns:
        `column_names` unchanged if there are no extras; otherwise schema
        columns first, extras appended in file order, then the derived
        columns (`is_aggregate`/`unit`) last.
    """
    extras = [name for name in actual_names if name not in column_names]
    if not extras:
        return column_names
    schema_names = set(_schema.preset_columns("all"))
    schema_ordered = [name for name in column_names if name in schema_names]
    derived_ordered = [name for name in column_names if name not in schema_names]
    return schema_ordered + extras + derived_ordered


def _valid_column_names() -> set[str]:
    """Every column name `get_tossd` can produce: schema columns + derived ones."""
    return {field.snake_name for field in _schema.load_schema()} | set(FORCED_COLUMNS)


def _unknown_column_message(name: str, valid_names: set[str]) -> str:
    """Build the ValueError message for an unrecognised `columns=` entry."""
    suggestions = difflib.get_close_matches(
        name, sorted(valid_names), n=_matching.MAX_SUGGESTIONS
    )
    suggestion_note = _matching.closest_matches_note(suggestions)
    return f"Unknown column {name!r} in columns=.{suggestion_note}"


def _convert_units(table: pa.Table, *, units: str) -> pa.Table:
    """Scale every `is_usd_thousand_amount` column: divide by 1000 for "usd_million", multiply for "usd".

    The published scale is already USD thousands, so "usd" (plain dollars)
    multiplies rather than divides.
    """
    if units == "usd_thousand":
        return table
    amount_columns = {
        field.snake_name
        for field in _schema.load_schema()
        if field.is_usd_thousand_amount
    }
    for name in table.column_names:
        if name not in amount_columns:
            continue
        column = table.column(name)
        converted = (
            pc.divide(column, 1000)  # ty: ignore[unresolved-attribute]
            if units == "usd_million"
            else pc.multiply(column, 1000)  # ty: ignore[unresolved-attribute]
        )
        table = table.set_column(table.column_names.index(name), name, converted)
    return table


def _reset_for_tests() -> None:
    """Clear this module's warn-once state.

    Test-only. Wired into `tests/conftest.py`'s shared autouse fixture
    (alongside _discovery's, config's, and _pillars's own resets), rather
    than a local per-file fixture.
    """
    _warned_unknown_codes.clear()
