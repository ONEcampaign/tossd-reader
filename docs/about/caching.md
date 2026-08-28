# About the cache and provenance

_As of v0.1._

tossd.online publishes six URLs, one per year
(`https://tossd.online/tossddata_{year}.parquet`), and republishes each one in
place. A correction, a late submission, a data refresh all land at the same
URL as before. The URL alone can't tell an analysis which revision of a year
it actually read. Why does `tossd_reader` key its cache on the HTTP `ETag`
instead of the URL or a fetch date, and what guarantee does that give a
result built from `get_tossd()` or `get_tossd_raw()`?

## The short answer

The publisher's `ETag` is the only identity a vintage has, so the cache key
embeds it directly, `tossd_{year}_{etag}`. Two downloads of
`tossddata_2024.parquet` that differ upstream get two different keys, two
different cached files, and two different provenance records. A result can
always name the exact bytes it was built from. A cache key stays valid until
the publisher issues a new `ETag` on that URL, surfaced by discovery's HEAD
sweep.

## Background

Each cached year is one whole parquet file, stored by
`readerkit.ArtifactCache` under a key shaped like
`tossd_2024_"69e6ac8d-5728379"`.
`discovery.discover()` runs one HEAD request per known year at the start of
a call and memoises the result for the life of the process. That sweep
exists to tell `fetch_year` which `ETag` to expect before it spends any
bandwidth on the download itself.

## The reasoning

### The GET response is authoritative, the HEAD sweep is a hint

`VintageInfo.etag`, from the HEAD sweep, only forms the candidate cache key.
`fetch_year`'s download compares the GET response's own `ETag` against that
candidate before writing a single byte. If they differ, the download retries
under the corrected key, up to two attempts total. If the `ETag` keeps
changing across both attempts, `fetch_year` gives up with a
`TossdNetworkError` naming every `ETag` it saw, rather than caching a file it
can't vouch for.

One case degrades the guarantee. When neither the HEAD nor the GET response
ever carries an `ETag`, the entry is keyed `..._unknown` instead, and a
warning fires once per year. That vintage can't detect a republish on its
own. Only `refresh=True` (or an enclosing `readerkit.refresh_scope()`)
forces a fresh download for it.

### An effectively unbounded TTL

The cache entry's TTL is ten years, which in practice is unbounded. The key
already encodes the vintage's `ETag`, so a fixed key's content has nothing
left to go stale by age. A cached vintage goes stale only when discovery
finds a new `ETag` at that URL. Wall-clock age plays no part in that
decision. `refresh=True` (or `refresh_scope()`) is what asks the "is there a
new `ETag` yet" question again.

### Serving stale rather than failing

When the publisher is unreachable, or a download drops mid-transfer,
`fetch_year` doesn't raise first. It serves the newest cached vintage for
that year and warns loudly, naming the vintage's retrieval date and `ETag`.
It raises `TossdNetworkError` only when nothing is cached for that year
either. A year the publisher has stopped listing behaves the same way,
served from cache with a warning. Passing `refresh=True` changes that.
Revalidating a delisted year isn't possible, so the call raises
`TossdNetworkError` instead of falling back.

The warning is the only signal marking a result as built from a stale
vintage. A process that runs unattended and discards warnings can work
from old data through an entire outage without anything else showing it.

### Provenance travels with every payload

Every downloaded vintage gets a sidecar, `<file>.provenance.json`, written
once and never overwritten on a later cache hit:

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
carries the receipts for what it was built from.

### Bounds, and a cache generation independent of the package version

The cache keeps the newest 24 artifacts and 4 GB total, both hardcoded.
Older entries are evicted once either limit is hit. The on-disk layout is
versioned separately from the package. `app_version="1"` is a coarse
generation number, bumped only when the key or artifact layout changes in a
way that would otherwise silently corrupt an existing cache. It isn't tied
to `__version__`, so a patch release doesn't force a re-download of the
roughly 2.4M-row dataset.

## Alternatives we considered

**OS or HTTP-level caching.** We considered leaving this to a generic HTTP
cache at the transport layer and rejected it. Discovery's HTTP session is
built with no disk cache there on purpose. A generic HTTP cache keys off
request headers it already has, but it has no concept of "serve the newest
thing you hold and warn loudly" versus "the origin is gone, fail." It also
carries no provenance. Naming the `ETag` a result came from would mean
capturing response headers separately at query time, which is the problem
this design solves, moved to a less convenient layer.

**Per-query result caching.** Caching the DataFrame `get_tossd()` returns,
keyed on years, providers, pillars, columns, and units, would invalidate on
the query's shape rather than on the data's identity. A republished vintage
would still need the same `ETag` tracking underneath, and every distinct
query shape would multiply cache entries for the same underlying bytes.
Provenance would also have to describe an already-filtered result instead of
the raw file it came from.

**Pinning by date.** The publisher republishes each year's file at the same
URL, with no version or date encoded in it. A date-keyed cache would
re-download an unchanged file every time the date rolled over, and would
just as easily mistake a same-day republish for the previous, unchanged
file, since nothing in the URL or the date carries the publisher's own
notion of a new revision.

## Consequences

Any cached vintage, and any result built from it, can name the exact `ETag`
and retrieval time it came from. Offline work is the default rather than an
opt-in mode. No cached data raises an explicit `TossdNetworkError`, but any
cached data at all is enough to keep working, with a warning marking it as
such.

The cost is disk and first-call latency. A single year's cached parquet
runs 55 to 91 MB. All six years together cost roughly 0.45 GB. The first
call for a year downloads the whole published file even when a query only
needs a handful of columns, since there's no partial or range-based fetch.
The stale-serve behaviour trades a small silent-failure risk, a warning an
unattended process could discard, for the ability to keep working through an
outage, mitigated by naming the exact vintage being substituted in the
warning text itself.

## Related

- [Work offline and manage the cache](../how-to/work-offline.md). Puts
  `set_cache_dir`, `TOSSD_READER_CACHE_DIR`, and `refresh=True` into
  practice.
- [Export a reproducible extract](../how-to/export-an-extract.md). Uses the
  provenance manifest this page describes.
- [Configuration and errors](../reference/configuration.md). The full
  parameter and exception reference.
