"""Maintainer-side refresh script for tossd_reader's packaged OECD codelists.

Fetches the provider/recipient area codelists and the TOSSD-relevant category
codelists from development-finance-codelists.oecd.org, via oda-reader's ASPX
handshake (never bypassed with a plain HTTP client — a bare request gets a
403), and writes deterministic, per-dimension CSV files to
`src/tossd_reader/_data/codelists/`, plus a `_version.json` stamp. The
packaged output is what `tossd_reader.codelists` (the runtime loader) reads;
oda-reader itself is a maintainer-only dependency (the `codelists` dependency
group) and is never imported at runtime.

Run under the `codelists` dependency group only:
    uv run --group codelists python scripts/refresh_codelists.py
    uv run --group codelists python scripts/refresh_codelists.py --check <baseline-dir> <candidate-dir>

`--annotate <codelists-dir>` is offline (no `codelists` group, no oda-reader
call): it scans locally cached TOSSD data vintages via `tossd_reader`'s own
fetch layer to record which packaged codes actually occur in the published
data.
    uv run python scripts/refresh_codelists.py --annotate <codelists-dir>

Licence note: this script, and the packaged snapshot it produces, redistributes
OECD development-finance codelist data. Redistribution licensing for a public
release is unresolved and tracked outside this repo; packaging the snapshot
here does not resolve it.
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Final

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

_PACKAGED_DIR: Final = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "tossd_reader"
    / "_data"
    / "codelists"
)

_AREA_CODELIST_IDS: Final[dict[str, str]] = {
    "provider": "5",
    "recipient": "13",
}
"""dimension -> oda-reader area codelist id, fetched via `fetch_codelists`."""

_CATEGORY_CODELIST_IDS: Final[dict[str, str]] = {
    "pillar": "19",  # TOSSD Pillar
    "financing_arrangement": "17",  # Financing Arrangement (FA01-FA05)
    "framework_of_collaboration": "18",  # Framework of collaboration (FC01-FC03)
    "purpose": "10",  # Purpose code -- split below into purpose (5/7-digit) + sector (3-digit)
    "channel": "3",  # Channel of delivery
    "modality": "14",  # Co-operation modality
    "finance_instrument": "15",  # Type of finance
}
"""dimension -> oda-reader category codelist id, fetched via
`fetch_code_categories`. `purpose`'s id ("10") is not written as its own
`purpose.csv` -- see `_split_purpose_and_sector`."""

_PURPOSE_DIMENSION: Final = "purpose"
_SECTOR_DIMENSION: Final = "sector"
_SECTOR_CODE_LENGTH: Final = 3
"""Purpose code (id "10") carries both 3-digit sector-level codes and
5/7-digit purpose-level codes in one flat list; TOSSD's `sector` dimension has
no id of its own and is a length-based split of this same codelist."""

_FETCHED_SOURCE: Final = "codelist"
"""`source` value stamped on every row that came from the live fetch, as
opposed to one of `_SUPPLEMENTAL_ROWS`'s own `source` values."""

_SUPPLEMENTAL_ROWS: Final[dict[str, tuple[dict[str, object], ...]]] = {
    _SECTOR_DIMENSION: (
        {
            "code": "700",
            "name": "VIII. Humanitarian Aid",
            "tossd_only": False,
            "source": "dac-sector-classification",
        },
    ),
}
"""Rows the fetched codelist snapshot never carries, packaged anyway because
the published TOSSD data reports them (sector `700`: the DAC 3-digit sector
classification's own "VIII. Humanitarian Aid" group heading over the
packaged `720`/`730`/`740` rows -- verified against the OECD's CRS purpose
codes documentation, not the fetched codelist, which only lists reportable
codes). Merged into the fetched frame by `_add_supplemental_rows`, in
code-sorted position, so a hand edit of the CSV is never needed and a
refresh never drops it. Only a dimension listed here gains a `source`
column at all."""


