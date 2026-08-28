"""Arrow-level parquet export of the full `get_tossd` pipeline output.

`export()` reuses `query._build_table` — the same per-year fetch/schema/
concat/derived-columns/units pipeline `get_tossd` runs — but stops one call
short of `to_pandas()`, so the written parquet is exactly what `get_tossd`
would return, without a pandas round-trip. Always `columns="all"`, units left
as published (`"usd_thousand"`): the point of `export()` is a normalised,
typed, but otherwise unfiltered snapshot, not a query result.

Module named `_export.py` (leading underscore), not `export.py`: the public
function is also named `export`, and `from tossd_reader import export`
(exactly how a caller reaches the public function) would otherwise resolve
to *this submodule* instead of the function the first time anything imports
it by that dotted path — Python's import system caches a submodule onto its
parent package by attribute assignment, which permanently shadows
`tossd_reader.__getattr__`'s lazy resolution for that name. `tossd_reader/
__init__.py` re-exports `export` from here instead.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq

from tossd_reader import __version__, _resources, fetch, query

_OP_NAME = "tossd_reader:export"
_COMPRESSION = "zstd"


def export(
    path: str | Path, *, years: int | list[int] | None = None, refresh: bool = False
) -> Path:
    """Write the normalised, typed `get_tossd` pipeline output to parquet.

    Args:
        path: A directory (created if missing), in which case the parquet
            file is written as `tossd_<years-range>.parquet` inside it; or
            an explicit path ending in `.parquet` (its parent directories
            are created if missing).
        years: Same semantics as `get_tossd`'s `years=`: a single year, an
            iterable of years, or `None` (the default) for the packaged
            known-years set.
        refresh: Same semantics as `get_tossd`'s `refresh=`.

    Returns:
        The path the parquet file was written to. A sidecar
        `<stem>.manifest.json` is written alongside it, carrying the
        package version, a schema hash, the exported years, per-year
        vintage provenance (etag/retrieved_at), the total row count, and
        the export's creation timestamp.

    Note:
        `years=None` (the default) materialises the full packaged
        known-years set as one arrow table, all in memory, before it's
        ever written to disk (`columns="all"`, per this function's own
        contract) -- measured at roughly 2.1GB+ resident for the full set.
        Pass an explicit `years=` to export a smaller slice if that's a
        concern.

    Raises:
        ValueError: `years` resolves to an empty set of years.
        UnknownCodeError, InvalidPillarError, TossdNetworkError,
            SchemaDriftError: Same conditions as `get_tossd` (export applies
            no provider/recipient/pillar filters, so only the fetch/schema
            layer's own failure modes apply in practice).
    """
    table, paths = query._build_table(
        years=years,
        providers=None,
        recipients=None,
        pillars=None,
        columns="all",
        units="usd_thousand",
        refresh=refresh,
        op_name=_OP_NAME,
    )
    resolved_years = tuple(paths)

    destination = _resolve_destination(Path(path), resolved_years)
    pq.write_table(table, destination, compression=_COMPRESSION)
    _write_manifest(
        destination, row_count=table.num_rows, years=resolved_years, paths=paths
    )
    return destination


def _resolve_destination(path: Path, years: tuple[int, ...]) -> Path:
    """Resolve `path` to a concrete `.parquet` file path, creating parent dirs."""
    if path.suffix == ".parquet":
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    path.mkdir(parents=True, exist_ok=True)
    return path / f"tossd_{_years_range_stem(years)}.parquet"


def _years_range_stem(years: tuple[int, ...]) -> str:
    """Format `years` (already sorted) as a filename-safe stem.

    A single year is just that year; a contiguous run is `<first>-<last>`;
    a non-contiguous set is every year joined by `_`.
    """
    if len(years) == 1:
        return str(years[0])
    if years == tuple(range(years[0], years[-1] + 1)):
        return f"{years[0]}-{years[-1]}"
    return "_".join(str(year) for year in years)


def _write_manifest(
    destination: Path,
    *,
    row_count: int,
    years: tuple[int, ...],
    paths: dict[int, Path],
) -> None:
    """Write `<destination stem>.manifest.json` beside `destination`."""
    manifest = {
        "tossd_reader_version": __version__,
        "schema_hash": _schema_hash(),
        "years": list(years),
        "row_count": row_count,
        "created_at": datetime.now(UTC).isoformat(),
        "vintages": {str(year): _vintage_provenance(paths[year]) for year in years},
    }
    manifest_path = destination.parent / f"{destination.stem}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def _vintage_provenance(path: Path) -> dict[str, str | None]:
    """Return `{"etag": ..., "retrieved_at": ...}` from `path`'s provenance sidecar.

    Both fields are `None` when the sidecar is missing (should not happen in
    practice: `fetch._write_provenance_if_absent` writes one for every
    downloaded vintage), rather than raising.
    """
    provenance = fetch._read_provenance(path) or {}
    etag = provenance.get("etag")
    retrieved_at = provenance.get("retrieved_at")
    return {
        "etag": etag if isinstance(etag, str) else None,
        "retrieved_at": retrieved_at if isinstance(retrieved_at, str) else None,
    }


def _schema_hash() -> str:
    """Sha256 of the packaged `_data/schema.csv`, CRLF-normalised for OS-stability."""
    with _resources.data_path("schema.csv") as schema_path:
        data = schema_path.read_bytes()
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()
