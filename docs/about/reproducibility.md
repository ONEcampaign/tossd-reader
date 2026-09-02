# About reproducibility and the cache

TOSSD datasets are published annually by the International Forum on TOSSD at fixed endpoints on [tossd.online](https://tossd.online). Because the Secretariat republishes datasets in place to incorporate retroactive corrections, provider revisions, and late submissions, analytical reproducibility requires tracking specific data vintages.

## In-place publication and data vintages

The official portal provides one endpoint per calendar year (`https://tossd.online/tossddata_{year}.parquet`). When a provider submits revisions for an earlier reporting period, the publisher updates the corresponding Parquet file at the existing URL. Consequently, two analyses querying the same URL at different points in time can encounter different data vintages.

## Cache keys and provenance tracking

An HTTP ETag (entity tag) is a standard web header that fingerprints a specific version of a file. When the International Forum on TOSSD publishes a revised dataset to `tossd.online`, the web server generates a new ETag for the file. Conversely, the host server occasionally formats ETags differently for unchanged content, so differing ETag strings do not by themselves indicate that the underlying data changed.

`tossd-reader` uses this ETag to distinguish between different revisions of the same reporting year. Cache keys combine the target year and the server ETag (such as `tossd_{year}_{etag}`).

Every downloaded vintage generates a JSON provenance sidecar file (`<stem>.provenance.json`) saved in the local cache directory.

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

## Provenance on query results

Every `get_tossd()`, `get_tossd_raw()`, and `load_export()` call stamps `df.attrs["tossd_reader"]` on its result before filtering or unit conversion occurs. Every verb and `df.tossd` accessor method copies `df.attrs` onto its return value, preserving provenance across chained calls such as `df.tossd.rank_entities()` or `explode_sdg(df)`. Standard pandas operations (such as merges, concatenations, or aggregations) can drop `attrs`. Read provenance early or retain the original query result to access metadata.

`get_provenance(df)` (also `df.tossd.provenance()`) reads that record back as a deep copy, allowing callers to mutate the returned dictionary freely.

```python
import tossd_reader as tossd
from pprint import pprint

df = tossd.get_tossd(years=2024, columns="analysis", units="usd_million")
pprint(tossd.get_provenance(df))
```

```text
{'created_at': '2026-09-02T12:23:44.126187+00:00',
 'package_version': '0.1.0',
 'query': {'columns': 'analysis',
           'filters': {},
           'include_aggregates': True,
           'pillars': None,
           'providers': None,
           'recipients': None,
           'refresh': False,
           'units': 'usd_million',
           'years': (2024,)},
 'years': {'2024': {'etag': '"69e6ac8d-5728379"',
                    'retrieved_at': '2026-09-02T12:21:52.639935+00:00',
                    'url': 'https://tossd.online/tossddata_2024.parquet'}}}
```

`df.tossd.provenance()` returns the identical dict. The whole payload is JSON-serialisable, ready for direct storage in run logs or audit records.

`get_tossd_raw()` produces the same structure, with a smaller `query` dictionary holding only `years` and `refresh`, as it applies no filtering or unit conversion. DataFrames loaded with `load_export()` contain `package_version`, `created_at`, and `years`. Export files store complete annual extracts, so their provenance records omit the `query` key.

```python
loaded = tossd.load_export("exports/tossd_2019.parquet")
pprint(tossd.get_provenance(loaded))
```

```text
{'created_at': '2026-09-02T12:20:31.461315+00:00',
 'package_version': '0.1.0',
 'years': {'2019': {'etag': '"69e6ac86-347a653"',
                    'retrieved_at': '2026-09-02T12:20:30.461811+00:00'}}}
```

Calling `get_provenance()` on a DataFrame lacking this metadata raises a `ValueError`, identifying the three functions that attach provenance attributes.

```text
ValueError: get_provenance() found no df.attrs['tossd_reader'] -- that key is set by get_tossd(), get_tossd_raw(), and load_export(); a frame built some other way (or a plain pandas operation that dropped attrs along the way) carries none.
```

## Export manifests for research reproducibility

When creating analytical extracts using `tossd.export()`, the package compiles an export manifest (`<stem>.manifest.json`) alongside the exported Parquet file.

<!-- prettier-ignore -->
```json
{
  "created_at": "2026-09-02T08:23:33.812561+00:00",
  "payload_sha256": "8a6eed10875a87fcd5faedece760bc461aa5926113ba1686613728c8c27d30bf",
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

The manifest records provenance metadata, upstream ETags, retrieval timestamps, schema hashes, payload hashes, row counts, export timestamps, and package versions.

`verify_export()` recomputes `payload_sha256` from the Parquet file and confirms that it matches the manifest. `load_export()` calls `verify_export()` before reading the file, raising an error if the file no longer matches its manifest.

## Offline workflows and vintage stability

`tossd-reader` executes queries against local disk storage once files are cached. In offline environments or during upstream server maintenance, `get_tossd()` serves the latest cached vintage and issues a structured warning detailing the retrieval timestamp and ETag.

Setting offline mode explicitly (`tossd.set_offline(True)` or the `TOSSD_READER_OFFLINE` environment variable) restricts all operations to the local cache. In offline mode, queries for uncached years raise `TossdNetworkError`. See [How to work offline and manage the cache](../how-to/work-offline.md) for offline cache management.

`get_vintages()` and `cache_info()` inspect available data vintages. `get_vintages()` performs a live discovery sweep and reports the current file metadata and ETag at each year's URL. `cache_info()` inspects locally cached files with one row per retrieved vintage, displaying multiple entries when a single year has been downloaded under multiple ETags.

<!-- prettier-ignore -->
!!! warning "Inconsistent ETag formatting on upstream server"
    The upstream server occasionally formats ETags differently for unchanged files. An ETag difference between `get_vintages()` and `cache_info()` can occur without changes to the underlying data. Verify file contents before assuming a new vintage.

## Related

- [How to work offline and manage the cache](../how-to/work-offline.md). Local cache operations, offline mode, and forced refreshes.
- [Configuration reference](../reference/configuration.md). Offline mode, `cache_info()`, and `clear_cache()`.
- [Export](../reference/export.md). Schema and field definitions for the export manifest.
- [A reproducible extract](../tutorials/reproducible-extract.md). Tutorial on generating research-grade extracts with manifests.
