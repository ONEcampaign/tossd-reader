# Build a six-year Senegal disbursement trend

> Query one recipient across six published years, rank its providers, and see how much of the trend survives once you account for inflation.

## What you'll build

A ranked table of Senegal's largest providers in 2024, and the same country's 2019-2024 disbursement trend in constant prices, saved to a CSV file at the end.

```text
provider_code  provider_name                 
976            Islamic Development Bank          445.0
302            United States                     367.6
4              France                            306.4
913            African Development Bank Group    149.1
701            Japan                             116.7
Name: usd_disbursement, dtype: float64
```

```text
year
2019    2504.1
2020    2549.7
2021    2329.0
2022    2929.2
2023    3132.2
2024    2648.0
Name: usd_disbursement_deflated, dtype: float64
```

## What you'll learn

- How to pull one year of `get_tossd` data for a single recipient.
- How to rank providers correctly, and why aggregate rows and colliding provider names both distort a naive ranking.
- How to extend a query across every published year.
- How to compare disbursements in current and constant prices.
- How to save a result as a CSV a colleague can trace back to its source query.

## What you'll need

- Python 3.12 or newer, tossd-reader installed, and enough pandas to read a `groupby`.
- About ten minutes.
- Roughly 450MB of downloads the first time each year in this tutorial runs. Every later query against the same years reads from the cache.

## Step 1: Pull one year

Query Senegal's 2024 activities first, before extending to six years.

```python
import tossd_reader as tossd

sen = tossd.get_tossd(
    years=2024, recipients="Senegal", columns="minimal", units="usd_million"
)
sen.shape
```

```text
(4802, 19)
```

`columns="minimal"` keeps 19 columns of IDs, names, pillars, and amounts instead of every published field. `units="usd_million"` divides the eight amount columns by 1000, so a total reads in the same units as a headline figure.

## Step 2: Rank the providers

Group by provider to see who disburses the most to Senegal.

```python
sen.groupby("provider_name", observed=True)["usd_disbursement"].sum().sort_values(
    ascending=False
).round(1).head(5)
```

```text
provider_name
Aggregate                         458.5
Islamic Development Bank          445.0
United States                     367.6
France                            306.4
African Development Bank Group    164.1
Name: usd_disbursement, dtype: float64
```

"Aggregate" is provider code 0, the TOSSD Secretariat's own pseudo-provider for finance it cannot attribute to a specific reporter. Across the full 2024 file it carries 20.0% of the global disbursement total, so it lands first in almost any provider ranking. Drop the aggregate row:

```python
sen[~sen["is_aggregate"]].groupby("provider_name", observed=True)[
    "usd_disbursement"
].sum().sort_values(ascending=False).round(1).head(5)
```

```text
provider_name
Islamic Development Bank          445.0
United States                     367.6
France                            306.4
African Development Bank Group    164.1
Japan                             116.7
Name: usd_disbursement, dtype: float64
```

Japan appears at 116.7. In the published 2024 file, "African Development Bank Group" covers two provider codes. Grouping by name alone adds their totals together. Group by `["provider_code", "provider_name"]` to keep them separate:

```python
sen[~sen["is_aggregate"]].groupby(["provider_code", "provider_name"], observed=True)[
    "usd_disbursement"
].sum().sort_values(ascending=False).round(1).head(5)
```

```text
provider_code  provider_name                 
976            Islamic Development Bank          445.0
302            United States                     367.6
4              France                            306.4
913            African Development Bank Group    149.1
701            Japan                             116.7
Name: usd_disbursement, dtype: float64
```

African Development Bank Group's total drops from 164.1 to 149.1 once the second code's rows get their own line.

## Step 3: Extend to six years

Repeat the same query across every published year, 2019 to 2024, to see the trend.

```python
multi = tossd.get_tossd(
    years=range(2019, 2025),
    recipients="Senegal",
    columns="minimal",
    units="usd_million",
)
multi.shape
```

```text
(26373, 19)
```

<!-- prettier-ignore -->
!!! warning "Heads up"
    Each year downloads its full published file the first time you request it, 55 to 91MB per year. Five more years means five more downloads.

```python
multi.groupby("year", observed=True)["usd_disbursement"].sum().round(1)
```

```text
year
2019    2199.6
2020    2301.5
2021    2224.4
2022    2720.8
2023    3063.4
2024    2648.0
Name: usd_disbursement, dtype: float64
```

## Step 4: Switch to constant prices

`usd_disbursement` is in the prices of the year it was reported. Swap it for `usd_disbursement_deflated` to compare years in constant prices instead.

```python
multi.groupby("year", observed=True)["usd_disbursement_deflated"].sum().round(1)
```

```text
year
2019    2504.1
2020    2549.7
2021    2329.0
2022    2929.2
2023    3132.2
2024    2648.0
Name: usd_disbursement_deflated, dtype: float64
```

Senegal's 2019 to 2024 disbursements rise 20.4% in current prices and 5.7% in constant prices. Price inflation accounts for most of the current-price growth.

Check for known discontinuities in how TOSSD was compiled across those years: `get_structural_breaks()` returns a reference table of known discontinuities in the published files:

```python
breaks = tossd.get_structural_breaks()
window = breaks[(breaks["break_year"] <= 2024) & (breaks["end_year"] >= 2019)]
print(window.to_string(index=False))
```

```text
 dimension  break_year  end_year                                                                                                                                                         description                                        source
sub_pillar        2022      2022                                                                                Sub-pillar tagging (Tossdpillar2 21/22) first appears as trace data: 24 rows in 2022                      audit of published files
sub_pillar        2023      2023                                                  Sub-pillar coverage ~51% in 2023, ~99% in 2024. Cross-year sub-pillar analysis is clean from 2024                      audit of published files
  modality        2021      2021                                                                                                                             Modality code K02 first appears in 2021                      audit of published files
 reporters        2019      2024 Reporter base grows from 97 (2019) to 130 (2024) distinct provider codes, counting provider_code != 0; apparent growth in totals partly reflects reporting coverage distinct provider_code in the published files
```

These four rows apply to every TOSSD query. You read the table and cite it alongside a figure.

## Step 5: Save the result

Save the constant-price trend to a CSV file someone else can open without rerunning the six queries.

```python
trend = multi.groupby("year", observed=True)["usd_disbursement_deflated"].sum().round(1)
trend.to_csv("senegal-disbursement-trend.csv")
```

`trend` is the six-year, deflated, Senegal-only series from Step 4. A CSV carries the numbers but not the query, so record a few facts alongside the file:

- Year range, 2019 to 2024.
- Aggregate rows, included.
- Unit, USD million (`units="usd_million"`).
- Price basis, constant prices (`usd_disbursement_deflated`).

## What you learned

- You pulled one year of `get_tossd` data for a single recipient.
- You ranked providers correctly, past the aggregate row and the colliding provider names that distort a naive ranking.
- You extended a query across every published year.
- You compared disbursements in current and constant prices.
- You saved a result as a CSV a colleague can trace back to its source query.

## What's next

- [Why TOSSD totals rise](../about/comparability.md) explains the reporter-base growth and sub-pillar rollout behind the structural-breaks table you just read.
- [About the amount columns](../about/amounts.md) covers the other six `usd_*` columns and when to reach for commitments or reflows instead of disbursements.
- [Build an extract someone else can reproduce](reproducible-extract.md) turns a query like this one into a parquet file and a manifest that pins the vintage it came from.
