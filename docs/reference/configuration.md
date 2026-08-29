# Configuration, warnings, and errors

_As of v0.1._

tossd_reader exposes one configuration function, `set_cache_dir`, and one
environment variable, `TOSSD_READER_CACHE_DIR`.

<!-- prettier-ignore -->
::: tossd_reader.config.set_cache_dir
    options:
      heading_level: 2

## Cache location and bounds

The default cache directory is platform-specific.

- macOS: `~/Library/Caches/readerkit/v1/tossd-reader/1`
- Linux: `~/.cache/readerkit/v1/tossd-reader/1`
- Windows: `%LOCALAPPDATA%\readerkit\Cache\v1\tossd-reader\1`

`TOSSD_READER_CACHE_DIR` overrides the
default and is re-read on every call. Changes to the environment take effect
without a reset step. Precedence, highest first:
`set_cache_dir(path)`, then `TOSSD_READER_CACHE_DIR`, then
`BBLOCKS_CACHE_DIR` (shared across the reader family), then the platform
default.

The cache keeps the newest 24 artefacts and 4 GB, whichever bound is reached
first. Both are hardcoded.

<!-- prettier-ignore -->
??? abstract "Under the hood"

    Discovery's HEAD sweep gives a candidate `ETag` for each requested year.
    The GET response's own `ETag` is authoritative. If it differs from the
    candidate, the download retries under the corrected key, up to two
    attempts total. If the `ETag` keeps changing across both attempts, the
    fetch raises `TossdNetworkError` naming every `ETag` it saw.

    When neither the HEAD nor the GET response ever carries an `ETag` for a
    year, that vintage is cached under an `unknown` key instead, with a
    warning. Only `refresh=True` (or an enclosing
    `readerkit.refresh_scope()`) forces a fresh download for it.

## Warnings

| Source         | Trigger                                                                                                                                                       | Repeats?                                                                  |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| `discovery.py` | The publisher now lists a year outside the packaged known-years set.                                                                                          | Once per newly seen year, per process.                                    |
| `fetch.py`     | The publisher is unreachable, or a requested year is no longer listed, and a cached vintage is served instead.                                                | No package-level suppression. Fires on every affected call.               |
| `fetch.py`     | Neither the HEAD nor the GET response carried an `ETag` for a year, so it's cached under an `unknown` key.                                                    | Once per year, per process.                                               |
| `fetch.py`     | A vintage's provenance sidecar exists but can't be parsed as JSON and is ignored; that year's `etag`/`retrieved_at` are `null` in an export manifest. | No package-level suppression. Fires on every read of the corrupt sidecar. |
| `query.py`     | `get_tossd`'s filters matched no rows.                                                                                                                        | No package-level suppression. Fires on every empty-result call.           |
| `query.py`     | A sub-pillar filter (`pillars=21/22/"II.A"/"II.B"`) with the default `years=None` narrows to 2023 onward.                                                     | Once per process.                                                         |
| `query.py`     | A sub-pillar filter's resolved years include 2023, where tagging coverage is incomplete.                                                                      | Once per process.                                                         |
| `query.py`     | A `parent_channel_code` value isn't in the packaged codelist, when `parent_channel_name` is requested.                                                        | Once per newly seen code, per process.                                    |
| `schema.py`    | The published file carries a column not in the packaged schema (visible only under `columns="all"`).                                                          | Once per newly seen column name, per process.                             |

## Errors

One base class. Catch `TossdReaderError` to catch everything tossd_reader
raises.

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

## Next

- [Work offline and manage the cache](../how-to/work-offline.md). Recipes for
  forcing a refresh and running with no network.
- [Export](export.md). Where `etag` and `retrieved_at` land in a manifest,
  and what those fields hold when a sidecar is corrupt.
