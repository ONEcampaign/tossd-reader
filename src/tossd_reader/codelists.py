"""Runtime loader for tossd_reader's packaged OECD codelist snapshot.

Reads only the packaged CSVs and `_version.json` under `_data/codelists/` --
no network access, and no import of `oda_reader` (that lives in the
maintainer-only `codelists` dependency group; `scripts/refresh_codelists.py`
is what produces the snapshot this module reads).

No name-resolution logic lives here: turning a user-supplied name or code
into a validated filter value is the query layer's job. This module only
loads and reports what is packaged.
"""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache

import pandas as pd

from tossd_reader import _resources
from tossd_reader._discovery import known_years

_YEARS_KEY = "years"


@lru_cache
def _available_dimensions() -> tuple[str, ...]:
    """Return every packaged codelist dimension name, sorted alphabetically."""
    with _resources.data_path("codelists") as path:
        names = [child.stem for child in path.glob("*.csv")]
    return tuple(sorted(names))


def load_codelist(dimension: str) -> pd.DataFrame:
    """Load one packaged codelist dimension's frame.

    Args:
        dimension: One of the packaged dimension names -- `provider`,
            `recipient`, `pillar`, `financing_arrangement`,
            `framework_of_collaboration`, `purpose`, `sector`, `channel`,
            `modality`, `finance_instrument`.

    Returns:
        A `pandas.DataFrame` with `code`, `name`, and `tossd_only` columns
        (plus `iso3` for `provider`/`recipient`; `source` for `sector`,
        `"codelist"` for a row fetched from the OECD codelist or the
        packaged snapshot's own value for a supplemental row not carried by
        that codelist, e.g. code `700`; `in_published_data` once the
        packaged snapshot has been annotated, marking whether the code
        actually occurs in the published TOSSD data -- pillar excepted, its
        rows are structural, and the annotation scans flat data columns
        pillar does not have), sorted by `code` as packaged. Each call
        returns a fresh copy, so callers can mutate the result without
        poisoning later calls.

    Raises:
        ValueError: `dimension` is not one of the packaged dimensions.
    """
    return _load_codelist_cached(dimension).copy()


@lru_cache
def _load_codelist_cached(dimension: str) -> pd.DataFrame:
    """Read and cache one packaged codelist CSV (shared object; do not expose)."""
    available = _available_dimensions()
    if dimension not in available:
        raise ValueError(
            f"Unknown codelist dimension {dimension!r}; available: "
            f"{', '.join(available)}."
        )
    with _resources.data_path("codelists", f"{dimension}.csv") as path:
        return pd.read_csv(path, dtype={"code": str})


def get_available_filters() -> dict[str, pd.DataFrame]:
    """Return every `get_tossd` filter dimension a user can browse.

    Covers every packaged codelist dimension (name/code/tossd-only-flag
    frames for provider, recipient, pillar, financing_arrangement,
    framework_of_collaboration, purpose, sector, channel, modality, and
    finance_instrument -- `sector` additionally carries a `source` column,
    and every dimension but `pillar` gains an `in_published_data` column
    once the packaged snapshot has been annotated) plus `years`, the
    packaged known-years set.

    Returns:
        `{dimension: frame}`, one entry per packaged codelist dimension plus
        a `"years"` entry (a single-column `year` frame built from
        `_discovery.known_years()`).
    """
    filters = {
        dimension: load_codelist(dimension) for dimension in _available_dimensions()
    }
    filters[_YEARS_KEY] = pd.DataFrame({"year": list(known_years())})
    return filters


@lru_cache
def get_codelists_version() -> str:
    """Return the packaged codelist snapshot's fetch date (ISO, date only).

    Returns:
        The `_version.json` `fetched_at` stamp's date portion, e.g.
        `"2026-08-28"`.
    """
    with _resources.data_path("codelists", "_version.json") as path:
        payload = json.loads(path.read_text())
    return datetime.fromisoformat(payload["fetched_at"]).date().isoformat()
