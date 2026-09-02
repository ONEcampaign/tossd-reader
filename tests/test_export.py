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

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import tossd_reader
from tests.factories import build_tossd_table
from tests.fakes import patch_discovery, patch_fetcher_by_url, url_for
from tossd_reader import _discovery, config, fetch, query
from tossd_reader._discovery import VintageInfo
from tossd_reader.exceptions import ExportIntegrityError

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
        types_mapper=query.ARROW_TO_PANDAS_INT.get
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


# --- one discovery sweep per call, not once per requested year ----------------


def test_export_multi_year_refresh_sweeps_discovery_exactly_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A multi-year export(refresh=True) call sweeps discovery once, not once per year."""
    years = [2019, 2020, 2021]
    _setup_default_years(monkeypatch, tmp_path, years, n_rows=5)

    calls: list[bool] = []
    real_discover = _discovery.discover

    def _spy(*, refresh: bool = False) -> dict:
        calls.append(refresh)
        return real_discover(refresh=refresh)

    monkeypatch.setattr(_discovery, "discover", _spy)

    tossd_reader.export(tmp_path / "out", years=years, refresh=True)

    assert len(calls) == 1


# --- verify_export / load_export -------------------------------------------------


def _manifest_path(destination: Path) -> Path:
    return destination.parent / f"{destination.stem}.manifest.json"


def test_export_manifest_carries_payload_sha256_matching_the_written_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The manifest's payload_sha256 is a real sha256 of the written parquet's own bytes."""
    _setup_default_years(monkeypatch, tmp_path, [2019])

    destination = tossd_reader.export(tmp_path / "out", years=2019)
    manifest = json.loads(_manifest_path(destination).read_text())

    assert (
        manifest["payload_sha256"]
        == hashlib.sha256(destination.read_bytes()).hexdigest()
    )


