# Build an extract someone else can reproduce

This tutorial exports an annual TOSSD dataset to Apache Parquet format, inspects the companion JSON export manifest, and verifies dataset vintages across repeated runs.

## What you'll build

An analytical Parquet data extract and its accompanying JSON export manifest.

```text
exports/tossd_2019.parquet
exports/tossd_2019.manifest.json
```

## What you'll learn

- How to export a full TOSSD annual release to Parquet format.
- How to inspect provenance metadata in the generated JSON manifest.
- How HTTP ETag headers identify published data vintages.
- How to verify an extract's integrity and reload it with `load_export`.
- How to document and package data extracts for reproducible research handover.

## What you'll need

- Python 3.12 or newer, with `tossd-reader` installed.
- About seven minutes.
- Cached 2019 TOSSD vintage (initial calls download the published file to local storage).

## Step 1: Export one year

Export the 2019 published TOSSD dataset into a dedicated export folder.

```python
import tossd_reader as tossd

path = tossd.export("exports", years=2019)
path
```

```text
UserWarning: 1 code(s) across 1 column(s) not in the packaged codelists (vintage newer than snapshot?): parent_channel_code has 45000.
PosixPath('exports/tossd_2019.parquet')
```

The warning means the packaged codelist snapshot hasn't caught up with one `parent_channel_code` value in the published 2019 data. `parent_channel_name` reads `NA` for the 116 rows carrying that code, and the rest of the export is unaffected.

Passing a directory path generates a standard filename (`tossd_2019.parquet`) and creates the target directory when required. The `export()` function preserves all published columns and original publisher units (USD thousand). Custom filtering by recipient, provider, or pillar and unit conversions take place downstream during analysis with `get_tossd()`.

## Step 2: Read the manifest

Inspect the JSON manifest file created alongside the Parquet extract to examine the recorded provenance metadata.

```python
from pathlib import Path

print(Path("exports/tossd_2019.manifest.json").read_text())
```

```text
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

`tossd_reader_version` identifies the package version, while `schema_hash` hashes the packaged schema definition rather than the exported Parquet payload. `payload_sha256` hashes the Parquet payload itself; `verify_export()` recomputes it on demand to confirm the file still matches this manifest. `created_at` records the export timestamp, and `row_count` records the number of exported rows. The `vintages` mapping records the HTTP `etag` and initial `retrieved_at` timestamp for each year included in the file.

## Step 3: Pin the vintage

The International Forum on TOSSD (IFT) publishes official data at tossd.online under stable URLs, updating files in place as revisions occur. The HTTP ETag header changes whenever the publisher releases an update. The manifest records this ETag to pin the exact vintage used.

Export the 2019 dataset a second time to verify that the recorded ETag remains consistent across runs.

```python
import json
from pathlib import Path

import tossd_reader as tossd

tossd.export("exports", years=2019)
manifest = json.loads(Path("exports/tossd_2019.manifest.json").read_text())
manifest["vintages"]["2019"]["etag"]
```

```text
'"69e6ac86-347a653"'
```

The matching ETag confirms that both exports used the identical upstream data vintage. The library checks the upstream ETag only when a discovery sweep actually runs, once per process by default, or again whenever `refresh=True` forces one. Both `export()` calls in this tutorial run in the same process, so the second call's matching ETag comes from the first call's memoised sweep, not a fresh check against the publisher. Passing `refresh=True` invalidates that memo and retrieves the latest published version directly from tossd.online.

## Step 4: Verify and reload the extract

`verify_export()` recomputes the Parquet file's hash and compares it against `payload_sha256` in the manifest. Run it before handing an extract to a colleague, or right after receiving one, to confirm the file wasn't corrupted or edited in transit.

```python
tossd.verify_export("exports/tossd_2019.parquet")
```

A silent return means the file matches its manifest.

`load_export()` calls `verify_export()` first, then reads the Parquet file back with the schema's nullable integer dtypes intact and attaches the manifest's provenance to `df.attrs`.

```python
df = tossd.load_export("exports/tossd_2019.parquet")
df.shape
```

```text
(290914, 55)
```

`df.tossd.provenance()` reads that provenance back as a deep copy, without needing to reopen the manifest file.

```python
from pprint import pprint

pprint(df.tossd.provenance())
```

```text
{'created_at': '2026-09-02T08:01:05.881968+00:00',
 'package_version': '0.1.0',
 'years': {'2019': {'etag': '"69e6ac86-347a653"',
                    'retrieved_at': '2026-08-28T21:14:14.414671+00:00'}}}
```

The row count matches `row_count` in the manifest, and the `etag` matches the one you read from the manifest in Step 2. It's the same provenance, reached from the loaded DataFrame instead of the JSON file.

<!-- prettier-ignore -->
!!! note
    An automated pipeline that runs with `tossd.set_offline(True)` can only see vintages already pinned in local cache. A live re-fetch can't slip in a different one. See [Work offline](../how-to/work-offline.md).

## Step 5: Hand it over

A complete reproducible research handover includes three things.

- The Parquet data file (`exports/tossd_2019.parquet`).
- The JSON export manifest (`exports/tossd_2019.manifest.json`).
- Analytical documentation recording the year range, provider filtering criteria, aggregate row handling, units, and price basis.

<!-- prettier-ignore -->
!!! note
    If a colleague's copy of the file changes in transit, even by one byte, `verify_export()` catches it:

    ```text
    ExportIntegrityError: exports/tossd_2019.parquet does not match its manifest: sha256 49d27ebdb8030316… but the manifest recorded 8a6eed10875a87fc…. The file may have been modified or corrupted since export.
    ```

<!-- prettier-ignore -->
!!! warning "Heads up"
    Exporting all six years without a `years` argument materialises 2.4 million rows in memory as an Apache Arrow table before writing to disk. Peak RAM reaches roughly 4.4 GB. The finished table itself is about 2.1 GB, but per-year tables stay alive alongside it until they're concatenated. Supply specific reporting years to `years=` when exporting on memory-constrained systems.

If a cached provenance file is corrupted, the manifest records `null` for `etag` and `retrieved_at` while emitting a warning during export. A missing provenance file records the same `null` values, silently.

## What's next

- [About reproducibility](../about/reproducibility.md) covers cache management, offline operation, and publisher connectivity.
- [Export](../reference/export.md) documents the complete `export()` function signature and manifest schema.
- [Build a six-year Senegal disbursement trend](first-analysis.md). A related multi-year analysis tutorial. It queries `get_tossd()` directly rather than exporting to Parquet first.
