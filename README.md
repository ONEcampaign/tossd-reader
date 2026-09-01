# tossd-reader

Total Official Support for Sustainable Development (TOSSD) is an international standard tracked by the International Forum on TOSSD (IFT) at [tossd.online](https://tossd.online). It measures cross-border development finance under Pillar I and expenditures for global public goods under Pillar II. The published dataset covers six years (2019 to 2024) across 2.4 million activity-level records.

`tossd-reader` provides Python analysts with typed, cached pandas DataFrames loaded directly from these official records. Annual files download once and cache locally on disk, so repeat queries run from local storage.

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

A single query reproduces the 2024 published headline figures of USD 364.1 billion for Pillar I and USD 133.6 billion for Pillar II directly from the raw activity records.

## Install

Python 3.12 or newer.

### uv

```bash
uv add git+https://github.com/ONEcampaign/tossd-reader.git
```

### pip

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

The `is_aggregate` flag marks rows reported by the publisher's aggregate pseudo-providers. Activity-level provider rankings filter on `~is_aggregate` to prevent double-counting. Two provider codes share the name African Development Bank Group, so grouping by code and name preserves distinct entities. Filter parameters accept official codes and exact names, and misspelled names return close matches in `UnknownCodeError`.

## What it does

`tossd-reader` normalises published annual parquet files into typed pandas DataFrames with snake_case column names, standard numeric types, nullable integer codes, and string categoricals. It validates provider and recipient filters against packaged codelists and provides helpers for multi-goal SDG weighting, thematic keyword markers, and country code lookups. The `export()` function writes normalised extracts to parquet with a manifest recording the package version and data vintages.

## Documentation

The [documentation site](https://onecampaign.github.io/tossd-reader/) provides tutorials, how-to guides, an API reference, and background notes on pillars, aggregate rows, and data comparability across years.

---

MIT licence, see [LICENSE](LICENSE). Data from the International Forum on TOSSD, published at [tossd.online](https://tossd.online).
