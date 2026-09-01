# Verbs

`tossd_reader.verbs` aggregates a `get_tossd()`-shaped frame along one
dimension: `rank_entities`, `compare_years`, `sdg_totals`,
`keyword_totals`, `subpillar_breakdown`. Each takes a DataFrame as its
first argument, keyword-only arguments after that, and returns a new
DataFrame, leaving the input frame untouched. Every one of the five is
also a `df.tossd` accessor method. See [The `df.tossd`
accessor](#the-dftossd-accessor) below.

They share four conventions:

- **`include_aggregates=False` by default.** Each verb drops the
  `provider_code == 0` pseudo-aggregate rows before aggregating.
  `get_tossd()` keeps them by default instead (see [Excluding aggregate
  rows](query.md#excluding-aggregate-rows)), so the two defaults exist
  to disagree on purpose. `get_tossd()` reproduces the published records
  in full. The verb layer sums only real providers' own activity.
- **`value=` and `top=`.** `value=` names the amount column each verb
  sums (`"usd_disbursement"` on most verbs, `"usd_disbursement_deflated"`
  on `compare_years`). `top=` keeps the first N rows after ranking.
- **`share_pct` is a share of the included total.** 0-100, unrounded,
  summing to 100 across whatever rows a call returns. The total is taken
  after `include_aggregates` and any filters already on the frame, not
  the frame's grand total.
- **`df.attrs` propagates.** Every verb copies the input frame's `attrs`
  onto its result.

## `include_aggregates` in practice

```python
import tossd_reader as tossd

df = tossd.get_tossd(years=2024, columns="analysis", units="usd_million")

tossd.rank_entities(df, top=3, include_aggregates=True)[
    ["provider_code", "provider_name", "usd_disbursement", "share_pct", "rank"]
]
```

```text
 provider_code   provider_name  usd_disbursement  share_pct  rank
             0       Aggregate      99379.609718  19.968737     1
           302   United States      67695.935324  13.602412     2
           918 EU Institutions      58667.476757  11.788288     3
```

The `"Aggregate"` pseudo-row outranks every real provider. The default
excludes it:

```python
tossd.rank_entities(df, top=3)[
    ["provider_code", "provider_name", "usd_disbursement", "share_pct", "rank"]
]
```

```text
 provider_code   provider_name  usd_disbursement  share_pct  rank
           302   United States      67695.935324  16.996373     1
           918 EU Institutions      58667.476757  14.729604     2
             4          France      25444.627005   6.388365     3
```

`df.tossd.rank_entities(top=3)` returns the same frame. See [The
`df.tossd` accessor](#the-dftossd-accessor) below.

## Activity counts vs row counts

`keyword_totals`'s `n_rows` counts rows whose keyword mask matches. The
publisher's pre-split rows can carry different keyword tags from each
other, so one activity spread across several rows counts once per
matching row. `rank_entities`'s `n_activities` counts distinct
`tossd_id` values instead. The two measure different things. Read the
column name before comparing one verb's count against the other's.

<!-- prettier-ignore -->
::: tossd_reader.verbs.rank_entities
    options:
      heading_level: 2

<!-- prettier-ignore -->
::: tossd_reader.verbs.compare_years
    options:
      heading_level: 2

<!-- prettier-ignore -->
::: tossd_reader.verbs.sdg_totals
    options:
      heading_level: 2

<!-- prettier-ignore -->
::: tossd_reader.verbs.keyword_totals
    options:
      heading_level: 2

<!-- prettier-ignore -->
::: tossd_reader.verbs.subpillar_breakdown
    options:
      heading_level: 2

## The `df.tossd` accessor

Every `tossd_reader` query or helper import registers `df.tossd` as a
`pandas.DataFrame` accessor, a
`pd.api.extensions.register_dataframe_accessor` call that runs once, as
a side effect of importing `tossd_reader.query` or `tossd_reader.analysis`.
A frame built without touching either module in a fresh session (unpickled,
for instance) needs `import tossd_reader.analysis` first to register it.

`df.tossd` carries the five verbs above, plus `add_iso3`,
`add_recipient_group`, `add_instrument_group`, `extract_keywords`,
`explode_sdg`, and `filter_provider_costs` from [Helpers](helpers.md),
each taking the same keyword arguments as its module function. Three
methods exist only on the accessor: `summary()` (a one-row printable
summary of the frame), `exclude_aggregates()` (drops `is_aggregate` rows
on its own, outside any verb), and `groupby_entity(dimension=)` (a raw
`GroupBy` over `{dimension}_code`/`{dimension}_name`, for aggregations
none of the five verbs cover).

Every method returns a DataFrame carrying its own `.tossd`, so calls
chain:

```python
df.tossd.exclude_aggregates().tossd.rank_entities(top=5)
```

```text
 provider_code                provider_name  usd_disbursement  n_activities  share_pct  rank
           302                United States      67695.935324         61832  16.996373     1
           918              EU Institutions      58667.476757         85406  14.729604     2
             4                       France      25444.627005         14066   6.388365     3
           915 Asian Development Bank Group      18558.332668          4671   4.659428     4
           701                        Japan      17339.414452         17981   4.353395     5
```

How-to pages and the tutorial use this accessor spelling throughout.
These module functions are the canonical documentation. The accessor
methods delegate to them and raise the same errors on the same input.

## Next

- [Rank providers by disbursement](../how-to/rank-providers.md). Applies
  `rank_entities` end to end, including the `top=`/`share_pct` interplay.
- [Split disbursements across SDG goals](../how-to/analyse-by-sdg.md).
  Works through `sdg_totals`'s weighting against a real SDG-tagged query.
