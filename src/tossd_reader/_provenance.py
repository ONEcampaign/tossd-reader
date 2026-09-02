"""Read/write of `<payload>.provenance.json` sidecars beside cached vintages.

Private module. Consumed by fetch.py, query.py, and _export.py. Not a leaf: it imports
pyarrow.parquet (for the sidecar's row-count field) and
`tossd_reader.__version__`.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import warnings
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import pyarrow.parquet as pq

from tossd_reader import __version__

ATTRS_KEY: Final = "tossd_reader"
"""The `df.attrs` key `get_tossd()`, `get_tossd_raw()`, and `load_export()` each set."""

SIDECAR_SUFFIX: Final = ".provenance.json"
"""The sidecar filename's fixed ending. Not underscore-prefixed: fetch.py's orphaned-provenance
sweep (`fetch._sweep_orphaned_provenance`) globs `*{SIDECAR_SUFFIX}` directly, alongside this
module's own use in `sidecar_path`/`payload_path_for_sidecar`."""

_PAYLOAD_SUFFIX: Final = ".parquet"
"""This package's one payload suffix -- every `ArtifactCache.ensure()` call in fetch.py passes
`suffix=".parquet"`. Kept private: only `payload_path_for_sidecar`, below, needs it."""


def sidecar_path(payload_path: Path) -> Path:
    """The `<payload path>.provenance.json` sidecar path for `payload_path`.

    Not underscore-prefixed: `config.py`'s `clear_cache()` reuses this to unlink a removed
    entry's sidecar alongside its payload, so cache clearing and provenance writing/reading never
    derive this path two different ways.
    """
    return payload_path.with_suffix(SIDECAR_SUFFIX)


def payload_path_for_sidecar(sidecar_file: Path) -> Path:
    """Reverse `sidecar_path`: the payload path named by a `<payload>.provenance.json` file.

    Name surgery, not `Path.with_suffix` -- `with_suffix` only ever replaces a path's *last*
    suffix component (the text after its final dot), so
    `Path("x.provenance.json").with_suffix(".parquet")` yields `"x.provenance.parquet"`, not
    `"x.parquet"`. Not underscore-prefixed: fetch.py's orphaned-provenance sweep reuses this, so
    the sidecar-name shape is derived in exactly one place, never independently reimplemented.

    Args:
        sidecar_file: A path whose name ends with `SIDECAR_SUFFIX` -- true for every sidecar this
            package writes.

    Returns:
        The payload path `sidecar_file` describes, with this package's one payload suffix.
    """
    stem = sidecar_file.name.removesuffix(SIDECAR_SUFFIX)
    return sidecar_file.with_name(f"{stem}{_PAYLOAD_SUFFIX}")


def write_provenance_if_absent(
    path: Path,
    *,
    url: str,
    captured: dict[str, str | None],
    etag_fallback: str | None,
) -> None:
    """Write `<path stem>.provenance.json` beside `path`, unless one already exists.

    Args:
        path: The cached parquet payload.
        url: The vintage's download URL.
        captured: The fetcher's captured `etag`, keyed under `"etag"`.
            `captured["etag"]` is `None` on a cache hit, since the fetcher
            never ran.
        etag_fallback: The cache key's own ETag (the retry loop's winning
            `etag`), used when `captured["etag"]` is `None` — a cache hit
            whose sidecar was lost still records the right ETag rather than
            `null`.
    """
    provenance_path = sidecar_path(path)
    if provenance_path.exists():
        return
    parquet_file = pq.ParquetFile(path)
    record = {
        "url": url,
        "etag": captured.get("etag") or etag_fallback,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "row_count": parquet_file.metadata.num_rows,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "tossd_reader_version": __version__,
    }
    # Written via a temp file + atomic rename, so a reader always sees a
    # complete sidecar. The suffix carries the pid plus random hex, so
    # concurrent writers each get a distinct temp file.
    tmp = provenance_path.with_name(
        f"{provenance_path.name}.tmp-{os.getpid()}-{secrets.token_hex(3)}"
    )
    tmp.write_text(json.dumps(record, indent=2), encoding="utf-8")
    tmp.replace(provenance_path)


