"""Post-query analysis toolkit for `get_tossd()` output.

`explode_sdg`, `add_iso3`, `extract_keywords`, and `pillar2_provider_costs`
each operate on a `pandas.DataFrame` already shaped like `get_tossd()`'s
output (snake_case columns) and raise a `ValueError` naming any column they
need but don't find, rather than a bare `KeyError`. Each returns a new
frame, leaving the caller's frame untouched. `get_structural_breaks` takes no
frame at all: it returns the packaged structural-breaks reference table.

`add_iso3` is the one helper here that touches `resolvekit`: `import
resolvekit` happens lazily, inside `_iso3_resolver`'s own body, never at
module scope -- a package-level import stays banned project-wide (see
`_matching.py`'s `_suggest_with_resolvekit`), so a bare `import tossd_reader`,
or calling any of this module's other four helpers, never pulls resolvekit
into `sys.modules`.
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
from typing import TYPE_CHECKING

import pandas as pd

from tossd_reader import _resources, _schema

if TYPE_CHECKING:
    import resolvekit

_SDG_DELIMITER = ";"
_KEYWORD_DELIMITER = "|"

_ISO3_GEO_MODULE = "geo.countries"
"""resolvekit's bundled (offline, no-download) country module. See
`add_iso3` for the codelist link this module provides and its
verification."""

_ISO3_LINKS: dict[str, tuple[str, str]] = {
    "provider_code": ("provider_iso3", "oecd:provider"),
    "recipient_code": ("recipient_iso3", "oecd:recipient"),
}
"""`code column -> (new iso3 column, resolvekit code system)`."""

_PROVIDER_COST_SECTOR_CODES = (910, 930)
"""Verified against the 2026-04 archive's 2024 vintage (`sector_code`/
`sector`): 910 = "Administrative Costs of Donors", 930 = "Domestic
expenditures for refugees/asylum seekers". See `pillar2_provider_costs`
for what this carve-out measures and why sector 720 is excluded."""


def _require_columns(df: pd.DataFrame, *names: str, func_name: str) -> None:
    """Raise `ValueError` naming any of `names` missing from `df`.

    When at least one missing column belongs to the `"analysis"` column
    preset, the message adds a hint naming the fix -- the common case is a
    caller who queried with `columns="minimal"` (or a narrow explicit list)
    and then ran an analysis helper that needs an analysis-preset-only
    column.
    """
    missing = [name for name in names if name not in df.columns]
    if not missing:
        return
    message = f"{func_name}() needs column(s) {', '.join(missing)}, not present in df."
    in_analysis_preset = [
        name for name in missing if name in _schema.preset_columns("analysis")
    ]
    if in_analysis_preset:
        message += (
            f" Re-query with columns='analysis', or add "
            f"{', '.join(in_analysis_preset)} to your columns= list."
        )
    raise ValueError(message)


# --- explode_sdg ---------------------------------------------------------------


_SDG_DERIVED_COLUMNS = ("sdg_code", "sdg_goal", "sdg_is_target", "sdg_weight")
"""Columns `explode_sdg` adds -- re-running it on its own output would
silently duplicate these, so their presence is checked for up front."""


def _split_sdg_tokens(raw: object) -> list[str]:
    """Split one row's `sdg_codes_raw` value into its `;`-delimited tokens."""
    if pd.isna(raw) or raw == "":
        return []
    tokens = (token.strip() for token in str(raw).split(_SDG_DELIMITER))
    return [token for token in tokens if token]


def _parse_sdg_token(token: str) -> tuple[int, bool]:
    """Parse one already-published SDG token into `(goal, is_target)`.

    Bare integers (`"5"`) are goal-level. `goal.target` tokens (`"5.2"`,
    `"6.b"` -- the target suffix can be a digit or a letter) are
    target-level, except the rare `goal.0` variant (12 occurrences in the
    2024 file, vastly outnumbered by the bare-integer goal convention) -- no
    SDG target is numbered `.0`, so this is a goal-level tag spelled with a
    trailing `.0`.
    """
    goal_part, sep, target_part = token.partition(".")
    if not sep or target_part == "0":
        return int(goal_part), False
    return int(goal_part), True


