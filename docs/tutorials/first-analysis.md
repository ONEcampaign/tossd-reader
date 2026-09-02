# Build a six-year Senegal disbursement trend

Tracking development finance flows to a partner country requires isolating real financial trends from price changes and reporting shifts. This tutorial evaluates six years of Total Official Support for Sustainable Development (TOSSD) data for Senegal, ranks bilateral and multilateral providers, and calculates real resource growth in constant prices.

## What you'll build

A validated ranking of Senegal's top external finance providers in 2024, and a 2019-2024 constant-price disbursement time series for a consistent reporting cohort, exported to CSV.

```text
 provider_code                  provider_name  usd_disbursement  n_activities  share_pct  rank
           976       Islamic Development Bank             445.0           397       20.3     1
           302                  United States             367.6           625       16.8     2
             4                         France             306.4           510       14.0     3
           913 African Development Bank Group             149.1            29        6.8     4
           701                          Japan             116.7           174        5.3     5
```

```text
 year  usd_disbursement_deflated  n_providers  pct_change
 2019                     1483.8           49         NaN
 2020                     1744.8           49        17.6
 2021                     1689.7           49        -3.2
 2022                     2135.5           49        26.4
 2023                     1976.7           49        -7.4
 2024                     2090.1           49         5.7
```

## What you'll learn

- How to query recipient-level activity data with `get_tossd()`.
- How to check what a query returned with `df.tossd.summary()`.
- How to rank development finance providers with `rank_entities()`, which excludes aggregate rows and keeps same-name reporting entities apart by default.
- How to retrieve multi-year time series across all published vintages.
- How to compare nominal and constant-price trends year over year with `compare_years()`, holding the reporting cohort constant.
- How to export a documented analytical summary to CSV.

## What you'll need

- Python 3.12 or newer, with `tossd-reader` and `pandas` installed.
- About ten minutes.
- Initial internet access to download published annual files (roughly 450MB total). Subsequent queries run from local cache.

## Step 1: Pull one year

Retrieve Senegal's 2024 reported activities and check what the query returned.

```python
import tossd_reader as tossd

sen = tossd.get_tossd(
    years=2024, recipients="Senegal", columns="minimal", units="usd_million"
)
sen.tossd.summary()
```

```text
years                   (2024,)
n_rows                     4802
n_aggregate_rows             77
n_pillar_1_rows            4395
n_pillar_2_rows             407
unit                usd_million
n_columns                    19
dtype: object
```

Setting `columns="minimal"` selects 19 core fields covering activity identifiers, provider and recipient names, pillars, and financial amounts. Setting `units="usd_million"` converts values from thousands to millions of US dollars for direct alignment with headline reporting figures. `df.tossd.summary()` is a quick way to confirm a query landed the way you expected before analysing it: 4802 rows, split between pillars, with 77 rows already flagged `is_aggregate`. Step 2 explains why that flag matters.

## Step 2: Rank the providers

A plain `groupby` over `provider_name` looks like the fastest way to rank Senegal's funders.

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

Two problems sit in that table. `Aggregate` is provider code 0. It combines bilateral non-concessional flows and export credits reported without naming an individual bilateral reporter, and TOSSD Secretariat estimates built from OECD DAC reporting for providers such as Germany and the World Bank Group. The summary above already counted its 77 rows. And `provider_name` alone merges distinct reporting entities that share a family label. The African Development Bank Group covers the African Development Bank (provider code 913) and the African Development Fund (914). 164.1 combines both providers' totals into one row.

`rank_entities()` fixes both by default: it drops `is_aggregate` rows before summing, and groups by `(provider_code, provider_name)` so shared-name entities stay apart.

```python
ranked = sen.tossd.rank_entities(top=5).round(1)
print(ranked.to_string(index=False))
```

```text
 provider_code                  provider_name  usd_disbursement  n_activities  share_pct  rank
           976       Islamic Development Bank             445.0           397       20.3     1
           302                  United States             367.6           625       16.8     2
             4                         France             306.4           510       14.0     3
           913 African Development Bank Group             149.1            29        6.8     4
           701                          Japan             116.7           174        5.3     5
```

`n_activities` counts distinct activities per provider (`tossd_id`, excluding the placeholder used for bundled lines with no activity identifier), `share_pct` is each provider's share of the ranked total, and `rank` handles ties. Provider code 913 now carries its own 149.1 million, with the African Development Fund's contribution tracked on a separate row.

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

## Step 4: Switch to constant prices

