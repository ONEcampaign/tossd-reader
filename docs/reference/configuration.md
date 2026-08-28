# Configuration and errors

_As of v0.1._

tossd_reader's configuration surface is deliberately narrow. One function,
`set_cache_dir`, and one environment variable, `TOSSD_READER_CACHE_DIR`.

<!-- prettier-ignore -->
::: tossd_reader.config.set_cache_dir
    options:
      heading_level: 2

## Cache location and bounds

The default cache directory is platform-specific.

- macOS: `~/Library/Caches/readerkit/v1/tossd-reader/1`
- Linux: `~/.cache/readerkit/v1/tossd-reader/1`

`TOSSD_READER_CACHE_DIR` overrides the
default and is re-read on every call, so a change to the environment between
calls takes effect with no reset step. Precedence, highest first:
`set_cache_dir(path)`, then `TOSSD_READER_CACHE_DIR`, then the platform
default.

The cache keeps the newest 24 artifacts and 4 GB, whichever bound is reached
first. Both are hardcoded, with no user-facing setting.

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
- [The cache and provenance](../about/caching.md). Why the cache is a single
  tier keyed by ETag, and what the provenance sidecar records.
