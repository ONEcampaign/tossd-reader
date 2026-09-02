"""Browse and resolve packaged codelist codes -- the read-only companion to `filters=`.

`browse()` is a thin pass-through to `codelists.load_codelist` (every
packaged dimension, `"pillar"` included). `lookup()` resolves a token
through the exact same `_matching` path `get_tossd`'s `providers=`/
`recipients=`/`filters=` use, so a `codes.lookup()` result and a filter
built from the same token can never disagree about what it means --
`lookup()` covers every dimension `filters=` does, plus `provider`/
`recipient` (which have their own dedicated `get_tossd` kwargs, not a
`filters=` entry, but resolve through the same `_matching` machinery).
`"pillar"` is deliberately excluded from `lookup()` -- a `pillars=` token
like `"II.A"` doesn't resolve to a flat codelist code the way every other
dimension does; see `_pillars.normalise_pillar_token` instead.
"""

from __future__ import annotations

import difflib

import pandas as pd

from tossd_reader import _matching, codelists

# Every dimension `lookup()` accepts -- the packaged codelist dimensions
# that resolve to a flat code via `_matching`. `browse()` accepts a wider
# set (every packaged codelist, `"pillar"` included) since it does no
# resolution of its own.
LOOKUP_DIMENSIONS: tuple[str, ...] = (
    "provider",
    "recipient",
    "sector",
    "purpose",
    "channel",
    "modality",
    "finance_instrument",
    "financing_arrangement",
    "framework_of_collaboration",
)


def browse(dimension: str) -> pd.DataFrame:
    """Return one packaged codelist dimension's frame, as a fresh copy.

    Args:
        dimension: One of the packaged dimension names -- `provider`,
            `recipient`, `pillar`, `sector`, `purpose`, `channel`,
            `modality`, `finance_instrument`, `financing_arrangement`,
            `framework_of_collaboration`.

    Returns:
        `codelists.load_codelist(dimension)`'s frame: `code`, `name`, and
        `tossd_only` columns (plus `iso3` for `provider`/`recipient`).

    Raises:
        ValueError: `dimension` is not one of the packaged dimensions.

    Example:
        >>> import tossd_reader
        >>> modality = tossd_reader.codes.browse("modality")
        >>> modality.loc[modality["code"] == "B02", "name"].item()
        'Core contributions to multilateral institutions'
    """
    return codelists.load_codelist(dimension)


def lookup(dimension: str, token: int | str) -> int | str:
    """Resolve one code/name token to its packaged code, in the type filters use.

    Goes through `_matching.resolve_one_code` -- the same building block
    `get_tossd`'s `providers=`/`recipients=`/`filters=` resolve each of
    their own tokens with, so this can never disagree with what a filter
    built from `token` would match.

    Args:
        dimension: One of `LOOKUP_DIMENSIONS`.
        token: A code, a digit-string code, or a name (case-folded for the
            name match) -- same resolution rules as `providers=`/
            `recipients=`/`filters=`'s own values.

    Returns:
        The resolved code: `int` for `provider`/`recipient`/`sector`/
        `purpose`/`channel`/`finance_instrument`; `str` (the packaged
        codelist's own code, e.g. `"B02"`) for `modality`/
        `financing_arrangement`/`framework_of_collaboration`.

    Raises:
        ValueError: `dimension` is not one of `LOOKUP_DIMENSIONS` (naming
            the valid ones; `"pillar"` points at `pillars=` instead, since
            a pillar token doesn't resolve to a flat code).
        UnknownCodeError: `token` matches no code or name in `dimension`'s
            packaged codelist.

    Example:
        >>> import tossd_reader
        >>> tossd_reader.codes.lookup(
        ...     "modality", "Core contributions to multilateral institutions"
        ... )
        'B02'
        >>> tossd_reader.codes.lookup("sector", "110")
        110
    """
    if dimension not in LOOKUP_DIMENSIONS:
        raise ValueError(_unknown_dimension_message(dimension))
    return _matching.resolve_one_code(token, dimension=dimension, label=dimension)


def _unknown_dimension_message(dimension: str) -> str:
    """Build lookup()'s ValueError message for an unrecognised dimension."""
    suggestions = difflib.get_close_matches(
        dimension, LOOKUP_DIMENSIONS, n=_matching.MAX_SUGGESTIONS
    )
    suggestion_note = _matching.closest_matches_note(suggestions)
    pillar_note = (
        " Pillar tokens ('1', 'II.A', ...) resolve via get_tossd(pillars=...), "
        "not codes.lookup()."
        if dimension == "pillar"
        else ""
    )
    return (
        f"Unknown lookup() dimension {dimension!r}; expected one of "
        f"{', '.join(LOOKUP_DIMENSIONS)}.{suggestion_note}{pillar_note}"
    )
