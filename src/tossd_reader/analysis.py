"""Post-query analysis toolkit for `get_tossd()` output.

`explode_sdg`, `add_iso3`, `extract_keywords`, `filter_provider_costs`,
`add_recipient_group`, and `add_instrument_group` each operate on a
`pandas.DataFrame` already shaped like `get_tossd()`'s output (snake_case
columns) and raise a `ValueError` naming any column they need but don't
find, rather than a bare `KeyError` -- `add_instrument_group` additionally
raises `UnknownCodeError` for a `finance_instrument_code` value the packaged
table doesn't cover (never a `ValueError`; see its own docstring). Each
returns a new frame, leaving the caller's frame untouched and copying its
`attrs`. `get_structural_breaks` takes no frame at all: it returns the
packaged structural-breaks reference table.

`add_iso3` is the one helper here that touches `resolvekit`: `import
resolvekit` happens lazily, inside `_iso3_resolver`'s own body, never at
module scope -- a package-level import stays banned project-wide (see
`_matching.py`'s `_suggest_with_resolvekit`), so a bare `import tossd_reader`,
or calling any of this module's other helpers, never pulls resolvekit into
`sys.modules`.
"""

from __future__ import annotations

import json
import warnings
from collections.abc import Iterable
from functools import lru_cache
from typing import TYPE_CHECKING, Literal

import pandas as pd

from tossd_reader import (
    _accessor,  # noqa: F401 - registers df.tossd
    _resources,
    _schema,
)
from tossd_reader.exceptions import UnknownCodeError

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
expenditures for refugees/asylum seekers". See `filter_provider_costs`
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


def _require_numeric_column(df: pd.DataFrame, value: str, *, func_name: str) -> None:
    """Raise `ValueError` naming `value` if `df[value]` isn't numeric-dtyped.

    Only called after the column's presence is already confirmed (e.g. via
    `_require_columns`), so `df[value]` is safe to access here. Mirrors
    `verbs.py`'s own `_require_numeric_value` message shape -- kept as a
    local copy rather than a shared import, since `verbs.py` imports
    `analysis`, not the other way around.
    """
    if not pd.api.types.is_numeric_dtype(df[value]):
        raise ValueError(
            f"{func_name}() needs value={value!r} to be numeric; df[{value!r}] "
            f"is {df[value].dtype} dtype."
        )


def explode_sdg(df: pd.DataFrame, *, value: str | None = None) -> pd.DataFrame:
    """Explode `sdg_codes_raw` into one row per SDG code token.

    Args:
        df: A `get_tossd()`-shaped frame carrying `sdg_codes_raw`.
        value: An amount column name. When given, the result gains a sibling
            `{value}_weighted` column (`df[value] * sdg_weight`) alongside
            the untouched original `value` column -- never overwriting it,
            since the same column name would mean a different thing
            depending on what last touched the frame. `None` (the default):
            today's behaviour, byte-identical output.

    Returns:
        A new frame: every input column, plus one row per `;`-delimited SDG
        token found in `sdg_codes_raw` -- `sdg_code` (the token exactly as
        published), `sdg_goal` (`Int8`, the token's integer goal part),
        `sdg_is_target` (`bool`, whether the token names a specific target
        rather than the goal as a whole), and `sdg_weight` (`float64`,
        `1 / n` for the `n` tokens that source row carried, so a grouped sum
        of `amount * sdg_weight` renormalises to that row's original
        amount). When `value` is given, also `{value}_weighted`
        (`df[value] * sdg_weight`, `float64`) -- a grouped sum of it equals
        the SDG-tagged subset's original `value` total, the same
        renormalisation identity `sdg_weight` already gives any ad hoc
        `amount * sdg_weight` multiplication, just precomputed and named.
        Rows with no SDG tag at all (an empty or null `sdg_codes_raw`)
        contribute nothing to the result: the exploded frame's weighted
        total equals only the SDG-tagged subset of `df`'s totals, never
        `df`'s grand total. Row order is otherwise preserved.

    Raises:
        ValueError: `df` has no `sdg_codes_raw` column (or, when `value` is
            given, no `value` column); `value` is given but `df[value]` isn't
            numeric-dtyped; or `df` already carries one of this function's
            own output columns (`sdg_code`, `sdg_goal`, `sdg_is_target`,
            `sdg_weight`, and `{value}_weighted` when `value` is given) --
            re-running `explode_sdg` on its own output would otherwise
            silently duplicate them.
    """
    _require_columns(df, "sdg_codes_raw", func_name="explode_sdg")
    weighted_column = None
    derived_columns = list(_SDG_DERIVED_COLUMNS)
    if value is not None:
        _require_columns(df, value, func_name="explode_sdg")
        _require_numeric_column(df, value, func_name="explode_sdg")
        weighted_column = f"{value}_weighted"
        derived_columns.append(weighted_column)

    already_exploded = [name for name in derived_columns if name in df.columns]
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

    output_columns = [
        *df.columns,
        "sdg_code",
        "sdg_goal",
        "sdg_is_target",
        "sdg_weight",
    ]
    if weighted_column is not None:
        exploded[weighted_column] = exploded[value] * exploded["sdg_weight"]
        output_columns.append(weighted_column)

    return exploded[output_columns]


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


