"""Unit tests for `scripts/check_vintage_drift.py`'s pure, offline `--check` diff mode.

No network access anywhere in this file — only the canary job's core diff
logic, exercised against hand-written temp JSON files, same convention as
`tests/test_refresh_codelists.py`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.script_loading import REPO_ROOT, import_script
from tossd_reader.exceptions import TossdNetworkError

SCRIPT = REPO_ROOT / "scripts" / "check_vintage_drift.py"


def _import_script():
    """Import `check_vintage_drift.py` by path (`scripts/` is not a package)."""
    return import_script("check_vintage_drift.py")


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


def test_main_prints_clear_diagnostic_when_live_sweep_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An uncaught TossdNetworkError from the live sweep never leaves an empty report.

    `main()`'s default (network) mode wraps the live sweep so a
    `TossdNetworkError` prints a clear "sweep failed" line to stdout (what
    the canary job captures as the issue body) and returns 1, instead of an
    uncaught traceback going to stderr and leaving stdout (the report) empty.
    """
    module = _import_script()
    monkeypatch.setattr(
        module,
        "_run_live_sweep",
        lambda: (_ for _ in ()).throw(TossdNetworkError("publisher unreachable")),
    )

    exit_code = module.main([])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "sweep failed" in captured.out.lower()
    assert "publisher unreachable" in captured.out


def test_record_mode_writes_a_fresh_known_vintages_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`--record <path>` sweeps live and writes a known_vintages.json-shaped file."""
    module = _import_script()
    monkeypatch.setattr(
        module,
        "_run_live_sweep",
        lambda: {2019: {"etag": '"e19"', "size_bytes": 100}},
    )
    output_path = tmp_path / "known_vintages.json"

    exit_code = module.main(["--record", str(output_path)])

    assert exit_code == 0
    payload = json.loads(output_path.read_text())
    assert payload["2019"]["etag"] == '"e19"'
    assert payload["2019"]["size_bytes"] == 100
    assert "recorded_at" in payload["2019"]


def test_load_reference_reads_the_packaged_known_vintages_json() -> None:
    """The packaged `known_vintages.json` loads as `{year: {etag, size_bytes}}`."""
    module = _import_script()

    reference = module.load_reference()

    assert set(reference) == {2019, 2020, 2021, 2022, 2023, 2024}
    for record in reference.values():
        assert record["etag"]
        assert record["size_bytes"] and record["size_bytes"] > 0
