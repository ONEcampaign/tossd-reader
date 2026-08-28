"""Unit tests for `scripts/check_reconciliation.py`'s pure `check_reconciliation` check.

No network access anywhere in this file -- only the canary reconciliation
job's core check logic, exercised against a small synthetic arrow table, same
convention as `tests/test_check_vintage_drift.py`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pyarrow as pa

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_reconciliation.py"


def _import_script():
    """Import `check_reconciliation.py` by path (`scripts/` is not a package)."""
    spec = importlib.util.spec_from_file_location("check_reconciliation", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _synthetic_table(
    *,
    pillars: list[str],
    disbursements: list[float],
    mobilised: list[float],
    sector3: list[str] | None = None,
) -> pa.Table:
    """Build a minimal table carrying only the columns `check_reconciliation` reads."""
    n = len(pillars)
    return pa.table(
        {
            "TossdPillar": pa.array(pillars, type=pa.string()),
            "USD_disbursements": pa.array(disbursements, type=pa.float64()),
            "USD_amountmobilised": pa.array(mobilised, type=pa.float64()),
            "sector": pa.array(["Education"] * n, type=pa.string()),
            "sector3": pa.array(sector3 or ["110"] * n, type=pa.string()),
            "purposecode": pa.array(["11240"] * n, type=pa.string()),
        }
    )


def test_check_reconciliation_passes_when_totals_and_columns_match() -> None:
    """Known per-pillar sums reproduced exactly (within tolerance) -> no failures."""
    module = _import_script()
    table = _synthetic_table(
        pillars=["1", "1", "2", "2"],
        disbursements=[100.0, 200.0, 50.0, 25.0],
        mobilised=[10.0, 5.0, 0.0, 0.0],
    )

    failures = module.check_reconciliation(
        table,
        year=2024,
        expected_totals_usd_k={"p1_disb": 300.0, "p2_disb": 75.0, "mob": 15.0},
        tolerance_usd_k=0.01,
        packed_columns=("sector", "sector3", "purposecode"),
    )

    assert failures == []


def test_check_reconciliation_detects_headline_total_mismatch() -> None:
    """A pillar-1 disbursement total outside tolerance is reported, naming the key."""
    module = _import_script()
    table = _synthetic_table(
        pillars=["1", "2"],
        disbursements=[100.0, 50.0],
        mobilised=[10.0, 0.0],
    )

    failures = module.check_reconciliation(
        table,
        year=2024,
        expected_totals_usd_k={"p1_disb": 999.0, "p2_disb": 50.0, "mob": 10.0},
        tolerance_usd_k=0.01,
        packed_columns=(),
    )

    assert len(failures) == 1
    assert "p1_disb" in failures[0]


def test_check_reconciliation_detects_packed_delimiter_violation() -> None:
    """A `;`-packed value in a documented single-valued column is reported."""
    module = _import_script()
    table = _synthetic_table(
        pillars=["1", "2"],
        disbursements=[100.0, 50.0],
        mobilised=[10.0, 0.0],
        sector3=["110", "311;312"],
    )

    failures = module.check_reconciliation(
        table,
        year=2024,
        expected_totals_usd_k={"p1_disb": 100.0, "p2_disb": 50.0, "mob": 10.0},
        tolerance_usd_k=0.01,
        packed_columns=("sector", "sector3", "purposecode"),
    )

    assert any("sector3" in failure for failure in failures)