# --- filter_provider_costs -------------------------------------------------------


def filter_provider_costs(df: pd.DataFrame) -> pd.DataFrame:
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
        df, "tossd_pillar", "sector_code", func_name="filter_provider_costs"
    )
    mask = (df["tossd_pillar"] == 2) & df["sector_code"].isin(
        _PROVIDER_COST_SECTOR_CODES
    )
    return df.loc[mask].copy()


# --- add_recipient_group -----------------------------------------------------------


_RECIPIENT_GROUP_COLUMN = "recipient_group"
_RECIPIENT_GROUP_SCHEME_COLUMNS: dict[str, str] = {
    "ldc": "ldc_group",
    "income": "income_group",
    "region": "region",
}
"""`scheme= -> the packaged recipient_groups.csv column it reads."""

_warned_unknown_recipient_codes: set[str] = set()
"""Warn-once state for `add_recipient_group`, the analysis-side counterpart
of `query.py`'s `_warned_unknown_codes` (a `dict[str, set[str]]` there
because it covers several decode columns; a flat `set[str]` here because
every scheme reads the same `recipient_code` key from one packaged table, so
a code is either in that table or it isn't, regardless of scheme)."""


def _reset_for_tests() -> None:
    """Clear this module's warn-once state (test isolation helper, not conftest-wired)."""
    _warned_unknown_recipient_codes.clear()


@lru_cache
def _load_recipient_groups() -> pd.DataFrame:
    """Load (once per process) the packaged recipient-groups table."""
    with _resources.data_path("recipient_groups.csv") as path:
        return pd.read_csv(path)


@lru_cache
def get_recipient_groups_version() -> str:
    """Return the packaged recipient-groups table's version stamp.

    Returns:
        The composite stamp recorded in `_data/recipient_groups_version.json`
        (its `"version"` field), e.g. `"ldc-2024review/wb-fy27"` --
        independently naming the UN LDC-list vintage (`ldc`/`region` schemes
        don't move on their own cadence) and the World Bank income
        classification's fiscal year (`income` scheme) the packaged table
        was built from.
    """
    with _resources.data_path("recipient_groups_version.json") as path:
        payload = json.loads(path.read_text())
    return payload["version"]