def _dedupe_by_code(frame: pd.DataFrame) -> pd.DataFrame:
    """Collapse historical duplicate `code` rows to one row per code.

    A handful of codes (recipient country reclassifications, channel merger
    history) carry more than one row across different `activation_date`s and
    `status`es -- verified live, every such group shares an identical label,
    so this only chooses among otherwise-identical rows. Prefers the
    `status == "active"` row; falls back to the most recent `activation_date`
    when none is active.
    """
    is_active = frame["status"] == "active"
    ranked = frame.assign(_rank=(~is_active).astype(int))
    ranked = ranked.sort_values(
        ["code", "_rank", "activation_date"], ascending=[True, True, False]
    )
    return ranked.drop_duplicates(subset="code", keep="first").drop(columns="_rank")


def _sort_key(code: str) -> tuple[int, int | str]:
    """Sort numeric codes by value, non-numeric codes lexicographically after them."""
    return (0, int(code)) if code.isdigit() else (1, code)


def _project_dimension_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Filter, dedupe and project one raw codelist frame to the packaged column set.

    Filters to TOSSD-applicable rows (`tossd == "1"`) where the column
    exists; every codelist this script packages carries one. Keeps `code`,
    renames `label` to `name`, keeps `iso3` where present, and derives
    `tossd_only` from `crs == "0"` -- `crs` marks whether a code is also valid
    under CRS reporting, so `tossd_only` is what lets downstream code tell a
    TOSSD-specific code (e.g. one of the 26 TOSSD-only purpose codes) apart
    from one shared with CRS.

    Returns:
        A new frame with columns `code`, `name`, `tossd_only`, and `iso3`
        (only when the source frame had one), sorted by `code`.
    """
    if "tossd" in frame.columns:
        frame = frame[frame["tossd"] == "1"]
    frame = _dedupe_by_code(frame)

    projected = pd.DataFrame(
        {
            "code": frame["code"].astype(str),
            "name": frame["label"].astype(str),
            "tossd_only": frame["crs"] == "0",
        }
    )
    if "iso3" in frame.columns:
        projected["iso3"] = frame["iso3"].to_numpy()

    order = sorted(projected.index, key=lambda i: _sort_key(projected.at[i, "code"]))
    return projected.loc[order].reset_index(drop=True)


def _split_purpose_and_sector(purpose_frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split the projected Purpose-code frame into `purpose` and `sector` dimensions.

    3-digit codes are DAC sector-level aggregates; everything else (5- and
    7-digit codes) is purpose-level detail.
    """
    is_sector = purpose_frame["code"].str.len() == _SECTOR_CODE_LENGTH
    return {
        _SECTOR_DIMENSION: purpose_frame[is_sector].reset_index(drop=True),
        _PURPOSE_DIMENSION: purpose_frame[~is_sector].reset_index(drop=True),
    }


def _add_supplemental_rows(dimension: str, frame: pd.DataFrame) -> pd.DataFrame:
    """Merge `dimension`'s `_SUPPLEMENTAL_ROWS` (if any) into a freshly fetched `frame`.

    A no-op for a dimension with no supplemental rows -- only `sector` gains
    a `source` column today. Every already-fetched row is tagged
    `_FETCHED_SOURCE`; each surviving supplemental row carries its own
    `source` value. A supplemental row whose code `frame` already carries is
    skipped (with a warning) instead of appended alongside it -- the OECD
    source now reports that code itself, so the hardcoded row is a live
    duplicate and should be retired from `_SUPPLEMENTAL_ROWS`. Re-sorts by
    `code` (the same key `_project_dimension_frame` sorts by) so a surviving
    supplemental row lands in its code-sorted position rather than trailing
    the file.
    """
    supplemental = _SUPPLEMENTAL_ROWS.get(dimension)
    if not supplemental:
        return frame
    tagged = frame.assign(source=_FETCHED_SOURCE)
    fetched_codes = set(frame["code"])
    surviving_rows = []
    for row in supplemental:
        if row["code"] in fetched_codes:
            warnings.warn(
                f"{dimension} supplemental row {row['code']!r} is now "
                "present in the fetched codelist itself; retire it from "
                "_SUPPLEMENTAL_ROWS.",
                stacklevel=2,
            )
            continue
        surviving_rows.append(row)
    combined = pd.concat([tagged, pd.DataFrame(surviving_rows)], ignore_index=True)
    order = sorted(combined.index, key=lambda i: _sort_key(combined.at[i, "code"]))
    return combined.loc[order].reset_index(drop=True)


