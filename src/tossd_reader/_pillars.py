"""Pillar/sub-pillar token resolution and sub-pillar year policy.

Private module. Consumed by query.py (and the tests). Row-level pillar
filtering (`_filter_pillar`) deliberately stays in query.py.
"""

from __future__ import annotations

import warnings

from tossd_reader.exceptions import InvalidPillarError

_SUBPILLAR_MIN_YEAR = 2023
_SUBPILLAR_COVERAGE_WARN_YEAR = 2023
_PILLAR_2022_TRACE_ROWS = 24
"""2022 carries only 24 `Tossdpillar2='21'` trace rows (out of ~128,900
pillar-2 rows); the substantive rollout starts in 2023."""

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


class _PillarsState:
    """Mutable singleton state backing this module's warn-once accessors."""

    def __init__(self) -> None:
        self.warned_subpillar_narrow = False
        self.warned_subpillar_2023_coverage = False


_state = _PillarsState()


def normalise_pillar_token(pillar: int | str) -> tuple[str, str | None]:
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


def resolve_subpillar_years(
    resolved_years: tuple[int, ...], *, years_was_none: bool
) -> tuple[int, ...]:
    """Apply the sub-pillar year policy, returning the (possibly narrowed) years."""
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
        # 5 frames up from here: _warn_subpillar_narrowed ->
        # _resolve_subpillar_years -> _build_table -> get_tossd -> the
        # caller (only get_tossd reaches this path; export() forces
        # pillars=None).
        stacklevel=5,
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
        # Same 5-frame chain as _warn_subpillar_narrowed.
        stacklevel=5,
    )


def _reset_for_tests() -> None:
    """Clear this module's warn-once state.

    Test-only. Wired into `tests/conftest.py`'s shared autouse fixture
    (alongside _discovery's, config's, and query's own resets), rather than
    a local per-file fixture.
    """
    _state.warned_subpillar_narrow = False
    _state.warned_subpillar_2023_coverage = False
