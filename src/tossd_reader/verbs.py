"""Aggregation verbs for `get_tossd()` output: rank, compare, and total.

`rank_entities`, `compare_years`, `sdg_totals`, `keyword_totals`, and
`subpillar_breakdown` each operate on a `pandas.DataFrame` already shaped
like `get_tossd()`'s output (snake_case columns) and raise a `ValueError`
naming any column they need but don't find, rather than a bare `KeyError`.
Each returns a new frame, leaving the caller's frame untouched, and copies
`df.attrs` onto its result.

Every verb here defaults `include_aggregates=False`: the `provider_code ==
0` pseudo-aggregate rows `get_tossd()` keeps by default are dropped before
aggregating, unless the caller opts back in with `include_aggregates=True`.
Excluding them needs the `is_aggregate` column `get_tossd()` output always
carries; a frame missing it raises, naming the column.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable
from typing import Literal

import pandas as pd

from tossd_reader import _matching, analysis

_COHORT_MODES: tuple[str, ...] = ("consistent", "all")
_SDG_LEVEL_GROUP_COLUMNS: dict[str, str] = {"goal": "sdg_goal", "code": "sdg_code"}
_SUBPILLAR_BUCKETS: tuple[str, str, str] = ("II.A", "II.B", "Untagged")


# --- shared helpers ----------------------------------------------------------


def _require_numeric_value(df: pd.DataFrame, value: str, *, func_name: str) -> None:
    """Raise `ValueError` naming `value` if `df[value]` isn't numeric-dtyped.

    Only called after the column's presence is already confirmed (e.g. via
    `analysis._require_columns`), so `df[value]` is safe to access here.
    """
    if not pd.api.types.is_numeric_dtype(df[value]):
        raise ValueError(
            f"{func_name}() needs value={value!r} to be numeric; df[{value!r}] "
            f"is {df[value].dtype} dtype."
        )


def _exclude_aggregates(
    df: pd.DataFrame, *, include_aggregates: bool, func_name: str
) -> pd.DataFrame:
    """Drop `is_aggregate` rows, unless `include_aggregates=True`."""
    if include_aggregates:
        return df
    if "is_aggregate" not in df.columns:
        raise ValueError(
            f"{func_name}() needs column 'is_aggregate' to exclude aggregate rows "
            "(include_aggregates=False, the default) -- it is always present in "
            "get_tossd() output. Pass include_aggregates=True to skip this filter."
        )
    return df.loc[~df["is_aggregate"]]


def _share_pct(values: pd.Series) -> pd.Series:
    """Each value's share of `values`' own sum, 0-100 scale, unrounded."""
    return values / values.sum() * 100


def _competition_rank(values: pd.Series) -> pd.Series:
    """Competition ranking (tied entries share the lower rank number), descending, 1-based."""
    return values.rank(method="min", ascending=False).astype("int64")


# --- rank_entities -------------------------------------------------------------


def rank_entities(
    df: pd.DataFrame,
    *,
    dimension: str = "provider",
    value: str = "usd_disbursement",
    top: int | None = None,
    include_aggregates: bool = False,
) -> pd.DataFrame:
    """Rank entities along one dimension by summed `value`.

    Works for any dimension whose `{dimension}_code`/`{dimension}_name`
    columns are present in `df` -- `"provider"` (the default),
    `"recipient"`, `"sector"`, `"purpose"`, `"channel"`, or any other
    packaged dimension pair. Ranking providers across both pillars at once
    mixes Pillar I bilateral/multilateral outflows with Pillar II core
    contributions to multilateral institutions -- a double count, if the
    two are meant to be read as one figure.

    Args:
        df: A `get_tossd()`-shaped frame carrying `{dimension}_code`,
            `{dimension}_name`, and `value`.
        dimension: The dimension to group by -- any prefix with a matching
            `{dimension}_code`/`{dimension}_name` column pair in `df`.
        value: The amount column to sum and rank by.
        top: Keep only the first `top` rows after ranking and sorting.
            `None` (the default) keeps every ranked row.
        include_aggregates: `False` (the default) drops `is_aggregate` rows
            (the `provider_code == 0` pseudo-aggregates) before ranking.

    Returns:
        One row per distinct `({dimension}_code, {dimension}_name)` pair
        (an `observed=True` groupby -- an unused category never appears),
        sorted by summed `value` descending: `{dimension}_code`,
        `{dimension}_name`, `value`, `n_activities` (only when `df` carries
        `tossd_id` -- distinct `tossd_id` per group, excluding the `"0000"`
        placeholder used for bundled lines with no activity identifier, so
        those lines are never counted as activities; omitted entirely,
        rather than raising, when `tossd_id` isn't present), `share_pct`
        (of the summed total across every included row, 0-100 scale,
        unrounded), and `rank` (competition ranking -- tied entries share
        the lower rank number -- 1-based, descending). Truncation to `top`
        happens after ranking, so the numbering on the entities that made
        the cut always matches what a caller would see without `top` set.
        The `"0000"` placeholder also lands on a small share of real
        providers' own rows in 2023-24 (bundled lines belonging to a real
        provider, not just pseudo-aggregates), so `n_activities` can
        slightly undercount those providers even after aggregate exclusion.

    Raises:
        ValueError: `df` is missing `{dimension}_code`, `{dimension}_name`,
            or `value`; `value` is not numeric; or (when
            `include_aggregates=False`) `df` has no `is_aggregate` column.
    """
    code_column = f"{dimension}_code"
    name_column = f"{dimension}_name"
    analysis._require_columns(
        df, code_column, name_column, value, func_name="rank_entities"
    )
    _require_numeric_value(df, value, func_name="rank_entities")
    working = _exclude_aggregates(
        df, include_aggregates=include_aggregates, func_name="rank_entities"
    )

    has_activities = "tossd_id" in working.columns
    if has_activities:
        working = working.copy()
        working["_activity_id"] = working["tossd_id"].mask(
            working["tossd_id"] == "0000"
        )
        aggregated = working.groupby([code_column, name_column], observed=True).agg(
            **{value: (value, "sum"), "n_activities": ("_activity_id", "nunique")}
        )
    else:
        aggregated = working.groupby([code_column, name_column], observed=True)[
            [value]
        ].sum()

    result = aggregated.reset_index()
    result["share_pct"] = _share_pct(result[value])
    result["rank"] = _competition_rank(result[value])
    result = result.sort_values(value, ascending=False, kind="stable")
    if top is not None:
        result = result.head(top)
    result = result.reset_index(drop=True)

    column_order = [code_column, name_column, value]
    if has_activities:
        column_order.append("n_activities")
    column_order += ["share_pct", "rank"]
    result = result[column_order]

    result.attrs = dict(df.attrs)
    return result


# --- compare_years ---------------------------------------------------------------


def _provider_pairs(frame: pd.DataFrame) -> pd.Series:
    """Build a hashable `(provider_code, provider_name)` pair per row of `frame`."""
    return pd.Series(
        list(zip(frame["provider_code"], frame["provider_name"], strict=True)),
        index=frame.index,
        dtype="object",
    )


def _consistent_provider_cohort(frame: pd.DataFrame) -> set[tuple[object, object]]:
    """Intersect the `(provider_code, provider_name)` pairs present in every year of `frame`."""
    cohort: set[tuple[object, object]] | None = None
    for _year, group in frame.groupby("year", observed=True):
        pairs = set(zip(group["provider_code"], group["provider_name"], strict=True))
        cohort = pairs if cohort is None else cohort & pairs
    return cohort or set()


def _empty_compare_years(
    df: pd.DataFrame, working: pd.DataFrame, value: str
) -> pd.DataFrame:
    """Build `compare_years`' 0-row result for an already-empty (post-exclusion) `working`."""
    result = working.groupby("year", observed=True)[value].sum().reset_index()
    result["n_providers"] = pd.Series([], dtype="int64")
    result["pct_change"] = pd.Series([], dtype="float64")
    result.attrs = dict(df.attrs)
    result.attrs["structural_breaks"] = analysis.get_structural_breaks(years=[])
    return result[["year", value, "n_providers", "pct_change"]]