def build_dimension_frames() -> tuple[dict[str, pd.DataFrame], datetime, str]:
    """Fetch every packaged codelist live and project it to its dimension frame.

    One `fetch_codelists` call for the two area codelists, one
    `fetch_code_categories` call for every category codelist -- each id
    requested in a single request rather than one per dimension.

    Returns:
        A 3-tuple: `{dimension: frame}` covering every packaged dimension,
        the later of the two snapshots' `fetched_at`, and the shared
        `source_url`.
    """
    # Imported here, not at module scope: `oda_reader` lives in the
    # maintainer-only `codelists` dependency group, so importing it lazily
    # keeps `--check`'s pure offline diff mode (and this module generally)
    # importable without that group installed.
    from oda_reader.codelists import (  # noqa: PLC0415 -- deliberately lazy, see above
        fetch_code_categories,
        fetch_codelists,
    )

    area_snapshot = fetch_codelists(codelist_ids=tuple(_AREA_CODELIST_IDS.values()))
    category_snapshot = fetch_code_categories(
        codelist_ids=tuple(_CATEGORY_CODELIST_IDS.values())
    )

    frames: dict[str, pd.DataFrame] = {}
    for dimension, codelist_id in _AREA_CODELIST_IDS.items():
        raw = area_snapshot.frame[area_snapshot.frame["codelist_id"] == codelist_id]
        frames[dimension] = _project_dimension_frame(raw)

    for dimension, codelist_id in _CATEGORY_CODELIST_IDS.items():
        raw = category_snapshot.frame[
            category_snapshot.frame["codelist_id"] == codelist_id
        ]
        projected = _project_dimension_frame(raw)
        if dimension == _PURPOSE_DIMENSION:
            frames.update(_split_purpose_and_sector(projected))
        else:
            frames[dimension] = projected

    for dimension, frame in frames.items():
        frames[dimension] = _add_supplemental_rows(dimension, frame)

    fetched_at = max(area_snapshot.fetched_at, category_snapshot.fetched_at)
    return frames, fetched_at, area_snapshot.source_url


def _version_payload(*, fetched_at: datetime, source_url: str) -> dict[str, object]:
    """Build the `_version.json` payload for one refresh run."""
    dimension_to_id = dict(_AREA_CODELIST_IDS)
    for dimension, codelist_id in _CATEGORY_CODELIST_IDS.items():
        if dimension == _PURPOSE_DIMENSION:
            dimension_to_id[_PURPOSE_DIMENSION] = codelist_id
            dimension_to_id[_SECTOR_DIMENSION] = codelist_id
        else:
            dimension_to_id[dimension] = codelist_id
    return {
        "fetched_at": fetched_at.isoformat(),
        "source_url": source_url,
        "codelist_ids": dimension_to_id,
    }


