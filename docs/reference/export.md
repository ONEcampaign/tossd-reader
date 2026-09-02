# Export

`export` casts and types TOSSD activity records, then writes the result to a compressed parquet file with an export manifest. Exports retain all columns (`columns="all"`) and original units (`units="usd_thousand"` in USD thousands).

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
  "created_at": "2026-09-02T08:24:37.680642+00:00",
  "payload_sha256": "8a6eed10875a87fcd5faedece760bc461aa5926113ba1686613728c8c27d30bf",
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

`load_export` sets `df.attrs["tossd_reader"]` to this same three-key shape on every call. An export is an unfiltered snapshot, so it carries no `query` key the way a `get_tossd()` or `get_tossd_raw()` result does. `tossd.get_provenance(df)` returns the payload as a deep copy, so mutating the result never touches `df`'s own attrs the way editing `df.attrs["tossd_reader"]` directly would. See [Verbs](verbs.md) for `get_provenance` and its `df.tossd.provenance()` accessor equivalent.

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

A tampered or truncated file fails at the hash check. Flipping a single byte mid-file is enough:

```python
with open("tossd_2024.parquet", "r+b") as f:
    f.seek(1_000_000)
    original_byte = f.read(1)
    f.seek(1_000_000)
    f.write(bytes([original_byte[0] ^ 0xFF]))

tossd.verify_export("tossd_2024.parquet")
```

```text
ExportIntegrityError: tossd_2024.parquet does not match its manifest: sha256 86f01b27506eeaba3f4fb71fd98ffa2e910bb6fb663e8d6d88a48c219ade1c3e but the manifest recorded cbc990069898161335701299e172cd6ae39bbfef2d2543ec7044e914384b13e8. The file may have been modified or corrupted since export.
```

<!-- prettier-ignore -->
::: tossd_reader.exceptions.ExportIntegrityError
    options:
      heading_level: 3

## Performance and memory

Exporting the default full dataset (`years=None`, covering 2019 through 2024) materialises approximately 2.4 million rows in memory as an Apache Arrow table before writing to disk. Peak resident memory reaches roughly 4.4 GB. The finished table itself accounts for about 2.1 GB of that. Per-year tables stay alive alongside it until concatenation completes. Pass specific years to `years=` when working in memory-constrained environments, or pass `max_rows=` to fail fast instead of writing an export larger than expected:

```python
tossd.export("out", years=2019, max_rows=100_000)
```

```text
ValueError: export() would write 290914 rows, exceeding max_rows=100000. Pass a larger max_rows=, or narrow years= to export a smaller slice.
```

The check runs after the table is built, so the error names the actual row count. It also runs before anything is written, so a rejected export leaves no partial file, and a pre-existing file at the target path is untouched.

## Next

- [Configuration, warnings, and errors](configuration.md). Cache settings, provenance handling, and error types.
- [Query](query.md). Interactive querying with `get_tossd`.
