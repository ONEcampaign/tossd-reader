# Columns, presets, and units

_As of v0.1._

tossd_reader publishes 53 columns from each TOSSD activity-level file, renamed
to snake_case and cast to the dtypes in `schema.csv`. The `columns=` argument
to `get_tossd` selects a subset, a named preset (`"minimal"`, `"analysis"`,
or `"all"`, the default) or an explicit `list[str]` of snake_case names.
Four columns are forced into the result regardless of that selection:
`tossd_pillar`, `tossd_subpillar`, `is_aggregate`, and `unit`. The first two
are published columns. `is_aggregate`, derived as `provider_code == 0`, and
`unit` are added by tossd_reader, so `columns="all"` returns 55 columns
against the file's 53. `parent_channel_name` is the one column
decoded from a codelist.

## Presets

| Preset     | Columns | Intent                                                                     |
| ---------- | :-----: | -------------------------------------------------------------------------- |
| `minimal`  |   19    | IDs, names, pillars, amounts.                                              |
| `analysis` |   44    | Adds sectors, channels, SDG and keyword raw fields, modalities.            |
| `all`      |   55    | Every packaged column, plus passthrough of any unexpected published extra. |

## Preset memory and timing

| `columns=`        | Columns |  2024 alone | All six years |
| ----------------- | :-----: | ----------: | ------------: |
| `"minimal"`       |   19    | 55MB, 0.05s |   278MB, 0.2s |
| `"analysis"`      |   44    | 102MB, 0.1s |   505MB, 0.6s |
| `"all"` (default) |   55    | 377MB, 0.2s |   2.1GB, 1.1s |

Memory is pandas `memory_usage(deep=True)` on the real 2026-04 vintage files.
Timings are warm-cache.

## All columns

Generated from `schema.csv`, in publisher-file order.

| Column                            | Dtype      | Minimal | Analysis | Notes                 |
| --------------------------------- | ---------- | :-----: | :------: | --------------------- |
| `year`                            | `Int16`    |    ✓    |    ✓     |                       |
| `provider_code`                   | `Int16`    |    ✓    |    ✓     |                       |
| `provider_name`                   | `category` |    ✓    |    ✓     |                       |
| `provider_agency_name`            | `category` |         |          |                       |
| `tossd_id`                        | `string`   |    ✓    |    ✓     |                       |
| `project_number`                  | `string`   |    ✓    |    ✓     |                       |
| `recipient_code`                  | `Int16`    |    ✓    |    ✓     |                       |
| `recipient_name`                  | `category` |    ✓    |    ✓     |                       |
| `region_name`                     | `category` |         |    ✓     |                       |
| `channel_raw_text`                | `string`   |         |          |                       |
| `channel_code`                    | `Int32`    |         |    ✓     |                       |
| `parent_channel_code`             | `Int32`    |         |          |                       |
| `parent_channel_name`             | `string`   |         |          | decoded from codelist |
| `other_partners`                  | `string`   |         |          |                       |
| `channel_name`                    | `category` |         |    ✓     |                       |
| `finance_instrument_code`         | `Int16`    |         |    ✓     |                       |
| `finance_instrument_name`         | `category` |         |    ✓     |                       |
| `financing_arrangement_code`      | `category` |         |    ✓     |                       |
| `financing_arrangement_name`      | `category` |         |    ✓     |                       |
| `framework_of_collaboration_code` | `category` |         |    ✓     |                       |
| `framework_of_collaboration_name` | `category` |         |    ✓     |                       |
| `modality_code`                   | `category` |         |    ✓     |                       |
| `modality_name`                   | `category` |         |    ✓     |                       |
| `project_title`                   | `string`   |         |          |                       |
| `external_link`                   | `string`   |         |          |                       |
| `sdg_codes_raw`                   | `string`   |         |    ✓     |                       |
| `sdg_goal_level_explanation`      | `string`   |         |          |                       |
| `keywords_raw`                    | `string`   |         |    ✓     |                       |
| `purpose_code`                    | `Int32`    |         |    ✓     |                       |
| `purpose_name`                    | `category` |         |    ✓     |                       |
| `sector_name`                     | `category` |         |    ✓     |                       |
| `sector_code`                     | `Int16`    |         |    ✓     |                       |
| `isic_code`                       | `category` |         |    ✓     |                       |
| `isic_description`                | `category` |         |    ✓     |                       |
| `isic_section_letter`             | `category` |         |    ✓     |                       |
| `isic_section_description`        | `category` |         |    ✓     |                       |
| `project_description`             | `string`   |         |          |                       |
| `tossd_pillar`                    | `Int8`     |    ✓    |    ✓     |                       |
| `tossd_subpillar`                 | `category` |    ✓    |    ✓     |                       |
| `usd_commitment`\*                | `float64`  |    ✓    |    ✓     |                       |
| `usd_commitment_deflated`\*       | `float64`  |    ✓    |    ✓     |                       |
| `usd_disbursement`\*              | `float64`  |    ✓    |    ✓     |                       |
| `usd_disbursement_deflated`\*     | `float64`  |    ✓    |    ✓     |                       |
| `usd_reflow`\*                    | `float64`  |    ✓    |    ✓     |                       |
| `usd_reflow_deflated`\*           | `float64`  |    ✓    |    ✓     |                       |
| `salary_cost`                     | `float64`  |         |          |                       |
| `concessionality_flag`            | `Int8`     |         |    ✓     |                       |
| `maturity`                        | `Int16`    |         |    ✓     |                       |
| `mobilisation_instrument`         | `category` |         |    ✓     |                       |
| `usd_amount_mobilised`\*          | `float64`  |    ✓    |    ✓     |                       |
| `usd_amount_mobilised_deflated`\* | `float64`  |    ✓    |    ✓     |                       |
| `mobilisation_origin`             | `string`   |         |          |                       |
| `source_name`                     | `category` |         |    ✓     |                       |