def write_snapshot(
    frames: dict[str, pd.DataFrame],
    *,
    output_dir: Path,
    fetched_at: datetime,
    source_url: str,
) -> None:
    """Write `frames` and a `_version.json` stamp to `output_dir`.

    Deterministic: each frame is already sorted by `code` (see
    `_project_dimension_frame`), and every CSV is written with an explicit
    LF line ending regardless of platform, so reruns produce clean diffs.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    for dimension, frame in frames.items():
        frame.to_csv(output_dir / f"{dimension}.csv", index=False, lineterminator="\n")

    payload = _version_payload(fetched_at=fetched_at, source_url=source_url)
    (output_dir / "_version.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n"
    )


def diff_snapshot_dirs(baseline_dir: Path, candidate_dir: Path) -> list[str]:
    """Diff two packaged-snapshot directories, ignoring `_version.json`'s `fetched_at`.

    Pure, offline comparison -- no network, no oda-reader call -- so the CI
    drift job's logic (and this function) can be exercised in a normal
    pytest run against two prepared temp directories.

    Args:
        baseline_dir: The currently packaged snapshot (e.g. the repo's
            `src/tossd_reader/_data/codelists`).
        candidate_dir: A freshly refreshed snapshot to compare against it.

    Returns:
        Human-readable descriptions of every difference found (added/removed
        dimension files, or changed rows within a shared one, plus a changed
        `codelist_ids` mapping). Empty when the two directories are
        equivalent.
    """
    baseline_csvs = {path.stem for path in baseline_dir.glob("*.csv")}
    candidate_csvs = {path.stem for path in candidate_dir.glob("*.csv")}

    diffs: list[str] = [
        f"{dimension}.csv: present in baseline, missing from candidate"
        for dimension in sorted(baseline_csvs - candidate_csvs)
    ]
    diffs.extend(
        f"{dimension}.csv: present in candidate, missing from baseline"
        for dimension in sorted(candidate_csvs - baseline_csvs)
    )

    for dimension in sorted(baseline_csvs & candidate_csvs):
        baseline_frame = _read_normalised(baseline_dir / f"{dimension}.csv")
        candidate_frame = _read_normalised(candidate_dir / f"{dimension}.csv")
        if not baseline_frame.equals(candidate_frame):
            diffs.append(
                f"{dimension}.csv: content differs ({len(baseline_frame)} baseline "
                f"rows vs {len(candidate_frame)} candidate rows)"
            )

    version_diff = _diff_codelist_ids(baseline_dir, candidate_dir)
    if version_diff is not None:
        diffs.append(version_diff)
    return diffs


_ANNOTATION_ONLY_COLUMNS: Final = ("source", "in_published_data")
"""Columns a live-refreshed candidate never carries but a packaged,
supplemented and/or annotated baseline may: dropped by `_read_normalised`
before comparison, alongside any row `_read_normalised` itself has already
excluded (a supplemental row -- see `_SUPPLEMENTAL_ROWS`), so the drift
canary never alarms on either."""


def _read_normalised(path: Path) -> pd.DataFrame:
    """Read one packaged CSV, sorted by every column, for order-insensitive comparison.

    Drops whatever `_add_supplemental_rows` and `--annotate` add before
    comparing: a row whose `source` is present and not `_FETCHED_SOURCE`
    (a supplemental row, e.g. sector `700`) is dropped first, then the
    `source`/`in_published_data` columns themselves are dropped wherever
    present. A freshly refreshed snapshot never carries either; the
    packaged baseline may carry both -- without this, the weekly drift job
    would alarm on every run.
    """
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    if "source" in frame.columns:
        frame = frame[frame["source"] == _FETCHED_SOURCE]
    frame = frame.drop(
        columns=[
            column for column in _ANNOTATION_ONLY_COLUMNS if column in frame.columns
        ]
    )
    columns = list(frame.columns)
    return frame.sort_values(columns).reset_index(drop=True)


def _diff_codelist_ids(baseline_dir: Path, candidate_dir: Path) -> str | None:
    """Compare the two directories' `_version.json` `codelist_ids` mappings.

    Ignores `fetched_at`/`source_url`, which legitimately differ on every
    refresh run.
    """
    baseline_path = baseline_dir / "_version.json"
    candidate_path = candidate_dir / "_version.json"
    if not baseline_path.exists() or not candidate_path.exists():
        return None
    baseline_ids = json.loads(baseline_path.read_text()).get("codelist_ids", {})
    candidate_ids = json.loads(candidate_path.read_text()).get("codelist_ids", {})
    if baseline_ids != candidate_ids:
        return f"_version.json codelist_ids differ: {baseline_ids} vs {candidate_ids}"
    return None


def _run_refresh(output_dir: Path) -> None:
    """Fetch live and write a fresh snapshot to `output_dir`."""
    frames, fetched_at, source_url = build_dimension_frames()
    write_snapshot(
        frames, output_dir=output_dir, fetched_at=fetched_at, source_url=source_url
    )
    for dimension, frame in sorted(frames.items()):
        print(f"{dimension}: {len(frame)} rows", file=sys.stderr)


_ANNOTATED_DIMENSIONS: Final[tuple[str, ...]] = (
    "provider",
    "recipient",
    "sector",
    "purpose",
    "channel",
    "modality",
    "finance_instrument",
    "financing_arrangement",
    "framework_of_collaboration",
)
"""Dimensions `--annotate` checks against the published data. `pillar` is
deliberately excluded: its rows are structural (`1`/`2`/`21`/`22`/`I`/`II`/
`II.A`/`II.B` tokens), not a code that maps onto one flat published-data
column the way every other dimension's does."""


