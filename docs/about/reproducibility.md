# About reproducibility and the cache

TOSSD datasets are published annually by the International Forum on TOSSD at fixed endpoints on [tossd.online](https://tossd.online). Because the Secretariat republishes datasets in place to incorporate retroactive corrections, provider revisions, and late submissions, analytical reproducibility requires tracking specific data vintages.

## In-place publication and data vintages

The official portal provides one endpoint per calendar year (`https://tossd.online/tossddata_{year}.parquet`). When a provider submits revisions for an earlier reporting period, the publisher updates the corresponding Parquet file at the existing URL. Consequently, two analyses querying the same URL at different points in time can encounter different data vintages.

## Cache keys and provenance tracking

An HTTP ETag (entity tag) is a standard web header that serves as a unique fingerprint for a specific version of a file. When the International Forum on TOSSD publishes an updated dataset to `tossd.online`, the web server generates a new ETag string for the revised file.

`tossd-reader` uses this ETag to distinguish between different revisions of the same reporting year. Cache keys combine the target year and the server ETag (such as `tossd_{year}_{etag}`).

Every downloaded vintage generates a JSON provenance sidecar file (`<stem>.provenance.json`) saved in the local cache directory:

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

The provenance record stores the source URL, HTTP ETag, file size in bytes, SHA-256 cryptographic checksum, total row count, download timestamp, and package version. When the upstream publisher updates a file, the resulting new ETag initiates a fresh download while preserving previous cached files and their provenance records on disk.

## Export manifests for research reproducibility

When creating analytical extracts using `tossd.export()`, the package compiles an export manifest (`<stem>.manifest.json`) alongside the exported Parquet file:

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

The manifest records provenance metadata, upstream ETags, retrieval timestamps, schema hashes, row counts, export timestamps, and package versions. This provides an audit trail for published research, collaborative projects, and institutional reporting.

## Offline workflows and vintage stability

`tossd-reader` executes queries against local disk storage once files are cached. In offline environments or during upstream server maintenance, `get_tossd()` serves the latest cached vintage and issues a structured warning detailing the retrieval timestamp and ETag. Analysts can pin specific project workflows to verified local vintages for reproducible computation in automated test suites and analytical pipelines.

## Related

- [How to work offline and manage the cache](../how-to/work-offline.md). Local cache operations, offline mode, and forced refreshes.
- [Export](../reference/export.md). Schema and field definitions for the export manifest.
- [A reproducible extract](../tutorials/reproducible-extract.md). Tutorial on generating research-grade extracts with manifests.