def compare_years(
    df: pd.DataFrame,
    *,
    value: str = "usd_disbursement_deflated",
    cohort: Literal["consistent", "all"] = "consistent",
    include_aggregates: bool = False,
) -> pd.DataFrame:
    """Compare summed `value` year over year.

    Recipients are not held constant across years -- only the provider
    cohort is, and only when `cohort="consistent"`. A year-over-year rise
    or fall can still be a shift in which recipients each provider funded,
    not a change in how much any single provider gave.

    Args:
        df: A `get_tossd()`-shaped frame carrying `year`, `provider_code`,
            `provider_name`, and `value`.
        value: The amount column to sum per year.
        cohort: `"consistent"` (the default) restricts every year to the
            `(provider_code, provider_name)` pairs present in every year
            `df` covers, so a year's total isn't inflated by a provider
            that only reported in some years. `"all"` disables that
            restriction -- every row counts, whichever years its provider
            happens to appear in.
        include_aggregates: `False` (the default) drops `is_aggregate` rows
            before comparing years.

    Returns:
        One row per year present in `df`: `year`, `value`, `n_providers`
        (the cohort's size under `"consistent"`; the year's own distinct
        provider-pair count under `"all"`), and `pct_change` (percent
        change from the previous row's `value`, 0-100 scale, unrounded;
        `NA` for the first -- or only -- year). `result.attrs
        ["structural_breaks"]` carries `get_structural_breaks(years=...)`'s
        rows intersecting the years covered, so a caller can flag a jump
        against a known discontinuity instead of a real trend.

    Raises:
        ValueError: `df` is missing `year`, `provider_code`,
            `provider_name`, or `value`; `value` is not numeric; `cohort`
            is not `"consistent"`/`"all"`; (when `include_aggregates=False`)
            `df` has no `is_aggregate` column; or `cohort="consistent"` and
            no provider pair is present in every year.
    """
    analysis._require_columns(
        df, "year", "provider_code", "provider_name", value, func_name="compare_years"
    )
    _require_numeric_value(df, value, func_name="compare_years")
    if cohort not in _COHORT_MODES:
        raise ValueError(
            f"compare_years() cohort={cohort!r} not recognised; expected "
            f"{' or '.join(map(repr, _COHORT_MODES))}."
        )
    working = _exclude_aggregates(
        df, include_aggregates=include_aggregates, func_name="compare_years"
    )

    if working.empty:
        return _empty_compare_years(df, working, value)

    years_present = sorted(int(year) for year in working["year"].unique())

    if cohort == "consistent":
        cohort_pairs = _consistent_provider_cohort(working)
        if not cohort_pairs:
            raise ValueError(
                "compare_years() found no (provider_code, provider_name) pair "
                f"present in every one of {years_present}; pass cohort='all' to "
                "disable this restriction."
            )
        working = working.loc[_provider_pairs(working).isin(cohort_pairs)]
        totals = (
            working.groupby("year", observed=True)[value].sum().reindex(years_present)
        )
        result = totals.reset_index()
        result["n_providers"] = len(cohort_pairs)
    else:
        working = working.assign(_pair=_provider_pairs(working))
        totals = (
            working.groupby("year", observed=True)[value].sum().reindex(years_present)
        )
        counts = (
            working.groupby("year", observed=True)["_pair"]
            .nunique()
            .reindex(years_present)
        )
        result = totals.reset_index()
        result["n_providers"] = counts.to_numpy()

    result["pct_change"] = result[value].pct_change() * 100
    result.attrs = dict(df.attrs)
    result.attrs["structural_breaks"] = analysis.get_structural_breaks(
        years=years_present
    )
    return result[["year", value, "n_providers", "pct_change"]]


