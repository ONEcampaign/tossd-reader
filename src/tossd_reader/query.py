"""The typed, filtered `get_tossd` query layer (D6/D7).

Per requested year: `fetch._resolve_year` → pyarrow read → `schema.apply_schema`
→ arrow-level row filters (provider/recipient/pillar). Then, once across every
year: `pa.concat_tables(...).unify_dictionaries()` (D6 — a categorical column
stays dictionary-encoded across a multi-year query), derived columns
(`is_aggregate`, `unit`, the `parent_channel_code` decode), preset/column
projection, units conversion, and exactly one `.to_pandas()` call at the very
end.

Discovery is swept once per `get_tossd` call (not once per requested year),
the same `_sweep_or_none` pattern `fetch.get_tossd_raw` already uses. A
year outside the packaged known-years set is honoured or rejected by
`fetch._resolve_year` itself (slice 1.1's rule d) — this module never
duplicates that logic.
"""

from __future__ import annotations

import difflib
import warnings
from collections.abc import Iterable
from typing import Literal

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from readerkit.refresh import effective_refresh

from tossd_reader import codelists, fetch, schema
from tossd_reader.exceptions import InvalidPillarError, UnknownCodeError

_VALID_UNITS = ("usd_thousand", "usd_million")
_FORCED_COLUMNS = ("tossd_pillar", "tossd_subpillar", "is_aggregate", "unit")
_MAX_SUGGESTIONS = 5

_SUBPILLAR_MIN_YEAR = 2023
_SUBPILLAR_COVERAGE_WARN_YEAR = 2023
_PILLAR_2022_TRACE_ROWS = 24
"""a4 audit: 2022 carries only 24 `Tossdpillar2='21'` trace rows (out of
~128,900 pillar-2 rows); the substantive rollout starts in 2023."""

_PILLAR_TOKENS: dict[str, tuple[str, str | None]] = {
    "1": ("1", None),
    "i": ("1", None),
    "2": ("2", None),
    "ii": ("2", None),
    "21": ("2", "21"),
    "ii.a": ("2", "21"),
    "22": ("2", "22"),
    "ii.b": ("2", "22"),
}

_DECODE_CHANNEL_DIMENSION = "channel"
_DECODE_CODE_COLUMN = "parent_channel_code"
_DECODE_NAME_COLUMN = "parent_channel_name"


class _QueryState:
    """Mutable singleton state backing this module's warn-once accessors."""

    def __init__(self) -> None:
        self.warned_subpillar_narrow = False
        self.warned_subpillar_2023_coverage = False
        self.warned_unknown_codes: dict[str, set[str]] = {}


_state = _QueryState()