def explode_sdg(df: pd.DataFrame) -> pd.DataFrame:
    """Explode `sdg_codes_raw` into one row per SDG code token.

    Args:
        df: A `get_tossd()`-shaped frame carrying `sdg_codes_raw`.

    Returns:
        A new frame: every input column, plus one row per `;`-delimited SDG
        token found in `sdg_codes_raw` -- `sdg_code` (the token exactly as
        published), `sdg_goal` (`Int8`, the token's integer goal part),
        `sdg_is_target` (`bool`, whether the token names a specific target
        rather than the goal as a whole), and `sdg_weight` (`float64`,
        `1 / n` for the `n` tokens that source row carried, so a grouped sum
        of `amount * sdg_weight` renormalises to that row's original
        amount). Rows with no SDG tag at all (an empty or null
        `sdg_codes_raw`) contribute nothing to the result: the exploded
        frame's weighted total equals only the SDG-tagged subset of `df`'s
        totals, never `df`'s grand total. Row order is otherwise preserved.

    Raises:
        ValueError: `df` has no `sdg_codes_raw` column, or already carries one
            of this function's own output columns (`sdg_code`, `sdg_goal`,
            `sdg_is_target`, `sdg_weight`) -- re-running `explode_sdg` on its
            own output would otherwise silently duplicate them.
    """
    _require_columns(df, "sdg_codes_raw", func_name="explode_sdg")
    already_exploded = [name for name in _SDG_DERIVED_COLUMNS if name in df.columns]
    if already_exploded:
        raise ValueError(
            f"explode_sdg() found column(s) {', '.join(already_exploded)} already "
            "present in df -- df looks already exploded."
        )

    tokens = df["sdg_codes_raw"].map(_split_sdg_tokens)
    weights = tokens.map(lambda toks: 1.0 / len(toks) if toks else float("nan")).astype(
        "float64"
    )

    exploded = df.copy()
    exploded["sdg_code"] = tokens
    exploded["sdg_weight"] = weights
    exploded = exploded.explode("sdg_code", ignore_index=False)
    exploded = exploded.loc[exploded["sdg_code"].notna()].reset_index(drop=True)

    parsed = [_parse_sdg_token(token) for token in exploded["sdg_code"]]
    exploded["sdg_goal"] = pd.Series(
        [goal for goal, _ in parsed], index=exploded.index, dtype="Int8"
    )
    exploded["sdg_is_target"] = pd.Series(
        [is_target for _, is_target in parsed], index=exploded.index, dtype="bool"
    )

    return exploded[
        [*df.columns, "sdg_code", "sdg_goal", "sdg_is_target", "sdg_weight"]
    ]


# --- add_iso3 --------------------------------------------------------------------


@lru_cache
def _iso3_resolver() -> resolvekit.Resolver:
    """Build (once per process) the bundled-`geo.countries` resolver `add_iso3` uses.

    `resolvekit` is imported lazily inside this function body, never at
    module scope -- see this module's own docstring for why.
    """
    import resolvekit  # noqa: PLC0415 - deliberately lazy: see module docstring

    return resolvekit.Resolver.from_modules(module_ids=[_ISO3_GEO_MODULE], warm=False)


