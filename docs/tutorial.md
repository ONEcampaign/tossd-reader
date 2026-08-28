# Build a six-year picture of TOSSD flows to Senegal

> Pull six years of Senegal's TOSSD activity data and turn it into a
> year x pillar disbursement table.

## What you'll build

A table of Senegal's TOSSD disbursements by year and pillar, 2019 to 2024,
in USD millions:

```text
tossd_pillar    0       1      2
year
2019          NaN  2121.4   78.1
2020          NaN  2223.2   78.3
2021          NaN  2121.3  103.1
2022          0.0  2600.3  120.4
2023          0.8  2948.2  114.3
2024          NaN  2280.6  367.4
```

## What you'll learn

- How to pull a filtered, typed extract for one recipient and year
- How to total disbursements by TOSSD pillar
- How to rank providers without "Aggregate" rows distorting the result
- How to combine several years into one frame and pivot it by year and pillar
- How to save the result with pandas

## What you'll need

- Python 3.12 or newer.
- Familiarity with pandas: `groupby`, `sort_values`, `unstack`.
- About ten minutes. Most of that is a one-time download, not computation.

## Step 1: Install and pull one year

Install the package, then run a single filtered query. tossd-reader
downloads TOSSD's per-year parquet files from tossd.online on first use, so
this first call for 2024 touches the network.

```bash
pip install git+https://github.com/ONEcampaign/tossd-reader.git
```

```python
import tossd_reader as tossd

sen = tossd.get_tossd(
    years=2024,
    recipients="Senegal",
    columns="minimal",
    units="usd_million",
)
sen.shape
```

```text
(4802, 19)
```

`recipients="Senegal"` matches the name case-foldedly against the packaged
recipient codelist. `columns="minimal"` keeps 19 columns, enough for this
tutorial (`tossd_pillar` and `is_aggregate` are always included regardless of
the preset). `columns="all"` would return 55, the 53 published columns plus
2 computed ones. `units="usd_million"` divides the eight `usd_*` amount
columns by 1000, so disbursements read in millions instead of the published
thousands.

Sort by disbursement to see the largest activities:

```python
sen.sort_values("usd_disbursement", ascending=False)[
    ["provider_name", "tossd_pillar", "usd_disbursement"]
].head()
```

```text
                 provider_name  tossd_pillar  usd_disbursement
                 United States             1        116.142315
      Islamic Development Bank             2         88.318120
African Development Bank Group             1         81.158011
      Islamic Development Bank             1         75.029870
      Islamic Development Bank             2         70.976410
```

## Step 2: Total disbursements by pillar

Every row carries a `tossd_pillar` code, 1 or 2. Group by it to see how
Senegal's 2024 total splits between them:

```python
sen.groupby("tossd_pillar", observed=True)["usd_disbursement"].sum().round(1)
```

```text
tossd_pillar
1    2280.6
2     367.4
Name: usd_disbursement, dtype: float64
```

## Step 3: Rank providers

Group by `provider_name` to rank Senegal's largest providers the same way:

```python
# ❌ "Aggregate" isn't a provider, it's the publisher's pseudo-provider rows
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

`Aggregate` tops the list. TOSSD's publisher reports some activities under a
pseudo-provider named "Aggregate" (provider code 0) instead of the actual
funder, and `get_tossd` flags exactly those rows in the `is_aggregate`
column. They belong in Senegal's total, since they're real disbursements,
but they wreck a per-provider ranking. Filter them out first:

```python
# ✅ Filter is_aggregate before ranking providers
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

Japan now appears in fifth place. Any ranking grouped by `provider_name`
needs this filter. The pillar totals in Step 2 didn't, because aggregate
rows are real disbursements and belong in a pillar-level total.

## Step 4: Extend to all six years

Drop `years=2024` for a `range` covering 2019 through 2024, the full
published history:

!!! warning "Heads up"

    Step 1 already cached 2024. This query adds the other five years, and
    TOSSD publishes one parquet file per year, fetched in full on first
    request, about 450MB total across all six years. Every later query for
    these years reads the local cache instead, in well under a second.

```python
multi = tossd.get_tossd(
    years=range(2019, 2025),
    recipients="Senegal",
    columns="minimal",
    units="usd_million",
)
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

`range(2019, 2025)` stops before 2025, Python's usual exclusive-end
convention, so this covers 2019 through 2024, six years.

The total moves year to year, but don't read it as a trend on its own. The
number of reporting providers grew from 90 to 128 over this period, so part
of the increase is more of TOSSD's activity being counted, not more finance
moving. `tossd.get_structural_breaks()` lists the verified breaks by year.

Now pivot by both year and pillar:

```python
multi.groupby(["year", "tossd_pillar"], observed=True)["usd_disbursement"].sum().round(
    1
).unstack()
```

```text
tossd_pillar    0       1      2
year
2019          NaN  2121.4   78.1
2020          NaN  2223.2   78.3
2021          NaN  2121.3  103.1
2022          0.0  2600.3  120.4
2023          0.8  2948.2  114.3
2024          NaN  2280.6  367.4
```

The `0` column is a placeholder
pillar the publisher used for a handful of rows between 2020 and 2023, not a
third pillar. [About the data model](about/data-model.md) covers it and the
rest of the pillar and aggregate mechanics in full.

## Step 5: Save the result

Assign the pivot and write it out:

```python
pivot = (
    multi.groupby(["year", "tossd_pillar"], observed=True)["usd_disbursement"]
    .sum()
    .round(1)
    .unstack()
)
pivot.to_csv("senegal_tossd_by_pillar_2019_2024.csv")
```

Open `senegal_tossd_by_pillar_2019_2024.csv` and you'll see the same six
rows, ready for a spreadsheet or a chart.

## What you learned

- Pulled a filtered, typed frame for Senegal's 2024 TOSSD activity, 4,802 rows across 19 columns
- Totalled Senegal's 2024 disbursements by pillar, 2280.6 USD million in Pillar I against 367.4 in Pillar II
- Ranked providers with `is_aggregate` filtered out, which moved Japan into fifth place
- Combined all six published years, 2019 through 2024, into one frame and pivoted it by year and pillar
- Saved the pivot to `senegal_tossd_by_pillar_2019_2024.csv`

## What's next

- [About the data model](about/data-model.md): the full pillar, sub-pillar,
  and aggregate-row mechanics behind what you filtered here.
- [Work offline and manage the cache](how-to/work-offline.md): where the
  downloaded files live, and how to query without a network connection.
- [Query and export](reference/query.md): every `get_tossd` parameter, plus
  `export` for freezing a full reproducible extract to disk.