def read_provenance(path: Path) -> dict[str, object] | None:
    """Read `<path stem>.provenance.json`, or `None` when missing or corrupt.

    A sidecar corrupted on disk (most plausibly a leftover from a non-atomic
    write — this module's own write is atomic, see
    `write_provenance_if_absent`) must not take down its consumers — the
    offline fallback's stale-serve warning and the export manifest — so a
    present-but-unparseable sidecar warns and degrades to `None`. Filesystem
    faults other than the file vanishing mid-read (permissions, I/O errors)
    still propagate: those are environment problems, not corruption.
    """
    provenance_path = sidecar_path(path)
    if not provenance_path.is_file():
        return None
    try:
        record = json.loads(provenance_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None  # vanished since the is_file() check: same as missing
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _warn_corrupt_provenance(provenance_path, reason=str(exc))
        return None
    if isinstance(record, dict):
        return record
    _warn_corrupt_provenance(provenance_path, reason="not a JSON object")
    return None


def _warn_corrupt_provenance(provenance_path: Path, *, reason: str) -> None:
    """Warn that a present-but-unparseable sidecar is being ignored.

    The warning is loud because the sidecar feeds the export manifest's audit
    fields (`etag`/`retrieved_at`): a silent drop would leave a corrupt
    sidecar indistinguishable in the manifest from an entry that never had
    provenance at all.
    """
    warnings.warn(
        f"Ignoring corrupt provenance sidecar {provenance_path} ({reason}); "
        "the cached payload itself is unaffected.",
        # 3 frames up: _warn_corrupt_provenance -> read_provenance -> its
        # caller (fetch._latest_cached, or _export._vintage_provenance).
        stacklevel=3,
    )


def build_attrs(
    *, query: dict[str, object], paths: Mapping[int, Path]
) -> dict[str, object]:
    """Build the `df.attrs["tossd_reader"]` payload `get_tossd()`/`get_tossd_raw()` attach.

    Args:
        query: The caller's normalised call -- already JSON-serializable (see each caller's own
            docstring for its exact shape).
        paths: Each resolved year's own cache path, read here for that vintage's own
            `.provenance.json` sidecar.

    Returns:
        `{"package_version", "created_at", "query", "years"}` -- `"created_at"` an ISO 8601 UTC
        timestamp of this call, not the vintage's own retrieval time; `"years"` maps each
        resolved year (as `str`, since JSON object keys are always strings) to
        `{"etag", "retrieved_at", "url"}` read from that year's sidecar, every field `None` when
        the sidecar is missing or corrupt (`read_provenance` already warns on corruption -- this
        function raises no warning of its own).
    """
    return {
        "package_version": __version__,
        "created_at": datetime.now(UTC).isoformat(),
        "query": query,
        "years": {str(year): _vintage_fields(path) for year, path in paths.items()},
    }


def _vintage_fields(path: Path) -> dict[str, str | None]:
    """One year's `{"etag", "retrieved_at", "url"}`, read from its provenance sidecar."""
    provenance = read_provenance(path) or {}
    return {
        "etag": _as_str(provenance.get("etag")),
        "retrieved_at": _as_str(provenance.get("retrieved_at")),
        "url": _as_str(provenance.get("url")),
    }


def _as_str(value: object) -> str | None:
    """Narrow a provenance-JSON field to `str`, or `None` if it isn't one.

    Duplicated from `fetch.py`'s own `_as_str` (both are 2-line helpers reading the same
    provenance dict shape) rather than shared: `_provenance.py` cannot import `fetch.py` (the
    dependency runs the other way), and a shared import isn't worth threading for this.
    """
    return value if isinstance(value, str) else None


def sha256_file(path: Path) -> str:
    """Hash `path`'s full contents.

    Not underscore-prefixed: `_export.py` (a sibling private module) reuses
    it to hash the written parquet payload for the export manifest's
    `payload_sha256` field, alongside this module's own use for the cached
    vintage's provenance sidecar.
    """
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()
