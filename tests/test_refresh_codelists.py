"""Unit tests for `scripts/refresh_codelists.py`'s pure, offline `--check` diff mode.

No network access and no `oda-reader` import happen anywhere in this file --
only the maintainer script's directory-diff logic, exercised against
hand-built temp directories. This keeps the weekly drift CI job's core logic
testable in the default (offline) pytest suite.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from tests.factories import write_tossd_fixture
from tests.fakes import patch_discovery, patch_fetcher_by_url, url_for
from tests.script_loading import REPO_ROOT, import_script
from tossd_reader._discovery import VintageInfo

SCRIPT = REPO_ROOT / "scripts" / "refresh_codelists.py"
_PACKAGED_CODELISTS_DIR = REPO_ROOT / "src" / "tossd_reader" / "_data" / "codelists"


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


# --- _add_supplemental_rows --------------------------------------------------


def test_add_supplemental_rows_inserts_in_code_sorted_position() -> None:
    """Sector `700` lands between `600` and `720`; fetched rows are tagged `source="codelist"`."""
    module = _import_script()
    frame = pd.DataFrame(
        {
            "code": ["600", "720"],
            "name": ["VII. Action Relating to Debt", "VIII.1. Emergency Response"],
            "tossd_only": [False, False],
        }
    )

    result = module._add_supplemental_rows("sector", frame)

    assert list(result["code"]) == ["600", "700", "720"]
    assert list(result["source"]) == [
        "codelist",
        "dac-sector-classification",
        "codelist",
    ]
    assert (
        result.loc[result["code"] == "700", "name"].item() == "VIII. Humanitarian Aid"
    )
    assert bool(result.loc[result["code"] == "700", "tossd_only"].item()) is False


def test_add_supplemental_rows_is_a_noop_for_dimensions_without_supplemental_rows() -> (
    None
):
    """A dimension with no `_SUPPLEMENTAL_ROWS` entry passes its frame through unchanged."""
    module = _import_script()
    frame = pd.DataFrame({"code": ["10000"], "name": ["Public"], "tossd_only": [False]})

    result = module._add_supplemental_rows("channel", frame)

    assert "source" not in result.columns
    assert result.equals(frame)


def test_add_supplemental_rows_skips_a_code_the_fetch_already_carries() -> None:
    """A fetched `700` wins over the hardcoded one -- exactly one `700` row survives, and a warning fires."""
    module = _import_script()
    frame = pd.DataFrame(
        {
            "code": ["600", "700", "720"],
            "name": [
                "VII. Action Relating to Debt",
                "VIII. Humanitarian Aid",
                "VIII.1. Emergency Response",
            ],
            "tossd_only": [False, False, False],
        }
    )

    with pytest.warns(UserWarning, match="700"):
        result = module._add_supplemental_rows("sector", frame)

    assert list(result["code"]) == ["600", "700", "720"]
    assert list(result["source"]) == ["codelist", "codelist", "codelist"]


# --- drift-canary normalisation: annotation columns + the supplemental row --


def _write_sector_snapshot(
    directory: Path,
    *,
    header: str,
    rows: str,
    fetched_at: str = "2026-01-01T00:00:00+00:00",
    annotated_from_years: list[int] | None = None,
) -> None:
    """Write a minimal `sector.csv` + `_version.json` snapshot for `--check` tests."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "sector.csv").write_text(f"{header}\n{rows}")
    payload: dict[str, object] = {
        "fetched_at": fetched_at,
        "source_url": "https://development-finance-codelists.oecd.org/CodesList.aspx",
        "codelist_ids": {"sector": "10"},
    }
    if annotated_from_years is not None:
        payload["annotated_from_years"] = annotated_from_years
    (directory / "_version.json").write_text(json.dumps(payload))


def test_check_ignores_annotation_columns_when_content_matches(tmp_path: Path) -> None:
    """An annotated baseline (`source`/`in_published_data`, every row `source="codelist"`) matches a bare candidate."""
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    _write_sector_snapshot(
        baseline,
        header="code,name,tossd_only,source,in_published_data",
        rows="110,Education,False,codelist,True\n120,Health,False,codelist,False\n",
    )
    _write_sector_snapshot(
        candidate,
        header="code,name,tossd_only",
        rows="110,Education,False\n120,Health,False\n",
    )

    result = _run_check(baseline, candidate)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "No codelist drift detected" in result.stdout


def test_check_detects_row_level_drift_despite_annotation_columns(
    tmp_path: Path,
) -> None:
    """A genuinely changed row is still caught, annotation columns notwithstanding."""
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    _write_sector_snapshot(
        baseline,
        header="code,name,tossd_only,source,in_published_data",
        rows="110,Education,False,codelist,True\n",
    )
    _write_sector_snapshot(
        candidate,
        header="code,name,tossd_only",
        rows="110,Basic Education,False\n",
    )

    result = _run_check(baseline, candidate)

    assert result.returncode == 1
    assert "sector.csv" in result.stdout


