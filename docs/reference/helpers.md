# Helpers

As of v0.1, `tossd_reader.helpers` ships five functions that run after
`get_tossd()`, on the frame it returns. All five take a `pandas.DataFrame`
and return a new one (`get_structural_breaks` takes none and returns the
packaged reference table instead). None of them mutate the frame you pass
in, and none of them touch the network. `add_iso3` looks like the one
exception. It resolves codes through a `resolvekit` module bundled for
offline use, so no request goes out.

Each helper checks its required columns up front and raises `ValueError`
naming the one it's missing, rather than failing later with a bare
`KeyError`. The table below is that contract at a glance.

| Helper                      | Requires                                | Smallest preset |
| --------------------------- | --------------------------------------- | --------------- |
| `explode_sdg`               | `sdg_codes_raw`                         | `"analysis"`    |
| `extract_keywords`          | `keywords_raw`                          | `"analysis"`    |
| `add_iso3`                  | `provider_code` and/or `recipient_code` | `"minimal"`     |
| `pillar2_own_country_costs` | `tossd_pillar`, `sector_code`           | `"analysis"`    |
| `get_structural_breaks`     | none, takes no frame                    | —               |

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

sen_a = tossd.get_tossd(recipients="Senegal", columns="analysis")
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

tossd.get_structural_breaks()
```

```
  dimension  break_year  end_year                                                                                                               description                         source
 sub_pillar        2022      2022                                      Sub-pillar tagging (Tossdpillar2 21/22) first appears as trace data: 24 rows in 2022    a4 audit of published files
 sub_pillar        2023      2023 Sub-pillar coverage ~51% of pillar-2 rows in 2023; ~99% in 2024 -- cross-year sub-pillar analysis is only clean from 2024    a4 audit of published files
   modality        2021      2021                                                                                   Modality code K02 first appears in 2021                       a4 audit
  reporters        2019      2024            Reporter base grows from 90 (2019) to 128 (2024); apparent growth in totals partly reflects reporting coverage                   a1/a4 audits
methodology        2026      2026    RDRM (revised debt-relief reporting methodology) takes effect May 2026 -- affects future vintages, not 2019-2024 files TOSSD Secretariat announcement
```

## Behavior reference

`explode_sdg`'s `sdg_weight` is `1 / n` for the `n` tokens a source row
carried, so the weights for any one tagged row sum to 1. Grouping the
exploded frame by `sdg_code` and summing `amount * sdg_weight` renormalises
to that row's original amount. Rows with no SDG tag at all are absent from
the exploded frame, so a weighted sum across the whole output covers only
the SDG-tagged subset of the input's totals.

`add_iso3` joins on the provider/recipient code, not the display name.
Provider codes 913 and 914 both display as "African Development Bank" in
the packaged codelist (909 and 1019 both display as "Inter-American
Development Bank"), so a name-keyed join would collapse distinct providers
into one row. Codes carry no such collision. Aggregate rows (code `0`),
multilaterals, and TOSSD-only entities all map to `NA` in the `iso3`
column, since none of them resolve to a single country.

`extract_keywords`'s 12 `kw_` columns come from the packaged
`_data/keyword_markers.csv` table. That fixed vocabulary is all it
recognises.

`pillar2_own_country_costs` is a verified heuristic, not an official TOSSD
category. Sector families 910 (administrative costs of donors) and 930
(in-donor refugee costs) accounted for 35.6% of pillar-2 gross
disbursements in 2024. TOSSD has not published an official
own-country-costs definition.

Next: [Analyse activities by SDG](../how-to/analyse-by-sdg.md) walks
through `explode_sdg` end to end. [Columns, presets, and units](columns.md)
lists what each preset carries.
