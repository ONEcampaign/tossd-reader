# About pillars and aggregate rows

Total Official Support for Sustainable Development (TOSSD) is an international statistical framework established by the International Forum on TOSSD (IFT) to track all officially supported financial resources for the Sustainable Development Goals (SDGs). The framework structures development finance into two distinct pillars based on delivery mechanisms and beneficiary scope, with Pillar I capturing cross-border flows to developing countries and Pillar II capturing regional and global expenditures addressing international public goods and global challenges.

## Pillar I cross-border flows to developing countries

Pillar I captures resource transfers provided directly to developing countries and territories on the official TOSSD recipient list. Every transaction in Pillar I associates with a designated recipient partner country or territory.

These cross-border flows encompass bilateral development projects, official grants, concessional and non-concessional loans, equity investments, and technical cooperation. The defining characteristic of Pillar I is the direct cross-border transfer of resources to support development priorities within the recipient economy.

## Pillar II global public goods and regional expenditures

Pillar II captures expenditures that generate shared regional or global benefits where financial resources are not transferred to a single recipient country. These activities support sustainable development through two operational sub-pillars recorded in `tossd_subpillar`:

- Pillar II.A (coded as `21`) covers regional and global public goods. This includes transnational climate change mitigation, biodiversity conservation, research and development for infectious diseases, pandemic preparedness, and international peacekeeping.
- Pillar II.B (coded as `22`) covers support to international and multilateral mechanisms, global programmes, and provider-country expenditures that support sustainable development frameworks.

## Sub-pillar implementation timeline

Sub-pillar classification phased in gradually across reporting cycles. In the 2022 dataset, sub-pillar tagging appeared in 24 activities out of 128,923 Pillar II records (0.02% coverage). In 2023, reporting providers tagged 50.6% of Pillar II activities with sub-pillar codes. In 2024, coverage reached 99.1% across 155,908 Pillar II activities.

Because sub-pillar tagging was established incrementally, longitudinal analysis by sub-pillar is fully consistent from 2024 onward. Data for 2023 provides partial sub-pillar attribution, while data from 2019 through 2022 captures Pillar II as a unified total.

`get_tossd()` reflects this reporting history. Supplying a sub-pillar filter with an explicit year prior to 2023 raises `InvalidPillarError`. When querying without year constraints (`years=None`), sub-pillar filters select records from 2023 onward and emit an informational warning. Queries that examine total Pillar II volume can pass `pillars=2` to capture all Pillar II activities regardless of sub-pillar classification.

## Aggregate provider records and double-counting protection

Published annual datasets combine activity-level project transactions from reporting providers with pre-computed summary rows. These summary records carry `provider_code == 0` and `provider_name == "Aggregate"`.

The TOSSD Secretariat includes aggregate records to represent high-level institutional totals where providers submitted summary figures. In the 2024 dataset, aggregate records represent 5,626 rows and account for USD 99.4 billion in disbursements, representing 20.0% of total reported disbursements (USD 497.7 billion).

The boolean `is_aggregate` column is present in every DataFrame returned by `get_tossd()`. The choice to include or exclude aggregate rows depends on the analytical objective:

- Calculating global headline volumes matching official IFT statistical publications requires retaining aggregate rows to capture all reported funding.
- Conducting provider-level rankings, recipient analyses, or sector-level aggregations requires filtering out aggregate rows (`~df["is_aggregate"]`) to prevent double-counting and isolate individual reporting institutions.

```python
import tossd_reader as tossd

df = tossd.get_tossd(years=2024, columns="minimal", units="usd_million")

# Exclude aggregate rows for provider rankings
df.loc[~df["is_aggregate"]].groupby("provider_name", observed=True)[
    "usd_disbursement"
].sum()

# Include all rows for headline totals matching official releases
df.groupby("provider_name", observed=True)["usd_disbursement"].sum()
```

## Bilateral core contributions and multilateral double-counting

Beyond publisher aggregate rows (`is_aggregate`), development finance analysis involves an architectural double-counting risk when combining bilateral and multilateral providers:

- **Provider perspective:** Measures a donor country's total financial effort, which includes bilateral cross-border transfers (Pillar I) plus core unearmarked contributions to multilateral organisations (Pillar II.B, aid modality `B02`).
- **Recipient perspective:** Measures resources received by developing countries, which includes bilateral cross-border transfers from donors plus the multilateral institutions' subsequent cross-border project disbursements (Pillar I).

Summing all bilateral providers and all multilateral institutions across both pillars counts the same funding twice: first as a bilateral core contribution to a multilateral fund, and second as a multilateral project disbursement in a partner country. When analysing cross-border finance received by partner countries, query Pillar I (`pillars=1`) and exclude core contributions (`modality_code != "B02"`).

## Provider-country expenditures in Pillar II

Pillar II includes expenditures incurred within provider territories that contribute to global sustainable development frameworks. The helper `pillar2_provider_costs()` isolates these domestic outlays by selecting Pillar II activities under sector 910 (administrative costs of donors) and sector 930 (domestic expenditures for refugees and asylum seekers in the host country). In the 2024 dataset, domestic provider costs represent USD 47.5 billion across 27,275 records, accounting for 35.6% of Pillar II gross disbursements.

Sector 720 records represent in-country humanitarian assistance delivered in recipient territories and remain distinct from domestic provider expenditures.

## Transitional Pillar 0 classifications

Datasets from 2020 through 2023 contain several hundred transactions recorded with pillar `0`. These records represent early submissions from provider entities prior to the uniform adoption of the two-pillar structure. Default queries (`pillars=None`) retain these rows to preserve the exact record count of the published source files. To select both standard pillars, leave `pillars` unset and filter the result with `df[df["tossd_pillar"].isin([1, 2])]`; alternatively, make separate queries with `pillars=1` and `pillars=2`.

## Concessionality criteria

TOSSD captures both concessional and non-concessional resource flows across all eligible instruments. The `concessionality_flag` field captures provider-reported concessionality status.

For debt instruments, the TOSSD methodology applies a uniform concessionality benchmark requiring a minimum 35% grant element calculated at a fixed 5% discount rate across loans and equity. By comparison, the OECD DAC grant-equivalent methodology for Official Development Assistance applies variable discount rates based on recipient income classifications (least developed countries, lower-middle-income countries, and upper-middle-income countries).

## Related

- [How to rank providers by disbursement](../how-to/rank-providers.md). Step-by-step aggregate exclusion with 2024 figures.
- [How to split Pillar II into its sub-pillars](../how-to/analyse-by-subpillar.md). The II.A and II.B filter, coverage figures, and warning behaviour.
- [How to measure Pillar II expenditures in the provider country](../how-to/provider-costs.md). Domestic provider cost filtering across sectors 910 and 930.
- [Helpers](../reference/helpers.md). Full parameter reference for `pillar2_provider_costs()`.
