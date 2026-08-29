"""Shared packaged-`_data/` path resolution.

Every module that reads a file under `_data/` -- `schema.csv` (`_schema.py`,
`_export.py`), the codelist CSVs and `_version.json` (`codelists.py`),
`known_years.json` (`_discovery.py`), and `keyword_markers.csv`/
`structural_breaks.csv` (`analysis.py`) -- resolves it through
`importlib.resources` the same way. Centralised here so that resolution
detail lives in exactly one place.
"""

from __future__ import annotations

import importlib.resources
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def data_path(*parts: str) -> Iterator[Path]:
    """Yield a real filesystem path to the packaged `_data/<...parts>` resource.

    Args:
        parts: Path segments under `_data/`, e.g. `("schema.csv",)` or
            `("codelists", "provider.csv")`.
    """
    resource = importlib.resources.files("tossd_reader").joinpath("_data", *parts)
    with importlib.resources.as_file(resource) as path:
        yield path
