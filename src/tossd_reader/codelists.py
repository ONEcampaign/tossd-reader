"""Runtime loader for tossd_reader's packaged OECD codelist snapshot (D6/D7).

Reads only the packaged CSVs and `_version.json` under `_data/codelists/` --
no network access, and no import of `oda_reader` (that lives in the
maintainer-only `codelists` dependency group; `scripts/refresh_codelists.py`
is what produces the snapshot this module reads).

No name-resolution logic lives here: turning a user-supplied name or code
into a validated filter value is the query layer's job (slice 2.2). This
module only loads and reports what is packaged.
"""

from __future__ import annotations

import importlib.resources
import json
from datetime import datetime
from functools import lru_cache

import pandas as pd

from tossd_reader.discovery import known_years

_YEARS_KEY = "years"


@lru_cache
def _available_dimensions() -> tuple[str, ...]:
    """Return every packaged codelist dimension name, sorted alphabetically."""
    resource = importlib.resources.files("tossd_reader") / "_data" / "codelists"
    with importlib.resources.as_file(resource) as path:
        names = [child.stem for child in path.glob("*.csv")]
    return tuple(sorted(names))


@lru_cache
def load_codelist(dimension: str) -> pd.DataFrame:
    """Load one packaged codelist dimension's frame.

    Args:
        dimension: One of the packaged dimension names -- `provider`,
            `recipient`, `pillar`, `financing_arrangement`,
            `framework_of_collaboration`, `purpose`, `sector`, `channel`,
            `modality`, `finance_instrument`.

    Returns:
        A `pandas.DataFrame` with `code`, `name`, and `tossd_only` columns
        (plus `iso3` for `provider`/`recipient`), sorted by `code` as
        packaged.

    Raises:
        ValueError: `dimension` is not one of the packaged dimensions.
    """
    available = _available_dimensions()
    if dimension not in available:
        raise ValueError(
            f"Unknown codelist dimension {dimension!r}; available: "
            f"{', '.join(available)}."
        )
    resource = (
        importlib.resources.files("tossd_reader")
        / "_data"
        / "codelists"
        / f"{dimension}.csv"
    )
    with importlib.resources.as_file(resource) as path:
        return pd.read_csv(path, dtype={"code": str})


def get_available_filters() -> dict[str, pd.DataFrame]:
    """Return every `get_tossd` filter dimension a user can browse.

    Covers every packaged codelist dimension (name/code/tossd-only-flag
    frames for provider, recipient, pillar, financing_arrangement,
    framework_of_collaboration, purpose, sector, channel, modality, and
    finance_instrument) plus `years`, the packaged known-years set.

    Returns:
        `{dimension: frame}`, one entry per packaged codelist dimension plus
        a `"years"` entry (a single-column `year` frame built from
        `discovery.known_years()`).
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
    resource = (
        importlib.resources.files("tossd_reader")
        / "_data"
        / "codelists"
        / "_version.json"
    )
    with importlib.resources.as_file(resource) as path:
        payload = json.loads(path.read_text())
    return datetime.fromisoformat(payload["fetched_at"]).date().isoformat()