def test_verify_export_succeeds_silently_on_a_fresh_export(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A freshly written export passes verify_export -- and returns None."""
    _setup_default_years(monkeypatch, tmp_path, [2019])
    destination = tossd_reader.export(tmp_path / "out", years=2019)

    assert tossd_reader.verify_export(destination) is None


def test_verify_export_raises_on_missing_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No manifest sidecar at all raises ExportIntegrityError."""
    _setup_default_years(monkeypatch, tmp_path, [2019])
    destination = tossd_reader.export(tmp_path / "out", years=2019)
    _manifest_path(destination).unlink()

    with pytest.raises(ExportIntegrityError, match="manifest"):
        tossd_reader.verify_export(destination)


def test_verify_export_raises_on_unparseable_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A manifest sidecar that isn't valid JSON raises ExportIntegrityError."""
    _setup_default_years(monkeypatch, tmp_path, [2019])
    destination = tossd_reader.export(tmp_path / "out", years=2019)
    _manifest_path(destination).write_text("{not json")

    with pytest.raises(ExportIntegrityError, match="JSON"):
        tossd_reader.verify_export(destination)


def test_verify_export_raises_when_manifest_is_not_a_json_object(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Valid JSON that isn't an object (e.g. a bare list) still raises ExportIntegrityError."""
    _setup_default_years(monkeypatch, tmp_path, [2019])
    destination = tossd_reader.export(tmp_path / "out", years=2019)
    _manifest_path(destination).write_text("[1, 2, 3]")

    with pytest.raises(ExportIntegrityError, match="JSON object"):
        tossd_reader.verify_export(destination)


def test_verify_export_raises_when_manifest_predates_payload_sha256(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A manifest written before payload_sha256 existed can't be hash-verified, and says so."""
    _setup_default_years(monkeypatch, tmp_path, [2019])
    destination = tossd_reader.export(tmp_path / "out", years=2019)
    manifest_path = _manifest_path(destination)
    manifest = json.loads(manifest_path.read_text())
    del manifest["payload_sha256"]
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(ExportIntegrityError, match="payload_sha256"):
        tossd_reader.verify_export(destination)


def test_verify_export_raises_when_manifest_has_no_row_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A manifest missing row_count entirely can't be row-count-verified, and says so."""
    _setup_default_years(monkeypatch, tmp_path, [2019])
    destination = tossd_reader.export(tmp_path / "out", years=2019)
    manifest_path = _manifest_path(destination)
    manifest = json.loads(manifest_path.read_text())
    del manifest["row_count"]
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(ExportIntegrityError, match="row_count"):
        tossd_reader.verify_export(destination)


def test_verify_export_raises_on_payload_hash_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A payload modified after export fails the sha256 check."""
    _setup_default_years(monkeypatch, tmp_path, [2019])
    destination = tossd_reader.export(tmp_path / "out", years=2019)
    with destination.open("ab") as handle:
        handle.write(b"tampered-bytes")

    with pytest.raises(ExportIntegrityError, match="sha256"):
        tossd_reader.verify_export(destination)


def test_verify_export_raises_on_row_count_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A manifest row_count that no longer matches the payload fails, independent of the hash."""
    _setup_default_years(monkeypatch, tmp_path, [2019])
    destination = tossd_reader.export(tmp_path / "out", years=2019)
    manifest_path = _manifest_path(destination)
    manifest = json.loads(manifest_path.read_text())
    manifest["row_count"] = manifest["row_count"] + 1
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(ExportIntegrityError, match="row"):
        tossd_reader.verify_export(destination)


def test_verify_export_does_not_raise_on_schema_hash_difference(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A schema_hash mismatch (an export from a different package version) is not an integrity failure."""
    _setup_default_years(monkeypatch, tmp_path, [2019])
    destination = tossd_reader.export(tmp_path / "out", years=2019)
    manifest_path = _manifest_path(destination)
    manifest = json.loads(manifest_path.read_text())
    manifest["schema_hash"] = "not-the-real-hash"
    manifest_path.write_text(json.dumps(manifest))

    assert tossd_reader.verify_export(destination) is None


def test_load_export_matches_get_tossd_columns_all(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """load_export reads back exactly what get_tossd(columns="all") would produce."""
    years = [2019, 2020]
    _setup_default_years(monkeypatch, tmp_path, years)
    destination = tossd_reader.export(tmp_path / "out", years=years)

    loaded = tossd_reader.load_export(destination)
    expected = query.get_tossd(years=years, columns="all")

    assert list(loaded.columns) == list(expected.columns)
    assert loaded.dtypes.equals(expected.dtypes)
    assert len(loaded) == len(expected)


def test_load_export_attaches_manifest_provenance_to_attrs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`df.attrs["tossd_reader"]` carries package_version/created_at/years from the manifest."""
    _setup_default_years(monkeypatch, tmp_path, [2019])
    destination = tossd_reader.export(tmp_path / "out", years=2019)
    manifest = json.loads(_manifest_path(destination).read_text())

    loaded = tossd_reader.load_export(destination)

    assert loaded.attrs["tossd_reader"] == {
        "package_version": manifest["tossd_reader_version"],
        "created_at": manifest["created_at"],
        "years": manifest["vintages"],
    }


def test_load_export_verify_true_by_default_raises_on_tampered_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """load_export verifies by default: a tampered payload raises before reading it back."""
    _setup_default_years(monkeypatch, tmp_path, [2019])
    destination = tossd_reader.export(tmp_path / "out", years=2019)
    with destination.open("ab") as handle:
        handle.write(b"tampered-bytes")

    with pytest.raises(ExportIntegrityError, match="sha256"):
        tossd_reader.load_export(destination)


def test_load_export_verify_false_skips_integrity_checks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """verify=False loads a payload that no longer matches its manifest hash anyway.

    The replacement table is still structurally valid parquet (unlike the
    byte-appending tamper used by the hash-mismatch tests above) -- this
    test is about `verify=False` skipping the *manifest* check, not about
    surviving a corrupted file, so the payload itself must stay readable.
    """
    _setup_default_years(monkeypatch, tmp_path, [2019])
    destination = tossd_reader.export(tmp_path / "out", years=2019)
    pq.write_table(pa.table({"x": [1, 2, 3]}), destination)

    loaded = tossd_reader.load_export(destination, verify=False)

    assert "tossd_reader" in loaded.attrs
    assert list(loaded.columns) == ["x"]


def test_load_export_verify_false_still_raises_on_missing_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Even with verify=False, a missing manifest still raises: attrs can't be built without it."""
    _setup_default_years(monkeypatch, tmp_path, [2019])
    destination = tossd_reader.export(tmp_path / "out", years=2019)
    _manifest_path(destination).unlink()

    with pytest.raises(ExportIntegrityError, match="manifest"):
        tossd_reader.load_export(destination, verify=False)


# --- max_rows guard ----------------------------------------------------------------


def test_export_max_rows_none_applies_no_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`max_rows=None` (the default) is unchanged behaviour: no guard at all."""
    _setup_default_years(monkeypatch, tmp_path, [2019], n_rows=20)

    destination = tossd_reader.export(tmp_path / "out", years=2019, max_rows=None)

    assert pq.read_metadata(destination).num_rows == 20


def test_export_max_rows_under_the_limit_writes_normally(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A table at or under `max_rows=` writes exactly as it would without the guard."""
    _setup_default_years(monkeypatch, tmp_path, [2019], n_rows=20)

    destination = tossd_reader.export(tmp_path / "out", years=2019, max_rows=20)

    assert pq.read_metadata(destination).num_rows == 20


def test_export_max_rows_exceeded_raises_before_writing_anything(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Exceeding `max_rows=` raises naming the actual count and the limit, writing nothing."""
    _setup_default_years(monkeypatch, tmp_path, [2019], n_rows=20)
    target = tmp_path / "out"

    with pytest.raises(ValueError, match="20") as excinfo:
        tossd_reader.export(target, years=2019, max_rows=5)

    assert "max_rows=5" in str(excinfo.value)
    assert not target.exists()


# --- offline mode --------------------------------------------------------------------


def test_export_offline_refresh_conflict_raises_before_any_fetch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`refresh=True` while offline mode is active raises, naming export(), before any fetch."""
    config.set_offline(True)

    with pytest.raises(ValueError, match="export") as excinfo:
        tossd_reader.export(tmp_path / "out", years=2019, refresh=True)

    assert "offline" in str(excinfo.value)
    assert not (tmp_path / "out").exists()


def test_export_offline_serves_cache_with_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Offline mode (no refresh conflict) still exports, served from cache, with one warning."""
    _setup_default_years(monkeypatch, tmp_path, [2019], n_rows=8)
    fetch.fetch_year(2019)  # warm the cache

    config.set_offline(True)

    with pytest.warns(UserWarning, match="[Oo]ffline mode"):
        destination = tossd_reader.export(tmp_path / "out", years=2019)

    assert pq.read_metadata(destination).num_rows == 8