\* Reported in USD thousands. `units="usd_million"` divides these 8 columns
by 1000.

## Amount columns

| Column                          | 2024 non-null rows |
| ------------------------------- | -----------------: |
| `usd_commitment`                |            390,190 |
| `usd_commitment_deflated`       |            390,190 |
| `usd_disbursement`              |            441,645 |
| `usd_disbursement_deflated`     |            441,645 |
| `usd_reflow`                    |            215,264 |
| `usd_reflow_deflated`           |            215,264 |
| `usd_amount_mobilised`          |              1,693 |
| `usd_amount_mobilised_deflated` |              1,693 |

Each nominal column and its `_deflated` twin have identical non-null counts
in 2024. See [About the amount columns](../about/amounts.md) for what
distinguishes commitments, disbursements, reflows, and mobilised amounts, and
current from constant prices.

## Always present

| Column            | Dtype      | Meaning                                                                                                                 |
| ----------------- | ---------- | ----------------------------------------------------------------------------------------------------------------------- |
| `tossd_pillar`    | `Int8`     | Pillar number, `1`, `2`, or `0` for the 2020-2023 placeholder rows (a publisher artefact). |
| `tossd_subpillar` | `category` | Sub-pillar tag, `"21"` or `"22"`, where tagged.                                                                         |
| `is_aggregate`    | `bool`     | `provider_code == 0`.                                                                                                   |
| `unit`            | `category` | `"usd_thousand"` or `"usd_million"`, set by the `units=` argument to `get_tossd`.                                       |

## Data quality notes

- Empty strings in the published files become real nulls in `get_tossd`.
  `get_tossd_raw` leaves them as published.
- Modality code `c01` is normalised to `C01`. The published files carry both
  cases across years.
- `maturity`'s unit is undocumented by the publisher and is passed through
  as published.

## Schema drift

On every read, tossd_reader checks the published file's columns against
`schema.csv`. A published file missing a column the packaged schema expects
raises `SchemaDriftError`. So does a value that cannot be cast to its
`schema.csv` `target_dtype`, and a file carrying two columns whose names
normalise to the same key. The message names the column, and the offending
value where there is one.

<!-- prettier-ignore -->
!!! warning "Unrecognised schema columns"

    A column the file carries that `schema.csv` doesn't recognise warns once
    per process and passes through under its original name, visible only
    under `columns="all"`.

## Next

- [Pillars, aggregates, and breaks](../about/pillars-and-aggregates.md).
  Pillar and sub-pillar semantics, the pillar-0 placeholder rows, and the
  reporter-base structural break.
- [Query](query.md). `columns=` and `units=` in context, on `get_tossd`.
