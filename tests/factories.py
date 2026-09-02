"""Deterministic synthetic TOSSD parquet fixture generator.

This is a checked-in test utility, not test data itself: it reads the
packaged schema table (`tossd_reader/_data/schema.csv`) for column names,
order, and arrow types, and synthesizes rows that mimic the shape and
quirks of the real published files (empty-string string-nulls, real
double-column nulls, packed `sdgcode`/`keywords` fields, pseudo-aggregate
rows, pillar-0 placeholder rows, per-year sub-pillar coverage, and modality
case drift, all as observed in the published 2019-2024 files).
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

_PROVIDERS = [
    ("1", "Provider Alpha"),
    ("4", "Provider Beta"),
    ("18", "Provider Gamma"),
    ("301", "Provider Delta"),
    ("971", "Provider Epsilon"),
]
_AGGREGATE_PROVIDER = ("0", "Aggregate")

_RECIPIENTS = [
    ("55", "Recipient Turquia"),
    ("269", "Recipient Senegal"),
    ("189", "Recipient Kenya"),
    ("77", "Recipient Brazil"),
]
_REGIONS = ["Europe", "Africa", "Asia", "Americas"]

_MODALITY_CODES = [
    ("C01", "Projects"),
    ("D01", "Experts and other technical assistance"),
    ("K02", "Research and development (R&D)"),
    ("B02", "Core contributions to multilateral institutions"),
]

_FINANCE_INSTRUMENTS = [
    ("110", "Standard grant"),
    ("421", "Standard loan"),
    ("510", "Common equity"),
]
_FINANCING_ARRANGEMENTS = [
    ("FA02", "ISLAMIC FINANCE"),
    ("FA01", "STANDARD GRANT"),
]
_FRAMEWORKS = [
    ("FC01", "SOUTH-SOUTH CO-OPERATION"),
    ("FC02", "TRIANGULAR CO-OPERATION"),
]
_PURPOSES = [
    ("11240", "Early childhood education"),
    ("11420", "Higher education"),
    ("31120", "Agricultural development"),
]
_SECTORS = [
    ("110", "Education"),
    ("311", "Agriculture, Forestry, Fishing"),
]
_ISIC = [
    ("851", "Pre-primary and primary education", "P", "Education"),
    ("8530", "Higher education", "P", "Education"),
]
_MOB_LVLS = [
    "Guarantees",
    "Direct investment in companies and SPVs",
    "Simple co-financing",
]
_SOURCE_NAMES = ["CRS-TOSSD", "TOSSD", "CRS data used as proxy", "TOSSD estimate"]
_SDG_TOKENS = ["1", "4", "5", "10", "13", "16", "4.2", "6.b", "13.1", "1.a"]
_KEYWORD_TOKENS = [
    "#GENDER",
    "#MITIGATION",
    "#ADAPTATION",
    "#BIODIVERSITY",
    "COVID-19",
    "#COVID-19",
    "R&D",
]
_PILLAR_ZERO_YEARS = {2020, 2021, 2022, 2023}


def _load_schema() -> pd.DataFrame:
    """Load the packaged schema table, preserving the published column order."""
    schema_resource = importlib.resources.files("tossd_reader") / "_data" / "schema.csv"
    with importlib.resources.as_file(schema_resource) as schema_path:
        return pd.read_csv(schema_path, dtype=str, keep_default_na=False)


def _packed(
    rng: np.random.Generator, tokens: list[str], delimiter: str, empty_rate: float
) -> str:
    """Build a delimiter-packed field from a token vocabulary, sometimes empty."""
    if rng.random() < empty_rate:
        return ""
    n = int(rng.integers(1, min(4, len(tokens)) + 1))
    chosen = rng.choice(tokens, size=n, replace=False)
    return delimiter.join(str(token) for token in chosen)


def _subpillar(year: int, pillar: str, rng: np.random.Generator) -> str:
    """Derive a Tossdpillar2 value consistent with the year's rollout stage."""
    if pillar != "2":
        return pillar
    if year <= 2021:
        return "2"
    if year == 2022:
        return "21" if rng.random() < 0.05 else "2"
    return str(rng.choice(["2", "21", "22"], p=[0.4, 0.3, 0.3]))


def _amount(
    rng: np.random.Generator,
    *,
    null_rate: float = 0.2,
    allow_negative: bool = True,
) -> float | None:
    """Generate a plausible USD amount (double), occasionally a real null."""
    if rng.random() < null_rate:
        return None
    value = float(rng.lognormal(mean=4.0, sigma=1.5))
    if allow_negative and rng.random() < 0.02:
        value = -abs(value) * 0.01
    return round(value, 4)


