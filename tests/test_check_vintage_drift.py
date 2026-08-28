"""Unit tests for `scripts/check_vintage_drift.py`'s pure, offline `--check` diff mode.

No network access anywhere in this file — only the canary job's core diff
logic, exercised against hand-written temp JSON files, same convention as
`tests/test_refresh_codelists.py`.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_vintage_drift.py"


def _import_script():
    """Import `check_vintage_drift.py` by path (`scripts/` is not a package)."""
    spec = importlib.util.spec_from_file_location("check_vintage_drift", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_records(path: Path, records: dict[int, dict[str, object]]) -> None:
    path.write_text(json.dumps({str(year): record for year, record in records.items()}))


def _run_check(reference: Path, live: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--check", str(reference), str(live)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_check_reports_no_drift_for_identical_snapshots(tmp_path: Path) -> None:
    records = {2019: {"etag": '"e19"', "size_bytes": 100}}
    reference = tmp_path / "reference.json"
    live = tmp_path / "live.json"
    _write_records(reference, records)
    _write_records(live, records)

    result = _run_check(reference, live)

    assert result.returncode == 0
    assert "No vintage drift detected." in result.stdout


def test_check_detects_etag_and_size_changes(tmp_path: Path) -> None:
    reference = tmp_path / "reference.json"
    live = tmp_path / "live.json"
    _write_records(reference, {2019: {"etag": '"old"', "size_bytes": 100}})
    _write_records(live, {2019: {"etag": '"new"', "size_bytes": 200}})

    result = _run_check(reference, live)

    assert result.returncode == 1
    assert "etag changed" in result.stdout
    assert "size_bytes changed" in result.stdout


def test_check_detects_missing_year(tmp_path: Path) -> None:
    """A recorded year absent from the live sweep is flagged as no-longer-published."""
    reference = tmp_path / "reference.json"
    live = tmp_path / "live.json"
    _write_records(reference, {2019: {"etag": '"e19"', "size_bytes": 100}})
    _write_records(live, {})

    result = _run_check(reference, live)

    assert result.returncode == 1
    assert "no longer published" in result.stdout


def test_check_detects_new_year(tmp_path: Path) -> None:
    """A live year absent from the reference is flagged as newly published."""
    reference = tmp_path / "reference.json"
    live = tmp_path / "live.json"
    _write_records(reference, {})
    _write_records(live, {2025: {"etag": '"e25"', "size_bytes": 100}})

    result = _run_check(reference, live)

    assert result.returncode == 1
    assert "newly published" in result.stdout


def test_load_reference_reads_the_packaged_known_vintages_json() -> None:
    """The packaged `known_vintages.json` loads as `{year: {etag, size_bytes}}`."""
    module = _import_script()

    reference = module.load_reference()

    assert set(reference) == {2019, 2020, 2021, 2022, 2023, 2024}
    for record in reference.values():
        assert record["etag"]
        assert record["size_bytes"] and record["size_bytes"] > 0
