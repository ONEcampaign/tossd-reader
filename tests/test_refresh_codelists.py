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

import pandas as pd

from tests.script_loading import REPO_ROOT, import_script

SCRIPT = REPO_ROOT / "scripts" / "refresh_codelists.py"


def _import_script():
    """Import `refresh_codelists.py` by path (`scripts/` is not a package)."""
    return import_script("refresh_codelists.py")


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


# --- transformation functions: _dedupe_by_code, _project_dimension_frame, -----
# --- _split_purpose_and_sector -------------------------------------------------


def test_dedupe_by_code_prefers_active_status_row() -> None:
    """Among duplicate `code` rows, the `status == "active"` row wins, regardless of order."""
    module = _import_script()
    frame = pd.DataFrame(
        {
            "code": ["1", "1", "2"],
            "label": ["Alpha", "Alpha", "Beta"],
            "status": ["inactive", "active", "active"],
            "activation_date": ["2010-01-01", "2015-01-01", "2020-01-01"],
        }
    )

    result = module._dedupe_by_code(frame)

    assert len(result) == 2
    assert result.set_index("code").loc["1", "status"] == "active"
    assert result.set_index("code").loc["1", "activation_date"] == "2015-01-01"


def test_dedupe_by_code_falls_back_to_latest_activation_date() -> None:
    """With no active row for a code, the most recent `activation_date` row wins."""
    module = _import_script()
    frame = pd.DataFrame(
        {
            "code": ["3", "3"],
            "label": ["Gamma", "Gamma"],
            "status": ["inactive", "inactive"],
            "activation_date": ["2010-01-01", "2020-01-01"],
        }
    )

    result = module._dedupe_by_code(frame)

    assert len(result) == 1
    assert result.iloc[0]["activation_date"] == "2020-01-01"


def test_project_dimension_frame_filters_tossd_and_derives_tossd_only() -> None:
    """Non-TOSSD rows are dropped; `tossd_only` is derived from `crs == "0"`."""
    module = _import_script()
    frame = pd.DataFrame(
        {
            "code": ["10", "20", "30"],
            "label": ["Ten", "Twenty", "Thirty"],
            "status": ["active", "active", "active"],
            "activation_date": ["2020-01-01"] * 3,
            "tossd": ["1", "0", "1"],
            "crs": ["1", "1", "0"],
            "iso3": ["AAA", "BBB", "CCC"],
        }
    )

    result = module._project_dimension_frame(frame)

    assert list(result["code"]) == ["10", "30"]  # code "20": tossd != "1", dropped
    assert list(result.columns) == ["code", "name", "tossd_only", "iso3"]
    by_code = result.set_index("code")
    assert bool(by_code.loc["10", "tossd_only"]) is False  # crs == "1"
    assert bool(by_code.loc["30", "tossd_only"]) is True  # crs == "0"


def test_project_dimension_frame_omits_iso3_when_source_frame_has_none() -> None:
    """A source frame with no `iso3` column projects without one, not a KeyError."""
    module = _import_script()
    frame = pd.DataFrame(
        {
            "code": ["10"],
            "label": ["Ten"],
            "status": ["active"],
            "activation_date": ["2020-01-01"],
            "crs": ["1"],
        }
    )

    result = module._project_dimension_frame(frame)

    assert list(result.columns) == ["code", "name", "tossd_only"]


def test_split_purpose_and_sector_by_code_length() -> None:
    """3-digit codes become `sector`; 5- and 7-digit codes stay in `purpose`."""
    module = _import_script()
    projected = pd.DataFrame(
        {
            "code": ["110", "11220", "1122001"],
            "name": ["Education", "Primary education", "Purpose detail"],
            "tossd_only": [False, False, True],
        }
    )

    result = module._split_purpose_and_sector(projected)

    assert list(result["sector"]["code"]) == ["110"]
    assert list(result["purpose"]["code"]) == ["11220", "1122001"]
