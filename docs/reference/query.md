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

The `get_tossd` function applies schema casting, row filtering, and derived columns (`is_aggregate`, `unit`, `tossd_pillar`, `tossd_subpillar`) across requested reporting years.

The `get_tossd_raw` function loads requested annual files as published, preserving source column names, data types, and column ordering.

The `get_available_filters` function returns a dictionary of DataFrames for each filter dimension, including valid provider codes, recipient codes, pillar categories, and reporting years.

The `get_codelists_version` function returns the snapshot date of the packaged codelists.

### Resolving a provider name

The `providers` and `recipients` arguments accept official numeric codes, string codes, or full names matched case-insensitively against the packaged codelist. Numeric strings evaluate as codes first and fall back to name matching. Unresolved strings raise `UnknownCodeError` with closest matching names.

```python
import tossd_reader as tossd

tossd.get_tossd(years=2024, providers="Germny")
```

```text
UnknownCodeError: 'Germny' did not match any providers code or name in the packaged codelist. Closest matches: Germany.
```

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

## Next

- [Verbs](verbs.md). Aggregation functions (`rank_entities`, `compare_years`, and others) built on `get_tossd()` output.
- [Look up provider and recipient codes](../how-to/look-up-codes.md). Code lookup techniques and error handling.
- [Read the published columns unchanged](../how-to/read-published-columns.md). Compare `get_tossd_raw` with typed `get_tossd` outputs.
- [Columns, presets, and units](columns.md). The full column surface, including `FORCED_COLUMNS`.
- [Export](export.md). Write normalised parquet extracts with provenance manifests.
