# How to export a reproducible extract

`export()` writes the full, normalised `get_tossd` output to parquet, with a manifest that pins the exact published vintage behind each year.

## What `export()` writes

`export(path, *, years=None, refresh=False)` takes only `years` and `refresh`, no provider, recipient, or pillar filters. What it writes is fixed. Every column (`columns="all"`), amounts in USD thousand (`units="usd_thousand"`, as published), normalised and typed by the same schema layer `get_tossd` uses, compressed with zstd.

For a filtered subset, call `get_tossd()`, which takes those filters, and write the result yourself:

```python
import tossd_reader as tossd

df = tossd.get_tossd(years=2024, pillars="1")
df.to_parquet("tossd_2024_pillar1.parquet")
```

Use `export()` for a full, reproducible extract of one or more years. Use `get_tossd()` plus `to_parquet` when you need a provider, recipient, or pillar filter.

## Export one or more years

1. Call `export` with a directory, or an explicit path ending in `.parquet`:

   ```python
   import tossd_reader as tossd

   out = tossd.export("exports", years=2019)
   print(out)
   ```

   ```text
   exports/tossd_2019.parquet
   ```

2. A directory path gets a generated filename, `tossd_<years-range>.parquet`. One year yields `tossd_2019.parquet`. A contiguous run yields `<first>-<last>`, for example `tossd_2019-2024.parquet`. A non-contiguous set joins every requested year with an underscore, for example `tossd_2019_2021_2023.parquet`. Pass an explicit `.parquet` path instead to name the file yourself.

## Read the manifest

Every export writes `<stem>.manifest.json` beside the parquet file. For `tossd_2019.parquet` that's `tossd_2019.manifest.json`:

```json
{
  "created_at": "2026-08-28T21:15:13.842131+00:00",
  "row_count": 290914,
  "schema_hash": "0a95f2c54852817a9db1a2174cffa5bd371d601e5d137a37cb27491182367df9",
  "tossd_reader_version": "0.1.0",
  "vintages": {
    "2019": {
      "etag": "\"69e6ac86-347a653\"",
      "retrieved_at": "2026-08-28T21:14:14.414671+00:00"
    }
  },
  "years": [2019]
}
```

`created_at`, `retrieved_at`, and `etag` vary from run to run. Expect different values on your own export.

| Field                  | What it's for                                                                                                                                                                                                   |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tossd_reader_version` | The package version that produced the export. The schema and column set can change between versions.                                                                                                            |
| `schema_hash`          | Sha256 of the packaged column schema. Two exports sharing a hash used the same column definitions.                                                                                                              |
| `years`                | The years written to the parquet file.                                                                                                                                                                          |
| `row_count`            | Total rows across every year in the file.                                                                                                                                                                       |
| `created_at`           | When the export ran.                                                                                                                                                                                            |
| `vintages`             | Per year, the publisher's `etag` and the `retrieved_at` timestamp for the cached vintage that was read. This is the reproducibility pin. Matching etags mean matching published bytes, whenever the export ran. |

## Verify it worked

Read the manifest back and check `row_count` and `vintages` against what you expect:

```python
import json
from pathlib import Path

manifest = json.loads(Path("exports/tossd_2019.manifest.json").read_text())
print(manifest["row_count"], manifest["vintages"])
```

!!! warning "Heads up"

    `years=None` (the default) materialises the full packaged years set as one table in memory before any of it reaches disk, roughly 2.1 GB or more resident. Pass an explicit `years=` on a laptop.

## See also

- [`export` reference](../reference/query.md) for the full parameter and exception contract.
- [Configuration reference](../reference/configuration.md) for `set_cache_dir` and `TOSSD_READER_CACHE_DIR`, which govern where `export` reads cached vintages from.
