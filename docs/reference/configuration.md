# Configuration, warnings, and errors

The package exposes two independent settings. Cache location (`set_cache_dir`/`get_cache_dir`, with `TOSSD_READER_CACHE_DIR` as the environment override) controls where downloaded vintages live. Offline mode (`set_offline`/`get_offline`, with `TOSSD_READER_OFFLINE` as its own environment override) controls whether a query is allowed to touch the network at all. `cache_info()` and `clear_cache()` inspect and prune what's actually on disk.

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

<!-- prettier-ignore -->
::: tossd_reader.config.set_offline
    options:
      heading_level: 2

<!-- prettier-ignore -->
::: tossd_reader.config.get_offline
    options:
      heading_level: 2

## Offline mode

`TOSSD_READER_OFFLINE` recognises `1`, `true`, and `yes` (case-insensitive) as true, and `0`, `false`, and `no` as false. Unset or empty stays false silently. Anything else (a typo like `on`, or a stray `2`) still resolves to `False`, but warns once per process, since a caller who set the variable almost certainly meant to turn offline mode on:

```bash
TOSSD_READER_OFFLINE=on python analysis.py
```

```text
UserWarning: TOSSD_READER_OFFLINE='on' is not a recognized value; offline mode is NOT active. Recognised truthy values are 1, true, yes (case-insensitive).
```

`set_offline(True)` or `set_offline(False)` overrides the environment variable outright, for the rest of the process. `set_offline(None)` resets to reading `TOSSD_READER_OFFLINE` again, the same state as never having called `set_offline` at all.

With offline mode active, a fetch that has a cached vintage to fall back on serves it and warns, naming the retrieval timestamp and ETag:

```python
import tossd_reader as tossd

tossd.set_offline(True)
df = tossd.get_tossd(years=2024, columns="minimal")
```

```text
UserWarning: Offline mode is active (tossd_reader.config.set_offline(False), or the TOSSD_READER_OFFLINE env var, would allow network access); serving the cached 2024 vintage retrieved 2026-09-02T12:21:52.639935+00:00 (etag "69e6ac8d-5728379").
```

`refresh=True` needs the network by definition, and offline mode exists to rule the network out, so combining the two raises `ValueError` naming the conflict. The same check guards `get_tossd()`, `get_tossd_raw()`, `export()`, and `get_vintages()`, with the same message shape aside from the leading function name:

```python
tossd.set_offline(True)
tossd.get_tossd(years=2024, refresh=True)
```

```text
ValueError: get_tossd(refresh=True) conflicts with offline mode (config.get_offline() is True): a forced refresh needs the network. Call tossd_reader.config.set_offline(False) first, or omit refresh=True.
```

The message spells out the full module path. `tossd.set_offline(False)` at the top level does the same thing.

<!-- prettier-ignore -->
::: tossd_reader.config.cache_info
    options:
      heading_level: 2

<!-- prettier-ignore -->
::: tossd_reader.config.clear_cache
    options:
      heading_level: 2

## Inspecting and clearing the cache

`cache_info()` lists every locally cached vintage, one row per vintage, not per year. A year re-downloaded after a republish shows up twice, once for each ETag retrieved. `path` is a local absolute path. The example below drops it to fit the page.

```python
import tossd_reader as tossd

tossd.cache_info().drop(columns=["path"])
```

```text
   year                etag                      retrieved_at                    downloaded_at  size_bytes
0  2019  "69e6ac86-347a653"  2026-08-28T21:14:14.414671+00:00 2026-09-02 08:05:04.508371+00:00    55027283
1  2021  "69e6ac8b-4112f49"  2026-08-28T21:14:42.382179+00:00 2026-08-28 21:14:42.356395+00:00    68235081
2  2020  "69e6ac8a-3c90446"  2026-08-28T21:14:28.358434+00:00 2026-08-28 21:14:28.331745+00:00    63505478
3  2022  "69e6ac8b-4e95ca1"  2026-08-28T21:14:57.492221+00:00 2026-08-28 21:14:57.461650+00:00    82402465
4  2024  "69e6ac8d-5728379"  2026-08-28T19:32:28.617740+00:00 2026-08-28 19:32:28.582136+00:00    91390841
5  2023  "69e6ac8c-56469db"  2026-08-28T21:15:12.643113+00:00 2026-08-28 21:15:12.608318+00:00    90466779
```

`etag` and `retrieved_at` come from that vintage's own provenance sidecar and read `None` if the sidecar is missing or corrupt. `downloaded_at` comes from the cache's own metadata, always present even when the sidecar is missing or corrupt.

`clear_cache()` with no arguments removes exactly the superseded vintages, the ones `keep_latest=True` (the default) doesn't need to protect, because a newer download for the same year already exists. A cache holding exactly one vintage per year has nothing superseded, so the bare call removes nothing:

```python
tossd.clear_cache()
```

```text
0
```

`keep_latest` protects each year's single newest entry even when `years=` or `before=` would otherwise match it. Pass `keep_latest=False` to drop that protection. With no other arguments, that empties the cache entirely:

```python
tossd.clear_cache(keep_latest=False)
```

```text
6
```

```python
len(tossd.cache_info())
```

```text
0
```

`before=` accepts a `date`, a `datetime`, or an ISO 8601 string. A naive value (no timezone) is treated as UTC. Every call returns the number of entries removed.

<!-- prettier-ignore -->
!!! warning "Heads up"

    A filesystem fault removing an entry (a permission error, say) propagates as `OSError` instead of being caught and skipped per-entry. The cache can be left partially cleared. The `removed` count from a prior, non-raising call is the only record of how much of a partial run completed.

## Warnings

| Source          | Condition                                                                                                                                    | Frequency                                    |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| Discovery       | Publisher lists a reporting year outside the packaged known years.                                                                           | Once per newly seen year per process.        |
| Discovery       | `get_vintages()` falls back to the local cache instead of a live sweep, because offline mode is active or the publisher host is unreachable. | Emitted on every affected call.              |
| Fetch and cache | Publisher host is unreachable, offline mode is active, or a requested year is no longer published, serving a cached vintage instead.         | Emitted on every affected call.              |
| Fetch and cache | Neither HEAD nor GET responses returned an `ETag` for a year.                                                                                | Once per year per process.                   |
| Fetch and cache | Provenance sidecar exists but contains invalid JSON, causing `null` vintage fields in export manifests.                                      | Emitted on every read of the corrupted file. |
| Config          | `TOSSD_READER_OFFLINE` is set to a value that's neither a recognised truthy nor falsy spelling.                                              | Once per process.                            |
| Query           | Query filters match zero records.                                                                                                            | Emitted on every empty result call.          |
| Query           | Sub-pillar filter (`pillars=21` or `"II.A"`) with default `years=None` narrows to 2023 onward.                                               | Once per process.                            |
| Query           | Sub-pillar filter includes 2023, where sub-pillar reporting coverage is partial.                                                             | Once per process.                            |
| Query           | Unmapped `parent_channel_code` value encountered during `parent_channel_name` resolution.                                                    | Once per newly seen code per process.        |
| Schema check    | Published dataset contains a column not defined in `schema.csv` (visible under `columns="all"`).                                             | Once per newly seen column per process.      |

## Errors

All package exceptions inherit from `TossdReaderError`. Catching `TossdReaderError` intercepts all package-specific exceptions. A few argument- and state-validation failures raise a plain `ValueError` instead, including the offline/refresh conflict above. Catching `TossdReaderError` alone won't intercept those.

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
- [About reproducibility and the cache](../about/reproducibility.md). Why vintages differ, and how provenance ties a result back to one.
