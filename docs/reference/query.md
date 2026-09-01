# Query

TOSSD activity-level data, tracked by the International Forum on TOSSD (IFT), measures development finance across Pillar I (cross-border flows) and Pillar II (global public goods). The query module loads, filters, and types these records into pandas DataFrames.

| Function | Output | Purpose |
| --- | --- | --- |
| `get_tossd()` | `pandas.DataFrame` | Typed and filtered activity-level data. Primary entry point. |
| `get_available_filters()` | `dict[str, pandas.DataFrame]` | Dimension names, codes, and labels available for query filtering. |
| `get_codelists_version()` | `str` | Snapshot date of the packaged OECD and TOSSD codelists (ISO 8601 date). |
| `get_tossd_raw()` | `pandas.DataFrame` | Raw published data preserving original column names, types, and ordering. |

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

- [Look up provider and recipient codes](../how-to/look-up-codes.md). Code lookup techniques and error handling.
- [Read the published columns unchanged](../how-to/read-published-columns.md). Compare `get_tossd_raw` with typed `get_tossd` outputs.
- [Export](export.md). Write normalised parquet extracts with provenance manifests.
