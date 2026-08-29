# About reproducibility and the cache

_As of v0.1._

## The publisher republishes in place

tossd.online publishes six URLs, one per year
(`https://tossd.online/tossddata_{year}.parquet`), and republishes each one
in place. A correction, a late submission, or a data refresh lands at the
same URL as before, so the URL alone cannot identify which revision of a
year a result was built from.

## What the cache key records

The publisher's `ETag` is the vintage's only identity, so the cache key
embeds it directly: `tossd_{year}_{etag}`. Two downloads of
`tossddata_2024.parquet` that differ upstream get two different keys, two
different cached files, and two different provenance records.

Every downloaded vintage gets a sidecar, `<stem>.provenance.json`, written
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

## What travels with an export

`export()` reads the same sidecars and folds `etag`/`retrieved_at` for every
exported year into `<stem>.manifest.json`, alongside the package version, a
schema hash, and the total row count:

```json
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

## Working from a stale vintage

When the publisher is unreachable, or a requested year is no longer listed,
tossd_reader serves the newest cached vintage for that year and warns,
naming the vintage's retrieval date and `ETag`. A year the publisher has
stopped listing behaves the same way, served from cache with a warning.

The warning is the only signal marking a result as built from a stale
vintage.

## Related

- [How to work offline and manage the cache](../how-to/work-offline.md).
  Priming the cache, `refresh=True`, and running with no network.
- [Export](../reference/export.md). The full manifest field reference for
  the JSON shown above.