def add_iso3(df: pd.DataFrame) -> pd.DataFrame:
    """Add `provider_iso3`/`recipient_iso3` via resolvekit's OECD numeric-code link.

    ISO3 is looked up by code. `provider_code` `913` and `914` both carry
    `provider_name` "African Development Bank Group" in the published files,
    as do `909` and `1019` for "Inter-American Development Bank Group", so a
    name-keyed join would collapse distinct providers into one row. The
    packaged codelist names them apart, so codes carry no such collision.

    Uses `resolvekit`'s bundled `geo.countries` module, which runs entirely
    offline, with no download step. That module carries the OECD DAC
    provider/recipient numeric codelists as the `oecd:provider` and
    `oecd:recipient` code systems, linked to `iso3`, and its link was
    checked against all 159 packaged provider codes and all 177 recipient
    codes with no mismatch against the packaged codelist's own `iso3`
    column.

    Args:
        df: A `get_tossd()`-shaped frame carrying `provider_code` and/or
            `recipient_code`.

    Returns:
        `df` plus `provider_iso3` and/or `recipient_iso3` (`category`
        dtype), for whichever of `provider_code`/`recipient_code` is
        present. Aggregates (code `0`), multilaterals, and TOSSD-only
        entities all map to `NA`.

    Raises:
        ValueError: Neither `provider_code` nor `recipient_code` is present
            in `df`.
    """
    present = [name for name in _ISO3_LINKS if name in df.columns]
    if not present:
        raise ValueError(
            "add_iso3() needs at least one of 'provider_code'/'recipient_code'; "
            "neither column is present in df."
        )

    resolver = _iso3_resolver()
    result = df.copy()
    for code_column in present:
        iso3_column, code_system = _ISO3_LINKS[code_column]
        resolved = resolver.bulk(
            values=df[code_column], from_system=code_system, to="iso3"
        )
        result[iso3_column] = resolved.astype("category")
    return result


# --- extract_keywords --------------------------------------------------------------


@lru_cache
def _keyword_markers() -> pd.DataFrame:
    """Load the packaged 12-marker keyword table (`_data/keyword_markers.csv`)."""
    with _resources.data_path("keyword_markers.csv") as path:
        return pd.read_csv(path)


def _canonical_keyword(token: str) -> str:
    """Casefold `token` and strip a leading `#`, for marker matching."""
    return token.casefold().lstrip("#")


def _canonical_keyword_set(raw: object) -> frozenset[str]:
    """Canonicalise one row's `|`-delimited `keywords_raw` tokens for marker matching."""
    if pd.isna(raw):
        return frozenset()
    text = str(raw)
    return frozenset(
        _canonical_keyword(token) for token in text.split(_KEYWORD_DELIMITER) if token
    )


def extract_keywords(df: pd.DataFrame) -> pd.DataFrame:
    """Add one boolean `kw_<marker>` column per packaged keyword marker.

    Matching casefolds each `keywords_raw` token and strips a leading `#`,
    so `"COVID-19"` and `"#COVID-19"` both count as the `covid_19` marker.
    Only the fixed 12-marker vocabulary shipped as `_data/keyword_markers.csv`
    is recognised; every other token in `keywords_raw` (315 distinct tokens
    across the full vocabulary) is ignored.

    Args:
        df: A `get_tossd()`-shaped frame carrying `keywords_raw`.

    Returns:
        `df` plus one `kw_<marker>` boolean column per packaged marker
        (`kw_gender`, `kw_adaptation`, `kw_mitigation`, `kw_biodiversity`,
        `kw_ppr_preparedness`, `kw_ppr_response`, `kw_covid_19`,
        `kw_refugees_hostcommunities`, `kw_idps_hostcommunities`,
        `kw_voluntaryrefugeereturn_reintegration`,
        `kw_transnational_benefits_global`, `kw_non_17_3_1`).
        `keywords_raw` itself is left untouched.

    Raises:
        ValueError: `df` has no `keywords_raw` column.
    """
    _require_columns(df, "keywords_raw", func_name="extract_keywords")

    markers = _keyword_markers()
    token_sets = df["keywords_raw"].map(_canonical_keyword_set)

    result = df.copy()
    for marker, column_name in zip(
        markers["marker"], markers["column_name"], strict=True
    ):
        canonical_marker = _canonical_keyword(marker)
        result[f"kw_{column_name}"] = pd.Series(
            [canonical_marker in tokens for tokens in token_sets],
            index=result.index,
            dtype="bool",
        )
    return result


# --- get_structural_breaks ----------------------------------------------------------


@lru_cache
def _load_structural_breaks() -> pd.DataFrame:
    """Load (once per process) the packaged structural-breaks reference table."""
    with _resources.data_path("structural_breaks.csv") as path:
        return pd.read_csv(path)