# --- sdg_totals --------------------------------------------------------------


def _require_sdg_codes_raw(df: pd.DataFrame) -> None:
    """Raise `ValueError` naming `sdg_codes_raw`, branded sdg_totals() rather
    than surfacing `explode_sdg`'s own message."""
    analysis._require_columns(df, "sdg_codes_raw", func_name="sdg_totals")


def _reject_already_exploded_sdg(df: pd.DataFrame) -> None:
    """Raise `ValueError`, branded sdg_totals(), if `df` already carries
    `explode_sdg`'s own output columns."""
    already = [name for name in analysis._SDG_DERIVED_COLUMNS if name in df.columns]
    if already:
        raise ValueError(
            f"sdg_totals() found column(s) {', '.join(already)} already present "
            "in df -- df looks already exploded."
        )


def sdg_totals(
    df: pd.DataFrame,
    *,
    value: str = "usd_disbursement",
    level: Literal["goal", "code"] = "goal",
    top: int | None = None,
    include_aggregates: bool = False,
) -> pd.DataFrame:
    """Sum `value` by SDG tag, weighted for rows that carry more than one tag.

    Internally explodes `df` with `analysis.explode_sdg` first, then sums
    `value * sdg_weight` per tag -- the weighted total this returns equals
    the SDG-tagged subset of `df`'s `value` total, never `df`'s grand
    total, since a row with no SDG tag at all contributes nothing to any
    group.

    Args:
        df: A `get_tossd()`-shaped frame carrying `sdg_codes_raw` and
            `value`.
        value: The amount column to sum.
        level: `"goal"` (the default) groups by SDG goal (`sdg_goal`);
            `"code"` groups by the exact token published in
            `sdg_codes_raw` (`sdg_code`), keeping goals and targets apart.
            The publisher formats some goal-level tags as a trailing-`.0`
            token (e.g. `"5.0"`, no real SDG target is numbered `.0`); at
            `level="code"` each such token gets its own row, while
            `level="goal"` folds it into its goal like any other goal-level
            tag.
        top: Keep only the first `top` rows after ranking and sorting.
            `None` (the default) keeps every row.
        include_aggregates: `False` (the default) drops `is_aggregate` rows
            before exploding.

    Returns:
        One row per distinct goal or code (matching `level`): `sdg_goal`
        or `sdg_code`, `value` (the weighted sum), `share_pct` (of the
        SDG-tagged total across every included row, 0-100 scale,
        unrounded), and `rank` (competition ranking, descending,
        1-based). Truncation to `top` happens after ranking.

    Raises:
        ValueError: `value` is missing or not numeric; `level` is not
            `"goal"`/`"code"`; `df` is missing `sdg_codes_raw` or already
            carries `explode_sdg`'s own output columns (both raised by
            sdg_totals() itself, naming sdg_totals() -- not a delegated
            `explode_sdg` message); or (when `include_aggregates=False`)
            `df` has no `is_aggregate` column.
    """
    analysis._require_columns(df, value, func_name="sdg_totals")
    _require_numeric_value(df, value, func_name="sdg_totals")
    if level not in _SDG_LEVEL_GROUP_COLUMNS:
        raise ValueError(
            f"sdg_totals() level={level!r} not recognised; expected "
            f"{' or '.join(map(repr, _SDG_LEVEL_GROUP_COLUMNS))}."
        )
    group_column = _SDG_LEVEL_GROUP_COLUMNS[level]
    _require_sdg_codes_raw(df)
    _reject_already_exploded_sdg(df)

    working = _exclude_aggregates(
        df, include_aggregates=include_aggregates, func_name="sdg_totals"
    )
    exploded = analysis.explode_sdg(working)
    exploded = exploded.assign(_weighted=exploded[value] * exploded["sdg_weight"])

    grouped = exploded.groupby(group_column)["_weighted"].sum()
    result = grouped.reset_index().rename(columns={"_weighted": value})
    result["share_pct"] = _share_pct(result[value])
    result["rank"] = _competition_rank(result[value])
    result = result.sort_values(value, ascending=False, kind="stable")
    if top is not None:
        result = result.head(top)
    result = result.reset_index(drop=True)

    result.attrs = dict(df.attrs)
    return result


