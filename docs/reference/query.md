# Query

_As of v0.1._

| Function                                              | Use for                                                                                                                  |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `get_tossd()`                                         | Typed, filtered activity-level data. The default entry point.                                                            |
| `get_available_filters()` / `get_codelists_version()` | Which provider, recipient, sector, and pillar values are valid before filtering, and which codelist vintage is packaged. |
| `get_tossd_raw()`                                     | Publisher column names, dtypes, and column order, unfiltered.                                                            |

`export()` writes a normalised, unfiltered parquet extract with a provenance
manifest. It has [its own page](export.md).

`get_tossd` applies schema typing, row filters, and derived columns
(`is_aggregate`, `unit`, the pillar tags) over one or more packaged years.
`get_tossd_raw` fetches and concatenates the requested years as published,
keeping publisher column names, dtypes, and column order. `get_available_filters`
and `get_codelists_version` return codelist metadata, dimension names, codes,
and the snapshot date. Call them to resolve a provider or recipient name
before passing it to `providers=`/`recipients=`, or to check which codelist
vintage is packaged. `pillars=` takes a single value. `providers=` and
`recipients=` each take a single value or an iterable of values.

## Resolving a provider name

```python
import tossd_reader as tossd

tossd.get_tossd(years=2024, providers="Germny")
```

```
UnknownCodeError: 'Germny' did not match any providers code or name in the packaged codelist. Closest matches: Germany.
```

`providers=` and `recipients=` match a string case-insensitively against the
packaged codelist's `name` column. A digit string is tried as a code first,
then falls back to a name match. An unresolved token raises
`UnknownCodeError` naming up to 5 closest matches.

## Looking up the pillar codelist

```python
import tossd_reader as tossd

print(tossd.get_available_filters()["pillar"].to_string(index=False))
```

```
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

- [How to look up provider and recipient codes](../how-to/look-up-codes.md).
  Resolve a name before filtering, with the full `UnknownCodeError` behaviour.
- [How to read the published columns unchanged](../how-to/read-published-columns.md).
  `get_tossd_raw` worked end to end, against `get_tossd` on the same year.
- [Export](export.md). Write a normalised, unfiltered parquet extract with a
  provenance manifest.
