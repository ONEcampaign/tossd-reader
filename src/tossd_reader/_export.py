"""Arrow-level parquet export of the full `get_tossd` pipeline output.

`export()` reuses `query.build_table` — the same per-year fetch/schema/
concat/derived-columns/units pipeline `get_tossd` runs — but stops one call
short of `to_pandas()`, so the written parquet is exactly what `get_tossd`
would return, without a pandas round-trip. Always `columns="all"`, units left
as published (`"usd_thousand"`): the point of `export()` is a normalised,
typed, but otherwise unfiltered snapshot, not a query result.

`verify_export()` and `load_export()` are this module's read side: the
manifest sidecar `export()` writes carries a `payload_sha256` of the written
parquet bytes plus the row count, both checked against the file on disk;
`load_export()` verifies by default, then reads the parquet straight back
(no `_schema.apply_schema` re-application -- the file already carries
snake_case names and final arrow types) and attaches the manifest's
provenance to `df.attrs["tossd_reader"]`.

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
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from tossd_reader import __version__, _provenance, _resources, query
from tossd_reader.exceptions import ExportIntegrityError

_OP_NAME = "tossd_reader:export"
_COMPRESSION = "zstd"


def export(
    path: str | Path,
    *,
    years: int | Iterable[int] | None = None,
    refresh: bool = False,
    max_rows: int | None = None,
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
        max_rows: Opt-in guard: once the table is built, raise `ValueError`
            (naming the actual row count and this limit) before writing
            anything, if it exceeds `max_rows`. `None` (the default)
            applies no limit -- the historical behaviour, unchanged.

    Returns:
        The path the parquet file was written to. A sidecar
        `<stem>.manifest.json` is written alongside it, carrying the
        package version, a schema hash, a sha256 of the written parquet's
        own bytes (`payload_sha256`, checked by `verify_export`), the
        exported years, per-year vintage provenance (etag/retrieved_at),
        the total row count, and the export's creation timestamp.

    Note:
        `years=None` (the default) materialises the full packaged
        known-years set as one arrow table, all in memory, before it's
        ever written to disk (`columns="all"`, per this function's own
        contract) -- measured at roughly 4.4GB peak resident for the full
        set (the finished table alone is ~2.1GB; per-year tables are
        transiently alive alongside it).
        Pass an explicit `years=` (or `max_rows=` to fail fast instead) to
        export a smaller slice if that's a concern.

    Raises:
        ValueError: `years` resolves to an empty set of years; `max_rows`
            is given and the built table exceeds it; or `refresh=True`
            while offline mode is active (`config.get_offline()` is
            `True`).
        TossdNetworkError: Same conditions as `get_tossd`; export applies
            no provider/recipient/pillar/`filters=` filters, so only the
            fetch/schema layer's own failure modes apply in practice.
        SchemaDriftError: Same conditions as `get_tossd`.

    Example:
        >>> import tossd_reader
        >>> path = tossd_reader.export(  # doctest: +SKIP
        ...     "tossd_2024.parquet", years=2024
        ... )
        >>> df = tossd_reader.load_export(path)  # doctest: +SKIP
    """
    table, paths = query.build_table(
        years=years,
        providers=None,
        recipients=None,
        pillars=None,
        filters=None,
        columns="all",
        units="usd_thousand",
        refresh=refresh,
        op_name=_OP_NAME,
    )
    if max_rows is not None and table.num_rows > max_rows:
        raise ValueError(
            f"export() would write {table.num_rows} rows, exceeding "
            f"max_rows={max_rows}. Pass a larger max_rows=, or narrow years= to "
            "export a smaller slice."
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
        "payload_sha256": _provenance.sha256_file(destination),
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
    practice: `_provenance.write_provenance_if_absent` writes one for every
    downloaded vintage), rather than raising.
    """
    provenance = _provenance.read_provenance(path) or {}
    etag = provenance.get("etag")
    retrieved_at = provenance.get("retrieved_at")
    return {
        "etag": etag if isinstance(etag, str) else None,
        "retrieved_at": retrieved_at if isinstance(retrieved_at, str) else None,
    }


def _schema_hash() -> str:
    """Sha256 of the packaged `_data/schema.csv`, CRLF-normalised for OS-stability.

    Every byte of that file counts, including columns no code reads. The
    documentation quotes this hash literally, so `tests/test_infra.py` pins
    it: an edit to schema.csv cannot change it silently.
    """
    with _resources.data_path("schema.csv") as schema_path:
        data = schema_path.read_bytes()
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


# --- verify / load a previously written export ---------------------------------


def verify_export(path: str | Path) -> None:
    """Verify a parquet file previously written by `export()` against its manifest sidecar.

    Two checks, both against `<stem>.manifest.json` beside `path`: the
    payload's sha256 hash (`payload_sha256`) and its row count (`row_count`).
    A `schema_hash` mismatch is deliberately not checked here -- an export
    written by an older or newer package version is not a corrupted file.

    Args:
        path: Path to a `.parquet` file previously written by `export()`.

    Returns:
        `None`. Only ever returns after every check passes.

    Raises:
        ExportIntegrityError: The manifest sidecar is missing or cannot be
            parsed as a JSON object; the payload's sha256 hash doesn't match
            the manifest's `payload_sha256`; or the payload's row count
            doesn't match the manifest's `row_count`.
    """
    payload_path = Path(path)
    manifest = _read_manifest(_manifest_path(payload_path))
    _verify_payload_hash(payload_path, manifest)
    _verify_row_count(payload_path, manifest)


def load_export(path: str | Path, *, verify: bool = True) -> pd.DataFrame:
    """Load a parquet file previously written by `export()`, with its provenance attached.

    Reads the file directly (`pq.read_table` + `to_pandas`, reusing
    `query`'s own `types_mapper`) rather than through `get_tossd`'s pipeline:
    an exported parquet already carries snake_case column names and final
    arrow types (`export()` wrote it that way), so re-running
    `_schema.apply_schema` would be redundant at best and wrong if the
    installed package's schema has since drifted from the one that produced
    the file.

    Args:
        path: Path to a `.parquet` file previously written by `export()`.
        verify: Run `verify_export(path)` first (the default). Pass `False`
            to skip the payload-hash/row-count checks -- `df.attrs`
            provenance is still read from the manifest either way, so a
            missing or unparseable manifest still raises regardless of this
            flag.

    Returns:
        A `pandas.DataFrame` read straight from the parquet file, with
        `df.attrs["tossd_reader"]` set to `{"package_version", "created_at",
        "years"}`: the manifest's `tossd_reader_version`, `created_at`, and
        `vintages` fields respectively.

    Raises:
        ExportIntegrityError: `verify=True` (the default) and the payload
            fails `verify_export`'s checks; or, regardless of `verify=`, the
            manifest sidecar is missing or cannot be parsed as a JSON
            object.

    Example:
        >>> import tossd_reader
        >>> df = tossd_reader.load_export("tossd_2024.parquet")  # doctest: +SKIP
    """
    payload_path = Path(path)
    if verify:
        verify_export(payload_path)
    manifest = _read_manifest(_manifest_path(payload_path))

    table = pq.read_table(payload_path)
    df = table.to_pandas(types_mapper=query.ARROW_TO_PANDAS_INT.get)
    df.attrs["tossd_reader"] = {
        "package_version": manifest.get("tossd_reader_version"),
        "created_at": manifest.get("created_at"),
        "years": manifest.get("vintages"),
    }
    return df


def _manifest_path(payload_path: Path) -> Path:
    """The `<stem>.manifest.json` sidecar path `export()` writes beside `payload_path`."""
    return payload_path.parent / f"{payload_path.stem}.manifest.json"


def _read_manifest(manifest_path: Path) -> dict[str, object]:
    """Read and parse `manifest_path`, raising `ExportIntegrityError` on any failure."""
    try:
        text = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ExportIntegrityError(
            f"Cannot read manifest {manifest_path}: {exc}."
        ) from exc
    try:
        manifest = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExportIntegrityError(
            f"Manifest {manifest_path} is not valid JSON: {exc}."
        ) from exc
    if not isinstance(manifest, dict):
        raise ExportIntegrityError(f"Manifest {manifest_path} is not a JSON object.")
    return manifest


def _verify_payload_hash(payload_path: Path, manifest: dict[str, object]) -> None:
    """Raise `ExportIntegrityError` unless `payload_path`'s sha256 matches the manifest's."""
    expected = manifest.get("payload_sha256")
    if not isinstance(expected, str):
        raise ExportIntegrityError(
            f"Manifest for {payload_path} has no payload_sha256 to verify against "
            "(written by an older tossd_reader version?)."
        )
    actual = _provenance.sha256_file(payload_path)
    if actual != expected:
        raise ExportIntegrityError(
            f"{payload_path} does not match its manifest: sha256 {actual} but the "
            f"manifest recorded {expected}. The file may have been modified or "
            "corrupted since export."
        )


def _verify_row_count(payload_path: Path, manifest: dict[str, object]) -> None:
    """Raise `ExportIntegrityError` unless `payload_path`'s row count matches the manifest's."""
    expected = manifest.get("row_count")
    if not isinstance(expected, int):
        raise ExportIntegrityError(
            f"Manifest for {payload_path} has no row_count to verify against."
        )
    actual = pq.read_metadata(payload_path).num_rows
    if actual != expected:
        raise ExportIntegrityError(
            f"{payload_path} has {actual} row(s); the manifest recorded {expected}."
        )
