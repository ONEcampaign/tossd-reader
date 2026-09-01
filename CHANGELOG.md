# Changelog

## 0.1.0 (unreleased)

Initial release. Covers TOSSD activity-level vintages 2019 to 2024.

### Added

- `get_tossd`: typed, filtered queries over the published per-year parquet
  files, with year/provider/recipient/pillar filters, `minimal`/`analysis`/
  `all` column presets, USD-thousand or USD-million units, and always-present
  `year`, `is_aggregate`, and `unit` columns via the public `FORCED_COLUMNS`
  tuple. After a `providers=`/`recipients=`/`pillars=` filter, categorical
  columns carry only the categories present in the result.
- `get_tossd_raw`: the files exactly as published. An unexpected keyword now
  raises a `TypeError` that names the keyword and points to `get_tossd`.
- ETag-keyed local caching with provenance sidecars, fetch-time validation of
  new vintages, and offline fallback to cached vintages with a warning.
- `export`: normalised zstd parquet plus a manifest recording package
  version, schema hash, payload hash, row count, and per-year vintage
  provenance.
- `verify_export`/`load_export`: verify an export against its manifest and
  load it back with the schema's nullable integer dtypes intact and
  provenance attached to `df.attrs["tossd_reader"]`. Both raise the new
  `ExportIntegrityError` on a payload-hash or row-count mismatch.
- Packaged OECD codelist snapshot with `get_available_filters` and
  `get_codelists_version`.
- Weekly codelist drift monitoring against the live endpoint.
- Helpers: `explode_sdg`, `add_iso3`, `extract_keywords`,
  `get_structural_breaks` (takes a keyword-only `years=` to scope results to
  the years being compared), `pillar2_provider_costs`. Missing-column errors
  now name the fix when the column ships in the `"analysis"` preset.
- Data canaries: weekly vintage-change detection and monthly full-download
  reconciliation against recorded headline totals.

### Notes

- The cache stores publisher bytes verbatim and applies the schema layer at
  read time (measured at ~0.2s per year). Fetch-time validation rejects a
  defective vintage loudly, before it ever reaches the cache.
