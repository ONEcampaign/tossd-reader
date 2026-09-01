# Configuration, warnings, and errors

The package provides two configuration functions, `set_cache_dir` and `get_cache_dir`, and one configuration environment variable, `TOSSD_READER_CACHE_DIR`.

<!-- prettier-ignore -->
::: tossd_reader.config.set_cache_dir
    options:
      heading_level: 2

<!-- prettier-ignore -->
::: tossd_reader.config.get_cache_dir
    options:
      heading_level: 2

## Cache location and bounds

The default cache location depends on the operating system:

- macOS: `~/Library/Caches/readerkit/v1/tossd-reader/1`
- Linux: `~/.cache/readerkit/v1/tossd-reader/1`
- Windows: `%LOCALAPPDATA%\readerkit\Cache\v1\tossd-reader\1`

Resolution precedence, in order of highest priority, evaluates `set_cache_dir(path)`, the `TOSSD_READER_CACHE_DIR` environment variable, the `BBLOCKS_CACHE_DIR` environment variable, and the platform default directory.

`TOSSD_READER_CACHE_DIR` overrides the platform default and is re-read on every query. Changes to the environment variable take effect immediately without requiring a cache reset.

The cache retains the newest 24 artifacts or up to 4 GB of data, whichever limit is reached first. Both limits are fixed.

<!-- prettier-ignore -->
??? abstract "Under the hood"

    Discovery runs a HEAD request sweep to identify candidate `ETag` values for requested years. The `ETag` returned by the subsequent GET response is authoritative. When the GET `ETag` differs from the candidate, the download retries under the corrected key (up to two total attempts). If the `ETag` continues changing across both attempts, the fetch raises `TossdNetworkError` detailing the observed values.

    When neither HEAD nor GET responses provide an `ETag` header, the downloaded vintage is stored under an `unknown` key with a warning. Passing `refresh=True` (or using `readerkit.refresh_scope()`) forces a fresh download.

## Warnings

| Source          | Condition                                                                                               | Frequency                                    |
| --------------- | ------------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| Discovery       | Publisher lists a reporting year outside the packaged known years.                                      | Once per newly seen year per process.        |
| Fetch and cache | Publisher host is unreachable or year is unavailable, serving a cached vintage.                         | Emitted on every affected call.              |
| Fetch and cache | Neither HEAD nor GET responses returned an `ETag` for a year.                                           | Once per year per process.                   |
| Fetch and cache | Provenance sidecar exists but contains invalid JSON, causing `null` vintage fields in export manifests. | Emitted on every read of the corrupted file. |
| Query           | Query filters match zero records.                                                                       | Emitted on every empty result call.          |
| Query           | Sub-pillar filter (`pillars=21` or `"II.A"`) with default `years=None` narrows to 2023 onward.          | Once per process.                            |
| Query           | Sub-pillar filter includes 2023, where sub-pillar reporting coverage is partial.                        | Once per process.                            |
| Query           | Unmapped `parent_channel_code` value encountered during `parent_channel_name` resolution.               | Once per newly seen code per process.        |
| Schema check    | Published dataset contains a column not defined in `schema.csv` (visible under `columns="all"`).        | Once per newly seen column per process.      |

## Errors

All package exceptions inherit from `TossdReaderError`. Catching `TossdReaderError` intercepts all package-specific exceptions.

<!-- prettier-ignore -->
::: tossd_reader.exceptions.TossdReaderError
    options:
      heading_level: 3

<!-- prettier-ignore -->
::: tossd_reader.exceptions.TossdNetworkError
    options:
      heading_level: 3

<!-- prettier-ignore -->
::: tossd_reader.exceptions.VintageValidationError
    options:
      heading_level: 3

<!-- prettier-ignore -->
::: tossd_reader.exceptions.SchemaDriftError
    options:
      heading_level: 3

<!-- prettier-ignore -->
::: tossd_reader.exceptions.UnknownCodeError
    options:
      heading_level: 3

<!-- prettier-ignore -->
::: tossd_reader.exceptions.InvalidPillarError
    options:
      heading_level: 3

<!-- prettier-ignore -->
::: tossd_reader.exceptions.ExportIntegrityError
    options:
      heading_level: 3

## Next

- [Work offline and manage the cache](../how-to/work-offline.md). Cache refresh workflows and offline execution.
- [Export](export.md). Parquet file generation and manifest provenance fields.
