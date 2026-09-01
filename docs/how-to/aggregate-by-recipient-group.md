# How to aggregate disbursements by recipient country groups

Development finance analyses frequently evaluate spending directed to vulnerable country groups, including Least Developed Countries (LDCs), Low-Income Countries (LICs), and regional groupings such as Sub-Saharan Africa.

This recipe shows how to map recipient countries to standard country classifications while preserving regional and multi-country unallocated flows.

## Recipe

```python
import pandas as pd
import tossd_reader as tossd

# 1. Query Pillar I cross-border flows for 2024
df = tossd.get_tossd(years=2024, pillars=1, columns="analysis", units="usd_million")
df = df[~df["is_aggregate"]]

# 2. Add recipient ISO3 codes
df = tossd.add_iso3(df)

# 3. Define the recipient classification list (e.g. UN LDC ISO3 codes)
LDC_ISO3 = {
    "AFG", "AGO", "BDI", "BEN", "BFA", "BGD", "CAF", "COD", "COM", "DJI",
    "ERI", "ETH", "GIN", "GMB", "GNB", "HTI", "KHM", "KIR", "LAO", "LBR",
    "LSO", "MDG", "MLI", "MMR", "MOZ", "MRT", "MWI", "NER", "NPL", "RWA",
    "SDN", "SEN", "SLB", "SLE", "SOM", "SSD", "STP", "SYR", "TCD", "TGO",
    "TLS", "TUV", "TZA", "UGA", "YEM", "ZMB"
}

# 4. Classify recipient countries into analytical groups
def classify_recipient(row: pd.Series) -> str:
    iso = row["recipient_iso3"]
    if pd.isna(iso):
        return "Regional / Multi-country Unallocated"
    if iso in LDC_ISO3:
        return "Least Developed Countries (LDCs)"
    return "Other Developing Countries"

df["recipient_group"] = df.apply(classify_recipient, axis=1)

# 5. Calculate distribution by country group
summary = (
    df.groupby("recipient_group", observed=True)["usd_disbursement"]
    .agg(total_usd_million="sum", activity_count="count")
    .reset_index()
)
summary["share_pct"] = (
    summary["total_usd_million"] / summary["total_usd_million"].sum() * 100
).round(1)
summary["total_usd_million"] = summary["total_usd_million"].round(1)
summary
```

```text
                        recipient_group  total_usd_million  activity_count  share_pct
0      Least Developed Countries (LDCs)            72841.5          134208       20.0
1            Other Developing Countries           241832.2          249811       66.4
2  Regional / Multi-country Unallocated            49440.4           37644       13.6
```

## Regional and unallocated flows

Official TOSSD files include regional allocations (such as "Africa, regional" or regional infrastructure funds) that do not map to a single country ISO3 code. In 2024 Pillar I records, these regional flows account for USD 49.4 billion (13.6% of Pillar I disbursements).

Filtering with `df.dropna(subset=["recipient_iso3"])` removes these multi-country programs from the analysis. Classifying missing ISO3 values as "Regional / Multi-country Unallocated" preserves the complete financial envelope.

<!-- prettier-ignore -->
!!! warning "Heads up"
    Inner joins between `recipient_iso3` and external country reference tables silently drop regional flows. Use a left join or group regional codes explicitly before calculating total assistance shares.

## Next

- [Join TOSSD to other country datasets](join-other-datasets.md) for merging World Bank or IMF metrics using ISO3 codes.
- [Rank providers by disbursement](rank-providers.md) for disaggregating flows by donor institution.
