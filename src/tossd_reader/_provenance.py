"""Read/write of `<payload>.provenance.json` sidecars beside cached vintages.

Private module. Consumed by fetch.py and _export.py. Not a leaf: it imports
pyarrow.parquet (for the sidecar's row-count field) and
`tossd_reader.__version__`.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import warnings
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq

from tossd_reader import __version__


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
    provenance_path = path.with_suffix(".provenance.json")
    if provenance_path.exists():
        return
    parquet_file = pq.ParquetFile(path)
    record = {
        "url": url,
        "etag": captured.get("etag") or etag_fallback,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
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
    provenance_path = path.with_suffix(".provenance.json")
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


def _sha256_file(path: Path) -> str:
    """Hash `path`'s full contents."""
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()
