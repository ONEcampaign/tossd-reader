# Verbs

`tossd_reader.verbs` aggregates a `get_tossd()`-shaped frame along one
dimension: `rank_entities`, `compare_years`, `sdg_totals`,
`keyword_totals`, `subpillar_breakdown`. Each takes a DataFrame as its
first argument, keyword-only arguments after that, and returns a new
DataFrame, leaving the input frame untouched. Every one of the five is
also a `df.tossd` accessor method. See [The `df.tossd`
accessor](#the-dftossd-accessor) below.

The same module carries two functions that read a frame's own state:
`get_provenance` returns its query record, and `reconcile` returns a
one-row read-out of the checks in [How to check a figure against the
published total](../how-to/reconcile-a-figure.md). Both take only `df`,
no keyword arguments, and both are `df.tossd` methods too, spelled
`provenance()` and `reconcile()`.

The five aggregation verbs share three conventions.

Each drops the `provider_code == 0` pseudo-aggregate rows before
aggregating, with `include_aggregates=False` as the default.
`get_tossd()` keeps them by default instead (see [Excluding aggregate
rows](query.md#excluding-aggregate-rows)), so the two defaults exist
to disagree on purpose. `get_tossd()` reproduces the published records
in full, and the verb layer sums only real providers' own activity.

`value=` names the amount column each verb sums, `"usd_disbursement"`
on most verbs and `"usd_disbursement_deflated"` on `compare_years`.

`df.attrs` propagates. Every verb copies the input frame's `attrs`
onto its result.

`top=` and `share_pct` vary by verb:

| verb                  | `top=` | `share_pct` |
| --------------------- | ------ | ----------- |
| `rank_entities`       | yes    | yes         |
| `sdg_totals`          | yes    | yes         |
| `subpillar_breakdown` | no     | yes         |
| `compare_years`       | no     | no          |
| `keyword_totals`      | no     | no          |

Where `share_pct` appears, it's a share of the included total, from 0
to 100, unrounded, computed over the full grouped result before any
`top=` truncates the rows. The total is taken after
`include_aggregates` and any filters already on the frame, not the
frame's grand total. A call without `top=` returns `share_pct` values
that sum to 100. A call with `top=` returns a truncated slice of that
ranking, and the column sums to less than 100.

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

## `get_provenance` in practice

```python
import tossd_reader as tossd
from pprint import pprint

df = tossd.get_tossd(years=2024, columns="analysis", units="usd_million")

pprint(tossd.get_provenance(df))
```

```text
{'created_at': '2026-09-02T12:19:04.952853+00:00',
 'package_version': '0.1.0',
 'query': {'columns': 'analysis',
           'filters': {},
           'include_aggregates': True,
           'pillars': None,
           'providers': None,
           'recipients': None,
           'refresh': False,
           'units': 'usd_million',
           'years': (2024,)},
 'years': {'2024': {'etag': '"69e6ac8d-5728379"',
                    'retrieved_at': '2026-09-02T12:10:44.031565+00:00',
                    'url': 'https://tossd.online/tossddata_2024.parquet'}}}
```

`get_provenance` returns a deep copy of `df.attrs["tossd_reader"]`, so
mutating the returned value never touches `df` itself. `get_tossd_raw()`
frames carry a minimal query dict (`refresh` and `years` only). A
`load_export()` frame carries the 3-key shape, no `query` key at all,
since an export is an unfiltered snapshot:

```python
loaded = tossd.load_export("exports/tossd_2019.parquet")

pprint(tossd.get_provenance(loaded))
```

```text
{'created_at': '2026-09-02T12:10:39.819913+00:00',
 'package_version': '0.1.0',
 'years': {'2019': {'etag': '"69e6ac86-347a653"',
                    'retrieved_at': '2026-09-02T12:10:39.379359+00:00'}}}
```

The key survives every verb and accessor call above. Each one copies
`df.attrs` onto its own result, so provenance survives `rank_entities`,
`explode_sdg`, and the rest. A plain pandas operation like `merge`,
`concat`, or some `groupby` calls can drop `attrs`. Calling
`get_provenance` on a frame that never carried the key raises:

```python
import pandas as pd

tossd.get_provenance(pd.DataFrame({"a": [1]}))
```

```text
ValueError: get_provenance() found no df.attrs['tossd_reader'] -- that
key is set by get_tossd(), get_tossd_raw(), and load_export(); a frame
built some other way (or a plain pandas operation that dropped attrs
along the way) carries none.
```

`df.tossd.provenance()` returns the identical dict and raises the same
error.

## `reconcile` in practice

```python
import tossd_reader as tossd

df = tossd.get_tossd(years=2024, columns="analysis", units="usd_million")

df.tossd.reconcile()
```

```text
unit                                 usd_million
n_aggregate_rows                            5626
aggregate_value                     99379.609718
aggregate_share_pct                    19.968737
usd_disbursement_total             497675.981441
usd_disbursement_deflated_total    497675.981441
pillars_present                           (1, 2)
year_min                                    2024
year_max                                    2024
n_years                                        1
has_provenance                              True
b02_core_contribution_value          6678.973842
b02_core_contribution_share_pct         1.342033
estimate_derived_value               2913.935663
estimate_derived_share_pct              0.585509
iso3_unmatched_value               147394.103994
iso3_unmatched_share_pct               29.616479
dtype: object
```

`reconcile` is a read-out, not a validator. Nothing here warns or
raises on what the data says, only on a frame that isn't
`get_tossd()`-shaped. Shares are of `df`'s own `usd_disbursement`
total, aggregate rows included, which is why `reconcile` takes no
`include_aggregates=`. Dropping the aggregate rows first would leave
`aggregate_share_pct` with nothing to measure.

`usd_disbursement_total` equals `usd_disbursement_deflated_total` here
because 2024 is the deflator base year. That equality is specific to a
2024-only frame, not a general property of `reconcile`'s output:

```python
multi = tossd.get_tossd(years=[2023, 2024], columns="analysis")

multi.tossd.reconcile()
```

```text
unit                                   usd_thousand
n_aggregate_rows                              11451
aggregate_value                    173447820.379903
aggregate_share_pct                       17.876098
usd_disbursement_total             970277829.269724
usd_disbursement_deflated_total    982043011.985994
pillars_present                           (0, 1, 2)
year_min                                       2023
year_max                                       2024
n_years                                           2
has_provenance                                 True
b02_core_contribution_value         12881067.080131
b02_core_contribution_share_pct            1.327565
estimate_derived_value               4259974.195728
estimate_derived_share_pct                 0.439047
iso3_unmatched_value               299091812.522857
iso3_unmatched_share_pct                  30.825378
dtype: object
```

`usd_disbursement_deflated_total`, `b02_core_contribution_value`,
`estimate_derived_value`, and `iso3_unmatched_value` read `pd.NA` when
their source column (`usd_disbursement_deflated`, `modality_code`,
`source_name`, `recipient_code` respectively) is missing from `df`.
`estimate_derived_value` sums `usd_disbursement` on rows whose
`source_name` contains "estimate" (case-insensitive). It's a heuristic
reading of the source name, not a packaged flag on the data.

`pillars_present` reflects whatever pillar values are actually in `df`.
The `(0, 1, 2)` above comes from real 2023 rows. See [Pillars and
aggregates](../about/pillars-and-aggregates.md) for what pillar 0
means.

See [How to check a figure against the published
total](../how-to/reconcile-a-figure.md) for reading these entries
against a specific published number.

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

<!-- prettier-ignore -->
::: tossd_reader.verbs.get_provenance
    options:
      heading_level: 2

<!-- prettier-ignore -->
::: tossd_reader.verbs.reconcile
    options:
      heading_level: 2

## The `df.tossd` accessor

Every `tossd_reader` query or helper import registers `df.tossd` as a
`pandas.DataFrame` accessor, a
`pd.api.extensions.register_dataframe_accessor` call that runs once, as
a side effect of importing `tossd_reader.query` or `tossd_reader.analysis`.
A frame built without touching either module in a fresh session (unpickled,
for instance) needs `import tossd_reader.analysis` first to register it.

`df.tossd` carries the five verbs above, `reconcile()`, plus `add_iso3`,
`add_recipient_group`, `add_instrument_group`, `extract_keywords`,
`explode_sdg`, and `filter_provider_costs` from [Helpers](helpers.md),
each taking the same keyword arguments as its module function.
`get_provenance` is the one exception to that naming pattern. Its
accessor method is `provenance()`, not `get_provenance()`. Three
methods exist only on the accessor: `summary()` (a one-row printable
summary of the frame), `exclude_aggregates()` (drops `is_aggregate` rows
on its own, outside any verb), and `groupby_entity(dimension=)` (a raw
`GroupBy` over `{dimension}_code`/`{dimension}_name`, for aggregations
none of the five verbs cover).

Every method above returns a DataFrame carrying its own `.tossd`, so
calls chain, with four exceptions. `provenance()` returns a `dict`.
`reconcile()` and `summary()` each return a `pandas.Series`.
`groupby_entity()` returns a `pandas.api.typing.DataFrameGroupBy`. A
chain stops at any of the four.

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
- [Check a figure against the published
  total](../how-to/reconcile-a-figure.md). Runs `reconcile()` against a
  real published number, then digs into individual checks.
