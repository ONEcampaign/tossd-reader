# Why TOSSD totals rise

_As of v0.1._

A 2019 to 2024 TOSSD growth figure combines three things: new finance, price inflation, and a reporter base that grew by about a third. The three are separable.

## The reporter base

The number of providers reporting to TOSSD grew every year from 2019 to 2024. Counting distinct `provider_code` values, excluding the aggregate pseudo-provider (code `0`):

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

Part of the year-over-year growth comes from the widening reporter base. Code `0`, the publisher-computed aggregate pseudo-provider, is out of this count. See [About pillars and aggregate rows](pillars-and-aggregates.md) for what that row is and when to keep it.

## The sub-pillar rollout

Sub-pillar tagging rolled out between 2022 and 2024, so a sub-pillar breakdown compared across years mixes a near-empty 2022, a half-tagged 2023, and a fully tagged 2024. See [About pillars and aggregate rows](pillars-and-aggregates.md) for the coverage figures and how `get_tossd()` handles them.

## Prices

A current-price comparison also measures inflation. Global disbursements rose 66.0% in current prices and 46.3% in constant prices between 2019 and 2024. See [About the amount columns](amounts.md) for the deflated columns and the full year-by-year table.

## What the breaks table is

`get_structural_breaks()` returns a curated five-row reference table of known discontinuities, maintained by the package from an audit of the published files. It ships inside the package as packaged data, so calling it needs no network access and returns the same five rows on every call. You read the table and cite it alongside a figure.

```text
  dimension  break_year  end_year                                                                                                                                                         description                                        source
 sub_pillar        2022      2022                                                                                Sub-pillar tagging (Tossdpillar2 21/22) first appears as trace data: 24 rows in 2022                      audit of published files
 sub_pillar        2023      2023                                           Sub-pillar coverage ~51% of pillar-2 rows in 2023; ~99% in 2024 -- cross-year sub-pillar analysis is only clean from 2024                      audit of published files
   modality        2021      2021                                                                                                                             Modality code K02 first appears in 2021                      audit of published files
  reporters        2019      2024 Reporter base grows from 97 (2019) to 130 (2024) distinct provider codes, counting provider_code != 0; apparent growth in totals partly reflects reporting coverage distinct provider_code in the published files
methodology        2026      2026                                              RDRM (revised debt-relief reporting methodology) takes effect May 2026 -- applies to vintages published from that date                TOSSD Secretariat announcement
```

The reporters row tracks continuous reporter-base growth through 2024, while the other rows mark discrete structural events.

## Related

- [Helpers](../reference/helpers.md). `get_structural_breaks()`'s full return value and column reference.
- [How to compare TOSSD totals across years](../how-to/compare-years.md). Applies the reporter-base and price checks above to a real year-over-year query.
