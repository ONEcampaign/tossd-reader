# Query

TOSSD activity-level data, tracked by the International Forum on TOSSD (IFT), measures development finance across Pillar I (cross-border flows) and Pillar II (global public goods). The query module loads, filters, and types these records into pandas DataFrames.

| Function                  | Output                        | Purpose                                                                   |
| ------------------------- | ----------------------------- | ------------------------------------------------------------------------- |
| `get_tossd()`             | `pandas.DataFrame`            | Typed and filtered activity-level data. Primary entry point.              |
| `get_available_filters()` | `dict[str, pandas.DataFrame]` | Dimension names, codes, and labels available for query filtering.         |
| `get_codelists_version()` | `str`                         | Snapshot date of the packaged OECD and TOSSD codelists (ISO 8601 date).   |
| `get_tossd_raw()`         | `pandas.DataFrame`            | Raw published data preserving original column names, types, and ordering. |

For saving complete annual datasets to disk, see [Export](export.md).

## Usage

`get_tossd()` applies schema casting, row filtering, and derived columns (`is_aggregate`, `unit`, `tossd_pillar`, `tossd_subpillar`) across requested reporting years.

Provider codes, recipient codes, pillar categories, and reporting years each get their own DataFrame from `get_available_filters()`.

### Resolving a provider name

The `providers` and `recipients` arguments accept official numeric codes, string codes, or full names matched case-insensitively against the packaged codelist. Numeric strings evaluate as codes first and fall back to name matching. Unresolved strings raise `UnknownCodeError` with closest matching names.

```python
import tossd_reader as tossd

tossd.get_tossd(years=2024, providers="Germny")
```

```text
UnknownCodeError: 'Germny' did not match any providers code or name in the packaged codelist. Closest matches: Germany.
```

### Filtering to pillars 1 and 2

