# Changelog

## 0.1.0 (unreleased)

Initial release. Covers TOSSD activity-level vintages 2019 to 2024.

### Added

- `get_tossd`: typed, filtered queries over the published per-year parquet
  files, with year/provider/recipient/pillar filters, `minimal`/`analysis`/
  `all` column presets, `usd_thousand` (default), `usd_million`, or `usd`
  units, an `include_aggregates=` toggle (`True` by default, matching the
  published records, `False` dropping `provider_code == 0` pseudo-aggregate
  rows), and always-present `year`, `is_aggregate`, and `unit` columns via
  the public `FORCED_COLUMNS` tuple. After a `providers=`/`recipients=`/
  `pillars=` filter, categorical columns carry only the categories present
  in the result.
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
- Five aggregation verbs, `rank_entities`, `compare_years`, `sdg_totals`,
  `keyword_totals`, and `subpillar_breakdown`, each summing a
  `get_tossd()`-shaped frame along one dimension. Each defaults
  `include_aggregates=False`, the opposite of `get_tossd()`'s own default,
  and copies `df.attrs` onto its result.
- The `df.tossd` pandas accessor, available on any DataFrame once
  `tossd_reader` has registered it (any query or helper import triggers
  registration). Carries the five aggregation verbs plus `add_iso3`,
  `add_recipient_group`, `add_instrument_group`, `extract_keywords`,
  `explode_sdg`, and `filter_provider_costs` as methods, and three
  accessor-only methods: `summary()` (a one-row overview of years, row
  counts, pillar mix, and unit), `exclude_aggregates()`, and
  `groupby_entity(dimension=)`.
- Packaged recipient-groups and instrument-groups reference tables.
  `add_recipient_group` (`scheme="ldc"|"income"|"region"`) and
  `add_instrument_group` join them onto a `get_tossd()`-shaped frame.
  `get_recipient_groups_version()` and `get_instrument_groups_version()`
  report each table's version stamp.
- Helpers: `explode_sdg` (an optional `value=` column adds a
  `{value}_weighted` sibling column), `add_iso3`, `extract_keywords`,
  `get_structural_breaks` (takes a keyword-only `years=` to scope results to
  the years being compared), `filter_provider_costs`. Missing-column errors
  now name the fix when the column ships in the `"analysis"` preset.
- Data canaries: weekly vintage-change detection and monthly full-download
  reconciliation against recorded headline totals.
- `get_tossd` and `get_tossd_raw` results now carry `df.attrs["tossd_reader"]`,
  the same provenance shape `load_export` already stamped: package version, a
  UTC timestamp, the normalised query, and each fetched year's etag, retrieval
  time, and source URL. `get_provenance(df)` reads it back as a deep copy.
- `reconcile(df)`: describes a `get_tossd()`-shaped frame against six manual
  reconciliation checks (aggregate share, both price-basis totals,
  core-contribution share, estimate-derived share, unmatched-recipient share,
  and year/pillar coverage) in one `pandas.Series`. Both `get_provenance` and
  `reconcile` are new `tossd_reader.verbs` functions and `df.tossd` accessor
  methods (`df.tossd.provenance()`, `df.tossd.reconcile()`).
- `get_vintages`: lists what the publisher has live right now, one row per
  year, from `get_tossd`'s own discovery sweep. Falls back to the local cache
  with a warning when offline mode is active or the publisher is unreachable,
  and raises the new `TossdNetworkError` if nothing is cached either.
- Offline mode: `set_offline`/`get_offline`, plus the `TOSSD_READER_OFFLINE`
  environment variable. Active offline mode serves cached vintages with a
  warning instead of touching the network. `refresh=True` combined with
  offline mode raises `ValueError` on `get_tossd`, `get_tossd_raw`, `export`,
  and `get_vintages` alike.
- `cache_info`: one row per cached vintage, a republished year counted
  separately rather than once per year. `clear_cache`: frees local cache
  space, filterable by `years=` and `before=`. The bare call drops only
  superseded vintages. `keep_latest=False` empties whatever `years=`/`before=`
  matches, the newest vintage included. Returns the number of entries
  removed.
- `export(..., max_rows=None)`: an opt-in guard. Once the table is built,
  raises `ValueError` naming the actual row count before anything is written,
  if it exceeds `max_rows`.

### Changed

- **Breaking:** `tossd_subpillar` is NA unless the row carries a real
  sub-pillar tag, with categories `"21"` and `"22"`. Pillar-1 rows,
  untagged pillar-2 rows, and pillar-0 rows now read NA instead of the
  previous sentinels `"1"` and `"2"`, so `.notna()` measures genuine
  sub-pillar coverage. `get_tossd_raw()` still returns the published
  sentinels verbatim.
- **Breaking:** `pillar2_provider_costs` is renamed `filter_provider_costs`.
  Behavior and the sector 910/930 carve-out are unchanged. No deprecation
  shim.

### Notes

- The cache stores publisher bytes verbatim and applies the schema layer at
  read time (measured at ~0.2s per year). Fetch-time validation rejects a
  defective vintage loudly, before it ever reaches the cache.
