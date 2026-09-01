# Build an extract someone else can reproduce

Development finance research requires traceable data extracts that colleagues and peer reviewers can audit and reproduce. This tutorial exports an annual TOSSD dataset to Apache Parquet format, inspects the companion JSON provenance manifest, and verifies dataset vintages across repeated runs.

## What you'll build

An analytical Parquet data extract and its accompanying JSON provenance manifest.

```text
exports/tossd_2019.parquet
exports/tossd_2019.manifest.json
```

## What you'll learn

- How to export a full TOSSD annual release to Parquet format.
- How to inspect provenance metadata in the generated JSON manifest.
- How HTTP ETag headers identify published data vintages.
- How to document and package data extracts for reproducible research handover.

## What you'll need

- Python 3.12 or newer, with `tossd-reader` installed.
- About five minutes.
- Cached 2019 TOSSD vintage (initial calls download the published file to local storage).

## Step 1: Export one year

Export the 2019 published TOSSD dataset into a dedicated export folder.

```python
import tossd_reader as tossd

path = tossd.export("exports", years=2019)
path
```

```text
PosixPath('exports/tossd_2019.parquet')
```

Passing a directory path generates a standard filename (`tossd_2019.parquet`) and creates the target directory when required. The `export()` function preserves all published columns and original publisher units (USD thousand). Custom filtering by recipient, provider, or pillar and unit conversions take place downstream during analysis with `get_tossd()`.

## Step 2: Read the manifest

Inspect the JSON manifest file created alongside the Parquet extract to examine the recorded provenance metadata.

```python
from pathlib import Path

print(Path("exports/tossd_2019.manifest.json").read_text())
```

```text
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

The manifest records descriptive metadata about the export. `tossd_reader_version` identifies the package version, while `schema_hash` hashes the packaged schema definition rather than the exported Parquet payload. `created_at` records the export timestamp, and `row_count` records the number of exported rows. The `vintages` mapping records the HTTP `etag` and initial `retrieved_at` timestamp for each year included in the file. Because the manifest contains no hash or signature of the Parquet file, it cannot by itself verify the payload's integrity or completeness after handover.

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

The matching ETag confirms that both exports used the identical upstream data vintage. The library validates the upstream ETag before serving from local cache, ensuring that upstream revisions are detected automatically. Passing `refresh=True` bypasses cached files and retrieves the latest published version directly from tossd.online.

```python
# The manifest ETag identifies the exact data vintage
manifest["vintages"]["2019"]["etag"]

# Static URLs omit publication revisions
# "https://tossd.online/tossddata_2019.parquet"
```

## Step 4: Hand it over

A complete reproducible research handover includes three core artifacts.

- The Parquet data file (`exports/tossd_2019.parquet`).
- The JSON provenance manifest (`exports/tossd_2019.manifest.json`).
- Analytical documentation recording the year range, provider filtering criteria, aggregate row handling, units, and price basis.

<!-- prettier-ignore -->
!!! warning "Heads up"
    Exporting all six years without a `years` argument materialises 2.4 million rows in memory as an Apache Arrow table before writing to disk, requiring roughly 2.1 GB of RAM. Supply specific reporting years to `years=` when exporting on memory-constrained systems.

If a cached provenance file is missing or corrupted, the manifest records `null` for `etag` and `retrieved_at` while emitting a warning during export.

## What you learned

- You exported an annual TOSSD dataset to Parquet format.
- You inspected provenance metadata in the generated JSON manifest.
- You compared ETag headers to determine whether exports reference the same published data vintage.
- You established the required documentation and file bundle for reproducible research handovers.

## What's next

- [About reproducibility](../about/reproducibility.md) covers cache management, offline operation, and publisher connectivity.
- [Export](../reference/export.md) documents the complete `export()` function signature and manifest schema.
- [Build a six-year Senegal disbursement trend](first-analysis.md) applies these reproducible data extracts to multi-year development finance analysis.
