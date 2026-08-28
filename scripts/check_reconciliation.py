"""Canary helper: full-download A1 headline-total reconciliation + packed-delimiter check.

Used by `.github/workflows/canary.yml`'s monthly reconciliation job. The
check itself (`check_reconciliation`) is pure and offline-testable against a
synthetic arrow table; the live entry point needs the network (a full
per-year parquet download), via `tossd_reader.fetch.fetch_year` (imported
lazily so this module stays importable, and its check logic testable,
without ever opening a socket) -- same split as `check_vintage_drift.py`.

Run manually:
    uv run python scripts/check_reconciliation.py
"""

from __future__ import annotations

from typing import Final

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from tossd_reader.exceptions import TossdNetworkError

# Latest year notes/build/audits/a1-reconciliation.md has recorded headline
# totals for; bump alongside a fresh A1 audit re-run.
YEAR: Final = 2024
EXPECTED_TOTALS_USD_K: Final[dict[str, float]] = {
    "p1_disb": 364_114_132.08,
    "p2_disb": 133_561_849.36,
    "mob": 79_646_259.46,
}
TOLERANCE_USD_K: Final = 1.0
# Guards the documented single-valued claim for these columns.
PACKED_COLUMNS: Final[tuple[str, ...]] = ("sector", "sector3", "purposecode")


def check_reconciliation(
    table: pa.Table,
    *,
    year: int,
    expected_totals_usd_k: dict[str, float],
    tolerance_usd_k: float,
    packed_columns: tuple[str, ...],
) -> list[str]:
    """Compare `table`'s headline totals and packed-delimiter columns against expectations.

    Args:
        table: One year's raw, publisher-bytes-verbatim table (as read
            straight off `fetch_year`'s cached parquet -- publisher column
            names, unrenamed, as `TossdPillar`/`USD_disbursements`/etc.).
        year: The reporting year `table` covers (only used in messages).
        expected_totals_usd_k: `{"p1_disb": ..., "p2_disb": ..., "mob": ...}`
            recorded headline totals (pillar-1 disbursements, pillar-2
            disbursements, amount mobilised), in USD thousands, including
            `is_aggregate` (pseudo-aggregate provider) rows -- no filtering.
        tolerance_usd_k: Absolute tolerance, in USD thousands.
        packed_columns: Column names expected to carry no `;`/`|`
            delimiter-packed value (guards the documented single-valued
            claim for these columns).

    Returns:
        Human-readable failure descriptions, one per failing check; empty
        when every headline total and packed-delimiter check passes.
    """
    failures: list[str] = []

    pillar = table["TossdPillar"]
    pillar_1 = table.filter(pc.equal(pillar, "1"))
    pillar_2 = table.filter(pc.equal(pillar, "2"))
    actual = {
        "p1_disb": pc.sum(pillar_1["USD_disbursements"]).as_py(),
        "p2_disb": pc.sum(pillar_2["USD_disbursements"]).as_py(),
        "mob": pc.sum(table["USD_amountmobilised"]).as_py(),
    }

    for key, expected in expected_totals_usd_k.items():
        value = actual.get(key)
        if value is None or abs(value - expected) > tolerance_usd_k:
            failures.append(
                f"{year} {key}: {value} vs expected {expected} (tol {tolerance_usd_k})"
            )

    for column_name in packed_columns:
        values = table.column(column_name)
        has_delimiter = pc.or_(
            pc.match_substring(values, ";"), pc.match_substring(values, "|")
        )
        if pc.any(pc.fill_null(has_delimiter, False)).as_py():
            failures.append(
                f"{column_name}: contains a packed ';' or '|' delimiter value"
            )

    return failures


def _report(failures: list[str], *, year: int) -> int:
    """Print `failures` and return the process exit code."""
    if not failures:
        print(f"{year} reconciliation and packed-delimiter checks passed.")
        return 0
    print(f"{year} reconciliation / packed-delimiter check FAILED:")
    for failure in failures:
        print(f"- {failure}")
    return 1


def _run_live_check() -> list[str]:
    """Full-download `YEAR` and run `check_reconciliation` against it, live."""
    from tossd_reader import fetch  # noqa: PLC0415 -- deliberately lazy, see above

    path = fetch.fetch_year(YEAR)
    table = pq.read_table(path)
    return check_reconciliation(
        table,
        year=YEAR,
        expected_totals_usd_k=EXPECTED_TOTALS_USD_K,
        tolerance_usd_k=TOLERANCE_USD_K,
        packed_columns=PACKED_COLUMNS,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: full-download `YEAR` and run the live reconciliation check.

    No arguments today (`argv` kept for symmetry with `check_vintage_drift.py`).

    An unreachable publisher (`TossdNetworkError`) prints a clear
    "Reconciliation check failed: <reason>" line to stdout (what the canary
    job captures as the issue body) before returning a non-zero exit code,
    rather than letting an uncaught traceback (stderr, not captured) leave
    the issue body empty -- same fix as `check_vintage_drift.py`'s live
    sweep wrapper.
    """
    del argv
    try:
        failures = _run_live_check()
    except TossdNetworkError as exc:
        print(f"Reconciliation check failed: {exc}")
        return 1
    return _report(failures, year=YEAR)


if __name__ == "__main__":
    raise SystemExit(main())