def _warn_unknown_recipient_codes(missing_values: list[object]) -> None:
    """Warn once (per never-before-seen `recipient_code`) that it has no packaged group.

    Mirrors `query.py`'s `_warn_unknown_decode_codes`: only codes not already
    warned about this session are reported, so a second call over the same
    unmapped codes stays quiet.
    """
    new_missing = sorted(
        {str(value) for value in missing_values} - _warned_unknown_recipient_codes,
        key=str,
    )
    if not new_missing:
        return
    _warned_unknown_recipient_codes.update(new_missing)
    warnings.warn(
        f"{len(new_missing)} recipient_code value(s) not in the packaged "
        f"recipient-groups table (version {get_recipient_groups_version()}, "
        "vintage newer than snapshot?): "
        f"{', '.join(new_missing)}. add_recipient_group() returns NA for these rows.",
        stacklevel=3,
    )


def add_recipient_group(
    df: pd.DataFrame, *, scheme: Literal["ldc", "income", "region"] = "ldc"
) -> pd.DataFrame:
    """Add `recipient_group`, joined from the packaged recipient-groups table.

    Args:
        df: A `get_tossd()`-shaped frame carrying `recipient_code`.
        scheme: Which grouping to apply -- `"ldc"` (Least Developed
            Countries / Other Developing Countries), `"income"` (World Bank
            income group), or `"region"` (the UN region TOSSD itself
            publishes per recipient, the same value `get_tossd()`'s own
            `region_name` column carries).

    Returns:
        `df` plus `recipient_group` (`category`), one value per
        `recipient_code` read from the table `get_recipient_groups_version()`
        names.

        Regional/multi-country recipient codes (e.g. "Europe, regional",
        "Global" -- codes with no `iso3` in the packaged recipient codelist)
        carry an explicit `"Regional / Multi-country Unallocated"` value under
        `"ldc"`/`"income"`; `"region"` never produces it, since TOSSD
        publishes a real region for these codes too. Six non-self-governing
        territories the World Bank does not publish independent GNI data for
        (Saint Helena, Montserrat, Cook Islands, Niue, Tokelau, Wallis and
        Futuna) carry `"Unclassified"` under `"income"` -- distinct from
        `"Regional / Multi-country Unallocated"`, since these are real,
        single-territory codes, not aggregates.

        A `recipient_code` absent from the packaged table (a TOSSD vintage
        newer than the snapshot) resolves to `NA` and triggers a
        once-per-code warning rather than an error, so a full-frame call
        stays usable.

        São Tomé and Príncipe (`recipient_code` 268) graduated from LDC
        status on 2024-12-06. The packaged table reflects the *current* LDC
        list, so it classifies STP as `"Other Developing Countries"` even
        for 2024 rows reported before that date -- an analyst reconciling
        against a 2024-vintage LDC classification should treat STP as LDC
        for that year instead of trusting this column.

    Raises:
        ValueError: `df` has no `recipient_code` column, `scheme` is not one
            of `"ldc"`/`"income"`/`"region"`, or `df` already carries a
            `recipient_group` column.
    """
    _require_columns(df, "recipient_code", func_name="add_recipient_group")
    if scheme not in _RECIPIENT_GROUP_SCHEME_COLUMNS:
        valid = ", ".join(
            repr(name) for name in sorted(_RECIPIENT_GROUP_SCHEME_COLUMNS)
        )
        raise ValueError(
            f"add_recipient_group() scheme={scheme!r} is not one of {valid}."
        )
    if _RECIPIENT_GROUP_COLUMN in df.columns:
        raise ValueError(
            f"add_recipient_group() found column '{_RECIPIENT_GROUP_COLUMN}' "
            "already present in df -- df looks already grouped."
        )

    table = _load_recipient_groups()
    scheme_column = _RECIPIENT_GROUP_SCHEME_COLUMNS[scheme]
    mapping = dict(zip(table["recipient_code"], table[scheme_column], strict=True))

    codes = df["recipient_code"]
    group = codes.map(mapping, na_action="ignore")

    unmapped_mask = codes.notna() & group.isna()
    if unmapped_mask.any():
        _warn_unknown_recipient_codes(codes.loc[unmapped_mask].unique().tolist())

    result = df.copy()
    result[_RECIPIENT_GROUP_COLUMN] = group.astype("category")
    result.attrs = dict(df.attrs)
    return result


