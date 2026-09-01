# tossd-reader

Total Official Support for Sustainable Development (TOSSD) is an international standard tracked by the International Forum on TOSSD at [tossd.online](https://tossd.online). It measures cross-border development finance under Pillar I and expenditures for global public goods under Pillar II. The published dataset covers six years (2019 to 2024) across 2.4 million activity-level records.

`tossd-reader` provides Python analysts with clean, cached pandas DataFrames loaded directly from these official records. Annual files download once and cache locally on disk, so repeat queries run from local storage.

## Quick verification

A single query reproduces the 2024 published headline figures of USD 364.1 billion for Pillar I and USD 133.6 billion for Pillar II directly from the raw activity records.

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

## Install

Python 3.12 or newer.

=== "uv"

    ```bash
    uv add git+https://github.com/ONEcampaign/tossd-reader.git
    ```

=== "pip"

    ```bash
    pip install git+https://github.com/ONEcampaign/tossd-reader.git
    ```

## What the package handles

- Typed DataFrames with snake_case column names, standard numeric types, nullable integer codes, and string categoricals.
- Provider and recipient filtering by name or official code, with fuzzy suggestions for misspelled names.
- Double-counting protection through the `is_aggregate` flag to separate activity-level transactions from summary records.
- Domain helpers for multi-goal SDG weighting, thematic keyword tags for climate and gender, and constant-price deflators.
- Automatic disk caching to accelerate repeat queries.

## Data size and workflow

- Initial queries for a year download the full published annual dataset (55 to 91 MB per year).
- The `columns="minimal"` preset loads the core financial and classification fields, keeping memory usage low during interactive analysis.
- Query parameters filter on years, providers, recipients, and pillars at load time. Detailed filtering by sector, purpose, channel, and modality takes place in pandas on the returned DataFrame, as shown in [How to filter by sector, purpose, channel, or modality](how-to/filter-by-sector.md).

## Where to start

- [Build a six-year Senegal disbursement trend](tutorials/first-analysis.md) walks through a query, provider rankings, multi-year trends, and constant prices for Senegal.
- [About pillars and aggregate rows](about/pillars-and-aggregates.md) explains how Pillar I and Pillar II differ and how to handle summary records safely.
- [About the amount columns](about/amounts.md) details current prices, constant prices, and the eight financial metrics in the dataset.
- [Query](reference/query.md) documents `get_tossd()`, its filter parameters, and code resolution helpers.
