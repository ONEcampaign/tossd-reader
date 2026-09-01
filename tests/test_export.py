"""Unit tests for `tossd_reader.export`: the arrow-level parquet + manifest writer.

Calls the public `tossd_reader.export(...)` surface throughout (not the
private `_export` module directly), since that also guards against the
module/function name collision `_export.py`'s own docstring explains:
`from tossd_reader import export` must always resolve to the function, never
to a same-named submodule.
"""

from __future__ import annotations

import hashlib
import importlib.resources
import json
from datetime import datetime
from pathlib import Path

import pyarrow.parquet as pq
import pytest

import tossd_reader
from tests.factories import build_tossd_table
from tests.fakes import patch_discovery, patch_fetcher_by_url, url_for
from tossd_reader import fetch, query
from tossd_reader._discovery import VintageInfo

# --- shared fetch/discovery patching (see tests/fakes.py) ---------------------


def _setup_default_years(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    years: list[int],
    n_rows: int = 20,
    seed: int = 0,
) -> None:
    published: dict[int, VintageInfo] = {}
    sources: dict[str, tuple[bytes, str | None]] = {}
    for year in years:
        table = build_tossd_table(year, n_rows=n_rows, seed=seed)
        path = tmp_path / f"fixture_{year}.parquet"
        pq.write_table(table, path, row_group_size=table.num_rows)
        url = url_for(year)
        etag = f'"e{year}"'
        published[year] = VintageInfo(url=url, etag=etag)
        sources[url] = (path.read_bytes(), etag)
    patch_discovery(monkeypatch, published)
    patch_fetcher_by_url(monkeypatch, sources)


def _independent_schema_hash() -> str:
    resource = importlib.resources.files("tossd_reader") / "_data" / "schema.csv"
    with importlib.resources.as_file(resource) as schema_path:
        data = schema_path.read_bytes()
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


# --- round trip: columns/dtypes match the pipeline output, zstd confirmed -----


def test_export_roundtrip_matches_pipeline_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Reading the exported parquet back matches `get_tossd(columns="all")`'s own output.

    The read uses the same `types_mapper` `get_tossd` does. Parquet stores the
    nullable integer widths faithfully, but pandas' default conversion widens
    any integer column holding nulls to `float64`, so a bare `to_pandas()`
    would compare two different conversions rather than two datasets.
    """
    years = [2019, 2020]
    _setup_default_years(monkeypatch, tmp_path, years)

    destination = tossd_reader.export(tmp_path / "out", years=years)
    written = pq.read_table(destination).to_pandas(
        types_mapper=query._ARROW_TO_PANDAS_INT.get
    )
    expected = query.get_tossd(years=years, columns="all")

    assert list(written.columns) == list(expected.columns)
    assert written.dtypes.equals(expected.dtypes)
    assert len(written) == len(expected)
    assert "is_aggregate" in written.columns
    assert "unit" in written.columns
    assert set(written["unit"]) == {"usd_thousand"}


def test_export_uses_zstd_compression(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The written parquet's row group is zstd-compressed."""
    _setup_default_years(monkeypatch, tmp_path, [2019])

    destination = tossd_reader.export(tmp_path / "out", years=2019)

    metadata = pq.ParquetFile(destination).metadata
    compression = metadata.row_group(0).column(0).compression
    assert compression.lower() == "zstd"


# --- manifest contents ----------------------------------------------------------


def test_export_manifest_contents(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The sidecar manifest carries version/schema-hash/years/provenance/row-count."""
    years = [2019, 2020]
    _setup_default_years(monkeypatch, tmp_path, years)

    destination = tossd_reader.export(tmp_path / "out", years=years)
    manifest_path = destination.parent / f"{destination.stem}.manifest.json"
    manifest = json.loads(manifest_path.read_text())

    assert manifest["schema_hash"] == _independent_schema_hash()
    assert manifest["years"] == years
    assert manifest["row_count"] == pq.read_metadata(destination).num_rows
    assert manifest["tossd_reader_version"]
    # created_at parses as a real ISO timestamp.
    datetime.fromisoformat(manifest["created_at"])

    for year in years:
        vintage = manifest["vintages"][str(year)]
        assert vintage["etag"] == f'"e{year}"'
        datetime.fromisoformat(vintage["retrieved_at"])


def test_export_manifest_warns_and_nulls_provenance_on_corrupt_sidecar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A corrupt sidecar warns and yields null manifest audit fields."""
    _setup_default_years(monkeypatch, tmp_path, [2019])
    cached_path = fetch.fetch_year(2019)
    cached_path.with_suffix(".provenance.json").write_text('{"url": "trunc')

    with pytest.warns(UserWarning, match="corrupt provenance sidecar"):
        destination = tossd_reader.export(tmp_path / "out", years=2019)

    manifest_path = destination.parent / f"{destination.stem}.manifest.json"
    manifest = json.loads(manifest_path.read_text())
    vintage = manifest["vintages"]["2019"]
    assert vintage["etag"] is None
    assert vintage["retrieved_at"] is None


# --- directory vs explicit file path handling -----------------------------------


def test_export_to_directory_creates_it_and_names_the_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A non-`.parquet` path is treated as a directory, created if missing."""
    years = [2019, 2020, 2021]
    _setup_default_years(monkeypatch, tmp_path, years)
    target_dir = tmp_path / "does" / "not" / "exist" / "yet"

    destination = tossd_reader.export(target_dir, years=years)

    assert destination == target_dir / "tossd_2019-2021.parquet"
    assert destination.exists()
    assert (target_dir / "tossd_2019-2021.manifest.json").exists()


def test_export_to_explicit_parquet_path_writes_exactly_there(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An explicit `.parquet` path is written verbatim (parent dirs created)."""
    _setup_default_years(monkeypatch, tmp_path, [2019])
    target = tmp_path / "nested" / "custom_name.parquet"

    destination = tossd_reader.export(target, years=2019)

    assert destination == target
    assert destination.exists()
    assert (tmp_path / "nested" / "custom_name.manifest.json").exists()


def test_export_single_year_stem_has_no_range(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A single exported year produces `tossd_<year>.parquet`, not a range."""
    _setup_default_years(monkeypatch, tmp_path, [2019])

    destination = tossd_reader.export(tmp_path, years=2019)

    assert destination.name == "tossd_2019.parquet"


def test_export_non_contiguous_years_joins_with_underscore(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Non-contiguous years are joined by `_`, not rendered as a misleading range."""
    _setup_default_years(monkeypatch, tmp_path, [2019, 2021])

    destination = tossd_reader.export(tmp_path, years=[2019, 2021])

    assert destination.name == "tossd_2019_2021.parquet"


# --- refresh passthrough ---------------------------------------------------------


def test_export_refresh_passthrough(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`refresh=True` reaches `effective_refresh` under export's own op key."""
    _setup_default_years(monkeypatch, tmp_path, [2019])

    calls: list[tuple[str, bool]] = []
    real_effective_refresh = query.effective_refresh

    def _spy(key: str, *, explicit: bool) -> bool:
        calls.append((key, explicit))
        return real_effective_refresh(key, explicit=explicit)

    monkeypatch.setattr(query, "effective_refresh", _spy)

    tossd_reader.export(tmp_path, years=2019, refresh=True)

    assert calls == [("tossd_reader:export", True)]
