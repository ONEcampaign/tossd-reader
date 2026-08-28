# tossd-reader

> Cached, typed access to TOSSD activity-level data for pandas analysts.

```python
import tossd_reader as tossd

df = tossd.get_tossd(years=2024, columns="minimal", units="usd_million")
df.groupby("tossd_pillar")["usd_disbursement"].sum()
```

```text
tossd_pillar
1    364114.1
2    133561.8
Name: usd_disbursement, dtype: float64
```

Those are the publisher's own 2024 headline figures (USD 364.1bn Pillar I,
133.6bn Pillar II), reproduced from the raw activity-level files in one call.
The package downloads the per-year parquet files from
[tossd.online](https://tossd.online), caches them locally, and hands you clean
typed frames.

TOSSD (Total Official Support for Sustainable Development) records official
development finance activity by activity. The published files cover 2019 to
2024, about 2.4 million rows, with amounts in USD thousands.

## Install

Python 3.12 or newer. The package is a v0.1 pilot and installs from the
repository:

```bash
pip install git+https://github.com/ONEcampaign/tossd-reader.git
```

## Quickstart

Filter by year, provider, recipient, or pillar. Providers and recipients
accept codes or exact names (matched case-insensitively):

```python
spain = tossd.get_tossd(years=2024, providers="Spain", pillars=1,
                        columns="minimal", units="usd_million")
spain["usd_disbursement"].sum()
```

```text
922.0
```

To see what values a filter accepts, browse the packaged codelists:

```python
filters = tossd.get_available_filters()
filters["provider"].head(3)
```

```text
  code     name  tossd_only iso3
0    1  Austria       False  AUT
1    2  Belgium       False  BEL
2    3  Denmark       False  DNK
```

A misspelled name raises `UnknownCodeError` with suggestions. The first call
for a year downloads its file (30 to 90MB). Later calls read from the local
cache in well under a second.

## Columns, presets, and units

The raw files ship 53 columns with inconsistent naming and empty strings for
missing values. `get_tossd` returns snake_case names, typed columns (nullable
integers for codes, categoricals for names, float64 for amounts), and real
nulls. Pick how much of it you want:

| `columns=`        | columns |  2024 alone | all six years |
| ----------------- | ------: | ----------: | ------------: |
| `"minimal"`       |      19 | 55MB, 0.05s |   278MB, 0.2s |
| `"analysis"`      |      44 | 102MB, 0.1s |   505MB, 0.6s |
| `"all"` (default) |      55 | 377MB, 0.2s |   2.1GB, 1.1s |

Memory is pandas `memory_usage(deep=True)` on the real 2026-04 vintage files.
Timings are warm-cache. An explicit list of column names works too, and an
unknown name raises with close matches.

Amounts are published in USD thousands. `units="usd_million"` converts the
eight `usd_*` amount columns. Two derived columns are always present:

- `unit` records which unit the amounts are in.
- `is_aggregate` marks rows reported by "aggregate" pseudo-providers
  (provider code 0). These rows carry about 20% of 2024 disbursements and
  are part of the publisher's headline totals, so keep them for totals and
  drop them for provider-level analysis.

`get_tossd_raw(years=...)` is the escape hatch: publisher column names,
dtypes, and empty-string nulls, verbatim.

## Pillars and years

`pillars=` accepts `1`, `2`, `21`, `22`, `"I"`, `"II"`, `"II.A"`, `"II.B"`.
Sub-pillar tagging (II.A and II.B) is usable from 2023 onward, and cleanly
only from 2024:

- 2022 files carry 24 trace-tagged rows. Requesting a sub-pillar with
  explicit years before 2023 raises `InvalidPillarError`.
- In 2023 about half of Pillar II rows carry no sub-pillar tag. Sub-pillar
  queries touching 2023 warn with that coverage figure.
- `get_tossd(pillars="II.A")` with no explicit years narrows to the valid
  years and warns about the narrowing.

The 2020 to 2023 files also contain a few hundred placeholder rows with
pillar `0`. Any `pillars=` filter excludes them. Unfiltered queries keep
them.

`tossd.get_structural_breaks()` returns a small reference table of verified
cross-year discontinuities (sub-pillar rollout, the K02 modality's 2021
introduction, reporter-base growth from 90 to 128 providers, the May 2026
RDRM methodology change). Consult it before comparing years, because some
apparent growth reflects reporting coverage rather than new finance.

## Caching, vintages, and offline use

Each downloaded file is cached keyed by the publisher's ETag, so a
republished vintage is fetched fresh while the old one remains on disk. Every
cache entry gets a provenance sidecar (URL, ETag, SHA-256, row count,
retrieval time). New downloads are validated before they enter the cache, and
a corrupt file raises `VintageValidationError` at fetch time.

When the publisher is unreachable and a year is cached, you get the cached
vintage plus one loud warning naming its retrieval date. With nothing cached,
you get `TossdNetworkError`. An empty result always comes back with a warning.

- `tossd.set_cache_dir(path)` moves the cache (`TOSSD_READER_CACHE_DIR` works
  too). `set_cache_dir(None)` switches to an ephemeral per-session cache.
- `refresh=True` on any query revalidates against the publisher.
- `tossd.export("out/", years=...)` writes the normalised frame to zstd
  parquet with a manifest recording the package version, schema hash, and
  per-year vintage provenance. Use it to freeze an analysis input.
- `tossd.get_codelists_version()` returns the packaged codelist snapshot's
  fetch date.

## Helpers

Five functions operate on `get_tossd` output:

- **`explode_sdg(df)`** splits the `;`-packed `sdg_codes_raw` into one row
  per SDG goal or target, with a `sdg_weight` of 1/n so
  `amount * sdg_weight` sums back to the SDG-tagged subtotal. Rows without
  SDG tags are dropped from the exploded frame, so its total is the tagged
  subtotal, a subset of the full total.
- **`add_iso3(df)`** adds `provider_iso3`/`recipient_iso3`. The lookup keys
  on codes because in-file names collide: codes 913 and 914 both display as
  "African Development Bank", and 909 and 1019 both display as
  "Inter-American Development Bank". Aggregates and multilaterals get `NA`.
- **`extract_keywords(df)`** adds boolean columns for a fixed 12-marker
  vocabulary from the `|`-packed keywords field: gender, adaptation,
  mitigation, biodiversity, ppr_preparedness, ppr_response, covid_19,
  refugees_hostcommunities, idps_hostcommunities,
  voluntaryrefugeereturn_reintegration, transnational_benefits_global, and
  non_17_3_1. Matching casefolds and strips a leading `#`.
- **`get_structural_breaks()`** returns the reference table described above.
- **`pillar2_own_country_costs(df)`** filters Pillar II to spending that
  stays in the provider's own country: administrative costs (sector family 910) and in-donor refugee costs (sector family 930). On 2024 data that is
  27,275 rows and 35.6% of Pillar II disbursements, consistent with the
  roughly 30% share civil-society critiques attribute to these costs. The
  rule is a verified heuristic. TOSSD publishes no official own-country-costs
  definition yet.

## Data quality notes

Things the package normalises or passes through that are worth knowing:

- String nulls in the raw files are empty strings. `get_tossd` converts them
  to real nulls. `get_tossd_raw` leaves them as published.
- One modality code appears as both `c01` and `C01` across years and is
  normalised to `C01`.
- `sector` and `purpose_code` are single-valued per row in the 2019 to 2024
  bulk files, so amounts sum without splitting.
- Concessionality is a column (`concessionality_flag` in the analysis
  preset). The flag is as reported by providers, so treat it as a claim
  rather than a derived fact.
- The `maturity` column's unit is undocumented by the publisher and is
  passed through as published.
- If a future vintage renames or drops a column, queries fail loudly with
  `SchemaDriftError`. Columns added by the publisher pass through into
  `columns="all"` with a warning.

---

Data: [TOSSD](https://tossd.online), published by the TOSSD Secretariat.
Codelists: OECD development-finance codelists (snapshot date via
`get_codelists_version()`). Built at the ONE Campaign.