def build_tossd_table(year: int, n_rows: int = 200, seed: int = 0) -> pa.Table:
    """Build a deterministic synthetic table mimicking one published TOSSD vintage.

    Args:
        year: Reporting year stamped onto every row (as `Year`).
        n_rows: Number of rows to generate.
        seed: Seed for the deterministic RNG; identical arguments always
            produce an identical table.

    Returns:
        A pyarrow Table with the exact column names, order, and arrow types
        of the packaged schema table (`tossd_reader/_data/schema.csv`).
    """
    schema_df = _load_schema()
    rng = np.random.default_rng(seed)

    n_aggregate = min(3, n_rows)
    n_pillar_zero = (
        min(2, max(n_rows - n_aggregate, 0)) if year in _PILLAR_ZERO_YEARS else 0
    )

    columns: dict[str, list[str | float | None]] = {
        name: [] for name in schema_df["published_name"]
    }

    for i in range(n_rows):
        is_aggregate = i < n_aggregate
        is_pillar_zero = n_aggregate <= i < n_aggregate + n_pillar_zero
        is_case_drift = year == 2024 and i == n_rows - 1

        provider_code, provider_name = (
            _AGGREGATE_PROVIDER if is_aggregate else _PROVIDERS[i % len(_PROVIDERS)]
        )
        recipient_code, recipient_name = _RECIPIENTS[i % len(_RECIPIENTS)]
        region_name = _REGIONS[i % len(_REGIONS)]

        modality_code, modality_name = _MODALITY_CODES[i % len(_MODALITY_CODES)]
        if is_case_drift:
            modality_code = modality_code.lower()

        finance_code, finance_name = _FINANCE_INSTRUMENTS[i % len(_FINANCE_INSTRUMENTS)]
        fa_code, fa_name = _FINANCING_ARRANGEMENTS[i % len(_FINANCING_ARRANGEMENTS)]
        fc_code, fc_name = _FRAMEWORKS[i % len(_FRAMEWORKS)]
        purpose_code, purpose_name = _PURPOSES[i % len(_PURPOSES)]
        sector_code, sector_name = _SECTORS[i % len(_SECTORS)]
        isic_code, isic_desc, isic_letter, isic_letter_desc = _ISIC[i % len(_ISIC)]

        if is_pillar_zero:
            tossd_pillar = "0"
            tossd_subpillar = "0"
        else:
            tossd_pillar = "1" if i % 2 == 0 else "2"
            tossd_subpillar = _subpillar(year, tossd_pillar, rng)

        project_title = (
            "Non-concessional flows: semi-aggregates"
            if is_aggregate
            else f"Synthetic project {i}"
        )
        concessionality = str(rng.choice(["0", "1", ""], p=[0.45, 0.45, 0.10]))
        maturity = str(int(rng.integers(0, 400))) if rng.random() > 0.5 else ""

        row: dict[str, str | float | None] = {
            "Year": str(year),
            "provider": provider_code,
            "ProviderNameE": provider_name,
            "agencyname_E": "" if rng.random() < 0.5 else f"Agency {i % 7}",
            "tossdid": f"{year}{i:06d}",
            "ProjectNumber": "" if rng.random() < 0.1 else f"{year}PN{i:05d}",
            "recipientcode": recipient_code,
            "recipientnamee": recipient_name,
            "regionnamee": region_name,
            "Channel": "" if rng.random() < 0.3 else "Provider Government",
            "ChannelCode": "" if rng.random() < 0.1 else "11000",
            "ParentChannelCode": "" if rng.random() < 0.1 else "11000",
            "parentchannelname_e": "",
            "otherPartners": "" if rng.random() < 0.9 else "Partner Org",
            "ChannelName_E": "" if rng.random() < 0.1 else "Provider Government",
            "Financeinstrument": finance_code,
            "FinanceinstrumentName_e": finance_name,
            "FinancingArrangement": "" if rng.random() < 0.9 else fa_code,
            "FinancingArrangementName_e": "" if rng.random() < 0.9 else fa_name,
            "FrameworkOfCollaboration": "" if rng.random() < 0.9 else fc_code,
            "FrameworkOfCollaborationName_e": "" if rng.random() < 0.9 else fc_name,
            "modality": modality_code,
            "Aid_T_Description_E": modality_name,
            "ProjectTitle": project_title,
            "ExternalLink": "" if rng.random() < 0.8 else "https://example.org/project",
            "sdgcode": _packed(rng, _SDG_TOKENS, ";", empty_rate=0.2),
            "SDG_goal_lvl_explanation": (
                "" if rng.random() < 0.9 else "Provider boilerplate explanation."
            ),
            "keywords": _packed(rng, _KEYWORD_TOKENS, "|", empty_rate=0.3),
            "purposecode": purpose_code,
            "purposename_e": purpose_name,
            "sector": sector_name,
            "sector3": sector_code,
            "ISICcode": isic_code,
            "ISICdescription": isic_desc,
            "ISIC_lvl": isic_letter,
            "ISICdescription_letter_lvl": isic_letter_desc,
            "ProjectDescription": (
                "" if rng.random() < 0.1 else f"Description for row {i}"
            ),
            "TossdPillar": tossd_pillar,
            "Tossdpillar2": tossd_subpillar,
            "USD_Commitment": _amount(rng),
            "USD_Commitment_defl": _amount(rng),
            "USD_disbursements": _amount(rng, null_rate=0.15),
            "USD_disbursement_defl": _amount(rng, null_rate=0.15),
            "USD_Reflows": _amount(rng, allow_negative=False),
            "USD_Reflow_defl": _amount(rng, allow_negative=False),
            "SalaryCost": _amount(rng, null_rate=0.85),
            "Concessionality": concessionality,
            "Maturity": maturity,
            "Mob_lvl": "" if rng.random() < 0.95 else _MOB_LVLS[i % len(_MOB_LVLS)],
            "USD_amountmobilised": _amount(rng, null_rate=0.85),
            "USD_amountmobilised_defl": _amount(rng, null_rate=0.85),
            "Mob_Origin": "",
            "Sourcename": _SOURCE_NAMES[i % len(_SOURCE_NAMES)],
        }

        for name, value in row.items():
            columns[name].append(value)

    # Guarantee at least one deterministic multi-token packed row and one
    # deterministic empty row for both sdgcode and keywords, regardless of
    # what the RNG happened to draw, so downstream tests can rely on them.
    forced_multi_idx = min(5, n_rows - 1)
    columns["sdgcode"][forced_multi_idx] = "13;10.a;1"
    columns["keywords"][forced_multi_idx] = "#GENDER|#MITIGATION"
    forced_empty_idx = min(6, n_rows - 1)
    if forced_empty_idx != forced_multi_idx:
        columns["sdgcode"][forced_empty_idx] = ""
        columns["keywords"][forced_empty_idx] = ""

    # Guarantee at least one deterministic pipe-packed FinancingArrangement/
    # FrameworkOfCollaboration row, mirroring the real published files
    # (verified against the cached 2019-2024 vintages: financing_arrangement_code
    # and framework_of_collaboration_code both carry pipe-packed multi-value
    # strings for a small share of rows, e.g. "FA02|FA03") -- otherwise a
    # small/fixed-seed fixture could go without one entirely, since the
    # per-row draw above only ever writes a single code or "".
    forced_packed_idx = min(7, n_rows - 1)
    if forced_packed_idx not in (forced_multi_idx, forced_empty_idx):
        columns["FinancingArrangement"][forced_packed_idx] = "FA01|FA02"
        columns["FinancingArrangementName_e"][forced_packed_idx] = (
            "STANDARD GRANT|ISLAMIC FINANCE"
        )
        columns["FrameworkOfCollaboration"][forced_packed_idx] = "FC01|FC02"
        columns["FrameworkOfCollaborationName_e"][forced_packed_idx] = (
            "SOUTH-SOUTH CO-OPERATION|TRIANGULAR CO-OPERATION"
        )

    arrays = []
    for _, field in schema_df.iterrows():
        name = field["published_name"]
        arrow_type = pa.string() if field["arrow_type"] == "string" else pa.float64()
        arrays.append(pa.array(columns[name], type=arrow_type))

    return pa.table(arrays, names=list(schema_df["published_name"]))


def write_tossd_fixture(
    path: str | Path,
    year: int,
    n_rows: int = 200,
    seed: int = 0,
) -> Path:
    """Write a single-row-group parquet fixture mimicking a published TOSSD vintage.

    Args:
        path: Destination file path.
        year: Reporting year to embed in the fixture.
        n_rows: Number of rows to generate.
        seed: Seed for the deterministic RNG.

    Returns:
        The path the fixture was written to.
    """
    table = build_tossd_table(year, n_rows=n_rows, seed=seed)
    destination = Path(path)
    pq.write_table(table, destination, row_group_size=table.num_rows)
    return destination
