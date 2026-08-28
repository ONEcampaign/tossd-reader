# About the cache and provenance

_As of v0.1._

tossd.online publishes six URLs, one per year
(`https://tossd.online/tossddata_{year}.parquet`), and republishes each one in
place. A correction, a late submission, a data refresh all land at the same URL
as before. The URL alone can't tell an analysis which revision of a year it
actually read. Why does `tossd_reader` key its cache on the HTTP `ETag` instead
of the URL or a fetch date, and what guarantee does that give a result built
from `get_tossd()` or `get_tossd_raw()`?

## The short answer

The publisher's `ETag` is the only identity a vintage has, so the cache key
embeds it directly, `tossd_{year}_{etag}`. Two downloads of
`tossddata_2024.parquet` that differ upstream get two different keys, two
different cached files, and two different provenance records. A result can
always name the exact bytes it was built from. A cache key stays valid until the
publisher issues a new `ETag` on that URL, surfaced by discovery's HEAD sweep.

## Background

Each cached year is one whole parquet file, stored by `readerkit.ArtifactCache`
under a key shaped like `tossd_2024_"69e6ac8d-5728379"`. `discovery.discover()`
runs one HEAD request per known year at the start of a call and memoises the
result for the life of the process. That sweep exists to tell `fetch_year` which
`ETag` to expect before it spends any bandwidth on the download itself.

## The reasoning

### The GET response is authoritative, the HEAD sweep is a hint

`VintageInfo.etag`, from the HEAD sweep, only forms the candidate cache key.
`fetch_year`'s download compares the GET response's own `ETag` against that
candidate before writing a single byte. If they differ, the download retries
under the corrected key, up to two attempts total. If the `ETag` keeps changing
across both attempts, `fetch_year` gives up with a `TossdNetworkError` naming
every `ETag` it saw, rather than caching a file it can't vouch for.

One case degrades the guarantee. When neither the HEAD nor the GET response ever
carries an `ETag`, the entry is keyed `..._unknown` instead, and a warning fires
once per year. That vintage can't detect a republish on its own. Only
`refresh=True` (or an enclosing `readerkit.refresh_scope()`) forces a fresh
download for it.

### An effectively unbounded TTL

The cache entry's TTL is ten years, which in practice is unbounded. The key
already encodes the vintage's `ETag`, so a fixed key's content has nothing left
to go stale by age. A cached vintage goes stale only when discovery finds a new
`ETag` at that URL. `refresh=True` (or `refresh_scope()`) is what asks the "is
there a new `ETag` yet" question again.

### Serving stale rather than failing

When the publisher is unreachable, or a download drops mid-transfer,
`fetch_year` serves the newest cached vintage for that year and warns loudly,
naming the vintage's retrieval date and `ETag`. It raises `TossdNetworkError`
only when nothing is cached for that year either. Any cached year keeps
offline work going, with no separate flag needed. A year the publisher has
stopped listing behaves the same way, served from cache with a warning.
Passing `refresh=True` for a delisted year raises `TossdNetworkError`, because
there is nothing new to revalidate against.

The warning is the only signal marking a result as built from a stale vintage. A
process that runs unattended and discards warnings can work from old data
through an entire outage without anything else showing it.

### Provenance travels with every payload

Every downloaded vintage gets a sidecar, `<file>.provenance.json`, written once
and never overwritten on a later cache hit:

```json
{
  "url": "https://tossd.online/tossddata_2024.parquet",
  "etag": "\"69e6ac8d-5728379\"",
  "size_bytes": 91390841,
  "sha256": "73382c164e12ece36119080631de60cc2d737ef4bba817b7a75a8eadd922614c",
  "row_count": 474026,
  "retrieved_at": "2026-08-28T19:32:28.617740+00:00",
  "tossd_reader_version": "0.1.0"
}
```

`export()` reads the same sidecars and folds `etag`/`retrieved_at` for every
exported year into `<stem>.manifest.json`, alongside the package version, a
schema hash, and the total row count. A parquet file handed to someone else
comes with a manifest describing what it was built from.

### Bounds, and a cache generation independent of the package version

A single year's cached parquet runs 55 to 91 MB, so all six years together cost
roughly 0.45 GB. The cache keeps the newest 24 artifacts and 4 GB total, both
hardcoded. Older entries are evicted once either limit is hit. The on-disk
layout is versioned separately from the package. `app_version="1"` is a coarse
generation number, bumped only when the key or artifact layout changes in a way
that would otherwise silently corrupt an existing cache. It isn't tied to
`__version__`, so a patch release doesn't force a re-download of the roughly
2.4M-row dataset. The first call for a year downloads the whole published file
even when a query only needs a handful of columns, since there's no partial or
range-based fetch.

## Related

- [Work offline and manage the cache](../how-to/work-offline.md). Puts
  `set_cache_dir`, `TOSSD_READER_CACHE_DIR`, and `refresh=True` into practice.
- [Export a reproducible extract](../how-to/export-an-extract.md). Uses the
  provenance manifest this page describes.
- [Configuration and errors](../reference/configuration.md). The full parameter
  and exception reference.
