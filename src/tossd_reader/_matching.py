"""Resolve `providers=`/`recipients=` tokens to packaged codelist codes.

Private module. Consumed by query.py (and the tests). Fuzzy COLUMN-name
suggestion (for an unrecognised `columns=` entry) deliberately stays in
query.py.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable

from tossd_reader import codelists
from tossd_reader.exceptions import UnknownCodeError

MAX_SUGGESTIONS = 5


def resolve_dimension_codes(
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
