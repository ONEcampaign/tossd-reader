# Helpers

The `tossd_reader.analysis` module provides analytical helper functions for working with `get_tossd()` outputs. Four functions accept a `pandas.DataFrame` and return a new DataFrame, leaving the input data unchanged. `get_structural_breaks` takes no DataFrame. Call it with an optional `years=` to narrow the packaged structural-break reference table to the years a query touches, or with no arguments for all five rows. All five functions operate entirely offline without network access.

Each DataFrame helper validates required columns before processing and raises a `ValueError` naming any missing column. When a missing column ships in the `"analysis"` preset, the message also names the fix:

```python
tossd.explode_sdg(tossd.get_tossd(years=2024, columns="minimal"))
```

```text
ValueError: explode_sdg() needs column(s) sdg_codes_raw, not present in df. Re-query with columns='analysis', or add sdg_codes_raw to your columns= list.
```

| Helper                   | Input Requirements                       | Minimum Preset | Output                                                                            |
| ------------------------ | ---------------------------------------- | -------------- | --------------------------------------------------------------------------------- |
| `explode_sdg`            | `sdg_codes_raw`                          | `"analysis"`   | Expanded DataFrame with `sdg_code`, `sdg_goal`, `sdg_is_target`, and `sdg_weight` |
| `extract_keywords`       | `keywords_raw`                           | `"analysis"`   | DataFrame with 12 `kw_<marker>` boolean columns                                   |
| `add_iso3`               | `provider_code` or `recipient_code`      | `"minimal"`    | DataFrame with `provider_iso3` or `recipient_iso3` categoricals                   |
| `pillar2_provider_costs` | `tossd_pillar`, `sector_code`            | `"analysis"`   | DataFrame filtered to Pillar II domestic expenditures (sectors 910 and 930)       |
| `get_structural_breaks`  | None; optional `years=` narrows the rows | n/a            | Reference DataFrame of dataset discontinuities (5 rows, fewer with `years=`)      |

<!-- prettier-ignore -->
::: tossd_reader.analysis.explode_sdg
    options:
      heading_level: 2

<!-- prettier-ignore -->
::: tossd_reader.analysis.extract_keywords
    options:
      heading_level: 2

```python
import tossd_reader as tossd

sen_a = tossd.get_tossd(years=2024, recipients="Senegal", columns="analysis")
kw = tossd.extract_keywords(sen_a)
kw_cols = [c for c in kw.columns if c.startswith("kw_")]
print(kw[kw_cols].sum().sort_values(ascending=False).head(6))
```

```text
kw_gender              1308
kw_adaptation           599
kw_biodiversity         398
kw_mitigation           378
kw_ppr_preparedness     119
kw_covid_19              83
dtype: int64
```

<!-- prettier-ignore -->
::: tossd_reader.analysis.add_iso3
    options:
      heading_level: 2

<!-- prettier-ignore -->
::: tossd_reader.analysis.pillar2_provider_costs
    options:
      heading_level: 2

<!-- prettier-ignore -->
::: tossd_reader.analysis.get_structural_breaks
    options:
      heading_level: 2

```python
import tossd_reader as tossd

breaks = tossd.get_structural_breaks()
print(
    breaks[["dimension", "break_year", "end_year", "description"]].to_string(
        index=False
    )
)
```

```text
  dimension  break_year  end_year                                                                                                                                                         description
 sub_pillar        2022      2022                                                                                Sub-pillar tagging (Tossdpillar2 21/22) first appears as trace data: 24 rows in 2022
 sub_pillar        2023      2023                                           Sub-pillar coverage ~51% of pillar-2 rows in 2023; ~99% in 2024. Cross-year sub-pillar analysis is only clean from 2024
   modality        2021      2021                                                                                                                             Modality code K02 first appears in 2021
  reporters        2019      2024 Reporter base grows from 97 (2019) to 130 (2024) distinct provider codes, counting provider_code != 0; apparent growth in totals partly reflects reporting coverage
methodology        2026      2026                                              RDRM (revised debt-relief reporting methodology) takes effect May 2026, applying to vintages published from that date
```

The table's fifth column, `source`, names the verification reference for each discontinuity.

Pass `years=` to narrow the table to breaks that intersect a query's own years, so `get_structural_breaks(years=query_years)` names only what's relevant to a matching `get_tossd(years=query_years)` call.

```python
tossd.get_structural_breaks(years=2021)
```

```text
dimension  break_year  end_year                                      description                                        source
 modality        2021      2021          Modality code K02 first appears in 2021                      audit of published files
reporters        2019      2024 Reporter base grows from 97 (2019) to 130 (20...  distinct provider_code in the published files
```

## Next

- [Split disbursements across SDG goals](../how-to/analyse-by-sdg.md). Practical workflow for `explode_sdg` with weighted sums.
- [Measure climate and gender finance](../how-to/analyse-by-keyword.md). Working with the 12 policy marker columns.
- [Measure Pillar II expenditures in the provider country](../how-to/provider-costs.md). In-donor cost methodology and sector breakdown.
- [Join TOSSD to other country datasets](../how-to/join-other-datasets.md). Joining country data on `provider_iso3` and `recipient_iso3`.
