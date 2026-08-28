"""Canary helper: compare a live HEAD sweep against the packaged `known_vintages.json`.

Used by `.github/workflows/canary.yml`'s weekly vintage-drift job. The
comparison itself (`diff_vintages`) is pure and offline-testable via this
module's `--check` mode; the default mode needs the network, via
`tossd_reader.discovery.discover` (imported lazily so this module stays
importable, and its diff logic testable, without ever opening a socket).

Run manually:
    uv run python scripts/check_vintage_drift.py
    uv run python scripts/check_vintage_drift.py --check <reference.json> <live.json>
"""

from __future__ import annotations

import argparse
import importlib.resources
import json
from pathlib import Path
from typing import TypedDict


class _VintageRecord(TypedDict):
    etag: str | None
    size_bytes: int | None


def load_reference() -> dict[int, _VintageRecord]:
    """Load the packaged `_data/known_vintages.json` reference snapshot."""
    resource = (
        importlib.resources.files("tossd_reader") / "_data" / "known_vintages.json"
    )
    with importlib.resources.as_file(resource) as path:
        return _load_records(Path(path))


def _load_records(path: Path) -> dict[int, _VintageRecord]:
    """Parse one `{year: {etag, size_bytes, ...}}`-shaped JSON file."""
    raw = json.loads(path.read_text())
    return {
        int(year): {"etag": record.get("etag"), "size_bytes": record.get("size_bytes")}
        for year, record in raw.items()
    }


def diff_vintages(
    reference: dict[int, _VintageRecord], live: dict[int, _VintageRecord]
) -> list[str]:
    """Compare `reference` (the packaged snapshot) against `live` (a fresh HEAD sweep).

    Args:
        reference: `{year: {"etag": ..., "size_bytes": ...}}`, as recorded in
            `known_vintages.json`.
        live: Same shape, freshly swept (e.g. from
            `tossd_reader.discovery.discover()`).

    Returns:
        Human-readable descriptions of every difference found: a year
        recorded but no longer published, a newly published year not yet
        recorded, or a recorded year whose etag/size_bytes changed. Empty
        when `reference` and `live` agree.
    """
    reference_years = set(reference)
    live_years = set(live)

    diffs = [
        f"{year}: recorded in known_vintages.json but no longer published "
        "(HEAD 404, or the publisher host was unreachable)"
        for year in sorted(reference_years - live_years)
    ]
    diffs.extend(
        f"{year}: newly published, not yet recorded in known_vintages.json"
        for year in sorted(live_years - reference_years)
    )

    for year in sorted(reference_years & live_years):
        recorded = reference[year]
        current = live[year]
        if recorded["etag"] != current["etag"]:
            diffs.append(
                f"{year}: etag changed ({recorded['etag']!r} -> {current['etag']!r})"
            )
        if recorded["size_bytes"] != current["size_bytes"]:
            diffs.append(
                f"{year}: size_bytes changed ({recorded['size_bytes']!r} -> "
                f"{current['size_bytes']!r})"
            )
    return diffs


def _run_live_sweep() -> dict[int, _VintageRecord]:
    """Sweep every currently published vintage, live (needs the network)."""
    from tossd_reader import discovery  # noqa: PLC0415 -- deliberately lazy, see above

    vintages = discovery.discover(refresh=True)
    return {
        year: {"etag": info.etag, "size_bytes": info.size_bytes}
        for year, info in vintages.items()
    }


def _report(diffs: list[str]) -> int:
    """Print `diffs` and return the process exit code."""
    if not diffs:
        print("No vintage drift detected.")
        return 0
    print("Vintage drift detected:")
    for diff in diffs:
        print(f"- {diff}")
    return 1


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Two modes:
    - Default: sweep live and compare against the packaged
      `known_vintages.json`.
    - `--check <reference.json> <live.json>`: pure offline diff between two
      already-written `{year: {etag, size_bytes}}` JSON files; no network.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        nargs=2,
        metavar=("REFERENCE_JSON", "LIVE_JSON"),
        help="Pure offline diff between two vintage-record JSON files; exits 1 on drift.",
    )
    args = parser.parse_args(argv)

    if args.check is not None:
        reference_path, live_path = (Path(value) for value in args.check)
        return _report(
            diff_vintages(_load_records(reference_path), _load_records(live_path))
        )

    return _report(diff_vintages(load_reference(), _run_live_sweep()))


if __name__ == "__main__":
    raise SystemExit(main())