Nominal values in `usd_disbursement` reflect price levels of the reporting year, so a year-over-year comparison mixes real funding changes with inflation. `compare_years()` sums one value column per year and reports the swing as `pct_change`. By default it also restricts every year to the `(provider_code, provider_name)` pairs that reported to Senegal in all six years, so a provider that only shows up in some years doesn't skew the comparison.

```python
nominal = multi.tossd.compare_years(value="usd_disbursement").round(1)
print(nominal.to_string(index=False))
```

```text
 year  usd_disbursement  n_providers  pct_change
 2019            1312.2           49         NaN
 2020            1584.1           49        20.7
 2021            1618.1           49         2.1
 2022            1987.1           49        22.8
 2023            1936.5           49        -2.5
 2024            2090.1           49         7.9
```

The 49 providers that reported to Senegal every year from 2019 to 2024 raised disbursements 59.3% in current prices. The publisher-supplied `usd_disbursement_deflated` column expresses the same activity records in constant 2024 US dollars, `compare_years()`'s own default value column.

```python
deflated = multi.tossd.compare_years().round(1)
print(deflated.to_string(index=False))
```

```text
 year  usd_disbursement_deflated  n_providers  pct_change
 2019                     1483.8           49         NaN
 2020                     1744.8           49        17.6
 2021                     1689.7           49        -3.2
 2022                     2135.5           49        26.4
 2023                     1976.7           49        -7.4
 2024                     2090.1           49         5.7
```

In constant prices, the same 49 providers raised disbursements 40.9%. The deflator, which adjusts for global price inflation and currency movements relative to the 2024 base year, accounts for roughly a third of the nominal growth.

`compare_years()` also attaches `get_structural_breaks()`'s rows for the years covered to `result.attrs["structural_breaks"]`, so a jump in the numbers above can be checked against a documented cause.

```python
print(deflated.attrs["structural_breaks"].to_string(index=False))
```

```text
 dimension  break_year  end_year                                                                                                                                                         description                                        source
sub_pillar        2022      2022                                                                                Sub-pillar tagging (Tossdpillar2 21/22) first appears as trace data: 24 rows in 2022                      audit of published files
sub_pillar        2023      2023                                           Sub-pillar coverage ~51% of pillar-2 rows in 2023; ~99% in 2024 -- cross-year sub-pillar analysis is only clean from 2024                      audit of published files
  modality        2021      2021                                                                                                                             Modality code K02 first appears in 2021                      audit of published files
 reporters        2019      2024 Reporter base grows from 97 (2019) to 130 (2024) distinct provider codes, counting provider_code != 0; apparent growth in totals partly reflects reporting coverage distinct provider_code in the published files
```

These breaks provide context for other TOSSD comparisons over this window. The reporter-base entry describes the global publisher's own reporting coverage. `compare_years()` already controls for Senegal's own cohort in the series above.

## Step 5: Save the result

Export the deflated comparison to a CSV file for sharing with colleagues or incorporating into analytical reports.

```python
deflated.to_csv("senegal-disbursement-trend.csv", index=False)
```

The exported file carries `year`, `usd_disbursement_deflated`, `n_providers`, and `pct_change` for 2019-2024. When distributing analytical outputs, record the core methodological parameters alongside the data file.

- Year range (2019 to 2024).
- Provider cohort (the 49 providers reporting to Senegal every year, `cohort="consistent"`, `compare_years()`'s default).
- Aggregate row inclusion (excluded, `compare_years()`'s `include_aggregates=False` default).
- Unit of measure (USD million via `units="usd_million"`).
- Price basis (constant 2024 USD via `usd_disbursement_deflated`, `compare_years()`'s default value column).

## What you learned

- You queried recipient-level activity data using `get_tossd()`.
- You checked a query's shape and composition with `df.tossd.summary()`.
- You ranked development finance providers with `rank_entities()`, excluding aggregate rows and keeping same-name entities apart.
- You retrieved a multi-year time series across published TOSSD vintages.
- You compared nominal and constant-price trends with `compare_years()`, holding Senegal's reporting cohort constant.
- You exported a documented analytical summary to CSV.

## What's next

- [How to rank providers by disbursement](../how-to/rank-providers.md) covers `dimension=` for ranking recipients or sectors instead of providers, and `include_aggregates=True` for when aggregate rows belong in the total.
- [How to compare TOSSD totals across years](../how-to/compare-years.md) covers `cohort="all"`, which counts every reporting provider each year rather than a consistent cohort.
- [Why TOSSD totals rise](../about/comparability.md) explains provider base expansion and sub-pillar adoption behind the structural breaks table.
- [Build an extract someone else can reproduce](reproducible-extract.md) demonstrates how to package analytical datasets into parquet files with provenance manifests.