# --- add_instrument_group -----------------------------------------------------------


_INSTRUMENT_GROUP_COLUMN = "instrument_group"
_LOAN_FAMILY_BASE_GROUP = "Non-concessional Loans"
"""The packaged table's placeholder value for the debt-instrument code
family (`420`-`425`, plus the observed `4221`/`4222`) -- not a fixed answer,
a sentinel `add_instrument_group` overrides per-row via
`concessionality_flag`. See that function's docstring."""

_CONCESSIONAL_LOANS_GROUP = "Concessional Loans"


@lru_cache
def _load_instrument_groups() -> pd.DataFrame:
    """Load (once per process) the packaged instrument-groups table."""
    with _resources.data_path("instrument_groups.csv") as path:
        return pd.read_csv(path)


@lru_cache
def get_instrument_groups_version() -> str:
    """Return the packaged instrument-groups table's version stamp.

    Returns:
        The composite stamp recorded in `_data/instrument_groups_version.json`
        (its `"version"` field), e.g.
        `"oecd-dac-cl15-2026-09-01/instrument-groups-methodology-v2"` --
        independently naming the OECD DAC CRS++ "List 15: Type of finance"
        fetch date the packaged `finance_instrument` codelist (and this
        table) were checked against, and this project's own group-assignment
        methodology revision, which moves independently of the OECD list
        (v2 additionally maps the codes real submissions carry that List 15
        itself doesn't yet flag `tossd`-applicable -- see
        `add_instrument_group`).
    """
    with _resources.data_path("instrument_groups_version.json") as path:
        payload = json.loads(path.read_text())
    return payload["version"]