`pillars="standard"` filters to pillars 1 and 2 together, excluding the
pillar-0 placeholder rows a few years carry. Every other `pillars=`
value already excludes pillar-0. Only the default `pillars=None` keeps
it. See [Pillars and aggregate
rows](../about/pillars-and-aggregates.md#transitional-pillar-0-classifications)
for what those rows are.

```python
import tossd_reader as tossd

len(tossd.get_tossd(years=2023, columns="minimal"))
```

```text
442737
```

```python
len(tossd.get_tossd(years=2023, columns="minimal", pillars="standard"))
```

```text
442399
```

### Filtering by dimension

`filters=` narrows results by any of seven dimensions with no dedicated
keyword: `sector`, `purpose`, `channel`, `modality`, `finance_instrument`,
`financing_arrangement`, `framework_of_collaboration`. Each key takes a
single code, a single codelist name, or an iterable mixing both, resolved
the same way `providers=` and `recipients=` resolve their own values.
Filtering on more than one dimension at once narrows to rows matching
every dimension given.

```python
df = tossd.get_tossd(
    years=2024,
    columns="analysis",
    units="usd_million",
    filters={"sector": "I.2. Health"},
)
len(df)
```

```text
53064
```

```python
round(df["usd_disbursement"].sum(), 1)
```

```text
30794.2
```

Resolve a token before filtering with `tossd.codes.lookup(dimension,
token)` to check what a code or name matches (see [Codes](#codes)
below).

`financing_arrangement` and `framework_of_collaboration` match by token
membership. Real data packs multiple codes into one row (`"FA02|FA03"`),
so a filter for `"FA02"` also matches a packed row carrying it alongside
another code. The other five dimensions match by exact equality.

```python
fa = tossd.get_tossd(
    years=2024,
    columns="analysis",
    units="usd_million",
    filters={"financing_arrangement": "FA02"},
)
len(fa)
```

```text
11561
```

```python
print(fa["financing_arrangement_code"].value_counts().head(2).to_string())
```

```text
financing_arrangement_code
FA02         11557
FA02|FA03        4
```

`provider`, `recipient`, and `pillar` keys raise, naming the dedicated
keyword to use instead.

```python
tossd.get_tossd(years=2024, filters={"provider": "France"})
```

```text
ValueError: filters={'provider': ...} is not supported; use providers= directly.
```

An unrecognized dimension raises the same way, with closest matches.

```python
tossd.get_tossd(years=2024, filters={"sectors": "x"})
```

```text
ValueError: Unknown filters= dimension 'sectors'; expected one of channel, finance_instrument, financing_arrangement, framework_of_collaboration, modality, purpose, sector. Closest matches: sector.
```

An unresolved code or name raises `UnknownCodeError` with closest
matching names.

```python
tossd.get_tossd(years=2024, filters={"sector": "Helth"})
```

```text
UnknownCodeError: 'Helth' did not match any sector code or name in the packaged codelist. Closest matches: I.2. Health, I.2.a. Health, general, I.2.b. Basic health, I.3. Population policies/programmes and reproductive health.
```

A codelist entry can resolve cleanly and still match no row. The
packaged `sector` codelist carries sub-sector codes the published data
folds into their top-level group before publishing, so a sub-sector
filter resolves the code and returns nothing.

```python
tossd.get_tossd(years=2024, filters={"sector": "I.2.b. Basic health"})
```

```text
UserWarning: get_tossd's filters matched no rows; returning an empty (but correctly typed) frame. A codelist entry can sit at a finer granularity than the published data uses (sector sub-codes, for example, fold into their top-level group) -- compare against the column's own values, e.g. df['sector_code'].unique().
```

`purpose_code` carries that sub-sector-level detail instead. Filter on
`purpose` for questions finer than the 25 top-level sector groups.

`export()` takes no `filters=`. Its contract is an unfiltered snapshot
of a requested year (see [Export](export.md)). Build a filtered extract
with `get_tossd(filters=...)` and your own `DataFrame.to_parquet` call.

### Checking the forced columns

`FORCED_COLUMNS` names the columns present in every `get_tossd` result, regardless of `columns=`. Import it to check membership before building an explicit column list.

```python
import tossd_reader as tossd

tossd.FORCED_COLUMNS
```

```text
('year', 'tossd_pillar', 'tossd_subpillar', 'is_aggregate', 'unit')
```

An explicit `columns=` list still gets every forced column appended, so a multi-year query can group by `year` without naming it:

```python
df = tossd.get_tossd(
    years=[2023, 2024],
    columns=["provider_name", "usd_disbursement"],
    units="usd_million",
)
list(df.columns)
```

```text
['provider_name', 'usd_disbursement', 'year', 'tossd_pillar', 'tossd_subpillar', 'is_aggregate', 'unit']
```

```python
df.groupby("year", observed=True)["usd_disbursement"].sum().round(1)
```

```text
year
2023    472601.8
2024    497676.0
```

### Converting units

`units=` accepts `"usd_thousand"` (default, as published), `"usd_million"`, or `"usd"`. The `unit` column records whichever option ran. `export()` takes no `units=` and always writes the published scale.

```python
import tossd_reader as tossd

th = tossd.get_tossd(years=2024, columns="minimal")
us = tossd.get_tossd(years=2024, columns="minimal", units="usd")
print(round(th["usd_disbursement"].sum(), 1))
```

```text
497675981.4
```

```python
print(round(us["usd_disbursement"].sum(), 1))
```

```text
497675981440.9
```

An unrecognised value raises `ValueError` naming the valid options:

```python
tossd.get_tossd(years=2024, units="usd_billion")
```

```text
ValueError: Unknown units 'usd_billion'; expected one of ('usd_thousand', 'usd_million', 'usd').
```

### Excluding aggregate rows

`include_aggregates=True` (the default) keeps every row `get_tossd()`
loads, including the `provider_code == 0` pseudo-aggregate rows the
publisher reports alongside individual providers' own records, so the
output matches the published files in full. Pass
`include_aggregates=False` to drop them before anything downstream
aggregates the frame.

```python
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

```python
tossd.rank_entities(df, top=3, include_aggregates=False)[
    ["provider_code", "provider_name", "usd_disbursement", "share_pct", "rank"]
]
```

```text
 provider_code   provider_name  usd_disbursement  share_pct  rank
           302   United States      67695.935324  16.996373     1
           918 EU Institutions      58667.476757  14.729604     2
             4          France      25444.627005   6.388365     3
```

Passed to `get_tossd()` itself, `include_aggregates=False` removes the
same rows one step earlier, before any grouping or ranking runs. Every
`tossd_reader.verbs` function defaults `include_aggregates=False` on its
own (see [Verbs](verbs.md)), so a query already excluding aggregates
needs no further filtering before ranking, comparing, or totalling.

### Inspecting available filters

```python
import tossd_reader as tossd

filters = tossd.get_available_filters()
print(filters["pillar"].to_string(index=False))
```

```text
code        name  tossd_only
   1    Pillar I        True
   2   Pillar II        True
  21 Pillar II.A        True
  22 Pillar II.B        True
```

### Reading back query provenance

`get_tossd()` stamps `df.attrs["tossd_reader"]` with the call's own
provenance: the package version, a UTC timestamp, the normalised query,
and each fetched year's etag, retrieval time, and source URL.
`get_provenance(df)` (documented in [Verbs](verbs.md)) returns a deep
copy of that dict.

```python
import tossd_reader as tossd
from pprint import pprint

df = tossd.get_tossd(years=2024, columns="analysis", units="usd_million")
pprint(tossd.get_provenance(df))
```

```text
{'created_at': '2026-09-02T12:23:44.126187+00:00',
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
                    'retrieved_at': '2026-09-02T12:21:52.639935+00:00',
                    'url': 'https://tossd.online/tossddata_2024.parquet'}}}
