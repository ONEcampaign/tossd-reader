# Build a six-year Senegal disbursement trend

Tracking development finance flows to a partner country requires isolating real financial trends from price changes and reporting shifts. This tutorial evaluates six years of Total Official Support for Sustainable Development (TOSSD) data for Senegal, ranks bilateral and multilateral providers, and calculates real resource growth in constant prices.

## What you'll build

A validated ranking of Senegal's top external finance providers in 2024 and a 2019-2024 constant-price disbursement time series exported to CSV.

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

- How to query recipient-level activity data with `get_tossd()`.
- How to rank development finance providers by accounting for provider codes and aggregate rows.
- How to retrieve multi-year time series across all published vintages.
- How to compare nominal disbursement trends with publisher-supplied constant-price series.
- How to export reproducible summary data for analytical briefings.

## What you'll need

- Python 3.12 or newer, with `tossd-reader` and `pandas` installed.
- About ten minutes.
- Initial internet access to download published annual files (roughly 450MB total). Subsequent queries run from local cache.

## Step 1: Pull one year

Retrieve Senegal's 2024 reported activities to inspect data dimensions and verify query parameters.

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

Setting `columns="minimal"` selects 19 core fields covering activity identifiers, provider and recipient names, pillars, and financial amounts. Setting `units="usd_million"` converts values from thousands to millions of US dollars for direct alignment with headline reporting figures.

## Step 2: Rank the providers

Group by provider name to examine reported disbursement totals for Senegal.

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

In TOSSD data tracked by the International Forum on TOSSD (IFT) at tossd.online, provider code 0 represents aggregate multilateral estimates and confidential flows that are not assigned to an individual bilateral reporter. In 2024, aggregate rows represent 20.0% of global disbursements. When ranking specific reporting institutions, analysts isolate bilateral and multilateral providers by filtering with `~sen["is_aggregate"]`.

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

In published TOSSD datasets, some institutional families share a `provider_name` across distinct reporting entities. For example, the African Development Bank Group includes both the African Development Bank (provider code 913) and the African Development Fund (provider code 914). Grouping by both `provider_code` and `provider_name` keeps each reporting entity distinct.

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

Separating provider codes assigns 149.1 million USD specifically to provider code 913, with other group entities tracked on their own lines.

## Step 3: Extend to six years

To track resource flow trends over time, query the full six-year publication window from 2019 through 2024.

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
    Each annual dataset downloads during its initial query (55MB to 91MB per year). Subsequent queries for cached years execute immediately from disk.

Calculate total nominal disbursements by year to observe top-line funding trajectories.

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

Nominal values in `usd_disbursement` reflect price levels of the reporting year. The publisher-supplied `usd_disbursement_deflated` column expresses the values in constant 2024 US dollars. `tossd-reader` passes this column through without applying or identifying the underlying deflator methodology.

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

Between 2019 and 2024, total disbursements to Senegal rose 20.4% in current prices and 5.7% in constant prices. Price inflation accounts for the majority of observed nominal growth.

Multi-year analysis also requires checking for structural reporting changes. The `tossd.get_structural_breaks()` helper returns documented discontinuities across published TOSSD files.

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

These documented breaks provide context for cross-year comparisons. Citing structural shifts, such as provider base expansion from 97 to 130 reporters, helps readers interpret observed volume changes accurately.

## Step 5: Save the result

Export the deflated Senegal disbursement series to a CSV file for sharing with colleagues or incorporating into analytical reports.

```python
trend = multi.groupby("year", observed=True)["usd_disbursement_deflated"].sum().round(1)
trend.to_csv("senegal-disbursement-trend.csv")
```

The `trend` series contains the aggregated 2019-2024 constant-price figures for Senegal. When distributing analytical outputs, record the core methodological parameters alongside the data file.

- Year range (2019 to 2024).
- Aggregate row inclusion (included in headline country totals).
- Unit of measure (USD million via `units="usd_million"`).
- Price basis (constant 2024 USD via `usd_disbursement_deflated`).

## What you learned

- You queried recipient-level activity data using `get_tossd()`.
- You ranked development finance providers by accounting for provider codes and aggregate rows.
- You retrieved a multi-year time series across published TOSSD vintages.
- You evaluated resource flows in both nominal and constant prices.
- You exported a documented analytical summary to CSV.

## What's next

- [Why TOSSD totals rise](../about/comparability.md) explains provider base expansion and sub-pillar adoption behind the structural breaks table.
- [About the amount columns](../about/amounts.md) details the eight financial amount fields and their analytical applications.
- [Build an extract someone else can reproduce](reproducible-extract.md) demonstrates how to package analytical datasets into parquet files with provenance manifests.