# --- keyword_totals ------------------------------------------------------------


def _require_keywords_raw(df: pd.DataFrame) -> None:
    """Raise `ValueError` naming `keywords_raw` if missing, flagging stale `kw_*` columns."""
    if "keywords_raw" in df.columns:
        return
    kw_columns = [name for name in df.columns if name.startswith("kw_")]
    if kw_columns:
        raise ValueError(
            "keyword_totals() needs 'keywords_raw' -- it recomputes marker masks "
            f"internally from that column, ignoring the already-present kw_* "
            f"column(s) {', '.join(kw_columns)}; keep keywords_raw in your "
            "columns= selection."
        )
    analysis._require_columns(df, "keywords_raw", func_name="keyword_totals")


def _canonical_marker_name(token: str) -> str:
    """Casefold `token` and strip an optional `kw_` prefix, for marker-name matching."""
    if token.casefold().startswith("kw_"):
        token = token[3:]
    return token.casefold()


def _resolve_markers(
    markers: str | Iterable[str], canonical_names: list[str]
) -> list[str]:
    """Resolve `markers` to the packaged canonical marker names, de-duplicated, order kept."""
    tokens = [markers] if isinstance(markers, str) else list(markers)
    canonical_set = set(canonical_names)
    resolved: list[str] = []
    for token in tokens:
        name = _canonical_marker_name(token)
        if name not in canonical_set:
            suggestions = difflib.get_close_matches(
                name, canonical_names, n=_matching.MAX_SUGGESTIONS
            )
            raise ValueError(
                f"keyword_totals() marker {token!r} not recognised; expected one "
                f"of {', '.join(sorted(canonical_names))}."
                f"{_matching.closest_matches_note(suggestions)}"
            )
        if name not in resolved:
            resolved.append(name)
    return resolved


