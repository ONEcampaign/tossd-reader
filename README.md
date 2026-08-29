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
billion for Pillar I and 133.6 billion for Pillar II, reproduced from the
raw activity-level files in one call. tossd-reader downloads the per-year
parquet files from the publisher's site, caches each one locally keyed to
its ETag, and returns typed pandas frames with snake_case column names.

## Install

Python 3.12 or newer.

```bash
pip install git+https://github.com/ONEcampaign/tossd-reader.git
```

## Quickstart

Filter by year, provider, recipient, or pillar with a code or an exact name.

```python
sen = tossd.get_tossd(
    years=2024, recipients="Senegal", columns="minimal", units="usd_million"
)
sen[~sen["is_aggregate"]].groupby(["provider_code", "provider_name"], observed=True)[
    "usd_disbursement"
].sum().sort_values(ascending=False).round(1).head(5)
```

```text
provider_code  provider_name                 
976            Islamic Development Bank          445.0
302            United States                     367.6
4              France                            306.4
913            African Development Bank Group    149.1
701            Japan                             116.7
Name: usd_disbursement, dtype: float64
```

`is_aggregate` marks rows reported by the publisher's own aggregate
pseudo-providers. Provider-level rankings exclude them. `provider_name`
collides too, with two provider codes sharing "African Development Bank
Group", so group by code and name together. A misspelled provider or
recipient name raises `UnknownCodeError` with close matches.

## What it does

TOSSD, Total Official Support for Sustainable Development, is an
activity-level record of official development finance published by the
TOSSD Secretariat. Six years, 2019 to 2024, about 2.4 million rows, amounts
in USD thousands. tossd-reader normalises the published files into typed
pandas frames, checks provider and recipient filters against packaged
codelists, and adds helpers for SDG splits, keyword markers, and country
lookups. `export()` writes a normalised extract to parquet with a manifest
recording the package version and each year's vintage.

## Documentation

The [docs site](https://onecampaign.github.io/tossd-reader/) covers a full
tutorial, task-oriented how-to guides, the API reference, and the concepts
behind pillars, aggregate rows, and comparability across years.

---

MIT licence, see [LICENSE](LICENSE). Data from the TOSSD Secretariat,
published at [tossd.online](https://tossd.online).
