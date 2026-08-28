"""Canary helper: compare a live HEAD sweep against the packaged `known_vintages.json`.

Used by `.github/workflows/canary.yml`'s weekly vintage-drift job. The
comparison itself (`diff_vintages`) is pure and offline-testable via this
module's `--check` mode; the default mode needs the network, via
`tossd_reader.discovery.discover` (imported lazily so this module stays
importable, and its diff logic testable, without ever opening a socket).

Run manually:
    uv run python scripts/check_vintage_drift.py
    uv run python scripts/check_vintage_drift.py --check <reference.json> <live.json>
    uv run python scripts/check_vintage_drift.py --record <output.json>
"""

from __future__ import annotations

import argparse
import importlib.resources
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

from tossd_reader.exceptions import TossdNetworkError


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


def _write_records(path: Path, records: dict[int, _VintageRecord]) -> None:
    """Write `records` to `path`, matching `known_vintages.json`'s own shape.

    Every entry gets the same `recorded_at` stamp (this sweep's time), same
    convention as the packaged `known_vintages.json`.
    """
    recorded_at = datetime.now(UTC).isoformat()
    payload = {
        str(year): {**record, "recorded_at": recorded_at}
        for year, record in sorted(records.items())
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


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

    Three modes:
    - Default: sweep live and compare against the packaged
      `known_vintages.json`.
    - `--check <reference.json> <live.json>`: pure offline diff between two
      already-written `{year: {etag, size_bytes}}` JSON files; no network.
    - `--record <output.json>`: sweep live and write a fresh
      `known_vintages.json`-shaped snapshot to `output.json` -- the refresh
      an operator runs after a drift alert, per the canary issue body.

    A live sweep that can't reach the publisher at all (`TossdNetworkError`)
    prints a clear "sweep failed" diagnostic to stdout (the canary job
    captures stdout as the issue body) before returning a non-zero exit
    code, rather than letting an uncaught traceback (stderr, not captured)
    leave the issue body empty.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        nargs=2,
        metavar=("REFERENCE_JSON", "LIVE_JSON"),
        help="Pure offline diff between two vintage-record JSON files; exits 1 on drift.",
    )
    parser.add_argument(
        "--record",
        metavar="OUTPUT_JSON",
        help="Sweep live and write a fresh known_vintages.json-shaped snapshot to OUTPUT_JSON.",
    )
    args = parser.parse_args(argv)

    if args.check is not None:
        reference_path, live_path = (Path(value) for value in args.check)
        return _report(
            diff_vintages(_load_records(reference_path), _load_records(live_path))
        )

    try:
        live = _run_live_sweep()
    except TossdNetworkError as exc:
        print(f"Vintage sweep failed: {exc}")
        return 1

    if args.record is not None:
        output_path = Path(args.record)
        _write_records(output_path, live)
        print(f"Wrote {len(live)} vintage record(s) to {output_path}.")
        return 0

    return _report(diff_vintages(load_reference(), live))


if __name__ == "__main__":
    raise SystemExit(main())