def get_tossd(
    *,
    years: int | Iterable[int] | None = None,
    providers: int | str | Iterable[int | str] | None = None,
    recipients: int | str | Iterable[int | str] | None = None,
    pillars: int | str | None = None,
    columns: Literal["all", "minimal", "analysis"] | list[str] = "all",
    units: Literal["usd_thousand", "usd_million"] = "usd_thousand",
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
        columns: `"all"` (default, every packaged column), `"minimal"`,
            `"analysis"` (see `schema.preset_columns`), or an explicit
            `list[str]` of snake_case column names. `tossd_pillar`,
            `tossd_subpillar`, `is_aggregate`, and `unit` are always present
            in the result regardless of this selection.
        units: `"usd_thousand"` (default, as published) or `"usd_million"`,
            which divides every `schema.csv` `is_usd_thousand_amount`
            column by 1000.
        refresh: Re-run discovery's HEAD sweep and force a readerkit
            conditional GET for every requested year. An enclosing
            `readerkit.refresh_scope()` has the same effect.

    Returns:
        A `pandas.DataFrame`, one row per activity matching every filter,
        across every requested year. An empty result (after filtering)
        still comes back correctly typed, with one warning.

    Raises:
        ValueError: `units` is not `"usd_thousand"`/`"usd_million"`;
            `columns` names an unknown column (or an unrecognised preset);
            `years` resolves to an empty set of years; or a requested year
            is not currently published and nothing is cached for it.
        UnknownCodeError: A `providers`/`recipients` token (name, code, or
            digit-string) does not match the packaged codelist.
        InvalidPillarError: A sub-pillar filter is requested for an
            explicit year before 2023.
        TossdNetworkError: The publisher is unreachable and nothing usable
            is cached for a requested year.
        SchemaDriftError: A requested year's published file no longer
            matches the packaged schema.
    """
    if units not in _VALID_UNITS:
        raise ValueError(f"Unknown units {units!r}; expected one of {_VALID_UNITS}.")

    years_was_none = years is None
    resolved_years = fetch._normalise_years(years)

    pillar_main, pillar_sub = (
        (None, None) if pillars is None else _normalise_pillar_token(pillars)
    )
    if pillar_sub is not None:
        resolved_years = _resolve_subpillar_years(
            resolved_years, years_was_none=years_was_none
        )

    provider_codes = _resolve_dimension_codes(
        providers, dimension="provider", label="providers"
    )
    recipient_codes = _resolve_dimension_codes(
        recipients, dimension="recipient", label="recipients"
    )
    column_names = _resolve_columns(columns)

    # Resolved once for the whole call, not once per requested year: see
    # fetch.get_tossd_raw's own docstring for why (M2).
    effective = effective_refresh("tossd_reader:get_tossd", explicit=refresh)
    vintages = fetch._sweep_or_none(effective)

    tables = []
    for year in resolved_years:
        path = fetch._resolve_year(year, vintages=vintages, refresh=effective)
        raw = pq.read_table(path)
        typed = schema.apply_schema(raw)
        filtered = _apply_row_filters(
            typed,
            provider_codes=provider_codes,
            recipient_codes=recipient_codes,
            pillar_main=pillar_main,
            pillar_sub=pillar_sub,
        )
        tables.append(filtered)

    combined = pa.concat_tables(tables).unify_dictionaries()
    combined = _add_derived_columns(combined, units=units)
    combined = combined.select(column_names)
    combined = _convert_units(combined, units=units)

    if combined.num_rows == 0:
        warnings.warn(
            "get_tossd's filters matched no rows; returning an empty (but "
            "correctly typed) frame.",
            stacklevel=2,
        )

    return combined.to_pandas()


# --- years / pillars ---------------------------------------------------------


def _normalise_pillar_token(pillar: int | str) -> tuple[str, str | None]:
    """Resolve one `pillars=` token to `(tossd_pillar, tossd_subpillar | None)`."""
    if isinstance(pillar, bool):
        key = None
    elif isinstance(pillar, int):
        key = str(pillar)
    elif isinstance(pillar, str):
        key = pillar.strip().casefold()
    else:
        key = None
    resolved = _PILLAR_TOKENS.get(key) if key is not None else None
    if resolved is None:
        raise ValueError(
            f"Unknown pillars token {pillar!r}; expected one of 1, 2, 21, 22, "
            "'I', 'II', 'II.A', 'II.B' (case-insensitive)."
        )
    return resolved


def _resolve_subpillar_years(
    resolved_years: tuple[int, ...], *, years_was_none: bool
) -> tuple[int, ...]:
    """Apply D7's sub-pillar year policy, returning the (possibly narrowed) years."""
    bad_years = [year for year in resolved_years if year < _SUBPILLAR_MIN_YEAR]
    if bad_years:
        if not years_was_none:
            raise InvalidPillarError(_invalid_subpillar_message(bad_years))
        narrowed = tuple(year for year in resolved_years if year >= _SUBPILLAR_MIN_YEAR)
        _warn_subpillar_narrowed(resolved_years, narrowed)
        resolved_years = narrowed
    if _SUBPILLAR_COVERAGE_WARN_YEAR in resolved_years:
        _warn_subpillar_2023_coverage()
    return resolved_years


def _invalid_subpillar_message(bad_years: list[int]) -> str:
    """Build InvalidPillarError's message, special-cased for 2022's trace rows."""
    detail = ""
    if 2022 in bad_years:
        detail = (
            f" 2022 specifically carries only {_PILLAR_2022_TRACE_ROWS} "
            "sub-pillar-tagged trace rows (out of roughly 128,900 pillar-2 "
            "rows that year); reach them with pillars=2 (every pillar-2 row, "
            "tagged or not) or an unfiltered query, not a sub-pillar filter."
        )
    return (
        "Sub-pillar filters (pillars=21/'II.A' or 22/'II.B') are not "
        f"meaningful before 2023; requested year(s) {bad_years} predate "
        f"that.{detail}"
    )


def _warn_subpillar_narrowed(
    original: tuple[int, ...], narrowed: tuple[int, ...]
) -> None:
    """Warn once that the default years were narrowed for a sub-pillar filter."""
    if _state.warned_subpillar_narrow:
        return
    _state.warned_subpillar_narrow = True
    warnings.warn(
        "Sub-pillar filters are only meaningful from 2023 onward; narrowing "
        f"the default years {list(original)} to {list(narrowed)}. Pass "
        "years= explicitly to request years before 2023 (raises "
        "InvalidPillarError for a sub-pillar filter).",
        # 4 frames up from here: _warn_subpillar_narrowed ->
        # _resolve_subpillar_years -> get_tossd -> the caller. Verified in
        # test_query.py against the real call chain, not just counted by eye.
        stacklevel=4,
    )


def _warn_subpillar_2023_coverage() -> None:
    """Warn once that 2023's sub-pillar tagging is materially incomplete."""
    if _state.warned_subpillar_2023_coverage:
        return
    _state.warned_subpillar_2023_coverage = True
    warnings.warn(
        "2023 sub-pillar tagging is incomplete: roughly 49% of 2023 "
        "pillar-2 rows carry no sub-pillar tag (the rollout wasn't yet "
        "complete that year). Treat 2023 sub-pillar splits as indicative, "
        "not reliable; 2024 onward is complete.",
        # Same 4-frame chain as _warn_subpillar_narrowed.
        stacklevel=4,
    )


# --- providers / recipients ---------------------------------------------------


def _resolve_dimension_codes(
    values: int | str | Iterable[int | str] | None,
    *,
    dimension: str,
    label: str,
) -> tuple[int, ...] | None:
    """Resolve `providers=`/`recipients=` to a tuple of codes, or `None` (no filter)."""
    if values is None:
        return None
    tokens = [values] if isinstance(values, int | str) else list(values)
    return tuple(
        _resolve_one_code(token, dimension=dimension, label=label) for token in tokens
    )


def _resolve_one_code(token: int | str, *, dimension: str, label: str) -> int:
    """Resolve one provider/recipient token (code, name, or digit-string) to a code."""
    if isinstance(token, bool) or not isinstance(token, int | str):
        raise TypeError(
            f"{label} filter values must be int or str, got {token!r} "
            f"({type(token).__name__})."
        )
    if isinstance(token, int):
        return token

    stripped = token.strip()
    if stripped.isdigit():
        code = _match_code(dimension, stripped)
        if code is not None:
            return code
    code = _match_name(dimension, stripped)
    if code is not None:
        return code
    raise _unknown_code_error(token, dimension=dimension, label=label)


def _match_code(dimension: str, token: str) -> int | None:
    """Return `token`'s code if it matches a packaged codelist code exactly."""
    frame = codelists.load_codelist(dimension)
    matches = frame.loc[frame["code"] == token, "code"]
    return None if matches.empty else int(matches.iloc[0])


def _match_name(dimension: str, token: str) -> int | None:
    """Return `token`'s code if it case-foldedly exact-matches a codelist name."""
    frame = codelists.load_codelist(dimension)
    folded = token.casefold()
    matches = frame.loc[frame["name"].str.casefold() == folded, "code"]
    return None if matches.empty else int(matches.iloc[0])


def _unknown_code_error(token: str, *, dimension: str, label: str) -> UnknownCodeError:
    """Build UnknownCodeError, carrying `token` and up to 5 sorted suggestions."""
    suggestions = _suggest(dimension, token)
    suggestion_note = (
        f" Closest matches: {', '.join(suggestions)}." if suggestions else ""
    )
    return UnknownCodeError(
        f"{token!r} did not match any {label} code or name in the packaged "
        f"codelist.{suggestion_note}"
    )


def _suggest(dimension: str, token: str) -> list[str]:
    """Best-effort ranked name suggestions for an unresolved code/name token."""
    try:
        return _suggest_with_resolvekit(dimension, token)
    except Exception:  # suggestions are best-effort, never fatal
        return _suggest_with_difflib(dimension, token)


def _suggest_with_resolvekit(dimension: str, token: str) -> list[str]:
    """Rank suggestions via resolvekit, imported lazily (only on this error path)."""
    import resolvekit  # noqa: PLC0415 - deliberately lazy: see module docstring

    frame = codelists.load_codelist(dimension)
    resolver = resolvekit.Resolver.from_records(
        frame,
        domain="custom",
        namespace=f"tossd_{dimension}",
        name="name",
        codes=["code"],
        cache=False,
        warm=False,
    )
    try:
        candidates = resolver.diagnostics.search(token, top_k=_MAX_SUGGESTIONS)
        names = set()
        for candidate in candidates:
            record = resolver.entity(candidate.entity_id)
            if record is not None:
                names.add(record.canonical_name)
        return sorted(names)[:_MAX_SUGGESTIONS]
    finally:
        resolver.close()


def _suggest_with_difflib(dimension: str, token: str) -> list[str]:
    """Fallback suggestions via stdlib difflib, if resolvekit's shape resists us."""
    frame = codelists.load_codelist(dimension)
    return sorted(
        difflib.get_close_matches(token, frame["name"].tolist(), n=_MAX_SUGGESTIONS)
    )


# --- row filters (arrow-level, applied per year before concat) ----------------


def _apply_row_filters(
    table: pa.Table,
    *,
    provider_codes: tuple[int, ...] | None,
    recipient_codes: tuple[int, ...] | None,
    pillar_main: str | None,
    pillar_sub: str | None,
) -> pa.Table:
    """Apply every requested filter to one year's already-typed table."""
    if provider_codes is not None:
        table = _filter_codes(table, "provider_code", provider_codes)
    if recipient_codes is not None:
        table = _filter_codes(table, "recipient_code", recipient_codes)
    if pillar_main is not None:
        table = _filter_pillar(table, pillar_main, pillar_sub)
    return table


def _filter_codes(
    table: pa.Table, column_name: str, codes: tuple[int, ...]
) -> pa.Table:
    """Keep only rows whose `column_name` value is one of `codes`."""
    column = table.column(column_name)
    values = pa.array(codes, type=column.type)
    return table.filter(pc.is_in(column, value_set=values))  # ty: ignore[unresolved-attribute]


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


# --- derived columns, decode, projection, units -------------------------------


def _add_derived_columns(table: pa.Table, *, units: str) -> pa.Table:
    """Append `is_aggregate`/`unit`, then decode `parent_channel_name`."""
    is_aggregate = pc.equal(table.column("provider_code"), 0)  # ty: ignore[unresolved-attribute]
    table = table.append_column("is_aggregate", is_aggregate)
    unit_values = pa.array([units] * table.num_rows, type=pa.string())
    table = table.append_column("unit", pc.dictionary_encode(unit_values))  # ty: ignore[unresolved-attribute]
    return _decode_parent_channel(table)


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
    already_warned = _state.warned_unknown_codes.setdefault(column_name, set())
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
        # 3 frames up from here: _warn_unknown_decode_codes ->
        # _decode_parent_channel -> _add_derived_columns -> get_tossd -> the
        # caller. Verified in test_query.py against the real call chain.
        stacklevel=5,
    )