def _dimension_to_published_column() -> dict[str, str]:
    """Map each `_ANNOTATED_DIMENSIONS` entry to its published column name, via `schema.csv`.

    Every annotated dimension's packaged codelist `code` column backs one
    `schema.csv` row whose `snake_name` is `f"{dimension}_code"` -- e.g.
    `sector` -> `sector_code` -> published `sector3`.
    """
    from tossd_reader._schema import load_schema  # noqa: PLC0415 - only needed here

    by_snake_name = {field.snake_name: field.published_name for field in load_schema()}
    return {
        dimension: by_snake_name[f"{dimension}_code"]
        for dimension in _ANNOTATED_DIMENSIONS
    }


def _normalise_observed_code(token: str) -> str:
    """Strip a spurious float `".0"` suffix so a numeric raw column's `"700.0"` matches the packaged `"700"`.

    Every packaged codelist `code` column is a plain digit string; this
    guards the defensive case where a raw published column arrives typed as
    a number rather than the `string` `arrow_type` `schema.csv` documents.
    """
    if token.endswith(".0") and token[:-2].isdigit():
        return token[:-2]
    return token


def _observed_codes(column: pa.ChunkedArray | pa.Array) -> set[str]:
    """Return the distinct non-null token codes in one published column, pipe-split.

    Splitting on `"|"` is a no-op for a column that never packs (a single
    token split on `"|"` is itself), so this applies uniformly to every
    scanned column rather than special-casing the two observed to pack more
    than one code (`financing_arrangement`, `framework_of_collaboration`,
    e.g. `"FA01|FA02"`).
    """
    codes: set[str] = set()
    for value in column.drop_null().unique().to_pylist():
        for raw_token in str(value).split("|"):
            token = raw_token.strip()
            if token:
                codes.add(_normalise_observed_code(token))
    return codes


