"""Maintainer-side build script for tossd_reader's packaged recipient-groups table.

Builds `src/tossd_reader/_data/recipient_groups.csv` (plus its
`recipient_groups_version.json` stamp): one row per code in the packaged
`_data/codelists/recipient.csv`, across three independently-sourced grouping
schemes -- `ldc_group`, `income_group`, `region` -- consumed at runtime by
`tossd_reader.analysis.add_recipient_group`. Like `refresh_codelists.py`,
this is maintainer-run, not part of any automated CI job: it writes a
candidate file for a human to review and commit, never auto-applies.

Sources, one per scheme:

- `ldc_group` -- UN LDC membership. OHRLLS,
  <https://www.un.org/ohrlls/content/list-ldcs>, cross-checked against
  UNCTAD's list, <https://unctad.org/topic/least-developed-countries/list>.
  The 44-member list moves only at triennial CDP reviews (next: 2027) plus a
  handful of individually announced, years-ahead-dated graduations -- both
  are plain HTML content pages, not a stable machine-readable feed, so
  scripting a live scrape here would be fragile for a source this
  infrequently updated. Membership is instead a checked-in constant,
  `_LDC_ISO3_CODES` below, dated and sourced in its own comment.
  **Maintainer: re-verify against both URLs before every run, and update the
  constant by hand when membership changes.**
- `income_group` -- World Bank income classification, fetched live from the
  Data Help Desk's downloadable "List of economies" workbook (needs
  `openpyxl`; not a core project dependency -- run this script via
  `uv run --with openpyxl python scripts/build_recipient_groups.py`). The
  resource id in `_WB_INCOME_RESOURCE_URL` changes with each annual FY
  release; if the fetch 404s, find the current one linked from
  <https://datahelpdesk.worldbank.org/knowledgebase/articles/906519-world-bank-country-and-lending-groups>
  and update that constant and `_WB_VERSION_LABEL` together.
- `region` -- derived live from TOSSD's own published data
  (`recipientcode`/`regionnamee`), via `tossd_reader.fetch.get_tossd_raw` --
  not a UN/WB concept, TOSSD publishes it directly per activity. Verified
  unique per `recipient_code` before writing; a code that maps to more than
  one region across the fetched years is reported and the region column is
  dropped from the written table rather than guessed (see
  `derive_region_map`).

Six ISO3-bearing codelist entries (non-self-governing territories: Saint
Helena, Montserrat, Cook Islands, Niue, Tokelau, Wallis and Futuna) carry no
World Bank income classification at all -- mapped to an explicit
`"Unclassified"` `income_group`, distinct from `"Regional-Multi-country
Unallocated"` (reserved for the packaged codelist's no-iso3
regional/aggregate rows, e.g. "Europe, regional", "Global").

Run (needs network -- both the World Bank fetch and the TOSSD fetch):
    uv run --with openpyxl python scripts/build_recipient_groups.py
    uv run --with openpyxl python scripts/build_recipient_groups.py \\
        --check <baseline.csv> <candidate.csv>
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import pandas as pd
import requests

from tossd_reader import codelists, fetch

_PACKAGED_DATA_DIR: Final = (
    Path(__file__).resolve().parent.parent / "src" / "tossd_reader" / "_data"
)
_OUTPUT_CSV_NAME: Final = "recipient_groups.csv"
_OUTPUT_VERSION_NAME: Final = "recipient_groups_version.json"

_LDC_SOURCE_URLS: Final = (
    "https://www.un.org/ohrlls/content/list-ldcs",
    "https://unctad.org/topic/least-developed-countries/list",
)
_LDC_AS_OF: Final = "2026-09-01"
_LDC_ISO3_CODES: Final[frozenset[str]] = frozenset(
    {
        "AFG", "AGO", "BDI", "BEN", "BFA", "BGD", "CAF", "COD", "COM", "DJI",
        "ERI", "ETH", "GIN", "GMB", "GNB", "HTI", "KHM", "KIR", "LAO", "LBR",
        "LSO", "MDG", "MLI", "MMR", "MOZ", "MRT", "MWI", "NER", "NPL", "RWA",
        "SDN", "SEN", "SLB", "SLE", "SOM", "SSD", "TCD", "TGO", "TLS", "TUV",
        "TZA", "UGA", "YEM", "ZMB",
    }
)  # fmt: skip
"""44 members, verified against both `_LDC_SOURCE_URLS` as of `_LDC_AS_OF`.
Known upcoming moves, none yet effective as of `_LDC_AS_OF`: Bangladesh, Lao
PDR, and Nepal graduate 2026-11-24 (UNGA resolution A/RES/76/8, adopted
2021-11-24); Solomon Islands in 2027; Cambodia and Senegal in 2029. Sao Tome
and Principe (STP) graduated 2024-12-06 -- already excluded from this list,
not a future move."""

_LDC_VERSION_LABEL: Final = "ldc-2024review"
_LDC_LABEL: Final = "Least Developed Countries"
_OTHER_DEVELOPING_LABEL: Final = "Other Developing Countries"
_UNALLOCATED_LABEL: Final = "Regional / Multi-country Unallocated"
_UNCLASSIFIED_LABEL: Final = "Unclassified"

_WB_INCOME_RESOURCE_URL: Final = (
    "https://ddh-openapi.worldbank.org/resources/DR0095333/download"
)
"""World Bank "Country and Lending Groups" downloadable workbook, FY27
(published 2026-07-01, based on 2025 GNI per capita, Atlas method)."""
_WB_VERSION_LABEL: Final = "wb-fy27"
_WB_SHEET_NAME: Final = "List of economies"
_WB_VALID_INCOME_GROUPS: Final = frozenset(
    {"Low income", "Lower middle income", "Upper middle income", "High income"}
)
"""Filters the workbook's per-economy rows from its regional/income-group
aggregate rows (e.g. "East Asia & Pacific"), which carry a blank Income
group cell."""

_INCOME_UNCLASSIFIED_ISO3: Final[frozenset[str]] = frozenset(
    {"SHN", "MSR", "COK", "NIU", "TKL", "WLF"}
)
"""Saint Helena, Montserrat, Cook Islands, Niue, Tokelau, Wallis and Futuna --
non-self-governing territories the World Bank publishes no independent GNI
classification for. Verified: these six are absent from the WB workbook's
income-classified rows every time this script has been run; if a future WB
release starts classifying one, `fetch_wb_income_table` picks it up as a
real income group automatically and this constant becomes a no-op for it,
not a conflict."""


def fetch_wb_income_table(
    *, resource_url: str = _WB_INCOME_RESOURCE_URL
) -> pd.DataFrame:
    """Fetch and parse the World Bank's live income-classification workbook.

    Args:
        resource_url: The workbook's direct-download URL.

    Returns:
        A frame with `iso3` and `income_group` columns, one row per
        individually classified economy (aggregate/region rows, which carry
        no income group, are dropped) -- 218 rows as of `_WB_VERSION_LABEL`.
    """
    response = requests.get(resource_url, timeout=30)
    response.raise_for_status()
    workbook = pd.read_excel(io.BytesIO(response.content), sheet_name=_WB_SHEET_NAME)
    classified = workbook[workbook["Income group"].isin(_WB_VALID_INCOME_GROUPS)]
    return pd.DataFrame(
        {
            "iso3": classified["Code"].to_numpy(),
            "income_group": classified["Income group"].to_numpy(),
        }
    )


def derive_region_map(
    *, years: int | range | None = None
) -> tuple[dict[int, str], dict[int, list[str]]]:
    """Derive `recipient_code -> region_name` from TOSSD's own published data.

    Args:
        years: Years to fetch (see `tossd_reader.fetch.get_tossd_raw`).
            `None` (the default) fetches the packaged known-years set.

    Returns:
        A 2-tuple: `{recipient_code: region_name}` for every code that maps
        to exactly one region across the fetched years, and
        `{recipient_code: [region_name, ...]}` for any code that doesn't (a
        genuine conflict to report, not resolve by guessing -- see
        `build_recipient_groups_table`).
    """
    raw = fetch.get_tossd_raw(years=years)
    pairs = raw[["recipientcode", "regionnamee"]].dropna()
    pairs = pairs[pairs["recipientcode"].astype(str).str.strip() != ""]
    pairs["recipientcode"] = pairs["recipientcode"].astype(int)

    grouped = pairs.groupby("recipientcode")["regionnamee"].unique()
    mapping: dict[int, str] = {}
    conflicts: dict[int, list[str]] = {}
    for code, regions in grouped.items():
        if len(regions) == 1:
            mapping[int(code)] = str(regions[0])
        else:
            conflicts[int(code)] = sorted(str(r) for r in regions)
    return mapping, conflicts


def build_recipient_groups_table(
    *,
    income_table: pd.DataFrame,
    region_map: dict[int, str] | None,
    ldc_iso3: frozenset[str] = _LDC_ISO3_CODES,
) -> pd.DataFrame:
    """Combine every source into the final packaged table (pure, no I/O).

    Args:
        income_table: `fetch_wb_income_table`'s output.
        region_map: `derive_region_map`'s mapping half, or `None` to ship
            without a `region` column (the conflict case).
        ldc_iso3: The verified LDC ISO3 set.

    Returns:
        One row per code in the packaged `recipient.csv`, sorted by code:
        `recipient_code`, `ldc_group`, `income_group`, and `region` (omitted
        entirely when `region_map` is `None`).
    """
    recipient_codelist = codelists.load_codelist("recipient")
    income_by_iso3 = dict(
        zip(income_table["iso3"], income_table["income_group"], strict=True)
    )

    rows: list[dict[str, object]] = []
    for _, entry in recipient_codelist.iterrows():
        code = int(entry["code"])
        iso3 = entry["iso3"] if pd.notna(entry["iso3"]) else None

        if iso3 is None:
            ldc_group = _UNALLOCATED_LABEL
            income_group = _UNALLOCATED_LABEL
        else:
            ldc_group = _LDC_LABEL if iso3 in ldc_iso3 else _OTHER_DEVELOPING_LABEL
            if iso3 in _INCOME_UNCLASSIFIED_ISO3:
                income_group = _UNCLASSIFIED_LABEL
            else:
                income_group = income_by_iso3.get(iso3)
                if income_group is None:
                    raise ValueError(
                        f"recipient code {code} (iso3={iso3!r}) has no World Bank "
                        "income classification and isn't in "
                        "_INCOME_UNCLASSIFIED_ISO3 -- a genuinely new gap, not "
                        "one of the six known non-self-governing territories. "
                        "Investigate before adding it to that constant blindly."
                    )

        row: dict[str, object] = {
            "recipient_code": code,
            "ldc_group": ldc_group,
            "income_group": income_group,
        }
        if region_map is not None:
            row["region"] = region_map.get(code)
        rows.append(row)

    table = pd.DataFrame(rows).sort_values("recipient_code").reset_index(drop=True)
    if region_map is not None and table["region"].isna().any():
        missing = table.loc[table["region"].isna(), "recipient_code"].tolist()
        raise ValueError(
            f"recipient code(s) {missing} have no region_name in the fetched "
            "TOSSD data -- either a new codelist entry with no activity yet, "
            "or a fetch that didn't cover enough years."
        )
    return table


def write_recipient_groups(
    table: pd.DataFrame,
    *,
    output_dir: Path,
    fetched_at: datetime,
) -> None:
    """Write `table` and its version stamp to `output_dir`, LF-terminated."""
    output_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(output_dir / _OUTPUT_CSV_NAME, index=False, lineterminator="\n")

    version = f"{_LDC_VERSION_LABEL}/{_WB_VERSION_LABEL}"
    payload = {
        "version": version,
        "fetched_at": fetched_at.isoformat(),
        "sources": {
            "ldc": _LDC_SOURCE_URLS[0],
            "income": _WB_INCOME_RESOURCE_URL,
            "region": "derived from the packaged TOSSD archive's own "
            "(recipient_code, region_name) pairs",
        },
    }
    (output_dir / _OUTPUT_VERSION_NAME).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n"
    )


def diff_recipient_groups_files(baseline_csv: Path, candidate_csv: Path) -> list[str]:
    """Diff two `recipient_groups.csv` files, sorted by every column first.

    Pure, offline comparison -- no network -- so this (and the CI drift
    check it backs) is testable against two prepared temp files.
    """
    baseline = _read_normalised(baseline_csv)
    candidate = _read_normalised(candidate_csv)
    if list(baseline.columns) != list(candidate.columns):
        return [
            f"columns differ: {list(baseline.columns)} vs {list(candidate.columns)}"
        ]
    if baseline.equals(candidate):
        return []
    return [
        f"content differs ({len(baseline)} baseline rows vs "
        f"{len(candidate)} candidate rows)"
    ]


def _read_normalised(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    columns = list(frame.columns)
    return frame.sort_values(columns).reset_index(drop=True)


def _run_build(output_dir: Path) -> int:
    income_table = fetch_wb_income_table()
    region_map, conflicts = derive_region_map()
    if conflicts:
        print(
            "region conflicts found -- shipping ldc_group/income_group only, "
            "region column omitted:",
            file=sys.stderr,
        )
        for code, regions in sorted(conflicts.items()):
            print(f"- recipient_code {code}: {regions}", file=sys.stderr)
        region_map = None

    table = build_recipient_groups_table(
        income_table=income_table, region_map=region_map
    )
    write_recipient_groups(table, output_dir=output_dir, fetched_at=datetime.now(UTC))
    print(f"{len(table)} recipient codes written to {output_dir}", file=sys.stderr)
    return 0


def _run_check(baseline_csv: Path, candidate_csv: Path) -> int:
    diffs = diff_recipient_groups_files(baseline_csv, candidate_csv)
    if not diffs:
        print("No recipient-groups drift detected.")
        return 0
    print("recipient-groups drift detected:")
    for diff in diffs:
        print(f"- {diff}")
    return 1


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. See module docstring for the two modes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_PACKAGED_DATA_DIR,
        help="Where to write the built table (default: the packaged _data/).",
    )
    parser.add_argument(
        "--check",
        nargs=2,
        metavar=("BASELINE_CSV", "CANDIDATE_CSV"),
        help="Pure offline diff between two recipient_groups.csv files; exits 1 on drift.",
    )
    args = parser.parse_args(argv)

    if args.check is not None:
        baseline_csv, candidate_csv = (Path(value) for value in args.check)
        return _run_check(baseline_csv, candidate_csv)

    return _run_build(args.output_dir)


if __name__ == "__main__":
    raise SystemExit(main())