def keyword_totals(
    df: pd.DataFrame,
    *,
    markers: str | Iterable[str] | None = None,
    value: str = "usd_disbursement",
    include_aggregates: bool = False,
) -> pd.DataFrame:
    """Sum `value` per keyword marker, plus a union row combining them.

    Marker masks are recomputed internally from `keywords_raw` via
    `analysis.extract_keywords` -- any `kw_*` columns already in `df` are
    ignored, so a caller who filtered or otherwise altered `df` since
    running `extract_keywords` never gets stale marker flags here.

    Args:
        df: A `get_tossd()`-shaped frame carrying `keywords_raw` and
            `value`.
        markers: One marker name, an iterable of them, or `None` (the
            default) for all 12 packaged markers. Each name is matched
            with or without its `kw_` prefix (`"gender"` and `"kw_gender"`
            both match); an unrecognised name raises, naming the closest
            matches.
        value: The amount column to sum.
        include_aggregates: `False` (the default) drops `is_aggregate` rows
            before summing.

    Returns:
        One row per requested marker, in the order given (packaged order
        when `markers=None`), plus a final `"Combined"` row: `marker`,
        `value`, `n_rows` (a row count of the marker's mask, not a
        distinct-`tossd_id` count -- the publisher's pre-split rows can
        spread one activity across several rows, and those rows can
        genuinely carry different keyword tags from each other, so a
        multi-row activity counts once per matching row rather than once
        overall, and no distinct-ID count is offered here). `"Combined"`'s
        mask is the union of every requested marker's mask, so the
        individual marker rows sum to at least `"Combined"`'s total, never
        less -- a row tagged with more than one requested marker is
        counted once per marker row but only once in `"Combined"`, which
        is the double count the union row exists to avoid.

    Raises:
        ValueError: `df` is missing `keywords_raw` (naming any already
            present `kw_*` columns as the likely cause) or `value`;
            `value` is not numeric; a `markers=` name isn't recognised; or
            (when `include_aggregates=False`) `df` has no `is_aggregate`
            column.
    """
    _require_keywords_raw(df)
    analysis._require_columns(df, value, func_name="keyword_totals")
    _require_numeric_value(df, value, func_name="keyword_totals")

    working = _exclude_aggregates(
        df, include_aggregates=include_aggregates, func_name="keyword_totals"
    )

    vocabulary = analysis._keyword_markers()
    canonical_names = list(vocabulary["column_name"])
    requested = (
        canonical_names
        if markers is None
        else _resolve_markers(markers, canonical_names)
    )

    if working.empty:
        result = pd.DataFrame(
            {
                "marker": pd.Series([], dtype="object"),
                value: pd.Series([], dtype="float64"),
                "n_rows": pd.Series([], dtype="int64"),
            }
        )
        result.attrs = dict(df.attrs)
        return result

    tagged = analysis.extract_keywords(working)
    combined_mask = pd.Series(False, index=tagged.index)
    rows = []
    for name in requested:
        mask = tagged[f"kw_{name}"]
        combined_mask = combined_mask | mask
        rows.append(
            {
                "marker": name,
                value: tagged.loc[mask, value].sum(),
                "n_rows": int(mask.sum()),
            }
        )
    rows.append(
        {
            "marker": "Combined",
            value: tagged.loc[combined_mask, value].sum(),
            "n_rows": int(combined_mask.sum()),
        }
    )

    result = pd.DataFrame(rows)
    result.attrs = dict(df.attrs)
    return result