def add_instrument_group(df: pd.DataFrame) -> pd.DataFrame:
    """Add `instrument_group`, joined from the packaged instrument-groups table.

    `finance_instrument_code` alone decides every group except the
    debt-instrument family (`420` "DEBT INSTRUMENTS" and its children `421`
    "Standard loan" through `425` "Other debt securities", plus `4221`
    "Loan-type reimbursable grant" and `4222` "Reflow-based reimbursable
    grant" -- both `422` "Reimbursable grant" sub-variants by name and
    real-data concessionality profile), which additionally needs
    `concessionality_flag`: flag `1` -> `"Concessional Loans"`, flag `0` ->
    `"Non-concessional Loans"`, a blank flag -> `NA` (17 rows in the 2024
    vintage, concentrated in code `421`, the highest-volume debt instrument
    -- there is no separate concessional/non-concessional code, only the one
    flag column).

    Groups: `"Grants"` (`100`/`110`), `"Non-concessional Loans"` /
    `"Concessional Loans"` (the debt family, see above),
    `"Hybrid/Mezzanine"` (`430`-`434`, the mezzanine-finance family),
    `"Equity"` (`500`/`510`/`520`), `"Guarantees"` (`1000`/`1100`, plus
    `1101` "Individual loan guarantee" and `1102` "Loan portfolio
    guarantee" by name and real-data concessionality profile -- overwhelmingly
    blank, matching `1100`, not the debt family's mixed split),
    `"Direct Provider Spending"` (`2000`/`2100`, its own group -- not a
    transfer to a recipient at all), `"Subsidies"` (`3000`/`3100`), and
    `"Other Instruments"` (`310` "Capital subscription on deposit basis",
    orphaned in the codelist's own header hierarchy -- no `300` parent row
    exists unlike every other family; and `0` "NON FLOW ITEMS", 3 real rows
    across 2019-2024, one provider (Korea, `provider_code` 742), each
    carrying a real `usd_disbursement` -- OECD's own List 15 flags it
    CRS-only, and its name argues for excluding it from a financing-flow
    breakdown entirely, but it is a real, non-blank code on real rows with
    real dollar amounts, not a structurally-blank pseudo-aggregate, so it
    gets an honest bucket here rather than `NA`).

    `100`, `110`, `310`, `420`-`425`, `430`-`434`, `500`, `510`, `520`,
    `1000`, `1100`, `2000`, `2100`, `3000`, `3100` come from the packaged
    `finance_instrument` codelist; `0`, `1101`, `1102`, `4221`, `4222` do
    not -- OECD's own live List 15 still flags all five `tossd="0"` (CRS-only)
    as of `get_instrument_groups_version()`'s fetch date, even though real
    2023-2024 TOSSD submissions carry them, so a codelist refresh alone can
    never add them (see `scripts/refresh_codelists.py`'s own `--check`,
    which reports zero drift against the live source). They are mapped
    directly here instead, from each code's official List-15 name and its
    real-data profile, distinguished from the codelist-sourced rows by the
    packaged table's own `source` column (`"codelist"`/`"observed"`) for
    anyone auditing where a mapping came from.

    Args:
        df: A `get_tossd()`-shaped frame carrying `finance_instrument_code`
            and `concessionality_flag`.

    Returns:
        `df` plus `instrument_group` (`category`). A blank/`NA`
        `finance_instrument_code` (every pseudo-aggregate row --
        `provider_code == 0` -- carries one) resolves to `NA`, not an error,
        so a full-frame call including aggregates stays usable. `NA` rows
        carry material dollar volume of their own (pseudo-aggregates plus
        blank-concessionality debt rows, roughly 20% of 2024 disbursements
        combined) and pandas' own `groupby` drops `NaN` keys by default, so
        totalling by `instrument_group` needs `dropna=False` or excluding
        aggregates first to avoid silently losing that share.

    Raises:
        ValueError: `df` is missing `finance_instrument_code` or
            `concessionality_flag`, or already carries an `instrument_group`
            column.
        UnknownCodeError: A non-null `finance_instrument_code` value is
            absent from the packaged table -- never silently grouped into
            `"Other Instruments"`. Reserved for a genuinely new or malformed
            code (a typo, or a future vintage's drift): every code observed
            in the six cached 2019-2024 TOSSD vintages is mapped, whether or
            not OECD's own codelist covers it yet.
    """
    _require_columns(
        df,
        "finance_instrument_code",
        "concessionality_flag",
        func_name="add_instrument_group",
    )
    if _INSTRUMENT_GROUP_COLUMN in df.columns:
        raise ValueError(
            f"add_instrument_group() found column '{_INSTRUMENT_GROUP_COLUMN}' "
            "already present in df -- df looks already grouped."
        )

    table = _load_instrument_groups()
    mapping = dict(
        zip(table["finance_instrument_code"], table["instrument_group"], strict=True)
    )

    codes = df["finance_instrument_code"]
    group = codes.map(mapping, na_action="ignore")

    unmapped_mask = codes.notna() & group.isna()
    if unmapped_mask.any():
        unknown = sorted(
            {str(code) for code in codes.loc[unmapped_mask].unique()}, key=str
        )
        raise UnknownCodeError(
            "add_instrument_group() found finance_instrument_code value(s) "
            f"{', '.join(unknown)} not in the packaged instrument-groups table "
            f"(version {get_instrument_groups_version()}). This TOSSD vintage "
            "carries a code the packaged snapshot doesn't cover yet -- refresh "
            "it via scripts/refresh_codelists.py, or check "
            "get_instrument_groups_version()."
        )

    is_loan_family = (group == _LOAN_FAMILY_BASE_GROUP).fillna(False)
    flags = df["concessionality_flag"]
    concessional_override = is_loan_family & (flags == 1).fillna(False)
    blank_flag_override = is_loan_family & flags.isna()

    group = group.mask(concessional_override, _CONCESSIONAL_LOANS_GROUP)
    group = group.mask(blank_flag_override, pd.NA)

    result = df.copy()
    result[_INSTRUMENT_GROUP_COLUMN] = group.astype("category")
    result.attrs = dict(df.attrs)
    return result
