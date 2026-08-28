# Query and export

As of v0.1.

| Function                                              | Use for                                                                                                                  |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `get_tossd()`                                         | Typed, filtered activity-level data. The default entry point.                                                            |
| `get_available_filters()` / `get_codelists_version()` | Which provider, recipient, sector, and pillar values are valid before filtering, and which codelist vintage is packaged. |
| `get_tossd_raw()`                                     | Publisher column names, dtypes, and column order, unfiltered.                                                            |
| `export()`                                            | A full, normalised parquet extract on disk, with a provenance manifest.                                                  |

`get_tossd` applies schema typing, row filters, and derived columns (`is_aggregate`, `unit`, the pillar tags) over one or more packaged years. `get_tossd_raw` fetches and concatenates the requested years as published, keeping publisher column names, dtypes, and column order. `export` runs the same fetch, schema, and derived-column pipeline as `get_tossd`, then writes the resulting arrow table straight to parquet instead of returning a `DataFrame`. It always uses `columns="all"` and applies no provider, recipient, or pillar filter. `get_available_filters` and `get_codelists_version` return codelist metadata, dimension names, codes, and the snapshot date. Call them to resolve a provider or recipient name before passing it to `providers=`/`recipients=`, or to check which codelist vintage is packaged.

## Resolving a misspelled provider

```python
import tossd_reader as tossd

tossd.get_tossd(years=2024, providers="Germny")
```

```
UnknownCodeError: 'Germny' did not match any providers code or name in the
packaged codelist. Closest matches: Germany.
```

`providers=` and `recipients=` match a string case-foldedly against the packaged codelist's `name` column. An unresolved token raises `UnknownCodeError` naming up to 5 closest matches.

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

<!-- prettier-ignore -->
::: tossd_reader._export.export
    options:
      heading_level: 2

## Behavior reference

`get_tossd` warns whenever a call returns an empty (but correctly typed) result. Several further warnings can recur across a session, and each is capped differently:

- Narrowing the default years for a sub-pillar filter (`pillars=21`/`22`/`"II.A"`/`"II.B"` with `years=None`) to 2023 onward. The package suppresses repeats of this one, printing it once per process.
- A sub-pillar filter whose resolved years include 2023, where tagging coverage is incomplete. The package suppresses repeats of this one too, once per process.
- An unmapped `parent_channel_code` value, when `parent_channel_name` is requested. The package suppresses repeats per distinct code, so each newly seen code still warns.
- The fetch layer serving a cached vintage when the network is unreachable, or when a requested year is no longer published (`get_tossd`, `get_tossd_raw`, and `export` all route through it). This one carries no package-level suppression. It's emitted on every affected call, and Python's default warning filter is what limits each distinct message, naming the year and vintage, to one line per process.
- Neither the HEAD nor the GET response carrying an `ETag` for a requested year, so that vintage is cached under an `unknown` key instead. The package suppresses repeats of this one per year, once per process. A vintage cached this way can't detect a republish on its own. Only `refresh=True` (or an enclosing `readerkit.refresh_scope()`) forces a fresh download for it.

`refresh=True` re-runs the publisher discovery sweep and forces a conditional GET for every requested year, on `get_tossd`, `get_tossd_raw`, and `export`. An enclosing `readerkit.refresh_scope()` has the same effect without passing `refresh=` at each call site.

`tossd_pillar`, `tossd_subpillar`, `is_aggregate`, and `unit` are present in every `get_tossd` result regardless of `columns=`. See [Pillars, aggregates, and breaks](../about/data-model.md) for pillar semantics and [Columns, presets, and units](../reference/columns.md) for what each preset includes.
