# Export

The `export` function processes TOSSD activity records through schema casting and derived column generation, then writes the complete result to a compressed parquet file with a JSON provenance manifest. Exports retain all columns (`columns="all"`) and original units (`units="usd_thousand"` in USD thousands).

```python
import tossd_reader as tossd

path = tossd.export("exports", years=2019)
print(path)
```

```text
exports/tossd_2019.parquet
```

<!-- prettier-ignore -->
::: tossd_reader._export.export
    options:
      heading_level: 2

## Generated filenames

When `path` specifies a directory, `export` creates the directory if needed and writes `tossd_<years>.parquet` inside it. When `path` ends in `.parquet`, `export` writes directly to that file path, creating parent directories as needed.

The `<years>` segment reflects the resolved, sorted list of years:

- Single year: `tossd_2019.parquet`
- Contiguous range: `tossd_2019-2024.parquet`
- Non-contiguous set: `tossd_2019_2021_2024.parquet`

## Manifest fields

Each export writes a companion `<stem>.manifest.json` file beside the parquet file.

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

| Field | Type | Description |
| --- | --- | --- |
| `tossd_reader_version` | string | Package version that created the export file. |
| `schema_hash` | string | SHA-256 hash of packaged `schema.csv`, CRLF-normalised. |
| `years` | list of `int` | Sorted list of reporting years included in the export. |
| `row_count` | int | Total row count across all exported reporting years. |
| `created_at` | string | Export timestamp in ISO 8601 format (UTC). |
| `vintages` | object | Mapping of reporting year to source metadata (`etag` and `retrieved_at`). |

## Performance and memory

Exporting the default full dataset (`years=None`, covering 2019 through 2024) materialises approximately 2.4 million rows in memory as an Apache Arrow table before writing to disk. This requires roughly 2.1 GB of resident memory. Pass specific years to `years=` when working in memory-constrained environments.

## Next

- [Configuration, warnings, and errors](configuration.md). Cache settings, provenance handling, and error types.
- [Query](query.md). Interactive querying with `get_tossd`.