# --- subpillar_breakdown -------------------------------------------------------


def _subpillar_bucket(subpillar: pd.Series) -> pd.Categorical:
    """Map a `tossd_subpillar` value to its `"II.A"`/`"II.B"`/`"Untagged"` bucket."""
    labels = pd.Series("Untagged", index=subpillar.index, dtype="object")
    labels = labels.mask(subpillar == "21", "II.A")
    labels = labels.mask(subpillar == "22", "II.B")
    return pd.Categorical(labels, categories=_SUBPILLAR_BUCKETS, ordered=False)


def subpillar_breakdown(
    df: pd.DataFrame,
    *,
    value: str = "usd_disbursement",
    include_aggregates: bool = False,
) -> pd.DataFrame:
    """Split Pillar II's `value` by sub-pillar, year over year.

    Takes the `tossd_pillar == 2` subset of `df` internally -- Pillar I
    rows never appear in the result. Every row's `tossd_subpillar` value
    buckets to `"II.A"` (a real `"21"` tag), `"II.B"` (`"22"`), or
    `"Untagged"` (`NA`, or anything else) -- an unordered category.

    Args:
        df: A `get_tossd()`-shaped frame carrying `year`, `tossd_pillar`,
            `tossd_subpillar`, and `value`.
        value: The amount column to sum.
        include_aggregates: `False` (the default) drops `is_aggregate` rows
            before splitting.

    Returns:
        One row per `(year, subpillar)` pair -- every year present gets
        all three bucket rows, even a bucket with nothing in it that year
        (`value` reads `0` then): `year`, `subpillar`, `value`,
        `share_pct` (that row's share of its year's Pillar II total,
        0-100 scale, unrounded), and `coverage_pct` (that year's combined
        `"II.A"` + `"II.B"` share of the same total -- the same number
        repeated on all three of that year's rows, since it describes the
        year, not the bucket).

        Sub-pillar tags only exist from 2023 (a 2022 trace appearance
        aside, per `get_structural_breaks`); a year with `"II.A"`/`"II.B"`
        both reading `0` and a near-zero `coverage_pct` means the year
        predates tagging, not that Pillar II went unfunded. Read `"II.A"`/
        `"II.B"` as real amounts only where `coverage_pct` is non-trivial.

    Raises:
        ValueError: `df` is missing `year`, `tossd_pillar`,
            `tossd_subpillar`, or `value`; `value` is not numeric; or
            (when `include_aggregates=False`) `df` has no `is_aggregate`
            column.
    """
    analysis._require_columns(
        df,
        "year",
        "tossd_pillar",
        "tossd_subpillar",
        value,
        func_name="subpillar_breakdown",
    )
    _require_numeric_value(df, value, func_name="subpillar_breakdown")
    working = _exclude_aggregates(
        df, include_aggregates=include_aggregates, func_name="subpillar_breakdown"
    )
    working = working.loc[working["tossd_pillar"] == 2]

    if working.empty:
        result = pd.DataFrame(
            {
                "year": pd.Series([], dtype=working["year"].dtype),
                "subpillar": pd.Categorical([], categories=_SUBPILLAR_BUCKETS),
                value: pd.Series([], dtype="float64"),
                "share_pct": pd.Series([], dtype="float64"),
                "coverage_pct": pd.Series([], dtype="float64"),
            }
        )
        result.attrs = dict(df.attrs)
        return result

    working = working.copy()
    working["subpillar"] = _subpillar_bucket(working["tossd_subpillar"])

    grouped = working.groupby(["year", "subpillar"], observed=False)[value].sum()
    result = grouped.reset_index()

    year_totals = result.groupby("year")[value].transform("sum")
    result["share_pct"] = result[value] / year_totals * 100

    tagged_totals = (
        result.loc[result["subpillar"].isin(["II.A", "II.B"])]
        .groupby("year")[value]
        .sum()
    )
    result["coverage_pct"] = result["year"].map(tagged_totals) / year_totals * 100

    result.attrs = dict(df.attrs)
    return result[["year", "subpillar", value, "share_pct", "coverage_pct"]]
