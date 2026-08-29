# tossd-reader

> Cached, typed access to TOSSD activity-level data for pandas analysts.

```python
import tossd_reader as tossd

df = tossd.get_tossd(years=2024, columns="minimal", units="usd_million")
df.groupby("tossd_pillar")["usd_disbursement"].sum().round(1)
```

```text
tossd_pillar
1    364114.1
2    133561.8
Name: usd_disbursement, dtype: float64
```

Those are the TOSSD Secretariat's own 2024 headline figures, USD 364.1
billion for Pillar I and 133.6 billion for Pillar II, reproduced from the raw
activity-level files in one call.

TOSSD, Total Official Support for Sustainable Development, is an
activity-level record of official development finance, one row per
reported activity, published by the TOSSD Secretariat. The published files
run six years, 2019 to 2024, about 2.4 million rows, with amounts reported
in USD thousands.

tossd-reader downloads the per-year parquet files from the publisher's
site, caches each one locally keyed to its ETag, and returns typed pandas
frames with snake_case column names, nullable integers for codes, and
categoricals for names.

## Install

Python 3.12 or newer.

```bash
pip install git+https://github.com/ONEcampaign/tossd-reader.git
```

## What you get

- Typed columns and real nulls in place of the published empty strings.
- Name-or-code filters for providers, recipients, and pillars, checked
  against the packaged codelists, with suggestions on a misspelling.
- Derived `is_aggregate` and pillar tags in every result.
- A provenance record, URL, ETag, and retrieval time, for every cached
  vintage.

## Limits

- The first call for a year downloads the whole published file, 55 to 91MB.
  `columns="minimal"` reduces the memory the resulting frame uses. The
  download is the full published file either way.
- `get_tossd` filters on years, providers, recipients, and pillars. Sector,
  purpose, and channel are post-query pandas work, covered in [How to filter
  by sector, purpose, channel, or modality](how-to/filter-by-sector.md).
- There is no CLI.
- Installs from git. There is no package-index release.

## Where to start

- [Build a six-year Senegal disbursement trend](tutorials/first-analysis.md)
  walks one query through a provider ranking, a multi-year trend, and a
  switch to constant prices, about ten minutes.
- [About the amount columns](about/amounts.md) explains current versus
  deflated columns, a 20-point gap between them over 2019 to 2024.
- [Query](reference/query.md) documents `get_tossd`, its filters, and how
  to look up a provider or recipient name.