def _resolve_columns(
    columns: Literal["all", "minimal", "analysis"] | list[str],
) -> list[str]:
    """Resolve `columns=` to the final column list, forcing the always-present four."""
    if isinstance(columns, str):
        selected = list(schema.preset_columns(columns))
    else:
        valid_names = _valid_column_names()
        selected = []
        for name in columns:
            if name not in valid_names:
                raise ValueError(_unknown_column_message(name, valid_names))
            if name not in selected:
                selected.append(name)
    for forced in _FORCED_COLUMNS:
        if forced not in selected:
            selected.append(forced)
    return selected


def _valid_column_names() -> set[str]:
    """Every column name `get_tossd` can produce: schema columns + derived ones."""
    return {field.snake_name for field in schema.load_schema()} | set(_FORCED_COLUMNS)


def _unknown_column_message(name: str, valid_names: set[str]) -> str:
    """Build the ValueError message for an unrecognised `columns=` entry."""
    suggestions = difflib.get_close_matches(
        name, sorted(valid_names), n=_MAX_SUGGESTIONS
    )
    suggestion_note = (
        f" Closest matches: {', '.join(suggestions)}." if suggestions else ""
    )
    return f"Unknown column {name!r} in columns=.{suggestion_note}"


def _convert_units(table: pa.Table, *, units: str) -> pa.Table:
    """Divide every `is_usd_thousand_amount` column by 1000 when units="usd_million"."""
    if units == "usd_thousand":
        return table
    amount_columns = {
        field.snake_name
        for field in schema.load_schema()
        if field.is_usd_thousand_amount
    }
    for name in table.column_names:
        if name not in amount_columns:
            continue
        converted = pc.divide(table.column(name), 1000)  # ty: ignore[unresolved-attribute]
        table = table.set_column(table.column_names.index(name), name, converted)
    return table


def _reset_for_tests() -> None:
    """Clear this module's warn-once state.

    Test-only. Wired into `tests/conftest.py`'s shared autouse fixture
    (alongside discovery's and config's own resets), rather than a local
    per-file fixture, since the plan reserved this reset hook for this slice.
    """
    _state.warned_subpillar_narrow = False
    _state.warned_subpillar_2023_coverage = False
    _state.warned_unknown_codes.clear()
