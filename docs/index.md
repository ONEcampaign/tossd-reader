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

Those are the publisher's own 2024 headline figures, reproduced from the raw
activity-level files in one call. tossd-reader downloads the per-year TOSSD
parquet files from [tossd.online](https://tossd.online), keeps them in a
local cache, and returns typed pandas frames with snake_case column names
and real nulls.

TOSSD, Total Official Support for Sustainable Development, is an
activity-level record of official development finance, published by the
TOSSD Secretariat. The published files run from 2019 to 2024, about 2.4
million rows, with amounts reported in USD thousands.

## Install

Python 3.12 or newer.

```bash
pip install git+https://github.com/ONEcampaign/tossd-reader.git
```

## Where to go next

- [Tutorial](tutorial.md) builds a year-by-pillar disbursement table for
  Senegal across all six published years, about ten minutes including the
  one-time download.
- [How to work offline and manage the cache](how-to/work-offline.md) covers
  moving the cache directory, forcing a refresh, and what happens when the
  publisher is unreachable.
- [How to export a reproducible extract](how-to/export-an-extract.md) walks
  through writing a full, unfiltered extract to parquet with a provenance
  manifest.
- [How to analyse activities by SDG](how-to/analyse-by-sdg.md) shows how to
  explode the packed SDG codes and sum weighted disbursements per goal.
- [Query and export](reference/query.md) documents `get_tossd`,
  `get_tossd_raw`, `export`, `get_available_filters`, and
  `get_codelists_version`.
- [Helpers](reference/helpers.md), [Columns, presets, and units](reference/columns.md),
  and [Configuration and errors](reference/configuration.md) cover the
  post-query helper functions, the column presets, and `set_cache_dir` with
  the exception hierarchy.
- [About the cache and provenance](about/caching.md) explains the cache's
  ETag-based provenance model.
- [About the data model](about/data-model.md) explains the pillar,
  aggregate, and structural-break concepts behind the data.
