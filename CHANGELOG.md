# Changelog

## 0.1.0 (unreleased)

Initial release. Covers TOSSD activity-level vintages 2019 to 2024.

### Added

- `get_tossd`: typed, filtered queries over the published per-year parquet
  files, with year/provider/recipient/pillar filters, `minimal`/`analysis`/
  `all` column presets, USD-thousand or USD-million units, and always-present
  `is_aggregate` and `unit` columns.
- `get_tossd_raw`: the files exactly as published.
- ETag-keyed local caching with provenance sidecars, fetch-time validation of
  new vintages, and offline fallback to cached vintages with a warning.
- `export`: normalised zstd parquet plus a manifest recording package
  version, schema hash, and per-year vintage provenance.
- Packaged OECD codelist snapshot with `get_available_filters` and
  `get_codelists_version`.
- Weekly codelist drift monitoring against the live endpoint.
- Helpers: `explode_sdg`, `add_iso3`, `extract_keywords`,
  `get_structural_breaks`, `pillar2_own_country_costs`.
- Data canaries: weekly vintage-change detection and monthly full-download
  reconciliation against recorded headline totals.

### Notes

- The cache stores publisher bytes verbatim and applies the schema layer at
  read time (measured at ~0.2s per year). Fetch-time validation rejects a
  defective vintage loudly, before it ever reaches the cache.