def test_check_ignores_the_supplemental_row(tmp_path: Path) -> None:
    """The packaged `700` supplemental row (a live fetch never produces it) doesn't alarm the canary."""
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    _write_sector_snapshot(
        baseline,
        header="code,name,tossd_only,source",
        rows=(
            "110,Education,False,codelist\n"
            "700,VIII. Humanitarian Aid,False,dac-sector-classification\n"
        ),
    )
    _write_sector_snapshot(
        candidate,
        header="code,name,tossd_only",
        rows="110,Education,False\n",
    )

    result = _run_check(baseline, candidate)

    assert result.returncode == 0, result.stdout + result.stderr


def test_check_ignores_differing_annotated_from_years(tmp_path: Path) -> None:
    """`_version.json`'s `annotated_from_years` doesn't feed `_diff_codelist_ids`."""
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    _write_sector_snapshot(
        baseline,
        header="code,name,tossd_only",
        rows="110,Education,False\n",
        annotated_from_years=[2019, 2020],
    )
    _write_sector_snapshot(
        candidate,
        header="code,name,tossd_only",
        rows="110,Education,False\n",
    )

    result = _run_check(baseline, candidate)

    assert result.returncode == 0, result.stdout + result.stderr


# --- --annotate: annotate_dimensions -----------------------------------------


def _copied_codelists_dir(tmp_path: Path) -> Path:
    """Copy the real packaged codelists directory to a scratch dir for `--annotate` tests."""
    destination = tmp_path / "codelists"
    shutil.copytree(_PACKAGED_CODELISTS_DIR, destination)
    return destination


def _stand_up_fixture_year(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, year: int
) -> None:
    """Patch discovery + the fetcher so `fetch.fetch_year(year)` serves a synthetic fixture, no network."""
    fixture_path = tmp_path / f"tossddata_{year}.parquet"
    write_tossd_fixture(fixture_path, year)
    url = url_for(year)
    patch_discovery(monkeypatch, {year: VintageInfo(url=url, etag='"e1"')})
    patch_fetcher_by_url(monkeypatch, {url: (fixture_path.read_bytes(), '"e1"')})


def test_annotate_dimensions_marks_observed_and_unobserved_codes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A code the synthetic fixture emits reads True; one it never emits reads False."""
    module = _import_script()
    codelists_dir = _copied_codelists_dir(tmp_path)
    _stand_up_fixture_year(monkeypatch, tmp_path, 2019)

    module.annotate_dimensions(codelists_dir, years=(2019,))

    sector = pd.read_csv(codelists_dir / "sector.csv", dtype={"code": str}).set_index(
        "code"
    )
    assert bool(sector.loc["110", "in_published_data"]) is True
    assert bool(sector.loc["998", "in_published_data"]) is False

    modality = pd.read_csv(
        codelists_dir / "modality.csv", dtype={"code": str}
    ).set_index("code")
    assert bool(modality.loc["C01", "in_published_data"]) is True
    assert bool(modality.loc["A", "in_published_data"]) is False


def test_annotate_dimensions_splits_pipe_packed_codes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Both codes of a pipe-packed `"FA01|FA02"` row are recorded, not the packed string itself."""
    module = _import_script()
    codelists_dir = _copied_codelists_dir(tmp_path)
    _stand_up_fixture_year(monkeypatch, tmp_path, 2019)

    module.annotate_dimensions(codelists_dir, years=(2019,))

    financing_arrangement = pd.read_csv(
        codelists_dir / "financing_arrangement.csv", dtype={"code": str}
    ).set_index("code")
    assert bool(financing_arrangement.loc["FA01", "in_published_data"]) is True
    assert bool(financing_arrangement.loc["FA02", "in_published_data"]) is True
    assert bool(financing_arrangement.loc["FA03", "in_published_data"]) is False


def test_annotate_dimensions_records_annotated_from_years(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`_version.json` gains a sorted `annotated_from_years`, preserving its other fields."""
    module = _import_script()
    codelists_dir = _copied_codelists_dir(tmp_path)
    _stand_up_fixture_year(monkeypatch, tmp_path, 2019)
    before = json.loads((codelists_dir / "_version.json").read_text())

    module.annotate_dimensions(codelists_dir, years=(2019,))

    after = json.loads((codelists_dir / "_version.json").read_text())
    assert after["annotated_from_years"] == [2019]
    assert after["fetched_at"] == before["fetched_at"]
    assert after["codelist_ids"] == before["codelist_ids"]


def test_annotate_dimensions_leaves_pillar_untouched(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`pillar.csv` is never annotated -- its rows are structural, not one flat data column."""
    module = _import_script()
    codelists_dir = _copied_codelists_dir(tmp_path)
    _stand_up_fixture_year(monkeypatch, tmp_path, 2019)
    before = (codelists_dir / "pillar.csv").read_text()

    counts = module.annotate_dimensions(codelists_dir, years=(2019,))

    assert "pillar" not in counts
    assert (codelists_dir / "pillar.csv").read_text() == before


@pytest.mark.parametrize(
    ("token", "expected"),
    [("700.0", "700"), ("700", "700"), ("7.5", "7.5"), ("B02", "B02")],
)
def test_normalise_observed_code_strips_spurious_float_suffix(
    token: str, expected: str
) -> None:
    """A numeric-typed raw column's `"700.0"` normalises to the packaged `"700"`; other tokens pass through."""
    module = _import_script()
    assert module._normalise_observed_code(token) == expected
