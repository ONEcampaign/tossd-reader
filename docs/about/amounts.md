# About the amount columns

Published TOSSD datasets record financial transactions across eight numeric amount fields, expressed in thousands of US dollars. The `minimal` column preset includes all eight fields. The `units=` argument on `get_tossd()` accepts `"usd_thousand"` (the default matching the published scale), `"usd_million"`, or `"usd"` for plain US dollars. The `unit` metadata column accompanies every DataFrame to record which scale is active.

```python
import tossd_reader as tossd

th = tossd.get_tossd(years=2024, columns="minimal")
us = tossd.get_tossd(years=2024, columns="minimal", units="usd")
print(round(th["usd_disbursement"].sum(), 1))
print(round(us["usd_disbursement"].sum(), 1))
print(us["unit"].iloc[0])
```

```text
497675981.4
497675981440.9
usd
```

`units=` accepts only those three scales.

```python
tossd.get_tossd(years=2024, units="usd_billion")
```

```text
ValueError: Unknown units 'usd_billion'; expected one of ('usd_thousand', 'usd_million', 'usd').
```

`export()` takes no `units=` argument. It always writes files at the published thousands scale, regardless of what unit a prior `get_tossd()` call used.

## Commitments and disbursements

TOSSD measures financial resources across two primary operational stages:

- `usd_commitment` records a formal institutional obligation undertaken during the reporting year to provide specified financial resources to a recipient or activity. Commitments represent forward-looking resource allocations, policy priorities, and signed agreements.
- `usd_disbursement` records the actual transfer of funds or placement of financial resources at the disposal of a recipient or executing partner during the reporting year.

Commitments and disbursements follow independent multi-year project lifecycles. An activity can report a commitment in its inaugural year followed by disbursements distributed across several subsequent years. Ongoing multi-year operations often report annual disbursements against commitments established in earlier reporting periods. In the 2024 dataset, 390,190 records report non-null commitments and 441,645 records report non-null disbursements out of 474,026 total activities.

## Current prices and constant prices

Each nominal financial field pairs with a deflated counterpart adjusted for price movements:

- `usd_commitment` and `usd_commitment_deflated`
- `usd_disbursement` and `usd_disbursement_deflated`
- `usd_reflow` and `usd_reflow_deflated`
- `usd_amount_mobilised` and `usd_amount_mobilised_deflated`

Nominal columns measure transactions at current prices and exchange rates during the reporting year. Deflated columns express transactions in constant 2024 US dollars using official deflators published alongside the dataset. In 2024, nominal and constant values match. For 2019 through 2023, deflated metrics adjust for global price inflation and currency movements relative to the 2024 base year.

Comparing multi-year disbursements in constant prices isolates real financial volume growth from inflation.

```python
import tossd_reader as tossd

df = tossd.get_tossd(
    years=range(2019, 2025),
    columns=["year", "usd_disbursement", "usd_disbursement_deflated"],
    units="usd_million",
)
df.groupby("year", observed=True)[
    ["usd_disbursement", "usd_disbursement_deflated"]
].sum().round(1)
```

```text
      usd_disbursement  usd_disbursement_deflated
year
2019          299878.4                   340219.0
2020          372334.6                   414304.5
2021          392156.9                   411967.9
2022          441608.0                   477946.4
2023          472601.8                   484367.0
2024          497676.0                   497676.0
```

Between 2019 and 2024, global TOSSD gross disbursements expanded by 66.0% in current prices (from USD 299.9 billion to USD 497.7 billion) and by 46.3% in constant 2024 prices (from USD 340.2 billion to USD 497.7 billion). The gap between current and constant values reflects price inflation over this five-year period.

## Gross disbursements, reflows, and net flows

`usd_disbursement` measures gross financial flows provided to recipients and international activities.

`usd_reflow` measures capital repayments returned to providers during the reporting year, including loan principal repayments, equity divestments, and returned grants. In the 2024 dataset, 215,264 records report non-null reflow values.

Net financial flows equal gross disbursements minus reflows (`usd_disbursement - usd_reflow`). Both metrics require alignment in the same unit scale and price basis before calculating net transfers.

## Mobilised private finance

`usd_amount_mobilised` records commercial private capital mobilised directly through official development finance interventions, such as syndicated loans, guarantees, credit lines, and direct equity participation. In the 2024 dataset, 1,693 activities report mobilised private finance.

TOSSD measures mobilised private finance as an indicator of private capital leverage in sustainable development. Official headline disbursement totals for Pillar I and Pillar II reflect official direct resources in `usd_disbursement`.

<!-- prettier-ignore -->
!!! warning "Keep mobilised private finance separate from disbursements"
    Keep `usd_amount_mobilised` separate from `usd_disbursement`. The `usd_amount_mobilised` field measures private commercial capital mobilised through official interventions, while `usd_disbursement` captures direct official fiscal transfers.

## Related

- [Columns, presets, and units](../reference/columns.md). Reference table of all eight amount columns and schema properties.
- [How to compare totals across years](../how-to/compare-years.md). Step-by-step instructions for constant-price time-series queries.
- [Why TOSSD totals rise](comparability.md). Analysis of inflation, provider expansion, and structural breaks across 2019 to 2024.
