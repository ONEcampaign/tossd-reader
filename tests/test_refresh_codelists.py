"""Unit tests for `scripts/refresh_codelists.py`'s pure, offline `--check` diff mode.

No network access and no `oda-reader` import happen anywhere in this file --
only the maintainer script's directory-diff logic, exercised against
hand-built temp directories. This keeps the weekly drift CI job's core logic
testable in the default (offline) pytest suite.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "refresh_codelists.py"


def _write_snapshot(
    directory: Path, *, pillar_rows: str, fetched_at: str = "2026-01-01T00:00:00+00:00"
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "pillar.csv").write_text(f"code,name,tossd_only\n{pillar_rows}")
    (directory / "_version.json").write_text(
        json.dumps(
            {
                "fetched_at": fetched_at,
                "source_url": "https://development-finance-codelists.oecd.org/CodesList.aspx",
                "codelist_ids": {"pillar": "19"},
            }
        )
    )


def _run_check(baseline: Path, candidate: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--check", str(baseline), str(candidate)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_check_reports_no_drift_for_identical_snapshots(tmp_path: Path) -> None:
    """Two directories with identical CSV content (different `fetched_at`) report no drift."""
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    rows = "1,Pillar I,True\n2,Pillar II,True\n"
    _write_snapshot(baseline, pillar_rows=rows, fetched_at="2026-01-01T00:00:00+00:00")
    _write_snapshot(candidate, pillar_rows=rows, fetched_at="2026-02-01T00:00:00+00:00")

    result = _run_check(baseline, candidate)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "No codelist drift detected" in result.stdout


def test_check_detects_row_level_drift(tmp_path: Path) -> None:
    """A changed row in the candidate directory is reported as drift, exit code 1."""
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    _write_snapshot(baseline, pillar_rows="1,Pillar I,True\n2,Pillar II,True\n")
    _write_snapshot(candidate, pillar_rows="1,Pillar I,True\n2,Pillar Two,True\n")

    result = _run_check(baseline, candidate)

    assert result.returncode == 1
    assert "pillar.csv" in result.stdout


def test_check_detects_added_and_removed_dimension_files(tmp_path: Path) -> None:
    """A dimension file present only on one side is reported as added/removed."""
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    _write_snapshot(baseline, pillar_rows="1,Pillar I,True\n")
    _write_snapshot(candidate, pillar_rows="1,Pillar I,True\n")
    (candidate / "channel.csv").write_text("code,name,tossd_only\n10000,Public,False\n")

    result = _run_check(baseline, candidate)

    assert result.returncode == 1
    assert "channel.csv" in result.stdout


def test_check_detects_changed_codelist_ids_mapping(tmp_path: Path) -> None:
    """A changed `codelist_ids` mapping in `_version.json` is reported, ignoring `fetched_at`."""
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    rows = "1,Pillar I,True\n"
    _write_snapshot(baseline, pillar_rows=rows)
    _write_snapshot(candidate, pillar_rows=rows)
    payload = json.loads((candidate / "_version.json").read_text())
    payload["codelist_ids"]["pillar"] = "99"
    (candidate / "_version.json").write_text(json.dumps(payload))

    result = _run_check(baseline, candidate)

    assert result.returncode == 1
    assert "codelist_ids" in result.stdout
