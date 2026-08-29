# About the amount columns

_As of v0.1._

Every published TOSSD file carries eight `usd_*` amount columns, in USD
thousands as published. All eight are marked `is_usd_thousand_amount=True` in
the packaged schema, all eight are in the `minimal` preset, and
`units="usd_million"` divides all eight by 1000. The `unit` column, forced
into every `get_tossd()` result, names which of the two states the rest of
the frame is currently in, so a frame passed between functions carries its
own units.

## Commitments and disbursements

A commitment (`usd_commitment`) is what a provider promised in a given year.
A disbursement (`usd_disbursement`) is what actually moved. The two are
reported independently. An activity can carry a commitment with no matching
disbursement that year, or a disbursement against a commitment made in an
earlier year. 2024 has 390,190 non-null `usd_commitment` rows against
441,645 non-null `usd_disbursement` rows, out of 474,026 rows total.

## Current and constant prices

Each nominal column (`usd_commitment`, `usd_disbursement`, `usd_reflow`,
`usd_amount_mobilised`) has a `_deflated` twin, with an identical non-null
count in every case. The nominal column is current prices, as reported. The
`_deflated` column restates the same flow in constant prices, with 2024 as
the base year. Every 2024 row's nominal and deflated value are identical,
and earlier years are adjusted relative to it.

A multi-year comparison in current prices measures inflation as well as
finance. Global disbursements from 2019 to 2024 are measured in USD million.

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

2019 to 2024 growth is 66.0% in current prices and 46.3% in constant prices.
The gap between the two is inflation over that period, priced into the
current-price column and stripped out of the constant-price one.

## Reflows and mobilised amounts

`usd_reflow` records returns against past finance: loan repayments,
recoveries, equity sales. 2024 carries 215,264 non-null rows. `usd_reflow`
is reported gross. A query that wants net flows subtracts it from
`usd_disbursement` itself, after confirming both are in the same price
basis and the same units.

`usd_amount_mobilised` records private finance a provider's activity brought
in alongside its own official contribution. 2024 carries 1,693 non-null
rows, a small slice of the 474,026-row file. The headline Pillar I/II
disbursement totals cover `usd_disbursement` only.

## Related

- [Columns, presets, and units](../reference/columns.md). Every column's
  dtype and preset membership, including the amount columns' `*` marker.
- [How to compare TOSSD totals across years](../how-to/compare-years.md).
  Puts the deflated column into a year-over-year comparison.
