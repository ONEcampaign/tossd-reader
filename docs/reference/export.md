# Export

_As of v0.1._

`export()` runs the same fetch, schema, and derived-column pipeline as `get_tossd`, then writes the result to parquet. `columns` is fixed at `"all"` and `units` at `"usd_thousand"`, as published. `export` writes every row of every requested year. The parquet file is written with `zstd` compression.

```python
import tossd_reader as tossd

tossd.export("exports", years=2019)
```

```
exports/tossd_2019.parquet
```

<!-- prettier-ignore -->
::: tossd_reader._export.export
    options:
      heading_level: 2

## Generated filenames

`path` given as a directory (created if it doesn't exist) writes `tossd_<years>.parquet` inside it. `path` given as an explicit filename ending in `.parquet` is used verbatim, creating its parent directories if needed.

`<years>` is built from the resolved, sorted year list.

- A single year is that year alone, e.g. `tossd_2019.parquet`.
- A contiguous run is `<first>-<last>`, e.g. `tossd_2019-2024.parquet`.
- A non-contiguous set is every year joined by `_`, e.g. `tossd_2019_2021_2024.parquet`.

## Manifest fields

Every export writes a `<stem>.manifest.json` sidecar alongside the parquet file.

```json
{
  "created_at": "2026-08-29T08:43:24.037603+00:00",
  "row_count": 290914,
  "schema_hash": "0a95f2c54852817a9db1a2174cffa5bd371d601e5d137a37cb27491182367df9",
  "tossd_reader_version": "0.1.0",
  "vintages": {
    "2019": {
      "etag": "\"69e6ac86-347a653\"",
      "retrieved_at": "2026-08-28T21:14:14.414671+00:00"
    }
  },
  "years": [
    2019
  ]
}
```

| Field                  | Type          | Description                                                                                                                                  |
| ---------------------- | ------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `tossd_reader_version` | string        | Package version that wrote the export.                                                                                                       |
| `schema_hash`          | string        | SHA-256 of the packaged `schema.csv`, CRLF-normalised.                                                                                       |
| `years`                | list of `int` | Exported years, sorted.                                                                                                                      |
| `row_count`            | int           | Total rows across all exported years.                                                                                                        |
| `created_at`           | string        | Export write time, ISO 8601, UTC.                                                                                                            |
| `vintages`             | object        | One entry per exported year. Both `etag` and `retrieved_at` are `null` when that year's provenance sidecar is missing or unreadable. |

## Next

- [Configuration, warnings, and errors](configuration.md). What a corrupt provenance sidecar does to the `vintages` fields above.
- [Query](query.md). `get_tossd`'s full filter and column arguments.
