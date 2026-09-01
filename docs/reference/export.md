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

<!-- prettier-ignore -->
```json
{
  "created_at": "2026-08-29T08:43:24.037603+00:00",
  "payload_sha256": "edb669d585db4108e63b9b73ed6a1a44e1eed200e4ce8a04506f62b34b234fca",
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

| Field                  | Type          | Description                                                                        |
| ---------------------- | ------------- | ---------------------------------------------------------------------------------- |
| `tossd_reader_version` | string        | Package version that created the export file.                                      |
| `schema_hash`          | string        | SHA-256 hash of packaged `schema.csv`, CRLF-normalised.                            |
| `payload_sha256`       | string        | SHA-256 hash of the exported parquet file's own bytes. Checked by `verify_export`. |
| `years`                | list of `int` | Sorted list of reporting years included in the export.                             |
| `row_count`            | int           | Total row count across all exported reporting years. Checked by `verify_export`.   |
| `created_at`           | string        | Export timestamp in ISO 8601 format (UTC).                                         |
| `vintages`             | object        | Mapping of reporting year to source metadata (`etag` and `retrieved_at`).          |

`payload_sha256` and `row_count` make an export file self-checking. `verify_export` re-hashes the parquet payload and compares both fields against the manifest. `load_export` runs that check by default before reading the file back.

```python
import tossd_reader as tossd

tossd.export("tossd_2024.parquet", years=2024)
tossd.verify_export("tossd_2024.parquet")

df = tossd.load_export("tossd_2024.parquet")
print(df.shape)
print(sorted(df.attrs["tossd_reader"]))
```

```text
(474026, 55)
['created_at', 'package_version', 'years']
```

`verify_export` checks only `payload_sha256` and `row_count`. An export written by an older or newer package version can carry a different `schema_hash` without being corrupted, so that field sits outside the check.

<!-- prettier-ignore -->
::: tossd_reader._export.verify_export
    options:
      heading_level: 2

<!-- prettier-ignore -->
::: tossd_reader._export.load_export
    options:
      heading_level: 2

<!-- prettier-ignore -->
!!! warning "Heads up"

    `verify=False` skips the payload-hash and row-count checks. `load_export` still reads `<stem>.manifest.json` for `df.attrs` provenance, so a missing or unreadable manifest raises `ExportIntegrityError` either way.

A tampered or truncated file fails at the hash check:

```python
tossd.verify_export("tossd_2024.parquet")
```

```text
ExportIntegrityError: tossd_2024.parquet does not match its manifest: sha256 a6cb8d2e18696af9… but the manifest recorded e203faab0bb8a69f…. The file may have been modified or corrupted since export.
```

<!-- prettier-ignore -->
::: tossd_reader.exceptions.ExportIntegrityError
    options:
      heading_level: 3

## Performance and memory

Exporting the default full dataset (`years=None`, covering 2019 through 2024) materialises approximately 2.4 million rows in memory as an Apache Arrow table before writing to disk. This requires roughly 2.1 GB of resident memory. Pass specific years to `years=` when working in memory-constrained environments.

## Next

- [Configuration, warnings, and errors](configuration.md). Cache settings, provenance handling, and error types.
- [Query](query.md). Interactive querying with `get_tossd`.
