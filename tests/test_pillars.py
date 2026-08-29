"""Unit tests for pillar/sub-pillar token normalisation."""

from __future__ import annotations

import pytest

from tossd_reader import _pillars


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        (1, ("1", None)),
        ("1", ("1", None)),
        ("I", ("1", None)),
        ("i", ("1", None)),
        (2, ("2", None)),
        ("2", ("2", None)),
        ("II", ("2", None)),
        (21, ("2", "21")),
        ("21", ("2", "21")),
        ("II.A", ("2", "21")),
        ("ii.a", ("2", "21")),
        (22, ("2", "22")),
        ("22", ("2", "22")),
        ("II.B", ("2", "22")),
    ],
)
def test_every_pillar_token_normalises_correctly(
    token: int | str, expected: tuple
) -> None:
    """Every documented pillar token maps to the right (pillar, subpillar) pair."""
    assert _pillars.normalise_pillar_token(token) == expected


def test_unknown_pillar_token_raises_value_error() -> None:
    """An unrecognised pillars= token raises ValueError, not a silent no-op."""
    with pytest.raises(ValueError, match="pillars"):
        _pillars.normalise_pillar_token("III")


def test_pillar_bool_token_raises_value_error_not_silently_matched_as_int() -> None:
    """bool is excluded before the int check, since Python's bool subclasses int and would otherwise match pillars=1."""
    with pytest.raises(ValueError, match="pillars"):
        _pillars.normalise_pillar_token(True)