def _write_annotated_years(codelists_dir: Path, years: Iterable[int]) -> None:
    """Merge `annotated_from_years` (sorted) into `codelists_dir`'s existing `_version.json`."""
    version_path = codelists_dir / "_version.json"
    payload = json.loads(version_path.read_text())
    payload["annotated_from_years"] = sorted(years)
    version_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def annotate_dimensions(
    codelists_dir: Path, *, years: Iterable[int] | None = None
) -> dict[str, int]:
    """Annotate every `_ANNOTATED_DIMENSIONS` CSV under `codelists_dir` with `in_published_data`.

    Offline apart from `tossd_reader`'s own fetch layer: never fetches
    codelists from the network (no `oda_reader` call). For each requested
    year, reads only the cached vintage's needed columns
    (`pyarrow.parquet.read_table(path, columns=[...])`) rather than loading
    every year's full frame at once, to see which codes actually occur in
    the published data, then writes each dimension's CSV back in place with
    an `in_published_data` column appended. Records the scanned years,
    sorted, into `codelists_dir/_version.json`'s `annotated_from_years`.

    Args:
        codelists_dir: Directory holding the already-packaged dimension CSVs
            to annotate in place.
        years: Years to scan. Defaults to
            `tossd_reader._discovery.known_years()`.

    Returns:
        `{dimension: distinct codes observed in the scanned years}`, for the
        CLI's own summary.
    """
    from tossd_reader import _discovery, fetch  # noqa: PLC0415 - only needed here

    resolved_years = tuple(years) if years is not None else _discovery.known_years()
    published_columns = _dimension_to_published_column()

    observed: dict[str, set[str]] = {
        dimension: set() for dimension in _ANNOTATED_DIMENSIONS
    }
    for year in resolved_years:
        path = fetch.fetch_year(year)
        table = pq.read_table(path, columns=list(published_columns.values()))
        for dimension, column_name in published_columns.items():
            observed[dimension].update(_observed_codes(table.column(column_name)))

    for dimension in _ANNOTATED_DIMENSIONS:
        csv_path = codelists_dir / f"{dimension}.csv"
        frame = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        frame["in_published_data"] = frame["code"].isin(observed[dimension])
        frame.to_csv(csv_path, index=False, lineterminator="\n")

    _write_annotated_years(codelists_dir, resolved_years)
    return {dimension: len(codes) for dimension, codes in observed.items()}


def _run_annotate(codelists_dir: Path) -> int:
    """CLI entry for `--annotate`: annotate `codelists_dir` in place and report counts."""
    counts = annotate_dimensions(codelists_dir)
    for dimension, count in sorted(counts.items()):
        print(
            f"{dimension}: {count} distinct codes observed in the published data",
            file=sys.stderr,
        )
    return 0


def _run_check(baseline_dir: Path, candidate_dir: Path) -> int:
    """Diff two directories and report; returns the process exit code."""
    diffs = diff_snapshot_dirs(baseline_dir, candidate_dir)
    if not diffs:
        print("No codelist drift detected.")
        return 0
    print("Codelist drift detected:")
    for diff in diffs:
        print(f"- {diff}")
    return 1


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Three modes:
    - Default: fetch live and write a snapshot to `--output-dir` (defaults to
      the packaged `src/tossd_reader/_data/codelists`).
    - `--check <baseline-dir> <candidate-dir>`: pure offline diff between two
      already-written snapshot directories; no network, no oda-reader call.
    - `--annotate <codelists-dir>`: offline apart from `tossd_reader`'s own
      fetch layer; annotates that directory's CSVs in place with
      `in_published_data`. No oda-reader call either.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_PACKAGED_DIR,
        help="Where to write the refreshed snapshot (default: the packaged _data/codelists).",
    )
    parser.add_argument(
        "--check",
        nargs=2,
        metavar=("BASELINE_DIR", "CANDIDATE_DIR"),
        help="Pure offline diff between two snapshot directories; exits 1 on drift.",
    )
    parser.add_argument(
        "--annotate",
        type=Path,
        metavar="CODELISTS_DIR",
        help=(
            "Annotate CODELISTS_DIR's dimension CSVs in place with "
            "in_published_data, scanned from locally cached TOSSD data "
            "vintages. Never fetches codelists from the network."
        ),
    )
    args = parser.parse_args(argv)

    if args.check is not None:
        baseline_dir, candidate_dir = (Path(value) for value in args.check)
        return _run_check(baseline_dir, candidate_dir)

    if args.annotate is not None:
        return _run_annotate(args.annotate)

    _run_refresh(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
