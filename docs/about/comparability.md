# Why TOSSD totals rise

Three primary drivers account for aggregate growth in TOSSD data from 2019 through 2024: expansion of the reporting provider base, price inflation and currency movements, and progressive statistical classifications. Understanding each driver ensures accurate interpretation of multi-year development finance trends.

## Expansion of the reporting provider base

The number of institutions reporting to TOSSD expanded steadily every year from 2019 through 2024. Counting distinct `provider_code` values while excluding the aggregate pseudo-provider (code `0`):

```python
import tossd_reader as tossd

df = tossd.get_tossd(years=range(2019, 2025), columns=["year", "provider_code"])
df[df["provider_code"] != 0].groupby("year", observed=True)["provider_code"].nunique()
```

```text
year
2019     97
2020    109
2021    119
2022    129
2023    129
2024    130
Name: provider_code, dtype: int64
```

A significant portion of observed aggregate growth reflects new bilateral providers and multilateral institutions joining the reporting framework over time. To analyse funding trajectories among established donors, analysts can hold the provider cohort constant across target years, isolating institutional reporting expansion from underlying funding growth.

## Inflation and price adjustments

Nominal disbursement increases combine real resource transfers with price inflation. Between 2019 and 2024, global TOSSD gross disbursements rose 66.0% in current prices (USD 299.9 billion to USD 497.7 billion) and 46.3% in constant 2024 prices (USD 340.2 billion to USD 497.7 billion). Using the deflated amount columns (`usd_disbursement_deflated`) isolates real volume changes from price-level shifts.

## Progressive implementation of sub-pillar tagging

Sub-pillar classification within Pillar II was introduced in stages. In 2022, sub-pillar tagging appeared in 24 trace records (0.02% of Pillar II). In 2023, reporting providers tagged 50.6% of Pillar II activities. In 2024, coverage expanded to 99.1%.

Cross-year comparisons at the sub-pillar level provide consistent coverage from 2024 onward. Data for 2023 offers partial sub-pillar attribution, while data from 2019 through 2022 captures Pillar II as a unified total.

## Statistical classification updates

Statistical classifications evolve to capture emerging cooperation modalities. For example, modality code `K02` (research and development, or R&D) was introduced in the 2021 reporting cycle with 109 rows, expanding to 74,174 rows by 2024.

## Future methodological implementations

Methodological revisions adopted by the International Forum on TOSSD take effect in scheduled publication vintages. The Revised Debt Relief Methodology (RDRM) applies to vintages published from May 2026 onward.

## The packaged structural breaks reference

`get_structural_breaks()` provides a curated reference table documenting known discontinuities and coverage milestones across the 2019 to 2024 series:

```python
import tossd_reader as tossd

tossd.get_structural_breaks()
```

| Dimension     | Break Year | End Year | Description                                                                                                                                                         | Source                                        |
| :------------ | :--------- | :------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------ | :-------------------------------------------- |
| `sub_pillar`  | 2022       | 2022     | Sub-pillar tagging (Tossdpillar2 21/22) first appears as trace data: 24 rows in 2022                                                                                | audit of published files                      |
| `sub_pillar`  | 2023       | 2023     | Sub-pillar coverage ~51% of pillar-2 rows in 2023; ~99% in 2024 -- cross-year sub-pillar analysis is only clean from 2024                                           | audit of published files                      |
| `modality`    | 2021       | 2021     | Modality code K02 first appears in 2021                                                                                                                             | audit of published files                      |
| `reporters`   | 2019       | 2024     | Reporter base grows from 97 (2019) to 130 (2024) distinct provider codes, counting provider_code != 0; apparent growth in totals partly reflects reporting coverage | distinct provider_code in the published files |
| `methodology` | 2026       | 2026     | RDRM (revised debt-relief reporting methodology) takes effect May 2026 -- applies to vintages published from that date                                              | TOSSD Secretariat announcement                |

## Comparing TOSSD and Official Development Assistance (ODA)

Analysts working across international development datasets frequently compare TOSSD with OECD DAC Official Development Assistance (ODA). While both measure international development support, their architectural scope and measurement rules differ substantially:

| Dimension | TOSSD (International Forum on TOSSD) | ODA (OECD Development Assistance Committee) |
| :--- | :--- | :--- |
| **Scope and Pillars** | Pillar I (Cross-border flows) + Pillar II (Global Public Goods and domestic provider expenditures). | Cross-border concessional flows to DAC List recipients, plus eligible in-donor refugee and student costs. |
| **Concessionality** | Captures both concessional and non-concessional resource flows at face value (gross disbursements). | Concessional flows only; sovereign loans are measured using the Grant Equivalent methodology. |
| **Provider Coverage** | OECD DAC members, non-DAC sovereign providers (South-South and triangular providers), and multilateral institutions. | OECD DAC members, participating non-DAC countries, and designated multilateral organisations. |
| **Private Finance** | Measures officially mobilised private commercial investment separately via `usd_amount_mobilised`. | Tracked under Private Sector Instruments (PSI) and separate mobilisation reporting. |
| **Debt Discount Rate** | Applies a uniform 5% discount rate (minimum 35% grant element) across all recipient countries. | Applies differentiated discount rates by income group (6% for Upper-Middle, 7% for Lower-Middle, 9% for LDCs/LICs). |

## Related

- [How to compare totals across years](../how-to/compare-years.md). Multi-year queries in constant prices.
- [About pillars and aggregate rows](pillars-and-aggregates.md). Details on Pillar I, Pillar II, and aggregate records.
- [About the amount columns](amounts.md). Current prices, constant prices, and deflator calculations.
- [Helpers](../reference/helpers.md). Full reference for `get_structural_breaks()`.
