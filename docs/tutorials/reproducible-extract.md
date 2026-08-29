# Build an extract someone else can reproduce

> Export one year of TOSSD to parquet, read what the manifest records about it, and pin the vintage it came from.

## What you'll build

A parquet file and its manifest, plus a second export of the same year that shows the vintage is unchanged.

```text
exports/tossd_2019.parquet
exports/tossd_2019.manifest.json
```

## What you'll learn

- How to export a year of TOSSD to parquet.
- How to read a manifest's provenance fields.
- How the ETag identifies a vintage.
- What to hand over alongside the file so someone else can reproduce it.

## What you'll need

- Python 3.12 or newer, tossd-reader installed.
- About five minutes.
- 2019's vintage cached (querying it downloads the full published file once, if you haven't already).

## Step 1: Export one year

Export 2019 to a directory.

```python
import tossd_reader as tossd

path = tossd.export("exports", years=2019)
path
```

```text
PosixPath('exports/tossd_2019.parquet')
```

A directory path gets a generated filename, `tossd_<years>.parquet`, inside a directory created if it doesn't exist yet.

`export()` always writes every packaged column, in the units the publisher used (USD thousand). Filtering by provider, recipient, or pillar, and converting to USD million, are `get_tossd`'s job.

## Step 2: Read the manifest

Every export writes a `<stem>.manifest.json` sidecar beside the parquet file.

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

`tossd_reader_version` and `schema_hash` pin the code that produced the file. `created_at` is the export's write time. `row_count` is a cheap check against a truncated copy. `vintages` carries one entry per exported year, each with an `etag` and a `retrieved_at`, the time that year's data was downloaded. Those two fields identify the vintage.

## Step 3: Pin the vintage

The TOSSD Secretariat republishes each year's file in place, at the same URL. The ETag changes with each republish, and the manifest pins the ETag.

Export 2019 again and check the ETag:

```python
import json

tossd.export("exports", years=2019)
manifest = json.loads(Path("exports/tossd_2019.manifest.json").read_text())
manifest["vintages"]["2019"]["etag"]
```

```text
'"69e6ac86-347a653"'
```

Same ETag as Step 2. Both exports read the same cached vintage. Every process asks the publisher for each year's current ETag before serving from the cache, so a republished file is picked up with no flag set. `refresh=True` re-asks inside a process that has already checked, and forces a fresh download.

```python
# ✅ Cite the manifest's ETag as the vintage
manifest["vintages"]["2019"]["etag"]

# ❌ Cite the publisher's URL as the vintage
# "https://tossd.online/tossddata_2019.parquet"
```

## Step 4: Hand it over

Three things travel with a reproducible extract:

- The parquet file, `exports/tossd_2019.parquet`.
- Its manifest, `exports/tossd_2019.manifest.json`.
- If the extract feeds an analysis, a note of the year range, aggregate-row handling, unit, and price basis that analysis used.

<!-- prettier-ignore -->
!!! warning "Memory footprint for multi-year exports"
    `export()` with `years=None`, the default, materialises every packaged year in memory before writing any of it to disk, measured at roughly 2.1GB resident for the full six-year set. Pass an explicit `years=` to export a smaller slice.

A corrupt provenance sidecar sets that year's `etag` and `retrieved_at` to `null` in the manifest, with a warning at export time as the only other signal.

## What you learned

- You exported a year of TOSSD to parquet.
- You read a manifest's provenance fields.
- You confirmed how the ETag identifies a vintage.
- You know what to hand over alongside the file so someone else can reproduce it.

## What's next

- [About reproducibility](../about/reproducibility.md) covers how the cache key embeds the ETag and what happens when the publisher is unreachable.
- [Export](../reference/export.md) documents `export`'s full signature and every field the manifest carries.
- [Build a six-year Senegal disbursement trend](first-analysis.md) is the query this extract's manifest note assumes, if you haven't run it yet.