def get_structural_breaks(*, years: int | Iterable[int] | None = None) -> pd.DataFrame:
    """Return the packaged structural-breaks reference table.

    Documents five verified TOSSD-vintage discontinuities relevant to
    cross-year analysis: sub-pillar tagging's 2022 trace appearance and
    2023 partial rollout, R&D modality (`K02`)'s 2021 introduction, reporter
    base growth spanning 2019-2024, and the 2026 RDRM methodology change.
    This is reference data for a caller to consult -- it does not validate
    or warn against any particular query.

    Args:
        years: A single year, an iterable of years, or `None` (the
            default) for every row. When given, keeps only the rows whose
            `[break_year, end_year]` interval intersects at least one
            requested year -- so `get_structural_breaks(years=query_years)`
            names only the breaks relevant to a `get_tossd(years=query_years)`
            call.

    Returns:
        A new `pandas.DataFrame` (a copy of the cached table, so editing it
        leaves later calls unaffected) with columns `dimension`,
        `break_year`, `end_year`, `description`, `source` -- all 5 rows with
        `years=None`, fewer (or none) once `years=` narrows them. For the
        four discrete breaks `end_year` equals `break_year`; the
        `reporters` row's `end_year` (2024) marks the end of that row's
        continuous 2019-2024 drift, so every year from `break_year` through
        `end_year` counts as affected.
    """
    breaks = _load_structural_breaks().copy()
    if years is None:
        return breaks
    requested = {years} if isinstance(years, int) else {int(year) for year in years}
    mask = breaks.apply(
        lambda row: (
            not requested.isdisjoint(range(row["break_year"], row["end_year"] + 1))
        ),
        axis=1,
    )
    return breaks.loc[mask].reset_index(drop=True)


# --- pillar2_provider_costs -------------------------------------------------------


def pillar2_provider_costs(df: pd.DataFrame) -> pd.DataFrame:
    """Filter pillar-2 rows to the provider-costs carve-out.

    Sector family 930 ("Domestic expenditures for refugees/asylum seekers")
    records spending inside the provider's own territory by definition.
    Sector family 910 ("Administrative Costs of Donors") is a proxy for
    donor administrative overhead, which predominantly stays in the provider
    country, though some administrative costs are incurred at the recipient
    end. Together the two are the share that the AidWatch, Oxfam, and
    ActionAid critique of TOSSD Pillar II identifies as the domestic-spending
    share of Pillar II.

    On the 2024 vintage the two families cover 27,275 of 155,908 pillar-2
    rows (17.5%), 35.6% of pillar-2 gross disbursements, and 31.0% of
    pillar-2 commitments, consistent with the roughly 30% share that
    critique attributes to these costs. Sector family 720 ("Humanitarian
    Assistance") sits outside the carve-out. Those rows are in-country
    humanitarian aid delivered by agencies such as UNHCR and UNICEF.

    TOSSD's Reporting Instructions describe this category as "expenditures
    in the provider country". Analysts commonly call this spending
    "in-donor" costs. TOSSD does not publish a ready-made carve-out
    matching that label, so this is a heuristic built from sector families
    910 and 930 that approximate it.

    Args:
        df: A `get_tossd()`-shaped frame carrying `tossd_pillar` and
            `sector_code` (`sector_code` is present under
            `columns="analysis"`/`"all"`, or any explicit `columns=` list
            naming it; `tossd_pillar` is always present in `get_tossd()`
            output).

    Returns:
        `df` filtered to `tossd_pillar == 2` rows whose `sector_code` is
        `910` ("Administrative Costs of Donors") or `930` ("Domestic
        expenditures for refugees/asylum seekers").

    Raises:
        ValueError: `df` is missing `tossd_pillar` or `sector_code`.
    """
    _require_columns(
        df, "tossd_pillar", "sector_code", func_name="pillar2_provider_costs"
    )
    mask = (df["tossd_pillar"] == 2) & df["sector_code"].isin(
        _PROVIDER_COST_SECTOR_CODES
    )
    return df.loc[mask].copy()