```

`df.tossd.provenance()` returns the identical dict. `get_tossd_raw()`
sets the same key with a minimal query: `"years"` and `"refresh"`, the
only two keywords it takes.

`tossd_reader.verbs` functions and `df.tossd` accessor methods copy
`df.attrs` onto their results, so provenance survives `rank_entities`,
`explode_sdg`, and the rest. A plain pandas operation like `merge`,
`concat`, or some `groupby` calls can drop `attrs`. Read provenance
from the query result itself, or early.

### Passing filter arguments to `get_tossd_raw`

`get_tossd_raw` accepts only `years` and `refresh`. Any other keyword raises a `TypeError` naming it and pointing at `get_tossd`.

```python
import tossd_reader as tossd

tossd.get_tossd_raw(years=2024, providers="France")
```

```text
TypeError: get_tossd_raw() got unexpected keyword argument(s): providers. get_tossd_raw() only accepts years=/refresh=; for filtering, column selection, or unit conversion, use get_tossd() instead.
```

<!-- prettier-ignore -->
::: tossd_reader.query.get_tossd
    options:
      heading_level: 2

<!-- prettier-ignore -->
::: tossd_reader.codelists.get_available_filters
    options:
      heading_level: 2

<!-- prettier-ignore -->
::: tossd_reader.codelists.get_codelists_version
    options:
      heading_level: 2

<!-- prettier-ignore -->
::: tossd_reader.fetch.get_tossd_raw
    options:
      heading_level: 2

## Codes

`tossd_reader.codes` browses and resolves the packaged codelists that
`filters=`, `providers=`, and `recipients=` all draw on. `browse(dimension)`
returns one dimension's full codelist frame. `lookup(dimension, token)`
resolves a single code or name to the packaged code, through the same
resolution path a filter uses, so a lookup and a filter built from its
result always agree.

```python
import tossd_reader as tossd

m = tossd.codes.browse("modality")
print(m.head(4).to_string(index=False))
```

```text
code                                                                     name  tossd_only  in_published_data
   A                                                           Budget support        True              False
 A00                                                           Budget support        True               True
   B                       Core contributions and pooled programmes and funds        True              False
 B01 Core support to NGOs, other private bodies, PPPs and research institutes        True               True
```

Every dimension's frame carries `code`, `name`, and `tossd_only`. Every dimension but `pillar` also carries `in_published_data`, marking whether the code occurs in the published data. `provider` and `recipient` add `iso3`, and `sector` adds `source`.

`browse()` covers all 10 packaged dimensions, `pillar` included.
`lookup()` covers the 9 that resolve to a flat code, every `filters=`
dimension plus `provider` and `recipient`, and returns `int` for the
int-coded dimensions (`provider`, `recipient`, `sector`, `purpose`,
`channel`, `finance_instrument`) or `str` for the str-coded ones
(`modality`, `financing_arrangement`, `framework_of_collaboration`).

```python
tossd.codes.lookup("sector", "I.2.b. Basic health")
```

```text
122
```

```python
tossd.codes.lookup("provider", "France")
```

```text
4
```

```python
tossd.codes.lookup("modality", "B02")
```

```text
'B02'
```

`lookup()` excludes `pillar`. Resolve a pillar token like `"II.A"`
through `get_tossd(pillars=...)` instead.

```python
tossd.codes.lookup("pillar", "II.A")
```

```text
ValueError: Unknown lookup() dimension 'pillar'; expected one of provider, recipient, sector, purpose, channel, modality, finance_instrument, financing_arrangement, framework_of_collaboration. Pillar tokens ('1', 'II.A', ...) resolve via get_tossd(pillars=...), not codes.lookup().
```

<!-- prettier-ignore -->
::: tossd_reader.codes.browse
    options:
      heading_level: 2

<!-- prettier-ignore -->
::: tossd_reader.codes.lookup
    options:
      heading_level: 2

## Next

- [Verbs](verbs.md). Aggregation functions (`rank_entities`, `compare_years`, and others) built on `get_tossd()` output.
- [How to look up codes and names](../how-to/look-up-codes.md). Browse or resolve any dimension's codes with `tossd_reader.codes`, then pass the result to `get_tossd`.
- [Read the published columns unchanged](../how-to/read-published-columns.md). Compare `get_tossd_raw` with typed `get_tossd` outputs.
- [Columns, presets, and units](columns.md). The full column surface, including `FORCED_COLUMNS`.
- [Export](export.md). Write normalised parquet extracts with export manifests.
