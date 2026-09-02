"""Resolve `providers=`/`recipients=`/`filters=` tokens to packaged codelist codes.

Private module. Consumed by query.py (row filters), codes.py (`lookup`), and
the tests. Fuzzy COLUMN-name suggestion (for an unrecognised `columns=`
entry) deliberately stays in query.py.

`_suggest_with_resolvekit` imports `resolvekit` lazily, inside its own
body -- a package-level import stays banned project-wide, so importing
this module never pulls resolvekit into `sys.modules`.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable
from typing import cast

from tossd_reader import codelists
from tossd_reader.exceptions import UnknownCodeError

MAX_SUGGESTIONS = 5

# Dimensions whose packaged codelist `code` column backs a `category<string>`
# frame column (`modality_code`, `financing_arrangement_code`,
# `framework_of_collaboration_code`) rather than an `Int16`/`Int32` one.
# `resolve_one_code` returns the resolved value as `str` for these (e.g.
# `"B02"`), `int` for every other dimension -- see `_schema.csv`'s
# `target_dtype` column.
STR_CODED_DIMENSIONS = frozenset(
    {"modality", "financing_arrangement", "framework_of_collaboration"}
)


def resolve_dimension_codes(
    values: int | str | Iterable[int | str] | None,
    *,
    dimension: str,
    label: str,
) -> tuple[int, ...] | tuple[str, ...] | None:
    """Resolve a `providers=`/`recipients=`/`filters=` value to a tuple of codes, or `None` (no filter)."""
    if values is None:
        return None
    tokens = [values] if isinstance(values, int | str) else list(values)
    resolved = tuple(
        resolve_one_code(token, dimension=dimension, label=label) for token in tokens
    )
    # Every element comes from the SAME dimension, so it's homogeneously
    # int or str (per STR_CODED_DIMENSIONS) -- a property `resolve_one_code`
    # guarantees but a plain comprehension's inferred `tuple[int | str, ...]`
    # doesn't statically capture.
    return cast("tuple[int, ...] | tuple[str, ...]", resolved)


def resolve_one_code(token: int | str, *, dimension: str, label: str) -> int | str:
    """Resolve one code/name/digit-string token against `dimension`'s packaged codelist.

    The single-token building block `resolve_dimension_codes` maps over;
    also consumed directly by `codes.lookup`, so a lookup and a
    `filters=`/`providers=`/`recipients=` resolution can never disagree
    about what a token means.

    Returns an `int` for every dimension except `STR_CODED_DIMENSIONS`
    (`modality`, `financing_arrangement`, `framework_of_collaboration`),
    which return the packaged codelist's own `str` code (e.g. `"B02"`).
    """
    if isinstance(token, bool) or not isinstance(token, int | str):
        raise TypeError(
            f"{label} filter values must be int or str, got {token!r} "
            f"({type(token).__name__})."
        )
    str_coded = dimension in STR_CODED_DIMENSIONS
    if isinstance(token, int):
        if str_coded:
            raise TypeError(
                f"{label} filter values must be str (the packaged codelist's "
                f"own code, e.g. 'B02') for {dimension!r}, got int {token!r}: "
                f"{dimension!r} codes aren't numeric."
            )
        return token

    stripped = token.strip()
    if str_coded:
        code = _match_code(dimension, stripped)
        if code is not None:
            return code
    elif stripped.isdigit():
        code = _match_code(dimension, stripped)
        if code is not None:
            return int(code)
    code = _match_name(dimension, stripped)
    if code is not None:
        return code if str_coded else int(code)
    raise _unknown_code_error(token, dimension=dimension, label=label)


def _match_code(dimension: str, token: str) -> str | None:
    """Return `token`'s code (as packaged, `str`) if it matches a codelist code exactly."""
    frame = codelists.load_codelist(dimension)
    matches = frame.loc[frame["code"] == token, "code"]
    return None if matches.empty else str(matches.iloc[0])


def _match_name(dimension: str, token: str) -> str | None:
    """Return `token`'s code (as packaged, `str`) if it case-foldedly exact-matches a codelist name."""
    frame = codelists.load_codelist(dimension)
    folded = token.casefold()
    matches = frame.loc[frame["name"].str.casefold() == folded, "code"]
    return None if matches.empty else str(matches.iloc[0])


def closest_matches_note(suggestions: list[str]) -> str:
    """Format a " Closest matches: ..." suffix, or "" if `suggestions` is empty."""
    return f" Closest matches: {', '.join(suggestions)}." if suggestions else ""


def _unknown_code_error(token: str, *, dimension: str, label: str) -> UnknownCodeError:
    """Build UnknownCodeError, carrying `token` and up to 5 sorted suggestions."""
    suggestion_note = closest_matches_note(_suggest(dimension, token))
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
        candidates = resolver.diagnostics.search(token, top_k=MAX_SUGGESTIONS)
        names = set()
        for candidate in candidates:
            record = resolver.entity(candidate.entity_id)
            if record is not None:
                names.add(record.canonical_name)
        return sorted(names)[:MAX_SUGGESTIONS]
    finally:
        resolver.close()


def _suggest_with_difflib(dimension: str, token: str) -> list[str]:
    """Fallback suggestions via stdlib difflib, if resolvekit's shape resists us."""
    frame = codelists.load_codelist(dimension)
    return sorted(
        difflib.get_close_matches(token, frame["name"].tolist(), n=MAX_SUGGESTIONS)
    )
