# Helpers

_As of v0.1._

`tossd_reader.helpers` ships five functions that run on `get_tossd()` output. Four take a `pandas.DataFrame` and return a new one, leaving the input frame untouched. `get_structural_breaks` takes no argument and returns the packaged reference table. All five run offline. `add_iso3` resolves codes through a `resolvekit` module bundled with the package, so it needs no network.

Each helper checks its required columns up front and raises `ValueError` naming the column it's missing.

| Helper                      | Requires                                | Smallest preset |
| --------------------------- | --------------------------------------- | --------------- |
| `explode_sdg`               | `sdg_codes_raw`                         | `"analysis"`    |
| `extract_keywords`          | `keywords_raw`                          | `"analysis"`    |
| `add_iso3`                  | `provider_code` and/or `recipient_code` | `"minimal"`     |
| `pillar2_own_country_costs` | `tossd_pillar`, `sector_code`           | `"analysis"`    |
| `get_structural_breaks`     | none, takes no frame                    | n/a             |

<!-- prettier-ignore -->
::: tossd_reader.helpers.explode_sdg
    options:
      heading_level: 2

<!-- prettier-ignore -->
::: tossd_reader.helpers.extract_keywords
    options:
      heading_level: 2

```python
import tossd_reader as tossd

sen_a = tossd.get_tossd(years=2024, recipients="Senegal", columns="analysis")
kw = tossd.extract_keywords(sen_a)
kw_cols = [c for c in kw.columns if c.startswith("kw_")]
kw[kw_cols].sum().sort_values(ascending=False).head(6)
```

```
kw_gender              1308
kw_adaptation           599
kw_biodiversity         398
kw_mitigation           378
kw_ppr_preparedness     119
kw_covid_19              83
dtype: int64
```

<!-- prettier-ignore -->
::: tossd_reader.helpers.add_iso3
    options:
      heading_level: 2

<!-- prettier-ignore -->
::: tossd_reader.helpers.pillar2_own_country_costs
    options:
      heading_level: 2

<!-- prettier-ignore -->
::: tossd_reader.helpers.get_structural_breaks
    options:
      heading_level: 2

```python
import tossd_reader as tossd

breaks = tossd.get_structural_breaks()
print(breaks.drop(columns=["source"]).to_string(index=False))
```

```
  dimension  break_year  end_year                                                                                                                                                         description
 sub_pillar        2022      2022                                                                                Sub-pillar tagging (Tossdpillar2 21/22) first appears as trace data: 24 rows in 2022
 sub_pillar        2023      2023                                           Sub-pillar coverage ~51% of pillar-2 rows in 2023; ~99% in 2024. Cross-year sub-pillar analysis is only clean from 2024
   modality        2021      2021                                                                                                                             Modality code K02 first appears in 2021
  reporters        2019      2024 Reporter base grows from 97 (2019) to 130 (2024) distinct provider codes, counting provider_code != 0; apparent growth in totals partly reflects reporting coverage
methodology        2026      2026                                              RDRM (revised debt-relief reporting methodology) takes effect May 2026 -- applies to vintages published from that date
```

The frame's fifth column, `source`, names the audit each row is verified against. It's dropped from the block above for width.

## Next

- [Analyse activities by SDG](../how-to/analyse-by-sdg.md). `explode_sdg` end to end, from a query through the per-goal totals.
- [Measure climate and gender finance with keyword markers](../how-to/analyse-by-keyword.md). `extract_keywords` end to end, including how the twelve markers combine.
- [Measure how much Pillar II stays in donor countries](../how-to/own-country-costs.md). `pillar2_own_country_costs` end to end, with the sector split.
- [Join TOSSD to other country datasets](../how-to/join-other-datasets.md). `add_iso3` end to end, joined against another dataset's own ISO3 column.
